"""Spec 070 FR-006 (detector part): what a narration paragraph still carries that a listener should not hear.

Pure function, no pipeline, no network, no word list. Every class is a FORM by Unicode general
category (``unicodedata`` of the pinned Unicode version; see ``unicode_emoji_data``) or by a fixed
syntax; nothing here knows a word of any book (Constitution VII).

Occurrence counting (REVIEW №18, data-model §3.3): ``count`` is the number of OCCURRENCES, not of
paragraphs. A number counts once (a maximal run of digit characters), a symbol counts once per
character, a roman numeral / URL / tag-form counts once per token, ``all_caps`` is one condition per
paragraph (count 1).

The first six classes are repairable by the one repair call; ``html_left`` and ``emoji_left`` are a
check on the deterministic cleanup itself and are only reported.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from docxaicorrector.text.narration_cleanup import find_emoji_sequences, find_html_tags
from docxaicorrector.text.narration_forms import without_combining_marks, without_combining_marks_with_offsets

__all__ = [
    "REPAIRABLE_RESIDUE_CLASSES",
    "RESIDUE_CLASSES",
    "ResidueFinding",
    "detect_narration_residue",
    "is_all_caps_paragraph",
    "is_roman_numeral_form",
    "mask_url_or_domain",
]

RESIDUE_DIGITS = "digits"
RESIDUE_ROMAN_NUMERALS = "roman_numerals"
RESIDUE_SYMBOLS = "symbols"
RESIDUE_ALL_CAPS = "all_caps"
RESIDUE_URL_OR_DOMAIN = "url_or_domain"
RESIDUE_TAG_FORM = "tag_form"
RESIDUE_HTML_LEFT = "html_left"
RESIDUE_EMOJI_LEFT = "emoji_left"

RESIDUE_CLASSES: tuple[str, ...] = (
    RESIDUE_DIGITS,
    RESIDUE_ROMAN_NUMERALS,
    RESIDUE_SYMBOLS,
    RESIDUE_ALL_CAPS,
    RESIDUE_URL_OR_DOMAIN,
    RESIDUE_TAG_FORM,
    RESIDUE_HTML_LEFT,
    RESIDUE_EMOJI_LEFT,
)
REPAIRABLE_RESIDUE_CLASSES = frozenset(
    {
        RESIDUE_DIGITS,
        RESIDUE_ROMAN_NUMERALS,
        RESIDUE_SYMBOLS,
        RESIDUE_ALL_CAPS,
        RESIDUE_URL_OR_DOMAIN,
        RESIDUE_TAG_FORM,
    }
)

SAMPLE_MAX_CHARS = 120
_SAMPLE_LEAD_CHARS = 40
_ALL_CAPS_MIN_WORD_LETTERS = 4
_ALL_CAPS_MIN_WORDS = 2
_SIGN_CHARS = frozenset("%№§&")
_SUPERSCRIPT_SUBSCRIPT_DIGITS = frozenset("²³¹")
_LETTER_RUN = re.compile(r"[^\W\d_]+")
_ROMAN_RUN = "[IVXLCDM]{2,}"
_ROMAN_TOKEN = re.compile(rf"(?<![^\W\d_]){_ROMAN_RUN}(?![^\W\d_])")
_ROMAN_FORM = re.compile(_ROMAN_RUN)
_TAG_FORM = re.compile(r"\[[a-z]+(?: [a-z]+)?\]")
# Scheme or ``www.`` ... or ``label.label`` with no space, ending in >= 2 letters. The label before
# the last dot must start with a letter, so numbers (``3.14``) and one-letter abbreviation tails
# (``т.е.``) never match; an ellipsis is not a single dot between two letters.
_URL_OR_DOMAIN = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9+.-]*://\S+"
    r"|www\.\S+"
    r"|(?<![\w.])(?:[^\W\d_][\w-]*\.)+[^\W\d_]{2,}(?![\w]))",
)


@dataclass(frozen=True)
class ResidueFinding:
    residue_class: str
    count: int
    sample: str


def _is_digit_char(char: str) -> bool:
    if char in _SUPERSCRIPT_SUBSCRIPT_DIGITS:
        return True
    code = ord(char)
    if 0x2070 <= code <= 0x209F:
        return unicodedata.category(char) == "No"
    return unicodedata.category(char) == "Nd"


def _is_symbol_char(char: str) -> bool:
    return char in _SIGN_CHARS or unicodedata.category(char) in {"Sc", "Sm"}


def _is_roman_numeral_char(char: str) -> bool:
    return unicodedata.category(char) == "Nl"


def _sample(text: str, position: int) -> str:
    start = max(0, position - _SAMPLE_LEAD_CHARS)
    return text[start : start + SAMPLE_MAX_CHARS]


def _char_runs(text: str, predicate) -> list[int]:
    """Start positions of the maximal runs of characters satisfying ``predicate``."""

    starts: list[int] = []
    previous = False
    for index, char in enumerate(text):
        current = predicate(char)
        if current and not previous:
            starts.append(index)
        previous = current
    return starts


def _is_all_caps_paragraph(text: str) -> tuple[bool, int]:
    """``(is it, position of its first long word)``. The letters are read without stress marks
    (spec 073 FR-002); the position is a position of the original string."""

    stripped, offsets = without_combining_marks_with_offsets(text)
    letters = [char for char in stripped if char.isalpha()]
    cased = [char for char in letters if char.lower() != char.upper()]
    if not cased or not all(char.isupper() for char in cased):
        return False, -1
    long_words = [match for match in _LETTER_RUN.finditer(stripped) if len(match.group()) >= _ALL_CAPS_MIN_WORD_LETTERS]
    if len(long_words) < _ALL_CAPS_MIN_WORDS:
        return False, -1
    return True, offsets[long_words[0].start()]


def is_all_caps_paragraph(text: str) -> bool:
    """The form of the ``all_caps`` class: every cased letter is capital and there are at least two long words."""

    return _is_all_caps_paragraph(text)[0]


def is_roman_numeral_form(token: str) -> bool:
    """The form of the ``roman_numerals`` class for ONE token: at least two characters of ``[IVXLCDM]`` and
    nothing else, or only characters of category Nl (``Ⅳ``). Stress marks are not read."""

    stripped = without_combining_marks(token)
    if not stripped:
        return False
    return _ROMAN_FORM.fullmatch(stripped) is not None or all(_is_roman_numeral_char(char) for char in stripped)


def mask_url_or_domain(text: str) -> str:
    """``text`` with every address (scheme, ``www.`` or ``label.label``) replaced by spaces of the same length,
    so the length of the string and the positions of everything else are kept."""

    return _URL_OR_DOMAIN.sub(lambda match: " " * len(match.group()), text)


def detect_narration_residue(text: str) -> tuple[ResidueFinding, ...]:
    """The residue classes present in ``text`` (empty tuple = clean), in the fixed class order."""

    findings: list[ResidueFinding] = []

    digit_starts = _char_runs(text, _is_digit_char)
    if digit_starts:
        findings.append(ResidueFinding(RESIDUE_DIGITS, len(digit_starts), _sample(text, digit_starts[0])))

    # Spec 073 FR-002: a roman numeral is read without stress marks; positions are the original string's.
    stripped, offsets = without_combining_marks_with_offsets(text)
    roman_positions = [offsets[match.start()] for match in _ROMAN_TOKEN.finditer(stripped)]
    roman_positions += [offsets[position] for position in _char_runs(stripped, _is_roman_numeral_char)]
    if roman_positions:
        roman_positions.sort()
        findings.append(ResidueFinding(RESIDUE_ROMAN_NUMERALS, len(roman_positions), _sample(text, roman_positions[0])))

    symbol_positions = [index for index, char in enumerate(text) if _is_symbol_char(char)]
    if symbol_positions:
        findings.append(ResidueFinding(RESIDUE_SYMBOLS, len(symbol_positions), _sample(text, symbol_positions[0])))

    all_caps, caps_position = _is_all_caps_paragraph(text)
    if all_caps:
        findings.append(ResidueFinding(RESIDUE_ALL_CAPS, 1, _sample(text, caps_position)))

    url_positions = [match.start() for match in _URL_OR_DOMAIN.finditer(text)]
    if url_positions:
        findings.append(ResidueFinding(RESIDUE_URL_OR_DOMAIN, len(url_positions), _sample(text, url_positions[0])))

    tag_positions = [match.start() for match in _TAG_FORM.finditer(text)]
    if tag_positions:
        findings.append(ResidueFinding(RESIDUE_TAG_FORM, len(tag_positions), _sample(text, tag_positions[0])))

    html_spans = find_html_tags(text)
    if html_spans:
        findings.append(ResidueFinding(RESIDUE_HTML_LEFT, len(html_spans), _sample(text, html_spans[0][0])))

    emoji_spans = find_emoji_sequences(text)
    if emoji_spans:
        findings.append(ResidueFinding(RESIDUE_EMOJI_LEFT, len(emoji_spans), _sample(text, emoji_spans[0][0])))

    return tuple(findings)
