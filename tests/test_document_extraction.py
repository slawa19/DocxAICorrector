import base64
import zipfile
from io import BytesIO
from typing import Any, cast

import pytest

import document
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from document import (
    build_document_text,
    build_marker_wrapped_block_text,
    extract_document_content_from_docx,
    inspect_placeholder_integrity,
    paragraph_has_strong_heading_format,
    resolve_effective_paragraph_font_size,
)
from models import ImageAsset, ParagraphUnit


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


def _append_textbox_with_paragraphs(paragraph, texts: list[str]) -> None:
    textbox_paragraphs = "".join(
        f"""
        <w:p>
            <w:r>
                <w:t>{text}</w:t>
            </w:r>
        </w:p>
        """
        for text in texts
    )
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
                                            {textbox_paragraphs}
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


def _set_style_alignment(style, value: str) -> None:
    style_properties = style._element.get_or_add_pPr()
    alignment = style_properties.find(qn("w:jc"))
    if alignment is None:
        alignment = OxmlElement("w:jc")
        style_properties.append(alignment)
    alignment.set(qn("w:val"), value)


def _extract_source_rects(element) -> list[dict[str, str]]:
    return [
        {key: src_rect.get(key) for key in ("l", "t", "r", "b") if src_rect.get(key) is not None}
        for src_rect in element.xpath(".//a:srcRect")
    ]


def _make_docx_with_emdash_bullet_numbering(texts: list[str]) -> BytesIO:
    """Create a DOCX where 'List Paragraph' paragraphs use em-dash (U+2014) as bullet char."""
    doc = Document()
    doc.add_paragraph("Обычный текст перед списком.")

    numbering_part = doc.part.numbering_part
    numbering_root = numbering_part._element

    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), "900")
    lvl = OxmlElement("w:lvl")
    lvl.set(qn("w:ilvl"), "0")
    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), "bullet")
    lvl.append(num_fmt)
    lvl_text = OxmlElement("w:lvlText")
    lvl_text.set(qn("w:val"), "\u2014")
    lvl.append(lvl_text)
    abstract_num.append(lvl)
    numbering_root.append(abstract_num)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), "900")
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), "900")
    num.append(abstract_ref)
    numbering_root.append(num)

    for text in texts:
        para = doc.add_paragraph(text, style="List Paragraph")
        paragraph_properties = para._element.find(qn("w:pPr"))
        if paragraph_properties is None:
            paragraph_properties = OxmlElement("w:pPr")
            para._element.insert(0, paragraph_properties)
        num_pr = OxmlElement("w:numPr")
        ilvl = OxmlElement("w:ilvl")
        ilvl.set(qn("w:val"), "0")
        num_id = OxmlElement("w:numId")
        num_id.set(qn("w:val"), "900")
        num_pr.append(ilvl)
        num_pr.append(num_id)
        paragraph_properties.append(num_pr)

    doc.add_paragraph("Обычный текст после.")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def test_extract_document_content_from_docx_merges_false_body_boundary_in_public_api():
    doc = Document()
    doc.add_paragraph("архетипами: повторяющимися моделями")
    doc.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "архетипами: повторяющимися моделями поведения во времени, наблюдаемыми в разных системах."
    assert paragraphs[0].origin_raw_indexes == [0, 1]
    assert build_marker_wrapped_block_text(paragraphs) == (
        f"[[DOCX_PARA_{paragraphs[0].paragraph_id}]]\n"
        "архетипами: повторяющимися моделями поведения во времени, наблюдаемыми в разных системах."
    )


def test_extract_document_content_from_docx_flattens_inline_break_wrapped_prose():
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("For centuries, economists and policymakers")
    paragraph.add_run().add_break()
    paragraph.add_run("divided activities by whether they created value.")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].text == (
        "For centuries, economists and policymakers divided activities by whether they created value."
    )


def test_extract_document_content_from_docx_drops_break_only_spacer_paragraphs():
    doc = Document()
    doc.add_paragraph("Before")
    spacer = doc.add_paragraph()
    spacer.add_run().add_break()
    doc.add_paragraph("After")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.text for paragraph in paragraphs] == ["Before", "After"]


def test_extract_document_content_from_docx_extracts_textbox_paragraphs():
    doc = Document()
    doc.add_paragraph("Before")
    host = doc.add_paragraph()
    _append_textbox_with_paragraphs(host, ["Inside text box", "Second textbox paragraph"])
    doc.add_paragraph("Middle")
    doc.add_paragraph("After")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, image_assets = extract_document_content_from_docx(buffer)

    assert [paragraph.text for paragraph in paragraphs] == [
        "Before Inside text box Second textbox paragraph Middle",
        "After",
    ]
    assert image_assets == []


def test_extract_document_content_from_docx_deduplicates_adjacent_textbox_paragraphs():
    doc = Document()
    host = doc.add_paragraph()
    _append_textbox_with_paragraphs(host, ["Duplicated line", "Duplicated line", "Next line"])
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.text for paragraph in paragraphs] == ["Duplicated line", "Next line"]


def test_extract_document_content_from_docx_splits_toc_like_inline_break_cluster_and_marks_toc_roles():
    doc = Document()
    doc.add_paragraph("Contents")
    paragraph = doc.add_paragraph()
    paragraph.add_run("Common Critiques of Value Extraction")
    paragraph.add_run().add_break()
    paragraph.add_run("What is Value?")
    paragraph.add_run().add_break()
    paragraph.add_run("Meet the Production Boundary")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.text for paragraph in paragraphs] == [
        "Contents",
        "Common Critiques of Value Extraction",
        "What is Value?",
        "Meet the Production Boundary",
    ]
    assert [paragraph.structural_role for paragraph in paragraphs] == [
        "toc_header",
        "toc_entry",
        "toc_entry",
        "toc_entry",
    ]


def test_extract_document_content_from_docx_splits_compact_toc_run_clusters_without_explicit_breaks():
    doc = Document()
    doc.add_paragraph("Contents")
    paragraph = doc.add_paragraph()
    paragraph.add_run("Banks and Financial Markets Become Allies")
    paragraph.add_run(" ")
    paragraph.add_run("The Banking Problem")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.text for paragraph in paragraphs] == [
        "Contents",
        "Banks and Financial Markets Become Allies",
        "The Banking Problem",
    ]
    assert [paragraph.structural_role for paragraph in paragraphs] == [
        "toc_header",
        "toc_entry",
        "toc_entry",
    ]


def test_extract_document_content_from_docx_splits_long_two_entry_compact_toc_run_clusters():
    doc = Document()
    doc.add_paragraph("Contents")
    paragraph = doc.add_paragraph()
    paragraph.add_run("Something Odd About the National Accounts: GDP Facit Saltus!")
    paragraph.add_run(" ")
    paragraph.add_run("Patching Up the National Accounts isn't Enough")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.text for paragraph in paragraphs] == [
        "Contents",
        "Something Odd About the National Accounts: GDP Facit Saltus!",
        "Patching Up the National Accounts isn't Enough",
    ]
    assert [paragraph.structural_role for paragraph in paragraphs] == [
        "toc_header",
        "toc_entry",
        "toc_entry",
    ]


def test_extract_document_content_from_docx_keeps_regular_body_run_clusters_as_one_paragraph():
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("Market failures")
    paragraph.add_run(" ")
    paragraph.add_run("matter here")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.text for paragraph in paragraphs] == ["Market failures matter here"]


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


def test_extract_document_content_from_docx_populates_image_asset_payload_fields(tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(PNG_BYTES)
    doc = Document()
    doc.add_paragraph().add_run().add_picture(str(image_path), width=Inches(1.25))
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, image_assets = extract_document_content_from_docx(buffer)

    assert [paragraph.text for paragraph in paragraphs] == ["[[DOCX_IMAGE_img_001]]"]
    assert len(image_assets) == 1
    asset = image_assets[0]
    assert asset.original_bytes == PNG_BYTES
    assert asset.position_index == 0
    assert asset.placeholder == "[[DOCX_IMAGE_img_001]]"
    assert asset.image_id == "img_001"
    assert asset.width_emu is not None
    assert asset.height_emu is not None


def test_extract_document_content_from_docx_captures_source_rect_forensics(tmp_path):
    image_path = tmp_path / "cropped-image.png"
    image_path.write_bytes(PNG_BYTES)

    doc = Document()
    run = doc.add_paragraph().add_run()
    run.add_picture(str(image_path), width=Inches(1.25))
    blip_fill = run._element.xpath(".//pic:blipFill")[0]
    source_rect = OxmlElement("a:srcRect")
    source_rect.set("l", "1250")
    source_rect.set("t", "2500")
    source_rect.set("r", "3750")
    source_rect.set("b", "5000")
    blip = blip_fill.xpath("./a:blip")[0]
    blip.addnext(source_rect)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    _, image_assets = extract_document_content_from_docx(buffer)

    assert image_assets[0].source_forensics["source_rect"] == {
        "l": 1250,
        "t": 2500,
        "r": 3750,
        "b": 5000,
    }
    assert "<wp:inline" in str(image_assets[0].source_forensics["drawing_container_xml"])


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
        "  - Подпункт"
    )


def test_build_document_text_renders_nested_ordered_lists_with_markdown_safe_indent():
    nested_ordered = ParagraphUnit(text="Вложенный пункт", role="list", list_kind="ordered", list_level=1)
    deeper_unordered = ParagraphUnit(text="Глубже", role="list", list_kind="unordered", list_level=2)

    assert nested_ordered.rendered_text == "  1. Вложенный пункт"
    assert deeper_unordered.rendered_text == "    - Глубже"


def test_build_document_text_does_not_duplicate_existing_list_markers():
    paragraphs = [
        ParagraphUnit(text="1. Уже размеченный пункт", role="list", list_kind="ordered"),
        ParagraphUnit(text="- Уже размеченный маркер", role="list", list_kind="unordered"),
    ]

    assert build_document_text(paragraphs) == "1. Уже размеченный пункт\n\n- Уже размеченный маркер"


def test_public_paragraph_helper_exports_match_heading_and_font_detection():
    doc = Document()
    paragraph = doc.add_paragraph("Ключевой раздел")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.runs[0].font.size = Pt(15)

    assert paragraph_has_strong_heading_format(paragraph) is True
    assert resolve_effective_paragraph_font_size(paragraph) == 15.0


def test_build_document_text_renders_epigraph_and_attribution_as_blockquotes():
    paragraphs = [
        ParagraphUnit(text="Богатство заключается в свободе желаний.", role="body", structural_role="epigraph"),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution"),
        ParagraphUnit(text="Обычный абзац.", role="body", structural_role="body"),
    ]

    assert build_document_text(paragraphs) == (
        "> Богатство заключается в свободе желаний.\n\n"
        "> — Эпиктет\n\n"
        "Обычный абзац."
    )


def test_build_document_text_does_not_duplicate_existing_blockquote_prefixes_for_epigraph_roles():
    paragraphs = [
        ParagraphUnit(text="> Уже оформленная цитата", role="body", structural_role="epigraph"),
        ParagraphUnit(text="> — Уже оформленный автор", role="body", structural_role="attribution"),
    ]

    assert build_document_text(paragraphs) == "> Уже оформленная цитата\n\n> — Уже оформленный автор"


def test_build_marker_wrapped_block_text_preserves_blockquote_rendering_for_epigraph_roles():
    paragraphs = [
        ParagraphUnit(text="Богатство заключается в свободе желаний.", role="body", structural_role="epigraph", paragraph_id="p0001"),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0002"),
    ]

    assert build_marker_wrapped_block_text(paragraphs) == (
        "[[DOCX_PARA_p0001]]\n> Богатство заключается в свободе желаний.\n\n"
        "[[DOCX_PARA_p0002]]\n> — Эпиктет"
    )


def test_emdash_bullet_paragraphs_are_not_classified_as_list():
    """Em-dash (—) bullet in OOXML numbering is Russian typographic convention, not a real list."""
    buffer = _make_docx_with_emdash_bullet_numbering([
        "Американская торговая палата тратит на лоббизм больше всех.",
        "Эти многоплановые усилия — прерогатива местных сообществ.",
    ])

    paragraphs, _ = extract_document_content_from_docx(buffer)

    emdash_paras = [p for p in paragraphs if "торговая палата" in p.text or "многоплановые" in p.text]
    assert len(emdash_paras) == 2
    for paragraph in emdash_paras:
        assert paragraph.role == "body", f"Expected role='body', got '{paragraph.role}' for: {paragraph.text[:60]}"
        assert paragraph.list_kind is None
        assert paragraph.list_num_xml is None
        assert paragraph.list_abstract_num_xml is None


def test_emdash_bullet_paragraphs_render_without_list_markers():
    """Paragraphs demoted from em-dash bullet should render as plain text, no '- ' prefix."""
    buffer = _make_docx_with_emdash_bullet_numbering(["Цитата из книги."])

    paragraphs, _ = extract_document_content_from_docx(buffer)

    quote_para = [p for p in paragraphs if "Цитата" in p.text][0]
    assert quote_para.role == "body"
    text = build_document_text([quote_para])
    assert not text.startswith("- ")
    assert not text.startswith("— ")


def test_classify_paragraph_role_does_not_treat_emdash_prefix_as_list():
    """Text starting with '— ' should not be classified as list by text pattern."""
    from document import classify_paragraph_role

    assert classify_paragraph_role("— Это прямая речь", "Body Text") == "body"
    assert classify_paragraph_role("— Цитата из книги", "Normal") == "body"
    assert classify_paragraph_role("- Пункт списка", "Body Text") == "list"
    assert classify_paragraph_role("• Маркированный пункт", "Normal") == "list"


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


def test_read_uploaded_docx_bytes_reuses_existing_docx_bytes_without_renormalizing(monkeypatch):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr("word/document.xml", "<w:document />")
    docx_bytes = buffer.getvalue()

    monkeypatch.setattr(document, "read_uploaded_file_bytes", lambda uploaded_file: docx_bytes)
    assert document._read_uploaded_docx_bytes(object()) == docx_bytes


def test_read_uploaded_docx_bytes_rejects_non_normalized_non_docx_input(monkeypatch):
    monkeypatch.setattr(document, "read_uploaded_file_bytes", lambda uploaded_file: b"legacy-binary")
    monkeypatch.setattr(document, "resolve_uploaded_filename", lambda uploaded_file: "legacy.doc")

    with pytest.raises(ValueError, match="Ожидался уже нормализованный DOCX-архив"):
        document._read_uploaded_docx_bytes(object())


def test_extraction_compatibility_override_inventory_is_explicit_and_applied(monkeypatch):
    monkeypatch.setattr(document._document_extraction, "MAX_DOCX_ARCHIVE_SIZE_BYTES", -1, raising=False)
    monkeypatch.setattr(document._document_extraction, "_validate_docx_archive", None, raising=False)

    document._sync_extraction_compatibility_overrides()

    assert document.EXTRACTION_COMPATIBILITY_OVERRIDE_DEADLINE == "2026-06-30"
    assert tuple(document._build_extraction_compatibility_overrides()) == document.EXTRACTION_COMPATIBILITY_OVERRIDE_TARGETS
    assert document._document_extraction.MAX_DOCX_ARCHIVE_SIZE_BYTES == document.MAX_DOCX_ARCHIVE_SIZE_BYTES
    assert document._document_extraction._validate_docx_archive is document._validate_docx_archive


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


def test_extract_document_content_from_docx_detects_heading_from_inherited_style_alignment_with_text_signal():
    doc = Document()
    centered_style = doc.styles.add_style("Centered Heading Candidate", WD_STYLE_TYPE.PARAGRAPH)
    _set_style_alignment(centered_style, "center")
    paragraph = doc.add_paragraph("Раздел 3 Основные результаты", style="Centered Heading Candidate")
    run = paragraph.runs[0]
    run.bold = True
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].role == "heading"
    assert paragraphs[0].heading_source == "heuristic"
    assert paragraphs[0].heading_level == 2


def test_extract_document_content_from_docx_detects_heading_from_base_style_chain_alignment_with_text_signal():
    doc = Document()
    base_style = doc.styles.add_style("Centered Heading Base", WD_STYLE_TYPE.PARAGRAPH)
    _set_style_alignment(base_style, "center")
    derived_style = cast(Any, doc.styles.add_style("Centered Heading Derived", WD_STYLE_TYPE.PARAGRAPH))
    derived_style.base_style = base_style
    paragraph = doc.add_paragraph("Глава 2 Методика", style="Centered Heading Derived")
    run = paragraph.runs[0]
    run.bold = True
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].role == "heading"
    assert paragraphs[0].heading_source == "heuristic"
    assert paragraphs[0].heading_level == 1


def test_extract_document_content_from_docx_promotes_front_matter_display_title_to_h1():
    doc = Document()
    author = doc.add_paragraph("Mariana Mazzucato", style="Heading 1")
    author.runs[0].font.size = Pt(28)

    title = doc.add_paragraph("T H E VALUE O F E V E RY T H I NG")
    title.runs[0].font.size = Pt(28)

    subtitle = doc.add_paragraph()
    subtitle_run = subtitle.add_run("Making and Taking in the Global Economy")
    subtitle_run.italic = True
    subtitle_run.font.size = Pt(18)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert paragraphs[0].text == "Mariana Mazzucato"
    assert paragraphs[0].role == "body"
    assert paragraphs[0].heading_level is None
    assert paragraphs[1].text == "T H E VALUE O F E V E RY T H I NG"
    assert paragraphs[1].role == "heading"
    assert paragraphs[1].heading_source == "heuristic"
    assert paragraphs[1].heading_level == 1
    assert paragraphs[2].role == "body"
    assert paragraphs[2].is_italic is True


def test_extract_document_content_from_docx_keeps_true_structural_h1_when_no_cover_title_exists():
    doc = Document()
    heading = doc.add_paragraph("Chapter 1 Value", style="Heading 1")
    heading.runs[0].font.size = Pt(20)
    body = doc.add_paragraph("This opening paragraph provides ordinary narrative context after the heading.")
    body.runs[0].font.size = Pt(11)
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert paragraphs[0].role == "heading"
    assert paragraphs[0].heading_level == 1
    assert paragraphs[0].text == "Chapter 1 Value"


def test_extract_document_content_from_docx_paragraph_alignment_override_beats_inherited_center_for_heading_detection():
    doc = Document()
    base_style = doc.styles.add_style("Centered Heading Base Override", WD_STYLE_TYPE.PARAGRAPH)
    _set_style_alignment(base_style, "center")
    derived_style = cast(Any, doc.styles.add_style("Centered Heading Derived Override", WD_STYLE_TYPE.PARAGRAPH))
    derived_style.base_style = base_style
    paragraph = doc.add_paragraph("Краткое описание установки", style="Centered Heading Derived Override")
    _set_raw_paragraph_alignment(paragraph, "left")
    run = paragraph.runs[0]
    run.bold = True
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].role == "body"
    assert paragraphs[0].heading_level is None
    assert paragraphs[0].role_confidence == "heuristic"


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


def test_extract_document_content_from_docx_does_not_promote_inherited_centered_body_without_text_signal():
    doc = Document()
    centered_style = doc.styles.add_style("Centered Body Candidate", WD_STYLE_TYPE.PARAGRAPH)
    _set_style_alignment(centered_style, "center")
    paragraph = doc.add_paragraph("Краткое описание установки", style="Centered Body Candidate")
    run = paragraph.runs[0]
    run.bold = True
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert len(paragraphs) == 1
    assert paragraphs[0].role == "body"
    assert paragraphs[0].heading_level is None
    assert paragraphs[0].role_confidence == "heuristic"


def test_extract_document_content_from_docx_promotes_short_larger_subheading_between_body_paragraphs():
    doc = Document()

    first_paragraph = doc.add_paragraph(
        "Богатство может означать деньги, свободу выбора, устойчивость и доступ к возможностям, "
        "которые человек иначе не получил бы."
    )
    first_paragraph.runs[0].font.size = Pt(11)

    heading_paragraph = doc.add_paragraph("Переосмысление богатства")
    heading_paragraph.runs[0].font.size = Pt(14)

    third_paragraph = doc.add_paragraph(
        "Богатство - это не только владение активами, но и способность направлять время, внимание "
        "и отношения к осмысленным целям."
    )
    third_paragraph.runs[0].font.size = Pt(11)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["body", "heading", "body"]
    assert paragraphs[1].heading_source == "heuristic"
    assert paragraphs[1].heading_level == 2
    assert build_document_text(paragraphs) == (
        "Богатство может означать деньги, свободу выбора, устойчивость и доступ к возможностям, "
        "которые человек иначе не получил бы.\n\n"
        "## Переосмысление богатства\n\n"
        "Богатство - это не только владение активами, но и способность направлять время, внимание "
        "и отношения к осмысленным целям."
    )


def test_extract_document_content_from_docx_promotes_very_short_subheading_between_body_paragraphs_without_larger_font():
    doc = Document()

    doc.add_paragraph(
        "Привлекательность лотерейных билетов с крупными призами отчасти объясняется мечтами о переменах и доступе к новым "
        "возможностям."
    )
    doc.add_paragraph("Переосмысление богатства")
    doc.add_paragraph(
        "Богатство - это то, чего мы все хотим, но его значение зависит не только от денег, а еще и от устойчивости, "
        "свободы выбора и качества связей."
    )

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["body", "heading", "body"]
    assert paragraphs[1].heading_source == "heuristic"
    assert paragraphs[1].heading_level == 2


def test_extract_document_content_from_docx_does_not_promote_very_short_sentence_with_terminal_period():
    doc = Document()

    doc.add_paragraph(
        "Привлекательность лотерейных билетов с крупными призами отчасти объясняется мечтами о переменах и доступе к новым "
        "возможностям."
    )
    doc.add_paragraph("Новое богатство.")
    doc.add_paragraph(
        "Богатство - это то, чего мы все хотим, но его значение зависит не только от денег, а еще и от устойчивости, "
        "свободы выбора и качества связей."
    )

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["body", "body", "body"]


def test_promote_short_standalone_headings_does_not_override_ai_classified_body_heading_candidate():
    paragraphs = [
        ParagraphUnit(
            text="Привлекательность лотерейных билетов с крупными призами объясняется мечтами о переменах и доступе к новым возможностям.",
            role="body",
            source_index=0,
            font_size_pt=11.0,
        ),
        ParagraphUnit(
            text="Переосмысление богатства",
            role="body",
            structural_role="body",
            role_confidence="ai",
            source_index=1,
            font_size_pt=14.0,
        ),
        ParagraphUnit(
            text="Богатство зависит не только от денег, но и от устойчивости, свободы выбора и качества связей.",
            role="body",
            source_index=2,
            font_size_pt=11.0,
        ),
    ]

    document._promote_short_standalone_headings(paragraphs)

    assert [paragraph.role for paragraph in paragraphs] == ["body", "body", "body"]
    assert paragraphs[1].role_confidence == "ai"
    assert paragraphs[1].heading_source is None
    assert paragraphs[1].heading_level is None


def test_promote_short_standalone_headings_does_not_override_ai_structural_attribution():
    paragraphs = [
        ParagraphUnit(
            text="Богатство может означать деньги, свободу выбора и доступ к возможностям.",
            role="body",
            source_index=0,
            font_size_pt=11.0,
        ),
        ParagraphUnit(
            text="ЭПИКТЕТ",
            role="body",
            structural_role="attribution",
            role_confidence="ai",
            source_index=1,
            font_size_pt=16.0,
        ),
        ParagraphUnit(
            text="Следующий абзац продолжает мысль и даёт обычный текстовый контекст для эвристического паттерна.",
            role="body",
            source_index=2,
            font_size_pt=11.0,
        ),
    ]

    document._promote_short_standalone_headings(paragraphs)

    assert paragraphs[1].role == "body"
    assert paragraphs[1].structural_role == "attribution"
    assert paragraphs[1].role_confidence == "ai"
    assert paragraphs[1].heading_source is None


def test_extract_document_content_from_docx_keeps_inherited_centered_caption_after_table():
    doc = Document()
    centered_style = doc.styles.add_style("Centered Caption Candidate", WD_STYLE_TYPE.PARAGRAPH)
    _set_style_alignment(centered_style, "center")
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Ячейка"
    paragraph = doc.add_paragraph("Таблица 1 Итоговые показатели", style="Centered Caption Candidate")
    run = paragraph.runs[0]
    run.bold = True
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)

    assert [paragraph.role for paragraph in paragraphs] == ["table", "caption"]
    assert paragraphs[1].attached_to_asset_id == "table_001"
    assert paragraphs[1].heading_level is None


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
