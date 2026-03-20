import base64
import importlib.util
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


PNG_BYTES = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII=")


def _load_validation_module():
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "tests" / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py"
    spec = importlib.util.spec_from_file_location("run_lietaer_validation", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load run_lietaer_validation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _docx_bytes(document: Document) -> bytes:
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _append_numbering_level(level: str, fmt: str) -> OxmlElement:
    lvl = OxmlElement("w:lvl")
    lvl.set(qn("w:ilvl"), level)

    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    lvl.append(start)

    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), fmt)
    lvl.append(num_fmt)

    lvl_text = OxmlElement("w:lvlText")
    lvl_text.set(
        qn("w:val"),
        "%1." if fmt in {"decimal", "lowerLetter", "upperLetter", "lowerRoman", "upperRoman"} else "•",
    )
    lvl.append(lvl_text)
    return lvl


def _append_multilevel_numbering_definition(document: Document, *, num_id: str, abstract_num_id: str) -> None:
    numbering_root = document.part.numbering_part.element

    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), abstract_num_id)
    abstract_num.append(_append_numbering_level("0", "bullet"))
    abstract_num.append(_append_numbering_level("1", "decimal"))
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


def test_evaluate_lietaer_acceptance_detects_caption_heading_regression(tmp_path):
    validation = _load_validation_module()
    image_path = tmp_path / "caption_image.png"
    image_path.write_bytes(PNG_BYTES)

    source_doc = Document()
    source_doc.add_paragraph().add_run().add_picture(str(image_path))
    source_doc.add_paragraph("Рисунок 1. Подпись")

    output_doc = Document()
    output_doc.add_paragraph().add_run().add_picture(str(image_path))
    output_doc.add_paragraph("Рисунок 1. Подпись", style="Heading 1")

    report = {
        "result": "succeeded",
        "output_artifacts": {
            "output_docx_openable": True,
            "output_contains_placeholder_markup": False,
        },
        "formatting_diagnostics": [],
    }

    acceptance = validation.evaluate_lietaer_acceptance(
        report,
        source_docx_bytes=_docx_bytes(source_doc),
        output_docx_bytes=_docx_bytes(output_doc),
    )

    assert acceptance["passed"] is False
    assert "captions_not_promoted_to_headings" in acceptance["failed_checks"]


def test_evaluate_lietaer_acceptance_passes_for_clean_structural_output(tmp_path):
    validation = _load_validation_module()
    image_path = tmp_path / "clean_image.png"
    image_path.write_bytes(PNG_BYTES)

    source_doc = Document()
    source_doc.add_paragraph("Глава 1", style="Heading 1")
    source_doc.add_paragraph("Первый пункт", style="List Number")
    source_doc.add_paragraph("Второй пункт", style="List Number")
    source_doc.add_paragraph().add_run().add_picture(str(image_path))
    source_doc.add_paragraph("Рисунок 1. Корректная подпись")

    output_doc = Document()
    output_doc.add_paragraph("Глава 1", style="Heading 1")
    output_doc.add_paragraph("Первый пункт", style="List Number")
    output_doc.add_paragraph("Второй пункт", style="List Number")
    output_doc.add_paragraph().add_run().add_picture(str(image_path))
    output_doc.add_paragraph("Рисунок 1. Корректная подпись")

    report = {
        "result": "succeeded",
        "output_artifacts": {
            "output_docx_openable": True,
            "output_contains_placeholder_markup": False,
        },
        "formatting_diagnostics": [],
    }

    acceptance = validation.evaluate_lietaer_acceptance(
        report,
        source_docx_bytes=_docx_bytes(source_doc),
        output_docx_bytes=_docx_bytes(output_doc),
    )

    assert acceptance["passed"] is True
    assert acceptance["failed_checks"] == []


def test_count_ordered_word_numbered_paragraphs_handles_multilevel_numbering() -> None:
    validation = _load_validation_module()

    document = Document()
    _append_multilevel_numbering_definition(document, num_id="9001", abstract_num_id="9000")

    bullet_paragraph = document.add_paragraph("Маркер")
    first_ordered_paragraph = document.add_paragraph("Первый пункт")
    second_ordered_paragraph = document.add_paragraph("Второй пункт")

    _attach_numbering(bullet_paragraph, num_id="9001", ilvl="0")
    _attach_numbering(first_ordered_paragraph, num_id="9001", ilvl="1")
    _attach_numbering(second_ordered_paragraph, num_id="9001", ilvl="1")

    assert validation._count_ordered_word_numbered_paragraphs(document) == 2


def test_extract_run_formatting_diagnostics_paths_prefers_current_run_artifacts() -> None:
    validation = _load_validation_module()

    event_log = [
        {
            "event_id": "formatting_diagnostics_artifacts_detected",
            "context": {"artifact_paths": [".run\\formatting_diagnostics\\older.json"]},
        },
        {
            "event_id": "formatting_diagnostics_artifacts_detected",
            "context": {
                "artifact_paths": [
                    ".run\\formatting_diagnostics\\normalize_current.json",
                    ".run\\formatting_diagnostics\\preserve_current.json",
                ]
            },
        },
    ]

    assert validation._extract_run_formatting_diagnostics_paths(event_log) == [
        ".run\\formatting_diagnostics\\normalize_current.json",
        ".run\\formatting_diagnostics\\preserve_current.json",
    ]