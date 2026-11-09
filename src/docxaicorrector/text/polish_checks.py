"""Spec 069 FR-004 (4): rollback predicates of the literary polish (second) pass.

Pure functions, no I/O, no Streamlit, no network. Each predicate compares a polished candidate
paragraph with the first-pass paragraph it was made from and answers by FORM only (Constitution
VII): digit tokens, letter scripts, leading list/heading prefixes, superscript references and
visible length. No word list, no dictionary of numerals: a number rewritten in words is a
deliberately conservative rollback (research R1, "число словами").

The reason codes are the ``reasons`` enum of
``specs/069-translation-modes/contracts/literary-polish-rollbacks.schema.json`` (the
paragraph-level subset; ``not_accepted``, ``block_marker_mismatch``, ``pass_failed`` and
``stopped`` belong to the caller).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from docxaicorrector.generation._generation import _number_leak_tokens
from docxaicorrector.pipeline.footnote_markers import superscript_markers
from docxaicorrector.pipeline.output_validation import (
    _CYRILLIC_LATIN_MIXED_TOKEN_PATTERN,
    _URL_OR_EMAIL_TOKEN_PATTERN,
    normalize_residual_bullet_glyphs_markdown,
)
from docxaicorrector.text.transform_assessment import _classify_char_script, expected_script_for_language

REASON_NUMBERS_CHANGED = "numbers_changed"
REASON_NEW_NON_TARGET_SCRIPT_WORD = "new_non_target_script_word"
REASON_LOST_NON_TARGET_SCRIPT_WORD = "lost_non_target_script_word"
REASON_MIXED_SCRIPT_WORD = "mixed_script_word"
REASON_LIST_PREFIX_CHANGED = "list_prefix_changed"
REASON_FOOTNOTE_MARKER_LOST = "footnote_marker_lost"
REASON_LENGTH_RATIO_OUT_OF_BOUNDS = "length_ratio_out_of_bounds"

#: Paragraph-level reason codes, in the order the summary function reports them.
PARAGRAPH_ROLLBACK_REASONS: tuple[str, ...] = (
    REASON_NUMBERS_CHANGED,
    REASON_NEW_NON_TARGET_SCRIPT_WORD,
    REASON_LOST_NON_TARGET_SCRIPT_WORD,
    REASON_MIXED_SCRIPT_WORD,
    REASON_LIST_PREFIX_CHANGED,
    REASON_FOOTNOTE_MARKER_LOST,
    REASON_LENGTH_RATIO_OUT_OF_BOUNDS,
)

#: Research R1: 0 of 206 compared paragraphs fall outside; the bounds catch only gross failures.
LENGTH_RATIO_MIN = 0.70
LENGTH_RATIO_MAX = 1.50

_LETTER_RUN = re.compile(r"[^\W\d_]+")
_NON_SPACE_RUN = re.compile(r"\S+")
_PREFIX = re.compile(r"^\s*((?:#{1,6}\s+|>\s+|[-*•●▪◦]\s*|\d+[.)]\s+|[IVXLC]+[.)]\s+)*)")
_MARKUP = re.compile(r"[*_`]")


@dataclass(frozen=True)
class PolishCheckResult:
    """``reasons`` is empty when the candidate is acceptable; ``details`` carries, per fired
    reason, what exactly fired (schema field ``details``)."""

    reasons: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def rolled_back(self) -> bool:
        return bool(self.reasons)


def _visible_length(text: str) -> int:
    return len(_MARKUP.sub("", text or "").strip())


def _words(text: str) -> list[str]:
    result: list[str] = []
    for token in _NON_SPACE_RUN.findall(text or ""):
        if _URL_OR_EMAIL_TOKEN_PATTERN.search(token):
            continue
        result.extend(_LETTER_RUN.findall(token))
    return result


def _word_script(word: str) -> str | None:
    """The single script of the word, or None when its letters mix scripts or are unclassified."""
    scripts = {_classify_char_script(char) for char in word}
    scripts.discard(None)
    if len(scripts) == 1:
        return next(iter(scripts))
    return None


def _non_target_words(text: str, target_script: str | None) -> list[str]:
    if target_script is None:
        return []
    return [word for word in _words(text) if (script := _word_script(word)) is not None and script != target_script]


def _mixed_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in _NON_SPACE_RUN.findall(text or ""):
        if _URL_OR_EMAIL_TOKEN_PATTERN.search(token):
            continue
        tokens.extend(_CYRILLIC_LATIN_MIXED_TOKEN_PATTERN.findall(token))
    return tokens


def _list_prefix(text: str) -> str:
    match = _PREFIX.match(normalize_residual_bullet_glyphs_markdown(text or ""))
    return re.sub(r"\s+", " ", match.group(1) if match else "").strip()


def numbers_changed(first_pass: str, candidate: str) -> dict[str, dict[str, int]] | None:
    """P1: the multiset of numeric tokens differs (one normalisation on both sides)."""
    before, after = _number_leak_tokens(first_pass), _number_leak_tokens(candidate)
    if before == after:
        return None
    return {"numbers_lost": dict(before - after), "numbers_added": dict(after - before)}


def new_non_target_script_words(first_pass: str, candidate: str, target_language: str | None) -> list[str]:
    """P2: whole words of a script other than the target's that the candidate has and the
    first pass lacks (casefolded). Empty when the target script is unknown."""
    known = {word.casefold() for word in _words(first_pass)}
    target_script = expected_script_for_language(target_language)
    return [word for word in _non_target_words(candidate, target_script) if word.casefold() not in known]


def lost_non_target_script_words(first_pass: str, candidate: str, target_language: str | None) -> list[str]:
    """P2': whole words of a non-target script the first pass has and the candidate lost
    (a left-as-is reference or title that the polish translated or transliterated)."""
    kept = {word.casefold() for word in _words(candidate)}
    target_script = expected_script_for_language(target_language)
    return [word for word in _non_target_words(first_pass, target_script) if word.casefold() not in kept]


def new_mixed_script_words(first_pass: str, candidate: str) -> list[str]:
    """P3: a Latin+Cyrillic word inside the candidate that the first pass does not have."""
    known = {token.casefold() for token in _mixed_tokens(first_pass)}
    return [token for token in _mixed_tokens(candidate) if token.casefold() not in known]


def list_prefix_changed(first_pass: str, candidate: str) -> tuple[str, str] | None:
    """P4: the leading heading/quote/list prefix differs after the delivery's own bullet-glyph
    normalisation ("•" -> "-" is no change; "2." -> "1." is)."""
    before, after = _list_prefix(first_pass), _list_prefix(candidate)
    return None if before == after else (before, after)


def lost_footnote_markers(first_pass: str, candidate: str) -> dict[str, int]:
    """P5: superscript references of the first pass the candidate lacks (multiset)."""
    return dict(Counter(superscript_markers(first_pass)) - Counter(superscript_markers(candidate)))


def length_ratio(first_pass: str, candidate: str) -> float | None:
    """Visible characters of the candidate over the first pass; None when the first pass is empty."""
    base = _visible_length(first_pass)
    if base == 0:
        return None
    return _visible_length(candidate) / base


def length_ratio_out_of_bounds(first_pass: str, candidate: str) -> float | None:
    """P6: the ratio when it lies outside [LENGTH_RATIO_MIN; LENGTH_RATIO_MAX], else None."""
    ratio = length_ratio(first_pass, candidate)
    if ratio is None or LENGTH_RATIO_MIN <= ratio <= LENGTH_RATIO_MAX:
        return None
    return ratio


def check_polished_paragraph(first_pass: str, candidate: str, *, target_language: str | None) -> PolishCheckResult:
    """All paragraph predicates against the first pass; any reason means "keep the first pass"."""
    reasons: list[str] = []
    details: dict[str, Any] = {}

    numbers = numbers_changed(first_pass, candidate)
    if numbers is not None:
        reasons.append(REASON_NUMBERS_CHANGED)
        details.update(numbers)

    new_words = new_non_target_script_words(first_pass, candidate, target_language)
    if new_words:
        reasons.append(REASON_NEW_NON_TARGET_SCRIPT_WORD)
        details["new_words"] = new_words

    lost_words = lost_non_target_script_words(first_pass, candidate, target_language)
    if lost_words:
        reasons.append(REASON_LOST_NON_TARGET_SCRIPT_WORD)
        details["lost_words"] = lost_words

    mixed = new_mixed_script_words(first_pass, candidate)
    if mixed:
        reasons.append(REASON_MIXED_SCRIPT_WORD)
        details["mixed_words"] = mixed

    prefixes = list_prefix_changed(first_pass, candidate)
    if prefixes is not None:
        reasons.append(REASON_LIST_PREFIX_CHANGED)
        details["prefix_first_pass"], details["prefix_candidate"] = prefixes

    lost_markers = lost_footnote_markers(first_pass, candidate)
    if lost_markers:
        reasons.append(REASON_FOOTNOTE_MARKER_LOST)
        details["footnote_markers_lost"] = lost_markers

    ratio = length_ratio_out_of_bounds(first_pass, candidate)
    if ratio is not None:
        reasons.append(REASON_LENGTH_RATIO_OUT_OF_BOUNDS)
        details["length_ratio"] = ratio

    return PolishCheckResult(reasons=tuple(reasons), details=details)
