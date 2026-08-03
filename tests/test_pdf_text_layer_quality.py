from __future__ import annotations

import json
import importlib.util
from pathlib import Path

from docxaicorrector.pdf_import.text_layer_quality import (
    PdfTextSpan,
    _font_style_flags,
    _inline_superscript_marker_char_ids,
    _line_text_with_char_overrides,
    _normalize_style_runs,
    _pdf_text_span_from_chars,
    _pdfminer_top_origin_bounds,
    _split_trailing_superscript_marker_chars,
    _style_runs_from_line_items,
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


def test_pdfminer_line_keeps_full_size_raised_digit_welded_to_word() -> None:
    # Raised but NOT smaller. Under-attaching costs one visible defect; rewriting a digit
    # that the book set at text size would corrupt text, so this is deliberately skipped.
    chars = _pdf_line([("the GDP.", 10, 100), ("9", 10, 104)])

    assert _extracted_line_text(chars) == "the GDP.9"


def test_pdfminer_line_keeps_number_split_across_a_line_break() -> None:
    # "$16.58" wrapped so that "58" follows the decimal point with no space: welded by
    # shape, but full size and on the baseline.
    chars = _pdf_line([("from $5.49 trillion to $16.", 10, 100), ("58", 10, 100)])

    assert _extracted_line_text(chars) == "from $5.49 trillion to $16.58"


def test_pdfminer_line_keeps_digit_separated_by_a_space() -> None:
    # A raised, undersized digit that does not touch the previous word is an orphan
    # marker, not a reference welded to text; the weld is what this rule keys on.
    chars = _pdf_line([("chapter ", 10, 100), ("2", 6.5, 104), (" opens", 10, 100)])

    assert _extracted_line_text(chars) == "chapter 2 opens"


def test_pdfminer_line_keeps_digit_separated_by_an_inferred_space() -> None:
    # pdfminer reports the space it INFERS between two words as a separate layout item
    # with no font and no geometry. It still separates them, so "paper 28" is not welded.
    chars: list[object] = list(_pdf_line([("paper", 10, 100)]))
    chars.append(_AnnoChar(" "))
    chars.extend(_pdf_line([("28", 6.5, 104)]))
    chars.extend(_pdf_line([(" gathered", 10, 100)]))

    assert _line_text_with_char_overrides(
        chars, _inline_superscript_marker_char_ids(chars)
    ) == "paper 28 gathered"


def test_pdfminer_line_keeps_year_length_digit_run_welded_to_word() -> None:
    # References are numbered one to a few hundred. Four digits is a year or a sum.
    chars = _pdf_line([("year", 10, 100), ("1990", 6.5, 104), (" was", 10, 100)])

    assert _extracted_line_text(chars) == "year1990 was"


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
