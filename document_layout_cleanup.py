from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict
from pathlib import Path

from logger import log_event
from models import LayoutArtifactCleanupDecision, LayoutArtifactCleanupReport, ParagraphUnit
from runtime_artifact_retention import prune_artifact_dir


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
PROTECTED_STRUCTURAL_ROLES = {"toc_header", "toc_entry", "epigraph", "attribution", "dedication"}
TERMINAL_PUNCTUATION = (".", "!", "?", "\u2026")


def clean_paragraph_layout_artifacts(
    paragraphs: list[ParagraphUnit],
    *,
    enabled: bool = True,
    min_repeat_count: int = DEFAULT_MIN_REPEAT_COUNT,
    max_repeated_text_chars: int = DEFAULT_MAX_REPEATED_TEXT_CHARS,
) -> tuple[list[ParagraphUnit], LayoutArtifactCleanupReport]:
    if not enabled:
        return paragraphs, _empty_report(
            paragraphs,
            cleanup_applied=False,
            skipped_reason="disabled",
        )

    try:
        return _clean_paragraph_layout_artifacts(
            paragraphs,
            min_repeat_count=max(2, int(min_repeat_count or DEFAULT_MIN_REPEAT_COUNT)),
            max_repeated_text_chars=max(1, int(max_repeated_text_chars or DEFAULT_MAX_REPEATED_TEXT_CHARS)),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        report = _empty_report(
            paragraphs,
            cleanup_applied=False,
            skipped_reason="cleanup_failed",
            error_code="unexpected_paragraph_shape",
        )
        _log_cleanup_outcome(report, error_message=str(exc))
        return paragraphs, report
    except Exception as exc:
        report = _empty_report(
            paragraphs,
            cleanup_applied=False,
            skipped_reason="cleanup_failed",
            error_code="cleanup_runtime_error",
        )
        _log_cleanup_outcome(report, error_message=str(exc))
        return paragraphs, report


def _clean_paragraph_layout_artifacts(
    paragraphs: list[ParagraphUnit],
    *,
    min_repeat_count: int,
    max_repeated_text_chars: int,
) -> tuple[list[ParagraphUnit], LayoutArtifactCleanupReport]:
    normalized_by_index: dict[int, str] = {}
    frequency: dict[str, int] = {}
    title_fingerprints = _collect_title_fingerprints(paragraphs)

    for index, paragraph in enumerate(paragraphs):
        normalized = normalize_layout_artifact_text(str(paragraph.text or ""))
        normalized_by_index[index] = normalized
        if _is_repeated_artifact_candidate(
            paragraph,
            normalized_text=normalized,
            max_repeated_text_chars=max_repeated_text_chars,
            title_fingerprints=title_fingerprints,
        ):
            frequency[normalized] = frequency.get(normalized, 0) + 1

    cleaned: list[ParagraphUnit] = []
    decisions: list[LayoutArtifactCleanupDecision] = []
    removed_page_numbers = 0
    removed_repeated = 0
    removed_empty = 0

    for index, paragraph in enumerate(paragraphs):
        normalized = normalized_by_index[index]
        repeat_count = frequency.get(normalized, 1)
        reason = "keep"
        action = "keep"

        if _is_protected(paragraph):
            action = "keep"
            reason = "protected_role_keep"
        elif not str(paragraph.text or "").strip():
            action = "remove"
            reason = "empty_or_whitespace"
            removed_empty += 1
        elif _is_page_number_artifact(paragraph):
            action = "remove"
            reason = "page_number_pattern"
            removed_page_numbers += 1
        elif repeat_count >= min_repeat_count:
            repeated_reason = _repeated_artifact_reason(
                paragraph,
                normalized_text=normalized,
                repeat_count=repeat_count,
                title_fingerprints=title_fingerprints,
            )
            if repeated_reason is not None:
                action = "remove"
                reason = repeated_reason
                removed_repeated += 1

        decisions.append(
            _build_decision(
                paragraph,
                action=action,
                reason=reason,
                normalized_text=normalized,
                repeat_count=repeat_count,
            )
        )
        if action == "keep":
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
        confidence="high" if action == "remove" else "medium",
        normalized_text=normalized_text,
        repeat_count=repeat_count,
    )


def _empty_report(
    paragraphs: list[ParagraphUnit],
    *,
    cleanup_applied: bool,
    skipped_reason: str | None,
    error_code: str | None = None,
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
            "removed_paragraph_count": report.removed_paragraph_count,
            "removed_page_number_count": report.removed_page_number_count,
            "removed_repeated_artifact_count": report.removed_repeated_artifact_count,
            "removed_empty_or_whitespace_count": report.removed_empty_or_whitespace_count,
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
        layout_cleanup_removed_count=report.removed_paragraph_count,
        layout_cleanup_page_number_count=report.removed_page_number_count,
        layout_cleanup_repeated_artifact_count=report.removed_repeated_artifact_count,
        layout_cleanup_empty_or_whitespace_count=report.removed_empty_or_whitespace_count,
        layout_cleanup_skipped_reason=report.skipped_reason,
        layout_cleanup_error_code=report.error_code,
        error_message=error_message,
    )
