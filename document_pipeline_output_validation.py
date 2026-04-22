import re
from dataclasses import dataclass
from typing import Literal, TypeAlias


ProcessedBlockStatus: TypeAlias = Literal["valid", "empty", "heading_only_output"]

# Spec TOC/minimal-formatting 2026-04-21 constants.
TOC_UPPERCASE_LABEL_MAX_CHARS = 10
TOC_UPPERCASE_LABEL_MIN_CHARS = 2
TOC_UNCHANGED_SUBSTANTIVE_ENTRY_REJECTION_THRESHOLD = 2
TOC_SUBSTANTIVE_ENTRY_MIN_COUNT_FOR_UNCHANGED_REJECTION = 3
TOC_PAGE_MARKER_LOSS_REJECTION_THRESHOLD = 2
# Current implementation keeps zero tolerance for paragraph-count drift until a
# narrower non-substantive tolerance is explicitly specified and validated.
TOC_PARAGRAPH_COUNT_TOLERANCE = 0
DISALLOWED_GENERIC_TOC_LABELS = {"CONTENTS"}


@dataclass(frozen=True)
class TocValidationResult:
    is_valid: bool
    reason: str | None = None


def iter_nonempty_markdown_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def is_markdown_heading_line(line: str) -> bool:
    return bool(re.match(r"#{1,6}\s+\S", line))


def is_heading_only_markdown(text: str) -> bool:
    nonempty_lines = iter_nonempty_markdown_lines(text)
    return bool(nonempty_lines) and all(is_markdown_heading_line(line) for line in nonempty_lines)


def is_heading_like_alpha_token(token: str) -> bool:
    stripped = token.strip("\"'“”‘’()[]{}<>«»,-—–:;,.!?")
    if not stripped:
        return False

    alpha_chars = [char for char in stripped if char.isalpha()]
    if not alpha_chars:
        return False

    if all(char.isupper() for char in alpha_chars):
        return True

    for char in stripped:
        if char.isalpha():
            return char.isupper()
    return False


def is_plaintext_heading_like_line(line: str) -> bool:
    if any(symbol in line for symbol in ".!?;"):
        return False

    tokens = [token for token in re.split(r"[\s\t]+", line.strip()) if token]
    alpha_tokens = [token for token in tokens if any(char.isalpha() for char in token)]
    if not alpha_tokens or len(alpha_tokens) > 14:
        return False

    letters = [char for char in line if char.isalpha()]
    if not letters:
        return False

    uppercase_letters = [char for char in letters if char.isupper()]
    uppercase_ratio = len(uppercase_letters) / len(letters)
    heading_like_token_ratio = sum(1 for token in alpha_tokens if is_heading_like_alpha_token(token)) / len(alpha_tokens)
    if line.count(":") == 1:
        prefix, suffix = [part.strip() for part in line.split(":", maxsplit=1)]
        prefix_tokens = [token for token in re.split(r"[\s\t]+", prefix) if any(char.isalpha() for char in token)]
        suffix_tokens = [token for token in re.split(r"[\s\t]+", suffix) if any(char.isalpha() for char in token)]
        if (
            prefix_tokens
            and suffix_tokens
            and len(prefix_tokens) <= 4
            and len(suffix_tokens) <= 8
            and all(is_heading_like_alpha_token(token) for token in prefix_tokens)
        ):
            return True
    if "\t" in line and uppercase_ratio >= 0.6:
        return True
    if uppercase_ratio >= 0.6:
        return True
    if heading_like_token_ratio >= 0.8:
        return True
    return False


def input_has_body_text_signal(text: str) -> bool:
    nonempty_lines = iter_nonempty_markdown_lines(text)
    body_lines = [line for line in nonempty_lines if not is_markdown_heading_line(line)]
    if not body_lines:
        return False
    if len(body_lines) >= 2:
        return True
    body_line = body_lines[0]
    if is_plaintext_heading_like_line(body_line):
        return False
    if len(body_line) >= 40:
        return True
    if len(body_line.split()) >= 5 and any(symbol in body_line for symbol in ".,;:!?"):
        return True
    return False


def classify_processed_block(target_text: str, processed_chunk: str) -> ProcessedBlockStatus:
    if not processed_chunk.strip():
        return "empty"
    if is_heading_only_markdown(processed_chunk) and input_has_body_text_signal(target_text):
        return "heading_only_output"
    return "valid"


def _normalize_toc_comparison_text(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"\s*([.·•]{2,}|\.{2,})\s*(\d+)\s*$", r" ... \2", lowered)
    return lowered.strip(" \t\r\n-–—:;,.!?()[]{}\"'«»“”")


def _split_markdown_paragraphs(text: str) -> list[str]:
    return [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]


def _is_page_reference_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.fullmatch(r"[0-9ivxlcdmIVXLCDM]+", stripped):
        return True
    if re.fullmatch(r"[.·•\-–—\s]+", stripped):
        return True
    return False


def _has_page_reference_suffix(text: str) -> bool:
    return re.search(r"(?:\.{2,}|\s{2,})\s*[0-9ivxlcdmIVXLCDM]+\s*$", text.strip()) is not None


def _is_allowlisted_acronym_or_label_line(text: str) -> bool:
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