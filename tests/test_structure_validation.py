import json
from pathlib import Path
from types import SimpleNamespace

import docxaicorrector.structure.validation as structure_validation
import docxaicorrector.validation.structural as structural_validation_runtime
from docxaicorrector.core.models import DocumentMap
from docxaicorrector.core.models import DocumentMapTocRegion
from docxaicorrector.core.models import DocumentTopologyOperation
from docxaicorrector.core.models import DocumentTopologyProjection
from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.core.models import StructuralUnit
from docxaicorrector.structure.validation import StructureValidationReport, validate_structure_quality


def _paragraph(
    index: int,
    text: str,
    *,
    role: str = "body",
    structural_role: str = "body",
    heading_source: str | None = None,
    paragraph_alignment: str | None = None,
    list_kind: str | None = None,
    attached_to_asset_id: str | None = None,
) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role=role,
        structural_role=structural_role,
        heading_source=heading_source,
        paragraph_alignment=paragraph_alignment,
        list_kind=list_kind,
        attached_to_asset_id=attached_to_asset_id,
        source_index=index,
    )


def _config(**overrides):
    base = {
        "structure_validation_toc_like_sequence_min_length": 4,
        "structure_validation_min_paragraphs_for_auto_gate": 40,
        "structure_validation_min_explicit_heading_density": 0.003,
        "structure_validation_max_suspicious_short_body_ratio_without_escalation": 0.05,
        "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation": 0.03,
        "structure_validation_forbid_heading_only_collapse": True,
    }
    base.update(overrides)
    return base


def test_validate_structure_quality_does_not_escalate_low_risk_document():
    paragraphs = [
        _paragraph(0, "Chapter 1", role="heading", heading_source="explicit"),
        _paragraph(1, "This is a long enough body paragraph with many ordinary words and extra context."),
        _paragraph(2, "Another ordinary body paragraph with stable narrative structure and additional detail here."),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.escalation_recommended is False
    assert report.escalation_reasons == ()
    assert report.readiness_status == "ready"


def test_validate_structure_quality_triggers_on_low_explicit_heading_density():
    paragraphs = [_paragraph(index, f"Body paragraph number {index} with plain text.") for index in range(50)]

    report = validate_structure_quality(
        paragraphs=paragraphs,
        app_config=_config(structure_validation_min_explicit_heading_density=0.1),
    )

    assert report.escalation_recommended is True
    assert "low_explicit_heading_density" in report.escalation_reasons


def test_validate_structure_quality_triggers_on_suspicious_short_body_ratio():
    paragraphs = [_paragraph(index, f"Section {index}") for index in range(10)]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.escalation_recommended is True
    assert "high_suspicious_short_body_ratio" in report.escalation_reasons


def test_validate_structure_quality_triggers_on_all_caps_or_centered_body_ratio():
    paragraphs = [
        _paragraph(0, "INTRODUCTION", paragraph_alignment="center"),
        _paragraph(1, "CHAPTER ONE"),
        _paragraph(2, "Regular body paragraph with enough words to be ordinary."),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.escalation_recommended is True
    assert "high_all_caps_or_centered_body_ratio" in report.escalation_reasons


def test_validate_structure_quality_triggers_on_toc_like_region():
    paragraphs = [
        _paragraph(0, "Introduction"),
        _paragraph(1, "Chapter One"),
        _paragraph(2, "Chapter Two"),
        _paragraph(3, "Appendix"),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.escalation_recommended is True
    assert "toc_like_sequence_detected" in report.escalation_reasons
    assert report.readiness_status == "blocked_unsafe_best_effort_only"


def test_validate_structure_quality_marks_large_front_matter_block_risk():
    paragraphs = [
        _paragraph(0, "Содержание", structural_role="toc_header"),
        _paragraph(1, "Глава 1........ 10", structural_role="toc_entry"),
        _paragraph(2, "Глава 2........ 20", structural_role="toc_entry"),
        _paragraph(3, "Марк 13:13", structural_role="epigraph"),
        _paragraph(4, "Введение", role="heading", heading_source="heuristic", structural_role="body"),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.large_front_matter_block_risk is True
    assert report.toc_region_bounded_count == 1
    assert report.readiness_status == "ready_with_warnings"
    assert "large_front_matter_block_risk" not in report.readiness_reasons


def test_validate_structure_quality_counts_hinted_toc_region_and_hinted_heading_for_front_matter():
    paragraphs = [
        _paragraph(0, "Содержание", structural_role="body"),
        _paragraph(1, "Глава 1........ 10", structural_role="body"),
        _paragraph(2, "Глава 2........ 20", structural_role="body"),
        _paragraph(3, "Марк 13:13", structural_role="epigraph"),
        _paragraph(4, "Введение", structural_role="body"),
    ]
    paragraphs[0].heuristic_structural_role_hint = "toc_header"
    paragraphs[1].heuristic_structural_role_hint = "toc_entry"
    paragraphs[2].heuristic_structural_role_hint = "toc_entry"
    paragraphs[4].heuristic_role_hint = "heading"
    paragraphs[4].heuristic_heading_level_hint = 2

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config(), phase="pre_ai_diagnostic")

    assert report.large_front_matter_block_risk is True
    assert report.toc_region_bounded_count == 1
    assert report.expected_heading_candidates_from_toc == 2
    assert report.readiness_status == "ready"
    assert "large_front_matter_block_risk" not in report.readiness_reasons


def test_validate_structure_quality_post_ai_readiness_does_not_treat_structural_hints_as_final_toc():
    paragraphs = [
        _paragraph(0, "Содержание", structural_role="body"),
        _paragraph(1, "Глава 1........ 10", structural_role="body"),
        _paragraph(2, "Глава 2........ 20", structural_role="body"),
        _paragraph(3, "Первый обычный абзац.", structural_role="body"),
    ]
    paragraphs[0].heuristic_structural_role_hint = "toc_header"
    paragraphs[1].heuristic_structural_role_hint = "toc_entry"
    paragraphs[2].heuristic_structural_role_hint = "toc_entry"

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config(), phase="post_ai_readiness")

    assert report.toc_region_bounded_count == 0
    assert report.expected_heading_candidates_from_toc == 0


def test_validate_structure_quality_post_ai_readiness_does_not_count_heuristic_headings_as_final_authority():
    paragraphs = [_paragraph(index, f"Paragraph {index} with enough words to count as body text.") for index in range(120)]
    paragraphs.extend(
        [
            _paragraph(1000, "Heading A", role="heading", heading_source="heuristic"),
            _paragraph(1001, "Heading B", role="heading", heading_source="heuristic"),
        ]
    )

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config(), phase="post_ai_readiness")

    assert report.escalation_recommended is True
    assert "heading_only_collapse_risk" in report.escalation_reasons


def test_validate_structure_quality_post_ai_readiness_counts_ai_headings_for_toc_expectation():
    paragraphs = [
        _paragraph(0, "Contents", structural_role="toc_header"),
        *[_paragraph(index, f"Chapter {index}........ {index * 10}", structural_role="toc_entry") for index in range(1, 7)],
        *[
            _paragraph(100 + index, f"Chapter {index}", role="heading", structural_role="heading", heading_source="ai")
            for index in range(1, 7)
        ],
        _paragraph(200, "Regular body paragraph with enough words to avoid short-body risk escalation."),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config(), phase="post_ai_readiness")

    assert report.expected_heading_candidates_from_toc == 6
    assert report.toc_region_bounded_count == 1
    assert "heading_count_far_below_toc_expectation" not in report.readiness_reasons
    assert "heading_only_collapse_risk" not in report.escalation_reasons


def test_validate_structure_quality_post_ai_readiness_ignores_ai_list_marker_classifications():
    paragraphs = [
        _paragraph(0, "1.", role="list", structural_role="list", heading_source="ai"),
        _paragraph(1, "Regular body paragraph with enough words to avoid short-body risk escalation."),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config(), phase="post_ai_readiness")

    assert report.isolated_marker_paragraph_count == 0
    assert "isolated_list_markers_remaining" not in report.readiness_reasons


def test_validate_structure_quality_ignores_year_tail_as_isolated_marker():
    paragraphs = [
        _paragraph(0, "2011."),
        _paragraph(1, "Regular body paragraph with enough words to avoid short-body risk escalation."),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config(), phase="post_ai_readiness")

    assert report.isolated_marker_paragraph_count == 0
    assert "isolated_list_markers_remaining" not in report.readiness_reasons


def test_validate_structure_quality_blocks_large_front_matter_without_bounded_toc():
    paragraphs = [
        _paragraph(0, "Содержание", structural_role="toc_header"),
        _paragraph(1, "Глава 1........ 10", structural_role="toc_entry"),
        _paragraph(2, "Марк 13:13", structural_role="epigraph"),
        _paragraph(3, "Введение", role="heading", heading_source="heuristic", structural_role="body"),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.large_front_matter_block_risk is True
    assert report.toc_region_bounded_count == 0
    assert report.readiness_status == "blocked_unsafe_best_effort_only"
    assert "large_front_matter_block_risk" in report.readiness_reasons


def test_validate_structure_quality_heading_only_collapse_boundary_119_and_3():
    paragraphs = [_paragraph(index, f"Paragraph {index} with enough words to count as body text.") for index in range(119)]
    paragraphs.extend(
        [
            _paragraph(1000, "Heading A", role="heading", heading_source="explicit"),
            _paragraph(1001, "Heading B", role="heading", heading_source="explicit"),
            _paragraph(1002, "Heading C", role="heading", heading_source="explicit"),
        ]
    )

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert "heading_only_collapse_risk" not in report.escalation_reasons


def test_validate_structure_quality_heading_only_collapse_boundary_120_and_2():
    paragraphs = [_paragraph(index, f"Paragraph {index} with enough words to count as body text.") for index in range(120)]
    paragraphs.extend(
        [
            _paragraph(1000, "Heading A", role="heading", heading_source="explicit"),
            _paragraph(1001, "Heading B", role="heading", heading_source="explicit"),
        ]
    )

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.escalation_recommended is True
    assert "heading_only_collapse_risk" in report.escalation_reasons


def test_write_structure_validation_debug_artifact_writes_json_payload(tmp_path, monkeypatch):
    diagnostics_dir = tmp_path / ".run" / "structure_validation"
    monkeypatch.setattr(structure_validation, "_STRUCTURE_VALIDATION_DEBUG_DIR", diagnostics_dir)
    report = StructureValidationReport(
        paragraph_count=120,
        nonempty_paragraph_count=118,
        explicit_heading_count=2,
        heuristic_heading_count=5,
        suspicious_short_body_count=9,
        all_caps_body_count=3,
        centered_body_count=1,
        toc_like_sequence_count=1,
        ambiguous_paragraph_count=13,
        explicit_heading_density=0.0169,
        suspicious_short_body_ratio=0.0763,
        all_caps_or_centered_body_ratio=0.0339,
        escalation_recommended=True,
        escalation_reasons=(
            "high_suspicious_short_body_ratio",
            "toc_like_sequence_detected",
        ),
        isolated_marker_paragraph_count=2,
        large_front_matter_block_risk=False,
        toc_region_bounded_count=0,
        expected_heading_candidates_from_toc=4,
        structure_quality_risk_level="high",
        readiness_status="blocked_unsafe_best_effort_only",
        readiness_reasons=("toc_like_sequence_without_bounded_region",),
        document_map_present=True,
        outline_coverage_ratio=0.75,
    )

    artifact_path = structure_validation.write_structure_validation_debug_artifact(
        report=report,
        app_config={
            "structure_recognition_mode": "always",
            "structure_recognition_model": "gpt-5.4",
        },
    )

    artifact_file = Path(artifact_path)
    assert artifact_file.exists()
    assert artifact_file.parent == diagnostics_dir
    assert artifact_file.name.startswith("gate_report_")
    payload = json.loads(artifact_file.read_text(encoding="utf-8"))
    assert payload == {
        "mode": "always",
        "model": "gpt-5.4",
        "paragraph_count": 120,
        "nonempty_paragraph_count": 118,
        "explicit_heading_count": 2,
        "heuristic_heading_count": 5,
        "suspicious_short_body_count": 9,
        "all_caps_body_count": 3,
        "centered_body_count": 1,
        "toc_like_sequence_count": 1,
        "ambiguous_paragraph_count": 13,
        "explicit_heading_density": 0.0169,
        "suspicious_short_body_ratio": 0.0763,
        "all_caps_or_centered_body_ratio": 0.0339,
        "escalation_recommended": True,
        "escalation_reasons": [
            "high_suspicious_short_body_ratio",
            "toc_like_sequence_detected",
        ],
        "isolated_marker_paragraph_count": 2,
        "large_front_matter_block_risk": False,
        "toc_region_bounded_count": 0,
        "expected_heading_candidates_from_toc": 4,
        "structure_quality_risk_level": "high",
        "readiness_status": "blocked_unsafe_best_effort_only",
        "readiness_reasons": ["toc_like_sequence_without_bounded_region"],
        "document_map_present": True,
        "outline_coverage_ratio": 0.75,
        "structure_repair_report": None,
    }


def test_validate_structure_quality_preserves_advisory_post_ai_fields():
    paragraphs = [
        _paragraph(0, "Chapter 1", role="heading", heading_source="ai"),
        _paragraph(1, "Regular paragraph with enough words to avoid short-body risk escalation."),
    ]

    report = validate_structure_quality(
        paragraphs=paragraphs,
        app_config=_config(),
        document_map_present=True,
        outline_coverage_ratio=0.5,
    )

    assert report.document_map_present is True
    assert report.outline_coverage_ratio == 0.5


def test_validate_structure_quality_keeps_outline_coverage_ratio_advisory_only_for_gating():
    paragraphs = [
        _paragraph(0, "Chapter 1", role="heading", heading_source="ai"),
        _paragraph(1, "Regular paragraph with enough words to avoid short-body risk escalation."),
        _paragraph(2, "Another ordinary body paragraph with stable narrative structure and additional detail here."),
    ]

    baseline = validate_structure_quality(
        paragraphs=paragraphs,
        app_config=_config(),
        document_map_present=False,
        outline_coverage_ratio=None,
    )
    low_coverage = validate_structure_quality(
        paragraphs=paragraphs,
        app_config=_config(),
        document_map_present=True,
        outline_coverage_ratio=0.0,
    )

    assert baseline.escalation_recommended is False
    assert low_coverage.escalation_recommended is False
    assert baseline.escalation_reasons == low_coverage.escalation_reasons
    assert baseline.readiness_status == low_coverage.readiness_status == "ready"
    assert baseline.readiness_reasons == low_coverage.readiness_reasons == ()
    assert low_coverage.document_map_present is True
    assert low_coverage.outline_coverage_ratio == 0.0


def test_candidate_page_artifact_projection_remains_non_binding_for_toc_body_concat_gate() -> None:
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
        cache_key="candidate-page-artifact-only",
        operations=(
            DocumentTopologyOperation(
                op="candidate_page_artifact_split",
                logical_indexes=(9, 10),
                canonical_text="This page intentionally left blank Chapter 11",
                authority="document_map_outline",
                confidence="candidate",
                evidence=("page_artifact_phrase", "local_heading_neighborhood", "page_break_boundary"),
            ),
            DocumentTopologyOperation(
                op="merge_heading_continuation",
                logical_indexes=(10, 11),
                canonical_text="Governance and We, the Citizens",
                authority="document_map_outline",
                confidence="high",
                evidence=("outline_entry", "adjacent_short_heading_fragments"),
            ),
        ),
    )

    assert (
        structural_validation_runtime._projection_supports_toc_body_concat_gate(
            document_map=document_map,
            topology_projection=projection,
        )
        is False
    )

    fields = structural_validation_runtime._derive_toc_body_concat_gate_fields(
        document_map=document_map,
        topology_projection=projection,
        markdown_detected=True,
    )

    assert fields["toc_body_concat_gate_source"] == "legacy_markdown"
    assert fields["toc_body_concat_detected"] is True
    assert fields["toc_body_concat_structure_detected"] is False
    assert fields["topology_split_compound_toc_operation_count"] == 0
    assert fields["topology_merge_heading_operation_count"] == 1


def test_apply_prepared_snapshot_fields_prefers_topology_authority_for_toc_body_concat_detected() -> None:
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
        cache_key="topology-authoritative-toc",
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
        paragraphs=[],
    )
    snapshot = structural_validation_runtime._build_preparation_diagnostic_defaults([])
    snapshot["toc_body_concat_detected"] = True
    snapshot["toc_body_concat_markdown_detected"] = True

    structural_validation_runtime._apply_prepared_snapshot_fields(
        snapshot,
        prepared,
        app_config={
            "structure_recovery_enabled": True,
            "structure_recovery_topology_projection_enabled": True,
        },
    )

    assert snapshot["toc_body_concat_markdown_detected"] is True
    assert snapshot["toc_body_concat_structure_detected"] is False
    assert snapshot["toc_body_concat_gate_source"] == "topology_projection"
    assert snapshot["toc_body_concat_detected"] is False
    assert snapshot["document_map_toc_detected"] is True
    assert snapshot["document_map_toc_region_count"] == 1
    assert snapshot["topology_toc_entry_count"] == 1
    assert snapshot["topology_split_compound_toc_operation_count"] == 0
    assert snapshot["document_map_compound_toc_split_hint_count"] == 0


def test_derive_unit_aware_unmapped_fields_exposes_raw_counts_and_explicit_basis() -> None:
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

    fields = structural_validation_runtime._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=projection,
        formatting_payload={
            "unmapped_source_ids": ["p0000", "p0001"],
            "unmapped_target_indexes": [0, 1],
            "target_registry": [
                {"target_index": 0, "mapped": False, "text_preview": "Governance and We,"},
                {"target_index": 1, "mapped": False, "text_preview": "the Citizens"},
            ],
        },
        generated_paragraph_registry=[
            {"paragraph_id": "p0000", "text": "# Governance and We,"},
            {"paragraph_id": "p0001", "text": "# the Citizens"},
        ],
    )

    assert fields["raw_unmapped_source_paragraph_count"] == 2
    assert fields["raw_unmapped_target_paragraph_count"] == 2
    assert fields["structure_unit_unmapped_source_count"] == 0
    assert fields["structure_unit_unmapped_target_count"] == 0
    assert fields["unmapped_source_count_basis"] == "topology_unit"
    assert fields["unmapped_target_count_basis"] == "topology_unit"
    assert fields["unit_unmapped_source_gate_source"] == "topology_unit"
    assert fields["unit_unmapped_target_gate_source"] == "topology_unit"


def test_build_structural_checks_exposes_explicit_unmapped_count_basis() -> None:
    document_profile = SimpleNamespace(
        max_formatting_diagnostics=5,
        max_unmapped_source_paragraphs=2,
        max_unmapped_target_paragraphs=2,
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
    checks = structural_validation_runtime._build_structural_checks(
        document_profile=document_profile,
        result="succeeded",
        metrics={
            "formatting_diagnostics_count": 0,
            "max_unmapped_source_paragraphs": 2,
            "max_unmapped_target_paragraphs": 2,
            "raw_unmapped_source_paragraph_count": 2,
            "raw_unmapped_target_paragraph_count": 2,
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
    assert by_name["unmapped_source_threshold"]["actual"] == 1
    assert by_name["unmapped_source_threshold"]["count_basis"] == "topology_unit"
    assert by_name["unmapped_source_threshold"]["raw_paragraph_actual"] == 2
    assert by_name["unmapped_source_threshold"]["unmapped_gate_source"] == "topology_unit"
    assert by_name["unmapped_target_threshold"]["actual"] == 1
    assert by_name["unmapped_target_threshold"]["count_basis"] == "topology_unit"
    assert by_name["unmapped_target_threshold"]["raw_paragraph_actual"] == 2
    assert by_name["unmapped_target_threshold"]["unmapped_gate_source"] == "topology_unit"


def test_build_markdown_quality_metrics_collects_detector_advisories_without_failing() -> None:
    metrics = structural_validation_runtime._build_markdown_quality_metrics(
        latest_markdown=(
            "# Chapter One\n"
            "# Chapter Two\n\n"
            "This page intentionally left blank\n\n"
            "Introduction 12\n"
            "Introduction 13\n"
            "Introduction 14\n"
        ),
        raw_markdown="",
        raw_structural_markdown="",
        translation_domain="general",
    )

    assert metrics["pdf_blank_page_marker_leakage_count"] == 1
    assert metrics["inline_page_furniture_leakage_count"] == 3
    assert metrics["adjacent_h1_without_body_count"] == 1
    assert metrics["pdf_blank_page_marker_leakage_threshold"] is None
    assert metrics["pdf_blank_page_marker_leakage_samples"][0]["reason"] == "blank_page_marker_visible_in_output"
    audit = metrics["quality_gate_audit_classifications"]
    assert audit["pdf_blank_page_marker_leakage"]["verdict"] == "unit_aware"
    assert audit["inline_page_furniture_leakage"]["verdict"] == "unit_aware"
    assert audit["heading_body_concat_detected"]["verdict"] == "tolerant"


def test_build_structural_checks_serializes_strict_detector_threshold_fields_when_configured() -> None:
    document_profile = SimpleNamespace(
        max_formatting_diagnostics=5,
        max_unmapped_source_paragraphs=2,
        max_unmapped_target_paragraphs=2,
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
        max_pdf_blank_page_marker_leakage=0,
        max_inline_page_furniture_leakage=1,
        max_adjacent_h1_without_body=0,
        max_heading_body_concat_detected=0,
        max_h1_epigraph_attribution_pattern=0,
    )
    checks = structural_validation_runtime._build_structural_checks(
        document_profile=document_profile,
        result="succeeded",
        metrics={
            "formatting_diagnostics_count": 0,
            "max_unmapped_source_paragraphs": 0,
            "max_unmapped_target_paragraphs": 0,
            "heading_level_drift": 0,
            "text_similarity": 1.0,
            "heading_only_output_detected": False,
            "pdf_blank_page_marker_leakage_count": 1,
            "pdf_blank_page_marker_leakage_samples": [{"line": 3}],
            "inline_page_furniture_leakage_count": 1,
            "inline_page_furniture_leakage_samples": [{"line": 3}],
            "adjacent_h1_without_body_count": 1,
            "adjacent_h1_without_body_samples": [{"line": 1}],
            "heading_body_concat_detected_count": 0,
            "heading_body_concat_detected_samples": [],
            "h1_epigraph_attribution_pattern_count": 0,
            "h1_epigraph_attribution_pattern_samples": [],
        },
        output_artifacts={"output_docx_openable": True, "output_visible_text_chars": 100},
    )

    by_name = {check["name"]: check for check in checks}
    assert by_name["pdf_blank_page_marker_leakage"]["passed"] is False
    assert by_name["pdf_blank_page_marker_leakage"]["allowed"] == 0
    assert by_name["pdf_blank_page_marker_leakage"]["samples"] == [{"line": 3}]
    assert by_name["inline_page_furniture_leakage"]["passed"] is True
    assert by_name["adjacent_h1_without_body"]["passed"] is False
