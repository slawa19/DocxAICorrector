"""Spec 074 FR-302, FR-401...FR-405: the address form, a superscript note after it, the address as the whole token,
``/`` and ``\\`` as residue, and the audiobook source shortened to the bare domain.

Examples are invented and of the FORM only (Constitution VII): reserved example domains, no book text, no word
list, no table of domain zones. The expected answers are the ones the spec wrote down before the code.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import pytest

import docxaicorrector.core.config as config
from docxaicorrector.core.models import DocumentBlock, ParagraphUnit
from docxaicorrector.document.semantic_blocks import build_editing_jobs
from docxaicorrector.pipeline.audiobook_pass import _block_source_texts
from docxaicorrector.pipeline.audiobook_plan import build_audiobook_block_plan
from docxaicorrector.pipeline.contracts import BlockExecutionPayload
from docxaicorrector.pipeline.job_parsing import parse_processing_job
from docxaicorrector.pipeline.reading_glossary import reading_candidate_units, reading_paragraphs_from_jobs
from docxaicorrector.text import narration_residue as residue
from docxaicorrector.text.narration_residue import (
    REPAIRABLE_RESIDUE_CLASSES,
    detect_narration_residue,
    latin_units,
    mask_url_or_domain,
)


def _classes(text: str) -> dict[str, int]:
    return {finding.residue_class: finding.count for finding in detect_narration_residue(text)}


def _masked_spans(text: str) -> list[str]:
    """The original substrings the mask blanked out, in order."""

    masked = mask_url_or_domain(text)
    assert len(masked) == len(text)
    return [text[start:end] for start, end in _runs(index for index, (a, b) in enumerate(zip(text, masked)) if a != b)]


def _runs(indexes) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    for index in indexes:
        if runs and runs[-1][1] == index:
            runs[-1] = (runs[-1][0], index + 1)
        else:
            runs.append((index, index + 1))
    return runs


# =====================================================================================================
# Characterisation: what must not change
# =====================================================================================================


@pytest.mark.parametrize(
    "text",
    [
        "Утром мы вышли к реке, т.е. к старому мосту, и т.д.",
        "число 3.14 и версия 2.5",
        "подожди...потом",
        "площадь в м² и формула Н₂О",
    ],
)
def test_text_without_an_address_is_not_masked(text: str) -> None:
    assert mask_url_or_domain(text) == text


@pytest.mark.parametrize(
    ("text", "address"),
    [
        ("зайдите на www.example.org сегодня", "www.example.org"),
        ("сайт example.com работает", "example.com"),
        ("см. https://example.org/path и ещё", "https://example.org/path"),
        ("пишите на ftp://host/file", "ftp://host/file"),
    ],
)
def test_an_address_without_a_note_is_masked_as_before(text: str, address: str) -> None:
    assert _masked_spans(text) == [address]
    assert _classes(text)["url_or_domain"] == 1


def test_two_bare_domains_are_still_two_addresses() -> None:
    assert _classes("a.example.com и b.example.org")["url_or_domain"] == 2


# =====================================================================================================
# FR-302: a trailing superscript note is split off an address and never makes a word an address
# =====================================================================================================


@pytest.mark.parametrize(
    "text",
    ["в США.¹⁵ Далее", "в две тысячи десятом году.¹³ Затем"],
)
def test_a_word_before_a_superscript_note_is_not_an_address(text: str) -> None:
    assert mask_url_or_domain(text) == text
    assert "url_or_domain" not in _classes(text)


@pytest.mark.parametrize(
    ("text", "address"),
    [
        ("см. www.example.org.¹² Далее", "www.example.org"),
        ("см. https://example.org/x² далее", "https://example.org/x"),
        ("сайт example.org² и", "example.org"),
    ],
)
def test_a_real_address_before_a_note_is_recognised_without_the_note(text: str, address: str) -> None:
    assert _masked_spans(text) == [address]
    assert _classes(text)["url_or_domain"] == 1


def test_an_abbreviation_before_a_note_is_a_reading_candidate_again() -> None:
    # User Story 2, scenario 3.
    assert reading_candidate_units("…в США.¹⁵ Далее") == ("США",)


def test_a_latin_word_before_a_note_is_a_latin_unit_again() -> None:
    assert [unit.text for unit in latin_units("так писал Quorvel.¹⁵ Далее")] == ["Quorvel"]


# =====================================================================================================
# FR-401: the address is the whole token
# =====================================================================================================


@pytest.mark.parametrize(
    ("text", "token", "domain"),
    [
        # SC-401: a domain with a path is ONE address, not two "domains".
        ("адрес example.com/index.asp. Один", "example.com/index.asp", "example.com"),
        ("(www.example.org).", "www.example.org", "example.org"),
        ("*www.example.org/a*;", "www.example.org/a", "example.org"),
        ("**www.example.org**:", "www.example.org", "example.org"),
        ("*go.example/Xy12.*", "go.example/Xy12", "go.example"),
        ("<u>www.example.org/a</u>", "www.example.org/a", "example.org"),
        ("www.example.org/a<sup>3</sup>", "www.example.org/a", "example.org"),
        ("см. www.example.org.¹² Далее", "www.example.org", "example.org"),
        ("https://www.example.org/a?b=1#c", "https://www.example.org/a?b=1#c", "example.org"),
        ("HTTP://WWW.Example.org/a", "HTTP://WWW.Example.org/a", "Example.org"),
        ("сайт example.org/.", "example.org/", "example.org"),
        ("хост sub.example.co.uk/x", "sub.example.co.uk/x", "sub.example.co.uk"),
    ],
)
def test_the_address_token_and_its_domain(text: str, token: str, domain: str) -> None:
    (address,) = residue.address_tokens(text)
    assert address.text == token
    assert text[address.start : address.end] == token
    assert address.domain == domain


def test_an_email_is_a_token_but_not_a_web_address() -> None:
    (address,) = residue.address_tokens("почта orders.desk@example.com, либо")
    assert address.text == "orders.desk@example.com"
    assert address.domain is None


@pytest.mark.parametrize("text", ["в США.¹⁵ Далее", "т.е. вот так", "число 3.14", ""])
def test_no_address_no_token(text: str) -> None:
    assert residue.address_tokens(text) == ()


def test_two_addresses_in_one_paragraph_are_two_tokens() -> None:
    tokens = residue.address_tokens("См. www.example.org/a и example.net/b/c.html, а также example.com.")
    assert [token.text for token in tokens] == ["www.example.org/a", "example.net/b/c.html", "example.com"]


# =====================================================================================================
# FR-405: the address is shortened to its domain (SC-403 synthetic cases)
# =====================================================================================================


@pytest.mark.parametrize(
    ("text", "shortened"),
    [
        # an address before a note keeps the note
        ("см. www.example.org.¹² Далее", "см. example.org.¹² Далее"),
        # an address at the end of a sentence keeps the full stop
        ("Подробнее: example.org/a/b.html.", "Подробнее: example.org."),
        # e-mail is not touched
        ("почта orders.desk@example.com, либо", "почта orders.desk@example.com, либо"),
        # a bare domain is not touched
        ("сайт example.org работает", "сайт example.org работает"),
        ("https://www.example.org/a?b=1#c", "example.org"),
        ("(www.example.org).", "(example.org)."),
        ("*www.example.org/a*;", "*example.org*;"),
        ("*go.example/Xy12.*", "*go.example.*"),
        ("<u>www.example.org/a</u>", "<u>example.org</u>"),
        ("www.example.org/a<sup>3</sup>", "example.org<sup>3</sup>"),
        ("сайт example.org/.", "сайт example.org."),
        (
            "См. www.example.org/a и example.net/b/c.html, а также example.com.",
            "См. example.org и example.net, а также example.com.",
        ),
        ("Утром мы вышли к реке, т.е. к мосту.", "Утром мы вышли к реке, т.е. к мосту."),
    ],
)
def test_the_address_is_shortened_to_its_domain(text: str, shortened: str) -> None:
    assert residue.shorten_addresses_to_domain(text) == shortened


def test_shortening_is_idempotent_and_leaves_no_path() -> None:
    text = "Сайты: https://example.org/a/b, www.example.net/c?d=1 и sub.example.com/e#f."
    once = residue.shorten_addresses_to_domain(text)
    assert residue.shorten_addresses_to_domain(once) == once
    assert "/" not in once and "www." not in once and "?" not in once and "#" not in once


# =====================================================================================================
# FR-405: the plug-in point -- the audiobook branch of ``build_editing_jobs``
# =====================================================================================================

_ADDRESS_PROSE = "Подробности на сайте www.example.org/reports/annual.html, там же архив отчётов."
_SHORT_PROSE = "Подробности на сайте example.org, там же архив отчётов."
_CAPTION_WITH_ADDRESS = "Рис. 1. Источник: www.example.org/fig/1.png"
_PROSE = "Над гаванью стоял туман, и лодки ждали у причала до самого вечера."
_ADDRESS_ONLY = "https://www.example.org/12345/67890/12345"


def _unit(text: str, pid: str, *, role: str = "body") -> ParagraphUnit:
    return ParagraphUnit(text=text, role=role, paragraph_id=pid, structural_role=role)


def _blocks() -> list[DocumentBlock]:
    return [
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0000")]),
        DocumentBlock(
            paragraphs=[
                _unit(_ADDRESS_PROSE, "p0001"),
                _unit(_CAPTION_WITH_ADDRESS, "p0002", role="caption"),
                _unit(_ADDRESS_ONLY, "p0003"),
            ]
        ),
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0004")]),
    ]


def _jobs(operation: str) -> list[dict[str, object]]:
    return build_editing_jobs(_blocks(), max_chars=3000, processing_operation=operation)


def test_the_audiobook_job_carries_the_shortened_address() -> None:
    job = _jobs("audiobook")[1]

    assert job["narration_exclusion_reasons"] == [None, "caption", "fragment"]
    target = str(job["target_text"])
    marked = str(job["target_text_with_markers"])
    assert _SHORT_PROSE in target and _SHORT_PROSE in marked
    assert "/reports/" not in target and "/reports/" not in marked
    assert job["target_chars"] == len(target)


def test_exclusion_reasons_are_decided_on_the_original_text() -> None:
    # The address-only paragraph is a fragment by form; shortened ("example.org") it would not be.
    assert "url_or_domain" in _classes(_ADDRESS_ONLY)
    job = _jobs("audiobook")[1]
    assert cast(list, job["narration_exclusion_reasons"])[2] == "fragment"


def test_excluded_paragraphs_keep_their_text() -> None:
    job = _jobs("audiobook")[1]
    assert _CAPTION_WITH_ADDRESS in str(job["target_text_with_markers"])
    assert _ADDRESS_ONLY in str(job["target_text_with_markers"])


def test_the_audiobook_context_is_built_from_the_shortened_paragraphs() -> None:
    jobs = _jobs("audiobook")
    assert _SHORT_PROSE in str(jobs[0]["context_after"])
    assert _SHORT_PROSE in str(jobs[2]["context_before"])
    assert "/reports/" not in str(jobs[0]["context_after"]) + str(jobs[2]["context_before"])


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_translate_and_edit_jobs_keep_the_whole_address(operation: str) -> None:
    jobs = _jobs(operation)
    assert _ADDRESS_PROSE in str(jobs[1]["target_text"])
    assert _ADDRESS_PROSE in str(jobs[1]["target_text_with_markers"])
    assert _ADDRESS_PROSE in str(jobs[0]["context_after"])
    assert jobs[1]["target_chars"] == len(str(jobs[1]["target_text"]))


def test_the_audiobook_jobs_differ_from_edit_only_in_the_shortened_paragraph_and_the_narration_fields() -> None:
    edit_jobs = _jobs("edit")
    audiobook_jobs = _jobs("audiobook")
    narration_keys = {"narration_exclusion_reasons", "narration_include", "job_kind"}
    text_keys = {"target_text", "target_text_with_markers", "target_chars", "context_before", "context_after", "context_chars"}
    for edit_job, audiobook_job in zip(edit_jobs, audiobook_jobs):
        same = {key for key in edit_job if key not in narration_keys | text_keys}
        assert {key: edit_job[key] for key in same} == {key: audiobook_job[key] for key in same}
        # The target is the edit target with the one address shortened, nothing else. (The context also leaves
        # out the excluded paragraphs -- spec 070 -- and is pinned by the context test above.)
        for key in ("target_text", "target_text_with_markers"):
            assert str(audiobook_job[key]) == str(edit_job[key]).replace(_ADDRESS_PROSE, _SHORT_PROSE)


def test_every_reader_of_the_audiobook_job_sees_the_same_shortened_source() -> None:
    job = _jobs("audiobook")[1]
    payload = parse_processing_job(job=job, payload_factory=BlockExecutionPayload)
    ids = [str(paragraph_id) for paragraph_id in cast(list, job["paragraph_ids"])]

    # coverage, residue, fallback and the Latin count read this
    assert _block_source_texts(payload, ids)[0] == _SHORT_PROSE
    # the model request (a subset: two paragraphs of the block are excluded)
    plan = build_audiobook_block_plan(payload)
    assert plan is not None and list(plan.send_ids) == ["p0001"]
    assert _SHORT_PROSE in plan.send_text_with_markers and "/reports/" not in plan.send_text_with_markers
    # the reading glossary
    sources = {paragraph.paragraph_id: paragraph.text for paragraph in reading_paragraphs_from_jobs(_jobs("audiobook"))}
    assert sources["p0001"] == _SHORT_PROSE


# =====================================================================================================
# FR-403: "/" and "\" have no reading -- residue of the class ``symbols``
# =====================================================================================================


@pytest.mark.parametrize(("text", "count"), [("и/или", 1), ("путь а/б/в", 2), ("а \\ б", 1)])
def test_slash_and_backslash_are_symbols(text: str, count: int) -> None:
    assert _classes(text) == {"symbols": count}
    assert "symbols" in REPAIRABLE_RESIDUE_CLASSES


def test_a_spoken_address_is_clean() -> None:
    assert detect_narration_residue("Подробности на сайте экзампл точка орг, там же архив.") == ()


# =====================================================================================================
# FR-402: the prompt rule, the same wording in the main and the repair prompt
# =====================================================================================================

_PROMPTS = Path(config.PROMPTS_DIR)


def _address_rule(prompt: str) -> str:
    lines = [line for line in prompt.splitlines() if "по адресу" in line]
    assert len(lines) == 1, lines
    return re.sub(r"^\d+\.\s*", "", lines[0].strip())


def test_the_main_and_the_repair_prompt_carry_the_same_address_rule() -> None:
    main = (_PROMPTS / "operation_audiobook.txt").read_text(encoding="utf-8")
    repair = (_PROMPTS / "operation_audiobook_repair.txt").read_text(encoding="utf-8")
    rule = _address_rule(main)
    assert rule in repair
    # the zone is read by the model as a word, the dot as the word "точка"; no table of zones in code
    assert "точка" in rule and "зон" in rule
    # the old "or remove it" choice is gone
    assert "или уберите" not in repair
