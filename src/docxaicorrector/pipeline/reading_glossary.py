"""Spec 073 FR-004: the reading glossary of an audiobook run -- one step before the first block.

Every block of the audiobook is prepared by its own call, which cannot see the others, so an
abbreviation was read one way in one chapter and another way in the next. This step fixes ONE
reading per abbreviation for the whole book; each block then receives the entries of its own source
(``reading_section_for_block``) at the end of its system prompt (the wiring is ``pipeline/setup.py`` and
``pipeline/block_execution.py``).

Candidates are found by FORM, not by a list (Constitution VII): a unit of letters (with hyphens,
apostrophes and decimal digits inside) that has at least two capital letters and more capitals than
small letters, read off the narrated paragraphs of the source -- never a roman numeral, never inside a
web address, never a word of a paragraph set wholly in capitals.

A MANDATORY step (owner decision 2026-11-10): the candidates go in batches of
``READING_GLOSSARY_BATCH_SIZE``; each batch is retried by the policy of the block call
(``context.max_retries`` attempts, the same retry predicates, the same pause
``generation._generation.retry_backoff_seconds``); the candidates left without an accepted reading
are asked ONCE more. A batch that gets no usable answer after all its attempts raises
``ReadingGlossaryUnavailable``, and the phase fails the run the way an unrecoverable block call does
(``pipeline/block_failures.py``, ``handle_block_generation_failure``). There is no "book without a
glossary" branch.

Nothing here keeps state between runs: the glossary lives in the run's ``ProcessingState`` and in the
run's artifact. Spellings and readings never go to the log (LOGGING §1.5) -- only to the artifact.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from docxaicorrector.core.constants import PROMPTS_DIR
from docxaicorrector.core.model_accounting import STAGE_AUDIOBOOK_READING_GLOSSARY
from docxaicorrector.document.segments import GlossaryTerm, render_glossary_prompt_section
from docxaicorrector.generation._generation import (
    _INCOMPLETE_RESPONSE_RETRY_MIN_OUTPUT_TOKENS,
    _boost_request_output_budget,
    _is_incomplete_response_error,
    _is_non_completed_response_error,
    _is_retryable_empty_generation_error,
    request_text_completion,
    retry_backoff_seconds,
)
from docxaicorrector.generation.model_response import CollapsedOutput, EmptyResponse
from docxaicorrector.image.shared import is_retryable_error
from docxaicorrector.pipeline.audiobook_pass import _block_source_texts, is_audiobook_operation
from docxaicorrector.pipeline.contracts import BlockExecutionPayload, LatePhaseStopped, PipelineResult
from docxaicorrector.pipeline.glossary_phase import _stage_usage, _write_run_glossary_artifact
from docxaicorrector.pipeline.job_parsing import parse_processing_job
from docxaicorrector.text.glossary_pass import (
    GlossaryResponseError,
    _load_json_object,
    _request_envelope,
    glossary_max_output_tokens,
)
from docxaicorrector.text.narration_forms import is_latin_letter, letter_series
from docxaicorrector.text.narration_residue import is_all_caps_paragraph, is_roman_numeral_form, mask_url_or_domain

__all__ = [
    "READING_GLOSSARY_BATCH_SIZE",
    "READING_GLOSSARY_CONTEXT_CHARS",
    "READING_GLOSSARY_MAX_CANDIDATES",
    "READING_GLOSSARY_SCHEMA",
    "READING_GLOSSARY_SECTION_HEADER",
    "READING_GLOSSARY_SECTION_MAX_CHARS",
    "READING_GLOSSARY_STATUSES",
    "READING_REJECTION_REASONS",
    "READING_UNAVAILABLE_REASONS",
    "ReadingCandidate",
    "ReadingEntry",
    "ReadingGlossary",
    "ReadingGlossaryUnavailable",
    "ReadingParagraph",
    "extract_reading_candidates",
    "narrated_source_paragraphs",
    "parse_reading_glossary_response",
    "reading_candidate_units",
    "reading_paragraphs_from_jobs",
    "reading_section_for_block",
    "run_reading_glossary",
    "run_reading_glossary_phase",
]

# Three times the 67 distinct candidates of the longest corpus book (research R4).
READING_GLOSSARY_MAX_CANDIDATES = 200
READING_GLOSSARY_CONTEXT_CHARS = 160
# Up to 7 entries a block on the corpus is ~350 characters (research R6).
READING_GLOSSARY_SECTION_MAX_CHARS = 2000
READING_GLOSSARY_SECTION_HEADER = (
    "КАК ЧИТАТЬ СОКРАЩЕНИЯ ЭТОЙ КНИГИ (каждое сокращение из списка читайте ровно так; "
    "если чтение — слово, склоняйте его по смыслу):"
)
READING_GLOSSARY_SCHEMA = "audiobook_reading_glossary/v1"
# One batch answers in ~1 000 tokens against the 4 096 of ``glossary_max_output_tokens(40)`` (research R5).
READING_GLOSSARY_BATCH_SIZE = 40
READING_GLOSSARY_PROMPT_FILE = "audiobook_reading_glossary.txt"

READING_GLOSSARY_STATUS_BUILT = "built"
READING_GLOSSARY_STATUS_NO_CANDIDATES = "no_candidates"
READING_GLOSSARY_STATUS_STOPPED = "stopped"
# Owner decision 2026-11-10: no ``partial`` / ``empty`` / ``failed`` -- an unavailable model is an
# exception (``ReadingGlossaryUnavailable``), not a status.
READING_GLOSSARY_STATUSES = (
    READING_GLOSSARY_STATUS_BUILT,
    READING_GLOSSARY_STATUS_NO_CANDIDATES,
    READING_GLOSSARY_STATUS_STOPPED,
)
READING_REJECTION_REASONS = ("not_a_candidate", "empty_reading", "latin_in_reading", "digit_in_reading", "duplicate")
# The last reason of the batch that ran out of attempts; a transport error not recognised as
# retryable is ``error`` at once.
READING_UNAVAILABLE_REASONS = ("error", "empty_response", "no_json", "invalid_json", "invalid_shape", "prompt_unavailable")

_PASS_FIRST = "first"
_PASS_REREQUEST = "rerequest"
_ERROR_STAGE = "Ошибка обработки"
_ERROR_TITLE = "Ошибка словаря чтения сокращений"


# ---------------------------------------------------------------------------------------------
# Entities (data-model §4)
# ---------------------------------------------------------------------------------------------


class ReadingGlossaryUnavailable(RuntimeError):
    """A batch got no usable answer after all its attempts: the run fails like an unrecoverable block."""

    def __init__(
        self,
        reason: str,
        *,
        batch_index: int,
        attempts: int,
        error_class: str | None,
        candidate_count: int = 0,
        sent_count: int = 0,
        artifact_path: str | None = None,
    ) -> None:
        super().__init__(
            f"reading glossary model unavailable: batch {batch_index} after {attempts} attempt(s) ({reason})"
        )
        self.reason = reason
        self.batch_index = batch_index
        self.attempts = attempts
        self.error_class = error_class
        self.candidate_count = candidate_count
        self.sent_count = sent_count
        self.artifact_path = artifact_path


@dataclass(frozen=True)
class ReadingParagraph:
    """The source of one narrated paragraph."""

    paragraph_id: str
    block_index: int
    text: str


@dataclass(frozen=True)
class ReadingCandidate:
    abbreviation: str
    occurrences: int
    first_block_index: int
    # Only for the request: up to READING_GLOSSARY_CONTEXT_CHARS around the first occurrence.
    context: str
    # False: dropped by READING_GLOSSARY_MAX_CANDIDATES.
    sent: bool


@dataclass(frozen=True)
class ReadingEntry:
    abbreviation: str
    reading: str


@dataclass(frozen=True)
class ReadingGlossary:
    status: str
    candidates: tuple[ReadingCandidate, ...] = ()
    # Accepted, in the order of the answers.
    entries: tuple[ReadingEntry, ...] = ()
    rejected_by_reason: Mapping[str, int] = field(default_factory=dict)
    rerequested: tuple[str, ...] = ()
    # Without a reading after the re-request too (artifact only, never the log).
    unresolved: tuple[str, ...] = ()
    batch_count: int = 0
    call_count: int = 0
    retry_count: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    artifact_path: str | None = None

    def entry_for(self, abbreviation: str) -> ReadingEntry | None:
        return next((entry for entry in self.entries if entry.abbreviation == abbreviation), None)


# ---------------------------------------------------------------------------------------------
# Candidates by form (research R4)
# ---------------------------------------------------------------------------------------------


def reading_candidate_units(text: str) -> tuple[str, ...]:
    """The candidate units of one paragraph, in order, repeats kept; exact spellings."""

    if not text or is_all_caps_paragraph(text):
        return ()
    units: list[str] = []
    for series in letter_series(mask_url_or_domain(text), digits_inside=True):
        capitals = sum(1 for character in series.text if character.isupper())
        smalls = sum(1 for character in series.text if character.islower())
        if capitals >= 2 and capitals > smalls and not is_roman_numeral_form(series.text):
            units.append(series.text)
    return tuple(units)


def _context_around(text: str, start: int, end: int) -> str:
    width = READING_GLOSSARY_CONTEXT_CHARS
    lead = max(0, (width - (end - start)) // 2)
    window_start = max(0, min(start - lead, len(text) - width))
    return " ".join(text[window_start : window_start + width].split())


def _first_occurrence_context(text: str, abbreviation: str) -> str:
    masked = mask_url_or_domain(text)
    for series in letter_series(masked, digits_inside=True):
        if series.text == abbreviation:
            return _context_around(text, series.start, series.end)
    return " ".join(text.split())[:READING_GLOSSARY_CONTEXT_CHARS]


def extract_reading_candidates(paragraphs: Sequence[ReadingParagraph]) -> tuple[ReadingCandidate, ...]:
    """Every distinct candidate of the paragraphs: by frequency (descending), then by first appearance;
    the first ``READING_GLOSSARY_MAX_CANDIDATES`` are sent."""

    counts: dict[str, int] = {}
    first_seen: dict[str, tuple[int, ReadingParagraph]] = {}
    for paragraph in paragraphs:
        for unit in reading_candidate_units(paragraph.text):
            counts[unit] = counts.get(unit, 0) + 1
            if unit not in first_seen:
                first_seen[unit] = (len(first_seen), paragraph)
    ordered = sorted(counts, key=lambda unit: (-counts[unit], first_seen[unit][0]))
    return tuple(
        ReadingCandidate(
            abbreviation=unit,
            occurrences=counts[unit],
            first_block_index=first_seen[unit][1].block_index,
            context=_first_occurrence_context(first_seen[unit][1].text, unit),
            sent=position < READING_GLOSSARY_MAX_CANDIDATES,
        )
        for position, unit in enumerate(ordered)
    )


# ---------------------------------------------------------------------------------------------
# The answer
# ---------------------------------------------------------------------------------------------


def _empty_rejections() -> dict[str, int]:
    return {reason: 0 for reason in READING_REJECTION_REASONS}


def parse_reading_glossary_response(
    raw_text: str, *, sent: Sequence[ReadingCandidate]
) -> tuple[tuple[ReadingEntry, ...], dict[str, int]]:
    """``(accepted entries, rejections by reason)``. An answer that is not JSON or carries no
    ``readings`` list raises ``GlossaryResponseError`` (``empty_response`` / ``no_json`` /
    ``invalid_json`` / ``invalid_shape``) -- the batch is asked again."""

    payload = _load_json_object(raw_text)
    readings = payload.get("readings")
    if not isinstance(readings, list):
        raise GlossaryResponseError("invalid_shape", "reading glossary answer has no 'readings' list")
    sent_spellings = {candidate.abbreviation for candidate in sent}
    rejected = _empty_rejections()
    accepted: dict[str, ReadingEntry] = {}
    for item in readings:
        abbreviation = item.get("abbreviation") if isinstance(item, Mapping) else None
        if not isinstance(abbreviation, str) or abbreviation not in sent_spellings:
            rejected["not_a_candidate"] += 1
            continue
        if abbreviation in accepted:
            rejected["duplicate"] += 1
            continue
        raw_reading = item.get("reading") if isinstance(item, Mapping) else None
        reading = raw_reading.strip() if isinstance(raw_reading, str) else ""
        if not reading:
            rejected["empty_reading"] += 1
        elif any(is_latin_letter(character) for character in reading):
            rejected["latin_in_reading"] += 1
        elif any(character.isdecimal() for character in reading):
            rejected["digit_in_reading"] += 1
        else:
            accepted[abbreviation] = ReadingEntry(abbreviation=abbreviation, reading=reading)
    return tuple(accepted.values()), rejected


# ---------------------------------------------------------------------------------------------
# The step (research R5)
# ---------------------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_reading_glossary_instructions() -> str:
    return (PROMPTS_DIR / READING_GLOSSARY_PROMPT_FILE).read_text(encoding="utf-8").strip()


def _failure_reason(exc: Exception) -> str:
    if isinstance(exc, GlossaryResponseError):
        return exc.code if exc.code in READING_UNAVAILABLE_REASONS else "invalid_shape"
    if isinstance(exc, (EmptyResponse, CollapsedOutput)):
        return "empty_response"
    return "error"


def _is_retryable(exc: Exception) -> bool:
    """The block call's predicates (``generation/_generation.py``, the attempt loop of
    ``generate_markdown_block``) plus an unusable answer -- the analogue of the block's retry on an
    answer it cannot use."""

    return (
        isinstance(exc, GlossaryResponseError)
        or is_retryable_error(exc)
        or _is_retryable_empty_generation_error(exc)
        or _is_non_completed_response_error(exc)
    )


@dataclass
class _StepLedger:
    accepted: dict[str, ReadingEntry] = field(default_factory=dict)
    rejected: dict[str, int] = field(default_factory=_empty_rejections)
    batches: list[dict[str, object]] = field(default_factory=list)
    call_count: int = 0
    retry_count: int = 0


class _Stopped(Exception):
    pass


def _ask_batch(
    batch: Sequence[ReadingCandidate],
    *,
    pass_name: str,
    ledger: _StepLedger,
    instructions: str,
    client: Any,
    model_id: str,
    max_retries: int,
    should_stop: Callable[[], bool],
    request_text_completion_fn: Callable[..., str],
    sleep_fn: Callable[[float], object],
) -> None:
    batch_index = len(ledger.batches) + 1
    record: dict[str, object] = {"index": batch_index, "pass": pass_name, "size": len(batch), "attempts": 0}
    ledger.batches.append(record)
    request = _request_envelope(
        model=model_id,
        instructions=instructions,
        payload={
            "candidates": [
                {"abbreviation": item.abbreviation, "occurrences": item.occurrences, "context": item.context}
                for item in batch
            ]
        },
        max_output_tokens=glossary_max_output_tokens(len(batch)),
    )
    attempts_allowed = max(1, int(max_retries))
    for attempt in range(1, attempts_allowed + 1):
        if should_stop():
            raise _Stopped()
        record["attempts"] = attempt
        ledger.call_count += 1
        try:
            raw_text = request_text_completion_fn(
                client, request, usage_stage=STAGE_AUDIOBOOK_READING_GLOSSARY, should_stop=should_stop
            )
            entries, rejected = parse_reading_glossary_response(raw_text, sent=batch)
        except LatePhaseStopped:
            raise _Stopped() from None
        except Exception as exc:
            if attempt >= attempts_allowed or not _is_retryable(exc):
                raise ReadingGlossaryUnavailable(
                    _failure_reason(exc),
                    batch_index=batch_index,
                    attempts=attempt,
                    error_class=type(exc).__name__,
                ) from exc
            ledger.retry_count += 1
            if _is_incomplete_response_error(exc):
                request = _boost_request_output_budget(
                    request, minimum_tokens=_INCOMPLETE_RESPONSE_RETRY_MIN_OUTPUT_TOKENS
                )
            sleep_fn(retry_backoff_seconds(attempt))
            continue
        for reason, count in rejected.items():
            ledger.rejected[reason] += count
        for entry in entries:
            ledger.accepted.setdefault(entry.abbreviation, entry)
        return


def _batches(candidates: Sequence[ReadingCandidate]) -> list[tuple[ReadingCandidate, ...]]:
    size = READING_GLOSSARY_BATCH_SIZE
    return [tuple(candidates[start : start + size]) for start in range(0, len(candidates), size)]


def _artifact_payload(
    *,
    filename: str,
    run_id: str,
    model_id: str,
    status: str | None,
    candidates: Sequence[ReadingCandidate],
    ledger: _StepLedger,
    rerequested: Sequence[str],
    unresolved: Sequence[str],
    usage: Mapping[str, object],
    failure: Mapping[str, object] | None = None,
) -> dict[str, object]:
    rerequested_set = set(rerequested)
    payload: dict[str, object] = {
        "schema": READING_GLOSSARY_SCHEMA,
        "filename": filename,
        "run_id": run_id,
        "model": model_id,
        "status": status,
        "candidates": [
            {
                "abbreviation": item.abbreviation,
                "occurrences": item.occurrences,
                "sent": item.sent,
                "rerequested": item.abbreviation in rerequested_set,
                "resolved": item.abbreviation in ledger.accepted,
            }
            for item in candidates
        ],
        "readings": [{"abbreviation": entry.abbreviation, "reading": entry.reading} for entry in ledger.accepted.values()],
        "unresolved": list(unresolved),
        "rejected_by_reason": dict(ledger.rejected),
        "batches": [dict(item) for item in ledger.batches],
        "usage": {key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "cost_usd")},
    }
    if failure is not None:
        payload["failure"] = dict(failure)
    return payload


def _write_artifact(
    payload: Mapping[str, object],
    *,
    write_artifact_fn: Callable[..., str],
    artifact_context: Any,
    log_event: Callable[..., object],
    filename: str,
) -> str | None:
    try:
        return write_artifact_fn(payload, context=artifact_context)
    except Exception as exc:
        # The family's event (``pipeline/glossary_phase.py``): the glossary itself is not touched.
        log_event(
            logging.WARNING,
            "run_glossary_artifact_write_failed",
            "Не удалось сохранить артефакт словаря чтения; словарь и прогон не затронуты.",
            filename=filename,
            schema=READING_GLOSSARY_SCHEMA,
            error_type=type(exc).__name__,
            error_message=" ".join(str(exc).split())[:120],
        )
        return None


def run_reading_glossary(
    *,
    paragraphs: Sequence[ReadingParagraph],
    client: Any,
    model_id: str,
    max_retries: int,
    should_stop: Callable[[], bool],
    log_event: Callable[..., object],
    filename: str,
    artifact_context: Any,
    request_text_completion_fn: Callable[..., str] = request_text_completion,
    sleep_fn: Callable[[float], object] = time.sleep,
    write_artifact_fn: Callable[..., str] = _write_run_glossary_artifact,
) -> ReadingGlossary:
    """Build the reading glossary of one run. Raises ``ReadingGlossaryUnavailable`` when the model is
    unavailable after all the attempts of a batch (the artifact with what was accepted is written first)."""

    candidates = extract_reading_candidates(paragraphs)
    sent = [item for item in candidates if item.sent]
    run_id = str(getattr(artifact_context, "run_id", "") or "")
    ledger = _StepLedger()

    if not sent:
        glossary = ReadingGlossary(status=READING_GLOSSARY_STATUS_NO_CANDIDATES, candidates=candidates)
        _log_built(log_event, glossary=glossary, filename=filename)
        return glossary

    def stopped() -> ReadingGlossary:
        return ReadingGlossary(
            status=READING_GLOSSARY_STATUS_STOPPED,
            candidates=candidates,
            entries=tuple(ledger.accepted.values()),
            rejected_by_reason=dict(ledger.rejected),
            batch_count=len(ledger.batches),
            call_count=ledger.call_count,
            retry_count=ledger.retry_count,
        )

    if should_stop():
        return stopped()

    rerequested: list[str] = []
    try:
        try:
            instructions = _load_reading_glossary_instructions()
        except OSError as exc:
            raise ReadingGlossaryUnavailable(
                "prompt_unavailable", batch_index=0, attempts=0, error_class=type(exc).__name__
            ) from exc

        def ask(batch: Sequence[ReadingCandidate], pass_name: str) -> None:
            _ask_batch(
                batch,
                pass_name=pass_name,
                ledger=ledger,
                instructions=instructions,
                client=client,
                model_id=model_id,
                max_retries=max_retries,
                should_stop=should_stop,
                request_text_completion_fn=request_text_completion_fn,
                sleep_fn=sleep_fn,
            )

        for batch in _batches(sent):
            ask(batch, _PASS_FIRST)
        # One re-request of everything the first pass left without an accepted reading.
        left = [item for item in sent if item.abbreviation not in ledger.accepted]
        rerequested = [item.abbreviation for item in left]
        for batch in _batches(left):
            ask(batch, _PASS_REREQUEST)
    except _Stopped:
        return stopped()
    except ReadingGlossaryUnavailable as exc:
        exc.candidate_count = len(candidates)
        exc.sent_count = len(sent)
        if ledger.call_count:
            payload = _artifact_payload(
                filename=filename,
                run_id=run_id,
                model_id=model_id,
                status=None,
                candidates=candidates,
                ledger=ledger,
                rerequested=rerequested,
                unresolved=(),
                usage=_stage_usage(stage_name=STAGE_AUDIOBOOK_READING_GLOSSARY),
                failure={
                    "reason": exc.reason,
                    "batch_index": exc.batch_index,
                    "attempts": exc.attempts,
                    "error_class": exc.error_class,
                },
            )
            exc.artifact_path = _write_artifact(
                payload,
                write_artifact_fn=write_artifact_fn,
                artifact_context=artifact_context,
                log_event=log_event,
                filename=filename,
            )
        raise

    unresolved = tuple(item.abbreviation for item in sent if item.abbreviation not in ledger.accepted)
    usage = _stage_usage(stage_name=STAGE_AUDIOBOOK_READING_GLOSSARY)
    artifact_path = _write_artifact(
        _artifact_payload(
            filename=filename,
            run_id=run_id,
            model_id=model_id,
            status=READING_GLOSSARY_STATUS_BUILT,
            candidates=candidates,
            ledger=ledger,
            rerequested=rerequested,
            unresolved=unresolved,
            usage=usage,
        ),
        write_artifact_fn=write_artifact_fn,
        artifact_context=artifact_context,
        log_event=log_event,
        filename=filename,
    )
    glossary = ReadingGlossary(
        status=READING_GLOSSARY_STATUS_BUILT,
        candidates=candidates,
        entries=tuple(ledger.accepted.values()),
        rejected_by_reason=dict(ledger.rejected),
        rerequested=tuple(rerequested),
        unresolved=unresolved,
        batch_count=len(ledger.batches),
        call_count=ledger.call_count,
        retry_count=ledger.retry_count,
        prompt_tokens=_optional_int(usage.get("prompt_tokens")),
        completion_tokens=_optional_int(usage.get("completion_tokens")),
        cost_usd=_optional_float(usage.get("cost_usd")),
        artifact_path=artifact_path,
    )
    _log_built(log_event, glossary=glossary, filename=filename)
    if unresolved:
        log_event(
            logging.WARNING,
            "audiobook_reading_glossary_unresolved",
            "Часть сокращений осталась без чтения и после повторного запроса; для них действует правило промпта.",
            filename=filename,
            review_data=True,
            unresolved_count=len(unresolved),
            sent_count=len(sent),
            rejected_by_reason=dict(glossary.rejected_by_reason),
            artifact_path=artifact_path,
        )
    return glossary


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _log_built(log_event: Callable[..., object], *, glossary: ReadingGlossary, filename: str) -> None:
    sent_count = sum(1 for item in glossary.candidates if item.sent)
    log_event(
        logging.INFO,
        "audiobook_reading_glossary_built",
        "Словарь чтения сокращений книги построен.",
        filename=filename,
        status=glossary.status,
        candidate_count=len(glossary.candidates),
        sent_count=sent_count,
        accepted_count=len(glossary.entries),
        rerequested_count=len(glossary.rerequested),
        unresolved_count=len(glossary.unresolved),
        dropped_by_limit_count=len(glossary.candidates) - sent_count,
        rejected_by_reason={reason: int(glossary.rejected_by_reason.get(reason, 0)) for reason in READING_REJECTION_REASONS},
        batch_count=glossary.batch_count,
        call_count=glossary.call_count,
        retry_count=glossary.retry_count,
        prompt_tokens=glossary.prompt_tokens,
        completion_tokens=glossary.completion_tokens,
        cost_usd=glossary.cost_usd,
        artifact_path=glossary.artifact_path,
    )


# ---------------------------------------------------------------------------------------------
# The section of one block (research R6)
# ---------------------------------------------------------------------------------------------


def reading_section_for_block(glossary: ReadingGlossary | None, source_texts: Sequence[str]) -> str:
    """The section of ONE block: the entries whose candidate occurs in the block's source (exact unit,
    as at selection), in order of first appearance; ``""`` when there is none. No state: the entries
    of a previous block never reach the next one."""

    if glossary is None or not glossary.entries:
        return ""
    readings = {entry.abbreviation: entry.reading for entry in glossary.entries}
    ordered: list[str] = []
    for text in source_texts:
        for unit in reading_candidate_units(str(text or "")):
            if unit in readings and unit not in ordered:
                ordered.append(unit)
    if not ordered:
        return ""
    return render_glossary_prompt_section(
        [GlossaryTerm(source_term=unit, target_term=readings[unit]) for unit in ordered],
        header=READING_GLOSSARY_SECTION_HEADER,
        max_chars=READING_GLOSSARY_SECTION_MAX_CHARS,
    )


def narrated_source_paragraphs(payload: Any) -> tuple[tuple[str, str], ...]:
    """``(paragraph_id, source text)`` of the block's NARRATED paragraphs (no exclusion reason).

    The one reading of a block's source for both the step and the section (``_block_source_texts`` of
    the audiobook pass); a block without paragraph ids is its target text, unaddressed (``""``).
    """

    paragraph_ids = [str(paragraph_id) for paragraph_id in (getattr(payload, "paragraph_ids", None) or [])]
    if not paragraph_ids:
        text = str(getattr(payload, "target_text", "") or "").strip()
        return (("", text),) if text else ()
    reasons = getattr(payload, "narration_exclusion_reasons", None)
    if not isinstance(reasons, list) or len(reasons) != len(paragraph_ids):
        reasons = [None] * len(paragraph_ids)
    sources = _block_source_texts(payload, paragraph_ids)
    return tuple(
        (paragraph_id, source)
        for paragraph_id, source, reason in zip(paragraph_ids, sources, reasons)
        if reason is None and source
    )


def reading_paragraphs_from_jobs(jobs: Any) -> tuple[ReadingParagraph, ...]:
    """The narrated paragraphs of every job, numbered as the block loop numbers blocks (from 1). A job
    that does not parse is skipped here: the block loop reports it as it always has."""

    paragraphs: list[ReadingParagraph] = []
    for block_index, job in enumerate(jobs or (), start=1):
        try:
            payload = parse_processing_job(job=job, payload_factory=BlockExecutionPayload)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        paragraphs.extend(
            ReadingParagraph(paragraph_id=paragraph_id, block_index=block_index, text=text)
            for paragraph_id, text in narrated_source_paragraphs(payload)
        )
    return tuple(paragraphs)


# ---------------------------------------------------------------------------------------------
# The phase (research R7)
# ---------------------------------------------------------------------------------------------


def run_reading_glossary_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    emit_failed_result_fn: Callable[..., PipelineResult],
    request_text_completion_fn: Callable[..., str] | None = None,
    sleep_fn: Callable[[float], object] | None = None,
    write_artifact_fn: Callable[..., str] | None = None,
) -> PipelineResult | None:
    """The step of an ``audiobook`` run; ``None`` -- go on to the blocks (the context is not changed).

    An unavailable model returns the failed outcome through the same calls as
    ``handle_block_generation_failure`` -- ``present_error``, ``emit_state(last_error=…,
    latest_docx_bytes=None)``, ``emit_failed_result_fn`` -- without ``persist_terminal_job_result``: the
    step has no block job of its own.
    """

    if not is_audiobook_operation(getattr(context, "processing_operation", "")):
        return None
    job_count = int(getattr(initialization, "job_count", 0) or 0)
    filename = str(getattr(context, "uploaded_filename", "") or "")
    paragraphs = reading_paragraphs_from_jobs(getattr(context, "jobs", ()))
    client = getattr(initialization, "text_client", None) or getattr(initialization, "client", None)
    model_id = str(getattr(initialization, "text_model_id", "") or getattr(context, "model", "") or "")
    emitters.emit_status(
        context.runtime,
        stage="Словарь чтения",
        detail="Закрепляю чтение сокращений книги.",
        current_block=0,
        block_count=job_count,
        target_chars=0,
        context_chars=0,
        progress=0.0,
        is_running=True,
    )
    optional: dict[str, Any] = {}
    if request_text_completion_fn is not None:
        optional["request_text_completion_fn"] = request_text_completion_fn
    if sleep_fn is not None:
        optional["sleep_fn"] = sleep_fn
    if write_artifact_fn is not None:
        optional["write_artifact_fn"] = write_artifact_fn
    try:
        glossary = run_reading_glossary(
            paragraphs=paragraphs,
            client=client,
            model_id=model_id,
            max_retries=int(getattr(context, "max_retries", 1) or 1),
            should_stop=lambda: bool(dependencies.should_stop_processing(context.runtime)),
            log_event=dependencies.log_event,
            filename=filename,
            artifact_context=context,
            **optional,
        )
    except ReadingGlossaryUnavailable as exc:
        cause = exc.__cause__ if isinstance(exc.__cause__, Exception) else exc
        error_message = dependencies.present_error(
            "audiobook_reading_glossary_failed",
            cause,
            _ERROR_TITLE,
            filename=filename,
            reason=exc.reason,
            batch_index=exc.batch_index,
            attempts=exc.attempts,
            error_class=exc.error_class,
            candidate_count=exc.candidate_count,
            sent_count=exc.sent_count,
            artifact_path=exc.artifact_path,
            model=model_id,
        )
        formatted_error = f"{_ERROR_TITLE}: {error_message}"
        emitters.emit_state(context.runtime, last_error=formatted_error, latest_docx_bytes=None)
        return emit_failed_result_fn(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage=_ERROR_STAGE,
            detail=formatted_error,
            progress=0.0,
            block_index=0,
            block_count=job_count,
            target_chars=0,
            context_chars=0,
            log_details=str(error_message),
        )
    state.audiobook_reading_glossary = glossary
    return None
