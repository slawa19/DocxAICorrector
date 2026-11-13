"""Spec 082 slice B on synthetic PDFs: the graphics pass, the render of a region, its density, and containment.

The PDFs are written byte by byte (``tests/pdf_synthetic.py``); a Flate bitmap is an image the extractor does not
emit (the seed), a DCT JPEG is emitted. Texts are invented.
"""

from __future__ import annotations

import io
import logging

import pytest
from PIL import Image

from docxaicorrector.pdf_import import figure_regions as fr
from docxaicorrector.pdf_import import logical_import, page_render
from docxaicorrector.pdf_import.images import extract_pdf_images_and_inventory
from docxaicorrector.pdf_import.text_layer_quality import extract_pdf_text_spans_with_pdfminer
from pdf_synthetic import SyntheticImage, SyntheticPage, SyntheticText, write_pdf

SENTENCE = "An invented line of running text that goes on for a while."


def _body(top_y: float, count: int = 3) -> list[SyntheticText]:
    return [SyntheticText(40, top_y - 15 * i, 11, SENTENCE) for i in range(count)]


def _figure_page(member_pixels=(50, 50), member_box=(205, 250, 255, 300), extra_images=(), seed_box=(100, 250, 200, 350)):
    return SyntheticPage(
        images=[
            SyntheticImage("flate_gray", *seed_box, pixels=(40, 30), pattern="gradient"),
            SyntheticImage("jpeg_gray", *member_box, pixels=member_pixels, pattern="corner"),
            *extra_images,
        ],
        paths=["0 G 1 w 110 260 m 190 340 l S"],
        texts=[*_body(560), SyntheticText(110, 300, 8, "Label A"), *_body(150)],
    )


def _run(path, monkeypatch=None, events=None):
    spans = extract_pdf_text_spans_with_pdfminer(path)
    extraction = extract_pdf_images_and_inventory(path)
    if monkeypatch is not None and events is not None:
        monkeypatch.setattr(fr, "log_event", lambda level, event, message, **context: events.append((level, event, context)))
    outcome = fr.replace_composite_figures(path, extraction, list(extraction.images), spans)
    return extraction, outcome


def test_the_graphics_pass_reads_images_in_inventory_order_and_paths_by_all_their_operands(tmp_path) -> None:
    page = SyntheticPage(
        images=[
            SyntheticImage("flate_gray", 100, 250, 200, 350),
            SyntheticImage("jpeg_gray", 220, 250, 260, 290, form_bbox=(0, 0, 400, 600)),
        ],
        # a curve whose control point (y 500) lies far above both of its end points (y 100)
        paths=["0 G 1 w 50 100 m 60 500 90 500 100 100 c S"],
        texts=_body(560),
    )
    path = write_pdf(tmp_path / "pass.pdf", [page])
    graphics = fr.read_page_graphics(path, [1])[1].graphics
    inventory = extract_pdf_images_and_inventory(path).discovered
    images = [g for g in graphics if g.kind == "image"]
    assert [(g.discovery_index, g.box) for g in images] == [(d.discovery_index, d.frame_box) for d in inventory]
    assert images[0].source_px == (40, 30)
    (curve,) = [g for g in graphics if g.kind == "path"]
    assert curve.box[1] == pytest.approx(600 - 500)  # the control point's height, not the end points' (600 - 100)


def test_a_region_is_rendered_as_the_page_shows_it_and_replaces_its_emitted_picture(tmp_path, monkeypatch) -> None:
    path = write_pdf(tmp_path / "figure.pdf", [_figure_page()])
    events: list = []
    extraction, outcome = _run(path, monkeypatch, events)
    assert len(extraction.images) == 1 and outcome.rendered == 1 and outcome.images_absorbed == 1
    (picture,) = outcome.images
    assert picture.region_members == extraction.images
    assert picture.mime_type == "image/png" and picture.display_width_points and picture.display_height_points
    rendered = Image.open(io.BytesIO(picture.image_bytes)).convert("L")
    assert picture.display_width_points is not None
    scale = rendered.size[0] / picture.display_width_points
    # the emitted member (205..255 x, top 300..350) is a 'corner' picture: dark top-left quarter, light elsewhere
    def at(x_pt, top_pt) -> int:
        value = rendered.getpixel((int((x_pt - picture.x0) * scale), int((top_pt - picture.top) * scale)))
        assert isinstance(value, int)
        return value
    assert at(212, 307) < 100 and at(248, 343) > 150
    assert any(event == "pdf_figure_region_rendered" for _l, event, _c in events)


def test_a_correct_emitted_member_keeps_its_pixel_density(tmp_path, monkeypatch) -> None:
    # the member: 400 x 400 px on 40 x 40 pt (720 dpi); the seed: 40 x 30 px on 100 x 100 pt (29 dpi)
    path = write_pdf(tmp_path / "dense.pdf", [_figure_page(member_pixels=(400, 400), member_box=(205, 250, 245, 290))])
    events: list = []
    _extraction, outcome = _run(path, monkeypatch, events)
    (picture,) = outcome.images
    width_px, _height_px = Image.open(io.BytesIO(picture.image_bytes)).size
    assert picture.display_width_points is not None
    assert width_px >= round(picture.display_width_points * 10) - 1  # 10 px per point = 720 dpi
    rendered = next(context for _l, event, context in events if event == "pdf_figure_region_rendered")
    assert rendered["scale_dpi"] == pytest.approx(720.0, abs=0.5) and rendered["scale_source"] == "member"


def test_a_lone_seed_adds_a_picture_with_no_members(tmp_path) -> None:
    page = SyntheticPage(images=[SyntheticImage("flate_gray", 100, 250, 200, 350)], texts=[*_body(560), *_body(150)])
    path = write_pdf(tmp_path / "lone.pdf", [page])
    extraction, outcome = _run(path)
    assert extraction.images == () and len(outcome.images) == 1
    assert outcome.images[0].region_members == () and outcome.images[0].display_width_points


def test_the_step_never_grows_the_list_past_the_image_cap(tmp_path) -> None:
    page = SyntheticPage(images=[SyntheticImage("flate_gray", 100, 250, 200, 350)], texts=[*_body(560), *_body(150)])
    path = write_pdf(tmp_path / "cap.pdf", [page])
    spans = extract_pdf_text_spans_with_pdfminer(path)
    extraction = extract_pdf_images_and_inventory(path)
    outcome = fr.replace_composite_figures(path, extraction, [], spans, max_image_count=0)
    assert outcome.images == () and outcome.rendered == 0


def test_a_render_over_the_pixel_budget_is_declined(tmp_path, monkeypatch) -> None:
    import docxaicorrector.pdf_import.image_frames as image_frames

    monkeypatch.setattr(image_frames, "_within_pixel_budget", lambda geometry: False)
    path = write_pdf(tmp_path / "budget.pdf", [_figure_page()])
    events: list = []
    extraction, outcome = _run(path, monkeypatch, events)
    assert outcome.images == extraction.images and outcome.declined == 1
    assert [c["reason"] for _l, e, c in events if e == "pdf_figure_region_declined"] == [fr.DECLINE_EXCEEDS_PIXEL_BUDGET]


def test_a_page_with_a_user_unit_is_declined(tmp_path, monkeypatch) -> None:
    page = _figure_page()
    page.user_unit = 2.0
    path = write_pdf(tmp_path / "unit.pdf", [page])
    events: list = []
    extraction, outcome = _run(path, monkeypatch, events)
    assert outcome.images == extraction.images and outcome.declined == 1
    assert [c["reason"] for _l, e, c in events if e == "pdf_figure_region_declined"] == [fr.DECLINE_USER_UNIT]


def _two_regions_page():
    return SyntheticPage(
        images=[
            SyntheticImage("flate_gray", 60, 250, 140, 330),
            SyntheticImage("jpeg_gray", 60, 335, 140, 380, pixels=(50, 30), pattern="corner"),
            SyntheticImage("flate_gray", 250, 250, 330, 330),
            SyntheticImage("jpeg_gray", 250, 335, 330, 380, pixels=(50, 30), pattern="corner"),
        ],
        texts=[*_body(560), *_body(150)],
    )


def test_two_regions_of_a_page_are_built_together_or_not_at_all(tmp_path, monkeypatch) -> None:
    path = write_pdf(tmp_path / "two.pdf", [_two_regions_page()])
    extraction, outcome = _run(path)
    assert outcome.rendered == 2 and len(outcome.images) == 2
    real_render = page_render.render_frame
    calls = {"n": 0}

    def second_fails(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("invented failure of the second render")
        return real_render(*args, **kwargs)

    monkeypatch.setattr(page_render, "render_frame", second_fails)
    _extraction, outcome = _run(path)
    assert outcome.images == extraction.images and outcome.rendered == 0 and outcome.failed == 1


@pytest.mark.parametrize("stage", ["inventory", "typography", "page_geometry", "plan", "render", "encode"])
def test_a_failure_at_any_stage_keeps_the_pictures_slice_a_delivered(tmp_path, monkeypatch, stage) -> None:
    path = write_pdf(tmp_path / "stage.pdf", [_figure_page()])
    _extraction, working = _run(path)
    assert working.rendered == 1  # not vacuous

    def boom(*args, **kwargs):
        raise RuntimeError("invented failure at " + stage)

    targets = {
        "inventory": (fr, "read_page_graphics"),
        "typography": (logical_import, "pdf_body_typography"),
        "page_geometry": (page_render, "read_page_geometry"),
        "plan": (fr, "plan_figure_regions"),
        "render": (page_render, "render_frame"),
        "encode": (page_render, "encode_frame_png"),
    }
    module, name = targets[stage]
    monkeypatch.setattr(module, name, boom)
    events: list = []
    extraction, outcome = _run(path, monkeypatch, events)
    assert outcome.images == extraction.images and outcome.rendered == 0
    assert [(level, context["stage"]) for level, event, context in events if event == "pdf_figure_region_failed"] == [(logging.ERROR, stage)]


def test_a_renderer_that_cannot_open_the_document_keeps_the_pictures(tmp_path, monkeypatch) -> None:
    path = write_pdf(tmp_path / "open.pdf", [_figure_page()])

    def cannot_open(*args, **kwargs):
        raise RuntimeError("invented failure opening the document")

    monkeypatch.setattr(page_render, "open_pdf_for_rendering", cannot_open)
    events: list = []
    extraction, outcome = _run(path, monkeypatch, events)
    assert outcome.images == extraction.images and outcome.failed == 1
    assert [c["stage"] for _l, e, c in events if e == "pdf_figure_region_failed"] == ["render"]


def test_a_correct_member_keeps_its_fine_detail_in_the_region(tmp_path) -> None:
    """The member is a one-pixel checkerboard at 720 dpi beside a 29 dpi seed: the region must show the checkerboard,
    not a grey blur (acceptance review, finding 2: detail, not only the PNG size)."""

    member = SyntheticImage("jpeg_gray", 205, 250, 245, 290, pixels=(400, 400), pattern="checker")
    page = SyntheticPage(
        images=[SyntheticImage("flate_gray", 100, 250, 200, 350, pixels=(40, 30)), member],
        texts=[*_body(560), SyntheticText(110, 300, 8, "Label A"), *_body(150)],
    )
    path = write_pdf(tmp_path / "checker.pdf", [page])
    _extraction, outcome = _run(path)
    (picture,) = outcome.images
    rendered = Image.open(io.BytesIO(picture.image_bytes)).convert("L")
    assert picture.display_width_points is not None
    scale = rendered.size[0] / picture.display_width_points
    # the member's middle (x 210..240, top 315..345): neighbouring pixels alternate dark and light
    box = (int((210 - picture.x0) * scale), int((315 - picture.top) * scale), int((240 - picture.x0) * scale), int((345 - picture.top) * scale))
    crop = rendered.crop(box)
    width, height = crop.size
    pixels = [int(crop.getpixel((x, y)) or 0) for y in range(height) for x in range(width)]  # type: ignore[arg-type]
    jumps = [abs(int(pixels[y * width + x]) - int(pixels[y * width + x + 1])) for y in range(height) for x in range(width - 1)]
    assert sum(jumps) / len(jumps) > 100  # a render at the seed's density would be a grey blur near 0


def test_a_member_placed_with_a_rotation_declines_the_page(tmp_path, monkeypatch) -> None:
    import math

    angle = math.radians(45)
    side = 40.0
    rotated = SyntheticImage(
        "jpeg_gray", 205, 250, 262, 307, pixels=(400, 400), pattern="checker",
        matrix=(side * math.cos(angle), side * math.sin(angle), -side * math.sin(angle), side * math.cos(angle), 233.3, 250.0),
    )
    page = SyntheticPage(
        images=[SyntheticImage("flate_gray", 100, 250, 200, 350, pixels=(40, 30)), rotated],
        texts=[*_body(560), SyntheticText(110, 300, 8, "Label A"), *_body(150)],
    )
    path = write_pdf(tmp_path / "rotated.pdf", [page])
    events: list = []
    extraction, outcome = _run(path, monkeypatch, events)
    assert len(extraction.images) == 1 and outcome.images == extraction.images  # the member is delivered as today
    assert [c["reason"] for _l, e, c in events if e == "pdf_figure_region_declined"] == [fr.DECLINE_MEMBER_PLACEMENT]
