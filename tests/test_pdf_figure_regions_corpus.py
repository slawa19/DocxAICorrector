"""Spec 082 slice B on a real book: Rethinking Money's Figure 7.1 -- 283 images (261 the extractor cannot emit),
2365 paths and 54 label lines -- becomes one picture; no other page of the book qualifies.

The counts and the box below were measured 2026-11-13 (spec 082 research R30-R37) and are the expected results of
this test, not parameters of the rule: the rule reads no page number, count or coordinate.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

from docxaicorrector.pdf_import import figure_regions as fr
from docxaicorrector.pdf_import.image_frames import apply_frame_replacements, plan_frame_replacements
from docxaicorrector.pdf_import.images import extract_pdf_images_and_inventory
from docxaicorrector.pdf_import.logical_import import pdf_body_typography
from docxaicorrector.pdf_import.page_render import read_page_geometry
from docxaicorrector.pdf_import.text_layer_quality import extract_pdf_text_spans_with_pdfminer

pytestmark = pytest.mark.integration_local

_BOOK = Path(__file__).resolve().parent / "sources" / "book"


def _book(pattern: str) -> Path:
    matches = glob.glob(str(_BOOK / pattern))
    if not matches:
        pytest.skip(f"corpus PDF not present: {pattern}")
    return Path(matches[0])


def test_rethinking_money_figure_is_one_region_and_nothing_else_is(monkeypatch) -> None:
    import docxaicorrector.pdf_import.image_frames as image_frames

    monkeypatch.setattr(image_frames, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(fr, "log_event", lambda *args, **kwargs: None)
    path = _book("Rethinking-money*.pdf")
    spans = extract_pdf_text_spans_with_pdfminer(path)
    extraction = extract_pdf_images_and_inventory(path)
    assert fr.seed_pages(extraction) == (151,)

    graphics = fr.read_page_graphics(path, [151])
    geometry = read_page_geometry(path, [151])
    plan = fr.plan_figure_regions(extraction, spans, graphics, pdf_body_typography(spans), {151: geometry[151].layout_cropbox})
    assert plan.declines == ()
    (region,) = plan.regions
    assert region.box == pytest.approx((42.18, 68.21, 353.85, 499.50), abs=0.01)
    assert (region.image_count, region.seed_count, len(region.member_keys), region.path_count, region.grown_line_count) == (
        283, 261, 22, 2365, 2,
    )

    images_a = list(apply_frame_replacements(path, extraction, plan_frame_replacements(extraction, spans)).images)
    outcome = fr.replace_composite_figures(path, extraction, images_a, spans)
    assert (len(images_a), len(outcome.images), outcome.rendered, outcome.images_absorbed) == (55, 34, 1, 22)
    (picture,) = [image for image in outcome.images if image.region_members is not None]
    assert picture.page_number == 151 and len(picture.region_members or ()) == 22
    # every other picture is slice A's, in slice A's order
    assert [image for image in outcome.images if image.region_members is None] == [
        image for image in images_a if image.page_number != 151
    ]
