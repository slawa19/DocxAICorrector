"""Spec 082 slice A, Codex acceptance review round 2: reproductions of the findings, kept as regression tests.

Finding 1: a negative correlation proves nothing when something on the page changes how the image looks
besides the image itself. The "correct" picture here is a DeviceGray JPEG stored exactly as it should look
(left half 64, right half 192). Something on the page hides or darkens one half -- a vector fill over it, a
clip, a soft mask, a colour-key mask, an ExtGState soft mask, a shading, a form's BBox -- and the render
becomes ANTI-correlated with the correct stored picture (premise asserted in every test). Delivering the
render would lose half the picture; the image must keep its bytes.

Finding 2: an image that reaches past the TOP of the page was seen as entirely inside it (its top had been
clamped to zero before the admission check); the four sides are tested.

Finding 3: an exception while encoding the render escaped the per-image handling.
"""

from __future__ import annotations

import io
import logging

import pytest
from PIL import Image

from docxaicorrector.pdf_import import image_frames
from docxaicorrector.pdf_import.image_frames import apply_frame_replacements, plan_frame_replacements
from docxaicorrector.pdf_import.images import extract_pdf_images_and_inventory
from pdf_synthetic import SyntheticImage, SyntheticPage, write_pdf

pytestmark = pytest.mark.unit_contract


def _grey(data: bytes, size=(48, 24)) -> list[int]:
    return list(Image.open(io.BytesIO(data)).convert("L").resize(size, Image.Resampling.BILINEAR).tobytes())


def _correlation(a: list[int], b: list[int]) -> float:
    n = len(a)
    mean_a, mean_b = sum(a) / n, sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    return cov / (var_a * var_b) ** 0.5


def _page_view(path, box) -> bytes:
    import pypdfium2

    document = pypdfium2.PdfDocument(str(path))
    try:
        whole = document[0].render(scale=3).to_pil().convert("L")
    finally:
        document.close()
    buffer = io.BytesIO()
    whole.crop(tuple(int(round(v * 3.0)) for v in box)).save(buffer, format="PNG")
    return buffer.getvalue()


def _run(path, monkeypatch=None):
    from docxaicorrector.pdf_import.text_layer_quality import extract_pdf_text_spans_with_pdfminer

    events: list[tuple[int, str, dict]] = []
    if monkeypatch is not None:
        monkeypatch.setattr(image_frames, "log_event", lambda level, event, message, **context: events.append((level, event, context)))
    extraction = extract_pdf_images_and_inventory(path)
    plan = plan_frame_replacements(extraction, extract_pdf_text_spans_with_pdfminer(path))
    return extraction, plan, apply_frame_replacements(path, extraction, plan), events


def _correct_photo(**kwargs) -> SyntheticImage:
    # 200 x 100 pt at (60, 300); left half 64, right half (x 160..260) a ramp 160..224.
    return SyntheticImage("jpeg_gray", 60, 300, 260, 400, pixels=(300, 150), pattern="halves_ramp", **kwargs)


def _negative_photo(**kwargs) -> SyntheticImage:
    return SyntheticImage("jpeg_separation", 60, 300, 260, 400, pixels=(300, 150), pattern="corner", **kwargs)


_RIGHT_HALF = "160 300 100 100 re"
_LEFT_HALF = "60 300 100 100 re"

_HIDING_CASES = {
    # a black fill over the right half: the page shows [64, 0]
    "vector_fill_over": (dict(), dict(overlays=["0 g " + _RIGHT_HALF + " f"]), "paint_over_frame"),
    # a dark shading painted over the right half
    "shading_over": (dict(), dict(overlays=["q " + _RIGHT_HALF + " W n /Sh0 sh Q"]), "paint_over_frame"),
    # a soft mask that makes the left half transparent: the page shows [white, ramp]
    "image_smask": (dict(smask="left_clear"), dict(), "masked_image"),
    # a colour key that makes the 64 samples transparent
    "colour_key_mask": (dict(colour_key="[40 90]"), dict(), "masked_image"),
    # an ExtGState soft mask whose luminosity is black over the left half
    "extgstate_smask": (dict(gs_smask=True), dict(), "masked_image"),
    # a clip that shows only the right half: the page shows [white, ramp]. The comparison is made on the
    # part the clip shows -- ramp against ramp, positive -- so the image is kept, not declined.
    "clip_shows_a_part": (dict(clip=_RIGHT_HALF + " W n"), dict(), None),
    # the same through a form whose BBox is the right half
    "form_bbox_clip": (dict(form_bbox=(160, 300, 260, 400)), dict(), None),
    # a clip of five corners (the right half with an extra vertex on its left edge): only an axis-aligned
    # rectangle of four corners is followed, anything else is declined
    "five_corner_clip": (dict(clip="160 300 m 260 300 l 260 400 l 160 400 l 160 350 l h W n"), dict(), "clipped_frame"),
}


@pytest.mark.parametrize("case", sorted(_HIDING_CASES))
def test_a_correct_image_the_page_partly_hides_keeps_its_bytes(tmp_path, monkeypatch, case) -> None:
    image_kwargs, page_kwargs, reason = _HIDING_CASES[case]
    path = write_pdf(tmp_path / (case + ".pdf"), [SyntheticPage(images=[_correct_photo(**image_kwargs)], **page_kwargs)])
    extraction, _plan, outcome, events = _run(path, monkeypatch)
    (stored,) = extraction.images
    # Premise: the page view is anti-correlated with the CORRECT stored picture, so the sign read over the
    # whole frame would replace it with a render that has lost half of it.
    assert _correlation(_grey(stored.image_bytes), _grey(_page_view(path, (60, 200, 260, 300)))) < -0.5
    assert outcome.replaced == 0
    assert outcome.images == extraction.images
    reasons = [context["reason"] for _level, event, context in events if event == "pdf_image_frame_render_declined"]
    assert reasons == ([reason] if reason else []), events
    if reason is None:
        assert outcome.checked == 1  # compared on the visible part, and found to be the page's own picture


@pytest.mark.parametrize(
    ("case", "image_kwargs", "page_kwargs"),
    [
        ("path_beside_the_frame", dict(), dict(overlays=["0 g 270 300 50 100 re f"])),
        ("path_under_text_elsewhere", dict(), dict(overlays=["0 g 60 100 200 20 re f"])),
        ("clip_containing_the_frame", dict(clip="40 280 240 140 re W n"), dict()),
        ("form_bbox_containing_the_frame", dict(form_bbox=(0, 0, 400, 600)), dict()),
        # a picture frame cropping its photograph by a point on every side, as layout programs do
        ("clip_cropping_a_point", dict(clip="61 301 198 98 re W n"), dict()),
        # the same rectangle followed by a lone moveto, as InDesign writes it
        ("clip_with_a_lone_moveto", dict(clip="61 301 198 98 re 61 399 m W n"), dict()),
        # the same rectangle as four lines without closepath (a clip is implicitly closed)
        ("clip_as_four_lines", dict(clip="61 301 m 259 301 l 259 399 l 61 399 l W n"), dict()),
        # a clip set and restored (q ... Q) before the image is drawn is not in force at the image
        ("clip_restored_by_Q", dict(), dict(paths=["q 0 0 10 10 re W n Q"])),
    ],
)
def test_page_content_that_cannot_reach_the_frame_does_not_decline_a_negative(tmp_path, case, image_kwargs, page_kwargs) -> None:
    """The declines are evidence-bound, not blanket: a negative with a path beside it, or a clip / form BBox
    containing its whole frame, is still replaced by its render."""
    path = write_pdf(tmp_path / (case + ".pdf"), [SyntheticPage(images=[_negative_photo(**image_kwargs)], **page_kwargs)])
    _extraction, _plan, outcome, _events = _run(path)
    (image,) = outcome.images
    assert outcome.replaced == 1
    assert image.original_image_bytes is not None
    assert _correlation(_grey(image.image_bytes), _grey(image.original_image_bytes)) < -0.9


@pytest.mark.parametrize(
    ("case", "overlay"),
    [
        # a vertical stroke 3 pt right of the frame, 8 pt wide: its paint reaches 1 pt into the frame
        ("stroke_spilling_in", "8 w 0 G 263 300 m 263 400 l S"),
        # a filled curve whose end points lie right of the frame and whose bulge reaches into it
        ("curve_bulging_in", "0 g 270 300 m 150 330 150 370 270 400 c h f"),
        # a hairline across the frame
        ("hairline_across", "0 w 0 G 40 350 m 280 350 l S"),
        # a hairline 0.1 pt inside the right edge: one device pixel wide, it covers the last pixel column
        # (half a render pixel is 1/3 pt here); as a zero-width line it would not reach a pixel centre
        ("hairline_along_the_edge", "0 w 0 G 259.9 290 m 259.9 410 l S"),
    ],
)
def test_paint_that_reaches_into_the_frame_declines_even_a_negative(tmp_path, monkeypatch, case, overlay) -> None:
    """Where paint may reach is bounded conservatively: a stroke's width (with its joins and caps), a curve's
    control points, a zero-width line's device pixel."""
    path = write_pdf(tmp_path / (case + ".pdf"), [SyntheticPage(images=[_negative_photo()], overlays=[overlay])])
    extraction, _plan, outcome, events = _run(path, monkeypatch)
    assert outcome.replaced == 0 and outcome.images == extraction.images
    reasons = [context["reason"] for _level, event, context in events if event == "pdf_image_frame_render_declined"]
    assert reasons == ["paint_over_frame"]


@pytest.mark.parametrize(
    ("side", "box"),
    [
        ("top", (60, 550, 260, 650)),
        ("bottom", (60, -50, 260, 50)),
        ("left", (-50, 300, 150, 400)),
        ("right", (300, 300, 500, 400)),
    ],
)
def test_an_image_reaching_past_any_page_edge_is_declined(tmp_path, monkeypatch, side, box) -> None:
    """Finding 2: page 400 x 600; the image reaches 50 pt past one edge. The admission check must see the
    image's true frame, not one clamped to the page."""
    photo = SyntheticImage("jpeg_separation", *box, pixels=(300, 150), pattern="corner")
    path = write_pdf(tmp_path / (side + ".pdf"), [SyntheticPage(images=[photo])])
    extraction, _plan, outcome, events = _run(path, monkeypatch)
    assert outcome.replaced == 0
    assert outcome.images == extraction.images
    reasons = [context["reason"] for _level, event, context in events if event == "pdf_image_frame_render_declined"]
    assert reasons == ["outside_crop_box"]


def test_the_ordering_key_of_an_image_reaching_past_the_top_is_unchanged(tmp_path) -> None:
    """Finding 2 must not move the image in the document: its top-origin ``top`` (the ordering key) stays
    clamped to the page as before; only the admission check sees the true frame."""
    photo = SyntheticImage("jpeg_separation", 60, 550, 260, 650, pixels=(300, 150), pattern="corner")
    path = write_pdf(tmp_path / "top.pdf", [SyntheticPage(images=[photo])])
    (image,) = extract_pdf_images_and_inventory(path).images
    assert (image.top, image.bottom, image.source_index) == (0.0, 50.0, 0)


def test_the_observed_walk_yields_the_layout_pdfminer_yields(tmp_path) -> None:
    """The evidence walk only observes: every layout object pdfminer's own ``extract_pages`` yields, in the
    same order with the same box, on a page with text, paths, a shading, a clip, a mask and a form."""
    from pdfminer.high_level import extract_pages

    from docxaicorrector.pdf_import.paint_evidence import iter_pages_with_evidence
    from pdf_synthetic import SyntheticText

    page = SyntheticPage(
        images=[_correct_photo(clip=_RIGHT_HALF + " W n"), SyntheticImage("jpeg_gray", 60, 100, 160, 150, smask="left_clear"),
                SyntheticImage("jpeg_rgb", 200, 100, 300, 150, form_bbox=(150, 80, 350, 170), gs_smask=True)],
        texts=[SyntheticText(40, 520, 11, "An invented line of text."), SyntheticText(40, 500, 11, "Another invented line.")],
        paths=["0.5 g 20 20 50 50 re f", "1 w 0 G 10 580 m 390 580 l S"],
        overlays=["q 300 400 80 80 re W n /Sh0 sh Q", "0 g 330 300 m 360 330 340 360 310 340 c f"],
    )
    path = write_pdf(tmp_path / "walk.pdf", [page, SyntheticPage(texts=[SyntheticText(40, 300, 12, "A second page.")])])

    def flatten(element):
        items = []
        for child in element:
            bbox = tuple(round(v, 6) for v in getattr(child, "bbox", ()))
            items.append((type(child).__name__, bbox, getattr(child, "get_text", lambda: "")()))
            if hasattr(child, "__iter__") and type(child).__name__ in {"LTFigure", "LTTextBoxHorizontal", "LTTextLineHorizontal"}:
                items.extend(flatten(child))
        return items

    expected = [flatten(layout) for layout in extract_pages(str(path))]
    observed = [flatten(layout) for layout, _evidence in iter_pages_with_evidence(path)]
    assert observed == expected
    assert sum(len(items) for items in expected) > 10


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ([("m", 0, 0), ("l", 10, 0), ("l", 10, 5), ("l", 0, 5), ("h",)], "rectangle"),
        ([("m", 0, 0), ("l", 10, 0), ("l", 10, 5), ("l", 0, 5)], "rectangle"),
        ([("m", 0, 0), ("l", 10, 0), ("l", 10, 5), ("l", 0, 5), ("l", 0, 0)], "rectangle"),
        ([("m", 0, 0), ("l", 10, 0), ("l", 10, 5), ("l", 0, 5), ("h",), ("m", 0, 5)], "rectangle"),
        ([("m", 0, 0), ("l", 10, 0), ("l", 10, 5), ("l", 0, 5), ("h",), ("m", 20, 20), ("l", 30, 20), ("l", 30, 30), ("h",)], "other"),
        ([("m", 0, 0), ("l", 10, 0), ("c", 12, 2, 12, 3, 10, 5), ("l", 0, 5), ("h",)], "other"),
        ([("m", 0, 0), ("l", 10, 1), ("l", 10, 5), ("l", 0, 5), ("h",)], "other"),
        ([("m", 0, 0), ("l", 10, 0), ("l", 10, 5), ("l", 10, 0), ("h",)], "other"),
        ([("m", 0, 0), ("l", 10, 0), ("l", 10, 5), ("l", 5, 5), ("l", 0, 5), ("h",)], "other"),
        ([], "other"),
    ],
)
def test_only_one_axis_aligned_four_corner_subpath_is_a_rectangle_clip(path, kind) -> None:
    from docxaicorrector.pdf_import.paint_evidence import clip_entry

    assert clip_entry(path, (1, 0, 0, 1, 0, 0)).kind == kind


def test_paint_reaching_into_a_frame_is_told_from_paint_that_only_borders_it() -> None:
    from docxaicorrector.pdf_import.images import PdfPaintedRegion

    frame = (100.0, 100.0, 200.0, 150.0)
    half = 0.25

    def region(box, reach=0.0, hairline=False):
        return PdfPaintedRegion(1, *box, reach=reach, hairline=hairline, kind="path")

    reaches = image_frames._reaches_into
    assert reaches(region((150, 120, 150, 120)), frame, half)  # a zero-size path inside
    assert reaches(region((90, 125, 210, 125), hairline=True), frame, half)  # a hairline across
    assert reaches(region((200.0, 100, 210, 150), reach=0.5), frame, half)  # a stroke spilling in
    assert not reaches(region((200.0, 100, 210, 150)), frame, half)  # a fill that borders the frame
    assert not reaches(region((199.8, 100, 210, 150)), frame, half)  # ... or reaches less than half a pixel in
    assert not reaches(region((100, 10, 200, 90), reach=5.0), frame, half)  # a stroke that stops short


def test_the_compare_command_reports_size_only_changes_and_added_or_removed_tails(tmp_path) -> None:
    """Round 2 finding 4: pictures compared on sha1 only, and a longer run's tail hidden by ``zip``."""
    import importlib.util
    import json
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "measure-pdf-image-frames.py"
    spec = importlib.util.spec_from_file_location("measure_pdf_image_frames", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    picture = {"sha1": "a", "bytes": 10, "emu": [1, 2]}
    before: dict[str, object] = {"books": {"book.pdf": {"paragraphs": [["p", "Normal"]], "pictures": [picture], "replaced_pages": [], "seconds": 1}}}
    after: dict[str, object] = {
        "books": {
            "book.pdf": {
                "paragraphs": [["p", "Normal"], ["q", "Normal"]],
                "pictures": [dict(picture, emu=[3, 4]), picture],
                "replaced_pages": [],
                "seconds": 1,
            }
        }
    }
    for run, label in ((before, "before"), (after, "after")):
        run["provenance"] = {"label": label}
        (tmp_path / (label + ".json")).write_text(json.dumps(run), encoding="utf-8")
    module.main(["compare", str(tmp_path / "before.json"), str(tmp_path / "after.json"), "--out", str(tmp_path / "c.json")])
    entry = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))["books"]["book.pdf"]
    assert [(d["index"], d["fields"]) for d in entry["picture_differences"]] == [(0, ["emu"]), (1, ["added"])]
    assert entry["pictures_added"] == [1] and entry["pictures_removed"] == []
    assert [(d["index"], d["before"], d["after"]) for d in entry["paragraph_differences"]] == [(1, None, ["q", "Normal"])]


@pytest.mark.parametrize("failing_call", ["first", "last"])
def test_an_encoding_failure_is_one_failed_image_and_the_rest_are_still_replaced(tmp_path, monkeypatch, failing_call) -> None:
    """Finding 3: the encoder raising for one image keeps that image's bytes, counts it as failed, logs an
    ERROR -- and every other candidate is still processed."""
    photos = [
        SyntheticImage("jpeg_separation", 60, y, 260, y + 100, pixels=(300, 150), pattern="corner")
        for y in (450, 300, 150)
    ]
    path = write_pdf(tmp_path / "three.pdf", [SyntheticPage(images=photos)])
    real_encode = image_frames.encode_frame_png
    calls: list[int] = []

    def flaky(image, geometry):
        calls.append(1)
        if (failing_call == "first" and len(calls) == 1) or (failing_call == "last" and len(calls) == 3):
            raise MemoryError("invented encoder failure")
        return real_encode(image, geometry)

    monkeypatch.setattr(image_frames, "encode_frame_png", flaky)
    extraction, plan, outcome, events = _run(path, monkeypatch)
    assert len(plan.candidates) == 3 and len(calls) == 3
    assert (outcome.checked, outcome.replaced, outcome.failed) == (3, 2, 1)
    failed_index = 0 if failing_call == "first" else 2
    failed_key = (plan.candidates[failed_index].image.page_number, plan.candidates[failed_index].image.discovery_index)
    errors = [(level, context) for level, event, context in events if event == "pdf_image_frame_render_failed"]
    assert [(level, (context["page_number"], context["discovery_index"]), context["error_type"]) for level, context in errors] == [
        (logging.ERROR, failed_key, "MemoryError")
    ]
    kept = [image for image in outcome.images if image.original_image_bytes is None]
    assert [(image.page_number, image.discovery_index) for image in kept] == [failed_key]
    assert {image.image_bytes for image in kept} <= {image.image_bytes for image in extraction.images}
