"""Spec 070 FR-003…FR-007 (research R2, R5, R7, R8, R9): one audiobook block, paragraph by paragraph.

The audiobook is a technical pass over finished text. For every paragraph of a block that is
narrated (the document layer gave it no exclusion reason, FR-003) this module decides the text
the listener hears:

1. the base text by the paragraph's disposition (R7) -- the model's answer when it gave one;
   the paragraph's OWN source text when the answer was empty (``empty_answer``), when the
   generator restored the source (``source_restored``), or when the whole block went down the
   controlled fallback (``source_fallback``). The source is in the language of the book now
   (``audiobook`` is not a language-changing operation), so it is narrated, never withheld;
2. the deterministic cleanup of what is unambiguous (FR-005, ``text.narration_cleanup``);
3. the residue detector (FR-006, ``text.narration_residue``) -- and for the paragraphs that
   still carry a repairable class, AT MOST ONE repair call for the whole block
   (``pipeline.audiobook_repair``); after it, cleanup and detector once more, never a second call;
4. the per-paragraph coverage signal against the paragraph's own source (FR-007,
   ``text.narration_coverage``).

Each narrated paragraph leaves one :class:`NarrationParagraphRecord`; the ``.tts.txt`` is
assembled from those records by id and preparation role (``narration_postprocess``), never by
re-reading Markdown the model returned. Nothing here blocks delivery (Anti-regression 2): a
paragraph that could not be made clean is delivered with ``needs_review`` and its address.

Pure over its inputs except for the repair call, which is injected; no Streamlit, no I/O.
Every rule is by role, status or FORM -- no word list, no per-book literal (Constitution VII).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from docxaicorrector.core.models import PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
from docxaicorrector.generation._generation import (
    PARAGRAPH_STATUS_ACCEPTED,
    PARAGRAPH_STATUS_OMITTED,
    PARAGRAPH_STATUS_RETRY_REQUIRED,
    PARAGRAPH_STATUS_SOURCE_RESTORED,
    MarkerPreservedBlockText,
    ParagraphDisposition,
    marker_paragraph_dispositions,
)
from docxaicorrector.pipeline.audiobook_plan import _source_texts_by_marker
from docxaicorrector.pipeline.audiobook_repair import RepairItem, RepairOutcome
from docxaicorrector.text.narration_cleanup import clean_narration_paragraph
from docxaicorrector.text.narration_coverage import (
    COVERAGE_REVIEW_THRESHOLD,
    CoverageResult,
    paragraph_coverage,
)
from docxaicorrector.text.narration_residue import (
    REPAIRABLE_RESIDUE_CLASSES,
    RESIDUE_CLASSES,
    ResidueFinding,
    detect_narration_residue,
)

__all__ = [
    "AUDIOBOOK_OPERATION",
    "NEEDS_REVIEW_REASONS",
    "AudiobookParagraphInput",
    "FinalizedAudiobookBlock",
    "NarrationParagraphRecord",
    "audiobook_block_narrates",
    "audiobook_block_paragraph_inputs",
    "audiobook_narration_summary",
    "finalize_audiobook_block",
    "fragment_samples",
    "is_audiobook_operation",
    "needs_review_event_records",
    "rebuild_block_with_narration_texts",
    "record_repair_outcome",
    "register_audiobook_block",
]

AUDIOBOOK_OPERATION = "audiobook"

NEEDS_REVIEW_EMPTY_ANSWER = "empty_answer"
NEEDS_REVIEW_SOURCE_RESTORED = "source_restored"
NEEDS_REVIEW_SOURCE_FALLBACK = "source_fallback"
NEEDS_REVIEW_RESIDUE = "residue"
NEEDS_REVIEW_REPAIR_FAILED = "repair_failed"
NEEDS_REVIEW_LOW_COVERAGE = "low_coverage"
# The order is the order a reader meets the causes in (how the text was obtained, then what is
# still wrong with it); it is also the order the reasons are published in.
NEEDS_REVIEW_REASONS: tuple[str, ...] = (
    NEEDS_REVIEW_EMPTY_ANSWER,
    NEEDS_REVIEW_SOURCE_RESTORED,
    NEEDS_REVIEW_SOURCE_FALLBACK,
    NEEDS_REVIEW_RESIDUE,
    NEEDS_REVIEW_REPAIR_FAILED,
    NEEDS_REVIEW_LOW_COVERAGE,
)
_BODY_ROLE = "body"
# Samples in log events and exclusion records: never a full text (LOGGING §1.5, contracts/events.md).
SAMPLE_MAX_CHARS = 120
FRAGMENT_SAMPLE_LIMIT = 3

RepairCall = Callable[[Sequence[RepairItem], str, str], RepairOutcome]


def is_audiobook_operation(processing_operation: Any) -> bool:
    return str(processing_operation or "").strip().casefold() == AUDIOBOOK_OPERATION


def _sample(text: str) -> str:
    collapsed = " ".join(str(text).split())
    return collapsed[:SAMPLE_MAX_CHARS]


@dataclass(frozen=True)
class NarrationParagraphRecord:
    """One narrated paragraph of the run: what the listener hears and what is still worth a look."""

    paragraph_id: str
    block_index: int
    role: str
    text: str
    needs_review_reasons: tuple[str, ...]
    residue_before: tuple[ResidueFinding, ...]
    residue_after: tuple[ResidueFinding, ...]
    coverage: CoverageResult


@dataclass(frozen=True)
class AudiobookParagraphInput:
    """One paragraph of a block as the finalizer sees it.

    ``exclusion_reason`` set means "not narrated" (FR-003): the paragraph is passed through to
    the DOCX untouched and never reaches the finalizer's text decisions. ``source_text`` is ``""``
    when the block's source could not be addressed paragraph by paragraph; the coverage signal
    is then not measured and an empty answer falls back to nothing (the paragraph is reported
    missing rather than given an invented text).
    """

    paragraph_id: str
    role: str
    source_text: str
    delivered_text: str
    status: str
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class FinalizedAudiobookBlock:
    records: tuple[NarrationParagraphRecord, ...]
    # The final narration text per narrated paragraph id; the block's DOCX/Markdown carries it (R4).
    texts_by_id: Mapping[str, str]
    repair_items: tuple[RepairItem, ...]
    repair_outcome: RepairOutcome | None


def _repairable_classes(findings: Sequence[ResidueFinding]) -> tuple[str, ...]:
    return tuple(finding.residue_class for finding in findings if finding.residue_class in REPAIRABLE_RESIDUE_CLASSES)


def _base_text(item: AudiobookParagraphInput, *, forced_reason: str | None) -> tuple[str, list[str]]:
    """The text a paragraph starts from, and the R7 reason when it is not the model's answer."""

    if forced_reason is not None:
        return item.source_text or item.delivered_text, [forced_reason]
    if item.status == PARAGRAPH_STATUS_SOURCE_RESTORED:
        return item.delivered_text or item.source_text, [NEEDS_REVIEW_SOURCE_RESTORED]
    if item.status in {PARAGRAPH_STATUS_OMITTED, PARAGRAPH_STATUS_RETRY_REQUIRED}:
        return item.source_text or item.delivered_text, [NEEDS_REVIEW_EMPTY_ANSWER]
    return item.delivered_text, []


def finalize_audiobook_block(
    *,
    block_index: int,
    paragraphs: Sequence[AudiobookParagraphInput],
    repair: RepairCall | None,
    forced_reason: str | None = None,
) -> FinalizedAudiobookBlock:
    """Finalize the narrated paragraphs of one block (see the module docstring for the order).

    ``repair`` is called AT MOST ONCE, and only when at least one addressable paragraph carries
    a repairable residue class; ``None`` means no repair is possible (no ids to put under
    markers) and the residue is reported instead. ``forced_reason`` is the R7 reason for a block
    the controlled fallback delivered as its own source (``source_fallback``).
    """

    narrated = [item for item in paragraphs if item.exclusion_reason is None]
    texts: dict[int, str] = {}
    reasons: dict[int, list[str]] = {}
    residue_before: dict[int, tuple[ResidueFinding, ...]] = {}
    for position, item in enumerate(narrated):
        base, base_reasons = _base_text(item, forced_reason=forced_reason)
        cleaned = clean_narration_paragraph(base).text
        if not cleaned and item.source_text and not base_reasons:
            # A model answer that cleans down to nothing (an emoji, a stray tag) is an empty
            # answer by another route (Edge Cases: "законного пустого ответа нет").
            cleaned = clean_narration_paragraph(item.source_text).text
            base_reasons = [NEEDS_REVIEW_EMPTY_ANSWER]
        texts[position] = cleaned
        reasons[position] = list(base_reasons)
        residue_before[position] = detect_narration_residue(cleaned)

    repair_positions = [
        position
        for position, item in enumerate(narrated)
        if item.paragraph_id and texts[position] and _repairable_classes(residue_before[position])
    ]
    repair_items = tuple(
        RepairItem(
            paragraph_id=narrated[position].paragraph_id,
            text=texts[position],
            residue_classes=_repairable_classes(residue_before[position]),
        )
        for position in repair_positions
    )
    repair_outcome: RepairOutcome | None = None
    if repair_items and repair is not None:
        first, last = repair_positions[0], repair_positions[-1]
        context_before = next((texts[p] for p in range(first - 1, -1, -1) if texts[p]), "")
        context_after = next((texts[p] for p in range(last + 1, len(narrated)) if texts[p]), "")
        repair_outcome = repair(repair_items, context_before, context_after)
        for position in repair_positions:
            if repair_outcome.status == "accepted":
                repaired = clean_narration_paragraph(
                    str(repair_outcome.texts.get(narrated[position].paragraph_id, texts[position]))
                ).text
                if repaired:
                    texts[position] = repaired
                    continue
            reasons[position].append(NEEDS_REVIEW_REPAIR_FAILED)
    elif repair_items:
        for position in repair_positions:
            reasons[position].append(NEEDS_REVIEW_REPAIR_FAILED)

    records: list[NarrationParagraphRecord] = []
    texts_by_id: dict[str, str] = {}
    for position, item in enumerate(narrated):
        text = texts[position]
        if not text:
            # Nothing narratable is left (the source itself was only a pipeline token): the id
            # stays in the denominator and is reported missing, no text is invented.
            continue
        residue_after = detect_narration_residue(text)
        paragraph_reasons = reasons[position]
        if residue_after:
            paragraph_reasons.append(NEEDS_REVIEW_RESIDUE)
        coverage = paragraph_coverage(item.source_text, text) if item.source_text else CoverageResult(0, 0, None)
        if coverage.ratio is not None and coverage.ratio < COVERAGE_REVIEW_THRESHOLD:
            paragraph_reasons.append(NEEDS_REVIEW_LOW_COVERAGE)
        ordered_reasons = tuple(reason for reason in NEEDS_REVIEW_REASONS if reason in paragraph_reasons)
        records.append(
            NarrationParagraphRecord(
                paragraph_id=item.paragraph_id,
                block_index=block_index,
                role=item.role or _BODY_ROLE,
                text=text,
                needs_review_reasons=ordered_reasons,
                residue_before=residue_before[position],
                residue_after=residue_after,
                coverage=coverage,
            )
        )
        if item.paragraph_id:
            texts_by_id[item.paragraph_id] = text
    return FinalizedAudiobookBlock(
        records=tuple(records),
        texts_by_id=texts_by_id,
        repair_items=repair_items,
        repair_outcome=repair_outcome,
    )


# ---------------------------------------------------------------------------------------------
# From a payload and a processed block to the finalizer's inputs
# ---------------------------------------------------------------------------------------------


def _payload_list(payload: Any, name: str, length: int) -> list[Any] | None:
    value = getattr(payload, name, None)
    return list(value) if isinstance(value, list) and len(value) == length else None


def _block_source_texts(payload: Any, paragraph_ids: list[str]) -> list[str]:
    """The block's source per paragraph, or ``""`` each when it cannot be addressed exactly."""

    try:
        return _source_texts_by_marker(
            paragraph_ids=paragraph_ids,
            marked_text=str(getattr(payload, "target_text_with_markers", "") or ""),
        )
    except ValueError:
        chunks = [chunk.strip() for chunk in str(getattr(payload, "target_text", "") or "").split("\n\n") if chunk.strip()]
        return chunks if len(chunks) == len(paragraph_ids) else [""] * len(paragraph_ids)


def _delivered_dispositions(processed_chunk: str, paragraph_ids: list[str]) -> list[ParagraphDisposition] | None:
    dispositions = marker_paragraph_dispositions(processed_chunk)
    if dispositions is not None:
        if [str(item.paragraph_id) for item in dispositions] == paragraph_ids:
            return list(dispositions)
        return None
    chunks = [chunk.strip() for chunk in str(processed_chunk).split("\n\n") if chunk.strip()]
    if len(chunks) != len(paragraph_ids):
        return None
    return [
        ParagraphDisposition(paragraph_id=paragraph_id, text=chunk, status=PARAGRAPH_STATUS_ACCEPTED)
        for paragraph_id, chunk in zip(paragraph_ids, chunks)
    ]


def audiobook_block_paragraph_inputs(
    *, payload: Any, processed_chunk: str, source_fallback: bool = False
) -> list[AudiobookParagraphInput]:
    """The finalizer's inputs for one delivered block.

    With paragraph ids (every block the document layer builds, R12) the inputs are by id, in
    order, with each paragraph's role, source text, delivered text, status and exclusion reason.
    A block whose delivered text cannot be mapped onto its ids -- or that has no ids at all --
    yields unaddressed inputs (``paragraph_id == ""``) split from the delivered text: they are
    narrated and checked, but cannot be repaired under markers and are not in the denominator.
    """

    paragraph_ids = [str(paragraph_id) for paragraph_id in (getattr(payload, "paragraph_ids", None) or [])]
    if paragraph_ids:
        count = len(paragraph_ids)
        roles = _payload_list(payload, "structural_roles", count) or [_BODY_ROLE] * count
        reasons = _payload_list(payload, "narration_exclusion_reasons", count) or [None] * count
        sources = _block_source_texts(payload, paragraph_ids)
        if source_fallback:
            delivered: list[ParagraphDisposition] | None = [
                ParagraphDisposition(paragraph_id=paragraph_id, text=source, status=PARAGRAPH_STATUS_SOURCE_RESTORED)
                for paragraph_id, source in zip(paragraph_ids, sources)
            ]
            if not all(sources):
                delivered = _delivered_dispositions(processed_chunk, paragraph_ids)
        else:
            delivered = _delivered_dispositions(processed_chunk, paragraph_ids)
        if delivered is not None:
            return [
                AudiobookParagraphInput(
                    paragraph_id=paragraph_id,
                    role=str(roles[position] or _BODY_ROLE).strip().casefold() or _BODY_ROLE,
                    source_text=sources[position],
                    delivered_text=delivered[position].text,
                    status=delivered[position].status,
                    exclusion_reason=(
                        reasons[position]
                        if reasons[position] is not None
                        else (
                            # The status the plan merge gives an excluded paragraph; a block
                            # without reasons never carries it, so this only keeps a kept-by-
                            # policy paragraph out of the narration whatever produced it.
                            "policy_kept_source"
                            if delivered[position].status == PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
                            else None
                        )
                    ),
                )
                for position, paragraph_id in enumerate(paragraph_ids)
            ]
    chunks = [chunk.strip() for chunk in str(processed_chunk).split("\n\n") if chunk.strip()]
    return [
        AudiobookParagraphInput(
            paragraph_id="",
            role=_BODY_ROLE,
            source_text="",
            delivered_text=chunk,
            status=PARAGRAPH_STATUS_ACCEPTED,
        )
        for chunk in chunks
    ]


def rebuild_block_with_narration_texts(
    *, payload: Any, processed_chunk: str, texts_by_id: Mapping[str, str], source_fallback: bool = False
) -> str:
    """The block whose narrated paragraphs carry their final narration text (R4).

    The DOCX and the Markdown of the audiobook carry what the listener hears, so the
    ``needs_review`` addresses point at text that exists there. Excluded paragraphs keep what
    they had (their source, ``policy_kept_source``). The per-paragraph record is kept: the block
    is rebuilt as a :class:`MarkerPreservedBlockText` from its dispositions, never by string
    operations on it. A block that cannot be addressed by id is returned unchanged.
    """

    paragraph_ids = [str(paragraph_id) for paragraph_id in (getattr(payload, "paragraph_ids", None) or [])]
    if not paragraph_ids or not texts_by_id:
        return processed_chunk
    if source_fallback:
        sources = _block_source_texts(payload, paragraph_ids)
        dispositions: list[ParagraphDisposition] | None = (
            [
                ParagraphDisposition(paragraph_id=paragraph_id, text=source, status=PARAGRAPH_STATUS_SOURCE_RESTORED)
                for paragraph_id, source in zip(paragraph_ids, sources)
            ]
            if all(sources)
            else _delivered_dispositions(processed_chunk, paragraph_ids)
        )
        reasons = _payload_list(payload, "narration_exclusion_reasons", len(paragraph_ids)) or [None] * len(paragraph_ids)
        if dispositions is not None:
            dispositions = [
                ParagraphDisposition(
                    paragraph_id=item.paragraph_id, text=item.text, status=PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
                )
                if reason is not None
                else item
                for item, reason in zip(dispositions, reasons)
            ]
    else:
        dispositions = _delivered_dispositions(processed_chunk, paragraph_ids)
    if dispositions is None:
        return processed_chunk
    sources = _block_source_texts(payload, paragraph_ids)
    rebuilt = [
        ParagraphDisposition(
            paragraph_id=item.paragraph_id,
            text=(
                _with_source_heading_prefix(texts_by_id[str(item.paragraph_id)], sources[position])
                if str(item.paragraph_id) in texts_by_id
                else item.text
            ),
            status=item.status,
        )
        for position, item in enumerate(dispositions)
    ]
    return MarkerPreservedBlockText("\n\n".join(item.text for item in rebuilt), rebuilt)


_MARKDOWN_HEADING_PREFIX = re.compile(r"^(#{1,6})[ \t]+\S")


def _with_source_heading_prefix(narration_text: str, source_text: str) -> str:
    """The DOCX/Markdown text of a narrated paragraph: its narration, under the SOURCE's heading.

    The narration itself carries no Markdown (the prompt forbids it, the cleanup strips what is
    left), so without this every heading of the source would reach the DOCX as a body
    paragraph -- the FR-009 run of 2026-11-10 failed ``key_headings_preserved`` on all three
    inputs for exactly that. The heading level is read off the paragraph's own source by form
    (a Markdown heading prefix), never off the answer; the ``.tts.txt`` is assembled from the
    narration records and never sees this prefix.
    """

    match = _MARKDOWN_HEADING_PREFIX.match(str(source_text or "").lstrip())
    text = str(narration_text or "")
    if match is None or not text.strip() or text.lstrip().startswith("#"):
        return text
    return f"{match.group(1)} {text.strip()}"


# ---------------------------------------------------------------------------------------------
# Run state: the denominator, the exclusions, the repair counters
# ---------------------------------------------------------------------------------------------


def audiobook_block_narrates(payload: Any) -> bool:
    """Does any paragraph of this block reach the narration?

    By the per-paragraph reasons when the document layer computed them (FR-003); a block of a
    producer without reasons falls back to its block-level ``narration_include``."""

    reasons = getattr(payload, "narration_exclusion_reasons", None)
    if isinstance(reasons, list) and reasons:
        return any(reason is None for reason in reasons)
    return bool(getattr(payload, "narration_include", True))


def residue_classes_by_paragraph_count(texts: Mapping[str, str]) -> dict[str, int]:
    """How many of these paragraphs still carry each residue class after the cleanup.

    The ``residue_after_by_class`` of ``audiobook_repair_completed``, in the same unit as its
    ``residue_before_by_class`` (paragraphs per class)."""

    counts: Counter[str] = Counter()
    for text in texts.values():
        for finding in detect_narration_residue(clean_narration_paragraph(str(text)).text):
            counts[finding.residue_class] += 1
    return dict(sorted(counts.items()))


def _state_list(state: Any, name: str) -> list[Any]:
    value = getattr(state, name, None)
    if not isinstance(value, list):
        value = []
        setattr(state, name, value)
    return value


def _state_dict(state: Any, name: str) -> dict[str, int]:
    value = getattr(state, name, None)
    if not isinstance(value, dict):
        value = {}
        setattr(state, name, value)
    return value


def register_audiobook_block(*, state: Any, payload: Any, block_index: int) -> tuple[str, ...]:
    """Record, BEFORE the model answers, which ids of this block are narrated and which are not.

    The narrated ids are the denominator of FR-007 (an empty answer cannot shrink it); every
    exclusion is kept with its reason and address (FR-003). Returns the narrated ids.
    """

    paragraph_ids = [str(paragraph_id) for paragraph_id in (getattr(payload, "paragraph_ids", None) or [])]
    if not paragraph_ids:
        return ()
    reasons = _payload_list(payload, "narration_exclusion_reasons", len(paragraph_ids)) or [None] * len(paragraph_ids)
    if not audiobook_block_narrates(payload) and all(reason is None for reason in reasons):
        # A block the document layer kept out without per-paragraph reasons (a producer older
        # than spec 070): nothing of it is narrated and there is no reason to report.
        return ()
    sources = _block_source_texts(payload, paragraph_ids) if any(reason is not None for reason in reasons) else []
    exclusions = _state_list(state, "narration_exclusions")
    narrated: list[str] = []
    for position, (paragraph_id, reason) in enumerate(zip(paragraph_ids, reasons)):
        if reason is None:
            narrated.append(paragraph_id)
            continue
        exclusions.append(
            {
                "paragraph_id": paragraph_id,
                "block_index": block_index,
                "reason": str(reason),
                "sample": _sample(sources[position]) if position < len(sources) else "",
            }
        )
    _state_list(state, "narration_expected_paragraph_ids").extend(narrated)
    return tuple(narrated)


REPAIR_COUNTER_KEYS: tuple[str, ...] = (
    "block_count",
    "call_count",
    "accepted_block_count",
    "failed_call_count",
    "skipped_stopped_count",
)


def record_repair_outcome(*, state: Any, outcome: RepairOutcome | None) -> None:
    """Fold one block's repair outcome into ``state.narration_repair_counters`` (data-model §5).

    ``failed_call_count`` counts calls that were MADE and failed without a usable answer (an
    SDK/network fault): the provider billed nothing and sent no usage, so this is how they are
    accounted (research R5). Rejected answers are counted by reason.
    """

    counters = _state_dict(state, "narration_repair_counters")
    for key in REPAIR_COUNTER_KEYS:
        counters.setdefault(key, 0)
    if outcome is None:
        return
    counters["block_count"] += 1
    if outcome.call_made:
        counters["call_count"] += 1
    if outcome.status == "accepted":
        counters["accepted_block_count"] += 1
    elif outcome.status == "failed" and outcome.call_made:
        counters["failed_call_count"] += 1
    elif outcome.status == "rejected" and outcome.reason:
        key = f"rejected_by_reason.{outcome.reason}"
        counters[key] = counters.get(key, 0) + 1
    if outcome.reason == "stopped":
        counters["skipped_stopped_count"] += 1


def _residue_by_class(records: Sequence[NarrationParagraphRecord], attribute: str) -> dict[str, dict[str, int]]:
    paragraphs: Counter[str] = Counter()
    occurrences: Counter[str] = Counter()
    for record in records:
        for finding in getattr(record, attribute):
            paragraphs[finding.residue_class] += 1
            occurrences[finding.residue_class] += finding.count
    return {
        residue_class: {"paragraphs": paragraphs[residue_class], "occurrences": occurrences[residue_class]}
        for residue_class in RESIDUE_CLASSES
        if paragraphs[residue_class]
    }


def audiobook_narration_summary(state: Any) -> dict[str, object]:
    """The run's narration totals (data-model §6), from the run state alone.

    Zero is a statement, never an absent field (Constitution V): every key is always present.
    """

    records = [record for record in (getattr(state, "narration_paragraphs", None) or ()) if isinstance(record, NarrationParagraphRecord)]
    expected = [str(paragraph_id) for paragraph_id in (getattr(state, "narration_expected_paragraph_ids", None) or ())]
    delivered_ids = {record.paragraph_id for record in records if record.paragraph_id}
    exclusions = [entry for entry in (getattr(state, "narration_exclusions", None) or ()) if isinstance(entry, Mapping)]
    excluded_by_reason: Counter[str] = Counter(str(entry.get("reason")) for entry in exclusions)
    excluded_ids_by_reason: dict[str, list[str]] = {}
    for entry in exclusions:
        excluded_ids_by_reason.setdefault(str(entry.get("reason")), []).append(str(entry.get("paragraph_id")))
    needs_review_by_reason: Counter[str] = Counter(
        reason for record in records for reason in record.needs_review_reasons
    )
    repair_counters = dict(getattr(state, "narration_repair_counters", None) or {})
    for key in REPAIR_COUNTER_KEYS:
        repair_counters.setdefault(key, 0)
    join_pairs = [
        [str(pair[0]), str(pair[1])] for pair in (getattr(state, "narration_joined_paragraph_id_pairs", None) or ())
    ]
    return {
        "expected_paragraph_count": len(expected),
        "delivered_paragraph_count": len(records),
        "missing_paragraph_ids": [paragraph_id for paragraph_id in expected if paragraph_id not in delivered_ids],
        "paragraph_boundary_check": getattr(state, "narration_paragraph_boundary_check", None) or "not_built",
        "deterministic_join_count": len(join_pairs),
        "deterministic_join_pairs": join_pairs,
        "excluded_count": len(exclusions),
        "excluded_by_reason": dict(sorted(excluded_by_reason.items())),
        "excluded_paragraph_ids_by_reason": dict(sorted(excluded_ids_by_reason.items())),
        "residue_before_by_class": _residue_by_class(records, "residue_before"),
        "residue_after_by_class": _residue_by_class(records, "residue_after"),
        "needs_review_paragraph_count": sum(1 for record in records if record.needs_review_reasons),
        "needs_review_by_reason": {
            reason: needs_review_by_reason[reason] for reason in NEEDS_REVIEW_REASONS if needs_review_by_reason[reason]
        },
        "repair_block_count": int(repair_counters.pop("block_count")),
        "repair_call_count": int(repair_counters.pop("call_count")),
        "repair_accepted_block_count": int(repair_counters.pop("accepted_block_count")),
        "repair_failed_call_count": int(repair_counters.pop("failed_call_count")),
        "repair_skipped_stopped_count": int(repair_counters.pop("skipped_stopped_count")),
        "repair_rejected_by_reason": {
            key.split(".", 1)[1]: int(value) for key, value in sorted(repair_counters.items()) if key.startswith("rejected_by_reason.")
        },
        "coverage_not_measured_count": sum(1 for record in records if record.coverage.ratio is None),
        "coverage_low_count": sum(
            1 for record in records if record.coverage.ratio is not None and record.coverage.ratio < COVERAGE_REVIEW_THRESHOLD
        ),
    }


def needs_review_event_records(state: Any) -> list[dict[str, object]]:
    """``audiobook_needs_review.records``: the address and a short sample, never the full text."""

    return [
        {
            "paragraph_id": record.paragraph_id,
            "block_index": record.block_index,
            "reasons": list(record.needs_review_reasons),
            "residue_classes": [finding.residue_class for finding in record.residue_after],
            "sample": _sample(record.text),
        }
        for record in (getattr(state, "narration_paragraphs", None) or ())
        if isinstance(record, NarrationParagraphRecord) and record.needs_review_reasons
    ]


def fragment_samples(state: Any) -> list[dict[str, object]]:
    """Up to three ``fragment`` exclusions with their samples, for reading each one (SC-001)."""

    samples: list[dict[str, object]] = []
    for entry in getattr(state, "narration_exclusions", None) or ():
        if isinstance(entry, Mapping) and entry.get("reason") == "fragment":
            samples.append({"paragraph_id": entry.get("paragraph_id"), "sample": entry.get("sample", "")})
            if len(samples) >= FRAGMENT_SAMPLE_LIMIT:
                break
    return samples
