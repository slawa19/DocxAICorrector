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
