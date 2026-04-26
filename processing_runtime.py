import hashlib
import logging
import os
import queue
import signal
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from collections.abc import Callable
from typing import Protocol, cast, runtime_checkable

import streamlit as st

from logger import log_event
from restart_store import clear_restart_source, load_restart_source_bytes, store_completed_source, store_restart_source
from state import (
    apply_processing_start,
    apply_preparation_complete,
    apply_preparation_failure,
    apply_processing_completion,
    get_latest_audiobook_postprocess_enabled,
    get_processing_event_queue,
    get_latest_processing_operation,
    get_processing_stop_event,
    get_processing_worker,
    get_preparation_event_queue,
    get_preparation_worker,
    get_latest_narration_text,
    get_latest_source_name,
    get_latest_source_token,
    get_restart_source,
    mark_preparation_started,
    request_processing_stop as request_processing_stop_via_state,
    reset_image_state,
    set_preparation_runtime,
    set_restart_source,
)
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
_PDF_MAGIC = b"%PDF-"
_DEFAULT_UPLOADED_FILENAME = "document.docx"
_DOC_CONVERSION_TIMEOUT_SECONDS = 120
_ALLOWED_SET_STATE_EVENT_KEYS = {
    "image_assets",
    "last_background_error",
    "last_error",
    "latest_docx_bytes",
    "latest_markdown",
    "latest_narration_text",
    "latest_marker_diagnostics_artifact",
    "latest_result_notice",
    "processed_block_markdowns",
    "processed_paragraph_registry",
}

__all__ = [
    "BackgroundRuntime",
    "FrozenUploadPayload",
    "NormalizedUploadedDocument",
    "UploadSourceIdentity",
    "ResolvedUploadContract",
    "InMemoryUploadedFile",
    "RuntimeEventEmitterDependencies",
    "RuntimeEventEmitters",
    "legacy_doc_conversion_available",
    "read_uploaded_file_bytes",
    "normalize_uploaded_document",
    "resolve_upload_contract",
    "freeze_resolved_upload",
    "freeze_uploaded_file",
    "build_uploaded_file_token",
    "build_in_memory_uploaded_file",
    "build_uploaded_file_selection_marker",
    "build_preparation_request_marker",
    "normalize_background_error",
    "build_result_bundle",
    "should_cache_completed_source",
    "get_current_result_bundle",
    "emit_or_apply_state",
    "emit_or_apply_image_reset",
    "emit_or_apply_status",
    "emit_or_apply_finalize",
    "emit_or_apply_activity",
    "emit_or_apply_log",
    "emit_or_apply_image_log",
    "build_runtime_event_emitters",
    "should_stop_processing",
    "resolve_uploaded_filename",
    "drain_processing_events",
    "drain_preparation_events",
    "preparation_worker_is_active",
    "processing_worker_is_active",
    "request_processing_stop",
    "start_background_processing",
    "start_background_preparation",
]


def _looks_like_runtime_object_repr(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("<") and " object at 0x" in normalized and normalized.endswith(">")


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


@dataclass(frozen=True)
class UploadSourceIdentity:
    original_filename: str
    source_bytes: bytes
    token_size: int
    token_hash: str


@dataclass(frozen=True)
class ResolvedUploadContract:
    source_identity: UploadSourceIdentity
    normalized_document: NormalizedUploadedDocument

    @property
    def filename(self) -> str:
        return self.normalized_document.filename

    @property
    def content_bytes(self) -> bytes:
        return self.normalized_document.content_bytes

    @property
    def file_size(self) -> int:
        return len(self.normalized_document.content_bytes)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.normalized_document.content_bytes).hexdigest()[:16]

    @property
    def file_token(self) -> str:
        return f"{self.filename}:{self.source_identity.token_size}:{self.source_identity.token_hash}"


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
    if source_bytes.startswith(_PDF_MAGIC):
        return "pdf"
    if suffix == ".docx":
        return "docx"
    if suffix == ".doc":
        return "doc"
    if suffix == ".pdf":
        return "pdf"
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
    cleanup_process_group: bool = False,
):
    if cleanup_process_group:
        process = None
        try:
            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": text,
            }
            if text:
                popen_kwargs["encoding"] = "utf-8"
                popen_kwargs["errors"] = "replace"
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
            process = subprocess.Popen(command, **popen_kwargs)
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            if process is not None:
                _terminate_process_tree(process)
                process.communicate()
            raise RuntimeError(
                f"{error_message} Превышено время ожидания {timeout_seconds} сек."
            ) from exc
        except OSError as exc:
            raise RuntimeError(error_message) from exc

        if process is None:
            raise RuntimeError(error_message)
        if process.returncode != 0:
            stderr_text = (stderr or "").strip() if text else ""
            stdout_text = (stdout or "").strip() if text else ""
            detail = stderr_text or stdout_text or f"exit_code={process.returncode}"
            raise RuntimeError(f"{error_message} {detail}")
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

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


def _terminate_process_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            process.kill()
            return
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        process.kill()
        return

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            process.kill()


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
            cleanup_process_group=True,
        )
        output_path = _resolve_converted_docx_output(
            temp_dir=temp_dir,
            expected_output_path=output_path,
            missing_output_message="Не удалось конвертировать legacy DOC через LibreOffice: выходной DOCX не создан.",
        )
        output_bytes = output_path.read_bytes()
        if not output_bytes:
            raise RuntimeError("Не удалось конвертировать legacy DOC через LibreOffice: выходной DOCX пуст.")
        return output_bytes


def _resolve_converted_docx_output(*, temp_dir: Path, expected_output_path: Path, missing_output_message: str) -> Path:
    if expected_output_path.exists():
        return expected_output_path
    fallback_matches = sorted(temp_dir.glob("*.docx"))
    if len(fallback_matches) == 1:
        return fallback_matches[0]
    raise RuntimeError(missing_output_message)


def _convert_pdf_to_docx(*, filename: str, source_bytes: bytes) -> tuple[bytes, str]:
    soffice_path = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice_path:
        raise RuntimeError(
            "Загружен PDF-файл, но автоконвертация недоступна. "
            "Установите LibreOffice (`soffice`) внутри WSL."
        )

    normalized_filename = _build_normalized_docx_filename(filename)
    with tempfile.TemporaryDirectory(prefix="docxaicorrector_pdf_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / (Path(filename).name or "document.pdf")
        output_path = temp_dir / Path(normalized_filename).name
        input_path.write_bytes(source_bytes)
        _run_completed_process(
            [
                soffice_path,
                "--headless",
                "--infilter=writer_pdf_import",
                "--convert-to",
                "docx",
                "--outdir",
                str(temp_dir),
                str(input_path),
            ],
            error_message="Не удалось конвертировать PDF через LibreOffice.",
            cleanup_process_group=True,
        )
        output_path = _resolve_converted_docx_output(
            temp_dir=temp_dir,
            expected_output_path=output_path,
            missing_output_message="Не удалось конвертировать PDF через LibreOffice: выходной DOCX не создан.",
        )
        output_bytes = output_path.read_bytes()
        if not output_bytes:
            raise RuntimeError("Не удалось конвертировать PDF через LibreOffice: выходной DOCX пуст.")
        return output_bytes, "libreoffice"


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


def legacy_doc_conversion_available() -> bool:
    if shutil.which("soffice") or shutil.which("libreoffice"):
        return True

    if not shutil.which("antiword"):
        return False

    try:
        import pypandoc

        pypandoc.get_pandoc_version()
    except OSError:
        return False

    return True


def normalize_uploaded_document(*, filename: str, source_bytes: bytes) -> NormalizedUploadedDocument:
    source_format = _detect_uploaded_document_format(filename=filename, source_bytes=source_bytes)
    normalized_filename = _build_normalized_docx_filename(filename) if source_format in {"doc", "docx", "pdf"} else filename

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

    if source_format == "pdf":
        converted_bytes, conversion_backend = _convert_pdf_to_docx(
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
    identity_bytes = source_bytes if normalized_document.source_format in {"doc", "pdf"} else normalized_document.content_bytes
    identity_hash = hashlib.sha256(identity_bytes).hexdigest()[:16]
    return len(identity_bytes), identity_hash


def resolve_upload_contract(*, filename: str, source_bytes: bytes) -> ResolvedUploadContract:
    normalized_document = normalize_uploaded_document(filename=filename, source_bytes=source_bytes)
    token_size, token_hash = _build_uploaded_file_token_components(
        normalized_document=normalized_document,
        source_bytes=source_bytes,
    )
    return ResolvedUploadContract(
        source_identity=UploadSourceIdentity(
            original_filename=filename,
            source_bytes=bytes(source_bytes),
            token_size=token_size,
            token_hash=token_hash,
        ),
        normalized_document=normalized_document,
    )


def freeze_resolved_upload(contract: ResolvedUploadContract) -> FrozenUploadPayload:
    return FrozenUploadPayload(
        filename=contract.filename,
        content_bytes=contract.content_bytes,
        file_size=contract.file_size,
        content_hash=contract.content_hash,
        file_token=contract.file_token,
    )


def freeze_uploaded_file(uploaded_file: UploadedFileLike | BytesIO) -> FrozenUploadPayload:
    source_bytes = read_uploaded_file_bytes(uploaded_file)
    filename = getattr(uploaded_file, "name", "") or _DEFAULT_UPLOADED_FILENAME
    return freeze_resolved_upload(resolve_upload_contract(filename=filename, source_bytes=source_bytes))


def build_uploaded_file_token(uploaded_file: UploadedFileLike | BytesIO | None = None, *, source_name: str | None = None, source_bytes: bytes | None = None) -> str:
    if isinstance(uploaded_file, FrozenUploadPayload):
        return uploaded_file.file_token
    if source_bytes is None:
        if uploaded_file is None:
            raise ValueError("Для построения токена нужен uploaded_file или source_bytes.")
        source_bytes = read_uploaded_file_bytes(uploaded_file)
    file_name = source_name if source_name is not None else (getattr(uploaded_file, "name", "") or _DEFAULT_UPLOADED_FILENAME)
    return resolve_upload_contract(filename=file_name, source_bytes=bytes(source_bytes)).file_token


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


def build_preparation_request_marker(uploaded_file, *, chunk_size: int, processing_operation: str = "edit") -> str:
    resolved_operation = str(processing_operation or "edit").strip().lower() or "edit"
    operation_suffix = "" if resolved_operation == "edit" else f":op={resolved_operation}"
    return f"{build_uploaded_file_selection_marker(uploaded_file)}:{chunk_size}{operation_suffix}"


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


def build_result_bundle(
    *,
    source_name: str,
    source_token: str,
    docx_bytes: bytes | None,
    markdown_text: str,
    narration_text: str | None = None,
    processing_operation: str = "edit",
    audiobook_postprocess_enabled: bool = False,
) -> dict[str, object]:
    return {
        "source_name": source_name,
        "source_token": source_token,
        "docx_bytes": docx_bytes,
        "markdown_text": markdown_text,
        "narration_text": narration_text,
        "processing_operation": processing_operation,
        "audiobook_postprocess_enabled": audiobook_postprocess_enabled,
    }


def should_cache_completed_source(*, source_bytes: bytes) -> bool:
    return len(source_bytes) <= MAX_COMPLETED_SOURCE_BYTES


def get_current_result_bundle() -> dict[str, object] | None:
    latest_docx_bytes = st.session_state.get("latest_docx_bytes")
    latest_narration_text = get_latest_narration_text()
    processing_operation = get_latest_processing_operation()
    if latest_docx_bytes is None:
        if latest_narration_text is None:
            return None
        if processing_operation == "audiobook":
            return None
    if not latest_docx_bytes and latest_narration_text is None:
        return None
    return build_result_bundle(
        source_name=get_latest_source_name(),
        source_token=get_latest_source_token(),
        docx_bytes=latest_docx_bytes,
        markdown_text=st.session_state.get("latest_markdown", ""),
        narration_text=latest_narration_text,
        processing_operation=processing_operation,
        audiobook_postprocess_enabled=get_latest_audiobook_postprocess_enabled(),
    )


def set_session_values(**values) -> None:
    for key, value in values.items():
        st.session_state[key] = value


def _filter_allowed_set_state_values(values: dict[str, object]) -> dict[str, object]:
    unknown_keys = sorted(key for key in values if key not in _ALLOWED_SET_STATE_EVENT_KEYS)
    if unknown_keys:
        log_event(
            logging.WARNING,
            "state_event_unknown_keys",
            "SetStateEvent попытался записать ключи вне разрешённого allowlist.",
            unknown_keys=unknown_keys,
        )
    return {key: value for key, value in values.items() if key in _ALLOWED_SET_STATE_EVENT_KEYS}


def emit_or_apply_state(runtime: BackgroundRuntime | None, **values) -> None:
    if runtime is None:
        set_session_values(**values)
        return
    runtime.emit(SetStateEvent(values=values))


def emit_or_apply_image_reset(runtime: BackgroundRuntime | None) -> None:
    if runtime is None:
        reset_image_state()
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


@dataclass(frozen=True)
class RuntimeEventEmitterDependencies:
    set_processing_status: Callable[..., None]
    finalize_processing_status: Callable[..., None]
    push_activity: Callable[[str], None]
    append_log: Callable[..., None]
    append_image_log: Callable[..., None]


@dataclass(frozen=True)
class RuntimeEventEmitters:
    emit_state: Callable[..., None]
    emit_image_reset: Callable[..., None]
    emit_status: Callable[..., None]
    emit_finalize: Callable[..., None]
    emit_activity: Callable[..., None]
    emit_log: Callable[..., None]
    emit_image_log: Callable[..., None]


def build_runtime_event_emitters(*, dependencies: RuntimeEventEmitterDependencies) -> RuntimeEventEmitters:
    return RuntimeEventEmitters(
        emit_state=emit_or_apply_state,
        emit_image_reset=emit_or_apply_image_reset,
        emit_status=lambda runtime, **payload: emit_or_apply_status(
            runtime,
            set_processing_status=dependencies.set_processing_status,
            **payload,
        ),
        emit_finalize=lambda runtime, stage, detail, progress, terminal_kind=None: emit_or_apply_finalize(
            runtime,
            finalize_processing_status=dependencies.finalize_processing_status,
            stage=stage,
            detail=detail,
            progress=progress,
            terminal_kind=terminal_kind,
        ),
        emit_activity=lambda runtime, message: emit_or_apply_activity(
            runtime,
            push_activity=dependencies.push_activity,
            message=message,
        ),
        emit_log=lambda runtime, **payload: emit_or_apply_log(
            runtime,
            append_log=dependencies.append_log,
            **payload,
        ),
        emit_image_log=lambda runtime, **payload: emit_or_apply_image_log(
            runtime,
            append_image_log=dependencies.append_image_log,
            **payload,
        ),
    )


def should_stop_processing(runtime: BackgroundRuntime | None) -> bool:
    if runtime is None:
        return False
    return runtime.should_stop()


def resolve_uploaded_filename(uploaded_file) -> str:
    if isinstance(uploaded_file, FrozenUploadPayload):
        return uploaded_file.filename
    explicit_name = getattr(uploaded_file, "name", None)
    if isinstance(explicit_name, str) and explicit_name.strip():
        return explicit_name

    fallback_name = str(uploaded_file).strip()
    if not fallback_name or _looks_like_runtime_object_repr(fallback_name):
        return _DEFAULT_UPLOADED_FILENAME
    return fallback_name


def drain_processing_events(*, set_processing_status, finalize_processing_status, push_activity, append_log, append_image_log) -> None:
    event_queue = get_processing_event_queue()
    if event_queue is None:
        return
    while True:
        try:
            event = event_queue.get_nowait()
        except queue.Empty:
            break

        if isinstance(event, SetStateEvent):
            allowed_values = _filter_allowed_set_state_values(event.values)
            if allowed_values:
                set_session_values(**allowed_values)
        elif isinstance(event, ResetImageStateEvent):
            reset_image_state()
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
            apply_processing_completion(
                outcome=event.outcome,
                push_activity=push_activity,
                load_restart_source_bytes_fn=load_restart_source_bytes,
                clear_restart_source_fn=clear_restart_source,
                store_completed_source_fn=store_completed_source,
                should_cache_completed_source_fn=should_cache_completed_source,
                log_event_fn=log_event,
            )


def drain_preparation_events(*, reset_run_state, set_processing_status, finalize_processing_status, push_activity) -> None:
    event_queue = get_preparation_event_queue()
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
            apply_preparation_complete(
                prepared_run_context=event.prepared_run_context,
                upload_marker=event.upload_marker,
                reset_run_state_fn=reset_run_state,
            )
            finalize_processing_status(
                "Документ подготовлен",
                "",
                1.0,
                "completed",
            )
        elif isinstance(event, PreparationFailedEvent):
            apply_preparation_failure(
                upload_marker=event.upload_marker,
                error_message=event.error_message,
                error_details=event.error_details,
            )
            finalize_processing_status(
                "Ошибка подготовки",
                event.error_message,
                1.0,
                "error",
            )
            push_activity("Не удалось прочитать и проанализировать документ.")


def preparation_worker_is_active() -> bool:
    worker = get_preparation_worker()
    return worker is not None and worker.is_alive()


def processing_worker_is_active() -> bool:
    worker = get_processing_worker()
    return worker is not None and worker.is_alive()


def request_processing_stop() -> None:
    request_processing_stop_via_state()


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
    processing_operation: str = "edit",
    source_language: str = "en",
    target_language: str = "ru",
) -> None:
    previous_restart_source = get_restart_source()
    restart_session_id = str(st.session_state.get("restart_session_id", ""))
    reset_run_state(preserve_preparation=True)
    try:
        set_restart_source(store_restart_source(
            session_id=restart_session_id,
            source_name=uploaded_filename,
            source_token=uploaded_token,
            source_bytes=source_bytes,
            previous_restart_source=previous_restart_source,
        ))
    except OSError as exc:
        set_restart_source(None)
        log_event(
            logging.WARNING,
            "restart_source_store_failed",
            "Не удалось сохранить временный restart source; продолжаю обработку без возможности restart без повторной загрузки.",
            filename=uploaded_filename,
            source_token=uploaded_token,
            error_message=str(exc),
        )
        push_activity("Не удалось сохранить временный файл для restart. Повторный запуск без загрузки файла будет недоступен.")

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
            "processing_operation": processing_operation,
            "source_language": source_language,
            "target_language": target_language,
        },
        daemon=True,
    )
    apply_processing_start(
        uploaded_filename=uploaded_filename,
        uploaded_token=uploaded_token,
        image_mode=image_mode,
        processing_operation=processing_operation,
        audiobook_postprocess_enabled=bool(app_config.get("audiobook_postprocess_enabled", False)),
        worker=worker,
        event_queue=processing_events,
        stop_event=stop_event,
    )
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
    processing_operation: str = "edit",
    app_config: dict[str, object] | None = None,
) -> None:
    reset_run_state(keep_restart_source=False)
    mark_preparation_started(upload_marker)

    preparation_events = queue.Queue()
    runtime = BackgroundRuntime(preparation_events, threading.Event())

    push_activity("Файл получен сервером. Запускаю анализ документа.")
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
                processing_operation=processing_operation,
                app_config=app_config,
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
    set_preparation_runtime(worker=worker, event_queue=preparation_events)
    worker.start()
