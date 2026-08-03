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
Accounting is bound to the IDENTITY of the work being measured, not to a global reset.
Each processing run opens ``run_model_accounting_scope(run_id=..., source_token=...)``,
which creates a ledger of its own and binds it to the calling context; the snapshot taken
at the end of that scope therefore reports what THAT run spent.

This matters because two runs are admitted concurrently by default
(``processing/processing_runtime._DEFAULT_PROCESSING_ADMISSION_LIMIT`` is 2). Under the
previous process-global-singleton-plus-reset design, run B starting mid-flight wiped run
A's totals and both runs then accumulated into the same counters — internally consistent
numbers describing nobody's run. Isolation here comes from each scope owning a distinct
ledger OBJECT, so it holds even when a caller passes a blank ``run_id``; the identity
fields are recorded so a snapshot says whose spend it is, following the ownership pattern
spec 048 established for formatting diagnostics.

The binding is a ``ContextVar`` rather than an injected parameter because the recording
points are leaf functions inside the provider-call helpers, which have no
dependency-injection channel; threading a ledger through every one of them would be a far
larger and riskier change than the observation it buys. A processing run executes on one
worker thread (``processing_runtime`` starts it, and nothing under it forks further), so
the context set at the top of the run is the context every recording point sees.

Preparation
-----------
Preparation-stage model calls (paragraph-boundary AI review) run in a SEPARATE worker,
before any run exists, and one preparation can serve several later runs of the same
source. They are therefore recorded against the source, not against a run:
``preparation_model_accounting_scope(source_token=...)`` keeps a per-source ledger, and a
run's snapshot carries it under ``preparation_accounting`` with
``included_in_run_totals: False``. So preparation spend is VISIBLE in the same payload
that reports the run, and it is never silently summed into a run it did not belong to —
nor charged to whichever unrelated run happened to be in flight, which is what the global
ledger did before.

Model calls recorded with no scope open at all land in a process-level unscoped ledger and
are counted in ``unscoped_model_call_count`` on every run snapshot, so "spend that no
scope claimed" is a number one can read rather than a silence.
"""

from __future__ import annotations

import contextvars
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass


ACCOUNTING_SCOPE = "processing_run"
PREPARATION_ACCOUNTING_SCOPE = "source_preparation"
UNSCOPED_ACCOUNTING_SCOPE = "unscoped"

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
    """Thread-safe accumulator for ONE scope of work — a run, or one source preparation.

    Thread-safe because image processing and block generation can run off the main
    thread; the lock keeps the counters consistent without changing any call ordering.

    ``run_id`` / ``source_token`` are the scope's identity. They are carried into the
    snapshot so the payload states whose spend it reports; isolation itself comes from
    this object being distinct per scope, so a blank identity cannot leak one scope's
    calls into another's totals.
    """

    def __init__(self, *, scope: str = ACCOUNTING_SCOPE, run_id: str = "", source_token: str = "") -> None:
        self.scope = scope
        self.run_id = str(run_id or "")
        self.source_token = str(source_token or "")
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

    def model_call_count(self) -> int:
        with self._lock:
            return self._totals.model_call_count

    def totals_snapshot(self) -> dict[str, object]:
        """Just this ledger's stage totals — used to embed one scope inside another."""
        with self._lock:
            return self._totals.to_dict()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            totals = self._totals
            payload: dict[str, object] = {
                "accounting_scope": self.scope,
                "run_id": self.run_id,
                "source_token": self.source_token,
                # Isolation does not depend on this being True (each scope owns its own
                # ledger); it says whether the snapshot can NAME the run it describes.
                "run_identity_complete": bool(self.run_id and self.source_token),
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


# Calls recorded while no scope is open. Not a run's spend and never reported as one —
# only counted, so "nobody claimed this call" is readable in every run snapshot.
_UNSCOPED_LEDGER = RunModelAccountingLedger(scope=UNSCOPED_ACCOUNTING_SCOPE)

_ACTIVE_LEDGER: contextvars.ContextVar[RunModelAccountingLedger | None] = contextvars.ContextVar(
    "docxaicorrector_active_model_accounting_ledger",
    default=None,
)

# Preparation ledgers, keyed by source token, so a run can find the preparation that fed
# it. Bounded: a long-lived process must not accumulate one ledger per upload forever.
_MAX_RETAINED_PREPARATION_LEDGERS = 32
_PREPARATION_LEDGERS: dict[str, RunModelAccountingLedger] = {}
_PREPARATION_LEDGERS_LOCK = threading.Lock()


def get_run_model_accounting_ledger() -> RunModelAccountingLedger:
    """The ledger the current context records into."""
    return _ACTIVE_LEDGER.get() or _UNSCOPED_LEDGER


@contextmanager
def run_model_accounting_scope(
    *,
    run_id: str | None = None,
    source_token: str | None = None,
) -> Iterator[RunModelAccountingLedger]:
    """Bind a FRESH ledger to this run for the duration of the block.

    The ledger is created here rather than fetched from a registry, so a second run
    starting while this one is in flight cannot reset, read or add to it.
    """

    ledger = RunModelAccountingLedger(
        scope=ACCOUNTING_SCOPE,
        run_id=str(run_id or ""),
        source_token=str(source_token or ""),
    )
    token = _ACTIVE_LEDGER.set(ledger)
    try:
        yield ledger
    finally:
        _ACTIVE_LEDGER.reset(token)


@contextmanager
def preparation_model_accounting_scope(
    *,
    source_token: str | None = None,
) -> Iterator[RunModelAccountingLedger]:
    """Bind a per-SOURCE ledger for the preparation worker.

    Preparation happens before any run exists and can be reused by several runs of the
    same source, so its spend belongs to the source. Re-preparing a source replaces that
    source's preparation totals: the run that follows consumes the preparation that
    actually ran for it, and stale attempts are not added on top.
    """

    normalized_token = str(source_token or "")
    ledger = RunModelAccountingLedger(
        scope=PREPARATION_ACCOUNTING_SCOPE,
        source_token=normalized_token,
    )
    if normalized_token:
        with _PREPARATION_LEDGERS_LOCK:
            # Re-preparing a source makes it the most recent again, so it is not the one
            # evicted while the run that needs it is still to come.
            _PREPARATION_LEDGERS.pop(normalized_token, None)
            _PREPARATION_LEDGERS[normalized_token] = ledger
            while len(_PREPARATION_LEDGERS) > _MAX_RETAINED_PREPARATION_LEDGERS:
                _PREPARATION_LEDGERS.pop(next(iter(_PREPARATION_LEDGERS)))
    token = _ACTIVE_LEDGER.set(ledger)
    try:
        yield ledger
    finally:
        _ACTIVE_LEDGER.reset(token)


def get_preparation_model_accounting_ledger(source_token: str | None) -> RunModelAccountingLedger | None:
    normalized_token = str(source_token or "")
    if not normalized_token:
        return None
    with _PREPARATION_LEDGERS_LOCK:
        return _PREPARATION_LEDGERS.get(normalized_token)


def reset_run_model_accounting() -> None:
    """Clear the ledger the current context records into.

    Retained for callers that record outside any scope (offline tools, tests). It resets
    only the ACTIVE ledger, so it can no longer erase a concurrent run's totals.
    """

    get_run_model_accounting_ledger().reset()


def record_model_call_usage(*, stage: str, response: object) -> ModelCallUsage:
    """Record one provider response against the active scope. Never raises.

    Accounting must not be able to break a run it only observes, so an exotic response
    object that blows up during field access is recorded as an unaccounted call rather
    than propagating.
    """

    try:
        usage = extract_model_call_usage(response)
    except Exception:
        usage = UNREPORTED_MODEL_CALL_USAGE
    get_run_model_accounting_ledger().record_model_call(stage=stage, usage=usage)
    return usage


def record_retry_attempt(*, reason: str, paragraph_count: int = 0, first_retry_for_block: bool = False) -> None:
    get_run_model_accounting_ledger().record_retry_attempt(
        reason=reason,
        paragraph_count=paragraph_count,
        first_retry_for_block=first_retry_for_block,
    )


def record_model_output_discarded(*, reason: str, paragraph_count: int = 0, block_count: int = 0) -> None:
    get_run_model_accounting_ledger().record_model_output_discarded(
        reason=reason,
        paragraph_count=paragraph_count,
        block_count=block_count,
    )


def snapshot_run_model_accounting() -> dict[str, object]:
    """What the CURRENT scope spent, plus the preparation that fed it.

    ``preparation_accounting`` is reported alongside the run totals, never inside them:
    one preparation can serve several runs of the same source, so adding it to a run
    would price the same work twice across those runs.
    """

    ledger = get_run_model_accounting_ledger()
    payload = ledger.snapshot()
    payload["unscoped_model_call_count"] = _UNSCOPED_LEDGER.model_call_count()
    # A preparation snapshot already IS the preparation; only a run reports one beside it.
    preparation_ledger = (
        get_preparation_model_accounting_ledger(ledger.source_token)
        if ledger.scope != PREPARATION_ACCOUNTING_SCOPE
        else None
    )
    if preparation_ledger is None:
        payload["preparation_accounting"] = None
    else:
        payload["preparation_accounting"] = {
            "accounting_scope": PREPARATION_ACCOUNTING_SCOPE,
            "source_token": preparation_ledger.source_token,
            "included_in_run_totals": False,
            **preparation_ledger.totals_snapshot(),
        }
    return payload
