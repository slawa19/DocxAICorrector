"""Pure preparation-diagnostic snapshot/metric appliers from
``validation/structural.py`` (spec 034, Step 6).

The side-effect-free subset of the snapshot/metric field appliers: structure-validation
field application, prepared snapshot/metric field application, preparation-error
fallbacks, quality-gate reason humanization, and first-block predicate helpers. Depends
only on stdlib / typing and on the lower validation leaves (``structural_metrics_common`` /
``structural_event_log`` / ``structural_toc_signals`` / ``structural_unit_alignment``) --
never on the ``structural`` orchestration module -- so no import cycle is introduced.
``structural`` re-exports them (including the run_lietaer trio
``_apply_prepared_snapshot_fields`` / ``_apply_prepared_metric_fields`` /
``_normalize_snapshot_or_metric_statuses``) so the qualified names keep resolving.
The orchestration anchors (``build_preparation_diagnostic_snapshot``,
``_build_preparation_diagnostic_defaults``,
``_build_preparation_diagnostic_snapshot_from_source``) stay resident in ``structural``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import cast

from docxaicorrector.validation.structural_event_log import _extract_event_context_int_list
from docxaicorrector.validation.structural_metrics_common import _as_int
from docxaicorrector.validation.structural_toc_signals import _derive_toc_body_concat_gate_fields
from docxaicorrector.validation.structural_unit_alignment import _derive_unit_aware_unmapped_fields


# Reverse of the humanized reasons that ``processing/preparation.py`` (``_REASON_LABELS``)
# actually puts into a "Причины: ..." preparation error. Only produced strings belong here:
# an entry nobody produces is a dead branch with a live test (spec 066 C-10).
_HUMANIZED_QUALITY_GATE_REASON_TO_CODE: dict[str, str] = {
    "первый блок смешивает элементы оглавления и эпиграфа": "first_block_mixed_toc_and_epigraph",
    "первый блок смешивает элементы оглавления и начало основного текста": "first_block_mixed_toc_and_body_start",
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


def _apply_prepared_snapshot_fields(snapshot: dict[str, object], prepared: object) -> None:
    structure_validation_report = getattr(prepared, "structure_validation_report", None)
    _apply_structure_validation_snapshot_fields(snapshot, structure_validation_report)
    if not str(snapshot.get("quality_gate_status") or ""):
        snapshot["quality_gate_status"] = str(getattr(prepared, "quality_gate_status", "") or "")
    if not list(cast(list[str], snapshot.get("quality_gate_reasons") or [])):
        snapshot["quality_gate_reasons"] = [
            str(reason)
            for reason in tuple(getattr(prepared, "quality_gate_reasons", ()) or ())
            if str(reason).strip()
        ]
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
    formatting_payload: Mapping[str, object] | None = None,
) -> None:
    structure_validation_report = getattr(prepared, "structure_validation_report", None)
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
    markdown_detected = bool(
        metrics.get(
            "toc_body_concat_markdown_detected",
            metrics.get("toc_body_concat_detected", False),
        )
    )
    metrics.update(_derive_toc_body_concat_gate_fields(markdown_detected=markdown_detected))
    metrics.update(_derive_unit_aware_unmapped_fields(formatting_payload=formatting_payload))
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
