import time
from datetime import datetime

import streamlit as st

from constants import APP_LOG_PATH


def init_session_state() -> None:
    st.session_state.setdefault("run_log", [])
    st.session_state.setdefault("activity_feed", [])
    st.session_state.setdefault("latest_markdown", "")
    st.session_state.setdefault("processed_block_markdowns", [])
    st.session_state.setdefault("latest_docx_bytes", None)
    st.session_state.setdefault("latest_source_name", "")
    st.session_state.setdefault("last_error", "")
    st.session_state.setdefault("last_log_hint", f"Подробный лог приложения: {APP_LOG_PATH}")
    st.session_state.setdefault(
        "processing_status",
        {
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
        },
    )
    st.session_state.setdefault("markdown_preview_block_index", 1)


def reset_run_state() -> None:
    st.session_state.run_log = []
    st.session_state.activity_feed = []
    st.session_state.latest_markdown = ""
    st.session_state.processed_block_markdowns = []
    st.session_state.latest_docx_bytes = None
    st.session_state.latest_source_name = ""
    st.session_state.last_error = ""
    st.session_state.markdown_preview_block_index = 1
    st.session_state.processing_status = {
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
