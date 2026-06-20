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
_DECISION_THRESHOLDS = {
    "min_visible_text_chars": 1500,
    "min_body_span_count": 20,
    "min_body_text_ratio": 0.70,
    "max_repeated_page_furniture_text_ratio": 0.25,
}


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
    font_sizes = [
        span.font_size
        for span in normalized_spans
        if isinstance(span.font_size, (int, float))
        and span.font_size > 0
        and _span_furniture_key(span) not in repeated_furniture_keys
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
        is_page_furniture = _span_furniture_key(span) in repeated_furniture_keys
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
        from pdfminer.layout import LTChar, LTTextContainer, LTTextLine
    except ImportError as exc:  # pragma: no cover - depends on optional env
        raise RuntimeError("optional_dependency_missing:pdfminer.six") from exc

    spans: list[PdfTextSpan] = []
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
                chars = [item for item in line if isinstance(item, LTChar)]
                font_names = [str(getattr(char, "fontname", "") or "") for char in chars]
                font_sizes = [float(getattr(char, "size", 0.0) or 0.0) for char in chars]
                font_name = _most_common(font_names)
                font_size = median(font_sizes) if font_sizes else None
                font_name_lower = font_name.lower()
                top, bottom = _pdfminer_top_origin_bounds(
                    y0=float(line.y0),
                    y1=float(line.y1),
                    page_height=page_height,
                )
                trailing_superscript_split = _split_trailing_superscript_marker_chars(chars)
                if trailing_superscript_split is None:
                    spans.append(
                        PdfTextSpan(
                            page_number=page_index,
                            text=text,
                            x0=float(line.x0),
                            top=top,
                            x1=float(line.x1),
                            bottom=bottom,
                            page_height=page_height,
                            font_name=font_name,
                            font_size=float(font_size) if font_size else None,
                            is_bold="bold" in font_name_lower or "black" in font_name_lower,
                            is_italic="italic" in font_name_lower or "oblique" in font_name_lower,
                        )
                    )
                    continue
                for segment_chars in trailing_superscript_split:
                    span = _pdf_text_span_from_chars(
                        segment_chars,
                        page_number=page_index,
                        page_height=page_height,
                    )
                    if span is not None:
                        spans.append(span)
    return spans


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
    return last_char.isalpha() or last_char in ".!?:;)]}»”\"'"


def _pdf_text_span_from_chars(
    chars: Sequence[object],
    *,
    page_number: int,
    page_height: float | None,
) -> PdfTextSpan | None:
    text = "".join(str(getattr(char, "get_text", lambda: "")() or "") for char in chars).strip()
    if not text:
        return None
    font_names = [str(getattr(char, "fontname", "") or "") for char in chars]
    font_sizes = [
        float(getattr(char, "size", 0.0) or 0.0)
        for char in chars
        if float(getattr(char, "size", 0.0) or 0.0) > 0
    ]
    font_name = _most_common(font_names)
    font_name_lower = font_name.lower()
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
        is_bold="bold" in font_name_lower or "black" in font_name_lower,
        is_italic="italic" in font_name_lower or "oblique" in font_name_lower,
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
