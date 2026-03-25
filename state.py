import time
from uuid import uuid4
from datetime import datetime

import streamlit as st

from constants import APP_LOG_PATH
from message_formatting import build_block_journal_entry, build_image_journal_entry
from restart_store import clear_restart_source
from workflow_state import ProcessingOutcome


def build_default_image_processing_summary() -> dict[str, object]:
    return {
        "total_images": 0,
        "processed_images": 0,
        "images_validated": 0,
        "validation_passed": 0,
        "fallbacks_applied": 0,
        "validation_errors": [],
    }


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


def reset_run_state(*, keep_restart_source: bool = True, preserve_preparation: bool = False) -> None:
    restart_source = st.session_state.get("restart_source")
    completed_source = st.session_state.get("completed_source")
    prepared_run_context = st.session_state.get("prepared_run_context") if preserve_preparation else None
    latest_preparation_summary = st.session_state.get("latest_preparation_summary") if preserve_preparation else None
    preparation_input_marker = str(st.session_state.get("preparation_input_marker", "")) if preserve_preparation else ""
    preparation_failed_marker = str(st.session_state.get("preparation_failed_marker", "")) if preserve_preparation else ""
    prepared_source_key = str(st.session_state.get("prepared_source_key", "")) if preserve_preparation else ""
    preparation_cache = dict(st.session_state.get("preparation_cache", {})) if preserve_preparation else {}
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
    st.session_state.image_assets = []
    st.session_state.image_validation_failures = []
    st.session_state.image_processing_summary = build_default_image_processing_summary()
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
