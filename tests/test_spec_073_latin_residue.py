"""Spec 073 WP-C: the residue class ``latin`` (FR-003, SC-001 form, SC-007).

Examples are invented and of the FORM only (Constitution VII): no book text, no word list.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from docxaicorrector.core import model_accounting
from docxaicorrector.generation._generation import PARAGRAPH_STATUS_ACCEPTED
from docxaicorrector.pipeline.audiobook_pass import (
    NEEDS_REVIEW_RESIDUE,
    AudiobookParagraphInput,
    finalize_audiobook_block,
)
from docxaicorrector.pipeline.audiobook_repair import repair_block_residue
from docxaicorrector.text.narration_residue import (
    REPAIRABLE_RESIDUE_CLASSES,
    RESIDUE_CLASSES,
    detect_narration_residue,
)


def _latin(text: str):
    return next((finding for finding in detect_narration_residue(text) if finding.residue_class == "latin"), None)


def _classes(text: str) -> list[str]:
    return [finding.residue_class for finding in detect_narration_residue(text)]


# --- T-C2: the unit is a series of letters with at least one Latin letter -------------------------


def test_latin_words_are_counted_one_unit_per_series() -> None:
    finding = _latin("Zentrix и Quorvel Labs")
    assert finding is not None and finding.count == 3
    assert _classes("Zentrix и Quorvel Labs") == ["latin"]


def test_a_hyphenated_latin_series_is_one_unit() -> None:
    finding = _latin("серия XyZ-QW вышла")
    assert finding is not None and finding.count == 1


def test_a_cyrillic_word_with_a_latin_lookalike_letter_is_one_unit() -> None:
    finding = _latin("город Квазибургa стоит")
    assert finding is not None and finding.count == 1


def test_a_marked_cyrillic_word_without_latin_is_not_latin() -> None:
    assert _latin("кв́азар") is None
    assert _classes("кв́азар") == []


# --- T-C3: the two subtractions are not vacuous ---------------------------------------------------


def test_an_address_is_masked_and_a_word_next_to_it_still_counts() -> None:
    finding = _latin("смотрите zentrix.example и слово Quorvel")
    assert finding is not None and finding.count == 1
    assert "Quorvel" in finding.sample
    assert _latin("смотрите zentrix.example") is None


def test_a_roman_numeral_is_not_latin_but_a_word_beside_it_is() -> None:
    finding = _latin("глава IV, раздел Quorvel")
    assert finding is not None and finding.count == 1
    assert _latin("глава IV") is None


def test_a_lone_roman_letter_is_latin_on_purpose() -> None:
    finding = _latin("пункт I")
    assert finding is not None and finding.count == 1


def test_the_sample_is_a_slice_of_the_original_string() -> None:
    text = "слово " * 20 + "Zentrix " + "слово " * 20
    finding = _latin(text)
    assert finding is not None and "Zentrix" in finding.sample and finding.sample in text


# --- T-C4: place among the classes ----------------------------------------------------------------


def test_latin_is_repairable_and_comes_after_tag_form() -> None:
    assert "latin" in REPAIRABLE_RESIDUE_CLASSES
    assert RESIDUE_CLASSES.index("latin") == RESIDUE_CLASSES.index("tag_form") + 1
    order = _classes("число 5 и Zentrix")
    assert order == [name for name in RESIDUE_CLASSES if name in order] and order == ["digits", "latin"]


# --- T-C5 (SC-007): one paid call for a block with three repairable classes -----------------------


class _CountingTransport:
    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.requests: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if isinstance(self.answer, Exception):
            raise self.answer
        return SimpleNamespace(
            status="completed",
            output_text=self.answer,
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, cost=0.001),
        )


class _Client:
    """A run's client: ``with_options(max_retries=0)`` hands out the counting transport."""

    def __init__(self, answer: Any) -> None:
        self.transport = _CountingTransport(answer)
        self.with_options_calls: list[dict[str, Any]] = []

    def with_options(self, **options: Any) -> _CountingTransport:
        self.with_options_calls.append(options)
        return self.transport


_SOURCES = {
    "p1": "В 1999 году вышло 5 книг.",
    "p2": "ВЕТЕР СЕВЕР ЗАПАД",
    "p3": "Это Zentrix и Quorvel Labs.",
}
_CLEAN_ANSWER = (
    "[[DOCX_PARA_p1]]\nВ тысяча девятьсот девяносто девятом вышло пять книг.\n\n"
    "[[DOCX_PARA_p2]]\nВетер север запад\n\n"
    "[[DOCX_PARA_p3]]\nЭто Зентрикс и Кворвел Лабс.\n"
)
_LATIN_LEFT_ANSWER = _CLEAN_ANSWER.replace("Зентрикс", "Zentrix")


def _paragraphs() -> list[AudiobookParagraphInput]:
    return [
        AudiobookParagraphInput(
            paragraph_id=paragraph_id,
            role="body",
            source_text=text,
            delivered_text=text,
            status=PARAGRAPH_STATUS_ACCEPTED,
        )
        for paragraph_id, text in _SOURCES.items()
    ]


def _finalize(client: _Client):
    def repair(items, context_before, context_after):
        with model_accounting.run_model_accounting_scope(run_id="r"):
            return repair_block_residue(
                client=client,
                model_id="m",
                system_prompt="FIXTURE REPAIR PROMPT",
                items=items,
                context_before=context_before,
                context_after=context_after,
                should_stop=lambda: False,
                log_event=lambda *args, **kwargs: "",
                block_index=0,
                filename="f.docx",
            )

    return finalize_audiobook_block(block_index=0, paragraphs=_paragraphs(), repair=repair)


def test_three_repairable_classes_cost_exactly_one_request() -> None:
    client = _Client(_CLEAN_ANSWER)
    block = _finalize(client)
    assert len(client.transport.requests) == 1
    assert client.with_options_calls == [{"max_retries": 0}]
    assert {name for item in block.repair_items for name in item.residue_classes} == {"digits", "all_caps", "latin"}
    assert block.repair_outcome is not None and block.repair_outcome.status == "accepted"
    assert all(record.residue_after == () for record in block.records)
    assert all(NEEDS_REVIEW_RESIDUE not in record.needs_review_reasons for record in block.records)


def test_an_answer_that_keeps_latin_is_needs_review_and_not_asked_again() -> None:
    client = _Client(_LATIN_LEFT_ANSWER)
    block = _finalize(client)
    assert len(client.transport.requests) == 1
    kept = next(record for record in block.records if record.paragraph_id == "p3")
    assert [finding.residue_class for finding in kept.residue_after] == ["latin"]
    assert NEEDS_REVIEW_RESIDUE in kept.needs_review_reasons
    assert all(record.residue_after == () for record in block.records if record.paragraph_id != "p3")


def test_an_ordinary_transport_exception_is_not_sent_again() -> None:
    client = _Client(RuntimeError("synthetic transport fault"))
    block = _finalize(client)
    assert len(client.transport.requests) == 1
    assert block.repair_outcome is not None and block.repair_outcome.status == "failed"
    assert all(NEEDS_REVIEW_RESIDUE in record.needs_review_reasons for record in block.records)


@pytest.mark.parametrize("text", ["обычная проза без латиницы.", "Он сказал: «да»."])
def test_prose_without_latin_has_no_latin_finding(text: str) -> None:
    assert _latin(text) is None
