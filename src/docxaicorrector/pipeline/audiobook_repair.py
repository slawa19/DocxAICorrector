"""One-call residue repair for an audiobook block (spec 070 FR-006, research R5).

After the audiobook pass a few paragraphs of a block may still hold text that cannot be read
aloud (digits, signs, addresses). This module spends AT MOST ONE paid call per block to
rewrite those paragraphs and accepts the answer only when it is provably whole: the marker ids
and their order match and no paragraph is empty. On ANY other outcome — a rejected answer, a
network/SDK error, a Stop — the previous text of every requested paragraph is kept.

There is no retry and no degradation ladder: the call goes through ``request_text_completion``
(the auxiliary-call path, ``max_retries=1`` with no retryable errors). The cost of every
response the provider returned, accepted by us or not, is booked under the
``audiobook_repair`` stage at the single accounting point of ``responses.create``; a call
that failed without a response carries no usage and is reported through ``call_made``.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from docxaicorrector.core.config import load_system_prompt
from docxaicorrector.core.model_accounting import STAGE_AUDIOBOOK_REPAIR
from docxaicorrector.generation._generation import (
    PARAGRAPH_STATUS_ACCEPTED,
    MarkerValidationError,
    _build_marker_preserving_user_prompt,
    _build_request_kwargs,
    request_text_completion,
    split_marker_preserved_paragraph_dispositions,
)

REPAIR_CONTEXT_MAX_CHARS = 600

RepairStatus = Literal["accepted", "rejected", "failed", "skipped"]
RepairReason = Literal["marker_mismatch", "empty_paragraph", "error", "stopped"]


@dataclass(frozen=True)
class RepairItem:
    paragraph_id: str
    text: str
    residue_classes: tuple[str, ...]


@dataclass(frozen=True)
class RepairOutcome:
    status: RepairStatus
    reason: RepairReason | None
    texts: Mapping[str, str]
    error_class: str | None
    call_made: bool


def load_repair_system_prompt() -> str:
    """The ``repair`` variant of the audiobook prompt (file owned by the prompt package)."""

    return load_system_prompt(operation="audiobook", prompt_variant="repair")


def _tail(text: str) -> str:
    return text[-REPAIR_CONTEXT_MAX_CHARS:] if len(text) > REPAIR_CONTEXT_MAX_CHARS else text


def _head(text: str) -> str:
    return text[:REPAIR_CONTEXT_MAX_CHARS]


def _class_counts(items: Sequence[RepairItem]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        counts.update(item.residue_classes)
    return dict(sorted(counts.items()))


def repair_block_residue(
    *,
    client: Any,
    model_id: str,
    system_prompt: str,
    items: Sequence[RepairItem],
    context_before: str,
    context_after: str,
    should_stop: Callable[[], bool],
    log_event: Callable[..., object],
    block_index: int,
    filename: str,
    residue_after_by_class: Callable[[Mapping[str, str]], Mapping[str, int]] | None = None,
) -> RepairOutcome:
    """Ask the model once to fix the residue paragraphs of one block; never raises on model faults."""

    previous = {item.paragraph_id: item.text for item in items}
    paragraph_ids = [item.paragraph_id for item in items]
    event_context: dict[str, Any] = {
        "filename": filename,
        "block_index": block_index,
        "paragraph_ids": paragraph_ids,
    }

    def _failed(status: RepairStatus, reason: RepairReason, error_class: str | None, call_made: bool) -> RepairOutcome:
        log_event(
            logging.WARNING,
            "audiobook_repair_failed",
            "Исправление остатка озвучки не принято; оставлен прежний текст.",
            **event_context,
            reason=reason,
            error_class=error_class,
            call_made=call_made,
        )
        return RepairOutcome(status=status, reason=reason, texts=dict(previous), error_class=error_class, call_made=call_made)

    if not items:
        return RepairOutcome(status="skipped", reason=None, texts={}, error_class=None, call_made=False)
    if should_stop():
        return _failed("skipped", "stopped", None, False)

    target_text = "\n\n".join(f"[[DOCX_PARA_{item.paragraph_id}]]\n{item.text}" for item in items)
    user_prompt = _build_marker_preserving_user_prompt(
        target_text=target_text,
        context_before=_tail(context_before),
        context_after=_head(context_after),
    )
    request_kwargs = _build_request_kwargs(
        model=model_id,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        target_text=target_text,
    )
    log_event(
        logging.DEBUG,
        "audiobook_repair_started",
        "Исправление остатка озвучки: вызов модели.",
        **event_context,
        residue_classes=sorted({name for item in items for name in item.residue_classes}),
        model=model_id,
    )
    try:
        # ``should_stop`` is deliberately NOT passed: a Stop is checked before the call only,
        # so it cannot abort the block mid-processing (research R5).
        answer = request_text_completion(client, request_kwargs, usage_stage=STAGE_AUDIOBOOK_REPAIR)
    except Exception as exc:  # noqa: BLE001 - any SDK/network fault keeps the previous text
        return _failed("failed", "error", type(exc).__name__, True)

    try:
        dispositions = split_marker_preserved_paragraph_dispositions(answer, paragraph_ids)
    except MarkerValidationError as exc:
        return _failed("rejected", "marker_mismatch", type(exc).__name__, True)
    except Exception as exc:  # noqa: BLE001 - e.g. MarkerParagraphRecordLost
        return _failed("failed", "error", type(exc).__name__, True)

    if any(d.status != PARAGRAPH_STATUS_ACCEPTED or not d.text.strip() for d in dispositions):
        return _failed("rejected", "empty_paragraph", None, True)

    texts = {d.paragraph_id: d.text for d in dispositions}
    completed: dict[str, Any] = {"residue_before_by_class": _class_counts(items)}
    if residue_after_by_class is not None:
        completed["residue_after_by_class"] = dict(residue_after_by_class(texts))
    log_event(
        logging.INFO,
        "audiobook_repair_completed",
        "Исправление остатка озвучки принято.",
        **event_context,
        **completed,
    )
    return RepairOutcome(status="accepted", reason=None, texts=texts, error_class=None, call_made=True)
