"""Spec 082 slice A, Codex acceptance review: reproductions of the findings, kept as regression tests.

Each test builds a tiny PDF (``tests/pdf_synthetic.py``) and runs the replacement end to end. The picture
check is spatial: the synthetic photograph is asymmetric (a dark block in its top-left quarter), and the
delivered picture must correlate with the page and anti-correlate with the stored negative -- the mean
brightness of a symmetric gradient cannot tell a negative from its page (review finding 6).
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from docxaicorrector.pdf_import.image_frames import apply_frame_replacements, plan_frame_replacements
from docxaicorrector.pdf_import.images import extract_pdf_images_and_inventory
from pdf_synthetic import SyntheticImage, SyntheticPage, SyntheticText, write_pdf

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


def _page_view(path, page_number: int, box) -> bytes:
    """The page as pdfium shows it, cropped by PIL to the image box (an independent crop path)."""
    import pypdfium2

    document = pypdfium2.PdfDocument(str(path))
    try:
        page = document[page_number - 1]
        whole = page.render(scale=3).to_pil().convert("L")
    finally:
        document.close()
    buffer = io.BytesIO()
    whole.crop(tuple(int(round(v * 3.0)) for v in box)).save(buffer, format="PNG")
    return buffer.getvalue()


def _run(path):
    from docxaicorrector.pdf_import.text_layer_quality import extract_pdf_text_spans_with_pdfminer

    extraction = extract_pdf_images_and_inventory(path)
    plan = plan_frame_replacements(extraction, extract_pdf_text_spans_with_pdfminer(path))
    return extraction, plan, apply_frame_replacements(path, extraction, plan)


def _photo(kind="jpeg_separation", **kwargs) -> SyntheticImage:
    return SyntheticImage(kind, 60, 300, 260, 400, pixels=(300, 150), pattern="corner", **kwargs)


def test_delivered_picture_is_the_page_and_not_the_stored_negative_spatially(tmp_path) -> None:
    """Finding 6. Mutation 'deliver the stored pixels as PNG' fails this test (the mean test did not)."""
    path = write_pdf(tmp_path / "corner.pdf", [SyntheticPage(images=[_photo()])])
    extraction, _plan, outcome = _run(path)
    (replaced,) = outcome.images
    assert replaced.original_image_bytes is not None
    page = _grey(_page_view(path, 1, (replaced.x0, replaced.top, replaced.x1, replaced.bottom)))
    delivered = _grey(replaced.image_bytes)
    stored = _grey(replaced.original_image_bytes)
    assert _correlation(stored, page) < -0.9
    assert _correlation(delivered, page) > 0.95


def test_a_frame_partly_outside_the_cropbox_is_declined_not_cropped(tmp_path) -> None:
    """Finding 1: a frame that is not entirely inside the visible page would lose source pixels."""
    path = write_pdf(tmp_path / "partly.pdf", [SyntheticPage(cropbox=(0, 0, 400, 350), images=[_photo()])])
    extraction, _plan, outcome = _run(path)
    assert outcome.images == extraction.images
    assert outcome.replaced == 0


def test_an_inherited_mediabox_does_not_shift_the_rendered_frame(tmp_path) -> None:
    """Finding 2: MediaBox on the Pages node, CropBox on the page; the render must show the image's own area."""
    page = SyntheticPage(mediabox=(10, 20, 410, 620), cropbox=(30, 50, 390, 590), inherit_mediabox=True, images=[_photo()])
    path = write_pdf(tmp_path / "inherited.pdf", [page])
    _extraction, _plan, outcome = _run(path)
    (image,) = outcome.images
    assert image.original_image_bytes is not None
    assert _correlation(_grey(image.image_bytes), _grey(image.original_image_bytes)) < -0.9


@pytest.mark.parametrize("rotate", [90, 270])
def test_an_inherited_rotation_does_not_shift_the_rendered_frame(tmp_path, rotate) -> None:
    page = SyntheticPage(cropbox=(20, 30, 380, 570), rotate=rotate, inherit_rotate=True, images=[_photo()])
    path = write_pdf(tmp_path / ("rot%d.pdf" % rotate), [page])
    _extraction, _plan, outcome = _run(path)
    (image,) = outcome.images
    if image.original_image_bytes is None:
        return  # declined is acceptable; a shifted render is not
    assert _correlation(_grey(image.image_bytes, (24, 48)), _grey(image.original_image_bytes, (24, 48))) != pytest.approx(0, abs=0.5)


@pytest.mark.parametrize(
    "matrix",
    [
        (0.0, 100.0, -200.0, 0.0, 260.0, 300.0),   # rotated 90 degrees
        (141.4, 141.4, -70.7, 70.7, 160.0, 250.0),  # rotated 45 degrees
        (200.0, 0.0, 0.0, -100.0, 60.0, 400.0),    # mirrored top to bottom
        (-200.0, 0.0, 0.0, 100.0, 260.0, 300.0),   # mirrored left to right
    ],
)
def test_an_image_placed_by_a_matrix_other_than_an_upright_scale_is_declined(tmp_path, matrix) -> None:
    """Finding 4: the source pixel density is defined only for an upright, axis-aligned placement."""
    path = write_pdf(tmp_path / "matrix.pdf", [SyntheticPage(images=[_photo(matrix=matrix)])])
    extraction, _plan, outcome = _run(path)
    assert outcome.images == extraction.images and outcome.replaced == 0


def test_a_page_with_a_user_unit_is_declined(tmp_path) -> None:
    """Finding 5: page units are not points there, so the explicit DOCX size would be wrong."""
    path = write_pdf(tmp_path / "unit.pdf", [SyntheticPage(user_unit=2.0, images=[_photo()])])
    extraction, _plan, outcome = _run(path)
    assert outcome.images == extraction.images and outcome.replaced == 0


@pytest.mark.parametrize(
    ("decode", "colourant"),
    [("[1 0]", "Black"), (None, "All")],
)
def test_an_ink_space_image_that_already_looks_like_its_page_is_not_replaced(tmp_path, decode, colourant) -> None:
    """Finding 3: Decode [1 0] cancels the tint inversion; the stored file is already the page's picture.
    (/All paints every colourant: with the grey alternate the page again shows 1 - tint.)"""
    path = write_pdf(tmp_path / "premise.pdf", [SyntheticPage(images=[_photo(decode=decode, colourant=colourant)])])
    extraction, _plan, outcome = _run(path)
    (image,) = outcome.images
    page = _grey(_page_view(path, 1, (image.x0, image.top, image.x1, image.bottom)))
    stored_correlation = _correlation(_grey(extraction.images[0].image_bytes), page)
    if stored_correlation > 0:
        assert image.original_image_bytes is None
    else:
        assert image.original_image_bytes is not None


def test_a_flat_image_is_declined(tmp_path) -> None:
    """A picture without variance has no sign of correlation: nothing tells a negative from it."""
    flat = SyntheticImage("jpeg_separation", 60, 300, 260, 400, pixels=(300, 150), pattern="flat")
    path = write_pdf(tmp_path / "flat.pdf", [SyntheticPage(images=[flat])])
    extraction, _plan, outcome = _run(path)
    assert outcome.images == extraction.images and outcome.replaced == 0


def test_a_device_gray_negative_is_replaced_by_evidence_not_by_label(tmp_path) -> None:
    """The evidence rule, not a colour-space label: a light-space image drawn with Decode [1 0] is a
    negative of its page and is replaced too."""
    photo = SyntheticImage("jpeg_gray", 60, 300, 260, 400, pixels=(300, 150), pattern="corner", decode="[1 0]")
    path = write_pdf(tmp_path / "gray_negative.pdf", [SyntheticPage(images=[photo], texts=[SyntheticText(40, 520, 11, "An invented line.")])])
    _extraction, _plan, outcome = _run(path)
    (image,) = outcome.images
    assert image.original_image_bytes is not None
    assert _correlation(_grey(image.image_bytes), _grey(image.original_image_bytes)) < -0.9
