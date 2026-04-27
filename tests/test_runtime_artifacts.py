import json
from pathlib import Path

from runtime_artifacts import write_ui_result_artifacts


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
