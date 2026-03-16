import base64
import zipfile
from io import BytesIO
from typing import Any, cast

import document
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Inches

from document import (
    _build_variant_table_element,
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    _replace_xml_element_with_sequence,
    extract_document_content_from_docx,
    inspect_placeholder_integrity,
    normalize_semantic_output_docx,
    preserve_source_paragraph_properties,
    resolve_image_insertions,
    resolve_final_image_bytes,
    reinsert_inline_images,
)
from models import ImageAsset, ImageVariantCandidate
from models import ParagraphUnit


PNG_BYTES = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII=")


def _add_hyperlink(paragraph, text: str, url: str) -> None:
    relationship_id = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)

    run = OxmlElement("w:r")
    text_element = OxmlElement("w:t")
    text_element.text = text
    run.append(text_element)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _append_tab(run) -> None:
    run._element.append(OxmlElement("w:tab"))


def _set_raw_paragraph_alignment(paragraph, value: str) -> None:
    paragraph_properties = paragraph._element.get_or_add_pPr()
    alignment = paragraph_properties.find(qn("w:jc"))
    if alignment is None:
        alignment = OxmlElement("w:jc")
        paragraph_properties.append(alignment)
    alignment.set(qn("w:val"), value)


def _set_outline_level(paragraph, value: int) -> None:
    paragraph_properties = paragraph._element.get_or_add_pPr()
    outline_level = paragraph_properties.find(qn("w:outlineLvl"))
    if outline_level is None:
        outline_level = OxmlElement("w:outlineLvl")
        paragraph_properties.append(outline_level)
    outline_level.set(qn("w:val"), str(value))


def _set_style_outline_level(style, value: int) -> None:
    style_properties = style._element.get_or_add_pPr()
    outline_level = style_properties.find(qn("w:outlineLvl"))
    if outline_level is None:
        outline_level = OxmlElement("w:outlineLvl")
        style_properties.append(outline_level)
    outline_level.set(qn("w:val"), str(value))


def _append_textbox_with_text(paragraph, text: str) -> None:
        paragraph._p.append(
                parse_xml(
                        f"""
                        <w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                                 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
                                 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                                 xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
                            <w:drawing>
                                <wp:inline>
                                    <wp:extent cx="914400" cy="914400"/>
                                    <wp:docPr id="1" name="TextBox 1"/>
                                    <a:graphic>
                                        <a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
                                            <wps:wsp>
                                                <wps:txbx>
                                                    <w:txbxContent>
                                                        <w:p>
                                                            <w:r>
                                                                <w:t>{text}</w:t>
                                                            </w:r>
                                                        </w:p>
                                                    </w:txbxContent>
                                                </wps:txbx>
                                                <wps:bodyPr/>
                                            </wps:wsp>
                                        </a:graphicData>
                                    </a:graphic>
                                </wp:inline>
                            </w:drawing>
                        </w:r>
                        """
                )
        )


def _extract_docpr_descriptions(element) -> list[str]:
    return [doc_pr.get("descr") for doc_pr in element.xpath(".//wp:docPr") if doc_pr.get("descr")]


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


def test_inspect_placeholder_integrity_reports_unexpected_placeholders():
    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
    )

    status_map = inspect_placeholder_integrity(
        "[[DOCX_IMAGE_img_001]]\n\n[[DOCX_IMAGE_img_999]]",
        [asset],
    )

    assert status_map == {
        "img_001": "ok",
        "unexpected:[[DOCX_IMAGE_img_999]]": "unexpected",
    }


def test_build_document_text_renders_word_numbered_and_bulleted_lists_as_markdown():
    doc = Document()
    doc.add_paragraph("Вступление")
    doc.add_paragraph("Первый пункт", style="List Number")
    doc.add_paragraph("Второй пункт", style="List Number")
    doc.add_paragraph("Подпункт", style="List Bullet 2")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["body", "list", "list", "list"]
    assert paragraphs[1].list_kind == "ordered"
    assert paragraphs[2].list_kind == "ordered"
    assert paragraphs[3].list_kind == "unordered"
    assert paragraphs[3].list_level == 1
    assert build_document_text(paragraphs) == (
        "Вступление\n\n"
        "1. Первый пункт\n\n"
        "1. Второй пункт\n\n"
        "    - Подпункт"
    )


def test_build_document_text_does_not_duplicate_existing_list_markers():
    paragraphs = [
        ParagraphUnit(text="1. Уже размеченный пункт", role="list", list_kind="ordered"),
        ParagraphUnit(text="- Уже размеченный маркер", role="list", list_kind="unordered"),
    ]

    assert build_document_text(paragraphs) == "1. Уже размеченный пункт\n\n- Уже размеченный маркер"


def test_extract_document_content_from_docx_renders_title_and_outline_levels_as_markdown_headings():
    doc = Document()
    doc.add_paragraph("Название главы", style="Title")
    subheading = doc.add_paragraph("Подзаголовок")
    _set_outline_level(subheading, 1)
    doc.add_paragraph("Основной текст.")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["heading", "heading", "body"]
    assert paragraphs[0].heading_level == 1
    assert paragraphs[1].heading_level == 2
    assert build_document_text(paragraphs) == "# Название главы\n\n## Подзаголовок\n\nОсновной текст."


def test_extract_document_content_from_docx_uses_inherited_outline_level_from_base_style():
    doc = Document()
    base_style = doc.styles.add_style("Base Outline Heading", WD_STYLE_TYPE.PARAGRAPH)
    _set_style_outline_level(base_style, 2)
    derived_style = cast(Any, doc.styles.add_style("Derived Outline Heading", WD_STYLE_TYPE.PARAGRAPH))
    derived_style.base_style = base_style
    doc.add_paragraph("Наследуемый заголовок", style="Derived Outline Heading")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].role == "heading"
    assert paragraphs[0].heading_level == 3
    assert build_document_text(paragraphs) == "### Наследуемый заголовок"


def test_extract_document_content_from_docx_recognizes_russian_heading_alias_style():
    doc = Document()
    doc.styles.add_style("Заголовок 3", WD_STYLE_TYPE.PARAGRAPH)
    doc.add_paragraph("Русский заголовок", style="Заголовок 3")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].role == "heading"
    assert paragraphs[0].heading_level == 3
    assert build_document_text(paragraphs) == "### Русский заголовок"


def test_extract_document_content_from_docx_keeps_tables_in_document_order():
    doc = Document()
    doc.add_paragraph("Перед таблицей")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Колонка A"
    table.cell(0, 1).text = "Колонка B"
    table.cell(1, 0).text = "Значение 1"
    table.cell(1, 1).text = "Значение 2"
    doc.add_paragraph("После таблицы")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["body", "table", "body"]
    assert paragraphs[1].text.startswith("<table>")
    assert "Колонка A" in paragraphs[1].text
    assert build_document_text(paragraphs).startswith("Перед таблицей\n\n<table>")


def test_extract_document_content_from_docx_marks_caption_after_image(tmp_path):
    image_path = tmp_path / "docx_caption_image.png"
    image_path.write_bytes(PNG_BYTES)

    doc = Document()
    doc.add_paragraph().add_run().add_picture(str(image_path))
    doc.add_paragraph("Рис. 1. Подпись к изображению")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["image", "caption"]


def test_extract_document_content_from_docx_keeps_caption_style_after_image_even_when_format_looks_like_heading(tmp_path):
    image_path = tmp_path / "docx_caption_headingish_image.png"
    image_path.write_bytes(PNG_BYTES)

    doc = Document()
    doc.add_paragraph().add_run().add_picture(str(image_path))
    caption = doc.add_paragraph(style="Caption")
    caption_run = caption.add_run("Рисунок 1 Образец подписи")
    caption_run.bold = True
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["image", "caption"]
    assert paragraphs[1].heading_level is None
    assert build_document_text(paragraphs) == "[[DOCX_IMAGE_img_001]]\n\n**Рисунок 1 Образец подписи**"


def test_extract_document_content_from_docx_marks_caption_after_table():
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Ячейка"
    doc.add_paragraph("Таблица 1. Подпись к таблице")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["table", "caption"]


def test_extract_document_content_from_docx_reclassifies_heading_like_caption_after_table():
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Ячейка"
    caption = doc.add_paragraph("Таблица 1 Итоговые показатели")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["table", "caption"]
    assert paragraphs[1].heading_level is None


def test_extract_document_content_from_docx_does_not_treat_justified_body_text_as_heading():
    doc = Document()
    paragraph = doc.add_paragraph("Это обычный выровненный по ширине абзац без признаков заголовка")
    _set_raw_paragraph_alignment(paragraph, "both")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].role == "body"
    assert paragraphs[0].heading_level is None


def test_extract_document_content_from_docx_recovers_mixed_format_heading_in_normal_style():
    doc = Document()
    paragraph = doc.add_paragraph(style="Normal")
    first_run = paragraph.add_run("Раздел 1:")
    first_run.bold = True
    paragraph.add_run(" Основные результаты")
    second_run = paragraph.add_run(" исследования")
    second_run.bold = True
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].role == "heading"
    assert paragraphs[0].heading_level == 2
    assert build_document_text(paragraphs) == "## **Раздел 1:** Основные результаты** исследования**"


def test_extract_document_content_from_docx_preserves_hyperlinks_tabs_and_inline_emphasis():
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("До ")
    bold_run = paragraph.add_run("важно")
    bold_run.bold = True
    paragraph.add_run(" и ")
    italic_run = paragraph.add_run("курсив")
    italic_run.italic = True
    tab_run = paragraph.add_run()
    _append_tab(tab_run)
    _add_hyperlink(paragraph, "ссылка", "https://example.com")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "До **важно** и *курсив*\t[ссылка](https://example.com)"


def test_preserve_source_paragraph_properties_restores_raw_xml_paragraph_formatting():
    source_doc = Document()
    source_paragraph = source_doc.add_paragraph("Абзац")
    source_paragraph.paragraph_format.left_indent = Inches(0.5)
    source_paragraph.paragraph_format.first_line_indent = Inches(0.25)
    _set_raw_paragraph_alignment(source_paragraph, "start")

    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)
    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    target_doc.add_paragraph("Абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))
    paragraph_properties = updated_doc.paragraphs[0]._element.pPr
    assert paragraph_properties is not None
    alignment = paragraph_properties.find(qn("w:jc"))
    indentation = paragraph_properties.find(qn("w:ind"))

    assert alignment is not None
    assert alignment.get(qn("w:val")) == "start"
    assert indentation is not None
    assert indentation.get(qn("w:start")) == "720" or indentation.get(qn("w:left")) == "720"
    assert indentation.get(qn("w:firstLine")) == "360"


def test_preserve_source_paragraph_properties_logs_mismatch_warning(monkeypatch):
    source_doc = Document()
    source_paragraph = source_doc.add_paragraph("Абзац")
    source_paragraph.paragraph_format.left_indent = Inches(0.5)
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)
    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    target_doc.add_paragraph("Абзац")
    target_doc.add_paragraph("Лишний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    events = []
    monkeypatch.setattr(document, "log_event", lambda level, event, message, **context: events.append((event, context)))

    preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)

    assert events == [
        (
            "paragraph_count_mismatch_preserve",
            {"source_count": 1, "target_count": 2},
        )
    ]


def test_preserve_source_paragraph_properties_skips_partial_transfer_on_mismatch():
    source_doc = Document()
    source_paragraph = source_doc.add_paragraph("Абзац")
    source_paragraph.paragraph_format.left_indent = Inches(0.5)
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)
    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    target_doc.add_paragraph("Абзац")
    target_doc.add_paragraph("Лишний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))
    paragraph_properties = updated_doc.paragraphs[0]._element.pPr
    indentation = None if paragraph_properties is None else paragraph_properties.find(qn("w:ind"))

    assert indentation is None


def test_replace_xml_element_with_sequence_empty_replacements_is_noop():
    parent = document.etree.fromstring("<root><child>text</child></root>")
    child = parent[0]

    _replace_xml_element_with_sequence(child, [])

    assert len(parent) == 1
    assert parent[0].text == "text"


def test_validate_docx_archive_rejects_zip_slip_paths():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("../evil.txt", "boom")

    try:
        document._validate_docx_archive(buffer.getvalue())
    except RuntimeError as exc:
        assert "подозрительные пути" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for zip-slip path")


def test_resolve_image_insertions_keeps_safe_and_candidates_for_manual_review():
    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
        safe_bytes=PNG_BYTES,
        attempt_variants=[
            ImageVariantCandidate(mode="candidate1", bytes=PNG_BYTES, mime_type="image/png"),
            ImageVariantCandidate(mode="candidate2", bytes=PNG_BYTES, mime_type="image/png"),
        ],
    )
    asset.update_pipeline_metadata(preserve_all_variants_in_docx=True)

    assert resolve_image_insertions(asset) == [
        ("safe", PNG_BYTES),
        ("candidate1", PNG_BYTES),
        ("candidate2", PNG_BYTES),
    ]


def test_reinsert_inline_images_labels_manual_review_variants():
    doc = Document()
    doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    buffer = BytesIO()
    doc.save(buffer)

    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
        safe_bytes=PNG_BYTES,
        attempt_variants=[
            ImageVariantCandidate(mode="candidate1", bytes=PNG_BYTES, mime_type="image/png"),
            ImageVariantCandidate(mode="candidate2", bytes=PNG_BYTES, mime_type="image/png"),
        ],
    )
    asset.update_pipeline_metadata(preserve_all_variants_in_docx=True)

    updated_bytes = reinsert_inline_images(buffer.getvalue(), [asset])
    updated_doc = Document(BytesIO(updated_bytes))
    visible_text = "\n".join(paragraph.text for paragraph in updated_doc.paragraphs)
    visible_text += "\n" + "\n".join(
        paragraph.text
        for table in updated_doc.tables
        for row in table.rows
        for cell in row.cells
        for paragraph in cell.paragraphs
    )

    assert len(updated_doc.tables) == 1
    assert len(updated_doc.tables[0].rows[0].cells) == 3
    assert len(updated_doc.inline_shapes) == 3
    assert len(updated_doc.paragraphs) == 0
    assert "candidate1" not in visible_text
    assert "candidate2" not in visible_text
    assert _extract_docpr_descriptions(updated_doc._element) == ["safe", "candidate1", "candidate2"]


def test_normalize_semantic_output_docx_applies_semantic_styles():
    source_paragraphs = [
        ParagraphUnit(text="Глава", role="heading", heading_level=1),
        ParagraphUnit(text="[[DOCX_IMAGE_img_001]]", role="image"),
        ParagraphUnit(text="Рис. 1. Подпись", role="caption"),
        ParagraphUnit(text="Обычный текст", role="body"),
    ]
    target_doc = Document()
    target_doc.add_paragraph("Глава")
    target_doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    target_doc.add_paragraph("Рис. 1. Подпись")
    target_doc.add_paragraph("Обычный текст")
    table = target_doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "A"
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[2].style is not None
    assert updated_doc.paragraphs[3].style is not None
    assert updated_doc.tables[0].style is not None

    assert updated_doc.paragraphs[0].style.name == "Heading 1"
    assert updated_doc.paragraphs[1].alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert updated_doc.paragraphs[2].style.name == "Caption"
    assert updated_doc.paragraphs[3].style.name in {"Body Text", "Normal"}
    assert updated_doc.tables[0].style.name == "Table Grid"


def test_normalize_semantic_output_docx_logs_mismatch_warning(monkeypatch):
    source_paragraphs = [ParagraphUnit(text="Один", role="body")]
    target_doc = Document()
    target_doc.add_paragraph("Один")
    target_doc.add_paragraph("Два")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    events = []
    monkeypatch.setattr(document, "log_event", lambda level, event, message, **context: events.append((event, context)))

    normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)

    assert events == [
        (
            "paragraph_count_mismatch_normalize",
            {"source_count": 1, "target_count": 2},
        )
    ]


def test_normalize_semantic_output_docx_skips_partial_normalization_on_mismatch():
    source_paragraphs = [ParagraphUnit(text="Заголовок", role="heading", heading_level=1)]
    target_doc = Document()
    target_doc.add_paragraph("Заголовок")
    target_doc.add_paragraph("Лишний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Normal"


def test_caption_survives_extraction_markdown_and_normalization_after_image(tmp_path):
    image_path = tmp_path / "docx_caption_pipeline_image.png"
    image_path.write_bytes(PNG_BYTES)

    source_doc = Document()
    source_doc.add_paragraph().add_run().add_picture(str(image_path))
    caption = source_doc.add_paragraph(style="Caption")
    caption.add_run("Рисунок 1 Образец подписи").bold = True
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)

    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)
    markdown = build_document_text(source_paragraphs)

    target_doc = Document()
    target_doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    target_doc.add_paragraph("Рисунок 1 Образец подписи")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert [paragraph.role for paragraph in source_paragraphs] == ["image", "caption"]
    assert markdown == "[[DOCX_IMAGE_img_001]]\n\n**Рисунок 1 Образец подписи**"
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Caption"
    assert updated_doc.paragraphs[1].alignment == WD_ALIGN_PARAGRAPH.CENTER


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


def test_reinsert_inline_images_preserves_formatted_text_around_placeholder_in_same_paragraph():
    doc = Document()
    paragraph = doc.add_paragraph()
    before_run = paragraph.add_run("До ")
    before_run.bold = True
    paragraph.add_run("[[DOCX_IMAGE_img_001]]")
    after_run = paragraph.add_run(" после")
    after_run.italic = True
    buffer = BytesIO()
    doc.save(buffer)

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
    updated_paragraph = updated_doc.paragraphs[0]

    assert updated_paragraph.text == "До  после"
    assert updated_paragraph.runs[0].text == "До "
    assert updated_paragraph.runs[0].bold is True
    assert updated_paragraph.runs[-1].text == " после"
    assert updated_paragraph.runs[-1].italic is True
    assert len(updated_doc.inline_shapes) == 1


def test_reinsert_inline_images_uses_shared_table_layout_for_multi_variant_placeholder_inside_paragraph():
    doc = Document()
    paragraph = doc.add_paragraph()
    before_run = paragraph.add_run("До ")
    before_run.bold = True
    paragraph.add_run("[[DOCX_IMAGE_img_001]]")
    after_run = paragraph.add_run(" после")
    after_run.italic = True
    buffer = BytesIO()
    doc.save(buffer)

    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
        safe_bytes=PNG_BYTES,
        attempt_variants=[
            ImageVariantCandidate(mode="candidate1", bytes=PNG_BYTES, mime_type="image/png"),
            ImageVariantCandidate(mode="candidate2", bytes=PNG_BYTES, mime_type="image/png"),
        ],
    )
    asset.update_pipeline_metadata(preserve_all_variants_in_docx=True)

    updated_bytes = reinsert_inline_images(buffer.getvalue(), [asset])
    updated_doc = Document(BytesIO(updated_bytes))

    assert [paragraph.text for paragraph in updated_doc.paragraphs] == ["До ", " после"]
    assert updated_doc.paragraphs[0].runs[0].bold is True
    assert updated_doc.paragraphs[1].runs[0].italic is True
    assert len(updated_doc.tables) == 1
    assert len(updated_doc.tables[0].rows[0].cells) == 3
    assert len(updated_doc.inline_shapes) == 3
    assert _extract_docpr_descriptions(updated_doc._element) == ["safe", "candidate1", "candidate2"]


def test_build_variant_table_element_returns_none_for_empty_insertions(monkeypatch):
    doc = Document()
    paragraph = doc.add_paragraph("placeholder")
    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
    )

    monkeypatch.setattr(document, "resolve_image_insertions", lambda current_asset: [])

    assert _build_variant_table_element(paragraph, asset) is None


def test_reinsert_inline_images_keeps_placeholder_text_when_no_image_bytes_resolved():
    doc = Document()
    doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    buffer = BytesIO()
    doc.save(buffer)

    updated_bytes = reinsert_inline_images(
        buffer.getvalue(),
        [
            ImageAsset(
                image_id="img_001",
                placeholder="[[DOCX_IMAGE_img_001]]",
                original_bytes=b"",
                mime_type="image/png",
                position_index=0,
                final_variant="original",
            )
        ],
    )
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].text == "[[DOCX_IMAGE_img_001]]"
    assert len(updated_doc.inline_shapes) == 0


def test_reinsert_inline_images_replaces_placeholder_with_picture_inside_table_cell():
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).paragraphs[0].add_run("[[DOCX_IMAGE_img_001]]")
    buffer = BytesIO()
    doc.save(buffer)

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
    cell_paragraph = updated_doc.tables[0].cell(0, 0).paragraphs[0]

    assert cell_paragraph.text == ""
    assert len(updated_doc.inline_shapes) == 1
    assert updated_doc.inline_shapes[0].width == 914400
    assert updated_doc.inline_shapes[0].height == 914400


def test_reinsert_inline_images_replaces_placeholder_with_picture_inside_nested_table_cell():
    doc = Document()
    outer_table = doc.add_table(rows=1, cols=1)
    nested_table = outer_table.cell(0, 0).add_table(rows=1, cols=1)
    nested_table.cell(0, 0).paragraphs[0].add_run("[[DOCX_IMAGE_img_001]]")
    buffer = BytesIO()
    doc.save(buffer)

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
    nested_cell_paragraph = updated_doc.tables[0].cell(0, 0).tables[0].cell(0, 0).paragraphs[0]

    assert nested_cell_paragraph.text == ""
    assert len(updated_doc.inline_shapes) == 1
    assert updated_doc.inline_shapes[0].width == 914400
    assert updated_doc.inline_shapes[0].height == 914400


def test_reinsert_inline_images_replaces_placeholder_split_across_runs_without_plain_text_fallback():
    doc = Document()
    paragraph = doc.add_paragraph()
    first_run = paragraph.add_run("До [[DOCX_")
    first_run.bold = True
    second_run = paragraph.add_run("IMAGE_img_001]] после")
    second_run.italic = True
    buffer = BytesIO()
    doc.save(buffer)

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
    updated_paragraph = updated_doc.paragraphs[0]

    assert updated_paragraph.text == "До  после"
    assert updated_paragraph.runs[0].text == "До "
    assert updated_paragraph.runs[0].bold is True
    assert updated_paragraph.runs[-1].text == " после"
    assert updated_paragraph.runs[-1].italic is True
    assert len(updated_doc.inline_shapes) == 1


def test_reinsert_inline_images_uses_shared_table_layout_for_split_run_multi_variant_placeholder():
    doc = Document()
    paragraph = doc.add_paragraph()
    first_run = paragraph.add_run("До [[DOCX_")
    first_run.bold = True
    second_run = paragraph.add_run("IMAGE_img_001]] после")
    second_run.italic = True
    buffer = BytesIO()
    doc.save(buffer)

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

    assert [paragraph.text for paragraph in updated_doc.paragraphs] == ["До ", " после"]
    assert updated_doc.paragraphs[0].runs[0].bold is True
    assert updated_doc.paragraphs[1].runs[0].italic is True
    assert len(updated_doc.tables) == 1
    assert len(updated_doc.tables[0].rows[0].cells) == 3
    assert len(updated_doc.inline_shapes) == 3
    assert _extract_docpr_descriptions(updated_doc._element) == [
        "Вариант 1: Просто улучшить",
        "Вариант 2: Креативная AI-перерисовка",
        "Вариант 3: Структурная AI-перерисовка",
    ]


def test_reinsert_inline_images_replaces_placeholder_in_header_and_footer():
    doc = Document()
    section = doc.sections[0]
    section.header.paragraphs[0].add_run("[[DOCX_IMAGE_img_001]]")
    section.footer.paragraphs[0].add_run("[[DOCX_IMAGE_img_001]]")
    buffer = BytesIO()
    doc.save(buffer)

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

    header_xml = updated_doc.sections[0].header._element.xml
    footer_xml = updated_doc.sections[0].footer._element.xml

    assert "[[DOCX_IMAGE_img_001]]" not in header_xml
    assert "[[DOCX_IMAGE_img_001]]" not in footer_xml
    assert "a:blip" in header_xml
    assert "a:blip" in footer_xml


def test_reinsert_inline_images_replaces_placeholder_inside_textbox():
    doc = Document()
    host_paragraph = doc.add_paragraph("Перед textbox")
    _append_textbox_with_text(host_paragraph, "[[DOCX_IMAGE_img_001]]")
    buffer = BytesIO()
    doc.save(buffer)

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
    document_xml = updated_doc._element.xml

    assert "[[DOCX_IMAGE_img_001]]" not in document_xml
    assert "w:txbxContent" in document_xml
    assert "a:blip" in document_xml


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
    visible_text = "\n".join(paragraph.text for paragraph in updated_doc.paragraphs)
    visible_text += "\n" + "\n".join(
        paragraph.text
        for table in updated_doc.tables
        for row in table.rows
        for cell in row.cells
        for paragraph in cell.paragraphs
    )

    assert len(updated_doc.inline_shapes) == 3
    assert len(updated_doc.tables) == 1
    assert len(updated_doc.tables[0].rows[0].cells) == 3
    assert [paragraph.text for paragraph in updated_doc.paragraphs] == ["До", "После"]
    assert "Вариант 1: Просто улучшить" not in visible_text
    assert "Вариант 2: Креативная AI-перерисовка" not in visible_text
    assert "Вариант 3: Структурная AI-перерисовка" not in visible_text
    assert _extract_docpr_descriptions(updated_doc._element) == [
        "Вариант 1: Просто улучшить",
        "Вариант 2: Креативная AI-перерисовка",
        "Вариант 3: Структурная AI-перерисовка",
    ]


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
