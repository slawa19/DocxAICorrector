"""Spec 070 T-E6: per-paragraph coverage signal (FR-007, research R9)."""

from __future__ import annotations

from docxaicorrector.text.narration_coverage import (
    COVERAGE_REVIEW_THRESHOLD,
    paragraph_coverage,
)

# Five sentences. The dropped one (the fourth) carries 13 of the 21 long words, so removing it must
# take the share below the review threshold; the others carry two to four each.
SENTENCES = [
    "Путешественник приехал рано.",
    "Хозяйка встретила гостя.",
    "Библиотека находилась рядом, коридор вёл налево.",
    "Лестница поднималась медленно, скрипели ступени, потолок нависал, фонари мерцали, окошки запотели, сквозняки гуляли.",
    "Утром выпал снег.",
]
SOURCE = " ".join(SENTENCES)


def test_identical_text_is_fully_covered() -> None:
    result = paragraph_coverage(SOURCE, SOURCE)
    assert result.ratio == 1.0
    assert result.long_word_count == result.found_count > 0


def test_a_dropped_sentence_lowers_the_share_below_the_threshold() -> None:
    answer = " ".join(SENTENCES[:3] + SENTENCES[4:])
    result = paragraph_coverage(SOURCE, answer)
    assert result.ratio is not None
    assert result.ratio < COVERAGE_REVIEW_THRESHOLD
    # anti-vacuum: the unmodified answer is above the threshold, so the line is not trivially crossed
    assert paragraph_coverage(SOURCE, SOURCE).ratio == 1.0


def test_a_number_in_words_instead_of_digits_does_not_lower_the_share() -> None:
    source = "Директор подписал приказ в 1234567 экземплярах и сразу передал документы архивариусу сегодня."
    answer = (
        "Директор подписал приказ в миллионе двухстах тридцати четырёх тысячах пятистах шестидесяти семи "
        "экземплярах и сразу передал документы архивариусу сегодня."
    )
    result = paragraph_coverage(source, answer)
    assert result.ratio == 1.0
    # the long digit string is not counted as a long word of the input
    assert result.long_word_count == 8


def test_words_are_compared_by_stem_so_case_endings_match() -> None:
    source = "Библиотекарь показывал читателям старинные рукописи каждому посетителю внимательно."
    answer = "Библиотекаря показывали читателю старинная рукопись каждого посетитель внимательный."
    result = paragraph_coverage(source, answer)
    assert result.ratio == 1.0


def test_stems_are_case_insensitive() -> None:
    source = "ПУТЕШЕСТВЕННИК ПРИЕХАЛ РАНО УТРОМ БИБЛИОТЕКА НАХОДИЛАСЬ РЯДОМ"
    answer = "путешественник приехал рано утром библиотека находилась рядом"
    assert paragraph_coverage(source, answer).ratio == 1.0


def test_too_few_long_words_is_not_measured() -> None:
    result = paragraph_coverage("Он шёл по длинной дороге домой вечером.", "")
    assert result.ratio is None
    assert result.long_word_count < 4


def test_too_few_tokens_is_not_measured() -> None:
    source = "Путешественник библиотекарь архивариус путеводитель"  # 4 long words, 4 tokens
    result = paragraph_coverage(source, "")
    assert result.long_word_count == 4
    assert result.ratio is None


def test_an_empty_answer_for_a_measurable_paragraph_is_zero() -> None:
    result = paragraph_coverage(SOURCE, "")
    assert result.ratio == 0.0
    assert result.found_count == 0
