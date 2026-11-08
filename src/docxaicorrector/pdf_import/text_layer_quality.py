"""Text-layer PDF source-import quality signals.

This module is deliberately small and dependency-light. It does not replace the
production PDF path; it provides deterministic metrics for PR-PDF0 so we can
measure whether source-side PDF cleanup is likely to beat post-translation
reader-cleanup tuning.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median


_WHITESPACE_PATTERN = re.compile(r"\s+")
_PAGE_NUMBER_PATTERN = re.compile(r"^(?:\d{1,4}|[ivxlcdmIVXLCDM]{1,12})$")
_LIST_MARKER_PATTERN = re.compile(r"^(?:[-*•●]|\d+[.)])\s+")
_FONT_SUBSET_PREFIX_PATTERN = re.compile(r"^[A-Z]{6}\+")
# Style tokens matched ONLY against the trailing style chunk of a font name.
# ``bt`` is intentionally absent from the bold set (``NewsGothicBT`` is a family,
# not a weight); ``it`` is intentionally scoped to the tail so ``Didot`` and other
# family names never register as italic.
_FONT_BOLD_STYLE_TOKENS = ("bold", "black", "semibold", "heavy", "demi", "blk", "bd", "dm")
_FONT_ITALIC_STYLE_TOKENS = ("italic", "oblique", "obl", "it")
_DECISION_THRESHOLDS = {
    "min_visible_text_chars": 1500,
    "min_body_span_count": 20,
    "min_body_text_ratio": 0.70,
    "max_repeated_page_furniture_text_ratio": 0.25,
}

# --- Footnote reference markers set inside a line -------------------------------------
#
# ``_split_trailing_superscript_marker_chars`` below lifts a footnote digit off the END
# of a line so the logical importer can re-bind it as a superscript. That covers only a
# marker that happens to fall on the last position of a line, and only when the marker is
# set at <= 0.62 of the line's text size. Measured over the four corpus books, those two
# conditions leave most references untouched: they sit in the middle of a line, or the
# book sets its references at 0.65-0.80 of the body size. The digit then survives welded
# to the word ("expansion.3 After the summit"), which is what a reader sees as a defect.
#
# This is the same typographic fact, detected the same way, without the position and
# with a size bound that matches what books actually do: a footnote reference is set
# SMALLER than the text it annotates and RAISED above that text's baseline. Both signals
# are required. The measured per-book distribution of (size ratio, raised) over every
# digit run welded to a word is strictly two-clustered:
#
#     book                  raised & smaller        flat (baseline-aligned)
#     creating_wealth       152 @ 0.75              44 @ 0.75, 106 @ 1.00
#     lietaer               214 @ 0.65              187 @ 1.00
#     mazzucato             354 @ 0.60, 27 @ 0.80   266 @ 1.00
#     money_sustainability  234 @ 0.40, 13 @ 0.53   424 @ 1.00
#
# The "flat" column is what makes the conjunction safe: it is where "CO2", "H2O", "$16.58"
# split across a line, "0.005" and "$2.5" land. A subscript is smaller but LOWERED; an
# ordinary number is baseline-aligned and full size. Neither can satisfy both tests.
# ``_SUPERSCRIPT_MARKER_MAX_SIZE_RATIO`` sits in the empty band between the two clusters
# (the largest observed reference is 0.80, the smallest observed ordinary digit 1.00).
#
# A digit that is raised but NOT smaller than its own line was left alone from 2026-08-03
# (commit 6cb7a6e), on the premise of "a book that sets references at full size". Spec 067
# I-2 measured that premise on the corpus and found no such book: all 54 raised digits at
# the size of their line (Creating Wealth 9, Money and Sustainability 45) sit in quotations
# and boxes the book sets ENTIRELY in its notes size -- 10.8 pt in Creating Wealth, 5.76 pt
# in Money and Sustainability, the modal size of the references already recognised there
# (157 of 157, 270 of 270) -- and every one is a reference with a note behind it (a source
# title ending in a year -> note 5, a name and its comma -> note 46). So "smaller than its
# line" has one alternative: set at the document's own reference size (`_document_reference_font_size`,
# within ``_REFERENCE_FONT_SIZE_TOLERANCE_PT``), still raised. A raised digit at the size of
# the body, where the book's references are smaller, stays a number, as do the 265 full-size
# digits on the baseline after a comma or a quote (spec 065 FR-007) and Rethinking Money's
# contents numbers (raised 0.30 of their size, at body size).
_SUPERSCRIPT_MARKER_MAX_SIZE_RATIO = 0.85
# Spec 067 FR-006: how close a run must be to the document's reference size (the modal size
# of the references recognised in it, `_document_reference_font_size`) to count as set in it.
_REFERENCE_FONT_SIZE_TOLERANCE_PT = 0.3
_SUPERSCRIPT_MARKER_MIN_BASELINE_RISE_RATIO = 0.35
_SUPERSCRIPT_MARKER_MAX_DIGITS = 3
_SUPERSCRIPT_DIGIT_TABLE = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
# What a reference may be welded to: the end of a word, or the punctuation that follows the
# word it annotates -- a sentence end, a clause comma, a closing bracket or a closing quote,
# typographic (” ’) or straight. Same set as ``_can_end_with_superscript_marker`` uses for
# the end-of-line case.
#
# Spec 065 FR-007: until 2026-11-08 the set had no comma and no right single quote (which is
# also the typographic apostrophe). A reference set after either -- "lending,³⁰ as",
# "reject.’¹⁰", "‘marginal revolution’⁴ –" -- reached the model as plain digits welded to the
# word, outside the marker count, although the book had set it smaller and raised like any
# other reference. Measured on the four corpus PDFs, every digit run of at most three digits
# welded to a comma or a ’ that passes the size-and-rise pair sits in its own book's
# reference cluster (size ratio, rise): The Value of Everything 67 at (0.60, 0.44) -- 42
# after a comma, 25 after ’ --, Rethinking Money 14 at (0.65, 0.44), Creating Wealth 5 at
# (0.75, 0.40), Money and Sustainability 14 at (0.40, 0.48); all 100 were read and all are
# references. The same two anchors precede 263 + 2 digit runs set at full size on the
# baseline ("1,300", "2,000", "’90s"), and the size-and-rise pair leaves every one a number.
_SUPERSCRIPT_MARKER_ANCHOR_CLOSERS = ".!?:;,)]}»”’\"'"


@dataclass(frozen=True)
class PdfTextSpan:
    page_number: int
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    page_height: float | None = None
    font_name: str = ""
    font_size: float | None = None
    is_bold: bool = False
    is_italic: bool = False
    # Character-level emphasis runs whose concatenation equals ``_normalize_text(text)``.
    # Each run is ``(text, is_bold, is_italic)``. Empty when the span was rebuilt from a
    # mapping (JSON) that carries no per-character font information.
    runs: tuple[tuple[str, bool, bool], ...] = ()


@dataclass(frozen=True)
class TextLayerQualityReport:
    status: str
    page_count: int
    span_count: int
    visible_text_chars: int
    body_text_chars: int
    repeated_page_furniture_text_chars: int
    page_number_text_chars: int
    body_text_ratio: float
    repeated_page_furniture_text_ratio: float
    body_span_count: int
    repeated_page_furniture_span_count: int
    page_number_span_count: int
    heading_candidate_count: int
    list_candidate_count: int
    bold_span_count: int
    italic_span_count: int
    median_font_size: float | None
    largest_font_size: float | None
    decision: str
    decision_reasons: tuple[str, ...]
    thresholds_used: Mapping[str, float | int]
    text_layer_interpretation: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_text_layer_quality_report(spans: Sequence[PdfTextSpan]) -> TextLayerQualityReport:
    normalized_spans = tuple(span for span in spans if _normalize_text(span.text))
    page_count = len({span.page_number for span in normalized_spans})
    repeated_furniture_keys = _detect_repeated_page_furniture_keys(normalized_spans)
    running_heads = _detect_running_heads_on_page_number_line(normalized_spans)
    font_sizes = [
        span.font_size
        for span in normalized_spans
        if isinstance(span.font_size, (int, float))
        and span.font_size > 0
        and _span_furniture_key(span) not in repeated_furniture_keys
        and span not in running_heads
        and not _looks_like_page_number(span)
    ]
    median_font_size = float(median(font_sizes)) if font_sizes else None
    largest_font_size = float(max(font_sizes)) if font_sizes else None

    repeated_page_furniture_span_count = 0
    repeated_page_furniture_text_chars = 0
    page_number_span_count = 0
    page_number_text_chars = 0
    heading_candidate_count = 0
    list_candidate_count = 0
    bold_span_count = 0
    italic_span_count = 0
    body_span_count = 0
    body_text_chars = 0
    visible_text_chars = 0

    for span in normalized_spans:
        normalized_text = _normalize_text(span.text)
        text_chars = _text_char_count(normalized_text)
        visible_text_chars += text_chars
        is_page_furniture = (
            _span_furniture_key(span) in repeated_furniture_keys or span in running_heads
        )
        is_page_number = _looks_like_page_number(span)
        if is_page_furniture:
            repeated_page_furniture_span_count += 1
            repeated_page_furniture_text_chars += text_chars
        if is_page_number:
            page_number_span_count += 1
            page_number_text_chars += text_chars
        if span.is_bold:
            bold_span_count += 1
        if span.is_italic:
            italic_span_count += 1
        if _looks_like_heading_candidate(span, median_font_size=median_font_size):
            heading_candidate_count += 1
        if _LIST_MARKER_PATTERN.match(normalized_text):
            list_candidate_count += 1
        if not is_page_furniture and not is_page_number:
            body_span_count += 1
            body_text_chars += text_chars

    decision, decision_reasons = _decide_text_layer_quality(
        status="ok",
        visible_text_chars=visible_text_chars,
        body_span_count=body_span_count,
        body_text_ratio=_safe_ratio(body_text_chars, visible_text_chars),
        repeated_page_furniture_text_ratio=_safe_ratio(
            repeated_page_furniture_text_chars,
            visible_text_chars,
        ),
        heading_candidate_count=heading_candidate_count,
        list_candidate_count=list_candidate_count,
        bold_span_count=bold_span_count,
        italic_span_count=italic_span_count,
        median_font_size=median_font_size,
        largest_font_size=largest_font_size,
    )
    return TextLayerQualityReport(
        status="ok",
        page_count=page_count,
        span_count=len(normalized_spans),
        visible_text_chars=visible_text_chars,
        body_text_chars=body_text_chars,
        repeated_page_furniture_text_chars=repeated_page_furniture_text_chars,
        page_number_text_chars=page_number_text_chars,
        body_text_ratio=_safe_ratio(body_text_chars, visible_text_chars),
        repeated_page_furniture_text_ratio=_safe_ratio(
            repeated_page_furniture_text_chars,
            visible_text_chars,
        ),
        body_span_count=body_span_count,
        repeated_page_furniture_span_count=repeated_page_furniture_span_count,
        page_number_span_count=page_number_span_count,
        heading_candidate_count=heading_candidate_count,
        list_candidate_count=list_candidate_count,
        bold_span_count=bold_span_count,
        italic_span_count=italic_span_count,
        median_font_size=median_font_size,
        largest_font_size=largest_font_size,
        decision=decision,
        decision_reasons=decision_reasons,
        thresholds_used=_DECISION_THRESHOLDS,
        text_layer_interpretation=_interpret_decision(decision),
    )


def unsupported_quality_report(reason: str) -> TextLayerQualityReport:
    return TextLayerQualityReport(
        status="unsupported",
        page_count=0,
        span_count=0,
        visible_text_chars=0,
        body_text_chars=0,
        repeated_page_furniture_text_chars=0,
        page_number_text_chars=0,
        body_text_ratio=0.0,
        repeated_page_furniture_text_ratio=0.0,
        body_span_count=0,
        repeated_page_furniture_span_count=0,
        page_number_span_count=0,
        heading_candidate_count=0,
        list_candidate_count=0,
        bold_span_count=0,
        italic_span_count=0,
        median_font_size=None,
        largest_font_size=None,
        decision="scanned_or_unsupported",
        decision_reasons=("unsupported_status",),
        thresholds_used=_DECISION_THRESHOLDS,
        text_layer_interpretation=_interpret_decision("scanned_or_unsupported"),
        warnings=(reason,),
    )


def load_spans_json(path: str | Path) -> list[PdfTextSpan]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("pdf_text_spans_json_must_be_list")
    return [_span_from_mapping(item) for item in payload if isinstance(item, Mapping)]


def write_quality_report(path: str | Path, report: TextLayerQualityReport) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def extract_pdf_text_spans_with_pdfminer(pdf_path: str | Path) -> list[PdfTextSpan]:
    """Extract line-level spans through optional pdfminer.six.

    The import stays local so production installs without pdfminer keep working.
    PR-PDF0 callers should catch RuntimeError and record unsupported status.
    """
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTAnno, LTChar, LTTextContainer, LTTextLine
    except ImportError as exc:  # pragma: no cover - depends on optional env
        raise RuntimeError("optional_dependency_missing:pdfminer.six") from exc

    # One list of spans per text line, so a line can be rebuilt after the whole document is
    # read (spec 067 FR-006, below).
    line_spans: list[list[PdfTextSpan]] = []
    reference_font_sizes: list[float] = []
    lines_to_reread: list[tuple[int, object, list[object], int, float | None]] = []
    for page_index, page_layout in enumerate(extract_pages(str(pdf_path)), start=1):
        page_height = _coerce_optional_float(getattr(page_layout, "height", None))
        for element in page_layout:
            if not isinstance(element, LTTextContainer):
                continue
            for line in element:
                if not isinstance(line, LTTextLine):
                    continue
                text = line.get_text().strip()
                if not text:
                    continue
                # Footnote references set inside the line are rendered as Unicode
                # superscript digits in place. The span keeps its geometry and its
                # character count, so every boundary decision downstream (soft-wrap
                # continuation, paragraph indent boundary, body merge) sees exactly the
                # line it saw before: a raw digit and a superscript digit are both
                # non-terminal, non-alphabetic characters.
                #
                # Read over the whole line rather than over ``chars``: pdfminer reports
                # the spaces it infers between words as separate layout items with no
                # font, and a rule that saw only the real characters would read the
                # space-separated "paper 28" as welded.
                items: list[object] = list(line)
                raised_runs = _raised_digit_runs(items)
                inline_marker_overrides = _reference_digit_overrides(
                    items, raised_runs, reference_font_size=None
                )
                reference_font_sizes.extend(
                    marker_font_size
                    for _, marker_font_size, line_text_font_size in raised_runs
                    if _run_is_smaller_than_its_line(marker_font_size, line_text_font_size)
                )
                if any(
                    not _run_is_smaller_than_its_line(marker_font_size, line_text_font_size)
                    for _, marker_font_size, line_text_font_size in raised_runs
                ):
                    lines_to_reread.append(
                        (len(line_spans), line, items, page_index, page_height)
                    )
                line_spans.append(
                    _spans_from_pdfminer_line(
                        line,
                        items,
                        inline_marker_overrides,
                        page_index=page_index,
                        page_height=page_height,
                        char_type=LTChar,
                    )
                )
    # Spec 067 FR-006: a reference set at the size this document sets its references in is a
    # reference even where its own line is set in that size too (a quotation or a box in the
    # notes size). The size is known only once every line has been read; the few lines that
    # carry a raised digit at their own size are read again with it.
    reference_font_size = _document_reference_font_size(reference_font_sizes)
    if reference_font_size is not None:
        for slot, line_box, items, page_index, page_height in lines_to_reread:
            overrides = _inline_superscript_marker_char_ids(
                items, reference_font_size=reference_font_size
            )
            line_spans[slot] = _spans_from_pdfminer_line(
                line_box,
                items,
                overrides,
                page_index=page_index,
                page_height=page_height,
                char_type=LTChar,
            )
    return [span for spans_of_line in line_spans for span in spans_of_line]


def _spans_from_pdfminer_line(
    line_box: object,
    items: Sequence[object],
    inline_marker_overrides: Mapping[int, str],
    *,
    page_index: int,
    page_height: float | None,
    char_type: type,
) -> list[PdfTextSpan]:
    """The span (or, with a trailing reference split off, the spans) of one pdfminer text
    line: ``line_box`` gives the line's box, ``items`` its full item sequence."""
    chars = [item for item in items if isinstance(item, char_type)]
    font_names = [str(getattr(char, "fontname", "") or "") for char in chars]
    font_sizes = [float(getattr(char, "size", 0.0) or 0.0) for char in chars]
    font_name = _most_common(font_names)
    font_size = median(font_sizes) if font_sizes else None
    is_bold, is_italic = _font_style_flags(font_name)
    top, bottom = _pdfminer_top_origin_bounds(
        y0=float(getattr(line_box, "y0")),
        y1=float(getattr(line_box, "y1")),
        page_height=page_height,
    )
    trailing_superscript_split = _trailing_marker_split_left_to_importer(
        chars, inline_marker_overrides
    )
    if trailing_superscript_split is None:
        return [
            PdfTextSpan(
                page_number=page_index,
                text=_line_text_with_char_overrides(items, inline_marker_overrides),
                x0=float(getattr(line_box, "x0")),
                top=top,
                x1=float(getattr(line_box, "x1")),
                bottom=bottom,
                page_height=page_height,
                font_name=font_name,
                font_size=float(font_size) if font_size else None,
                is_bold=is_bold,
                is_italic=is_italic,
                runs=_style_runs_from_line_items(
                    items, char_text_overrides=inline_marker_overrides
                ),
            )
        ]
    # Only the leading segment is rewritten. The trailing marker keeps its raw digits so the
    # logical importer still recognises it as a standalone ``\d{1,3}`` marker span and
    # re-binds it through the existing path.
    spans: list[PdfTextSpan] = []
    for segment_index, segment_chars in enumerate(trailing_superscript_split):
        span = _pdf_text_span_from_chars(
            segment_chars,
            page_number=page_index,
            page_height=page_height,
            char_text_overrides=inline_marker_overrides if segment_index == 0 else None,
        )
        if span is not None:
            spans.append(span)
    return spans


_ASCII_DIGITS = frozenset("0123456789")


def _char_display_text(char: object) -> str:
    return str(getattr(char, "get_text", lambda: "")() or "")


def _char_font_size(char: object) -> float:
    return float(getattr(char, "size", 0.0) or 0.0)


def _char_baseline(char: object) -> float:
    return float(getattr(char, "y0", 0.0) or 0.0)


def _inline_superscript_marker_char_ids(
    chars: Sequence[object], *, reference_font_size: float | None = None
) -> dict[int, str]:
    """Map ``id(char) -> superscript glyph`` for the footnote references in one line.

    ``chars`` must be the line's FULL item sequence, including the whitespace items the
    extractor infers between words — the weld test below reads them.

    A digit run qualifies when all four hold, and they are all properties of how the
    book SET the digit — no vocabulary, no document-specific string, no counting:

    * it is welded to the end of a word or of a sentence: the character immediately
      before it, with no space between, is a letter or a closing mark (``.``, ``”``,
      ``)``…); OR (spec 063 FR-007) it stands apart — after a space or at the start of
      the line — and is raised ALONE: neither of its non-space neighbours is itself
      small and raised, which keeps an exponent group such as ``(n - 1)`` a formula;
    * it is at most three digits long — references are numbered, page-scale quantities
      and years are not;
    * it is set SMALLER than the text on its line;
    * it is RAISED above that text's baseline.

    The last two are the discriminating pair. An ordinary number welded to a word by a
    line break ("$16.58", "0.005") is full size and baseline-aligned; a chemical
    subscript ("CO2", "H2O") is smaller but LOWERED. Neither passes both — and neither
    does a full-size number after a space ("nearly 39 million"), which is why dropping
    the weld requirement for a stand-alone run is safe. Measured 2026-11-07 on the four
    corpus PDFs: the stand-alone form takes Rethinking Money's 15 references set after a
    closing quote and a space ("works.” 9") and Money and Sustainability's "paper 28";
    the raised-alone test rejects the one exponent the size-and-raise pair alone would
    take (Rethinking Money p. 244).

    A stand-alone run keeps the space before it: only the digits are rewritten, so the
    span's character count stays what it was, like for every other reference.

    Spec 067 FR-006: "smaller than the text on its line" has one alternative --
    set at ``reference_font_size``, the size this document sets its recognised
    references in (`_document_reference_font_size`), within
    ``_REFERENCE_FONT_SIZE_TOLERANCE_PT``. A quotation or a box that the book sets in
    its notes size carries its references at the size of its own line; they are still
    raised, and still at the size of every other reference in the book. Everything else
    is required as before. A raised digit at the size of the BODY (a full stop and a
    body-size digit, where the references are smaller) stays a number, and so does a raised
    digit in a document that has no recognised references at all.
    """
    return _reference_digit_overrides(
        chars, _raised_digit_runs(chars), reference_font_size=reference_font_size
    )


def _reference_digit_overrides(
    chars: Sequence[object],
    raised_runs: Sequence[tuple[list[int], float, float]],
    *,
    reference_font_size: float | None,
) -> dict[int, str]:
    overrides: dict[int, str] = {}
    for run_indexes, marker_font_size, line_text_font_size in raised_runs:
        if not (
            _run_is_smaller_than_its_line(marker_font_size, line_text_font_size)
            or _is_set_at_reference_size(marker_font_size, reference_font_size)
        ):
            continue
        for index in run_indexes:
            overrides[id(chars[index])] = (
                _char_display_text(chars[index]).strip().translate(_SUPERSCRIPT_DIGIT_TABLE)
            )
    return overrides


def _run_is_smaller_than_its_line(marker_font_size: float, line_text_font_size: float) -> bool:
    return marker_font_size <= line_text_font_size * _SUPERSCRIPT_MARKER_MAX_SIZE_RATIO


def _is_set_at_reference_size(marker_font_size: float, reference_font_size: float | None) -> bool:
    return (
        reference_font_size is not None
        and abs(marker_font_size - reference_font_size) <= _REFERENCE_FONT_SIZE_TOLERANCE_PT
    )


def _document_reference_font_size(reference_font_sizes: Sequence[float]) -> float | None:
    """Spec 067 FR-006: the size a document sets its footnote references in -- the most
    common size, to 0.1 pt, of the references the in-line rule recognised in it by size
    and rise. None when it recognised none."""
    rounded = Counter(round(size, 1) for size in reference_font_sizes if size > 0)
    if not rounded:
        return None
    return rounded.most_common(1)[0][0]


def _raised_digit_runs(chars: Sequence[object]) -> list[tuple[list[int], float, float]]:
    """Every digit run of the line that satisfies the reference form except the size test:
    welded or standing raised alone, at most three digits, raised above the text's baseline.
    Each as ``(run item indexes, run size, line text size)``; the size is decided by the
    caller (`_inline_superscript_marker_char_ids`)."""
    non_space_indexes = [
        index for index, char in enumerate(chars) if _char_display_text(char).strip()
    ]
    if len(non_space_indexes) < 2:
        return []
    line_font_sizes = [
        size
        for size in (_char_font_size(chars[index]) for index in non_space_indexes)
        if size > 0
    ]
    if not line_font_sizes:
        return []
    line_text_font_size = float(median(line_font_sizes))
    if line_text_font_size <= 0:
        return []

    runs: list[tuple[list[int], float, float]] = []
    position = 0
    while position < len(non_space_indexes):
        if _char_display_text(chars[non_space_indexes[position]]).strip() not in _ASCII_DIGITS:
            position += 1
            continue
        run_start = position
        position += 1
        # A run is digits with nothing between them: a space ends it, so "$1,300 36" is
        # "300" and "36", not one five-digit "30036" (spec 063 FR-007 reads the second).
        while (
            position < len(non_space_indexes)
            and _char_display_text(chars[non_space_indexes[position]]).strip() in _ASCII_DIGITS
            and not _whitespace_between(
                chars,
                anchor_index=non_space_indexes[position - 1],
                run_start_index=non_space_indexes[position],
            )
        ):
            position += 1
        run_indexes = non_space_indexes[run_start:position]
        if len(run_indexes) > _SUPERSCRIPT_MARKER_MAX_DIGITS:
            continue
        welded = run_start > 0 and _digit_run_is_welded_to_preceding_text(
            chars,
            anchor_index=non_space_indexes[run_start - 1],
            run_start_index=run_indexes[0],
        )
        # Spec 063 FR-007: a reference that does NOT touch the previous word — a space
        # between them, or the start of the line — is read by the same two typographic
        # signals. Nothing else about it is required: what precedes it may be a digit
        # ("$1,300 36 billion"), a closing quote or nothing at all.
        if not welded and not (
            run_start == 0
            or _whitespace_between(
                chars,
                anchor_index=non_space_indexes[run_start - 1],
                run_start_index=run_indexes[0],
            )
        ):
            continue
        run_font_sizes = [
            size for size in (_char_font_size(chars[index]) for index in run_indexes) if size > 0
        ]
        marker_font_size = (
            float(median(run_font_sizes)) if run_font_sizes else line_text_font_size
        )
        # The baseline the digits must rise above: the text before them, or — for a run
        # that opens the line — the text after them. For a welded run the first list is
        # never empty, so the welded rule reads exactly what it read before FR-007.
        text_baselines = [
            _char_baseline(chars[index])
            for index in non_space_indexes
            if index < run_indexes[0]
        ] or [
            _char_baseline(chars[index])
            for index in non_space_indexes
            if index > run_indexes[-1]
        ]
        marker_baselines = [_char_baseline(chars[index]) for index in run_indexes]
        if not text_baselines or not marker_baselines:
            continue
        text_baseline = float(median(text_baselines))
        required_baseline = (
            text_baseline + marker_font_size * _SUPERSCRIPT_MARKER_MIN_BASELINE_RISE_RATIO
        )
        if float(median(marker_baselines)) < required_baseline:
            continue
        # An unattached run must be raised ALONE. In "(1 + i)^(n - 1)" the exponent's "1"
        # is small, raised and follows a space — but so do the "(", "n" and "-" around it:
        # it is one character of a raised group, not a reference. A footnote reference is
        # digits and nothing else; its neighbours are set as text.
        if not welded and any(
            _char_is_raised_and_smaller(
                chars[neighbour],
                line_text_font_size=line_text_font_size,
                text_baseline=text_baseline,
            )
            for neighbour in (
                non_space_indexes[run_start - 1] if run_start > 0 else None,
                non_space_indexes[position] if position < len(non_space_indexes) else None,
            )
            if neighbour is not None
        ):
            continue
        runs.append((run_indexes, marker_font_size, line_text_font_size))
    return runs


def _digit_run_is_welded_to_preceding_text(
    chars: Sequence[object], *, anchor_index: int, run_start_index: int
) -> bool:
    """True when the digit run touches the previous word with nothing in between."""
    anchor_text = _char_display_text(chars[anchor_index]).strip()
    if not anchor_text:
        return False
    last_char = anchor_text[-1]
    if not (last_char.isalpha() or last_char in _SUPERSCRIPT_MARKER_ANCHOR_CLOSERS):
        return False
    return not _whitespace_between(
        chars, anchor_index=anchor_index, run_start_index=run_start_index
    )


def _whitespace_between(
    chars: Sequence[object], *, anchor_index: int, run_start_index: int
) -> bool:
    """True when a space item — real or inferred by the extractor — separates the two."""
    return any(
        _char_display_text(chars[index]) and not _char_display_text(chars[index]).strip()
        for index in range(anchor_index + 1, run_start_index)
    )


def _char_is_raised_and_smaller(
    char: object, *, line_text_font_size: float, text_baseline: float
) -> bool:
    """The reference conjunction, asked of ONE character: smaller than its line AND raised."""
    size = _char_font_size(char)
    if size <= 0 or size > line_text_font_size * _SUPERSCRIPT_MARKER_MAX_SIZE_RATIO:
        return False
    return _char_baseline(char) >= text_baseline + size * _SUPERSCRIPT_MARKER_MIN_BASELINE_RISE_RATIO


def _trailing_marker_split_left_to_importer(
    chars: Sequence[object], inline_marker_overrides: Mapping[int, str]
) -> tuple[Sequence[object], Sequence[object]] | None:
    """The end-of-line split, except for a reference the importer would read out of place.

    Spec 063 FR-007, measured 2026-11-07 on the corpus PDFs. The split hands the importer
    the reference as its own span, and the importer orders spans by ``(page, top, x0)``.
    A reference is raised; when it is raised far enough that its box clears the top of
    its own line, it has the smaller ``top`` and is read BEFORE that line — after the
    previous one — and re-bound there. On The Value of Everything, which sets references
    at 0.60 of the body and raises them by 0.43 of it, every one of the 130 end-of-line
    references took this path: a reference after a sentence-end full stop arrived inside a
    sum on a neighbouring line ("($1,300 36 billion)"), and another stood as a line of its
    own between two lines of a sum, which the pipeline later re-joined into "nearly 39
    £30,000" — the corpus's only blocker, where the model read the two as one sum. The
    stray span also cut 11 paragraphs in two and, by ending the line before it with a full
    stop, let the importer's boundary rule break 12 more in the middle (the next line was
    not indented; that book indents every paragraph start).

    Such a reference, when the in-line rule claims it (welded, at most three digits,
    smaller, raised), is rendered where it is set — "word.³⁹" — on its own line, and
    needs no re-binding. Every other split is left exactly as it was: Money and
    Sustainability sets its references at 0.40, their box mostly stays under the line's
    top, and the re-binding path has worked there since it was written. Keeping the split
    there also keeps the span population the importer's heading clustering is computed
    over — measured: dropping the split for every claimed reference moved Money's heading
    threshold and promoted five note lines to headings.
    """
    split = _split_trailing_superscript_marker_chars(chars)
    if split is None:
        return None
    body_chars, marker_chars = split
    claimed = [char for char in marker_chars if _char_display_text(char).strip()]
    if not claimed or not all(id(char) in inline_marker_overrides for char in claimed):
        return split
    if _char_top_edge(marker_chars) > _char_top_edge(body_chars):
        return None
    return split


def _char_top_edge(chars: Sequence[object]) -> float:
    """The highest point of the characters, in the extractor's bottom-origin coordinates."""
    return max((float(getattr(char, "y1", 0.0) or 0.0) for char in chars), default=0.0)


def _line_text_with_char_overrides(
    items: Iterable[object], char_text_overrides: Mapping[int, str] | None
) -> str:
    """The line's raw text, with the claimed digits replaced by superscript glyphs."""
    pieces: list[str] = []
    for item in items:
        piece = _char_display_text(item)
        if char_text_overrides and id(item) in char_text_overrides:
            piece = char_text_overrides[id(item)]
        pieces.append(piece)
    return "".join(pieces).strip()


def _split_trailing_superscript_marker_chars(chars: Sequence[object]) -> tuple[Sequence[object], Sequence[object]] | None:
    if len(chars) < 2:
        return None
    non_space_indexes = [
        index
        for index, char in enumerate(chars)
        if str(getattr(char, "get_text", lambda: "")() or "").strip()
    ]
    if len(non_space_indexes) < 2:
        return None
    font_sizes = [
        float(getattr(chars[index], "size", 0.0) or 0.0)
        for index in non_space_indexes
        if float(getattr(chars[index], "size", 0.0) or 0.0) > 0
    ]
    if not font_sizes:
        return None
    body_font_size = float(median(font_sizes))
    tail_indexes: list[int] = []
    for index in reversed(non_space_indexes):
        char = chars[index]
        text = str(getattr(char, "get_text", lambda: "")() or "")
        char_size = float(getattr(char, "size", 0.0) or 0.0)
        if text.isdigit() and char_size <= body_font_size * 0.62:
            tail_indexes.append(index)
            continue
        break
    if not tail_indexes:
        return None
    tail_indexes.reverse()
    if len(tail_indexes) > 3:
        return None
    marker_start = tail_indexes[0]
    before_chars = chars[:marker_start]
    marker_chars = chars[marker_start:]
    before_text = "".join(str(getattr(char, "get_text", lambda: "")() or "") for char in before_chars).rstrip()
    marker_text = "".join(str(getattr(char, "get_text", lambda: "")() or "") for char in marker_chars).strip()
    if not before_text or not marker_text.isdigit():
        return None
    if not _can_end_with_superscript_marker(before_text):
        return None
    body_baselines = [
        float(getattr(char, "y0", 0.0) or 0.0)
        for char in before_chars
        if str(getattr(char, "get_text", lambda: "")() or "").strip()
    ]
    marker_baselines = [
        float(getattr(char, "y0", 0.0) or 0.0)
        for char in marker_chars
        if str(getattr(char, "get_text", lambda: "")() or "").strip()
    ]
    if not body_baselines or not marker_baselines:
        return None
    marker_font_sizes = [
        float(getattr(char, "size", 0.0) or 0.0)
        for char in marker_chars
        if float(getattr(char, "size", 0.0) or 0.0) > 0
    ]
    marker_font_size = float(median(marker_font_sizes)) if marker_font_sizes else body_font_size
    if float(median(marker_baselines)) < float(median(body_baselines)) + marker_font_size * 0.35:
        return None
    return before_chars, marker_chars


def _can_end_with_superscript_marker(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    last_char = stripped[-1]
    return last_char.isalpha() or last_char in _SUPERSCRIPT_MARKER_ANCHOR_CLOSERS


def _pdf_text_span_from_chars(
    chars: Sequence[object],
    *,
    page_number: int,
    page_height: float | None,
    char_text_overrides: Mapping[int, str] | None = None,
) -> PdfTextSpan | None:
    text = _line_text_with_char_overrides(chars, char_text_overrides)
    if not text:
        return None
    font_names = [str(getattr(char, "fontname", "") or "") for char in chars]
    font_sizes = [
        float(getattr(char, "size", 0.0) or 0.0)
        for char in chars
        if float(getattr(char, "size", 0.0) or 0.0) > 0
    ]
    font_name = _most_common(font_names)
    is_bold, is_italic = _font_style_flags(font_name)
    x0 = min(float(getattr(char, "x0", 0.0) or 0.0) for char in chars)
    x1 = max(float(getattr(char, "x1", 0.0) or 0.0) for char in chars)
    y0 = min(float(getattr(char, "y0", 0.0) or 0.0) for char in chars)
    y1 = max(float(getattr(char, "y1", 0.0) or 0.0) for char in chars)
    top, bottom = _pdfminer_top_origin_bounds(y0=y0, y1=y1, page_height=page_height)
    font_size = float(median(font_sizes)) if font_sizes else None
    return PdfTextSpan(
        page_number=page_number,
        text=text,
        x0=x0,
        top=top,
        x1=x1,
        bottom=bottom,
        page_height=page_height,
        font_name=font_name,
        font_size=font_size,
        is_bold=is_bold,
        is_italic=is_italic,
        runs=_style_runs_from_line_items(chars, char_text_overrides=char_text_overrides),
    )


def _span_from_mapping(item: Mapping[str, object]) -> PdfTextSpan:
    return PdfTextSpan(
        page_number=_coerce_int(item.get("page_number"), default=1),
        text=str(item.get("text") or ""),
        x0=_coerce_float(item.get("x0")),
        top=_coerce_float(item.get("top")),
        x1=_coerce_float(item.get("x1")),
        bottom=_coerce_float(item.get("bottom")),
        page_height=_coerce_optional_float(item.get("page_height")),
        font_name=str(item.get("font_name") or ""),
        font_size=_coerce_optional_float(item.get("font_size")),
        is_bold=bool(item.get("is_bold", False)),
        is_italic=bool(item.get("is_italic", False)),
    )


def _detect_repeated_page_furniture_keys(spans: Sequence[PdfTextSpan]) -> set[tuple[str, str]]:
    pages = {span.page_number for span in spans}
    if len(pages) < 2:
        return set()
    counts: Counter[tuple[str, str]] = Counter()
    pages_by_key: dict[tuple[str, str], set[int]] = {}
    for span in spans:
        key = _span_furniture_key(span)
        if key[0] == "body":
            continue
        counts[key] += 1
        pages_by_key.setdefault(key, set()).add(span.page_number)
    return {
        key
        for key, page_numbers in pages_by_key.items()
        if len(page_numbers) >= min(3, len(pages)) and counts[key] >= len(page_numbers)
    }


_RUNNING_HEAD_MAX_WORDS = 8
_RUNNING_HEAD_SENTENCE_END_CHARS = ".!?;:"
_RUNNING_HEAD_MIN_VERTICAL_OVERLAP_RATIO = 0.5


def _detect_running_heads_on_page_number_line(
    spans: Sequence[PdfTextSpan],
) -> frozenset[PdfTextSpan]:
    """Spec 067 FR-007 (I-3): a running head set on the page-number line is page furniture,
    however few pages repeat it.

    `_detect_repeated_page_furniture_keys` needs a (zone, text) key on at least three pages.
    A running head that changes with the section is on fewer: Rethinking Money's foreword head
    is on two pages (13 and 14) and its contents head on one (11), and all three reached the body --
    two glued to the start of a paragraph, one as an extra heading. What marks them is not
    repetition but the line they stand on: the folio's.

    The form, all of it required:
      * the span is in the top or bottom band of its page (`_page_zone`);
      * on the same page a page number (`_looks_like_page_number`) stands on the same line:
        the two boxes overlap vertically by at least half of the shorter one;
      * it stands apart from that number -- a gap of at least its own font size between
        them -- so a footnote reference split off the end of a short line is not a folio;
      * it is short and does not end a sentence: at most eight words, last character none
        of . ! ? ; :
    The number itself is dropped by `_looks_like_page_number` as before. A book without
    page numbers in its text layer gets nothing from this rule. Measured on the four corpus
    PDFs (2026-11-08): the three Rethinking Money spans above, nothing else."""
    numbers_by_page: dict[int, list[PdfTextSpan]] = {}
    for span in spans:
        if _looks_like_page_number(span):
            numbers_by_page.setdefault(span.page_number, []).append(span)
    if not numbers_by_page:
        return frozenset()
    running_heads: set[PdfTextSpan] = set()
    for span in spans:
        numbers = numbers_by_page.get(span.page_number)
        if not numbers or _looks_like_page_number(span) or _page_zone(span) == "body":
            continue
        text = _normalize_text(span.text)
        if (
            not text
            or len(text.split()) > _RUNNING_HEAD_MAX_WORDS
            or text[-1] in _RUNNING_HEAD_SENTENCE_END_CHARS
        ):
            continue
        if any(_span_stands_on_folio_line(span, number) for number in numbers):
            running_heads.add(span)
    return frozenset(running_heads)


def _span_stands_on_folio_line(span: PdfTextSpan, number: PdfTextSpan) -> bool:
    overlap = min(float(span.bottom), float(number.bottom)) - max(float(span.top), float(number.top))
    shorter = min(float(span.bottom) - float(span.top), float(number.bottom) - float(number.top))
    if shorter <= 0 or overlap < shorter * _RUNNING_HEAD_MIN_VERTICAL_OVERLAP_RATIO:
        return False
    font_size = (
        float(span.font_size)
        if isinstance(span.font_size, (int, float)) and span.font_size > 0
        else shorter
    )
    gap = max(float(number.x0) - float(span.x1), float(span.x0) - float(number.x1))
    return gap >= font_size


def _span_furniture_key(span: PdfTextSpan) -> tuple[str, str]:
    zone = _page_zone(span)
    if zone == "body":
        return ("body", "")
    return (zone, _normalize_text(span.text))


def _page_zone(span: PdfTextSpan) -> str:
    # Internal coordinates are top-origin. Extractors with bottom-origin
    # coordinates, such as pdfminer, must be normalized before creating spans.
    page_height = span.page_height if isinstance(span.page_height, (int, float)) else None
    top_zone_end = max(80.0, page_height * 0.1) if page_height and page_height > 0 else 80.0
    bottom_zone_start = (
        page_height - top_zone_end
        if page_height and page_height > 0
        else 720.0
    )
    if span.top <= top_zone_end or span.bottom <= top_zone_end:
        return "top"
    if span.top >= bottom_zone_start or span.bottom >= bottom_zone_start:
        return "bottom"
    return "body"


def _looks_like_page_number(span: PdfTextSpan) -> bool:
    text = _normalize_text(span.text)
    return bool(_PAGE_NUMBER_PATTERN.match(text)) and _page_zone(span) in {"top", "bottom"}


def _looks_like_heading_candidate(span: PdfTextSpan, *, median_font_size: float | None) -> bool:
    text = _normalize_text(span.text)
    if not text or _looks_like_page_number(span):
        return False
    words = text.split()
    if len(words) > 14:
        return False
    font_size = span.font_size if isinstance(span.font_size, (int, float)) else None
    if median_font_size and font_size and font_size >= median_font_size * 1.18:
        return True
    alpha_chars = [char for char in text if char.isalpha()]
    uppercase_ratio = (
        sum(1 for char in alpha_chars if char.isupper()) / len(alpha_chars)
        if alpha_chars
        else 0.0
    )
    return span.is_bold and (uppercase_ratio >= 0.55 or len(words) <= 8)


def _normalize_text(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", str(text or "")).strip()


def _text_char_count(text: str) -> int:
    return len(_normalize_text(text).replace(" ", ""))


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _decide_text_layer_quality(
    *,
    status: str,
    visible_text_chars: int,
    body_span_count: int,
    body_text_ratio: float,
    repeated_page_furniture_text_ratio: float,
    heading_candidate_count: int,
    list_candidate_count: int,
    bold_span_count: int,
    italic_span_count: int,
    median_font_size: float | None,
    largest_font_size: float | None,
) -> tuple[str, tuple[str, ...]]:
    if status != "ok":
        return "scanned_or_unsupported", ("unsupported_status",)
    if visible_text_chars == 0 or body_span_count == 0:
        return "scanned_or_unsupported", ("empty_text_layer",)
    if visible_text_chars < 500 or body_span_count < 10:
        return "scanned_or_unsupported", ("too_little_text_layer",)

    reasons: list[str] = []
    if visible_text_chars < _DECISION_THRESHOLDS["min_visible_text_chars"]:
        reasons.append("low_visible_text_chars")
    if body_span_count < _DECISION_THRESHOLDS["min_body_span_count"]:
        reasons.append("low_body_span_count")
    if body_text_ratio < _DECISION_THRESHOLDS["min_body_text_ratio"]:
        reasons.append("low_body_text_ratio")
    if repeated_page_furniture_text_ratio > _DECISION_THRESHOLDS["max_repeated_page_furniture_text_ratio"]:
        reasons.append("high_page_furniture_ratio")
    if not _has_structure_signal(
        heading_candidate_count=heading_candidate_count,
        list_candidate_count=list_candidate_count,
        bold_span_count=bold_span_count,
        italic_span_count=italic_span_count,
        median_font_size=median_font_size,
        largest_font_size=largest_font_size,
    ):
        reasons.append("no_structure_signals")
    if reasons:
        return "insufficient", tuple(reasons)
    return "promising", ("text_layer_dense_with_structure_signals",)


def _has_structure_signal(
    *,
    heading_candidate_count: int,
    list_candidate_count: int,
    bold_span_count: int,
    italic_span_count: int,
    median_font_size: float | None,
    largest_font_size: float | None,
) -> bool:
    if heading_candidate_count > 0 or list_candidate_count > 0:
        return True
    if bold_span_count > 0 or italic_span_count > 0:
        return True
    return bool(
        median_font_size
        and largest_font_size
        and largest_font_size > median_font_size
    )


def _interpret_decision(decision: str) -> str:
    if decision == "promising":
        return "Text layer is dense enough for PR-PDF1 importer work."
    if decision == "insufficient":
        return "Text exists, but source-import evidence is not strong enough for promotion."
    return "No usable text-layer proof yet; use fallback or OCR path."


def _pdfminer_top_origin_bounds(
    *,
    y0: float,
    y1: float,
    page_height: float | None,
) -> tuple[float, float]:
    if not page_height or page_height <= 0:
        return float(y1), float(y0)
    top = max(0.0, page_height - float(y1))
    bottom = max(top, page_height - float(y0))
    return top, bottom


def _most_common(values: Iterable[str]) -> str:
    counter = Counter(value for value in values if value)
    if not counter:
        return ""
    return counter.most_common(1)[0][0]


def _font_style_flags(font_name: str) -> tuple[bool, bool]:
    """Map a PDF font name to ``(is_bold, is_italic)``.

    The subset prefix (``^[A-Z]{6}\\+``) is stripped and only the trailing style
    chunk (after the last ``-`` or ``,``) is inspected, so family-name substrings —
    the ``it`` in ``Didot`` or the bare ``BT`` in ``NewsGothicBT`` — cannot pose as
    style signals. A name without a style separator carries no style information and
    is treated as regular.
    """
    name = _FONT_SUBSET_PREFIX_PATTERN.sub("", str(font_name or ""))
    separator_index = max(name.rfind("-"), name.rfind(","))
    if separator_index < 0:
        return (False, False)
    tail = name[separator_index + 1 :].lower()
    if not tail:
        return (False, False)
    is_bold = any(token in tail for token in _FONT_BOLD_STYLE_TOKENS)
    is_italic = any(token in tail for token in _FONT_ITALIC_STYLE_TOKENS)
    return (is_bold, is_italic)


def _style_runs_from_line_items(
    items: Iterable[object],
    *,
    char_text_overrides: Mapping[int, str] | None = None,
) -> tuple[tuple[str, bool, bool], ...]:
    """Group a line's characters into consecutive same-style runs.

    ``items`` may mix real characters (carrying ``fontname``) with virtual layout
    characters (spaces/newlines inferred by the extractor, which have no font); the
    latter inherit the current style so a space inside an italic word does not split
    the run. The returned runs are whitespace-normalized so their concatenation equals
    ``_normalize_text`` of the line text.

    ``char_text_overrides`` maps ``id(item)`` to the text that item contributes, so a
    footnote reference can be emitted as a superscript glyph without disturbing the
    runs' structure. The same map must be used to build the span text, or the runs
    would stop reconstructing it and be discarded downstream.
    """
    raw: list[tuple[str, bool, bool]] = []
    current_style: tuple[bool, bool] | None = None
    buffer: list[str] = []
    for item in items:
        get_text = getattr(item, "get_text", None)
        if not callable(get_text):
            continue
        piece = str(get_text() or "")
        if char_text_overrides and id(item) in char_text_overrides:
            piece = char_text_overrides[id(item)]
        if not piece:
            continue
        if hasattr(item, "fontname"):
            style = _font_style_flags(str(getattr(item, "fontname", "") or ""))
        else:
            style = current_style if current_style is not None else (False, False)
        if current_style is None:
            current_style = style
        elif style != current_style:
            raw.append(("".join(buffer), current_style[0], current_style[1]))
            buffer = []
            current_style = style
        buffer.append(piece)
    if buffer and current_style is not None:
        raw.append(("".join(buffer), current_style[0], current_style[1]))
    return _normalize_style_runs(raw)


def _normalize_style_runs(
    runs: Iterable[tuple[str, bool, bool]],
) -> tuple[tuple[str, bool, bool], ...]:
    """Collapse internal whitespace to single spaces and strip the ends, preserving
    per-run style. The concatenation of the result equals ``_normalize_text`` of the
    concatenated input text."""
    result: list[tuple[str, bool, bool]] = []
    pending_space = False
    started = False
    for text, is_bold, is_italic in runs:
        chars_out: list[str] = []
        for char in text:
            if char.isspace():
                if started:
                    pending_space = True
                continue
            if pending_space:
                chars_out.append(" ")
                pending_space = False
            chars_out.append(char)
            started = True
        segment = "".join(chars_out)
        if segment:
            result.append((segment, bool(is_bold), bool(is_italic)))
    return tuple(result)


def _coerce_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
