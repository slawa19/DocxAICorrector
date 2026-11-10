"""The narration text: per-paragraph cleanup, assembly by id and role, and the review data.

Spec 070 (research R8) replaced the Markdown-reading stripper of specs 031/054
(``generation.strip_markdown_for_narration*``) with two pieces, and this module's behavioural
cases moved with them -- the ones that are still right, verbatim:

* ``text.narration_cleanup.clean_narration_paragraph`` cleans ONE paragraph (the paragraph is
  the unit, addressed by its id; it is never re-found in a joined text);
* ``pipeline.narration_postprocess.assemble_narration_records`` joins the records by id and
  closes a sentence torn across a paragraph break -- by FORM, between two paragraphs whose
  preparation ROLE is ``body`` (no longer by the Markdown the model returned).

What changed on purpose: intonation tags no longer exist (D-3), so the tag cases are gone; a
numbered-list marker is no longer cut by code (FR-005: a year must survive, numbers are the
model's job); a raw URL is no longer deleted by code (O-7: the residue detector reports it).
"""

from collections.abc import Mapping, Sequence
from typing import cast

import pytest

from docxaicorrector.pipeline.audiobook_pass import NarrationParagraphRecord
from docxaicorrector.pipeline.narration_postprocess import (
    _NARRATION_REVIEW_SAMPLE_CHARS,
    _collect_narration_artifact_review_findings,
    _summarize_narration_review_findings,
    assemble_narration_records,
)
from docxaicorrector.text.narration_cleanup import clean_narration_paragraph
from docxaicorrector.text.narration_coverage import CoverageResult
from docxaicorrector.text.narration_residue import detect_narration_residue


def _clean(text: str) -> str:
    return clean_narration_paragraph(text).text


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("# Chapter 1", "Chapter 1"),
        ("**Bold** and *italic* text with [link](https://example.com).", "Bold and italic text with link."),
        ("> Quoted line", "Quoted line"),
        ("- Second item", "Second item"),
        ("`inline code` [[DOCX_PARA_p0001]] [[DOCX_IMAGE_img_001]]", "inline code"),
    ],
)
def test_cleanup_removes_markdown_and_pipeline_tokens_from_one_paragraph(source, expected):
    assert _clean(source) == expected


def test_cleanup_is_idempotent():
    source = "## Title with **emphasis** and [link](https://example.com)."

    once = _clean(source)

    assert _clean(once) == once


def test_cleanup_leaves_a_numbered_list_marker_to_the_model():
    """FR-005: ``1990. …`` must keep its year; numbers are rewritten by the model."""
    assert _clean("1. First item") == "1. First item"


def test_cleanup_keeps_a_raw_url_and_the_detector_reports_it():
    """O-7: deleting the URL by code made the ``url_or_domain`` class unreachable."""
    source = "Текст\tс сырым адресом https://example.com/path и www.example.org\tвнутри."

    cleaned = _clean(source)

    assert cleaned == "Текст с сырым адресом https://example.com/path и www.example.org внутри."
    assert [finding.residue_class for finding in detect_narration_residue(cleaned)] == ["url_or_domain"]


@pytest.mark.parametrize("glyph", ["•", "●", "◦", "‣"])
def test_cleanup_drops_the_bullet_glyph_and_keeps_the_item_text(glyph):
    """Spec 054: a list-bullet glyph is not speech, and 116 of them reached the 2026-08-04
    narration artifact of Money & Sustainability, where a TTS engine would read them aloud.
    """
    source = f"{glyph} Компании постоянно балансируют на этих качелях.\n{glyph} Второй пункт."

    assert _clean(source) == "Компании постоянно балансируют на этих качелях.\nВторой пункт."


def test_cleanup_leaves_a_bullet_glyph_welded_inside_a_token():
    """Anti-vacuum: a glyph welded between word characters is data, not a list marker."""
    source = "Значение 4●5 осталось в тексте."

    assert _clean(source) == "Значение 4●5 осталось в тексте."


def test_cleanup_keeps_prose_that_merely_starts_with_a_dash_word():
    """Anti-vacuum for the whole list rule: an em-dash opening a line of dialogue is not a
    bullet, and the paragraph text is never shortened by the glyph rule."""
    source = "— Декларация 1700 ведущих учёных из 70 стран."

    assert _clean(source) == source


def _record(paragraph_id: str, text: str, role: str = "body") -> NarrationParagraphRecord:
    return NarrationParagraphRecord(
        paragraph_id=paragraph_id,
        block_index=1,
        role=role,
        text=text,
        needs_review_reasons=(),
        residue_before=(),
        residue_after=(),
        coverage=CoverageResult(0, 0, None),
    )


def _assemble(*items: tuple[str, str]):
    """``(role, text)`` per paragraph, ids in order."""
    return assemble_narration_records([_record(f"p{index}", text, role) for index, (role, text) in enumerate(items, 1)])


def _letters(text: str) -> str:
    return "".join(character for character in text if not character.isspace())


def test_narration_joins_a_sentence_that_runs_across_a_paragraph_break():
    """Spec 054, 2026-08-06. Measured on the four-book corpus: 81 of the 83 such boundaries
    arrive from IMPORT, where a PDF line wrap became a paragraph break. Both halves are there
    and nothing is missing — only the separator is wrong, and a TTS engine reads a paragraph
    break as a pause in the middle of a sentence."""
    assembly = _assemble(
        ("body", "Слово «кредит» звучит позитивно — вам доверились и сочли вас"),
        ("body", "платежеспособным. Слово «долг» несет негативный оттенок."),
    )

    assert assembly.join_pairs == (("p1", "p2"),)
    assert assembly.text == (
        "Слово «кредит» звучит позитивно — вам доверились и сочли вас "
        "платежеспособным. Слово «долг» несет негативный оттенок."
    )
    assert assembly.boundary_check == "ok"


def test_narration_join_changes_only_the_separator():
    """Nothing is added and nothing is lost: the letter sequence is identical before and
    after, which is what makes the rule checkable rather than merely plausible."""
    first, second = "первым шагом стало формирование основной", "команды, в неё вошли жители."

    assembly = _assemble(("body", first), ("body", second))

    assert len(assembly.join_pairs) == 1
    assert _letters(assembly.text) == _letters(first + second)


def test_narration_does_not_join_a_heading_to_the_prose_under_it():
    """Anti-vacuum. A heading legitimately ends without punctuation, which is exactly the
    shape the rule keys on — so the kind is the PREPARATION's role, not the text's shape."""
    assembly = _assemble(("heading", "Деньги как соглашение"), ("body", "доверие внутри сообщества делает их деньгами."))

    assert assembly.join_pairs == ()
    assert assembly.text == "Деньги как соглашение\n\nдоверие внутри сообщества делает их деньгами."


def test_narration_does_not_join_a_list_item_to_its_neighbour():
    """Anti-vacuum. Items of a list end without punctuation by convention and the next item
    may well start lowercase; welding them would turn a list into one run-on sentence."""
    assembly = _assemble(("list", "мера стоимости"), ("list", "средство обращения"))

    assert assembly.join_pairs == ()


def test_narration_does_not_join_an_epigraph_to_the_paragraph_after_it():
    assembly = _assemble(("epigraph", "цитата без точки"), ("body", "продолжение обычного абзаца."))

    assert assembly.join_pairs == ()


def test_narration_does_not_join_an_epigraph_attribution_to_what_follows_it():
    """Anti-vacuum, and the case the owner named. An attribution legitimately ends without a
    full stop; both its role and the capital that starts what follows stop the join."""
    assembly = _assemble(
        ("attribution", "— Эдгар Кан, создатель Time Dollars, основатель TimeBanks USA"),
        ("body", "«Вместо того чтобы просто винить кого-то, авторы предлагают решения»."),
    )

    assert assembly.join_pairs == ()


def test_narration_does_not_join_index_rows():
    """Anti-vacuum. The row ends on a PAGE NUMBER: allow digit endings and the only two such
    rows on the whole corpus join."""
    assembly = _assemble(("body", "Страх, 4"), ("body", "в Юте, 201; в Веймарской республике, 136"))

    assert assembly.join_pairs == ()


@pytest.mark.parametrize("terminal", [".", "!", "?", "…", ":", ";", "»", "\"", ")"])
def test_narration_does_not_join_after_a_finished_sentence(terminal):
    assembly = _assemble(
        ("body", f"Абзац закончился{terminal}"), ("body", "следующий абзац начинается со строчной буквы.")
    )

    assert assembly.join_pairs == ()


def test_narration_join_count_is_zero_when_nothing_runs_on():
    """Zero is a statement, not an absent measurement (Constitution V)."""
    assembly = _assemble(("body", "Первый абзац закончен."), ("body", "Второй абзац тоже закончен."))

    assert assembly.join_pairs == ()
    assert assembly.text == "Первый абзац закончен.\n\nВторой абзац тоже закончен."


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
    assert _rules(f"Источник: {reference_text}.") == [expected_rule]


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
            "Первый (Смит, 2019) фрагмент.",
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
    narration_text = "См. (Смит, 2019 " + "а" * 400 + ")"

    findings = _collect_narration_artifact_review_findings(narration_text)

    assert [str(finding["rule"]) for finding in findings] == ["inline_citation"]
    sample = _samples(findings[0])[0]
    assert len(sample) == _NARRATION_REVIEW_SAMPLE_CHARS + 1
    assert sample.endswith("…")


def test_narration_review_is_silent_on_clean_narration():
    assert _collect_narration_artifact_review_findings("Обычный абзац без маркеров.") == []
    assert _summarize_narration_review_findings([]) == {
        "review_finding_count": 0,
        "review_match_count": 0,
        "review_rules": [],
    }


def test_summarize_narration_review_findings_totals_matches_across_rules():
    findings = _collect_narration_artifact_review_findings(
        "doi:10.5194/sapiens-2-1, ISBN 978-5-9614-1234-5 и (Смит, 2019)."
    )

    assert _summarize_narration_review_findings(findings) == {
        "review_finding_count": 3,
        "review_match_count": 3,
        "review_rules": ["doi", "isbn_identifier", "inline_citation"],
    }
