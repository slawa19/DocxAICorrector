import hashlib
import logging
import queue
import threading
from io import BytesIO
from typing import Protocol, runtime_checkable

import streamlit as st

from logger import log_event
from restart_store import clear_restart_source, load_restart_source_bytes, store_completed_source, store_restart_source
from runtime_events import (
    AppendImageLogEvent,
    AppendLogEvent,
    FinalizeProcessingStatusEvent,
    PreparationCompleteEvent,
    PreparationFailedEvent,
    ProcessingEvent,
    PushActivityEvent,
    ResetImageStateEvent,
    SetProcessingStatusEvent,
    SetStateEvent,
    WorkerCompleteEvent,
)
from workflow_state import ProcessingOutcome


MAX_COMPLETED_SOURCE_BYTES = 8 * 1024 * 1024


class BackgroundRuntime:
    def __init__(self, event_queue, stop_event):
        self._event_queue = event_queue
        self._stop_event = stop_event

    def emit(self, event: ProcessingEvent) -> None:
        self._event_queue.put(event)

    def should_stop(self) -> bool:
        return self._stop_event.is_set()


@runtime_checkable
class UploadedFileLike(Protocol):
    name: str

    def read(self, size: int = -1) -> bytes: ...

    def getvalue(self) -> bytes: ...

    def seek(self, offset: int, whence: int = 0) -> int: ...


def read_uploaded_file_bytes(uploaded_file: UploadedFileLike | BytesIO) -> bytes:
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


def build_uploaded_file_token(uploaded_file: UploadedFileLike | BytesIO | None = None, *, source_name: str | None = None, source_bytes: bytes | None = None) -> str:
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


def build_uploaded_file_selection_marker(uploaded_file) -> str:
    source_name = getattr(uploaded_file, "name", "")
    file_size = getattr(uploaded_file, "size", "")
    file_id = getattr(uploaded_file, "file_id", "")
    if file_id:
        return f"{source_name}:{file_size}:{file_id}"
    return f"{source_name}:{file_size}"


def build_preparation_request_marker(uploaded_file, *, chunk_size: int) -> str:
    return f"{build_uploaded_file_selection_marker(uploaded_file)}:{chunk_size}"


def build_result_bundle(*, source_name: str, source_token: str, docx_bytes: bytes, markdown_text: str) -> dict[str, object]:
    return {
        "source_name": source_name,
        "source_token": source_token,
        "docx_bytes": docx_bytes,
        "markdown_text": markdown_text,
    }


def should_cache_completed_source(*, source_bytes: bytes) -> bool:
    return len(source_bytes) <= MAX_COMPLETED_SOURCE_BYTES


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
            previous_completed_source = st.session_state.get("completed_source")
            if event.outcome == ProcessingOutcome.SUCCEEDED.value and restart_source:
                source_bytes = load_restart_source_bytes(restart_source)
                if source_bytes:
                    if should_cache_completed_source(source_bytes=source_bytes):
                        try:
                            st.session_state.completed_source = store_completed_source(
                                session_id=str(restart_source.get("session_id", st.session_state.get("restart_session_id", ""))),
                                source_name=str(restart_source.get("filename", "")),
                                source_token=str(restart_source.get("token", "")),
                                source_bytes=source_bytes,
                                previous_completed_source=previous_completed_source,
                            )
                        except OSError as exc:
                            if previous_completed_source:
                                clear_restart_source(previous_completed_source)
                            st.session_state.completed_source = None
                            log_event(
                                logging.WARNING,
                                "completed_source_store_failed",
                                "Не удалось сохранить completed source во временное файловое хранилище.",
                                filename=str(restart_source.get("filename", "")),
                                source_token=str(restart_source.get("token", "")),
                                error_message=str(exc),
                            )
                            push_activity(
                                "Не удалось сохранить исходный DOCX для повторного запуска после завершения. Для нового запуска загрузите файл заново."
                            )
                    else:
                        if previous_completed_source:
                            clear_restart_source(previous_completed_source)
                        st.session_state.completed_source = None
                        push_activity(
                            "Исходный файл слишком большой для повторного запуска из памяти. Для нового запуска загрузите DOCX заново."
                        )
                clear_restart_source(restart_source)
                st.session_state.restart_source = None
            st.session_state.processing_outcome = event.outcome
            st.session_state.processing_worker = None
            st.session_state.processing_event_queue = None
            st.session_state.processing_stop_event = None
            st.session_state.processing_stop_requested = False


def drain_preparation_events(*, reset_run_state, set_processing_status, finalize_processing_status, push_activity) -> None:
    event_queue = st.session_state.get("preparation_event_queue")
    if event_queue is None:
        return
    while True:
        try:
            event = event_queue.get_nowait()
        except queue.Empty:
            break

        if isinstance(event, SetProcessingStatusEvent):
            set_processing_status(**event.payload)
        elif isinstance(event, FinalizeProcessingStatusEvent):
            finalize_processing_status(event.stage, event.detail, event.progress)
        elif isinstance(event, PushActivityEvent):
            push_activity(event.message)
        elif isinstance(event, PreparationCompleteEvent):
            prepared_run_context = event.prepared_run_context
            previous_token = str(st.session_state.get("selected_source_token", ""))
            uploaded_token = str(getattr(prepared_run_context, "uploaded_file_token", ""))
            if previous_token and uploaded_token and previous_token != uploaded_token:
                reset_run_state(keep_restart_source=False)
            st.session_state.prepared_run_context = prepared_run_context
            st.session_state.preparation_input_marker = event.upload_marker
            st.session_state.preparation_failed_marker = ""
            st.session_state.selected_source_token = uploaded_token
            st.session_state.prepared_source_key = str(getattr(prepared_run_context, "prepared_source_key", ""))
            st.session_state.preparation_worker = None
            st.session_state.preparation_event_queue = None
            finalize_processing_status(
                "Документ подготовлен",
                "Анализ файла завершён. Можно запускать обработку.",
                1.0,
            )
        elif isinstance(event, PreparationFailedEvent):
            st.session_state.prepared_run_context = None
            st.session_state.preparation_input_marker = event.upload_marker
            st.session_state.preparation_failed_marker = event.upload_marker
            st.session_state.preparation_worker = None
            st.session_state.preparation_event_queue = None
            st.session_state.last_error = event.error_message
            finalize_processing_status(
                "Ошибка подготовки",
                event.error_message,
                1.0,
            )
            push_activity("Не удалось прочитать и проанализировать DOCX-файл.")


def preparation_worker_is_active() -> bool:
    worker = st.session_state.get("preparation_worker")
    return worker is not None and worker.is_alive()


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
    source_paragraphs: list | None = None,
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
            "source_paragraphs": source_paragraphs,
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


def start_background_preparation(
    *,
    worker_target,
    reset_run_state,
    push_activity,
    set_processing_status,
    uploaded_file,
    upload_marker: str,
    chunk_size: int,
    image_mode: str,
    enable_post_redraw_validation: bool,
) -> None:
    reset_run_state(keep_restart_source=False)
    st.session_state.preparation_input_marker = upload_marker
    st.session_state.preparation_failed_marker = ""
    st.session_state.prepared_run_context = None

    preparation_events = queue.Queue()
    runtime = BackgroundRuntime(preparation_events, threading.Event())

    push_activity("Файл получен сервером. Запускаю анализ DOCX.")
    set_processing_status(
        stage="Файл получен",
        detail="Файл передан на сервер. Запускаю анализ документа.",
        progress=0.02,
        is_running=True,
        phase="preparing",
    )

    last_reported_stage = {"value": ""}

    def report_progress(*, stage: str, detail: str, progress: float, metrics: dict[str, object]) -> None:
        runtime.emit(
            SetProcessingStatusEvent(
                payload={
                    "stage": stage,
                    "detail": detail,
                    "progress": progress,
                    "is_running": True,
                    "phase": "preparing",
                    "block_count": int(metrics.get("block_count", 0) or 0),
                    "file_size_bytes": int(metrics.get("file_size_bytes", 0) or 0),
                    "paragraph_count": int(metrics.get("paragraph_count", 0) or 0),
                    "image_count": int(metrics.get("image_count", 0) or 0),
                    "source_chars": int(metrics.get("source_chars", 0) or 0),
                    "cached": bool(metrics.get("cached", False)),
                }
            )
        )
        if stage and stage != last_reported_stage["value"]:
            runtime.emit(PushActivityEvent(message=f"[Анализ] {stage}: {detail}"))
            last_reported_stage["value"] = stage

    def run_preparation() -> None:
        try:
            prepared_run_context = worker_target(
                uploaded_file=uploaded_file,
                chunk_size=chunk_size,
                image_mode=image_mode,
                enable_post_redraw_validation=enable_post_redraw_validation,
                progress_callback=report_progress,
            )
        except Exception as exc:
            runtime.emit(PreparationFailedEvent(upload_marker=upload_marker, error_message=str(exc)))
            return
        runtime.emit(PreparationCompleteEvent(prepared_run_context=prepared_run_context, upload_marker=upload_marker))

    worker = threading.Thread(target=run_preparation, daemon=True, name="docx-preparation-worker")
    st.session_state.preparation_event_queue = preparation_events
    st.session_state.preparation_worker = worker
    worker.start()