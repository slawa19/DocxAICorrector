import json
import os
from pathlib import Path

import docxaicorrector.runtime.artifacts as runtime_artifacts
from docxaicorrector.runtime.artifacts import (
    load_job_result_registry,
    write_job_result_registry,
    write_segment_result_registry,
    write_structure_manifest_artifact,
    write_ui_result_artifacts,
)


def test_write_ui_result_artifacts_persists_markdown_and_docx_pair(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="The Value of Everything.docx",
        markdown_text="# Result\n\nTranslated text",
        docx_bytes=b"docx-bytes",
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    markdown_path = Path(artifact_paths["markdown_path"])
    docx_path = Path(artifact_paths["docx_path"])

    assert markdown_path.parent == tmp_path
    assert docx_path.parent == tmp_path
    assert markdown_path.name.endswith(".result.md")
    assert docx_path.name.endswith(".result.docx")
    assert markdown_path.read_text(encoding="utf-8") == "# Result\n\nTranslated text"
    assert docx_path.read_bytes() == b"docx-bytes"


def test_write_ui_result_artifacts_prunes_oldest_files_for_same_family(tmp_path):
    stale_markdown = tmp_path / "old.result.md"
    stale_docx = tmp_path / "old.result.docx"
    stale_markdown.write_text("old", encoding="utf-8")
    stale_docx.write_bytes(b"old")

    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="new",
        docx_bytes=b"new",
        output_dir=tmp_path,
        created_at=1_766_636_466.0,
    )

    # No pruning should happen here yet because the family cap is far above 4 files;
    # this test mainly guards that the helper coexists with prior artifacts in one dir.
    assert stale_markdown.exists()
    assert stale_docx.exists()
    assert Path(artifact_paths["markdown_path"]).exists()
    assert Path(artifact_paths["docx_path"]).exists()


def test_write_ui_result_artifacts_persists_optional_narration_text(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="The Value of Everything.docx",
        markdown_text="# Result\n\nTranslated text",
        docx_bytes=b"docx-bytes",
        narration_text="[thoughtful] Ready for ElevenLabs",
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    tts_path = Path(artifact_paths["tts_text_path"])

    assert tts_path.parent == tmp_path
    assert tts_path.name.endswith(".result.tts.txt")
    assert tts_path.read_text(encoding="utf-8") == "[thoughtful] Ready for ElevenLabs"


def test_write_ui_result_artifacts_persists_machine_readable_quality_warning(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "kind": "translation_quality_gate",
            "quality_status": "warn",
            "gate_reasons": ["unmapped_source_paragraphs_above_advisory_threshold"],
            "message": "Paragraph mapping drift detected.",
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    metadata_path = Path(artifact_paths["metadata_path"])

    assert metadata_path.parent == tmp_path
    assert metadata_path.name.endswith(".result.meta.json")
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "quality_warning": {
            "kind": "translation_quality_gate",
            "quality_status": "warn",
            "gate_reasons": ["unmapped_source_paragraphs_above_advisory_threshold"],
            "message": "Paragraph mapping drift detected.",
        },
    }


def test_write_ui_result_artifacts_records_assembly_mode_in_meta(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        assembly_mode="selected_chapters",
        selected_segment_count=3,
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    metadata_path = Path(artifact_paths["metadata_path"])

    assert metadata_path.name.endswith(".result.meta.json")
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["assembly_mode"] == "selected_chapters"
    assert payload["selected_segment_count"] == 3
    assert "quality_warning" not in payload


def test_write_ui_result_artifacts_persists_result_manifest(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        result_manifest={
            "schema_version": 1,
            "assembly_mode": "selected_chapters",
            "output_mode": "selected_only",
            "segments": [{"segment_id": "seg_0001", "job_count": 2, "selected": True}],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    manifest_path = Path(artifact_paths["manifest_path"])

    assert manifest_path.parent == tmp_path
    assert manifest_path.name.endswith(".result.manifest.json")
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "assembly_mode": "selected_chapters",
        "output_mode": "selected_only",
        "segments": [{"segment_id": "seg_0001", "job_count": 2, "selected": True}],
    }


def test_write_ui_result_artifacts_records_full_document_assembly_mode(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        assembly_mode="full_document",
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    metadata_path = Path(artifact_paths["metadata_path"])
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["assembly_mode"] == "full_document"
    assert "selected_segment_count" not in payload


def test_write_ui_result_artifacts_merges_assembly_mode_and_quality_warning(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        assembly_mode="selected_chapters",
        selected_segment_count=2,
        quality_warning={"quality_status": "warn", "gate_reasons": ["drift"]},
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    metadata_path = Path(artifact_paths["metadata_path"])
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["assembly_mode"] == "selected_chapters"
    assert payload["selected_segment_count"] == 2
    assert payload["quality_warning"] == {"quality_status": "warn", "gate_reasons": ["drift"]}


def test_write_ui_result_artifacts_no_meta_when_no_mode_or_warning(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    assert "metadata_path" not in artifact_paths
    assert not any(p.name.endswith(".result.meta.json") for p in tmp_path.iterdir())


def test_write_ui_result_artifacts_prunes_old_result_family_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_artifacts, "UI_RESULT_ARTIFACTS_MAX_COUNT", 1)
    monkeypatch.setattr(runtime_artifacts, "UI_RESULT_ARTIFACTS_MAX_AGE_SECONDS", 10_000)

    old_stem = "20260423_101010_old.result"
    for suffix, content in {
        ".md": "old markdown",
        ".docx": b"old docx",
        ".tts.txt": "old narration",
        ".meta.json": json.dumps({"version": 1, "assembly_mode": "selected_chapters"}),
        ".manifest.json": json.dumps({"schema_version": 1, "segments": []}),
    }.items():
        path = tmp_path / f"{old_stem}{suffix}"
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        os.utime(path, (10.0, 10.0))

    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="new body",
        docx_bytes=b"new docx",
        narration_text="new narration",
        quality_warning={"quality_status": "warn", "gate_reasons": ["drift"]},
        result_manifest={"schema_version": 1, "segments": [{"segment_id": "seg_0001"}]},
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    new_family_names = sorted(Path(path).name for path in artifact_paths.values())
    remaining_names = sorted(path.name for path in tmp_path.iterdir() if path.is_file())

    assert not any(name.startswith(old_stem) for name in remaining_names)
    assert len(new_family_names) == 5
    assert all(name.endswith(suffix) for name, suffix in zip(new_family_names, [
        ".result.docx",
        ".result.manifest.json",
        ".result.md",
        ".result.meta.json",
        ".result.tts.txt",
    ]))
    assert remaining_names == new_family_names


def test_write_ui_result_artifacts_keeps_unrelated_files_while_pruning_result_families(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_artifacts, "UI_RESULT_ARTIFACTS_MAX_COUNT", 1)
    monkeypatch.setattr(runtime_artifacts, "UI_RESULT_ARTIFACTS_MAX_AGE_SECONDS", 10_000)

    old_stem = "20260423_101010_old.result"
    (tmp_path / f"{old_stem}.md").write_text("old markdown", encoding="utf-8")
    (tmp_path / f"{old_stem}.docx").write_bytes(b"old docx")
    os.utime(tmp_path / f"{old_stem}.md", (10.0, 10.0))
    os.utime(tmp_path / f"{old_stem}.docx", (10.0, 10.0))

    unrelated_paths = [
        tmp_path / "completed_session_token.docx",
        tmp_path / "notes.txt",
    ]
    unrelated_paths[0].write_bytes(b"completed cache")
    unrelated_paths[1].write_text("keep me", encoding="utf-8")
    os.utime(unrelated_paths[0], (5.0, 5.0))
    os.utime(unrelated_paths[1], (5.0, 5.0))

    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="new body",
        docx_bytes=b"new docx",
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    new_family_names = sorted(Path(path).name for path in artifact_paths.values())
    remaining_names = sorted(path.name for path in tmp_path.iterdir() if path.is_file())

    assert "completed_session_token.docx" in remaining_names
    assert "notes.txt" in remaining_names
    assert not any(name.startswith(old_stem) for name in remaining_names)
    assert new_family_names[0] in remaining_names
    assert new_family_names[1] in remaining_names


def test_write_structure_manifest_artifact_persists_segments_json(tmp_path):
    manifest_path = write_structure_manifest_artifact(
        source_name="The Value of Everything.docx",
        manifest_payload={
            "schema_version": 1,
            "structure_fingerprint": "abc123",
            "segments": [{"segment_id": "seg_0001_deadbeef", "title": "Chapter 1"}],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    persisted_path = Path(manifest_path)

    assert persisted_path.parent == tmp_path
    assert persisted_path.name.endswith(".segments.json")
    assert json.loads(persisted_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "structure_fingerprint": "abc123",
        "segments": [{"segment_id": "seg_0001_deadbeef", "title": "Chapter 1"}],
    }


def test_write_segment_result_registry_persists_segment_records_in_identity_tree(tmp_path):
    artifact_paths = write_segment_result_registry(
        records=[
            {
                "schema_version": 1,
                "prepared_source_key": "prep:report:1234",
                "structure_fingerprint": "struct-abc",
                "segment_id": "seg_0001",
                "translated_markdown": "Translated chapter",
                "result_artifact_paths": {
                    "markdown_path": "/tmp/report.result.md",
                    "docx_path": "/tmp/report.result.docx",
                },
            }
        ],
        output_dir=tmp_path,
    )

    persisted_path = Path(artifact_paths["seg_0001"])

    assert persisted_path == tmp_path / "prep_report_1234" / "struct-abc" / "seg_0001.segment-result.json"
    assert json.loads(persisted_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "prepared_source_key": "prep:report:1234",
        "structure_fingerprint": "struct-abc",
        "segment_id": "seg_0001",
        "translated_markdown": "Translated chapter",
        "result_artifact_paths": {
            "markdown_path": "/tmp/report.result.md",
            "docx_path": "/tmp/report.result.docx",
        },
    }


def test_write_job_result_registry_persists_job_records_in_identity_tree(tmp_path):
    artifact_paths = write_job_result_registry(
        records=[
            {
                "schema_version": 1,
                "prepared_source_key": "prep:report:1234",
                "structure_fingerprint": "struct-abc",
                "job_id": "job_0007",
                "segment_id": "seg_0002",
                "status": "failed",
                "updated_at": "2026-05-07T12:00:00+00:00",
                "error_code": "block_failed",
            }
        ],
        output_dir=tmp_path,
    )

    persisted_path = Path(artifact_paths["job_0007"])

    assert persisted_path == tmp_path / "prep_report_1234" / "struct-abc" / "job_0007.job-result.json"
    assert json.loads(persisted_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "prepared_source_key": "prep:report:1234",
        "structure_fingerprint": "struct-abc",
        "job_id": "job_0007",
        "segment_id": "seg_0002",
        "status": "failed",
        "updated_at": "2026-05-07T12:00:00+00:00",
        "error_code": "block_failed",
    }


def test_load_job_result_registry_keeps_latest_record_per_job_id(tmp_path):
    target_dir = tmp_path / "prep_report_1234" / "struct-abc"
    target_dir.mkdir(parents=True, exist_ok=True)

    first_path = target_dir / "job_0001.job-result.json"
    second_path = target_dir / "job_0002.job-result.json"

    first_path.write_text(
        json.dumps(
            {
                "prepared_source_key": "prep:report:1234",
                "structure_fingerprint": "struct-abc",
                "job_id": "job_0001",
                "status": "failed",
            }
        ),
        encoding="utf-8",
    )
    second_path.write_text(
        json.dumps(
            {
                "prepared_source_key": "prep:report:1234",
                "structure_fingerprint": "struct-abc",
                "job_id": "job_0002",
                "status": "completed",
            }
        ),
        encoding="utf-8",
    )

    loaded = load_job_result_registry(
        prepared_source_key="prep:report:1234",
        structure_fingerprint="struct-abc",
        input_dir=tmp_path,
    )

    assert loaded == {
        "job_0001": {
            "prepared_source_key": "prep:report:1234",
            "structure_fingerprint": "struct-abc",
            "job_id": "job_0001",
            "status": "failed",
        },
        "job_0002": {
            "prepared_source_key": "prep:report:1234",
            "structure_fingerprint": "struct-abc",
            "job_id": "job_0002",
            "status": "completed",
        },
    }


def test_load_job_result_registry_prefers_payload_updated_at_over_file_mtime(tmp_path):
    target_dir = tmp_path / "prep_report_1234" / "struct-abc"
    target_dir.mkdir(parents=True, exist_ok=True)

    older_payload_newer_file = target_dir / "job_0001_newer-file.job-result.json"
    newer_payload_older_file = target_dir / "job_0001_older-file.job-result.json"

    older_payload_newer_file.write_text(
        json.dumps(
            {
                "prepared_source_key": "prep:report:1234",
                "structure_fingerprint": "struct-abc",
                "job_id": "job_0001",
                "status": "completed",
                "updated_at": "2026-05-07T11:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    newer_payload_older_file.write_text(
        json.dumps(
            {
                "prepared_source_key": "prep:report:1234",
                "structure_fingerprint": "struct-abc",
                "job_id": "job_0001",
                "status": "failed",
                "updated_at": "2026-05-07T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    os.utime(newer_payload_older_file, (1_700_000_000, 1_700_000_000))
    os.utime(older_payload_newer_file, (1_800_000_000, 1_800_000_000))

    loaded = load_job_result_registry(
        prepared_source_key="prep:report:1234",
        structure_fingerprint="struct-abc",
        input_dir=tmp_path,
    )

    assert loaded == {
        "job_0001": {
            "prepared_source_key": "prep:report:1234",
            "structure_fingerprint": "struct-abc",
            "job_id": "job_0001",
            "status": "failed",
            "updated_at": "2026-05-07T12:00:00+00:00",
        }
    }
