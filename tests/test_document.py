import base64
import json
import os
import zipfile
from io import BytesIO
from pathlib import Path
import config
from typing import Any, cast

import document
import formatting_transfer
import formatting_diagnostics_retention
import image_reinsertion
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from document import (
    build_paragraph_relations,
    build_marker_wrapped_block_text,
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    extract_document_content_from_docx,
    extract_document_content_with_normalization_reports,
    inspect_placeholder_integrity,
)
from formatting_transfer import (
    normalize_semantic_output_docx,
    preserve_source_paragraph_properties,
)
from image_reinsertion import (
    _build_variant_block_elements,
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


def _set_style_alignment(style, value: str) -> None:
    style_properties = style._element.get_or_add_pPr()
    alignment = style_properties.find(qn("w:jc"))
    if alignment is None:
        alignment = OxmlElement("w:jc")
        style_properties.append(alignment)
    alignment.set(qn("w:val"), value)


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


def _extract_source_rects(element) -> list[dict[str, str]]:
    return [
        {key: src_rect.get(key) for key in ("l", "t", "r", "b") if src_rect.get(key) is not None}
        for src_rect in element.xpath(".//a:srcRect")
    ]


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


def test_build_paragraph_relations_detects_caption_epigraph_and_toc_groups():
    paragraphs = [
        ParagraphUnit(text="[[DOCX_IMAGE_img_001]]", role="image", structural_role="image", paragraph_id="p0000", asset_id="img_001"),
        ParagraphUnit(
            text="Рис. 1. Подпись",
            role="caption",
            structural_role="caption",
            paragraph_id="p0001",
            attached_to_asset_id="img_001",
        ),
        ParagraphUnit(
            text="Богатство заключается не в том, чтобы иметь много имущества.",
            role="body",
            structural_role="epigraph",
            paragraph_id="p0002",
            paragraph_alignment="center",
        ),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0003"),
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0004"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0005"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0006"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert [relation.relation_kind for relation in relations] == [
        "image_caption",
        "epigraph_attribution",
        "toc_region",
    ]
    assert report.total_relations == 3
    assert report.relation_counts == {
        "image_caption": 1,
        "epigraph_attribution": 1,
        "toc_region": 1,
    }


def test_build_semantic_blocks_keeps_epigraph_attribution_pair_together():
    paragraphs = [
        ParagraphUnit(text="Богатство заключается в свободе желаний.", role="body", structural_role="epigraph", paragraph_id="p0000"),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0001"),
        ParagraphUnit(text="Следующий обычный абзац должен перейти в отдельный блок.", role="body", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=70)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Богатство заключается в свободе желаний.",
        "— Эпиктет",
    ]


def test_build_semantic_blocks_keeps_toc_region_together():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Первый обычный абзац после содержания.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=60)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Содержание",
        "Глава 1........ 12",
        "Глава 2........ 18",
    ]


def test_build_semantic_blocks_fallback_uses_effective_relation_config(monkeypatch):
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("image_caption", "table_caption"),
            "relation_normalization_save_debug_artifacts": True,
        },
    )
    paragraphs = [
        ParagraphUnit(
            text="Богатство заключается не в накоплении вещей, а в свободе от лишнего.",
            role="body",
            structural_role="epigraph",
            paragraph_id="p0000",
        ),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0001"),
        ParagraphUnit(text="Следующий обычный абзац должен остаться отдельным блоком.", role="body", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=55)

    assert len(blocks) == 3
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Богатство заключается не в накоплении вещей, а в свободе от лишнего.",
    ]
    assert [paragraph.text for paragraph in blocks[1].paragraphs] == ["— Эпиктет"]


def test_build_paragraph_relations_records_epigraph_and_isolated_toc_rejections():
    paragraphs = [
        ParagraphUnit(text="Богатство заключается в свободе желаний.", role="body", structural_role="epigraph", paragraph_id="p0000"),
        ParagraphUnit(text="Комментарий редактора", role="body", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0002"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert relations == []
    assert report.rejected_candidate_count == 2
    assert [(decision.relation_kind, decision.reasons) for decision in report.decisions] == [
        ("epigraph_attribution", ("epigraph_without_attribution",)),
        ("toc_region", ("isolated_toc_entry",)),
    ]


def test_build_paragraph_relations_detects_table_caption_and_headerless_toc_run():
    paragraphs = [
        ParagraphUnit(text="<table><tr><td>1</td></tr></table>", role="table", structural_role="table", paragraph_id="p0000", asset_id="table_001"),
        ParagraphUnit(text="Табл. 1. Подпись", role="caption", structural_role="caption", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0003"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert [relation.relation_kind for relation in relations] == ["table_caption", "toc_region"]
    assert report.relation_counts == {"table_caption": 1, "toc_region": 1}


def test_build_paragraph_relations_records_rejected_caption_candidate():
    paragraphs = [
        ParagraphUnit(text="Рис. 3. Одинокая подпись", role="caption", structural_role="caption", paragraph_id="p0000"),
        ParagraphUnit(text="Обычный абзац", role="body", paragraph_id="p0001"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert relations == []
    assert report.total_relations == 0
    assert report.rejected_candidate_count == 1
    assert report.decisions[0].decision == "reject"
    assert report.decisions[0].relation_kind == "caption_attachment"
    assert report.decisions[0].reasons == ("caption_without_preceding_asset",)


def test_build_editing_jobs_preserves_marker_count_after_relation_grouping():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=200)
    jobs = build_editing_jobs(blocks, max_chars=200)

    assert len(blocks) == 1
    assert jobs[0]["paragraph_ids"] == ["p0000", "p0001", "p0002"]
    assert str(jobs[0]["target_text_with_markers"]).count("[[DOCX_PARA_") == 3


def test_build_marker_wrapped_block_text_preserves_paragraph_ids_and_boundaries():
    paragraphs = [
        ParagraphUnit(text="Глава", role="heading", paragraph_id="p0001", heading_level=1),
        ParagraphUnit(text="Основной текст", role="body", paragraph_id="p0002"),
    ]

    result = build_marker_wrapped_block_text(paragraphs)

    assert result == "[[DOCX_PARA_p0001]]\n# Глава\n\n[[DOCX_PARA_p0002]]\nОсновной текст"


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


def _make_docx_with_emdash_bullet_numbering(texts: list[str]) -> BytesIO:
    """Create a DOCX where 'List Paragraph' paragraphs use em-dash (U+2014) as bullet char."""
    doc = Document()
    doc.add_paragraph("Обычный текст перед списком.")

    numbering_part = doc.part.numbering_part
    numbering_root = numbering_part._element
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

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
        pPr = para._element.find(qn("w:pPr"))
        if pPr is None:
            pPr = OxmlElement("w:pPr")
            para._element.insert(0, pPr)
        numPr = OxmlElement("w:numPr")
        ilvl = OxmlElement("w:ilvl")
        ilvl.set(qn("w:val"), "0")
        numId = OxmlElement("w:numId")
        numId.set(qn("w:val"), "900")
        numPr.append(ilvl)
        numPr.append(numId)
        pPr.append(numPr)

    doc.add_paragraph("Обычный текст после.")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def test_emdash_bullet_paragraphs_are_not_classified_as_list():
    """Em-dash (—) bullet in OOXML numbering is Russian typographic convention, not a real list."""
    buffer = _make_docx_with_emdash_bullet_numbering([
        "Американская торговая палата тратит на лоббизм больше всех.",
        "Эти многоплановые усилия — прерогатива местных сообществ.",
    ])

    paragraphs, _ = extract_document_content_from_docx(buffer)

    emdash_paras = [p for p in paragraphs if "торговая палата" in p.text or "многоплановые" in p.text]
    assert len(emdash_paras) == 2
    for p in emdash_paras:
        assert p.role == "body", f"Expected role='body', got '{p.role}' for: {p.text[:60]}"
        assert p.list_kind is None
        assert p.list_num_xml is None
        assert p.list_abstract_num_xml is None


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
    # Real list markers still work
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


def test_preserve_source_paragraph_properties_keeps_existing_heading_semantics_in_target_docx():
    source_paragraphs = [ParagraphUnit(text="Заголовок", role="heading", heading_level=1)]

    target_doc = Document()
    target_doc.add_paragraph("Заголовок", style="Heading 2")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Heading 2"


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


def test_preserve_source_paragraph_properties_does_not_replay_raw_xml_on_mismatch():
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

    assert first_indentation is None


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


def test_preserve_source_paragraph_properties_artifact_records_restored_list_decisions_during_mismatch(tmp_path, monkeypatch):
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

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)

    artifacts = sorted(diagnostics_dir.glob("*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert len(payload["list_restoration_decisions"]) == 1
    assert payload["list_restoration_decisions"][0]["action"] == "restored"


def test_prune_formatting_diagnostics_removes_oldest_and_preserves_newest(tmp_path):
    diagnostics_dir = tmp_path / "formatting_diagnostics"
    diagnostics_dir.mkdir()
    timestamps = [1000, 2000, 3000, 4000]
    paths = []
    for timestamp in timestamps:
        path = diagnostics_dir / f"restore_{timestamp}.json"
        path.write_text("{}", encoding="utf-8")
        paths.append(path)

    for offset, path in enumerate(paths, start=1):
        mtime = float(offset)
        path.touch()
        os.utime(path, (mtime, mtime))

    pruned = formatting_diagnostics_retention.prune_formatting_diagnostics(
        diagnostics_dir=diagnostics_dir,
        now_epoch_seconds=10.0,
        max_age_seconds=100,
        max_count=2,
    )

    remaining = sorted(path.name for path in diagnostics_dir.glob("*.json"))
    assert remaining == ["restore_3000.json", "restore_4000.json"]
    assert sorted(Path(path).name for path in pruned) == ["restore_1000.json", "restore_2000.json"]


def test_write_formatting_diagnostics_artifact_prunes_expired_runtime_files_only(tmp_path):
    runtime_dir = tmp_path / ".run" / "formatting_diagnostics"
    tests_dir = tmp_path / "tests" / "artifacts" / "formatting_diagnostics"
    runtime_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    old_runtime = runtime_dir / "restore_old.json"
    old_runtime.write_text("{}", encoding="utf-8")
    test_artifact = tests_dir / "keep.json"
    test_artifact.write_text("{}", encoding="utf-8")

    import os
    os.utime(old_runtime, (1.0, 1.0))

    artifact_path = formatting_diagnostics_retention.write_formatting_diagnostics_artifact(
        stage="restore",
        diagnostics={"mapped_count": 1},
        diagnostics_dir=runtime_dir,
        now_epoch_ms=200_000,
    )

    assert artifact_path is not None
    assert sorted(path.name for path in runtime_dir.glob("*.json")) == [Path(artifact_path).name]
    assert test_artifact.exists()


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

    assert len(updated_doc.tables) == 0
    assert len(updated_doc.inline_shapes) == 3
    assert len(updated_doc.paragraphs) == 3
    assert "candidate1" not in visible_text
    assert "candidate2" not in visible_text
    assert _extract_docpr_descriptions(updated_doc._element) == ["safe", "candidate1", "candidate2"]


def test_preserve_source_paragraph_properties_applies_minimal_output_formatting():
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

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[2].style is not None
    assert updated_doc.paragraphs[3].style is not None
    assert updated_doc.tables[0].style is not None

    assert updated_doc.paragraphs[0].style.name == "Normal"
    assert updated_doc.paragraphs[1].alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert updated_doc.paragraphs[2].style.name == "Caption"
    assert updated_doc.paragraphs[3].style.name in {"Body Text", "Normal"}
    assert updated_doc.tables[0].style.name == "Table Grid"


def test_preserve_source_paragraph_properties_applies_partial_transfer_on_semantic_mismatch():
    source_paragraphs = [ParagraphUnit(text="Заголовок", role="heading", heading_level=1)]
    target_doc = Document()
    target_doc.add_paragraph("Заголовок")
    target_doc.add_paragraph("Лишний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Normal"
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Normal"


def test_preserve_source_paragraph_properties_uses_content_heuristics_for_captions_without_mapping():
    source_paragraphs = [ParagraphUnit(text="Рис. 1. Подпись к изображению", role="caption")]
    target_doc = Document()
    target_doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    target_doc.add_paragraph("Рисунок 1 Подпись к изображению")
    target_doc.add_paragraph("Посторонний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Caption"
    assert updated_doc.paragraphs[1].alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_preserve_source_paragraph_properties_restores_direct_center_alignment_for_mapped_paragraphs():
    source_paragraphs = [
        ParagraphUnit(text="ГЛАВА 1", role="heading", heading_level=1, paragraph_alignment="center", paragraph_id="p0000"),
        ParagraphUnit(text="Богатство заключается не в том, чтобы иметь много имущества.", role="body", paragraph_alignment="center", paragraph_id="p0001"),
    ]
    target_doc = Document()
    target_doc.add_paragraph("ГЛАВА 1")
    target_doc.add_paragraph("Богатство заключается не в том, чтобы иметь много имущества.")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert updated_doc.paragraphs[1].alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_preserve_source_paragraph_properties_does_not_promote_generated_registry_text_to_heading():
    source_paragraphs = [ParagraphUnit(text="Старый заголовок", role="heading", heading_level=1, paragraph_id="p0000")]
    target_doc = Document()
    target_doc.add_paragraph("Совершенно новый заголовок")
    target_doc.add_paragraph("Лишний абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(
        target_buffer.getvalue(),
        source_paragraphs,
        generated_paragraph_registry=[{"paragraph_id": "p0000", "text": "Совершенно новый заголовок"}],
    )
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Normal"
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Normal"


def test_preserve_source_paragraph_properties_does_not_apply_body_formatting_via_generated_registry_similarity():
    source_paragraphs = [ParagraphUnit(text="Исходный абзац сильно отличается", role="body", paragraph_id="p0010")]
    target_doc = Document()
    target_doc.add_paragraph("Лишний абзац перед целью")
    target_doc.add_paragraph("Итоговый литературно отредактированный абзац")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(
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
    assert updated_doc.paragraphs[1].style.name == "Normal"


def test_preserve_source_paragraph_properties_leaves_ambiguous_generated_registry_targets_unchanged():
    source_paragraphs = [
        ParagraphUnit(text="Исходный абзац сильно отличается", role="body", paragraph_id="p0011"),
    ]
    target_doc = Document()
    target_doc.add_paragraph("Отредактированный абзац с важной мыслью о богатстве и сообществе сегодня")
    target_doc.add_paragraph("Отредактированный абзац с важной мыслью о богатстве и сообществе завтра")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(
        target_buffer.getvalue(),
        source_paragraphs,
        generated_paragraph_registry=[
            {
                "paragraph_id": "p0011",
                "text": "Отредактированный абзац с важной мыслью о богатстве и сообществе",
            }
        ],
    )
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Normal"
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Normal"


def test_preserve_source_paragraph_properties_does_not_use_split_generated_registry_mapping_for_body():
    source_paragraphs = [ParagraphUnit(text="Старый слитый абзац", role="body", paragraph_id="p0056")]
    target_doc = Document()
    target_doc.add_paragraph("Новый заголовок", style="Heading 3")
    target_doc.add_paragraph("Текст после нового заголовка")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(
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
    assert updated_doc.paragraphs[1].style.name == "Normal"


def test_preserve_source_paragraph_properties_does_not_restyle_reordered_paragraphs():
    source_paragraphs = [
        ParagraphUnit(text="Заголовок", role="heading", heading_level=1),
        ParagraphUnit(text="Обычный текст", role="body"),
    ]
    target_doc = Document()
    target_doc.add_paragraph("Обычный текст")
    target_doc.add_paragraph("Заголовок")
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name in {"Body Text", "Normal"}
    assert updated_doc.paragraphs[1].style is not None
    assert updated_doc.paragraphs[1].style.name == "Normal"


def test_preserve_source_paragraph_properties_keeps_existing_numbered_list_semantics_without_injecting_source_numbering():
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
    original_first = _extract_numbering_ids(first)
    original_second = _extract_numbering_ids(second)
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    first_ilvl, first_num_id = _extract_numbering_ids(updated_doc.paragraphs[0])
    second_ilvl, second_num_id = _extract_numbering_ids(updated_doc.paragraphs[1])

    assert (first_ilvl, first_num_id) == original_first
    assert (second_ilvl, second_num_id) == original_second
    assert first_num_id is not None
    assert _numbering_root_contains_num_id(updated_doc, first_num_id)


def test_preserve_source_paragraph_properties_restores_numbering_for_mapped_plain_target_paragraphs_despite_mismatch():
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

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
    updated_doc = Document(BytesIO(updated_bytes))

    ilvl, num_id = _extract_numbering_ids(updated_doc.paragraphs[0])

    assert updated_doc.paragraphs[0].style is not None
    assert updated_doc.paragraphs[0].style.name == "Normal"
    assert ilvl == "0"
    assert num_id is not None
    assert _numbering_root_contains_num_id(updated_doc, num_id)
    assert _extract_numbering_ids(updated_doc.paragraphs[1]) == (None, None)


def test_normalize_semantic_output_docx_remains_noop():
    target_doc = Document()
    paragraph = target_doc.add_paragraph("Обычный текст")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    target_buffer = BytesIO()
    target_doc.save(target_buffer)

    docx_bytes = target_buffer.getvalue()
    assert normalize_semantic_output_docx(docx_bytes, [ParagraphUnit(text="Обычный текст", role="body")]) == docx_bytes


def test_caption_survives_extraction_markdown_and_preserve_after_image(tmp_path):
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

    updated_bytes = preserve_source_paragraph_properties(target_buffer.getvalue(), source_paragraphs)
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


def test_reinsert_inline_images_uses_shared_block_layout_for_multi_variant_placeholder_inside_paragraph():
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

    assert [paragraph.text for paragraph in updated_doc.paragraphs] == ["До ", "", "", "", " после"]
    assert updated_doc.paragraphs[0].runs[0].bold is True
    assert updated_doc.paragraphs[-1].runs[0].italic is True
    assert len(updated_doc.tables) == 0
    assert len(updated_doc.inline_shapes) == 3
    assert _extract_docpr_descriptions(updated_doc._element) == ["safe", "candidate1", "candidate2"]


def test_reinsert_inline_images_preserves_hyperlink_when_multi_variant_blocks_are_inserted_nearby():
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
    assert len(updated_doc.tables) == 0
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
    monkeypatch.setattr(
        image_reinsertion,
        "_replace_multi_variant_placeholders_with_blocks",
        lambda paragraph, asset_map, insertion_cache: False,
    )
    monkeypatch.setattr(
        image_reinsertion,
        "_replace_run_level_placeholders",
        lambda paragraph, placeholders, asset_map, insertion_cache: False,
    )
    monkeypatch.setattr(
        image_reinsertion,
        "_replace_multi_run_placeholders",
        lambda paragraph, asset_map, insertion_cache: False,
    )
    monkeypatch.setattr(
        image_reinsertion,
        "_replace_paragraph_placeholders_fallback",
        lambda paragraph, paragraph_text, asset_map, insertion_cache: False,
    )
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


def test_build_variant_block_elements_returns_empty_for_empty_insertions(monkeypatch):
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

    assert _build_variant_block_elements(paragraph, asset) == []


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


def test_reinsert_inline_images_reapplies_source_rect_and_doc_properties_for_original_asset():
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
                original_bytes=PNG_BYTES,
                mime_type="image/png",
                position_index=0,
                width_emu=914400,
                height_emu=914400,
                final_variant="original",
                source_forensics={
                    "source_rect": {"l": 1250, "t": 2500, "r": 3750, "b": 5000},
                    "doc_properties": {
                        "descr": "Исходное описание",
                        "title": "Исходный title",
                        "name": "Исходное имя",
                    },
                },
            )
        ],
    )
    updated_doc = Document(BytesIO(updated_bytes))

    assert _extract_source_rects(updated_doc._element) == [
        {"l": "1250", "t": "2500", "r": "3750", "b": "5000"}
    ]
    doc_pr = updated_doc._element.xpath(".//wp:docPr")[0]
    assert doc_pr.get("descr") == "Исходное описание"
    assert doc_pr.get("title") == "Исходный title"
    assert doc_pr.get("name") == "Исходное имя"


def test_reinsert_inline_images_restores_anchor_container_from_source_forensics():
        doc = Document()
        doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
        buffer = BytesIO()
        doc.save(buffer)

        source_anchor_xml = """
        <wp:anchor xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
                             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                             xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
                             simplePos="0" relativeHeight="0" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">
            <wp:simplePos x="0" y="0"/>
            <wp:positionH relativeFrom="column"><wp:posOffset>0</wp:posOffset></wp:positionH>
            <wp:positionV relativeFrom="paragraph"><wp:posOffset>0</wp:posOffset></wp:positionV>
            <wp:extent cx="914400" cy="914400"/>
            <wp:wrapNone/>
            <wp:docPr id="7" name="Source Anchor" descr="Исходный anchor"/>
            <wp:cNvGraphicFramePr/>
            <a:graphic>
                <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
                    <pic:pic/>
                </a:graphicData>
            </a:graphic>
        </wp:anchor>
        """

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
                                source_forensics={
                                        "drawing_container": "anchor",
                                        "drawing_container_xml": source_anchor_xml,
                                        "doc_properties": {"descr": "Исходный anchor", "name": "Source Anchor"},
                                },
                        )
                ],
        )
        updated_doc = Document(BytesIO(updated_bytes))

        assert len(updated_doc._element.xpath(".//wp:anchor")) == 1
        assert len(updated_doc._element.xpath(".//wp:inline")) == 0
        assert updated_doc._element.xpath(".//wp:docPr")[0].get("descr") == "Исходный anchor"


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


def test_reinsert_inline_images_uses_shared_block_layout_for_split_run_multi_variant_placeholder():
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

    assert [paragraph.text for paragraph in updated_doc.paragraphs] == ["До ", "", "", "", " после"]
    assert updated_doc.paragraphs[0].runs[0].bold is True
    assert updated_doc.paragraphs[-1].runs[0].italic is True
    assert len(updated_doc.tables) == 0
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
    assert len(updated_doc.tables) == 0
    assert [paragraph.text for paragraph in updated_doc.paragraphs] == ["До", "", "", "", "После"]
    assert "Вариант 1: Просто улучшить" not in visible_text
    assert "Вариант 2: Креативная AI-перерисовка" not in visible_text
    assert "Вариант 3: Структурная AI-перерисовка" not in visible_text
    assert _extract_docpr_descriptions(updated_doc._element) == [
        "Вариант 1: Просто улучшить",
        "Вариант 2: Креативная AI-перерисовка",
        "Вариант 3: Структурная AI-перерисовка",
    ]


def test_reinsert_inline_images_resolves_multi_variant_insertions_once_per_placeholder(monkeypatch):
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
    call_count = 0

    def fake_resolve_image_insertions(current_asset):
        nonlocal call_count
        call_count += 1
        return [
            ("safe", PNG_BYTES),
            ("candidate1", PNG_BYTES),
            ("candidate2", PNG_BYTES),
        ]

    monkeypatch.setattr(image_reinsertion, "resolve_image_insertions", fake_resolve_image_insertions)

    updated_bytes = reinsert_inline_images(buffer.getvalue(), [asset])
    updated_doc = Document(BytesIO(updated_bytes))

    assert call_count == 1
    assert len(updated_doc.inline_shapes) == 3


def test_reinsert_inline_images_resolves_reused_placeholder_once_per_pass_across_paragraphs(monkeypatch):
    doc = Document()
    doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    doc.add_paragraph("Before [[DOCX_IMAGE_img_001]] after")
    buffer = BytesIO()
    doc.save(buffer)

    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
    )
    call_count = 0

    def fake_resolve_image_insertions(current_asset):
        nonlocal call_count
        call_count += 1
        assert current_asset.placeholder == "[[DOCX_IMAGE_img_001]]"
        return [(None, PNG_BYTES)]

    monkeypatch.setattr(image_reinsertion, "resolve_image_insertions", fake_resolve_image_insertions)

    updated_bytes = reinsert_inline_images(buffer.getvalue(), [asset])
    updated_doc = Document(BytesIO(updated_bytes))

    assert call_count == 1
    assert len(updated_doc.inline_shapes) == 2
    assert updated_doc.paragraphs[0].text == ""
    assert updated_doc.paragraphs[1].text == "Before  after"


def test_reinsert_inline_images_different_placeholders_keep_separate_cache_entries(monkeypatch):
    doc = Document()
    doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    doc.add_paragraph("[[DOCX_IMAGE_img_002]]")
    buffer = BytesIO()
    doc.save(buffer)

    first_asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
        width_emu=914400,
        height_emu=914400,
        final_variant="original",
    )
    second_asset = ImageAsset(
        image_id="img_002",
        placeholder="[[DOCX_IMAGE_img_002]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=1,
        width_emu=1828800,
        height_emu=1828800,
        final_variant="original",
    )
    seen_placeholders = []

    def fake_resolve_image_insertions(current_asset):
        seen_placeholders.append(current_asset.placeholder)
        return [(None, current_asset.original_bytes)]

    monkeypatch.setattr(image_reinsertion, "resolve_image_insertions", fake_resolve_image_insertions)

    updated_bytes = reinsert_inline_images(buffer.getvalue(), [first_asset, second_asset])
    updated_doc = Document(BytesIO(updated_bytes))

    assert seen_placeholders == ["[[DOCX_IMAGE_img_001]]", "[[DOCX_IMAGE_img_002]]"]
    assert len(updated_doc.inline_shapes) == 2
    assert updated_doc.inline_shapes[0].width == 914400
    assert updated_doc.inline_shapes[1].width == 1828800


def test_reinsert_inline_images_multi_variant_blocks_drop_list_indent_and_keep_next_formatting():
    doc = Document()
    _append_decimal_numbering_definition(doc, num_id="77", abstract_num_id="700")
    paragraph = doc.add_paragraph("[[DOCX_IMAGE_img_001]]")
    _attach_numbering(paragraph, num_id="77", ilvl="0")
    paragraph.paragraph_format.left_indent = Inches(0.5)
    paragraph_properties = paragraph._element.get_or_add_pPr()
    keep_next = OxmlElement("w:keepNext")
    paragraph_properties.append(keep_next)
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

    assert len(updated_doc.paragraphs) == 3
    for updated_paragraph in updated_doc.paragraphs:
        paragraph_properties = updated_paragraph._element.pPr
        assert paragraph_properties is not None
        alignment = paragraph_properties.find(qn("w:jc"))
        assert alignment is not None
        assert alignment.get(qn("w:val")) == "center"
        assert paragraph_properties.find(qn("w:numPr")) is None
        assert paragraph_properties.find(qn("w:ind")) is None
        assert paragraph_properties.find(qn("w:keepNext")) is None


def test_reinsert_inline_images_multi_variant_blocks_drop_heading_style_from_source_paragraph():
    doc = Document()
    paragraph = doc.add_paragraph("[[DOCX_IMAGE_img_001]]", style="Heading 1")
    paragraph_properties = paragraph._element.get_or_add_pPr()
    keep_lines = OxmlElement("w:keepLines")
    paragraph_properties.append(keep_lines)
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

    assert len(updated_doc.paragraphs) == 3
    for updated_paragraph in updated_doc.paragraphs:
        paragraph_properties = updated_paragraph._element.pPr
        assert paragraph_properties is not None
        assert paragraph_properties.find(qn("w:pStyle")) is None
        assert paragraph_properties.find(qn("w:outlineLvl")) is None
        assert paragraph_properties.find(qn("w:keepLines")) is None
        alignment = paragraph_properties.find(qn("w:jc"))
        assert alignment is not None
        assert alignment.get(qn("w:val")) == "center"


def test_reinsert_inline_images_keeps_single_variant_placeholder_text_and_logs_when_inside_hyperlink_in_mixed_multi_variant_paragraph(monkeypatch):
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("Lead ")
    _add_hyperlink(paragraph, "[[DOCX_IMAGE_img_001]]", "https://example.com")
    paragraph.add_run(" middle [[DOCX_IMAGE_img_002]] tail")
    buffer = BytesIO()
    doc.save(buffer)

    first_asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
        width_emu=914400,
        height_emu=914400,
        final_variant="original",
    )
    second_asset = ImageAsset(
        image_id="img_002",
        placeholder="[[DOCX_IMAGE_img_002]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=1,
        safe_bytes=PNG_BYTES,
        attempt_variants=[
            ImageVariantCandidate(mode="candidate1", bytes=PNG_BYTES, mime_type="image/png"),
            ImageVariantCandidate(mode="candidate2", bytes=PNG_BYTES, mime_type="image/png"),
        ],
    )
    second_asset.update_pipeline_metadata(preserve_all_variants_in_docx=True)

    events = []
    monkeypatch.setattr(image_reinsertion, "log_event", lambda level, event, message, **context: events.append((event, context)))

    updated_bytes = reinsert_inline_images(buffer.getvalue(), [first_asset, second_asset])
    updated_doc = Document(BytesIO(updated_bytes))
    visible_text = "\n".join(paragraph.text for paragraph in updated_doc.paragraphs)

    assert "[[DOCX_IMAGE_img_001]]" in visible_text
    assert "tail" in visible_text
    assert len(updated_doc.inline_shapes) == 3
    assert len(updated_doc._element.xpath(".//w:hyperlink")) == 1
    assert not any(
        event == "image_reinsertion_multi_variant_block_fallback_to_text"
        and context.get("reason") == "multi_variant_placeholder_inside_hyperlink_or_non_run_child"
        for event, context in events
    )


def test_reinsert_inline_images_logs_multi_variant_specific_warning_when_block_build_fails(monkeypatch):
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

    events = []
    monkeypatch.setattr(image_reinsertion, "_build_replacement_blocks_from_fragments", lambda paragraph, fragments: [])
    monkeypatch.setattr(image_reinsertion, "log_event", lambda level, event, message, **context: events.append((event, context)))

    updated_bytes = reinsert_inline_images(buffer.getvalue(), [asset])
    updated_doc = Document(BytesIO(updated_bytes))

    assert updated_doc.paragraphs[0].text == "[[DOCX_IMAGE_img_001]]"
    assert any(
        event == "image_reinsertion_multi_variant_block_unresolved"
        and context.get("reason") == "multi_variant_block_builder_returned_no_output"
        for event, context in events
    )


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
    assert asset.resolved_delivery_payload().selected_variant == "semantic_redraw_direct"
    assert asset.resolved_delivery_payload().final_bytes == b"chosen"


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
    assert asset.resolved_delivery_payload().delivery_kind == "compare_all_variants"
    assert [insertion.variant_key for insertion in asset.resolved_delivery_payload().insertions] == [
        "safe",
        "semantic_redraw_direct",
        "semantic_redraw_structured",
    ]


def test_resolved_delivery_payload_uses_manual_review_insertions_when_enabled():
    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=b"original",
        mime_type="image/png",
        position_index=0,
        safe_bytes=b"safe",
        attempt_variants=[
            ImageVariantCandidate(mode="candidate1", bytes=b"candidate-1", mime_type="image/png"),
            ImageVariantCandidate(mode="candidate2", bytes=b"candidate-2", mime_type="image/png"),
        ],
    )
    asset.update_pipeline_metadata(preserve_all_variants_in_docx=True)

    payload = asset.resolved_delivery_payload()

    assert payload.delivery_kind == "manual_review_variants"
    assert [(insertion.label, insertion.bytes) for insertion in payload.insertions] == [
        ("safe", b"safe"),
        ("candidate1", b"candidate-1"),
        ("candidate2", b"candidate-2"),
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


def test_read_uploaded_docx_bytes_normalizes_legacy_doc_upload(monkeypatch):
    monkeypatch.setattr(document, "read_uploaded_file_bytes", lambda uploaded_file: b"legacy-binary")
    monkeypatch.setattr(document, "resolve_uploaded_filename", lambda uploaded_file: "legacy.doc")
    monkeypatch.setattr(
        document,
        "normalize_uploaded_document",
        lambda **kwargs: type("NormalizedDocument", (), {"content_bytes": b"converted-docx"})(),
    )

    assert document._read_uploaded_docx_bytes(object()) == b"converted-docx"
