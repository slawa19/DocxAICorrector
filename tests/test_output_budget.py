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
