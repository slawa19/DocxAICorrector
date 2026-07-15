"""Counter-proof tests for spec 020 — preserve authored tables; flatten scan-origin.

Two behaviors are pinned here:

1. Part 1 — a KEPT table is emitted as a Pandoc-markdown table and therefore
   survives the render as a real Word ``w:tbl`` (raw ``<table>`` HTML is dropped
   by Pandoc; markdown tables are not).
2. Part 2 — a document classified as scan-origin (OCR) has its tables flattened
   into linear body paragraphs (no ``w:tbl``), with cell text conserved, while
   authored documents keep their tables. The classifier is pinned on the
   measured provenance signals (RESISTANCE=129 multi-col vs authored 0-2).
"""

import re
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

import docxaicorrector.generation._generation as generation
from docx import Document

from docxaicorrector.document.extraction import build_document_text, extract_document_content_from_docx
from docxaicorrector.document.provenance import (
    classify_document_scan_origin,
    classify_scan_origin_from_document_xml,
)


BOOK_SOURCES = Path(__file__).resolve().parent / "sources" / "book"
RESISTANCE = BOOK_SOURCES / "RESISTANCE FACTORS AND SPECIAL FORCES AREAS UKRAINE.docx"
MAZZUCATO = BOOK_SOURCES / "The Value of Everything. Making and Taking in the Global Economy by Mariana Mazzucato (z-lib.org).docx"
LIETAER = BOOK_SOURCES / "Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne.docx"


def _pandoc_available() -> bool:
    generation.ensure_pandoc_available.cache_clear()
    try:
        generation.ensure_pandoc_available()
        return True
    except Exception:
        return False
    finally:
        generation.ensure_pandoc_available.cache_clear()


def _count_word_tables(docx_bytes: bytes) -> int:
    with zipfile.ZipFile(BytesIO(docx_bytes)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8", "ignore")
    return len(re.findall(r"<w:tbl\b", document_xml))


def _output_all_text(docx_bytes: bytes) -> str:
    document = Document(BytesIO(docx_bytes))
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def _strip_ws(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _synthetic_document_xml(*, num_sections: int, multi_column_sections: int) -> str:
    sections = []
    for index in range(num_sections):
        num = 2 if index < multi_column_sections else 1
        sections.append(f'<w:p><w:pPr><w:sectPr><w:cols w:num="{num}"/></w:sectPr></w:pPr></w:p>')
    body = "".join(sections)
    return f'<w:document xmlns:w="ns"><w:body>{body}<w:sectPr><w:cols w:num="1"/></w:sectPr></w:body></w:document>'


# --------------------------------------------------------------------------- #
# Required counter-proof 1: scan-origin classifier (threshold pinned on corpus) #
# --------------------------------------------------------------------------- #


def test_scan_origin_classifier_pins_corpus_provenance():
    resistance = classify_document_scan_origin(RESISTANCE.read_bytes())
    mazzucato = classify_document_scan_origin(MAZZUCATO.read_bytes())
    lietaer = classify_document_scan_origin(LIETAER.read_bytes())

    assert resistance.is_scan_origin is True
    assert resistance.multi_column_section_count == 129

    assert mazzucato.is_scan_origin is False
    assert mazzucato.multi_column_section_count == 0

    assert lietaer.is_scan_origin is False
    assert lietaer.multi_column_section_count == 2


def test_scan_origin_classifier_does_not_over_trigger_on_authored_two_column_layout():
    # Anti-vacuum: a normal authored document with a couple of two-column
    # sections must stay authored (bias to authored; don't flatten magazines).
    authored_xml = _synthetic_document_xml(num_sections=10, multi_column_sections=3)
    classification = classify_scan_origin_from_document_xml(authored_xml)

    assert classification.multi_column_section_count == 3
    assert classification.is_scan_origin is False


def test_scan_origin_classifier_flags_high_multi_column_density():
    scan_xml = _synthetic_document_xml(num_sections=200, multi_column_sections=120)
    classification = classify_scan_origin_from_document_xml(scan_xml)

    assert classification.multi_column_section_count == 120
    assert classification.is_scan_origin is True


# --------------------------------------------------------------------------- #
# Required counter-proof 2: scan tables flattened + conservation (RESISTANCE)  #
# --------------------------------------------------------------------------- #


def test_scan_origin_document_flattens_tables_and_conserves_cell_text():
    source_bytes = RESISTANCE.read_bytes()
    paragraphs, _ = extract_document_content_from_docx(BytesIO(source_bytes))

    # No table survives extraction for a scan-origin document.
    assert all(paragraph.role != "table" for paragraph in paragraphs)

    body_stream = _strip_ws(build_document_text(paragraphs))
    source_document = Document(BytesIO(source_bytes))

    missing: list[str] = []
    checked = 0
    for table in source_document.tables:
        for row in table.rows:
            seen: set[int] = set()
            for cell in row.cells:
                identity = id(cell._tc)
                if identity in seen:
                    continue
                seen.add(identity)
                cell_text = _strip_ws(cell.text)
                if not cell_text:
                    continue
                checked += 1
                if cell_text not in body_stream:
                    missing.append(cell.text)

    assert checked > 100  # sanity: the fixture really has substantial tabular data
    # Whitespace-insensitive conservation: at most a negligible tail of OCR cells
    # whose surrounding punctuation (wrapping quotes) reflowed; the token content
    # is preserved. Pin a hard, near-total conservation bound.
    assert len(missing) <= 1, f"table cell text lost on flatten: {missing[:10]}"


# --------------------------------------------------------------------------- #
# Required counter-proof 3: authored tables survive the render as real w:tbl   #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _pandoc_available(), reason="pandoc is unavailable in current runtime")
def test_raw_html_table_is_dropped_but_markdown_table_survives_render():
    raw_html_table = "<table>\n<tbody>\n<tr><td>A</td><td>B</td></tr>\n<tr><td>1</td><td>2</td></tr>\n</tbody>\n</table>"
    markdown_table = "|  |  |\n| --- | --- |\n| A | B |\n| 1 | 2 |"

    assert _count_word_tables(generation.convert_markdown_to_docx_bytes(raw_html_table)) == 0
    assert _count_word_tables(generation.convert_markdown_to_docx_bytes(markdown_table)) >= 1


@pytest.mark.skipif(not _pandoc_available(), reason="pandoc is unavailable in current runtime")
def test_authored_document_table_renders_as_real_word_table():
    document = Document()
    document.add_paragraph("Перед таблицей")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Колонка A"
    table.cell(0, 1).text = "Колонка B"
    table.cell(1, 0).text = "Значение 1"
    table.cell(1, 1).text = "Значение 2"
    document.add_paragraph("После таблицы")
    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)

    paragraphs, _ = extract_document_content_from_docx(buffer)
    assert [paragraph.role for paragraph in paragraphs] == ["body", "table", "body"]

    markdown = build_document_text(paragraphs)
    output = generation.convert_markdown_to_docx_bytes(markdown)

    assert _count_word_tables(output) >= 1
    output_text = _output_all_text(output)
    for value in ("Колонка A", "Колонка B", "Значение 1", "Значение 2"):
        assert value in output_text


@pytest.mark.skipif(not _pandoc_available(), reason="pandoc is unavailable in current runtime")
def test_mazzucato_authored_tables_survive_render_as_word_tables():
    paragraphs, _ = extract_document_content_from_docx(BytesIO(MAZZUCATO.read_bytes()))
    table_paragraphs = [paragraph for paragraph in paragraphs if paragraph.role == "table"]
    assert len(table_paragraphs) == 3

    markdown = build_document_text(paragraphs)
    output = generation.convert_markdown_to_docx_bytes(markdown)

    assert _count_word_tables(output) >= 3


@pytest.mark.skipif(not _pandoc_available(), reason="pandoc is unavailable in current runtime")
def test_resistance_scan_tables_do_not_render_word_tables():
    paragraphs, _ = extract_document_content_from_docx(BytesIO(RESISTANCE.read_bytes()))
    markdown = build_document_text(paragraphs)
    output = generation.convert_markdown_to_docx_bytes(markdown)

    assert _count_word_tables(output) == 0
