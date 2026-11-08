"""Spec 067 P1 -- the apparatus the import left in the body, and a name kept as a name.

FR-001 (A-1): a run of notes the PDF import delivered as ordinary body paragraphs of the prose
region is recognised by its FORM on the document layer and gets the apparatus treatment of a
block: the block prompt names it under «СПРАВОЧНЫЙ АППАРАТ БЛОКА», and a paragraph the model
kept unchanged whose every entry is a reference is relabelled ``policy_kept_source`` (spec 064
FR-006), which the gate does not count. Measured on the fourth translate run (2026-11-08): Money
62 document-layer paragraphs (the 59 delivered records of A-1), Creating Wealth 1, The Value of
Everything 0, Rethinking Money 0 -- its one form match is a line of the table of contents the
role detector left in the prose region, excluded by the roles around it.

Every rule here has its counter-rule on the same input shape without the signal.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

import docxaicorrector.pipeline.block_execution as block_execution
from docxaicorrector.core.models import (
    BACK_MATTER_SECTION_NOTES,
    PARAGRAPH_STATUS_POLICY_KEPT_SOURCE,
    DocumentBlock,
    ParagraphUnit,
)
from docxaicorrector.document import semantic_blocks
from docxaicorrector.generation._generation import (
    PARAGRAPH_STATUS_ACCEPTED,
    MarkerPreservedBlockText,
    ParagraphDisposition,
)
from docxaicorrector.pipeline import output_validation
from docxaicorrector.pipeline.contracts import BlockExecutionPayload
from docxaicorrector.pipeline.job_parsing import parse_processing_job
from tests.test_spec_063_apparatus_policy import _run  # the 063 block harness (process_single_block)

_TRANSLATE = SimpleNamespace(processing_operation="translate")

# A run of notes as a PDF text layer delivers it: numbers without a full stop, entries run on.
_NOTES_CITATIONS = (
    "1 R. Hall, *The Tides of Cities* (London: Harbour Press, 2004), p. 85. "
    "2 J. Smith and K. Lee, ‘Money and Debt’, *Journal of Economic Studies* 12(3), 1999, pp. 4-19."
)
_NOTES_WITH_COMMENTARY = (
    "3 The argument that money is neutral was never accepted by the classical writers, who saw "
    "it shaping every exchange and every debt in the economy they described. "
    "4 R. Brown, *Credit and Trust* (Oxford: Clarendon, 2001), p. 12."
)
_LABELLED_SINGLE_NOTE = "Footnotes 1 *The Tides of Cities* (London: Harbour Press, 2004), p. 85."
_TORN_TAIL_AND_NOTE = (
    "*Studies in Exchange* (2008). 26 M. Ortega, *The Second Ledger* (Madrid: Prensa, 2011), p. 40."
)
_PROSE = (
    "A harbour is not a place but an arrangement among its pilots to treat one stretch of water "
    "as a shelter from the storm, and that arrangement is what this chapter is about."
)


# --- the form ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(_NOTES_CITATIONS, id="chain-of-references"),
        pytest.param(_NOTES_WITH_COMMENTARY, id="chain-half-references-half-commentary"),
        pytest.param(_LABELLED_SINGLE_NOTE, id="single-note-after-a-label"),
        pytest.param(_TORN_TAIL_AND_NOTE, id="single-note-after-a-torn-note-tail"),
    ],
)
def test_a_notes_run_is_recognised_by_its_form(text: str) -> None:
    assert output_validation.is_notes_run_paragraph(text) is True


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("1. Collect the receipts (2010). 2. Sort them by date, as in 1999.", id="numbered-list-with-full-stops"),
        pytest.param("Chapter 2 The Market and Chapter 3 The State are discussed below.", id="running-text-without-references"),
        pytest.param("6 Methods for Sailing *95*", id="toc-line-a-single-number-without-label"),
        pytest.param("It took 3 years and 4 months to repay the loan of 1998.", id="lowercase-after-the-numbers"),
        pytest.param(_PROSE, id="prose"),
    ],
)
def test_counter_rule_what_is_not_a_notes_run(text: str) -> None:
    assert output_validation.is_notes_run_paragraph(text) is False


def test_only_a_run_whose_every_part_is_a_reference_reads_as_citations() -> None:
    assert output_validation.notes_run_reads_as_citations(_NOTES_CITATIONS) is True
    assert output_validation.notes_run_reads_as_citations(_TORN_TAIL_AND_NOTE) is True
    # Anti-vacuum: one entry of commentary, or a label (a title of the apparatus, translated
    # under D1), keeps the paragraph out of the credit.
    assert output_validation.notes_run_reads_as_citations(_NOTES_WITH_COMMENTARY) is False
    assert output_validation.notes_run_reads_as_citations(_LABELLED_SINGLE_NOTE) is False
    assert output_validation.notes_run_reads_as_citations(_PROSE) is False


# --- the document layer ----------------------------------------------------------------------


def _unit(text: str, pid: str, *, role: str = "body", level: int | None = None, structural_role: str | None = None) -> ParagraphUnit:
    return ParagraphUnit(
        text=text, role=role, paragraph_id=pid, heading_level=level, structural_role=structural_role or role
    )


def _book() -> list[DocumentBlock]:
    return [
        DocumentBlock(
            paragraphs=[
                _unit("CONTENTS", "p0000", role="heading", level=1, structural_role="toc_header"),
                _unit("1 The First Chapter *11*", "p0001", structural_role="toc_entry"),
            ]
        ),
        # A stretch of contents lines the role detector left untyped, between two TOC lines.
        DocumentBlock(paragraphs=[_unit("2 The Second Chapter: *Ports and Tides* 23 3 The Third Chapter: *Debt* (2004) 37", "p0002")]),
        DocumentBlock(paragraphs=[_unit("4 The Fourth Chapter *51*", "p0003", structural_role="toc_entry")]),
        DocumentBlock(paragraphs=[_unit("Chapter One", "p0004", role="heading", level=1), _unit(_PROSE, "p0005")]),
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0006"), _unit(_NOTES_CITATIONS, "p0007")]),
        DocumentBlock(paragraphs=[_unit(_NOTES_WITH_COMMENTARY, "p0008", role="list"), _unit(_PROSE, "p0009")]),
        # The same form as a heading or a caption is never a notes run.
        DocumentBlock(paragraphs=[_unit(_NOTES_CITATIONS, "p0010", role="caption")]),
        DocumentBlock(paragraphs=[_unit("Notes", "p0011", role="heading", level=1), _unit(_NOTES_CITATIONS, "p0012")]),
    ]


def test_editing_jobs_mark_the_notes_runs_of_the_prose_region() -> None:
    jobs = semantic_blocks.build_editing_jobs(_book(), max_chars=3000, processing_operation="translate")
    marked = {pid for job in jobs for pid in cast(list[str], job["notes_in_body_paragraph_ids"])}

    assert marked == {"p0007", "p0008"}
    # The mark is beside the region, never a relabelling of it.
    regions = {
        pid: region
        for job in jobs
        for pid, region in zip(cast(list[str], job["paragraph_ids"]), cast(list[str], job["paragraph_regions"]))
    }
    assert regions["p0007"] == regions["p0008"] == "prose"
    # Counter-rules: the untyped contents stretch, a caption, and notes already in the
    # back-matter region (which carry their own section policy) are not marked.
    assert "p0002" not in marked
    assert regions["p0012"] == "back_matter" and "p0012" not in marked


def test_the_toc_bracket_needs_contents_on_both_sides_and_no_heading_between() -> None:
    paragraphs = [
        _unit("1 The First Chapter *11*", "a", structural_role="toc_entry"),
        _unit(_NOTES_CITATIONS, "b"),
        _unit("Chapter One", "c", role="heading", level=1),
        _unit(_NOTES_CITATIONS, "d"),
        _unit("2 The Second Chapter *23*", "e", structural_role="toc_entry"),
        _unit(_NOTES_CITATIONS, "f"),
    ]
    # b..d hold a heading, so they are a chapter, not a contents gap; f has no TOC after it.
    assert semantic_blocks._toc_bracketed_positions(paragraphs, structure_phase="post_ai_final") == frozenset()
    assert semantic_blocks._resolve_notes_in_body_positions(paragraphs, ["prose"] * len(paragraphs)) == frozenset({1, 3, 5})

    # The rule itself: untyped lines between two contents lines, no heading among them.
    gap = [
        _unit("1 The First Chapter *11*", "a", structural_role="toc_entry"),
        _unit("2 The Second Chapter: *Ports and Tides* 23 3 The Third Chapter: *Debt* (2004) 37", "b"),
        _unit("Yet! *41*", "c"),
        _unit("CONTENTS", "d", role="heading", level=3, structural_role="toc_header"),
        _unit(_NOTES_CITATIONS, "e"),
    ]
    assert output_validation.is_notes_run_paragraph(gap[1].text) is True
    assert semantic_blocks._toc_bracketed_positions(gap, structure_phase="post_ai_final") == frozenset({1, 2})
    assert semantic_blocks._resolve_notes_in_body_positions(gap, ["prose"] * len(gap)) == frozenset({4})


def test_the_mark_reaches_the_payload_and_a_foreign_id_is_refused() -> None:
    job = {
        "job_kind": "llm",
        "target_text": "x\n\ny",
        "context_before": "",
        "context_after": "",
        "target_chars": 4,
        "context_chars": 0,
        "paragraph_ids": ["p0001", "p0002"],
        "paragraph_regions": ["prose", "prose"],
        "notes_in_body_paragraph_ids": ["p0002"],
    }
    assert parse_processing_job(job=job, payload_factory=BlockExecutionPayload).notes_in_body_paragraph_ids == ["p0002"]
    without = {key: value for key, value in job.items() if key != "notes_in_body_paragraph_ids"}
    assert parse_processing_job(job=without, payload_factory=BlockExecutionPayload).notes_in_body_paragraph_ids is None
    with pytest.raises(ValueError, match="outside the block"):
        parse_processing_job(job={**job, "notes_in_body_paragraph_ids": ["p0009"]}, payload_factory=BlockExecutionPayload)


# --- the block: prompt and disposition --------------------------------------------------------


def _payload(texts: list[str], *, notes: list[int], regions: list[str] | None = None) -> SimpleNamespace:
    paragraph_ids = [f"p{index:04d}" for index in range(len(texts))]
    return SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text="\n\n".join(texts),
        target_text_with_markers="\n\n".join(f"[[DOCX_PARA_{pid}]]\n{text}" for pid, text in zip(paragraph_ids, texts)),
        paragraph_ids=paragraph_ids,
        structural_roles=["body"] * len(texts),
        paragraph_regions=regions or ["prose"] * len(texts),
        back_matter_section=None,
        notes_in_body_paragraph_ids=[paragraph_ids[index] for index in notes],
        narration_include=True,
    )


def _answer(payload: SimpleNamespace, texts: list[str] | None = None) -> MarkerPreservedBlockText:
    delivered = texts or payload.target_text.split("\n\n")
    return MarkerPreservedBlockText(
        "\n\n".join(delivered),
        tuple(
            ParagraphDisposition(pid, text, PARAGRAPH_STATUS_ACCEPTED) for pid, text in zip(payload.paragraph_ids, delivered)
        ),
    )


def _statuses(chunk: str) -> list[str]:
    return [disposition.status for disposition in block_execution.marker_paragraph_dispositions(chunk) or ()]


def test_a_body_block_names_its_notes_run_in_the_apparatus_section() -> None:
    payload = _payload([_PROSE, _NOTES_CITATIONS], notes=[1])

    section = block_execution._build_block_apparatus_prompt(context=_TRANSLATE, payload=payload, marker_mode_enabled=True)

    assert section.startswith(block_execution._APPARATUS_PROMPT_HEADER)
    assert "- Раздел: примечания" in section
    assert "- Абзацы: [[DOCX_PARA_p0001]]" in section
    assert "[[DOCX_PARA_p0000]]" not in section


def test_counter_rule_no_section_without_the_mark_or_outside_translation() -> None:
    unmarked = _payload([_PROSE, _NOTES_CITATIONS], notes=[])
    assert block_execution._build_block_apparatus_prompt(context=_TRANSLATE, payload=unmarked, marker_mode_enabled=True) == ""
    marked = _payload([_PROSE, _NOTES_CITATIONS], notes=[1])
    edit = SimpleNamespace(processing_operation="edit")
    assert block_execution._build_block_apparatus_prompt(context=edit, payload=marked, marker_mode_enabled=True) == ""


def test_an_unchanged_notes_run_of_references_is_policy_kept_beside_translated_prose() -> None:
    payload = _payload([_PROSE, _NOTES_CITATIONS], notes=[1])
    answer = _answer(payload, ["Гавань — не место, а договорённость между лоцманами.", _NOTES_CITATIONS])

    kept = block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=answer)

    assert kept is not None
    assert kept.whole_block is False
    assert kept.notes_in_body_paragraph_count == 1
    assert _statuses(kept.processed_chunk) == [PARAGRAPH_STATUS_ACCEPTED, PARAGRAPH_STATUS_POLICY_KEPT_SOURCE]
    assert kept.processed_chunk == answer  # the text is the model's, to the character


def test_anti_vacuum_an_unchanged_notes_run_with_commentary_is_not_credited() -> None:
    payload = _payload([_NOTES_WITH_COMMENTARY], notes=[0])
    assert block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=_answer(payload)) is None


def test_counter_rule_the_same_paragraph_without_the_mark_or_outside_prose_is_not_relabelled() -> None:
    unmarked = _payload([_NOTES_CITATIONS], notes=[])
    assert block_execution.model_kept_apparatus(context=_TRANSLATE, payload=unmarked, processed_chunk=_answer(unmarked)) is None
    front = _payload([_NOTES_CITATIONS], notes=[0], regions=["front_matter"])
    assert block_execution.model_kept_apparatus(context=_TRANSLATE, payload=front, processed_chunk=_answer(front)) is None


def test_without_a_per_paragraph_record_a_body_block_is_never_relabelled() -> None:
    payload = _payload([_NOTES_CITATIONS], notes=[0])
    payload.narration_include = False
    assert block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=payload.target_text) is None


def test_a_whole_block_of_kept_references_is_no_longer_a_source_fallback() -> None:
    payload = _payload([_NOTES_CITATIONS, _TORN_TAIL_AND_NOTE], notes=[0, 1])

    kept = block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=_answer(payload))

    assert kept is not None and kept.whole_block is True
    assert _statuses(kept.processed_chunk) == [PARAGRAPH_STATUS_POLICY_KEPT_SOURCE] * 2


def test_the_back_matter_branch_is_unchanged_by_the_body_mark() -> None:
    """Non-goal: the 064 FR-006 dispositions of the back-matter region do not move. A notes
    section block reads its paragraphs with the per-paragraph citation test, as before."""
    payload = _payload([_NOTES_CITATIONS], notes=[], regions=["back_matter"])
    payload.back_matter_section = BACK_MATTER_SECTION_NOTES
    kept = block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=_answer(payload))
    expected = output_validation.is_citation_form_paragraph(_NOTES_CITATIONS)
    assert (kept is not None) is expected


# =============================================================================================
# FR-004 (A-4) -- a heading that is a bare name, returned unchanged, is the name, not a loss
# =============================================================================================
#
# Creating Wealth, fourth run, block 434: a heading that is a publisher's name came back as it was, the
# pair rule read ``source_text_fallback`` and the acceptance check ``untranslated_prose_not_delivered``
# failed the book on 26 characters. The document layer now marks such a heading by role and form
# (shape + the document's own case count + the phrase written mid-sentence in running text), and
# the block keeps it as ``policy_kept_source`` with the reason ``name_kept``. Measured on the
# fourth run: 1 / 0 / 1 / 5 marked headings (Money / VoE / RM / CW), all names, no chapter title;
# replay: CW block 434 -> valid, acceptance passes; nothing else changes.

_NAME_BODY = (
    "The book was printed by Harbour Lane Press in a small run, and the press itself kept a lane "
    "of its own for such work; see Chapter II for the history of the chapter and its five parts."
)
_INTRODUCTION_BODY = "This introduction explains the market, and the introduction is short."


def _name_book() -> list[ParagraphUnit]:
    return [
        _unit("Chapter II", "h0", role="heading", level=1),
        _unit(_NAME_BODY, "b0"),
        _unit(_INTRODUCTION_BODY, "b1"),
        _unit("Harbour Lane Press", "h1", role="heading", level=3),
        _unit("Introduction", "h2", role="heading", level=2),
        _unit("Benefits of the Fenwick System", "h3", role="heading", level=3),
        _unit("Harbour Lane Press", "b2"),  # the same text as BODY is never a name heading
    ]


def test_a_heading_that_is_a_name_by_the_documents_own_count_is_marked() -> None:
    book = _name_book()
    positions = semantic_blocks._resolve_name_heading_positions(book, ["prose"] * len(book))
    assert positions == frozenset({3})


@pytest.mark.parametrize(
    ("heading", "why"),
    [
        ("Introduction", "the word occurs lowercase in the body"),
        ("Chapter II", "a roman numeral is not a name signal and the word chapter occurs lowercase"),
        ("Benefits of the Fenwick System", "the phrase never occurs in running text"),
        ("Harbour Lane Press.", "sentence punctuation"),
        ("A Short History of the Harbour Lane Press Company Today", "more than six words"),
    ],
)
def test_counter_rule_ordinary_headings_are_not_names(heading: str, why: str) -> None:
    book = [_unit(_NAME_BODY, "b0"), _unit(_INTRODUCTION_BODY, "b1"), _unit(heading, "h", role="heading", level=2)]
    assert semantic_blocks._resolve_name_heading_positions(book, ["prose"] * len(book)) == frozenset(), why


def test_a_name_heading_outside_the_prose_region_is_not_marked() -> None:
    book = _name_book()
    regions = ["prose"] * len(book)
    regions[3] = "front_matter"
    assert semantic_blocks._resolve_name_heading_positions(book, regions) == frozenset()


def test_editing_jobs_carry_the_name_mark_and_parsing_checks_it() -> None:
    blocks = [DocumentBlock(paragraphs=[paragraph]) for paragraph in _name_book()]
    jobs = semantic_blocks.build_editing_jobs(blocks, max_chars=3000, processing_operation="translate")
    marked = {pid for job in jobs for pid in cast(list[str], job["name_heading_paragraph_ids"])}
    assert marked == {"h1"}
    job = next(job for job in jobs if job["paragraph_ids"] == ["h1"])
    payload = parse_processing_job(job=job, payload_factory=BlockExecutionPayload)
    assert payload.name_heading_paragraph_ids == ["h1"]
    with pytest.raises(ValueError, match="outside the block"):
        parse_processing_job(job={**job, "name_heading_paragraph_ids": ["h9"]}, payload_factory=BlockExecutionPayload)


def _name_payload(texts: list[str], *, roles: list[str], names: list[int]) -> SimpleNamespace:
    payload = _payload(texts, notes=[])
    payload.structural_roles = roles
    payload.name_heading_paragraph_ids = [payload.paragraph_ids[index] for index in names]
    payload.target_chars = len(payload.target_text)
    payload.context_chars = 0
    payload.context_before = ""
    payload.context_after = ""
    return payload


def test_a_name_heading_is_not_prose_and_its_echo_is_not_announced() -> None:
    payload = _name_payload(["### Harbour Lane Press"], roles=["heading"], names=[0])
    assert block_execution.prose_paragraph_indexes(payload) == ()
    assert block_execution.payload_contains_prose(payload) is False
    assert (
        block_execution.untranslated_prose_would_be_delivered(
            payload=payload, fallback_markdown=payload.target_text, languages_differ=True
        )
        is False
    )


def test_counter_rule_an_unmarked_heading_or_a_marked_body_paragraph_stays_prose() -> None:
    unmarked = _name_payload(["### Introduction"], roles=["heading"], names=[])
    assert block_execution.prose_paragraph_indexes(unmarked) == (0,)
    # The mark is read together with the role: a body paragraph is never a name heading.
    body = _name_payload(["Harbour Lane Press"], roles=["body"], names=[0])
    assert block_execution.prose_paragraph_indexes(body) == (0,)
    assert (
        block_execution.untranslated_prose_would_be_delivered(
            payload=unmarked, fallback_markdown=unmarked.target_text, languages_differ=True
        )
        is True
    )


def test_an_unchanged_name_heading_block_is_policy_kept_with_the_reason_name_kept(monkeypatch) -> None:
    written: list[object] = []
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **kwargs: written.append(kwargs))
    payload = _name_payload(["### Harbour Lane Press"], roles=["heading"], names=[0])

    run = _run(payload, model_answer=_answer(payload), classification="source_text_fallback")

    assert run.outcome is None
    assert written == []
    assert [entry["paragraph_status"] for entry in run.state.generated_paragraph_registry] == [
        PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
    ]
    events = dict(run.events)
    assert "block_controlled_fallback" not in events
    assert "block_apparatus_kept_by_model" not in events
    assert events["block_name_kept_by_model"]["reason"] == block_execution.POLICY_KEPT_REASON_NAME_KEPT == "name_kept"
    assert run.snapshot["controlled_block_fallback_block_count"] == 0
    assert run.snapshot["untranslated_prose_block_delivery_count"] == 0


def test_counter_rule_a_translated_or_unmarked_heading_is_not_relabelled() -> None:
    payload = _name_payload(["### Harbour Lane Press"], roles=["heading"], names=[0])
    translated = _answer(payload, ["### Издательство Harbour Lane Press"])
    assert block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=translated) is None
    unmarked = _name_payload(["### Introduction"], roles=["heading"], names=[])
    assert block_execution.model_kept_apparatus(context=_TRANSLATE, payload=unmarked, processed_chunk=_answer(unmarked)) is None


def test_a_name_heading_followed_by_its_section_is_left_accepted() -> None:
    """The torn-run rule holds for a name as for a reference: a heading never ends a sentence,
    so with a paragraph after it in the block it is relabelled only together with that one --
    and a translated paragraph is not kept. The heading stays ``accepted``; it is still not prose."""
    payload = _name_payload(["### Harbour Lane Press", _PROSE], roles=["heading", "body"], names=[0])
    answer = _answer(payload, ["### Harbour Lane Press", "Гавань — не место, а договорённость."])
    assert block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=answer) is None
    assert block_execution.prose_paragraph_indexes(payload) == (1,)


# --- FR-001: the wording of rule 12's sub-bullets ---------------------------------------------


def test_rule_12_keeps_as_is_only_inside_a_citation_and_says_commentary_is_translated_beside_it() -> None:
    """Spec 067 FR-001 (A-1): the FR-011 sub-bullets of spec 065 said "leave as is" without
    saying WHERE, and on the fourth run 27 notes-run paragraphs of Money came back English whole.
    The link is a hypothesis measured by FR-012, not a fact; the wording is fixed either way:
    "as is" applies only inside a kept citation, and "translate the commentary" is the next line."""
    from pathlib import Path

    prompt = (
        Path(block_execution.__file__).resolve().parents[1] / "resources" / "prompts" / "operation_translate.txt"
    ).read_text(encoding="utf-8")
    lines = prompt.splitlines()
    rule = next(index for index, line in enumerate(lines) if line.startswith("12. "))
    inside, commentary = lines[rule + 1], lines[rule + 2]
    assert inside.lstrip().startswith("- Только внутри оставленной ссылки")
    assert "Ibid." in inside and "3 March 1998" in inside
    assert commentary.lstrip().startswith("- Комментарий переводите всегда")
    assert lines[rule + 3].startswith("13. ")


# =============================================================================================
# Codex acceptance review 2026-11-08, two P0 on P1 -- counter-rules that must hold
# =============================================================================================

_NUMBERED_STEPS_WITH_YEARS = "1 Collect receipts from 2010. 2 Sort documents from 1999."
_STEPS_WITH_YEARS_LONGER = (
    "1 Open the ledger kept since 1987 and copy the totals. 2 Compare them with the figures of 1994. "
    "3 Mark every gap found in 2003 before the audit."
)
_SHORT_SENTENCES_WITHOUT_PERIODS = "1 Wash the bowls 2 Dry the cups 3 Stack the plates in 2011"


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(_NUMBERED_STEPS_WITH_YEARS, id="codex-counterexample-steps-with-years"),
        pytest.param(_STEPS_WITH_YEARS_LONGER, id="numbered-steps-each-with-a-year"),
        pytest.param(_SHORT_SENTENCES_WITHOUT_PERIODS, id="short-sentences-without-periods"),
    ],
)
def test_a_bare_year_is_not_a_citation_anchor_numbered_body_steps_are_no_notes_run(text: str) -> None:
    assert output_validation.is_notes_run_paragraph(text) is False
    assert output_validation.notes_run_reads_as_citations(text) is False


@pytest.mark.parametrize(
    "entry",
    [
        "R. Hall, *The Tides of Cities*, 2004.",
        "‘Money and Debt in Two Ports’, 1999.",
        "Hall (2004), on the ports.",
        "Hall, ports and debt, 2004, p. 85.",
        "See www.example.org for the series.",
        "Hall, R. Ports and debt.",
    ],
)
def test_each_citation_anchor_is_recognised(entry: str) -> None:
    assert output_validation.has_citation_anchor(entry) is True


def test_counter_rule_a_sentence_with_a_year_has_no_citation_anchor() -> None:
    assert output_validation.has_citation_anchor("Collect receipts from 2010.") is False
    assert output_validation.has_citation_anchor("Sort the documents, then file them.") is False


def test_codex_counterexample_end_to_end_is_not_marked_and_not_credited() -> None:
    blocks = [
        DocumentBlock(paragraphs=[_unit("Chapter One", "p0000", role="heading", level=1), _unit(_PROSE, "p0001")]),
        DocumentBlock(paragraphs=[_unit(_NUMBERED_STEPS_WITH_YEARS, "p0002")]),
    ]
    jobs = semantic_blocks.build_editing_jobs(blocks, max_chars=3000, processing_operation="translate")
    assert all(job["notes_in_body_paragraph_ids"] == [] for job in jobs)
    # Even with the mark forced on, the unchanged echo is not credited as kept citations.
    payload = _payload([_NUMBERED_STEPS_WITH_YEARS], notes=[0])
    assert block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=_answer(payload)) is None


def test_a_heading_inside_a_longer_word_is_not_a_name_occurrence() -> None:
    """Codex P0: heading «Trade» and the sentence «Our team uses TradeLink ...» -- a substring is
    not an occurrence of the phrase, so the heading is not a name."""
    book = [
        _unit("Trade", "h", role="heading", level=3),
        _unit("Our team uses TradeLink to connect all suppliers.", "b"),
    ]
    assert semantic_blocks._resolve_name_heading_positions(book, ["prose", "prose"]) == frozenset()
    # Counter-proof: the same heading written as a whole word mid-sentence is a name.
    book[1] = _unit("Our team uses Trade to connect all suppliers.", "b")
    assert semantic_blocks._resolve_name_heading_positions(book, ["prose", "prose"]) == frozenset({0})
