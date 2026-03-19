from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, replace
from io import BytesIO
import logging
from threading import Event, Lock

from document import (
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    extract_document_content_from_docx,
)
from logger import log_event
from models import ImageAsset, ImagePipelineMetadata, ImageValidationResult, ImageVariantCandidate


@dataclass
class PreparedDocumentData:
    source_text: str
    paragraphs: list
    image_assets: list
    jobs: list[dict[str, object]]
    prepared_source_key: str
    cached: bool = False


PREPARATION_CACHE_LIMIT = 2
_shared_preparation_cache: OrderedDict[str, PreparedDocumentData] = OrderedDict()
_shared_preparation_cache_lock = Lock()
_shared_preparation_inflight: dict[str, Event] = {}


def emit_preparation_progress(progress_callback, *, stage: str, detail: str, progress: float, metrics: dict[str, object] | None = None) -> None:
    if progress_callback is None:
        return
    progress_callback(stage=stage, detail=detail, progress=progress, metrics=metrics or {})


def build_prepared_source_key(uploaded_file_token: str, chunk_size: int) -> str:
    return f"{uploaded_file_token}:{chunk_size}"


def _build_in_memory_uploaded_file(*, source_name: str, source_bytes: bytes):
    uploaded_file = BytesIO(source_bytes)
    uploaded_file.name = source_name
    setattr(uploaded_file, "size", len(source_bytes))
    return uploaded_file


def _prepare_document_for_processing(source_name: str, source_bytes: bytes, chunk_size: int, *, progress_callback=None):
    emit_preparation_progress(
        progress_callback,
        stage="Разбор DOCX",
        detail="Извлекаю абзацы и встроенные изображения.",
        progress=0.3,
    )
    uploaded_file = _build_in_memory_uploaded_file(source_name=source_name, source_bytes=source_bytes)
    paragraphs, image_assets = extract_document_content_from_docx(uploaded_file)
    emit_preparation_progress(
        progress_callback,
        stage="Структура извлечена",
        detail="Документ прочитан, собираю текст для анализа.",
        progress=0.5,
        metrics={
            "paragraph_count": len(paragraphs),
            "image_count": len(image_assets),
        },
    )
    source_text = build_document_text(paragraphs)
    emit_preparation_progress(
        progress_callback,
        stage="Текст собран",
        detail="Формирую цельный текст документа и считаю объём.",
        progress=0.65,
        metrics={
            "paragraph_count": len(paragraphs),
            "image_count": len(image_assets),
            "source_chars": len(source_text),
        },
    )
    blocks = build_semantic_blocks(paragraphs, max_chars=chunk_size)
    emit_preparation_progress(
        progress_callback,
        stage="Смысловые блоки",
        detail="Группирую абзацы в блоки для модели.",
        progress=0.8,
        metrics={
            "paragraph_count": len(paragraphs),
            "image_count": len(image_assets),
            "source_chars": len(source_text),
            "block_count": len(blocks),
        },
    )
    jobs = build_editing_jobs(blocks, max_chars=chunk_size)
    emit_preparation_progress(
        progress_callback,
        stage="Задания собраны",
        detail="Готовлю финальный набор задач для обработки.",
        progress=0.92,
        metrics={
            "paragraph_count": len(paragraphs),
            "image_count": len(image_assets),
            "source_chars": len(source_text),
            "block_count": len(jobs),
        },
    )
    return PreparedDocumentData(
        source_text=source_text,
        paragraphs=paragraphs,
        image_assets=image_assets,
        jobs=jobs,
        prepared_source_key="",
        cached=False,
    )


def _get_preparation_cache(session_state) -> dict[str, PreparedDocumentData]:
    if session_state is None:
        return {}
    cache = session_state.get("preparation_cache")
    if not isinstance(cache, dict):
        cache = {}
        session_state["preparation_cache"] = cache
    return cache


def _touch_cache_entry(cache: dict[str, PreparedDocumentData], prepared_source_key: str, prepared_document: PreparedDocumentData) -> None:
    cache.pop(prepared_source_key, None)
    cache[prepared_source_key] = prepared_document


def _trim_cache(cache: dict[str, PreparedDocumentData]) -> None:
    while len(cache) > PREPARATION_CACHE_LIMIT:
        oldest_key = next(iter(cache))
        cache.pop(oldest_key, None)


def _read_cache_entry(cache: dict[str, PreparedDocumentData], prepared_source_key: str):
    cached = cache.get(prepared_source_key)
    if cached is None:
        return None
    _touch_cache_entry(cache, prepared_source_key, cached)
    return cached


def _clone_prepared_document(data: PreparedDocumentData, prepared_source_key: str, *, cached: bool) -> PreparedDocumentData:
    return PreparedDocumentData(
        source_text=data.source_text,
        paragraphs=deepcopy(data.paragraphs),
        image_assets=[_clone_prepared_image_asset(asset) for asset in data.image_assets],
        jobs=[dict(job) for job in data.jobs],
        prepared_source_key=prepared_source_key,
        cached=cached,
    )


def _clone_prepared_image_variant(variant):
    if isinstance(variant, ImageVariantCandidate):
        return replace(
            variant,
            validation_result=deepcopy(variant.validation_result),
        )
    if isinstance(variant, dict):
        cloned_variant = dict(variant)
        if "validation_result" in cloned_variant:
            cloned_variant["validation_result"] = deepcopy(cloned_variant["validation_result"])
        return cloned_variant
    return deepcopy(variant)


def _clone_prepared_image_asset(asset):
    if not isinstance(asset, ImageAsset):
        return deepcopy(asset)
    return replace(
        asset,
        analysis_result=deepcopy(asset.analysis_result),
        metadata=replace(asset.metadata) if isinstance(asset.metadata, ImagePipelineMetadata) else deepcopy(asset.metadata),
        validation_result=deepcopy(asset.validation_result),
        attempt_variants=[_clone_prepared_image_variant(variant) for variant in asset.attempt_variants],
        comparison_variants={
            variant_key: _clone_prepared_image_variant(variant)
            for variant_key, variant in asset.comparison_variants.items()
        },
    )


def _read_or_reserve_cached_prepared_document(*, session_state, prepared_source_key: str):
    # Session cache is only touched from the Streamlit rerun thread. Background preparation
    # workers always pass session_state=None and only participate in the shared cache path.
    session_cache = _get_preparation_cache(session_state) if session_state is not None else None
    if session_cache is not None:
        cached = _read_cache_entry(session_cache, prepared_source_key)
        if cached is not None:
            return _clone_prepared_document(cached, prepared_source_key, cached=True), None, "session"

    while True:
        with _shared_preparation_cache_lock:
            cached = _read_cache_entry(_shared_preparation_cache, prepared_source_key)
            if cached is not None:
                if session_cache is not None:
                    _touch_cache_entry(session_cache, prepared_source_key, cached)
                    _trim_cache(session_cache)
                return _clone_prepared_document(cached, prepared_source_key, cached=True), None, "shared"

            in_flight = _shared_preparation_inflight.get(prepared_source_key)
            if in_flight is None:
                in_flight = Event()
                _shared_preparation_inflight[prepared_source_key] = in_flight
                return None, in_flight, None

        in_flight.wait()


def _release_shared_preparation(prepared_source_key: str) -> None:
    with _shared_preparation_cache_lock:
        in_flight = _shared_preparation_inflight.pop(prepared_source_key, None)
    if in_flight is not None:
        in_flight.set()


def _store_cached_prepared_document(*, session_state, prepared_source_key: str, prepared_document: PreparedDocumentData) -> None:
    prepared_document.prepared_source_key = ""
    prepared_document.cached = False
    if session_state is not None:
        cache = _get_preparation_cache(session_state)
        _touch_cache_entry(cache, prepared_source_key, prepared_document)
        _trim_cache(cache)

    with _shared_preparation_cache_lock:
        _touch_cache_entry(_shared_preparation_cache, prepared_source_key, prepared_document)
        _trim_cache(_shared_preparation_cache)


def clear_preparation_cache(*, session_state=None, clear_shared: bool = False) -> None:
    if session_state is not None:
        session_state["preparation_cache"] = {}
    if clear_shared:
        with _shared_preparation_cache_lock:
            _shared_preparation_cache.clear()


def prepare_document_for_processing(*, uploaded_filename: str, source_bytes: bytes, uploaded_file_token: str, chunk_size: int, session_state=None, progress_callback=None) -> PreparedDocumentData:
    prepared_source_key = build_prepared_source_key(uploaded_file_token, chunk_size)
    cached, in_flight, cache_level = _read_or_reserve_cached_prepared_document(
        session_state=session_state,
        prepared_source_key=prepared_source_key,
    )
    if cached is not None:
        log_event(
            logging.INFO,
            "preparation_cache_hit",
            "Использован кэш подготовки документа.",
            prepared_source_key=prepared_source_key,
            cache_level=cache_level,
        )
        emit_preparation_progress(
            progress_callback,
            stage="Подготовка документа",
            detail="Использую кэш подготовки для текущего файла.",
            progress=0.95,
            metrics={
                "paragraph_count": len(cached.paragraphs),
                "image_count": len(cached.image_assets),
                "source_chars": len(cached.source_text),
                "block_count": len(cached.jobs),
                "cached": cached.cached,
            },
        )
        return cached

    log_event(
        logging.INFO,
        "preparation_cache_miss",
        "Подготовка документа выполняется без готового cache-hit.",
        prepared_source_key=prepared_source_key,
    )

    try:
        prepared_document = _prepare_document_for_processing(
            uploaded_filename,
            source_bytes,
            chunk_size,
            progress_callback=progress_callback,
        )
        _store_cached_prepared_document(
            session_state=session_state,
            prepared_source_key=prepared_source_key,
            prepared_document=prepared_document,
        )
    except Exception:
        if in_flight is not None:
            _release_shared_preparation(prepared_source_key)
        raise

    if in_flight is not None:
        _release_shared_preparation(prepared_source_key)
    return _clone_prepared_document(prepared_document, prepared_source_key, cached=False)
