import re
from collections import defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias

# spec 035 Step 1: the paragraph-break detection satellite now lives in
# ``pipeline.paragraph_break_detection``. Re-export its public + private names so
# ``output_validation.<name>`` (and ``from ...output_validation import <name>``) keep
# resolving for every existing consumer (situation-1, re-export only).
from docxaicorrector.pipeline.paragraph_break_detection import (  # noqa: F401
    ParagraphBreakSample,
    _PARAGRAPH_BREAK_CONTINUATION_STARTS,
    _PARAGRAPH_BREAK_LIST_KINDS,
    _paragraph_break_ends_without_terminal,
    _paragraph_break_entry_is_heading_or_list,
    _paragraph_break_out_of_main_content,
    _paragraph_break_raw_key,
    _paragraph_break_shares_source_paragraph,
    _paragraph_break_source_index,
    _paragraph_break_starts_continuation,
    collect_paragraph_break_samples,
)
# spec 035 Step 2: the translated-TOC-block validation satellite now lives in
# ``pipeline.toc_block_validation``. Re-export its public + private names — INCLUDING the
# private ``_is_page_reference_like`` / ``_is_substantive_toc_line`` /
# ``_is_allowlisted_unchanged_toc_line`` that whole-module test aliases read — so
# ``output_validation.<name>`` keeps resolving for every existing consumer.
from docxaicorrector.pipeline.toc_block_validation import (  # noqa: F401
    TOC_PAGE_MARKER_LOSS_REJECTION_THRESHOLD,
    TOC_PARAGRAPH_COUNT_TOLERANCE,
    TOC_SUBSTANTIVE_ENTRY_MIN_COUNT_FOR_UNCHANGED_REJECTION,
    TOC_UNCHANGED_SUBSTANTIVE_ENTRY_REJECTION_THRESHOLD,
    TOC_UPPERCASE_LABEL_MAX_CHARS,
    TOC_UPPERCASE_LABEL_MIN_CHARS,
    TocValidationResult,
    _is_allowlisted_acronym_or_label_line,
    _is_allowlisted_unchanged_toc_line,
    _is_page_reference_like,
    _is_substantive_toc_line,
    _normalize_toc_comparison_text,
    validate_translated_toc_block,
)


ProcessedBlockStatus: TypeAlias = Literal[
    "valid",
    "empty",
    "source_text_fallback",
    "heading_only_output",
    "bullet_heading_output",
    "toc_body_concat",
    "english_residual_output",
]
GeneratedHeadingKind: TypeAlias = Literal["real_heading", "false_fragment_heading", "unknown"]

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
_CANONICAL_JUDGMENT_HEADING_PATTERN = re.compile(r"^суд\b.+\(откровение\s+\d{1,3}:\d{1,3}", re.IGNORECASE)
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
# A bullet glyph welded between two word characters ("4●5", "a◦b") is data, not a
# stray bullet: the residual-glyph pass and its detector both leave it untouched.
_WELDED_BULLET_GLYPH_PATTERN = re.compile(r"(?<=\w)[●•◦‣](?=\w)")
_CODE_FENCE_LINE_PATTERN = re.compile(r"^\s*(?:`{3,}|~{3,})")
_INLINE_CODE_SPAN_PATTERN = re.compile(r"(`[^`]+`)")
# A whitespace-delimited token carrying a scheme, an "@", or a domain-style dot is
# an address, not prose: its Latin/Cyrillic look-alikes are intentional.
_URL_OR_EMAIL_TOKEN_PATTERN = re.compile(r"://|www\.|@|[\w-]+\.[\w-]{2,}")
_DANGLING_NUMBER_PATTERN = re.compile(r"(?:^|\s)\d+\.$")
_RUSSIAN_CONTINUATION_ENDING_PATTERN = re.compile(r"\b(?:ли|что|относительно|с|в|на|к|по|для|о|у|при|об|под|над|между|является)$", re.IGNORECASE)
_RUSSIAN_HEADING_CONTINUATION_START_PATTERN = re.compile(r"^(?:[а-яё]|[)\],.;:!?-])")
_RUSSIAN_PRONOUN_CONTINUATION_START_PATTERN = re.compile(
    r"^(?:Я|Мы|Ты|Вы|Он|Она|Они)\s+(?:смог\w+|буд\w+|хот\w+|мож\w+|долж\w+|стан\w+|готов\w+|суме\w+)",
    re.IGNORECASE,
)
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
_PAGE_PLACEHOLDER_CHAPTER_CONCAT_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?:(?P<marker>#{1,6})\s+)?(?P<placeholder>this page intentionally left blank)\s+(?P<heading>(?:chapter|глава)\b.+)$",
    re.IGNORECASE,
)
_CHAPTER_MARKER_LINE_PATTERN = re.compile(r"^(?:#{1,6}\s+)?(?:chapter|глава)\s+(?:\d+|[ivxlcdm]+)\b[ .:-]*$", re.IGNORECASE)
_INLINE_HEADING_FRAGMENT_MAX_WORDS = 6
_INLINE_PARAGRAPH_FRAGMENT_MAX_WORDS = 12
_INLINE_PARAGRAPH_FRAGMENT_MAX_CHARS = 100
_SOURCE_TEXT_FALLBACK_MIN_CHARS = 120
_SOURCE_TEXT_FALLBACK_MIN_ENGLISH_WORDS = 12


@dataclass(frozen=True)
class QualityIssueSample:
    line: int
    text: str
    reason: str | None = None


@dataclass(frozen=True)
class FinalAssemblyDecision:
    action: Literal["demote_heading", "merge"]
    block_index: int
    paragraph_ids: tuple[str, ...] = ()
    reason: str | None = None


@dataclass(frozen=True)
class FinalAssemblyDiagnostics:
    accepted_merges: int = 0
    denied_merges: int = 0
    protected_boundary_denials: int = 0
    demoted_false_headings: int = 0
    registry_covered_paragraphs: int = 0
    fallback_paragraphs: int = 0
    paragraph_count_drift: int = 0
    inconsistent_registry_blocks: tuple[int, ...] = ()
    merge_decisions: tuple[FinalAssemblyDecision, ...] = ()


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
    generated_heading_kind: GeneratedHeadingKind | None = None
    merged_paragraph_ids: tuple[str, ...] = ()
    controlled_fallback: bool = False
    controlled_fallback_kind: str | None = None


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
    if is_source_text_fallback_output(target_text=target_text, processed_chunk=processed_chunk):
        return "source_text_fallback"
    if has_bullet_heading_output(processed_chunk):
        return "bullet_heading_output"
    if is_heading_only_markdown(processed_chunk) and input_has_body_text_signal(target_text):
        return "heading_only_output"
    if has_toc_body_concat_signal(target_text=target_text, processed_chunk=processed_chunk):
        return "toc_body_concat"
    if has_unexplained_english_residuals(processed_chunk):
        return "english_residual_output"
    return "valid"


def is_source_text_fallback_output(*, target_text: str, processed_chunk: str) -> bool:
    if processed_chunk != target_text:
        return False
    stripped = target_text.strip()
    if len(stripped) < _SOURCE_TEXT_FALLBACK_MIN_CHARS:
        return False
    if _CYRILLIC_CHAR_PATTERN.search(stripped):
        return False
    return len(_ENGLISH_WORD_PATTERN.findall(stripped)) >= _SOURCE_TEXT_FALLBACK_MIN_ENGLISH_WORDS


def has_bullet_heading_output(text: str) -> bool:
    return any(_BULLET_HEADING_PATTERN.match(line) for line in iter_nonempty_markdown_lines(text))


def has_toc_body_concat_signal(*, target_text: str, processed_chunk: str) -> bool:
    source_has_toc_markers = _has_page_reference_suffix(target_text) or "contents" in target_text.casefold() or "содержание" in target_text.casefold()
    if not source_has_toc_markers:
        return False
    return has_toc_body_concat_markdown(processed_chunk)


def has_toc_body_concat_markdown(text: str) -> bool:
    paragraphs = _split_markdown_paragraphs(_normalize_markdown_for_toc_body_concat_advisory_detection(text))
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


def normalize_heading_match_text(text: str) -> str:
    # Canonical match key for comparing a heading line against a registry-derived
    # protected heading. Both sides MUST use this one function so matching is
    # consistent (late_phases builds the protected set with it).
    normalized = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip().lower()
    return re.sub(r"\s+", " ", normalized)


def _build_protected_heading_predicate(
    protected_heading_texts: Collection[str] | None,
) -> Callable[[str], bool]:
    # A protected heading carries a source-declared heading role (Constitution VII):
    # no display-side cleanup may demote it, merge it away, or fold it into a list.
    protected_match_texts = {
        normalize_heading_match_text(candidate)
        for candidate in (protected_heading_texts or ())
        if candidate and candidate.strip()
    }

    def is_protected_heading_line(line: str) -> bool:
        if not protected_match_texts:
            return False
        stripped_line = line.strip()
        if not is_markdown_heading_line(stripped_line):
            return False
        return normalize_heading_match_text(_trim_heading_prefix(stripped_line)) in protected_match_texts

    return is_protected_heading_line


def _normalize_repeated_heading_phrase(text: str) -> str:
    stripped = text.strip()
    match = _MARKDOWN_HEADING_PREFIX_PATTERN.match(stripped)
    if match is None:
        return stripped

    marker = match.group(1)
    heading_text = stripped[match.end() :].strip()
    words = heading_text.split()
    if len(words) < 4 or len(words) % 2 != 0:
        return stripped

    midpoint = len(words) // 2
    left_words = words[:midpoint]
    right_words = words[midpoint:]
    left_normalized = _normalize_heading_text(" ".join(left_words))
    right_normalized = _normalize_heading_text(" ".join(right_words))
    if not left_normalized or left_normalized != right_normalized:
        return stripped

    return f"{marker} {' '.join(left_words)}"


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


def _is_chapter_marker_line(line: str) -> bool:
    return _CHAPTER_MARKER_LINE_PATTERN.match(_strip_blockquote_content(line).strip()) is not None


def _is_opening_chapter_heading_pair(*, previous_line: str, heading_text: str, is_document_opening_pair: bool) -> bool:
    if not is_document_opening_pair:
        return False
    if not _is_chapter_marker_line(previous_line):
        return False
    normalized_heading_text = heading_text.rstrip("?!").rstrip()
    return _looks_title_like_heading_text(normalized_heading_text)


def _looks_structural_boundary_line(line: str) -> bool:
    stripped = _strip_blockquote_content(line)
    if not stripped:
        return False
    if is_markdown_heading_line(stripped):
        return True
    if re.match(r"^\d+[.)]\s+", stripped):
        return True
    if _looks_index_page_reference_fragment(stripped):
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


def _is_parenthetical_question_tail(text: str) -> bool:
    stripped = text.strip()
    return stripped.endswith("?)") or (stripped.endswith(")") and "?" in stripped)


def _is_canonical_judgment_heading_text(text: str) -> bool:
    return bool(_CANONICAL_JUDGMENT_HEADING_PATTERN.match(text.strip()))


def _entry_looks_major_section_heading(entry: FinalAssemblyEntry) -> bool:
    body_text = _entry_body_text(entry)
    if is_markdown_heading_line(body_text):
        body_text = _trim_heading_prefix(body_text)
    if not body_text:
        return False
    if body_text[0].islower():
        return False
    if _is_canonical_judgment_heading_text(body_text):
        return False
    if _is_parenthetical_question_tail(body_text):
        return False
    return _looks_title_like_heading_text(body_text)


def _entry_looks_scripture_reference_fragment(entry: FinalAssemblyEntry) -> bool:
    return bool(_SCRIPTURE_REFERENCE_HEADING_PATTERN.match(entry.text.strip()))


def _entry_looks_parenthetical_heading_fragment(entry: FinalAssemblyEntry) -> bool:
    return bool(_PARENTHETICAL_ONLY_HEADING_PATTERN.match(entry.text.strip()))


def _entry_looks_sentence_fragment_heading(entry: FinalAssemblyEntry) -> bool:
    body_text = _entry_body_text(entry)
    if not body_text:
        return False
    if _entry_looks_scripture_reference_fragment(entry) or _entry_looks_parenthetical_heading_fragment(entry):
        return True
    if _is_parenthetical_question_tail(body_text):
        return True
    if body_text[0].islower() and _looks_inline_fragment_line(body_text):
        return True
    if body_text.startswith(("/", ")", "]", ",", ";", ":", "?", "!", "-", "—", "–")):
        return True
    return False


def _text_has_open_parenthetical_context(text: str) -> bool:
    balance = 0
    for char in text:
        if char == "(":
            balance += 1
        elif char == ")" and balance > 0:
            balance -= 1
    return balance > 0


def _entry_has_explicit_source_heading_signal(entry: FinalAssemblyEntry) -> bool:
    return entry.role == "heading" or entry.structural_role in {"heading", "toc_header", "toc_entry"}


def _entry_is_source_backed_scripture_heading(entry: FinalAssemblyEntry) -> bool:
    return (
        _entry_looks_scripture_reference_fragment(entry)
        and _entry_has_source_heading_signal(entry)
        and entry.from_registry
        and not entry.used_fallback
    )


def _entry_looks_parenthetical_question_tail_fragment(entry: FinalAssemblyEntry) -> bool:
    return _is_parenthetical_question_tail(_entry_body_text(entry))


def _entry_has_mixed_block_parenthetical_tail_context(
    entry: FinalAssemblyEntry,
    previous_entry: FinalAssemblyEntry | None,
    next_entry: FinalAssemblyEntry | None,
) -> bool:
    if previous_entry is None or next_entry is None:
        return False
    if previous_entry.block_index + 1 != entry.block_index:
        return False
    if next_entry.block_index != entry.block_index:
        return False
    if not _entry_looks_parenthetical_question_tail_fragment(entry):
        return False
    if _entry_is_source_backed_scripture_heading(entry):
        return False
    if not _entry_allows_continuation_context(previous_entry):
        return False
    previous_body = _entry_body_text(previous_entry)
    if not previous_body or not _text_has_open_parenthetical_context(previous_body):
        return False
    return _left_entry_looks_incomplete(previous_entry)


def _entry_can_override_source_heading_signal(
    entry: FinalAssemblyEntry,
    previous_entry: FinalAssemblyEntry | None,
    next_entry: FinalAssemblyEntry | None,
) -> bool:
    if entry.used_fallback or not entry.from_registry:
        return False
    if entry.structural_role in {"toc_header", "toc_entry"}:
        return False
    if _entry_is_source_backed_scripture_heading(entry):
        return False
    if _entry_has_mixed_block_parenthetical_tail_context(entry, previous_entry, next_entry):
        return True
    if _entry_looks_sentence_fragment_heading(entry):
        return True
    if _entry_has_cross_block_continuation_context(entry, previous_entry, next_entry):
        return True
    if _entry_has_previous_block_and_same_block_tail_context(entry, previous_entry, next_entry):
        return True
    if entry.heading_level is not None and _entry_looks_major_section_heading(entry):
        return False
    return False


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


def normalize_page_placeholder_heading_concats_markdown(text: str) -> str:
    normalized_lines: list[str] = []
    for raw_line in text.splitlines():
        match = _PAGE_PLACEHOLDER_CHAPTER_CONCAT_PATTERN.match(raw_line.rstrip())
        if match is None:
            normalized_lines.append(raw_line.rstrip())
            continue

        indent = match.group("indent") or ""
        marker = match.group("marker") or ""
        placeholder = str(match.group("placeholder") or "").strip()
        heading = str(match.group("heading") or "").strip()
        normalized_lines.append(f"{indent}{placeholder}")
        normalized_lines.append("")
        if marker:
            normalized_lines.append(f"{indent}{marker} {heading}")
        else:
            normalized_lines.append(f"{indent}{heading}")

    return _collapse_markdown_blank_lines("\n".join(normalized_lines))


def collect_page_placeholder_heading_concat_samples(text: str) -> list[QualityIssueSample]:
    samples: list[QualityIssueSample] = []
    for line_number, raw_line in iter_markdown_lines_with_numbers(text):
        stripped = raw_line.rstrip()
        if not stripped:
            continue
        if _PAGE_PLACEHOLDER_CHAPTER_CONCAT_PATTERN.match(stripped) is None:
            continue
        samples.append(
            QualityIssueSample(
                line=line_number,
                text=stripped,
                reason="page_placeholder_heading_concat_markdown_present",
            )
        )
    return samples


def _normalize_markdown_for_toc_body_concat_advisory_detection(text: str) -> str:
    # Placeholder splitting here is compatibility preprocessing for markdown advisory detection,
    # not new structure authority.
    return normalize_page_placeholder_heading_concats_markdown(text)


def _normalize_entry_text(entry: FinalAssemblyEntry) -> str:
    text = entry.text.strip()
    if entry.from_registry and not entry.used_fallback:
        return text
    return normalize_mixed_script_markdown(text)


def _normalize_final_entry_text(text: str) -> str:
    # Assembly stays close to recovered source-backed text. Display-only cleanup runs later.
    normalized = normalize_mixed_script_markdown(text)
    normalized = _normalize_repeated_heading_phrase(normalized)
    return normalized.strip()


def _normalize_final_entry_list_fragments(entries: Sequence[FinalAssemblyEntry]) -> tuple[FinalAssemblyEntry, ...]:
    if not entries:
        return ()

    normalized_entries = list(entries)

    def _replace_entry(index: int, text: str) -> None:
        entry = normalized_entries[index]
        normalized_entries[index] = FinalAssemblyEntry(
            text=text.strip(),
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
            generated_heading_kind=entry.generated_heading_kind,
            merged_paragraph_ids=entry.merged_paragraph_ids,
            controlled_fallback=entry.controlled_fallback,
            controlled_fallback_kind=entry.controlled_fallback_kind,
        )

    for index, entry in enumerate(list(normalized_entries)):
        stripped = entry.text.strip()
        if not stripped:
            continue
        next_index = index + 1
        if next_index >= len(normalized_entries):
            continue
        next_entry = normalized_entries[next_index]
        next_stripped = next_entry.text.strip()
        if not next_stripped:
            continue

        intro_match = re.match(r"^(?P<prefix>.+?):\s+1\.$", stripped)
        if intro_match is not None and not _entry_is_heading(next_entry):
            _replace_entry(index, intro_match.group("prefix") + ":")
            next_content = _trim_heading_prefix(next_stripped) if is_markdown_heading_line(next_stripped) else next_stripped
            _replace_entry(next_index, f"1. {next_content}")
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
        if not next_stripped or _entry_is_heading(entry):
            continue

        # A hanging trailing number on a footnote/body block (e.g. an endnote
        # block ending in a page reference "… с. 24.") must not steal the number
        # of a following chapter/section heading. Mirror the intro-branch guard
        # (`not _entry_is_heading(next_entry)`): only fold the follower into a
        # list marker when it is NOT itself a heading — unless the current entry
        # is a genuine numbered list item carrying an explicit leading ordinal,
        # which is the legitimate list-continuation case where a mis-tagged
        # subheading really is the next list item.
        next_is_heading = (
            _entry_is_heading(next_entry)
            or next_entry.heading_level is not None
            or is_markdown_heading_line(next_stripped)
        )
        if next_is_heading and not (
            current_number_group is not None and _entry_is_list(entry)
        ):
            continue

        body_tokens = body.split()
        if current_number_group is None and len(body_tokens) <= 2 and not re.search(r"[A-Za-zА-Яа-яЁё]", body):
            _replace_entry(index, body)
        else:
            _replace_entry(index, f"{current_number}. {body}")

        next_content = _trim_heading_prefix(next_stripped) if is_markdown_heading_line(next_stripped) else next_stripped
        _replace_entry(next_index, f"{next_number}. {next_content}")

    return tuple(normalized_entries)


def _dedupe_repeated_real_heading_cluster_tokens(entries: Sequence[FinalAssemblyEntry]) -> tuple[FinalAssemblyEntry, ...]:
    if not entries:
        return ()

    deduped: list[FinalAssemblyEntry] = []
    heading_cluster_seen: set[str] = set()
    heading_cluster_length = 0

    for entry in entries:
        if _entry_is_heading(entry) and _entry_has_source_heading_signal(entry):
            heading_text = _trim_heading_prefix(entry.text)
            normalized_heading = _normalize_heading_text(heading_text)
            token_count = len(normalized_heading.split())
            if (
                heading_cluster_length > 0
                and normalized_heading
                and token_count <= 3
                and normalized_heading in heading_cluster_seen
            ):
                heading_cluster_length += 1
                continue
            deduped.append(entry)
            if normalized_heading:
                heading_cluster_seen.add(normalized_heading)
            heading_cluster_length += 1
            continue

        deduped.append(entry)
        if _entry_body_text(entry):
            heading_cluster_seen = set()
            heading_cluster_length = 0

    return tuple(deduped)


def _apply_final_entry_post_normalization(entries: Sequence[FinalAssemblyEntry]) -> tuple[FinalAssemblyEntry, ...]:
    normalized_entries: list[FinalAssemblyEntry] = []
    for entry in entries:
        normalized_text = _normalize_final_entry_text(entry.text)
        if normalized_text == entry.text:
            normalized_entries.append(entry)
            continue
        normalized_entries.append(
            FinalAssemblyEntry(
                text=normalized_text,
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
                generated_heading_kind=entry.generated_heading_kind,
                merged_paragraph_ids=entry.merged_paragraph_ids,
                controlled_fallback=entry.controlled_fallback,
                controlled_fallback_kind=entry.controlled_fallback_kind,
            )
        )
    normalized_entries = list(_normalize_final_entry_list_fragments(tuple(normalized_entries)))
    return _dedupe_repeated_real_heading_cluster_tokens(tuple(normalized_entries))


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


def _entry_paragraph_ids(entry: FinalAssemblyEntry) -> tuple[str, ...]:
    if entry.merged_paragraph_ids:
        return entry.merged_paragraph_ids
    if entry.paragraph_id:
        return (entry.paragraph_id,)
    return ()


def _merge_paragraph_ids(*entries: FinalAssemblyEntry) -> tuple[str, ...]:
    ordered_ids: list[str] = []
    seen_ids: set[str] = set()
    for entry in entries:
        for paragraph_id in _entry_paragraph_ids(entry):
            if paragraph_id in seen_ids:
                continue
            seen_ids.add(paragraph_id)
            ordered_ids.append(paragraph_id)
    return tuple(ordered_ids)


def _entry_has_source_heading_signal(entry: FinalAssemblyEntry) -> bool:
    return (
        entry.heading_level is not None
        or entry.role == "heading"
        or entry.structural_role in {"heading", "toc_header", "toc_entry"}
    )


def _entry_allows_continuation_context(entry: FinalAssemblyEntry) -> bool:
    if entry.used_fallback or not entry.from_registry:
        return False
    body_text = _entry_body_text(entry)
    if not body_text:
        return False
    if _entry_is_heading(entry) or _entry_is_toc(entry):
        return False
    if _entry_is_list(entry) or _entry_is_structural_label(entry):
        return False
    return True


def _build_recovery_entry(
    entry: FinalAssemblyEntry,
    *,
    text: str,
    generated_heading_kind: GeneratedHeadingKind | None,
) -> FinalAssemblyEntry:
    return FinalAssemblyEntry(
        text=text,
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
        generated_heading_kind=generated_heading_kind,
        merged_paragraph_ids=_entry_paragraph_ids(entry),
        controlled_fallback=entry.controlled_fallback,
        controlled_fallback_kind=entry.controlled_fallback_kind,
    )


def _entry_has_previous_continuation_context(
    entry: FinalAssemblyEntry,
    previous_entry: FinalAssemblyEntry | None,
) -> bool:
    return (
        previous_entry is not None
        and _entry_allows_continuation_context(previous_entry)
        and _left_entry_looks_incomplete(previous_entry)
    )


def _entry_has_next_continuation_context(
    entry: FinalAssemblyEntry,
    next_entry: FinalAssemblyEntry | None,
) -> bool:
    if next_entry is None or not _entry_allows_continuation_context(next_entry):
        return False
    demoted_entry = _build_recovery_entry(
        entry,
        text=_trim_heading_prefix(entry.text),
        generated_heading_kind="false_fragment_heading",
    )
    return _left_entry_looks_incomplete(demoted_entry) and _right_entry_looks_like_continuation(next_entry)


def _entry_has_cross_block_continuation_context(
    entry: FinalAssemblyEntry,
    previous_entry: FinalAssemblyEntry | None,
    next_entry: FinalAssemblyEntry | None,
) -> bool:
    if previous_entry is None or next_entry is None:
        return False
    if previous_entry.block_index + 1 != entry.block_index:
        return False
    if entry.block_index + 1 != next_entry.block_index:
        return False
    return _entry_has_previous_continuation_context(entry, previous_entry) and _entry_has_next_continuation_context(entry, next_entry)


def _entry_has_previous_block_and_same_block_tail_context(
    entry: FinalAssemblyEntry,
    previous_entry: FinalAssemblyEntry | None,
    next_entry: FinalAssemblyEntry | None,
) -> bool:
    if previous_entry is None or next_entry is None:
        return False
    if previous_entry.block_index + 1 != entry.block_index:
        return False
    if next_entry.block_index != entry.block_index:
        return False
    if not _entry_has_previous_continuation_context(entry, previous_entry):
        return False
    demoted_body = _trim_heading_prefix(entry.text).strip()
    if not demoted_body:
        return False
    next_body = _entry_body_text(next_entry)
    if not next_body:
        return False
    if re.fullmatch(r"[.?!…,:;]+", next_body):
        return True
    if _right_entry_looks_like_continuation(next_entry):
        return True
    return False


def _classify_generated_heading(
    entry: FinalAssemblyEntry,
    previous_entry: FinalAssemblyEntry | None,
    next_entry: FinalAssemblyEntry | None,
) -> GeneratedHeadingKind | None:
    if not is_markdown_heading_line(entry.text):
        return None
    if _entry_has_source_heading_signal(entry) and not _entry_can_override_source_heading_signal(entry, previous_entry, next_entry):
        return "real_heading"
    if entry.used_fallback or not entry.from_registry:
        return "unknown"

    demoted_text = _trim_heading_prefix(entry.text)
    if not (_looks_inline_fragment_line(demoted_text) or _entry_looks_sentence_fragment_heading(entry)):
        return "unknown"

    same_block_left_context = previous_entry is not None and previous_entry.block_index == entry.block_index and _entry_has_previous_continuation_context(entry, previous_entry)
    same_block_right_context = next_entry is not None and next_entry.block_index == entry.block_index and _entry_has_next_continuation_context(entry, next_entry)
    if same_block_left_context or same_block_right_context:
        return "false_fragment_heading"
    if _entry_has_mixed_block_parenthetical_tail_context(entry, previous_entry, next_entry):
        return "false_fragment_heading"
    if _entry_has_cross_block_continuation_context(entry, previous_entry, next_entry):
        return "false_fragment_heading"
    if _entry_has_previous_block_and_same_block_tail_context(entry, previous_entry, next_entry):
        return "false_fragment_heading"
    return "unknown"


def _normalize_recovery_entry(
    entry: FinalAssemblyEntry,
    previous_entry: FinalAssemblyEntry | None,
    next_entry: FinalAssemblyEntry | None,
) -> tuple[FinalAssemblyEntry, FinalAssemblyDecision | None]:
    generated_heading_kind = _classify_generated_heading(entry, previous_entry, next_entry)
    normalized_text = _normalize_entry_text(entry)
    if generated_heading_kind == "false_fragment_heading":
        demoted_text = _trim_heading_prefix(normalized_text)
        return (
            _build_recovery_entry(
                entry,
                text=demoted_text,
                generated_heading_kind=generated_heading_kind,
            ),
            FinalAssemblyDecision(
                action="demote_heading",
                block_index=entry.block_index,
                paragraph_ids=_entry_paragraph_ids(entry),
                reason="source_body_continuation_context",
            ),
        )
    return (
        _build_recovery_entry(
            entry,
            text=normalized_text,
            generated_heading_kind=generated_heading_kind,
        ),
        None,
    )


def _entry_is_heading(entry: FinalAssemblyEntry) -> bool:
    if entry.generated_heading_kind == "false_fragment_heading":
        return False
    if entry.generated_heading_kind == "real_heading":
        return True
    return (
        _entry_has_source_heading_signal(entry)
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


def _entries_match_blockquote_body_continuation_merge(left: FinalAssemblyEntry, right: FinalAssemblyEntry) -> bool:
    if not _entry_is_blockquote(left) or _entry_is_blockquote(right):
        return False
    if _entry_is_heading(right) or _entry_is_toc(right):
        return False
    if _entry_is_list(right) or _entry_is_structural_label(right):
        return False
    return _left_entry_looks_incomplete(left) and _right_entry_looks_like_continuation(right)


def _entry_can_participate_in_merge(entry: FinalAssemblyEntry) -> bool:
    if entry.used_fallback or not entry.from_registry:
        return False
    body_text = _entry_body_text(entry)
    if not body_text:
        return False
    return True


def _entries_match_allowed_protected_merge(left: FinalAssemblyEntry, right: FinalAssemblyEntry) -> bool:
    if _entry_is_blockquote(left) and _entry_is_blockquote(right):
        return True
    if _entries_match_blockquote_body_continuation_merge(left, right):
        return True
    if _entry_is_blockquote(left) and right.generated_heading_kind == "false_fragment_heading":
        return True
    if left.generated_heading_kind == "false_fragment_heading" and _entry_is_blockquote(right):
        return True
    if left.generated_heading_kind == "false_fragment_heading" or right.generated_heading_kind == "false_fragment_heading":
        return True
    return False


def _entries_can_participate_in_merge(left: FinalAssemblyEntry, right: FinalAssemblyEntry) -> bool:
    if not _entry_can_participate_in_merge(left) or not _entry_can_participate_in_merge(right):
        return False
    left_protected = _entry_is_protected_boundary(left)
    right_protected = _entry_is_protected_boundary(right)
    if not left_protected and not right_protected:
        return True
    return _entries_match_allowed_protected_merge(left, right)


def _left_entry_looks_incomplete(entry: FinalAssemblyEntry) -> bool:
    body_text = _entry_body_text(entry)
    if not body_text:
        return False
    if _text_has_open_parenthetical_context(body_text):
        return True
    if body_text[-1] in {"(", "[", "{", "-", "—", "–", ":", ","}:
        return True
    if _SENTENCE_TERMINAL_PATTERN.search(body_text) is None:
        return True
    return _RUSSIAN_CONTINUATION_ENDING_PATTERN.search(body_text) is not None


def _right_entry_looks_like_continuation(entry: FinalAssemblyEntry) -> bool:
    body_text = _entry_body_text(entry)
    if not body_text:
        return False
    if re.fullmatch(r"[.?!…,:;]+", body_text):
        return True
    if _RUSSIAN_HEADING_CONTINUATION_START_PATTERN.match(body_text):
        return True
    if _RUSSIAN_PRONOUN_CONTINUATION_START_PATTERN.match(body_text):
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
        generated_heading_kind=None,
        merged_paragraph_ids=_merge_paragraph_ids(left, right),
        controlled_fallback=left.controlled_fallback or right.controlled_fallback,
        controlled_fallback_kind=left.controlled_fallback_kind or right.controlled_fallback_kind,
    )


def _recover_adjacent_entries(
    entries: Sequence[FinalAssemblyEntry],
) -> tuple[tuple[FinalAssemblyEntry, ...], int, int, int, int, tuple[FinalAssemblyDecision, ...]]:
    if not entries:
        return (), 0, 0, 0, 0, ()

    normalized_entries: list[FinalAssemblyEntry] = []
    recovery_decisions: list[FinalAssemblyDecision] = []
    demoted_false_headings = 0

    for index, entry in enumerate(entries):
        previous_entry = entries[index - 1] if index > 0 else None
        next_entry = entries[index + 1] if index + 1 < len(entries) else None
        normalized_entry, decision = _normalize_recovery_entry(entry, previous_entry, next_entry)
        normalized_entries.append(normalized_entry)
        if decision is not None:
            demoted_false_headings += 1
            recovery_decisions.append(decision)

    recovered: list[FinalAssemblyEntry] = []
    accepted_merges = 0
    denied_merges = 0
    protected_boundary_denials = 0

    for normalized_entry in normalized_entries:
        if not recovered:
            recovered.append(normalized_entry)
            continue

        previous = recovered[-1]
        same_block = previous.block_index == normalized_entry.block_index
        adjacent_cross_block = previous.block_index + 1 == normalized_entry.block_index
        if not same_block and not adjacent_cross_block:
            recovered.append(normalized_entry)
            continue

        if not _entries_can_participate_in_merge(previous, normalized_entry):
            if (
                (_entry_is_protected_boundary(previous) or _entry_is_protected_boundary(normalized_entry))
                and not _entries_match_allowed_protected_merge(previous, normalized_entry)
            ):
                protected_boundary_denials += 1
            else:
                denied_merges += 1
            recovered.append(normalized_entry)
            continue

        if _left_entry_looks_incomplete(previous) and _right_entry_looks_like_continuation(normalized_entry):
            recovered[-1] = _merge_entry_pair(previous, normalized_entry)
            accepted_merges += 1
            recovery_decisions.append(
                FinalAssemblyDecision(
                    action="merge",
                    block_index=normalized_entry.block_index,
                    paragraph_ids=_entry_paragraph_ids(recovered[-1]),
                    reason="adjacent_continuation_recovery",
                )
            )
            continue

        denied_merges += 1
        recovered.append(normalized_entry)

    return (
        tuple(recovered),
        accepted_merges,
        denied_merges,
        protected_boundary_denials,
        demoted_false_headings,
        tuple(recovery_decisions),
    )


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
                    merged_paragraph_ids=(),
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
                    merged_paragraph_ids=(paragraph_id,) if paragraph_id else (),
                    controlled_fallback=bool(entry.get("controlled_fallback")),
                    controlled_fallback_kind=(
                        str(entry.get("controlled_fallback_kind"))
                        if isinstance(entry.get("controlled_fallback_kind"), str)
                        else None
                    ),
                )
            )

    original_entry_count = len(entries)
    (
        recovered_entries,
        accepted_merges,
        denied_merges,
        protected_boundary_denials,
        demoted_false_headings,
        merge_decisions,
    ) = _recover_adjacent_entries(entries)
    recovered_entries = _apply_final_entry_post_normalization(recovered_entries)
    assembled_markdown = "\n\n".join(entry.text for entry in recovered_entries).strip()
    final_markdown = _collapse_markdown_blank_lines(assembled_markdown)
    paragraph_count_drift = len(_split_markdown_paragraphs(final_markdown)) - original_entry_count
    diagnostics = FinalAssemblyDiagnostics(
        accepted_merges=accepted_merges,
        denied_merges=denied_merges,
        protected_boundary_denials=protected_boundary_denials,
        demoted_false_headings=demoted_false_headings,
        registry_covered_paragraphs=registry_covered_paragraphs,
        fallback_paragraphs=fallback_paragraphs,
        paragraph_count_drift=paragraph_count_drift,
        inconsistent_registry_blocks=tuple(inconsistent_blocks),
        merge_decisions=merge_decisions,
    )
    return FinalMarkdownAssemblyResult(
        final_markdown=final_markdown,
        entries=recovered_entries,
        diagnostics=diagnostics,
    )


def _entry_heading_text(entry: FinalAssemblyEntry) -> str:
    body_text = _entry_body_text(entry)
    if is_markdown_heading_line(body_text):
        return _trim_heading_prefix(body_text)
    return body_text.strip()


def _iter_entry_heading_positions(entries: Sequence[FinalAssemblyEntry]) -> list[tuple[int, int, FinalAssemblyEntry]]:
    positions: list[tuple[int, int, FinalAssemblyEntry]] = []
    line_number = 1
    for index, entry in enumerate(entries):
        positions.append((index, line_number, entry))
        line_number += max(1, len(entry.text.splitlines())) + 1
    return positions


def collect_false_fragment_heading_samples_from_entries(entries: Sequence[FinalAssemblyEntry]) -> list[QualityIssueSample]:
    positions = _iter_entry_heading_positions(entries)
    heading_occurrences: list[tuple[int, int, str, str]] = []
    samples: list[QualityIssueSample] = []

    for position_index, line_number, entry in positions:
        if entry.generated_heading_kind == "false_fragment_heading":
            continue
        stripped = entry.text.strip()
        if not is_markdown_heading_line(stripped):
            continue

        heading_text = _entry_heading_text(entry)
        normalized_heading = _normalize_heading_text(heading_text)
        previous_entry = positions[position_index - 1][2] if position_index > 0 else None
        next_entry = positions[position_index + 1][2] if position_index + 1 < len(positions) else None
        previous_line = previous_entry.text.strip() if previous_entry is not None else ""
        next_line = next_entry.text.strip() if next_entry is not None else ""
        continuation_prev = _entry_has_previous_continuation_context(entry, previous_entry)
        continuation_next = _entry_has_next_continuation_context(entry, next_entry)

        if _entry_is_toc(entry):
            heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))
            continue

        if _entry_is_source_backed_scripture_heading(entry):
            heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))
            continue

        if _entry_looks_scripture_reference_fragment(entry):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="scripture_reference_heading_present"))
            heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))
            continue

        if _entry_looks_parenthetical_heading_fragment(entry):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="false_fragment_headings_present"))
            heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))
            continue

        if _is_parenthetical_question_tail(heading_text):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="sentence_split_heading_present"))
            heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))
            continue

        if (
            entry.generated_heading_kind == "real_heading"
            or (
                _entry_has_source_heading_signal(entry)
                and not _entry_can_override_source_heading_signal(entry, previous_entry, next_entry)
            )
        ):
            heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))
            continue

        if _is_canonical_judgment_heading_text(heading_text):
            heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))
            continue

        if _is_opening_chapter_heading_pair(
            previous_line=previous_line,
            heading_text=heading_text,
            is_document_opening_pair=position_index == 1,
        ):
            heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))
            continue

        if _entry_looks_major_section_heading(entry) and not continuation_prev and next_line and not continuation_next:
            heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))
            continue

        if _is_split_heading_continuation(previous_line, stripped):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="split_heading_continuation_present"))
            heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))
            continue

        if continuation_prev and len(heading_text.split()) <= _INLINE_HEADING_FRAGMENT_MAX_WORDS:
            reason = "inline_term_heading_present"
            if not continuation_next:
                reason = "sentence_split_heading_present"
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason=reason))
        elif continuation_prev and continuation_next:
            reason = "sentence_split_heading_present"
            if len(heading_text.split()) <= 4:
                reason = "inline_term_heading_present"
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason=reason))

        heading_occurrences.append((position_index, line_number, heading_text, normalized_heading))

    grouped: dict[str, list[tuple[int, int, str]]] = {}
    for position_index, line_number, heading_text, normalized_heading in heading_occurrences:
        if not normalized_heading:
            continue
        grouped.setdefault(normalized_heading, []).append((position_index, line_number, heading_text))

    heading_positions = {position_index for position_index, _, _, _ in heading_occurrences}
    for repeated in grouped.values():
        if len(repeated) <= 1:
            continue
        previous_position: int | None = None
        for position_index, line_number, heading_text in repeated:
            if previous_position is None:
                previous_position = position_index
                continue
            intervening_body_entries = any(
                candidate_index not in heading_positions
                for candidate_index in range(previous_position + 1, position_index)
            )
            if intervening_body_entries:
                previous_position = position_index
                continue
            samples.append(_build_quality_sample(line=line_number, text=heading_text, reason="suspicious_heading_repetition_present"))
            previous_position = position_index

    deduped: list[QualityIssueSample] = []
    seen: set[tuple[int, str]] = set()
    for sample in samples:
        key = (sample.line, sample.reason or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sample)
    return deduped


def collect_recovered_heading_entries(entries: Sequence[FinalAssemblyEntry]) -> tuple[FinalAssemblyEntry, ...]:
    return tuple(
        entry
        for entry in entries
        if is_markdown_heading_line(entry.text.strip()) or entry.generated_heading_kind == "false_fragment_heading"
    )


def build_generated_paragraph_registry_from_entries(entries: Sequence[FinalAssemblyEntry]) -> list[dict[str, object]]:
    registry: list[dict[str, object]] = []
    for entry in entries:
        paragraph_id = entry.paragraph_id or (_entry_paragraph_ids(entry)[0] if _entry_paragraph_ids(entry) else None)
        if not paragraph_id:
            continue
        payload: dict[str, object] = {
            "block_index": entry.block_index,
            "paragraph_id": paragraph_id,
            "text": entry.text,
        }
        merged_ids = list(_entry_paragraph_ids(entry))
        if len(merged_ids) > 1:
            payload["merged_paragraph_ids"] = merged_ids
        if entry.controlled_fallback:
            payload["controlled_fallback"] = True
            if entry.controlled_fallback_kind:
                payload["controlled_fallback_kind"] = entry.controlled_fallback_kind
        registry.append(payload)
    return registry


def _build_quality_sample(*, line: int, text: str, reason: str) -> QualityIssueSample:
    return QualityIssueSample(line=line, text=text.strip(), reason=reason)


def collect_false_fragment_heading_samples(text: str) -> list[QualityIssueSample]:
    lines = iter_markdown_lines_with_numbers(text)
    toc_heading_registry = _collect_toc_heading_registry(text)
    first_nonempty_index = next((index for index, (_, raw_line) in enumerate(lines) if raw_line.strip()), None)
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
        previous_nonempty_index: int | None = None

        for previous_index in range(index - 1, -1, -1):
            candidate = lines[previous_index][1].strip()
            if candidate:
                previous_line = candidate
                previous_nonempty_index = previous_index
                break

        for next_index in range(index + 1, len(lines)):
            candidate = lines[next_index][1].strip()
            if candidate:
                next_line = candidate
                break

        continuation_prev = _is_continuation_like_previous_line(previous_line)
        continuation_next = _is_continuation_like_next_line(next_line)

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

        if _is_canonical_judgment_heading_text(heading_text):
            heading_occurrences.append((line_number, heading_text, normalized_heading))
            continue

        if _is_opening_chapter_heading_pair(
            previous_line=previous_line,
            heading_text=heading_text,
            is_document_opening_pair=(
                previous_nonempty_index is not None and previous_nonempty_index == first_nonempty_index
            ),
        ):
            heading_occurrences.append((line_number, heading_text, normalized_heading))
            continue

        if _looks_title_like_heading_text(heading_text) and not continuation_prev and next_line and not continuation_next:
            heading_occurrences.append((line_number, heading_text, normalized_heading))
            continue

        if _is_split_heading_continuation(previous_line, stripped):
            samples.append(_build_quality_sample(line=line_number, text=stripped, reason="split_heading_continuation_present"))
            heading_occurrences.append((line_number, heading_text, normalized_heading))
            continue

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


def normalize_false_fragment_headings_markdown(
    text: str,
    *,
    protected_heading_texts: Collection[str] | None = None,
) -> str:
    lines = text.splitlines()
    toc_heading_registry = _collect_toc_heading_registry(text)
    is_protected_heading_line = _build_protected_heading_predicate(protected_heading_texts)
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

        # A source-declared heading is never absorbed into a neighbouring line (FR-002/FR-003).
        if is_protected_heading_line(stripped):
            index += 1
            continue

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
                if (
                    next_index is not None
                    and _is_continuation_like_next_line(next_line)
                    and not is_protected_heading_line(next_line)
                ):
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


def _strip_stray_bullet_glyphs(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        # A glyph welded between two word characters is data (e.g. "4●5"); leave it
        # and its neighbours untouched. Every other glyph is a stray bullet.
        if match.group("welded") is not None:
            return match.group(0)
        return " "

    return re.sub(r"(?P<welded>(?<=\w)[●•◦‣](?=\w))|\s*[●•◦‣]\s*", _replace, text)


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
        # Only a leading glyph followed by whitespace AND real content is a list item.
        updated = re.sub(r"^(\s*)[●•◦‣]\s+(?=\S)", r"\1- ", updated)
        updated = re.sub(r"([,;:])\s*[●•◦‣]\s*", r"\1 ", updated)
        updated = re.sub(r"\s*[●•◦‣]\s*;\s*", "; ", updated)
        updated = _strip_stray_bullet_glyphs(updated)
        updated = re.sub(r" {2,}", " ", updated)
        normalized_lines.append(updated.rstrip())

    return "\n".join(normalized_lines)


def normalize_list_fragment_regressions_markdown(
    text: str,
    *,
    protected_heading_texts: Collection[str] | None = None,
) -> str:
    lines = text.splitlines()
    is_protected_heading_line = _build_protected_heading_predicate(protected_heading_texts)

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
        # A footnote entry ending in the next ordinal ("… 24.") must not steal a
        # source-declared heading and render it as list item "24. Глава IV".
        if is_protected_heading_line(next_stripped):
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


def _looks_url_or_email_token(token: str) -> bool:
    return bool(_URL_OR_EMAIL_TOKEN_PATTERN.search(token))


def _repair_mixed_script_token(match: re.Match[str]) -> str:
    token = match.group(0)
    repaired = token.translate(_HOMOGLYPH_TABLE)
    return repaired if repaired != token else token


def _repair_mixed_script_segment(segment: str) -> str:
    def _repair_word(match: re.Match[str]) -> str:
        word = match.group(0)
        if _looks_url_or_email_token(word):
            return word
        return _CYRILLIC_LATIN_MIXED_TOKEN_PATTERN.sub(_repair_mixed_script_token, word)

    return re.sub(r"\S+", _repair_word, segment)


def normalize_mixed_script_markdown(text: str) -> str:
    normalized_lines: list[str] = []
    in_fenced_block = False
    for line in text.splitlines():
        if _CODE_FENCE_LINE_PATTERN.match(line):
            in_fenced_block = not in_fenced_block
            normalized_lines.append(line)
            continue
        if in_fenced_block:
            normalized_lines.append(line)
            continue
        # Repair only the segments outside inline code spans; split() keeps the
        # backticked spans at odd indices so they pass through untouched.
        parts = _INLINE_CODE_SPAN_PATTERN.split(line)
        for index in range(0, len(parts), 2):
            parts[index] = _repair_mixed_script_segment(parts[index])
        normalized_lines.append("".join(parts))
    return "\n".join(normalized_lines)


def _has_repairable_bullet_glyph(text: str) -> bool:
    # Mirror the residual-glyph pass: a glyph welded between two word characters is
    # data the pass leaves alone, so the detector must not flag it either.
    return bool(_BULLET_GLYPH_PATTERN.search(_WELDED_BULLET_GLYPH_PATTERN.sub("", text)))


def collect_residual_bullet_glyph_samples(text: str) -> list[QualityIssueSample]:
    samples: list[QualityIssueSample] = []
    for line_number, raw_line in iter_markdown_lines_with_numbers(text):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            content = stripped[2:]
            if _has_repairable_bullet_glyph(content):
                samples.append(_build_quality_sample(line=line_number, text=stripped, reason="residual_bullet_glyphs_present"))
            continue
        if re.match(r"^\d+[.)]\s+", stripped):
            content = re.sub(r"^\d+[.)]\s+", "", stripped)
            if _has_repairable_bullet_glyph(content):
                samples.append(_build_quality_sample(line=line_number, text=stripped, reason="residual_bullet_glyphs_present"))
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith(">"):
            continue
        if _has_repairable_bullet_glyph(stripped):
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


def _iter_repairable_mixed_script_tokens(line: str) -> list[str]:
    # Share the mixed-script pass's guard: tokens inside inline code spans or that
    # look like a URL/email are left alone by the pass, so they are not reported.
    tokens: list[str] = []
    parts = _INLINE_CODE_SPAN_PATTERN.split(line)
    for index in range(0, len(parts), 2):
        for word in re.findall(r"\S+", parts[index]):
            if _looks_url_or_email_token(word):
                continue
            tokens.extend(_CYRILLIC_LATIN_MIXED_TOKEN_PATTERN.findall(word))
    return tokens


def collect_mixed_script_samples(text: str) -> list[QualityIssueSample]:
    samples: list[QualityIssueSample] = []
    in_fenced_block = False
    for line_number, raw_line in iter_markdown_lines_with_numbers(text):
        if _CODE_FENCE_LINE_PATTERN.match(raw_line):
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue
        stripped = raw_line.strip()
        if not stripped:
            continue
        for token in _iter_repairable_mixed_script_tokens(stripped):
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


def collect_glossary_and_heading_issue_samples(
    text: str,
    *,
    glossary_terms: Collection[str] = (),
    awkward_heading_markers: Collection[str] = (),
) -> list[QualityIssueSample]:
    # Spec 036 F2: the detector is config-driven with EMPTY defaults (anti-vacuum by
    # construction). No book-specific string is embedded here; callers supply the
    # document's translation-domain glossary terms / awkward-heading markers, and with
    # nothing configured the axis simply does not fire. The reason outputs
    # (``awkward_judgment_heading_present`` / ``unresolved_glossary_term_present``) are
    # unchanged so the gate report schema stays stable.
    normalized_heading_markers = [marker for marker in (str(m).strip() for m in awkward_heading_markers) if marker]
    normalized_glossary_terms = [term for term in (str(t).strip().casefold() for t in glossary_terms) if term]
    samples: list[QualityIssueSample] = []
    if not normalized_heading_markers and not normalized_glossary_terms:
        return samples
    for line_number, raw_line in iter_markdown_lines_with_numbers(text):
        stripped = raw_line.strip()
        if not stripped:
            continue
        for marker in normalized_heading_markers:
            if marker in stripped:
                samples.append(_build_quality_sample(line=line_number, text=stripped, reason="awkward_judgment_heading_present"))
        lowered = stripped.casefold()
        for glossary_term in normalized_glossary_terms:
            if glossary_term in lowered:
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


# Backwards-compatible alias (spec 036 F2): the former ``collect_theology_style_issue_samples``
# hardcoded per-book strings; it now resolves to the domain-neutral, config-driven detector
# above so any caller/import referencing the old name gets the empty-default behaviour.
collect_theology_style_issue_samples = collect_glossary_and_heading_issue_samples


def _split_markdown_paragraphs(text: str) -> list[str]:
    return [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]


def _has_page_reference_suffix(text: str) -> bool:
    return re.search(r"(?:\.{2,}|\s{2,})\s*[0-9ivxlcdmIVXLCDM]+\s*$", text.strip()) is not None


def _looks_index_page_reference_fragment(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    collapsed = re.sub(r"\s+", "", stripped)
    if not collapsed:
        return False
    if re.fullmatch(r"[.·•,;:()\[\]\-–—]+", collapsed):
        return False
    if re.fullmatch(r"[0-9ivxlcdmIVXLCDMnN,;:()\[\]\-–—]+", collapsed) is None:
        return False
    return any(char.isdigit() for char in collapsed) or bool(re.search(r"[ivxlcdmIVXLCDM]", collapsed))
