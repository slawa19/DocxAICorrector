"""Spec 072 WP-B — the narration document plan (FR-003 (а)–(г), FR-006, SC-002).

``pipeline/narration_document.py`` turns the ordered narration groups of the ``.tts.txt``
assembly into the paragraphs of ``.tts.docx``: which paragraph is a chapter (``Heading 1``),
which heading series merge into one paragraph, and the ElevenLabs Studio limit counters.

Every group here is FICTIONAL and built by the test (Constitution VII): the rules are keyed on
role and level only, never on words, and the anti-vacuum cases below prove that a body
paragraph shaped like a heading stays a body paragraph.
"""

from __future__ import annotations

import ast
import itertools
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

import docxaicorrector.pipeline.narration_document as narration_document
from docxaicorrector.pipeline.narration_document import (
    NARRATION_DOCUMENT_STYLE_HEADING_1,
    NARRATION_DOCUMENT_STYLE_NORMAL,
    STUDIO_MAX_CHAPTER_PARAGRAPHS,
    STUDIO_MAX_CHAPTERS,
    STUDIO_MAX_PARAGRAPH_CHARS,
    HeadingMerge,
    NarrationDocumentPlan,
    build_narration_document_plan,
)

pytestmark = pytest.mark.unit_contract

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "src" / "docxaicorrector" / "pipeline" / "narration_document.py"

H1 = NARRATION_DOCUMENT_STYLE_HEADING_1
NORMAL = NARRATION_DOCUMENT_STYLE_NORMAL


@dataclass(frozen=True)
class _Group:
    """A test double of the assembly group: the four fields the plan reads, nothing else."""

    paragraph_ids: tuple[str, ...]
    role: str
    heading_level: int | None
    text: str


def _heading(paragraph_id: str, level: int | None, text: str) -> _Group:
    return _Group(paragraph_ids=(paragraph_id,), role="heading", heading_level=level, text=text)


def _body(paragraph_id: str, text: str, *more_ids: str) -> _Group:
    return _Group(paragraph_ids=(paragraph_id, *more_ids), role="body", heading_level=None, text=text)


def _styles(plan: NarrationDocumentPlan) -> list[str]:
    return [paragraph.style for paragraph in plan.paragraphs]


def _texts(plan: NarrationDocumentPlan) -> list[str]:
    return [paragraph.text for paragraph in plan.paragraphs]


def _ids(plan: NarrationDocumentPlan) -> list[tuple[str, ...]]:
    return [paragraph.paragraph_ids for paragraph in plan.paragraphs]


# --- T-B1: the example table of data-model.md §3, one case per row ---------------------------


@dataclass(frozen=True)
class _TableCase:
    groups: tuple[_Group, ...]
    styles: tuple[str, ...]
    texts: tuple[str, ...]
    paragraph_ids: tuple[tuple[str, ...], ...]
    merges: tuple[HeadingMerge, ...]


_TABLE_CASES: dict[str, _TableCase] = {
    "single_rank1_heading_then_body": _TableCase(
        groups=(_heading("h1", 1, "Первая часть"), _body("p1", "Текст части."), _body("p2", "Ещё текст.")),
        styles=(H1, NORMAL, NORMAL),
        texts=("Первая часть", "Текст части.", "Ещё текст."),
        paragraph_ids=(("h1",), ("p1",), ("p2",)),
        merges=(),
    ),
    "series_2_then_1_merges_into_one_heading1": _TableCase(
        groups=(_heading("h1", 2, "Часть вторая"), _heading("h2", 1, "Дорога домой"), _body("p1", "Текст.")),
        styles=(H1, NORMAL),
        texts=("Часть вторая. Дорога домой", "Текст."),
        paragraph_ids=(("h1", "h2"), ("p1",)),
        merges=(HeadingMerge(paragraph_ids=("h1", "h2"), levels=(2, 1), style=H1),),
    ),
    "series_1_then_1_merges_into_one_heading1": _TableCase(
        groups=(_heading("h1", 1, "Раздел"), _heading("h2", 1, "Название"), _body("p1", "Текст.")),
        styles=(H1, NORMAL),
        texts=("Раздел. Название", "Текст."),
        paragraph_ids=(("h1", "h2"), ("p1",)),
        merges=(HeadingMerge(paragraph_ids=("h1", "h2"), levels=(1, 1), style=H1),),
    ),
    "part_ending_with_dot_gets_only_a_space": _TableCase(
        groups=(_heading("h1", 2, "Часть 1."), _heading("h2", 1, "Начало"), _body("p1", "Текст.")),
        styles=(H1, NORMAL),
        texts=("Часть 1. Начало", "Текст."),
        paragraph_ids=(("h1", "h2"), ("p1",)),
        merges=(HeadingMerge(paragraph_ids=("h1", "h2"), levels=(2, 1), style=H1),),
    ),
    "series_1_then_2_does_not_merge": _TableCase(
        groups=(_heading("h1", 1, "Глава"), _heading("h2", 2, "Подраздел"), _body("p1", "Текст.")),
        styles=(H1, NORMAL, NORMAL),
        texts=("Глава", "Подраздел", "Текст."),
        paragraph_ids=(("h1",), ("h2",), ("p1",)),
        merges=(),
    ),
    "series_1_2_1_gives_heading1_then_merged_2_1": _TableCase(
        groups=(
            _heading("h1", 1, "Первое"),
            _heading("h2", 2, "Второе"),
            _heading("h3", 1, "Третье"),
            _body("p1", "Текст."),
        ),
        styles=(H1, H1, NORMAL),
        texts=("Первое", "Второе. Третье", "Текст."),
        paragraph_ids=(("h1",), ("h2", "h3"), ("p1",)),
        merges=(HeadingMerge(paragraph_ids=("h2", "h3"), levels=(2, 1), style=H1),),
    ),
    "book_levels_2_and_4": _TableCase(
        groups=(
            _heading("h1", 2, "Верхний"),
            _body("p1", "Текст один."),
            _heading("h2", 4, "Глубокий"),
            _body("p2", "Текст два."),
        ),
        styles=(H1, NORMAL, NORMAL, NORMAL),
        texts=("Верхний", "Текст один.", "Глубокий", "Текст два."),
        paragraph_ids=(("h1",), ("p1",), ("h2",), ("p2",)),
        merges=(),
    ),
    "series_3_then_3_below_chapter_level_is_one_normal": _TableCase(
        groups=(
            _heading("h1", 1, "Глава"),
            _body("p1", "Текст."),
            _heading("h2", 3, "Пункт"),
            _heading("h3", 3, "Подпункт"),
            _body("p2", "Ещё текст."),
        ),
        styles=(H1, NORMAL, NORMAL, NORMAL),
        texts=("Глава", "Текст.", "Пункт. Подпункт", "Ещё текст."),
        paragraph_ids=(("h1",), ("p1",), ("h2", "h3"), ("p2",)),
        merges=(HeadingMerge(paragraph_ids=("h2", "h3"), levels=(3, 3), style=NORMAL),),
    ),
    "rank1_heading_at_the_end_of_the_book_stays": _TableCase(
        groups=(_heading("h1", 1, "Начало"), _body("p1", "Текст."), _heading("h2", 1, "Конец")),
        styles=(H1, NORMAL, H1),
        texts=("Начало", "Текст.", "Конец"),
        paragraph_ids=(("h1",), ("p1",), ("h2",)),
        merges=(),
    ),
    "deeper_heading_at_the_end_of_the_book_stays_normal": _TableCase(
        groups=(_heading("h1", 1, "Начало"), _body("p1", "Текст."), _heading("h2", 2, "Хвост")),
        styles=(H1, NORMAL, NORMAL),
        texts=("Начало", "Текст.", "Хвост"),
        paragraph_ids=(("h1",), ("p1",), ("h2",)),
        merges=(),
    ),
    "heading_role_without_level_is_normal_and_breaks_the_series": _TableCase(
        groups=(
            _heading("h1", 1, "Первое"),
            _heading("h2", None, "Без уровня"),
            _heading("h3", 1, "Второе"),
            _body("p1", "Текст."),
        ),
        styles=(H1, NORMAL, H1, NORMAL),
        texts=("Первое", "Без уровня", "Второе", "Текст."),
        paragraph_ids=(("h1",), ("h2",), ("h3",), ("p1",)),
        merges=(),
    ),
    "heading_role_without_level_does_not_start_a_series": _TableCase(
        groups=(_heading("h1", None, "Без уровня"), _heading("h2", 1, "Глава"), _body("p1", "Текст.")),
        styles=(NORMAL, H1, NORMAL),
        texts=("Без уровня", "Глава", "Текст."),
        paragraph_ids=(("h1",), ("h2",), ("p1",)),
        merges=(),
    ),
    "no_heading_at_all": _TableCase(
        groups=(_body("p1", "Первый абзац."), _body("p2", "Второй абзац.", "p3")),
        styles=(NORMAL, NORMAL),
        texts=("Первый абзац.", "Второй абзац."),
        paragraph_ids=(("p1",), ("p2", "p3")),
        merges=(),
    ),
}


@pytest.mark.parametrize("case_name", sorted(_TABLE_CASES))
def test_example_table_row(case_name: str) -> None:
    case = _TABLE_CASES[case_name]

    plan = build_narration_document_plan(case.groups)

    assert tuple(_styles(plan)) == case.styles
    assert tuple(_texts(plan)) == case.texts
    assert tuple(_ids(plan)) == case.paragraph_ids
    assert plan.heading_merges == case.merges


def test_no_heading_book_counts_as_one_chapter_with_zero_heading1() -> None:
    plan = build_narration_document_plan(_TABLE_CASES["no_heading_at_all"].groups)

    assert plan.studio_limits.heading1_count == 0
    assert plan.studio_limits.chapter_count_for_limits == 1
    assert plan.studio_limits.max_chapter_paragraph_count == 2
    assert plan.chapter_level is None


def test_source_heading_level_is_the_series_minimum_and_none_for_body() -> None:
    plan = build_narration_document_plan(
        (
            _heading("h1", 2, "Часть"),
            _heading("h2", 1, "Глава"),
            _body("p1", "Текст."),
            _heading("h3", 3, "Пункт"),
            _heading("h4", None, "Без уровня"),
        )
    )

    assert [paragraph.source_heading_level for paragraph in plan.paragraphs] == [1, None, 3, None]


# --- T-B2: anti-vacuum — the rule reads role and level, never the words --------------------


@pytest.mark.parametrize(
    "text",
    ["# Раздел", "## Подраздел", "Глава 1", "КОРОТКО", "Итог", "1. Начало"],
)
def test_body_shaped_like_a_heading_stays_normal(text: str) -> None:
    plan = build_narration_document_plan((_heading("h1", 1, "Глава"), _body("p1", text), _body("p2", "Текст.")))

    assert _styles(plan) == [H1, NORMAL, NORMAL]
    assert _texts(plan)[1] == text
    assert plan.studio_limits.heading1_count == 1


def test_body_only_book_shaped_like_headings_has_no_heading1() -> None:
    plan = build_narration_document_plan(
        (_body("p1", "# Раздел"), _body("p2", "Глава 1"), _body("p3", "КОРОТКО"), _body("p4", "Текст."))
    )

    assert _styles(plan) == [NORMAL] * 4
    assert plan.studio_limits.heading1_count == 0
    assert plan.heading_merges == ()


_ALPHABET: tuple[tuple[str, int | None], ...] = (
    ("body", None),
    ("heading", 1),
    ("heading", 2),
    ("heading", 3),
    ("heading", None),
)


def _generated_books() -> list[tuple[_Group, ...]]:
    """Every sequence of up to four groups over body / heading 1..3 / heading without level."""

    books: list[tuple[_Group, ...]] = []
    for length in range(1, 5):
        for shape in itertools.product(_ALPHABET, repeat=length):
            groups = tuple(
                _Group(
                    paragraph_ids=(f"g{index}",),
                    role=role,
                    heading_level=level,
                    text=f"{role}-{level}-{index}",
                )
                for index, (role, level) in enumerate(shape)
            )
            books.append(groups)
    return books


_GENERATED_BOOKS = _generated_books()


def test_generated_books_are_numerous_and_contain_merges() -> None:
    # Anti-vacuum for the property test below: the generated set really exercises series,
    # demotions and level-less headings, not just trivial books.
    plans = [build_narration_document_plan(groups) for groups in _GENERATED_BOOKS]

    assert len(_GENERATED_BOOKS) == 5 + 25 + 125 + 625
    assert sum(len(plan.heading_merges) for plan in plans) > 100
    assert sum(plan.demoted_heading_count for plan in plans) > 100
    assert sum(plan.studio_limits.heading1_count for plan in plans) > 100


def _oracle_chapter_level(groups: tuple[_Group, ...], limit: int) -> int | None:
    """The chapter level of spec 074 FR-101, written independently of the module under test.

    Tokens of the plan: ``("S", level)`` for a heading series (a heading with a level joins the open series unless it
    is deeper than the shallowest member; the series level is its minimum) and ``("B", 0)`` for everything else. The
    level is the first, from the top, whose division (a series of that level or above opens a chapter; paragraphs
    before the first opener are a chapter of their own; the opening series is not counted) has no chapter over the
    limit; none fits -> the deepest level present; no levels -> ``None``.
    """

    tokens: list[tuple[str, int]] = []
    series_levels: list[int] = []
    present: set[int] = set()
    for group in groups:
        level = group.heading_level if group.role == "heading" else None
        if level is None:
            if series_levels:
                tokens.append(("S", min(series_levels)))
                series_levels = []
            tokens.append(("B", 0))
            continue
        present.add(level)
        if series_levels and level > min(series_levels):
            tokens.append(("S", min(series_levels)))
            series_levels = []
        series_levels.append(level)
    if series_levels:
        tokens.append(("S", min(series_levels)))
    if not present:
        return None
    for candidate in sorted(present):
        chapters: list[int] = []
        for kind, level in tokens:
            if kind == "S" and level <= candidate:
                chapters.append(0)
            elif chapters:
                chapters[-1] += 1
            else:
                chapters.append(1)
        if max(chapters) <= limit:
            return candidate
    return max(present)


def _book_invariant_violations(groups: tuple[_Group, ...], limit: int = STUDIO_MAX_CHAPTER_PARAGRAPHS) -> list[str]:
    plan = build_narration_document_plan(groups)
    by_id = {group.paragraph_ids[0]: group for group in groups}
    chapter_level = _oracle_chapter_level(groups, limit)
    violations: list[str] = []

    # The ids of the plan, in order and with multiplicity, are the ids of the groups.
    if [pid for paragraph in plan.paragraphs for pid in paragraph.paragraph_ids] != [
        pid for group in groups for pid in group.paragraph_ids
    ]:
        violations.append("ids")
    if plan.chapter_level != chapter_level:
        violations.append("chapter_level")
    for paragraph in plan.paragraphs:
        members = [by_id[pid] for pid in paragraph.paragraph_ids]
        # Spec 074 FR-102: a member at or above the chapter level (not only AT it, as in spec 072 FR-003 (a)).
        reaches_chapter_level = [
            m.role == "heading"
            and m.heading_level is not None
            and chapter_level is not None
            and m.heading_level <= chapter_level
            for m in members
        ]
        # Only the two styles, ever.
        if paragraph.style not in (H1, NORMAL):
            violations.append(f"style {paragraph.style}")
        # Heading 1 if and only if a member at or above the chapter level is in the paragraph.
        if (paragraph.style == H1) != any(reaches_chapter_level):
            violations.append(f"heading1 {paragraph.paragraph_ids}")
        # Every member text is in the plan byte for byte (demoted headings included).
        if any(member.text not in paragraph.text for member in members):
            violations.append(f"text {paragraph.paragraph_ids}")
        # A merged paragraph is made of heading groups with a level only.
        if len(members) > 1 and not all(m.role == "heading" and m.heading_level is not None for m in members):
            violations.append(f"merge {paragraph.paragraph_ids}")
        # Body and level-less headings are always Normal, alone, verbatim.
        if members[0].role != "heading" or members[0].heading_level is None:
            if (paragraph.style, paragraph.text, len(members)) != (NORMAL, members[0].text, 1):
                violations.append(f"body {paragraph.paragraph_ids}")
    return violations


def test_generated_book_invariants() -> None:
    failures = {
        index: violations
        for index, groups in enumerate(_GENERATED_BOOKS)
        if (violations := _book_invariant_violations(groups))
    }

    assert not failures, dict(itertools.islice(failures.items(), 10))


# The generated books are far under the Studio limit, so the limit rule never leaves the topmost level above. A limit of
# 1 or 2 paragraphs per chapter makes the same books exercise the rule itself (spec 074 FR-101): the level goes down, the
# fallback to the deepest level is taken, and series at or above the level are ``Heading 1`` (FR-102).
@pytest.mark.parametrize("limit", [1, 2])
def test_generated_book_invariants_under_a_small_chapter_limit(monkeypatch: pytest.MonkeyPatch, limit: int) -> None:
    monkeypatch.setattr(narration_document, "STUDIO_MAX_CHAPTER_PARAGRAPHS", limit)
    failures = {
        index: violations
        for index, groups in enumerate(_GENERATED_BOOKS)
        if (violations := _book_invariant_violations(groups, limit))
    }

    assert not failures, dict(itertools.islice(failures.items(), 10))


@pytest.mark.parametrize("limit", [1, 2])
def test_a_small_chapter_limit_moves_the_level_down_on_the_generated_books(
    monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    # Anti-vacuum for the test above: the small limit really changes the level on many generated books.
    shallow = {
        index: build_narration_document_plan(groups).chapter_level for index, groups in enumerate(_GENERATED_BOOKS)
    }
    monkeypatch.setattr(narration_document, "STUDIO_MAX_CHAPTER_PARAGRAPHS", limit)
    moved = sum(
        1
        for index, groups in enumerate(_GENERATED_BOOKS)
        if build_narration_document_plan(groups).chapter_level != shallow[index]
    )

    assert moved > 50


def test_the_oracle_gives_min_levels_when_nothing_is_over_the_limit() -> None:
    # What spec 072 FR-003 (a) said survives as a special case: a book whose topmost level fits keeps it.
    for groups in _GENERATED_BOOKS:
        levels = [g.heading_level for g in groups if g.role == "heading" and g.heading_level is not None]
        assert _oracle_chapter_level(groups, STUDIO_MAX_CHAPTER_PARAGRAPHS) == (min(levels) if levels else None)


# --- T-B3: no style but Heading 1 and Normal, whatever the levels ---------------------------


@pytest.mark.parametrize(
    "levels",
    [
        (1,),
        (2,),
        (3,),
        (4,),
        (5,),
        (6,),
        (1, 2, 3, 4, 5, 6),
        (6, 5, 4, 3, 2, 1),
        (2, 4),
        (3, 6),
        (5, 6, 5),
        (4, 1, 6, 2),
    ],
    ids=lambda levels: "-".join(str(level) for level in levels),
)
@pytest.mark.parametrize("separated", [True, False], ids=["with_body_between", "consecutive"])
def test_only_heading1_and_normal_for_any_levels(levels: tuple[int, ...], separated: bool) -> None:
    groups: list[_Group] = []
    for index, level in enumerate(levels):
        groups.append(_heading(f"h{index}", level, f"Заголовок {index}"))
        if separated:
            groups.append(_body(f"p{index}", f"Текст {index}."))

    plan = build_narration_document_plan(groups)

    assert set(_styles(plan)) <= {H1, NORMAL}
    assert H1 in _styles(plan)
    # Spec 074 FR-101: the books here are far under the Studio limit, so the topmost level fits and is the chapter level.
    assert plan.chapter_level == min(levels)
    if separated:
        expected = [H1 if level <= min(levels) else NORMAL for level in levels]
        assert [p.style for p in plan.paragraphs if p.source_heading_level is not None] == expected


# --- T-B4: FR-006 Studio limits -------------------------------------------------------------


def test_heading1_count_counts_chapters_after_merges() -> None:
    plan = build_narration_document_plan(
        (
            _heading("h1", 2, "Часть"),
            _heading("h2", 1, "Глава"),
            _body("p1", "Текст."),
            _heading("h3", 1, "Глава"),
            _body("p2", "Текст."),
            _heading("h4", 2, "Подраздел"),
            _body("p3", "Текст."),
        )
    )

    assert plan.studio_limits.heading1_count == 2


def test_paragraphs_before_first_heading1_are_a_chapter_of_their_own() -> None:
    plan = build_narration_document_plan(
        (
            _body("p1", "Вступление."),
            _body("p2", "Вступление."),
            _body("p3", "Вступление."),
            _heading("h1", 1, "Глава"),
            _body("p4", "Текст."),
            _body("p5", "Текст."),
        )
    )

    assert plan.studio_limits.chapter_count_for_limits == 2
    assert plan.studio_limits.max_chapter_paragraph_count == 3


def test_chapter_paragraph_count_excludes_the_heading1_itself() -> None:
    plan = build_narration_document_plan(
        (_heading("h1", 1, "Глава"), _body("p1", "Текст."), _body("p2", "Текст."), _heading("h2", 2, "Пункт"))
    )

    assert plan.studio_limits.chapter_count_for_limits == 1
    assert plan.studio_limits.max_chapter_paragraph_count == 3


def test_max_paragraph_chars_is_measured_after_merges() -> None:
    plan = build_narration_document_plan(
        (_heading("h1", 2, "а" * 10), _heading("h2", 1, "б" * 10), _body("p1", "в" * 15))
    )

    assert plan.studio_limits.max_paragraph_chars == len("а" * 10 + ". " + "б" * 10) == 22


def _chapters_book(chapter_count: int) -> list[_Group]:
    groups: list[_Group] = []
    for index in range(chapter_count):
        groups.append(_heading(f"h{index}", 1, f"Глава {index}"))
        groups.append(_body(f"p{index}", "Текст."))
    return groups


@pytest.mark.parametrize(
    ("chapter_count", "exceeded"),
    [(STUDIO_MAX_CHAPTERS, ()), (STUDIO_MAX_CHAPTERS + 1, ("chapters",))],
)
def test_chapter_limit_boundary(chapter_count: int, exceeded: tuple[str, ...]) -> None:
    plan = build_narration_document_plan(_chapters_book(chapter_count))

    assert plan.studio_limits.heading1_count == chapter_count
    assert plan.studio_limits.exceeded == exceeded


@pytest.mark.parametrize(
    ("paragraph_count", "exceeded"),
    [(STUDIO_MAX_CHAPTER_PARAGRAPHS, ()), (STUDIO_MAX_CHAPTER_PARAGRAPHS + 1, ("chapter_paragraphs",))],
)
def test_chapter_paragraph_limit_boundary(paragraph_count: int, exceeded: tuple[str, ...]) -> None:
    groups = [_heading("h0", 1, "Глава")] + [_body(f"p{index}", "Текст.") for index in range(paragraph_count)]

    plan = build_narration_document_plan(groups)

    assert plan.studio_limits.max_chapter_paragraph_count == paragraph_count
    assert plan.studio_limits.exceeded == exceeded


@pytest.mark.parametrize(
    ("paragraph_count", "exceeded"),
    [(STUDIO_MAX_CHAPTER_PARAGRAPHS, ()), (STUDIO_MAX_CHAPTER_PARAGRAPHS + 1, ("chapter_paragraphs",))],
)
def test_chapter_paragraph_limit_boundary_without_headings(paragraph_count: int, exceeded: tuple[str, ...]) -> None:
    plan = build_narration_document_plan([_body(f"p{index}", "Текст.") for index in range(paragraph_count)])

    assert plan.studio_limits.chapter_count_for_limits == 1
    assert plan.studio_limits.max_chapter_paragraph_count == paragraph_count
    assert plan.studio_limits.exceeded == exceeded


@pytest.mark.parametrize(
    ("char_count", "exceeded"),
    [(STUDIO_MAX_PARAGRAPH_CHARS, ()), (STUDIO_MAX_PARAGRAPH_CHARS + 1, ("paragraph_chars",))],
)
def test_paragraph_chars_limit_boundary(char_count: int, exceeded: tuple[str, ...]) -> None:
    plan = build_narration_document_plan((_heading("h0", 1, "Глава"), _body("p0", "я" * char_count)))

    assert plan.studio_limits.max_paragraph_chars == char_count
    assert plan.studio_limits.exceeded == exceeded


def test_paragraph_chars_limit_counts_a_merged_heading() -> None:
    half = STUDIO_MAX_PARAGRAPH_CHARS // 2
    plan = build_narration_document_plan((_heading("h0", 2, "а" * half), _heading("h1", 1, "б" * half)))

    # Each part is under the limit; the merged paragraph (+ ". ") is over it.
    assert plan.studio_limits.max_paragraph_chars == 2 * half + 2
    assert plan.studio_limits.exceeded == ("paragraph_chars",)


def test_all_limits_exceeded_are_reported_in_fixed_order() -> None:
    groups = [_body("long", "я" * (STUDIO_MAX_PARAGRAPH_CHARS + 1))]
    groups += [_body(f"intro{index}", "Текст.") for index in range(STUDIO_MAX_CHAPTER_PARAGRAPHS + 1)]
    groups += _chapters_book(STUDIO_MAX_CHAPTERS + 1)

    plan = build_narration_document_plan(groups)

    assert plan.studio_limits.exceeded == ("chapters", "chapter_paragraphs", "paragraph_chars")
    assert plan.studio_limits.chapter_count_for_limits == STUDIO_MAX_CHAPTERS + 2
    assert plan.studio_limits.max_chapter_paragraph_count == STUDIO_MAX_CHAPTER_PARAGRAPHS + 2


def test_limit_constants_are_the_studio_limits() -> None:
    assert (STUDIO_MAX_CHAPTERS, STUDIO_MAX_CHAPTER_PARAGRAPHS, STUDIO_MAX_PARAGRAPH_CHARS) == (500, 400, 5000)


def test_empty_input_gives_an_empty_plan() -> None:
    plan = build_narration_document_plan(())

    assert plan.paragraphs == ()
    assert plan.studio_limits.heading1_count == 0
    assert plan.studio_limits.chapter_count_for_limits == 0
    assert plan.studio_limits.max_chapter_paragraph_count == 0
    assert plan.studio_limits.max_paragraph_chars == 0
    assert plan.studio_limits.exceeded == ()


# --- T-B5: chapter_level, heading_levels_present, demoted_heading_count ---------------------


def test_levels_and_demoted_count_with_a_series_counted_once() -> None:
    plan = build_narration_document_plan(
        (
            _heading("h1", 2, "Глава"),
            _heading("h2", 4, "Пункт"),
            _heading("h3", 4, "Подпункт"),
            _body("p1", "Текст."),
            _heading("h4", 3, "Раздел"),
            _body("p2", "Текст."),
            _heading("h5", None, "Без уровня"),
            _body("p3", "Текст."),
        )
    )

    assert plan.chapter_level == 2
    assert plan.heading_levels_present == (2, 3, 4)
    # The 4 → 4 series is one demoted paragraph, the level-3 heading another; the
    # level-less heading is not "deeper than rank 1" and is not counted.
    assert plan.demoted_heading_count == 2
    assert _styles(plan) == [H1, NORMAL, NORMAL, NORMAL, NORMAL, NORMAL, NORMAL]


def test_a_deeper_heading_merged_into_a_heading1_is_not_demoted() -> None:
    plan = build_narration_document_plan(
        (_heading("h1", 3, "Пункт"), _heading("h2", 1, "Глава"), _body("p1", "Текст."))
    )

    assert plan.demoted_heading_count == 0
    assert plan.heading_merges == (HeadingMerge(paragraph_ids=("h1", "h2"), levels=(3, 1), style=H1),)


def test_no_headings_gives_no_levels() -> None:
    plan = build_narration_document_plan((_body("p1", "Текст."), _heading("h1", None, "Без уровня")))

    assert plan.chapter_level is None
    assert plan.heading_levels_present == ()
    assert plan.demoted_heading_count == 0
    assert plan.heading_merges == ()


# --- T-B7: the module is pure — no python-docx, no Streamlit, no I/O ------------------------

_ALLOWED_IMPORTS = {"__future__", "collections", "dataclasses", "typing"}


def test_module_imports_only_pure_standard_library() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert imported <= _ALLOWED_IMPORTS, imported
    assert "open" not in names


def test_importing_the_module_loads_neither_docx_nor_streamlit() -> None:
    probe = (
        "import docxaicorrector.pipeline.narration_document;"
        "import sys;"
        "loaded=[m for m in sys.modules if m.split('.')[0] in ('docx','streamlit')];"
        "assert not loaded, loaded;"
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        check=False,
    )

    assert result.returncode == 0, result.stderr[-800:]
    assert "OK" in result.stdout
