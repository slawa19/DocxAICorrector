from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

PageFurnitureKind = Literal[
    "blank_page_marker",
    "intentionally_blank_marker",
    "running_header_candidate",
    "page_number_island",
]

_WHITESPACE_PATTERN = re.compile(r"\s+")
_PAGE_FURNITURE_PHRASES = (
    "this page intentionally left blank",
    "эта страница намеренно оставлена пустой",
    "page intentionally left blank",
    "intentionally blank",
    "intentionally left blank",
)
_PAGE_NUMBER_ISLAND_PATTERN = re.compile(r"^\s*(?:page\s+)?[0-9ivxlcdm]+\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class PageFurnitureHit:
    kind: PageFurnitureKind
    phrase: str
    start: int
    end: int
    matched_text: str
    normalized_text: str


def page_furniture_phrases() -> tuple[str, ...]:
    return _PAGE_FURNITURE_PHRASES


def collapse_page_furniture_whitespace(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", str(text or "").strip())


def detect_page_furniture_hits(text: str) -> tuple[PageFurnitureHit, ...]:
    normalized_text = collapse_page_furniture_whitespace(text)
    if not normalized_text:
        return ()
    lowered_text = normalized_text.casefold()
    hits: list[PageFurnitureHit] = []
    seen_ranges: set[tuple[int, int, str]] = set()
    for phrase in _PAGE_FURNITURE_PHRASES:
        start = lowered_text.find(phrase)
        if start < 0:
            continue
        end = start + len(phrase)
        kind: PageFurnitureKind = (
            "blank_page_marker" if phrase == "this page intentionally left blank" else "intentionally_blank_marker"
        )
        key = (start, end, kind)
        if key in seen_ranges:
            continue
        seen_ranges.add(key)
        hits.append(
            PageFurnitureHit(
                kind=kind,
                phrase=phrase,
                start=start,
                end=end,
                matched_text=normalized_text[start:end],
                normalized_text=normalized_text,
            )
        )
    if _PAGE_NUMBER_ISLAND_PATTERN.match(normalized_text):
        hits.append(
            PageFurnitureHit(
                kind="page_number_island",
                phrase=normalized_text,
                start=0,
                end=len(normalized_text),
                matched_text=normalized_text,
                normalized_text=normalized_text,
            )
        )
    return tuple(sorted(hits, key=lambda hit: (hit.start, hit.end, hit.kind)))


def find_candidate_page_artifact_leading_hit(text: str, *, preview_chars: int = 120, min_remainder_chars: int = 6) -> PageFurnitureHit | None:
    normalized_text = collapse_page_furniture_whitespace(text)
    if not normalized_text:
        return None
    for hit in detect_page_furniture_hits(normalized_text):
        if hit.kind not in {"blank_page_marker", "intentionally_blank_marker"}:
            continue
        if hit.start >= preview_chars:
            continue
        if len(normalized_text[hit.end :].strip()) < min_remainder_chars:
            continue
        return hit
    return None
