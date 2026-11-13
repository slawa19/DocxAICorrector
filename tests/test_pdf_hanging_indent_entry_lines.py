"""Spec 081: a wrapped line of a reference list set with a hanging indent continues its entry even
when its wording looks like the start of an entry.

The notes / reference join of spec 064 R-7 (``logical_import._join_torn_back_matter_entries``)
re-joins an entry the line grouping tore at its hanging indent, but it refused a wrapped line
whose wording opens like a new entry -- an author form ("Review, March 2011.") or a number and a
word ("27 May 2011."). Spec 081 lets the page's geometry decide those two openers
(``_entry_line_sits_at_the_hanging_indent``): the line sits to the right of the entry's first
line by the indent step, and the unbroken run of lines holding both shows that margin / indent
pair in at least two entries (``_HANGING_INDENT_MIN_RUN_ENTRIES``).

What the tests below prove, and how:
  * POSITIVE tests -- the join happens, and only paragraph boundaries change (every character
    kept, word order kept);
  * CONDITION tests -- each keeps two lines apart because of one condition, and fails when
    that condition is removed by a mutation (spec 081 Changelog, mutation table). Some of the
    shapes are contrived on purpose: their only job is to pin one guard;
  * SCOPE tests -- the rule lives inside the notes / reference join and never runs outside a
    notes or reference section.
All texts are invented; none is taken from a corpus book (Constitution VII).
"""

from __future__ import annotations

from collections import Counter

import pytest

import docxaicorrector.pdf_import.logical_import as logical_import
from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.pdf_import.logical_import import build_paragraph_units_from_text_spans
from docxaicorrector.pdf_import.text_layer_quality import PdfTextSpan

# Page geometry: body column x0 50 .. x1 450, 10 pt type on a 14 pt pitch (12 pt line box), so
# the line grouping's first-line-indent step is 0.45 x 14 = 6.3 pt. Entries begin at the margin
# (50) and wrap to a hanging indent of 15 pt (65); an edge tolerance is half a font size (5 pt).
_LEFT = 50.0
_HANG = 65.0
_FULL = 449.0
_PITCH = 14.0
_LINE = 12.0
_BODY = 10.0
_SMALL = 8.0
_START = 140.0
_GAP = "<blank line>"


def _span(text: str, *, top: float, x0: float, x1: float, size: float = _BODY, page: int = 1) -> PdfTextSpan:
    return PdfTextSpan(
        page_number=page,
        text=text,
        x0=x0,
        top=top,
        x1=x1,
        bottom=top + (_LINE if size >= _BODY else size * 1.2),
        page_height=800,
        font_name="SourceSerif",
        font_size=size,
        is_bold=False,
        is_italic=False,
    )


def _page(*rows: object, title: str = "Bibliography") -> list[PdfTextSpan]:
    """Three running body lines (the body size, margins and leading), a section title, then the
    rows: (text, x0, x1[, size]) set one pitch apart; `_GAP` leaves a blank line."""
    spans = [
        _span("A first running body line that sets the measure of the page for the import.", top=40, x0=_LEFT, x1=450),
        _span("A second running body line that sets the measure of the page for the import.", top=54, x0=_LEFT, x1=450),
        _span("A third running body line that closes the opening paragraph of the page here.", top=68, x0=_LEFT, x1=440),
        PdfTextSpan(
            page_number=1, text=title, x0=_LEFT, top=100, x1=160, bottom=120, page_height=800,
            font_name="SourceSerif-Bold", font_size=18, is_bold=True, is_italic=False,
        ),
    ]
    top = _START
    for row in rows:
        if row == _GAP:
            top += _PITCH * 1.5
            continue
        assert isinstance(row, tuple)
        text, x0, x1 = row[0], row[1], row[2]
        size = row[3] if len(row) == 4 else _BODY
        spans.append(_span(text, top=top, x0=x0, x1=x1, size=size))
        top += _PITCH
    return spans


def _texts(spans: list[PdfTextSpan]) -> list[str]:
    return [paragraph.text or "" for paragraph in build_paragraph_units_from_text_spans(spans).paragraphs]


def _nonspace(texts: list[str]) -> Counter[str]:
    return Counter(char for text in texts for char in text if not char.isspace())


# Entries of an invented reference list. Every entry's first line runs to the column edge
# without ending a sentence; its wrapped line sits at the hanging indent.
_ENTRY_A = (
    ("Ashdown, P., The Quiet Ledgers of the Northern Harbours and the Keepers of Their", _LEFT, _FULL),
    ("Lamps (Wendlemoor: Tolly Press, 1981).", _HANG, 260.0),
)
_ENTRY_C = (
    ("Corvell, A., Counting Ships at Dawn: Notes from the Harbour Office of the Old", _LEFT, _FULL),
    ("Lower Quay (Fenwick: Marrow House, 2004).", _HANG, 280.0),
)
_ENTRY_D = (
    ("Dunmore, K., ‘Why the harbour fees rose twice in one winter’, Tidewater Gazette,", _LEFT, _FULL),
    ("for the second time that year (Lowmoor: Gull Press, 1999).", _HANG, 330.0),
)
# The wrapped line opens with an author form: "Review, March ..." -- a capitalised word, a comma,
# a capitalised word.
_HEAD_AUTHOR_FORM = ("Brennick, T., ‘Tides and tallies: a short account of the port’, The Harbour", _LEFT, _FULL)
_TAIL_AUTHOR_FORM = ("Review, March 2011.", _HANG, 160.0)
# The wrapped line opens with a number and a word: a date.
_HEAD_DATE = ("Ellery, S., ‘A quay that never closed’, Coastal Notes, The Tidewater Gazette,", _LEFT, _FULL)
_TAIL_DATE = ("27 May 2011.", _HANG, 120.0)


def _off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logical_import, "_entry_line_sits_at_the_hanging_indent", lambda *a, **k: False)


# --- the rule joins ------------------------------------------------------------------------------


def test_wrapped_line_with_an_author_form_continues_its_entry() -> None:
    texts = _texts(_page(*_ENTRY_A, _HEAD_AUTHOR_FORM, _TAIL_AUTHOR_FORM, *_ENTRY_C))

    assert f"{_HEAD_AUTHOR_FORM[0]} {_TAIL_AUTHOR_FORM[0]}" in texts
    assert _TAIL_AUTHOR_FORM[0] not in texts


def test_wrapped_line_with_a_date_continues_its_entry() -> None:
    texts = _texts(_page(*_ENTRY_A, _HEAD_DATE, _TAIL_DATE, *_ENTRY_C))

    assert f"{_HEAD_DATE[0]} {_TAIL_DATE[0]}" in texts
    assert _TAIL_DATE[0] not in texts


def test_without_the_rule_both_wrapped_lines_stay_torn(monkeypatch: pytest.MonkeyPatch) -> None:
    # ANTI-VACUUM: the same pages with the rule switched off are torn, so the rule is what joins.
    _off(monkeypatch)
    texts = _texts(_page(*_ENTRY_A, _HEAD_AUTHOR_FORM, _TAIL_AUTHOR_FORM, _HEAD_DATE, _TAIL_DATE, *_ENTRY_C))

    assert _TAIL_AUTHOR_FORM[0] in texts
    assert _TAIL_DATE[0] in texts


def test_rule_changes_nothing_but_paragraph_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    spans = _page(*_ENTRY_A, _HEAD_AUTHOR_FORM, _TAIL_AUTHOR_FORM, _HEAD_DATE, _TAIL_DATE, *_ENTRY_C)
    source = [span.text for span in spans]
    with_rule = _texts(spans)
    _off(monkeypatch)
    without_rule = _texts(spans)

    assert len(with_rule) == len(without_rule) - 2
    assert _nonspace(with_rule) == _nonspace(without_rule) == _nonspace(source)
    assert " ".join(with_rule).split() == " ".join(without_rule).split() == " ".join(source).split()


# --- scope ---------------------------------------------------------------------------------------


def test_scope_same_list_outside_a_notes_or_reference_section_is_left_alone() -> None:
    # The rule is part of the notes / reference join, which reads only the region a notes or
    # reference title anchors. A list under any other title keeps today's split.
    texts = _texts(_page(*_ENTRY_A, _HEAD_AUTHOR_FORM, _TAIL_AUTHOR_FORM, *_ENTRY_C, title="Overview"))

    assert _HEAD_AUTHOR_FORM[0] in texts
    assert _TAIL_AUTHOR_FORM[0] in texts


# --- conditions: explicit entry markers ----------------------------------------------------------


def test_numbered_line_at_the_indent_starts_an_entry() -> None:
    # An entry whose full first line introduces a numbered sub-list set at the wrap indent. "1."
    # MARKS an entry; geometry does not overrule it.
    intro = ("Harbour Board papers consulted for this chapter are listed by shelf mark in", _LEFT, _FULL)
    first = ("1. Minutes, Lower Quay, 1880-1902.", _HANG, 260.0)
    second = ("2. Ledgers, Upper Quay, 1903-1911.", _HANG, 260.0)
    texts = _texts(_page(*_ENTRY_A, intro, first, second, *_ENTRY_C))

    assert intro[0] in texts
    assert first[0] in texts


# --- conditions: the step is read from the head's FIRST line, to the right ------------------------


def test_paragraphs_with_a_first_line_indent_stay_apart() -> None:
    # Prose (or a dialogue) set with a FIRST-line indent inside a notes section: a paragraph's
    # last line runs full to the margin without ending, the next paragraph starts at the indent
    # and opens with a name and a comma. Read from the paragraph's LAST line this is the same
    # step as a hanging indent, and the run shows it at every paragraph; read from its first
    # line there is no step at all.
    rows = (
        ("The keeper of the lower quay wrote down every vessel that came in on the", _HANG, _FULL),
        ("evening tide and every one that left before the morning bell rang over the", _LEFT, _FULL),
        ("Tamsin, Marrow and the clerk agreed that the tide was late again that night,", _HANG, _FULL),
        ("and the ledger stayed open on the desk until the bell rang over the", _LEFT, _FULL),
        ("Corin, Hale and the pilot argued about the fees until the lamps were lit.", _HANG, 430.0),
        ("Nobody wrote that part down.", _LEFT, 200.0),
    )
    texts = _texts(_page(*rows, title="Notes"))

    assert not any("rang over the Tamsin" in text for text in texts)
    assert not any("rang over the Corin" in text for text in texts)


def _unit(span: PdfTextSpan, *, role: str = "body") -> ParagraphUnit:
    return ParagraphUnit(
        text=span.text,
        role=role,
        structural_role=role,
        font_size_pt=span.font_size,
        origin_raw_indexes=[(span.page_number - 1) * 10000 + int(round(span.top))],
        origin_raw_texts=[span.text],
    )


def _title_unit() -> ParagraphUnit:
    return ParagraphUnit(
        text="Bibliography",
        role="heading",
        structural_role="heading",
        heading_level=2,
        font_size_pt=18,
        origin_raw_indexes=[100],
        origin_raw_texts=["Bibliography"],
    )


def test_line_at_the_margin_after_a_line_at_the_indent_starts_an_entry() -> None:
    # Unit level (the line grouping does not produce this pair by itself): a wrapped line of an
    # entry standing alone -- an address that ends in a hyphen, so it does not end a sentence --
    # then the next entry back at the margin. The step runs to the LEFT. Read as a distance
    # either way, the margin and the indent swap roles and the run still shows the pair at every
    # entry.
    spans = _page(
        *_ENTRY_A,
        ("Brennick, T., ‘Tides and tallies: a short account of the port’, Harbour Review (2011).", _LEFT, _FULL),
        ("www.tidewater.zz/archive/ledgers/lower-quay/the-report-of-the-clerk-for-the-", _HANG, _FULL),
        *_ENTRY_C,
        *_ENTRY_D,
    )
    profile = logical_import._build_heading_layout_profile(spans, repeated_furniture_keys=set())
    address, corvell = spans[-5], spans[-4]
    units = [_title_unit(), _unit(address), _unit(corvell)]

    joined = logical_import._join_torn_back_matter_entries(units, spans, layout_profile=profile)

    assert [unit.text for unit in joined] == ["Bibliography", address.text, corvell.text]


# --- conditions: the pair must sit in a RUN of at least two entries ------------------------------


def test_signature_over_a_place_line_stays_apart() -> None:
    # Set flush right at the end of a notes section: the signature runs to the right edge
    # (so it reads as full) and does not end a sentence; the place line under it starts further
    # right and opens like an author form. One step, no run.
    signature = ("— Tamsin and Corin", 330.0, 450.0)
    place = ("Lowmoor, Wendland", 360.0, 450.0)
    texts = _texts(_page(*_ENTRY_A, *_ENTRY_C, _GAP, signature, place, title="Notes"))

    assert signature[0] in texts
    assert place[0] in texts


def test_single_indented_quotation_under_a_full_line_stays_apart() -> None:
    # An entry quotes a letter, set at a deeper indent than the list's wrapped lines. The
    # quotation's margin / indent pair occurs once.
    head = ("Halloran, M., letter to the Harbour Board of the Lower Quay, which ends with the", _LEFT, _FULL)
    quote = ("Gentlemen, Whatever the tide does, the ledger stays open.", 90.0, 400.0)
    texts = _texts(_page(*_ENTRY_A, head, quote, *_ENTRY_C))

    assert head[0] in texts
    assert quote[0] in texts


# --- conditions: what belongs to the run ---------------------------------------------------------
# A lone pair -- a full line at the margin and a line at the indent that opens like an author
# form -- has no run of its own. Each test below puts a hanging-indent list at the SAME two
# edges next to it, separated by one thing the run must not cross.

_LONE_HEAD = ("Gillow, R., notes taken at the hearing of the Harbour Board on the matter of", _LEFT, _FULL)
_LONE_TAIL = ("Fees, Tolls and Moorings in the Lower Quay.", _HANG, 300.0)


def test_lone_pair_next_to_a_list_in_another_size_stays_apart() -> None:
    small_a = tuple((text, x0, x1, _SMALL) for text, x0, x1 in _ENTRY_A)
    small_c = tuple((text, x0, x1, _SMALL) for text, x0, x1 in _ENTRY_C)
    texts = _texts(_page(*small_a, *small_c, _LONE_HEAD, _LONE_TAIL))

    assert _LONE_HEAD[0] in texts
    assert _LONE_TAIL[0] in texts


def test_lone_pair_after_a_blank_line_stays_apart() -> None:
    texts = _texts(_page(*_ENTRY_A, *_ENTRY_C, _GAP, _LONE_HEAD, _LONE_TAIL))

    assert _LONE_HEAD[0] in texts
    assert _LONE_TAIL[0] in texts


def test_lone_pair_after_a_line_at_another_edge_stays_apart() -> None:
    texts = _texts(_page(*_ENTRY_A, *_ENTRY_C, ("* * *", 230.0, 262.0), _LONE_HEAD, _LONE_TAIL))

    assert _LONE_HEAD[0] in texts
    assert _LONE_TAIL[0] in texts


def test_run_must_hold_the_entry_s_own_first_line() -> None:
    # Unit level: the head's first line is at the margin, its second line at an edge of its own
    # (58: neither the margin nor the indent within half a font size), so the run around the
    # tail stops there and does not reach the head's first line; the list below it shows the
    # margin / indent pair twice.
    spans = _page(
        ("Ingram, L., a petition of the lamp keepers of the lower quay, with the note", _LEFT, _FULL),
        ("appended by the clerk of the board in his own hand, signed and dated by the", 58.0, _FULL),
        ("Keepers, Wardens and Pilots of the Quay.", _HANG, 300.0),
        *_ENTRY_C,
        *_ENTRY_D,
    )
    profile = logical_import._build_heading_layout_profile(spans, repeated_furniture_keys=set())
    first, second, tail = spans[4], spans[5], spans[6]
    head = _unit(first)
    head.text = f"{first.text} {second.text}"
    head.origin_raw_indexes = [int(round(first.top)), int(round(second.top))]
    head.origin_raw_texts = [first.text, second.text]
    units = [_title_unit(), head, _unit(tail)]

    joined = logical_import._join_torn_back_matter_entries(units, spans, layout_profile=profile)

    assert [unit.text for unit in joined] == ["Bibliography", head.text, tail.text]


# --- shapes the corpus lacks: held by the join's other conditions ---------------------------------


def test_verse_with_indented_second_lines_stays_apart() -> None:
    # Verse quoted in a note, every second line indented: the run shows the margin / indent pair
    # again and again, but no line ran out of room -- each ended where the verse line ends.
    rows = (
        ("Who keeps the ledger of the tide", _LEFT, 230.0),
        ("Harbours, Quays and the boats inside,", _HANG, 260.0),
        ("Who counts the lamps along the shore", _LEFT, 240.0),
        ("Keepers, Clerks and one man more?", _HANG, 250.0),
    )
    texts = _texts(_page(*_ENTRY_A, *rows, *_ENTRY_C, title="Notes"))

    assert not any("tide Harbours, Quays" in text for text in texts)
    assert not any("shore Keepers, Clerks" in text for text in texts)


def test_definition_under_a_short_term_stays_its_own_paragraph() -> None:
    # A glossary inside a reference section: the term at the margin ends well before the
    # column does, the definition is a block at the indent. By form that is two units -- the
    # term did not wrap -- and they are not joined.
    term = ("Tally", _LEFT, 80.0)
    definition = ("Tally-stick, Notched record of a debt, split between lender and borrower.", _HANG, 440.0)
    texts = _texts(_page(*_ENTRY_A, term, definition, *_ENTRY_C))

    assert term[0] in texts
    assert definition[0] in texts


def test_two_column_reference_page_is_left_as_it_was(monkeypatch: pytest.MonkeyPatch) -> None:
    # Two columns of entries with hanging indents: the reading order interleaves lines of both
    # columns at one height, so no run of one column's edges forms. The rule changes nothing.
    # No single mutation of the rule drops this test (spec 081 Changelog): the join's own
    # conditions (a column line does not reach the body's right edge; lines at one height are
    # not "the next line") already keep the columns apart -- it pins the outcome, not a guard.
    left, right = (_LEFT, _HANG, 245.0), (260.0, 275.0, 450.0)
    rows = []
    for k, (head, tail) in enumerate(
        (
            ("Ashdown, P., The Quiet Ledgers of the North", "Harbours, Keepers (Tolly Press, 1981)."),
            ("Corvell, A., Counting Ships at Dawn in the Old", "Quay, Fenwick (Marrow House, 2004)."),
            ("Dunmore, K., Why the harbour fees rose twice in", "Winter, Lowmoor (Gull Press, 1999)."),
        )
    ):
        for column, (margin, indent, edge) in enumerate((left, right)):
            rows.append((head + ("" if column == 0 else " "), margin, edge, k * 2 * _PITCH))
            rows.append((tail, indent, edge - 60.0, k * 2 * _PITCH + _PITCH))
    spans = _page()
    for text, x0, x1, offset in rows:
        spans.append(_span(text.strip(), top=_START + offset, x0=x0, x1=x1))
    with_rule = _texts(spans)
    _off(monkeypatch)

    assert with_rule == _texts(spans)
