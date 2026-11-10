"""Spec 072 WP-E: result group files for the narration DOCX/PDF and their retention (FR-007).

Contract: specs/072-narration-docx-pdf/contracts/result-group.md section 1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from docxaicorrector.runtime.artifact_retention import (
    _resolve_ui_result_group_key,
    prune_ui_result_artifact_groups,
)
from docxaicorrector.runtime.artifacts import write_ui_result_artifacts

_CREATED_AT = 1_766_636_465.0
_RUN_ID = "run072"
_SOURCE = "Fictional Book.docx"


def _write(tmp_path: Path, **kwargs) -> dict[str, str]:
    return write_ui_result_artifacts(
        source_name=_SOURCE,
        markdown_text="# Title\n\nBody.",
        docx_bytes=b"docx-for-review",
        output_dir=tmp_path,
        created_at=_CREATED_AT,
        run_id=_RUN_ID,
        **kwargs,
    )


def _names(tmp_path: Path) -> list[str]:
    return sorted(path.name for path in tmp_path.iterdir())


# --- T-E1: characterization, green before and after the change ----------------------------------


def test_group_without_new_arguments_keeps_composition_names_and_keys(tmp_path):
    paths = _write(tmp_path, narration_text="Narration text.")

    stem = next(name for name in _names(tmp_path) if name.endswith(".md"))[: -len(".md")]
    assert stem.endswith(".result")
    assert _names(tmp_path) == sorted([f"{stem}.md", f"{stem}.docx", f"{stem}.tts.txt"])
    assert set(paths) == {"markdown_path", "docx_path", "tts_text_path"}
    assert {key: Path(value).name for key, value in paths.items()} == {
        "markdown_path": f"{stem}.md",
        "docx_path": f"{stem}.docx",
        "tts_text_path": f"{stem}.tts.txt",
    }


def test_group_without_narration_keeps_two_files(tmp_path):
    paths = _write(tmp_path)

    assert set(paths) == {"markdown_path", "docx_path"}
    assert len(_names(tmp_path)) == 2


# --- T-E2: new members -------------------------------------------------------------------------


def test_narration_docx_and_pdf_bytes_become_group_members(tmp_path):
    paths = _write(
        tmp_path,
        narration_text="Narration text.",
        narration_docx_bytes=b"PK-narration-docx",
        narration_pdf_bytes=b"%PDF-narration",
    )

    docx_path = Path(paths["tts_docx_path"])
    pdf_path = Path(paths["tts_pdf_path"])
    stem = Path(paths["markdown_path"]).name[: -len(".md")]
    assert docx_path.name == f"{stem}.tts.docx"
    assert pdf_path.name == f"{stem}.tts.pdf"
    assert docx_path.read_bytes() == b"PK-narration-docx"
    assert pdf_path.read_bytes() == b"%PDF-narration"
    assert Path(paths["tts_text_path"]).read_text(encoding="utf-8") == "Narration text."
    assert len(_names(tmp_path)) == 5


@pytest.mark.parametrize("empty", [None, b""])
def test_empty_narration_bytes_add_no_file_and_no_key(tmp_path, empty):
    paths = _write(
        tmp_path,
        narration_text="Narration text.",
        narration_docx_bytes=empty,
        narration_pdf_bytes=empty,
    )

    assert "tts_docx_path" not in paths
    assert "tts_pdf_path" not in paths
    assert len(_names(tmp_path)) == 3


def test_only_docx_bytes_writes_only_docx(tmp_path):
    paths = _write(tmp_path, narration_text="Narration text.", narration_docx_bytes=b"PK-x")

    assert "tts_docx_path" in paths
    assert "tts_pdf_path" not in paths
    assert not any(name.endswith(".tts.pdf") for name in _names(tmp_path))


# --- T-E3: atomic group rollback ---------------------------------------------------------------


def test_failed_write_of_pdf_member_leaves_no_group_file_and_no_temp_file(tmp_path, monkeypatch):
    original_write_bytes = Path.write_bytes

    def failing_write_bytes(self, data):
        if ".tts.pdf" in self.name:
            raise OSError("disk full")
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing_write_bytes)

    with pytest.raises(OSError, match="disk full"):
        _write(
            tmp_path,
            narration_text="Narration text.",
            narration_docx_bytes=b"PK-narration-docx",
            narration_pdf_bytes=b"%PDF-narration",
        )

    assert _names(tmp_path) == []


@pytest.mark.parametrize("failing_member", [".tts.pdf", ".tts.docx", ".result.md"])
def test_failure_after_partial_write_leaves_no_temp_file_and_no_member(tmp_path, monkeypatch, failing_member):
    """Codex acceptance finding 2: the write creates the temp file, THEN raises."""
    original_write_bytes = Path.write_bytes
    original_write_text = Path.write_text
    partial_writes: list[str] = []

    def partial_then_fail_bytes(self, data):
        if failing_member in self.name:
            original_write_bytes(self, data[:3])
            partial_writes.append(self.name)
            raise OSError("disk full after partial write")
        return original_write_bytes(self, data)

    def partial_then_fail_text(self, data, *args, **kwargs):
        if failing_member in self.name:
            original_write_text(self, data[:3], *args, **kwargs)
            partial_writes.append(self.name)
            raise OSError("disk full after partial write")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_bytes", partial_then_fail_bytes)
    monkeypatch.setattr(Path, "write_text", partial_then_fail_text)

    with pytest.raises(OSError, match="after partial write"):
        _write(
            tmp_path,
            narration_text="Narration text.",
            narration_docx_bytes=b"PK-narration-docx",
            narration_pdf_bytes=b"%PDF-narration",
        )

    assert len(partial_writes) == 1, "the failing member must really have created a partial file"
    assert _names(tmp_path) == []


# --- T-E4: retention ---------------------------------------------------------------------------


def _touch(path: Path, *, mtime: float) -> None:
    path.write_bytes(b"x")
    os.utime(path, (mtime, mtime))


def _full_group(directory: Path, stem: str, *, mtime: float) -> list[Path]:
    members = [
        directory / f"{stem}.result.md",
        directory / f"{stem}.result.docx",
        directory / f"{stem}.result.tts.txt",
        directory / f"{stem}.result.tts.docx",
        directory / f"{stem}.result.tts.pdf",
    ]
    for member in members:
        _touch(member, mtime=mtime)
    return members


def test_group_key_of_new_suffixes_is_the_stem():
    assert _resolve_ui_result_group_key(Path("x.result.tts.docx")) == "x"
    assert _resolve_ui_result_group_key(Path("x.result.tts.pdf")) == "x"
    assert _resolve_ui_result_group_key(Path("x.result.docx")) == "x"


def test_old_group_is_deleted_with_both_new_files(tmp_path):
    now = 2_000_000_000.0
    old = _full_group(tmp_path, "20250101_000000_old_run1", mtime=now - 1000)
    fresh = _full_group(tmp_path, "20250102_000000_new_run2", mtime=now)

    pruned = prune_ui_result_artifact_groups(
        target_dir=tmp_path,
        max_age_seconds=500,
        max_count=None,
        now_epoch_seconds=now,
        emit_log=False,
    )

    assert sorted(pruned) == sorted(str(path) for path in old)
    assert all(not path.exists() for path in old)
    assert all(path.exists() for path in fresh)


def test_overflow_group_is_deleted_whole_including_new_files(tmp_path):
    now = 2_000_000_000.0
    older = _full_group(tmp_path, "20250101_000000_old_run1", mtime=now - 20)
    newer = _full_group(tmp_path, "20250102_000000_new_run2", mtime=now)

    prune_ui_result_artifact_groups(
        target_dir=tmp_path,
        max_age_seconds=None,
        max_count=1,
        now_epoch_seconds=now,
        emit_log=False,
    )

    assert all(not path.exists() for path in older)
    assert all(path.exists() for path in newer)


def test_unrelated_file_is_still_never_pruned(tmp_path):
    now = 2_000_000_000.0
    _full_group(tmp_path, "20250101_000000_old_run1", mtime=now - 1000)
    stray = tmp_path / "notes.txt"
    _touch(stray, mtime=now - 1000)

    prune_ui_result_artifact_groups(
        target_dir=tmp_path,
        max_age_seconds=500,
        max_count=None,
        now_epoch_seconds=now,
        emit_log=False,
    )

    assert stray.exists()
