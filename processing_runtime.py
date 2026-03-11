import hashlib
import logging
import queue
import threading
from io import BytesIO

import streamlit as st

from logger import log_event
from restart_store import clear_restart_source, load_restart_source_bytes, store_restart_source
from runtime_events import (
    AppendImageLogEvent,
    AppendLogEvent,
    FinalizeProcessingStatusEvent,
    ProcessingEvent,
    PushActivityEvent,
    ResetImageStateEvent,
    SetProcessingStatusEvent,
    SetStateEvent,
    WorkerCompleteEvent,
)
from workflow_state import ProcessingOutcome


class BackgroundRuntime:
    def __init__(self, event_queue, stop_event):
        self._event_queue = event_queue
        self._stop_event = stop_event

    def emit(self, event: ProcessingEvent) -> None:
        self._event_queue.put(event)

    def should_stop(self) -> bool:
        return self._stop_event.is_set()


def read_uploaded_file_bytes(uploaded_file) -> bytes:
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    if hasattr(uploaded_file, "getvalue"):
        source_bytes = uploaded_file.getvalue()
    else:
        source_bytes = uploaded_file.read()
    if not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
        raise ValueError("Не удалось прочитать содержимое загруженного файла.")
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    return bytes(source_bytes)


def build_uploaded_file_token(uploaded_file=None, *, source_name: str | None = None, source_bytes: bytes | None = None) -> str:
    if source_bytes is None:
        source_bytes = read_uploaded_file_bytes(uploaded_file)
    file_name = source_name if source_name is not None else getattr(uploaded_file, "name", "")
    file_size = len(source_bytes)
    content_hash = hashlib.sha256(source_bytes).hexdigest()[:16]
    return f"{file_name}:{file_size}:{content_hash}"


def build_in_memory_uploaded_file(*, source_name: str, source_bytes: bytes):
    uploaded_file = BytesIO(source_bytes)
    uploaded_file.name = source_name
    uploaded_file.size = len(source_bytes)
    return uploaded_file


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


def set_session_values(**values) -> None:
    for key, value in values.items():
        st.session_state[key] = value


def emit_or_apply_state(runtime: BackgroundRuntime | None, **values) -> None:
    if runtime is None:
        set_session_values(**values)
        return
    runtime.emit(SetStateEvent(values=values))


def emit_or_apply_image_reset(runtime: BackgroundRuntime | None) -> None:
    if runtime is None:
        st.session_state.image_assets = []
        st.session_state.image_validation_failures = []
        return
    runtime.emit(ResetImageStateEvent())


def emit_or_apply_status(runtime: BackgroundRuntime | None, *, set_processing_status, **payload) -> None:
    if runtime is None:
        set_processing_status(**payload)
        return
    runtime.emit(SetProcessingStatusEvent(payload=payload))


def emit_or_apply_finalize(runtime: BackgroundRuntime | None, *, finalize_processing_status, stage: str, detail: str, progress: float) -> None:
    if runtime is None:
        finalize_processing_status(stage, detail, progress)
        return
    runtime.emit(FinalizeProcessingStatusEvent(stage=stage, detail=detail, progress=progress))


def emit_or_apply_activity(runtime: BackgroundRuntime | None, *, push_activity, message: str) -> None:
    if runtime is None:
        push_activity(message)
        return
    runtime.emit(PushActivityEvent(message=message))


def emit_or_apply_log(runtime: BackgroundRuntime | None, *, append_log, **payload) -> None:
    if runtime is None:
        append_log(**payload)
        return
    runtime.emit(AppendLogEvent(payload=payload))


def emit_or_apply_image_log(runtime: BackgroundRuntime | None, *, append_image_log, **payload) -> None:
    if runtime is None:
        append_image_log(**payload)
        return
    runtime.emit(AppendImageLogEvent(payload=payload))


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

        if isinstance(event, SetStateEvent):
            set_session_values(**event.values)
        elif isinstance(event, ResetImageStateEvent):
            st.session_state.image_assets = []
            st.session_state.image_validation_failures = []
        elif isinstance(event, SetProcessingStatusEvent):
            set_processing_status(**event.payload)
        elif isinstance(event, FinalizeProcessingStatusEvent):
            finalize_processing_status(event.stage, event.detail, event.progress)
        elif isinstance(event, PushActivityEvent):
            push_activity(event.message)
        elif isinstance(event, AppendLogEvent):
            append_log(**event.payload)
        elif isinstance(event, AppendImageLogEvent):
            append_image_log(**event.payload)
        elif isinstance(event, WorkerCompleteEvent):
            restart_source = st.session_state.get("restart_source")
            if event.outcome == ProcessingOutcome.SUCCEEDED.value and restart_source:
                source_bytes = load_restart_source_bytes(restart_source)
                if source_bytes:
                    st.session_state.completed_source = {
                        "filename": str(restart_source.get("filename", "")),
                        "token": str(restart_source.get("token", "")),
                        "source_bytes": source_bytes,
                        "size": len(source_bytes),
                    }
                clear_restart_source(restart_source)
                st.session_state.restart_source = None
            st.session_state.processing_outcome = event.outcome
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
    source_bytes: bytes,
    jobs: list[dict[str, str | int]],
    image_assets: list,
    image_mode: str,
    app_config: dict[str, object],
    model: str,
    max_retries: int,
) -> None:
    previous_restart_source = st.session_state.get("restart_source")
    restart_session_id = str(st.session_state.get("restart_session_id", ""))
    reset_run_state()
    st.session_state.latest_source_name = uploaded_filename
    st.session_state.latest_source_token = uploaded_token
    st.session_state.selected_source_token = uploaded_token
    try:
        st.session_state.restart_source = store_restart_source(
            session_id=restart_session_id,
            source_name=uploaded_filename,
            source_token=uploaded_token,
            source_bytes=source_bytes,
            previous_restart_source=previous_restart_source,
        )
    except OSError as exc:
        st.session_state.restart_source = None
        log_event(
            logging.WARNING,
            "restart_source_store_failed",
            "Не удалось сохранить временный restart source; продолжаю обработку без возможности restart без повторной загрузки.",
            filename=uploaded_filename,
            source_token=uploaded_token,
            error_message=str(exc),
        )
        push_activity("Не удалось сохранить временный файл для restart. Повторный запуск без загрузки файла будет недоступен.")
    st.session_state.latest_image_mode = image_mode
    st.session_state.processing_outcome = ProcessingOutcome.RUNNING.value

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