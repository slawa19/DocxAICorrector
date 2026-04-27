import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import processing_runtime
from generation import ensure_pandoc_available
from models import LayoutArtifactCleanupReport, ParagraphBoundaryNormalizationReport, RelationNormalizationReport


def _cleanup_report() -> LayoutArtifactCleanupReport:
    return LayoutArtifactCleanupReport(0, 0, 0, 0, 0, 0, cleanup_applied=True)


from real_document_validation_profiles import load_validation_registry
import real_document_validation_structural
from real_document_validation_structural import evaluate_extraction_profile, run_structural_passthrough_validation


REGISTRY = load_validation_registry()
STRUCTURAL_RUN_PROFILE = REGISTRY.get_run_profile("structural-passthrough-default")


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

    result = cast(dict[str, Any], run_structural_passthrough_validation(document_profile, STRUCTURAL_RUN_PROFILE))

    assert result["validation_tier"] == "structural"
    assert result["run_profile_id"] == STRUCTURAL_RUN_PROFILE.id
    assert result["runtime_config"]["effective"]["image_mode"] == STRUCTURAL_RUN_PROFILE.image_mode
    assert "source_file" not in result
    assert "runtime_configuration" not in result
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
            ),
            ui_defaults=_resolution_payload(
                chunk_size=6000,
                image_mode="safe",
                keep_all_image_variants=False,
                model="gpt-5.4",
                max_retries=1,
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
            ),
            ui_defaults=_resolution_payload(
                chunk_size=6000,
                image_mode="safe",
                keep_all_image_variants=False,
                model="gpt-5.4",
                max_retries=1,
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
            ),
            ui_defaults=_resolution_payload(
                chunk_size=6000,
                image_mode="safe",
                keep_all_image_variants=False,
                model="gpt-5.4",
                max_retries=1,
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
    assert captured["metrics"]["max_unmapped_target_paragraphs"] == 1
