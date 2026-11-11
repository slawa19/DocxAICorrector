"""Spec 072 FR-003 / FR-006 — the paragraph plan of the narration document (``.tts.docx``).

Pure: no python-docx, no Streamlit, no I/O. The input is the ordered narration groups of
the ``.tts.txt`` assembly (``pipeline/narration_postprocess``, spec 072 FR-001), read
through the ``NarrationGroupLike`` protocol so this module depends on no concrete class.
The output says, for each paragraph of the document, its style and exact text, which
assembly ids it carries, which heading series were merged, and the ElevenLabs Studio limit
counters — everything the DOCX renderer, the event and the runner report need.

FR-003 as amended by the owner on 2026-11-10 (Studio makes a chapter of EVERY Word heading,
any level) and by spec 074 FR-101/FR-102 (the chapter level is decided by the Studio limit):

* (а) The chapter level is the topmost heading level at which no chapter is longer than
  ``STUDIO_MAX_CHAPTER_PARAGRAPHS`` (spec 074 FR-101; spec 072 took the topmost level present
  unconditionally, which is the same answer whenever that level fits). A chapter is opened by every
  series of that level or above; the paragraphs before the first one are a chapter of their own, and
  a chapter is counted without its own ``Heading 1``. When no level fits, the chapter level is the
  deepest level present (the exceeded limit is reported, as before). A series at or above the
  chapter level is ``Heading 1`` (FR-102); every deeper heading is ``Normal``. The chapter level is a
  THRESHOLD: ``Heading 1`` is the style of every series AT OR ABOVE it, not only at it.
* (б) Consecutive heading groups with a level form a series while each next member is not
  deeper than the shallowest member already in it; a deeper heading starts a new series.
  A series is ONE paragraph: parts joined with ``". "`` (a part already ending in ``.``
  gets only the space), level = the series minimum, style by (а). This applies to every
  series, including one below the chapter level, which becomes one ``Normal`` paragraph
  (plan deviation О-1).
* (в) Every series of two or more members is recorded as a ``HeadingMerge`` by id.
* (г) A ``heading`` group without a level is ``Normal`` and neither starts nor continues a
  series (Constitution VII: no source signal, no repair).

The rule reads role and level only, never the words of the text (Constitution VII).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol

NARRATION_DOCUMENT_STYLE_HEADING_1: Literal["Heading 1"] = "Heading 1"
NARRATION_DOCUMENT_STYLE_NORMAL: Literal["Normal"] = "Normal"
NarrationDocumentStyle = Literal["Heading 1", "Normal"]

# ElevenLabs Studio project limits (spec 072, "Что известно про ElevenLabs Studio"). Strictly
# greater than the limit is an excess; exactly at the limit is not.
STUDIO_MAX_CHAPTERS = 500
STUDIO_MAX_CHAPTER_PARAGRAPHS = 400
STUDIO_MAX_PARAGRAPH_CHARS = 5000
STUDIO_LIMIT_CHAPTERS = "chapters"
STUDIO_LIMIT_CHAPTER_PARAGRAPHS = "chapter_paragraphs"
STUDIO_LIMIT_PARAGRAPH_CHARS = "paragraph_chars"

_HEADING_ROLE = "heading"
_MIN_HEADING_LEVEL = 1
_MAX_HEADING_LEVEL = 6
_PART_SEPARATOR = ". "


class NarrationGroupLike(Protocol):
    """One paragraph of the ``.tts.txt`` assembly: its record ids, role, heading level and text."""

    @property
    def paragraph_ids(self) -> Sequence[str]: ...

    @property
    def role(self) -> str: ...

    @property
    def heading_level(self) -> int | None: ...

    @property
    def text(self) -> str: ...


@dataclass(frozen=True)
class NarrationDocumentParagraph:
    style: NarrationDocumentStyle
    text: str
    paragraph_ids: tuple[str, ...]
    # The series minimum for a paragraph made of headings with a level (also when it became
    # ``Normal``); ``None`` for body paragraphs and level-less headings.
    source_heading_level: int | None


@dataclass(frozen=True)
class HeadingMerge:
    paragraph_ids: tuple[str, ...]
    levels: tuple[int, ...]
    style: NarrationDocumentStyle


@dataclass(frozen=True)
class StudioLimits:
    heading1_count: int
    # Segments for the 400-paragraph limit: the paragraphs before the first ``Heading 1`` are
    # a chapter of their own when there are any; a book without ``Heading 1`` is one chapter.
    chapter_count_for_limits: int
    # Paragraphs of the longest chapter, not counting its ``Heading 1``.
    max_chapter_paragraph_count: int
    # ``len(text)`` of the longest plan paragraph, after merges.
    max_paragraph_chars: int
    # Subset of ("chapters", "chapter_paragraphs", "paragraph_chars"), in that order.
    exceeded: tuple[str, ...]


@dataclass(frozen=True)
class NarrationDocumentPlan:
    paragraphs: tuple[NarrationDocumentParagraph, ...]
    chapter_level: int | None
    heading_levels_present: tuple[int, ...]
    heading_merges: tuple[HeadingMerge, ...]
    # Plan paragraphs made of headings deeper than the chapter level and written ``Normal``
    # (a merged series counts once; level-less headings are not counted).
    demoted_heading_count: int
    studio_limits: StudioLimits


def _group_heading_level(group: NarrationGroupLike) -> int | None:
    """The heading level a group takes part in series with, or ``None`` (body, no level)."""

    if group.role.strip().casefold() != _HEADING_ROLE:
        return None
    level = group.heading_level
    if isinstance(level, bool) or not isinstance(level, int):
        return None
    if not _MIN_HEADING_LEVEL <= level <= _MAX_HEADING_LEVEL:
        return None
    return level


def _join_series_text(parts: Sequence[str]) -> str:
    joined = parts[0]
    for part in parts[1:]:
        joined += (" " if joined.endswith(".") else _PART_SEPARATOR) + part
    return joined


def _chapter_sizes(opens_chapter: Iterable[bool]) -> list[int]:
    """Paragraph counts of the chapters Studio sees, for a plan given as one flag per paragraph: ``True`` when the
    paragraph is a chapter opener (``Heading 1``). An opener is not counted in its own chapter; the paragraphs before
    the first opener are a chapter of their own; a plan without paragraphs has no chapter."""

    sizes: list[int] = []
    current: int | None = None  # paragraphs of the open chapter; None until one is open
    for opens in opens_chapter:
        if opens:
            if current is not None:
                sizes.append(current)
            current = 0
        else:
            current = 1 if current is None else current + 1
    if current is not None:
        sizes.append(current)
    return sizes


def _studio_limits(paragraphs: Sequence[NarrationDocumentParagraph]) -> StudioLimits:
    heading1_count = sum(1 for paragraph in paragraphs if paragraph.style == NARRATION_DOCUMENT_STYLE_HEADING_1)
    chapter_sizes = _chapter_sizes(paragraph.style == NARRATION_DOCUMENT_STYLE_HEADING_1 for paragraph in paragraphs)

    max_chapter_paragraph_count = max(chapter_sizes, default=0)
    max_paragraph_chars = max((len(paragraph.text) for paragraph in paragraphs), default=0)
    exceeded: list[str] = []
    if heading1_count > STUDIO_MAX_CHAPTERS:
        exceeded.append(STUDIO_LIMIT_CHAPTERS)
    if max_chapter_paragraph_count > STUDIO_MAX_CHAPTER_PARAGRAPHS:
        exceeded.append(STUDIO_LIMIT_CHAPTER_PARAGRAPHS)
    if max_paragraph_chars > STUDIO_MAX_PARAGRAPH_CHARS:
        exceeded.append(STUDIO_LIMIT_PARAGRAPH_CHARS)
    return StudioLimits(
        heading1_count=heading1_count,
        chapter_count_for_limits=len(chapter_sizes),
        max_chapter_paragraph_count=max_chapter_paragraph_count,
        max_paragraph_chars=max_paragraph_chars,
        exceeded=tuple(exceeded),
    )


def _chapter_level(drafts: Sequence[NarrationDocumentParagraph], levels_present: Sequence[int]) -> int | None:
    """Spec 074 FR-101: the topmost level at which no chapter is longer than the Studio limit.

    ``levels_present`` is sorted from the topmost (1) down. For a level ``L`` a series with a level ``<= L`` opens a
    chapter (``_chapter_sizes``). Nothing fits -> the deepest level present; no levels -> ``None``. Only roles, levels
    and counts are read, never words (Constitution VII).
    """

    for level in levels_present:
        sizes = _chapter_sizes(
            draft.source_heading_level is not None and draft.source_heading_level <= level for draft in drafts
        )
        if max(sizes, default=0) <= STUDIO_MAX_CHAPTER_PARAGRAPHS:
            return level
    return levels_present[-1] if levels_present else None


def build_narration_document_plan(groups: Sequence[NarrationGroupLike]) -> NarrationDocumentPlan:
    """The ``.tts.docx`` paragraph plan of the narration groups (FR-003, FR-006; spec 074 FR-101...FR-104).

    Two passes over ONE source of truth: the series and their texts and ids are built first, with the style
    still open; the chapter level is chosen from them (``_chapter_level``); the styles follow from that level and
    from nothing else (FR-104).
    """

    levels = [level for level in (_group_heading_level(group) for group in groups) if level is not None]

    drafts: list[NarrationDocumentParagraph] = []
    merge_members: list[tuple[tuple[str, ...], tuple[int, ...]]] = []
    series: list[tuple[NarrationGroupLike, int]] = []

    def close_series() -> None:
        if not series:
            return
        series_level = min(level for _, level in series)
        paragraph_ids = tuple(pid for group, _ in series for pid in group.paragraph_ids)
        drafts.append(
            NarrationDocumentParagraph(
                style=NARRATION_DOCUMENT_STYLE_NORMAL,
                text=_join_series_text([group.text for group, _ in series]),
                paragraph_ids=paragraph_ids,
                source_heading_level=series_level,
            )
        )
        if len(series) > 1:
            merge_members.append((paragraph_ids, tuple(level for _, level in series)))
        series.clear()

    for group in groups:
        level = _group_heading_level(group)
        if level is None:
            close_series()
            drafts.append(
                NarrationDocumentParagraph(
                    style=NARRATION_DOCUMENT_STYLE_NORMAL,
                    text=group.text,
                    paragraph_ids=tuple(group.paragraph_ids),
                    source_heading_level=None,
                )
            )
            continue
        if series and level > min(member_level for _, member_level in series):
            close_series()
        series.append((group, level))
    close_series()

    chapter_level = _chapter_level(drafts, sorted(set(levels)))
    style_of_series: dict[tuple[str, ...], NarrationDocumentStyle] = {}
    paragraphs: list[NarrationDocumentParagraph] = []
    demoted_heading_count = 0
    for draft in drafts:
        series_level = draft.source_heading_level
        if series_level is None:
            paragraphs.append(draft)
            continue
        style: NarrationDocumentStyle = (
            NARRATION_DOCUMENT_STYLE_HEADING_1
            if chapter_level is not None and series_level <= chapter_level
            else NARRATION_DOCUMENT_STYLE_NORMAL
        )
        style_of_series[draft.paragraph_ids] = style
        if style == NARRATION_DOCUMENT_STYLE_NORMAL:
            demoted_heading_count += 1
        paragraphs.append(replace(draft, style=style))
    merges = [
        HeadingMerge(paragraph_ids=paragraph_ids, levels=member_levels, style=style_of_series[paragraph_ids])
        for paragraph_ids, member_levels in merge_members
    ]

    return NarrationDocumentPlan(
        paragraphs=tuple(paragraphs),
        chapter_level=chapter_level,
        heading_levels_present=tuple(sorted(set(levels))),
        heading_merges=tuple(merges),
        demoted_heading_count=demoted_heading_count,
        studio_limits=_studio_limits(paragraphs),
    )
