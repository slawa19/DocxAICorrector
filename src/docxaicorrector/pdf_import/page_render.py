"""Render a rectangle of a PDF page as the reader sees it (spec 082).

Two pure functions carry all the geometry, so it is tested without a PDF:

- ``layout_cropbox`` puts the page's CropBox into pdfminer's layout space, using the same matrix
  pdfminer applies to the page (``pdfminer.pdfinterp.PDFPageInterpreter.process_page``), so a
  rotated page is handled the way its text and images were measured;
- ``frame_geometry`` turns a pdfminer box into whole pixels of the rendered CropBox, rounding
  OUTWARD -- the rendered frame never has fewer pixels than ``box size x scale`` -- and clipping to
  the CropBox, which is all the renderer can draw.

Rendering uses pypdfium2 (pinned in ``requirements.txt``), imported lazily. PDFium is not
thread-safe (pypdfium2 documentation, "Incompatibility with Threading"); production renders in the
single-threaded PDF parse child, but the in-process test seam runs the parse in a thread and up to
two imports may run at once, so every PDFium call happens under one module lock.
"""

from __future__ import annotations

import io
import math
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_PDFIUM_LOCK = threading.Lock()

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class FrameGeometry:
    """A frame in whole pixels of the rendered CropBox at ``scale`` pixels per point."""

    left_px: int
    top_px: int
    right_px: int
    bottom_px: int
    page_width_px: int
    page_height_px: int
    scale: float

    @property
    def width_px(self) -> int:
        return self.right_px - self.left_px

    @property
    def height_px(self) -> int:
        return self.bottom_px - self.top_px

    @property
    def frame_width_points(self) -> float:
        return self.width_px / self.scale

    @property
    def frame_height_points(self) -> float:
        return self.height_px / self.scale


@dataclass(frozen=True)
class RenderedFrame:
    png_bytes: bytes
    geometry: FrameGeometry
    grayscale: bool


def _rotation_ctm(mediabox: Box, rotation: int) -> tuple[float, float, float, float, float, float]:
    x0, y0, x1, y1 = mediabox
    rotation = rotation % 360
    if rotation == 90:
        return (0, -1, 1, 0, -y0, x1)
    if rotation == 180:
        return (-1, 0, 0, -1, x1, y1)
    if rotation == 270:
        return (0, 1, -1, 0, y1, -x0)
    return (1, 0, 0, 1, -x0, -y0)


def _apply(ctm, point: tuple[float, float]) -> tuple[float, float]:
    a, b, c, d, e, f = ctm
    x, y = point
    return (a * x + c * y + e, b * x + d * y + f)


def layout_cropbox(mediabox: Box, cropbox: Box, rotation: int) -> Box:
    """The CropBox as a top-origin box ``(x0, top, x1, bottom)`` in pdfminer's layout space."""

    ctm = _rotation_ctm(mediabox, rotation)
    mx = [_apply(ctm, (mediabox[0], mediabox[1])), _apply(ctm, (mediabox[2], mediabox[3]))]
    layout_height = abs(mx[0][1] - mx[1][1])
    corners = [_apply(ctm, (x, y)) for x in (cropbox[0], cropbox[2]) for y in (cropbox[1], cropbox[3])]
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    return (min(xs), layout_height - max(ys), max(xs), layout_height - min(ys))


def frame_geometry(box: Box, *, crop: Box, scale: float) -> FrameGeometry | None:
    """``box`` and ``crop`` are top-origin pdfminer layout boxes; ``None`` when nothing of ``box`` is
    inside ``crop`` (or the box is empty)."""

    if scale <= 0:
        return None
    crop_width = crop[2] - crop[0]
    crop_height = crop[3] - crop[1]
    # pypdfium2 sizes the full-page bitmap as ceil(size x scale) (``PdfPage.render``).
    page_width_px = math.ceil(crop_width * scale)
    page_height_px = math.ceil(crop_height * scale)
    left = max(0, math.floor((box[0] - crop[0]) * scale))
    top = max(0, math.floor((box[1] - crop[1]) * scale))
    right = min(page_width_px, math.ceil((box[2] - crop[0]) * scale))
    bottom = min(page_height_px, math.ceil((box[3] - crop[1]) * scale))
    if right <= left or bottom <= top:
        return None
    return FrameGeometry(
        left_px=left,
        top_px=top,
        right_px=right,
        bottom_px=bottom,
        page_width_px=page_width_px,
        page_height_px=page_height_px,
        scale=scale,
    )


def pdfium_crop_amounts(geometry: FrameGeometry) -> tuple[float, float, float, float]:
    """The ``crop`` argument of ``PdfPage.render`` that yields exactly ``geometry``'s pixels.

    pypdfium2 turns each crop amount ``c`` into ``ceil(c x scale)`` pixels; passing
    ``(pixels - 0.5) / scale`` makes that exact whatever the floating-point error."""

    def amount(pixels: int) -> float:
        return 0.0 if pixels <= 0 else (pixels - 0.5) / geometry.scale

    return (
        amount(geometry.left_px),
        amount(geometry.page_height_px - geometry.bottom_px),
        amount(geometry.page_width_px - geometry.right_px),
        amount(geometry.top_px),
    )


def page_layout_cropbox(page) -> Box:
    """``layout_cropbox`` for an open pypdfium2 page."""

    return layout_cropbox(tuple(page.get_mediabox()), tuple(page.get_cropbox()), int(page.get_rotation() or 0))


@contextmanager
def open_pdf_for_rendering(pdf_path: str | Path) -> Iterator[object]:
    """Open the PDF with pypdfium2 and hold the module lock for the whole session."""

    import pypdfium2

    with _PDFIUM_LOCK:
        document = pypdfium2.PdfDocument(str(pdf_path))
        try:
            yield document
        finally:
            document.close()


def render_frame(document, *, page_number: int, geometry_for_crop) -> RenderedFrame | None:
    """Render the frame ``geometry_for_crop(crop_box)`` of page ``page_number`` (1-based).

    ``geometry_for_crop`` receives the page's CropBox in layout space and returns a ``FrameGeometry``
    or ``None`` (nothing to render) -- the caller decides scale and budget, this function only draws.
    """

    page = document[page_number - 1]
    try:
        geometry = geometry_for_crop(page_layout_cropbox(page))
        if geometry is None:
            return None
        bitmap = page.render(
            scale=geometry.scale,
            crop=pdfium_crop_amounts(geometry),
            draw_annots=False,
            may_draw_forms=False,
        )
        image = bitmap.to_pil().convert("RGB")
    finally:
        page.close()
    if image.size != (geometry.width_px, geometry.height_px):
        raise RuntimeError(
            f"pdf_frame_render_size_mismatch:{image.size}!=({geometry.width_px}, {geometry.height_px})"
        )
    return encode_frame_png(image, geometry)


def encode_frame_png(image, geometry: FrameGeometry) -> RenderedFrame:
    """PNG with the render density in pHYs; greyscale when the three channels are identical."""

    red, green, blue = image.split()
    grayscale = red.tobytes() == green.tobytes() == blue.tobytes()
    if grayscale:
        image = red
    dpi = geometry.scale * 72.0
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", dpi=(dpi, dpi))
    return RenderedFrame(png_bytes=buffer.getvalue(), geometry=geometry, grayscale=grayscale)
