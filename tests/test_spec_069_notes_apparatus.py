"""Spec 069 FR-005 (a), (b) -- the block prompt names the notes that carry the author's text.

Spec 067 FR-001 marks a run of chapter-end notes the import left in the body, and the block
prompt names that PARAGRAPH under «СПРАВОЧНЫЙ АППАРАТ БЛОКА» with the D1 rule "keep references
as they are, translate only the commentary". The bake-off of spec 063 (``research.md`` R4)
showed what a rule addressed to a paragraph does when the paragraph holds 2-13 notes of both
kinds: a strong model decides for the whole paragraph ("mostly references -- keep it") and
leaves a real comment in English; a weak one translates everything, author names included.

So the rule is now addressed to the NOTE. For each marked paragraph in marker mode the section
adds one line naming the notes whose entry is not a reference by the per-entry test of spec 067
(``output_validation.notes_run_commentary_numbers``): "В абзаце [[DOCX_PARA_id]] авторский
текст есть в примечаниях N, M: его переведите, ссылки и имена авторов в них оставьте". A run of
references only gets no line. Rule 12 of ``operation_translate.txt`` says the same in general:
decide per note, not per paragraph, and an author's name is part of the reference.

Orchestrator decision O-4 (2026-11-09): this change is common to every translation mode,
``single`` included. What does NOT change is pinned below as golden bytes: the section of a
block without a run of notes, and every rule of the translate prompt except rule 12.

All texts are invented, of the same form as the bake-off paragraphs; no book text.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import docxaicorrector.pipeline.block_execution as block_execution
from docxaicorrector.core.models import (
    BACK_MATTER_SECTION_NOTES,
    BACK_MATTER_SECTION_REFERENCES,
    DocumentBlock,
    ParagraphUnit,
)
from docxaicorrector.document import semantic_blocks
from docxaicorrector.pipeline import output_validation
from docxaicorrector.pipeline.contracts import BlockExecutionPayload
from docxaicorrector.pipeline.job_parsing import parse_processing_job
from tests.test_spec_063_apparatus_policy import _capture_block_prompt  # the 063 request capture

_TRANSLATE = SimpleNamespace(processing_operation="translate")
_PROMPT_PATH = (
    Path(block_execution.__file__).resolve().parents[1] / "resources" / "prompts" / "operation_translate.txt"
)

# The D1 rule line, byte for byte as before this spec.
_RULE_BYTES = (
    "- Записи библиографии и ссылки на источники оставляйте как есть, на языке оригинала: "
    "авторов, названия, издательства, годы, страницы и адреса не переводите и не "
    "транслитерируйте. Переводите только авторский комментарий."
)

# --- invented texts --------------------------------------------------------------------------

_PROSE = (
    "A harbour is not a place but an arrangement among its pilots to treat one stretch of water "
    "as a shelter from the storm, and that arrangement is what this chapter is about."
)
_REFERENCE_ONE = "R. Hall, *The Harbour Ledger: Annual Review* (Kelbrook: Tidewater Press, 2011), p. 14."
_REFERENCE_THREE = "J. Smith and K. Lee, ‘Credit and the Tide’, *Journal of Harbour Studies* 12(3), pp. 4-19."
_COMMENT = (
    "The lantern survey of the northern ports estimates the tonnage moved through the three quays at roughly "
    "four hundred million a year, a figure the guild never published and its own clerks disputed for a decade."
)
_SECOND_COMMENT = (
    "This is the title of a pamphlet the pilots printed at their own cost and handed out on the quays, "
    "and the council never answered it in writing."
)
# References and one comment (note 2).
_RUN_WITH_ONE_COMMENT = f"1 {_REFERENCE_ONE} 2 {_COMMENT} 3 {_REFERENCE_THREE}"
# References only.
_RUN_OF_REFERENCES = (
    "4 M. Ortega, *The Second Ledger* (Madrid: Prensa, 2011), p. 40. "
    "5 Bureau of Harbour Statistics, ‘Quarterly Bulletin of Port Traffic’, March 2012, www.harbourstats.example.org."
)
# Two comments (notes 7 and 9) around a reference.
_RUN_WITH_TWO_COMMENTS = (
    f"6 {_REFERENCE_THREE} 7 {_SECOND_COMMENT} 8 R. Brown, *Credit and Trust* (Oxford: Clarendon, 2001), p. 12. "
    f"9 {_COMMENT}"
)


def _payload(
    texts: list[str],
    *,
    notes: list[int] | None = None,
    regions: list[str] | None = None,
    section: str | None = None,
) -> SimpleNamespace:
    paragraph_ids = [f"p{index:04d}" for index in range(len(texts))]
    return SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text="\n\n".join(texts),
        target_text_with_markers="\n\n".join(f"[[DOCX_PARA_{pid}]]\n{text}" for pid, text in zip(paragraph_ids, texts)),
        paragraph_ids=paragraph_ids,
        structural_roles=["body"] * len(texts),
        paragraph_regions=regions or ["prose"] * len(texts),
        back_matter_section=section,
        notes_in_body_paragraph_ids=[paragraph_ids[index] for index in (notes or [])],
        narration_include=True,
    )


def _section(payload: SimpleNamespace, *, marker_mode: bool = True) -> str:
    return block_execution._build_block_apparatus_prompt(
        context=_TRANSLATE, payload=payload, marker_mode_enabled=marker_mode
    )


# =============================================================================================
# A. Golden bytes (O-4): what this spec does NOT change
# =============================================================================================


def test_golden_a_back_matter_notes_block() -> None:
    payload = _payload([_REFERENCE_ONE, _REFERENCE_THREE], regions=["back_matter"] * 2, section=BACK_MATTER_SECTION_NOTES)
    assert _section(payload) == (
        "СПРАВОЧНЫЙ АППАРАТ БЛОКА:\n- Раздел: примечания\n- Абзацы: все абзацы блока\n" + _RULE_BYTES
    )


def test_golden_a_mixed_block_with_a_reference_list_entry() -> None:
    payload = _payload(
        [_PROSE, _REFERENCE_ONE], regions=["prose", "back_matter"], section=BACK_MATTER_SECTION_REFERENCES
    )
    assert _section(payload) == (
        "СПРАВОЧНЫЙ АППАРАТ БЛОКА:\n- Раздел: список литературы\n- Абзацы: [[DOCX_PARA_p0001]]\n" + _RULE_BYTES
    )


def test_golden_a_back_matter_notes_paragraph_that_is_a_run_is_named_as_before() -> None:
    """The per-note line belongs to the run of notes the import left in the BODY (the 067 mark,
    where the bake-off measured the defect). A notes section in the back matter keeps its
    section exactly as before: its paragraphs were not measured, so they are not touched."""
    payload = _payload(
        [_PROSE, _RUN_WITH_ONE_COMMENT], regions=["prose", "back_matter"], section=BACK_MATTER_SECTION_NOTES
    )
    assert _section(payload) == (
        "СПРАВОЧНЫЙ АППАРАТ БЛОКА:\n- Раздел: примечания\n- Абзацы: [[DOCX_PARA_p0001]]\n" + _RULE_BYTES
    )


def test_golden_a_body_run_of_references_only() -> None:
    payload = _payload([_PROSE, _RUN_OF_REFERENCES], notes=[1])
    assert _section(payload) == (
        "СПРАВОЧНЫЙ АППАРАТ БЛОКА:\n- Раздел: примечания\n- Абзацы: [[DOCX_PARA_p0001]]\n" + _RULE_BYTES
    )


@pytest.mark.parametrize(
    ("texts", "notes", "scope"),
    [
        pytest.param([_PROSE, _RUN_WITH_ONE_COMMENT], [1], "абзацы с нумерованными примечаниями в блоке", id="mixed-block"),
        pytest.param([_RUN_WITH_ONE_COMMENT], [0], "все абзацы блока", id="whole-block"),
    ],
)
def test_golden_without_markers_the_section_is_as_before(texts: list[str], notes: list[int], scope: str) -> None:
    """Without markers there is no paragraph id to address a note by, so nothing is added."""
    payload = _payload(texts, notes=notes)
    assert _section(payload, marker_mode=False) == (
        f"СПРАВОЧНЫЙ АППАРАТ БЛОКА:\n- Раздел: примечания\n- Абзацы: {scope}\n" + _RULE_BYTES
    )


def test_golden_no_section_for_a_block_without_apparatus_or_outside_translation() -> None:
    assert _section(_payload([_PROSE, _RUN_WITH_ONE_COMMENT])) == ""
    edit = SimpleNamespace(processing_operation="edit")
    marked = _payload([_PROSE, _RUN_WITH_ONE_COMMENT], notes=[1])
    assert block_execution._build_block_apparatus_prompt(context=edit, payload=marked, marker_mode_enabled=True) == ""


def test_golden_the_translate_prompt_outside_rule_12_is_unchanged() -> None:
    lines = _PROMPT_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(index for index, line in enumerate(lines) if line.startswith("12. "))
    end = next(index for index, line in enumerate(lines) if line.startswith("13. "))
    rest = "".join(lines[:start] + lines[end:])
    assert (len(rest), hashlib.sha256(rest.encode("utf-8")).hexdigest()) == (
        1793,
        "e48d378ba1eb786589f500bedaee58072703b8248ecf7667380967bd45a4f124",
    )


# =============================================================================================
# B. The per-note line (red on main)
# =============================================================================================


def test_the_commentary_numbers_are_the_entries_that_are_not_references() -> None:
    assert output_validation.notes_run_commentary_numbers(_RUN_WITH_ONE_COMMENT) == (2,)
    assert output_validation.notes_run_commentary_numbers(_RUN_WITH_TWO_COMMENTS) == (7, 9)
    # Counter-rules: a run of references names nothing; prose is not a run at all.
    assert output_validation.notes_run_commentary_numbers(_RUN_OF_REFERENCES) == ()
    assert output_validation.notes_run_commentary_numbers(_PROSE) == ()


def test_the_section_names_the_notes_that_carry_the_authors_text() -> None:
    payload = _payload([_PROSE, _RUN_WITH_TWO_COMMENTS, _RUN_OF_REFERENCES, _RUN_WITH_ONE_COMMENT], notes=[1, 2, 3])

    section = _section(payload)

    assert section == "\n".join(
        (
            "СПРАВОЧНЫЙ АППАРАТ БЛОКА:",
            "- Раздел: примечания",
            "- Абзацы: [[DOCX_PARA_p0001]], [[DOCX_PARA_p0002]], [[DOCX_PARA_p0003]]",
            _RULE_BYTES,
            "- В абзаце [[DOCX_PARA_p0001]] авторский текст есть в примечаниях 7, 9: "
            "его переведите, ссылки и имена авторов в них оставьте.",
            "- В абзаце [[DOCX_PARA_p0003]] авторский текст есть в примечании 2: "
            "его переведите, ссылки и имена авторов в нём оставьте.",
        )
    )
    # Counter-rule: the run of references only (p0002) gets no line.
    assert "В абзаце [[DOCX_PARA_p0002]]" not in section


def test_a_whole_block_of_runs_is_still_addressed_note_by_note() -> None:
    payload = _payload([_RUN_WITH_ONE_COMMENT], notes=[0])
    section = _section(payload)
    assert "- Абзацы: все абзацы блока" in section
    assert section.endswith(
        "- В абзаце [[DOCX_PARA_p0000]] авторский текст есть в примечании 2: "
        "его переведите, ссылки и имена авторов в нём оставьте."
    )


def test_no_line_when_the_source_cannot_be_addressed_paragraph_by_paragraph() -> None:
    """The numbers are read off the block's own SOURCE per paragraph; a marker text that does
    not carry every expected marker gives no per-note line (never a guess)."""
    payload = _payload([_PROSE, _RUN_WITH_ONE_COMMENT], notes=[1])
    payload.target_text_with_markers = payload.target_text
    section = _section(payload)
    assert "- Абзацы: [[DOCX_PARA_p0001]]" in section
    assert "В абзаце" not in section


# --- through the document layer and the request ----------------------------------------------


def _unit(text: str, pid: str, *, role: str = "body", level: int | None = None) -> ParagraphUnit:
    return ParagraphUnit(text=text, role=role, paragraph_id=pid, heading_level=level, structural_role=role)


def test_a_chapter_ending_with_its_notes_sends_the_per_note_line_in_the_request() -> None:
    """The bake-off shape, invented: a chapter of prose whose numbered notes follow it as body
    paragraphs. The 067 mark is set on the document layer, travels in the job, and the request
    the model receives names the note that carries the author's text."""
    book = [
        DocumentBlock(paragraphs=[_unit("Chapter Three", "p0000", role="heading", level=1), _unit(_PROSE, "p0001")]),
        DocumentBlock(
            paragraphs=[
                _unit(_PROSE, "p0002"),
                _unit(_RUN_WITH_ONE_COMMENT, "p0003"),
                _unit(_RUN_OF_REFERENCES, "p0004"),
            ]
        ),
    ]
    jobs = semantic_blocks.build_editing_jobs(book, max_chars=3000, processing_operation="translate")
    job = next(job for job in jobs if "p0003" in cast(list[str], job["paragraph_ids"]))
    assert set(cast(list[str], job["notes_in_body_paragraph_ids"])) == {"p0003", "p0004"}
    payload = parse_processing_job(job=job, payload_factory=BlockExecutionPayload)

    prompt = _capture_block_prompt(cast(SimpleNamespace, payload))

    assert "- Абзацы: [[DOCX_PARA_p0003]], [[DOCX_PARA_p0004]]" in prompt
    assert (
        "- В абзаце [[DOCX_PARA_p0003]] авторский текст есть в примечании 2: "
        "его переведите, ссылки и имена авторов в нём оставьте."
    ) in prompt
    assert "В абзаце [[DOCX_PARA_p0004]]" not in prompt


# --- rule 12 -----------------------------------------------------------------------------------


def test_rule_12_says_to_decide_per_note_and_that_an_authors_name_is_part_of_the_reference() -> None:
    lines = _PROMPT_PATH.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("12. "))
    end = next(index for index, line in enumerate(lines) if line.startswith("13. "))
    rule = " ".join(lines[start:end])
    assert "решайте по каждому примечанию, а не по абзацу целиком" in rule
    assert "имя автора — часть ссылки" in rule
