from __future__ import annotations

from dataclasses import dataclass
import re

from docxaicorrector.structure.page_furniture_detection import detect_page_furniture_hits

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
_ATTRIBUTION_PATTERN = re.compile(r"^[\u2014\-\u2013]?\s*[A-ZА-ЯЁ][^.!?\n]{0,80}$")
_SENTENCE_START_PATTERN = re.compile(r"^[A-ZА-ЯЁ][^\n]*[.!?]")


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
    samples: list[StructureDetectorSample] = []
    for index, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip()
        stripped = line.strip()
        previous_context = _nearest_nonempty_line(lines, index - 2, step=-1)
        next_context = _nearest_nonempty_line(lines, index, step=1)
        heading_match = _HEADING_PATTERN.match(stripped)
        if not stripped:
            continue
        for hit in detect_page_furniture_hits(stripped):
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
        if any(hit.kind in {"page_number_island", "blank_page_marker", "intentionally_blank_marker"} for hit in detect_page_furniture_hits(stripped)):
            if not _is_standalone_blank_marker_line(stripped):
                samples.append(
                    StructureDetectorSample(
                        detector_id="inline_page_furniture_leakage",
                        line=index,
                        heading_level=_heading_level(heading_match),
                        text=stripped,
                        previous_context=previous_context,
                        next_context=next_context,
                        reason="page_furniture_visible_inline",
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
                    reason="heading_contains_body_sentence",
                )
            )
        if heading_match and len(heading_match.group(1)) == 1 and _looks_like_epigraph_attribution(heading_match.group(2)):
            samples.append(
                StructureDetectorSample(
                    detector_id="h1_epigraph_attribution_pattern",
                    line=index,
                    heading_level=1,
                    text=stripped,
                    previous_context=previous_context,
                    next_context=next_context,
                    reason="h1_matches_epigraph_attribution_shape",
                )
            )

    for left_index, left_line in enumerate(lines, start=1):
        left_match = _HEADING_PATTERN.match(left_line.strip())
        if not left_match or len(left_match.group(1)) != 1:
            continue
        right_index, right_line = _next_nonempty_index_and_line(lines, left_index)
        if right_index is None:
            samples.append(
                StructureDetectorSample(
                    detector_id="adjacent_h1_without_body",
                    line=left_index,
                    heading_level=1,
                    text=left_line.strip(),
                    previous_context=_nearest_nonempty_line(lines, left_index - 2, step=-1),
                    next_context="",
                    reason="terminal_h1_without_body",
                )
            )
            continue
        right_match = _HEADING_PATTERN.match(right_line.strip())
        if right_match and len(right_match.group(1)) == 1:
            samples.append(
                StructureDetectorSample(
                    detector_id="adjacent_h1_without_body",
                    line=left_index,
                    heading_level=1,
                    text=left_line.strip(),
                    previous_context=_nearest_nonempty_line(lines, left_index - 2, step=-1),
                    next_context=right_line.strip(),
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


def _next_nonempty_index_and_line(lines: list[str], current_line_number: int) -> tuple[int | None, str]:
    for index in range(current_line_number, len(lines)):
        stripped = lines[index].strip()
        if stripped:
            return index + 1, lines[index]
    return None, ""


def _is_standalone_blank_marker_line(line: str) -> bool:
    stripped = line.strip()
    hits = detect_page_furniture_hits(stripped)
    return bool(hits) and all(hit.start == 0 and hit.end == len(stripped) for hit in hits)


def _looks_like_heading_body_concat(heading_text: str) -> bool:
    text = heading_text.strip()
    if not text or text.endswith(":"):
        return False
    if len(text.split()) < 5:
        return False
    return bool(_SENTENCE_START_PATTERN.match(text))


def _looks_like_epigraph_attribution(heading_text: str) -> bool:
    text = heading_text.strip()
    if not text or len(text.split()) > 10:
        return False
    if any(symbol in text for symbol in ".!?"):
        return False
    return bool(_ATTRIBUTION_PATTERN.match(text))
