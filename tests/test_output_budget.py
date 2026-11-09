"""Spec 069 WP-2, FR-006: the output budget of a block call and its model multiplier.

Section A pins the budget of today (multiplier 1) on the lengths where the formula turns:
the 512-token floor (0, 383, 384), an ordinary block (6 000), the exact ceiling (12 288) and
past it (20 000). It was run green against the unmodified generator before WP-2 changed it.
"""

from __future__ import annotations

import pytest

import docxaicorrector.generation._generation as generation

# length of the source text -> budget the generator asked for before spec 069.
_BUDGET_OF_TODAY = {
    0: 512,
    383: 512,
    384: 512,
    6_000: 8_000,
    12_288: 16_384,
    20_000: 16_384,
}


# --- A. golden: multiplier 1 is today's budget (SC-006) ------------------------------------


@pytest.mark.parametrize(("length", "expected"), sorted(_BUDGET_OF_TODAY.items()))
def test_budget_without_a_multiplier_is_the_budget_of_today(length, expected):
    assert generation._estimate_max_output_tokens("x" * length) == expected


def test_ceiling_and_ladder_constant_are_unchanged():
    assert generation._MODEL_OUTPUT_TOKEN_CEILING == 16_384
    assert generation._LADDER_BUDGETABLE_SOURCE_CHARS == 12_288


# --- B. the multiplier (FR-006; research R2, WP-0) ------------------------------------------


@pytest.mark.parametrize(("length", "expected"), sorted(_BUDGET_OF_TODAY.items()))
def test_multiplier_one_is_the_budget_of_today(length, expected):
    assert generation._estimate_max_output_tokens("x" * length, 1.0) == expected
    assert generation._estimate_max_output_tokens("x" * length, multiplier=1) == expected


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        # The floor is multiplied too (WP-0: both Haiku cut-offs were short blocks at 512).
        (0, 1_536),
        (383, 1_536),
        (384, 1_536),
        (1_000, 3 * 1_332),
        (3_000, 12_000),
        (6_000, 16_384),  # 24 000 → the provider ceiling
        (12_288, 16_384),
        (20_000, 16_384),
    ],
)
def test_multiplier_three_is_ceil_of_base_times_three_under_the_ceiling(length, expected):
    assert generation._estimate_max_output_tokens("x" * length, 3.0) == expected


def test_fractional_multiplier_rounds_up():
    # base 1 332 x 1.5 = 1 998; base 512 x 1.3 = 665.6 → 666
    assert generation._estimate_max_output_tokens("x" * 1_000, 1.5) == 1_998
    assert generation._estimate_max_output_tokens("x" * 10, 1.3) == 666


def test_ladder_budgetable_source_chars_follows_the_multiplier():
    ceiling = generation._MODEL_OUTPUT_TOKEN_CEILING
    assert generation._ladder_budgetable_source_chars(1) == 12_288
    assert generation._ladder_budgetable_source_chars(1.0) == generation._LADDER_BUDGETABLE_SOURCE_CHARS
    assert generation._ladder_budgetable_source_chars(3) == ceiling * 3 // (4 * 3) == 4_096
    # Derived, not chosen: a unit of exactly that length is the longest one still budgeted
    # under the ceiling at that multiplier.
    for multiplier in (1.0, 3.0):
        budgetable = generation._ladder_budgetable_source_chars(multiplier)
        assert generation._estimate_max_output_tokens("x" * budgetable, multiplier) <= ceiling


def test_multiplier_table_v1():
    from docxaicorrector.generation import output_budget

    assert dict(output_budget.MODEL_OUTPUT_BUDGET_MULTIPLIERS) == {
        "google/gemini-3.1-flash-lite-preview": 1.0,
        "google/gemini-3.7-flash": 1.0,
        "google/gemini-3.8-flash": 1.0,
        "anthropic/claude-haiku-5.5": 3.0,
    }


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        ("openrouter:google/gemini-3.1-flash-lite-preview", 1.0),
        ("google/gemini-3.7-flash", 1.0),
        ("openrouter:google/gemini-3.8-flash", 1.0),
        ("openrouter:anthropic/claude-haiku-5.5", 3.0),
        ("  OpenRouter:Anthropic/Claude-Haiku-5.5  ", 3.0),
        ("anthropic:claude-haiku-5.5", 3.0),
        ("openrouter:vendor/unknown-model", 1.0),
        ("gpt-5.4", 1.0),
        ("", 1.0),
    ],
)
def test_multiplier_of_a_model_selector(selector, expected):
    from docxaicorrector.generation import output_budget

    assert output_budget.output_budget_multiplier_for_model(selector) == expected


def test_invalid_multiplier_is_refused():
    from docxaicorrector.generation import output_budget

    for bad in (0, -1, float("nan"), float("inf"), True, "3"):
        with pytest.raises(ValueError):
            output_budget.validate_output_budget_multiplier(bad)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            generation._estimate_max_output_tokens("x", bad)  # type: ignore[arg-type]


_HAIKU_ALIASES = [
    "anthropic:claude-haiku-5.5",
    "anthropic:claude-haiku-5-5",
    "anthropic:anthropic/claude-haiku-5.5",
    "anthropic:anthropic/claude-haiku-5-5",
    "openrouter:anthropic/claude-haiku-5.5",
    "openrouter:anthropic/claude-haiku-5-5",
    "anthropic/claude-haiku-5.5",
    "anthropic/claude-haiku-5-5",
    "  OpenRouter:Anthropic/Claude-Haiku-5-5  ",
]


@pytest.mark.parametrize("alias", _HAIKU_ALIASES)
def test_every_spelling_of_one_native_model_gets_the_same_multiplier_and_floor(alias):
    """Codex acceptance review of spec 069, finding 6: dotted and dashed ids are one model."""

    from docxaicorrector.generation import output_budget

    multiplier = output_budget.output_budget_multiplier_for_model(alias)
    assert multiplier == 3.0
    assert generation._estimate_max_output_tokens("x", multiplier) == 1536


def test_unmeasured_dotted_models_still_keep_the_budget_of_today():
    from docxaicorrector.generation import output_budget

    for selector in ("openrouter:vendor/model-1.2", "openrouter:vendor/model-1-2", "anthropic:claude-opus-9.9"):
        assert output_budget.output_budget_multiplier_for_model(selector) == 1.0


def test_budget_dotted_version_rule_is_the_generators_rule():
    from docxaicorrector.generation import output_budget

    assert output_budget._DOTTED_VERSION_SEPARATOR_PATTERN.pattern == generation._DOTTED_VERSION_SEPARATOR_PATTERN.pattern
    # Both spellings reach the same API id, so they must reach the same budget row.
    for selector in ("anthropic:claude-haiku-5.5", "anthropic:claude-haiku-5-5", "anthropic/claude-haiku-5.5"):
        assert generation._normalize_anthropic_model_id(selector) == "claude-haiku-5-5"
