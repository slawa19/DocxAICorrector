"""Extract reusable image files from PDF text-layer source documents."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from docxaicorrector.core.logger import log_event

# Defensive page budget for a *direct* call into this extractor. The primary
# resource budget lives in ``processing.processing_runtime`` and rejects
# over-budget documents before this function runs, but this belt-and-suspenders
# cap keeps a direct caller from iterating an unbounded page tree. Truncation is
# logged (never silent).
_MAX_PDF_IMAGE_SOURCE_PAGES = 2000


@dataclass(frozen=True)
class PdfImageObject:
    page_number: int
    x0: float
    top: float
    x1: float
    bottom: float
    page_height: float | None
    image_bytes: bytes
    mime_type: str | None
    source_index: int
    width_points: float | None = None
    height_points: float | None = None


def extract_pdf_images_with_pdfminer(pdf_path: str | Path) -> list[PdfImageObject]:
    """Extract embedded PDF images that are already stored as image files.

    This intentionally skips raw bitmap streams that would require raster
    reconstruction. The source-import bridge is a logical-content path, so
    unsupported image encodings should fall back to diagnostics rather than a
    fragile visual-layout conversion.
    """

    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTFigure, LTImage
    except ImportError as exc:  # pragma: no cover - depends on optional env
        raise RuntimeError("optional_dependency_missing:pdfminer.six") from exc

    images: list[PdfImageObject] = []
    discovered_count = 0
    skipped_no_image_bytes = 0
    skipped_unknown_mime = 0
    pages_truncated = False
    for page_index, page_layout in enumerate(extract_pages(str(pdf_path)), start=1):
        if page_index > _MAX_PDF_IMAGE_SOURCE_PAGES:
            pages_truncated = True
            log_event(
                logging.WARNING,
                "pdf_image_extraction_page_budget_exceeded",
                "PDF image extraction truncated: page budget exceeded (remaining pages not scanned for images).",
                pdf_path=str(pdf_path),
                max_pages=_MAX_PDF_IMAGE_SOURCE_PAGES,
            )
            break
        page_height = _coerce_optional_float(getattr(page_layout, "height", None))
        for image in _iter_pdfminer_images(page_layout, lt_image_type=LTImage, lt_figure_type=LTFigure):
            discovered_count += 1
            image_bytes = _extract_pdfminer_image_file_bytes(image)
            if not image_bytes:
                skipped_no_image_bytes += 1
                continue
            mime_type = _detect_image_mime_type(image_bytes)
            if mime_type is None:
                skipped_unknown_mime += 1
                continue
            top, bottom = _pdfminer_top_origin_bounds(
                y0=float(getattr(image, "y0", 0.0) or 0.0),
                y1=float(getattr(image, "y1", 0.0) or 0.0),
                page_height=page_height,
            )
            x0 = float(getattr(image, "x0", 0.0) or 0.0)
            x1 = float(getattr(image, "x1", x0) or x0)
            images.append(
                PdfImageObject(
                    page_number=page_index,
                    x0=x0,
                    top=top,
                    x1=x1,
                    bottom=bottom,
                    page_height=page_height,
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    source_index=max(0, (page_index - 1) * 10000 + int(round(top))),
                    width_points=max(0.0, x1 - x0),
                    height_points=max(0.0, bottom - top),
                )
            )
    emitted_count = len(images)
    skipped_count = discovered_count - emitted_count
    if discovered_count > emitted_count:
        # Discovered images that never became emittable objects are a silent
        # image-loss signal; surface it at WARNING so it is observable.
        log_event(
            logging.WARNING,
            "pdf_image_extraction_dropped_images",
            "PDF images were discovered but not emitted; possible silent image loss.",
            pdf_path=str(pdf_path),
            discovered=discovered_count,
            emitted=emitted_count,
            skipped=skipped_count,
            skipped_no_image_bytes=skipped_no_image_bytes,
            skipped_unknown_mime=skipped_unknown_mime,
            pages_truncated=pages_truncated,
        )
    else:
        log_event(
            logging.INFO,
            "pdf_image_extraction_summary",
            "PDF image extraction completed.",
            pdf_path=str(pdf_path),
            discovered=discovered_count,
            emitted=emitted_count,
            pages_truncated=pages_truncated,
        )
    return sorted(images, key=lambda item: (item.page_number, item.top, item.x0))


def _iter_pdfminer_images(element, *, lt_image_type: type, lt_figure_type: type) -> Iterable[object]:
    if isinstance(element, lt_image_type):
        yield element
        return
    if isinstance(element, lt_figure_type) or hasattr(element, "__iter__"):
        try:
            children = list(element)
        except TypeError:
            return
        for child in children:
            yield from _iter_pdfminer_images(
                child,
                lt_image_type=lt_image_type,
                lt_figure_type=lt_figure_type,
            )


def _extract_pdfminer_image_file_bytes(image: object) -> bytes | None:
    stream = getattr(image, "stream", None)
    if stream is None:
        return None
    for method_name in ("get_rawdata", "get_data"):
        method = getattr(stream, method_name, None)
        if method is None:
            continue
        try:
            data = method()
        except Exception:
            continue
        if isinstance(data, bytes) and data:
            return data
    return None


def _detect_image_mime_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def _pdfminer_top_origin_bounds(
    *,
    y0: float,
    y1: float,
    page_height: float | None,
) -> tuple[float, float]:
    if not page_height or page_height <= 0:
        return float(y1), float(y0)
    top = max(0.0, page_height - float(y1))
    bottom = max(top, page_height - float(y0))
    return top, bottom


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
