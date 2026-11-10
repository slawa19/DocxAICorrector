"""Spec 073 WP-J: the book file as a result-group member, its retention and the bundle key (FR-008).

Contract: specs/073-narration-for-the-ear/contracts/result-and-screen.md sections 1-2.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import cast

import pytest

import docxaicorrector.processing.processing_runtime as processing_runtime
from docxaicorrector.pipeline.contracts import ResultArtifactWriter
from docxaicorrector.runtime.artifact_retention import (
    _resolve_ui_result_group_key,
    prune_ui_result_artifact_groups,
)
from docxaicorrector.runtime.artifacts import write_ui_result_artifacts

_CREATED_AT = 1_766_636_465.0
_RUN_ID = "run073"
_SOURCE = "Fictional Book.docx"
_BOOK_JSON = '{"schema_version": 1}\n'


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


# --- T-J1: characterization, green before and after the change -----------------------------------


def test_audiobook_group_with_docx_and_pdf_keeps_composition_and_keys(tmp_path):
    paths = _write(
        tmp_path,
        narration_text="Narration text.",
        narration_docx_bytes=b"PK-narration-docx",
        narration_pdf_bytes=b"%PDF-narration",
    )

    stem = Path(paths["markdown_path"]).name[: -len(".md")]
    assert _names(tmp_path) == sorted(
        [f"{stem}.md", f"{stem}.docx", f"{stem}.tts.txt", f"{stem}.tts.docx", f"{stem}.tts.pdf"]
    )
    assert set(paths) == {"markdown_path", "docx_path", "tts_text_path", "tts_docx_path", "tts_pdf_path"}


def test_translation_group_keeps_two_files_and_two_keys(tmp_path):
    paths = _write(tmp_path)

    assert len(_names(tmp_path)) == 2
    assert set(paths) == {"markdown_path", "docx_path"}


# --- T-J2: the new member ---------------------------------------------------------------------


def test_book_json_becomes_group_member_with_its_own_key(tmp_path):
    paths = _write(tmp_path, narration_text="Narration text.", narration_book_json=_BOOK_JSON)

    book_path = Path(paths["narration_book_path"])
    stem = Path(paths["markdown_path"]).name[: -len(".md")]
    assert stem.endswith(".result")
    assert book_path.name == f"{stem}.narration.json"
    assert book_path.read_bytes() == _BOOK_JSON.encode("utf-8")
    assert b"\r" not in book_path.read_bytes()


def test_book_json_keeps_non_ascii_text_as_utf8(tmp_path):
    text = '{"title": "Квазибург"}\n'
    paths = _write(tmp_path, narration_book_json=text)

    assert Path(paths["narration_book_path"]).read_bytes() == text.encode("utf-8")


@pytest.mark.parametrize("empty", [None, ""])
def test_empty_book_json_adds_no_file_and_no_key(tmp_path, empty):
    paths = _write(tmp_path, narration_text="Narration text.", narration_book_json=empty)

    assert "narration_book_path" not in paths
    assert not any(name.endswith(".narration.json") for name in _names(tmp_path))
    assert len(_names(tmp_path)) == 3


def test_result_artifact_writer_protocol_accepts_narration_book_json():
    assert "narration_book_json" in inspect.signature(ResultArtifactWriter.__call__).parameters
    assert "narration_book_json" in inspect.signature(write_ui_result_artifacts).parameters


# --- T-J3: atomic group rollback ----------------------------------------------------------------


def test_failed_write_of_book_member_leaves_no_group_file_and_no_temp_file(tmp_path, monkeypatch):
    original_write_text = Path.write_text

    def failing_write_text(self, data, *args, **kwargs):
        if ".narration.json" in self.name:
            raise OSError("disk full")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(OSError, match="disk full"):
        _write(tmp_path, narration_text="Narration text.", narration_book_json=_BOOK_JSON)

    assert _names(tmp_path) == []


# --- T-J4: retention ---------------------------------------------------------------------------


def _touch(path: Path, *, mtime: float) -> None:
    path.write_bytes(b"x")
    os.utime(path, (mtime, mtime))


def _book_group(tmp_path: Path, stem: str, *, mtime: float) -> list[Path]:
    members = [
        tmp_path / f"{stem}.result.md",
        tmp_path / f"{stem}.result.docx",
        tmp_path / f"{stem}.result.narration.json",
    ]
    for member in members:
        _touch(member, mtime=mtime)
    return members


def test_group_key_of_the_book_file_is_the_stem_and_other_suffixes_are_not_mixed_up():
    assert _resolve_ui_result_group_key(Path("x.result.narration.json")) == "x"
    assert _resolve_ui_result_group_key(Path("x.result.manifest.json")) == "x"
    assert _resolve_ui_result_group_key(Path("x.result.meta.json")) == "x"
    assert _resolve_ui_result_group_key(Path("x.narration.json")) is None


def test_old_group_is_deleted_with_the_book_file(tmp_path):
    now = 2_000_000_000.0
    old = _book_group(tmp_path, "20250101_000000_old_run1", mtime=now - 1000)
    fresh = _book_group(tmp_path, "20250102_000000_new_run2", mtime=now)

    pruned = prune_ui_result_artifact_groups(
        target_dir=tmp_path, max_age_seconds=500, max_count=None, now_epoch_seconds=now, emit_log=False
    )

    assert sorted(pruned) == sorted(str(path) for path in old)
    assert all(not path.exists() for path in old)
    assert all(path.exists() for path in fresh)


def test_overflow_group_is_deleted_whole_including_the_book_file(tmp_path):
    now = 2_000_000_000.0
    older = _book_group(tmp_path, "20250101_000000_old_run1", mtime=now - 20)
    newer = _book_group(tmp_path, "20250102_000000_new_run2", mtime=now)

    prune_ui_result_artifact_groups(
        target_dir=tmp_path, max_age_seconds=None, max_count=1, now_epoch_seconds=now, emit_log=False
    )

    assert all(not path.exists() for path in older)
    assert all(path.exists() for path in newer)


# --- T-J5: the bundle key ----------------------------------------------------------------------


def _bundle(narration_exports):
    return processing_runtime.build_result_bundle(
        source_name="r.docx",
        source_token="t",
        docx_bytes=None,
        markdown_text="md",
        narration_text="text",
        narration_exports=narration_exports,
    )["narration_exports"]


def test_bundle_keeps_book_json_and_the_four_072_keys():
    exports = _bundle(
        {
            "docx_bytes": b"docx",
            "pdf_bytes": None,
            "docx_unavailable_reason": None,
            "pdf_unavailable_reason": "timeout",
            "book_json": "t",
            "extra": b"drop me",
        }
    )

    assert exports == {
        "docx_bytes": b"docx",
        "pdf_bytes": None,
        "docx_unavailable_reason": None,
        "pdf_unavailable_reason": "timeout",
        "book_json": "t",
    }


@pytest.mark.parametrize("bad", [b"bytes", 5, "", None])
def test_bundle_turns_bad_book_json_into_none(bad):
    exports = cast("dict[str, object] | None", _bundle({"docx_bytes": b"docx", "book_json": bad}))

    assert exports is not None
    assert exports["book_json"] is None
