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


def test_unified_restoration_preserves_alignment():
    source_doc = Document()
    heading = source_doc.add_paragraph("Что такое богатство?")
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading.add_run().bold = True
    body_left = source_doc.add_paragraph("Первый абзац")
    body_left.alignment = WD_ALIGN_PARAGRAPH.LEFT
    epigraph = source_doc.add_paragraph("Краткая мысль")
    epigraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    epigraph.runs[0].italic = True
    justified = source_doc.add_paragraph("Основной абзац с обычным телом текста")
    _set_raw_paragraph_alignment(justified, "both")

    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)
    source_paragraphs, _ = extract_document_content_from_docx(source_buffer)

    target_doc = Document()
    target_doc.add_paragraph("Что такое богатство?")
    target_doc.add_paragraph("Первый абзац")
    target_doc.add_paragraph("Краткая мысль")
    target_doc.add_paragraph("Основной абзац с обычным телом текста")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_doc = Document(BytesIO(restore_source_formatting(target_buffer.getvalue(), source_paragraphs)))

    assert [_get_alignment_xml_value(paragraph) for paragraph in updated_doc.paragraphs] == [
        _get_alignment_xml_value(paragraph) for paragraph in source_doc.paragraphs
    ]


def test_unified_restoration_preserves_list_numbering():
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

    updated_doc = Document(BytesIO(restore_source_formatting(target_buffer.getvalue(), source_paragraphs)))
    first_ilvl, first_num_id = _extract_numbering_ids(updated_doc.paragraphs[0])
    second_ilvl, second_num_id = _extract_numbering_ids(updated_doc.paragraphs[1])

    assert updated_doc.paragraphs[0].style.name == "List Paragraph"
    assert updated_doc.paragraphs[1].style.name == "List Paragraph"
    assert first_ilvl == "0"
    assert second_ilvl == "0"
    assert first_num_id is not None
    assert second_num_id == first_num_id
    assert _numbering_root_contains_num_id(updated_doc, first_num_id)


def test_unified_restoration_preserves_heading_styles():
    source_paragraphs = [
        ParagraphUnit(text="Глава", role="heading", heading_level=1),
        ParagraphUnit(text="Раздел", role="heading", heading_level=2),
        ParagraphUnit(text="Краткое описание установки", role="heading", heading_level=2),
        ParagraphUnit(text="Обычный текст", role="body"),
    ]

    target_doc = Document()
    for paragraph in source_paragraphs:
        target_doc.add_paragraph(paragraph.text)
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_doc = Document(BytesIO(restore_source_formatting(target_buffer.getvalue(), source_paragraphs)))

    assert updated_doc.paragraphs[0].style.name == "Heading 1"
    assert updated_doc.paragraphs[1].style.name == "Heading 2"
    assert updated_doc.paragraphs[2].style.name == "Heading 2"
    assert updated_doc.paragraphs[3].style.name in {"Body Text", "Normal"}


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