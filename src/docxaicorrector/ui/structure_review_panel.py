from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Sequence
from typing import Any, Mapping, Protocol, TypedDict, cast

import streamlit as st

from docxaicorrector.chapter_workflow.service import (
    build_effective_selected_processing_state as chapter_workflow_build_effective_selected_processing_state,
    build_retry_failed_processing_state as chapter_workflow_build_retry_failed_processing_state,
    build_selected_processing_payload as chapter_workflow_build_selected_processing_payload,
)
from docxaicorrector.core.logger import log_event
from docxaicorrector.document.segments import OVERSIZED_HEADING_SPLIT_EVIDENCE_SOURCE, humanize_segment_warnings
from docxaicorrector.runtime.state import (
    get_active_segment_id,
    get_confirmed_at_settings_hash,
    get_confirmed_structure_fingerprint,
    get_confirmed_structure_segment_ids,
    get_run_log,
    get_segment_progress_by_id,
    get_segment_status_by_id,
    get_segments_loaded_for_source_token,
    get_selected_segment_ids,
    get_structure_confirmed,
    get_structure_manifest_notice_details,
    get_structure_manifest_notice_token,
    set_selected_segment_ids,
    set_structure_manifest_notice,
    set_structure_confirmation_state,
)
from docxaicorrector.pipeline.contracts import SegmentSelection
from docxaicorrector.ui.i18n import t


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
    segment_ids_changed: bool
    settings_changed: bool


class SelectedProcessingPayload(TypedDict):
    selected_segment_ids: list[str]
    jobs: list[dict[str, object]]
    source_paragraphs: list[object]
    image_assets: list[object]
    include_front_matter: bool
    include_toc: bool


class EffectiveSelectedProcessingState(TypedDict):
    payload: SelectedProcessingPayload
    effective_selected_segment_ids: list[str]
    effective_selected_segments: list[SegmentLike]
    selected_word_count: int
    selected_job_count: int
    excluded_locked_segment_ids: list[str]
    uses_job_index_filter: bool
    retry_job_source: str
    selection_blocked_reason: str


_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_IMAGE_[^\]]+\]\]")
_MARKDOWN_NOISE_PATTERN = re.compile(r"[*_`]+")


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


def _has_chunk_size_sensitive_structure(prepared_run_context: object) -> bool:
    for segment in _get_prepared_segments(prepared_run_context):
        for evidence in getattr(segment, "boundary_evidence", ()) or ():
            if str(getattr(evidence, "source", "") or "") == OVERSIZED_HEADING_SPLIT_EVIDENCE_SOURCE:
                return True
    return False


def _build_structure_settings_hash(
    *,
    uploaded_file_token: str,
    prepared_run_context,
    chunk_size: int,
    app_config: Mapping[str, object] | None = None,
) -> str:
    resolved_app_config = dict(app_config or {})
    chunk_size_sensitive_structure = _has_chunk_size_sensitive_structure(prepared_run_context)
    payload = {
        "uploaded_file_token": uploaded_file_token,
        "structure_fingerprint": str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
        "detector_version": str(getattr(prepared_run_context, "detector_version", "") or ""),
        "chunk_size_sensitive_structure": chunk_size_sensitive_structure,
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
        "structure_validation_enabled": bool(resolved_app_config.get("structure_validation_enabled", True)),
    }
    if chunk_size_sensitive_structure:
        payload["chunk_size"] = int(chunk_size or 0)
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
    confirmed_segment_ids = get_confirmed_structure_segment_ids()
    confirmed_settings_hash = get_confirmed_at_settings_hash()
    confirmation_invalidated = False
    legacy_confirmed_snapshot_missing = (
        structure_confirmed
        and not confirmed_segment_ids
        and bool(str(confirmed_fingerprint or "").strip())
    )
    fingerprint_changed = structure_confirmed and confirmed_fingerprint != current_fingerprint
    segment_ids_changed = structure_confirmed and not legacy_confirmed_snapshot_missing and confirmed_segment_ids != segment_ids
    settings_changed = structure_confirmed and confirmed_settings_hash != current_settings_hash
    if structure_confirmed and (fingerprint_changed or segment_ids_changed or settings_changed):
        set_structure_confirmation_state(
            structure_confirmed=False,
            confirmed_structure_fingerprint="",
            confirmed_segment_ids=[],
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
        "segment_ids_changed": segment_ids_changed,
        "settings_changed": settings_changed,
    }


def _build_structure_invalidation_summary(review_state: StructureReviewState) -> str:
    if not bool(review_state.get("confirmation_invalidated", False)):
        return ""
    fingerprint_changed = bool(review_state.get("fingerprint_changed", False))
    settings_changed = bool(review_state.get("settings_changed", False))
    summary_lines = [t("structure.invalidation_title")]
    if fingerprint_changed:
        summary_lines.append(t("structure.invalidation_fingerprint_changed"))
    if settings_changed:
        summary_lines.append(t("structure.invalidation_settings_changed"))
    summary_lines.append(t("structure.invalidation_review_again"))
    return "\n".join(summary_lines)


def _coerce_segment_preview_text(paragraph: object) -> str:
    if isinstance(paragraph, str):
        return _clean_user_visible_text(paragraph, fallback="")
    for attribute_name in ("rendered_text", "text"):
        value = str(getattr(paragraph, attribute_name, "") or "").strip()
        if value:
            return _clean_user_visible_text(value, fallback="")
    return _clean_user_visible_text(paragraph, fallback="")


def _clean_user_visible_text(text: object, *, limit: int | None = None, fallback: str = "n/a") -> str:
    normalized = str(text or "")
    normalized = _IMAGE_PLACEHOLDER_PATTERN.sub(" ", normalized)
    normalized = normalized.replace("\\-", "-").replace("\\*", "*")
    normalized = _MARKDOWN_NOISE_PATTERN.sub("", normalized)
    normalized = " ".join(normalized.split()).strip(" -|:")
    if not normalized:
        normalized = fallback
    if limit is not None and limit > 0 and len(normalized) > limit:
        return normalized[: max(0, limit - 3)].rstrip() + "..."
    return normalized


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


def _humanize_segment_role(role: object) -> str:
    normalized = " ".join(str(role or "section").replace("_", " ").split()).strip().lower()
    return normalized or "section"


def _build_segment_fallback_title(segment: SegmentLike) -> str:
    role_label = _humanize_segment_role(getattr(segment, "structural_role", "section")).title()
    try:
        ordinal = int(getattr(segment, "ordinal", 0) or 0)
    except (TypeError, ValueError):
        ordinal = 0
    if ordinal > 0:
        return f"{role_label} {ordinal}"
    return role_label


def _resolve_segment_display_title(segment: SegmentLike, *, limit: int = 96) -> str:
    normalized_title = _clean_user_visible_text(getattr(segment, "title", ""), limit=limit, fallback="")
    if normalized_title:
        return normalized_title
    return _build_segment_fallback_title(segment)


def _localized_status_label(status: object) -> str:
    normalized = _normalize_segment_status(status)
    key = f"structure.status_{normalized}"
    label = t(key)
    return label if label != key else normalized


def _build_segment_confidence_hint(confidence: object) -> str:
    normalized = str(confidence or "high").strip().lower() or "high"
    if normalized == "low":
        return t("structure.confidence_hint_low")
    if normalized == "medium":
        return t("structure.confidence_hint_medium")
    return t("structure.confidence_hint_high")


def _build_structure_overview_message(*, segment_count: int) -> str:
    return t("structure.overview_message", count=segment_count)


def _build_structure_confidence_summary(*, diagnostics: object) -> str:
    high_confidence_count = int(getattr(diagnostics, "high_confidence_count", 0) or 0)
    medium_confidence_count = int(getattr(diagnostics, "medium_confidence_count", 0) or 0)
    low_confidence_count = int(getattr(diagnostics, "low_confidence_count", 0) or 0)
    return t(
        "structure.confidence_summary",
        high=high_confidence_count,
        medium=medium_confidence_count,
        low=low_confidence_count,
    )


def _build_selected_processing_payload(
    *,
    prepared_run_context,
    selected_segment_ids: list[str] | None,
    segment_selection: SegmentSelection | None = None,
    selected_job_indexes: list[int] | None = None,
    segment_status_by_id: dict[str, str] | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
) -> SelectedProcessingPayload:
    return cast(
        SelectedProcessingPayload,
        chapter_workflow_build_selected_processing_payload(
            prepared_run_context=prepared_run_context,
            selected_segment_ids=selected_segment_ids,
            segment_selection=segment_selection,
            selected_job_indexes=selected_job_indexes,
            segment_status_by_id=segment_status_by_id,
            include_front_matter=include_front_matter,
            include_toc=include_toc,
        ),
    )


def _build_effective_selected_processing_state(
    *,
    prepared_run_context,
    selected_segment_ids: list[str] | None,
    segment_selection: SegmentSelection | None = None,
    selected_job_indexes: list[int] | None = None,
    segment_status_by_id: dict[str, str] | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
) -> EffectiveSelectedProcessingState:
    return cast(
        EffectiveSelectedProcessingState,
        chapter_workflow_build_effective_selected_processing_state(
            prepared_run_context=prepared_run_context,
            selected_segment_ids=selected_segment_ids,
            segment_selection=segment_selection,
            selected_job_indexes=selected_job_indexes,
            segment_status_by_id=segment_status_by_id,
            include_front_matter=include_front_matter,
            include_toc=include_toc,
        ),
    )


def _build_latest_block_status_by_job_index(run_log: Sequence[object] | None = None) -> dict[int, str]:
    latest_status_by_job_index: dict[int, str] = {}
    for entry in list(run_log or get_run_log()):
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("kind", "") or "").strip().lower() != "block":
            continue
        raw_block_index = entry.get("block_index")
        if isinstance(raw_block_index, bool) or not isinstance(raw_block_index, int) or raw_block_index <= 0:
            continue
        status = str(entry.get("status", "") or "").strip().lower()
        if not status:
            continue
        latest_status_by_job_index[raw_block_index - 1] = status
    return latest_status_by_job_index


def _resolve_retry_failed_job_indexes(
    *,
    prepared_run_context,
    failed_segment_ids: list[str],
    run_log: Sequence[object] | None = None,
) -> list[int]:
    if not failed_segment_ids:
        return []
    segment_to_job = dict(getattr(prepared_run_context, "segment_to_job", {}) or {})
    candidate_job_indexes = {
        int(job_index)
        for segment_id in failed_segment_ids
        for job_index in (segment_to_job.get(segment_id, ()) or ())
        if isinstance(job_index, int) and job_index >= 0
    }
    if not candidate_job_indexes:
        return []
    latest_status_by_job_index = _build_latest_block_status_by_job_index(run_log)
    failed_job_indexes = sorted(
        job_index
        for job_index in candidate_job_indexes
        if latest_status_by_job_index.get(job_index) in {"error", "failed"}
    )
    return failed_job_indexes


def _resolve_failed_segment_ids(*, prepared_run_context, segment_status_by_id: dict[str, str] | None = None) -> list[str]:
    segments = _get_prepared_segments(prepared_run_context)
    return [
        segment.segment_id
        for segment in segments
        if str(getattr(segment, "segment_id", "") or "").strip()
        and _normalize_segment_status(
            (segment_status_by_id or {}).get(str(getattr(segment, "segment_id", "") or ""), "pending")
        )
        == "failed"
    ]


def _build_retry_failed_processing_state(
    *,
    prepared_run_context,
    segment_status_by_id: dict[str, str] | None = None,
    run_log: Sequence[object] | None = None,
) -> EffectiveSelectedProcessingState:
    return cast(
        EffectiveSelectedProcessingState,
        chapter_workflow_build_retry_failed_processing_state(
            prepared_run_context=prepared_run_context,
            segment_status_by_id=segment_status_by_id,
            run_log=run_log,
        ),
    )


def _get_selected_context_policy() -> tuple[bool, bool]:
    include_front_matter = bool(st.session_state.get("selected_context_include_front_matter_checkbox", True))
    include_toc = bool(st.session_state.get("selected_context_include_toc_checkbox", True))
    return include_front_matter, include_toc


def _build_retry_failed_ready_message(*, retry_job_source: str) -> str:
    if retry_job_source == "current_session_jobs":
        return t("structure.retry_ready_current_session")
    if retry_job_source == "persisted_jobs":
        return t("structure.retry_ready_persisted")
    return t("structure.retry_ready_default")


def _build_retry_failed_help_text(*, retry_job_source: str) -> str:
    if retry_job_source == "current_session_jobs":
        return t("structure.retry_help_current_session")
    if retry_job_source == "persisted_jobs":
        return t("structure.retry_help_persisted")
    if retry_job_source == "blocked_incomplete_mapping":
        return t("structure.retry_help_blocked")
    return t("structure.retry_help_default")


def _build_retry_failed_segment_summary(*, failed_segment_count: int, retry_job_source: str) -> str:
    if retry_job_source == "persisted_jobs":
        return t("structure.retry_summary_persisted", count=failed_segment_count)
    return t("structure.retry_summary_default", count=failed_segment_count)


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
        return t("structure.badge_completed", percent=progress_percent)
    if normalized_status == "processing":
        return t("structure.badge_processing", percent=progress_percent)
    if normalized_status == "failed":
        return t("structure.badge_failed", percent=progress_percent)
    if normalized_status == "queued":
        return t("structure.badge_queued", percent=progress_percent)
    return _localized_status_label(normalized_status)


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
        parent_title = _resolve_segment_display_title(parent_segment, limit=64) if parent_segment is not None else ""
        if parent_title:
            return t("structure.relation_under", title=parent_title)
        return t("structure.relation_nested")
    descendant_count = len(_collect_descendant_segment_ids(segment_id=segment_id, parent_to_children_map=parent_to_children_map))
    if descendant_count > 0:
        return t("structure.relation_includes", count=descendant_count)
    return ""


def _build_segment_title_prefix(level: object) -> str:
    try:
        normalized_level = max(1, int(cast(Any, level)))
    except (TypeError, ValueError):
        normalized_level = 1
    if normalized_level <= 1:
        return ""
    return "  " * (normalized_level - 1) + "- "


def _build_structure_confirmation_summary(
    *,
    structure_confirmed: bool,
    selected_segment_ids: list[str],
    segment_lookup: dict[str, SegmentLike],
    review_state: StructureReviewState,
) -> str:
    if not structure_confirmed:
        return t("structure.confirmation_not_confirmed")
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
    return t(
        "structure.confirmation_confirmed",
        top=selected_top_level_count,
        nested=selected_nested_count,
    )


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
            t(
                "structure.manifest_diff_warning",
                manifest_path=manifest_path,
                exported=exported_fingerprint,
                current=current_fingerprint,
            ),
        )
    match_suffix = t("structure.manifest_match_suffix") if exported_fingerprint and exported_fingerprint == current_fingerprint else ""
    fingerprint_suffix = t("structure.manifest_fingerprint_suffix", value=exported_fingerprint) if exported_fingerprint else ""
    return (
        "caption",
        t(
            "structure.last_exported_manifest",
            path=manifest_path,
            fingerprint_suffix=fingerprint_suffix,
            match_suffix=match_suffix,
        ),
    )


def _import_structure_manifest_notice(*, uploaded_file_token: str, uploaded_manifest_file: object) -> tuple[str, str] | None:
    if uploaded_manifest_file is None:
        return None

    filename = str(getattr(uploaded_manifest_file, "name", "structure-manifest.json") or "structure-manifest.json").strip()
    getvalue = getattr(uploaded_manifest_file, "getvalue", None)
    if not callable(getvalue):
        return ("warning", t("structure.import_unable_read", filename=filename))
    try:
        raw_payload = getvalue()
        if isinstance(raw_payload, bytes):
            payload_bytes = raw_payload
        elif isinstance(raw_payload, bytearray):
            payload_bytes = bytes(raw_payload)
        else:
            return ("warning", t("structure.import_unable_read_bytes", filename=filename))
        manifest_payload = json.loads(payload_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return ("warning", t("structure.import_unable_parse", filename=filename, error=exc))
    if not isinstance(manifest_payload, dict):
        return ("warning", t("structure.import_not_object", filename=filename))

    structure_fingerprint = str(manifest_payload.get("structure_fingerprint", "") or "").strip()
    if not structure_fingerprint:
        return ("warning", t("structure.import_no_fingerprint", filename=filename))

    set_structure_manifest_notice(
        file_token=uploaded_file_token,
        details={
            "file_token": uploaded_file_token,
            "manifest_path": t("structure.imported_manifest_path", filename=filename),
            "structure_fingerprint": structure_fingerprint,
        },
    )
    return ("caption", t("structure.import_ready", filename=filename))


def _build_process_selected_unavailable_note(
    *,
    selected_segment_ids: list[str],
    selected_job_count: int,
    selection_blocked_reason: str = "",
) -> str:
    if not selected_segment_ids:
        return t("structure.process_unavailable_select")
    if selection_blocked_reason == "segment_job_mapping_incomplete":
        return t("structure.process_unavailable_mapping")
    if selected_job_count <= 0:
        return t("structure.process_unavailable_no_content")
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


def _build_segment_status_hint(segment_status: str) -> str:
    normalized_status = _normalize_segment_status(segment_status)
    if normalized_status == "completed":
        return t("structure.status_hint_completed")
    if normalized_status == "failed":
        return t("structure.status_hint_failed")
    if normalized_status == "skipped":
        return t("structure.status_hint_skipped")
    return ""


def _render_terminology_review(*, prepared_run_context: object) -> None:
    document_context_profile = getattr(prepared_run_context, "document_context_profile", None)
    glossary_terms = list(getattr(document_context_profile, "glossary_terms", ()) or ())
    if not glossary_terms:
        return

    translation_domain = str(getattr(prepared_run_context, "translation_domain", "general") or "general").strip() or "general"
    with st.expander(t("structure.terminology_expander", count=len(glossary_terms)), expanded=False):
        st.caption(t("structure.terminology_caption"))
        st.caption(t("structure.terminology_domain", domain=translation_domain))
        for term in glossary_terms:
            source_term = str(getattr(term, "source_term", "") or "").strip()
            target_term = str(getattr(term, "target_term", "") or "").strip()
            if not source_term or not target_term:
                continue
            st.write(f"- {source_term} -> {target_term}")


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

    st.subheader(t("structure.subheader"))
    st.info(_build_structure_overview_message(segment_count=len(segments)))
    diagnostics = getattr(prepared_run_context, "segment_diagnostics", None)
    if diagnostics is not None:
        st.caption(_build_structure_confidence_summary(diagnostics=diagnostics))
        diagnostic_warnings = humanize_segment_warnings(getattr(diagnostics, "warnings", ()) or ())
        if diagnostic_warnings:
            st.warning(t("structure.diagnostic_warning", details="; ".join(diagnostic_warnings)))
    _render_terminology_review(prepared_run_context=prepared_run_context)

    manifest_path = str(getattr(prepared_run_context, "exported_structure_manifest_path", "") or "")
    with st.expander(t("structure.advanced_tools_expander"), expanded=False):
        st.caption(t("structure.advanced_tools_caption"))
        st.caption(t("structure.fingerprint_caption", value=review_state["fingerprint"] or "n/a"))
        st.caption(t("structure.detector_version_caption", value=str(getattr(prepared_run_context, "detector_version", "") or "n/a")))
        if manifest_path:
            st.caption(t("structure.manifest_path_caption", path=manifest_path))
        imported_manifest_file = st.file_uploader(
            t("structure.compare_manifest_label"),
            type=["json"],
            key="compare_structure_manifest_file_uploader",
            help=t("structure.compare_manifest_help"),
        )
        imported_manifest_notice = _import_structure_manifest_notice(
            uploaded_file_token=uploaded_file_token,
            uploaded_manifest_file=imported_manifest_file,
        )
        if imported_manifest_notice is not None:
            notice_level, notice_message = imported_manifest_notice
            _show_notice(level=notice_level, message=notice_message)
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
        t("structure.filter_all"): "all",
        t("structure.filter_pending"): "pending",
        t("structure.filter_queued"): "queued",
        t("structure.filter_processing"): "processing",
        t("structure.filter_completed"): "completed",
        t("structure.filter_failed"): "failed",
        t("structure.filter_skipped"): "skipped",
        t("structure.filter_low_confidence"): "low_confidence",
    }
    filter_labels = list(status_filter_options.keys())
    current_filter_value = str(st.session_state.get("chapter_selector_filter", "all") or "all")
    current_filter_label = next(
        (label for label, value in status_filter_options.items() if value == current_filter_value),
        t("structure.filter_all"),
    )
    selected_filter_label = st.selectbox(
        t("structure.status_filter_label"),
        filter_labels,
        index=filter_labels.index(current_filter_label),
        key="chapter_selector_filter_selectbox",
    )
    selected_filter_value = status_filter_options[selected_filter_label]
    st.session_state.chapter_selector_filter = selected_filter_value
    search_query = st.text_input(
        t("structure.search_label"),
        value=search_query,
        key="chapter_selector_search_input",
        placeholder=t("structure.search_placeholder"),
    )
    st.session_state.chapter_selector_search = search_query
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
    st.caption(t("structure.visible_count", visible=len(visible_segments), total=len(segments)))
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
        st.caption(t("structure.currently_unavailable_view", count=locked_visible_count))
    bulk_select_col, bulk_clear_col, bulk_all_col = st.columns(3)
    if bulk_select_col.button(
        t("structure.select_visible_button"),
        use_container_width=True,
        disabled=not bool(visible_selectable_segment_ids),
        key="select_visible_segments_button",
    ):
        bulk_updated_selection = list(dict.fromkeys([*selected_segment_ids, *visible_selectable_segment_ids]))
    if bulk_clear_col.button(
        t("structure.clear_visible_button"),
        use_container_width=True,
        disabled=not bool(visible_segment_ids),
        key="clear_visible_segments_button",
    ):
        bulk_updated_selection = [segment_id for segment_id in selected_segment_ids if segment_id not in managed_visible_segment_ids]
    if bulk_all_col.button(
        t("structure.select_entire_book_button"),
        use_container_width=True,
        disabled=not bool(all_selectable_segment_ids),
        key="select_entire_book_segments_button",
    ):
        bulk_updated_selection = list(all_selectable_segment_ids)
    current_selection_ids = list(bulk_updated_selection if bulk_updated_selection is not None else selected_segment_ids)
    current_selection_set = set(current_selection_ids)
    updated_selection = [segment_id for segment_id in current_selection_ids if segment_id not in managed_visible_segment_ids]
    for segment in visible_segments:
        segment_status = segment_status_by_id.get(segment.segment_id, "pending")
        segment_progress = segment_progress_by_id.get(segment.segment_id, 0.0)
        active_segment_suffix = t("structure.label_active_suffix") if active_segment_id == segment.segment_id else ""
        relation_fragment = _build_segment_relation_fragment(
            segment=segment,
            segment_lookup=segment_lookup,
            parent_to_children_map=parent_to_children_map,
        )
        display_title = _resolve_segment_display_title(segment)
        role_label = _humanize_segment_role(getattr(segment, "structural_role", "section"))
        confidence_hint = _build_segment_confidence_hint(getattr(segment, "confidence", "high"))
        label = t(
            "structure.segment_label",
            title=display_title,
            words=segment.word_count,
            role=role_label,
            relation=relation_fragment,
            confidence=confidence_hint,
            badge=_build_segment_runtime_badge(segment_status, segment_progress),
            active=active_segment_suffix,
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
        with st.expander(t("structure.included_preview_expander", title=display_title), expanded=False):
            st.caption(
                t(
                    "structure.preview_starts_with",
                    text=_resolve_segment_preview(paragraphs, _coerce_segment_index(getattr(segment, "start_paragraph_index", -1))),
                )
            )
            st.caption(
                t(
                    "structure.preview_ends_with",
                    text=_resolve_segment_preview(paragraphs, _coerce_segment_index(getattr(segment, "end_paragraph_index", -1))),
                )
            )
            segment_warnings = list(humanize_segment_warnings(getattr(segment, "warnings", ()) or ()))
            if segment_warnings:
                st.caption(t("structure.preview_review_notes", details="; ".join(segment_warnings)))
            if str(getattr(segment, "confidence", "high") or "high").strip().lower() != "high":
                st.caption(t("structure.preview_boundary_confidence", hint=_build_segment_confidence_hint(getattr(segment, "confidence", "high"))))
    if not visible_segments:
        st.info(t("structure.no_sections_match"))
    updated_selection = list(dict.fromkeys(updated_selection))
    if updated_selection != selected_segment_ids:
        set_selected_segment_ids(updated_selection)
        selected_segment_ids = updated_selection

    include_front_matter, include_toc = _get_selected_context_policy()
    effective_selected_state = _build_effective_selected_processing_state(
        prepared_run_context=prepared_run_context,
        selected_segment_ids=selected_segment_ids,
        segment_status_by_id=segment_status_by_id,
        include_front_matter=include_front_matter,
        include_toc=include_toc,
    )
    effective_selected_segment_ids = effective_selected_state["effective_selected_segment_ids"]
    selected_segments = effective_selected_state["effective_selected_segments"]
    selected_word_count = effective_selected_state["selected_word_count"]
    selected_job_count = effective_selected_state["selected_job_count"]
    can_process_selected = bool(effective_selected_segment_ids) and selected_job_count > 0
    total_all_words = sum(int(getattr(seg, "word_count", 0) or 0) for seg in segments)
    st.info(
        t(
            "structure.will_translate",
            selected=len(selected_segments),
            total=len(segments),
            selected_words=selected_word_count,
            total_words=total_all_words,
        )
    )
    excluded_locked_segment_ids = effective_selected_state["excluded_locked_segment_ids"]
    if excluded_locked_segment_ids:
        blocked_count = len(excluded_locked_segment_ids)
        st.caption(t("structure.launch_skip", count=blocked_count))
    process_selected_unavailable_note = _build_process_selected_unavailable_note(
        selected_segment_ids=effective_selected_segment_ids,
        selected_job_count=selected_job_count,
        selection_blocked_reason=str(effective_selected_state["selection_blocked_reason"]),
    )
    if can_process_selected:
        st.caption(t("structure.ready_note"))
    elif process_selected_unavailable_note:
        st.caption(process_selected_unavailable_note)
    if can_process_selected:
        st.checkbox(
            t("structure.include_front_matter_label"),
            value=include_front_matter,
            key="selected_context_include_front_matter_checkbox",
            help=t("structure.include_front_matter_help"),
        )
        st.checkbox(
            t("structure.include_toc_label"),
            value=include_toc,
            key="selected_context_include_toc_checkbox",
            help=t("structure.include_toc_help"),
        )
    retry_failed_state = _build_retry_failed_processing_state(
        prepared_run_context=prepared_run_context,
        segment_status_by_id=segment_status_by_id,
        run_log=get_run_log(),
    )
    retry_failed_segment_ids = retry_failed_state["effective_selected_segment_ids"]
    retry_failed_job_count = retry_failed_state["selected_job_count"]
    retry_job_source = str(retry_failed_state["retry_job_source"])
    current_failed_segment_count = len(
        _resolve_failed_segment_ids(
            prepared_run_context=prepared_run_context,
            segment_status_by_id=segment_status_by_id,
        )
    )
    failed_segment_count = current_failed_segment_count or (
        len(retry_failed_segment_ids) if retry_job_source == "persisted_jobs" else 0
    )
    can_retry_failed = bool(retry_failed_segment_ids) and retry_failed_job_count > 0
    retry_failed_unavailable_note = ""
    if failed_segment_count > 0 and not can_retry_failed:
        if retry_job_source == "blocked_incomplete_mapping":
            retry_failed_unavailable_note = t("structure.retry_unavailable_mapping")
        else:
            retry_failed_unavailable_note = t("structure.retry_unavailable_no_content")
    if failed_segment_count > 0:
        if can_retry_failed:
            st.caption(
                _build_retry_failed_segment_summary(
                    failed_segment_count=failed_segment_count,
                    retry_job_source=retry_job_source,
                )
                + " "
                + _build_retry_failed_ready_message(retry_job_source=retry_job_source)
            )
        else:
            st.caption(
                _build_retry_failed_segment_summary(
                    failed_segment_count=failed_segment_count,
                    retry_job_source=retry_job_source,
                )
                + " "
                f"{retry_failed_unavailable_note}"
            )
    can_build_final_book = _can_build_final_translated_book(
        segments=segments,
        segment_status_by_id=segment_status_by_id,
    )

    action_columns = st.columns(2)
    partial_col = action_columns[0]
    full_book_col = action_columns[1]
    current_settings_hash = str(review_state["settings_hash"])
    current_fingerprint = str(review_state["fingerprint"])

    def _confirm_structure_on_start() -> None:
        # §8: starting a partial action confirms the reviewed structure implicitly,
        # setting the SAME downstream confirmation state the explicit Confirm used to set.
        set_structure_confirmation_state(
            structure_confirmed=True,
            confirmed_structure_fingerprint=current_fingerprint,
            confirmed_segment_ids=review_state["segment_ids"],
            confirmed_at_settings_hash=current_settings_hash,
            segments_loaded_for_source_token=uploaded_file_token,
        )
        log_event_fn(
            logging.INFO,
            "structure_confirmed",
            "Структура документа подтверждена автоматически при запуске обработки выбранных разделов.",
            file_token=uploaded_file_token,
            structure_fingerprint=current_fingerprint,
            selected_segment_count=len(selected_segment_ids),
        )

    if partial_col.button(
        t("structure.process_selected_button"),
        use_container_width=True,
        disabled=not can_process_selected,
        help=(
            t("structure.process_selected_help")
            if can_process_selected
            else process_selected_unavailable_note
        ),
        key="process_selected_button",
    ):
        _confirm_structure_on_start()
        return "start_selected"
    if partial_col.button(
        t("structure.selected_with_context_button"),
        use_container_width=True,
        disabled=not can_process_selected,
        help=(
            t("structure.selected_with_context_help")
            if can_process_selected
            else process_selected_unavailable_note
        ),
        key="process_selected_with_context_button",
    ):
        _confirm_structure_on_start()
        return "start_selected_with_context"
    if failed_segment_count > 0 and partial_col.button(
        t("structure.retry_failed_button"),
        use_container_width=True,
        disabled=not can_retry_failed,
        help=(
            _build_retry_failed_help_text(retry_job_source=retry_job_source)
            if can_retry_failed
            else retry_failed_unavailable_note
        ),
        key="retry_failed_segments_button",
    ):
        _confirm_structure_on_start()
        return "start_retry_failed"
    if full_book_col.button(t("structure.process_entire_book_button"), type="primary", use_container_width=True, key="process_entire_book_button"):
        return "start_final_book" if can_build_final_book else "start_full_book"
    if structure_confirmed:
        st.success(t("structure.structure_confirmed_success"))
    st.caption(
        _build_structure_confirmation_summary(
            structure_confirmed=structure_confirmed,
            selected_segment_ids=selected_segment_ids,
            segment_lookup=segment_lookup,
            review_state=review_state,
        )
    )
    return None