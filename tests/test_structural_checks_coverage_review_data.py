"""Spec 039 (A) / Constitution VII anti-regression: the canonical structural gate
(``validation/structural_checks.py::_build_structural_checks``) must treat the two unmapped
coverage axes as REVIEW DATA (``passed=True`` + advisory markers), never as a hard gate, while
every GENUINE structural gate (text similarity, heading drift) still bites.

The roll-up at ``validation/structural.py:624`` reads only ``passed`` to build ``failed_checks``;
we replicate that exact expression so the assertions exercise the real verdict logic without a
real-document run.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import docxaicorrector.validation.structural as structural_validation_runtime
from docxaicorrector.validation.profiles import DocumentProfile


def _rollup_failed_checks(checks: list[dict[str, object]]) -> list[str]:
    # Byte-identical to validation/structural.py:624 (_build_validation_result).
    return [str(check["name"]) for check in checks if not bool(check["passed"])]


def _profile(*, min_text_similarity: float = 0.95, max_heading_level_drift: int = 1) -> DocumentProfile:
    # A minimal duck-typed stand-in; _build_structural_checks only reads these attributes. Cast so
    # the pyright ratchet stays clean (mirrors the SimpleNamespace-based profiles in
    # test_structure_validation.py without adding to the error baseline).
    return cast(
        DocumentProfile,
        SimpleNamespace(
            max_formatting_diagnostics=5,
        max_unmapped_source_paragraphs=5,
        max_unmapped_target_paragraphs=5,
        max_heading_level_drift=max_heading_level_drift,
        min_text_similarity=min_text_similarity,
        require_numbered_lists_preserved=False,
        require_nonempty_output=False,
        forbid_heading_only_collapse=False,
        require_toc_detected=False,
        require_pdf_conversion=False,
        require_no_bullet_headings=False,
        require_no_toc_body_concat=False,
        require_translation_domain=None,
        ),
    )


def test_coverage_axes_exceeding_threshold_are_advisory_review_data_not_gated() -> None:
    # Source actual (role_aware branch) = 50 > allowed 5; target actual (topology_unit) = 40 > 5.
    checks = structural_validation_runtime._build_structural_checks(
        document_profile=_profile(),
        result="succeeded",
        metrics={
            "formatting_diagnostics_count": 0,
            "max_unmapped_source_paragraphs": 12,
            "max_unmapped_target_paragraphs": 9,
            "raw_unmapped_source_paragraph_count": 50,
            "raw_unmapped_target_paragraph_count": 40,
            "effective_unmapped_source_count": 50,
            "structure_unit_unmapped_source_count": 33,
            "structure_unit_unmapped_target_count": 40,
            "unmapped_source_count_basis": "role_aware_formatting_coverage",
            "unmapped_target_count_basis": "topology_unit",
            "heading_level_drift": 0,
            "text_similarity": 0.99,
            "heading_only_output_detected": False,
        },
        output_artifacts={"output_docx_openable": True, "output_visible_text_chars": 100},
    )
    by_name = {check["name"]: check for check in checks}

    for axis in ("unmapped_source_threshold", "unmapped_target_threshold"):
        check = by_name[axis]
        assert check["passed"] is True, axis
        assert check["advisory"] is True, axis
        assert check["review_data"] is True, axis
        assert check["exceeds_threshold"] is True, axis

    # Residual severity is still visible: actual reflects the gate-source count.
    assert by_name["unmapped_source_threshold"]["actual"] == 50
    assert by_name["unmapped_source_threshold"]["allowed"] == 5
    assert by_name["unmapped_target_threshold"]["actual"] == 40
    assert by_name["unmapped_target_threshold"]["allowed"] == 5

    failed = _rollup_failed_checks(checks)
    assert "unmapped_source_threshold" not in failed
    assert "unmapped_target_threshold" not in failed
    # Nothing genuine is wrong here, so the gate is green overall.
    assert failed == []


def test_coverage_within_threshold_still_marks_advisory_and_not_exceeds() -> None:
    checks = structural_validation_runtime._build_structural_checks(
        document_profile=_profile(),
        result="succeeded",
        metrics={
            "formatting_diagnostics_count": 0,
            "max_unmapped_source_paragraphs": 1,
            "max_unmapped_target_paragraphs": 1,
            "raw_unmapped_source_paragraph_count": 1,
            "raw_unmapped_target_paragraph_count": 1,
            "structure_unit_unmapped_source_count": 1,
            "structure_unit_unmapped_target_count": 1,
            "unmapped_source_count_basis": "topology_unit",
            "unmapped_target_count_basis": "topology_unit",
            "heading_level_drift": 0,
            "text_similarity": 0.99,
            "heading_only_output_detected": False,
        },
        output_artifacts={"output_docx_openable": True, "output_visible_text_chars": 100},
    )
    by_name = {check["name"]: check for check in checks}
    for axis in ("unmapped_source_threshold", "unmapped_target_threshold"):
        assert by_name[axis]["passed"] is True, axis
        assert by_name[axis]["advisory"] is True, axis
        assert by_name[axis]["review_data"] is True, axis
        assert by_name[axis]["exceeds_threshold"] is False, axis


def test_genuine_gates_still_bite_when_coverage_is_advisory() -> None:
    # Anti-vacuum: text similarity BELOW min and heading drift ABOVE max are GENUINE structural
    # gates — they must still land in failed_checks even though coverage is now advisory.
    checks = structural_validation_runtime._build_structural_checks(
        document_profile=_profile(min_text_similarity=0.95, max_heading_level_drift=1),
        result="succeeded",
        metrics={
            "formatting_diagnostics_count": 0,
            "max_unmapped_source_paragraphs": 99,
            "max_unmapped_target_paragraphs": 99,
            "raw_unmapped_source_paragraph_count": 99,
            "raw_unmapped_target_paragraph_count": 99,
            "effective_unmapped_source_count": 99,
            "structure_unit_unmapped_source_count": 99,
            "structure_unit_unmapped_target_count": 99,
            "unmapped_source_count_basis": "role_aware_formatting_coverage",
            "unmapped_target_count_basis": "topology_unit",
            "heading_level_drift": 7,
            "text_similarity": 0.10,
            "heading_only_output_detected": False,
        },
        output_artifacts={"output_docx_openable": True, "output_visible_text_chars": 100},
    )
    by_name = {check["name"]: check for check in checks}
    failed = _rollup_failed_checks(checks)

    # Coverage advisory did NOT blind the genuine gates.
    assert by_name["text_similarity_threshold"]["passed"] is False
    assert "text_similarity_threshold" in failed
    assert by_name["heading_level_drift_threshold"]["passed"] is False
    assert "heading_level_drift_threshold" in failed

    # Coverage axes, even wildly exceeding threshold, are NOT gated.
    assert by_name["unmapped_source_threshold"]["exceeds_threshold"] is True
    assert by_name["unmapped_target_threshold"]["exceeds_threshold"] is True
    assert "unmapped_source_threshold" not in failed
    assert "unmapped_target_threshold" not in failed
