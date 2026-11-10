"""Spec 073 WP-B (FR-001, FR-003, FR-005): the audiobook prompt rules, tested by their properties.

The rules are rules by FORM (Constitution VII): a stress mark on the word that is spelled like
another word and read differently, Latin script written in Cyrillic as it is pronounced, the
number at the head of a heading read as a neuter ordinal. There is no homograph list, no
transliteration table and no table of numerals, so these tests check the properties of the
RENDERED prompts (``load_system_prompt``), not phrases (the pattern of
``tests/test_audiobook_prompt.py``):

* the stress rule carries the combining acute U+0301 in a word of its own text, and nothing in
  the prompt shows another way to mark stress (a ``+`` before a vowel, a capital vowel inside a
  lower-case word);
* the Latin rule states its priority as four items in a fixed order -- the book's reading
  section, a Latin abbreviation without a record, a Latin initial, a Cyrillic abbreviation
  without a record -- and "as is" is said of Cyrillic only;
* the section-number rule is one line that sees the number through inline emphasis
  (``## **1. …**``, research R3) and forbids adding words;
* the ``repair`` variant reads its OWN instructions file (``core/config.py:1773``), so every rule
  it needs is checked on the rendered repair prompt, not inherited from the main one;
* the example teaches the same rules with invented text.

The name of the reading section is the literal of ``contracts/prompt-and-glossary.md`` §2 (the
constant ``READING_GLOSSARY_SECTION_HEADER`` belongs to another work package; the contract
literal is copied here on purpose, so a drift between the two is a visible failure).
"""

from __future__ import annotations

import re
from pathlib import Path

import docxaicorrector.core.config as config

_PROMPTS = Path(config.PROMPTS_DIR)
_MARKER = re.compile(r"\[\[DOCX_PARA_[A-Za-z0-9_.]+\]\]")
_STRESS = "́"
_VOWELS = "аеёиоуыэюяАЕЁИОУЫЭЮЯ"
_SECTION_HEADER = (
    "КАК ЧИТАТЬ СОКРАЩЕНИЯ ЭТОЙ КНИГИ (каждое сокращение из списка читайте ровно так; "
    "если чтение — слово, склоняйте его по смыслу):"
)
_SECTION_NAME = _SECTION_HEADER.split(" (", 1)[0]
_PLUS_BEFORE_VOWEL = re.compile(rf"\+[{_VOWELS}]")
_CAPITAL_VOWEL_INSIDE_WORD = re.compile(r"[а-яё][АЕЁИОУЫЭЮЯ][а-яё]")
_STRESSED_WORD = re.compile(rf"[а-яё]*[{_VOWELS}]{_STRESS}[а-яё]*", re.IGNORECASE)
_MARK_NOT_AFTER_VOWEL = re.compile(rf"(?:^|[^{_VOWELS}]){_STRESS}")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_LATIN_PRIORITY_ANCHORS = (
    re.escape(_SECTION_NAME),
    r"латинск\w*\s+аббревиатур",
    r"латинск\w*\s+инициал",
    r"кириллическ\w*\s+аббревиатур",
)
_HEADING_NUMBER_IN_EMPHASIS = re.compile(r"^#+\s+\*\*\s*\d+\.\s", re.MULTILINE)
_NEUTER_ORDINAL_HEAD = re.compile(r"^[А-ЯЁ][а-яё]+(?:ое|ье)\.\s")


def _load(prompt_variant: str = "default") -> str:
    config.load_system_prompt.cache_clear()
    try:
        return config.load_system_prompt(operation="audiobook", prompt_variant=prompt_variant)
    finally:
        config.load_system_prompt.cache_clear()


def _sections(prompt: str) -> dict[str, str]:
    parts = re.split(r"^### (.+)$", prompt, flags=re.MULTILINE)
    return {parts[index].strip(): parts[index + 1].strip() for index in range(1, len(parts) - 1, 2)}


def _instructions(prompt_variant: str = "default") -> str:
    return _sections(_load(prompt_variant))["ИНСТРУКЦИИ РЕЖИМА"]


def _rules(text: str) -> list[str]:
    """Numbered rules and blank-line paragraphs; sub-items stay with the rule they belong to."""

    return [chunk.strip() for chunk in re.split(r"\n(?=\d+\.\s)|\n\s*\n", text) if chunk.strip()]


def _rule_with(text: str, *needles: str) -> str:
    matching = [rule for rule in _rules(text) if all(needle.lower() in rule.lower() for needle in needles)]
    assert len(matching) == 1, f"expected exactly one rule naming {needles}, found {len(matching)}"
    return matching[0]


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def _assert_stress_rule(instructions: str) -> None:
    rule = _rule_with(instructions, "ударени", "транскрипц")
    assert _STRESSED_WORD.search(rule), "the stress rule shows the mark U+0301 in a word"
    for forbidden in ("заглавн", "«+»", "апостроф", "транскрипц"):
        assert forbidden in rule, f"the stress rule names {forbidden!r} as forbidden"


def _assert_no_other_stress_notation(prompt: str) -> None:
    assert not _PLUS_BEFORE_VOWEL.search(prompt)
    assert not _CAPITAL_VOWEL_INSIDE_WORD.search(prompt)
    assert not _MARK_NOT_AFTER_VOWEL.search(prompt), "the mark stands right after the stressed vowel"


def _assert_latin_priority(instructions: str) -> None:
    rule = _rule_with(instructions, _SECTION_NAME, "инициал")
    starts: list[int] = []
    for anchor in _LATIN_PRIORITY_ANCHORS:
        match = re.compile(anchor, re.IGNORECASE).search(rule, (starts[-1] + 1) if starts else 0)
        assert match, f"priority item {anchor!r} is missing or out of order"
        starts.append(match.start())
    first, second, third, fourth = (
        rule[starts[0] : starts[1]],
        rule[starts[1] : starts[2]],
        rule[starts[2] : starts[3]],
        rule[starts[3] :],
    )
    assert "ровно" in first, "a record of the reading section is read exactly as written"
    assert "букв" in second, "a Latin abbreviation without a record is read by the names of its letters"
    assert "букв" in third and "имя" in third, "a Latin initial is the name of its letter; no name is invented"
    assert "как есть" in fourth
    assert "как есть" not in rule[: starts[3]], "'as is' belongs to the Cyrillic item only"


def _assert_as_is_only_for_cyrillic(instructions: str) -> None:
    """Every 'keep as is' said of an abbreviation or an initial is said of Cyrillic ones only."""

    said_of_units = [
        sentence
        for sentence in _sentences(instructions)
        if "как есть" in sentence and re.search(r"аббревиатур|инициал", sentence)
    ]
    assert said_of_units, "the Cyrillic 'as is' item is stated"
    for sentence in said_of_units:
        assert "кириллическ" in sentence, f"'as is' said of something other than Cyrillic: {sentence!r}"


# ------------------------------------------------------------------------- T-B2: stress (main)


def test_main_prompt_states_the_stress_rule_with_the_mark_itself():
    _assert_stress_rule(_instructions())


def test_main_prompt_shows_no_other_way_to_mark_stress():
    _assert_no_other_stress_notation(_load())


def test_main_prompt_names_the_reading_section_by_its_literal_name():
    assert _SECTION_NAME in _instructions()


# ------------------------------------------------------------------- T-B3: Latin priority (main)


def test_main_prompt_states_the_latin_priority_in_order():
    _assert_latin_priority(_instructions())


def test_main_prompt_keeps_the_initials_rule_of_spec_070():
    assert "не восстанавливайте имя по памяти" in _instructions().lower()


def test_main_prompt_says_as_is_of_cyrillic_only():
    _assert_as_is_only_for_cyrillic(_instructions())


def test_main_prompt_says_latin_is_written_in_cyrillic_not_translated():
    rule = _rule_with(_instructions(), _SECTION_NAME, "инициал")
    assert "латиниц" in rule and "кириллиц" in rule
    assert "не перевод" in rule, "transliteration does not contradict 'keep the language of every fragment'"


# ------------------------------------------------------------------ T-B4: section number (main)


def test_main_prompt_reads_a_heading_number_as_a_neuter_ordinal_in_one_line():
    lines = [
        line
        for line in _instructions().splitlines()
        if "заголов" in line and "порядков" in line and "средн" in line
    ]
    assert len(lines) == 1
    line = lines[0]
    assert "римск" in line and "точк" in line
    assert re.search(r"\*\*\s*\d+\.", line), "the number is seen through emphasis at the head of a heading"
    assert "не добавля" in line and "глав" in line, "no word such as 'chapter' is added"
    ordinal_examples = re.findall(r"«[А-ЯЁ][а-яё]+(?:ое|ье)\.»", line)
    assert 1 <= len(ordinal_examples) <= 2, "an illustration of the form, not a list of numerals"


# ---------------------------------------------------------------- T-B5: the rendered repair prompt


def test_repair_prompt_names_latin_among_the_residue():
    residue = _rule_with(_instructions("repair"), "цифры", "римские")
    assert "латиниц" in residue


def test_repair_prompt_states_the_stress_rule_with_the_mark_itself():
    _assert_stress_rule(_instructions("repair"))


def test_repair_prompt_shows_no_other_way_to_mark_stress():
    _assert_no_other_stress_notation(_load("repair"))


def test_repair_prompt_states_the_same_latin_priority_in_order():
    _assert_latin_priority(_instructions("repair"))


def test_repair_prompt_names_the_reading_section_and_says_as_is_of_cyrillic_only():
    instructions = _instructions("repair")
    assert _SECTION_NAME in instructions
    _assert_as_is_only_for_cyrillic(instructions)


# ------------------------------------------------------------------------------ T-B6: the example


def _example_pairs() -> list[tuple[str, str]]:
    body = (_PROMPTS / "example_audiobook.txt").read_text(encoding="utf-8").strip()
    pairs = []
    for chunk in body.split("Пример принципа:")[1:]:
        _, rest = chunk.split("Вход:", 1)
        source, result = rest.split("Выход:", 1)
        pairs.append((source.strip(), result.strip()))
    return pairs


def _paragraphs(text: str) -> dict[str, str]:
    parts = _MARKER.split(text)
    return {marker: part.strip() for marker, part in zip(_MARKER.findall(text), parts[1:])}


def test_example_results_carry_no_latin_letters():
    for _, result in _example_pairs():
        assert not _LATIN_LETTER.search(_MARKER.sub("", result))


def test_example_shows_a_latin_name_in_cyrillic_and_a_stress_mark():
    shown = [
        (source, result)
        for source, result in _example_pairs()
        if re.search(r"[A-Za-z]{2,}", _MARKER.sub("", source)) and _STRESSED_WORD.search(result)
    ]
    assert len(shown) == 1
    source, result = shown[0]
    assert _STRESS not in source, "the mark is added by the pass, not copied"
    assert not _MARK_NOT_AFTER_VOWEL.search(result)


def test_example_shows_a_heading_number_inside_emphasis_read_as_a_neuter_ordinal():
    shown = [(source, result) for source, result in _example_pairs() if _HEADING_NUMBER_IN_EMPHASIS.search(source)]
    assert len(shown) == 1
    source, result = shown[0]
    source_paragraphs, result_paragraphs = _paragraphs(source), _paragraphs(result)
    headings = [marker for marker, text in source_paragraphs.items() if _HEADING_NUMBER_IN_EMPHASIS.match(text)]
    assert headings
    for marker in headings:
        read = result_paragraphs[marker]
        assert _NEUTER_ORDINAL_HEAD.match(read), read
        assert "#" not in read and "*" not in read, "no markup in the result"
        if "глав" not in source_paragraphs[marker].lower():
            assert "глав" not in read.lower(), "no word is added to the number"
