from __future__ import annotations

from docxaicorrector.pdf_import.logical_import import build_paragraph_units_from_text_spans
from docxaicorrector.pdf_import.text_layer_quality import PdfTextSpan


def _span(
    page: int,
    text: str,
    *,
    top: float,
    bottom: float,
    x0: float = 50,
    x1: float = 450,
    font_size: float = 10,
    bold: bool = False,
    italic: bool = False,
) -> PdfTextSpan:
    return PdfTextSpan(
        page_number=page,
        text=text,
        x0=x0,
        top=top,
        x1=x1,
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


def test_build_paragraph_units_separates_superscript_footnote_marker() -> None:
    spans = [
        _span(1, "Body line establishes the normal document sentence.", top=70, bottom=82, x0=50, x1=430),
        _span(1, "This sentence ends with a citation.", top=100, bottom=112, x0=50, x1=250),
        _span(1, "2", top=101, bottom=106, x0=248, x1=252, font_size=4),
        _span(1, "The following sentence starts a new paragraph.", top=130, bottom=142, x0=50, x1=420),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body", "body", "footnote", "body"]
    assert result.paragraphs[1].text == "This sentence ends with a citation."
    assert result.paragraphs[2].text == "2"
    assert result.paragraphs[2].structural_role == "footnote"


def test_build_paragraph_units_separates_attribution_superscript_footnote_marker() -> None:
    spans = [
        _span(1, "Body line establishes the normal document sentence.", top=70, bottom=82, x0=50, x1=430),
        _span(1, "Kofi Annan, former UN Secretary-General", top=100, bottom=112, x0=50, x1=270),
        _span(1, "28", top=101, bottom=106, x0=268, x1=274, font_size=4),
        _span(1, "The following sentence starts a new paragraph.", top=130, bottom=142, x0=50, x1=420),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body", "body", "footnote", "body"]
    assert result.paragraphs[1].text == "Kofi Annan, former UN Secretary-General"
    assert result.paragraphs[2].text == "28"
    assert result.paragraphs[2].structural_role == "footnote"


def test_build_paragraph_units_keeps_non_superscript_trailing_number_in_body() -> None:
    spans = [
        _span(1, "Body line establishes the normal document sentence.", top=70, bottom=82, x0=50, x1=430),
        _span(1, "Hyman Minsky, 19921", top=100, bottom=112, x0=50, x1=180),
        _span(1, "A real body paragraph resumes here.", top=130, bottom=142, x0=50, x1=350),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body", "body", "body"]
    assert result.paragraphs[1].text == "Hyman Minsky, 19921"


def test_build_paragraph_units_merges_ordered_list_continuation_lines() -> None:
    spans = [
        _span(1, "Body line establishes the normal document sentence.", top=70, bottom=82, x0=50, x1=430),
        _span(1, "1. first item continues toward the right edge", top=100, bottom=112, x0=70, x1=420),
        _span(1, "and finishes on the next physical line", top=114, bottom=126, x0=70, x1=300),
        _span(1, "2. second item is separate", top=128, bottom=140, x0=70, x1=280),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    lists = [paragraph for paragraph in result.paragraphs if paragraph.role == "list"]
    assert len(lists) == 2
    assert lists[0].list_kind == "ordered"
    assert lists[0].text == (
        "1. first item continues toward the right edge and finishes on the next physical line"
    )
    assert lists[1].text == "2. second item is separate"


def test_build_paragraph_units_splits_short_terminal_body_line_at_left_return() -> None:
    spans = [
        _span(1, "A full body line establishes the usual line width for this page.", top=70, bottom=82, x0=50, x1=430),
        _span(1, "Short paragraph ends.", top=100, bottom=112, x0=50, x1=180),
        _span(1, "Next paragraph begins with an uppercase word.", top=114, bottom=126, x0=50, x1=390),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.text for paragraph in result.paragraphs] == [
        "A full body line establishes the usual line width for this page.",
        "Short paragraph ends.",
        "Next paragraph begins with an uppercase word.",
    ]


def test_build_paragraph_units_keeps_leading_chapter_number_with_heading() -> None:
    spans = [
        _span(1, "Prior body sentence closes the previous chapter.", top=70, bottom=82, x0=50, x1=420),
        _span(1, "3 Measuring the Wealth of Nations", top=120, bottom=138, x0=50, x1=360, font_size=16, bold=True),
        _span(1, "What we measure affects what we do.", top=150, bottom=162, x0=50, x1=390),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body", "heading", "body"]
    assert result.paragraphs[1].rendered_text == "## 3 Measuring the Wealth of Nations"


def test_build_paragraph_units_merges_standalone_leading_chapter_number_with_heading() -> None:
    spans = [
        _span(1, "Prior body sentence closes the previous chapter.", top=70, bottom=82, x0=50, x1=420),
        _span(1, "3", top=110, bottom=126, x0=290, x1=301, font_size=16),
        _span(1, "Measuring the Wealth of Nations", top=140, bottom=156, x0=157, x1=437, font_size=16),
        _span(1, "What we measure affects what we do.", top=190, bottom=202, x0=50, x1=390),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body", "heading", "body"]
    assert result.paragraphs[1].rendered_text == "## 3 Measuring the Wealth of Nations"


def test_build_paragraph_units_does_not_promote_small_digit_note_to_heading() -> None:
    spans = [
        _span(1, "A body line establishes the dominant document style.", top=70, bottom=82, x0=50, x1=430),
        _span(1, "19", top=100, bottom=106, x0=300, x1=308, font_size=6),
        _span(1, "The next paragraph resumes ordinary text.", top=130, bottom=142, x0=50, x1=390),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert all(paragraph.role != "heading" for paragraph in result.paragraphs)
    assert any(paragraph.text == "19" for paragraph in result.paragraphs)


def test_build_paragraph_units_detects_body_sized_small_caps_subheading() -> None:
    spans = [
        _span(1, "the subjective nature of the preferences in the", top=100, bottom=112, x0=72),
        _span(1, "economy.", top=114, bottom=126, x0=72),
        _span(
            1,
            "THE MERCANTILISTS: TRADE AND TREASURE",
            top=150,
            bottom=162,
            x0=175,
            font_size=8,
        ),
        _span(1, "Since ancient times, humanity has divided its economic", top=180, bottom=192, x0=72),
        _span(1, "activity into productive and unproductive types.", top=194, bottom=206, x0=72),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == [
        "body",
        "heading",
        "body",
    ]
    assert result.paragraphs[1].text == "THE MERCANTILISTS: TRADE AND TREASURE"


def test_build_paragraph_units_separates_heading_levels_by_style_clusters() -> None:
    spans = [
        _span(1, "Body line one keeps the dominant document style", top=100, bottom=112, x0=50),
        _span(1, "body line two keeps the dominant document style", top=114, bottom=126, x0=50),
        _span(1, "Body line three keeps the dominant document style.", top=128, bottom=140, x0=50),
        _span(1, "PART ONE", top=180, bottom=202, x0=150, font_size=18, bold=True),
        _span(1, "LOCAL ECONOMICS", top=210, bottom=232, x0=160, font_size=18, bold=True),
        _span(1, "Body text resumes with the dominant document style.", top=270, bottom=282, x0=50),
        _span(1, "A Systems Perspective", top=320, bottom=334, x0=180, font_size=10),
        _span(1, "Another body line follows the clustered subheading.", top=360, bottom=372, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == [
        "body",
        "heading",
        "body",
        "heading",
        "body",
    ]
    assert result.paragraphs[1].text == "PART ONE LOCAL ECONOMICS"
    assert result.paragraphs[3].text == "A Systems Perspective"


def test_build_paragraph_units_is_conservative_for_ambiguous_caps_line() -> None:
    spans = [
        _span(1, "The quotation continues across the current line", top=100, bottom=112, x0=50),
        _span(1, "ALDO LEOPOLD", top=114, bottom=126, x0=50),
        _span(1, "without enough layout separation to prove a heading.", top=128, bottom=140, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body"]
    assert "ALDO LEOPOLD" in result.paragraphs[0].text


def test_build_paragraph_units_rejects_long_body_like_heading_candidate() -> None:
    spans = [
        _span(1, "Body style line establishes the normal line length.", top=100, bottom=112, x0=50),
        _span(1, "Another body style line establishes the normal line length.", top=114, bottom=126, x0=50),
        _span(
            1,
            "This Capitalized Line Is Much Longer Than The Document Body Tail And Therefore Is Body Text",
            top=170,
            bottom=182,
            x0=150,
        ),
        _span(1, "Short body line follows after the long fragment.", top=220, bottom=232, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert all(paragraph.role == "body" for paragraph in result.paragraphs)
    assert any("Much Longer" in paragraph.text for paragraph in result.paragraphs)


def test_build_paragraph_units_rejects_mid_sentence_heading_candidate() -> None:
    spans = [
        _span(1, "The body sentence deliberately continues", top=100, bottom=112, x0=50),
        _span(1, "through a line that starts lowercase", top=114, bottom=126, x0=50),
        _span(1, "and ends as ordinary prose.", top=128, bottom=140, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body"]
    assert "starts lowercase" in result.paragraphs[0].text


def test_build_paragraph_units_rejects_epigraph_credit_year_line() -> None:
    spans = [
        _span(1, "Instability is part of the system.", top=100, bottom=112, x0=50),
        _span(1, "Hyman Minsky, 19921", top=150, bottom=162, x0=180),
        _span(1, "A real body paragraph resumes here.", top=190, bottom=202, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body", "body", "body"]
    assert result.paragraphs[1].text == "Hyman Minsky, 19921"


def test_build_paragraph_units_rejects_footnote_citation_tail_candidate() -> None:
    spans = [
        _span(1, "The citation begins in the previous line", top=100, bottom=112, x0=50),
        _span(1, "[online]. cited October 23, 2010]. federalreserve.gov/releases", top=150, bottom=162, x0=130),
        _span(1, "The next paragraph starts normally.", top=190, bottom=202, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert all(paragraph.role == "body" for paragraph in result.paragraphs)
    assert "federalreserve" in " ".join(paragraph.text for paragraph in result.paragraphs)


def test_build_paragraph_units_detects_short_inline_subheading_between_body_lines() -> None:
    spans = [
        _span(1, "The time currency also created stronger", top=100, bottom=112, x0=50),
        _span(1, "community ties.", top=114, bottom=126, x0=50),
        _span(1, "Employment", top=128, bottom=140, x0=50),
        _span(1, "The first LETS systems originated in Canada in northern regions", top=142, bottom=154, x0=50),
        _span(1, "aiming specifically at currency scarcity in areas.", top=156, bottom=168, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == [
        "body",
        "heading",
        "body",
    ]
    assert [paragraph.text for paragraph in result.paragraphs] == [
        "The time currency also created stronger community ties.",
        "Employment",
        "The first LETS systems originated in Canada in northern regions aiming specifically at currency scarcity in areas.",
    ]


def test_build_paragraph_units_does_not_promote_left_margin_bold_sentence_to_heading() -> None:
    spans = [
        _span(1, "Important update continued in the same paragraph", top=100, bottom=112, x0=50, bold=True),
        _span(1, "with normal body text on the next line.", top=114, bottom=126, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body"]
    assert result.paragraphs[0].text == (
        "Important update continued in the same paragraph with normal body text on the next line."
    )


def test_build_paragraph_units_keeps_dash_attribution_out_of_headings() -> None:
    spans = [
        _span(1, "A thoughtful sentence closes the praise.", top=100, bottom=112, x0=50),
        _span(1, "— Jane Example, author of Useful Systems", top=130, bottom=142, x0=150),
        _span(1, "The next paragraph starts normally after the quote.", top=170, bottom=182, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body", "body", "body"]
    assert result.paragraphs[1].text == "— Jane Example, author of Useful Systems"


def test_build_paragraph_units_classifies_figure_line_as_caption_not_heading() -> None:
    spans = [
        _span(1, "FIGURE 2.3. The Corporate Process", top=100, bottom=112, x0=160),
        _span(1, "Normal body text follows the figure caption.", top=140, bottom=152, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["caption", "body"]
    assert result.paragraphs[0].structural_role == "caption"
    assert result.paragraphs[0].style_name == "PDF Caption"


def test_build_paragraph_units_keeps_location_signature_line_out_of_headings() -> None:
    spans = [
        _span(1, "The foreword ends with a short sign-off.", top=100, bottom=112, x0=50),
        _span(1, "Northcote, Australia", top=140, bottom=152, x0=180),
        _span(1, "A regular paragraph starts on the following line.", top=180, bottom=192, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["body", "body", "body"]
    assert result.paragraphs[1].text == "Northcote, Australia"


def test_build_paragraph_units_does_not_keep_glued_toc_heading_as_heading() -> None:
    spans = [
        _span(1, "Preface by Dennis Meadows", top=100, bottom=112, x0=95),
        _span(1, "Foreword by Hunter Lovins", top=114, bottom=126, x0=95),
        _span(
            1,
            "Acknowledgments Introduction: Cities And Economies Conclusion: Toward A Monetary Democracy "
            "Appendix: The Community Currency How-To Manual",
            top=128,
            bottom=140,
            x0=95,
        ),
        _span(1, "Body text starts after the front matter list.", top=180, bottom=192, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert all(paragraph.role == "body" for paragraph in result.paragraphs)
    assert result.paragraphs[0].text.startswith("Preface by Dennis Meadows")


def test_build_paragraph_units_merges_multiline_heading_into_single_heading() -> None:
    spans = [
        _span(1, "Глава восьмая", top=80, bottom=98, font_size=16, bold=True),
        _span(1, "STRATEGIES FOR", top=110, bottom=140, font_size=28, bold=True),
        _span(1, "GOVERNMENTS", top=142, bottom=172, font_size=28, bold=True),
        _span(1, "Money is the lever of power.", top=210, bottom=222, font_size=10),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == [
        "heading",
        "heading",
        "body",
    ]
    chapter_label = result.paragraphs[0]
    merged_heading = result.paragraphs[1]
    assert chapter_label.text == "Глава восьмая"
    assert merged_heading.text == "STRATEGIES FOR GOVERNMENTS"
    assert merged_heading.boundary_rationale == "merged_adjacent_pdf_heading_spans"
    assert merged_heading.heading_level is not None
    assert merged_heading.heading_source == "pdf_text_layer"
    assert merged_heading.origin_raw_texts == ["STRATEGIES FOR", "GOVERNMENTS"]


def test_build_paragraph_units_keeps_separate_headings_with_different_font_size() -> None:
    spans = [
        _span(1, "PART THREE", top=80, bottom=98, font_size=14, bold=True),
        _span(1, "RETHINKING MONEY", top=110, bottom=140, font_size=26, bold=True),
        _span(1, "Body paragraph follows.", top=200, bottom=212, font_size=10),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.text for paragraph in result.paragraphs] == [
        "PART THREE",
        "RETHINKING MONEY",
        "Body paragraph follows.",
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


def test_build_paragraph_units_splits_body_on_first_line_indent_boundary() -> None:
    spans = [
        _span(1, "First paragraph starts here and continues", top=100, bottom=112, x0=64),
        _span(1, "on the next line without a first-line indent.", top=114, bottom=126, x0=50),
        _span(1, "Second paragraph begins with a first-line indent.", top=128, bottom=140, x0=64),
        _span(1, "and then continues on the left margin.", top=142, bottom=154, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.text for paragraph in result.paragraphs] == [
        "First paragraph starts here and continues on the next line without a first-line indent.",
        "Second paragraph begins with a first-line indent. and then continues on the left margin.",
    ]


def test_build_paragraph_units_skips_generic_blank_page_notices() -> None:
    spans = [
        _span(1, "This page intentionally left blank", top=400, bottom=412, font_size=10, italic=True),
        _span(2, "Страница намеренно оставлена пустой", top=400, bottom=412, font_size=10, italic=True),
        _span(3, "Actual body text.", top=150, bottom=162, font_size=10),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert result.report.skipped_blank_page_notice_count == 2
    assert [paragraph.text for paragraph in result.paragraphs] == ["Actual body text."]
