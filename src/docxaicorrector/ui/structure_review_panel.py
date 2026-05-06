from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Mapping, Protocol, TypedDict, cast

import streamlit as st

from docxaicorrector.core.logger import log_event
from docxaicorrector.runtime.state import (
    get_active_segment_id,
    get_confirmed_at_settings_hash,
    get_confirmed_structure_fingerprint,
    get_segment_progress_by_id,
    get_segment_status_by_id,
    get_segments_loaded_for_source_token,
    get_selected_segment_ids,
    get_structure_confirmed,
    get_structure_manifest_notice_details,
    get_structure_manifest_notice_token,
    set_selected_segment_ids,
    set_structure_confirmation_state,
)


class SegmentLike(Protocol):
    segment_id: str
    parent_segment_id: str | None
    level: int
    title: str
    word_count: int
    confidence: str
    structural_role: str
    warnings: tuple[str, ...]
    boundary_evidence: tuple[object, ...]
    boundary_fingerprint: str
    paragraph_ids: tuple[str, ...]
    start_paragraph_index: int
    end_paragraph_index: int


class StructureReviewState(TypedDict):
    segment_ids: list[str]
    selected_segment_ids: list[str]
    structure_confirmed: bool
    settings_hash: str
    fingerprint: str
    confirmation_invalidated: bool
    confirmed_fingerprint_before_invalidation: str
    fingerprint_changed: bool
    settings_changed: bool


class SelectedProcessingPayload(TypedDict):
    selected_segment_ids: list[str]
    jobs: list[dict[str, object]]
    source_paragraphs: list[object]
    image_assets: list[object]


class EffectiveSelectedProcessingState(TypedDict):
    payload: SelectedProcessingPayload
    effective_selected_segment_ids: list[str]
    effective_selected_segments: list[SegmentLike]
    selected_word_count: int
    selected_job_count: int
    excluded_locked_segment_ids: list[str]


def _show_notice(*, level: str, message: str) -> None:
    if level == "warning":
        st.warning(message)
        return
    if level == "caption":
        st.caption(message)
        return
    if level == "info":
        st.info(message)
        return
    raise ValueError(f"Unsupported Streamlit notice level: {level}")


def _get_prepared_segments(prepared_run_context: object) -> list[SegmentLike]:
    return cast(list[SegmentLike], list(getattr(prepared_run_context, "segments", None) or []))


def _build_structure_settings_hash(
    *,
    uploaded_file_token: str,
    prepared_run_context,
    chunk_size: int,
    app_config: Mapping[str, object] | None = None,
) -> str:
    resolved_app_config = dict(app_config or {})
    payload = {
        "uploaded_file_token": uploaded_file_token,
        "structure_fingerprint": str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
        "detector_version": str(getattr(prepared_run_context, "detector_version", "") or ""),
        "structure_recognition_mode": str(getattr(prepared_run_context, "structure_recognition_mode", "off") or "off"),
        "chunk_size": int(chunk_size or 0),
        "source_format": str(getattr(prepared_run_context, "source_format", "docx") or "docx"),
        "conversion_backend": str(getattr(prepared_run_context, "conversion_backend", "") or ""),
        "paragraph_boundary_normalization_enabled": bool(
            resolved_app_config.get("paragraph_boundary_normalization_enabled", True)
        ),
        "paragraph_boundary_normalization_mode": str(
            resolved_app_config.get("paragraph_boundary_normalization_mode", "high_only") or "high_only"
        ),
        "paragraph_boundary_ai_review_enabled": bool(
            resolved_app_config.get("paragraph_boundary_ai_review_enabled", False)
        ),
        "paragraph_boundary_ai_review_mode": str(
            resolved_app_config.get("paragraph_boundary_ai_review_mode", "off") or "off"
        ),
        "structure_recognition_min_confidence": str(
            resolved_app_config.get("structure_recognition_min_confidence", "medium") or "medium"
        ),
        "structure_validation_enabled": bool(resolved_app_config.get("structure_validation_enabled", True)),
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def _sync_structure_review_state(
    *,
    prepared_run_context,
    uploaded_file_token: str,
    chunk_size: int,
    app_config: Mapping[str, object] | None = None,
    build_structure_settings_hash_fn=None,
) -> StructureReviewState:
    segments = _get_prepared_segments(prepared_run_context)
    segment_ids = [
        str(getattr(segment, "segment_id", "") or "")
        for segment in segments
        if str(getattr(segment, "segment_id", "") or "").strip()
    ]
    hash_builder = build_structure_settings_hash_fn or _build_structure_settings_hash
    current_settings_hash = hash_builder(
        uploaded_file_token=uploaded_file_token,
        prepared_run_context=prepared_run_context,
        chunk_size=chunk_size,
        app_config=app_config,
    )
    current_fingerprint = str(getattr(prepared_run_context, "structure_fingerprint", "") or "")
    loaded_token = get_segments_loaded_for_source_token()
    selected_segment_ids = get_selected_segment_ids()
    if loaded_token != uploaded_file_token:
        set_selected_segment_ids(segment_ids)
        set_structure_confirmation_state(
            structure_confirmed=False,
            confirmed_structure_fingerprint="",
            confirmed_at_settings_hash="",
            segments_loaded_for_source_token=uploaded_file_token,
        )
        selected_segment_ids = segment_ids
    else:
        normalized_selected = [segment_id for segment_id in selected_segment_ids if segment_id in set(segment_ids)]
        if normalized_selected != selected_segment_ids:
            set_selected_segment_ids(normalized_selected)
            selected_segment_ids = normalized_selected
    structure_confirmed = get_structure_confirmed()
    confirmed_fingerprint = get_confirmed_structure_fingerprint()
    confirmed_settings_hash = get_confirmed_at_settings_hash()
    confirmation_invalidated = False
    fingerprint_changed = structure_confirmed and confirmed_fingerprint != current_fingerprint
    settings_changed = structure_confirmed and confirmed_settings_hash != current_settings_hash
    if structure_confirmed and (fingerprint_changed or settings_changed):
        set_structure_confirmation_state(
            structure_confirmed=False,
            confirmed_structure_fingerprint="",
            confirmed_at_settings_hash="",
            segments_loaded_for_source_token=uploaded_file_token,
        )
        structure_confirmed = False
        confirmation_invalidated = True
    return {
        "segment_ids": segment_ids,
        "selected_segment_ids": selected_segment_ids,
        "structure_confirmed": structure_confirmed,
        "settings_hash": current_settings_hash,
        "fingerprint": current_fingerprint,
        "confirmation_invalidated": confirmation_invalidated,
        "confirmed_fingerprint_before_invalidation": confirmed_fingerprint,
        "fingerprint_changed": fingerprint_changed,
        "settings_changed": settings_changed,
    }


def _build_structure_invalidation_summary(review_state: StructureReviewState) -> str:
    if not bool(review_state.get("confirmation_invalidated", False)):
        return ""
    previous_fingerprint = str(review_state.get("confirmed_fingerprint_before_invalidation", "") or "")
    current_fingerprint = str(review_state.get("fingerprint", "") or "")
    fingerprint_changed = bool(review_state.get("fingerprint_changed", False))
    settings_changed = bool(review_state.get("settings_changed", False))
    summary_lines = ["Structure confirmation invalidated."]
    if previous_fingerprint:
        summary_lines.append(f"Previous confirmed fingerprint: {previous_fingerprint}")
    summary_lines.append(f"Current fingerprint: {current_fingerprint or 'n/a'}")
    if fingerprint_changed:
        summary_lines.append("Detected chapter structure changed after re-analysis.")
    if settings_changed:
        summary_lines.append("Detection-affecting settings changed since the last confirmation.")
    summary_lines.append("Review the chapter list and confirm structure again before processing selected chapters.")
    return "\n".join(summary_lines)


def _coerce_segment_preview_text(paragraph: object) -> str:
    if isinstance(paragraph, str):
        return " ".join(paragraph.strip().split())
    for attribute_name in ("rendered_text", "text"):
        value = str(getattr(paragraph, attribute_name, "") or "").strip()
        if value:
            return " ".join(value.split())
    return " ".join(str(paragraph or "").strip().split())


def _truncate_segment_preview(text: str, *, limit: int = 120) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return "n/a"
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def _resolve_segment_preview(paragraphs: list[object], paragraph_index: int) -> str:
    if paragraph_index < 0 or paragraph_index >= len(paragraphs):
        return "n/a"
    return _truncate_segment_preview(_coerce_segment_preview_text(paragraphs[paragraph_index]))


def _coerce_segment_index(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _format_segment_evidence_line(evidence: object) -> str:
    source = str(getattr(evidence, "source", "fallback") or "fallback")
    confidence = str(getattr(evidence, "confidence", "low") or "low")
    details = getattr(evidence, "details", {}) or {}
    details_suffix = ""
    if isinstance(details, dict) and details:
        detail_parts = [f"{key}={details[key]}" for key in sorted(details)]
        details_suffix = " | " + ", ".join(detail_parts)
    return f"{source} | confidence={confidence}{details_suffix}"


def _build_selected_processing_payload(
    *,
    prepared_run_context,
    selected_segment_ids: list[str] | None,
    segment_status_by_id: dict[str, str] | None = None,
) -> SelectedProcessingPayload:
    segments = _get_prepared_segments(prepared_run_context)
    parent_to_children_map = _build_segment_parent_to_children_map(segments)
    expanded_selected_segment_ids = _expand_segment_ids_for_selection(
        segment_ids=[str(segment_id).strip() for segment_id in (selected_segment_ids or []) if str(segment_id).strip()],
        parent_to_children_map=parent_to_children_map,
        segment_status_by_id=dict(segment_status_by_id or {}),
        include_locked=False,
    )
    selected_segment_id_set = set(expanded_selected_segment_ids)
    if not selected_segment_id_set:
        return {
            "selected_segment_ids": [],
            "jobs": [],
            "source_paragraphs": [],
            "image_assets": [],
        }

    selected_segments = [segment for segment in segments if segment.segment_id in selected_segment_id_set]
    selected_paragraph_ids = {
        str(paragraph_id).strip()
        for segment in selected_segments
        for paragraph_id in getattr(segment, "paragraph_ids", ()) or ()
        if str(paragraph_id).strip()
    }
    segment_to_job = dict(getattr(prepared_run_context, "segment_to_job", {}) or {})
    selected_job_indexes = sorted(
        {
            int(job_index)
            for segment in selected_segments
            for job_index in (segment_to_job.get(segment.segment_id, ()) or ())
        }
    )
    all_jobs = list(getattr(prepared_run_context, "jobs", []) or [])
    filtered_jobs = [all_jobs[job_index] for job_index in selected_job_indexes if 0 <= job_index < len(all_jobs)]
    all_paragraphs = list(getattr(prepared_run_context, "paragraphs", []) or [])
    filtered_paragraphs = [
        paragraph
        for paragraph in all_paragraphs
        if str(getattr(paragraph, "paragraph_id", "") or "").strip() in selected_paragraph_ids
    ]
    selected_asset_ids = {
        str(asset_id).strip()
        for paragraph in filtered_paragraphs
        for asset_id in (
            getattr(paragraph, "asset_id", None),
            getattr(paragraph, "attached_to_asset_id", None),
        )
        if str(asset_id or "").strip()
    }
    filtered_image_assets = [
        asset
        for asset in list(getattr(prepared_run_context, "image_assets", []) or [])
        if str(getattr(asset, "image_id", "") or "").strip() in selected_asset_ids
    ]
    return {
        "selected_segment_ids": [segment.segment_id for segment in selected_segments],
        "jobs": filtered_jobs,
        "source_paragraphs": filtered_paragraphs,
        "image_assets": filtered_image_assets,
    }


def _build_effective_selected_processing_state(
    *,
    prepared_run_context,
    selected_segment_ids: list[str] | None,
    segment_status_by_id: dict[str, str] | None = None,
) -> EffectiveSelectedProcessingState:
    payload = _build_selected_processing_payload(
        prepared_run_context=prepared_run_context,
        selected_segment_ids=selected_segment_ids,
        segment_status_by_id=segment_status_by_id,
    )
    segments = _get_prepared_segments(prepared_run_context)
    effective_selected_segment_ids = [
        str(segment_id).strip() for segment_id in payload["selected_segment_ids"] if str(segment_id).strip()
    ]
    effective_selected_segment_id_set = set(effective_selected_segment_ids)
    effective_selected_segments = [
        segment for segment in segments if str(getattr(segment, "segment_id", "") or "") in effective_selected_segment_id_set
    ]
    selected_word_count = sum(int(getattr(segment, "word_count", 0) or 0) for segment in effective_selected_segments)
    selected_job_count = len(payload["jobs"])

    parent_to_children_map = _build_segment_parent_to_children_map(segments)
    expanded_with_locked = _expand_segment_ids_for_selection(
        segment_ids=[str(segment_id).strip() for segment_id in (selected_segment_ids or []) if str(segment_id).strip()],
        parent_to_children_map=parent_to_children_map,
        segment_status_by_id=dict(segment_status_by_id or {}),
        include_locked=True,
    )
    excluded_locked_segment_ids = [
        segment_id for segment_id in expanded_with_locked if segment_id not in effective_selected_segment_id_set
    ]
    return {
        "payload": payload,
        "effective_selected_segment_ids": effective_selected_segment_ids,
        "effective_selected_segments": effective_selected_segments,
        "selected_word_count": selected_word_count,
        "selected_job_count": selected_job_count,
        "excluded_locked_segment_ids": excluded_locked_segment_ids,
    }


def _count_segment_descendant_jobs(*, segment_id: str, parent_to_children_map: dict[str, list[str]], segment_to_job: dict[str, tuple[int, ...]]) -> int:
    return sum(
        len(segment_to_job.get(descendant_segment_id, ()) or ())
        for descendant_segment_id in _collect_descendant_segment_ids(
            segment_id=segment_id,
            parent_to_children_map=parent_to_children_map,
        )
    )


def _build_segment_runtime_badge(segment_status: str, segment_progress: float) -> str:
    normalized_status = str(segment_status or "pending").strip().lower() or "pending"
    progress_percent = int(max(0.0, min(float(segment_progress or 0.0), 1.0)) * 100)
    if normalized_status == "completed":
        return f"completed {progress_percent}%"
    if normalized_status == "processing":
        return f"processing {progress_percent}%"
    if normalized_status == "failed":
        return f"failed {progress_percent}%"
    if normalized_status == "queued":
        return f"queued {progress_percent}%"
    return normalized_status


def _build_segment_status_summary_line(*, segments: list[SegmentLike], segment_status_by_id: dict[str, str]) -> str:
    if not segments:
        return ""
    ordered_statuses = ("pending", "queued", "processing", "completed", "failed", "skipped")
    counts = {status: 0 for status in ordered_statuses}
    for segment in segments:
        segment_id = str(getattr(segment, "segment_id", "") or "").strip()
        if not segment_id:
            continue
        normalized_status = str(segment_status_by_id.get(segment_id, "pending") or "pending").strip().lower() or "pending"
        if normalized_status not in counts:
            continue
        counts[normalized_status] += 1
    fragments = [f"{status} {count}" for status, count in counts.items() if count > 0]
    if not fragments:
        return ""
    return "Segment status summary: " + " | ".join(fragments)


def _build_selected_segment_status_summary_line(*, selected_segments: list[SegmentLike], segment_status_by_id: dict[str, str]) -> str:
    if not selected_segments:
        return ""
    ordered_statuses = ("pending", "queued", "processing", "completed", "failed", "skipped")
    counts = {status: 0 for status in ordered_statuses}
    for segment in selected_segments:
        segment_id = str(getattr(segment, "segment_id", "") or "").strip()
        if not segment_id:
            continue
        normalized_status = _normalize_segment_status(segment_status_by_id.get(segment_id, "pending"))
        if normalized_status not in counts:
            continue
        counts[normalized_status] += 1
    fragments = [f"{status} {count}" for status, count in counts.items() if count > 0]
    if not fragments:
        return ""
    return "Selected segment statuses: " + " | ".join(fragments)


def _normalize_segment_status(value: object) -> str:
    return str(value or "pending").strip().lower() or "pending"


def _can_build_final_translated_book(*, segments: list[SegmentLike], segment_status_by_id: dict[str, str]) -> bool:
    required_segment_ids = [
        segment_id
        for segment_id in (str(getattr(segment, "segment_id", "") or "").strip() for segment in segments)
        if segment_id and _normalize_segment_status(segment_status_by_id.get(segment_id, "pending")) != "skipped"
    ]
    if not required_segment_ids:
        return False
    return all(
        _normalize_segment_status(segment_status_by_id.get(segment_id, "pending")) == "completed"
        for segment_id in required_segment_ids
    )


def _is_segment_selection_locked(segment_status: str) -> bool:
    return _normalize_segment_status(segment_status) in {"queued", "processing"}


def _build_bulk_selectable_segment_ids(*, visible_segments: list[SegmentLike], segment_status_by_id: dict[str, str]) -> list[str]:
    selectable_segment_ids: list[str] = []
    for segment in visible_segments:
        segment_id = str(getattr(segment, "segment_id", "") or "").strip()
        if not segment_id:
            continue
        if _is_segment_selection_locked(segment_status_by_id.get(segment_id, "pending")):
            continue
        selectable_segment_ids.append(segment_id)
    return selectable_segment_ids


def _build_segment_parent_to_children_map(segments: list[SegmentLike]) -> dict[str, list[str]]:
    parent_to_children_map: dict[str, list[str]] = {}
    for segment in segments:
        segment_id = str(getattr(segment, "segment_id", "") or "").strip()
        parent_segment_id = str(getattr(segment, "parent_segment_id", "") or "").strip()
        if not segment_id or not parent_segment_id:
            continue
        parent_to_children_map.setdefault(parent_segment_id, []).append(segment_id)
    return parent_to_children_map


def _build_segment_lookup(segments: list[SegmentLike]) -> dict[str, SegmentLike]:
    return {
        segment_id: segment
        for segment in segments
        for segment_id in [str(getattr(segment, "segment_id", "") or "").strip()]
        if segment_id
    }


def _collect_descendant_segment_ids(*, segment_id: str, parent_to_children_map: dict[str, list[str]]) -> list[str]:
    descendants: list[str] = []
    pending = list(parent_to_children_map.get(segment_id, ()))
    seen: set[str] = set()
    while pending:
        current_segment_id = pending.pop(0)
        if current_segment_id in seen:
            continue
        seen.add(current_segment_id)
        descendants.append(current_segment_id)
        pending.extend(parent_to_children_map.get(current_segment_id, ()))
    return descendants


def _expand_segment_ids_for_selection(
    *,
    segment_ids: list[str],
    parent_to_children_map: dict[str, list[str]],
    segment_status_by_id: dict[str, str],
    include_locked: bool,
) -> list[str]:
    expanded_segment_ids: list[str] = []
    seen: set[str] = set()
    for segment_id in segment_ids:
        for candidate_segment_id in [segment_id, *_collect_descendant_segment_ids(segment_id=segment_id, parent_to_children_map=parent_to_children_map)]:
            if candidate_segment_id in seen:
                continue
            if not include_locked and _is_segment_selection_locked(segment_status_by_id.get(candidate_segment_id, "pending")):
                continue
            seen.add(candidate_segment_id)
            expanded_segment_ids.append(candidate_segment_id)
    return expanded_segment_ids


def _build_segment_relation_fragment(
    *,
    segment: SegmentLike,
    segment_lookup: dict[str, SegmentLike],
    parent_to_children_map: dict[str, list[str]],
) -> str:
    segment_id = str(getattr(segment, "segment_id", "") or "").strip()
    parent_segment_id = str(getattr(segment, "parent_segment_id", "") or "").strip()
    if parent_segment_id:
        parent_segment = segment_lookup.get(parent_segment_id)
        parent_title = str(getattr(parent_segment, "title", "") or "").strip()
        if parent_title:
            return f" | parent: {parent_title}"
        return f" | parent: {parent_segment_id}"
    descendant_count = len(_collect_descendant_segment_ids(segment_id=segment_id, parent_to_children_map=parent_to_children_map))
    if descendant_count > 0:
        return f" | +{descendant_count} descendants"
    return ""


def _build_segment_title_prefix(level: object) -> str:
    try:
        normalized_level = max(1, int(cast(Any, level)))
    except (TypeError, ValueError):
        normalized_level = 1
    if normalized_level <= 1:
        return ""
    return "  " * (normalized_level - 1) + "- "


def _count_selected_descendant_coverage(*, selected_segment_ids: list[str], segment_lookup: dict[str, SegmentLike]) -> int:
    selected_segment_id_set = {segment_id for segment_id in selected_segment_ids if segment_id}
    covered_descendant_count = 0
    for segment_id in selected_segment_id_set:
        current_segment = segment_lookup.get(segment_id)
        seen: set[str] = set()
        while current_segment is not None:
            parent_segment_id = str(getattr(current_segment, "parent_segment_id", "") or "").strip()
            if not parent_segment_id or parent_segment_id in seen:
                break
            if parent_segment_id in selected_segment_id_set:
                covered_descendant_count += 1
                break
            seen.add(parent_segment_id)
            current_segment = segment_lookup.get(parent_segment_id)
    return covered_descendant_count


def _build_structure_confirmation_summary(
    *,
    structure_confirmed: bool,
    selected_segment_ids: list[str],
    segment_lookup: dict[str, SegmentLike],
    review_state: StructureReviewState,
) -> str:
    current_fingerprint = str(review_state.get("fingerprint", "") or "")
    if not structure_confirmed:
        return "Structure not confirmed. Process Selected stays disabled until the current outline is reviewed and confirmed."
    selected_top_level_count = 0
    selected_nested_count = 0
    for segment_id in selected_segment_ids:
        segment = segment_lookup.get(segment_id)
        if segment is None:
            continue
        parent_segment_id = str(getattr(segment, "parent_segment_id", "") or "").strip()
        if parent_segment_id:
            selected_nested_count += 1
        else:
            selected_top_level_count += 1
    return (
        f"Structure confirmed for fingerprint {current_fingerprint or 'n/a'} | "
        f"selected top-level {selected_top_level_count} | selected nested {selected_nested_count}"
    )


def _build_selected_segment_structure_summary(*, selected_segments: list[SegmentLike]) -> str:
    if not selected_segments:
        return ""
    top_level_count = 0
    nested_count = 0
    for segment in selected_segments:
        parent_segment_id = str(getattr(segment, "parent_segment_id", "") or "").strip()
        if parent_segment_id:
            nested_count += 1
        else:
            top_level_count += 1
    return f"Selected structure: top-level {top_level_count} | nested {nested_count}"


def _build_manifest_comparison_notice(
    *,
    uploaded_file_token: str,
    current_fingerprint: str,
    current_manifest_path: str,
) -> tuple[str, str] | None:
    manifest_notice = get_structure_manifest_notice_details()
    if not isinstance(manifest_notice, dict):
        return None
    if get_structure_manifest_notice_token() != uploaded_file_token:
        return None
    manifest_path = str(manifest_notice.get("manifest_path", "") or "").strip()
    exported_fingerprint = str(manifest_notice.get("structure_fingerprint", "") or "").strip()
    if not manifest_path:
        return None
    if current_manifest_path and manifest_path == current_manifest_path and (not exported_fingerprint or exported_fingerprint == current_fingerprint):
        return None
    if exported_fingerprint and current_fingerprint and exported_fingerprint != current_fingerprint:
        return (
            "warning",
            "Current analysis differs from the last exported structure manifest.\n"
            f"Manifest path: {manifest_path}\n"
            f"Exported fingerprint: {exported_fingerprint}\n"
            f"Current fingerprint: {current_fingerprint}",
        )
    match_suffix = " | fingerprint matches current analysis" if exported_fingerprint and exported_fingerprint == current_fingerprint else ""
    fingerprint_suffix = f" | fingerprint {exported_fingerprint}" if exported_fingerprint else ""
    return ("caption", f"Last exported manifest: {manifest_path}{fingerprint_suffix}{match_suffix}")


def _build_process_selected_unavailable_note(
    *,
    structure_confirmed: bool,
    selected_segment_ids: list[str],
    selected_job_count: int,
) -> str:
    if not structure_confirmed and not selected_segment_ids:
        return "Process Selected unavailable: confirm the current outline and keep at least one selectable segment selected."
    if not structure_confirmed:
        return "Process Selected unavailable: confirm the current outline before running the current chapter selection."
    if not selected_segment_ids:
        return "Process Selected unavailable: keep at least one selectable segment selected."
    if selected_job_count <= 0:
        return "Process Selected unavailable: the current selection does not resolve to any selectable jobs."
    return ""


def _segment_matches_review_filters(
    *,
    segment: SegmentLike,
    segment_status_by_id: dict[str, str],
    status_filter: str,
    search_query: str,
) -> bool:
    normalized_filter = str(status_filter or "all").strip().lower() or "all"
    normalized_query = " ".join(str(search_query or "").strip().lower().split())
    segment_status = _normalize_segment_status(
        segment_status_by_id.get(str(getattr(segment, "segment_id", "") or ""), "pending")
    )
    segment_title = " ".join(str(getattr(segment, "title", "") or "").strip().lower().split())
    segment_warning_text = " ".join(
        str(item).strip().lower()
        for item in (getattr(segment, "warnings", ()) or ())
        if str(item).strip()
    )
    if normalized_filter == "low_confidence":
        if str(getattr(segment, "confidence", "") or "").strip().lower() != "low":
            return False
    elif normalized_filter != "all" and segment_status != normalized_filter:
        return False
    if not normalized_query:
        return True
    return normalized_query in segment_title or normalized_query in segment_warning_text


def _build_visible_structure_summary(*, visible_segments: list[SegmentLike]) -> str:
    if not visible_segments:
        return ""
    total_visible = len(visible_segments)
    parent_visible = sum(
        1
        for segment in visible_segments
        if not str(getattr(segment, "parent_segment_id", "") or "").strip()
    )
    child_visible = max(0, total_visible - parent_visible)
    max_level = 1
    for segment in visible_segments:
        try:
            max_level = max(max_level, int(getattr(segment, "level", 1) or 1))
        except (TypeError, ValueError):
            continue
    if child_visible <= 0 and max_level <= 1:
        return ""
    return f"Visible structure: {parent_visible} top-level | {child_visible} nested | max level {max_level}"


def _build_segment_status_hint(segment_status: str) -> str:
    normalized_status = _normalize_segment_status(segment_status)
    if normalized_status == "completed":
        return "Completed in this session. This segment can be selected again for reprocess/export later."
    if normalized_status == "failed":
        return "Failed in this session. Retry UI is not available yet in the current phase."
    if normalized_status == "skipped":
        return "Skipped in the current session workflow. Usually excluded by default."
    return ""


def _render_analysis_review_panel(
    *,
    prepared_run_context,
    uploaded_file_token: str,
    chunk_size: int,
    app_config: Mapping[str, object] | None = None,
    build_structure_settings_hash_fn=None,
    log_event_fn=log_event,
) -> str | None:
    segments = _get_prepared_segments(prepared_run_context)
    if not segments:
        return None
    review_state = _sync_structure_review_state(
        prepared_run_context=prepared_run_context,
        uploaded_file_token=uploaded_file_token,
        chunk_size=chunk_size,
        app_config=app_config,
        build_structure_settings_hash_fn=build_structure_settings_hash_fn,
    )
    selected_segment_ids = list(review_state["selected_segment_ids"])
    structure_confirmed = bool(review_state["structure_confirmed"])
    invalidation_summary = _build_structure_invalidation_summary(review_state)
    if invalidation_summary:
        st.warning(invalidation_summary)

    st.subheader("Chapter Selector")
    st.caption(f"Structure fingerprint: {review_state['fingerprint'] or 'n/a'}")
    st.caption(f"Detector version: {str(getattr(prepared_run_context, 'detector_version', '') or 'n/a')}")
    diagnostics = getattr(prepared_run_context, "segment_diagnostics", None)
    if diagnostics is not None:
        st.info(
            f"Detected segments: {len(segments)} | Confidence H/M/L: "
            f"{int(getattr(diagnostics, 'high_confidence_count', 0) or 0)}/"
            f"{int(getattr(diagnostics, 'medium_confidence_count', 0) or 0)}/"
            f"{int(getattr(diagnostics, 'low_confidence_count', 0) or 0)} | "
            f"TOC matched: {int(getattr(diagnostics, 'toc_matched_count', 0) or 0)}/"
            f"{int(getattr(diagnostics, 'toc_entry_count', 0) or 0)}"
        )
        diagnostic_warnings = tuple(str(item).strip() for item in getattr(diagnostics, "warnings", ()) if str(item).strip())
        if diagnostic_warnings:
            st.warning("Structure warnings: " + "; ".join(diagnostic_warnings))

    manifest_path = str(getattr(prepared_run_context, "exported_structure_manifest_path", "") or "")
    if manifest_path:
        st.caption(f"Manifest path: {manifest_path}")
    manifest_comparison_notice = _build_manifest_comparison_notice(
        uploaded_file_token=uploaded_file_token,
        current_fingerprint=str(review_state["fingerprint"]),
        current_manifest_path=manifest_path,
    )
    if manifest_comparison_notice is not None:
        notice_level, notice_message = manifest_comparison_notice
        _show_notice(level=notice_level, message=notice_message)

    segment_status_by_id = get_segment_status_by_id()
    segment_progress_by_id = get_segment_progress_by_id()
    active_segment_id = get_active_segment_id()
    parent_to_children_map = _build_segment_parent_to_children_map(segments)
    segment_lookup = _build_segment_lookup(segments)
    search_query = str(st.session_state.get("chapter_selector_search", "") or "")
    status_filter_options = {
        "All segments": "all",
        "Pending": "pending",
        "Queued": "queued",
        "Processing": "processing",
        "Completed": "completed",
        "Failed": "failed",
        "Skipped": "skipped",
        "Low confidence": "low_confidence",
    }
    filter_labels = list(status_filter_options.keys())
    current_filter_value = str(st.session_state.get("chapter_selector_filter", "all") or "all")
    current_filter_label = next(
        (label for label, value in status_filter_options.items() if value == current_filter_value),
        "All segments",
    )
    selected_filter_label = st.selectbox(
        "Status Filter",
        filter_labels,
        index=filter_labels.index(current_filter_label),
        key="chapter_selector_filter_selectbox",
    )
    selected_filter_value = status_filter_options[selected_filter_label]
    st.session_state.chapter_selector_filter = selected_filter_value
    search_query = st.text_input(
        "Search Chapters",
        value=search_query,
        key="chapter_selector_search_input",
        placeholder="Search by title or warning",
    )
    st.session_state.chapter_selector_search = search_query
    status_summary_line = _build_segment_status_summary_line(
        segments=segments,
        segment_status_by_id=segment_status_by_id,
    )
    if status_summary_line:
        st.caption(status_summary_line)
    paragraphs = list(getattr(prepared_run_context, "paragraphs", []) or [])
    updated_selection: list[str] = []
    visible_segments = [
        segment
        for segment in segments
        if _segment_matches_review_filters(
            segment=segment,
            segment_status_by_id=segment_status_by_id,
            status_filter=selected_filter_value,
            search_query=search_query,
        )
    ]
    st.caption(f"Visible segments: {len(visible_segments)}/{len(segments)}")
    visible_structure_summary = _build_visible_structure_summary(visible_segments=visible_segments)
    if visible_structure_summary:
        st.caption(visible_structure_summary)
    visible_segment_ids = {
        str(getattr(segment, "segment_id", "") or "").strip()
        for segment in visible_segments
        if str(getattr(segment, "segment_id", "") or "").strip()
    }
    visible_selectable_segment_ids = _build_bulk_selectable_segment_ids(
        visible_segments=visible_segments,
        segment_status_by_id=segment_status_by_id,
    )
    visible_selectable_segment_ids = _expand_segment_ids_for_selection(
        segment_ids=visible_selectable_segment_ids,
        parent_to_children_map=parent_to_children_map,
        segment_status_by_id=segment_status_by_id,
        include_locked=False,
    )
    all_selectable_segment_ids = _build_bulk_selectable_segment_ids(
        visible_segments=segments,
        segment_status_by_id=segment_status_by_id,
    )
    all_selectable_segment_ids = _expand_segment_ids_for_selection(
        segment_ids=all_selectable_segment_ids,
        parent_to_children_map=parent_to_children_map,
        segment_status_by_id=segment_status_by_id,
        include_locked=False,
    )
    managed_visible_segment_ids = set(
        _expand_segment_ids_for_selection(
            segment_ids=sorted(visible_segment_ids),
            parent_to_children_map=parent_to_children_map,
            segment_status_by_id=segment_status_by_id,
            include_locked=False,
        )
    )
    locked_visible_count = sum(
        1
        for segment in visible_segments
        if _is_segment_selection_locked(
            segment_status_by_id.get(str(getattr(segment, "segment_id", "") or "").strip(), "pending")
        )
    )
    bulk_updated_selection: list[str] | None = None
    if locked_visible_count > 0:
        st.caption(f"Locked while queued/processing: {locked_visible_count}")
    bulk_select_col, bulk_clear_col, bulk_all_col = st.columns(3)
    if bulk_select_col.button(
        "Select Visible",
        use_container_width=True,
        disabled=not bool(visible_selectable_segment_ids),
        key="select_visible_segments_button",
    ):
        bulk_updated_selection = list(dict.fromkeys([*selected_segment_ids, *visible_selectable_segment_ids]))
    if bulk_clear_col.button(
        "Clear Visible",
        use_container_width=True,
        disabled=not bool(visible_segment_ids),
        key="clear_visible_segments_button",
    ):
        bulk_updated_selection = [segment_id for segment_id in selected_segment_ids if segment_id not in managed_visible_segment_ids]
    if bulk_all_col.button(
        "Select Entire Book",
        use_container_width=True,
        disabled=not bool(all_selectable_segment_ids),
        key="select_entire_book_segments_button",
    ):
        bulk_updated_selection = list(all_selectable_segment_ids)
    current_selection_ids = list(bulk_updated_selection if bulk_updated_selection is not None else selected_segment_ids)
    current_selection_set = set(current_selection_ids)
    updated_selection = [segment_id for segment_id in current_selection_ids if segment_id not in managed_visible_segment_ids]
    for segment in visible_segments:
        segment_to_job = dict(getattr(prepared_run_context, "segment_to_job", {}) or {})
        segment_job_count = len(segment_to_job.get(segment.segment_id, ()) or ())
        descendant_job_count = _count_segment_descendant_jobs(
            segment_id=str(getattr(segment, "segment_id", "") or ""),
            parent_to_children_map=parent_to_children_map,
            segment_to_job=segment_to_job,
        )
        segment_status = segment_status_by_id.get(segment.segment_id, "pending")
        segment_progress = segment_progress_by_id.get(segment.segment_id, 0.0)
        active_segment_suffix = " | active" if active_segment_id == segment.segment_id else ""
        relation_fragment = _build_segment_relation_fragment(
            segment=segment,
            segment_lookup=segment_lookup,
            parent_to_children_map=parent_to_children_map,
        )
        title_prefix = _build_segment_title_prefix(getattr(segment, "level", 1))
        if segment_job_count <= 0 and descendant_job_count > 0:
            jobs_fragment = f"approx. 0 direct jobs | {descendant_job_count} descendant jobs"
        else:
            jobs_fragment = f"approx. {segment_job_count} jobs"
        label = (
            f"{title_prefix}{segment.title} | {segment.word_count} words | {segment.confidence} | "
            f"{segment.structural_role}{relation_fragment} | {jobs_fragment} | "
            f"{_build_segment_runtime_badge(segment_status, segment_progress)}{active_segment_suffix}"
        )
        checkbox_key = f"segment_checkbox_{segment.segment_id}"
        checkbox_value = segment.segment_id in current_selection_set
        if st.checkbox(
            label,
            value=checkbox_value,
            key=checkbox_key,
            disabled=_is_segment_selection_locked(segment_status),
        ):
            updated_selection.extend(
                _expand_segment_ids_for_selection(
                    segment_ids=[segment.segment_id],
                    parent_to_children_map=parent_to_children_map,
                    segment_status_by_id=segment_status_by_id,
                    include_locked=False,
                )
            )
        status_hint = _build_segment_status_hint(segment_status)
        if status_hint:
            st.caption(status_hint)
        if segment.confidence == "low":
            warning_suffix = "; ".join(segment.warnings) if segment.warnings else "Review boundary preview and evidence before processing."
            st.warning(f"Low-confidence segment: {segment.title}. {warning_suffix}")
        with st.expander(f"Boundary preview: {segment.title}", expanded=segment.confidence == "low"):
            st.caption(
                "Starts: "
                + _resolve_segment_preview(paragraphs, _coerce_segment_index(getattr(segment, "start_paragraph_index", -1)))
            )
            st.caption(
                "Ends: "
                + _resolve_segment_preview(paragraphs, _coerce_segment_index(getattr(segment, "end_paragraph_index", -1)))
            )
            st.caption(f"Boundary fingerprint: {str(getattr(segment, 'boundary_fingerprint', '') or 'n/a')}")
            segment_warnings = [str(item).strip() for item in getattr(segment, "warnings", ()) if str(item).strip()]
            if segment_warnings:
                st.write("Warnings: " + "; ".join(segment_warnings))
            evidence_items = list(getattr(segment, "boundary_evidence", ()) or [])
            if evidence_items:
                st.write("Boundary evidence:")
                for evidence in evidence_items:
                    st.caption(_format_segment_evidence_line(evidence))
            else:
                st.caption("Boundary evidence: n/a")
    if not visible_segments:
        st.info("No segments match the current filter/search.")
    updated_selection = list(dict.fromkeys(updated_selection))
    if updated_selection != selected_segment_ids:
        set_selected_segment_ids(updated_selection)
        selected_segment_ids = updated_selection

    effective_selected_state = _build_effective_selected_processing_state(
        prepared_run_context=prepared_run_context,
        selected_segment_ids=selected_segment_ids,
        segment_status_by_id=segment_status_by_id,
    )
    effective_selected_segment_ids = effective_selected_state["effective_selected_segment_ids"]
    selected_segments = effective_selected_state["effective_selected_segments"]
    selected_word_count = effective_selected_state["selected_word_count"]
    selected_job_count = effective_selected_state["selected_job_count"]
    can_process_selected = structure_confirmed and bool(effective_selected_segment_ids) and selected_job_count > 0
    total_all_words = sum(int(getattr(seg, "word_count", 0) or 0) for seg in segments)
    total_all_job_count = sum(
        len((getattr(prepared_run_context, "segment_to_job", {}) or {}).get(seg.segment_id, ()))
        for seg in segments
    )
    st.info(
        f"Selected: {len(selected_segments)}/{len(segments)} segments | {selected_word_count}/{total_all_words} words | approx. {selected_job_count}/{total_all_job_count} jobs"
    )
    selected_status_summary_line = _build_selected_segment_status_summary_line(
        selected_segments=selected_segments,
        segment_status_by_id=segment_status_by_id,
    )
    if selected_status_summary_line:
        st.caption(selected_status_summary_line)
    selected_structure_summary = _build_selected_segment_structure_summary(selected_segments=selected_segments)
    if selected_structure_summary:
        st.caption(selected_structure_summary)
    selected_descendant_coverage = _count_selected_descendant_coverage(
        selected_segment_ids=effective_selected_segment_ids,
        segment_lookup=segment_lookup,
    )
    if selected_descendant_coverage > 0:
        st.caption(
            f"Selected coverage includes {selected_descendant_coverage} descendant segments under selected parent sections."
        )
    excluded_locked_segment_ids = effective_selected_state["excluded_locked_segment_ids"]
    if excluded_locked_segment_ids:
        st.caption(
            f"Selected launch payload excludes {len(excluded_locked_segment_ids)} locked segment(s) that are currently queued or processing."
        )
    process_selected_unavailable_note = _build_process_selected_unavailable_note(
        structure_confirmed=structure_confirmed,
        selected_segment_ids=effective_selected_segment_ids,
        selected_job_count=selected_job_count,
    )
    if can_process_selected:
        st.caption("Ready: confirmed structure | selection resolves to processable jobs.")
    elif process_selected_unavailable_note:
        st.caption(process_selected_unavailable_note)
    failed_segment_count = sum(
        1
        for seg in segments
        if _normalize_segment_status(
            segment_status_by_id.get(str(getattr(seg, "segment_id", "") or ""), "pending")
        )
        == "failed"
    )
    if failed_segment_count > 0:
        st.caption(
            f"{failed_segment_count} segment(s) failed in this session. "
            "Segment retry is not available in Phase 2 — "
            "reselect failed segments and rerun, or use Process Entire Book as a fallback."
        )
    can_build_final_book = _can_build_final_translated_book(
        segments=segments,
        segment_status_by_id=segment_status_by_id,
    )

    confirm_col, selected_col, full_book_col = st.columns(3)
    current_settings_hash = str(review_state["settings_hash"])
    current_fingerprint = str(review_state["fingerprint"])
    confirm_label = "Re-confirm Structure" if structure_confirmed else "Confirm Structure"
    if confirm_col.button(confirm_label, use_container_width=True, key="confirm_structure_button"):
        set_structure_confirmation_state(
            structure_confirmed=True,
            confirmed_structure_fingerprint=current_fingerprint,
            confirmed_at_settings_hash=current_settings_hash,
            segments_loaded_for_source_token=uploaded_file_token,
        )
        log_event_fn(
            logging.INFO,
            "structure_confirmed",
            "Пользователь подтвердил обнаруженную структуру документа.",
            file_token=uploaded_file_token,
            structure_fingerprint=current_fingerprint,
            selected_segment_count=len(selected_segment_ids),
        )
        st.rerun()
    if selected_col.button(
        "Process Selected",
        use_container_width=True,
        disabled=not can_process_selected,
        help=(
            "Processes only the selected chapters and produces a partial output artifact."
            if can_process_selected
            else process_selected_unavailable_note
        ),
        key="process_selected_button",
    ):
        return "start_selected"
    if full_book_col.button("Process Entire Book", type="primary", use_container_width=True, key="process_entire_book_button"):
        return "start_final_book" if can_build_final_book else "start_full_book"
    if structure_confirmed:
        st.success("Structure confirmed for the current prepared document.")
        st.caption(
            _build_structure_confirmation_summary(
                structure_confirmed=structure_confirmed,
                selected_segment_ids=selected_segment_ids,
                segment_lookup=segment_lookup,
                review_state=review_state,
            )
        )
        if can_process_selected:
            st.caption("Process Selected now runs only the chosen chapters and produces a partial output artifact.")
        if can_build_final_book:
            st.caption("Process Entire Book is ready to produce the final translated book for the current session.")
    else:
        st.caption(
            _build_structure_confirmation_summary(
                structure_confirmed=structure_confirmed,
                selected_segment_ids=selected_segment_ids,
                segment_lookup=segment_lookup,
                review_state=review_state,
            )
        )
        if selected_segment_ids:
            st.caption("Current selection is ready for review, but chapter-based processing stays disabled until confirmation.")
    return None