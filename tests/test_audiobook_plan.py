"""Spec 070 FR-003 / research R2 (WP-D): the block plan of an audiobook -- only the narrated
paragraphs are sent to the model, and the answer is merged back over ALL of the block's ids.

The plan is a pure function of a ``BlockExecutionPayload``; these tests build the payload from
the real document layer (``build_editing_jobs`` -> ``parse_processing_job``) so the producer and
the consumer of the contract are exercised together. The text is invented.
"""

from __future__ import annotations

import pytest

from docxaicorrector.core.models import PARAGRAPH_STATUS_POLICY_KEPT_SOURCE, DocumentBlock, ParagraphUnit
from docxaicorrector.document.semantic_blocks import build_editing_jobs
from docxaicorrector.generation._generation import (
    PARAGRAPH_STATUS_ACCEPTED,
    MarkerPreservedBlockText,
    ParagraphDisposition,
)
from docxaicorrector.pipeline.audiobook_plan import (
    AudiobookBlockPlan,
    build_audiobook_block_plan,
    merge_audiobook_dispositions,
)
from docxaicorrector.pipeline.contracts import BlockExecutionPayload
from docxaicorrector.pipeline.job_parsing import parse_processing_job

_FIRST = "The pilots argued about the chart until the lamps were lit."
_SECOND = "By morning the harbour had agreed on nothing at all."


def _unit(text: str, pid: str, *, role: str = "body", level: int | None = None, structural_role: str | None = None) -> ParagraphUnit:
    return ParagraphUnit(
        text=text, role=role, paragraph_id=pid, heading_level=level, structural_role=structural_role or role
    )


def _mixed_block() -> DocumentBlock:
    return DocumentBlock(
        paragraphs=[
            _unit("One ..... 3", "p0001", structural_role="toc_entry"),
            _unit(_FIRST, "p0002"),
            _unit("Figure 1. A chart of the tides.", "p0003", role="caption"),
            _unit("(i)", "p0004"),
            _unit("Chapter Two", "p0005", role="heading", level=1),
            _unit(_SECOND, "p0006"),
        ]
    )


def _payload(block: DocumentBlock | None = None) -> BlockExecutionPayload:
    (job,) = build_editing_jobs([block or _mixed_block()], max_chars=3000, processing_operation="audiobook")
    return parse_processing_job(job=job, payload_factory=BlockExecutionPayload)


def _plan(block: DocumentBlock | None = None) -> AudiobookBlockPlan:
    plan = build_audiobook_block_plan(_payload(block))
    assert plan is not None
    return plan


def _answer(*pairs: tuple[str, str]) -> MarkerPreservedBlockText:
    dispositions = tuple(
        ParagraphDisposition(paragraph_id=paragraph_id, text=text, status=PARAGRAPH_STATUS_ACCEPTED)
        for paragraph_id, text in pairs
    )
    return MarkerPreservedBlockText("\n\n".join(text for _, text in pairs), dispositions)


# --- T-D6: what is sent ----------------------------------------------------------------------


def test_only_the_narrated_paragraphs_are_sent_in_the_source_order() -> None:
    plan = _plan()

    assert plan.paragraph_ids == ("p0001", "p0002", "p0003", "p0004", "p0005", "p0006")
    assert plan.send_ids == ("p0002", "p0005", "p0006")
    assert plan.send_text_with_markers == (
        f"[[DOCX_PARA_p0002]]\n{_FIRST}\n\n[[DOCX_PARA_p0005]]\n# Chapter Two\n\n[[DOCX_PARA_p0006]]\n{_SECOND}"
    )
    assert plan.send_text == f"{_FIRST}\n\n# Chapter Two\n\n{_SECOND}"
    # Nothing excluded reaches the request, in any form.
    for excluded_text in ("One ..... 3", "Figure 1", "(i)", "DOCX_PARA_p0001", "DOCX_PARA_p0003", "DOCX_PARA_p0004"):
        assert excluded_text not in plan.send_text_with_markers
        assert excluded_text not in plan.send_text


def test_the_source_texts_are_read_back_by_marker_in_the_sent_order() -> None:
    plan = _plan()

    assert plan.send_source_texts == (_FIRST, "# Chapter Two", _SECOND)
    assert [(item.paragraph_id, item.reason, item.source_text) for item in plan.excluded] == [
        ("p0001", "toc", "One ..... 3"),
        ("p0003", "caption", "Figure 1. A chart of the tides."),
        ("p0004", "fragment", "(i)"),
    ]


def test_a_block_with_nothing_excluded_has_no_plan_and_goes_whole() -> None:
    block = DocumentBlock(paragraphs=[_unit(_FIRST, "p0001"), _unit(_SECOND, "p0002")])

    assert build_audiobook_block_plan(_payload(block)) is None


def test_a_payload_without_reasons_or_ids_has_no_plan() -> None:
    payload = _payload()
    no_reasons = BlockExecutionPayload(
        job_kind="llm",
        target_chars=1,
        context_chars=0,
        target_text="x",
        target_text_with_markers=payload.target_text_with_markers,
        paragraph_ids=payload.paragraph_ids,
        context_before="",
        context_after="",
    )
    no_ids = BlockExecutionPayload(
        job_kind="llm",
        target_chars=1,
        context_chars=0,
        target_text="x",
        target_text_with_markers="x",
        paragraph_ids=None,
        context_before="",
        context_after="",
        narration_exclusion_reasons=[],
    )

    assert build_audiobook_block_plan(no_reasons) is None
    assert build_audiobook_block_plan(no_ids) is None


def test_a_block_of_only_excluded_paragraphs_has_a_plan_with_nothing_to_send() -> None:
    block = DocumentBlock(paragraphs=[_unit("One ..... 3", "p0001", structural_role="toc_entry"), _unit("(i)", "p0002")])

    plan = _plan(block)

    assert plan.send_ids == ()
    assert plan.send_text_with_markers == ""
    merged = merge_audiobook_dispositions(plan, MarkerPreservedBlockText("", ()))
    assert [d.status for d in merged.paragraph_dispositions] == [PARAGRAPH_STATUS_POLICY_KEPT_SOURCE] * 2


def test_a_payload_whose_markers_do_not_match_its_ids_is_a_defect_not_a_guess() -> None:
    payload = _payload()
    broken = BlockExecutionPayload(
        job_kind="llm",
        target_chars=1,
        context_chars=0,
        target_text="x",
        target_text_with_markers=payload.target_text_with_markers.replace("[[DOCX_PARA_p0005]]", "[[DOCX_PARA_p0099]]"),
        paragraph_ids=payload.paragraph_ids,
        context_before="",
        context_after="",
        narration_exclusion_reasons=payload.narration_exclusion_reasons,
    )

    with pytest.raises(ValueError):
        build_audiobook_block_plan(broken)


# --- T-D6: the merge -------------------------------------------------------------------------


def test_the_merge_returns_every_id_in_the_source_order_and_excluded_ones_keep_their_source() -> None:
    plan = _plan()
    generated = _answer(("p0002", "Пилоты спорили о карте."), ("p0005", "## Глава вторая"), ("p0006", "К утру порт ни о чём не договорился."))

    merged = merge_audiobook_dispositions(plan, generated)

    assert [d.paragraph_id for d in merged.paragraph_dispositions] == list(plan.paragraph_ids)
    by_id = {d.paragraph_id: d for d in merged.paragraph_dispositions}
    for paragraph_id, source in (
        ("p0001", "One ..... 3"),
        ("p0003", "Figure 1. A chart of the tides."),
        ("p0004", "(i)"),
    ):
        assert by_id[paragraph_id].status == PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
        assert by_id[paragraph_id].text == source
    for paragraph_id in ("p0002", "p0005", "p0006"):
        assert by_id[paragraph_id].status == PARAGRAPH_STATUS_ACCEPTED
    # The text of the block is derived from the record, in the source order.
    assert str(merged) == "\n\n".join(d.text for d in merged.paragraph_dispositions)
    assert str(merged).index("One ..... 3") < str(merged).index("Пилоты")


def test_the_merge_keeps_the_generator_status_of_a_sent_paragraph() -> None:
    plan = _plan()
    generated = MarkerPreservedBlockText(
        "\n\n".join(("a", "b", "c")),
        (
            ParagraphDisposition("p0002", "a", PARAGRAPH_STATUS_ACCEPTED),
            ParagraphDisposition("p0005", _FIRST, "source_restored"),
            ParagraphDisposition("p0006", "c", PARAGRAPH_STATUS_ACCEPTED),
        ),
    )

    merged = merge_audiobook_dispositions(plan, generated)

    assert {d.paragraph_id: d.status for d in merged.paragraph_dispositions}["p0005"] == "source_restored"


@pytest.mark.parametrize(
    "ids",
    [
        ("p0002", "p0005"),  # one missing
        ("p0002", "p0005", "p0006", "p0004"),  # an excluded id came back
        ("p0002", "p0006", "p0005"),  # order changed
        ("p0002", "p0005", "p0007"),  # an id nobody sent
    ],
    ids=["missing", "excluded-returned", "reordered", "foreign"],
)
def test_an_answer_that_does_not_cover_exactly_the_sent_ids_raises(ids: tuple[str, ...]) -> None:
    plan = _plan()
    generated = _answer(*((paragraph_id, "text") for paragraph_id in ids))

    with pytest.raises(ValueError):
        merge_audiobook_dispositions(plan, generated)


def test_a_plain_string_answer_without_the_record_raises() -> None:
    with pytest.raises(ValueError):
        merge_audiobook_dispositions(_plan(), "a\n\nb\n\nc")
