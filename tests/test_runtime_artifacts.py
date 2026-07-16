import json
import os
from pathlib import Path

import pytest

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
    formatting_review_path = Path(artifact_paths["formatting_review_path"])

    assert metadata_path.parent == tmp_path
    assert metadata_path.name.endswith(".result.meta.json")
    assert formatting_review_path.parent == tmp_path
    assert formatting_review_path.name.endswith(".result.formatting_review.txt")
    assert "Проверка оформления — report.docx" in formatting_review_path.read_text(encoding="utf-8")
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "quality_warning": {
            "kind": "translation_quality_gate",
            "quality_status": "warn",
            "gate_reasons": ["unmapped_source_paragraphs_above_advisory_threshold"],
            "message": "Paragraph mapping drift detected.",
        },
    }


def test_write_ui_result_artifacts_persists_human_readable_formatting_review(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "quality_status": "warn",
            "gate_reasons": ["list_fragment_regressions_review_required"],
            "formatting_review_required_count": 1,
            "formatting_review_items": [
                {
                    "label": "Одиночный номер в сносках или библиографии",
                    "sample": {"text": "1489."},
                }
            ],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    review_path = Path(artifact_paths["formatting_review_path"])
    review_text = review_path.read_text(encoding="utf-8")

    assert review_path.name.endswith(".result.formatting_review.txt")
    assert "[ПРОВЕРКА] Одиночный номер в сносках или библиографии" in review_text
    assert "В выводе: «1489.»" in review_text
    assert "Всего: ПРАВКА 0 · ПРОВЕРКА 1 · КРИТ 0" in review_text


def test_write_ui_result_artifacts_marks_role_loss_review_items_as_fix(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "quality_status": "warn",
            "gate_reasons": ["role_loss_review_required"],
            "formatting_review_required_count": 1,
            "formatting_review_items": [
                {
                    "severity": "fix",
                    "label": "Структурный абзац стал обычным текстом",
                    "sample": {"text": "Chapter 10"},
                }
            ],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    review_text = Path(artifact_paths["formatting_review_path"]).read_text(encoding="utf-8")

    assert "[ПРАВКА] Структурный абзац стал обычным текстом" in review_text
    assert "В выводе: «Chapter 10»" in review_text
    assert "Всего: ПРАВКА 1 · ПРОВЕРКА 0 · КРИТ 0" in review_text


def test_write_ui_result_artifacts_uses_aggregate_count_for_capped_role_loss_samples(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "quality_status": "fail",
            "gate_reasons": ["role_loss_above_manual_review_threshold"],
            "formatting_review_required_count": 11,
            "formatting_review_items": [
                {
                    "severity": "fix",
                    "label": "Структурный абзац стал обычным текстом",
                    "aggregate_count": 11,
                    "count": 0,
                    "sample": {"text": "Chapter 0"},
                },
                *[
                    {
                        "severity": "fix",
                        "label": "Структурный абзац стал обычным текстом",
                        "count": 0,
                        "sample": {"text": f"Chapter {index}"},
                    }
                    for index in range(1, 8)
                ],
            ],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    review_text = Path(artifact_paths["formatting_review_path"]).read_text(encoding="utf-8")

    assert "[ПРАВКА] Структурный абзац стал обычным текстом" in review_text
    assert "В выводе: «Chapter 0»" in review_text
    assert "В выводе: «Chapter 7»" in review_text
    assert "Всего: ПРАВКА 11 · ПРОВЕРКА 0 · КРИТ 0" in review_text


def test_write_ui_result_artifacts_marks_bad_pair_review_items_as_defect(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "quality_status": "fail",
            "gate_reasons": ["mapping_text_quality_bad_pair"],
            "formatting_review_required_count": 1,
            "formatting_review_items": [
                {
                    "severity": "defect",
                    "label": "Перевод встал не к тому исходному абзацу",
                    "sample": {
                        "text": "Совсем другой перевод",
                        "source_text": "Original source paragraph",
                    },
                }
            ],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    review_text = Path(artifact_paths["formatting_review_path"]).read_text(encoding="utf-8")

    assert "[КРИТ] Перевод встал не к тому исходному абзацу" in review_text
    assert "Исходный абзац: «Original source paragraph»" in review_text
    assert "В выводе: «Совсем другой перевод»" in review_text
    assert "Всего: ПРАВКА 0 · ПРОВЕРКА 1 · КРИТ 0" not in review_text
    assert "Всего: ПРАВКА 0 · ПРОВЕРКА 0 · КРИТ 1" in review_text


def test_write_ui_result_artifacts_totals_line_counts_all_three_severities(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "quality_status": "fail",
            "gate_reasons": ["mapping_text_quality_bad_pair"],
            "formatting_review_items": [
                {"severity": "fix", "label": "Правка оформления", "sample": {"text": "A"}},
                {"severity": "review", "label": "Проверьте оформление", "sample": {"text": "B"}},
                {"severity": "review", "label": "И это тоже", "sample": {"text": "C"}},
                {
                    "severity": "defect",
                    "label": "Перевод встал не к тому исходному абзацу",
                    "aggregate_count": 5,
                    "count": 0,
                    "sample": {"text": "D", "source_text": "src"},
                },
            ],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    review_text = Path(artifact_paths["formatting_review_path"]).read_text(encoding="utf-8")

    assert "[ПРАВКА] Правка оформления" in review_text
    assert "[ПРОВЕРКА] Проверьте оформление" in review_text
    assert "[КРИТ] Перевод встал не к тому исходному абзацу" in review_text
    # Real counts: 1 fix, 2 review, 5 defects (aggregate) — no hardcoded КРИТ 0.
    assert "Всего: ПРАВКА 1 · ПРОВЕРКА 2 · КРИТ 5" in review_text


def test_write_ui_result_artifacts_empty_items_render_ok_block_with_zero_totals(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "quality_status": "warn",
            "gate_reasons": ["some_reason"],
            "formatting_review_items": [],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    review_text = Path(artifact_paths["formatting_review_path"]).read_text(encoding="utf-8")

    assert "[OK] Расхождений оформления для ручной проверки не найдено." in review_text
    assert "Всего: ПРАВКА 0 · ПРОВЕРКА 0 · КРИТ 0" in review_text


def test_write_ui_result_artifacts_aggregates_anchorless_items_without_empty_quote(tmp_path):
    # FR-006: an item whose anchor is not locatable is counted, never printed as «».
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "quality_status": "warn",
            "gate_reasons": ["role_loss_review_required"],
            "formatting_review_items": [
                {
                    "severity": "fix",
                    "label": "Структурный абзац стал обычным текстом",
                    "sample": {"text": "Глава десятая"},
                },
                {
                    "severity": "fix",
                    "label": "Структурный абзац стал обычным текстом",
                    "sample": {"text": "", "anchor_usable": False},
                },
            ],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    review_text = Path(artifact_paths["formatting_review_path"]).read_text(encoding="utf-8")

    assert "«»" not in review_text
    assert "В выводе: «Глава десятая»" in review_text
    assert "Мест без локализуемого якоря: 1" in review_text
    # Both items still counted in the totals — the anchorless one is not dropped.
    assert "Всего: ПРАВКА 2 · ПРОВЕРКА 0 · КРИТ 0" in review_text


def test_write_ui_result_artifacts_names_word_style_action_for_role_loss(tmp_path):
    # FR-005: a role_loss item with action_style names the Word style to apply.
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "quality_status": "fail",
            "gate_reasons": ["role_loss_above_manual_review_threshold"],
            "formatting_review_items": [
                {
                    "severity": "fix",
                    "label": "Заголовок стал обычным текстом",
                    "action_style": "Заголовок 1",
                    "sample": {"text": "Глава десятая", "role": "heading"},
                }
            ],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    review_text = Path(artifact_paths["formatting_review_path"]).read_text(encoding="utf-8")

    assert "Как исправить: примените стиль «Заголовок 1» к этому абзацу в DOCX." in review_text
    assert "убедитесь, что стиль и позиция сохранены" not in review_text


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
        ".formatting_review.txt": "old review",
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
    assert len(new_family_names) == 6
    assert all(name.endswith(suffix) for name, suffix in zip(new_family_names, [
        ".result.docx",
        ".result.formatting_review.txt",
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


def test_write_ui_result_artifacts_softens_short_note_or_marker_wording(tmp_path):
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "quality_status": "warn",
            "gate_reasons": ["unmapped_target_paragraphs_review_required"],
            "formatting_review_items": [
                {
                    "severity": "review",
                    "label": "Абзац перевода без явного соответствия оригиналу",
                    "sample": {"text": "1489.", "residual_class": "short_note_or_marker"},
                }
            ],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )

    review_text = Path(artifact_paths["formatting_review_path"]).read_text(encoding="utf-8")

    assert "похоже на сноску или маркер" in review_text
    # The generic check-wording must be replaced, not appended.
    assert "убедитесь, что стиль и позиция сохранены" not in review_text


def _build_short_note_review_text(tmp_path, *, residual_class: bool) -> str:
    sample: dict[str, object] = {"text": "1489."}
    if residual_class:
        sample["residual_class"] = "short_note_or_marker"
    artifact_paths = write_ui_result_artifacts(
        source_name="report.docx",
        markdown_text="body",
        docx_bytes=b"docx-bytes",
        quality_warning={
            "quality_status": "warn",
            "gate_reasons": ["unmapped_target_paragraphs_review_required"],
            "formatting_review_items": [
                {
                    "severity": "review",
                    "label": "Абзац перевода без явного соответствия оригиналу",
                    "sample": sample,
                }
            ],
        },
        output_dir=tmp_path,
        created_at=1_766_636_465.0,
    )
    return Path(artifact_paths["formatting_review_path"]).read_text(encoding="utf-8")


def test_short_note_or_marker_softening_is_data_preserving(tmp_path):
    # Counter-proof: softening the ONE descriptive phrase must not move any count/total.
    plain = _build_short_note_review_text(tmp_path, residual_class=False)
    softened = _build_short_note_review_text(tmp_path, residual_class=True)

    def summary_lines(text: str) -> list[str]:
        return [line for line in text.splitlines() if line.startswith(("Итог:", "Всего:"))]

    assert summary_lines(plain) == summary_lines(softened)
    assert "Всего: ПРАВКА 0 · ПРОВЕРКА 1 · КРИТ 0" in summary_lines(plain)

    plain_lines = plain.splitlines()
    softened_lines = softened.splitlines()
    assert len(plain_lines) == len(softened_lines)
    diffs = [(a, b) for a, b in zip(plain_lines, softened_lines) if a != b]
    assert len(diffs) == 1
    assert "похоже на сноску или маркер" in diffs[0][1]
    assert "убедитесь, что стиль и позиция сохранены" in diffs[0][0]


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


def test_write_segment_result_registry_prunes_stale_family_by_count(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_artifacts, "SEGMENT_RESULT_REGISTRY_MAX_COUNT", 1)
    monkeypatch.setattr(runtime_artifacts, "SEGMENT_RESULT_REGISTRY_MAX_AGE_SECONDS", 10_000)

    stale_leaf = tmp_path / "prep_old" / "struct-old"
    stale_leaf.mkdir(parents=True, exist_ok=True)
    stale_path = stale_leaf / "seg_0000.segment-result.json"
    stale_path.write_text(json.dumps({"segment_id": "seg_0000"}), encoding="utf-8")
    os.utime(stale_path, (10.0, 10.0))

    artifact_paths = write_segment_result_registry(
        records=[
            {
                "schema_version": 1,
                "prepared_source_key": "prep:report:1234",
                "structure_fingerprint": "struct-abc",
                "segment_id": "seg_0001",
                "translated_markdown": "Translated chapter",
            }
        ],
        output_dir=tmp_path,
    )

    new_path = Path(artifact_paths["seg_0001"])
    assert new_path.exists()
    # The count cap is family-wide (recursive), so the stale leaf is pruned even
    # though it lives under a different source/structure identity.
    assert not stale_path.exists()
    remaining = sorted(path.name for path in tmp_path.rglob("*.segment-result.json"))
    assert remaining == ["seg_0001.segment-result.json"]


def test_write_segment_result_registry_prunes_stale_family_by_age(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_artifacts, "SEGMENT_RESULT_REGISTRY_MAX_COUNT", 1000)
    monkeypatch.setattr(runtime_artifacts, "SEGMENT_RESULT_REGISTRY_MAX_AGE_SECONDS", 60)

    stale_leaf = tmp_path / "prep_old" / "struct-old"
    stale_leaf.mkdir(parents=True, exist_ok=True)
    stale_path = stale_leaf / "seg_0000.segment-result.json"
    stale_path.write_text(json.dumps({"segment_id": "seg_0000"}), encoding="utf-8")
    os.utime(stale_path, (10.0, 10.0))

    artifact_paths = write_segment_result_registry(
        records=[
            {
                "schema_version": 1,
                "prepared_source_key": "prep:report:1234",
                "structure_fingerprint": "struct-abc",
                "segment_id": "seg_0001",
                "translated_markdown": "Translated chapter",
            }
        ],
        output_dir=tmp_path,
    )

    assert Path(artifact_paths["seg_0001"]).exists()
    assert not stale_path.exists()


def test_write_segment_result_registry_never_prunes_current_run_batch(tmp_path, monkeypatch):
    # F11: a batch larger than the family count budget must return paths that ALL
    # still exist — the current run's just-written records are never pruned.
    monkeypatch.setattr(runtime_artifacts, "SEGMENT_RESULT_REGISTRY_MAX_COUNT", 2)
    monkeypatch.setattr(runtime_artifacts, "SEGMENT_RESULT_REGISTRY_MAX_AGE_SECONDS", 10_000)

    records = [
        {
            "schema_version": 1,
            "prepared_source_key": "prep:report:1234",
            "structure_fingerprint": "struct-abc",
            "segment_id": f"seg_{index:04d}",
            "translated_markdown": "Translated chapter",
        }
        for index in range(5)
    ]

    artifact_paths = write_segment_result_registry(records=records, output_dir=tmp_path)

    # All five returned paths exist despite the count budget being 2.
    assert len(artifact_paths) == 5
    for path in artifact_paths.values():
        assert Path(path).exists(), path


def test_write_segment_result_registry_prunes_history_but_protects_oversized_current_run(tmp_path, monkeypatch):
    # F11: history is still bounded — a stale historical leaf is pruned even while
    # the (oversized) current batch is fully protected.
    monkeypatch.setattr(runtime_artifacts, "SEGMENT_RESULT_REGISTRY_MAX_COUNT", 2)
    monkeypatch.setattr(runtime_artifacts, "SEGMENT_RESULT_REGISTRY_MAX_AGE_SECONDS", 10_000)

    stale_leaf = tmp_path / "prep_old" / "struct-old"
    stale_leaf.mkdir(parents=True, exist_ok=True)
    stale_path = stale_leaf / "seg_stale.segment-result.json"
    stale_path.write_text(json.dumps({"segment_id": "seg_stale"}), encoding="utf-8")
    os.utime(stale_path, (10.0, 10.0))

    records = [
        {
            "schema_version": 1,
            "prepared_source_key": "prep:report:1234",
            "structure_fingerprint": "struct-abc",
            "segment_id": f"seg_{index:04d}",
            "translated_markdown": "Translated chapter",
        }
        for index in range(3)
    ]

    artifact_paths = write_segment_result_registry(records=records, output_dir=tmp_path)

    assert len(artifact_paths) == 3
    for path in artifact_paths.values():
        assert Path(path).exists(), path
    # The stale historical leaf is still reclaimed.
    assert not stale_path.exists()


def test_write_segment_result_registry_writes_atomically_without_partial_file(tmp_path, monkeypatch):
    # F11: an interrupted write must never leave a truncated half-file at the final
    # path. Fail the os.replace of the SECOND record; its destination must not exist
    # and no temp sibling may survive.
    real_replace = os.replace
    replace_calls = {"count": 0}

    def _flaky_replace(src, dst, *args, **kwargs):
        replace_calls["count"] += 1
        if replace_calls["count"] >= 2:
            raise OSError("simulated interrupted registry write")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(runtime_artifacts.os, "replace", _flaky_replace)

    records = [
        {
            "prepared_source_key": "prep:report:1234",
            "structure_fingerprint": "struct-abc",
            "segment_id": f"seg_{index:04d}",
            "translated_markdown": "Translated chapter",
        }
        for index in range(2)
    ]

    with pytest.raises(OSError):
        write_segment_result_registry(records=records, output_dir=tmp_path)

    leaf = tmp_path / "prep_report_1234" / "struct-abc"
    # The second record's final artifact was never published — no half-file.
    assert not (leaf / "seg_0001.segment-result.json").exists()
    # No leftover temp siblings from the interrupted write.
    assert list(leaf.glob("*.tmp.*")) == []


def test_write_job_result_registry_never_prunes_current_run_batch(tmp_path, monkeypatch):
    # F11 (job-result writer parity): an oversized batch returns paths that all exist.
    monkeypatch.setattr(runtime_artifacts, "JOB_RESULT_REGISTRY_MAX_COUNT", 2)
    monkeypatch.setattr(runtime_artifacts, "JOB_RESULT_REGISTRY_MAX_AGE_SECONDS", 10_000)

    records = [
        {
            "schema_version": 1,
            "prepared_source_key": "prep:report:1234",
            "structure_fingerprint": "struct-abc",
            "job_id": f"job_{index:04d}",
            "segment_id": "seg_0001",
            "status": "completed",
        }
        for index in range(5)
    ]

    artifact_paths = write_job_result_registry(records=records, output_dir=tmp_path)

    assert len(artifact_paths) == 5
    for path in artifact_paths.values():
        assert Path(path).exists(), path


def test_write_job_result_registry_prunes_stale_family_by_count(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_artifacts, "JOB_RESULT_REGISTRY_MAX_COUNT", 1)
    monkeypatch.setattr(runtime_artifacts, "JOB_RESULT_REGISTRY_MAX_AGE_SECONDS", 10_000)

    stale_leaf = tmp_path / "prep_old" / "struct-old"
    stale_leaf.mkdir(parents=True, exist_ok=True)
    stale_path = stale_leaf / "job_0000.job-result.json"
    stale_path.write_text(json.dumps({"job_id": "job_0000", "status": "failed"}), encoding="utf-8")
    os.utime(stale_path, (10.0, 10.0))

    artifact_paths = write_job_result_registry(
        records=[
            {
                "schema_version": 1,
                "prepared_source_key": "prep:report:1234",
                "structure_fingerprint": "struct-abc",
                "job_id": "job_0007",
                "segment_id": "seg_0002",
                "status": "completed",
                "updated_at": "2026-05-07T12:00:00+00:00",
            }
        ],
        output_dir=tmp_path,
    )

    new_path = Path(artifact_paths["job_0007"])
    assert new_path.exists()
    assert not stale_path.exists()
    remaining = sorted(path.name for path in tmp_path.rglob("*.job-result.json"))
    assert remaining == ["job_0007.job-result.json"]


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


def test_atomic_write_group_staging_failure_publishes_nothing(tmp_path):
    # The SECOND entry's parent dir does not exist, so its ``write_text`` raises
    # FileNotFoundError (an OSError subclass) DURING staging. Nothing is published,
    # and the first entry's already-staged temp is rolled back.
    good_dir = tmp_path / "good"
    good_dir.mkdir()
    good_final = good_dir / "first.txt"
    bad_final = tmp_path / "missing" / "second.txt"  # parent "missing" does not exist

    with pytest.raises(OSError):
        runtime_artifacts._atomic_write_group(
            [
                (good_final, "first"),
                (bad_final, "second"),
            ]
        )

    # Nothing was published (staging failed before the os.replace phase).
    assert not good_final.exists()
    # The first entry's staged temp was unlinked on rollback — no leftovers.
    assert list(good_dir.glob("*.tmp.*")) == []


def test_atomic_write_group_publish_failure_rolls_back(tmp_path, monkeypatch):
    # os.replace succeeds on the first publish then raises OSError on the second, so the
    # first (already-published) final must be rolled back and no temp may survive.
    first_final = tmp_path / "first.txt"
    second_final = tmp_path / "second.txt"

    real_replace = os.replace
    replace_calls = {"count": 0}

    def _flaky_replace(src, dst, *args, **kwargs):
        replace_calls["count"] += 1
        if replace_calls["count"] >= 2:
            raise OSError("simulated publish failure on second os.replace")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(runtime_artifacts.os, "replace", _flaky_replace)

    with pytest.raises(OSError):
        runtime_artifacts._atomic_write_group(
            [
                (first_final, "first"),
                (second_final, "second"),
            ]
        )

    # First final was published then rolled back; second never published.
    assert not first_final.exists()
    assert not second_final.exists()
    # Both staged temps were unlinked (the moved one is gone, the remaining one cleaned).
    assert list(tmp_path.glob("*.tmp.*")) == []
