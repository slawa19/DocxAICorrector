"""Spec 082 slice A: an emitted PDF image that is a NEGATIVE of what the page shows is replaced by a render
of its own page frame.

The trigger is a conjunction of a CAUSE and EVIDENCE, both general, neither tuned (acceptance round 3):

- cause -- a property of the PDF object: the image's colour space is an ink space (``Separation`` or
  ``DeviceN``, or ``Indexed`` over one of them). Its samples are amounts of ink, so a file that stores them
  as a picture shows the page inverted. This is the structural reason the stored bytes can be a negative;
- evidence -- the stored image (decoded as it will be delivered) and the render of its whole frame, both grey
  and at the same size, are ANTI-correlated: Pearson coefficient below zero, the sign and not a threshold. A
  label alone is not evidence: a ``/Decode`` array, the tint function, the alternate space or a special
  colourant can make an ink-space image right as stored (review round 1, finding 3).

Replaced only when BOTH hold. Measured on the four corpus PDFs (spec 082 research R25, R29): the 32
Rethinking Money photographs are one-ink ``Separation`` JPEGs at r = -0.997 ... -0.899; every other emitted
image is either not in an ink space or correlates positively. A correct image is replaced only if it is an
ink-space image extracted correctly (a compensating Decode or tint) AND something on the page this step does
not observe (vector paint, a clip, a blend) makes it anti-correlated with its frame -- two independent
coincidences. Observing everything a page can paint over an image was tried in review round 2 and dropped in
round 3: it has no end, and it made today's extraction depend on new interpreter code.

Text is never touched. An image stays exactly as emitted when: text or another image overlaps its frame (the
render would carry them); its dictionary names a ``/SMask`` or ``/Mask`` (where the mask is transparent the
page shows what is beneath, not the image); it is not placed by an upright axis-aligned scale (a rotated,
skewed or mirrored placement -- its pixel density along its own axes is not the box's, and a mirror changes
the spatial comparison); its page has a /UserUnit other than 1; its TRUE frame is not entirely inside the
visible page (a partial render would drop source pixels); a render with no fewer pixels than the source
would exceed the image pipeline's per-image budget; pdfminer and PDFium disagree about the page; or the
picture is flat (no variance: nothing to compare). Any failure while rendering, comparing or encoding one
image keeps that image's emitted bytes and logs an ERROR; the other images go on.
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
    PageGeometryMismatch,
    encode_frame_png,
    frame_geometry,
    open_pdf_for_rendering,
    read_page_geometry,
    render_frame,
)

DECLINE_TEXT_OVER_FRAME = "text_over_frame"
DECLINE_IMAGE_OVER_FRAME = "image_over_frame"
DECLINE_MASKED_IMAGE = "masked_image"
DECLINE_NOT_INK_SPACE = "not_ink_space"
DECLINE_UNSUPPORTED_PLACEMENT = "unsupported_placement"
DECLINE_UNREADABLE_SOURCE = "unreadable_source"
DECLINE_USER_UNIT = "user_unit"
DECLINE_OUTSIDE_CROP_BOX = "outside_crop_box"
DECLINE_EXCEEDS_PIXEL_BUDGET = "exceeds_pixel_budget"
DECLINE_PAGE_GEOMETRY_DISAGREES = "page_geometry_disagrees"
DECLINE_FLAT_IMAGE = "flat_image"

INK_SPACE_FAMILIES = frozenset({"Separation", "DeviceN"})

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
    checked: int
    replaced: int
    declined: int
    failed: int


def _box(item) -> tuple[float, float, float, float]:
    """The item's true top-origin frame: ``frame_box`` when the extractor recorded it (an image's ``top``
    is clamped to the page for the ordering key and may hide that the image reaches past the top edge)."""

    frame = getattr(item, "frame_box", None)
    if frame is not None:
        return (float(frame[0]), float(frame[1]), float(frame[2]), float(frame[3]))
    return (float(item.x0), float(item.top), float(item.x1), float(item.bottom))


def _overlap_area(a, b) -> float:
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0.0
    return width * height


def is_upright_scale(matrix) -> bool:
    """The image's unit square is placed by ``a 0 0 d e f`` with ``a, d > 0``: no rotation, skew or mirror."""

    if matrix is None or len(matrix) != 6:
        return False
    a, b, c, d = matrix[0], matrix[1], matrix[2], matrix[3]
    return b == 0 and c == 0 and a > 0 and d > 0


def is_ink_space(image: PdfImageObject) -> bool:
    """The cause half of the trigger. The extractor reads it from the colour-space array (``Indexed`` over an
    ink space included); a record built without it falls back to the family name."""

    if image.ink_space is not None:
        return bool(image.ink_space)
    return image.colour_space_family in INK_SPACE_FAMILIES


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
    """Which emitted images are checked against their page, and which are declined before rendering.

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
        if image.mask is not None:
            declines.append(FrameDecline(image, DECLINE_MASKED_IMAGE, image.mask))
            continue
        if not is_ink_space(image):
            declines.append(FrameDecline(image, DECLINE_NOT_INK_SPACE, str(image.colour_space_family)))
            continue
        matrix = getattr(image, "placement_matrix", None)
        if not is_upright_scale(matrix):
            declines.append(FrameDecline(image, DECLINE_UNSUPPORTED_PLACEMENT, str(matrix)[:_PREVIEW_CHARS]))
            continue
        width_pt = box[2] - box[0]
        height_pt = box[3] - box[1]
        source = _source_pixels(image)
        if source is None or width_pt <= 0 or height_pt <= 0:
            declines.append(FrameDecline(image, DECLINE_UNREADABLE_SOURCE))
            continue
        # The source's own pixel density (the placement is an upright scale, so the box IS the image's
        # extent): the render has no fewer pixels than the source on either axis.
        scale = max(source[0] / width_pt, source[1] / height_pt)
        candidates.append(FrameCandidate(image, source[0], source[1], scale))
    return FramePlan(candidates=tuple(candidates), declines=tuple(declines))


def _within_pixel_budget(geometry: FrameGeometry) -> bool:
    from docxaicorrector.image.analysis import MAX_IMAGE_DIMENSION_PX, MAX_IMAGE_MEGAPIXELS

    if geometry.width_px > MAX_IMAGE_DIMENSION_PX or geometry.height_px > MAX_IMAGE_DIMENSION_PX:
        return False
    return geometry.width_px * geometry.height_px <= MAX_IMAGE_MEGAPIXELS * 1_000_000


def correlation_with_page(image_bytes: bytes, rendered) -> float | None:
    """Pearson correlation of the stored picture and the rendered frame, both grey at the stored size.

    ``None`` when either is flat (zero variance): a picture with no variation has no sign to read."""

    import numpy
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as opened:
        stored = opened.convert("L")
    page = rendered.convert("L").resize(stored.size, Image.Resampling.BILINEAR)
    a = numpy.asarray(stored, dtype=numpy.float64).ravel()
    b = numpy.asarray(page, dtype=numpy.float64).ravel()
    a = a - a.mean()
    b = b - b.mean()
    denominator = float(numpy.sqrt((a * a).sum() * (b * b).sum()))
    if denominator == 0.0:
        return None
    return float((a * b).sum()) / denominator


def _key(image: PdfImageObject) -> tuple[int, int | None]:
    return (image.page_number, image.discovery_index)


def apply_frame_replacements(pdf_path: str | Path, extraction: PdfImageExtraction, plan: FramePlan) -> FrameOutcome:
    """Render each candidate's frame; replace the image when it is anti-correlated with the render."""

    declines: list[FrameDecline] = list(plan.declines)
    replacements: dict[tuple[int, int | None], PdfImageObject] = {}
    handled: set[tuple[int, int | None]] = set()
    checked = 0
    failed = 0
    if plan.candidates:
        try:
            page_geometries = read_page_geometry(pdf_path, {candidate.image.page_number for candidate in plan.candidates})
            with open_pdf_for_rendering(pdf_path) as document:
                for candidate in plan.candidates:
                    image = candidate.image
                    handled.add(_key(image))
                    page_geometry = page_geometries.get(image.page_number)
                    if page_geometry is None or page_geometry.user_unit != 1.0:
                        declines.append(FrameDecline(image, DECLINE_USER_UNIT if page_geometry else DECLINE_PAGE_GEOMETRY_DISAGREES))
                        continue
                    try:
                        geometry = frame_geometry(_box(image), crop=page_geometry.layout_cropbox, scale=candidate.scale)
                    except Exception as exc:  # noqa: BLE001 - the image stays as emitted
                        failed += 1
                        _log_render_failed(pdf_path, image, exc)
                        continue
                    if geometry is None:
                        declines.append(FrameDecline(image, DECLINE_OUTSIDE_CROP_BOX))
                        continue
                    if not _within_pixel_budget(geometry):
                        declines.append(FrameDecline(image, DECLINE_EXCEEDS_PIXEL_BUDGET))
                        continue
                    try:
                        rendered = render_frame(
                            document, page_number=image.page_number, page_geometry=page_geometry, geometry=geometry
                        )
                        correlation = correlation_with_page(image.image_bytes, rendered)
                    except PageGeometryMismatch as exc:
                        declines.append(FrameDecline(image, DECLINE_PAGE_GEOMETRY_DISAGREES, str(exc)))
                        continue
                    except Exception as exc:  # noqa: BLE001 - the image stays as emitted
                        failed += 1
                        _log_render_failed(pdf_path, image, exc)
                        continue
                    checked += 1
                    if correlation is None:
                        declines.append(FrameDecline(image, DECLINE_FLAT_IMAGE))
                        continue
                    if correlation >= 0:
                        continue  # the stored picture already looks like its page: keep it
                    try:
                        encoded = encode_frame_png(rendered, geometry)
                    except Exception as exc:  # noqa: BLE001 - the image stays as emitted; the rest go on
                        failed += 1
                        _log_render_failed(pdf_path, image, exc)
                        continue
                    replacements[_key(image)] = replace(
                        image,
                        image_bytes=encoded.png_bytes,
                        mime_type="image/png",
                        display_width_points=geometry.frame_width_points,
                        display_height_points=geometry.frame_height_points,
                        original_image_bytes=image.image_bytes,
                        original_mime_type=image.mime_type,
                    )
                    log_event(
                        logging.INFO,
                        "pdf_image_frame_rendered",
                        "PDF image replaced by a render of its page frame: the stored picture is a negative of the page.",
                        pdf_path=str(pdf_path),
                        page_number=image.page_number,
                        discovery_index=image.discovery_index,
                        box=[round(value, 1) for value in _box(image)],
                        colour_space=image.colour_space_family,
                        correlation=round(correlation, 4),
                        source_width_px=candidate.source_width_px,
                        source_height_px=candidate.source_height_px,
                        width_px=geometry.width_px,
                        height_px=geometry.height_px,
                        scale_dpi=round(geometry.scale * 72.0, 2),
                        bytes=len(encoded.png_bytes),
                        grayscale=encoded.grayscale,
                    )
        except Exception as exc:  # noqa: BLE001 - the document could not be read: unhandled candidates stay as emitted
            for candidate in plan.candidates:
                if _key(candidate.image) not in handled:
                    failed += 1
                    _log_render_failed(pdf_path, candidate.image, exc)
    for decline in declines:
        log_event(
            logging.INFO,
            "pdf_image_frame_render_declined",
            "PDF image kept as emitted: its page frame is not compared or rendered in its place.",
            pdf_path=str(pdf_path),
            page_number=decline.image.page_number,
            discovery_index=decline.image.discovery_index,
            box=[round(value, 1) for value in _box(decline.image)],
            colour_space=decline.image.colour_space_family,
            reason=decline.reason,
            detail=decline.detail[:_PREVIEW_CHARS],
        )
    images = tuple(replacements.get(_key(image), image) for image in extraction.images)
    return FrameOutcome(images=images, checked=checked, replaced=len(replacements), declined=len(declines), failed=failed)


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
