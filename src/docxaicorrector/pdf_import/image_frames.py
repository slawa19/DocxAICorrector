"""Spec 082 slice A: an emitted PDF image whose stored bytes are not what the page shows is replaced by a
render of its own page frame.

The trigger is a property of the PDF format, with no threshold: the samples of an image in a
``Separation`` or ``DeviceN`` colour space are tints of inks, not light (PDF 32000-1, 8.6.6.4-5), so the
JPEG the extractor hands over as it is shows a negative. Measured 2026-11-13 on the four corpus PDFs
(spec 082 research R18): all 44 such images of one book were negatives; no other emitted image differed
from its page in a way a format property names.

Text is never touched. A replacement is declined -- the image stays exactly as emitted -- when a text
line or another image overlaps its frame by a positive area (a render would carry foreign text or a
foreign picture), when the frame lies outside the CropBox, or when a render with no fewer pixels than the
source would exceed the image pipeline's per-image budget. A render that raises keeps the original bytes
and logs an ERROR; nothing is lost either way.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from docxaicorrector.core.logger import log_event
from docxaicorrector.pdf_import.images import PdfDiscoveredImage, PdfImageExtraction, PdfImageObject
from docxaicorrector.pdf_import.page_render import (
    FrameGeometry,
    frame_geometry,
    open_pdf_for_rendering,
    render_frame,
)

INK_COLOUR_SPACE_FAMILIES = frozenset({"Separation", "DeviceN"})

DECLINE_TEXT_OVER_FRAME = "text_over_frame"
DECLINE_IMAGE_OVER_FRAME = "image_over_frame"
DECLINE_EXCEEDS_PIXEL_BUDGET = "exceeds_pixel_budget"
DECLINE_OUTSIDE_CROP_BOX = "outside_crop_box"
DECLINE_UNREADABLE_SOURCE = "unreadable_source"

_PREVIEW_CHARS = 120


@dataclass(frozen=True)
class FrameCandidate:
    image: PdfImageObject
    source_width_px: int
    source_height_px: int
    scale: float


@dataclass(frozen=True)
class FrameDecline:
    image: PdfImageObject
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class FramePlan:
    candidates: tuple[FrameCandidate, ...]
    declines: tuple[FrameDecline, ...]


@dataclass(frozen=True)
class FrameOutcome:
    images: tuple[PdfImageObject, ...]
    replaced: int
    declined: int
    failed: int


def colour_space_is_ink(family: str | None) -> bool:
    return family in INK_COLOUR_SPACE_FAMILIES


def _box(item) -> tuple[float, float, float, float]:
    return (float(item.x0), float(item.top), float(item.x1), float(item.bottom))


def _overlap_area(a, b) -> float:
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0.0
    return width * height


def _source_pixels(image: PdfImageObject) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(image.image_bytes)) as opened:
            width, height = opened.size
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return int(width), int(height)


def plan_frame_replacements(extraction: PdfImageExtraction, spans: Sequence[object]) -> FramePlan:
    """Which emitted images are candidates, and which candidates are declined before rendering.

    Pure: reads the inventory, the spans and the image file headers only."""

    spans_by_page: dict[int, list[object]] = {}
    for span in spans:
        if str(getattr(span, "text", "") or "").strip():
            spans_by_page.setdefault(int(getattr(span, "page_number")), []).append(span)
    discovered_by_page: dict[int, list[PdfDiscoveredImage]] = {}
    for item in extraction.discovered:
        discovered_by_page.setdefault(item.page_number, []).append(item)

    candidates: list[FrameCandidate] = []
    declines: list[FrameDecline] = []
    for image in extraction.images:
        if not colour_space_is_ink(getattr(image, "colour_space_family", None)):
            continue
        box = _box(image)
        text_over = next((span for span in spans_by_page.get(image.page_number, []) if _overlap_area(box, _box(span)) > 0), None)
        if text_over is not None:
            declines.append(FrameDecline(image, DECLINE_TEXT_OVER_FRAME, str(getattr(text_over, "text", ""))[:_PREVIEW_CHARS]))
            continue
        image_over = next(
            (
                other
                for other in discovered_by_page.get(image.page_number, [])
                if other.discovery_index != image.discovery_index and _overlap_area(box, _box(other)) > 0
            ),
            None,
        )
        if image_over is not None:
            declines.append(
                FrameDecline(image, DECLINE_IMAGE_OVER_FRAME, f"page {image_over.page_number} image {image_over.discovery_index}")
            )
            continue
        width_pt = box[2] - box[0]
        height_pt = box[3] - box[1]
        source = _source_pixels(image)
        if source is None or width_pt <= 0 or height_pt <= 0:
            declines.append(FrameDecline(image, DECLINE_UNREADABLE_SOURCE))
            continue
        # The source's own pixel density, so the render has no fewer pixels than the source (FR-A5).
        scale = max(source[0] / width_pt, source[1] / height_pt)
        candidates.append(FrameCandidate(image, source[0], source[1], scale))
    return FramePlan(candidates=tuple(candidates), declines=tuple(declines))


def _within_pixel_budget(geometry: FrameGeometry) -> bool:
    from docxaicorrector.image.analysis import MAX_IMAGE_DIMENSION_PX, MAX_IMAGE_MEGAPIXELS

    if geometry.width_px > MAX_IMAGE_DIMENSION_PX or geometry.height_px > MAX_IMAGE_DIMENSION_PX:
        return False
    return geometry.width_px * geometry.height_px <= MAX_IMAGE_MEGAPIXELS * 1_000_000


def _key(image: PdfImageObject) -> tuple[int, int | None]:
    return (image.page_number, image.discovery_index)


def apply_frame_replacements(pdf_path: str | Path, extraction: PdfImageExtraction, plan: FramePlan) -> FrameOutcome:
    """Render each candidate's frame and swap its bytes; log one event per candidate."""

    declines: list[FrameDecline] = list(plan.declines)
    replacements: dict[tuple[int, int | None], PdfImageObject] = {}
    handled: set[tuple[int, int | None]] = set()
    failed = 0
    if plan.candidates:
        try:
            with open_pdf_for_rendering(pdf_path) as document:
                for candidate in plan.candidates:
                    image = candidate.image
                    handled.add(_key(image))
                    reason_box: list[str] = []

                    def geometry_for_crop(crop, image=image, candidate=candidate, reason_box=reason_box):
                        geometry = frame_geometry(_box(image), crop=crop, scale=candidate.scale)
                        if geometry is None:
                            reason_box.append(DECLINE_OUTSIDE_CROP_BOX)
                            return None
                        if not _within_pixel_budget(geometry):
                            reason_box.append(DECLINE_EXCEEDS_PIXEL_BUDGET)
                            return None
                        return geometry

                    try:
                        rendered = render_frame(document, page_number=image.page_number, geometry_for_crop=geometry_for_crop)
                    except Exception as exc:  # noqa: BLE001 - the image stays as emitted
                        failed += 1
                        _log_render_failed(pdf_path, image, exc)
                        continue
                    if rendered is None:
                        declines.append(FrameDecline(image, reason_box[0] if reason_box else DECLINE_OUTSIDE_CROP_BOX))
                        continue
                    geometry = rendered.geometry
                    replacements[_key(image)] = replace(
                        image,
                        image_bytes=rendered.png_bytes,
                        mime_type="image/png",
                        display_width_points=geometry.frame_width_points,
                        display_height_points=geometry.frame_height_points,
                        original_image_bytes=image.image_bytes,
                        original_mime_type=image.mime_type,
                    )
                    log_event(
                        logging.INFO,
                        "pdf_image_frame_rendered",
                        "PDF image replaced by a render of its page frame (stored bytes are ink tints, not the page's look).",
                        pdf_path=str(pdf_path),
                        page_number=image.page_number,
                        discovery_index=image.discovery_index,
                        box=[round(value, 1) for value in _box(image)],
                        colour_space=image.colour_space_family,
                        source_width_px=candidate.source_width_px,
                        source_height_px=candidate.source_height_px,
                        width_px=geometry.width_px,
                        height_px=geometry.height_px,
                        scale_dpi=round(geometry.scale * 72.0, 2),
                        bytes=len(rendered.png_bytes),
                        grayscale=rendered.grayscale,
                    )
        except Exception as exc:  # noqa: BLE001 - the document could not be opened: unhandled candidates stay as emitted
            for candidate in plan.candidates:
                if _key(candidate.image) not in handled:
                    failed += 1
                    _log_render_failed(pdf_path, candidate.image, exc)
    for decline in declines:
        log_event(
            logging.INFO,
            "pdf_image_frame_render_declined",
            "PDF image kept as emitted: its page frame is not rendered in its place.",
            pdf_path=str(pdf_path),
            page_number=decline.image.page_number,
            discovery_index=decline.image.discovery_index,
            box=[round(value, 1) for value in _box(decline.image)],
            colour_space=decline.image.colour_space_family,
            reason=decline.reason,
            detail=decline.detail[:_PREVIEW_CHARS],
        )
    images = tuple(replacements.get(_key(image), image) for image in extraction.images)
    return FrameOutcome(images=images, replaced=len(replacements), declined=len(declines), failed=failed)


def _log_render_failed(pdf_path: str | Path, image: PdfImageObject, exc: BaseException) -> None:
    log_event(
        logging.ERROR,
        "pdf_image_frame_render_failed",
        "Rendering the page frame of a PDF image failed; the image keeps its emitted bytes.",
        pdf_path=str(pdf_path),
        page_number=image.page_number,
        discovery_index=image.discovery_index,
        box=[round(value, 1) for value in _box(image)],
        error_type=exc.__class__.__name__,
        error_message=str(exc)[:_PREVIEW_CHARS],
    )
