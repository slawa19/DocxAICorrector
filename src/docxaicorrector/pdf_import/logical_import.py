"""Build source paragraph units from deterministic PDF text-layer spans."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from statistics import median

from docxaicorrector.core.models import (
    BACK_MATTER_SECTION_INDEX,
    BACK_MATTER_SECTION_NOTES,
    BACK_MATTER_SECTION_REFERENCES,
    ParagraphUnit,
)
from docxaicorrector.document.semantic_blocks import (
    _BACK_MATTER_SECTION_KIND_BY_TITLE,
    _unwrap_inline_emphasis,
)
from docxaicorrector.pipeline.output_validation import (
    is_notes_run_paragraph,
    opens_with_note_number,
)
from docxaicorrector.validation.formatting_coverage import _normalize_structural_text
from docxaicorrector.pdf_import.text_layer_quality import (
    _SUPERSCRIPT_MARKER_ANCHOR_CLOSERS,
    PdfTextSpan,
    _can_end_with_superscript_marker,
    _detect_repeated_page_furniture_keys,
    _detect_running_heads_on_page_number_line,
    _looks_like_page_number,
    _normalize_text,
    _span_furniture_key,
)


_BULLET_PATTERN = re.compile(r"^(?P<marker>[-*•●])\s+(?P<body>.+)$")
_ORDERED_LIST_PATTERN = re.compile(r"^(?P<marker>\d+)[.)]\s+(?P<body>.+)$")
# A leading section ordinal on a heading line ("5. Обесценивание …" or the
# nested "2.1. …"). Used to rank numbered section headings above bare headings
# set at the same font size. General numbering signal, not a literal.
_SECTION_ORDINAL_HEADING_PATTERN = re.compile(r"^\d+(?:\.\d+)*\.\s+\S")
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
_SUPERSCRIPT_REFERENCE_TAIL_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹ "
# A line that reaches this share of the body column did not end short: the body merge reads a
# shorter line before a new sentence as a paragraph end, the list merge a longer one as a line
# the item ran on from, and spec 078 a longer numbered line as one that wrapped. One value,
# named in spec 078 where it had been written out twice; the value is unchanged.
_FULL_LINE_FILL_RATIO = 0.72
# A line of at least this many words can be a line of running body text (the body column is measured on such
# lines only); spec 082 slice B reads the same test.
_BODY_LINE_MIN_WORDS = 7
# Spec 064 FR-007: two spans are in one table row when their tops differ by at most this share
# of a line's height and their sizes by less than this many points.
_TABLE_ROW_BASELINE_TOLERANCE = 0.3
_TABLE_ROW_SIZE_TOLERANCE_PT = 0.5
_TABLE_CELL_MAX_FONT_RATIO = 1.1
# Spec 064 FR-007: a table cell is shorter than this share of a body line (p75) -- half a line
# keeps a two-column body out. Spec 068 FR-001: inside a back-matter index a whole line.
_TABLE_CELL_MAX_BODY_LINE_SHARE = 0.5
_INDEX_CELL_MAX_BODY_LINE_SHARE = 1.0
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
    # Spec 064 FR-007: spans that share their baseline with another short span of the same
    # size across a horizontal gap -- the cells of a table, the columns of an index.
    table_row_span_keys: frozenset[tuple[int, float, float]] = frozenset()


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


@dataclass(frozen=True)
class PdfBodyTypography:
    """The body typography the importer measures for a document: its body font size and body column."""

    body_font_size: float | None
    body_left_x0: float | None
    body_right_x1: float | None


@dataclass(frozen=True)
class _PreparedImportSpans:
    normalized_spans: list[PdfTextSpan]
    repeated_furniture_keys: set[tuple[str, str]]
    display_text_spans: list[PdfTextSpan]
    skipped_running_head_count: int
    ordered_spans: list[PdfTextSpan]
    layout_profile: _PdfHeadingLayoutProfile


def _prepare_spans_for_import(spans: list[PdfTextSpan]) -> _PreparedImportSpans:
    normalized_spans = [span for span in spans if _normalize_text(span.text)]
    repeated_furniture_keys = _detect_repeated_page_furniture_keys(tuple(normalized_spans))
    # Spec 067 FR-007: a running head on the page-number line is furniture even on one or two
    # pages, where the repeated-key rule above does not reach it. It is dropped here, before
    # anything reads the page, like the number beside it. Heads the key rule already covers
    # stay in the list and are skipped where they always were; the repeated-display-text
    # count still reads every line, running heads included, as before.
    running_heads = frozenset(
        span
        for span in _detect_running_heads_on_page_number_line(normalized_spans)
        if _span_furniture_key(span) not in repeated_furniture_keys
    )
    display_text_spans = normalized_spans
    skipped_running_head_count = 0
    if running_heads:
        kept_spans = [span for span in normalized_spans if span not in running_heads]
        skipped_running_head_count = len(normalized_spans) - len(kept_spans)
        normalized_spans = kept_spans
    ordered_spans = sorted(normalized_spans, key=lambda item: (item.page_number, item.top, item.x0))
    layout_profile = _build_heading_layout_profile(
        ordered_spans,
        repeated_furniture_keys=repeated_furniture_keys,
        display_text_spans=display_text_spans,
    )
    return _PreparedImportSpans(
        normalized_spans=normalized_spans,
        repeated_furniture_keys=repeated_furniture_keys,
        display_text_spans=display_text_spans,
        skipped_running_head_count=skipped_running_head_count,
        ordered_spans=ordered_spans,
        layout_profile=layout_profile,
    )


def pdf_body_typography(spans: list[PdfTextSpan]) -> PdfBodyTypography:
    """The importer's body font size and body column, by the very preparation the importer runs (spec 082 slice B
    reads them to tell running text from the labels of a figure)."""

    profile = _prepare_spans_for_import(list(spans)).layout_profile
    return PdfBodyTypography(
        body_font_size=profile.body_font_size,
        body_left_x0=profile.body_left_x0,
        body_right_x1=profile.body_right_x1,
    )


def build_paragraph_units_from_text_spans(
    spans: list[PdfTextSpan],
) -> PdfSourceImportResult:
    prepared = _prepare_spans_for_import(spans)
    normalized_spans = prepared.normalized_spans
    repeated_furniture_keys = prepared.repeated_furniture_keys
    skipped_running_head_count = prepared.skipped_running_head_count
    dehyphenation_evidence = _build_soft_wrap_dehyphenation_evidence(normalized_spans)
    ordered_spans = prepared.ordered_spans
    layout_profile = prepared.layout_profile
    median_font_size = layout_profile.body_font_size
    # Spec 084: the lines of each page, in reading order, for the hanging-indent run test the
    # classifier asks of a line it would type a heading -- the same lists spec 081 reads.
    lines_by_page: dict[int, list[PdfTextSpan]] = {}
    for ordered_span in ordered_spans:
        lines_by_page.setdefault(ordered_span.page_number, []).append(ordered_span)

    emitted: list[ParagraphUnit] = []
    pending_body_spans: list[PdfTextSpan] = []
    pending_body_inline_markers: dict[int, list[str]] = {}
    pending_heading_spans: list[PdfTextSpan] = []
    pending_list_spans: list[PdfTextSpan] = []
    skipped_repeated_page_furniture_count = skipped_running_head_count
    skipped_page_number_count = 0
    skipped_blank_page_notice_count = 0

    def _flush_body() -> None:
        nonlocal pending_body_spans, pending_body_inline_markers
        if pending_body_spans:
            emitted.append(
                _mark_table_cell_unit(
                    _paragraph_from_body_spans(
                        pending_body_spans,
                        inline_markers=pending_body_inline_markers,
                        dehyphenation_evidence=dehyphenation_evidence,
                    ),
                    pending_body_spans,
                    layout_profile=layout_profile,
                )
            )
            pending_body_spans = []
            pending_body_inline_markers = {}

    def _flush_heading() -> None:
        nonlocal pending_heading_spans
        if pending_heading_spans:
            emitted.append(
                _mark_table_cell_unit(
                    _paragraph_from_heading_spans(
                        pending_heading_spans, median_font_size=median_font_size
                    ),
                    pending_heading_spans,
                    layout_profile=layout_profile,
                )
            )
            pending_heading_spans = []

    def _flush_list() -> None:
        nonlocal pending_list_spans
        if pending_list_spans:
            emitted.append(
                _mark_table_cell_unit(
                    _paragraph_from_list_spans(
                        pending_list_spans, median_font_size=median_font_size
                    ),
                    pending_list_spans,
                    layout_profile=layout_profile,
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
            page_lines=lines_by_page.get(span.page_number, []),
        )
        if role == "body":
            # Spec 063 FR-008: the last line of a two-line heading that the per-span
            # classifier sent to body (a second line that reads like a sentence
            # continuation, or whose signature drifted into the body cluster) joins the
            # heading it continues.
            if _can_continue_heading_with_line(
                pending_heading_spans,
                span,
                next_span=next_content_span,
                layout_profile=layout_profile,
            ):
                pending_heading_spans.append(span)
                continue
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
            if pending_body_spans and (
                not _can_merge_body_span(
                    pending_body_spans[-1],
                    span,
                    layout_profile=layout_profile,
                    paragraph_left_x0=_paragraph_run_left_x0(pending_body_spans),
                )
                # Spec 065 FR-008 (I-4): a table cell is a paragraph of its own. Since
                # spec 064 FR-007 a cell is no longer a heading, and the body merge then
                # ran it into the next line of ANOTHER column ("PU BLIC SECTOR" + "NGO
                # Initiative s :", Money's Box 7.1).
                or _is_table_row_cell(pending_body_spans[-1], layout_profile=layout_profile)
                or _is_table_row_cell(span, layout_profile=layout_profile)
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
            emitted.append(
                _mark_table_cell_unit(
                    _paragraph_from_span(span, role=role, median_font_size=median_font_size),
                    [span],
                    layout_profile=layout_profile,
                )
            )
            continue
        if role == "toc_entry":
            _flush_body()
            _flush_heading()
            _flush_list()
            emitted.append(
                _mark_table_cell_unit(
                    _paragraph_from_span(span, role=role, median_font_size=median_font_size),
                    [span],
                    layout_profile=layout_profile,
                )
            )
            continue
        _flush_body()
        _flush_heading()
        _flush_list()
        emitted.append(
            _mark_table_cell_unit(
                _paragraph_from_span(span, role=role, median_font_size=median_font_size),
                [span],
                layout_profile=layout_profile,
            )
        )

    _flush_body()
    _flush_heading()
    _flush_list()

    emitted = _consolidate_cross_role_continuations(
        emitted, dehyphenation_evidence=dehyphenation_evidence
    )
    emitted = _reconcile_structural_headings(
        emitted, body_font_size=layout_profile.body_font_size
    )
    # After the structural pass: a heading that pass makes keeps the level it gives, and
    # FR-009 only reads what is still body.
    emitted = _reconcile_display_titles(emitted, ordered_spans, layout_profile=layout_profile)
    # Spec 065 FR-008: settle heading roles inside notes / reference sections before the join
    # reads them -- the join never crosses a heading, so a fragment typed heading kept a torn
    # entry torn.
    emitted = _settle_back_matter_entry_roles(emitted, ordered_spans)
    # Spec 064 R-7: after every role is final, because the region is anchored on a heading
    # and the join refuses to touch one.
    emitted = _join_torn_back_matter_entries(
        emitted,
        ordered_spans,
        layout_profile=layout_profile,
        dehyphenation_evidence=dehyphenation_evidence,
    )
    # Spec 065 FR-009: the body counterpart, outside those sections -- a sentence that wrapped
    # before a number ("...during" + "1702. She was known ...") is not a list item.
    emitted = _join_numbered_body_continuations(
        emitted,
        ordered_spans,
        layout_profile=layout_profile,
        dehyphenation_evidence=dehyphenation_evidence,
    )
    # Spec 067 FR-005: a body paragraph torn at a page break whose second half opens with a
    # capital, a digit, a quote or a bracket -- the text-only soft-wrap merge leaves it torn.
    emitted = _join_page_torn_body_paragraphs(
        emitted,
        ordered_spans,
        layout_profile=layout_profile,
        repeated_furniture_keys=repeated_furniture_keys,
        dehyphenation_evidence=dehyphenation_evidence,
    )

    _attach_pdf_layout_signals(emitted, ordered_spans, layout_profile=layout_profile)

    # Every role is final by this point, so the style the bridge will write can be decided —
    # once, from the single table in `_ROLE_DOCX_STYLE`.
    _assign_docx_style_names(emitted)

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
    if unit.is_pdf_table_cell:
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
    footnote marker (handled inline separately). Nor a table cell (spec 065 FR-008): a
    cell is a paragraph of its own, whatever case its text begins with."""
    if unit.structural_role == "toc_entry":
        return False
    if unit.is_pdf_table_cell:
        return False
    if _unit_is_standalone_footnote_marker(unit):
        return False
    return bool((unit.text or "").strip())


def _merge_continuation_units(
    units: list[ParagraphUnit],
    *,
    inline_markers: list[str],
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None = None,
) -> ParagraphUnit:
    """Fuse a run of prose units (Rule 2) into a single body unit.

    ``inline_markers`` are footnote-marker texts that sat between halves of the
    fused sentence (Rule 1); they are spliced back inline at their original
    position so the marker survives without breaking the paragraph flow.
    """
    piece_runs: list[list[StyleRun]] = []
    for index, unit in enumerate(units):
        runs = _unit_style_runs(unit)
        if index < len(inline_markers) and inline_markers[index]:
            if "".join(text for text, _, _ in runs):
                runs.append((" ", False, False))
            runs.append((inline_markers[index], False, False))
        piece_runs.append(runs)
    joined_runs = _join_soft_wrapped_run_pieces(
        piece_runs, dehyphenation_evidence=dehyphenation_evidence
    )
    text = "".join(run_text for run_text, _, _ in joined_runs)
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
        is_bold=all(unit.is_bold for unit in units),
        is_italic=all(unit.is_italic for unit in units),
        font_size_pt=first.font_size_pt,
        origin_raw_indexes=origin_indexes,
        origin_raw_texts=origin_texts,
        pdf_emphasis_runs=joined_runs,
        layout_origin="pdf_text_layer",
        boundary_source="pdf_text_layer",
        boundary_confidence="heuristic",
        boundary_rationale="merged_cross_role_soft_wrap_continuation",
        source_index=first.source_index,
        page_number=first.page_number,
    )


def _mark_table_cell_unit(
    unit: ParagraphUnit,
    spans: list[PdfTextSpan],
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> ParagraphUnit:
    """Spec 065 FR-008 (I-4): a unit built from a table-row cell carries that fact, so the
    passes that join units after the span loop -- which no longer see the table geometry --
    refuse to join across it (`_consolidate_cross_role_continuations`,
    `_join_torn_back_matter_entries`, `_join_numbered_body_continuations`)."""
    if any(_is_table_row_cell(span, layout_profile=layout_profile) for span in spans):
        unit.is_pdf_table_cell = True
    return unit


def _consolidate_cross_role_continuations(
    units: list[ParagraphUnit],
    *,
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None = None,
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
            result.append(
                _merge_continuation_units(
                    run,
                    inline_markers=inline_markers,
                    dehyphenation_evidence=dehyphenation_evidence,
                )
            )
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
    page_lines: list[PdfTextSpan] | None = None,
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
    if not soft_wrap_continuation and _looks_like_chapter_heading(
        span, layout_profile=layout_profile
    ):
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
        page_lines=page_lines,
    ):
        return "heading"
    return "body"


def _build_heading_layout_profile(
    spans: list[PdfTextSpan],
    *,
    repeated_furniture_keys: set[tuple[str, str]],
    display_text_spans: list[PdfTextSpan] | None = None,
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
        if len(words) < _BODY_LINE_MIN_WORDS:
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
    repeated_display_text_keys = _detect_repeated_display_text_keys(
        spans if display_text_spans is None else display_text_spans
    )
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
        table_row_span_keys=_detect_table_row_span_keys(
            spans,
            repeated_furniture_keys=repeated_furniture_keys,
            body_line_length_p75=body_line_length_p75,
            body_font_size=body_font_size,
        ),
    )


def _table_row_span_key(span: PdfTextSpan) -> tuple[int, float, float]:
    return (span.page_number, round(float(span.top), 2), round(float(span.x0), 2))


def _row_pieces_are_one_cut_line(
    first: PdfTextSpan,
    second: PdfTextSpan,
    page_spans: list[PdfTextSpan],
) -> bool:
    """Spec 065 FR-008: two spans of one baseline that are one line of text the extractor cut
    in pieces, not two cells.

    The pieces stand a word space apart -- the gap between them is less than one font size
    -- and the right one starts no column: no span of its size on another row of the page
    starts where it starts. Measured 2026-11-08 on the four corpus PDFs: the extractor cuts
    justified prose lines of Money and Sustainability (pp. 10, 71, 118, 135), a line of
    Creating Wealth around a fraction glyph (p. 51) and a contents row of Rethinking Money
    ("Foreword" | "ix") at 0.56-0.72 of the font size; every real row of a table or an index
    has a wider gap, except Money's signature block (p. 4, 0.56), whose second column starts
    at the same x on three rows."""
    left, right = (first, second) if float(first.x0) <= float(second.x0) else (second, first)
    font_size = float(left.font_size or right.font_size or 0)
    if font_size <= 0 or float(right.x0) - float(left.x1) >= font_size:
        return False
    line_height = float(right.bottom) - float(right.top) or font_size
    return not any(
        other is not right
        and abs(float(other.top) - float(right.top)) > _TABLE_ROW_BASELINE_TOLERANCE * line_height
        and abs(float(other.font_size or 0) - float(right.font_size or 0)) < _TABLE_ROW_SIZE_TOLERANCE_PT
        and abs(float(other.x0) - float(right.x0)) <= 1.0
        for other in page_spans
    )


def _span_stands_between(
    first: PdfTextSpan,
    second: PdfTextSpan,
    page_spans: list[PdfTextSpan],
) -> bool:
    """Is there a span of the same baseline horizontally between the two?"""
    left, right = (first, second) if float(first.x0) <= float(second.x0) else (second, first)
    line_height = float(left.bottom) - float(left.top) or float(left.font_size or 0)
    return any(
        other is not left
        and other is not right
        and abs(float(other.top) - float(left.top)) <= _TABLE_ROW_BASELINE_TOLERANCE * line_height
        and float(other.x0) >= float(left.x1)
        and float(other.x1) <= float(right.x0)
        for other in page_spans
    )


def _detect_table_row_span_keys(
    spans: list[PdfTextSpan],
    *,
    repeated_furniture_keys: set[tuple[str, str]],
    body_line_length_p75: float,
    body_font_size: float | None = None,
) -> frozenset[tuple[int, float, float]]:
    """Spans that sit in one ROW with another short span of the same size (spec 064 FR-007).

    A heading stands alone on its line. Two or more spans on one baseline, separated by a
    horizontal gap, set in the same size and each shorter than half a body line, are the
    cells of a table or a diagram, or the two columns of an index: Creating Wealth's
    "Competition and Cooperation" figure ("Peak Experience" | "Endurance-Sus tainability")
    came through as a run of level-3 headings (spec 064 R-5). The half-line bound keeps a
    two-column body out: there the line beside a heading is a full column line.

    Spec 068 FR-001: inside a back-matter INDEX (`_index_region_span_flags`) the bound is a
    whole body line instead. An index is set in two narrow columns of entries, never in a
    two-column body, so the risk the half-line bound guards against does not exist there --
    while an entry line of the index runs up to a column's width, longer than half a body line
    (Rethinking Money: 39-41 characters at a half-line of 35.5). Such a row failed the bound,
    and its short neighbour then took the typographic heading path as a lone small line: a
    false heading that opened its own block in the middle of the index (24 of them).
    """

    if body_line_length_p75 <= 0:
        return frozenset()
    max_cell_chars = _TABLE_CELL_MAX_BODY_LINE_SHARE * body_line_length_p75
    max_index_cell_chars = _INDEX_CELL_MAX_BODY_LINE_SHARE * body_line_length_p75
    in_index = _index_region_span_flags(
        spans,
        repeated_furniture_keys=repeated_furniture_keys,
        body_font_size=body_font_size,
    )
    by_page: dict[int, list[PdfTextSpan]] = {}
    for span, span_in_index in zip(spans, in_index):
        text = _normalize_text(span.text)
        bound = max_index_cell_chars if span_in_index else max_cell_chars
        if not text or len(text) >= bound or not span.font_size:
            continue
        if _span_furniture_key(span) in repeated_furniture_keys or _looks_like_page_number(span):
            continue
        by_page.setdefault(span.page_number, []).append(span)
    all_by_page: dict[int, list[PdfTextSpan]] = {}
    for span in spans:
        if _normalize_text(span.text) and span.font_size:
            all_by_page.setdefault(span.page_number, []).append(span)
    keys: set[tuple[int, float, float]] = set()
    for page_number, page_spans in by_page.items():
        for index, span in enumerate(page_spans):
            line_height = float(span.bottom) - float(span.top) or float(span.font_size or 0)
            for other in page_spans[index + 1 :]:
                if abs(float(other.top) - float(span.top)) > _TABLE_ROW_BASELINE_TOLERANCE * line_height:
                    continue
                if not (other.x1 <= span.x0 or other.x0 >= span.x1):
                    continue
                if abs(float(other.font_size or 0) - float(span.font_size or 0)) >= _TABLE_ROW_SIZE_TOLERANCE_PT:
                    continue
                if _row_pieces_are_one_cut_line(span, other, all_by_page.get(page_number, [])):
                    continue
                if _span_stands_between(span, other, all_by_page.get(page_number, [])):
                    # Not neighbours: the pair of each with the piece between them decides.
                    continue
                keys.add(_table_row_span_key(span))
                keys.add(_table_row_span_key(other))
    # One hop more: a short span of the same size within one line of a cell belongs to the
    # same table -- a header cell set a little above its row, or two cells the extractor
    # read as one line ("Command and Control Mutual Trust and Action"). Only one hop, so a
    # heading set at a heading's distance above a table is not reached.
    row_cells = [
        span for page_spans in by_page.values() for span in page_spans if _table_row_span_key(span) in keys
    ]
    cells_by_page: dict[int, list[PdfTextSpan]] = {}
    for cell in row_cells:
        cells_by_page.setdefault(cell.page_number, []).append(cell)
    for page_number, page_spans in by_page.items():
        page_cells = cells_by_page.get(page_number, [])
        if not page_cells:
            continue
        for span in page_spans:
            if _table_row_span_key(span) in keys:
                continue
            line_height = float(span.bottom) - float(span.top) or float(span.font_size or 0)
            same_size_cells = [
                cell
                for cell in page_cells
                if abs(float(cell.font_size or 0) - float(span.font_size or 0)) < _TABLE_ROW_SIZE_TOLERANCE_PT
            ]
            if not same_size_cells:
                continue
            # Codex review 2026-11-07: the span must also stand within the table's width --
            # the horizontal extent of its cells of this size on the page. A short heading in
            # the other column, one line above a table row, is not part of the table.
            table_x0 = min(float(cell.x0) for cell in same_size_cells)
            table_x1 = max(float(cell.x1) for cell in same_size_cells)
            if float(span.x1) <= table_x0 or float(span.x0) >= table_x1:
                continue
            for cell in same_size_cells:
                vertical_gap = max(float(cell.top) - float(span.bottom), float(span.top) - float(cell.bottom))
                if vertical_gap <= line_height:
                    keys.add(_table_row_span_key(span))
                    break
    return frozenset(keys)


def _index_region_span_flags(
    spans: list[PdfTextSpan],
    *,
    repeated_furniture_keys: set[tuple[str, str]],
    body_font_size: float | None,
) -> list[bool]:
    """Spec 068 FR-001: per span of `spans` (reading order), does it sit inside a back-matter
    INDEX?

    The rows are read from spans, before any unit exists, so the unit-level region
    (`_back_matter_entry_region_flags`) is not available here; the anchor is read in the same
    terms at span level. It is a line whose whole text is an index title of the blessed
    back-matter lexicon (`_BACK_MATTER_SECTION_KIND_BY_TITLE`, exact match after the
    normalisation `_back_matter_anchor_kind` applies -- never containment), set above the body
    and opening its page: the first line of the page that is not furniture or a page number.
    That is the form of a section title; a contents row naming the index is set at body size
    among other rows, and a running head is furniture. The region runs from the line after the
    title to the next line that opens its page set at the title's size or larger -- the next
    section of the same rank -- or to the end of the document. Without a body size there is no
    region: the bound stays where it was."""

    flags = [False] * len(spans)
    if not body_font_size:
        return flags
    opens_page: list[bool] = []
    seen_pages: set[int] = set()
    for span in spans:
        is_content = bool(_normalize_text(span.text)) and not (
            _span_furniture_key(span) in repeated_furniture_keys or _looks_like_page_number(span)
        )
        opens_page.append(is_content and span.page_number not in seen_pages)
        if is_content:
            seen_pages.add(span.page_number)
    title_size: float | None = None
    for index, span in enumerate(spans):
        font_size = float(span.font_size or 0)
        if opens_page[index] and font_size > 0:
            if title_size is not None and font_size >= title_size - _TABLE_ROW_SIZE_TOLERANCE_PT:
                title_size = None
            title = _normalize_structural_text(_unwrap_inline_emphasis(_normalize_text(span.text))).lower()
            if (
                _BACK_MATTER_SECTION_KIND_BY_TITLE.get(title) == BACK_MATTER_SECTION_INDEX
                and font_size / body_font_size >= _HEADING_PROMINENT_FONT_RATIO
            ):
                title_size = font_size
                continue
        flags[index] = title_size is not None
    return flags


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


def _opens_a_wrapped_citation_entry(
    span: PdfTextSpan,
    *,
    next_span: PdfTextSpan | None,
    page_lines: list[PdfTextSpan],
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    """Spec 084: `span` is the first line of an entry of a list set with a hanging indent, and
    the entry is a reference -- so typography does not make it a heading.

    `_looks_like_footnote_or_citation_tail` already keeps a line that cites from becoming a
    heading, but it reads the one line; an entry that wraps before its year or address
    ("Surname, A. *A Title of Some Length* (City: Publisher" + "Press 1999)") passes it, and
    the indent of a hanging-indent list together with title-cased words is enough for the
    style clusters to call that line a heading. All five are required, each read off the page:
      * the next line wraps to the hanging indent of a run (`_line_wraps_to_the_hanging_indent`,
        the spec 081 test): it starts right of `span` by the first-line-indent step, and the
        unbroken run of same-size lines on the page shows that margin / indent pair at least
        twice. A heading above a list, or above prose set flush, is followed by a line at the
        margin;
      * the run is not prose set with a first-line indent
        (`_run_returns_running_text_to_the_margin`): nowhere in it does a full line at the indent
        run on at the margin. Prose shows the margin / indent step at every paragraph start too;
        under a full-width heading it read as a list (Codex acceptance review, P1);
      * `span` ran out of room for the next line's first word (`_entry_line_ran_out_of_room`):
        a short line at the margin over the indent -- an author set as a label above his works
        -- ended for a reason of its own;
      * the line and the next line read together as a citation by the same invariant;
      * P, position (Codex acceptance review, round 2): the line directly above `span` is a
        line of the same run AT THE INDENT -- the wrapped line of the entry before
        (`_follows_a_wrapped_line_of_the_run`). A heading stands above what it heads, so
        nothing of the list or prose under it precedes it; a reference entry mistaken for a
        heading stands inside its list, between entries. N reads prose by what its lines do and
        a ragged right edge defeats it; P asks where the line stands.
    The deterministic heading paths (a chapter label, a numbered section heading) never reach
    this: it is asked only on the typographic path. The run is looked up on `span`'s page, so
    nothing is compared across a page break, where the edges of facing pages differ. Measured
    2026-11-13 on the four corpus PDFs with the classifier as it stood before this rule: of 677
    lines typed heading by typography, 3 hold H, N, R and C -- the first lines of three entries
    of one reference list in Creating Wealth -- and 2 of them hold P as well: the third follows
    the list's centred sub-heading, not an entry, and stays as it was (spec 084)."""
    if next_span is None:
        return False
    if not _line_wraps_to_the_hanging_indent(
        span, next_span, page_lines=page_lines, layout_profile=layout_profile
    ):
        return False
    if not _follows_a_wrapped_line_of_the_run(span, next_span, page_lines=page_lines):
        return False
    if _run_returns_running_text_to_the_margin(
        span, next_span, page_lines=page_lines, layout_profile=layout_profile
    ):
        return False
    next_text = _normalize_text(next_span.text)
    if not _entry_line_ran_out_of_room(span, next_text, layout_profile=layout_profile):
        return False
    return _looks_like_footnote_or_citation_tail(f"{_normalize_text(span.text)} {next_text}")


def _looks_like_pdf_heading_candidate(
    span: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    previous_span: PdfTextSpan | None,
    next_span: PdfTextSpan | None,
    page_lines: list[PdfTextSpan] | None = None,
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
    if _opens_a_wrapped_citation_entry(
        span,
        next_span=next_span,
        page_lines=page_lines or [],
        layout_profile=layout_profile,
    ):
        return False
    if _is_table_row_cell(span, layout_profile=layout_profile):
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


def _is_table_row_cell(span: PdfTextSpan, *, layout_profile: _PdfHeadingLayoutProfile) -> bool:
    """A table cell is not a heading -- unless it is set ABOVE the body (display type).

    Only the typographic path asks this: a chapter label or a numbered section heading is
    decided by its own deterministic rule, and a line set larger than the body is display
    type that a table of body-size cells does not produce.
    """

    if _table_row_span_key(span) not in layout_profile.table_row_span_keys:
        return False
    body_font_size = layout_profile.body_font_size
    if body_font_size and span.font_size and float(span.font_size) > _TABLE_CELL_MAX_FONT_RATIO * body_font_size:
        return False
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


_NUMBERED_SECTION_HEADING_PATTERN = re.compile(r"^(?P<number>\d{1,3})\.\s+(?P<title>[A-ZА-Я].*)$")

# --------------------------------------------------------------------------- #
# Heading-marker lexicon (Constitution VII).                                    #
# --------------------------------------------------------------------------- #
# Structural heading detection recognises a small set of MARKER WORDS that open a
# chapter / part / front- or back-matter divider. Those words are collected here
# as a single, documented, EXTENSIBLE lexicon instead of being buried as literals
# inside individual regexes, so the language/literal dependency is explicit and
# auditable, and so the lexicon can be resolved per language via configuration in
# future (an override map keyed by document language would slot in here without
# touching the pattern-construction logic below).
#
# Honest residual limitation: the default lexicon is ENGLISH because source PDFs
# are English on import (translation happens downstream). This is still a
# language-dependent heuristic — a fully language-agnostic structural detector is
# out of scope here (it would key off typography/layout, not marker words) and
# remains future work. Lifting the words into named constants removes the
# "buried per-book/English literal" smell and keeps the current behaviour exactly;
# it does not, by itself, make the detector language-independent.

# Word(s) that open a chapter heading ("Chapter VI"). Matched case-insensitively
# (the whole chapter pattern carries re.IGNORECASE), so casing is not enumerated.
_CHAPTER_MARKER_WORDS: tuple[str, ...] = ("chapter",)
# Word(s) that open a part divider ("PART II", "Part 3"). Matched only in the
# "PART"/"Part" casings — never lowercase "part", which is ordinary prose
# ("part i think"). Casing IS enumerated here because the part patterns are
# case-sensitive by design.
_PART_MARKER_WORDS: tuple[str, ...] = ("PART", "Part")

_CHAPTER_MARKER_ALT = "|".join(_CHAPTER_MARKER_WORDS)
_PART_MARKER_ALT = "|".join(_PART_MARKER_WORDS)

# A chapter heading line: a chapter marker word followed by a roman numeral or an
# arabic number, either standing alone ("Chapter VI") or carrying an inline title
# after a dash/colon ("Chapter I — Where the tide turns"). Roman numerals are
# restricted to a sane chapter range (I…XXXIX worth of letters) and uppercase to
# avoid matching prose words; the title tail, when present, must be introduced by
# a dash or colon (never by a bare space, which would swallow running prose that
# merely begins with the marker word).
_CHAPTER_HEADING_PATTERN = re.compile(
    r"^(?:" + _CHAPTER_MARKER_ALT + r")\s+(?:[IVXLC]{1,7}|\d{1,3})"
    r"(?:\s*[–—:.\-]\s*\S.*)?$",
    re.IGNORECASE,
)
# The standalone "Chapter <roman/number>" number line with nothing after it. Such
# a line is the chapter number itself, never a TOC entry (the trailing roman/arabic
# IS the chapter number, not a page reference following a title).
_CHAPTER_NUMBER_ONLY_PATTERN = re.compile(
    r"^(?:" + _CHAPTER_MARKER_ALT + r")\s+(?:[IVXLC]{1,7}|\d{1,3})$",
    re.IGNORECASE,
)

# A part divider ("PART II", "Part 3", "PART I: LOCAL ECONOMICS"). The number is a
# roman numeral or an arabic number; a title tail, when present, must be introduced
# by a separator (colon/dash), never by a bare space — a body line that merely opens
# "Part I of this survey sets out…" must not be swallowed (the lowercase continuation
# after the number is neither empty nor a separator, so it never matches). Roman
# numerals are uppercase to avoid matching lowercase prose ("part i think").
_PART_DIVIDER_PATTERN = re.compile(
    r"^(?:" + _PART_MARKER_ALT + r")\s+(?:[IVXLCM]{1,7}|\d{1,3})\b(?P<tail>.*)$"
)
# The bare "Part <roman/number>" divider with nothing after it. Like a bare chapter
# number line, the trailing roman/arabic IS the part number, never a page reference,
# so such a line is a divider even though the trailing-page TOC pattern also matches.
_PART_NUMBER_ONLY_PATTERN = re.compile(
    r"^(?:" + _PART_MARKER_ALT + r")\s+(?:[IVXLCM]{1,7}|\d{1,3})$"
)
_STRUCTURAL_TAIL_SEPARATORS = ":—–‒-"

# Standalone front/back-matter section markers — part of the heading-marker
# lexicon documented above (English default, extensible per language via config;
# see the _CHAPTER_MARKER_WORDS / _PART_MARKER_WORDS block). A line that IS exactly
# one of these words (optionally followed by a separator + short title) is a
# structural section heading, not prose. A mid-sentence use ("Conclusion In
# the light of these cases…") is excluded: the marker is followed by a
# space and more words rather than by end-of-line or a separator, so it stays body.
_SECTION_MARKER_WORDS = frozenset(
    {
        "conclusion",
        "introduction",
        "appendix",
        "epilogue",
        "prologue",
        "foreword",
        "preface",
        "afterword",
    }
)
_SECTION_MARKER_LINE_PATTERN = re.compile(r"^(?P<word>[A-Za-z]+)\b(?P<tail>.*)$")

# The notes / bibliography section that opens the back-matter — part of the
# heading-marker lexicon documented above (English default, extensible per
# language via config). In it, per-chapter endnote groupings render as bare
# "Chapter N" labels that are NOT chapter openers.
_NOTES_BACKMATTER_MARKERS = frozenset(
    {"notes", "endnotes", "references", "bibliography"}
)


def _structural_tail_is_heading_shaped(tail: str) -> bool:
    """A structural-heading tail is either empty (bare divider/marker) or a short
    title introduced by a separator. A tail beginning with an ordinary word (a
    space-joined continuation of running prose) is not heading-shaped."""
    stripped = tail.strip()
    if not stripped:
        return True
    if stripped[0] not in _STRUCTURAL_TAIL_SEPARATORS:
        return False
    if stripped.count(":") >= 2:
        # Two colons signal a glued TOC line ("Conclusion: … Appendix: …"), not a
        # single section heading.
        return False
    return len(_words(stripped)) <= 10


def _text_is_part_divider(text: str) -> bool:
    match = _PART_DIVIDER_PATTERN.match(text.strip())
    if match is None:
        return False
    return _structural_tail_is_heading_shaped(match.group("tail"))


def _text_is_section_marker(text: str) -> bool:
    match = _SECTION_MARKER_LINE_PATTERN.match(text.strip())
    if match is None:
        return False
    if match.group("word").lower() not in _SECTION_MARKER_WORDS:
        return False
    return _structural_tail_is_heading_shaped(match.group("tail"))


def _text_is_bare_chapter_number(text: str) -> bool:
    return bool(_CHAPTER_NUMBER_ONLY_PATTERN.match(text.strip()))


def _bare_chapter_number_token(text: str) -> str | None:
    match = re.match(
        r"^(?:" + _CHAPTER_MARKER_ALT + r")\s+([IVXLC]{1,7}|\d{1,3})$",
        text.strip(),
        re.IGNORECASE,
    )
    return match.group(1).upper() if match else None


def _promote_unit_to_heading(unit: ParagraphUnit, *, heading_level: int) -> None:
    unit.role = "heading"
    unit.structural_role = "heading"
    unit.heading_level = heading_level
    unit.heading_source = "pdf_text_layer"
    unit.list_kind = None
    unit.list_level = 0
    unit.boundary_rationale = "promoted_structural_heading"


def _demote_heading_to_body(unit: ParagraphUnit) -> None:
    unit.role = "body"
    unit.structural_role = "body"
    unit.heading_level = None
    unit.heading_source = None
    unit.boundary_rationale = "demoted_spurious_chapter_heading"


# Minimum line-font / body-font ratio that counts as prominent heading typography.
# Shared threshold with the numbered-section detector's font-prominence gate
# (``_looks_like_numbered_section_heading``): a line set at >= 1.12x the body font
# carries a genuine typographic heading signal.
_HEADING_PROMINENT_FONT_RATIO = 1.12


def _span_has_heading_typography_signal(
    span: PdfTextSpan, *, layout_profile: _PdfHeadingLayoutProfile
) -> bool:
    """True when a span carries at least one corroborating heading-typography
    signal — a prominent font relative to body, or bold emphasis.

    This is the layout corroboration required before a pure *text-shape*
    structural match (a ``Chapter N`` line) may be promoted to a heading, mirroring
    ``_looks_like_numbered_section_heading``'s font-prominence gate. Without such a
    signal a body line that merely matches the literal pattern stays body ("no
    source signal, no repair").
    """
    if span.is_bold or any(is_bold for _, is_bold, _ in span.runs):
        return True
    body_font_size = layout_profile.body_font_size
    span_font_size = span.font_size if isinstance(span.font_size, (int, float)) else None
    if body_font_size and span_font_size:
        if float(span_font_size) / float(body_font_size) >= _HEADING_PROMINENT_FONT_RATIO:
            return True
    return False


def _unit_has_heading_typography_signal(
    unit: ParagraphUnit, *, body_font_size: float | None
) -> bool:
    """Paragraph-unit counterpart of ``_span_has_heading_typography_signal``.

    Reads the typography that survives per-span classification and soft-wrap
    consolidation onto the unit (bold flag, per-character emphasis runs, prominent
    font size). A structural divider / section marker the per-span typography test
    missed is promoted only when it still carries one of these signals — a plain
    body-font, non-emphasized line matching the marker literal is left as body.
    """
    if unit.is_bold or any(is_bold for _, is_bold, _ in unit.pdf_emphasis_runs):
        return True
    font_size = unit.font_size_pt
    if body_font_size and isinstance(font_size, (int, float)):
        if float(font_size) / float(body_font_size) >= _HEADING_PROMINENT_FONT_RATIO:
            return True
    return False


def _reconcile_structural_headings(
    units: list[ParagraphUnit], *, body_font_size: float | None = None
) -> list[ParagraphUnit]:
    """Deterministic, document-level heading reconciliation (runs after the per-span
    classification and soft-wrap consolidation).

    Two independent corrections, both driven by generic structure (never by
    book-specific literals):

    A. Promote structural dividers the per-span typography test misses because they
       are set at body size (bold body). A bare "Part N" / "Part N: Title" divider
       becomes a top-level heading (Part sits above Chapter). A standalone
       front/back-matter section marker ("Conclusion", "Introduction: …") becomes a
       heading — but ONLY in the main body (before the notes/bibliography
       back-matter), so an endnote grouping label of the same word is left alone.

    B. De-duplicate chapter openers. A real opener ("Chapter N — Title", or a bare
       "Chapter N" whose chapter body follows) stays a heading. A bare "Chapter N"
       heading is demoted to body when it is instead (1) an adjacent duplicate of the
       same number, (2) part of a cluster of >=2 consecutive bare chapter numbers (a
       part-boundary mini-listing), or (3) inside the notes/bibliography back-matter
       (a per-chapter endnote label). Two real openers never sit adjacent with no
       chapter body between them, so demoting an adjacent run never drops a real
       opener.
    """
    if not units:
        return units

    backmatter_start = len(units)
    for index, unit in enumerate(units):
        if unit.role == "heading" and (unit.text or "").strip().lower() in _NOTES_BACKMATTER_MARKERS:
            backmatter_start = index
            break

    # A. Promote dividers / section markers that were left as body.
    for index, unit in enumerate(units):
        text = unit.text or ""
        is_toc = unit.structural_role == "toc_entry"
        if _text_is_part_divider(text):
            # A bare part divider ("PART II") is mis-read as a TOC row because the
            # roman numeral is taken for a trailing page reference; the roman IS the
            # part number, so it is promoted anyway. A titled part TOC row that
            # genuinely ends with a page number is left to the TOC pass.
            if is_toc and _PART_NUMBER_ONLY_PATTERN.match(text) is None:
                continue
            # Promote a divider left as body to the top level (above chapters), but
            # only when it carries a corroborating typography signal (prominent font
            # or bold) — a plain body-font line that merely matches the "Part N"
            # literal is not repaired. An already-classified heading (e.g. a Contents
            # "PART I: Title" row) keeps its level — its role is not the defect here.
            if unit.role != "heading" and _unit_has_heading_typography_signal(
                unit, body_font_size=body_font_size
            ):
                _promote_unit_to_heading(unit, heading_level=1)
            continue
        # A TOC row ("Introduction: … 1") ends with a page reference and is owned by
        # the TOC pass — never a section-marker heading.
        if is_toc:
            continue
        if (
            unit.role != "heading"
            and index < backmatter_start
            and _text_is_section_marker(text)
            and _unit_has_heading_typography_signal(unit, body_font_size=body_font_size)
        ):
            _promote_unit_to_heading(unit, heading_level=1)

    # B. Demote spurious bare "Chapter N" headings.
    chapter_indexes = [
        index
        for index, unit in enumerate(units)
        if unit.role == "heading" and _text_is_bare_chapter_number(unit.text or "")
    ]
    demote: set[int] = set()
    for index in chapter_indexes:
        if index >= backmatter_start:
            demote.add(index)
    # Group adjacent bare-chapter headings (consecutive in the unit list) into runs.
    run: list[int] = []
    for index in chapter_indexes:
        if run and index == run[-1] + 1:
            run.append(index)
        else:
            if len(run) >= 2:
                _resolve_bare_chapter_run(run, units, demote)
            run = [index]
    if len(run) >= 2:
        _resolve_bare_chapter_run(run, units, demote)

    for index in demote:
        _demote_heading_to_body(units[index])
    return units


def _resolve_bare_chapter_run(
    run: list[int], units: list[ParagraphUnit], demote: set[int]
) -> None:
    """A run of >=2 adjacent bare-chapter headings is never two real openers (a real
    opener is always followed by its chapter body, not by another bare number). If
    every member is the same chapter number it is a duplicate — keep the first and
    demote the rest; otherwise it is a mini-listing — demote all of them."""
    numbers = {_bare_chapter_number_token(units[index].text or "") for index in run}
    if len(numbers) == 1:
        demote.update(run[1:])
    else:
        demote.update(run)


@dataclass(frozen=True)
class _UnitPlacement:
    page_number: int
    top: float
    bottom: float


# Punctuation a title's words may be wrapped in, or that may stand alone between them
# ("EVENLY . . . YET!", "Crash & Burn").
_TITLE_TOKEN_EDGE_CHARS = ".,:;!?…'\"“”‘’«»()[]–—-&"
# One word of a title: letters and digits, optionally joined by an apostrophe, a period or
# a hyphen ("ISN’T", "U.S.", "Non-linear", "1970s"). A token with any other symbol inside is
# not a word -- that is what an OCR'd cover ("ri1*\VvrV", "4&A") is made of.
_TITLE_WORD_PATTERN = re.compile(r"^[^\W_]+(?:['’.\-][^\W_]+)*$")


def _text_is_title_words(text: str) -> bool:
    """Every token is a word or bare punctuation, and at least one word has two letters.

    A shape check on characters, not on vocabulary: it says nothing about WHICH words a
    title holds, only that the line is made of words at all.
    """
    has_word = False
    for token in _words(text):
        core = token.strip(_TITLE_TOKEN_EDGE_CHARS)
        if not core:
            continue
        if not _TITLE_WORD_PATTERN.match(core):
            return False
        if sum(1 for char in core if char.isalpha()) >= 2:
            has_word = True
    return has_word


def _unit_placement(
    unit: ParagraphUnit, spans_by_origin: dict[int, list[PdfTextSpan]]
) -> _UnitPlacement | None:
    """Where the unit sits on its page, read back from the spans it was built from.

    ``None`` when the unit's spans cannot be located or the unit crosses a page: such a
    unit gives no position signal, and FR-009 does not guess one.
    """
    spans = [
        span
        for origin in (unit.origin_raw_indexes or [])
        for span in spans_by_origin.get(int(origin), [])
    ]
    if not spans:
        return None
    pages = {span.page_number for span in spans}
    if len(pages) != 1:
        return None
    return _UnitPlacement(
        page_number=spans[0].page_number,
        top=min(float(span.top) for span in spans),
        bottom=max(float(span.bottom) for span in spans),
    )


def _unit_is_display_line(unit: ParagraphUnit, *, body_font_size: float) -> bool:
    """A short unit set at display size: what a chapter title is made of."""
    if unit.role not in {"body", "heading"} or unit.structural_role not in {"body", "heading"}:
        return False
    font_size = unit.font_size_pt
    if not isinstance(font_size, (int, float)) or font_size <= 0:
        return False
    if float(font_size) / body_font_size < _DISPLAY_TITLE_FONT_RATIO:
        return False
    if len(unit.origin_raw_indexes or []) > _HEADING_MAX_LINES:
        return False
    return 0 < len(_words(unit.text or "")) <= _DISPLAY_TITLE_MAX_WORDS


def _units_continue_one_title(
    previous: ParagraphUnit,
    previous_placement: _UnitPlacement,
    current: ParagraphUnit,
    current_placement: _UnitPlacement,
) -> bool:
    """Two display units are lines of ONE title: same size, set at the title's own leading,
    and the line above neither ends a sentence nor reads as a TOC row (the same refusals as
    ``_can_merge_heading_span``)."""
    previous_size = float(previous.font_size_pt or 0.0)
    current_size = float(current.font_size_pt or 0.0)
    if not _font_sizes_match(previous_size, current_size):
        return False
    gap = current_placement.top - previous_placement.bottom
    if gap > max(previous_size, current_size) * _HEADING_LINE_MAX_GAP_FONT_RATIO:
        return False
    previous_text = (previous.text or "").strip()
    if not previous_text or previous_text[-1] in ".!?:":
        return False
    return not _text_looks_like_toc_entry(previous_text)


def _unit_numbers_title(
    number_unit: ParagraphUnit,
    title_unit: ParagraphUnit,
    spans_by_origin: dict[int, list[PdfTextSpan]],
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    """A chapter number set on its own line above the title ("7" over "Extracting Value
    ..."): the importer's own number-prefix rule (``_can_prefix_heading_with_standalone_
    number``) decides, exactly as it does when the title line was classified a heading."""
    number_spans = [
        span
        for origin in (number_unit.origin_raw_indexes or [])
        for span in spans_by_origin.get(int(origin), [])
    ]
    title_spans = [
        span
        for origin in (title_unit.origin_raw_indexes or [])
        for span in spans_by_origin.get(int(origin), [])
    ]
    if len(number_spans) != 1 or not title_spans:
        return False
    return _can_prefix_heading_with_standalone_number(
        number_spans[0], title_spans[0], layout_profile=layout_profile
    )


def _display_title_heading_level(font_size: float, *, body_font_size: float) -> int:
    # The importer's own font tiers (``_infer_font_heading_level``); a display title is
    # never below the h2 tier by construction.
    return 1 if font_size / body_font_size >= 1.8 else 2


def _display_title_unit(
    group: list[ParagraphUnit], *, body_font_size: float
) -> ParagraphUnit:
    font_sizes = [float(unit.font_size_pt or 0.0) for unit in group]
    font_size = float(median(font_sizes))
    heading_level = _display_title_heading_level(font_size, body_font_size=body_font_size)
    if len(group) == 1:
        unit = group[0]
        _promote_unit_to_heading(unit, heading_level=heading_level)
        unit.boundary_rationale = "promoted_display_title"
        return unit
    runs: list[StyleRun] = []
    for index, unit in enumerate(group):
        if index:
            runs.append((" ", False, False))
        runs.extend(_unit_style_runs(unit))
    origin_indexes: list[int] = []
    origin_texts: list[str] = []
    for unit in group:
        origin_indexes.extend(unit.origin_raw_indexes or [])
        origin_texts.extend(unit.origin_raw_texts or [])
    first = group[0]
    return ParagraphUnit(
        text=" ".join((unit.text or "").strip() for unit in group),
        role="heading",
        structural_role="heading",
        role_confidence="heuristic",
        heading_level=heading_level,
        heading_source="pdf_text_layer",
        list_level=0,
        is_bold=all(unit.is_bold for unit in group),
        is_italic=all(unit.is_italic for unit in group),
        font_size_pt=font_size,
        origin_raw_indexes=origin_indexes,
        origin_raw_texts=origin_texts,
        pdf_emphasis_runs=runs,
        layout_origin="pdf_text_layer",
        boundary_source="pdf_text_layer",
        boundary_confidence="heuristic",
        boundary_rationale="merged_display_title_lines",
        source_index=first.source_index,
    )


def _reconcile_display_titles(
    units: list[ParagraphUnit],
    ordered_spans: list[PdfTextSpan],
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> list[ParagraphUnit]:
    """Spec 063 FR-009: a chapter title that the per-span pass left as body, by form only.

    Where a chapter opens, the page starts with its display block: labels the importer
    already calls headings ("Chapter One", "PART TWO") and title lines set at display size.
    The per-span pass judges each line alone and loses some of those lines to checks made
    for body text -- a title ending in "?", a second line that begins lowercase, a title
    repeated as a running head, a line aligned with the one above it. Here the block is
    read as a whole:

    * the block is the PREFIX of a page: units from the top of the page while each is a
      heading or a display line (``_DISPLAY_TITLE_FONT_RATIO`` and above, at most
      ``_HEADING_MAX_LINES`` lines and ``_DISPLAY_TITLE_MAX_WORDS`` words). The first
      unit of any other kind -- body text, a list, a caption -- ends it, so nothing in
      the middle of a page is touched;
    * inside the block, consecutive display units are lines of one title when
      ``_units_continue_one_title`` says so (same size, title leading, no sentence end
      or TOC row above);
    * a group that holds at least one body unit becomes ONE heading, if it stays within
      ``_HEADING_MAX_LINES`` lines and is made of words (``_text_is_title_words``). A
      group of headings only is left exactly as the importer made it.

    No title word, no "Chapter" literal and no list of section names is read. A page
    whose title carries no display size or does not open the page yields no signal, and
    stays as imported (Constitution VII, "no source signal, no repair").
    """
    body_font_size = layout_profile.body_font_size
    if not units or not body_font_size:
        return units
    spans_by_origin: dict[int, list[PdfTextSpan]] = {}
    for span in ordered_spans:
        spans_by_origin.setdefault(_span_origin_index(span), []).append(span)
    placements = [_unit_placement(unit, spans_by_origin) for unit in units]

    replacements: dict[int, tuple[int, ParagraphUnit]] = {}
    index = 0
    count = len(units)
    while index < count:
        placement = placements[index]
        previous_placement = placements[index - 1] if index else None
        opens_page = placement is not None and (
            previous_placement is None or previous_placement.page_number != placement.page_number
        )
        if not opens_page:
            index += 1
            continue
        assert placement is not None
        block: list[int] = []
        cursor = index
        while cursor < count:
            cursor_placement = placements[cursor]
            if cursor_placement is None or cursor_placement.page_number != placement.page_number:
                break
            unit = units[cursor]
            if not (
                unit.role == "heading"
                or _unit_is_display_line(unit, body_font_size=body_font_size)
            ):
                break
            block.append(cursor)
            cursor += 1
        group: list[int] = []
        for member in block + [-1]:
            if member >= 0 and group:
                last = group[-1]
                last_placement = placements[last]
                member_placement = placements[member]
                assert last_placement is not None and member_placement is not None
                if _unit_is_display_line(
                    units[last], body_font_size=body_font_size
                ) and _unit_is_display_line(units[member], body_font_size=body_font_size) and (
                    _units_continue_one_title(
                        units[last], last_placement, units[member], member_placement
                    )
                    or _unit_numbers_title(
                        units[last], units[member], spans_by_origin, layout_profile=layout_profile
                    )
                ):
                    group.append(member)
                    continue
            if group:
                group_units = [units[item] for item in group]
                line_count = sum(len(unit.origin_raw_indexes or []) for unit in group_units)
                text = " ".join((unit.text or "").strip() for unit in group_units)
                if (
                    any(unit.role != "heading" for unit in group_units)
                    and all(
                        _unit_is_display_line(unit, body_font_size=body_font_size)
                        for unit in group_units
                    )
                    and line_count <= _HEADING_MAX_LINES
                    and len(_words(text)) <= _DISPLAY_TITLE_MAX_WORDS
                    and _text_is_title_words(text)
                ):
                    replacements[group[0]] = (
                        group[-1],
                        _display_title_unit(group_units, body_font_size=body_font_size),
                    )
            group = [member] if member >= 0 else []
        index = max(cursor, index + 1)

    if not replacements:
        return units
    result: list[ParagraphUnit] = []
    index = 0
    while index < count:
        replacement = replacements.get(index)
        if replacement is None:
            result.append(units[index])
            index += 1
            continue
        last_index, unit = replacement
        result.append(unit)
        index = last_index + 1
    return result


def _looks_like_chapter_heading(
    span: PdfTextSpan, *, layout_profile: _PdfHeadingLayoutProfile
) -> bool:
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
    * The literal match alone is not sufficient: the line must also carry a
      corroborating heading-typography signal (prominent font or bold emphasis),
      consistent with ``_looks_like_numbered_section_heading``. A plain body-font,
      non-emphasized line that merely reads "Chapter N" is left as body ("no
      source signal, no repair").
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
    if len(_words(text)) > 14:
        return False
    return _span_has_heading_typography_signal(span, layout_profile=layout_profile)


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


# A line-wrap hyphen: the previous PDF line ended mid-token with a hyphen
# ("…life-\nthreatening…", "…про-\nцентов…"), so the two halves belong to one token
# and the erroneous joining space between them must be removed. Only a genuine
# in-token hyphen qualifies — the run immediately before the hyphen must be an
# alphabetic word (latin or cyrillic, generalized via ``[^\W\d_]``), the hyphen must
# be the very last character of the line, and the continuation must start with a
# lowercase letter. This deliberately excludes:
#   * number ranges ("1603-\n1714"): a digit, not a letter, precedes the hyphen and
#     the continuation starts with a digit;
#   * spaced compound dashes ("foo -\nbar"): a space, not a letter, precedes it;
#   * list-item / heading / new-sentence starts: the continuation is uppercase or a
#     marker, so it is never treated as a wrapped continuation;
#   * en/em dashes: only U+002D hyphen-minus, U+00AD soft hyphen and U+2010 hyphen
#     count; the U+2013 en dash / U+2014 em dash used for ranges and asides never match.
#
# Whether the hyphen ITSELF is dropped ("про-"+"центов" → "процентов") or KEPT
# ("life-"+"threatening" → "life-threatening") is decided by corpus evidence, not
# by the raw pattern: epub-derived PDFs wrap genuine hyphenated compounds at their
# hyphen far more often than they soft-hyphenate a single word, so unconditionally
# dropping the hyphen would corrupt real compounds. See
# ``_SoftWrapDehyphenationEvidence``.
_SOFT_WRAP_HYPHEN_CHARS = "-­‐"  # hyphen-minus, soft hyphen, hyphen
_SOFT_WRAP_HYPHEN_TAIL_PATTERN = re.compile(
    rf"([^\W\d_]+)[{_SOFT_WRAP_HYPHEN_CHARS}]\Z", re.UNICODE
)
_SOFT_WRAP_HEAD_WORD_PATTERN = re.compile(r"\A([^\W\d_]+)", re.UNICODE)
_SOLID_WORD_SCAN_PATTERN = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
_HYPHENATED_WORD_SCAN_PATTERN = re.compile(
    rf"[^\W\d_]+[{_SOFT_WRAP_HYPHEN_CHARS}][^\W\d_]+", re.UNICODE
)


@dataclass(frozen=True)
class _SoftWrapDehyphenationEvidence:
    """Document-level evidence used to decide, per wrap, whether a line-break hyphen
    is a *soft* hyphen (inserted only to wrap a single word — drop it) or a *hard*
    compound hyphen (part of the word — keep it).

    ``solid_forms`` are whole alphabetic tokens attested anywhere in the document;
    ``hyphenated_forms`` are whole ``word-word`` tokens attested anywhere. A wrap
    ``tail-`` + ``head`` is de-hyphenated only when the fused solid form
    (``tailhead``) is attested elsewhere AND the hyphenated form (``tail-head``) is
    NOT — i.e. there is positive evidence the joined word is a real single word and
    no evidence it is a real compound. Absent positive soft-wrap evidence the hyphen
    is preserved (under-merge is safer than corrupting a compound). This mirrors the
    importer's standing anti-over-merge discipline.
    """

    solid_forms: frozenset[str]
    hyphenated_forms: frozenset[str]

    def should_drop_hyphen(self, tail_word: str, head_word: str) -> bool:
        hyphenated = f"{tail_word}-{head_word}".lower()
        if hyphenated in self.hyphenated_forms:
            return False
        return f"{tail_word}{head_word}".lower() in self.solid_forms


def _build_soft_wrap_dehyphenation_evidence(
    spans: list[PdfTextSpan],
) -> _SoftWrapDehyphenationEvidence:
    solid_forms: set[str] = set()
    hyphenated_forms: set[str] = set()
    for span in spans:
        lowered = _normalize_text(span.text).lower()
        if not lowered:
            continue
        solid_forms.update(_SOLID_WORD_SCAN_PATTERN.findall(lowered))
        hyphenated_forms.update(
            match.replace("­", "-").replace("‐", "-")
            for match in _HYPHENATED_WORD_SCAN_PATTERN.findall(lowered)
        )
    return _SoftWrapDehyphenationEvidence(
        solid_forms=frozenset(solid_forms),
        hyphenated_forms=frozenset(hyphenated_forms),
    )


def _soft_wrap_hyphen_boundary(previous_text: str, next_text: str) -> tuple[str, str] | None:
    """Return ``(tail_word, head_word)`` when ``previous_text`` ends with an in-token
    line-wrap hyphen and ``next_text`` begins with a lowercase word; else ``None``."""
    if not previous_text or not next_text:
        return None
    first_char = next_text[0]
    if not (first_char.isalpha() and first_char.islower()):
        return None
    tail = _SOFT_WRAP_HYPHEN_TAIL_PATTERN.search(previous_text)
    if tail is None:
        return None
    head = _SOFT_WRAP_HEAD_WORD_PATTERN.match(next_text)
    if head is None:
        return None
    return tail.group(1), head.group(1)


StyleRun = tuple[str, bool, bool]


def _join_soft_wrapped_run_pieces(
    piece_runs: list[list[StyleRun]],
    *,
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None = None,
) -> list[StyleRun]:
    """Join per-piece style-run sequences with a single space, except across a
    line-wrap hyphen — the single de-hyphenation decision, shared by both the plain
    ``paragraph.text`` build and the per-run emphasis emission.

    At a wrap boundary (previous ends ``word-``, next starts a lowercase word) the
    erroneous joining space is always removed. The hyphen itself is dropped only when
    ``dehyphenation_evidence`` confirms a soft wrap ("multi-"+"faceted" →
    "multifaceted"); otherwise it is kept ("life-"+"threatening" → "life-threatening").
    Concatenating the returned run texts yields exactly the joined paragraph string.
    """
    result: list[StyleRun] = []
    joined_text = ""
    for runs in piece_runs:
        piece_text = "".join(text for text, _, _ in runs)
        if not piece_text:
            continue
        if not result:
            result.extend(runs)
            joined_text = piece_text
            continue
        boundary = _soft_wrap_hyphen_boundary(joined_text, piece_text)
        if boundary is None:
            result.append((" ", False, False))
            result.extend(runs)
            joined_text = f"{joined_text} {piece_text}"
            continue
        tail_word, head_word = boundary
        if dehyphenation_evidence is not None and dehyphenation_evidence.should_drop_hyphen(
            tail_word, head_word
        ):
            _drop_trailing_char_from_runs(result)
            result.extend(runs)
            joined_text = f"{joined_text[:-1]}{piece_text}"
        else:
            result.extend(runs)
            joined_text = f"{joined_text}{piece_text}"
    return result


def _drop_trailing_char_from_runs(runs: list[StyleRun]) -> None:
    """Remove the final character (a soft-wrap hyphen) from the last run in place."""
    while runs:
        text, is_bold, is_italic = runs[-1]
        if text:
            trimmed = text[:-1]
            if trimmed:
                runs[-1] = (trimmed, is_bold, is_italic)
            else:
                runs.pop()
            return
        runs.pop()


def _join_soft_wrapped_text_pieces(
    pieces: list[str],
    *,
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None = None,
) -> str:
    """Plain-text view of :func:`_join_soft_wrapped_run_pieces` — one de-hyphenation
    implementation shared with the per-run emphasis emission."""
    piece_runs = [[(piece, False, False)] for piece in pieces if piece]
    joined = _join_soft_wrapped_run_pieces(
        piece_runs, dehyphenation_evidence=dehyphenation_evidence
    )
    return "".join(text for text, _, _ in joined)


def _span_style_runs(span: PdfTextSpan) -> list[StyleRun]:
    """Return the span's character-level emphasis runs, falling back to a single
    line-level run when no per-character data is available or when the runs would not
    reconstruct the normalized span text (mapping-loaded spans, malformed runs)."""
    normalized = _normalize_text(span.text)
    runs: tuple[StyleRun, ...] = span.runs
    if runs and "".join(text for text, _, _ in runs) == normalized:
        return list(runs)
    return [(normalized, bool(span.is_bold), bool(span.is_italic))]


def _unit_style_runs(unit: ParagraphUnit) -> list[StyleRun]:
    """Emphasis runs for an already-built unit, used when fusing continuation units.
    Falls back to a single unit-level run when the stored runs cannot reconstruct the
    unit text."""
    stripped = (unit.text or "").strip()
    runs: list[StyleRun] = list(unit.pdf_emphasis_runs)
    if runs and "".join(text for text, _, _ in runs) == stripped:
        return runs
    return [(stripped, bool(unit.is_bold), bool(unit.is_italic))]


def _glue_superscript_marker_to_runs(runs: list[StyleRun], superscript_text: str) -> None:
    """Strip the trailing whitespace of the last run and append the footnote marker as
    a plain superscript run, mirroring ``f"{previous.rstrip()}{superscript}"``."""
    if runs:
        text, is_bold, is_italic = runs[-1]
        runs[-1] = (text.rstrip(), is_bold, is_italic)
    runs.append((superscript_text, False, False))


def _space_joined_style_runs(spans: list[PdfTextSpan]) -> list[StyleRun]:
    """Emphasis runs for spans concatenated with a single space, matching the
    ``" ".join(_normalize_text(...))`` text used by heading/list builders."""
    result: list[StyleRun] = []
    for span in spans:
        runs = _span_style_runs(span)
        if not "".join(text for text, _, _ in runs):
            continue
        if result:
            result.append((" ", False, False))
        result.extend(runs)
    return result


# A body line that ends here has finished its sentence -- or introduces what follows (a colon,
# a semicolon), which is how a real numbered list is announced.
_BODY_LINE_CLOSED_CHARS = ".!?…:;"


def _unit_ordered_list_number(unit: ParagraphUnit) -> int | None:
    match = _ORDERED_LIST_PATTERN.match((unit.text or "").strip())
    return int(match.group("marker")) if match else None


def _body_text_is_closed(text: str) -> bool:
    stripped = text.rstrip()
    while stripped and (stripped[-1] in _ENTRY_TRAILING_CLOSER_CHARS or stripped[-1].isspace()):
        stripped = stripped[:-1]
    return not stripped or stripped[-1] in _BODY_LINE_CLOSED_CHARS


def _is_numbered_body_continuation(
    head: ParagraphUnit,
    tail: ParagraphUnit,
    *,
    spans_by_origin: dict[int, list[PdfTextSpan]],
    layout_profile: _PdfHeadingLayoutProfile,
    last_list_item_number: int | None,
) -> bool:
    """Spec 065 FR-009: a list item that opens with a number and a period or bracket ("1815. He
    was said", "2011) argued") right after a body paragraph that broke mid-sentence continues
    that paragraph; the line break fell before a number.

    The form, all of it required -- the geometry the spec 064 notes-join reads, in the body:
      * the paragraph does not close: its last character, past closing quotes, brackets and
        superscript references, is none of . ! ? ... : ;
      * its last line ran out of room: the number would not have fit before the body column's
        right edge (`_entry_line_ran_out_of_room`);
      * the item's first line is the next line: on the same page with less than a blank line
        above it, or at the top of the next page (`_entry_lines_are_consecutive`);
      * both lines are set in one size;
      * the number is not the next one of a running list: not the number of the last list
        item since the last heading plus one.
    A real numbered list is announced by a line that closes (usually with a colon) or that
    ends short of the margin, and its later items follow the item before them in number.
    Notes and reference sections are left to the notes-join: there an entry number after an
    address that ran to the margin opens the next entry."""
    if head.role != "body" or head.structural_role != "body" or tail.role != "list":
        return False
    if head.is_pdf_table_cell or tail.is_pdf_table_cell:
        return False
    number = _unit_ordered_list_number(tail)
    if number is None:
        return False
    if last_list_item_number is not None and number == last_list_item_number + 1:
        return False
    if _body_text_is_closed(head.text or ""):
        return False
    last_line = _unit_line_span(head, -1, spans_by_origin)
    first_line = _unit_line_span(tail, 0, spans_by_origin)
    if last_line is None or first_line is None:
        return False
    if not _font_sizes_match(_span_font_size(last_line), _span_font_size(first_line)):
        return False
    return _entry_lines_are_consecutive(last_line, first_line) and _entry_line_ran_out_of_room(
        last_line, _normalize_text(first_line.text), layout_profile=layout_profile
    )


def _join_numbered_body_continuations(
    units: list[ParagraphUnit],
    ordered_spans: list[PdfTextSpan],
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None = None,
) -> list[ParagraphUnit]:
    """Spec 065 FR-009: join a body paragraph and the "list item" its own sentence ran into.
    See `_is_numbered_body_continuation` for the form."""
    in_back_matter = _back_matter_entry_region_flags(units)
    spans_by_origin: dict[int, list[PdfTextSpan]] = {}
    for span in ordered_spans:
        spans_by_origin.setdefault(_span_origin_index(span), []).append(span)
    result: list[ParagraphUnit] = []
    last_list_item_number: int | None = None
    for unit, in_region in zip(units, in_back_matter):
        if unit.role == "heading":
            last_list_item_number = None
        if (
            not in_region
            and result
            and _is_numbered_body_continuation(
                result[-1],
                unit,
                spans_by_origin=spans_by_origin,
                layout_profile=layout_profile,
                last_list_item_number=last_list_item_number,
            )
        ):
            result[-1] = replace(
                _merge_torn_back_matter_entry(
                    result[-1], unit, dehyphenation_evidence=dehyphenation_evidence
                ),
                boundary_rationale="merged_numbered_body_continuation",
            )
            continue
        if unit.role == "list":
            last_list_item_number = _unit_ordered_list_number(unit)
        result.append(unit)
    return result


_PAGE_BODY_TEXT_MIN_LINES = 3
_PAGE_BODY_TEXT_MIN_WORDS = 7


def _pages_carrying_body_text(
    ordered_spans: list[PdfTextSpan],
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    repeated_furniture_keys: set[tuple[str, str]],
) -> frozenset[int]:
    """Pages with running text on them: at least three content lines set at the body size
    (`_font_sizes_match`) with at least seven words each."""
    body_font_size = layout_profile.body_font_size
    if not body_font_size:
        return frozenset()
    lines_by_page: dict[int, int] = {}
    for span in ordered_spans:
        if _span_furniture_key(span) in repeated_furniture_keys or _looks_like_page_number(span):
            continue
        if not _font_sizes_match(_span_font_size(span), body_font_size):
            continue
        if len(_words(_normalize_text(span.text))) < _PAGE_BODY_TEXT_MIN_WORDS:
            continue
        lines_by_page[span.page_number] = lines_by_page.get(span.page_number, 0) + 1
    return frozenset(
        page for page, count in lines_by_page.items() if count >= _PAGE_BODY_TEXT_MIN_LINES
    )


def _page_edge_lines(
    ordered_spans: list[PdfTextSpan],
    *,
    repeated_furniture_keys: set[tuple[str, str]],
) -> tuple[dict[int, PdfTextSpan], dict[int, PdfTextSpan]]:
    """The first and the last content line of every page, in reading order (page furniture and
    page numbers are not content)."""
    first_by_page: dict[int, PdfTextSpan] = {}
    last_by_page: dict[int, PdfTextSpan] = {}
    for span in ordered_spans:
        if _span_furniture_key(span) in repeated_furniture_keys or _looks_like_page_number(span):
            continue
        first_by_page.setdefault(span.page_number, span)
        last_by_page[span.page_number] = span
    return first_by_page, last_by_page


_PAGE_TORN_BODY_RATIONALE = "merged_page_torn_body_continuation"
_PAGE_TORN_NOTES_RUN_RATIONALE = "merged_page_torn_notes_run_continuation"


def _halves_continue_an_in_body_notes_run(
    head: ParagraphUnit,
    tail: ParagraphUnit,
    last_line: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None,
) -> bool:
    """Spec 068 FR-003 (X-3): the two halves are one run of numbered notes left in the body,
    set apart from the running text in a size of its own.

    A chapter's notes set at its end in a smaller size fill pages on which no line is set at
    the body size, so the running-text condition of the page-tear join never holds there. This
    is the alternative to it, read off the halves alone (Constitution VII: no word list):
      * the torn line is set SMALLER than the body (`_font_sizes_match` refuses the body size);
        the caller has already required both lines to share that size;
      * the second half does not open with a note number (`opens_with_note_number`: a 1-3
        digit token without a full stop before an entry opener) -- that is the next note,
        not the rest of this one;
      * the two halves joined read as a notes run by the spec 067 FR-001 form
        (`is_notes_run_paragraph`: a chain of numbered entries counting n, n+1, ... carrying
        citation anchors, or one anchored entry behind a label)."""
    body_font_size = layout_profile.body_font_size
    size = _span_font_size(last_line)
    if body_font_size is None or size is None:
        return False
    if size >= body_font_size or _font_sizes_match(size, body_font_size):
        return False
    if opens_with_note_number(tail.text or ""):
        return False
    joined = _merge_torn_back_matter_entry(head, tail, dehyphenation_evidence=dehyphenation_evidence)
    return is_notes_run_paragraph(joined.text or "")


def _page_torn_continuation_rationale(
    head: ParagraphUnit,
    tail: ParagraphUnit,
    *,
    spans_by_origin: dict[int, list[PdfTextSpan]],
    layout_profile: _PdfHeadingLayoutProfile,
    first_line_by_page: dict[int, PdfTextSpan],
    last_line_by_page: dict[int, PdfTextSpan],
    body_text_pages: frozenset[int],
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None = None,
) -> str | None:
    """Spec 067 FR-005 (I-1): the second half of a body paragraph that a page break tore off.
    Returns the boundary rationale of the join, or None when `tail` is not that half.

    The body counterpart of the notes-join geometry (spec 064 R-7), read across one page
    break. All of it is required:
      * both units are body, neither is a table cell; headings, list items, captions and
        TOC entries are never joined, and notes / reference sections are left to the
        notes-join (the caller skips them);
      * the paragraph does not close (`_body_text_is_closed`: past closing quotes, brackets
        and superscript references its last character is none of . ! ? ... : ;);
      * its last line is the last content line of its page, and the next unit's first line
        is the first content line of the NEXT page;
      * the two lines are set in one size (`_font_sizes_match`);
      * the last line ran out of room: the next line's first word would not have fit before
        the body column's right edge (`_entry_line_ran_out_of_room`);
      * both pages carry running text -- at least three lines at the body size with at least
        seven words each -- so the end of a list of notes, an index column or a caption page
        does not read as prose; OR (spec 068 FR-003) the two halves continue one run of
        numbered notes set smaller than the body (`_halves_continue_an_in_body_notes_run`),
        whatever the pages carry.
    What the second half of running text begins with is not read: a capital, a digit, a quote
    or a bracket opens the continuation as often as a lowercase letter does ("...such as the" +
    "Harbour Board", "...in" + "1702, said", "...considered you" + "'seaworthy'").
    Measured on the four corpus PDFs (2026-11-08) against the 87 page-break
    candidates of spec 067's sweep, each read: this rule joins 27, all of them real tears, and
    no false one; two more (Rethinking Money, pp. 12-14) join through the soft-wrap merge once
    the running head between the halves is dropped (FR-007) -- 29 of 32. The notes-run
    alternative (spec 068 FR-003) joins the two chapter-end notes of Money and Sustainability
    set on pages with no line at the body size -- 31 of 32, still no false one. Not joined:
    one bibliography entry inside a references section, which belongs to the notes-join.
    Re-measured 2026-11-12 with spec 078's hanging-indent rule, which changes the note
    paragraphs of Money and Sustainability: the same joins on every book (27 body, 2 notes
    run), the rule on or off."""
    if head.role != "body" or head.structural_role != "body":
        return None
    if tail.role != "body" or tail.structural_role != "body":
        return None
    if head.is_pdf_table_cell or tail.is_pdf_table_cell:
        return None
    if _body_text_is_closed(head.text or ""):
        return None
    last_line = _unit_line_span(head, -1, spans_by_origin)
    first_line = _unit_line_span(tail, 0, spans_by_origin)
    if last_line is None or first_line is None:
        return None
    if first_line.page_number != last_line.page_number + 1:
        return None
    if (
        last_line_by_page.get(last_line.page_number) is not last_line
        or first_line_by_page.get(first_line.page_number) is not first_line
    ):
        return None
    if not _font_sizes_match(_span_font_size(last_line), _span_font_size(first_line)):
        return None
    if not _entry_line_ran_out_of_room(
        last_line, _normalize_text(first_line.text), layout_profile=layout_profile
    ):
        return None
    if last_line.page_number in body_text_pages and first_line.page_number in body_text_pages:
        return _PAGE_TORN_BODY_RATIONALE
    if _halves_continue_an_in_body_notes_run(
        head,
        tail,
        last_line,
        layout_profile=layout_profile,
        dehyphenation_evidence=dehyphenation_evidence,
    ):
        return _PAGE_TORN_NOTES_RUN_RATIONALE
    return None


def _join_page_torn_body_paragraphs(
    units: list[ParagraphUnit],
    ordered_spans: list[PdfTextSpan],
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    repeated_furniture_keys: set[tuple[str, str]],
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None = None,
) -> list[ParagraphUnit]:
    """Spec 067 FR-005: join a body paragraph and its second half across a page break (spec 068
    FR-003: also a run of in-body notes). See `_page_torn_continuation_rationale` for the form."""
    in_back_matter = _back_matter_entry_region_flags(units)
    spans_by_origin: dict[int, list[PdfTextSpan]] = {}
    for span in ordered_spans:
        spans_by_origin.setdefault(_span_origin_index(span), []).append(span)
    first_line_by_page, last_line_by_page = _page_edge_lines(
        ordered_spans, repeated_furniture_keys=repeated_furniture_keys
    )
    body_text_pages = _pages_carrying_body_text(
        ordered_spans,
        layout_profile=layout_profile,
        repeated_furniture_keys=repeated_furniture_keys,
    )
    result: list[ParagraphUnit] = []
    previous_in_region = False
    for unit, in_region in zip(units, in_back_matter):
        rationale = (
            _page_torn_continuation_rationale(
                result[-1],
                unit,
                spans_by_origin=spans_by_origin,
                layout_profile=layout_profile,
                first_line_by_page=first_line_by_page,
                last_line_by_page=last_line_by_page,
                body_text_pages=body_text_pages,
                dehyphenation_evidence=dehyphenation_evidence,
            )
            if not in_region and not previous_in_region and result
            else None
        )
        if rationale is not None:
            result[-1] = replace(
                _merge_torn_back_matter_entry(
                    result[-1], unit, dehyphenation_evidence=dehyphenation_evidence
                ),
                boundary_rationale=rationale,
            )
            continue
        result.append(unit)
        previous_in_region = in_region
    return result


def _paragraph_run_left_x0(pending_spans: list[PdfTextSpan]) -> float | None:
    """Spec 067 FR-006 follow-up: the left edge of the paragraph being built -- the smallest
    x0 among its lines set in the size of its last line. A quotation or a box set apart from
    the body has its own left edge, which the document's body margin does not describe."""
    if not pending_spans:
        return None
    size = _span_font_size(pending_spans[-1])
    edges = [
        float(span.x0)
        for span in pending_spans
        if span.page_number == pending_spans[-1].page_number
        and _font_sizes_match(_span_font_size(span), size)
    ]
    return min(edges) if edges else None


def _can_merge_body_span(
    previous: PdfTextSpan,
    current: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    paragraph_left_x0: float | None = None,
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
    if _opens_body_size_entry_after_small_print(
        previous, current_text, current, layout_profile=layout_profile
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
    # A sentence end followed by a footnote reference ("settled.” ¹¹") is still a sentence end.
    previous_sentence_text = previous_text.rstrip(_SUPERSCRIPT_REFERENCE_TAIL_CHARS)
    if (
        previous_sentence_text
        and current_text
        and previous_sentence_text[-1] in _TERMINAL_SENTENCE_PUNCTUATION
        and _starts_like_new_body_sentence(current_text)
        and _span_line_fill_ratio(previous, layout_profile) < _FULL_LINE_FILL_RATIO
        and (
            _is_near_body_left(current, layout_profile)
            or _is_near_paragraph_left(current, paragraph_left_x0, layout_profile)
        )
    ):
        return False
    return True


def _is_near_paragraph_left(
    span: PdfTextSpan, paragraph_left_x0: float | None, layout_profile: _PdfHeadingLayoutProfile
) -> bool:
    """Spec 067 FR-006 follow-up: the line starts where the paragraph's own lines start
    (`_paragraph_run_left_x0`), within the tolerance `_is_near_body_left` uses for the body
    margin.

    The sentence-end boundary in `_can_merge_body_span` -- the previous line ends a sentence
    (terminal punctuation, optionally followed by a superscript reference: "settled.” ¹¹"),
    ends short (fill < 0.72, `_FULL_LINE_FILL_RATIO`), and the next line starts a new
    sentence at the left edge --
    read that left edge only as the document's BODY margin. A quotation or a box set apart
    from the body has its own margin, so inside it the boundary never fired: Money and
    Sustainability sets its body at x0 5.0 and Box 4.1 at 33.8, and a quotation's last line
    there (a closing quote and a reference) and the box's next sentence survived as two
    paragraphs only by an accident (the line ending in the reference's digits read as a
    contents line) that spec 067 FR-006 removed. The paragraph's
    own edge is the alternative. Measured on the four corpus PDFs (2026-11-08): 38 new
    boundaries, every one read as a paragraph end inside an inset -- The Value of
    Everything p. 207 (1); Creating Wealth pp. 23, 72, 93, 155-156 (13: a dialogue, a list
    of principles, resource entries); Money and Sustainability pp. 9, 54, 57, 73-74, 77, 81,
    91, 105, 134-135 (24, Box 4.1 among them); Rethinking Money none. Headings, levels 1-2,
    superscripts and the symbol multiset unchanged. Re-measured 2026-11-12 with spec 078's
    hanging-indent rule: the same 38 boundaries on the same pages, the rule on or off."""
    if paragraph_left_x0 is None:
        return False
    body_leading = layout_profile.body_leading or layout_profile.body_font_size or 10.0
    return abs(float(span.x0) - paragraph_left_x0) <= body_leading * 0.75


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
        # Spec 078: the indent under a full line that opens with a note number is that
        # entry's hanging indent, not the first-line indent of the next paragraph.
        return not _continues_hanging_numbered_line(
            previous, current, layout_profile=layout_profile
        )
    if layout_profile.body_left_x0 is None or not _is_near_body_left(current, layout_profile):
        return False
    if previous_text[-1] not in _TERMINAL_SENTENCE_PUNCTUATION:
        return False
    first_char = current_text[0]
    return first_char in _OPENING_TEXT_BOUNDARY_CHARS or first_char.isupper()


def _continues_hanging_numbered_line(
    previous: PdfTextSpan,
    current: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    """Spec 078: `current` is the wrapped line of a numbered entry set with a HANGING indent.

    A note set with a hanging indent puts its number at the margin and every wrapped line
    further right; the first-line-indent branch above reads that step as a new paragraph and
    tears each such note after its first line. All of it is required:
      * `previous` opens with a note number (`opens_with_note_number`, the spec 068 form: a
        1-3 digit token without a full stop, whitespace, then a capital or an entry opener);
      * `current` does not -- an indented line that opens with a number is the next entry;
      * both lines are set in one size (`_font_sizes_match`);
      * both lines are set SMALLER than the body (`_is_set_below_body_size`): positive
        evidence that they are not running text. Joined, body text set like a numbered
        instruction ("1 Disconnect ...", an indented paragraph, "2 Verify ...") read as a run
        of notes and left the narration (spec 078, Codex review round 1, P1). Notes set at the
        body size keep the old split: a missed join, never body text excluded;
      * `previous` is a FULL line: it reaches `_FULL_LINE_FILL_RATIO` of the body column, the
        share the body and list merges already read as a line that did not end short. A line
        wraps only when it is full, so a numbered line that ends short -- a one-line list item,
        a one-line note -- is never continued by the indented line under it, which stays the
        first line of the next paragraph.
    The step itself is the one the branch above measured (at least 0.45 of the body leading);
    the vertical-gap limit of `_can_merge_body_span` still applies after this. Only lines are
    joined: no text is dropped or rewritten.

    Measured on the four corpus PDFs (2026-11-12): fires 62 times, all in Money and
    Sustainability's chapter-end notes (number at x0 5.0, wrapped lines at 27.3, one at 33.8;
    10.8 pt against a 14.5 pt body), every one the second line of the note above it; the
    numbered lines fill 0.867-1.0 of the column, nine of them end a sentence. Not one line of
    Rethinking Money, The Value of Everything or Creating Wealth has this form, at any size."""
    previous_text = _normalize_text(previous.text)
    current_text = _normalize_text(current.text)
    if not opens_with_note_number(previous_text) or opens_with_note_number(current_text):
        return False
    previous_size, current_size = _span_font_size(previous), _span_font_size(current)
    if not _font_sizes_match(previous_size, current_size):
        return False
    if not (
        _is_set_below_body_size(previous_size, layout_profile)
        and _is_set_below_body_size(current_size, layout_profile)
    ):
        return False
    return _span_line_fill_ratio(previous, layout_profile) >= _FULL_LINE_FILL_RATIO


def _opens_body_size_entry_after_small_print(
    previous: PdfTextSpan,
    current_text: str,
    current: PdfTextSpan,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    """Spec 078 (Codex review round 2, P1): a line set at the body size that opens with a note
    number does not continue a paragraph whose last line is set below the body size -- it
    starts a paragraph of its own. Without this, small print joined by the hanging-indent rule
    ("1 Disconnect ...", its indented line "... (2024).") took the next numbered body-size line
    in through the ordinary merge, read as a run of notes and left the narration with it.
    Same size test as the rule (`_is_set_below_body_size`). Measured on the four corpus PDFs
    (2026-11-13): refuses none of the 22 084 body merges there."""
    return (
        opens_with_note_number(current_text)
        and _is_set_below_body_size(_span_font_size(previous), layout_profile)
        and not _is_set_below_body_size(_span_font_size(current), layout_profile)
    )


def _is_set_below_body_size(size: float | None, layout_profile: _PdfHeadingLayoutProfile) -> bool:
    """Spec 078: the size is known, the body size is known, and the size is smaller than the
    body by more than the importer's size tolerance (`_font_sizes_match`) -- the test the
    spec 068 notes-run page join already makes (`_halves_continue_an_in_body_notes_run`)."""
    body_font_size = layout_profile.body_font_size
    if size is None or body_font_size is None:
        return False
    return size < body_font_size and not _font_sizes_match(size, body_font_size)


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
        or _span_line_fill_ratio(previous, layout_profile) >= _FULL_LINE_FILL_RATIO
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
    if not _can_end_with_superscript_marker(text):
        return False
    body_leading = layout_profile.body_leading or body_font_size * 1.2
    if float(marker.x0) < float(text_span.x1) - body_leading * 0.2:
        return False
    if float(marker.top) > float(text_span.bottom) or float(marker.bottom) < float(text_span.top):
        return False
    return float(marker.bottom) <= float(text_span.bottom) - marker_font_size * 0.5


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


# --------------------------------------------------------------------------------------
# Spec 063 FR-008 / FR-009: a heading the per-span classifier tore in two, or a chapter
# title it left as body. Both rules key on typesetting only -- face, size, the vertical gap
# between lines, position on the page, line count -- never on the words of the title
# (Constitution VII).
#
# The line bound is the corpus' own maximum: the longest heading in the four corpus books is
# a three-line chapter title (Rethinking Money ch. 5, set in capitals and ending in a spaced
# ellipsis, measured 2026-11-07). A longer run is a display
# paragraph -- a pull quote, a title page -- and is left alone.
_HEADING_MAX_LINES = 3
# Two lines of one heading are set at the heading's own leading: the white space between
# them is a fraction of the line's size. Measured on the corpus' torn titles 2026-11-07:
# 0.04-0.43 x font size (RM ch. 5 and its bold sub-heads, CW chs. 2, 9-11, the Money
# advertisement page). Lines a full line apart are separate items -- a TOC (Money p. 2:
# 1.0) or an author above a title (the VoE title page: 1.27).
_HEADING_LINE_MAX_GAP_FONT_RATIO = 0.5
# A display title is set well above body size. 1.35 is the importer's own h2 tier
# (``_infer_font_heading_level``); the h3 tier (1.12) is where body-sized bold lead-ins and
# small caps live, which FR-009 must not touch.
_DISPLAY_TITLE_FONT_RATIO = 1.35
_DISPLAY_TITLE_MAX_WORDS = 14


def _span_font_size(span: PdfTextSpan) -> float | None:
    if isinstance(span.font_size, (int, float)) and span.font_size > 0:
        return float(span.font_size)
    return None


def _font_sizes_match(first: float | None, second: float | None) -> bool:
    """The size tolerance ``_can_merge_heading_span`` already uses for heading lines."""
    if not first or not second:
        return False
    smaller, larger = min(first, second), max(first, second)
    return larger - smaller <= max(0.5, smaller * 0.1)


def _spans_share_heading_face(previous: PdfTextSpan, current: PdfTextSpan) -> bool:
    """Same typeface, weight and slant -- the style a heading's lines share.

    The font name is the face as the PDF names it; when either side carries none (spans
    rebuilt from JSON), weight and slant are all that is left to compare.
    """
    if previous.is_bold != current.is_bold or previous.is_italic != current.is_italic:
        return False
    if previous.font_name and current.font_name:
        return previous.font_name == current.font_name
    return True


def _heading_line_gap_is_tight(previous: PdfTextSpan, current: PdfTextSpan) -> bool:
    if previous.page_number != current.page_number:
        return False
    font_size = max(_span_font_size(previous) or 0.0, _span_font_size(current) or 0.0) or 10.0
    gap = float(current.top) - float(previous.bottom)
    return gap <= font_size * _HEADING_LINE_MAX_GAP_FONT_RATIO


def _span_is_fully_bold(span: PdfTextSpan) -> bool:
    if not span.is_bold:
        return False
    return all(is_bold for text, is_bold, _ in span.runs if text.strip())


def _span_is_set_above_body(span: PdfTextSpan, *, layout_profile: _PdfHeadingLayoutProfile) -> bool:
    body_font_size = layout_profile.body_font_size
    font_size = _span_font_size(span)
    return bool(
        body_font_size and font_size and font_size / body_font_size >= _HEADING_PROMINENT_FONT_RATIO
    )


def _can_continue_heading_with_line(
    pending_heading_spans: list[PdfTextSpan],
    span: PdfTextSpan,
    *,
    next_span: PdfTextSpan | None,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    """Spec 063 FR-008: is this body-classified line the last line of the pending heading?

    All of these must hold, and none of them reads the words:

    * the line may join the heading under the importer's own heading-line rule
      (``_can_merge_heading_span``: same page, neither side a TOC row, the heading line
      above does not end a sentence, same size);
    * it is set in the heading's face (same font, weight and slant), and that face is a
      heading face on its own: bold throughout, or a size above body. A plain body line,
      or a body line with one bold word, never qualifies;
    * the white space above it is at most ``_HEADING_LINE_MAX_GAP_FONT_RATIO`` of its size;
    * it is the heading's LAST line: the white space below it is larger than the white
      space above it (a heading is set off from what follows), and the next line is not
      another line in the same face and size that could still belong to the same block.
      A bold body paragraph under a bold heading runs on for several lines and stays body;
    * the heading stays within ``_HEADING_MAX_LINES``.
    """
    if not pending_heading_spans or len(pending_heading_spans) >= _HEADING_MAX_LINES:
        return False
    previous = pending_heading_spans[-1]
    if not _can_merge_heading_span(previous, span):
        return False
    if not _spans_share_heading_face(previous, span):
        return False
    if not (
        _span_is_fully_bold(span) or _span_is_set_above_body(span, layout_profile=layout_profile)
    ):
        return False
    if not _heading_line_gap_is_tight(previous, span):
        return False
    if next_span is not None and next_span.page_number == span.page_number:
        gap_above = float(span.top) - float(previous.bottom)
        gap_below = float(next_span.top) - float(span.bottom)
        if gap_below <= gap_above:
            return False
        if (
            _spans_share_heading_face(span, next_span)
            and _font_sizes_match(_span_font_size(span), _span_font_size(next_span))
            and _can_merge_heading_span(span, next_span)
        ):
            return False
    return True



def _paragraph_from_body_spans(
    spans: list[PdfTextSpan],
    *,
    inline_markers: dict[int, list[str]] | None = None,
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None = None,
) -> ParagraphUnit:
    inline_markers = inline_markers or {}
    piece_runs: list[list[StyleRun]] = []
    for index, span in enumerate(spans):
        piece_runs.append(_span_style_runs(span))
        for marker in inline_markers.get(index, []):
            # A marker that re-attaches to the END of a completed sentence (the
            # preceding piece ends with terminal punctuation) is a footnote
            # reference for that sentence: render it as a trailing Unicode
            # superscript glued directly to the sentence (no separating space)
            # so the sentence body stays byte-identical and the marker reads as a
            # footnote superscript rather than a stray digit. A marker that
            # interrupts a sentence (preceding half not terminated) keeps its
            # original inline, space-separated form so the prose flows across it.
            #
            # Spec 065 FR-007: a clause comma or a closing ’ is where a reference
            # is welded as much as a full stop is ("capitalism,⁵ the examples");
            # the extractor lifts such a marker off the line end by the same
            # anchor set, so it is glued by that set too, not left as "capitalism,
            # 5 the examples" -- a number in the middle of the sentence.
            previous_runs = piece_runs[-1] if piece_runs else []
            previous_piece = "".join(text for text, _, _ in previous_runs)
            if (
                previous_piece
                and (
                    previous_piece[-1] in _TERMINAL_SENTENCE_PUNCTUATION
                    or previous_piece[-1] in _SUPERSCRIPT_MARKER_ANCHOR_CLOSERS
                )
                and _SUPERSCRIPT_MARKER_DIGITS_PATTERN.match(marker)
            ):
                _glue_superscript_marker_to_runs(
                    previous_runs, _to_superscript_digits(marker)
                )
            else:
                piece_runs.append([(marker, False, False)])
    joined_runs = _join_soft_wrapped_run_pieces(
        piece_runs, dehyphenation_evidence=dehyphenation_evidence
    )
    text = "".join(run_text for run_text, _, _ in joined_runs)
    first = spans[0]
    return ParagraphUnit(
        text=text,
        role="body",
        structural_role="body",
        role_confidence="heuristic",
        is_bold=all(span.is_bold for span in spans),
        is_italic=all(span.is_italic for span in spans),
        font_size_pt=_median_font_size(spans),
        origin_raw_indexes=[_span_origin_index(span) for span in spans],
        origin_raw_texts=[_normalize_text(span.text) for span in spans],
        pdf_emphasis_runs=joined_runs,
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
        heading_level=heading_level,
        heading_source="pdf_text_layer",
        list_level=0,
        is_bold=all(span.is_bold for span in spans),
        is_italic=all(span.is_italic for span in spans),
        font_size_pt=_median_font_size(spans),
        origin_raw_indexes=[_span_origin_index(span) for span in spans],
        origin_raw_texts=[_normalize_text(span.text) for span in spans],
        pdf_emphasis_runs=_space_joined_style_runs(spans),
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
        heading_level=None,
        heading_source=None,
        list_kind="ordered" if _ORDERED_LIST_PATTERN.match(_normalize_text(first.text)) else "bullet",
        list_level=0,
        is_bold=all(span.is_bold for span in spans),
        is_italic=all(span.is_italic for span in spans),
        font_size_pt=_median_font_size(spans),
        origin_raw_indexes=[_span_origin_index(span) for span in spans],
        origin_raw_texts=[_normalize_text(span.text) for span in spans],
        pdf_emphasis_runs=_space_joined_style_runs(spans),
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
        heading_level=heading_level,
        heading_source="pdf_text_layer" if heading_level is not None else None,
        list_kind=list_kind,
        list_level=0,
        is_bold=span.is_bold,
        is_italic=span.is_italic,
        font_size_pt=span.font_size,
        origin_raw_indexes=[_span_origin_index(span)],
        origin_raw_texts=[text],
        pdf_emphasis_runs=_span_style_runs(span),
        layout_origin="pdf_text_layer",
        boundary_source="pdf_text_layer",
        boundary_confidence="heuristic",
        source_index=_span_origin_index(span),
    )


def _infer_heading_level(span: PdfTextSpan, *, median_font_size: float | None) -> int:
    level = _infer_font_heading_level(span, median_font_size=median_font_size)
    # A heading that opens with a section ordinal ("5. Обесценивание …" or the
    # nested "2.1. …") is structurally superior to a bare heading set at the
    # same font size, but font-ratio inference collapses both into the same
    # tier. Lift the numbered heading one level so numbered sections outrank
    # their bare same-size siblings (body-font numbered -> h2, body-font bare
    # -> h3). Only the lowest (body-font) tier is lifted, so the larger-font
    # chapter tiers (h1/h2) that carry deliberate structure are never disturbed.
    if level >= 3 and _has_leading_section_ordinal(span):
        return level - 1
    return level


def _infer_font_heading_level(span: PdfTextSpan, *, median_font_size: float | None) -> int:
    if not median_font_size or not span.font_size:
        return 2
    ratio = span.font_size / median_font_size
    if ratio >= 1.8:
        return 1
    if ratio >= 1.35:
        return 2
    return 3


def _has_leading_section_ordinal(span: PdfTextSpan) -> bool:
    return bool(_SECTION_ORDINAL_HEADING_PATTERN.match(_normalize_text(span.text)))


# ----------------------------------------------------------------------------------------
# Spec 064 R-7: an entry of a notes / reference section that the importer split into two
# paragraphs in the middle of a sentence ("1. Both Tony Blair, ... and Chuka" + "Umunna,
# considered ..."; "33. Barba and de Vivo, ..., pp." + "1490-91.") is joined back here.
#
# Why the tear happens: an entry wraps with a hanging indent, and the span-level list/body
# merges only accept a wrapped line that starts lowercase (`_is_soft_wrap_continuation_pair`)
# or that sits at the previous line's indent. A wrap that happens to start on a capitalised
# name, a digit or an opening parenthesis is therefore cut off into a paragraph of its own.
# Downstream the model either translates the whole sentence under the first marker and leaves
# the second empty (delivered as untranslated source, content twice) or translates the tail
# on its own, where it is neither prose nor a citation for the acceptance gate.
#
# Why it lives HERE and not where the regions are resolved (`document/semantic_blocks.py`):
# the evidence that tells a wrapped line from a new entry is geometry -- whether the previous
# line ran out of room and whether a blank line separates them -- and the coordinates stop
# existing the moment the intermediate DOCX is written. The region the importer can see is
# narrower but sufficient: the anchor is the same blessed back-matter title lexicon, read
# through the same partition (`_BACK_MATTER_SECTION_KIND_BY_TITLE`), on a unit that is already
# a heading; the outline bound mirrors `_resolve_reference_region_outline_bound`.
#
# The rule reads form and geometry only, never a word (Constitution VII). A unit is joined to
# the one before it when ALL hold:
#   * both are inside a notes / reference section and both are body or list units (never a
#     heading, caption, TOC row or footnote marker);
#   * the predecessor does not end a sentence: its last character, past closing quotes,
#     brackets and superscript digits, is none of . ! ? ... -- a comma, a colon, a semicolon,
#     a dash, an open quote or parenthesis, a hyphen-broken word or a bare word all leave it
#     open ("(London:" + "Macmillan, 1865)"; "(1848;" + "London: ..."; 48 of the measured
#     joins end so, all of them correct), and so does a locator abbreviation before a number
#     (`_entry_text_ends_sentence`);
#   * the unit does not open a new entry: no leading note number ("12.", "12)", "12 Text"),
#     no bullet, no repeated-author dash run, no author form ("Surname, X." / "Surname,
#     Firstname" within the first four words). Spec 081: the author form and "12 Text" are
#     guesses from wording, and a wrapped line carries them by accident ("Business Review,
#     January 2014.", "27 May 2011."); when the unit's first line sits at the wrap indent of
#     a hanging-indent run on its page (`_entry_line_sits_at_the_hanging_indent`), geometry
#     overrules them. "12." / "12)", bullets and dash runs always open an entry. Measured on
#     the four corpus PDFs (2026-11-13, cached spans): the join makes 486 joins with this and
#     419 without (Rethinking Money 58 / 46, The Value of Everything 362 / 315, Money and
#     Sustainability 7 / 7, Creating Wealth 59 / 51); every one of the 67 added joins was read
#     and is the wrapped line of the entry above it (spec 081);
#   * the predecessor's last line is FULL: the unit's first word, at that line's own average
#     character width, would not have fit before the body column's right edge -- so the line
#     broke because it ran out of room, not because the entry ended;
#   * the unit's first line is the next line: on the same page with less than a blank line
#     (one font size) of white space above it, or at the top of the very next page;
#   * on the same page, the unit's first line does not step back left of a wrapped
#     predecessor's last line (`_entry_continuation_keeps_the_wrap_indent`).
# A line the TOC heuristic flagged (`structural_role == "toc_entry"`, a line that ends in a
# number) is left alone even here: the flag feeds the TOC-region bound downstream
# (`toc_entry_count`), and clearing it is a separate decision (spec 064 Changelog, notes-join).
# The importer does not see images (they are extracted separately and interleaved by the
# PDF->DOCX bridge), so "not across an image" rests on the blank-line test on the same page;
# across a page break it is a measured residual (spec 064 Changelog, notes-join).
# ----------------------------------------------------------------------------------------

_BACK_MATTER_ENTRY_SECTION_KINDS = frozenset(
    {BACK_MATTER_SECTION_NOTES, BACK_MATTER_SECTION_REFERENCES}
)
_BACK_MATTER_ENTRY_ROLES = frozenset({"body", "list"})
_ENTRY_SENTENCE_END_CHARS = ".!?…"
_ENTRY_TRAILING_CLOSER_CHARS = "’”\"')]}»⁰¹²³⁴⁵⁶⁷⁸⁹"
_ENTRY_NOTE_NUMBER_OPENER_PATTERN = re.compile(r"^\d{1,3}(?:[.)](?:\s|$)|\s+[^\W\d_])")
_ENTRY_REPEATED_AUTHOR_DASH_PATTERN = re.compile(r"^[‒–—―-]{2,}")
_ENTRY_AUTHOR_FORM_MAX_NAME_WORDS = 4
# A short lowercase token closed by a period at the very end ("p.", "pp.", "vol."), standing
# after a space or an opening bracket -- the shape of a locator abbreviation.
_ENTRY_LOCATOR_TOKEN_PATTERN = re.compile(r"(?:^|[\s(\[])(?P<token>[^\W\d_]{1,3})\.\Z", re.UNICODE)
_ENTRY_HARD_HYPHEN_TAIL_PATTERN = re.compile(rf"[^\W_][{_SOFT_WRAP_HYPHEN_CHARS}]\Z", re.UNICODE)
# Spec 081: a number closed by a full stop or a bracket -- the explicit form of an entry number,
# as against the "number, then a word" form a wrapped date also has ("27 May 2011.").
_ENTRY_EXPLICIT_NUMBER_PATTERN = re.compile(r"^\d{1,3}[.)](?:\s|$)")
# Spec 081: a hanging indent is a convention of the list, so it is read only where the list
# shows it more than once: the entry under test plus at least one more entry of the same
# unbroken run that begins at the same margin and wraps to the same indent. One step is just
# the pair the line grouping already split; two is the least that makes the edge a REPEATED
# one. Not tuned: every one of the 67 corpus joins it allows sits in a run of 5 to 17 entries
# (2026-11-13), so any minimum from 1 to 5 makes the same joins there (spec 081).
_HANGING_INDENT_MIN_RUN_ENTRIES = 2


def _back_matter_anchor_kind(unit: ParagraphUnit) -> str | None:
    """The back-matter section kind a HEADING unit opens, or None. Exact title match after the
    same normalisation `semantic_blocks._reference_section_title` applies -- never containment."""
    if unit.role != "heading":
        return None
    title = _normalize_structural_text(_unwrap_inline_emphasis(unit.text or "")).lower()
    return _BACK_MATTER_SECTION_KIND_BY_TITLE.get(title)


def _back_matter_entry_region_flags(units: list[ParagraphUnit]) -> list[bool]:
    """Per unit: does it sit inside a notes / reference section?

    A section opens after a heading whose whole text is a notes or reference title and runs
    until the next back-matter title of any kind (an index ends a bibliography), or until the
    outline returns to the title's depth or shallower; a heading with no depth closes it, and
    so does any heading when the title itself has none. The same reading of the outline as
    `semantic_blocks._resolve_reference_region_outline_bound`, cut short where that one needs
    blocks: a bound that comes too early only loses joins, it never makes one."""
    flags = [False] * len(units)
    index = 0
    while index < len(units):
        kind = _back_matter_anchor_kind(units[index])
        if kind not in _BACK_MATTER_ENTRY_SECTION_KINDS:
            index += 1
            continue
        title_level = units[index].heading_level
        end = index + 1
        while end < len(units):
            candidate = units[end]
            if candidate.role == "heading" and (
                _back_matter_anchor_kind(candidate) is not None
                or title_level is None
                or candidate.heading_level is None
                or candidate.heading_level <= title_level
            ):
                break
            end += 1
        for position in range(index + 1, end):
            flags[position] = True
        index = end
    return flags


def _entry_text_ends_sentence(text: str, *, next_text: str = "") -> bool:
    """Does `text` end a sentence? A trailing period that closes a short lowercase token
    ("p.", "pp.", "vol.") right before a line that opens with a digit is a locator waiting for
    its number ("..., pp." + "1490-91."), not the end of a sentence -- the shape of the token and
    of the next line decide it, no list of abbreviations does."""
    stripped = text.rstrip()
    while stripped and (stripped[-1] in _ENTRY_TRAILING_CLOSER_CHARS or stripped[-1].isspace()):
        stripped = stripped[:-1]
    if not stripped or stripped[-1] not in _ENTRY_SENTENCE_END_CHARS:
        return not stripped
    if stripped[-1] == "." and next_text.lstrip()[:1].isdigit():
        locator = _ENTRY_LOCATOR_TOKEN_PATTERN.search(stripped)
        return locator is None or not locator.group("token").islower()
    return True


def _opens_with_author_form(text: str) -> bool:
    """"Surname, X." / "Surname, Firstname" / "Body Corporate, Title": a capitalised name of at
    most four words, a comma, then a capitalised token. A wrapped line that merely contains a
    comma ("Umunna, considered ...", "Blackwell, 2013)") does not have this shape."""
    head, separator, tail = text.partition(",")
    if not separator:
        return False
    words = head.split()
    if not 1 <= len(words) <= _ENTRY_AUTHOR_FORM_MAX_NAME_WORDS:
        return False
    if not (words[0][:1].isalpha() and words[0][:1].isupper()):
        return False
    after = tail.lstrip()
    return bool(after) and after[0].isalpha() and after[0].isupper()


def _text_opens_back_matter_entry(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return True
    return bool(
        _ENTRY_NOTE_NUMBER_OPENER_PATTERN.match(stripped)
        or _BULLET_PATTERN.match(stripped)
        or stripped[0] in "•●"
        or _ENTRY_REPEATED_AUTHOR_DASH_PATTERN.match(stripped)
        or _opens_with_author_form(stripped)
    )


def _unit_line_span(
    unit: ParagraphUnit,
    position: int,
    spans_by_origin: dict[int, list[PdfTextSpan]],
) -> PdfTextSpan | None:
    """The span of one line of `unit` (`position` indexes its origin lists), matched by the
    origin coordinate AND the line text, so two spans that share a baseline are never confused."""
    origins = unit.origin_raw_indexes or []
    texts = unit.origin_raw_texts or []
    if not origins or len(origins) != len(texts):
        return None
    origin = int(origins[position])
    line_text = texts[position]
    for span in spans_by_origin.get(origin, []):
        if _normalize_text(span.text) == line_text:
            return span
    return None


def _entry_line_ran_out_of_room(
    last_line: PdfTextSpan,
    next_line_text: str,
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    """Would the next line's first word have fit at the end of `last_line`? If it would, the
    line ended for a reason of its own -- the entry ended -- and nothing is joined."""
    right_edge = layout_profile.body_right_x1
    line_text = _normalize_text(last_line.text)
    words = next_line_text.split()
    if right_edge is None or not line_text or not words:
        return False
    char_width = (float(last_line.x1) - float(last_line.x0)) / len(line_text)
    # The word plus the one space that would have separated it.
    needed = char_width * (len(words[0]) + 1)
    return float(last_line.x1) + needed > float(right_edge)


def _entry_lines_are_consecutive(last_line: PdfTextSpan, first_line: PdfTextSpan) -> bool:
    if first_line.page_number == last_line.page_number + 1:
        return True
    if first_line.page_number != last_line.page_number:
        return False
    if float(first_line.top) <= float(last_line.top):
        return False
    font_size = _span_font_size(last_line) or _span_font_size(first_line)
    if font_size is None:
        return False
    return float(first_line.top) - float(last_line.bottom) < font_size


def _entry_continuation_keeps_the_wrap_indent(
    head: ParagraphUnit, last_line: PdfTextSpan, first_line: PdfTextSpan
) -> bool:
    """On one page, a wrapped line never steps back out to where entries begin. When the
    predecessor already has a wrapped line, its last line sits at the wrap indent; a line that
    starts half a font size or more to the LEFT of it starts a new entry, whatever the line
    above looks like -- VoE's bibliography, an entry ending in a web address that overran the
    column (so it reads as full), then the next entry, opening with a quoted title, back
    at the entry margin. Across a page break the margins of facing pages differ, so the test
    is not made there."""
    if len(head.origin_raw_indexes or []) < 2 or first_line.page_number != last_line.page_number:
        return True
    font_size = _span_font_size(last_line) or _span_font_size(first_line)
    if font_size is None:
        return False
    return float(first_line.x0) >= float(last_line.x0) - 0.5 * font_size


def _opens_with_explicit_entry_marker(text: str) -> bool:
    """Spec 081: the openers of `_text_opens_back_matter_entry` that MARK an entry -- a number
    closed by a full stop or a bracket ("12.", "12)"), a bullet, a repeated-author dash run.
    The other two openers there are guesses from wording that a wrapped line can carry by
    accident: the author form ("Business Review, January 2014.") and a number followed by a
    word ("27 May 2011.")."""
    stripped = text.lstrip()
    return bool(
        _ENTRY_EXPLICIT_NUMBER_PATTERN.match(stripped)
        or _BULLET_PATTERN.match(stripped)
        or stripped[:1] in "•●"
        or _ENTRY_REPEATED_AUTHOR_DASH_PATTERN.match(stripped)
    )


def _hanging_indent_line_position(
    span: PdfTextSpan, *, margin: float, indent: float, tolerance: float
) -> str | None:
    """'margin' or 'indent' when the line starts at one of the two edges (the nearer one, within
    `tolerance`); None when it starts anywhere else."""
    to_margin = abs(float(span.x0) - margin)
    to_indent = abs(float(span.x0) - indent)
    if min(to_margin, to_indent) > tolerance:
        return None
    return "margin" if to_margin < to_indent else "indent"


def _hanging_indent_run_entry_count(
    page_lines: list[PdfTextSpan],
    head_first_line: PdfTextSpan,
    tail_first_line: PdfTextSpan,
) -> int:
    """Spec 081: how many entries of an unbroken hanging-indent run hold the pair.

    The run is the block of lines around `tail_first_line` on its page in which every line is
    set in that line's size (`_font_sizes_match`), follows the line above with less than a
    blank line between them (`_entry_lines_are_consecutive`), and starts at one of the pair's
    two edges -- the margin where `head_first_line` starts, or the indent where
    `tail_first_line` starts -- within half a font size, the tolerance
    `_entry_continuation_keeps_the_wrap_indent` gives an edge. An entry of the run is a line at
    the margin directly followed by a line at the indent. Zero when the block does not hold
    the head's first line too."""
    run = _hanging_indent_run(page_lines, head_first_line, tail_first_line)
    return sum(
        1
        for (_, upper), (_, lower) in zip(run, run[1:])
        if upper == "margin" and lower == "indent"
    )


def _hanging_indent_run(
    page_lines: list[PdfTextSpan],
    head_first_line: PdfTextSpan,
    tail_first_line: PdfTextSpan,
) -> list[tuple[PdfTextSpan, str | None]]:
    """The run `_hanging_indent_run_entry_count` reads, line by line with its edge ('margin' or
    'indent'); empty when there is no run that holds both lines."""
    size = _span_font_size(tail_first_line)
    if size is None:
        return []
    index = next((k for k, line in enumerate(page_lines) if line is tail_first_line), None)
    if index is None:
        return []
    margin, indent, tolerance = float(head_first_line.x0), float(tail_first_line.x0), 0.5 * size

    def belongs(line: PdfTextSpan) -> bool:
        return _font_sizes_match(_span_font_size(line), size) and (
            _hanging_indent_line_position(line, margin=margin, indent=indent, tolerance=tolerance)
            is not None
        )

    start = index
    while (
        start > 0
        and belongs(page_lines[start - 1])
        and _entry_lines_are_consecutive(page_lines[start - 1], page_lines[start])
    ):
        start -= 1
    end = index
    while (
        end + 1 < len(page_lines)
        and belongs(page_lines[end + 1])
        and _entry_lines_are_consecutive(page_lines[end], page_lines[end + 1])
    ):
        end += 1
    block = page_lines[start : end + 1]
    if not any(line is head_first_line for line in block):
        return []
    return [
        (line, _hanging_indent_line_position(line, margin=margin, indent=indent, tolerance=tolerance))
        for line in block
    ]


def _entry_line_sits_at_the_hanging_indent(
    head: ParagraphUnit,
    first_line: PdfTextSpan,
    *,
    spans_by_origin: dict[int, list[PdfTextSpan]],
    lines_by_page: dict[int, list[PdfTextSpan]],
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    """Spec 081: the tail's first line is a WRAPPED line of a list set with a hanging indent, so
    its wording ("Business Review, January 2014.", "27 May 2011.") is not the start of a new
    entry. Both are required:
      * the tail's first line starts to the RIGHT of the head's FIRST line by at least the
        first-line-indent step of the line grouping (0.45 of the body leading,
        `_looks_like_body_paragraph_indent_boundary`): it sits under the entry, not where
        entries begin. The head's first line, not its last: in text set with a first-line
        indent (a dialogue, paragraphs of prose) a paragraph's last line is at the margin and
        the next paragraph starts at the indent -- the same step, read from the wrong line;
      * that margin / indent pair is a property of the run, not of this pair: the unbroken run
        of lines on the tail's page that holds both first lines
        (`_hanging_indent_run_entry_count`) has at least `_HANGING_INDENT_MIN_RUN_ENTRIES`
        entries that begin at the margin and continue at the indent. A signature over a place
        line, a two-line title, a single indented quotation or a lone sub-item under a full
        line show the step once; a list set with a hanging indent shows it at every wrapped
        entry. The run lies on one page, so nothing is compared across a page break, where
        the edges of facing pages differ."""
    head_first_line = _unit_line_span(head, 0, spans_by_origin)
    if head_first_line is None:
        return False
    return _line_wraps_to_the_hanging_indent(
        head_first_line,
        first_line,
        page_lines=lines_by_page.get(first_line.page_number, []),
        layout_profile=layout_profile,
    )


def _line_wraps_to_the_hanging_indent(
    entry_first_line: PdfTextSpan,
    line: PdfTextSpan,
    *,
    page_lines: list[PdfTextSpan],
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    """The two tests of `_entry_line_sits_at_the_hanging_indent`, read from lines: `line` starts
    right of `entry_first_line` by the first-line-indent step, and the unbroken run on its page
    that holds both shows that margin / indent pair at least `_HANGING_INDENT_MIN_RUN_ENTRIES`
    times. Spec 084 asks the same question of a line the classifier would type a heading."""
    body_leading = layout_profile.body_leading or layout_profile.body_font_size or 10.0
    if float(line.x0) - float(entry_first_line.x0) < body_leading * 0.45:
        return False
    return (
        _hanging_indent_run_entry_count(page_lines, entry_first_line, line)
        >= _HANGING_INDENT_MIN_RUN_ENTRIES
    )


def _run_returns_running_text_to_the_margin(
    entry_first_line: PdfTextSpan,
    line: PdfTextSpan,
    *,
    page_lines: list[PdfTextSpan],
    layout_profile: _PdfHeadingLayoutProfile,
) -> bool:
    """Spec 084 (Codex acceptance review, P1): the margin / indent run is set with a FIRST-LINE
    indent, not a hanging one.

    The two are mirror images and both show the margin -> indent step at every item, so the
    step alone does not tell them apart (prose under a full-width heading counted as a list of
    references). What does is where running text goes after a line at the indent that ran out
    of room (`_entry_line_ran_out_of_room`): in a hanging-indent list it wraps to the indent
    again -- the entry goes on under itself; in prose set with a first-line indent the
    paragraph's first line is at the indent and its text runs on at the margin. One such return
    anywhere in the run makes it prose."""
    run = _hanging_indent_run(page_lines, entry_first_line, line)
    return any(
        upper == "indent"
        and lower == "margin"
        and _entry_line_ran_out_of_room(
            upper_line, _normalize_text(lower_line.text), layout_profile=layout_profile
        )
        for (upper_line, upper), (lower_line, lower) in zip(run, run[1:])
    )


def _follows_a_wrapped_line_of_the_run(
    entry_first_line: PdfTextSpan,
    line: PdfTextSpan,
    *,
    page_lines: list[PdfTextSpan],
) -> bool:
    """Spec 084 (Codex acceptance review, round 2): the line directly above `entry_first_line`
    belongs to the same run (`_hanging_indent_run`: the same size, less than a blank line
    above, at one of the run's two edges) and stands at the indent -- the wrapped line of the
    entry before. So `entry_first_line` is not the first thing of the run: entries precede it
    as well as follow it."""
    run = _hanging_indent_run(page_lines, entry_first_line, line)
    position = next((k for k, (member, _) in enumerate(run) if member is entry_first_line), None)
    return position is not None and position > 0 and run[position - 1][1] == "indent"


def _is_torn_back_matter_entry_continuation(
    head: ParagraphUnit,
    tail: ParagraphUnit,
    *,
    spans_by_origin: dict[int, list[PdfTextSpan]],
    layout_profile: _PdfHeadingLayoutProfile,
    lines_by_page: dict[int, list[PdfTextSpan]],
) -> bool:
    if head.role not in _BACK_MATTER_ENTRY_ROLES or tail.role not in _BACK_MATTER_ENTRY_ROLES:
        return False
    if head.is_pdf_table_cell or tail.is_pdf_table_cell:
        return False
    if head.structural_role not in _BACK_MATTER_ENTRY_ROLES or tail.structural_role not in _BACK_MATTER_ENTRY_ROLES:
        return False
    tail_texts = tail.origin_raw_texts or []
    if not tail_texts:
        return False
    if _entry_text_ends_sentence(head.text or "", next_text=tail_texts[0]):
        return False
    last_line = _unit_line_span(head, -1, spans_by_origin)
    first_line = _unit_line_span(tail, 0, spans_by_origin)
    if last_line is None or first_line is None:
        return False
    # Spec 081: a wrapped line can open like an entry by its wording alone (an author form, a
    # number and a word); where the page's geometry shows it at the wrap indent of a hanging-
    # indent run, the geometry decides. An explicit entry marker always starts an entry.
    tail_text = tail.text or ""
    if _text_opens_back_matter_entry(tail_text) and (
        _opens_with_explicit_entry_marker(tail_text)
        or not _entry_line_sits_at_the_hanging_indent(
            head,
            first_line,
            spans_by_origin=spans_by_origin,
            lines_by_page=lines_by_page,
            layout_profile=layout_profile,
        )
    ):
        return False
    return (
        _entry_lines_are_consecutive(last_line, first_line)
        and _entry_continuation_keeps_the_wrap_indent(head, last_line, first_line)
        and _entry_line_ran_out_of_room(last_line, tail_texts[0], layout_profile=layout_profile)
    )


def _join_entry_continuation_runs(
    head_runs: list[StyleRun],
    tail_runs: list[StyleRun],
    *,
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None,
) -> list[StyleRun]:
    head_text = "".join(text for text, _, _ in head_runs)
    tail_text = "".join(text for text, _, _ in tail_runs)
    if (
        _soft_wrap_hyphen_boundary(head_text, tail_text) is None
        and _ENTRY_HARD_HYPHEN_TAIL_PATTERN.search(head_text)
        and tail_text[:1]
        and not tail_text[0].isspace()
    ):
        # A compound or an address broken at its own hyphen before a capital or a digit
        # ("Wiley-" + "Blackwell", "co-gp-" + "20110913.html"): the hyphen is part of the
        # token, so it stays and no space is put in.
        return [*head_runs, *tail_runs]
    return _join_soft_wrapped_run_pieces(
        [head_runs, tail_runs], dehyphenation_evidence=dehyphenation_evidence
    )


def _merge_torn_back_matter_entry(
    head: ParagraphUnit,
    tail: ParagraphUnit,
    *,
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None,
) -> ParagraphUnit:
    joined_runs = _join_entry_continuation_runs(
        _unit_style_runs(head),
        _unit_style_runs(tail),
        dehyphenation_evidence=dehyphenation_evidence,
    )
    return replace(
        head,
        text="".join(text for text, _, _ in joined_runs),
        pdf_emphasis_runs=joined_runs,
        is_bold=head.is_bold and tail.is_bold,
        is_italic=head.is_italic and tail.is_italic,
        origin_raw_indexes=[*(head.origin_raw_indexes or []), *(tail.origin_raw_indexes or [])],
        origin_raw_texts=[*(head.origin_raw_texts or []), *(tail.origin_raw_texts or [])],
        boundary_rationale="merged_back_matter_entry_continuation",
    )


# ----------------------------------------------------------------------------------------
# Spec 065 FR-008 (I-2): the roles inside a notes / reference section.
#
# The per-span classifier reads typography page by page and knows nothing of the section it
# is in, so inside the notes it inverts two roles (The Value of Everything, 2026-11-08): a
# wrapped line of an entry -- a book title, an address tail, a quoted fragment -- comes out a
# level-3 heading (31 of them), and the title of a chapter's group of notes ("1. A BRIEF
# HISTORY OF VALUE") comes out a list item or body (10 of 11). The fragment-heading also
# stops the 064 notes-join, which never joins through a heading (block 600, "(Basingstoke ...
# 2005)."). Both are settled here, before that join, from form and geometry only:
#
#   * a GROUP TITLE is a one-line unit after which the entry numbering starts again -- the
#     next unit opens with entry number 1 -- set in a different size from that entry, and not
#     itself the next entry of the running sequence (when it carries a number, that number is
#     not the previous entry's plus one). It becomes a heading one level below the section
#     title, and never shallower than level 3: a group of notes is not a chapter.
#   * an ENTRY FRAGMENT is a heading set at the size of the entry before it that either opens
#     an entry by form (`_text_opens_back_matter_entry`: a note number, a bullet, a repeated-
#     author dash, an author form) or whose first line is the very next line after that entry
#     (`_entry_lines_are_consecutive`: no blank line, or the top of the next page). It becomes
#     body; the notes-join that follows then reads it like any other torn line.
#
# A heading that is set apart -- another size than the entry before it, or a blank line above
# it -- stays a heading, and so does a group title. Lines the TOC heuristic flagged are not
# fragments here, and a group title takes them only by the same form as any other line.
# ----------------------------------------------------------------------------------------

_ENTRY_NUMBER_PATTERN = re.compile(r"^(?P<number>\d{1,3})(?:[.)](?:\s|$)|\s+[^\W\d_])")
_BACK_MATTER_GROUP_TITLE_MIN_LEVEL = 3


def _entry_number(text: str) -> int | None:
    match = _ENTRY_NUMBER_PATTERN.match((text or "").lstrip())
    return int(match.group("number")) if match else None


def _is_back_matter_group_title(
    unit: ParagraphUnit,
    following: ParagraphUnit | None,
    *,
    previous_entry_number: int | None,
) -> bool:
    if following is None or len(unit.origin_raw_indexes or []) != 1:
        return False
    if unit.role not in {"body", "list", "heading"}:
        return False
    if following.role not in _BACK_MATTER_ENTRY_ROLES or _entry_number(following.text or "") != 1:
        return False
    if _font_sizes_match(unit.font_size_pt, following.font_size_pt):
        return False
    own_number = _entry_number(unit.text or "")
    return not (
        own_number is not None
        and previous_entry_number is not None
        and own_number == previous_entry_number + 1
    )


def _is_back_matter_entry_fragment(
    unit: ParagraphUnit,
    previous: ParagraphUnit,
    *,
    spans_by_origin: dict[int, list[PdfTextSpan]],
) -> bool:
    if unit.role != "heading" or previous.role not in _BACK_MATTER_ENTRY_ROLES:
        return False
    if not _font_sizes_match(unit.font_size_pt, previous.font_size_pt):
        return False
    if _text_opens_back_matter_entry(unit.text or ""):
        return True
    last_line = _unit_line_span(previous, -1, spans_by_origin)
    first_line = _unit_line_span(unit, 0, spans_by_origin)
    return (
        last_line is not None
        and first_line is not None
        and _entry_lines_are_consecutive(last_line, first_line)
    )


def _settle_back_matter_entry_roles(
    units: list[ParagraphUnit],
    ordered_spans: list[PdfTextSpan],
) -> list[ParagraphUnit]:
    """Spec 065 FR-008: group titles of a notes section are headings, wrapped lines of its
    entries are not. See the block comment above for the form."""
    flags = _back_matter_entry_region_flags(units)
    if not any(flags):
        return units
    spans_by_origin: dict[int, list[PdfTextSpan]] = {}
    for span in ordered_spans:
        spans_by_origin.setdefault(_span_origin_index(span), []).append(span)
    section_level: int | None = None
    previous_entry_number: int | None = None
    for index, unit in enumerate(units):
        if not flags[index]:
            if _back_matter_anchor_kind(unit) is not None:
                section_level = unit.heading_level
                previous_entry_number = None
            continue
        following = units[index + 1] if index + 1 < len(units) and flags[index + 1] else None
        if _is_back_matter_group_title(
            unit, following, previous_entry_number=previous_entry_number
        ):
            if unit.role != "heading":
                _promote_unit_to_heading(
                    unit,
                    heading_level=max(
                        _BACK_MATTER_GROUP_TITLE_MIN_LEVEL, (section_level or 0) + 1
                    ),
                )
                unit.boundary_rationale = "promoted_back_matter_group_title"
            previous_entry_number = None
            continue
        if (
            index > 0
            and flags[index - 1]
            and _is_back_matter_entry_fragment(
                unit, units[index - 1], spans_by_origin=spans_by_origin
            )
        ):
            unit.role = "body"
            unit.structural_role = "body"
            unit.heading_level = None
            unit.heading_source = None
            unit.boundary_rationale = "demoted_back_matter_entry_fragment"
        number = _entry_number(unit.text or "")
        if number is not None and unit.role in _BACK_MATTER_ENTRY_ROLES:
            previous_entry_number = number
    return units


def _join_torn_back_matter_entries(
    units: list[ParagraphUnit],
    ordered_spans: list[PdfTextSpan],
    *,
    layout_profile: _PdfHeadingLayoutProfile,
    dehyphenation_evidence: _SoftWrapDehyphenationEvidence | None = None,
) -> list[ParagraphUnit]:
    """Spec 064 R-7: join an entry of a notes / reference section that import tore in the
    middle of a sentence. See the block comment above for the rule and why it lives here."""
    flags = _back_matter_entry_region_flags(units)
    if not any(flags):
        return units
    spans_by_origin: dict[int, list[PdfTextSpan]] = {}
    lines_by_page: dict[int, list[PdfTextSpan]] = {}
    for span in ordered_spans:
        spans_by_origin.setdefault(_span_origin_index(span), []).append(span)
        lines_by_page.setdefault(span.page_number, []).append(span)
    result: list[ParagraphUnit] = []
    previous_in_region = False
    for unit, in_region in zip(units, flags):
        if (
            in_region
            and previous_in_region
            and result
            and _is_torn_back_matter_entry_continuation(
                result[-1],
                unit,
                spans_by_origin=spans_by_origin,
                layout_profile=layout_profile,
                lines_by_page=lines_by_page,
            )
        ):
            result[-1] = _merge_torn_back_matter_entry(
                result[-1], unit, dehyphenation_evidence=dehyphenation_evidence
            )
            continue
        result.append(unit)
        previous_in_region = in_region
    return result


def _attach_pdf_layout_signals(
    paragraphs: list[ParagraphUnit],
    ordered_spans: list[PdfTextSpan],
    *,
    layout_profile: _PdfHeadingLayoutProfile,
) -> None:
    """Record, on each unit, the vertical gap this importer measured above it.

    ``ParagraphUnit.vertical_gap_before_pt`` has existed since the DOCX path was written and
    the PDF path never assigned it: 0 of 8216 paragraphs across the four corpus books
    (census, 2026-08-05). It is recoverable here and nowhere downstream, because in a PDF it
    IS geometry — there is no ``w:spacing`` to read, only coordinates, and the coordinates
    stop existing the moment the intermediate DOCX is written.

    Nothing in here looks at the text, and nothing is guessed: a paragraph whose spans cannot
    be located, or one that opens a page, yields no signal at all.

    Centring is deliberately NOT recorded, though this importer can measure it accurately
    (`_spans_are_centered_in_body_column`, deleted in the spec 055 history — recover it from
    git if the question is ever reopened). It was carried, the corpus was re-run, and it
    produced 33 heading promotions across four books of which not one was correct: 24 were
    per-chapter labels inside notes back-matter, which this module has a dedicated test for
    demoting. The signal was true and the downstream inference from it is wrong for this
    document class, which Constitution VII answers with ACCEPT, not with a cleverer rule.
    """

    if not paragraphs:
        return

    spans_by_origin: dict[int, list[PdfTextSpan]] = {}
    for span in ordered_spans:
        spans_by_origin.setdefault(_span_origin_index(span), []).append(span)

    previous_page: int | None = None
    previous_bottom: float | None = None
    for paragraph in paragraphs:
        paragraph_spans = [
            span
            for origin in (paragraph.origin_raw_indexes or [])
            for span in spans_by_origin.get(int(origin), [])
        ]
        if not paragraph_spans:
            previous_page = None
            previous_bottom = None
            continue

        first_span = paragraph_spans[0]
        if previous_page == first_span.page_number and previous_bottom is not None:
            paragraph.vertical_gap_before_pt = round(
                max(0.0, float(first_span.top) - previous_bottom), 2
            )

        last_page = max(span.page_number for span in paragraph_spans)
        previous_page = last_page
        previous_bottom = max(
            float(span.bottom) for span in paragraph_spans if span.page_number == last_page
        )


# ----------------------------------------------------------------------------------------
# The one place where an importer role becomes an intermediate-DOCX paragraph style.
#
# Until spec 055 there were two. This module computed a style name from the role and stored
# it on ``ParagraphUnit.style_name``; the PDF->DOCX bridge
# (``processing/processing_runtime.py:_append_pdf_text_paragraph_to_docx``) ignored that field
# and re-derived its own map, which knew ``heading`` and ``list`` and nothing else. So the
# importer's decision was computed and dropped in the same breath: on Money & Sustainability
# it produced ``PDF Footnote`` 21 times, ``PDF TOC Entry`` 16 and ``PDF Caption`` twice, and
# not one of those strings existed anywhere downstream. The table below is now the only
# role->style decision on the PDF path; ``_assign_docx_style_names`` stamps its verdict onto
# every unit once every role is final, and the bridge writes that verdict verbatim.
#
# Every name here MUST exist in python-docx's default template: the bridge passes it straight
# to ``Document.add_paragraph(style=...)``, which raises ``KeyError`` on an unknown style and
# would fail the whole book. That is why the carried caption style is the built-in ``Caption``
# and not ``PDF Caption`` -- the latter is what the discarded mapper used to return, and
# python-docx rejects it. ``test_every_carried_docx_style_name_exists_in_the_default_template``
# is the counter-proof, and it is the test to extend whenever a role is added here.
#
# The roles mapped to ``None`` are NOT carried on purpose. This is a recorded decision, not an
# oversight; do not "complete" the table without the measurement that reverses it:
#
#   * ``toc_entry`` -- 608 paragraphs across the four-book corpus, and no built-in style
#     expresses a TOC row as a paragraph role (Word's ``TOC 1`` is field-generated). Carrying
#     it needs a style definition first, and the owner deferred that until the four-book run
#     reports what a TOC role would do downstream (spec 055 changelog, 2026-08-05).
#   * ``footnote`` -- 59 characters across the whole corpus, absent from two of the four books,
#     and what it covers is a bare superscript marker, not a footnote body. Constitution VII
#     puts footnotes outside the detection scope outright. Decided closed, not deferred.
#   * ``body`` -- has no style by definition; ``None`` means the DOCX default (``Normal``).
# ----------------------------------------------------------------------------------------

# The heading style is the single level-dependent entry, so the table holds a template rather
# than a name and ``docx_style_name_for_role`` fills the level in.
_HEADING_DOCX_STYLE_TEMPLATE = "Heading {level}"
_MAX_DOCX_HEADING_LEVEL = 6

_ROLE_DOCX_STYLE: dict[str, str | None] = {
    "heading": _HEADING_DOCX_STYLE_TEMPLATE,
    "list": "List Bullet",
    "caption": "Caption",
    "toc_entry": None,
    "footnote": None,
    "body": None,
}


def docx_style_name_for_role(role: str, heading_level: int | None = None) -> str | None:
    """The intermediate-DOCX paragraph style for an importer role, or ``None`` for ``Normal``.

    An unknown role is treated as body, which is what the two previous mappers both did.
    """
    style = _ROLE_DOCX_STYLE.get(role)
    if style == _HEADING_DOCX_STYLE_TEMPLATE:
        level = min(max(int(heading_level or 2), 1), _MAX_DOCX_HEADING_LEVEL)
        return _HEADING_DOCX_STYLE_TEMPLATE.format(level=level)
    return style


def _assign_docx_style_names(paragraphs: list[ParagraphUnit]) -> None:
    """Stamp the style the bridge will write, once, after every role decision is final.

    Doing it here rather than in the paragraph constructors is what keeps the field honest:
    ``_promote_unit_to_heading`` / ``_demote_heading_to_body`` run after construction, so a
    style computed at construction time would already be stale for the units they touch.

    ``structural_role`` is the key because it is the only field that still says ``toc_entry``
    -- those units carry ``role="body"`` (see ``_paragraph_from_span``) -- and for every other
    role the two agree.
    """
    for paragraph in paragraphs:
        role = paragraph.structural_role or paragraph.role
        paragraph.style_name = docx_style_name_for_role(role, paragraph.heading_level) or ""


def _looks_like_toc_entry(span: PdfTextSpan) -> bool:
    return _text_looks_like_toc_entry(_normalize_text(span.text))


def _text_looks_like_toc_entry(text: str) -> bool:
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
