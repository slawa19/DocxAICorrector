import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import docxaicorrector.processing.processing_runtime as processing_runtime
import docxaicorrector.validation.profiles as validation_profiles
import docxaicorrector.validation.structural as real_document_validation_structural
from docxaicorrector.core import config as core_config
from docxaicorrector.core.config import describe_provider_availability, load_app_config
from docxaicorrector.validation.structural import (
    evaluate_extraction_profile,
    evaluate_structural_preparation_diagnostic,
    run_structural_passthrough_validation,
)

from docxaicorrector.core.models import (
    DocumentBlock,
    LayoutArtifactCleanupReport,
    ParagraphBoundaryNormalizationReport,
    ParagraphUnit,
    RelationNormalizationReport,
)
from docxaicorrector.generation._generation import ensure_pandoc_available

REGISTRY = validation_profiles.load_validation_registry()
STRUCTURAL_RUN_PROFILE = REGISTRY.get_run_profile("ui-parity-translate-benchmark-advisory")
TASKS_PATH = Path(".vscode/tasks.json")
WORKFLOW_DOC_PATH = Path("docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md")
MAINTENANCE_GUIDE_PATH = Path("docs/testing/UNIVERSAL_TEST_SYSTEM_MAINTENANCE_GUIDE_2026-03-21.md")
REQUIRE_REAL_DOCUMENT_CAPABILITIES_ENV = "DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES"

pytestmark = pytest.mark.system_deps


def _cleanup_report() -> LayoutArtifactCleanupReport:
    return LayoutArtifactCleanupReport(0, 0, 0, 0, 0, 0, cleanup_applied=True)


def _resolve_structural_run_profile(document_profile):
    run_profile_id = getattr(document_profile, "structural_run_profile", None) or STRUCTURAL_RUN_PROFILE.id
    return REGISTRY.get_run_profile(run_profile_id)


def _load_vscode_task_labels() -> set[str]:
    payload = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    return {str(task["label"]) for task in payload["tasks"]}


def _extract_backtick_values(text: str) -> set[str]:
    return {match.group(1) for match in re.finditer(r"`([^`]+)`", text)}


def _load_json_payload(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _require_or_skip_real_document_capability(message: str) -> None:
    if str(os.environ.get(REQUIRE_REAL_DOCUMENT_CAPABILITIES_ENV, "")).strip() == "1":
        pytest.fail(message)
    pytest.skip(message)


def _skip_if_missing_real_document_source(source_path: Path) -> None:
    if source_path.exists():
        return
    _require_or_skip_real_document_capability(f"missing real-document source: {source_path}")


def test_registry_documents_declare_required_core_fields_and_allowed_source_locations() -> None:
    run_profile_ids = {profile.id for profile in REGISTRY.run_profiles}

    for document_profile in REGISTRY.documents:
        assert document_profile.id
        assert document_profile.source_path
        assert document_profile.artifact_prefix
        assert document_profile.output_basename
        assert document_profile.default_run_profile in run_profile_ids
        assert document_profile.tags
        assert document_profile.provenance

        relative_source_path = Path(document_profile.source_path)
        assert relative_source_path.parts[:2] == ("tests", "sources")
        assert document_profile.resolved_source_path().is_relative_to(Path.cwd())


def test_maintenance_guide_no_longer_requires_removed_expected_acceptance_policy_field() -> None:
    maintenance_guide_text = MAINTENANCE_GUIDE_PATH.read_text(encoding="utf-8")

    assert "expected_acceptance_policy" not in maintenance_guide_text


def test_require_or_skip_real_document_capability_skips_by_default() -> None:
    with pytest.raises(pytest.skip.Exception, match="capability missing"):
        _require_or_skip_real_document_capability("capability missing")


def test_require_or_skip_real_document_capability_fails_when_capabilities_are_required(monkeypatch) -> None:
    monkeypatch.setenv(REQUIRE_REAL_DOCUMENT_CAPABILITIES_ENV, "1")

    with pytest.raises(pytest.fail.Exception, match="capability missing"):
        _require_or_skip_real_document_capability("capability missing")


def test_skip_if_missing_real_document_source_uses_controlled_skip_reason(tmp_path) -> None:
    missing_source = tmp_path / "missing.pdf"

    with pytest.raises(pytest.skip.Exception, match=r"missing real-document source"):
        _skip_if_missing_real_document_source(missing_source)


def test_skip_if_missing_real_document_source_fails_when_capabilities_are_required(monkeypatch, tmp_path) -> None:
    missing_source = tmp_path / "missing.pdf"
    monkeypatch.setenv(REQUIRE_REAL_DOCUMENT_CAPABILITIES_ENV, "1")

    with pytest.raises(pytest.fail.Exception, match=r"missing real-document source"):
        _skip_if_missing_real_document_source(missing_source)


def test_build_validation_processing_service_uses_real_client_factories(monkeypatch) -> None:
    captured = {}

    monkeypatch.setattr(
        real_document_validation_structural,
        "clone_processing_service",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )

    sentinel_get_client = object()
    sentinel_get_provider_client = object()
    sentinel_get_client_for_model_selector = object()
    sentinel_resolve_model_selector = object()

    monkeypatch.setattr(real_document_validation_structural, "get_client", sentinel_get_client)
    monkeypatch.setattr(real_document_validation_structural, "get_provider_client", sentinel_get_provider_client)
    monkeypatch.setattr(real_document_validation_structural, "get_client_for_model_selector", sentinel_get_client_for_model_selector)
    monkeypatch.setattr(real_document_validation_structural, "resolve_model_selector", sentinel_resolve_model_selector)

    real_document_validation_structural._build_validation_processing_service([])

    assert captured["kwargs"]["get_client_fn"] is sentinel_get_client
    assert captured["kwargs"]["get_provider_client_fn"] is sentinel_get_provider_client
    assert captured["kwargs"]["get_client_for_model_selector_fn"] is sentinel_get_client_for_model_selector
    assert captured["kwargs"]["resolve_model_selector_fn"] is sentinel_resolve_model_selector


def test_evaluate_structural_preparation_diagnostic_returns_snapshot_summary(monkeypatch) -> None:
    document_profile = SimpleNamespace(id="stub-structural-profile")
    run_profile = SimpleNamespace(id="ui-parity-pdf-structural-recovery")

    monkeypatch.setattr(
        real_document_validation_structural,
        "run_structural_passthrough_validation",
        lambda document_profile, run_profile: {
            "validation_tier": "structural",
            "validation_execution_mode": "passthrough",
            "passed": False,
            "failed_checks": ["preparation_quality_gate_blocked"],
            "metrics": {"preparation_error": "blocked by quality gate"},
            "preparation_diagnostic_snapshot": {"readiness_status": "blocked_unsafe_best_effort_only"},
        },
    )

    result = evaluate_structural_preparation_diagnostic(cast(Any, document_profile), cast(Any, run_profile))

    assert result == {
        "document_profile_id": "stub-structural-profile",
        "run_profile_id": "ui-parity-pdf-structural-recovery",
        "validation_tier": "structural",
        "validation_execution_mode": "passthrough",
        "passed": False,
        "failed_checks": ["preparation_quality_gate_blocked"],
        "preparation_error": "blocked by quality gate",
        "preparation_diagnostic_snapshot": {"readiness_status": "blocked_unsafe_best_effort_only"},
    }


def test_build_structural_metrics_uses_flagged_layout_cleanup_counts_for_signal_mode() -> None:
    metrics = real_document_validation_structural._build_structural_metrics(
        paragraphs=[ParagraphUnit(text="Body", role="body", structural_role="body")],
        image_assets=[],
        cleanup_report=LayoutArtifactCleanupReport(
            original_paragraph_count=3,
            cleaned_paragraph_count=3,
            removed_paragraph_count=0,
            removed_page_number_count=0,
            removed_repeated_artifact_count=0,
            removed_empty_or_whitespace_count=0,
            cleanup_applied=True,
            cleanup_mode="flag",
            flagged_page_number_count=2,
            flagged_repeated_artifact_count=1,
            flagged_empty_or_whitespace_count=0,
        ),
    )

    assert metrics["layout_cleanup_removed_count"] == 3
    assert metrics["layout_cleanup_page_number_count"] == 2
    assert metrics["layout_cleanup_repeated_artifact_count"] == 1
    assert metrics["layout_cleanup_empty_or_whitespace_count"] == 0


def _skip_if_legacy_doc_conversion_unavailable(source_path: Path) -> None:
    if source_path.suffix.lower() != ".doc":
        return
    if processing_runtime.legacy_doc_conversion_available():
        return
    _require_or_skip_real_document_capability(
        f"legacy DOC auto-conversion unavailable in current runtime: {source_path}"
    )


def _iter_structural_passthrough_required_selectors(run_profile) -> tuple[str, ...]:
    app_config = load_app_config()
    runtime_resolution = validation_profiles.resolve_runtime_resolution(app_config, run_profile)
    selectors: list[str] = []

    effective_model = str(runtime_resolution.effective.model or "").strip()
    if effective_model:
        selectors.append(effective_model)

    return tuple(dict.fromkeys(selectors))


def _skip_if_structural_passthrough_runtime_unavailable(run_profile) -> None:
    try:
        ensure_pandoc_available()
    except RuntimeError as exc:
        _require_or_skip_real_document_capability(
            f"structural passthrough runtime unavailable: {exc}"
        )

    app_config = load_app_config()
    if str(__import__("os").environ.get(REQUIRE_REAL_DOCUMENT_CAPABILITIES_ENV, "")).strip() == "1":
        from docxaicorrector.core.config import load_project_dotenv
        from docxaicorrector.core.constants import ENV_PATH

        core_config.ENV_PATH = ENV_PATH
        load_project_dotenv()
    for selector in _iter_structural_passthrough_required_selectors(run_profile):
        availability = describe_provider_availability(selector, app_config=app_config)
        if availability.error_message:
            _require_or_skip_real_document_capability(
                f"structural passthrough runtime unavailable: {availability.error_message}"
            )


def test_skip_if_legacy_doc_conversion_unavailable_uses_controlled_skip_reason(monkeypatch) -> None:
    monkeypatch.setattr(processing_runtime, "legacy_doc_conversion_available", lambda: False)

    with pytest.raises(pytest.skip.Exception, match=r"legacy DOC auto-conversion unavailable in current runtime"):
        _skip_if_legacy_doc_conversion_unavailable(Path("tests/sources/sample.doc"))


@pytest.mark.parametrize("document_profile", REGISTRY.documents, ids=[profile.id for profile in REGISTRY.documents])
def test_corpus_extraction(document_profile) -> None:
    source_path = document_profile.resolved_source_path()
    _skip_if_missing_real_document_source(source_path)
    _skip_if_legacy_doc_conversion_unavailable(source_path)

    result = cast(dict[str, Any], evaluate_extraction_profile(document_profile))

    assert result["validation_tier"] == "extraction"
    assert result["document_profile_id"] == document_profile.id
    assert result["passed"] is True, json.dumps(result, ensure_ascii=False, indent=2)


@pytest.mark.parametrize("document_profile", REGISTRY.documents, ids=[profile.id for profile in REGISTRY.documents])
def test_corpus_structural_passthrough(document_profile) -> None:
    source_path = document_profile.resolved_source_path()
    _skip_if_missing_real_document_source(source_path)
    _skip_if_legacy_doc_conversion_unavailable(source_path)
    run_profile = _resolve_structural_run_profile(document_profile)
    _skip_if_structural_passthrough_runtime_unavailable(run_profile)

    result = cast(dict[str, Any], run_structural_passthrough_validation(document_profile, run_profile))

    assert result["validation_tier"] == "structural"
    assert result["validation_execution_mode"] == "passthrough"
    assert result["run_profile_id"] == run_profile.id
    expected_image_mode = run_profile.image_mode or result["runtime_config"]["ui_defaults"]["image_mode"]
    assert result["runtime_config"]["effective"]["image_mode"] == expected_image_mode
    assert "source_file" not in result
    assert "runtime_configuration" not in result
    expected_result = getattr(document_profile, "structural_expected_result", "pass")
    expected_failed_checks = list(getattr(document_profile, "structural_expected_failed_checks", ()))
    optional_failed_checks = set(getattr(document_profile, "structural_optional_failed_checks", ()))
    if expected_result == "fail":
        assert result["passed"] is False, json.dumps(result, ensure_ascii=False, indent=2)
        actual_failed_checks = set(result["failed_checks"])
        expected_failed_check_set = set(expected_failed_checks)
        assert expected_failed_check_set.issubset(actual_failed_checks), json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
        assert actual_failed_checks.issubset(expected_failed_check_set | optional_failed_checks), json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
        assert actual_failed_checks == expected_failed_check_set, json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    else:
        assert result["passed"] is True, json.dumps(result, ensure_ascii=False, indent=2)


def test_evaluate_extraction_profile_reports_merged_boundary_metrics(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "sample.docx"
    source_path.write_bytes(b"PK\x03\x04source")

    document_profile = SimpleNamespace(
        id="sample-doc",
        resolved_source_path=lambda project_root=None: source_path,
        min_paragraphs=1,
        min_merged_groups=1,
        min_merged_raw_paragraphs=2,
        has_headings=False,
        min_headings=0,
        has_numbered_lists=False,
        min_numbered_items=0,
        has_images=False,
        min_images=0,
        has_tables=False,
        min_tables=0,
        max_formatting_diagnostics=0,
        max_unmapped_source_paragraphs=0,
        max_unmapped_target_paragraphs=0,
        max_heading_level_drift=0,
        min_text_similarity=1.0,
        require_numbered_lists_preserved=False,
        require_nonempty_output=True,
        forbid_heading_only_collapse=False,
    )

    monkeypatch.setattr(real_document_validation_structural, "PROJECT_ROOT", Path(project_root))
    monkeypatch.setattr(
        real_document_validation_structural.processing_runtime,
        "normalize_uploaded_document",
        lambda **kwargs: SimpleNamespace(content_bytes=b"PK\x03\x04normalized"),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: (
            [SimpleNamespace(role="body"), SimpleNamespace(role="body")],
            [],
            ParagraphBoundaryNormalizationReport(
                total_raw_paragraphs=3,
                total_logical_paragraphs=2,
                merged_group_count=1,
                merged_raw_paragraph_count=2,
            ),
            [],
            RelationNormalizationReport(
                total_relations=1,
                relation_counts={"toc_region": 1},
                rejected_candidate_count=0,
            ),
            _cleanup_report(),
        ),
    )

    result = cast(dict[str, Any], evaluate_extraction_profile(cast(Any, document_profile)))

    assert result["passed"] is True
    assert result["metrics"]["merged_group_count"] == 1
    assert result["metrics"]["merged_raw_paragraph_count"] == 2
    assert result["metrics"]["raw_paragraph_count"] == 3
    assert result["metrics"]["high_confidence_merge_count"] == 0
    assert result["metrics"]["medium_accepted_merge_count"] == 0
    assert result["metrics"]["medium_rejected_candidate_count"] == 0
    assert "merged_group_count_minimum" in {check["name"] for check in result["checks"]}


def test_build_structural_checks_enforces_pdf_translation_quality_specific_constraints() -> None:
    document_profile = SimpleNamespace(
        max_formatting_diagnostics=5,
        max_unmapped_source_paragraphs=0,
        max_unmapped_target_paragraphs=3,
        max_heading_level_drift=1,
        min_text_similarity=0.95,
        require_numbered_lists_preserved=False,
        require_nonempty_output=True,
        forbid_heading_only_collapse=True,
        require_toc_detected=True,
        require_pdf_conversion=True,
        require_no_bullet_headings=True,
        require_no_toc_body_concat=True,
        require_translation_domain="theology",
    )
    metrics = {
        "formatting_diagnostics_count": 0,
        "max_unmapped_source_paragraphs": 0,
        "max_unmapped_target_paragraphs": 0,
        "heading_level_drift": 0,
        "text_similarity": 0.99,
        "heading_only_output_detected": False,
        "source_toc_detected": True,
        "output_toc_detected": False,
        "structure_repair_bounded_toc_regions": 1,
        "source_toc_region_count": 1,
        "effective_source_toc_region_count": 0,
        "require_pdf_conversion_satisfied": True,
        "bullet_heading_count": 0,
        "false_fragment_heading_count": 0,
        "scripture_reference_heading_count": 0,
        "suspicious_heading_repetition_count": 0,
        "residual_bullet_glyph_count": 0,
        "list_fragment_regression_count": 0,
        "theology_style_deterministic_issue_count": 0,
        "toc_body_concat_detected": False,
        "structure_repair_toc_body_boundary_repairs": 1,
        "runtime_translation_domain": "theology",
    }
    output_artifacts = {"output_docx_openable": True, "output_visible_text_chars": 100}

    checks = real_document_validation_structural._build_structural_checks(
        document_profile=cast(Any, document_profile),
        result="succeeded",
        metrics=metrics,
        output_artifacts=output_artifacts,
    )

    by_name = {check["name"]: check for check in checks}
    assert by_name["toc_detected_required"]["passed"] is True
    assert by_name["pdf_conversion_required"]["passed"] is True
    assert by_name["no_bullet_headings_required"]["passed"] is True
    assert by_name["no_toc_body_concat_required"]["passed"] is True
    assert by_name["translation_domain_required"]["passed"] is True


def test_build_structural_checks_rejects_effectively_infinite_acceptance_thresholds() -> None:
    document_profile = SimpleNamespace(
        max_formatting_diagnostics=999999,
        max_unmapped_source_paragraphs=999999,
        max_unmapped_target_paragraphs=999999,
        max_heading_level_drift=999999,
        min_text_similarity=0.95,
        require_numbered_lists_preserved=False,
        require_nonempty_output=True,
        forbid_heading_only_collapse=False,
        require_toc_detected=False,
        require_pdf_conversion=False,
        require_no_bullet_headings=False,
        require_no_toc_body_concat=False,
        require_translation_domain=None,
    )
    metrics = {
        "formatting_diagnostics_count": 0,
        "max_unmapped_source_paragraphs": 0,
        "max_unmapped_target_paragraphs": 0,
        "heading_level_drift": 0,
        "text_similarity": 0.99,
        "heading_only_output_detected": False,
    }
    output_artifacts = {"output_docx_openable": True, "output_visible_text_chars": 100}

    checks = real_document_validation_structural._build_structural_checks(
        document_profile=cast(Any, document_profile),
        result="succeeded",
        metrics=metrics,
        output_artifacts=output_artifacts,
    )

    by_name = {check["name"]: check for check in checks}
    assert by_name["max_unmapped_source_paragraphs_not_sentinel"]["passed"] is False
    assert by_name["max_unmapped_target_paragraphs_not_sentinel"]["passed"] is False
    assert by_name["max_formatting_diagnostics_not_sentinel"]["passed"] is False
    failed_checks = [check["name"] for check in checks if not bool(check["passed"])]
    assert "max_unmapped_source_paragraphs_not_sentinel" in failed_checks
    assert "max_unmapped_target_paragraphs_not_sentinel" in failed_checks


def test_build_structural_checks_requires_bounded_toc_and_source_boundary_repair_for_pdf_constraints() -> None:
    document_profile = SimpleNamespace(
        max_formatting_diagnostics=5,
        max_unmapped_source_paragraphs=0,
        max_unmapped_target_paragraphs=3,
        max_heading_level_drift=1,
        min_text_similarity=0.95,
        require_numbered_lists_preserved=False,
        require_nonempty_output=False,
        forbid_heading_only_collapse=False,
        require_toc_detected=True,
        require_pdf_conversion=False,
        require_no_bullet_headings=False,
        require_no_toc_body_concat=True,
        require_translation_domain=None,
    )
    metrics = {
        "formatting_diagnostics_count": 0,
        "max_unmapped_source_paragraphs": 0,
        "max_unmapped_target_paragraphs": 0,
        "heading_level_drift": 0,
        "text_similarity": 0.99,
        "heading_only_output_detected": False,
        "source_toc_detected": False,
        "output_toc_detected": False,
        "structure_repair_bounded_toc_regions": 0,
        "source_toc_region_count": 0,
        "effective_source_toc_region_count": 0,
        "toc_body_concat_detected": False,
        "structure_repair_toc_body_boundary_repairs": 0,
    }
    output_artifacts = {"output_docx_openable": True, "output_visible_text_chars": 100}

    checks = real_document_validation_structural._build_structural_checks(
        document_profile=cast(Any, document_profile),
        result="succeeded",
        metrics=metrics,
        output_artifacts=output_artifacts,
    )

    by_name = {check["name"]: check for check in checks}
    assert by_name["toc_detected_required"]["passed"] is False
    assert by_name["no_toc_body_concat_required"]["passed"] is False


def test_build_structural_checks_accepts_ai_bounded_toc_region_as_boundary_repair() -> None:
    document_profile = SimpleNamespace(
        max_formatting_diagnostics=5,
        max_unmapped_source_paragraphs=0,
        max_unmapped_target_paragraphs=3,
        max_heading_level_drift=1,
        min_text_similarity=0.95,
        require_numbered_lists_preserved=False,
        require_nonempty_output=False,
        forbid_heading_only_collapse=False,
        require_toc_detected=True,
        require_pdf_conversion=False,
        require_no_bullet_headings=False,
        require_no_toc_body_concat=True,
        require_translation_domain=None,
    )
    metrics = {
        "formatting_diagnostics_count": 0,
        "max_unmapped_source_paragraphs": 0,
        "max_unmapped_target_paragraphs": 0,
        "heading_level_drift": 0,
        "text_similarity": 0.99,
        "heading_only_output_detected": False,
        "source_toc_detected": True,
        "output_toc_detected": False,
        "structure_repair_bounded_toc_regions": 0,
        "source_toc_region_count": 0,
        "effective_source_toc_region_count": 1,
        "toc_body_concat_detected": False,
        "structure_repair_toc_body_boundary_repairs": 0,
    }
    output_artifacts = {"output_docx_openable": True, "output_visible_text_chars": 100}

    checks = real_document_validation_structural._build_structural_checks(
        document_profile=cast(Any, document_profile),
        result="succeeded",
        metrics=metrics,
        output_artifacts=output_artifacts,
    )

    by_name = {check["name"]: check for check in checks}
    assert by_name["toc_detected_required"]["passed"] is True
    assert by_name["no_toc_body_concat_required"]["passed"] is True
    assert by_name["no_toc_body_concat_required"]["effective_source_toc_region_count"] == 1


def test_apply_prepared_metric_fields_uses_explicit_unknown_when_statuses_missing() -> None:
    metrics = {}
    prepared = SimpleNamespace(
        quality_gate_status="",
        quality_gate_reasons=(),
        structure_validation_report=SimpleNamespace(readiness_status="", readiness_reasons=()),
    )

    real_document_validation_structural._apply_prepared_metric_fields(metrics, prepared)

    assert metrics["quality_gate_status"] == "unknown"
    assert metrics["readiness_status"] == "unknown"


def test_build_structural_checks_prefers_topology_unit_unmapped_counts_when_available() -> None:
    document_profile = SimpleNamespace(
        max_formatting_diagnostics=5,
        max_unmapped_source_paragraphs=1,
        max_unmapped_target_paragraphs=1,
        max_heading_level_drift=1,
        min_text_similarity=0.95,
        require_numbered_lists_preserved=False,
        require_nonempty_output=False,
        forbid_heading_only_collapse=False,
        require_toc_detected=False,
        require_pdf_conversion=False,
        require_no_bullet_headings=False,
        require_no_toc_body_concat=False,
        require_translation_domain=None,
    )
    metrics = {
        "formatting_diagnostics_count": 0,
        "max_unmapped_source_paragraphs": 2,
        "max_unmapped_target_paragraphs": 2,
        "structure_unit_unmapped_source_count": 1,
        "structure_unit_unmapped_target_count": 1,
        "unit_unmapped_source_gate_source": "topology_unit",
        "unit_unmapped_target_gate_source": "topology_unit",
        "heading_level_drift": 0,
        "text_similarity": 0.99,
        "heading_only_output_detected": False,
    }

    checks = real_document_validation_structural._build_structural_checks(
        document_profile=cast(Any, document_profile),
        result="succeeded",
        metrics=metrics,
        output_artifacts={"output_docx_openable": True, "output_visible_text_chars": 100},
    )

    by_name = {check["name"]: check for check in checks}
    assert by_name["unmapped_source_threshold"]["passed"] is True
    assert by_name["unmapped_source_threshold"]["actual"] == 1
    assert by_name["unmapped_source_threshold"]["paragraph_actual"] == 2
    assert by_name["unmapped_source_threshold"]["unmapped_gate_source"] == "topology_unit"
    assert by_name["unmapped_target_threshold"]["passed"] is True
    assert by_name["unmapped_target_threshold"]["actual"] == 1
    assert by_name["unmapped_target_threshold"]["paragraph_actual"] == 2
    assert by_name["unmapped_target_threshold"]["unmapped_gate_source"] == "topology_unit"


def test_structural_passthrough_failure_derives_snapshot_block_status_from_preparation_error(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.4 sample")

    document_profile = SimpleNamespace(id="stub-structural-profile", resolved_source_path=lambda project_root=None: source_path)
    run_profile = SimpleNamespace(id="ui-parity-pdf-structural-recovery", image_mode="safe")

    class _StructureRepairReport:
        repaired_bullet_items = 0
        repaired_numbered_items = 0
        bounded_toc_regions = 1
        toc_body_boundary_repairs = 1
        heading_candidates_from_toc = 0
        remaining_isolated_marker_count = 0

    def _resolution_payload(**values):
        return SimpleNamespace(**values, to_dict=lambda: dict(values))

    monkeypatch.setattr(real_document_validation_structural, "PROJECT_ROOT", Path(project_root))
    monkeypatch.setattr(real_document_validation_structural, "load_app_config", lambda: object())
    monkeypatch.setattr(
        real_document_validation_structural,
        "resolve_runtime_resolution",
        lambda app_config, run_profile: SimpleNamespace(
            effective=_resolution_payload(
                chunk_size=6000,
                image_mode="safe",
                keep_all_image_variants=False,
                model="gpt-5.4",
                max_retries=1,
                translation_domain="theology",
            ),
            ui_defaults=_resolution_payload(image_mode="safe"),
        ),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "apply_runtime_resolution_to_app_config",
        lambda app_config, runtime_resolution: {"translation_domain_default": "theology"},
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "build_validation_runtime_config",
        lambda runtime_resolution: {
            "effective": runtime_resolution.effective.to_dict(),
            "ui_defaults": runtime_resolution.ui_defaults.to_dict(),
        },
    )
    monkeypatch.setattr(
        real_document_validation_structural.processing_runtime,
        "normalize_uploaded_document",
        lambda **kwargs: SimpleNamespace(content_bytes=b"PK\x03\x04normalized"),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: (
            [
                ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0),
                ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", source_index=1),
                ParagraphUnit(text="Introduction", role="heading", structural_role="body", heading_level=1, source_index=2),
            ],
            [],
            ParagraphBoundaryNormalizationReport(0, 0, 0, 0),
            [],
            RelationNormalizationReport(1, {"toc_region": 1}, 0),
            _cleanup_report(),
            _StructureRepairReport(),
        ),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "build_semantic_blocks",
        lambda paragraphs, max_chars, relations=None: [DocumentBlock(paragraphs=list(paragraphs))],
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_validation_processing_service",
        lambda event_log: SimpleNamespace(
            run_prepared_background_document=lambda **kwargs: (_ for _ in ()).throw(
                ValueError("Подготовка заблокирована quality gate: документ требует structural repair перед обработкой.")
            )
        ),
    )

    result = cast(dict[str, Any], run_structural_passthrough_validation(cast(Any, document_profile), cast(Any, run_profile)))

    snapshot = result["preparation_diagnostic_snapshot"]
    assert snapshot["quality_gate_status"] == "blocked"
    assert snapshot["quality_gate_reasons"] == ["structural_repair_required_before_processing"]
    assert snapshot["readiness_status"] == "blocked_needs_structure_repair"
    assert snapshot["readiness_reasons"] == ["structural_repair_required_before_processing"]


def test_structural_passthrough_failure_derives_detailed_snapshot_reasons_from_preparation_error(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.4 sample")

    document_profile = SimpleNamespace(id="stub-structural-profile", resolved_source_path=lambda project_root=None: source_path)
    run_profile = SimpleNamespace(id="ui-parity-pdf-structural-recovery", image_mode="safe")

    class _StructureRepairReport:
        repaired_bullet_items = 0
        repaired_numbered_items = 0
        bounded_toc_regions = 1
        toc_body_boundary_repairs = 1
        heading_candidates_from_toc = 0
        remaining_isolated_marker_count = 0

    def _resolution_payload(**values):
        return SimpleNamespace(**values, to_dict=lambda: dict(values))

    monkeypatch.setattr(real_document_validation_structural, "PROJECT_ROOT", Path(project_root))
    monkeypatch.setattr(real_document_validation_structural, "load_app_config", lambda: object())
    monkeypatch.setattr(
        real_document_validation_structural,
        "resolve_runtime_resolution",
        lambda app_config, run_profile: SimpleNamespace(
            effective=_resolution_payload(
                chunk_size=6000,
                image_mode="safe",
                keep_all_image_variants=False,
                model="gpt-5.4",
                max_retries=1,
                translation_domain="theology",
            ),
            ui_defaults=_resolution_payload(image_mode="safe"),
        ),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "apply_runtime_resolution_to_app_config",
        lambda app_config, runtime_resolution: {"translation_domain_default": "theology"},
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "build_validation_runtime_config",
        lambda runtime_resolution: {
            "effective": runtime_resolution.effective.to_dict(),
            "ui_defaults": runtime_resolution.ui_defaults.to_dict(),
        },
    )
    monkeypatch.setattr(
        real_document_validation_structural.processing_runtime,
        "normalize_uploaded_document",
        lambda **kwargs: SimpleNamespace(content_bytes=b"PK\x03\x04normalized"),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: (
            [
                ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0),
                ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", source_index=1),
                ParagraphUnit(text="Introduction", role="heading", structural_role="body", heading_level=1, source_index=2),
            ],
            [],
            ParagraphBoundaryNormalizationReport(0, 0, 0, 0),
            [],
            RelationNormalizationReport(1, {"toc_region": 1}, 0),
            _cleanup_report(),
            _StructureRepairReport(),
        ),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "build_semantic_blocks",
        lambda paragraphs, max_chars, relations=None: [DocumentBlock(paragraphs=list(paragraphs))],
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_validation_processing_service",
        lambda event_log: SimpleNamespace(
            run_prepared_background_document=lambda **kwargs: (_ for _ in ()).throw(
                ValueError(
                    "Подготовка заблокирована quality gate: документ требует structural repair перед обработкой. "
                    "Причины: обнаружен TOC-подобный фрагмент без надёжно выделенной границы, AI-распознавание структуры не внесло изменений для документа с высоким структурным риском"
                )
            )
        ),
    )

    result = cast(dict[str, Any], run_structural_passthrough_validation(cast(Any, document_profile), cast(Any, run_profile)))

    snapshot = result["preparation_diagnostic_snapshot"]
    assert snapshot["quality_gate_status"] == "blocked"
    assert snapshot["quality_gate_reasons"] == [
        "toc_like_sequence_without_bounded_region",
        "structure_recognition_noop_on_high_risk",
    ]
    assert snapshot["readiness_status"] == "blocked_unsafe_best_effort_only"
    assert snapshot["readiness_reasons"] == [
        "toc_like_sequence_without_bounded_region",
        "structure_recognition_noop_on_high_risk",
    ]
    assert snapshot["structure_ai_attempted"] is True
    assert snapshot["ai_classified_count"] == 0
    assert snapshot["ai_heading_count"] == 0


def test_markdown_quality_metrics_keep_false_fragment_and_list_fragment_fallback_raw_only() -> None:
    metrics = cast(
        dict[str, Any],
        real_document_validation_structural._build_markdown_quality_metrics(
            latest_markdown=(
                "Наблюдайте внимательно.\n\n"
                "(Матфея 24:36)\n\n"
                "Это продолжение абзаца.\n\n"
                "Поразительно, но все петли следуют одной и той же схеме.\n\n"
                "1. Духовные существа восстают против Бога."
            ),
            raw_markdown=(
                "Наблюдайте внимательно.\n\n"
                "(Матфея 24:36)\n\n"
                "Это продолжение абзаца.\n\n"
                "Поразительно, но все петли следуют одной и той же схеме.\n\n"
                "1. Духовные существа восстают против Бога."
            ),
            raw_structural_markdown=(
                "Наблюдайте внимательно.\n\n"
                "## (Матфея 24:36)\n\n"
                "Это продолжение абзаца.\n\n"
                "Поразительно, но все петли следуют одной и той же схеме: 1.\n"
                "Духовные существа восстают против Бога."
            ),
            translation_domain="general",
        ),
    )

    assert metrics["false_fragment_heading_count"] == 1
    assert metrics["raw_false_fragment_heading_count"] == 1
    assert metrics["bullet_heading_count"] == 0
    assert metrics["bullet_heading_gate_source"] == "legacy_markdown"
    assert metrics["bullet_heading_classification"] == "markdown_gate"
    assert metrics["raw_bullet_heading_count"] == 0
    assert metrics["scripture_reference_heading_count"] == 1
    assert metrics["list_fragment_regression_count"] == 1
    assert metrics["raw_list_fragment_regression_count"] == 1
    assert metrics["mixed_script_term_gate_source"] == "legacy_markdown"
    assert metrics["mixed_script_term_classification"] == "non_structural_hygiene"
    assert metrics["raw_mixed_script_term_count"] == 0
    assert metrics["theology_style_deterministic_issue_source"] == "legacy_markdown"
    assert metrics["theology_style_deterministic_issue_classification"] == "domain_style_advisory"
    assert metrics["raw_theology_style_deterministic_issue_count"] == 0


def test_markdown_quality_metrics_do_not_fallback_false_fragment_and_list_fragment_to_latest_markdown() -> None:
    metrics = cast(
        dict[str, Any],
        real_document_validation_structural._build_markdown_quality_metrics(
            latest_markdown=(
                "Наблюдайте внимательно.\n\n"
                "## (Матфея 24:36)\n\n"
                "Это продолжение абзаца.\n\n"
                "Поразительно, но все петли следуют одной и той же схеме: 1.\n"
                "Духовные существа восстают против Бога."
            ),
            raw_markdown=(
                "Наблюдайте внимательно.\n\n"
                "## (Матфея 24:36)\n\n"
                "Это продолжение абзаца.\n\n"
                "Поразительно, но все петли следуют одной и той же схеме: 1.\n"
                "Духовные существа восстают против Бога."
            ),
            raw_structural_markdown="",
            translation_domain="general",
        ),
    )

    assert metrics["false_fragment_heading_count"] == 0
    assert metrics["raw_false_fragment_heading_count"] == 0
    assert metrics["bullet_heading_count"] == 0
    assert metrics["bullet_heading_gate_source"] == "legacy_markdown"
    assert metrics["bullet_heading_classification"] == "markdown_gate"
    assert metrics["raw_bullet_heading_count"] == 0
    assert metrics["scripture_reference_heading_count"] == 0
    assert metrics["list_fragment_regression_count"] == 0
    assert metrics["mixed_script_term_gate_source"] == "legacy_markdown"
    assert metrics["mixed_script_term_classification"] == "non_structural_hygiene"
    assert metrics["raw_mixed_script_term_count"] == 0
    assert metrics["theology_style_deterministic_issue_source"] == "legacy_markdown"
    assert metrics["theology_style_deterministic_issue_classification"] == "domain_style_advisory"
    assert metrics["raw_theology_style_deterministic_issue_count"] == 0
    assert metrics["raw_list_fragment_regression_count"] == 0


def test_markdown_quality_metrics_keep_residual_bullet_raw_observability_separate_from_latest_markdown() -> None:
    metrics = cast(
        dict[str, Any],
        real_document_validation_structural._build_markdown_quality_metrics(
            latest_markdown=(
                "- В 27 начальных школах Чикаго с самым низким рейтингом пяти- и\n\n"
                "шестиклассники зарабатывали тайм-кредиты."
            ),
            raw_markdown=(
                "• В 27 начальных школах Чикаго с самым низким рейтингом пяти- и\n\n"
                "шестиклассники зарабатывали тайм-кредиты."
            ),
            raw_structural_markdown=(
                "• В 27 начальных школах Чикаго с самым низким рейтингом пяти- и\n\n"
                "шестиклассники зарабатывали тайм-кредиты."
            ),
            translation_domain="general",
        ),
    )

    assert metrics["residual_bullet_glyph_count"] == 0
    assert metrics["residual_bullet_glyph_gate_source"] == "legacy_markdown"
    assert metrics["residual_bullet_glyph_classification"] == "display_hygiene"
    assert metrics["raw_residual_bullet_glyph_count"] == 1
