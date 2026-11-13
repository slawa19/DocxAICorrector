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


def _picture_sequence(docx_bytes: bytes) -> list[tuple[str, int]]:
    import hashlib
    import io as _io

    from docx import Document

    document = Document(_io.BytesIO(docx_bytes))
    blip = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
    embed = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    out: list[tuple[str, int]] = []
    for position, paragraph in enumerate(document.paragraphs):
        for element in paragraph._element.iter(blip):
            out.append((hashlib.sha1(document.part.related_parts[element.get(embed)].blob).hexdigest(), position))
    return out


def test_rethinking_money_a_failed_region_insertion_restores_the_book_as_without_the_step(monkeypatch) -> None:
    """Acceptance review of slice B, finding 1: p151 holds members that share a source_index (the same top) and were
    discovered in the other order; the rollback must give back the extractor's order, picture for picture."""

    import docxaicorrector.processing.processing_runtime as runtime

    path = _book("Rethinking-money*.pdf")
    monkeypatch.setattr(runtime, "_PDF_PARSE_IN_PROCESS", True)
    with monkeypatch.context() as off:
        off.setattr(
            fr, "replace_composite_figures", lambda p, extraction, images_a, spans, **kwargs: fr.FigureRegionOutcome(images=tuple(images_a))
        )
        baseline, _ = runtime._convert_pdf_text_layer_to_docx(filename=path.name, source_bytes=path.read_bytes())
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(runtime, "log_event", lambda level, event, message, **context: events.append((event, context)))
    real_append = runtime._append_image_bytes_to_docx

    def failing_region(document, image_bytes, *, width_points=None, height_points=None):
        if height_points is not None and height_points > 400:  # the region render is 431 pt tall; no photo of the book is
            raise RuntimeError("invented failure inserting the region")
        return real_append(document, image_bytes, width_points=width_points, height_points=height_points)

    monkeypatch.setattr(runtime, "_append_image_bytes_to_docx", failing_region)
    restored, _ = runtime._convert_pdf_text_layer_to_docx(filename=path.name, source_bytes=path.read_bytes())
    assert _picture_sequence(restored) == _picture_sequence(baseline)
    succeeded = next(context for event, context in events if event == "pdf_text_layer_import_succeeded")
    assert (succeeded["image_count"], succeeded["images_emitted"], succeeded["images_dropped"]) == (55, 55, 0)
    assert (succeeded["figure_regions_inserted"], succeeded["figure_region_members_restored"]) == (0, 22)
