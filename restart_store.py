from pathlib import Path

from constants import RUN_DIR


def _sanitize_suffix(source_name: str) -> str:
    suffix = Path(source_name).suffix.lower()
    return suffix if suffix else ".docx"


def _build_restart_source_path(session_id: str, source_token: str, source_name: str) -> Path:
    safe_session_id = session_id.replace(":", "_")
    safe_token = source_token.replace(":", "_")
    return RUN_DIR / f"restart_{safe_session_id}_{safe_token}{_sanitize_suffix(source_name)}"


def store_restart_source(*, session_id: str, source_name: str, source_token: str, source_bytes: bytes, previous_restart_source: dict[str, object] | None = None) -> dict[str, object]:
    clear_restart_source(previous_restart_source)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    storage_path = _build_restart_source_path(session_id, source_token, source_name)
    storage_path.write_bytes(source_bytes)
    return {
        "session_id": session_id,
        "filename": source_name,
        "token": source_token,
        "storage_path": str(storage_path),
        "size": len(source_bytes),
    }


def load_restart_source_bytes(restart_source: dict[str, object] | None) -> bytes | None:
    if not restart_source:
        return None
    storage_path = restart_source.get("storage_path")
    if not isinstance(storage_path, str) or not storage_path:
        return None
    restart_path = Path(storage_path)
    if not restart_path.exists() or not restart_path.is_file():
        return None
    source_bytes = restart_path.read_bytes()
    if not source_bytes:
        return None
    return source_bytes


def clear_restart_source(restart_source: dict[str, object] | None) -> None:
    if not restart_source:
        return
    storage_path = restart_source.get("storage_path")
    if not isinstance(storage_path, str) or not storage_path:
        return
    restart_path = Path(storage_path)
    try:
        if restart_path.exists() and restart_path.is_file():
            restart_path.unlink()
    except OSError:
        return