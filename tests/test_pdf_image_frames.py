"""Spec 082 slice A: an emitted PDF image whose bytes are ink tints is replaced by a render of its frame.

Pure decisions are tested on hand-made records; the replacement on tiny PDFs from ``tests/pdf_synthetic.py``.
All text is invented. Each trigger condition and each decline has a test that fails when the condition is
removed (mutation notes in the docstrings; spec 082 SC-A4).
"""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageStat

import docxaicorrector.pdf_import.image_frames as image_frames
from docxaicorrector.pdf_import.image_frames import (
    DECLINE_EXCEEDS_PIXEL_BUDGET,
    DECLINE_IMAGE_OVER_FRAME,
    DECLINE_OUTSIDE_CROP_BOX,
    DECLINE_TEXT_OVER_FRAME,
    apply_frame_replacements,
    colour_space_is_ink,
    plan_frame_replacements,
)
from docxaicorrector.pdf_import.images import (
    PdfDiscoveredImage,
    PdfImageExtraction,
    PdfImageObject,
    extract_pdf_images_and_inventory,
)
from docxaicorrector.pdf_import.text_layer_quality import PdfTextSpan
from pdf_synthetic import SyntheticImage, SyntheticPage, SyntheticText, write_pdf

pytestmark = pytest.mark.unit_contract


def _jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (width, height), 60).save(buffer, format="JPEG")
    return buffer.getvalue()


def _image(index: int, box, family: str | None, *, page: int = 1, pixels=(300, 150)) -> PdfImageObject:
    return PdfImageObject(
        page_number=page,
        x0=box[0],
        top=box[1],
        x1=box[2],
        bottom=box[3],
        page_height=600.0,
        image_bytes=_jpeg(*pixels),
        mime_type="image/jpeg",
        source_index=(page - 1) * 10000 + int(round(box[1])),
        discovery_index=index,
        colour_space_family=family,
    )


def _extraction(*images: PdfImageObject, extra=()) -> PdfImageExtraction:
    discovered = tuple(
        PdfDiscoveredImage(i.page_number, i.discovery_index or 0, i.x0, i.top, i.x1, i.bottom, i.colour_space_family, None)
        for i in images
    ) + tuple(extra)
    return PdfImageExtraction(images=tuple(images), discovered=discovered)


def _span(text: str, box, page: int = 1) -> PdfTextSpan:
    return PdfTextSpan(page_number=page, text=text, x0=box[0], top=box[1], x1=box[2], bottom=box[3], page_height=600.0, font_size=9.0)


BOX = (50.0, 100.0, 200.0, 175.0)


# --------------------------------------------------------------------------- trigger


@pytest.mark.parametrize("family", ["Separation", "DeviceN"])
def test_an_ink_space_image_is_a_candidate(family) -> None:
    """Mutation: dropping the colour-space test (every image a candidate) fails the next test instead;
    narrowing INK_COLOUR_SPACE_FAMILIES to one name fails this one for the other."""
    plan = plan_frame_replacements(_extraction(_image(0, BOX, family)), [])
    assert [c.image.discovery_index for c in plan.candidates] == [0]
    assert colour_space_is_ink(family)


@pytest.mark.parametrize("family", ["DeviceGray", "DeviceRGB", "DeviceCMYK", "ICCBased", "Indexed", "Lab", None])
def test_an_image_in_a_light_space_is_never_touched(family) -> None:
    """Mutation: replacing the colour-space test by ``True`` makes every one of these a candidate."""
    plan = plan_frame_replacements(_extraction(_image(0, BOX, family)), [_span("Far away line.", (50, 400, 300, 410))])
    assert plan.candidates == () and plan.declines == ()


def test_the_render_scale_is_the_source_pixel_density() -> None:
    plan = plan_frame_replacements(_extraction(_image(0, BOX, "Separation", pixels=(300, 160))), [])
    (candidate,) = plan.candidates
    # 300 px over 150 pt wide, 160 px over 75 pt high: the denser axis decides.
    assert candidate.scale == pytest.approx(160 / 75)
    assert (candidate.source_width_px, candidate.source_height_px) == (300, 160)


# --------------------------------------------------------------------------- declines


def test_text_over_the_frame_declines_the_replacement() -> None:
    """Mutation: removing the text-overlap check makes the image a candidate."""
    plan = plan_frame_replacements(
        _extraction(_image(0, BOX, "Separation")), [_span("Label alpha", (60, 110, 120, 120))]
    )
    assert plan.candidates == ()
    assert [(d.reason, d.detail) for d in plan.declines] == [(DECLINE_TEXT_OVER_FRAME, "Label alpha")]


def test_text_that_only_touches_the_frame_edge_or_sits_on_another_page_does_not_decline() -> None:
    """Mutation: counting a zero-area touch as overlap declines this image."""
    spans = [
        _span("A caption under the picture.", (50, 175, 200, 185)),  # shares the bottom edge
        _span("Text on another page.", (60, 110, 120, 120), page=2),
        _span("   ", (60, 110, 120, 120)),  # whitespace is not text
    ]
    plan = plan_frame_replacements(_extraction(_image(0, BOX, "Separation")), spans)
    assert len(plan.candidates) == 1 and plan.declines == ()


def test_another_image_over_the_frame_declines_the_replacement_even_if_it_was_not_emitted() -> None:
    """Mutation: removing the image-overlap check makes the image a candidate."""
    hidden = PdfDiscoveredImage(1, 7, 150.0, 150.0, 250.0, 250.0, "DeviceGray", "unknown_mime")
    plan = plan_frame_replacements(_extraction(_image(0, BOX, "Separation"), extra=(hidden,)), [])
    assert plan.candidates == ()
    assert [(d.reason, d.detail) for d in plan.declines] == [(DECLINE_IMAGE_OVER_FRAME, "page 1 image 7")]


def test_the_same_discovery_index_on_another_page_is_another_image() -> None:
    elsewhere = PdfDiscoveredImage(2, 0, 50.0, 100.0, 200.0, 175.0, "DeviceGray", None)
    plan = plan_frame_replacements(_extraction(_image(0, BOX, "Separation"), extra=(elsewhere,)), [])
    assert len(plan.candidates) == 1


# --------------------------------------------------------------------------- replacement on a real PDF


def _page_with(kind: str, *, texts=(), extra_images=(), cropbox=None) -> SyntheticPage:
    return SyntheticPage(
        cropbox=cropbox,
        images=[SyntheticImage(kind, 60, 300, 260, 400, pixels=(300, 150))] + list(extra_images),
        texts=[SyntheticText(40, 520, 11, "An invented sentence above the picture.")] + list(texts),
    )


def _spans(path):
    from docxaicorrector.pdf_import.text_layer_quality import extract_pdf_text_spans_with_pdfminer

    return extract_pdf_text_spans_with_pdfminer(path)


def _page_render_mean(path, image: PdfImageObject) -> float:
    from docxaicorrector.pdf_import.page_render import frame_geometry, open_pdf_for_rendering, render_frame

    with open_pdf_for_rendering(path) as document:
        rendered = render_frame(
            document, page_number=1, geometry_for_crop=lambda crop: frame_geometry((image.x0, image.top, image.x1, image.bottom), crop=crop, scale=1.5)
        )
    assert rendered is not None
    return ImageStat.Stat(Image.open(io.BytesIO(rendered.png_bytes)).convert("L")).mean[0]


@pytest.mark.parametrize("kind", ["jpeg_separation", "jpeg_devicen"])
def test_an_ink_space_jpeg_is_replaced_by_a_render_that_looks_like_the_page(tmp_path, kind) -> None:
    path = write_pdf(tmp_path / (kind + ".pdf"), [_page_with(kind)])
    extraction = extract_pdf_images_and_inventory(path)
    (emitted,) = extraction.images
    outcome = apply_frame_replacements(path, extraction, plan_frame_replacements(extraction, _spans(path)))
    (replaced,) = outcome.images
    assert (outcome.replaced, outcome.declined, outcome.failed) == (1, 0, 0)
    assert replaced.mime_type == "image/png" and replaced.original_image_bytes == emitted.image_bytes
    assert (replaced.source_index, replaced.discovery_index, replaced.x0, replaced.top) == (
        emitted.source_index, emitted.discovery_index, emitted.x0, emitted.top)
    rendered = Image.open(io.BytesIO(replaced.image_bytes))
    stored = Image.open(io.BytesIO(emitted.image_bytes))
    # Never fewer pixels than the source (FR-A5).
    assert rendered.size[0] >= stored.size[0] and rendered.size[1] >= stored.size[1]
    assert replaced.display_width_points == pytest.approx(rendered.size[0] * 200 / stored.size[0], rel=0.02)
    # The stored file is a negative of the page; the replacement is the page.
    page_mean = _page_render_mean(path, emitted)
    stored_mean = ImageStat.Stat(stored.convert("L")).mean[0]
    rendered_mean = ImageStat.Stat(rendered.convert("L")).mean[0]
    assert abs(rendered_mean - page_mean) < 3
    assert abs(stored_mean - (255 - page_mean)) < 6


def test_a_device_gray_jpeg_keeps_its_bytes(tmp_path) -> None:
    path = write_pdf(tmp_path / "gray.pdf", [_page_with("jpeg_gray")])
    extraction = extract_pdf_images_and_inventory(path)
    outcome = apply_frame_replacements(path, extraction, plan_frame_replacements(extraction, _spans(path)))
    assert outcome.images == extraction.images
    assert (outcome.replaced, outcome.declined, outcome.failed) == (0, 0, 0)


def test_a_label_over_the_picture_keeps_the_negative_and_logs_the_decline(tmp_path, monkeypatch) -> None:
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(image_frames, "log_event", lambda level, event, message, **context: events.append((event, context)))
    path = write_pdf(tmp_path / "label.pdf", [_page_with("jpeg_separation", texts=[SyntheticText(100, 350, 8, "Label alpha")])])
    extraction = extract_pdf_images_and_inventory(path)
    outcome = apply_frame_replacements(path, extraction, plan_frame_replacements(extraction, _spans(path)))
    assert outcome.images == extraction.images
    assert [(e, c["reason"]) for e, c in events] == [("pdf_image_frame_render_declined", DECLINE_TEXT_OVER_FRAME)]


def test_a_frame_outside_the_cropbox_is_declined(tmp_path) -> None:
    """Mutation: dropping the CropBox clip in frame_geometry renders an empty-looking frame instead."""
    path = write_pdf(tmp_path / "outside.pdf", [_page_with("jpeg_separation", cropbox=(0, 0, 400, 250))])
    extraction = extract_pdf_images_and_inventory(path)
    outcome = apply_frame_replacements(path, extraction, plan_frame_replacements(extraction, _spans(path)))
    assert outcome.images == extraction.images and outcome.declined == 1


def test_a_render_over_the_pixel_budget_is_declined_rather_than_shrunk(tmp_path, monkeypatch) -> None:
    """Mutation: removing the budget check delivers a render larger than the pipeline admits."""
    import docxaicorrector.image.analysis as analysis

    monkeypatch.setattr(analysis, "MAX_IMAGE_DIMENSION_PX", 200)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(image_frames, "log_event", lambda level, event, message, **context: events.append((event, context)))
    path = write_pdf(tmp_path / "budget.pdf", [_page_with("jpeg_separation")])
    extraction = extract_pdf_images_and_inventory(path)
    outcome = apply_frame_replacements(path, extraction, plan_frame_replacements(extraction, _spans(path)))
    assert outcome.images == extraction.images
    assert [c["reason"] for e, c in events if e == "pdf_image_frame_render_declined"] == [DECLINE_EXCEEDS_PIXEL_BUDGET]


def test_a_render_that_raises_keeps_the_emitted_bytes_and_logs_an_error(tmp_path, monkeypatch) -> None:
    events: list[tuple[int, str, dict]] = []
    monkeypatch.setattr(image_frames, "log_event", lambda level, event, message, **context: events.append((level, event, context)))

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic render failure")

    monkeypatch.setattr(image_frames, "render_frame", boom)
    path = write_pdf(tmp_path / "boom.pdf", [_page_with("jpeg_separation")])
    extraction = extract_pdf_images_and_inventory(path)
    outcome = apply_frame_replacements(path, extraction, plan_frame_replacements(extraction, _spans(path)))
    assert outcome.images == extraction.images and outcome.failed == 1
    assert [(level, event) for level, event, _ in events] == [(40, "pdf_image_frame_render_failed")]


def test_no_candidate_means_the_pdf_is_never_opened_for_rendering(tmp_path, monkeypatch) -> None:
    opened: list[object] = []
    monkeypatch.setattr(image_frames, "open_pdf_for_rendering", lambda path: opened.append(path))
    path = write_pdf(tmp_path / "none.pdf", [_page_with("jpeg_gray")])
    extraction = extract_pdf_images_and_inventory(path)
    apply_frame_replacements(path, extraction, plan_frame_replacements(extraction, _spans(path)))
    assert opened == []


def test_the_inventory_names_every_image_with_its_skip_reason_and_colour_space(tmp_path) -> None:
    path = write_pdf(
        tmp_path / "inventory.pdf",
        [
            SyntheticPage(images=[SyntheticImage("jpeg_separation", 60, 300, 260, 400), SyntheticImage("flate_gray", 300, 300, 380, 380)]),
            SyntheticPage(images=[SyntheticImage("jpeg_rgb", 60, 300, 260, 400)]),
        ],
    )
    extraction = extract_pdf_images_and_inventory(path)
    assert [(d.page_number, d.discovery_index, d.colour_space_family, d.skip_reason) for d in extraction.discovered] == [
        (1, 0, "Separation", None),
        (1, 1, "DeviceGray", "unknown_mime"),
        (2, 0, "DeviceRGB", None),
    ]
    assert [(i.page_number, i.discovery_index, i.colour_space_family) for i in extraction.images] == [
        (1, 0, "Separation"),
        (2, 0, "DeviceRGB"),
    ]
    assert DECLINE_OUTSIDE_CROP_BOX  # the constant is part of the event contract
