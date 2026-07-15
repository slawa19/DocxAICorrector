"""Pure preparation-diagnostic snapshot/metric appliers from
``validation/structural.py`` (spec 034, Step 6).

The side-effect-free subset of the snapshot/metric field appliers: structure-summary
and structure-validation field application, layout-signals backfill, prepared
snapshot/metric field application, preparation-error fallbacks, quality-gate reason
humanization, and first-block predicate helpers. Depends only on stdlib / typing, on
``derive_layout_signals`` (``structure.layout_signals``), and on the lower validation
leaves (``structural_metrics_common`` / ``structural_event_log`` / ``structural_toc_signals``
/ ``structural_unit_alignment``) -- never on the ``structural`` orchestration module -- so
no import cycle is introduced. Bodies are byte-identical to their former in-module
definitions; ``structural`` re-exports them (including the run_lietaer trio
``_apply_prepared_snapshot_fields`` / ``_apply_prepared_metric_fields`` /
``_normalize_snapshot_or_metric_statuses``) so the qualified names keep resolving.
The orchestration anchors (``build_preparation_diagnostic_snapshot``,
``_build_preparation_diagnostic_defaults``,
``_build_preparation_diagnostic_snapshot_from_source``) stay resident in ``structural``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
import re
from typing import Any, cast

from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.structure.layout_signals import derive_layout_signals
from docxaicorrector.validation.structural_event_log import _extract_event_context_int_list
from docxaicorrector.validation.structural_metrics_common import _as_int
from docxaicorrector.validation.structural_toc_signals import (
    _count_document_map_anchor_roles,
    _count_topology_toc_entry_units,
    _derive_toc_body_concat_gate_fields,
    _has_high_confidence_bounded_document_map_toc_region,
)
from docxaicorrector.validation.structural_unit_alignment import _derive_unit_aware_unmapped_fields


_HUMANIZED_QUALITY_GATE_REASON_TO_CODE: dict[str, str] = {
    "обнаружен TOC-подобный фрагмент без надёжно выделенной границы": "toc_like_sequence_without_bounded_region",
    "AI-распознавание структуры не внесло изменений для документа с высоким структурным риском": "structure_recognition_noop_on_high_risk",
    "перед обработкой требуется structural repair документа": "structural_repair_required_before_processing",
    "после подготовки остались изолированные маркеры списка": "isolated_list_markers_remaining",
    "первый блок смешивает элементы оглавления и эпиграфа": "first_block_mixed_toc_and_epigraph",
    "первый блок смешивает элементы оглавления и начало основного текста": "first_block_mixed_toc_and_body_start",
    "мало явных заголовков": "low_explicit_heading_density",
    "много коротких body-абзацев": "high_suspicious_short_body_ratio",
    "обнаружен TOC-подобный фрагмент": "toc_like_sequence_detected",
    "слишком много body-абзацев в ВЕРХНЕМ РЕГИСТРЕ или по центру": "high_all_caps_or_centered_body_ratio",
    "есть риск потери заголовочной структуры": "heading_only_collapse_risk",
    "остались изолированные маркеры списков": "isolated_list_marker_fragments",
    "обнаружен риск крупного фронт-маттер блока без безопасной границы": "large_front_matter_block_risk",
    "заголовков значительно меньше, чем ожидается по оглавлению": "heading_count_far_below_toc_expectation",
    "документ высокого риска не прошёл structural repair": "high_risk_without_structure_repair",
}


def _normalize_snapshot_or_metric_statuses(payload: dict[str, object]) -> None:
    quality_gate_status = str(payload.get("quality_gate_status") or "").strip()
    readiness_status = str(payload.get("readiness_status") or "").strip()
    if not quality_gate_status:
        payload["quality_gate_status"] = "unknown"
    if not readiness_status:
        payload["readiness_status"] = "unknown"
    if payload.get("quality_gate_reasons") is None:
        payload["quality_gate_reasons"] = []
    if payload.get("readiness_reasons") is None:
        payload["readiness_reasons"] = []


def _apply_structure_summary_snapshot_fields(snapshot: dict[str, object], structure_summary: object | None) -> None:
    if structure_summary is None:
        return
    if not bool(snapshot.get("ai_first_degraded", False)):
        snapshot["ai_first_degraded"] = bool(getattr(structure_summary, "ai_first_degraded", False))
    if not str(snapshot.get("fallback_stage") or ""):
        fallback_stage = str(getattr(structure_summary, "fallback_stage", "") or "").strip()
        if fallback_stage:
            snapshot["fallback_stage"] = fallback_stage
    if not str(snapshot.get("fallback_reason") or ""):
        fallback_reason = str(getattr(structure_summary, "fallback_reason", "") or "").strip()
        if fallback_reason:
            snapshot["fallback_reason"] = fallback_reason
    if not bool(snapshot.get("document_map_present", False)):
        snapshot["document_map_present"] = bool(getattr(structure_summary, "document_map_present", False))
    fallback_stats = getattr(structure_summary, "fallback_stats", None)
    fallback_metrics = {
        "structure_window_split_count": int(getattr(fallback_stats, "structure_window_split_count", 0) or 0),
        "structure_max_fallback_depth": int(getattr(fallback_stats, "structure_max_fallback_depth", 0) or 0),
        "structure_split_fallback_descriptor_count": int(
            getattr(fallback_stats, "structure_split_fallback_descriptor_count", 0) or 0
        ),
        "structure_timeout_retry_count": int(getattr(fallback_stats, "structure_timeout_retry_count", 0) or 0),
        "structure_timeout_retry_succeeded_count": int(
            getattr(fallback_stats, "structure_timeout_retry_succeeded_count", 0) or 0
        ),
        "structure_timeout_retry_failed_count": int(
            getattr(fallback_stats, "structure_timeout_retry_failed_count", 0) or 0
        ),
        "structure_split_fallback_capped_descriptor_count": int(
            getattr(fallback_stats, "structure_split_fallback_capped_descriptor_count", 0) or 0
        ),
        "structure_primary_classified_count": int(
            getattr(structure_summary, "structure_primary_classified_count", 0) or 0
        ),
        "structure_retry_classified_count": int(
            getattr(structure_summary, "structure_retry_classified_count", 0) or 0
        ),
        "structure_split_fallback_classified_count": int(
            getattr(structure_summary, "structure_split_fallback_classified_count", 0) or 0
        ),
    }
    for key, value in fallback_metrics.items():
        if _as_int(snapshot, key) == 0:
            snapshot[key] = value


def _build_layout_signals_snapshot_context(
    *,
    layout_signals: object,
    paragraphs: Sequence[object],
) -> dict[str, object]:
    tiers = tuple(getattr(layout_signals, "tiers", ()) or ())
    return {
        "body_baseline_pt": getattr(layout_signals, "body_baseline_pt", None),
        "tier_count": len(tiers),
        "heading_tier_count": sum(1 for tier in tiers if bool(getattr(tier, "is_heading_candidate", False))),
        "paragraphs_with_font_size_count": sum(
            1 for paragraph in paragraphs if getattr(paragraph, "font_size_pt", None) is not None
        ),
        "heading_ratio": float(getattr(layout_signals, "heading_ratio", 1.15) or 1.15),
    }


def _maybe_backfill_layout_signals_snapshot(
    snapshot: dict[str, object],
    *,
    paragraphs: Sequence[object],
    app_config: Mapping[str, Any] | None,
) -> None:
    if snapshot.get("document_topology_layout_signals") is not None:
        return
    if app_config is None:
        return
    if not bool(app_config.get("structure_recovery_topology_projection_enabled", False)):
        return
    if not bool(app_config.get("structure_recovery_topology_projection_layout_signals_enabled", False)):
        return
    if not paragraphs:
        return
    try:
        layout_signals = derive_layout_signals(
            cast(Sequence[ParagraphUnit], paragraphs),
            heading_ratio=float(app_config.get("structure_recovery_topology_projection_layout_signals_heading_ratio", 1.15) or 1.15),
            short_line_chars=int(app_config.get("structure_recovery_topology_projection_layout_signals_short_line_chars", 80) or 80),
            baseline_tolerance_pt=float(app_config.get("structure_recovery_topology_projection_layout_signals_baseline_tolerance_pt", 0.25) or 0.25),
            min_tier_population=int(app_config.get("structure_recovery_topology_projection_layout_signals_min_tier_population", 2) or 2),
        )
    except Exception:
        return
    snapshot["document_topology_layout_signals"] = _build_layout_signals_snapshot_context(
        layout_signals=layout_signals,
        paragraphs=paragraphs,
    )


def _apply_prepared_snapshot_fields(
    snapshot: dict[str, object],
    prepared: object,
    *,
    app_config: Mapping[str, Any] | None = None,
) -> None:
    structure_validation_report = getattr(prepared, "structure_validation_report", None)
    structure_summary = getattr(prepared, "structure_recognition_summary", None)
    prepared_document_map = getattr(prepared, "document_map", None)
    prepared_topology_projection = getattr(prepared, "document_topology_projection", None)
    prepared_paragraphs = tuple(getattr(prepared, "paragraphs", ()) or ())
    _apply_structure_validation_snapshot_fields(snapshot, structure_validation_report)
    _apply_structure_summary_snapshot_fields(snapshot, structure_summary)
    if not str(snapshot.get("quality_gate_status") or ""):
        snapshot["quality_gate_status"] = str(getattr(prepared, "quality_gate_status", "") or "")
    if not list(cast(list[str], snapshot.get("quality_gate_reasons") or [])):
        snapshot["quality_gate_reasons"] = [
            str(reason)
            for reason in tuple(getattr(prepared, "quality_gate_reasons", ()) or ())
            if str(reason).strip()
        ]
    if not bool(snapshot.get("structure_ai_attempted")):
        snapshot["structure_ai_attempted"] = bool(getattr(prepared, "structure_ai_attempted", False))
    if _as_int(snapshot, "ai_classified_count") == 0:
        snapshot["ai_classified_count"] = int(getattr(prepared, "ai_classified_count", 0) or 0)
    if _as_int(snapshot, "ai_heading_count") == 0:
        snapshot["ai_heading_count"] = int(getattr(prepared, "ai_heading_count", 0) or 0)
    prepared_structure_map = getattr(prepared, "structure_map", None)
    prepared_fallback_stats = getattr(prepared_structure_map, "fallback_stats", None)
    for key in (
        "structure_window_split_count",
        "structure_max_fallback_depth",
        "structure_split_fallback_descriptor_count",
        "structure_timeout_retry_count",
        "structure_timeout_retry_succeeded_count",
        "structure_timeout_retry_failed_count",
        "structure_split_fallback_capped_descriptor_count",
    ):
        if _as_int(snapshot, key) == 0:
            snapshot[key] = int(getattr(prepared_fallback_stats, key, 0) or 0)
    prepared_fallback_provenance_metrics = (
        prepared_structure_map.fallback_provenance_metrics() if prepared_structure_map is not None else {}
    )
    for key in (
        "structure_primary_classified_count",
        "structure_retry_classified_count",
        "structure_split_fallback_classified_count",
    ):
        if _as_int(snapshot, key) == 0:
            snapshot[key] = int(prepared_fallback_provenance_metrics.get(key, 0) or 0)
    current_document_map_status = str(snapshot.get("document_map_status") or "").strip().lower()
    prepared_document_map_status = str(getattr(prepared, "document_map_status", "") or "").strip()
    if prepared_document_map_status and current_document_map_status in {"", "not_requested"}:
        snapshot["document_map_status"] = prepared_document_map_status
    if "document_map_status_reason" not in snapshot:
        snapshot["document_map_status_reason"] = ""
    current_document_map_status_reason = str(snapshot.get("document_map_status_reason") or "")
    prepared_document_map_status_reason = str(getattr(prepared, "document_map_status_reason", "") or "").strip()
    if not current_document_map_status_reason and prepared_document_map_status_reason:
        snapshot["document_map_status_reason"] = prepared_document_map_status_reason
    if not bool(snapshot.get("document_map_present", False)):
        snapshot["document_map_present"] = bool(prepared_document_map is not None)
    if _has_high_confidence_bounded_document_map_toc_region(prepared_document_map):
        if _as_int(snapshot, "bounded_toc_region_count") < 1:
            snapshot["bounded_toc_region_count"] = 1
        toc_header_count = _count_document_map_anchor_roles(prepared_document_map, role="toc_header")
        if toc_header_count > _as_int(snapshot, "toc_header_count"):
            snapshot["toc_header_count"] = toc_header_count
        toc_entry_count = _count_document_map_anchor_roles(prepared_document_map, role="toc_entry")
        if toc_entry_count > _as_int(snapshot, "toc_entry_count"):
            snapshot["toc_entry_count"] = toc_entry_count
    current_topology_status = str(snapshot.get("document_topology_projection_status") or "").strip().lower()
    prepared_topology_status = str(getattr(prepared, "document_topology_projection_status", "") or "").strip()
    if prepared_topology_status and current_topology_status in {"", "not_requested"}:
        snapshot["document_topology_projection_status"] = prepared_topology_status
    current_topology_reason = str(snapshot.get("document_topology_projection_status_reason") or "")
    prepared_topology_reason = str(getattr(prepared, "document_topology_projection_status_reason", "") or "").strip()
    if not current_topology_reason and prepared_topology_reason:
        snapshot["document_topology_projection_status_reason"] = prepared_topology_reason
    if prepared_topology_projection is not None:
        snapshot["document_topology_projection"] = asdict(prepared_topology_projection)
        topology_toc_entry_count = _count_topology_toc_entry_units(prepared_topology_projection)
        if topology_toc_entry_count > _as_int(snapshot, "toc_entry_count"):
            snapshot["toc_entry_count"] = topology_toc_entry_count
    document_map_toc_region_count = 1 if _has_high_confidence_bounded_document_map_toc_region(prepared_document_map) else 0
    document_map_toc_detected = bool(
        document_map_toc_region_count
        or _count_document_map_anchor_roles(prepared_document_map, role="toc_header")
        or _count_document_map_anchor_roles(prepared_document_map, role="toc_entry")
    )
    if document_map_toc_detected:
        snapshot["document_map_toc_detected"] = True
    if document_map_toc_region_count > _as_int(snapshot, "document_map_toc_region_count"):
        snapshot["document_map_toc_region_count"] = document_map_toc_region_count
    topology_toc_entry_count = _count_topology_toc_entry_units(prepared_topology_projection)
    if topology_toc_entry_count > _as_int(snapshot, "topology_toc_entry_count"):
        snapshot["topology_toc_entry_count"] = topology_toc_entry_count
    if prepared_document_map is not None or prepared_topology_projection is not None:
        markdown_detected = bool(
            snapshot.get(
                "toc_body_concat_markdown_detected",
                snapshot.get("toc_body_concat_detected", False),
            )
        )
        snapshot.update(
            {
                key: value
                for key, value in _derive_toc_body_concat_gate_fields(
                    document_map=prepared_document_map,
                    topology_projection=prepared_topology_projection,
                    markdown_detected=markdown_detected,
                ).items()
                if key
                in {
                    "toc_body_concat_detected",
                    "toc_body_concat_markdown_detected",
                    "toc_body_concat_structure_detected",
                    "toc_body_concat_gate_source",
                    "topology_split_compound_toc_operation_count",
                    "topology_merge_heading_operation_count",
                    "document_map_compound_toc_split_hint_count",
                }
            }
        )
    _maybe_backfill_layout_signals_snapshot(
        snapshot,
        paragraphs=prepared_paragraphs,
        app_config=app_config,
    )
    _apply_quality_gate_readiness_fallback(snapshot)
    _normalize_snapshot_or_metric_statuses(snapshot)
def _apply_structure_validation_snapshot_fields(snapshot: dict[str, object], structure_validation_report: object) -> None:
    toc_region_bounded_count = getattr(structure_validation_report, "toc_region_bounded_count", None)
    if toc_region_bounded_count is not None and int(toc_region_bounded_count or 0) > _as_int(snapshot, "bounded_toc_region_count"):
        snapshot["bounded_toc_region_count"] = int(toc_region_bounded_count or 0)
    if not str(snapshot.get("readiness_status") or ""):
        snapshot["readiness_status"] = str(getattr(structure_validation_report, "readiness_status", "") or "")
    if not list(cast(list[str], snapshot.get("readiness_reasons") or [])):
        snapshot["readiness_reasons"] = [
            str(reason)
            for reason in tuple(getattr(structure_validation_report, "readiness_reasons", ()) or ())
            if str(reason).strip()
        ]
    if not bool(snapshot.get("document_map_present")):
        snapshot["document_map_present"] = bool(getattr(structure_validation_report, "document_map_present", False))
    if snapshot.get("outline_coverage_ratio") is None:
        outline_coverage_ratio = getattr(structure_validation_report, "outline_coverage_ratio", None)
        if outline_coverage_ratio is not None:
            snapshot["outline_coverage_ratio"] = float(outline_coverage_ratio)


def _apply_quality_gate_readiness_fallback(snapshot: dict[str, object]) -> None:
    if str(snapshot.get("readiness_status") or ""):
        return
    quality_gate_status = str(snapshot.get("quality_gate_status") or "").strip().lower()
    quality_gate_reasons = [str(reason).strip() for reason in list(cast(list[str], snapshot.get("quality_gate_reasons") or [])) if str(reason).strip()]
    if quality_gate_status == "pass":
        snapshot["readiness_status"] = "ready"
        return
    if quality_gate_status == "blocked":
        snapshot["readiness_status"] = _infer_readiness_status_from_quality_gate_reasons(quality_gate_reasons)


def _apply_prepared_metric_fields(
    metrics: dict[str, object],
    prepared: object,
    *,
    source_paragraphs: Sequence[object] | None = None,
    formatting_payload: Mapping[str, object] | None = None,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> None:
    structure_validation_report = getattr(prepared, "structure_validation_report", None)
    structure_summary = getattr(prepared, "structure_recognition_summary", None)
    prepared_document_map = getattr(prepared, "document_map", None)
    prepared_topology_projection = getattr(prepared, "document_topology_projection", None)
    if not str(metrics.get("quality_gate_status") or ""):
        metrics["quality_gate_status"] = str(getattr(prepared, "quality_gate_status", "") or "")
    if not list(cast(list[str], metrics.get("quality_gate_reasons") or [])):
        metrics["quality_gate_reasons"] = [
            str(reason)
            for reason in tuple(getattr(prepared, "quality_gate_reasons", ()) or ())
            if str(reason).strip()
        ]
    if not str(metrics.get("readiness_status") or ""):
        metrics["readiness_status"] = str(getattr(structure_validation_report, "readiness_status", "") or "")
    document_map_toc_region_count = 1 if _has_high_confidence_bounded_document_map_toc_region(prepared_document_map) else 0
    document_map_toc_detected = bool(
        document_map_toc_region_count
        or _count_document_map_anchor_roles(prepared_document_map, role="toc_header")
        or _count_document_map_anchor_roles(prepared_document_map, role="toc_entry")
    )
    topology_toc_entry_count = _count_topology_toc_entry_units(prepared_topology_projection)
    if document_map_toc_detected:
        metrics["document_map_toc_detected"] = True
    if document_map_toc_region_count > _as_int(metrics, "document_map_toc_region_count"):
        metrics["document_map_toc_region_count"] = document_map_toc_region_count
    if topology_toc_entry_count > _as_int(metrics, "topology_toc_entry_count"):
        metrics["topology_toc_entry_count"] = topology_toc_entry_count
    markdown_detected = bool(
        metrics.get(
            "toc_body_concat_markdown_detected",
            metrics.get("toc_body_concat_detected", False),
        )
    )
    metrics.update(
        _derive_toc_body_concat_gate_fields(
            document_map=prepared_document_map,
            topology_projection=prepared_topology_projection,
            markdown_detected=markdown_detected,
        )
    )
    if source_paragraphs is not None:
        metrics.update(
            _derive_unit_aware_unmapped_fields(
                source_paragraphs=source_paragraphs,
                topology_projection=prepared_topology_projection,
                formatting_payload=formatting_payload,
                generated_paragraph_registry=generated_paragraph_registry,
            )
        )
    _apply_structure_summary_snapshot_fields(metrics, structure_summary)
    _normalize_snapshot_or_metric_statuses(metrics)


def _apply_preparation_error_snapshot_fallback(snapshot: dict[str, object], preparation_error: str) -> None:
    normalized = preparation_error.strip().casefold()
    if not normalized:
        return
    detailed_reasons = _extract_quality_gate_reasons_from_error(preparation_error)
    quality_gate_blocked = "quality gate" in normalized
    if "quality gate" in normalized and not str(snapshot.get("quality_gate_status") or ""):
        snapshot["quality_gate_status"] = "blocked"
    if detailed_reasons:
        if not list(cast(list[str], snapshot.get("quality_gate_reasons") or [])):
            snapshot["quality_gate_reasons"] = detailed_reasons
        if not list(cast(list[str], snapshot.get("readiness_reasons") or [])):
            snapshot["readiness_reasons"] = detailed_reasons
    if quality_gate_blocked and str(snapshot.get("quality_gate_status") or "").strip().lower() == "blocked":
        effective_reasons = [
            str(reason).strip()
            for reason in list(cast(list[str], snapshot.get("quality_gate_reasons") or []))
            if str(reason).strip()
        ]
        current_readiness_status = str(snapshot.get("readiness_status") or "").strip().lower()
        if current_readiness_status in {"", "ready", "unknown"}:
            snapshot["readiness_status"] = _infer_readiness_status_from_quality_gate_reasons(effective_reasons)
    if "structural repair" in normalized:
        snapshot["readiness_status"] = _infer_readiness_status_from_quality_gate_reasons(detailed_reasons)
        if not list(cast(list[str], snapshot.get("readiness_reasons") or [])):
            snapshot["readiness_reasons"] = ["structural_repair_required_before_processing"]
        if not list(cast(list[str], snapshot.get("quality_gate_reasons") or [])):
            snapshot["quality_gate_reasons"] = ["structural_repair_required_before_processing"]
    if "structure_recognition_noop_on_high_risk" in detailed_reasons:
        snapshot["structure_ai_attempted"] = True
        if _as_int(snapshot, "ai_classified_count") == 0:
            snapshot["ai_classified_count"] = 0
        if _as_int(snapshot, "ai_heading_count") == 0:
            snapshot["ai_heading_count"] = 0


def _extract_quality_gate_reasons_from_error(preparation_error: str) -> list[str]:
    match = re.search(r"Причины:\s*(.+)$", preparation_error)
    if match is None:
        return []
    parsed = [reason.strip() for reason in match.group(1).split(",") if reason.strip()]
    return [_HUMANIZED_QUALITY_GATE_REASON_TO_CODE.get(reason, reason) for reason in parsed]


def _infer_readiness_status_from_quality_gate_reasons(reasons: Sequence[str]) -> str:
    normalized = {str(reason).strip() for reason in reasons if str(reason).strip()}
    if not normalized:
        return "blocked_needs_structure_repair"
    unsafe_best_effort_reasons = {
        "toc_like_sequence_without_bounded_region",
        "isolated_list_markers_remaining",
        "large_front_matter_block_risk",
        "heading_count_far_below_toc_expectation",
    }
    if normalized & unsafe_best_effort_reasons:
        return "blocked_unsafe_best_effort_only"
    return "blocked_needs_structure_repair"


def _extract_first_block_target_chars(
    *,
    event_log: Sequence[Mapping[str, object]],
    semantic_blocks: Sequence[object],
) -> int:
    first_block_target_chars = _extract_event_context_int_list(event_log, "block_plan_summary", "first_block_target_chars")
    if first_block_target_chars:
        return first_block_target_chars[0]
    if not semantic_blocks:
        return 0
    return len(str(getattr(semantic_blocks[0], "text", "") or ""))


def _block_has_toc(paragraphs: Sequence[object]) -> bool:
    return any(
        str(getattr(paragraph, "structural_role", "") or "").strip().lower() in {"toc_header", "toc_entry"}
        for paragraph in paragraphs
    )


def _block_has_epigraph(paragraphs: Sequence[object]) -> bool:
    return any(
        str(getattr(paragraph, "structural_role", "") or "").strip().lower() in {"epigraph", "attribution", "dedication"}
        for paragraph in paragraphs
    )


def _block_has_body_start(paragraphs: Sequence[object]) -> bool:
    for paragraph in paragraphs:
        role = str(getattr(paragraph, "role", "") or "").strip().lower()
        structural_role = str(getattr(paragraph, "structural_role", "") or "body").strip().lower() or "body"
        if role in {"heading", "body", "list"} and structural_role not in {"toc_header", "toc_entry", "epigraph", "attribution", "dedication"}:
            return True
    return False


def _block_has_isolated_marker(paragraphs: Sequence[object]) -> bool:
    for paragraph in paragraphs:
        if _is_isolated_marker_text(str(getattr(paragraph, "text", "") or "")):
            return True
    return False


def _is_isolated_marker_text(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return bool(re.match(r"^(?:[\-\*•●]|\d+[\.)])$", normalized))
