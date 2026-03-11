import logging
from dataclasses import dataclass

from preparation import prepare_document_for_processing
from processing_runtime import (
    build_in_memory_uploaded_file,
    build_uploaded_file_token,
    read_uploaded_file_bytes,
    resolve_uploaded_filename,
)
from restart_store import load_restart_source_bytes
from workflow_state import derive_idle_view_state, has_restartable_outcome


@dataclass
class PreparedRunContext:
    uploaded_filename: str
    uploaded_file_bytes: bytes
    uploaded_file_token: str
    source_text: str
    paragraphs: list
    image_assets: list
    jobs: list[dict[str, str | int]]
    prepared_source_key: str


def sync_selected_file_context(*, session_state, reset_run_state_fn, uploaded_file_token: str) -> None:
    previous_token = session_state.get("selected_source_token", "")
    if not previous_token or previous_token == uploaded_file_token:
        session_state.selected_source_token = uploaded_file_token
        return

    reset_run_state_fn(keep_restart_source=False)
    session_state.selected_source_token = uploaded_file_token


def get_cached_restart_file(
    *,
    session_state,
    load_restart_source_bytes_fn=None,
    build_in_memory_uploaded_file_fn=None,
):
    if load_restart_source_bytes_fn is None:
        load_restart_source_bytes_fn = load_restart_source_bytes
    if build_in_memory_uploaded_file_fn is None:
        build_in_memory_uploaded_file_fn = build_in_memory_uploaded_file
    restart_source = session_state.get("restart_source")
    if not restart_source:
        return None
    source_name = str(restart_source.get("filename", ""))
    source_bytes = load_restart_source_bytes_fn(restart_source)
    if not source_name or source_bytes is None:
        return None
    return build_in_memory_uploaded_file_fn(source_name=source_name, source_bytes=source_bytes)


def get_cached_completed_file(
    *,
    session_state,
    build_in_memory_uploaded_file_fn=None,
):
    if build_in_memory_uploaded_file_fn is None:
        build_in_memory_uploaded_file_fn = build_in_memory_uploaded_file
    completed_source = session_state.get("completed_source")
    if not completed_source:
        return None
    source_name = str(completed_source.get("filename", ""))
    source_bytes = completed_source.get("source_bytes")
    if not source_name or not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
        return None
    return build_in_memory_uploaded_file_fn(source_name=source_name, source_bytes=bytes(source_bytes))


def should_log_document_prepared(*, session_state, prepared_source_key: str) -> bool:
    return session_state.get("prepared_source_key", "") != prepared_source_key


def has_restartable_source(
    *,
    session_state,
) -> bool:
    restart_source = session_state.get("restart_source")
    if not restart_source:
        return False
    if not has_restartable_outcome(session_state.get("processing_outcome")):
        return False
    return bool(str(restart_source.get("filename", "")) and str(restart_source.get("storage_path", "")))


def has_resettable_state(
    *,
    current_result,
    session_state,
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
) -> str:
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
    enable_post_redraw_validation: bool,
    session_state,
    reset_run_state_fn,
    fail_critical_fn,
    log_event_fn,
    prepare_document_for_processing_fn=None,
    resolve_uploaded_filename_fn=None,
    read_uploaded_file_bytes_fn=None,
    build_uploaded_file_token_fn=None,
) -> PreparedRunContext:
    if prepare_document_for_processing_fn is None:
        prepare_document_for_processing_fn = prepare_document_for_processing
    if resolve_uploaded_filename_fn is None:
        resolve_uploaded_filename_fn = resolve_uploaded_filename
    if read_uploaded_file_bytes_fn is None:
        read_uploaded_file_bytes_fn = read_uploaded_file_bytes
    if build_uploaded_file_token_fn is None:
        build_uploaded_file_token_fn = build_uploaded_file_token
    uploaded_filename = resolve_uploaded_filename_fn(uploaded_file)
    uploaded_file_bytes = read_uploaded_file_bytes_fn(uploaded_file)
    uploaded_file_token = build_uploaded_file_token_fn(source_name=uploaded_filename, source_bytes=uploaded_file_bytes)
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
    )
    if not prepared_document.jobs:
        fail_critical_fn("no_jobs_built", "Не удалось собрать ни одного блока для обработки.", filename=uploaded_filename)
    if any(not str(job["target_text"]).strip() for job in prepared_document.jobs):
        fail_critical_fn("empty_target_block", "Обнаружен пустой целевой блок перед отправкой в модель.", filename=uploaded_filename)
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
            enable_post_redraw_validation=enable_post_redraw_validation,
        )
        session_state.prepared_source_key = prepared_document.prepared_source_key

    return PreparedRunContext(
        uploaded_filename=uploaded_filename,
        uploaded_file_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        source_text=prepared_document.source_text,
        paragraphs=prepared_document.paragraphs,
        image_assets=prepared_document.image_assets,
        jobs=prepared_document.jobs,
        prepared_source_key=prepared_document.prepared_source_key,
    )