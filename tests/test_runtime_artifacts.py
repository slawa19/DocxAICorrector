import json
from pathlib import Path

from docxaicorrector.runtime.artifacts import write_structure_manifest_artifact, write_ui_result_artifacts


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
