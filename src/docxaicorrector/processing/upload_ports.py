"""UI-free upload/read-stage ports (F3).

Holds the pure, Streamlit-free upload + read-stage helpers that the
``document``/``processing`` core needs so importing that core never transitively
loads Streamlit. This module MUST NOT import ``streamlit`` (directly or
transitively) and MUST NOT import back into ``processing_runtime`` at module load
time — ``processing_runtime`` re-exports these names for backward compatibility.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol, runtime_checkable

from docxaicorrector.core.logger import log_event


_DEFAULT_UPLOADED_FILENAME = "document.docx"


def _looks_like_runtime_object_repr(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("<") and " object at 0x" in normalized and normalized.endswith(">")


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
    source_format: str = "docx"
    conversion_backend: str | None = None


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


def build_in_memory_uploaded_file(*, source_name: str, source_bytes: bytes):
    uploaded_file = InMemoryUploadedFile(source_bytes)
    uploaded_file.name = source_name
    uploaded_file.size = len(source_bytes)
    return uploaded_file


class HeartbeatBeacon:
    """Periodically re-emits a progress event during a long blocking call.

    Designed to wrap subprocess calls (LibreOffice) and synchronous network
    calls (OpenAI) where we cannot inject native progress hooks. The beacon
    runs a daemon thread that ticks every ``interval_seconds`` and invokes
    ``progress_callback`` with the current elapsed seconds substituted into
    ``detail_template`` (``{elapsed}`` placeholder). The beacon is a no-op
    when ``progress_callback`` is ``None``.

    The beacon is reentrant via the context manager and never raises out of
    the worker: any exception in ``progress_callback`` stops the beacon.
    """

    def __init__(
        self,
        progress_callback,
        *,
        stage: str,
        detail_template: str,
        progress: float,
        metrics: dict | None = None,
        interval_seconds: float = 2.0,
    ) -> None:
        self._progress_callback = progress_callback
        self._stage = stage
        self._detail_template = detail_template
        self._progress = progress
        self._metrics = dict(metrics or {})
        self._interval = max(0.05, float(interval_seconds))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = 0.0
        self._callback_failure_logged = False

    def __enter__(self) -> "HeartbeatBeacon":
        if self._progress_callback is None:
            return self
        self._started_at = time.monotonic()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="docxai-heartbeat",
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=self._interval + 0.5)
        return False

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            elapsed = max(0, int(time.monotonic() - self._started_at))
            try:
                detail = self._detail_template.format(elapsed=elapsed)
            except (KeyError, IndexError, ValueError):
                detail = self._detail_template
            try:
                self._progress_callback(
                    stage=self._stage,
                    detail=detail,
                    progress=self._progress,
                    metrics=dict(self._metrics),
                )
            except Exception:
                if not self._callback_failure_logged:
                    self._callback_failure_logged = True
                    log_event(
                        logging.WARNING,
                        "heartbeat_callback_failed",
                        "Heartbeat progress callback failed; periodic heartbeat updates were disabled for this operation.",
                        stage=self._stage,
                        detail_template=self._detail_template,
                        interval_seconds=self._interval,
                    )
                # Heartbeat must never abort the worker.
                return
