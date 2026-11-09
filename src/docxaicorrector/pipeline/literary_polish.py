"""Spec 069 FR-004: the literary polish (second) pass of a ``translate`` run in ``standard`` mode.

One more model call per translated block, made INSIDE block execution after the first pass was
accepted and before anything else reads the block (the apparatus relabel, footnote restoration,
the paragraph registry, the narration projection): those steps see the final text, and nothing
is imported again (``block_execution.process_single_block`` holds the hook).

What is sent (FR-004 (1), plan O-1): paragraphs the first pass ``accepted`` whose letters are at
least ``TARGET_SCRIPT_MIN_SHARE`` of the target language's script -- a reference left in its own
language by rule D1 is ``accepted`` too, and a same-language polish could translate it with no
predicate seeing it. A block without a per-paragraph record is polished only when it is ONE
paragraph (the one marker is its paragraph id); several unmarked paragraphs are not sent.

What comes back is checked by FORM against the first pass, paragraph by paragraph
(``text/polish_checks.py``, Constitution VII). Any predicate, an answer status other than
``accepted``, a paragraph set or order that differs from what was sent, an exception or a Stop
-- each keeps the first pass. Paragraph statuses never change: the delivered record is the first
pass's ``MarkerPreservedBlockText`` with the polished text where it was accepted, so the
disposition counters stay those of the first pass and are booked once (FR-004 (6)); whatever the
generator books during the call goes to the ``literary_polish`` accounting section through
``pass_counter_scope``.

Rollbacks are written with their texts to ``.run/literary_polish_rollbacks/<run_id>.jsonl``
(``contracts/literary-polish-rollbacks.schema.json``) and announced without texts (LOGGING §1.5).
The pass never fails a block: a write error is a WARNING, a model error is a rollback.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docxaicorrector.core import constants
from docxaicorrector.core.model_accounting import (
    PASS_LITERARY_POLISH,
    STAGE_LITERARY_POLISH,
    STAGE_TEXT_GENERATION,
    pass_counter_scope,
    record_pass_counter,
)
from docxaicorrector.generation._generation import (
    PARAGRAPH_STATUS_ACCEPTED,
    GenerationRequestProfile,
    MarkerPreservedBlockText,
    ParagraphDisposition,
    marker_paragraph_dispositions,
)
from docxaicorrector.pipeline.contracts import LatePhaseStopped
from docxaicorrector.runtime.artifact_retention import (
    LITERARY_POLISH_ROLLBACKS_MAX_AGE_SECONDS,
    LITERARY_POLISH_ROLLBACKS_MAX_COUNT,
    prune_artifact_dir,
)
from docxaicorrector.text.polish_checks import check_polished_paragraph
from docxaicorrector.text.transform_assessment import _script_counts, expected_script_for_language

#: Plan O-1: share of the target script among the letters of a first-pass paragraph.
TARGET_SCRIPT_MIN_SHARE = 0.5

#: Modes whose passes carry a ``GenerationRequestProfile``; ``single`` is today's request.
MODES_WITH_REQUEST_PROFILE = ("standard", "quality")

ROLLBACKS_DIR_NAME = "literary_polish_rollbacks"
ROLLBACK_SCHEMA_VERSION = 1

# Why a paragraph was not sent.
SKIP_NOT_ACCEPTED = "not_accepted"
SKIP_NON_TARGET_SCRIPT = "non_target_script"
SKIP_UNMARKED_BLOCK = "unmarked_block"

# Caller-level rollback reasons of the artifact schema (the paragraph predicates live in
# ``text/polish_checks.py``).
REASON_NOT_ACCEPTED = "not_accepted"
REASON_BLOCK_MARKER_MISMATCH = "block_marker_mismatch"
REASON_PASS_FAILED = "pass_failed"
REASON_STOPPED = "stopped"

# ``literary_polish_block_failed.reason``.
FAILURE_ERROR = "error"
FAILURE_EMPTY = "empty"
FAILURE_STOPPED = "stopped"

DECISION_ACCEPTED = "accepted"
DECISION_ROLLED_BACK = "rolled_back"

# Own counters (flat keys in the accounting section and in ``state.literary_polish_counts``;
# the ``<map>.<key>`` ones are the per-reason maps of ``data-model.md`` §3).
COUNT_SENT_BLOCKS = "sent_block_count"
COUNT_SENT_PARAGRAPHS = "sent_paragraph_count"
COUNT_ACCEPTED_PARAGRAPHS = "accepted_paragraph_count"
COUNT_ROLLED_BACK_PARAGRAPHS = "rolled_back_paragraph_count"
COUNT_BLOCK_ROLLBACKS = "block_rollback_count"
COUNT_FAILED_BLOCKS = "failed_block_count"
COUNT_SKIPPED_UNMARKED_BLOCKS = "skipped_unmarked_block_count"
MAP_ROLLBACK_REASONS = "rollback_reason_counts"
MAP_FAILED_REASONS = "failed_reason_counts"
MAP_SKIPPED_PARAGRAPHS = "skipped_paragraph_counts"
_SCALAR_COUNTERS = (
    COUNT_SENT_BLOCKS,
    COUNT_SENT_PARAGRAPHS,
    COUNT_ACCEPTED_PARAGRAPHS,
    COUNT_ROLLED_BACK_PARAGRAPHS,
    COUNT_BLOCK_ROLLBACKS,
    COUNT_FAILED_BLOCKS,
    COUNT_SKIPPED_UNMARKED_BLOCKS,
)
_MAP_COUNTERS = (MAP_ROLLBACK_REASONS, MAP_FAILED_REASONS, MAP_SKIPPED_PARAGRAPHS)

_MARKER_TEMPLATE = "[[DOCX_PARA_{paragraph_id}]]\n{text}"
_UNSAFE_STEM_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


# --- which pass runs, with which request ----------------------------------------------------------


def _config_text(app_config: object, key: str) -> str:
    getter = getattr(app_config, "get", None)
    try:
        value = getter(key) if callable(getter) else None
    except Exception:
        value = None
    return str(value or "").strip()


def _translation_mode(context: Any) -> str:
    if str(getattr(context, "processing_operation", "") or "") != "translate":
        return ""
    return _config_text(getattr(context, "app_config", None), "translation_mode").lower()


def first_pass_request_profile(
    context: Any, *, usage_stage: str = STAGE_TEXT_GENERATION
) -> GenerationRequestProfile | None:
    """The request profile of the FIRST pass of a ``standard`` / ``quality`` translate run.

    FR-003: the level of the mode's first pass and the multiplier of its model go with every
    call of that pass -- the blocks (``block_execution._generate_block_chunk``) and the run
    glossary (``glossary_phase``). ``None`` for ``single``, ``edit`` and ``audiobook``: their
    callers pass no profile at all and the request stays the one of before (SC-006).
    """

    if _translation_mode(context) not in MODES_WITH_REQUEST_PROFILE:
        return None
    app_config = getattr(context, "app_config", None)
    model = _config_text(app_config, "translation_first_pass_model") or str(getattr(context, "model", "") or "")
    return GenerationRequestProfile.for_model(
        model,
        reasoning_effort=_config_text(app_config, "translation_first_pass_reasoning_effort") or None,
        usage_stage=usage_stage,
    )


def polish_pass_model(context: Any) -> str | None:
    """The model selector of the second pass, or ``None`` when this run has none."""

    if _translation_mode(context) not in MODES_WITH_REQUEST_PROFILE:
        return None
    return _config_text(getattr(context, "app_config", None), "translation_polish_model") or None


def polish_request_profile(context: Any) -> GenerationRequestProfile:
    app_config = getattr(context, "app_config", None)
    return GenerationRequestProfile.for_model(
        polish_pass_model(context) or "",
        reasoning_effort=_config_text(app_config, "translation_polish_reasoning_effort") or None,
        usage_stage=STAGE_LITERARY_POLISH,
    )


def literary_polish_applies(*, context: Any, initialization: Any) -> bool:
    """The run has a second pass: a translate run whose initialization built its client."""

    return (
        polish_pass_model(context) is not None
        and bool(getattr(initialization, "polish_model_id", None))
        and getattr(initialization, "polish_client", None) is not None
    )


# --- what is sent ----------------------------------------------------------------------------------


def target_script_share(text: str, target_language: str | None) -> float:
    """Letters of the target language's script over all classified letters; 0 when unknown."""

    target_script = expected_script_for_language(target_language)
    if target_script is None:
        return 0.0
    counts = _script_counts(text or "")
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return counts.get(target_script, 0) / total


@dataclass(frozen=True)
class PolishSelection:
    """``first_pass``: the block's whole record (a one-paragraph record for an unmarked block of
    one paragraph, ``()`` for an unmarked block of several); ``selected``: what is sent."""

    first_pass: tuple[ParagraphDisposition, ...]
    selected: tuple[ParagraphDisposition, ...]
    skipped_counts: dict[str, int] = field(default_factory=dict)
    has_record: bool = True
    unmarked_block: bool = False


def select_polish_paragraphs(
    processed_chunk: str,
    *,
    paragraph_ids: Sequence[str] | None,
    target_language: str | None,
) -> PolishSelection:
    """FR-004 (1) with plan O-1: ``accepted`` paragraphs mostly in the target script."""

    dispositions = marker_paragraph_dispositions(processed_chunk)
    has_record = dispositions is not None
    if dispositions is None:
        ids = list(paragraph_ids or ())
        text = str(processed_chunk or "").strip()
        if len(ids) != 1 or not text or _PARAGRAPH_BREAK.search(text):
            return PolishSelection(
                first_pass=(),
                selected=(),
                skipped_counts={SKIP_UNMARKED_BLOCK: max(1, len(ids))},
                has_record=False,
                unmarked_block=True,
            )
        dispositions = (ParagraphDisposition(ids[0], text, PARAGRAPH_STATUS_ACCEPTED),)

    selected: list[ParagraphDisposition] = []
    skipped: dict[str, int] = {}
    for disposition in dispositions:
        if disposition.status != PARAGRAPH_STATUS_ACCEPTED:
            reason = SKIP_NOT_ACCEPTED
        elif target_script_share(disposition.text, target_language) < TARGET_SCRIPT_MIN_SHARE:
            reason = SKIP_NON_TARGET_SCRIPT
        else:
            selected.append(disposition)
            continue
        skipped[reason] = skipped.get(reason, 0) + 1
    return PolishSelection(
        first_pass=tuple(dispositions),
        selected=tuple(selected),
        skipped_counts=skipped,
        has_record=has_record,
    )


# --- outcome -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PolishParagraphOutcome:
    paragraph_id: str
    first_pass_text: str
    candidate_text: str | None
    final_text: str
    decision: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolishBlockOutcome:
    processed_chunk: str
    paragraphs: tuple[PolishParagraphOutcome, ...] = ()
    block_rolled_back: bool = False
    failure: str | None = None
    stopped: bool = False


def _assemble(selection: PolishSelection, accepted: Mapping[str, str], first_pass_chunk: str) -> str:
    """The delivered block: the first pass's record with the accepted polished texts.

    Statuses are carried over unchanged. A first pass without a record (one unmarked paragraph)
    stays a plain string, so every consumer reads it exactly as it read the first pass.
    """

    if not accepted:
        return first_pass_chunk
    dispositions = tuple(
        ParagraphDisposition(item.paragraph_id, accepted.get(item.paragraph_id, item.text), item.status)
        for item in selection.first_pass
    )
    if not selection.has_record:
        return dispositions[0].text
    return MarkerPreservedBlockText("\n\n".join(item.text for item in dispositions), dispositions)


# --- counters, artifact, events ---------------------------------------------------------------------


def _count(state: Any, key: str, count: int = 1) -> None:
    if count <= 0:
        return
    record_pass_counter(PASS_LITERARY_POLISH, key, count)
    counts = getattr(state, "literary_polish_counts", None)
    if isinstance(counts, dict):
        counts[key] = counts.get(key, 0) + count


def literary_polish_summary(counts: Mapping[str, int]) -> dict[str, object]:
    """The flat counters as the nested shape of ``data-model.md`` §3; zeros are statements."""

    summary: dict[str, object] = {key: int(counts.get(key, 0)) for key in _SCALAR_COUNTERS}
    for map_name in _MAP_COUNTERS:
        prefix = f"{map_name}."
        summary[map_name] = {
            key[len(prefix):]: int(value) for key, value in sorted(counts.items()) if key.startswith(prefix)
        }
    return summary


def resolve_literary_polish_rollbacks_dir() -> Path:
    """Read at call time, so ``DOCX_AI_RUN_DIR`` (or a test) can move the family."""

    return Path(constants.RUN_DIR) / ROLLBACKS_DIR_NAME


def _artifact_run_id(context: Any) -> str:
    return str(getattr(context, "run_id", "") or "").strip() or "run_without_id"


def literary_polish_rollbacks_path(context: Any) -> Path:
    stem = _UNSAFE_STEM_CHARS.sub("_", _artifact_run_id(context)).strip("._") or "run_without_id"
    return resolve_literary_polish_rollbacks_dir() / f"{stem[:120]}.jsonl"


def _details_summary(details: Mapping[str, object]) -> dict[str, object]:
    """What fired, as numbers only: sizes of the word/token collections, the length ratio."""

    summary: dict[str, object] = {}
    for key, value in details.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            summary[key] = round(float(value), 3) if isinstance(value, float) else value
        elif isinstance(value, (list, tuple, dict)):
            summary[key] = len(value)
    return summary


@dataclass
class _PassCall:
    """Everything one block's second pass needs to report what it did."""

    context: Any
    dependencies: Any
    state: Any
    index: int
    polish_model: str
    reasoning_effort: str | None
    target_language: str
    rows: list[dict[str, object]] = field(default_factory=list)

    def row(
        self,
        *,
        scope: str,
        paragraph_id: str | None,
        reasons: Sequence[str],
        details: Mapping[str, object],
        first_pass_text: str | None,
        candidate_text: str | None,
        final_text: str | None,
    ) -> None:
        self.rows.append(
            {
                "schema_version": ROLLBACK_SCHEMA_VERSION,
                "run_id": _artifact_run_id(self.context),
                "source_token": str(getattr(self.context, "source_token", "") or "") or None,
                "block_index": self.index,
                "scope": scope,
                "paragraph_id": paragraph_id,
                "polish_model": self.polish_model,
                "polish_reasoning_effort": self.reasoning_effort,
                "reasons": list(dict.fromkeys(reasons)),
                "details": dict(details),
                "first_pass_text": first_pass_text,
                "candidate_text": candidate_text,
                "final_text": final_text,
                "target_language": self.target_language,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def write_rows(self) -> str | None:
        """Append this block's rollback lines; never raises (FR-004 (7))."""

        if not self.rows:
            return None
        path = literary_polish_rollbacks_path(self.context)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                for row in self.rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            prune_artifact_dir(
                target_dir=path.parent,
                max_age_seconds=LITERARY_POLISH_ROLLBACKS_MAX_AGE_SECONDS,
                max_count=LITERARY_POLISH_ROLLBACKS_MAX_COUNT,
                glob="*.jsonl",
                emit_log=False,
            )
        except OSError as exc:
            self.dependencies.log_event(
                logging.WARNING,
                "literary_polish_artifact_write_failed",
                "Не удалось записать артефакт откатов литературной шлифовки; блок и прогон не затронуты.",
                run_id=_artifact_run_id(self.context),
                path=str(path),
                error_class=type(exc).__name__,
            )
            return None
        if hasattr(self.state, "literary_polish_artifact_path"):
            self.state.literary_polish_artifact_path = str(path)
        return str(path)

    def announce_paragraph(self, paragraph_id: str, reasons: Sequence[str], details: Mapping[str, object], artifact_path: str | None) -> None:
        self.dependencies.log_event(
            logging.WARNING,
            "literary_polish_paragraph_rolled_back",
            "Литературная шлифовка абзаца отклонена: доставлен текст первого прохода.",
            filename=str(getattr(self.context, "uploaded_filename", "") or ""),
            run_id=_artifact_run_id(self.context),
            block_index=self.index,
            paragraph_id=paragraph_id,
            polish_model=self.polish_model,
            reasons=list(reasons),
            details_summary=_details_summary(details),
            artifact_path=artifact_path,
        )

    def announce_block(self, *, reason: str, error_class: str | None, paragraph_count: int, artifact_path: str | None) -> None:
        self.dependencies.log_event(
            logging.WARNING,
            "literary_polish_block_failed",
            "Литературная шлифовка блока не применена: доставлен первый проход блока.",
            filename=str(getattr(self.context, "uploaded_filename", "") or ""),
            run_id=_artifact_run_id(self.context),
            block_index=self.index,
            polish_model=self.polish_model,
            reason=reason,
            error_class=error_class,
            paragraph_count=paragraph_count,
            artifact_path=artifact_path,
        )


# --- the pass ----------------------------------------------------------------------------------------


def _previous_block_tail(state: Any, length: int) -> str:
    """Plan O-7: the end of the previous block's DELIVERED text, as long as the first pass's
    own context before; cut to a word boundary, never mid-word."""

    chunks = list(getattr(state, "processed_chunks", ()) or ())
    if length <= 0 or not chunks:
        return ""
    previous = str(chunks[-1] or "")
    if len(previous) <= length:
        return previous
    tail = previous[-length:]
    boundary = re.search(r"\s", tail)
    return tail[boundary.end():] if boundary else tail


def _block_rollback(
    call: _PassCall,
    *,
    selection: PolishSelection,
    first_pass_chunk: str,
    reason: str,
    artifact_reason: str,
    details: Mapping[str, object],
    candidate_text: str | None,
    failed: bool,
    stopped: bool = False,
) -> PolishBlockOutcome:
    sent = len(selection.selected)
    _count(call.state, COUNT_ROLLED_BACK_PARAGRAPHS, sent)
    if failed:
        _count(call.state, COUNT_FAILED_BLOCKS)
        _count(call.state, f"{MAP_FAILED_REASONS}.{reason}")
    else:
        _count(call.state, COUNT_BLOCK_ROLLBACKS)
        _count(call.state, f"{MAP_ROLLBACK_REASONS}.{artifact_reason}")
    call.row(
        scope="block",
        paragraph_id=None,
        reasons=(artifact_reason,),
        details=details,
        first_pass_text=None,
        candidate_text=candidate_text,
        final_text=str(first_pass_chunk),
    )
    artifact_path = call.write_rows()
    call.announce_block(
        reason=reason,
        error_class=str(details.get("error_class") or "") or None,
        paragraph_count=sent,
        artifact_path=artifact_path,
    )
    return PolishBlockOutcome(
        processed_chunk=first_pass_chunk,
        paragraphs=tuple(
            PolishParagraphOutcome(
                paragraph_id=item.paragraph_id,
                first_pass_text=item.text,
                candidate_text=None,
                final_text=item.text,
                decision=DECISION_ROLLED_BACK,
                reasons=(artifact_reason,),
            )
            for item in selection.selected
        ),
        block_rolled_back=True,
        failure=reason if failed else None,
        stopped=stopped,
    )


def polish_block(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    system_prompt_fn: Callable[[], str],
) -> PolishBlockOutcome:
    """Run the second pass over one valid first-pass block and return what ships."""

    target_language = str(getattr(context, "target_language", "") or "")
    selection = select_polish_paragraphs(
        processed_chunk,
        paragraph_ids=getattr(payload, "paragraph_ids", None),
        target_language=target_language,
    )
    if selection.unmarked_block:
        _count(state, COUNT_SKIPPED_UNMARKED_BLOCKS)
    for reason, count in selection.skipped_counts.items():
        _count(state, f"{MAP_SKIPPED_PARAGRAPHS}.{reason}", count)
    if not selection.selected:
        return PolishBlockOutcome(processed_chunk=processed_chunk)

    profile = polish_request_profile(context)
    call = _PassCall(
        context=context,
        dependencies=dependencies,
        state=state,
        index=index,
        polish_model=str(getattr(initialization, "polish_model_id", "") or polish_pass_model(context) or ""),
        reasoning_effort=profile.reasoning_effort,
        target_language=target_language,
    )
    sent_ids = [item.paragraph_id for item in selection.selected]
    _count(state, COUNT_SENT_BLOCKS)
    _count(state, COUNT_SENT_PARAGRAPHS, len(sent_ids))

    try:
        system_prompt = system_prompt_fn()
        with pass_counter_scope(PASS_LITERARY_POLISH):
            answer = dependencies.generate_markdown_block(
                client=initialization.polish_client,
                model=initialization.polish_model_id,
                system_prompt=system_prompt,
                target_text="\n\n".join(
                    _MARKER_TEMPLATE.format(paragraph_id=item.paragraph_id, text=item.text) for item in selection.selected
                ),
                context_before=_previous_block_tail(state, len(str(getattr(payload, "context_before", "") or ""))),
                context_after="",
                max_retries=context.max_retries,
                expected_paragraph_ids=sent_ids,
                marker_mode=True,
                block_index=index,
                # "Answer or raise": no ladder, no source substitution -- the first pass is the
                # fallback, and it is already here.
                allow_controlled_source_fallback=False,
                should_stop=lambda: bool(dependencies.should_stop_processing(context.runtime)),
                request_profile=profile,
            )
    except LatePhaseStopped:
        # FR-004 (5): Stop during the second pass keeps the block's first pass and stops the
        # run after it (``run_block_processing_phase`` reads the flag, on the last block too).
        if hasattr(state, "stopped_during_polish"):
            state.stopped_during_polish = True
        return _block_rollback(
            call,
            selection=selection,
            first_pass_chunk=processed_chunk,
            reason=FAILURE_STOPPED,
            artifact_reason=REASON_STOPPED,
            details={"error_class": LatePhaseStopped.__name__},
            candidate_text=None,
            failed=True,
            stopped=True,
        )
    except Exception as exc:
        return _block_rollback(
            call,
            selection=selection,
            first_pass_chunk=processed_chunk,
            reason=FAILURE_ERROR,
            artifact_reason=REASON_PASS_FAILED,
            details={"error_class": type(exc).__name__},
            candidate_text=None,
            failed=True,
        )

    answer_text = str(answer or "")
    if not answer_text.strip():
        return _block_rollback(
            call,
            selection=selection,
            first_pass_chunk=processed_chunk,
            reason=FAILURE_EMPTY,
            artifact_reason=REASON_PASS_FAILED,
            details={"error_class": None},
            candidate_text=answer_text,
            failed=True,
        )
    answered = marker_paragraph_dispositions(answer)
    found_ids = [item.paragraph_id for item in answered] if answered is not None else []
    if (
        answered is None
        or found_ids != sent_ids
        # FR-004 (4), Anti-regression 3: the number of paragraphs is the first pass's.
        or any(_PARAGRAPH_BREAK.search(item.text.strip()) for item in answered)
    ):
        return _block_rollback(
            call,
            selection=selection,
            first_pass_chunk=processed_chunk,
            reason=REASON_BLOCK_MARKER_MISMATCH,
            artifact_reason=REASON_BLOCK_MARKER_MISMATCH,
            details={"expected_paragraph_ids": sent_ids, "found_paragraph_ids": found_ids},
            candidate_text=answer_text,
            failed=False,
        )

    accepted: dict[str, str] = {}
    outcomes: list[PolishParagraphOutcome] = []
    rolled_back: list[tuple[str, tuple[str, ...], dict[str, object]]] = []
    for first, candidate in zip(selection.selected, answered):
        if candidate.status != PARAGRAPH_STATUS_ACCEPTED:
            reasons: tuple[str, ...] = (REASON_NOT_ACCEPTED,)
            details: dict[str, object] = {"candidate_status": candidate.status}
        else:
            result = check_polished_paragraph(first.text, candidate.text, target_language=target_language)
            reasons, details = tuple(result.reasons), dict(result.details)
        if reasons:
            _count(state, COUNT_ROLLED_BACK_PARAGRAPHS)
            for reason in reasons:
                _count(state, f"{MAP_ROLLBACK_REASONS}.{reason}")
            call.row(
                scope="paragraph",
                paragraph_id=first.paragraph_id,
                reasons=reasons,
                details=details,
                first_pass_text=first.text,
                candidate_text=candidate.text,
                final_text=first.text,
            )
            rolled_back.append((first.paragraph_id, reasons, details))
            outcomes.append(
                PolishParagraphOutcome(first.paragraph_id, first.text, candidate.text, first.text, DECISION_ROLLED_BACK, reasons)
            )
            continue
        _count(state, COUNT_ACCEPTED_PARAGRAPHS)
        accepted[first.paragraph_id] = candidate.text
        outcomes.append(
            PolishParagraphOutcome(first.paragraph_id, first.text, candidate.text, candidate.text, DECISION_ACCEPTED)
        )

    if rolled_back:
        artifact_path = call.write_rows()
        for paragraph_id, reasons, details in rolled_back:
            call.announce_paragraph(paragraph_id, reasons, details, artifact_path)
    return PolishBlockOutcome(
        processed_chunk=_assemble(selection, accepted, processed_chunk),
        paragraphs=tuple(outcomes),
    )


def emit_literary_polish_completed(*, context: Any, dependencies: Any, state: Any, initialization: Any) -> None:
    """INFO once per run that had a second pass: its own counters and the artifact's path."""

    if not literary_polish_applies(context=context, initialization=initialization):
        return
    counts = getattr(state, "literary_polish_counts", None)
    dependencies.log_event(
        logging.INFO,
        "literary_polish_completed",
        "Литературная шлифовка прогона завершена.",
        filename=str(getattr(context, "uploaded_filename", "") or ""),
        run_id=_artifact_run_id(context),
        polish_model=str(getattr(initialization, "polish_model_id", "") or ""),
        **literary_polish_summary(counts if isinstance(counts, Mapping) else {}),
        artifact_path=getattr(state, "literary_polish_artifact_path", None),
    )


__all__ = [
    "TARGET_SCRIPT_MIN_SHARE",
    "PolishBlockOutcome",
    "PolishParagraphOutcome",
    "PolishSelection",
    "emit_literary_polish_completed",
    "first_pass_request_profile",
    "literary_polish_applies",
    "literary_polish_rollbacks_path",
    "literary_polish_summary",
    "polish_block",
    "polish_pass_model",
    "polish_request_profile",
    "resolve_literary_polish_rollbacks_dir",
    "select_polish_paragraphs",
    "target_script_share",
]
