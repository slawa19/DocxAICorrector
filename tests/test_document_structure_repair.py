from document_structure_repair import repair_pdf_derived_structure
from models import ParagraphUnit


def _paragraph(index: int, text: str, *, role: str = "body", structural_role: str = "body", paragraph_alignment=None) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role=role,
        structural_role=structural_role,
        source_index=index,
        paragraph_id=f"p{index:04d}",
        paragraph_alignment=paragraph_alignment,
    )


def test_repair_pdf_derived_structure_merges_isolated_bullet_with_following_text():
    paragraphs = [
        _paragraph(0, "●"),
        _paragraph(1, "Text of item"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == ["- Text of item"]
    assert repaired[0].role == "list"
    assert repaired[0].list_kind == "unordered"
    assert report.repaired_bullet_items == 1
    assert report.remaining_isolated_marker_count == 0


def test_repair_pdf_derived_structure_builds_bounded_toc_and_keeps_body_boundary():
    paragraphs = [
        _paragraph(0, "Содержание"),
        _paragraph(1, "Введение .... 1"),
        _paragraph(2, "Заключение .... 29"),
        _paragraph(3, "Марк 13:13", paragraph_alignment="center"),
        _paragraph(4, "Введение"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert repaired[0].structural_role == "toc_header"
    assert repaired[1].structural_role == "toc_entry"
    assert repaired[2].structural_role == "toc_entry"
    assert repaired[3].structural_role == "body"
    assert repaired[4].role == "heading"
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
        "Conclusion........ 29",
        '"You will be hated by all for my name\'s sake." - Mark 13:13',
        "Introduction",
        "My grandfather was convinced",
    ]
    assert repaired[3].structural_role == "toc_entry"
    assert repaired[4].structural_role == "epigraph"
    assert repaired[5].role == "heading"
    assert repaired[6].role == "body"
    assert report.toc_body_boundary_repairs >= 1
    assert report.heading_candidates_from_toc >= 1


def test_repair_pdf_derived_structure_merges_split_numbered_list_lead_with_following_body():
    paragraphs = [
        _paragraph(0, "4. Daniel 9:27,"),
        _paragraph(1, "11:31 and Matthew 24:15 describe the abomination of desolation."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "4. Daniel 9:27, 11:31 and Matthew 24:15 describe the abomination of desolation.",
    ]
    assert repaired[0].role == "list"
    assert repaired[0].list_kind == "ordered"
    assert report.repaired_numbered_items == 1


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
        "Action Steps for Individuals",
        "1. Prepare your spirit for faithful endurance.",
    ]
    assert repaired[3].role == "heading"
    assert repaired[4].role == "list"
    assert repaired[4].list_kind == "ordered"
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
        "The Rapture",
        "why this matters for endurance.",
    ]
    assert repaired[3].role == "heading"
    assert repaired[4].role == "body"
    assert report.heading_candidates_from_toc >= 1


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


def test_repair_pdf_derived_structure_keeps_standalone_number_before_caption_boundary():
    paragraphs = [
        _paragraph(0, "1."),
        _paragraph(1, "Figure 1. Market structure", role="caption", structural_role="caption"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == ["1.", "Figure 1. Market structure"]
    assert repaired[0].role == "body"
    assert repaired[1].role == "caption"
    assert report.repaired_numbered_items == 0
    assert report.remaining_isolated_marker_count == 1


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
