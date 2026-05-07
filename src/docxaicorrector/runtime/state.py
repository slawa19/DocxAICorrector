from __future__ import annotations

import queue
import threading
import time
import logging
from typing import Any, TYPE_CHECKING
from uuid import uuid4
from dataclasses import dataclass

if TYPE_CHECKING:
    from docxaicorrector.ui.application_flow import PreparedRunContext
from datetime import datetime

import streamlit as st

from docxaicorrector.core.constants import APP_LOG_PATH
from docxaicorrector.generation.message_formatting import build_block_journal_entry, build_image_journal_entry
from docxaicorrector.processing.restart_store import clear_restart_source
from docxaicorrector.runtime.workflow_state import ProcessingOutcome


def build_default_image_processing_summary() -> dict[str, Any]:
    return {
        "total_images": 0,
        "processed_images": 0,
        "images_validated": 0,
        "validation_passed": 0,
        "fallbacks_applied": 0,
        "validation_errors": [],
    }


def reset_image_state() -> None:
    st.session_state.image_assets = []
    st.session_state.image_validation_failures = []
    st.session_state.image_processing_summary = build_default_image_processing_summary()


def _resolve_session_state(session_state=None):
    return st.session_state if session_state is None else session_state


@dataclass(frozen=True)
class PreparationStateSnapshot:
    input_marker: str
    failed_marker: str
    prepared_run_context: object | None


@dataclass(frozen=True)
class ProcessingSessionSnapshot:
    outcome: str
    worker: threading.Thread | None
    event_queue: queue.Queue[Any] | None
    stop_event: threading.Event | None
    stop_requested: bool
    latest_source_name: str
    latest_source_token: str
    latest_narration_text: str | None
    latest_processing_operation: str
    latest_audiobook_postprocess_enabled: bool
    selected_source_token: str
    latest_image_mode: str


def get_preparation_state() -> PreparationStateSnapshot:
    return PreparationStateSnapshot(
        input_marker=str(st.session_state.get("preparation_input_marker", "")),
        failed_marker=str(st.session_state.get("preparation_failed_marker", "")),
        prepared_run_context=st.session_state.get("prepared_run_context"),
    )


def get_processing_outcome(*, session_state=None) -> str:
    resolved_session_state = _resolve_session_state(session_state)
    return str(resolved_session_state.get("processing_outcome") or ProcessingOutcome.IDLE.value)


def get_processing_session_snapshot(*, session_state=None) -> ProcessingSessionSnapshot:
    resolved_session_state = _resolve_session_state(session_state)
    return ProcessingSessionSnapshot(
        outcome=get_processing_outcome(session_state=resolved_session_state),
        worker=resolved_session_state.get("processing_worker"),
        event_queue=resolved_session_state.get("processing_event_queue"),
        stop_event=resolved_session_state.get("processing_stop_event"),
        stop_requested=bool(resolved_session_state.get("processing_stop_requested", False)),
        latest_source_name=str(resolved_session_state.get("latest_source_name", "")),
        latest_source_token=str(resolved_session_state.get("latest_source_token", "")),
        latest_narration_text=resolved_session_state.get("latest_narration_text"),
        latest_processing_operation=str(resolved_session_state.get("latest_processing_operation", "edit") or "edit"),
        latest_audiobook_postprocess_enabled=bool(
            resolved_session_state.get("latest_audiobook_postprocess_enabled", False)
        ),
        selected_source_token=str(resolved_session_state.get("selected_source_token", "")),
        latest_image_mode=str(resolved_session_state.get("latest_image_mode", "no_change") or "no_change"),
    )


def get_processing_status() -> dict[str, Any]:
    status = st.session_state.get("processing_status")
    return status if isinstance(status, dict) else {}


def get_run_log() -> list[dict[str, Any]]:
    run_log = st.session_state.get("run_log")
    return list(run_log) if isinstance(run_log, list) else []


def get_activity_feed() -> list[dict[str, Any]]:
    activity_feed = st.session_state.get("activity_feed")
    return list(activity_feed) if isinstance(activity_feed, list) else []


def get_image_assets() -> list[Any]:
    image_assets = st.session_state.get("image_assets")
    return list(image_assets) if isinstance(image_assets, list) else []


def get_image_processing_summary() -> dict[str, Any]:
    summary = st.session_state.get("image_processing_summary")
    if isinstance(summary, dict):
        return summary
    legacy_summary = st.session_state.get("image_validation_summary")
    return legacy_summary if isinstance(legacy_summary, dict) else {}


def get_processed_block_markdowns() -> list[str]:
    blocks = st.session_state.get("processed_block_markdowns")
    return [str(block) for block in blocks] if isinstance(blocks, list) else []


def get_latest_docx_bytes():
    return st.session_state.get("latest_docx_bytes")


def get_latest_narration_text(*, session_state=None) -> str | None:
    value = _resolve_session_state(session_state).get("latest_narration_text")
    return value if isinstance(value, str) else None


def get_latest_source_name(*, session_state=None) -> str:
    return get_processing_session_snapshot(session_state=session_state).latest_source_name


def get_latest_source_token(*, session_state=None) -> str:
    return get_processing_session_snapshot(session_state=session_state).latest_source_token


def get_latest_processing_operation(*, session_state=None) -> str:
    return get_processing_session_snapshot(session_state=session_state).latest_processing_operation


def get_latest_audiobook_postprocess_enabled(*, session_state=None) -> bool:
    return get_processing_session_snapshot(session_state=session_state).latest_audiobook_postprocess_enabled


def get_selected_source_token(*, session_state=None) -> str:
    return get_processing_session_snapshot(session_state=session_state).selected_source_token


def get_latest_image_mode(*, session_state=None) -> str:
    return get_processing_session_snapshot(session_state=session_state).latest_image_mode


def get_processing_worker() -> threading.Thread | None:
    return get_processing_session_snapshot().worker


def get_processing_event_queue() -> queue.Queue[Any] | None:
    return get_processing_session_snapshot().event_queue


def get_processing_stop_event() -> threading.Event | None:
    return get_processing_session_snapshot().stop_event


def is_processing_stop_requested() -> bool:
    return get_processing_session_snapshot().stop_requested


def get_restart_source(*, session_state=None) -> dict[str, object]:
    restart_source = _resolve_session_state(session_state).get("restart_source")
    return restart_source if isinstance(restart_source, dict) else {}


def get_completed_source(*, session_state=None) -> dict[str, object]:
    completed_source = _resolve_session_state(session_state).get("completed_source")
    return completed_source if isinstance(completed_source, dict) else {}


def get_prepared_source_key(*, session_state=None) -> str:
    return str(_resolve_session_state(session_state).get("prepared_source_key", ""))


def get_latest_preparation_summary(*, session_state=None) -> dict[str, Any] | None:
    summary = _resolve_session_state(session_state).get("latest_preparation_summary")
    return summary if isinstance(summary, dict) else None


def get_preparation_worker() -> threading.Thread | None:
    worker = st.session_state.get("preparation_worker")
    return worker if isinstance(worker, threading.Thread) else None


def get_preparation_event_queue() -> queue.Queue[Any] | None:
    event_queue = st.session_state.get("preparation_event_queue")
    return event_queue if isinstance(event_queue, queue.Queue) else None


def is_app_start_logged() -> bool:
    return bool(st.session_state.get("app_start_logged", False))


def is_persisted_source_cleanup_done() -> bool:
    return bool(st.session_state.get("persisted_source_cleanup_done", False))


def has_persisted_source(*, session_state=None) -> bool:
    return bool(
        get_restart_source(session_state=session_state)
        or get_completed_source(session_state=session_state)
    )


def get_restart_source_filename(*, session_state=None) -> str:
    return str(get_restart_source(session_state=session_state).get("filename", ""))


def mark_app_start_logged(*, session_state=None) -> None:
    _resolve_session_state(session_state).app_start_logged = True


def mark_persisted_source_cleanup_done(*, session_state=None) -> None:
    _resolve_session_state(session_state).persisted_source_cleanup_done = True


def set_latest_preparation_summary(summary: dict[str, object] | None, *, session_state=None) -> None:
    _resolve_session_state(session_state).latest_preparation_summary = summary


def set_prepared_source_key(prepared_source_key: str, *, session_state=None) -> None:
    _resolve_session_state(session_state).prepared_source_key = prepared_source_key


def set_restart_source(restart_source: dict[str, object] | None, *, session_state=None) -> None:
    _resolve_session_state(session_state).restart_source = restart_source


def set_preparation_runtime(*, worker, event_queue, session_state=None) -> None:
    resolved_session_state = _resolve_session_state(session_state)
    resolved_session_state.preparation_worker = worker
    resolved_session_state.preparation_event_queue = event_queue


def clear_completed_source(*, completed_source: dict[str, object] | None = None, clear_restart_source_fn=clear_restart_source, session_state=None) -> None:
    resolved_session_state = _resolve_session_state(session_state)
    source_to_clear = completed_source if completed_source is not None else resolved_session_state.get("completed_source")
    if source_to_clear:
        clear_restart_source_fn(source_to_clear)
    resolved_session_state.completed_source = None


def should_start_preparation_for_marker(upload_marker: str) -> bool:
    snapshot = get_preparation_state()
    return (snapshot.input_marker != upload_marker or snapshot.prepared_run_context is None) and snapshot.failed_marker != upload_marker


def is_preparation_failed_for_marker(upload_marker: str) -> bool:
    snapshot = get_preparation_state()
    return snapshot.failed_marker == upload_marker and snapshot.prepared_run_context is None


def get_prepared_run_context_for_marker(upload_marker: str) -> PreparedRunContext | None:
    from docxaicorrector.ui.application_flow import PreparedRunContext as _PRC

    snapshot = get_preparation_state()
    if snapshot.input_marker == upload_marker and snapshot.failed_marker != upload_marker:
        ctx = snapshot.prepared_run_context
        if isinstance(ctx, _PRC):
            return ctx
    return None


def mark_preparation_started(upload_marker: str) -> None:
    st.session_state.preparation_input_marker = upload_marker
    st.session_state.preparation_failed_marker = ""
    st.session_state.prepared_run_context = None


def apply_preparation_complete(*, prepared_run_context, upload_marker: str, reset_run_state_fn) -> None:
    previous_token = str(st.session_state.get("selected_source_token", ""))
    uploaded_token = str(getattr(prepared_run_context, "uploaded_file_token", ""))
    if previous_token and uploaded_token and previous_token != uploaded_token:
        reset_run_state_fn(keep_restart_source=False)
    st.session_state.prepared_run_context = prepared_run_context
    st.session_state.preparation_input_marker = upload_marker
    st.session_state.preparation_failed_marker = ""
    st.session_state.selected_source_token = uploaded_token
    st.session_state.selected_segment_ids = [
        str(getattr(segment, "segment_id", "") or "")
        for segment in (getattr(prepared_run_context, "segments", None) or [])
        if str(getattr(segment, "segment_id", "") or "").strip()
    ]
    st.session_state.segment_status_by_id = {
        str(getattr(segment, "segment_id", "") or ""): "pending"
        for segment in (getattr(prepared_run_context, "segments", None) or [])
        if str(getattr(segment, "segment_id", "") or "").strip()
    }
    st.session_state.segment_progress_by_id = {
        str(getattr(segment, "segment_id", "") or ""): 0.0
        for segment in (getattr(prepared_run_context, "segments", None) or [])
        if str(getattr(segment, "segment_id", "") or "").strip()
    }
    st.session_state.active_segment_id = ""
    st.session_state.active_segment_title = ""
    st.session_state.structure_confirmed = False
    st.session_state.confirmed_structure_fingerprint = ""
    st.session_state.confirmed_at_settings_hash = ""
    st.session_state.segments_loaded_for_source_token = uploaded_token
    st.session_state.chapter_selector_search = ""
    st.session_state.chapter_selector_filter = "all"
    set_prepared_source_key(str(getattr(prepared_run_context, "prepared_source_key", "")))
    set_preparation_runtime(worker=None, event_queue=None)
    st.session_state.processing_outcome = ProcessingOutcome.IDLE.value


def apply_preparation_failure(*, upload_marker: str, error_message: str, error_details: dict[str, object]) -> None:
    st.session_state.prepared_run_context = None
    st.session_state.preparation_input_marker = upload_marker
    st.session_state.preparation_failed_marker = upload_marker
    set_preparation_runtime(worker=None, event_queue=None)
    st.session_state.last_background_error = error_details
    st.session_state.last_error = error_message
    st.session_state.processing_outcome = ProcessingOutcome.FAILED.value


def apply_processing_completion(
    *,
    outcome: str,
    push_activity,
    load_restart_source_bytes_fn,
    clear_restart_source_fn,
    store_completed_source_fn,
    should_cache_completed_source_fn,
    log_event_fn,
) -> None:
    restart_source = st.session_state.get("restart_source")
    previous_completed_source = st.session_state.get("completed_source")
    if outcome == ProcessingOutcome.SUCCEEDED.value and restart_source:
        source_bytes = load_restart_source_bytes_fn(restart_source)
        if source_bytes:
            if should_cache_completed_source_fn(source_bytes=source_bytes):
                try:
                    st.session_state.completed_source = store_completed_source_fn(
                        session_id=str(restart_source.get("session_id", st.session_state.get("restart_session_id", ""))),
                        source_name=str(restart_source.get("filename", "")),
                        source_token=str(restart_source.get("token", "")),
                        source_bytes=source_bytes,
                        previous_completed_source=previous_completed_source,
                    )
                except OSError as exc:
                    if previous_completed_source:
                        clear_restart_source_fn(previous_completed_source)
                    clear_completed_source(clear_restart_source_fn=clear_restart_source_fn)
                    log_event_fn(
                        logging.WARNING,
                        "completed_source_store_failed",
                        "Не удалось сохранить completed source во временное файловое хранилище.",
                        filename=str(restart_source.get("filename", "")),
                        source_token=str(restart_source.get("token", "")),
                        error_message=str(exc),
                    )
                    push_activity(
                        "Не удалось сохранить исходный DOCX для повторного запуска после завершения. Для нового запуска загрузите файл заново."
                    )
            else:
                if previous_completed_source:
                    clear_restart_source_fn(previous_completed_source)
                clear_completed_source(clear_restart_source_fn=clear_restart_source_fn)
                push_activity(
                    "Исходный файл слишком большой для повторного запуска из памяти. Для нового запуска загрузите DOCX заново."
                )
        clear_restart_source_fn(restart_source)
        set_restart_source(None)
    st.session_state.processing_outcome = outcome
    st.session_state.processing_worker = None
    st.session_state.processing_event_queue = None
    st.session_state.processing_stop_event = None
    st.session_state.processing_stop_requested = False


def apply_processing_start(
    *,
    uploaded_filename: str,
    uploaded_token: str,
    image_mode: str,
    processing_operation: str,
    audiobook_postprocess_enabled: bool,
    worker,
    event_queue,
    stop_event,
) -> None:
    st.session_state.latest_source_name = uploaded_filename
    st.session_state.latest_source_token = uploaded_token
    st.session_state.selected_source_token = uploaded_token
    st.session_state.latest_image_mode = image_mode
    st.session_state.latest_processing_operation = processing_operation
    st.session_state.latest_audiobook_postprocess_enabled = audiobook_postprocess_enabled
    st.session_state.processing_outcome = ProcessingOutcome.RUNNING.value
    st.session_state.processing_worker = worker
    st.session_state.processing_event_queue = event_queue
    st.session_state.processing_stop_event = stop_event
    st.session_state.processing_stop_requested = False


def request_processing_stop() -> None:
    stop_event = get_processing_stop_event()
    if stop_event is not None:
        stop_event.set()
    st.session_state.processing_stop_requested = True


def set_selected_source_token(uploaded_token: str, *, session_state=None) -> None:
    _resolve_session_state(session_state).selected_source_token = uploaded_token


def get_recommended_text_settings() -> object | None:
    return st.session_state.get("recommended_text_settings")


def get_text_transform_assessment() -> object | None:
    return st.session_state.get("text_transform_assessment")


def get_recommended_text_settings_applied_for_token() -> str:
    return str(st.session_state.get("recommended_text_settings_applied_for_token") or "")


def get_recommended_text_settings_applied_snapshot() -> object | None:
    return st.session_state.get("recommended_text_settings_applied_snapshot")


def get_recommended_text_settings_pending_widget_state() -> object | None:
    return st.session_state.get("recommended_text_settings_pending_widget_state")


def get_recommended_text_settings_notice_token() -> str:
    return str(st.session_state.get("recommended_text_settings_notice_token") or "")


def get_recommended_text_settings_notice_details() -> object | None:
    return st.session_state.get("recommended_text_settings_notice_details")


def get_manual_text_settings_override_for_token() -> object | None:
    return st.session_state.get("manual_text_settings_override_for_token")


def get_structure_manifest_notice_details() -> object | None:
    return st.session_state.get("structure_manifest_notice_details")


def get_structure_manifest_notice_token() -> str:
    return str(st.session_state.get("structure_manifest_notice_token") or "")


def get_selected_segment_ids() -> list[str]:
    selected_segment_ids = st.session_state.get("selected_segment_ids")
    if not isinstance(selected_segment_ids, list):
        return []
    return [str(segment_id) for segment_id in selected_segment_ids if str(segment_id).strip()]


def get_segment_status_by_id() -> dict[str, str]:
    raw_value = st.session_state.get("segment_status_by_id")
    if not isinstance(raw_value, dict):
        return {}
    return {
        str(segment_id): str(status)
        for segment_id, status in raw_value.items()
        if str(segment_id).strip() and str(status).strip()
    }


def get_segment_progress_by_id() -> dict[str, float]:
    raw_value = st.session_state.get("segment_progress_by_id")
    if not isinstance(raw_value, dict):
        return {}
    normalized: dict[str, float] = {}
    for segment_id, progress in raw_value.items():
        if not str(segment_id).strip():
            continue
        try:
            normalized[str(segment_id)] = max(0.0, min(float(progress), 1.0))
        except (TypeError, ValueError):
            continue
    return normalized


def get_active_segment_id() -> str:
    return str(st.session_state.get("active_segment_id") or "")


def get_active_segment_title() -> str:
    return str(st.session_state.get("active_segment_title") or "")


def get_structure_confirmed() -> bool:
    return bool(st.session_state.get("structure_confirmed", False))


def get_confirmed_structure_fingerprint() -> str:
    return str(st.session_state.get("confirmed_structure_fingerprint") or "")


def get_confirmed_structure_segment_ids() -> list[str]:
    return [str(segment_id) for segment_id in (st.session_state.get("confirmed_structure_segment_ids") or []) if str(segment_id).strip()]


def get_confirmed_at_settings_hash() -> str:
    return str(st.session_state.get("confirmed_at_settings_hash") or "")


def get_segments_loaded_for_source_token() -> str:
    return str(st.session_state.get("segments_loaded_for_source_token") or "")


def set_recommended_text_settings(recommendation: object | None) -> None:
    st.session_state.recommended_text_settings = recommendation


def set_text_transform_assessment(assessment: object | None) -> None:
    st.session_state.text_transform_assessment = assessment


def set_manual_text_settings_override_for_token(manual_override: object | None) -> None:
    st.session_state.manual_text_settings_override_for_token = manual_override


def set_structure_manifest_notice(*, file_token: str | None, details: dict[str, object] | None) -> None:
    st.session_state.structure_manifest_notice_token = file_token
    st.session_state.structure_manifest_notice_details = details


def set_selected_segment_ids(selected_segment_ids: list[str] | None) -> None:
    st.session_state.selected_segment_ids = list(selected_segment_ids or [])


def set_segment_runtime_state(
    *,
    segment_status_by_id: dict[str, str] | None = None,
    segment_progress_by_id: dict[str, float] | None = None,
    active_segment_id: str = "",
    active_segment_title: str = "",
) -> None:
    st.session_state.segment_status_by_id = {
        str(segment_id): str(status)
        for segment_id, status in (segment_status_by_id or {}).items()
        if str(segment_id).strip() and str(status).strip()
    }
    st.session_state.segment_progress_by_id = {
        str(segment_id): max(0.0, min(float(progress), 1.0))
        for segment_id, progress in (segment_progress_by_id or {}).items()
        if str(segment_id).strip()
    }
    st.session_state.active_segment_id = str(active_segment_id or "")
    st.session_state.active_segment_title = str(active_segment_title or "")


def set_structure_confirmation_state(
    *,
    structure_confirmed: bool,
    confirmed_structure_fingerprint: str = "",
    confirmed_segment_ids: Sequence[str] | None = None,
    confirmed_at_settings_hash: str = "",
    segments_loaded_for_source_token: str = "",
) -> None:
    st.session_state.structure_confirmed = bool(structure_confirmed)
    st.session_state.confirmed_structure_fingerprint = confirmed_structure_fingerprint
    st.session_state.confirmed_structure_segment_ids = [
        str(segment_id) for segment_id in (confirmed_segment_ids or []) if str(segment_id).strip()
    ]
    st.session_state.confirmed_at_settings_hash = confirmed_at_settings_hash
    st.session_state.segments_loaded_for_source_token = segments_loaded_for_source_token


def clear_structure_review_state() -> None:
    st.session_state.selected_segment_ids = []
    st.session_state.segment_status_by_id = {}
    st.session_state.segment_progress_by_id = {}
    st.session_state.active_segment_id = ""
    st.session_state.active_segment_title = ""
    st.session_state.structure_confirmed = False
    st.session_state.confirmed_structure_fingerprint = ""
    st.session_state.confirmed_structure_segment_ids = []
    st.session_state.confirmed_at_settings_hash = ""
    st.session_state.segments_loaded_for_source_token = ""
    st.session_state.chapter_selector_search = ""
    st.session_state.chapter_selector_filter = "all"


def clear_recommended_text_settings_notice_token() -> None:
    st.session_state.recommended_text_settings_notice_token = None


def set_recommended_text_settings_applied(*, file_token: str | None, snapshot: dict[str, str] | None) -> None:
    st.session_state.recommended_text_settings_applied_for_token = file_token
    st.session_state.recommended_text_settings_applied_snapshot = snapshot


def set_recommended_text_settings_pending_widget_state(pending_state: dict[str, object] | None) -> None:
    st.session_state.recommended_text_settings_pending_widget_state = pending_state


def set_recommended_text_settings_notice(*, file_token: str | None, details: dict[str, object] | None) -> None:
    st.session_state.recommended_text_settings_notice_token = file_token
    st.session_state.recommended_text_settings_notice_details = details


def consume_recommended_text_settings_pending_widget_state() -> dict[str, object] | None:
    pending_state = st.session_state.get("recommended_text_settings_pending_widget_state")
    if not isinstance(pending_state, dict):
        return None
    widget_state = pending_state.get("widget_state")
    if not isinstance(widget_state, dict):
        st.session_state.recommended_text_settings_pending_widget_state = None
        return None
    st.session_state.recommended_text_settings_pending_widget_state = None
    return pending_state


def apply_recommended_widget_state(widget_state: dict[str, object]) -> None:
    for widget_key, widget_value in widget_state.items():
        if isinstance(widget_key, str):
            st.session_state[widget_key] = widget_value


def _current_unix_timestamp() -> float:
    return time.time()


def _current_clock_label() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _default_processing_status() -> dict[str, object]:
    return {
        "is_running": False,
        "phase": "processing",
        "stage": "Ожидание запуска",
        "detail": "Загрузите файл и запустите обработку.",
        "current_block": 0,
        "block_count": 0,
        "target_chars": 0,
        "context_chars": 0,
        "file_size_bytes": 0,
        "paragraph_count": 0,
        "image_count": 0,
        "source_chars": 0,
        "source_format": "docx",
        "conversion_backend": None,
        "raw_paragraph_count": 0,
        "logical_paragraph_count": 0,
        "merged_group_count": 0,
        "merged_raw_paragraph_count": 0,
        "high_confidence_merge_count": 0,
        "medium_accepted_merge_count": 0,
        "medium_rejected_candidate_count": 0,
        "cached": False,
        "started_at": None,
        "last_update_at": None,
        "progress": 0.0,
        "terminal_kind": None,
    }


def init_session_state() -> None:
    st.session_state.setdefault("app_start_logged", False)
    st.session_state.setdefault("run_log", [])
    st.session_state.setdefault("activity_feed", [])
    st.session_state.setdefault("latest_markdown", "")
    st.session_state.setdefault("processed_block_markdowns", [])
    st.session_state.setdefault("latest_docx_bytes", None)
    st.session_state.setdefault("latest_narration_text", None)
    st.session_state.setdefault("latest_result_notice", None)
    st.session_state.setdefault("latest_source_name", "")
    st.session_state.setdefault("latest_source_token", "")
    st.session_state.setdefault("latest_processing_operation", "edit")
    st.session_state.setdefault("latest_audiobook_postprocess_enabled", False)
    st.session_state.setdefault("selected_source_token", "")
    st.session_state.setdefault("last_error", "")
    st.session_state.setdefault("last_background_error", None)
    st.session_state.setdefault("last_log_hint", f"Подробный лог приложения: {APP_LOG_PATH}")
    st.session_state.setdefault("processing_status", _default_processing_status())
    st.session_state.setdefault("image_assets", [])
    st.session_state.setdefault("image_validation_failures", [])
    st.session_state.setdefault("image_processing_summary", build_default_image_processing_summary())
    st.session_state.setdefault("processing_stop_requested", False)
    st.session_state.setdefault("processing_worker", None)
    st.session_state.setdefault("processing_event_queue", None)
    st.session_state.setdefault("processing_stop_event", None)
    st.session_state.setdefault("preparation_worker", None)
    st.session_state.setdefault("preparation_event_queue", None)
    st.session_state.setdefault("prepared_run_context", None)
    st.session_state.setdefault("latest_preparation_summary", None)
    st.session_state.setdefault("preparation_input_marker", "")
    st.session_state.setdefault("preparation_failed_marker", "")
    st.session_state.setdefault("processing_outcome", ProcessingOutcome.IDLE.value)
    st.session_state.setdefault("prepared_source_key", "")
    st.session_state.setdefault("preparation_cache", {})
    st.session_state.setdefault("restart_source", None)
    st.session_state.setdefault("completed_source", None)
    st.session_state.setdefault("persisted_source_cleanup_done", False)
    st.session_state.setdefault("restart_session_id", uuid4().hex)
    st.session_state.setdefault("latest_image_mode", "no_change")
    st.session_state.setdefault("text_transform_assessment", None)
    st.session_state.setdefault("recommended_text_settings", None)
    st.session_state.setdefault("recommended_text_settings_applied_for_token", None)
    st.session_state.setdefault("recommended_text_settings_applied_snapshot", None)
    st.session_state.setdefault("recommended_text_settings_pending_widget_state", None)
    st.session_state.setdefault("recommended_text_settings_notice_token", None)
    st.session_state.setdefault("recommended_text_settings_notice_details", None)
    st.session_state.setdefault("manual_text_settings_override_for_token", None)
    st.session_state.setdefault("structure_manifest_notice_token", None)
    st.session_state.setdefault("structure_manifest_notice_details", None)
    st.session_state.setdefault("selected_segment_ids", [])
    st.session_state.setdefault("segment_status_by_id", {})
    st.session_state.setdefault("segment_progress_by_id", {})
    st.session_state.setdefault("active_segment_id", "")
    st.session_state.setdefault("active_segment_title", "")
    st.session_state.setdefault("structure_confirmed", False)
    st.session_state.setdefault("confirmed_structure_fingerprint", "")
    st.session_state.setdefault("confirmed_structure_segment_ids", [])
    st.session_state.setdefault("confirmed_at_settings_hash", "")
    st.session_state.setdefault("segments_loaded_for_source_token", "")
    st.session_state.setdefault("chapter_selector_search", "")
    st.session_state.setdefault("chapter_selector_filter", "all")


def reset_run_state(*, keep_restart_source: bool = True, preserve_preparation: bool = False) -> None:
    restart_source = st.session_state.get("restart_source")
    completed_source = st.session_state.get("completed_source")
    prepared_run_context = st.session_state.get("prepared_run_context") if preserve_preparation else None
    latest_preparation_summary = st.session_state.get("latest_preparation_summary") if preserve_preparation else None
    preparation_input_marker = str(st.session_state.get("preparation_input_marker", "")) if preserve_preparation else ""
    preparation_failed_marker = str(st.session_state.get("preparation_failed_marker", "")) if preserve_preparation else ""
    prepared_source_key = str(st.session_state.get("prepared_source_key", "")) if preserve_preparation else ""
    preparation_cache = dict(st.session_state.get("preparation_cache", {})) if preserve_preparation else {}
    recommended_text_settings = st.session_state.get("recommended_text_settings") if preserve_preparation else None
    recommended_text_settings_applied_for_token = (
        st.session_state.get("recommended_text_settings_applied_for_token") if preserve_preparation else None
    )
    recommended_text_settings_applied_snapshot = (
        st.session_state.get("recommended_text_settings_applied_snapshot") if preserve_preparation else None
    )
    recommended_text_settings_pending_widget_state = (
        st.session_state.get("recommended_text_settings_pending_widget_state") if preserve_preparation else None
    )
    recommended_text_settings_notice_token = (
        st.session_state.get("recommended_text_settings_notice_token") if preserve_preparation else None
    )
    recommended_text_settings_notice_details = (
        st.session_state.get("recommended_text_settings_notice_details") if preserve_preparation else None
    )
    manual_text_settings_override_for_token = (
        st.session_state.get("manual_text_settings_override_for_token") if preserve_preparation else None
    )
    structure_manifest_notice_token = (
        st.session_state.get("structure_manifest_notice_token") if preserve_preparation else None
    )
    structure_manifest_notice_details = (
        st.session_state.get("structure_manifest_notice_details") if preserve_preparation else None
    )
    selected_segment_ids = list(st.session_state.get("selected_segment_ids", [])) if preserve_preparation else []
    chapter_selector_search = str(st.session_state.get("chapter_selector_search", "")) if preserve_preparation else ""
    chapter_selector_filter = str(st.session_state.get("chapter_selector_filter", "all") or "all") if preserve_preparation else "all"
    segment_status_by_id = dict(st.session_state.get("segment_status_by_id", {})) if preserve_preparation else {}
    segment_progress_by_id = dict(st.session_state.get("segment_progress_by_id", {})) if preserve_preparation else {}
    active_segment_id = str(st.session_state.get("active_segment_id", "")) if preserve_preparation else ""
    active_segment_title = str(st.session_state.get("active_segment_title", "")) if preserve_preparation else ""
    structure_confirmed = bool(st.session_state.get("structure_confirmed", False)) if preserve_preparation else False
    confirmed_structure_fingerprint = (
        str(st.session_state.get("confirmed_structure_fingerprint", "")) if preserve_preparation else ""
    )
    confirmed_structure_segment_ids = list(st.session_state.get("confirmed_structure_segment_ids", [])) if preserve_preparation else []
    confirmed_at_settings_hash = (
        str(st.session_state.get("confirmed_at_settings_hash", "")) if preserve_preparation else ""
    )
    segments_loaded_for_source_token = (
        str(st.session_state.get("segments_loaded_for_source_token", "")) if preserve_preparation else ""
    )
    preserved_file_token = str(getattr(prepared_run_context, "uploaded_file_token", "")) if prepared_run_context is not None else ""
    if preserved_file_token:
        if not isinstance(recommended_text_settings, dict) or str(recommended_text_settings.get("file_token", "")) != preserved_file_token:
            recommended_text_settings = None
        if str(recommended_text_settings_applied_for_token or "") != preserved_file_token:
            recommended_text_settings_applied_for_token = None
        if (
            not isinstance(recommended_text_settings_applied_snapshot, dict)
            or str(recommended_text_settings_applied_snapshot.get("file_token", "")) != preserved_file_token
        ):
            recommended_text_settings_applied_snapshot = None
        if (
            not isinstance(recommended_text_settings_pending_widget_state, dict)
            or str(recommended_text_settings_pending_widget_state.get("file_token", "")) != preserved_file_token
        ):
            recommended_text_settings_pending_widget_state = None
        if str(recommended_text_settings_notice_token or "") != preserved_file_token:
            recommended_text_settings_notice_token = None
        if (
            not isinstance(recommended_text_settings_notice_details, dict)
            or str(recommended_text_settings_notice_details.get("file_token", "")) != preserved_file_token
        ):
            recommended_text_settings_notice_details = None
        if (
            not isinstance(manual_text_settings_override_for_token, dict)
            or str(manual_text_settings_override_for_token.get("file_token", "")) != preserved_file_token
        ):
            manual_text_settings_override_for_token = None
        if str(structure_manifest_notice_token or "") != preserved_file_token:
            structure_manifest_notice_token = None
        if (
            not isinstance(structure_manifest_notice_details, dict)
            or str(structure_manifest_notice_details.get("file_token", "")) != preserved_file_token
        ):
            structure_manifest_notice_details = None
        if segments_loaded_for_source_token != preserved_file_token:
            selected_segment_ids = []
            chapter_selector_search = ""
            chapter_selector_filter = "all"
            segment_status_by_id = {}
            segment_progress_by_id = {}
            active_segment_id = ""
            active_segment_title = ""
            structure_confirmed = False
            confirmed_structure_fingerprint = ""
            confirmed_structure_segment_ids = []
            confirmed_at_settings_hash = ""
            segments_loaded_for_source_token = ""
    else:
        recommended_text_settings = None
        recommended_text_settings_applied_for_token = None
        recommended_text_settings_applied_snapshot = None
        recommended_text_settings_pending_widget_state = None
        recommended_text_settings_notice_token = None
        recommended_text_settings_notice_details = None
        manual_text_settings_override_for_token = None
        structure_manifest_notice_token = None
        structure_manifest_notice_details = None
        selected_segment_ids = []
        chapter_selector_search = ""
        chapter_selector_filter = "all"
        segment_status_by_id = {}
        segment_progress_by_id = {}
        active_segment_id = ""
        active_segment_title = ""
        structure_confirmed = False
        confirmed_structure_fingerprint = ""
        confirmed_structure_segment_ids = []
        confirmed_at_settings_hash = ""
        segments_loaded_for_source_token = ""
    st.session_state.run_log = []
    st.session_state.activity_feed = []
    st.session_state.latest_markdown = ""
    st.session_state.processed_block_markdowns = []
    for _key in list(st.session_state.keys()):
        if isinstance(_key, str) and _key.startswith("mdpreview_"):
            del st.session_state[_key]
    st.session_state.latest_docx_bytes = None
    st.session_state.latest_narration_text = None
    st.session_state.latest_result_notice = None
    st.session_state.latest_source_name = ""
    st.session_state.latest_source_token = ""
    st.session_state.latest_processing_operation = "edit"
    st.session_state.latest_audiobook_postprocess_enabled = False
    st.session_state.last_error = ""
    st.session_state.last_background_error = None
    reset_image_state()
    st.session_state.processing_status = _default_processing_status()
    st.session_state.processing_stop_requested = False
    st.session_state.processing_worker = None
    st.session_state.processing_event_queue = None
    st.session_state.processing_stop_event = None
    st.session_state.preparation_worker = None
    st.session_state.preparation_event_queue = None
    st.session_state.prepared_run_context = prepared_run_context
    st.session_state.latest_preparation_summary = latest_preparation_summary
    st.session_state.preparation_input_marker = preparation_input_marker
    st.session_state.preparation_failed_marker = preparation_failed_marker
    st.session_state.processing_outcome = ProcessingOutcome.IDLE.value
    st.session_state.prepared_source_key = prepared_source_key
    st.session_state.preparation_cache = preparation_cache
    st.session_state.latest_image_mode = "no_change"
    st.session_state.recommended_text_settings = recommended_text_settings
    st.session_state.recommended_text_settings_applied_for_token = recommended_text_settings_applied_for_token
    st.session_state.recommended_text_settings_applied_snapshot = recommended_text_settings_applied_snapshot
    st.session_state.recommended_text_settings_pending_widget_state = recommended_text_settings_pending_widget_state
    st.session_state.recommended_text_settings_notice_token = recommended_text_settings_notice_token
    st.session_state.recommended_text_settings_notice_details = recommended_text_settings_notice_details
    st.session_state.manual_text_settings_override_for_token = manual_text_settings_override_for_token
    st.session_state.structure_manifest_notice_token = structure_manifest_notice_token
    st.session_state.structure_manifest_notice_details = structure_manifest_notice_details
    st.session_state.selected_segment_ids = selected_segment_ids
    st.session_state.chapter_selector_search = chapter_selector_search
    st.session_state.chapter_selector_filter = chapter_selector_filter
    st.session_state.segment_status_by_id = segment_status_by_id
    st.session_state.segment_progress_by_id = segment_progress_by_id
    st.session_state.active_segment_id = active_segment_id
    st.session_state.active_segment_title = active_segment_title
    st.session_state.structure_confirmed = structure_confirmed
    st.session_state.confirmed_structure_fingerprint = confirmed_structure_fingerprint
    st.session_state.confirmed_structure_segment_ids = confirmed_structure_segment_ids
    st.session_state.confirmed_at_settings_hash = confirmed_at_settings_hash
    st.session_state.segments_loaded_for_source_token = segments_loaded_for_source_token
    clear_restart_source(completed_source)
    st.session_state.completed_source = None
    if not keep_restart_source:
        clear_restart_source(restart_source)
        st.session_state.restart_source = None


def push_activity(message: str) -> None:
    timestamp = _current_clock_label()
    st.session_state.activity_feed.append({"time": timestamp, "message": message})
    st.session_state.activity_feed = st.session_state.activity_feed[-20:]


def _append_run_log_entry(entry: dict[str, object]) -> None:
    st.session_state.run_log.append(entry)
    st.session_state.run_log = st.session_state.run_log[-30:]


def set_processing_status(
    *,
    stage: str,
    detail: str,
    current_block: int = 0,
    block_count: int = 0,
    target_chars: int = 0,
    context_chars: int = 0,
    file_size_bytes: int | None = None,
    paragraph_count: int | None = None,
    image_count: int | None = None,
    source_chars: int | None = None,
    source_format: str | None = None,
    conversion_backend: str | None = None,
    raw_paragraph_count: int | None = None,
    logical_paragraph_count: int | None = None,
    merged_group_count: int | None = None,
    merged_raw_paragraph_count: int | None = None,
    high_confidence_merge_count: int | None = None,
    medium_accepted_merge_count: int | None = None,
    medium_rejected_candidate_count: int | None = None,
    cached: bool | None = None,
    segment_status_by_id: dict[str, str] | None = None,
    segment_progress_by_id: dict[str, float] | None = None,
    active_segment_id: str | None = None,
    active_segment_title: str | None = None,
    progress: float = 0.0,
    is_running: bool | None = None,
    phase: str | None = None,
    terminal_kind: str | None = None,
) -> None:
    status = dict(st.session_state.processing_status)
    if is_running is not None:
        status["is_running"] = is_running
    if phase is not None:
        status["phase"] = phase
    status.update(
        {
            "stage": stage,
            "detail": detail,
            "current_block": current_block,
            "block_count": block_count,
            "target_chars": target_chars,
            "context_chars": context_chars,
            "last_update_at": _current_unix_timestamp(),
            "progress": max(0.0, min(progress, 1.0)),
            "terminal_kind": terminal_kind if terminal_kind in {None, "completed", "stopped", "error"} else None,
        }
    )
    if file_size_bytes is not None:
        status["file_size_bytes"] = file_size_bytes
    if paragraph_count is not None:
        status["paragraph_count"] = paragraph_count
    if image_count is not None:
        status["image_count"] = image_count
    if source_chars is not None:
        status["source_chars"] = source_chars
    if source_format is not None:
        status["source_format"] = source_format
    if conversion_backend is not None or "conversion_backend" not in status:
        status["conversion_backend"] = conversion_backend
    if raw_paragraph_count is not None:
        status["raw_paragraph_count"] = raw_paragraph_count
    if logical_paragraph_count is not None:
        status["logical_paragraph_count"] = logical_paragraph_count
    if merged_group_count is not None:
        status["merged_group_count"] = merged_group_count
    if merged_raw_paragraph_count is not None:
        status["merged_raw_paragraph_count"] = merged_raw_paragraph_count
    if high_confidence_merge_count is not None:
        status["high_confidence_merge_count"] = high_confidence_merge_count
    if medium_accepted_merge_count is not None:
        status["medium_accepted_merge_count"] = medium_accepted_merge_count
    if medium_rejected_candidate_count is not None:
        status["medium_rejected_candidate_count"] = medium_rejected_candidate_count
    if cached is not None:
        status["cached"] = cached
    if segment_status_by_id is not None:
        status["segment_status_by_id"] = {
            str(segment_id): str(segment_status)
            for segment_id, segment_status in segment_status_by_id.items()
            if str(segment_id).strip() and str(segment_status).strip()
        }
        st.session_state.segment_status_by_id = dict(status["segment_status_by_id"])
    if segment_progress_by_id is not None:
        normalized_progress = {
            str(segment_id): max(0.0, min(float(segment_progress), 1.0))
            for segment_id, segment_progress in segment_progress_by_id.items()
            if str(segment_id).strip()
        }
        status["segment_progress_by_id"] = normalized_progress
        st.session_state.segment_progress_by_id = dict(normalized_progress)
    if active_segment_id is not None:
        status["active_segment_id"] = str(active_segment_id or "")
        st.session_state.active_segment_id = status["active_segment_id"]
    if active_segment_title is not None:
        status["active_segment_title"] = str(active_segment_title or "")
        st.session_state.active_segment_title = status["active_segment_title"]
    if status["is_running"] and not status.get("started_at"):
        status["started_at"] = _current_unix_timestamp()
    st.session_state.processing_status = status


def _resolve_terminal_segment_runtime_state(
    *,
    terminal_kind: str | None,
    segment_status_by_id: dict[str, str],
    segment_progress_by_id: dict[str, float],
    active_segment_id: str,
) -> tuple[dict[str, str], dict[str, float]]:
    normalized_status_by_id = {
        str(segment_id): str(segment_status or "pending").strip().lower() or "pending"
        for segment_id, segment_status in segment_status_by_id.items()
        if str(segment_id).strip()
    }
    normalized_progress_by_id = {
        str(segment_id): max(0.0, min(float(segment_progress), 1.0))
        for segment_id, segment_progress in segment_progress_by_id.items()
        if str(segment_id).strip()
    }
    if terminal_kind == "stopped":
        for segment_id, segment_status in tuple(normalized_status_by_id.items()):
            if segment_status in {"queued", "processing"}:
                normalized_status_by_id[segment_id] = "pending"
                normalized_progress_by_id[segment_id] = 0.0
    elif terminal_kind == "error" and active_segment_id:
        current_status = normalized_status_by_id.get(active_segment_id, "pending")
        if current_status in {"pending", "queued", "processing"}:
            normalized_status_by_id[active_segment_id] = "failed"
            normalized_progress_by_id.setdefault(active_segment_id, 0.0)
    return normalized_status_by_id, normalized_progress_by_id


def finalize_processing_status(stage: str, detail: str, progress: float, terminal_kind: str | None = None) -> None:
    status = dict(st.session_state.processing_status)
    status.update(
        {
            "is_running": False,
            "stage": stage,
            "detail": detail,
            "last_update_at": _current_unix_timestamp(),
            "progress": max(0.0, min(progress, 1.0)),
            "terminal_kind": terminal_kind if terminal_kind in {None, "completed", "stopped", "error"} else None,
        }
    )
    if terminal_kind in {"stopped", "error"}:
        raw_segment_status_by_id = status.get("segment_status_by_id")
        raw_segment_progress_by_id = status.get("segment_progress_by_id")
        active_segment_id = str(status.get("active_segment_id") or st.session_state.get("active_segment_id") or "")
        segment_status_by_id = (
            {
                str(segment_id): str(segment_status)
                for segment_id, segment_status in raw_segment_status_by_id.items()
                if str(segment_id).strip() and str(segment_status).strip()
            }
            if isinstance(raw_segment_status_by_id, dict)
            else get_segment_status_by_id()
        )
        segment_progress_by_id = (
            {
                str(segment_id): max(0.0, min(float(segment_progress), 1.0))
                for segment_id, segment_progress in raw_segment_progress_by_id.items()
                if str(segment_id).strip()
            }
            if isinstance(raw_segment_progress_by_id, dict)
            else get_segment_progress_by_id()
        )
        segment_status_by_id, segment_progress_by_id = _resolve_terminal_segment_runtime_state(
            terminal_kind=terminal_kind,
            segment_status_by_id=segment_status_by_id,
            segment_progress_by_id=segment_progress_by_id,
            active_segment_id=active_segment_id,
        )
        status["segment_status_by_id"] = segment_status_by_id
        status["segment_progress_by_id"] = segment_progress_by_id
        st.session_state.segment_status_by_id = dict(segment_status_by_id)
        st.session_state.segment_progress_by_id = dict(segment_progress_by_id)
    if terminal_kind in {"completed", "stopped", "error"}:
        status["active_segment_id"] = ""
        status["active_segment_title"] = ""
        st.session_state.active_segment_id = ""
        st.session_state.active_segment_title = ""
    st.session_state.processing_status = status


def append_image_log(
    *,
    image_id: str,
    status: str,
    decision: str,
    confidence: float,
    missing_labels: list[str] | None = None,
    suspicious_reasons: list[str] | None = None,
    final_variant: str | None = None,
    final_reason: str | None = None,
) -> None:
    summary = dict(st.session_state.image_processing_summary)
    summary["total_images"] = int(summary.get("total_images", 0)) + 1
    summary["processed_images"] = int(summary.get("processed_images", 0)) + 1

    if status == "validated":
        summary["images_validated"] = int(summary.get("images_validated", 0)) + 1
        if decision in {"accept", "accept_soft"}:
            summary["validation_passed"] = int(summary.get("validation_passed", 0)) + 1
    if decision.startswith("fallback_"):
        summary["fallbacks_applied"] = int(summary.get("fallbacks_applied", 0)) + 1

    if status not in {"validated", "skipped", "compared"}:
        errors = list(summary.get("validation_errors", []))
        reason = "unknown"
        if suspicious_reasons:
            reason = suspicious_reasons[0]
        elif missing_labels:
            reason = f"missing_labels:{', '.join(missing_labels)}"
        errors.append(f"{image_id}: {reason}")
        summary["validation_errors"] = errors[-10:]
        failures = list(st.session_state.image_validation_failures)
        failures.append(f"{image_id}: {reason}")
        st.session_state.image_validation_failures = failures[-10:]

    st.session_state.image_processing_summary = summary
    _append_run_log_entry(
        build_image_journal_entry(
            image_id=image_id,
            status=status,
            decision=decision,
            confidence=confidence,
            missing_labels=missing_labels,
            suspicious_reasons=suspicious_reasons,
            final_variant=final_variant,
            final_reason=final_reason,
        )
    )


def append_log(
    status: str,
    block_index: int,
    block_count: int,
    target_chars: int,
    context_chars: int,
    details: str,
) -> None:
    _append_run_log_entry(
        build_block_journal_entry(
            status=status,
            block_index=block_index,
            block_count=block_count,
            target_chars=target_chars,
            context_chars=context_chars,
            details=details,
        )
    )
