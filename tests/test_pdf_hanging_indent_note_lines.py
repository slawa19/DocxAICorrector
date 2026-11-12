"""Spec 078: the wrapped line of a numbered note set with a hanging indent continues its note.

The PDF import's first-line-indent branch read every line set to the right of the line above
as the first line of a new paragraph. A note set with a hanging indent puts its number at the
margin and its wrapped lines further right, so each such note was torn after its first line
(Money and Sustainability, 62 notes). The rule in
``logical_import._continues_hanging_numbered_line`` keeps those lines together; every negative
test below pins one of its conditions and fails when that condition is removed.
"""

from __future__ import annotations

from collections import Counter

import pytest

import docxaicorrector.pdf_import.logical_import as logical_import
from docxaicorrector.pdf_import.logical_import import build_paragraph_units_from_text_spans
from docxaicorrector.pdf_import.text_layer_quality import PdfTextSpan

# Page geometry shared by every test: body column x0 50 .. x1 450, 10 pt type on a 14 pt
# pitch (12 pt line box, 2 pt between lines), so the first-line-indent step is
# 0.45 x 14 = 6.3 pt and an indent of 22 pt is well past it.
_LEFT = 50.0
_RIGHT = 450.0
_HANG = 72.0
_PITCH = 14.0
_LINE = 12.0


def _span(text: str, *, top: float, x0: float = _LEFT, x1: float = _RIGHT, size: float = 10.0) -> PdfTextSpan:
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
        size = row[3] if len(row) == 4 else 10.0
        spans.append(_span(text, top=top, x0=x0, x1=x1, size=size))
        top += _PITCH
    return spans


def _texts(spans: list[PdfTextSpan]) -> list[str]:
    return [paragraph.text or "" for paragraph in build_paragraph_units_from_text_spans(spans).paragraphs]


def _nonspace(texts: list[str]) -> Counter[str]:
    return Counter(char for text in texts for char in text if not char.isspace())


# --- the rule joins ------------------------------------------------------------------------


def test_note_with_hanging_indent_keeps_its_wrapped_lines() -> None:
    # Money and Sustainability's notes: number at the margin, wrapped lines indented, a size
    # below the body. Before spec 078 "Implications, ..." became the lead of note 13 and
    # "University Press ..." a paragraph of its own.
    spans = _lines(
        ("12 Stephen G. Cecchetti and M. S. Mohanty, The Future of Public Debt: Prospects and", _LEFT, 449.0, 9.0),
        ("Implications, BIS Working Paper 300 (2010).", _HANG, 300.0, 9.0),
        ("13 Nicholas Georgescu-Roegen, The Entropy Law and the Economic Process, Harvard", _LEFT, 448.0, 9.0),
        ("University Press (1971), pp. 12-14.", _HANG, 250.0, 9.0),
    )

    texts = _texts(spans)

    assert any("Prospects and Implications, BIS Working Paper 300 (2010)." in text for text in texts)
    assert any("Economic Process, Harvard University Press (1971), pp. 12-14." in text for text in texts)
    assert not any(text.startswith(("Implications", "University")) for text in texts)


def test_note_whose_first_line_ends_a_sentence_keeps_its_capitalised_continuation() -> None:
    # Nine of the 62 Money notes end a sentence exactly at the end of the full first line, and
    # the wrapped line opens with a capital; the soft-wrap merge does not reach them.
    spans = _lines(
        ("15 The Elderplan insurance company in New York ran this idea with a time currency.", _LEFT, 449.0, 9.0),
        ("They found that people who took part in it stayed healthier for longer.", _HANG, 400.0, 9.0),
    )

    texts = _texts(spans)

    assert any(
        "with a time currency. They found that people who took part" in text for text in texts
    )


def test_hanging_indent_rule_conserves_every_character() -> None:
    # The rule only decides whether two lines belong to one paragraph; it never drops,
    # reorders or rewrites text. Same characters, same order, with and without it.
    spans = _lines(
        ("12 Stephen G. Cecchetti and M. S. Mohanty, The Future of Public Debt: Prospects and", _LEFT, 449.0, 9.0),
        ("Implications, BIS Working Paper 300 (2010).", _HANG, 300.0, 9.0),
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
        ("12 Stephen G. Cecchetti and M. S. Mohanty, The Future of Public Debt: Prospects and", _LEFT, 449.0, 9.0),
        ("Implications, BIS Working Paper 300 (2010).", _HANG, 300.0, 9.0),
        ("13 Nicholas Georgescu-Roegen, The Entropy Law and the Economic Process, Harvard", _LEFT, 448.0, 9.0),
        ("University Press (1971), pp. 12-14.", _HANG, 250.0, 9.0),
    )
    with_rule = _texts(spans)
    monkeypatch.setattr(logical_import, "_continues_hanging_numbered_line", lambda *a, **k: False)
    without_rule = _texts(spans)

    assert len(with_rule) < len(without_rule)
    assert _nonspace(with_rule) == _nonspace(without_rule)
    assert " ".join(with_rule).split() == " ".join(without_rule).split()


# --- the shapes it must leave apart: each pins one condition --------------------------------


def test_numbered_heading_at_body_size_keeps_the_indented_paragraph_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # "3 Results" ends short; the indented line under it is the first line of the section's
    # first paragraph. The importer types the line a heading (numbered-section rule), so the
    # body merge -- and the hanging-indent rule inside it -- is never reached; the full-line
    # condition is the second guard for this shape and is pinned by the two tests below.
    def _must_not_be_called(*args: object, **kwargs: object) -> bool:
        raise AssertionError("a numbered heading reached the hanging-indent rule")

    monkeypatch.setattr(logical_import, "_continues_hanging_numbered_line", _must_not_be_called)
    spans = _lines(
        ("3 Results", _LEFT, 110.0),
        ("The samples were collected in the spring and measured twice over the year.", _HANG, 440.0),
        ("Each measurement was repeated by a second observer to check the first.", _LEFT, 420.0),
    )

    texts = _texts(spans)

    assert "3 Results" in texts
    assert not any("Results The samples" in text for text in texts)


def test_short_note_keeps_the_indented_line_under_it_apart() -> None:
    # Condition: the numbered line is FULL. A one-line note ends short (half the column); an
    # indented line of the same size under it starts a paragraph of its own. (A note ending
    # in a bare page number would be typed a contents entry and never reach the rule.)
    spans = _lines(
        ("16 See Beinhocker (2006) for the whole argument.", _LEFT, 260.0, 9.0),
        ("Figures in this chapter are drawn from the sources listed above unless noted.", _HANG, 445.0, 9.0),
    )

    texts = _texts(spans)

    assert not any("whole argument. Figures in this chapter" in text for text in texts)


def test_one_line_numbered_item_keeps_its_indented_sub_paragraph_apart() -> None:
    # Condition: the numbered line is FULL. A one-line numbered item without a full stop
    # (so not a list item by the importer's form) followed by an indented paragraph.
    spans = _lines(
        ("1 Collect the samples before noon", _LEFT, 230.0),
        ("Samples taken later in the day are kept apart and labelled with the hour.", _HANG, 445.0),
        ("They are measured only after the morning samples have been recorded.", _LEFT, 410.0),
    )

    texts = _texts(spans)

    assert "1 Collect the samples before noon" in texts
    assert not any("before noon Samples taken" in text for text in texts)


def test_ordinary_first_line_indent_after_a_numbered_paragraph_still_splits() -> None:
    # Condition: the line ABOVE the indent opens with a note number. A numbered paragraph of
    # a legal text runs several lines flush; its last line is full but is not the numbered
    # line, so the indented line under it is the next paragraph's first-line indent.
    spans = _lines(
        ("12 The parties agree that the lease runs for ten years from the date of signing and", _LEFT, 448.0),
        ("that either of them may end it on six months' notice given in writing to the other", _LEFT, 449.0),
        ("party at the address stated above, or at any later address notified in writing.", _LEFT, 447.0),
        ("Notice is given on the day it is delivered by hand or the day after it is posted.", _HANG, 440.0),
    )

    texts = _texts(spans)

    assert any(text.startswith("Notice is given on the day") for text in texts)
    assert not any("notified in writing. Notice is given" in text for text in texts)


def test_indented_line_that_opens_with_a_number_is_the_next_entry() -> None:
    # Condition: the indented line does NOT open with a note number. Two consecutive notes
    # whose second number is set indented: the second is a new entry, not a wrapped line.
    spans = _lines(
        ("11 Galbraith, Money: Whence It Came, Where It Went, Houghton Mifflin, Boston (1975).", _LEFT, 449.0, 9.0),
        ("12 Ferguson, The Cash Nexus: Money and Power in the Modern World (2001), p. 77.", _HANG, 445.0, 9.0),
    )

    texts = _texts(spans)

    assert not any("Boston (1975). 12 Ferguson" in text for text in texts)


def test_note_followed_by_indented_body_text_in_another_size_stays_apart() -> None:
    # Condition: both lines are set in ONE size. A chapter's last note, set below the body
    # size, followed with no extra space by an indented paragraph in the body size.
    spans = _lines(
        ("41 Office of the Inspector-General, City of Chicago, Report on the Parking Meter", _LEFT, 449.0, 8.5),
        ("The city sold its parking meters for seventy-five years in a single afternoon.", _HANG, 445.0),
        ("Within a year the rates had doubled and the council had no say over them.", _LEFT, 420.0),
    )

    texts = _texts(spans)

    assert not any("Parking Meter The city sold" in text for text in texts)
    assert any(text.startswith("The city sold its parking meters") for text in texts)


def test_contents_line_is_not_continued_by_the_indented_line_under_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A table of contents: a numbered chapter line with its page number, then an indented
    # section line. Both are typed contents entries before the body merge, so the
    # hanging-indent rule is never consulted.
    def _must_not_be_called(*args: object, **kwargs: object) -> bool:
        raise AssertionError("a contents line reached the hanging-indent rule")

    monkeypatch.setattr(logical_import, "_continues_hanging_numbered_line", _must_not_be_called)
    spans = _lines(
        ("3 The Monetary Blind Spot and What It Costs a Sustainable Economy 45", _LEFT, 449.0),
        ("Why the monetary system was left out of the sustainability debate 47", _HANG, 449.0),
    )

    texts = _texts(spans)

    assert not any("Economy 45 Why the monetary" in text for text in texts)


def test_note_followed_by_body_text_at_the_margin_never_consults_the_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No indent, no hanging-indent question: the rule is not consulted, so whatever decides
    # this boundary is what decided it before spec 078.
    def _must_not_be_called(*args: object, **kwargs: object) -> bool:
        raise AssertionError("the hanging-indent rule was consulted without an indent")

    monkeypatch.setattr(logical_import, "_continues_hanging_numbered_line", _must_not_be_called)
    spans = _lines(
        ("41 Office of the Inspector-General, City of Chicago, Report on the Parking Meter", _LEFT, 449.0, 9.0),
        ("The city sold its parking meters for seventy-five years in a single afternoon.", _LEFT, 445.0),
    )

    assert _texts(spans)
