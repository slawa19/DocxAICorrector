"""Spec 070 FR-003 (WP-D): which paragraphs are not narrated, decided PER PARAGRAPH on the
document layer from role, region and the FORM of the text -- never from words (Constitution VII).

The examples are invented and carry the shape of the real cases only.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from docxaicorrector.core.models import (
    NARRATION_EXCLUSION_REASONS,
    DocumentBlock,
    ParagraphUnit,
)
from docxaicorrector.document.narration_exclusion import (
    is_fragment_without_connected_text,
    resolve_narration_exclusion_reason,
)
from docxaicorrector.document.semantic_blocks import build_editing_jobs
from docxaicorrector.pipeline.contracts import BlockExecutionPayload
from docxaicorrector.pipeline.job_parsing import (
    coerce_narration_exclusion_reasons,
    is_marker_mode_enabled,
    parse_processing_job,
)

_SNAPSHOT_PATH = Path(__file__).parent / "fixtures" / "spec_070_translate_edit_jobs_snapshot.json"

# A run of notes as a PDF text layer delivers it (the shape spec 067 FR-001 recognises).
_NOTES_RUN = (
    "1 R. Hall, *The Tides of Cities* (London: Harbour Press, 2004), p. 85. "
    "2 J. Smith and K. Lee, ‘Money and Debt’, *Journal of Economic Studies* 12(3), 1999, pp. 4-19."
)
_PROSE = (
    "A harbour is not a place but an arrangement among its pilots to treat one stretch of water "
    "as a shelter from the storm, and that arrangement is what this chapter is about."
)


def _unit(
    text: str,
    pid: str,
    *,
    role: str = "body",
    level: int | None = None,
    structural_role: str | None = None,
) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role=role,
        paragraph_id=pid,
        heading_level=level,
        structural_role=structural_role or role,
    )


def _snapshot_blocks() -> list[DocumentBlock]:
    """An invented document that touches every role and region the jobs carry."""
    return [
        DocumentBlock(
            paragraphs=[
                _unit("Chapter One", "p0000", role="heading", level=1),
                _unit("The harbour woke slowly under a thin grey light, and nobody on the quay spoke.", "p0001"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                _unit("The tide keeps no promises.", "p0002", structural_role="epigraph"),
                _unit("- A. Writer", "p0003", structural_role="attribution"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                _unit("Contents", "p0004", structural_role="toc_header"),
                _unit("One ..... 3", "p0005", structural_role="toc_entry"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                _unit("[[DOCX_IMAGE_img_001]]", "p0006", role="image"),
                _unit("Figure 1. A chart of the tides.", "p0007", role="caption"),
                _unit("<table><tr><td>1</td></tr></table>", "p0008", role="table"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                _unit("The pilots argued about the chart until the lamps were lit and the water turned black.", "p0009"),
                _unit("(i)", "p0010"),
                _unit("11 vv", "p0011"),
            ]
        ),
        DocumentBlock(paragraphs=[_unit("Notes", "p0012", role="heading", level=2)]),
        DocumentBlock(paragraphs=[_unit("1. Harbour Ledger, 2010.", "p0013", role="list")]),
    ]


def _reasons_by_id(blocks: list[DocumentBlock]) -> dict[str, str | None]:
    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")
    return {
        paragraph_id: reason
        for job in jobs
        for paragraph_id, reason in zip(
            cast(list[str], job["paragraph_ids"]), cast(list[str | None], job["narration_exclusion_reasons"])
        )
    }


# --- T-D1: translate and edit are byte-identical (SC-004, Anti-regression 1) -----------------


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_translate_and_edit_jobs_are_byte_identical_to_the_snapshot_taken_before_wp_d(operation: str) -> None:
    snapshot = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    jobs = build_editing_jobs(_snapshot_blocks(), max_chars=3000, processing_operation=operation)

    assert json.loads(json.dumps(jobs, ensure_ascii=False)) == snapshot[operation]
    # The field exists for the audiobook only; a stray key would change the cache key of a job.
    assert all("narration_exclusion_reasons" not in job for job in jobs)


def test_the_audiobook_jobs_differ_from_edit_only_in_the_narration_fields() -> None:
    edit_jobs = build_editing_jobs(_snapshot_blocks(), max_chars=3000, processing_operation="edit")
    audiobook_jobs = build_editing_jobs(_snapshot_blocks(), max_chars=3000, processing_operation="audiobook")

    for edit_job, audiobook_job in zip(edit_jobs, audiobook_jobs):
        # The context fields too (fix-1, finding 6): the audiobook builds them from narrated
        # paragraphs only -- pinned by the context tests below.
        keys_that_may_differ = {
            "narration_exclusion_reasons",
            "narration_include",
            "job_kind",
            "context_before",
            "context_after",
            "context_chars",
        }
        assert {k: v for k, v in edit_job.items() if k not in keys_that_may_differ} == {
            k: v for k, v in audiobook_job.items() if k not in keys_that_may_differ
        }


# --- T-D2: a mixed block is decided per paragraph --------------------------------------------


def test_a_mixed_block_gets_one_reason_per_paragraph_and_the_prose_gets_none() -> None:
    blocks = [
        DocumentBlock(
            paragraphs=[
                _unit(_PROSE, "p0000"),
                _unit("One ..... 3", "p0001", structural_role="toc_entry"),
                _unit("<table><tr><td>1</td></tr></table>", "p0002", role="table"),
                _unit("Figure 1. A chart of the tides.", "p0003", role="caption"),
                _unit("[[DOCX_IMAGE_img_001]]", "p0004", role="image"),
                _unit(_PROSE, "p0005"),
            ]
        )
    ]

    (job,) = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert job["narration_exclusion_reasons"] == [None, "toc", "table", "caption", "image", None]
    # The block is still narrated -- it has prose -- and still goes to the model (as a subset).
    assert job["narration_include"] is True
    assert job["job_kind"] == "llm"


# --- fix-1, Codex acceptance finding 6: what is not narrated is not context either ------------

_TOC_LINE = "One ..... 3"
_TABLE = "<table><tr><td>17</td></tr></table>"
_CAPTION = "Figure 1. A chart of the tides."
_ENTRY = "1. Harbour Ledger, 2010."
_PROSE_BEFORE = "The pilots argued about the chart until the lamps were lit and the water turned black."
_PROSE_AFTER = "Morning came grey and quiet, and the boats went out again past the broken mole."


def _context_blocks() -> list[DocumentBlock]:
    return [
        DocumentBlock(paragraphs=[_unit(_PROSE_BEFORE, "p0000")]),
        # A mixed neighbour: a TOC line, a table and a caption beside narrated prose.
        DocumentBlock(
            paragraphs=[
                _unit(_TOC_LINE, "p0001", structural_role="toc_entry"),
                _unit(_TABLE, "p0002", role="table"),
                _unit(_CAPTION, "p0003", role="caption"),
            ]
        ),
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0004")]),
        # Recognised apparatus after the target, then the author's prose again.
        DocumentBlock(paragraphs=[_unit("Notes", "p0005", role="heading", level=1)]),
        DocumentBlock(paragraphs=[_unit(_ENTRY, "p0006", role="list")]),
        DocumentBlock(
            paragraphs=[_unit("Afterword", "p0007", role="heading", level=1), _unit(_PROSE_AFTER, "p0008")]
        ),
    ]


def test_the_audiobook_context_carries_only_narrated_paragraphs() -> None:
    jobs = build_editing_jobs(_context_blocks(), max_chars=3000, processing_operation="audiobook")
    target = jobs[2]

    # The premise: the neighbours really are excluded, and the target is narrated.
    assert jobs[1]["narration_exclusion_reasons"] == ["toc", "table", "caption"]
    assert jobs[3]["narration_exclusion_reasons"] == ["apparatus"]
    assert jobs[4]["narration_exclusion_reasons"] == ["apparatus"]
    assert target["narration_exclusion_reasons"] == [None]

    before = str(target["context_before"])
    after = str(target["context_after"])
    for excluded in (_TOC_LINE, _TABLE, _CAPTION, "<table>"):
        assert excluded not in before
    for excluded in ("Notes", _ENTRY):
        assert excluded not in after
    # Anti-vacuum: the context is not simply dropped -- the narrated neighbours are still in it,
    # past the excluded blocks in between.
    assert _PROSE_BEFORE in before
    assert "Afterword" in after and _PROSE_AFTER[:40] in after
    assert target["context_chars"] == len(before) + len(after)


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_translate_and_edit_context_still_carries_every_neighbour(operation: str) -> None:
    # Counter-proof of the scope: the same document under translate and edit keeps the old context.
    jobs = build_editing_jobs(_context_blocks(), max_chars=3000, processing_operation=operation)
    target = jobs[2]

    assert _TOC_LINE in str(target["context_before"])
    assert _CAPTION in str(target["context_before"])
    assert _ENTRY in str(target["context_after"])


def test_a_block_of_nothing_but_excluded_paragraphs_is_a_passthrough_without_a_call() -> None:
    blocks = [
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0000")]),
        DocumentBlock(
            paragraphs=[
                _unit("One ..... 3", "p0001", structural_role="toc_entry"),
                _unit("Figure 1. A chart of the tides.", "p0002", role="caption"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert jobs[1]["narration_exclusion_reasons"] == ["toc", "caption"]
    assert jobs[1]["narration_include"] is False
    assert jobs[1]["job_kind"] == "passthrough"
    assert jobs[0]["job_kind"] == "llm"


def test_the_back_matter_region_is_excluded_per_paragraph_as_index_or_apparatus() -> None:
    blocks = [
        DocumentBlock(paragraphs=[_unit("Closing thoughts", "p0000", role="heading", level=1), _unit(_PROSE, "p0001")]),
        DocumentBlock(paragraphs=[_unit("Notes", "p0002", role="heading", level=1)]),
        DocumentBlock(paragraphs=[_unit("1. Harbour Ledger, 2010.", "p0003", role="list")]),
        DocumentBlock(paragraphs=[_unit("Index", "p0004", role="heading", level=1)]),
        DocumentBlock(
            paragraphs=[
                _unit("Ballast, 19– 20, 46", "p0005"),
                _unit("Pilots, 3, 7", "p0006"),
            ]
        ),
    ]

    reasons = _reasons_by_id(blocks)

    assert reasons == {
        "p0000": None,  # the heading BEFORE the recognised apparatus is not part of it
        "p0001": None,
        "p0002": "apparatus",
        "p0003": "apparatus",
        "p0004": "index",
        "p0005": "index",
        "p0006": "index",
    }


def test_a_run_of_notes_left_in_the_body_is_excluded_as_notes_in_body_and_its_neighbours_are_not() -> None:
    blocks = [
        DocumentBlock(paragraphs=[_unit("Chapter One", "p0000", role="heading", level=1), _unit(_PROSE, "p0001")]),
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0002"), _unit(_NOTES_RUN, "p0003")]),
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0004")]),
    ]

    reasons = _reasons_by_id(blocks)

    assert reasons["p0003"] == "notes_in_body"
    assert [reasons[pid] for pid in ("p0000", "p0001", "p0002", "p0004")] == [None, None, None, None]


# --- fix-1, Codex acceptance finding 1: a contents line naming a reference section -----------


def _contents_line_then_prose() -> list[DocumentBlock]:
    """The FORM of the measured case: a contents list the import did not tag as one, whose last
    row names a reference section as a body line WITHOUT a heading level, followed by the
    author's front sections (headings WITH a level) and only later by the real section."""
    return [
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0000")]),
        DocumentBlock(
            paragraphs=[
                _unit("Appendices", "p0001", role="heading", level=3),
                _unit("**Acknowledgements**", "p0002"),
                _unit("**Our team**", "p0003"),
                _unit("**Bibliography**", "p0004"),
            ]
        ),
        DocumentBlock(paragraphs=[_unit("[[DOCX_IMAGE_img_001]]", "p0005", role="image")]),
        DocumentBlock(
            paragraphs=[_unit("Foreword", "p0006", role="heading", level=3), _unit(_PROSE, "p0007"), _unit(_PROSE, "p0008")]
        ),
        DocumentBlock(paragraphs=[_unit("Preface", "p0009", role="heading", level=2), _unit(_PROSE, "p0010")]),
        DocumentBlock(paragraphs=[_unit("Chapter One", "p0011", role="heading", level=1), _unit(_PROSE, "p0012")]),
        DocumentBlock(paragraphs=[_unit("Bibliography", "p0013", role="heading", level=2)]),
        DocumentBlock(paragraphs=[_unit("Harbour, A. *Tides*. London, 2004.", "p0014", role="list")]),
    ]


def test_prose_after_a_contents_line_naming_a_reference_section_is_narrated() -> None:
    reasons = _reasons_by_id(_contents_line_then_prose())

    # The prose before the contents line, the line itself and the front sections after it.
    assert [reasons[f"p{n:04d}"] for n in (0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12)] == [None] * 12
    assert reasons["p0005"] == "image"
    # Anti-vacuum: the real section, whose title carries a level, is still apparatus.
    assert reasons["p0013"] == "apparatus"
    assert reasons["p0014"] == "apparatus"


def test_a_contents_list_without_emphasis_markup_is_refused_the_same_way() -> None:
    # The guard reads the row in FRONT of the title (does it end a sentence?), not the bold
    # markup of the rows: plain rows and no picture in between give the same answer.
    blocks = [
        DocumentBlock(
            paragraphs=[_unit(_unwrapped(paragraph.text), str(paragraph.paragraph_id), role=paragraph.role, level=paragraph.heading_level) for paragraph in block.paragraphs]
        )
        for block in _contents_line_then_prose()
        if block.paragraphs[0].role != "image"
    ]

    reasons = _reasons_by_id(blocks)

    assert [reasons[f"p{n:04d}"] for n in (4, 6, 7, 8, 9, 10)] == [None] * 6
    assert reasons["p0014"] == "apparatus"


def _unwrapped(text: str) -> str:
    return text[2:-2] if text.startswith("**") and text.endswith("**") else text


def test_an_unlevelled_reference_title_still_excludes_the_entries_that_follow_it() -> None:
    # Counter-proof of the guard: the same title line WITHOUT a level, at the tail of a block,
    # but behind the chapter's last FINISHED sentence (the shape the tail case was built for) --
    # it still anchors, and its entries up to the next section are still apparatus.
    blocks = [
        DocumentBlock(
            paragraphs=[
                _unit("Closing thoughts", "p0000", role="heading", level=1),
                _unit(_PROSE, "p0001"),
                _unit("**Notes**", "p0002"),
            ]
        ),
        DocumentBlock(paragraphs=[_unit("1. Harbour Ledger, 2010.", "p0003", role="list")]),
        DocumentBlock(paragraphs=[_unit("2. Pilots' Almanac, 1999.", "p0004", role="list")]),
        DocumentBlock(paragraphs=[_unit("Acknowledgements", "p0005", role="heading", level=1), _unit(_PROSE, "p0006")]),
    ]

    reasons = _reasons_by_id(blocks)

    assert reasons["p0003"] == "apparatus"
    assert reasons["p0004"] == "apparatus"
    assert [reasons[pid] for pid in ("p0000", "p0001", "p0002", "p0005", "p0006")] == [None] * 5


def test_a_levelled_reference_title_still_runs_over_its_deeper_headings() -> None:
    # Counter-proof of the scope of the bound: only a title WITHOUT a level stops at the first
    # heading. A titled section with per-chapter labels one level deeper keeps all of them.
    blocks = [
        DocumentBlock(paragraphs=[_unit("Chapter One", "p0000", role="heading", level=1), _unit(_PROSE, "p0001")]),
        DocumentBlock(paragraphs=[_unit("Notes", "p0002", role="heading", level=1)]),
        DocumentBlock(paragraphs=[_unit("Chapter 1", "p0003", role="heading", level=2), _unit("1. Harbour Ledger, 2010.", "p0004", role="list")]),
        DocumentBlock(paragraphs=[_unit("Chapter 2", "p0005", role="heading", level=2), _unit("2. Pilots' Almanac, 1999.", "p0006", role="list")]),
        DocumentBlock(paragraphs=[_unit("Acknowledgements", "p0007", role="heading", level=1), _unit(_PROSE, "p0008")]),
    ]

    reasons = _reasons_by_id(blocks)

    assert [reasons[f"p000{n}"] for n in range(2, 7)] == ["apparatus"] * 5
    assert [reasons[pid] for pid in ("p0000", "p0001", "p0007", "p0008")] == [None] * 4


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_the_narration_bound_does_not_change_the_translate_and_edit_jobs(operation: str) -> None:
    # The bound is the audiobook's own (fix-1 scope): the shared back-matter fields of the jobs
    # -- the ones translate and edit read -- are the same for the audiobook and the operation.
    blocks = _contents_line_then_prose()
    shared = ("paragraph_regions", "back_matter_section")
    other = build_editing_jobs(blocks, max_chars=3000, processing_operation=operation)
    audiobook = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [[job[key] for key in shared] for job in audiobook] == [[job[key] for key in shared] for job in other]


def test_every_reason_the_document_layer_produces_is_in_the_closed_vocabulary() -> None:
    reasons = _reasons_by_id(_snapshot_blocks())

    produced = {reason for reason in reasons.values() if reason is not None}
    assert produced
    assert produced <= NARRATION_EXCLUSION_REASONS


# --- T-D3: anti-vacuum -- what must NOT be excluded ------------------------------------------


def test_headings_epigraphs_attributions_and_dedications_are_narrated_even_when_they_look_like_fragments() -> None:
    blocks = [
        DocumentBlock(
            paragraphs=[
                _unit("II", "p0000", role="heading", level=1),
                _unit("1", "p0001", role="heading", level=2),
                _unit("— Ю. Ли", "p0002", structural_role="attribution"),
                _unit("Tide.", "p0003", structural_role="epigraph"),
                _unit("To M.", "p0004", structural_role="dedication"),
                _unit(_PROSE, "p0005"),
            ]
        )
    ]

    reasons = _reasons_by_id(blocks)

    assert [reasons[f"p000{n}"] for n in range(6)] == [None] * 6


def test_the_role_is_what_exempts_the_same_text_with_a_body_role_is_a_fragment() -> None:
    # Counter-proof of the exemption: take the role away and the same text is excluded. If the
    # exemption were vacuous (the fragment rule never firing), the test above would pass either way.
    blocks = [
        DocumentBlock(
            paragraphs=[
                _unit("II", "p0000"),
                _unit("— Ю. Ли", "p0001"),
                _unit(_PROSE, "p0002"),
            ]
        )
    ]

    reasons = _reasons_by_id(blocks)

    assert reasons["p0000"] == "fragment"
    assert reasons["p0001"] == "fragment"
    assert reasons["p0002"] is None


def test_the_basic_heading_role_exempts_even_when_the_structural_role_is_still_body() -> None:
    # ``ParagraphUnit.structural_role`` defaults to "body" and is copied from ``role`` only when
    # extraction assigns the identity; a unit built without that step is still a heading.
    heading = ParagraphUnit(text="II", role="heading", paragraph_id="p0000", heading_level=1)

    assert heading.structural_role == "body"
    reasons = _reasons_by_id([DocumentBlock(paragraphs=[heading, _unit(_PROSE, "p0001")])])
    assert reasons["p0000"] is None


def test_short_prose_front_matter_and_a_heading_before_apparatus_are_narrated() -> None:
    blocks = [
        # The front matter: everything before the first run of long prose (the boundary detector
        # of the document layer). None of it is excluded by REGION.
        DocumentBlock(
            paragraphs=[
                _unit("The tide keeps no promises.", "p0000", structural_role="epigraph"),
                _unit("- A. Writer", "p0001", structural_role="attribution"),
                _unit("It began on a Tuesday.", "p0002"),
                _unit("(i)", "p0003"),
            ]
        ),
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0004"), _unit(_PROSE, "p0005"), _unit(_PROSE, "p0006")]),
        # A heading with the recognised apparatus after it in the same block.
        DocumentBlock(
            paragraphs=[
                _unit("Closing thoughts", "p0007", role="heading", level=1),
                _unit("One ..... 3", "p0008", structural_role="toc_entry"),
            ]
        ),
    ]
    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")
    regions = {
        paragraph_id: region
        for job in jobs
        for paragraph_id, region in zip(cast(list[str], job["paragraph_ids"]), cast(list[str], job["paragraph_regions"]))
    }
    reasons = _reasons_by_id(blocks)

    assert [regions[f"p000{n}"] for n in range(4)] == ["front_matter"] * 4  # the premise of the test
    assert reasons["p0000"] is None
    assert reasons["p0001"] is None
    assert reasons["p0002"] is None  # short prose of one sentence
    assert reasons["p0003"] == "fragment"  # a fragment is excluded wherever it is
    assert reasons["p0007"] is None
    assert reasons["p0008"] == "toc"


# --- the form rule ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["(i)", "11 vv", "— 42 —", "* * *", "42", "", "   ", "ab", "а б в г"])
def test_fragments_have_no_connected_text(text: str) -> None:
    assert is_fragment_without_connected_text(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Он ушёл.",
        "abc",  # a run of exactly three letters is not a fragment
        "abc 123",  # letters are exactly half of the non-space characters: not a fragment
        "ab 12 abc",  # a three-letter token elsewhere in the text
        "école",  # a combining accent belongs to its letter, it is not a non-letter
        "Chapter 7",
        _PROSE,
    ],
)
def test_text_with_a_connected_run_of_letters_is_not_a_fragment(text: str) -> None:
    assert is_fragment_without_connected_text(text) is False


def test_the_letter_share_boundary_is_exact() -> None:
    assert is_fragment_without_connected_text("abc 123") is False  # 3 of 6
    assert is_fragment_without_connected_text("abc 1234") is True  # 3 of 7, fewer than half
    assert is_fragment_without_connected_text("Hello, 1234567") is True  # a real word, but mostly digits


# --- fix-1, Codex acceptance finding 2: a short sentence is speech, not a fragment ------------


@pytest.mark.parametrize(
    "text",
    [
        "Да.",  # no run of three letters
        "Я и ты.",  # no run of three letters
        "Go!",  # no run of three letters
        "你好。",  # ideographic full stop, two letters
        "От 10 до 20.",  # letters fewer than half of the non-space characters
        "Ну?",
        "Ah…",  # an ellipsis ends a sentence too
        "«Да.»",  # closing quote after the terminal
        "(Go!)",  # closing bracket after the terminal
        "*Да.*",  # the importer's emphasis markup after the terminal
        "So 1, 2, 3.",
    ],
)
def test_a_short_sentence_with_a_letter_and_a_terminal_mark_is_connected_text(text: str) -> None:
    assert is_fragment_without_connected_text(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "(i)",
        "( i)",
        "11 vv",
        "ri1*",
        "O",
        "30",
        "1",
        "1.",  # a terminal mark without a single letter is still a fragment
        "— 42 —",
        "Да",  # the same letters as above without the terminal mark
        "Go",
        "От 10 до 20",
        "¿Si",  # an INVERTED mark opens a sentence; it does not end one
    ],
)
def test_without_a_letter_or_without_a_terminal_mark_the_form_rule_still_holds(text: str) -> None:
    assert is_fragment_without_connected_text(text) is True


def test_a_short_reply_in_a_body_paragraph_is_narrated_through_the_document_layer() -> None:
    blocks = [
        DocumentBlock(
            paragraphs=[
                _unit(_PROSE, "p0000"),
                _unit("Да.", "p0001"),
                _unit("Go!", "p0002"),
                _unit("От 10 до 20.", "p0003"),
                _unit("(i)", "p0004"),
            ]
        )
    ]

    reasons = _reasons_by_id(blocks)

    assert [reasons[f"p000{n}"] for n in range(5)] == [None, None, None, None, "fragment"]


def test_an_empty_paragraph_is_excluded_under_any_role_so_a_request_never_carries_one() -> None:
    blocks = [DocumentBlock(paragraphs=[_unit("[[DOCX_IMAGE_img_007]]", "p0000", role="heading", level=1), _unit(_PROSE, "p0001")])]

    reasons = _reasons_by_id(blocks)

    assert reasons["p0000"] == "fragment"
    assert reasons["p0001"] is None


def test_a_separator_styled_as_a_heading_has_nothing_to_narrate_but_a_number_or_numeral_does() -> None:
    # FR-009 run 2026-11-10: a scene separator the import styled as a heading reached the
    # ``.tts.txt`` -- the model answered it empty, the empty-answer rule narrated it from
    # source. No letter and no digit under any role is nothing to say; a heading of a single
    # digit or a Roman numeral still is something (the exemption above stays).
    blocks = [
        DocumentBlock(
            paragraphs=[
                _unit("* * *", "p0000", role="heading", level=2),
                _unit("1", "p0001", role="heading", level=2),
                _unit("IV", "p0002", role="heading", level=2),
                _unit("~ ~", "p0003", structural_role="epigraph"),
                _unit(_PROSE, "p0004"),
            ]
        )
    ]

    reasons = _reasons_by_id(blocks)

    assert [reasons[f"p000{n}"] for n in range(5)] == ["fragment", None, None, "fragment", None]


def test_priority_is_image_table_caption_toc_index_apparatus_notes_fragment() -> None:
    kwargs = {"back_matter_section": None, "in_notes_in_body": False, "text": "(i)"}

    assert resolve_narration_exclusion_reason(structural_role="image", region="prose", **kwargs) == "image"
    assert resolve_narration_exclusion_reason(structural_role="table", region="back_matter", **kwargs) == "table"
    assert resolve_narration_exclusion_reason(structural_role="caption", region="toc", **kwargs) == "caption"
    assert resolve_narration_exclusion_reason(structural_role="toc_entry", region="back_matter", **kwargs) == "toc"
    assert (
        resolve_narration_exclusion_reason(
            structural_role="body", region="back_matter", back_matter_section="index", in_notes_in_body=True, text="(i)"
        )
        == "index"
    )
    assert (
        resolve_narration_exclusion_reason(
            structural_role="body", region="back_matter", back_matter_section="notes", in_notes_in_body=True, text="(i)"
        )
        == "apparatus"
    )
    assert (
        resolve_narration_exclusion_reason(
            structural_role="body", region="prose", back_matter_section=None, in_notes_in_body=True, text="(i)"
        )
        == "notes_in_body"
    )
    assert resolve_narration_exclusion_reason(structural_role="body", region="prose", **kwargs) == "fragment"
    assert (
        resolve_narration_exclusion_reason(
            structural_role="body", region="front_matter", back_matter_section=None, in_notes_in_body=False, text=_PROSE
        )
        is None
    )


# --- T-D4: the payload carries the reasons through a validated boundary ----------------------


def _job_dict(**overrides: object) -> dict[str, object]:
    job: dict[str, object] = {
        "job_kind": "llm",
        "target_chars": 10,
        "context_chars": 0,
        "target_text": "abc def",
        "target_text_with_markers": "[[DOCX_PARA_p1]]\nabc\n\n[[DOCX_PARA_p2]]\n(i)",
        "paragraph_ids": ["p1", "p2"],
        "context_before": "",
        "context_after": "",
    }
    job.update(overrides)
    return job


def test_the_payload_carries_the_reasons_parallel_to_the_paragraph_ids() -> None:
    payload = parse_processing_job(
        job=_job_dict(narration_exclusion_reasons=[None, "fragment"]), payload_factory=BlockExecutionPayload
    )

    assert payload.narration_exclusion_reasons == [None, "fragment"]


def test_a_missing_field_means_nothing_is_excluded() -> None:
    payload = parse_processing_job(job=_job_dict(), payload_factory=BlockExecutionPayload)

    assert payload.narration_exclusion_reasons is None


@pytest.mark.parametrize(
    "reasons",
    [[None], [None, None, None], ["fragment", "fragmentary"], ["Fragment", None], [""]],
    ids=["too-short", "too-long", "unknown-reason", "case-matters", "empty-string"],
)
def test_a_wrong_length_or_an_unknown_reason_is_an_error_not_a_silent_exclusion(reasons: list[str | None]) -> None:
    with pytest.raises(ValueError):
        parse_processing_job(job=_job_dict(narration_exclusion_reasons=reasons), payload_factory=BlockExecutionPayload)


def test_a_non_list_or_a_non_string_entry_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        coerce_narration_exclusion_reasons({"narration_exclusion_reasons": "toc"}, paragraph_ids=["p1"])
    with pytest.raises(TypeError):
        coerce_narration_exclusion_reasons({"narration_exclusion_reasons": [3]}, paragraph_ids=["p1"])


def test_the_reasons_the_document_layer_emits_survive_the_parse_of_the_real_jobs() -> None:
    for job in build_editing_jobs(_snapshot_blocks(), max_chars=3000, processing_operation="audiobook"):
        payload = parse_processing_job(job=job, payload_factory=BlockExecutionPayload)
        assert payload.narration_exclusion_reasons == job["narration_exclusion_reasons"]


# --- T-D5: the audiobook is always addressed by marker (R12 / O-3) ---------------------------


def _context(operation: str, *, markers: bool) -> SimpleNamespace:
    return SimpleNamespace(processing_operation=operation, app_config={"enable_paragraph_markers": markers})


_PAYLOAD_WITH_IDS = SimpleNamespace(paragraph_ids=["p1", "p2"])
_PAYLOAD_WITHOUT_IDS = SimpleNamespace(paragraph_ids=None)


def test_audiobook_uses_markers_even_when_the_config_key_is_off() -> None:
    assert is_marker_mode_enabled(_context("audiobook", markers=False), _PAYLOAD_WITH_IDS) is True
    assert is_marker_mode_enabled(_context("audiobook", markers=True), _PAYLOAD_WITH_IDS) is True
    # No ids, no markers: there is nothing to address.
    assert is_marker_mode_enabled(_context("audiobook", markers=False), _PAYLOAD_WITHOUT_IDS) is False


@pytest.mark.parametrize("operation", ["edit", "translate"])
def test_translate_and_edit_keep_following_the_config_key(operation: str) -> None:
    assert is_marker_mode_enabled(_context(operation, markers=False), _PAYLOAD_WITH_IDS) is False
    assert is_marker_mode_enabled(_context(operation, markers=True), _PAYLOAD_WITH_IDS) is True
    assert is_marker_mode_enabled(_context(operation, markers=True), _PAYLOAD_WITHOUT_IDS) is False
