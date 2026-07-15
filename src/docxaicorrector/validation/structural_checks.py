"""Structural-metric and check-building helpers from ``validation/structural.py``
(spec 034, Step 5, Clusters B + K + ``_apply_metric_snapshot_fields``).

Markdown-quality metric assembly, structural-metric extraction, and the extraction /
structural / sentinel check builders. Depends only on stdlib / typing, on
``_as_int`` / ``_as_float`` from the lower ``structural_metrics_common`` leaf, and on
domain helpers (``pipeline.output_validation`` / ``pipeline.display_hygiene`` /
``document.boundaries`` / ``validation.quality_gate_audit`` / ``validation.profiles``) --
never on the ``structural`` orchestration module -- so no import cycle is introduced.
Bodies are byte-identical to their former in-module definitions; ``structural``
re-exports them so the qualified names (``structural._build_structural_checks``,
``structural._build_markdown_quality_metrics``, ...) keep resolving.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from docxaicorrector.core.models import ParagraphBoundaryNormalizationReport
from docxaicorrector.document.boundaries import summarize_boundary_normalization_metrics
from docxaicorrector.pipeline.display_hygiene import summarize_structure_quality_detectors
from docxaicorrector.pipeline.output_validation import (
    collect_bullet_heading_samples,
    collect_false_fragment_heading_samples,
    collect_list_fragment_regression_samples,
    collect_mixed_script_samples,
    collect_page_placeholder_heading_concat_samples,
    collect_residual_bullet_glyph_samples,
    collect_theology_style_issue_samples,
)
from docxaicorrector.validation.profiles import DocumentProfile
from docxaicorrector.validation.quality_gate_audit import quality_gate_audit_classifications_payload
from docxaicorrector.validation.structural_metrics_common import (
    _as_float,
    _as_int,
)


def _build_markdown_quality_metrics(
    *,
    latest_markdown: str,
    raw_markdown: str,
    raw_structural_markdown: str,
    translation_domain: str,
) -> dict[str, object]:
    detector_counts, detector_samples = summarize_structure_quality_detectors(latest_markdown)
    bullet_heading_samples = collect_bullet_heading_samples(latest_markdown)
    raw_bullet_heading_samples = collect_bullet_heading_samples(raw_markdown)
    false_fragment_heading_samples = collect_false_fragment_heading_samples(raw_structural_markdown)
    page_placeholder_heading_concat_samples = collect_page_placeholder_heading_concat_samples(latest_markdown)
    raw_page_placeholder_heading_concat_samples = collect_page_placeholder_heading_concat_samples(raw_markdown)
    residual_bullet_glyph_samples = collect_residual_bullet_glyph_samples(latest_markdown)
    raw_residual_bullet_glyph_samples = collect_residual_bullet_glyph_samples(raw_markdown)
    list_fragment_regression_samples = collect_list_fragment_regression_samples(raw_structural_markdown)
    mixed_script_samples = collect_mixed_script_samples(latest_markdown)
    theology_style_samples = (
        collect_theology_style_issue_samples(latest_markdown)
        if str(translation_domain or "").strip().lower() == "theology"
        else []
    )
    suspicious_heading_repetition_count = sum(
        1
        for sample in false_fragment_heading_samples
        if str(getattr(sample, "reason", "") or "") == "suspicious_heading_repetition_present"
    )
    scripture_reference_heading_count = sum(
        1
        for sample in false_fragment_heading_samples
        if str(getattr(sample, "reason", "") or "") == "scripture_reference_heading_present"
    )
    return {
        "bullet_heading_count": len(bullet_heading_samples),
        "bullet_heading_gate_source": "legacy_markdown",
        "bullet_heading_classification": "markdown_gate",
        "raw_bullet_heading_count": len(raw_bullet_heading_samples),
        "false_fragment_heading_count": len(false_fragment_heading_samples),
        "false_fragment_heading_gate_source": "legacy_markdown",
        "raw_false_fragment_heading_count": len(false_fragment_heading_samples),
        "page_placeholder_heading_concat_count": len(page_placeholder_heading_concat_samples),
        "page_placeholder_heading_concat_source": "legacy_markdown",
        "page_placeholder_heading_concat_classification": "display_hygiene",
        "raw_page_placeholder_heading_concat_count": len(raw_page_placeholder_heading_concat_samples),
        "residual_bullet_glyph_count": len(residual_bullet_glyph_samples),
        "residual_bullet_glyph_gate_source": "legacy_markdown",
        "residual_bullet_glyph_classification": "display_hygiene",
        "raw_residual_bullet_glyph_count": len(raw_residual_bullet_glyph_samples),
        "list_fragment_regression_count": len(list_fragment_regression_samples),
        "list_fragment_regression_gate_source": "legacy_markdown",
        "raw_list_fragment_regression_count": len(list_fragment_regression_samples),
        "mixed_script_term_count": len(mixed_script_samples),
        "mixed_script_term_gate_source": "legacy_markdown",
        "mixed_script_term_classification": "non_structural_hygiene",
        "raw_mixed_script_term_count": len(mixed_script_samples),
        "theology_style_deterministic_issue_count": len(theology_style_samples),
        "theology_style_deterministic_issue_source": "legacy_markdown",
        "theology_style_deterministic_issue_classification": "domain_style_advisory",
        "raw_theology_style_deterministic_issue_count": len(theology_style_samples),
        "suspicious_heading_repetition_count": suspicious_heading_repetition_count,
        "scripture_reference_heading_count": scripture_reference_heading_count,
        "pdf_blank_page_marker_leakage_count": detector_counts.get("pdf_blank_page_marker_leakage", 0),
        "pdf_blank_page_marker_leakage_threshold": None,
        "pdf_blank_page_marker_leakage_samples": detector_samples.get("pdf_blank_page_marker_leakage", []),
        "inline_page_furniture_leakage_count": detector_counts.get("inline_page_furniture_leakage", 0),
        "inline_page_furniture_leakage_threshold": None,
        "inline_page_furniture_leakage_samples": detector_samples.get("inline_page_furniture_leakage", []),
        "adjacent_h1_without_body_count": detector_counts.get("adjacent_h1_without_body", 0),
        "adjacent_h1_without_body_threshold": None,
        "adjacent_h1_without_body_samples": detector_samples.get("adjacent_h1_without_body", []),
        "heading_body_concat_detected_count": detector_counts.get("heading_body_concat_detected", 0),
        "heading_body_concat_detected_threshold": None,
        "heading_body_concat_detected_samples": detector_samples.get("heading_body_concat_detected", []),
        "h1_epigraph_attribution_pattern_count": detector_counts.get("h1_epigraph_attribution_pattern", 0),
        "h1_epigraph_attribution_pattern_threshold": None,
        "h1_epigraph_attribution_pattern_samples": detector_samples.get("h1_epigraph_attribution_pattern", []),
        "quality_gate_audit_classifications": quality_gate_audit_classifications_payload(),
    }


def _apply_metric_snapshot_fields(snapshot: dict[str, object], metrics: Mapping[str, object]) -> None:
    for key in (
        "document_map_toc_detected",
        "document_map_toc_region_count",
        "topology_toc_entry_count",
        "bullet_heading_count",
        "bullet_heading_gate_source",
        "bullet_heading_classification",
        "raw_bullet_heading_count",
        "false_fragment_heading_count",
        "false_fragment_heading_gate_source",
        "raw_false_fragment_heading_count",
        "page_placeholder_heading_concat_count",
        "page_placeholder_heading_concat_source",
        "page_placeholder_heading_concat_classification",
        "raw_page_placeholder_heading_concat_count",
        "residual_bullet_glyph_count",
        "residual_bullet_glyph_gate_source",
        "residual_bullet_glyph_classification",
        "raw_residual_bullet_glyph_count",
        "list_fragment_regression_count",
        "list_fragment_regression_gate_source",
        "raw_list_fragment_regression_count",
        "mixed_script_term_count",
        "mixed_script_term_gate_source",
        "mixed_script_term_classification",
        "raw_mixed_script_term_count",
        "theology_style_deterministic_issue_count",
        "theology_style_deterministic_issue_source",
        "theology_style_deterministic_issue_classification",
        "raw_theology_style_deterministic_issue_count",
        "toc_body_concat_detected",
        "toc_body_concat_markdown_detected",
        "toc_body_concat_structure_detected",
        "toc_body_concat_gate_source",
        "topology_split_compound_toc_operation_count",
        "topology_merge_heading_operation_count",
        "document_map_compound_toc_split_hint_count",
        "raw_unmapped_source_paragraph_count",
        "raw_unmapped_target_paragraph_count",
        "structure_unit_unmapped_source_count",
        "structure_unit_unmapped_target_count",
        "unit_covered_source_fragment_count",
        "unit_covered_target_fragment_count",
        "unmapped_source_count_basis",
        "unmapped_target_count_basis",
        "unit_unmapped_source_gate_source",
        "unit_unmapped_target_gate_source",
        "pdf_blank_page_marker_leakage_count",
        "pdf_blank_page_marker_leakage_threshold",
        "pdf_blank_page_marker_leakage_samples",
        "inline_page_furniture_leakage_count",
        "inline_page_furniture_leakage_threshold",
        "inline_page_furniture_leakage_samples",
        "adjacent_h1_without_body_count",
        "adjacent_h1_without_body_threshold",
        "adjacent_h1_without_body_samples",
        "heading_body_concat_detected_count",
        "heading_body_concat_detected_threshold",
        "heading_body_concat_detected_samples",
        "h1_epigraph_attribution_pattern_count",
        "h1_epigraph_attribution_pattern_threshold",
        "h1_epigraph_attribution_pattern_samples",
    ):
        if key in metrics:
            snapshot[key] = metrics[key]


def _build_structural_metrics(
    *,
    paragraphs: Sequence[object],
    image_assets: Sequence[object],
    normalization_report: ParagraphBoundaryNormalizationReport | None = None,
    relation_report=None,
    cleanup_report=None,
) -> dict[str, object]:
    paragraph_units = list(paragraphs)
    cleanup_mode = "remove" if cleanup_report is None else str(getattr(cleanup_report, "cleanup_mode", "remove") or "remove").strip().lower()
    if cleanup_mode == "flag":
        effective_cleanup_removed_count = int(getattr(cleanup_report, "flagged_page_number_count", 0) or 0) + int(
            getattr(cleanup_report, "flagged_repeated_artifact_count", 0) or 0
        ) + int(getattr(cleanup_report, "flagged_empty_or_whitespace_count", 0) or 0)
        effective_cleanup_page_number_count = int(getattr(cleanup_report, "flagged_page_number_count", 0) or 0)
        effective_cleanup_repeated_artifact_count = int(
            getattr(cleanup_report, "flagged_repeated_artifact_count", 0) or 0
        )
        effective_cleanup_empty_or_whitespace_count = int(
            getattr(cleanup_report, "flagged_empty_or_whitespace_count", 0) or 0
        )
    else:
        effective_cleanup_removed_count = 0 if cleanup_report is None else int(getattr(cleanup_report, "removed_paragraph_count", 0) or 0)
        effective_cleanup_page_number_count = 0 if cleanup_report is None else int(getattr(cleanup_report, "removed_page_number_count", 0) or 0)
        effective_cleanup_repeated_artifact_count = 0 if cleanup_report is None else int(
            getattr(cleanup_report, "removed_repeated_artifact_count", 0) or 0
        )
        effective_cleanup_empty_or_whitespace_count = 0 if cleanup_report is None else int(
            getattr(cleanup_report, "removed_empty_or_whitespace_count", 0) or 0
        )
    return {
        "paragraph_count": len(paragraph_units),
        "heading_count": sum(1 for paragraph in paragraph_units if getattr(paragraph, "role", None) == "heading"),
        "numbered_item_count": sum(
            1
            for paragraph in paragraph_units
            if getattr(paragraph, "role", None) == "list" and getattr(paragraph, "list_kind", None) == "ordered"
        ),
        "image_count": len(list(image_assets)),
        "table_count": sum(1 for paragraph in paragraph_units if getattr(paragraph, "role", None) == "table"),
        "raw_paragraph_count": 0 if normalization_report is None else normalization_report.total_raw_paragraphs,
        "logical_paragraph_count": 0 if normalization_report is None else normalization_report.total_logical_paragraphs,
        "merged_group_count": 0 if normalization_report is None else normalization_report.merged_group_count,
        "merged_raw_paragraph_count": 0 if normalization_report is None else normalization_report.merged_raw_paragraph_count,
        **summarize_boundary_normalization_metrics(normalization_report),
        "relation_count": 0 if relation_report is None else relation_report.total_relations,
        "rejected_relation_candidate_count": 0 if relation_report is None else relation_report.rejected_candidate_count,
        "relation_counts": {} if relation_report is None else dict(relation_report.relation_counts),
        "layout_cleanup_removed_count": effective_cleanup_removed_count,
        "layout_cleanup_page_number_count": effective_cleanup_page_number_count,
        "layout_cleanup_repeated_artifact_count": effective_cleanup_repeated_artifact_count,
        "layout_cleanup_empty_or_whitespace_count": effective_cleanup_empty_or_whitespace_count,
    }


def _build_extraction_checks(document_profile: DocumentProfile, metrics: Mapping[str, object]) -> list[dict[str, object]]:
    checks = [
        _check_minimum("paragraph_count_minimum", _as_int(metrics, "paragraph_count"), document_profile.min_paragraphs),
    ]
    if document_profile.min_merged_groups > 0:
        checks.append(
            _check_minimum(
                "merged_group_count_minimum",
                _as_int(metrics, "merged_group_count"),
                document_profile.min_merged_groups,
            )
        )
    if document_profile.min_merged_raw_paragraphs > 0:
        checks.append(
            _check_minimum(
                "merged_raw_paragraph_count_minimum",
                _as_int(metrics, "merged_raw_paragraph_count"),
                document_profile.min_merged_raw_paragraphs,
            )
        )
    if document_profile.has_headings:
        checks.append(_check_minimum("heading_count_minimum", _as_int(metrics, "heading_count"), document_profile.min_headings))
    if document_profile.has_numbered_lists:
        checks.append(
            _check_minimum(
                "numbered_item_count_minimum",
                _as_int(metrics, "numbered_item_count"),
                document_profile.min_numbered_items,
            )
        )
    if document_profile.has_images:
        checks.append(_check_minimum("image_count_minimum", _as_int(metrics, "image_count"), document_profile.min_images))
    if document_profile.has_tables:
        checks.append(_check_minimum("table_count_minimum", _as_int(metrics, "table_count"), document_profile.min_tables))
    return checks


def _build_structural_checks(
    *,
    document_profile: DocumentProfile,
    result: str,
    metrics: Mapping[str, object],
    output_artifacts: Mapping[str, object],
) -> list[dict[str, object]]:
    sentinel_threshold_checks = _build_sentinel_threshold_checks(document_profile)
    unmapped_source_gate_source = str(
        metrics.get("unmapped_source_count_basis")
        or metrics.get("unit_unmapped_source_gate_source")
        or "legacy_paragraph"
    ).strip().lower()
    unmapped_source_actual = (
        _as_int(metrics, "structure_unit_unmapped_source_count")
        if unmapped_source_gate_source in {"topology_unit", "accepted_aggregation_legacy"}
        else _as_int(metrics, "effective_unmapped_source_count")
        if unmapped_source_gate_source == "role_aware_formatting_coverage"
        else _as_int(metrics, "max_unmapped_source_paragraphs")
    )
    unmapped_target_gate_source = str(
        metrics.get("unmapped_target_count_basis")
        or metrics.get("unit_unmapped_target_gate_source")
        or "legacy_paragraph"
    ).strip().lower()
    unmapped_target_actual = (
        _as_int(metrics, "structure_unit_unmapped_target_count")
        if unmapped_target_gate_source in {"topology_unit", "accepted_aggregation_legacy"}
        else _as_int(metrics, "max_unmapped_target_paragraphs")
    )
    checks = [
        *sentinel_threshold_checks,
        {"name": "pipeline_succeeded", "passed": result == "succeeded", "result": result},
        {
            "name": "output_docx_openable",
            "passed": bool(output_artifacts.get("output_docx_openable")),
            "output_docx_openable": output_artifacts.get("output_docx_openable"),
        },
        {
            "name": "formatting_diagnostics_threshold",
            "passed": _as_int(metrics, "formatting_diagnostics_count") <= document_profile.max_formatting_diagnostics,
            "actual": metrics["formatting_diagnostics_count"],
            "allowed": document_profile.max_formatting_diagnostics,
        },
        {
            "name": "unmapped_source_threshold",
            "passed": unmapped_source_actual <= document_profile.max_unmapped_source_paragraphs,
            "actual": unmapped_source_actual,
            "allowed": document_profile.max_unmapped_source_paragraphs,
            "count_basis": unmapped_source_gate_source,
            "raw_paragraph_actual": metrics.get(
                "raw_unmapped_source_paragraph_count",
                metrics["max_unmapped_source_paragraphs"],
            ),
            "paragraph_actual": metrics["max_unmapped_source_paragraphs"],
            "structure_unit_actual": metrics.get("structure_unit_unmapped_source_count"),
            "unmapped_gate_source": metrics.get(
                "unmapped_source_count_basis",
                metrics.get("unit_unmapped_source_gate_source"),
            ),
        },
        {
            "name": "unmapped_target_threshold",
            "passed": unmapped_target_actual <= document_profile.max_unmapped_target_paragraphs,
            "actual": unmapped_target_actual,
            "allowed": document_profile.max_unmapped_target_paragraphs,
            "count_basis": unmapped_target_gate_source,
            "raw_paragraph_actual": metrics.get(
                "raw_unmapped_target_paragraph_count",
                metrics["max_unmapped_target_paragraphs"],
            ),
            "paragraph_actual": metrics["max_unmapped_target_paragraphs"],
            "structure_unit_actual": metrics.get("structure_unit_unmapped_target_count"),
            "unmapped_gate_source": metrics.get(
                "unmapped_target_count_basis",
                metrics.get("unit_unmapped_target_gate_source"),
            ),
        },
        {
            "name": "heading_level_drift_threshold",
            "passed": _as_int(metrics, "heading_level_drift") <= document_profile.max_heading_level_drift,
            "actual": metrics["heading_level_drift"],
            "allowed": document_profile.max_heading_level_drift,
        },
        {
            "name": "text_similarity_threshold",
            "passed": _as_float(metrics, "text_similarity") >= document_profile.min_text_similarity,
            "actual": metrics["text_similarity"],
            "required": document_profile.min_text_similarity,
        },
    ]
    if document_profile.require_numbered_lists_preserved:
        checks.append(
            {
                "name": "numbered_lists_preserved",
                "passed": _as_int(metrics, "output_numbered_item_count") >= _as_int(metrics, "numbered_item_count"),
                "source": metrics["numbered_item_count"],
                "output": metrics["output_numbered_item_count"],
            }
        )
    if document_profile.require_nonempty_output:
        checks.append(
            {
                "name": "nonempty_output_required",
                "passed": bool(output_artifacts.get("output_visible_text_chars")),
                "output_visible_text_chars": output_artifacts.get("output_visible_text_chars"),
            }
        )
    if document_profile.forbid_heading_only_collapse:
        checks.append(
            {
                "name": "forbid_heading_only_collapse",
                "passed": not bool(metrics["heading_only_output_detected"]),
                "heading_only_output_detected": metrics["heading_only_output_detected"],
            }
        )
    if document_profile.require_toc_detected:
        bounded_toc_detected = bool(
            metrics.get("source_toc_detected")
            or metrics.get("output_toc_detected")
            or _as_int(metrics, "structure_repair_bounded_toc_regions") > 0
            or _as_int(metrics, "source_toc_region_count") > 0
            or _as_int(metrics, "effective_source_toc_region_count") > 0
            or bool(metrics.get("document_map_toc_detected"))
            or _as_int(metrics, "document_map_toc_region_count") > 0
            or _as_int(metrics, "topology_toc_entry_count") > 0
        )
        checks.append(
            {
                "name": "toc_detected_required",
                "passed": bounded_toc_detected,
                "source_toc_detected": metrics.get("source_toc_detected"),
                "output_toc_detected": metrics.get("output_toc_detected"),
                "structure_repair_bounded_toc_regions": metrics.get("structure_repair_bounded_toc_regions"),
                "source_toc_region_count": metrics.get("source_toc_region_count"),
                "effective_source_toc_region_count": metrics.get("effective_source_toc_region_count"),
                "document_map_toc_detected": metrics.get("document_map_toc_detected"),
                "document_map_toc_region_count": metrics.get("document_map_toc_region_count"),
                "topology_toc_entry_count": metrics.get("topology_toc_entry_count"),
            }
        )
    if document_profile.require_pdf_conversion:
        checks.append(
            {
                "name": "pdf_conversion_required",
                "passed": bool(metrics.get("require_pdf_conversion_satisfied")),
                "require_pdf_conversion_satisfied": metrics.get("require_pdf_conversion_satisfied"),
            }
        )
    if document_profile.require_no_bullet_headings:
        checks.append(
            {
                "name": "no_bullet_headings_required",
                "passed": _as_int(metrics, "bullet_heading_count") == 0,
                "bullet_heading_count": metrics.get("bullet_heading_count"),
            }
        )
    if document_profile.require_no_toc_body_concat:
        gate_source = str(metrics.get("toc_body_concat_gate_source") or "legacy_markdown").strip().lower() or "legacy_markdown"
        structure_toc_boundary_resolved = bool(
            _as_int(metrics, "document_map_toc_region_count") > 0
            and (
                _as_int(metrics, "topology_toc_entry_count") > 0
                or _as_int(metrics, "topology_split_compound_toc_operation_count") > 0
                or _as_int(metrics, "document_map_compound_toc_split_hint_count") == 0
            )
        )
        source_toc_boundary_repaired = (
            _as_int(metrics, "structure_repair_toc_body_boundary_repairs") > 0
            or _as_int(metrics, "effective_source_toc_region_count") > 0
            or (gate_source == "topology_projection" and structure_toc_boundary_resolved)
        )
        gate_detected = bool(
            metrics.get(
                "toc_body_concat_structure_detected"
                if gate_source == "topology_projection"
                else "toc_body_concat_markdown_detected",
                metrics.get("toc_body_concat_detected"),
            )
        )
        checks.append(
            {
                "name": "no_toc_body_concat_required",
                "passed": not gate_detected and source_toc_boundary_repaired,
                "toc_body_concat_detected": metrics.get("toc_body_concat_detected"),
                "toc_body_concat_markdown_detected": metrics.get("toc_body_concat_markdown_detected"),
                "toc_body_concat_structure_detected": metrics.get("toc_body_concat_structure_detected"),
                "toc_body_concat_gate_source": metrics.get("toc_body_concat_gate_source"),
                "structure_repair_toc_body_boundary_repairs": metrics.get("structure_repair_toc_body_boundary_repairs"),
                "effective_source_toc_region_count": metrics.get("effective_source_toc_region_count"),
                "document_map_toc_region_count": metrics.get("document_map_toc_region_count"),
                "topology_toc_entry_count": metrics.get("topology_toc_entry_count"),
                "topology_split_compound_toc_operation_count": metrics.get(
                    "topology_split_compound_toc_operation_count"
                ),
            }
        )
    if document_profile.require_translation_domain:
        checks.append(
            {
                "name": "translation_domain_required",
                "passed": str(metrics.get("runtime_translation_domain", "")) == document_profile.require_translation_domain,
                "actual": metrics.get("runtime_translation_domain"),
                "required": document_profile.require_translation_domain,
            }
        )
    for check_name, metric_key, threshold in (
        (
            "pdf_blank_page_marker_leakage",
            "pdf_blank_page_marker_leakage_count",
                getattr(document_profile, "max_pdf_blank_page_marker_leakage", None),
        ),
        (
            "inline_page_furniture_leakage",
            "inline_page_furniture_leakage_count",
                getattr(document_profile, "max_inline_page_furniture_leakage", None),
        ),
        (
            "adjacent_h1_without_body",
            "adjacent_h1_without_body_count",
                getattr(document_profile, "max_adjacent_h1_without_body", None),
        ),
        (
            "heading_body_concat_detected",
            "heading_body_concat_detected_count",
                getattr(document_profile, "max_heading_body_concat_detected", None),
        ),
        (
            "h1_epigraph_attribution_pattern",
            "h1_epigraph_attribution_pattern_count",
                getattr(document_profile, "max_h1_epigraph_attribution_pattern", None),
        ),
    ):
        if threshold is None:
            continue
        checks.append(
            {
                "name": check_name,
                "passed": _as_int(metrics, metric_key) <= threshold,
                "actual": metrics.get(metric_key),
                "allowed": threshold,
                "advisory_only": False,
                "samples": metrics.get(metric_key.replace("_count", "_samples"), []),
            }
        )
    if _as_int(metrics, "structure_repair_bounded_toc_regions") > 0:
        checks.append(
            {
                "name": "bounded_toc_repair_detected",
                "passed": True,
                "bounded_toc_regions": metrics.get("structure_repair_bounded_toc_regions"),
                "source_toc_region_count": metrics.get("source_toc_region_count"),
            }
        )
    return checks


def _build_sentinel_threshold_checks(document_profile: DocumentProfile) -> list[dict[str, object]]:
    threshold_fields = {
        "max_formatting_diagnostics": document_profile.max_formatting_diagnostics,
        "max_unmapped_source_paragraphs": document_profile.max_unmapped_source_paragraphs,
        "max_unmapped_target_paragraphs": document_profile.max_unmapped_target_paragraphs,
        "max_heading_level_drift": document_profile.max_heading_level_drift,
    }
    return [
        {
            "name": f"{field_name}_not_sentinel",
            "passed": not _is_effectively_infinite_threshold(value),
            "actual": value,
            "maximum_allowed_threshold": 100000,
        }
        for field_name, value in threshold_fields.items()
    ]


def _is_effectively_infinite_threshold(value: object) -> bool:
    try:
        return int(value) >= 100000
    except (TypeError, ValueError):
        return False


def _check_minimum(name: str, actual: int, minimum: int) -> dict[str, object]:
    return {"name": name, "passed": actual >= minimum, "actual": actual, "minimum": minimum}
