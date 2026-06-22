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
    summary_lines = ["Structure confirmation invalidated."]
    if fingerprint_changed:
        summary_lines.append("Detected chapter structure changed after re-analysis.")
    if settings_changed:
        summary_lines.append("Detection-affecting settings changed since the last confirmation.")
    summary_lines.append("Review the chapter list and confirm structure again before processing selected chapters.")
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


def _pluralize(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return singular
    return plural or f"{singular}s"


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


def _build_segment_confidence_hint(confidence: object) -> str:
    normalized = str(confidence or "high").strip().lower() or "high"
    if normalized == "low":
        return "uncertain boundary"
    if normalized == "medium":
        return "review suggested"
    return "clear boundary"


def _build_structure_overview_message(*, segment_count: int) -> str:
    return (
        f"Detected {segment_count} reviewable {_pluralize(segment_count, 'section')} for partial translation. "
        "Review the list below to decide what should be translated separately."
    )


def _build_structure_confidence_summary(*, diagnostics: object) -> str:
    high_confidence_count = int(getattr(diagnostics, "high_confidence_count", 0) or 0)
    medium_confidence_count = int(getattr(diagnostics, "medium_confidence_count", 0) or 0)
    low_confidence_count = int(getattr(diagnostics, "low_confidence_count", 0) or 0)
    return (
        "Confidence overview: "
        f"{high_confidence_count} clear | {medium_confidence_count} review | {low_confidence_count} uncertain"
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
        return "Retry Failed is ready to rerun only the failed jobs recorded in the current session for those failed segments."
    if retry_job_source == "persisted_jobs":
        return "Retry Failed is ready to rerun only the failed jobs from persisted retry state for this prepared document."
    return "Retry Failed is ready to rerun only those failed segments."


def _build_retry_failed_help_text(*, retry_job_source: str) -> str:
    if retry_job_source == "current_session_jobs":
        return "Reruns only the failed jobs recorded in the current session for the failed segments."
    if retry_job_source == "persisted_jobs":
        return "Reruns only the failed jobs recorded in persisted retry state for this prepared document."
    if retry_job_source == "blocked_incomplete_mapping":
        return (
            "Prepared jobs no longer match the current chapter boundaries. "
            "Re-prepare the document before rerunning failed segments."
        )
    return "Reruns only the segments marked failed for this prepared document."


def _build_retry_failed_segment_summary(*, failed_segment_count: int, retry_job_source: str) -> str:
    if retry_job_source == "persisted_jobs":
        return f"{failed_segment_count} {_pluralize(failed_segment_count, 'section')} have persisted failed work for this prepared document."
    return f"{failed_segment_count} {_pluralize(failed_segment_count, 'section')} failed in this session."


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
    return "Section status: " + " | ".join(fragments)


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
    return "Selected section status: " + " | ".join(fragments)


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
            return f" | under {parent_title}"
        return " | nested section"
    descendant_count = len(_collect_descendant_segment_ids(segment_id=segment_id, parent_to_children_map=parent_to_children_map))
    if descendant_count > 0:
        return f" | includes {descendant_count} nested {_pluralize(descendant_count, 'section')}"
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
        f"Structure confirmed | selected main {selected_top_level_count} {_pluralize(selected_top_level_count, 'section')}"
        f" | selected nested {selected_nested_count} {_pluralize(selected_nested_count, 'section')}"
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
    return (
        f"Selection hierarchy: {top_level_count} main {_pluralize(top_level_count, 'section')}"
        f" | {nested_count} nested {_pluralize(nested_count, 'section')}"
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
            "Current analysis differs from the last exported structure manifest.\n"
            f"Manifest path: {manifest_path}\n"
            f"Exported fingerprint: {exported_fingerprint}\n"
            f"Current fingerprint: {current_fingerprint}",
        )
    match_suffix = " | fingerprint matches current analysis" if exported_fingerprint and exported_fingerprint == current_fingerprint else ""
    fingerprint_suffix = f" | fingerprint {exported_fingerprint}" if exported_fingerprint else ""
    return ("caption", f"Last exported manifest: {manifest_path}{fingerprint_suffix}{match_suffix}")


def _import_structure_manifest_notice(*, uploaded_file_token: str, uploaded_manifest_file: object) -> tuple[str, str] | None:
    if uploaded_manifest_file is None:
        return None

    filename = str(getattr(uploaded_manifest_file, "name", "structure-manifest.json") or "structure-manifest.json").strip()
    getvalue = getattr(uploaded_manifest_file, "getvalue", None)
    if not callable(getvalue):
        return ("warning", f"Unable to read imported structure manifest: {filename}")
    try:
        raw_payload = getvalue()
        if isinstance(raw_payload, bytes):
            payload_bytes = raw_payload
        elif isinstance(raw_payload, bytearray):
            payload_bytes = bytes(raw_payload)
        else:
            return ("warning", f"Unable to read imported structure manifest bytes: {filename}")
        manifest_payload = json.loads(payload_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return ("warning", f"Unable to parse imported structure manifest {filename}: {exc}")
    if not isinstance(manifest_payload, dict):
        return ("warning", f"Imported structure manifest must be a JSON object: {filename}")

    structure_fingerprint = str(manifest_payload.get("structure_fingerprint", "") or "").strip()
    if not structure_fingerprint:
        return ("warning", f"Imported structure manifest does not contain structure_fingerprint: {filename}")

    set_structure_manifest_notice(
        file_token=uploaded_file_token,
        details={
            "file_token": uploaded_file_token,
            "manifest_path": f"Imported manifest: {filename}",
            "structure_fingerprint": structure_fingerprint,
        },
    )
    return ("caption", f"Imported structure manifest ready for comparison: {filename}")


def _build_process_selected_unavailable_note(
    *,
    structure_confirmed: bool,
    selected_segment_ids: list[str],
    selected_job_count: int,
    selection_blocked_reason: str = "",
) -> str:
    if not structure_confirmed and not selected_segment_ids:
        return "Process Selected unavailable: confirm the current outline and keep at least one selectable segment selected."
    if not structure_confirmed:
        return "Process Selected unavailable: confirm the current outline before running the current chapter selection."
    if not selected_segment_ids:
        return "Process Selected unavailable: keep at least one selectable segment selected."
    if selection_blocked_reason == "segment_job_mapping_incomplete":
        return (
            "Process Selected unavailable: the current section boundaries no longer match the prepared document. "
            "Re-prepare the document before partial translation."
        )
    if selected_job_count <= 0:
        return "Process Selected unavailable: the current selection does not map to any translatable content."
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
    return (
        f"Hierarchy in current view: {parent_visible} main {_pluralize(parent_visible, 'section')}"
        f" | {child_visible} nested {_pluralize(child_visible, 'section')}"
    )


def _build_segment_status_hint(segment_status: str) -> str:
    normalized_status = _normalize_segment_status(segment_status)
    if normalized_status == "completed":
        return "Completed in this session. You can select this section again if you need a revised translation."
    if normalized_status == "failed":
        return "Failed in this session. Use Retry Failed or select this section again for another translation pass."
    if normalized_status == "skipped":
        return "Skipped in the current session workflow. It is usually left out of the final book by design."
    return ""


def _render_terminology_review(*, prepared_run_context: object) -> None:
    document_context_profile = getattr(prepared_run_context, "document_context_profile", None)
    glossary_terms = list(getattr(document_context_profile, "glossary_terms", ()) or ())
    if not glossary_terms:
        return

    translation_domain = str(getattr(prepared_run_context, "translation_domain", "general") or "general").strip() or "general"
    with st.expander(f"Terminology Review ({len(glossary_terms)})", expanded=False):
        st.caption(
            "Session-scoped glossary candidates extracted from the current analysis. "
            "These terms are already injected into translate prompts for this run."
        )
        st.caption(f"Domain: {translation_domain}")
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

    st.subheader("Review Sections Before Partial Translation")
    st.info(_build_structure_overview_message(segment_count=len(segments)))
    diagnostics = getattr(prepared_run_context, "segment_diagnostics", None)
    if diagnostics is not None:
        st.caption(_build_structure_confidence_summary(diagnostics=diagnostics))
        diagnostic_warnings = humanize_segment_warnings(getattr(diagnostics, "warnings", ()) or ())
        if diagnostic_warnings:
            st.warning(
                "Some section boundaries need manual review before partial translation: "
                + "; ".join(diagnostic_warnings)
            )
    _render_terminology_review(prepared_run_context=prepared_run_context)

    manifest_path = str(getattr(prepared_run_context, "exported_structure_manifest_path", "") or "")
    with st.expander("Advanced structure tools", expanded=False):
        st.caption("Technical details for export, support, and structure diffing. Not required for normal translation review.")
        st.caption(f"Structure fingerprint: {review_state['fingerprint'] or 'n/a'}")
        st.caption(f"Detector version: {str(getattr(prepared_run_context, 'detector_version', '') or 'n/a')}")
        if manifest_path:
            st.caption(f"Manifest path: {manifest_path}")
        imported_manifest_file = st.file_uploader(
            "Compare exported structure JSON",
            type=["json"],
            key="compare_structure_manifest_file_uploader",
            help="Import a previously exported .segments.json manifest to compare it with the current analysis.",
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
        "All sections": "all",
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
        "All sections",
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
        "Search Sections",
        value=search_query,
        key="chapter_selector_search_input",
        placeholder="Search by section title or warning",
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
    st.caption(f"Visible sections: {len(visible_segments)}/{len(segments)}")
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
        st.caption(
            f"Currently unavailable in this view: {locked_visible_count} {_pluralize(locked_visible_count, 'section')} already queued or processing."
        )
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
        segment_status = segment_status_by_id.get(segment.segment_id, "pending")
        segment_progress = segment_progress_by_id.get(segment.segment_id, 0.0)
        active_segment_suffix = " | active" if active_segment_id == segment.segment_id else ""
        relation_fragment = _build_segment_relation_fragment(
            segment=segment,
            segment_lookup=segment_lookup,
            parent_to_children_map=parent_to_children_map,
        )
        display_title = _resolve_segment_display_title(segment)
        role_label = _humanize_segment_role(getattr(segment, "structural_role", "section"))
        confidence_hint = _build_segment_confidence_hint(getattr(segment, "confidence", "high"))
        label = (
            f"{display_title} | {segment.word_count} words | {role_label}{relation_fragment} | {confidence_hint} | "
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
            segment_warning_messages = humanize_segment_warnings(getattr(segment, "warnings", ()) or ())
            warning_suffix = "; ".join(segment_warning_messages) if segment_warning_messages else "Review the included text preview before translating this section separately."
            st.warning(f"Review this section before partial translation: {display_title}. {warning_suffix}")
        with st.expander(f"Included text preview: {display_title}", expanded=segment.confidence == "low"):
            st.caption(
                "Starts with: "
                + _resolve_segment_preview(paragraphs, _coerce_segment_index(getattr(segment, "start_paragraph_index", -1)))
            )
            st.caption(
                "Ends with: "
                + _resolve_segment_preview(paragraphs, _coerce_segment_index(getattr(segment, "end_paragraph_index", -1)))
            )
            segment_warnings = list(humanize_segment_warnings(getattr(segment, "warnings", ()) or ()))
            if segment_warnings:
                st.caption("Review notes: " + "; ".join(segment_warnings))
            if str(getattr(segment, "confidence", "high") or "high").strip().lower() != "high":
                st.caption(f"Boundary confidence: {_build_segment_confidence_hint(getattr(segment, 'confidence', 'high'))}.")
    if not visible_segments:
        st.info("No sections match the current filter/search.")
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
    can_process_selected = structure_confirmed and bool(effective_selected_segment_ids) and selected_job_count > 0
    total_all_words = sum(int(getattr(seg, "word_count", 0) or 0) for seg in segments)
    st.info(f"Will translate: {len(selected_segments)}/{len(segments)} sections | {selected_word_count}/{total_all_words} words")
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
            f"Selection also includes {selected_descendant_coverage} nested {_pluralize(selected_descendant_coverage, 'section')} under chosen parent sections."
        )
    excluded_locked_segment_ids = effective_selected_state["excluded_locked_segment_ids"]
    if excluded_locked_segment_ids:
        blocked_count = len(excluded_locked_segment_ids)
        verb = "is" if blocked_count == 1 else "are"
        st.caption(
            f"This launch will skip {blocked_count} {_pluralize(blocked_count, 'section')} that {verb} already queued or processing."
        )
    process_selected_unavailable_note = _build_process_selected_unavailable_note(
        structure_confirmed=structure_confirmed,
        selected_segment_ids=effective_selected_segment_ids,
        selected_job_count=selected_job_count,
        selection_blocked_reason=str(effective_selected_state["selection_blocked_reason"]),
    )
    if can_process_selected:
        st.caption("Ready: confirmed structure | selection maps to translatable content.")
    elif process_selected_unavailable_note:
        st.caption(process_selected_unavailable_note)
    if can_process_selected:
        st.checkbox(
            "Include Front Matter",
            value=include_front_matter,
            key="selected_context_include_front_matter_checkbox",
            help="When enabled, Selected + Context prepends front matter segments as source-backed context.",
        )
        st.checkbox(
            "Include TOC",
            value=include_toc,
            key="selected_context_include_toc_checkbox",
            help="When enabled, Selected + Context prepends table-of-contents segments as source-backed context.",
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
    can_retry_failed = structure_confirmed and bool(retry_failed_segment_ids) and retry_failed_job_count > 0
    retry_failed_unavailable_note = ""
    if failed_segment_count > 0 and not can_retry_failed:
        if not structure_confirmed:
            retry_failed_unavailable_note = "Retry Failed unavailable: confirm the current outline before rerunning failed segments."
        elif retry_job_source == "blocked_incomplete_mapping":
            retry_failed_unavailable_note = (
                "Retry Failed unavailable: the current section boundaries no longer match the prepared document. "
                "Re-prepare the document before rerunning failed sections."
            )
        else:
            retry_failed_unavailable_note = "Retry Failed unavailable: failed sections do not currently map to translatable content."
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

    confirm_col, selected_col, full_book_col = st.columns(3)
    current_settings_hash = str(review_state["settings_hash"])
    current_fingerprint = str(review_state["fingerprint"])
    confirm_label = "Re-confirm Structure" if structure_confirmed else "Confirm Structure"
    if confirm_col.button(confirm_label, use_container_width=True, key="confirm_structure_button"):
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
            "Processes only the selected sections and produces a partial output artifact."
            if can_process_selected
            else process_selected_unavailable_note
        ),
        key="process_selected_button",
    ):
        return "start_selected"
    if selected_col.button(
        "Selected + Context",
        use_container_width=True,
        disabled=not can_process_selected,
        help=(
            "Processes the selected sections and prepends leading structural context such as front matter or TOC as source-backed content."
            if can_process_selected
            else process_selected_unavailable_note
        ),
        key="process_selected_with_context_button",
    ):
        return "start_selected_with_context"
    if failed_segment_count > 0 and selected_col.button(
        "Retry Failed",
        use_container_width=True,
        disabled=not can_retry_failed,
        help=(
            _build_retry_failed_help_text(retry_job_source=retry_job_source)
            if can_retry_failed
            else retry_failed_unavailable_note
        ),
        key="retry_failed_segments_button",
    ):
        return "start_retry_failed"
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
            st.caption("Process Selected now runs only the chosen sections and produces a partial output artifact.")
            st.caption("Selected + Context prepends leading source-backed structural context such as front matter or TOC before the first selected chapter.")
        if can_retry_failed:
            st.caption(_build_retry_failed_ready_message(retry_job_source=retry_job_source))
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