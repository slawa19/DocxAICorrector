import os
from pathlib import Path

import restart_store


def test_store_and_load_restart_source_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    metadata = restart_store.store_restart_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.docx:3:abc",
        source_bytes=b"docx-bytes",
    )

    assert metadata["session_id"] == "session-a"
    assert metadata["filename"] == "report.docx"
    assert metadata["token"] == "report.docx:3:abc"
    assert metadata["size"] == 10
    assert Path(metadata["storage_path"]).exists()
    assert restart_store.load_restart_source_bytes(metadata) == b"docx-bytes"


def test_store_restart_source_replaces_previous_file(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    first = restart_store.store_restart_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.docx:3:first",
        source_bytes=b"one",
    )
    first_path = Path(first["storage_path"])

    second = restart_store.store_restart_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.docx:3:second",
        source_bytes=b"two",
        previous_restart_source=first,
    )

    assert not first_path.exists()
    assert Path(second["storage_path"]).exists()
    assert restart_store.load_restart_source_bytes(second) == b"two"


def test_store_restart_source_overwrites_same_path_without_deleting_new_file(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    first = restart_store.store_restart_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.docx:3:same",
        source_bytes=b"one",
    )

    second = restart_store.store_restart_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.docx:3:same",
        source_bytes=b"two",
        previous_restart_source=first,
    )

    assert first["storage_path"] == second["storage_path"]
    assert Path(second["storage_path"]).exists()
    assert restart_store.load_restart_source_bytes(second) == b"two"


def test_store_restart_source_uses_session_scoped_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    first = restart_store.store_restart_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.docx:3:shared",
        source_bytes=b"one",
    )
    second = restart_store.store_restart_source(
        session_id="session-b",
        source_name="report.docx",
        source_token="report.docx:3:shared",
        source_bytes=b"two",
    )

    assert first["storage_path"] != second["storage_path"]
    assert Path(first["storage_path"]).exists()
    assert Path(second["storage_path"]).exists()


def test_store_restart_source_sanitizes_forbidden_filename_characters(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    metadata = restart_store.store_restart_source(
        session_id='session<>:"/\\|?*',
        source_name="report.docx",
        source_token='report<>:"/\\|?*.docx:3:abc',
        source_bytes=b"docx-bytes",
    )

    storage_path = Path(metadata["storage_path"])

    assert storage_path.exists()
    assert storage_path.parent == tmp_path
    assert not any(char in storage_path.name for char in '<>:"/\\|?*')


def test_clear_restart_source_ignores_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    restart_store.clear_restart_source({"storage_path": str(tmp_path / "missing.docx")})


def test_store_completed_source_uses_distinct_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    metadata = restart_store.store_completed_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.docx:3:abc",
        source_bytes=b"docx-bytes",
    )

    assert Path(metadata["storage_path"]).name.startswith("completed_")
    assert restart_store.load_restart_source_bytes(metadata) == b"docx-bytes"


def test_cleanup_stale_persisted_sources_removes_old_restart_and_completed_files(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)
    stale_restart = tmp_path / "restart_session_token.docx"
    stale_completed = tmp_path / "completed_session_token.docx"
    fresh_restart = tmp_path / "restart_recent_token.docx"
    stale_restart.write_bytes(b"x")
    stale_completed.write_bytes(b"x")
    fresh_restart.write_bytes(b"x")

    os.utime(stale_restart, (10.0, 10.0))
    os.utime(stale_completed, (10.0, 10.0))
    os.utime(fresh_restart, (95.0, 95.0))

    removed_count = restart_store.cleanup_stale_persisted_sources(max_age_seconds=20, now_timestamp=100.0)

    assert removed_count == 2
    assert not stale_restart.exists()
    assert not stale_completed.exists()
    assert fresh_restart.exists()