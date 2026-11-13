"""Spec 082 slice A on a real book: Rethinking Money stores its photographs as JPEGs in a one-ink
Separation space, and every one of them was emitted as a negative before spec 082.

Corpus counts below were measured 2026-11-13 (spec 082 research R20, R25) and are the expected results of
this test, not parameters of the rule: the rule reads no page number, no count and no colour-space name.
"""

from __future__ import annotations

import glob
import io
from pathlib import Path

import pytest
from PIL import Image

from docxaicorrector.pdf_import.image_frames import (
    DECLINE_IMAGE_OVER_FRAME,
    DECLINE_PAINT_OVER_FRAME,
    DECLINE_TEXT_OVER_FRAME,
    apply_frame_replacements,
    plan_frame_replacements,
)
from docxaicorrector.pdf_import.images import extract_pdf_images_and_inventory
from docxaicorrector.pdf_import.text_layer_quality import extract_pdf_text_spans_with_pdfminer

pytestmark = pytest.mark.integration_local

_BOOK = Path(__file__).resolve().parent / "sources" / "book"

# Pages of the photographs replaced (research R20; R28 after acceptance round 2). The 22 images of the
# composite figure on page 151 (12 Separation, 10 ICCBased) are declined before rendering: labels or other
# images lie over every frame. The photograph on page 276 -- a negative -- is declined since round 2: a
# 1.5 pt grey border is stroked over three of its edges, so its render is not the image alone. The cover
# (page 1) reaches 0.00001 pt above the page and is no longer compared (it was kept as emitted before too).
# Every replaced photograph is clipped by its picture frame; the sign is read on the part the clip shows.
_REPLACED_PAGES = [
    26, 38, 52, 72, 88, 94, 96, 103, 105, 110, 119, 120, 121, 126, 134, 140,
    142, 156, 159, 166, 174, 176, 178, 181, 184, 190, 192, 198, 202, 218, 230,
]


def _book(pattern: str) -> Path:
    matches = glob.glob(str(_BOOK / pattern))
    if not matches:
        pytest.skip(f"corpus PDF not present: {pattern}")
    return Path(matches[0])


def test_rethinking_money_negatives_are_replaced_and_nothing_else_is(monkeypatch) -> None:
    import docxaicorrector.pdf_import.image_frames as image_frames

    monkeypatch.setattr(image_frames, "log_event", lambda *args, **kwargs: None)
    path = _book("Rethinking-money*.pdf")
    spans = extract_pdf_text_spans_with_pdfminer(path)
    extraction = extract_pdf_images_and_inventory(path)
    assert (len(extraction.discovered), len(extraction.images)) == (316, 55)

    plan = plan_frame_replacements(extraction, spans)
    outcome = apply_frame_replacements(path, extraction, plan)

    replaced = [image for image in outcome.images if image.original_image_bytes is not None]
    assert [image.page_number for image in replaced] == _REPLACED_PAGES
    assert (outcome.checked, outcome.replaced, outcome.declined, outcome.failed) == (31, 31, 24, 0)
    declines = list(plan.declines)
    assert {decline.image.page_number for decline in declines if decline.image.page_number != 276} == {151}
    assert {decline.reason for decline in declines if decline.image.page_number == 151} <= {DECLINE_TEXT_OVER_FRAME, DECLINE_IMAGE_OVER_FRAME}
    assert [decline.reason for decline in declines if decline.image.page_number == 276] == [DECLINE_PAINT_OVER_FRAME]
    assert all(candidate.visible_box is not None for candidate in plan.candidates if candidate.image.page_number != 1)
    for image in replaced:
        assert image.original_image_bytes is not None
        source = Image.open(io.BytesIO(image.original_image_bytes))
        render = Image.open(io.BytesIO(image.image_bytes))
        assert render.size[0] >= source.size[0] and render.size[1] >= source.size[1], image.page_number
    # Everything that is not replaced is the very object the extractor emitted.
    kept = [after for before, after in zip(extraction.images, outcome.images) if after.original_image_bytes is None]
    assert len(kept) == 24
    assert all(after is before for before, after in zip(extraction.images, outcome.images) if after.original_image_bytes is None)
