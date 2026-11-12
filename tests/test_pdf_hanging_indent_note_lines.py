"""Spec 078: the wrapped line of a numbered note set with a hanging indent continues its note.

The PDF import's first-line-indent branch read every line set to the right of the line above
as the first line of a new paragraph. A note set with a hanging indent puts its number at the
margin and its wrapped lines further right, so each such note was torn after its first line
(Money and Sustainability, 62 notes). The rule in
``logical_import._continues_hanging_numbered_line`` keeps those lines together.

What the tests below prove, and how:
  * CONDITION tests -- each keeps two lines apart because of one condition of the rule, and
    fails when that condition is removed from the rule (mutation runs, spec 078 Changelog);
  * a DOWNSTREAM test -- body text set like a numbered instruction must not become a run of
    notes and leave the narration (Codex acceptance review round 1, P1): spans, the import,
    the notes-run mark and the narration exclusion reason, all production code;
  * ROUTING tests -- shapes that never reach the rule (typed a heading or a contents entry
    first, or no indent at all); they patch the rule to raise and prove only the routing.
All texts are invented; none is taken from a corpus book (Constitution VII).
"""

from __future__ import annotations

from collections import Counter

import pytest

import docxaicorrector.pdf_import.logical_import as logical_import
from docxaicorrector.core.models import PARAGRAPH_REGION_PROSE, ParagraphUnit
from docxaicorrector.document.narration_exclusion import resolve_narration_exclusion_reason
from docxaicorrector.document.semantic_blocks import _resolve_notes_in_body_positions
from docxaicorrector.pdf_import.logical_import import build_paragraph_units_from_text_spans
from docxaicorrector.pdf_import.text_layer_quality import PdfTextSpan

# Page geometry shared by every test: body column x0 50 .. x1 450, 10 pt body type on a 14 pt
# pitch (12 pt line box, 2 pt between lines), so the first-line-indent step is
# 0.45 x 14 = 6.3 pt and an indent of 22 pt is well past it. Small print is 8.5 pt: outside
# the importer's size tolerance of the 10 pt body (max(0.5, 10 % of the smaller size)).
_LEFT = 50.0
_RIGHT = 450.0
_HANG = 72.0
_PITCH = 14.0
_LINE = 12.0
_BODY = 10.0
_SMALL = 8.5


def _span(text: str, *, top: float, x0: float = _LEFT, x1: float = _RIGHT, size: float = _BODY) -> PdfTextSpan:
    return PdfTextSpan(
        page_number=1,
        text=text,
        x0=x0,
        top=top,
        x1=x1,
        bottom=top + _LINE,
        page_height=800,
        font_name="SourceSerif",
        font_size=size,
        is_bold=False,
        is_italic=False,
    )


def _context() -> list[PdfTextSpan]:
    """Running body text that gives the page its body size, margins and leading, then a
    paragraph gap, so the lines under test start a paragraph of their own."""
    return [
        _span("A first running body line that sets the measure of the page for the import.", top=40),
        _span("A second running body line that sets the measure of the page for the import.", top=54),
        _span("A third running body line that closes the opening paragraph of the page here.", top=68),
    ]


def _lines(*rows: tuple[str, float, float] | tuple[str, float, float, float]) -> list[PdfTextSpan]:
    """(text, x0, x1[, size]) rows set one pitch apart, starting after a paragraph gap."""
    spans = _context()
    top = 110.0
    for row in rows:
        text, x0, x1 = row[0], row[1], row[2]
        size = row[3] if len(row) == 4 else _BODY
        spans.append(_span(text, top=top, x0=x0, x1=x1, size=size))
        top += _PITCH
    return spans


def _paragraphs(spans: list[PdfTextSpan]) -> list[ParagraphUnit]:
    return build_paragraph_units_from_text_spans(spans).paragraphs


def _texts(spans: list[PdfTextSpan]) -> list[str]:
    return [paragraph.text or "" for paragraph in _paragraphs(spans)]


def _nonspace(texts: list[str]) -> Counter[str]:
    return Counter(char for text in texts for char in text if not char.isspace())


def _narration_reasons(spans: list[PdfTextSpan]) -> list[tuple[str, str | None]]:
    """(text, narration exclusion reason) per imported paragraph, every paragraph taken as
    prose: the spec 067 notes-in-body mark, then the spec 070 exclusion reason."""
    paragraphs = _paragraphs(spans)
    regions = [PARAGRAPH_REGION_PROSE] * len(paragraphs)
    marked = _resolve_notes_in_body_positions(paragraphs, regions)
    return [
        (
            paragraph.text or "",
            resolve_narration_exclusion_reason(
                structural_role=paragraph.structural_role,
                paragraph_role=paragraph.role,
                region=PARAGRAPH_REGION_PROSE,
                back_matter_section=None,
                in_notes_in_body=position in marked,
                text=paragraph.text or "",
            ),
        )
        for position, paragraph in enumerate(paragraphs)
    ]


# --- the rule joins ------------------------------------------------------------------------


def test_note_with_hanging_indent_keeps_its_wrapped_lines() -> None:
    # Notes in small print: number at the margin, wrapped lines indented. Before spec 078
    # "Consequences, ..." became the lead of note 13 and "Fenwick House ..." a paragraph.
    spans = _lines(
        ("12 Harriet V. Lomond and P. Okafor-Brandt, a study of the ledgers of small harbours, with prospects and", _LEFT, 449.0, _SMALL),
        ("Consequences, Coastal Papers Series 41 (2011).", _HANG, 300.0, _SMALL),
        ("13 Tobias Wrenfield, The Weight of Tides and the Accounting of Quiet Ports, Fenwick", _LEFT, 448.0, _SMALL),
        ("House Press (1974), pp. 12-14.", _HANG, 250.0, _SMALL),
    )

    texts = _texts(spans)

    assert any("with prospects and Consequences, Coastal Papers Series 41 (2011)." in text for text in texts)
    assert any("Quiet Ports, Fenwick House Press (1974), pp. 12-14." in text for text in texts)
    assert not any(text.startswith(("Consequences", "House Press")) for text in texts)


def test_note_whose_first_line_ends_a_sentence_keeps_its_capitalised_continuation() -> None:
    # The full first line ends a sentence and the wrapped line opens with a capital; the
    # soft-wrap merge does not reach this.
    spans = _lines(
        ("15 The Marrowby lending circle tried this scheme with tokens instead of coins in 1998.", _LEFT, 449.0, _SMALL),
        ("They found that members who took part in it stayed in the circle for longer.", _HANG, 400.0, _SMALL),
    )

    texts = _texts(spans)

    assert any("coins in 1998. They found that members" in text for text in texts)


def test_hanging_indent_rule_conserves_every_character() -> None:
    # The rule only decides whether two lines belong to one paragraph; it never drops,
    # reorders or rewrites text. Same characters, same order as the source.
    spans = _lines(
        ("12 Harriet V. Lomond and P. Okafor-Brandt, a study of the ledgers of small harbours, with prospects and", _LEFT, 449.0, _SMALL),
        ("Consequences, Coastal Papers Series 41 (2011).", _HANG, 300.0, _SMALL),
        ("3 Results", _LEFT, 110.0),
        ("The samples were collected in the spring and measured twice over the year.", _HANG, 440.0),
        ("Each measurement was repeated by a second observer to check the first.", _LEFT, 420.0),
    )
    source = [span.text for span in spans]

    with_rule = _texts(spans)

    assert _nonspace(with_rule) == _nonspace(source)
    assert " ".join(with_rule).split() == " ".join(source).split()


def test_hanging_indent_rule_changes_nothing_but_paragraph_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    spans = _lines(
        ("12 Harriet V. Lomond and P. Okafor-Brandt, a study of the ledgers of small harbours, with prospects and", _LEFT, 449.0, _SMALL),
        ("Consequences, Coastal Papers Series 41 (2011).", _HANG, 300.0, _SMALL),
        ("13 Tobias Wrenfield, The Weight of Tides and the Accounting of Quiet Ports, Fenwick", _LEFT, 448.0, _SMALL),
        ("House Press (1974), pp. 12-14.", _HANG, 250.0, _SMALL),
    )
    with_rule = _texts(spans)
    monkeypatch.setattr(logical_import, "_continues_hanging_numbered_line", lambda *a, **k: False)
    without_rule = _texts(spans)

    assert len(with_rule) < len(without_rule)
    assert _nonspace(with_rule) == _nonspace(without_rule)
    assert " ".join(with_rule).split() == " ".join(without_rule).split()


# --- downstream: body text must not become a notes run (Codex review round 1, P1) -----------

_INSTRUCTION = (
    ("1 Disconnect the supply before opening the enclosure or removing the cover.", _LEFT, 410.0),
    ("Follow the isolation procedure described in the manual (2024).", _HANG, 380.0),
    ("2 Verify the absence of voltage before touching any exposed conductor.", _LEFT, 400.0),
)


def test_numbered_instruction_at_body_size_stays_narrated() -> None:
    # A technical instruction set at body size, numbers without a full stop: a full numbered
    # line, an indented paragraph of its own, the next numbered line. Joined, the three lines
    # read as a chain 1, 2 with one citation mark -- a notes run -- and left the narration.
    reasons = _narration_reasons(_lines(*_INSTRUCTION))

    instruction = [(text, reason) for text, reason in reasons if "Disconnect" in text or "Verify" in text]
    assert instruction
    assert all(reason is None for _, reason in instruction), instruction
    assert not any("removing the cover. Follow the isolation" in text for text, _ in reasons)


def test_body_size_numbered_line_after_a_small_print_entry_stays_narrated() -> None:
    # Codex review round 2, P1: the first two lines are small print and join by the rule; the
    # third, a numbered line at the BODY size, used to join them through the ordinary body
    # merge, and the paragraph -- a chain 1, 2 with a citation mark -- left the narration
    # together with that body-size line. A numbered line at the body size after small print
    # starts a paragraph of its own.
    spans = _lines(
        ("1 Disconnect the supply before opening the enclosure or removing the cover.", _LEFT, 410.0, _SMALL),
        ("Follow the isolation procedure described in the manual (2024).", _HANG, 380.0, _SMALL),
        ("2 Verify the absence of voltage before touching any exposed conductor.", _LEFT, 400.0),
    )

    reasons = _narration_reasons(spans)

    body_line = [(text, reason) for text, reason in reasons if "Verify the absence" in text]
    assert body_line
    assert all(reason is None for _, reason in body_line), body_line
    # The small-print pair stays joined, and alone it is one entry without a lead -- not a
    # run of notes -- so it is narrated too.
    small_print = [(text, reason) for text, reason in reasons if "removing the cover. Follow the isolation" in text]
    assert small_print
    assert all(reason is None for _, reason in small_print), small_print
    assert not any("(2024). 2 Verify" in text for text, _ in reasons)


def test_rule_never_fires_when_the_body_size_is_unknown() -> None:
    # Condition: the body size is known. Without it nothing says the lines are small print.
    def _profile(body_font_size: float | None):
        return logical_import._PdfHeadingLayoutProfile(
            body_font_size=body_font_size,
            body_left_x0=_LEFT,
            body_right_x1=_RIGHT,
            body_leading=_PITCH,
            body_line_length_p75=80.0,
            body_line_length_p90=85.0,
            body_uppercase_ratio=0.05,
            body_title_word_ratio=0.1,
        )

    head = _span("12 Harriet V. Lomond and P. Okafor-Brandt, a study of the ledgers of small harbours, with prospects and",
                 top=110, x1=449.0, size=_SMALL)
    tail = _span("Consequences, Coastal Papers Series 41 (2011).", top=124, x0=_HANG, x1=300.0, size=_SMALL)

    assert logical_import._continues_hanging_numbered_line(head, tail, layout_profile=_profile(_BODY))
    assert not logical_import._continues_hanging_numbered_line(head, tail, layout_profile=_profile(None))


# --- condition tests: shapes the rule must leave apart --------------------------------------
# Body-size shapes (Codex review round 1, "checked forms of body text"): the condition that
# keeps each apart is "both lines are set smaller than the body".


def test_one_line_legal_item_at_body_size_keeps_its_indented_paragraph_apart() -> None:
    spans = _lines(
        ("12 The parties agree that the lease runs for ten years from the date of signing.", _LEFT, 440.0),
        ("Either party may end it on six months' notice given in writing to the other.", _HANG, 445.0),
        ("13 The tenant keeps the premises in good repair throughout the whole term.", _LEFT, 420.0),
    )

    texts = _texts(spans)

    assert not any("date of signing. Either party" in text for text in texts)


def test_title_opening_with_a_number_at_body_size_keeps_the_next_paragraph_apart() -> None:
    spans = _lines(
        ("40 Quiet Rooms was staged in a single week in a borrowed hall down by the river.", _LEFT, 445.0),
        ("Nobody in the company had worked in a theatre before that first winter season.", _HANG, 445.0),
    )

    texts = _texts(spans)

    assert not any("by the river. Nobody in the company" in text for text in texts)


def test_verse_after_a_numbered_line_at_body_size_stays_apart() -> None:
    spans = _lines(
        ("3 Songs for the Winter Road opens the cycle with the lines that the singer recalls:", _LEFT, 446.0),
        ("Over the hill the lantern swings,", _HANG, 260.0),
        ("and the dark comes down to meet it.", _HANG, 270.0),
    )

    texts = _texts(spans)

    assert not any("singer recalls: Over the hill" in text for text in texts)


def test_caption_opening_with_a_bare_number_at_body_size_stays_apart() -> None:
    spans = _lines(
        ("1 Distribution of pressure along the inner wall of the vessel at its full working load", _LEFT, 448.0),
        ("The pressure rises steeply near the inlet and falls away towards the outlet valve.", _HANG, 446.0),
    )

    texts = _texts(spans)

    assert not any("working load The pressure rises" in text for text in texts)


def test_unrecognised_contents_line_at_body_size_stays_apart() -> None:
    # A contents line without a page number is not typed a contents entry.
    spans = _lines(
        ("4 The Long Road Home and the Questions It Leaves Behind for the Patient Reader", _LEFT, 447.0),
        ("The first crossing and what it cost the families who stayed behind", _HANG, 400.0),
    )

    texts = _texts(spans)

    assert not any("Patient Reader The first crossing" in text for text in texts)


# Small-print shapes, one condition each.


def test_one_line_numbered_item_keeps_its_indented_sub_paragraph_apart() -> None:
    # Condition: the numbered line is FULL. A one-line numbered item without a full stop
    # (so not a list item by the importer's form) followed by an indented paragraph.
    spans = _lines(
        ("1 Collect the samples before noon", _LEFT, 230.0, _SMALL),
        ("Samples taken later in the day are kept apart and labelled with the hour.", _HANG, 445.0, _SMALL),
        ("They are measured only after the morning samples have been recorded.", _LEFT, 410.0, _SMALL),
    )

    texts = _texts(spans)

    assert "1 Collect the samples before noon" in texts
    assert not any("before noon Samples taken" in text for text in texts)


def test_short_note_keeps_the_indented_line_under_it_apart() -> None:
    # Condition: the numbered line is FULL. A one-line note ends short (half the column); an
    # indented line of the same size under it starts a paragraph of its own. (A note ending
    # in a bare page number would be typed a contents entry and never reach the rule.)
    spans = _lines(
        ("16 See Halloran (2003) for the whole argument.", _LEFT, 260.0, _SMALL),
        ("Figures in this chapter are drawn from the sources listed above unless noted.", _HANG, 445.0, _SMALL),
    )

    texts = _texts(spans)

    assert not any("whole argument. Figures in this chapter" in text for text in texts)


def test_ordinary_first_line_indent_after_a_numbered_paragraph_still_splits() -> None:
    # Condition: the line ABOVE the indent opens with a note number. A numbered paragraph runs
    # several lines flush; its last line is full but is not the numbered line, so the indented
    # line under it is the next paragraph's first-line indent.
    spans = _lines(
        ("12 The members agree that the fund runs for ten years from the date of signing and", _LEFT, 448.0, _SMALL),
        ("that any of them may leave it on six months' notice given in writing to the others", _LEFT, 449.0, _SMALL),
        ("at the address stated above, or at any later address notified to them in writing.", _LEFT, 447.0, _SMALL),
        ("Notice is given on the day it is delivered by hand or the day after it is posted.", _HANG, 440.0, _SMALL),
    )

    texts = _texts(spans)

    assert any(text.startswith("Notice is given on the day") for text in texts)
    assert not any("notified to them in writing. Notice is given" in text for text in texts)


def test_indented_line_that_opens_with_a_number_is_the_next_entry() -> None:
    # Condition: the indented line does NOT open with a note number. Two consecutive notes
    # whose second number is set indented: the second is a new entry, not a wrapped line.
    spans = _lines(
        ("11 Pellworth, Coin and Credit in the Northern Counties, Arden, Leith, second edition (1968).", _LEFT, 449.0, _SMALL),
        ("12 Hasselby, Silver Roads and the Northern Trade in the Herring Years (1993), p. 41.", _HANG, 445.0, _SMALL),
    )

    texts = _texts(spans)

    assert not any("(1968). 12 Hasselby" in text for text in texts)


def test_note_followed_by_a_line_in_another_small_size_stays_apart() -> None:
    # Condition: both lines are set in ONE size. A note, then an indented source line set
    # smaller still -- both below the body, so only the size match keeps them apart.
    spans = _lines(
        ("41 Report of the harbour auditor on the mooring fee charged by the borough of Wexmoor and", _LEFT, 449.0, _SMALL),
        ("Collected from the annual returns of the borough for each of the years shown here.", _HANG, 445.0, 6.5),
    )

    texts = _texts(spans)

    assert not any("borough of Wexmoor and Collected from the annual" in text for text in texts)


def test_note_followed_by_indented_body_text_stays_apart() -> None:
    # Conditions: both lines are set smaller than the BODY, and in one size -- held by the two
    # together, so no single mutation drops this test (each alone is pinned elsewhere here).
    # A chapter's last note in small print, then with no extra space an indented paragraph in
    # the body size.
    spans = _lines(
        ("41 Report of the harbour auditor on the mooring fee charged by the borough of Wexmoor and", _LEFT, 449.0, _SMALL),
        ("The borough sold its moorings for forty years in a single afternoon.", _HANG, 445.0),
        ("Within a year the fees had doubled and the council had no say over them.", _LEFT, 420.0),
    )

    texts = _texts(spans)

    assert not any("borough of Wexmoor and The borough sold" in text for text in texts)
    assert any(text.startswith("The borough sold its moorings") for text in texts)


# --- routing tests: shapes that never reach the rule ----------------------------------------


def _forbid_rule(monkeypatch: pytest.MonkeyPatch, shape: str) -> None:
    def _must_not_be_called(*args: object, **kwargs: object) -> bool:
        raise AssertionError(f"{shape} reached the hanging-indent rule")

    monkeypatch.setattr(logical_import, "_continues_hanging_numbered_line", _must_not_be_called)


def test_routing_short_numbered_heading_never_reaches_the_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    # Routing only: "3 Results" ends short and is typed a heading by the per-line role
    # classifier before the body merge, so the rule is never consulted. (Were it body, the
    # full-line condition would keep it apart -- see the two short-line tests above.)
    _forbid_rule(monkeypatch, "a short numbered heading")
    spans = _lines(
        ("3 Results", _LEFT, 110.0),
        ("The samples were collected in the spring and measured twice over the year.", _HANG, 440.0),
        ("Each measurement was repeated by a second observer to check the first.", _LEFT, 420.0),
    )

    texts = _texts(spans)

    assert "3 Results" in texts
    assert not any("Results The samples" in text for text in texts)


def test_routing_contents_lines_never_reach_the_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    # Routing only: a numbered chapter line with its page number, then an indented section
    # line; both are typed contents entries before the body merge.
    _forbid_rule(monkeypatch, "a contents line")
    spans = _lines(
        ("3 The Tidal Ledger and What It Costs a Patient Coastal Economy 45", _LEFT, 449.0),
        ("Why the harbour ledger was left out of the long public debate 47", _HANG, 449.0),
    )

    texts = _texts(spans)

    assert not any("Economy 45 Why the harbour" in text for text in texts)


def test_routing_note_followed_by_text_at_the_margin_never_reaches_the_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Routing only: no indent, no hanging-indent question.
    _forbid_rule(monkeypatch, "a line without an indent")
    spans = _lines(
        ("41 Report of the harbour auditor on the mooring fee charged by the borough of Wexmoor and", _LEFT, 449.0, _SMALL),
        ("The borough sold its moorings for forty years in a single afternoon.", _LEFT, 445.0),
    )

    assert _texts(spans)
