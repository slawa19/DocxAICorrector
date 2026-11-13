"""Spec 082 slice A, Codex acceptance reviews round 2 and 3: reproductions of the findings, kept as tests.

Round 2, finding 1: a negative correlation proves nothing when something on the page changes how the image
looks besides the image itself. The "correct" picture here is stored exactly as it should look (left half
64, right half a ramp 160..224). Something on the page hides or darkens one half -- a vector fill, a
shading, a clip, a soft mask, a colour-key mask, an ExtGState soft mask, a form's BBox -- and the render
becomes ANTI-correlated with the correct stored picture (premise asserted in every test). Round 3 answers
with the CAUSE half of the trigger, not by observing the paint: an image outside an ink space is never
replaced; an image whose dictionary names an /SMask or /Mask is declined. The residual -- an ink-space image
already right as stored AND anti-correlated by something unobserved -- is pinned as such.

Round 2, finding 2: an image that reaches past the TOP of the page was seen as entirely inside it (its top
had been clamped to zero before the admission check); the four sides are tested.

Round 2, finding 3: an exception while encoding the render escaped the per-image handling.
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

_HIDING_CASES = {
    # a black fill over the right half: the page shows [64, 0]
    "vector_fill_over": (dict(), dict(overlays=["0 g " + _RIGHT_HALF + " f"]), "not_ink_space"),
    # a dark shading painted over the right half
    "shading_over": (dict(), dict(overlays=["q " + _RIGHT_HALF + " W n /Sh0 sh Q"]), "not_ink_space"),
    # a clip that shows only the right half: the page shows [white, ramp]
    "clip_shows_a_part": (dict(clip=_RIGHT_HALF + " W n"), dict(), "not_ink_space"),
    # the same through a form whose BBox is the right half
    "form_bbox_clip": (dict(form_bbox=(160, 300, 260, 400)), dict(), "not_ink_space"),
    # an ExtGState soft mask whose luminosity is black over the left half
    "extgstate_smask": (dict(gs_smask=True), dict(), "not_ink_space"),
    # a soft mask that makes the left half transparent -- named in the image dictionary
    "image_smask": (dict(smask="left_clear"), dict(), "masked_image"),
    # a colour key that makes the 64 samples transparent -- named in the image dictionary
    "colour_key_mask": (dict(colour_key="[40 90]"), dict(), "masked_image"),
}


@pytest.mark.parametrize("case", sorted(_HIDING_CASES))
def test_a_correct_image_the_page_partly_hides_keeps_its_bytes(tmp_path, monkeypatch, case) -> None:
    image_kwargs, page_kwargs, reason = _HIDING_CASES[case]
    path = write_pdf(tmp_path / (case + ".pdf"), [SyntheticPage(images=[_correct_photo(**image_kwargs)], **page_kwargs)])
    extraction, _plan, outcome, events = _run(path, monkeypatch)
    (stored,) = extraction.images
    # Premise: the page view is anti-correlated with the CORRECT stored picture, so the sign alone would
    # replace it with a render that has lost half of it.
    assert _correlation(_grey(stored.image_bytes), _grey(_page_view(path, (60, 200, 260, 300)))) < -0.5
    assert outcome.replaced == 0
    assert outcome.images == extraction.images
    reasons = [context["reason"] for _level, event, context in events if event == "pdf_image_frame_render_declined"]
    assert reasons == [reason], events


@pytest.mark.parametrize(("case", "image_kwargs"), [("smask", dict(smask="left_clear")), ("colour_key", dict(colour_key="[20 40]"))])
def test_an_ink_space_negative_with_a_mask_in_its_dictionary_is_declined(tmp_path, monkeypatch, case, image_kwargs) -> None:
    """The one structural decline round 3 keeps from round 2, read from the image dictionary pdfminer already
    gives: where a mask is transparent the page shows what is beneath, not the image."""
    path = write_pdf(tmp_path / (case + ".pdf"), [SyntheticPage(images=[_negative_photo(**image_kwargs)])])
    extraction, _plan, outcome, events = _run(path, monkeypatch)
    assert outcome.replaced == 0 and outcome.images == extraction.images
    reasons = [context["reason"] for _level, event, context in events if event == "pdf_image_frame_render_declined"]
    assert reasons == ["masked_image"]


def test_residual_an_ink_image_right_as_stored_and_darkened_by_unobserved_paint_is_replaced(tmp_path) -> None:
    """The residual of the round-3 rule, pinned so that it stays visible: two independent coincidences --
    an ink-space image already right as stored (/Decode [1 0] cancels the tint inversion) AND paint over it
    that this step does not observe (a black fill over its right half) -- make it anti-correlated with its
    frame, and it is replaced by the render, which shows the page with the fill. Spec 082 records this as
    the residual; observing paint was tried in round 2 and dropped in round 3."""
    photo = SyntheticImage("jpeg_separation", 60, 300, 260, 400, pixels=(300, 150), pattern="halves_ramp", decode="[1 0]")
    path = write_pdf(tmp_path / "residual.pdf", [SyntheticPage(images=[photo], overlays=["0 g " + _RIGHT_HALF + " f"])])
    _extraction, _plan, outcome, _events = _run(path)
    (image,) = outcome.images
    assert outcome.replaced == 1 and image.original_image_bytes is not None


@pytest.mark.parametrize(
    ("case", "image_kwargs", "page_kwargs"),
    [
        ("path_beside_the_frame", dict(), dict(overlays=["0 g 270 300 50 100 re f"])),
        ("clip_containing_the_frame", dict(clip="40 280 240 140 re W n"), dict()),
        ("form_bbox_containing_the_frame", dict(form_bbox=(0, 0, 400, 600)), dict()),
        # a picture frame cropping its photograph by a point on every side, as layout programs do
        ("clip_cropping_a_point", dict(clip="61 301 198 98 re W n"), dict()),
    ],
)
def test_an_ink_space_negative_beside_paint_or_inside_a_clip_is_replaced(tmp_path, case, image_kwargs, page_kwargs) -> None:
    """Paint and clips are not observed: a negative is compared on its whole frame and replaced."""
    path = write_pdf(tmp_path / (case + ".pdf"), [SyntheticPage(images=[_negative_photo(**image_kwargs)], **page_kwargs)])
    _extraction, _plan, outcome, _events = _run(path)
    (image,) = outcome.images
    assert outcome.replaced == 1
    assert image.original_image_bytes is not None
    assert _correlation(_grey(image.image_bytes), _grey(image.original_image_bytes)) < -0.9


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


def test_reading_the_image_dictionary_never_raises() -> None:
    """Round 3 (the lesson of its finding 1): what the extractor reads from the image dictionary -- the
    cause, the mask -- may not cost the import its images. An unreadable dictionary declines that image."""
    from docxaicorrector.pdf_import import images as pdf_images

    class _Exploding(dict):
        def get(self, *args, **kwargs):
            raise RuntimeError("invented unreadable dictionary")

    class _Stream:
        attrs = _Exploding()

    class _Image:
        stream = _Stream()

    assert pdf_images._image_mask(_Image()) == "unreadable"
    assert pdf_images._is_ink_space(_Image()) is False


@pytest.mark.parametrize(
    ("colour_space", "ink"),
    [
        ("Separation", True),
        ("DeviceN", True),
        ("IndexedSeparation", True),
        ("IndexedRGB", False),
        ("DeviceGray", False),
        ("ICCBased", False),
        ("Unresolvable", False),
    ],
)
def test_the_cause_is_an_ink_space_indexed_over_one_included(colour_space, ink) -> None:
    from pdfminer.psparser import LIT

    from docxaicorrector.pdf_import import images as pdf_images

    tint = {"FunctionType": 2}
    spaces = {
        "Separation": [LIT("Separation"), LIT("Black"), LIT("DeviceGray"), tint],
        "DeviceN": [LIT("DeviceN"), [LIT("Black")], LIT("DeviceGray"), tint],
        "IndexedSeparation": [LIT("Indexed"), [LIT("Separation"), LIT("Black"), LIT("DeviceGray"), tint], 255, b""],
        "IndexedRGB": [LIT("Indexed"), LIT("DeviceRGB"), 255, b""],
        "DeviceGray": LIT("DeviceGray"),
        "ICCBased": [LIT("ICCBased"), {"N": 3}],
        "Unresolvable": LIT("CS0"),
    }

    class _Stream:
        attrs = {"ColorSpace": spaces[colour_space]}

    class _Image:
        stream = _Stream()

    assert pdf_images._is_ink_space(_Image()) is ink



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


_PER_IMAGE_STAGES = {
    # stage: (function in image_frames, counted as checked when it fails)
    "frame_geometry": ("frame_geometry", 2),
    "render": ("render_frame", 2),
    "comparison": ("correlation_with_page", 2),
    "encode": ("encode_frame_png", 3),
}


@pytest.mark.parametrize("failing_call", ["first", "last"])
@pytest.mark.parametrize("stage", sorted(_PER_IMAGE_STAGES))
def test_a_failure_in_one_image_is_one_failed_image_and_the_rest_are_still_replaced(tmp_path, monkeypatch, stage, failing_call) -> None:
    """Round 2 finding 3 (the encoder), extended in round 3 to every per-image stage: the failing image keeps
    its bytes, is counted as failed, gets one ERROR -- and every other candidate is still processed."""
    photos = [
        SyntheticImage("jpeg_separation", 60, y, 260, y + 100, pixels=(300, 150), pattern="corner")
        for y in (450, 300, 150)
    ]
    path = write_pdf(tmp_path / "three.pdf", [SyntheticPage(images=photos)])
    name, checked = _PER_IMAGE_STAGES[stage]
    real = getattr(image_frames, name)
    calls: list[int] = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if (failing_call == "first" and len(calls) == 1) or (failing_call == "last" and len(calls) == 3):
            raise MemoryError("invented failure at " + stage)
        return real(*args, **kwargs)

    monkeypatch.setattr(image_frames, name, flaky)
    extraction, plan, outcome, events = _run(path, monkeypatch)
    assert len(plan.candidates) == 3 and len(calls) == 3
    assert (outcome.checked, outcome.replaced, outcome.failed) == (checked, 2, 1)
    failed_index = 0 if failing_call == "first" else 2
    failed_key = (plan.candidates[failed_index].image.page_number, plan.candidates[failed_index].image.discovery_index)
    errors = [(level, context) for level, event, context in events if event == "pdf_image_frame_render_failed"]
    assert [(level, (context["page_number"], context["discovery_index"]), context["error_type"]) for level, context in errors] == [
        (logging.ERROR, failed_key, "MemoryError")
    ]
    kept = [image for image in outcome.images if image.original_image_bytes is None]
    assert [(image.page_number, image.discovery_index) for image in kept] == [failed_key]
    assert {image.image_bytes for image in kept} <= {image.image_bytes for image in extraction.images}


@pytest.mark.parametrize("name", ["read_page_geometry", "open_pdf_for_rendering"])
def test_a_document_level_failure_keeps_every_image_and_counts_each_as_failed(tmp_path, monkeypatch, name) -> None:
    """The document cannot be read for rendering: no exception leaves the step, every candidate keeps its
    bytes and gets its own ERROR."""
    photos = [SyntheticImage("jpeg_separation", 60, y, 260, y + 100, pixels=(300, 150), pattern="corner") for y in (450, 150)]
    path = write_pdf(tmp_path / "two.pdf", [SyntheticPage(images=photos)])

    def boom(*args, **kwargs):
        raise OSError("invented unreadable document")

    monkeypatch.setattr(image_frames, name, boom)
    extraction, _plan, outcome, events = _run(path, monkeypatch)
    assert outcome.images == extraction.images
    assert (outcome.checked, outcome.replaced, outcome.failed) == (0, 0, 2)
    assert [level for level, event, _context in events if event == "pdf_image_frame_render_failed"] == [logging.ERROR, logging.ERROR]
