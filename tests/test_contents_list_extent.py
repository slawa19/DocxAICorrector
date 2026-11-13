"""Spec 085: where a contents list ends (``extraction._toc_region_end``).

What ships is the part that cannot drop text: compared with the pass before this spec, a region
only ever ends EARLIER where that pass recognised the header, and only a header set in emphasis
markers adds a region. Every condition of the rule has a test here that fails when the condition
is removed (mutation results in ``specs/085-contents-list-extent/spec.md``). All text is invented.
"""

import random
from io import BytesIO
from typing import cast

from docx import Document
from docx.document import Document as DocxDocument
from docx.shared import Pt

import docxaicorrector.document.extraction as extraction
from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.document.semantic_blocks import build_editing_jobs, build_semantic_blocks

TOC = {"toc_header", "toc_entry"}


def _unit(text: str, *, role: str = "body", level: int | None = None) -> ParagraphUnit:
    return ParagraphUnit(text=text, role=role, structural_role=role, heading_level=level)


def _heading(text: str, level: int = 2) -> ParagraphUnit:
    return _unit(text, role="heading", level=level)


def _image() -> ParagraphUnit:
    return _unit("[[DOCX_IMAGE_img_001]]", role="image")


def _sentence(subject: str) -> ParagraphUnit:
    return _unit(f"{subject} was kept by hand in a ledger that every harbour master signed at dusk.")


def _marked(paragraphs: list[ParagraphUnit]) -> list[str]:
    extraction._annotate_toc_region_candidates(paragraphs)
    return [paragraph.text for paragraph in paragraphs if paragraph.structural_role in TOC]


# Sub-section titles of one chapter typeset as ONE paragraph: longer than the contents shape
# allows (more than 16 words), no sentence end.
LONG_ONE = (
    "The Merchants: Cargo and Coin The Pilots: The Answer Lies in the Channel "
    "The Engineers: Value in Stone and Timber Along the Quay"
)
LONG_TWO = (
    "Night Watches and Signal Fires The Keepers Guild Comes into Being "
    "Measuring the Light Something Odd About the Lamp Rooms"
)


def _two_level_contents_book() -> list[ParagraphUnit]:
    return [
        _unit("Contents"),
        _unit("Preface: Tales of the Tide Keepers"),
        _unit("1. A Short History of Harbours", role="list"),
        _unit(LONG_ONE),
        _unit("2. Lanterns and Their Keepers", role="list"),
        _unit(LONG_TWO),
        _unit("Notes"),
        _heading("Preface: Tales of the Tide Keepers"),
        _sentence("The first tide table"),
        _heading("A Short History of Harbours", 1),
        _heading("The Merchants: Cargo and Coin", 3),
        _sentence("The cargo"),
        _heading("The Pilots: The Answer Lies in the Channel", 3),
        _sentence("The channel"),
        _heading("The Engineers: Value in Stone and Timber Along the Quay", 3),
        _sentence("The quay"),
        _heading("Lanterns and Their Keepers", 1),
        _heading("Night Watches and Signal Fires", 3),
        _sentence("The signal fire"),
        _heading("The Keepers Guild Comes into Being", 3),
        _heading("Measuring the Light", 3),
        _heading("Something Odd About the Lamp Rooms", 3),
        _sentence("The lamp room"),
        _heading("Notes", 1),
        _sentence("The note"),
    ]


def test_a_line_longer_than_the_contents_shape_is_never_carried() -> None:
    # Owner's decision of 2026-11-13: a run of sub-section titles typeset as one paragraph ends the
    # list as it did before this spec, even when later headings account for every title in it --
    # carrying long lines took prose or a real heading in shapes the earlier pass narrates.
    assert _marked(_two_level_contents_book()) == [
        "Contents",
        "Preface: Tales of the Tide Keepers",
        "1. A Short History of Harbours",
    ]


def test_a_heading_that_repeats_an_entry_ends_the_list() -> None:
    # The body's first heading repeats an entry: the section itself has begun. No line names a
    # later heading here, so only the repeat ends the list (mutation: the heading is marked).
    paragraphs = [
        _unit("Contents"),
        _unit("Alpha Soundings"),
        _unit("Beta Soundings"),
        _heading("Alpha Soundings"),
        _unit("by Ilsa Varn"),
        _sentence("The sounding line"),
    ]

    assert _marked(paragraphs) == ["Contents", "Alpha Soundings", "Beta Soundings"]
    assert (paragraphs[3].role, paragraphs[3].structural_role) == ("heading", "heading")


def test_a_plain_line_repeating_an_entry_does_not_end_the_list() -> None:
    # Two parts, each with its own "Introduction": a repeated LINE is an entry, only a repeated
    # HEADING is the section itself (mutation: any repeat stops -> the second part is cut off).
    paragraphs = [
        _unit("Contents"),
        _unit("Part One"),
        _unit("Introduction"),
        _unit("The Tide Ledger"),
        _unit("Part Two"),
        _unit("Introduction"),
        _unit("Keepers of the Lamp"),
        _sentence("The ledger"),
        _heading("Introduction", 2),
        _heading("The Tide Ledger", 1),
        _heading("Introduction", 2),
        _heading("Keepers of the Lamp", 1),
    ]

    assert _marked(paragraphs) == [
        "Contents",
        "Part One",
        "Introduction",
        "The Tide Ledger",
        "Part Two",
        "Introduction",
        "Keepers of the Lamp",
    ]


def test_title_page_lines_after_a_list_without_page_numbers_stay_outside() -> None:
    # Spec 080's shape without a picture: a list without page numbers, then the organisation's
    # letterhead, its patron line and the foreword's title, all short. The run took them all; the
    # list now ends at its last line naming a later heading (mutation: drop that evidence -> all
    # four are marked).
    paragraphs = [
        _unit("Contents"),
        _unit("Why this Ledger, Now?"),
        _unit("Tides Explained"),
        _unit("About the Harbour Society"),
        _heading("THE HARBOUR SOCIETY: NORTHERN CHAPTER", 3),
        _unit("Honorary Warden Ilsa Varn of the Northern Quay"),
        _heading("Telling the Truth about Tides", 2),
        _unit("Introductory remarks to the members"),
        _sentence("The northern quay"),
        _heading("Why this Ledger, Now?", 1),
        _sentence("This ledger"),
        _heading("Tides Explained", 1),
        _sentence("The tide"),
        _heading("About the Harbour Society", 1),
        _sentence("The society"),
    ]

    assert _marked(paragraphs) == [
        "Contents",
        "Why this Ledger, Now?",
        "Tides Explained",
        "About the Harbour Society",
    ]


def test_title_page_lines_after_a_picture_stay_outside_as_before() -> None:
    paragraphs = [
        _unit("Contents"),
        _unit("Why this Ledger, Now?"),
        _unit("Tides Explained"),
        _image(),
        _heading("THE HARBOUR SOCIETY: NORTHERN CHAPTER", 3),
        _unit("Honorary Warden Ilsa Varn of the Northern Quay"),
        _heading("Telling the Truth about Tides", 2),
        _sentence("The northern quay"),
        _heading("Why this Ledger, Now?", 1),
        _sentence("This ledger"),
        _heading("Tides Explained", 1),
    ]

    assert _marked(paragraphs) == ["Contents", "Why this Ledger, Now?", "Tides Explained"]


def test_a_line_naming_no_heading_inside_the_list_stays_in_it() -> None:
    # "Interlude" has no heading of its own in the body; the list does not end there, because a
    # later line still names a later heading.
    paragraphs = [
        _unit("Contents"),
        _unit("The Northern Quay"),
        _unit("Interlude"),
        _unit("The Southern Quay"),
        _heading("The Northern Quay", 1),
        _sentence("The northern quay"),
        _heading("The Southern Quay", 1),
        _sentence("The southern quay"),
    ]

    assert _marked(paragraphs) == ["Contents", "The Northern Quay", "Interlude", "The Southern Quay"]


def test_a_foreword_line_repeating_a_chapter_title_is_not_an_entry() -> None:
    # The foreword (not listed) opens with a line that repeats the first chapter's title. It
    # names that chapter's heading, but out of order: the list already named a heading after it
    # (mutation: count any later heading -> the foreword's title and first line are marked).
    paragraphs = [
        _unit("Contents"),
        _unit("The Tide Ledger"),
        _unit("Keepers of the Lamp"),
        _unit("Foreword"),
        _unit("The Tide Ledger"),
        _sentence("This foreword"),
        _heading("The Tide Ledger", 1),
        _sentence("The ledger"),
        _heading("Keepers of the Lamp", 1),
        _sentence("The lamp"),
    ]

    assert _marked(paragraphs) == ["Contents", "The Tide Ledger", "Keepers of the Lamp"]


def test_a_contents_list_at_the_end_of_the_book_is_left_as_the_run_found_it() -> None:
    # Every heading stands BEFORE the list, so no line names a later one: no evidence, and the
    # run stands as before this spec, including the last line that has no heading (mutation:
    # count headings before the line -> the list ends at "Keepers of the Lamp").
    paragraphs = [
        _heading("The Tide Ledger", 1),
        _sentence("The ledger"),
        _heading("Keepers of the Lamp", 1),
        _sentence("The lamp"),
        _unit("Contents"),
        _unit("The Tide Ledger"),
        _unit("Keepers of the Lamp"),
        _unit("Index of Harbours"),
    ]

    assert _marked(paragraphs) == ["Contents", "The Tide Ledger", "Keepers of the Lamp", "Index of Harbours"]


def test_without_evidence_a_long_line_still_ends_the_list() -> None:
    # No page numbers and no later headings: the walk stands, and the length limit ends it.
    paragraphs = [
        _unit("Contents"),
        _unit("The Tide Ledger"),
        _unit("Keepers of the Lamp"),
        _unit(LONG_ONE),
        _sentence("The ledger"),
    ]

    assert _marked(paragraphs) == ["Contents", "The Tide Ledger", "Keepers of the Lamp"]


def test_one_named_line_is_not_enough_evidence_to_cut_the_list() -> None:
    # Only the first entry names a later heading. One line is no evidence for where the list
    # ends (as one page number is none): the run stands (mutation: one is enough -> the list is cut
    # to a single entry and dropped).
    paragraphs = [
        _unit("Contents"),
        _unit("The Tide Ledger"),
        _unit("Of Gulls and Gales"),
        _unit("Low Water"),
        _sentence("The gull"),
        _heading("The Tide Ledger", 1),
        _sentence("The ledger"),
    ]

    assert _marked(paragraphs) == ["Contents", "The Tide Ledger", "Of Gulls and Gales", "Low Water"]


def test_two_contents_lists_each_get_their_own_region() -> None:
    # A short list, then a detailed one under its own header whose part lines are styled as
    # headings and repeat the short list's entries. Only headings AFTER a line count as named:
    # the detailed list's part line does not name the heading it is itself (mutation: headings
    # not after the line count -> each part line names itself, and the list is cut after the
    # last part line, leaving "The Lamp Room" out).
    paragraphs = [
        _unit("Contents"),
        _unit("Part One"),
        _unit("Part Two"),
        _unit("Contents"),
        _heading("Part One", 3),
        _unit("Spring Tides"),
        _heading("Part Two", 3),
        _unit("The Lamp Room"),
        _sentence("The ledger"),
    ]

    extraction._annotate_toc_region_candidates(paragraphs)

    assert [paragraph.structural_role for paragraph in paragraphs] == [
        "toc_header",
        "toc_entry",
        "toc_entry",
        "toc_header",
        "toc_entry",
        "toc_entry",
        "toc_entry",
        "toc_entry",
        "body",
    ]


def test_a_second_contents_header_opens_a_list_of_its_own() -> None:
    # The short list names no heading; the detailed list after the second header does. Without
    # the stop at the second header the first list would run on through it, and the detailed
    # list's evidence would close one region over both (mutation: the second header becomes an
    # entry of the first list).
    paragraphs = [
        _unit("Contents"),
        _unit("Part One"),
        _unit("Part Two"),
        _unit("Contents"),
        _unit("Spring Tides"),
        _unit("The Lamp Room"),
        _sentence("The ledger"),
        _heading("Spring Tides", 1),
        _heading("The Lamp Room", 1),
    ]

    extraction._annotate_toc_region_candidates(paragraphs)

    assert [paragraph.structural_role for paragraph in paragraphs[:7]] == [
        "toc_header",
        "toc_entry",
        "toc_entry",
        "toc_header",
        "toc_entry",
        "toc_entry",
        "body",
    ]


def test_page_numbers_decide_before_named_headings() -> None:
    # A list with page numbers and dotted leaders ends at its last numbered line even when a short
    # line after it names a later heading in order (mutation: named headings first -> the
    # society's name is marked).
    paragraphs = [
        _unit("Contents"),
        _unit("The Tide Ledger ........ 1"),
        _unit("Keepers of the Lamp ........ 29"),
        _unit("Harbour Society"),
        _unit("Ilsa Varn"),
        _sentence("The ledger"),
        _heading("The Tide Ledger", 1),
        _heading("Keepers of the Lamp", 1),
        _heading("Harbour Society", 1),
    ]

    assert _marked(paragraphs) == ["Contents", "The Tide Ledger ........ 1", "Keepers of the Lamp ........ 29"]


def test_a_line_holding_several_titles_names_its_headings() -> None:
    # The last line holds three titles and splits into them with nothing left over, in order. It
    # is the list's last line by evidence (mutation: whole-line matches only -> it is left out).
    paragraphs = [
        _unit("Contents"),
        _unit("The Tide Ledger"),
        _unit("Keepers of the Lamp"),
        _unit("Low Water Notes Index of Harbours"),
        _unit("Follow the Harbour Society"),
        _sentence("The ledger"),
        _heading("The Tide Ledger", 1),
        _heading("Keepers of the Lamp", 1),
        _heading("Low Water", 1),
        _heading("Notes", 1),
        _heading("Index of Harbours", 1),
    ]

    assert _marked(paragraphs) == ["Contents", "The Tide Ledger", "Keepers of the Lamp", "Low Water Notes Index of Harbours"]


def test_a_line_only_partly_made_of_later_titles_is_no_evidence() -> None:
    # "Low Water" names no heading: the line holds two later titles, but they do not account for
    # it (mutation: a title occurring inside the line is enough -> it is marked).
    paragraphs = [
        _unit("Contents"),
        _unit("The Tide Ledger"),
        _unit("Keepers of the Lamp"),
        _unit("Low Water Notes Index of Harbours"),
        _sentence("The ledger"),
        _heading("The Tide Ledger", 1),
        _heading("Keepers of the Lamp", 1),
        _heading("Notes", 1),
        _heading("Index of Harbours", 1),
    ]

    assert _marked(paragraphs) == ["Contents", "The Tide Ledger", "Keepers of the Lamp"]


def test_titles_out_of_order_do_not_account_for_a_line() -> None:
    # The line's two titles exist, but in the body the second comes first: a run of section titles
    # follows the body's order (mutation: pieces in any order -> the line is marked).
    paragraphs = [
        _unit("Contents"),
        _unit("The Tide Ledger"),
        _unit("Keepers of the Lamp"),
        _unit("Index of Harbours Notes"),
        _sentence("The ledger"),
        _heading("The Tide Ledger", 1),
        _heading("Keepers of the Lamp", 1),
        _heading("Notes", 1),
        _heading("Index of Harbours", 1),
    ]

    assert _marked(paragraphs) == ["Contents", "The Tide Ledger", "Keepers of the Lamp"]


def test_a_numbered_entry_names_its_unnumbered_heading() -> None:
    # The list numbers its chapters, the body's headings do not carry the number. The last entry
    # is evidence once its ordinal is set aside (mutation: no ordinal -> the list ends one entry
    # early).
    paragraphs = [
        _unit("Contents"),
        _unit("1. The Tide Ledger"),
        _unit("2. Keepers of the Lamp"),
        _unit("3. Low Water"),
        _unit("Ilsa Varn"),
        _sentence("The ledger"),
        _heading("The Tide Ledger", 1),
        _heading("Keepers of the Lamp", 1),
        _heading("Low Water", 1),
    ]

    assert _marked(paragraphs) == ["Contents", "1. The Tide Ledger", "2. Keepers of the Lamp", "3. Low Water"]


def test_a_heading_without_a_letter_names_no_section() -> None:
    # The body sets each chapter number as its own heading. A bare number after the list (a year,
    # a folio) matches the third one, in order; a heading without a letter is no section
    # (mutation: letterless headings count -> the byline and the number are marked).
    paragraphs = [
        _unit("Contents"),
        _unit("The Tide Ledger"),
        _unit("Keepers of the Lamp"),
        _unit("Ilsa Varn"),
        _unit("3"),
        _sentence("The ledger"),
        _heading("1", 1),
        _heading("The Tide Ledger", 1),
        _heading("2", 1),
        _heading("Keepers of the Lamp", 1),
        _heading("3", 1),
        _heading("Low Water", 1),
    ]

    assert _marked(paragraphs) == ["Contents", "The Tide Ledger", "Keepers of the Lamp"]


def test_emphasis_markers_do_not_hide_a_repeated_heading_or_a_header() -> None:
    # The reader renders the same title bold in one place and plain in another, and a bold header
    # as "**Contents**" (mutations: compare with markers -> the heading is marked; read the
    # header with markers -> no list at all).
    paragraphs = [
        _unit("**Contents**"),
        _unit("**Preface** *by Ilsa Varn*"),
        _unit("Keepers of the Lamp"),
        _heading("Preface by Ilsa Varn"),
        _sentence("The preface"),
    ]

    assert _marked(paragraphs) == ["**Contents**", "**Preface** *by Ilsa Varn*", "Keepers of the Lamp"]


def test_a_list_under_a_header_in_emphasis_markers_ends_at_its_last_page_number() -> None:
    # The earlier pass did not read this header, so nothing bounds its region but the rule itself:
    # the page-number end of spec 067 still applies (mutation: no page-number end -> the byline
    # after the list is marked).
    paragraphs = [
        _unit("**Contents**"),
        _unit("The Tide Ledger ........ 1"),
        _unit("Keepers of the Lamp ........ 29"),
        _unit("Ilsa Varn"),
        _sentence("The ledger"),
    ]

    assert _marked(paragraphs) == ["**Contents**", "The Tide Ledger ........ 1", "Keepers of the Lamp ........ 29"]


def _narration_reasons(document: DocxDocument) -> list[tuple[str, str | None]]:
    """(text, narration exclusion reason) of every paragraph, in document order, through the real
    extraction, semantic blocks and audiobook jobs (the phase preparation uses before any model
    has looked at the structure)."""
    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    paragraphs, _ = extraction.extract_document_content_from_docx(buffer)
    phase = "pre_ai_diagnostic"
    blocks = build_semantic_blocks(paragraphs, max_chars=3000, structure_phase=phase)
    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook", structure_phase=phase)
    by_id = {paragraph.paragraph_id: paragraph.text for paragraph in paragraphs}
    return [
        (by_id[paragraph_id], reason)
        for job in jobs
        for paragraph_id, reason in zip(cast(list[str], job["paragraph_ids"]), cast(list, job["narration_exclusion_reasons"]))
    ]


def test_narration_keeps_the_title_page_lines_after_a_list_without_page_numbers() -> None:
    document = Document()
    document.add_paragraph("Contents")
    for text in ("Why this Ledger, Now?", "Tides Explained", "About the Harbour Society"):
        document.add_paragraph(text)
    document.add_heading("THE HARBOUR SOCIETY: NORTHERN CHAPTER", level=3)
    document.add_paragraph("Honorary Warden Ilsa Varn of the Northern Quay")
    document.add_heading("Telling the Truth about Tides", level=2)
    document.add_paragraph("We do not tell the truth about tides, yet every harbour keeps a ledger of them.")
    document.add_heading("Why this Ledger, Now?", level=1)
    document.add_paragraph("This ledger was opened in a hard winter.")
    document.add_heading("Tides Explained", level=1)
    document.add_paragraph("The tide turns twice a day.")
    document.add_heading("About the Harbour Society", level=1)
    document.add_paragraph("The society was founded by pilots.")

    reasons = _narration_reasons(document)

    assert reasons[:8] == [
        ("Contents", "toc"),
        ("Why this Ledger, Now?", "toc"),
        ("Tides Explained", "toc"),
        ("About the Harbour Society", "toc"),
        ("THE HARBOUR SOCIETY: NORTHERN CHAPTER", None),
        ("Honorary Warden Ilsa Varn of the Northern Quay", None),
        ("Telling the Truth about Tides", None),
        ("We do not tell the truth about tides, yet every harbour keeps a ledger of them.", None),
    ]


# Codex acceptance review of spec 085 (2026-11-13), finding 1: a single word of a later heading
# ("Notes") inside prose or inside a real heading made that paragraph a contents entry.
CODEX_PROSE = (
    "The first volume brings together the records of the harbour and the voices of those who "
    "lived there and asks why these Notes matter?"
)
CODEX_LONG_HEADING = (
    "Notes on the Lives and Work of the Harbour Keepers Along the Entire Coast During the Long Winter"
)
CODEX_DEDICATION = (
    "For the keepers of the northern lights who stood their watch through every winter storm and "
    "never once let the lamp go dark for want of oil or courage"
)


def _codex_book(between: list[tuple[str, int | None]], entries: tuple[str, ...], headings: tuple[str, ...]) -> DocxDocument:
    """Codex's shapes as a DOCX. The header is a heading and each line after the list is set in its
    own size, so that the paragraph-boundary normaliser keeps them apart as the review's function
    calls did (a size change refuses a merge, spec 080)."""
    document = Document()
    document.add_heading("Contents", level=1)
    for entry in entries:
        document.add_paragraph(entry)
    for size, (text, level) in enumerate(between, start=8):
        if level is None:
            document.add_paragraph().add_run(text).font.size = Pt(size)
        else:
            document.add_heading(text, level=level)
    document.add_paragraph("The account begins.")
    for heading in headings:
        document.add_heading(heading, level=1)
        document.add_paragraph(f"The chapter on {heading.lower()} begins with the tide tables of the quay.")
    return document


def test_prose_holding_one_word_of_a_later_heading_stays_narrated() -> None:
    reasons = dict(
        _narration_reasons(
            _codex_book([("Foreword", 2), (CODEX_PROSE, None)], ("Harbours", "Tides Notes"), ("Harbours", "Tides", "Notes"))
        )
    )

    assert reasons["Foreword"] is None
    assert reasons[CODEX_PROSE] is None


def test_a_long_heading_holding_one_word_of_a_later_heading_stays_narrated() -> None:
    reasons = dict(
        _narration_reasons(
            _codex_book([(CODEX_LONG_HEADING, 2)], ("Harbours", "Tides Notes"), ("Harbours", "Tides", "Notes"))
        )
    )

    assert reasons[CODEX_LONG_HEADING] is None


def test_a_year_in_the_front_matter_is_not_a_page_number_of_the_contents() -> None:
    # Codex round 1, finding 2: on an earlier version of this branch the walk ran through a long
    # dedication to a copyright line whose year read as a page number. Main shape ends the walk at it.
    reasons = dict(
        _narration_reasons(
            _codex_book(
                [("Foreword", 2), (CODEX_DEDICATION, None), ("Copyright Harbour Society 2026", None)],
                ("Harbours .... 1", "Tides .... 29"),
                ("Harbours", "Tides"),
            )
        )
    )

    assert reasons["Tides .... 29"] == "toc"
    assert reasons["Foreword"] is None
    assert reasons[CODEX_DEDICATION] is None
    assert reasons["Copyright Harbour Society 2026"] is None


# Codex acceptance review of spec 085, round 2 (2026-11-13).
def _docx(items: list[tuple[str, int | None, float | None]]) -> DocxDocument:
    """A DOCX from ``(text, heading level or None, font size or None)``, in order. Lines after a
    contents list carry their own size so that the paragraph-boundary normaliser keeps them apart
    (a size change refuses a merge, spec 080), as the review's function calls had them."""
    document = Document()
    for text, level, size in items:
        if level is not None:
            document.add_heading(text, level=level)
        elif size is None:
            document.add_paragraph(text)
        else:
            document.add_paragraph().add_run(text).font.size = Pt(size)
    return document


def _foreword_before_the_evidence(entries_before: tuple[str, ...]) -> DocxDocument:
    return _docx(
        [
            ("Contents", 1, None),
            *[(entry, None, None) for entry in entries_before],
            (CODEX_LONG_HEADING, 2, None),
            (CODEX_PROSE, None, 9),
            ("Harbours", None, 10),
            ("Tides", None, 14),
            ("The account begins.", None, None),
            ("Harbours", 1, None),
            ("The chapter on harbours begins with the tide tables of the quay.", None, None),
            ("Tides", 1, None),
            ("The chapter on tides begins with the tide tables of the quay.", None, None),
        ]
    )


def test_a_foreword_with_evidence_only_after_it_stays_narrated() -> None:
    # Codex round 2, finding 2: both lines naming later headings stand AFTER the long heading and
    # the prose. On an earlier version of this branch both were excluded; the walk now ends at the
    # long heading, as before this spec.
    for entries_before in (("Part One", "Part Two"), ()):
        reasons = dict(_narration_reasons(_foreword_before_the_evidence(entries_before)))

        assert reasons[CODEX_LONG_HEADING] is None, entries_before
        assert reasons[CODEX_PROSE] is None, entries_before


def _half_title_after_a_numbered_list(*, numbered: bool = True) -> DocxDocument:
    entries = ("Harbours .... 1", "Tides .... 29") if numbered else ("Harbours", "Tides")
    return _docx(
        [
            ("Contents", 1, None),
            *[(entry, None, None) for entry in entries],
            (CODEX_LONG_HEADING, 2, None),
            ("Copyright Harbour Society 2026", None, 8),
            ("The account begins.", None, None),
            ("Harbours", 1, None),
            ("The chapter on harbours begins with the tide tables of the quay.", None, None),
            ("Tides", 1, None),
            ("The chapter on tides begins with the tide tables of the quay.", None, None),
            (CODEX_LONG_HEADING, 1, None),
            ("The keepers kept their own notes through the winter.", None, None),
        ]
    )


def test_a_long_heading_equal_to_a_later_heading_does_not_carry_the_page_numbers_on() -> None:
    # Codex round 2, finding 3: a long heading set again later (a half-title); on an earlier version
    # of this branch the page-number walk ran through it to a copyright year. The walk now ends at
    # the long heading, as before this spec.
    reasons = _narration_reasons(_half_title_after_a_numbered_list())

    assert reasons[:5] == [
        ("Contents", "toc"),
        ("Harbours .... 1", "toc"),
        ("Tides .... 29", "toc"),
        (CODEX_LONG_HEADING, None),
        ("Copyright Harbour Society 2026", None),
    ]


def test_a_long_line_equal_to_one_later_heading_is_no_contents_evidence() -> None:
    # The mirror of round 2's finding 3 without page numbers: the half-title is longer than the
    # contents shape, so the walk ends at it and it cannot become the list's last evidence.
    reasons = _narration_reasons(_half_title_after_a_numbered_list(numbered=False))

    assert reasons[:4] == [
        ("Contents", "toc"),
        ("Harbours", "toc"),
        ("Tides", "toc"),
        (CODEX_LONG_HEADING, None),
    ]


# Codex acceptance review of spec 085, round 3 (2026-11-13).
SPLIT_HEADING_HEAD = "Notes on the Lives and Work of the Harbour Keepers"
SPLIT_HEADING_TAIL = "Along the Entire Coast During the Long Winter"


def _long_heading_split_later(entries_before: tuple[str, ...]) -> DocxDocument:
    # A long real heading that splits, with nothing left over, into two headings set later.
    return _docx(
        [
            ("Contents", 1, None),
            *[(entry, None, None) for entry in entries_before],
            (CODEX_LONG_HEADING, 2, None),
            ("Copyright Harbour Society 2026", None, 8),
            ("The account begins.", None, None),
            ("Harbours", 1, None),
            ("The chapter on harbours begins with the tide tables of the quay.", None, None),
            ("Tides", 1, None),
            ("The chapter on tides begins with the tide tables of the quay.", None, None),
            (SPLIT_HEADING_HEAD, 1, None),
            ("The keepers kept their own notes through the winter.", None, None),
            (SPLIT_HEADING_TAIL, 1, None),
            ("The coast froze from the first week of the year.", None, None),
        ]
    )


def test_a_long_heading_that_later_headings_account_for_stays_narrated() -> None:
    # Codex round 3, finding 2: on the earlier branch the heading counted as "accounted for" and,
    # with nothing else as evidence, the copyright line after it was excluded with it.
    for entries_before in (("Part One", "Part Two"), ("Harbours", "Tides")):
        reasons = dict(_narration_reasons(_long_heading_split_later(entries_before)))

        assert reasons[CODEX_LONG_HEADING] is None, entries_before
        assert reasons["Copyright Harbour Society 2026"] is None, entries_before


READERS_LETTER = (
    "Dear keepers, after all these winters of storms and quiet nights, will any of you tell us at "
    "last why the northern lamp was never allowed to go dark?"
)


def test_a_readers_letter_and_its_signature_stay_narrated() -> None:
    # Codex round 3: a letter ending in a long question, then a signature equal to a later heading
    # (a biography section of that name), after a list of chapters.
    reasons = dict(
        _narration_reasons(
            _docx(
                [
                    ("Contents", 1, None),
                    ("Harbours", None, None),
                    ("Tides", None, 14),
                    (READERS_LETTER, None, 9),
                    ("Ilsa Varn", None, 12),
                    ("The account begins.", None, None),
                    ("Harbours", 1, None),
                    ("The chapter on harbours begins with the tide tables of the quay.", None, None),
                    ("Tides", 1, None),
                    ("The chapter on tides begins with the tide tables of the quay.", None, None),
                    ("Ilsa Varn", 1, None),
                    ("She kept the northern lamp for forty years.", None, None),
                ]
            )
        )
    )

    assert reasons[READERS_LETTER] is None
    assert reasons["Ilsa Varn"] is None


def test_a_header_inside_a_region_of_the_earlier_pass_ends_no_later_than_that_region() -> None:
    # A second "Contents" line inside a numbered list (a running head kept on the list's second
    # page). The earlier pass took it as an entry and cut the list at its last page number; the
    # list the second header opens has only one numbered line, so without the bound its walk would
    # run on over the byline after it. Bounded, that list is too short to be one and is read aloud
    # -- the safe direction (mutations: no bound, or a bound without the page-number cut -> the
    # byline is marked).
    paragraphs = [
        _unit("Contents"),
        _unit("The Tide Ledger 1"),
        _unit("Keepers of the Lamp 29"),
        _unit("Contents"),
        _unit("Low Water 61"),
        _unit("Ilsa Varn"),
        _sentence("The ledger"),
    ]

    marked = _marked(paragraphs)

    assert "Ilsa Varn" not in marked
    assert marked == ["Contents", "The Tide Ledger 1", "Keepers of the Lamp 29"]


def _marked_before_this_spec(paragraphs: list[ParagraphUnit]) -> set[int]:
    """The contents pass as it was before spec 085 (main @ 1712332), re-stated for the property
    test below: plain header, run of the contents shape, cut at the last page-numbered line."""
    marked: set[int] = set()
    index = 0
    while index < len(paragraphs):
        if paragraphs[index].text.strip().lower() not in {"contents", "содержание"}:
            index += 1
            continue
        end = index + 1
        while end < len(paragraphs) and extraction._is_toc_candidate_paragraph(paragraphs[end]):
            end += 1
        numbered = extraction._page_numbered_positions(paragraphs, start=index + 1, end=end)
        if len(numbered) >= 2:
            end = numbered[-1] + 1
        if end - index >= 3:
            marked.update(range(index, end))
            index = end
            continue
        index += 1
    return marked


_PALETTE = (
    lambda: _unit("Contents"),
    lambda: _unit("**Contents**"),
    lambda: _unit("The Tide Ledger"),
    lambda: _unit("Keepers of the Lamp"),
    lambda: _unit("Low Water 12"),
    lambda: _unit("Spring Tides .... 40"),
    lambda: _unit("Ilsa Varn"),
    lambda: _unit("2026"),
    lambda: _unit(LONG_ONE),
    lambda: _unit(CODEX_LONG_HEADING),
    lambda: _sentence("The ledger"),
    lambda: _image(),
    lambda: _heading("The Tide Ledger", 1),
    lambda: _heading("Keepers of the Lamp", 1),
    lambda: _heading("Low Water", 1),
    lambda: _heading(CODEX_LONG_HEADING, 2),
    lambda: _heading("Ilsa Varn", 2),
)


def test_property_where_the_earlier_pass_saw_a_list_the_region_never_grows() -> None:
    # Over 3000 seeded random documents built from contents lines, page-numbered lines, title-page
    # lines, long lines, sentences, pictures and headings: every paragraph marked now and not
    # before lies under a header set in emphasis markers that the earlier pass did not read; no
    # other paragraph enters a region.
    generator = random.Random(85)
    for _ in range(3000):
        paragraphs = [generator.choice(_PALETTE)() for _ in range(generator.randint(3, 14))]
        before = _marked_before_this_spec([_unit(p.text, role=p.role) for p in paragraphs])
        extraction._annotate_toc_region_candidates(paragraphs)
        now = {position for position, paragraph in enumerate(paragraphs) if paragraph.structural_role in TOC}
        for position in sorted(now - before):
            header = max(
                index for index in range(position + 1) if paragraphs[index].structural_role == "toc_header"
            )
            assert paragraphs[header].text.strip() != paragraphs[header].text.replace("*", "").strip(), [
                p.text for p in paragraphs
            ]
