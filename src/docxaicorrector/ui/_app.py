import logging
import threading
import time
from typing import Any, Mapping, TypeAlias, cast

import streamlit as st

from docxaicorrector.ui.i18n import t

st.set_page_config(
    page_title=t("app.page_title"),
    layout="wide",
    initial_sidebar_state="expanded",
)

from docxaicorrector.core.constants import APP_READY_PATH, MAX_DOCX_ARCHIVE_SIZE_BYTES
import docxaicorrector.ui.application_flow as application_flow
import docxaicorrector.ui.compare_panel as compare_panel
from docxaicorrector.chapter_workflow.service import build_document_context_prompt as build_chapter_workflow_document_context_prompt
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
from docxaicorrector.processing.processing_runtime import (
    freeze_uploaded_file,
    freeze_uploaded_file_lightweight,
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
    render_image_validation_summary,
    render_intro_layout_styles,
    render_live_status,
    render_markdown_preview,
    render_partial_result,
    render_preparation_summary,
    render_result,
    render_result_bundle,
    render_run_log,
    render_sidebar,
)
from docxaicorrector.ui.structure_review_panel import (
    EffectiveSelectedProcessingState,
    SegmentLike,
    SelectedProcessingPayload,
    StructureReviewState,
    _build_effective_selected_processing_state as _structure_review_panel_build_effective_selected_processing_state,
    _build_retry_failed_processing_state as _structure_review_panel_build_retry_failed_processing_state,
    _get_selected_context_policy as _structure_review_panel_get_selected_context_policy,
    _build_selected_processing_payload as _structure_review_panel_build_selected_processing_payload,
    _build_structure_settings_hash as _structure_review_panel_build_structure_settings_hash,
    _expand_segment_ids_for_selection as _structure_review_panel_expand_segment_ids_for_selection,
    _render_analysis_review_panel as _structure_review_panel_render_analysis_review_panel,
)
from docxaicorrector.runtime.workflow_state import IdleViewState, ProcessingOutcome, has_restartable_outcome
from docxaicorrector.pipeline.contracts import SegmentSelection

PERSISTED_SOURCE_TTL_SECONDS = 12 * 60 * 60
APP_READY_FRESHNESS_WINDOW_SECONDS = 15.0
_CLEANUP_THREAD_LOCK = threading.Lock()
_CLEANUP_THREAD_STARTED = False
_APP_READY_MARKER_WRITER = AppReadyMarkerWriter(
    path=APP_READY_PATH,
    freshness_window_seconds=APP_READY_FRESHNESS_WINDOW_SECONDS,
    time_fn=time.monotonic,
)

SidebarSettings: TypeAlias = tuple[str, int, int, str, bool, str, str, str, bool, bool]

_build_structure_settings_hash = _structure_review_panel_build_structure_settings_hash
_build_selected_processing_payload = _structure_review_panel_build_selected_processing_payload
_build_effective_selected_processing_state = _structure_review_panel_build_effective_selected_processing_state
_build_retry_failed_processing_state = _structure_review_panel_build_retry_failed_processing_state
_expand_segment_ids_for_selection = _structure_review_panel_expand_segment_ids_for_selection


def _render_analysis_review_panel(
    *,
    prepared_run_context,
    uploaded_file_token: str,
    chunk_size: int,
    app_config: Mapping[str, object] | None = None,
) -> str | None:
    return _structure_review_panel_render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token=uploaded_file_token,
        chunk_size=chunk_size,
        app_config=app_config,
        build_structure_settings_hash_fn=_build_structure_settings_hash,
        log_event_fn=log_event,
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


def _finalize_app_frame() -> None:
    _mark_app_ready()
    _schedule_stale_persisted_sources_cleanup()


def _is_uploaded_file_too_large(uploaded_file) -> bool:
    file_size = getattr(uploaded_file, "size", None)
    return isinstance(file_size, int) and file_size > MAX_DOCX_ARCHIVE_SIZE_BYTES


def _show_notice(*, level: str, message: str) -> None:
    if level == "warning":
        st.warning(message)
        return
    if level == "error":
        st.error(message)
        return
    if level == "caption":
        st.caption(message)
        return
    if level == "info":
        st.info(message)
        return
    raise ValueError(f"Unsupported Streamlit notice level: {level}")


def _restartable_outcome_notice(outcome: str | None, uploaded_filename: str) -> tuple[str, str] | None:
    if outcome == "stopped":
        return ("warning", t("app.restartable_stopped_notice", filename=uploaded_filename))
    if outcome == "failed":
        return ("error", t("app.restartable_failed_notice", filename=uploaded_filename))
    return None


def _build_document_context_prompt(
    *,
    prepared_run_context: object,
    selected_segment_ids: list[str] | None = None,
    segment_selection: SegmentSelection | None = None,
) -> str:
    return build_chapter_workflow_document_context_prompt(
        prepared_run_context=prepared_run_context,
        selected_segment_ids=selected_segment_ids,
        segment_selection=segment_selection,
    )


def _get_prepared_segments(prepared_run_context: object) -> list[SegmentLike]:
    return cast(list[SegmentLike], list(getattr(prepared_run_context, "segments", None) or []))


def _start_background_processing(
    *,
    uploaded_filename: str,
    uploaded_token: str,
    source_bytes: bytes,
    prepared_source_key: str | None = None,
    structure_fingerprint: str | None = None,
    jobs: list[dict[str, str | int]],
    selected_segment_ids: list[str] | None = None,
    segment_selection: SegmentSelection | None = None,
    document_segments: list | None = None,
    output_mode: str | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
    source_paragraphs: list,
    image_assets: list,
    image_mode: str,
    app_config: dict[str, object],
    model: str,
    max_retries: int,
    processing_operation: str = "edit",
    source_language: str = "en",
    target_language: str = "ru",
    document_context_prompt: str = "",
) -> None:
    def worker_entrypoint(
        *,
        runtime,
        uploaded_filename,
        source_token="",
        run_id="",
        prepared_source_key,
        structure_fingerprint,
        jobs,
        selected_segment_ids,
        segment_selection=None,
        document_segments=None,
        output_mode,
        include_front_matter,
        include_toc,
        source_paragraphs,
        image_assets,
        image_mode,
        app_config,
        model,
        max_retries,
        processing_operation,
        source_language,
        target_language,
        document_context_prompt=document_context_prompt,
    ) -> None:
        from docxaicorrector.processing.processing_service import get_processing_service

        get_processing_service().run_processing_worker(
            runtime=runtime,
            uploaded_filename=uploaded_filename,
            source_token=source_token,
            run_id=run_id,
            prepared_source_key=prepared_source_key,
            structure_fingerprint=structure_fingerprint,
            jobs=jobs,
            selected_segment_ids=selected_segment_ids,
            segment_selection=segment_selection,
            document_segments=document_segments,
            output_mode=output_mode,
            include_front_matter=include_front_matter,
            include_toc=include_toc,
            source_paragraphs=source_paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            document_context_prompt=document_context_prompt,
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
        prepared_source_key=prepared_source_key,
        structure_fingerprint=structure_fingerprint,
        jobs=jobs,
        selected_segment_ids=selected_segment_ids,
        segment_selection=segment_selection,
        document_segments=document_segments,
        output_mode=output_mode,
        include_front_matter=include_front_matter,
        include_toc=include_toc,
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


def _resolve_sidebar_settings(sidebar_result: object) -> SidebarSettings:
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
    normalization_metrics = application_flow.flatten_normalization_metrics(
        getattr(prepared_run_context, "normalization_report", None)
    )
    relation_metrics = application_flow.flatten_relation_metrics(
        getattr(prepared_run_context, "relation_report", None)
    )
    cleanup_metrics = application_flow.flatten_layout_cleanup_metrics(
        getattr(prepared_run_context, "cleanup_report", None)
    )
    status_notes: list[str] = []
    exported_manifest_path = str(getattr(prepared_run_context, "exported_structure_manifest_path", "") or "")
    if exported_manifest_path:
        status_notes.append(t("status.prep_manifest_meta", path=exported_manifest_path))
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
        "processing_operation": t("recommend.field_operation"),
        "source_language": t("recommend.field_source_language"),
        "target_language": t("recommend.field_target_language"),
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
        changes.append(
            t("recommend.change_detail", field=field_labels[field], from_value=from_value, to_value=to_value)
        )
    return changes


def _build_recommended_text_settings_notice(uploaded_file_token: str) -> str | None:
    if not _should_render_recommended_text_settings_notice(uploaded_file_token):
        return None
    notice_details = get_recommended_text_settings_notice_details()
    if not isinstance(notice_details, dict) or str(notice_details.get("file_token", "")) != uploaded_file_token:
        return t("recommend.notice_generic")
    changes = notice_details.get("changes")
    if not isinstance(changes, list):
        return t("recommend.notice_generic")
    normalized_changes = [str(change).strip() for change in changes if str(change).strip()]
    if not normalized_changes:
        return t("recommend.notice_generic")
    return t("recommend.notice_with_changes", changes="; ".join(normalized_changes))


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

    start_label = (
        t("app.button_processing_running")
        if is_processing
        else (t("app.button_start_processing") if emphasize_start else t("app.button_reprocess"))
    )
    if start_col.button(
        start_label,
        type="primary" if emphasize_start else "secondary",
        use_container_width=True,
        disabled=(not can_start) or is_processing,
        key="start_processing_button",
    ):
        return "start"

    if stop_col.button(
        t("app.button_stopping") if stop_requested else t("app.button_stop"),
        use_container_width=True,
        disabled=(not is_processing) or stop_requested,
        key="stop_processing_button",
    ):
        return "stop"

    return None


def _render_completed_result_view(result: Mapping[str, object]) -> None:
    """Single completed-result renderer: markdown preview + download bundle + review block.

    Unifies the two former completed-render paths (IdleViewState.COMPLETED and
    FILE_SELECTED + has_completed_result) so both surface the formatting-review block
    from the same ``quality_warning`` DATA carried on the result bundle.
    """
    render_markdown_preview(title=t("app.markdown_preview_title"))
    render_result_bundle(
        docx_bytes=cast(bytes | None, result.get("docx_bytes")),
        markdown_text=str(result.get("markdown_text") or ""),
        original_filename=str(result.get("source_name") or ""),
        narration_text=cast(str | None, result.get("narration_text")),
        processing_operation=str(result.get("processing_operation", "edit")),
        audiobook_postprocess_enabled=bool(result.get("audiobook_postprocess_enabled", False)),
        success_message=t("result.success_document_processed"),
        quality_warning=cast(Mapping[str, object] | None, result.get("quality_warning")),
    )


def main() -> None:
    init_session_state()
    _drain_processing_events()
    _drain_preparation_events()
    if not is_app_start_logged():
        log_event(logging.INFO, "app_start", "Приложение инициализировано")
        mark_app_start_logged()

    try:
        app_config = _cached_load_app_config()
    except Exception as exc:
        user_message = present_error("config_load_failed", exc, "Ошибка загрузки конфигурации")
        st.error(t("app.config_load_error", message=user_message))
        return

    _apply_pending_recommended_widget_state()
    analysis_action: str | None = None

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

    st.title(t("app.title"))
    st.write(t("app.intro_description"))
    st.caption(t("app.pdf_caption"))
    uploaded_widget_file = st.file_uploader(t("app.upload_prompt"), type=["docx", "doc", "pdf"])

    if processing_in_progress:
        @st.fragment(run_every=2)
        def render_processing_panel() -> None:
            _drain_processing_events()
            render_live_status()
            render_run_log()
            render_image_validation_summary()
            render_partial_result()
            _finalize_app_frame()

            still_running = get_processing_outcome() == ProcessingOutcome.RUNNING.value
            action = _render_processing_controls(can_start=False, is_processing=still_running)
            if action == "stop":
                push_activity(t("app.activity_stopping"))
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
        st.error(t("app.file_too_large", limit=MAX_DOCX_ARCHIVE_SIZE_BYTES // (1024 * 1024)))
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
            uploaded_widget_payload = freeze_uploaded_file_lightweight(uploaded_widget_file)
        except Exception as exc:
            user_message = present_error(
                "document_read_failed",
                exc,
                "Ошибка чтения документа",
                filename=resolve_uploaded_filename(uploaded_widget_file),
            )
            st.error(t("app.document_read_error", message=user_message))
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
            preparation_error = str(st.session_state.get("last_error") or "")
            if preparation_error:
                st.error(preparation_error)
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
            st.warning(t("app.preparation_state_unavailable"))
            render_live_status()
            render_run_log()
            _finalize_app_frame()
            return

    if application_flow.has_resettable_state(current_result=current_result, session_state=session_state):
        if st.button(t("app.reset_results_button"), use_container_width=True):
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
                st.error(t("app.result_unavailable"))
                _finalize_app_frame()
                return
            completed_result = cast(dict[str, object], current_result)
            render_run_log()
            render_image_validation_summary()
            _render_completed_result_view(completed_result)
        elif idle_view_state == IdleViewState.RESTARTABLE:
            processing_outcome = get_processing_outcome()
            restart_filename = get_restart_source_filename()
            outcome_notice = _restartable_outcome_notice(processing_outcome, restart_filename)
            if outcome_notice is not None:
                notice_level, notice_message = outcome_notice
                _show_notice(level=notice_level, message=notice_message)
            else:
                st.info(t("app.restartable_generic_info"))
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
            st.error(t("app.document_read_error", message=user_message))
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

    outcome_notice = _restartable_outcome_notice(processing_outcome, uploaded_filename)
    if current_result is None and outcome_notice is not None:
        notice_level, notice_message = outcome_notice
        _show_notice(level=notice_level, message=notice_message)

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
    if not st.session_state.get("activity_feed") and not restartable_outcome:
        push_activity(t("app.activity_document_parsed", count=len(jobs)))

    if len(jobs) == 1:
        st.info(t("app.single_block_info"))

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
        if notice_message is not None:
            st.info(notice_message)

    last_error = str(st.session_state.get("last_error") or "")
    last_log_hint = str(st.session_state.get("last_log_hint") or "")
    if last_error:
        st.error(last_error)
        st.caption(last_log_hint)

    processing_snapshot = get_processing_session_snapshot()
    has_completed_result = bool(
        (st.session_state.get("latest_docx_bytes") or st.session_state.get("latest_narration_text"))
        and processing_snapshot.latest_source_token == uploaded_file_token
    )
    if not restartable_outcome:
        preparation_summary = get_latest_preparation_summary()
        manifest_notice = get_structure_manifest_notice_details()
        if (
            isinstance(preparation_summary, dict)
            and isinstance(manifest_notice, dict)
            and get_structure_manifest_notice_token() == uploaded_file_token
        ):
            manifest_path = str(manifest_notice.get("manifest_path", "") or "")
            if manifest_path:
                status_notes = [str(note).strip() for note in preparation_summary.get("status_notes", []) if str(note).strip()]
                manifest_note = t("status.prep_manifest_meta", path=manifest_path)
                if manifest_note not in status_notes:
                    status_notes.append(manifest_note)
                preparation_summary = {
                    **preparation_summary,
                    "manifest_path": manifest_path,
                    "status_notes": status_notes,
                }
        render_preparation_summary(preparation_summary)
        if st.button(t("app.export_manifest_button"), use_container_width=True, key="export_structure_manifest_button"):
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
            app_config=app_config,
        )
    render_run_log()
    render_image_validation_summary()
    render_partial_result()

    compare_panel.render_compare_all_apply_panel(
        latest_image_mode=get_latest_image_mode(),
        image_assets=cast(list[object], st.session_state.get("image_assets", [])),
    )

    if has_completed_result:
        _render_completed_result_view(
            {
                "docx_bytes": st.session_state.get("latest_docx_bytes"),
                "markdown_text": str(st.session_state.get("latest_markdown") or ""),
                "source_name": uploaded_filename,
                "narration_text": st.session_state.get("latest_narration_text"),
                "processing_operation": processing_snapshot.latest_processing_operation,
                "audiobook_postprocess_enabled": processing_snapshot.latest_audiobook_postprocess_enabled,
                "quality_warning": st.session_state.get("latest_quality_warning"),
            }
        )

    _finalize_app_frame()
    action = analysis_action if analysis_action is not None else _render_processing_controls(
        can_start=True,
        is_processing=False,
        emphasize_start=not has_completed_result,
    )
    document_context_prompt = _build_document_context_prompt(prepared_run_context=prepared_run_context)
    if action == "start":
        _start_background_processing(
            uploaded_filename=uploaded_filename,
            uploaded_token=uploaded_file_token,
            source_bytes=uploaded_file_bytes,
            prepared_source_key=str(getattr(prepared_run_context, "prepared_source_key", "") or ""),
            structure_fingerprint=str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
            jobs=cast(list[dict[str, str | int]], jobs),
            document_segments=list(getattr(prepared_run_context, "segments", []) or []),
            output_mode="legacy_full_document",
            source_paragraphs=paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            document_context_prompt=document_context_prompt,
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
        )
    elif action == "start_selected":
        requested_segment_selection = SegmentSelection(selected_segment_ids=tuple(get_selected_segment_ids()))
        selected_processing_state = _build_effective_selected_processing_state(
            prepared_run_context=prepared_run_context,
            selected_segment_ids=get_selected_segment_ids(),
            segment_selection=requested_segment_selection,
            segment_status_by_id=get_segment_status_by_id(),
        )
        selected_processing_payload = selected_processing_state["payload"]
        effective_segment_selection = SegmentSelection(
            selected_segment_ids=tuple(selected_processing_payload["selected_segment_ids"]),
            include_descendants=False,
        )
        _start_background_processing(
            uploaded_filename=uploaded_filename,
            uploaded_token=uploaded_file_token,
            source_bytes=uploaded_file_bytes,
            prepared_source_key=str(getattr(prepared_run_context, "prepared_source_key", "") or ""),
            structure_fingerprint=str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
            jobs=cast(list[dict[str, str | int]], selected_processing_payload["jobs"]),
            selected_segment_ids=selected_processing_payload["selected_segment_ids"],
            segment_selection=effective_segment_selection,
            document_segments=list(getattr(prepared_run_context, "segments", []) or []),
            output_mode="selected_only",
            include_front_matter=False,
            include_toc=False,
            source_paragraphs=selected_processing_payload["source_paragraphs"],
            image_assets=selected_processing_payload["image_assets"],
            image_mode=image_mode,
            app_config=app_config,
            document_context_prompt=_build_document_context_prompt(
                prepared_run_context=prepared_run_context,
                selected_segment_ids=selected_processing_payload["selected_segment_ids"],
                segment_selection=effective_segment_selection,
            ),
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
        )
        st.rerun()
    elif action == "start_selected_with_context":
        include_front_matter, include_toc = _structure_review_panel_get_selected_context_policy()
        requested_segment_selection = SegmentSelection(selected_segment_ids=tuple(get_selected_segment_ids()))
        selected_processing_state = _build_effective_selected_processing_state(
            prepared_run_context=prepared_run_context,
            selected_segment_ids=get_selected_segment_ids(),
            segment_selection=requested_segment_selection,
            segment_status_by_id=get_segment_status_by_id(),
            include_front_matter=include_front_matter,
            include_toc=include_toc,
        )
        selected_processing_payload = selected_processing_state["payload"]
        effective_segment_selection = SegmentSelection(
            selected_segment_ids=tuple(selected_processing_payload["selected_segment_ids"]),
            include_descendants=False,
        )
        _start_background_processing(
            uploaded_filename=uploaded_filename,
            uploaded_token=uploaded_file_token,
            source_bytes=uploaded_file_bytes,
            prepared_source_key=str(getattr(prepared_run_context, "prepared_source_key", "") or ""),
            structure_fingerprint=str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
            jobs=cast(list[dict[str, str | int]], selected_processing_payload["jobs"]),
            selected_segment_ids=selected_processing_payload["selected_segment_ids"],
            segment_selection=effective_segment_selection,
            document_segments=list(getattr(prepared_run_context, "segments", []) or []),
            output_mode="selected_with_context",
            include_front_matter=bool(selected_processing_payload["include_front_matter"]),
            include_toc=bool(selected_processing_payload["include_toc"]),
            source_paragraphs=paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            document_context_prompt=_build_document_context_prompt(
                prepared_run_context=prepared_run_context,
                selected_segment_ids=selected_processing_payload["selected_segment_ids"],
                segment_selection=effective_segment_selection,
            ),
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
        )
        st.rerun()
    elif action == "start_retry_failed":
        retry_failed_state = _build_retry_failed_processing_state(
            prepared_run_context=prepared_run_context,
            segment_status_by_id=get_segment_status_by_id(),
        )
        retry_failed_payload = retry_failed_state["payload"]
        retry_segment_selection = SegmentSelection(
            selected_segment_ids=tuple(retry_failed_payload["selected_segment_ids"]),
            include_descendants=False,
        )
        _start_background_processing(
            uploaded_filename=uploaded_filename,
            uploaded_token=uploaded_file_token,
            source_bytes=uploaded_file_bytes,
            prepared_source_key=str(getattr(prepared_run_context, "prepared_source_key", "") or ""),
            structure_fingerprint=str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
            jobs=cast(list[dict[str, str | int]], retry_failed_payload["jobs"]),
            selected_segment_ids=retry_failed_payload["selected_segment_ids"],
            segment_selection=retry_segment_selection,
            document_segments=list(getattr(prepared_run_context, "segments", []) or []),
            output_mode="selected_only",
            include_front_matter=False,
            include_toc=False,
            source_paragraphs=retry_failed_payload["source_paragraphs"],
            image_assets=retry_failed_payload["image_assets"],
            image_mode=image_mode,
            app_config=app_config,
            document_context_prompt=_build_document_context_prompt(
                prepared_run_context=prepared_run_context,
                selected_segment_ids=retry_failed_payload["selected_segment_ids"],
                segment_selection=retry_segment_selection,
            ),
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
            prepared_source_key=str(getattr(prepared_run_context, "prepared_source_key", "") or ""),
            structure_fingerprint=str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
            jobs=cast(list[dict[str, str | int]], jobs),
            document_segments=list(getattr(prepared_run_context, "segments", []) or []),
            output_mode="legacy_full_document",
            source_paragraphs=paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            document_context_prompt=document_context_prompt,
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
        )
        st.rerun()
    elif action == "start_final_book":
        _start_background_processing(
            uploaded_filename=uploaded_filename,
            uploaded_token=uploaded_file_token,
            source_bytes=uploaded_file_bytes,
            prepared_source_key=str(getattr(prepared_run_context, "prepared_source_key", "") or ""),
            structure_fingerprint=str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
            jobs=cast(list[dict[str, str | int]], jobs),
            document_segments=list(getattr(prepared_run_context, "segments", []) or []),
            output_mode="final_translated_book",
            source_paragraphs=paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            document_context_prompt=document_context_prompt,
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
        )
        st.rerun()
