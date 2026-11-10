"""Spec 072 WP-H, T-H7: the product chain end to end with the REAL LibreOffice (SC-001 + SC-003 on the product file).

Narration records -> ``_build_narration_text`` (groups) -> ``build_narration_exports`` (plan -> DOCX -> the real
``export_narration_pdf``) -> the checks of T-D6 on the files the product made, not on a DOCX built by the test.

Needs ``soffice``; skips without it, fails when ``DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES`` is set. The text set is
invented (Constitution VII), of the same form as narration: three chapters, heading series ``2 -> 1`` and ``1 -> 2``,
a torn sentence the assembly joins, a ``needs_review`` record; no combining marks (the PDF text layer of U+0301 is a
Non-goal of the spec).
"""

from __future__ import annotations

import io
import os
import re
import time
from types import SimpleNamespace

import docx
import pytest

from docxaicorrector.pipeline.audiobook_pass import NarrationParagraphRecord
from docxaicorrector.pipeline.contracts import ProcessingState
from docxaicorrector.pipeline.narration_exports import build_narration_exports
from docxaicorrector.pipeline.narration_postprocess import _build_narration_text
from docxaicorrector.runtime.external_process import find_soffice_binary
from docxaicorrector.text.narration_coverage import CoverageResult

pytestmark = pytest.mark.system_deps

REQUIRE_ENV = "DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES"


@pytest.fixture(scope="module", autouse=True)
def _require_soffice():
    if find_soffice_binary() is None:
        if os.environ.get(REQUIRE_ENV):
            pytest.fail("soffice/libreoffice is required but not found")
        pytest.skip("soffice/libreoffice not available")


def _record(pid: str, text: str, role: str = "body", reasons: tuple[str, ...] = (), level: int | None = None) -> NarrationParagraphRecord:
    return NarrationParagraphRecord(
        paragraph_id=pid,
        block_index=1,
        role=role,
        text=text,
        needs_review_reasons=reasons,
        residue_before=(),
        residue_after=(),
        coverage=CoverageResult(0, 0, None),
        heading_level=level,
    )


def _records() -> list[NarrationParagraphRecord]:
    records = [
        _record("c1a", "Часть первая", role="heading", level=2),
        _record("c1b", "Тихая дорога", role="heading", level=1),
    ]
    for n in range(1, 13):
        records.append(_record(f"c1p{n}", f"Путник шёл по тихой дороге и считал шаги: {n * 7}. Ёжик знал ответ, «зачем?»"))
    records += [
        _record("c1t1", "Дорога вела вдоль реки, и никто"),
        _record("c1t2", "не спрашивал, куда он идёт."),
        _record("c2", "Глава вторая", role="heading", level=1),
        _record("c2s", "Подраздел о мосте", role="heading", level=2),
    ]
    for n in range(1, 13):
        records.append(_record(f"c2p{n}", f"Мост над оврагом скрипел под ногами — {n} раз подряд — и затихал."))
    records.append(_record("c2r", "Этот абзац вернулся из источника.", reasons=("source_restored",)))
    records.append(_record("c3", "Послесловие", role="heading", level=1))
    for n in range(1, 6):
        records.append(_record(f"c3p{n}", f"Последние страницы, номер {n}, закрывают книгу."))
    return records


def _strip_ws(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _text_matches(pdf_text: str, expected_texts: list[str]) -> bool:
    """Whitespace-free equality of the whole text, each paragraph found in order, no tail (T-D6)."""

    got = _strip_ws(pdf_text)
    if not expected_texts or got != _strip_ws("".join(expected_texts)):
        return False
    cursor = 0
    for text in expected_texts:
        index = got.find(_strip_ws(text), cursor)
        if index < 0:
            return False
        cursor = index + len(_strip_ws(text))
    return cursor == len(got)


def _pdf_text(pdf_bytes: bytes) -> str:
    from pdfminer.high_level import extract_text

    return extract_text(io.BytesIO(pdf_bytes))


def _outline_level_1(pdf_bytes: bytes) -> list[str]:
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfparser import PDFParser

    document = PDFDocument(PDFParser(io.BytesIO(pdf_bytes)))
    return [title for level, title, _dest, _action, _se in document.get_outlines() if level == 1]


def _fonts_all_embedded(pdf_bytes: bytes) -> bool:
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdftypes import resolve1

    document = PDFDocument(PDFParser(io.BytesIO(pdf_bytes)))
    count = 0
    for page in PDFPage.create_pages(document):
        fonts = resolve1(resolve1(page.resources).get("Font", {})) or {}
        for ref in fonts.values():
            font = resolve1(ref)
            descriptor = font.get("FontDescriptor")
            if descriptor is None and font.get("DescendantFonts"):
                descriptor = resolve1(resolve1(font["DescendantFonts"])[0]).get("FontDescriptor")
            descriptor = resolve1(descriptor) if descriptor is not None else None
            count += 1
            if descriptor is None or not any(key in descriptor for key in ("FontFile", "FontFile2", "FontFile3")):
                return False
    return count > 0


def test_t_h7_records_to_tts_docx_and_tts_pdf_through_the_product_chain():
    records = _records()
    state = ProcessingState(
        narration_paragraphs=records,
        narration_expected_paragraph_ids=[record.paragraph_id for record in records],
    )
    tts_text = _build_narration_text(
        context=SimpleNamespace(processing_operation="audiobook", runtime=None),
        dependencies=None,
        emitters=None,
        state=state,
    )
    assert isinstance(tts_text, str) and tts_text
    events: list[tuple[int, str, dict[str, object]]] = []

    started = time.monotonic()
    exports = build_narration_exports(
        groups=state.narration_groups,
        source_name="synthetic book.docx",
        log_event=lambda level, event, message, **context: events.append((level, event, context)),
    )
    wall = time.monotonic() - started
    print(f"\nWP-H product chain: pdf.seconds={exports.pdf.seconds:.2f}s wall={wall:.2f}s reason={exports.pdf.reason}")

    assert events == []
    assert exports.pdf.reason is None, exports.pdf.detail
    assert exports.docx_bytes and exports.pdf_bytes and exports.pdf_bytes.startswith(b"%PDF-")

    # the product DOCX: Heading 1 / Normal only; the paragraphs are the .tts.txt with the two listed merges
    document = docx.Document(io.BytesIO(exports.docx_bytes))
    paragraphs = [(paragraph.style.name if paragraph.style is not None else "", paragraph.text) for paragraph in document.paragraphs]
    assert {style for style, _text in paragraphs} == {"Heading 1", "Normal"}
    assert document.core_properties.title == "synthetic book"
    tts_paragraphs = tts_text.split("\n\n")
    assert [text for _style, text in paragraphs] == ["Часть первая. Тихая дорога", *tts_paragraphs[2:]]
    headings_1 = [text for style, text in paragraphs if style == "Heading 1"]
    assert headings_1 == ["Часть первая. Тихая дорога", "Глава вторая", "Послесловие"]
    assert ("Normal", "Подраздел о мосте") in paragraphs
    assert "Дорога вела вдоль реки, и никто не спрашивал, куда он идёт." in tts_paragraphs
    plan = exports.plan
    assert plan is not None
    assert [(list(m.paragraph_ids), list(m.levels), m.style) for m in plan.heading_merges] == [
        (["c1a", "c1b"], [2, 1], "Heading 1")
    ]

    # the product PDF (T-D6): text, order, no tail; bookmarks = Heading 1; fonts embedded
    expected_texts = [text for _style, text in paragraphs]
    pdf_text = _pdf_text(exports.pdf_bytes)
    assert _text_matches(pdf_text, expected_texts)
    assert _outline_level_1(exports.pdf_bytes) == headings_1
    assert _fonts_all_embedded(exports.pdf_bytes)
    # negative controls through the SAME comparison function
    assert not _text_matches(pdf_text, expected_texts[:5] + expected_texts[6:])
    assert not _text_matches(pdf_text, expected_texts + [expected_texts[3]])
    assert not _text_matches(pdf_text, [])
