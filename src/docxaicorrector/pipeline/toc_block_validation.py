"""Translated TOC-block validation satellite (spec 035, Step 2).

Extracted verbatim from ``pipeline/output_validation.py``: ``TocValidationResult``,
the TOC-only threshold constants, the TOC comparison/allowlist helpers
(``_normalize_toc_comparison_text``, ``_is_page_reference_like``,
``_is_allowlisted_acronym_or_label_line``, ``_is_allowlisted_unchanged_toc_line``,
``_is_substantive_toc_line``), and ``validate_translated_toc_block``. Behaviour is
unchanged; ``output_validation`` re-exports these names (including the private ones
some whole-module test aliases read) so ``output_validation.<name>`` keeps resolving.

The shared primitives this cluster needs — ``_split_markdown_paragraphs``,
``_has_page_reference_suffix`` (also a core detector), and
``DISALLOWED_GENERIC_TOC_LABELS`` (also read by ``has_unexplained_english_residuals``)
— STAY in ``output_validation`` and are reached via function-local imports inside the
TOC functions that use them (avoids relocating widely-shared primitives and a
module-level import cycle).
"""

import re
from dataclasses import dataclass


# Spec TOC/minimal-formatting 2026-04-21 constants.
TOC_UPPERCASE_LABEL_MAX_CHARS = 10
TOC_UPPERCASE_LABEL_MIN_CHARS = 2
TOC_UNCHANGED_SUBSTANTIVE_ENTRY_REJECTION_THRESHOLD = 2
TOC_SUBSTANTIVE_ENTRY_MIN_COUNT_FOR_UNCHANGED_REJECTION = 3
TOC_PAGE_MARKER_LOSS_REJECTION_THRESHOLD = 2
# Current implementation keeps zero tolerance for paragraph-count drift until a
# narrower non-substantive tolerance is explicitly specified and validated.
TOC_PARAGRAPH_COUNT_TOLERANCE = 0


@dataclass(frozen=True)
class TocValidationResult:
    is_valid: bool
    reason: str | None = None


def _normalize_toc_comparison_text(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"\s*([.·•]{2,}|\.{2,})\s*(\d+)\s*$", r" ... \2", lowered)
    return lowered.strip(" \t\r\n-–—:;,.!?()[]{}\"'«»“”")


def _is_page_reference_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.fullmatch(r"[0-9ivxlcdmIVXLCDM]+", stripped):
        return True
    if re.fullmatch(r"[.·•\-–—\s]+", stripped):
        return True
    return False


def _is_allowlisted_acronym_or_label_line(text: str) -> bool:
    from docxaicorrector.pipeline.output_validation import DISALLOWED_GENERIC_TOC_LABELS

    tokens = [token for token in re.split(r"\s+", text.strip()) if token]
    if not tokens:
        return False
    alpha_seen = False
    for token in tokens:
        cleaned = token.strip(".()[]{}'\"“”‘’,:;!?-–—/")
        if not cleaned:
            continue
        if re.fullmatch(r"[IVXLCDM]+", cleaned):
            continue
        if cleaned.isdigit():
            continue
        alpha_chars = "".join(char for char in cleaned if char.isalpha())
        if not alpha_chars:
            continue
        alpha_seen = True
        if not alpha_chars.isupper():
            return False
        if cleaned in DISALLOWED_GENERIC_TOC_LABELS:
            return False
        if len(alpha_chars) < TOC_UPPERCASE_LABEL_MIN_CHARS or len(alpha_chars) > TOC_UPPERCASE_LABEL_MAX_CHARS:
            return False
    return alpha_seen


def _is_allowlisted_unchanged_toc_line(source_line: str, target_line: str) -> bool:
    normalized_source = _normalize_toc_comparison_text(source_line)
    normalized_target = _normalize_toc_comparison_text(target_line)
    if normalized_source != normalized_target:
        return False
    if _is_page_reference_like(normalized_source):
        return True
    if _is_allowlisted_acronym_or_label_line(source_line):
        return True
    return False


def _is_substantive_toc_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _is_page_reference_like(stripped):
        return False
    return bool(re.search(r"\w", stripped, re.UNICODE))


def validate_translated_toc_block(
    *,
    source_text: str,
    processed_chunk: str,
    structural_roles: list[str] | tuple[str, ...] | None,
    source_language: str,
    target_language: str,
) -> TocValidationResult:
    from docxaicorrector.pipeline.output_validation import _has_page_reference_suffix, _split_markdown_paragraphs

    if source_language.strip().lower() == target_language.strip().lower():
        return TocValidationResult(True)

    source_paragraphs = _split_markdown_paragraphs(source_text)
    target_paragraphs = _split_markdown_paragraphs(processed_chunk)
    if not source_paragraphs or not target_paragraphs:
        return TocValidationResult(False, "empty_toc_block")
    if abs(len(source_paragraphs) - len(target_paragraphs)) > TOC_PARAGRAPH_COUNT_TOLERANCE:
        return TocValidationResult(False, "toc_paragraph_count_drift")

    normalized_roles = [str(role or "").strip().lower() for role in (structural_roles or [])]
    unchanged_substantive_entries = 0
    substantive_toc_entries = 0
    lost_page_markers = 0

    for index, (source_paragraph, target_paragraph) in enumerate(zip(source_paragraphs, target_paragraphs)):
        role = normalized_roles[index] if index < len(normalized_roles) else ""
        normalized_source = _normalize_toc_comparison_text(source_paragraph)
        normalized_target = _normalize_toc_comparison_text(target_paragraph)

        if role == "toc_header" and normalized_source == normalized_target and not _is_allowlisted_unchanged_toc_line(source_paragraph, target_paragraph):
            return TocValidationResult(False, "unchanged_toc_header")

        if role == "toc_entry" and _is_substantive_toc_line(source_paragraph):
            substantive_toc_entries += 1
            if normalized_source == normalized_target and not _is_allowlisted_unchanged_toc_line(source_paragraph, target_paragraph):
                unchanged_substantive_entries += 1
            if _has_page_reference_suffix(source_paragraph) and not _has_page_reference_suffix(target_paragraph):
                lost_page_markers += 1

    if (
        unchanged_substantive_entries >= TOC_UNCHANGED_SUBSTANTIVE_ENTRY_REJECTION_THRESHOLD
        and substantive_toc_entries >= TOC_SUBSTANTIVE_ENTRY_MIN_COUNT_FOR_UNCHANGED_REJECTION
    ):
        return TocValidationResult(False, "too_many_unchanged_toc_entries")
    if lost_page_markers >= TOC_PAGE_MARKER_LOSS_REJECTION_THRESHOLD:
        return TocValidationResult(False, "lost_toc_page_markers")
    return TocValidationResult(True)
