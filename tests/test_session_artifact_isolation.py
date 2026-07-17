"""Spec 023 — per-run artifact isolation and confined restart-source deletion."""

from __future__ import annotations

from pathlib import Path

import docxaicorrector.processing.restart_store as restart_store
from docxaicorrector.runtime.artifacts import (
    _build_ui_result_stem,
    write_structure_manifest_artifact,
    write_ui_result_artifacts,
)

_SAME_SECOND = 1_766_636_465.0


# --- Problem A: artifact collisions -----------------------------------------

def test_same_source_same_second_yields_distinct_run_stems() -> None:
    first = _build_ui_result_stem("report.docx", created_at=_SAME_SECOND)
    second = _build_ui_result_stem("report.docx", created_at=_SAME_SECOND)
    assert first != second, "two runs of the same source in the same second must not share a stem"
    assert first.endswith(".result") and second.endswith(".result")


def test_explicit_run_id_is_threaded_into_stem() -> None:
    stem = _build_ui_result_stem("report.docx", created_at=_SAME_SECOND, run_id="deadbeef")
    assert "_deadbeef.result" in stem


def test_concurrent_same_source_runs_do_not_overwrite(tmp_path) -> None:
    first = write_ui_result_artifacts(
        source_name="report.docx", markdown_text="one", docx_bytes=b"one",
        output_dir=tmp_path, created_at=_SAME_SECOND,
    )
    second = write_ui_result_artifacts(
        source_name="report.docx", markdown_text="two", docx_bytes=b"two",
        output_dir=tmp_path, created_at=_SAME_SECOND,
    )
    assert first["markdown_path"] != second["markdown_path"]
    assert Path(first["markdown_path"]).read_text(encoding="utf-8") == "one"
    assert Path(second["markdown_path"]).read_text(encoding="utf-8") == "two"


def test_structure_manifest_runs_do_not_collide(tmp_path) -> None:
    first = write_structure_manifest_artifact(
        source_name="report.docx", manifest_payload={"segments": [1]},
        output_dir=tmp_path, created_at=_SAME_SECOND,
    )
    second = write_structure_manifest_artifact(
        source_name="report.docx", manifest_payload={"segments": [2]},
        output_dir=tmp_path, created_at=_SAME_SECOND,
    )
    assert first != second
    assert Path(first).exists() and Path(second).exists()


def test_atomic_write_leaves_no_temp_files(tmp_path) -> None:
    write_ui_result_artifacts(
        source_name="report.docx", markdown_text="body", docx_bytes=b"docx",
        narration_text="narr", output_dir=tmp_path, created_at=_SAME_SECOND,
    )
    leftovers = [p.name for p in tmp_path.iterdir() if ".tmp." in p.name]
    assert leftovers == [], f"temp files must not survive a successful write: {leftovers}"


# --- Problem B: confined restart-source deletion ----------------------------

def test_clear_restart_source_deletes_confined_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)
    target = tmp_path / "restart_sess_token.docx"
    target.write_bytes(b"x")
    restart_store.clear_restart_source({"storage_path": str(target)})
    assert not target.exists()


def test_clear_restart_source_refuses_path_outside_run_dir(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(restart_store, "RUN_DIR", run_dir)
    # Correct prefix but OUTSIDE RUN_DIR — must be refused, not deleted, no raise.
    outside = tmp_path / "restart_evil.docx"
    outside.write_bytes(b"keep")
    restart_store.clear_restart_source({"storage_path": str(outside)})
    assert outside.exists()


def test_clear_restart_source_refuses_bad_name_inside_run_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)
    # Inside RUN_DIR but not a restart_/completed_ file — must be refused.
    inside = tmp_path / "important.docx"
    inside.write_bytes(b"keep")
    restart_store.clear_restart_source({"storage_path": str(inside)})
    assert inside.exists()
