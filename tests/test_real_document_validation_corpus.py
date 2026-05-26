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
    DocumentMap,
    DocumentMapAnchor,
    DocumentMapTocEntry,
    DocumentMapTocRegion,
    DocumentTopologyOperation,
    DocumentTopologyProjection,
    DocumentBlock,
    LayoutArtifactCleanupReport,
    ParagraphBoundaryNormalizationReport,
    ParagraphUnit,
    RelationNormalizationReport,
    StructuralUnit,
)
from docxaicorrector.generation._generation import ensure_pandoc_available


def _cleanup_report() -> LayoutArtifactCleanupReport:
    return LayoutArtifactCleanupReport(0, 0, 0, 0, 0, 0, cleanup_applied=True)


from docxaicorrector.validation.profiles import load_validation_registry
from docxaicorrector.validation.structural import (
    evaluate_extraction_profile,
    evaluate_structural_preparation_diagnostic,
    run_structural_passthrough_validation,
)

REGISTRY = load_validation_registry()
STRUCTURAL_RUN_PROFILE = REGISTRY.get_run_profile("structural-passthrough-default")
TASKS_PATH = Path(".vscode/tasks.json")
WORKFLOW_DOC_PATH = Path("docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md")
MAINTENANCE_GUIDE_PATH = Path("docs/testing/UNIVERSAL_TEST_SYSTEM_MAINTENANCE_GUIDE_2026-03-21.md")
REQUIRE_REAL_DOCUMENT_CAPABILITIES_ENV = "DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES"
LIETAER_CHAPTER_REGION_STRUCTURAL_DIAGNOSTIC_PATH = Path(
    "tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/structural_diagnostic.json"
)
LIETAER_CHAPTER_REGION_DOCUMENT_MAP_ARTIFACT_PATH = Path(
    "tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/document_map.json"
)
LIETAER_CHAPTER_REGION_TOPOLOGY_ARTIFACT_PATH = Path(
    "tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/document_topology_projection.json"
)

pytestmark = pytest.mark.system_deps


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


def _assert_lietaer_chapter_region_chapter_11_stage1_authority_contract(
    diagnostic_payload: dict[str, Any],
    *,
    document_map_payload: dict[str, Any],
    topology_payload: dict[str, Any],
) -> None:
    snapshot = cast(dict[str, Any], diagnostic_payload["preparation_diagnostic_snapshot"])
    snapshot_projection = cast(dict[str, Any], snapshot["document_topology_projection"])
    snapshot_layout_signals = cast(dict[str, Any], snapshot.get("document_topology_layout_signals"))
    document_map_cache_key = str(document_map_payload.get("cache_key") or "")
    if "document_map" in document_map_payload:
        document_map_payload = cast(dict[str, Any], document_map_payload["document_map"])
    toc_region = cast(dict[str, Any], document_map_payload["toc_region"])
    toc_entries = cast(list[dict[str, Any]], toc_region["entries"])
    outline_entries = cast(list[dict[str, Any]], document_map_payload["outline"])
    topology_operations = cast(list[dict[str, Any]], topology_payload["operations"])
    topology_units = cast(list[dict[str, Any]], topology_payload["projected_units"])
    snapshot_operations = cast(list[dict[str, Any]], snapshot_projection["operations"])
    snapshot_units = cast(list[dict[str, Any]], snapshot_projection["projected_units"])

    assert diagnostic_payload["document_profile_id"] == "lietaer-pdf-chapter-region-core"
    assert diagnostic_payload["run_profile_id"] == "structural-ai-first-default"
    assert diagnostic_payload["validation_tier"] == "structural"
    assert diagnostic_payload["validation_execution_mode"] == "passthrough"
    assert diagnostic_payload["passed"] is True
    assert diagnostic_payload["failed_checks"] == []

    assert snapshot["document_map_present"] is True
    assert snapshot["toc_entry_count"] == 9
    assert snapshot["document_topology_projection_status"] == "built"
    assert snapshot["quality_gate_status"] == "pass"
    assert snapshot["toc_body_concat_gate_source"] == "topology_projection"
    assert snapshot["toc_body_concat_detected"] is False
    assert snapshot["toc_body_concat_markdown_detected"] is True
    assert snapshot["toc_body_concat_structure_detected"] is False
    assert snapshot_layout_signals == {
        "body_baseline_pt": 11.0,
        "tier_count": 5,
        "heading_tier_count": 3,
        "paragraphs_with_font_size_count": 336,
        "heading_ratio": 1.15,
    }

    assert snapshot_projection["cache_key"] == topology_payload["cache_key"]
    assert snapshot_projection["document_map_cache_key"] == document_map_cache_key
    assert topology_payload["document_map_cache_key"] == document_map_cache_key
    assert topology_payload["topology_projection_schema_version"] == 2
    assert snapshot_projection == topology_payload

    chapter_11_toc_entry = [
        entry
        for entry in toc_entries
        if entry["title"] == "Chapter Eleven GOVERNANCE AND WE, THE CITIZENS An Ancient Future?"
    ]
    assert len(chapter_11_toc_entry) == 1, json.dumps(toc_entries, ensure_ascii=False, indent=2)
    assert chapter_11_toc_entry[0]["candidate_body_logical_index"] == 221
    assert chapter_11_toc_entry[0]["confidence"] == "high"

    chapter_11_outline_entry = [
        entry
        for entry in outline_entries
        if entry["title"] == "Chapter Eleven GOVERNANCE AND WE, THE CITIZENS An Ancient Future?"
    ]
    assert len(chapter_11_outline_entry) == 1, json.dumps(outline_entries, ensure_ascii=False, indent=2)
    assert chapter_11_outline_entry[0]["logical_index"] == 221
    assert chapter_11_outline_entry[0]["member_logical_indexes"] == [221, 222, 223, 224]
    assert chapter_11_outline_entry[0]["confidence"] == "high"

    chapter_11_topology_operation = [
        operation
        for operation in topology_operations
        if operation["op"] == "merge_heading_continuation"
        and operation["logical_indexes"] == [221, 222, 223, 224]
    ]
    assert len(chapter_11_topology_operation) == 1, json.dumps(topology_operations, ensure_ascii=False, indent=2)
    assert chapter_11_topology_operation[0]["canonical_text"] == (
        "Chapter Eleven GOVERNANCE AND WE, THE CITIZENS An Ancient Future?"
    )
    assert chapter_11_topology_operation[0]["authority"] == "document_map_outline"
    assert chapter_11_topology_operation[0]["confidence"] == "high"
    assert chapter_11_topology_operation[0]["evidence"] == [
        "outline_entry",
        "adjacent_short_heading_fragments",
        "body_font_baseline_outlier",
    ]

    chapter_11_snapshot_operation = [
        operation
        for operation in snapshot_operations
        if operation["op"] == "merge_heading_continuation"
        and operation["logical_indexes"] == [221, 222, 223, 224]
    ]
    assert len(chapter_11_snapshot_operation) == 1, json.dumps(snapshot_operations, ensure_ascii=False, indent=2)
    assert chapter_11_snapshot_operation[0] == chapter_11_topology_operation[0]

    chapter_11_topology_unit = [
        unit
        for unit in topology_units
        if unit["unit_type"] == "chapter_heading" and unit["logical_indexes"] == [221, 222, 223, 224]
    ]
    assert len(chapter_11_topology_unit) == 1, json.dumps(topology_units, ensure_ascii=False, indent=2)
    assert chapter_11_topology_unit[0]["canonical_text"] == (
        "Chapter Eleven GOVERNANCE AND WE, THE CITIZENS An Ancient Future?"
    )
    assert chapter_11_topology_unit[0]["role"] == "heading"
    assert chapter_11_topology_unit[0]["heading_level"] == 1
    assert chapter_11_topology_unit[0]["authority"] == "document_map_outline"
    assert chapter_11_topology_unit[0]["confidence"] == "high"
    assert chapter_11_topology_unit[0]["evidence"] == [
        "outline_entry",
        "adjacent_short_heading_fragments",
        "body_font_baseline_outlier",
    ]

    chapter_11_snapshot_unit = [
        unit
        for unit in snapshot_units
        if unit["unit_type"] == "chapter_heading" and unit["logical_indexes"] == [221, 222, 223, 224]
    ]
    assert len(chapter_11_snapshot_unit) == 1, json.dumps(snapshot_units, ensure_ascii=False, indent=2)
    assert chapter_11_snapshot_unit[0] == chapter_11_topology_unit[0]

    for logical_indexes, canonical_text in (
        ([10, 11], "Chapter Eight STRATEGIES FOR GOVERNMENTS"),
        ([161, 162], "Chapter Ten TRUTH AND CONSEQUENCES Lessons Learned"),
    ):
        matching_units = [
            unit
            for unit in topology_units
            if unit["unit_type"] == "chapter_heading" and unit["logical_indexes"] == logical_indexes
        ]
        assert len(matching_units) == 1, json.dumps(topology_units, ensure_ascii=False, indent=2)
        assert matching_units[0]["canonical_text"] == canonical_text
        assert matching_units[0]["authority"] == "document_map_outline"
        assert "body_font_baseline_outlier" in matching_units[0]["evidence"]

    split_toc_operations = [
        operation for operation in topology_operations if operation["op"] == "split_compound_toc_entries"
    ]
    assert len(split_toc_operations) == 2, json.dumps(topology_operations, ensure_ascii=False, indent=2)
    assert {tuple(operation["logical_indexes"]) for operation in split_toc_operations} == {(6,), (8,)}
    assert {operation["authority"] for operation in split_toc_operations} <= {
        "document_map_split_hint",
        "document_map_toc",
    }

    split_toc_units = [unit for unit in topology_units if unit["unit_type"] == "toc_entry"]
    assert len(split_toc_units) == 4, json.dumps(topology_units, ensure_ascii=False, indent=2)
    assert {tuple(unit["logical_indexes"]) for unit in split_toc_units} == {(6,), (8,)}
    assert {unit["authority"] for unit in split_toc_units} <= {
        "document_map_split_hint",
        "document_map_toc",
    }
    assert {unit["canonical_text"].lower() for unit in split_toc_units} == {
        "Chapter Eight STRATEGIES FOR GOVERNMENTS".lower(),
        "Strategies for NGOs".lower(),
        "Chapter Ten TRUTH AND CONSEQUENCES Lessons Learned".lower(),
        "Chapter Eleven GOVERNANCE AND WE, THE CITIZENS An Ancient Future?".lower(),
    }

    assert not [unit for unit in topology_units if tuple(unit["logical_indexes"]) == (104, 105)]
    assert not [operation for operation in topology_operations if operation["op"] == "candidate_page_artifact_split"]


def _require_or_skip_real_document_capability(message: str) -> None:
    if str(os.environ.get(REQUIRE_REAL_DOCUMENT_CAPABILITIES_ENV, "")).strip() == "1":
        pytest.fail(message)
    pytest.skip(message)


def _skip_if_missing_real_document_source(source_path: Path) -> None:
    if source_path.exists():
        return
    _require_or_skip_real_document_capability(f"missing real-document source: {source_path}")


def test_registry_includes_end_times_pdf_regression_profile() -> None:
    profile_ids = {profile.id for profile in REGISTRY.documents}

    assert "end-times-pdf-core" in profile_ids


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


def test_registry_structural_profiles_and_tolerance_contracts_are_consistent() -> None:
    run_profiles_by_id = {profile.id: profile for profile in REGISTRY.run_profiles}

    for document_profile in REGISTRY.documents:
        if document_profile.structural_run_profile is not None:
            assert document_profile.structural_run_profile in run_profiles_by_id
        assert document_profile.structural_expected_result in {"pass", "fail"}
        if document_profile.structural_mode == "tolerant":
            assert document_profile.tolerance_reason
        if "benchmark-only" in document_profile.tags:
            expected_benchmark_profile = {
                "lietaer-pdf-full-benchmark": "ui-parity-translate-benchmark-topology-advisory",
            }.get(document_profile.id, "ui-parity-translate-benchmark-advisory")
            assert document_profile.default_run_profile == expected_benchmark_profile


def test_document_profile_detector_threshold_fields_parse_as_optional_and_serialize() -> None:
    profile = validation_profiles._build_document_profile(
        {
            "id": "test-profile",
            "source_path": "tests/sources/sample.docx",
            "output_basename": "sample.out.docx",
            "default_run_profile": "structural-passthrough-default",
            "tags": ["test"],
            "provenance": "unit-test",
            "max_pdf_blank_page_marker_leakage": 1,
            "max_inline_page_furniture_leakage": 2,
            "max_adjacent_h1_without_body": 3,
            "max_heading_body_concat_detected": 4,
            "max_h1_epigraph_attribution_pattern": 5,
        }
    )

    assert profile.max_pdf_blank_page_marker_leakage == 1
    assert profile.max_inline_page_furniture_leakage == 2
    assert profile.max_adjacent_h1_without_body == 3
    assert profile.max_heading_body_concat_detected == 4
    assert profile.max_h1_epigraph_attribution_pattern == 5


def test_document_profile_detector_threshold_fields_default_to_none() -> None:
    profile = validation_profiles._build_document_profile(
        {
            "id": "test-profile-defaults",
            "source_path": "tests/sources/sample.docx",
            "output_basename": "sample-defaults.out.docx",
            "default_run_profile": "structural-passthrough-default",
            "tags": ["test"],
            "provenance": "unit-test",
        }
    )

    assert profile.max_pdf_blank_page_marker_leakage is None
    assert profile.max_inline_page_furniture_leakage is None
    assert profile.max_adjacent_h1_without_body is None
    assert profile.max_heading_body_concat_detected is None
    assert profile.max_h1_epigraph_attribution_pattern is None


def test_workflow_doc_describes_benchmark_only_policy_and_current_registered_mappings() -> None:
    workflow_doc_text = WORKFLOW_DOC_PATH.read_text(encoding="utf-8")

    assert "benchmark-only" in workflow_doc_text
    assert "ui-parity-translate-benchmark-advisory" in workflow_doc_text
    assert "lietaer-pdf-first-20-benchmark" in workflow_doc_text
    assert "lietaer-pdf-full-benchmark" in workflow_doc_text
    assert "excluded from mandatory full gates" in workflow_doc_text
    assert "structural-ai-first-default" in workflow_doc_text
    assert "ui-parity-translate-audiobook-postprocess" in workflow_doc_text


def test_workflow_docs_reference_existing_registry_profiles_tasks_and_scripts() -> None:
    workflow_doc_text = WORKFLOW_DOC_PATH.read_text(encoding="utf-8")
    task_labels = _load_vscode_task_labels()
    document_profile_ids = {profile.id for profile in REGISTRY.documents}
    run_profile_ids = {profile.id for profile in REGISTRY.run_profiles}

    expected_tasks = {
        "Run Structure Recovery Diagnostic (First 20 Pages)",
        "Run Lietaer Real Validation",
        "Run Lietaer Real Validation AI",
        "Run Real Document Validation Profile",
        "Run Real Document Quality Gate",
    }
    expected_scripts = {
        "scripts/run-structural-preparation-diagnostic.sh",
        "scripts/run-real-document-validation.sh",
        "scripts/run-real-document-quality-gate.sh",
    }
    expected_document_profiles = {
        "lietaer-core",
        "religion-wealth-core",
        "lietaer-pdf-first-20-structure-core",
        "lietaer-pdf-chapter-region-core",
    }
    expected_run_profiles = {
        "ui-parity-default",
        "ui-parity-ai-default",
        "ui-parity-soak-3x",
        "structural-passthrough-default",
        "ui-parity-pdf-structural-recovery",
    }

    for task_label in expected_tasks:
        assert task_label in workflow_doc_text
        assert task_label in task_labels

    for script_path in expected_scripts:
        assert script_path in workflow_doc_text
        assert Path(script_path).exists()

    for profile_id in expected_document_profiles:
        assert profile_id in workflow_doc_text
        assert profile_id in document_profile_ids

    for profile_id in expected_run_profiles:
        assert profile_id in workflow_doc_text
        assert profile_id in run_profile_ids


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


def test_end_times_pdf_structural_run_profile_is_generic_structural_recovery() -> None:
    document_profile = REGISTRY.get_document_profile("end-times-pdf-core")
    run_profile = _resolve_structural_run_profile(document_profile)

    assert run_profile.id == "ui-parity-pdf-structural-recovery"
    assert document_profile.structural_expected_result == "pass"
    assert document_profile.structural_expected_failed_checks == ()
    assert document_profile.structural_optional_failed_checks == ()


def test_lietaer_first20_structural_run_profile_is_ai_first_default() -> None:
    document_profile = REGISTRY.get_document_profile("lietaer-pdf-first-20-structure-core")
    run_profile = _resolve_structural_run_profile(document_profile)

    assert run_profile.id == "structural-ai-first-default"
    assert document_profile.structural_expected_result == "pass"
    assert document_profile.structural_expected_failed_checks == ()
    assert document_profile.structural_optional_failed_checks == ()


def test_lietaer_chapter_region_structural_run_profile_is_ai_first_default() -> None:
    document_profile = REGISTRY.get_document_profile("lietaer-pdf-chapter-region-core")
    run_profile = _resolve_structural_run_profile(document_profile)

    assert run_profile.id == "structural-ai-first-default"
    assert run_profile.structure_recovery_topology_projection_enabled is True
    assert run_profile.structure_recovery_topology_projection_layout_signals_enabled is True
    assert run_profile.structure_recovery_topology_projection_binding_splits_enabled is True
    assert document_profile.structural_expected_result == "pass"
    assert document_profile.structural_expected_failed_checks == ()
    assert document_profile.structural_optional_failed_checks == ()


def test_build_preparation_diagnostic_defaults_includes_layout_signals_event_context() -> None:
    snapshot = real_document_validation_structural._build_preparation_diagnostic_defaults(
        [
            {
                "event_id": "document_topology_layout_signals_built",
                "context": {
                    "body_baseline_pt": 11.0,
                    "tier_count": 3,
                    "heading_tier_count": 2,
                    "paragraphs_with_font_size_count": 42,
                    "heading_ratio": 1.15,
                },
            }
        ]
    )

    assert snapshot["document_topology_layout_signals"] == {
        "body_baseline_pt": 11.0,
        "tier_count": 3,
        "heading_tier_count": 2,
        "paragraphs_with_font_size_count": 42,
        "heading_ratio": 1.15,
    }


def test_lietaer_chapter_region_structural_diagnostic_artifact_locks_chapter_11_stage1_authority_contract() -> None:
    diagnostic_payload = _load_json_payload(LIETAER_CHAPTER_REGION_STRUCTURAL_DIAGNOSTIC_PATH)
    document_map_payload = _load_json_payload(LIETAER_CHAPTER_REGION_DOCUMENT_MAP_ARTIFACT_PATH)
    topology_payload = _load_json_payload(LIETAER_CHAPTER_REGION_TOPOLOGY_ARTIFACT_PATH)

    _assert_lietaer_chapter_region_chapter_11_stage1_authority_contract(
        diagnostic_payload,
        document_map_payload=document_map_payload,
        topology_payload=topology_payload,
    )


def test_lietaer_chapter_region_structural_passthrough_keeps_live_contract_separate_from_fixture_refresh() -> None:
    document_profile = REGISTRY.get_document_profile("lietaer-pdf-chapter-region-core")
    source_path = document_profile.resolved_source_path()
    _skip_if_missing_real_document_source(source_path)
    _skip_if_legacy_doc_conversion_unavailable(source_path)
    run_profile = _resolve_structural_run_profile(document_profile)
    _skip_if_structural_passthrough_runtime_unavailable(run_profile)

    diagnostic_payload = evaluate_structural_preparation_diagnostic(document_profile, run_profile)
    snapshot = cast(dict[str, Any], diagnostic_payload["preparation_diagnostic_snapshot"])
    snapshot_projection = cast(dict[str, Any], snapshot["document_topology_projection"])
    document_map_cache_key = str(snapshot_projection["document_map_cache_key"])
    topology_cache_key = str(snapshot_projection["cache_key"])
    document_map_artifact_path = Path(".run/document_maps") / f"{document_map_cache_key}.json"
    topology_artifact_path = Path(".run/document_topology") / f"{topology_cache_key}.json"
    live_document_map_payload = _load_json_payload(document_map_artifact_path)
    live_topology_payload = _load_json_payload(topology_artifact_path)

    assert document_map_artifact_path.exists(), document_map_artifact_path
    assert topology_artifact_path.exists(), topology_artifact_path
    assert document_map_cache_key == str(live_document_map_payload["cache_key"])
    assert topology_cache_key == str(live_topology_payload["cache_key"])

    _assert_lietaer_chapter_region_chapter_11_stage1_authority_contract(
        diagnostic_payload,
        document_map_payload=live_document_map_payload,
        topology_payload=live_topology_payload,
    )


def test_lietaer_full_benchmark_default_run_profile_enables_topology_projection() -> None:
    document_profile = REGISTRY.get_document_profile("lietaer-pdf-full-benchmark")
    run_profile = REGISTRY.resolve_run_profile(document_profile)

    assert document_profile.default_run_profile == "ui-parity-translate-benchmark-topology-advisory"
    assert run_profile.tier == "full"
    assert run_profile.processing_operation == "translate"
    assert run_profile.translation_output_quality_gate_policy == "advisory"
    assert run_profile.structure_recognition_mode == "always"
    assert run_profile.structure_recovery_topology_projection_enabled is True
    assert run_profile.structure_recovery_topology_projection_binding_splits_enabled is True


def test_end_times_pdf_structural_diagnostic_artifact_matches_current_contract() -> None:
    artifact_path = Path("tests/artifacts/structural_diagnostics/end-times-pdf-core/structural_diagnostic.json")
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    snapshot = payload["preparation_diagnostic_snapshot"]
    document_profile = REGISTRY.get_document_profile("end-times-pdf-core")

    assert payload["document_profile_id"] == "end-times-pdf-core"
    assert payload["run_profile_id"] == "ui-parity-pdf-structural-recovery"
    assert payload["validation_tier"] == "structural"
    assert payload["validation_execution_mode"] == "passthrough"
    assert payload["passed"] is True
    assert payload["failed_checks"] == []
    assert payload["preparation_error"] is None
    assert snapshot["readiness_status"] == "ready"
    assert snapshot["readiness_reasons"] == []
    assert snapshot["quality_gate_status"] == "pass"
    assert snapshot["quality_gate_reasons"] == []
    assert snapshot["structure_ai_attempted"] is False


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
    document_profile = SimpleNamespace(id="end-times-pdf-core")
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
        "document_profile_id": "end-times-pdf-core",
        "run_profile_id": "ui-parity-pdf-structural-recovery",
        "validation_tier": "structural",
        "validation_execution_mode": "passthrough",
        "passed": False,
        "failed_checks": ["preparation_quality_gate_blocked"],
        "preparation_error": "blocked by quality gate",
        "preparation_diagnostic_snapshot": {"readiness_status": "blocked_unsafe_best_effort_only"},
    }


def test_build_preparation_diagnostic_defaults_includes_spec_acceptance_fields() -> None:
    snapshot = real_document_validation_structural._build_preparation_diagnostic_defaults(
        [
            {
                "event_id": "structure_processing_outcome",
                "context": {
                    "readiness_status": "ready_with_warnings",
                    "readiness_reasons": ["x"],
                    "quality_gate_status": "pass",
                    "quality_gate_reasons": [],
                    "structure_ai_attempted": True,
                    "ai_classified_count": 8,
                    "ai_heading_count": 2,
                    "document_map_present": True,
                    "document_map_status": "ai",
                    "document_map_status_reason": "",
                    "outline_coverage_ratio": 0.75,
                    "document_topology_projection_status": "no_operations",
                    "document_topology_projection_status_reason": "",
                },
            },
            {
                "event_id": "reconciliation_report_saved",
                "context": {
                    "front_matter_leaks": [1, 3],
                    "outline_coverage_ratio": 0.75,
                        "front_matter_body_advisories": [2],
                    "targeted_recall_invoked": True,
                },
            },
        ]
    )

    assert snapshot["document_map_present"] is True
    assert snapshot["document_map_status"] == "ai"
    assert snapshot["document_map_status_reason"] == ""
    assert snapshot["outline_coverage_ratio"] == 0.75
    assert snapshot["document_topology_projection_status"] == "no_operations"
    assert snapshot["document_topology_projection_status_reason"] == ""
    assert snapshot["front_matter_leaks"] == [1, 3]
    assert snapshot["front_matter_body_advisories"] == [2]
    assert snapshot["targeted_recall_invoked"] is True


def test_build_preparation_diagnostic_defaults_loads_topology_projection_artifact_from_event_log(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "document_topology" / "projection.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        json.dumps(
            {
                "operations": [{"op": "merge_heading_continuation", "logical_indexes": [10, 11]}],
                "projected_units": [{"unit_id": "u_test", "logical_indexes": [10, 11]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(real_document_validation_structural, "PROJECT_ROOT", tmp_path)

    snapshot = real_document_validation_structural._build_preparation_diagnostic_defaults(
        [
            {
                "event_id": "structure_processing_outcome",
                "context": {
                    "document_topology_projection_status": "built",
                },
            },
            {
                "event_id": "document_topology_projection_built",
                "context": {
                    "artifact_path": str(artifact_path),
                },
            },
        ]
    )

    assert snapshot["document_topology_projection_status"] == "built"
    assert snapshot["document_topology_projection"] == {
        "operations": [{"op": "merge_heading_continuation", "logical_indexes": [10, 11]}],
        "projected_units": [{"unit_id": "u_test", "logical_indexes": [10, 11]}],
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


def test_runtime_resolution_accepts_provider_qualified_model_override() -> None:
    app_config = SimpleNamespace(
        models=SimpleNamespace(
            text=SimpleNamespace(
                default="gpt-5.4-mini",
                options=("gpt-5.4-mini", "openrouter:google/gemini-3.1-flash-lite-preview"),
            )
        ),
        chunk_size=6000,
        max_retries=3,
        image_mode_default="safe",
        processing_operation_default="edit",
        source_language_default="en",
        target_language_default="ru",
        translation_domain_default="general",
        audiobook_postprocess_default=False,
        enable_paragraph_markers=True,
        keep_all_image_variants=False,
        structure_recognition_mode="off",
        structure_recognition_enabled=False,
        to_dict=lambda: {
            "models": SimpleNamespace(
                text=SimpleNamespace(
                    default="gpt-5.4-mini",
                    options=("gpt-5.4-mini", "openrouter:google/gemini-3.1-flash-lite-preview"),
                )
            ),
            "chunk_size": 6000,
            "max_retries": 3,
            "image_mode_default": "safe",
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "translation_domain_default": "general",
            "audiobook_postprocess_default": False,
            "enable_paragraph_markers": True,
            "keep_all_image_variants": False,
            "structure_recognition_mode": "off",
            "structure_recognition_enabled": False,
        },
    )
    run_profile = validation_profiles.RunProfile(
        id="openrouter-text-profile",
        model="openrouter:google/gemini-3.1-flash-lite-preview",
        processing_operation="translate",
        source_language="en",
        target_language="ru",
    )

    resolution = validation_profiles.resolve_runtime_resolution(app_config, run_profile)
    applied_config = validation_profiles.apply_runtime_resolution_to_app_config(app_config, resolution)

    assert resolution.effective.model == "openrouter:google/gemini-3.1-flash-lite-preview"
    assert resolution.overrides["model"] == "openrouter:google/gemini-3.1-flash-lite-preview"
    assert applied_config["model"] == "openrouter:google/gemini-3.1-flash-lite-preview"
    assert applied_config["processing_operation"] == "translate"


def test_runtime_resolution_applies_translation_quality_gate_policy_override() -> None:
    app_config = SimpleNamespace(
        models=SimpleNamespace(
            text=SimpleNamespace(
                default="gpt-5.4-mini",
                options=("gpt-5.4-mini", "openrouter:google/gemini-3.1-flash-lite-preview"),
            )
        ),
        to_dict=lambda: {
            "models": SimpleNamespace(
                text=SimpleNamespace(
                    default="gpt-5.4-mini",
                    options=("gpt-5.4-mini", "openrouter:google/gemini-3.1-flash-lite-preview"),
                )
            ),
            "model": "gpt-5.4",
            "chunk_size": 6000,
            "max_retries": 3,
            "image_mode_default": "safe",
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "translation_domain_default": "general",
            "audiobook_postprocess_default": False,
            "enable_paragraph_markers": True,
            "keep_all_image_variants": False,
            "structure_recognition_mode": "off",
            "structure_recognition_enabled": False,
            "translation_output_quality_gate_policy": "strict",
        },
        model="gpt-5.4",
        chunk_size=6000,
        max_retries=3,
        image_mode_default="safe",
        processing_operation_default="edit",
        source_language_default="en",
        target_language_default="ru",
        translation_domain_default="general",
        audiobook_postprocess_default=False,
        enable_paragraph_markers=True,
        keep_all_image_variants=False,
        structure_recognition_mode="off",
        structure_recognition_enabled=False,
    )
    run_profile = validation_profiles.RunProfile(
        id="benchmark-translate-profile",
        processing_operation="translate",
        translation_output_quality_gate_policy="advisory",
    )

    resolution = validation_profiles.resolve_runtime_resolution(app_config, run_profile)
    applied_config = validation_profiles.apply_runtime_resolution_to_app_config(app_config, resolution)

    assert resolution.overrides["translation_output_quality_gate_policy"] == "advisory"
    assert resolution.app_config_overrides["translation_output_quality_gate_policy"] == "advisory"
    assert applied_config["translation_output_quality_gate_policy"] == "advisory"


def test_runtime_resolution_applies_reader_cleanup_overrides() -> None:
    app_config = SimpleNamespace(
        models=SimpleNamespace(
            text=SimpleNamespace(
                default="gpt-5.4-mini",
                options=("gpt-5.4-mini",),
            )
        ),
        to_dict=lambda: {
            "models": SimpleNamespace(
                text=SimpleNamespace(
                    default="gpt-5.4-mini",
                    options=("gpt-5.4-mini",),
                )
            ),
            "model": "gpt-5.4",
            "chunk_size": 6000,
            "max_retries": 3,
            "image_mode_default": "safe",
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "translation_domain_default": "general",
            "audiobook_postprocess_default": False,
            "reader_cleanup_default": False,
            "enable_paragraph_markers": True,
            "keep_all_image_variants": False,
            "structure_recognition_mode": "off",
            "structure_recognition_enabled": False,
        },
        model="gpt-5.4",
        chunk_size=6000,
        max_retries=3,
        image_mode_default="safe",
        processing_operation_default="edit",
        source_language_default="en",
        target_language_default="ru",
        translation_domain_default="general",
        audiobook_postprocess_default=False,
        reader_cleanup_default=False,
        enable_paragraph_markers=True,
        keep_all_image_variants=False,
        structure_recognition_mode="off",
        structure_recognition_enabled=False,
    )
    run_profile = validation_profiles.RunProfile(
        id="simple-reader-cleanup",
        processing_operation="translate",
        reader_cleanup_enabled=True,
        reader_cleanup_model="gpt-5.4-mini",
        reader_cleanup_chunk_size=30000,
        reader_cleanup_global_plan_enabled=True,
        reader_cleanup_keep_toc=True,
        reader_cleanup_policy="advisory",
    )

    resolution = validation_profiles.resolve_runtime_resolution(app_config, run_profile)
    applied_config = validation_profiles.apply_runtime_resolution_to_app_config(app_config, resolution)

    assert resolution.effective.reader_cleanup_enabled is True
    assert resolution.overrides["reader_cleanup_enabled"] is True
    assert resolution.overrides["reader_cleanup_model"] == "gpt-5.4-mini"
    assert resolution.app_config_overrides["reader_cleanup_chunk_size"] == 30000
    assert applied_config["reader_cleanup_enabled"] is True
    assert applied_config["reader_cleanup_model"] == "gpt-5.4-mini"
    assert applied_config["reader_cleanup_keep_toc"] is True


def test_runtime_resolution_applies_layout_cleanup_mode_override() -> None:
    app_config = SimpleNamespace(
        models=SimpleNamespace(
            text=SimpleNamespace(
                default="gpt-5.4-mini",
                options=("gpt-5.4-mini",),
            )
        ),
        to_dict=lambda: {
            "models": SimpleNamespace(
                text=SimpleNamespace(
                    default="gpt-5.4-mini",
                    options=("gpt-5.4-mini",),
                )
            ),
            "model": "gpt-5.4",
            "chunk_size": 6000,
            "max_retries": 3,
            "image_mode_default": "safe",
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "translation_domain_default": "general",
            "audiobook_postprocess_default": False,
            "reader_cleanup_default": False,
            "enable_paragraph_markers": True,
            "keep_all_image_variants": False,
            "structure_recognition_mode": "off",
            "structure_recognition_enabled": False,
        },
        model="gpt-5.4",
        chunk_size=6000,
        max_retries=3,
        image_mode_default="safe",
        processing_operation_default="edit",
        source_language_default="en",
        target_language_default="ru",
        translation_domain_default="general",
        audiobook_postprocess_default=False,
        reader_cleanup_default=False,
        enable_paragraph_markers=True,
        keep_all_image_variants=False,
        structure_recognition_mode="off",
        structure_recognition_enabled=False,
    )
    run_profile = validation_profiles.RunProfile(
        id="source-cleanup-remove",
        processing_operation="translate",
        layout_artifact_cleanup_mode="remove",
        reader_verifier_enabled=True,
    )

    resolution = validation_profiles.resolve_runtime_resolution(app_config, run_profile)
    applied_config = validation_profiles.apply_runtime_resolution_to_app_config(app_config, resolution)

    assert resolution.overrides["layout_artifact_cleanup_mode"] == "remove"
    assert resolution.app_config_overrides["layout_artifact_cleanup_mode"] == "remove"
    assert applied_config["layout_artifact_cleanup_mode"] == "remove"
    assert resolution.overrides["reader_verifier_enabled"] is True
    assert resolution.app_config_overrides["reader_verifier_enabled"] is True
    assert applied_config["reader_verifier_enabled"] is True


def test_validation_registry_declares_reader_cleanup_validation_profiles() -> None:
    validation_profiles.load_validation_registry.cache_clear()
    registry = validation_profiles.load_validation_registry()

    baseline = registry.get_run_profile("ui-parity-translate-simple-reader-cleanup")
    comparison_only = registry.get_run_profile("ui-parity-translate-simple-reader-cleanup-comparison-only")
    source_cleanup_remove = registry.get_run_profile("ui-parity-translate-simple-reader-cleanup-source-cleanup-remove")
    # Wide-chunk stays as an optional experiment profile; it is not a stronger repository contract.
    wide_chunk = registry.get_run_profile("ui-parity-translate-simple-reader-cleanup-wide-chunk")

    assert baseline.processing_operation == "translate"
    assert baseline.structure_recognition_mode == "off"
    assert baseline.reader_cleanup_enabled is True
    assert baseline.reader_cleanup_policy == "advisory"
    assert baseline.reader_cleanup_keep_toc is False
    assert baseline.reader_cleanup_drop_back_matter is False
    assert baseline.reader_cleanup_chunk_size == 30000
    assert baseline.comparison_only_validation is False

    assert comparison_only.processing_operation == "translate"
    assert comparison_only.structure_recognition_mode == "off"
    assert comparison_only.reader_cleanup_enabled is True
    assert comparison_only.reader_cleanup_policy == "advisory"
    assert comparison_only.reader_cleanup_keep_toc is False
    assert comparison_only.reader_cleanup_drop_back_matter is False
    assert comparison_only.reader_cleanup_chunk_size == 30000
    assert comparison_only.translation_output_quality_gate_policy == "advisory"
    assert comparison_only.comparison_only_validation is True

    assert source_cleanup_remove.processing_operation == "translate"
    assert source_cleanup_remove.reader_cleanup_enabled is True
    assert source_cleanup_remove.reader_verifier_enabled is True
    assert source_cleanup_remove.translation_output_quality_gate_policy == "advisory"
    assert source_cleanup_remove.layout_artifact_cleanup_mode == "remove"
    assert source_cleanup_remove.comparison_only_validation is True

    assert wide_chunk.processing_operation == "translate"
    assert wide_chunk.reader_cleanup_enabled is True
    assert wide_chunk.reader_cleanup_policy == "advisory"
    assert wide_chunk.reader_cleanup_keep_toc is False
    assert wide_chunk.reader_cleanup_chunk_size == 50000


def test_reader_cleanup_comparison_only_target_document_is_chapter_region_pdf() -> None:
    validation_profiles.load_validation_registry.cache_clear()
    registry = validation_profiles.load_validation_registry()

    document_profile = registry.get_document_profile("lietaer-pdf-chapter-region-core")
    resolved_source = document_profile.resolved_source_path(project_root=Path(__file__).resolve().parents[1])

    assert document_profile.id == "lietaer-pdf-chapter-region-core"
    assert resolved_source.as_posix().endswith(
        "tests/sources/Rethinking-money-chapter-region-pages-10-11-and-156-217.pdf"
    )


def test_runtime_resolution_applies_topology_projection_override() -> None:
    app_config = SimpleNamespace(
        models=SimpleNamespace(
            text=SimpleNamespace(
                default="gpt-5.4-mini",
                options=("gpt-5.4-mini",),
            )
        ),
        to_dict=lambda: {
            "models": SimpleNamespace(
                text=SimpleNamespace(
                    default="gpt-5.4-mini",
                    options=("gpt-5.4-mini",),
                )
            ),
            "model": "gpt-5.4",
            "chunk_size": 6000,
            "max_retries": 3,
            "image_mode_default": "safe",
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "translation_domain_default": "general",
            "audiobook_postprocess_default": False,
            "enable_paragraph_markers": True,
            "keep_all_image_variants": False,
            "structure_recognition_mode": "off",
            "structure_recognition_enabled": False,
            "structure_recovery_topology_projection_enabled": False,
            "structure_recovery_topology_projection_layout_signals_enabled": False,
        },
        model="gpt-5.4",
        chunk_size=6000,
        max_retries=3,
        image_mode_default="safe",
        processing_operation_default="edit",
        source_language_default="en",
        target_language_default="ru",
        translation_domain_default="general",
        audiobook_postprocess_default=False,
        enable_paragraph_markers=True,
        keep_all_image_variants=False,
        structure_recognition_mode="off",
        structure_recognition_enabled=False,
    )
    run_profile = validation_profiles.RunProfile(
        id="structural-ai-first-default",
        tier="structural",
        structure_recognition_mode="always",
        structure_recovery_topology_projection_enabled=True,
        structure_recovery_topology_projection_layout_signals_enabled=True,
        structure_recovery_topology_projection_binding_splits_enabled=True,
    )

    resolution = validation_profiles.resolve_runtime_resolution(app_config, run_profile)
    applied_config = validation_profiles.apply_runtime_resolution_to_app_config(app_config, resolution)

    assert resolution.overrides["structure_recovery_topology_projection_enabled"] is True
    assert resolution.overrides["structure_recovery_topology_projection_layout_signals_enabled"] is True
    assert resolution.overrides["structure_recovery_topology_projection_binding_splits_enabled"] is True
    assert resolution.app_config_overrides["structure_recovery_topology_projection_enabled"] is True
    assert resolution.app_config_overrides["structure_recovery_topology_projection_layout_signals_enabled"] is True
    assert resolution.app_config_overrides["structure_recovery_topology_projection_binding_splits_enabled"] is True
    assert applied_config["structure_recovery_topology_projection_enabled"] is True
    assert applied_config["structure_recovery_topology_projection_layout_signals_enabled"] is True
    assert applied_config["structure_recovery_topology_projection_binding_splits_enabled"] is True


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

    structure_mode = str(runtime_resolution.effective.structure_recognition_mode or "").strip().lower()
    structure_selector = str(getattr(app_config, "structure_recognition_model", "") or "").strip()
    if structure_mode != "off" and structure_selector:
        selectors.append(structure_selector)

    document_map_enabled = bool(getattr(app_config, "structure_recovery_enabled", False)) and bool(
        getattr(app_config, "structure_recovery_document_map_enabled", False)
    )
    if structure_mode != "off" and document_map_enabled:
        document_map_selector = str(getattr(app_config, "structure_recovery_document_map_model", "") or "").strip()
        if not document_map_selector:
            document_map_selector = structure_selector
        if document_map_selector:
            selectors.append(document_map_selector)

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


def test_skip_if_structural_passthrough_runtime_unavailable_uses_controlled_skip_reason(monkeypatch) -> None:
    monkeypatch.setattr(
        __import__(__name__),
        "ensure_pandoc_available",
        lambda: (_ for _ in ()).throw(RuntimeError("pandoc missing")),
    )

    with pytest.raises(pytest.skip.Exception, match=r"structural passthrough runtime unavailable: pandoc missing"):
        _skip_if_structural_passthrough_runtime_unavailable(SimpleNamespace(id="structural-passthrough-default"))


def test_skip_if_structural_passthrough_runtime_unavailable_skips_when_provider_key_missing(monkeypatch) -> None:
    run_profile = REGISTRY.get_run_profile("structural-ai-first-default")

    monkeypatch.setattr(__import__(__name__), "ensure_pandoc_available", lambda: None)

    with pytest.raises(pytest.skip.Exception, match=r"structural passthrough runtime unavailable: .*API_KEY"):
        _skip_if_structural_passthrough_runtime_unavailable(run_profile)


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


def test_structural_cli_uses_lietaer_first20_default_run_profile_and_prints_acceptance_snapshot(capsys, monkeypatch) -> None:
    captured = {}

    def _fake_evaluate(document_profile, run_profile):
        captured["document_profile_id"] = document_profile.id
        captured["run_profile_id"] = run_profile.id
        return {
            "document_profile_id": document_profile.id,
            "run_profile_id": run_profile.id,
            "validation_tier": "structural",
            "validation_execution_mode": "passthrough",
            "passed": True,
            "failed_checks": [],
            "preparation_error": None,
            "preparation_diagnostic_snapshot": {
                "document_map_present": True,
                "document_map_status": "ai",
                "document_map_status_reason": "",
                "outline_coverage_ratio": 1.0,
                "front_matter_leaks": [],
                "targeted_recall_invoked": False,
                "quality_gate_status": "pass",
            },
        }

    monkeypatch.setattr(real_document_validation_structural, "evaluate_structural_preparation_diagnostic", _fake_evaluate)

    exit_code = real_document_validation_structural.main(["lietaer-pdf-first-20-structure-core"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured == {
        "document_profile_id": "lietaer-pdf-first-20-structure-core",
        "run_profile_id": "structural-ai-first-default",
    }
    assert payload["run_profile_id"] == "structural-ai-first-default"
    assert payload["preparation_diagnostic_snapshot"] == {
        "document_map_present": True,
        "document_map_status": "ai",
        "document_map_status_reason": "",
        "outline_coverage_ratio": 1.0,
        "front_matter_leaks": [],
        "targeted_recall_invoked": False,
        "quality_gate_status": "pass",
    }


def test_structural_cli_uses_lietaer_chapter_region_default_run_profile(capsys, monkeypatch) -> None:
    captured = {}

    def _fake_evaluate(document_profile, run_profile):
        captured["document_profile_id"] = document_profile.id
        captured["run_profile_id"] = run_profile.id
        return {
            "document_profile_id": document_profile.id,
            "run_profile_id": run_profile.id,
            "validation_tier": "structural",
            "validation_execution_mode": "passthrough",
            "passed": True,
            "failed_checks": [],
            "preparation_error": None,
            "preparation_diagnostic_snapshot": {
                "document_map_present": True,
                "document_topology_projection_status": "built",
                "quality_gate_status": "pass",
            },
        }

    monkeypatch.setattr(real_document_validation_structural, "evaluate_structural_preparation_diagnostic", _fake_evaluate)

    exit_code = real_document_validation_structural.main(["lietaer-pdf-chapter-region-core"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured == {
        "document_profile_id": "lietaer-pdf-chapter-region-core",
        "run_profile_id": "structural-ai-first-default",
    }
    assert payload["run_profile_id"] == "structural-ai-first-default"
    assert payload["preparation_diagnostic_snapshot"] == {
        "document_map_present": True,
        "document_topology_projection_status": "built",
        "quality_gate_status": "pass",
    }


def test_structural_passthrough_uses_original_legacy_doc_bytes_for_prepared_facade(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "legacy.doc"
    source_bytes = bytes.fromhex("D0CF11E0A1B11AE1") + b"legacy-source"
    source_path.write_bytes(source_bytes)
    document_profile = SimpleNamespace(id="legacy-doc", resolved_source_path=lambda project_root=None: source_path)
    run_profile = SimpleNamespace(id="structural-passthrough-default")
    captured = {}

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
                    translation_domain="general",
                ),
                ui_defaults=_resolution_payload(
                    chunk_size=6000,
                    image_mode="safe",
                    keep_all_image_variants=False,
                    model="gpt-5.4",
                    max_retries=1,
                    translation_domain="general",
                ),
            overrides={},
        ),
    )
    monkeypatch.setattr(real_document_validation_structural, "apply_runtime_resolution_to_app_config", lambda app_config, resolution: {})
    monkeypatch.setattr(real_document_validation_structural, "_snapshot_formatting_diagnostics_paths", lambda: set())
    monkeypatch.setattr(real_document_validation_structural, "_collect_new_formatting_diagnostics_paths", lambda before, after: [])
    monkeypatch.setattr(real_document_validation_structural, "_load_formatting_diagnostics_payloads", lambda paths: [])
    monkeypatch.setattr(
        real_document_validation_structural,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: ([], [], ParagraphBoundaryNormalizationReport(0, 0, 0, 0), [], RelationNormalizationReport(0, {}, 0), _cleanup_report()),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "extract_document_content_from_docx",
        lambda uploaded_file: ([], []),
    )
    monkeypatch.setattr(real_document_validation_structural, "_build_output_artifacts", lambda docx_bytes, markdown_text: {"output_docx_openable": True})
    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_structural_metrics",
        lambda *, paragraphs, image_assets, normalization_report=None, relation_report=None, cleanup_report=None: {},
    )
    monkeypatch.setattr(real_document_validation_structural, "_build_extraction_checks", lambda document_profile, metrics: [])
    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_structural_checks",
        lambda document_profile, result, metrics, output_artifacts: [],
    )

    def _run_prepared_background_document(**kwargs):
        uploaded_file = kwargs["uploaded_file"]
        captured["uploaded_filename"] = uploaded_file.name
        captured["uploaded_bytes"] = uploaded_file.getvalue()
        runtime = kwargs["runtime"]
        runtime["state"]["latest_docx_bytes"] = b"PK\x03\x04output"
        runtime["state"]["latest_markdown"] = "markdown"
        return "succeeded", SimpleNamespace(
            uploaded_file_bytes=b"PK\x03\x04normalized-source",
            source_text="text",
            paragraphs=[],
            image_assets=[],
            jobs=[{"job_kind": "passthrough"}],
        )

    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_validation_processing_service",
        lambda event_log: SimpleNamespace(run_prepared_background_document=_run_prepared_background_document),
    )
    monkeypatch.setattr(
        real_document_validation_structural.processing_runtime,
        "normalize_uploaded_document",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("validator should not pre-normalize uploads")),
    )

    result = cast(
        dict[str, Any],
        run_structural_passthrough_validation(cast(Any, document_profile), cast(Any, run_profile)),
    )

    assert captured["uploaded_filename"] == "legacy.doc"
    assert captured["uploaded_bytes"] == source_bytes
    assert result["result"] == "succeeded"
    assert "source_file" not in result
    assert "runtime_configuration" not in result


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


def test_structural_passthrough_reports_accepted_merged_source_metrics_from_formatting_diagnostics(
    tmp_path, monkeypatch
) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "sample.docx"
    source_path.write_bytes(b"PK\x03\x04source")

    document_profile = SimpleNamespace(
        id="sample-doc",
        resolved_source_path=lambda project_root=None: source_path,
        min_paragraphs=0,
        min_merged_groups=0,
        min_merged_raw_paragraphs=0,
        has_headings=False,
        min_headings=0,
        has_numbered_lists=False,
        min_numbered_items=0,
        has_images=False,
        min_images=0,
        has_tables=False,
        min_tables=0,
        max_formatting_diagnostics=5,
        max_unmapped_source_paragraphs=5,
        max_unmapped_target_paragraphs=5,
        max_heading_level_drift=5,
        min_text_similarity=0.0,
        require_numbered_lists_preserved=False,
        require_nonempty_output=False,
        forbid_heading_only_collapse=False,
    )
    run_profile = SimpleNamespace(id="structural-passthrough-default", image_mode="safe")

    def _resolution_payload(**values):
        return SimpleNamespace(**values, to_dict=lambda: dict(values))

    formatting_payload = {
        "accepted_merged_sources": [
            {
                "logical_paragraph_id": "p0010",
                "origin_raw_indexes": [10, 11],
                "accepted_merged_sources_count": 2,
            },
            {
                "logical_paragraph_id": "p0011",
                "origin_raw_indexes": [20, 21, 22],
                "accepted_merged_sources_count": 3,
            },
        ],
        "accepted_merged_sources_count": 2,
        "max_accepted_merged_sources": 3,
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [],
    }

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
                    translation_domain="general",
                ),
                ui_defaults=_resolution_payload(
                    chunk_size=6000,
                    image_mode="safe",
                    keep_all_image_variants=False,
                    model="gpt-5.4",
                    max_retries=1,
                    translation_domain="general",
                ),
            overrides={},
        ),
    )
    monkeypatch.setattr(real_document_validation_structural, "apply_runtime_resolution_to_app_config", lambda app_config, resolution: {})
    monkeypatch.setattr(real_document_validation_structural, "_snapshot_formatting_diagnostics_paths", lambda: set())
    monkeypatch.setattr(real_document_validation_structural, "_collect_new_formatting_diagnostics_paths", lambda before, after: [])
    monkeypatch.setattr(
        real_document_validation_structural,
        "_load_formatting_diagnostics_payloads",
        lambda paths: [formatting_payload],
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: ([], [], ParagraphBoundaryNormalizationReport(0, 0, 0, 0), [], RelationNormalizationReport(2, {"image_caption": 1, "epigraph_attribution": 1}, 0), _cleanup_report()),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "extract_document_content_from_docx",
        lambda uploaded_file: ([], []),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_output_artifacts",
        lambda docx_bytes, markdown_text: {
            "output_docx_openable": True,
            "output_visible_text_chars": 0,
        },
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_structural_metrics",
        lambda *, paragraphs, image_assets, normalization_report=None, relation_report=None, cleanup_report=None: {},
    )
    monkeypatch.setattr(real_document_validation_structural, "_build_extraction_checks", lambda document_profile, metrics: [])

    captured = {}

    def _build_structural_checks(*, document_profile, result, metrics, output_artifacts):
        captured["metrics"] = dict(metrics)
        return []

    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_structural_checks",
        _build_structural_checks,
    )

    def _run_prepared_background_document(**kwargs):
        runtime = kwargs["runtime"]
        runtime["state"]["latest_docx_bytes"] = b"PK\x03\x04output"
        runtime["state"]["latest_markdown"] = "markdown"
        return "succeeded", SimpleNamespace(
            uploaded_file_bytes=b"PK\x03\x04normalized-source",
            source_text="text",
            paragraphs=[],
            image_assets=[],
            jobs=[{"job_kind": "passthrough"}],
        )

    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_validation_processing_service",
        lambda event_log: SimpleNamespace(run_prepared_background_document=_run_prepared_background_document),
    )

    result = cast(
        dict[str, Any],
        run_structural_passthrough_validation(cast(Any, document_profile), cast(Any, run_profile)),
    )

    assert result["metrics"]["accepted_merged_sources_count"] == 2
    assert result["metrics"]["max_accepted_merged_sources"] == 3
    assert result["metrics"]["relation_count"] == 2
    assert result["metrics"]["relation_counts"] == {"image_caption": 1, "epigraph_attribution": 1}
    assert captured["metrics"]["accepted_merged_sources_count"] == 2
    assert captured["metrics"]["max_accepted_merged_sources"] == 3
    assert captured["metrics"]["relation_count"] == 2
    assert captured["metrics"]["relation_counts"] == {"image_caption": 1, "epigraph_attribution": 1}
    assert result["formatting_diagnostics"] == [formatting_payload]


def test_structural_passthrough_uses_latest_formatting_diagnostics_payload_for_threshold_metrics(
    tmp_path, monkeypatch
) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "sample.docx"
    source_path.write_bytes(b"PK\x03\x04source")

    document_profile = SimpleNamespace(
        id="sample-doc",
        resolved_source_path=lambda project_root=None: source_path,
        min_paragraphs=0,
        min_merged_groups=0,
        min_merged_raw_paragraphs=0,
        has_headings=False,
        min_headings=0,
        has_numbered_lists=False,
        min_numbered_items=0,
        has_images=False,
        min_images=0,
        has_tables=False,
        min_tables=0,
        max_formatting_diagnostics=1,
        max_unmapped_source_paragraphs=1,
        max_unmapped_target_paragraphs=1,
        max_heading_level_drift=5,
        min_text_similarity=0.0,
        require_numbered_lists_preserved=False,
        require_nonempty_output=False,
        forbid_heading_only_collapse=False,
    )
    run_profile = SimpleNamespace(id="structural-passthrough-default", image_mode="safe")

    def _resolution_payload(**values):
        return SimpleNamespace(**values, to_dict=lambda: dict(values))

    earlier_payload = {
        "generated_at_epoch_ms": 1000,
        "unmapped_source_ids": ["p0001", "p0002"],
        "unmapped_target_indexes": [1, 2],
        "accepted_merged_sources": [],
    }
    later_payload = {
        "generated_at_epoch_ms": 2000,
        "unmapped_source_ids": ["p0003"],
        "unmapped_target_indexes": [3],
        "accepted_merged_sources": [],
    }

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
                    translation_domain="general",
                ),
                ui_defaults=_resolution_payload(
                    chunk_size=6000,
                    image_mode="safe",
                    keep_all_image_variants=False,
                    model="gpt-5.4",
                    max_retries=1,
                    translation_domain="general",
                ),
            overrides={},
        ),
    )
    monkeypatch.setattr(real_document_validation_structural, "apply_runtime_resolution_to_app_config", lambda app_config, resolution: {})
    monkeypatch.setattr(real_document_validation_structural, "_snapshot_formatting_diagnostics_paths", lambda: set())
    monkeypatch.setattr(real_document_validation_structural, "_collect_new_formatting_diagnostics_paths", lambda before, after: [])
    monkeypatch.setattr(
        real_document_validation_structural,
        "_load_formatting_diagnostics_payloads",
        lambda paths: [earlier_payload, later_payload],
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: ([], [], ParagraphBoundaryNormalizationReport(0, 0, 0, 0), [], RelationNormalizationReport(0, {}, 0), _cleanup_report()),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "extract_document_content_from_docx",
        lambda uploaded_file: ([], []),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_output_artifacts",
        lambda docx_bytes, markdown_text: {
            "output_docx_openable": True,
            "output_visible_text_chars": 0,
        },
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_structural_metrics",
        lambda *, paragraphs, image_assets, normalization_report=None, relation_report=None, cleanup_report=None: {},
    )
    monkeypatch.setattr(real_document_validation_structural, "_build_extraction_checks", lambda document_profile, metrics: [])

    captured = {}

    def _build_structural_checks(*, document_profile, result, metrics, output_artifacts):
        captured["metrics"] = dict(metrics)
        return []

    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_structural_checks",
        _build_structural_checks,
    )

    def _run_prepared_background_document(**kwargs):
        runtime = kwargs["runtime"]
        runtime["state"]["latest_docx_bytes"] = b"PK\x03\x04output"
        runtime["state"]["latest_markdown"] = "markdown"
        return "succeeded", SimpleNamespace(
            uploaded_file_bytes=b"PK\x03\x04normalized-source",
            source_text="text",
            paragraphs=[],
            image_assets=[],
            jobs=[{"job_kind": "passthrough"}],
        )

    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_validation_processing_service",
        lambda event_log: SimpleNamespace(
            run_prepared_background_document=lambda **kwargs: (
                event_log.append(
                    {
                        "event_id": "structure_processing_outcome",
                        "context": {
                            "quality_gate_status": "pass",
                            "quality_gate_reasons": [],
                            "readiness_status": "ready",
                        },
                    }
                ),
                event_log.append(
                    {
                        "event_id": "block_plan_summary",
                        "context": {
                            "block_count": 3,
                            "llm_block_count": 2,
                            "passthrough_block_count": 1,
                            "first_block_target_chars": [3891, 946, 935],
                        },
                    }
                ),
                _run_prepared_background_document(**kwargs),
            )[-1]
        ),
    )

    result = cast(
        dict[str, Any],
        run_structural_passthrough_validation(cast(Any, document_profile), cast(Any, run_profile)),
    )

    assert result["formatting_diagnostics"] == [earlier_payload, later_payload]
    assert result["metrics"]["formatting_diagnostics_count"] == 1
    assert result["metrics"]["max_unmapped_source_paragraphs"] == 1
    assert result["metrics"]["max_unmapped_target_paragraphs"] == 1
    assert captured["metrics"]["formatting_diagnostics_count"] == 1
    assert captured["metrics"]["max_unmapped_source_paragraphs"] == 1


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


def test_build_structural_checks_prefers_structure_toc_body_gate_when_topology_authority_is_present() -> None:
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
        "effective_source_toc_region_count": 0,
        "toc_body_concat_detected": False,
        "toc_body_concat_markdown_detected": True,
        "toc_body_concat_structure_detected": False,
        "toc_body_concat_gate_source": "topology_projection",
        "structure_repair_toc_body_boundary_repairs": 0,
        "document_map_toc_region_count": 1,
        "topology_toc_entry_count": 2,
        "topology_split_compound_toc_operation_count": 1,
        "document_map_compound_toc_split_hint_count": 1,
    }
    output_artifacts = {"output_docx_openable": True, "output_visible_text_chars": 100}

    checks = real_document_validation_structural._build_structural_checks(
        document_profile=cast(Any, document_profile),
        result="succeeded",
        metrics=metrics,
        output_artifacts=output_artifacts,
    )

    by_name = {check["name"]: check for check in checks}
    assert by_name["no_toc_body_concat_required"]["passed"] is True
    assert by_name["no_toc_body_concat_required"]["toc_body_concat_gate_source"] == "topology_projection"
    assert by_name["no_toc_body_concat_required"]["toc_body_concat_markdown_detected"] is True
    assert by_name["no_toc_body_concat_required"]["toc_body_concat_structure_detected"] is False


def test_build_structural_checks_accepts_document_map_and_topology_toc_authority() -> None:
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
        "source_toc_detected": False,
        "output_toc_detected": False,
        "structure_repair_bounded_toc_regions": 0,
        "source_toc_region_count": 0,
        "effective_source_toc_region_count": 0,
        "document_map_toc_detected": True,
        "document_map_toc_region_count": 1,
        "topology_toc_entry_count": 2,
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
    assert by_name["toc_detected_required"]["document_map_toc_region_count"] == 1
    assert by_name["toc_detected_required"]["topology_toc_entry_count"] == 2


def test_structural_passthrough_surfaces_structure_repair_and_event_metrics(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.4 sample")

    document_profile = SimpleNamespace(
        id="end-times-pdf-core",
        resolved_source_path=lambda project_root=None: source_path,
        min_paragraphs=0,
        min_merged_groups=0,
        min_merged_raw_paragraphs=0,
        has_headings=False,
        min_headings=0,
        has_numbered_lists=False,
        min_numbered_items=0,
        has_images=False,
        min_images=0,
        has_tables=False,
        min_tables=0,
        max_formatting_diagnostics=5,
        max_unmapped_source_paragraphs=0,
        max_unmapped_target_paragraphs=3,
        max_heading_level_drift=1,
        min_text_similarity=0.0,
        require_numbered_lists_preserved=False,
        require_nonempty_output=False,
        forbid_heading_only_collapse=False,
        require_toc_detected=False,
        require_pdf_conversion=True,
        require_no_bullet_headings=False,
        require_no_toc_body_concat=False,
        require_translation_domain="theology",
    )
    run_profile = SimpleNamespace(id="ui-parity-pdf-structural-recovery", image_mode="safe")

    def _resolution_payload(**values):
        return SimpleNamespace(**values, to_dict=lambda: dict(values))

    class _RelationReport:
        total_relations = 3
        relation_counts = {"toc_region": 2}
        rejected_candidate_count = 0

    class _StructureRepairReport:
        repaired_bullet_items = 4
        repaired_numbered_items = 5
        bounded_toc_regions = 1
        toc_body_boundary_repairs = 1
        heading_candidates_from_toc = 7
        remaining_isolated_marker_count = 0

    formatting_payload = {
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [],
    }
    source_paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0),
        ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", source_index=1),
        ParagraphUnit(text="-", role="body", structural_role="body", source_index=2),
        ParagraphUnit(text="Quoted front matter", role="body", structural_role="epigraph", source_index=3),
        ParagraphUnit(text="Introduction", role="heading", structural_role="body", heading_level=1, source_index=4),
    ]

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
            ui_defaults=_resolution_payload(
                chunk_size=6000,
                image_mode="safe",
                keep_all_image_variants=False,
                model="gpt-5.4",
                max_retries=1,
                translation_domain="general",
            ),
            overrides={"translation_domain": "theology"},
        ),
    )
    monkeypatch.setattr(real_document_validation_structural, "apply_runtime_resolution_to_app_config", lambda app_config, resolution: {})
    monkeypatch.setattr(real_document_validation_structural, "_snapshot_formatting_diagnostics_paths", lambda: set())
    monkeypatch.setattr(real_document_validation_structural, "_collect_new_formatting_diagnostics_paths", lambda before, after: [])
    monkeypatch.setattr(
        real_document_validation_structural,
        "_load_formatting_diagnostics_payloads",
        lambda paths: [formatting_payload],
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "build_semantic_blocks",
        lambda paragraphs, max_chars, relations=None: [DocumentBlock(paragraphs=list(paragraphs))],
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: (
            source_paragraphs,
            [],
            ParagraphBoundaryNormalizationReport(0, 0, 0, 0),
            [],
            _RelationReport(),
            _cleanup_report(),
            _StructureRepairReport(),
        ),
    )
    monkeypatch.setattr(real_document_validation_structural, "extract_document_content_from_docx", lambda uploaded_file: ([], []))
    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_output_artifacts",
        lambda docx_bytes, markdown_text: {
            "output_docx_openable": True,
            "output_visible_text_chars": 120,
        },
    )
    monkeypatch.setattr(real_document_validation_structural, "_build_extraction_checks", lambda document_profile, metrics: [])

    def _run_prepared_background_document(**kwargs):
        runtime = kwargs["runtime"]
        runtime["state"]["latest_docx_bytes"] = b"PK\x03\x04output"
        runtime["state"]["latest_markdown"] = "markdown"
        return "succeeded", SimpleNamespace(
            uploaded_file_bytes=b"PK\x03\x04normalized-source",
            source_text="text",
            paragraphs=source_paragraphs,
            image_assets=[],
            jobs=[{"job_kind": "llm"}],
        )

    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_validation_processing_service",
        lambda event_log: SimpleNamespace(
            run_prepared_background_document=lambda **kwargs: (
                event_log.append(
                    {
                        "event_id": "structure_processing_outcome",
                        "context": {
                            "quality_gate_status": "pass",
                            "quality_gate_reasons": [],
                            "readiness_status": "ready",
                        },
                    }
                ),
                event_log.append(
                    {
                        "event_id": "block_plan_summary",
                        "context": {
                            "block_count": 3,
                            "llm_block_count": 2,
                            "passthrough_block_count": 1,
                            "first_block_target_chars": [3891, 946, 935],
                        },
                    }
                ),
                _run_prepared_background_document(**kwargs),
            )[-1]
        ),
    )

    result = cast(
        dict[str, Any],
        run_structural_passthrough_validation(cast(Any, document_profile), cast(Any, run_profile)),
    )

    assert result["metrics"]["structure_repair_bullet_items"] == 4
    assert result["metrics"]["structure_repair_numbered_items"] == 5
    assert result["metrics"]["structure_repair_bounded_toc_regions"] == 1
    assert result["metrics"]["structure_repair_toc_body_boundary_repairs"] == 1
    assert result["metrics"]["structure_repair_heading_candidates_from_toc"] == 7
    assert result["metrics"]["structure_repair_remaining_isolated_markers"] == 0
    assert result["metrics"]["source_toc_region_count"] == 2
    assert result["metrics"]["quality_gate_status"] == "pass"
    assert result["metrics"]["quality_gate_reasons"] == []
    assert result["metrics"]["readiness_status"] == "ready"
    assert result["metrics"]["block_count"] == 3
    assert result["metrics"]["llm_block_count"] == 2
    assert result["metrics"]["passthrough_block_count"] == 1
    assert result["metrics"]["first_block_target_chars"] == [3891, 946, 935]
    snapshot = result["preparation_diagnostic_snapshot"]
    assert snapshot["paragraph_count"] == 5
    assert snapshot["heading_count"] == 1
    assert snapshot["toc_header_count"] == 1
    assert snapshot["toc_entry_count"] == 1
    assert snapshot["bounded_toc_region_count"] == 1
    assert snapshot["repaired_bullet_items"] == 4
    assert snapshot["repaired_numbered_items"] == 5
    assert snapshot["toc_body_boundary_repairs"] == 1
    assert snapshot["remaining_isolated_marker_count"] == 0
    assert snapshot["readiness_status"] == "ready"
    assert snapshot["readiness_reasons"] == []
    assert snapshot["document_map_present"] is False
    assert snapshot["outline_coverage_ratio"] is None
    assert snapshot["front_matter_leaks"] == []
    assert snapshot["front_matter_body_advisories"] == []
    assert snapshot["targeted_recall_invoked"] is False
    assert snapshot["quality_gate_status"] == "pass"
    assert snapshot["quality_gate_reasons"] == []
    assert snapshot["structure_ai_attempted"] is False
    assert snapshot["ai_first_degraded"] is False
    assert snapshot["fallback_stage"] == ""
    assert snapshot["fallback_reason"] == ""
    assert snapshot["document_map_status"] == "not_requested"
    assert snapshot["document_map_status_reason"] == ""
    assert snapshot["ai_classified_count"] == 0
    assert snapshot["ai_heading_count"] == 0
    assert snapshot["semantic_block_count"] == 1
    assert snapshot["first_block_target_chars"] == 3891
    assert snapshot["first_block_has_toc"] is True
    assert snapshot["first_block_has_epigraph"] is True
    assert snapshot["first_block_has_body_start"] is True
    assert snapshot["first_block_has_isolated_marker"] is True
    by_name = {check["name"]: check for check in result["checks"]}
    assert by_name["pdf_conversion_required"]["passed"] is True
    assert by_name["translation_domain_required"]["passed"] is True
    assert by_name["bounded_toc_repair_detected"]["passed"] is True


def test_structural_passthrough_success_uses_prepared_context_when_event_log_lacks_structure_outcome(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.4 sample")

    document_profile = SimpleNamespace(
        id="end-times-pdf-core",
        resolved_source_path=lambda project_root=None: source_path,
        min_paragraphs=0,
        min_merged_groups=0,
        min_merged_raw_paragraphs=0,
        has_headings=False,
        min_headings=0,
        has_numbered_lists=False,
        min_numbered_items=0,
        has_images=False,
        min_images=0,
        has_tables=False,
        min_tables=0,
        max_formatting_diagnostics=5,
        max_unmapped_source_paragraphs=10,
        max_unmapped_target_paragraphs=10,
        max_heading_level_drift=10,
        min_text_similarity=0.0,
        require_numbered_lists_preserved=False,
        require_nonempty_output=False,
        forbid_heading_only_collapse=False,
        require_toc_detected=False,
        require_pdf_conversion=True,
        require_no_bullet_headings=False,
        require_no_toc_body_concat=False,
        require_translation_domain="theology",
    )
    run_profile = SimpleNamespace(id="ui-parity-pdf-structural-recovery", image_mode="safe")

    def _resolution_payload(**values):
        return SimpleNamespace(**values, to_dict=lambda: dict(values))

    class _RelationReport:
        total_relations = 1
        relation_counts = {"toc_region": 1}
        rejected_candidate_count = 0

    class _StructureRepairReport:
        repaired_bullet_items = 0
        repaired_numbered_items = 0
        bounded_toc_regions = 1
        toc_body_boundary_repairs = 1
        heading_candidates_from_toc = 0
        remaining_isolated_marker_count = 0

    source_paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0),
        ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", source_index=1),
        ParagraphUnit(text="Introduction", role="heading", structural_role="body", heading_level=1, source_index=2),
    ]

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
            ui_defaults=_resolution_payload(image_mode="safe", translation_domain="general"),
            overrides={},
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
            source_paragraphs,
            [],
            ParagraphBoundaryNormalizationReport(0, 0, 0, 0),
            [],
            _RelationReport(),
            _cleanup_report(),
            _StructureRepairReport(),
        ),
    )
    monkeypatch.setattr(
        real_document_validation_structural,
        "build_semantic_blocks",
        lambda paragraphs, max_chars, relations=None: [DocumentBlock(paragraphs=list(paragraphs))],
    )

    class _PreparedStub:
        uploaded_file_bytes = b"PK\x03\x04prepared"
        quality_gate_status = "pass"
        quality_gate_reasons = []
        document_map_status = "ai"
        document_map_status_reason = ""
        structure_validation_report = SimpleNamespace(
            readiness_status="ready",
            readiness_reasons=[],
            document_map_present=True,
            outline_coverage_ratio=0.75,
        )
        structure_ai_attempted = True
        ai_classified_count = 12
        ai_heading_count = 4

    def _run_prepared_background_document(**kwargs):
        return ("succeeded", _PreparedStub())

    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_validation_processing_service",
        lambda event_log: SimpleNamespace(
            run_prepared_background_document=lambda **kwargs: (
                event_log.append(
                    {
                        "event_id": "block_plan_summary",
                        "context": {
                            "block_count": 3,
                            "llm_block_count": 2,
                            "passthrough_block_count": 1,
                            "first_block_target_chars": [265, 946, 935],
                        },
                    }
                ),
                _run_prepared_background_document(**kwargs),
            )[-1]
        ),
    )

    result = cast(dict[str, Any], run_structural_passthrough_validation(cast(Any, document_profile), cast(Any, run_profile)))

    assert result["metrics"]["quality_gate_status"] == "pass"
    assert result["metrics"]["quality_gate_reasons"] == []
    assert result["metrics"]["readiness_status"] == "ready"
    assert result["preparation_diagnostic_snapshot"]["quality_gate_status"] == "pass"
    assert result["preparation_diagnostic_snapshot"]["quality_gate_reasons"] == []
    assert result["preparation_diagnostic_snapshot"]["readiness_status"] == "ready"
    assert result["preparation_diagnostic_snapshot"]["readiness_reasons"] == []
    assert result["preparation_diagnostic_snapshot"]["structure_ai_attempted"] is True
    assert result["preparation_diagnostic_snapshot"]["ai_classified_count"] == 12
    assert result["preparation_diagnostic_snapshot"]["ai_heading_count"] == 4
    assert result["preparation_diagnostic_snapshot"]["document_map_present"] is True
    assert result["preparation_diagnostic_snapshot"]["document_map_status"] == "ai"
    assert result["preparation_diagnostic_snapshot"]["document_map_status_reason"] == ""
    assert result["preparation_diagnostic_snapshot"]["outline_coverage_ratio"] == 0.75


def test_apply_prepared_snapshot_fields_uses_prepared_document_map_status_when_present_only_on_prepared() -> None:
    snapshot = real_document_validation_structural._build_preparation_diagnostic_defaults([])
    prepared = SimpleNamespace(
        document_map_status="ai",
        document_map_status_reason="",
        document_map=object(),
        structure_validation_report=SimpleNamespace(
            readiness_status="ready",
            readiness_reasons=[],
            document_map_present=True,
            outline_coverage_ratio=1.0,
        ),
        structure_recognition_summary=SimpleNamespace(
            ai_first_degraded=False,
            fallback_stage="",
            fallback_reason="",
            document_map_present=True,
        ),
        quality_gate_status="pass",
        quality_gate_reasons=(),
        structure_ai_attempted=True,
        ai_classified_count=3,
        ai_heading_count=1,
    )

    real_document_validation_structural._apply_prepared_snapshot_fields(snapshot, prepared)

    assert snapshot["document_map_present"] is True
    assert snapshot["document_map_status"] == "ai"
    assert snapshot["document_map_status_reason"] == ""


def test_apply_structure_validation_snapshot_fields_prefers_bounded_toc_count_from_validation_report() -> None:
    snapshot = real_document_validation_structural.build_preparation_diagnostic_snapshot(
        paragraphs=[ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0, logical_index=0)],
        relations=[],
        structure_repair_report=SimpleNamespace(
            bounded_toc_regions=0,
            repaired_bullet_items=0,
            repaired_numbered_items=0,
            toc_body_boundary_repairs=0,
            remaining_isolated_marker_count=0,
        ),
        chunk_size=1000,
        event_log=[],
    )

    real_document_validation_structural._apply_structure_validation_snapshot_fields(
        snapshot,
        SimpleNamespace(
            toc_region_bounded_count=1,
            readiness_status="ready",
            readiness_reasons=(),
            document_map_present=False,
            outline_coverage_ratio=None,
        ),
    )

    assert snapshot["bounded_toc_region_count"] == 1


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


def test_apply_prepared_snapshot_and_metric_fields_surface_document_map_and_topology_toc_authority() -> None:
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=DocumentMapTocRegion(
            start_logical_index=0,
            end_logical_index=9,
            header_logical_index=0,
            entries=(
                DocumentMapTocEntry(
                    title="8 Strategies for Governments",
                    target_level=2,
                    candidate_body_logical_index=10,
                    confidence="high",
                ),
                DocumentMapTocEntry(
                    title="10 Truth and Consequences: Lessons Learned",
                    target_level=2,
                    candidate_body_logical_index=161,
                    confidence="high",
                ),
            ),
            confidence="high",
        ),
        outline=(),
        paragraph_anchors={
            0: DocumentMapAnchor(role="toc_header", heading_level=None, confidence="high"),
            8: DocumentMapAnchor(role="toc_entry", heading_level=None, confidence="high"),
            9: DocumentMapAnchor(role="toc_entry", heading_level=None, confidence="high"),
        },
        review_zones=(),
        split_hints=(),
        sampled=False,
        sampled_logical_indexes=(0, 8, 9),
    )
    projection = DocumentTopologyProjection(
        cache_key="topology-key",
        document_map_cache_key="document-map-key",
        projected_units=(
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(8,),
                canonical_text="10 Truth and Consequences: Lessons Learned",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
                evidence=("bounded_toc_region", "one_to_one_toc_entry_match", "toc_entry"),
            ),
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(8,),
                canonical_text="11 Governance and We, the Citizens: An Ancient Future?",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
                evidence=("bounded_toc_region", "one_to_one_toc_entry_match", "toc_entry"),
            ),
        ),
    )
    prepared = SimpleNamespace(
        document_map=document_map,
        document_map_status="ai",
        document_map_status_reason="",
        document_topology_projection=projection,
        document_topology_projection_status="built",
        document_topology_projection_status_reason="",
        quality_gate_status="pass",
        quality_gate_reasons=(),
        structure_validation_report=SimpleNamespace(readiness_status="ready_with_warnings", readiness_reasons=()),
        structure_recognition_summary=SimpleNamespace(
            ai_first_degraded=False,
            fallback_stage="",
            fallback_reason="",
            document_map_present=True,
        ),
    )

    snapshot = real_document_validation_structural._build_preparation_diagnostic_defaults([])
    metrics: dict[str, object] = {"toc_body_concat_markdown_detected": True, "toc_body_concat_detected": True}

    real_document_validation_structural._apply_prepared_snapshot_fields(snapshot, prepared)
    real_document_validation_structural._apply_prepared_metric_fields(metrics, prepared)

    assert snapshot["bounded_toc_region_count"] == 1
    assert snapshot["toc_header_count"] == 1
    assert snapshot["toc_entry_count"] == 2
    assert snapshot["toc_body_concat_gate_source"] == "topology_projection"
    assert snapshot["toc_body_concat_structure_detected"] is False
    assert metrics["document_map_toc_detected"] is True
    assert metrics["document_map_toc_region_count"] == 1
    assert metrics["topology_toc_entry_count"] == 2
    assert metrics["toc_body_concat_markdown_detected"] is True
    assert metrics["toc_body_concat_structure_detected"] is False
    assert metrics["toc_body_concat_gate_source"] == "topology_projection"
    assert metrics["toc_body_concat_detected"] is False


def test_derive_toc_body_concat_gate_fields_falls_back_to_legacy_markdown_without_authoritative_projection() -> None:
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=DocumentMapTocRegion(
            start_logical_index=0,
            end_logical_index=9,
            header_logical_index=0,
            entries=(),
            confidence="high",
        ),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(),
        sampled=False,
        sampled_logical_indexes=(0,),
    )
    projection = DocumentTopologyProjection(
        cache_key="topology-low-confidence",
        projected_units=(
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(8,),
                canonical_text="10 Truth and Consequences",
                role="toc_entry",
                heading_level=None,
                confidence="medium",
                authority="document_map_toc",
            ),
        ),
    )

    fields = real_document_validation_structural._derive_toc_body_concat_gate_fields(
        document_map=document_map,
        topology_projection=projection,
        markdown_detected=True,
    )

    assert fields["toc_body_concat_gate_source"] == "legacy_markdown"
    assert fields["toc_body_concat_detected"] is True
    assert fields["toc_body_concat_structure_detected"] is False


def test_has_toc_body_concat_structure_ignores_authoritative_compound_toc_split_projection() -> None:
    projection = DocumentTopologyProjection(
        cache_key="topology-split-ok",
        operations=(
            DocumentTopologyOperation(
                op="split_compound_toc_entries",
                logical_indexes=(8,),
                canonical_text="10 Truth and Consequences | 11 Governance and We, the Citizens",
                authority="document_map_toc",
                confidence="high",
                evidence=("bounded_toc_region",),
            ),
        ),
        projected_units=(
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(8,),
                canonical_text="10 Truth and Consequences",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
            ),
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(8,),
                canonical_text="11 Governance and We, the Citizens",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
            ),
        ),
    )

    assert real_document_validation_structural.has_toc_body_concat_structure(projection) is False


def test_derive_unit_aware_unmapped_fields_collapses_merged_source_fragments_to_one_unit() -> None:
    source_paragraphs = [
        ParagraphUnit(text="Governance and We,", role="heading", paragraph_id="p0000", source_index=0, logical_index=10),
        ParagraphUnit(text="the Citizens", role="heading", paragraph_id="p0001", source_index=1, logical_index=11),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-merged-heading",
        projected_units=(
            StructuralUnit(
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Governance and We, the Citizens",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload={
            "unmapped_source_ids": ["p0000", "p0001"],
            "unmapped_target_indexes": [],
        },
        generated_paragraph_registry=None,
    )

    assert fields["structure_unit_unmapped_source_count"] == 1
    assert fields["unit_unmapped_source_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_counts_split_units_on_shared_logical_index_distinctly() -> None:
    source_paragraphs = [
        ParagraphUnit(text="10 Truth... 11 Governance...", role="body", paragraph_id="p0008", source_index=8, logical_index=8),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-split-toc-entry",
        projected_units=(
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(8,),
                canonical_text="10 Truth and Consequences",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
            ),
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(8,),
                canonical_text="11 Governance and We, the Citizens",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
            ),
        ),
    )
    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload={
            "unmapped_source_ids": ["p0008"],
            "unmapped_target_indexes": [],
        },
        generated_paragraph_registry=None,
    )

    assert fields["structure_unit_unmapped_source_count"] == 2
    assert fields["unit_unmapped_source_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_collapses_unmapped_targets_by_aligned_topology_unit() -> None:
    source_paragraphs = [
        ParagraphUnit(text="Governance and We,", role="heading", paragraph_id="p0000", source_index=0, logical_index=10),
        ParagraphUnit(text="the Citizens", role="heading", paragraph_id="p0001", source_index=1, logical_index=11),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-target-collapse",
        projected_units=(
            StructuralUnit(
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Governance and We, the Citizens",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [0, 1],
        "target_registry": [
            {"target_index": 0, "mapped": False, "text_preview": "Governance and We,"},
            {"target_index": 1, "mapped": False, "text_preview": "the Citizens"},
        ],
    }
    generated_registry = [
        {"paragraph_id": "p0000", "text": "# Governance and We,"},
        {"paragraph_id": "p0001", "text": "# the Citizens"},
    ]

    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=generated_registry,
    )

    assert fields["structure_unit_unmapped_target_count"] == 1
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_cancels_shared_chapter_heading_unit_between_unmapped_source_and_target() -> None:
    source_paragraphs = [
        ParagraphUnit(text="Chapter Eight", role="heading", paragraph_id="p0793", source_index=793, logical_index=200),
        ParagraphUnit(text="Strategies for Governments", role="heading", paragraph_id="p0794", source_index=794, logical_index=201),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-shared-heading-cancel",
        projected_units=(
            StructuralUnit(
                unit_type="chapter_heading",
                logical_indexes=(200, 201),
                canonical_text="Chapter Eight STRATEGIES FOR GOVERNMENTS",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )

    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload={
            "unmapped_source_ids": ["p0793", "p0794"],
            "unmapped_target_indexes": [753],
            "target_registry": [
                {"target_index": 753, "mapped": False, "text_preview": "глава восьмая стратегии для государств"},
            ],
        },
        generated_paragraph_registry=[
            {
                "paragraph_id": "p0793",
                "merged_paragraph_ids": ["p0793", "p0794"],
                "text": "# Глава восьмая стратегии для государств",
            },
        ],
    )

    assert fields["structure_unit_unmapped_source_count"] == 0
    assert fields["structure_unit_unmapped_target_count"] == 0
    assert fields["unmapped_source_count_basis"] == "topology_unit"
    assert fields["unmapped_target_count_basis"] == "topology_unit"
    assert fields["unit_unmapped_source_gate_source"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_aligns_truncated_toc_target_preview_to_generated_composite() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="4 the flying fish: a new perspective on money 57 5 the future has arrived but isn't distributed evenly...",
            role="body",
            structural_role="toc_entry",
            paragraph_id="p0038",
            source_index=38,
            logical_index=40,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-truncated-toc-preview",
        projected_units=(
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(40,),
                canonical_text="Chapter Eight STRATEGIES FOR GOVERNMENTS",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
            ),
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(40,),
                canonical_text="Strategies for NGOs",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
            ),
        ),
    )
    generated_text = (
        "4 летучая рыба: новый взгляд на деньги 57 5 будущее уже наступило, но распределено неравномерно, "
        "но пока что только для немногих регионов и институтов"
    )
    target_preview = generated_text[:119].rstrip() + "…"

    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload={
            "unmapped_source_ids": ["p0038"],
            "unmapped_target_indexes": [31],
            "target_registry": [
                {"target_index": 31, "mapped": False, "text_preview": target_preview},
            ],
        },
        generated_paragraph_registry=[
            {"paragraph_id": "p0038", "text": generated_text},
        ],
    )

    assert fields["structure_unit_unmapped_source_count"] == 0
    assert fields["structure_unit_unmapped_target_count"] == 0
    assert fields["unmapped_target_count_basis"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_suppresses_source_unit_already_covered_by_mapped_target_alignment() -> None:
    source_paragraphs = [
        ParagraphUnit(text="Chapter One", role="heading", paragraph_id="p0103", source_index=103, logical_index=103),
        ParagraphUnit(text="The Failure of Money", role="heading", paragraph_id="p0104", source_index=104, logical_index=104),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-covered-source-unit",
        projected_units=(
            StructuralUnit(
                unit_type="chapter_heading",
                logical_indexes=(103, 104),
                canonical_text="Chapter One THE FAILURE OF MONEY",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )

    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload={
            "unmapped_source_ids": ["p0103"],
            "unmapped_target_indexes": [],
            "target_registry": [
                {"target_index": 93, "mapped": True, "text_preview": "глава первая крах денег"},
            ],
        },
        generated_paragraph_registry=[
            {
                "paragraph_id": "p0103",
                "merged_paragraph_ids": ["p0103", "p0104"],
                "text": "# Глава первая крах денег",
            },
        ],
    )

    assert fields["structure_unit_unmapped_source_count"] == 0
    assert fields["structure_unit_unmapped_target_count"] == 0
    assert fields["unmapped_source_count_basis"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_cancels_note_heading_interval_recovery_with_paragraph_fallback_keys() -> None:
    source_paragraphs = [
        ParagraphUnit(text="Underclass (Oxford: Blackwell, 1996).", role="body", paragraph_id="p1429", source_index=1429, logical_index=1429),
        ParagraphUnit(text="230 notes", role="heading", paragraph_id="p1430", source_index=1430, logical_index=1430, heading_level=1),
        ParagraphUnit(text="chapter 4", role="heading", paragraph_id="p1431", source_index=1431, logical_index=1431, heading_level=1),
        ParagraphUnit(
            text="Glyn Davies, A History of Money from Ancient Times to the Present Day",
            role="list",
            paragraph_id="p1432",
            source_index=1432,
            logical_index=1432,
            list_kind="ordered",
            list_level=0,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-note-interval-recovery",
        projected_units=(
            StructuralUnit(
                unit_id="u_elsewhere",
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Elsewhere",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "source_registry": [
            {"paragraph_id": "p1429", "mapped_target_index": 1331},
            {"paragraph_id": "p1430", "mapped_target_index": None},
            {"paragraph_id": "p1431", "mapped_target_index": None},
            {"paragraph_id": "p1432", "mapped_target_index": 1333},
        ],
        "unmapped_source_ids": ["p1430", "p1431"],
        "unmapped_target_indexes": [1332],
        "target_registry": [
            {"target_index": 1331, "mapped": True, "text_preview": "низшие слои общества"},
            {"target_index": 1332, "mapped": False, "text_preview": "230 примечания глава 4"},
            {"target_index": 1333, "mapped": True, "text_preview": "глин дэвис"},
        ],
    }
    generated_paragraph_registry = [
        {"paragraph_id": "p1430", "text": "# 230 ПРИМЕЧАНИЯ"},
        {"paragraph_id": "p1431", "text": "# Глава 4"},
        {"paragraph_id": "p1432", "text": "1. Глин Дэвис"},
    ]

    paragraph_unit_keys, _ = real_document_validation_structural._build_source_paragraph_unit_membership(
        source_paragraphs,
        projection,
    )
    source_registry_alignments, _, _ = real_document_validation_structural._build_target_alignments_from_source_registry(
        formatting_payload,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    aligned_target_unit_keys = real_document_validation_structural._align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
    )

    assert paragraph_unit_keys["p1430"] == frozenset({"paragraph:p1430"})
    assert paragraph_unit_keys["p1431"] == frozenset({"paragraph:p1431"})
    assert source_registry_alignments == {
        1331: frozenset({"paragraph:p1429"}),
        1333: frozenset({"paragraph:p1432"}),
    }
    assert aligned_target_unit_keys is not None
    assert aligned_target_unit_keys[1332] == frozenset({"paragraph:p1430", "paragraph:p1431"})
    assert fields["structure_unit_unmapped_source_count"] == 0
    assert fields["structure_unit_unmapped_target_count"] == 0
    assert fields["unmapped_source_count_basis"] == "topology_unit"
    assert fields["unmapped_target_count_basis"] == "topology_unit"
    assert fields["unit_unmapped_source_gate_source"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_aligns_numbered_ibid_target_preview() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="America Down? Atlantic Monthly, October 1995.",
            role="body",
            paragraph_id="p1371",
            source_index=1371,
            logical_index=1371,
        ),
        ParagraphUnit(
            text="Ibid.",
            role="list",
            paragraph_id="p1372",
            source_index=1372,
            logical_index=1372,
            list_kind="ordered",
            list_level=0,
        ),
        ParagraphUnit(
            text="There have been two exceptions.",
            role="list",
            paragraph_id="p1373",
            source_index=1373,
            logical_index=1373,
            list_kind="ordered",
            list_level=0,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-numbered-ibid-preview-alignment",
        projected_units=(
            StructuralUnit(
                unit_id="u_elsewhere",
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Elsewhere",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "source_registry": [
            {"paragraph_id": "p1371", "mapped_target_index": 1254},
            {"paragraph_id": "p1372", "mapped_target_index": 1370},
            {"paragraph_id": "p1373", "mapped_target_index": 1256},
        ],
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [1255],
        "target_registry": [
            {"target_index": 1254, "mapped": True, "text_preview": "америке становится хуже?"},
            {"target_index": 1255, "mapped": False, "text_preview": "там же."},
            {"target_index": 1256, "mapped": True, "text_preview": "существовало два исключения."},
            {"target_index": 1370, "mapped": True, "text_preview": "11."},
        ],
    }
    generated_paragraph_registry = [
        {"paragraph_id": "p1372", "text": "11. Там же."},
    ]

    paragraph_unit_keys, _ = real_document_validation_structural._build_source_paragraph_unit_membership(
        source_paragraphs,
        projection,
    )
    aligned_target_unit_keys = real_document_validation_structural._align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
    )

    assert aligned_target_unit_keys is not None
    assert aligned_target_unit_keys[1255] == frozenset({"paragraph:p1372"})
    assert fields["structure_unit_unmapped_source_count"] == 0
    assert fields["structure_unit_unmapped_target_count"] == 0
    assert fields["unmapped_target_count_basis"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_does_not_align_numbered_ibid_preview_to_different_text() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="Ibid.",
            role="list",
            paragraph_id="p1372",
            source_index=1372,
            logical_index=1372,
            list_kind="ordered",
            list_level=0,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-numbered-ibid-preview-guard",
        projected_units=(
            StructuralUnit(
                unit_id="u_elsewhere",
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Elsewhere",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "source_registry": [
            {"paragraph_id": "p1372", "mapped_target_index": 1370},
        ],
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [1255],
        "target_registry": [
            {"target_index": 1255, "mapped": False, "text_preview": "там же."},
            {"target_index": 1370, "mapped": True, "text_preview": "11."},
        ],
    }
    generated_paragraph_registry = [
        {"paragraph_id": "p1372", "text": "11. См. другой источник."},
    ]

    aligned_target_unit_keys = real_document_validation_structural._align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=real_document_validation_structural._build_source_paragraph_unit_membership(
            source_paragraphs,
            projection,
        )[0],
    )
    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
    )

    assert aligned_target_unit_keys is not None
    assert 1255 not in aligned_target_unit_keys
    assert fields["structure_unit_unmapped_target_count"] == 1
    assert fields["unmapped_target_count_basis"] == "legacy_paragraph"
    assert fields["unit_unmapped_target_gate_source"] == "legacy_paragraph"


def test_collect_target_alignment_preview_trace_replays_saved_target_1274() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="America Down? Atlantic Monthly, October 1995.",
            role="body",
            paragraph_id="p1371",
            source_index=1371,
            logical_index=1371,
        ),
        ParagraphUnit(
            text="Ibid.",
            role="list",
            paragraph_id="p1372",
            source_index=1372,
            logical_index=1372,
            list_kind="ordered",
            list_level=0,
        ),
        ParagraphUnit(
            text="There have been two exceptions.",
            role="list",
            paragraph_id="p1373",
            source_index=1373,
            logical_index=1373,
            list_kind="ordered",
            list_level=0,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-preview-trace-1274",
        projected_units=(
            StructuralUnit(
                unit_id="u_elsewhere",
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Elsewhere",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "source_registry": [
            {"paragraph_id": "p1371", "mapped_target_index": 1273},
            {"paragraph_id": "p1372", "mapped_target_index": 1373},
            {"paragraph_id": "p1373", "mapped_target_index": 1275},
        ],
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [1274],
        "target_registry": [
            {"target_index": 1273, "mapped": True, "text_preview": "america down? atlantic monthly, october 1995."},
            {"target_index": 1274, "mapped": False, "text_preview": "там же."},
            {"target_index": 1275, "mapped": True, "text_preview": "there have been two exceptions: friedrich hayek and maurice allais both"},
        ],
    }
    generated_paragraph_registry = [
        {"paragraph_id": "p1371", "text": "Америка в упадке?», Atlantic Monthly, октябрь 1995 г."},
        {"paragraph_id": "p1372", "text": "11. Там же."},
        {"paragraph_id": "p1373", "text": "12. Было два исключения: Фридрих Хайек и Морис Алле получили Нобелевскую"},
    ]

    paragraph_unit_keys, _ = real_document_validation_structural._build_source_paragraph_unit_membership(
        source_paragraphs,
        projection,
    )
    trace = real_document_validation_structural._collect_target_alignment_preview_trace(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
        target_indexes=[1274],
    )
    aligned_target_unit_keys = real_document_validation_structural._align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    )

    assert trace == [
        {
            "target_index": 1274,
            "target_preview": "там же.",
            "candidate_generated_previews": [
                {
                    "paragraph_id": "p1371",
                    "generated_preview": "америка в упадке?», atlantic monthly, октябрь 1995 г.",
                    "matches_target_preview": False,
                },
                {
                    "paragraph_id": "p1372",
                    "generated_preview": "там же.",
                    "matches_target_preview": True,
                }
            ],
            "match_result": "matched",
            "chosen_generated_paragraph_id": "p1372",
            "chosen_generated_preview": "там же.",
            "unit_keys": ["paragraph:p1372"],
        }
    ]
    assert aligned_target_unit_keys is not None
    assert aligned_target_unit_keys[1274] == frozenset({"paragraph:p1372"})


def test_collect_target_alignment_preview_trace_replays_saved_target_1372() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="John Naisbitt, Megatrends (New York: Warner Books, 1982), 183.",
            role="list",
            paragraph_id="p1480",
            source_index=1480,
            logical_index=1480,
            list_kind="ordered",
            list_level=0,
        ),
        ParagraphUnit(
            text="Paul Hawken, Blessed Unrest: How the Largest Movement in the World",
            role="list",
            paragraph_id="p1481",
            source_index=1481,
            logical_index=1481,
            list_kind="ordered",
            list_level=0,
        ),
        ParagraphUnit(
            text="came into being and why no one saw it coming (New York: Viking, 2007), 4.",
            role="body",
            paragraph_id="p1482",
            source_index=1482,
            logical_index=1482,
        ),
        ParagraphUnit(
            text="Michael Linton, interview with Jacqui Dunne, December 9, 2011.",
            role="list",
            paragraph_id="p1483",
            source_index=1483,
            logical_index=1483,
            list_kind="ordered",
            list_level=0,
        ),
        ParagraphUnit(
            text="Ibid.",
            role="list",
            paragraph_id="p1484",
            source_index=1484,
            logical_index=1484,
            list_kind="ordered",
            list_level=0,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-preview-trace-1372",
        projected_units=(
            StructuralUnit(
                unit_id="u_elsewhere",
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Elsewhere",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "source_registry": [
            {"paragraph_id": "p1480", "mapped_target_index": 1369},
            {"paragraph_id": "p1481", "mapped_target_index": 1370},
            {"paragraph_id": "p1482", "mapped_target_index": 1371},
            {"paragraph_id": "p1483", "mapped_target_index": None},
            {"paragraph_id": "p1484", "mapped_target_index": None},
        ],
        "unmapped_source_ids": ["p1483", "p1484"],
        "unmapped_target_indexes": [1372],
        "target_registry": [
            {"target_index": 1369, "mapped": True, "text_preview": "john naisbitt, megatrends (new york: warner books, 1982), 183."},
            {"target_index": 1370, "mapped": True, "text_preview": "paul hawken, blessed unrest: how the largest movement in the world"},
            {"target_index": 1371, "mapped": True, "text_preview": "came into being and why no one saw it coming (new york: viking, 2007), 4."},
            {"target_index": 1372, "mapped": False, "text_preview": "майкл линтон, интервью с джеки данн, 9 декабря 2011 г."},
            {"target_index": 1373, "mapped": True, "text_preview": "там же."},
        ],
    }
    generated_paragraph_registry = [
        {"paragraph_id": "p1480", "text": "1.   Джон Нейсбит, «Мегатренды» (Нью-Йорк: Warner Books, 1982), 183."},
        {"paragraph_id": "p1481", "text": "2.   Пол Хокен, «Благословенное беспокойство: как возникло крупнейшее в мире"},
        {"paragraph_id": "p1482", "text": "движение и почему никто этого не предвидел» (Нью-Йорк: Viking, 2007), 4."},
        {"paragraph_id": "p1483", "text": "3.   Майкл Линтон, интервью с Джеки Данн, 9 декабря 2011 г."},
        {"paragraph_id": "p1484", "text": "4.   Там же."},
    ]

    paragraph_unit_keys, _ = real_document_validation_structural._build_source_paragraph_unit_membership(
        source_paragraphs,
        projection,
    )
    trace = real_document_validation_structural._collect_target_alignment_preview_trace(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
        target_indexes=[1372],
    )
    aligned_target_unit_keys = real_document_validation_structural._align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    )

    assert trace == [
        {
            "target_index": 1372,
            "target_preview": "майкл линтон, интервью с джеки данн, 9 декабря 2011 г.",
            "candidate_generated_previews": [
                {
                    "paragraph_id": "p1480",
                    "generated_preview": "джон нейсбит, «мегатренды» (нью-йорк: warner books, 1982), 183.",
                    "matches_target_preview": False,
                },
                {
                    "paragraph_id": "p1481",
                    "generated_preview": "пол хокен, «благословенное беспокойство: как возникло крупнейшее в мире",
                    "matches_target_preview": False,
                },
                {
                    "paragraph_id": "p1482",
                    "generated_preview": "движение и почему никто этого не предвидел» (нью-йорк: viking, 2007), 4.",
                    "matches_target_preview": False,
                },
                {
                    "paragraph_id": "p1483",
                    "generated_preview": "майкл линтон, интервью с джеки данн, 9 декабря 2011 г.",
                    "matches_target_preview": True,
                }
            ],
            "match_result": "matched",
            "chosen_generated_paragraph_id": "p1483",
            "chosen_generated_preview": "майкл линтон, интервью с джеки данн, 9 декабря 2011 г.",
            "unit_keys": ["paragraph:p1483"],
        }
    ]
    assert aligned_target_unit_keys is not None
    assert aligned_target_unit_keys[1372] == frozenset({"paragraph:p1483"})


def test_collect_target_alignment_preview_trace_exposes_expected_fields() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="America Down? Atlantic Monthly, October 1995.",
            role="body",
            paragraph_id="p1371",
            source_index=1371,
            logical_index=1371,
        ),
        ParagraphUnit(
            text="Ibid.",
            role="list",
            paragraph_id="p1372",
            source_index=1372,
            logical_index=1372,
            list_kind="ordered",
            list_level=0,
        ),
        ParagraphUnit(
            text="There have been two exceptions.",
            role="list",
            paragraph_id="p1373",
            source_index=1373,
            logical_index=1373,
            list_kind="ordered",
            list_level=0,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-preview-trace-expected-fields",
        projected_units=(
            StructuralUnit(
                unit_id="u_elsewhere",
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Elsewhere",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "source_registry": [
            {"paragraph_id": "p1371", "mapped_target_index": 1273},
            {"paragraph_id": "p1372", "mapped_target_index": 1373},
            {"paragraph_id": "p1373", "mapped_target_index": 1275},
        ],
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [1274],
        "target_registry": [
            {"target_index": 1273, "mapped": True, "text_preview": "america down? atlantic monthly, october 1995."},
            {"target_index": 1274, "mapped": False, "text_preview": "там же."},
            {"target_index": 1275, "mapped": True, "text_preview": "there have been two exceptions: friedrich hayek and maurice allais both"},
        ],
    }
    generated_paragraph_registry = [
        {"paragraph_id": "p1371", "text": "Америка в упадке?», Atlantic Monthly, октябрь 1995 г."},
        {"paragraph_id": "p1372", "text": "11. Там же."},
        {"paragraph_id": "p1373", "text": "12. Было два исключения: Фридрих Хайек и Морис Алле получили Нобелевскую"},
    ]

    paragraph_unit_keys, _ = real_document_validation_structural._build_source_paragraph_unit_membership(
        source_paragraphs,
        projection,
    )
    trace = real_document_validation_structural._collect_target_alignment_preview_trace(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
        target_indexes=[1274],
    )

    assert len(trace) == 1
    trace_entry = trace[0]
    assert {
        "target_index",
        "target_preview",
        "match_result",
        "chosen_generated_paragraph_id",
        "chosen_generated_preview",
        "unit_keys",
    }.issubset(trace_entry)
    assert trace_entry["target_index"] == 1274
    assert trace_entry["target_preview"] == "там же."
    assert trace_entry["match_result"] == "matched"
    assert trace_entry["chosen_generated_paragraph_id"] == "p1372"
    assert trace_entry["chosen_generated_preview"] == "там же."
    assert trace_entry["unit_keys"] == ["paragraph:p1372"]


def test_derive_unit_aware_unmapped_fields_aligns_empty_source_window_body_target_127_shape() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="Requiem for a Dream",
            role="heading",
            paragraph_id="p0138",
            source_index=138,
            logical_index=138,
            heading_level=2,
        ),
        ParagraphUnit(
            text="He's a proud man.",
            role="body",
            paragraph_id="p0139",
            source_index=139,
            logical_index=139,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-empty-window-body-127",
        projected_units=(
            StructuralUnit(
                unit_id="u_elsewhere",
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Elsewhere",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "source_registry": [
            {"paragraph_id": "p0138", "mapped_target_index": 126},
            {"paragraph_id": "p0139", "mapped_target_index": 128},
        ],
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [127],
        "target_registry": [
            {"target_index": 126, "mapped": True, "text_preview": "реквием по мечте"},
            {
                "target_index": 127,
                "mapped": False,
                "text_preview": "поначалу испытываешь настоящий шок, когда видишь фреда, упаковывающего продукты в популярном супермаркете. согбенный, с…",
            },
            {
                "target_index": 128,
                "mapped": True,
                "text_preview": "фред — человек гордый; говорит, что пошел на эту работу по настоянию жены, которая хотела, чтобы он хоть чем-то занимал…",
            },
        ],
    }
    generated_paragraph_registry = [
        {
            "paragraph_id": "p0138",
            "text": "## РЕКВИЕМ ПО МЕЧТЕ\nПоначалу испытываешь настоящий шок, когда видишь Фреда, упаковывающего продукты в популярном супермаркете. Согбенный, с торсом, почти параллельным полу, с узловатыми, изуродованными артритом пальцами, он старательно укладывает тяжелые покупки в двойные пакеты.",
        },
        {
            "paragraph_id": "p0139",
            "text": "Фред — человек гордый; говорит, что пошел на эту работу по настоянию жены, которая хотела, чтобы он хоть чем-то занимался, а не сидел дома.",
        },
    ]

    paragraph_unit_keys, _ = real_document_validation_structural._build_source_paragraph_unit_membership(
        source_paragraphs,
        projection,
    )
    aligned_target_unit_keys = real_document_validation_structural._align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
    )

    assert aligned_target_unit_keys is not None
    assert aligned_target_unit_keys[127] == frozenset({"paragraph:p0138"})
    assert fields["structure_unit_unmapped_target_count"] == 0
    assert fields["unmapped_target_count_basis"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_aligns_empty_source_window_body_target_685_shape() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="The Hub Network",
            role="heading",
            paragraph_id="p0719",
            source_index=719,
            logical_index=719,
            heading_level=3,
        ),
        ParagraphUnit(
            text="10. The Hub is a place for purpose-driven people.",
            role="body",
            paragraph_id="p0720",
            source_index=720,
            logical_index=720,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-empty-window-body-685",
        projected_units=(
            StructuralUnit(
                unit_id="u_elsewhere",
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Elsewhere",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "source_registry": [
            {"paragraph_id": "p0719", "mapped_target_index": 684},
            {"paragraph_id": "p0720", "mapped_target_index": 686},
        ],
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [685],
        "target_registry": [
            {"target_index": 684, "mapped": True, "text_preview": "сеть the hub"},
            {
                "target_index": 685,
                "mapped": False,
                "text_preview": "the hub network — это социальное предприятие, работающее более чем в 26 странах мира. их миссия — «вдохновлять и поддер…",
            },
            {
                "target_index": 686,
                "mapped": True,
                "text_preview": "10 the hub — это место, где люди, объединенные общей целью, могут общаться и создавать решения для лучшего мира. «участ…",
            },
        ],
    }
    generated_paragraph_registry = [
        {
            "paragraph_id": "p0719",
            "text": "### СЕТЬ THE HUB\nThe Hub Network — это социальное предприятие, работающее более чем в 26 странах мира. Их миссия — «вдохновлять и поддерживать творческие и предприимчивые инициативы ради лучшего будущего».",
        },
        {
            "paragraph_id": "p0720",
            "text": "10 The Hub — это место, где люди, объединенные общей целью, могут общаться и создавать решения для лучшего мира. «Участники работают в The Hub».",
        },
    ]

    paragraph_unit_keys, _ = real_document_validation_structural._build_source_paragraph_unit_membership(
        source_paragraphs,
        projection,
    )
    aligned_target_unit_keys = real_document_validation_structural._align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
    )

    assert aligned_target_unit_keys is not None
    assert aligned_target_unit_keys[685] == frozenset({"paragraph:p0719"})
    assert fields["structure_unit_unmapped_target_count"] == 0
    assert fields["unmapped_target_count_basis"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_does_not_align_empty_source_window_numbered_ibid_case() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="America Down? Atlantic Monthly, October 1995.",
            role="body",
            paragraph_id="p1371",
            source_index=1371,
            logical_index=1371,
        ),
        ParagraphUnit(
            text="There have been two exceptions.",
            role="list",
            paragraph_id="p1373",
            source_index=1373,
            logical_index=1373,
            list_kind="ordered",
            list_level=0,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-empty-window-numbered-ibid-guard",
        projected_units=(
            StructuralUnit(
                unit_id="u_elsewhere",
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Elsewhere",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "source_registry": [
            {"paragraph_id": "p1371", "mapped_target_index": 1254},
            {"paragraph_id": "p1373", "mapped_target_index": 1256},
        ],
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [1255],
        "target_registry": [
            {"target_index": 1254, "mapped": True, "text_preview": "америке становится хуже?"},
            {"target_index": 1255, "mapped": False, "text_preview": "там же."},
            {"target_index": 1256, "mapped": True, "text_preview": "существовало два исключения."},
        ],
    }
    generated_paragraph_registry = [
        {"paragraph_id": "p1371", "text": "Америка в упадке?», Atlantic Monthly, октябрь 1995 г."},
        {"paragraph_id": "p1373", "text": "12. Было два исключения: Фридрих Хайек и Морис Алле получили Нобелевскую"},
    ]

    aligned_target_unit_keys = real_document_validation_structural._align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=real_document_validation_structural._build_source_paragraph_unit_membership(
            source_paragraphs,
            projection,
        )[0],
    )
    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
    )

    assert aligned_target_unit_keys is not None
    assert 1255 not in aligned_target_unit_keys
    assert fields["structure_unit_unmapped_target_count"] == 1
    assert fields["unmapped_target_count_basis"] == "legacy_paragraph"
    assert fields["unit_unmapped_target_gate_source"] == "legacy_paragraph"


def test_derive_unit_aware_unmapped_fields_infers_single_unmapped_target_from_source_registry_interval() -> None:
    source_paragraphs = [
        ParagraphUnit(text="Intro", role="body", paragraph_id="p-prev", source_index=0, logical_index=9),
        ParagraphUnit(text="Governance and We,", role="heading", paragraph_id="p0000", source_index=1, logical_index=10),
        ParagraphUnit(text="the Citizens", role="heading", paragraph_id="p0001", source_index=2, logical_index=11),
        ParagraphUnit(text="An Ancient Future?", role="heading", paragraph_id="p0002", source_index=3, logical_index=12),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-target-interval-collapse",
        projected_units=(
            StructuralUnit(
                unit_type="chapter_heading",
                logical_indexes=(10, 11, 12),
                canonical_text="Governance and We, the Citizens An Ancient Future?",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "unmapped_source_ids": ["p0000", "p0001"],
        "unmapped_target_indexes": [1],
        "source_registry": [
            {"paragraph_id": "p-prev", "mapped_target_index": 0},
            {"paragraph_id": "p0000", "mapped_target_index": None},
            {"paragraph_id": "p0001", "mapped_target_index": None},
            {"paragraph_id": "p0002", "mapped_target_index": 2},
        ],
        "target_registry": [
            {"target_index": 0, "mapped": True, "text_preview": "Intro"},
            {"target_index": 1, "mapped": False, "text_preview": "chapter eleven governance and we,"},
            {"target_index": 2, "mapped": True, "text_preview": "An Ancient Future?"},
        ],
    }

    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=None,
    )

    assert fields["structure_unit_unmapped_target_count"] == 1
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_recovers_multi_target_interval_gap() -> None:
    source_paragraphs = [
        ParagraphUnit(text="Prelude", role="body", paragraph_id="p-prev", source_index=0, logical_index=9),
        ParagraphUnit(
            text="This page intentionally left blank introduction",
            role="body",
            paragraph_id="p0057",
            source_index=57,
            logical_index=57,
        ),
        ParagraphUnit(
            text="From scarcity to prosperity",
            role="body",
            paragraph_id="p0058",
            source_index=58,
            logical_index=58,
        ),
        ParagraphUnit(
            text="Within a generation",
            role="body",
            paragraph_id="p0059",
            source_index=59,
            logical_index=59,
        ),
        ParagraphUnit(
            text="The foreman said",
            role="body",
            paragraph_id="p0060",
            source_index=60,
            logical_index=60,
        ),
        ParagraphUnit(text="Meanwhile", role="body", paragraph_id="p0061", source_index=61, logical_index=61),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-multi-target-interval-gap",
        projected_units=(
            StructuralUnit(
                unit_id="u_elsewhere",
                unit_type="chapter_heading",
                logical_indexes=(200, 201),
                canonical_text="Elsewhere",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )
    formatting_payload = {
        "source_registry": [
            {"paragraph_id": "p-prev", "mapped_target_index": 44},
            {"paragraph_id": "p0057", "mapped_target_index": None},
            {"paragraph_id": "p0058", "mapped_target_index": None},
            {"paragraph_id": "p0059", "mapped_target_index": None},
            {"paragraph_id": "p0060", "mapped_target_index": None},
            {"paragraph_id": "p0061", "mapped_target_index": 47},
        ],
        "unmapped_source_ids": ["p0057", "p0058", "p0059", "p0060"],
        "unmapped_target_indexes": [45, 46],
        "target_registry": [
            {"target_index": 44, "mapped": True, "text_preview": "Prelude"},
            {"target_index": 45, "mapped": False, "text_preview": "Within a generation"},
            {"target_index": 46, "mapped": False, "text_preview": "The foreman said"},
            {"target_index": 47, "mapped": True, "text_preview": "Meanwhile"},
        ],
    }

    paragraph_unit_keys, _ = real_document_validation_structural._build_source_paragraph_unit_membership(
        source_paragraphs,
        projection,
    )
    aligned_target_unit_keys = real_document_validation_structural._align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=None,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=None,
    )

    assert aligned_target_unit_keys is not None
    assert aligned_target_unit_keys[45] == frozenset(
        {"paragraph:p0057", "paragraph:p0058", "paragraph:p0059", "paragraph:p0060"}
    )
    assert aligned_target_unit_keys[46] == frozenset(
        {"paragraph:p0057", "paragraph:p0058", "paragraph:p0059", "paragraph:p0060"}
    )
    assert fields["structure_unit_unmapped_source_count"] == 0
    assert fields["structure_unit_unmapped_target_count"] == 0
    assert fields["unmapped_source_count_basis"] == "topology_unit"
    assert fields["unmapped_target_count_basis"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_cancels_aligned_subset_while_preserving_legacy_target_basis() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="This page intentionally left blank",
            role="body",
            paragraph_id="p0102",
            source_index=102,
            logical_index=102,
        ),
        ParagraphUnit(text="Chapter One", role="heading", paragraph_id="p0103", source_index=103, logical_index=103),
        ParagraphUnit(
            text="The Failure of Money",
            role="heading",
            paragraph_id="p0104",
            source_index=104,
            logical_index=104,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-partial-aligned-unmapped-subset",
        projected_units=(
            StructuralUnit(
                unit_type="chapter_heading",
                logical_indexes=(103, 104),
                canonical_text="Chapter One THE FAILURE OF MONEY",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )

    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload={
            "unmapped_source_ids": ["p0102", "p0103", "p0104"],
            "unmapped_target_indexes": [88, 89],
            "target_registry": [
                {"target_index": 88, "mapped": False, "text_preview": "эта страница намеренно оставлена пустой."},
                {"target_index": 89, "mapped": False, "text_preview": "глава первая крах денег"},
            ],
        },
        generated_paragraph_registry=[
            {
                "paragraph_id": "p0103",
                "merged_paragraph_ids": ["p0103", "p0104"],
                "text": "# Глава первая крах денег",
            },
        ],
    )

    assert fields["structure_unit_unmapped_source_count"] == 1
    assert fields["structure_unit_unmapped_target_count"] == 2
    assert fields["unmapped_source_count_basis"] == "topology_unit"
    assert fields["unmapped_target_count_basis"] == "legacy_paragraph"
    assert fields["unit_unmapped_source_gate_source"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "legacy_paragraph"


def test_derive_unit_aware_unmapped_fields_promotes_target_basis_when_all_unmapped_targets_align() -> None:
    source_paragraphs = [
        ParagraphUnit(text="Chapter One", role="heading", paragraph_id="p0103", source_index=103, logical_index=103),
        ParagraphUnit(
            text="The Failure of Money",
            role="heading",
            paragraph_id="p0104",
            source_index=104,
            logical_index=104,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-fully-aligned-unmapped-subset",
        projected_units=(
            StructuralUnit(
                unit_type="chapter_heading",
                logical_indexes=(103, 104),
                canonical_text="Chapter One THE FAILURE OF MONEY",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
            ),
        ),
    )

    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload={
            "unmapped_source_ids": ["p0103", "p0104"],
            "unmapped_target_indexes": [89],
            "target_registry": [
                {"target_index": 89, "mapped": False, "text_preview": "глава первая крах денег"},
            ],
        },
        generated_paragraph_registry=[
            {
                "paragraph_id": "p0103",
                "merged_paragraph_ids": ["p0103", "p0104"],
                "text": "# Глава первая крах денег",
            },
        ],
    )

    assert fields["structure_unit_unmapped_source_count"] == 0
    assert fields["structure_unit_unmapped_target_count"] == 0
    assert fields["unmapped_source_count_basis"] == "topology_unit"
    assert fields["unmapped_target_count_basis"] == "topology_unit"
    assert fields["unit_unmapped_source_gate_source"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_derive_unit_aware_unmapped_fields_suppresses_relation_sibling_covered_by_mapped_target_alignment() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="4 the flying fish: a new perspective on money 57 5 the future has arrived but isn't distributed evenly...",
            role="body",
            structural_role="toc_entry",
            paragraph_id="p0038",
            source_index=38,
            logical_index=38,
        ),
        ParagraphUnit(
            text="Yet!",
            role="body",
            structural_role="toc_entry",
            paragraph_id="p0039",
            source_index=39,
            logical_index=39,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-relation-sibling-suppression",
        projected_units=(
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(38,),
                canonical_text="4 The Flying Fish 57 5 The Future Has Arrived But Isn't Distributed Evenly",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
            ),
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(39,),
                canonical_text="Yet!",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
            ),
        ),
    )

    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload={
            "source_registry": [
                {
                    "paragraph_id": "p0038",
                    "relation_ids": ["rel_0002"],
                    "mapped_target_index": None,
                },
                {
                    "paragraph_id": "p0039",
                    "relation_ids": ["rel_0002"],
                    "mapped_target_index": 29,
                },
            ],
            "unmapped_source_ids": ["p0038"],
            "unmapped_target_indexes": [28],
            "target_registry": [
                {"target_index": 28, "mapped": False, "text_preview": "4 летучие рыбы: новый взгляд на деньги 57 5 будущее уже наступило"},
                {"target_index": 29, "mapped": True, "text_preview": "еще нет!"},
            ],
        },
        generated_paragraph_registry=[
            {"paragraph_id": "p0039", "text": "Еще нет!"},
        ],
    )

    assert fields["structure_unit_unmapped_source_count"] == 0
    assert fields["structure_unit_unmapped_target_count"] == 1
    assert fields["unmapped_source_count_basis"] == "topology_unit"
    assert fields["unmapped_target_count_basis"] == "legacy_paragraph"
    assert fields["unit_unmapped_source_gate_source"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "legacy_paragraph"


def test_derive_unit_aware_unmapped_fields_does_not_suppress_adjacent_fragment_without_shared_relation_id() -> None:
    source_paragraphs = [
        ParagraphUnit(
            text="4 the flying fish: a new perspective on money 57 5 the future has arrived but isn't distributed evenly...",
            role="body",
            structural_role="toc_entry",
            paragraph_id="p0038",
            source_index=38,
            logical_index=38,
        ),
        ParagraphUnit(
            text="Yet!",
            role="body",
            structural_role="toc_entry",
            paragraph_id="p0039",
            source_index=39,
            logical_index=39,
        ),
    ]
    projection = DocumentTopologyProjection(
        cache_key="topology-no-relation-sibling-suppression",
        projected_units=(
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(38,),
                canonical_text="4 The Flying Fish 57 5 The Future Has Arrived But Isn't Distributed Evenly",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
            ),
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(39,),
                canonical_text="Yet!",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
            ),
        ),
    )

    fields = real_document_validation_structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload={
            "source_registry": [
                {
                    "paragraph_id": "p0038",
                    "relation_ids": [],
                    "mapped_target_index": None,
                },
                {
                    "paragraph_id": "p0039",
                    "relation_ids": [],
                    "mapped_target_index": 29,
                },
            ],
            "unmapped_source_ids": ["p0038"],
            "unmapped_target_indexes": [28],
            "target_registry": [
                {"target_index": 28, "mapped": False, "text_preview": "4 летучие рыбы: новый взгляд на деньги 57 5 будущее уже наступило"},
                {"target_index": 29, "mapped": True, "text_preview": "еще нет!"},
            ],
        },
        generated_paragraph_registry=[
            {"paragraph_id": "p0039", "text": "Еще нет!"},
        ],
    )

    assert fields["structure_unit_unmapped_source_count"] == 1
    assert fields["structure_unit_unmapped_target_count"] == 1
    assert fields["unmapped_source_count_basis"] == "topology_unit"
    assert fields["unmapped_target_count_basis"] == "legacy_paragraph"
    assert fields["unit_unmapped_source_gate_source"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "legacy_paragraph"


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


def test_structural_passthrough_failure_includes_preparation_diagnostic_snapshot(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.4 sample")

    document_profile = SimpleNamespace(
        id="end-times-pdf-core",
        resolved_source_path=lambda project_root=None: source_path,
    )
    run_profile = SimpleNamespace(id="ui-parity-pdf-structural-recovery", image_mode="safe")

    class _StructureRepairReport:
        repaired_bullet_items = 0
        repaired_numbered_items = 0
        bounded_toc_regions = 1
        toc_body_boundary_repairs = 1
        heading_candidates_from_toc = 0
        remaining_isolated_marker_count = 0

    source_paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0),
        ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", source_index=1),
        ParagraphUnit(text="Introduction", role="heading", structural_role="body", heading_level=1, source_index=2),
    ]

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
            source_paragraphs,
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

    def _run_prepared_background_document(**kwargs):
        raise RuntimeError("blocked by quality gate")

    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_validation_processing_service",
        lambda event_log: SimpleNamespace(
            run_prepared_background_document=lambda **kwargs: (
                event_log.append(
                    {
                        "event_id": "structure_processing_outcome",
                        "context": {
                            "structure_ai_attempted": True,
                            "quality_gate_status": "blocked",
                            "quality_gate_reasons": ["structure_readiness_blocked_unsafe_best_effort_only"],
                            "readiness_status": "blocked_unsafe_best_effort_only",
                            "readiness_reasons": ["heading_count_far_below_toc_expectation"],
                            "ai_classified_count": 0,
                            "ai_heading_count": 0,
                        },
                    }
                ),
                _run_prepared_background_document(**kwargs),
            )[-1]
        ),
    )

    result = cast(
        dict[str, Any],
        run_structural_passthrough_validation(cast(Any, document_profile), cast(Any, run_profile)),
    )

    assert result["passed"] is False
    assert result["failed_checks"] == ["preparation_quality_gate_blocked"]
    snapshot = result["preparation_diagnostic_snapshot"]
    assert snapshot["paragraph_count"] == 3
    assert snapshot["heading_count"] == 1
    assert snapshot["toc_header_count"] == 1
    assert snapshot["toc_entry_count"] == 1
    assert snapshot["bounded_toc_region_count"] == 1
    assert snapshot["repaired_bullet_items"] == 0
    assert snapshot["repaired_numbered_items"] == 0
    assert snapshot["toc_body_boundary_repairs"] == 1
    assert snapshot["remaining_isolated_marker_count"] == 0
    assert snapshot["readiness_status"] == "blocked_unsafe_best_effort_only"
    assert snapshot["readiness_reasons"] == ["heading_count_far_below_toc_expectation"]
    assert snapshot["document_map_present"] is False
    assert snapshot["outline_coverage_ratio"] is None
    assert snapshot["front_matter_leaks"] == []
    assert snapshot["front_matter_body_advisories"] == []
    assert snapshot["targeted_recall_invoked"] is False
    assert snapshot["quality_gate_status"] == "blocked"
    assert snapshot["quality_gate_reasons"] == ["structure_readiness_blocked_unsafe_best_effort_only"]
    assert snapshot["structure_ai_attempted"] is True
    assert snapshot["ai_first_degraded"] is False
    assert snapshot["fallback_stage"] == ""
    assert snapshot["fallback_reason"] == ""
    assert snapshot["document_map_status"] == "not_requested"
    assert snapshot["document_map_status_reason"] == ""
    assert snapshot["ai_classified_count"] == 0
    assert snapshot["ai_heading_count"] == 0
    assert snapshot["semantic_block_count"] == 1
    assert snapshot["first_block_target_chars"] == len("Contents\n\nChapter 1........ 12\n\n# Introduction")
    assert snapshot["first_block_has_toc"] is True
    assert snapshot["first_block_has_epigraph"] is False
    assert snapshot["first_block_has_body_start"] is True
    assert snapshot["first_block_has_isolated_marker"] is False


def test_structural_passthrough_failure_derives_snapshot_block_status_from_preparation_error(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.4 sample")

    document_profile = SimpleNamespace(id="end-times-pdf-core", resolved_source_path=lambda project_root=None: source_path)
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

    document_profile = SimpleNamespace(id="end-times-pdf-core", resolved_source_path=lambda project_root=None: source_path)
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


def test_structural_passthrough_prefers_saved_quality_report_authority_fields(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project-root"
    source_dir = project_root / "tests" / "sources"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "sample.pdf"
    source_path.write_bytes(b"%PDF-1.4 sample")

    quality_report_path = project_root / ".run" / "quality_reports" / "saved_quality_report.json"
    quality_report_path.parent.mkdir(parents=True, exist_ok=True)
    quality_report_path.write_text(
        json.dumps(
            {
                "quality_status": "pass",
                "gate_reasons": [],
                "page_placeholder_heading_concat_count": 0,
                "page_placeholder_heading_concat_source": "legacy_markdown",
                "page_placeholder_heading_concat_classification": "display_hygiene",
                "raw_page_placeholder_heading_concat_count": 1,
                "false_fragment_heading_count": 0,
                "false_fragment_heading_gate_source": "entry_assembly",
                "raw_false_fragment_heading_count": 2,
                "scripture_reference_heading_count": 1,
                "suspicious_heading_repetition_count": 0,
                "residual_bullet_glyph_count": 0,
                "residual_bullet_glyph_gate_source": "legacy_markdown",
                "raw_residual_bullet_glyph_count": 0,
                "list_fragment_regression_count": 0,
                "list_fragment_regression_gate_source": "topology_projection",
                "raw_list_fragment_regression_count": 1,
                "toc_body_concat_detected": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    document_profile = SimpleNamespace(id="end-times-pdf-core", resolved_source_path=lambda project_root=None: source_path)
    run_profile = SimpleNamespace(id="ui-parity-pdf-structural-recovery", image_mode="safe")

    class _StructureRepairReport:
        repaired_bullet_items = 4
        repaired_numbered_items = 5
        bounded_toc_regions = 1
        toc_body_boundary_repairs = 1
        heading_candidates_from_toc = 7
        remaining_isolated_marker_count = 0

    def _resolution_payload(**values):
        return SimpleNamespace(**values, to_dict=lambda: dict(values))

    source_paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0),
        ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", source_index=1),
        ParagraphUnit(text="Introduction", role="heading", structural_role="body", heading_level=1, source_index=2),
    ]

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
            source_paragraphs,
            [],
            ParagraphBoundaryNormalizationReport(0, 0, 0, 0),
            [],
            RelationNormalizationReport(1, {"toc_region": 1}, 0),
            _cleanup_report(),
            _StructureRepairReport(),
        ),
    )
    monkeypatch.setattr(real_document_validation_structural, "_build_extraction_checks", lambda document_profile, metrics: [])
    monkeypatch.setattr(real_document_validation_structural, "_build_structural_checks", lambda **kwargs: [])

    def _run_prepared_background_document(**kwargs):
        runtime = kwargs["runtime"]
        runtime["state"]["latest_docx_bytes"] = b"PK\x03\x04output"
        runtime["state"]["latest_markdown"] = (
            "Иисус постоянно говорит о том, как важно распознавать знамения.\n\n"
            "## Великую скорбь\n\n"
            "они могли устоять до конца.\n\n"
            "Поразительно, но все петли следуют одной и той же схеме: 1.\n"
            "Духовные существа восстают против Бога."
        )
        return "succeeded", SimpleNamespace(
            uploaded_file_bytes=b"PK\x03\x04normalized-source",
            source_text="text",
            paragraphs=source_paragraphs,
            image_assets=[],
            jobs=[{"job_kind": "llm"}],
        )

    monkeypatch.setattr(
        real_document_validation_structural,
        "_build_validation_processing_service",
        lambda event_log: SimpleNamespace(
            run_prepared_background_document=lambda **kwargs: (
                event_log.append(
                    {
                        "event_id": "structure_processing_outcome",
                        "context": {
                            "quality_gate_status": "pass",
                            "quality_gate_reasons": [],
                            "readiness_status": "ready",
                        },
                    }
                ),
                event_log.append(
                    {
                        "event_id": "block_plan_summary",
                        "context": {
                            "block_count": 3,
                            "llm_block_count": 2,
                            "passthrough_block_count": 1,
                            "first_block_target_chars": [3891, 946, 935],
                        },
                    }
                ),
                event_log.append(
                    {
                        "event_id": "quality_report_saved",
                        "context": {"artifact_path": ".run/quality_reports/saved_quality_report.json"},
                    }
                ),
                _run_prepared_background_document(**kwargs),
            )[-1]
        ),
    )

    result = cast(
        dict[str, Any],
        run_structural_passthrough_validation(cast(Any, document_profile), cast(Any, run_profile)),
    )

    metrics = cast(dict[str, Any], result["metrics"])
    snapshot = cast(dict[str, Any], result["preparation_diagnostic_snapshot"])

    assert metrics["false_fragment_heading_count"] == 0
    assert metrics["false_fragment_heading_gate_source"] == "entry_assembly"
    assert metrics["raw_false_fragment_heading_count"] == 2
    assert metrics["page_placeholder_heading_concat_count"] == 0
    assert metrics["page_placeholder_heading_concat_source"] == "legacy_markdown"
    assert metrics["page_placeholder_heading_concat_classification"] == "display_hygiene"
    assert metrics["raw_page_placeholder_heading_concat_count"] == 1
    assert metrics["bullet_heading_count"] == 0
    assert metrics["bullet_heading_gate_source"] == "legacy_markdown"
    assert metrics["bullet_heading_classification"] == "markdown_gate"
    assert metrics["raw_bullet_heading_count"] == 0
    assert metrics["scripture_reference_heading_count"] == 1
    assert metrics["residual_bullet_glyph_count"] == 0
    assert metrics["residual_bullet_glyph_gate_source"] == "legacy_markdown"
    assert metrics["residual_bullet_glyph_classification"] == "display_hygiene"
    assert metrics["raw_residual_bullet_glyph_count"] == 0
    assert metrics["list_fragment_regression_count"] == 0
    assert metrics["list_fragment_regression_gate_source"] == "topology_projection"
    assert metrics["raw_list_fragment_regression_count"] == 1
    assert metrics["mixed_script_term_count"] == 0
    assert metrics["mixed_script_term_gate_source"] == "legacy_markdown"
    assert metrics["mixed_script_term_classification"] == "non_structural_hygiene"
    assert metrics["raw_mixed_script_term_count"] == 0
    assert metrics["theology_style_deterministic_issue_count"] == 0
    assert metrics["theology_style_deterministic_issue_source"] == "legacy_markdown"
    assert metrics["theology_style_deterministic_issue_classification"] == "domain_style_advisory"
    assert metrics["raw_theology_style_deterministic_issue_count"] == 0
    assert metrics["translation_quality_report_path"] == str(quality_report_path.resolve())
    assert snapshot["false_fragment_heading_count"] == 0
    assert snapshot["false_fragment_heading_gate_source"] == "entry_assembly"
    assert snapshot["raw_false_fragment_heading_count"] == 2
    assert snapshot["page_placeholder_heading_concat_count"] == 0
    assert snapshot["page_placeholder_heading_concat_source"] == "legacy_markdown"
    assert snapshot["page_placeholder_heading_concat_classification"] == "display_hygiene"
    assert snapshot["raw_page_placeholder_heading_concat_count"] == 1
    assert snapshot["bullet_heading_count"] == 0
    assert snapshot["bullet_heading_gate_source"] == "legacy_markdown"
    assert snapshot["bullet_heading_classification"] == "markdown_gate"
    assert snapshot["raw_bullet_heading_count"] == 0
    assert snapshot["residual_bullet_glyph_count"] == 0
    assert snapshot["residual_bullet_glyph_gate_source"] == "legacy_markdown"
    assert snapshot["residual_bullet_glyph_classification"] == "display_hygiene"
    assert snapshot["raw_residual_bullet_glyph_count"] == 0
    assert snapshot["list_fragment_regression_count"] == 0
    assert snapshot["list_fragment_regression_gate_source"] == "topology_projection"
    assert snapshot["raw_list_fragment_regression_count"] == 1
    assert snapshot["mixed_script_term_count"] == 0
    assert snapshot["mixed_script_term_gate_source"] == "legacy_markdown"
    assert snapshot["mixed_script_term_classification"] == "non_structural_hygiene"
    assert snapshot["raw_mixed_script_term_count"] == 0
    assert snapshot["theology_style_deterministic_issue_count"] == 0
    assert snapshot["theology_style_deterministic_issue_source"] == "legacy_markdown"
    assert snapshot["theology_style_deterministic_issue_classification"] == "domain_style_advisory"
    assert snapshot["raw_theology_style_deterministic_issue_count"] == 0


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
