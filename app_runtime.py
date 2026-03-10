from processing_runtime import (
    BackgroundRuntime,
    drain_processing_events as drain_processing_events_impl,
    emit_or_apply_activity as emit_or_apply_activity_impl,
    emit_or_apply_finalize as emit_or_apply_finalize_impl,
    emit_or_apply_image_log as emit_or_apply_image_log_impl,
    emit_or_apply_image_reset as emit_or_apply_image_reset_impl,
    emit_or_apply_log as emit_or_apply_log_impl,
    emit_or_apply_state as emit_or_apply_state_impl,
    emit_or_apply_status as emit_or_apply_status_impl,
    processing_worker_is_active as processing_worker_is_active_impl,
    request_processing_stop as request_processing_stop_impl,
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


def emit_state(runtime: BackgroundRuntime | None, **values) -> None:
    emit_or_apply_state_impl(runtime, **values)


def emit_image_reset(runtime: BackgroundRuntime | None) -> None:
    emit_or_apply_image_reset_impl(runtime)


def emit_status(runtime: BackgroundRuntime | None, **payload) -> None:
    emit_or_apply_status_impl(runtime, set_processing_status=set_processing_status, **payload)


def emit_finalize(runtime: BackgroundRuntime | None, stage: str, detail: str, progress: float) -> None:
    emit_or_apply_finalize_impl(
        runtime,
        finalize_processing_status=finalize_processing_status,
        stage=stage,
        detail=detail,
        progress=progress,
    )


def emit_activity(runtime: BackgroundRuntime | None, message: str) -> None:
    emit_or_apply_activity_impl(runtime, push_activity=push_activity, message=message)


def emit_log(runtime: BackgroundRuntime | None, **payload) -> None:
    emit_or_apply_log_impl(runtime, append_log=append_log, **payload)


def emit_image_log(runtime: BackgroundRuntime | None, **payload) -> None:
    emit_or_apply_image_log_impl(runtime, append_image_log=append_image_log, **payload)


def drain_processing_events() -> None:
    drain_processing_events_impl(
        set_processing_status=set_processing_status,
        finalize_processing_status=finalize_processing_status,
        push_activity=push_activity,
        append_log=append_log,
        append_image_log=append_image_log,
    )


def processing_worker_is_active() -> bool:
    return processing_worker_is_active_impl()


def request_processing_stop() -> None:
    request_processing_stop_impl()


def start_background_processing(*, worker_target, uploaded_filename: str, uploaded_token: str, jobs, image_assets, image_mode: str, app_config: dict[str, object], model: str, max_retries: int) -> None:
    start_background_processing_impl(
        worker_target=worker_target,
        reset_run_state=reset_run_state,
        push_activity=push_activity,
        set_processing_status=set_processing_status,
        uploaded_filename=uploaded_filename,
        uploaded_token=uploaded_token,
        jobs=jobs,
        image_assets=image_assets,
        image_mode=image_mode,
        app_config=app_config,
        model=model,
        max_retries=max_retries,
    )