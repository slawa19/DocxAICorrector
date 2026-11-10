"""Spec 073 WP-D (FR-006, SC-006): a scene separator leaves a mark in the narration assembly.

A paragraph excluded with the reason ``fragment`` whose SOURCE is non-empty and has no letter and no digit (the form
``is_scene_break_text``: ``***``, ``# %``) and that stands between two narrated paragraphs marks the next group as
"after a scene break"; the mark forbids the deterministic body+body join across it (research R8, data-model §6).

Two layers:

* characterization (T-D1) -- what must NOT change: a set without separators gives the same groups and joins as
  before; written green on ``e121990`` BEFORE any production edit;
* the new behaviour (T-D2...T-D5) -- each fails without the change (the state field, the function, the parameter or
  the group field is not there).

All texts are invented, of the same FORM as book text; no book of the corpus is quoted (Constitution VII).
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from docxaicorrector.pipeline import audiobook_pass
from docxaicorrector.pipeline.audiobook_pass import NarrationParagraphRecord, register_audiobook_block
from docxaicorrector.pipeline.contracts import ProcessingState
from docxaicorrector.pipeline.narration_postprocess import _build_narration_text, assemble_narration_records
from docxaicorrector.text.narration_coverage import CoverageResult

# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------

# Token of a block paragraph -> (exclusion reason, source text). ``B``/``H`` tokens are narrated (reason ``None``)
# and take their source from the record table of the test; ``*`` is a scene separator; ``x`` is an exclusion
# that is not one (a ``fragment`` WITH a letter); ``t`` is an exclusion by another reason whose source has the
# separator's form -- only ``fragment`` gives the mark, so it is as transparent as ``x``.
_SEPARATOR_SOURCES = ("***", "# %", "— — —")
_LETTERED_FRAGMENT = "Квазибург"


def _record(pid: str, text: str, role: str = "body", block_index: int = 0) -> NarrationParagraphRecord:
    return NarrationParagraphRecord(
        paragraph_id=pid,
        block_index=block_index,
        role=role,
        text=text,
        needs_review_reasons=(),
        residue_before=(),
        residue_after=(),
        coverage=CoverageResult(0, 0, None),
    )


def _payload(paragraphs: list[tuple[str, str, str | None]]) -> SimpleNamespace:
    """``(paragraph_id, source text, exclusion reason)`` per paragraph, in block order."""

    ids = [item[0] for item in paragraphs]
    texts = [item[1] for item in paragraphs]
    reasons = [item[2] for item in paragraphs]
    return SimpleNamespace(
        paragraph_ids=ids,
        target_text="\n\n".join(texts),
        target_text_with_markers="\n\n".join(f"[[DOCX_PARA_{pid}]]\n{text}" for pid, text in zip(ids, texts)),
        narration_exclusion_reasons=reasons,
        narration_include=any(reason is None for reason in reasons),
    )


def _register(state: object, blocks: list[list[tuple[str, str, str | None]]]) -> None:
    for index, block in enumerate(blocks):
        register_audiobook_block(state=state, payload=_payload(block), block_index=index)


def _context() -> SimpleNamespace:
    return SimpleNamespace(processing_operation="audiobook", uploaded_filename="book.docx", runtime=None)


def _build(state: object) -> str | None:
    return _build_narration_text(context=_context(), dependencies=None, emitters=None, state=state)


# --------------------------------------------------------------------------------------------
# T-D1 (characterization): no separator -> the same groups and joins as before
# --------------------------------------------------------------------------------------------


def _no_separator_blocks() -> list[list[tuple[str, str, str | None]]]:
    return [
        [
            ("p1", "# Глава первая", None),
            ("p2", "Дорога вела вдоль реки и никто", None),
            ("p3", _LETTERED_FRAGMENT, "fragment"),
            ("p4", "не спрашивал, куда он идёт.", None),
        ],
        [
            ("p5", "Утром он вышел к мосту и", None),
            ("p6", "Рисунок 1", "caption"),
        ],
        [
            ("p7", "долго смотрел на воду.", None),
            ("p8", "Последний абзац главы.", None),
        ],
    ]


def _no_separator_records() -> list[NarrationParagraphRecord]:
    return [
        _record("p1", "Глава первая", role="heading"),
        _record("p2", "Дорога вела вдоль реки и никто"),
        _record("p4", "не спрашивал, куда он идёт."),
        _record("p5", "Утром он вышел к мосту и", block_index=1),
        _record("p7", "долго смотрел на воду.", block_index=2),
        _record("p8", "Последний абзац главы.", block_index=2),
    ]


def test_t_d1_without_separators_the_groups_and_joins_are_the_snapshot() -> None:
    state = ProcessingState()
    _register(state, _no_separator_blocks())
    state.narration_paragraphs = _no_separator_records()

    text = _build(state)

    # Snapshot written by hand from the 072 rules and confirmed green on e121990 before any edit.
    assert state.narration_expected_paragraph_ids == ["p1", "p2", "p4", "p5", "p7", "p8"]
    assert state.narration_joined_paragraph_id_pairs == [("p2", "p4"), ("p5", "p7")]
    assert [group.paragraph_ids for group in state.narration_groups] == [("p1",), ("p2", "p4"), ("p5", "p7"), ("p8",)]
    assert text == (
        "Глава первая\n\n"
        "Дорога вела вдоль реки и никто не спрашивал, куда он идёт.\n\n"
        "Утром он вышел к мосту и долго смотрел на воду.\n\n"
        "Последний абзац главы."
    )
    assert text == assemble_narration_records(_no_separator_records()).text
    assert state.narration_paragraph_boundary_check == "ok"


# --------------------------------------------------------------------------------------------
# T-D2: registration writes the kind of every paragraph of the block, in order
# --------------------------------------------------------------------------------------------


def test_t_d2_register_writes_the_paragraph_kinds_over_two_blocks() -> None:
    state = ProcessingState()
    _register(
        state,
        [
            [
                ("p1", "Первый абзац.", None),
                ("p2", "***", "fragment"),
                ("p3", _LETTERED_FRAGMENT, "fragment"),
                ("p4", "***", "toc"),
            ],
            [
                ("p5", "### # %", "fragment"),
                ("p6", "Второй абзац.", None),
                ("p7", "", "fragment"),
            ],
        ],
    )

    assert state.narration_paragraph_kinds == [
        ("p1", "narrated"),
        ("p2", "scene_break"),
        ("p3", "excluded"),
        ("p4", "excluded"),
        ("p5", "scene_break"),
        ("p6", "narrated"),
        ("p7", "excluded"),
    ]
    # The exclusions and the denominator are recorded exactly as before.
    assert state.narration_expected_paragraph_ids == ["p1", "p6"]
    assert [item["paragraph_id"] for item in state.narration_exclusions] == ["p2", "p3", "p4", "p5", "p7"]


def test_t_d2_the_kinds_vocabulary_is_closed() -> None:
    assert audiobook_pass.NARRATION_PARAGRAPH_KINDS == ("narrated", "scene_break", "excluded")
    state = ProcessingState()
    _register(state, [[("p1", "Абзац.", None), ("p2", "***", "fragment"), ("p3", "Квазибург", "fragment")]])
    assert {kind for _, kind in state.narration_paragraph_kinds} <= set(audiobook_pass.NARRATION_PARAGRAPH_KINDS)


@pytest.mark.parametrize("source", _SEPARATOR_SOURCES)
def test_t_d2_every_separator_form_is_a_scene_break(source: str) -> None:
    state = ProcessingState()
    _register(state, [[("p1", "Абзац и", None), ("p2", source, "fragment"), ("p3", "абзац.", None)]])
    assert state.narration_paragraph_kinds == [("p1", "narrated"), ("p2", "scene_break"), ("p3", "narrated")]


def test_t_d2_a_fully_narrated_block_needs_no_source_and_writes_narrated_kinds() -> None:
    state = ProcessingState()
    _register(state, [[("p1", "Абзац.", None), ("p2", "Ещё абзац.", None)]])
    assert state.narration_paragraph_kinds == [("p1", "narrated"), ("p2", "narrated")]


# --------------------------------------------------------------------------------------------
# T-D3: the table of data-model §6, row by row, through the pure function and the text builder
# --------------------------------------------------------------------------------------------

# Narrated texts by id: ``B*`` end without a terminal and begin lowercase, so any B+B pair WOULD be joined by the
# 072 rule -- the only thing that can keep them apart is the mark. ``H1`` is a heading.
_TABLE_TEXTS: dict[str, tuple[str, str]] = {
    "B1": ("body", "он шёл вдоль берега и"),
    "B2": ("body", "не оглядывался назад и"),
    "B3": ("body", "дошёл до моста к вечеру"),
    "H1": ("heading", "Часть вторая"),
}


def _block_rows(tokens: list[str], start: int) -> tuple[list[tuple[str, str, str | None]], int]:
    rows: list[tuple[str, str, str | None]] = []
    counter = start
    for token in tokens:
        if token == "*":
            counter += 1
            rows.append((f"s{counter}", "***", "fragment"))
        elif token == "x":
            counter += 1
            rows.append((f"x{counter}", _LETTERED_FRAGMENT, "fragment"))
        elif token == "t":
            counter += 1
            rows.append((f"t{counter}", "***", "toc"))
        else:
            rows.append((token, _TABLE_TEXTS[token][1], None))
    return rows, counter


# (row name, blocks of tokens, ids whose record text is empty, expected marks, expected groups, expected flags)
_TABLE = [
    ("B1 * B2", [["B1", "*", "B2"]], (), {"B2"}, [("B1",), ("B2",)], [False, True]),
    ("B1 * * B2", [["B1", "*", "*", "B2"]], (), {"B2"}, [("B1",), ("B2",)], [False, True]),
    ("B1 * x B2", [["B1", "*", "x", "B2"]], (), {"B2"}, [("B1",), ("B2",)], [False, True]),
    ("B1 x * B2", [["B1", "x", "*", "B2"]], (), {"B2"}, [("B1",), ("B2",)], [False, True]),
    ("B1 x B2", [["B1", "x", "B2"]], (), set(), [("B1", "B2")], [False]),
    ("B1 t B2 (another reason, separator form)", [["B1", "t", "B2"]], (), set(), [("B1", "B2")], [False]),
    ("* B1 B2 (start of the book)", [["*", "B1", "B2"]], (), set(), [("B1", "B2")], [False]),
    ("B1 B2 * (end of the book)", [["B1", "B2", "*"]], (), set(), [("B1", "B2")], [False]),
    ("H1 * B1", [["H1", "*", "B1"]], (), {"B1"}, [("H1",), ("B1",)], [False, True]),
    ("B1 * | B2 (block boundary)", [["B1", "*"], ["B2"]], (), {"B2"}, [("B1",), ("B2",)], [False, True]),
    ("B1 | * B2 (block boundary)", [["B1"], ["*", "B2"]], (), {"B2"}, [("B1",), ("B2",)], [False, True]),
    ("B1 * B2(empty) B3", [["B1", "*", "B2", "B3"]], ("B2",), {"B3"}, [("B1",), ("B3",)], [False, True]),
    ("B1(empty) * B2 (nothing narrated before)", [["B1", "*", "B2"]], ("B1",), set(), [("B2",)], [False]),
]


def _table_state(blocks: list[list[str]], empty_ids: tuple[str, ...]) -> ProcessingState:
    state = ProcessingState()
    counter = 0
    payload_blocks: list[list[tuple[str, str, str | None]]] = []
    for tokens in blocks:
        rows, counter = _block_rows(tokens, counter)
        payload_blocks.append(rows)
    _register(state, payload_blocks)
    state.narration_paragraphs = [
        _record(pid, "" if pid in empty_ids else _TABLE_TEXTS[pid][1], role=_TABLE_TEXTS[pid][0])
        for pid in state.narration_expected_paragraph_ids
    ]
    return state


@pytest.mark.parametrize(
    ("blocks", "empty_ids", "marks", "groups", "flags"),
    [row[1:] for row in _TABLE],
    ids=[row[0] for row in _TABLE],
)
def test_t_d3_the_table_through_the_pure_function(blocks, empty_ids, marks, groups, flags) -> None:
    from docxaicorrector.pipeline.narration_postprocess import scene_break_before_ids

    state = _table_state(blocks, empty_ids)
    present = {record.paragraph_id for record in state.narration_paragraphs if record.text.strip()}

    result = scene_break_before_ids(state.narration_paragraph_kinds, present_ids=present)

    assert isinstance(result, frozenset)
    assert result == marks


@pytest.mark.parametrize(
    ("blocks", "empty_ids", "marks", "groups", "flags"),
    [row[1:] for row in _TABLE],
    ids=[row[0] for row in _TABLE],
)
def test_t_d3_the_table_through_the_text_builder(blocks, empty_ids, marks, groups, flags) -> None:
    state = _table_state(blocks, empty_ids)

    text = _build(state)

    assert [group.paragraph_ids for group in state.narration_groups] == groups
    assert [group.after_scene_break for group in state.narration_groups] == flags
    assert text == "\n\n".join(group.text for group in state.narration_groups)
    # A narrated id left without text is a missing paragraph of the denominator (spec 070 FR-007), reported as a
    # mismatch exactly as before 073; every other row assembles cleanly.
    assert state.narration_paragraph_boundary_check == ("mismatch" if empty_ids else "ok")
    # A join closes exactly the pairs inside a group; none crosses a mark.
    joined_into = {pair[1] for pair in state.narration_joined_paragraph_id_pairs}
    assert not (joined_into & marks)


# --------------------------------------------------------------------------------------------
# T-D4: anti-vacuum -- the same pair is joined without a separator and kept apart with one
# --------------------------------------------------------------------------------------------


def test_t_d4_the_pair_without_a_separator_is_joined_as_before() -> None:
    records = [_record("B1", "он шёл вдоль берега и"), _record("B2", "не оглядывался назад.")]

    assembly = assemble_narration_records(records)

    assert assembly.join_pairs == (("B1", "B2"),)
    assert [group.paragraph_ids for group in assembly.groups] == [("B1", "B2")]


def test_t_d4_the_same_pair_with_a_separator_is_two_groups() -> None:
    records = [_record("B1", "он шёл вдоль берега и"), _record("B2", "не оглядывался назад.")]

    assembly = assemble_narration_records(records, scene_break_before_ids=frozenset({"B2"}))

    assert assembly.join_pairs == ()
    assert [group.paragraph_ids for group in assembly.groups] == [("B1",), ("B2",)]
    assert [group.after_scene_break for group in assembly.groups] == [False, True]
    assert assembly.text == "\n\n".join(group.text for group in assembly.groups)
    assert assembly.boundary_check == "ok"


def test_t_d4_through_registration_the_separator_keeps_the_pair_apart() -> None:
    joined = ProcessingState()
    _register(joined, [[("B1", "он шёл вдоль берега и", None), ("B2", "не оглядывался назад.", None)]])
    joined.narration_paragraphs = [_record("B1", "он шёл вдоль берега и"), _record("B2", "не оглядывался назад.")]
    apart = ProcessingState()
    _register(
        apart,
        [[("B1", "он шёл вдоль берега и", None), ("S", "***", "fragment"), ("B2", "не оглядывался назад.", None)]],
    )
    apart.narration_paragraphs = [_record("B1", "он шёл вдоль берега и"), _record("B2", "не оглядывался назад.")]

    joined_text = _build(joined)
    apart_text = _build(apart)

    assert joined_text == "он шёл вдоль берега и не оглядывался назад."
    assert apart_text == "он шёл вдоль берега и\n\nне оглядывался назад."
    assert [group.after_scene_break for group in apart.narration_groups] == [False, True]
    assert apart.narration_joined_paragraph_id_pairs == []


def test_t_d4_the_group_field_is_last_and_defaults_to_false() -> None:
    from docxaicorrector.pipeline.narration_postprocess import NarrationGroup

    names = [item.name for item in dataclasses.fields(NarrationGroup)]
    assert names == ["paragraph_ids", "role", "heading_level", "text", "after_scene_break"]
    assert NarrationGroup(paragraph_ids=("p1",), role="body", heading_level=None, text="Абзац.").after_scene_break is False


# --------------------------------------------------------------------------------------------
# T-D5: the run-state declarations of spec 073 (data-model §5)
# --------------------------------------------------------------------------------------------


def test_t_d5_processing_state_declares_the_073_fields() -> None:
    state = ProcessingState()

    assert state.narration_paragraph_kinds == []
    assert state.audiobook_reading_glossary is None
    assert state.audiobook_reading_glossary_block_indexes == set()
    other = ProcessingState()
    assert state.narration_paragraph_kinds is not other.narration_paragraph_kinds
    assert state.audiobook_reading_glossary_block_indexes is not other.audiobook_reading_glossary_block_indexes
