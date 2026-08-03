from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict
from pathlib import Path

from docxaicorrector.core.logger import log_event
from docxaicorrector.core.models import LayoutArtifactCleanupDecision, LayoutArtifactCleanupReport, ParagraphUnit
from docxaicorrector.runtime.artifact_retention import prune_artifact_dir
from docxaicorrector.structure.page_furniture_detection import detect_page_furniture_hits


DEFAULT_MIN_REPEAT_COUNT = 3
DEFAULT_MAX_REPEATED_TEXT_CHARS = 80
DEFAULT_MAX_REPEATED_WORD_COUNT = 12
TITLE_FIRST_PARAGRAPH_SCAN_LIMIT = 12
PAGE_NUMBER_MAX_CHARS = 20

PAGE_NUMBER_PATTERNS = (
    re.compile(r"^\d{1,4}$", re.IGNORECASE),
    re.compile(r"^[\-\u2013\u2014]\s*\d{1,4}\s*[\-\u2013\u2014]$", re.IGNORECASE),
    re.compile(r"^(?:page|p\.)\s+\d{1,4}$", re.IGNORECASE),
    re.compile(r"^(?:стр\.|с\.)\s*\d{1,4}$", re.IGNORECASE),
    re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$", re.IGNORECASE),
    re.compile(r"^\d{1,4}\s+of\s+\d{1,4}$", re.IGNORECASE),
)
URL_OR_EMAIL_PATTERN = re.compile(r"(?:https?://|www\.|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b)", re.IGNORECASE)
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MARKDOWN_WRAPPER_PATTERN = re.compile(r"^(?:[*_`~]+)(.*?)(?:[*_`~]+)$")
WORD_PATTERN = re.compile(r"\w+", re.UNICODE)
BOILERPLATE_TOKENS = {
    "confidential",
    "draft",
    "copyright",
    "all rights reserved",
    "конфиденциально",
    "черновик",
    "все права защищены",
}
PROTECTED_ROLES = {"heading", "caption", "list", "table", "image"}
# Page furniture — a scanner stamp, a classification marking, a running header — recurs
# once per PAGE. Measured over a whole document that means it reappears every few
# paragraphs. Section structure (a per-chapter "Footnotes" heading, a part divider)
# recurs at chapter scale, an order of magnitude further apart. The three constants below
# are that cadence boundary; they key on WHERE the block repeats and HOW OFTEN, never on
# what it says (Constitution VII).
#
# Cadence ALONE is not enough to condemn a block, and no value of these constants would
# make it enough. A play whose speaker label recurs every few paragraphs, a poem's
# refrain, a textbook's repeated exercise heading all sit squarely inside this cadence
# band by their nature, not by coincidence — see ``_document_admits_page_furniture`` for
# the provenance precondition that separates them from a stamp.
PAGE_FURNITURE_MAX_MEAN_PARAGRAPH_GAP = 40
PAGE_FURNITURE_MIN_DOCUMENT_SPAN_RATIO = 0.5
PAGE_FURNITURE_MIN_REPEAT_COUNT = 6
# Blast-radius bound. Furniture is a thin overlay on a document — the stamp measured on
# the OCR corpus is 167 of 2069 paragraphs, 8%. A block that IS a fifth of
# the document is far more likely to be content whose repetition is the point (a refrain,
# a recurring speaker label in a play), and no cadence heuristic should silently delete
# that much text. Above this share the block is kept, whatever its cadence.
PAGE_FURNITURE_MAX_DOCUMENT_SHARE = 0.2
# Structural containers, not text blocks: a table or image placeholder is never furniture.
PAGE_FURNITURE_EXCLUDED_ROLES = {"table", "image"}
# An image anchor must never be dropped as a side effect of a text rule.
IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\[\[(?:DOCX_)?IMAGE_[A-Za-z0-9_]+\]\]", re.IGNORECASE)
PROTECTED_STRUCTURAL_ROLES = {"toc_header", "toc_entry", "epigraph", "attribution", "dedication"}
TERMINAL_PUNCTUATION = (".", "!", "?", "\u2026")
_EXTRACTION_ARTIFACT_PATTERN = re.compile(
    r"^(?:\[\[DOCX_[A-Za-z0-9_]+\]\]|\[\[IMAGE_[A-Za-z0-9_]+\]\]|\[\[DOCX_IMAGE_[A-Za-z0-9_]+\]\]|</?placeholder>|---+|===+)$",
    re.IGNORECASE,
)
_SUPPORTED_CLEANUP_MODES = {"flag", "remove"}


def clean_paragraph_layout_artifacts(
    paragraphs: list[ParagraphUnit],
    *,
    enabled: bool = True,
    min_repeat_count: int = DEFAULT_MIN_REPEAT_COUNT,
    max_repeated_text_chars: int = DEFAULT_MAX_REPEATED_TEXT_CHARS,
    cleanup_mode: str = "flag",
    structure_recovery_enabled: bool = False,
    structure_recovery_mode: str = "legacy",
    is_scan_origin: bool = False,
) -> tuple[list[ParagraphUnit], LayoutArtifactCleanupReport]:
    resolved_mode = str(cleanup_mode or "flag").strip().lower() or "flag"
    if resolved_mode not in _SUPPORTED_CLEANUP_MODES:
        resolved_mode = "flag"
    if not enabled:
        report = _empty_report(
            paragraphs,
            cleanup_applied=False,
            skipped_reason="disabled",
            cleanup_mode=resolved_mode,
        )
        _log_cleanup_outcome(report)
        return paragraphs, report

    try:
        signal_only = resolved_mode != "remove"
        return _clean_paragraph_layout_artifacts(
            paragraphs,
            min_repeat_count=max(2, int(min_repeat_count or DEFAULT_MIN_REPEAT_COUNT)),
            max_repeated_text_chars=max(1, int(max_repeated_text_chars or DEFAULT_MAX_REPEATED_TEXT_CHARS)),
            signal_only=signal_only,
            is_scan_origin=bool(is_scan_origin),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        report = _empty_report(
            paragraphs,
            cleanup_applied=False,
            skipped_reason="cleanup_failed",
            error_code="unexpected_paragraph_shape",
            cleanup_mode=resolved_mode,
        )
        _log_cleanup_outcome(report, error_message=str(exc))
        return paragraphs, report
    except Exception as exc:
        report = _empty_report(
            paragraphs,
            cleanup_applied=False,
            skipped_reason="cleanup_failed",
            error_code="cleanup_runtime_error",
            cleanup_mode=resolved_mode,
        )
        _log_cleanup_outcome(report, error_message=str(exc))
        return paragraphs, report


def _clean_paragraph_layout_artifacts(
    paragraphs: list[ParagraphUnit],
    *,
    min_repeat_count: int,
    max_repeated_text_chars: int,
    signal_only: bool,
    is_scan_origin: bool = False,
) -> tuple[list[ParagraphUnit], LayoutArtifactCleanupReport]:
    normalized_by_index: dict[int, str] = {}
    frequency: dict[str, int] = {}
    candidate_indexes: set[int] = set()
    title_fingerprints = _collect_title_fingerprints(paragraphs)

    for index, paragraph in enumerate(paragraphs):
        normalized_by_index[index] = normalize_layout_artifact_text(str(paragraph.text or ""))

    page_furniture_fingerprints = _collect_page_cadence_furniture_fingerprints(
        paragraphs,
        normalized_by_index=normalized_by_index,
        max_repeated_text_chars=max_repeated_text_chars,
        # The operator's repeat threshold can only make this stricter, never looser: this
        # rule deletes, so it must not be tunable below its own floor.
        min_repeat_count=max(min_repeat_count, PAGE_FURNITURE_MIN_REPEAT_COUNT),
        is_scan_origin=is_scan_origin,
    )

    for index, paragraph in enumerate(paragraphs):
        normalized = normalized_by_index[index]
        if _is_repeated_artifact_candidate(
            paragraph,
            normalized_text=normalized,
            max_repeated_text_chars=max_repeated_text_chars,
            title_fingerprints=title_fingerprints,
        ):
            candidate_indexes.add(index)
            frequency[normalized] = frequency.get(normalized, 0) + 1

    cleaned: list[ParagraphUnit] = []
    decisions: list[LayoutArtifactCleanupDecision] = []
    removed_page_numbers = 0
    removed_repeated = 0
    removed_empty = 0
    removed_page_furniture = 0
    flagged_page_numbers = 0
    flagged_repeated = 0
    flagged_empty = 0

    for index, paragraph in enumerate(paragraphs):
        normalized = normalized_by_index[index]
        repeat_count = frequency.get(normalized, 1)
        reason = "keep"
        action = "keep"
        paragraph.is_likely_page_number = False
        paragraph.is_repeated_across_pages = False

        if normalized and normalized in page_furniture_fingerprints:
            # Targeted drop: page-cadence furniture is removed in BOTH modes. Flag mode
            # exists so that UNCERTAIN structure decisions stay visible to AI-first
            # structure recovery; a block recurring at page cadence across the whole
            # document is not a structure decision, and leaving it in means it is
            # translated once per page.
            action = "remove"
            reason = "repeated_page_furniture"
            paragraph.is_repeated_across_pages = True
            removed_page_furniture += 1
            removed_repeated += 1
        elif _is_protected(paragraph):
            action = "keep"
            reason = "protected_role_keep"
        elif not str(paragraph.text or "").strip():
            action = "flag" if signal_only else "remove"
            reason = "empty_or_whitespace"
            if signal_only:
                flagged_empty += 1
            else:
                removed_empty += 1
        elif _is_blank_page_marker_artifact(paragraph):
            action = "flag" if signal_only else "remove"
            reason = "blank_page_marker"
            if signal_only:
                flagged_repeated += 1
            else:
                removed_repeated += 1
        elif _is_extraction_artifact(paragraph):
            action = "flag" if signal_only else "remove"
            reason = "extraction_artifact"
            if signal_only:
                flagged_repeated += 1
            else:
                removed_repeated += 1
        elif _is_page_number_artifact(paragraph):
            action = "flag" if signal_only else "remove"
            reason = "page_number_pattern"
            paragraph.is_likely_page_number = True
            if signal_only:
                flagged_page_numbers += 1
            else:
                removed_page_numbers += 1
        elif index in candidate_indexes and repeat_count >= min_repeat_count:
            repeated_reason = _repeated_artifact_reason(
                paragraph,
                normalized_text=normalized,
                repeat_count=repeat_count,
                title_fingerprints=title_fingerprints,
            )
            if repeated_reason is not None:
                action = "flag" if signal_only else "remove"
                reason = repeated_reason
                paragraph.is_repeated_across_pages = True
                if signal_only:
                    flagged_repeated += 1
                else:
                    removed_repeated += 1
        elif index in candidate_indexes and repeat_count > 1:
            reason = "uncertain_repeated_artifact"

        decisions.append(
            _build_decision(
                paragraph,
                action=action,
                reason=reason,
                normalized_text=normalized,
                repeat_count=repeat_count,
            )
        )
        if action == "keep" or (signal_only and action == "flag"):
            cleaned.append(paragraph)

    report = LayoutArtifactCleanupReport(
        original_paragraph_count=len(paragraphs),
        cleaned_paragraph_count=len(cleaned),
        removed_paragraph_count=len(paragraphs) - len(cleaned),
        removed_page_number_count=removed_page_numbers,
        removed_repeated_artifact_count=removed_repeated,
        removed_empty_or_whitespace_count=removed_empty,
        decisions=decisions,
        cleanup_applied=True,
        cleanup_mode="flag" if signal_only else "remove",
        flagged_page_number_count=flagged_page_numbers,
        flagged_repeated_artifact_count=flagged_repeated,
        flagged_empty_or_whitespace_count=flagged_empty,
        removed_page_furniture_count=removed_page_furniture,
    )
    _log_cleanup_outcome(report)
    return cleaned, report


def normalize_layout_artifact_text(text: str) -> str:
    normalized = MARKDOWN_LINK_PATTERN.sub(r"\1 \2", text or "")
    normalized = normalized.replace("\u2018", "'").replace("\u2019", "'")
    normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    wrapper_match = MARKDOWN_WRAPPER_PATTERN.match(normalized)
    if wrapper_match is not None:
        normalized = wrapper_match.group(1).strip()
    normalized = normalized.strip(" \t\r\n-_*`~|:;,.()[]{}<>")
    return re.sub(r"\s+", " ", normalized).casefold()


def _is_page_number_artifact(paragraph: ParagraphUnit) -> bool:
    text = str(paragraph.text or "").strip()
    if len(text) > PAGE_NUMBER_MAX_CHARS:
        return False
    if not text:
        return False
    if getattr(paragraph, "role", "body") != "body":
        return False
    if getattr(paragraph, "structural_role", "body") not in {"body"}:
        return False
    if _has_list_metadata(paragraph):
        return False
    return any(pattern.match(text) for pattern in PAGE_NUMBER_PATTERNS)


def _is_blank_page_marker_artifact(paragraph: ParagraphUnit) -> bool:
    text = str(paragraph.text or "").strip()
    if not text or _is_protected(paragraph):
        return False
    hits = detect_page_furniture_hits(text)
    if not hits:
        return False
    return any(
        hit.kind in {"blank_page_marker", "intentionally_blank_marker"}
        and hit.start == 0
        and hit.end == len(hit.normalized_text)
        for hit in hits
    )


def _is_extraction_artifact(paragraph: ParagraphUnit) -> bool:
    text = str(paragraph.text or "").strip()
    if not text or _is_protected(paragraph):
        return False
    if len(text) > DEFAULT_MAX_REPEATED_TEXT_CHARS:
        return False
    return _EXTRACTION_ARTIFACT_PATTERN.fullmatch(text) is not None


def _is_repeated_artifact_candidate(
    paragraph: ParagraphUnit,
    *,
    normalized_text: str,
    max_repeated_text_chars: int,
    title_fingerprints: set[str] | None = None,
) -> bool:
    if not normalized_text:
        return False
    if _is_protected(paragraph):
        return False
    if getattr(paragraph, "role", "body") != "body":
        return False
    if getattr(paragraph, "structural_role", "body") != "body":
        return False
    if _has_list_metadata(paragraph):
        return False
    if len(normalized_text) > max_repeated_text_chars:
        return False
    if len(WORD_PATTERN.findall(normalized_text)) > DEFAULT_MAX_REPEATED_WORD_COUNT:
        return False
    if terminal_sentence_like(str(paragraph.text or "")) and normalized_text not in (title_fingerprints or set()):
        return False
    return True


def _document_admits_page_furniture(*, is_scan_origin: bool) -> bool:
    """Can page furniture reach the body paragraph stream of THIS document at all?

    Page furniture belongs to the PAGE, not to the text: a scanner stamp, a
    classification marking, a running header. In a document authored from structure, those
    live in the ``w:hdr``/``w:ftr`` parts, which extraction never reads — so they cannot
    appear among body paragraphs. They enter the body stream only when a page IMAGE was
    flattened into text, i.e. when the source is an OCR scan. That is the provenance
    ``classify_document_scan_origin`` establishes, from the document's own layout, before
    a single paragraph is inspected.

    This precondition exists because cadence cannot carry the decision on its own. A play
    whose speaker label recurs every few paragraphs clears every cadence threshold in this
    module with room to spare (a 1000-paragraph play with a label every 6 paragraphs:
    ~167 repeats, 16.7% share, full span, mean gap 6) and would be silently deleted,
    delivering dialogue with nobody speaking it. Raising the thresholds to exclude that
    one example would be fitting numbers to a book, which Constitution VII forbids; asking
    whether the document is even the KIND that can contain page furniture is a provenance
    question with a real answer.

    The cost is coverage, deliberately: a stamp burned into an authored document is no
    longer removed. Not deleting a play's dialogue labels is worth more than removing a
    stamp that this rule was never able to tell apart from them.
    """

    return bool(is_scan_origin)


def _collect_page_cadence_furniture_fingerprints(
    paragraphs: list[ParagraphUnit],
    *,
    normalized_by_index: dict[int, str],
    max_repeated_text_chars: int,
    min_repeat_count: int,
    is_scan_origin: bool = False,
) -> set[str]:
    """Normalized blocks that repeat at PAGE cadence across the whole document.

    Applies only to documents whose provenance admits page furniture at all — see
    ``_document_admits_page_furniture``. Within those, the block is identified by WHERE and
    HOW OFTEN it repeats, never by what it says. A stamp, a classification marking or a
    running header sits in the same slot on every page, so across the document it
    reappears every few paragraphs and its occurrences span the document end to end.
    Section structure that legitimately repeats — a per-chapter "Footnotes" heading, a part
    divider echoed in the table of contents — repeats at chapter cadence, an order of
    magnitude further apart, and is therefore not matched.

    Deliberately blind to ``role`` and ``layout_origin``: an OCR stamp is imported
    sometimes as a textbox, sometimes as a plain paragraph, and a short all-caps stamp is
    routinely mis-promoted to ``role="heading"`` by the import heuristics. Which of those
    accidents a given occurrence got is not evidence about the block. (Measured on the OCR
    corpus, the 167 stamp occurrences carry six different role/origin combinations and six
    different font sizes — which is also why this rule cannot be replaced by deferring to
    the protected-role check: 145 of those 167 occurrences hold a protected role.)
    """
    if not _document_admits_page_furniture(is_scan_origin=is_scan_origin):
        return set()
    if len(paragraphs) < min_repeat_count:
        return set()

    positions_by_fingerprint: dict[str, list[int]] = {}
    for index, paragraph in enumerate(paragraphs):
        normalized = normalized_by_index.get(index, "")
        if not _is_page_cadence_candidate(
            paragraph,
            normalized_text=normalized,
            max_repeated_text_chars=max_repeated_text_chars,
        ):
            continue
        positions_by_fingerprint.setdefault(normalized, []).append(index)

    document_span = max(1, len(paragraphs) - 1)
    fingerprints: set[str] = set()
    for normalized, positions in positions_by_fingerprint.items():
        if len(positions) < min_repeat_count:
            continue
        if len(positions) / len(paragraphs) > PAGE_FURNITURE_MAX_DOCUMENT_SHARE:
            continue
        occupied_span = positions[-1] - positions[0]
        if occupied_span / document_span < PAGE_FURNITURE_MIN_DOCUMENT_SPAN_RATIO:
            continue
        mean_gap = occupied_span / (len(positions) - 1)
        if mean_gap > PAGE_FURNITURE_MAX_MEAN_PARAGRAPH_GAP:
            continue
        fingerprints.add(normalized)
    return fingerprints


def _is_page_cadence_candidate(
    paragraph: ParagraphUnit,
    *,
    normalized_text: str,
    max_repeated_text_chars: int,
) -> bool:
    if not normalized_text:
        return False
    if getattr(paragraph, "role", "body") in PAGE_FURNITURE_EXCLUDED_ROLES:
        return False
    if IMAGE_PLACEHOLDER_PATTERN.search(str(paragraph.text or "")):
        return False
    if _has_list_metadata(paragraph):
        return False
    if len(normalized_text) > max_repeated_text_chars:
        return False
    if len(WORD_PATTERN.findall(normalized_text)) > DEFAULT_MAX_REPEATED_WORD_COUNT:
        return False
    if terminal_sentence_like(str(paragraph.text or "")):
        return False
    return True


def _repeated_artifact_reason(
    paragraph: ParagraphUnit,
    *,
    normalized_text: str,
    repeat_count: int,
    title_fingerprints: set[str],
) -> str | None:
    text = str(paragraph.text or "")
    if URL_OR_EMAIL_PATTERN.search(text):
        return "repeated_url_footer"
    if normalized_text in BOILERPLATE_TOKENS:
        return "repeated_boilerplate_token"
    if normalized_text in title_fingerprints:
        return "repeated_title_header"
    if getattr(paragraph, "layout_origin", "paragraph") == "textbox" and _is_short_running_header_candidate(normalized_text) and repeat_count >= DEFAULT_MIN_REPEAT_COUNT:
        return "repeated_running_header"
    return None


def terminal_sentence_like(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    if len(stripped) <= PAGE_NUMBER_MAX_CHARS and any(pattern.match(stripped) for pattern in PAGE_NUMBER_PATTERNS):
        return False
    return stripped.endswith(TERMINAL_PUNCTUATION)


def _collect_title_fingerprints(paragraphs: list[ParagraphUnit]) -> set[str]:
    fingerprints: set[str] = set()
    for paragraph in paragraphs[:TITLE_FIRST_PARAGRAPH_SCAN_LIMIT]:
        text = normalize_layout_artifact_text(str(paragraph.text or ""))
        if not text:
            continue
        if getattr(paragraph, "role", "body") == "heading" or getattr(paragraph, "heading_level", None) is not None:
            fingerprints.add(text)
    return fingerprints


def _is_short_running_header_candidate(normalized_text: str) -> bool:
    words = WORD_PATTERN.findall(normalized_text)
    return 1 <= len(words) <= 6


def _is_protected(paragraph: ParagraphUnit) -> bool:
    return getattr(paragraph, "role", "body") in PROTECTED_ROLES or getattr(paragraph, "structural_role", "body") in PROTECTED_STRUCTURAL_ROLES


def _has_list_metadata(paragraph: ParagraphUnit) -> bool:
    return bool(
        getattr(paragraph, "list_kind", None)
        or getattr(paragraph, "list_num_id", None)
        or getattr(paragraph, "list_abstract_num_id", None)
    )


def _build_decision(
    paragraph: ParagraphUnit,
    *,
    action: str,
    reason: str,
    normalized_text: str,
    repeat_count: int,
) -> LayoutArtifactCleanupDecision:
    return LayoutArtifactCleanupDecision(
        original_source_index=int(getattr(paragraph, "source_index", -1)),
        original_paragraph_id=str(getattr(paragraph, "paragraph_id", "") or ""),
        origin_raw_indexes=tuple(int(index) for index in (getattr(paragraph, "origin_raw_indexes", []) or [])),
        text_preview=str(getattr(paragraph, "text", "") or "")[:120],
        action=action,
        reason=reason,
        confidence=_decision_confidence(action=action, reason=reason),
        normalized_text=normalized_text,
        repeat_count=repeat_count,
        page_number=getattr(paragraph, "page_number", None),
        layout_origin=str(getattr(paragraph, "layout_origin", "paragraph") or "paragraph"),
    )


def _decision_confidence(*, action: str, reason: str) -> str:
    if reason == "uncertain_repeated_artifact":
        return "low"
    if action not in {"remove", "flag"}:
        return "medium"
    if reason in {"repeated_title_header", "repeated_running_header"}:
        return "medium"
    return "high"


def _empty_report(
    paragraphs: list[ParagraphUnit],
    *,
    cleanup_applied: bool,
    skipped_reason: str | None,
    error_code: str | None = None,
    cleanup_mode: str = "remove",
) -> LayoutArtifactCleanupReport:
    return LayoutArtifactCleanupReport(
        original_paragraph_count=len(paragraphs),
        cleaned_paragraph_count=len(paragraphs),
        removed_paragraph_count=0,
        removed_page_number_count=0,
        removed_repeated_artifact_count=0,
        removed_empty_or_whitespace_count=0,
        decisions=[],
        cleanup_applied=cleanup_applied,
        skipped_reason=skipped_reason,
        error_code=error_code,
        cleanup_mode=cleanup_mode,
    )


def write_layout_cleanup_report_artifact(
    *,
    source_name: str,
    source_bytes: bytes,
    report: LayoutArtifactCleanupReport,
    target_dir: Path,
    max_age_seconds: int,
    max_count: int,
) -> str | None:
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        source_hash = hashlib.sha1(source_bytes).hexdigest()[:8]
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source_name or "document.docx").strip("_") or "document.docx"
        artifact_path = target_dir / f"{safe_name}_{source_hash}.json"
        payload = {
            "version": 1,
            "source_file": source_name,
            "source_hash": source_hash,
            "original_paragraph_count": report.original_paragraph_count,
            "cleaned_paragraph_count": report.cleaned_paragraph_count,
            "cleanup_mode": report.cleanup_mode,
            "removed_paragraph_count": report.removed_paragraph_count,
            "removed_page_number_count": report.removed_page_number_count,
            "removed_repeated_artifact_count": report.removed_repeated_artifact_count,
            "removed_empty_or_whitespace_count": report.removed_empty_or_whitespace_count,
            "flagged_page_number_count": report.flagged_page_number_count,
            "flagged_repeated_artifact_count": report.flagged_repeated_artifact_count,
            "flagged_empty_or_whitespace_count": report.flagged_empty_or_whitespace_count,
            "removed_page_furniture_count": report.removed_page_furniture_count,
            "cleanup_applied": report.cleanup_applied,
            "skipped_reason": report.skipped_reason,
            "error_code": report.error_code,
            "decisions": [asdict(decision) for decision in report.decisions],
        }
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_artifact_dir(
            target_dir=target_dir,
            max_age_seconds=max_age_seconds,
            max_count=max_count,
        )
        return str(artifact_path)
    except Exception:
        return None


def _log_cleanup_outcome(report: LayoutArtifactCleanupReport, *, error_message: str | None = None) -> None:
    log_event(
        logging.INFO if report.error_code is None else logging.WARNING,
        "layout_artifact_cleanup_outcome",
        "Завершена очистка layout artifacts документа.",
        layout_cleanup_enabled=report.skipped_reason != "disabled",
        layout_cleanup_applied=report.cleanup_applied,
        layout_cleanup_mode=report.cleanup_mode,
        layout_cleanup_removed_count=report.removed_paragraph_count,
        layout_cleanup_page_number_count=report.removed_page_number_count,
        layout_cleanup_repeated_artifact_count=report.removed_repeated_artifact_count,
        layout_cleanup_empty_or_whitespace_count=report.removed_empty_or_whitespace_count,
        layout_cleanup_flagged_page_number_count=report.flagged_page_number_count,
        layout_cleanup_flagged_repeated_artifact_count=report.flagged_repeated_artifact_count,
        layout_cleanup_flagged_empty_or_whitespace_count=report.flagged_empty_or_whitespace_count,
        layout_cleanup_removed_page_furniture_count=report.removed_page_furniture_count,
        layout_cleanup_skipped_reason=report.skipped_reason,
        layout_cleanup_error_code=report.error_code,
        error_message=error_message,
    )
