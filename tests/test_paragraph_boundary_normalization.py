from io import BytesIO
import base64
import json

import config
from docx import Document as make_document
import document as document_module

from document import (
    build_document_text,
    build_marker_wrapped_block_text,
    extract_document_content_with_boundary_report,
)


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII="
)


def _save_document(document) -> BytesIO:
    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer


def test_false_body_boundary_is_merged_into_one_logical_paragraph():
    document = make_document()
    document.add_paragraph("архетипами: повторяющимися моделями")
    document.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "архетипами: повторяющимися моделями поведения во времени, наблюдаемыми в разных системах."
    assert paragraphs[0].origin_raw_indexes == [0, 1]
    assert paragraphs[0].origin_raw_texts == [
        "архетипами: повторяющимися моделями",
        "поведения во времени, наблюдаемыми в разных системах.",
    ]
    assert paragraphs[0].boundary_source == "normalized_merge"
    assert report.merged_group_count == 1
    assert report.merged_raw_paragraph_count == 2
    assert build_document_text(paragraphs) == paragraphs[0].text
    assert build_marker_wrapped_block_text(paragraphs) == f"[[DOCX_PARA_{paragraphs[0].paragraph_id}]]\n{paragraphs[0].text}"


def test_terminal_punctuation_preserves_real_paragraph_boundary():
    document = make_document()
    document.add_paragraph("Первый абзац закончен.")
    document.add_paragraph("Второй абзац начинается с новой мысли.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.text for paragraph in paragraphs] == [
        "Первый абзац закончен.",
        "Второй абзац начинается с новой мысли.",
    ]
    assert report.merged_group_count == 0
    assert report.decisions[0].decision == "keep"
    assert report.decisions[0].confidence == "blocked"


def test_heading_body_boundary_is_never_merged():
    document = make_document()
    document.add_paragraph("Глава 1", style="Heading 1")
    document.add_paragraph("основной текст после заголовка")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["heading", "body"]
    assert report.merged_group_count == 0
    assert report.decisions[0].reasons == ("heading_boundary", "non_body_role", "style_transition")


def test_list_boundary_is_never_merged():
    document = make_document()
    document.add_paragraph("Вступление без финальной точки")
    document.add_paragraph("Первый пункт", style="List Number")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "list"]
    assert report.merged_group_count == 0
    assert "list_metadata" in report.decisions[0].reasons


def test_merged_text_spacing_is_normalized_conservatively():
    document = make_document()
    document.add_paragraph("Это важное")
    document.add_paragraph("продолжение текста")

    paragraphs, _, _ = extract_document_content_with_boundary_report(_save_document(document))

    assert paragraphs[0].text == "Это важное продолжение текста"


def test_high_confidence_merge_chain_collapses_three_adjacent_body_paragraphs():
    document = make_document()
    document.add_paragraph("Это особенно важно")
    document.add_paragraph("для устойчивой")
    document.add_paragraph("работы всей системы.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "Это особенно важно для устойчивой работы всей системы."
    assert paragraphs[0].origin_raw_indexes == [0, 1, 2]
    assert paragraphs[0].boundary_source == "normalized_merge"
    assert paragraphs[0].boundary_confidence == "high"
    assert paragraphs[0].boundary_rationale == (
        "same_body_style, compatible_alignment, left_not_terminal, "
        "right_starts_continuation, left_incomplete, combined_sentence_plausible"
    )
    assert report.merged_group_count == 1
    assert report.merged_raw_paragraph_count == 3
    assert [(decision.left_raw_index, decision.right_raw_index, decision.decision, decision.confidence) for decision in report.decisions] == [
        (0, 1, "merge", "high"),
        (1, 2, "merge", "high"),
    ]


def test_debug_artifact_report_writes_expected_path_and_payload(monkeypatch, tmp_path):
    reports_dir = tmp_path / "paragraph-boundary-reports"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_REPORTS_DIR", reports_dir)
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": True,
        },
    )
    monkeypatch.setattr(document_module, "resolve_uploaded_filename", lambda uploaded_file: "debug sample.docx")

    debug_doc = make_document()
    debug_doc.add_paragraph("архетипами: повторяющимися моделями")
    debug_doc.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")
    uploaded = _save_document(debug_doc)

    paragraphs, _, report = extract_document_content_with_boundary_report(uploaded)

    assert len(paragraphs) == 1
    artifact_files = sorted(reports_dir.glob("*.json"))
    assert len(artifact_files) == 1
    assert artifact_files[0].name.startswith("debug_sample.docx_")

    payload = json.loads(artifact_files[0].read_text(encoding="utf-8"))
    assert payload == {
        "version": 1,
        "source_file": "debug sample.docx",
        "source_hash": payload["source_hash"],
        "mode": "high_only",
        "total_raw_paragraphs": 2,
        "total_logical_paragraphs": 1,
        "merged_group_count": 1,
        "merged_raw_paragraph_count": 2,
        "decisions": [
            {
                "left_raw_index": 0,
                "right_raw_index": 1,
                "decision": "merge",
                "confidence": "high",
                "reasons": [
                    "same_body_style",
                    "compatible_alignment",
                    "left_not_terminal",
                    "right_starts_continuation",
                    "left_incomplete",
                    "combined_sentence_plausible",
                ],
            }
        ],
    }
    assert len(payload["source_hash"]) == 8


def test_debug_artifact_report_is_not_written_when_saving_disabled(monkeypatch, tmp_path):
    reports_dir = tmp_path / "paragraph-boundary-reports"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_REPORTS_DIR", reports_dir)
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": False,
        },
    )
    monkeypatch.setattr(document_module, "resolve_uploaded_filename", lambda uploaded_file: "debug sample.docx")

    debug_doc = make_document()
    debug_doc.add_paragraph("архетипами: повторяющимися моделями")
    debug_doc.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(debug_doc))

    assert len(paragraphs) == 1
    assert report.merged_group_count == 1
    assert not reports_dir.exists()


def test_debug_artifact_directory_creation_failure_is_non_fatal(monkeypatch, tmp_path):
    reports_dir = tmp_path / "paragraph-boundary-reports"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_REPORTS_DIR", reports_dir)
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": True,
        },
    )

    def fail_mkdir(self, *args, **kwargs):
        raise OSError("mkdir blocked")

    monkeypatch.setattr(document_module.Path, "mkdir", fail_mkdir)

    debug_doc = make_document()
    debug_doc.add_paragraph("архетипами: повторяющимися моделями")
    debug_doc.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(debug_doc))

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "архетипами: повторяющимися моделями поведения во времени, наблюдаемыми в разных системах."
    assert report.merged_group_count == 1
    assert not reports_dir.exists()


def test_debug_artifact_file_write_failure_is_non_fatal(monkeypatch, tmp_path):
    reports_dir = tmp_path / "paragraph-boundary-reports"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_REPORTS_DIR", reports_dir)
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": True,
        },
    )
    monkeypatch.setattr(document_module, "resolve_uploaded_filename", lambda uploaded_file: "debug sample.docx")

    original_write_text = document_module.Path.write_text

    def fail_report_write(self, *args, **kwargs):
        if self.suffix == ".json":
            raise OSError("write blocked")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(document_module.Path, "write_text", fail_report_write)

    debug_doc = make_document()
    debug_doc.add_paragraph("архетипами: повторяющимися моделями")
    debug_doc.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(debug_doc))

    assert len(paragraphs) == 1
    assert report.merged_group_count == 1
    assert reports_dir.exists()
    assert list(reports_dir.glob("*.json")) == []


def test_disabled_normalization_preserves_legacy_boundaries(monkeypatch):
    document = make_document()
    document.add_paragraph("архетипами: повторяющимися моделями")
    document.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": False,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": False,
        },
    )

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.text for paragraph in paragraphs] == [
        "архетипами: повторяющимися моделями",
        "поведения во времени, наблюдаемыми в разных системах.",
    ]
    assert report.merged_group_count == 0
    assert report.merged_raw_paragraph_count == 0


def test_caption_boundary_is_never_merged():
    document = make_document()
    document.add_paragraph("Вступление без завершающей точки")
    document.add_paragraph("Рисунок 1. Подпись", style="Caption")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "caption"]
    assert report.merged_group_count == 0
    assert "caption_like_boundary" in report.decisions[0].reasons


def test_image_boundary_is_never_merged(tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(PNG_BYTES)
    document = make_document()
    document.add_paragraph("Вступление без завершающей точки")
    document.add_paragraph().add_run().add_picture(str(image_path))
    document.add_paragraph("продолжение после изображения")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "image", "body"]
    assert report.merged_group_count == 0
    assert report.decisions[0].decision == "keep"
    assert report.decisions[0].confidence == "blocked"
    assert "non_body_role" in report.decisions[0].reasons
    assert report.decisions[1].decision == "keep"
    assert report.decisions[1].confidence == "blocked"
    assert "non_body_role" in report.decisions[1].reasons


def test_table_boundary_is_never_merged():
    document = make_document()
    document.add_paragraph("Вступление без завершающей точки")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "ячейка"
    document.add_paragraph("продолжение после таблицы")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "table", "body"]
    assert report.merged_group_count == 0
