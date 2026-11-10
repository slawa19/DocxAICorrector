"""Spec 072 WP-D: real LibreOffice -> PDF checks (SC-003, SC-006).

Needs ``soffice``; skips without it, fails when DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES is set.
Paragraph set is invented (Constitution VII): ~60 paragraphs, 3 Heading 1, no combining marks.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import threading
import time

import pytest
from docx import Document
from docx.styles.style import ParagraphStyle

from docxaicorrector.generation.narration_pdf import NarrationPdfOutcome, export_narration_pdf
from docxaicorrector.runtime.external_process import find_soffice_binary

pytestmark = pytest.mark.system_deps

REQUIRE_ENV = "DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES"
FONT = "Times New Roman"


@pytest.fixture(scope="module", autouse=True)
def _require_soffice():
    if find_soffice_binary() is None:
        if os.environ.get(REQUIRE_ENV):
            pytest.fail("soffice/libreoffice is required but not found")
        pytest.skip("soffice/libreoffice not available")


def _build_paragraphs() -> list[tuple[str, str]]:
    """(kind, text) pairs; kind is 'h1' or 'p'. Invented text, same shape as narration."""
    items: list[tuple[str, str]] = []
    for chapter in range(1, 4):
        items.append(("h1", f"Глава {chapter}. Вымышленный раздел номер {chapter}"))
        for n in range(1, 20):
            items.append(
                (
                    "p",
                    f"Абзац {chapter}.{n}: путник шёл по тихой дороге, считал шаги — {n * 7} — "
                    f"и спрашивал себя, «зачем?» Ответ, конечно, нашёлся: ёжик знал.",
                )
            )
    return items


def _build_docx(items: list[tuple[str, str]]) -> bytes:
    document = Document()
    for style_name in ("Normal", "Heading 1"):
        style = document.styles[style_name]
        assert isinstance(style, ParagraphStyle)
        style.font.name = FONT
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.get_or_add_rFonts()
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rfonts.set(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}" + attr.split(":")[1], FONT
            )
    for kind, text in items:
        if kind == "h1":
            document.add_heading(text, level=1)
        else:
            document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _strip_ws(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _extract_text(pdf_bytes: bytes) -> str:
    from pdfminer.high_level import extract_text

    return extract_text(io.BytesIO(pdf_bytes))


def _text_matches(pdf_text: str, expected_texts: list[str]) -> bool:
    """Whitespace-free equality of the whole text, each paragraph found in order, no tail."""
    got = _strip_ws(pdf_text)
    if got != _strip_ws("".join(expected_texts)):
        return False
    cursor = 0
    for text in expected_texts:
        index = got.find(_strip_ws(text), cursor)
        if index < 0:
            return False
        cursor = index + len(_strip_ws(text))
    return cursor == len(got)


def _outline_titles(pdf_bytes: bytes) -> list[tuple[int, str]]:
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfparser import PDFParser

    document = PDFDocument(PDFParser(io.BytesIO(pdf_bytes)))
    return [(level, title) for level, title, _dest, _action, _se in document.get_outlines()]


def _fonts_all_embedded(pdf_bytes: bytes) -> tuple[bool, int]:
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdftypes import resolve1

    document = PDFDocument(PDFParser(io.BytesIO(pdf_bytes)))
    seen: set[int] = set()
    count = 0
    for page in PDFPage.create_pages(document):
        fonts = resolve1(resolve1(page.resources).get("Font", {})) or {}
        for ref in fonts.values():
            font = resolve1(ref)
            objid = getattr(ref, "objid", id(font))
            if objid in seen:
                continue
            seen.add(objid)
            descriptor = font.get("FontDescriptor")
            if descriptor is None and font.get("DescendantFonts"):
                descendant = resolve1(resolve1(font["DescendantFonts"])[0])
                descriptor = descendant.get("FontDescriptor")
            descriptor = resolve1(descriptor) if descriptor is not None else None
            count += 1
            if descriptor is None or not any(k in descriptor for k in ("FontFile", "FontFile2", "FontFile3")):
                return False, count
    return count > 0, count


def _check_pdf(pdf_bytes: bytes, items: list[tuple[str, str]]) -> None:
    expected = [text for _kind, text in items]
    assert pdf_bytes.startswith(b"%PDF-")
    assert _text_matches(_extract_text(pdf_bytes), expected)
    outline = _outline_titles(pdf_bytes)
    assert [t for lvl, t in outline if lvl == 1] == [t for k, t in items if k == "h1"]
    embedded, count = _fonts_all_embedded(pdf_bytes)
    assert embedded and count > 0


def _soffice_count() -> int:
    result = subprocess.run(["pgrep", "-c", "soffice"], capture_output=True, text=True, check=False)
    try:
        return int(result.stdout.strip() or 0)
    except ValueError:
        return 0


def test_sc003_real_pdf_text_bookmarks_fonts_and_negative_controls():
    items = _build_paragraphs()
    started = time.monotonic()
    outcome = export_narration_pdf(_build_docx(items), stem="synthetic")
    wall = time.monotonic() - started
    print(f"\nWP-D conversion: outcome.seconds={outcome.seconds:.2f}s wall={wall:.2f}s")

    assert outcome.reason is None, outcome.detail
    assert outcome.pdf_bytes
    assert outcome.seconds > 0
    _check_pdf(outcome.pdf_bytes, items)

    # negative controls through the SAME comparison function
    expected = [text for _kind, text in items]
    pdf_text = _extract_text(outcome.pdf_bytes)
    assert _text_matches(pdf_text, expected)
    assert not _text_matches(pdf_text, expected[:10] + expected[11:])  # a dropped paragraph
    assert not _text_matches(pdf_text, expected + [expected[5]])  # an extra duplicate
    assert not _text_matches("", expected)  # an empty set is not a match


def test_sc006_two_parallel_exports_both_valid_and_no_leaked_processes():
    items = _build_paragraphs()
    docx = _build_docx(items)
    before = _soffice_count()
    results: dict[int, NarrationPdfOutcome] = {}

    def worker(slot: int) -> None:
        results[slot] = export_narration_pdf(docx, stem=f"parallel{slot}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    assert set(results) == {0, 1}
    for outcome in results.values():
        assert outcome.reason is None, outcome.detail
        assert outcome.pdf_bytes is not None
        _check_pdf(outcome.pdf_bytes, items)
    assert _soffice_count() <= before
