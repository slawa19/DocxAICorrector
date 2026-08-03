"""Per-run accounting of what a processing run actually cost.

Why this module exists
----------------------
Before it, nothing in ``src/`` read ``usage`` off a provider response: a run that spent
real money reported neither tokens nor dollars, so the price of a book could only be
recovered by patching the SDK from outside the product (run 2026-08-03: $0.43 /
801 522 tokens / 219 calls, measured that way and nowhere else).

Honesty contract
----------------
This module NEVER estimates. Token counts and cost are recorded only when the provider
reported them on the response:

* a call whose response carried no usable ``usage`` increments
  ``model_calls_without_usage`` and contributes zero tokens — the snapshot therefore
  distinguishes "0 tokens because nothing was spent" from "unknown because the provider
  stayed silent" via ``token_accounting_complete``;
* cost is taken only from the provider's own ``usage.cost`` (OpenRouter reports it in
  USD per call). Providers that do not report cost leave ``cost_usd_reported_by_provider``
  covering only the calls that did report, and ``cost_accounting_complete`` False. No
  price list is applied, ever.

The only arithmetic performed on provider numbers is ``total = prompt + completion`` when
a provider reports the two components but not the total, and summation across calls.

Scope
-----
The ledger is a process-global singleton reset at the start of each processing run
(``pipeline/_pipeline.run_document_processing``). It is process-global rather than
injected because the recording points are leaf functions inside the provider-call
helpers, which have no dependency-injection channel; threading a ledger through every
one of them would be a far larger and riskier change than the observation it buys.
Preparation-stage model calls (structure recognition, paragraph-boundary AI review) run
in a separate worker BEFORE that reset and are therefore outside a processing run's
snapshot; ``accounting_scope`` names that boundary instead of leaving it implied.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass


ACCOUNTING_SCOPE = "processing_run"

STAGE_TEXT_GENERATION = "text_generation"
STAGE_BOUNDARY_REVIEW = "boundary_review"
STAGE_IMAGE_ANALYSIS = "image_analysis"
STAGE_IMAGE_VALIDATION = "image_validation"
STAGE_IMAGE_RECONSTRUCTION = "image_reconstruction"
STAGE_IMAGE_GENERATION = "image_generation"
STAGE_UNATTRIBUTED = "unattributed"

_PROMPT_TOKEN_FIELDS = ("prompt_tokens", "input_tokens")
_COMPLETION_TOKEN_FIELDS = ("completion_tokens", "output_tokens")
_TOTAL_TOKEN_FIELDS = ("total_tokens",)


@dataclass(frozen=True)
class ModelCallUsage:
    """What ONE provider response reported about itself.

    ``usage_reported`` / ``cost_reported`` are carried explicitly so a genuine reported
    zero (a free model really does cost $0.00) stays distinguishable from "the provider
    said nothing", which is the distinction the whole module exists to preserve.
    """

    usage_reported: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_reported: bool = False
    cost_usd: float = 0.0


UNREPORTED_MODEL_CALL_USAGE = ModelCallUsage()


def _read_field(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _coerce_token_count(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0.0:
        return int(value)
    return None


def _coerce_cost_usd(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        cost = float(value)
        return cost if cost >= 0.0 else None
    return None


def _first_reported_token_count(usage: object, field_names: tuple[str, ...]) -> int | None:
    for field_name in field_names:
        token_count = _coerce_token_count(_read_field(usage, field_name))
        if token_count is not None:
            return token_count
    return None


def extract_model_call_usage(response: object) -> ModelCallUsage:
    """Read ``usage`` off a provider response without inventing anything.

    Covers the three shapes the product actually talks to: OpenAI Responses
    (``input_tokens``/``output_tokens``), Chat Completions and OpenRouter
    (``prompt_tokens``/``completion_tokens`` plus ``cost`` in USD), and Anthropic
    Messages (``input_tokens``/``output_tokens``, no cost). An unrecognised shape is
    reported as "no usage", never as zero spend.
    """

    usage = _read_field(response, "usage")
    if usage is None:
        return UNREPORTED_MODEL_CALL_USAGE

    cost_usd = _coerce_cost_usd(_read_field(usage, "cost"))
    prompt_tokens = _first_reported_token_count(usage, _PROMPT_TOKEN_FIELDS)
    completion_tokens = _first_reported_token_count(usage, _COMPLETION_TOKEN_FIELDS)
    total_tokens = _first_reported_token_count(usage, _TOTAL_TOKEN_FIELDS)

    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        # A usage container with no readable token counts is NOT an accounted call, even
        # when it carried a cost. Both facts are recorded as they are.
        return ModelCallUsage(
            usage_reported=False,
            cost_reported=cost_usd is not None,
            cost_usd=cost_usd or 0.0,
        )

    resolved_prompt_tokens = prompt_tokens or 0
    resolved_completion_tokens = completion_tokens or 0
    resolved_total_tokens = (
        total_tokens if total_tokens is not None else resolved_prompt_tokens + resolved_completion_tokens
    )
    return ModelCallUsage(
        usage_reported=True,
        prompt_tokens=resolved_prompt_tokens,
        completion_tokens=resolved_completion_tokens,
        total_tokens=resolved_total_tokens,
        cost_reported=cost_usd is not None,
        cost_usd=cost_usd or 0.0,
    )


@dataclass
class _StageTotals:
    model_call_count: int = 0
    model_calls_with_usage: int = 0
    model_calls_without_usage: int = 0
    model_calls_without_cost: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd_reported_by_provider: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "model_call_count": self.model_call_count,
            "model_calls_with_usage": self.model_calls_with_usage,
            "model_calls_without_usage": self.model_calls_without_usage,
            "model_calls_without_cost": self.model_calls_without_cost,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd_reported_by_provider": round(self.cost_usd_reported_by_provider, 6),
        }


class RunModelAccountingLedger:
    """Thread-safe accumulator for one processing run.

    Thread-safe because image processing and block generation can run off the main
    thread; the lock keeps the counters consistent without changing any call ordering.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._totals = _StageTotals()
        self._stages: dict[str, _StageTotals] = {}
        self._retry_attempt_count = 0
        self._retried_block_count = 0
        self._retried_paragraph_count = 0
        self._retry_reason_counts: dict[str, int] = {}
        self._discarded_paragraph_count = 0
        self._discarded_block_count = 0
        self._discard_reason_counts: dict[str, int] = {}

    def reset(self) -> None:
        with self._lock:
            self._totals = _StageTotals()
            self._stages = {}
            self._retry_attempt_count = 0
            self._retried_block_count = 0
            self._retried_paragraph_count = 0
            self._retry_reason_counts = {}
            self._discarded_paragraph_count = 0
            self._discarded_block_count = 0
            self._discard_reason_counts = {}

    def record_model_call(self, *, stage: str, usage: ModelCallUsage) -> None:
        with self._lock:
            stage_totals = self._stages.setdefault(stage, _StageTotals())
            for totals in (self._totals, stage_totals):
                totals.model_call_count += 1
                if usage.usage_reported:
                    totals.model_calls_with_usage += 1
                    totals.prompt_tokens += usage.prompt_tokens
                    totals.completion_tokens += usage.completion_tokens
                    totals.total_tokens += usage.total_tokens
                else:
                    totals.model_calls_without_usage += 1
                if usage.cost_reported:
                    totals.cost_usd_reported_by_provider += usage.cost_usd
                else:
                    totals.model_calls_without_cost += 1

    def record_retry_attempt(self, *, reason: str, paragraph_count: int = 0, first_retry_for_block: bool = False) -> None:
        with self._lock:
            self._retry_attempt_count += 1
            self._retry_reason_counts[reason] = self._retry_reason_counts.get(reason, 0) + 1
            if first_retry_for_block:
                self._retried_block_count += 1
                self._retried_paragraph_count += max(0, paragraph_count)

    def record_model_output_discarded(self, *, reason: str, paragraph_count: int = 0, block_count: int = 0) -> None:
        with self._lock:
            self._discarded_paragraph_count += max(0, paragraph_count)
            self._discarded_block_count += max(0, block_count)
            self._discard_reason_counts[reason] = self._discard_reason_counts.get(reason, 0) + 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            totals = self._totals
            payload: dict[str, object] = {
                "accounting_scope": ACCOUNTING_SCOPE,
                "model_call_count": totals.model_call_count,
                "model_calls_with_usage": totals.model_calls_with_usage,
                "model_calls_without_usage": totals.model_calls_without_usage,
                "model_calls_without_cost": totals.model_calls_without_cost,
                "prompt_tokens": totals.prompt_tokens,
                "completion_tokens": totals.completion_tokens,
                "total_tokens": totals.total_tokens,
                # Sum of the per-call cost the PROVIDER reported. Covers only
                # ``model_call_count - model_calls_without_cost`` calls; read it together
                # with ``cost_accounting_complete`` before calling it the run's price.
                "cost_usd_reported_by_provider": round(totals.cost_usd_reported_by_provider, 6),
                "token_accounting_complete": totals.model_calls_without_usage == 0,
                "cost_accounting_complete": totals.model_calls_without_cost == 0,
                "retry_attempt_count": self._retry_attempt_count,
                "retried_block_count": self._retried_block_count,
                "retried_paragraph_count": self._retried_paragraph_count,
                "retry_reason_counts": dict(sorted(self._retry_reason_counts.items())),
                "model_output_discarded_paragraph_count": self._discarded_paragraph_count,
                "model_output_discarded_block_count": self._discarded_block_count,
                "model_output_discarded_reason_counts": dict(sorted(self._discard_reason_counts.items())),
                "stages": {stage: self._stages[stage].to_dict() for stage in sorted(self._stages)},
            }
            return payload


_LEDGER = RunModelAccountingLedger()


def get_run_model_accounting_ledger() -> RunModelAccountingLedger:
    return _LEDGER


def reset_run_model_accounting() -> None:
    _LEDGER.reset()


def record_model_call_usage(*, stage: str, response: object) -> ModelCallUsage:
    """Record one provider response against the active run. Never raises.

    Accounting must not be able to break a run it only observes, so an exotic response
    object that blows up during field access is recorded as an unaccounted call rather
    than propagating.
    """

    try:
        usage = extract_model_call_usage(response)
    except Exception:
        usage = UNREPORTED_MODEL_CALL_USAGE
    _LEDGER.record_model_call(stage=stage, usage=usage)
    return usage


def record_retry_attempt(*, reason: str, paragraph_count: int = 0, first_retry_for_block: bool = False) -> None:
    _LEDGER.record_retry_attempt(
        reason=reason,
        paragraph_count=paragraph_count,
        first_retry_for_block=first_retry_for_block,
    )


def record_model_output_discarded(*, reason: str, paragraph_count: int = 0, block_count: int = 0) -> None:
    _LEDGER.record_model_output_discarded(
        reason=reason,
        paragraph_count=paragraph_count,
        block_count=block_count,
    )


def snapshot_run_model_accounting() -> dict[str, object]:
    return _LEDGER.snapshot()
