"""Spec 073 FR-007 (owner decision D-4) — the book file for the narration tool, ``<stem>.narration.json``.

Pure: no python-docx, no Streamlit, no I/O. The input is the ordered narration groups of the
``.tts.txt`` assembly (``pipeline/narration_postprocess``, spec 072 FR-001, with the spec 073
FR-006 scene-break mark), read through the ``NarrationBookGroupLike`` protocol, and the spec 072
paragraph plan of the SAME groups (``pipeline/narration_document.build_narration_document_plan``),
whose series and chapters this module reads instead of deciding them again. The output is the
JSON object of ``specs/073-narration-for-the-ear/contracts/narration-book.md`` (schema version 1)
plus the counters the late phase reports.

The rules (``data-model.md`` §7, research R9):

* **Segments are the groups.** One segment per group, in order; its text is ``group.text``
  byte for byte, so ``"\\n\\n".join(segment texts)`` IS the ``.tts.txt`` (SC-006).
* **The plan and the groups walk in step.** A plan paragraph with ``source_heading_level`` (a
  heading series) absorbs ``len(paragraph_ids)`` groups — a heading group is always one record,
  since the assembly only joins body + body — any other plan paragraph absorbs one group. The
  ids of the absorbed groups must be exactly the plan paragraph's ids; any departure is a
  ``ValueError`` (the late phase turns it into a WARNING and ships the book without the file).
* **Chapters** — the 072 rule (``StudioLimits.chapter_count_for_limits``): a ``Heading 1`` plan
  paragraph opens a chapter titled with that paragraph's text (the merged series "A. B"); the
  segments before the first one form a chapter with ``title: null``.
* **Pause kinds.** The last segment of a series that became ``Heading 1`` — ``chapter``; of a
  series that became ``Normal`` — ``heading``; the segment before a segment with
  ``after_scene_break`` — ``scene_break``. A coincidence keeps the kind with the longer seconds
  (a tie keeps the series kind); the last segment of the book has no pause; body paragraphs have
  none (the tool sets the paragraph pause). A heading without a level is no series (072 (г)) and
  gets no series pause.

The rules read role, level and the scene-break mark only, never the words (Constitution VII).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from docxaicorrector.pipeline.narration_document import (
    NARRATION_DOCUMENT_STYLE_HEADING_1,
    NarrationDocumentPlan,
    NarrationGroupLike,
)

NARRATION_BOOK_SCHEMA_VERSION = 1
NARRATION_BOOK_PRODUCER_NAME = "DocxAICorrector"
# The closed top-level key set of schema version 1, in file order. A new top-level key is a new
# schema version: the narration tool stops the import on an unknown one.
NARRATION_BOOK_TOP_LEVEL_KEYS = (
    "schema_version",
    "producer",
    "book",
    "chapter_heading_level",
    "chapters",
    "segments",
    "reading_glossary",
    "stats",
)

NARRATION_PAUSE_CHAPTER = "chapter"
NARRATION_PAUSE_HEADING = "heading"
NARRATION_PAUSE_SCENE_BREAK = "scene_break"
NARRATION_PAUSE_KINDS = (NARRATION_PAUSE_CHAPTER, NARRATION_PAUSE_HEADING, NARRATION_PAUSE_SCENE_BREAK)
# Default seconds written into ``pause_after.seconds``; the tool may replace them with its own book
# settings without regenerating. Measured on MiniMax (``D:\\Temp\\docxai-research\\minimax-tts\\RESEARCH.md``,
# "Проба разметки через API"): marks of 1.5 / 0.8 / 2.0 s gave 1.88 / 1.24 / 2.48 s of silence.
NARRATION_PAUSE_DEFAULT_SECONDS: Mapping[str, float] = MappingProxyType(
    {NARRATION_PAUSE_CHAPTER: 1.5, NARRATION_PAUSE_HEADING: 0.8, NARRATION_PAUSE_SCENE_BREAK: 2.0}
)


class NarrationBookGroupLike(NarrationGroupLike, Protocol):
    """One paragraph of the ``.tts.txt`` assembly, with the FR-006 scene-break mark."""

    @property
    def after_scene_break(self) -> bool: ...


class NarrationBookGlossaryEntryLike(Protocol):
    """One accepted reading-glossary entry (FR-004)."""

    @property
    def abbreviation(self) -> str: ...

    @property
    def reading(self) -> str: ...


@dataclass(frozen=True)
class NarrationBookProducer:
    # Git SHA of the code that built the file, or ``None`` outside a git checkout (never invented).
    version: str | None
    run_id: str
    # UTC, ISO 8601 with ``Z``, seconds.
    produced_at: str


@dataclass(frozen=True)
class NarrationBookSource:
    source_name: str
    source_token: str


@dataclass(frozen=True)
class NarrationBook:
    # The JSON object in contract key order (plain dicts and lists, so it round-trips).
    payload: Mapping[str, object]
    # The pause kind of each segment, in group order (``None`` — no pause).
    pause_kinds: tuple[str | None, ...]
    # Every key of ``NARRATION_PAUSE_KINDS``, always.
    pause_counts: Mapping[str, int]
    chapter_count: int

    def to_json(self) -> str:
        return json.dumps(self.payload, ensure_ascii=False, indent=1) + "\n"


def _walk_plan(
    groups: Sequence[NarrationBookGroupLike], plan: NarrationDocumentPlan
) -> tuple[list[str | None], dict[int, str]]:
    """Walk the plan and the groups in step.

    Returns the series pause kind of each group and, for each group that opens a chapter (the
    first group of a ``Heading 1`` plan paragraph), the chapter title. Raises ``ValueError``
    when the plan is not the plan of these groups.
    """

    series_kinds: list[str | None] = [None] * len(groups)
    chapter_titles: dict[int, str] = {}
    position = 0
    for paragraph_number, paragraph in enumerate(plan.paragraphs, start=1):
        is_series = paragraph.source_heading_level is not None
        span = len(paragraph.paragraph_ids) if is_series else 1
        absorbed = groups[position : position + span]
        absorbed_ids = tuple(pid for group in absorbed for pid in group.paragraph_ids)
        if len(absorbed) != span or absorbed_ids != tuple(paragraph.paragraph_ids):
            raise ValueError(
                f"narration book: plan paragraph {paragraph_number} does not match groups "
                f"{position + 1}..{position + span} of {len(groups)}"
            )
        is_chapter = paragraph.style == NARRATION_DOCUMENT_STYLE_HEADING_1
        if is_chapter:
            chapter_titles[position] = paragraph.text
        if is_series:
            series_kinds[position + span - 1] = NARRATION_PAUSE_CHAPTER if is_chapter else NARRATION_PAUSE_HEADING
        position += span
    if position != len(groups):
        raise ValueError(f"narration book: the plan covers {position} of {len(groups)} group(s)")
    return series_kinds, chapter_titles


def _pause_kind(candidates: Sequence[str], seconds: Mapping[str, float]) -> str | None:
    """The kind with the longest pause; the first candidate wins a tie."""

    chosen: str | None = None
    for kind in candidates:
        if chosen is None or seconds[kind] > seconds[chosen]:
            chosen = kind
    return chosen


def build_narration_book(
    *,
    groups: Sequence[NarrationBookGroupLike],
    plan: NarrationDocumentPlan,
    glossary_entries: Sequence[NarrationBookGlossaryEntryLike],
    producer: NarrationBookProducer,
    source: NarrationBookSource,
    excluded_count: int,
    excluded_by_reason: Mapping[str, int],
    pause_seconds: Mapping[str, float] = NARRATION_PAUSE_DEFAULT_SECONDS,
) -> NarrationBook:
    """The ``<stem>.narration.json`` object of the narration groups and their 072 plan (FR-007)."""

    if not groups:
        raise ValueError("narration book: no narration groups")
    seconds = {kind: float(pause_seconds[kind]) for kind in NARRATION_PAUSE_KINDS}
    series_kinds, chapter_titles = _walk_plan(groups, plan)

    pause_kinds: list[str | None] = []
    last = len(groups) - 1
    for index in range(len(groups)):
        if index == last:
            pause_kinds.append(None)
            continue
        candidates: list[str] = []
        series_kind = series_kinds[index]
        if series_kind is not None:
            candidates.append(series_kind)
        if groups[index + 1].after_scene_break:
            candidates.append(NARRATION_PAUSE_SCENE_BREAK)
        pause_kinds.append(_pause_kind(candidates, seconds))

    chapters: list[dict[str, object]] = []
    chapter_segments: list[list[int]] = []
    segments: list[dict[str, object]] = []
    for index, group in enumerate(groups):
        if index == 0 or index in chapter_titles:
            chapter_segments.append([])
            chapters.append(
                {
                    "ordinal": len(chapters) + 1,
                    "title": chapter_titles.get(index),
                    "segment_ordinals": chapter_segments[-1],
                }
            )
        ordinal = index + 1
        chapter_segments[-1].append(ordinal)
        kind = pause_kinds[index]
        segments.append(
            {
                "ordinal": ordinal,
                "chapter_ordinal": len(chapters),
                "role": group.role,
                "heading_level": group.heading_level,
                "text": group.text,
                "after_scene_break": bool(group.after_scene_break),
                "pause_after": None if kind is None else {"kind": kind, "seconds": seconds[kind]},
                "source_paragraph_ids": list(group.paragraph_ids),
            }
        )

    if len(chapters) != plan.studio_limits.chapter_count_for_limits:
        raise ValueError(
            f"narration book: {len(chapters)} chapter(s) against the plan's "
            f"{plan.studio_limits.chapter_count_for_limits}"
        )

    pause_counts = {kind: sum(1 for value in pause_kinds if value == kind) for kind in NARRATION_PAUSE_KINDS}
    reading_glossary = [{"abbreviation": entry.abbreviation, "reading": entry.reading} for entry in glossary_entries]
    payload: dict[str, object] = {
        "schema_version": NARRATION_BOOK_SCHEMA_VERSION,
        "producer": {
            "name": NARRATION_BOOK_PRODUCER_NAME,
            "version": producer.version,
            "run_id": producer.run_id,
            "produced_at": producer.produced_at,
        },
        "book": {"source_name": source.source_name, "source_token": source.source_token},
        "chapter_heading_level": plan.chapter_level,
        "chapters": chapters,
        "segments": segments,
        "reading_glossary": reading_glossary,
        "stats": {
            "char_count": len("\n\n".join(group.text for group in groups)),
            "segment_count": len(segments),
            "chapter_count": len(chapters),
            "heading1_count": plan.studio_limits.heading1_count,
            "scene_break_count": sum(1 for group in groups if group.after_scene_break),
            "pause_counts": dict(pause_counts),
            "excluded_count": excluded_count,
            "excluded_by_reason": dict(excluded_by_reason),
            "reading_glossary_entry_count": len(reading_glossary),
        },
    }
    return NarrationBook(
        payload=payload,
        pause_kinds=tuple(pause_kinds),
        pause_counts=MappingProxyType(pause_counts),
        chapter_count=len(chapters),
    )
