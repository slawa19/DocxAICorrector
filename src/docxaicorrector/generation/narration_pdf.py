"""Narration text -> PDF through LibreOffice (spec 072, FR-005).

``export_narration_pdf`` never raises (except ``BaseException``): every failure is a
``NarrationPdfOutcome`` with a reason from the closed set ``NARRATION_PDF_UNAVAILABLE_REASONS``.
Each conversion gets a NEW LibreOffice profile in the same temporary directory as the input and
output, because a shared profile breaks parallel conversions (research R7). Detail strings carry
only the tail of process errors, never book text.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from docxaicorrector.runtime.external_process import find_soffice_binary, run_completed_process

NARRATION_PDF_TIMEOUT_SECONDS = 60
NARRATION_PDF_FILTER = 'pdf:writer_pdf_Export:{"ExportBookmarks":{"type":"boolean","value":"true"}}'

NARRATION_PDF_UNAVAILABLE_REASONS = (
    "docx_not_built",  # narration DOCX was not built, so PDF is not attempted
    "soffice_not_found",  # find_soffice_binary() -> None
    "timeout",  # helper RuntimeError about exceeded time (process group terminated)
    "failed",  # non-zero exit code / OSError on launch
    "missing_output",  # process finished, <stem>.tts.pdf is absent
    "empty_output",  # file present, 0 bytes
    "not_pdf",  # file does not start with b"%PDF-"
)

_DETAIL_LIMIT = 300
_TIMEOUT_MARKER = "Превышено время ожидания"
_PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class NarrationPdfOutcome:
    pdf_bytes: bytes | None
    reason: str | None  # None <=> pdf_bytes is non-empty
    seconds: float  # wall time of the conversion (0.0 if it was not started)
    detail: str  # <= 300 chars of stderr/message tail; never book text


def _failure(reason: str, *, seconds: float, detail: str = "") -> NarrationPdfOutcome:
    return NarrationPdfOutcome(pdf_bytes=None, reason=reason, seconds=seconds, detail=detail[-_DETAIL_LIMIT:])


def export_narration_pdf(
    docx_bytes: bytes,
    *,
    stem: str,
    timeout_seconds: int = NARRATION_PDF_TIMEOUT_SECONDS,
    runner: Callable[..., object] = run_completed_process,
    find_soffice: Callable[[], str | None] = find_soffice_binary,
) -> NarrationPdfOutcome:
    soffice = find_soffice()
    if not soffice:
        return _failure("soffice_not_found", seconds=0.0)

    with tempfile.TemporaryDirectory(prefix="docxaicorrector_tts_pdf_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / f"{stem}.tts.docx"
        output_path = temp_dir / f"{stem}.tts.pdf"
        profile_uri = (temp_dir / "lo_profile").as_uri()
        input_path.write_bytes(docx_bytes)

        command = [
            soffice,
            f"-env:UserInstallation={profile_uri}",
            "--headless",
            "--norestore",
            "--convert-to",
            NARRATION_PDF_FILTER,
            "--outdir",
            str(temp_dir),
            str(input_path),
        ]
        started = time.perf_counter()
        try:
            runner(
                command,
                error_message="Не удалось сконвертировать текст озвучки в PDF.",
                cleanup_process_group=True,
                timeout_seconds=timeout_seconds,
            )
        except (RuntimeError, OSError) as exc:
            seconds = time.perf_counter() - started
            message = str(exc)
            reason = "timeout" if _TIMEOUT_MARKER in message else "failed"
            return _failure(reason, seconds=seconds, detail=message)
        seconds = time.perf_counter() - started

        if not output_path.is_file():
            return _failure("missing_output", seconds=seconds)
        try:
            pdf_bytes = output_path.read_bytes()
        except OSError as exc:
            return _failure("failed", seconds=seconds, detail=str(exc))
        if not pdf_bytes:
            return _failure("empty_output", seconds=seconds)
        if not pdf_bytes.startswith(_PDF_MAGIC):
            return _failure("not_pdf", seconds=seconds)
        return NarrationPdfOutcome(pdf_bytes=pdf_bytes, reason=None, seconds=seconds, detail="")
