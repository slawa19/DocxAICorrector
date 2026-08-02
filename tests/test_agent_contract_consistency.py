"""Static guard: ``AGENTS.md`` must not contradict the constitution it declares BINDING.

Why this file exists
--------------------
An external review (Codex, gpt-5.6-sol, 2026-08-02) found the two documents an
agent is required to obey giving opposite instructions for the same situation:

* ``.specify/memory/constitution.md`` Principle III (constitution 2.0.0) says the
  **spec-only** tier is the normal case for bounded, defect-driven work, and that
  ``plan.md`` / ``tasks.md`` are never written after the fact;
* ``AGENTS.md``'s routing step 3 said, unconditionally, "If a spec exists and
  implementation direction is requested ... create ``plan.md``, ``research.md``,
  ``data-model.md``, ``contracts/`` ... and ``quickstart.md``".

An agent cannot satisfy both. Faced with two BINDING documents it picks one
arbitrarily, which is worse than having no rule: the choice is invisible in the
output and differs between runs.

What this guard checks, and what it deliberately does not
--------------------------------------------------------
It checks only *mechanical* agreement — that the routing step which triggers
``speckit-plan`` is gated on the full-cycle tier, that the spec-only default is
stated in ``AGENTS.md`` at all, and that the ratification caveat travels with the
principle it qualifies. It does NOT try to judge whether the prose is a good
summary of Principle III; no test can do that, and a guard that pretends to would
be the false green this repository has been burned by before.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_PATH = REPO_ROOT / "AGENTS.md"
CONSTITUTION_PATH = REPO_ROOT / ".specify/memory/constitution.md"

pytestmark = pytest.mark.static_workflow

# The wording in the constitution that this guard is keyed to. If Principle III is
# rewritten so that these disappear, the guard fails and whoever rewrote it has to
# revisit AGENTS.md too -- which is the whole point.
_CONSTITUTION_TIER_MARKERS = (
    "**Two tiers, and the smaller one is the normal case.**",
    "Never write `plan.md` or `tasks.md` after the fact.",
)

_NOT_RATIFIED_MARKER = "NOT YET RATIFIED"


def _agents_text() -> str:
    return AGENTS_PATH.read_text(encoding="utf-8")


def _constitution_text() -> str:
    return CONSTITUTION_PATH.read_text(encoding="utf-8")


def _speckit_plan_routing_step() -> str:
    """The numbered routing step in AGENTS.md that tells an agent to write a plan.

    Returned with its continuation lines, so a condition placed on the second line
    of the step still counts.
    """
    lines = _agents_text().splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if re.match(r"^\d+\.\s", line) or (line.strip() and not line.startswith((" ", "\t")))
    ]
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        step = "\n".join(lines[start:end])
        if "speckit-plan" in step and re.match(r"^\d+\.\s", lines[start]):
            return step
    raise AssertionError(
        "AGENTS.md no longer has a numbered routing step that invokes speckit-plan. "
        "This guard is keyed to it; re-point it rather than deleting it."
    )


def test_constitution_still_states_the_two_tier_rule_this_guard_is_keyed_to() -> None:
    """Anti-vacuum: the checks below are meaningless if the principle moved."""
    text = _constitution_text()
    missing = [marker for marker in _CONSTITUTION_TIER_MARKERS if marker not in text]
    assert not missing, (
        "Principle III no longer carries the wording tests/test_agent_contract_consistency.py "
        f"cross-checks AGENTS.md against (missing: {missing!r}). If the principle was "
        "deliberately rewritten, update AGENTS.md's 'Which tier' section and this guard "
        "together — they exist to stay in step."
    )


def test_agents_md_does_not_demand_a_plan_unconditionally() -> None:
    """The routing step that writes ``plan.md`` must be gated on the full-cycle tier."""
    step = _speckit_plan_routing_step()
    assert "full-cycle" in step.lower(), (
        "AGENTS.md routing step for speckit-plan is unconditional:\n\n"
        f"{step}\n\n"
        "Constitution Principle III makes the spec-only tier the default and reserves "
        "plan.md/tasks.md for full-cycle work. An agent told to always produce a plan "
        "cannot satisfy both documents and will pick one at random. Gate the step on "
        "the tier."
    )


def test_agents_md_states_the_spec_only_tier_is_the_default() -> None:
    text = _agents_text()
    assert "Spec only" in text and "the default" in text, (
        "AGENTS.md no longer tells an agent that a spec on its own is the normal case. "
        "Principle III says 48 of 53 specs are that tier and that guessing 'full cycle' "
        "is not the safe default; AGENTS.md is the document agents actually read first, "
        "so the tier choice has to be visible here."
    )


def test_agents_md_carries_the_ratification_caveat_while_the_constitution_does() -> None:
    """The caveat travels with the principle: 2.0.0 is the owner's call, not an agent's."""
    if _NOT_RATIFIED_MARKER not in _constitution_text():
        pytest.skip("constitution no longer flags its version as awaiting ratification")
    assert _NOT_RATIFIED_MARKER in _agents_text(), (
        "The constitution flags its current version as NOT YET RATIFIED by the owner, "
        "but AGENTS.md presents the two-tier rule as settled. An agent reading only "
        "AGENTS.md would never learn to ask. Keep the caveat next to the rule it "
        "qualifies, or drop it from both documents once the owner ratifies."
    )
