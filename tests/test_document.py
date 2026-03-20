import base64
import json
import zipfile
from io import BytesIO
from typing import Any, cast

import document
import formatting_transfer
import image_reinsertion
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Inches

from document import (
    build_marker_wrapped_block_text,
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    extract_document_content_from_docx,
    inspect_placeholder_integrity,
)
from formatting_transfer import (
    normalize_semantic_output_docx,
    preserve_source_paragraph_properties,
)
from image_reinsertion import (
    _build_variant_table_element,
    _replace_xml_element_with_sequence,
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


def _extract_numbering_ids(paragraph) -> tuple[str | None, str | None]:
    paragraph_properties = paragraph._element.pPr
    if paragraph_properties is None:
        return None, None
    num_pr = paragraph_properties.find(qn("w:numPr"))
    if num_pr is None:
        return None, None
    ilvl = num_pr.find(qn("w:ilvl"))
    num_id = num_pr.find(qn("w:numId"))
    return (
        None if ilvl is None else ilvl.get(qn("w:val")),
        None if num_id is None else num_id.get(qn("w:val")),
    )


def _numbering_root_contains_num_id(document: Document, num_id: str) -> bool:
    numbering_root = document.part.numbering_part.element
    for child in numbering_root:
        if child.tag == qn("w:num") and child.get(qn("w:numId")) == num_id:
            abstract_num = child.find(qn("w:abstractNumId"))
            if abstract_num is None:
                return False
            abstract_num_id = abstract_num.get(qn("w:val"))
            return any(
                candidate.tag == qn("w:abstractNum") and candidate.get(qn("w:abstractNumId")) == abstract_num_id
                for candidate in numbering_root
            )
    return False


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


def test_build_semantic_blocks_keeps_consecutive_headings_with_following_body():
    paragraphs = [
        ParagraphUnit(text="Глава 1", role="heading", heading_level=1),
        ParagraphUnit(text="Раздел 1.1", role="heading", heading_level=2),
        ParagraphUnit(text="Первый содержательный абзац после цепочки заголовков.", role="body"),
        ParagraphUnit(text="Следующий абзац уже должен перейти в отдельный блок из-за лимита.", role="body"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=90)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Глава 1",
        "Раздел 1.1",
        "Первый содержательный абзац после цепочки заголовков.",
    ]
    assert blocks[1].text == "Следующий абзац уже должен перейти в отдельный блок из-за лимита."


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


def test_build_editing_jobs_marks_image_only_blocks_as_passthrough():
    paragraphs = [
        ParagraphUnit(text="Вступление", role="body"),
        ParagraphUnit(text="[[DOCX_IMAGE_img_001]]", role="image"),
        ParagraphUnit(text="Основной текст", role="body"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=20)
    jobs = build_editing_jobs(blocks, max_chars=3000)

    assert [job["target_text"] for job in jobs] == ["Вступление", "[[DOCX_IMAGE_img_001]]", "Основной текст"]
    assert [job["job_kind"] for job in jobs] == ["llm", "passthrough", "llm"]
    assert jobs[0]["paragraph_ids"] == ["p0000"]
    assert str(jobs[1]["target_text_with_markers"]).startswith("[[DOCX_PARA_p0001]]")


def test_build_marker_wrapped_block_text_preserves_paragraph_ids_and_boundaries():
    paragraphs = [
        ParagraphUnit(text="Глава", role="heading", paragraph_id="p0001", heading_level=1),
        ParagraphUnit(text="Основной текст", role="body", paragraph_id="p0002"),
    ]

    result = build_marker_wrapped_block_text(paragraphs)

    assert result == "[[DOCX_PARA_p0001]]\n# Глава\n\n[[DOCX_PARA_p0002]]\nОсновной текст"


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
    assert paragraphs[1].asset_id == "img_001"
    assert [paragraph.paragraph_id for paragraph in paragraphs] == ["p0000", "p0001", "p0002"]
    assert [paragraph.source_index for paragraph in paragraphs] == [0, 1, 2]
    assert [paragraph.structural_role for paragraph in paragraphs] == ["body", "image", "body"]
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
    assert paragraphs[1].list_numbering_format is not None
    assert paragraphs[1].list_num_id is not None
    assert paragraphs[1].list_abstract_num_id is not None
    assert paragraphs[1].list_num_xml is not None
    assert paragraphs[1].list_abstract_num_xml is not None
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
    assert [paragraph.role_confidence for paragraph in paragraphs] == ["explicit", "adjacent"]
    assert paragraphs[0].asset_id == "img_001"
    assert paragraphs[1].attached_to_asset_id == "img_001"


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
    assert paragraphs[1].role_confidence == "explicit"
    assert paragraphs[1].attached_to_asset_id == "img_001"
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
    assert paragraphs[0].asset_id == "table_001"
    assert paragraphs[1].attached_to_asset_id == "table_001"


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
    assert paragraphs[1].attached_to_asset_id == "table_001"
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


def test_extract_document_content_from_docx_does_not_promote_centered_bold_body_without_text_signal():
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("Краткое описание установки")
    run.bold = True
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].role == "body"
    assert paragraphs[0].heading_level is None
    assert paragraphs[0].role_confidence == "heuristic"


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
    monkeypatch.setattr(formatting_transfer, "log_event", lambda level, event, message, **context: events.append((event, context)))

    preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)

    assert len(events) == 1
    event_name, context = events[0]
    assert event_name == "paragraph_count_mismatch_preserve"
    assert context["source_count"] == 1
    assert context["target_count"] == 2
    assert context["mapped_count"] == 1
    assert context["unmapped_source_count"] == 0
    assert context["unmapped_target_count"] == 1
    assert isinstance(context["artifact_path"], str)


def test_preserve_source_paragraph_properties_applies_partial_transfer_on_mismatch():
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
    first_paragraph_properties = updated_doc.paragraphs[0]._element.pPr
    first_indentation = None if first_paragraph_properties is None else first_paragraph_properties.find(qn("w:ind"))
    second_paragraph_properties = updated_doc.paragraphs[1]._element.pPr
    second_indentation = None if second_paragraph_properties is None else second_paragraph_properties.find(qn("w:ind"))

    assert first_indentation is not None
    assert second_indentation is None


def test_preserve_source_paragraph_properties_artifact_records_caption_heading_conflict(tmp_path, monkeypatch):
    image_path = tmp_path / "artifact_caption_image.png"
    image_path.write_bytes(PNG_BYTES)

    source_doc = Document()
    source_doc.add_paragraph().add_run().add_picture(str(image_path))
    source_caption = source_doc.add_paragraph("Рис. 1. Подпись к изображению")
    source_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)
    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    target_doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    target_doc.add_paragraph("Рис. 1. Подпись к изображению", style="Heading 1")
    target_doc.add_paragraph("Лишний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    diagnostics_dir = tmp_path / "formatting_diagnostics"
    monkeypatch.setattr(formatting_transfer, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)

    preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)

    artifacts = sorted(diagnostics_dir.glob("*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert len(payload["caption_heading_conflicts"]) == 1
    assert payload["caption_heading_conflicts"][0]["target_style_name"] == "Heading 1"
    assert payload["caption_heading_conflicts"][0]["target_heading_level"] == 1


def test_normalize_semantic_output_docx_artifact_records_list_restoration_decisions(tmp_path, monkeypatch):
    source_doc = Document()
    source_doc.add_paragraph("Первый пункт", style="List Number")
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)
    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    target_doc.add_paragraph("Первый пункт")
    target_doc.add_paragraph("Лишний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    diagnostics_dir = tmp_path / "formatting_diagnostics"
    monkeypatch.setattr(formatting_transfer, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)

    updated_bytes = normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)

    updated_doc = Document(BytesIO(updated_bytes))
    assert _extract_numbering_ids(updated_doc.paragraphs[0])[1] is not None
    artifacts = sorted(diagnostics_dir.glob("*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["list_restoration_decisions"][0]["action"] == "restored"


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


def test_validate_docx_archive_rejects_oversized_archive_bytes(monkeypatch):
    monkeypatch.setattr(document, "MAX_DOCX_ARCHIVE_SIZE_BYTES", 5)

    try:
        document._validate_docx_archive(b"123456")
    except RuntimeError as exc:
        assert "превышает допустимый размер архива" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for oversized DOCX archive")


def test_validate_docx_archive_rejects_bad_zip_payload():
    try:
        document._validate_docx_archive(b"not-a-zip")
    except RuntimeError as exc:
        assert "поврежденный или неподдерживаемый DOCX-архив" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for invalid DOCX archive")


def test_validate_docx_archive_rejects_empty_archive():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w"):
        pass

    try:
        document._validate_docx_archive(buffer.getvalue())
    except RuntimeError as exc:
        assert "пустой DOCX-архив" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for empty DOCX archive")


def test_validate_docx_archive_rejects_too_many_entries(monkeypatch):
    monkeypatch.setattr(document, "MAX_DOCX_ENTRY_COUNT", 1)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")

    try:
        document._validate_docx_archive(buffer.getvalue())
    except RuntimeError as exc:
        assert "слишком много файлов" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for excessive DOCX entry count")


def test_validate_docx_archive_rejects_suspicious_compression_ratio(monkeypatch):
    monkeypatch.setattr(document, "MAX_DOCX_COMPRESSION_RATIO", 1)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "A" * 2048)
        archive.writestr("word/document.xml", "B" * 2048)

    try:
        document._validate_docx_archive(buffer.getvalue())
    except RuntimeError as exc:
        assert "подозрительно высокий коэффициент сжатия" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for suspicious DOCX compression ratio")


def test_validate_docx_archive_rejects_absolute_paths():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("/word/document.xml", "boom")

    try:
        document._validate_docx_archive(buffer.getvalue())
    except RuntimeError as exc:
        assert "абсолютные пути" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for absolute path in DOCX archive")


def test_validate_docx_archive_rejects_missing_content_types():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")

    try:
        document._validate_docx_archive(buffer.getvalue())
    except RuntimeError as exc:
        assert "отсутствует [Content_Types].xml" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for missing [Content_Types].xml")


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
    monkeypatch.setattr(formatting_transfer, "log_event", lambda level, event, message, **context: events.append((event, context)))

    normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)

    assert len(events) == 1
    event_name, context = events[0]
    assert event_name == "paragraph_count_mismatch_normalize"
    assert context["source_count"] == 1
    assert context["target_count"] == 2
    assert context["mapped_count"] == 1
    assert context["unmapped_source_count"] == 0
    assert context["unmapped_target_count"] == 1
    assert isinstance(context["artifact_path"], str)


def test_normalize_semantic_output_docx_applies_partial_normalization_on_mismatch():
    source_paragraphs = [ParagraphUnit(text="Заголовок", role="heading", heading_level=1)]
    target_doc = Document()
    target_doc.add_paragraph("Заголовок")
    target_doc.add_paragraph("Лишний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Heading 1"
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Normal"


def test_normalize_semantic_output_docx_similarity_mapping_restores_caption_when_text_changes_slightly():
    source_paragraphs = [ParagraphUnit(text="Рис. 1. Подпись к изображению", role="caption")]
    target_doc = Document()
    target_doc.add_paragraph("Рисунок 1 Подпись к изображению")
    target_doc.add_paragraph("Посторонний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Caption"
    assert updated_doc.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_normalize_semantic_output_docx_uses_generated_paragraph_registry_for_marker_anchored_mapping():
    source_paragraphs = [
        ParagraphUnit(text="Старый заголовок", role="heading", heading_level=1, paragraph_id="p0000"),
    ]
    target_doc = Document()
    target_doc.add_paragraph("Совершенно новый заголовок")
    target_doc.add_paragraph("Лишний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(
        target_buffer.getvalue(),
        source_paragraphs,
        generated_paragraph_registry=[{"paragraph_id": "p0000", "text": "Совершенно новый заголовок"}],
    )
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Heading 1"
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Normal"


def test_normalize_semantic_output_docx_uses_generated_registry_similarity_for_near_position_body_mapping():
    source_paragraphs = [
        ParagraphUnit(text="Исходный абзац сильно отличается", role="body", paragraph_id="p0010"),
    ]
    target_doc = Document()
    target_doc.add_paragraph("Лишний абзац перед целью")
    target_doc.add_paragraph("Итоговый литературно отредактированный абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(
        target_buffer.getvalue(),
        source_paragraphs,
        generated_paragraph_registry=[
            {"paragraph_id": "p0010", "text": "Итоговый литературно отредактированный абзац"}
        ],
    )
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Normal"
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Body Text"


def test_normalize_semantic_output_docx_maps_body_to_generated_non_heading_lines():
    source_paragraphs = [
        ParagraphUnit(text="Старый слитый абзац", role="body", paragraph_id="p0056"),
    ]
    target_doc = Document()
    target_doc.add_paragraph("Новый заголовок", style="Heading 3")
    target_doc.add_paragraph("Текст после нового заголовка")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(
        target_buffer.getvalue(),
        source_paragraphs,
        generated_paragraph_registry=[
            {"paragraph_id": "p0056", "text": "### Новый заголовок\nТекст после нового заголовка"}
        ],
    )
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Heading 3"
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Body Text"


def test_normalize_semantic_output_docx_does_not_apply_positional_mapping_on_equal_count_reorder():
    source_paragraphs = [
        ParagraphUnit(text="Заголовок", role="heading", heading_level=1),
        ParagraphUnit(text="Обычный текст", role="body"),
    ]
    target_doc = Document()
    target_doc.add_paragraph("Обычный текст")
    target_doc.add_paragraph("Заголовок")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name in {"Body Text", "Normal"}
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Heading 1"


def test_normalize_semantic_output_docx_restores_real_word_numbering_for_mapped_lists():
    source_doc = Document()
    source_doc.add_paragraph("Первый пункт", style="List Number")
    source_doc.add_paragraph("Второй пункт", style="List Number")
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)

    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    target_doc.add_paragraph("Первый пункт")
    target_doc.add_paragraph("Второй пункт")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    first_ilvl, first_num_id = _extract_numbering_ids(updated_doc.paragraphs[0])
    second_ilvl, second_num_id = _extract_numbering_ids(updated_doc.paragraphs[1])

    assert updated_doc.paragraphs[0].style.name == "List Paragraph"
    assert updated_doc.paragraphs[1].style.name == "List Paragraph"
    assert first_ilvl == "0"
    assert second_ilvl == "0"
    assert first_num_id is not None
    assert second_num_id == first_num_id
    assert _numbering_root_contains_num_id(updated_doc, first_num_id)


def test_normalize_semantic_output_docx_restores_real_word_numbering_on_partial_mapping_mismatch():
    source_doc = Document()
    source_doc.add_paragraph("Первый пункт", style="List Number")
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)

    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    target_doc.add_paragraph("Первый пункт")
    target_doc.add_paragraph("Лишний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = normalize_semantic_output_docx(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    ilvl, num_id = _extract_numbering_ids(updated_doc.paragraphs[0])

    assert updated_doc.paragraphs[0].style.name == "List Paragraph"
    assert ilvl == "0"
    assert num_id is not None
    assert _numbering_root_contains_num_id(updated_doc, num_id)
    assert _extract_numbering_ids(updated_doc.paragraphs[1]) == (None, None)


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


def test_reinsert_inline_images_preserves_hyperlink_xml_when_placeholder_is_in_same_paragraph():
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("До ")
    _add_hyperlink(paragraph, "ссылка", "https://example.com")
    paragraph.add_run(" [[DOCX_")
    paragraph.add_run("IMAGE_img_001]] после")
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

    assert "[[DOCX_IMAGE_img_001]]" not in updated_paragraph.text
    assert "ссылка" in updated_paragraph.text
    assert "после" in updated_paragraph.text
    assert len(updated_doc.inline_shapes) == 1
    assert len(updated_paragraph._element.xpath("./w:hyperlink")) == 1


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


def test_reinsert_inline_images_preserves_hyperlink_when_multi_variant_table_is_inserted_nearby():
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("До ")
    _add_hyperlink(paragraph, "ссылка", "https://example.com")
    paragraph.add_run(" [[DOCX_IMAGE_img_001]] после")
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

    assert "ссылка" in visible_text
    assert "после" in visible_text
    assert len(updated_doc.tables) == 1
    assert len(updated_doc.tables[0].rows[0].cells) == 3
    assert len(updated_doc.inline_shapes) == 3
    assert len(updated_doc._element.xpath(".//w:hyperlink")) == 1
    assert _extract_docpr_descriptions(updated_doc._element) == ["safe", "candidate1", "candidate2"]


def test_reinsert_inline_images_logs_warning_when_all_replacement_strategies_fail(monkeypatch):
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
    )

    events = []
    monkeypatch.setattr(image_reinsertion, "_replace_multi_variant_placeholders_with_tables", lambda paragraph, asset_map: False)
    monkeypatch.setattr(image_reinsertion, "_replace_run_level_placeholders", lambda paragraph, placeholders, asset_map: False)
    monkeypatch.setattr(image_reinsertion, "_replace_multi_run_placeholders", lambda paragraph, asset_map: False)
    monkeypatch.setattr(image_reinsertion, "_replace_paragraph_placeholders_fallback", lambda paragraph, paragraph_text, asset_map: False)
    monkeypatch.setattr(image_reinsertion, "log_event", lambda level, event, message, **context: events.append((event, context)))

    updated_bytes = reinsert_inline_images(buffer.getvalue(), [asset])
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].text == "[[DOCX_IMAGE_img_001]]"
    assert events == [
        (
            "image_reinsertion_placeholder_unhandled",
            {
                "placeholder_count": 1,
                "placeholders": ["[[DOCX_IMAGE_img_001]]"],
                "paragraph_text_preview": "[[DOCX_IMAGE_img_001]]",
            },
        )
    ]


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

    monkeypatch.setattr(image_reinsertion, "resolve_image_insertions", lambda current_asset: [])

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
