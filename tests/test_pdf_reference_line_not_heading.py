"""Spec 084: the first line of a reference entry set with a hanging indent is not a heading.

A reference list set with a hanging indent puts each entry's first line at the list's margin
and its wrapped lines further right. When the list sits indented from the body column and the
entry is set in title-cased words, the typographic heading path
(``logical_import._looks_like_pdf_heading_candidate``) read the first line as a heading: the
indent and the case are its heading evidence, and the sanity invariant that keeps a line that
cites from becoming a heading (``_looks_like_footnote_or_citation_tail``) read only that one
line, while the entry's year sat on the wrapped line under it. The rule
(``_opens_a_wrapped_citation_entry``) asks five things of such a line, each read off the page:
the next line wraps to the hanging indent of a run of entries; the line directly above is a
wrapped line of the same run, so entries stand before it as well as after it (P -- Codex
acceptance review, round 2); the run is not prose set with a first-line indent (no full line at
the indent runs on at the margin -- round 1); the line ran out of room for the next line's first
word; and the two lines read together as a citation. The first entry of a list stands where a
heading would stand and is left as the importer found it.

What the tests below prove, and how:
  * POSITIVE tests -- the entry line is no longer a heading, and without the rule it is one
    (the anti-vacuum half: each patches the rule off and sees the heading come back);
  * CONDITION tests -- each keeps a real heading a heading because of one condition, and fails
    when that condition is removed from the rule (mutation runs, spec 084 Changelog). Some of
    the shapes are contrived on purpose: their only job is to pin one guard;
  * ROUTING and SCOPE tests -- headings decided by a deterministic rule never reach this one,
    and nothing is compared across a page break;
  * a CONSERVATION test -- the rule changes roles and paragraph boundaries only.
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

# Page geometry: body column x0 50 .. x1 450, 10 pt body type on a 14 pt pitch, so the line
# grouping's first-line-indent step is 0.45 x 14 = 6.3 pt. The reference list sits indented from
# the body column (entries at 70) and wraps to a hanging indent of 14 pt (84).
_LEFT = 50.0
_ENTRY = 70.0
_HANG = 84.0
_PITCH = 14.0
_BODY = 10.0
_LARGER = 11.5
_FULL = 448.0

_PROSE = (
    "The harbour masters kept their accounts in long ledgers that ran for many years at a time.",
    "Every entry recorded a ship, its cargo and the fee that the town took for the mooring.",
    "Over the decades these books grew into a record of the whole coast and its small trades.",
    "Historians who read them later found patterns that the clerks themselves never noticed.",
    "The fees rose in hard winters and fell when the fishing was good and the boats came home.",
    "Some towns kept two sets of books, one for the crown and one for the guild of the port.",
)

# Three invented references whose year falls on the wrapped line, as in the defect.
_ENTRIES = (
    ("Marlow, Edith. The Ledgers of Small Harbours: A Survey (Portsmouth: Tidewater", "Press 1987)"),
    ("Quill, Ansel. Moorings and Tolls of the Northern Coast (Leith: Grey Gull", "Books 1992)"),
    ("Fenwick, Rosa. Salt, Fish and Fees: The Port Towns (Bristol: Harbour Lane", "Publishing 2001)"),
)

Row = tuple[str, float, float, float, bool]


def _span(
    text: str, *, top: float, x0: float, x1: float, size: float = _BODY, bold: bool = False, page: int = 1
) -> PdfTextSpan:
    return PdfTextSpan(
        page_number=page,
        text=text,
        x0=x0,
        top=top,
        x1=x1,
        bottom=top + size * 1.2,
        page_height=800,
        font_name="SourceSerif-Bold" if bold else "SourceSerif",
        font_size=size,
        is_bold=bold,
        is_italic=False,
    )


def _prose(start: float, *, page: int = 1) -> list[PdfTextSpan]:
    """Six lines of running body text: the body size, margins and leading of the page."""
    return [
        _span(text, top=start + index * _PITCH, x0=_LEFT, x1=440.0 if index % 3 != 2 else 300.0, page=page)
        for index, text in enumerate(_PROSE)
    ]


def _page(rows: list[Row], *, gap_before: float = _PITCH * 1.5, page: int = 1) -> list[PdfTextSpan]:
    """Running prose, a gap, then the rows (text, x0, x1, size, bold), each a line of its size
    below the last."""
    spans = _prose(40.0, page=page)
    top = spans[-1].top + _PITCH + gap_before
    for text, x0, x1, size, bold in rows:
        spans.append(_span(text, top=top, x0=x0, x1=x1, size=size, bold=bold, page=page))
        top += size * 1.4
    return spans


def _entry_rows(*, size: float = _BODY, bold: bool = False, x0: float = _ENTRY, hang: float = _HANG) -> list[Row]:
    rows: list[Row] = []
    for first, wrapped in _ENTRIES:
        rows.append((first, x0, _FULL, size, bold))
        rows.append((wrapped, hang, hang + 70.0, size, bold))
    return rows


def _paragraphs(spans: list[PdfTextSpan]) -> list[ParagraphUnit]:
    return build_paragraph_units_from_text_spans(spans).paragraphs


def _headings(spans: list[PdfTextSpan]) -> list[str]:
    return [paragraph.text or "" for paragraph in _paragraphs(spans) if paragraph.role == "heading"]


def _rule_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logical_import, "_opens_a_wrapped_citation_entry", lambda *args, **kwargs: False)


def _entry_headings(headings: list[str]) -> list[str]:
    return [text for text in headings if any(first[:12] in text for first, _ in _ENTRIES)]


def _later_entry_headings(headings: list[str]) -> list[str]:
    """Headings among the entries after the first: only those stand between entries (P)."""
    return [text for text in headings if any(first[:12] in text for first, _ in _ENTRIES[1:])]


def _first_entry_headings(headings: list[str]) -> list[str]:
    return [text for text in headings if _ENTRIES[0][0][:12] in text]


def _nonspace(texts: list[str]) -> Counter[str]:
    return Counter(char for text in texts for char in text if not char.isspace())


# --- positive: the entry line is not a heading ----------------------------------------------


def test_indented_reference_entry_in_title_case_is_not_a_heading(monkeypatch: pytest.MonkeyPatch) -> None:
    # The defect's form: body size, plain face, the list indented from the body column. The
    # entries after the first stand between entries and are not headings; the first stands at
    # the top of its list, where a heading would stand, and is left as the importer found it
    # (the price of the position condition P, spec 084 Non-goals).
    spans = _page(_entry_rows())

    headings = _headings(spans)
    assert _later_entry_headings(headings) == []

    first_with_rule = _first_entry_headings(headings)
    _rule_off(monkeypatch)
    headings_off = _headings(spans)
    assert len(_entry_headings(headings_off)) == len(_ENTRIES)
    assert first_with_rule == _first_entry_headings(headings_off)


def test_reference_list_in_a_heavier_face_is_not_a_heading(monkeypatch: pytest.MonkeyPatch) -> None:
    spans = _page(_entry_rows(bold=True))

    assert _later_entry_headings(_headings(spans)) == []

    _rule_off(monkeypatch)
    assert _later_entry_headings(_headings(spans))


def test_reference_list_in_a_larger_face_keeps_only_what_main_types(monkeypatch: pytest.MonkeyPatch) -> None:
    # A list set larger than the text around it: here only its first entry is typed a heading
    # even without the rule (the later ones are merged into body by the line grouping), and the
    # first entry stands where a heading would stand, so P leaves it -- the rule changes nothing
    # in this shape. Pinned so that a change is noticed.
    spans = _page(_entry_rows(size=_LARGER, x0=_LEFT, hang=_LEFT + 16.0))

    with_rule = _entry_headings(_headings(spans))
    _rule_off(monkeypatch)
    without_rule = _entry_headings(_headings(spans))

    assert with_rule == without_rule == [_ENTRIES[0][0]]


def test_entry_opening_a_new_page_is_left_and_the_one_under_it_is_not_a_heading(monkeypatch: pytest.MonkeyPatch) -> None:
    # The run lies on one page. An entry at the top of the next page has nothing of its list
    # above it there, so P leaves it as the importer found it; the entry under it is read with
    # the run. Two entries end page 1, two open page 2.
    rows = _entry_rows()
    page_two = [*rows[4:], ("Thorne, Ivo. Tolls, Tides and Tallies of the Southern Shore (Hull: Fen", _ENTRY, _FULL, _BODY, False), ("Press 1979)", _HANG, _HANG + 70.0, _BODY, False)]
    spans = (
        _page(rows[:4])
        + [
            _span(text, top=60.0 + index * _PITCH, x0=x0, x1=x1, page=2)
            for index, (text, x0, x1, _size, _bold) in enumerate(page_two)
        ]
        + _prose(200.0, page=2)
    )

    headings = _headings(spans)
    assert not any("Quill, Ansel" in text or "Thorne, Ivo" in text for text in headings)
    fenwick_with_rule = [text for text in headings if "Fenwick, Rosa" in text]

    _rule_off(monkeypatch)
    headings_off = _headings(spans)
    assert any("Thorne, Ivo" in text for text in headings_off)
    assert fenwick_with_rule == [text for text in headings_off if "Fenwick, Rosa" in text]


def test_condition_position__first_entry_of_a_list_is_not_decided(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pins P. The first entry has prose above it, set off by white space -- where a heading would
    # stand; it is left as the importer found it. Mutation: drop
    # `_follows_a_wrapped_line_of_the_run` -> demoted.
    spans = _page(_entry_rows())

    with_rule = _first_entry_headings(_headings(spans))
    _rule_off(monkeypatch)
    without_rule = _first_entry_headings(_headings(spans))

    assert with_rule
    assert with_rule == without_rule


def test_condition_run_of_two__a_lone_wrapped_entry_is_not_decided_by_the_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    # Known limit, pinned: the hanging indent is a convention of a LIST, so it is read only where
    # the page shows it at least twice (`_HANGING_INDENT_MIN_RUN_ENTRIES`, spec 081). A single
    # wrapped entry -- here under a line at the indent, so that P holds -- is left as the
    # importer found it. Mutation: a minimum of 1 -> demoted.
    spans = _page([("as the old charter of the guild had asked of every port.", _HANG, 330.0, _BODY, False), *_entry_rows()[:2]])

    with_rule = _entry_headings(_headings(spans))
    _rule_off(monkeypatch)
    without_rule = _entry_headings(_headings(spans))

    assert with_rule
    assert with_rule == without_rule


def test_rule_conserves_every_character_and_the_word_order() -> None:
    spans = _page(_entry_rows())
    texts = [paragraph.text or "" for paragraph in _paragraphs(spans)]
    source = [span.text for span in spans]

    assert _nonspace(texts) == _nonspace(source)
    assert " ".join(texts).split() == " ".join(source).split()


def test_demoted_entries_are_not_marked_a_run_of_notes() -> None:
    # Downstream (AGENT_RULES §2): what the lines become must not read as a run of notes, which
    # would take them out of the narration and the prose translation.
    paragraphs = _paragraphs(_page(_entry_rows()))
    marked = _resolve_notes_in_body_positions(paragraphs, [PARAGRAPH_REGION_PROSE] * len(paragraphs))

    assert paragraphs
    assert not marked


# --- real headings stay headings ------------------------------------------------------------


def test_heading_directly_above_a_reference_list_stays_a_heading() -> None:
    # A section title at the list's margin, set tight above the first entry: the line after it
    # is an entry's first line at the margin, not a wrapped line at the indent.
    spans = _page([("Further Reading", _ENTRY, 160.0, _LARGER, True), *_entry_rows()])

    headings = _headings(spans)

    assert "Further Reading" in headings
    assert _entry_headings(headings) == []


def test_condition_hanging_run__full_width_heading_above_prose_that_cites_stays_a_heading() -> None:
    # Pins the hanging-indent condition. A heading that fills the measure, directly above a
    # paragraph whose first line carries a year after a comma: the line ran out of room and the
    # two lines read together cite, but the next line starts at the margin, not at a hanging
    # indent. Mutation: drop `_line_wraps_to_the_hanging_indent` from the rule -> demoted.
    spans = _page(
        [
            ("The Quiet Accounting of the Northern Harbours and Their Patient Clerks", _LEFT, _FULL, _LARGER, False),
            ("In the winter of 1874, the clerks of the northern ports began to keep a second", _LEFT, 440.0, _BODY, False),
            ("ledger for the guild, and the habit spread along the coast within a decade.", _LEFT, 430.0, _BODY, False),
        ]
    )

    assert "The Quiet Accounting of the Northern Harbours and Their Patient Clerks" in _headings(spans)


_INDENTED_PROSE: list[Row] = [
    ("In 1874, the clerks of the northern ports began to keep a second ledger for", _LEFT + 16.0, 440.0, _BODY, False),
    ("the guild, and the habit spread along the coast within a single decade.", _LEFT, 420.0, _BODY, False),
    ("Some towns resisted the change for many years and kept to the old books.", _LEFT + 16.0, 440.0, _BODY, False),
    ("They argued that one ledger was enough for an honest harbour master.", _LEFT, 400.0, _BODY, False),
]
_FULL_HEADING = "The Quiet Accounting of the Northern Harbours and Their Patient Clerks Too"


def _heading_inside_indented_prose(first_line_x1: float, *, one_line_paragraph: bool = True) -> list[PdfTextSpan]:
    """Prose set with a first-line indent; a one-line indented paragraph stands directly above a
    full-width heading (less than a blank line between them), and the first line under the
    heading carries a year after a comma. `first_line_x1` is where the indented first lines
    end: at the measure, or short of it (a ragged edge, which the line-full test misreads)."""
    indent = _LEFT + 16.0
    rows = [
        ("The harbour masters kept their accounts in long ledgers that ran for many", indent, first_line_x1, 0.0),
        ("years at a time and recorded every ship.", _LEFT, 260.0, 0.0),
        ("So it went for a century.", indent, 190.0, 0.0),
        (_FULL_HEADING, _LEFT, _FULL, 7.9),
        ("In 1874, the clerks of the northern ports began to keep a second ledger for", indent, first_line_x1, 0.0),
        ("the guild, and the habit spread along the coast within a single decade.", _LEFT, 420.0, 0.0),
        ("Some towns resisted the change for many years and kept to the old books.", indent, first_line_x1, 0.0),
        ("They argued that one ledger was enough for an honest harbour master.", _LEFT, 400.0, 0.0),
    ]
    if not one_line_paragraph:
        rows = [row for row in rows if row[0] != "So it went for a century."]
    spans = _prose(40.0)
    top = spans[-1].top + _PITCH + 28.0
    for text, x0, x1, extra_above in rows:
        top += extra_above
        spans.append(_span(text, top=top, x0=x0, x1=x1, bold=text == _FULL_HEADING))
        top += _PITCH
    return spans


def test_condition_first_line_indent__heading_between_indented_paragraphs_stays_a_heading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pins N. The heading stands between paragraphs (P holds: a one-line indented paragraph sits
    # directly above it), fills the measure (R), sits in a "run" (H) and reads as a citation with
    # the first prose line (C). What tells the run is prose: a full line at the indent runs on at
    # the margin. Mutation: drop `_run_returns_running_text_to_the_margin` -> demoted.
    spans = _heading_inside_indented_prose(440.0)

    assert _FULL_HEADING in _headings(spans)

    monkeypatch.setattr(logical_import, "_run_returns_running_text_to_the_margin", lambda *args, **kwargs: False)
    assert _FULL_HEADING not in _headings(spans)


def test_residual__heading_between_ragged_indented_paragraphs_is_demoted(monkeypatch: pytest.MonkeyPatch) -> None:
    # KNOWN RESIDUAL, documented (spec 084, "Остаточный риск"): the same page with the indented
    # first lines ending short of the measure. The line-full test then reads none of them as full
    # (the next word "would have fit"), so N does not see prose, and with a one-line indented
    # paragraph directly above a same-size full-width heading whose next line cites, all five
    # conditions hold and the real heading becomes body. Every link of the chain is needed: the
    # same page with full first lines keeps the heading (test above); a heading set off by a
    # blank line, or the first thing after other material, keeps it (P).
    spans = _heading_inside_indented_prose(400.0)

    assert _FULL_HEADING not in _headings(spans)

    _rule_off(monkeypatch)
    assert _FULL_HEADING in _headings(spans)


# --- recorded residual (Codex acceptance review, round 3) ------------------------------------
#
# The rule demotes a real heading exactly when H, P, N, R and C all hold for it: a heading set
# in the size of the text around it, filling the measure, whose line above sits at the indent of
# a run that shows the margin -> indent pair at least twice, in which no full line at the indent
# runs on at the margin, and which reads as a citation together with the line under it. The
# tests below DOCUMENT that outcome on the shapes the review reproduced, so that a change in it
# is noticed; they are not the behaviour the rule aims at. Each also checks the harm class: the
# demoted heading is a body paragraph of the prose region with its whole text, narrated (no
# exclusion reason), not cut and not dropped -- structure is lost, text is not.

_SECOND_HEADING = "The Loud Accounting of the Southern Harbours and Their Hasty Clerks Also"
_QUOTATION_BLOCKS: list[tuple[str, float, float]] = [
    (_FULL_HEADING, _LEFT, _FULL),
    ("In 1874, the clerks of the northern ports began to keep a second ledger,", _LEFT + 16.0, 440.0),
    ("as the guild had asked.", _LEFT + 16.0, 200.0),
    (_SECOND_HEADING, _LEFT, _FULL),
    ("In 1881, the southern ports followed the northern ones in the same habit,", _LEFT + 16.0, 440.0),
    ("though not for long.", _LEFT + 16.0, 180.0),
]


def _quotation_page(
    *, line_above: str | None = None, extra_above_first: float = 0.0, extra_above_second: float = 0.0
) -> list[PdfTextSpan]:
    """Prose, then two blocks "full-width heading -> indented quotation" on one pitch; optionally a
    line at the indent directly above the first heading, and extra white space above a heading
    (7.9 pt makes 9.9 pt of white at 10 pt type -- under one font size, so the lines stay
    consecutive, and enough for the importer to type the heading at all)."""
    spans = _prose(40.0)
    top = spans[-1].top + _PITCH + 28.0
    if line_above is not None:
        spans.append(_span(line_above, top=top, x0=_LEFT + 16.0, x1=260.0))
        top += _PITCH
    for text, x0, x1 in _QUOTATION_BLOCKS:
        if text == _FULL_HEADING:
            top += extra_above_first
        elif text == _SECOND_HEADING:
            top += extra_above_second
        spans.append(_span(text, top=top, x0=x0, x1=x1, bold=text in (_FULL_HEADING, _SECOND_HEADING)))
        top += _PITCH
    return spans


def _assert_demoted_with_text_narrated(
    spans: list[PdfTextSpan], heading: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    paragraphs = _paragraphs(spans)
    demoted = [paragraph for paragraph in paragraphs if paragraph.text == heading]
    assert len(demoted) == 1 and demoted[0].role == "body"
    marked = _resolve_notes_in_body_positions(paragraphs, [PARAGRAPH_REGION_PROSE] * len(paragraphs))
    reason = resolve_narration_exclusion_reason(
        structural_role=demoted[0].structural_role,
        paragraph_role=demoted[0].role,
        region=PARAGRAPH_REGION_PROSE,
        back_matter_section=None,
        in_notes_in_body=paragraphs.index(demoted[0]) in marked,
        text=demoted[0].text or "",
    )
    assert reason is None
    assert _nonspace([paragraph.text or "" for paragraph in paragraphs]) == _nonspace([span.text for span in spans])

    _rule_off(monkeypatch)
    on_main = [paragraph for paragraph in _paragraphs(spans) if paragraph.text == heading]
    assert len(on_main) == 1 and (on_main[0].role, on_main[0].heading_level) == ("heading", 3)


def test_residual__second_heading_after_a_quotation_is_demoted(monkeypatch: pytest.MonkeyPatch) -> None:
    # The review's shape: the line above the second heading is the short last line of the first
    # quotation, at the indent. No first-line-indent prose and no misjudged line is involved.
    spans = _quotation_page(extra_above_second=7.9)

    _assert_demoted_with_text_narrated(spans, _SECOND_HEADING, monkeypatch)


@pytest.mark.parametrize(
    "line_above",
    [
        "1. Keep the harbour books.",  # a one-line list item
        "Figure 3. The harbour books.",  # a caption line set at the indent
        "The lamp burns low, the water turns.",  # a line of verse
        "as the old charter required.",  # the end of a quotation
    ],
)
def test_residual__heading_after_a_line_at_the_indent_is_demoted(
    line_above: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    spans = _quotation_page(line_above=line_above, extra_above_first=7.9)

    _assert_demoted_with_text_narrated(spans, _FULL_HEADING, monkeypatch)


def test_condition_position__full_width_heading_over_ragged_indented_prose_stays_a_heading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Codex acceptance review, round 2, P1: the round-1 shape with the indented first lines
    # ending short of the measure (x1 415) -- N does not see prose there. The heading is the first
    # thing of what follows (white space above it), so P keeps it. Mutation: drop
    # `_follows_a_wrapped_line_of_the_run` -> demoted (the outcome at 2bbd897).
    ragged = [(text, x0, 415.0 if x0 > _LEFT else x1, size, bold) for text, x0, x1, size, bold in _INDENTED_PROSE]
    spans = _page([(_FULL_HEADING, _LEFT, _FULL, _BODY, True), *ragged], gap_before=_PITCH * 2.0)

    assert _FULL_HEADING in _headings(spans)

    monkeypatch.setattr(logical_import, "_follows_a_wrapped_line_of_the_run", lambda *args, **kwargs: True)
    assert _FULL_HEADING not in _headings(spans)


def test_full_width_heading_over_repeated_indented_quotations_stays_a_heading() -> None:
    # Codex acceptance review, round 2: two blocks "heading at the margin -> indented quotation",
    # one size, one pitch, quotations ending short. The first heading is the first thing of what
    # follows; at 2bbd897 it became body.
    second = "The Loud Accounting of the Southern Harbours and Their Hasty Clerks Also"
    spans = _page(
        [
            (_FULL_HEADING, _LEFT, _FULL, _BODY, True),
            ("In 1874, the clerks of the northern ports began to keep a second ledger,", _LEFT + 16.0, 440.0, _BODY, False),
            ("as the guild had asked.", _LEFT + 16.0, 200.0, _BODY, False),
            (second, _LEFT, _FULL, _BODY, True),
            ("In 1881, the southern ports followed the northern ones in the same habit,", _LEFT + 16.0, 440.0, _BODY, False),
            ("though not for long.", _LEFT + 16.0, 180.0, _BODY, False),
        ],
        gap_before=_PITCH * 2.0,
    )

    assert _FULL_HEADING in _headings(spans)


def test_full_width_heading_over_indented_prose_stays_a_heading() -> None:
    # The round-1 shape (full first lines): held by both N and P.
    spans = _page([(_FULL_HEADING, _LEFT, _FULL, _BODY, True), *_INDENTED_PROSE], gap_before=_PITCH * 2.0)

    assert _FULL_HEADING in _headings(spans)


def test_full_width_heading_over_a_one_line_paragraph_then_indented_prose_stays_a_heading() -> None:
    # A variant of the review's shape: the first paragraph is one short line, so the line under
    # the heading never runs on; the paragraphs after it do.
    spans = _page(
        [
            (_FULL_HEADING, _LEFT, _FULL, _BODY, True),
            ("In 1874, the clerks began a second ledger.", _LEFT + 16.0, 280.0, _BODY, False),
            *_INDENTED_PROSE[2:],
            *_INDENTED_PROSE[:2],
        ],
        gap_before=_PITCH * 2.0,
    )

    assert _FULL_HEADING in _headings(spans)


def test_full_width_heading_over_an_indented_block_quotation_stays_a_heading() -> None:
    spans = _page(
        [
            (_FULL_HEADING, _LEFT, _FULL, _BODY, True),
            ("In 1874, the clerks of the northern ports began to keep a second ledger for", _LEFT + 16.0, 440.0, _BODY, False),
            ("the guild, and the habit spread along the coast within a single decade,", _LEFT + 16.0, 430.0, _BODY, False),
            ("and so the second ledger outlived the guild that had asked for it.", _LEFT + 16.0, 380.0, _BODY, False),
            *_INDENTED_PROSE[2:],
        ],
        gap_before=_PITCH * 2.0,
    )

    assert _FULL_HEADING in _headings(spans)


def test_full_width_heading_over_a_numbered_list_stays_a_heading() -> None:
    spans = _page(
        [
            (_FULL_HEADING, _LEFT, _FULL, _BODY, True),
            ("1. In 1874, the clerks of the northern ports began to keep a second", _LEFT, 440.0, _BODY, False),
            ("ledger for the guild of the port.", _LEFT + 16.0, 260.0, _BODY, False),
            ("2. In 1881, the southern ports followed, though not all of", _LEFT, 430.0, _BODY, False),
            ("them kept it for long.", _LEFT + 16.0, 200.0, _BODY, False),
        ],
        gap_before=_PITCH * 2.0,
    )

    assert _FULL_HEADING in _headings(spans)


def test_short_heading_over_indented_prose_that_cites_stays_a_heading() -> None:
    # The same prose under a short heading: held by the first-line-indent test and by R.
    spans = _page([("The Harbour Accounts", _LEFT, 170.0, _BODY, True), *_INDENTED_PROSE], gap_before=_PITCH * 2.0)

    assert "The Harbour Accounts" in _headings(spans)


def test_condition_ran_out_of_room__author_label_over_a_hanging_list_is_not_decided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pins the line-full condition. A list set with a hanging indent in which an author's name
    # stands at the margin as a label over the works at the indent: the name line ended short,
    # for a reason of its own, so the rule does not decide it, although the run is a hanging one,
    # the second name stands under a wrapped line of the first author's works (P) and the name
    # plus the first work read as a citation. Mutation: drop `_entry_line_ran_out_of_room` ->
    # demoted.
    rows: list[Row] = [
        ("Edith Marlow", _ENTRY, 140.0, _BODY, False),
        ("The Ledgers of Small Harbours (Portsmouth: Tidewater Press, 1987).", _HANG, 420.0, _BODY, False),
        ("Moorings and Tolls of the Northern Coast and Its Many Small Ports (Leith:", _HANG, _FULL, _BODY, False),
        ("Grey Gull Books, 1992).", _HANG, 200.0, _BODY, False),
        ("Ansel Quill", _ENTRY, 130.0, _BODY, False),
        ("Salt, Fish and Fees: The Port Towns (Bristol: Harbour Lane, 2001).", _HANG, 400.0, _BODY, False),
    ]
    spans = _page(rows)

    with_rule = [text for text in _headings(spans) if text == "Ansel Quill"]
    _rule_off(monkeypatch)
    without_rule = [text for text in _headings(spans) if text == "Ansel Quill"]

    assert with_rule == ["Ansel Quill"]
    assert with_rule == without_rule


def test_condition_citation__hanging_list_that_does_not_cite_keeps_its_headings(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pins the citation condition. The defect's list (indented, title case, hanging indent), but
    # no entry carries a year, an address or a trailing comma on either line: geometry alone does
    # not decide, and the importer's typing is kept. Mutation: drop
    # `_looks_like_footnote_or_citation_tail` from the rule -> demoted.
    rows: list[Row] = []
    for first, wrapped in zip((first for first, _ in _ENTRIES), ("Press of the North)", "Books of the Coast)", "Lane Publishing)")):
        rows.append((first, _ENTRY, _FULL, _BODY, False))
        rows.append((wrapped, _HANG, _HANG + 70.0, _BODY, False))
    spans = _page(rows)

    with_rule = _later_entry_headings(_headings(spans))
    _rule_off(monkeypatch)
    without_rule = _later_entry_headings(_headings(spans))

    assert with_rule
    assert with_rule == without_rule


def test_condition_position_at_the_indent__heading_under_a_paragraph_end_stays_a_heading() -> None:
    # Pins that P wants the line above AT THE INDENT. The ragged page of the residual, but the
    # heading stands directly under the last line of a paragraph, which runs at the margin: the
    # line above belongs to the run but is not the wrapped line of an entry. Mutation: accept a
    # line above at either edge -> demoted.
    spans = _heading_inside_indented_prose(400.0, one_line_paragraph=False)

    assert _FULL_HEADING in _headings(spans)


# --- routing and scope ----------------------------------------------------------------------


def _forbid_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> bool:
        raise AssertionError("a deterministic heading reached the spec 084 rule")

    monkeypatch.setattr(logical_import, "_opens_a_wrapped_citation_entry", _raise)


def test_routing_numbered_section_heading_never_reaches_the_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    _forbid_rule(monkeypatch)
    spans = _page(
        [
            ("4. The Ledgers of the Northern Coast", _LEFT, 260.0, _LARGER, True),
            ("The clerks of the northern ports kept two books for every season of the year.", _LEFT, 440.0, _BODY, False),
        ]
    )

    assert "4. The Ledgers of the Northern Coast" in _headings(spans)


def test_routing_chapter_label_never_reaches_the_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    _forbid_rule(monkeypatch)
    spans = _page(
        [
            ("Chapter 7", 220.0, 280.0, _LARGER, True),
            ("The clerks of the northern ports kept two books for every season of the year.", _LEFT, 440.0, _BODY, False),
        ]
    )

    assert any(text.startswith("Chapter 7") for text in _headings(spans))


def test_chapter_title_naming_a_year_stays_a_heading_above_a_reference_list() -> None:
    # A chapter titled after a period, centred in display type, opening onto a reading list:
    # the line after it starts at the list's margin, left of the title -- no hanging indent.
    # (A title that ENDS with the year is read as a contents row with a page number before this
    # rule is ever asked -- a separate limit of `_looks_like_toc_entry`, spec 084 Non-goals.)
    spans = _page(
        [
            ("The Long Winter of 1929 in the Harbour Ledgers", 130.0, 380.0, 18.0, True),
            *_entry_rows(),
        ]
    )

    headings = _headings(spans)

    assert "The Long Winter of 1929 in the Harbour Ledgers" in headings
    assert _entry_headings(headings) == []


def test_scope_entry_wrapping_across_a_page_break_is_not_decided_by_the_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    # Known limit, pinned: the margins of facing pages differ, so the run is read on one page
    # only. An entry whose wrapped line falls on the next page is left as the importer found it.
    # Two whole entries above it on page 1, so a run that let the next page in would count it.
    # Mutation: look the run up with the next page's line in it -> demoted.
    first, wrapped = _ENTRIES[2]
    spans = (
        _page(_entry_rows()[:5])
        + [
            _span(wrapped, top=60.0, x0=_HANG, x1=_HANG + 70.0, page=2),
            _span("Thorne, Ivo. Tolls, Tides and Tallies of the Southern Shore (Hull: Fen", top=74.0, x0=_ENTRY, x1=_FULL, page=2),
            _span("Press 1979)", top=88.0, x0=_HANG, x1=_HANG + 70.0, page=2),
        ]
        + _prose(200.0, page=2)
    )

    with_rule = [text for text in _headings(spans) if first[:12] in text]
    _rule_off(monkeypatch)
    without_rule = [text for text in _headings(spans) if first[:12] in text]

    assert with_rule
    assert with_rule == without_rule
