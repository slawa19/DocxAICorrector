"""Thin Streamlit-facing adapter over processing runtime primitives."""

from processing_runtime import (
    BackgroundRuntime,
    build_preparation_request_marker,
    drain_preparation_events as drain_preparation_events_impl,
    drain_processing_events as drain_processing_events_impl,
    emit_or_apply_activity as emit_or_apply_activity_impl,
    emit_or_apply_finalize as emit_or_apply_finalize_impl,
    emit_or_apply_image_log as emit_or_apply_image_log_impl,
    emit_or_apply_image_reset as emit_or_apply_image_reset_impl,
    emit_or_apply_log as emit_or_apply_log_impl,
    emit_or_apply_state as emit_or_apply_state_impl,
    emit_or_apply_status as emit_or_apply_status_impl,
    preparation_worker_is_active as preparation_worker_is_active_impl,
    processing_worker_is_active as processing_worker_is_active_impl,
    request_processing_stop as request_processing_stop_impl,
    start_background_preparation as start_background_preparation_impl,
    start_background_processing as start_background_processing_impl,
)
from state import (
    append_image_log,
    append_log,
    finalize_processing_status,
    push_activity,
    reset_run_state,
    set_processing_status,
)

__all__ = [
    "BackgroundRuntime",
    "build_preparation_request_marker",
    "emit_state",
    "emit_image_reset",
    "emit_status",
    "emit_finalize",
    "emit_activity",
    "emit_log",
    "emit_image_log",
    "drain_processing_events",
    "drain_preparation_events",
    "preparation_worker_is_active",
    "processing_worker_is_active",
    "request_processing_stop",
    "start_background_preparation",
    "start_background_processing",
]


def emit_state(runtime: BackgroundRuntime | None, **values) -> None:
    """Forward raw state updates through the stable UI/runtime adapter seam."""
    emit_or_apply_state_impl(runtime, **values)


def emit_image_reset(runtime: BackgroundRuntime | None) -> None:
    """Forward image reset through the stable UI/runtime adapter seam."""
    emit_or_apply_image_reset_impl(runtime)


def emit_status(runtime: BackgroundRuntime | None, **payload) -> None:
    """Bind runtime status updates to the canonical state owner."""
    emit_or_apply_status_impl(runtime, set_processing_status=set_processing_status, **payload)


def emit_finalize(runtime: BackgroundRuntime | None, stage: str, detail: str, progress: float, terminal_kind: str | None = None) -> None:
    """Bind final status transitions to the canonical state owner."""
    emit_or_apply_finalize_impl(
        runtime,
        finalize_processing_status=finalize_processing_status,
        stage=stage,
        detail=detail,
        progress=progress,
        terminal_kind=terminal_kind,
    )


def emit_activity(runtime: BackgroundRuntime | None, message: str) -> None:
    """Bind activity events to the canonical state owner."""
    emit_or_apply_activity_impl(runtime, push_activity=push_activity, message=message)


def emit_log(runtime: BackgroundRuntime | None, **payload) -> None:
    """Bind block log events to the canonical state owner."""
    emit_or_apply_log_impl(runtime, append_log=append_log, **payload)


def emit_image_log(runtime: BackgroundRuntime | None, **payload) -> None:
    """Bind image log events to the canonical state owner."""
    emit_or_apply_image_log_impl(runtime, append_image_log=append_image_log, **payload)


def drain_processing_events() -> None:
    """Drain processing runtime events through bound state-owner functions."""
    drain_processing_events_impl(
        set_processing_status=set_processing_status,
        finalize_processing_status=finalize_processing_status,
        push_activity=push_activity,
        append_log=append_log,
        append_image_log=append_image_log,
    )


def drain_preparation_events() -> None:
    """Drain preparation runtime events through bound state-owner functions."""
    drain_preparation_events_impl(
        reset_run_state=reset_run_state,
        set_processing_status=set_processing_status,
        finalize_processing_status=finalize_processing_status,
        push_activity=push_activity,
    )


def preparation_worker_is_active() -> bool:
    """Expose worker liveness without leaking runtime internals into app.py."""
    return preparation_worker_is_active_impl()


def processing_worker_is_active() -> bool:
    """Expose worker liveness without leaking runtime internals into app.py."""
    return processing_worker_is_active_impl()


def request_processing_stop() -> None:
    """Expose stop requests without leaking runtime internals into app.py."""
    request_processing_stop_impl()


def start_background_preparation(*, worker_target, uploaded_payload, upload_marker: str, chunk_size: int, image_mode: str, keep_all_image_variants: bool) -> None:
    """Start preparation with the canonical state owners pre-bound for UI code."""
    start_background_preparation_impl(
        worker_target=worker_target,
        reset_run_state=reset_run_state,
        push_activity=push_activity,
        set_processing_status=set_processing_status,
        uploaded_payload=uploaded_payload,
        upload_marker=upload_marker,
        chunk_size=chunk_size,
        image_mode=image_mode,
        keep_all_image_variants=keep_all_image_variants,
    )


def start_background_processing(*, worker_target, uploaded_filename: str, uploaded_token: str, source_bytes: bytes, jobs, source_paragraphs=None, image_assets=None, image_mode: str, app_config: dict[str, object], model: str, max_retries: int, processing_operation: str = "edit", source_language: str = "en", target_language: str = "ru") -> None:
    """Start processing with the canonical state owners pre-bound for UI code."""
    start_background_processing_impl(
        worker_target=worker_target,
        reset_run_state=reset_run_state,
        push_activity=push_activity,
        set_processing_status=set_processing_status,
        uploaded_filename=uploaded_filename,
        uploaded_token=uploaded_token,
        source_bytes=source_bytes,
        jobs=jobs,
        source_paragraphs=source_paragraphs,
        image_assets=image_assets or [],
        image_mode=image_mode,
        app_config=app_config,
        model=model,
        max_retries=max_retries,
        processing_operation=processing_operation,
        source_language=source_language,
        target_language=target_language,
    )
