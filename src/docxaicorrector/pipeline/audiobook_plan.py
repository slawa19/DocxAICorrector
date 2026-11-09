"""Spec 070 FR-003 / research R2: the plan for ONE audiobook block -- which paragraphs go to the
model, and how the answer is put back together with the ones that do not.

Pure functions over a ``BlockExecutionPayload``; no model call, no I/O, no state. The document
layer decided WHY a paragraph is not narrated (``narration_exclusion_reasons``); this module
only acts on that decision at the request boundary:

* ``build_audiobook_block_plan`` cuts the block's marked source text into paragraphs by their
  ``[[DOCX_PARA_<id>]]`` markers and keeps, in order, the ones the audiobook narrates;
* ``merge_audiobook_dispositions`` rebuilds the block over ALL of its paragraph ids from the
  generator's answer for the sent ones, putting every excluded paragraph back as its own source
  text with the status ``policy_kept_source`` ("kept by policy, not a loss"), the status spec 063
  FR-011 and spec 064 FR-006 already use for apparatus and every consumer already understands.

Who calls it, and when, is the integration work package's (WP-G); nothing here depends on the
generator's retry ladder, which sees exactly the ids that were sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from docxaicorrector.core.models import NARRATION_EXCLUSION_REASONS, PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
from docxaicorrector.generation._generation import MarkerPreservedBlockText, ParagraphDisposition


@dataclass(frozen=True)
class AudiobookExcludedParagraph:
    """A paragraph of the block that is not narrated: its id, why, and its own source text."""

    paragraph_id: str
    reason: str
    source_text: str


@dataclass(frozen=True)
class AudiobookBlockPlan:
    paragraph_ids: tuple[str, ...]
    send_ids: tuple[str, ...]
    send_text_with_markers: str
    send_text: str
    send_source_texts: tuple[str, ...]
    excluded: tuple[AudiobookExcludedParagraph, ...]


def _marker(paragraph_id: str) -> str:
    # The producer's form (``document.semantic_blocks.build_marker_wrapped_block_text``).
    return f"[[DOCX_PARA_{paragraph_id}]]\n"


def _source_texts_by_marker(*, paragraph_ids: list[str], marked_text: str) -> list[str]:
    """The block's own source text per paragraph, read off its marked form by locating each
    expected marker in order. Exact, never repaired: a marker that is not where the producer
    put it is a defect of the code that built the payload, so it raises."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for paragraph_id in paragraph_ids:
        marker = _marker(paragraph_id)
        position = marked_text.find(marker, cursor)
        if position < 0:
            raise ValueError(f"audiobook plan: marker of paragraph {paragraph_id!r} is missing or out of order")
        spans.append((position, position + len(marker)))
        cursor = position + len(marker)
    if marked_text[: spans[0][0]].strip():
        raise ValueError("audiobook plan: text in front of the first paragraph marker")
    return [
        marked_text[end : (spans[order + 1][0] if order + 1 < len(spans) else len(marked_text))].strip()
        for order, (_, end) in enumerate(spans)
    ]


def build_audiobook_block_plan(payload: Any) -> AudiobookBlockPlan | None:
    """The plan for this block, or ``None`` when nothing in it is excluded (the block goes to the
    model whole, exactly as before) or the payload carries no paragraph ids to address.

    The request carries only the ids this returns in ``send_ids``; a block whose paragraphs are
    ALL excluded is a passthrough job and never reaches here with a model call to make, but the
    plan is still well-defined for it (empty ``send_ids``).
    """
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    reasons = getattr(payload, "narration_exclusion_reasons", None)
    if not isinstance(paragraph_ids, list) or not paragraph_ids or not isinstance(reasons, list):
        return None
    if len(reasons) != len(paragraph_ids):
        raise ValueError(
            "narration_exclusion_reasons must be parallel to paragraph_ids: "
            f"{len(reasons)} entries against {len(paragraph_ids)} paragraphs"
        )
    unknown = sorted({reason for reason in reasons if reason is not None and reason not in NARRATION_EXCLUSION_REASONS})
    if unknown:
        raise ValueError(f"narration_exclusion_reasons carries unknown reasons: {unknown}")
    if all(reason is None for reason in reasons):
        return None

    ids = [str(paragraph_id) for paragraph_id in paragraph_ids]
    texts = _source_texts_by_marker(
        paragraph_ids=ids, marked_text=str(getattr(payload, "target_text_with_markers", "") or "")
    )
    send_ids: list[str] = []
    send_texts: list[str] = []
    excluded: list[AudiobookExcludedParagraph] = []
    for paragraph_id, reason, text in zip(ids, reasons, texts):
        if reason is None:
            send_ids.append(paragraph_id)
            send_texts.append(text)
        else:
            excluded.append(AudiobookExcludedParagraph(paragraph_id=paragraph_id, reason=reason, source_text=text))
    return AudiobookBlockPlan(
        paragraph_ids=tuple(ids),
        send_ids=tuple(send_ids),
        send_text_with_markers="\n\n".join(
            f"{_marker(paragraph_id)}{text}" for paragraph_id, text in zip(send_ids, send_texts)
        ).strip(),
        send_text="\n\n".join(send_texts),
        send_source_texts=tuple(send_texts),
        excluded=tuple(excluded),
    )


def merge_audiobook_dispositions(plan: AudiobookBlockPlan, generated: str) -> MarkerPreservedBlockText:
    """The block over ALL of its paragraph ids, in the source order.

    ``generated`` is the generator's answer for the SENT paragraphs: a marker-preserved block
    whose per-paragraph record names exactly ``plan.send_ids`` in order. Anything else is a defect
    of the calling code, not of the model (the generator validated its own answer against the ids
    it was given), so it raises. Every excluded paragraph is put back as its source text with the
    status ``policy_kept_source``; the text of the result is derived from the record, as everywhere
    else in the generator (``MarkerPreservedBlockText`` is a transport, never a place to compute).
    """
    generated_dispositions = getattr(generated, "paragraph_dispositions", None)
    if not isinstance(generated_dispositions, tuple):
        raise ValueError("audiobook plan: the generated block carries no per-paragraph record")
    generated_ids = tuple(disposition.paragraph_id for disposition in generated_dispositions)
    if generated_ids != plan.send_ids:
        raise ValueError(
            f"audiobook plan: the answer covers {list(generated_ids)} but the request sent {list(plan.send_ids)}"
        )
    answers = {disposition.paragraph_id: disposition for disposition in generated_dispositions}
    excluded = {item.paragraph_id: item for item in plan.excluded}
    merged: list[ParagraphDisposition] = []
    for paragraph_id in plan.paragraph_ids:
        if paragraph_id in excluded:
            merged.append(
                ParagraphDisposition(
                    paragraph_id=paragraph_id,
                    text=excluded[paragraph_id].source_text,
                    status=PARAGRAPH_STATUS_POLICY_KEPT_SOURCE,
                )
            )
        else:
            merged.append(answers[paragraph_id])
    return MarkerPreservedBlockText("\n\n".join(disposition.text for disposition in merged), merged)
