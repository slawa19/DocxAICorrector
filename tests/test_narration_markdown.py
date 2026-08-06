from collections.abc import Mapping, Sequence
from typing import cast

import pytest

import docxaicorrector.generation._generation as generation
from docxaicorrector.pipeline.narration_postprocess import (
    _NARRATION_REVIEW_SAMPLE_CHARS,
    _collect_narration_artifact_review_findings,
    _summarize_narration_review_findings,
)


def test_strip_markdown_for_narration_removes_markdown_and_placeholders_but_preserves_tags():
    source = (
        "# Chapter 1\n\n"
        "[thoughtful] **Bold** and *italic* text with [link](https://example.com).\n\n"
        "> Quoted line\n\n"
        "1. First item\n"
        "- Second item\n\n"
        "`inline code` [[DOCX_PARA_p0001]] [[DOCX_IMAGE_img_001]]"
    )

    stripped = generation.strip_markdown_for_narration(source)

    assert stripped == (
        "Chapter 1\n\n"
        "[thoughtful] Bold and italic text with link.\n\n"
        "Quoted line\n\n"
        "First item\n"
        "Second item\n\n"
        "inline code"
    )


def test_strip_markdown_for_narration_is_idempotent():
    source = "## Title\n\n[curious] Text with **emphasis** and [link](https://example.com)."

    once = generation.strip_markdown_for_narration(source)
    twice = generation.strip_markdown_for_narration(once)

    assert once == twice


def test_strip_markdown_for_narration_inserts_blank_line_after_heading_when_missing():
    source = "# Title\nNext line"

    stripped = generation.strip_markdown_for_narration(source)

    assert stripped == "Title\n\nNext line"


def test_strip_markdown_for_narration_removes_raw_urls_and_normalizes_internal_whitespace():
    source = "[thoughtful]\tText   with raw URL https://example.com/path and www.example.org\tinside."

    stripped = generation.strip_markdown_for_narration(source)

    assert stripped == "[thoughtful] Text with raw URL and inside."


def test_strip_markdown_for_narration_removes_heading_marker_after_audio_tag():
    source = "[serious] # Introduction\nNext line"

    stripped = generation.strip_markdown_for_narration(source)

    assert stripped == "[serious] Introduction\n\nNext line"


@pytest.mark.parametrize("glyph", ["•", "●", "◦", "‣"])
def test_strip_markdown_for_narration_drops_the_bullet_glyph_and_keeps_the_item_text(glyph):
    """Spec 054: a list-bullet glyph is not speech, and 116 of them reached the 2026-08-04
    narration artifact of Money & Sustainability, where a TTS engine would read them aloud.

    The glyph set is the repository's existing bullet lexicon
    (``output_validation._BULLET_GLYPH_PATTERN``), which is what counted those 116; only
    ``•`` actually occurs in that artifact, the other three ride along on form.
    """
    source = f"{glyph} Компании постоянно балансируют на этих качелях.\n{glyph} Второй пункт."

    stripped = generation.strip_markdown_for_narration(source)

    assert stripped == "Компании постоянно балансируют на этих качелях.\nВторой пункт."


def test_strip_markdown_for_narration_drops_a_bullet_glyph_behind_an_audio_tag():
    """3 of the 116 measured bullets sat behind an ElevenLabs tag ("[serious] • …").

    The tag is a legitimate narration directive and stays; only the marker goes.
    """
    source = "[serious] • ЭКО: национальная система финансирования экологических проектов."

    stripped = generation.strip_markdown_for_narration(source)

    assert stripped == "[serious] ЭКО: национальная система финансирования экологических проектов."


def test_strip_markdown_for_narration_leaves_a_bullet_glyph_welded_inside_a_token():
    """Anti-vacuum: a glyph welded between word characters is data, not a list marker —
    the same distinction ``_WELDED_BULLET_GLYPH_PATTERN`` draws in the quality gate. The
    rule requires a separator after the glyph, so nothing here is touched."""
    source = "Значение 4●5 осталось в тексте."

    assert generation.strip_markdown_for_narration(source) == "Значение 4●5 осталось в тексте."


def test_strip_markdown_for_narration_keeps_prose_that_merely_starts_with_a_dash_word():
    """Anti-vacuum for the whole list rule: an em-dash opening a line of dialogue is not a
    bullet, and the paragraph text is never shortened by the glyph rule."""
    source = "— Декларация 1700 ведущих учёных из 70 стран.\n\nОбычный абзац без маркеров."

    stripped = generation.strip_markdown_for_narration(source)

    assert stripped == "— Декларация 1700 ведущих учёных из 70 стран.\n\nОбычный абзац без маркеров."


def _letters(text: str) -> str:
    return "".join(character for character in text if not character.isspace())


def test_narration_joins_a_sentence_that_runs_across_a_paragraph_break():
    """Spec 054, 2026-08-06. Measured on the four-book corpus: 34 such boundaries, and 81 of
    the 83 arrive from IMPORT, where a PDF line wrap became a paragraph break. Both halves
    are translated and nothing is missing — only the separator is wrong, and a TTS engine
    reads a paragraph break as a pause in the middle of a sentence."""
    source = (
        "Слово «кредит» звучит позитивно — вам доверились и сочли вас\n\n"
        "платежеспособным. Слово «долг» несет негативный оттенок."
    )

    stripped, joined = generation.strip_markdown_for_narration_with_stats(source)

    assert joined == 1
    assert stripped == (
        "Слово «кредит» звучит позитивно — вам доверились и сочли вас "
        "платежеспособным. Слово «долг» несет негативный оттенок."
    )


def test_narration_join_changes_only_the_separator():
    """Nothing is added and nothing is lost: the letter sequence is identical before and
    after, which is what makes the rule checkable rather than merely plausible."""
    source = "первым шагом стало формирование основной\n\nкоманды, в неё вошли жители."

    before = "".join(source.split("\n\n"))
    stripped, joined = generation.strip_markdown_for_narration_with_stats(source)

    assert joined == 1
    assert _letters(stripped) == _letters(before)


def test_narration_does_not_join_a_heading_to_the_prose_under_it():
    """Anti-vacuum. A heading legitimately ends without punctuation, which is exactly the
    shape the rule keys on — so the kind is read off the MARKDOWN, not off the text."""
    source = "## Деньги как соглашение\n\nдоверие внутри сообщества делает их деньгами."

    stripped, joined = generation.strip_markdown_for_narration_with_stats(source)

    assert joined == 0
    assert stripped == "Деньги как соглашение\n\nдоверие внутри сообщества делает их деньгами."


def test_narration_does_not_join_a_heading_that_arrives_behind_an_audio_tag():
    source = "[serious] ### Валюта Терра\n\nсоздаётся из излишков товарных запасов."

    stripped, joined = generation.strip_markdown_for_narration_with_stats(source)

    assert joined == 0
    assert stripped == "[serious] Валюта Терра\n\nсоздаётся из излишков товарных запасов."


@pytest.mark.parametrize(
    "marker",
    ["- ", "1. ", "• ", "[serious] - ", "[serious] • "],
)
def test_narration_does_not_join_a_list_item_to_its_neighbour(marker):
    """Anti-vacuum. Items of a list end without punctuation by convention and the next item
    may well start lowercase; welding them would turn a list into one run-on sentence."""
    source = f"{marker}мера стоимости\n\n{marker}средство обращения"

    _, joined = generation.strip_markdown_for_narration_with_stats(source)

    assert joined == 0


def test_narration_does_not_join_a_blockquote_to_the_paragraph_after_it():
    source = "> цитата без точки\n\nпродолжение обычного абзаца."

    _, joined = generation.strip_markdown_for_narration_with_stats(source)

    assert joined == 0


def test_narration_does_not_join_an_epigraph_attribution_to_what_follows_it():
    """Anti-vacuum, and the case the owner named. An attribution legitimately ends without a
    full stop; what stops the join is that whatever comes next STARTS something — a new
    epigraph, a name, a tag — and therefore does not begin with a lowercase letter. Taken
    verbatim from Rethinking Money's front matter."""
    source = (
        "— Эдгар Кан, создатель Time Dollars, основатель TimeBanks USA\n\n"
        "«Вместо того чтобы просто винить кого-то, авторы предлагают решения»."
    )

    _, joined = generation.strip_markdown_for_narration_with_stats(source)

    assert joined == 0


def test_narration_does_not_join_index_rows():
    """Anti-vacuum. Two independent guards refuse an index row and each was measured to be
    load-bearing on Rethinking Money's 422-paragraph index: the row ends on a PAGE NUMBER,
    and the next row starts on a capital. Allow digit endings and these two rows — the only
    ones on the whole corpus — join."""
    source = "Страх, 4\n\nв Юте, 201; в Веймарской республике, 136"

    _, joined = generation.strip_markdown_for_narration_with_stats(source)

    assert joined == 0


@pytest.mark.parametrize("terminal", [".", "!", "?", "…", ":", ";", "»", "\"", ")"])
def test_narration_does_not_join_after_a_finished_sentence(terminal):
    source = f"Абзац закончился{terminal}\n\nследующий абзац начинается со строчной буквы."

    _, joined = generation.strip_markdown_for_narration_with_stats(source)

    assert joined == 0


def test_narration_does_not_join_when_the_continuation_starts_a_new_speech_unit():
    """An audio tag opens a new delivery unit, so a paragraph starting with one is never the
    tail of the sentence before it."""
    source = "эта программа использует\n\n[thoughtful] тайм-банкинг как основу."

    _, joined = generation.strip_markdown_for_narration_with_stats(source)

    assert joined == 0


def test_narration_join_is_idempotent():
    source = "Смотрите\n\nрисунок 8.4."

    once, first = generation.strip_markdown_for_narration_with_stats(source)
    twice, second = generation.strip_markdown_for_narration_with_stats(once)

    assert (first, second) == (1, 0)
    assert once == twice == "Смотрите рисунок 8.4."


def test_narration_join_count_is_zero_when_nothing_runs_on():
    """Zero is a statement, not an absent measurement (Constitution V)."""
    _, joined = generation.strip_markdown_for_narration_with_stats(
        "Первый абзац закончен.\n\nВторой абзац тоже закончен."
    )

    assert joined == 0


def _rules(narration_text: str) -> list[str]:
    return [str(finding["rule"]) for finding in _collect_narration_artifact_review_findings(narration_text)]


def _samples(finding: Mapping[str, object]) -> list[str]:
    return [str(sample) for sample in cast(Sequence[object], finding["samples"])]


@pytest.mark.parametrize(
    "prose",
    [
        # Spec 054 Finding 4, verbatim: the bare words `isbn` / `arxiv` fired on a book that
        # merely TALKS about publishing. That is narratable prose — nothing to review.
        "Издательство присвоило книге ISBN и отправило её в печать.",
        "Он опубликовал препринт на arXiv…",
    ],
)
def test_narration_review_ignores_prose_that_only_names_an_identifier_scheme(prose):
    assert _collect_narration_artifact_review_findings(prose) == []


@pytest.mark.parametrize(
    ("reference_text", "expected_rule"),
    [
        ("ISBN 978-5-9614-1234-5", "isbn_identifier"),
        ("ISBN 5-9614-1234-X", "isbn_identifier"),
        ("ISBN-13: 9785961412345", "isbn_identifier"),
        ("arXiv:2103.12345", "arxiv_identifier"),
        ("arXiv: 2103.12345v2", "arxiv_identifier"),
        ("arXiv math.GT/0309136", "arxiv_identifier"),
    ],
)
def test_narration_review_still_reports_the_identifier_itself(reference_text, expected_rule):
    """Constitution VII: the rules are keyed on the FORM of the identifier, like `doi`.

    Tightening them from a bare word to the number keeps every real bibliography leak
    visible; what it drops is only the prose that names the scheme.
    """
    assert _rules(f"[thoughtful] Источник: {reference_text}.") == [expected_rule]


@pytest.mark.parametrize(
    "prose",
    [
        "В Веймарской республике (Германия, 1923) деньги обесценивались ежедневно.",
        "Это случилось в тот год (Берлин, 1923 год), когда цены удваивались.",
    ],
)
def test_narration_review_reports_the_imprecise_citation_rule_without_gating(prose):
    """`inline_citation` still fires on plain prose — and that is now ACCEPTED.

    Making it precise would take the name / city / publisher lists Constitution VII
    forbids. Since the finding no longer destroys the artifact, an extra line of review
    data is the agreed price; what must never happen is the run failing over it.
    """
    findings = _collect_narration_artifact_review_findings(prose)

    assert [str(finding["rule"]) for finding in findings] == ["inline_citation"]
    assert findings[0]["match_count"] == 1


def test_narration_review_counts_every_match_and_keeps_a_few_truncated_samples():
    long_citation = "(" + "Мюллер" + "а" * 60 + ", 1923)"
    narration_text = "\n".join(
        [
            "[serious] Первый (Смит, 2019) фрагмент.",
            "Второй (Джонс, 2020) фрагмент.",
            "Третий (Браун, 2021) фрагмент.",
            f"Четвёртый {long_citation} фрагмент.",
        ]
    )

    findings = _collect_narration_artifact_review_findings(narration_text)

    assert len(findings) == 1
    assert findings[0]["rule"] == "inline_citation"
    assert findings[0]["match_count"] == 4
    samples = _samples(findings[0])
    assert samples == ["(Смит, 2019)", "(Джонс, 2020)", "(Браун, 2021)"]
    assert all(len(sample) <= _NARRATION_REVIEW_SAMPLE_CHARS + 1 for sample in samples)


def test_narration_review_truncates_an_oversized_sample_instead_of_logging_the_payload():
    narration_text = "См. https://example.org/" + "a" * 400

    findings = _collect_narration_artifact_review_findings(narration_text)

    assert [str(finding["rule"]) for finding in findings] == ["raw_url"]
    sample = _samples(findings[0])[0]
    assert len(sample) == _NARRATION_REVIEW_SAMPLE_CHARS + 1
    assert sample.endswith("…")


def test_narration_review_reports_non_elevenlabs_tags_as_their_own_finding():
    findings = _collect_narration_artifact_review_findings("[thoughtful] ok [angry] not modelled")

    assert [str(finding["rule"]) for finding in findings] == ["disallowed_tags"]
    assert _samples(findings[0]) == ["[angry]"]


def test_narration_review_is_silent_on_clean_narration():
    assert _collect_narration_artifact_review_findings("[thoughtful] Обычный абзац без маркеров.") == []
    assert _summarize_narration_review_findings([]) == {
        "review_finding_count": 0,
        "review_match_count": 0,
        "review_rules": [],
    }


def test_summarize_narration_review_findings_totals_matches_across_rules():
    findings = _collect_narration_artifact_review_findings(
        "[serious] doi:10.5194/sapiens-2-1, ISBN 978-5-9614-1234-5 и (Смит, 2019)."
    )

    assert _summarize_narration_review_findings(findings) == {
        "review_finding_count": 3,
        "review_match_count": 3,
        "review_rules": ["doi", "isbn_identifier", "inline_citation"],
    }
