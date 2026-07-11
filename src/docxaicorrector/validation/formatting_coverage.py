from __future__ import annotations

import re
from collections.abc import Mapping, Sequence


_CHAPTER_MARKER_TEXT_PATTERN = re.compile(r"^(?:chapter|глава)\s+(?:\d+|[ivxlcdm]+)\b[ .:-]*$", re.IGNORECASE)
_IMAGE_PLACEHOLDER_TEXT_PATTERN = re.compile(r"\[\[docx_image_[^\]]+\]\]", re.IGNORECASE)
_LEADING_CONTINUATION_FRAGMENT_PATTERN = re.compile(r"^[,.;:!?…)\]»]\s*\S")

# --- Agreed pass-through detection (front-matter / bounded-TOC / page-furniture) ---
#
# Director scope decision (GLOBAL_PLAN 2026-06-20c): TOC, front-matter (title/cover/
# attributions) and source/reference pages are PASS-THROUGH — translated as-is but
# EXCLUDED from the strict unmapped-paragraph acceptance thresholds. These detectors
# classify an *already-unmapped* registry entry into one of those agreed categories so
# the acceptance gate can subtract them with auditable provenance. They never touch a
# real main-body prose paragraph: detection is by role/region/form, never by a
# book-specific literal.
_ROMAN_NUMERAL_PATTERN = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
# A standalone chapter-body heading ("Chapter IV — Instabilities…" / "Глава V: …"): a
# chapter number FOLLOWED by a title. This marks where front-matter ends and the report
# body begins.
_CHAPTER_BODY_HEADING_PATTERN = re.compile(
    r"^(?:chapter|глава)\s+(?:\d+|[ivxlcdm]+)\b\s*[—\-–:]\s*\S",
    re.IGNORECASE,
)
# Page furniture: bare separators / star-dividers ("* * *").
_DIVIDER_FURNITURE_PATTERN = re.compile(r"^[\*•·\-–—\s]+$")
_CONTENTS_HEADING_PATTERN = re.compile(r"^(?:contents|содержание|оглавление)$", re.IGNORECASE)

_MAX_FURNITURE_PREVIEW_LEN = 16

# --- Additional agreed pass-through categories (references / captions / part-dividers) ---
#
# Breadth (GLOBAL_PLAN 1-A, 2026-06-22): lietaer/mazzucato fail acceptance PURELY on
# pass-through the Money fix did not yet credit — bibliography/notes/index entries,
# figure captions and part-dividers. These extend the same detection-with-provenance
# mechanism; they never touch a real main-body prose paragraph (each detector is
# role/region/form based, never a book-specific literal, and the references region
# carries a substantial-body-prose valve so a genuinely misplaced body paragraph is
# still counted).
#
# Figure/table caption ("Figure 27. …" / "Рисунок 2.2: …" / "Table 3 …"). The marker
# must be at the START of the line — body prose almost never opens a paragraph with a
# bare "Figure N." noun phrase.
_CAPTION_TEXT_PATTERN = re.compile(
    r"^(?:figure|fig|рисунок|рис|table|табл(?:ица)?|схема|диаграмма|chart|plate|photo|"
    r"иллюстрация|илл)\.?\s*\d+",
    re.IGNORECASE,
)
_MAX_CAPTION_PREVIEW_LEN = 200
# Part-divider ("Part Two" / "Part III" / "Часть вторая"): a short structural heading.
_PART_DIVIDER_PATTERN = re.compile(
    r"^(?:part|часть)\s+"
    r"(?:\d+|[ivxlcdm]+|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"первая|вторая|третья|четвёртая|четвертая|пятая|шестая|седьмая|восьмая|девятая|десятая)"
    r"\b",
    re.IGNORECASE,
)
_MAX_PART_DIVIDER_LEN = 48
# Bare back-matter section titles that open the references/notes/index region. Matched
# EXACTLY against the normalized text so front-matter TOC rows ("notes 225",
# "bibliography 241") — which carry a trailing page number — never anchor the region.
_BACKMATTER_SECTION_TITLES = frozenset(
    {
        "notes",
        "endnotes",
        "footnotes",
        "references",
        "bibliography",
        "index",
        "sources",
        "works cited",
        "further reading",
        "примечания",
        "библиография",
        "указатель",
        "источники",
        "литература",
        "сноски",
        "список литературы",
        "именной указатель",
        "предметный указатель",
    }
)
# A substantial, self-contained body-prose paragraph: the anti-vacuum valve. Even inside
# a detected references region, an entry that reads like a real paragraph (long, opens
# with a capital, ends with terminal punctuation) is RETAINED and still counts — so a
# genuine body-text loss can never be masked by a mis-anchored back-matter region.
_MIN_BODY_PROSE_LEN = 140
_BODY_PROSE_TERMINAL_CHARS = ".!?…»\"”"

# --- Additional agreed pass-through categories (index-region / attribution) — 3A ---
#
# GATE_TRUSTWORTHINESS 3A (2026-07-09): the residue that still tips effective-unmapped
# over threshold is itself pass-through — back-matter INDEX rows (a term followed by a
# semicolon-separated list of page numbers / ranges) and front/back ATTRIBUTION lines
# (epigraph author credits). Both are translated as-is but must not count as body loss.
# Each detector is form/region based (never a book-specific literal) and preserves the
# anti-vacuum valve: a real body-prose paragraph (`_is_substantial_body_prose`) is never
# classified as either.
#
# Index row: a term/heading followed by page references — at least one semicolon-joined
# page group OR a bare/comma-led run of page numbers and page ranges ("60–61, 72; 88").
# Only trusted INSIDE the confirmed references/back-matter region (source_index >=
# references_region_start) so a mid-body sentence that merely ends in a number is safe.
_INDEX_PAGE_RUN_PATTERN = re.compile(r"\d+\s*[–—-]\s*\d+|\d+\s*;\s*\d+|,\s*\d+(?:\s*[–—-]\s*\d+)?\s*(?:;|$)")
_INDEX_SEMICOLON_PAGE_PATTERN = re.compile(r";\s*(?:pp?\.?\s*)?\d")
_MAX_INDEX_ROW_LEN = 400
# Attribution: an epigraph/dedication author credit. Either an explicit structural role,
# or a short dash-led credit ("— Adrienne Rich") that does NOT end in sentence-terminal
# punctuation — a short dash-led line ending in "."/"!"/"?" is dialogue / an em-dash-led
# clause, not an author credit.
_ATTRIBUTION_STRUCTURAL_ROLES = frozenset({"attribution", "epigraph", "dedication"})
_MAX_ATTRIBUTION_LEN = 90
_ATTRIBUTION_DASH_PATTERN = re.compile(r"^[—–\-]\s*[^\W\d_]", re.UNICODE)
_ATTRIBUTION_SENTENCE_TERMINAL = ".!?"


def _entry_role(entry: Mapping[str, object] | None) -> str:
    if entry is None:
        return ""
    return str(entry.get("role") or entry.get("structural_role") or "").strip().lower()


def _is_page_furniture_text(text: str) -> bool:
    """A short standalone marker that is NOT real prose: a page number, footnote-ref
    digit, roman numeral, single-character OCR artifact, bare chapter marker, or a
    star/dash divider. Form-only — no book-specific strings."""
    normalized = _normalize_structural_text(text)
    if not normalized:
        return False
    lowered = normalized.lower()
    if _CHAPTER_MARKER_TEXT_PATTERN.match(lowered) is not None:
        return True
    if len(normalized) > _MAX_FURNITURE_PREVIEW_LEN:
        return False
    core = re.sub(r"[()\[\].,:;\s]", "", normalized)
    if core == "":
        return _DIVIDER_FURNITURE_PATTERN.match(normalized) is not None
    if core.isdigit():
        return True
    if _ROMAN_NUMERAL_PATTERN.fullmatch(core) is not None:
        return True
    if _DIVIDER_FURNITURE_PATTERN.match(normalized) is not None:
        return True
    # Single-character OCR junk that survived as a standalone "heading"/line.
    if len(core) <= 1 and core.isalpha():
        return True
    return False


def _is_caption_text(text: str, role: str) -> bool:
    """A figure/table caption: role=caption, or a line that OPENS with a numbered
    figure/table marker ("Figure 27. …" / "Рисунок 2.2: …"). Form-only otherwise."""
    if role == "caption":
        return True
    normalized = _normalize_structural_text(text)
    if not normalized or len(normalized) > _MAX_CAPTION_PREVIEW_LEN:
        return False
    return _CAPTION_TEXT_PATTERN.match(normalized) is not None


def _is_part_divider_text(text: str) -> bool:
    """A short "Part N" / "Часть N" structural divider (numeral / roman / spelled-out
    ordinal). Length-bounded so running prose beginning "Part of…" is never caught."""
    normalized = _normalize_structural_text(text)
    if not normalized or len(normalized) > _MAX_PART_DIVIDER_LEN:
        return False
    return _PART_DIVIDER_PATTERN.match(normalized) is not None


def _is_substantial_body_prose(text: str) -> bool:
    """The anti-vacuum valve: True only for a line that reads like a real body
    paragraph — long, opening with a capital letter, closing with terminal
    punctuation. Such an entry is NEVER classified as pass-through, so a genuine body
    loss cannot be hidden inside a back-matter region."""
    normalized = _normalize_structural_text(text)
    if len(normalized) < _MIN_BODY_PROSE_LEN:
        return False
    first_alpha = next((ch for ch in normalized if ch.isalpha()), "")
    if not first_alpha or first_alpha == first_alpha.lower():
        return False
    return normalized[-1] in _BODY_PROSE_TERMINAL_CHARS


def _is_index_row_text(text: str) -> bool:
    """An index/back-matter reference row: a term followed by a run of page numbers
    (semicolon-joined groups or comma-led page ranges). Form-only; the caller restricts
    it to the confirmed references region so a body sentence ending in a number is safe.
    A substantial body-prose paragraph is never an index row (anti-vacuum valve)."""
    normalized = _normalize_structural_text(text)
    if not normalized or len(normalized) > _MAX_INDEX_ROW_LEN:
        return False
    if _is_substantial_body_prose(normalized):
        return False
    if _INDEX_SEMICOLON_PAGE_PATTERN.search(normalized) is not None:
        return True
    # Otherwise require a term (letters) plus a page run: a page range (digits joined by a
    # dash) or a semicolon, AND at least three numeric groups — index rows carry a dense
    # run of page numbers, so a plain "…in 2010." sentence tail is never mistaken for one.
    if not any(ch.isalpha() for ch in normalized):
        return False
    numeric_group_count = len(re.findall(r"\d+", normalized))
    has_page_run = (
        re.search(r"\d+\s*[–—-]\s*\d+", normalized) is not None or ";" in normalized
    )
    return has_page_run and numeric_group_count >= 3


def _is_attribution_text(text: str, role: str, structural_role: str) -> bool:
    """An epigraph/dedication attribution credit. True for an explicit structural role,
    or a short dash-led author credit ("— Adrienne Rich"). A dash-led line that ends in
    sentence-terminal punctuation ("."/"!"/"?") is dialogue / an em-dash-led clause, not a
    credit, and is rejected. Length-bounded and never matches a real body paragraph —
    anti-vacuum safe."""
    if structural_role in _ATTRIBUTION_STRUCTURAL_ROLES or role in _ATTRIBUTION_STRUCTURAL_ROLES:
        return True
    normalized = _normalize_structural_text(text)
    if not normalized or len(normalized) > _MAX_ATTRIBUTION_LEN:
        return False
    if _is_substantial_body_prose(normalized):
        return False
    if normalized[-1] in _ATTRIBUTION_SENTENCE_TERMINAL:
        return False
    return _ATTRIBUTION_DASH_PATTERN.match(normalized) is not None


def _target_registry_is_heading(entry: Mapping[str, object] | None) -> bool:
    if entry is None:
        return False
    return entry.get("heading_level") is not None


def classify_heading_demotions(
    payload: Mapping[str, object],
    preparation_diagnostic_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Body-integrity axis 1‑D: detect MAPPED source-heading → target body/list pairs
    where the heading content survived (the pair is mapped) but the target lost the
    heading role. Complements the existing role_loss over UNMAPPED source. Scoped to the
    main-content span `[front_matter_boundary … references_region_start)` (excluding the
    bounded TOC and caption/part markers) using the same provenance as
    `classify_passthrough_unmapped_source`, so TOC / front-matter / back-matter / index
    / attribution demotions are never counted. Returns the demotion samples + count +
    boundary provenance (payload-level so it runs offline over saved reports and live in
    the gate identically)."""
    source_registry = _coerce_mapping_sequence(payload.get("source_registry"))
    target_registry = _coerce_mapping_sequence(payload.get("target_registry"))
    if not source_registry or not target_registry:
        return {
            "demotion_count": 0,
            "demotions": [],
            "samples": [],
            "front_matter_boundary_source_index": None,
            "references_region_source_start_index": None,
            "bounded_toc_region": None,
        }
    target_by_index = {
        _coerce_int(entry.get("target_index"), default=-1): entry for entry in target_registry
    }
    boundary = _resolve_source_front_matter_boundary(source_registry, preparation_diagnostic_snapshot)
    toc_region = _resolve_bounded_toc_region(source_registry, preparation_diagnostic_snapshot, boundary)
    references_region_start = _resolve_references_region_start(source_registry, boundary, toc_region)

    demotions: list[dict[str, object]] = []
    for entry in source_registry:
        role = _entry_role(entry)
        heading_level = entry.get("heading_level")
        if role != "heading" and heading_level is None:
            continue
        structural_role = str(entry.get("structural_role") or "").strip().lower()
        source_text = str(entry.get("text_preview") or "")
        # A caption / part-divider that happens to carry a heading role is furniture,
        # not a demotable body heading.
        if role == "caption" or structural_role == "caption":
            continue
        if _is_part_divider_text(source_text):
            continue
        mapped = entry.get("mapped_target_index")
        if mapped is None:
            continue
        target_entry = target_by_index.get(_coerce_int(mapped, default=-1))
        if target_entry is None:
            continue
        if _target_registry_is_heading(target_entry):
            continue
        target_text = str(target_entry.get("text_preview") or "")
        # The pair is mapped (content survived); guard against an empty / furniture target
        # so a heading mapped onto a page-number or divider is not mis-flagged.
        if not target_text.strip() or _is_page_furniture_text(target_text):
            continue
        index = _coerce_int(entry.get("source_index"), default=-1)
        if boundary is not None and 0 <= index < boundary:
            continue
        if references_region_start is not None and index >= references_region_start:
            continue
        if toc_region is not None and toc_region[0] <= index <= toc_region[1]:
            continue
        demotions.append(
            {
                "paragraph_id": str(entry.get("paragraph_id") or ""),
                "source_index": index,
                "mapped_target_index": _coerce_int(mapped, default=-1),
                "source_role": role or "heading",
                "source_structural_role": structural_role or None,
                "source_heading_level": heading_level,
                "text_preview": source_text,
                "target_text_preview": target_text,
                "target_style_name": target_entry.get("style_name"),
                "reason": "content_survived_but_heading_demoted",
            }
        )

    return {
        "demotion_count": len(demotions),
        "demotions": demotions,
        "samples": demotions[:8],
        "front_matter_boundary_source_index": boundary,
        "references_region_source_start_index": references_region_start,
        "bounded_toc_region": list(toc_region) if toc_region is not None else None,
    }


def _resolve_references_region_start(
    source_registry: Sequence[Mapping[str, object]],
    front_matter_boundary: int | None,
    toc_region: tuple[int, int] | None,
) -> int | None:
    """The source_index at which the back-matter references/notes/index region begins,
    or None. Anchored on the earliest EXACT bare back-matter section title
    ("Notes"/"Bibliography"/"Index"/"Примечания"/…) that sits after the front-matter
    boundary and after any bounded TOC region. Exact matching keeps the front-matter TOC
    rows ("notes 225") from anchoring it. The caller confirms the region by form before
    trusting it."""
    if not source_registry:
        return None
    toc_end = toc_region[1] if toc_region is not None else -1
    boundary = front_matter_boundary if front_matter_boundary is not None else -1
    best: int | None = None
    for entry in source_registry:
        normalized = _normalize_structural_text(str(entry.get("text_preview") or "")).lower()
        if normalized in _BACKMATTER_SECTION_TITLES:
            index = _coerce_int(entry.get("source_index"), default=-1)
            if index >= 0 and index > boundary and index > toc_end:
                if best is None or index < best:
                    best = index
    return best


def _resolve_target_references_boundary(
    source_registry: Sequence[Mapping[str, object]],
    source_region_start: int | None,
) -> int | None:
    """Project the source references-region start through the source→target mapping: the
    first mapped target index at/after the source anchor (mirrors the front-matter
    target-boundary projection, since the target registry carries no roles)."""
    if source_region_start is None or not source_registry:
        return None
    for entry in source_registry:
        if _coerce_int(entry.get("source_index"), default=-1) < source_region_start:
            continue
        mapped = entry.get("mapped_target_index")
        if mapped is not None:
            mapped_index = _coerce_int(mapped, default=-1)
            return mapped_index if mapped_index >= 0 else None
    return None


def _resolve_source_front_matter_boundary(
    source_registry: Sequence[Mapping[str, object]],
    preparation_diagnostic_snapshot: Mapping[str, object] | None,
) -> int | None:
    """The source_index at which the report body begins. Front-matter is everything
    before it. Detected generally (not by literals):
      1. the first chapter-body heading ("Chapter N — Title"), else
      2. the first sustained run of >= 3 long body-prose paragraphs.
    Gated by `first_block_has_body_start` being False (the document opens with
    front-matter); if the first block is already body, there is no front-matter region.
    """
    snapshot = preparation_diagnostic_snapshot or {}
    if "first_block_has_body_start" in snapshot and bool(snapshot.get("first_block_has_body_start")):
        return None
    if not source_registry:
        return None

    for entry in source_registry:
        if _entry_role(entry) == "heading" and _CHAPTER_BODY_HEADING_PATTERN.match(
            _normalize_structural_text(str(entry.get("text_preview") or "")).lower()
        ):
            index = _coerce_int(entry.get("source_index"), default=-1)
            if index >= 0:
                return index

    run = 0
    run_start_index: int | None = None
    for entry in source_registry:
        text = _normalize_structural_text(str(entry.get("text_preview") or ""))
        if _entry_role(entry) == "body" and len(text) >= 100:
            if run == 0:
                run_start_index = _coerce_int(entry.get("source_index"), default=-1)
            run += 1
            if run >= 3 and run_start_index is not None and run_start_index >= 0:
                return run_start_index
        else:
            run = 0
            run_start_index = None
    return None


def _resolve_target_front_matter_boundary(
    source_registry: Sequence[Mapping[str, object]],
    source_boundary_index: int | None,
) -> int | None:
    """Anchor the target front-matter boundary through the source→target mapping: the
    first mapped target index at/after the source body-start boundary. Avoids re-deriving
    a boundary from the (role-less) target registry."""
    if source_boundary_index is None or not source_registry:
        return None
    for entry in source_registry:
        if _coerce_int(entry.get("source_index"), default=-1) < source_boundary_index:
            continue
        mapped = entry.get("mapped_target_index")
        if mapped is not None:
            mapped_index = _coerce_int(mapped, default=-1)
            return mapped_index if mapped_index >= 0 else None
    return None


def _resolve_bounded_toc_region(
    source_registry: Sequence[Mapping[str, object]],
    preparation_diagnostic_snapshot: Mapping[str, object] | None,
    front_matter_boundary: int | None,
) -> tuple[int, int] | None:
    """Inclusive (start, end) source_index range of the bounded TOC region, or None.
    Gated by `bounded_toc_region_count`/`document_map_toc_detected`. The region starts at
    a "Contents"-style heading and runs up to the front-matter boundary (the TOC always
    sits inside the front matter)."""
    snapshot = preparation_diagnostic_snapshot or {}
    has_toc = _coerce_int(snapshot.get("bounded_toc_region_count")) > 0 or bool(
        snapshot.get("document_map_toc_detected")
    )
    if not has_toc or not source_registry:
        return None
    start_index: int | None = None
    for entry in source_registry:
        if _CONTENTS_HEADING_PATTERN.match(
            _normalize_structural_text(str(entry.get("text_preview") or ""))
        ):
            start_index = _coerce_int(entry.get("source_index"), default=-1)
            break
    if start_index is None or start_index < 0:
        return None
    # Bound the TOC by its own entry count (plus the header rows) — NOT by the whole
    # front-matter region, so front-matter attributions after the TOC stay classified as
    # front_matter, not mislabelled as TOC entries.
    toc_entry_count = _coerce_int(snapshot.get("toc_entry_count"))
    toc_header_count = _coerce_int(snapshot.get("toc_header_count"))
    if toc_entry_count > 0:
        end_index = start_index + toc_entry_count + max(toc_header_count, 1)
    elif front_matter_boundary is not None:
        end_index = front_matter_boundary - 1
    else:
        return None
    if front_matter_boundary is not None:
        # The TOC always sits inside the front matter; never extend past the body start.
        end_index = min(end_index, front_matter_boundary - 1)
    if end_index < start_index:
        return None
    return (start_index, end_index)


def resolve_main_content_scope(
    source_registry: Sequence[Mapping[str, object]],
    preparation_diagnostic_snapshot: Mapping[str, object] | None = None,
) -> tuple[int | None, int | None, tuple[int, int] | None]:
    """Resolve the main-content span boundaries `(front_matter_boundary,
    references_region_start, bounded_toc_region)` using the SAME region provenance as
    `classify_heading_demotions` — the three `_resolve_*` helpers in the same order. A
    caller scopes to the main body by keeping only source_index in
    `[front_matter_boundary … references_region_start)` and outside `bounded_toc_region`.

    Public wrapper so other modules (e.g. the paragraph-break detector) can reuse this
    provenance without reaching into module-private helpers or duplicating the logic
    (Constitution VII: scope by region, not by per-book literal)."""
    boundary = _resolve_source_front_matter_boundary(source_registry, preparation_diagnostic_snapshot)
    toc_region = _resolve_bounded_toc_region(source_registry, preparation_diagnostic_snapshot, boundary)
    references_region_start = _resolve_references_region_start(source_registry, boundary, toc_region)
    return boundary, references_region_start, toc_region


def classify_passthrough_unmapped_source(
    payload: Mapping[str, object],
    preparation_diagnostic_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Classify each unmapped source id into an agreed pass-through category
    (bounded_toc / front_matter / page_furniture) or leave it counted. Returns category
    id-lists, counts, the retained (non-pass-through) ids, and boundary provenance."""
    unmapped_ids = _coerce_string_list(payload.get("unmapped_source_ids"))
    source_registry = _coerce_mapping_sequence(payload.get("source_registry"))
    by_id = {
        str(entry.get("paragraph_id") or "").strip(): entry
        for entry in source_registry
        if str(entry.get("paragraph_id") or "").strip()
    }
    boundary = _resolve_source_front_matter_boundary(source_registry, preparation_diagnostic_snapshot)
    toc_region = _resolve_bounded_toc_region(source_registry, preparation_diagnostic_snapshot, boundary)
    references_region_start = _confirmed_source_references_region_start(
        unmapped_ids, by_id, source_registry, boundary, toc_region
    )

    categories: dict[str, list[str]] = {
        "bounded_toc": [],
        "front_matter": [],
        "page_furniture": [],
        "references": [],
        "caption": [],
        "part": [],
        "index": [],
        "attribution": [],
    }
    retained: list[str] = []
    for paragraph_id in unmapped_ids:
        entry = by_id.get(paragraph_id)
        if entry is None:
            retained.append(paragraph_id)
            continue
        index = _coerce_int(entry.get("source_index"), default=-1)
        text = str(entry.get("text_preview") or "")
        role = _entry_role(entry)
        structural_role = str(entry.get("structural_role") or "").strip().lower()
        if _is_page_furniture_text(text):
            categories["page_furniture"].append(paragraph_id)
        elif _is_caption_text(text, role):
            categories["caption"].append(paragraph_id)
        elif _is_part_divider_text(text):
            categories["part"].append(paragraph_id)
        elif _is_attribution_text(text, role, structural_role):
            categories["attribution"].append(paragraph_id)
        elif toc_region is not None and toc_region[0] <= index <= toc_region[1]:
            categories["bounded_toc"].append(paragraph_id)
        elif boundary is not None and 0 <= index < boundary:
            categories["front_matter"].append(paragraph_id)
        elif (
            references_region_start is not None
            and index >= references_region_start
            and _is_index_row_text(text)
        ):
            categories["index"].append(paragraph_id)
        elif (
            references_region_start is not None
            and index >= references_region_start
            and not _is_substantial_body_prose(text)
        ):
            categories["references"].append(paragraph_id)
        else:
            retained.append(paragraph_id)
    return {
        "categories": categories,
        "category_counts": {key: len(value) for key, value in categories.items()},
        "passthrough_count": sum(len(value) for value in categories.values()),
        "retained_ids": retained,
        "retained_count": len(retained),
        "front_matter_boundary_source_index": boundary,
        "bounded_toc_region": list(toc_region) if toc_region is not None else None,
        "references_region_source_start_index": references_region_start,
    }


def _confirmed_source_references_region_start(
    unmapped_ids: Sequence[str],
    by_id: Mapping[str, Mapping[str, object]],
    source_registry: Sequence[Mapping[str, object]],
    front_matter_boundary: int | None,
    toc_region: tuple[int, int] | None,
) -> int | None:
    """Resolve the references-region anchor, then CONFIRM it by form: the region is
    trusted only when the majority of its own unmapped entries are non-prose
    (citations / index rows / fragments). A mid-body section literally titled "Notes"
    followed by real prose is therefore rejected — the region cannot silence body text."""
    region_start = _resolve_references_region_start(source_registry, front_matter_boundary, toc_region)
    if region_start is None:
        return None
    in_region_prose = 0
    in_region_total = 0
    for paragraph_id in unmapped_ids:
        entry = by_id.get(paragraph_id)
        if entry is None:
            continue
        if _coerce_int(entry.get("source_index"), default=-1) < region_start:
            continue
        in_region_total += 1
        if _is_substantial_body_prose(str(entry.get("text_preview") or "")):
            in_region_prose += 1
    if in_region_total == 0:
        return None
    if in_region_prose * 2 >= in_region_total:
        return None
    return region_start


def classify_passthrough_unmapped_target(
    payload: Mapping[str, object],
    preparation_diagnostic_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Target-side counterpart of `classify_passthrough_unmapped_source`. The target
    registry carries no role field, so front-matter is bounded by the source boundary
    projected through the mapping; furniture is form-only."""
    raw_indexes = payload.get("unmapped_target_indexes")
    unmapped_indexes = [
        _coerce_int(value, default=-1)
        for value in (
            raw_indexes
            if isinstance(raw_indexes, Sequence) and not isinstance(raw_indexes, (str, bytes, bytearray))
            else []
        )
    ]
    target_registry = _coerce_mapping_sequence(payload.get("target_registry"))
    source_registry = _coerce_mapping_sequence(payload.get("source_registry"))
    by_index = {
        _coerce_int(entry.get("target_index"), default=-1): entry for entry in target_registry
    }
    source_boundary = _resolve_source_front_matter_boundary(source_registry, preparation_diagnostic_snapshot)
    target_boundary = _resolve_target_front_matter_boundary(source_registry, source_boundary)
    source_toc_region = _resolve_bounded_toc_region(
        source_registry, preparation_diagnostic_snapshot, source_boundary
    )
    source_references_start = _resolve_references_region_start(
        source_registry, source_boundary, source_toc_region
    )
    target_references_boundary = _confirmed_target_references_boundary(
        unmapped_indexes, by_index, source_registry, source_references_start
    )

    categories: dict[str, list[int]] = {
        "front_matter": [],
        "page_furniture": [],
        "references": [],
        "caption": [],
        "part": [],
        "index": [],
        "attribution": [],
    }
    retained: list[int] = []
    retained_samples: list[dict[str, object]] = []
    for index in unmapped_indexes:
        entry = by_index.get(index)
        text = str(entry.get("text_preview") or "") if entry is not None else ""
        role = _entry_role(entry)
        structural_role = str((entry or {}).get("structural_role") or "").strip().lower()
        if _is_page_furniture_text(text):
            categories["page_furniture"].append(index)
        elif _is_caption_text(text, role):
            categories["caption"].append(index)
        elif _is_part_divider_text(text):
            categories["part"].append(index)
        elif _is_attribution_text(text, role, structural_role):
            categories["attribution"].append(index)
        elif target_boundary is not None and 0 <= index < target_boundary:
            categories["front_matter"].append(index)
        elif (
            target_references_boundary is not None
            and index >= target_references_boundary
            and _is_index_row_text(text)
        ):
            categories["index"].append(index)
        elif (
            target_references_boundary is not None
            and index >= target_references_boundary
            and not _is_substantial_body_prose(text)
        ):
            categories["references"].append(index)
        else:
            retained.append(index)
            retained_samples.append({"target_index": index, "text_preview": text})
    return {
        "categories": categories,
        "category_counts": {key: len(value) for key, value in categories.items()},
        "passthrough_count": sum(len(value) for value in categories.values()),
        "retained_indexes": retained,
        "retained_count": len(retained),
        "retained_samples": retained_samples,
        "front_matter_boundary_target_index": target_boundary,
        "references_region_target_start_index": target_references_boundary,
    }


def _confirmed_target_references_boundary(
    unmapped_indexes: Sequence[int],
    by_index: Mapping[int, Mapping[str, object]],
    source_registry: Sequence[Mapping[str, object]],
    source_references_start: int | None,
) -> int | None:
    """Target-side counterpart of `_confirmed_source_references_region_start`: project
    the source anchor to a target boundary, then confirm the projected region is
    non-prose-dominated before trusting it."""
    boundary = _resolve_target_references_boundary(source_registry, source_references_start)
    if boundary is None:
        return None
    in_region_prose = 0
    in_region_total = 0
    for index in unmapped_indexes:
        if index < boundary:
            continue
        in_region_total += 1
        entry = by_index.get(index)
        text = str(entry.get("text_preview") or "") if entry is not None else ""
        if _is_substantial_body_prose(text):
            in_region_prose += 1
    if in_region_total == 0:
        return None
    if in_region_prose * 2 >= in_region_total:
        return None
    return boundary


def _coerce_mapping_sequence(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _coerce_string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(float(stripped))
        except ValueError:
            return default
    return default


def _normalize_structural_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _entry_has_target_mapping(entry: Mapping[str, object] | None) -> bool:
    if entry is None:
        return False
    return entry.get("mapped_target_index") is not None


def _is_benign_opening_chapter_marker_merge(
    entry: Mapping[str, object],
    next_entry: Mapping[str, object] | None,
) -> bool:
    source_index = _coerce_int(entry.get("source_index"), default=-1)
    if source_index > 0:
        return False
    text_preview = _normalize_structural_text(str(entry.get("text_preview") or ""))
    if _CHAPTER_MARKER_TEXT_PATTERN.match(text_preview) is None:
        return False
    if not _entry_has_target_mapping(next_entry):
        return False
    next_role = str((next_entry or {}).get("role") or (next_entry or {}).get("structural_role") or "").strip().lower()
    return next_role == "heading"


def _is_benign_image_attachment_merge(
    entry: Mapping[str, object],
    previous_entry: Mapping[str, object] | None,
    next_entry: Mapping[str, object] | None,
) -> bool:
    role = str(entry.get("role") or entry.get("structural_role") or "").strip().lower()
    asset_id = str(entry.get("asset_id") or "").strip()
    text_preview = str(entry.get("text_preview") or "")

    if role == "image" and asset_id and _entry_has_target_mapping(next_entry):
        attached_asset_id = str((next_entry or {}).get("attached_to_asset_id") or "").strip()
        if attached_asset_id == asset_id:
            return True

    if _IMAGE_PLACEHOLDER_TEXT_PATTERN.search(text_preview) is None:
        return False
    if _entry_has_target_mapping(next_entry):
        next_preview = _normalize_structural_text(str((next_entry or {}).get("text_preview") or ""))
        if next_preview.startswith("рисунок ") or next_preview.startswith("figure "):
            return True
    if _entry_has_target_mapping(previous_entry):
        previous_preview = str((previous_entry or {}).get("text_preview") or "")
        if _IMAGE_PLACEHOLDER_TEXT_PATTERN.search(previous_preview) is not None:
            return True
    return False


def _is_benign_punctuation_continuation_merge(
    entry: Mapping[str, object],
    previous_entry: Mapping[str, object] | None,
) -> bool:
    role = str(entry.get("role") or entry.get("structural_role") or "").strip().lower()
    if role != "body" or not _entry_has_target_mapping(previous_entry):
        return False
    previous_role = str((previous_entry or {}).get("role") or (previous_entry or {}).get("structural_role") or "").strip().lower()
    if previous_role != "body":
        return False
    text_preview = str(entry.get("text_preview") or "").lstrip()
    return _LEADING_CONTINUATION_FRAGMENT_PATTERN.match(text_preview) is not None


def filter_benign_unmapped_source_ids(payload: Mapping[str, object]) -> list[str]:
    unmapped_source_ids = _coerce_string_list(payload.get("unmapped_source_ids"))
    if not unmapped_source_ids:
        return []

    source_registry = _coerce_mapping_sequence(payload.get("source_registry"))
    if not source_registry:
        return unmapped_source_ids

    entry_positions = {
        str(entry.get("paragraph_id") or "").strip(): index
        for index, entry in enumerate(source_registry)
        if str(entry.get("paragraph_id") or "").strip()
    }

    filtered_ids: list[str] = []
    for paragraph_id in unmapped_source_ids:
        position = entry_positions.get(paragraph_id)
        if position is None:
            filtered_ids.append(paragraph_id)
            continue
        entry = source_registry[position]
        previous_entry = source_registry[position - 1] if position > 0 else None
        next_entry = source_registry[position + 1] if position + 1 < len(source_registry) else None

        if _is_benign_opening_chapter_marker_merge(entry, next_entry):
            continue
        if _is_benign_image_attachment_merge(entry, previous_entry, next_entry):
            continue
        if _is_benign_punctuation_continuation_merge(entry, previous_entry):
            continue
        filtered_ids.append(paragraph_id)

    return filtered_ids


def resolve_filtered_formatting_unmapped_source_count(
    formatting_diagnostics: Sequence[Mapping[str, object]],
) -> tuple[int, bool]:
    max_count = 0
    benign_reduction_applied = False
    for payload in formatting_diagnostics:
        raw_ids = _coerce_string_list(payload.get("unmapped_source_ids"))
        filtered_ids = filter_benign_unmapped_source_ids(payload)
        if len(filtered_ids) != len(raw_ids):
            benign_reduction_applied = True
        max_count = max(max_count, len(filtered_ids))
    return max_count, benign_reduction_applied


def formatting_payload_format_neutral_creditable_count(payload: Mapping[str, object]) -> int | None:
    residual = payload.get("unmapped_source_residual_diagnostics")
    if not isinstance(residual, Mapping):
        return None
    effective = residual.get("effective_formatting_coverage_diagnostics")
    if not isinstance(effective, Mapping):
        return None
    if "format_neutral_creditable_count" not in effective:
        return None
    return max(0, _coerce_int(effective.get("format_neutral_creditable_count"), default=0))


def formatting_payload_target_split_accounting_creditable_count(payload: Mapping[str, object]) -> int | None:
    residual = payload.get("unmapped_target_residual_diagnostics")
    if not isinstance(residual, Mapping):
        return None
    if "split_accounting_creditable_count" not in residual:
        return None
    return max(0, _coerce_int(residual.get("split_accounting_creditable_count"), default=0))


def resolve_role_aware_formatting_unmapped_source_summary(
    formatting_diagnostics: Sequence[Mapping[str, object]],
    preparation_diagnostic_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    summaries: list[dict[str, object]] = []
    for payload in formatting_diagnostics:
        creditable_count = formatting_payload_format_neutral_creditable_count(payload)
        if creditable_count is None:
            continue
        raw_ids = _coerce_string_list(payload.get("unmapped_source_ids"))
        filtered_ids = filter_benign_unmapped_source_ids(payload)
        raw_count = len(raw_ids)
        filtered_count = len(filtered_ids)
        passthrough = classify_passthrough_unmapped_source(payload, preparation_diagnostic_snapshot)
        passthrough_count = int(passthrough["passthrough_count"])
        # The agreed pass-through reduction (front-matter / bounded-TOC / page-furniture)
        # applies only when a preparation snapshot is supplied (region signals available),
        # so existing production callers that pass none keep their prior behaviour. Use the
        # stronger of the two reducers (format-neutral credit vs agreed pass-through)
        # rather than stacking them, so a real body paragraph is never double-subtracted.
        applied_passthrough_count = passthrough_count if preparation_diagnostic_snapshot is not None else 0
        reduction = max(creditable_count, applied_passthrough_count)
        effective_count = max(filtered_count - reduction, 0)
        category_counts = passthrough["category_counts"]
        if not isinstance(category_counts, Mapping):
            category_counts = {}
        summaries.append(
            {
                "raw_unmapped_source_count": raw_count,
                "filtered_unmapped_source_count": filtered_count,
                "format_neutral_creditable_count": creditable_count,
                "passthrough_unmapped_source_count": passthrough_count,
                "passthrough_source_category_counts": passthrough["category_counts"],
                "passthrough_front_matter_source_count": int(category_counts["front_matter"]),
                "passthrough_bounded_toc_source_count": int(category_counts["bounded_toc"]),
                "passthrough_page_furniture_source_count": int(category_counts["page_furniture"]),
                "passthrough_references_source_count": int(category_counts["references"]),
                "passthrough_caption_source_count": int(category_counts["caption"]),
                "passthrough_part_source_count": int(category_counts["part"]),
                "passthrough_index_source_count": int(category_counts["index"]),
                "passthrough_attribution_source_count": int(category_counts["attribution"]),
                "front_matter_boundary_source_index": passthrough["front_matter_boundary_source_index"],
                "bounded_toc_region": passthrough["bounded_toc_region"],
                "references_region_source_start_index": passthrough["references_region_source_start_index"],
                "effective_unmapped_source_count": effective_count,
                "benign_reduction_applied": filtered_count != raw_count or applied_passthrough_count > 0,
            }
        )

    if not summaries:
        return None

    max_summary = max(summaries, key=lambda item: int(item["effective_unmapped_source_count"]))
    return {
        **max_summary,
        "unmapped_source_count_basis": "role_aware_formatting_coverage",
        "payload_count": len(summaries),
        "counting_note": "filtered_raw_unmapped_source_count minus format_neutral_creditable_count, floored at zero",
    }


def resolve_role_aware_formatting_unmapped_target_summary(
    formatting_diagnostics: Sequence[Mapping[str, object]],
    preparation_diagnostic_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    summaries: list[dict[str, object]] = []
    for payload in formatting_diagnostics:
        creditable_count = formatting_payload_target_split_accounting_creditable_count(payload)
        if creditable_count is None:
            continue
        raw_indexes = payload.get("unmapped_target_indexes")
        raw_count = len(raw_indexes) if isinstance(raw_indexes, Sequence) and not isinstance(raw_indexes, (str, bytes, bytearray)) else 0
        passthrough = classify_passthrough_unmapped_target(payload, preparation_diagnostic_snapshot)
        passthrough_count = int(passthrough["passthrough_count"])
        applied_passthrough_count = passthrough_count if preparation_diagnostic_snapshot is not None else 0
        reduction = max(creditable_count, applied_passthrough_count)
        effective_count = max(raw_count - reduction, 0)
        category_counts = passthrough["category_counts"]
        if not isinstance(category_counts, Mapping):
            category_counts = {}
        # spec 011: thread the winning payload's genuinely-unmapped (retained) target
        # samples outward via **max_summary so the production emitter can itemize them.
        # Capped to the first 8, mirroring the source cap at late_phases.py:2670; the
        # winning payload only (consistent with the count).
        retained_samples_value = passthrough["retained_samples"]
        retained_target_samples = (
            list(retained_samples_value[:8]) if isinstance(retained_samples_value, list) else []
        )
        summaries.append(
            {
                "raw_unmapped_target_count": raw_count,
                "target_split_accounting_creditable_count": creditable_count,
                "passthrough_unmapped_target_count": passthrough_count,
                "passthrough_target_category_counts": passthrough["category_counts"],
                "passthrough_front_matter_target_count": int(category_counts["front_matter"]),
                "passthrough_page_furniture_target_count": int(category_counts["page_furniture"]),
                "passthrough_references_target_count": int(category_counts["references"]),
                "passthrough_caption_target_count": int(category_counts["caption"]),
                "passthrough_part_target_count": int(category_counts["part"]),
                "passthrough_index_target_count": int(category_counts["index"]),
                "passthrough_attribution_target_count": int(category_counts["attribution"]),
                "front_matter_boundary_target_index": passthrough["front_matter_boundary_target_index"],
                "references_region_target_start_index": passthrough["references_region_target_start_index"],
                "effective_unmapped_target_count": effective_count,
                "benign_reduction_applied": creditable_count > 0 or applied_passthrough_count > 0,
                "retained_target_count": _coerce_int(passthrough["retained_count"]),
                "retained_target_samples": retained_target_samples,
            }
        )

    if not summaries:
        return None

    max_summary = max(summaries, key=lambda item: int(item["effective_unmapped_target_count"]))
    return {
        **max_summary,
        "unmapped_target_count_basis": "role_aware_formatting_coverage",
        "payload_count": len(summaries),
        "counting_note": "raw_unmapped_target_count minus split_accounting_creditable_count, floored at zero",
    }
