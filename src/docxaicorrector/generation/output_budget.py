"""Spec 069 FR-006: how much output a model may be asked for, relative to today's formula.

A block call asks for ``max((len // 3) * 4, 512)`` tokens, clamped to the provider ceiling
(``generation._generation._estimate_max_output_tokens``). That formula was sized on the current
text model, and a model that spends more tokens on the same text — through its tokenizer, or
through reasoning that counts against ``max_output_tokens`` — is cut off under it. The fix is a
per-model MULTIPLIER of the whole formula, the 512 floor included, under the same ceiling.

These are generation LIMITS, not prices: a limit only caps, tokens are paid as generated, and
the cost estimate (FR-007) keeps its own coefficients. The rule for a value is the one the
glossary budget already follows (``text/glossary_pass.py``): the measured per-response p99 of
output/limit must sit at or below half the limit, i.e. ``m >= 2 * p99`` rounded up to a whole
number; an unmeasured model keeps 1.0 — today's budget — until a run measures it.

Pure module: no network, no Streamlit, no import from the generator, so the pipeline contracts
and the glossary builders can read it without an import cycle.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from types import MappingProxyType

DEFAULT_OUTPUT_BUDGET_MULTIPLIER = 1.0

# Canonical model id (no ``openrouter:``/``openai:``/``anthropic:`` selector prefix, lower case)
# -> multiplier of the block budget formula. Every value names where it comes from.
MODEL_OUTPUT_BUDGET_MULTIPLIERS: Mapping[str, float] = MappingProxyType(
    {
        # The current text model and the first pass of ``standard``. Multiplier 1 is the SC-006
        # contract (budgets of ``single``/``edit``/``audiobook`` byte-identical) and the fact:
        # 0 ``incomplete_response`` retries on 28 chapter calls and 229 + 292 full-book calls of
        # bake-off FR-017 (spec 063), mean output 22–31 % of the limit (research R2).
        "google/gemini-3.1-flash-lite-preview": 1.0,
        # First pass of ``quality``, always sent with ``reasoning.effort = low``: per-response
        # output/limit p99 0.289, max 0.290, 0 incomplete of 56 (bake-off harness
        # ``reasoning_calls.jsonl``, research R2). Without ``low`` it is NOT 1: 13 of 51 cut off.
        "google/gemini-3.7-flash": 1.0,
        # Same harness, ``effort = low``: p99 0.277, max 0.285, n = 28 (research R2). Not used
        # by a mode (rejected in bake-off: same quality, dearer); listed so it is not guessed.
        "google/gemini-3.8-flash": 1.0,
        # Second pass of ``standard`` (``literary_polish``), DEFAULT reasoning — the
        # configuration whose quality bake-off C measured. WP-0 of spec 069, 2026-11-09
        # (data outside the repo: D:\Temp\docxai-research\069-wp0\wp0.md): 45 responses on two chapters,
        # completed output/limit p99 0.90, max 0.92; 2 incomplete at the 512 floor (one spent
        # all 512 tokens on reasoning, the other needed 793 = 1.55x the floor); 53 % of
        # responses reason, reasoning = 43 % of output. m = 3 is the smallest whole number with
        # p99 at or under half the limit (0.30) and covers the floor class (512 -> 1 536).
        # With ``effort = low`` (p99 0.64, max 0.68) 2 would do — no mode sends it, so the
        # table is not keyed by effort.
        "anthropic/claude-haiku-5.5": 3.0,
    }
)

_SELECTOR_PROVIDERS = ("openai", "openrouter", "anthropic")

# The rule ``generation._generation._normalize_anthropic_model_id`` applies to the id it sends
# (a dotted version ``N.M`` is written ``N-M``): a copy, because that module imports this one;
# ``tests/test_output_budget.py`` holds the two equal. Applied to selector AND table keys, every
# spelling of one model reaches one row.
_DOTTED_VERSION_SEPARATOR_PATTERN = re.compile(r"(?<=\d)\.(?=\d)")


def validate_output_budget_multiplier(multiplier: float) -> float:
    """The multiplier as a float, or ``ValueError``: a finite real number above zero."""

    if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)):
        raise ValueError(f"output budget multiplier must be a number, got {multiplier!r}")
    value = float(multiplier)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"output budget multiplier must be finite and above zero, got {multiplier!r}")
    return value


def scale_output_budget(base_tokens: int, multiplier: float, *, ceiling: int) -> int:
    """``base_tokens`` times the multiplier, rounded up, under ``ceiling``.

    ``multiplier == 1`` returns ``min(base_tokens, ceiling)`` with no float arithmetic at all,
    so the budget of every call without a profile is the integer it always was.
    """

    value = validate_output_budget_multiplier(multiplier)
    limit = base_tokens if value == 1.0 else math.ceil(base_tokens * value)
    return min(limit, ceiling)


def _canonical_model_key(model: str) -> str:
    return _DOTTED_VERSION_SEPARATOR_PATTERN.sub("-", model)


def canonical_output_budget_model_id(model: str) -> str:
    """The table key of a model selector: provider prefix dropped, lower case, dotted versions dashed.

    ``openrouter:google/gemini-3.7-flash`` and ``google/gemini-3.7-flash`` are one model. A
    native Anthropic selector (``anthropic:claude-haiku-5.5``) names the model without the
    ``anthropic/`` vendor part OpenRouter puts in front, so it gets it back.
    """

    selector = str(model or "").strip().lower()
    provider, separator, model_id = selector.partition(":")
    if separator and provider.strip() in _SELECTOR_PROVIDERS:
        selector = model_id.strip()
        if provider.strip() == "anthropic" and "/" not in selector:
            selector = f"anthropic/{selector}"
    return _DOTTED_VERSION_SEPARATOR_PATTERN.sub("-", selector)


_CANONICAL_MULTIPLIERS: Mapping[str, float] = MappingProxyType(
    {_canonical_model_key(key): value for key, value in MODEL_OUTPUT_BUDGET_MULTIPLIERS.items()}
)


def output_budget_multiplier_for_model(model: str) -> float:
    """The multiplier of a model selector; a model nobody measured keeps today's budget (1.0)."""

    return _CANONICAL_MULTIPLIERS.get(canonical_output_budget_model_id(model), DEFAULT_OUTPUT_BUDGET_MULTIPLIER)


__all__ = [
    "DEFAULT_OUTPUT_BUDGET_MULTIPLIER",
    "MODEL_OUTPUT_BUDGET_MULTIPLIERS",
    "canonical_output_budget_model_id",
    "output_budget_multiplier_for_model",
    "scale_output_budget",
    "validate_output_budget_multiplier",
]
