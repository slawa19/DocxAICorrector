import queue
import threading

import streamlit as st


class BackgroundRuntime:
    def __init__(self, event_queue, stop_event):
        self._event_queue = event_queue
        self._stop_event = stop_event

    def emit(self, event_type: str, **payload) -> None:
        self._event_queue.put({"type": event_type, **payload})

    def should_stop(self) -> bool:
        return self._stop_event.is_set()


def build_uploaded_file_token(uploaded_file) -> str:
    file_name = getattr(uploaded_file, "name", "")
    file_size = getattr(uploaded_file, "size", None)
    if file_size is None:
        raw_value = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else b""
        file_size = len(raw_value)
    return f"{file_name}:{file_size}"


def build_result_bundle(*, source_name: str, source_token: str, docx_bytes: bytes, markdown_text: str) -> dict[str, object]:
    return {
        "source_name": source_name,
        "source_token": source_token,
        "docx_bytes": docx_bytes,
        "markdown_text": markdown_text,
    }


def get_current_result_bundle() -> dict[str, object] | None:
    latest_docx_bytes = st.session_state.get("latest_docx_bytes")
    if not latest_docx_bytes:
        return None
    return build_result_bundle(
        source_name=st.session_state.get("latest_source_name", ""),
        source_token=st.session_state.get("latest_source_token", ""),
        docx_bytes=latest_docx_bytes,
        markdown_text=st.session_state.get("latest_markdown", ""),
    )


def get_previous_result_bundle(selected_source_token: str) -> dict[str, object] | None:
    current_bundle = get_current_result_bundle()
    if current_bundle and current_bundle["source_token"] != selected_source_token:
        return current_bundle
    previous_bundle = st.session_state.get("previous_result")
    if previous_bundle and previous_bundle.get("source_token") != selected_source_token:
        return previous_bundle
    return None


def set_session_values(**values) -> None:
    for key, value in values.items():
        st.session_state[key] = value


def emit_or_apply_state(runtime: BackgroundRuntime | None, **values) -> None:
    if runtime is None:
        set_session_values(**values)
        return
    runtime.emit("set_state", values=values)


def emit_or_apply_image_reset(runtime: BackgroundRuntime | None) -> None:
    if runtime is None:
        st.session_state.image_assets = []
        st.session_state.image_validation_failures = []
        return
    runtime.emit("reset_image_state")


def emit_or_apply_status(runtime: BackgroundRuntime | None, *, set_processing_status, **payload) -> None:
    if runtime is None:
        set_processing_status(**payload)
        return
    runtime.emit("set_processing_status", payload=payload)


def emit_or_apply_finalize(runtime: BackgroundRuntime | None, *, finalize_processing_status, stage: str, detail: str, progress: float) -> None:
    if runtime is None:
        finalize_processing_status(stage, detail, progress)
        return
    runtime.emit("finalize_processing_status", stage=stage, detail=detail, progress=progress)


def emit_or_apply_activity(runtime: BackgroundRuntime | None, *, push_activity, message: str) -> None:
    if runtime is None:
        push_activity(message)
        return
    runtime.emit("push_activity", message=message)


def emit_or_apply_log(runtime: BackgroundRuntime | None, *, append_log, **payload) -> None:
    if runtime is None:
        append_log(**payload)
        return
    runtime.emit("append_log", payload=payload)


def emit_or_apply_image_log(runtime: BackgroundRuntime | None, *, append_image_log, **payload) -> None:
    if runtime is None:
        append_image_log(**payload)
        return
    runtime.emit("append_image_log", payload=payload)


def should_stop_processing(runtime: BackgroundRuntime | None) -> bool:
    if runtime is None:
        return False
    return runtime.should_stop()


def resolve_uploaded_filename(uploaded_file) -> str:
    return getattr(uploaded_file, "name", str(uploaded_file))


def drain_processing_events(*, set_processing_status, finalize_processing_status, push_activity, append_log, append_image_log) -> None:
    event_queue = st.session_state.get("processing_event_queue")
    if event_queue is None:
        return
    while True:
        try:
            event = event_queue.get_nowait()
        except queue.Empty:
            break

        event_type = event.get("type")
        if event_type == "set_state":
            set_session_values(**event["values"])
        elif event_type == "reset_image_state":
            st.session_state.image_assets = []
            st.session_state.image_validation_failures = []
        elif event_type == "set_processing_status":
            set_processing_status(**event["payload"])
        elif event_type == "finalize_processing_status":
            finalize_processing_status(event["stage"], event["detail"], event["progress"])
        elif event_type == "push_activity":
            push_activity(event["message"])
        elif event_type == "append_log":
            append_log(**event["payload"])
        elif event_type == "append_image_log":
            append_image_log(**event["payload"])
        elif event_type == "worker_complete":
            st.session_state.processing_outcome = event["outcome"]
            st.session_state.processing_worker = None
            st.session_state.processing_event_queue = None
            st.session_state.processing_stop_event = None
            st.session_state.processing_stop_requested = False


def processing_worker_is_active() -> bool:
    worker = st.session_state.get("processing_worker")
    return worker is not None and worker.is_alive()


def request_processing_stop() -> None:
    stop_event = st.session_state.get("processing_stop_event")
    if stop_event is not None:
        stop_event.set()
    st.session_state.processing_stop_requested = True


def start_background_processing(
    *,
    worker_target,
    reset_run_state,
    push_activity,
    set_processing_status,
    uploaded_filename: str,
    uploaded_token: str,
    jobs: list[dict[str, str | int]],
    image_assets: list,
    image_mode: str,
    app_config: dict[str, object],
    model: str,
    max_retries: int,
) -> None:
    existing_result = get_current_result_bundle()
    if existing_result is not None:
        st.session_state.previous_result = existing_result

    reset_run_state()
    st.session_state.latest_source_name = uploaded_filename
    st.session_state.latest_source_token = uploaded_token
    st.session_state.selected_source_token = uploaded_token
    st.session_state.latest_image_mode = image_mode
    st.session_state.processing_outcome = "running"

    processing_events = queue.Queue()
    stop_event = threading.Event()
    runtime = BackgroundRuntime(processing_events, stop_event)

    push_activity("Запуск обработки документа.")
    set_processing_status(
        stage="Инициализация",
        detail="Проверяю доступность OpenAI, Pandoc и системного промпта.",
        current_block=0,
        block_count=len(jobs),
        progress=0.0,
        is_running=True,
    )

    worker = threading.Thread(
        target=worker_target,
        kwargs={
            "runtime": runtime,
            "uploaded_filename": uploaded_filename,
            "jobs": jobs,
            "image_assets": image_assets,
            "image_mode": image_mode,
            "app_config": app_config,
            "model": model,
            "max_retries": max_retries,
        },
        daemon=True,
    )
    st.session_state.processing_worker = worker
    st.session_state.processing_event_queue = processing_events
    st.session_state.processing_stop_event = stop_event
    worker.start()