"""Build source paragraph units from deterministic PDF text-layer spans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.pdf_import.text_layer_quality import (
    PdfTextSpan,
    _detect_repeated_page_furniture_keys,
    _looks_like_page_number,
    _normalize_text,
    _span_furniture_key,
)


_BULLET_PATTERN = re.compile(r"^(?P<marker>[-*•●])\s+(?P<body>.+)$")
_ORDERED_LIST_PATTERN = re.compile(r"^(?P<marker>\d+)[.)]\s+(?P<body>.+)$")
_TOC_TRAILING_PAGE_PATTERN = re.compile(
    r"^(?P<title>.+?)\s+(?:\.{2,}\s*)?(?P<page>\d{1,4}|[ivxlcdmIVXLCDM]{1,12})$"
)
_CAPTION_PATTERN = re.compile(
    r"^(?:fig(?:ure)?\.?|table|табл\.?|рис\.?)\s+[A-ZА-Я]?\d+(?:[.\-:]\d+)?(?:[.)]\s*|\s+).+",
    re.IGNORECASE,
)
_DASH_ATTRIBUTION_PATTERN = re.compile(r"^[\u2013\u2014-]\s+\S+")
_LOCATION_OR_SIGNATURE_LINE_PATTERN = re.compile(
    r"^[A-ZА-Я][\wА-Яа-яЁё.'-]+(?:\s+[A-ZА-Я][\wА-Яа-яЁё.'-]+){0,2},\s+"
    r"[A-ZА-Я][\wА-Яа-яЁё.'-]+(?:\s+[A-ZА-Я][\wА-Яа-яЁё.'-]+){0,2}$"
)
_BYLINE_PATTERN = re.compile(r"^by\s+[A-ZА-Я]", re.IGNORECASE)
_BLANK_PAGE_NOTICE_PATTERN = re.compile(
    r"^(?:this\s+page\s+(?:is\s+)?(?:intentionally|deliberately)\s+left\s+blank|"
    r"страниц[аы]\s+(?:намеренно|умышленно)\s+оставлен[аы]\s+пуст(?:ой|ая|ые|ыми|а|ы)?)\.?$",
    re.IGNORECASE,
)
_TERMINAL_SENTENCE_PUNCTUATION = ".!?;:»”\"'"
_OPENING_TEXT_BOUNDARY_CHARS = "\"“‘'«"


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


@dataclass(frozen=True)
class _PdfHeadingLayoutProfile:
    median_font_size: float | None
    body_left_x0: float | None


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
    layout_profile = _build_heading_layout_profile(
        normalized_spans,
        repeated_furniture_keys=repeated_furniture_keys,
        median_font_size=median_font_size,
    )

    emitted: list[ParagraphUnit] = []
    pending_body_spans: list[PdfTextSpan] = []
    pending_heading_spans: list[PdfTextSpan] = []
    skipped_repeated_page_furniture_count = 0
    skipped_page_number_count = 0
    skipped_blank_page_notice_count = 0

    def _flush_body() -> None:
        nonlocal pending_body_spans
        if pending_body_spans:
            emitted.append(_paragraph_from_body_spans(pending_body_spans))
            pending_body_spans = []

    def _flush_heading() -> None:
        nonlocal pending_heading_spans
        if pending_heading_spans:
            emitted.append(
                _paragraph_from_heading_spans(
                    pending_heading_spans, median_font_size=median_font_size
                )
            )
            pending_heading_spans = []

    ordered_spans = sorted(normalized_spans, key=lambda item: (item.page_number, item.top, item.x0))
    for span_index, span in enumerate(ordered_spans):
        if _span_furniture_key(span) in repeated_furniture_keys:
            skipped_repeated_page_furniture_count += 1
            continue
        if _looks_like_page_number(span):
            skipped_page_number_count += 1
            continue
        if _looks_like_blank_page_notice(span):
            skipped_blank_page_notice_count += 1
            continue
        role = _classify_span_role(
            span,
            layout_profile=layout_profile,
            previous_span=_nearest_content_span(
                ordered_spans,
                span_index,
                direction=-1,
                repeated_furniture_keys=repeated_furniture_keys,
            ),
            next_span=_nearest_content_span(
                ordered_spans,
                span_index,
                direction=1,
                repeated_furniture_keys=repeated_furniture_keys,
            ),
        )
        if role == "body":
            _flush_heading()
            if pending_body_spans and not _can_merge_body_span(pending_body_spans[-1], span):
                _flush_body()
            pending_body_spans.append(span)
            continue
        if role == "heading":
            _flush_body()
            if pending_heading_spans and not _can_merge_heading_span(
                pending_heading_spans[-1], span
            ):
                _flush_heading()
            pending_heading_spans.append(span)
            continue
        if role == "toc_entry":
            _flush_body()
            _flush_heading()
            emitted.append(_paragraph_from_span(span, role=role, median_font_size=median_font_size))
            continue
        _flush_body()
        _flush_heading()
        emitted.append(_paragraph_from_span(span, role=role, median_font_size=median_font_size))

    _flush_body()
    _flush_heading()

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


def _classify_span_role(
    span: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    previous_span: PdfTextSpan | None,
    next_span: PdfTextSpan | None,
) -> str:
    text = _normalize_text(span.text)
    if _BULLET_PATTERN.match(text) or _ORDERED_LIST_PATTERN.match(text):
        return "list"
    if _looks_like_caption(span):
        return "caption"
    if _looks_like_toc_entry(span):
        return "toc_entry"
    if _looks_like_non_heading_front_matter_line(span):
        return "body"
    if _looks_like_pdf_heading_candidate(
        span,
        layout_profile=layout_profile,
        previous_span=previous_span,
        next_span=next_span,
    ):
        return "heading"
    return "body"


def _build_heading_layout_profile(
    spans: list[PdfTextSpan],
    *,
    repeated_furniture_keys: set[tuple[str, str]],
    median_font_size: float | None,
) -> _PdfHeadingLayoutProfile:
    body_left_candidates: list[float] = []
    for span in spans:
        text = _normalize_text(span.text)
        if not text:
            continue
        if _span_furniture_key(span) in repeated_furniture_keys:
            continue
        if _looks_like_page_number(span) or _looks_like_toc_entry(span):
            continue
        words = _words(text)
        if len(words) < 7:
            continue
        if median_font_size and span.font_size:
            ratio = float(span.font_size) / median_font_size
            if ratio < 0.75 or ratio > 1.25:
                continue
        body_left_candidates.append(float(span.x0))
    body_left_x0 = float(median(body_left_candidates)) if body_left_candidates else None
    return _PdfHeadingLayoutProfile(
        median_font_size=median_font_size,
        body_left_x0=body_left_x0,
    )


def _nearest_content_span(
    spans: list[PdfTextSpan],
    span_index: int,
    *,
    direction: int,
    repeated_furniture_keys: set[tuple[str, str]],
) -> PdfTextSpan | None:
    index = span_index + direction
    while 0 <= index < len(spans):
        candidate = spans[index]
        if (
            _span_furniture_key(candidate) not in repeated_furniture_keys
            and not _looks_like_page_number(candidate)
            and not _looks_like_blank_page_notice(candidate)
            and _normalize_text(candidate.text)
        ):
            return candidate
        index += direction
    return None


def _looks_like_pdf_heading_candidate(
    span: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    previous_span: PdfTextSpan | None,
    next_span: PdfTextSpan | None,
) -> bool:
    text = _normalize_text(span.text)
    words = _words(text)
    if not text or not words or len(words) > 14:
        return False
    if _looks_like_glued_heading_line(text):
        return False
    if _has_terminal_sentence_punctuation(text):
        return False
    font_ratio = _font_ratio(span, layout_profile.median_font_size)
    uppercase_ratio = _uppercase_ratio(text)
    title_word_ratio = _title_word_ratio(words)
    strong_indent = _strong_heading_indent(span, layout_profile)
    standalone_context = _looks_like_standalone_heading_context(
        span,
        previous_span=previous_span,
        next_span=next_span,
    )

    if font_ratio is not None and font_ratio >= 1.18:
        return True
    if span.is_bold and uppercase_ratio >= 0.55:
        return True
    if span.is_bold and strong_indent and len(words) <= 8:
        return True
    if span.is_bold and len(words) <= 4 and standalone_context:
        return True
    if uppercase_ratio >= 0.72 and len(words) <= 10:
        return strong_indent or standalone_context
    if title_word_ratio >= 0.65 and len(words) <= 6 and strong_indent:
        return True
    if title_word_ratio >= 0.75 and len(words) <= 3 and standalone_context:
        return True
    return False


def _words(text: str) -> list[str]:
    return [word for word in re.split(r"\s+", text) if word]


def _looks_like_caption(span: PdfTextSpan) -> bool:
    return bool(_CAPTION_PATTERN.match(_normalize_text(span.text)))


def _looks_like_non_heading_front_matter_line(span: PdfTextSpan) -> bool:
    text = _normalize_text(span.text)
    if not text:
        return False
    if _DASH_ATTRIBUTION_PATTERN.match(text):
        return True
    if _BYLINE_PATTERN.match(text) and len(_words(text)) <= 5:
        return True
    if (
        _LOCATION_OR_SIGNATURE_LINE_PATTERN.match(text)
        and len(_words(text)) <= 4
        and _uppercase_ratio(text) < 0.55
    ):
        return True
    if _looks_like_person_pair_byline(text):
        return True
    return False


def _looks_like_person_pair_byline(text: str) -> bool:
    if " & " not in text and " and " not in text:
        return False
    if any(marker in text for marker in (":", ";", "?", "!")):
        return False
    words = [word.strip(".,'\"“”‘’") for word in _words(text)]
    if len(words) < 3 or len(words) > 7:
        return False
    joiners = {"&", "and"}
    name_like = [
        word
        for word in words
        if word not in joiners and word[:1].isupper() and not word.isupper()
    ]
    return len(name_like) >= 3 and len(name_like) + sum(word in joiners for word in words) == len(words)


def _looks_like_glued_heading_line(text: str) -> bool:
    words = _words(text)
    if len(text) <= 90 and len(words) <= 14:
        return False
    title_like_words = sum(
        1
        for word in words
        if (cleaned := word.strip(".,:;()[]\"“”‘’'«»")) and cleaned[:1].isupper()
    )
    colon_count = text.count(":")
    return colon_count >= 2 or title_like_words >= max(8, len(words) // 2)


def _font_ratio(span: PdfTextSpan, median_font_size: float | None) -> float | None:
    if not median_font_size or not span.font_size:
        return None
    return float(span.font_size) / median_font_size


def _uppercase_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for char in letters if char.isupper()) / len(letters)


def _title_word_ratio(words: list[str]) -> float:
    alpha_words = [word.strip("\"“”‘’'«»()[]") for word in words if any(char.isalpha() for char in word)]
    if not alpha_words:
        return 0.0
    titled = 0
    for word in alpha_words:
        first_alpha = next((char for char in word if char.isalpha()), "")
        if first_alpha.isupper():
            titled += 1
    return titled / len(alpha_words)


def _has_terminal_sentence_punctuation(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?", ";"))


def _strong_heading_indent(span: PdfTextSpan, layout_profile: _PdfHeadingLayoutProfile) -> bool:
    if layout_profile.body_left_x0 is None:
        return False
    return float(span.x0) - layout_profile.body_left_x0 >= 35.0


def _looks_like_standalone_heading_context(
    span: PdfTextSpan,
    *,
    previous_span: PdfTextSpan | None,
    next_span: PdfTextSpan | None,
) -> bool:
    if next_span is None or next_span.page_number != span.page_number:
        return False
    current_text = _normalize_text(span.text)
    next_text = _normalize_text(next_span.text)
    next_words = _words(next_text)
    next_is_heading_like = len(next_words) >= 2 and _uppercase_ratio(next_text) >= 0.72
    if not current_text or not next_text or (len(next_words) < 4 and not next_is_heading_like):
        return False
    if _BULLET_PATTERN.match(next_text) or _ORDERED_LIST_PATTERN.match(next_text):
        return False
    previous_boundary = previous_span is None or previous_span.page_number != span.page_number
    if previous_span is not None and previous_span.page_number == span.page_number:
        previous_text = _normalize_text(previous_span.text)
        previous_boundary = bool(previous_text and previous_text[-1] in _TERMINAL_SENTENCE_PUNCTUATION)
    if not previous_boundary:
        return False
    current_font_size = span.font_size if isinstance(span.font_size, (int, float)) else 10.0
    next_gap = max(0.0, float(next_span.top) - float(span.bottom))
    previous_gap = 0.0
    if previous_span is not None and previous_span.page_number == span.page_number:
        previous_gap = max(0.0, float(span.top) - float(previous_span.bottom))
    has_visual_gap = previous_gap >= current_font_size * 0.6 and next_gap >= current_font_size * 0.35
    starts_new_body_line = next_text[0].isupper() or next_text[0] in _OPENING_TEXT_BOUNDARY_CHARS
    return has_visual_gap or starts_new_body_line


def _can_merge_body_span(previous: PdfTextSpan, current: PdfTextSpan) -> bool:
    if previous.page_number != current.page_number:
        return False
    if _looks_like_toc_entry(previous) or _looks_like_toc_entry(current):
        return False
    if _looks_like_body_paragraph_indent_boundary(previous, current):
        return False
    previous_font_size = previous.font_size if isinstance(previous.font_size, (int, float)) else 10.0
    current_font_size = current.font_size if isinstance(current.font_size, (int, float)) else previous_font_size
    vertical_gap = max(0.0, float(current.top) - float(previous.bottom))
    max_gap = max(8.0, min(previous_font_size, current_font_size) * 1.25)
    return vertical_gap <= max_gap


def _looks_like_body_paragraph_indent_boundary(previous: PdfTextSpan, current: PdfTextSpan) -> bool:
    previous_text = _normalize_text(previous.text)
    current_text = _normalize_text(current.text)
    if not previous_text or not current_text:
        return False
    previous_x0 = float(previous.x0)
    current_x0 = float(current.x0)
    indent_delta = current_x0 - previous_x0
    if indent_delta >= 8.0:
        return True
    if current_x0 < 12.0 or abs(indent_delta) > 3.0:
        return False
    if previous_text[-1] not in _TERMINAL_SENTENCE_PUNCTUATION:
        return False
    first_char = current_text[0]
    return first_char in _OPENING_TEXT_BOUNDARY_CHARS or first_char.isupper()


def _can_merge_heading_span(previous: PdfTextSpan, current: PdfTextSpan) -> bool:
    if previous.page_number != current.page_number:
        return False
    if _looks_like_toc_entry(previous) or _looks_like_toc_entry(current):
        return False
    previous_text = _normalize_text(previous.text)
    if previous_text and previous_text[-1] in ".!?:":
        return False
    previous_font_size = (
        float(previous.font_size)
        if isinstance(previous.font_size, (int, float)) and previous.font_size > 0
        else None
    )
    current_font_size = (
        float(current.font_size)
        if isinstance(current.font_size, (int, float)) and current.font_size > 0
        else None
    )
    if previous_font_size and current_font_size:
        smaller = min(previous_font_size, current_font_size)
        larger = max(previous_font_size, current_font_size)
        if larger - smaller > max(0.5, smaller * 0.1):
            return False
    base_font_size = previous_font_size or current_font_size or 10.0
    vertical_gap = max(0.0, float(current.top) - float(previous.bottom))
    max_gap = max(8.0, base_font_size * 1.4)
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


def _paragraph_from_heading_spans(
    spans: list[PdfTextSpan],
    *,
    median_font_size: float | None,
) -> ParagraphUnit:
    if len(spans) == 1:
        return _paragraph_from_span(spans[0], role="heading", median_font_size=median_font_size)
    text = " ".join(_normalize_text(span.text) for span in spans)
    if _looks_like_glued_heading_line(text):
        return _paragraph_from_body_spans(spans)
    first = spans[0]
    heading_level = _infer_heading_level(first, median_font_size=median_font_size)
    return ParagraphUnit(
        text=text,
        role="heading",
        structural_role="heading",
        role_confidence="heuristic",
        style_name=_style_name_for_role("heading"),
        heading_level=heading_level,
        heading_source="pdf_text_layer",
        list_level=0,
        is_bold=all(span.is_bold for span in spans),
        is_italic=all(span.is_italic for span in spans),
        font_size_pt=_median_font_size(spans),
        origin_raw_indexes=[_span_origin_index(span) for span in spans],
        origin_raw_texts=[_normalize_text(span.text) for span in spans],
        layout_origin="pdf_text_layer",
        boundary_source="pdf_text_layer",
        boundary_confidence="heuristic",
        boundary_rationale="merged_adjacent_pdf_heading_spans",
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
    if role == "caption":
        return "PDF Caption"
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
