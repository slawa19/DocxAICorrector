"""Spec 070 T-E5: the residue detector (FR-006). Each class catches its own form and is silent on clean
prose; the counts are numbers of occurrences. Examples are invented and of the same FORM as real text."""

from __future__ import annotations

from docxaicorrector.text.narration_residue import (
    REPAIRABLE_RESIDUE_CLASSES,
    RESIDUE_CLASSES,
    detect_narration_residue,
)

CLEAN = (
    "Утром мы вышли к реке, и туман ещё лежал над водой. Никто не говорил — «тише», шептал проводник… "
    "Мы шли долго, пока не увидели т.е. тот самый мост и т.д. Эй, кафе, наив."
)


def by_class(text: str) -> dict[str, tuple[int, str]]:
    return {finding.residue_class: (finding.count, finding.sample) for finding in detect_narration_residue(text)}


def classes(text: str) -> set[str]:
    return set(by_class(text))


def test_clean_russian_prose_is_silent() -> None:
    assert detect_narration_residue(CLEAN) == ()
    assert detect_narration_residue("") == ()


def test_digits_count_numbers_not_characters() -> None:
    found = by_class("В 1990 году и в 2024 было 7 случаев.")
    assert found["digits"][0] == 3
    assert "1990" in found["digits"][1]


def test_superscript_and_subscript_digits_and_non_ascii_decimal_digits_are_digits() -> None:
    assert classes("площадь в м²") == {"digits"}
    assert classes("формула Н₂О") == {"digits"}
    assert classes("число ٣٤") == {"digits"}  # arabic-indic digits (Nd)


def test_fractions_and_circled_digits_are_not_in_the_class() -> None:
    assert "digits" not in classes("половина ½ и ①")


def test_roman_numerals_by_form() -> None:
    assert by_class("глава XIV и том II")["roman_numerals"][0] == 2
    assert "roman_numerals" in classes("раздел Ⅳ здесь")  # a Nl character
    assert "roman_numerals" in classes("раздел Ⅱ здесь")


def test_a_single_letter_i_and_lookalikes_inside_words_are_not_roman_numerals() -> None:
    assert "roman_numerals" not in classes("Мы говорили: I этого достаточно")
    assert "roman_numerals" not in classes("слово MIXED внутри")  # letters around: not a token of IVXLCDM only
    assert "roman_numerals" not in classes("МИД и ХХ век")  # Cyrillic capitals, not the Latin letters


def test_symbols_by_category_and_the_four_signs() -> None:
    found = by_class("цена $5 и 10% и № 3 и § 4 и Tom & Jerry")
    assert found["symbols"][0] == 5  # $ % № § &
    assert classes("а + б") == {"symbols"}
    assert classes("а → б") == {"symbols"}
    assert classes("а € б") == {"symbols"}  # a currency sign


def test_ordinary_punctuation_is_not_a_symbol() -> None:
    assert detect_narration_residue("Слово, слово; слово: «слово» — слово… (слово) 'слово' \"слово\" слово-слово.") == ()


def test_all_caps_needs_every_letter_upper_and_two_words_of_four_letters() -> None:
    assert classes("ТИХИЙ ВЕЧЕР НАД РЕКОЙ") == {"all_caps"}
    assert by_class("ТИХИЙ ВЕЧЕР НАД РЕКОЙ")["all_caps"][0] == 1
    assert "all_caps" not in classes("ВВП и США")  # lowercase "и"
    assert "all_caps" not in classes("ВВП США")  # no two words of >= 4 letters
    assert "all_caps" not in classes("ТИХИЙ")  # one long word
    assert "all_caps" not in classes("Тихий ВЕЧЕР НАД РЕКОЙ")  # a lowercase letter present


def test_url_or_domain() -> None:
    assert by_class("см. https://example.org/path и ещё")["url_or_domain"][0] == 1
    assert "url_or_domain" in classes("зайдите на www.example.org")
    assert "url_or_domain" in classes("сайт example.com работает")
    assert "url_or_domain" in classes("пишите на ftp://host/file")
    assert by_class("a.example.com и b.example.org")["url_or_domain"][0] == 2


def test_abbreviations_ellipses_and_numbers_are_not_domains() -> None:
    assert detect_narration_residue("то есть, т.е. вот так, и т.д. и т.п.") == ()
    assert "url_or_domain" not in classes("подожди...потом")
    assert "url_or_domain" not in classes("подожди…потом")
    assert "url_or_domain" not in classes("число 3.14 и версия 2.5")


def test_tag_form_is_lowercase_latin_in_brackets() -> None:
    assert by_class("[serious] текст [whispers softly] ещё")["tag_form"][0] == 2
    assert "tag_form" not in classes("[Примеч. ред.] текст")
    assert "tag_form" not in classes("[авторская вставка] текст")
    assert "tag_form" not in classes("[Serious] текст")
    assert "tag_form" not in classes("[[DOCX_IMAGE_a_1]] текст")


def test_html_and_emoji_left_are_reported() -> None:
    found = by_class("слово <b>слово</b> и \U0001F600")
    assert found["html_left"][0] == 2
    assert found["emoji_left"][0] == 1


def test_a_lone_less_than_is_a_symbol_but_not_html() -> None:
    assert classes("а < б") == {"symbols"}


def test_only_html_and_emoji_left_are_not_repairable() -> None:
    assert REPAIRABLE_RESIDUE_CLASSES == {"digits", "roman_numerals", "symbols", "all_caps", "url_or_domain", "tag_form", "latin"}
    assert {"html_left", "emoji_left"}.isdisjoint(REPAIRABLE_RESIDUE_CLASSES)
    assert set(RESIDUE_CLASSES) == REPAIRABLE_RESIDUE_CLASSES | {"html_left", "emoji_left"}


def test_findings_come_in_the_fixed_class_order_with_a_bounded_sample() -> None:
    text = "Начало. " * 30 + "число 5 и $ и конец. " + "Хвост. " * 30
    findings = detect_narration_residue(text)
    order = [finding.residue_class for finding in findings]
    assert order == [name for name in RESIDUE_CLASSES if name in order]
    assert all(len(finding.sample) <= 120 for finding in findings)
    digits = next(finding for finding in findings if finding.residue_class == "digits")
    assert "5" in digits.sample
