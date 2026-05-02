import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias


ProcessedBlockStatus: TypeAlias = Literal[
    "valid",
    "empty",
    "heading_only_output",
    "bullet_heading_output",
    "toc_body_concat",
    "english_residual_output",
]

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
_BULLET_HEADING_PATTERN = re.compile(r"^#{1,6}\s*[●•\-*]\s*$")
_MARKDOWN_HEADING_PATTERN = re.compile(r"^#{1,6}\s+\S")
_ENGLISH_WORD_PATTERN = re.compile(r"\b[A-Za-z]{4,}\b")
_CYRILLIC_CHAR_PATTERN = re.compile(r"[А-Яа-яЁё]")
_BULLET_GLYPH_PATTERN = re.compile(r"[●•◦‣]")
_SCRIPTURE_REFERENCE_HEADING_PATTERN = re.compile(
    r"^#{1,6}\s+\((?:[1-3]\s*)?[A-ZА-ЯЁ][^()]{0,40}\s+\d{1,3}:\d{1,3}(?:[-–]\d{1,3})?\)$"
)
_PARENTHETICAL_ONLY_HEADING_PATTERN = re.compile(r"^#{1,6}\s+\([^\n]+\)$")
_HEADING_PREFIX_PATTERN = re.compile(r"^#{1,6}\s+")
_CYRILLIC_LATIN_MIXED_TOKEN_PATTERN = re.compile(r"(?=\w*[A-Za-z])(?=\w*[А-Яа-яЁё])[A-Za-zА-Яа-яЁё]+")
_HOMOGLYPH_TABLE = str.maketrans({
    "a": "а",
    "e": "е",
    "o": "о",
    "c": "с",
    "p": "р",
    "x": "х",
    "y": "у",
    "A": "А",
    "E": "Е",
    "O": "О",
    "C": "С",
    "P": "Р",
    "X": "Х",
    "Y": "У",
})
_DANGLING_NUMBER_PATTERN = re.compile(r"(?:^|\s)\d+\.$")
_RUSSIAN_CONTINUATION_ENDING_PATTERN = re.compile(r"\b(?:ли|что|относительно|с|в|на|к|по|для|о|у|при|об|под|над|между|является)$", re.IGNORECASE)
_RUSSIAN_HEADING_CONTINUATION_START_PATTERN = re.compile(r"^(?:[а-яё]|[)\],.;:!?-])")
_LOWERCASE_START_PATTERN = re.compile(r"^[a-zа-яё]")
_SENTENCE_TERMINAL_PATTERN = re.compile(r"[.!?…:](?:[)\]»”’'\"])?$")
_TOC_BODY_CONCAT_MARKDOWN_PATTERN = re.compile(
    r"(?:\.{2,}|[\u2024\u2025\u2026\u2027\u2219\u22c5\u00b7]{2,}|\s{2,})\s*[0-9ivxlcdmIVXLCDM]+\s+[А-Яа-яЁёA-Za-z]"
)
_TOC_TITLE_CAPTURE_PATTERN = re.compile(
    r"(?P<title>[А-ЯЁA-Z][^\n]{0,120}?)(?:\.{2,}|[\u2024\u2025\u2026\u2027\u2219\u22c5\u00b7]{2,})\s*[0-9ivxlcdmIVXLCDM]+"
)
_BLOCKQUOTE_PREFIX_PATTERN = re.compile(r"^(\s*>\s?)(.*)$")
_MARKDOWN_HEADING_PREFIX_PATTERN = re.compile(r"^(#{1,6})\s+")
_STRUCTURAL_INLINE_LABEL_PATTERN = re.compile(
    r"^(?:\d+\s*/\s*\d+\.\)|год\s+\d+\b|(?:суд|чаша|петля|часть|глава|введение|заключение|содержание)\b)",
    re.IGNORECASE,
)
_INLINE_HEADING_FRAGMENT_MAX_WORDS = 6
_INLINE_PARAGRAPH_FRAGMENT_MAX_WORDS = 12
_INLINE_PARAGRAPH_FRAGMENT_MAX_CHARS = 100


@dataclass(frozen=True)
class TocValidationResult:
    is_valid: bool
    reason: str | None = None


@dataclass(frozen=True)
class QualityIssueSample:
    line: int
    text: str
    reason: str | None = None


@dataclass(frozen=True)
class FinalAssemblyDiagnostics:
    accepted_merges: int = 0
    denied_merges: int = 0
    protected_boundary_denials: int = 0
    registry_covered_paragraphs: int = 0
    fallback_paragraphs: int = 0
    paragraph_count_drift: int = 0
    inconsistent_registry_blocks: tuple[int, ...] = ()


@dataclass(frozen=True)
class FinalAssemblyEntry:
    text: str
    block_index: int
    paragraph_id: str | None = None
    source_index: int | None = None
    role: str | None = None
    structural_role: str | None = None
    heading_level: int | None = None
    list_kind: str | None = None
    boundary_source: str | None = None
    boundary_confidence: str | None = None
    from_registry: bool = False
    used_fallback: bool = False


@dataclass(frozen=True)
class FinalMarkdownAssemblyResult:
    final_markdown: str
    entries: tuple[FinalAssemblyEntry, ...]
    diagnostics: FinalAssemblyDiagnostics


def iter_nonempty_markdown_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def iter_markdown_lines_with_numbers(text: str) -> list[tuple[int, str]]:
    return [(index, line.rstrip()) for index, line in enumerate(text.splitlines(), start=1)]


def is_markdown_heading_line(line: str) -> bool:
    return bool(_MARKDOWN_HEADING_PATTERN.match(line))


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
    if has_bullet_heading_output(processed_chunk):
        return "bullet_heading_output"
    if is_heading_only_markdown(processed_chunk) and input_has_body_text_signal(target_text):
        return "heading_only_output"
    if has_toc_body_concat_signal(target_text=target_text, processed_chunk=processed_chunk):
        return "toc_body_concat"
    if has_unexplained_english_residuals(processed_chunk):
        return "english_residual_output"
    return "valid"


def has_bullet_heading_output(text: str) -> bool:
    return any(_BULLET_HEADING_PATTERN.match(line) for line in iter_nonempty_markdown_lines(text))


def has_toc_body_concat_signal(*, target_text: str, processed_chunk: str) -> bool:
    source_has_toc_markers = _has_page_reference_suffix(target_text) or "contents" in target_text.casefold() or "содержание" in target_text.casefold()
    if not source_has_toc_markers:
        return False
    return has_toc_body_concat_markdown(processed_chunk)


def has_toc_body_concat_markdown(text: str) -> bool:
    paragraphs = _split_markdown_paragraphs(text)
    if not paragraphs:
        return False
    return any(_TOC_BODY_CONCAT_MARKDOWN_PATTERN.search(paragraph) for paragraph in paragraphs)


def has_unexplained_english_residuals(text: str) -> bool:
    if not _CYRILLIC_CHAR_PATTERN.search(text):
        return False
    lines = iter_nonempty_markdown_lines(text)
    english_hits = 0
    for line in lines:
        normalized = line.lstrip("#> -*0123456789.\t ")
        for word in _ENGLISH_WORD_PATTERN.findall(normalized):
            upper_word = word.upper()
            if upper_word in DISALLOWED_GENERIC_TOC_LABELS:
                english_hits += 1
                continue
            if word.lower() in {"chapter", "contents", "introduction", "conclusion", "judgment"}:
                english_hits += 1
                continue
    return english_hits > 0


def collect_bullet_heading_samples(text: str) -> list[QualityIssueSample]:
    samples: list[QualityIssueSample] = []
    for line_number, raw_line in iter_markdown_lines_with_numbers(text):
        line = raw_line.strip()
        if _BULLET_HEADING_PATTERN.match(line):
            samples.append(QualityIssueSample(line=line_number, text=line, reason="bullet_marker_heading"))
    return samples


def _trim_heading_prefix(line: str) -> str:
    return _HEADING_PREFIX_PATTERN.sub("", line.strip(), count=1).strip()


def _normalize_heading_text(text: str) -> str:
    lowered = text.casefold().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip(" \t\r\n\"'“”‘’«»()[]{}:;,.!?-–—")


def _is_continuation_like_previous_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped[-1] in {"(", "[", "{", "-", "—", "–", ":", ","}:
        return True
    if _SENTENCE_TERMINAL_PATTERN.search(stripped) is None:
        return True
    return _RUSSIAN_CONTINUATION_ENDING_PATTERN.search(stripped) is not None


def _is_continuation_like_next_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _RUSSIAN_HEADING_CONTINUATION_START_PATTERN.match(stripped):
        return True
    return False


def _split_blockquote_prefix(line: str) -> tuple[str, str]:
    match = _BLOCKQUOTE_PREFIX_PATTERN.match(line)
    if match is None:
        return "", line.strip()
    return match.group(1), match.group(2).strip()


def _merge_inline_fragments(*parts: str) -> str:
    merged = " ".join(part.strip() for part in parts if part and part.strip())
    merged = re.sub(r"\s+([,.;:!?…)])", r"\1", merged)
    merged = re.sub(r"([([])\s+", r"\1", merged)
    merged = re.sub(r"\s+", " ", merged)
    return merged.strip()


def _merge_content_line(base_line: str, addition_line: str) -> str:
    base_prefix, base_content = _split_blockquote_prefix(base_line)
    addition_prefix, addition_content = _split_blockquote_prefix(addition_line)
    prefix = base_prefix or addition_prefix
    merged_content = _merge_inline_fragments(base_content, addition_content)
    return f"{prefix}{merged_content}" if prefix else merged_content


def _heading_level_marker(line: str) -> str | None:
    match = _MARKDOWN_HEADING_PREFIX_PATTERN.match(line.strip())
    if match is None:
        return None
    return match.group(1)


def _strip_blockquote_content(line: str) -> str:
    return _split_blockquote_prefix(line)[1].strip()


def _looks_title_like_heading_text(text: str) -> bool:
    stripped = text.strip().strip('"\'“”‘’«»')
    if not stripped:
        return False
    if _STRUCTURAL_INLINE_LABEL_PATTERN.match(stripped):
        return True
    if stripped[0].islower():
        return False
    if _SENTENCE_TERMINAL_PATTERN.search(stripped):
        return False
    words = [token for token in re.split(r"\s+", stripped) if token]
    return 0 < len(words) <= _INLINE_HEADING_FRAGMENT_MAX_WORDS


def _looks_structural_boundary_line(line: str) -> bool:
    stripped = _strip_blockquote_content(line)
    if not stripped:
        return False
    if is_markdown_heading_line(stripped):
        return True
    if re.match(r"^\d+[.)]\s+", stripped):
        return True
    if _STRUCTURAL_INLINE_LABEL_PATTERN.match(stripped):
        return True
    if _has_page_reference_suffix(stripped):
        return True
    if _looks_title_like_heading_text(stripped) and stripped.endswith(":"):
        return True
    return False


def _looks_heading_boundary_context(next_line: str) -> bool:
    if _BLOCKQUOTE_PREFIX_PATTERN.match(next_line.strip()):
        return True
    stripped = _strip_blockquote_content(next_line)
    if not stripped:
        return False
    if stripped[0].isupper():
        return True
    return stripped.startswith(("(", '"', "«"))


def _collect_toc_heading_registry(text: str) -> set[str]:
    headings: set[str] = set()
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.casefold() in {"содержание", "contents"}:
            continue
        for match in _TOC_TITLE_CAPTURE_PATTERN.finditer(stripped):
            normalized = _normalize_heading_text(match.group("title"))
            if normalized:
                headings.add(normalized)
    return headings


def _is_split_heading_continuation(previous_line: str, current_line: str) -> bool:
    previous_level = _heading_level_marker(previous_line)
    current_level = _heading_level_marker(current_line)
    if previous_level is None or current_level is None or previous_level != current_level:
        return False
    current_heading_text = _trim_heading_prefix(current_line.strip())
    return 0 < len(current_heading_text.split()) <= _INLINE_HEADING_FRAGMENT_MAX_WORDS


def _looks_inline_fragment_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _looks_structural_boundary_line(stripped):
        return False
    if is_markdown_heading_line(stripped) or stripped.startswith(("- ", ">")):
        return False
    if re.match(r"^\d+[.)]\s+", stripped):
        return False
    word_count = len(stripped.split())
    return word_count <= _INLINE_PARAGRAPH_FRAGMENT_MAX_WORDS or len(stripped) <= _INLINE_PARAGRAPH_FRAGMENT_MAX_CHARS


def _collapse_markdown_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _normalize_entry_text(entry: FinalAssemblyEntry) -> str:
    text = entry.text.strip()
    if entry.from_registry and not entry.used_fallback:
        return text
    return normalize_mixed_script_markdown(normalize_residual_bullet_glyphs_markdown(text))


def _coerce_source_paragraph_id(paragraph: object) -> str:
    paragraph_id = getattr(paragraph, "paragraph_id", "")
    return paragraph_id if isinstance(paragraph_id, str) else ""


def _coerce_source_paragraph_int(paragraph: object, attribute: str) -> int | None:
    value = getattr(paragraph, attribute, None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _coerce_source_paragraph_str(paragraph: object, attribute: str) -> str | None:
    value = getattr(paragraph, attribute, None)
    return value if isinstance(value, str) and value else None


def _build_source_paragraph_lookup(source_paragraphs: Sequence[object] | None) -> dict[str, object]:
    if not source_paragraphs:
        return {}
    lookup: dict[str, object] = {}
    for paragraph in source_paragraphs:
        paragraph_id = _coerce_source_paragraph_id(paragraph)
        if paragraph_id:
            lookup[paragraph_id] = paragraph
    return lookup


def _build_registry_by_block(generated_paragraph_registry: Sequence[Mapping[str, object]] | None) -> dict[int, list[Mapping[str, object]]]:
    grouped: dict[int, list[Mapping[str, object]]] = defaultdict(list)
    for entry in generated_paragraph_registry or ():
        block_index = entry.get("block_index")
        if isinstance(block_index, bool) or not isinstance(block_index, int):
            continue
        grouped[block_index].append(entry)
    return dict(grouped)


def _entry_text(entry: Mapping[str, object]) -> str:
    text = entry.get("text")
    return text.strip() if isinstance(text, str) else ""


def _entry_paragraph_id(entry: Mapping[str, object]) -> str | None:
    paragraph_id = entry.get("paragraph_id")
    return paragraph_id if isinstance(paragraph_id, str) and paragraph_id else None


def _block_registry_matches_raw_chunk(raw_chunk: str, entries: Sequence[Mapping[str, object]]) -> bool:
    raw_paragraphs = _split_markdown_paragraphs(raw_chunk)
    registry_paragraphs = [_entry_text(entry) for entry in entries if _entry_text(entry)]
    return raw_paragraphs == registry_paragraphs


def _entry_body_text(entry: FinalAssemblyEntry) -> str:
    return _strip_blockquote_content(entry.text).strip()


def _entry_is_heading(entry: FinalAssemblyEntry) -> bool:
    return (
        entry.heading_level is not None
        or entry.role == "heading"
        or entry.structural_role == "heading"
        or is_markdown_heading_line(entry.text)
    )


def _entry_is_blockquote(entry: FinalAssemblyEntry) -> bool:
    return bool(_BLOCKQUOTE_PREFIX_PATTERN.match(entry.text.strip()))


def _entry_is_toc(entry: FinalAssemblyEntry) -> bool:
    return entry.structural_role in {"toc_header", "toc_entry"}


def _entry_is_list(entry: FinalAssemblyEntry) -> bool:
    body_text = _entry_body_text(entry)
    return bool(entry.list_kind) or bool(re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)", body_text))


def _entry_is_structural_label(entry: FinalAssemblyEntry) -> bool:
    body_text = _entry_body_text(entry)
    return bool(_STRUCTURAL_INLINE_LABEL_PATTERN.match(body_text))


def _entry_is_protected_boundary(entry: FinalAssemblyEntry) -> bool:
    body_text = _entry_body_text(entry)
    if not body_text:
        return True
    if _entry_is_toc(entry) or _entry_is_heading(entry) or _entry_is_blockquote(entry):
        return True
    if _entry_is_list(entry) or _entry_is_structural_label(entry):
        return True
    return _looks_structural_boundary_line(body_text)


def _entry_can_participate_in_merge(entry: FinalAssemblyEntry) -> bool:
    if entry.used_fallback or not entry.from_registry:
        return False
    if _entry_is_protected_boundary(entry):
        return False
    body_text = _entry_body_text(entry)
    if not body_text:
        return False
    return True


def _left_entry_looks_incomplete(entry: FinalAssemblyEntry) -> bool:
    body_text = _entry_body_text(entry)
    if not body_text:
        return False
    if body_text[-1] in {"(", "[", "{", "-", "—", "–", ":", ","}:
        return True
    if _SENTENCE_TERMINAL_PATTERN.search(body_text) is None:
        return True
    return _RUSSIAN_CONTINUATION_ENDING_PATTERN.search(body_text) is not None


def _right_entry_looks_like_continuation(entry: FinalAssemblyEntry) -> bool:
    body_text = _entry_body_text(entry)
    if not body_text:
        return False
    if _RUSSIAN_HEADING_CONTINUATION_START_PATTERN.match(body_text):
        return True
    if _looks_inline_fragment_line(body_text):
        return True
    if body_text[0].islower():
        return True
    return body_text.startswith(("(", '"', "«", "—", "–"))


def _merge_entry_pair(left: FinalAssemblyEntry, right: FinalAssemblyEntry) -> FinalAssemblyEntry:
    return FinalAssemblyEntry(
        text=_merge_content_line(left.text, right.text),
        block_index=left.block_index,
        paragraph_id=left.paragraph_id,
        source_index=left.source_index,
        role=left.role,
        structural_role=left.structural_role,
        heading_level=left.heading_level,
        list_kind=left.list_kind,
        boundary_source=left.boundary_source,
        boundary_confidence=left.boundary_confidence,
        from_registry=left.from_registry and right.from_registry,
        used_fallback=left.used_fallback or right.used_fallback,
    )


def _recover_adjacent_entries(entries: Sequence[FinalAssemblyEntry]) -> tuple[tuple[FinalAssemblyEntry, ...], int, int, int]:
    if not entries:
        return (), 0, 0, 0

    recovered: list[FinalAssemblyEntry] = []
    accepted_merges = 0
    denied_merges = 0
    protected_boundary_denials = 0

    for entry in entries:
        normalized_entry = FinalAssemblyEntry(
            text=_normalize_entry_text(entry),
            block_index=entry.block_index,
            paragraph_id=entry.paragraph_id,
            source_index=entry.source_index,
            role=entry.role,
            structural_role=entry.structural_role,
            heading_level=entry.heading_level,
            list_kind=entry.list_kind,
            boundary_source=entry.boundary_source,
            boundary_confidence=entry.boundary_confidence,
            from_registry=entry.from_registry,
            used_fallback=entry.used_fallback,
        )

        if not recovered:
            recovered.append(normalized_entry)
            continue

        previous = recovered[-1]
        same_block = previous.block_index == normalized_entry.block_index
        if not same_block:
            recovered.append(normalized_entry)
            continue

        if not _entry_can_participate_in_merge(previous) or not _entry_can_participate_in_merge(normalized_entry):
            if _entry_is_protected_boundary(previous) or _entry_is_protected_boundary(normalized_entry):
                protected_boundary_denials += 1
            else:
                denied_merges += 1
            recovered.append(normalized_entry)
            continue

        if _left_entry_looks_incomplete(previous) and _right_entry_looks_like_continuation(normalized_entry):
            recovered[-1] = _merge_entry_pair(previous, normalized_entry)
            accepted_merges += 1
            continue

        denied_merges += 1
        recovered.append(normalized_entry)

    return tuple(recovered), accepted_merges, denied_merges, protected_boundary_denials


def assemble_final_markdown(
    *,
    processed_chunks: Sequence[str],
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
    source_paragraphs: Sequence[object] | None,
) -> FinalMarkdownAssemblyResult:
    source_lookup = _build_source_paragraph_lookup(source_paragraphs)
    registry_by_block = _build_registry_by_block(generated_paragraph_registry)
    entries: list[FinalAssemblyEntry] = []
    inconsistent_blocks: list[int] = []
    registry_covered_paragraphs = 0
    fallback_paragraphs = 0

    for block_index, raw_chunk in enumerate(processed_chunks, start=1):
        stripped_chunk = raw_chunk.strip()
        if not stripped_chunk:
            continue
        raw_paragraphs = _split_markdown_paragraphs(stripped_chunk)
        block_entries = registry_by_block.get(block_index, [])

        if not block_entries or not _block_registry_matches_raw_chunk(stripped_chunk, block_entries):
            if block_entries:
                inconsistent_blocks.append(block_index)
            fallback_paragraphs += len(raw_paragraphs)
            for paragraph_text in raw_paragraphs:
                entries.append(
                    FinalAssemblyEntry(
                        text=paragraph_text,
                        block_index=block_index,
                        from_registry=False,
                        used_fallback=True,
                    )
                )
            continue

        registry_covered_paragraphs += len(block_entries)
        for entry in block_entries:
            paragraph_text = _entry_text(entry)
            paragraph_id = _entry_paragraph_id(entry)
            source_paragraph = source_lookup.get(paragraph_id or "")
            entries.append(
                FinalAssemblyEntry(
                    text=paragraph_text,
                    block_index=block_index,
                    paragraph_id=paragraph_id,
                    source_index=_coerce_source_paragraph_int(source_paragraph, "source_index") if source_paragraph is not None else None,
                    role=_coerce_source_paragraph_str(source_paragraph, "role") if source_paragraph is not None else None,
                    structural_role=_coerce_source_paragraph_str(source_paragraph, "structural_role") if source_paragraph is not None else None,
                    heading_level=_coerce_source_paragraph_int(source_paragraph, "heading_level") if source_paragraph is not None else None,
                    list_kind=_coerce_source_paragraph_str(source_paragraph, "list_kind") if source_paragraph is not None else None,
                    boundary_source=_coerce_source_paragraph_str(source_paragraph, "boundary_source") if source_paragraph is not None else None,
                    boundary_confidence=_coerce_source_paragraph_str(source_paragraph, "boundary_confidence") if source_paragraph is not None else None,
                    from_registry=True,
                    used_fallback=False,
                )
            )

    original_entry_count = len(entries)
    recovered_entries, accepted_merges, denied_merges, protected_boundary_denials = _recover_adjacent_entries(entries)
    assembled_markdown = "\n\n".join(entry.text for entry in recovered_entries).strip()
    final_markdown = _collapse_markdown_blank_lines(assembled_markdown)
    paragraph_count_drift = len(_split_markdown_paragraphs(final_markdown)) - original_entry_count
    diagnostics = FinalAssemblyDiagnostics(
        accepted_merges=accepted_merges,
        denied_merges=denied_merges,
        protected_boundary_denials=protected_boundary_denials,
        registry_covered_paragraphs=registry_covered_paragraphs,
        fallback_paragraphs=fallback_paragraphs,
        paragraph_count_drift=paragraph_count_drift,
        inconsistent_registry_blocks=tuple(inconsistent_blocks),
    )
    return FinalMarkdownAssemblyResult(
        final_markdown=final_markdown,
        entries=recovered_entries,
        diagnostics=diagnostics,
    )


def _build_quality_sample(*, line: int, text: str, reason: str) -> QualityIssueSample:
    return QualityIssueSample(line=line, text=text.strip(), reason=reason)


def collect_false_fragment_heading_samples(text: str) -> list[QualityIssueSample]:
    lines = iter_markdown_lines_with_numbers(text)
    toc_heading_registry = _collect_toc_heading_registry(text)
    heading_occurrences: list[tuple[int, str, str]] = []
    samples: list[QualityIssueSample] = []

    for index, (line_number, raw_line) in enumerate(lines):
        stripped = raw_line.strip()
        if not is_markdown_heading_line(stripped):
            continue

        heading_text = _trim_heading_prefix(stripped)
        normalized_heading = _normalize_heading_text(heading_text)
        previous_line = ""
        next_line = ""

        for previous_index in range(index - 1, -1, -1):
            candidate = lines[previous_index][1].strip()
            if candidate:
                previous_line = candidate
                break

        for next_index in range(index + 1, len(lines)):
            candidate = lines[next_index][1].strip()
            if candidate:
                next_line = candidate
                break

        if _SCRIPTURE_REFERENCE_HEADING_PATTERN.match(stripped):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="scripture_reference_heading_present"))
            heading_occurrences.append((line_number, heading_text, normalized_heading))
            continue

        if _PARENTHETICAL_ONLY_HEADING_PATTERN.match(stripped):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="false_fragment_headings_present"))
            heading_occurrences.append((line_number, heading_text, normalized_heading))
            continue

        if normalized_heading in toc_heading_registry and _looks_title_like_heading_text(heading_text):
            heading_occurrences.append((line_number, heading_text, normalized_heading))
            continue

        if _is_split_heading_continuation(previous_line, stripped):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="split_heading_continuation_present"))
            heading_occurrences.append((line_number, heading_text, normalized_heading))
            continue

        continuation_prev = _is_continuation_like_previous_line(previous_line)
        continuation_next = _is_continuation_like_next_line(next_line)
        if heading_text.endswith("?)") or heading_text.endswith(")") and "?" in heading_text:
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="sentence_split_heading_present"))
        elif continuation_prev and len(heading_text.split()) <= _INLINE_HEADING_FRAGMENT_MAX_WORDS:
            reason = "inline_term_heading_present"
            if not continuation_next:
                reason = "sentence_split_heading_present"
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason=reason))
        elif continuation_prev and continuation_next:
            reason = "sentence_split_heading_present"
            if len(heading_text.split()) <= 4:
                reason = "inline_term_heading_present"
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason=reason))
        heading_occurrences.append((line_number, heading_text, normalized_heading))

    grouped: dict[str, list[tuple[int, str]]] = {}
    for line_number, heading_text, normalized_heading in heading_occurrences:
        if not normalized_heading:
            continue
        grouped.setdefault(normalized_heading, []).append((line_number, heading_text))

    nonempty_non_heading_lines = {line_number for line_number, raw_line in lines if raw_line.strip() and not raw_line.strip().startswith("#")}

    for repeated in grouped.values():
        if len(repeated) <= 1:
            continue
        previous_line_number: int | None = None
        for line_number, heading_text in repeated:
            if previous_line_number is None:
                previous_line_number = line_number
                continue
            intervening_body_lines = sum(
                1 for candidate in nonempty_non_heading_lines if previous_line_number < candidate < line_number
            )
            if intervening_body_lines > 0:
                previous_line_number = line_number
                continue
            samples.append(_build_quality_sample(line=line_number, text=heading_text, reason="suspicious_heading_repetition_present"))
            previous_line_number = line_number

    deduped: list[QualityIssueSample] = []
    seen: set[tuple[int, str]] = set()
    for sample in samples:
        key = (sample.line, sample.reason or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sample)
    return deduped


def normalize_false_fragment_headings_markdown(text: str) -> str:
    lines = text.splitlines()
    toc_heading_registry = _collect_toc_heading_registry(text)
    index = 0

    def previous_nonempty_index(start_index: int) -> int | None:
        for candidate_index in range(start_index - 1, -1, -1):
            if lines[candidate_index].strip():
                return candidate_index
        return None

    def next_nonempty_index(start_index: int) -> int | None:
        for candidate_index in range(start_index + 1, len(lines)):
            if lines[candidate_index].strip():
                return candidate_index
        return None

    while index < len(lines):
        stripped = lines[index].strip()
        if not is_markdown_heading_line(stripped):
            index += 1
            continue

        heading_text = _trim_heading_prefix(stripped)
        normalized_heading = _normalize_heading_text(heading_text)
        previous_index = previous_nonempty_index(index)
        next_index = next_nonempty_index(index)
        previous_line = lines[previous_index].strip() if previous_index is not None else ""
        next_line = lines[next_index].strip() if next_index is not None else ""

        if previous_index is not None and _is_split_heading_continuation(previous_line, stripped):
            previous_level = _heading_level_marker(previous_line) or "##"
            previous_heading_text = _trim_heading_prefix(previous_line)
            lines[previous_index] = f"{previous_level} {_merge_inline_fragments(previous_heading_text, heading_text)}"
            lines[index] = ""
            index += 1
            continue

        should_demote = False
        if _SCRIPTURE_REFERENCE_HEADING_PATTERN.match(stripped):
            should_demote = True
        elif _PARENTHETICAL_ONLY_HEADING_PATTERN.match(stripped):
            should_demote = True
        elif normalized_heading in toc_heading_registry and _looks_title_like_heading_text(heading_text):
            should_demote = False
        else:
            continuation_prev = _is_continuation_like_previous_line(previous_line)
            continuation_next = _is_continuation_like_next_line(next_line)
            if continuation_prev and len(heading_text.split()) <= _INLINE_HEADING_FRAGMENT_MAX_WORDS:
                should_demote = not (
                    _looks_title_like_heading_text(heading_text)
                    and _looks_heading_boundary_context(next_line)
                )
            elif continuation_prev and continuation_next:
                should_demote = True
            elif heading_text.endswith("?)") or heading_text.endswith(")") and "?" in heading_text:
                should_demote = True

        if should_demote:
            if previous_index is not None and _is_continuation_like_previous_line(previous_line):
                lines[previous_index] = _merge_content_line(lines[previous_index], heading_text)
                lines[index] = ""
                if next_index is not None and _is_continuation_like_next_line(next_line):
                    lines[previous_index] = _merge_content_line(lines[previous_index], lines[next_index])
                    lines[next_index] = ""
            else:
                lines[index] = heading_text

        index += 1

    return _collapse_markdown_blank_lines("\n".join(lines))


def normalize_inline_fragment_paragraphs_markdown(text: str) -> str:
    lines = text.splitlines()

    def previous_nonempty_index(start_index: int) -> int | None:
        for candidate_index in range(start_index - 1, -1, -1):
            if lines[candidate_index].strip():
                return candidate_index
        return None

    def next_nonempty_index(start_index: int) -> int | None:
        for candidate_index in range(start_index + 1, len(lines)):
            if lines[candidate_index].strip():
                return candidate_index
        return None

    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not _looks_inline_fragment_line(stripped):
            index += 1
            continue

        previous_index = previous_nonempty_index(index)
        if previous_index is None:
            index += 1
            continue

        previous_line = lines[previous_index].strip()
        if (
            is_markdown_heading_line(previous_line)
            or _looks_structural_boundary_line(previous_line)
            or not _is_continuation_like_previous_line(previous_line)
        ):
            index += 1
            continue

        lines[previous_index] = _merge_content_line(lines[previous_index], lines[index])
        lines[index] = ""

        next_index = next_nonempty_index(index)
        if next_index is not None:
            next_line = lines[next_index].strip()
            if _looks_inline_fragment_line(next_line) and _is_continuation_like_next_line(next_line) and not _SENTENCE_TERMINAL_PATTERN.search(stripped):
                lines[previous_index] = _merge_content_line(lines[previous_index], lines[next_index])
                lines[next_index] = ""

        index += 1

    return _collapse_markdown_blank_lines("\n".join(lines))


def normalize_residual_bullet_glyphs_markdown(text: str) -> str:
    normalized_lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            normalized_lines.append(raw_line)
            continue
        if stripped.startswith("#") or stripped.startswith(">"):
            normalized_lines.append(raw_line)
            continue

        updated = raw_line
        updated = re.sub(r"^(\s*)[●•◦‣]\s+", r"\1- ", updated)
        updated = re.sub(r"([,;:])\s*[●•◦‣]\s*", r"\1 ", updated)
        updated = re.sub(r"\s*[●•◦‣]\s*;\s*", "; ", updated)
        updated = re.sub(r"\s*[●•◦‣]\s*", " ", updated)
        updated = re.sub(r" {2,}", " ", updated)
        normalized_lines.append(updated.rstrip())

    return "\n".join(normalized_lines)


def normalize_list_fragment_regressions_markdown(text: str) -> str:
    lines = text.splitlines()

    def _next_nonempty_index(start_index: int) -> int | None:
        for candidate_index in range(start_index + 1, len(lines)):
            if lines[candidate_index].strip():
                return candidate_index
        return None

    def _strip_heading_prefix(text_line: str) -> str:
        stripped_line = text_line.strip()
        if is_markdown_heading_line(stripped_line):
            return _trim_heading_prefix(stripped_line)
        return stripped_line

    for index, raw_line in enumerate(list(lines)):
        stripped = raw_line.strip()
        if not stripped:
            continue

        next_index = _next_nonempty_index(index)
        if next_index is None:
            continue
        next_stripped = lines[next_index].strip()
        if re.match(r"^\d+[.)]\s+", next_stripped):
            continue

        intro_match = re.match(r"^(?P<prefix>.+?):\s+1\.$", stripped)
        if intro_match is not None:
            lines[index] = intro_match.group("prefix") + ":"
            next_content = _strip_heading_prefix(lines[next_index])
            lines[next_index] = f"1. {next_content}"
            continue

        carry_match = re.match(r"^(?:(?P<current>\d+)\.\s+)?(?P<body>.+?)\s+(?P<next>\d+)\.$", stripped)
        if carry_match is None:
            continue

        next_number = int(carry_match.group("next"))
        current_number_group = carry_match.group("current")
        current_number = int(current_number_group) if current_number_group is not None else max(1, next_number - 1)
        if current_number_group is not None and next_number != current_number + 1:
            continue

        body = str(carry_match.group("body") or "").strip()
        if not body:
            continue

        body_tokens = body.split()
        if current_number_group is None and len(body_tokens) <= 2 and not re.search(r"[A-Za-zА-Яа-яЁё]", body):
            lines[index] = body
        else:
            lines[index] = f"{current_number}. {body}"
        next_content = _strip_heading_prefix(lines[next_index])
        lines[next_index] = f"{next_number}. {next_content}"

    return "\n".join(lines)


def normalize_mixed_script_markdown(text: str) -> str:
    def _repair_mixed_token(match: re.Match[str]) -> str:
        token = match.group(0)
        repaired = token.translate(_HOMOGLYPH_TABLE)
        return repaired if repaired != token else token

    return _CYRILLIC_LATIN_MIXED_TOKEN_PATTERN.sub(_repair_mixed_token, text)


def collect_residual_bullet_glyph_samples(text: str) -> list[QualityIssueSample]:
    samples: list[QualityIssueSample] = []
    for line_number, raw_line in iter_markdown_lines_with_numbers(text):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            content = stripped[2:]
            if _BULLET_GLYPH_PATTERN.search(content):
                samples.append(_build_quality_sample(line=line_number, text=stripped, reason="residual_bullet_glyphs_present"))
            continue
        if re.match(r"^\d+[.)]\s+", stripped):
            content = re.sub(r"^\d+[.)]\s+", "", stripped)
            if _BULLET_GLYPH_PATTERN.search(content):
                samples.append(_build_quality_sample(line=line_number, text=stripped, reason="residual_bullet_glyphs_present"))
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith(">"):
            continue
        if _BULLET_GLYPH_PATTERN.search(stripped):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="residual_bullet_glyphs_present"))
    return samples


def collect_list_fragment_regression_samples(text: str) -> list[QualityIssueSample]:
    lines = iter_markdown_lines_with_numbers(text)
    samples: list[QualityIssueSample] = []
    for index, (line_number, raw_line) in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped:
            continue
        next_line = lines[index + 1][1].strip() if index + 1 < len(lines) else ""
        if stripped.startswith("- ") and _DANGLING_NUMBER_PATTERN.search(stripped):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="list_fragment_regressions_present"))
            continue
        if stripped.startswith("- ") and next_line.startswith("- "):
            next_content = next_line[2:].strip()
            if next_content and (_LOWERCASE_START_PATTERN.match(next_content) or len(next_content.split()) <= 3):
                samples.append(_build_quality_sample(line=line_number, text=f"{stripped} || {next_line}", reason="list_fragment_regressions_present"))
                continue
        if not stripped.startswith(("- ", "#", ">")) and next_line.startswith("- "):
            next_content = next_line[2:].strip()
            if next_content and not _SENTENCE_TERMINAL_PATTERN.search(stripped) and (
                _LOWERCASE_START_PATTERN.match(next_content) or len(next_content.split()) <= 4
            ):
                samples.append(_build_quality_sample(line=line_number, text=f"{stripped} || {next_line}", reason="list_fragment_regressions_present"))
                continue
        if not stripped.startswith(("- ", "#", ">")) and _DANGLING_NUMBER_PATTERN.search(stripped):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="list_fragment_regressions_present"))
    return samples


def collect_mixed_script_samples(text: str) -> list[QualityIssueSample]:
    samples: list[QualityIssueSample] = []
    for line_number, raw_line in iter_markdown_lines_with_numbers(text):
        stripped = raw_line.strip()
        if not stripped:
            continue
        for token in _CYRILLIC_LATIN_MIXED_TOKEN_PATTERN.findall(stripped):
            samples.append(_build_quality_sample(line=line_number, text=token, reason="mixed_script_term_present"))
    seen: set[tuple[int, str, str]] = set()
    deduped: list[QualityIssueSample] = []
    for sample in samples:
        key = (sample.line, sample.text, sample.reason or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sample)
    return deduped


def collect_theology_style_issue_samples(text: str) -> list[QualityIssueSample]:
    samples: list[QualityIssueSample] = []
    seen_glossary_terms: dict[str, int] = {}
    for line_number, raw_line in iter_markdown_lines_with_numbers(text):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if "Суд над пятым печатью" in stripped:
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="awkward_judgment_heading_present"))
        if "Четвёртое чашеобразное судилище" in stripped:
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="awkward_judgment_heading_present"))
        lowered = stripped.casefold()
        for glossary_term in ("imago dei", "koinonia"):
            if glossary_term in lowered:
                seen_glossary_terms[glossary_term] = seen_glossary_terms.get(glossary_term, 0) + 1
                samples.append(_build_quality_sample(line=line_number, text=stripped, reason="unresolved_glossary_term_present"))

    deduped: list[QualityIssueSample] = []
    seen: set[tuple[int, str, str]] = set()
    for sample in samples:
        key = (sample.line, sample.text, sample.reason or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sample)
    return deduped


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
