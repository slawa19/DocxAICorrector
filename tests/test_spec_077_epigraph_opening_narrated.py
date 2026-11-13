"""Spec 077: a chapter's opening that the spec 067 mark reads as a one-entry notes run is narrated.

An epigraph with its attribution, a stray note number and the chapter's first paragraph arrive as
ONE paragraph; by form it is a notes run of one entry with a lead (spec 067 FR-001), so the
narration dropped the chapter's first paragraph. The audiobook now narrates such a paragraph when
the entry is prose holding no further entry opener and the lead is a quotation with a signature --
for the narration only: the spec 067 mark and the translate and edit jobs do not change. Each
negative test breaks one condition and keeps the others.

The texts are invented and carry the shape of the measured case only (Constitution VII).
"""

from __future__ import annotations

from typing import cast

import pytest

from docxaicorrector.core.models import DocumentBlock, ParagraphUnit
from docxaicorrector.document import semantic_blocks
from docxaicorrector.document.narration_exclusion import follows_a_sentence_end, quotation_and_signature
from docxaicorrector.document.semantic_blocks import build_editing_jobs
from docxaicorrector.pipeline import output_validation

_PROSE_ENTRY = (
    "We have seen how a second ledger in the port would change the way the pilots *trade* with each "
    "other, and this chapter follows that change from one quay to the next.¹"
)
_EPIGRAPH = "*“The tide does not wait for the harbour master.”* – K. L. Tollan"
_OPENING = _EPIGRAPH + " 1 " + _PROSE_ENTRY
_OPENING_GUILLEMETS = "*«Прилив не ждёт начальника порта».* — K. L. Tollan 1 " + _PROSE_ENTRY
_OPENING_ITALIC_ONLY = "*The tide does not wait for the harbour master.* – K. L. Tollan 1 " + _PROSE_ENTRY
# A number inside the prose that does not stand after a sentence end opens no entry.
_OPENING_WITH_A_NUMBER = (
    _EPIGRAPH + " 1 We have seen how the pilots of 3 Harbours *trade* with each other, and this chapter "
    "follows that change from one quay to the next."
)
# A signature in the author form "Surname, I." names a person; it is no hard reference mark.
_OPENING_SURNAME_FIRST = "*“The tide does not wait for the harbour master.”* – Tollan, K. 1 " + _PROSE_ENTRY
_PROSE = (
    "A harbour is not a place but an arrangement among its pilots to treat one stretch of water "
    "as a shelter from the storm, and that arrangement is what this chapter is about."
)
_REFERENCE_ENTRY = "R. Hall, *The Tides of Cities* (London: Harbour Press, 2004), p. 85."
# Codex acceptance review, round 2, finding 3: notes numbered 1, 3, 5, ... form a chain of ONE
# whose entry hides every other note.
_PACK_OF_NOTES = (
    _EPIGRAPH
    + " 1 "
    + _PROSE_ENTRY
    + " "
    + " ".join(
        f"{number} K. Lane, *Coastal Routes and Their Keepers* ({1900 + number}), p. {number}. "
        "A comment on the route follows here."
        for number in range(3, 40, 2)
    )
)

# Each one breaks exactly one condition of the exemption; all are marked by spec 067.
_STAYS_EXCLUDED = [
    pytest.param("Footnotes 1 " + _PROSE_ENTRY, id="a-label-lead"),
    pytest.param("*Harbours and Their Keepers* (1997). 1 " + _PROSE_ENTRY, id="a-bibliographic-lead"),
    pytest.param(_EPIGRAPH + " 1 " + _REFERENCE_ENTRY, id="the-entry-is-a-reference"),
    pytest.param(_EPIGRAPH + " 1 " + _PROSE_ENTRY + " 2 " + _REFERENCE_ENTRY, id="two-entries"),
    pytest.param(_PACK_OF_NOTES, id="a-pack-of-entries-numbered-1-3-5"),
    pytest.param(
        "*“The tide does not wait for the harbour master.”* – K. Tollan, *Harbour Songs* (1998) 1 " + _PROSE_ENTRY,
        id="a-signature-with-a-year",
    ),
    pytest.param("*“The tide does not wait.” K. L. Tollan* 1 " + _PROSE_ENTRY, id="no-dash"),
    pytest.param("*The Tides of the Northern Cities* – K. L. Tollan 1 " + _PROSE_ENTRY, id="the-quotation-is-no-sentence"),
]


def _unit(text: str, pid: str, *, role: str = "body", level: int | None = None) -> ParagraphUnit:
    return ParagraphUnit(text=text, role=role, paragraph_id=pid, heading_level=level, structural_role=role)


def _chapter(opening: str) -> list[DocumentBlock]:
    return [
        DocumentBlock(paragraphs=[_unit("Chapter Four", "p0000", role="heading", level=1), _unit(_PROSE, "p0001")]),
        DocumentBlock(paragraphs=[_unit("Chapter Five", "p0002", role="heading", level=1), _unit(opening, "p0003")]),
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0004")]),
    ]


def _by_id(jobs: list[dict[str, object]], field: str) -> dict[str, object]:
    return {
        paragraph_id: value
        for job in jobs
        for paragraph_id, value in zip(cast(list[str], job["paragraph_ids"]), cast(list[object], job[field]))
    }


def _marked(jobs: list[dict[str, object]]) -> set[str]:
    return {pid for job in jobs for pid in cast(list[str], job["notes_in_body_paragraph_ids"])}


@pytest.mark.parametrize(
    "opening",
    [
        pytest.param(_OPENING, id="quotes-en-dash"),
        pytest.param(_OPENING_GUILLEMETS, id="guillemets-em-dash"),
        pytest.param(_OPENING_ITALIC_ONLY, id="italic-without-quotes"),
        pytest.param(_OPENING_WITH_A_NUMBER, id="a-number-inside-the-prose"),
        pytest.param(_OPENING_SURNAME_FIRST, id="a-signature-surname-first"),
    ],
)
def test_the_chapter_opening_is_marked_but_narrated(opening: str) -> None:
    jobs = build_editing_jobs(_chapter(opening), max_chars=3000, processing_operation="audiobook")
    assert "p0003" in _marked(jobs)  # the premise: spec 067 still marks it
    assert _by_id(jobs, "narration_exclusion_reasons")["p0003"] is None
    # It reaches the model like any narrated paragraph, and is context for its neighbour.
    assert opening[-60:] in str(jobs[1]["target_text"])
    assert opening[-60:] in str(jobs[2]["context_before"])


@pytest.mark.parametrize("opening", _STAYS_EXCLUDED)
def test_counter_rule_what_stays_excluded(opening: str) -> None:
    assert output_validation.is_notes_run_paragraph(opening) is True  # the premise
    jobs = build_editing_jobs(_chapter(opening), max_chars=3000, processing_operation="audiobook")
    assert "p0003" in _marked(jobs)
    assert _by_id(jobs, "narration_exclusion_reasons")["p0003"] == "notes_in_body"


def test_a_pack_of_entries_is_one_entry_to_the_chain() -> None:
    """The premise of the pack test: the chain sees ONE entry, so only the entry-opener bound keeps
    the pack out of the narration."""
    parts = output_validation.notes_run_parts(_PACK_OF_NOTES)
    assert parts is not None
    _, entries = parts
    assert len(entries) == 1
    assert not output_validation.notes_run_piece_reads_as_reference(entries[0])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("“The tide waits.” – K. L. Tollan", ("“The tide waits.”", "K. L. Tollan"), id="quotes-and-en-dash"),
        pytest.param("*«Прилив ждёт».* — K. Tollan", ("«Прилив ждёт».", "K. Tollan"), id="guillemets-em-dash-emphasis"),
        pytest.param("“Wait – then go.” – Tollan", ("“Wait – then go.”", "Tollan"), id="a-dash-inside-the-quotation"),
        pytest.param("“The tide waits.” – K. Lee-Tollan", ("“The tide waits.”", "K. Lee-Tollan"), id="a-hyphen-in-the-name"),
        pytest.param("“The tide waits.” K. L. Tollan", None, id="no-dash"),
        pytest.param("“The tide waits.”–Tollan", None, id="a-dash-without-spaces"),
        pytest.param("The Tides of Cities – K. L. Tollan", None, id="no-sentence-before-the-dash"),
        pytest.param("“The tide waits.” – 1998", None, id="a-signature-without-a-letter"),
        pytest.param("Footnotes", None, id="a-label"),
        pytest.param("", None, id="empty"),
    ],
)
def test_quotation_and_signature(text: str, expected: tuple[str, str] | None) -> None:
    assert quotation_and_signature(text) == expected


@pytest.mark.parametrize(
    ("text", "offset", "expected"),
    [
        pytest.param("Harbour Press, 2004, p. 85. 3 J. Smith", 28, True, id="after-a-full-stop"),
        pytest.param("it was “late.” 3 Pilots", 15, True, id="after-a-closing-quote"),
        pytest.param("the pilots of 3 Harbours", 14, False, id="inside-a-sentence"),
        pytest.param("3 Harbours", 0, False, id="at-the-start"),
    ],
)
def test_follows_a_sentence_end(text: str, offset: int, expected: bool) -> None:
    assert text[offset].isdigit()
    assert follows_a_sentence_end(text, offset) is expected


def test_note_number_spans_and_hard_reference_marks() -> None:
    text = "1 We met. 3 K. Lane, p. 4. 2010 Was a year; in 7 days."
    assert output_validation.note_number_spans(text) == ((1, 0), (3, 10))
    assert output_validation.has_hard_reference_mark("K. Tollan, *Harbour Songs* (1998)") is True
    assert output_validation.has_hard_reference_mark("see p. 12") is True
    assert output_validation.has_hard_reference_mark("www.example.org") is True
    # A name in the author form and an emphasised name are not marks of WHERE a work is found.
    assert output_validation.has_hard_reference_mark("Tollan, K.") is False
    assert output_validation.has_hard_reference_mark("*K. L. Tollan*") is False


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_translate_and_edit_are_unchanged(operation: str) -> None:
    jobs = build_editing_jobs(_chapter(_OPENING), max_chars=3000, processing_operation=operation)
    assert "p0003" in _marked(jobs)
    assert all("narration_exclusion_reasons" not in job for job in jobs)


def test_the_mark_is_not_narrowed_in_the_audiobook() -> None:
    """The exemption is subtracted for the narration reason only: the job field translate and edit
    read (and the audiobook job carries too) keeps the paragraph."""
    paragraphs = [_unit("Chapter Five", "h", role="heading", level=1), _unit(_OPENING, "b"), _unit(_PROSE, "c")]
    regions = ["prose"] * len(paragraphs)
    notes = semantic_blocks._resolve_notes_in_body_positions(paragraphs, regions)
    assert notes == frozenset({1})
    assert semantic_blocks._resolve_epigraph_led_note_positions(paragraphs, notes) == frozenset({1})
    jobs = build_editing_jobs([DocumentBlock(paragraphs=paragraphs)], max_chars=3000, processing_operation="audiobook")
    assert _marked(jobs) == {"b"}
    assert _by_id(jobs, "narration_exclusion_reasons")["b"] is None
