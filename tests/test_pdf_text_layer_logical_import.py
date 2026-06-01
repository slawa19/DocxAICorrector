from __future__ import annotations

from docxaicorrector.pdf_import.logical_import import build_paragraph_units_from_text_spans
from docxaicorrector.pdf_import.text_layer_quality import PdfTextSpan


def _span(
    page: int,
    text: str,
    *,
    top: float,
    bottom: float,
    font_size: float = 10,
    bold: bool = False,
    italic: bool = False,
) -> PdfTextSpan:
    return PdfTextSpan(
        page_number=page,
        text=text,
        x0=50,
        top=top,
        x1=450,
        bottom=bottom,
        page_height=800,
        font_name="SourceSerif-Bold" if bold else "SourceSerif",
        font_size=font_size,
        is_bold=bold,
        is_italic=italic,
    )


def test_build_paragraph_units_skips_repeated_furniture_and_page_numbers() -> None:
    spans = [
        _span(1, "RUNNING HEADER", top=20, bottom=35, font_size=8),
        _span(1, "1", top=750, bottom=765, font_size=8),
        _span(1, "First body line", top=200, bottom=212),
        _span(1, "continues here.", top=214, bottom=226),
        _span(2, "RUNNING HEADER", top=20, bottom=35, font_size=8),
        _span(2, "2", top=750, bottom=765, font_size=8),
        _span(2, "Second body paragraph.", top=200, bottom=212),
        _span(3, "RUNNING HEADER", top=20, bottom=35, font_size=8),
        _span(3, "3", top=750, bottom=765, font_size=8),
        _span(3, "Third body paragraph.", top=200, bottom=212),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert result.report.skipped_repeated_page_furniture_count == 3
    assert result.report.skipped_page_number_count == 3
    assert result.report.skipped_blank_page_notice_count == 0
    assert [paragraph.text for paragraph in result.paragraphs] == [
        "First body line continues here.",
        "Second body paragraph.",
        "Third body paragraph.",
    ]
    assert all(paragraph.layout_origin == "pdf_text_layer" for paragraph in result.paragraphs)


def test_build_paragraph_units_preserves_heading_list_and_formatting_signals() -> None:
    spans = [
        _span(1, "CHAPTER EIGHT", top=100, bottom=120, font_size=18, bold=True),
        _span(1, "Intro body.", top=150, bottom=162, font_size=10),
        _span(1, "- bullet item", top=190, bottom=202, font_size=10),
        _span(1, "italic body", top=230, bottom=242, font_size=10, italic=True),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == [
        "heading",
        "body",
        "list",
        "body",
    ]
    heading = result.paragraphs[0]
    assert heading.heading_level == 1
    assert heading.heading_source == "pdf_text_layer"
    assert heading.is_bold is True
    assert result.paragraphs[2].list_kind == "bullet"
    assert result.paragraphs[3].is_italic is True
    assert [paragraph.paragraph_id for paragraph in result.paragraphs] == [
        "p0000",
        "p0001",
        "p0002",
        "p0003",
    ]


def test_build_paragraph_units_does_not_merge_toc_entries_into_large_body_blob() -> None:
    spans = [
        _span(1, "CONTENTS", top=100, bottom=120, font_size=18, bold=True),
        _span(1, "Foreword ix", top=150, bottom=162, font_size=10),
        _span(1, "Introduction: From Scarcity to Prosperity 1", top=164, bottom=176, font_size=10),
        _span(1, "PART ONE SCARCITY", top=190, bottom=202, font_size=10),
        _span(1, "1 The Failure of Money: The Competitive Society 11", top=204, bottom=216, font_size=10),
        _span(2, "First normal body line", top=150, bottom=162, font_size=10),
        _span(2, "continues as one paragraph.", top=164, bottom=176, font_size=10),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.text for paragraph in result.paragraphs[:5]] == [
        "CONTENTS",
        "Foreword ix",
        "Introduction: From Scarcity to Prosperity 1",
        "PART ONE SCARCITY",
        "1 The Failure of Money: The Competitive Society 11",
    ]
    assert result.paragraphs[1].structural_role == "toc_entry"
    assert result.paragraphs[2].structural_role == "toc_entry"
    assert result.paragraphs[4].structural_role == "toc_entry"
    assert result.paragraphs[-1].text == "First normal body line continues as one paragraph."


def test_build_paragraph_units_skips_generic_blank_page_notices() -> None:
    spans = [
        _span(1, "This page intentionally left blank", top=400, bottom=412, font_size=10, italic=True),
        _span(2, "Страница намеренно оставлена пустой", top=400, bottom=412, font_size=10, italic=True),
        _span(3, "Actual body text.", top=150, bottom=162, font_size=10),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert result.report.skipped_blank_page_notice_count == 2
    assert [paragraph.text for paragraph in result.paragraphs] == ["Actual body text."]
