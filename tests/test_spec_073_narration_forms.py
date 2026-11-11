"""Spec 073 WP-A (FR-002, SC-005): one set of text forms for every LEXICAL comparison of the narration pass.

A stress mark is a combining mark (Unicode category M*): it belongs to its letter. The comparisons that
read letters -- coverage, the residue classes ``all_caps`` and ``roman_numerals``, the fragment rule and the
context-leakage check -- must give the same answer for a text with the marks and for the same text without
them, while the exact assembly of the narration text stays byte-exact.

Part A of this file is the characterisation of what must NOT change (it is green before any change of the
package); part B is the new behaviour. Every example is invented and carries only the FORM of the real case
(Constitution VII): no book text, no word list.
"""

from __future__ import annotations

import re
import unicodedata

import pytest

from docxaicorrector.document.narration_exclusion import is_fragment_without_connected_text
from docxaicorrector.generation import _generation as generation
from docxaicorrector.pipeline.audiobook_pass import NarrationParagraphRecord
from docxaicorrector.pipeline.narration_postprocess import assemble_narration_records
from docxaicorrector.text.narration_coverage import COVERAGE_REVIEW_THRESHOLD, CoverageResult, paragraph_coverage
from docxaicorrector.text.narration_residue import detect_narration_residue

ACUTE = "́"

# ---------------------------------------------------------------------------------------------------------
# Part A. Characterisation: texts WITHOUT marks behave as they did before spec 073 (T-A1, T-A2).
# ---------------------------------------------------------------------------------------------------------

# The residue classes as they were on ``7347bd3``: the class ``latin`` of WP-C is not part of the snapshot.
_PRE_073_CLASSES = (
    "digits",
    "roman_numerals",
    "symbols",
    "all_caps",
    "url_or_domain",
    "tag_form",
    "html_left",
    "emoji_left",
)

# At least 20 invented paragraphs of the forms the passes meet: prose, capitals, roman numerals, an address,
# digits, Latin script, markup, fragments.
SYNTHETIC_PARAGRAPHS: tuple[str, ...] = (
    "Квазибург стоял на берегу широкой реки, и каждое утро над водой поднимался густой туман.",
    "АЛМАЗНЫЙ ВЕТЕР ПРИШЁЛ С ЗАПАДА",
    "Подробности даны в главе XIV и в разделе III нашего повествования.",
    "Компания Zentrix выпустила новую версию программы в конце прошлого года.",
    "Адрес страницы www.example.test/page указан внизу, а письмо ушло с домена mail.example.test сегодня.",
    "Цена выросла на 15 % за 3 года, а доля достигла 42,5 процента от всего объёма рынка.",
    "[pause] Он замолчал [whisper] и медленно вышел из комнаты, не оглядываясь назад.",
    "<b>Жирный</b> текст остался в абзаце вместе с разметкой, которую никто не убрал.",
    "Да.",
    "11",
    "* * *",
    "(i)",
    "Том Ⅳ вышел позже остальных томов серии и разошёлся быстрее прежних изданий.",
    "XyZ-QW и ABC обозначали две партии, которые различали на складе по маркировке.",
    "Мы шли долго, пока не увидели старый мост, и река осталась позади нас надолго.",
    "ИМЯ ФАМИЛИЯ",
    "Он сказал: «Тише», и все замолчали до самого утра, не двигаясь с места.",
    "Привет 😀 всем, кто дочитал это письмо до самого конца, и до встречи.",
    "Версия v2 вышла под номером 2.0 и содержала ABC-123 для тестирования новых возможностей.",
    "Первое предложение абзаца идёт сразу. Второе предложение абзаца следует за ним. Третье завершает всё.",
    "   ",
    "x² + y² = z² в самом простом виде записи для учебного примера.",
    "Заглавные слова ПЕРВЫЙ ВТОРОЙ ТРЕТИЙ идут подряд, но весь абзац заглавным не является.",
    "Ничего особенного в этом абзаце нет, он просто длинный и состоит из обычных слов подряд.",
)


def _observe_paragraph(index: int, text: str) -> dict[str, object]:
    half = " ".join(text.split()[: max(1, len(text.split()) // 2)])
    coverage_same = paragraph_coverage(text, text)
    coverage_half = paragraph_coverage(text, half)
    residue = tuple(
        (finding.residue_class, finding.count, finding.sample)
        for finding in detect_narration_residue(text)
        if finding.residue_class in _PRE_073_CLASSES
    )
    if index > 0:
        previous = SYNTHETIC_PARAGRAPHS[index - 1]
        leakage = generation._detect_context_leakage(f"{previous} {text}", text, previous, "")
    else:
        leakage = None
    return {
        "coverage_same": (coverage_same.long_word_count, coverage_same.found_count, coverage_same.ratio),
        "coverage_half": (coverage_half.long_word_count, coverage_half.found_count, coverage_half.ratio),
        "residue": residue,
        "fragment": is_fragment_without_connected_text(text),
        "leakage": leakage,
    }


def observe_synthetic_set() -> list[dict[str, object]]:
    return [_observe_paragraph(index, text) for index, text in enumerate(SYNTHETIC_PARAGRAPHS)]


# Recorded on ``7347bd3`` by running ``observe_synthetic_set`` before any change of the package.
SNAPSHOT: list[dict[str, object]] = (
[{'coverage_same': (6, 6, 1.0), 'coverage_half': (6, 3, 0.5), 'residue': (), 'fragment': False, 'leakage': None},
 {'coverage_same': (3, 0, None),
  'coverage_half': (3, 0, None),
  'residue': (('all_caps', 1, 'АЛМАЗНЫЙ ВЕТЕР ПРИШЁЛ С ЗАПАДА'),),
  'fragment': False,
  'leakage': 'Квазибург стоял на берегу широкой реки'},
 {'coverage_same': (4, 4, 1.0),
  'coverage_half': (4, 1, 0.25),
  'residue': (('roman_numerals', 2, 'Подробности даны в главе XIV и в разделе III нашего повествования.'),),
  'fragment': False,
  'leakage': None},
 {'coverage_same': (6, 6, 1.0),
  'coverage_half': (6, 4, 0.6666666666666666),
  'residue': (),
  'fragment': False,
  'leakage': 'Подробности даны в главе XIV и'},
 # Spec 074 FR-403 changed this entry on purpose: the "/" of the address is now a ``symbols`` residue.
 {'coverage_same': (7, 7, 1.0),
  'coverage_half': (7, 4, 0.5714285714285714),
  'residue': (('symbols',
               1,
               'Адрес страницы www.example.test/page указан внизу, а письмо ушло с домена mail.example.test '
               'сегодня.'),
              ('url_or_domain',
               2,
               'Адрес страницы www.example.test/page указан внизу, а письмо ушло с домена mail.example.test '
               'сегодня.'),),
  'fragment': False,
  'leakage': 'Компания Zentrix выпустила новую версию программы'},
 {'coverage_same': (4, 4, 1.0),
  'coverage_half': (4, 1, 0.25),
  'residue': (('digits', 4, 'Цена выросла на 15 % за 3 года, а доля достигла 42,5 процента от всего объёма рынка.'),
              ('symbols', 1, 'Цена выросла на 15 % за 3 года, а доля достигла 42,5 процента от всего объёма рынка.')),
  'fragment': False,
  'leakage': 'Адрес страницы www.example.test/page'},
 {'coverage_same': (5, 5, 1.0),
  'coverage_half': (5, 3, 0.6),
  'residue': (('tag_form', 2, '[pause] Он замолчал [whisper] и медленно вышел из комнаты, не оглядываясь назад.'),),
  'fragment': False,
  'leakage': 'Цена выросла на 15 % за 3'},
 # Spec 074 FR-403: the "/" of the closing tag is a fifth symbol next to the four angle brackets.
 {'coverage_same': (6, 6, 1.0),
  'coverage_half': (6, 4, 0.6666666666666666),
  'residue': (('symbols', 5, '<b>Жирный</b> текст остался в абзаце вместе с разметкой, которую никто не убрал.'),
              ('html_left', 2, '<b>Жирный</b> текст остался в абзаце вместе с разметкой, которую никто не убрал.')),
  'fragment': False,
  'leakage': 'pause] Он замолчал [whisper] и медленно'},
 {'coverage_same': (0, 0, None),
  'coverage_half': (0, 0, None),
  'residue': (),
  'fragment': False,
  'leakage': 'b>Жирный</b> текст остался в'},
 {'coverage_same': (0, 0, None),
  'coverage_half': (0, 0, None),
  'residue': (('digits', 1, '11'),),
  'fragment': True,
  'leakage': None},
 {'coverage_same': (0, 0, None), 'coverage_half': (0, 0, None), 'residue': (), 'fragment': True, 'leakage': None},
 {'coverage_same': (0, 0, None), 'coverage_half': (0, 0, None), 'residue': (), 'fragment': True, 'leakage': None},
 {'coverage_same': (5, 5, 1.0),
  'coverage_half': (5, 1, 0.2),
  'residue': (('roman_numerals', 1, 'Том Ⅳ вышел позже остальных томов серии и разошёлся быстрее прежних изданий.'),),
  'fragment': False,
  'leakage': None},
 {'coverage_same': (6, 6, 1.0),
  'coverage_half': (6, 2, 0.3333333333333333),
  'residue': (),
  'fragment': False,
  'leakage': 'Том Ⅳ вышел позже остальных томов'},
 {'coverage_same': (5, 5, 1.0),
  'coverage_half': (5, 2, 0.4),
  'residue': (),
  'fragment': False,
  'leakage': 'XyZ-QW и ABC обозначали две партии'},
 {'coverage_same': (1, 0, None),
  'coverage_half': (1, 0, None),
  'residue': (),
  'fragment': False,
  'leakage': 'Мы шли долго, пока не увидели'},
 {'coverage_same': (4, 4, 1.0), 'coverage_half': (4, 2, 0.5), 'residue': (), 'fragment': False, 'leakage': None},
 {'coverage_same': (5, 5, 1.0),
  'coverage_half': (5, 2, 0.4),
  'residue': (('emoji_left', 1, 'Привет 😀 всем, кто дочитал это письмо до самого конца, и до встречи.'),),
  'fragment': False,
  'leakage': 'Он сказал: «Тише», и все замолчали'},
 {'coverage_same': (5, 5, 1.0),
  'coverage_half': (5, 2, 0.4),
  'residue': (('digits',
               4,
               'Версия v2 вышла под номером 2.0 и содержала ABC-123 для тестирования новых возможностей.'),),
  'fragment': False,
  'leakage': 'Привет 😀 всем, кто дочитал это письмо'},
 {'coverage_same': (9, 9, 1.0),
  'coverage_half': (9, 6, 0.6666666666666666),
  'residue': (),
  'fragment': False,
  'leakage': 'Версия v2 вышла под номером 2'},
 {'coverage_same': (0, 0, None),
  'coverage_half': (0, 0, None),
  'residue': (),
  'fragment': True,
  'leakage': 'Первое предложение абзаца идёт сразу. Второе'},
 {'coverage_same': (4, 4, 1.0),
  'coverage_half': (4, 0, 0.0),
  'residue': (('digits', 3, 'x² + y² = z² в самом простом виде записи для учебного примера.'),
              ('symbols', 2, 'x² + y² = z² в самом простом виде записи для учебного примера.')),
  'fragment': False,
  'leakage': None},
 {'coverage_same': (7, 7, 1.0),
  'coverage_half': (7, 5, 0.7142857142857143),
  'residue': (),
  'fragment': False,
  'leakage': 'x² + y² = z² в самом простом'},
 {'coverage_same': (8, 8, 1.0),
  'coverage_half': (8, 3, 0.375),
  'residue': (),
  'fragment': False,
  'leakage': 'Заглавные слова ПЕРВЫЙ ВТОРОЙ ТРЕТИЙ идут'}])


def test_the_synthetic_set_is_large_enough() -> None:
    assert len(SYNTHETIC_PARAGRAPHS) >= 20
    assert not any(unicodedata.category(char).startswith("M") for text in SYNTHETIC_PARAGRAPHS for char in text)


def test_texts_without_marks_behave_as_before_spec_073() -> None:
    assert observe_synthetic_set() == SNAPSHOT


class _LossyOnFirstStrip(str):
    """A record text whose first ``strip()`` loses the marks, like an assembly that drops them: the
    assembled paragraph then differs from the record text read back by the check."""

    def __new__(cls, value: str):
        instance = super().__new__(cls, value)
        instance._calls = 0
        return instance

    def strip(self, chars=None):  # type: ignore[override]
        self._calls += 1
        value = str.strip(self, chars)
        if self._calls == 1:
            return "".join(char for char in value if not unicodedata.category(char).startswith("M"))
        return value


def _record(paragraph_id: str, text: str) -> NarrationParagraphRecord:
    return NarrationParagraphRecord(
        paragraph_id=paragraph_id,
        block_index=1,
        role="body",
        text=text,
        needs_review_reasons=(),
        residue_before=(),
        residue_after=(),
        coverage=CoverageResult(0, 0, None),
    )


def test_exact_assembly_keeps_a_stress_mark_and_sees_its_loss() -> None:
    marked = f"за{ACUTE}мок стоял на холме"
    intact = assemble_narration_records([_record("p1", marked)])
    assert intact.text == marked
    assert intact.boundary_check == "ok"

    lost = assemble_narration_records([_record("p1", _LossyOnFirstStrip(marked))])
    assert lost.text == "замок стоял на холме"
    assert lost.boundary_check == "mismatch"
    assert lost.first_mismatch_paragraph_id == "p1"


# ---------------------------------------------------------------------------------------------------------
# Part B. New behaviour (T-A3 .. T-A7). The shared module is imported inside the tests, so that part A keeps
# running on a tree where the module does not exist yet.
# ---------------------------------------------------------------------------------------------------------

_WORD = re.compile(r"[^\W\d_]+")


def _forms():
    from docxaicorrector.text import narration_forms

    return narration_forms


def _without_marks_reference(text: str) -> str:
    return "".join(char for char in text if not unicodedata.category(char).startswith("M"))


def _mark_long_words(text: str, *, after: int = 2) -> str:
    """The text with a stress mark inside every word of six letters or more (after its ``after``-th
    letter): the way a model returns a narration paragraph (FR-001)."""

    def put(match: re.Match[str]) -> str:
        word = match.group(0)
        return word if len(word) < 6 else word[:after] + ACUTE + word[after:]

    return _WORD.sub(put, text)


_MARK_INPUTS = (
    f"за{ACUTE}мок",
    f"e{ACUTE}̂x",
    "",
    "ABC",
    "Ж⃝З",
    ACUTE,
    f"{ACUTE}а",
    f"сло{ACUTE}во и ещё{ACUTE} одно{ACUTE}",
)


def test_without_combining_marks_is_the_former_helper() -> None:
    forms = _forms()
    for text in _MARK_INPUTS:
        assert forms.without_combining_marks(text) == _without_marks_reference(text)
    assert forms.without_combining_marks("ABC без знаков") == "ABC без знаков"
    # the exclusion module reads the same helper under its former name
    from docxaicorrector.document import narration_exclusion

    assert narration_exclusion._without_combining_marks is forms.without_combining_marks


def test_offsets_point_at_the_original_characters() -> None:
    forms = _forms()
    for text in _MARK_INPUTS:
        stripped, offsets = forms.without_combining_marks_with_offsets(text)
        assert stripped == _without_marks_reference(text)
        assert len(offsets) == len(stripped)
        assert all(stripped[index] == text[offsets[index]] for index in range(len(stripped)))
        assert list(offsets) == sorted(set(offsets))


def test_original_span_gives_the_mark_to_its_letter() -> None:
    forms = _forms()
    text = f"за{ACUTE}мок"
    stripped, offsets = forms.without_combining_marks_with_offsets(text)
    assert stripped == "замок"
    # the end of a span that stops right after a marked letter is carried through its mark
    start, end = forms.original_span(text, offsets, 0, 2)
    assert text[start:end] == f"за{ACUTE}"
    # a span that starts after the mark, up to the end of the text
    start, end = forms.original_span(text, offsets, 2, 5)
    assert text[start:end] == "мок"
    assert forms.original_span(text, offsets, 0, 5) == (0, len(text))
    # an empty span stays empty
    start, end = forms.original_span(text, offsets, 2, 2)
    assert start == end


def test_letter_series_keeps_a_marked_word_whole() -> None:
    forms = _forms()
    text = f"за{ACUTE}мок и дом"
    series = forms.letter_series(text)
    assert [unit.text for unit in series] == [f"за{ACUTE}мок", "и", "дом"]
    assert all(text[unit.start : unit.end] == unit.text for unit in series)


def test_letter_series_trims_hyphens_and_apostrophes_at_the_edges() -> None:
    forms = _forms()
    for source, expected in (
        ("-слово-", ["слово"]),
        ("«‐слово‑»", ["слово"]),
        ("'quoted' и dont'", ["quoted", "и", "dont"]),
        ("кое-что и кое‐как", ["кое-что", "и", "кое‐как"]),
        ("don't и don’t", ["don't", "и", "don’t"]),
        ("-- ' - 12", []),
    ):
        series = forms.letter_series(source, digits_inside=True)
        assert [unit.text for unit in series] == expected, source
        assert all(source[unit.start : unit.end] == unit.text for unit in series)


def test_letter_series_takes_digits_only_when_asked_and_never_superscripts() -> None:
    forms = _forms()
    assert [unit.text for unit in forms.letter_series("код XY-12 готов")] == ["код", "XY", "готов"]
    assert [unit.text for unit in forms.letter_series("код XY-12 готов", digits_inside=True)] == ["код", "XY-12", "готов"]
    assert [unit.text for unit in forms.letter_series("номер 12 и 7", digits_inside=True)] == ["номер", "и"]
    assert [unit.text for unit in forms.letter_series("ЖЗИ⁷ и ABC²", digits_inside=True)] == ["ЖЗИ", "и", "ABC"]


def test_stress_marks_do_not_change_coverage_residue_or_leakage() -> None:
    """SC-005: the same paragraph with and without a stress mark in each long word."""

    plain = "Путешественник приехал рано утром, хозяйка встретила гостя, библиотека находилась рядом."
    marked = _mark_long_words(plain)
    assert marked != plain
    # the form the measure needs: >= 4 long words and >= 6 tokens
    assert len([word for word in _WORD.findall(plain) if len(word) >= 6]) >= 4
    assert len(plain.split()) >= 6

    baseline = paragraph_coverage(plain, plain)
    assert baseline.ratio == 1.0
    for source, answer in ((plain, marked), (marked, plain), (marked, marked)):
        assert paragraph_coverage(source, answer) == baseline

    caps = "ГЛАВА IV: СТАРЫЙ ЗАМОК СТОЯЛ НА ВЫСОКОМ ХОЛМЕ"
    marked_caps = _mark_long_words(caps, after=1).replace("IV", f"I{ACUTE}V")
    assert marked_caps != caps

    def projection(text: str) -> set[tuple[str, int]]:
        return {(finding.residue_class, finding.count) for finding in detect_narration_residue(text)}

    assert projection(caps) == {("roman_numerals", 1), ("all_caps", 1)}
    assert projection(marked_caps) == projection(caps)

    context = "эту книгу взяли многие читатели вчера"
    target = "Исправленный блок."
    plain_response = f"{target} {context.capitalize()}"
    marked_response = _mark_long_words(plain_response)
    plain_leak = generation._detect_context_leakage(plain_response, target, context, "")
    assert plain_leak is not None
    marked_leak = generation._detect_context_leakage(marked_response, target, context, "")
    assert marked_leak is not None
    assert _without_marks_reference(marked_leak) == plain_leak
    # and the other way round: the context carries the marks, the answer does not
    assert generation._detect_context_leakage(plain_response, target, _mark_long_words(context), "") == plain_leak


def test_a_really_lost_sentence_is_caught_with_and_without_marks() -> None:
    sentences = [
        "Путешественник приехал рано.",
        "Хозяйка встретила гостя.",
        "Библиотека находилась рядом, коридор вёл налево.",
        "Лестница поднималась медленно, скрипели ступени, потолок нависал, фонари мерцали, окошки запотели, сквозняки гуляли.",
        "Утром выпал снег.",
    ]
    source = " ".join(sentences)
    lost = " ".join(sentences[:3] + sentences[4:])
    complete_marked = paragraph_coverage(source, _mark_long_words(source))
    lost_plain = paragraph_coverage(source, lost)
    lost_marked = paragraph_coverage(source, _mark_long_words(lost))
    assert complete_marked.ratio == 1.0
    assert lost_plain.ratio is not None and lost_plain.ratio < COVERAGE_REVIEW_THRESHOLD
    assert lost_marked == lost_plain


def test_all_caps_and_roman_forms_read_the_text_without_marks() -> None:
    caps_marked = f"А{ACUTE}ЛМАЗ ВЕ{ACUTE}ТЕР"
    findings = {finding.residue_class: finding for finding in detect_narration_residue(caps_marked)}
    assert "all_caps" in findings
    assert findings["all_caps"].sample == caps_marked  # the slice of the ORIGINAL string, marks included
    roman = {finding.residue_class: finding for finding in detect_narration_residue(f"глава I{ACUTE}V")}
    assert roman["roman_numerals"].count == 1


def test_residue_sample_is_a_slice_of_the_original_string_at_the_original_position() -> None:
    prefix = (f"за{ACUTE}мок " * 14).strip() + " "
    text = prefix + f"глава I{ACUTE}V и ещё несколько слов после неё в конце абзаца"
    findings = {finding.residue_class: finding for finding in detect_narration_residue(text)}
    position = text.index(f"I{ACUTE}V")
    assert position > 60  # the sample window does not start at 0, so a shifted position is visible
    assert findings["roman_numerals"].sample == text[position - 40 : position - 40 + 120]
    assert ACUTE in findings["roman_numerals"].sample


def test_leaked_fragment_is_a_slice_of_the_marked_answer_and_is_trimmed() -> None:
    context = "эту книгу взяли многие читатели вчера"
    target = "Исправленный блок."
    answer = _mark_long_words(f"{target} {context.capitalize()}")
    fragment = generation._detect_context_leakage(answer, target, context, "")
    assert fragment is not None
    assert fragment in answer
    assert ACUTE in fragment
    trimmed, changed = generation._trim_boundary_context_leakage(answer, fragment)
    assert changed is True
    assert fragment not in trimmed
    assert trimmed.startswith(_mark_long_words("Исправленный блок"))


def test_public_forms_for_the_residue_class_and_the_dictionary() -> None:
    from docxaicorrector.text import narration_residue as residue

    assert residue.is_all_caps_paragraph("АЛМАЗНЫЙ ВЕТЕР") is True
    assert residue.is_all_caps_paragraph(f"А{ACUTE}ЛМАЗ ВЕ{ACUTE}ТЕР") is True
    assert residue.is_all_caps_paragraph("Обычный текст абзаца") is False
    assert residue.is_all_caps_paragraph("") is False

    for token in ("IV", "XIV", "MCM", "Ⅳ", "ⅣⅤ", f"I{ACUTE}V"):
        assert residue.is_roman_numeral_form(token) is True, token
    for token in ("I", "V", "IVa", "Ab", "XyZ", "ABC", "", "12", "Ⅳa"):
        assert residue.is_roman_numeral_form(token) is False, token

    source = "Письмо на mail.example.test ушло, см. www.example.test/page и всё."
    masked = residue.mask_url_or_domain(source)
    assert len(masked) == len(source)
    assert "example" not in masked
    assert masked.startswith("Письмо на ") and masked.endswith(" и всё.")
    assert residue.mask_url_or_domain("Обычный текст без адреса.") == "Обычный текст без адреса."
    assert not any(finding.residue_class == "url_or_domain" for finding in detect_narration_residue(masked))


def test_scene_break_forms_of_the_exclusion_module() -> None:
    from docxaicorrector.document import narration_exclusion as exclusion

    for text in ("", "   ", "***", "# %", "— — —", "\n"):
        assert exclusion.has_no_letter_or_digit(text) is True, repr(text)
    for text in ("1", "I", "Да", "* 1 *", "ж"):
        assert exclusion.has_no_letter_or_digit(text) is False, repr(text)

    for text in ("***", "# %", "— — —", "  * * *  "):
        assert exclusion.is_scene_break_text(text) is True, repr(text)
    for text in ("", "   ", "\n", "1", "I", "Да.", "* 1 *"):
        assert exclusion.is_scene_break_text(text) is False, repr(text)


@pytest.mark.parametrize(
    ("char", "expected"),
    [
        ("a", True),
        ("Z", True),
        ("é", True),
        ("я", False),
        ("α", False),
        ("1", False),
        ("-", False),
        ("Ⅳ", False),
        (ACUTE, False),
        ("", False),
        ("ab", False),
    ],
)
def test_is_latin_letter(char: str, expected: bool) -> None:
    assert _forms().is_latin_letter(char) is expected
