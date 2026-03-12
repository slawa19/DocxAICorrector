import base64
import zipfile
from io import BytesIO

import document
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches

from document import (
    build_editing_jobs,
    build_semantic_blocks,
    extract_document_content_from_docx,
    inspect_placeholder_integrity,
    resolve_image_insertions,
    resolve_final_image_bytes,
    reinsert_inline_images,
)
from models import ImageAsset
from models import ParagraphUnit


PNG_BYTES = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII=")


def test_build_semantic_blocks_keeps_heading_with_following_body():
    paragraphs = [
        ParagraphUnit(text="Глава 1", role="heading"),
        ParagraphUnit(text="Короткий абзац после заголовка.", role="body"),
        ParagraphUnit(text="Следующий абзац, который уже должен перейти в отдельный блок.", role="body"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=70)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Глава 1",
        "Короткий абзац после заголовка.",
    ]
    assert blocks[1].text == "Следующий абзац, который уже должен перейти в отдельный блок."


def test_build_editing_jobs_uses_neighbor_blocks_for_context():
    paragraphs = [
        ParagraphUnit(text="Первый блок.", role="body"),
        ParagraphUnit(text="Второй блок.", role="body"),
        ParagraphUnit(text="Третий блок.", role="body"),
    ]
    blocks = build_semantic_blocks(paragraphs, max_chars=20)

    jobs = build_editing_jobs(blocks, max_chars=3000)

    assert len(jobs) == 3
    assert jobs[1]["target_text"] == "Второй блок."
    assert jobs[1]["context_before"] == "Первый блок."
    assert jobs[1]["context_after"] == "Третий блок."
    assert all(str(job["target_text"]).strip() for job in jobs)


def test_extract_document_content_from_docx_inserts_image_placeholders(tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(PNG_BYTES)
    doc = Document()
    doc.add_paragraph("Вступление")
    doc.add_paragraph().add_run().add_picture(str(image_path))
    doc.add_paragraph("Завершение")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, image_assets = extract_document_content_from_docx(buffer)

    assert [paragraph.text for paragraph in paragraphs] == [
        "Вступление",
        "[[DOCX_IMAGE_img_001]]",
        "Завершение",
    ]
    assert len(image_assets) == 1
    assert image_assets[0].image_id == "img_001"
    assert image_assets[0].placeholder == "[[DOCX_IMAGE_img_001]]"
    assert image_assets[0].width_emu is not None
    assert image_assets[0].height_emu is not None
    assert inspect_placeholder_integrity("\n\n".join(paragraph.text for paragraph in paragraphs), image_assets) == {
        "img_001": "ok"
    }


def test_reinsert_inline_images_replaces_placeholder_with_picture():
    doc = Document()
    doc.add_paragraph("До")
    image_paragraph = doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    image_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    image_paragraph.paragraph_format.left_indent = Inches(0.5)
    doc.add_paragraph("После")
    buffer = BytesIO()
    doc.save(buffer)

    expected_indent = image_paragraph.paragraph_format.left_indent

    updated_bytes = reinsert_inline_images(
        buffer.getvalue(),
        [
            ImageAsset(
                image_id="img_001",
                placeholder="[[DOCX_IMAGE_img_001]]",
                original_bytes=PNG_BYTES,
                mime_type="image/png",
                position_index=0,
                width_emu=914400,
                height_emu=914400,
                final_variant="original",
            )
        ],
    )
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[1].text == ""
    assert updated_doc.paragraphs[1].alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert updated_doc.paragraphs[1].paragraph_format.left_indent == expected_indent
    assert len(updated_doc.inline_shapes) == 1
    assert updated_doc.inline_shapes[0].width == 914400
    assert updated_doc.inline_shapes[0].height == 914400


def test_reinsert_inline_images_in_compare_all_mode_inserts_all_generated_variants():
    doc = Document()
    doc.add_paragraph("До")
    doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    doc.add_paragraph("После")
    buffer = BytesIO()
    doc.save(buffer)

    updated_bytes = reinsert_inline_images(
        buffer.getvalue(),
        [
            ImageAsset(
                image_id="img_001",
                placeholder="[[DOCX_IMAGE_img_001]]",
                original_bytes=b"original",
                mime_type="image/png",
                position_index=0,
                width_emu=914400,
                height_emu=914400,
                validation_status="compared",
                comparison_variants={
                    "safe": {"bytes": PNG_BYTES},
                    "semantic_redraw_direct": {"bytes": PNG_BYTES},
                    "semantic_redraw_structured": {"bytes": PNG_BYTES},
                },
            )
        ],
    )
    updated_doc = Document(BytesIO(updated_bytes))

    assert len(updated_doc.inline_shapes) == 3
    assert "Вариант 1: Просто улучшить" in updated_doc.paragraphs[1].text
    assert "Вариант 2: Креативная AI-перерисовка" in updated_doc.paragraphs[1].text
    assert "Вариант 3: Структурная AI-перерисовка" in updated_doc.paragraphs[1].text


def test_resolve_final_image_bytes_prefers_selected_compare_variant():
    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=b"original",
        mime_type="image/png",
        position_index=0,
        safe_bytes=b"safe",
        redrawn_bytes=b"redrawn",
        final_variant="redrawn",
        comparison_variants={
            "semantic_redraw_direct": {"bytes": b"chosen"},
        },
        selected_compare_variant="semantic_redraw_direct",
    )

    assert resolve_final_image_bytes(asset) == b"chosen"


def test_resolve_final_image_bytes_returns_original_for_explicit_original_compare_choice():
    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=b"original",
        mime_type="image/png",
        position_index=0,
        safe_bytes=b"safe",
        redrawn_bytes=b"redrawn",
        final_variant="redrawn",
        comparison_variants={"semantic_redraw_direct": {"bytes": b"chosen"}},
        selected_compare_variant="original",
    )

    assert resolve_final_image_bytes(asset) == b"original"


def test_resolve_image_insertions_returns_all_compare_all_variants_before_single_final_choice():
    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=b"original",
        mime_type="image/png",
        position_index=0,
        validation_status="compared",
        comparison_variants={
            "safe": {"bytes": b"safe"},
            "semantic_redraw_direct": {"bytes": b"direct"},
            "semantic_redraw_structured": {"bytes": b"structured"},
        },
    )

    assert resolve_image_insertions(asset) == [
        ("Вариант 1: Просто улучшить", b"safe"),
        ("Вариант 2: Креативная AI-перерисовка", b"direct"),
        ("Вариант 3: Структурная AI-перерисовка", b"structured"),
    ]


def test_extract_document_content_from_docx_rejects_suspicious_uncompressed_archive(monkeypatch):
    monkeypatch.setattr(document, "MAX_DOCX_UNCOMPRESSED_SIZE_BYTES", 100)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "x" * 150)
        archive.writestr("word/document.xml", "<w:document />")
    buffer.seek(0)

    try:
        extract_document_content_from_docx(buffer)
    except RuntimeError as exc:
        assert "слишком велик после распаковки" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for suspiciously large uncompressed DOCX archive")


def test_read_uploaded_docx_bytes_preserves_original_cause(monkeypatch):
    failing_error = ValueError("bad upload")
    monkeypatch.setattr(document, "read_uploaded_file_bytes", lambda uploaded_file: (_ for _ in ()).throw(failing_error))

    try:
        document._read_uploaded_docx_bytes(object())
    except ValueError as exc:
        assert "Не удалось прочитать содержимое DOCX-файла" in str(exc)
        assert exc.__cause__ is failing_error
    else:
        raise AssertionError("Expected ValueError when uploaded DOCX bytes cannot be read")
