from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

# The comparison probes PDFs through the optional pdfminer.six backend. Without it
# the tool reports "unsupported" instead of the ok/error paths this test asserts, so
# skip honestly rather than assert on a dependency-missing state.
pytest.importorskip("pdfminer")

from tools.compare_pdf_import_backends import build_pdf_import_backend_comparison


def _docx_bytes(path: Path, paragraphs: list[tuple[str, str | None]]) -> bytes:
    document = Document()
    for text, style in paragraphs:
        document.add_paragraph(text, style=style)
    output = path / "candidate.docx"
    document.save(output)
    return output.read_bytes()


def test_build_pdf_import_backend_comparison_summarizes_each_backend(tmp_path: Path) -> None:
    input_pdf = tmp_path / "source.pdf"
    input_pdf.write_bytes(b"%PDF- fake")
    libreoffice_docx = _docx_bytes(
        tmp_path,
        [
            ("1", None),
            ("CHAPTER ONE", "Heading 1"),
            ("Body text.", None),
        ],
    )
    text_layer_docx = _docx_bytes(
        tmp_path,
        [
            ("CHAPTER ONE", "Heading 1"),
            ("Body text.", None),
        ],
    )

    comparison = build_pdf_import_backend_comparison(
        input_pdf=input_pdf,
        converters={
            "libreoffice": lambda filename, content: (libreoffice_docx, "libreoffice"),
            "pdf_text_layer": lambda filename, content: (text_layer_docx, "pdf-text-layer"),
        },
    )

    backends = comparison["backends"]
    assert backends["libreoffice"]["status"] == "ok"
    assert backends["pdf_text_layer"]["status"] == "ok"
    assert backends["libreoffice"]["page_number_like_paragraph_count"] == 1
    assert backends["pdf_text_layer"]["page_number_like_paragraph_count"] == 0
    assert backends["pdf_text_layer"]["heading_count"] == 1
    assert backends["pdf_text_layer"]["markdown_emphasis_marker_count"] == 0
    assert backends["pdf_text_layer"]["docx_media_count"] == 0
    assert backends["pdf_text_layer"]["extracted_image_asset_count"] == 0
    assert backends["pdf_text_layer"]["direct_bold_run_count"] == 0
    assert comparison["text_layer_quality"]["status"] == "unsupported"
    assert comparison["pdf_image_objects"]["status"] in {"ok", "error"}
