"""Spec 072 WP-C (FR-004): the narration DOCX renderer.

Fictional paragraphs only (Constitution VII). The renderer receives (style, text)
pairs and must write them verbatim: no Markdown parsing, no headers/footers, no
table of contents, no images, explicit Times New Roman, clean document properties.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as etree
import zipfile
import xml.etree.ElementTree as etree
from dataclasses import dataclass

import docx
import pytest


from docxaicorrector.generation.narration_docx import render_narration_docx

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_FONT_SLOTS = ("ascii", "hAnsi", "cs", "eastAsia")


@dataclass(frozen=True)
class _Paragraph:
    style: str
    text: str


def _normal(text: str) -> _Paragraph:
    return _Paragraph("Normal", text)


def _heading(text: str) -> _Paragraph:
    return _Paragraph("Heading 1", text)


_LITERAL_TEXTS = (
    "Абзац со *звёздами* и _чертой_ внутри строки.",
    "# решётка в начале не заголовок",
    "<угол> и <b>тег</b> остаются текстом",
    "> знак цитаты в начале",
    "— тире в начале строки",
    "за\u0301мок с ударением",
    "замОк с заглавной гласной",
    "Ёлка и ёж",
    "первая строка\nвторая строка",
)


def _render(paragraphs, title: str = "Вымышленная книга") -> bytes:
    return render_narration_docx(paragraphs, title=title)


def _open(data: bytes):
    return docx.Document(io.BytesIO(data))


def _zip_names(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.namelist()


def _zip_text(data: bytes, name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(name).decode("utf-8")


# --- T-C1: verbatim -----------------------------------------------------------


def test_paragraph_text_is_byte_identical_to_input() -> None:
    plan = [_heading("Глава первая")] + [_normal(text) for text in _LITERAL_TEXTS]
    document = _open(_render(plan))
    assert [p.text for p in document.paragraphs] == [p.text for p in plan]


def test_single_newline_becomes_line_break_element() -> None:
    document_xml = _zip_text(_render([_normal("первая\nвторая")]), "word/document.xml")
    assert "<w:br/>" in document_xml
    assert "первая" in document_xml and "вторая" in document_xml


def test_combining_acute_and_capital_vowel_survive_in_xml() -> None:
    document_xml = _zip_text(_render([_normal("за\u0301мок замОк")]), "word/document.xml")
    assert "за\u0301мок замОк" in document_xml


def test_markup_characters_are_not_interpreted() -> None:
    plan = [_normal("# не *заголовок* _курсив_ <тег> > цитата\n— тире")]
    document = _open(_render(plan))
    assert document.paragraphs[0].text == plan[0].text
    assert document.paragraphs[0].style is not None
    assert document.paragraphs[0].style.name == "Normal"
    assert len(document.paragraphs[0].runs) == 1


# --- T-C2: styles -------------------------------------------------------------


def test_only_heading_1_and_normal_styles_are_used() -> None:
    plan = [_heading("А"), _normal("б"), _heading("В"), _normal("г")]
    document = _open(_render(plan))
    used = [p.style.name for p in document.paragraphs if p.style is not None]
    assert used == ["Heading 1", "Normal", "Heading 1", "Normal"]


def _style_rfonts(data: bytes, style_name: str) -> dict[str, str]:
    root = etree.fromstring(_zip_text(data, "word/styles.xml"))
    for style in root.findall(f"{{{W_NS}}}style"):
        name = style.find(f"{{{W_NS}}}name")
        if name is not None and (name.get(f"{{{W_NS}}}val") or "").casefold() == style_name.casefold():
            rfonts = style.find(f"{{{W_NS}}}rPr/{{{W_NS}}}rFonts")
            assert rfonts is not None, f"style {style_name} has no w:rFonts"
            return {key.rsplit("}", 1)[-1]: value for key, value in rfonts.attrib.items()}
    raise AssertionError(f"style {style_name} not found")


@pytest.mark.parametrize("style_name", ["Normal", "Heading 1"])
def test_styles_use_times_new_roman_in_every_slot_without_theme(style_name: str) -> None:
    attributes = _style_rfonts(_render([_normal("а"), _heading("б")]), style_name)
    for slot in _FONT_SLOTS:
        assert attributes.get(slot) == "Times New Roman", (style_name, slot, attributes)
    assert not [key for key in attributes if key.endswith("Theme")], attributes


def test_unsupported_style_is_rejected() -> None:
    with pytest.raises(ValueError):
        _render([_Paragraph("Heading 2", "текст")])


# --- T-C3: structure ----------------------------------------------------------


def test_paragraph_count_equals_input_and_no_empty_paragraphs() -> None:
    plan = [_heading("Глава")] + [_normal(f"Абзац номер {number}") for number in range(7)]
    document = _open(_render(plan))
    assert len(document.paragraphs) == len(plan)
    assert all(p.text for p in document.paragraphs)


def test_package_has_no_headers_footers_toc_images_or_tables() -> None:
    data = _render([_heading("Глава"), _normal("Текст"), _normal("Ещё текст")])
    names = _zip_names(data)
    assert not [n for n in names if n.startswith("word/header") or n.startswith("word/footer")], names
    assert not [n for n in names if n.startswith("word/media/")], names
    document_xml = _zip_text(data, "word/document.xml")
    for forbidden in ("<w:fldSimple", "<w:instrText", "<w:tbl>", "<w:tbl ", "<w:drawing", "<w:pict"):
        assert forbidden not in document_xml, forbidden
    assert "<w:headerReference" not in document_xml
    assert "<w:footerReference" not in document_xml


# --- T-C4: properties ---------------------------------------------------------


def test_core_properties_carry_title_and_no_generator_traces() -> None:
    data = _render([_normal("Текст")], title="Вымышленное название")
    properties = _open(data).core_properties
    assert properties.title == "Вымышленное название"
    assert properties.author == ""
    assert properties.comments == ""
    core_xml = _zip_text(data, "docProps/core.xml")
    assert "python-docx" not in core_xml


# --- T-C5: invalid XML characters ---------------------------------------------


def test_xml_incompatible_character_propagates() -> None:
    with pytest.raises(ValueError):
        _render([_normal("a\x0bb")])
