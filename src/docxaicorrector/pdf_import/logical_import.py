"""Build source paragraph units from deterministic PDF text-layer spans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.pdf_import.text_layer_quality import (
    PdfTextSpan,
    _detect_repeated_page_furniture_keys,
    _looks_like_heading_candidate,
    _looks_like_page_number,
    _normalize_text,
    _span_furniture_key,
)


_BULLET_PATTERN = re.compile(r"^(?P<marker>[-*•●])\s+(?P<body>.+)$")
_ORDERED_LIST_PATTERN = re.compile(r"^(?P<marker>\d+)[.)]\s+(?P<body>.+)$")
_TOC_TRAILING_PAGE_PATTERN = re.compile(
    r"^(?P<title>.+?)\s+(?:\.{2,}\s*)?(?P<page>\d{1,4}|[ivxlcdmIVXLCDM]{1,12})$"
)
_BLANK_PAGE_NOTICE_PATTERN = re.compile(
    r"^(?:this\s+page\s+(?:is\s+)?(?:intentionally|deliberately)\s+left\s+blank|"
    r"страниц[аы]\s+(?:намеренно|умышленно)\s+оставлен[аы]\s+пуст(?:ой|ая|ые|ыми|а|ы)?)\.?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PdfSourceImportReport:
    input_span_count: int
    emitted_paragraph_count: int
    skipped_repeated_page_furniture_count: int
    skipped_page_number_count: int
    skipped_blank_page_notice_count: int
    heading_count: int
    list_count: int


@dataclass(frozen=True)
class PdfSourceImportResult:
    paragraphs: list[ParagraphUnit]
    report: PdfSourceImportReport


def build_paragraph_units_from_text_spans(
    spans: list[PdfTextSpan],
) -> PdfSourceImportResult:
    normalized_spans = [span for span in spans if _normalize_text(span.text)]
    repeated_furniture_keys = _detect_repeated_page_furniture_keys(tuple(normalized_spans))
    font_sizes = [
        span.font_size
        for span in normalized_spans
        if isinstance(span.font_size, (int, float)) and span.font_size > 0
        and _span_furniture_key(span) not in repeated_furniture_keys
        and not _looks_like_page_number(span)
    ]
    median_font_size = float(median(font_sizes)) if font_sizes else None

    emitted: list[ParagraphUnit] = []
    pending_body_spans: list[PdfTextSpan] = []
    skipped_repeated_page_furniture_count = 0
    skipped_page_number_count = 0
    skipped_blank_page_notice_count = 0

    for span in sorted(normalized_spans, key=lambda item: (item.page_number, item.top, item.x0)):
        if _span_furniture_key(span) in repeated_furniture_keys:
            skipped_repeated_page_furniture_count += 1
            continue
        if _looks_like_page_number(span):
            skipped_page_number_count += 1
            continue
        if _looks_like_blank_page_notice(span):
            skipped_blank_page_notice_count += 1
            continue
        role = _classify_span_role(span, median_font_size=median_font_size)
        if role == "body":
            if pending_body_spans and not _can_merge_body_span(pending_body_spans[-1], span):
                emitted.append(_paragraph_from_body_spans(pending_body_spans))
                pending_body_spans = []
            pending_body_spans.append(span)
            continue
        if role == "toc_entry":
            if pending_body_spans:
                emitted.append(_paragraph_from_body_spans(pending_body_spans))
                pending_body_spans = []
            emitted.append(_paragraph_from_span(span, role=role, median_font_size=median_font_size))
            continue
        if pending_body_spans:
            emitted.append(_paragraph_from_body_spans(pending_body_spans))
            pending_body_spans = []
        emitted.append(_paragraph_from_span(span, role=role, median_font_size=median_font_size))

    if pending_body_spans:
        emitted.append(_paragraph_from_body_spans(pending_body_spans))

    for logical_index, paragraph in enumerate(emitted):
        _assign_pdf_paragraph_identity(paragraph, logical_index)

    return PdfSourceImportResult(
        paragraphs=emitted,
        report=PdfSourceImportReport(
            input_span_count=len(normalized_spans),
            emitted_paragraph_count=len(emitted),
            skipped_repeated_page_furniture_count=skipped_repeated_page_furniture_count,
            skipped_page_number_count=skipped_page_number_count,
            skipped_blank_page_notice_count=skipped_blank_page_notice_count,
            heading_count=sum(1 for paragraph in emitted if paragraph.role == "heading"),
            list_count=sum(1 for paragraph in emitted if paragraph.role == "list"),
        ),
    )


def _classify_span_role(span: PdfTextSpan, *, median_font_size: float | None) -> str:
    text = _normalize_text(span.text)
    if _BULLET_PATTERN.match(text) or _ORDERED_LIST_PATTERN.match(text):
        return "list"
    if _looks_like_toc_entry(span):
        return "toc_entry"
    if _looks_like_heading_candidate(span, median_font_size=median_font_size):
        return "heading"
    return "body"


def _can_merge_body_span(previous: PdfTextSpan, current: PdfTextSpan) -> bool:
    if previous.page_number != current.page_number:
        return False
    if _looks_like_toc_entry(previous) or _looks_like_toc_entry(current):
        return False
    previous_font_size = previous.font_size if isinstance(previous.font_size, (int, float)) else 10.0
    current_font_size = current.font_size if isinstance(current.font_size, (int, float)) else previous_font_size
    vertical_gap = max(0.0, float(current.top) - float(previous.bottom))
    max_gap = max(8.0, min(previous_font_size, current_font_size) * 1.25)
    return vertical_gap <= max_gap


def _paragraph_from_body_spans(spans: list[PdfTextSpan]) -> ParagraphUnit:
    text = " ".join(_normalize_text(span.text) for span in spans)
    first = spans[0]
    return ParagraphUnit(
        text=text,
        role="body",
        structural_role="body",
        role_confidence="heuristic",
        style_name="PDF Body",
        is_bold=all(span.is_bold for span in spans),
        is_italic=all(span.is_italic for span in spans),
        font_size_pt=_median_font_size(spans),
        origin_raw_indexes=[_span_origin_index(span) for span in spans],
        origin_raw_texts=[_normalize_text(span.text) for span in spans],
        layout_origin="pdf_text_layer",
        boundary_source="pdf_text_layer",
        boundary_confidence="heuristic",
        boundary_rationale="merged_adjacent_pdf_text_spans",
        source_index=_span_origin_index(first),
    )


def _paragraph_from_span(
    span: PdfTextSpan,
    *,
    role: str,
    median_font_size: float | None,
) -> ParagraphUnit:
    text = _normalize_text(span.text)
    list_kind = None
    if role == "list":
        list_kind = "ordered" if _ORDERED_LIST_PATTERN.match(text) else "bullet"
    heading_level = _infer_heading_level(span, median_font_size=median_font_size) if role == "heading" else None
    structural_role = "toc_entry" if role == "toc_entry" else role
    paragraph_role = "body" if role == "toc_entry" else role
    return ParagraphUnit(
        text=text,
        role=paragraph_role,
        structural_role=structural_role,
        role_confidence="heuristic",
        style_name=_style_name_for_role(role),
        heading_level=heading_level,
        heading_source="pdf_text_layer" if heading_level is not None else None,
        list_kind=list_kind,
        list_level=0,
        is_bold=span.is_bold,
        is_italic=span.is_italic,
        font_size_pt=span.font_size,
        origin_raw_indexes=[_span_origin_index(span)],
        origin_raw_texts=[text],
        layout_origin="pdf_text_layer",
        boundary_source="pdf_text_layer",
        boundary_confidence="heuristic",
        source_index=_span_origin_index(span),
    )


def _infer_heading_level(span: PdfTextSpan, *, median_font_size: float | None) -> int:
    if not median_font_size or not span.font_size:
        return 2
    ratio = span.font_size / median_font_size
    if ratio >= 1.8:
        return 1
    if ratio >= 1.35:
        return 2
    return 3


def _style_name_for_role(role: str) -> str:
    if role == "heading":
        return "PDF Heading"
    if role == "list":
        return "PDF List"
    if role == "toc_entry":
        return "PDF TOC Entry"
    return "PDF Body"


def _looks_like_toc_entry(span: PdfTextSpan) -> bool:
    text = _normalize_text(span.text)
    if not text:
        return False
    match = _TOC_TRAILING_PAGE_PATTERN.match(text)
    if match is None:
        return False
    title = str(match.group("title") or "").strip()
    if not title or title.isdigit():
        return False
    words = [word for word in re.split(r"\s+", title) if word]
    if len(words) > 16:
        return False
    return True


def _looks_like_blank_page_notice(span: PdfTextSpan) -> bool:
    text = _normalize_text(span.text).strip("*_ ")
    return bool(_BLANK_PAGE_NOTICE_PATTERN.match(text))


def _median_font_size(spans: list[PdfTextSpan]) -> float | None:
    font_sizes = [
        span.font_size
        for span in spans
        if isinstance(span.font_size, (int, float)) and span.font_size > 0
    ]
    return float(median(font_sizes)) if font_sizes else None


def _span_origin_index(span: PdfTextSpan) -> int:
    return max(0, (span.page_number - 1) * 10000 + int(round(span.top)))


def _assign_pdf_paragraph_identity(paragraph: ParagraphUnit, logical_index: int) -> None:
    paragraph.logical_index = logical_index
    paragraph.paragraph_id = f"p{logical_index:04d}"
    if int(getattr(paragraph, "source_index", -1)) < 0:
        paragraph.source_index = logical_index
