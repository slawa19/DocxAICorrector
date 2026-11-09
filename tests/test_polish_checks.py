"""Spec 069 WP-4: rollback predicates of the literary polish pass.

Every pair below is INVENTED and has the FORM of one of the seven real firings of research R1
(a number moved, a number written in words, a foreign word, a mixed-script word, a list number
changed): no text of any book (Constitution VII, guard 066)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docxaicorrector.text import polish_checks as pc

_SCHEMA = (
    Path(__file__).resolve().parent.parent
    / "specs"
    / "069-translation-modes"
    / "contracts"
    / "literary-polish-rollbacks.schema.json"
)

# A Latin letter inside a Cyrillic word, written by code point so the file itself stays clean.
_LATIN_E = "e"
_LATIN_O = "o"


def _check(first_pass: str, candidate: str, lang: str = "ru") -> pc.PolishCheckResult:
    return pc.check_polished_paragraph(first_pass, candidate, target_language=lang)


def _stretched(base: str, ratio: float) -> str:
    """A candidate of exactly ``ratio`` of the visible length of ``base``."""
    return "а" * round(len(base) * ratio)


# --- A. silent on a good edit ----------------------------------------------------------------

_GOOD_EDITS = [
    ("Он быстро пошёл домой.", "Он поспешил домой."),  # style / synonym
    ("Река текла медленно и тихо.", "Тихо и медленно текла река."),  # word order
    ("В саду было 12 яблонь.", "В саду росло 12 яблонь."),  # number kept
    ("• первый пункт\n• второй", "- первый пункт\n- второй"),  # delivery glyph, O-3
    ("1. Первый шаг", "1. Начальный шаг"),
    ("Текст¹ со сноской.", "Со сноской текст¹."),
    ("См. https://example.org/a и mail@example.org.", "Смотрите https://example.org/a и mail@example.org."),
]


@pytest.mark.parametrize(("first_pass", "candidate"), _GOOD_EDITS)
def test_good_edit_fires_no_predicate(first_pass: str, candidate: str) -> None:
    result = _check(first_pass, candidate)
    assert result.reasons == ()
    assert not result.rolled_back


@pytest.mark.parametrize("ratio", [0.82, 1.43])
def test_good_length_ratio_is_silent(ratio: float) -> None:
    base = "а" * 200
    assert pc.length_ratio_out_of_bounds(base, _stretched(base, ratio)) is None
    assert _check(base, _stretched(base, ratio)).reasons == ()


# --- B. one test per predicate form ------------------------------------------------------------


@pytest.mark.parametrize(
    ("first_pass", "candidate"),
    [
        ("Было 23 дома.", "Было 32 дома."),  # digits swapped
        ("Доля 1.5 процента.", "Доля 15 процента."),  # decimal point lost
        ("Было 23 дома.", "Было двадцать три дома."),  # number in words: conservative
        ("После 1 шага вышли.", "После шага вышли."),  # a number dropped with its phrase
    ],
)
def test_p1_numbers(first_pass: str, candidate: str) -> None:
    assert pc.numbers_changed(first_pass, candidate) is not None
    assert pc.REASON_NUMBERS_CHANGED in _check(first_pass, candidate).reasons


def test_p1_details_name_lost_and_added() -> None:
    details = pc.numbers_changed("Было 23 дома.", "Было 32 дома.")
    assert details == {"numbers_lost": {"23": 1}, "numbers_added": {"32": 1}}


def test_p2_new_non_target_word_ru() -> None:
    first_pass, candidate = "Они будут помогать нам.", "Они will помогать нам."
    assert pc.new_non_target_script_words(first_pass, candidate, "ru") == ["will"]
    result = _check(first_pass, candidate)
    assert pc.REASON_NEW_NON_TARGET_SCRIPT_WORD in result.reasons
    assert result.details["new_words"] == ["will"]


def test_p2_existing_non_target_word_is_not_new() -> None:
    first_pass, candidate = "Книга Smith вышла.", "Вышла книга Smith."
    assert pc.new_non_target_script_words(first_pass, candidate, "ru") == []


def test_p2_prime_lost_non_target_word_ru() -> None:
    first_pass, candidate = "Книга Smith вышла.", "Книга Смит вышла."
    assert pc.lost_non_target_script_words(first_pass, candidate, "ru") == ["Smith"]
    assert pc.REASON_LOST_NON_TARGET_SCRIPT_WORD in _check(first_pass, candidate).reasons


def test_p2_symmetric_for_latin_target() -> None:
    # target en: the non-target script is Cyrillic.
    new = pc.new_non_target_script_words("They will help us.", "They will помогать us.", "en")
    lost = pc.lost_non_target_script_words("They cite Иванов here.", "They cite Ivanov here.", "en")
    assert new == ["помогать"]
    assert lost == ["Иванов"]
    # and Latin words are NOT foreign for an en target
    assert pc.new_non_target_script_words("They help.", "They will help.", "en") == []
    assert pc.lost_non_target_script_words("They help.", "They will help.", "en") == []


def test_p2_ignores_url_and_email_tokens() -> None:
    first_pass = "Пишите на адрес."
    candidate = "Пишите на adress@example.org или www.example.org/page."
    assert pc.new_non_target_script_words(first_pass, candidate, "ru") == []
    lost = pc.lost_non_target_script_words(
        "Пишите на adress@example.org или www.example.org/page.", "Пишите.", "ru"
    )
    assert lost == []


def test_p2_unknown_target_script_is_silent() -> None:
    assert pc.new_non_target_script_words("Они идут.", "Они will идут.", "auto") == []
    assert pc.lost_non_target_script_words("Они Smith идут.", "Они идут.", None) == []


def test_p3_mixed_script_word() -> None:
    mixed = f"ход{_LATIN_E}л"  # Cyrillic letters with one Latin letter inside
    first_pass, candidate = "Он ходил домой.", f"Он {mixed} домой."
    assert pc.new_mixed_script_words(first_pass, candidate) == [mixed]
    assert pc.REASON_MIXED_SCRIPT_WORD in _check(first_pass, candidate).reasons


def test_p3_mixed_word_already_in_first_pass_is_not_new() -> None:
    mixed = f"ход{_LATIN_O}"
    assert pc.new_mixed_script_words(f"Он {mixed}.", f"Это {mixed}.") == []


@pytest.mark.parametrize(
    ("first_pass", "candidate"),
    [
        ("2. Второй шаг", "1. Второй шаг"),
        ("3) Третий шаг", "1) Третий шаг"),
        ("## Раздел", "# Раздел"),
        ("- пункт", "Пункт"),
    ],
)
def test_p4_prefix_changed(first_pass: str, candidate: str) -> None:
    assert pc.list_prefix_changed(first_pass, candidate) is not None
    assert pc.REASON_LIST_PREFIX_CHANGED in _check(first_pass, candidate).reasons


def test_p4_bullet_glyph_to_dash_is_not_a_change() -> None:
    assert pc.list_prefix_changed("• первый пункт", "- первый пункт") is None


def test_p5_lost_footnote_marker() -> None:
    assert pc.lost_footnote_markers("Слово¹ и слово².", "Слово и слово².") == {"¹": 1}
    assert pc.REASON_FOOTNOTE_MARKER_LOST in _check("Слово¹ и слово².", "Слово и слово².").reasons


def test_p5_multiset_counts_repeats() -> None:
    assert pc.lost_footnote_markers("А¹ б¹.", "А¹ б.") == {"¹": 1}


@pytest.mark.parametrize("ratio", [0.69, 1.51])
def test_p6_length_out_of_bounds(ratio: float) -> None:
    base = "а" * 200
    candidate = _stretched(base, ratio)
    assert pc.length_ratio_out_of_bounds(base, candidate) == pytest.approx(ratio, abs=0.005)
    assert pc.REASON_LENGTH_RATIO_OUT_OF_BOUNDS in _check(base, candidate).reasons


def test_p6_markup_is_not_visible_length() -> None:
    assert pc.length_ratio("**аб**", "аб") == 1.0


def test_p6_empty_first_pass_has_no_ratio() -> None:
    assert pc.length_ratio("", "текст") is None
    assert pc.length_ratio_out_of_bounds("", "текст") is None


# --- C. summary --------------------------------------------------------------------------------


def test_summary_reports_several_reasons_in_fixed_order() -> None:
    result = _check("2. Было 23 дома.", "1. Было 32 дома.")
    assert result.reasons == (pc.REASON_NUMBERS_CHANGED, pc.REASON_LIST_PREFIX_CHANGED)
    assert result.rolled_back


def test_reason_codes_match_schema_enum() -> None:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    enum = set(schema["properties"]["reasons"]["items"]["enum"])
    paragraph = set(pc.PARAGRAPH_ROLLBACK_REASONS)
    assert len(paragraph) == len(pc.PARAGRAPH_ROLLBACK_REASONS) == 7
    assert paragraph <= enum
    # the rest of the enum belongs to the caller (block-level and failure reasons)
    assert enum - paragraph == {"not_accepted", "block_marker_mismatch", "pass_failed", "stopped"}


def test_every_reason_is_reachable_through_the_summary() -> None:
    fired: set[str] = set()
    cases = [
        ("Было 23 дома.", "Было 32 дома.", "ru"),
        ("Они будут.", "Они will.", "ru"),
        ("Книга Smith.", "Книга Смит.", "ru"),
        ("Он ходил.", f"Он ход{_LATIN_E}л.", "ru"),
        ("2. Шаг", "1. Шаг", "ru"),
        ("Слово¹.", "Слово.", "ru"),
        ("а" * 100, "а" * 40, "ru"),
    ]
    for first_pass, candidate, lang in cases:
        fired.update(_check(first_pass, candidate, lang).reasons)
    assert fired == set(pc.PARAGRAPH_ROLLBACK_REASONS)
