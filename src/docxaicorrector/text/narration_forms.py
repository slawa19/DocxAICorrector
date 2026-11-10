"""Spec 073 FR-002: the forms of text that every LEXICAL comparison of the narration pass reads.

A stress mark (an acute accent after the stressed vowel, FR-001) is a combining mark: Unicode category
M*. It belongs to its letter, so a comparison of WORDS -- the coverage signal, the residue classes
``all_caps`` and ``roman_numerals``, the fragment rule, the context-leakage check -- must not see it, while
the exact assembly of the narration text (byte-exact, by id) must keep it.

This module is a leaf: it imports only the standard library, so the document layer, the text layer and the
generator can all use it without a cycle. Nothing here knows a word of any book or a list of anything
(Constitution VII): every rule is a Unicode general category or a fixed character -- and the one fixed table
of letters drawn identically in the Latin and the Cyrillic alphabets (``unify_mixed_script_words``).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

__all__ = [
    "LetterSeries",
    "is_cyrillic_letter",
    "is_latin_letter",
    "letter_series",
    "original_span",
    "unify_mixed_script_words",
    "without_combining_marks",
    "without_combining_marks_with_offsets",
]

# Characters that join two letter runs into one word, and are cut off at the edge of a unit: the hyphen-minus,
# U+2010 HYPHEN, U+2011 NON-BREAKING HYPHEN, the apostrophe and U+2019 RIGHT SINGLE QUOTATION MARK.
_JOINERS = frozenset("-‐‑'’")


def _is_combining_mark(character: str) -> bool:
    return unicodedata.category(character).startswith("M")


def without_combining_marks(text: str) -> str:
    """Drop combining marks (Unicode category M*): a diacritic belongs to its letter, so it is
    neither a letter run of its own nor a non-letter that dilutes the share of letters."""

    return "".join(character for character in text if not _is_combining_mark(character))


def without_combining_marks_with_offsets(text: str) -> tuple[str, tuple[int, ...]]:
    """``(stripped, offsets)``: the text without its marks and, for each character of it, the index of
    that character in ``text`` (``len(offsets) == len(stripped)``)."""

    kept: list[str] = []
    offsets: list[int] = []
    for index, character in enumerate(text):
        if _is_combining_mark(character):
            continue
        kept.append(character)
        offsets.append(index)
    return "".join(kept), tuple(offsets)


def original_span(text: str, offsets: tuple[int, ...] | list[int], start: int, end: int) -> tuple[int, int]:
    """The span ``[start, end)`` of the string WITHOUT marks as a span of ``text``.

    The end is carried through the marks that follow the last letter of the span: a mark belongs to its
    letter, so a slice of ``text`` never ends between a letter and its stress mark. An empty span stays empty.
    """

    original_start = offsets[start] if start < len(offsets) else len(text)
    if end <= start:
        return original_start, original_start
    original_end = offsets[end - 1] + 1
    while original_end < len(text) and _is_combining_mark(text[original_end]):
        original_end += 1
    return original_start, original_end


@dataclass(frozen=True)
class LetterSeries:
    """One unit of letters. ``start`` / ``end`` are positions of the string the series was read from."""

    text: str
    start: int
    end: int


def letter_series(text: str, *, digits_inside: bool = False) -> tuple[LetterSeries, ...]:
    """The maximal series of letters (L*) with their marks (M*), hyphens and apostrophes, and -- when
    ``digits_inside`` -- decimal digits (Nd); hyphens and apostrophes at either edge are cut off, and a
    series without a letter is not a unit. A superscript or a fraction is not a decimal digit, so it never
    joins a series."""

    units: list[LetterSeries] = []
    run_start: int | None = None
    for index in range(len(text) + 1):
        character = text[index] if index < len(text) else ""
        category = unicodedata.category(character) if character else ""
        belongs = bool(character) and (
            category.startswith(("L", "M")) or character in _JOINERS or (digits_inside and category == "Nd")
        )
        if belongs:
            if run_start is None:
                run_start = index
            continue
        if run_start is not None:
            unit = _trimmed_unit(text, run_start, index)
            if unit is not None:
                units.append(unit)
            run_start = None
    return tuple(units)


def _trimmed_unit(text: str, start: int, end: int) -> LetterSeries | None:
    while start < end and text[start] in _JOINERS:
        start += 1
    while end > start and text[end - 1] in _JOINERS:
        end -= 1
    if not any(unicodedata.category(character).startswith("L") for character in text[start:end]):
        return None
    return LetterSeries(text=text[start:end], start=start, end=end)


def is_latin_letter(character: str) -> bool:
    """One character that is a letter (L*) of the Latin script, by its Unicode name."""

    if len(character) != 1 or not unicodedata.category(character).startswith("L"):
        return False
    return "LATIN" in unicodedata.name(character, "")


def is_cyrillic_letter(character: str) -> bool:
    """One character that is a letter (L*) of the Cyrillic script, by its Unicode name."""

    if len(character) != 1 or not unicodedata.category(character).startswith("L"):
        return False
    return "CYRILLIC" in unicodedata.name(character, "")


# Spec 073 (measurement WP-Y, 2026-11-10): the basic Latin letters that are drawn exactly like a Cyrillic letter,
# paired with that letter. A fixed table of the two alphabets (homoglyphs), not a list of words: it says nothing
# about any book. Only visually identical pairs -- a letter that merely resembles another (Latin ``n`` / Cyrillic
# ``п``, Latin ``u`` / ``и``) is not here, so a word with such a letter keeps it and stays residue for the repair.
_LATIN_LOOKALIKES = "aeopcxyABEKMHOPCTX"
_CYRILLIC_TWINS = "аеорсхуАВЕКМНОРСТХ"
_LOOKALIKE_TO_CYRILLIC = str.maketrans(_LATIN_LOOKALIKES, _CYRILLIC_TWINS)
_LATIN_LOOKALIKE_SET = frozenset(_LATIN_LOOKALIKES)


def _is_word_character(character: str) -> bool:
    return unicodedata.category(character).startswith(("L", "M"))


def _unified_word(word: str) -> str:
    decomposed = unicodedata.normalize("NFD", word)
    if not any(character in _LATIN_LOOKALIKE_SET for character in decomposed):
        return word
    if not any(is_cyrillic_letter(character) for character in decomposed):
        return word
    return unicodedata.normalize("NFC", decomposed.translate(_LOOKALIKE_TO_CYRILLIC))


def unify_mixed_script_words(text: str) -> str:
    """A Latin look-alike letter inside a Cyrillic word becomes its Cyrillic twin.

    A word here is a maximal run of letters (L*) and their marks (M*); a hyphen, an apostrophe, a digit or a
    space ends it, so each part of ``ABC-рынок`` is a word of its own. A word that holds a Cyrillic letter is
    decomposed (NFD: a precomposed Latin ``á`` becomes ``a`` + U+0301), each Latin letter of the table above
    is replaced by its Cyrillic twin, and the word is recomposed (NFC), so a stress mark ends as U+0301 on the
    Cyrillic letter. A word without a Cyrillic letter, or without a look-alike, is returned byte for byte: real
    Latin stays Latin and remains residue for the repair call. Pure and idempotent.
    """

    if text.isascii():
        return text
    pieces: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        start = index
        in_word = _is_word_character(text[index])
        while index < length and _is_word_character(text[index]) == in_word:
            index += 1
        piece = text[start:index]
        pieces.append(_unified_word(piece) if in_word else piece)
    return "".join(pieces)
