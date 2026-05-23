from __future__ import annotations

from dataclasses import dataclass
import re

from docxaicorrector.structure.page_furniture_detection import detect_page_furniture_hits

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCED_CODE_PATTERN = re.compile(r"^\s*(?:```+|~~~+)")
_INLINE_CODE_SPAN_PATTERN = re.compile(r"`[^`\n]+`")
_HTML_COMMENT_PATTERN = re.compile(r"^\s*<!--.*?-->\s*$")
_KNOWN_INTERNAL_PLACEHOLDER_PATTERN = re.compile(r"^\s*(?:\[\[DOCXAI_[A-Z0-9_]+\]\]|<!--\s*docxai:.*?-->)\s*$", re.IGNORECASE)
_INLINE_PAGE_NUMBER_TOKEN_PATTERN = re.compile(r"(?<![\w:])(?:page\s+)?(?:\d{1,4}|[ivxlcdm]{1,8})(?![\w:])", re.IGNORECASE)
_DOTTED_PAGE_RANGE_PATTERN = re.compile(r"\.{2,}\s*\d{1,4}\s*$")
_BIBLIOGRAPHY_CITATION_PATTERN = re.compile(r"(?:\[[0-9]{1,3}\]|\([0-9]{1,3}\))(?:\s*[;,]\s*(?:\[[0-9]{1,3}\]|\([0-9]{1,3}\))){1,}")
_SENTENCE_CONTINUATION_PATTERN = re.compile(r"[.!?]\s+[a-zа-яё]")
_SENTENCE_CLAUSE_PATTERN = re.compile(r"[.!?]\s+[A-ZА-ЯЁa-zа-яё]")
_SCRIPTURE_REFERENCE_PATTERN = re.compile(r"\b(?:[1-3]\s*)?[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё]+\s+\d{1,3}:\d{1,3}(?:[-–]\d{1,3})?\b")
_NUMBERED_APPENDIX_OR_INDEX_PATTERN = re.compile(r"^(?:appendix|index)\b(?:\s+[A-Z0-9IVXLCDM]+)?", re.IGNORECASE)
_TITLE_CASE_OR_ALL_CAPS_WORD_PATTERN = re.compile(r"[A-Za-zА-Яа-яЁё]+")
_CHAPTER_TOKEN_PATTERN = re.compile(r"\b(?:chapter|глава|part|section)\b", re.IGNORECASE)
_LEADING_NUMBERING_PATTERN = re.compile(r"^(?:\d+|[ivxlcdm]+)\b", re.IGNORECASE)
_QUOTE_LIKE_LINE_PATTERN = re.compile(r"^(?:>|[\"'«“”].+[\"'»“”])")
_ATTRIBUTION_DASH_PATTERN = re.compile(
    r"^(?:--|—)\s*[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё'’.\-]*(?:\s+[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё'’.\-]*){0,4},\s*[A-Za-zА-Яа-яЁё][^!?\n]{1,80}$"
)
_NAME_ROLE_PATTERN = re.compile(
    r"^[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё'’.\-]*(?:\s+[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё'’.\-]*){0,4},\s*[A-Za-zА-Яа-яЁё][^.!?0-9\n]{1,80}$"
)


@dataclass(frozen=True)
class StructureDetectorSample:
    detector_id: str
    line: int
    heading_level: int | None
    text: str
    previous_context: str
    next_context: str
    reason: str


def collect_structure_quality_detector_samples(markdown: str) -> tuple[StructureDetectorSample, ...]:
    lines = markdown.splitlines()
    repeated_running_header_candidates = _collect_repeated_running_header_candidates(lines)
    samples: list[StructureDetectorSample] = []
    in_fenced_code_block = False

    for index, raw_line in enumerate(lines, start=1):
        stripped = raw_line.rstrip().strip()
        if _FENCED_CODE_PATTERN.match(stripped):
            in_fenced_code_block = not in_fenced_code_block
            continue
        previous_context = _nearest_nonempty_line(lines, index - 2, step=-1)
        next_context = _nearest_nonempty_line(lines, index, step=1)
        heading_match = _HEADING_PATTERN.match(stripped)
        if not stripped or in_fenced_code_block:
            continue

        visible_text = _strip_inline_code_spans(stripped)
        if _is_safe_for_blank_marker_detection(stripped, heading_match, visible_text):
            for hit in detect_page_furniture_hits(visible_text):
                if hit.kind in {"blank_page_marker", "intentionally_blank_marker"}:
                    samples.append(
                        StructureDetectorSample(
                            detector_id="pdf_blank_page_marker_leakage",
                            line=index,
                            heading_level=_heading_level(heading_match),
                            text=stripped,
                            previous_context=previous_context,
                            next_context=next_context,
                            reason=f"{hit.kind}_visible_in_output",
                        )
                    )
                    break

        inline_page_furniture_reason = _detect_inline_page_furniture_reason(
            stripped,
            heading_match=heading_match,
            visible_text=visible_text,
            repeated_running_header_candidates=repeated_running_header_candidates,
        )
        if inline_page_furniture_reason is not None:
            samples.append(
                StructureDetectorSample(
                    detector_id="inline_page_furniture_leakage",
                    line=index,
                    heading_level=_heading_level(heading_match),
                    text=stripped,
                    previous_context=previous_context,
                    next_context=next_context,
                    reason=inline_page_furniture_reason,
                )
            )

        if heading_match and _looks_like_heading_body_concat(heading_match.group(2)):
            samples.append(
                StructureDetectorSample(
                    detector_id="heading_body_concat_detected",
                    line=index,
                    heading_level=len(heading_match.group(1)),
                    text=stripped,
                    previous_context=previous_context,
                    next_context=next_context,
                    reason="heading_exceeds_closed_concat_threshold",
                )
            )
        if heading_match and len(heading_match.group(1)) == 1 and _looks_like_epigraph_attribution(
            heading_match.group(2), previous_context=previous_context
        ):
            samples.append(
                StructureDetectorSample(
                    detector_id="h1_epigraph_attribution_pattern",
                    line=index,
                    heading_level=1,
                    text=stripped,
                    previous_context=previous_context,
                    next_context=next_context,
                    reason="h1_matches_attribution_shape_without_chapter_tokens",
                )
            )

    semantic_lines = _build_semantic_lines(lines)
    for line_number, stripped, heading_match, previous_context in semantic_lines:
        if not heading_match or len(heading_match.group(1)) != 1:
            continue
        next_semantic = _next_semantic_line(semantic_lines, line_number)
        if next_semantic is None:
            continue
        _, next_stripped, next_heading_match, _ = next_semantic
        if next_heading_match and len(next_heading_match.group(1)) == 1:
            samples.append(
                StructureDetectorSample(
                    detector_id="adjacent_h1_without_body",
                    line=line_number,
                    heading_level=1,
                    text=stripped,
                    previous_context=previous_context,
                    next_context=next_stripped,
                    reason="adjacent_h1_without_body_between",
                )
            )

    return tuple(samples)


def summarize_structure_quality_detectors(markdown: str, *, max_samples_per_detector: int = 5) -> tuple[dict[str, int], dict[str, list[dict[str, object]]]]:
    counts: dict[str, int] = {}
    samples_by_detector: dict[str, list[dict[str, object]]] = {}
    for sample in collect_structure_quality_detector_samples(markdown):
        counts[sample.detector_id] = counts.get(sample.detector_id, 0) + 1
        serialized = {
            "line": sample.line,
            "heading_level": sample.heading_level,
            "text": sample.text,
            "previous_context": sample.previous_context,
            "next_context": sample.next_context,
            "reason": sample.reason,
        }
        bucket = samples_by_detector.setdefault(sample.detector_id, [])
        if len(bucket) < max_samples_per_detector:
            bucket.append(serialized)
    return counts, samples_by_detector


def _heading_level(match: re.Match[str] | None) -> int | None:
    return None if match is None else len(match.group(1))


def _nearest_nonempty_line(lines: list[str], start_index: int, *, step: int) -> str:
    index = start_index
    while 0 <= index < len(lines):
        candidate = lines[index].strip()
        if candidate:
            return candidate
        index += step
    return ""


def _build_semantic_lines(lines: list[str]) -> list[tuple[int, str, re.Match[str] | None, str]]:
    semantic_lines: list[tuple[int, str, re.Match[str] | None, str]] = []
    in_fenced_code_block = False
    for index, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if _FENCED_CODE_PATTERN.match(stripped):
            in_fenced_code_block = not in_fenced_code_block
            continue
        if not stripped or in_fenced_code_block:
            continue
        if _HTML_COMMENT_PATTERN.match(stripped) or _KNOWN_INTERNAL_PLACEHOLDER_PATTERN.match(stripped):
            continue
        semantic_lines.append((index, stripped, _HEADING_PATTERN.match(stripped), _nearest_nonempty_line(lines, index - 2, step=-1)))
    return semantic_lines


def _next_semantic_line(
    semantic_lines: list[tuple[int, str, re.Match[str] | None, str]],
    line_number: int,
) -> tuple[int, str, re.Match[str] | None, str] | None:
    for semantic_line in semantic_lines:
        if semantic_line[0] > line_number:
            return semantic_line
    return None


def _is_standalone_blank_marker_line(line: str) -> bool:
    stripped = line.strip()
    hits = detect_page_furniture_hits(stripped)
    return bool(hits) and all(hit.start == 0 and hit.end == len(stripped) for hit in hits)


def _looks_like_heading_body_concat(heading_text: str) -> bool:
    text = heading_text.strip()
    if not text:
        return False
    if len(text.split()) <= 18 and len(text) <= 140:
        return False
    if _is_accepted_long_title_shape(text):
        return False
    if _SENTENCE_CONTINUATION_PATTERN.search(text):
        return True
    return len(_SENTENCE_CLAUSE_PATTERN.findall(text)) >= 2


def _looks_like_epigraph_attribution(heading_text: str, *, previous_context: str) -> bool:
    text = heading_text.strip()
    if not text or len(text.split()) > 12 or len(text) > 90:
        return False
    if _has_chapter_like_tokens(text):
        return False
    if _ATTRIBUTION_DASH_PATTERN.match(text):
        return True
    if _NAME_ROLE_PATTERN.match(text):
        return _looks_like_quote_line(previous_context) or "," in text
    return False


def _strip_inline_code_spans(text: str) -> str:
    return _INLINE_CODE_SPAN_PATTERN.sub(" ", text)


def _is_safe_for_blank_marker_detection(
    stripped: str,
    heading_match: re.Match[str] | None,
    visible_text: str,
) -> bool:
    if heading_match is not None:
        return False
    if stripped.startswith(">"):
        return False
    return bool(visible_text.strip())


def _collect_repeated_running_header_candidates(lines: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    in_fenced_code_block = False
    for raw_line in lines:
        stripped = raw_line.strip()
        if _FENCED_CODE_PATTERN.match(stripped):
            in_fenced_code_block = not in_fenced_code_block
            continue
        if not stripped or in_fenced_code_block or stripped.startswith(">") or _HEADING_PATTERN.match(stripped):
            continue
        visible_text = _strip_inline_code_spans(stripped)
        if _DOTTED_PAGE_RANGE_PATTERN.search(visible_text) or _BIBLIOGRAPHY_CITATION_PATTERN.search(visible_text):
            continue
        match = _INLINE_PAGE_NUMBER_TOKEN_PATTERN.search(visible_text)
        if match is None:
            continue
        for candidate in (
            _normalize_running_header_candidate(visible_text[: match.start()]),
            _normalize_running_header_candidate(visible_text[match.end() :]),
        ):
            if candidate is None:
                continue
            counts[candidate] = counts.get(candidate, 0) + 1
    return counts


def _detect_inline_page_furniture_reason(
    stripped: str,
    *,
    heading_match: re.Match[str] | None,
    visible_text: str,
    repeated_running_header_candidates: dict[str, int],
) -> str | None:
    if heading_match is not None or stripped.startswith(">"):
        return None
    if _is_standalone_blank_marker_line(visible_text):
        return None
    if _DOTTED_PAGE_RANGE_PATTERN.search(visible_text) or _BIBLIOGRAPHY_CITATION_PATTERN.search(visible_text):
        return None
    match = _INLINE_PAGE_NUMBER_TOKEN_PATTERN.search(visible_text)
    if match is None or len(visible_text) > 80:
        return None
    for candidate in (
        _normalize_running_header_candidate(visible_text[: match.start()]),
        _normalize_running_header_candidate(visible_text[match.end() :]),
    ):
        if candidate is None:
            continue
        if repeated_running_header_candidates.get(candidate, 0) >= 3:
            return "page_number_island_with_repeated_running_header_context"
    return None


def _normalize_running_header_candidate(text: str) -> str | None:
    candidate = re.sub(r"\s+", " ", text.strip(" -–—|,;:.\t"))
    if not candidate:
        return None
    if len(candidate) > 40:
        return None
    word_count = len(candidate.split())
    if word_count == 0 or word_count > 5:
        return None
    if not any(char.isalpha() for char in candidate):
        return None
    return candidate.casefold()


def _is_accepted_long_title_shape(text: str) -> bool:
    if text.endswith(":"):
        return True
    if _NUMBERED_APPENDIX_OR_INDEX_PATTERN.match(text):
        return True
    if _SCRIPTURE_REFERENCE_PATTERN.search(text):
        return True
    if any(symbol in text for symbol in ".!?"):
        return False
    words = _TITLE_CASE_OR_ALL_CAPS_WORD_PATTERN.findall(text)
    if not words:
        return False
    titled_or_upper = sum(1 for word in words if word.isupper() or word[:1].isupper())
    return titled_or_upper >= max(3, int(len(words) * 0.7))


def _has_chapter_like_tokens(text: str) -> bool:
    normalized_text = text.strip()
    if _CHAPTER_TOKEN_PATTERN.search(normalized_text):
        return True
    return bool(_LEADING_NUMBERING_PATTERN.match(normalized_text))


def _looks_like_quote_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return bool(_QUOTE_LIKE_LINE_PATTERN.match(stripped))
