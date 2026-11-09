"""Spec 070 FR-005: deterministic narration cleanup, and the UTS #51 emoji scanner (research R1, R8).

Pure functions over one paragraph of text: no pipeline, no Streamlit, no network, no word list.
Only what is unambiguous is removed by code; everything else (digits, ``%``, ``№``, ``§``, ``&``,
URLs, bracketed text) is left for the model to rewrite and for the residue detector
(``narration_residue``) to report. Square-bracket text is never removed, except the pipeline's own
``[[DOCX_<KIND>_...]]`` tokens (decision О-9).

What is removed, in order:

1. pipeline tokens ``[[DOCX_<KIND>_...]]``;
2. HTML by TAG SYNTAX (element name, no attributes or ``name=value`` attributes only), keeping the
   content; only known inline formatting elements vanish without a trace; every other element (``<br>``, blocks, unknown) becomes a space so words never weld; entities that end in ``;``
   are expanded. A lone ``<`` that is not followed by an element name (``a < b``) is not a tag;
3. emoji, as whole sequences by the Unicode Emoji properties pinned in ``unicode_emoji_data``;
4. Markdown the model returned against its prompt: heading, quote and bullet prefixes, a decoration
   glyph at the start of a line, emphasis, backticks, ``[text](url)`` links. A numbered-list marker
   (``1990. ...``) is NOT touched: a year must survive, and numbers are rewritten by the model;
5. whitespace is collapsed.

Documented decisions where the rule text leaves room:

* A lone ``Emoji_Modifier`` or ``Regional_Indicator`` is an ``Emoji_Component`` and stays (the spec:
  components are not removed globally); the same holds for ASCII digits, ``#`` and ``*``, which
  are removed only inside a keycap sequence, and an ASCII digit followed by ``U+FE0F`` alone is
  not an emoji sequence (it would delete a digit from prose).
* ``№`` is never treated as a line-start decoration glyph although its category is ``So``: it is a
  sign with meaning, and ``narration_residue`` reports it.
* The cleanup runs to a fixed point (a removal can expose a new prefix), so it is idempotent.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass

from docxaicorrector.text.unicode_emoji_data import (
    EMOJI,
    EMOJI_COMPONENT,
    EMOJI_MODIFIER,
    EMOJI_MODIFIER_BASE,
    EMOJI_PRESENTATION,
    EXTENDED_PICTOGRAPHIC,
)

__all__ = [
    "CleanupResult",
    "CleanupStats",
    "HTML_TAG_PATTERN",
    "clean_narration_paragraph",
    "find_emoji_sequences",
    "find_html_tags",
]


@dataclass(frozen=True)
class CleanupStats:
    internal_token_count: int = 0
    html_tag_count: int = 0
    html_entity_count: int = 0
    emoji_sequence_count: int = 0
    decoration_marker_count: int = 0
    markdown_syntax_count: int = 0

    def __add__(self, other: "CleanupStats") -> "CleanupStats":
        return CleanupStats(
            self.internal_token_count + other.internal_token_count,
            self.html_tag_count + other.html_tag_count,
            self.html_entity_count + other.html_entity_count,
            self.emoji_sequence_count + other.emoji_sequence_count,
            self.decoration_marker_count + other.decoration_marker_count,
            self.markdown_syntax_count + other.markdown_syntax_count,
        )


@dataclass(frozen=True)
class CleanupResult:
    text: str
    stats: CleanupStats


# ---------------------------------------------------------------------------------------------
# Emoji scanner (UTS #51 ED-14..ED-17, research R1)
# ---------------------------------------------------------------------------------------------


def _expand(ranges: tuple[tuple[int, int], ...]) -> frozenset[int]:
    return frozenset(cp for start, end in ranges for cp in range(start, end + 1))


_EMOJI = _expand(EMOJI)
_EMOJI_PRESENTATION = _expand(EMOJI_PRESENTATION)
_EMOJI_MODIFIER = _expand(EMOJI_MODIFIER)
_EMOJI_MODIFIER_BASE = _expand(EMOJI_MODIFIER_BASE)
_EMOJI_COMPONENT = _expand(EMOJI_COMPONENT)
_EXTENDED_PICTOGRAPHIC = _expand(EXTENDED_PICTOGRAPHIC)

_ZWJ = 0x200D
_VS16 = 0xFE0F
_KEYCAP = 0x20E3
_TAG_FIRST = 0xE0020
_TAG_LAST = 0xE007F  # the cancel tag closes a tag sequence
_REGIONAL_INDICATORS = frozenset(range(0x1F1E6, 0x1F1FF + 1))
_KEYCAP_BASES = frozenset("0123456789#*")


def _skip_tags(text: str, index: int) -> int:
    while index < len(text) and _TAG_FIRST <= ord(text[index]) <= _TAG_LAST:
        index += 1
    return index


def _element_end(text: str, index: int) -> int | None:
    """End of the emoji element that starts at ``index``, or ``None`` when none starts there."""

    length = len(text)
    char = text[index]
    code = ord(char)
    if code in _REGIONAL_INDICATORS:
        if index + 1 < length and ord(text[index + 1]) in _REGIONAL_INDICATORS:
            return index + 2  # a flag
        return None
    if char in _KEYCAP_BASES:
        end = index + 1
        if end < length and ord(text[end]) == _VS16:
            end += 1
        if end < length and ord(text[end]) == _KEYCAP:
            return end + 1
        return None
    if code in _EMOJI_MODIFIER_BASE and index + 1 < length and ord(text[index + 1]) in _EMOJI_MODIFIER:
        return index + 2
    next_is_vs16 = index + 1 < length and ord(text[index + 1]) == _VS16
    if next_is_vs16 and code in _EMOJI:
        return _skip_tags(text, index + 2)
    if code in _EMOJI_PRESENTATION and code not in _EMOJI_COMPONENT:
        return _skip_tags(text, index + 2 if next_is_vs16 else index + 1)
    return None


def _sequence_end(text: str, index: int) -> int | None:
    """End of the emoji sequence (element or ZWJ chain) that starts at ``index``."""

    length = len(text)
    end = _element_end(text, index)
    lone_pictographic = False
    if end is None:
        if ord(text[index]) not in _EXTENDED_PICTOGRAPHIC:
            return None
        end = index + 1
        lone_pictographic = True
    chained = False
    while end + 1 < length and ord(text[end]) == _ZWJ:
        following = _element_end(text, end + 1)
        if following is None:
            if ord(text[end + 1]) not in _EXTENDED_PICTOGRAPHIC:
                break
            following = end + 2
            if following < length and ord(text[following]) == _VS16:
                following += 1
        end = following
        chained = True
    if chained:
        return end
    return None if lone_pictographic else end


def find_emoji_sequences(text: str) -> list[tuple[int, int]]:
    """Non-overlapping ``(start, end)`` spans of the emoji sequences in ``text``."""

    spans: list[tuple[int, int]] = []
    index = 0
    length = len(text)
    while index < length:
        end = _sequence_end(text, index)
        if end is None:
            index += 1
            continue
        spans.append((index, end))
        index = end
    return spans


# ---------------------------------------------------------------------------------------------
# HTML (research R8, step 2)
# ---------------------------------------------------------------------------------------------

_ATTRIBUTE = r"""\s+[A-Za-z_:][-A-Za-z0-9_:.]*\s*=\s*(?:"[^"<>]*"|'[^'<>]*'|[^\s"'<>=`]+)"""
# A tag is ``<name>``, ``</name>``, ``<name/>`` or ``<name attr="v" ...>``. A valueless "attribute"
# is deliberately not accepted: ``a<b and c>d`` is prose, not a tag.
HTML_TAG_PATTERN = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9-]*)((?:" + _ATTRIBUTE + r")*)\s*(/?)>")
_HTML_ENTITY_PATTERN = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
# HTML vocabulary (WHATWG "text-level semantics" plus the legacy formatting elements): only these
# are removed without a separator, because they can sit INSIDE a word (``сло<b>во</b>``). ANY other
# element - a known block (``hr``, ``section``, ``article``) or an unknown one - is a word
# separator, so the rule needs no list of block tags and cannot weld words on a tag it did not know.
_HTML_INLINE_TAGS = frozenset(
    {
        "a", "abbr", "acronym", "b", "bdi", "bdo", "big", "cite", "code", "data", "del", "dfn", "em",
        "font", "i", "ins", "kbd", "mark", "q", "s", "samp", "small", "span", "strike", "strong",
        "sub", "sup", "time", "tt", "u", "var",
    }
)
_INTERNAL_TOKEN_PATTERN = re.compile(r"\[\[DOCX_[A-Za-z0-9_]+\]\]")


def find_html_tags(text: str) -> list[tuple[int, int]]:
    """Spans of HTML tags by tag syntax (what the cleanup removes, and what the detector looks for)."""

    return [match.span() for match in HTML_TAG_PATTERN.finditer(text)]


_CLOSING_PUNCTUATION = ".,;:!?…)]}»”’\"'"


def _splice(text: str, spans: list[tuple[int, int]], *, replacement: str = "") -> str:
    """Remove ``spans`` from ``text``; keep words apart where the removal would weld them."""

    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(text[cursor:start])
        cursor = end
        left = "".join(pieces)
        right = text[end:]
        if replacement:
            pieces.append(replacement)
        elif not right or right[0] in _CLOSING_PUNCTUATION:
            pieces[:] = [left.rstrip(" \t")]
        elif left and not left[-1].isspace() and not right[0].isspace():
            pieces.append(" ")
    pieces.append(text[cursor:])
    return "".join(pieces)


def _strip_html(text: str) -> tuple[str, int, int]:
    tag_count = 0
    entity_count = 0

    def replace_tag(match: re.Match[str]) -> str:
        nonlocal tag_count
        tag_count += 1
        return "" if match.group(2).lower() in _HTML_INLINE_TAGS else " "

    def replace_entity(match: re.Match[str]) -> str:
        nonlocal entity_count
        expanded = html.unescape(match.group(0))
        if expanded != match.group(0):
            entity_count += 1
        return expanded

    for _ in range(4):  # an escaped tag (``&lt;b&gt;``) becomes a tag after expansion: strip it as well
        before = text
        text = HTML_TAG_PATTERN.sub(replace_tag, text)
        text = _HTML_ENTITY_PATTERN.sub(replace_entity, text)
        if text == before:
            break
    return text, tag_count, entity_count


# ---------------------------------------------------------------------------------------------
# Markdown and decoration (research R8, step 4)
# ---------------------------------------------------------------------------------------------

_HEADING_PREFIX = re.compile(r"^\s{0,3}#{1,6}(?:\s+|$)")
_QUOTE_PREFIX = re.compile(r"^\s{0,3}>\s?")
_LIST_PREFIX = re.compile(r"^\s{0,3}[-*+]\s+")
_BULLET_GLYPH_PREFIX = re.compile(r"^\s{0,3}[●•◦‣]\s+")
_GLYPH_PREFIX = re.compile(r"^\s{0,3}(\S+)\s+")  # a whole token made only of decoration glyphs
_LINK_PATTERN = re.compile(r"!?\[([^\]\n]+)\]\(([^)\n]+)\)")
_STRONG_STAR = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_STRONG_UNDERSCORE = re.compile(r"(?<![\w_])__(?=\S)(.+?)(?<=\S)__(?![\w_])")
_EMPHASIS_STAR = re.compile(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])")
_EMPHASIS_UNDERSCORE = re.compile(r"(?<![\w_])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])")
_INLINE_SPACE = re.compile(r"[ \t ]+")


def _is_decoration_glyph(char: str) -> bool:
    return char != "№" and unicodedata.category(char) in {"So", "Sm"}


def _strip_line_prefixes(line: str) -> tuple[str, int, int]:
    markdown_count = 0
    decoration_count = 0
    while True:
        if (match := _HEADING_PREFIX.match(line)) or (match := _QUOTE_PREFIX.match(line)) or (
            match := _LIST_PREFIX.match(line)
        ):
            markdown_count += 1
        elif match := _BULLET_GLYPH_PREFIX.match(line):
            decoration_count += 1
        elif (match := _GLYPH_PREFIX.match(line)) and all(_is_decoration_glyph(char) for char in match.group(1)):
            decoration_count += 1
        else:
            return line, markdown_count, decoration_count
        line = line[match.end() :]


def _strip_inline_markdown(line: str) -> tuple[str, int]:
    count = 0
    line, links = _LINK_PATTERN.subn(r"\1", line)
    count += links
    if "`" in line:
        count += line.count("`")
        line = line.replace("`", "")
    while True:
        before = line
        for pattern in (_STRONG_STAR, _STRONG_UNDERSCORE, _EMPHASIS_STAR, _EMPHASIS_UNDERSCORE):
            line, replaced = pattern.subn(r"\1", line)
            count += replaced
        if line == before:
            return line, count


# ---------------------------------------------------------------------------------------------
# The cleanup
# ---------------------------------------------------------------------------------------------


def _clean_once(text: str) -> tuple[str, CleanupStats]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    token_spans = [match.span() for match in _INTERNAL_TOKEN_PATTERN.finditer(text)]
    text = _splice(text, token_spans)

    text, tag_count, entity_count = _strip_html(text)

    emoji_spans = find_emoji_sequences(text)
    text = _splice(text, emoji_spans)

    markdown_count = 0
    decoration_count = 0
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line, line_markdown, line_decoration = _strip_line_prefixes(raw_line)
        line, inline_markdown = _strip_inline_markdown(line)
        markdown_count += line_markdown + inline_markdown
        decoration_count += line_decoration
        line = _INLINE_SPACE.sub(" ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines), CleanupStats(
        internal_token_count=len(token_spans),
        html_tag_count=tag_count,
        html_entity_count=entity_count,
        emoji_sequence_count=len(emoji_spans),
        decoration_marker_count=decoration_count,
        markdown_syntax_count=markdown_count,
    )


def clean_narration_paragraph(text: str) -> CleanupResult:
    """Clean one narration paragraph. Pure and idempotent (run to a fixed point)."""

    stats = CleanupStats()
    current = text
    for _ in range(8):
        cleaned, pass_stats = _clean_once(current)
        stats = stats + pass_stats
        if cleaned == current:
            break
        current = cleaned
    return CleanupResult(text=current, stats=stats)
