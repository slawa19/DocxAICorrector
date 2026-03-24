import hashlib
import logging
import queue
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

import streamlit as st

from logger import log_event
from restart_store import clear_restart_source, load_restart_source_bytes, store_completed_source, store_restart_source
from state import build_default_image_processing_summary
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
_DOCX_ZIP_MAGIC = b"PK\x03\x04"
_LEGACY_DOC_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_DEFAULT_UPLOADED_FILENAME = "document.docx"
_DOC_CONVERSION_TIMEOUT_SECONDS = 120


def _build_default_image_processing_summary() -> dict[str, object]:
    return build_default_image_processing_summary()


def _reset_image_state() -> None:
    st.session_state.image_assets = []
    st.session_state.image_validation_failures = []
    st.session_state.image_processing_summary = _build_default_image_processing_summary()


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


class InMemoryUploadedFile(BytesIO):
    name: str
    size: int


@dataclass(frozen=True)
class FrozenUploadPayload:
    filename: str
    content_bytes: bytes
    file_size: int
    content_hash: str
    file_token: str


@dataclass(frozen=True)
class NormalizedUploadedDocument:
    original_filename: str
    filename: str
    content_bytes: bytes
    source_format: str
    conversion_backend: str | None


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


def _detect_uploaded_document_format(*, filename: str, source_bytes: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if source_bytes.startswith(_DOCX_ZIP_MAGIC):
        return "docx"
    if source_bytes.startswith(_LEGACY_DOC_MAGIC):
        return "doc" if suffix == ".doc" else "unknown"
    if suffix == ".docx":
        return "docx"
    if suffix == ".doc":
        return "doc"
    return "unknown"


def _build_normalized_docx_filename(filename: str) -> str:
    path = Path(filename or "document")
    if path.suffix.lower() == ".docx":
        return path.name or "document.docx"
    if path.suffix:
        return str(path.with_suffix(".docx"))
    if path.name:
        return f"{path.name}.docx"
    return "document.docx"


def _run_completed_process(
    command: list[str],
    *,
    error_message: str,
    text: bool = True,
    timeout_seconds: int = _DOC_CONVERSION_TIMEOUT_SECONDS,
):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=text,
            timeout=timeout_seconds,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"{error_message} Превышено время ожидания {timeout_seconds} сек."
        ) from exc
    except OSError as exc:
        raise RuntimeError(error_message) from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip() if text else ""
        detail = stderr or stdout or f"exit_code={result.returncode}"
        raise RuntimeError(f"{error_message} {detail}")
    return result


def _convert_legacy_doc_with_soffice(*, soffice_path: str, filename: str, source_bytes: bytes) -> bytes:
    normalized_filename = _build_normalized_docx_filename(filename)
    with tempfile.TemporaryDirectory(prefix="docxaicorrector_doc_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / (Path(filename).name or "document.doc")
        output_path = temp_dir / Path(normalized_filename).name
        input_path.write_bytes(source_bytes)
        _run_completed_process(
            [
                soffice_path,
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                str(temp_dir),
                str(input_path),
            ],
            error_message="Не удалось конвертировать legacy DOC через LibreOffice.",
        )
        if not output_path.exists():
            raise RuntimeError("Не удалось конвертировать legacy DOC через LibreOffice: выходной DOCX не создан.")
        output_bytes = output_path.read_bytes()
        if not output_bytes:
            raise RuntimeError("Не удалось конвертировать legacy DOC через LibreOffice: выходной DOCX пуст.")
        return output_bytes


def _convert_legacy_doc_with_antiword(*, antiword_path: str, filename: str, source_bytes: bytes) -> bytes:
    from generation import ensure_pandoc_available
    import pypandoc

    ensure_pandoc_available()
    normalized_filename = _build_normalized_docx_filename(filename)
    with tempfile.TemporaryDirectory(prefix="docxaicorrector_doc_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / (Path(filename).name or "document.doc")
        output_path = temp_dir / Path(normalized_filename).name
        input_path.write_bytes(source_bytes)
        antiword_result = _run_completed_process(
            [antiword_path, "-x", "db", str(input_path)],
            error_message="Не удалось извлечь legacy DOC через antiword.",
        )
        docbook_xml = (antiword_result.stdout or "").strip()
        if not docbook_xml:
            raise RuntimeError("Не удалось извлечь legacy DOC через antiword: получен пустой DocBook XML.")
        try:
            pypandoc.convert_text(docbook_xml, to="docx", format="docbook", outputfile=str(output_path))
        except (OSError, RuntimeError) as exc:
            raise RuntimeError("Не удалось собрать DOCX из legacy DOC через Pandoc.") from exc
        output_bytes = output_path.read_bytes() if output_path.exists() else b""
        if not output_bytes:
            raise RuntimeError("Не удалось собрать DOCX из legacy DOC через Pandoc: выходной DOCX пуст.")
        return output_bytes


def _convert_legacy_doc_to_docx(*, filename: str, source_bytes: bytes) -> tuple[bytes, str]:
    soffice_path = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice_path:
        try:
            return _convert_legacy_doc_with_soffice(
                soffice_path=soffice_path,
                filename=filename,
                source_bytes=source_bytes,
            ), "libreoffice"
        except RuntimeError as soffice_exc:
            antiword_path = shutil.which("antiword")
            if antiword_path:
                try:
                    return _convert_legacy_doc_with_antiword(
                        antiword_path=antiword_path,
                        filename=filename,
                        source_bytes=source_bytes,
                    ), "antiword+pandoc"
                except RuntimeError as antiword_exc:
                    raise RuntimeError(
                        "Не удалось конвертировать legacy DOC ни через LibreOffice, ни через antiword+pandoc. "
                        f"LibreOffice: {soffice_exc} antiword+pandoc: {antiword_exc}"
                    ) from antiword_exc
            raise soffice_exc

    antiword_path = shutil.which("antiword")
    if antiword_path:
        return _convert_legacy_doc_with_antiword(
            antiword_path=antiword_path,
            filename=filename,
            source_bytes=source_bytes,
        ), "antiword+pandoc"

    raise RuntimeError(
        "Загружен legacy DOC-файл, но автоконвертация недоступна. "
        "Установите в WSL LibreOffice (`soffice`) или связку `antiword` + `pandoc`."
    )


def normalize_uploaded_document(*, filename: str, source_bytes: bytes) -> NormalizedUploadedDocument:
    source_format = _detect_uploaded_document_format(filename=filename, source_bytes=source_bytes)
    normalized_filename = _build_normalized_docx_filename(filename) if source_format in {"doc", "docx"} else filename

    if source_format == "doc":
        converted_bytes, conversion_backend = _convert_legacy_doc_to_docx(
            filename=filename,
            source_bytes=source_bytes,
        )
        return NormalizedUploadedDocument(
            original_filename=filename,
            filename=normalized_filename,
            content_bytes=converted_bytes,
            source_format=source_format,
            conversion_backend=conversion_backend,
        )

    return NormalizedUploadedDocument(
        original_filename=filename,
        filename=normalized_filename if source_format == "docx" else filename,
        content_bytes=bytes(source_bytes),
        source_format=source_format,
        conversion_backend=None,
    )


def _build_uploaded_file_token_components(*, normalized_document: NormalizedUploadedDocument, source_bytes: bytes) -> tuple[int, str]:
    identity_bytes = source_bytes if normalized_document.source_format == "doc" else normalized_document.content_bytes
    identity_hash = hashlib.sha256(identity_bytes).hexdigest()[:16]
    return len(identity_bytes), identity_hash


def freeze_uploaded_file(uploaded_file: UploadedFileLike | BytesIO) -> FrozenUploadPayload:
    source_bytes = read_uploaded_file_bytes(uploaded_file)
    filename = getattr(uploaded_file, "name", "") or _DEFAULT_UPLOADED_FILENAME
    normalized_document = normalize_uploaded_document(filename=filename, source_bytes=source_bytes)
    token_size, token_hash = _build_uploaded_file_token_components(
        normalized_document=normalized_document,
        source_bytes=source_bytes,
    )
    content_hash = hashlib.sha256(normalized_document.content_bytes).hexdigest()[:16]
    return FrozenUploadPayload(
        filename=normalized_document.filename,
        content_bytes=normalized_document.content_bytes,
        file_size=len(normalized_document.content_bytes),
        content_hash=content_hash,
        file_token=f"{normalized_document.filename}:{token_size}:{token_hash}",
    )


def build_uploaded_file_token(uploaded_file: UploadedFileLike | BytesIO | None = None, *, source_name: str | None = None, source_bytes: bytes | None = None) -> str:
    if isinstance(uploaded_file, FrozenUploadPayload):
        return uploaded_file.file_token
    if source_bytes is None:
        if uploaded_file is None:
            raise ValueError("Для построения токена нужен uploaded_file или source_bytes.")
        source_bytes = read_uploaded_file_bytes(uploaded_file)
    file_name = source_name if source_name is not None else (getattr(uploaded_file, "name", "") or _DEFAULT_UPLOADED_FILENAME)
    normalized_document = normalize_uploaded_document(filename=file_name, source_bytes=bytes(source_bytes))
    file_size, content_hash = _build_uploaded_file_token_components(
        normalized_document=normalized_document,
        source_bytes=bytes(source_bytes),
    )
    return f"{normalized_document.filename}:{file_size}:{content_hash}"


def build_in_memory_uploaded_file(*, source_name: str, source_bytes: bytes):
    uploaded_file = InMemoryUploadedFile(source_bytes)
    uploaded_file.name = source_name
    uploaded_file.size = len(source_bytes)
    return uploaded_file


def _coerce_metric_to_int(metrics: dict[str, object], key: str) -> int:
    value = metrics.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def build_uploaded_file_selection_marker(uploaded_file) -> str:
    return build_uploaded_file_token(uploaded_file)


def build_preparation_request_marker(uploaded_file, *, chunk_size: int) -> str:
    return f"{build_uploaded_file_selection_marker(uploaded_file)}:{chunk_size}"


def normalize_background_error(
    *,
    stage: str,
    exc: Exception,
    user_message: str,
    severity: str = "error",
    recoverable: bool = False,
) -> dict[str, object]:
    return {
        "stage": stage,
        "severity": severity,
        "user_message": user_message,
        "technical_message": str(exc),
        "error_type": exc.__class__.__name__,
        "recoverable": recoverable,
    }


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
        _reset_image_state()
        return
    runtime.emit(ResetImageStateEvent())


def emit_or_apply_status(runtime: BackgroundRuntime | None, *, set_processing_status, **payload) -> None:
    if runtime is None:
        set_processing_status(**payload)
        return
    runtime.emit(SetProcessingStatusEvent(payload=payload))


def emit_or_apply_finalize(runtime: BackgroundRuntime | None, *, finalize_processing_status, stage: str, detail: str, progress: float, terminal_kind: str | None = None) -> None:
    if runtime is None:
        finalize_processing_status(stage, detail, progress, terminal_kind)
        return
    runtime.emit(FinalizeProcessingStatusEvent(stage=stage, detail=detail, progress=progress, terminal_kind=terminal_kind))


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
    if isinstance(uploaded_file, FrozenUploadPayload):
        return uploaded_file.filename
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
            _reset_image_state()
        elif isinstance(event, SetProcessingStatusEvent):
            set_processing_status(**event.payload)
        elif isinstance(event, FinalizeProcessingStatusEvent):
            finalize_processing_status(event.stage, event.detail, event.progress, event.terminal_kind)
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
            finalize_processing_status(event.stage, event.detail, event.progress, event.terminal_kind)
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
            st.session_state.processing_outcome = ProcessingOutcome.IDLE.value
            finalize_processing_status(
                "Документ подготовлен",
                "Анализ файла завершён. Можно запускать обработку.",
                1.0,
                "completed",
            )
        elif isinstance(event, PreparationFailedEvent):
            st.session_state.prepared_run_context = None
            st.session_state.preparation_input_marker = event.upload_marker
            st.session_state.preparation_failed_marker = event.upload_marker
            st.session_state.preparation_worker = None
            st.session_state.preparation_event_queue = None
            st.session_state.last_background_error = event.error_details
            st.session_state.last_error = event.error_message
            st.session_state.processing_outcome = ProcessingOutcome.FAILED.value
            finalize_processing_status(
                "Ошибка подготовки",
                event.error_message,
                1.0,
                "error",
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
    uploaded_payload,
    upload_marker: str,
    chunk_size: int,
    image_mode: str,
    keep_all_image_variants: bool,
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
                    "block_count": _coerce_metric_to_int(metrics, "block_count"),
                    "file_size_bytes": _coerce_metric_to_int(metrics, "file_size_bytes"),
                    "paragraph_count": _coerce_metric_to_int(metrics, "paragraph_count"),
                    "image_count": _coerce_metric_to_int(metrics, "image_count"),
                    "source_chars": _coerce_metric_to_int(metrics, "source_chars"),
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
                uploaded_payload=uploaded_payload,
                chunk_size=chunk_size,
                image_mode=image_mode,
                keep_all_image_variants=keep_all_image_variants,
                progress_callback=report_progress,
            )
        except Exception as exc:
            error_details = normalize_background_error(
                stage="preparation",
                exc=exc,
                user_message=str(exc),
            )
            runtime.emit(
                PreparationFailedEvent(
                    upload_marker=upload_marker,
                    error_message=str(error_details["user_message"]),
                    error_details=error_details,
                )
            )
            return
        runtime.emit(PreparationCompleteEvent(prepared_run_context=prepared_run_context, upload_marker=upload_marker))

    worker = threading.Thread(target=run_preparation, daemon=True, name="docx-preparation-worker")
    st.session_state.preparation_event_queue = preparation_events
    st.session_state.preparation_worker = worker
    worker.start()
