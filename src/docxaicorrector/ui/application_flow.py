"""UI-facing application flow: session/state helpers plus the interactive
``prepare_run_context`` entrypoint.

The domain preparation contract (``PreparedRunContext``) and the ui-free
orchestration now live in ``docxaicorrector.processing.application_flow``; they
are re-exported here so existing ``docxaicorrector.ui.application_flow.X``
references keep working. This module localizes user-facing messages by passing
``ui.i18n.t`` into the shared orchestration (spec 027 broke the processing→ui
cycle by moving the contract down).
"""

import logging
import hashlib
import re
from pathlib import Path
from typing import Any, Protocol

from docxaicorrector.processing.application_flow import (
    NormalizationMetrics,
    PreparedRunContext,
    ResolvedPreparationUpload,
    _build_prepared_run_context,
    _prepare_run_context_core,
    _raise_or_fail_preparation,
    flatten_layout_cleanup_metrics,
    flatten_normalization_metrics,
    flatten_relation_metrics,
    prepare_run_context_for_background,
    sync_selected_file_context,
)
from docxaicorrector.processing.preparation import emit_preparation_progress
from docxaicorrector.processing.processing_runtime import FrozenUploadPayload, build_in_memory_uploaded_file
from docxaicorrector.processing.restart_store import clear_restart_source, load_restart_source_bytes
from docxaicorrector.runtime.state import (
    clear_completed_source,
    get_completed_source,
    get_prepared_source_key,
    get_processing_outcome,
    get_restart_source,
    set_prepared_source_key,
)
from docxaicorrector.runtime.workflow_state import IdleViewState, derive_idle_view_state, has_restartable_outcome
from docxaicorrector.ui.i18n import t

__all__ = [
    "NormalizationMetrics",
    "PreparedRunContext",
    "ResolvedPreparationUpload",
    "SessionStateLike",
    "flatten_normalization_metrics",
    "flatten_relation_metrics",
    "flatten_layout_cleanup_metrics",
    "sync_selected_file_context",
    "get_cached_restart_file",
    "get_cached_completed_file",
    "should_log_document_prepared",
    "consume_completed_source_if_used",
    "has_restartable_source",
    "has_resettable_state",
    "resolve_effective_uploaded_file",
    "derive_app_idle_view_state",
    "prepare_run_context",
    "prepare_run_context_for_background",
]


class SessionStateLike(Protocol):
    def get(self, key: str, default: object | None = None) -> Any: ...

    def __getitem__(self, key: str): ...

    def __setitem__(self, key: str, value: object) -> None: ...


def _restore_frozen_upload_payload(source_record: dict[str, object], source_bytes: bytes) -> FrozenUploadPayload | None:
    source_name = str(source_record.get("filename", ""))
    source_token = str(source_record.get("token", ""))
    source_format = str(source_record.get("source_format", "")).strip().lower()
    conversion_backend = source_record.get("conversion_backend")
    expected_size = source_record.get("size")
    expected_digest = source_record.get("payload_sha256")
    actual_digest = hashlib.sha256(source_bytes).hexdigest()
    if (
        not source_name
        or not source_token
        or source_format not in {"docx", "doc", "pdf"}
        or not isinstance(expected_size, int)
        or expected_size != len(source_bytes)
        or not isinstance(expected_digest, str)
        or expected_digest != actual_digest
        or (source_format != "docx" and not isinstance(conversion_backend, str))
    ):
        return None
    return FrozenUploadPayload(
        filename=source_name,
        content_bytes=source_bytes,
        file_size=len(source_bytes),
        content_hash=actual_digest[:16],
        file_token=source_token,
        source_format=source_format,
        conversion_backend=conversion_backend if isinstance(conversion_backend, str) else None,
    )


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
    restart_source = get_restart_source(session_state=session_state)
    if not isinstance(restart_source, dict):
        return None
    if not restart_source:
        return None
    source_bytes = load_restart_source_bytes_fn(restart_source)
    if not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
        return None
    return _restore_frozen_upload_payload(restart_source, bytes(source_bytes))


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
    completed_source = get_completed_source(session_state=session_state)
    if not isinstance(completed_source, dict):
        return None
    if not completed_source:
        return None
    source_bytes = load_completed_source_bytes_fn(completed_source)
    if not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
        return None
    return _restore_frozen_upload_payload(completed_source, bytes(source_bytes))


def should_log_document_prepared(*, session_state, prepared_source_key: str) -> bool:
    return get_prepared_source_key(session_state=session_state) != prepared_source_key


def consume_completed_source_if_used(*, session_state, uploaded_file_token: str) -> None:
    completed_source = get_completed_source(session_state=session_state)
    if not completed_source:
        return
    if str(completed_source.get("token", "")) != uploaded_file_token:
        return
    clear_completed_source(
        completed_source=completed_source,
        clear_restart_source_fn=clear_restart_source,
        session_state=session_state,
    )


def has_restartable_source(
    *,
    session_state: SessionStateLike,
) -> bool:
    restart_source = get_restart_source(session_state=session_state)
    if not isinstance(restart_source, dict) or not restart_source:
        return False
    if not has_restartable_outcome(get_processing_outcome(session_state=session_state)):
        return False
    source_name = str(restart_source.get("filename", ""))
    storage_path = str(restart_source.get("storage_path", ""))
    if not source_name or not storage_path:
        return False
    # spec-045: a record without the integrity/format metadata can NEVER be
    # restored by load_restart_source_bytes (it is rejected as invalid_metadata),
    # so offering it in the RESTARTABLE view is a permanent dead end. Checked
    # structurally, without materializing the payload, to keep this predicate cheap.
    payload_sha256 = restart_source.get("payload_sha256")
    source_format = str(restart_source.get("source_format", "")).strip().lower()
    if not isinstance(payload_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", payload_sha256):
        return False
    if source_format not in {"docx", "doc", "pdf"}:
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
    # Completed-source caching runs only for SUCCEEDED, so any run that ended stopped or
    # failed — a delivery-blocked result, or a stop observed after the result was already
    # published — keeps its restart source instead. ``has_restartable_source`` already
    # encodes exactly that eligibility (restartable outcome + a verifiable record), so it
    # is the whole condition: without this fall-through those runs render as COMPLETED
    # with no reprocess control while valid source bytes sit on disk.
    if has_restartable_source(session_state=session_state):
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
    processing_operation: str = "edit",
    app_config: dict[str, object] | None = None,
    session_state,
    reset_run_state_fn,
    fail_critical_fn,
    log_event_fn,
    prepare_document_for_processing_fn=None,
    resolve_uploaded_filename_fn=None,
    progress_callback=None,
    client_factory=None,
) -> PreparedRunContext:
    uploaded_filename, uploaded_file_bytes, uploaded_file_token, prepared_document, elapsed_seconds = _prepare_run_context_core(
        uploaded_file=uploaded_file,
        chunk_size=chunk_size,
        processing_operation=processing_operation,
        app_config=app_config,
        session_state=session_state,
        progress_callback=progress_callback,
        prepare_document_for_processing_fn=prepare_document_for_processing_fn,
        resolve_uploaded_filename_fn=resolve_uploaded_filename_fn,
        reset_run_state_fn=reset_run_state_fn,
        fail_critical_fn=fail_critical_fn,
        client_factory=client_factory,
    )
    consume_completed_source_if_used(session_state=session_state, uploaded_file_token=uploaded_file_token)
    _raise_or_fail_preparation(prepared_document=prepared_document, uploaded_filename=uploaded_filename, fail_critical_fn=fail_critical_fn, translate_fn=t)
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
            **flatten_normalization_metrics(getattr(prepared_document, "normalization_report", None)),
            **flatten_relation_metrics(getattr(prepared_document, "relation_report", None)),
            **flatten_layout_cleanup_metrics(getattr(prepared_document, "cleanup_report", None)),
        )
        set_prepared_source_key(prepared_document.prepared_source_key, session_state=session_state)
    emit_preparation_progress(
        progress_callback,
        stage="Документ подготовлен",
        detail="",
        progress=1.0,
        metrics={
            "file_size_bytes": len(uploaded_file_bytes),
            "paragraph_count": len(prepared_document.paragraphs),
            "image_count": len(prepared_document.image_assets),
            "source_chars": len(prepared_document.source_text),
            "block_count": len(prepared_document.jobs),
            "cached": prepared_document.cached,
            **flatten_normalization_metrics(getattr(prepared_document, "normalization_report", None)),
            **flatten_relation_metrics(getattr(prepared_document, "relation_report", None)),
            **flatten_layout_cleanup_metrics(getattr(prepared_document, "cleanup_report", None)),
        },
    )
    return _build_prepared_run_context(
        uploaded_filename=uploaded_filename,
        uploaded_file_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        prepared_document=prepared_document,
        elapsed_seconds=elapsed_seconds,
        translate_fn=t,
    )
