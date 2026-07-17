"""Acceptance unmapped-coverage as review DATA (spec 038 / Constitution VII).

Coverage is review DATA, not a verdict gate. The three coverage checks
(``formatting_diagnostics_threshold``, ``unmapped_source_threshold``,
``unmapped_target_threshold``) never enter ``failed_checks`` on residual unmapped
coverage: the source/target coverage checks are ADVISORY (``passed=True`` unconditionally,
``failed_reason="advisory_only"``, ``review_data=True``), and
``formatting_diagnostics_threshold`` gates ONLY on the genuine caption/heading structural
conflict clause. Spec 037's furniture-crediting arithmetic
(``resolve_genuine_unmapped_count`` + the credited/genuine audit fields) is KEPT — it now
feeds the review-DATA payload instead of a pass/fail branch.

The pass-through exclusion (front-matter / bounded-TOC / page-furniture / references /
captions / part dividers) still runs and its per-category provenance stays fully auditable
in the details. These tests load the real saved artifacts (Money & Sustainability Gemini
fixture; lietaer/mazzucato breadth full-run reports) and prove:

  * per-category pass-through provenance counters are present and auditable;
  * the three coverage checks stay OUT of failed_checks with ``passed is True``;
  * ANTI-VACUUM (now enforced on the DATA, not the gate): a synthetic REAL unmapped
    body-prose paragraph raises the genuine unmapped COUNT by exactly one and flips
    ``genuine_exceeds_threshold`` at a tight threshold — the loss is surfaced honestly —
    while the check's ``passed`` stays True and it never enters failed_checks.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from docxaicorrector.validation.acceptance import (
    build_acceptance_verdict,
    resolve_genuine_unmapped_count,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "money_gemini_passthrough_fixture.json"
# Profile threshold for this document (max_unmapped_source/target_paragraphs).
MONEY_THRESHOLD = 16

# --- Breadth artifacts (GLOBAL_PLAN item 1-A): the saved lietaer/mazzucato runs that
# failed acceptance PURELY on references/captions/part pass-through the Money fix did not
# yet credit. These are the real, on-disk full-run reports (no LLM to reproduce). ---
_RUNS_ROOT = PROJECT_ROOT / "tests" / "artifacts" / "real_document_pipeline" / "runs"
LIETAER_REPORT_PATH = _RUNS_ROOT / "20260622T_lietaer_breadth" / "lietaer_pdf_full_benchmark_report.json"
MAZZUCATO_REPORT_PATH = _RUNS_ROOT / "20260622T_mazzucato_breadth" / "mazzucato_pdf_full_benchmark_report.json"
# Profile thresholds for these documents (corpus_registry.toml: both 12 source / 6 target).
BREADTH_SOURCE_THRESHOLD = 12
BREADTH_TARGET_THRESHOLD = 6
_THREE_UNMAPPED_CHECKS = (
    "formatting_diagnostics_threshold",
    "unmapped_source_threshold",
    "unmapped_target_threshold",
)


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


def test_real_body_paragraph_still_surfaced_in_review_data(validation_module, money_report):
    """ANTI-VACUUM on the DATA (spec 038): a genuine unmapped main-body prose paragraph
    (not front-matter, not TOC, not furniture) must STILL raise the genuine unmapped COUNT
    by one and flip ``genuine_exceeds_threshold`` at a tight threshold — the loss is
    surfaced honestly — but coverage is review data, so ``passed`` stays True and the
    check never enters failed_checks."""
    base = _evaluate(validation_module, money_report)
    base_check = _checks_by_name(base)["unmapped_source_threshold"]
    base_src = base_check["actual"]
    base_genuine = base_check["genuine_unmapped_source_count"]
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

    # Evaluate the poisoned report at a tight threshold pinned to the baseline residual so
    # the one extra genuine loss exceeds it.
    poisoned_acceptance = validation_module.evaluate_lietaer_acceptance(
        poisoned,
        mismatch_threshold=base_src,
        unmapped_target_threshold=MONEY_THRESHOLD,
    )
    poisoned_src = _checks_by_name(poisoned_acceptance)["unmapped_source_threshold"]

    # The synthetic real body paragraph is NOT classified as pass-through: the retained
    # (effective) count and the genuine count each rise by exactly one.
    assert poisoned_src["actual"] == base_src + 1
    assert poisoned_src["genuine_unmapped_source_count"] == base_genuine + 1

    # The residual severity is surfaced in the DATA: genuine now exceeds the tight
    # threshold.
    assert poisoned_src["genuine_exceeds_threshold"] is True

    # But coverage is review DATA — the check still passes and never enters failed_checks.
    assert poisoned_src["passed"] is True
    assert "unmapped_source_threshold" not in set(poisoned_acceptance.get("failed_checks", []))


# ===================================================================================
# Item 1-A breadth: generalise the pass-through exclusion (references / captions / part)
# across books, on the SAVED lietaer + mazzucato full-run artifacts. Both failed
# acceptance ONLY on this pass-through; the Money fix (front-matter / TOC / furniture)
# did not credit it. These tests prove the three unmapped checks now leave failed_checks
# for refs/caption/part reasons, that the new categories carry provenance, and — the
# counter-proof — that a genuine main-body prose loss is STILL counted and re-fails.
# ===================================================================================


def _load_report(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _evaluate_breadth(validation_module, report):
    return validation_module.evaluate_lietaer_acceptance(
        report,
        mismatch_threshold=BREADTH_SOURCE_THRESHOLD,
        unmapped_target_threshold=BREADTH_TARGET_THRESHOLD,
    )


@pytest.fixture(scope="module")
def lietaer_report():
    if not LIETAER_REPORT_PATH.exists():
        pytest.skip(f"breadth artifact not present: {LIETAER_REPORT_PATH}")
    return _load_report(LIETAER_REPORT_PATH)


@pytest.fixture(scope="module")
def mazzucato_report():
    if not MAZZUCATO_REPORT_PATH.exists():
        pytest.skip(f"breadth artifact not present: {MAZZUCATO_REPORT_PATH}")
    return _load_report(MAZZUCATO_REPORT_PATH)


@pytest.mark.parametrize(
    "report_fixture, expect_caption, expect_part",
    [
        # lietaer: back-of-book index (references) dominates; one "Part Two" divider; no captions.
        ("lietaer_report", False, True),
        # mazzucato: endnotes (references) + two "Figure N" captions; no part divider in the tail.
        ("mazzucato_report", True, False),
    ],
)
def test_breadth_refs_captions_part_leave_failed_checks(
    validation_module, request, report_fixture, expect_caption, expect_part
):
    report = request.getfixturevalue(report_fixture)
    acceptance = _evaluate_breadth(validation_module, report)
    checks = _checks_by_name(acceptance)
    failed = set(acceptance.get("failed_checks", []))

    fmt = checks["formatting_diagnostics_threshold"]
    src = checks["unmapped_source_threshold"]
    tgt = checks["unmapped_target_threshold"]

    # (pre-condition) The RAW pass-through noise really did overflow the profile
    # thresholds — so a pass here is earned by exclusion, not by an already-clean run.
    assert src["raw_worst_unmapped_source_count"] > BREADTH_SOURCE_THRESHOLD
    assert tgt["raw_unmapped_target_count"] > BREADTH_TARGET_THRESHOLD

    # (a) The three unmapped/formatting checks now pass and leave failed_checks.
    for name in _THREE_UNMAPPED_CHECKS:
        assert checks[name]["passed"] is True, name
        assert name not in failed, name

    # The residual sits under the profile threshold after exclusion.
    assert src["actual"] <= BREADTH_SOURCE_THRESHOLD
    assert tgt["actual"] <= BREADTH_TARGET_THRESHOLD

    # (b) Per-category provenance for the NEW categories is present and auditable, on
    # both the source and the target side.
    for field in (
        "passthrough_references_source_count",
        "passthrough_caption_source_count",
        "passthrough_part_source_count",
    ):
        assert isinstance(fmt[field], int)
        assert isinstance(src[field], int)
    for field in (
        "passthrough_references_target_count",
        "passthrough_caption_target_count",
        "passthrough_part_target_count",
    ):
        assert isinstance(tgt[field], int)

    # References/bibliography/index is the dominant newly-excluded category on both books,
    # detected as a back-matter region (auditable start index, not a hard-coded literal).
    assert src["passthrough_references_source_count"] > 0
    assert isinstance(fmt["references_region_source_start_index"], int)
    assert tgt["passthrough_references_target_count"] > 0

    # Book-specific shapes: mazzucato has figure captions, lietaer has a part divider.
    if expect_caption:
        assert src["passthrough_caption_source_count"] > 0
    if expect_part:
        assert src["passthrough_part_source_count"] > 0

    # The excluded categories fully account for the drop from raw to residual (including
    # the 3A index-region / attribution categories added on top of the 1‑A set).
    category_total = (
        src["passthrough_front_matter_source_count"]
        + src["passthrough_bounded_toc_source_count"]
        + src["passthrough_page_furniture_source_count"]
        + src["passthrough_references_source_count"]
        + src["passthrough_caption_source_count"]
        + src["passthrough_part_source_count"]
        + src["passthrough_index_source_count"]
        + src["passthrough_attribution_source_count"]
    )
    assert src["raw_worst_unmapped_source_count"] - category_total == src["actual"]


def test_breadth_counter_proof_real_body_paragraph_still_surfaced_in_review_data(validation_module):
    """(c) ANTI-VACUUM on the DATA (spec 038), breadth artifact: a genuine unmapped
    main-body prose paragraph — placed in the body region, BEFORE the references region,
    and not a caption/part/furniture line — must STILL raise the genuine unmapped COUNT by
    one and flip ``genuine_exceeds_threshold`` at a tight threshold. Proves the extended
    exclusion did not go blind. Coverage is review data, so ``passed`` stays True and the
    check never enters failed_checks."""
    if not MAZZUCATO_REPORT_PATH.exists():
        pytest.skip(f"breadth artifact not present: {MAZZUCATO_REPORT_PATH}")
    # Fresh load so the in-place mutation below cannot leak into the module-scoped fixture.
    report = _load_report(MAZZUCATO_REPORT_PATH)

    base = _evaluate_breadth(validation_module, report)
    base_fmt = _checks_by_name(base)["formatting_diagnostics_threshold"]
    base_src_check = _checks_by_name(base)["unmapped_source_threshold"]
    base_src = base_src_check["actual"]
    base_genuine = base_src_check["genuine_unmapped_source_count"]
    assert base_src <= BREADTH_SOURCE_THRESHOLD  # baseline already under threshold

    references_start = base_fmt["references_region_source_start_index"]
    front_matter_boundary = base_fmt["front_matter_boundary_source_index"]
    assert isinstance(references_start, int)

    # The un-poisoned report passes at a threshold tightened to its own residual — the
    # baseline against which the extra real loss must make a difference.
    baseline_at_tight = validation_module.evaluate_lietaer_acceptance(
        report,
        mismatch_threshold=base_src,
        unmapped_target_threshold=BREADTH_TARGET_THRESHOLD,
    )
    assert _checks_by_name(baseline_at_tight)["unmapped_source_threshold"]["passed"] is True

    payload = report["formatting_diagnostics"][0]
    registry = payload["source_registry"]

    # Anchor the synthetic paragraph on a real mapped BODY unit sitting in the main body
    # (past the front-matter boundary, well before the references region) so it lands in
    # genuine body territory — not front-matter, TOC, captions, or the notes/index tail.
    lower_bound = max(int(front_matter_boundary or 0), 0)
    body_anchor = next(
        entry
        for entry in registry
        if str(entry.get("role") or entry.get("structural_role") or "").strip().lower() == "body"
        and entry.get("mapped_target_index") is not None
        and lower_bound < int(entry.get("source_index", -1)) < references_start
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
            "This is a genuinely unmapped main-body prose paragraph that develops a "
            "substantive argument across a full sentence of real running text, well "
            "before the notes and bibliography region and outside any caption, part "
            "divider, or page-furniture line."
        ),
    }
    insert_at = next(
        i for i, entry in enumerate(registry) if int(entry.get("source_index", -1)) == synthetic_index
    ) + 1
    registry.insert(insert_at, synthetic)
    payload["unmapped_source_ids"] = list(payload["unmapped_source_ids"]) + ["p_synthetic_body_loss"]

    # Evaluate at a tight threshold pinned to the baseline residual so the one extra
    # genuine loss exceeds it.
    poisoned = validation_module.evaluate_lietaer_acceptance(
        report,
        mismatch_threshold=base_src,
        unmapped_target_threshold=BREADTH_TARGET_THRESHOLD,
    )
    poisoned_src = _checks_by_name(poisoned)["unmapped_source_threshold"]

    # The synthetic real body paragraph is NOT swallowed by any pass-through category:
    # the effective residual and the genuine count each rise by exactly one.
    assert poisoned_src["actual"] == base_src + 1
    assert poisoned_src["genuine_unmapped_source_count"] == base_genuine + 1

    # The residual severity is surfaced in the DATA: genuine now exceeds the tight
    # threshold.
    assert poisoned_src["genuine_exceeds_threshold"] is True

    # But coverage is review DATA — the check still passes and never enters failed_checks.
    assert poisoned_src["passed"] is True
    assert "unmapped_source_threshold" not in set(poisoned.get("failed_checks", []))


# ===================================================================================
# Spec 037: the structural passthrough gate CREDITS agreed passthrough furniture and
# hard-gates ONLY the genuine (non-furniture) remainder. These are synthetic verdict
# inputs driven directly through ``build_acceptance_verdict`` (the shared harness↔prod
# assembler) plus focused unit tests of the ``resolve_genuine_unmapped_count`` credit
# arithmetic (Constitution VII anti-vacuum: real body loss is still gated).
# ===================================================================================

_GENUINE_BODY_PREVIEW = (
    "This is a genuinely unmapped main-body prose paragraph that develops a substantive "
    "argument across a full sentence of real running text, well outside any front-matter, "
    "table of contents, references region, caption, part divider, or page-furniture line."
)


def _source_entry(paragraph_id, source_index, text, *, mapped=None):
    return {
        "paragraph_id": paragraph_id,
        "source_index": source_index,
        "role": "body",
        "structural_role": "body",
        "heading_level": None,
        "list_kind": None,
        "mapped_target_index": mapped,
        "text_preview": text,
    }


def _target_entry(target_index, text):
    return {"target_index": target_index, "text_preview": text}


def _synthetic_report(*, furniture_count, genuine_body_count):
    """Build a report whose single formatting-diagnostics payload flows through the
    role-aware coverage path with ``furniture_count`` page-furniture unmapped lines
    (bare page numbers) and ``genuine_body_count`` genuinely-unmapped body prose lines,
    on BOTH the source and target sides."""
    source_registry = [
        _source_entry(f"p_anchor_{i}", i, f"Абзац основного текста номер {i}.", mapped=i)
        for i in range(6)
    ]
    target_registry = [_target_entry(i, f"Абзац основного текста номер {i}.") for i in range(6)]
    unmapped_source_ids = []
    unmapped_target_indexes = []

    next_index = 300
    for f in range(furniture_count):
        pid = f"p_furn_{f}"
        page_number_text = str(200 + f)  # bare page number -> page_furniture (form-only)
        source_registry.append(_source_entry(pid, next_index, page_number_text))
        target_registry.append(_target_entry(next_index, page_number_text))
        unmapped_source_ids.append(pid)
        unmapped_target_indexes.append(next_index)
        next_index += 1
    for b in range(genuine_body_count):
        pid = f"p_body_{b}"
        source_registry.append(_source_entry(pid, next_index, _GENUINE_BODY_PREVIEW))
        target_registry.append(_target_entry(next_index, _GENUINE_BODY_PREVIEW))
        unmapped_source_ids.append(pid)
        unmapped_target_indexes.append(next_index)
        next_index += 1

    payload = {
        "unmapped_source_ids": unmapped_source_ids,
        "source_registry": source_registry,
        "unmapped_source_residual_diagnostics": {
            "effective_formatting_coverage_diagnostics": {"format_neutral_creditable_count": 0}
        },
        "unmapped_target_indexes": unmapped_target_indexes,
        "target_registry": target_registry,
        "unmapped_target_residual_diagnostics": {"split_accounting_creditable_count": 0},
    }
    return {
        "result": "succeeded",
        "runtime_config": {"effective": {"processing_operation": "translate"}},
        "translation_quality_report": {},
        "formatting_diagnostics": [payload],
        "output_artifacts": {},
        "runtime": {},
        "reader_cleanup_evidence": {},
        "preparation_diagnostic_snapshot": {},
    }


def _verdict(report, *, mismatch_threshold, unmapped_target_threshold):
    return build_acceptance_verdict(
        report,
        mismatch_threshold=mismatch_threshold,
        unmapped_target_threshold=unmapped_target_threshold,
    )


def _failed_names(verdict) -> set:
    names = verdict.get("failed_checks", [])
    return set(names) if isinstance(names, list) else set()


# --------------------------------------------------------------------------------- #
# Unit tests of the credit arithmetic (deterministic, no coverage plumbing).
# --------------------------------------------------------------------------------- #


def test_genuine_count_anti_vacuum_no_furniture_gates_full_body():
    # No furniture available -> genuine equals the effective count (body still gated).
    genuine, credited = resolve_genuine_unmapped_count(
        effective_count=20, pre_credit_base_count=20, passthrough_furniture_count=0
    )
    assert (genuine, credited) == (20, 0)


def test_genuine_count_furniture_only_credits_to_zero():
    # All effective unmapped is furniture that was NOT yet subtracted -> genuine floors to 0.
    genuine, credited = resolve_genuine_unmapped_count(
        effective_count=10, pre_credit_base_count=10, passthrough_furniture_count=10
    )
    assert (genuine, credited) == (0, 10)


def test_genuine_count_mixed_credits_only_furniture_remainder():
    # 3 furniture + 7 genuine body, none pre-subtracted -> genuine == 7.
    genuine, credited = resolve_genuine_unmapped_count(
        effective_count=10, pre_credit_base_count=10, passthrough_furniture_count=3
    )
    assert (genuine, credited) == (7, 3)


def test_genuine_count_never_double_credits_already_subtracted_furniture():
    # Role-aware effective already removed the 4 furniture (base 14 -> effective 10);
    # crediting must NOT subtract them a second time (mirrors max(creditable,passthrough)).
    genuine, credited = resolve_genuine_unmapped_count(
        effective_count=10, pre_credit_base_count=14, passthrough_furniture_count=4
    )
    assert (genuine, credited) == (10, 0)


# --------------------------------------------------------------------------------- #
# Verdict-level tests through build_acceptance_verdict.
# --------------------------------------------------------------------------------- #


def test_verdict_furniture_only_is_excused_on_both_sides():
    report = _synthetic_report(furniture_count=8, genuine_body_count=0)
    verdict = _verdict(report, mismatch_threshold=0, unmapped_target_threshold=0)
    checks = _checks_by_name(verdict)
    src = checks["unmapped_source_threshold"]
    tgt = checks["unmapped_target_threshold"]

    # Furniture was classified and credited; the genuine remainder is zero, so the checks
    # pass even at a zero threshold and leave failed_checks.
    assert src["credited_passthrough_furniture_source_count"] == 8
    assert tgt["credited_passthrough_furniture_target_count"] == 8
    assert src["genuine_unmapped_source_count"] == 0
    assert tgt["genuine_unmapped_target_count"] == 0
    # Genuine is zero <= threshold, so the review-data severity marker stays clear.
    assert src["genuine_exceeds_threshold"] is False
    assert tgt["genuine_exceeds_threshold"] is False
    assert src["passed"] is True
    assert tgt["passed"] is True
    failed = _failed_names(verdict)
    assert "unmapped_source_threshold" not in failed
    assert "unmapped_target_threshold" not in failed


def test_verdict_genuine_body_surfaced_but_not_gated():
    # 8 furniture + 3 genuine body at threshold 2: the furniture is credited and the 3
    # genuine body paragraphs are SURFACED honestly (genuine count == 3,
    # genuine_exceeds_threshold True), but coverage is review DATA — neither check enters
    # failed_checks and both stay passed (spec 038 / Constitution VII).
    report = _synthetic_report(furniture_count=8, genuine_body_count=3)
    verdict = _verdict(report, mismatch_threshold=2, unmapped_target_threshold=2)
    checks = _checks_by_name(verdict)
    src = checks["unmapped_source_threshold"]
    tgt = checks["unmapped_target_threshold"]

    assert src["genuine_unmapped_source_count"] == 3
    assert tgt["genuine_unmapped_target_count"] == 3
    assert src["credited_passthrough_furniture_source_count"] == 8
    assert tgt["credited_passthrough_furniture_target_count"] == 8
    # The residual severity is surfaced in the DATA (genuine 3 > threshold 2)...
    assert src["genuine_exceeds_threshold"] is True
    assert tgt["genuine_exceeds_threshold"] is True
    # ...but coverage never gates: both checks pass and stay out of failed_checks.
    assert src["passed"] is True
    assert tgt["passed"] is True
    failed = _failed_names(verdict)
    assert "unmapped_source_threshold" not in failed
    assert "unmapped_target_threshold" not in failed


def test_verdict_mixed_gates_only_the_genuine_remainder():
    # Same 8 furniture + 3 body, but a threshold of 3 leaves ONLY the genuine remainder
    # (3) at/under the bar -> the checks pass, proving furniture is not counted against it.
    report = _synthetic_report(furniture_count=8, genuine_body_count=3)
    verdict = _verdict(report, mismatch_threshold=3, unmapped_target_threshold=3)
    checks = _checks_by_name(verdict)
    src = checks["unmapped_source_threshold"]
    tgt = checks["unmapped_target_threshold"]

    assert src["genuine_unmapped_source_count"] == 3
    assert tgt["genuine_unmapped_target_count"] == 3
    # The raw unmapped count (furniture included) is well above the threshold; only the
    # genuine remainder (3) is measured, and it sits at/under the bar.
    assert src["raw_worst_unmapped_source_count"] > 3
    assert tgt["raw_unmapped_target_count"] > 3
    # Genuine (3) <= threshold (3), so the review-data severity marker stays clear.
    assert src["genuine_exceeds_threshold"] is False
    assert tgt["genuine_exceeds_threshold"] is False
    assert src["passed"] is True
    assert tgt["passed"] is True
    failed = _failed_names(verdict)
    assert "unmapped_source_threshold" not in failed
    assert "unmapped_target_threshold" not in failed
