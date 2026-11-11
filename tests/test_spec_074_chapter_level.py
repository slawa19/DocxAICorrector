"""Spec 074 group 1xx (FR-101...FR-104) -- the chapter level is the topmost level whose chapters fit Studio.

``pipeline/narration_document.build_narration_document_plan`` picks the chapter level of the narration plan:
the topmost (shallowest) heading level at which no chapter is longer than ``STUDIO_MAX_CHAPTER_PARAGRAPHS``
(FR-101); a series at or above that level is ``Heading 1`` (FR-102); the DOCX, the event and the book file read the
same plan (FR-103); only styles change (FR-104).

Every book here is SYNTHETIC and built by the test (Constitution VII): the rule reads roles, levels and the number of
paragraphs, never words. The expected answers of the structure matrix S1...S10 are copied from the spec (section
"Матрица структур"), where they were written BEFORE the implementation; they are not derived from the code.

* the CHARACTERIZATION block pins what must not change (a book whose top level fits Studio keeps its levels, chapters
  and styles) -- it is green before and after the change;
* the NEW BEHAVIOUR block fails without the change.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Sequence
from dataclasses import dataclass

import docx
import pytest

import docxaicorrector.pipeline.narration_document as narration_document
from docxaicorrector.generation.narration_pdf import NarrationPdfOutcome
from docxaicorrector.pipeline.narration_book import NarrationBookProducer, NarrationBookSource
from docxaicorrector.pipeline.narration_document import (
    NARRATION_DOCUMENT_STYLE_HEADING_1,
    NARRATION_DOCUMENT_STYLE_NORMAL,
    STUDIO_MAX_CHAPTER_PARAGRAPHS,
    NarrationDocumentPlan,
    build_narration_document_plan,
)
from docxaicorrector.pipeline.narration_exports import NarrationBookInputs, build_narration_exports
from docxaicorrector.pipeline.narration_postprocess import NarrationGroup

pytestmark = pytest.mark.unit_contract

H1 = NARRATION_DOCUMENT_STYLE_HEADING_1
NORMAL = NARRATION_DOCUMENT_STYLE_NORMAL

H = "H"
P = "P"

# A structure is a list of ("H", level) -- one heading group -- and ("P", n) -- n body paragraphs.
Structure = Sequence[tuple[str, int]]


def _groups(structure: Structure) -> list[NarrationGroup]:
    groups: list[NarrationGroup] = []
    for kind, value in structure:
        if kind == H:
            number = len(groups)
            groups.append(
                NarrationGroup(paragraph_ids=(f"g{number}",), role="heading", heading_level=value, text=f"Заголовок {number}")
            )
        else:
            for _ in range(value):
                number = len(groups)
                groups.append(NarrationGroup(paragraph_ids=(f"g{number}",), role="body", heading_level=None, text=f"Текст {number}."))
    return groups


def _plan(structure: Structure) -> NarrationDocumentPlan:
    return build_narration_document_plan(_groups(structure))


def _chapter_sizes(plan: NarrationDocumentPlan) -> list[int]:
    """Chapters as Studio sees them, read from the plan styles only: a ``Heading 1`` opens a chapter, the text
    before the first one is a chapter of its own; the size does not count the heading."""

    sizes: list[int] = []
    current: int | None = None
    for paragraph in plan.paragraphs:
        if paragraph.style == H1:
            if current is not None:
                sizes.append(current)
            current = 0
        else:
            current = 1 if current is None else current + 1
    if current is not None:
        sizes.append(current)
    return sizes


# --- The structure matrix: the answers are the spec's table, written before the implementation -------------------

# name -> (structure, chapter level, chapter sizes); the rows S1...S10 of the spec.
_MATRIX: dict[str, tuple[Structure, int | None, list[int]]] = {
    "S1_two_h1_parts_of_300": ([(H, 1), (P, 300), (H, 1), (P, 300)], 1, [300, 300]),
    "S2_two_h1_parts_450_and_50": ([(H, 1), (P, 450), (H, 1), (P, 50)], 1, [450, 50]),
    "S3_big_h1_with_three_h2_and_two_short_h1": (
        [(H, 1), (H, 2), (P, 100), (H, 2), (P, 100), (H, 2), (P, 100), (H, 1), (P, 50), (H, 1), (P, 50)],
        1,
        [303, 50, 50],
    ),
    "S4_collection_of_three_h1_articles": ([(H, 1), (P, 80)] * 3, 1, [80, 80, 80]),
    "S5_h1_title_only_then_three_h2": ([(H, 1), (H, 2), (P, 80), (H, 2), (P, 80), (H, 2), (P, 80)], 1, [243]),
    "S6_ten_h1_sections_of_5": ([(H, 1), (P, 5)] * 10, 1, [5] * 10),
    "S7_uneven_book_goes_down_to_h3": (
        [(H, 1), (H, 2), (H, 3), (P, 150), (H, 3), (P, 150), (H, 3), (P, 150), (H, 1), (P, 50), (H, 1), (P, 50)],
        3,
        [0, 0, 150, 150, 150, 50, 50],
    ),
    "S8_two_h1_parts_each_with_two_h2_of_250": (
        [(H, 1), (H, 2), (P, 250), (H, 2), (P, 250), (H, 1), (H, 2), (P, 250), (H, 2), (P, 250)],
        2,
        [0, 250, 250, 0, 250, 250],
    ),
    "S10_one_h1_and_500_paragraphs": ([(H, 1), (P, 500)], 1, [500]),
}

# The rows whose answer is the same as ``min(levels)`` gave (the top level fits, or nothing fits anywhere): characterization.
_MATRIX_UNCHANGED = (
    "S1_two_h1_parts_of_300",
    "S2_two_h1_parts_450_and_50",
    "S3_big_h1_with_three_h2_and_two_short_h1",
    "S4_collection_of_three_h1_articles",
    "S5_h1_title_only_then_three_h2",
    "S6_ten_h1_sections_of_5",
    "S10_one_h1_and_500_paragraphs",
)
# The rows the new rule changes.
_MATRIX_CHANGED = ("S7_uneven_book_goes_down_to_h3", "S8_two_h1_parts_each_with_two_h2_of_250")


@pytest.mark.parametrize("name", _MATRIX_UNCHANGED)
def test_matrix_rows_where_the_top_level_already_gave_the_answer(name: str) -> None:
    structure, level, sizes = _MATRIX[name]

    plan = _plan(structure)

    assert plan.chapter_level == level
    assert _chapter_sizes(plan) == sizes


@pytest.mark.parametrize("name", _MATRIX_CHANGED)
def test_matrix_rows_where_a_deeper_level_is_needed(name: str) -> None:
    structure, level, sizes = _MATRIX[name]

    plan = _plan(structure)

    assert plan.chapter_level == level
    assert _chapter_sizes(plan) == sizes


def test_matrix_s9_no_headings_has_no_chapter_level() -> None:
    plan = _plan([(P, 120)])

    assert plan.chapter_level is None
    assert plan.studio_limits.heading1_count == 0
    assert plan.studio_limits.chapter_count_for_limits == 1
    assert plan.studio_limits.max_chapter_paragraph_count == 120
    assert plan.heading_levels_present == ()


def test_matrix_s2_and_s10_keep_the_event_when_nothing_fits() -> None:
    # No level fits (S2: the only level is over the limit; S10: no inner heading): the fallback keeps the book
    # as today and the limit stays exceeded, so the existing event fires.
    for name in ("S2_two_h1_parts_450_and_50", "S10_one_h1_and_500_paragraphs"):
        plan = _plan(_MATRIX[name][0])
        assert plan.studio_limits.exceeded == ("chapter_paragraphs",)


# --- Characterization: what must not change ------------------------------------------------------------------------


def test_a_book_of_many_h1_chapters_keeps_its_level_and_styles() -> None:
    # The shape of a full book (23 chapters under H1, H2 and H3 sections inside, every chapter far under the limit).
    structure: list[tuple[str, int]] = []
    for _ in range(23):
        structure += [(H, 1), (P, 3), (H, 2), (P, 20), (H, 3), (P, 5), (H, 2), (P, 20)]
    plan = _plan(structure)

    assert plan.chapter_level == 1
    assert plan.studio_limits.heading1_count == 23
    assert len(_chapter_sizes(plan)) == 23
    assert max(_chapter_sizes(plan)) <= STUDIO_MAX_CHAPTER_PARAGRAPHS
    assert [p.style for p in plan.paragraphs if p.source_heading_level == 1] == [H1] * 23
    assert {p.style for p in plan.paragraphs if p.source_heading_level in (2, 3)} == {NORMAL}


def test_an_excerpt_of_one_chapter_stays_one_chapter() -> None:
    # An excerpt: one H1, several deeper headings, 103 paragraphs -- under the limit, so the top level stays.
    structure: Structure = [(H, 1), (P, 20), (H, 2), (P, 30), (H, 3), (P, 20), (H, 2), (P, 30)]

    plan = _plan(structure)

    assert plan.chapter_level == 1
    assert _chapter_sizes(plan) == [103]  # the deeper headings are paragraphs of the one chapter
    assert [p.style for p in plan.paragraphs if p.source_heading_level == 2] == [NORMAL, NORMAL]


def test_a_deeper_only_book_keeps_its_top_level() -> None:
    # No H1 at all, H3 is the topmost level present and the chapters fit: the level is 3, as before.
    plan = _plan([(H, 3), (P, 10), (H, 3), (P, 10), (H, 4), (P, 10)])

    assert plan.chapter_level == 3
    assert _chapter_sizes(plan) == [10, 21]
    assert plan.demoted_heading_count == 1


# --- FR-101: the topmost level at which every chapter fits Studio ---------------------------------------------------


def test_fr101_the_second_level_when_the_first_gives_a_chapter_over_the_limit() -> None:
    # The shape of a book with a title and one big front section under H1 and the chapters under H2 (User Story 1).
    structure: list[tuple[str, int]] = [(H, 1), (H, 1), (P, 5)]
    for _ in range(9):
        structure += [(H, 2), (P, 120)]
    plan = _plan(structure)

    assert plan.chapter_level == 2
    assert plan.studio_limits.exceeded == ()
    assert max(_chapter_sizes(plan)) == 120


@pytest.mark.parametrize(
    ("body_size", "expected_level"),
    [(STUDIO_MAX_CHAPTER_PARAGRAPHS, 1), (STUDIO_MAX_CHAPTER_PARAGRAPHS + 1, 2)],
    ids=["at_the_limit_stays", "one_over_the_limit_goes_down"],
)
def test_fr101_the_limit_is_strict_greater_than(body_size: int, expected_level: int) -> None:
    # One H1 whose body is exactly the limit (or one more), split by an inner H2 in the middle.
    first = body_size // 2
    plan = _plan([(H, 1), (P, first), (H, 2), (P, body_size - first - 1)])

    assert plan.chapter_level == expected_level


def test_fr101_the_fallback_is_the_deepest_level_present_when_no_level_fits() -> None:
    plan = _plan([(H, 1), (P, 450), (H, 2), (P, 450), (H, 3), (P, 450)])

    assert plan.chapter_level == 3
    assert plan.studio_limits.exceeded == ("chapter_paragraphs",)


def test_fr101_the_first_level_that_fits_wins_even_when_a_deeper_one_would_fit_too() -> None:
    # Levels present 1, 2, 3: level 1 gives [450, 210] (over), level 2 gives [450, 200, 10] (450 is over too),
    # level 3 gives the same division as level 2 plus nothing -- the deepest present, the fallback.
    plan = _plan([(H, 1), (P, 450), (H, 2), (P, 200), (H, 1), (P, 10), (H, 3), (P, 5)])

    assert plan.chapter_level == 3
    assert plan.studio_limits.exceeded == ("chapter_paragraphs",)

    # The same book with a smaller first chapter: level 2 is the first that fits and the answer stops there.
    fitting = _plan([(H, 1), (P, 350), (H, 2), (P, 200), (H, 1), (P, 10), (H, 3), (P, 5)])

    assert fitting.chapter_level == 2
    assert _chapter_sizes(fitting) == [350, 200, 10 + 1 + 5]


def test_fr101_the_rule_reads_levels_and_counts_never_words() -> None:
    # The same structure with other texts gives the same answer: headings that look like "Chapter" or "Part" are no
    # signal, body paragraphs that look like headings are no headings (Constitution VII).
    structure = [(H, 1), (P, 450), (H, 2), (P, 100)]
    shaped = _groups(structure)
    renamed = [
        NarrationGroup(paragraph_ids=g.paragraph_ids, role=g.role, heading_level=g.heading_level, text="Глава 1" if g.role == "heading" else "# Раздел")
        for g in shaped
    ]

    assert build_narration_document_plan(renamed).chapter_level == build_narration_document_plan(shaped).chapter_level


def test_fr101_headings_without_a_level_take_no_part_in_the_choice() -> None:
    groups = _groups([(H, 1), (P, 200), (H, 2), (P, 150)])
    groups.append(NarrationGroup(paragraph_ids=("x",), role="heading", heading_level=None, text="Без уровня"))
    groups += [NarrationGroup(paragraph_ids=(f"y{i}",), role="body", heading_level=None, text="Текст.") for i in range(100)]

    plan = build_narration_document_plan(groups)

    # Level 1 gives one chapter of 200 + 1 + 150 + 1 + 100 = 452 (over); level 2 gives 200 and 150 + 1 + 100: the
    # level-less heading is a paragraph of the chapter, never an opener.
    assert plan.chapter_level == 2
    assert _chapter_sizes(plan) == [200, 251]
    assert plan.heading_levels_present == (1, 2)


# --- FR-102: a series at or above the chapter level is Heading 1 ---------------------------------------------------


def test_fr102_headings_above_the_chapter_level_are_heading_1() -> None:
    structure: list[tuple[str, int]] = [(H, 1), (H, 2), (P, 250), (H, 2), (P, 250)]
    plan = _plan(structure)

    assert plan.chapter_level == 2
    series = [(p.source_heading_level, p.style) for p in plan.paragraphs if p.source_heading_level is not None]
    assert series == [(1, H1), (2, H1), (2, H1)]
    # The title is a chapter of its own (0 paragraphs): the existing 072 behaviour, not removed by this spec.
    assert _chapter_sizes(plan) == [0, 250, 250]


def test_fr102_a_series_merged_from_levels_above_and_at_the_level_is_one_heading_1() -> None:
    # H2 then H1 form ONE series (a heading not deeper than the series minimum joins it); its level is 1.
    structure: list[tuple[str, int]] = [(H, 2), (H, 1), (P, 250), (H, 2), (P, 250), (H, 2), (P, 250)]
    plan = _plan(structure)

    assert plan.chapter_level == 2
    assert [p.style for p in plan.paragraphs if p.source_heading_level is not None] == [H1, H1, H1]
    assert plan.heading_merges[0].levels == (2, 1)
    assert plan.heading_merges[0].style == H1


def test_fr102_headings_deeper_than_the_level_are_normal_and_counted_as_demoted() -> None:
    structure: list[tuple[str, int]] = [(H, 1), (H, 2), (P, 250), (H, 3), (P, 20), (H, 2), (P, 250), (H, 3), (P, 20)]
    plan = _plan(structure)

    assert plan.chapter_level == 2
    assert [p.style for p in plan.paragraphs if p.source_heading_level == 3] == [NORMAL, NORMAL]
    assert plan.demoted_heading_count == 2


# --- FR-103: one source for the DOCX, the event and the book file --------------------------------------------------


_S8_STRUCTURE: Structure = _MATRIX["S8_two_h1_parts_each_with_two_h2_of_250"][0]


def _exports(structure: Structure):  # type: ignore[no-untyped-def]
    events: list[tuple[str, dict[str, object]]] = []

    def log_event(level: int, name: str, _message: str, **fields: object) -> None:
        assert level in (logging.INFO, logging.WARNING, logging.ERROR)
        events.append((name, dict(fields)))

    def export_pdf(_docx: bytes, *, stem: str) -> NarrationPdfOutcome:
        return NarrationPdfOutcome(pdf_bytes=b"%PDF-1.7", reason=None, seconds=0.0, detail="")

    exports = build_narration_exports(
        groups=_groups(structure),
        source_name="book.docx",
        log_event=log_event,
        export_pdf=export_pdf,
        book_inputs=NarrationBookInputs(
            glossary_entries=(),
            producer=NarrationBookProducer(version="0f1e2d3", run_id="run", produced_at="2026-11-11T10:00:00Z"),
            source=NarrationBookSource(source_name="book.docx", source_token="book.docx:1:00"),
            excluded_count=0,
            excluded_by_reason={},
        ),
    )
    return exports, events


def test_fr103_docx_event_and_book_file_follow_one_chapter_level() -> None:
    exports, events = _exports(_S8_STRUCTURE)

    plan = exports.plan
    assert plan is not None and plan.chapter_level == 2
    # DOCX: its Heading 1 paragraphs are the plan's (6 chapters: 2 parts and 4 sections, every one is Heading 1).
    assert exports.docx_bytes is not None
    document = docx.Document(io.BytesIO(exports.docx_bytes))
    style_names = [p.style.name if p.style is not None else None for p in document.paragraphs]
    heading_styles = [name for name in style_names if name != "Normal"]
    assert heading_styles == ["Heading 1"] * 6
    # Event fields.
    fields = exports.event_fields(artifact_paths={})
    assert fields["chapter_heading_level"] == 2
    assert fields["heading1_count"] == 6
    assert fields["demoted_heading_count"] == 0
    assert fields["studio_limits_exceeded"] == []
    assert fields["studio_max_chapter_paragraph_count"] == 250
    assert fields["narration_book_chapter_count"] == 6
    # Book file: chapter_heading_level is the threshold, chapters open on the Heading 1 paragraphs.
    assert exports.book is not None
    payload = exports.book.payload
    assert payload["chapter_heading_level"] == 2
    chapters = payload["chapters"]
    assert isinstance(chapters, list)
    assert [len(chapter["segment_ordinals"]) for chapter in chapters] == [1, 251, 251, 1, 251, 251]
    # The event of an exceeded limit is NOT emitted: every chapter fits.
    assert "audiobook_studio_limits_exceeded" not in [name for name, _ in events]


def test_fr103_pause_kinds_of_the_book_file_follow_the_styles() -> None:
    exports, _events = _exports(_S8_STRUCTURE)

    assert exports.book is not None
    segments = exports.book.payload["segments"]
    assert isinstance(segments, list)
    heading_segments = [s for s in segments if s["role"] == "heading"]
    # Every heading series became Heading 1 (levels 1 and 2 are at or above the chapter level 2): all are `chapter`.
    assert [s["pause_after"]["kind"] for s in heading_segments] == ["chapter"] * 6  # type: ignore[index]


def test_fr103_a_deeper_series_keeps_the_heading_pause_in_the_book_file() -> None:
    structure: list[tuple[str, int]] = [(H, 1), (H, 2), (P, 250), (H, 3), (P, 20), (H, 2), (P, 250)]
    exports, _events = _exports(structure)

    assert exports.book is not None and exports.plan is not None
    assert exports.plan.chapter_level == 2
    segments = exports.book.payload["segments"]
    assert isinstance(segments, list)
    kinds_by_level = {
        level: {s["pause_after"]["kind"] for s in segments if s["role"] == "heading" and s["heading_level"] == level}  # type: ignore[index]
        for level in (1, 2, 3)
    }
    assert kinds_by_level == {1: {"chapter"}, 2: {"chapter"}, 3: {"heading"}}


def test_fr103_the_event_of_an_exceeded_limit_still_fires_when_nothing_fits() -> None:
    exports, events = _exports(_MATRIX["S10_one_h1_and_500_paragraphs"][0])

    assert exports.plan is not None
    assert exports.plan.studio_limits.exceeded == ("chapter_paragraphs",)
    assert "audiobook_studio_limits_exceeded" in [name for name, _ in events]


# --- FR-104: only styles change ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Shape:
    texts: tuple[str, ...]
    ids: tuple[tuple[str, ...], ...]
    source_levels: tuple[int | None, ...]
    merges: tuple[tuple[tuple[str, ...], tuple[int, ...]], ...]


def _shape(plan: NarrationDocumentPlan) -> _Shape:
    return _Shape(
        texts=tuple(p.text for p in plan.paragraphs),
        ids=tuple(p.paragraph_ids for p in plan.paragraphs),
        source_levels=tuple(p.source_heading_level for p in plan.paragraphs),
        merges=tuple((m.paragraph_ids, m.levels) for m in plan.heading_merges),
    )


def test_fr104_texts_ids_series_and_merges_do_not_depend_on_the_chapter_level(monkeypatch: pytest.MonkeyPatch) -> None:
    # The same groups under two limits: the plan differs only in the styles (and what follows from them).
    structure: list[tuple[str, int]] = [(H, 1), (H, 1), (P, 30), (H, 2), (H, 3), (P, 30), (H, 3), (H, 3), (P, 30), (H, 2), (P, 30)]
    default_plan = _plan(structure)
    monkeypatch.setattr(narration_document, "STUDIO_MAX_CHAPTER_PARAGRAPHS", 40)
    tight_plan = _plan(structure)

    assert default_plan.chapter_level != tight_plan.chapter_level
    assert _shape(default_plan) == _shape(tight_plan)
    assert [p.style for p in default_plan.paragraphs] != [p.style for p in tight_plan.paragraphs]
    assert default_plan.heading_levels_present == tight_plan.heading_levels_present


def test_fr104_the_module_still_has_two_styles_only(monkeypatch: pytest.MonkeyPatch) -> None:
    structure: list[tuple[str, int]] = [(H, 1), (H, 2), (H, 3), (P, 150), (H, 3), (P, 150), (H, 3), (P, 150), (H, 1), (P, 50)]
    for limit in (400, 200, 160, 50, 1):
        monkeypatch.setattr(narration_document, "STUDIO_MAX_CHAPTER_PARAGRAPHS", limit)
        plan = _plan(structure)
        assert {p.style for p in plan.paragraphs} <= {H1, NORMAL}
