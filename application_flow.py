import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from document import validate_docx_source_bytes
from preparation import emit_preparation_progress, prepare_document_for_processing
from processing_runtime import (
    FrozenUploadPayload,
    build_in_memory_uploaded_file,
    build_uploaded_file_token,
    normalize_uploaded_document,
    read_uploaded_file_bytes,
    resolve_uploaded_filename,
)
from restart_store import clear_restart_source, load_restart_source_bytes
from workflow_state import IdleViewState, derive_idle_view_state, has_restartable_outcome


class SessionStateLike(Protocol):
    def get(self, key: str, default: object | None = None) -> Any: ...

    def __getitem__(self, key: str): ...

    def __setitem__(self, key: str, value) -> None: ...


@dataclass
class PreparedRunContext:
    uploaded_filename: str
    uploaded_file_bytes: bytes
    uploaded_file_token: str
    source_text: str
    paragraphs: list
    image_assets: list
    jobs: list[dict[str, object]]
    prepared_source_key: str
    preparation_stage: str
    preparation_detail: str
    preparation_cached: bool
    preparation_elapsed_seconds: float

def sync_selected_file_context(*, session_state, reset_run_state_fn, uploaded_file_token: str) -> None:
    previous_token = session_state.get("selected_source_token", "")
    if not previous_token or previous_token == uploaded_file_token:
        session_state.selected_source_token = uploaded_file_token
        return

    reset_run_state_fn(keep_restart_source=False)
    session_state.selected_source_token = uploaded_file_token


def get_cached_restart_file(
    *,
    session_state: SessionStateLike,
    load_restart_source_bytes_fn=None,
    build_in_memory_uploaded_file_fn=None,
):
    if load_restart_source_bytes_fn is None:
        load_restart_source_bytes_fn = load_restart_source_bytes
    if build_in_memory_uploaded_file_fn is None:
        build_in_memory_uploaded_file_fn = build_in_memory_uploaded_file
    restart_source = session_state.get("restart_source")
    if not isinstance(restart_source, dict):
        return None
    if not restart_source:
        return None
    source_name = str(restart_source.get("filename", ""))
    source_bytes = load_restart_source_bytes_fn(restart_source)
    if not source_name or not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
        return None
    return build_in_memory_uploaded_file_fn(source_name=source_name, source_bytes=bytes(source_bytes))


def get_cached_completed_file(
    *,
    session_state: SessionStateLike,
    build_in_memory_uploaded_file_fn=None,
    load_completed_source_bytes_fn=None,
):
    if build_in_memory_uploaded_file_fn is None:
        build_in_memory_uploaded_file_fn = build_in_memory_uploaded_file
    if load_completed_source_bytes_fn is None:
        load_completed_source_bytes_fn = load_restart_source_bytes
    completed_source = session_state.get("completed_source")
    if not isinstance(completed_source, dict):
        return None
    if not completed_source:
        return None
    source_name = str(completed_source.get("filename", ""))
    source_bytes = load_completed_source_bytes_fn(completed_source)
    if not source_name or not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
        return None
    return build_in_memory_uploaded_file_fn(source_name=source_name, source_bytes=bytes(source_bytes))


def should_log_document_prepared(*, session_state, prepared_source_key: str) -> bool:
    return session_state.get("prepared_source_key", "") != prepared_source_key


def consume_completed_source_if_used(*, session_state, uploaded_file_token: str) -> None:
    completed_source = session_state.get("completed_source")
    if not completed_source:
        return
    if str(completed_source.get("token", "")) != uploaded_file_token:
        return
    clear_restart_source(completed_source)
    session_state.completed_source = None


def _resolve_preparation_dependencies(
    *,
    prepare_document_for_processing_fn,
    resolve_uploaded_filename_fn,
    read_uploaded_file_bytes_fn,
    build_uploaded_file_token_fn,
):
    return (
        prepare_document_for_processing if prepare_document_for_processing_fn is None else prepare_document_for_processing_fn,
        resolve_uploaded_filename if resolve_uploaded_filename_fn is None else resolve_uploaded_filename_fn,
        read_uploaded_file_bytes if read_uploaded_file_bytes_fn is None else read_uploaded_file_bytes_fn,
        build_uploaded_file_token if build_uploaded_file_token_fn is None else build_uploaded_file_token_fn,
    )


def _prepare_run_context_core(
    *,
    uploaded_file=None,
    uploaded_payload: FrozenUploadPayload | None = None,
    chunk_size: int,
    session_state,
    progress_callback,
    prepare_document_for_processing_fn,
    resolve_uploaded_filename_fn,
    read_uploaded_file_bytes_fn,
    build_uploaded_file_token_fn,
    reset_run_state_fn=None,
):
    started_at = time.perf_counter()
    (
        prepare_document_for_processing_fn,
        resolve_uploaded_filename_fn,
        read_uploaded_file_bytes_fn,
        build_uploaded_file_token_fn,
    ) = _resolve_preparation_dependencies(
        prepare_document_for_processing_fn=prepare_document_for_processing_fn,
        resolve_uploaded_filename_fn=resolve_uploaded_filename_fn,
        read_uploaded_file_bytes_fn=read_uploaded_file_bytes_fn,
        build_uploaded_file_token_fn=build_uploaded_file_token_fn,
    )
    if uploaded_payload is not None:
        uploaded_filename = uploaded_payload.filename
        uploaded_file_bytes = uploaded_payload.content_bytes
        uploaded_file_token = uploaded_payload.file_token
    else:
        uploaded_filename = resolve_uploaded_filename_fn(uploaded_file)
        emit_preparation_progress(
            progress_callback,
            stage="Чтение файла",
            detail=f"Читаю содержимое {uploaded_filename}",
            progress=0.05,
        )
        uploaded_file_bytes = read_uploaded_file_bytes_fn(uploaded_file)
        uploaded_file_token = build_uploaded_file_token_fn(source_name=uploaded_filename, source_bytes=uploaded_file_bytes)
    normalized_document = normalize_uploaded_document(filename=uploaded_filename, source_bytes=uploaded_file_bytes)
    uploaded_filename = normalized_document.filename
    uploaded_file_bytes = normalized_document.content_bytes
    uploaded_file_token = build_uploaded_file_token_fn(source_name=uploaded_filename, source_bytes=uploaded_file_bytes)
    emit_preparation_progress(
        progress_callback,
        stage="Файл прочитан",
        detail="Формирую идентификатор источника и подготавливаю анализ.",
        progress=0.15,
        metrics={"file_size_bytes": len(uploaded_file_bytes)},
    )
    validate_docx_source_bytes(uploaded_file_bytes)
    if session_state is not None and reset_run_state_fn is not None:
        sync_selected_file_context(
            session_state=session_state,
            reset_run_state_fn=reset_run_state_fn,
            uploaded_file_token=uploaded_file_token,
        )
    prepared_document = prepare_document_for_processing_fn(
        uploaded_filename=uploaded_filename,
        source_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        chunk_size=chunk_size,
        session_state=session_state,
        progress_callback=progress_callback,
    )
    elapsed_seconds = max(0.0, time.perf_counter() - started_at)
    return uploaded_filename, uploaded_file_bytes, uploaded_file_token, prepared_document, elapsed_seconds


def _raise_or_fail_preparation(*, prepared_document, uploaded_filename: str, fail_critical_fn=None) -> None:
    if not prepared_document.jobs:
        if fail_critical_fn is not None:
            fail_critical_fn("no_jobs_built", "Не удалось собрать ни одного блока для обработки.", filename=uploaded_filename)
        raise ValueError("Не удалось собрать ни одного блока для обработки.")
    if any(not str(job.get("target_text") or "").strip() for job in prepared_document.jobs):
        if fail_critical_fn is not None:
            fail_critical_fn("empty_target_block", "Обнаружен пустой целевой блок перед отправкой в модель.", filename=uploaded_filename)
        raise ValueError("Обнаружен пустой целевой блок перед отправкой в модель.")


def _build_prepared_run_context(*, uploaded_filename: str, uploaded_file_bytes: bytes, uploaded_file_token: str, prepared_document, elapsed_seconds: float) -> PreparedRunContext:
    return PreparedRunContext(
        uploaded_filename=uploaded_filename,
        uploaded_file_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        source_text=prepared_document.source_text,
        paragraphs=prepared_document.paragraphs,
        image_assets=prepared_document.image_assets,
        jobs=prepared_document.jobs,
        prepared_source_key=prepared_document.prepared_source_key,
        preparation_stage="Документ подготовлен",
        preparation_detail="Анализ завершён. Можно запускать обработку.",
        preparation_cached=prepared_document.cached,
        preparation_elapsed_seconds=elapsed_seconds,
    )


def has_restartable_source(
    *,
    session_state: SessionStateLike,
) -> bool:
    restart_source = session_state.get("restart_source")
    if not isinstance(restart_source, dict) or not restart_source:
        return False
    if not has_restartable_outcome(session_state.get("processing_outcome")):
        return False
    source_name = str(restart_source.get("filename", ""))
    storage_path = str(restart_source.get("storage_path", ""))
    if not source_name or not storage_path:
        return False
    return Path(storage_path).is_file()


def has_resettable_state(
    *,
    current_result,
    session_state: SessionStateLike,
) -> bool:
    if current_result:
        return True
    return has_restartable_source(session_state=session_state)


def resolve_effective_uploaded_file(
    *,
    uploaded_file,
    current_result,
    session_state,
    load_restart_source_bytes_fn=None,
    build_in_memory_uploaded_file_fn=None,
):
    if uploaded_file is not None:
        return uploaded_file
    if current_result is not None:
        completed_file = get_cached_completed_file(
            session_state=session_state,
            build_in_memory_uploaded_file_fn=build_in_memory_uploaded_file_fn,
            load_completed_source_bytes_fn=load_restart_source_bytes_fn,
        )
        if completed_file is not None:
            return completed_file
    if current_result is None and has_restartable_source(session_state=session_state):
        return get_cached_restart_file(
            session_state=session_state,
            load_restart_source_bytes_fn=load_restart_source_bytes_fn,
            build_in_memory_uploaded_file_fn=build_in_memory_uploaded_file_fn,
        )
    return None


def derive_app_idle_view_state(
    *,
    current_result,
    uploaded_file,
    session_state,
) -> IdleViewState:
    return derive_idle_view_state(
        current_result=current_result,
        uploaded_file=uploaded_file,
        has_restartable_source=has_restartable_source(session_state=session_state),
    )


def prepare_run_context(
    *,
    uploaded_file,
    chunk_size: int,
    image_mode: str,
    keep_all_image_variants: bool,
    session_state,
    reset_run_state_fn,
    fail_critical_fn,
    log_event_fn,
    prepare_document_for_processing_fn=None,
    resolve_uploaded_filename_fn=None,
    read_uploaded_file_bytes_fn=None,
    build_uploaded_file_token_fn=None,
    progress_callback=None,
) -> PreparedRunContext:
    uploaded_filename, uploaded_file_bytes, uploaded_file_token, prepared_document, elapsed_seconds = _prepare_run_context_core(
        uploaded_file=uploaded_file,
        chunk_size=chunk_size,
        session_state=session_state,
        progress_callback=progress_callback,
        prepare_document_for_processing_fn=prepare_document_for_processing_fn,
        resolve_uploaded_filename_fn=resolve_uploaded_filename_fn,
        read_uploaded_file_bytes_fn=read_uploaded_file_bytes_fn,
        build_uploaded_file_token_fn=build_uploaded_file_token_fn,
        reset_run_state_fn=reset_run_state_fn,
    )
    consume_completed_source_if_used(session_state=session_state, uploaded_file_token=uploaded_file_token)
    _raise_or_fail_preparation(prepared_document=prepared_document, uploaded_filename=uploaded_filename, fail_critical_fn=fail_critical_fn)
    if should_log_document_prepared(session_state=session_state, prepared_source_key=prepared_document.prepared_source_key):
        log_event_fn(
            logging.INFO,
            "document_prepared",
            "Документ подготовлен к обработке",
            filename=uploaded_filename,
            paragraph_count=len(prepared_document.paragraphs),
            block_count=len(prepared_document.jobs),
            image_count=len(prepared_document.image_assets),
            source_chars=len(prepared_document.source_text),
            chunk_size=chunk_size,
            image_mode=image_mode,
            keep_all_image_variants=keep_all_image_variants,
        )
        session_state.prepared_source_key = prepared_document.prepared_source_key
    emit_preparation_progress(
        progress_callback,
        stage="Документ подготовлен",
        detail="Анализ завершён. Можно запускать обработку.",
        progress=1.0,
        metrics={
            "file_size_bytes": len(uploaded_file_bytes),
            "paragraph_count": len(prepared_document.paragraphs),
            "image_count": len(prepared_document.image_assets),
            "source_chars": len(prepared_document.source_text),
            "block_count": len(prepared_document.jobs),
            "cached": prepared_document.cached,
        },
    )
    return _build_prepared_run_context(
        uploaded_filename=uploaded_filename,
        uploaded_file_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        prepared_document=prepared_document,
        elapsed_seconds=elapsed_seconds,
    )


def prepare_run_context_for_background(
    *,
    uploaded_payload: FrozenUploadPayload,
    chunk_size: int,
    image_mode: str,
    keep_all_image_variants: bool,
    prepare_document_for_processing_fn=None,
    resolve_uploaded_filename_fn=None,
    read_uploaded_file_bytes_fn=None,
    build_uploaded_file_token_fn=None,
    progress_callback=None,
) -> PreparedRunContext:
    uploaded_filename, uploaded_file_bytes, uploaded_file_token, prepared_document, elapsed_seconds = _prepare_run_context_core(
        uploaded_payload=uploaded_payload,
        chunk_size=chunk_size,
        session_state=None,
        progress_callback=progress_callback,
        prepare_document_for_processing_fn=prepare_document_for_processing_fn,
        resolve_uploaded_filename_fn=resolve_uploaded_filename_fn,
        read_uploaded_file_bytes_fn=read_uploaded_file_bytes_fn,
        build_uploaded_file_token_fn=build_uploaded_file_token_fn,
    )
    _raise_or_fail_preparation(prepared_document=prepared_document, uploaded_filename=uploaded_filename)
    emit_preparation_progress(
        progress_callback,
        stage="Документ подготовлен",
        detail="Анализ завершён. Можно запускать обработку.",
        progress=1.0,
        metrics={
            "file_size_bytes": len(uploaded_file_bytes),
            "paragraph_count": len(prepared_document.paragraphs),
            "image_count": len(prepared_document.image_assets),
            "source_chars": len(prepared_document.source_text),
            "block_count": len(prepared_document.jobs),
            "cached": prepared_document.cached,
        },
    )
    return _build_prepared_run_context(
        uploaded_filename=uploaded_filename,
        uploaded_file_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        prepared_document=prepared_document,
        elapsed_seconds=elapsed_seconds,
    )
