"""Tiny PDFs written byte by byte for the PDF-import tests (spec 082).

Not a test module: the tests that need a real PDF -- one both pdfminer and pypdfium2 read -- build it here
instead of shipping a binary fixture. Coordinates are PDF user space (origin bottom-left, points). All
text is invented. Images are drawn by a ``cm`` that maps the unit square onto the given box.

Image kinds:
- ``jpeg_gray``        DCT stream in /DeviceGray -- the extractor emits it, and it looks like the page;
- ``jpeg_separation``  the same JPEG in a one-ink /Separation space whose tint 1 is black: the page shows
                       ``255 - sample``, the stored file shows ``sample`` (a negative);
- ``jpeg_devicen``     the same in a one-colourant /DeviceN space;
- ``jpeg_rgb``         DCT stream in /DeviceRGB;
- ``flate_gray``       a Flate bitmap -- the extractor does not emit it.
"""

from __future__ import annotations

import io
import zlib
from dataclasses import dataclass, field

_TINT_TO_GRAY = "<< /FunctionType 2 /Domain [0 1] /C0 [1] /C1 [0] /N 1 >>"
_COLOUR_SPACES = {
    "jpeg_gray": "/DeviceGray",
    "jpeg_rgb": "/DeviceRGB",
    "jpeg_separation": "[/Separation /Black /DeviceGray " + _TINT_TO_GRAY + "]",
    "jpeg_devicen": "[/DeviceN [/Black] /DeviceGray " + _TINT_TO_GRAY + "]",
    "flate_gray": "/DeviceGray",
}


@dataclass
class SyntheticImage:
    kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    pixels: tuple[int, int] = (40, 30)
    # ``gradient``: left-to-right ramp 0..255; ``dark``: every sample 40 (a dark-looking stored file).
    pattern: str = "gradient"


@dataclass
class SyntheticText:
    x: float
    y: float
    size: float
    text: str


@dataclass
class SyntheticPage:
    width: float = 400.0
    height: float = 600.0
    mediabox: tuple[float, float, float, float] | None = None
    cropbox: tuple[float, float, float, float] | None = None
    rotate: int = 0
    images: list[SyntheticImage] = field(default_factory=list)
    texts: list[SyntheticText] = field(default_factory=list)
    # Raw content-stream operators for vector paths, e.g. ``"0 g 50 50 20 20 re f"``.
    paths: list[str] = field(default_factory=list)


def _pixels(image: SyntheticImage, channels: int) -> bytes:
    w, h = image.pixels
    if image.pattern == "dark":
        row = bytes([40] * w)
    else:
        row = bytes((x * 255) // max(1, w - 1) for x in range(w))
    gray = row * h
    if channels == 1:
        return gray
    return bytes(value for value in gray for _ in range(channels))


def _image_stream(image: SyntheticImage) -> bytes:
    from PIL import Image

    w, h = image.pixels
    if image.kind == "flate_gray":
        data = zlib.compress(_pixels(image, 1))
        head = "<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 /Filter /FlateDecode /Length %d >>"
        return (head % (w, h, _COLOUR_SPACES[image.kind], len(data))).encode() + b"\nstream\n" + data + b"\nendstream"
    channels = 3 if image.kind == "jpeg_rgb" else 1
    mode = "RGB" if channels == 3 else "L"
    buffer = io.BytesIO()
    Image.frombytes(mode, (w, h), _pixels(image, channels)).save(buffer, format="JPEG", quality=95)
    data = buffer.getvalue()
    head = "<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>"
    return (head % (w, h, _COLOUR_SPACES[image.kind], len(data))).encode() + b"\nstream\n" + data + b"\nendstream"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(pages: list[SyntheticPage]) -> bytes:
    """A PDF with the given pages; every page shares one Helvetica font object."""

    objects: list[bytes] = []

    def add(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    catalog = add(b"")
    pages_obj = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    kids: list[int] = []
    for page in pages:
        names = []
        for index, image in enumerate(page.images):
            names.append(("Im%d" % index, add(_image_stream(image))))
        ops: list[str] = []
        ops.extend(page.paths)
        for (name, _ref), image in zip(names, page.images):
            ops.append("q %.3f 0 0 %.3f %.3f %.3f cm /%s Do Q" % (image.x1 - image.x0, image.y1 - image.y0, image.x0, image.y0, name))
        for text in page.texts:
            ops.append("BT /F1 %.2f Tf %.3f %.3f Td (%s) Tj ET" % (text.size, text.x, text.y, _escape(text.text)))
        content = "\n".join(ops).encode("latin-1")
        content_ref = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        mediabox = page.mediabox or (0.0, 0.0, page.width, page.height)
        entries = "/MediaBox [%s]" % " ".join("%.3f" % v for v in mediabox)
        if page.cropbox is not None:
            entries += " /CropBox [%s]" % " ".join("%.3f" % v for v in page.cropbox)
        if page.rotate:
            entries += " /Rotate %d" % page.rotate
        xobjects = " ".join("/%s %d 0 R" % (name, ref) for name, ref in names)
        resources = "<< /Font << /F1 %d 0 R >> /XObject << %s >> >>" % (font, xobjects)
        kids.append(add(("<< /Type /Page /Parent %d 0 R %s /Resources %s /Contents %d 0 R >>" % (
            pages_obj, entries, resources, content_ref)).encode()))
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj
    objects[pages_obj - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join("%d 0 R" % k for k in kids), len(kids))).encode()

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, payload in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + payload + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref))
    return out.getvalue()


def write_pdf(path, pages: list[SyntheticPage]):
    data = build_pdf(pages)
    with open(path, "wb") as handle:
        handle.write(data)
    return path
