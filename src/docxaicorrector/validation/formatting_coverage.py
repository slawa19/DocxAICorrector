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

    categories: dict[str, list[str]] = {"bounded_toc": [], "front_matter": [], "page_furniture": []}
    retained: list[str] = []
    for paragraph_id in unmapped_ids:
        entry = by_id.get(paragraph_id)
        if entry is None:
            retained.append(paragraph_id)
            continue
        index = _coerce_int(entry.get("source_index"), default=-1)
        text = str(entry.get("text_preview") or "")
        if _is_page_furniture_text(text):
            categories["page_furniture"].append(paragraph_id)
        elif toc_region is not None and toc_region[0] <= index <= toc_region[1]:
            categories["bounded_toc"].append(paragraph_id)
        elif boundary is not None and 0 <= index < boundary:
            categories["front_matter"].append(paragraph_id)
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
    }


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

    categories: dict[str, list[int]] = {"front_matter": [], "page_furniture": []}
    retained: list[int] = []
    for index in unmapped_indexes:
        entry = by_index.get(index)
        text = str(entry.get("text_preview") or "") if entry is not None else ""
        if _is_page_furniture_text(text):
            categories["page_furniture"].append(index)
        elif target_boundary is not None and 0 <= index < target_boundary:
            categories["front_matter"].append(index)
        else:
            retained.append(index)
    return {
        "categories": categories,
        "category_counts": {key: len(value) for key, value in categories.items()},
        "passthrough_count": sum(len(value) for value in categories.values()),
        "retained_indexes": retained,
        "retained_count": len(retained),
        "front_matter_boundary_target_index": target_boundary,
    }


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
        summaries.append(
            {
                "raw_unmapped_source_count": raw_count,
                "filtered_unmapped_source_count": filtered_count,
                "format_neutral_creditable_count": creditable_count,
                "passthrough_unmapped_source_count": passthrough_count,
                "passthrough_source_category_counts": passthrough["category_counts"],
                "passthrough_front_matter_source_count": int(passthrough["category_counts"]["front_matter"]),
                "passthrough_bounded_toc_source_count": int(passthrough["category_counts"]["bounded_toc"]),
                "passthrough_page_furniture_source_count": int(passthrough["category_counts"]["page_furniture"]),
                "front_matter_boundary_source_index": passthrough["front_matter_boundary_source_index"],
                "bounded_toc_region": passthrough["bounded_toc_region"],
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
        summaries.append(
            {
                "raw_unmapped_target_count": raw_count,
                "target_split_accounting_creditable_count": creditable_count,
                "passthrough_unmapped_target_count": passthrough_count,
                "passthrough_target_category_counts": passthrough["category_counts"],
                "passthrough_front_matter_target_count": int(passthrough["category_counts"]["front_matter"]),
                "passthrough_page_furniture_target_count": int(passthrough["category_counts"]["page_furniture"]),
                "front_matter_boundary_target_index": passthrough["front_matter_boundary_target_index"],
                "effective_unmapped_target_count": effective_count,
                "benign_reduction_applied": creditable_count > 0 or applied_passthrough_count > 0,
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
