"""Narration text as a DOCX (spec 072, FR-004).

Writes the paragraphs of a narration document plan into a minimal python-docx
document, verbatim: each paragraph is ONE run holding the exact string (python-docx
turns a single ``\n`` into ``<w:br/>``), nothing is parsed as Markdown, nothing is
cleaned. The document has only the ``Normal`` and ``Heading 1`` styles, both with an
explicit Times New Roman (so Word and LibreOffice pick a Cyrillic-capable face), and
no headers, footers, table of contents, images or tables.

The module knows nothing about the pipeline: its input is any sequence of objects with
``style`` and ``text``. Characters that are invalid in XML make python-docx raise
``ValueError``; the renderer lets it propagate (the caller decides what a failed build
means).
"""

from __future__ import annotations

import io
from typing import Protocol, Sequence

import docx
from docx.oxml.ns import qn

NARRATION_DOCX_STYLE_HEADING_1 = "Heading 1"
NARRATION_DOCX_STYLE_NORMAL = "Normal"
NARRATION_DOCX_FONT_NAME = "Times New Roman"

_ALLOWED_STYLES = frozenset({NARRATION_DOCX_STYLE_HEADING_1, NARRATION_DOCX_STYLE_NORMAL})
_FONT_SLOTS = ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia")
_THEME_FONT_ATTRIBUTES = ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme")


class NarrationDocumentParagraphLike(Protocol):
    """One paragraph to write: a style name and the exact text."""

    @property
    def style(self) -> str: ...

    @property
    def text(self) -> str: ...


def _apply_explicit_font(style) -> None:
    """Pin ``NARRATION_DOCX_FONT_NAME`` in every ``w:rFonts`` slot and drop theme links."""
    style.font.name = NARRATION_DOCX_FONT_NAME  # creates w:rPr/w:rFonts, sets ascii + hAnsi
    rfonts = style.element.rPr.rFonts
    for slot in _FONT_SLOTS:
        rfonts.set(qn(slot), NARRATION_DOCX_FONT_NAME)
    for attribute in _THEME_FONT_ATTRIBUTES:
        key = qn(attribute)
        if key in rfonts.attrib:
            del rfonts.attrib[key]


def render_narration_docx(
    paragraphs: Sequence[NarrationDocumentParagraphLike],
    *,
    title: str,
) -> bytes:
    """Return the bytes of a DOCX holding ``paragraphs`` verbatim.

    Raises ``ValueError`` for a style other than ``Normal`` / ``Heading 1`` and for text
    python-docx rejects (XML-incompatible control characters).
    """
    for paragraph in paragraphs:
        if paragraph.style not in _ALLOWED_STYLES:
            raise ValueError(f"unsupported narration paragraph style: {paragraph.style!r}")

    document = docx.Document()
    for style_name in (NARRATION_DOCX_STYLE_NORMAL, NARRATION_DOCX_STYLE_HEADING_1):
        _apply_explicit_font(document.styles[style_name])

    for paragraph in paragraphs:
        document.add_paragraph(style=paragraph.style).add_run(paragraph.text)

    properties = document.core_properties
    properties.title = title
    properties.author = ""
    properties.comments = ""
    properties.last_modified_by = ""

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
