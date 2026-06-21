"""Acceptance-gate pass-through exclusion (front-matter / bounded-TOC / page-furniture).

Director scope decision (GLOBAL_PLAN 2026-06-20c): TOC, front-matter (title/cover/
attributions) and source/reference pages are PASS-THROUGH — translated as-is but
EXCLUDED from the strict unmapped-paragraph acceptance thresholds. The main-content text
is the quality focus.

On the saved Money & Sustainability (Gemini) run, acceptance=FAILED purely because the
unmapped thresholds drowned in that pass-through noise (71 source / 67 target). These
tests load the real saved artifacts (compacted into a fixture with REAL values) and prove:

  * the three unmapped checks drop drastically and leave failed_checks once the agreed
    (A) front-matter / (B) bounded-TOC / (C) page-furniture categories are excluded;
  * per-category provenance counters are present in the check details (auditable);
  * COUNTER-PROOF: a synthetic REAL unmapped body-prose paragraph (structural_role=body,
    long prose, outside TOC/front-matter, not furniture) is STILL counted and re-fails the
    threshold — the gate did not go blind in the other direction.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "money_gemini_passthrough_fixture.json"
# Profile threshold for this document (max_unmapped_source/target_paragraphs).
MONEY_THRESHOLD = 16


def _load_validation_module():
    module_path = PROJECT_ROOT / "tests" / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py"
    spec = importlib.util.spec_from_file_location("run_lietaer_validation", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load run_lietaer_validation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validation_module():
    return _load_validation_module()


@pytest.fixture
def money_report():
    with FIXTURE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _checks_by_name(acceptance: dict) -> dict:
    return {check["name"]: check for check in acceptance.get("checks", [])}


def _evaluate(validation_module, report):
    return validation_module.evaluate_lietaer_acceptance(
        report,
        mismatch_threshold=MONEY_THRESHOLD,
        unmapped_target_threshold=MONEY_THRESHOLD,
    )


def test_passthrough_excludes_only_agreed_categories(validation_module, money_report):
    acceptance = _evaluate(validation_module, money_report)
    checks = _checks_by_name(acceptance)

    fmt = checks["formatting_diagnostics_threshold"]
    src = checks["unmapped_source_threshold"]
    tgt = checks["unmapped_target_threshold"]

    # The raw, pre-exclusion counts the saved run failed on.
    assert fmt["raw_worst_unmapped_source_count"] == 82
    assert tgt["raw_unmapped_target_count"] == 67

    # Pass-through provenance is present and auditable (per category).
    assert src["passthrough_front_matter_source_count"] is not None
    assert src["passthrough_bounded_toc_source_count"] is not None
    assert src["passthrough_page_furniture_source_count"] is not None
    assert tgt["passthrough_front_matter_target_count"] is not None
    assert tgt["passthrough_page_furniture_target_count"] is not None

    # Page furniture (bare digits / footnote markers / dividers / chapter markers) is the
    # dominant excluded category on both sides.
    assert src["passthrough_page_furniture_source_count"] >= 40
    assert tgt["passthrough_page_furniture_target_count"] >= 40
    # Front-matter (title/cover/attributions before the report body) is excluded too.
    assert src["passthrough_front_matter_source_count"] >= 10
    assert tgt["passthrough_front_matter_target_count"] >= 1
    # The front-matter boundary was detected, not hard-coded (carried on the
    # formatting_diagnostics / target checks).
    assert isinstance(fmt["front_matter_boundary_source_index"], int)
    assert isinstance(tgt["front_matter_boundary_target_index"], int)

    # Counts drop drastically and now sit under the profile threshold.
    assert src["actual"] <= MONEY_THRESHOLD
    assert tgt["actual"] <= MONEY_THRESHOLD
    assert src["actual"] < 82
    assert tgt["actual"] < 67

    # The three checks pass, so they leave failed_checks for pass-through reasons.
    failed = set(acceptance.get("failed_checks", []))
    assert "formatting_diagnostics_threshold" not in failed
    assert "unmapped_source_threshold" not in failed
    assert "unmapped_target_threshold" not in failed
    assert fmt["passed"] is True
    assert src["passed"] is True
    assert tgt["passed"] is True


def test_real_body_paragraph_still_fails_the_gate(validation_module, money_report):
    """COUNTER-PROOF: a genuine unmapped main-body prose paragraph (not front-matter, not
    TOC, not furniture) must STILL be counted and re-trip the source threshold."""
    base = _evaluate(validation_module, money_report)
    base_src = _checks_by_name(base)["unmapped_source_threshold"]["actual"]
    assert base_src <= MONEY_THRESHOLD  # baseline already under threshold

    poisoned = copy.deepcopy(money_report)
    payload = poisoned["formatting_diagnostics"][0]
    registry = payload["source_registry"]

    # Place the synthetic paragraph deep in the main body (well past the front-matter
    # boundary and the TOC), with a long real-prose preview that is not page furniture.
    body_anchor = next(
        entry for entry in registry if entry.get("source_index") == 902 and entry.get("role") == "body"
    )
    synthetic_index = int(body_anchor["source_index"])
    synthetic = {
        "paragraph_id": "p_synthetic_body_loss",
        "source_index": synthetic_index,
        "role": "body",
        "structural_role": "body",
        "heading_level": None,
        "list_kind": None,
        "mapped_target_index": None,
        "text_preview": (
            "This is a genuinely unmapped main-body prose paragraph that argues a "
            "substantive economic point across a full sentence of real running text, "
            "well outside any front-matter, table of contents, or page-furniture region."
        ),
    }
    # Insert just after the anchor so it lands inside the body region, then add it to the
    # unmapped set. We bump nothing else: it must be counted on its own merit.
    insert_at = next(i for i, entry in enumerate(registry) if entry.get("source_index") == synthetic_index) + 1
    registry.insert(insert_at, synthetic)
    payload["unmapped_source_ids"] = list(payload["unmapped_source_ids"]) + ["p_synthetic_body_loss"]

    poisoned_acceptance = _evaluate(validation_module, poisoned)
    poisoned_src = _checks_by_name(poisoned_acceptance)["unmapped_source_threshold"]

    # The synthetic real body paragraph is NOT classified as pass-through: the retained
    # (effective) count rises by exactly one.
    assert poisoned_src["actual"] == base_src + 1

    # With the threshold at exactly the baseline residual, one extra real loss re-fails.
    tight = validation_module.evaluate_lietaer_acceptance(
        poisoned,
        mismatch_threshold=base_src,
        unmapped_target_threshold=MONEY_THRESHOLD,
    )
    tight_checks = _checks_by_name(tight)
    assert tight_checks["unmapped_source_threshold"]["passed"] is False
    assert "unmapped_source_threshold" in set(tight.get("failed_checks", []))
    # And the same baseline threshold leaves the un-poisoned report passing — proving the
    # extra failure is caused by the real body loss, not a lowered bar.
    baseline_at_tight = validation_module.evaluate_lietaer_acceptance(
        money_report,
        mismatch_threshold=base_src,
        unmapped_target_threshold=MONEY_THRESHOLD,
    )
    assert _checks_by_name(baseline_at_tight)["unmapped_source_threshold"]["passed"] is True
