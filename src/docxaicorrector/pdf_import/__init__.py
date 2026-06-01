"""Deterministic PDF source-import helpers."""

from docxaicorrector.pdf_import.text_layer_quality import (
    PdfTextSpan,
    TextLayerQualityReport,
    build_text_layer_quality_report,
    unsupported_quality_report,
)
from docxaicorrector.pdf_import.logical_import import (
    PdfSourceImportReport,
    PdfSourceImportResult,
    build_paragraph_units_from_text_spans,
)
from docxaicorrector.pdf_import.images import (
    PdfImageObject,
    extract_pdf_images_with_pdfminer,
)

__all__ = [
    "PdfImageObject",
    "PdfTextSpan",
    "PdfSourceImportReport",
    "PdfSourceImportResult",
    "TextLayerQualityReport",
    "build_paragraph_units_from_text_spans",
    "build_text_layer_quality_report",
    "extract_pdf_images_with_pdfminer",
    "unsupported_quality_report",
]
