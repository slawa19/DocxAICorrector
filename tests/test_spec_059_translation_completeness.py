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
import logging
from types import SimpleNamespace

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


def test_the_pipelines_own_placeholder_markup_is_not_something_to_translate() -> None:
    """A-I, second condition, on the case that made it necessary.

    ``[[DOCX_IMAGE_...]]`` and ``[[DOCX_PARA_...]]`` are the pipeline's own markup and every
    stage is required to carry them through verbatim, so a block that is nothing but
    placeholders is delivered unchanged BY DESIGN and has nothing in it to translate. Their
    Latin letters belong to the machinery, not to the book. Same reasoning as spec 057's
    unwrapping of importer-added emphasis: strip exactly the markup the pipeline itself
    added, and nothing else -- which is why the second case below still fires.
    """
    placeholder_only = "[[DOCX_IMAGE_img_001]]"
    assert output_validation.classify_processed_block(placeholder_only, placeholder_only) == "valid"

    with_prose = "[[DOCX_IMAGE_img_001]]\n\nFigure 1. The circulation of money."
    assert output_validation.classify_processed_block(with_prose, with_prose) == "source_text_fallback"


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


# ``test_job_changes_language_reads_the_job_not_the_text`` stood here and asked the question
# with the language CODES alone. That was the P0 defect written as a test: it was green while
# the pipeline answered "yes, this job translates" on the default literary edit. It is
# replaced by the operation-aware group under "P0" below, which covers every case it covered
# plus the four it could not see.


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
    tree = ast.parse(inspect.getsource(block_execution))
    call_sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "fallback_delivered_source_text"
    ]
    assert len(call_sites) >= 2, (
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

    def __init__(
        self,
        *,
        target_text: str,
        paragraph_regions: list[str] | None = None,
        structural_roles: list[str] | None = None,
    ) -> None:
        self.target_text = target_text
        self.paragraph_regions = paragraph_regions
        self.structural_roles = structural_roles
        self.job_kind = "llm"
        self.paragraph_ids = ["p1"]
        self.target_text_with_markers = target_text


def _payload(
    *,
    target_text: str,
    paragraph_regions: list[str] | None = None,
    structural_roles: list[str] | None = None,
) -> _Payload:
    return _Payload(
        target_text=target_text,
        paragraph_regions=paragraph_regions,
        structural_roles=structural_roles,
    )


# ---------------------------------------------------------------------------
# A-II / FR-A6 -- the per-paragraph REGION reaches the payload
# ---------------------------------------------------------------------------
#
# The region existed, but on another stage and at another granularity: block-level for the
# narration (``semantic_blocks._resolve_reference_region_indexes``) and per-source_index but
# only AFTER generation (``validation/formatting_coverage.py``). Nothing reached
# ``BlockExecutionPayload``, so on a mixed "apparatus + prose" block there was nothing to
# tell the two apart -- which is why the invariant in A-4 could not be written before this.
#
# PROSE = the source registry minus front matter, minus the TOC, minus the back-matter
# reference region (spec 059 A-6). Region and structural role only; never the shape of the
# text (Constitution VII).

_LONG_BODY = (
    "Money is not a thing but an agreement within a community to use something standardised "
    "as a means of payment, and that agreement is what this chapter is about."
)


def _front_matter_to_back_matter_document():
    from docxaicorrector.core.models import DocumentBlock, ParagraphUnit

    return [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Rethinking Money", role="heading", paragraph_id="p0000", heading_level=1),
                ParagraphUnit(text="A Berrett-Koehler book", role="body", paragraph_id="p0001"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Contents", role="heading", structural_role="toc_header", paragraph_id="p0002"),
                ParagraphUnit(text="Chapter 1 ...... 7", role="body", structural_role="toc_entry", paragraph_id="p0003"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Chapter 1 — Beginnings", role="heading", paragraph_id="p0004", heading_level=1),
                ParagraphUnit(text=_LONG_BODY, role="body", paragraph_id="p0005"),
                ParagraphUnit(text=_LONG_BODY, role="body", paragraph_id="p0006"),
                ParagraphUnit(text=_LONG_BODY, role="body", paragraph_id="p0007"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="References", role="heading", paragraph_id="p0008", heading_level=1),
                ParagraphUnit(text="[1] Smith, 2009. DOI:10.1000/xyz", role="body", paragraph_id="p0009"),
            ]
        ),
    ]


def test_editing_jobs_carry_a_region_for_every_paragraph() -> None:
    """A-II. Four regions, resolved from the document, one label per paragraph."""
    from docxaicorrector.document.semantic_blocks import build_editing_jobs

    jobs = build_editing_jobs(_front_matter_to_back_matter_document(), max_chars=3000)

    assert [job["paragraph_regions"] for job in jobs] == [
        ["front_matter", "front_matter"],
        ["toc", "toc"],
        ["prose", "prose", "prose", "prose"],
        ["back_matter", "back_matter"],
    ]


def test_every_editing_job_labels_exactly_as_many_paragraphs_as_it_carries() -> None:
    """The contract is "parallel to ``paragraph_ids``", and a guard is cheaper than a bug:
    a producer that forgets the field reopens the hole in A-4 silently, because an absent
    region is read as "unknown"."""
    from docxaicorrector.document.semantic_blocks import build_editing_jobs

    jobs = build_editing_jobs(_front_matter_to_back_matter_document(), max_chars=3000)

    for job in jobs:
        regions = job["paragraph_regions"]
        paragraph_ids = job["paragraph_ids"]
        assert isinstance(regions, list) and isinstance(paragraph_ids, list)
        assert len(regions) == len(paragraph_ids)


def test_payload_carries_the_regions_through_job_parsing() -> None:
    """A-II is a CONTRACT change: the field has to survive the job -> payload boundary."""
    from docxaicorrector.pipeline.contracts import BlockExecutionPayload
    from docxaicorrector.pipeline.job_parsing import parse_processing_job

    payload = parse_processing_job(
        job={
            "target_text": "Body.",
            "context_before": "",
            "context_after": "",
            "target_chars": 5,
            "context_chars": 0,
            "paragraph_ids": ["p1", "p2"],
            "paragraph_regions": ["prose", "back_matter"],
        },
        payload_factory=BlockExecutionPayload,
    )

    assert payload.paragraph_regions == ["prose", "back_matter"]


def test_an_unknown_region_name_is_refused_rather_than_read_as_prose() -> None:
    """Constitution VII: a vocabulary nobody validates is a vocabulary that drifts. A region
    the pipeline does not define must not be silently folded into either answer."""
    from docxaicorrector.pipeline.contracts import BlockExecutionPayload
    from docxaicorrector.pipeline.job_parsing import parse_processing_job

    with pytest.raises((TypeError, ValueError)):
        parse_processing_job(
            job={
                "target_text": "Body.",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
                "paragraph_ids": ["p1"],
                "paragraph_regions": ["footnotes"],
            },
            payload_factory=BlockExecutionPayload,
        )


def test_payload_contains_prose_reads_the_region_and_nothing_else() -> None:
    """The consumer side of A-II, and the one the invariant asks.

    A block of apparatus alone answers False -- that is the anti-vacuum half of
    anti-regression 8. A MIXED block answers True, because a block that carries one paragraph
    of prose cannot be substituted wholesale without losing that prose.

    ``None`` means the producer resolved no regions at all. That is treated as prose: the
    only production producer is ``build_editing_jobs``, which always labels, so absence means
    a caller outside document preparation, and the safe direction there is to protect the
    text rather than to assume it is apparatus.
    """
    assert block_execution.payload_contains_prose(_payload(target_text="x", paragraph_regions=["prose"])) is True
    assert block_execution.payload_contains_prose(
        _payload(target_text="x", paragraph_regions=["back_matter", "toc", "front_matter"])
    ) is False
    assert block_execution.payload_contains_prose(
        _payload(target_text="x", paragraph_regions=["back_matter", "prose"])
    ) is True
    assert block_execution.payload_contains_prose(_payload(target_text="x", paragraph_regions=None)) is True
    assert block_execution.payload_contains_prose(_payload(target_text="x", paragraph_regions=[])) is True


# ---------------------------------------------------------------------------
# A-II, second narrowing (2026-08-09) -- the FIGURE apparatus is not prose
# ---------------------------------------------------------------------------
#
# The region is the span of the book's BODY, and figures live in the body, so an image
# placeholder and the caption under it are labelled ``prose`` by region and were read as prose
# by the invariant. The signal that tells them apart already exists and predates this spec:
# ``BlockExecutionPayload.structural_roles``, one label per paragraph, produced by
# ``build_editing_jobs`` from the document layer's own roles.
#
# Measured on the four recorded books by re-running document preparation with no model call
# (``jobs`` from ``_prepare_document_for_processing``): blocks holding at least one
# prose-region paragraph, and of those, the blocks whose every prose-region paragraph is
# image/caption --
#
#     Rethinking Money        281 blocks with prose region, 54 flip to apparatus
#     The Value of Everything 211                            40
#     Money & Sustainability  293                            39
#     Creating Wealth         415                            61
#
# and the prose-region role census finds 28 ``caption`` paragraphs in The Value of Everything,
# 22 in Creating Wealth. So this is not a rule written for nobody.


def test_an_image_and_its_caption_are_not_prose_although_the_region_says_so() -> None:
    """The narrowing, on the shape the measurement actually found: a figure block is one
    ``[[DOCX_IMAGE_…]]`` paragraph followed by its caption, both inside the prose region."""
    figure_block = _payload(
        target_text="x",
        paragraph_regions=["prose", "prose"],
        structural_roles=["image", "caption"],
    )
    assert block_execution.payload_contains_prose(figure_block) is False
    assert block_execution.prose_paragraph_indexes(figure_block) == ()


def test_one_body_paragraph_beside_the_figure_is_still_prose_and_is_the_one_named() -> None:
    """Anti-vacuum: the narrowing must not swallow the block. A caption next to a paragraph of
    body text leaves the body text prose — and ``prose_paragraph_indexes`` names WHICH, because
    the warning has to carry an address."""
    mixed = _payload(
        target_text="x",
        paragraph_regions=["prose", "prose", "prose"],
        structural_roles=["image", "caption", "body"],
    )
    assert block_execution.payload_contains_prose(mixed) is True
    assert block_execution.prose_paragraph_indexes(mixed) == (2,)


def test_the_roles_that_carry_a_books_text_stay_prose() -> None:
    """The other half of the same anti-vacuum. Headings and list items are text a reader reads
    and a translator must translate; only the figure apparatus is excused."""
    for role in ("body", "heading", "list", "list_item", "epigraph", "attribution", ""):
        assert (
            block_execution.payload_contains_prose(
                _payload(target_text="x", paragraph_regions=["prose"], structural_roles=[role])
            )
            is True
        ), role


def test_the_diagram_label_that_killed_the_recorded_run_is_NOT_closed_by_the_roles() -> None:
    """HONEST CHARACTERIZATION, and the load-bearing one for this whole change.

    Block 140 of 305 on run ``20260809T_059_doc_rethinking`` is paragraph ``p0812``, whose
    entire text is ``2b`` — a step label on the Terra currency diagram, sitting next to
    ``[[DOCX_IMAGE_img_031]]``. Re-running document preparation over the same PDF with no model
    call reproduces the run exactly (2 265 paragraphs, 305 jobs) and gives that paragraph
    ``structural_role="body"``, ``region="prose"``: the PDF text layer offers nothing else, so
    the document layer has no signal to give it a figure role.

    The narrowing above therefore does NOT catch it, and Constitution VII says such a residual
    is ACCEPTED rather than patched with a length floor or a word list. That is exactly why the
    outcome had to stop being a fail: a detector this rule cannot fix must not be able to make
    a book unreachable.
    """
    diagram_label = _payload(
        target_text="2b", paragraph_regions=["prose"], structural_roles=["body"]
    )
    assert block_execution.payload_contains_prose(diagram_label) is True


# ---------------------------------------------------------------------------
# A-4 / FR-A8 -- delivering untranslated prose becomes an inexpressible outcome
# ---------------------------------------------------------------------------
#
# ``CONTROLLED_BLOCK_FAILURE_POLICY`` splits block failures into seven QUALITY kinds that
# ship the block anyway (``fallback_continue``) and ten STRUCTURAL kinds that fail the run.
# The invariant sits on the first group only, and only where all three of A-I's and A-II's
# facts hold at once: the job changes language, the text about to ship IS the block's own
# source, and the block carries at least one paragraph of prose.

_QUALITY_REJECTION_KINDS = (
    "empty",
    "empty_processed_block",
    "source_text_fallback",
    "english_residual_output",
    "heading_only_output",
    "bullet_heading_output",
    "toc_body_concat",
)
_APPARATUS_REGIONS = ("front_matter", "toc", "back_matter")


def _registry_entries(**_kwargs):
    return [{"paragraph_id": "p1", "text": "x"}]


def _decide(
    *,
    rejection_kind,
    target_text,
    processed_chunk,
    paragraph_regions,
    languages_differ=True,
    structural_roles=None,
):
    payload = _payload(
        target_text=target_text,
        paragraph_regions=paragraph_regions,
        structural_roles=structural_roles,
    )
    return block_execution.classify_processed_block_failure_decision(
        rejection_kind=rejection_kind,
        payload=payload,
        processed_chunk=processed_chunk,
        build_processed_paragraph_registry_entries_fn=_registry_entries,
        languages_differ=languages_differ,
    )


@pytest.mark.parametrize("rejection_kind", _QUALITY_REJECTION_KINDS)
def test_a_prose_block_delivered_as_its_source_ships_with_a_warning_not_a_fail(
    rejection_kind: str,
) -> None:
    """FR-A8 as revised on 2026-08-09. Every one of the seven quality kinds, on a block of
    prose whose delivered text is its own source: the block SHIPS, and the decision carries
    the warning that makes the delivery loud.

    This assertion was the exact opposite until the recorded run
    ``20260809T_059_doc_rethinking`` died at 45% on block 140 of 305 — whose whole text is
    ``2b``, a step label on a currency diagram the model rightly returned unchanged. A hard
    stop on a DETERMINISTIC detector defect makes the book unreachable: the next run stops in
    the same place, and no action of the user's gets past it.
    """
    decision = _decide(
        rejection_kind=rejection_kind,
        target_text=_SHORT_UNTRANSLATED_BLOCK,
        processed_chunk=_SHORT_UNTRANSLATED_BLOCK,
        paragraph_regions=["prose"],
    )
    assert decision["decision"] == "fallback_continue"
    assert decision[block_execution.UNTRANSLATED_PROSE_WARNING_KEY] == "untranslated_prose"
    # Anti-regression 3: the text is delivered, not withheld. A warning that also drops the
    # block would be the old failure wearing a quieter name.
    assert decision["fallback_markdown"] == _SHORT_UNTRANSLATED_BLOCK


@pytest.mark.parametrize("rejection_kind", _QUALITY_REJECTION_KINDS)
@pytest.mark.parametrize("region", _APPARATUS_REGIONS)
def test_the_same_failure_on_apparatus_ships_with_no_warning_at_all(rejection_kind: str, region: str) -> None:
    """Anti-regression 8, the anti-vacuum half, and it matters MORE now than when the outcome
    was a fail: a warning printed on every substituted block is noise, and the apparatus is
    where substitution is the RIGHT outcome. Footnotes, the table of contents and front matter
    ship silently — on the recorded ``20260809T_059_doc_value`` run that is 48 blocks and
    8 828 characters of bibliography and URLs, every one of them correct.
    """
    decision = _decide(
        rejection_kind=rejection_kind,
        target_text=_SHORT_UNTRANSLATED_BLOCK,
        processed_chunk=_SHORT_UNTRANSLATED_BLOCK,
        paragraph_regions=[region, region],
    )
    assert decision["decision"] == "fallback_continue"
    assert block_execution.UNTRANSLATED_PROSE_WARNING_KEY not in decision


def test_a_mixed_block_is_decided_by_the_prose_paragraph_it_carries() -> None:
    """Anti-regression 7c. Substitution happens on the BLOCK, so one paragraph of prose is
    enough to make substituting the whole block a loss of prose. Remove that paragraph and
    the same block, the same text and the same rejection kind decide the other way -- which
    is the per-paragraph discrimination A-II was built for.
    """
    mixed = _decide(
        rejection_kind="source_text_fallback",
        target_text=_SHORT_UNTRANSLATED_BLOCK,
        processed_chunk=_SHORT_UNTRANSLATED_BLOCK,
        paragraph_regions=["back_matter", "prose"],
    )
    apparatus_only = _decide(
        rejection_kind="source_text_fallback",
        target_text=_SHORT_UNTRANSLATED_BLOCK,
        processed_chunk=_SHORT_UNTRANSLATED_BLOCK,
        paragraph_regions=["back_matter", "back_matter"],
    )
    assert block_execution.UNTRANSLATED_PROSE_WARNING_KEY in mixed
    assert block_execution.UNTRANSLATED_PROSE_WARNING_KEY not in apparatus_only
    assert mixed["decision"] == apparatus_only["decision"] == "fallback_continue"


# The measured control group, named one by one rather than invented. These are the pair
# rule's false alarms from ``measurement-translation-signal.md`` section 5: 26 of 7 103
# delivered records, 21 of them shorter than 20 letters, 2 URLs, 1 title-case name. A rule
# that fails a run on "### B2B" or on a bare domain is broken (anti-regression 7b) -- and
# what tells them from lost prose is the REGION, never the feature.
_MEASURED_FALSE_ALARMS = (
    "### B2B",
    "### WISPOS",
    "MediCash, 165",
    "Lehman Brothers, 70",
    "Stripe, 115- 116",
    "Barter Systems Inc.",
    "**www.triarchypress.com/peoplemoney**",
    "complementarycurrency.org.",
    "*Finanzmaerkte* (2005).",
)


@pytest.mark.parametrize("text", _MEASURED_FALSE_ALARMS)
def test_the_measured_false_alarms_do_not_fail_a_run_from_their_own_region(text: str) -> None:
    """Anti-regression 7b, first direction: in the region they actually live in -- index and
    bibliography rows are back matter, and acronym headings inside it are too -- the
    invariant leaves them alone, and says nothing about them either.
    """
    decision = _decide(
        rejection_kind="source_text_fallback",
        target_text=text,
        processed_chunk=text,
        paragraph_regions=["back_matter"],
    )
    assert decision["decision"] == "fallback_continue"
    assert block_execution.UNTRANSLATED_PROSE_WARNING_KEY not in decision


@pytest.mark.parametrize("text", _MEASURED_FALSE_ALARMS)
def test_the_measured_false_alarms_do_not_fire_the_rule_inside_a_translated_block(text: str) -> None:
    """Anti-regression 7b, second and stronger direction, and the reason the measurement was
    re-run at block granularity before any code was written.

    Every one of those 26 records is a PARAGRAPH. Substitution and classification both happen
    on a BLOCK, and a block is 3 to 6 paragraphs on the recorded runs. Put an untranslated
    acronym heading next to one translated neighbour and the block is no longer byte-identical
    to its source, so the rule does not fire at all -- region or no region. Measured
    consequence: 1 firing block in 1 394 across five runs
    (``scripts/measure-block-pair-rule.py``), and that one is the title page.
    """
    source_block = text + "\n\nThe monetary system is unchanged."
    delivered_block = text + "\n\nДенежная система не изменилась."
    assert output_validation.classify_processed_block(source_block, delivered_block) == "valid"
    decision = _decide(
        rejection_kind="source_text_fallback",
        target_text=source_block,
        processed_chunk=delivered_block,
        paragraph_regions=["prose", "prose"],
    )
    assert decision["decision"] == "fallback_continue"
    assert block_execution.UNTRANSLATED_PROSE_WARNING_KEY not in decision


def test_the_invariant_is_off_when_the_job_does_not_change_language() -> None:
    """FR-A5 at the decision point, not only at the classifier."""
    decision = _decide(
        rejection_kind="source_text_fallback",
        target_text="Это уже хороший абзац.",
        processed_chunk="Это уже хороший абзац.",
        paragraph_regions=["prose"],
        languages_differ=False,
    )
    assert decision["decision"] == "fallback_continue"
    assert block_execution.UNTRANSLATED_PROSE_WARNING_KEY not in decision


def test_a_prose_block_that_ships_the_models_own_answer_keeps_fallback_continue() -> None:
    """Anti-regression 3, on the unit level: the invariant must not become "stop substituting".

    A quality rejection whose fallback ships the MODEL's answer -- text that is not the
    source -- still ships. The rule keys on what is about to be DELIVERED, not on the fact
    that something was rejected, so no path removes text that used to be delivered.
    """
    decision = _decide(
        rejection_kind="heading_only_output",
        target_text="# Заголовок\n\nЭто полноценный абзац.",
        processed_chunk="# Heading",
        paragraph_regions=["prose", "prose"],
    )
    assert decision["decision"] == "fallback_continue"
    assert decision["fallback_markdown"] == "# Heading"


def test_the_ten_structural_kinds_are_untouched_by_the_invariant() -> None:
    """Anti-regression 8, second sentence: the ten structural kinds stay ``fail``, and they
    stay ``fail`` for their own reason, not for this one.
    """
    for rejection_kind in (
        "missing_provider_client",
        "missing_provider_configuration",
        "missing_source_segment",
        "missing_translated_segment",
        "final_translated_book_incomplete",
        "marker_registry_failure",
        "marker_anchor_failure",
        "invalid_processing_job",
        "corrupted_block",
        "source_extraction_failure",
    ):
        decision = _decide(
            rejection_kind=rejection_kind,
            target_text=_SHORT_UNTRANSLATED_BLOCK,
            processed_chunk=_SHORT_UNTRANSLATED_BLOCK,
            paragraph_regions=["prose"],
        )
        assert decision == {"decision": "fail", "fallback_kind": rejection_kind}


def test_the_invariant_stops_working_without_either_half_it_stands_on() -> None:
    """Anti-regression 10, and the reason the spec fixes the order A-I -> A-II -> A-4.

    A table changed before the per-paragraph classification gives an invariant that is
    declared and does not fire. This drives that failure directly instead of asserting it:
    take A-I's pair away -- deliver something that is NOT the source -- and the rule cannot
    fire at all, whatever the region says. Take A-II's region away and the block is read as
    prose, which is the safe direction and the one the contract documents.

    Since 2026-08-09 both blocks SHIP, so what this reads is the warning key rather than the
    decision: the rule that "fires" now announces instead of stopping.
    """
    without_the_pair = _decide(
        rejection_kind="source_text_fallback",
        target_text=_SHORT_UNTRANSLATED_BLOCK,
        processed_chunk="Денежная система не изменилась.",
        paragraph_regions=["prose"],
    )
    assert without_the_pair["decision"] == "fallback_continue"
    assert block_execution.UNTRANSLATED_PROSE_WARNING_KEY not in without_the_pair

    without_the_region = _decide(
        rejection_kind="source_text_fallback",
        target_text=_SHORT_UNTRANSLATED_BLOCK,
        processed_chunk=_SHORT_UNTRANSLATED_BLOCK,
        paragraph_regions=None,
    )
    assert without_the_region["decision"] == "fallback_continue"
    assert block_execution.UNTRANSLATED_PROSE_WARNING_KEY in without_the_region


# ---------------------------------------------------------------------------
# FR-A9 -- the narration branch that throws text away
# ---------------------------------------------------------------------------
#
# ``continue_controlled_processed_block_rejection`` has one ``narration_chunks.append``, and
# it sits in the ``else``. The branch above it -- "the fallback delivered the block's own
# source" -- appends nothing at all: the text is DISCARDED, not merely skipped. On the
# 2026-08-06 Money & Sustainability run that branch removed 5 581 characters from the
# audiobook.
#
# Spec 054 decided that source-language text must not reach the narration, and that stands.
# What did not stand is that the branch asked the pair rule WITHOUT asking whether the job
# changes language at all: on a ru->ru literary edit, 65.0% of deliveries are byte-identical
# to their source and every one of them is correct (measurement section 5), so the branch
# would have discarded two thirds of the book from the narration.


def _marker_block(*pairs):
    """The generator's return value for a block: (paragraph_id, text, status)."""
    from docxaicorrector.generation._generation import MarkerPreservedBlockText, ParagraphDisposition

    dispositions = [
        ParagraphDisposition(paragraph_id=paragraph_id, text=text, status=status)
        for paragraph_id, text, status in pairs
    ]
    joined = "\n\n".join(item.text for item in dispositions)
    return MarkerPreservedBlockText(joined, dispositions)


def _narration_harness():
    state = SimpleNamespace(
        processed_chunks=[],
        narration_chunks=[],
        excluded_narration_block_count=0,
        narration_excluded_source_fallback_block_count=0,
        narration_excluded_source_fallback_chars=0,
        narration_excluded_omitted_paragraph_count=0,
        narration_excluded_omitted_chars=0,
        generated_paragraph_registry=[],
    )
    context = SimpleNamespace(
        uploaded_filename="book.docx",
        runtime=object(),
        on_progress=lambda **_kwargs: None,
        source_language="en",
        target_language="ru",
    )
    dependencies = SimpleNamespace(log_event=lambda *_args, **_kwargs: None)
    emitters = SimpleNamespace(
        emit_state=lambda *_args, **_kwargs: None,
        emit_status=lambda *_args, **_kwargs: None,
        emit_log=lambda *_args, **_kwargs: None,
    )
    return state, context, dependencies, emitters


def _continue_fallback(*, target_text, processed_chunk, languages_differ, monkeypatch, narration_include=True):
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    monkeypatch.setattr(block_execution, "persist_terminal_job_result", lambda **_kwargs: None)
    state, context, dependencies, emitters = _narration_harness()
    payload = SimpleNamespace(
        job_kind="llm",
        target_text=target_text,
        target_text_with_markers=target_text,
        paragraph_ids=["p1"],
        paragraph_regions=["prose"],
        narration_include=narration_include,
        target_chars=len(target_text),
        context_chars=0,
    )
    block_execution.continue_controlled_processed_block_rejection(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=SimpleNamespace(job_count=1),
        index=1,
        payload=payload,
        processed_chunk=processed_chunk,
        rejection_kind="source_text_fallback",
        append_marker_registry_entries_fn=lambda **_kwargs: None,
        languages_differ=languages_differ,
    )
    return state


def test_a_same_language_job_no_longer_loses_an_unchanged_block_from_the_narration(monkeypatch) -> None:
    """FR-A9 + FR-A5. The measured case: a literary edit that legitimately left a paragraph
    alone. Before this, the branch read "delivered == source" as "untranslated" and dropped
    the paragraph out of the audiobook without anyone asking what the job was."""
    unchanged = "Это уже хороший абзац, и правка его не улучшит."
    state = _continue_fallback(
        target_text=unchanged,
        processed_chunk=unchanged,
        languages_differ=False,
        monkeypatch=monkeypatch,
    )
    assert state.narration_chunks == [unchanged]
    assert state.narration_excluded_source_fallback_block_count == 0
    assert state.narration_excluded_source_fallback_chars == 0


def test_apparatus_delivered_in_the_source_language_is_still_kept_out_of_the_narration(monkeypatch) -> None:
    """The anti-vacuum half, and spec 054's rule intact: where the job DOES change language,
    a block delivered in the source language still does not reach the audiobook, and the
    characters are still counted. Nothing sits between the audio and the listener."""
    english = "Notes and references for chapter four."
    state = _continue_fallback(
        target_text=english,
        processed_chunk=english,
        languages_differ=True,
        monkeypatch=monkeypatch,
    )
    assert state.narration_chunks == []
    assert state.narration_excluded_source_fallback_block_count == 1
    assert state.narration_excluded_source_fallback_chars == len(english)


def test_a_block_the_region_excludes_is_counted_as_a_region_exclusion(monkeypatch) -> None:
    """The first branch is untouched: a block the document region keeps out of the narration
    is counted there, not as a source-fallback exclusion. The two answer different questions
    and a run report that mixes them cannot be read."""
    english = "Notes and references for chapter four."
    state = _continue_fallback(
        target_text=english,
        processed_chunk=english,
        languages_differ=True,
        monkeypatch=monkeypatch,
        narration_include=False,
    )
    assert state.narration_chunks == []
    assert state.excluded_narration_block_count == 1
    assert state.narration_excluded_source_fallback_block_count == 0


@pytest.mark.parametrize("operation", ["translate", "audiobook"])
def test_source_text_is_never_spoken_in_a_language_changing_operation(operation) -> None:
    """Anti-regression 11 as rewritten by spec 061 FR-009 — and ANTI-VACUUM for FR-006.

    "A paragraph carrying source text is not spoken in a translating operation; ``accepted``
    is always spoken." Both statuses that mean "this is the paragraph's own SOURCE" are held,
    each with its address and its status in the record; the ``accepted`` Russian paragraph
    beside them is spoken, so the rule is shown not to subtract everything.

    The previous wording — ``omitted`` held, ``source_restored`` spoken — protected a
    partial-rescue argument and is what read two English paragraphs (587 characters,
    target-alphabet share 0.000) into the Russian audiobook of ``20260809T_059_audio_money``.
    """
    from docxaicorrector.generation._generation import (
        PARAGRAPH_STATUS_ACCEPTED,
        PARAGRAPH_STATUS_OMITTED,
        PARAGRAPH_STATUS_SOURCE_RESTORED,
    )

    spoken, withheld = block_execution.narration_projection_for_processed_block(
        _marker_block(
            ("p1", "Этот абзац переведён на русский.", PARAGRAPH_STATUS_ACCEPTED),
            ("p2", "English restored after a merge.", PARAGRAPH_STATUS_SOURCE_RESTORED),
            ("p3", "English the model returned nothing for.", PARAGRAPH_STATUS_OMITTED),
        ),
        processing_operation=operation,
    )

    assert spoken == "Этот абзац переведён на русский."
    assert withheld == [
        {"paragraph_id": "p2", "text": "English restored after a merge.", "status": "source_restored"},
        {"paragraph_id": "p3", "text": "English the model returned nothing for.", "status": "omitted"},
    ]


def test_on_edit_a_restored_paragraph_is_spoken_and_an_omitted_one_is_still_held() -> None:
    """FR-007: on ``edit`` nothing changes — ``source_restored`` is a real paragraph of the book.

    And the omission rule spec 056 E introduced keeps holding on every operation it held on.
    """
    from docxaicorrector.generation._generation import (
        PARAGRAPH_STATUS_ACCEPTED,
        PARAGRAPH_STATUS_OMITTED,
        PARAGRAPH_STATUS_SOURCE_RESTORED,
    )

    spoken, withheld = block_execution.narration_projection_for_processed_block(
        _marker_block(
            ("p1", "Отредактированный абзац.", PARAGRAPH_STATUS_ACCEPTED),
            ("p2", "Исходный абзац, восстановленный после слияния.", PARAGRAPH_STATUS_SOURCE_RESTORED),
            ("p3", "14", PARAGRAPH_STATUS_OMITTED),
        ),
        processing_operation="edit",
    )

    assert spoken == "Отредактированный абзац.\n\nИсходный абзац, восстановленный после слияния."
    assert withheld == [{"paragraph_id": "p3", "text": "14", "status": "omitted"}]


# ---------------------------------------------------------------------------
# The wiring: the invariant has to be reachable from the block loop, not only callable
# ---------------------------------------------------------------------------


def _run_block_through_the_loop(*, payload, classification, processed_chunk, context):
    from docxaicorrector.pipeline.block_execution import process_single_block

    state = SimpleNamespace(
        processed_chunks=[],
        narration_chunks=[],
        excluded_narration_block_count=0,
        narration_excluded_source_fallback_block_count=0,
        narration_excluded_source_fallback_chars=0,
        narration_excluded_omitted_paragraph_count=0,
        narration_excluded_omitted_chars=0,
        generated_paragraph_registry=[],
        untranslated_prose_delivered_paragraphs=[],
        started_at=0.0,
    )
    events: list[tuple[int, str, dict]] = []
    rejections: list[dict] = []
    outcome = process_single_block(
        context=context,
        dependencies=SimpleNamespace(
            log_event=lambda level, event, _message, **ctx: events.append((level, event, ctx))
        ),
        emitters=SimpleNamespace(
            emit_state=lambda *_a, **_k: None,
            emit_status=lambda *_a, **_k: None,
            emit_log=lambda *_a, **_k: None,
        ),
        state=state,
        initialization=SimpleNamespace(job_count=1),
        index=1,
        job=object(),
        parse_processing_job_fn=lambda **_kwargs: payload,
        handle_invalid_processing_job_fn=lambda **_kwargs: None,
        emit_block_started_fn=lambda **_kwargs: None,
        is_marker_mode_enabled_fn=lambda _context, _payload: False,
        execute_processing_block_fn=lambda **_kwargs: (processed_chunk, False),
        handle_block_generation_failure_fn=lambda **_kwargs: None,
        classify_processed_block_fn=lambda *_args, **_kwargs: classification,
        handle_processed_block_rejection_fn=lambda **kwargs: rejections.append(kwargs) or "failed",
        append_marker_registry_entries_fn=lambda **_kwargs: None,
        handle_marker_registry_failure_fn=lambda **_kwargs: None,
        emit_block_completed_fn=lambda **_kwargs: None,
    )
    return outcome, state, events, rejections


def test_a_prose_block_delivered_as_its_source_ships_and_is_announced(monkeypatch) -> None:
    """FR-A8 end to end through ``process_single_block``: delivered, loud, and counted.

    Anti-regression 1 in the direction that matters — the rule has to be ABLE to fire. On the
    recorded 2026-08-06 Money & Sustainability run this is the shape of the two blocks that
    shipped English (5 581 characters also missing from the audiobook); a rule that stays
    quiet on that shape is broken.

    What changed on 2026-08-09 is the OUTCOME, not the detection: ``outcome is None`` (the run
    continues) and ``state.processed_chunks`` carries the block, where both used to say the
    opposite. Rule 4 of this change: the volume of delivered text may only grow.
    """
    from docxaicorrector.core import model_accounting

    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    monkeypatch.setattr(block_execution, "persist_terminal_job_result", lambda **_kwargs: None)
    model_accounting.get_run_model_accounting_ledger().reset()
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=_SHORT_UNTRANSLATED_BLOCK,
        target_text_with_markers=_SHORT_UNTRANSLATED_BLOCK,
        paragraph_ids=["p0001"],
        paragraph_regions=["prose"],
        structural_roles=["body"],
        narration_include=True,
        target_chars=len(_SHORT_UNTRANSLATED_BLOCK),
        context_chars=0,
    )
    outcome, state, events, rejections = _run_block_through_the_loop(
        payload=payload,
        classification="source_text_fallback",
        processed_chunk=_SHORT_UNTRANSLATED_BLOCK,
        context=SimpleNamespace(
            processing_operation="translate",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
            source_language="en",
            target_language="ru",
        ),
    )

    assert outcome is None
    assert rejections == []
    assert state.processed_chunks == [_SHORT_UNTRANSLATED_BLOCK]

    announced = [
        (level, context)
        for level, event, context in events
        if event == "block_untranslated_prose_delivered"
    ]
    assert len(announced) == 1
    level, context = announced[0]
    # Constitution V: the level has to mean what it says. The run completed and delivered.
    assert level == logging.WARNING
    assert context["prose_paragraph_count"] == 1
    assert context["rejection_kind"] == "source_text_fallback"
    assert context["source_language"] == "en"
    assert context["delivered_chars"] == len(_SHORT_UNTRANSLATED_BLOCK)

    # The alarm channel gets an addressable record, one entry per delivered block.
    assert [
        [record["paragraph_id"] for record in block]
        for block in state.untranslated_prose_delivered_paragraphs
    ] == [["p0001"]]

    snapshot = model_accounting.get_run_model_accounting_ledger().snapshot()
    assert snapshot["untranslated_prose_block_delivery_count"] == 1
    assert snapshot["untranslated_prose_block_delivery_chars"] == len(_SHORT_UNTRANSLATED_BLOCK)
    assert snapshot["untranslated_prose_block_delivery_kind_counts"] == {"source_text_fallback": 1}
    # SUBSET, not a separate family: the block was shipped, so the fallback family counts it
    # too, and the difference between the two is the apparatus.
    assert snapshot["controlled_block_fallback_block_count"] == 1
    model_accounting.get_run_model_accounting_ledger().reset()


def test_an_apparatus_block_in_the_same_loop_still_ships_and_is_counted_as_a_fallback(monkeypatch) -> None:
    """The anti-vacuum twin of the test above, driven through the same call path so the
    difference is the REGION and nothing else."""
    from docxaicorrector.core import model_accounting

    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    monkeypatch.setattr(block_execution, "persist_terminal_job_result", lambda **_kwargs: None)
    model_accounting.get_run_model_accounting_ledger().reset()
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=_SHORT_UNTRANSLATED_BLOCK,
        target_text_with_markers=_SHORT_UNTRANSLATED_BLOCK,
        paragraph_ids=["p0001"],
        paragraph_regions=["back_matter"],
        narration_include=True,
        target_chars=len(_SHORT_UNTRANSLATED_BLOCK),
        context_chars=0,
    )
    outcome, state, events, rejections = _run_block_through_the_loop(
        payload=payload,
        classification="source_text_fallback",
        processed_chunk=_SHORT_UNTRANSLATED_BLOCK,
        context=SimpleNamespace(
            processing_operation="translate",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
            source_language="en",
            target_language="ru",
        ),
    )

    assert outcome is None
    assert rejections == []
    assert state.processed_chunks == [_SHORT_UNTRANSLATED_BLOCK]
    assert not [event for _level, event, _ctx in events if event == "block_untranslated_prose_delivered"]
    assert state.untranslated_prose_delivered_paragraphs == []

    snapshot = model_accounting.get_run_model_accounting_ledger().snapshot()
    assert snapshot["untranslated_prose_block_delivery_count"] == 0
    assert snapshot["controlled_block_fallback_block_count"] == 1
    model_accounting.get_run_model_accounting_ledger().reset()


# ---------------------------------------------------------------------------
# P0 -- the invariant must not fire on the DEFAULT operation
# ---------------------------------------------------------------------------
#
# Reading only the language codes was wrong, and wrong in the most expensive direction.
# The shipped defaults are ``processing_operation_default = "edit"``,
# ``source_language_default = "en"``, ``target_language_default = "ru"``
# (``resources/config.toml:25-27``), and the UI renders the SOURCE-language selector only
# for two operations (``ui/_ui.py:588``):
#
#     if processing_operation in {"translate", "audiobook"}:
#
# So on a literary edit the user cannot set the source language at all and it stays ``en``
# against a target of ``ru``. Codes alone therefore answer "yes, this job changes language"
# on the DEFAULT path -- where 1 144 of 1 761 recorded deliveries are byte-identical to
# their source and every one of them is correct (measurement section 5). The run would have
# died on the first unchanged paragraph of prose.
#
# The operation is part of the question, not context around it.

_LANGUAGE_CHANGING = ("translate", "audiobook")
_NON_LANGUAGE_CHANGING = ("edit", "", "  ", "unknown_future_operation")


@pytest.mark.parametrize("operation", _NON_LANGUAGE_CHANGING)
def test_an_operation_that_does_not_translate_never_changes_language(operation: str) -> None:
    """P0. The shipped default pair en->ru on a literary edit is a UI artefact, not a job
    that translates: the edit screen has no source-language selector to correct it with."""
    assert (
        block_execution.job_changes_language(
            processing_operation=operation, source_language="en", target_language="ru"
        )
        is False
    )


@pytest.mark.parametrize("operation", _LANGUAGE_CHANGING)
def test_the_two_translating_operations_read_the_codes(operation: str) -> None:
    assert (
        block_execution.job_changes_language(
            processing_operation=operation, source_language="en", target_language="ru"
        )
        is True
    )
    assert (
        block_execution.job_changes_language(
            processing_operation=operation, source_language="ru", target_language="ru"
        )
        is False
    )


def test_language_codes_are_compared_as_languages_not_as_strings() -> None:
    """A region subtag names a variety of the SAME language. ``en`` -> ``en-US`` is a
    reformatting job, not a translation, and comparing raw strings called it one. This is
    BCP-47 structure, not a list of locales."""
    assert (
        block_execution.job_changes_language(
            processing_operation="translate", source_language="en", target_language="en-US"
        )
        is False
    )
    assert (
        block_execution.job_changes_language(
            processing_operation="translate", source_language="EN_gb", target_language=" en "
        )
        is False
    )


def test_an_unnamed_language_is_a_missing_signal_on_either_side() -> None:
    for source, target in (("", "ru"), ("en", ""), ("en", None), (None, None)):
        assert (
            block_execution.job_changes_language(
                processing_operation="translate", source_language=source, target_language=target
            )
            is False
        )


def test_auto_counts_as_a_change_but_only_where_the_user_asked_to_translate() -> None:
    """``auto`` is not a language, so on its own it says nothing. What says something is the
    OPERATION around it: in ``translate``/``audiobook`` the user asserted "put this into
    <target>", so a delivery identical to the source means the model did nothing.

    Measured, and this is what decides it: the recorded ``money_translate_docx`` run --
    the ONLY one of the five on the document path, and therefore the only one that DELIVERS
    untranslated text rather than dropping it -- ran with ``source_language: "auto"``
    (``artifacts/audiobook_final_run/money_translate_docx/run_summary.txt:20``). Treating
    ``auto`` as "unknown, rule off" would have switched the invariant off exactly where the
    loss is delivered.
    """
    assert (
        block_execution.job_changes_language(
            processing_operation="translate", source_language="auto", target_language="ru"
        )
        is True
    )
    assert (
        block_execution.job_changes_language(
            processing_operation="edit", source_language="auto", target_language="ru"
        )
        is False
    )


def test_the_default_edit_run_keeps_an_unchanged_prose_block_instead_of_dying(monkeypatch) -> None:
    """P0 driven through the block loop with the SHIPPED defaults, because the unit test
    above would have passed even while the pipeline computed the flag from codes alone.

    A literary edit that legitimately left a paragraph of prose alone: the run continues,
    the text is delivered, and the narration keeps it.
    """
    from docxaicorrector.core import model_accounting

    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    monkeypatch.setattr(block_execution, "persist_terminal_job_result", lambda **_kwargs: None)
    model_accounting.get_run_model_accounting_ledger().reset()
    unchanged = "Это уже хороший абзац, и правка его не улучшит."
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=unchanged,
        target_text_with_markers=unchanged,
        paragraph_ids=["p0001"],
        paragraph_regions=["prose"],
        narration_include=True,
        target_chars=len(unchanged),
        context_chars=0,
    )
    outcome, state, events, rejections = _run_block_through_the_loop(
        payload=payload,
        classification="source_text_fallback",
        processed_chunk=unchanged,
        context=SimpleNamespace(
            # The shipped defaults, verbatim: resources/config.toml:25-27.
            processing_operation="edit",
            source_language="en",
            target_language="ru",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
    )

    assert outcome is None
    assert rejections == []
    assert state.processed_chunks == [unchanged]
    assert state.narration_chunks == [unchanged]
    assert not [event for _level, event, _ctx in events if event == "block_untranslated_prose_delivered"]
    assert (
        model_accounting.get_run_model_accounting_ledger().snapshot()[
            "untranslated_prose_block_delivery_count"
        ]
        == 0
    )
    model_accounting.get_run_model_accounting_ledger().reset()


def test_the_same_block_on_a_translate_run_is_still_announced(monkeypatch) -> None:
    """Anti-vacuum for the operation gate: the fix must not switch the rule off for everyone.
    Same block, same text, same region -- only the operation differs, and only the operation
    that asked for another language gets the warning."""
    from docxaicorrector.core import model_accounting

    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    monkeypatch.setattr(block_execution, "persist_terminal_job_result", lambda **_kwargs: None)
    model_accounting.get_run_model_accounting_ledger().reset()
    english = "The monetary system is unchanged."
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=english,
        target_text_with_markers=english,
        paragraph_ids=["p0001"],
        paragraph_regions=["prose"],
        structural_roles=["body"],
        narration_include=True,
        target_chars=len(english),
        context_chars=0,
    )
    outcome, state, events, rejections = _run_block_through_the_loop(
        payload=payload,
        classification="source_text_fallback",
        processed_chunk=english,
        context=SimpleNamespace(
            processing_operation="translate",
            source_language="en",
            target_language="ru",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
    )

    assert outcome is None
    assert rejections == []
    assert state.processed_chunks == [english]
    assert [event for _level, event, _ctx in events if event == "block_untranslated_prose_delivered"]
    model_accounting.get_run_model_accounting_ledger().reset()


# ---------------------------------------------------------------------------
# P1 -- a run that stops must say what actually stopped it
# ---------------------------------------------------------------------------


def test_the_rejection_handler_is_told_the_real_reason_not_the_stale_status() -> None:
    """Constitution V, on the ONE reason that can still stop the run at this call site.

    With the invariant demoted to a warning, a quality rejection reaches the handler only when
    the marker substrate is broken, and the reason it must be given is the classifier's own
    ``source_text_fallback``. That was not a key of ``block_failures`` before spec 059, so the
    lookup silently fell through to the ``heading_only_output`` entry and told the user the
    model had returned only a heading.

    The companion assertion — that ``untranslated_prose`` is a key — is deliberately INVERTED
    here: no path reaches this handler with that reason any more, and a catalogue entry for an
    outcome that cannot happen is a sentence kept alive to be believed.
    """
    from docxaicorrector.pipeline import block_failures

    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=_SHORT_UNTRANSLATED_BLOCK,
        target_text_with_markers=_SHORT_UNTRANSLATED_BLOCK,
        # No paragraph ids: the controlled-fallback substrate cannot be built, which is the
        # only remaining ``fail`` on this branch.
        paragraph_ids=[],
        paragraph_regions=["prose"],
        structural_roles=["body"],
        narration_include=True,
        target_chars=len(_SHORT_UNTRANSLATED_BLOCK),
        context_chars=0,
    )
    outcome, _state, _events, rejections = _run_block_through_the_loop(
        payload=payload,
        classification="source_text_fallback",
        processed_chunk=_SHORT_UNTRANSLATED_BLOCK,
        context=SimpleNamespace(
            processing_operation="translate",
            source_language="en",
            target_language="ru",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
    )
    assert outcome == "failed"
    assert rejections[0]["rejection_kind"] == "source_text_fallback"
    assert "source_text_fallback" in block_failures.PROCESSED_BLOCK_REJECTION_MAP
    assert "untranslated_prose" not in block_failures.PROCESSED_BLOCK_REJECTION_MAP


def test_every_status_the_classifier_can_produce_has_its_own_rejection_entry() -> None:
    """The silent ``.get(kind, rejection_map["heading_only_output"])`` default is what let the
    wrong message through, and it will do it again for the next status added to
    ``ProcessedBlockStatus``. Every kind that can reach the handler is named."""
    from docxaicorrector.pipeline import block_failures

    reachable = {
        "empty",
        "source_text_fallback",
        "english_residual_output",
        "heading_only_output",
        "bullet_heading_output",
        "toc_body_concat",
    }
    named = set(block_failures.PROCESSED_BLOCK_REJECTION_MAP) | {"empty"}
    assert reachable <= named, f"unnamed rejection kinds fall through to a wrong message: {reachable - named}"


def test_an_unknown_rejection_kind_is_not_reported_silently(monkeypatch) -> None:
    """Anti-vacuum for the entry above: the default still exists (a run must stop even for a
    kind nobody named), but it is no longer silent."""
    from docxaicorrector.pipeline import block_failures

    logged: list[tuple[int, str, dict]] = []
    presented: list[dict] = []
    dependencies = SimpleNamespace(
        log_event=lambda level, event, _message, **ctx: logged.append((level, event, ctx)),
        present_error=lambda code, exc, title, **kwargs: presented.append(dict(kwargs)) or f"{title}: {exc}",
    )
    block_failures.handle_processed_block_rejection(
        context=SimpleNamespace(uploaded_filename="book.docx", runtime=object()),
        dependencies=dependencies,
        emitters=SimpleNamespace(emit_state=lambda *_a, **_k: None),
        initialization=SimpleNamespace(job_count=1),
        index=1,
        target_chars=10,
        context_chars=0,
        target_text="x",
        processed_chunk="x",
        rejection_kind="a_kind_nobody_named",
        emit_failed_result_fn=lambda **_kwargs: "failed",
    )
    assert [event for _level, event, _ctx in logged if event == "processed_block_rejection_kind_unmapped"]


# ---------------------------------------------------------------------------
# P2 -- the parallel lists must actually be parallel
# ---------------------------------------------------------------------------


def test_a_region_list_of_the_wrong_length_is_refused() -> None:
    """``paragraph_regions`` is defined as parallel to ``paragraph_ids``. Nothing checked it,
    and a short list is the quiet failure: ``["back_matter"]`` against two paragraphs, the
    second of them prose, reads as "all apparatus" and ships the source silently. The
    shipped producer keeps them in step; the CONTRACT has to require it."""
    from docxaicorrector.pipeline.contracts import BlockExecutionPayload
    from docxaicorrector.pipeline.job_parsing import parse_processing_job

    with pytest.raises(ValueError):
        parse_processing_job(
            job={
                "target_text": "Body.",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
                "paragraph_ids": ["p1", "p2"],
                "paragraph_regions": ["back_matter"],
            },
            payload_factory=BlockExecutionPayload,
        )


def test_a_structural_role_list_of_the_wrong_length_is_refused() -> None:
    """The same contract, and the same silence, for the role list that predates this work."""
    from docxaicorrector.pipeline.contracts import BlockExecutionPayload
    from docxaicorrector.pipeline.job_parsing import parse_processing_job

    with pytest.raises(ValueError):
        parse_processing_job(
            job={
                "target_text": "Body.",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
                "paragraph_ids": ["p1", "p2"],
                "structural_roles": ["body"],
            },
            payload_factory=BlockExecutionPayload,
        )


# ---------------------------------------------------------------------------
# Recorded, not fixed: the front-matter guard this call site cannot use
# ---------------------------------------------------------------------------


def test_front_matter_resolution_runs_without_its_documented_gate() -> None:
    """HONEST CHARACTERIZATION of a claim that does not hold at this call site.

    ``_resolve_source_front_matter_boundary`` documents itself as "gated by
    ``first_block_has_body_start`` being False (the document opens with front-matter)". That
    gate reads a preparation diagnostic snapshot, and ``build_editing_jobs`` has none, so
    ``_resolve_paragraph_regions`` passes ``None`` and the gate is INERT: ``"…" in {}`` is
    False, and the resolver falls through to its two rules.

    The failure direction is recorded rather than argued: with no gate the resolver can only
    mark a PREFIX as front matter, up to the first sustained run of body prose. Prose
    mislabelled as apparatus makes the invariant fire LESS, never more -- it can hide a loss,
    it cannot fail a healthy run. That is why this is a recorded residual and not a blocker,
    and it is measured by the four-book run, not argued here.
    """
    from docxaicorrector.core.models import DocumentBlock, ParagraphUnit
    from docxaicorrector.document.semantic_blocks import build_editing_jobs

    body_first = [
        DocumentBlock(paragraphs=[ParagraphUnit(text=_LONG_BODY, role="body", paragraph_id=f"p{index:04d}")])
        for index in range(4)
    ]
    jobs = build_editing_jobs(body_first, max_chars=3000)
    assert [job["paragraph_regions"] for job in jobs] == [["prose"]] * 4
