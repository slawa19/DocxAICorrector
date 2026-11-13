"""Spec 085: where a contents list ends (``extraction._toc_region_end``).

Every condition of the rule has a test here that fails when the condition is removed (mutation
results in ``specs/085-contents-list-extent/spec.md``). All text is invented.
"""

from io import BytesIO
from typing import cast

from docx import Document

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
        _heading("Lanterns and Their Keepers", 1),
        _heading("Night Watches and Signal Fires", 3),
        _sentence("The signal fire"),
        _heading("Notes", 1),
        _sentence("The note"),
    ]


def test_a_long_line_of_sub_section_titles_stays_in_the_contents() -> None:
    # The defect: the run ended at the first line longer than the contents shape, and the rest of
    # the list was narrated. Mutation: walk with the length limit -> the list ends before LONG_ONE.
    assert _marked(_two_level_contents_book()) == [
        "Contents",
        "Preface: Tales of the Tide Keepers",
        "1. A Short History of Harbours",
        LONG_ONE,
        "2. Lanterns and Their Keepers",
        LONG_TWO,
        "Notes",
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
    # No page numbers and no later headings: the candidate run stands, so the length limit still
    # ends the list (mutation: fall back to the whole walk -> the long line is marked).
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
    # The last line holds three titles; only runs of its words name headings. It is the list's
    # last line by evidence (mutation: whole-line matches only -> it is left out).
    paragraphs = [
        _unit("Contents"),
        _unit("The Tide Ledger"),
        _unit("Keepers of the Lamp"),
        _unit("Low Water Notes Index of Harbours"),
        _unit("Follow the Harbour Society"),
        _sentence("The ledger"),
        _heading("The Tide Ledger", 1),
        _heading("Keepers of the Lamp", 1),
        _heading("Notes", 1),
        _heading("Index of Harbours", 1),
    ]

    assert _marked(paragraphs) == ["Contents", "The Tide Ledger", "Keepers of the Lamp", "Low Water Notes Index of Harbours"]


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


def _narration_reasons(document: Document) -> list[tuple[str, str | None]]:
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


def test_narration_drops_the_whole_two_level_list_and_keeps_the_body_heading() -> None:
    document = Document()
    document.add_paragraph("Contents")
    for text in ("Preface: Tales of the Tide Keepers", "1. A Short History of Harbours", LONG_ONE, "Epilogue: Low Water"):
        document.add_paragraph(text)
    document.add_heading("Preface: Tales of the Tide Keepers", level=2)
    document.add_paragraph("The first tide table was kept by hand in a ledger that every harbour master signed.")
    document.add_heading("A Short History of Harbours", level=1)
    document.add_heading("The Merchants: Cargo and Coin", level=3)
    document.add_paragraph("The cargo was weighed twice, once at the quay and once at the warehouse door.")
    document.add_heading("The Pilots: The Answer Lies in the Channel", level=3)
    document.add_paragraph("The channel shifted every winter, and the pilots redrew it every spring.")
    document.add_heading("Epilogue: Low Water", level=1)
    document.add_paragraph("At low water the whole harbour floor could be walked from quay to quay.")

    reasons = _narration_reasons(document)

    assert reasons[:6] == [
        ("Contents", "toc"),
        ("Preface: Tales of the Tide Keepers", "toc"),
        ("1. A Short History of Harbours", "toc"),
        (LONG_ONE, "toc"),
        ("Epilogue: Low Water", "toc"),
        ("Preface: Tales of the Tide Keepers", None),
    ]
    assert all(reason is None for _, reason in reasons[6:])


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
