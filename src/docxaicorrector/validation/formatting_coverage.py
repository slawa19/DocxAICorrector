from __future__ import annotations

import re
from collections.abc import Mapping, Sequence


_CHAPTER_MARKER_TEXT_PATTERN = re.compile(r"^(?:chapter|глава)\s+(?:\d+|[ivxlcdm]+)\b[ .:-]*$", re.IGNORECASE)
_IMAGE_PLACEHOLDER_TEXT_PATTERN = re.compile(r"\[\[docx_image_[^\]]+\]\]", re.IGNORECASE)
_LEADING_CONTINUATION_FRAGMENT_PATTERN = re.compile(r"^[,.;:!?…)\]»]\s*\S")


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


def resolve_role_aware_formatting_unmapped_source_summary(
    formatting_diagnostics: Sequence[Mapping[str, object]],
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
        effective_count = max(filtered_count - creditable_count, 0)
        summaries.append(
            {
                "raw_unmapped_source_count": raw_count,
                "filtered_unmapped_source_count": filtered_count,
                "format_neutral_creditable_count": creditable_count,
                "effective_unmapped_source_count": effective_count,
                "benign_reduction_applied": filtered_count != raw_count,
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
