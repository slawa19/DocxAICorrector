from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from document import extract_document_content_from_docx
from formatting_transfer import (
    _apply_preserved_paragraph_properties,
    _apply_semantic_style,
    _map_source_target_paragraphs,
    _apply_minimal_caption_formatting,
    _apply_minimal_image_formatting,
    normalize_semantic_output_docx,
    restore_source_formatting,
)
from models import ParagraphUnit


def _set_raw_paragraph_alignment(paragraph, value: str) -> None:
    paragraph_properties = paragraph._element.get_or_add_pPr()
    alignment = paragraph_properties.find(qn("w:jc"))
    if alignment is None:
        alignment = OxmlElement("w:jc")
        paragraph_properties.append(alignment)
    alignment.set(qn("w:val"), value)


def _get_alignment_xml_value(paragraph) -> str | None:
    paragraph_properties = paragraph._element.pPr
    if paragraph_properties is None:
        return None
    alignment = paragraph_properties.find(qn("w:jc"))
    if alignment is None:
        return None
    return alignment.get(qn("w:val"))


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


def _numbering_root_contains_num_id(document, num_id: str) -> bool:
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


def _append_decimal_numbering_definition(document, *, num_id: str, abstract_num_id: str) -> None:
    numbering_root = document.part.numbering_part.element

    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), abstract_num_id)
    lvl = OxmlElement("w:lvl")
    lvl.set(qn("w:ilvl"), "0")

    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    lvl.append(start)

    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), "decimal")
    lvl.append(num_fmt)

    lvl_text = OxmlElement("w:lvlText")
    lvl_text.set(qn("w:val"), "%1.")
    lvl.append(lvl_text)
    abstract_num.append(lvl)
    numbering_root.append(abstract_num)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), num_id)
    abstract_num_ref = OxmlElement("w:abstractNumId")
    abstract_num_ref.set(qn("w:val"), abstract_num_id)
    num.append(abstract_num_ref)
    numbering_root.append(num)


def _attach_numbering(paragraph, *, num_id: str, ilvl: str) -> None:
    paragraph_properties = paragraph._element.get_or_add_pPr()
    num_pr = paragraph_properties.find(qn("w:numPr"))
    if num_pr is None:
        num_pr = OxmlElement("w:numPr")
        paragraph_properties.append(num_pr)

    ilvl_element = num_pr.find(qn("w:ilvl"))
    if ilvl_element is None:
        ilvl_element = OxmlElement("w:ilvl")
        num_pr.append(ilvl_element)
    ilvl_element.set(qn("w:val"), ilvl)

    num_id_element = num_pr.find(qn("w:numId"))
    if num_id_element is None:
        num_id_element = OxmlElement("w:numId")
        num_pr.append(num_id_element)
    num_id_element.set(qn("w:val"), num_id)


def test_restore_source_formatting_preserves_existing_heading_semantics():
    source_doc = Document()
    source_doc.add_paragraph("Что такое богатство?")
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)
    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    target_doc.add_paragraph("Что такое богатство?", style="Heading 2")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_doc = Document(BytesIO(restore_source_formatting(target_buffer.getvalue(), source_paragraphs)))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Heading 2"


def test_restore_source_formatting_does_not_inject_source_numbering_xml():
    source_doc = Document()
    source_doc.add_paragraph("Первый пункт", style="List Number")
    source_doc.add_paragraph("Второй пункт", style="List Number")
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)
    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    _append_decimal_numbering_definition(target_doc, num_id="77", abstract_num_id="700")
    first = target_doc.add_paragraph("Первый пункт")
    second = target_doc.add_paragraph("Второй пункт")
    _attach_numbering(first, num_id="77", ilvl="0")
    _attach_numbering(second, num_id="77", ilvl="0")
    first_ilvl, first_num_id = _extract_numbering_ids(first)
    second_ilvl, second_num_id = _extract_numbering_ids(second)
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_doc = Document(BytesIO(restore_source_formatting(target_buffer.getvalue(), source_paragraphs)))
    updated_first_ilvl, updated_first_num_id = _extract_numbering_ids(updated_doc.paragraphs[0])
    updated_second_ilvl, updated_second_num_id = _extract_numbering_ids(updated_doc.paragraphs[1])

    assert updated_first_ilvl == first_ilvl
    assert updated_second_ilvl == second_ilvl
    assert updated_first_num_id == first_num_id
    assert updated_second_num_id == second_num_id
    assert updated_first_num_id is not None
    assert _numbering_root_contains_num_id(updated_doc, updated_first_num_id)


def test_unified_restoration_preserves_heading_styles():
    source_paragraphs = [
        ParagraphUnit(text="Глава", role="heading", heading_level=1),
        ParagraphUnit(text="Раздел", role="heading", heading_level=2),
        ParagraphUnit(text="Краткое описание установки", role="heading", heading_level=2),
        ParagraphUnit(text="Обычный текст", role="body"),
    ]

    target_doc = Document()
    target_doc.add_paragraph(source_paragraphs[0].text, style="Heading 1")
    target_doc.add_paragraph(source_paragraphs[1].text, style="Heading 2")
    target_doc.add_paragraph(source_paragraphs[2].text, style="Heading 2")
    target_doc.add_paragraph(source_paragraphs[3].text)
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_doc = Document(BytesIO(restore_source_formatting(target_buffer.getvalue(), source_paragraphs)))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[2].style is not None
    assert updated_doc.paragraphs[3].style is not None
    assert updated_doc.paragraphs[0].style.name == "Heading 1"
    assert updated_doc.paragraphs[1].style.name == "Heading 2"
    assert updated_doc.paragraphs[2].style.name == "Heading 2"
    assert updated_doc.paragraphs[3].style.name in {"Body Text", "Normal"}


def test_normalize_semantic_output_docx_is_noop():
    document = Document()
    paragraph = document.add_paragraph("Обычный текст")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    buffer = BytesIO()
    document.save(buffer)

    docx_bytes = buffer.getvalue()
    assert normalize_semantic_output_docx(docx_bytes, [ParagraphUnit(text="Обычный текст", role="body")]) == docx_bytes


def test_style_assignment_does_not_destroy_alignment():
    source_doc = Document()
    source_paragraph = source_doc.add_paragraph("Что такое богатство?")
    source_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)
    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    target_doc.add_paragraph("Что такое богатство?")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    working_doc = Document(BytesIO(target_buffer.getvalue()))
    paragraph = working_doc.paragraphs[0]
    _apply_semantic_style(
        working_doc,
        paragraph,
        ParagraphUnit(text="Что такое богатство?", role="heading", heading_level=1),
    )
    _apply_preserved_paragraph_properties(
        paragraph,
        source_paragraphs[0].preserved_ppr_xml,
        exclude_names=frozenset({"pStyle", "numPr"}),
    )

    assert _get_alignment_xml_value(paragraph) == "center"


def test_mapping_accepts_split_heading_target_for_merged_source_paragraph():
    source_paragraphs = [
        ParagraphUnit(
            paragraph_id="p0056",
            text=(
                "Миф (и потенциал) индивидуального богатства "
                "До сих пор мы затронули три вещи, которые определяют наше понимание богатства:"
            ),
            role="body",
            structural_role="body",
            role_confidence="heuristic",
        )
    ]
    generated_registry = [
        {
            "paragraph_id": "p0056",
            "text": (
                "### Миф (и потенциал) индивидуального богатства\n"
                "До сих пор мы затронули три вещи, которые определяют наше понимание богатства:"
            ),
        }
    ]

    target_doc = Document()
    target_doc.add_paragraph("Миф (и потенциал) индивидуального богатства", style="Heading 3")
    target_doc.add_paragraph("До сих пор мы затронули три вещи, которые определяют наше понимание богатства:")

    mapping_pairs, diagnostics = _map_source_target_paragraphs(
        source_paragraphs,
        target_doc.paragraphs,
        generated_paragraph_registry=generated_registry,
    )

    assert [(source.paragraph_id, target.text) for source, target in mapping_pairs] == [
        ("p0056", "До сих пор мы затронули три вещи, которые определяют наше понимание богатства:"),
    ]
    assert diagnostics["unmapped_source_ids"] == []
    assert diagnostics["unmapped_target_indexes"] == []
    assert len(diagnostics["accepted_split_targets"]) == 1
    accepted_target = diagnostics["accepted_split_targets"][0]
    assert accepted_target["target_index"] == 0
    assert accepted_target["derived_from_source_index"] == 0
    assert accepted_target["kind"] == "split_heading_prefix"
    assert accepted_target["heading_level"] == 3
    assert accepted_target["target_text_preview"] == "Миф (и потенциал) индивидуального богатства"
    assert accepted_target["source_text_preview"].startswith("Миф (и потенциал) индивидуального богатства")


def test_apply_minimal_image_formatting_centers_only_image_only_paragraphs():
    document = Document()
    image_only = document.add_paragraph("[[DOCX_IMAGE_img_001]]")
    mixed = document.add_paragraph("Текст [[DOCX_IMAGE_img_002]] подпись")

    _apply_minimal_image_formatting(document)

    assert image_only.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert mixed.alignment is None


def test_apply_minimal_caption_formatting_marks_caption_after_image_anchor():
    document = Document()
    document.add_paragraph("[[DOCX_IMAGE_img_001]]")
    caption = document.add_paragraph("Рис. 1. Подпись к изображению")
    source_paragraphs = [
        ParagraphUnit(text="[[DOCX_IMAGE_img_001]]", role="image", paragraph_id="p0000"),
        ParagraphUnit(text="Рис. 1. Подпись к изображению", role="caption", paragraph_id="p0001"),
    ]

    _apply_minimal_caption_formatting(document, source_paragraphs)

    assert caption.style is not None
    assert caption.style.name == "Caption"
    assert caption.alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_apply_minimal_caption_formatting_marks_caption_after_table_anchor():
    document = Document()
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Данные"
    caption = document.add_paragraph("Table 1. Summary")
    source_paragraphs = [
        ParagraphUnit(text="<table><tbody><tr><td>Данные</td></tr></tbody></table>", role="table", paragraph_id="p0000"),
        ParagraphUnit(text="Table 1. Summary", role="caption", paragraph_id="p0001"),
    ]

    _apply_minimal_caption_formatting(document, source_paragraphs)

    assert caption.style is not None
    assert caption.style.name == "Caption"
    assert caption.alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_apply_minimal_caption_formatting_does_not_promote_body_caption_like_text_without_anchor():
    document = Document()
    body = document.add_paragraph("Рис. 5. Это обычный абзац основного текста")
    source_paragraphs = [
        ParagraphUnit(text="Рис. 5. Это обычный абзац основного текста", role="body", paragraph_id="p0000"),
    ]

    _apply_minimal_caption_formatting(document, source_paragraphs)

    assert body.style is None or body.style.name != "Caption"
    assert body.alignment is None


def test_apply_minimal_caption_formatting_keeps_exact_caption_match_gated_by_anchor_context():
    document = Document()
    document.add_paragraph("Вводный абзац")
    body = document.add_paragraph("Table 3. Generated caption text")
    source_paragraphs = [
        ParagraphUnit(text="Table 3. Generated caption text", role="caption", paragraph_id="p0007"),
    ]
    generated_registry = [{"paragraph_id": "p0007", "text": "Table 3. Generated caption text"}]

    _apply_minimal_caption_formatting(
        document,
        source_paragraphs,
        generated_paragraph_registry=generated_registry,
    )

    assert body.style is None or body.style.name != "Caption"
    assert body.alignment is None
