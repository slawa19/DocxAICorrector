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
    PdfDiscoveredImage,
    PdfImageExtraction,
    PdfImageObject,
    extract_pdf_images_and_inventory,
)

__all__ = [
    "PdfDiscoveredImage",
    "PdfImageExtraction",
    "PdfImageObject",
    "PdfTextSpan",
    "PdfSourceImportReport",
    "PdfSourceImportResult",
    "TextLayerQualityReport",
    "build_paragraph_units_from_text_spans",
    "build_text_layer_quality_report",
    "extract_pdf_images_and_inventory",
    "unsupported_quality_report",
]
