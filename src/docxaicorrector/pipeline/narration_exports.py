"""Spec 072 FR-003 (в), FR-005, FR-006, FR-007: the narration DOCX and PDF of an audiobook run.

One orchestrator for the late phase (research R9): the narration groups of the ``.tts.txt`` assembly
(``ProcessingState.narration_groups``) -> the document plan (``pipeline.narration_document``, FR-003 / FR-006) -> the
DOCX (``generation.narration_docx``, FR-004) -> the PDF (``generation.narration_pdf``, FR-005). A DOCX that was not
built means no PDF attempt (reason ``docx_not_built``).

Nothing here blocks delivery (Anti-regression 3): a renderer failure is an ERROR event and no DOCX, an unavailable PDF
is a WARNING event with its reason, an exceeded Studio limit is an advisory WARNING and a result notice; the book is
delivered with what was built. The events carry ids, numbers and reason codes only, never paragraph text
(LOGGING §1.5). The renderer and the PDF converter are looked up on this module at call time, so a test can replace
them here (research R14: CI has no LibreOffice).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from docxaicorrector.generation.narration_docx import render_narration_docx
from docxaicorrector.generation.narration_pdf import (
    NARRATION_PDF_TIMEOUT_SECONDS,
    NarrationPdfOutcome,
    export_narration_pdf,
)
from docxaicorrector.pipeline.narration_document import (
    STUDIO_LIMIT_CHAPTER_PARAGRAPHS,
    STUDIO_LIMIT_CHAPTERS,
    STUDIO_LIMIT_PARAGRAPH_CHARS,
    STUDIO_MAX_CHAPTER_PARAGRAPHS,
    STUDIO_MAX_CHAPTERS,
    STUDIO_MAX_PARAGRAPH_CHARS,
    NarrationDocumentPlan,
    NarrationGroupLike,
    build_narration_document_plan,
)

NARRATION_DOCX_UNAVAILABLE_RENDER_FAILED = "render_failed"
NARRATION_PDF_NOT_ATTEMPTED_REASON = "docx_not_built"
NARRATION_DOCX_STATUS_BUILT = "built"
NARRATION_DOCX_STATUS_FAILED = "failed"
NARRATION_PDF_STATUS_BUILT = "built"
NARRATION_PDF_STATUS_UNAVAILABLE = "unavailable"
STUDIO_LIMITS_NOTICE_MESSAGE_KEY = "result.audiobook_studio_limits_exceeded"

_EVENT_TEXT_LIMIT = 300
_STUDIO_LIMIT_VALUES: Mapping[str, int] = {
    STUDIO_LIMIT_CHAPTERS: STUDIO_MAX_CHAPTERS,
    STUDIO_LIMIT_CHAPTER_PARAGRAPHS: STUDIO_MAX_CHAPTER_PARAGRAPHS,
    STUDIO_LIMIT_PARAGRAPH_CHARS: STUDIO_MAX_PARAGRAPH_CHARS,
}
_UNSAFE_STEM_CHARACTERS = re.compile(r"[^\w.-]+")

LogEvent = Callable[..., object]
PdfExporter = Callable[..., NarrationPdfOutcome]


@dataclass(frozen=True)
class NarrationExports:
    """What the late phase publishes about the narration DOCX and PDF of one run."""

    plan: NarrationDocumentPlan | None
    docx_bytes: bytes | None
    # The renderer's exception class when the DOCX was not built; ``None`` when it was.
    docx_error: str | None
    pdf: NarrationPdfOutcome

    @property
    def pdf_bytes(self) -> bytes | None:
        return self.pdf.pdf_bytes or None

    def state_value(self) -> dict[str, object]:
        """The value of the state key ``latest_narration_exports`` (data-model §5, contracts/state-bundle.md)."""

        return {
            "docx_bytes": self.docx_bytes,
            "pdf_bytes": self.pdf_bytes,
            "docx_unavailable_reason": None if self.docx_bytes else NARRATION_DOCX_UNAVAILABLE_RENDER_FAILED,
            "pdf_unavailable_reason": None if self.pdf_bytes else self.pdf.reason,
        }

    def event_fields(self, *, artifact_paths: Mapping[str, object]) -> dict[str, object]:
        """The keys spec 072 adds to ``ui_audiobook_artifact_saved`` (contracts/events.md); every key always present."""

        plan = self.plan
        limits = plan.studio_limits if plan is not None else None
        merges = plan.heading_merges if plan is not None else ()
        docx_built = self.docx_bytes is not None
        return {
            "tts_docx_path": _optional_path(artifact_paths, "tts_docx_path"),
            "tts_pdf_path": _optional_path(artifact_paths, "tts_pdf_path"),
            "narration_docx_status": NARRATION_DOCX_STATUS_BUILT if docx_built else NARRATION_DOCX_STATUS_FAILED,
            "narration_pdf_status": NARRATION_PDF_STATUS_BUILT if self.pdf_bytes else NARRATION_PDF_STATUS_UNAVAILABLE,
            "narration_pdf_unavailable_reason": None if self.pdf_bytes else self.pdf.reason,
            "narration_pdf_seconds": round(float(self.pdf.seconds), 3),
            "chapter_heading_level": plan.chapter_level if plan is not None else None,
            "heading_levels_present": list(plan.heading_levels_present) if plan is not None else [],
            "heading1_count": limits.heading1_count if limits is not None else 0,
            "demoted_heading_count": plan.demoted_heading_count if plan is not None else 0,
            "heading_merge_count": len(merges),
            "heading_merges": [
                {"paragraph_ids": list(merge.paragraph_ids), "levels": list(merge.levels), "style": merge.style}
                for merge in merges
            ],
            "studio_max_chapter_paragraph_count": limits.max_chapter_paragraph_count if limits is not None else 0,
            "studio_max_paragraph_chars": limits.max_paragraph_chars if limits is not None else 0,
            "studio_limits_exceeded": list(limits.exceeded) if limits is not None else [],
            # Paragraphs IN the ``.tts.docx`` (after merges); no file, no paragraphs.
            "narration_docx_paragraph_count": len(plan.paragraphs) if docx_built and plan is not None else 0,
        }

    def studio_limits_notice(self) -> dict[str, object] | None:
        """The result-screen notice of FR-006 when a Studio limit is exceeded; ``None`` otherwise."""

        if self.plan is None or not self.plan.studio_limits.exceeded:
            return None
        actual = _studio_limit_actuals(self.plan)
        return {
            "kind": "narration",
            "level": "warning",
            "message_key": STUDIO_LIMITS_NOTICE_MESSAGE_KEY,
            "params": {
                "limits": ", ".join(
                    f"{name}: {actual[name]} > {_STUDIO_LIMIT_VALUES[name]}" for name in self.plan.studio_limits.exceeded
                ),
            },
        }


def build_narration_exports(
    *,
    groups: Sequence[NarrationGroupLike],
    source_name: str,
    log_event: LogEvent,
    export_pdf: PdfExporter | None = None,
) -> NarrationExports:
    """Plan -> DOCX -> PDF for one run's narration groups; logs the three spec 072 events. Never raises ``Exception``."""

    title = Path(str(source_name or "")).stem
    plan: NarrationDocumentPlan | None = None
    docx_bytes: bytes | None = None
    docx_error: str | None = None
    try:
        if not groups:
            raise ValueError("narration groups are empty")
        plan = build_narration_document_plan(groups)
        docx_bytes = render_narration_docx(plan.paragraphs, title=title) or None
        if docx_bytes is None:
            raise ValueError("narration DOCX renderer returned no bytes")
    except Exception as exc:
        docx_bytes = None
        docx_error = type(exc).__name__
        log_event(
            logging.ERROR,
            "audiobook_narration_docx_failed",
            "DOCX озвучки не собран; текст озвучки (TXT) и DOCX для проверки доставлены.",
            filename=source_name,
            error_class=docx_error,
            error_message=str(exc)[:_EVENT_TEXT_LIMIT],
            group_count=len(groups),
        )

    if docx_bytes is None:
        pdf = NarrationPdfOutcome(pdf_bytes=None, reason=NARRATION_PDF_NOT_ATTEMPTED_REASON, seconds=0.0, detail="")
    else:
        pdf = _export_pdf(export_pdf, docx_bytes, stem=_temporary_file_stem(title))

    if not pdf.pdf_bytes:
        log_event(
            logging.WARNING,
            "audiobook_narration_pdf_unavailable",
            "PDF озвучки не собран; книга доставлена без него.",
            filename=source_name,
            reason=pdf.reason,
            seconds=round(float(pdf.seconds), 3),
            detail=str(pdf.detail or "")[-_EVENT_TEXT_LIMIT:],
            timeout_seconds=NARRATION_PDF_TIMEOUT_SECONDS,
        )

    if plan is not None and plan.studio_limits.exceeded:
        limits = plan.studio_limits
        log_event(
            logging.WARNING,
            "audiobook_studio_limits_exceeded",
            "Текст озвучки превышает лимиты проекта ElevenLabs Studio; файл не изменён.",
            filename=source_name,
            review_data=True,
            advisory=True,
            exceeded=list(limits.exceeded),
            heading1_count=limits.heading1_count,
            max_chapter_paragraph_count=limits.max_chapter_paragraph_count,
            max_paragraph_chars=limits.max_paragraph_chars,
            limits=dict(_STUDIO_LIMIT_VALUES),
        )

    return NarrationExports(plan=plan, docx_bytes=docx_bytes, docx_error=docx_error, pdf=pdf)


def _export_pdf(export_pdf: PdfExporter | None, docx_bytes: bytes, *, stem: str) -> NarrationPdfOutcome:
    exporter = export_pdf if export_pdf is not None else export_narration_pdf
    try:
        outcome = exporter(docx_bytes, stem=stem)
    except Exception as exc:  # the converter promises not to raise; delivery must not depend on that promise
        return NarrationPdfOutcome(pdf_bytes=None, reason="failed", seconds=0.0, detail=str(exc)[-_EVENT_TEXT_LIMIT:])
    if outcome.pdf_bytes:
        return outcome
    return NarrationPdfOutcome(
        pdf_bytes=None,
        reason=outcome.reason or "empty_output",
        seconds=outcome.seconds,
        detail=outcome.detail,
    )


def _temporary_file_stem(title: str) -> str:
    """The name of the converter's temporary ``<stem>.tts.docx``; the PDF's title comes from the DOCX properties."""

    stem = _UNSAFE_STEM_CHARACTERS.sub("_", title).strip("._")
    return stem or "narration"


def _studio_limit_actuals(plan: NarrationDocumentPlan) -> dict[str, int]:
    limits = plan.studio_limits
    return {
        STUDIO_LIMIT_CHAPTERS: limits.heading1_count,
        STUDIO_LIMIT_CHAPTER_PARAGRAPHS: limits.max_chapter_paragraph_count,
        STUDIO_LIMIT_PARAGRAPH_CHARS: limits.max_paragraph_chars,
    }


def _optional_path(artifact_paths: Mapping[str, object], key: str) -> str | None:
    value = artifact_paths.get(key)
    return value if isinstance(value, str) and value else None


__all__ = [
    "NARRATION_DOCX_UNAVAILABLE_RENDER_FAILED",
    "NarrationExports",
    "build_narration_exports",
]
