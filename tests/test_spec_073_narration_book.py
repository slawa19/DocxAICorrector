"""Spec 073 WP-G — the book file for the narration tool (FR-007, owner decision D-4, SC-006).

``pipeline/narration_book.py`` turns the ordered narration groups of the ``.tts.txt`` assembly and
the spec 072 paragraph plan of the same groups into the ``<stem>.narration.json`` payload
(``contracts/narration-book.md``): chapters by the 072 chapter rule, one segment per group with
its pause kind, the accepted reading glossary and the run's counters.

Every group here is FICTIONAL and built by the test (Constitution VII): the rules read role,
level and the scene-break mark only, never the words, and every text below is an invented
example of the same form. The plan is the REAL 072 plan of the same groups
(``build_narration_document_plan``), so a series or a chapter here is exactly what the
narration DOCX shows.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from docxaicorrector.pipeline.narration_book import (
    NARRATION_BOOK_SCHEMA_VERSION,
    NARRATION_BOOK_TOP_LEVEL_KEYS,
    NARRATION_PAUSE_DEFAULT_SECONDS,
    NARRATION_PAUSE_KINDS,
    NarrationBook,
    NarrationBookProducer,
    NarrationBookSource,
    build_narration_book,
)
from docxaicorrector.pipeline.narration_document import NarrationDocumentPlan, build_narration_document_plan
from docxaicorrector.pipeline.narration_postprocess import NarrationGroup

pytestmark = pytest.mark.unit_contract

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "src" / "docxaicorrector" / "pipeline" / "narration_book.py"

CHAPTER = "chapter"
HEADING = "heading"
SCENE = "scene_break"

ACUTE = "́"


@dataclass(frozen=True)
class _Group:
    """A test double of the assembly group: the five fields the book reads, nothing else."""

    paragraph_ids: tuple[str, ...]
    role: str
    heading_level: int | None
    text: str
    after_scene_break: bool = False


@dataclass(frozen=True)
class _Entry:
    abbreviation: str
    reading: str


_ID_COUNTER = iter(range(1, 1_000_000))


def _next_id() -> str:
    return f"p{next(_ID_COUNTER):04d}"


def _h(level: int | None, text: str) -> _Group:
    return _Group(paragraph_ids=(_next_id(),), role="heading", heading_level=level, text=text)


def _b(text: str, *, scene: bool = False, ids: tuple[str, ...] | None = None) -> _Group:
    return _Group(
        paragraph_ids=ids if ids is not None else (_next_id(),),
        role="body",
        heading_level=None,
        text=text,
        after_scene_break=scene,
    )


_PRODUCER = NarrationBookProducer(version="0f1e2d3", run_id="run-xyz", produced_at="2026-11-10T15:01:39Z")
_SOURCE = NarrationBookSource(source_name="kvazibu.docx", source_token="kvazibu.docx:1024:0f0f0f0f0f0f0f0f")


def _book(
    groups: Sequence[_Group],
    *,
    plan: NarrationDocumentPlan | None = None,
    glossary: Sequence[_Entry] = (),
    producer: NarrationBookProducer = _PRODUCER,
    excluded_count: int = 0,
    excluded_by_reason: Mapping[str, int] | None = None,
    pause_seconds: Mapping[str, float] | None = None,
) -> NarrationBook:
    extra: dict[str, Mapping[str, float]] = {} if pause_seconds is None else {"pause_seconds": pause_seconds}
    return build_narration_book(
        groups=groups,
        plan=plan if plan is not None else build_narration_document_plan(groups),
        glossary_entries=glossary,
        producer=producer,
        source=_SOURCE,
        excluded_count=excluded_count,
        excluded_by_reason=excluded_by_reason or {},
        **extra,
    )


def _segments(book: NarrationBook) -> list[dict[str, object]]:
    segments = book.payload["segments"]
    assert isinstance(segments, list)
    return segments


def _chapters(book: NarrationBook) -> list[dict[str, object]]:
    chapters = book.payload["chapters"]
    assert isinstance(chapters, list)
    return chapters


def _stats(book: NarrationBook) -> dict[str, object]:
    stats = book.payload["stats"]
    assert isinstance(stats, dict)
    return stats


def _pause_kinds_of(book: NarrationBook) -> list[str | None]:
    kinds: list[str | None] = []
    for segment in _segments(book):
        pause = segment["pause_after"]
        kinds.append(None if pause is None else pause["kind"])  # type: ignore[index]
    return kinds


def _joined_segment_text(segments: Sequence[Mapping[str, object]]) -> str:
    """The ONE comparison of the contract: the segment texts joined like the ``.tts.txt``."""

    return "\n\n".join(str(segment["text"]) for segment in segments)


def _tts_text(groups: Sequence[_Group]) -> str:
    return "\n\n".join(group.text for group in groups)


# --- T-G1: the example table of data-model.md §7, one case per row ---------------------------


@dataclass(frozen=True)
class _TableCase:
    groups: tuple[_Group, ...]
    kinds: tuple[str | None, ...]
    # (title, segment ordinals) per chapter, in order.
    chapters: tuple[tuple[str | None, tuple[int, ...]], ...]
    chapter_level: int | None


_TABLE_CASES: dict[str, _TableCase] = {
    "h1_b_b": _TableCase(
        groups=(_h(1, "Квазибург"), _b("Тело первое."), _b("Тело второе.")),
        kinds=(CHAPTER, None, None),
        chapters=(("Квазибург", (1, 2, 3)),),
        chapter_level=1,
    ),
    "b0_h1_b": _TableCase(
        groups=(_b("Посвящается городу."), _h(1, "Квазибург"), _b("Тело.")),
        kinds=(None, CHAPTER, None),
        chapters=((None, (1,)), ("Квазибург", (2, 3))),
        chapter_level=1,
    ),
    "series_h2_h1_b": _TableCase(
        groups=(_h(2, "Часть первая"), _h(1, "Квазибург"), _b("Тело.")),
        kinds=(None, CHAPTER, None),
        chapters=(("Часть первая. Квазибург", (1, 2, 3)),),
        chapter_level=1,
    ),
    "h1_h2_b": _TableCase(
        groups=(_h(1, "Квазибург"), _h(2, "Окрестности"), _b("Тело.")),
        kinds=(CHAPTER, HEADING, None),
        chapters=(("Квазибург", (1, 2, 3)),),
        chapter_level=1,
    ),
    "h1_b_series_h3_h3_b": _TableCase(
        groups=(_h(1, "Квазибург"), _b("Тело."), _h(3, "Раздел один"), _h(3, "Раздел два"), _b("Ещё тело.")),
        kinds=(CHAPTER, None, None, HEADING, None),
        chapters=(("Квазибург", (1, 2, 3, 4, 5)),),
        chapter_level=1,
    ),
    "b1_b2_after_scene_break": _TableCase(
        groups=(_b("Первая сцена."), _b("Вторая сцена.", scene=True)),
        kinds=(SCENE, None),
        chapters=((None, (1, 2)),),
        chapter_level=None,
    ),
    "h1_b1_after_scene_break_b2": _TableCase(
        groups=(_h(1, "Квазибург"), _b("Сцена.", scene=True), _b("Продолжение.")),
        kinds=(SCENE, None, None),
        chapters=(("Квазибург", (1, 2, 3)),),
        chapter_level=1,
    ),
    "h1_b_h1_heading_last": _TableCase(
        groups=(_h(1, "Квазибург"), _b("Тело."), _h(1, "Zentrix")),
        kinds=(CHAPTER, None, None),
        chapters=(("Квазибург", (1, 2)), ("Zentrix", (3,))),
        chapter_level=1,
    ),
    "only_h3_b_h3_b": _TableCase(
        groups=(_h(3, "Раздел один"), _b("Тело."), _h(3, "Раздел два"), _b("Ещё тело.")),
        kinds=(CHAPTER, None, CHAPTER, None),
        chapters=(("Раздел один", (1, 2)), ("Раздел два", (3, 4))),
        chapter_level=3,
    ),
    "no_headings": _TableCase(
        groups=(_b("Один."), _b("Два."), _b("Три.", scene=True), _b("Четыре.")),
        kinds=(None, SCENE, None, None),
        chapters=((None, (1, 2, 3, 4)),),
        chapter_level=None,
    ),
}


@pytest.mark.parametrize("case_id", list(_TABLE_CASES))
def test_table_pause_kinds_and_seconds_per_segment(case_id: str) -> None:
    case = _TABLE_CASES[case_id]
    book = _book(case.groups)

    assert tuple(_pause_kinds_of(book)) == case.kinds
    assert book.pause_kinds == case.kinds
    for segment, kind in zip(_segments(book), case.kinds):
        expected = None if kind is None else {"kind": kind, "seconds": NARRATION_PAUSE_DEFAULT_SECONDS[kind]}
        assert segment["pause_after"] == expected


@pytest.mark.parametrize("case_id", list(_TABLE_CASES))
def test_table_chapters(case_id: str) -> None:
    case = _TABLE_CASES[case_id]
    book = _book(case.groups)

    chapters = _chapters(book)
    assert [(chapter["title"], tuple(chapter["segment_ordinals"])) for chapter in chapters] == list(  # type: ignore[arg-type]
        case.chapters
    )
    assert [chapter["ordinal"] for chapter in chapters] == list(range(1, len(case.chapters) + 1))
    assert book.payload["chapter_heading_level"] == case.chapter_level
    assert book.chapter_count == len(case.chapters)
    assert _stats(book)["chapter_count"] == len(case.chapters)


@pytest.mark.parametrize("case_id", list(_TABLE_CASES))
def test_table_pause_counts(case_id: str) -> None:
    case = _TABLE_CASES[case_id]
    book = _book(case.groups)

    counted = Counter(kind for kind in case.kinds if kind is not None)
    expected = {kind: counted.get(kind, 0) for kind in NARRATION_PAUSE_KINDS}
    assert dict(book.pause_counts) == expected
    assert _stats(book)["pause_counts"] == expected
    assert _stats(book)["scene_break_count"] == sum(1 for group in case.groups if group.after_scene_break)


# --- T-G2: the text contract — the segments ARE the .tts.txt ----------------------------------


def _contract_groups() -> tuple[_Group, ...]:
    return (
        _h(1, f"Ква{ACUTE}зибург"),
        _b(f"Ста{ACUTE}рый за{ACUTE}мок стоял на холме."),
        _b("Первая строка стихотворения\nвторая строка стихотворения"),
        _b("# не заголовок, а тело с решёткой в начале"),
        _Group(paragraph_ids=("",), role="heading", heading_level=2, text="Неадресуемая запись"),
        _b("Склеенное тело из двух записей.", ids=(_next_id(), _next_id())),
    )


def test_segment_texts_joined_equal_the_tts_text_byte_for_byte() -> None:
    groups = _contract_groups()
    book = _book(groups)
    segments = _segments(book)

    assert _joined_segment_text(segments).encode("utf-8") == _tts_text(groups).encode("utf-8")
    assert len(segments) == len(groups)
    assert [segment["text"] for segment in segments] == [group.text for group in groups]
    assert [segment["source_paragraph_ids"] for segment in segments] == [list(group.paragraph_ids) for group in groups]
    assert segments[4]["source_paragraph_ids"] == [""]
    assert _stats(book)["char_count"] == len(_tts_text(groups))


def test_text_contract_comparison_sees_one_extra_space() -> None:
    """Negative control: the same comparison is not blind to a one-character difference."""

    groups = _contract_groups()
    segments = [dict(segment) for segment in _segments(_book(groups))]
    segments[2]["text"] = str(segments[2]["text"]) + " "

    assert _joined_segment_text(segments) != _tts_text(groups)


def test_segment_fields_come_from_the_group() -> None:
    groups = _contract_groups()
    segments = _segments(_book(groups))

    assert [segment["ordinal"] for segment in segments] == list(range(1, len(groups) + 1))
    assert [segment["role"] for segment in segments] == [group.role for group in groups]
    assert [segment["heading_level"] for segment in segments] == [group.heading_level for group in groups]
    assert [segment["after_scene_break"] for segment in segments] == [group.after_scene_break for group in groups]
    assert list(segments[0]) == [
        "ordinal",
        "chapter_ordinal",
        "role",
        "heading_level",
        "text",
        "after_scene_break",
        "pause_after",
        "source_paragraph_ids",
    ]


def test_real_narration_groups_are_accepted() -> None:
    groups = (
        NarrationGroup(paragraph_ids=("p0001",), role="heading", heading_level=1, text="Квазибург"),
        NarrationGroup(paragraph_ids=("p0002", "p0003"), role="body", heading_level=None, text="Тело."),
        NarrationGroup(
            paragraph_ids=("p0005",), role="body", heading_level=None, text="После сцены.", after_scene_break=True
        ),
    )
    book = build_narration_book(
        groups=groups,
        plan=build_narration_document_plan(groups),
        glossary_entries=(),
        producer=_PRODUCER,
        source=_SOURCE,
        excluded_count=1,
        excluded_by_reason={"scene_break": 1},
    )

    assert book.pause_kinds == (CHAPTER, SCENE, None)
    assert _joined_segment_text(_segments(book)) == "\n\n".join(group.text for group in groups)


# --- T-G3: chapters by the 072 rule --------------------------------------------------------


@pytest.mark.parametrize("case_id", list(_TABLE_CASES))
def test_chapters_follow_the_072_chapter_count_and_cover_every_segment_once(case_id: str) -> None:
    groups = _TABLE_CASES[case_id].groups
    plan = build_narration_document_plan(groups)
    book = _book(groups, plan=plan)
    chapters = _chapters(book)
    segments = _segments(book)

    assert len(chapters) == plan.studio_limits.chapter_count_for_limits
    ordinals = [ordinal for chapter in chapters for ordinal in chapter["segment_ordinals"]]  # type: ignore[union-attr]
    assert ordinals == list(range(1, len(segments) + 1))
    for chapter in chapters:
        assert chapter["segment_ordinals"]
        for ordinal in chapter["segment_ordinals"]:  # type: ignore[union-attr]
            assert segments[ordinal - 1]["chapter_ordinal"] == chapter["ordinal"]


def test_chapter_before_the_first_heading1_has_no_title() -> None:
    chapters = _chapters(_book(_TABLE_CASES["b0_h1_b"].groups))

    assert chapters[0]["title"] is None
    assert chapters[1]["title"] == "Квазибург"


@pytest.mark.parametrize("case_id", ["b1_b2_after_scene_break", "no_headings"])
def test_book_without_heading1_is_one_untitled_chapter(case_id: str) -> None:
    groups = _TABLE_CASES[case_id].groups
    chapters = _chapters(_book(groups))

    assert len(chapters) == 1
    assert chapters[0]["title"] is None
    assert chapters[0]["segment_ordinals"] == list(range(1, len(groups) + 1))


def test_chapter_title_is_the_merged_plan_paragraph_text() -> None:
    groups = _TABLE_CASES["series_h2_h1_b"].groups
    plan = build_narration_document_plan(groups)
    chapters = _chapters(_book(groups, plan=plan))

    assert chapters[0]["title"] == plan.paragraphs[0].text
    assert chapters[0]["title"] != groups[1].text


def test_heading1_count_comes_from_the_plan() -> None:
    groups = _TABLE_CASES["h1_b_h1_heading_last"].groups
    plan = build_narration_document_plan(groups)

    assert _stats(_book(groups, plan=plan))["heading1_count"] == plan.studio_limits.heading1_count == 2


# --- T-G4: anti-vacuum of series and of coinciding pauses -------------------------------------


def test_no_pause_inside_a_series_but_a_pause_without_it() -> None:
    in_series = _book((_h(2, "Часть первая"), _h(1, "Квазибург"), _b("Тело.")))
    apart = _book((_h(2, "Часть первая"), _b("Вступление."), _h(1, "Квазибург"), _b("Тело.")))

    assert in_series.pause_kinds[0] is None
    assert apart.pause_kinds[0] == HEADING
    assert apart.pause_kinds == (HEADING, None, CHAPTER, None)


def test_chapter_and_scene_break_coinciding_give_the_longer_scene_break() -> None:
    book = _book(_TABLE_CASES["h1_b1_after_scene_break_b2"].groups)

    assert NARRATION_PAUSE_DEFAULT_SECONDS[SCENE] > NARRATION_PAUSE_DEFAULT_SECONDS[CHAPTER]
    assert _segments(book)[0]["pause_after"] == {"kind": SCENE, "seconds": NARRATION_PAUSE_DEFAULT_SECONDS[SCENE]}
    assert book.pause_counts[CHAPTER] == 0
    assert book.pause_counts[SCENE] == 1


def test_coinciding_pauses_are_decided_by_seconds_not_by_kind() -> None:
    """Anti-vacuum of the rule above: longer chapter seconds turn the same coincidence into ``chapter``."""

    seconds = {CHAPTER: 3.0, HEADING: 0.8, SCENE: 2.0}
    book = _book(_TABLE_CASES["h1_b1_after_scene_break_b2"].groups, pause_seconds=seconds)

    assert _segments(book)[0]["pause_after"] == {"kind": CHAPTER, "seconds": 3.0}


def test_pause_seconds_argument_is_written_into_the_file() -> None:
    seconds = {CHAPTER: 1.0, HEADING: 0.5, SCENE: 2.5}
    book = _book(_TABLE_CASES["h1_h2_b"].groups, pause_seconds=seconds)

    assert [segment["pause_after"] for segment in _segments(book)] == [
        {"kind": CHAPTER, "seconds": 1.0},
        {"kind": HEADING, "seconds": 0.5},
        None,
    ]


def test_heading_without_a_level_gets_no_pause() -> None:
    """072 (г): a level-less heading is no series, so it carries no series pause."""

    book = _book((_h(1, "Квазибург"), _h(None, "Без уровня"), _b("Тело.")))

    assert book.pause_kinds == (CHAPTER, None, None)


# --- T-G5: the shape of the file ------------------------------------------------------------


def test_top_level_keys_are_the_closed_set_in_order() -> None:
    book = _book(_TABLE_CASES["h1_b_b"].groups)

    assert tuple(book.payload) == NARRATION_BOOK_TOP_LEVEL_KEYS
    assert NARRATION_BOOK_TOP_LEVEL_KEYS == (
        "schema_version",
        "producer",
        "book",
        "chapter_heading_level",
        "chapters",
        "segments",
        "reading_glossary",
        "stats",
    )
    assert book.payload["schema_version"] == NARRATION_BOOK_SCHEMA_VERSION == 1


def test_book_carries_only_the_source_name_and_token() -> None:
    book = _book(_TABLE_CASES["h1_b_b"].groups)

    assert book.payload["book"] == {"source_name": _SOURCE.source_name, "source_token": _SOURCE.source_token}
    assert list(book.payload["book"]) == ["source_name", "source_token"]  # type: ignore[arg-type]


@pytest.mark.parametrize("version", ["0f1e2d3", None])
def test_producer_carries_the_given_version_or_null(version: str | None) -> None:
    producer = NarrationBookProducer(version=version, run_id="run-abc", produced_at="2026-11-10T00:00:00Z")
    book = _book(_TABLE_CASES["h1_b_b"].groups, producer=producer)

    assert book.payload["producer"] == {
        "name": "DocxAICorrector",
        "version": version,
        "run_id": "run-abc",
        "produced_at": "2026-11-10T00:00:00Z",
    }
    assert list(book.payload["producer"]) == ["name", "version", "run_id", "produced_at"]  # type: ignore[arg-type]
    assert json.loads(book.to_json())["producer"]["version"] == version


def test_reading_glossary_is_the_given_entries_in_order() -> None:
    entries = (_Entry("XyZ-QW", "икс-игрек-зет"), _Entry("ABC", "а-бэ-цэ"))
    book = _book(_TABLE_CASES["h1_b_b"].groups, glossary=entries)

    assert book.payload["reading_glossary"] == [
        {"abbreviation": "XyZ-QW", "reading": "икс-игрек-зет"},
        {"abbreviation": "ABC", "reading": "а-бэ-цэ"},
    ]
    assert _stats(book)["reading_glossary_entry_count"] == 2
    assert _book(_TABLE_CASES["h1_b_b"].groups).payload["reading_glossary"] == []


def test_stats_carry_the_run_numbers() -> None:
    groups = _TABLE_CASES["h1_b1_after_scene_break_b2"].groups
    book = _book(groups, excluded_count=3, excluded_by_reason={"scene_break": 1, "fragment": 2})

    assert _stats(book) == {
        "char_count": len(_tts_text(groups)),
        "segment_count": 3,
        "chapter_count": 1,
        "heading1_count": 1,
        "scene_break_count": 1,
        "pause_counts": {CHAPTER: 0, HEADING: 0, SCENE: 1},
        "excluded_count": 3,
        "excluded_by_reason": {"scene_break": 1, "fragment": 2},
        "reading_glossary_entry_count": 0,
    }
    assert list(_stats(book)) == [
        "char_count",
        "segment_count",
        "chapter_count",
        "heading1_count",
        "scene_break_count",
        "pause_counts",
        "excluded_count",
        "excluded_by_reason",
        "reading_glossary_entry_count",
    ]


def test_to_json_round_trips_and_keeps_the_acute_as_a_character() -> None:
    book = _book(_contract_groups())
    text = book.to_json()

    assert json.loads(text) == book.payload
    assert text == json.dumps(book.payload, ensure_ascii=False, indent=1) + "\n"
    assert ACUTE in text
    assert "\\u0301" not in text
    assert "\\u04" not in text  # Cyrillic is written as is, not escaped
    assert "\r" not in text
    assert text.endswith("}\n")


# --- T-G6: the plan and the groups must walk in step ------------------------------------------


def test_heading_group_of_two_records_breaks_the_step_and_raises() -> None:
    groups = (
        _Group(paragraph_ids=(_next_id(), _next_id()), role="heading", heading_level=1, text="Квазибург"),
        _b("Тело."),
    )

    with pytest.raises(ValueError):
        _book(groups)


def test_plan_of_other_groups_raises() -> None:
    groups = _TABLE_CASES["h1_b_b"].groups
    other_plan = build_narration_document_plan(_TABLE_CASES["b0_h1_b"].groups)

    with pytest.raises(ValueError):
        _book(groups, plan=other_plan)


def test_empty_groups_raise() -> None:
    with pytest.raises(ValueError):
        _book(())


# --- T-G7: the module is pure — no python-docx, no Streamlit, no I/O ------------------------

_ALLOWED_IMPORTS = {"__future__", "collections", "dataclasses", "json", "types", "typing", "docxaicorrector"}


def test_module_imports_only_pure_modules() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    project_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
            if (node.module or "").startswith("docxaicorrector"):
                project_modules.add(node.module or "")
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert imported <= _ALLOWED_IMPORTS, imported
    assert project_modules <= {"docxaicorrector.pipeline.narration_document"}, project_modules
    assert "open" not in names


def test_importing_the_module_loads_neither_docx_nor_streamlit() -> None:
    probe = (
        "import docxaicorrector.pipeline.narration_book;"
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
