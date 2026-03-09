import time
from datetime import datetime

import streamlit as st

from constants import APP_LOG_PATH


def _default_processing_status() -> dict[str, object]:
    return {
        "is_running": False,
        "stage": "Ожидание запуска",
        "detail": "Загрузите файл и запустите обработку.",
        "current_block": 0,
        "block_count": 0,
        "target_chars": 0,
        "context_chars": 0,
        "started_at": None,
        "last_update_at": None,
        "progress": 0.0,
    }


def _default_image_processing_summary() -> dict[str, object]:
    return {
        "total_images": 0,
        "processed_images": 0,
        "images_validated": 0,
        "validation_passed": 0,
        "fallbacks_applied": 0,
        "validation_errors": [],
    }


def init_session_state() -> None:
    st.session_state.setdefault("app_start_logged", False)
    st.session_state.setdefault("run_log", [])
    st.session_state.setdefault("activity_feed", [])
    st.session_state.setdefault("latest_markdown", "")
    st.session_state.setdefault("processed_block_markdowns", [])
    st.session_state.setdefault("markdown_preview_render_nonce", 0)
    st.session_state.setdefault("latest_docx_bytes", None)
    st.session_state.setdefault("latest_source_name", "")
    st.session_state.setdefault("latest_source_token", "")
    st.session_state.setdefault("selected_source_token", "")
    st.session_state.setdefault("last_error", "")
    st.session_state.setdefault("last_log_hint", f"Подробный лог приложения: {APP_LOG_PATH}")
    st.session_state.setdefault("processing_status", _default_processing_status())
    st.session_state.setdefault("markdown_preview_block_index", 1)
    st.session_state.setdefault("image_assets", [])
    st.session_state.setdefault("image_validation_failures", [])
    st.session_state.setdefault("image_processing_summary", _default_image_processing_summary())
    st.session_state.setdefault("previous_result", None)
    st.session_state.setdefault("processing_stop_requested", False)
    st.session_state.setdefault("processing_worker", None)
    st.session_state.setdefault("processing_event_queue", None)
    st.session_state.setdefault("processing_stop_event", None)
    st.session_state.setdefault("processing_outcome", "idle")
    st.session_state.setdefault("prepared_source_key", "")


def reset_run_state(*, keep_previous_result: bool = True) -> None:
    st.session_state.run_log = []
    st.session_state.activity_feed = []
    st.session_state.latest_markdown = ""
    st.session_state.processed_block_markdowns = []
    st.session_state.markdown_preview_render_nonce = 0
    st.session_state.latest_docx_bytes = None
    st.session_state.latest_source_name = ""
    st.session_state.latest_source_token = ""
    st.session_state.last_error = ""
    st.session_state.markdown_preview_block_index = 1
    st.session_state.image_assets = []
    st.session_state.image_validation_failures = []
    st.session_state.image_processing_summary = _default_image_processing_summary()
    st.session_state.processing_status = _default_processing_status()
    st.session_state.processing_stop_requested = False
    st.session_state.processing_worker = None
    st.session_state.processing_event_queue = None
    st.session_state.processing_stop_event = None
    st.session_state.processing_outcome = "idle"
    st.session_state.prepared_source_key = ""
    if not keep_previous_result:
        st.session_state.previous_result = None


def push_activity(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.activity_feed.append({"time": timestamp, "message": message})
    st.session_state.activity_feed = st.session_state.activity_feed[-8:]


def set_processing_status(
    *,
    stage: str,
    detail: str,
    current_block: int = 0,
    block_count: int = 0,
    target_chars: int = 0,
    context_chars: int = 0,
    progress: float = 0.0,
    is_running: bool | None = None,
) -> None:
    status = dict(st.session_state.processing_status)
    if is_running is not None:
        status["is_running"] = is_running
    status.update(
        {
            "stage": stage,
            "detail": detail,
            "current_block": current_block,
            "block_count": block_count,
            "target_chars": target_chars,
            "context_chars": context_chars,
            "last_update_at": time.time(),
            "progress": max(0.0, min(progress, 1.0)),
        }
    )
    if status["is_running"] and not status.get("started_at"):
        status["started_at"] = time.time()
    st.session_state.processing_status = status


def finalize_processing_status(stage: str, detail: str, progress: float) -> None:
    status = dict(st.session_state.processing_status)
    status.update(
        {
            "is_running": False,
            "stage": stage,
            "detail": detail,
            "last_update_at": time.time(),
            "progress": max(0.0, min(progress, 1.0)),
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
) -> None:
    summary = dict(st.session_state.image_processing_summary)
    summary["total_images"] = int(summary.get("total_images", 0)) + 1
    summary["processed_images"] = int(summary.get("processed_images", 0)) + 1

    if status == "validated":
        summary["images_validated"] = int(summary.get("images_validated", 0)) + 1
        if decision in {"accept", "accept_soft"}:
            summary["validation_passed"] = int(summary.get("validation_passed", 0)) + 1
        elif decision.startswith("fallback_"):
            summary["fallbacks_applied"] = int(summary.get("fallbacks_applied", 0)) + 1
    else:
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
    push_activity(f"[IMG] {image_id}: {status} | conf: {confidence:.2f} | {decision}")


def append_log(
    status: str,
    block_index: int,
    block_count: int,
    target_chars: int,
    context_chars: int,
    details: str,
) -> None:
    st.session_state.run_log.append(
        {
            "status": status,
            "block_index": block_index,
            "block_count": block_count,
            "target_chars": target_chars,
            "context_chars": context_chars,
            "details": details,
        }
    )
    st.session_state.run_log = st.session_state.run_log[-30:]
