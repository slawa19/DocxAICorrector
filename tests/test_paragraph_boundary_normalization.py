from io import BytesIO
import base64

import config
from docx import Document

from document import (
    build_document_text,
    build_marker_wrapped_block_text,
    extract_document_content_with_boundary_report,
)


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII="
)


def _save_document(document: Document) -> BytesIO:
    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer


def test_false_body_boundary_is_merged_into_one_logical_paragraph():
    document = Document()
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
    document = Document()
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
    document = Document()
    document.add_paragraph("Глава 1", style="Heading 1")
    document.add_paragraph("основной текст после заголовка")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["heading", "body"]
    assert report.merged_group_count == 0
    assert report.decisions[0].reasons == ("heading_boundary", "non_body_role", "style_transition")


def test_list_boundary_is_never_merged():
    document = Document()
    document.add_paragraph("Вступление без финальной точки")
    document.add_paragraph("Первый пункт", style="List Number")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "list"]
    assert report.merged_group_count == 0
    assert "list_metadata" in report.decisions[0].reasons


def test_merged_text_spacing_is_normalized_conservatively():
    document = Document()
    document.add_paragraph("Это важное")
    document.add_paragraph("продолжение текста")

    paragraphs, _, _ = extract_document_content_with_boundary_report(_save_document(document))

    assert paragraphs[0].text == "Это важное продолжение текста"


def test_disabled_normalization_preserves_legacy_boundaries(monkeypatch):
    document = Document()
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
    document = Document()
    document.add_paragraph("Вступление без завершающей точки")
    document.add_paragraph("Рисунок 1. Подпись", style="Caption")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "caption"]
    assert report.merged_group_count == 0
    assert "caption_like_boundary" in report.decisions[0].reasons


def test_image_boundary_is_never_merged(tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(PNG_BYTES)
    document = Document()
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
    document = Document()
    document.add_paragraph("Вступление без завершающей точки")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "ячейка"
    document.add_paragraph("продолжение после таблицы")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "table", "body"]
    assert report.merged_group_count == 0