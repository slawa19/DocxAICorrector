import os
import hashlib
from pathlib import Path

import docxaicorrector.processing.restart_store as restart_store
from docxaicorrector.runtime.artifacts import write_ui_result_artifacts


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
    assert metadata["payload_sha256"] == hashlib.sha256(b"docx-bytes").hexdigest()
    assert metadata["source_format"] == "docx"
    assert metadata["conversion_backend"] is None
    assert Path(metadata["storage_path"]).exists()
    assert restart_store.load_restart_source_bytes(metadata) == b"docx-bytes"


def test_store_and_load_normalized_pdf_payload_preserves_source_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    metadata = restart_store.store_restart_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.pdf:11:original",
        source_bytes=b"normalized-docx",
        source_format="pdf",
        conversion_backend="libreoffice-writer-pdf-import",
    )

    assert metadata["token"] == "report.pdf:11:original"
    assert metadata["source_format"] == "pdf"
    assert metadata["conversion_backend"] == "libreoffice-writer-pdf-import"
    assert restart_store.load_restart_source_bytes(metadata) == b"normalized-docx"


def test_load_restart_source_rejects_changed_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)
    metadata = restart_store.store_restart_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.pdf:11:original",
        source_bytes=b"normalized-docx",
        source_format="pdf",
        conversion_backend="libreoffice-writer-pdf-import",
    )
    Path(metadata["storage_path"]).write_bytes(b"normalized-DOCX")

    assert restart_store.load_restart_source_bytes(metadata) is None


def test_load_restart_source_rejects_size_digest_and_required_metadata_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)
    metadata = restart_store.store_restart_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.pdf:11:original",
        source_bytes=b"normalized-docx",
        source_format="pdf",
        conversion_backend="libreoffice-writer-pdf-import",
    )

    for changed in (
        {**metadata, "size": metadata["size"] + 1},
        {**metadata, "payload_sha256": "0" * 64},
        {key: value for key, value in metadata.items() if key != "payload_sha256"},
        {key: value for key, value in metadata.items() if key != "token"},
        {**metadata, "conversion_backend": None},
    ):
        assert restart_store.load_restart_source_bytes(changed) is None


def test_load_restart_source_rejects_unconfined_path(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(restart_store, "RUN_DIR", run_dir)
    outside = tmp_path / "restart_outside.docx"
    outside.write_bytes(b"normalized-docx")

    record = {
        "filename": "report.docx",
        "token": "report.pdf:11:original",
        "storage_path": str(outside),
        "size": len(b"normalized-docx"),
        "payload_sha256": hashlib.sha256(b"normalized-docx").hexdigest(),
        "source_format": "pdf",
        "conversion_backend": "libreoffice-writer-pdf-import",
    }

    assert restart_store.load_restart_source_bytes(record) is None


def _pdf_record(storage_path, source_bytes: bytes = b"normalized-docx") -> dict:
    return {
        "filename": "report.docx",
        "token": "report.pdf:11:original",
        "storage_path": str(storage_path),
        "size": len(source_bytes),
        "payload_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_format": "pdf",
        "conversion_backend": "libreoffice-writer-pdf-import",
    }


def test_structural_metadata_gate_rejects_non_docx_record_without_conversion_backend(tmp_path):
    # Round-11 Fix 1 (the DRIFT case): the UI restartable gate used to omit exactly this
    # clause, so a pdf/doc record with no backend was offered and could never restore.
    for missing_backend in (None, "", "   ", 17):
        record = {**_pdf_record(tmp_path / "restart_x.docx"), "conversion_backend": missing_backend}
        assert restart_store.has_valid_persisted_source_metadata(record) is False


def test_structural_metadata_gate_accepts_valid_docx_and_pdf_records(tmp_path):
    # ANTI-VACUUM: the shared helper must keep accepting the records it always accepted.
    pdf_record = _pdf_record(tmp_path / "restart_x.docx")
    docx_record = {**pdf_record, "source_format": "docx", "conversion_backend": None}

    assert restart_store.has_valid_persisted_source_metadata(pdf_record) is True
    assert restart_store.has_valid_persisted_source_metadata(docx_record) is True


def test_structural_metadata_gate_and_loader_agree_on_the_same_inputs(tmp_path, monkeypatch):
    # The two copies of this rule have already drifted once; pin that they now share one.
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)
    storage_path = tmp_path / "restart_session_token.docx"
    storage_path.write_bytes(b"normalized-docx")
    valid = _pdf_record(storage_path)

    variants = [
        valid,
        {**valid, "storage_path": ""},
        {key: value for key, value in valid.items() if key != "storage_path"},
        {**valid, "token": ""},
        {key: value for key, value in valid.items() if key != "token"},
        {**valid, "size": 0},
        {**valid, "size": "15"},
        {**valid, "payload_sha256": "0" * 63},
        {**valid, "payload_sha256": "0" * 64},
        {**valid, "source_format": "txt"},
        {**valid, "conversion_backend": None},
        {**valid, "source_format": "docx", "conversion_backend": None},
    ]

    for record in variants:
        _bytes, reason = restart_store.load_persisted_source_bytes_with_reason(record)
        assert restart_store.has_valid_persisted_source_metadata(record) is (reason != "invalid_metadata"), record


def test_load_persisted_source_bytes_with_reason_reports_every_rejection_reason(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(restart_store, "RUN_DIR", run_dir)
    good_path = run_dir / "restart_session_token.docx"
    good_path.write_bytes(b"normalized-docx")
    outside_path = tmp_path / "restart_outside.docx"
    outside_path.write_bytes(b"normalized-docx")
    unreadable_path = run_dir / "restart_session_dir.docx"
    unreadable_path.mkdir()
    tampered_path = run_dir / "restart_session_tampered.docx"
    tampered_path.write_bytes(b"tampered-payload")

    assert restart_store.load_persisted_source_bytes_with_reason(None) == (None, None)
    assert restart_store.load_persisted_source_bytes_with_reason(_pdf_record(good_path)) == (b"normalized-docx", None)
    assert restart_store.load_persisted_source_bytes_with_reason(
        {**_pdf_record(good_path), "conversion_backend": None}
    ) == (None, "invalid_metadata")
    assert restart_store.load_persisted_source_bytes_with_reason(_pdf_record(outside_path)) == (None, "unconfined_path")
    assert restart_store.load_persisted_source_bytes_with_reason(_pdf_record(unreadable_path)) == (
        None,
        "unreadable_payload",
    )
    assert restart_store.load_persisted_source_bytes_with_reason(_pdf_record(tampered_path)) == (
        None,
        "integrity_mismatch",
    )


def test_permanent_rejection_reasons_exclude_the_transient_one():
    # Fix 2 scoping contract: destroying data on a transient read failure is worse than
    # an extra retry, so unreadable_payload must never trigger self-healing deletion.
    assert restart_store.PERMANENT_PERSISTED_SOURCE_REJECTIONS == {
        "invalid_metadata",
        "unconfined_path",
        "integrity_mismatch",
    }


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


def test_completed_source_cache_is_separate_from_ui_result_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    completed_source = restart_store.store_completed_source(
        session_id="session-a",
        source_name="report.docx",
        source_token="report.docx:3:abc",
        source_bytes=b"source-bytes",
    )
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"result-docx",
        output_dir=tmp_path / "ui_results",
        created_at=1_766_636_465.0,
    )

    completed_path = Path(completed_source["storage_path"])
    markdown_path = Path(artifact_paths["markdown_path"])
    docx_path = Path(artifact_paths["docx_path"])

    assert completed_source["storage_kind"] == "completed"
    assert completed_path.parent == tmp_path
    assert completed_path.name.startswith("completed_")
    assert markdown_path.parent == tmp_path / "ui_results"
    assert docx_path.parent == tmp_path / "ui_results"
    assert completed_path != markdown_path
    assert completed_path != docx_path
    assert ".result." not in completed_path.name


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
