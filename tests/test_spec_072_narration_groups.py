"""Spec 072 WP-A (FR-001, FR-002): narration records know their heading level; the assembly hands out groups.

Two layers:

* characterization tests (T-A1, T-A2) -- they pin what must NOT change (the ``.tts.txt`` bytes, the text of the
  block the DOCX for review is built from) and were written green on ``f6de2fd`` BEFORE any production edit;
* tests of the new behaviour (T-A3...T-A6) -- each fails without the change (the function / field / attribute is
  not there).

All texts are invented, of the same FORM as book text; no book of the corpus is quoted (Constitution VII).
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from docxaicorrector.pipeline.audiobook_pass import (
    AudiobookParagraphInput,
    NarrationParagraphRecord,
    finalize_audiobook_block,
    rebuild_block_with_narration_texts,
)
from docxaicorrector.pipeline.contracts import ProcessingState
from docxaicorrector.pipeline.narration_postprocess import _build_narration_text, assemble_narration_records
from docxaicorrector.text.narration_coverage import CoverageResult

# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------


def _record(pid: str, text: str, role: str = "body", reasons: tuple[str, ...] = (), **extra: object) -> NarrationParagraphRecord:
    return NarrationParagraphRecord(
        paragraph_id=pid,
        block_index=1,
        role=role,
        text=text,
        needs_review_reasons=reasons,
        residue_before=(),
        residue_after=(),
        coverage=CoverageResult(0, 0, None),
        **extra,  # type: ignore[arg-type]
    )


def _golden_records() -> list[NarrationParagraphRecord]:
    """Invented records covering every shape the ``.tts.txt`` assembly has a rule for (T-A1)."""

    return [
        _record("p1", "Глава первая", role="heading"),
        _record("p2", "Он пришёл в посёлок поздним вечером."),
        # a torn sentence: the first half has no terminal, the second begins lowercase -> joined by a space
        _record("p3", "Дорога вела вдоль реки и никто"),
        _record("p4", "не спрашивал, куда он идёт."),
        # a single newline inside one paragraph
        _record("p5", "Первая строка\nвторая строка."),
        # a body paragraph that begins with a hash
        _record("p6", "# не заголовок, а тело."),
        # a combining acute accent and a capital vowel (stress marks for the TTS engine)
        _record("p7", "за́мок и замОк стоят рядом."),
        # needs_review does not change the text
        _record("p8", "Этот абзац вернулся из источника.", reasons=("source_restored",)),
        _record("p9", "Этот абзац целиком взят из источника.", reasons=("source_fallback",)),
        _record("p10", "Подраздел", role="heading"),
        _record("p11", "Последний абзац книги."),
    ]


# SHA-256 of ``assemble_narration_records(_golden_records()).text`` (UTF-8), obtained ONCE on ``f6de2fd`` through
# the canonical path and never edited since (SC-004): the ``.tts.txt`` is byte-for-byte what it was.
_GOLDEN_TTS_SHA256 = "de90dd0e3c727bf4fd6890accf2d4bb3058b3a585b8e93a518663cfb8e2c5b60"


def test_t_a1_the_tts_text_is_byte_for_byte_the_golden_one() -> None:
    assembly = assemble_narration_records(_golden_records())

    assert assembly.boundary_check == "ok"
    assert assembly.join_pairs == (("p3", "p4"),)
    assert hashlib.sha256(assembly.text.encode("utf-8")).hexdigest() == _GOLDEN_TTS_SHA256


# --- T-A2: the text of the block the DOCX for review is built from ------------------------------

_SOURCE_BODY = "Исходный абзац"
_NARRATION_KINDS = {"empty": "", "plain": "Обычный текст озвучки", "hash": "# Текст, начинающийся с решётки"}
_SOURCE_PREFIXES = ("", "# ", "## ", "### ")

# (role, source prefix, narration kind) -> the text the rebuilt block carries for that paragraph. Written by hand
# from the rule "only a HEADING role with a source prefix gets the prefix; an empty text and a text that already
# begins with '#' are left alone" and confirmed green against ``f6de2fd``.
_EXPECTED_BLOCK_TEXT: dict[tuple[str, str, str], str] = {}
for _role in ("heading", "body"):
    for _prefix in _SOURCE_PREFIXES:
        for _kind, _narration in _NARRATION_KINDS.items():
            if _role == "heading" and _prefix and _kind == "plain":
                _EXPECTED_BLOCK_TEXT[(_role, _prefix, _kind)] = f"{_prefix}{_narration}"
            else:
                _EXPECTED_BLOCK_TEXT[(_role, _prefix, _kind)] = _narration

# The same snapshot spelled out for the heading rows, so the table is not only a restatement of the loop above.
assert _EXPECTED_BLOCK_TEXT[("heading", "## ", "plain")] == "## Обычный текст озвучки"
assert _EXPECTED_BLOCK_TEXT[("heading", "### ", "hash")] == "# Текст, начинающийся с решётки"
assert _EXPECTED_BLOCK_TEXT[("heading", "# ", "empty")] == ""
assert _EXPECTED_BLOCK_TEXT[("body", "## ", "plain")] == "Обычный текст озвучки"


def _payload(role: str, source: str) -> SimpleNamespace:
    return SimpleNamespace(
        paragraph_ids=["p1"],
        structural_roles=[role],
        target_text_with_markers=f"[[DOCX_PARA_p1]]\n{source}",
        target_text=source,
        narration_exclusion_reasons=None,
    )


def _rebuild(role: str, prefix: str, narration: str) -> tuple[str, str]:
    source = f"{prefix}{_SOURCE_BODY}"
    payload = _payload(role, source)
    kwargs: dict[str, object] = {}
    # What the finalizer says about the heading level, when it says anything (it does from WP-A on); the call itself
    # is what the block phase makes, so the snapshot holds both before and after the change.
    finalized = finalize_audiobook_block(
        block_index=1,
        paragraphs=[
            AudiobookParagraphInput(
                paragraph_id="p1", role=role, source_text=source, delivered_text="x", status="accepted"
            )
        ],
        repair=None,
    )
    levels = getattr(finalized, "heading_levels_by_id", None)
    if levels is not None:
        kwargs["heading_levels_by_id"] = levels
    rebuilt = rebuild_block_with_narration_texts(
        payload=payload, processed_chunk="ответ модели", texts_by_id={"p1": narration}, **kwargs  # type: ignore[arg-type]
    )
    dispositions = getattr(rebuilt, "paragraph_dispositions", ())
    assert len(dispositions) == 1
    return dispositions[0].text, dispositions[0].status


@pytest.mark.parametrize("role", ["heading", "body"])
@pytest.mark.parametrize("prefix", _SOURCE_PREFIXES, ids=lambda value: f"prefix{len(value.strip())}")
@pytest.mark.parametrize("kind", list(_NARRATION_KINDS))
def test_t_a2_the_block_text_of_the_docx_for_review_is_unchanged(role: str, prefix: str, kind: str) -> None:
    text, status = _rebuild(role, prefix, _NARRATION_KINDS[kind])

    assert text == _EXPECTED_BLOCK_TEXT[(role, prefix, kind)]
    assert status == "accepted"


# --------------------------------------------------------------------------------------------
# T-A3: the one function that reads a heading level (FR-002)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "source", "expected"),
    [
        ("heading", "# Глава", 1),
        ("heading", "## Глава", 2),
        ("heading", "###### Глава", 6),
        ("heading", "  ### Глава с отступом", 3),
        ("heading", "##\tГлава после табуляции", 2),
        (" Heading ", "## Глава", 2),  # the role is compared the way the pass compares it: stripped, case-folded
        ("body", "## Глава", None),  # a body paragraph whose text begins with '#' stays body
        ("heading", "Глава без префикса", None),
        ("heading", "####### Семь решёток", None),
        ("heading", "##Без пробела", None),
        ("heading", "## ", None),  # nothing after the prefix
        ("heading", "", None),
        ("", "## Глава", None),
    ],
)
def test_t_a3_narration_heading_level_reads_role_and_source_prefix(role: str, source: str, expected: int | None) -> None:
    from docxaicorrector.pipeline import audiobook_pass

    assert audiobook_pass.narration_heading_level(role=role, source_text=source) == expected


# --------------------------------------------------------------------------------------------
# T-A4: the finalizer puts the level on the record and in a by-id map (R1)
# --------------------------------------------------------------------------------------------


def _input(pid: str, role: str, source: str, delivered: str) -> AudiobookParagraphInput:
    return AudiobookParagraphInput(paragraph_id=pid, role=role, source_text=source, delivered_text=delivered, status="accepted")


def test_t_a4_finalize_audiobook_block_carries_the_heading_level() -> None:
    finalized = finalize_audiobook_block(
        block_index=3,
        paragraphs=[
            _input("p1", "heading", "## Первая глава", "Первая глава"),
            _input("p2", "body", "## Тело с решёткой", "Тело с решёткой."),
            _input("p3", "heading", "Заголовок без префикса", "Заголовок без префикса"),
            _input("p4", "heading", "### Подраздел", "Подраздел"),
            # an unaddressable input (no id, so no source text): narrated, but it has no key in the by-id map
            _input("", "body", "", "Абзац без адреса."),
        ],
        repair=None,
    )

    by_id = {record.paragraph_id: record for record in finalized.records}
    assert by_id["p1"].heading_level == 2
    assert by_id["p2"].heading_level is None
    assert by_id["p3"].heading_level is None
    assert by_id["p4"].heading_level == 3
    assert by_id[""].heading_level is None
    assert dict(finalized.heading_levels_by_id) == {"p1": 2, "p4": 3}


def test_t_a4_an_unaddressable_input_never_enters_the_by_id_map() -> None:
    finalized = finalize_audiobook_block(
        block_index=1,
        paragraphs=[_input("", "heading", "## Заголовок без адреса", "Заголовок без адреса")],
        repair=None,
    )

    assert len(finalized.records) == 1
    assert dict(finalized.heading_levels_by_id) == {}


def test_t_a4_a_paragraph_with_nothing_narratable_has_no_level() -> None:
    finalized = finalize_audiobook_block(
        block_index=1,
        paragraphs=[_input("p1", "heading", "## Заголовок", "")],
        repair=None,
    )

    # An empty answer falls back to the paragraph's own source; the level is still the source's own.
    assert [record.heading_level for record in finalized.records] == [2]
    assert dict(finalized.heading_levels_by_id) == {"p1": 2}


# --------------------------------------------------------------------------------------------
# T-A5: the assembly hands out the groups the .tts.txt is built from (FR-001, R2)
# --------------------------------------------------------------------------------------------


def _group_records() -> list[NarrationParagraphRecord]:
    return [
        _record("p1", "Часть первая", role="heading", heading_level=1),
        _record("p2", "Глава о начале", role="heading", heading_level=2),
        _record("p3", "Он пришёл в посёлок."),
        _record("p4", "Дорога вела вдоль реки и никто"),
        _record("p5", "не спрашивал, куда он идёт."),
        _record("", "Абзац без адреса."),
        _record("p7", "Заголовок без уровня", role="heading"),
        _record("p8", "Хвост."),
    ]


def test_t_a5_the_groups_are_what_the_text_is_joined_from() -> None:
    records = _group_records()

    assembly = assemble_narration_records(records)

    assert assembly.text == "\n\n".join(group.text for group in assembly.groups)
    flattened = [pid for group in assembly.groups for pid in group.paragraph_ids]
    assert flattened == [record.paragraph_id for record in records]  # the id sequence, with multiplicity, in order
    assert sum(len(group.paragraph_ids) for group in assembly.groups) == len(records)


def test_t_a5_a_joined_group_carries_both_ids_and_one_text() -> None:
    assembly = assemble_narration_records(_group_records())

    joined = [group for group in assembly.groups if len(group.paragraph_ids) > 1]
    assert [group.paragraph_ids for group in joined] == [("p4", "p5")]
    assert joined[0].text == "Дорога вела вдоль реки и никто не спрашивал, куда он идёт."
    assert joined[0].role == "body"
    assert joined[0].heading_level is None


def test_t_a5_a_heading_group_is_one_record_with_its_level() -> None:
    assembly = assemble_narration_records(_group_records())

    headings = [group for group in assembly.groups if group.role == "heading"]
    assert [(group.paragraph_ids, group.heading_level) for group in headings] == [
        (("p1",), 1),
        (("p2",), 2),
        (("p7",), None),  # a heading role without a level (FR-003 (г))
    ]
    assert all(len(group.paragraph_ids) == 1 for group in headings)


def test_t_a5_a_body_group_has_no_heading_level_even_if_its_record_carries_one() -> None:
    assembly = assemble_narration_records([_record("p1", "Абзац тела.", role="body", heading_level=3)])

    assert [group.heading_level for group in assembly.groups] == [None]


def test_t_a5_an_unaddressable_record_is_a_group_with_an_empty_id() -> None:
    assembly = assemble_narration_records([_record("", "Абзац без адреса.")])

    assert [group.paragraph_ids for group in assembly.groups] == [("",)]


def test_t_a5_the_groups_do_not_change_the_text() -> None:
    """The groups are an additional projection; the golden hash of T-A1 holds with them present."""

    assembly = assemble_narration_records(_golden_records())

    assert hashlib.sha256(assembly.text.encode("utf-8")).hexdigest() == _GOLDEN_TTS_SHA256
    assert assembly.text == "\n\n".join(group.text for group in assembly.groups)


# --------------------------------------------------------------------------------------------
# T-A6: the late phase's text builder leaves the groups in the run state
# --------------------------------------------------------------------------------------------


def test_t_a6_build_narration_text_writes_the_groups_and_returns_the_same_text() -> None:
    records = _group_records()
    state = SimpleNamespace(
        narration_paragraphs=records,
        narration_expected_paragraph_ids=[record.paragraph_id for record in records if record.paragraph_id],
    )
    context = SimpleNamespace(processing_operation="audiobook", uploaded_filename="book.docx", runtime=None)

    text = _build_narration_text(context=context, dependencies=None, emitters=None, state=state)

    expected = assemble_narration_records(records)
    assert text == expected.text
    assert state.narration_groups == list(expected.groups)  # type: ignore[attr-defined]
    assert isinstance(state.narration_groups, list)  # type: ignore[attr-defined]


def test_t_a6_other_operations_leave_the_groups_empty() -> None:
    state = ProcessingState()
    context = SimpleNamespace(processing_operation="translate", uploaded_filename="book.docx", runtime=None)

    assert _build_narration_text(context=context, dependencies=None, emitters=None, state=state) is None
    assert state.narration_groups == []


def test_t_a6_processing_state_defaults_to_no_groups() -> None:
    assert ProcessingState().narration_groups == []
    assert ProcessingState().narration_groups is not ProcessingState().narration_groups


# --------------------------------------------------------------------------------------------
# T-A9 (contract): the writer protocol accepts the two new byte arguments, with None defaults
# --------------------------------------------------------------------------------------------


def test_t_a9_the_result_artifact_writer_protocol_has_the_two_optional_byte_arguments() -> None:
    import inspect

    from docxaicorrector.pipeline.contracts import ResultArtifactWriter

    parameters = inspect.signature(ResultArtifactWriter.__call__).parameters
    for name in ("narration_docx_bytes", "narration_pdf_bytes"):
        assert name in parameters
        assert parameters[name].default is None
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
