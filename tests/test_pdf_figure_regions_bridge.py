"""Spec 082 slice B through the PDF bridge (`_convert_pdf_text_layer_to_docx`, parse in process).

The baseline of every comparison is the same bridge with slice B switched off (its entry point returns slice A's
pictures unchanged). Synthetic PDFs (``tests/pdf_synthetic.py``); texts are invented.
"""

from __future__ import annotations

import hashlib
import io
import logging
from types import SimpleNamespace

import pytest

import docxaicorrector.processing.processing_runtime as processing_runtime
from docxaicorrector.pdf_import import figure_regions
from docxaicorrector.pdf_import import images as pdf_images
from pdf_synthetic import SyntheticImage, SyntheticPage, SyntheticText, build_pdf

SENTENCE = "An invented line of running text that goes on for a while."


@pytest.fixture(autouse=True)
def _in_process_and_promising(monkeypatch):
    from docxaicorrector.pdf_import import text_layer_quality

    monkeypatch.setattr(processing_runtime, "_PDF_PARSE_IN_PROCESS", True)
    monkeypatch.setattr(
        text_layer_quality,
        "build_text_layer_quality_report",
        lambda spans: SimpleNamespace(decision="promising", decision_reasons=(), body_text_ratio=1.0),
    )


def _body(top_y: float, count: int = 3, prefix: str = "") -> list[SyntheticText]:
    return [SyntheticText(40, top_y - 15 * i, 11, f"{prefix}{SENTENCE}") for i in range(count)]


def _figure_page(member_kind: str = "jpeg_gray") -> SyntheticPage:
    return SyntheticPage(
        images=[
            SyntheticImage("flate_gray", 100, 250, 200, 350, pixels=(40, 30)),
            SyntheticImage(member_kind, 205, 250, 255, 300, pixels=(50, 50), pattern="corner"),
        ],
        paths=["0 G 1 w 110 260 m 190 340 l S"],
        texts=[*_body(560, prefix="Above. "), SyntheticText(110, 300, 8, "Label A"), SyntheticText(110, 270, 8, "Label B"), *_body(150, prefix="Below. ")],
    )


def _two_regions_page() -> SyntheticPage:
    return SyntheticPage(
        images=[
            SyntheticImage("flate_gray", 60, 250, 140, 330),
            SyntheticImage("jpeg_gray", 60, 335, 140, 380, pixels=(50, 30), pattern="corner"),
            SyntheticImage("flate_gray", 250, 250, 330, 330),
            SyntheticImage("jpeg_gray", 250, 335, 330, 380, pixels=(60, 30), pattern="gradient"),
        ],
        texts=[*_body(560, prefix="Above. "), SyntheticText(70, 300, 8, "Left label"), SyntheticText(260, 300, 8, "Right label"), *_body(150, prefix="Below. ")],
    )


def _sequence(docx_bytes: bytes) -> list[tuple]:
    from docx import Document

    document = Document(io.BytesIO(docx_bytes))
    blip = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
    embed = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    extent = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"
    out: list[tuple] = []
    for paragraph in document.paragraphs:
        if paragraph.text:
            out.append(("p", paragraph.text, paragraph.style.name if paragraph.style is not None else ""))
        for element in paragraph._element.iter(blip):
            blob = document.part.related_parts[element.get(embed)].blob
            size = next(paragraph._element.iter(extent), None)
            out.append(("img", hashlib.sha1(blob).hexdigest(), None if size is None else (size.get("cx"), size.get("cy"))))
    return out


def _convert(pages) -> bytes:
    docx_bytes, _backend = processing_runtime._convert_pdf_text_layer_to_docx(filename="figure.pdf", source_bytes=build_pdf(pages))
    return docx_bytes


def _baseline(monkeypatch, pages) -> list[tuple]:
    with monkeypatch.context() as off:
        off.setattr(
            figure_regions,
            "replace_composite_figures",
            lambda path, extraction, images_a, spans, **kwargs: figure_regions.FigureRegionOutcome(images=tuple(images_a)),
        )
        return _sequence(_convert(pages))


def _events(monkeypatch) -> list[tuple[int, str, dict]]:
    events: list[tuple[int, str, dict]] = []
    record = lambda level, event, message, **context: events.append((level, event, context))  # noqa: E731
    monkeypatch.setattr(processing_runtime, "log_event", record)
    monkeypatch.setattr(figure_regions, "log_event", record)
    monkeypatch.setattr(pdf_images, "log_event", record)
    return events


def _pictures(sequence) -> list[tuple]:
    return [item for item in sequence if item[0] == "img"]


def _paragraphs(sequence) -> list[tuple]:
    return [item for item in sequence if item[0] == "p"]


def test_a_composite_figure_reaches_the_docx_as_one_picture_and_the_text_is_unchanged(monkeypatch) -> None:
    baseline = _baseline(monkeypatch, [_figure_page()])
    events = _events(monkeypatch)
    working = _sequence(_convert([_figure_page()]))
    assert _paragraphs(working) == _paragraphs(baseline)
    assert len(_pictures(baseline)) == 1 and len(_pictures(working)) == 1 and _pictures(working) != _pictures(baseline)
    succeeded = next(context for _l, event, context in events if event == "pdf_text_layer_import_succeeded")
    assert (succeeded["images_emitted"], succeeded["figure_regions_inserted"], succeeded["figure_region_members_restored"]) == (1, 1, 0)
    summary = next(context for _l, event, context in events if event.startswith("pdf_image_extraction_"))
    assert (summary["figure_region_rendered"], summary["figure_region_images_absorbed"]) == (1, 1)
    assert sum(1 for _l, event, _c in events if event.startswith("pdf_image_extraction_")) == 1


def test_the_span_list_is_the_extractors_list_untouched(monkeypatch, tmp_path) -> None:
    from docxaicorrector.pdf_import import text_layer_quality

    pdf = tmp_path / "figure.pdf"
    pdf.write_bytes(build_pdf([_figure_page()]))
    real_extract = text_layer_quality.extract_pdf_text_spans_with_pdfminer
    seen: dict[str, object] = {}

    def recording(path):
        spans = list(real_extract(path))
        seen["list"], seen["copy"] = spans, list(spans)
        return spans

    monkeypatch.setattr(text_layer_quality, "extract_pdf_text_spans_with_pdfminer", recording)
    real_step = figure_regions.replace_composite_figures

    def spying(path, extraction, images_a, spans, **kwargs):
        seen["step"] = spans
        return real_step(path, extraction, images_a, spans, **kwargs)

    monkeypatch.setattr(figure_regions, "replace_composite_figures", spying)
    result = processing_runtime._run_pdf_parse_stages(
        input_path=pdf, ocr_output_path=tmp_path / "ocr.pdf", filename="figure.pdf", ocr_import_enabled=False,
        max_page_count=10, max_span_count=10_000, max_image_count=10,
    )
    assert any(getattr(image, "region_members", None) is not None for image in result.image_objects)  # not vacuous
    # the step reads the very list the importer is handed, and that list is still the extractor's spans
    assert seen["step"] is result.spans and result.spans == seen["copy"]


@pytest.mark.parametrize("failing", ["first", "second"])
def test_a_region_that_cannot_be_inserted_rebuilds_its_whole_page_as_without_the_step(monkeypatch, failing) -> None:
    pages = [_two_regions_page()]
    baseline = _baseline(monkeypatch, pages)
    working = _sequence(_convert(pages))
    assert len(_pictures(working)) == 2 and _pictures(working) != _pictures(baseline)  # not vacuous
    events = _events(monkeypatch)
    real_append = processing_runtime._append_image_bytes_to_docx
    calls = {"regions": 0}

    def failing_region(document, image_bytes, *, width_points=None, height_points=None):
        if image_bytes.startswith(b"\x89PNG"):
            calls["regions"] += 1
            if (failing == "first" and calls["regions"] == 1) or (failing == "second" and calls["regions"] == 2):
                raise RuntimeError("invented failure inserting a region")
        return real_append(document, image_bytes, width_points=width_points, height_points=height_points)

    monkeypatch.setattr(processing_runtime, "_append_image_bytes_to_docx", failing_region)
    restored = _sequence(_convert(pages))
    assert restored == baseline
    failed = [context for level, event, context in events if event == "pdf_figure_region_insert_failed" and level == logging.ERROR]
    assert len(failed) == 1 and (failed[0]["regions"], failed[0]["members_restored"]) == (2, 2)
    succeeded = next(context for _l, event, context in events if event == "pdf_text_layer_import_succeeded")
    assert (succeeded["images_emitted"], succeeded["figure_regions_inserted"], succeeded["figure_region_members_restored"]) == (2, 0, 2)


def test_a_slice_a_render_absorbed_by_a_region_comes_back_as_slice_a_delivered_it(monkeypatch) -> None:
    pages = [_figure_page(member_kind="jpeg_separation")]
    baseline = _baseline(monkeypatch, pages)  # slice A replaces the negative member
    events = _events(monkeypatch)
    working = _sequence(_convert(pages))
    assert len(_pictures(working)) == 1 and _pictures(working) != _pictures(baseline)
    rendered = next(context for _l, event, context in events if event == "pdf_figure_region_rendered")
    assert rendered["absorbed_frame_renders"] == 1
    real_append = processing_runtime._append_image_bytes_to_docx

    def failing_region(document, image_bytes, *, width_points=None, height_points=None):
        if image_bytes.startswith(b"\x89PNG") and width_points and width_points > 100:
            raise RuntimeError("invented failure inserting a region")
        return real_append(document, image_bytes, width_points=width_points, height_points=height_points)

    monkeypatch.setattr(processing_runtime, "_append_image_bytes_to_docx", failing_region)
    assert _sequence(_convert(pages)) == baseline


@pytest.mark.parametrize("stage", ["inventory", "plan", "page_geometry", "render", "encode", "step"])
def test_a_failure_in_the_step_leaves_the_document_as_without_it(monkeypatch, stage) -> None:
    from docxaicorrector.pdf_import import page_render

    pages = [_figure_page()]
    baseline = _baseline(monkeypatch, pages)

    def boom(*args, **kwargs):
        raise RuntimeError("invented failure at " + stage)

    targets = {
        "inventory": (figure_regions, "read_page_graphics"),
        "plan": (figure_regions, "plan_figure_regions"),
        "page_geometry": (page_render, "read_page_geometry"),
        "render": (page_render, "render_frame"),
        "encode": (page_render, "encode_frame_png"),
        "step": (figure_regions, "replace_composite_figures"),
    }
    module, name = targets[stage]
    events = _events(monkeypatch)
    monkeypatch.setattr(module, name, boom)
    assert _sequence(_convert(pages)) == baseline
    assert any(level == logging.ERROR and event == "pdf_figure_region_failed" for level, event, _c in events)


def test_no_region_in_the_ocr_branch(monkeypatch, tmp_path) -> None:
    from docxaicorrector.pdf_import.images import extract_pdf_images_and_inventory

    pdf = tmp_path / "figure.pdf"
    pdf.write_bytes(build_pdf([_figure_page()]))
    called = []
    monkeypatch.setattr(figure_regions, "replace_composite_figures", lambda *a, **k: called.append(1))
    events = _events(monkeypatch)
    extraction = extract_pdf_images_and_inventory(pdf)
    images = processing_runtime._replace_pdf_images_by_page_frames(pdf, extraction, [], ocr_used=True)
    assert called == [] and images == list(extraction.images)
    summary = next(context for _l, event, context in events if event.startswith("pdf_image_extraction_"))
    assert summary["figure_region_enabled"] is False


def test_the_image_cap_is_checked_before_the_steps_and_slice_b_never_exceeds_it(monkeypatch) -> None:
    # one emitted picture: a cap of 0 rejects the document before any step, as without slice B
    monkeypatch.setattr(processing_runtime, "_MAX_PDF_IMPORT_IMAGE_COUNT", 0)
    with pytest.raises(RuntimeError, match="pdf_import_over_budget:image_count"):
        _convert([_figure_page()])
    # a lone seed and nothing emitted: the cap of 0 holds, and slice B does not add its picture
    lone = SyntheticPage(images=[SyntheticImage("flate_gray", 100, 250, 200, 350)], texts=[*_body(560), *_body(150)])
    assert _pictures(_sequence(_convert([lone]))) == []
    monkeypatch.setattr(processing_runtime, "_MAX_PDF_IMPORT_IMAGE_COUNT", 1)
    assert len(_pictures(_sequence(_convert([lone])))) == 1


def test_neighbouring_paragraphs_are_the_same_after_document_preparation(monkeypatch) -> None:
    """N pictures between short paragraphs become one: the document layer (boundaries, roles, captions) must see
    the same paragraphs, apart from the picture rows."""

    from docxaicorrector.core.config import load_app_config
    from docxaicorrector.core.constants import DEFAULT_CHUNK_SIZE
    from docxaicorrector.processing.preparation import _prepare_document_for_processing

    page = SyntheticPage(
        images=[
            SyntheticImage("flate_gray", 100, 250, 200, 350),
            SyntheticImage("jpeg_gray", 205, 330, 255, 350, pixels=(50, 20), pattern="corner"),
            SyntheticImage("jpeg_gray", 205, 290, 255, 310, pixels=(50, 20), pattern="gradient"),
            SyntheticImage("jpeg_gray", 205, 250, 255, 270, pixels=(50, 20), pattern="corner"),
        ],
        texts=[
            *_body(560, prefix="Above. "),
            SyntheticText(110, 335, 8, "Top label"),
            SyntheticText(110, 300, 8, "Middle label"),
            SyntheticText(110, 260, 8, "Bottom label"),
            SyntheticText(40, 225, 9, "Figure 1.1 An invented diagram."),
            *_body(150, prefix="Below. "),
        ],
    )

    def prepared_rows() -> list[tuple]:
        config = load_app_config()
        config = dict(config) if isinstance(config, dict) else dict(config.to_dict())
        normalized = processing_runtime.normalize_uploaded_document(filename="figure.pdf", source_bytes=build_pdf([page]))
        prepared = _prepare_document_for_processing(
            normalized.filename, normalized.content_bytes, DEFAULT_CHUNK_SIZE, source_format=normalized.source_format,
            conversion_backend=normalized.conversion_backend, app_config=config, processing_operation="audiobook",
            get_client_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model")), client_factory=None,
        )
        rows = []
        for job in prepared.jobs:
            texts = str(job["target_text"]).split("\n\n")
            reasons = job.get("narration_exclusion_reasons") or [None] * len(job["paragraph_ids"])
            for k in range(len(job["paragraph_ids"])):
                rows.append((job["structural_roles"][k], reasons[k], texts[k] if len(texts) == len(job["paragraph_ids"]) else None))
        return rows

    with monkeypatch.context() as off:
        off.setattr(
            figure_regions,
            "replace_composite_figures",
            lambda path, extraction, images_a, spans, **kwargs: figure_regions.FigureRegionOutcome(images=tuple(images_a)),
        )
        baseline = prepared_rows()
    working = prepared_rows()
    assert sum(1 for row in baseline if row[0] == "image") == 3 and sum(1 for row in working if row[0] == "image") == 1
    assert [row for row in working if row[0] != "image"] == [row for row in baseline if row[0] != "image"]
