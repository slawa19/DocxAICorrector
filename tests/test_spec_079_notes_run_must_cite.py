"""Spec 079: a chain of numbered entries is a run of notes only when at least one piece CITES.

The spec 067 form read numbered body text that merged into one paragraph -- two steps, one year in
brackets between them -- as a notes run: half the entries carried a citation anchor. The paragraph
was then excluded from the narration and translated under the apparatus policy. A chain of two or
more now also needs one piece, the lead or an entry, that is a reference by the per-piece test
(citation form AND an anchor). The one-entry path of spec 067 is unchanged.

The texts are invented (Constitution VII).
"""

from __future__ import annotations

from typing import cast

import pytest

from docxaicorrector.core.models import DocumentBlock, ParagraphUnit
from docxaicorrector.document.semantic_blocks import build_editing_jobs
from docxaicorrector.pipeline import output_validation

# Numbered body text, every piece prose by form; the anchors are incidental.
_STEPS_WITH_A_YEAR = (
    "1 Disconnect the supply before opening the enclosure or removing the cover. Follow the isolation "
    "procedure described in the manual (2024). 2 Verify the absence of voltage before touching any "
    "exposed conductor."
)
_CONDITIONS_WITH_A_YEAR = (
    "1 The offer holds only for members who joined before the end of the last season and paid in full. "
    "2 The discount applies once per member and cannot be combined with other offers (2024)."
)
_STEPS_WITH_AN_ITALIC_WORD = (
    "1 Open the *Settings* panel and choose the account that you want to change today. 2 Press the "
    "button marked Save and wait for the confirmation to appear on the screen."
)
_STEPS_WITH_A_QUOTED_PHRASE = (
    "1 Type “harbour charts” into the search field and wait for the list to appear below it. 2 Pick the "
    "first chart from the list and open it in a new window."
)

# Runs of notes the rule must keep (anti-vacuum: real apparatus is still counted).
_REFERENCE_AND_COMMENTARY = (
    "Notes 1 R. Hall, *The Tides of Cities* (London: Harbour Press, 2004), p. 85. 2 The harbour master "
    "kept a second ledger for the pilots, and this note explains why it mattered so much to the guild "
    "in the years that followed (1999)."
)
# The tail of a reference torn across a page leads; every numbered entry is the author's commentary.
_TORN_REFERENCE_LEAD_AND_COMMENTARY = (
    "*Harbours and Their Keepers* (1989). 20 The rate at which the old quays were abandoned is "
    "estimated at ten times the rate of the century before (2003). 21 The pilots themselves "
    "described the change in letters that survive in two family collections and in the guild's own "
    "minutes. 22 A later survey of the coast repeats the estimate without a source of its own (2011)."
)
_ONE_COMMENTARY_NOTE_BEHIND_A_LABEL = (
    "Notes 1 The canonical definition was given by the harbour historian in *The Shape of Tides* (1965), "
    "and it describes a harbour as a pattern of habits shared by the pilots who use it."
)
# The accepted cost: a run of two or more notes that are ALL commentary, with no reference lead.
_COMMENTARY_ONLY_RUN = (
    "Notes 1 The definition was first given by the harbour historian in *The Shape of Tides* (1965), and "
    "he describes a harbour as a pattern of habits. 2 This view has since been debated at length among "
    "historians of the coast, who doubt that it holds for the smaller ports."
)


def _unit(text: str, pid: str, *, role: str = "body", level: int | None = None) -> ParagraphUnit:
    return ParagraphUnit(text=text, role=role, paragraph_id=pid, heading_level=level, structural_role=role)


def _document(paragraph: str) -> list[DocumentBlock]:
    return [
        DocumentBlock(
            paragraphs=[
                _unit("Chapter Six", "p0000", role="heading", level=1),
                _unit(
                    "The pilots of the northern harbours kept their own rules, and this chapter follows them "
                    "from one quay to the next.",
                    "p0001",
                ),
                _unit(paragraph, "p0002"),
            ]
        )
    ]


def _marked(jobs: list[dict[str, object]]) -> set[str]:
    return {pid for job in jobs for pid in cast(list[str], job["notes_in_body_paragraph_ids"])}


def _reasons(jobs: list[dict[str, object]]) -> dict[str, object]:
    return {
        pid: reason
        for job in jobs
        for pid, reason in zip(cast(list[str], job["paragraph_ids"]), cast(list[object], job["narration_exclusion_reasons"]))
    }


_BODY_STEPS = [
    pytest.param(_STEPS_WITH_A_YEAR, id="steps-with-a-year"),
    pytest.param(_CONDITIONS_WITH_A_YEAR, id="conditions-with-a-year"),
    pytest.param(_STEPS_WITH_AN_ITALIC_WORD, id="steps-with-an-italic-word"),
    pytest.param(_STEPS_WITH_A_QUOTED_PHRASE, id="steps-with-a-quoted-phrase"),
]


@pytest.mark.parametrize("text", _BODY_STEPS)
def test_numbered_body_text_with_an_incidental_anchor_is_not_a_notes_run(text: str) -> None:
    body = output_validation._INTERNAL_PLACEHOLDER_PATTERN.sub(" ", text)
    chain = output_validation._note_number_chain(body)
    # The premise: a chain of two, at least half of it anchored -- the old form called it notes.
    assert len(chain) == 2
    entries = [body[chain[0][2] : chain[1][1]], body[chain[1][2] :]]
    assert sum(output_validation.has_citation_anchor(entry) for entry in entries) >= 1
    assert output_validation.is_notes_run_paragraph(text) is False
    assert output_validation.notes_run_commentary_numbers(text) == ()
    assert output_validation.notes_run_reads_as_citations(text) is False


@pytest.mark.parametrize("text", _BODY_STEPS)
@pytest.mark.parametrize("operation", ["audiobook", "translate", "edit"])
def test_numbered_body_text_is_not_marked_in_any_operation(text: str, operation: str) -> None:
    jobs = build_editing_jobs(_document(text), max_chars=3000, processing_operation=operation)
    assert _marked(jobs) == set()
    if operation == "audiobook":
        assert _reasons(jobs)["p0002"] is None


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(_REFERENCE_AND_COMMENTARY, id="a-reference-and-a-comment"),
        pytest.param(_TORN_REFERENCE_LEAD_AND_COMMENTARY, id="a-torn-reference-lead-and-comments"),
        pytest.param(_ONE_COMMENTARY_NOTE_BEHIND_A_LABEL, id="one-comment-behind-a-label"),
    ],
)
def test_runs_of_notes_stay_marked_and_excluded(text: str) -> None:
    assert output_validation.is_notes_run_paragraph(text) is True
    jobs = build_editing_jobs(_document(text), max_chars=3000, processing_operation="audiobook")
    assert _marked(jobs) == {"p0002"}
    assert _reasons(jobs)["p0002"] == "notes_in_body"


def test_the_torn_reference_lead_is_the_only_piece_that_cites() -> None:
    """The premise of the torn-lead case: no ENTRY is a reference, so only the lead keeps it a run."""
    parts = output_validation.notes_run_parts(_TORN_REFERENCE_LEAD_AND_COMMENTARY)
    assert parts is not None
    lead, entries = parts
    assert len(entries) == 3
    assert not any(output_validation.notes_run_piece_reads_as_reference(entry) for entry in entries)
    assert output_validation.notes_run_piece_reads_as_reference(lead)
    assert output_validation.notes_run_commentary_numbers(_TORN_REFERENCE_LEAD_AND_COMMENTARY) == (20, 21, 22)


def test_one_commentary_note_behind_a_label_keeps_the_spec_067_path() -> None:
    """A chain of ONE is judged by the spec 067 label path, not by this rule: its entry is
    commentary and nothing in it cites, yet it is a note."""
    parts = output_validation.notes_run_parts(_ONE_COMMENTARY_NOTE_BEHIND_A_LABEL)
    assert parts is not None
    lead, entries = parts
    assert (lead, len(entries)) == ("Notes", 1)
    assert not output_validation.notes_run_piece_reads_as_reference(entries[0])


def test_one_reference_does_not_replace_the_half_anchored_chain() -> None:
    """The rule ADDS a condition to the spec 067 chain test, it does not replace it: one cited step
    among three numbered steps without an anchor is still not a run of notes."""
    text = (
        "1 R. Hall, *The Tides of Cities* (London: Harbour Press, 2004), p. 85. 2 Turn the valve slowly "
        "until the gauge reads zero and the light goes out. 3 Close the cover and lock the enclosure "
        "before you leave the room."
    )
    assert len(output_validation._note_number_chain(text)) == 3
    assert output_validation.notes_run_parts(text) is None


def test_the_accepted_cost_a_run_of_commentary_only_is_read_as_body() -> None:
    """Named in the spec: two or more notes that are all commentary, behind a label that is not a
    reference, are no longer a notes run -- they are narrated and translated as body text."""
    assert len(output_validation._note_number_chain(_COMMENTARY_ONLY_RUN)) == 2
    assert output_validation.is_notes_run_paragraph(_COMMENTARY_ONLY_RUN) is False
    jobs = build_editing_jobs(_document(_COMMENTARY_ONLY_RUN), max_chars=3000, processing_operation="audiobook")
    assert _reasons(jobs)["p0002"] is None
