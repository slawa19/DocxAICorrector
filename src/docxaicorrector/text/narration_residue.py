"""Spec 070 FR-006 (detector part): what a narration paragraph still carries that a listener should not hear.

Pure function, no pipeline, no network, no word list. Every class is a FORM by Unicode general
category (``unicodedata`` of the pinned Unicode version; see ``unicode_emoji_data``) or by a fixed
syntax; nothing here knows a word of any book (Constitution VII).

Occurrence counting (REVIEW №18, data-model §3.3): ``count`` is the number of OCCURRENCES, not of
paragraphs. A number counts once (a maximal run of digit characters), a symbol counts once per
character, a roman numeral / URL / tag-form counts once per token, ``all_caps`` is one condition per
paragraph (count 1), a ``latin`` unit is one series of letters (spec 073 FR-003) that holds at least
one Latin letter, outside an address and not a roman numeral.

The first seven classes (up to and including ``latin``) are repairable by the one repair call;
``html_left`` and ``emoji_left`` are a check on the deterministic cleanup itself and are only reported.

The address form (spec 074 FR-302, FR-401) lives here too, because every reader of an address uses it: the
mask of the reading glossary and of ``latin``, the ``url_or_domain`` class, and the audiobook source, where
``shorten_addresses_to_domain`` replaces each web address by its domain (FR-405).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from docxaicorrector.text.narration_cleanup import find_emoji_sequences, find_html_tags
from docxaicorrector.text.narration_forms import (
    LetterSeries,
    is_latin_letter,
    letter_series,
    without_combining_marks,
    without_combining_marks_with_offsets,
)

__all__ = [
    "REPAIRABLE_RESIDUE_CLASSES",
    "RESIDUE_CLASSES",
    "AddressToken",
    "ResidueFinding",
    "address_tokens",
    "detect_narration_residue",
    "is_all_caps_paragraph",
    "is_roman_numeral_form",
    "latin_units",
    "mask_url_or_domain",
    "shorten_addresses_to_domain",
]

RESIDUE_DIGITS = "digits"
RESIDUE_ROMAN_NUMERALS = "roman_numerals"
RESIDUE_SYMBOLS = "symbols"
RESIDUE_ALL_CAPS = "all_caps"
RESIDUE_URL_OR_DOMAIN = "url_or_domain"
RESIDUE_TAG_FORM = "tag_form"
RESIDUE_LATIN = "latin"
RESIDUE_HTML_LEFT = "html_left"
RESIDUE_EMOJI_LEFT = "emoji_left"

RESIDUE_CLASSES: tuple[str, ...] = (
    RESIDUE_DIGITS,
    RESIDUE_ROMAN_NUMERALS,
    RESIDUE_SYMBOLS,
    RESIDUE_ALL_CAPS,
    RESIDUE_URL_OR_DOMAIN,
    RESIDUE_TAG_FORM,
    RESIDUE_LATIN,
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
        RESIDUE_LATIN,
    }
)

SAMPLE_MAX_CHARS = 120
_SAMPLE_LEAD_CHARS = 40
_ALL_CAPS_MIN_WORD_LETTERS = 4
_ALL_CAPS_MIN_WORDS = 2
# Spec 074 FR-403: "/" and "\" have no reading either; left in a narration they are a symbol to repair.
_SIGN_CHARS = frozenset("%№§&/\\")
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
# Spec 074 FR-302 / FR-401: what can close a token after its address and is not part of it -- the markup the
# import writes (emphasis delimiters, ``<u>``/``<sup>``/``<sub>`` tags), brackets and quotes, sentence
# punctuation, and a note: a run of characters of category No (``¹²``) or a ``<sup>`` element.
_ADDRESS_EDGE_MARKS = frozenset("*_<>()[]«»\"'“”‘’„")
_ADDRESS_TRAILING_PUNCTUATION = frozenset(".,;:!?")
_ADDRESS_CLOSERS = {")": "(", "]": "["}
_TRAILING_NOTE_ELEMENT = re.compile(r"<sup>[^<>]*</sup>$")
_TRAILING_TAG = re.compile(r"</?[A-Za-z]+>$")
# FR-401: the host ends where the path, the query, the fragment or the port begins.
_HOST_END = re.compile(r"[/?#:]")
_SCHEME_SEPARATOR = "://"
_WWW_PREFIX = "www."


@dataclass(frozen=True)
class ResidueFinding:
    residue_class: str
    count: int
    sample: str


@dataclass(frozen=True)
class AddressToken:
    """Spec 074 FR-401: one address -- the whole token around an address match (scheme, ``www.``, domain, path,
    query; the local part of an e-mail), without the import's markup, the trailing punctuation and a note.
    ``start``/``end`` are positions of the original string."""

    start: int
    end: int
    text: str

    @property
    def domain(self) -> str | None:
        """The host without the scheme and a leading ``www.``; ``None`` for an e-mail, which is not a web
        address in the sense of FR-401."""

        if "@" in self.text:
            return None
        before, separator, after = self.text.partition(_SCHEME_SEPARATOR)
        host = _HOST_END.split(after if separator else before, maxsplit=1)[0]
        if host[: len(_WWW_PREFIX)].lower() == _WWW_PREFIX:
            host = host[len(_WWW_PREFIX) :]
        return host or None


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


def _trim_address_end(text: str, start: int, end: int) -> int:
    """The end of ``text[start:end]`` without what closes a token and is not an address (FR-302 (b)): the
    import's tags and a ``<sup>`` note, a run of No characters with the punctuation in front of it, trailing
    punctuation, markup, quotes and unbalanced closing brackets."""

    while end > start:
        segment = text[start:end]
        tag = _TRAILING_NOTE_ELEMENT.search(segment) or _TRAILING_TAG.search(segment)
        if tag is not None:
            end = start + tag.start()
            continue
        char = text[end - 1]
        opener = _ADDRESS_CLOSERS.get(char)
        if opener is not None and segment.count(opener) >= segment.count(char):
            break
        if (
            unicodedata.category(char) == "No"
            or char in _ADDRESS_EDGE_MARKS
            or char in _ADDRESS_TRAILING_PUNCTUATION
        ):
            end -= 1
            continue
        break
    return end


def _is_letter_label(label: str) -> bool:
    return len(label) >= 2 and all(unicodedata.category(char).startswith("L") for char in label)


def _address_spans(text: str) -> list[tuple[int, int]]:
    """Spec 074 FR-302: the addresses of ``text`` as ``(start, end)``. A note after an address is cut off the
    match; a match without a scheme and without ``www.`` is an address only when its last label is letters
    (category L), so a word before a note ("слово.¹⁵") is never one."""

    spans: list[tuple[int, int]] = []
    for match in _URL_OR_DOMAIN.finditer(text):
        start = match.start()
        end = _trim_address_end(text, start, match.end())
        candidate = text[start:end]
        if not candidate:
            continue
        if _SCHEME_SEPARATOR not in candidate and candidate[: len(_WWW_PREFIX)].lower() != _WWW_PREFIX:
            if "." not in candidate or not _is_letter_label(candidate.rpartition(".")[2]):
                continue
        spans.append((start, end))
    return spans


def mask_url_or_domain(text: str) -> str:
    """``text`` with every address (scheme, ``www.`` or ``label.label``; spec 074 FR-302 form) replaced by
    spaces of the same length, so the length of the string and the positions of everything else are kept."""

    spans = _address_spans(text)
    if not spans:
        return text
    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(text[cursor:start])
        pieces.append(" " * (end - start))
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def address_tokens(text: str) -> tuple[AddressToken, ...]:
    """Spec 074 FR-401: the addresses of ``text`` as whole tokens, in order, one per token.

    A token is the run of non-space characters around an address match. It begins at its first match -- or,
    for an e-mail, at the local part in front of ``@`` -- so markup and brackets before the address are not in
    it, and it ends before the markup, punctuation and note that close it (``_trim_address_end``)."""

    first_match_by_token: dict[int, int] = {}
    token_end_by_start: dict[int, int] = {}
    for start, end in _address_spans(text):
        token_start = start
        while token_start > 0 and not text[token_start - 1].isspace():
            token_start -= 1
        token_end = end
        while token_end < len(text) and not text[token_end].isspace():
            token_end += 1
        first_match_by_token[token_start] = min(start, first_match_by_token.get(token_start, start))
        token_end_by_start[token_start] = token_end
    tokens: list[AddressToken] = []
    for token_start in sorted(first_match_by_token):
        core_start = first_match_by_token[token_start]
        if core_start > token_start and text[core_start - 1] == "@":
            while core_start > token_start and text[core_start - 1] not in _ADDRESS_EDGE_MARKS:
                core_start -= 1
        core_end = _trim_address_end(text, core_start, token_end_by_start[token_start])
        if core_end > core_start:
            tokens.append(AddressToken(start=core_start, end=core_end, text=text[core_start:core_end]))
    return tuple(tokens)


def shorten_addresses_to_domain(text: str) -> str:
    """Spec 074 FR-405: ``text`` with every web address (FR-401) replaced by its domain -- the scheme, a leading
    ``www.``, the path, the query and the fragment are dropped; the markup, punctuation and note around the
    address stay. An e-mail and an address that is already its bare domain are left as they are."""

    pieces: list[str] = []
    cursor = 0
    for token in address_tokens(text):
        domain = token.domain
        if domain is None or domain == token.text:
            continue
        pieces.append(text[cursor : token.start])
        pieces.append(domain)
        cursor = token.end
    if not pieces:
        return text
    pieces.append(text[cursor:])
    return "".join(pieces)


def latin_units(text: str) -> tuple[LetterSeries, ...]:
    """The units of the ``latin`` class: series of letters (stress marks, hyphens and apostrophes inside)
    that hold at least one Latin letter. Addresses are masked first (same length, so positions are the
    original string's) and a series that is wholly a roman numeral form is not Latin."""

    masked = mask_url_or_domain(text)
    return tuple(
        unit
        for unit in letter_series(masked, digits_inside=False)
        if any(is_latin_letter(char) for char in unit.text) and not is_roman_numeral_form(unit.text)
    )


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

    url_positions = [start for start, _ in _address_spans(text)]
    if url_positions:
        findings.append(ResidueFinding(RESIDUE_URL_OR_DOMAIN, len(url_positions), _sample(text, url_positions[0])))

    tag_positions = [match.start() for match in _TAG_FORM.finditer(text)]
    if tag_positions:
        findings.append(ResidueFinding(RESIDUE_TAG_FORM, len(tag_positions), _sample(text, tag_positions[0])))

    latin = latin_units(text)
    if latin:
        findings.append(ResidueFinding(RESIDUE_LATIN, len(latin), _sample(text, latin[0].start)))

    html_spans = find_html_tags(text)
    if html_spans:
        findings.append(ResidueFinding(RESIDUE_HTML_LEFT, len(html_spans), _sample(text, html_spans[0][0])))

    emoji_spans = find_emoji_sequences(text)
    if emoji_spans:
        findings.append(ResidueFinding(RESIDUE_EMOJI_LEFT, len(emoji_spans), _sample(text, emoji_spans[0][0])))

    return tuple(findings)
