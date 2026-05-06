import logging
import threading
import time
import hashlib
import json
from typing import Any, cast

import streamlit as st

st.set_page_config(
    page_title="AI DOCX Editor",
    layout="wide",
    initial_sidebar_state="expanded",
)

from docxaicorrector.core.constants import APP_READY_PATH, MAX_DOCX_ARCHIVE_SIZE_BYTES
import docxaicorrector.ui.application_flow as application_flow
import docxaicorrector.ui.compare_panel as compare_panel
from docxaicorrector.ui.recommended_text_settings import (
    ManualTextSettingsOverride,
    RecommendedTextSettings,
    TEXT_SETTINGS_FIELDS,
    build_empty_manual_text_settings_override,
    derive_recommended_text_settings,
    mark_manual_overrides_from_baseline,
    mark_manual_overrides_from_recommendation,
    mark_manual_overrides_from_snapshot,
    normalize_manual_text_settings_override,
    normalize_recommendation_snapshot,
)
from docxaicorrector.core.config import load_app_config
from docxaicorrector.ui.app_runtime import (
    build_preparation_request_marker,
    drain_preparation_events as _drain_preparation_events,
    drain_processing_events as _drain_processing_events,
    preparation_worker_is_active as _preparation_worker_is_active,
    processing_worker_is_active as _processing_worker_is_active,
    request_processing_stop as _request_processing_stop,
    start_background_preparation,
    start_background_processing,
)
from docxaicorrector.core.logger import fail_critical, log_event, present_error
from docxaicorrector.generation.message_formatting import get_preparation_state_unavailable_message, get_restartable_outcome_notice
from docxaicorrector.processing.processing_runtime import (
    freeze_uploaded_file,
    get_current_result_bundle,
    resolve_uploaded_filename,
)
from docxaicorrector.runtime.artifacts import AppReadyMarkerWriter
from docxaicorrector.runtime.state import (
    apply_recommended_widget_state,
    clear_recommended_text_settings_notice_token,
    consume_recommended_text_settings_pending_widget_state,
    get_active_segment_id,
    get_active_segment_title,
    get_latest_preparation_summary,
    get_manual_text_settings_override_for_token,
    get_latest_image_mode,
    get_recommended_text_settings_applied_for_token,
    get_recommended_text_settings_applied_snapshot,
    get_recommended_text_settings_notice_details,
    get_recommended_text_settings_notice_token,
    get_selected_segment_ids,
    get_structure_confirmed,
    get_confirmed_structure_fingerprint,
    get_confirmed_at_settings_hash,
    get_segments_loaded_for_source_token,
    get_structure_manifest_notice_details,
    get_structure_manifest_notice_token,
    get_text_transform_assessment,
    get_latest_source_token,
    get_processing_outcome,
    get_processing_session_snapshot,
    get_prepared_run_context_for_marker,
    get_restart_source_filename,
    get_segment_progress_by_id,
    get_segment_status_by_id,
    has_persisted_source,
    init_session_state,
    is_app_start_logged,
    is_preparation_failed_for_marker,
    is_persisted_source_cleanup_done,
    is_processing_stop_requested,
    mark_app_start_logged,
    mark_persisted_source_cleanup_done,
    push_activity,
    reset_run_state,
    set_selected_segment_ids,
    set_manual_text_settings_override_for_token,
    set_recommended_text_settings,
    set_recommended_text_settings_applied,
    set_recommended_text_settings_notice,
    set_recommended_text_settings_pending_widget_state,
    set_latest_preparation_summary,
    set_structure_confirmation_state,
    set_text_transform_assessment,
    set_structure_manifest_notice,
    set_processing_status,
    should_start_preparation_for_marker,
)
from docxaicorrector.text.transform_assessment import TextTransformAssessment, assess_text_transform_excerpt, build_text_transform_warnings
from docxaicorrector.ui._ui import (
    get_source_language_widget_value,
    get_target_language_label,
    get_text_operation_label,
    get_text_setting_widget_keys,
    inject_ui_styles,
    render_image_validation_summary,
    render_file_uploader_state_styles,
    render_intro_layout_styles,
    render_live_status,
    render_markdown_preview,
    render_partial_result,
    render_preparation_summary,
    render_result,
    render_result_bundle,
    render_run_log,
    render_section_gap,
    render_sidebar,
)
from docxaicorrector.runtime.workflow_state import IdleViewState, ProcessingOutcome, has_restartable_outcome

PERSISTED_SOURCE_TTL_SECONDS = 12 * 60 * 60
APP_READY_FRESHNESS_WINDOW_SECONDS = 15.0
_CLEANUP_THREAD_LOCK = threading.Lock()
_CLEANUP_THREAD_STARTED = False
_APP_READY_MARKER_WRITER = AppReadyMarkerWriter(
    path=APP_READY_PATH,
    freshness_window_seconds=APP_READY_FRESHNESS_WINDOW_SECONDS,
    time_fn=time.monotonic,
)


@st.cache_resource
def _cached_load_app_config():
    return load_app_config()


def _schedule_stale_persisted_sources_cleanup() -> None:
    global _CLEANUP_THREAD_STARTED
    if is_persisted_source_cleanup_done():
        return
    with _CLEANUP_THREAD_LOCK:
        if _CLEANUP_THREAD_STARTED:
            return
        _CLEANUP_THREAD_STARTED = True

    def worker() -> None:
        from docxaicorrector.processing.restart_store import cleanup_stale_persisted_sources

        try:
            cleanup_stale_persisted_sources(max_age_seconds=PERSISTED_SOURCE_TTL_SECONDS)
        finally:
            with _CLEANUP_THREAD_LOCK:
                global _CLEANUP_THREAD_STARTED
                _CLEANUP_THREAD_STARTED = False

    threading.Thread(target=worker, daemon=True, name="persisted-source-cleanup").start()
    mark_persisted_source_cleanup_done()


def _mark_app_ready() -> None:
    _APP_READY_MARKER_WRITER.mark_ready()


def _finalize_app_frame(*, add_section_gap: bool = False) -> None:
    if add_section_gap:
        render_section_gap("lg")
    _mark_app_ready()
    _schedule_stale_persisted_sources_cleanup()


def _is_uploaded_file_too_large(uploaded_file) -> bool:
    file_size = getattr(uploaded_file, "size", None)
    return isinstance(file_size, int) and file_size > MAX_DOCX_ARCHIVE_SIZE_BYTES


def _start_background_processing(
    *,
    uploaded_filename: str,
    uploaded_token: str,
    source_bytes: bytes,
    jobs: list[dict[str, str | int]],
    selected_segment_ids: list[str] | None = None,
    source_paragraphs: list,
    image_assets: list,
    image_mode: str,
    app_config: dict[str, object],
    model: str,
    max_retries: int,
    processing_operation: str = "edit",
    source_language: str = "en",
    target_language: str = "ru",
) -> None:
    def worker_entrypoint(
        *,
        runtime,
        uploaded_filename,
        jobs,
        selected_segment_ids,
        source_paragraphs,
        image_assets,
        image_mode,
        app_config,
        model,
        max_retries,
        processing_operation,
        source_language,
        target_language,
    ) -> None:
        from docxaicorrector.processing.processing_service import get_processing_service

        get_processing_service().run_processing_worker(
            runtime=runtime,
            uploaded_filename=uploaded_filename,
            jobs=jobs,
            selected_segment_ids=selected_segment_ids,
            source_paragraphs=source_paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
        )

    start_background_processing(
        worker_target=worker_entrypoint,
        uploaded_filename=uploaded_filename,
        uploaded_token=uploaded_token,
        source_bytes=source_bytes,
        jobs=jobs,
        selected_segment_ids=selected_segment_ids,
        source_paragraphs=source_paragraphs,
        image_assets=image_assets,
        image_mode=image_mode,
        app_config=app_config,
        model=model,
        max_retries=max_retries,
        processing_operation=processing_operation,
        source_language=source_language,
        target_language=target_language,
    )


def _resolve_sidebar_settings(sidebar_result):
    if isinstance(sidebar_result, tuple) and len(sidebar_result) == 10:
        return sidebar_result
    if isinstance(sidebar_result, tuple) and len(sidebar_result) == 9:
        return (*sidebar_result, False)
    if isinstance(sidebar_result, tuple) and len(sidebar_result) == 8:
        return (*sidebar_result, False, False)
    if isinstance(sidebar_result, tuple) and len(sidebar_result) == 5:
        model, chunk_size, max_retries, image_mode, keep_all_image_variants = sidebar_result
        return model, chunk_size, max_retries, image_mode, keep_all_image_variants, "edit", "en", "ru", False, False
    raise RuntimeError("Некорректный контракт render_sidebar().")


def _start_background_preparation(
    *,
    uploaded_payload,
    upload_marker: str,
    chunk_size: int,
    image_mode: str,
    keep_all_image_variants: bool,
    processing_operation: str = "edit",
    app_config: dict[str, object] | None = None,
) -> None:
    start_background_preparation(
        worker_target=application_flow.prepare_run_context_for_background,
        uploaded_payload=uploaded_payload,
        upload_marker=upload_marker,
        chunk_size=chunk_size,
        image_mode=image_mode,
        keep_all_image_variants=keep_all_image_variants,
        processing_operation=processing_operation,
        app_config=app_config,
    )


def _store_preparation_summary(*, prepared_run_context) -> None:
    elapsed_seconds = float(getattr(prepared_run_context, "preparation_elapsed_seconds", 0.0) or 0.0)
    elapsed = f"{elapsed_seconds:.1f} c" if elapsed_seconds > 0 else ""
    structure_summary = application_flow.resolve_structure_recognition_summary(prepared_run_context)
    normalization_metrics = application_flow.flatten_normalization_metrics(
        getattr(prepared_run_context, "normalization_report", None)
    )
    relation_metrics = application_flow.flatten_relation_metrics(
        getattr(prepared_run_context, "relation_report", None)
    )
    cleanup_metrics = application_flow.flatten_layout_cleanup_metrics(
        getattr(prepared_run_context, "cleanup_report", None)
    )
    structure_status_note = application_flow.build_structure_processing_status_note(prepared_run_context)
    cleanup_status_note = application_flow.build_layout_cleanup_status_note(
        getattr(prepared_run_context, "cleanup_report", None)
    )
    structure_repair_status_note = application_flow.build_structure_repair_status_note(
        getattr(prepared_run_context, "structure_repair_report", None)
    )
    status_notes = [note for note in (structure_status_note, structure_repair_status_note, cleanup_status_note) if note]
    exported_manifest_path = str(getattr(prepared_run_context, "exported_structure_manifest_path", "") or "")
    if exported_manifest_path:
        status_notes.append(f"Structure manifest: {exported_manifest_path}")
    summary = {
        "stage": str(getattr(prepared_run_context, "preparation_stage", "Документ подготовлен")),
        "detail": str(getattr(prepared_run_context, "preparation_detail", "")),
        "file_size_bytes": len(prepared_run_context.uploaded_file_bytes),
        "source_format": str(getattr(prepared_run_context, "source_format", "docx") or "docx"),
        "conversion_backend": getattr(prepared_run_context, "conversion_backend", None),
        "paragraph_count": len(prepared_run_context.paragraphs),
        "image_count": len(prepared_run_context.image_assets),
        "source_chars": len(prepared_run_context.source_text),
        "block_count": len(prepared_run_context.jobs),
        "cached": bool(getattr(prepared_run_context, "preparation_cached", False)),
        "quality_gate_status": str(getattr(prepared_run_context, "quality_gate_status", "pass") or "pass"),
        **structure_summary.as_preparation_summary_metrics(),
        "elapsed": elapsed,
        "progress": 1.0,
        "status_notes": status_notes,
        **normalization_metrics,
        **relation_metrics,
        **cleanup_metrics,
    }
    structure_fingerprint = str(getattr(prepared_run_context, "structure_fingerprint", "") or "")
    detector_version = str(getattr(prepared_run_context, "detector_version", "") or "")
    segment_count = len(getattr(prepared_run_context, "segments", []) or [])
    diagnostics = getattr(prepared_run_context, "segment_diagnostics", None)
    if structure_fingerprint:
        summary["structure_fingerprint"] = structure_fingerprint
    if detector_version:
        summary["detector_version"] = detector_version
    if segment_count > 0:
        summary["segment_count"] = segment_count
    if diagnostics is not None and segment_count > 0:
        summary["high_confidence_count"] = int(getattr(diagnostics, "high_confidence_count", 0) or 0)
        summary["medium_confidence_count"] = int(getattr(diagnostics, "medium_confidence_count", 0) or 0)
        summary["low_confidence_count"] = int(getattr(diagnostics, "low_confidence_count", 0) or 0)
        summary["toc_entry_count"] = int(getattr(diagnostics, "toc_entry_count", 0) or 0)
        summary["toc_matched_count"] = int(getattr(diagnostics, "toc_matched_count", 0) or 0)
    if exported_manifest_path:
        summary["manifest_path"] = exported_manifest_path
    set_latest_preparation_summary(summary)


def _assess_text_transform(*, source_text: str, target_language: str) -> TextTransformAssessment:
    assessment = assess_text_transform_excerpt(source_text, target_language=target_language)
    set_text_transform_assessment(assessment)
    return assessment


def _handle_structure_manifest_export(*, prepared_run_context, app_config: dict[str, object], chunk_size: int) -> None:
    manifest_path = application_flow.export_structure_manifest(
        prepared_run_context=prepared_run_context,
        app_config={
            **app_config,
            "chunk_size": chunk_size,
        },
    )
    uploaded_token = str(getattr(prepared_run_context, "uploaded_file_token", "") or "")
    set_structure_manifest_notice(
        file_token=uploaded_token,
        details={
            "file_token": uploaded_token,
            "manifest_path": manifest_path,
            "structure_fingerprint": str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
        },
    )
    _store_preparation_summary(prepared_run_context=prepared_run_context)
    log_event(
        logging.INFO,
        "structure_manifest_exported",
        "Экспортирован manifest обнаруженной структуры.",
        filename=str(getattr(prepared_run_context, "uploaded_filename", "") or ""),
        file_token=uploaded_token,
        manifest_path=manifest_path,
        structure_fingerprint=str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
        segment_count=len(getattr(prepared_run_context, "segments", []) or []),
    )


def _build_structure_settings_hash(*, uploaded_file_token: str, prepared_run_context, chunk_size: int) -> str:
    payload = {
        "uploaded_file_token": uploaded_file_token,
        "structure_fingerprint": str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
        "detector_version": str(getattr(prepared_run_context, "detector_version", "") or ""),
        "structure_recognition_mode": str(getattr(prepared_run_context, "structure_recognition_mode", "off") or "off"),
        "chunk_size": int(chunk_size or 0),
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def _sync_structure_review_state(*, prepared_run_context, uploaded_file_token: str, chunk_size: int) -> dict[str, object]:
    segments = list(cast(Any, getattr(prepared_run_context, "segments", None)) or [])
    segment_ids = [str(getattr(segment, "segment_id", "") or "") for segment in segments if str(getattr(segment, "segment_id", "") or "").strip()]
    current_settings_hash = _build_structure_settings_hash(
        uploaded_file_token=uploaded_file_token,
        prepared_run_context=prepared_run_context,
        chunk_size=chunk_size,
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


def _build_structure_invalidation_summary(review_state: dict[str, object]) -> str:
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


def _build_selected_processing_payload(*, prepared_run_context, selected_segment_ids: list[str] | None) -> dict[str, object]:
    segments = list(cast(Any, getattr(prepared_run_context, "segments", None)) or [])
    selected_segment_id_set = {
        str(segment_id).strip() for segment_id in (selected_segment_ids or []) if str(segment_id).strip()
    }
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


def _build_segment_status_summary_line(*, segments: list[object], segment_status_by_id: dict[str, str]) -> str:
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


def _build_selected_segment_status_summary_line(*, selected_segments: list[object], segment_status_by_id: dict[str, str]) -> str:
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


def _is_segment_selection_locked(segment_status: str) -> bool:
    return _normalize_segment_status(segment_status) in {"queued", "processing"}


def _build_bulk_selectable_segment_ids(*, visible_segments: list[object], segment_status_by_id: dict[str, str]) -> list[str]:
    selectable_segment_ids: list[str] = []
    for segment in visible_segments:
        segment_id = str(getattr(segment, "segment_id", "") or "").strip()
        if not segment_id:
            continue
        if _is_segment_selection_locked(segment_status_by_id.get(segment_id, "pending")):
            continue
        selectable_segment_ids.append(segment_id)
    return selectable_segment_ids


def _segment_matches_review_filters(
    *,
    segment: object,
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
        return "Completed in this session. This segment can be selected again for reprocess/export later."
    if normalized_status == "failed":
        return "Failed in this session. Retry UI is not available yet in the current phase."
    if normalized_status == "skipped":
        return "Skipped in the current session workflow. Usually excluded by default."
    return ""


def _render_analysis_review_panel(*, prepared_run_context, uploaded_file_token: str, chunk_size: int) -> str | None:
    segments = list(cast(Any, getattr(prepared_run_context, "segments", None)) or [])
    if not segments:
        return None
    review_state = _sync_structure_review_state(
        prepared_run_context=prepared_run_context,
        uploaded_file_token=uploaded_file_token,
        chunk_size=chunk_size,
    )
    selected_segment_ids = list(cast(Any, review_state["selected_segment_ids"]))
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

    segment_status_by_id = get_segment_status_by_id()
    segment_progress_by_id = get_segment_progress_by_id()
    active_segment_id = get_active_segment_id()
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
    visible_segment_ids = {
        str(getattr(segment, "segment_id", "") or "").strip()
        for segment in visible_segments
        if str(getattr(segment, "segment_id", "") or "").strip()
    }
    visible_selectable_segment_ids = _build_bulk_selectable_segment_ids(
        visible_segments=visible_segments,
        segment_status_by_id=segment_status_by_id,
    )
    all_selectable_segment_ids = _build_bulk_selectable_segment_ids(
        visible_segments=segments,
        segment_status_by_id=segment_status_by_id,
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
        bulk_updated_selection = [segment_id for segment_id in selected_segment_ids if segment_id not in visible_segment_ids]
    if bulk_all_col.button(
        "Select Entire Book",
        use_container_width=True,
        disabled=not bool(all_selectable_segment_ids),
        key="select_entire_book_segments_button",
    ):
        bulk_updated_selection = list(all_selectable_segment_ids)
    current_selection_ids = list(bulk_updated_selection if bulk_updated_selection is not None else selected_segment_ids)
    current_selection_set = set(current_selection_ids)
    updated_selection = [segment_id for segment_id in current_selection_ids if segment_id not in visible_segment_ids]
    for segment in visible_segments:
        segment_job_count = len((getattr(prepared_run_context, "segment_to_job", {}) or {}).get(segment.segment_id, ()))
        segment_status = segment_status_by_id.get(segment.segment_id, "pending")
        segment_progress = segment_progress_by_id.get(segment.segment_id, 0.0)
        active_segment_suffix = " | active" if active_segment_id == segment.segment_id else ""
        label = (
            f"{segment.title} | {segment.word_count} words | {segment.confidence} | "
            f"{segment.structural_role} | approx. {segment_job_count} jobs | "
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
            updated_selection.append(segment.segment_id)
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
    if updated_selection != selected_segment_ids:
        set_selected_segment_ids(updated_selection)
        selected_segment_ids = updated_selection
        if structure_confirmed:
            set_structure_confirmation_state(
                structure_confirmed=False,
                confirmed_structure_fingerprint="",
                confirmed_at_settings_hash="",
                segments_loaded_for_source_token=uploaded_file_token,
            )
            structure_confirmed = False

    selected_segments = [segment for segment in segments if segment.segment_id in set(selected_segment_ids)]
    selected_word_count = sum(int(getattr(segment, "word_count", 0) or 0) for segment in selected_segments)
    selected_job_count = sum(
        len((getattr(prepared_run_context, "segment_to_job", {}) or {}).get(segment.segment_id, ()))
        for segment in selected_segments
    )
    can_process_selected = structure_confirmed and bool(selected_segment_ids) and selected_job_count > 0
    st.info(
        f"Selected: {len(selected_segments)} segments | {selected_word_count} words | approx. {selected_job_count} jobs"
    )
    selected_status_summary_line = _build_selected_segment_status_summary_line(
        selected_segments=selected_segments,
        segment_status_by_id=segment_status_by_id,
    )
    if selected_status_summary_line:
        st.caption(selected_status_summary_line)

    confirm_col, selected_col, full_book_col = st.columns(3)
    current_settings_hash = str(review_state["settings_hash"])
    current_fingerprint = str(review_state["fingerprint"])
    if confirm_col.button("Confirm Structure", use_container_width=True, key="confirm_structure_button"):
        set_structure_confirmation_state(
            structure_confirmed=True,
            confirmed_structure_fingerprint=current_fingerprint,
            confirmed_at_settings_hash=current_settings_hash,
            segments_loaded_for_source_token=uploaded_file_token,
        )
        log_event(
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
            else "Confirm the current structure and keep at least one segment selected to process only chosen chapters."
        ),
        key="process_selected_button",
    ):
        return "start_selected"
    if full_book_col.button("Process Entire Book", type="primary", use_container_width=True, key="process_entire_book_button"):
        return "start_full_book"
    if structure_confirmed:
        st.success("Structure confirmed for the current prepared document.")
        if can_process_selected:
            st.caption("Process Selected now runs only the chosen chapters and produces a partial output artifact.")
    else:
        st.caption("Confirm the detected structure before chapter-based processing becomes available in a later phase.")
    return None


def _current_text_settings(*, processing_operation: str, source_language: str, target_language: str) -> dict[str, str]:
    return {
        "processing_operation": processing_operation,
        "source_language": source_language,
        "target_language": target_language,
    }


def _default_text_settings(config: dict[str, object]) -> dict[str, str]:
    return {
        "processing_operation": str(config.get("processing_operation_default", "edit")),
        "source_language": str(config.get("source_language_default", "en")),
        "target_language": str(config.get("target_language_default", "ru")),
    }


def _text_setting_display_value(*, config: dict[str, object], field: str, value: str) -> str:
    if field == "processing_operation":
        return get_text_operation_label(value)
    if field == "source_language":
        return get_source_language_widget_value(config, value)
    if field == "target_language":
        return get_target_language_label(config, value)
    return value


def _describe_recommended_text_setting_changes(
    *,
    config: dict[str, object],
    current_settings: dict[str, str],
    recommendation: RecommendedTextSettings,
    manual_override: ManualTextSettingsOverride,
) -> list[str]:
    field_labels = {
        "processing_operation": "режим",
        "source_language": "язык оригинала",
        "target_language": "целевой язык",
    }
    changes: list[str] = []
    for field in TEXT_SETTINGS_FIELDS:
        if bool(manual_override.get(field, False)):
            continue
        current_value = str(current_settings[field])
        recommended_value = str(recommendation[field])
        if current_value == recommended_value:
            continue
        from_value = _text_setting_display_value(config=config, field=field, value=current_value)
        to_value = _text_setting_display_value(config=config, field=field, value=recommended_value)
        changes.append(f"{field_labels[field]}: изменено с {from_value} на {to_value}")
    return changes


def _build_recommended_text_settings_notice(uploaded_file_token: str) -> str | None:
    if not _should_render_recommended_text_settings_notice(uploaded_file_token):
        return None
    notice_details = get_recommended_text_settings_notice_details()
    if not isinstance(notice_details, dict) or str(notice_details.get("file_token", "")) != uploaded_file_token:
        return "После анализа файла приложение скорректировало текстовые настройки до рекомендуемых для этого документа."
    changes = notice_details.get("changes")
    if not isinstance(changes, list):
        return "После анализа файла приложение скорректировало текстовые настройки до рекомендуемых для этого документа."
    normalized_changes = [str(change).strip() for change in changes if str(change).strip()]
    if not normalized_changes:
        return "После анализа файла приложение скорректировало текстовые настройки до рекомендуемых для этого документа."
    return (
        "После анализа файла приложение скорректировало текстовые настройки: "
        + "; ".join(normalized_changes)
        + "."
    )


def _apply_recommended_widget_state(
    *,
    config: dict[str, object],
    recommendation: RecommendedTextSettings,
    manual_override: ManualTextSettingsOverride,
) -> dict[str, str]:
    widget_keys = get_text_setting_widget_keys()
    updates: dict[str, str] = {}
    if not bool(manual_override.get("processing_operation", False)):
        operation_label = get_text_operation_label(str(recommendation["processing_operation"]))
        if st.session_state.get(widget_keys["processing_operation"]) != operation_label:
            updates[widget_keys["processing_operation"]] = operation_label
    if not bool(manual_override.get("target_language", False)):
        target_label = get_target_language_label(config, str(recommendation["target_language"]))
        if st.session_state.get(widget_keys["target_language"]) != target_label:
            updates[widget_keys["target_language"]] = target_label
    if not bool(manual_override.get("source_language", False)):
        source_widget_value = get_source_language_widget_value(config, str(recommendation["source_language"]))
        if st.session_state.get(widget_keys["source_language"]) != source_widget_value:
            updates[widget_keys["source_language"]] = source_widget_value
    return updates


def _apply_pending_recommended_widget_state() -> None:
    pending_state = consume_recommended_text_settings_pending_widget_state()
    if not isinstance(pending_state, dict):
        return
    widget_state = pending_state.get("widget_state")
    if not isinstance(widget_state, dict):
        return
    apply_recommended_widget_state(widget_state)


def _maybe_apply_file_recommendations(
    *,
    app_config: dict[str, object],
    prepared_run_context,
    assessment: TextTransformAssessment,
    processing_operation: str,
    source_language: str,
    target_language: str,
) -> None:
    file_token = str(getattr(prepared_run_context, "uploaded_file_token", ""))
    if not file_token:
        return

    current_settings = _current_text_settings(
        processing_operation=processing_operation,
        source_language=source_language,
        target_language=target_language,
    )
    source_visible = processing_operation == "translate"
    manual_override = normalize_manual_text_settings_override(
        get_manual_text_settings_override_for_token(),
        file_token=file_token,
    )
    applied_for_token = get_recommended_text_settings_applied_for_token()
    notice_token = get_recommended_text_settings_notice_token()
    applied_snapshot = normalize_recommendation_snapshot(
        get_recommended_text_settings_applied_snapshot(),
        file_token=file_token,
    )

    if notice_token and notice_token != file_token and applied_for_token != file_token:
        clear_recommended_text_settings_notice_token()

    if applied_for_token != file_token:
        manual_override = mark_manual_overrides_from_baseline(
            manual_override,
            current_settings=current_settings,
            baseline_settings=_default_text_settings(app_config),
            source_visible=source_visible,
        )

    recommendation = derive_recommended_text_settings(
        file_token=file_token,
        assessment=assessment,
        current_settings=current_settings,
    )
    set_recommended_text_settings(recommendation)

    if applied_for_token == file_token:
        manual_override_before_recommendation = dict(manual_override)
        if applied_snapshot is not None:
            manual_override = mark_manual_overrides_from_snapshot(
                manual_override,
                current_settings=current_settings,
                applied_snapshot=applied_snapshot,
            )
        else:
            manual_override = mark_manual_overrides_from_recommendation(
                manual_override,
                current_settings=current_settings,
                recommended_settings=recommendation,
                source_visible=source_visible,
            )
        set_manual_text_settings_override_for_token(manual_override)
        if any(
            not bool(manual_override_before_recommendation.get(field, False))
            and bool(manual_override.get(field, False))
            for field in TEXT_SETTINGS_FIELDS
        ):
            clear_recommended_text_settings_notice_token()
        return

    set_manual_text_settings_override_for_token(manual_override)
    widget_state_updates = _apply_recommended_widget_state(
        config=app_config,
        recommendation=recommendation,
        manual_override=manual_override,
    )
    applied_snapshot_payload = {
        "file_token": file_token,
        "processing_operation": str(recommendation["processing_operation"]),
        "source_language": str(recommendation["source_language"]),
        "target_language": str(recommendation["target_language"]),
    }
    set_recommended_text_settings_applied(file_token=file_token, snapshot=applied_snapshot_payload)
    did_change = bool(widget_state_updates)
    notice_changes = _describe_recommended_text_setting_changes(
        config=app_config,
        current_settings=current_settings,
        recommendation=recommendation,
        manual_override=manual_override,
    )
    pending_widget_state = (
        {
            "file_token": file_token,
            "widget_state": widget_state_updates,
        }
        if did_change
        else None
    )
    notice_details = (
        {
            "file_token": file_token,
            "changes": notice_changes,
        }
        if did_change
        else None
    )
    set_recommended_text_settings_pending_widget_state(pending_widget_state)
    set_recommended_text_settings_notice(file_token=file_token if did_change else None, details=notice_details)
    if did_change:
        st.rerun()


def _should_render_recommended_text_settings_notice(uploaded_file_token: str) -> bool:
    notice_token = get_recommended_text_settings_notice_token()
    return bool(uploaded_file_token) and notice_token == uploaded_file_token


def _render_processing_controls(*, can_start: bool, is_processing: bool, emphasize_start: bool = True) -> str | None:
    stop_requested = is_processing_stop_requested()
    start_col, stop_col = st.columns(2)

    start_label = "Обработка запущена" if is_processing else ("Начать обработку" if emphasize_start else "Обработать повторно")
    if start_col.button(
        start_label,
        type="primary" if emphasize_start else "secondary",
        use_container_width=True,
        disabled=(not can_start) or is_processing,
        key="start_processing_button",
    ):
        return "start"

    if stop_col.button(
        "Останавливаю..." if stop_requested else "Стоп",
        use_container_width=True,
        disabled=(not is_processing) or stop_requested,
        key="stop_processing_button",
    ):
        return "stop"

    return None


def main() -> None:
    init_session_state()
    _drain_processing_events()
    _drain_preparation_events()
    inject_ui_styles()
    if not is_app_start_logged():
        log_event(logging.INFO, "app_start", "Приложение инициализировано")
        mark_app_start_logged()

    try:
        app_config = _cached_load_app_config()
    except Exception as exc:
        user_message = present_error("config_load_failed", exc, "Ошибка загрузки конфигурации")
        st.error(f"Ошибка загрузки конфигурации: {user_message}")
        return

    _apply_pending_recommended_widget_state()

    (
        model,
        chunk_size,
        max_retries,
        image_mode,
        keep_all_image_variants,
        processing_operation,
        source_language,
        target_language,
        translation_second_pass_enabled,
        audiobook_postprocess_enabled,
    ) = _resolve_sidebar_settings(render_sidebar(app_config))
    app_config = dict(app_config)
    app_config["keep_all_image_variants"] = keep_all_image_variants
    app_config["processing_operation"] = processing_operation
    app_config["source_language"] = source_language
    app_config["target_language"] = target_language
    app_config["translation_second_pass_enabled"] = translation_second_pass_enabled
    app_config["audiobook_postprocess_enabled"] = audiobook_postprocess_enabled

    processing_active = _processing_worker_is_active()
    processing_outcome = get_processing_outcome()
    processing_in_progress = processing_active or processing_outcome == ProcessingOutcome.RUNNING.value
    preparation_active = _preparation_worker_is_active()
    current_result = get_current_result_bundle()

    render_intro_layout_styles()

    st.title("AI-редактор DOCX/DOC/PDF через Markdown")
    st.write(
        "Загрузите DOCX, legacy DOC или PDF. Приложение при необходимости автоконвертирует исходник в DOCX, "
        "соберет смысловые блоки из нескольких абзацев, добавит соседний контекст для модели и соберет новый DOCX."
    )
    st.caption(
        "PDF импортируется через преобразование в DOCX; качество структуры и форматирования зависит от исходного PDF и конвертера."
    )
    uploaded_widget_file = st.file_uploader("Загрузите DOCX/DOC/PDF-файл", type=["docx", "doc", "pdf"])
    render_file_uploader_state_styles(has_uploaded_file=uploaded_widget_file is not None)

    if processing_in_progress:
        @st.fragment(run_every=2)
        def render_processing_panel() -> None:
            _drain_processing_events()
            render_live_status()
            render_run_log()
            render_image_validation_summary()
            render_partial_result()
            _finalize_app_frame(add_section_gap=True)

            still_running = get_processing_outcome() == ProcessingOutcome.RUNNING.value
            action = _render_processing_controls(can_start=False, is_processing=still_running)
            if action == "stop":
                push_activity("Остановлено. Завершение текущего шага...")
                _request_processing_stop()
                st.rerun()

            if not still_running:
                st.rerun()

        render_processing_panel()
        return

    @st.fragment(run_every=1)
    def render_preparation_panel() -> None:
        _drain_preparation_events()
        render_live_status()
        render_run_log()
        _finalize_app_frame()
        if not _preparation_worker_is_active():
            st.rerun()

    if uploaded_widget_file is not None and _is_uploaded_file_too_large(uploaded_widget_file):
        st.error(
            f"Размер DOCX/DOC/PDF превышает допустимый предел {MAX_DOCX_ARCHIVE_SIZE_BYTES // (1024 * 1024)} МБ. Загрузите файл меньшего размера."
        )
        render_run_log()
        _finalize_app_frame()
        return

    if preparation_active:
        render_preparation_panel()
        return

    if (
        uploaded_widget_file is None
        and current_result is None
        and not has_persisted_source()
    ):
        render_run_log()
        render_image_validation_summary()
        render_partial_result()
        _finalize_app_frame()
        return

    uploaded_widget_payload = None
    if uploaded_widget_file is not None:
        try:
            uploaded_widget_payload = freeze_uploaded_file(uploaded_widget_file)
        except Exception as exc:
            user_message = present_error(
                "document_read_failed",
                exc,
                "Ошибка чтения документа",
                filename=resolve_uploaded_filename(uploaded_widget_file),
            )
            st.error(f"Ошибка чтения документа: {user_message}")
            render_run_log()
            _finalize_app_frame()
            return
        preparation_request_marker = build_preparation_request_marker(
            uploaded_widget_payload,
            chunk_size=chunk_size,
            processing_operation=processing_operation,
        )
        prepared_run_context = get_prepared_run_context_for_marker(preparation_request_marker)
        if should_start_preparation_for_marker(preparation_request_marker):
            _start_background_preparation(
                uploaded_payload=uploaded_widget_payload,
                upload_marker=preparation_request_marker,
                chunk_size=chunk_size,
                image_mode=image_mode,
                keep_all_image_variants=keep_all_image_variants,
                processing_operation=processing_operation,
                app_config=app_config,
            )
            render_preparation_panel()
            return
        if is_preparation_failed_for_marker(preparation_request_marker):
            if st.session_state.last_error:
                st.error(st.session_state.last_error)
            render_live_status()
            render_run_log()
            _finalize_app_frame()
            return

    session_state = cast(application_flow.SessionStateLike, st.session_state)

    uploaded_file = application_flow.resolve_effective_uploaded_file(
        uploaded_file=uploaded_widget_file,
        current_result=current_result,
        session_state=session_state,
    )

    prepared_run_context = None
    if uploaded_widget_payload is not None:
        current_preparation_request_marker = build_preparation_request_marker(
            uploaded_widget_payload,
            chunk_size=chunk_size,
            processing_operation=processing_operation,
        )
        prepared_run_context = get_prepared_run_context_for_marker(current_preparation_request_marker)
        if prepared_run_context is None:
            st.warning(get_preparation_state_unavailable_message())
            render_live_status()
            render_run_log()
            _finalize_app_frame()
            return

    if application_flow.has_resettable_state(current_result=current_result, session_state=session_state):
        if st.button("Сбросить результаты", use_container_width=True):
            reset_run_state(keep_restart_source=False)
            st.rerun()
    idle_view_state = application_flow.derive_app_idle_view_state(
        current_result=current_result,
        uploaded_file=uploaded_file,
        session_state=session_state,
    )

    if idle_view_state != IdleViewState.FILE_SELECTED:
        if idle_view_state == IdleViewState.COMPLETED:
            if current_result is None:
                st.error("Результат обработки недоступен в текущей сессии.")
                _finalize_app_frame()
                return
            completed_result = cast(dict[str, object], current_result)
            render_run_log()
            render_image_validation_summary()
            render_markdown_preview(title="Предпросмотр Markdown")
            render_result_bundle(
                docx_bytes=cast(bytes | None, completed_result["docx_bytes"]),
                markdown_text=str(completed_result["markdown_text"]),
                original_filename=str(completed_result["source_name"]),
                narration_text=cast(str | None, completed_result.get("narration_text")),
                processing_operation=str(completed_result.get("processing_operation", "edit")),
                audiobook_postprocess_enabled=bool(completed_result.get("audiobook_postprocess_enabled", False)),
            )
        elif idle_view_state == IdleViewState.RESTARTABLE:
            processing_outcome = get_processing_outcome()
            restart_filename = get_restart_source_filename()
            outcome_notice = get_restartable_outcome_notice(processing_outcome, restart_filename)
            if outcome_notice is not None:
                notice_level, notice_message = outcome_notice
                getattr(st, notice_level)(notice_message)
            else:
                st.info("Можно изменить настройки и запустить обработку заново без повторной загрузки файла.")
            render_run_log()
            render_image_validation_summary()
            render_partial_result()
        _finalize_app_frame()
        return

    if prepared_run_context is None:
        try:
            prepared_run_context = application_flow.prepare_run_context(
                uploaded_file=uploaded_file,
                chunk_size=chunk_size,
                image_mode=image_mode,
                keep_all_image_variants=keep_all_image_variants,
                processing_operation=processing_operation,
                session_state=st.session_state,
                reset_run_state_fn=reset_run_state,
                fail_critical_fn=fail_critical,
                log_event_fn=log_event,
            )
        except Exception as exc:
            user_message = present_error(
                "document_read_failed",
                exc,
                "Ошибка чтения документа",
                filename=resolve_uploaded_filename(uploaded_file),
            )
            st.error(f"Ошибка чтения документа: {user_message}")
            return

    uploaded_filename = prepared_run_context.uploaded_filename
    uploaded_file_bytes = prepared_run_context.uploaded_file_bytes
    uploaded_file_token = prepared_run_context.uploaded_file_token
    paragraphs = prepared_run_context.paragraphs
    image_assets = prepared_run_context.image_assets
    jobs = prepared_run_context.jobs
    source_text = prepared_run_context.source_text
    assessment = _assess_text_transform(
        source_text=source_text,
        target_language=target_language,
    )
    _maybe_apply_file_recommendations(
        app_config=app_config,
        prepared_run_context=prepared_run_context,
        assessment=assessment,
        processing_operation=processing_operation,
        source_language=source_language,
        target_language=target_language,
    )
    processing_outcome = get_processing_outcome()
    restartable_outcome = has_restartable_outcome(processing_outcome)

    outcome_notice = get_restartable_outcome_notice(processing_outcome, uploaded_filename)
    if current_result is None and outcome_notice is not None:
        notice_level, notice_message = outcome_notice
        getattr(st, notice_level)(notice_message)

    _store_preparation_summary(prepared_run_context=prepared_run_context)
    if not processing_active and not restartable_outcome:
        normalization_metrics = application_flow.flatten_normalization_metrics(
            getattr(prepared_run_context, "normalization_report", None)
        )
        set_processing_status(
            stage="Документ подготовлен",
            detail="",
            current_block=0,
            block_count=len(jobs),
            file_size_bytes=len(uploaded_file_bytes),
            paragraph_count=len(paragraphs),
            image_count=len(image_assets),
            source_chars=len(source_text),
            cached=bool(getattr(prepared_run_context, "preparation_cached", False)),
            progress=1.0,
            is_running=False,
            phase="preparing",
            terminal_kind="completed",
            **normalization_metrics,
        )
    if not st.session_state.activity_feed and not restartable_outcome:
        push_activity(f"Документ разобран на {len(jobs)} блоков.")

    if len(jobs) == 1:
        st.info("Документ помещается в один блок. Для длинных файлов обработка пойдет по блокам с соседним контекстом.")

    notice_message = None
    if not restartable_outcome:
        for warning_message in build_text_transform_warnings(
            operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
            assessment=assessment,
        ):
            st.warning(warning_message)
        notice_message = _build_recommended_text_settings_notice(uploaded_file_token)

    if st.session_state.last_error:
        st.error(st.session_state.last_error)
        st.caption(st.session_state.last_log_hint)

    processing_snapshot = get_processing_session_snapshot()
    has_completed_result = bool(
        (st.session_state.latest_docx_bytes or st.session_state.get("latest_narration_text"))
        and processing_snapshot.latest_source_token == uploaded_file_token
    )
    if not restartable_outcome:
        preparation_summary = get_latest_preparation_summary()
        if isinstance(preparation_summary, dict) and notice_message is not None:
            status_notes = [str(note).strip() for note in preparation_summary.get("status_notes", []) if str(note).strip()]
            status_notes.append(notice_message)
            preparation_summary = {
                **preparation_summary,
                "status_notes": status_notes,
            }
        manifest_notice = get_structure_manifest_notice_details()
        if (
            isinstance(preparation_summary, dict)
            and isinstance(manifest_notice, dict)
            and get_structure_manifest_notice_token() == uploaded_file_token
        ):
            manifest_path = str(manifest_notice.get("manifest_path", "") or "")
            if manifest_path:
                status_notes = [str(note).strip() for note in preparation_summary.get("status_notes", []) if str(note).strip()]
                manifest_note = f"Structure manifest: {manifest_path}"
                if manifest_note not in status_notes:
                    status_notes.append(manifest_note)
                preparation_summary = {
                    **preparation_summary,
                    "manifest_path": manifest_path,
                    "status_notes": status_notes,
                }
        render_preparation_summary(preparation_summary)
        if st.button("Export Structure Manifest", use_container_width=True, key="export_structure_manifest_button"):
            _handle_structure_manifest_export(
                prepared_run_context=prepared_run_context,
                app_config=app_config,
                chunk_size=chunk_size,
            )
            st.rerun()
        analysis_action = _render_analysis_review_panel(
            prepared_run_context=prepared_run_context,
            uploaded_file_token=uploaded_file_token,
            chunk_size=chunk_size,
        )
    render_run_log()
    render_image_validation_summary()
    render_partial_result()

    compare_panel.render_compare_all_apply_panel(
        latest_image_mode=get_latest_image_mode(),
        image_assets=st.session_state.image_assets,
        render_section_gap=render_section_gap,
    )

    if has_completed_result:
        render_markdown_preview(title="Предпросмотр Markdown")
        render_result(
            st.session_state.latest_docx_bytes,
            st.session_state.latest_markdown,
            uploaded_filename,
            st.session_state.get("latest_narration_text"),
            processing_operation=processing_snapshot.latest_processing_operation,
            audiobook_postprocess_enabled=processing_snapshot.latest_audiobook_postprocess_enabled,
        )

    _finalize_app_frame(add_section_gap=True)
    action = analysis_action if 'analysis_action' in locals() and analysis_action is not None else _render_processing_controls(
        can_start=True,
        is_processing=False,
        emphasize_start=not has_completed_result,
    )
    if action == "start":
        _start_background_processing(
            uploaded_filename=uploaded_filename,
            uploaded_token=uploaded_file_token,
            source_bytes=uploaded_file_bytes,
            jobs=cast(list[dict[str, str | int]], jobs),
            source_paragraphs=paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
        )
    elif action == "start_selected":
        selected_processing_payload = _build_selected_processing_payload(
            prepared_run_context=prepared_run_context,
            selected_segment_ids=get_selected_segment_ids(),
        )
        _start_background_processing(
            uploaded_filename=uploaded_filename,
            uploaded_token=uploaded_file_token,
            source_bytes=uploaded_file_bytes,
            jobs=cast(list[dict[str, str | int]], selected_processing_payload["jobs"]),
            selected_segment_ids=cast(list[str], selected_processing_payload["selected_segment_ids"]),
            source_paragraphs=cast(list, selected_processing_payload["source_paragraphs"]),
            image_assets=cast(list, selected_processing_payload["image_assets"]),
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
        )
        st.rerun()
    elif action == "start_full_book":
        _start_background_processing(
            uploaded_filename=uploaded_filename,
            uploaded_token=uploaded_file_token,
            source_bytes=uploaded_file_bytes,
            jobs=cast(list[dict[str, str | int]], jobs),
            source_paragraphs=paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
        )
        st.rerun()
