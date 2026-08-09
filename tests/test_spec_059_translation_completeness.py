"""Spec 059, part A: prose must be delivered translated, in both paths.

Phase A-I -- the pair rule reaches the place where the decision is taken.

The rule itself was already written: ``fallback_delivered_source_text``
(``pipeline/block_execution.py:99``) asks whether the text a controlled fallback
delivered IS the block's own source. It had exactly one consumer -- the narration
exclusion at ``:988`` -- so neither ``classify_processed_block`` nor the failure-decision
table could see it, and a block delivered wholly in the source language was classified
``valid``.

The numbers these tests are written against come from
``specs/059-verdict-never-reaches-the-screen/measurement-translation-signal.md`` (7 233
recorded pairs, five runs) and from ``scripts/measure-block-pair-rule.py``, which
re-counts the same material at the granularity the decision actually uses: 1 firing block
out of 1 394, and that one is front matter.
"""

from __future__ import annotations

import ast
import inspect

import pytest

import docxaicorrector.pipeline.block_execution as block_execution
import docxaicorrector.pipeline.output_validation as output_validation


# ---------------------------------------------------------------------------
# A-I / FR-A2 -- the pair rule, with no floor under it
# ---------------------------------------------------------------------------

# Measured price of the floors that used to sit on this rule: between 14.7% and 38.1% of
# prose is shorter than 60 letters (measurement, feature 4), and the old
# ``_SOURCE_TEXT_FALLBACK_MIN_CHARS`` was 120 characters with a 12-English-word companion.
# A short paragraph delivered in the source language is the same defect as a long one.
_SHORT_UNTRANSLATED_BLOCK = "The monetary system is unchanged."


def test_short_block_delivered_as_its_own_source_is_not_valid() -> None:
    """A-I. Under the old floors this returned ``valid`` and never reached the table."""
    assert (
        output_validation.classify_processed_block(
            _SHORT_UNTRANSLATED_BLOCK, _SHORT_UNTRANSLATED_BLOCK
        )
        == "source_text_fallback"
    )


def test_fully_english_answer_equal_to_source_is_not_valid() -> None:
    """A-I. The Cyrillic guard (`output_validation.py:372-373`) made a wholly English
    answer invisible: no Cyrillic -> False -> ``valid``. The pair rule does not look at
    scripts at all."""
    source = "Chapter 4. Money and sustainability."
    assert output_validation.classify_processed_block(source, source) == "source_text_fallback"


def test_pair_rule_ignores_a_source_with_nothing_to_translate() -> None:
    """A-I. "There is a letter in the source" is the whole of the second condition:
    a block of digits and punctuation delivered unchanged is the right outcome, not a
    defect. Measured: 46 of the 7 103 delivered records are exactly this (measurement §5)."""
    source = "1. 2. 3. — 4."
    assert output_validation.classify_processed_block(source, source) == "valid"


def test_pair_rule_does_not_fire_when_the_job_keeps_the_language() -> None:
    """FR-A5. On the ru->ru literary-edit run 1 144 of 1 761 deliveries were byte-identical
    to their source, and every one of them was the RIGHT outcome (measurement §5). The
    condition is a property of the job, never guessed from the text."""
    source = "Это уже хороший абзац."
    assert (
        output_validation.classify_processed_block(source, source, languages_differ=False)
        == "valid"
    )
    assert (
        output_validation.classify_processed_block(source, source, languages_differ=True)
        == "source_text_fallback"
    )


def test_job_changes_language_reads_the_job_not_the_text() -> None:
    """FR-A5. Both languages must be named for the rule to apply: an unnamed language is a
    missing signal, and Constitution VII forbids inventing one."""
    assert block_execution.job_changes_language(source_language="en", target_language="ru") is True
    assert block_execution.job_changes_language(source_language="ru", target_language="ru") is False
    assert block_execution.job_changes_language(source_language="RU", target_language=" ru ") is False
    assert block_execution.job_changes_language(source_language="auto", target_language="ru") is True
    assert block_execution.job_changes_language(source_language="", target_language="ru") is False
    assert block_execution.job_changes_language(source_language="en", target_language=None) is False


# ---------------------------------------------------------------------------
# FR-A2 -- one comparison, written once
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target_text", "processed_chunk"),
    [
        ("The monetary system is unchanged.", "The monetary system is unchanged."),
        ("The monetary system is unchanged.", "  The monetary system is unchanged.  "),
        ("The monetary system is unchanged.", "Денежная система не изменилась."),
        ("1. 2. 3.", "1. 2. 3."),
        ("", ""),
    ],
)
def test_one_byte_comparison_serves_both_call_sites(target_text: str, processed_chunk: str) -> None:
    """FR-A2 forbids a second predicate. ``fallback_delivered_source_text`` keeps its name
    and its narration call site, and is a payload-shaped face over the single
    implementation the classifier also uses."""
    payload = _payload(target_text=target_text)
    assert block_execution.fallback_delivered_source_text(
        payload=payload, processed_chunk=processed_chunk
    ) is output_validation.delivered_text_equals_source(
        target_text=target_text, processed_chunk=processed_chunk
    )


def test_pair_rule_is_visible_to_classification_and_to_the_decision_table() -> None:
    """A-I in one sentence: the rule stopped having exactly one consumer.

    Before this work ``fallback_delivered_source_text`` was called from
    ``block_execution.py:988`` and nowhere else, so the classifier and the policy table
    could not see it. This asserts both new readers by source, not by mock."""
    module_source = inspect.getsource(block_execution)
    assert module_source.count("fallback_delivered_source_text(payload=") >= 2, (
        "the pair rule must be read by the decision table as well as by the narration branch"
    )
    classifier_source = inspect.getsource(output_validation.classify_processed_block)
    assert "is_source_text_fallback_output" in classifier_source
    fallback_source = inspect.getsource(output_validation.is_source_text_fallback_output)
    assert "delivered_text_equals_source" in fallback_source


# ---------------------------------------------------------------------------
# FR-A4 / anti-regression 13 -- the five-word list must be GONE, not extended
# ---------------------------------------------------------------------------


def test_five_word_english_residual_dictionary_no_longer_exists() -> None:
    """Anti-regression 13, checked in the direction that matters: the replacement must not
    quietly become an addition. ``has_unexplained_english_residuals`` keyed on
    ``{chapter, contents, introduction, conclusion, judgment}`` -- a word list, forbidden by
    Constitution VII, and unreachable for a wholly English answer anyway."""
    assert not hasattr(output_validation, "has_unexplained_english_residuals")

    # Checked over the AST, not over the text: a comment or a docstring may (and does)
    # discuss the removed words, while no string LITERAL may be one of them.
    #
    # The forbidden set is deliberately three words, not five. "contents" and "chapter"
    # survive elsewhere in this module as TOC/section ANCHORS, and Constitution VII blesses
    # that generic structural-anchor lexicon by name
    # (`references/bibliography/index/notes/contents/содержание/оглавление, chapter/глава`)
    # as an accepted, extensible language-coverage residual. "introduction", "conclusion"
    # and "judgment" carry no such role: they were book vocabulary, and their presence
    # anywhere in a literal here means the replacement turned back into an addition.
    tree = ast.parse(inspect.getsource(output_validation))
    literals = {
        node.value.casefold()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    forbidden = {"introduction", "conclusion", "judgment"}
    assert not (literals & forbidden), (
        f"book words are back on the decision path: {sorted(literals & forbidden)}"
    )

    # And the SET the classifier keyed on is gone as a set, not merely renamed: no set or
    # frozenset literal in the module may pair a TOC anchor with book vocabulary.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Set):
            continue
        values = {
            element.value.casefold()
            for element in node.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
        assert not (values & forbidden), f"the residual word list is back: {sorted(values)}"


def test_length_and_word_count_floors_are_gone() -> None:
    """FR-A3's neighbour: the two numeric floors under the old detector were the measured
    price of blindness (measurement §2, feature 4). They are removed, not lowered."""
    assert not hasattr(output_validation, "_SOURCE_TEXT_FALLBACK_MIN_CHARS")
    assert not hasattr(output_validation, "_SOURCE_TEXT_FALLBACK_MIN_ENGLISH_WORDS")


# ---------------------------------------------------------------------------
# Recorded blindness -- a discrepancy inside the spec, written down rather than hidden
# ---------------------------------------------------------------------------


def test_coherent_english_answer_unequal_to_source_stays_valid() -> None:
    """RECORDED BLINDNESS, not an aspiration.

    ``spec.md`` A-9 asks that a wholly English answer which is NOT byte-equal to its source
    stop being ``valid``. The same document (A-I, "Честно названный остаток слепоты") names
    that case as the honest residual, says the corpus of 7 233 records contains ZERO of
    them, and FR-A3 forbids the only instrument that could catch it -- a target-alphabet
    share used as a decision condition. The two requirements cannot both be met, so this
    test pins the behaviour that IS shipped and names the reason.
    """
    source = "Глава 4. Деньги и устойчивость."
    coherent_english = "Chapter four discusses money and sustainability at some length."
    assert output_validation.classify_processed_block(source, coherent_english) == "valid"

    partially_english = "Это переведённое предложение. The monetary system remains unchanged."
    assert output_validation.classify_processed_block(source, partially_english) == "valid"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _Payload:
    """The two attributes the pair rule reads. Deliberately not a ``BlockExecutionPayload``:
    the predicate is documented as reading a payload by attribute, and a stub proves it."""

    def __init__(self, *, target_text: str, paragraph_regions: list[str] | None = None) -> None:
        self.target_text = target_text
        self.paragraph_regions = paragraph_regions
        self.job_kind = "llm"
        self.paragraph_ids = ["p1"]
        self.target_text_with_markers = target_text


def _payload(*, target_text: str, paragraph_regions: list[str] | None = None) -> _Payload:
    return _Payload(target_text=target_text, paragraph_regions=paragraph_regions)
