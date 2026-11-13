"""Spec 082 slice A: page-frame geometry and rendering (``pdf_import/page_render.py``).

The pure geometry is tested on numbers; the renderer on tiny PDFs built by ``tests/pdf_synthetic.py``
and read back through pdfminer, so every test checks the SAME coordinates the importer measures.
Mutation notes name the condition whose removal makes a test fail (spec 082 SC-A4).
"""

from __future__ import annotations

import io
import math
import threading

import pytest
from PIL import Image

from docxaicorrector.pdf_import.page_render import (
    FrameGeometry,
    PageGeometryMismatch,
    encode_frame_png,
    frame_geometry,
    layout_cropbox,
    open_pdf_for_rendering,
    pdfium_crop_amounts,
    read_page_geometry,
    render_frame,
)
from pdf_synthetic import SyntheticImage, SyntheticPage, SyntheticText, write_pdf

pytestmark = pytest.mark.unit_contract


def _layout_rects(pdf_path):
    """Top-origin boxes of the filled rectangles pdfminer finds on page 1."""

    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTCurve

    layout = next(iter(extract_pages(str(pdf_path))))
    height = layout.height
    return [(r.x0, height - r.y1, r.x1, height - r.y0) for r in layout if isinstance(r, LTCurve)]


# --------------------------------------------------------------------------- smoke


def test_synthetic_pdf_is_read_by_pdfminer_and_rendered_by_pdfium(tmp_path) -> None:
    from docxaicorrector.pdf_import.text_layer_quality import extract_pdf_text_spans_with_pdfminer
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTImage

    path = write_pdf(
        tmp_path / "smoke.pdf",
        [
            SyntheticPage(
                images=[SyntheticImage("jpeg_gray", 60, 300, 180, 420)],
                texts=[SyntheticText(40, 520, 11, "An invented body sentence for the smoke test.")],
            )
        ],
    )
    spans = extract_pdf_text_spans_with_pdfminer(path)
    assert [(span.text, round(span.font_size or 0)) for span in spans] == [("An invented body sentence for the smoke test.", 11)]

    def walk(element):
        for child in element:
            if isinstance(child, LTImage):
                yield child
            elif hasattr(child, "__iter__"):
                yield from walk(child)

    images = list(walk(next(iter(extract_pages(str(path))))))
    assert [(round(i.x0), round(i.y0), round(i.x1), round(i.y1)) for i in images] == [(60, 300, 180, 420)]
    with open_pdf_for_rendering(path) as document:
        page = document[0]  # type: ignore[index]
        assert page.render(scale=1.0).to_pil().size == (400, 600)


# --------------------------------------------------------------------------- pure geometry


def test_layout_cropbox_without_rotation_is_the_cropbox_measured_from_the_mediabox_top_left() -> None:
    assert layout_cropbox((0, 0, 400, 600), (20, 30, 380, 570), 0) == (20, 30, 380, 570)
    # A MediaBox that does not start at the origin: pdfminer measures from its lower-left corner.
    assert layout_cropbox((10, -5, 410, 595), (30, 25, 390, 565), 0) == (20, 30, 380, 570)


@pytest.mark.parametrize(
    ("rotation", "expected"),
    [
        (90, (30, 20, 570, 380)),
        (180, (20, 30, 380, 570)),
        (270, (30, 20, 570, 380)),
    ],
)
def test_layout_cropbox_follows_pdfminer_rotation(rotation, expected) -> None:
    box = layout_cropbox((0, 0, 400, 600), (20, 30, 380, 570), rotation)
    assert tuple(round(v, 6) for v in box) == expected


def test_frame_geometry_rounds_outward_so_the_frame_never_has_fewer_pixels() -> None:
    # Mutation: rounding the edges to nearest (round instead of floor/ceil) makes this fail.
    crop = (0.0, 0.0, 400.0, 600.0)
    for scale in (1.0, 150.11 / 72, 217.5 / 72, 3.3333):
        for x0 in (10.0, 10.3, 38.07, 99.999):
            box = (x0, 28.8, x0 + 205.49, 136.83)
            geometry = frame_geometry(box, crop=crop, scale=scale)
            assert geometry is not None
            assert geometry.width_px >= (box[2] - box[0]) * scale - 1e-9
            assert geometry.height_px >= (box[3] - box[1]) * scale - 1e-9
            assert geometry.left_px == math.floor(box[0] * scale)
            assert geometry.right_px == math.ceil(box[2] * scale)


def test_frame_geometry_is_measured_from_the_cropbox() -> None:
    crop = (20.0, 30.0, 380.0, 570.0)
    inside = frame_geometry((120.0, 130.0, 220.0, 180.0), crop=crop, scale=2.0)
    assert inside is not None
    assert (inside.left_px, inside.top_px, inside.right_px, inside.bottom_px) == (200, 200, 400, 300)
    assert (inside.page_width_px, inside.page_height_px) == (720, 1080)
    assert (inside.frame_width_points, inside.frame_height_points) == (100.0, 50.0)
    # A frame on the CropBox edge is inside.
    assert frame_geometry((20.0, 30.0, 380.0, 570.0), crop=crop, scale=2.0) is not None
    assert frame_geometry((100.0, 100.0, 100.0, 140.0), crop=crop, scale=2.0) is None


@pytest.mark.parametrize(
    "box",
    [
        (0.0, 0.0, 100.0, 100.0),       # over the top-left corner
        (19.99, 100.0, 120.0, 200.0),   # a hair over the left edge
        (100.0, 500.0, 200.0, 570.01),  # a hair over the bottom edge
        (390.0, 10.0, 399.0, 20.0),     # entirely outside
    ],
)
def test_a_frame_not_entirely_inside_the_cropbox_is_refused_not_clipped(box) -> None:
    """Acceptance review finding 1: clipping kept 160x140 of a 200x200 frame (56 % of the source).
    Mutation: dropping the inside check returns a clipped geometry for the first three boxes."""
    assert frame_geometry(box, crop=(20.0, 30.0, 380.0, 570.0), scale=2.0) is None


def test_pdfium_crop_amounts_give_exactly_the_geometry_pixels() -> None:
    for scale in (1.0, 2.0848, 3.0208333, 6.4166):
        geometry = frame_geometry((38.07, 28.83, 243.56, 136.83), crop=(2.32, 15.68, 387.52, 638.48), scale=scale)
        assert geometry is not None
        crop = pdfium_crop_amounts(geometry)
        pixels = [math.ceil(c * scale) for c in crop]
        assert pixels == [
            geometry.left_px,
            geometry.page_height_px - geometry.bottom_px,
            geometry.page_width_px - geometry.right_px,
            geometry.top_px,
        ]


def test_encode_frame_png_is_greyscale_only_when_channels_are_identical() -> None:
    geometry = FrameGeometry(0, 0, 4, 2, 4, 2, 150.2 / 72)
    grey = encode_frame_png(Image.new("RGB", (4, 2), (90, 90, 90)), geometry)
    colour = encode_frame_png(Image.new("RGB", (4, 2), (90, 91, 90)), geometry)
    assert grey.grayscale and Image.open(io.BytesIO(grey.png_bytes)).mode == "L"
    assert not colour.grayscale and Image.open(io.BytesIO(colour.png_bytes)).mode == "RGB"
    dpi = Image.open(io.BytesIO(grey.png_bytes)).info["dpi"]
    assert abs(dpi[0] - 150.2) < 0.1


# --------------------------------------------------------------------------- rendering


def _render_around(path, box, *, margin=10.0, scale=2.0):
    page_geometry = read_page_geometry(path, {1})[1]
    geometry = frame_geometry(
        (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin), crop=page_geometry.layout_cropbox, scale=scale
    )
    assert geometry is not None
    with open_pdf_for_rendering(path) as document:
        image = render_frame(document, page_number=1, page_geometry=page_geometry, geometry=geometry)
    encoded = encode_frame_png(image, geometry)
    return geometry, encoded, image.convert("L")


def _assert_square_in_centre(image) -> None:
    width, height = image.size
    pixels = list(image.tobytes())
    assert pixels[(height // 2) * width + width // 2] < 40
    for x, y in ((2, 2), (width - 3, 2), (2, height - 3), (width - 3, height - 3)):
        assert pixels[y * width + x] > 215


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
def test_render_frame_finds_the_square_pdfminer_measured_with_a_cropbox_and_rotation(tmp_path, rotate) -> None:
    # Mutation: dropping the CropBox from layout_cropbox (using the MediaBox) shifts the frame by
    # 20 x 30 pt and the centre pixel turns white.
    path = write_pdf(
        tmp_path / ("square_%d.pdf" % rotate),
        [SyntheticPage(cropbox=(20, 30, 380, 570), rotate=rotate, paths=["0 g 100 200 50 40 re f"])],
    )
    (box,) = _layout_rects(path)
    geometry, _encoded, image = _render_around(path, box)
    assert image.size == (geometry.width_px, geometry.height_px)
    _assert_square_in_centre(image)


def test_render_frame_finds_the_square_when_the_mediabox_is_inherited(tmp_path) -> None:
    """Acceptance review finding 2: pypdfium2's get_mediabox reads the page dictionary only; the boxes
    come from pdfminer, which resolves the page tree. Mutation: reading the boxes from pypdfium2 again
    shifts the frame off the square."""
    page = SyntheticPage(mediabox=(10, 20, 410, 620), cropbox=(30, 50, 390, 590), inherit_mediabox=True,
                         paths=["0 g 110 270 50 40 re f"])
    path = write_pdf(tmp_path / "inherited.pdf", [page])
    (box,) = _layout_rects(path)
    assert read_page_geometry(path, {1})[1].mediabox == (10.0, 20.0, 410.0, 620.0)
    _geometry, _encoded, image = _render_around(path, box)
    _assert_square_in_centre(image)


@pytest.mark.parametrize("rotate", [90, 180, 270])
def test_an_inherited_rotation_either_renders_the_square_or_is_refused(tmp_path, rotate) -> None:
    page = SyntheticPage(cropbox=(20, 30, 380, 570), rotate=rotate, inherit_rotate=True, paths=["0 g 100 200 50 40 re f"])
    path = write_pdf(tmp_path / ("inherited_rotate_%d.pdf" % rotate), [page])
    (box,) = _layout_rects(path)
    assert read_page_geometry(path, {1})[1].rotation == rotate
    try:
        _geometry, _encoded, image = _render_around(path, box)
    except PageGeometryMismatch:
        return
    _assert_square_in_centre(image)


def test_render_frame_refuses_a_page_the_two_engines_measure_differently(tmp_path) -> None:
    """The cross-check: a page geometry that is not PDFium's page (here: a wrong CropBox) is refused
    before anything is drawn. Mutation: dropping the size check renders the wrong area."""
    path = write_pdf(tmp_path / "check.pdf", [SyntheticPage(paths=["0 g 100 200 50 40 re f"])])
    real = read_page_geometry(path, {1})[1]
    wrong = type(real)(mediabox=real.mediabox, cropbox=(0.0, 0.0, 400.0, 500.0), rotation=0)
    geometry = frame_geometry((90.0, 350.0, 160.0, 410.0), crop=wrong.layout_cropbox, scale=2.0)
    assert geometry is not None
    with open_pdf_for_rendering(path) as document:
        with pytest.raises(PageGeometryMismatch):
            render_frame(document, page_number=1, page_geometry=wrong, geometry=geometry)


def test_render_frame_refuses_a_page_whose_rotation_the_engines_disagree_on(tmp_path) -> None:
    """A square page, so only the rotation can tell the two geometries apart. Mutation: dropping the
    rotation check renders the frame of the wrong orientation."""
    path = write_pdf(tmp_path / "square_page.pdf", [SyntheticPage(width=400, height=400, paths=["0 g 100 200 50 40 re f"])])
    real = read_page_geometry(path, {1})[1]
    rotated = type(real)(mediabox=real.mediabox, cropbox=real.cropbox, rotation=90)
    geometry = frame_geometry((90.0, 150.0, 160.0, 210.0), crop=rotated.layout_cropbox, scale=2.0)
    assert geometry is not None
    with open_pdf_for_rendering(path) as document:
        with pytest.raises(PageGeometryMismatch):
            render_frame(document, page_number=1, page_geometry=rotated, geometry=geometry)


def test_read_page_geometry_reports_the_user_unit(tmp_path) -> None:
    path = write_pdf(tmp_path / "unit.pdf", [SyntheticPage(user_unit=2.0), SyntheticPage()])
    geometry = read_page_geometry(path, {1, 2})
    assert (geometry[1].user_unit, geometry[2].user_unit) == (2.0, 1.0)


def test_render_frame_of_a_grey_page_is_a_greyscale_png_and_of_a_colour_page_rgb(tmp_path) -> None:
    grey_path = write_pdf(tmp_path / "grey.pdf", [SyntheticPage(paths=["0.3 g 100 200 50 40 re f"])])
    colour_path = write_pdf(tmp_path / "colour.pdf", [SyntheticPage(paths=["1 0 0 rg 100 200 50 40 re f"])])
    _g, grey, _ = _render_around(grey_path, _layout_rects(grey_path)[0])
    _g, colour, _ = _render_around(colour_path, _layout_rects(colour_path)[0])
    assert grey.grayscale
    assert not colour.grayscale


def test_two_threads_render_through_the_module_lock(tmp_path) -> None:
    path = write_pdf(tmp_path / "threads.pdf", [SyntheticPage(paths=["0 g 100 200 50 40 re f"])])
    box = _layout_rects(path)[0]
    results: list[bytes] = []
    errors: list[BaseException] = []

    def work() -> None:
        try:
            for _ in range(5):
                results.append(_render_around(path, box)[1].png_bytes)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(results) == 10 and len(set(results)) == 1
