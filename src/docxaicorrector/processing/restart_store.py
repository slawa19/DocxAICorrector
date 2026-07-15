import logging
import re
import time
from pathlib import Path
from typing import Any

from docxaicorrector.core.constants import RUN_DIR
from docxaicorrector.core.logger import log_event


def _is_confined_persisted_source(path: Path) -> bool:
    """A persisted-source path is safe to delete only when it resolves INSIDE
    RUN_DIR and its name matches the ``restart_``/``completed_`` convention.

    Guards clear_restart_source and cleanup_stale_persisted_sources against
    deleting an arbitrary file whose path leaked in via corrupted or externally
    restored session metadata (path traversal / arbitrary file deletion)."""
    if not (path.name.startswith("restart_") or path.name.startswith("completed_")):
        return False
    try:
        resolved = path.resolve()
        run_dir_resolved = RUN_DIR.resolve()
    except OSError:
        return False
    return resolved.is_relative_to(run_dir_resolved)


def _sanitize_suffix(source_name: str) -> str:
    suffix = Path(source_name).suffix.lower()
    return suffix if suffix else ".docx"


def _sanitize_for_filename(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)


def _build_persisted_source_path(prefix: str, session_id: str, source_token: str, source_name: str) -> Path:
    safe_session_id = _sanitize_for_filename(session_id)
    safe_token = _sanitize_for_filename(source_token)
    return RUN_DIR / f"{prefix}_{safe_session_id}_{safe_token}{_sanitize_suffix(source_name)}"


def _store_persisted_source(
    *,
    prefix: str,
    session_id: str,
    source_name: str,
    source_token: str,
    source_bytes: bytes,
    previous_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    storage_path = _build_persisted_source_path(prefix, session_id, source_token, source_name)
    previous_storage_path = previous_source.get("storage_path") if isinstance(previous_source, dict) else None
    storage_path.write_bytes(source_bytes)
    if previous_storage_path != str(storage_path):
        clear_restart_source(previous_source)
    return {
        "session_id": session_id,
        "filename": source_name,
        "token": source_token,
        "storage_path": str(storage_path),
        "size": len(source_bytes),
        "storage_kind": prefix,
    }


def _build_restart_source_path(session_id: str, source_token: str, source_name: str) -> Path:
    return _build_persisted_source_path("restart", session_id, source_token, source_name)


def store_restart_source(*, session_id: str, source_name: str, source_token: str, source_bytes: bytes, previous_restart_source: dict[str, Any] | None = None) -> dict[str, Any]:
    return _store_persisted_source(
        prefix="restart",
        session_id=session_id,
        source_name=source_name,
        source_token=source_token,
        source_bytes=source_bytes,
        previous_source=previous_restart_source,
    )


def store_completed_source(*, session_id: str, source_name: str, source_token: str, source_bytes: bytes, previous_completed_source: dict[str, Any] | None = None) -> dict[str, Any]:
    return _store_persisted_source(
        prefix="completed",
        session_id=session_id,
        source_name=source_name,
        source_token=source_token,
        source_bytes=source_bytes,
        previous_source=previous_completed_source,
    )


def load_restart_source_bytes(restart_source: dict[str, Any] | None) -> bytes | None:
    if not restart_source:
        return None
    storage_path = restart_source.get("storage_path")
    if not isinstance(storage_path, str) or not storage_path:
        return None
    try:
        source_bytes = Path(storage_path).read_bytes()
    except OSError:
        return None
    if not source_bytes:
        return None
    return source_bytes


def clear_restart_source(restart_source: dict[str, Any] | None) -> None:
    if not restart_source:
        return
    storage_path = restart_source.get("storage_path")
    if not isinstance(storage_path, str) or not storage_path:
        return
    restart_path = Path(storage_path)
    if not _is_confined_persisted_source(restart_path):
        log_event(
            logging.WARNING,
            "restart_source_delete_refused",
            "Refused to delete a persisted source outside RUN_DIR or with an unexpected name.",
            storage_path=str(restart_path),
        )
        return
    try:
        if restart_path.exists() and restart_path.is_file():
            restart_path.unlink()
    except OSError:
        return


def cleanup_stale_persisted_sources(*, max_age_seconds: int, now_timestamp: float | None = None) -> int:
    if max_age_seconds <= 0 or not RUN_DIR.exists() or not RUN_DIR.is_dir():
        return 0
    removed_count = 0
    current_timestamp = time.time() if now_timestamp is None else now_timestamp
    for candidate in RUN_DIR.glob("*_*"):
        if not candidate.is_file():
            continue
        if not _is_confined_persisted_source(candidate):
            continue
        try:
            candidate_age = current_timestamp - candidate.stat().st_mtime
            if candidate_age <= max_age_seconds:
                continue
            candidate.unlink()
            removed_count += 1
        except OSError:
            continue
    return removed_count
