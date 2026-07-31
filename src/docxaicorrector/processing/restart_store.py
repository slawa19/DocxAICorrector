import logging
import hashlib
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from docxaicorrector.core.constants import RUN_DIR
from docxaicorrector.core.logger import log_event


PERSISTED_SOURCE_FORMATS = frozenset({"docx", "doc", "pdf"})

#: Rejection reasons from :func:`load_persisted_source_bytes_with_reason` that describe a
#: PERMANENTLY unusable record: re-reading it can never produce a different verdict, so a
#: caller may safely drop the session record and its file. ``unreadable_payload`` is
#: deliberately excluded — a momentarily locked or unavailable file is transient, and
#: destroying the payload on a transient error is worse than an extra retry.
PERMANENT_PERSISTED_SOURCE_REJECTIONS = frozenset({"invalid_metadata", "unconfined_path", "integrity_mismatch"})


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
    source_format: str = "docx",
    conversion_backend: str | None = None,
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
        "payload_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_format": str(source_format or "docx").strip().lower(),
        "conversion_backend": conversion_backend,
        "storage_kind": prefix,
    }


def _build_restart_source_path(session_id: str, source_token: str, source_name: str) -> Path:
    return _build_persisted_source_path("restart", session_id, source_token, source_name)


def store_restart_source(*, session_id: str, source_name: str, source_token: str, source_bytes: bytes, source_format: str = "docx", conversion_backend: str | None = None, previous_restart_source: dict[str, Any] | None = None) -> dict[str, Any]:
    return _store_persisted_source(
        prefix="restart",
        session_id=session_id,
        source_name=source_name,
        source_token=source_token,
        source_bytes=source_bytes,
        source_format=source_format,
        conversion_backend=conversion_backend,
        previous_source=previous_restart_source,
    )


def store_completed_source(*, session_id: str, source_name: str, source_token: str, source_bytes: bytes, source_format: str = "docx", conversion_backend: str | None = None, previous_completed_source: dict[str, Any] | None = None) -> dict[str, Any]:
    return _store_persisted_source(
        prefix="completed",
        session_id=session_id,
        source_name=source_name,
        source_token=source_token,
        source_bytes=source_bytes,
        source_format=source_format,
        conversion_backend=conversion_backend,
        previous_source=previous_completed_source,
    )


def has_valid_persisted_source_metadata(persisted_source: Mapping[str, Any] | None) -> bool:
    """The STRUCTURAL half of the "is this persisted record usable" rule: everything
    decidable from the record alone, without reading the payload bytes.

    Single source of truth for both consumers — the loader
    (:func:`load_persisted_source_bytes_with_reason`, which adds the byte-level size and
    digest checks on top) and the UI restartable gate
    (``ui.application_flow.has_restartable_source``, which adds a filename and an
    existence check). The two used to re-implement this independently and drifted: the
    gate omitted the ``conversion_backend`` requirement, so a pdf/doc record without a
    backend was offered for restore and then always failed to restore.

    Cheap by construction: no filesystem access, so the gate stays a predicate.
    """
    if not isinstance(persisted_source, Mapping) or not persisted_source:
        return False
    storage_path = persisted_source.get("storage_path")
    source_token = persisted_source.get("token")
    payload_size = persisted_source.get("size")
    payload_sha256 = persisted_source.get("payload_sha256")
    source_format = str(persisted_source.get("source_format", "")).strip().lower()
    conversion_backend = persisted_source.get("conversion_backend")
    return (
        isinstance(storage_path, str)
        and bool(storage_path)
        and isinstance(source_token, str)
        and bool(source_token)
        and isinstance(payload_size, int)
        and payload_size > 0
        and isinstance(payload_sha256, str)
        and bool(re.fullmatch(r"[0-9a-f]{64}", payload_sha256))
        and source_format in PERSISTED_SOURCE_FORMATS
        and (source_format == "docx" or (isinstance(conversion_backend, str) and bool(conversion_backend.strip())))
    )


def load_persisted_source_bytes_with_reason(
    restart_source: Mapping[str, Any] | None,
) -> tuple[bytes | None, str | None]:
    """Load the persisted payload, returning ``(bytes, None)`` on success and
    ``(None, reason)`` on rejection.

    The reason is the same string already logged as ``persisted_source_validation_failed``;
    callers compare it against :data:`PERMANENT_PERSISTED_SOURCE_REJECTIONS` to decide
    whether the record is worth keeping. ``(None, None)`` means there was no record at all.
    """
    if not restart_source:
        return None, None
    if not has_valid_persisted_source_metadata(restart_source):
        _log_persisted_source_rejection(restart_source, reason="invalid_metadata")
        return None, "invalid_metadata"
    payload_size = restart_source["size"]
    payload_sha256 = restart_source["payload_sha256"]
    source_path = Path(str(restart_source["storage_path"]))
    if not _is_confined_persisted_source(source_path):
        _log_persisted_source_rejection(restart_source, reason="unconfined_path")
        return None, "unconfined_path"
    try:
        source_bytes = source_path.read_bytes()
    except OSError:
        _log_persisted_source_rejection(restart_source, reason="unreadable_payload")
        return None, "unreadable_payload"
    if (
        not source_bytes
        or len(source_bytes) != payload_size
        or hashlib.sha256(source_bytes).hexdigest() != payload_sha256
    ):
        _log_persisted_source_rejection(restart_source, reason="integrity_mismatch")
        return None, "integrity_mismatch"
    return source_bytes, None


def load_restart_source_bytes(restart_source: dict[str, Any] | None) -> bytes | None:
    source_bytes, _rejection_reason = load_persisted_source_bytes_with_reason(restart_source)
    return source_bytes


def _log_persisted_source_rejection(restart_source: Mapping[str, Any], *, reason: str) -> None:
    log_event(
        logging.WARNING,
        "persisted_source_validation_failed",
        "Persisted source is unavailable because its identity or payload integrity could not be verified.",
        reason=reason,
        filename=str(restart_source.get("filename", "")),
        source_token=str(restart_source.get("token", "")),
        storage_kind=str(restart_source.get("storage_kind", "")),
    )


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
