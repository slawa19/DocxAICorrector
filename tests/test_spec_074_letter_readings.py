"""Spec 074 FR-303...FR-305: a purely letter-by-letter reading of an abbreviation follows ONE convention.

Every text here is of the FORM the rule reads (Constitution VII): the two-to-four-letter abbreviations are the
generic ones the spec records as its synthetic acceptance cases (``USB``, ``PDF``, ``JPEG``, ...) or generated
spellings of letters; the readings are the letter names of an alphabet. The alphabet tables below are the
ORACLE of the tests, written out here independently of the code (an alphabet is a closed set, not a word list).
The model is never called: every call goes to a double of ``request_text_completion``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

# ---------------------------------------------------------------------------------------------
# Oracle: the convention (spec 074, "Решение о соглашении названий латинских букв")
# ---------------------------------------------------------------------------------------------

# Latin letters: English names written in Cyrillic (the canonical name first, accepted variants after).
ENGLISH = {
    "A": ("эй",), "B": ("би",), "C": ("си",), "D": ("ди",), "E": ("и",), "F": ("эф",), "G": ("джи",), "H": ("эйч",),
    "I": ("ай",), "J": ("джей",), "K": ("кей", "кэй"), "L": ("эл", "эль"), "M": ("эм",), "N": ("эн",), "O": ("о", "оу"),
    "P": ("пи",), "Q": ("кью",), "R": ("ар", "эр"), "S": ("эс",), "T": ("ти",), "U": ("ю",), "V": ("ви",),
    "W": ("дабл-ю",), "X": ("экс", "икс"), "Y": ("уай",), "Z": ("зед", "зи"),
}
# The school / German names of Latin letters that the convention does NOT accept.
SCHOOL = {
    "A": "а", "B": "бэ", "C": "цэ", "D": "дэ", "E": "е", "G": "гэ", "H": "ха", "I": "и", "J": "йот", "K": "ка",
    "P": "пэ", "Q": "ку", "T": "тэ", "U": "у", "V": "вэ", "W": "вэ", "Y": "игрек", "Z": "зэт",
}
# Cyrillic letters: Russian names.
RUSSIAN = {
    "А": ("а",), "Б": ("бэ",), "В": ("вэ",), "Г": ("гэ",), "Д": ("дэ",), "Е": ("е",), "Ё": ("ё",), "Ж": ("жэ", "же"),
    "З": ("зэ",), "И": ("и",), "К": ("ка",), "Л": ("эль", "эл"), "М": ("эм",), "Н": ("эн",), "О": ("о",), "П": ("пэ",),
    "Р": ("эр",), "С": ("эс",), "Т": ("тэ",), "У": ("у",), "Ф": ("эф",), "Х": ("ха",), "Ц": ("цэ",), "Ч": ("че", "чэ"),
    "Ш": ("ша",), "Щ": ("ща",), "Ы": ("ы",), "Э": ("э",), "Ю": ("ю",), "Я": ("я",),
}

STRESS = "́"


# ---------------------------------------------------------------------------------------------
# Doubles (the shape of tests/test_spec_073_reading_glossary.py)
# ---------------------------------------------------------------------------------------------


def _sent(*spellings: str) -> list[Any]:
    from docxaicorrector.pipeline.reading_glossary import ReadingCandidate

    return [ReadingCandidate(abbreviation=item, occurrences=1, first_block_index=1, context="", sent=True) for item in spellings]


def _parse(abbreviation: str, reading: str):
    from docxaicorrector.pipeline.reading_glossary import parse_reading_glossary_response

    return parse_reading_glossary_response(
        json.dumps({"readings": [{"abbreviation": abbreviation, "reading": reading}]}, ensure_ascii=False),
        sent=_sent(abbreviation),
    )


def _accepted_reading(abbreviation: str, reading: str) -> str:
    entries, rejected = _parse(abbreviation, reading)
    assert not any(rejected.values()), rejected
    (entry,) = entries
    return entry.reading


class _Log:
    def __init__(self) -> None:
        self.events: list[tuple[int, str, dict[str, object]]] = []

    def __call__(self, level: int, event: str, message: str, **context: object) -> str:
        self.events.append((level, event, dict(context)))
        return "evt"

    def named(self, event: str) -> list[tuple[int, str, dict[str, object]]]:
        return [item for item in self.events if item[1] == event]


class _Artifacts:
    def __init__(self) -> None:
        self.written: list[dict[str, object]] = []

    def __call__(self, payload: dict[str, object], *, context: object) -> str:
        self.written.append(json.loads(json.dumps(payload, ensure_ascii=False)))
        return f"/fake/run_glossaries/artifact_{len(self.written)}.json"


class _Completion:
    def __init__(self, readings: dict[str, str]) -> None:
        self.readings = readings
        self.calls: list[dict[str, object]] = []

    def __call__(self, client: object, request: dict[str, object], *, usage_stage: str, should_stop: object = None) -> str:
        self.calls.append(dict(request))
        user = cast(list[dict[str, Any]], request["input"])[1]
        items = json.loads(user["content"][0]["text"])["candidates"]
        return json.dumps(
            {"readings": [{"abbreviation": item["abbreviation"], "reading": self.readings[item["abbreviation"]]} for item in items]},
            ensure_ascii=False,
        )


def _run(text: str, readings: dict[str, str]):
    from docxaicorrector.pipeline.reading_glossary import ReadingParagraph, run_reading_glossary

    completion = _Completion(readings)
    log = _Log()
    artifacts = _Artifacts()
    glossary = run_reading_glossary(
        paragraphs=[ReadingParagraph(paragraph_id="p1", block_index=1, text=text)],
        client=object(),
        model_id="model-x",
        max_retries=3,
        should_stop=lambda: False,
        log_event=log,
        filename="book.docx",
        artifact_context=SimpleNamespace(run_id="run-7", source_token="tok"),
        request_text_completion_fn=completion,
        sleep_fn=lambda seconds: None,
        write_artifact_fn=artifacts,
    )
    return glossary, completion, log, artifacts


# ---------------------------------------------------------------------------------------------
# Characterisation: what must NOT change (passes before and after the change)
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("abbreviation", "reading"),
    [
        ("JPEG", "джей-пег"),  # syllabic: letters then a word
        ("ESOP", "и-соп"),  # a word read by syllables
        ("NY", "Нью-Йорк"),  # an expansion
        ("OECD", "о-э-с-дэ"),  # mixed: the third part is no name of the third letter
        ("ABC", "ка-вэ"),  # two parts for three letters
        ("ABC", "ка‐вэ"),  # a typographic hyphen, two parts for three letters
        ("QXZ", "кувэ́"),  # one word with a stress mark
        ("QXZ", "два слова"),  # a reading with a space
        ("USB", "Универсальная Последовательная Шина"),  # an expansion
        ("ESOP", "Эй-би-си-ди"),  # four parts, none is a name of its letter
    ],
)
def test_reading_that_is_not_purely_letter_by_letter_is_accepted_exactly_as_the_model_wrote_it(abbreviation, reading):
    entries, rejected = _parse(abbreviation, reading)

    assert [entry.reading for entry in entries] == [reading]
    assert not any(rejected.values())


@pytest.mark.parametrize(
    ("abbreviation", "reading"),
    [
        ("USB", "ю-эс-би"),
        ("IBM", "ай-би-эм"),
        ("NHS", "эн-эйч-эс"),
        ("ABC", "эй-би-си"),
    ],
)
def test_reading_already_in_the_convention_is_untouched(abbreviation, reading):
    assert _accepted_reading(abbreviation, reading) == reading


@pytest.mark.parametrize(
    ("abbreviation", "reading"),
    [
        ("Q1", "ку-один"),  # digits are out of scope
        ("Q-X", "ку-икс"),  # a hyphen in the spelling is out of scope
        ("CO2", "цэ-о-два"),
        ("B2B", "би-ту-би"),
    ],
)
def test_spelling_with_a_digit_or_a_hyphen_is_never_touched(abbreviation, reading):
    assert _accepted_reading(abbreviation, reading) == reading


def test_the_rejection_reasons_are_the_same_set():
    from docxaicorrector.pipeline.reading_glossary import READING_REJECTION_REASONS

    assert READING_REJECTION_REASONS == (
        "not_a_candidate", "empty_reading", "latin_in_reading", "digit_in_reading", "not_cyrillic_reading", "duplicate",
    )


def test_a_letter_reading_that_the_form_refuses_is_still_refused_for_its_own_reason():
    entries, rejected = _parse("ABC", "эй-би-си-ex")

    assert entries == ()
    assert rejected["latin_in_reading"] == 1 and sum(rejected.values()) == 1


def test_a_run_over_words_only_has_one_call_and_nothing_normalised_in_the_artifact():
    glossary, completion, _log, artifacts = _run("Слово ABC и XYZ.", {"ABC": "чтение", "XYZ": "Эксуайзед"})

    assert len(completion.calls) == 1
    assert glossary.rerequested == () and glossary.unresolved == ()
    readings = cast(list[dict[str, object]], artifacts.written[0]["readings"])
    assert [(item["abbreviation"], item["reading"]) for item in readings] == [("ABC", "чтение"), ("XYZ", "Эксуайзед")]


# ---------------------------------------------------------------------------------------------
# FR-303: the purely letter-by-letter reading is rewritten to the convention
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("abbreviation", "reading", "expected"),
    [
        ("USB", "у-эс-бэ", "ю-эс-би"),  # spec: «у-эс-бэ» → «ю-эс-би»
        ("PDF", "пэ-дэ-эф", "пи-ди-эф"),  # spec: «пэ-дэ-эф» → «пи-ди-эф»
        ("ЦРУ", "Цэ-эр-у" + STRESS, "цэ-эр-у"),  # spec: only case and stress change
        ("QZV", "ку-зэт-вэ", "кью-зед-ви"),
        ("VW", "фау-вэ", "ви-дабл-ю"),  # spec: the school/German name of V and W, a two-word name «дабл-ю»
        ("XYW", "икс-игрек-дубль-вэ", "икс-уай-дабл-ю"),  # «икс» is accepted for X; the rest is replaced
        ("GE", "гэ-е", "джи-и"),
    ],
)
def test_purely_letter_by_letter_reading_is_rewritten_to_the_convention(abbreviation, reading, expected):
    assert _accepted_reading(abbreviation, reading) == expected


def test_w_is_one_part_even_though_its_name_has_a_hyphen():
    assert _accepted_reading("WU", "дабл-ю-ю") == "дабл-ю-ю"
    assert _accepted_reading("UW", "у-вэ") == "ю-дабл-ю"
    assert _accepted_reading("WW", "вэ-вэ") == "дабл-ю-дабл-ю"


def test_every_latin_letter_the_convention_does_not_accept_is_replaced_by_its_english_name():
    for letter, school in SCHOOL.items():
        english = ENGLISH[letter][0]
        assert _accepted_reading(letter + "M", f"{school}-эм") == f"{english}-эм", letter
        assert _accepted_reading("M" + letter, f"эм-{school}") == f"эм-{english}", letter


def test_every_accepted_variant_of_a_latin_letter_is_kept():
    for letter, names in ENGLISH.items():
        for name in names:
            assert _accepted_reading(letter + "M", f"{name}-эм") == f"{name}-эм", (letter, name)


def test_every_cyrillic_letter_is_read_by_its_russian_name_and_the_variants_are_kept():
    for letter, names in RUSSIAN.items():
        for name in names:
            assert _accepted_reading(letter + "М", f"{name}-эм") == f"{name}-эм", (letter, name)
            assert _accepted_reading(letter + "М", f"{name.capitalize()}{STRESS}-эм") == f"{name}-эм", (letter, name)


def test_a_latin_name_is_no_name_of_a_cyrillic_letter_so_the_reading_is_not_purely_letter_by_letter():
    # «эй» / «би» are names of Latin letters: for the Cyrillic «А» and «Б» the reading is not letter-by-letter
    # in the alphabet of the spelling, so it is left as the model wrote it.
    assert _accepted_reading("АБ", "эй-би") == "эй-би"


def test_a_mixed_script_spelling_takes_the_table_of_each_letter():
    # Latin «A» and Cyrillic «Б» in one spelling: the English name for the first, the Russian one for the second.
    assert _accepted_reading("AБ", "а-бэ") == "эй-бэ"


def test_one_wrong_part_of_a_reading_that_is_not_letter_names_keeps_the_whole_reading():
    # The third part «си» is a name of C, but the second part «соп» is no letter name at all.
    assert _accepted_reading("ABCD", "эй-соп-си-ди") == "эй-соп-си-ди"


def test_the_rewrite_is_lowercase_without_stress_and_with_ascii_hyphens():
    assert _accepted_reading("ABC", f"Э{STRESS}й‐Би‑Си") == "эй-би-си"


def test_the_entry_remembers_the_reading_of_the_model_only_when_it_was_rewritten():
    entries, _ = _parse("PDF", "Пэ-дэ-эф")
    (rewritten,) = entries
    assert rewritten.reading == "пи-ди-эф"
    assert rewritten.model_reading == "Пэ-дэ-эф"

    entries, _ = _parse("PDF", "пи-ди-эф")
    (untouched,) = entries
    assert untouched.model_reading is None

    entries, _ = _parse("JPEG", "джей-пег")
    (syllabic,) = entries
    assert syllabic.model_reading is None


def test_reading_entry_keeps_its_two_positional_fields():
    from docxaicorrector.pipeline.reading_glossary import ReadingEntry

    entry = ReadingEntry("ABC", "эй-би-си")

    assert (entry.abbreviation, entry.reading) == ("ABC", "эй-би-си")


def test_duplicates_and_other_rejections_are_counted_as_before_around_a_rewritten_entry():
    from docxaicorrector.pipeline.reading_glossary import parse_reading_glossary_response

    answer = json.dumps(
        {
            "readings": [
                {"abbreviation": "PDF", "reading": "пэ-дэ-эф"},
                {"abbreviation": "PDF", "reading": "другое"},
                {"abbreviation": "USB", "reading": "латиница-usb"},
            ]
        },
        ensure_ascii=False,
    )
    entries, rejected = parse_reading_glossary_response(answer, sent=_sent("PDF", "USB"))

    assert [(entry.abbreviation, entry.reading) for entry in entries] == [("PDF", "пи-ди-эф")]
    assert rejected["duplicate"] == 1 and rejected["latin_in_reading"] == 1


# ---------------------------------------------------------------------------------------------
# FR-305: the account, no new request, no spelling in the log
# ---------------------------------------------------------------------------------------------


def test_the_built_event_counts_the_rewritten_entries_and_makes_no_new_call():
    glossary, completion, log, artifacts = _run(
        "Слово USB, PDF и ESOP, а также QXZ.",
        {"USB": "у-эс-бэ", "PDF": "пи-ди-эф", "ESOP": "и-соп", "QXZ": "чтение"},
    )

    assert len(completion.calls) == 1
    assert glossary.rerequested == () and glossary.unresolved == ()
    assert glossary.letter_reading_normalized_count == 1
    (built,) = log.named("audiobook_reading_glossary_built")
    assert built[0] == logging.INFO
    assert built[2]["letter_reading_normalized_count"] == 1
    assert built[2]["rerequested_count"] == 0 and built[2]["call_count"] == 1
    assert built[2]["rejected_by_reason"] == {
        "not_a_candidate": 0, "empty_reading": 0, "latin_in_reading": 0, "digit_in_reading": 0,
        "not_cyrillic_reading": 0, "duplicate": 0,
    }
    rendered = json.dumps(log.events, ensure_ascii=False)
    for forbidden in ("USB", "PDF", "ESOP", "у-эс-бэ", "ю-эс-би", "джей"):
        assert forbidden not in rendered


def test_the_artifact_keeps_the_model_reading_next_to_the_accepted_one_for_a_rewritten_entry_only():
    _glossary, _completion, _log, artifacts = _run("Слово USB и ESOP.", {"USB": "у-эс-бэ", "ESOP": "и-соп"})

    readings = {item["abbreviation"]: item for item in cast(list[dict[str, object]], artifacts.written[0]["readings"])}
    assert readings["USB"]["reading"] == "ю-эс-би"
    assert readings["USB"]["model_reading"] == "у-эс-бэ"
    assert readings["ESOP"] == {"abbreviation": "ESOP", "reading": "и-соп"}


def test_the_block_receives_the_rewritten_reading():
    from docxaicorrector.pipeline.reading_glossary import reading_section_for_block

    glossary, *_ = _run("Слово USB.", {"USB": "у-эс-бэ"})
    section = reading_section_for_block(glossary, ["Здесь USB."])

    assert "ю-эс-би" in section and "у-эс-бэ" not in section


def test_the_event_field_is_zero_for_a_book_without_candidates():
    glossary, completion, log, _artifacts = _run("Обычный текст без сокращений.", {})

    assert completion.calls == []
    assert glossary.letter_reading_normalized_count == 0
    (built,) = log.named("audiobook_reading_glossary_built")
    assert built[2]["letter_reading_normalized_count"] == 0


def test_the_field_is_registered_in_the_logging_document():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "LOGGING_AND_ARTIFACT_RETENTION.md").read_text(encoding="utf-8")
    start = text.index("`audiobook_reading_glossary_built`")
    assert "letter_reading_normalized_count" in text[start : start + 900]


# ---------------------------------------------------------------------------------------------
# FR-304: the prompt names the convention
# ---------------------------------------------------------------------------------------------


def test_the_glossary_prompt_names_the_letter_name_convention():
    root = Path(__file__).resolve().parents[1]
    prompt = (root / "src" / "docxaicorrector" / "resources" / "prompts" / "audiobook_reading_glossary.txt").read_text(
        encoding="utf-8"
    )
    line = next(item for item in prompt.splitlines() if "по буквам" in item)

    assert "кириллические буквы" in line and "русскими названиями" in line
    assert "латинские" in line and "английскими названиями" in line and "кириллицей" in line
    assert "строчными" in line and "ударения" in line
    assert "названия букв по-русски" not in prompt
