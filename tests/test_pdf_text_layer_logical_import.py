from __future__ import annotations

import docxaicorrector.pdf_import.logical_import as logical_import
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


def test_065_fr007_marker_split_off_a_line_ending_in_a_comma_is_glued_as_superscript() -> None:
    # Spec 065 FR-007, Money and Sustainability's shape: a reference set after a clause comma
    # at the end of a line is lifted off the line by the extractor (the comma is now an
    # anchor) and re-bound here. Glued like one after a full stop -- not "capitalism, 5 the
    # examples", a number in the middle of the sentence.
    spans = [
        _span(1, "Body line establishes the normal document sentence.", top=70, bottom=82, x0=50, x1=430),
        _span(1, "a basic characteristic of capitalism,", top=100, bottom=112, x0=50, x1=430),
        _span(1, "5", top=101, bottom=106, x0=431, x1=434, font_size=4),
        _span(1, "the examples he uses all refer to firms.", top=114, bottom=126, x0=50, x1=300),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    joined = " ".join(paragraph.text for paragraph in result.paragraphs)
    assert "capitalism,⁵ the examples" in joined
    assert all(paragraph.text.strip() != "5" for paragraph in result.paragraphs)


def test_065_fr007_marker_after_a_bare_word_keeps_its_inline_form() -> None:
    # Anti-vacuum for the glue above: a marker after a bare word keeps the inline,
    # space-separated form Rule 1 pins (unchanged; no corpus case reaches it).
    spans = [
        _span(1, "Body text line one with a body sentence", top=100, bottom=112, x0=50, x1=300, font_size=12),
        _span(1, "12", top=101, bottom=106, x0=302, x1=309, font_size=6),
        _span(1, "evolution which is bound to throw up results", top=120, bottom=132, x0=50, x1=300, font_size=12),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert result.paragraphs[0].text == (
        "Body text line one with a body sentence 12 evolution which is bound to throw up results"
    )


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
    # The caption role is carried across the PDF->DOCX bridge as the built-in ``Caption``
    # style (spec 055). Before that it was stamped ``PDF Caption``, a name python-docx has
    # never had, and the bridge dropped it unread.
    assert result.paragraphs[0].style_name == "Caption"


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
        is_bold=bold,
        font_size_pt=font_size_pt,
    )


def _heading_unit(text: str, *, level: int) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role="heading",
        structural_role="heading",
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


# --- Spec 055: the importer records the layout evidence it measured ---------
#
# `vertical_gap_before_pt` was 0 of 8216 paragraphs across the four corpus books before this
# (census, 2026-08-05). It can only be filled here: a PDF carries no `w:spacing`, so the gap
# IS geometry, and the geometry stops existing once the intermediate DOCX is written.
#
# `paragraph_alignment` stays unset on purpose. Centring is measurable here and was carried
# for one round of the spec 055 experiment; on the corpus it produced 33 heading promotions
# across four books, not one of them correct, and it is not carried any more. The last test
# in this block is the guard on that verdict.


def _wide_body_context_spans() -> list[PdfTextSpan]:
    return [
        _span(1, "A first running body line long enough to count as a body width sample.", top=40, bottom=54),
        _span(1, "A second running body line long enough to count as a body width sample.", top=56, bottom=70),
        _span(1, "A third running body line long enough to count as a body width sample.", top=72, bottom=86),
        _span(1, "A fourth running body line long enough to count as a body width sample.", top=88, bottom=102),
    ]


def test_paragraph_units_record_measured_gap_before() -> None:
    spans = _wide_body_context_spans() + [
        _span(1, "A body line set well below the paragraph above it here.", top=142, bottom=156),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    below = next(p for p in result.paragraphs if p.text.startswith("A body line set well below"))
    # 142 - 102 = 40pt of measured whitespace above the line.
    assert below.vertical_gap_before_pt == 40.0


def test_gap_before_is_not_guessed_across_a_page_break() -> None:
    spans = _wide_body_context_spans() + [
        _span(2, "The first body line on the following page of the document.", top=40, bottom=54),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    first_on_page_two = next(
        p for p in result.paragraphs if p.text.startswith("The first body line on the following page")
    )
    assert first_on_page_two.vertical_gap_before_pt is None


def test_gap_before_is_measured_for_every_reachable_paragraph() -> None:
    # ANTI-VACUUM: a carry that silently reached almost nothing would look identical to the
    # defect it fixes. Every paragraph after the first on a page must get a measured gap.
    result = build_paragraph_units_from_text_spans(_wide_body_context_spans())

    measured = [p for p in result.paragraphs if p.vertical_gap_before_pt is not None]
    assert len(measured) == len(result.paragraphs) - 1


def test_centring_is_measurable_but_deliberately_not_carried() -> None:
    # A line inset far inside the body column on both sides is unambiguously centred, and the
    # importer still records no alignment for it. Spec 055 measured the alternative: carrying
    # it promoted 24 notes-back-matter chapter labels, a copyright year, a formula and half a
    # wrapped chapter title to headings, and nothing correct. If this assertion is ever
    # flipped, the corpus measurement has to be redone first — a unit test cannot settle it.
    spans = _wide_body_context_spans() + [
        _span(1, "A Centred Display Line", top=140, bottom=154, x0=200, x1=300),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    centred = next(p for p in result.paragraphs if p.text == "A Centred Display Line")
    assert centred.paragraph_alignment is None
    assert all(p.paragraph_alignment is None for p in result.paragraphs)


# --- Spec 055 follow-up: one role->style decision, and it is this one ---------------
#
# `logical_import._ROLE_DOCX_STYLE` is the only place where an importer role becomes an
# intermediate-DOCX paragraph style. The PDF->DOCX bridge used to keep a second, poorer
# mapper of its own and ignore the field this module sets; it now reads `style_name`.


def test_every_carried_docx_style_name_exists_in_the_default_template() -> None:
    # The bridge passes this name straight to `Document.add_paragraph(style=...)`, which
    # raises KeyError on a style the template does not define — and that would abort the
    # import of a whole book. This is the guard for every future addition to the table:
    # "PDF Caption", the name this module used to emit, fails it.
    from docx import Document

    document = Document()
    for role in logical_import._ROLE_DOCX_STYLE:
        for heading_level in (None, 1, 2, 6, 9):
            style_name = logical_import.docx_style_name_for_role(role, heading_level)
            if style_name is None:
                continue
            assert document.styles[style_name] is not None


def test_roles_deliberately_not_carried_have_no_docx_style() -> None:
    # A recorded decision, not an omission — see the comment above `_ROLE_DOCX_STYLE`.
    # `toc_entry` is deferred pending the four-book run; `footnote` is closed (59 characters
    # of bare superscript markers across the corpus, and Constitution VII puts footnotes out
    # of scope); `body` is `Normal` by definition.
    for role in ("toc_entry", "footnote", "body"):
        assert role in logical_import._ROLE_DOCX_STYLE
        assert logical_import.docx_style_name_for_role(role) is None
    assert logical_import.docx_style_name_for_role("something_new_and_unmapped") is None


def test_carried_roles_map_to_the_expected_styles() -> None:
    assert logical_import.docx_style_name_for_role("heading", 1) == "Heading 1"
    assert logical_import.docx_style_name_for_role("heading", 3) == "Heading 3"
    # The clamp the deleted bridge mapper applied, kept verbatim: no level means 2, and the
    # range is 1..6 because that is what the DOCX template defines.
    assert logical_import.docx_style_name_for_role("heading", None) == "Heading 2"
    assert logical_import.docx_style_name_for_role("heading", 0) == "Heading 2"
    assert logical_import.docx_style_name_for_role("heading", 42) == "Heading 6"
    assert logical_import.docx_style_name_for_role("heading", -3) == "Heading 1"
    assert logical_import.docx_style_name_for_role("list") == "List Bullet"
    assert logical_import.docx_style_name_for_role("caption") == "Caption"


def test_style_name_is_stamped_from_the_final_role_not_the_constructed_one() -> None:
    # Why the stamp is a pass at the end of the import rather than a constructor argument:
    # `_promote_unit_to_heading` runs after the unit is built, so a style decided at
    # construction time would be stale exactly where the role changed.
    unit = ParagraphUnit(text="CONCLUSION", role="body", structural_role="body")
    logical_import._promote_unit_to_heading(unit, heading_level=1)

    logical_import._assign_docx_style_names([unit])

    assert unit.style_name == "Heading 1"

    logical_import._demote_heading_to_body(unit)
    logical_import._assign_docx_style_names([unit])

    assert unit.style_name == ""


def test_toc_entry_units_are_keyed_on_structural_role_and_stay_unstyled() -> None:
    # A TOC row carries `role="body"` and `structural_role="toc_entry"`, so the stamp keys on
    # the structural role — otherwise the table entry that names the deferral would be
    # unreachable and read as dead code.
    unit = ParagraphUnit(text="Chapter One .......... 12", role="body", structural_role="toc_entry")

    logical_import._assign_docx_style_names([unit])

    assert unit.style_name == ""


def test_every_imported_paragraph_carries_the_style_its_role_decides() -> None:
    # ANTI-VACUUM: the bridge now trusts `style_name`, so a unit that escaped the stamp would
    # silently lose its style. Every paragraph the importer returns must agree with the table.
    spans = [
        _span(1, "A Chapter Opener", top=60, bottom=84, x0=50, font_size=22, bold=True),
        _span(1, "Ordinary prose opens the chapter and runs on for a while.", top=110, bottom=122),
        _span(1, "• A bulleted item", top=140, bottom=152),
        _span(1, "FIGURE 1.1. The Corporate Process", top=180, bottom=192, x0=160),
        _span(1, "More prose after the figure caption line.", top=210, bottom=222),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert {p.structural_role for p in result.paragraphs} >= {"heading", "body", "caption"}
    for paragraph in result.paragraphs:
        expected = logical_import.docx_style_name_for_role(
            paragraph.structural_role or paragraph.role, paragraph.heading_level
        )
        assert paragraph.style_name == (expected or "")


# --------------------------------------------------------------------------------------
# Spec 063 FR-008: a two-line heading arrives from import as ONE heading.
# Spec 063 FR-009: a chapter title the per-span pass left as body is a heading by form.
# Every rule here keys on typesetting -- face, size, gaps, page position, line count -- and
# the anti-vacuum tests below show what the same shapes must NOT turn into.
# --------------------------------------------------------------------------------------


def _body_page(page: int, *, top: float, count: int = 6) -> list[PdfTextSpan]:
    """Running prose on ``page`` from ``top``: enough for a realistic body size and leading."""
    return [
        _span(
            page,
            f"Running prose line number {index} of the body text that fills this page here.",
            top=top + index * 14,
            bottom=top + index * 14 + 10,
        )
        for index in range(count)
    ]


def test_fr008_two_line_bold_sub_head_is_one_heading() -> None:
    # Rethinking Money p. 149 in miniature: a body-sized bold sub-head broken over two lines.
    # The second line starts flush with the body column and the first does not end a
    # sentence, so the per-span pass reads the second line as a sentence continuation.
    spans = (
        _body_page(1, top=40)
        + [
            _span(1, "A PROPOSAL FOR A GLOBAL TRADE", top=150, bottom=160, x1=220, bold=True),
            _span(1, "REFERENCE CURRENCY", top=164, bottom=174, x1=150, bold=True),
            _span(1, "A new nonnational currency has been designed to provide a safety net.", top=188, bottom=198),
        ]
        + _body_page(1, top=202, count=4)
    )

    result = build_paragraph_units_from_text_spans(spans)

    headings = [p for p in result.paragraphs if p.role == "heading"]
    assert [p.text for p in headings] == ["A PROPOSAL FOR A GLOBAL TRADE REFERENCE CURRENCY"]
    assert headings[0].origin_raw_texts == ["A PROPOSAL FOR A GLOBAL TRADE", "REFERENCE CURRENCY"]
    assert not any(p.text == "REFERENCE CURRENCY" for p in result.paragraphs)


def test_fr008_display_title_second_line_that_reads_lowercase_joins_the_title() -> None:
    # Creating Wealth ch. 9: the title is set large and NOT bold; its second line begins in
    # lowercase, which the per-span pass reads as a sentence continuation.
    spans = (
        _body_page(1, top=40)
        + [_span(2, "CHAPTER 9", top=40, bottom=52, x0=200, x1=280, bold=True)]
        + [
            _span(2, "Minding", top=96, bottom=116, x0=230, x1=300, font_size=20),
            _span(2, "the Community’s Business", top=120, bottom=140, x0=180, x1=380, font_size=20),
        ]
        + _body_page(2, top=200)
    )

    result = build_paragraph_units_from_text_spans(spans)

    title = next(p for p in result.paragraphs if p.text.startswith("Minding"))
    assert title.text == "Minding the Community’s Business"
    assert title.role == "heading"


def test_fr008_bold_paragraph_under_a_bold_heading_is_not_glued_to_it() -> None:
    # ANTI-VACUUM: the same face and the same leading, but the bold text runs on for three
    # lines -- a paragraph, not the last line of the heading.
    spans = (
        _body_page(1, top=40)
        + [
            _span(1, "A PROPOSAL FOR A GLOBAL TRADE", top=150, bottom=160, x1=220, bold=True),
            _span(1, "REFERENCE CURRENCY IS DISCUSSED IN THIS", top=164, bottom=174, bold=True),
            _span(1, "BOLD PASSAGE THAT KEEPS GOING ON AND ON", top=178, bottom=188, bold=True),
            _span(1, "FOR A THIRD LINE BEFORE IT STOPS HERE", top=192, bottom=202, bold=True),
        ]
        + _body_page(1, top=230, count=4)
    )

    result = build_paragraph_units_from_text_spans(spans)

    assert not any(
        p.role == "heading" and "REFERENCE CURRENCY" in p.text for p in result.paragraphs
    )


def test_fr008_plain_body_line_never_joins_a_heading() -> None:
    # ANTI-VACUUM: the line under the heading is in the body face. Same column, same size,
    # tight leading -- but nothing typographic says it belongs to the heading.
    spans = (
        _body_page(1, top=40)
        + [
            _span(1, "A PROPOSAL FOR A GLOBAL TRADE", top=150, bottom=160, x1=220, bold=True),
            _span(1, "REFERENCE CURRENCY", top=164, bottom=174, x1=150),
        ]
        + _body_page(1, top=200, count=4)
    )

    result = build_paragraph_units_from_text_spans(spans)

    assert [p.text for p in result.paragraphs if p.role == "heading"] == ["A PROPOSAL FOR A GLOBAL TRADE"]


def test_fr008_line_with_one_bold_word_is_not_a_heading_line() -> None:
    # ANTI-VACUUM (Creating Wealth contents page): pdfminer reports the first word of a
    # contents line as bold. Bold must hold for the whole line.
    spans = (
        _body_page(1, top=40)
        + [
            _span(1, "A PROPOSAL FOR A GLOBAL TRADE", top=150, bottom=160, x1=220, bold=True),
            PdfTextSpan(
                page_number=1,
                text="REFERENCE CURRENCY",
                x0=50,
                top=164,
                x1=150,
                bottom=174,
                page_height=800,
                font_name="SourceSerif-Bold",
                font_size=10,
                is_bold=True,
                is_italic=False,
                runs=(("REFERENCE", True, False), (" CURRENCY", False, False)),
            ),
        ]
        + _body_page(1, top=200, count=4)
    )

    result = build_paragraph_units_from_text_spans(spans)

    assert [p.text for p in result.paragraphs if p.role == "heading"] == ["A PROPOSAL FOR A GLOBAL TRADE"]


def test_fr008_line_not_set_off_from_what_follows_is_not_the_heading_last_line() -> None:
    # ANTI-VACUUM (Money & Sustainability, the advertisement page): a bold title line under
    # a bold heading, followed at a TIGHTER gap than the one above it. A heading is set off
    # from what follows; this line opens an entry, it does not end the heading.
    spans = (
        _body_page(1, top=40)
        + [
            _span(1, "ALSO AVAILABLE FROM THIS PUBLISHER", top=150, bottom=160, x1=260, bold=True),
            _span(1, "A BOOK TITLE SET IN BOLD", top=164, bottom=174, x1=200, bold=True),
            _span(1, "Its authors, named on a plain line right below", top=176, bottom=186, x1=300),
        ]
        + _body_page(1, top=210, count=4)
    )

    result = build_paragraph_units_from_text_spans(spans)

    assert not any(
        p.role == "heading" and "A BOOK TITLE SET IN BOLD" in p.text and "ALSO AVAILABLE" in p.text
        for p in result.paragraphs
    )


def test_fr008_headings_of_different_size_in_a_row_stay_two() -> None:
    # ANTI-VACUUM: two heading levels back to back. The second line is bold and sits at the
    # heading's leading, but it is set at another size: another level.
    spans = (
        _body_page(1, top=40)
        + [
            _span(1, "PART THREE OF THE BOOK", top=150, bottom=164, x1=260, font_size=14, bold=True),
            _span(1, "A SECTION IN THE PART", top=168, bottom=178, x1=200, bold=True),
        ]
        + _body_page(1, top=200, count=4)
    )

    result = build_paragraph_units_from_text_spans(spans)

    assert not any(
        "PART THREE OF THE BOOK" in p.text and "A SECTION IN THE PART" in p.text
        for p in result.paragraphs
    )


def test_fr008_bold_line_in_another_typeface_is_not_the_heading_last_line() -> None:
    # ANTI-VACUUM: bold, same size, tight leading, set off below -- but in a different
    # typeface from the heading line above it. A heading's lines share one face.
    def bold_span(text: str, *, top: float, font_name: str) -> PdfTextSpan:
        return PdfTextSpan(
            page_number=1,
            text=text,
            x0=50,
            top=top,
            x1=220,
            bottom=top + 10,
            page_height=800,
            font_name=font_name,
            font_size=10,
            is_bold=True,
            is_italic=False,
        )

    spans = (
        _body_page(1, top=40)
        + [
            bold_span("A PROPOSAL FOR A GLOBAL TRADE", top=150, font_name="FranklinGothic-Demi"),
            bold_span("REFERENCE CURRENCY", top=164, font_name="SourceSerif-Bold"),
        ]
        + _body_page(1, top=200, count=4)
    )

    result = build_paragraph_units_from_text_spans(spans)

    assert [p.text for p in result.paragraphs if p.role == "heading"] == ["A PROPOSAL FOR A GLOBAL TRADE"]


def _chapter_opening(title_spans: list[PdfTextSpan], *, page: int = 2) -> list[PdfTextSpan]:
    """A chapter opening page: prose ends on the page before, the new page starts with a
    bold chapter label, then the title lines, then prose."""
    return (
        _body_page(page - 1, top=40)
        + [_span(page, "Chapter Three", top=40, bottom=54, x0=200, x1=300, font_size=12, bold=True)]
        + title_spans
        + _body_page(page, top=200)
    )


def test_fr009_display_title_ending_in_a_question_mark_is_a_heading() -> None:
    # Money & Sustainability ch. I / IX, Creating Wealth ch. 1: the title ends in "?", so the
    # per-span pass refuses it as a heading (a heading does not end a sentence). Its form --
    # display size, at the top of the chapter page under the label -- says otherwise.
    result = build_paragraph_units_from_text_spans(
        _chapter_opening([_span(2, "Why this Report, Now?", top=80, bottom=104, x0=150, x1=400, font_size=20)])
    )

    title = next(p for p in result.paragraphs if p.text == "Why this Report, Now?")
    assert title.role == "heading"
    assert title.heading_level == 1
    assert title.boundary_rationale == "promoted_display_title"


def test_fr009_title_broken_over_two_display_lines_is_one_heading() -> None:
    # Creating Wealth ch. 11 and Rethinking Money ch. 5/11: two (or three) display lines of
    # one title, each left as body.
    result = build_paragraph_units_from_text_spans(
        _chapter_opening(
            [
                _span(2, "Honoring Our Elders,", top=80, bottom=100, x0=180, x1=380, font_size=20),
                _span(2, "Caring for Children", top=103, bottom=123, x0=190, x1=370, font_size=20),
            ]
        )
    )

    titles = [p for p in result.paragraphs if "Elders" in p.text or "Caring" in p.text]
    assert [(p.role, p.text) for p in titles] == [("heading", "Honoring Our Elders, Caring for Children")]
    assert titles[0].origin_raw_texts == ["Honoring Our Elders,", "Caring for Children"]


def test_fr009_title_and_subtitle_set_at_different_sizes_stay_two_headings() -> None:
    # ANTI-VACUUM (Rethinking Money chapter openings): the title and the subtitle under it
    # are both display lines at the top of the page, but at different sizes -- two headings,
    # not one. As in the book, the title also runs as the page head of the chapter's later
    # pages, which is why the per-span pass refuses it; the subtitle ends in "?".
    running_heads = [
        _span(page, "THE FAILURE OF MONEY", top=20, bottom=29, x0=150, x1=300, font_size=8)
        for page in (3, 4, 5)
    ]
    later_pages = [span for page in (3, 4, 5) for span in _body_page(page, top=40, count=3)]
    result = build_paragraph_units_from_text_spans(
        _chapter_opening(
            [
                _span(2, "THE FAILURE OF MONEY", top=100, bottom=123, x0=150, x1=420, font_size=23),
                _span(2, "An Ancient Future?", top=126, bottom=146, x0=160, x1=410, font_size=19),
            ]
        )
        + running_heads
        + later_pages
    )

    page_two_headings = [
        p.text for p in result.paragraphs if p.role == "heading" and p.text != "Chapter Three"
    ]
    assert page_two_headings == ["THE FAILURE OF MONEY", "An Ancient Future?"]


def test_fr009_chapter_number_line_above_the_title_joins_it() -> None:
    # Value of Everything ch. 7: "7" on its own display line, the title under it. The title
    # starts within a leading of the body column's left edge and the line above ("7") does
    # not end a sentence, so the per-span pass reads the title as running prose.
    result = build_paragraph_units_from_text_spans(
        _body_page(1, top=40)
        + [
            _span(2, "7", top=216, bottom=237, x0=260, x1=271, font_size=21),
            _span(
                2,
                "Extracting Value through the Innovation Economy",
                top=254,
                bottom=275,
                x0=55,
                x1=480,
                font_size=21,
            ),
        ]
        + _body_page(2, top=400)
    )

    headings = [p for p in result.paragraphs if p.role == "heading"]
    assert [p.text for p in headings] == ["7 Extracting Value through the Innovation Economy"]


def test_fr009_display_line_in_the_middle_of_a_page_stays_body() -> None:
    # ANTI-VACUUM: the same display-size line, but prose precedes it on the page. Only the
    # opening block of a page is read; nothing mid-page is promoted.
    spans = (
        _body_page(1, top=40)
        + [_span(1, "Why this Report, Now?", top=140, bottom=164, x0=150, x1=400, font_size=20)]
        + _body_page(1, top=180, count=4)
    )

    result = build_paragraph_units_from_text_spans(spans)

    line = next(p for p in result.paragraphs if p.text == "Why this Report, Now?")
    assert line.role == "body"


def test_fr009_display_block_longer_than_a_title_stays_body() -> None:
    # ANTI-VACUUM: four display lines at the top of a page are a display paragraph (a pull
    # quote, a title page blurb), not a title -- the corpus' longest title has three lines.
    lines = [
        "We all suffer",
        "and before change",
        "it must first be",
        "understood by all",
    ]
    title_spans = [
        _span(2, text, top=80 + index * 23, bottom=100 + index * 23, x0=150, x1=420, font_size=20)
        for index, text in enumerate(lines)
    ]

    result = build_paragraph_units_from_text_spans(_chapter_opening(title_spans))

    assert not any(p.role == "heading" and "suffer" in p.text for p in result.paragraphs)


def test_fr009_cover_scan_noise_at_display_size_stays_body() -> None:
    # ANTI-VACUUM (Money & Sustainability cover, OCR'd): display-size characters that are
    # not words. Position and size alone do not make a title.
    spans = [
        _span(1, "ri1*\\VvrV", top=60, bottom=84, x0=150, x1=300, font_size=20),
    ] + _body_page(1, top=200)

    result = build_paragraph_units_from_text_spans(spans)

    noise = next(p for p in result.paragraphs if "VvrV" in p.text)
    assert noise.role == "body"


def test_fr009_body_size_line_at_the_top_of_a_page_stays_body() -> None:
    # ANTI-VACUUM: a short line opening a page at BODY size -- the tail of a paragraph
    # carried over, a list head -- is never a display title.
    spans = (
        _body_page(1, top=40)
        + [_span(2, "Why this Report, Now?", top=40, bottom=50, x0=50, x1=200)]
        + _body_page(2, top=80)
    )

    result = build_paragraph_units_from_text_spans(spans)

    line = next(p for p in result.paragraphs if p.text == "Why this Report, Now?")
    assert line.role == "body"


# Spec 064 FR-007 (R-5): a cell of a table or diagram is not a heading. Creating Wealth's figure
# "Competition and Cooperation" came through as a run of level-3 headings ("Peak Experience" |
# "Endurance-Sus tainability" on one baseline); the model merged one into the body and
# ``key_headings_preserved`` failed. The form: two short spans of one size on one baseline.


def _subheading_page(*middle: PdfTextSpan) -> list[PdfTextSpan]:
    return [
        _span(1, "The time currency also created stronger", top=100, bottom=112, x0=50),
        _span(1, "community ties.", top=114, bottom=126, x0=50),
        *middle,
        _span(1, "The first LETS systems originated in Canada in northern regions", top=142, bottom=154, x0=50),
        _span(1, "aiming specifically at currency scarcity in areas.", top=156, bottom=168, x0=50),
    ]


def test_fr007_short_line_alone_on_its_baseline_is_a_heading() -> None:
    # ANTI-VACUUM for the next test: the same line, alone on its row, is a heading today.
    result = build_paragraph_units_from_text_spans(
        _subheading_page(_span(1, "Employment", top=128, bottom=140, x0=50, x1=120))
    )

    assert [p.role for p in result.paragraphs] == ["body", "heading", "body"]


def test_fr007_two_short_cells_on_one_baseline_are_not_headings() -> None:
    result = build_paragraph_units_from_text_spans(
        _subheading_page(
            _span(1, "Employment", top=128, bottom=140, x0=50, x1=120),
            _span(1, "Endurance", top=128, bottom=140, x0=200, x1=270),
        )
    )

    assert not any(p.role == "heading" for p in result.paragraphs)


def test_fr007_cell_one_line_off_its_row_belongs_to_the_table() -> None:
    # A header cell set a little above its row, or two cells the extractor read as one line
    # (Creating Wealth: "Command and Control Mutual Trust and Action"), sits within one line
    # of a row cell of the same size: it is part of the table too. A line of the same size
    # further away than one line is not reached.
    spans = _subheading_page(
        _span(1, "Characteristics", top=126, bottom=132, x0=110, x1=160, font_size=5),
        _span(1, "Competition", top=134, bottom=140, x0=120, x1=170, font_size=5),
        _span(1, "Cooperation", top=134, bottom=140, x0=200, x1=250, font_size=5),
        _span(1, "Far Away Label", top=60, bottom=66, x0=50, x1=90, font_size=5),
    )

    result = build_paragraph_units_from_text_spans(spans)
    keys = logical_import._detect_table_row_span_keys(
        spans, repeated_furniture_keys=set(), body_line_length_p75=64.0
    )

    assert not any(p.role == "heading" for p in result.paragraphs if "Co" in p.text)
    assert (1, 126.0, 110.0) in keys
    assert (1, 60.0, 50.0) not in keys


def test_fr007_line_beside_a_full_body_line_of_another_column_is_not_a_table_cell() -> None:
    # ANTI-VACUUM (two-column body): the line beside the short one is a whole column line,
    # longer than half a body line, so the row is not a table row. The importer orders a
    # two-column page by baseline and has no column model, so this is checked on the row
    # detector itself, the one place the bound lives.
    spans = _subheading_page(
        _span(1, "Employment", top=128, bottom=140, x0=50, x1=120),
        _span(1, "a whole line of the second column of a body set in two", top=128, bottom=140, x0=300, x1=560),
    )
    keys = logical_import._detect_table_row_span_keys(
        spans, repeated_furniture_keys=set(), body_line_length_p75=64.0
    )

    assert keys == frozenset()
    short_row = logical_import._detect_table_row_span_keys(
        _subheading_page(
            _span(1, "Employment", top=128, bottom=140, x0=50, x1=120),
            _span(1, "Endurance", top=128, bottom=140, x0=200, x1=270),
        ),
        repeated_furniture_keys=set(),
        body_line_length_p75=64.0,
    )
    assert {(1, 128.0, 50.0), (1, 128.0, 200.0)} <= short_row


def test_fr007_display_size_line_beside_a_short_span_stays_a_heading() -> None:
    # ANTI-VACUUM: a line set ABOVE the body is display type, not a table cell, even when a
    # short span of its size stands on its baseline (a chapter number set beside the title).
    spans = [
        _span(1, "Body line one keeps the dominant document style", top=100, bottom=112, x0=50),
        _span(1, "body line two keeps the dominant document style", top=114, bottom=126, x0=50),
        _span(1, "Body line three keeps the dominant document style.", top=128, bottom=140, x0=50),
        _span(1, "PART ONE", top=180, bottom=202, x0=150, x1=260, font_size=18, bold=True),
        _span(1, "I", top=180, bottom=202, x0=300, x1=310, font_size=18, bold=True),
        _span(1, "Body text resumes with the dominant document style.", top=270, bottom=282, x0=50),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert any(p.role == "heading" and "PART ONE" in p.text for p in result.paragraphs)


def test_065_fr008_a_table_cell_is_a_paragraph_of_its_own() -> None:
    # Spec 065 FR-008 (I-4), Money's Box 7.1: two column labels on one baseline, a label of
    # the left column one line below. Since 064 FR-007 the right label is no longer a heading,
    # and the body merge ran it into the left column's next line ("PU BLIC SECTOR NGO
    # Initiative s :"); the model then joined the labels with an invented conjunction.
    spans = _subheading_page(
        _span(1, "Left Sector", top=128, bottom=134, x0=50, x1=100, font_size=5),
        _span(1, "Right Sector", top=128, bottom=134, x0=150, x1=200, font_size=5),
        _span(1, "Sub Label :", top=135, bottom=141, x0=50, x1=90, font_size=5, bold=True),
    )

    result = build_paragraph_units_from_text_spans(spans)
    texts = [p.text for p in result.paragraphs]

    assert "Left Sector" in texts
    assert "Right Sector" in texts
    assert not any("Right Sector" in t and "Sub Label" in t for t in texts)


def test_065_fr008_a_lowercase_table_cell_is_not_rejoined_after_the_span_loop() -> None:
    # Codex acceptance review 2026-11-08: the boundary set at the body flush did not survive
    # `_consolidate_cross_role_continuations`, which re-joined the two cells as a soft wrap when
    # the second began lowercase ("Left Sector right sector"). A unit built from a cell carries
    # the fact, and no later join crosses it.
    spans = _subheading_page(
        _span(1, "Left Sector", top=128, bottom=134, x0=50, x1=100, font_size=5),
        _span(1, "right sector", top=128, bottom=134, x0=150, x1=200, font_size=5),
        _span(1, "Sub Label :", top=135, bottom=141, x0=50, x1=90, font_size=5, bold=True),
    )

    paragraphs = build_paragraph_units_from_text_spans(spans).paragraphs
    texts = [p.text for p in paragraphs]

    assert "Left Sector" in texts
    assert "right sector" in texts
    assert all(p.is_pdf_table_cell for p in paragraphs if p.text in {"Left Sector", "right sector"})


def test_065_fr008_consolidation_neither_leads_from_nor_continues_into_a_cell() -> None:
    def units(cell_index: int) -> list[ParagraphUnit]:
        pair = [_body_unit("A body sentence that does not end and"), _body_unit("continues lowercase here.")]
        pair[cell_index].is_pdf_table_cell = True
        return pair

    plain = [_body_unit("A body sentence that does not end and"), _body_unit("continues lowercase here.")]
    assert len(logical_import._consolidate_cross_role_continuations(plain)) == 1  # anti-vacuum
    assert len(logical_import._consolidate_cross_role_continuations(units(0))) == 2
    assert len(logical_import._consolidate_cross_role_continuations(units(1))) == 2


def test_065_fr008_a_prose_line_cut_at_a_word_space_is_not_a_table_row() -> None:
    # Money and Sustainability p. 71: the extractor cut one justified line into "to an" |
    # "inflationary boom period. Conversely, when" | "the business horizon darkens, banks", a
    # word space apart. Read as table cells they split the paragraph mid-sentence once cells
    # stopped being re-joined. A word-space gap and a right piece that starts no column: one line.
    spans = [
        _span(1, "A first running body line that establishes the document leading here.", top=40, bottom=54),
        _span(1, "A second running body line that establishes the document leading too.", top=56, bottom=70),
        _span(1, "to an", top=72, bottom=86, x0=50, x1=80),
        _span(1, "inflationary period, when", top=72, bottom=86, x0=86, x1=230),
        _span(1, "the horizon darkens", top=72, bottom=86, x0=236, x1=340),
    ]
    keys = logical_import._detect_table_row_span_keys(
        spans, repeated_furniture_keys=set(), body_line_length_p75=64.0
    )

    assert keys == frozenset()


def test_065_fr008_close_columns_that_start_a_column_stay_a_table() -> None:
    # Counterexample, Money p. 4: two signature columns a word space apart; the right column
    # starts at the same x on the next row, so the rows are a table.
    spans = [
        _span(1, "Felix Name", top=100, bottom=106, x0=7, x1=43, font_size=5),
        _span(1, "Ivo Name", top=100, bottom=106, x0=46, x1=70, font_size=5),
        _span(1, "President of one", top=110, bottom=116, x0=7, x1=43, font_size=5),
        _span(1, "President of two", top=110, bottom=116, x0=46, x1=80, font_size=5),
    ]
    keys = logical_import._detect_table_row_span_keys(
        spans, repeated_furniture_keys=set(), body_line_length_p75=64.0
    )

    assert {(1, 100.0, 46.0), (1, 110.0, 46.0)} <= keys


def test_065_fr008_a_table_cell_unit_refuses_the_later_joins() -> None:
    # The two joins that run after the consolidation read the same flag.
    head = _span(1, "32. T. Atkinson, Atkinson Review: Final Report. Measurement of", top=160, bottom=172, x0=50, x1=446)
    tail = _span(1, "Government Output and Productivity for the National Accounts.", top=174, bottom=186, x0=70, x1=440)
    spans = _notes_page(head, tail)
    profile = logical_import._build_heading_layout_profile(spans, repeated_furniture_keys=set())
    units = [_notes_title_unit(), _line_unit(head, role="list"), _line_unit(tail, role="body")]
    assert len(logical_import._join_torn_back_matter_entries(units, spans, layout_profile=profile)) == 2

    units = [_notes_title_unit(), _line_unit(head, role="list"), _line_unit(tail, role="body")]
    units[2].is_pdf_table_cell = True
    assert len(logical_import._join_torn_back_matter_entries(units, spans, layout_profile=profile)) == 3

    wrap_head = _span(1, _WRAP_HEAD, top=72, bottom=86, x1=447)
    wrap_number = _span(1, _WRAP_NUMBER, top=88, bottom=102, x1=420)
    body_spans = _body_lead_spans() + [wrap_head, wrap_number]
    body_profile = logical_import._build_heading_layout_profile(body_spans, repeated_furniture_keys=set())
    pair = [_line_unit(wrap_head, role="body"), _line_unit(wrap_number, role="list")]
    assert len(logical_import._join_numbered_body_continuations(pair, body_spans, layout_profile=body_profile)) == 1
    pair = [_line_unit(wrap_head, role="body"), _line_unit(wrap_number, role="list")]
    pair[0].is_pdf_table_cell = True
    assert len(logical_import._join_numbered_body_continuations(pair, body_spans, layout_profile=body_profile)) == 2


def test_065_fr008_short_lines_that_are_not_table_cells_still_merge() -> None:
    # ANTI-VACUUM: a wrapped body line with nothing beside it is not a table cell; the body
    # merge treats it as before.
    spans = [
        _span(1, "A first running body line that establishes the document leading here.", top=40, bottom=54),
        _span(1, "A second running body line that establishes the document leading", top=56, bottom=70),
        _span(1, "and a wrapped third line continues the same sentence here.", top=72, bottom=86),
    ]

    result = build_paragraph_units_from_text_spans(spans)

    assert any("leading and a wrapped third line" in p.text for p in result.paragraphs)


def test_fr007_second_pass_does_not_reach_a_heading_beside_the_table():
    # Codex review 2026-11-07: a short heading of the cells' size, one line above a table row
    # but horizontally outside every cell of the table (the other column of the page), is not
    # part of the table.
    spans = _subheading_page(
        _span(1, "Side Heading", top=121, bottom=127, x0=300, x1=360, font_size=5),
        _span(1, "Competition", top=128, bottom=134, x0=50, x1=100, font_size=5),
        _span(1, "Cooperation", top=128, bottom=134, x0=150, x1=200, font_size=5),
    )
    keys = logical_import._detect_table_row_span_keys(
        spans, repeated_furniture_keys=set(), body_line_length_p75=64.0
    )

    assert {(1, 128.0, 50.0), (1, 128.0, 150.0)} <= keys
    assert (1, 121.0, 300.0) not in keys


# Spec 064 R-7: an entry of a notes / reference section that import tore in the middle of a
# sentence is joined back -- by form and geometry, never by a word. The page below is set like
# the corpus notes: body column 50..450, notes numbered at x0=50 with a hanging indent of 70, a
# wrapped line follows its predecessor with no blank line between them.


def _notes_page(*entries: PdfTextSpan, title: str = "Notes") -> list[PdfTextSpan]:
    return [
        _span(1, "A first running body line that establishes the document leading here.", top=40, bottom=54),
        _span(1, "A second running body line that establishes the document leading here.", top=56, bottom=70),
        _span(1, "A third running body line that establishes the document leading here.", top=72, bottom=86),
        _span(1, title, top=120, bottom=140, x0=50, x1=140, font_size=18, bold=True),
        *entries,
    ]


def _texts(spans: list[PdfTextSpan]) -> list[str]:
    return [paragraph.text for paragraph in build_paragraph_units_from_text_spans(spans).paragraphs]


_TORN_HEAD = "1. Both Tony Blair, the former British Prime Minister, and Chuka"
_TORN_TAIL = "Umunna, considered a rising star in the Labour Party, argued so."
_NEXT_NOTE = "2. Next note opens with its own number and ends a sentence."


def test_r7_torn_note_is_joined_into_one_paragraph() -> None:
    # VoE p1923/p1924 (run ids), CW p1781/p1782: the wrap starts on a capitalised name, which
    # the span-level merges do not accept; the line above ran out of room.
    texts = _texts(
        _notes_page(
            _span(1, _TORN_HEAD, top=160, bottom=172, x0=50, x1=446),
            _span(1, _TORN_TAIL, top=174, bottom=186, x0=70, x1=440),
            _span(1, _NEXT_NOTE, top=188, bottom=200, x0=50, x1=420),
        )
    )

    assert f"{_TORN_HEAD} {_TORN_TAIL}" in texts
    assert _NEXT_NOTE in texts
    assert _TORN_TAIL not in texts


def test_r7_tear_is_real_without_the_join() -> None:
    # ANTI-VACUUM: the same page without the pass is torn, so the join above is what fixes it.
    spans = _notes_page(
        _span(1, _TORN_HEAD, top=160, bottom=172, x0=50, x1=446),
        _span(1, _TORN_TAIL, top=174, bottom=186, x0=70, x1=440),
    )
    original = logical_import._join_torn_back_matter_entries
    logical_import._join_torn_back_matter_entries = lambda units, *args, **kwargs: units
    try:
        texts = _texts(spans)
    finally:
        logical_import._join_torn_back_matter_entries = original

    assert _TORN_HEAD in texts
    assert _TORN_TAIL in texts


def test_r7_numbered_next_note_is_not_joined() -> None:
    next_note = "2. Umunna, considered a rising star in the Labour Party."
    texts = _texts(
        _notes_page(
            _span(1, _TORN_HEAD, top=160, bottom=172, x0=50, x1=446),
            _span(1, next_note, top=174, bottom=186, x0=50, x1=420),
        )
    )

    assert _TORN_HEAD in texts
    assert next_note in texts


def test_r7_predecessor_ending_with_a_period_is_not_joined() -> None:
    head = "1. Both Tony Blair, the former British Prime Minister, said that."
    texts = _texts(
        _notes_page(
            _span(1, head, top=160, bottom=172, x0=50, x1=446),
            _span(1, _TORN_TAIL, top=174, bottom=186, x0=70, x1=440),
        )
    )

    assert head in texts
    assert _TORN_TAIL in texts


def test_r7_heading_is_not_joined() -> None:
    # A line typed heading inside the notes (a per-chapter label, or a reference fragment
    # import set as a heading) is never a side of a join, whatever its punctuation.
    spans = _notes_page(
        _span(1, "1. A complete first note that ends its own sentence here.", top=160, bottom=172, x0=50, x1=420),
        _span(1, "Chapter Two Of The Book Under Discussion", top=190, bottom=204, x0=50, x1=446, font_size=13, bold=True),
        _span(1, _TORN_TAIL, top=206, bottom=218, x0=70, x1=440),
    )
    paragraphs = build_paragraph_units_from_text_spans(spans).paragraphs
    heading = next(p for p in paragraphs if p.text.startswith("Chapter Two"))

    assert heading.role == "heading"
    assert heading.text == "Chapter Two Of The Book Under Discussion"
    assert _TORN_TAIL in [p.text for p in paragraphs]


def test_r7_second_paragraph_of_a_note_after_a_sentence_end_is_not_joined() -> None:
    # A note of two paragraphs: the first ends a sentence. The model keeps seeing two
    # paragraphs there, even though its last line ran to the column edge.
    first = "1. The first paragraph of this note ends a sentence right at the edge."
    second = "Further paragraph of the same note continues the argument."
    texts = _texts(
        _notes_page(
            _span(1, first, top=160, bottom=172, x0=50, x1=448),
            _span(1, second, top=174, bottom=186, x0=70, x1=400),
        )
    )

    assert first in texts
    assert second in texts


def test_r7_short_last_line_is_an_entry_end_even_without_punctuation() -> None:
    # Money & Sustainability's bibliography: entries carry no final period. The line ended
    # well before the column edge, so the next word would have fit -- a new entry, not a wrap.
    first = "1. Georg Friedrich Knapp, The State Theory of Money [1924]"
    second = "Anthony B. Atkinson and S. Morelli and others, An Inequality Database"
    texts = _texts(
        _notes_page(
            _span(1, first, top=160, bottom=172, x0=50, x1=330),
            _span(1, second, top=174, bottom=186, x0=70, x1=380),
        )
    )

    assert first in texts
    assert second in texts


def test_r7_blank_line_between_is_a_boundary() -> None:
    texts = _texts(
        _notes_page(
            _span(1, _TORN_HEAD, top=160, bottom=172, x0=50, x1=446),
            _span(1, _TORN_TAIL, top=190, bottom=202, x0=70, x1=440),
        )
    )

    assert _TORN_HEAD in texts
    assert _TORN_TAIL in texts


def test_r7_same_tear_outside_a_notes_section_is_left_alone() -> None:
    # The rule is scoped to the notes / reference region a back-matter title anchors.
    texts = _texts(
        _notes_page(
            _span(1, _TORN_HEAD, top=160, bottom=172, x0=50, x1=446),
            _span(1, _TORN_TAIL, top=174, bottom=186, x0=70, x1=440),
            title="Overview",
        )
    )

    assert _TORN_HEAD in texts
    assert _TORN_TAIL in texts


def test_r7_locator_abbreviation_waits_for_its_number() -> None:
    # VoE "33. Barba and de Vivo, ..., pp." + "1490-91.": a period after a short lowercase
    # token, before a line that opens with a digit, is a locator, not a sentence end.
    head = "33. Barba and de Vivo, An unproductive labour view of finance, pp."
    texts = _texts(
        _notes_page(
            _span(1, head, top=160, bottom=172, x0=50, x1=445),
            _span(1, "1490–91.", top=174, bottom=186, x0=70, x1=120),
        )
    )

    assert f"{head} 1490–91." in texts


def test_r7_compound_broken_at_its_hyphen_keeps_the_hyphen_without_a_space() -> None:
    head = "20. B. Christophers, Banking Across Boundaries (Chichester: Wiley-"
    texts = _texts(
        _notes_page(
            _span(1, head, top=160, bottom=172, x0=50, x1=420),
            _span(1, "Blackwell, 2013), p. 38.", top=174, bottom=186, x0=70, x1=200),
        )
    )

    assert f"{head}Blackwell, 2013), p. 38." in texts


def test_r7_line_back_at_the_entry_margin_starts_a_new_entry() -> None:
    # VoE bibliography shape: an address that overran the column reads as a full line, and the
    # next entry has no author ("'Fiscal policy ...', World Economic Outlook"). It starts back at
    # the entry margin, left of the wrapped line above it, so it is a new entry.
    url = "https://www.gov.uk/government/uploads/system/uploads/attachment_data/file/228786/7529.pdf"
    entry = "‘Fiscal policy as a countercyclical tool’, World Economic Outlook (2008)."
    spans = _notes_page(
        _span(1, "1. Hutton, D., Smith, I. R. and Hooper, R., Modernise or Decline: Policies to", top=160, bottom=172, x0=50, x1=446),
        _span(1, url, top=174, bottom=186, x0=70, x1=600),
        _span(1, entry, top=188, bottom=200, x0=50, x1=430),
    )
    texts = _texts(spans)

    assert any(text.endswith("7529.pdf") for text in texts)
    assert entry in texts


def test_r7_tear_across_a_page_break_is_joined() -> None:
    spans = _notes_page(_span(1, _TORN_HEAD, top=760, bottom=772, x0=50, x1=446))
    spans.append(_span(2, _TORN_TAIL, top=60, bottom=72, x0=70, x1=440))

    texts = _texts(spans)

    assert f"{_TORN_HEAD} {_TORN_TAIL}" in texts


# Spec 065 FR-008 (I-2): roles inside a notes section. A group title -- the line after which
# the entry numbering starts again, set in another size -- is a heading; a wrapped line of an
# entry the classifier typed heading is not. Form and geometry only.


def _notes_title_unit(top: float = 120) -> ParagraphUnit:
    return ParagraphUnit(
        text="Notes",
        role="heading",
        structural_role="heading",
        heading_level=2,
        font_size_pt=18,
        origin_raw_indexes=[int(round(top))],
        origin_raw_texts=["Notes"],
    )


def _line_unit(span: PdfTextSpan, *, role: str, level: int | None = None) -> ParagraphUnit:
    return ParagraphUnit(
        text=span.text,
        role=role,
        structural_role=role,
        heading_level=level,
        font_size_pt=span.font_size,
        origin_raw_indexes=[(span.page_number - 1) * 10000 + int(round(span.top))],
        origin_raw_texts=[span.text],
    )


def test_065_fr008_group_title_before_a_numbering_restart_is_a_heading() -> None:
    # VoE "INTRODUCTION: MAKING VERSUS TAKING": body, one line, in a smaller size than the
    # note 1 that follows it. It becomes a heading below the section title, never at a
    # chapter's level.
    last = _span(1, "14. Forbes, 2017.", top=160, bottom=172, x0=50, x1=150)
    title = _span(1, "INTRODUCTION: A GROUP OF NOTES", top=190, bottom=198, x0=150, x1=350, font_size=8)
    first = _span(1, "1. The first note of the introduction ends a sentence.", top=210, bottom=222, x0=50, x1=420)
    units = [
        _notes_title_unit(),
        _line_unit(last, role="list"),
        _line_unit(title, role="body"),
        _line_unit(first, role="list"),
    ]

    logical_import._settle_back_matter_entry_roles(units, _notes_page(last, title, first))

    assert units[2].role == "heading"
    assert units[2].heading_level == 3
    assert units[1].role == "list" and units[3].role == "list"


def test_065_fr008_numbered_group_title_out_of_sequence_is_a_heading() -> None:
    # VoE "1. A BRIEF HISTORY OF VALUE" after note 20, before note 1 of its own group.
    paragraphs = build_paragraph_units_from_text_spans(
        _notes_page(
            _span(1, "4. A note of the previous group ends its own sentence.", top=160, bottom=172, x0=50, x1=420),
            _span(1, "5. The last note of the previous group ends a sentence.", top=174, bottom=186, x0=50, x1=420),
            _span(1, "2. A GROUP TITLE IN CAPITALS", top=200, bottom=208, x0=150, x1=350, font_size=8),
            _span(1, "1. The first note of the group ends its own sentence.", top=220, bottom=232, x0=50, x1=420),
        )
    ).paragraphs
    title = next(p for p in paragraphs if p.text == "2. A GROUP TITLE IN CAPITALS")

    assert title.role == "heading"


def test_065_fr008_last_note_before_a_restart_stays_a_note() -> None:
    # Counterexamples: a book without group titles. The last note of a chapter is followed by
    # note 1 of the next one -- set in the entries' own size, or the next number of its own
    # sequence; neither is a title.
    same_size = build_paragraph_units_from_text_spans(
        _notes_page(
            _span(1, "1. A first note of the chapter ends its own sentence.", top=160, bottom=172, x0=50, x1=420),
            _span(1, "Ibid., p. 4", top=174, bottom=186, x0=50, x1=150),
            _span(1, "1. The first note of the next chapter ends a sentence.", top=188, bottom=200, x0=50, x1=420),
        )
    ).paragraphs
    in_sequence = build_paragraph_units_from_text_spans(
        _notes_page(
            _span(1, "1. A first note of the chapter ends its own sentence.", top=160, bottom=172, x0=50, x1=420),
            _span(1, "2. A SMALL PRINT NOTE", top=180, bottom=188, x0=50, x1=150, font_size=8),
            _span(1, "1. The first note of the next chapter ends a sentence.", top=200, bottom=212, x0=50, x1=420),
        )
    ).paragraphs

    assert next(p for p in same_size if p.text == "Ibid., p. 4").role != "heading"
    assert next(p for p in in_sequence if p.text == "2. A SMALL PRINT NOTE").role != "heading"


def test_065_fr008_wrapped_entry_line_typed_heading_becomes_body_and_joins() -> None:
    # VoE block 600: "32. T. Atkinson, ... Measurement of" + a wrapped line the classifier typed
    # h3 + "(Basingstoke ... 2005)." -- the join never crosses a heading, so the entry stayed torn.
    head = _span(1, "32. T. Atkinson, Atkinson Review: Final Report. Measurement of", top=160, bottom=172, x0=50, x1=446)
    fragment = _span(1, "Government Output and Productivity for the National Accounts", top=174, bottom=186, x0=70, x1=446)
    tail = _span(1, "(Basingstoke and New York: Palgrave Macmillan, 2005).", top=188, bottom=200, x0=70, x1=360)
    spans = _notes_page(head, fragment, tail)
    units = [
        _notes_title_unit(),
        _line_unit(head, role="list"),
        _line_unit(fragment, role="heading", level=3),
        _line_unit(tail, role="body"),
    ]

    settled = logical_import._settle_back_matter_entry_roles(units, spans)
    profile = logical_import._build_heading_layout_profile(spans, repeated_furniture_keys=set())
    joined = logical_import._join_torn_back_matter_entries(settled, spans, layout_profile=profile)

    assert units[2].role == "body" and units[2].heading_level is None
    assert [u.text for u in joined][1] == f"{head.text} {fragment.text} {tail.text}"


def test_065_fr008_heading_set_apart_inside_notes_stays_a_heading() -> None:
    # Counterexamples: a real heading inside the notes -- a blank line above it at the entries'
    # size, or the very next line but in its own size -- is not an entry fragment.
    entry = _span(1, "1. A first note of the section ends its own sentence here at the edge", top=160, bottom=172, x0=50, x1=446)
    apart = _span(1, "A Heading Set Apart By A Blank Line", top=200, bottom=212, x0=50, x1=300)
    other_size = _span(1, "A Heading In Its Own Size", top=174, bottom=188, x0=50, x1=300, font_size=13)
    for heading in (apart, other_size):
        units = [_notes_title_unit(), _line_unit(entry, role="list"), _line_unit(heading, role="heading", level=3)]

        logical_import._settle_back_matter_entry_roles(units, _notes_page(entry, heading))

        assert units[2].role == "heading" and units[2].heading_level == 3


def test_065_fr008_heading_outside_a_notes_section_is_not_touched() -> None:
    entry = _span(1, "1. A numbered paragraph of the body ends at the edge of the column", top=160, bottom=172, x0=50, x1=446)
    fragment = _span(1, "Government Output and Productivity", top=174, bottom=186, x0=70, x1=300)
    title = _notes_title_unit()
    title.text = "Overview"
    title.origin_raw_texts = ["Overview"]
    units = [title, _line_unit(entry, role="list"), _line_unit(fragment, role="heading", level=3)]

    logical_import._settle_back_matter_entry_roles(units, _notes_page(entry, fragment, title="Overview"))

    assert units[2].role == "heading"


# Spec 065 FR-009 (I-3): a sentence that wrapped before a number ("...the Battle of Waterloo in"
# + "1815. He was said ...") is one paragraph, not a body paragraph and a numbered-list item.

_WRAP_HEAD = "A running body line that establishes the leading tells how the bank, during"
_WRAP_NUMBER = "1815. He was said to have made a fortune from holding on to the bonds."


def _body_lead_spans(page: int = 1) -> list[PdfTextSpan]:
    return [
        _span(page, "A first running body line that establishes the document leading here.", top=40, bottom=54, x1=446),
        _span(page, "A second running body line that establishes the document leading too", top=56, bottom=70, x1=448),
    ]


def test_065_fr009_number_after_a_mid_sentence_wrap_continues_the_paragraph() -> None:
    texts = _texts(
        _body_lead_spans()
        + [
            _span(1, _WRAP_HEAD, top=72, bottom=86, x1=447),
            _span(1, _WRAP_NUMBER, top=88, bottom=102, x1=420),
        ]
    )

    assert any(f"{_WRAP_HEAD} {_WRAP_NUMBER}" in text for text in texts)
    assert _WRAP_NUMBER not in texts


def test_065_fr009_number_at_the_top_of_the_next_page_continues_the_paragraph() -> None:
    texts = _texts(
        _body_lead_spans()
        + [
            _span(1, _WRAP_HEAD, top=760, bottom=774, x1=447),
            _span(2, _WRAP_NUMBER, top=40, bottom=54, x1=420),
        ]
    )

    assert any(f"{_WRAP_HEAD} {_WRAP_NUMBER}" in text for text in texts)


def test_065_fr009_list_announced_by_a_closed_line_stays_a_list() -> None:
    # Counterexamples: a real list follows a line that closes (a colon), or one that ends
    # short of the margin.
    for head in (
        "A running body line that establishes the leading names the three steps:",
        "The three steps are",
    ):
        paragraphs = build_paragraph_units_from_text_spans(
            _body_lead_spans()
            + [
                _span(1, head, top=72, bottom=86, x1=447 if head.endswith(":") else 160),
                _span(1, "1. Collect the data from every branch of the bank.", top=88, bottom=102, x1=380),
            ]
        ).paragraphs

        item = next(p for p in paragraphs if p.text.startswith("1. Collect"))
        assert item.role == "list"


def test_065_fr009_next_item_of_a_running_list_stays_a_list() -> None:
    # Counterexample: the item before a wrapped, open line was number 1; "2." is the next item
    # of that list, whatever the line above it looks like.
    first = _span(1, "1. The first item of the list opens the enumeration here.", top=72, bottom=86, x1=400)
    wrapped = _span(1, "a body line of the first item that runs to the right edge and", top=88, bottom=102, x1=447)
    second = _span(1, "2. The second item of the list follows its own number.", top=104, bottom=118, x1=380)
    spans = _body_lead_spans() + [first, wrapped, second]
    units = [
        _line_unit(first, role="list"),
        _line_unit(wrapped, role="body"),
        _line_unit(second, role="list"),
    ]
    profile = logical_import._build_heading_layout_profile(spans, repeated_furniture_keys=set())

    joined = logical_import._join_numbered_body_continuations(units, spans, layout_profile=profile)

    assert [u.role for u in joined] == ["list", "body", "list"]


def test_065_fr009_next_note_after_an_address_inside_notes_is_not_joined() -> None:
    # Counterexample: inside a notes section an entry number after an address that ran to the
    # margin opens the next entry; that region belongs to the notes-join.
    address = _span(1, "http://www.example.org/archive/documents/historic/speeches/speech409", top=174, bottom=186, x0=70, x1=447)
    note = _span(1, "10. Source: a bureau of statistics, own calculations.", top=188, bottom=200, x0=50, x1=380)
    spans = _notes_page(address, note)
    units = [_notes_title_unit(), _line_unit(address, role="body"), _line_unit(note, role="list")]
    profile = logical_import._build_heading_layout_profile(spans, repeated_furniture_keys=set())

    joined = logical_import._join_numbered_body_continuations(units, spans, layout_profile=profile)

    assert [u.role for u in joined] == ["heading", "body", "list"]


# Spec 067 FR-007 (I-3): a running head that stands on the page-number line is page furniture
# even when only one or two pages carry it (Rethinking Money's "FOREWORD" on pages 13-14 and
# "CONTENTS" on page 11 reached the body: glued to a paragraph start, or an extra heading).

_FOLIO_TOP, _FOLIO_BOTTOM = 35.6, 47.9


def _foreword_page(page: int, folio: str, *, head: str = "FOREWORD", head_top: float = 37.4) -> list[PdfTextSpan]:
    return [
        _span(page, folio, top=_FOLIO_TOP, bottom=_FOLIO_BOTTOM, x0=42, x1=48, font_size=10.5),
        _span(page, head, top=head_top, bottom=head_top + 10.5, x0=78, x1=125, font_size=10.5),
    ]


def test_067_fr007_running_head_on_the_folio_line_is_dropped_with_the_number() -> None:
    spans = (
        _body_lead_spans()
        + [_span(1, "the ingenuity of the local population of the town can be", top=760, bottom=774, x1=447)]
        + _foreword_page(2, "xi")
        + [_span(2, "galvanized; with their own money they are empowered to act.", top=100, bottom=114, x1=420)]
    )

    result = build_paragraph_units_from_text_spans(spans)
    texts = [p.text for p in result.paragraphs]

    assert not any("FOREWORD" in text for text in texts)
    assert any("town can be galvanized; with their own money" in text for text in texts)
    assert result.report.skipped_repeated_page_furniture_count == 1
    assert result.report.skipped_page_number_count == 1


def test_067_fr007_short_line_off_the_folio_line_is_kept() -> None:
    # Counterexamples. A short line in the top band that does not stand on the number's line
    # (set a full line lower), and one on a page that has no page number at all, are text.
    lower = _foreword_page(2, "xi", head="Preface to the reader", head_top=60)
    no_number = [_span(3, "Acknowledgements", top=37.4, bottom=47.9, x0=78, x1=170, font_size=10.5)]
    spans = (
        _body_lead_spans()
        + lower
        + [_span(2, "A body line on the second page that ends its sentence here.", top=100, bottom=114, x1=420)]
        + no_number
        + [_span(3, "A body line on the third page that ends its sentence here too.", top=100, bottom=114, x1=420)]
    )

    texts = [p.text for p in build_paragraph_units_from_text_spans(spans).paragraphs]

    assert any("Preface to the reader" in text for text in texts)
    assert any("Acknowledgements" in text for text in texts)


# Spec 067 FR-005 (I-1): a body paragraph torn at a page break, whose second half opens with a
# capital, a digit, a quote or a bracket ("...bodies such as the" / "International Monetary
# Fund ..."), is one paragraph. The text-only soft-wrap merge joins only a lowercase start.

_TEAR_HEAD = "and those of the powerful multilateral bodies such as the"
_TEAR_TAIL = "International Monetary Fund and the World Bank set the terms of the loans."


def _torn_page_spans(
    *,
    head_x1: float = 449,
    tail: str = _TEAR_TAIL,
    second_page_body: bool = True,
) -> list[PdfTextSpan]:
    second_page = (
        _body_page(2, top=60)
        if second_page_body
        else [_span(2, f"Short line {index}.", top=60 + index * 14, bottom=70 + index * 14, x1=140) for index in range(4)]
    )
    return [
        *_body_page(1, top=40),
        _span(1, _TEAR_HEAD, top=760, bottom=770, x1=head_x1),
        _span(2, tail, top=40, bottom=50, x1=446),
        *second_page,
    ]


def test_067_fr005_paragraph_torn_at_a_page_break_is_joined() -> None:
    result = build_paragraph_units_from_text_spans(_torn_page_spans())
    texts = [p.text for p in result.paragraphs]

    assert any(f"{_TEAR_HEAD} {_TEAR_TAIL}" in text for text in texts)
    joined = next(p for p in result.paragraphs if _TEAR_HEAD in p.text)
    assert joined.boundary_rationale == "merged_page_torn_body_continuation"


def test_067_fr005_second_half_opening_with_a_digit_or_a_quote_is_joined() -> None:
    for tail in (
        "2008 crisis) to bring over-the-counter derivatives onto exchanges was taken.",
        "‘de-risking’. And it must not be about levelling the field for the incumbents.",
    ):
        texts = _texts(_torn_page_spans(tail=tail))

        assert any(f"{_TEAR_HEAD} {tail}" in text for text in texts), tail


def test_067_fr005_line_that_ended_short_of_the_margin_is_not_joined() -> None:
    # Counterexample: the last line stops well before the right edge -- the next word would
    # have fit, so the line ended for a reason of its own (a title line, a new section).
    texts = _texts(_torn_page_spans(head_x1=300))

    assert _TEAR_HEAD in texts
    assert not any(f"{_TEAR_HEAD} International" in text for text in texts)


def test_067_fr005_page_without_running_text_is_not_joined() -> None:
    # Counterexample: the next page carries no running text (an index column, the end of the
    # notes, a caption page) -- the top line there is not read as the paragraph's second half.
    texts = _texts(_torn_page_spans(second_page_body=False))

    assert not any(f"{_TEAR_HEAD} International" in text for text in texts)


def test_067_fr005_list_item_at_the_top_of_the_next_page_stays_a_list() -> None:
    texts = _texts(_torn_page_spans(tail="• International Monetary Fund lending rules."))

    assert not any(_TEAR_HEAD in text and "International" in text for text in texts)


def _torn_units(spans: list[PdfTextSpan]) -> tuple[ParagraphUnit, ParagraphUnit]:
    head_span = next(s for s in spans if s.text == _TEAR_HEAD)
    tail_span = next(s for s in spans if s.text == _TEAR_TAIL)
    return _line_unit(head_span, role="body"), _line_unit(tail_span, role="body")


def _join_page_tears(units: list[ParagraphUnit], spans: list[PdfTextSpan]) -> list[ParagraphUnit]:
    profile = logical_import._build_heading_layout_profile(spans, repeated_furniture_keys=set())
    return logical_import._join_page_torn_body_paragraphs(
        units, spans, layout_profile=profile, repeated_furniture_keys=set()
    )


def test_067_fr005_units_join_and_a_table_cell_refuses() -> None:
    spans = _torn_page_spans()
    head, tail = _torn_units(spans)
    assert len(_join_page_tears([head, tail], spans)) == 1

    head, tail = _torn_units(spans)
    tail.is_pdf_table_cell = True
    assert len(_join_page_tears([head, tail], spans)) == 2


def test_067_fr005_notes_section_is_left_to_the_notes_join() -> None:
    spans = _torn_page_spans()
    head, tail = _torn_units(spans)

    joined = _join_page_tears([_notes_title_unit(), head, tail], spans)

    assert [u.text for u in joined] == ["Notes", _TEAR_HEAD, _TEAR_TAIL]


# Spec 067 FR-006 follow-up: the sentence-end paragraph boundary inside a quotation or a box
# reads the box's own left edge, not the body margin (Money and Sustainability, Box 4.1: body at
# x0 5.0, the box at 33.8; "...evenly mixed.” ¹¹" / "Entropy is time’s arrow ...").

_INSET_X0 = 33.8
_INSET_FULL = "these are words of a quotation set inside a box that runs to its right edge"


def _wide_body_lines() -> list[PdfTextSpan]:
    return [
        _span(1, f"Body line {index} of running prose that is set across the whole page width here.", top=40 + index * 18, bottom=54 + index * 18, x0=5, x1=607, font_size=14.4)
        for index in range(8)
    ]


def _inset(*lines: tuple[str, float]) -> list[PdfTextSpan]:
    return [
        _span(1, text, top=400 + index * 8.6, bottom=405.8 + index * 8.6, x0=_INSET_X0, x1=x1, font_size=5.76)
        for index, (text, x1) in enumerate(lines)
    ]


def test_067_inset_sentence_end_at_the_box_edge_is_a_paragraph_boundary() -> None:
    texts = _texts(
        _wide_body_lines()
        + _inset(
            (_INSET_FULL, 607),
            ("and cream poured into coffee dissipates until it is evenly mixed.” ¹¹", 267),
            ("Entropy is time’s arrow. Without entropy there would be no way to tell the past", 607),
            ("from the future, and the box goes on with its argument here.", 400),
        )
    )

    assert any(text.endswith("evenly mixed.” ¹¹") for text in texts)
    assert any(text.startswith("Entropy is time’s arrow.") for text in texts)


def test_067_inset_line_that_does_not_end_a_sentence_still_merges() -> None:
    texts = _texts(
        _wide_body_lines()
        + _inset(
            (_INSET_FULL, 607),
            ("and cream poured into coffee dissipates until it is evenly", 267),
            ("Mixed with milk, the coffee is lighter and the box goes on with its argument here.", 607),
        )
    )

    assert any("dissipates until it is evenly Mixed with milk" in text for text in texts)


def test_067_body_margin_sentence_end_behaves_as_before() -> None:
    # At the body margin the boundary is the one `_is_near_body_left` always made; a short
    # sentence-ending line followed by a new sentence at the margin starts a paragraph.
    spans = _wide_body_lines() + [
        _span(1, "The last line of a body paragraph ends here.", top=200, bottom=214, x0=5, x1=300, font_size=14.4),
        _span(1, "A new paragraph begins at the margin and runs across the page width here.", top=218, bottom=232, x0=5, x1=607, font_size=14.4),
    ]
    texts = _texts(spans)

    assert any(text.endswith("The last line of a body paragraph ends here.") for text in texts)
    assert any(text.startswith("A new paragraph begins at the margin") for text in texts)
