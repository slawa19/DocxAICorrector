from __future__ import annotations

from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.pdf_import.logical_import import (
    build_paragraph_units_from_text_spans,
    _reconcile_structural_headings,
)
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


def _run_span(
    page: int,
    text: str,
    runs: list[tuple[str, bool, bool]],
    *,
    top: float,
    bottom: float,
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
        font_name="SourceSerif",
        font_size=10,
        is_bold=False,
        is_italic=italic,
        runs=tuple(runs),
    )


def test_pdf_emphasis_runs_carry_dehyphenation_and_inline_italics() -> None:
    # Three soft-wrapped lines fuse into one body paragraph. The compound hyphen
    # ("life-"+"threatening") is kept because "lifethreatening" is unattested, while
    # "multi-"+"faceted" is de-hyphenated because "multifaceted" is attested in the
    # trailing paragraph. The italic emphasis on "multi" must survive the hyphen drop.
    spans = [
        _run_span(
            1,
            "The risk is life-",
            [("The risk is ", False, False), ("life-", False, False)],
            top=200,
            bottom=212,
        ),
        _run_span(
            1,
            "threatening and multi-",
            [("threatening and ", False, False), ("multi-", False, True)],
            top=213,
            bottom=225,
        ),
        _run_span(
            1,
            "faceted, he said.",
            [("faceted, he said.", False, False)],
            top=226,
            bottom=238,
        ),
        _run_span(
            1,
            "Truly multifaceted outcomes.",
            [("Truly multifaceted outcomes.", False, False)],
            top=320,
            bottom=332,
        ),
    ]

    result = build_paragraph_units_from_text_spans(spans)
    merged = next(p for p in result.paragraphs if "life" in p.text)

    assert merged.text == "The risk is life-threatening and multifaceted, he said."
    assert "multi faceted" not in merged.text and "multi- faceted" not in merged.text
    # The per-run emission surface reconstructs the paragraph text exactly and keeps
    # the recovered de-hyphenated word italic.
    assert "".join(text for text, _, _ in merged.pdf_emphasis_runs) == merged.text
    assert ("multi", False, True) in merged.pdf_emphasis_runs


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


def test_build_paragraph_units_reattaches_boundary_superscript_footnote_marker() -> None:
    # Rule 1b: a footnote marker that sits AFTER a completed sentence (the body
    # before it ends with terminal punctuation) and BEFORE a fresh sentence is
    # re-bound as a trailing Unicode superscript on the END of that sentence,
    # rather than surviving as a standalone digit paragraph between the two.
    spans = [
        _span(1, "Body line establishes the normal document sentence.", top=70, bottom=82, x0=50, x1=430),
        _span(1, "This sentence ends with a citation.", top=100, bottom=112, x0=50, x1=250),
        _span(1, "2", top=101, bottom=106, x0=248, x1=252, font_size=4),
        _span(1, "The following sentence starts a new paragraph.", top=130, bottom=142, x0=50, x1=420),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    # No standalone footnote-digit paragraph survives; the marker is folded into
    # the tail of the sentence it references, with the sentence body unchanged.
    assert [paragraph.role for paragraph in result.paragraphs] == ["body", "body", "body"]
    assert result.paragraphs[1].text == "This sentence ends with a citation.²"
    assert result.paragraphs[1].text.startswith("This sentence ends with a citation.")
    assert all(paragraph.structural_role != "footnote" for paragraph in result.paragraphs)
    assert all(paragraph.text.strip() != "2" for paragraph in result.paragraphs)


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


def test_infer_heading_level_ranks_numbered_section_above_bare_same_font() -> None:
    from docxaicorrector.pdf_import.logical_import import _paragraph_from_span

    numbered = _paragraph_from_span(
        _span(1, "5. Обесценивание денег", top=100, bottom=112, font_size=10),
        role="heading",
        median_font_size=10.0,
    )
    nested = _paragraph_from_span(
        _span(1, "2.1. Подраздел о рисках", top=100, bottom=112, font_size=10),
        role="heading",
        median_font_size=10.0,
    )
    bare = _paragraph_from_span(
        _span(1, "Определение стоимости", top=100, bottom=112, font_size=10),
        role="heading",
        median_font_size=10.0,
    )
    large_numbered = _paragraph_from_span(
        _span(1, "1. Введение", top=100, bottom=112, font_size=20),
        role="heading",
        median_font_size=10.0,
    )

    # Same (body) font size: the numbered section outranks the bare heading.
    assert numbered.heading_level == 2
    assert nested.heading_level == 2
    assert bare.heading_level == 3
    assert numbered.heading_level < bare.heading_level
    # Numbering must not disturb the larger-font chapter tier (h1 stays h1).
    assert large_numbered.heading_level == 1
    # Role stays "heading" regardless of the level adjustment.
    assert numbered.role == "heading" and numbered.structural_role == "heading"


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


def test_build_paragraph_units_merges_indented_soft_wrap_continuation() -> None:
    # epub->pdf exports indent soft-wrapped continuation lines (justified word
    # groups / hanging indents). The previous line ends mid-sentence (no terminal
    # punctuation) and the continuation starts lowercase, so it must merge even
    # though it is indented far to the right of the line it continues.
    spans = [
        _span(1, "It makes clear that awareness of this Missing Link", top=100, bottom=112, x0=5),
        _span(1, "is an absolute imperative for", top=114, bottom=126, x0=178),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.text for paragraph in result.paragraphs] == [
        "It makes clear that awareness of this Missing Link is an absolute imperative for",
    ]


def test_build_paragraph_units_merges_same_line_split_word_groups() -> None:
    # Justified text can be emitted as several spans on the same visual line
    # (identical top/bottom, increasing x0). They must collapse into one line.
    spans = [
        _span(1, "clear", top=100, bottom=112, x0=5, x1=38),
        _span(1, "that awareness of", top=100, bottom=112, x0=47, x1=169),
        _span(1, "this Missing Link", top=100, bottom=112, x0=178, x1=311),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.text for paragraph in result.paragraphs] == [
        "clear that awareness of this Missing Link",
    ]


def test_build_paragraph_units_merges_soft_wrap_across_page_break() -> None:
    # A sentence that does not finish at the bottom of one page and continues
    # lowercase at the top of the next must merge across the page boundary.
    spans = [
        _span(1, "the gap between money", top=760, bottom=772, x0=20),
        _span(2, "and sustainability lies elsewhere.", top=6, bottom=18, x0=5),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.text for paragraph in result.paragraphs] == [
        "the gap between money and sustainability lies elsewhere.",
    ]


def test_build_paragraph_units_merges_hanging_indent_list_continuation() -> None:
    # A bullet wraps with a hanging indent: the continuation line sits further
    # right than the bullet line and continues it lowercase. It must stay part of
    # the same list item, not split into a separate paragraph.
    spans = [
        _span(1, "- a description of the many problems we may expect from", top=100, bottom=112, x0=5),
        _span(1, "financial systems", top=114, bottom=126, x0=25),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.role for paragraph in result.paragraphs] == ["list"]
    assert result.paragraphs[0].text == (
        "- a description of the many problems we may expect from financial systems"
    )


def test_build_paragraph_units_does_not_over_merge_real_boundaries() -> None:
    # Real boundaries must stay separate even when lines are tightly spaced:
    #  * a sentence-ending line followed by a new capitalised paragraph,
    #  * a heading,
    #  * the start of a new (numbered) list item.
    spans = [
        _span(1, "First paragraph ends with a full stop.", top=100, bottom=112, x0=50),
        _span(1, "Second paragraph clearly starts new.", top=114, bottom=126, x0=50),
        _span(1, "A SHORT HEADING", top=150, bottom=170, x0=50, font_size=18, bold=True),
        _span(1, "1. First numbered list item starts here", top=200, bottom=212, x0=50),
        _span(1, "2. Second numbered list item starts here", top=214, bottom=226, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    texts = [paragraph.text for paragraph in result.paragraphs]
    roles = [paragraph.role for paragraph in result.paragraphs]
    # The two real paragraphs survive as their own, distinct units (not fused).
    assert "First paragraph ends with a full stop." in texts
    assert "Second paragraph clearly starts new." in texts
    assert not any("full stop. Second paragraph" in t for t in texts)
    assert "heading" in roles
    # Both numbered list items survive as their own units (not merged).
    list_texts = [t for t, r in zip(texts, roles) if r == "list"]
    assert any(t.startswith("1.") for t in list_texts)
    assert any(t.startswith("2.") for t in list_texts)


# --- Rule 1: footnote-marker transparency -----------------------------------


def test_build_paragraph_units_merges_prose_across_standalone_footnote_marker() -> None:
    # A superscript footnote digit sits between the two halves of one sentence.
    # The marker must be transparent to the merge: the prose joins across it, the
    # marker survives inline at its original position, and there is no leftover
    # standalone digit paragraph breaking the flow.
    spans = [
        _span(1, "Body text line one with a body sentence", top=100, bottom=112, x0=50, x1=300, font_size=12),
        # superscript marker: small font, raised within the line (sorts after the
        # body line it tail-attaches to), tucked at the right edge of the line.
        _span(1, "12", top=101, bottom=106, x0=302, x1=309, font_size=6),
        _span(1, "evolution which is bound to throw up results", top=120, bottom=132, x0=50, x1=300, font_size=12),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    texts = [paragraph.text for paragraph in result.paragraphs]
    # Single fused body unit, marker kept inline, no standalone "12" paragraph.
    assert texts == [
        "Body text line one with a body sentence 12 evolution which is bound to throw up results",
    ]
    assert all(paragraph.text.strip() != "12" for paragraph in result.paragraphs)
    assert result.paragraphs[0].role == "body"


# --- Rule 1b: sentence-boundary footnote re-attach --------------------------


def test_build_paragraph_units_does_not_reattach_marker_after_heading() -> None:
    # A footnote marker that follows a HEADING (not a completed body sentence)
    # must NOT be re-bound: there is no pending body to attach to, so it is left
    # as its own standalone footnote unit (under-attach is safer than mis-bind).
    spans = [
        _span(1, "CHAPTER SEVEN", top=70, bottom=92, x0=50, x1=260, font_size=18, bold=True),
        _span(1, "7", top=71, bottom=76, x0=262, x1=266, font_size=4),
        _span(1, "A real body paragraph resumes here with a full sentence.", top=120, bottom=132, x0=50, x1=420),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    roles = [paragraph.role for paragraph in result.paragraphs]
    assert "heading" in roles
    # The heading text is not polluted with the marker, and the marker survives
    # as a standalone footnote unit rather than being bound to the heading.
    heading = next(p for p in result.paragraphs if p.role == "heading")
    assert heading.text == "CHAPTER SEVEN"
    standalone = [p for p in result.paragraphs if p.text.strip() == "7"]
    assert standalone, "marker after a heading must stay standalone, not be re-bound"
    assert standalone[0].structural_role == "footnote"


def test_build_paragraph_units_does_not_reattach_marker_after_unterminated_non_continuation() -> None:
    # The body line before the marker does NOT end with terminal punctuation, and
    # the next line does NOT continue it (it is a fresh capitalized sentence, not
    # a lowercase soft-wrap). Neither the mid-sentence inline rule nor the
    # boundary re-attach rule should fire: the marker stays standalone.
    spans = [
        _span(1, "An unterminated trailing fragment without a stop", top=100, bottom=112, x0=50, x1=300, font_size=10),
        _span(1, "9", top=101, bottom=106, x0=302, x1=306, font_size=4),
        _span(1, "Another Independent Sentence Begins Capitalized Here.", top=140, bottom=152, x0=50, x1=400, font_size=10),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    standalone = [p for p in result.paragraphs if p.text.strip() == "9"]
    assert standalone, "marker after an unterminated non-continuation must stay standalone"
    assert standalone[0].structural_role == "footnote"
    # The unterminated fragment is not silently glued to the marker.
    assert any(p.text == "An unterminated trailing fragment without a stop" for p in result.paragraphs)


def test_build_paragraph_units_preserves_footnote_marker_count_on_reattach() -> None:
    # Invariant: re-attaching boundary markers must NEVER lose a marker. The total
    # footnote-marker count (inline-superscript + standalone) is unchanged; only
    # the rendering (folded into a sentence tail vs. its own paragraph) changes.
    spans = [
        _span(1, "First sentence ends cleanly here.", top=70, bottom=82, x0=50, x1=250),
        _span(1, "3", top=71, bottom=76, x0=252, x1=256, font_size=4),
        _span(1, "Second sentence also ends cleanly here.", top=100, bottom=112, x0=50, x1=260),
        _span(1, "4", top=101, bottom=106, x0=262, x1=266, font_size=4),
        _span(1, "Third sentence rounds things out here.", top=130, bottom=142, x0=50, x1=250),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    # Both boundary markers (3, 4) are re-bound as trailing superscripts; none
    # survives as a standalone digit, and both superscripts are present.
    assert all(p.role == "body" for p in result.paragraphs)
    assert all(p.text.strip() not in {"3", "4"} for p in result.paragraphs)
    joined = " ".join(p.text for p in result.paragraphs)
    assert "³" in joined and "⁴" in joined
    # Exactly two markers survive, one per referenced sentence.
    assert sum(joined.count(ch) for ch in ("³", "⁴")) == 2
    assert result.paragraphs[0].text == "First sentence ends cleanly here.³"
    assert result.paragraphs[1].text == "Second sentence also ends cleanly here.⁴"


# --- Rule 2: cross-role continuation merge ----------------------------------


def test_build_paragraph_units_merges_cross_role_soft_wrap_continuation() -> None:
    # The first line is mis-clustered as a caption-like / list-like role at import,
    # but it does not finish its sentence and the next line continues it lowercase.
    # A real caption/list start never begins lowercase mid-sentence, so the two
    # halves must fuse as a single body unit regardless of the role mismatch.
    spans = [
        # Looks like a figure caption (matches caption pattern) but is running prose
        # that does not terminate: it must not block the lowercase continuation.
        _span(1, "Figure 2.2 shows the impact of banking crises on government", top=100, bottom=112, x0=50, x1=300, font_size=10),
        _span(1, "finances over the relevant decade.", top=114, bottom=126, x0=50, x1=300, font_size=10),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert [paragraph.text for paragraph in result.paragraphs] == [
        "Figure 2.2 shows the impact of banking crises on government finances over the relevant decade.",
    ]
    assert result.paragraphs[0].role == "body"


# --- Rule 3: numbered section-heading promotion -----------------------------


def test_build_paragraph_units_promotes_numbered_section_heading() -> None:
    # A standalone "N. Title" line set in a prominent heading font, surrounded by
    # body prose (not part of a numbered run), is a numbered section heading.
    spans = [
        _span(1, "The previous section ends with a full stop.", top=100, bottom=112, x0=50, font_size=10),
        _span(1, "2. Dealing with the Monetary System", top=150, bottom=168, x0=50, font_size=16, bold=True),
        _span(1, "In order to spell out the economic paradigm we operate in.", top=200, bottom=212, x0=50, font_size=10),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    by_text = {paragraph.text: paragraph for paragraph in result.paragraphs}
    heading = by_text["2. Dealing with the Monetary System"]
    assert heading.role == "heading"
    # A promoted numbered heading must not be tagged as an unordered/bullet list.
    assert heading.list_kind is None


def test_build_paragraph_units_does_not_promote_body_font_numbered_list() -> None:
    # A consecutive numbered run set at body font is a genuine ordered list, even
    # when each item is short and followed by body prose. It must stay an ordered
    # list (never promoted to headings, never tagged unordered).
    spans = [
        _span(1, "The four key categories are as follows:", top=100, bottom=112, x0=50, font_size=10),
        _span(1, "1. Respect and care for the community of life", top=120, bottom=132, x0=50, font_size=10),
        _span(1, "2. Ecological integrity", top=134, bottom=146, x0=50, font_size=10),
        _span(1, "3. Social and economic justice", top=148, bottom=160, x0=50, font_size=10),
        _span(1, "4. Democracy, non-violence and peace", top=162, bottom=174, x0=50, font_size=10),
        _span(1, "The reference material for our analysis follows.", top=190, bottom=202, x0=50, font_size=10),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    numbered = [
        paragraph
        for paragraph in result.paragraphs
        if paragraph.text[:2] in {"1.", "2.", "3.", "4."}
    ]
    assert numbered, "expected the numbered items to survive as their own units"
    assert all(paragraph.role == "list" for paragraph in numbered)
    assert all(paragraph.list_kind == "ordered" for paragraph in numbered)
    assert all(paragraph.list_kind != "unordered" for paragraph in numbered)


def test_build_paragraph_units_does_not_promote_numbered_run_at_heading_font() -> None:
    # Even at a prominent font, a *consecutive* numbered run (1., 2., 3.) is an
    # ordered list (e.g. a table of contents chapter list), not a set of section
    # headings. The consecutive-sibling guard must keep them as ordered list items.
    spans = [
        _span(1, "1. A Brief History of Value", top=100, bottom=118, x0=50, font_size=15, bold=True),
        _span(1, "2. The Rise of the Marginalists", top=122, bottom=140, x0=50, font_size=15, bold=True),
        _span(1, "3. Measuring the Wealth of Nations", top=144, bottom=162, x0=50, font_size=15, bold=True),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    roles = [paragraph.role for paragraph in result.paragraphs]
    assert roles == ["list", "list", "list"]
    assert all(paragraph.list_kind == "ordered" for paragraph in result.paragraphs)


def test_build_paragraph_units_keeps_real_bullet_list_when_body_follows() -> None:
    # A genuine bullet list item must not be fused with a following separate body
    # paragraph merely because the item lacks terminal punctuation and the body
    # line begins lowercase (anti-over-merge for explicit-marker list heads).
    # Enough body context so the layout profile estimates a realistic ~14pt line
    # leading; the bullet then sits a full blank line (large gap) above a separate
    # body paragraph, which must not be swallowed as a hanging-indent continuation.
    spans = [
        _span(1, "A first running body line that establishes the document leading here.", top=40, bottom=54, x0=50, x1=430, font_size=10),
        _span(1, "A second running body line that establishes the document leading here.", top=56, bottom=70, x0=50, x1=430, font_size=10),
        _span(1, "A third running body line that establishes the document leading here.", top=72, bottom=86, x0=50, x1=430, font_size=10),
        _span(1, "- bullet item without terminal punctuation", top=120, bottom=134, x0=50, x1=300, font_size=10),
        _span(1, "A separate body paragraph that begins after a blank line.", top=180, bottom=194, x0=50, x1=400, font_size=10),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    roles = [paragraph.role for paragraph in result.paragraphs]
    assert "list" in roles
    bullet = next(p for p in result.paragraphs if p.role == "list")
    assert bullet.text == "- bullet item without terminal punctuation"
    # The separate body paragraph survives as its own body unit (not fused).
    assert any(
        p.role == "body" and p.text == "A separate body paragraph that begins after a blank line."
        for p in result.paragraphs
    )


def _body_context_spans() -> list[PdfTextSpan]:
    # Enough running body so the layout profile estimates a realistic body font
    # size and leading; the chapter detection itself is text-driven (deterministic
    # ``Chapter <roman/number>``), independent of heading typography.
    return [
        _span(1, "A first running body line that establishes the document leading here.", top=40, bottom=54),
        _span(1, "A second running body line that establishes the document leading here.", top=56, bottom=70),
        _span(1, "A third running body line that establishes the document leading here.", top=72, bottom=86),
    ]


def test_build_paragraph_units_promotes_standalone_roman_chapter_number() -> None:
    # A standalone "Chapter VI" number line that carries a heading-typography signal
    # (bold emphasis here) is promoted to a chapter heading. The literal match alone
    # is no longer sufficient (F23): a plain body line reading "Chapter VI" stays body
    # — see test_build_paragraph_units_does_not_promote_plain_body_chapter_line.
    spans = _body_context_spans() + [
        _span(1, "Chapter VI", top=140, bottom=158, x0=50, x1=160, font_size=10, bold=True),
        _span(1, "Body prose that follows the chapter heading.", top=190, bottom=204),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    chapter = next(p for p in result.paragraphs if p.text == "Chapter VI")
    assert chapter.role == "heading"
    assert chapter.heading_level == 1


def test_build_paragraph_units_promotes_chapter_number_with_inline_title() -> None:
    # "Chapter I — Why this report, now?" (number + dash + title) carrying a heading
    # typography signal (bold) is a heading.
    spans = _body_context_spans() + [
        _span(1, "Chapter I — Why this report, now?", top=140, bottom=158, x0=50, x1=300, font_size=10, bold=True),
        _span(1, "Body prose that follows the chapter heading.", top=190, bottom=204),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    chapter = next(p for p in result.paragraphs if p.text.startswith("Chapter I"))
    assert chapter.role == "heading"
    assert chapter.heading_level == 1


def test_build_paragraph_units_promotes_prominent_chapter_line() -> None:
    # The typography signal need not be bold: a "Chapter III" line set at a prominent
    # font relative to body (>= 1.12x) is corroboration enough to promote.
    spans = _body_context_spans() + [
        _span(1, "Chapter III", top=140, bottom=158, x0=50, x1=170, font_size=16, bold=False),
        _span(1, "Body prose that follows the chapter heading.", top=190, bottom=204),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    chapter = next(p for p in result.paragraphs if p.text == "Chapter III")
    assert chapter.role == "heading"
    assert chapter.heading_level == 1


def test_build_paragraph_units_does_not_promote_plain_body_chapter_line() -> None:
    # F23: a "Chapter III" line at plain body font with no emphasis carries no
    # typography signal, so the literal match alone does NOT promote it to a heading.
    spans = _body_context_spans() + [
        _span(1, "Chapter III", top=140, bottom=158, x0=50, x1=170, font_size=10, bold=False),
        _span(1, "Body prose that follows the chapter heading.", top=190, bottom=204),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    chapter = next(p for p in result.paragraphs if p.text == "Chapter III")
    assert chapter.role == "body"
    assert chapter.heading_level is None


def test_build_paragraph_units_does_not_promote_midsentence_chapter_mention() -> None:
    # A mid-sentence mention "…in chapter 3 we saw…" does not start with the word
    # "Chapter" + number, so it is never promoted (stays body).
    spans = _body_context_spans() + [
        _span(1, "As we discussed in chapter 3 we saw the pro-cyclical tendency emerge.", top=140, bottom=154),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    line = next(p for p in result.paragraphs if "in chapter 3 we saw" in p.text)
    assert line.role == "body"


def test_build_paragraph_units_does_not_promote_toc_chapter_entry() -> None:
    # A TOC line "Chapter II ........ 45" (title + trailing page number) is a TOC
    # entry, never a promoted chapter heading.
    spans = _body_context_spans() + [
        _span(1, "Chapter II .................... 45", top=140, bottom=154, x0=50, x1=400),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    line = next(p for p in result.paragraphs if p.text.startswith("Chapter II"))
    assert line.role != "heading"
    assert line.structural_role == "toc_entry"


def test_build_paragraph_units_dehyphenates_soft_wrapped_word() -> None:
    # A single word split across a soft line break ("про-" / "центов") is rejoined
    # whole, dropping the wrap hyphen and inserting no internal space → "процентов".
    # De-hyphenation is corpus-evidence-gated: the solid word "процентов" is attested
    # elsewhere in the document (and no "про-центов" compound is), which is the signal
    # that the line-break hyphen was a soft wrap, not a compound hyphen.
    spans = _body_context_spans() + [
        _span(1, "Годовой отчёт указал, что уровень процентов остаётся высоким.", top=120, bottom=134),
        _span(1, "Отчёт зафиксировал резкое падение на 38 про-", top=140, bottom=154),
        _span(1, "центов за квартал.", top=156, bottom=170),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    merged = next(p for p in result.paragraphs if "падение на 38" in p.text)
    assert "процентов" in merged.text
    assert "про- центов" not in merged.text
    assert "про-центов" not in merged.text


def test_build_paragraph_units_dehyphenates_latin_soft_wrapped_word() -> None:
    # De-hyphenation is language-agnostic: a latin word wrapped at the hyphen
    # ("estab-" / "lished") is rejoined whole → "established" once the solid form is
    # attested elsewhere in the document.
    spans = _body_context_spans() + [
        _span(1, "A quorum was established before the vote proceeded.", top=120, bottom=134),
        _span(1, "The committee had already estab-", top=140, bottom=154),
        _span(1, "lished a working budget.", top=156, bottom=170),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    merged = next(p for p in result.paragraphs if "committee had already" in p.text)
    assert "established" in merged.text
    assert "estab- lished" not in merged.text
    assert "estab-lished" not in merged.text


def test_build_paragraph_units_preserves_wrapped_compound_hyphen() -> None:
    # A genuine hyphenated compound wrapped at its hyphen ("life-" / "threatening")
    # keeps the hyphen — the compound "life-threatening" is attested elsewhere, so it
    # is NOT corrupted into "lifethreatening". The erroneous joining space is still
    # removed ("life- threatening" would be wrong too).
    spans = _body_context_spans() + [
        _span(1, "It was a life-threatening emergency for the whole crew.", top=120, bottom=134),
        _span(1, "Doctors described the wound as life-", top=140, bottom=154),
        _span(1, "threatening but ultimately survivable.", top=156, bottom=170),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    merged = next(p for p in result.paragraphs if "Doctors described" in p.text)
    assert "life-threatening" in merged.text
    assert "lifethreatening" not in merged.text
    assert "life- threatening" not in merged.text


def test_build_paragraph_units_keeps_hyphen_without_soft_wrap_evidence() -> None:
    # Absent positive soft-wrap evidence (neither the solid word nor the compound is
    # attested elsewhere) the hyphen is preserved — under-merge is safer than
    # corrupting a word. The spurious joining space is still removed.
    spans = _body_context_spans() + [
        _span(1, "The treaty relied on a broad inter-", top=140, bottom=154),
        _span(1, "national coalition of partners.", top=156, bottom=170),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    merged = next(p for p in result.paragraphs if "The treaty relied" in p.text)
    assert "inter-national" in merged.text
    assert "inter- national" not in merged.text
    assert "internationalcoalition" not in merged.text


def test_build_paragraph_units_does_not_dehyphenate_number_range() -> None:
    # A numeric range wrapped at the hyphen ("1603-" / "1714") is NOT a soft word
    # wrap: a digit (not a letter) precedes the hyphen and the continuation starts
    # with a digit, so the halves are never fused into a single token.
    spans = _body_context_spans() + [
        _span(1, "The dynasty reigned across the years 1603-", top=140, bottom=154),
        _span(1, "1714 without interruption at all.", top=156, bottom=170),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    joined = " ".join(p.text for p in result.paragraphs)
    assert "16031714" not in joined
    assert "1603- 1714" in joined


def test_build_paragraph_units_does_not_dehyphenate_before_uppercase_continuation() -> None:
    # A line ending "sub-" followed by an UPPERCASE continuation is a boundary
    # (new sentence / proper noun), not a soft word wrap: never de-hyphenated.
    spans = _body_context_spans() + [
        _span(1, "The council convened with the sub-", top=140, bottom=154),
        _span(1, "Committee reviewed the final report.", top=156, bottom=170),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    joined = " ".join(p.text for p in result.paragraphs)
    assert "subCommittee" not in joined


def _heading_notes_marker_spans(page: int, top: float) -> list[PdfTextSpan]:
    # A prominent "Notes" divider that opens the endnote back-matter.
    return [_span(page, "Notes", top=top, bottom=top + 20, x0=50, x1=140, font_size=18, bold=True)]


def test_build_paragraph_units_promotes_bare_part_divider_to_top_level_heading() -> None:
    # A body-sized but BOLD "PART II" divider is missed by the font-ratio typography
    # test (it is only body-sized) yet carries a corroborating emphasis signal, so it
    # is promoted to a deterministic top-level structural heading (Part sits above
    # Chapter). Reconcile — not the per-span classifier — does the promotion, so the
    # level is forced to 1 rather than inferred from the (body) font ratio.
    spans = _body_context_spans() + [
        _span(1, "PART II", top=140, bottom=154, x0=50, x1=130, font_size=10, bold=True),
        _span(1, "Body prose opening the second part of the book here.", top=190, bottom=204),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    part = next(p for p in result.paragraphs if p.text == "PART II")
    assert part.role == "heading"
    assert part.heading_level == 1


def test_build_paragraph_units_does_not_promote_plain_body_part_divider() -> None:
    # F23: the same "PART II" literal set at plain body font with no emphasis carries
    # no typography signal, so it is NOT promoted ("no source signal, no repair").
    spans = _body_context_spans() + [
        _span(1, "PART II", top=140, bottom=154, x0=50, x1=130, font_size=10, bold=False),
        _span(1, "Body prose opening the second part of the book here.", top=190, bottom=204),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    part = next(p for p in result.paragraphs if p.text == "PART II")
    assert part.role == "body"
    assert part.heading_level is None


def test_build_paragraph_units_does_not_promote_part_number_in_running_prose() -> None:
    # "Part I of the book describes…" opens with "Part I" but continues as prose (a
    # bare-space lowercase continuation, no separator), so it stays body.
    spans = _body_context_spans() + [
        _span(1, "Part I of the book describes the process by which wealth is created.", top=140, bottom=154),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    line = next(p for p in result.paragraphs if p.text.startswith("Part I of the book"))
    assert line.role == "body"


def _body_unit(
    text: str, *, bold: bool = False, font_size_pt: float | None = None
) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role="body",
        structural_role="body",
        style_name="PDF Body",
        is_bold=bold,
        font_size_pt=font_size_pt,
    )


def _heading_unit(text: str, *, level: int) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role="heading",
        structural_role="heading",
        style_name="PDF Heading",
        heading_level=level,
        heading_source="pdf_text_layer",
    )


def test_reconcile_promotes_standalone_conclusion_body_line_to_heading() -> None:
    # A standalone "CONCLUSION" section marker left as body but carrying a heading
    # typography signal (bold body, as it survives real large-corpus clustering) is
    # promoted to a top-level heading.
    units = [
        _body_unit("A running body sentence closes the previous chapter."),
        _body_unit("CONCLUSION", bold=True),
        _body_unit("Body prose that opens the concluding section of the book."),
    ]

    result = _reconcile_structural_headings(units)

    conclusion = next(u for u in result if u.text == "CONCLUSION")
    assert conclusion.role == "heading"
    assert conclusion.heading_level == 1


def test_reconcile_does_not_promote_plain_body_section_marker() -> None:
    # F23: a "CONCLUSION" section marker set at plain body font with no emphasis
    # carries no typography signal, so the marker literal alone does NOT promote it.
    units = [
        _body_unit("A running body sentence closes the previous chapter."),
        _body_unit("CONCLUSION"),
        _body_unit("Body prose that opens the concluding section of the book."),
    ]

    result = _reconcile_structural_headings(units, body_font_size=10.0)

    assert next(u for u in result if u.text == "CONCLUSION").role == "body"


def test_reconcile_does_not_promote_section_marker_in_backmatter() -> None:
    # After the notes back-matter opens, a bare "Conclusion" endnote-group label is
    # left as body even WITH a typography signal — the back-matter position gate, not
    # a missing signal, is what suppresses the promotion here.
    units = [
        _body_unit("A running body sentence in the main body."),
        _heading_unit("Notes", level=3),
        _body_unit("Conclusion", bold=True),
        _body_unit("An endnote entry for the concluding section."),
    ]

    result = _reconcile_structural_headings(units)

    assert next(u for u in result if u.text == "Conclusion").role == "body"


def test_build_paragraph_units_does_not_promote_midsentence_conclusion_word() -> None:
    # "Conclusion In addition to the specific examples…" uses the word mid-sentence
    # (a bare-space capitalized continuation, not a separator), so it stays body.
    spans = _body_context_spans() + [
        _span(1, "Conclusion In addition to the specific examples of currency reform we saw.", top=140, bottom=154),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    line = next(p for p in result.paragraphs if p.text.startswith("Conclusion In addition"))
    assert line.role == "body"


def test_build_paragraph_units_keeps_single_adjacent_duplicate_chapter_number() -> None:
    # Two adjacent bare chapter numbers of the same value ("CHAPTER 5" then
    # "Chapter 5", one per page so they stay separate heading units) are one opener:
    # keep the first, demote the duplicate. Both bare chapter lines carry a heading
    # typography signal (bold) so they are promoted before de-duplication runs.
    spans = _body_context_spans() + [
        _span(1, "CHAPTER 5", top=200, bottom=218, x0=50, x1=160, font_size=10, bold=True),
        _span(2, "Chapter 5", top=40, bottom=58, x0=50, x1=160, font_size=10, bold=True),
        _span(2, "Body prose that opens the fifth chapter of the book here.", top=90, bottom=104),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    chapters = [p for p in result.paragraphs if p.text in {"CHAPTER 5", "Chapter 5"}]
    assert [p.role for p in chapters] == ["heading", "body"]


def test_build_paragraph_units_demotes_bare_chapter_number_cluster() -> None:
    # A part-boundary mini-listing of >=2 consecutive bare chapter numbers (different
    # values) is not a set of real openers — demote them all.
    spans = _body_context_spans() + [
        _span(1, "CHAPTER 1", top=200, bottom=218, x0=50, x1=160, font_size=10, bold=True),
        _span(2, "CHAPTER 12", top=40, bottom=58, x0=50, x1=170, font_size=10, bold=True),
        _span(3, "Chapter 1", top=40, bottom=58, x0=50, x1=160, font_size=10, bold=True),
        _span(4, "Chapter 12", top=40, bottom=58, x0=50, x1=170, font_size=10, bold=True),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    cluster = [p for p in result.paragraphs if p.text in {"CHAPTER 1", "CHAPTER 12", "Chapter 1", "Chapter 12"}]
    assert len(cluster) == 4
    assert all(p.role == "body" for p in cluster)


def test_build_paragraph_units_demotes_backmatter_bare_chapter_labels() -> None:
    # Inside the notes back-matter, per-chapter endnote groupings render as bare
    # "Chapter N" labels — pass-through (body), not chapter openers.
    spans = (
        _body_context_spans()
        + _heading_notes_marker_spans(1, 200)
        + [
            _span(1, "Chapter 1", top=260, bottom=274, x0=50, x1=160, font_size=10, bold=True),
            _span(1, "An endnote entry belonging to the first chapter of the book.", top=290, bottom=304),
            _span(1, "Chapter 2", top=340, bottom=354, x0=50, x1=160, font_size=10, bold=True),
            _span(1, "An endnote entry belonging to the second chapter of the book.", top=370, bottom=384),
        ]
    )

    result = build_paragraph_units_from_text_spans(spans)

    labels = [p for p in result.paragraphs if p.text in {"Chapter 1", "Chapter 2"}]
    assert len(labels) == 2
    assert all(p.role == "body" for p in labels)
    # The real "Notes" divider that opens the back-matter stays a heading.
    assert next(p for p in result.paragraphs if p.text == "Notes").role == "heading"


def test_build_paragraph_units_keeps_real_bare_chapter_opener() -> None:
    # A lone bare "Chapter 6" opener followed by chapter body (not a duplicate, not a
    # cluster, not back-matter) is preserved as a heading.
    spans = _body_context_spans() + [
        _span(1, "Chapter 6", top=200, bottom=218, x0=50, x1=160, font_size=10, bold=True),
        _span(1, "Body prose that opens the sixth chapter of the book here.", top=250, bottom=264),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    chapter = next(p for p in result.paragraphs if p.text == "Chapter 6")
    assert chapter.role == "heading"
    assert chapter.heading_level == 1
