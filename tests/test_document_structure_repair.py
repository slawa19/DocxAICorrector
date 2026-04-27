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
