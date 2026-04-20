from __future__ import annotations

import time
import logging
from typing import Any, TYPE_CHECKING
from uuid import uuid4
from dataclasses import dataclass

if TYPE_CHECKING:
    from application_flow import PreparedRunContext
from datetime import datetime

import streamlit as st

from constants import APP_LOG_PATH
from message_formatting import build_block_journal_entry, build_image_journal_entry
from restart_store import clear_restart_source
from workflow_state import ProcessingOutcome


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


@dataclass(frozen=True)
class PreparationStateSnapshot:
    input_marker: str
    failed_marker: str
    prepared_run_context: object | None


@dataclass(frozen=True)
class ProcessingSessionSnapshot:
    outcome: str
    worker: object | None
    event_queue: object | None
    stop_event: object | None
    stop_requested: bool
    latest_source_name: str
    latest_source_token: str
    selected_source_token: str
    latest_image_mode: str


def get_preparation_state() -> PreparationStateSnapshot:
    return PreparationStateSnapshot(
        input_marker=str(st.session_state.get("preparation_input_marker", "")),
        failed_marker=str(st.session_state.get("preparation_failed_marker", "")),
        prepared_run_context=st.session_state.get("prepared_run_context"),
    )


def get_processing_outcome() -> str:
    return str(st.session_state.get("processing_outcome") or ProcessingOutcome.IDLE.value)


def get_processing_session_snapshot() -> ProcessingSessionSnapshot:
    return ProcessingSessionSnapshot(
        outcome=get_processing_outcome(),
        worker=st.session_state.get("processing_worker"),
        event_queue=st.session_state.get("processing_event_queue"),
        stop_event=st.session_state.get("processing_stop_event"),
        stop_requested=bool(st.session_state.get("processing_stop_requested", False)),
        latest_source_name=str(st.session_state.get("latest_source_name", "")),
        latest_source_token=str(st.session_state.get("latest_source_token", "")),
        selected_source_token=str(st.session_state.get("selected_source_token", "")),
        latest_image_mode=str(st.session_state.get("latest_image_mode", "no_change") or "no_change"),
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


def get_latest_source_name() -> str:
    return get_processing_session_snapshot().latest_source_name


def get_latest_source_token() -> str:
    return get_processing_session_snapshot().latest_source_token


def get_selected_source_token() -> str:
    return get_processing_session_snapshot().selected_source_token


def get_latest_image_mode() -> str:
    return get_processing_session_snapshot().latest_image_mode


def get_processing_worker():
    return get_processing_session_snapshot().worker


def get_processing_event_queue():
    return get_processing_session_snapshot().event_queue


def get_processing_stop_event():
    return get_processing_session_snapshot().stop_event


def is_processing_stop_requested() -> bool:
    return get_processing_session_snapshot().stop_requested


def get_restart_source() -> dict[str, object]:
    restart_source = st.session_state.get("restart_source")
    return restart_source if isinstance(restart_source, dict) else {}


def get_completed_source() -> dict[str, object]:
    completed_source = st.session_state.get("completed_source")
    return completed_source if isinstance(completed_source, dict) else {}


def has_persisted_source() -> bool:
    return bool(get_restart_source() or get_completed_source())


def get_restart_source_filename() -> str:
    return str(get_restart_source().get("filename", ""))


def should_start_preparation_for_marker(upload_marker: str) -> bool:
    snapshot = get_preparation_state()
    return (snapshot.input_marker != upload_marker or snapshot.prepared_run_context is None) and snapshot.failed_marker != upload_marker


def is_preparation_failed_for_marker(upload_marker: str) -> bool:
    snapshot = get_preparation_state()
    return snapshot.failed_marker == upload_marker and snapshot.prepared_run_context is None


def get_prepared_run_context_for_marker(upload_marker: str) -> PreparedRunContext | None:
    from application_flow import PreparedRunContext as _PRC
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
    st.session_state.prepared_source_key = str(getattr(prepared_run_context, "prepared_source_key", ""))
    st.session_state.preparation_worker = None
    st.session_state.preparation_event_queue = None
    st.session_state.processing_outcome = ProcessingOutcome.IDLE.value


def apply_preparation_failure(*, upload_marker: str, error_message: str, error_details: dict[str, object]) -> None:
    st.session_state.prepared_run_context = None
    st.session_state.preparation_input_marker = upload_marker
    st.session_state.preparation_failed_marker = upload_marker
    st.session_state.preparation_worker = None
    st.session_state.preparation_event_queue = None
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
                    st.session_state.completed_source = None
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
                st.session_state.completed_source = None
                push_activity(
                    "Исходный файл слишком большой для повторного запуска из памяти. Для нового запуска загрузите DOCX заново."
                )
        clear_restart_source_fn(restart_source)
        st.session_state.restart_source = None
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
    worker,
    event_queue,
    stop_event,
) -> None:
    st.session_state.latest_source_name = uploaded_filename
    st.session_state.latest_source_token = uploaded_token
    st.session_state.selected_source_token = uploaded_token
    st.session_state.latest_image_mode = image_mode
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
    st.session_state.setdefault("latest_result_notice", None)
    st.session_state.setdefault("latest_source_name", "")
    st.session_state.setdefault("latest_source_token", "")
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
    st.session_state.setdefault("recommended_text_settings", None)
    st.session_state.setdefault("recommended_text_settings_applied_for_token", None)
    st.session_state.setdefault("recommended_text_settings_applied_snapshot", None)
    st.session_state.setdefault("recommended_text_settings_pending_widget_state", None)
    st.session_state.setdefault("recommended_text_settings_notice_token", None)
    st.session_state.setdefault("recommended_text_settings_notice_details", None)
    st.session_state.setdefault("manual_text_settings_override_for_token", None)


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
    else:
        recommended_text_settings = None
        recommended_text_settings_applied_for_token = None
        recommended_text_settings_applied_snapshot = None
        recommended_text_settings_pending_widget_state = None
        recommended_text_settings_notice_token = None
        recommended_text_settings_notice_details = None
        manual_text_settings_override_for_token = None
    st.session_state.run_log = []
    st.session_state.activity_feed = []
    st.session_state.latest_markdown = ""
    st.session_state.processed_block_markdowns = []
    for _key in list(st.session_state.keys()):
        if isinstance(_key, str) and _key.startswith("mdpreview_"):
            del st.session_state[_key]
    st.session_state.latest_docx_bytes = None
    st.session_state.latest_result_notice = None
    st.session_state.latest_source_name = ""
    st.session_state.latest_source_token = ""
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
    raw_paragraph_count: int | None = None,
    logical_paragraph_count: int | None = None,
    merged_group_count: int | None = None,
    merged_raw_paragraph_count: int | None = None,
    high_confidence_merge_count: int | None = None,
    medium_accepted_merge_count: int | None = None,
    medium_rejected_candidate_count: int | None = None,
    cached: bool | None = None,
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
    if status["is_running"] and not status.get("started_at"):
        status["started_at"] = _current_unix_timestamp()
    st.session_state.processing_status = status


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
