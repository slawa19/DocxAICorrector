"""Render a rectangle of a PDF page as the reader sees it (spec 082).

One source of truth for the page boxes: pdfminer, which resolves the inheritable ``MediaBox``,
``CropBox`` and ``Rotate`` through the page tree (``PDFPage.create_pages``) and is the engine that
measured every image box. pypdfium2's ``get_mediabox`` / ``get_cropbox`` read the page dictionary only
(spec 082 acceptance review, finding 2), so they are never used for geometry; PDFium's page size and
rotation, which its renderer derives with inheritance, are used only as a cross-check -- when the two
engines disagree about the page, nothing is rendered.

Two pure functions carry the geometry, so it is tested without a PDF:

- ``layout_cropbox`` puts the CropBox into pdfminer's layout space with the matrix pdfminer applies to
  the page (``pdfminer.pdfinterp.PDFPageInterpreter.process_page``);
- ``frame_geometry`` turns a pdfminer box that lies ENTIRELY inside the CropBox into whole pixels of the
  rendered CropBox, rounding outward -- the frame never has fewer pixels than ``box size x scale``. A box
  reaching outside the visible page is refused, not clipped: clipping would drop source pixels.

Rendering uses pypdfium2 (pinned in ``requirements.txt``), imported lazily. PDFium is not thread-safe
(pypdfium2 documentation, "Incompatibility with Threading"); production renders in the single-threaded
PDF parse child, but the in-process test seam runs the parse in a thread and up to two imports may run
at once, so every PDFium call happens under one module lock.
"""

from __future__ import annotations

import io
import math
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_PDFIUM_LOCK = threading.Lock()

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class PdfPageGeometry:
    """A page's boxes as pdfminer resolves them (inheritance included)."""

    mediabox: Box
    cropbox: Box
    rotation: int
    user_unit: float = 1.0

    @property
    def layout_cropbox(self) -> Box:
        return layout_cropbox(self.mediabox, self.cropbox, self.rotation)


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
class EncodedFrame:
    png_bytes: bytes
    grayscale: bool


class PageGeometryMismatch(RuntimeError):
    """pdfminer and PDFium disagree about the page: its frame is not rendered."""


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
    """``box`` and ``crop`` are top-origin pdfminer layout boxes. ``None`` unless ``box`` is non-empty and
    lies entirely inside ``crop`` (checked on the unrounded numbers)."""

    if scale <= 0 or box[2] <= box[0] or box[3] <= box[1]:
        return None
    if box[0] < crop[0] or box[1] < crop[1] or box[2] > crop[2] or box[3] > crop[3]:
        return None
    # pypdfium2 sizes the full-page bitmap as ceil(size x scale) (``PdfPage.render``).
    page_width_px = math.ceil((crop[2] - crop[0]) * scale)
    page_height_px = math.ceil((crop[3] - crop[1]) * scale)
    left = max(0, math.floor((box[0] - crop[0]) * scale))
    top = max(0, math.floor((box[1] - crop[1]) * scale))
    right = min(page_width_px, math.ceil((box[2] - crop[0]) * scale))
    bottom = min(page_height_px, math.ceil((box[3] - crop[1]) * scale))
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


def read_page_geometry(pdf_path: str | Path, page_numbers: Iterable[int]) -> dict[int, PdfPageGeometry]:
    """pdfminer's resolved boxes, rotation and ``UserUnit`` of the given 1-based pages."""

    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdftypes import resolve1

    wanted = set(page_numbers)
    result: dict[int, PdfPageGeometry] = {}
    if not wanted:
        return result
    last = max(wanted)
    with open(pdf_path, "rb") as handle:
        document = PDFDocument(PDFParser(handle))
        for number, page in enumerate(PDFPage.create_pages(document), start=1):
            if number > last:
                break
            if number not in wanted:
                continue
            try:
                user_unit = float(resolve1(page.attrs.get("UserUnit", 1.0)))
            except (TypeError, ValueError):
                user_unit = float("nan")
            mediabox = [float(v) for v in page.mediabox]
            cropbox = [float(v) for v in page.cropbox]
            result[number] = PdfPageGeometry(
                mediabox=(mediabox[0], mediabox[1], mediabox[2], mediabox[3]),
                cropbox=(cropbox[0], cropbox[1], cropbox[2], cropbox[3]),
                rotation=int(page.rotate or 0) % 360,
                user_unit=user_unit,
            )
    return result


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


def render_frame(document, *, page_number: int, page_geometry: PdfPageGeometry, geometry: FrameGeometry):
    """Render ``geometry`` of page ``page_number`` (1-based) and return an RGB ``PIL.Image``.

    ``page_geometry`` is pdfminer's. Raises ``PageGeometryMismatch`` when PDFium's page differs from it:
    in rotation, or in size by half a pixel at this scale or more -- the amount that would move the frame
    by a pixel."""

    page = document[page_number - 1]
    try:
        crop = page_geometry.layout_cropbox
        width_pt, height_pt = page.get_size()
        tolerance = 0.5 / geometry.scale
        rotation = int(page.get_rotation() or 0) % 360
        if rotation != page_geometry.rotation:
            raise PageGeometryMismatch(f"rotation {rotation} != {page_geometry.rotation}")
        if abs(width_pt - (crop[2] - crop[0])) >= tolerance or abs(height_pt - (crop[3] - crop[1])) >= tolerance:
            raise PageGeometryMismatch(
                f"size {width_pt:.3f}x{height_pt:.3f} != {crop[2] - crop[0]:.3f}x{crop[3] - crop[1]:.3f}"
            )
        # The full-page bitmap is sized by the renderer's own numbers (ceil(size x scale)); a frame that
        # touches the page edge must still fit inside it, or the crop would have to grow the page.
        page_width_px = math.ceil(width_pt * geometry.scale)
        page_height_px = math.ceil(height_pt * geometry.scale)
        if geometry.right_px > page_width_px or geometry.bottom_px > page_height_px:
            raise PageGeometryMismatch("frame reaches past the renderer's page bitmap")
        geometry = FrameGeometry(
            left_px=geometry.left_px,
            top_px=geometry.top_px,
            right_px=geometry.right_px,
            bottom_px=geometry.bottom_px,
            page_width_px=page_width_px,
            page_height_px=page_height_px,
            scale=geometry.scale,
        )
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
    return image


def encode_frame_png(image, geometry: FrameGeometry) -> EncodedFrame:
    """PNG with the render density in pHYs; greyscale when the three channels are identical."""

    red, green, blue = image.split()
    grayscale = red.tobytes() == green.tobytes() == blue.tobytes()
    if grayscale:
        image = red
    dpi = geometry.scale * 72.0
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", dpi=(dpi, dpi))
    return EncodedFrame(png_bytes=buffer.getvalue(), grayscale=grayscale)
