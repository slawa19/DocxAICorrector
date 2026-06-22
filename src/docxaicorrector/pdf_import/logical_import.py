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
_EPIGRAPH_CREDIT_PATTERN = re.compile(
    r"^[A-ZА-Я][\wА-Яа-яЁё.'-]+(?:\s+[A-ZА-Я][\wА-Яа-яЁё.'-]+){0,3}"
    r"(?:,\s+[^,]{2,48})?,\s+(?:18|19|20)\d{2}\d{0,2}\.?$"
)
_EPIGRAPH_SOURCE_CREDIT_PATTERN = re.compile(
    r"^[A-ZА-Я][\wА-Яа-яЁё.'-]+(?:\s+[A-ZА-Я][\wА-Яа-яЁё.'-]+){0,3},\s+"
    r".*(?:\(\d{4}\)|\d{1,3})$"
)
_FOOTNOTE_OR_CITATION_TAIL_PATTERN = re.compile(
    r"(?:\[\s*online\s*\]|https?://|www\.|(?:18|19|20)\d{2}\].*|[;,]\s*$)",
    re.IGNORECASE,
)
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
    body_font_size: float | None
    body_left_x0: float | None
    body_right_x1: float | None
    body_leading: float | None
    body_line_length_p75: float
    body_line_length_p90: float
    body_uppercase_ratio: float
    body_title_word_ratio: float
    clusters: tuple["_PdfStyleCluster", ...] = ()
    heading_cluster_ids: frozenset[int] = frozenset()
    ambiguous_cluster_ids: frozenset[int] = frozenset()
    repeated_display_text_keys: frozenset[str] = frozenset()
    heading_prominence_threshold: float = 0.0


@dataclass(frozen=True)
class _PdfStyleSignature:
    vector: tuple[float, ...]
    prominence: float
    font_ratio: float
    indent_units: float
    isolation_units: float
    uppercase_delta: float
    title_delta: float
    shortness: float
    boundary_context: float


@dataclass(frozen=True)
class _PdfStyleCluster:
    cluster_id: int
    size: int
    center: tuple[float, ...]
    prominence: float


def build_paragraph_units_from_text_spans(
    spans: list[PdfTextSpan],
) -> PdfSourceImportResult:
    normalized_spans = [span for span in spans if _normalize_text(span.text)]
    repeated_furniture_keys = _detect_repeated_page_furniture_keys(tuple(normalized_spans))
    ordered_spans = sorted(normalized_spans, key=lambda item: (item.page_number, item.top, item.x0))
    layout_profile = _build_heading_layout_profile(
        ordered_spans,
        repeated_furniture_keys=repeated_furniture_keys,
    )
    median_font_size = layout_profile.body_font_size

    emitted: list[ParagraphUnit] = []
    pending_body_spans: list[PdfTextSpan] = []
    pending_body_inline_markers: dict[int, list[str]] = {}
    pending_heading_spans: list[PdfTextSpan] = []
    pending_list_spans: list[PdfTextSpan] = []
    skipped_repeated_page_furniture_count = 0
    skipped_page_number_count = 0
    skipped_blank_page_notice_count = 0

    def _flush_body() -> None:
        nonlocal pending_body_spans, pending_body_inline_markers
        if pending_body_spans:
            emitted.append(
                _paragraph_from_body_spans(
                    pending_body_spans, inline_markers=pending_body_inline_markers
                )
            )
            pending_body_spans = []
            pending_body_inline_markers = {}

    def _flush_heading() -> None:
        nonlocal pending_heading_spans
        if pending_heading_spans:
            emitted.append(
                _paragraph_from_heading_spans(
                    pending_heading_spans, median_font_size=median_font_size
                )
            )
            pending_heading_spans = []

    def _flush_list() -> None:
        nonlocal pending_list_spans
        if pending_list_spans:
            emitted.append(
                _paragraph_from_list_spans(
                    pending_list_spans, median_font_size=median_font_size
                )
            )
            pending_list_spans = []

    for span_index, span in enumerate(ordered_spans):
        if _span_furniture_key(span) in repeated_furniture_keys:
            skipped_repeated_page_furniture_count += 1
            continue
        previous_content_span = _nearest_content_span(
            ordered_spans,
            span_index,
            direction=-1,
            repeated_furniture_keys=repeated_furniture_keys,
        )
        next_content_span = _nearest_content_span(
            ordered_spans,
            span_index,
            direction=1,
            repeated_furniture_keys=repeated_furniture_keys,
        )
        if (
            _looks_like_page_number(span)
            and not _looks_like_superscript_footnote_marker(
                span,
                previous_span=previous_content_span,
                next_span=next_content_span,
                layout_profile=layout_profile,
            )
        ):
            skipped_page_number_count += 1
            continue
        if _looks_like_blank_page_notice(span):
            skipped_blank_page_notice_count += 1
            continue
        role = _classify_span_role(
            span,
            layout_profile=layout_profile,
            previous_span=previous_content_span,
            next_span=next_content_span,
        )
        if role == "body":
            _flush_heading()
            if pending_list_spans:
                if _can_merge_list_continuation_span(
                    pending_list_spans[-1],
                    span,
                    layout_profile=layout_profile,
                ):
                    pending_list_spans.append(span)
                    continue
                _flush_list()
            if pending_body_spans and not _can_merge_body_span(
                pending_body_spans[-1],
                span,
                layout_profile=layout_profile,
            ):
                _flush_body()
            pending_body_spans.append(span)
            continue
        if role == "heading":
            _flush_list()
            if len(pending_body_spans) == 1 and _can_prefix_heading_with_standalone_number(
                pending_body_spans[0],
                span,
                layout_profile=layout_profile,
            ):
                prefix_span = pending_body_spans.pop()
                if pending_heading_spans and not _can_merge_heading_span(
                    pending_heading_spans[-1], prefix_span
                ):
                    _flush_heading()
                pending_heading_spans.append(prefix_span)
            else:
                _flush_body()
            if pending_heading_spans and not _can_merge_heading_span(
                pending_heading_spans[-1], span
            ):
                _flush_heading()
            pending_heading_spans.append(span)
            continue
        if role == "list":
            _flush_body()
            _flush_heading()
            if pending_list_spans:
                _flush_list()
            pending_list_spans.append(span)
            continue
        if role == "footnote":
            # Rule 1: a superscript footnote marker is transparent to the body
            # merge. When it interrupts a sentence (a body is pending whose last
            # line has not ended), keep it inline at its position so the prose
            # merges across it instead of being split by a standalone digit
            # paragraph.
            #
            # Rule 1b (sentence-boundary re-attach): a footnote reference that
            # sits AFTER a completed sentence (the pending body's last line ends
            # with terminal punctuation) is re-bound as a trailing marker on the
            # END of that same sentence, instead of surviving as a standalone
            # digit paragraph wedged between two sentences. This reuses the very
            # same ``pending_body_inline_markers`` path as the mid-sentence case;
            # the marker is never lost — it is spliced inline at the tail of the
            # sentence it references. We only re-attach to a *pending body* unit
            # (so we never cross a heading/image/page boundary, and never touch a
            # footnote-DEFINITION block, which is emitted as its own unit and is
            # not a ``pending_body_spans`` context). When there is no safe body to
            # bind to — no pending body, a pending heading/list, or a body whose
            # last line is neither terminated nor a soft-wrap continuation — the
            # marker is left as its own standalone footnote unit (under-attach is
            # safer than mis-binding).
            if pending_body_spans and not pending_heading_spans and not pending_list_spans:
                last_body_text = _normalize_text(pending_body_spans[-1].text)
                next_continues = (
                    next_content_span is not None
                    and _is_soft_wrap_continuation_pair(
                        last_body_text, _normalize_text(next_content_span.text)
                    )
                )
                last_body_terminated = bool(
                    last_body_text and last_body_text[-1] in _TERMINAL_SENTENCE_PUNCTUATION
                )
                if last_body_text and (
                    last_body_terminated
                    or (last_body_text[-1] not in _TERMINAL_SENTENCE_PUNCTUATION and next_continues)
                ):
                    pending_body_inline_markers.setdefault(len(pending_body_spans) - 1, []).append(
                        _normalize_text(span.text)
                    )
                    continue
            _flush_body()
            _flush_heading()
            _flush_list()
            emitted.append(_paragraph_from_span(span, role=role, median_font_size=median_font_size))
            continue
        if role == "toc_entry":
            _flush_body()
            _flush_heading()
            _flush_list()
            emitted.append(_paragraph_from_span(span, role=role, median_font_size=median_font_size))
            continue
        _flush_body()
        _flush_heading()
        _flush_list()
        emitted.append(_paragraph_from_span(span, role=role, median_font_size=median_font_size))

    _flush_body()
    _flush_heading()
    _flush_list()

    emitted = _consolidate_cross_role_continuations(emitted)

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


_STANDALONE_FOOTNOTE_MARKER_PATTERN = re.compile(r"^\d{1,3}$")

# A purely-numeric footnote marker that may be rendered as a trailing Unicode
# superscript when re-attached to the end of a completed sentence.
_SUPERSCRIPT_MARKER_DIGITS_PATTERN = re.compile(r"^\d{1,3}$")
_SUPERSCRIPT_DIGIT_TABLE = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _to_superscript_digits(digits: str) -> str:
    """Render a short numeric footnote marker as Unicode superscript digits."""
    return digits.translate(_SUPERSCRIPT_DIGIT_TABLE)


def _unit_is_standalone_footnote_marker(unit: ParagraphUnit) -> bool:
    if unit.structural_role != "footnote" and unit.role != "footnote":
        return False
    return bool(_STANDALONE_FOOTNOTE_MARKER_PATTERN.match((unit.text or "").strip()))


def _unit_can_lead_continuation(unit: ParagraphUnit) -> bool:
    """A unit that may begin (be the head of) a soft-wrap continuation run.

    TOC / index entries are excluded: they end with a page reference (``, 102`` /
    ``69– 70``) and the next two-column entry can begin lowercase, which would
    otherwise be mistaken for a sentence continuation and over-merge unrelated
    index lines. Excluding them is the conservative choice (under-merge is safer
    than over-merge); a handful of running-prose lines mis-tagged ``toc_entry``
    therefore stay split rather than risk fusing a real index.

    A unit that begins with an *explicit* bullet/number marker is also excluded:
    a genuine list item legitimately ends without terminal punctuation, so the
    following lowercase line may be a separate item rather than a wrapped
    continuation. That case is geometry-sensitive and already owned by the
    span-level list-continuation merge; re-deciding it here (without geometry)
    would risk fusing two distinct list items, so we leave marker-led units to
    that pass. Mis-clustered running prose (no explicit marker) still leads."""
    if unit.structural_role == "toc_entry":
        return False
    if _unit_is_standalone_footnote_marker(unit):
        return False
    head_text = (unit.text or "").strip()
    if _BULLET_PATTERN.match(head_text) or _ORDERED_LIST_PATTERN.match(head_text):
        return False
    return bool(head_text)


def _unit_can_continue_run(unit: ParagraphUnit) -> bool:
    """A unit that may be appended as a soft-wrap continuation.

    The continuation half must not be a real TOC / index entry nor a standalone
    footnote marker (handled inline separately)."""
    if unit.structural_role == "toc_entry":
        return False
    if _unit_is_standalone_footnote_marker(unit):
        return False
    return bool((unit.text or "").strip())


def _merge_continuation_units(units: list[ParagraphUnit], *, inline_markers: list[str]) -> ParagraphUnit:
    """Fuse a run of prose units (Rule 2) into a single body unit.

    ``inline_markers`` are footnote-marker texts that sat between halves of the
    fused sentence (Rule 1); they are spliced back inline at their original
    position so the marker survives without breaking the paragraph flow.
    """
    parts: list[str] = []
    for index, unit in enumerate(units):
        parts.append((unit.text or "").strip())
        if index < len(inline_markers) and inline_markers[index]:
            parts[-1] = f"{parts[-1]} {inline_markers[index]}".strip()
    text = " ".join(part for part in parts if part)
    origin_indexes: list[int] = []
    origin_texts: list[str] = []
    for unit in units:
        origin_indexes.extend(unit.origin_raw_indexes or [])
        origin_texts.extend(unit.origin_raw_texts or [])
    first = units[0]
    return ParagraphUnit(
        text=text,
        role="body",
        structural_role="body",
        role_confidence="heuristic",
        style_name="PDF Body",
        is_bold=all(unit.is_bold for unit in units),
        is_italic=all(unit.is_italic for unit in units),
        font_size_pt=first.font_size_pt,
        origin_raw_indexes=origin_indexes,
        origin_raw_texts=origin_texts,
        layout_origin="pdf_text_layer",
        boundary_source="pdf_text_layer",
        boundary_confidence="heuristic",
        boundary_rationale="merged_cross_role_soft_wrap_continuation",
        source_index=first.source_index,
        page_number=first.page_number,
    )


def _consolidate_cross_role_continuations(
    units: list[ParagraphUnit],
) -> list[ParagraphUnit]:
    """Rules 1 & 2: merge soft-wrap continuations across role boundaries.

    Walking the emitted units, whenever a unit's text does not end a sentence and
    the next prose unit continues it lowercase, the pair is a soft-wrap that the
    importer split because the two halves received different roles (body / list /
    caption / heading). They are fused into one body unit. A standalone footnote
    marker between the two halves is transparent: prose merges across it and the
    marker is kept inline (Rule 1), so it no longer survives as a barrier digit
    paragraph. This never fuses a genuine boundary, because a real heading / list
    item / caption never *ends* without terminal punctuation followed by a
    lowercase continuation.
    """
    if not units:
        return units
    result: list[ParagraphUnit] = []
    index = 0
    count = len(units)
    while index < count:
        current = units[index]
        if not _unit_can_lead_continuation(current):
            result.append(current)
            index += 1
            continue
        run = [current]
        inline_markers: list[str] = []
        cursor = index
        merged_any = False
        while True:
            # Look ahead past an optional standalone footnote marker.
            marker_text = ""
            lookahead = cursor + 1
            if (
                lookahead < count
                and _unit_is_standalone_footnote_marker(units[lookahead])
                and lookahead + 1 < count
            ):
                marker_text = (units[lookahead].text or "").strip()
                next_index = lookahead + 1
            else:
                next_index = cursor + 1
            if next_index >= count:
                break
            nxt = units[next_index]
            if not _unit_can_continue_run(nxt):
                break
            if not _is_soft_wrap_continuation_pair(
                (run[-1].text or "").strip(), (nxt.text or "").strip()
            ):
                break
            inline_markers.append(marker_text)
            run.append(nxt)
            cursor = next_index
            merged_any = True
        if merged_any:
            result.append(_merge_continuation_units(run, inline_markers=inline_markers))
            index = cursor + 1
        else:
            result.append(current)
            index += 1
    return result


def _classify_span_role(
    span: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    previous_span: PdfTextSpan | None,
    next_span: PdfTextSpan | None,
) -> str:
    text = _normalize_text(span.text)
    if _BULLET_PATTERN.match(text) or _ORDERED_LIST_PATTERN.match(text):
        # Rule 3: a standalone ``N. Title`` line with heading typography that is not
        # part of a consecutive numbered run is a numbered section heading, not a
        # bullet/list item. Real ordered/bullet lists fall through to "list".
        if _looks_like_numbered_section_heading(
            span,
            layout_profile=layout_profile,
            previous_span=previous_span,
            next_span=next_span,
        ):
            return "heading"
        return "list"
    if _looks_like_superscript_footnote_marker(
        span,
        previous_span=previous_span,
        next_span=next_span,
        layout_profile=layout_profile,
    ):
        return "footnote"
    if _looks_like_caption(span):
        return "caption"
    soft_wrap_continuation = (
        previous_span is not None
        and previous_span.page_number == span.page_number
        and _is_soft_wrap_continuation_pair(_normalize_text(previous_span.text), text)
    )
    if not soft_wrap_continuation and _looks_like_chapter_heading(span):
        # Deterministic "Chapter <roman/number>" promotion runs before the TOC and
        # heading-typography passes: a bare "Chapter VI" number line otherwise looks
        # like a TOC entry (roman read as a page ref) and a body-sized chapter line
        # otherwise fails the typography test. A real TOC chapter row (trailing page
        # reference) is excluded inside _looks_like_chapter_heading.
        return "heading"
    if not soft_wrap_continuation and _looks_like_toc_entry(span):
        return "toc_entry"
    if _looks_like_digit_only_small_span(span, layout_profile=layout_profile):
        return "body"
    if _looks_like_non_heading_front_matter_line(span):
        return "body"
    if soft_wrap_continuation:
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
) -> _PdfHeadingLayoutProfile:
    sentence_font_sizes = [
        float(span.font_size)
        for span in spans
        if isinstance(span.font_size, (int, float))
        and span.font_size > 0
        and _span_furniture_key(span) not in repeated_furniture_keys
        and not _looks_like_page_number(span)
        and _normalize_text(span.text).rstrip().endswith((".", "!", "?"))
        and len(_words(_normalize_text(span.text))) >= 2
    ]
    font_sizes = [
        float(span.font_size)
        for span in spans
        if isinstance(span.font_size, (int, float))
        and span.font_size > 0
        and _span_furniture_key(span) not in repeated_furniture_keys
        and not _looks_like_page_number(span)
    ]
    body_font_size = _mode_font_size(sentence_font_sizes) or _mode_font_size(font_sizes)
    body_left_candidates: list[float] = []
    body_right_candidates: list[float] = []
    body_line_lengths: list[int] = []
    body_case_candidates: list[tuple[float, float]] = []
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
        if body_font_size and span.font_size:
            ratio = float(span.font_size) / body_font_size
            if ratio < 0.75 or ratio > 1.25:
                continue
        body_left_candidates.append(float(span.x0))
        body_right_candidates.append(float(span.x1))
        body_line_lengths.append(len(text))
        body_case_candidates.append((_uppercase_ratio(text), _title_word_ratio(words)))
    body_left_x0 = float(median(body_left_candidates)) if body_left_candidates else None
    body_right_x1 = _percentile(body_right_candidates, 0.85) if body_right_candidates else None
    body_line_length_p75 = _percentile(body_line_lengths, 0.75)
    body_line_length_p90 = _percentile(body_line_lengths, 0.90)
    body_leading = _estimate_body_leading(
        spans,
        repeated_furniture_keys=repeated_furniture_keys,
        body_font_size=body_font_size,
    )
    body_uppercase_ratio = (
        float(median([item[0] for item in body_case_candidates])) if body_case_candidates else 0.0
    )
    body_title_word_ratio = (
        float(median([item[1] for item in body_case_candidates])) if body_case_candidates else 0.0
    )
    base_profile = _PdfHeadingLayoutProfile(
        body_font_size=body_font_size,
        body_left_x0=body_left_x0,
        body_right_x1=body_right_x1,
        body_leading=body_leading,
        body_line_length_p75=body_line_length_p75,
        body_line_length_p90=body_line_length_p90,
        body_uppercase_ratio=body_uppercase_ratio,
        body_title_word_ratio=body_title_word_ratio,
    )
    repeated_display_text_keys = _detect_repeated_display_text_keys(spans)
    signatures: list[_PdfStyleSignature] = []
    for index, span in enumerate(spans):
        if not _is_style_cluster_input(span, repeated_furniture_keys=repeated_furniture_keys):
            continue
        signatures.append(
            _style_signature(
                span,
                layout_profile=base_profile,
                previous_span=_nearest_content_span(
                    spans,
                    index,
                    direction=-1,
                    repeated_furniture_keys=repeated_furniture_keys,
                ),
                next_span=_nearest_content_span(
                    spans,
                    index,
                    direction=1,
                    repeated_furniture_keys=repeated_furniture_keys,
                ),
            )
        )
    clusters = _cluster_style_signatures(signatures)
    heading_prominence_threshold = _otsu_prominence_threshold(
        [signature.prominence for signature in signatures]
    )
    heading_cluster_ids, ambiguous_cluster_ids = _select_heading_clusters(
        clusters,
        signatures,
        heading_prominence_threshold=heading_prominence_threshold,
    )
    return _PdfHeadingLayoutProfile(
        body_font_size=body_font_size,
        body_left_x0=body_left_x0,
        body_right_x1=body_right_x1,
        body_leading=body_leading,
        body_line_length_p75=body_line_length_p75,
        body_line_length_p90=body_line_length_p90,
        body_uppercase_ratio=body_uppercase_ratio,
        body_title_word_ratio=body_title_word_ratio,
        clusters=clusters,
        heading_cluster_ids=heading_cluster_ids,
        ambiguous_cluster_ids=ambiguous_cluster_ids,
        repeated_display_text_keys=repeated_display_text_keys,
        heading_prominence_threshold=heading_prominence_threshold,
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


def _mode_font_size(font_sizes: list[float]) -> float | None:
    if not font_sizes:
        return None
    buckets: dict[float, int] = {}
    for font_size in font_sizes:
        bucket = round(float(font_size) * 2.0) / 2.0
        buckets[bucket] = buckets.get(bucket, 0) + 1
    return max(buckets.items(), key=lambda item: (item[1], -abs(item[0])))[0]


def _percentile(values: list[int] | list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, round(percentile * (len(ordered) - 1))))
    return ordered[index]


def _estimate_body_leading(
    spans: list[PdfTextSpan],
    *,
    repeated_furniture_keys: set[tuple[str, str]],
    body_font_size: float | None,
) -> float | None:
    deltas: list[float] = []
    previous: PdfTextSpan | None = None
    for span in spans:
        text = _normalize_text(span.text)
        if not text or len(_words(text)) < 6:
            continue
        if _span_furniture_key(span) in repeated_furniture_keys:
            continue
        if _looks_like_page_number(span) or _looks_like_toc_entry(span) or _looks_like_caption(span):
            continue
        if body_font_size and span.font_size:
            ratio = float(span.font_size) / body_font_size
            if ratio < 0.8 or ratio > 1.2:
                continue
        if previous is not None and previous.page_number == span.page_number:
            delta = float(span.top) - float(previous.top)
            if delta > 0:
                deltas.append(delta)
        previous = span
    if deltas:
        return float(median(deltas))
    return body_font_size * 1.2 if body_font_size else None


def _is_style_cluster_input(
    span: PdfTextSpan,
    *,
    repeated_furniture_keys: set[tuple[str, str]],
) -> bool:
    text = _normalize_text(span.text)
    if not text:
        return False
    if _span_furniture_key(span) in repeated_furniture_keys:
        return False
    if _looks_like_page_number(span) or _looks_like_blank_page_notice(span):
        return False
    if _BULLET_PATTERN.match(text) or _ORDERED_LIST_PATTERN.match(text):
        return False
    if _looks_like_toc_entry(span) or _looks_like_caption(span):
        return False
    if _looks_like_non_heading_front_matter_line(span):
        return False
    return True


def _detect_repeated_display_text_keys(spans: list[PdfTextSpan]) -> frozenset[str]:
    counts: dict[str, int] = {}
    for span in spans:
        text = _normalize_text(span.text)
        if not text or len(text) > 45:
            continue
        words = _words(text)
        if not words or len(words) > 6:
            continue
        if _has_terminal_sentence_punctuation(text):
            continue
        key = _display_text_key(text)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return frozenset(key for key, count in counts.items() if count >= 3)


def _display_text_key(text: str) -> str:
    key = re.sub(r"[^\w\s]", " ", _normalize_text(text).lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", key).strip()


def _style_signature(
    span: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    previous_span: PdfTextSpan | None,
    next_span: PdfTextSpan | None,
) -> _PdfStyleSignature:
    text = _normalize_text(span.text)
    words = _words(text)
    word_count = max(1, len(words))
    body_font_size = layout_profile.body_font_size or span.font_size or 10.0
    font_ratio = float(span.font_size or body_font_size) / float(body_font_size)
    font_up = max(0.0, min(2.5, font_ratio - 1.0))
    font_down = max(0.0, min(1.0, 1.0 - font_ratio))
    body_leading = layout_profile.body_leading or body_font_size * 1.2
    indent_units = 0.0
    if layout_profile.body_left_x0 is not None:
        indent_units = max(0.0, min(4.0, (float(span.x0) - layout_profile.body_left_x0) / body_leading))
    previous_gap = 0.0
    next_gap = 0.0
    if previous_span is not None and previous_span.page_number == span.page_number:
        previous_gap = max(0.0, float(span.top) - float(previous_span.bottom))
    if next_span is not None and next_span.page_number == span.page_number:
        next_gap = max(0.0, float(next_span.top) - float(span.bottom))
    isolation_units = max(0.0, min(4.0, (previous_gap + next_gap) / body_leading))
    uppercase_ratio = _uppercase_ratio(text)
    title_word_ratio = _title_word_ratio(words)
    uppercase_delta = max(0.0, uppercase_ratio - layout_profile.body_uppercase_ratio)
    title_delta = max(0.0, title_word_ratio - layout_profile.body_title_word_ratio)
    shortness = max(0.0, 1.0 - min(word_count, 14) / 14.0)
    boundary_context = _boundary_context_score(span, previous_span=previous_span, next_span=next_span)
    bold = 1.0 if span.is_bold else 0.0
    italic = 1.0 if span.is_italic else 0.0
    vector = (
        font_up,
        font_down,
        indent_units,
        isolation_units,
        uppercase_delta,
        title_delta,
        shortness,
        bold,
        italic,
        boundary_context,
    )
    prominence = (
        font_up * 2.0
        + font_down * 0.7
        + indent_units * 0.7
        + isolation_units * 0.8
        + uppercase_delta * 1.2
        + title_delta * 0.7
        + shortness * 0.7
        + bold * 0.8
        + italic * 0.3
        + boundary_context * 0.8
    )
    return _PdfStyleSignature(
        vector=vector,
        prominence=prominence,
        font_ratio=font_ratio,
        indent_units=indent_units,
        isolation_units=isolation_units,
        uppercase_delta=uppercase_delta,
        title_delta=title_delta,
        shortness=shortness,
        boundary_context=boundary_context,
    )


def _boundary_context_score(
    span: PdfTextSpan,
    *,
    previous_span: PdfTextSpan | None,
    next_span: PdfTextSpan | None,
) -> float:
    if next_span is None or next_span.page_number != span.page_number:
        return 0.0
    next_text = _normalize_text(next_span.text)
    if len(_words(next_text)) < 4:
        return 0.0
    if _BULLET_PATTERN.match(next_text) or _ORDERED_LIST_PATTERN.match(next_text):
        return 0.0
    if previous_span is None or previous_span.page_number != span.page_number:
        return 0.5
    previous_text = _normalize_text(previous_span.text)
    if previous_text and previous_text[-1] in _TERMINAL_SENTENCE_PUNCTUATION:
        return 1.0
    return 0.0


def _cluster_style_signatures(
    signatures: list[_PdfStyleSignature],
) -> tuple[_PdfStyleCluster, ...]:
    if not signatures:
        return ()
    cluster_count = min(6, len(signatures), max(3, int(len(signatures) ** 0.5 // 8) + 2))
    ordered = sorted(signatures, key=lambda item: item.prominence)
    centers = [
        ordered[min(len(ordered) - 1, round(index * (len(ordered) - 1) / max(1, cluster_count - 1)))].vector
        for index in range(cluster_count)
    ]
    assignments = [0] * len(signatures)
    for _ in range(20):
        changed = False
        for index, signature in enumerate(signatures):
            cluster_id = _nearest_center_id(signature.vector, centers)
            if assignments[index] != cluster_id:
                assignments[index] = cluster_id
                changed = True
        new_centers: list[tuple[float, ...]] = []
        for cluster_id in range(cluster_count):
            vectors = [
                signature.vector
                for signature, assignment in zip(signatures, assignments)
                if assignment == cluster_id
            ]
            if not vectors:
                new_centers.append(centers[cluster_id])
                continue
            new_centers.append(
                tuple(sum(vector[item] for vector in vectors) / len(vectors) for item in range(len(vectors[0])))
            )
        centers = new_centers
        if not changed:
            break
    clusters: list[_PdfStyleCluster] = []
    for cluster_id, center in enumerate(centers):
        members = [
            signature
            for signature, assignment in zip(signatures, assignments)
            if assignment == cluster_id
        ]
        if not members:
            continue
        clusters.append(
            _PdfStyleCluster(
                cluster_id=cluster_id,
                size=len(members),
                center=center,
                prominence=float(median([member.prominence for member in members])),
            )
        )
    return tuple(clusters)


def _nearest_center_id(vector: tuple[float, ...], centers: list[tuple[float, ...]]) -> int:
    return min(
        range(len(centers)),
        key=lambda index: sum((vector[item] - centers[index][item]) ** 2 for item in range(len(vector))),
    )


def _select_heading_clusters(
    clusters: tuple[_PdfStyleCluster, ...],
    signatures: list[_PdfStyleSignature],
    *,
    heading_prominence_threshold: float,
) -> tuple[frozenset[int], frozenset[int]]:
    if not clusters or not signatures:
        return frozenset(), frozenset()
    body_cluster_id = min(clusters, key=lambda cluster: (cluster.prominence, -cluster.size)).cluster_id
    max_heading_cluster_size = max(75, int(len(signatures) * 0.12))
    heading_ids: set[int] = set()
    ambiguous_ids: set[int] = set()
    for cluster in clusters:
        if cluster.cluster_id == body_cluster_id:
            continue
        if _looks_like_display_noise_cluster(cluster):
            continue
        if cluster.size > max_heading_cluster_size:
            continue
        if cluster.prominence < heading_prominence_threshold:
            continue
        heading_ids.add(cluster.cluster_id)
        if _cluster_is_ambiguous_caps_or_short_label(cluster):
            ambiguous_ids.add(cluster.cluster_id)
    return frozenset(heading_ids), frozenset(ambiguous_ids)


def _otsu_prominence_threshold(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) < 3:
        return ordered[-1]
    total_sum = sum(ordered)
    total_count = len(ordered)
    best_index = 0
    best_variance = -1.0
    left_sum = 0.0
    for index, value in enumerate(ordered[:-1], start=1):
        left_sum += value
        right_count = total_count - index
        if right_count <= 0:
            break
        left_mean = left_sum / index
        right_mean = (total_sum - left_sum) / right_count
        variance = index * right_count * (left_mean - right_mean) ** 2
        if variance > best_variance:
            best_variance = variance
            best_index = index
    return (ordered[best_index - 1] + ordered[best_index]) / 2.0


def _cluster_is_ambiguous_caps_or_short_label(cluster: _PdfStyleCluster) -> bool:
    center = cluster.center
    font_up, font_down, indent_units, isolation_units, uppercase_delta, title_delta, shortness = center[:7]
    has_typographic_separation = font_up > 0.2 or font_down > 0.2 or indent_units > 1.0 or isolation_units > 0.8
    is_short_case_only = shortness > 0.7 and (uppercase_delta > 0.5 or title_delta > 0.5)
    return is_short_case_only and not has_typographic_separation


def _looks_like_display_noise_cluster(cluster: _PdfStyleCluster) -> bool:
    center = cluster.center
    indent_units = center[2]
    boundary_context = center[9]
    return cluster.size > 150 and indent_units > 3.0 and boundary_context < 0.2


def _nearest_style_cluster(
    signature: _PdfStyleSignature,
    clusters: tuple[_PdfStyleCluster, ...],
) -> _PdfStyleCluster | None:
    if not clusters:
        return None
    return min(
        clusters,
        key=lambda cluster: sum(
            (signature.vector[item] - cluster.center[item]) ** 2
            for item in range(len(signature.vector))
        ),
    )


def _ambiguous_signature_has_structural_support(signature: _PdfStyleSignature) -> bool:
    if signature.font_ratio >= 1.12 or signature.font_ratio <= 0.82:
        return True
    if signature.indent_units >= 1.0:
        return True
    if signature.isolation_units >= 0.8:
        return True
    if signature.boundary_context >= 1.0 and signature.title_delta >= 0.5:
        return True
    return False


def _signature_has_heading_support(signature: _PdfStyleSignature) -> bool:
    if signature.font_ratio >= 1.12 or signature.font_ratio <= 0.82:
        return True
    if signature.isolation_units >= 0.8 and (
        signature.uppercase_delta >= 0.45 or signature.title_delta >= 0.45
    ):
        return True
    if signature.indent_units >= 1.0 and (signature.uppercase_delta >= 0.45 or signature.title_delta >= 0.45):
        return True
    if signature.boundary_context >= 1.0 and signature.title_delta >= 0.45 and signature.shortness >= 0.55:
        return True
    if signature.boundary_context >= 1.0 and signature.uppercase_delta >= 0.55:
        return True
    return False


def _violates_heading_sanity_invariants(
    span: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    previous_span: PdfTextSpan | None,
) -> bool:
    text = _normalize_text(span.text)
    if not text:
        return True
    if _is_longer_than_document_body_line_tail(span, text, layout_profile):
        return True
    if _starts_like_sentence_continuation(text):
        return True
    if _display_text_key(text) in layout_profile.repeated_display_text_keys:
        return True
    if _continues_previous_sentence(span, previous_span=previous_span, layout_profile=layout_profile):
        return True
    if _EPIGRAPH_CREDIT_PATTERN.match(text) or _EPIGRAPH_SOURCE_CREDIT_PATTERN.match(text):
        return True
    if _looks_like_footnote_or_citation_tail(text):
        return True
    return False


def _is_longer_than_document_body_line_tail(
    span: PdfTextSpan,
    text: str,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    if layout_profile.body_line_length_p90 <= 0:
        return False
    if layout_profile.body_font_size and span.font_size:
        font_ratio = float(span.font_size) / layout_profile.body_font_size
        if font_ratio > 1.12:
            return False
        if 0.9 <= font_ratio <= 1.1 and layout_profile.body_line_length_p75 > 0:
            return len(text) > layout_profile.body_line_length_p75
    return len(text) > layout_profile.body_line_length_p90


def _starts_like_sentence_continuation(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return True
    first = stripped[0]
    if first.islower():
        return True
    if first in ",.;:)]}»”":
        return True
    if first in "-–—" and not _DASH_ATTRIBUTION_PATTERN.match(stripped):
        return True
    return False


def _continues_previous_sentence(
    span: PdfTextSpan,
    *,
    previous_span: PdfTextSpan | None,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    if previous_span is None or previous_span.page_number != span.page_number:
        return False
    previous_text = _normalize_text(previous_span.text)
    if not previous_text or previous_text[-1] in _TERMINAL_SENTENCE_PUNCTUATION:
        return False
    current_text = _normalize_text(span.text)
    if _looks_like_consecutive_heading_style_lines(
        current_text,
        previous_text,
        span=span,
        previous_span=previous_span,
        layout_profile=layout_profile,
    ):
        return False
    if layout_profile.body_left_x0 is None:
        return False
    body_leading = layout_profile.body_leading or layout_profile.body_font_size or 10.0
    current_x0 = float(span.x0)
    previous_x0 = float(previous_span.x0)
    near_body_left = abs(current_x0 - layout_profile.body_left_x0) <= body_leading * 0.75
    near_previous_left = abs(current_x0 - previous_x0) <= body_leading * 0.75
    return near_body_left or near_previous_left


def _looks_like_consecutive_heading_style_lines(
    current_text: str,
    previous_text: str,
    *,
    span: PdfTextSpan,
    previous_span: PdfTextSpan,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    current_words = _words(current_text)
    previous_words = _words(previous_text)
    if len(current_words) > 8 or len(previous_words) > 8:
        return False
    current_case = _uppercase_ratio(current_text) >= 0.65 or _title_word_ratio(current_words) >= 0.75
    previous_case = _uppercase_ratio(previous_text) >= 0.65 or _title_word_ratio(previous_words) >= 0.75
    if not (current_case and previous_case):
        return False
    if layout_profile.body_font_size and span.font_size and previous_span.font_size:
        current_ratio = float(span.font_size) / layout_profile.body_font_size
        previous_ratio = float(previous_span.font_size) / layout_profile.body_font_size
        return current_ratio >= 1.08 or previous_ratio >= 1.08
    return True


def _looks_like_footnote_or_citation_tail(text: str) -> bool:
    if _FOOTNOTE_OR_CITATION_TAIL_PATTERN.search(text):
        return True
    if re.search(r"\b(?:18|19|20)\d{2}\d{1,2}\b", text):
        return True
    if re.search(r"\b(?:18|19|20)\d{2}\b", text) and (
        "," in text or "(" in text or ")" in text or ":" in text or len(_words(text)) <= 8
    ):
        return True
    if re.search(r"\b\d{1,3}\)\s*$", text):
        return True
    return False


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
    if _violates_heading_sanity_invariants(
        span,
        layout_profile=layout_profile,
        previous_span=previous_span,
    ):
        return False
    signature = _style_signature(
        span,
        layout_profile=layout_profile,
        previous_span=previous_span,
        next_span=next_span,
    )
    cluster = _nearest_style_cluster(signature, layout_profile.clusters)
    if cluster is None or cluster.cluster_id not in layout_profile.heading_cluster_ids:
        return (
            signature.prominence >= layout_profile.heading_prominence_threshold
            and _signature_has_heading_support(signature)
        )
    if not _signature_has_heading_support(signature):
        return False
    if cluster.cluster_id in layout_profile.ambiguous_cluster_ids:
        return _ambiguous_signature_has_structural_support(signature)
    return True


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


_NUMBERED_SECTION_HEADING_PATTERN = re.compile(r"^(?P<number>\d{1,3})\.\s+(?P<title>[A-ZА-Я].*)$")

# A chapter heading line: the latin word "Chapter" followed by a roman numeral or
# an arabic number, either standing alone ("Chapter VI") or carrying an inline
# title after a dash/colon ("Chapter I — Why this report, now?"). Source PDFs are
# English on import, so only the latin spelling is matched. Roman numerals are
# restricted to a sane chapter range (I…XXXIX worth of letters) and uppercase to
# avoid matching prose words; the title tail, when present, must be introduced by
# a dash or colon (never by a bare space, which would swallow running prose that
# merely begins with the word "Chapter").
_CHAPTER_HEADING_PATTERN = re.compile(
    r"^chapter\s+(?:[IVXLC]{1,7}|\d{1,3})"
    r"(?:\s*[–—:.\-]\s*\S.*)?$",
    re.IGNORECASE,
)
# The standalone "Chapter <roman/number>" number line with nothing after it. Such
# a line is the chapter number itself, never a TOC entry (the trailing roman/arabic
# IS the chapter number, not a page reference following a title).
_CHAPTER_NUMBER_ONLY_PATTERN = re.compile(
    r"^chapter\s+(?:[IVXLC]{1,7}|\d{1,3})$",
    re.IGNORECASE,
)


def _looks_like_chapter_heading(span: PdfTextSpan) -> bool:
    """Detect a deterministic ``Chapter <roman/number>`` heading line.

    Promotes a standalone ``Chapter VI`` number line or a ``Chapter I — Title``
    line to a heading. This is the one signal the LLM structure-recognition stage
    contributed that the importer's numbered-section detector (``N. Title``) did
    not already cover, so it is folded in deterministically here.

    Guards (anti over-promote):
    * Only a line that *begins* with the latin word ``Chapter`` (sources are
      English on import) followed immediately by a roman numeral or arabic number
      qualifies — a mid-sentence mention ("…in chapter 3 we saw…") never starts
      with ``Chapter`` + number, so it is never matched.
    * A title tail is accepted only when introduced by a dash or colon, never by a
      bare space, so a body line that merely opens with the word ``Chapter`` does
      not get swallowed.
    * The caller invokes this AFTER the TOC and soft-wrap-continuation guards, so
      ``Chapter II … 45`` TOC lines (matched by the trailing-page pattern) and
      sentence continuations are passed through untouched.
    """
    text = _normalize_text(span.text)
    if not text:
        return False
    # A TOC entry ("Chapter II .......... 45" / "Chapter VI: Title ... 88") ends
    # with a page reference and is owned by the TOC pass — never promote it. A bare
    # number line ("Chapter VI") is NOT a TOC entry (no real title precedes the
    # roman, the trailing token IS the chapter number), so it falls through here.
    if _looks_like_toc_entry(span) and not _CHAPTER_NUMBER_ONLY_PATTERN.match(text):
        return False
    if _CHAPTER_HEADING_PATTERN.match(text) is None:
        return False
    # A real chapter heading is short; reject an over-long line that happens to
    # open "Chapter N —" but then runs on like body prose.
    return len(_words(text)) <= 14


def _numbered_line_number(text: str) -> int | None:
    match = _ORDERED_LIST_PATTERN.match(text)
    if not match:
        return None
    try:
        return int(match.group("marker"))
    except (TypeError, ValueError):
        return None


def _is_consecutive_numbered_sibling(
    span: PdfTextSpan,
    neighbour: PdfTextSpan | None,
    *,
    own_number: int,
) -> bool:
    """True when ``neighbour`` is part of the same ordered-list run as ``span``.

    A genuine ordered list reads as ``1.``, ``2.``, ``3.`` … in sequence at the
    same type size. We detect membership by an adjacent ordered-list line whose
    number differs by exactly one and whose font size matches, so a numbered
    *section heading* (isolated, surrounded by body prose) is never mistaken for
    a list item and vice-versa.
    """
    if neighbour is None or neighbour.page_number != span.page_number:
        return False
    neighbour_number = _numbered_line_number(_normalize_text(neighbour.text))
    if neighbour_number is None:
        return False
    if abs(neighbour_number - own_number) != 1:
        return False
    span_font = span.font_size if isinstance(span.font_size, (int, float)) else None
    neighbour_font = neighbour.font_size if isinstance(neighbour.font_size, (int, float)) else None
    if span_font and neighbour_font:
        smaller = min(float(span_font), float(neighbour_font))
        larger = max(float(span_font), float(neighbour_font))
        if larger - smaller > max(0.5, smaller * 0.1):
            return False
    return True


def _looks_like_numbered_section_heading(
    span: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    previous_span: PdfTextSpan | None,
    next_span: PdfTextSpan | None,
) -> bool:
    """Distinguish a numbered *section heading* (``N. Title``) from a list item.

    Promotion is deliberately conservative (under-promotion is safer than
    over-promotion): a ``N. Title`` line becomes a heading ONLY when it carries
    genuine heading typography (prominent font relative to body) AND it is not
    part of a consecutive numbered run (a real ordered list). Body-sized numbered
    lines (e.g. lietaer sub-points styled at body size) and TOC chapter runs
    (mazzucato ``1.``…``9.`` sequences) therefore stay classified as list items.
    """
    text = _normalize_text(span.text)
    match = _NUMBERED_SECTION_HEADING_PATTERN.match(text)
    if not match:
        return False
    own_number = int(match.group("number"))
    title = match.group("title")
    title_words = _words(title)
    # Heading-shaped: short title, no terminal sentence punctuation on a long line,
    # not a footnote/citation tail glued to a number.
    if not title_words or len(title_words) > 16:
        return False
    if _looks_like_footnote_or_citation_tail(text):
        return False
    # A numbered section heading begins a section; the line after it is body prose
    # (or another heading), never the next item of the same numbered run.
    if _is_consecutive_numbered_sibling(span, previous_span, own_number=own_number):
        return False
    if _is_consecutive_numbered_sibling(span, next_span, own_number=own_number):
        return False
    # Require genuine heading typography: a prominent font relative to body. This
    # is the signal that separates Money's real 16.5pt section headings from the
    # body-sized numbered lines in other books (which must stay lists).
    body_font_size = layout_profile.body_font_size
    span_font_size = span.font_size if isinstance(span.font_size, (int, float)) else None
    if not body_font_size or not span_font_size:
        return False
    if float(span_font_size) / float(body_font_size) < 1.12:
        return False
    # A real heading is not as long as a wrapped body line.
    if _is_longer_than_document_body_line_tail(span, text, layout_profile):
        return False
    return True


def _is_soft_wrap_continuation_pair(previous_text: str, current_text: str) -> bool:
    """Return True when the textual signal unambiguously marks a soft line wrap.

    A soft wrap is when the previous line did *not* end a sentence (no terminal
    punctuation) and the current line continues it (starts lowercase or with a
    connecting/closing character). Real paragraph, heading and list-item starts
    begin with an uppercase letter, an opening quote, a bullet or a number, so
    this signal never fuses a genuine boundary. It is geometry-independent on
    purpose: epub→pdf exports indent soft-wrapped continuations (hanging list
    indents, justified word-group splits), which fools purely indent-based
    boundary heuristics.
    """
    if not previous_text or not current_text:
        return False
    if previous_text[-1] in _TERMINAL_SENTENCE_PUNCTUATION:
        return False
    if _BULLET_PATTERN.match(current_text) or _ORDERED_LIST_PATTERN.match(current_text):
        return False
    return _starts_like_sentence_continuation(current_text)


def _can_merge_body_span(
    previous: PdfTextSpan,
    current: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    previous_text = _normalize_text(previous.text)
    current_text = _normalize_text(current.text)
    soft_wrap = _is_soft_wrap_continuation_pair(previous_text, current_text)
    if not soft_wrap and (_looks_like_toc_entry(previous) or _looks_like_toc_entry(current)):
        # A confirmed soft-wrap continuation (non-terminal previous line + lowercase
        # start) is structurally incompatible with a real TOC entry, so it overrides
        # a spurious TOC classification of running body prose.
        return False
    if previous.page_number != current.page_number:
        # The only safe cross-page merge is a confirmed soft-wrap continuation:
        # the previous page's last line did not finish a sentence and the next
        # page's first line continues it lowercase. Page-relative geometry is not
        # comparable across pages, so we rely solely on the textual signal here.
        return soft_wrap
    if not soft_wrap and _looks_like_body_paragraph_indent_boundary(
        previous, current, layout_profile=layout_profile
    ):
        return False
    previous_font_size = previous.font_size if isinstance(previous.font_size, (int, float)) else 10.0
    current_font_size = current.font_size if isinstance(current.font_size, (int, float)) else previous_font_size
    vertical_gap = max(0.0, float(current.top) - float(previous.bottom))
    body_leading = layout_profile.body_leading or min(previous_font_size, current_font_size) * 1.2
    max_gap = min(body_leading * 0.55, min(previous_font_size, current_font_size) * 1.25)
    if soft_wrap:
        # A confirmed soft-wrap continuation is a full text line, so allow up to a
        # single body line of leading between the two lines (still rejecting the
        # large block gaps that separate paragraphs).
        max_gap = max(max_gap, body_leading * 1.1)
    if vertical_gap > max_gap:
        return False
    if (
        previous_text
        and current_text
        and previous_text[-1] in _TERMINAL_SENTENCE_PUNCTUATION
        and _starts_like_new_body_sentence(current_text)
        and _span_line_fill_ratio(previous, layout_profile) < 0.72
        and _is_near_body_left(current, layout_profile)
    ):
        return False
    return True


def _looks_like_body_paragraph_indent_boundary(
    previous: PdfTextSpan,
    current: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    previous_text = _normalize_text(previous.text)
    current_text = _normalize_text(current.text)
    if not previous_text or not current_text:
        return False
    previous_x0 = float(previous.x0)
    current_x0 = float(current.x0)
    indent_delta = current_x0 - previous_x0
    body_leading = layout_profile.body_leading or layout_profile.body_font_size or 10.0
    if indent_delta >= body_leading * 0.45:
        return True
    if layout_profile.body_left_x0 is None or not _is_near_body_left(current, layout_profile):
        return False
    if previous_text[-1] not in _TERMINAL_SENTENCE_PUNCTUATION:
        return False
    first_char = current_text[0]
    return first_char in _OPENING_TEXT_BOUNDARY_CHARS or first_char.isupper()


def _starts_like_new_body_sentence(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    first_char = stripped[0]
    return first_char in _OPENING_TEXT_BOUNDARY_CHARS or first_char.isupper()


def _is_near_body_left(span: PdfTextSpan, layout_profile: _PdfHeadingLayoutProfile) -> bool:
    if layout_profile.body_left_x0 is None:
        return False
    body_leading = layout_profile.body_leading or layout_profile.body_font_size or 10.0
    return abs(float(span.x0) - layout_profile.body_left_x0) <= body_leading * 0.75


def _span_line_fill_ratio(span: PdfTextSpan, layout_profile: _PdfHeadingLayoutProfile) -> float:
    if layout_profile.body_left_x0 is not None and layout_profile.body_right_x1 is not None:
        body_width = max(1.0, layout_profile.body_right_x1 - layout_profile.body_left_x0)
        return max(0.0, min(1.25, (float(span.x1) - layout_profile.body_left_x0) / body_width))
    if layout_profile.body_line_length_p75 > 0:
        return max(0.0, min(1.25, len(_normalize_text(span.text)) / layout_profile.body_line_length_p75))
    return 1.0


def _can_merge_list_continuation_span(
    previous: PdfTextSpan,
    current: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    current_text = _normalize_text(current.text)
    if not current_text or _BULLET_PATTERN.match(current_text) or _ORDERED_LIST_PATTERN.match(current_text):
        return False
    if _looks_like_superscript_footnote_marker(
        current,
        previous_span=previous,
        layout_profile=layout_profile,
    ):
        return False
    previous_font_size = previous.font_size if isinstance(previous.font_size, (int, float)) else 10.0
    current_font_size = current.font_size if isinstance(current.font_size, (int, float)) else previous_font_size
    body_leading = layout_profile.body_leading or min(previous_font_size, current_font_size) * 1.2
    previous_text = _normalize_text(previous.text)
    soft_wrap = _is_soft_wrap_continuation_pair(previous_text, current_text)
    if previous.page_number != current.page_number:
        # A list item can wrap across a page break. As with body merges, the only
        # safe cross-page join is a confirmed soft-wrap continuation: the last
        # line of the item on the previous page did not finish a sentence and the
        # next page continues it lowercase. Page-relative geometry (gaps, indent)
        # is not comparable across pages, so we rely solely on the textual signal.
        return soft_wrap
    vertical_gap = max(0.0, float(current.top) - float(previous.bottom))
    max_gap = min(body_leading * 0.55, min(previous_font_size, current_font_size) * 1.25)
    if soft_wrap:
        max_gap = max(max_gap, body_leading * 1.1)
    if vertical_gap > max_gap:
        return False
    # A list item soft-wraps with a hanging indent: the continuation line is set
    # further right than the bullet/number line. A confirmed continuation signal
    # (non-terminal previous + lowercase start) therefore overrides the
    # "near the previous indent" requirement, which only holds for flush wraps.
    near_previous_indent = abs(float(current.x0) - float(previous.x0)) <= body_leading * 0.75
    if not near_previous_indent and not soft_wrap:
        return False
    return (
        _starts_like_sentence_continuation(current_text)
        or _span_line_fill_ratio(previous, layout_profile) >= 0.72
    )


def _looks_like_superscript_footnote_marker(
    span: PdfTextSpan,
    *,
    previous_span: PdfTextSpan | None,
    next_span: PdfTextSpan | None = None,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    text = _normalize_text(span.text)
    if not re.fullmatch(r"\d{1,3}", text):
        return False
    body_font_size = layout_profile.body_font_size
    marker_font_size = span.font_size if isinstance(span.font_size, (int, float)) else None
    if not body_font_size or not marker_font_size or marker_font_size > body_font_size * 0.62:
        return False
    return any(
        _span_is_tail_marker_for_text_span(
            marker=span,
            text_span=candidate,
            marker_font_size=marker_font_size,
            body_font_size=body_font_size,
            layout_profile=layout_profile,
        )
        for candidate in (previous_span, next_span)
    )


def _span_is_tail_marker_for_text_span(
    *,
    marker: PdfTextSpan,
    text_span: PdfTextSpan | None,
    marker_font_size: float,
    body_font_size: float,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    if text_span is None or text_span.page_number != marker.page_number:
        return False
    text = _normalize_text(text_span.text)
    if not _can_attach_tail_footnote_marker(text):
        return False
    body_leading = layout_profile.body_leading or body_font_size * 1.2
    if float(marker.x0) < float(text_span.x1) - body_leading * 0.2:
        return False
    if float(marker.top) > float(text_span.bottom) or float(marker.bottom) < float(text_span.top):
        return False
    return float(marker.bottom) <= float(text_span.bottom) - marker_font_size * 0.5


def _can_attach_tail_footnote_marker(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    last_char = stripped[-1]
    return last_char.isalpha() or last_char in ".!?:;)]}»”\"'"


def _can_prefix_heading_with_standalone_number(
    prefix_span: PdfTextSpan,
    heading_span: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    prefix_text = _normalize_text(prefix_span.text)
    if not re.fullmatch(r"\d{1,3}", prefix_text):
        return False
    if prefix_span.page_number != heading_span.page_number:
        return False
    prefix_font_size = prefix_span.font_size if isinstance(prefix_span.font_size, (int, float)) else None
    heading_font_size = heading_span.font_size if isinstance(heading_span.font_size, (int, float)) else None
    if not prefix_font_size or not heading_font_size:
        return False
    smaller = min(float(prefix_font_size), float(heading_font_size))
    larger = max(float(prefix_font_size), float(heading_font_size))
    if larger - smaller > max(0.5, smaller * 0.12):
        return False
    vertical_gap = float(heading_span.top) - float(prefix_span.bottom)
    body_leading = layout_profile.body_leading or float(heading_font_size) * 1.2
    if vertical_gap < 0 or vertical_gap > max(float(heading_font_size) * 1.5, body_leading * 2.5):
        return False
    prefix_center = (float(prefix_span.x0) + float(prefix_span.x1)) / 2.0
    heading_padding = max(float(heading_font_size), (float(heading_span.x1) - float(heading_span.x0)) * 0.08)
    return float(heading_span.x0) - heading_padding <= prefix_center <= float(heading_span.x1) + heading_padding


def _looks_like_digit_only_small_span(
    span: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    text = _normalize_text(span.text)
    if not re.fullmatch(r"\d{1,3}", text):
        return False
    body_font_size = layout_profile.body_font_size
    span_font_size = span.font_size if isinstance(span.font_size, (int, float)) else None
    return bool(body_font_size and span_font_size and span_font_size <= body_font_size * 0.82)


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



def _paragraph_from_body_spans(
    spans: list[PdfTextSpan],
    *,
    inline_markers: dict[int, list[str]] | None = None,
) -> ParagraphUnit:
    inline_markers = inline_markers or {}
    pieces: list[str] = []
    for index, span in enumerate(spans):
        pieces.append(_normalize_text(span.text))
        for marker in inline_markers.get(index, []):
            # A marker that re-attaches to the END of a completed sentence (the
            # preceding piece ends with terminal punctuation) is a footnote
            # reference for that sentence: render it as a trailing Unicode
            # superscript glued directly to the sentence (no separating space)
            # so the sentence body stays byte-identical and the marker reads as a
            # footnote superscript rather than a stray digit. A marker that
            # interrupts a sentence (preceding half not terminated) keeps its
            # original inline, space-separated form so the prose flows across it.
            previous_piece = pieces[-1] if pieces else ""
            if (
                previous_piece
                and previous_piece[-1] in _TERMINAL_SENTENCE_PUNCTUATION
                and _SUPERSCRIPT_MARKER_DIGITS_PATTERN.match(marker)
            ):
                pieces[-1] = f"{previous_piece.rstrip()}{_to_superscript_digits(marker)}"
            else:
                pieces.append(marker)
    text = " ".join(piece for piece in pieces if piece)
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


def _paragraph_from_list_spans(
    spans: list[PdfTextSpan],
    *,
    median_font_size: float | None,
) -> ParagraphUnit:
    if len(spans) == 1:
        return _paragraph_from_span(spans[0], role="list", median_font_size=median_font_size)
    text = " ".join(_normalize_text(span.text) for span in spans)
    first = spans[0]
    return ParagraphUnit(
        text=text,
        role="list",
        structural_role="list",
        role_confidence="heuristic",
        style_name=_style_name_for_role("list"),
        heading_level=None,
        heading_source=None,
        list_kind="ordered" if _ORDERED_LIST_PATTERN.match(_normalize_text(first.text)) else "bullet",
        list_level=0,
        is_bold=all(span.is_bold for span in spans),
        is_italic=all(span.is_italic for span in spans),
        font_size_pt=_median_font_size(spans),
        origin_raw_indexes=[_span_origin_index(span) for span in spans],
        origin_raw_texts=[_normalize_text(span.text) for span in spans],
        layout_origin="pdf_text_layer",
        boundary_source="pdf_text_layer",
        boundary_confidence="heuristic",
        boundary_rationale="merged_pdf_list_continuation_spans",
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
    heading_level = None
    if role == "heading":
        # A deterministic "Chapter <roman/number>" line is the top-level structural
        # heading (h1) regardless of its font size: such a chapter line is frequently
        # set at body size, so font-ratio inference would mislabel it h3.
        if _CHAPTER_HEADING_PATTERN.match(text):
            heading_level = 1
        else:
            heading_level = _infer_heading_level(span, median_font_size=median_font_size)
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
    if role == "footnote":
        return "PDF Footnote"
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
