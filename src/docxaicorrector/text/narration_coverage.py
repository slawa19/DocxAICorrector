"""Spec 070 FR-007: per-paragraph coverage signal (research R9).

"What share of the long words of this paragraph's INPUT appear in ITS OWN answer." It is an
auxiliary signal, not proof: a lost number or a flipped negation is caught by reading the sample
(FR-008), not here. Pure function; no pipeline, no network, no word list.

Digits are not letters: a number rewritten in words neither lowers the share nor counts as a lost
word, and a digit string in the input is never a "long word". Words are compared by STEM, the first
``STEM_LETTERS`` letters after ``casefold``, so different case endings of one word match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from docxaicorrector.text.narration_forms import without_combining_marks

__all__ = [
    "COVERAGE_MIN_LONG_WORDS",
    "COVERAGE_MIN_TOKENS",
    "COVERAGE_REVIEW_THRESHOLD",
    "CoverageResult",
    "LONG_WORD_MIN_LETTERS",
    "STEM_LETTERS",
    "paragraph_coverage",
]

# Provisional (research R9): the threshold of the measurer that produced the old-run baseline.
COVERAGE_REVIEW_THRESHOLD = 0.6
COVERAGE_MIN_LONG_WORDS = 4
COVERAGE_MIN_TOKENS = 6
LONG_WORD_MIN_LETTERS = 6
STEM_LETTERS = 5

_LETTER_RUN = re.compile(r"[^\W\d_]+")


@dataclass(frozen=True)
class CoverageResult:
    long_word_count: int
    found_count: int
    ratio: float | None  # None: not measured (too little text to make a share meaningful)


def _stem(word: str) -> str:
    return word.casefold()[:STEM_LETTERS]


def paragraph_coverage(source: str, answer: str) -> CoverageResult:
    # Spec 073 FR-002: both sides are read without stress marks, so a marked word is one word.
    source = without_combining_marks(source)
    answer = without_combining_marks(answer)
    long_words = [word for word in _LETTER_RUN.findall(source) if len(word) >= LONG_WORD_MIN_LETTERS]
    long_word_count = len(long_words)
    if long_word_count < COVERAGE_MIN_LONG_WORDS or len(source.split()) < COVERAGE_MIN_TOKENS:
        return CoverageResult(long_word_count=long_word_count, found_count=0, ratio=None)
    answer_stems = {_stem(word) for word in _LETTER_RUN.findall(answer)}
    found_count = sum(1 for word in long_words if _stem(word) in answer_stems)
    return CoverageResult(long_word_count=long_word_count, found_count=found_count, ratio=found_count / long_word_count)
