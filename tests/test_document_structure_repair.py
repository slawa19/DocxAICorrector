import pytest

from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.document.structure_repair import repair_pdf_derived_structure


def _paragraph(index: int, text: str, *, role: str = "body", structural_role: str = "body", paragraph_alignment=None) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role=role,
        structural_role=structural_role,
        source_index=index,
        paragraph_id=f"p{index:04d}",
        paragraph_alignment=paragraph_alignment,
    )


def test_repair_pdf_derived_structure_hints_isolated_bullet_without_merging():
    paragraphs = [
        _paragraph(0, "●"),
        _paragraph(1, "Text of item"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == ["●", "Text of item"]
    assert repaired[0].role == "body"
    assert repaired[0].structural_role == "body"
    assert repaired[1].role == "body"
    assert repaired[1].heuristic_role_hint == "list"
    assert repaired[1].heuristic_list_kind_hint == "unordered"
    assert repaired[1].list_kind is None
    assert report.repaired_bullet_items == 0
    assert report.remaining_isolated_marker_count == 1


def test_repair_pdf_derived_structure_builds_bounded_toc_and_keeps_body_boundary():
    paragraphs = [
        _paragraph(0, "Содержание"),
        _paragraph(1, "Введение .... 1"),
        _paragraph(2, "Заключение .... 29"),
        _paragraph(3, "Марк 13:13", paragraph_alignment="center"),
        _paragraph(4, "Введение"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert repaired[0].structural_role == "body"
    assert repaired[0].heuristic_structural_role_hint == "toc_header"
    assert repaired[1].structural_role == "body"
    assert repaired[1].heuristic_structural_role_hint == "toc_entry"
    assert repaired[2].structural_role == "body"
    assert repaired[2].heuristic_structural_role_hint == "toc_entry"
    assert repaired[3].structural_role == "body"
    assert repaired[4].role == "body"
    assert repaired[4].structural_role == "body"
    assert repaired[4].heuristic_role_hint == "heading"
    assert repaired[4].heuristic_heading_level_hint == 2
    assert report.bounded_toc_regions == 1
    assert report.toc_body_boundary_repairs == 1
    assert report.heading_candidates_from_toc == 1


def test_repair_pdf_derived_structure_splits_compound_toc_tail_from_epigraph_and_heading_start():
    paragraphs = [
        _paragraph(0, "Table of Contents", structural_role="toc_header"),
        _paragraph(1, "Introduction........ 4", structural_role="toc_entry"),
        _paragraph(2, "Conclusion........ 29", structural_role="toc_entry"),
        _paragraph(
            3,
            "Conclusion........ 29 \"You will be hated by all for my name's sake.\" - Mark 13:13 Introduction My grandfather was convinced",
        ),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "Table of Contents",
        "Introduction........ 4",
        "Conclusion........ 29",
        "Conclusion........ 29 \"You will be hated by all for my name's sake.\" - Mark 13:13 Introduction My grandfather was convinced",
    ]
    assert repaired[3].structural_role == "body"
    assert repaired[3].heuristic_structural_role_hint is None
    assert [hint.text for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "Conclusion........ 29",
        '"You will be hated by all for my name\'s sake." - Mark 13:13',
        "Introduction",
        "My grandfather was convinced",
    ]
    assert [hint.structural_role for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "toc_entry",
        "epigraph",
        "body",
        "body",
    ]
    assert [hint.role for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "body",
        "body",
        "heading",
        "body",
    ]
    assert report.toc_body_boundary_repairs >= 1
    assert report.heading_candidates_from_toc >= 1


def test_repair_pdf_derived_structure_hints_split_numbered_list_lead_without_merging():
    paragraphs = [
        _paragraph(0, "4. Daniel 9:27,"),
        _paragraph(1, "11:31 and Matthew 24:15 describe the abomination of desolation."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "4. Daniel 9:27,",
        "11:31 and Matthew 24:15 describe the abomination of desolation.",
    ]
    assert repaired[0].role == "body"
    assert repaired[0].structural_role == "body"
    assert repaired[0].heuristic_role_hint == "list"
    assert repaired[0].heuristic_list_kind_hint == "ordered"
    assert repaired[0].list_kind is None
    assert repaired[1].role == "body"
    assert report.repaired_numbered_items == 0


def test_repair_pdf_derived_structure_splits_heading_prefix_from_numbered_list_start():
    paragraphs = [
        _paragraph(0, "Contents", structural_role="toc_header"),
        _paragraph(1, "Action Steps for Individuals........ 27", structural_role="toc_entry"),
        _paragraph(2, "Action Steps for Nations........ 28", structural_role="toc_entry"),
        _paragraph(3, "Action Steps for Individuals 1. Prepare your spirit for faithful endurance."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "Contents",
        "Action Steps for Individuals........ 27",
        "Action Steps for Nations........ 28",
        "Action Steps for Individuals 1. Prepare your spirit for faithful endurance.",
    ]
    assert repaired[3].role == "body"
    assert repaired[3].structural_role == "body"
    assert [hint.text for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "Action Steps for Individuals",
        "1. Prepare your spirit for faithful endurance.",
    ]
    assert [hint.role for hint in repaired[3].heuristic_embedded_structure_hints] == ["heading", "list"]
    assert [hint.heading_level for hint in repaired[3].heuristic_embedded_structure_hints] == [2, None]
    assert [hint.list_kind for hint in repaired[3].heuristic_embedded_structure_hints] == [None, "ordered"]
    assert report.heading_candidates_from_toc >= 1


def test_repair_pdf_derived_structure_splits_heading_prefix_with_punctuation_variant():
    paragraphs = [
        _paragraph(0, "Contents", structural_role="toc_header"),
        _paragraph(1, "The Rapture........ 7", structural_role="toc_entry"),
        _paragraph(2, "Great Tribulation........ 9", structural_role="toc_entry"),
        _paragraph(3, "The Rapture: why this matters for endurance."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "Contents",
        "The Rapture........ 7",
        "Great Tribulation........ 9",
        "The Rapture: why this matters for endurance.",
    ]
    assert repaired[3].role == "body"
    assert repaired[3].structural_role == "body"
    assert [hint.text for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "The Rapture",
        "why this matters for endurance.",
    ]
    assert [hint.role for hint in repaired[3].heuristic_embedded_structure_hints] == ["heading", "body"]
    assert [hint.heading_level for hint in repaired[3].heuristic_embedded_structure_hints] == [2, None]
    assert report.heading_candidates_from_toc >= 1


def test_repair_pdf_derived_structure_does_not_promote_inline_toc_title_fragment_inside_sentence():
    paragraphs = [
        _paragraph(0, "Contents", structural_role="toc_header"),
        _paragraph(1, "The Mark of the Beast........ 19", structural_role="toc_entry"),
        _paragraph(2, "Is the Mark of the Beast actually a quantum technology?"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "Contents",
        "The Mark of the Beast........ 19",
        "Is the Mark of the Beast actually a quantum technology?",
    ]
    assert repaired[2].role == "body"
    assert report.heading_candidates_from_toc == 0


def test_repair_pdf_derived_structure_accepts_plain_toc_entries_inside_bounded_region():
    paragraphs = [
        _paragraph(0, "Содержание"),
        _paragraph(1, "Введение .... 1"),
        _paragraph(2, "Восхищение"),
        _paragraph(3, "Великая скорбь"),
        _paragraph(4, "Заключение .... 29"),
        _paragraph(5, "Марк 13:13", paragraph_alignment="center"),
        _paragraph(6, "Это обычный абзац после содержания с достаточной длиной."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.structural_role for paragraph in repaired[:5]] == [
        "body",
        "body",
        "body",
        "body",
        "body",
    ]
    assert [paragraph.heuristic_structural_role_hint for paragraph in repaired[:5]] == [
        "toc_header",
        "toc_entry",
        "toc_entry",
        "toc_entry",
        "toc_entry",
    ]
    assert repaired[5].structural_role == "body"
    assert repaired[6].role == "body"
    assert report.bounded_toc_regions == 1


def test_repair_pdf_derived_structure_keeps_standalone_bullet_before_heading_boundary():
    paragraphs = [
        _paragraph(0, "●"),
        _paragraph(1, "Figure Overview", role="heading", structural_role="heading"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == ["●", "Figure Overview"]
    assert repaired[0].role == "body"
    assert repaired[0].structural_role == "body"
    assert report.repaired_bullet_items == 0
    assert report.remaining_isolated_marker_count == 1


def test_repair_pdf_derived_structure_keeps_standalone_number_before_structural_boundary():
    paragraphs = [
        _paragraph(0, "1."),
        _paragraph(1, "Figure 1. Market structure", role="caption", structural_role="caption"),
        _paragraph(2, "2."),
        _paragraph(3, "Section Heading", role="heading", structural_role="heading"),
        _paragraph(4, "3."),
        _paragraph(5, "Contents", role="body", structural_role="toc_header"),
        _paragraph(6, "4."),
        _paragraph(7, "Image placeholder", role="image", structural_role="image"),
        _paragraph(8, "5."),
        _paragraph(9, "Table placeholder", role="table", structural_role="table"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "1.",
        "Figure 1. Market structure",
        "2.",
        "Section Heading",
        "3.",
        "Contents",
        "4.",
        "Image placeholder",
        "5.",
        "Table placeholder",
    ]
    assert repaired[0].role == "body"
    assert repaired[1].role == "caption"
    assert report.repaired_numbered_items == 0
    assert report.remaining_isolated_marker_count == 5


def test_repair_pdf_derived_structure_does_not_infer_toc_from_short_front_matter_without_header():
    paragraphs = [
        _paragraph(0, "Foreword"),
        _paragraph(1, "Author's Note"),
        _paragraph(2, "This edition preserves the original argument without adding a table of contents."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.structural_role for paragraph in repaired] == ["body", "body", "body"]
    assert [paragraph.role for paragraph in repaired] == ["body", "body", "body"]
    assert report.bounded_toc_regions == 0
    assert report.heading_candidates_from_toc == 0
    assert report.applied is False


def test_repair_pdf_derived_structure_keeps_body_prose_with_ellipsis_outside_toc_region():
    paragraphs = [
        _paragraph(0, "He paused... then continued with the same argument in the next sentence."),
        _paragraph(1, "The discussion remains ordinary body prose and not a TOC entry."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "He paused... then continued with the same argument in the next sentence.",
        "The discussion remains ordinary body prose and not a TOC entry.",
    ]
    assert [paragraph.structural_role for paragraph in repaired] == ["body", "body"]
    assert report.bounded_toc_regions == 0
    assert report.applied is False


# --- Spec 080 round 2: the contents sweep stops where the contents end ---------------------------

PNG_BYTES = __import__("base64").b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII="
)


def _effective_role(paragraph: ParagraphUnit) -> str:
    return paragraph.heuristic_structural_role_hint or paragraph.structural_role


def _contents_then_front_matter_document(tmp_path):
    # The shape measured in a translated book (spec 080): a contents header, contents lines of two
    # levels set in two sizes and without page numbers, then an image, an organisation line, a
    # patron line and the title of the foreword (a heading by style), then the foreword's body.
    from docx import Document
    from docx.shared import Pt

    def add(document, text, size, style=None):
        paragraph = document.add_paragraph(style=style)
        run = paragraph.add_run(text)
        run.font.size = Pt(size)
        return paragraph

    document = Document()
    add(document, "Contents", 23.5)
    add(document, "Introduction: the lantern keepers", 14.0)
    add(document, "Chapter I", 10.5)
    add(document, "Why the tides matter", 14.0)
    add(document, "Chapter II", 10.5)
    add(document, "Ledgers and lanterns", 14.0)
    add(document, "Acknowledgements", 14.0)
    image_path = tmp_path / "seal.png"
    image_path.write_bytes(PNG_BYTES)
    document.add_paragraph().add_run().add_picture(str(image_path))
    add(document, "THE HARBOUR SOCIETY — NORTH CHAPTER", 14.0, style="Heading 3")
    add(document, "Honorary Patron Ilsa Varn of Keswick", 14.0)
    add(document, "Keeping the Tide Honest", 16.0, style="Heading 2")
    add(
        document,
        "We do not tell the truth about tides. Yet the tide is at the heart of every harbour, and every "
        "harbour keeps a ledger of it by hand.",
        14.0,
    )
    path = tmp_path / "contents.docx"
    document.save(str(path))
    return path


def test_contents_sweep_does_not_run_over_the_image_and_front_matter_after_the_contents(tmp_path):
    from docxaicorrector.document.extraction import extract_document_content_from_docx

    with open(_contents_then_front_matter_document(tmp_path), "rb") as handle:
        paragraphs, _ = extract_document_content_from_docx(handle)
    by_text = {paragraph.text: paragraph for paragraph in paragraphs}

    assert _effective_role(by_text["Contents"]) == "toc_header"
    for line in (
        "Introduction: the lantern keepers",
        "Chapter I",
        "Why the tides matter",
        "Chapter II",
        "Ledgers and lanterns",
        "Acknowledgements",
    ):
        assert _effective_role(by_text[line]) == "toc_entry", line
    image = next(paragraph for paragraph in paragraphs if paragraph.text.startswith("[[DOCX_IMAGE_"))
    assert (image.role, _effective_role(image)) == ("image", "image")
    for line in ("THE HARBOUR SOCIETY — NORTH CHAPTER", "Honorary Patron Ilsa Varn of Keswick", "Keeping the Tide Honest"):
        assert _effective_role(by_text[line]) not in {"toc_header", "toc_entry"}, line
    assert by_text["Keeping the Tide Honest"].role == "heading"


def _unit(index: int, text: str, *, role: str = "body", structural_role: str = "body", heading_source=None) -> ParagraphUnit:
    paragraph = _paragraph(index, text, role=role, structural_role=structural_role)
    paragraph.heading_source = heading_source
    return paragraph


@pytest.mark.parametrize("role", ["image", "table", "caption"])
def test_contents_sweep_stops_at_a_paragraph_that_is_not_a_line_of_text(role):
    from docxaicorrector.document.structure_repair import _find_bounded_toc_regions

    paragraphs = [
        _unit(0, "Contents"),
        _unit(1, "Chapter I"),
        _unit(2, "Chapter II"),
        _unit(3, "Harbour seal", role=role, structural_role=role),
        _unit(4, "Afterword"),
    ]

    assert _find_bounded_toc_regions(paragraphs) == [(0, 2)]
    assert (paragraphs[3].role, paragraphs[3].heuristic_structural_role_hint) == (role, None)
    assert paragraphs[4].heuristic_structural_role_hint is None


def test_contents_sweep_stops_at_a_heading_styled_by_the_source():
    from docxaicorrector.document.structure_repair import _find_bounded_toc_regions

    paragraphs = [
        _unit(0, "Contents"),
        _unit(1, "Chapter I"),
        _unit(2, "Chapter II"),
        _unit(3, "Keeping the Tide Honest", role="heading", structural_role="heading", heading_source="explicit"),
        _unit(4, "Honorary Patron Ilsa Varn of Keswick"),
    ]

    assert _find_bounded_toc_regions(paragraphs) == [(0, 2)]
    assert (paragraphs[3].role, paragraphs[3].heading_source, paragraphs[3].heuristic_structural_role_hint) == (
        "heading",
        "explicit",
        None,
    )
    assert paragraphs[4].heuristic_structural_role_hint is None


def test_contents_sweep_crosses_a_styled_heading_the_extraction_pass_put_into_the_contents():
    # Chapter lines inside a contents list are often styled as headings; the extraction pass marks
    # them `toc_entry`, and the sweep goes on over them as before.
    from docxaicorrector.document.structure_repair import _find_bounded_toc_regions

    paragraphs = [
        _unit(0, "Contents"),
        _unit(1, "Chapter I"),
        _unit(2, "Chapter II", role="heading", structural_role="toc_entry", heading_source="explicit"),
        _unit(3, "Chapter III"),
    ]

    assert _find_bounded_toc_regions(paragraphs) == [(0, 3)]


def test_contents_sweep_crosses_a_line_only_guessed_to_be_a_heading():
    # A short line the reader only guessed to be a heading is no evidence against the contents.
    from docxaicorrector.document.structure_repair import _find_bounded_toc_regions

    paragraphs = [
        _unit(0, "Contents"),
        _unit(1, "Chapter I"),
        _unit(2, "Chapter II", role="heading", structural_role="heading", heading_source="heuristic"),
        _unit(3, "Chapter III"),
    ]

    assert _find_bounded_toc_regions(paragraphs) == [(0, 3)]


def test_short_lines_after_a_numbered_contents_list_stay_narrated():
    # Codex acceptance review of spec 080 (P2): the extraction pass ends a contents list with page
    # numbers at its last numbered entry; the sweep must not extend the region again over the short
    # lines after it (an organisation name, an author line), which narration would then drop.
    from docx import Document
    from typing import cast

    from docxaicorrector.document.extraction import extract_document_content_from_docx
    from docxaicorrector.document.semantic_blocks import build_editing_jobs, build_semantic_blocks

    document = Document()
    for text in (
        "Contents",
        "Introduction .... 1",
        "Conclusion .... 29",
        "The Harbour Society",
        "Ilsa Varn",
        "We do not tell the truth about tides. Yet the tide is at the heart of every harbour, and every "
        "harbour keeps a ledger of it by hand.",
    ):
        document.add_paragraph(text)
    from io import BytesIO

    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    paragraphs, _ = extract_document_content_from_docx(buffer)
    # The phase preparation uses before any model has looked at the structure
    # (`processing/preparation.py`, `downstream_structure_phase`): structure hints are binding there.
    phase = "pre_ai_diagnostic"
    blocks = build_semantic_blocks(paragraphs, max_chars=3000, structure_phase=phase)
    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook", structure_phase=phase)
    by_id = {paragraph.paragraph_id: paragraph.text for paragraph in paragraphs}
    reasons = {
        by_id[paragraph_id]: reason
        for job in jobs
        for paragraph_id, reason in zip(cast(list[str], job["paragraph_ids"]), cast(list, job["narration_exclusion_reasons"]))
    }

    assert reasons["Introduction .... 1"] == "toc"
    assert reasons["Conclusion .... 29"] == "toc"
    assert reasons["The Harbour Society"] is None
    assert reasons["Ilsa Varn"] is None
