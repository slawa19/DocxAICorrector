from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
import logging
from threading import Event, Lock

from config import get_client, load_app_config
from document import (
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    extract_document_content_with_normalization_reports,
    summarize_boundary_normalization_metrics,
)
from logger import log_event
from models import ParagraphBoundaryNormalizationReport, ParagraphRelation, RelationNormalizationReport
from models import clone_prepared_image_asset
from models import StructureMap
from processing_runtime import FrozenUploadPayload, build_in_memory_uploaded_file
from structure_recognition import apply_structure_map, build_structure_map


@dataclass
class PreparedDocumentData:
    source_text: str
    paragraphs: list
    image_assets: list
    relations: list[ParagraphRelation]
    jobs: list[dict[str, object]]
    prepared_source_key: str
    normalization_report: ParagraphBoundaryNormalizationReport | None = None
    relation_report: RelationNormalizationReport | None = None
    structure_map: StructureMap | None = None
    ai_classified_count: int = 0
    ai_heading_count: int = 0
    ai_role_change_count: int = 0
    ai_heading_promotion_count: int = 0
    ai_heading_demotion_count: int = 0
    ai_structural_role_change_count: int = 0
    cached: bool = False


def _build_normalization_metrics(
    normalization_report: ParagraphBoundaryNormalizationReport | None,
    relation_report: RelationNormalizationReport | None = None,
) -> dict[str, int]:
    metrics: dict[str, int] = {}
    if normalization_report is not None:
        metrics.update(
            {
                "raw_paragraph_count": normalization_report.total_raw_paragraphs,
                "logical_paragraph_count": normalization_report.total_logical_paragraphs,
                "merged_group_count": normalization_report.merged_group_count,
                "merged_raw_paragraph_count": normalization_report.merged_raw_paragraph_count,
            }
        )
        metrics.update(summarize_boundary_normalization_metrics(normalization_report))
    if relation_report is not None:
        metrics.update(
            {
                "relation_count": relation_report.total_relations,
                "rejected_relation_candidate_count": relation_report.rejected_candidate_count,
            }
        )
        for relation_kind, count in relation_report.relation_counts.items():
            metrics[f"relation_{relation_kind}_count"] = count
    return metrics


def _build_structure_metrics(
    *,
    structure_map: StructureMap | None,
    ai_classified_count: int = 0,
    ai_heading_count: int = 0,
    ai_role_change_count: int = 0,
    ai_heading_promotion_count: int = 0,
    ai_heading_demotion_count: int = 0,
    ai_structural_role_change_count: int = 0,
) -> dict[str, int]:
    metrics: dict[str, int] = {}
    if structure_map is not None:
        metrics["structure_window_count"] = structure_map.window_count
    if ai_classified_count:
        metrics["ai_classified"] = ai_classified_count
    if ai_heading_count:
        metrics["ai_headings"] = ai_heading_count
    if ai_role_change_count:
        metrics["ai_role_changes"] = ai_role_change_count
    if ai_heading_promotion_count:
        metrics["ai_heading_promotions"] = ai_heading_promotion_count
    if ai_heading_demotion_count:
        metrics["ai_heading_demotions"] = ai_heading_demotion_count
    if ai_structural_role_change_count:
        metrics["ai_structural_role_changes"] = ai_structural_role_change_count
    return metrics


def _capture_structure_baseline(paragraphs: list) -> dict[int, tuple[str, str]]:
    return {
        paragraph.source_index: (paragraph.role, paragraph.structural_role)
        for paragraph in paragraphs
    }


def _build_structure_divergence_metrics(*, baseline: dict[int, tuple[str, str]], paragraphs: list) -> dict[str, int]:
    metrics = {
        "ai_role_changes": 0,
        "ai_heading_promotions": 0,
        "ai_heading_demotions": 0,
        "ai_structural_role_changes": 0,
    }
    for paragraph in paragraphs:
        if paragraph.role_confidence != "ai":
            continue
        previous = baseline.get(paragraph.source_index)
        if previous is None:
            continue
        previous_role, previous_structural_role = previous
        if previous_role != paragraph.role:
            metrics["ai_role_changes"] += 1
        if previous_role != "heading" and paragraph.role == "heading":
            metrics["ai_heading_promotions"] += 1
        elif previous_role == "heading" and paragraph.role != "heading":
            metrics["ai_heading_demotions"] += 1
        if previous_structural_role != paragraph.structural_role:
            metrics["ai_structural_role_changes"] += 1
    return metrics


def _run_structure_recognition(*, paragraphs: list, image_assets: list, app_config: dict[str, object], progress_callback, normalization_report, relation_report) -> tuple[StructureMap | None, int, int, dict[str, int]]:
    if not bool(app_config.get("structure_recognition_enabled", False)):
        return None, 0, 0, {}

    base_metrics = {
        "paragraph_count": len(paragraphs),
        "image_count": len(image_assets),
        **_build_normalization_metrics(normalization_report, relation_report),
    }
    emit_preparation_progress(
        progress_callback,
        stage="Распознавание структуры…",
        detail="Анализирую роли абзацев с помощью AI.",
        progress=0.35,
        metrics=base_metrics,
    )

    try:
        baseline = _capture_structure_baseline(paragraphs)
        structure_map = build_structure_map(
            paragraphs,
            client=get_client(),
            model=str(app_config.get("structure_recognition_model", "gpt-4o-mini")),
            max_window_paragraphs=int(app_config.get("structure_recognition_max_window_paragraphs", 1800) or 1800),
            overlap_paragraphs=int(app_config.get("structure_recognition_overlap_paragraphs", 50) or 50),
            timeout=float(app_config.get("structure_recognition_timeout_seconds", 60) or 60),
        )
        applied_metrics = apply_structure_map(
            paragraphs,
            structure_map,
            min_confidence=str(app_config.get("structure_recognition_min_confidence", "medium")),
        )
        divergence_metrics = _build_structure_divergence_metrics(baseline=baseline, paragraphs=paragraphs)
    except Exception as exc:
        log_event(
            logging.WARNING,
            "structure_recognition_fallback",
            "AI-распознавание структуры завершилось fallback-путём.",
            error_message=str(exc),
        )
        emit_preparation_progress(
            progress_callback,
            stage="Структура: эвристика",
            detail="AI-распознавание недоступно. Используются текущие правила.",
            progress=0.55,
            metrics=base_metrics,
        )
        return None, 0, 0, {}

    ai_classified_count = int(applied_metrics.get("ai_classified", 0) or 0)
    ai_heading_count = int(applied_metrics.get("ai_headings", 0) or 0)
    if ai_classified_count > 0:
        detail = f"Классифицировано {ai_classified_count} абзацев, найдено {ai_heading_count} заголовков."
        stage = "Структура распознана"
    else:
        detail = "AI не внёс изменений. Используются текущие правила."
        stage = "Структура: эвристика"
    emit_preparation_progress(
        progress_callback,
        stage=stage,
        detail=detail,
        progress=0.55,
        metrics={
            **base_metrics,
            **_build_structure_metrics(
                structure_map=structure_map,
                ai_classified_count=ai_classified_count,
                ai_heading_count=ai_heading_count,
                ai_role_change_count=int(divergence_metrics.get("ai_role_changes", 0) or 0),
                ai_heading_promotion_count=int(divergence_metrics.get("ai_heading_promotions", 0) or 0),
                ai_heading_demotion_count=int(divergence_metrics.get("ai_heading_demotions", 0) or 0),
                ai_structural_role_change_count=int(divergence_metrics.get("ai_structural_role_changes", 0) or 0),
            ),
        },
    )
    return structure_map, ai_classified_count, ai_heading_count, divergence_metrics


PREPARATION_CACHE_LIMIT = 2
_shared_preparation_cache: OrderedDict[str, PreparedDocumentData] = OrderedDict()
_shared_preparation_cache_lock = Lock()
_shared_preparation_inflight: dict[str, Event] = {}


def emit_preparation_progress(progress_callback, *, stage: str, detail: str, progress: float, metrics: dict[str, object] | None = None) -> None:
    if progress_callback is None:
        return
    progress_callback(stage=stage, detail=detail, progress=progress, metrics=metrics or {})


def build_prepared_source_key(
    uploaded_file_token: str,
    chunk_size: int,
    *,
    paragraph_boundary_normalization_mode: str = "high_only",
    paragraph_boundary_ai_review_mode: str = "off",
    relation_normalization_key: str = "phase2_default:epigraph_attribution,image_caption,table_caption,toc_region",
    structure_recognition_enabled: bool = False,
) -> str:
    structure_recognition_suffix = ":sr=1" if structure_recognition_enabled else ""
    return (
        f"{uploaded_file_token}:{chunk_size}:{paragraph_boundary_normalization_mode}:"
        f"{paragraph_boundary_ai_review_mode}:{relation_normalization_key}{structure_recognition_suffix}"
    )


def _prepare_document_for_processing(
    source_name: str,
    source_bytes: bytes,
    chunk_size: int,
    *,
    app_config: dict[str, object],
    progress_callback=None,
):
    emit_preparation_progress(
        progress_callback,
        stage="Разбор DOCX",
        detail="Извлекаю абзацы и встроенные изображения.",
        progress=0.2,
    )
    uploaded_file = build_in_memory_uploaded_file(source_name=source_name, source_bytes=source_bytes)
    paragraphs, image_assets, normalization_report, relations, relation_report = extract_document_content_with_normalization_reports(uploaded_file)
    emit_preparation_progress(
        progress_callback,
        stage="Структура извлечена",
        detail="Документ прочитан, собираю текст для анализа.",
        progress=0.3,
        metrics={
            "paragraph_count": len(paragraphs),
            "image_count": len(image_assets),
            **_build_normalization_metrics(normalization_report, relation_report),
        },
    )
    structure_map, ai_classified_count, ai_heading_count, divergence_metrics = _run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=image_assets,
        app_config=app_config,
        progress_callback=progress_callback,
        normalization_report=normalization_report,
        relation_report=relation_report,
    )
    source_text = build_document_text(paragraphs)
    emit_preparation_progress(
        progress_callback,
        stage="Текст собран",
        detail="Формирую цельный текст документа и считаю объём.",
        progress=0.6,
        metrics={
            "paragraph_count": len(paragraphs),
            "image_count": len(image_assets),
            "source_chars": len(source_text),
            **_build_normalization_metrics(normalization_report, relation_report),
            **_build_structure_metrics(
                structure_map=structure_map,
                ai_classified_count=ai_classified_count,
                ai_heading_count=ai_heading_count,
                ai_role_change_count=int(divergence_metrics.get("ai_role_changes", 0) or 0),
                ai_heading_promotion_count=int(divergence_metrics.get("ai_heading_promotions", 0) or 0),
                ai_heading_demotion_count=int(divergence_metrics.get("ai_heading_demotions", 0) or 0),
                ai_structural_role_change_count=int(divergence_metrics.get("ai_structural_role_changes", 0) or 0),
            ),
        },
    )
    blocks = build_semantic_blocks(paragraphs, max_chars=chunk_size, relations=relations)
    emit_preparation_progress(
        progress_callback,
        stage="Смысловые блоки",
        detail="Группирую абзацы в блоки для модели.",
        progress=0.75,
        metrics={
            "paragraph_count": len(paragraphs),
            "image_count": len(image_assets),
            "source_chars": len(source_text),
            "block_count": len(blocks),
            **_build_normalization_metrics(normalization_report, relation_report),
            **_build_structure_metrics(
                structure_map=structure_map,
                ai_classified_count=ai_classified_count,
                ai_heading_count=ai_heading_count,
                ai_role_change_count=int(divergence_metrics.get("ai_role_changes", 0) or 0),
                ai_heading_promotion_count=int(divergence_metrics.get("ai_heading_promotions", 0) or 0),
                ai_heading_demotion_count=int(divergence_metrics.get("ai_heading_demotions", 0) or 0),
                ai_structural_role_change_count=int(divergence_metrics.get("ai_structural_role_changes", 0) or 0),
            ),
        },
    )
    jobs = build_editing_jobs(blocks, max_chars=chunk_size)
    emit_preparation_progress(
        progress_callback,
        stage="Задания собраны",
        detail="Готовлю финальный набор задач для обработки.",
        progress=0.9,
        metrics={
            "paragraph_count": len(paragraphs),
            "image_count": len(image_assets),
            "source_chars": len(source_text),
            "block_count": len(jobs),
            **_build_normalization_metrics(normalization_report, relation_report),
            **_build_structure_metrics(
                structure_map=structure_map,
                ai_classified_count=ai_classified_count,
                ai_heading_count=ai_heading_count,
                ai_role_change_count=int(divergence_metrics.get("ai_role_changes", 0) or 0),
                ai_heading_promotion_count=int(divergence_metrics.get("ai_heading_promotions", 0) or 0),
                ai_heading_demotion_count=int(divergence_metrics.get("ai_heading_demotions", 0) or 0),
                ai_structural_role_change_count=int(divergence_metrics.get("ai_structural_role_changes", 0) or 0),
            ),
        },
    )
    return PreparedDocumentData(
        source_text=source_text,
        paragraphs=paragraphs,
        image_assets=image_assets,
        relations=relations,
        jobs=jobs,
        prepared_source_key="",
        normalization_report=normalization_report,
        relation_report=relation_report,
        structure_map=structure_map,
        ai_classified_count=ai_classified_count,
        ai_heading_count=ai_heading_count,
        ai_role_change_count=int(divergence_metrics.get("ai_role_changes", 0) or 0),
        ai_heading_promotion_count=int(divergence_metrics.get("ai_heading_promotions", 0) or 0),
        ai_heading_demotion_count=int(divergence_metrics.get("ai_heading_demotions", 0) or 0),
        ai_structural_role_change_count=int(divergence_metrics.get("ai_structural_role_changes", 0) or 0),
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
        image_assets=[clone_prepared_image_asset(asset) for asset in data.image_assets],
        relations=deepcopy(data.relations),
        jobs=[dict(job) for job in data.jobs],
        prepared_source_key=prepared_source_key,
        normalization_report=deepcopy(data.normalization_report),
        relation_report=deepcopy(data.relation_report),
        structure_map=deepcopy(data.structure_map),
        ai_classified_count=data.ai_classified_count,
        ai_heading_count=data.ai_heading_count,
        ai_role_change_count=data.ai_role_change_count,
        ai_heading_promotion_count=data.ai_heading_promotion_count,
        ai_heading_demotion_count=data.ai_heading_demotion_count,
        ai_structural_role_change_count=data.ai_structural_role_change_count,
        cached=cached,
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


def prepare_document_for_processing(
    *,
    uploaded_payload: FrozenUploadPayload,
    chunk_size: int,
    app_config: dict[str, object] | None = None,
    session_state=None,
    progress_callback=None,
) -> PreparedDocumentData:
    app_config = load_app_config() if app_config is None else app_config
    normalization_mode = (
        str(app_config["paragraph_boundary_normalization_mode"])
        if bool(app_config["paragraph_boundary_normalization_enabled"])
        else "off"
    )
    ai_review_mode = (
        str(app_config.get("paragraph_boundary_ai_review_mode", "off"))
        if bool(app_config.get("paragraph_boundary_ai_review_enabled", False))
        else "off"
    )
    relation_normalization_key = "off"
    if bool(app_config.get("relation_normalization_enabled", True)):
        relation_profile = str(app_config.get("relation_normalization_profile", "phase2_default"))
        configured_relation_kinds = app_config.get("relation_normalization_enabled_relation_kinds", ())
        if not isinstance(configured_relation_kinds, (list, tuple, set)):
            configured_relation_kinds = ()
        enabled_relation_kinds = ",".join(
            sorted(str(kind) for kind in configured_relation_kinds)
        )
        relation_normalization_key = f"{relation_profile}:{enabled_relation_kinds}"
    prepared_source_key = build_prepared_source_key(
        uploaded_payload.file_token,
        chunk_size,
        paragraph_boundary_normalization_mode=normalization_mode,
        paragraph_boundary_ai_review_mode=ai_review_mode,
        relation_normalization_key=relation_normalization_key,
        structure_recognition_enabled=bool(app_config.get("structure_recognition_enabled", False)),
    )
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
                **_build_normalization_metrics(cached.normalization_report, cached.relation_report),
                **_build_structure_metrics(
                    structure_map=cached.structure_map,
                    ai_classified_count=cached.ai_classified_count,
                    ai_heading_count=cached.ai_heading_count,
                    ai_role_change_count=cached.ai_role_change_count,
                    ai_heading_promotion_count=cached.ai_heading_promotion_count,
                    ai_heading_demotion_count=cached.ai_heading_demotion_count,
                    ai_structural_role_change_count=cached.ai_structural_role_change_count,
                ),
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
            uploaded_payload.filename,
            uploaded_payload.content_bytes,
            chunk_size,
            app_config=app_config,
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
