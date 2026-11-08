from __future__ import annotations

import json
import importlib.util
from pathlib import Path

from docxaicorrector.pdf_import.text_layer_quality import (
    PdfTextSpan,
    _detect_running_heads_on_page_number_line,
    _document_reference_font_size,
    _font_style_flags,
    _inline_superscript_marker_char_ids,
    _line_text_with_char_overrides,
    _normalize_style_runs,
    _pdf_text_span_from_chars,
    _pdfminer_top_origin_bounds,
    _split_trailing_superscript_marker_chars,
    _style_runs_from_line_items,
    _trailing_marker_split_left_to_importer,
    build_text_layer_quality_report,
    extract_pdf_text_spans_with_pdfminer,
    load_spans_json,
    unsupported_quality_report,
)


def _span(
    page: int,
    text: str,
    *,
    top: float = 200,
    bottom: float = 220,
    page_height: float = 800,
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
        page_height=page_height,
        font_name="SourceSerif-Bold" if bold else "SourceSerif",
        font_size=font_size,
        is_bold=bold,
        is_italic=italic,
    )


class _FakePdfMinerChar:
    def __init__(self, text: str, *, size: float, x0: float, x1: float, y0: float, y1: float) -> None:
        self._text = text
        self.size = size
        self.x0 = x0
        self.x1 = x1
        self.y0 = y0
        self.y1 = y1
        self.fontname = "SourceSerif"

    def get_text(self) -> str:
        return self._text


def test_pdfminer_line_split_detects_trailing_superscript_marker() -> None:
    chars = [
        _FakePdfMinerChar("O", size=10, x0=10, x1=18, y0=100, y1=110),
        _FakePdfMinerChar("K", size=10, x0=18, x1=26, y0=100, y1=110),
        _FakePdfMinerChar(".", size=10, x0=26, x1=29, y0=100, y1=110),
        _FakePdfMinerChar("2", size=4, x0=28, x1=30, y0=105, y1=109),
    ]

    split = _split_trailing_superscript_marker_chars(chars)

    assert split is not None
    body, marker = split
    assert "".join(char.get_text() for char in body) == "OK."
    assert "".join(char.get_text() for char in marker) == "2"


class _StyledChar:
    def __init__(self, text: str, fontname: str) -> None:
        self._text = text
        self.fontname = fontname

    def get_text(self) -> str:
        return self._text


class _AnnoChar:
    # Mirrors pdfminer LTAnno: virtual layout character with no ``fontname``.
    def __init__(self, text: str) -> None:
        self._text = text

    def get_text(self) -> str:
        return self._text


def test_font_style_flags_reads_trailing_style_chunk() -> None:
    assert _font_style_flags("DODEEN+NewCaledoniaLTStd-It") == (False, True)
    assert _font_style_flags("Arial-BoldItalicMT") == (True, True)
    assert _font_style_flags("BGKDGP+TimesNewRoman,Italic") == (False, True)
    assert _font_style_flags("DidotLTStd-Bold") == (True, False)
    assert _font_style_flags("ITCFranklinGothicStd-Demi") == (True, False)


def test_font_style_flags_ignores_family_name_traps() -> None:
    # Bare ``BT`` in a family name is not bold; ``it`` inside a family name (Didot,
    # NewCaledonia) is not italic; a name with no style separator is regular.
    assert _font_style_flags("DODABN+NewsGothicBT-Reg") == (False, False)
    assert _font_style_flags("DODBHH+DidotLTStd-Roman") == (False, False)
    assert _font_style_flags("DODEGN+NewCaledoniaLTStd") == (False, False)
    assert _font_style_flags("AAAAAA+LiberationSerif") == (False, False)


def test_font_style_flags_bold_weight_in_family_stays_conservative() -> None:
    # The bold weight is baked into the family segment ("Bd"), only the upright/italic
    # axis is in the tail ("-Reg"). Per the tail-only rule this reads as not-bold; the
    # italic axis is still recovered from the tail.
    assert _font_style_flags("DOCPNN+NewsGothicBdBT-Reg") == (False, False)
    assert _font_style_flags("DOCPPN+NewsGothicBdBT-It") == (False, True)


def test_style_runs_from_line_items_groups_mixed_styles() -> None:
    items = [
        _StyledChar("m", "Body"),
        _StyledChar("i", "Body"),
        _StyledChar("x", "Body"),
        _AnnoChar(" "),
        _StyledChar("i", "Body-It"),
        _StyledChar("t", "Body-It"),
        _AnnoChar(" "),
        _StyledChar("b", "Body-Bold"),
    ]
    runs = _style_runs_from_line_items(items)
    assert "".join(text for text, _, _ in runs) == "mix it b"
    assert runs == (
        ("mix", False, False),
        (" it", False, True),
        (" b", True, False),
    )


def test_normalize_style_runs_collapses_and_strips_whitespace() -> None:
    runs = _normalize_style_runs(
        [
            ("  lead", False, True),
            ("   mid  ", False, True),
            ("tail   ", True, False),
        ]
    )
    assert "".join(text for text, _, _ in runs) == "lead mid tail"


def test_pdfminer_line_split_detects_attribution_trailing_superscript_marker() -> None:
    chars = [
        _FakePdfMinerChar("K", size=10, x0=10, x1=18, y0=100, y1=110),
        _FakePdfMinerChar("o", size=10, x0=18, x1=26, y0=100, y1=110),
        _FakePdfMinerChar("f", size=10, x0=26, x1=34, y0=100, y1=110),
        _FakePdfMinerChar("i", size=10, x0=34, x1=38, y0=100, y1=110),
        _FakePdfMinerChar(" ", size=10, x0=38, x1=42, y0=100, y1=110),
        _FakePdfMinerChar("A", size=10, x0=42, x1=50, y0=100, y1=110),
        _FakePdfMinerChar("n", size=10, x0=50, x1=58, y0=100, y1=110),
        _FakePdfMinerChar("n", size=10, x0=58, x1=66, y0=100, y1=110),
        _FakePdfMinerChar("a", size=10, x0=66, x1=74, y0=100, y1=110),
        _FakePdfMinerChar("n", size=10, x0=74, x1=82, y0=100, y1=110),
        _FakePdfMinerChar("2", size=4, x0=82, x1=84, y0=105, y1=109),
        _FakePdfMinerChar("8", size=4, x0=84, x1=86, y0=105, y1=109),
    ]

    split = _split_trailing_superscript_marker_chars(chars)

    assert split is not None
    body, marker = split
    assert "".join(char.get_text() for char in body) == "Kofi Annan"
    assert "".join(char.get_text() for char in marker) == "28"


# --------------------------------------------------------------------------------------
# Footnote references set inside a line
#
# What a reader sees is the delivered text, so every test below asserts on the span TEXT
# the extractor produces for a line, built exactly the way
# ``extract_pdf_text_spans_with_pdfminer`` builds it: detect the references, then render
# the line and its style runs through the same override map.
# --------------------------------------------------------------------------------------

def _pdf_line(pieces: list[tuple[str, float, float]]) -> list[_FakePdfMinerChar]:
    """Build a line of characters from ``(text, font_size, baseline)`` groups."""
    chars: list[_FakePdfMinerChar] = []
    x = 10.0
    for text, size, baseline in pieces:
        for character in text:
            width = size * 0.5
            chars.append(
                _FakePdfMinerChar(
                    character, size=size, x0=x, x1=x + width, y0=baseline, y1=baseline + size
                )
            )
            x += width
    return chars


def _extracted_line_text(chars: list[_FakePdfMinerChar]) -> str:
    return _line_text_with_char_overrides(chars, _inline_superscript_marker_char_ids(chars))


def _extracted_line_runs(chars: list[_FakePdfMinerChar]) -> tuple[tuple[str, bool, bool], ...]:
    return _style_runs_from_line_items(
        chars, char_text_overrides=_inline_superscript_marker_char_ids(chars)
    )


def test_pdfminer_line_renders_mid_line_footnote_reference_as_superscript() -> None:
    # The shape the owner reported: a reference welded to the end of a sentence in the
    # MIDDLE of a line, which the end-of-line split can never reach.
    chars = _pdf_line([("plunged.", 10, 100), ("2", 6.5, 104), (" The bank", 10, 100)])

    assert _extracted_line_text(chars) == "plunged.² The bank"


def test_pdfminer_line_renders_undersized_end_of_line_reference_as_superscript() -> None:
    # A reference at the end of the line set at 0.75 of the body size: too large for the
    # 0.62 bound the end-of-line split applies, so it survived welded to the word.
    chars = _pdf_line([("expansion.", 10, 100), ("3", 7.5, 105)])

    assert _split_trailing_superscript_marker_chars(chars) is None
    assert _extracted_line_text(chars) == "expansion.³"


def test_pdfminer_line_keeps_lowered_digit_welded_to_word() -> None:
    # "CO2": smaller than the text but set BELOW its baseline. A subscript is not a
    # reference, and rewriting it would corrupt the formula.
    chars = _pdf_line([("more CO", 10, 100), ("2", 7.5, 98), (" means", 10, 100)])

    assert _extracted_line_text(chars) == "more CO2 means"


def test_pdfminer_line_keeps_body_size_raised_digit_welded_to_word() -> None:
    # Raised but set at the size of the BODY, in a document whose references are smaller
    # (spec 067 FR-006 rewords what this test meant): neither smaller than its line nor at
    # the document's reference size, so it stays a number -- with the reference size known
    # and without it.
    chars = _pdf_line([("the GDP.", 10, 100), ("9", 10, 104)])

    assert _extracted_line_text(chars) == "the GDP.9"
    assert (
        _line_text_with_char_overrides(
            chars, _inline_superscript_marker_char_ids(chars, reference_font_size=6.5)
        )
        == "the GDP.9"
    )


def test_pdfminer_line_keeps_number_split_across_a_line_break() -> None:
    # "$16.58" wrapped so that "58" follows the decimal point with no space: welded by
    # shape, but full size and on the baseline.
    chars = _pdf_line([("from $5.49 trillion to $16.", 10, 100), ("58", 10, 100)])

    assert _extracted_line_text(chars) == "from $5.49 trillion to $16.58"


def test_pdfminer_line_renders_raised_undersized_digit_after_a_space() -> None:
    # Spec 063 FR-007 reverses what this test pinned until 2026-11-07 ("chapter 2 opens"):
    # a digit that is smaller than its line AND raised above it is a reference wherever it
    # stands. The weld was never the signal — the size and the rise are — and requiring it
    # left Rethinking Money's references set after a closing quote and a space
    # ("works.” 9") as plain numbers. Only the digit is rewritten; the space stays.
    chars = _pdf_line([("chapter ", 10, 100), ("2", 6.5, 104), (" opens", 10, 100)])

    assert _extracted_line_text(chars) == "chapter ² opens"


def test_pdfminer_line_renders_reference_after_an_inferred_space() -> None:
    # pdfminer reports the space it INFERS between two words as a separate layout item
    # with no font and no geometry. "paper 28" is Money and Sustainability's own case: a
    # reference set after the word with a space, which FR-007 reads by its form.
    chars: list[object] = list(_pdf_line([("paper", 10, 100)]))
    chars.append(_AnnoChar(" "))
    chars.extend(_pdf_line([("28", 6.5, 104)]))
    chars.extend(_pdf_line([(" gathered", 10, 100)]))

    assert _line_text_with_char_overrides(
        chars, _inline_superscript_marker_char_ids(chars)
    ) == "paper ²⁸ gathered"


# --- Spec 063 FR-007: references that do not touch the word before them -------------------


def test_pdfminer_line_renders_unattached_reference_between_a_word_and_a_sum() -> None:
    # The shape of the corpus blocker (VoE idx 592): "…nearly" + a raised, undersized "39"
    # + "£30,000". Read as plain digits, the model took "39 £30,000" for one sum.
    chars = _pdf_line(
        [("equivalent to nearly ", 15, 100), ("39", 9, 106.5), (" £30,000 for each", 15, 100)]
    )

    assert _extracted_line_text(chars) == "equivalent to nearly ³⁹ £30,000 for each"


def test_pdfminer_line_renders_unattached_reference_after_a_number() -> None:
    # VoE idx 583's shape: the reference follows a sum and a space. Nothing about what
    # precedes it is required — only the reference's own size and rise.
    chars = _pdf_line([("($1,300 ", 15, 100), ("36", 9, 106.5), (" billion)", 15, 100)])

    assert _extracted_line_text(chars) == "($1,300 ³⁶ billion)"


def test_pdfminer_line_renders_reference_opening_the_line() -> None:
    # At the line's start there is no text before the run; its rise is measured against
    # the text after it.
    chars = _pdf_line([("40", 9, 106.5), (" around the turn of the century.", 15, 100)])

    assert _extracted_line_text(chars) == "⁴⁰ around the turn of the century."


def test_pdfminer_line_keeps_full_size_number_after_a_space() -> None:
    # Anti-vacuum: "nearly 39" with "39" set at text size on the baseline is a number.
    chars = _pdf_line(
        [("equivalent to nearly ", 15, 100), ("39", 15, 100), (" million", 15, 100)]
    )

    assert _extracted_line_text(chars) == "equivalent to nearly 39 million"


def test_pdfminer_line_keeps_lowered_digit_after_a_space() -> None:
    # Anti-vacuum: smaller but LOWERED is a subscript, wherever it stands.
    chars = _pdf_line([("the CO ", 10, 100), ("2", 7.5, 98), (" level", 10, 100)])

    assert _extracted_line_text(chars) == "the CO 2 level"


def test_pdfminer_line_keeps_ordinary_numbers_beside_an_unattached_reference() -> None:
    # Anti-vacuum: the stand-alone rule touches the reference and nothing else on the line —
    # "CO2" (lowered), "$16.58" and "0.005" (full size, on the baseline) stay numbers.
    chars = _pdf_line(
        [
            ("CO", 10, 100),
            ("2", 7.5, 98),
            (" rose ", 10, 100),
            ("4", 6.5, 104),
            (" from $16.58 to 0.005 per unit", 10, 100),
        ]
    )

    assert _extracted_line_text(chars) == "CO2 rose ⁴ from $16.58 to 0.005 per unit"


def test_pdfminer_line_keeps_digit_inside_a_raised_exponent_group() -> None:
    # Rethinking Money p. 244: "(1 + i)^(n - 1)". The "1" of the exponent is small, raised
    # and follows a space — but so are the "(", "n" and "-" around it. A reference is raised
    # alone; a digit inside a raised group is a formula and stays a digit.
    chars = _pdf_line(
        [
            ("The exact formula is (1 + i) ", 9, 100),
            ("(n - 1)", 5.8, 103.9),
            (", where i is the rate", 9, 100),
        ]
    )

    assert _extracted_line_text(chars) == "The exact formula is (1 + i) (n - 1), where i is the rate"


def test_end_of_line_reference_raised_above_its_line_is_rendered_in_place() -> None:
    # The Value of Everything sets references at 0.60 of the body and raises them so far
    # that their top clears the line's. Split off, such a reference was read BEFORE its line
    # and re-bound to the previous one ("in 2011.36" arrived as "($1,300 36 billion)").
    # It is rendered where it is set instead.
    chars = _pdf_line([("less than £300 billion in 2011.", 15, 100), ("36", 9, 106.5)])
    overrides = _inline_superscript_marker_char_ids(chars)

    assert _split_trailing_superscript_marker_chars(chars) is not None
    assert _trailing_marker_split_left_to_importer(chars, overrides) is None
    assert _line_text_with_char_overrides(chars, overrides) == "less than £300 billion in 2011.³⁶"


def test_end_of_line_reference_under_its_line_top_keeps_the_importer_path() -> None:
    # Money and Sustainability's references (0.40 of the body) stay under the line's top;
    # the split and the importer's re-binding they have used since it was written stay.
    chars = _pdf_line([("OK.", 10, 100), ("2", 4, 105)])
    overrides = _inline_superscript_marker_char_ids(chars)

    split = _trailing_marker_split_left_to_importer(chars, overrides)

    assert split is not None
    assert _line_text_with_char_overrides(split[1], None) == "2"



def test_pdfminer_line_keeps_year_length_digit_run_welded_to_word() -> None:
    # References are numbered one to a few hundred. Four digits is a year or a sum.
    chars = _pdf_line([("year", 10, 100), ("1990", 6.5, 104), (" was", 10, 100)])

    assert _extracted_line_text(chars) == "year1990 was"


# --- Spec 065 FR-007: a reference welded to a clause comma or a closing ’ ------------------


def test_065_fr007_reference_welded_to_a_clause_comma_is_rendered_as_superscript() -> None:
    # The Value of Everything's shape, measured at (0.60, 0.44): "…through loans," + a small,
    # raised "30" + " as distinct from". The comma was missing from the anchor set, so the
    # reference reached the reader welded to the word ("кредитования,30").
    chars = _pdf_line([("money through loans,", 15, 100), ("30", 9, 106.5), (" as distinct", 15, 100)])

    assert _extracted_line_text(chars) == "money through loans,³⁰ as distinct"


def test_065_fr007_reference_welded_to_a_closing_single_quote_is_rendered_as_superscript() -> None:
    # "‘marginal revolution’" + "4" mid-line: the closing ’ is a closing quote like ”.
    chars = _pdf_line([("a ‘marginal revolution’", 15, 100), ("4", 9, 106.5), (" – it was", 15, 100)])

    assert _extracted_line_text(chars) == "a ‘marginal revolution’⁴ – it was"


def test_065_fr007_end_of_line_reference_after_a_closing_quote_is_rendered_in_place() -> None:
    # "…shall have to reject.’" + "10" at the end of the line, raised above the line's top
    # (VoE geometry): rendered where it is set, not split off and re-bound elsewhere.
    chars = _pdf_line([("shall have to reject.’", 15, 100), ("10", 9, 106.5)])
    overrides = _inline_superscript_marker_char_ids(chars)

    assert _trailing_marker_split_left_to_importer(chars, overrides) is None
    assert _line_text_with_char_overrides(chars, overrides) == "shall have to reject.’¹⁰"


def test_065_fr007_second_reference_after_a_comma_joins_the_first() -> None:
    # Rethinking Money: "dating.¹⁸,19" -- the first reference was taken, the second, welded
    # to the comma between them, was not.
    chars = _pdf_line([("compensated dating.", 10, 100), ("18", 6.5, 104), (",", 10, 100), ("19", 6.5, 104)])

    assert _extracted_line_text(chars) == "compensated dating.¹⁸,¹⁹"


def test_065_fr007_full_size_numbers_after_a_comma_or_quote_stay_numbers() -> None:
    # Anti-regression 4: the new anchors precede ordinary numbers far more often than
    # references (263 + 2 on the corpus) -- a thousands group, a run of years, a decade
    # abbreviated with ’. Full size on the baseline, every one stays a number.
    chars = _pdf_line(
        [
            ("from $1,", 10, 100),
            ("300", 10, 100),
            (" in 2010,", 10, 100),
            ("2011", 10, 100),
            (" and the ’", 10, 100),
            ("90", 10, 100),
            ("s", 10, 100),
        ]
    )

    assert _extracted_line_text(chars) == "from $1,300 in 2010,2011 and the ’90s"


def test_065_fr007_lowered_digit_after_a_comma_stays_a_digit() -> None:
    # Anti-regression 4: smaller but LOWERED after a comma is a subscript, not a reference.
    chars = _pdf_line([("water, CO,", 10, 100), ("2", 7.5, 98), (" and air", 10, 100)])

    assert _extracted_line_text(chars) == "water, CO,2 and air"


def test_065_fr007_year_after_a_comma_stays_a_number() -> None:
    # Anti-regression 4: a year after a comma, full size -- and a raised one is four digits,
    # past the three a reference may have.
    flat = _pdf_line([("in the year,", 10, 100), ("2011", 10, 100), (".", 10, 100)])
    raised = _pdf_line([("in the year,", 10, 100), ("2011", 6.5, 104)])

    assert _extracted_line_text(flat) == "in the year,2011."
    assert _extracted_line_text(raised) == "in the year,2011"


def test_pdfminer_line_preserves_every_reference_it_rewrites() -> None:
    # The marker-preservation invariant: each reference keeps its value and its position,
    # nothing is dropped, nothing is duplicated, and no other character moves.
    chars = _pdf_line(
        [
            ("month.", 10, 100),
            ("6", 6.5, 104),
            (" Savings are low.", 10, 100),
            ("7", 6.5, 104),
            (" Debt passed a trillion.", 10, 100),
            ("12", 6.5, 104),
        ]
    )

    text = _extracted_line_text(chars)

    assert text == (
        "month.⁶ Savings are low.⁷ Debt passed a trillion.¹²"
    )
    superscripts = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
    assert text.translate(superscripts) == "month.6 Savings are low.7 Debt passed a trillion.12"


def test_pdfminer_line_style_runs_still_reconstruct_the_rewritten_text() -> None:
    # ``_span_style_runs`` discards runs that do not reconstruct the span text, which
    # would silently drop every emphasis run on a line carrying a reference.
    chars = _pdf_line([("plunged.", 10, 100), ("2", 6.5, 104), (" The bank", 10, 100)])

    runs = _extracted_line_runs(chars)

    assert "".join(text for text, _, _ in runs) == _extracted_line_text(chars)


def test_pdfminer_end_of_line_reference_span_keeps_raw_digits() -> None:
    # The proven end-of-line path stays intact: when the split fires, the marker segment
    # is built WITHOUT the rewrite so the logical importer still recognises it as a
    # standalone ``\d{1,3}`` marker span and re-binds it itself.
    chars = _pdf_line([("OK.", 10, 100), ("2", 4, 105)])
    split = _split_trailing_superscript_marker_chars(chars)
    assert split is not None
    body_chars, marker_chars = split

    marker_span = _pdf_text_span_from_chars(marker_chars, page_number=1, page_height=800)
    body_span = _pdf_text_span_from_chars(
        body_chars,
        page_number=1,
        page_height=800,
        char_text_overrides=_inline_superscript_marker_char_ids(chars),
    )

    assert marker_span is not None and marker_span.text == "2"
    assert body_span is not None and body_span.text == "OK."


def test_pdfminer_line_split_rejects_normal_trailing_number() -> None:
    chars = [
        _FakePdfMinerChar("2", size=10, x0=10, x1=15, y0=100, y1=110),
        _FakePdfMinerChar("0", size=10, x0=15, x1=20, y0=100, y1=110),
        _FakePdfMinerChar("2", size=10, x0=20, x1=25, y0=100, y1=110),
        _FakePdfMinerChar("6", size=10, x0=25, x1=30, y0=100, y1=110),
    ]

    assert _split_trailing_superscript_marker_chars(chars) is None


def test_quality_report_filters_repeated_page_furniture_and_page_numbers() -> None:
    spans = [
        _span(1, "RETHINKING MONEY", top=20, bottom=35, font_size=8),
        _span(1, "1", top=750, bottom=765, font_size=8),
        _span(1, "First body paragraph.", font_size=10),
        _span(2, "RETHINKING MONEY", top=20, bottom=35, font_size=8),
        _span(2, "2", top=750, bottom=765, font_size=8),
        _span(2, "Second body paragraph.", font_size=10),
        _span(3, "RETHINKING MONEY", top=20, bottom=35, font_size=8),
        _span(3, "3", top=750, bottom=765, font_size=8),
        _span(3, "Third body paragraph.", font_size=10),
    ]

    report = build_text_layer_quality_report(spans)

    assert report.status == "ok"
    assert report.page_count == 3
    assert report.span_count == 9
    assert report.repeated_page_furniture_span_count == 3
    assert report.page_number_span_count == 3
    assert report.body_span_count == 3
    assert report.visible_text_chars == 106
    assert report.body_text_chars == 58
    assert report.repeated_page_furniture_text_chars == 45
    assert report.page_number_text_chars == 3
    assert report.body_text_ratio == 0.5472
    assert report.repeated_page_furniture_text_ratio == 0.4245
    assert report.decision == "scanned_or_unsupported"
    assert report.decision_reasons == ("too_little_text_layer",)


def test_pdfminer_bottom_origin_coordinates_are_normalized_to_top_origin() -> None:
    top, bottom = _pdfminer_top_origin_bounds(y0=760, y1=780, page_height=800)

    assert top == 20
    assert bottom == 40

    report = build_text_layer_quality_report(
        [
            _span(1, "RUNNING HEADER", top=top, bottom=bottom, page_height=800),
            _span(2, "RUNNING HEADER", top=top, bottom=bottom, page_height=800),
            _span(3, "RUNNING HEADER", top=top, bottom=bottom, page_height=800),
            _span(1, "Body text", top=200, bottom=220, page_height=800),
        ]
    )

    assert report.repeated_page_furniture_span_count == 3


def test_quality_report_detects_source_formatting_and_structure_candidates() -> None:
    spans = [
        _span(1, "Chapter Eight", font_size=12, bold=True),
        _span(1, "NATIONAL CURRENCY CRISIS SOLUTION?", font_size=16, bold=True),
        _span(1, "- a bullet item", font_size=10),
        _span(1, "body text with emphasis", font_size=10, italic=True),
    ]
    spans.extend(
        _span(1, "This is a regular body sentence with enough text for the quality gate.", font_size=10)
        for _ in range(30)
    )

    report = build_text_layer_quality_report(spans)

    assert report.heading_candidate_count == 2
    assert report.list_candidate_count == 1
    assert report.bold_span_count == 2
    assert report.italic_span_count == 1
    assert report.median_font_size == 10.0
    assert report.largest_font_size == 16.0
    assert report.decision == "promising"


def test_quality_report_does_not_treat_body_digits_as_page_numbers() -> None:
    spans = [
        _span(1, "1950", top=250, bottom=265, font_size=10),
        _span(1, "1950 was part of the sentence.", top=270, bottom=285, font_size=10),
    ]

    report = build_text_layer_quality_report(spans)

    assert report.page_number_span_count == 0
    assert report.body_span_count == 2
    assert report.decision == "scanned_or_unsupported"
    assert report.decision_reasons == ("too_little_text_layer",)


def test_quality_decision_can_classify_dense_but_noisy_text_layer_as_insufficient() -> None:
    spans = [
        _span(page, f"RUNNING HEADER {page % 2}", top=20, bottom=35, font_size=8)
        for page in range(1, 31)
    ]
    spans.extend(
        _span(page, f"{page}", top=750, bottom=765, font_size=8)
        for page in range(1, 31)
    )
    spans.extend(
        _span(page, "Short body text.", top=220, bottom=240, font_size=10)
        for page in range(1, 31)
    )

    report = build_text_layer_quality_report(spans)

    assert report.decision == "insufficient"
    assert "high_page_furniture_ratio" in report.decision_reasons


def test_load_spans_json_coerces_span_fields(tmp_path) -> None:
    path = tmp_path / "spans.json"
    path.write_text(
        json.dumps(
            [
                {
                    "page_number": "2",
                    "text": "EDUCATION",
                    "x0": "42.5",
                    "top": "91",
                    "x1": "300",
                    "bottom": "111",
                    "font_name": "Arial-Bold",
                    "font_size": "14",
                    "is_bold": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    spans = load_spans_json(path)

    assert spans == [
        PdfTextSpan(
            page_number=2,
            text="EDUCATION",
            x0=42.5,
            top=91.0,
            x1=300.0,
            bottom=111.0,
            page_height=None,
            font_name="Arial-Bold",
            font_size=14.0,
            is_bold=True,
            is_italic=False,
        )
    ]


def test_unsupported_quality_report_is_non_throwing_diagnostic() -> None:
    report = unsupported_quality_report("optional_dependency_missing:pdfminer.six")

    assert report.status == "unsupported"
    assert report.decision == "scanned_or_unsupported"
    assert report.warnings == ("optional_dependency_missing:pdfminer.six",)
    assert report.span_count == 0


def test_pdfminer_optional_dependency_missing_is_reported(monkeypatch) -> None:
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("pdfminer"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    try:
        extract_pdf_text_spans_with_pdfminer("unused.pdf")
    except RuntimeError as exc:
        assert str(exc) == "optional_dependency_missing:pdfminer.six"
    else:  # pragma: no cover - defensive clarity
        raise AssertionError("expected missing optional dependency diagnostic")


def test_quality_probe_cli_reports_unsupported_without_raising(monkeypatch, capsys) -> None:
    module_path = Path("tools/pdf_text_layer_quality_probe.py")
    spec = importlib.util.spec_from_file_location("pdf_text_layer_quality_probe", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(
        module,
        "extract_pdf_text_spans_with_pdfminer",
        lambda path: (_ for _ in ()).throw(RuntimeError("optional_dependency_missing:pdfminer.six")),
    )

    assert module.main(["--input-pdf", "unused.pdf"]) == 0
    assert "unsupported" in capsys.readouterr().out


# Spec 067 FR-007 (I-3): running heads on the page-number line.


def _folio_line_span(text: str, *, x0: float, x1: float, top: float = 37.4, bottom: float = 47.9) -> PdfTextSpan:
    return PdfTextSpan(
        page_number=14,
        text=text,
        x0=x0,
        top=top,
        x1=x1,
        bottom=bottom,
        page_height=652,
        font_name="SourceSerif",
        font_size=10.5,
    )


def test_067_fr007_running_head_beside_the_folio_is_furniture() -> None:
    number = _folio_line_span("xi", x0=344, x1=350, top=35.5, bottom=46.0)
    head = _folio_line_span("FOREWORD", x0=266, x1=317)

    assert _detect_running_heads_on_page_number_line([number, head]) == frozenset({head})


def test_067_fr007_lines_that_are_not_running_heads_are_kept() -> None:
    number = _folio_line_span("xi", x0=344, x1=350, top=35.5, bottom=46.0)
    candidates = [
        # ends a sentence
        _folio_line_span("This is the end.", x0=150, x1=300),
        # longer than a running head
        _folio_line_span("one two three four five six seven eight nine", x0=60, x1=300),
        # welded to the number: a reference split off a short line, not a head beside a folio
        _folio_line_span("the Club of Rome", x0=250, x1=343),
        # a full line below the number's line
        _folio_line_span("Preface", x0=60, x1=120, top=60, bottom=70.5),
    ]

    assert _detect_running_heads_on_page_number_line([number, *candidates]) == frozenset()
    # ...and on a page without a page number nothing is furniture by this rule.
    assert _detect_running_heads_on_page_number_line(candidates) == frozenset()


# Spec 067 FR-006 (I-2): a reference set at the document's reference size inside a quotation
# or a box that the book sets entirely in its notes size (Money and Sustainability: 5.76 pt,
# raised 0.375 of its size; Creating Wealth: 10.8 pt, raised 0.40).


def _with_reference_size(chars: list[_FakePdfMinerChar], reference_font_size: float | None) -> str:
    return _line_text_with_char_overrides(
        chars, _inline_superscript_marker_char_ids(chars, reference_font_size=reference_font_size)
    )


def test_067_fr006_reference_in_a_notes_size_inset_is_a_superscript() -> None:
    welded = _pdf_line([("include Mitchell Innes,", 5.76, 100), ("46", 5.76, 102.16), (" Georg Knapp", 5.76, 100)])
    after_a_space = _pdf_line([("until it is evenly mixed.” ", 5.76, 100), ("11", 5.76, 102.16)])

    assert _with_reference_size(welded, 5.8) == "include Mitchell Innes,⁴⁶ Georg Knapp"
    assert _with_reference_size(after_a_space, 5.8) == "until it is evenly mixed.” ¹¹"
    # Without the document's reference size the line's own size decides, as before.
    assert _with_reference_size(welded, None) == "include Mitchell Innes,46 Georg Knapp"


def test_067_fr006_digits_that_are_not_references_stay_numbers() -> None:
    # A contents line: a chapter number at the start, at body size, raised 0.30 of its size
    # (Rethinking Money p. 10) -- neither raised enough nor at the reference size 7.1.
    contents = _pdf_line([("1", 10.97, 103.33), ("  The Failure of Money", 10.97, 100)])
    # Full-size digits on the baseline after a comma or a quote (spec 065 FR-007, 265 cases).
    flat = _pdf_line([("from $1,", 5.76, 100), ("300", 5.76, 100), (" in the ’", 5.76, 100), ("90", 5.76, 100), ("s", 5.76, 100)])
    # Set at the reference size but LOWERED below the line: a subscript, not a reference.
    lowered = _pdf_line([("more CO", 5.76, 100), ("2", 5.76, 98), (" means", 5.76, 100)])

    assert _with_reference_size(contents, 7.1) == "1  The Failure of Money"
    assert _with_reference_size(flat, 5.8) == "from $1,300 in the ’90s"
    assert _with_reference_size(lowered, 5.8) == "more CO2 means"


def test_067_fr006_document_reference_size_is_the_modal_recognised_size() -> None:
    assert _document_reference_font_size([5.76, 5.76, 5.8, 6.5]) == 5.8
    assert _document_reference_font_size([7.1, 7.08, 6.5]) == 7.1
    assert _document_reference_font_size([]) is None


class _FakeTextLine(list):
    def __init__(self, chars: list[_FakePdfMinerChar]) -> None:
        super().__init__(chars)
        self.x0 = min(char.x0 for char in chars)
        self.x1 = max(char.x1 for char in chars)
        self.y0 = min(char.y0 for char in chars)
        self.y1 = max(char.y1 for char in chars)

    def get_text(self) -> str:
        return "".join(char.get_text() for char in self) + "\n"


class _FakeTextBox(list):
    pass


class _FakePage(list):
    height = 800.0


def test_067_fr006_extraction_reads_the_inset_again_with_the_document_reference_size(monkeypatch) -> None:
    import pdfminer.high_level as high_level
    import pdfminer.layout as layout

    body = [
        _FakeTextLine(_pdf_line([("The bank plunged.", 10, 700), ("2", 6.5, 704), (" Then it rose", 10, 700)])),
        _FakeTextLine(_pdf_line([("again in the spring.", 10, 686), ("3", 6.5, 690)])),
        _FakeTextLine(_pdf_line([("as a share of the GDP.", 10, 672), ("9", 10, 676)])),
    ]
    inset = [_FakeTextLine(_pdf_line([("quoted in the box,", 6.5, 640), ("4", 6.5, 642.4), (" said he", 6.5, 640)]))]
    page = _FakePage([_FakeTextBox(body), _FakeTextBox(inset)])
    monkeypatch.setattr(layout, "LTChar", _FakePdfMinerChar)
    monkeypatch.setattr(layout, "LTTextLine", _FakeTextLine)
    monkeypatch.setattr(layout, "LTTextContainer", _FakeTextBox)
    monkeypatch.setattr(high_level, "extract_pages", lambda path: [page])

    texts = [span.text for span in extract_pdf_text_spans_with_pdfminer("unused.pdf")]

    assert texts == [
        "The bank plunged.² Then it rose",
        "again in the spring.³",
        "as a share of the GDP.9",
        "quoted in the box,⁴ said he",
    ]
