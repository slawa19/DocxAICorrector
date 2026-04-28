import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import processing_runtime
from generation import ensure_pandoc_available
from models import DocumentBlock, LayoutArtifactCleanupReport, ParagraphBoundaryNormalizationReport, ParagraphUnit, RelationNormalizationReport


def _cleanup_report() -> LayoutArtifactCleanupReport:
    return LayoutArtifactCleanupReport(0, 0, 0, 0, 0, 0, cleanup_applied=True)


from real_document_validation_profiles import load_validation_registry
import real_document_validation_structural
from real_document_validation_structural import (
    evaluate_extraction_profile,
    evaluate_structural_preparation_diagnostic,
    run_structural_passthrough_validation,
)


REGISTRY = load_validation_registry()
STRUCTURAL_RUN_PROFILE = REGISTRY.get_run_profile("structural-passthrough-default")


def _resolve_structural_run_profile(document_profile):
    run_profile_id = getattr(document_profile, "structural_run_profile", None) or STRUCTURAL_RUN_PROFILE.id
    return REGISTRY.get_run_profile(run_profile_id)


def test_registry_includes_end_times_pdf_regression_profile() -> None:
    profile_ids = {profile.id for profile in REGISTRY.documents}

    assert "end-times-pdf-core" in profile_ids


def test_end_times_pdf_structural_run_profile_is_generic_structural_recovery() -> None:
    document_profile = REGISTRY.get_document_profile("end-times-pdf-core")
    run_profile = _resolve_structural_run_profile(document_profile)

    assert run_profile.id == "ui-parity-pdf-structural-recovery"
    assert document_profile.structural_expected_result == "fail"
    assert document_profile.structural_expected_failed_checks == ("unmapped_source_threshold",)
    assert document_profile.structural_optional_failed_checks == ()


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

    result = evaluate_structural_preparation_diagnostic(document_profile, run_profile)

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


def _skip_if_legacy_doc_conversion_unavailable(source_path: Path) -> None:
    if source_path.suffix.lower() != ".doc":
        return
    if processing_runtime.legacy_doc_conversion_available():
        return
    pytest.skip(f"legacy DOC auto-conversion unavailable in current runtime: {source_path}")


def _skip_if_structural_passthrough_runtime_unavailable() -> None:
    try:
        ensure_pandoc_available()
    except RuntimeError as exc:
        pytest.skip(f"structural passthrough runtime unavailable: {exc}")


@pytest.mark.parametrize("document_profile", REGISTRY.documents, ids=[profile.id for profile in REGISTRY.documents])
def test_corpus_extraction(document_profile) -> None:
    source_path = document_profile.resolved_source_path()
    if not source_path.exists():
        pytest.skip(f"missing real-document source: {source_path}")
    _skip_if_legacy_doc_conversion_unavailable(source_path)

    result = cast(dict[str, Any], evaluate_extraction_profile(document_profile))

    assert result["validation_tier"] == "extraction"
    assert result["document_profile_id"] == document_profile.id
    assert result["passed"] is True, json.dumps(result, ensure_ascii=False, indent=2)


@pytest.mark.parametrize("document_profile", REGISTRY.documents, ids=[profile.id for profile in REGISTRY.documents])
def test_corpus_structural_passthrough(document_profile) -> None:
    source_path = document_profile.resolved_source_path()
    if not source_path.exists():
        pytest.skip(f"missing real-document source: {source_path}")
    _skip_if_legacy_doc_conversion_unavailable(source_path)
    _skip_if_structural_passthrough_runtime_unavailable()

    run_profile = _resolve_structural_run_profile(document_profile)

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
        lambda event_log: SimpleNamespace(run_prepared_background_document=_run_prepared_background_document),
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
        "require_pdf_conversion_satisfied": True,
        "bullet_heading_count": 0,
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
    monkeypatch.setattr(real_document_validation_structural, "_load_formatting_diagnostics_payloads", lambda paths: [formatting_payload])
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
    assert result["preparation_diagnostic_snapshot"] == {
        "paragraph_count": 5,
        "heading_count": 1,
        "toc_header_count": 1,
        "toc_entry_count": 1,
        "bounded_toc_region_count": 1,
        "repaired_bullet_items": 4,
        "repaired_numbered_items": 5,
        "toc_body_boundary_repairs": 1,
        "remaining_isolated_marker_count": 0,
        "readiness_status": "ready",
        "readiness_reasons": [],
        "quality_gate_status": "pass",
        "quality_gate_reasons": [],
        "structure_ai_attempted": False,
        "ai_classified_count": 0,
        "ai_heading_count": 0,
        "semantic_block_count": 1,
        "first_block_target_chars": 3891,
        "first_block_has_toc": True,
        "first_block_has_epigraph": True,
        "first_block_has_body_start": True,
        "first_block_has_isolated_marker": True,
    }
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
    monkeypatch.setattr(real_document_validation_structural, "apply_runtime_resolution_to_app_config", lambda app_config, resolution: {})
    monkeypatch.setattr(real_document_validation_structural, "_snapshot_formatting_diagnostics_paths", lambda: set())
    monkeypatch.setattr(real_document_validation_structural, "_collect_new_formatting_diagnostics_paths", lambda before, after: [])
    monkeypatch.setattr(real_document_validation_structural, "_load_formatting_diagnostics_payloads", lambda paths: [])
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
            quality_gate_status="pass",
            quality_gate_reasons=(),
            structure_validation_report=SimpleNamespace(readiness_status="ready", readiness_reasons=()),
            structure_ai_attempted=True,
            ai_classified_count=12,
            ai_heading_count=4,
        )

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
    assert result["preparation_diagnostic_snapshot"] == {
        "paragraph_count": 3,
        "heading_count": 1,
        "toc_header_count": 1,
        "toc_entry_count": 1,
        "bounded_toc_region_count": 1,
        "repaired_bullet_items": 0,
        "repaired_numbered_items": 0,
        "toc_body_boundary_repairs": 1,
        "remaining_isolated_marker_count": 0,
        "readiness_status": "blocked_unsafe_best_effort_only",
        "readiness_reasons": ["heading_count_far_below_toc_expectation"],
        "quality_gate_status": "blocked",
        "quality_gate_reasons": ["structure_readiness_blocked_unsafe_best_effort_only"],
        "structure_ai_attempted": True,
        "ai_classified_count": 0,
        "ai_heading_count": 0,
        "semantic_block_count": 1,
        "first_block_target_chars": len("Contents\n\nChapter 1........ 12\n\n# Introduction"),
        "first_block_has_toc": True,
        "first_block_has_epigraph": False,
        "first_block_has_body_start": True,
        "first_block_has_isolated_marker": False,
    }


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
                    "Причины: toc_like_sequence_without_bounded_region, structure_recognition_noop_on_high_risk"
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
