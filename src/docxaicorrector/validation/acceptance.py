"""Shared acceptance-verdict assembly.

This module owns the assembly of the acceptance verdict (the list of named
checks + ``passed``/``failed_checks`` roll-up) that historically lived entirely
inside the validation harness (``run_lietaer_validation.py``).

Extracting it here (GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR §Scope item 6 —
"Harness↔prod verdict parity") lets BOTH the harness and production
finalization compute the *same* trustworthy verdict from a report context.

The report-derived checks (pipeline/reader-cleanup/output-artifacts/threshold/
translation-quality/toc checks) are assembled here from the ``report`` mapping.
The optional structural (source↔output DOCX) comparison checks — which depend on
docx parsing helpers owned by the harness — are supplied via an injected
``structural_checks_builder`` callback, so this module stays free of test-only
dependencies while remaining behaviour-identical to the harness.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import cast

from docxaicorrector.pipeline.output_validation import collect_page_placeholder_heading_concat_samples
from docxaicorrector.validation.formatting_coverage import (
    resolve_filtered_formatting_unmapped_source_count as _resolve_filtered_formatting_unmapped_source_count,
    resolve_role_aware_formatting_unmapped_source_summary as _resolve_role_aware_formatting_unmapped_source_summary,
    resolve_role_aware_formatting_unmapped_target_summary as _resolve_role_aware_formatting_unmapped_target_summary,
)


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            return default
    return default


def _max_payload_list_length(
    formatting_diagnostics: Sequence[Mapping[str, object]],
    key: str,
) -> int:
    max_length = 0
    for payload in formatting_diagnostics:
        values = payload.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)):
            max_length = max(max_length, len(values))
    return max_length


def resolve_acceptance_unmapped_source_summary(
    *,
    formatting_diagnostics: Sequence[Mapping[str, object]],
    translation_quality_report: Mapping[str, object],
    preparation_diagnostic_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    count_basis = str(translation_quality_report.get("unmapped_source_count_basis") or "").strip().lower()
    if count_basis in {"topology_unit", "accepted_aggregation_legacy"}:
        actual = _coerce_int(
            translation_quality_report.get(
                "structure_unit_unmapped_source_count",
                translation_quality_report.get(
                    "worst_unmapped_source_count",
                    translation_quality_report.get("unmapped_source_count"),
                ),
            )
        )
        return {
            "actual": actual,
            "unmapped_source_count_basis": count_basis,
            "raw_worst_unmapped_source_count": _max_payload_list_length(formatting_diagnostics, "unmapped_source_ids"),
            "format_neutral_creditable_count": 0,
        }

    role_aware_summary = _resolve_role_aware_formatting_unmapped_source_summary(
        formatting_diagnostics, preparation_diagnostic_snapshot
    )
    if role_aware_summary is not None:
        return {
            "actual": _coerce_int(role_aware_summary["effective_unmapped_source_count"]),
            **role_aware_summary,
            "quality_unmapped_source_count": _coerce_int(
                translation_quality_report.get(
                    "worst_unmapped_source_count",
                    translation_quality_report.get("unmapped_source_count"),
                )
            ),
        }

    quality_count = _coerce_int(
        translation_quality_report.get(
            "worst_unmapped_source_count",
            translation_quality_report.get("unmapped_source_count"),
        )
    )
    formatting_count, benign_reduction_applied = _resolve_filtered_formatting_unmapped_source_count(formatting_diagnostics)
    actual = formatting_count if benign_reduction_applied else max(quality_count, formatting_count)
    return {
        "actual": actual,
        "unmapped_source_count_basis": translation_quality_report.get("unmapped_source_count_basis"),
        "raw_worst_unmapped_source_count": _max_payload_list_length(formatting_diagnostics, "unmapped_source_ids"),
        "filtered_unmapped_source_count": formatting_count,
        "quality_unmapped_source_count": quality_count,
        "benign_reduction_applied": benign_reduction_applied,
        "format_neutral_creditable_count": 0,
    }


def resolve_acceptance_unmapped_target_summary(
    *,
    formatting_diagnostics: Sequence[Mapping[str, object]],
    translation_quality_report: Mapping[str, object],
    preparation_diagnostic_snapshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    role_aware_target_summary = _resolve_role_aware_formatting_unmapped_target_summary(
        formatting_diagnostics, preparation_diagnostic_snapshot
    )
    if role_aware_target_summary is not None:
        quality_count = _coerce_int(translation_quality_report.get("unmapped_target_count"))
        return {
            "actual": _coerce_int(role_aware_target_summary["effective_unmapped_target_count"]),
            "unmapped_target_count_basis": role_aware_target_summary["unmapped_target_count_basis"],
            "raw_unmapped_target_count": _coerce_int(role_aware_target_summary["raw_unmapped_target_count"]),
            "role_aware_effective_unmapped_target_count": role_aware_target_summary.get(
                "effective_unmapped_target_count"
            ),
            "quality_unmapped_target_count": quality_count,
            "target_split_accounting_creditable_count": role_aware_target_summary.get(
                "target_split_accounting_creditable_count"
            ),
            "passthrough_unmapped_target_count": role_aware_target_summary.get(
                "passthrough_unmapped_target_count"
            ),
            "passthrough_target_category_counts": role_aware_target_summary.get(
                "passthrough_target_category_counts"
            ),
            "passthrough_front_matter_target_count": role_aware_target_summary.get(
                "passthrough_front_matter_target_count"
            ),
            "passthrough_page_furniture_target_count": role_aware_target_summary.get(
                "passthrough_page_furniture_target_count"
            ),
            "passthrough_references_target_count": role_aware_target_summary.get(
                "passthrough_references_target_count"
            ),
            "passthrough_caption_target_count": role_aware_target_summary.get(
                "passthrough_caption_target_count"
            ),
            "passthrough_part_target_count": role_aware_target_summary.get(
                "passthrough_part_target_count"
            ),
            "front_matter_boundary_target_index": role_aware_target_summary.get(
                "front_matter_boundary_target_index"
            ),
            "references_region_target_start_index": role_aware_target_summary.get(
                "references_region_target_start_index"
            ),
        }
    count_basis = str(translation_quality_report.get("unmapped_target_count_basis") or "").strip().lower()
    if count_basis in {"topology_unit", "accepted_aggregation_legacy"}:
        actual = _coerce_int(
            translation_quality_report.get(
                "structure_unit_unmapped_target_count",
                translation_quality_report.get("unmapped_target_count"),
            )
        )
        return {
            "actual": actual,
            "unmapped_target_count_basis": count_basis,
            "raw_unmapped_target_count": _max_payload_list_length(formatting_diagnostics, "unmapped_target_indexes"),
            "role_aware_effective_unmapped_target_count": None,
            "quality_unmapped_target_count": _coerce_int(translation_quality_report.get("unmapped_target_count")),
            "target_split_accounting_creditable_count": 0,
        }
    quality_count = _coerce_int(translation_quality_report.get("unmapped_target_count"))
    formatting_count = _max_payload_list_length(formatting_diagnostics, "unmapped_target_indexes")
    raw_count = formatting_count
    actual = max(quality_count, formatting_count)
    summary_basis = translation_quality_report.get("unmapped_target_count_basis") or "raw_paragraph"
    return {
        "actual": actual,
        "unmapped_target_count_basis": summary_basis,
        "raw_unmapped_target_count": raw_count,
        "role_aware_effective_unmapped_target_count": None,
        "quality_unmapped_target_count": quality_count,
        "target_split_accounting_creditable_count": 0,
    }


def _build_toc_body_concat_provenance_details(
    *,
    preparation_diagnostic_snapshot: Mapping[str, object] | None = None,
    translation_quality_report: Mapping[str, object] | None = None,
) -> dict[str, object]:
    snapshot = preparation_diagnostic_snapshot or {}
    report = translation_quality_report or {}
    gate_source = (
        str(
            snapshot.get("toc_body_concat_gate_source")
            or report.get("toc_body_concat_gate_source")
            or "legacy_markdown"
        )
        .strip()
        .lower()
        or "legacy_markdown"
    )
    effective_gate_detected = snapshot.get(
        "toc_body_concat_detected",
        report.get("toc_body_concat_detected"),
    )
    markdown_gate_detected = snapshot.get(
        "toc_body_concat_markdown_detected",
        report.get("toc_body_concat_markdown_detected", effective_gate_detected),
    )
    structure_gate_detected = snapshot.get(
        "toc_body_concat_structure_detected",
        report.get("toc_body_concat_structure_detected"),
    )
    return {
        "toc_body_concat_detected": effective_gate_detected,
        "toc_body_concat_markdown_detected": markdown_gate_detected,
        "toc_body_concat_structure_detected": structure_gate_detected,
        "toc_body_concat_gate_source": gate_source,
    }


def build_acceptance_toc_body_concat_check(
    *,
    preparation_diagnostic_snapshot: Mapping[str, object],
    translation_quality_report: Mapping[str, object],
) -> dict[str, object]:
    provenance = _build_toc_body_concat_provenance_details(
        preparation_diagnostic_snapshot=preparation_diagnostic_snapshot,
        translation_quality_report=translation_quality_report,
    )
    gate_source = str(provenance["toc_body_concat_gate_source"] or "legacy_markdown")
    effective_gate_detected = provenance["toc_body_concat_detected"]
    markdown_gate_detected = provenance["toc_body_concat_markdown_detected"]
    structure_gate_detected = provenance["toc_body_concat_structure_detected"]
    structure_toc_boundary_resolved = bool(
        _coerce_int(preparation_diagnostic_snapshot.get("document_map_toc_region_count")) > 0
        and (
            _coerce_int(preparation_diagnostic_snapshot.get("topology_toc_entry_count")) > 0
            or _coerce_int(preparation_diagnostic_snapshot.get("topology_split_compound_toc_operation_count")) > 0
            or _coerce_int(preparation_diagnostic_snapshot.get("document_map_compound_toc_split_hint_count")) == 0
        )
    )
    source_toc_boundary_repaired = bool(
        _coerce_int(preparation_diagnostic_snapshot.get("structure_repair_toc_body_boundary_repairs")) > 0
        or _coerce_int(preparation_diagnostic_snapshot.get("effective_source_toc_region_count")) > 0
        or (gate_source == "topology_projection" and structure_toc_boundary_resolved)
    )
    gate_detected = bool(
        structure_gate_detected if gate_source == "topology_projection" else markdown_gate_detected
    )
    return {
        "name": "no_toc_body_concat_required",
        "passed": not gate_detected and source_toc_boundary_repaired,
        "toc_body_concat_detected": effective_gate_detected,
        "toc_body_concat_markdown_detected": markdown_gate_detected,
        "toc_body_concat_structure_detected": structure_gate_detected,
        "toc_body_concat_gate_source": gate_source,
        "structure_repair_toc_body_boundary_repairs": preparation_diagnostic_snapshot.get(
            "structure_repair_toc_body_boundary_repairs"
        ),
        "effective_source_toc_region_count": preparation_diagnostic_snapshot.get("effective_source_toc_region_count"),
        "document_map_toc_region_count": preparation_diagnostic_snapshot.get("document_map_toc_region_count"),
        "topology_toc_entry_count": preparation_diagnostic_snapshot.get("topology_toc_entry_count"),
        "topology_split_compound_toc_operation_count": preparation_diagnostic_snapshot.get(
            "topology_split_compound_toc_operation_count"
        ),
    }


def translation_quality_reason_is_review_only(
    translation_quality_report: Mapping[str, object],
    *,
    reason: str,
) -> bool:
    gate_reasons = translation_quality_report.get("gate_reasons")
    if not isinstance(gate_reasons, Sequence) or isinstance(gate_reasons, (str, bytes)):
        return False
    return reason in {str(item) for item in gate_reasons}


def extract_runtime_processing_operation(report: Mapping[str, object]) -> str:
    runtime_config = cast(Mapping[str, object], report.get("runtime_config") or {})
    effective = cast(Mapping[str, object], runtime_config.get("effective") or {})
    return str(effective.get("processing_operation") or "").strip().lower()


def build_acceptance_verdict(
    report: Mapping[str, object],
    *,
    mismatch_threshold: int | None = None,
    unmapped_target_threshold: int | None = None,
    require_no_toc_body_concat: bool = False,
    structural_checks_builder: Callable[[str], Sequence[Mapping[str, object]]] | None = None,
) -> dict[str, object]:
    """Assemble the acceptance verdict from a report context.

    Every check carries three distinguishable states in the data (spec FR-009):

    - ``applicable=True, passed=True``  — evaluated and satisfied,
    - ``applicable=True, passed=False`` — evaluated and violated (the only checks
      that enter ``failed_checks``),
    - ``applicable=False``              — the signal needed to evaluate the check is
      genuinely absent, so it is neither a pass nor a fail. Such a check carries a
      ``reason`` explaining why it could not be evaluated and never enters
      ``failed_checks`` (Constitution VII — "No source signal, no repair").

    A threshold passed as ``None`` means *unconfigured* (production has no per-book
    loss budget); the corresponding threshold check is emitted NOT-APPLICABLE while
    still carrying the measured ``actual``. A configured ``0`` still gates. The
    optional structural (source↔output DOCX) comparison checks are supplied by
    ``structural_checks_builder`` (invoked with the resolved
    ``processing_operation``); when it is ``None`` a single NOT-APPLICABLE
    ``structural_comparison_available`` check is emitted instead.

    The harness path — integer thresholds and a ``structural_checks_builder`` —
    yields a verdict whose ``passed``/``failed_checks`` are identical to the legacy
    behaviour; each check merely gains the explicit ``applicable`` key.
    """
    checks: list[dict[str, object]] = []

    def add_check(name: str, passed: bool, *, applicable: bool = True, **details: object) -> None:
        checks.append({"name": name, "passed": passed, "applicable": applicable, **details})

    result = str(report.get("result") or "")
    processing_operation = extract_runtime_processing_operation(report)
    output_artifacts = cast(Mapping[str, object], report.get("output_artifacts") or {})
    formatting_diagnostics = cast(Sequence[Mapping[str, object]], report.get("formatting_diagnostics") or [])
    translation_quality_report = cast(Mapping[str, object], report.get("translation_quality_report") or {})
    reader_cleanup_evidence = cast(Mapping[str, object], report.get("reader_cleanup_evidence") or {})

    add_check("pipeline_succeeded", result == "succeeded", result=result)
    reader_cleanup_stage_status = str(reader_cleanup_evidence.get("stage_status") or "").strip()
    reader_cleanup_failed_chunk_count = _coerce_int(reader_cleanup_evidence.get("failed_chunk_count"))
    reader_cleanup_chunk_count = _coerce_int(reader_cleanup_evidence.get("cleanup_chunk_count"))
    reader_cleanup_failure_ratio = (
        0.0
        if reader_cleanup_chunk_count <= 0
        else round(reader_cleanup_failed_chunk_count / reader_cleanup_chunk_count, 6)
    )
    add_check(
        "reader_cleanup_stage_completed",
        not reader_cleanup_stage_status or reader_cleanup_stage_status.lower() == "completed",
        stage_status=reader_cleanup_stage_status or None,
        failed_chunk_count=reader_cleanup_failed_chunk_count,
        cleanup_chunk_count=reader_cleanup_chunk_count,
        failed_chunk_ratio=reader_cleanup_failure_ratio,
    )
    output_docx_openable_value = output_artifacts.get("output_docx_openable")
    if output_docx_openable_value is None:
        # Production finalization computes this verdict before the delivered DOCX
        # exists (reader cleanup defers the base docx build), so the output's
        # openability — and therefore whether it carries placeholder markup — is
        # genuinely unknown here. Emit both as NOT-APPLICABLE rather than guessing
        # a pass or silently failing (spec FR-001/FR-002, Constitution VII).
        add_check(
            "output_docx_openable",
            False,
            applicable=False,
            reason="output_docx_not_available",
            output_docx_openable=None,
        )
        add_check(
            "no_placeholder_markup",
            False,
            applicable=False,
            reason="output_docx_not_available",
            output_contains_placeholder_markup=output_artifacts.get("output_contains_placeholder_markup"),
        )
    else:
        add_check(
            "output_docx_openable",
            bool(output_docx_openable_value),
            output_docx_openable=output_docx_openable_value,
        )
        add_check(
            "no_placeholder_markup",
            not bool(output_artifacts.get("output_contains_placeholder_markup")),
            output_contains_placeholder_markup=output_artifacts.get("output_contains_placeholder_markup"),
        )

    runtime = cast(Mapping[str, object], report.get("runtime") or {})
    runtime_state = cast(Mapping[str, object], runtime.get("state") or {})
    preparation_diagnostic_snapshot = cast(
        Mapping[str, object], report.get("preparation_diagnostic_snapshot") or {}
    )
    latest_markdown = str(runtime_state.get("latest_markdown") or "")
    processed_block_markdowns = cast(Sequence[object], runtime_state.get("processed_block_markdowns") or [])
    combined_processed_markdown = "\n\n".join(
        str(item) for item in processed_block_markdowns if isinstance(item, str) and item.strip()
    )
    if translation_quality_report:
        page_placeholder_heading_concat_count = _coerce_int(
            translation_quality_report.get("page_placeholder_heading_concat_count")
        )
        raw_page_placeholder_heading_concat_count = _coerce_int(
            translation_quality_report.get("raw_page_placeholder_heading_concat_count")
        )
        page_placeholder_heading_concat_source = translation_quality_report.get("page_placeholder_heading_concat_source")
        page_placeholder_heading_concat_classification = translation_quality_report.get(
            "page_placeholder_heading_concat_classification"
        )
    else:
        page_placeholder_heading_concat_count = len(collect_page_placeholder_heading_concat_samples(latest_markdown))
        raw_page_placeholder_heading_concat_count = len(
            collect_page_placeholder_heading_concat_samples(combined_processed_markdown or latest_markdown)
        )
        page_placeholder_heading_concat_source = "legacy_markdown"
        page_placeholder_heading_concat_classification = "display_hygiene"

    add_check(
        "page_placeholder_heading_concat_hygiene_applied",
        page_placeholder_heading_concat_count == 0,
        page_placeholder_heading_concat_count=page_placeholder_heading_concat_count,
        raw_page_placeholder_heading_concat_count=raw_page_placeholder_heading_concat_count,
        page_placeholder_heading_concat_source=page_placeholder_heading_concat_source,
        page_placeholder_heading_concat_classification=page_placeholder_heading_concat_classification,
    )

    known_false_split_patterns = {
        "lietaer_exchange_install_roof_split": "установить\n\nустановить новую крышу",
    }
    for check_suffix, bad_pattern in known_false_split_patterns.items():
        add_check(
            f"known_false_split_absent_in_final_markdown:{check_suffix}",
            bad_pattern not in latest_markdown.lower(),
            bad_pattern=bad_pattern,
        )
        add_check(
            f"known_false_split_absent_in_processed_markdown:{check_suffix}",
            bad_pattern not in combined_processed_markdown.lower(),
            bad_pattern=bad_pattern,
        )

    worst_unmapped_source_count = 0
    total_caption_heading_conflicts = 0
    for payload in formatting_diagnostics:
        worst_unmapped_source_count = max(
            worst_unmapped_source_count,
            len(cast(Sequence[object], payload.get("unmapped_source_ids") or [])),
        )
        total_caption_heading_conflicts += len(
            cast(Sequence[object], payload.get("caption_heading_conflicts") or [])
        )
    unmapped_source_summary = resolve_acceptance_unmapped_source_summary(
        formatting_diagnostics=formatting_diagnostics,
        translation_quality_report=translation_quality_report,
        preparation_diagnostic_snapshot=preparation_diagnostic_snapshot,
    )
    explicit_unmapped_source_count = _coerce_int(unmapped_source_summary["actual"])
    unmapped_target_summary = resolve_acceptance_unmapped_target_summary(
        formatting_diagnostics=formatting_diagnostics,
        translation_quality_report=translation_quality_report,
        preparation_diagnostic_snapshot=preparation_diagnostic_snapshot,
    )
    explicit_unmapped_target_count = _coerce_int(unmapped_target_summary["actual"])
    add_check(
        "formatting_diagnostics_threshold",
        bool(
            mismatch_threshold is not None
            and explicit_unmapped_source_count <= mismatch_threshold
            and total_caption_heading_conflicts == 0
        ),
        applicable=mismatch_threshold is not None,
        actual=explicit_unmapped_source_count,
        worst_unmapped_source_count=worst_unmapped_source_count,
        raw_worst_unmapped_source_count=worst_unmapped_source_count,
        unmapped_source_count_basis=unmapped_source_summary.get("unmapped_source_count_basis"),
        role_aware_effective_unmapped_source_count=unmapped_source_summary.get("effective_unmapped_source_count"),
        filtered_unmapped_source_count=unmapped_source_summary.get("filtered_unmapped_source_count"),
        format_neutral_creditable_count=unmapped_source_summary.get("format_neutral_creditable_count"),
        quality_unmapped_source_count=unmapped_source_summary.get("quality_unmapped_source_count"),
        passthrough_unmapped_source_count=unmapped_source_summary.get("passthrough_unmapped_source_count"),
        passthrough_source_category_counts=unmapped_source_summary.get("passthrough_source_category_counts"),
        passthrough_front_matter_source_count=unmapped_source_summary.get("passthrough_front_matter_source_count"),
        passthrough_bounded_toc_source_count=unmapped_source_summary.get("passthrough_bounded_toc_source_count"),
        passthrough_page_furniture_source_count=unmapped_source_summary.get("passthrough_page_furniture_source_count"),
        passthrough_references_source_count=unmapped_source_summary.get("passthrough_references_source_count"),
        passthrough_caption_source_count=unmapped_source_summary.get("passthrough_caption_source_count"),
        passthrough_part_source_count=unmapped_source_summary.get("passthrough_part_source_count"),
        passthrough_index_source_count=unmapped_source_summary.get("passthrough_index_source_count"),
        passthrough_attribution_source_count=unmapped_source_summary.get("passthrough_attribution_source_count"),
        front_matter_boundary_source_index=unmapped_source_summary.get("front_matter_boundary_source_index"),
        bounded_toc_region=unmapped_source_summary.get("bounded_toc_region"),
        references_region_source_start_index=unmapped_source_summary.get("references_region_source_start_index"),
        mismatch_threshold=mismatch_threshold,
        caption_heading_conflicts=total_caption_heading_conflicts,
        artifact_count=len(formatting_diagnostics),
        **({"reason": "threshold_not_configured"} if mismatch_threshold is None else {}),
    )
    add_check(
        "unmapped_source_threshold",
        bool(mismatch_threshold is not None and explicit_unmapped_source_count <= mismatch_threshold),
        applicable=mismatch_threshold is not None,
        actual=explicit_unmapped_source_count,
        allowed=mismatch_threshold,
        worst_unmapped_source_count=explicit_unmapped_source_count,
        raw_worst_unmapped_source_count=worst_unmapped_source_count,
        count_basis=unmapped_source_summary.get("unmapped_source_count_basis"),
        role_aware_effective_unmapped_source_count=unmapped_source_summary.get("effective_unmapped_source_count"),
        format_neutral_creditable_count=unmapped_source_summary.get("format_neutral_creditable_count"),
        passthrough_unmapped_source_count=unmapped_source_summary.get("passthrough_unmapped_source_count"),
        passthrough_front_matter_source_count=unmapped_source_summary.get("passthrough_front_matter_source_count"),
        passthrough_bounded_toc_source_count=unmapped_source_summary.get("passthrough_bounded_toc_source_count"),
        passthrough_page_furniture_source_count=unmapped_source_summary.get("passthrough_page_furniture_source_count"),
        passthrough_references_source_count=unmapped_source_summary.get("passthrough_references_source_count"),
        passthrough_caption_source_count=unmapped_source_summary.get("passthrough_caption_source_count"),
        passthrough_part_source_count=unmapped_source_summary.get("passthrough_part_source_count"),
        passthrough_index_source_count=unmapped_source_summary.get("passthrough_index_source_count"),
        passthrough_attribution_source_count=unmapped_source_summary.get("passthrough_attribution_source_count"),
        references_region_source_start_index=unmapped_source_summary.get("references_region_source_start_index"),
        **({"reason": "threshold_not_configured"} if mismatch_threshold is None else {}),
    )
    add_check(
        "unmapped_target_threshold",
        bool(unmapped_target_threshold is not None and explicit_unmapped_target_count <= unmapped_target_threshold),
        applicable=unmapped_target_threshold is not None,
        actual=explicit_unmapped_target_count,
        allowed=unmapped_target_threshold,
        unmapped_target_count=explicit_unmapped_target_count,
        count_basis=unmapped_target_summary.get("unmapped_target_count_basis"),
        raw_unmapped_target_count=unmapped_target_summary.get("raw_unmapped_target_count"),
        role_aware_effective_unmapped_target_count=unmapped_target_summary.get(
            "role_aware_effective_unmapped_target_count"
        ),
        target_split_accounting_creditable_count=unmapped_target_summary.get(
            "target_split_accounting_creditable_count"
        ),
        quality_unmapped_target_count=unmapped_target_summary.get("quality_unmapped_target_count"),
        passthrough_unmapped_target_count=unmapped_target_summary.get("passthrough_unmapped_target_count"),
        passthrough_target_category_counts=unmapped_target_summary.get("passthrough_target_category_counts"),
        passthrough_front_matter_target_count=unmapped_target_summary.get("passthrough_front_matter_target_count"),
        passthrough_page_furniture_target_count=unmapped_target_summary.get("passthrough_page_furniture_target_count"),
        passthrough_references_target_count=unmapped_target_summary.get("passthrough_references_target_count"),
        passthrough_caption_target_count=unmapped_target_summary.get("passthrough_caption_target_count"),
        passthrough_part_target_count=unmapped_target_summary.get("passthrough_part_target_count"),
        passthrough_index_target_count=unmapped_target_summary.get("passthrough_index_target_count"),
        passthrough_attribution_target_count=unmapped_target_summary.get("passthrough_attribution_target_count"),
        front_matter_boundary_target_index=unmapped_target_summary.get("front_matter_boundary_target_index"),
        references_region_target_start_index=unmapped_target_summary.get("references_region_target_start_index"),
        **({"reason": "threshold_not_configured"} if unmapped_target_threshold is None else {}),
    )

    if translation_quality_report:
        add_check(
            "translation_quality_report_not_failed",
            str(translation_quality_report.get("quality_status") or "").strip().lower() != "fail",
            quality_status=translation_quality_report.get("quality_status"),
            gate_reasons=translation_quality_report.get("gate_reasons"),
        )
        add_check(
            "bullet_marker_headings_present",
            _coerce_int(translation_quality_report.get("bullet_heading_count")) == 0
            or translation_quality_reason_is_review_only(
                translation_quality_report,
                reason="bullet_marker_headings_review_required",
            ),
            bullet_heading_count=translation_quality_report.get("bullet_heading_count"),
            bullet_heading_gate_source=translation_quality_report.get("bullet_heading_gate_source"),
            bullet_heading_classification=translation_quality_report.get("bullet_heading_classification"),
            raw_bullet_heading_count=translation_quality_report.get("raw_bullet_heading_count"),
        )
        add_check(
            "false_fragment_headings_present",
            _coerce_int(translation_quality_report.get("false_fragment_heading_count")) == 0
            or translation_quality_reason_is_review_only(
                translation_quality_report,
                reason="false_fragment_headings_review_required",
            ),
            false_fragment_heading_count=translation_quality_report.get("false_fragment_heading_count"),
            false_fragment_heading_gate_source=translation_quality_report.get("false_fragment_heading_gate_source"),
            raw_false_fragment_heading_count=translation_quality_report.get("raw_false_fragment_heading_count"),
        )
        add_check(
            "residual_bullet_glyphs_present",
            _coerce_int(translation_quality_report.get("residual_bullet_glyph_count")) == 0
            or translation_quality_reason_is_review_only(
                translation_quality_report,
                reason="residual_bullet_glyphs_review_required",
            ),
            residual_bullet_glyph_count=translation_quality_report.get("residual_bullet_glyph_count"),
            residual_bullet_glyph_gate_source=translation_quality_report.get("residual_bullet_glyph_gate_source"),
            residual_bullet_glyph_classification=translation_quality_report.get("residual_bullet_glyph_classification"),
            raw_residual_bullet_glyph_count=translation_quality_report.get("raw_residual_bullet_glyph_count"),
        )
        add_check(
            "list_fragment_regressions_present",
            _coerce_int(translation_quality_report.get("list_fragment_regression_count")) == 0
            or translation_quality_reason_is_review_only(
                translation_quality_report,
                reason="list_fragment_regressions_review_required",
            ),
            list_fragment_regression_count=translation_quality_report.get("list_fragment_regression_count"),
            list_fragment_regression_gate_source=translation_quality_report.get("list_fragment_regression_gate_source"),
            raw_list_fragment_regression_count=translation_quality_report.get("raw_list_fragment_regression_count"),
            review_reason=(
                "list_fragment_regressions_review_required"
                if translation_quality_reason_is_review_only(
                    translation_quality_report,
                    reason="list_fragment_regressions_review_required",
                )
                else None
            ),
        )
        add_check(
            "mixed_script_terms_present",
            _coerce_int(translation_quality_report.get("mixed_script_term_count")) == 0
            or translation_quality_reason_is_review_only(
                translation_quality_report,
                reason="mixed_script_terms_review_required",
            ),
            mixed_script_term_count=translation_quality_report.get("mixed_script_term_count"),
            mixed_script_term_gate_source=translation_quality_report.get("mixed_script_term_gate_source"),
            mixed_script_term_classification=translation_quality_report.get("mixed_script_term_classification"),
            raw_mixed_script_term_count=translation_quality_report.get("raw_mixed_script_term_count"),
        )
        add_check(
            "theology_style_deterministic_issues_present",
            True,
            theology_style_deterministic_issue_count=translation_quality_report.get("theology_style_deterministic_issue_count"),
            theology_style_deterministic_issue_source=translation_quality_report.get("theology_style_deterministic_issue_source"),
            theology_style_deterministic_issue_classification=translation_quality_report.get(
                "theology_style_deterministic_issue_classification"
            ),
            raw_theology_style_deterministic_issue_count=translation_quality_report.get(
                "raw_theology_style_deterministic_issue_count"
            ),
            failed_reason="advisory_only",
        )
    if require_no_toc_body_concat:
        toc_body_concat_check = build_acceptance_toc_body_concat_check(
            preparation_diagnostic_snapshot=preparation_diagnostic_snapshot,
            translation_quality_report=translation_quality_report,
        )
        add_check(
            str(toc_body_concat_check["name"]),
            bool(toc_body_concat_check["passed"]),
            toc_body_concat_detected=toc_body_concat_check.get("toc_body_concat_detected"),
            toc_body_concat_markdown_detected=toc_body_concat_check.get("toc_body_concat_markdown_detected"),
            toc_body_concat_structure_detected=toc_body_concat_check.get("toc_body_concat_structure_detected"),
            toc_body_concat_gate_source=toc_body_concat_check.get("toc_body_concat_gate_source"),
            structure_repair_toc_body_boundary_repairs=toc_body_concat_check.get(
                "structure_repair_toc_body_boundary_repairs"
            ),
            effective_source_toc_region_count=toc_body_concat_check.get("effective_source_toc_region_count"),
            document_map_toc_region_count=toc_body_concat_check.get("document_map_toc_region_count"),
            topology_toc_entry_count=toc_body_concat_check.get("topology_toc_entry_count"),
            topology_split_compound_toc_operation_count=toc_body_concat_check.get(
                "topology_split_compound_toc_operation_count"
            ),
            document_map_compound_toc_split_hint_count=toc_body_concat_check.get(
                "document_map_compound_toc_split_hint_count"
            ),
        )

    if structural_checks_builder is not None:
        for structural_check in structural_checks_builder(processing_operation):
            checks.append(dict(structural_check))
    else:
        add_check(
            "structural_comparison_available",
            False,
            applicable=False,
            reason="source_or_output_docx_missing",
        )

    failed_checks = [
        check["name"]
        for check in checks
        if check.get("applicable", True) and not bool(check["passed"])
    ]
    return {
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "checks": checks,
    }
