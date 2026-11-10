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


def _latin_priority_items(instructions: str) -> tuple[str, str, str, str]:
    rule = _rule_with(instructions, _SECTION_NAME, "инициал")
    starts: list[int] = []
    for anchor in _LATIN_PRIORITY_ANCHORS:
        match = re.compile(anchor, re.IGNORECASE).search(rule, (starts[-1] + 1) if starts else 0)
        assert match, f"priority item {anchor!r} is missing or out of order"
        starts.append(match.start())
    return (
        rule[starts[0] : starts[1]],
        rule[starts[1] : starts[2]],
        rule[starts[2] : starts[3]],
        rule[starts[3] :],
    )


def _assert_latin_priority(instructions: str) -> None:
    first, second, third, fourth = _latin_priority_items(instructions)
    assert "ровно" in first, "a record of the reading section is read exactly as written"
    assert "букв" in second, "a Latin abbreviation without a record is read by the names of its letters"
    assert "букв" in third and "имя" in third, "a Latin initial is the name of its letter; no name is invented"
    assert "как есть" in fourth
    assert "как есть" not in first + second + third, "'as is' belongs to the Cyrillic item only"


def _assert_a_section_record_is_not_expanded(instructions: str) -> None:
    """WP-Y (2026-11-10): an abbreviation of the reading section is written as its reading, everywhere, and is not
    replaced by its full name even when the model knows it (measured: the section's letter reading was replaced by
    the full name in place in a share of occurrences, a second reading in one book)."""

    first = _latin_priority_items(instructions)[0]
    clauses = [clause for clause in re.split(r"[;:]", first) if "полн" in clause and "назван" in clause]
    assert len(clauses) == 1, "one clause speaks of the full name"
    clause = clauses[0]
    assert re.search(r"\bне\s+раскрыва", clause), "the full name is forbidden, not offered"
    assert "даже если" in clause and "известн" in clause, "a known expansion is no exception"
    assert "в каждом месте одинаково" in first, "the same reading at every occurrence"


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


def test_main_prompt_writes_a_section_record_as_given_and_never_expands_it():
    _assert_a_section_record_is_not_expanded(_instructions())


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


# WP-Y (measurement 2026-11-10): the rule above over-applied -- a heading of the form "<word> <roman numeral>" lost its
# word and became a bare neuter ordinal, a heading of the form "<word> <n.m>" lost its word, a heading without a number
# got one, and two headings got their number twice. The three statements below are checked on the rendered rule; the
# split keeps "**1. …**" whole (a sentence ends at a period followed by a space and a capital letter).


def _heading_number_rule() -> str:
    lines = [line for line in _instructions().splitlines() if "заголов" in line and "порядков" in line and "средн" in line]
    assert len(lines) == 1
    return lines[0]


def _rule_sentences(rule: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?»])\s+(?=[А-ЯЁ])", rule) if part.strip()]


def test_heading_number_rule_applies_only_when_the_heading_itself_begins_with_the_number():
    prescribing = [sentence for sentence in _rule_sentences(_heading_number_rule()) if "порядков" in sentence]
    assert len(prescribing) == 1, "one sentence prescribes the neuter ordinal"
    sentence = prescribing[0]
    assert sentence.startswith("Если "), "the ordinal is a conditional, not a rule for every heading"
    assert re.search(r"заголовок\s+сам\s+начинается\s+с\s+номера", sentence), "the condition is the heading's own head"
    assert "перед номером" not in sentence, "a heading with a word before its number is outside this sentence"


def test_heading_number_rule_keeps_a_word_that_stands_before_the_number():
    sentences = [sentence for sentence in _rule_sentences(_heading_number_rule()) if "перед номером" in sentence]
    assert len(sentences) == 1
    sentence = sentences[0]
    assert re.search(r"перед номером стоит слово", sentence), "said by form, not by a list of words"
    assert re.search(r"слово\s+оставьте", sentence), "the word is kept"
    assert "соглас" in sentence and "словами" in sentence, "the number is written in words that agree with the word"
    assert "порядков" not in sentence and "средн" not in sentence, "no neuter ordinal for this form"
    examples = re.findall(r"«([^»]+)»", sentence)
    assert examples, "the form is illustrated"
    for example in examples:
        words = example.split()
        assert len(words) >= 2 and words[0][0].isupper(), "the word first, then the number"
        assert not re.search(r"\d|[IVXLCDM]{2,}|\.$", example), "the number is written in words, without a period"


def test_heading_number_rule_adds_no_number_or_word_and_does_not_repeat_the_heading():
    sentences = [sentence for sentence in _rule_sentences(_heading_number_rule()) if "не добавля" in sentence]
    assert len(sentences) == 1
    sentence = sentences[0]
    assert re.search(r"\bни в один заголовок\b", sentence, re.IGNORECASE), "said of every heading, numbered or not"
    assert "номер" in sentence and "слово" in sentence, "neither a number nor a word is added"
    assert "которых в нём нет" in sentence, "only what the heading itself carries"
    assert re.search(r"не повторяйте заголовок", sentence), "the heading is not said twice"


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


def test_repair_prompt_writes_a_section_record_as_given_and_never_expands_it():
    _assert_a_section_record_is_not_expanded(_instructions("repair"))


# ------------------------------------------------- WP-Y: the reading-glossary instructions (FR-004)
# Measured 2026-11-10: about a third of the candidates of a full book are ordinary words and surnames set in capitals
# (they pass the form rule by design, Non-goals); the model returned them lower-case, so a surname reached the
# narration lower-case. The instructions the step actually sends are read through the step's own loader.


def _glossary_instructions() -> str:
    from docxaicorrector.pipeline.reading_glossary import _load_reading_glossary_instructions

    _load_reading_glossary_instructions.cache_clear()
    try:
        return _load_reading_glossary_instructions()
    finally:
        _load_reading_glossary_instructions.cache_clear()


def test_glossary_prompt_returns_a_word_or_a_name_in_capitals_in_its_normal_spelling():
    instructions = _glossary_instructions()
    bullets = [line for line in instructions.splitlines() if line.startswith("- ") and "имя" in line]
    assert len(bullets) == 1, "one item speaks of a word or a name in capitals"
    item = bullets[0]
    assert "не сокращение" in item and "обычное слово" in item and "заглавными" in item
    assert re.search(r"а не названиями букв", item), "not spelled out by the names of its letters"
    assert re.search(r"обычное слово\s+—\s+строчными", item), "an ordinary word: lower case"
    assert re.search(r"заглавной первой буквы", item), "a name: a capital first letter"
    assert "не строчными целиком" in item, "a name is not written all lower-case"


def test_glossary_prompt_says_candidates_may_be_names():
    intro = next(line for line in _glossary_instructions().splitlines() if '"candidates"' in line)
    assert re.search(r"обычные слова и имена заглавными", intro)


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


# WP-Y: the example teaches the three forms of the rule, one invented case each.
_HEADING_PREFIX = re.compile(r"^#+\s+")
_NUMBER_AFTER_A_WORD = re.compile(r"^([А-ЯЁ][а-яё]+)\s+(\d+(?:\.\d+)*|[IVXLCDM]+)\.?(?=\s|$)")
_ANY_NUMBER = re.compile(r"\d|\b[IVXLCDM]+\b")


def _example_headings() -> list[tuple[str, str]]:
    """``(heading without markup, its result)`` for every heading paragraph of every example pair."""

    headings = []
    for source, result in _example_pairs():
        source_paragraphs, result_paragraphs = _paragraphs(source), _paragraphs(result)
        for marker, text in source_paragraphs.items():
            if _HEADING_PREFIX.match(text):
                headings.append((_HEADING_PREFIX.sub("", text).replace("*", "").strip(), result_paragraphs[marker]))
    return headings


def test_example_keeps_the_word_before_a_heading_number_and_writes_the_number_in_words():
    cases = [(plain, read, match) for plain, read in _example_headings() if (match := _NUMBER_AFTER_A_WORD.match(plain))]
    assert {"roman" if match.group(2).isalpha() else "digits" for _, _, match in cases} == {"roman", "digits"}
    for plain, read, match in cases:
        word = match.group(1)
        assert read.split()[0] == word, f"the word before the number stays first: {read!r}"
        assert [token.lower() for token in read.split()].count(word.lower()) == 1, "the heading is not repeated"
        assert not _NEUTER_ORDINAL_HEAD.match(read), "no neuter ordinal for a number after a word"
        assert not _ANY_NUMBER.search(read), "the number is written in words"
        remainder = plain[match.end() :].strip()
        if remainder:
            assert read.endswith(remainder), "the title after the number is kept"


def test_example_gives_no_number_to_a_heading_without_one():
    cases = [(plain, read) for plain, read in _example_headings() if not _ANY_NUMBER.search(plain)]
    assert cases
    for plain, read in cases:
        assert read == plain, "nothing is added to a heading without a number"
