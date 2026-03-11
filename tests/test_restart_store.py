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


def test_clear_restart_source_ignores_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    restart_store.clear_restart_source({"storage_path": str(tmp_path / "missing.docx")})