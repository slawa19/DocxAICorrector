import base64
import importlib.util
from io import BytesIO
from pathlib import Path

from docx import Document


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