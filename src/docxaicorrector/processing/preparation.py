from collections import Counter, OrderedDict
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import hashlib
import inspect
import json
import logging
from io import BytesIO
from pathlib import Path
from threading import Event, Lock
from collections.abc import Mapping, Sequence
from typing import Any, cast

from docx import Document as DocxDocument

from docxaicorrector.core.config import get_client, get_client_for_model_selector, get_model_role_value, load_app_config
from docxaicorrector.core.constants import RUN_DIR
from docxaicorrector.document._document import (
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    extract_document_content_with_normalization_reports,
    summarize_boundary_normalization_metrics,
)
from docxaicorrector.document.relations import build_paragraph_relations
from docxaicorrector.core.logger import log_event
from docxaicorrector.core.models import DocumentMap, DocumentTopologyProjection, LayoutArtifactCleanupReport, ParagraphBoundaryNormalizationReport, ParagraphRelation, RelationNormalizationReport
from docxaicorrector.core.models import StructureFallbackStats, StructureRecognitionSummary
from docxaicorrector.core.models import StructureRepairReport
from docxaicorrector.core.models import clone_prepared_image_asset
from docxaicorrector.core.models import normalize_heuristic_list_kind_hint, normalize_heuristic_role_hint, normalize_heuristic_structural_role_hint
from docxaicorrector.core.models import StructureMap
from docxaicorrector.processing.processing_runtime import FrozenUploadPayload, HeartbeatBeacon, build_in_memory_uploaded_file
from docxaicorrector.runtime.artifact_retention import (
    DOCUMENT_TOPOLOGY_MAX_AGE_SECONDS,
    DOCUMENT_TOPOLOGY_MAX_COUNT,
    STRUCTURE_MAPS_MAX_AGE_SECONDS,
    STRUCTURE_MAPS_MAX_COUNT,
    prune_artifact_dir,
)
from docxaicorrector.document.segments import (
    CHAPTER_SEGMENTS_DETECTOR_VERSION,
    DocumentContextProfile,
    DocumentSegment,
    GlossaryTerm,
    SegmentDetectionReport,
    SegmentOutlineEntry,
    build_segment_to_job_mapping,
    detect_document_segments,
    resolve_segment_hard_boundary_paragraph_ids,
    validate_segment_coverage,
)
from docxaicorrector.document.structure_authority import get_effective_structural_role
from docxaicorrector.structure.document_map import (
    DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION,
    DOCUMENT_MAP_OUTLINE_MEMBERSHIP_SCHEMA_VERSION,
    DOCUMENT_MAP_POSTPROCESS_VERSION,
    DOCUMENT_MAP_PROMPT_VERSION,
    DOCUMENT_MAP_SPLIT_HINT_SCHEMA_VERSION,
    DocumentMapRequestTimeout,
    DocumentMapSchemaError,
    build_document_map,
)
from docxaicorrector.structure.recognition import (
    STRUCTURE_RECOGNITION_DESCRIPTOR_SCHEMA_VERSION,
    STRUCTURE_RECOGNITION_PROMPT_VERSION,
    StructureRecognitionRequestTimeout,
    apply_structure_map,
    build_structure_map,
)
from docxaicorrector.structure.reconciliation import (
    RECONCILIATION_TARGETED_DESCRIPTOR_SCHEMA_VERSION,
    RECONCILIATION_TARGETED_PROMPT_VERSION,
    ReconciliationReport,
    STRUCTURE_RECONCILIATION_SCHEMA_VERSION,
    _build_targeted_selection,
    reconcile_with_document_map,
    selection_has_authority_uncertainty_context,
    targeted_reclassify_with_reconciliation_context,
)
from docxaicorrector.structure.topology import TOPOLOGY_PROJECTION_SCHEMA_VERSION, apply_document_map_topology
from docxaicorrector.structure.validation import StructureValidationReport, validate_structure_quality, write_structure_validation_debug_artifact
from docxaicorrector.text.translation_domains import build_terminology_plan, build_translation_domain_instructions


_REASON_LABELS: dict[str, str] = {
    "structure_recognition_noop_on_high_risk": "AI-распознавание структуры не внесло изменений для документа с высоким структурным риском",
    "toc_like_sequence_without_bounded_region": "обнаружен TOC-подобный фрагмент без надёжно выделенной границы",
    "structural_repair_required_before_processing": "перед обработкой требуется structural repair документа",
    "isolated_list_markers_remaining": "после подготовки остались изолированные маркеры списка",
    "first_block_mixed_toc_and_epigraph": "первый блок смешивает элементы оглавления и эпиграфа",
    "first_block_mixed_toc_and_body_start": "первый блок смешивает элементы оглавления и начало основного текста",
    "low_explicit_heading_density": "мало явных заголовков",
    "high_suspicious_short_body_ratio": "много коротких body-абзацев",
    "toc_like_sequence_detected": "обнаружен TOC-подобный фрагмент",
    "high_all_caps_or_centered_body_ratio": "слишком много body-абзацев в ВЕРХНЕМ РЕГИСТРЕ или по центру",
    "heading_only_collapse_risk": "есть риск потери заголовочной структуры",
    "isolated_list_marker_fragments": "остались изолированные маркеры списков",
    "large_front_matter_block_risk": "обнаружен риск крупного фронт-маттер блока без безопасной границы",
    "heading_count_far_below_toc_expectation": "заголовков значительно меньше, чем ожидается по оглавлению",
    "high_risk_without_structure_repair": "документ высокого риска не прошёл structural repair",
}


def humanize_quality_gate_reason(reason: str) -> str:
    normalized = str(reason or "").strip()
    return _REASON_LABELS.get(normalized, normalized.replace("_", " "))


def humanize_quality_gate_reasons(reasons) -> list[str]:
    return [humanize_quality_gate_reason(str(reason).strip()) for reason in reasons or () if str(reason).strip()]


def _format_ai_first_fallback_reason(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return type(exc).__name__


def _is_structure_provider_runtime_error(exc: RuntimeError) -> bool:
    message = str(exc or "").strip().lower()
    if message == "unsupported structure recognition client":
        return True
    return any(
        marker in message
        for marker in (
            "api_key",
            "api key",
            "selector",
            "provider",
            "disabled",
            "отключ",
            "не найден",
            "missing api key",
        )
    )


def _is_document_map_provider_runtime_error(exc: RuntimeError) -> bool:
    message = str(exc or "").strip().lower()
    if message == "unsupported document-map client":
        return True
    return any(
        marker in message
        for marker in (
            "api_key",
            "api key",
            "selector",
            "provider",
            "disabled",
            "отключ",
            "не найден",
            "missing api key",
            "generation failed without a terminal result",
            "terminal result",
        )
    )


def _resolve_downstream_structure_phase(*, structure_ai_attempted: bool, structure_summary: StructureRecognitionSummary) -> str:
    if not structure_ai_attempted:
        return "pre_ai_diagnostic"
    if structure_summary.ai_first_degraded:
        return "ai_first_degraded_fallback"
    return "post_ai_final"


def _build_paragraph_relations_with_optional_phase(*, paragraphs, enabled_relation_kinds, structure_phase: str, document_map=None):
    try:
        return build_paragraph_relations(
            paragraphs,
            enabled_relation_kinds=enabled_relation_kinds,
            structure_phase=structure_phase,
            document_map=document_map,
        )
    except TypeError as exc:
        if "structure_phase" not in str(exc) and "document_map" not in str(exc):
            raise
        try:
            return build_paragraph_relations(
                paragraphs,
                enabled_relation_kinds=enabled_relation_kinds,
                structure_phase=structure_phase,
            )
        except TypeError as inner_exc:
            if "structure_phase" not in str(inner_exc):
                raise
            return build_paragraph_relations(
                paragraphs,
                enabled_relation_kinds=enabled_relation_kinds,
            )


def _record_document_map_state(
    state: dict[str, object] | None,
    *,
    status: str,
    reason: str = "",
    document_map_present: bool,
) -> None:
    if state is None:
        return
    state["document_map_status"] = str(status or "").strip().lower() or "not_requested"
    state["document_map_status_reason"] = str(reason or "").strip()
    state["document_map_present"] = document_map_present


def _client_factory_accepts_model_selector(get_client_fn) -> bool:
    try:
        signature = inspect.signature(get_client_fn)
    except (TypeError, ValueError):
        return False
    parameters = list(signature.parameters.values())
    if any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters):
        return True
    positional_parameters = [
        parameter
        for parameter in parameters
        if parameter.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    return bool(positional_parameters)


def _resolve_responses_client_for_model(*, get_client_fn, model_selector: str, app_config: Mapping[str, Any]) -> object:
    if get_client_fn is get_client:
        return get_client_for_model_selector(
            model_selector,
            "responses_text",
            config_like=app_config,
        )
    if not _client_factory_accepts_model_selector(get_client_fn):
        return get_client_fn()

    try:
        signature = inspect.signature(get_client_fn)
    except (TypeError, ValueError):
        return get_client_fn()
    parameters = list(signature.parameters.values())
    accepts_varargs = any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters)
    accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    accepts_config_like = accepts_kwargs or "config_like" in signature.parameters
    positional_parameters = [
        parameter
        for parameter in parameters
        if parameter.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    if accepts_varargs or len(positional_parameters) >= 2:
        if accepts_config_like:
            return get_client_fn(model_selector, "responses_text", config_like=app_config)
        return get_client_fn(model_selector, "responses_text")
    return get_client_fn(model_selector)


def _relation_report_phase_and_source(report: RelationNormalizationReport | None) -> tuple[str, str]:
    if report is None or not report.decisions:
        return "", ""
    first_decision = report.decisions[0]
    return (
        str(getattr(first_decision, "structure_phase", "") or "").strip(),
        str(getattr(first_decision, "structure_source", "") or "").strip(),
    )


def _build_ai_first_degraded_summary(*, fallback_stage: str, reason: str, document_map_present: bool) -> StructureRecognitionSummary:
    return StructureRecognitionSummary(
        ai_first_degraded=True,
        fallback_stage=fallback_stage,
        fallback_reason=reason,
        document_map_present=document_map_present,
    )


def _record_ai_first_fallback(
    fallback_state: dict[str, object] | None,
    *,
    fallback_stage: str,
    reason: str,
    document_map_present: bool,
) -> None:
    if fallback_state is None:
        return
    fallback_state["ai_first_degraded"] = True
    fallback_state["fallback_stage"] = fallback_stage
    fallback_state["fallback_reason"] = reason
    fallback_state["document_map_present"] = document_map_present


def _finalize_ai_first_structure_summary(
    *,
    structure_summary: StructureRecognitionSummary,
    fallback_state: Mapping[str, object] | None,
    document_map_present: bool,
) -> StructureRecognitionSummary:
    normalized_summary = StructureRecognitionSummary.from_source(structure_summary)
    fallback_state = fallback_state or {}
    fallback_degraded = bool(fallback_state.get("ai_first_degraded", False))
    fallback_stage = str(fallback_state.get("fallback_stage", "") or "")
    fallback_reason = str(fallback_state.get("fallback_reason", "") or "")
    resolved_document_map_present = (
        normalized_summary.document_map_present
        or bool(fallback_state.get("document_map_present", False))
        or document_map_present
    )

    if fallback_degraded and not normalized_summary.ai_first_degraded:
        return replace(
            normalized_summary,
            ai_first_degraded=True,
            fallback_stage=fallback_stage,
            fallback_reason=fallback_reason,
            document_map_present=resolved_document_map_present,
        )

    if not normalized_summary.ai_first_degraded:
        return normalized_summary

    resolved_fallback_stage = normalized_summary.fallback_stage or fallback_stage
    resolved_fallback_reason = normalized_summary.fallback_reason or fallback_reason
    if (
        resolved_fallback_stage != normalized_summary.fallback_stage
        or resolved_fallback_reason != normalized_summary.fallback_reason
        or resolved_document_map_present != normalized_summary.document_map_present
    ):
        return replace(
            normalized_summary,
            fallback_stage=resolved_fallback_stage,
            fallback_reason=resolved_fallback_reason,
            document_map_present=resolved_document_map_present,
        )
    return normalized_summary


@dataclass
class PreparedDocumentData:
    source_text: str
    paragraphs: list
    image_assets: list
    relations: list[ParagraphRelation]
    jobs: list[dict[str, Any]]
    prepared_source_key: str
    segments: list[DocumentSegment] | None = None
    segment_diagnostics: SegmentDetectionReport = field(default_factory=SegmentDetectionReport)
    structure_fingerprint: str = ""
    detector_version: str = CHAPTER_SEGMENTS_DETECTOR_VERSION
    segment_to_job: dict[str, tuple[int, ...]] | None = None
    source_format: str = "docx"
    conversion_backend: str | None = None
    normalization_report: ParagraphBoundaryNormalizationReport | None = None
    relation_report: RelationNormalizationReport | None = None
    cleanup_report: LayoutArtifactCleanupReport | None = None
    structure_repair_report: StructureRepairReport | None = None
    document_map: DocumentMap | None = None
    document_topology_projection: DocumentTopologyProjection | None = None
    document_map_status: str = "not_requested"
    document_map_status_reason: str = ""
    document_topology_projection_status: str = "not_requested"
    document_topology_projection_status_reason: str = ""
    structure_map: StructureMap | None = None
    structure_recognition_summary: StructureRecognitionSummary = field(default_factory=StructureRecognitionSummary)
    structure_validation_report: StructureValidationReport | None = None
    structure_recognition_mode: str = "off"
    structure_ai_attempted: bool = False
    quality_gate_status: str = "pass"
    quality_gate_reasons: tuple[str, ...] = ()
    translation_domain: str = "general"
    translation_domain_instructions: str = ""
    document_context_profile: DocumentContextProfile = field(default_factory=DocumentContextProfile)
    cached: bool = False

    @property
    def ai_classified_count(self) -> int:
        return self.structure_recognition_summary.ai_classified_count

    @property
    def ai_heading_count(self) -> int:
        return self.structure_recognition_summary.ai_heading_count

    @property
    def ai_role_change_count(self) -> int:
        return self.structure_recognition_summary.ai_role_change_count

    @property
    def ai_heading_promotion_count(self) -> int:
        return self.structure_recognition_summary.ai_heading_promotion_count

    @property
    def ai_heading_demotion_count(self) -> int:
        return self.structure_recognition_summary.ai_heading_demotion_count

    @property
    def ai_structural_role_change_count(self) -> int:
        return self.structure_recognition_summary.ai_structural_role_change_count


def _build_normalization_metrics(
    normalization_report: ParagraphBoundaryNormalizationReport | None,
    relation_report: RelationNormalizationReport | None = None,
    cleanup_report: LayoutArtifactCleanupReport | None = None,
    structure_repair_report: StructureRepairReport | None = None,
) -> dict[str, int]:
    metrics: dict[str, int] = {}
    if normalization_report is not None:
        metrics.update(
            {
                "raw_paragraph_count": normalization_report.total_raw_paragraphs,
                "logical_paragraph_count": normalization_report.total_logical_paragraphs,
                "merged_group_count": normalization_report.merged_group_count,
                "merged_raw_paragraph_count": normalization_report.merged_raw_paragraph_count,
            }
        )
        metrics.update(summarize_boundary_normalization_metrics(normalization_report))
    if relation_report is not None:
        metrics.update(
            {
                "relation_count": relation_report.total_relations,
                "rejected_relation_candidate_count": relation_report.rejected_candidate_count,
            }
        )
        for relation_kind, count in relation_report.relation_counts.items():
            metrics[f"relation_{relation_kind}_count"] = count
    if cleanup_report is not None:
        metrics.update(flatten_layout_cleanup_metrics(cleanup_report))
    if structure_repair_report is not None:
        metrics.update(flatten_structure_repair_metrics(structure_repair_report))
    return metrics


def flatten_layout_cleanup_metrics(cleanup_report) -> dict[str, int]:
    if cleanup_report is None:
        return {}
    cleanup_mode = str(getattr(cleanup_report, "cleanup_mode", "remove") or "remove").strip().lower()
    if cleanup_mode == "flag":
        return {
            "layout_cleanup_removed_count": int(getattr(cleanup_report, "flagged_page_number_count", 0) or 0)
            + int(getattr(cleanup_report, "flagged_repeated_artifact_count", 0) or 0)
            + int(getattr(cleanup_report, "flagged_empty_or_whitespace_count", 0) or 0),
            "layout_cleanup_page_number_count": int(getattr(cleanup_report, "flagged_page_number_count", 0) or 0),
            "layout_cleanup_repeated_artifact_count": int(
                getattr(cleanup_report, "flagged_repeated_artifact_count", 0) or 0
            ),
            "layout_cleanup_empty_or_whitespace_count": int(
                getattr(cleanup_report, "flagged_empty_or_whitespace_count", 0) or 0
            ),
        }
    return {
        "layout_cleanup_removed_count": int(getattr(cleanup_report, "removed_paragraph_count", 0) or 0),
        "layout_cleanup_page_number_count": int(getattr(cleanup_report, "removed_page_number_count", 0) or 0),
        "layout_cleanup_repeated_artifact_count": int(getattr(cleanup_report, "removed_repeated_artifact_count", 0) or 0),
        "layout_cleanup_empty_or_whitespace_count": int(
            getattr(cleanup_report, "removed_empty_or_whitespace_count", 0) or 0
        ),
    }


def flatten_structure_repair_metrics(structure_repair_report) -> dict[str, int]:
    if structure_repair_report is None:
        return {}
    return {
        "structure_repair_bullet_items": int(getattr(structure_repair_report, "repaired_bullet_items", 0) or 0),
        "structure_repair_numbered_items": int(getattr(structure_repair_report, "repaired_numbered_items", 0) or 0),
        "structure_repair_bounded_toc_regions": int(getattr(structure_repair_report, "bounded_toc_regions", 0) or 0),
        "structure_repair_toc_body_boundary_repairs": int(
            getattr(structure_repair_report, "toc_body_boundary_repairs", 0) or 0
        ),
        "structure_repair_heading_candidates_from_toc": int(
            getattr(structure_repair_report, "heading_candidates_from_toc", 0) or 0
        ),
        "structure_repair_remaining_isolated_markers": int(
            getattr(structure_repair_report, "remaining_isolated_marker_count", 0) or 0
        ),
    }


def _build_preparation_stage_metrics(
    *,
    paragraph_count: int,
    image_count: int,
    normalization_report: ParagraphBoundaryNormalizationReport | None,
    relation_report: RelationNormalizationReport | None,
    cleanup_report: LayoutArtifactCleanupReport | None = None,
    structure_repair_report: StructureRepairReport | None = None,
    structure_map: StructureMap | None = None,
    structure_summary: StructureRecognitionSummary | None = None,
    source_text: str | None = None,
    block_count: int | None = None,
) -> dict[str, int]:
    metrics = {
        "paragraph_count": paragraph_count,
        "image_count": image_count,
        **_build_normalization_metrics(normalization_report, relation_report, cleanup_report, structure_repair_report),
    }
    if source_text is not None:
        metrics["source_chars"] = len(source_text)
    if block_count is not None:
        metrics["block_count"] = block_count
    if structure_summary is not None:
        metrics.update(structure_summary.as_progress_metrics(structure_map=structure_map))
    return metrics


def _capture_structure_baseline(paragraphs: list) -> dict[int, tuple[str, str, str | None, int | None, str | None]]:
    return {
        int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1))): (
            paragraph.role,
            paragraph.structural_role,
            paragraph.heading_source,
            paragraph.heading_level,
            paragraph.role_confidence,
        )
        for paragraph in paragraphs
    }


def _restore_structure_baseline(*, baseline: dict[int, tuple[str, str, str | None, int | None, str | None]], paragraphs: list) -> None:
    for paragraph in paragraphs:
        logical_index = int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1)))
        previous = baseline.get(logical_index)
        if previous is None:
            continue
        previous_role, previous_structural_role, previous_heading_source, previous_heading_level, previous_role_confidence = previous
        paragraph.role = previous_role
        paragraph.structural_role = previous_structural_role
        paragraph.heading_source = previous_heading_source
        paragraph.heading_level = previous_heading_level
        paragraph.role_confidence = previous_role_confidence


def _build_structure_divergence_metrics(*, baseline: dict[int, tuple[str, str, str | None, int | None, str | None]], paragraphs: list) -> dict[str, int]:
    metrics = {
        "ai_role_changes": 0,
        "ai_heading_promotions": 0,
        "ai_heading_demotions": 0,
        "ai_structural_role_changes": 0,
    }
    for paragraph in paragraphs:
        if paragraph.role_confidence != "ai":
            continue
        logical_index = int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1)))
        previous = baseline.get(logical_index)
        if previous is None:
            continue
        previous_role, previous_structural_role, _previous_heading_source, _previous_heading_level, _previous_role_confidence = previous
        if previous_role != paragraph.role:
            metrics["ai_role_changes"] += 1
        if previous_role != "heading" and paragraph.role == "heading":
            metrics["ai_heading_promotions"] += 1
        elif previous_role == "heading" and paragraph.role != "heading":
            metrics["ai_heading_demotions"] += 1
        if previous_structural_role != paragraph.structural_role:
            metrics["ai_structural_role_changes"] += 1
    return metrics


_STRUCTURE_MAP_CACHE_LIMIT = 8
_structure_map_cache: OrderedDict[str, StructureMap] = OrderedDict()
_structure_map_cache_lock = Lock()
_STRUCTURE_MAP_DEBUG_DIR = RUN_DIR / "structure_maps"
_RECONCILIATION_REPORT_DEBUG_DIR = RUN_DIR / "reconciliation_reports"
_DOCUMENT_TOPOLOGY_DEBUG_DIR = RUN_DIR / "document_topology"
_DOCUMENT_MAP_CACHE_LIMIT = 8
_document_map_cache: OrderedDict[str, DocumentMap] = OrderedDict()
_document_map_cache_lock = Lock()
_DOCUMENT_MAP_DEBUG_DIR = RUN_DIR / "document_maps"
STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION = 1


def _build_structure_recognition_summary(
    *,
    applied_metrics: dict[str, int],
    divergence_metrics: dict[str, int],
    structure_map: StructureMap | None,
) -> StructureRecognitionSummary:
    fallback_provenance_metrics = {} if structure_map is None else structure_map.fallback_provenance_metrics()
    return StructureRecognitionSummary(
        ai_classified_count=int(applied_metrics.get("ai_classified", 0) or 0),
        ai_heading_count=int(applied_metrics.get("ai_headings", 0) or 0),
        ai_role_change_count=int(divergence_metrics.get("ai_role_changes", 0) or 0),
        ai_heading_promotion_count=int(divergence_metrics.get("ai_heading_promotions", 0) or 0),
        ai_heading_demotion_count=int(divergence_metrics.get("ai_heading_demotions", 0) or 0),
        ai_structural_role_change_count=int(divergence_metrics.get("ai_structural_role_changes", 0) or 0),
        reconciliation_patch_count=int(applied_metrics.get("reconciliation_patches_applied", 0) or 0),
        reconciliation_locked_override_count=int(applied_metrics.get("reconciliation_locked_overrides_applied", 0) or 0),
        reconciliation_locked_override_skip_count=int(applied_metrics.get("reconciliation_locked_overrides_skipped", 0) or 0),
        fallback_stats=StructureFallbackStats.from_source(None if structure_map is None else structure_map.fallback_stats),
        structure_primary_classified_count=int(fallback_provenance_metrics.get("structure_primary_classified_count", 0) or 0),
        structure_retry_classified_count=int(fallback_provenance_metrics.get("structure_retry_classified_count", 0) or 0),
        structure_split_fallback_classified_count=int(
            fallback_provenance_metrics.get("structure_split_fallback_classified_count", 0) or 0
        ),
    )


def _format_structure_escalation_reasons(report: StructureValidationReport | None) -> str:
    if report is None or not report.escalation_reasons:
        return ""
    return ", ".join(humanize_quality_gate_reason(reason) for reason in report.escalation_reasons)


def build_structure_repair_status_note(structure_repair_report) -> str:
    if structure_repair_report is None or not bool(getattr(structure_repair_report, "applied", False)):
        return ""
    bullet_items = int(getattr(structure_repair_report, "repaired_bullet_items", 0) or 0)
    numbered_items = int(getattr(structure_repair_report, "repaired_numbered_items", 0) or 0)
    toc_regions = int(getattr(structure_repair_report, "bounded_toc_regions", 0) or 0)
    heading_candidates = int(getattr(structure_repair_report, "heading_candidates_from_toc", 0) or 0)
    return (
        "Восстановление структуры: "
        f"списки {bullet_items + numbered_items}, TOC-регионов {toc_regions}, подсказок заголовков {heading_candidates}."
    )


def build_structure_processing_status_note(source: object | None) -> str:
    if source is None:
        return ""

    mode = str(getattr(source, "structure_recognition_mode", "off") or "off").strip().lower()
    validation_report = getattr(source, "structure_validation_report", None)
    structure_map = getattr(source, "structure_map", None)
    structure_summary = StructureRecognitionSummary.from_source(getattr(source, "structure_recognition_summary", None))
    ai_attempted = bool(getattr(source, "structure_ai_attempted", False))
    escalation_reasons = _format_structure_escalation_reasons(validation_report)
    readiness_status = str(getattr(validation_report, "readiness_status", "") or "")
    if structure_summary.ai_first_degraded:
        stage = structure_summary.fallback_stage or "unknown"
        reason = structure_summary.fallback_reason or "unspecified"
        if structure_map is not None and structure_summary.ai_classified_count > 0:
            return (
                f"Структура: AI-first degraded ({stage}); продолжен ограниченный fallback-путь, "
                f"классифицировано {structure_summary.ai_classified_count} абзацев. Причина: {reason}."
            )
        return f"Структура: AI-first degraded ({stage}); использованы текущие правила. Причина: {reason}."

    if mode == "off":
        return "Структура: AI выключен, использованы текущие правила."
    if mode == "auto":
        if validation_report is None:
            return "Структура: auto-режим без gate-отчёта, использованы текущие правила."
        if not bool(validation_report.escalation_recommended):
            return "Структура: auto-режим, эскалация в AI не потребовалась; структурный риск не найден."
        reason_suffix = f" Причины: {escalation_reasons}." if escalation_reasons else ""
        if not ai_attempted or structure_map is None:
            return f"Структура: auto-режим, выполнена эскалация в AI; AI недоступен, использованы текущие правила.{reason_suffix}"
        if structure_summary.ai_classified_count > 0:
            return (
                "Структура: auto-режим, выполнена эскалация в AI; "
                f"классифицировано {structure_summary.ai_classified_count} абзацев, "
                f"найдено {structure_summary.ai_heading_count} заголовков.{reason_suffix}"
            )
        if readiness_status in {"blocked_needs_structure_repair", "blocked_unsafe_best_effort_only"}:
            return (
                "Структура: auto-режим, выполнена эскалация в AI; AI не внёс изменений, документ помечен как "
                f"требующий structural repair.{reason_suffix}"
            )
        return f"Структура: auto-режим, выполнена эскалация в AI; AI не внёс изменений.{reason_suffix}"
    if mode == "always":
        if not ai_attempted or structure_map is None:
            return "Структура: режим always, AI недоступен, использованы текущие правила."
        if structure_summary.ai_classified_count > 0:
            return (
                "Структура: режим always, AI-распознавание выполнено; "
                f"классифицировано {structure_summary.ai_classified_count} абзацев, "
                f"найдено {structure_summary.ai_heading_count} заголовков."
            )
        return "Структура: режим always, AI-распознавание выполнено, но изменений не внесло."
    return ""


def _build_structure_map_cache_key(
    *,
    paragraphs: list,
    app_config: Mapping[str, Any],
    document_map: DocumentMap | None = None,
    topology_projection: DocumentTopologyProjection | None = None,
    resolved_model: str | None = None,
) -> str:
    structure_recovery_mode = str(app_config.get("structure_recovery_mode", "ai_first") or "ai_first").strip().lower()
    structure_recovery_enabled = bool(app_config.get("structure_recovery_enabled", False))
    coordinate_schema_version = int(
        app_config.get("structure_recovery_coordinate_schema_version", STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION)
        or STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION
    )
    max_window_paragraphs, overlap_paragraphs, preview_chars, target_input_tokens = _resolve_structure_recognition_window_settings(
        app_config=app_config,
        document_map=document_map,
    )
    payload = {
        "stage": "structure_recognition_v1",
        "model": resolved_model or get_model_role_value(app_config, "structure_recognition"),
        "prompt_version": STRUCTURE_RECOGNITION_PROMPT_VERSION,
        "descriptor_schema_version": STRUCTURE_RECOGNITION_DESCRIPTOR_SCHEMA_VERSION,
        "reconciliation_schema_version": STRUCTURE_RECONCILIATION_SCHEMA_VERSION,
        "reconciliation_targeted_enabled": bool(app_config.get("structure_recovery_reconciliation_targeted_enabled", False)),
        "reconciliation_targeted_prompt_version": RECONCILIATION_TARGETED_PROMPT_VERSION,
        "reconciliation_targeted_descriptor_schema_version": RECONCILIATION_TARGETED_DESCRIPTOR_SCHEMA_VERSION,
        "reconciliation_targeted_threshold": (
            int(app_config.get("structure_recovery_reconciliation_targeted_threshold", 3) or 3)
            if bool(app_config.get("structure_recovery_reconciliation_targeted_enabled", False))
            else None
        ),
        "reconciliation_targeted_timeout_seconds": (
            float(app_config.get("structure_recovery_reconciliation_targeted_timeout_seconds", 45) or 45)
            if bool(app_config.get("structure_recovery_reconciliation_targeted_enabled", False))
            else None
        ),
        "reconciliation_targeted_max_paragraphs": (
            int(app_config.get("structure_recovery_reconciliation_targeted_max_paragraphs", 60) or 60)
            if bool(app_config.get("structure_recovery_reconciliation_targeted_enabled", False))
            else None
        ),
        "max_window_paragraphs": max_window_paragraphs,
        "overlap_paragraphs": overlap_paragraphs,
        "preview_chars": preview_chars,
        "target_input_tokens": target_input_tokens,
        "split_fallback_max_depth": int(app_config.get("structure_recognition_split_fallback_max_depth", 3) or 3),
        "split_fallback_max_expansions": int(app_config.get("structure_recognition_split_fallback_max_expansions", 8) or 8),
        "structure_recovery_enabled": structure_recovery_enabled,
        "structure_recovery_mode": structure_recovery_mode,
        "coordinate_schema_version": coordinate_schema_version,
        "topology_projection_schema_version": TOPOLOGY_PROJECTION_SCHEMA_VERSION,
        "topology_projection_enabled": bool(app_config.get("structure_recovery_topology_projection_enabled", False)),
        "topology_projection_cache_key": None if topology_projection is None else topology_projection.cache_key,
        "topology_projection_units": None
        if topology_projection is None
        else [
            {
                "unit_id": unit.unit_id,
                "unit_type": unit.unit_type,
                "logical_indexes": list(unit.logical_indexes),
                "canonical_text": unit.canonical_text,
                "heading_level": unit.heading_level,
                "authority": unit.authority,
            }
            for unit in topology_projection.projected_units
        ],
        "document_map_anchor_fingerprint": [
            {
                "index": int(index),
                "role": str(anchor.role or "body"),
                "heading_level": anchor.heading_level,
                "confidence": str(anchor.confidence or "low"),
            }
            for index, anchor in sorted((document_map.paragraph_anchors or {}).items())
        ]
        if document_map is not None
        else None,
        "paragraphs": [
            {
                "index": int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1))),
                "text": str(paragraph.text or ""),
                "style_name": str(paragraph.style_name or ""),
                "is_bold": bool(paragraph.is_bold),
                "paragraph_alignment": paragraph.paragraph_alignment,
                "font_size_pt": paragraph.font_size_pt,
                "list_kind": paragraph.list_kind,
                "heading_level": paragraph.heading_level if paragraph.heading_source == "explicit" else None,
            }
            for paragraph in paragraphs
        ],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _resolve_structure_recognition_window_settings(
    *,
    app_config: Mapping[str, Any],
    document_map: DocumentMap | None,
) -> tuple[int, int, int, int | None]:
    if document_map is not None:
        return (
            int(app_config.get("structure_recovery_anchored_classification_max_window_paragraphs", 3000) or 3000),
            int(app_config.get("structure_recovery_anchored_classification_overlap_paragraphs", 0) or 0),
            int(app_config.get("structure_recovery_anchored_classification_preview_chars", 1500) or 1500),
            int(app_config.get("structure_recovery_anchored_classification_target_input_tokens", 180000) or 180000),
        )
    return (
        int(app_config.get("structure_recognition_max_window_paragraphs", 1800) or 1800),
        int(app_config.get("structure_recognition_overlap_paragraphs", 50) or 50),
        600,
        None,
    )


def _build_document_map_cache_key(*, paragraphs: list, app_config: Mapping[str, Any]) -> str:
    structure_recovery_mode = str(app_config.get("structure_recovery_mode", "ai_first") or "ai_first").strip().lower()
    structure_recovery_enabled = bool(app_config.get("structure_recovery_enabled", False))
    coordinate_schema_version = int(
        app_config.get("structure_recovery_coordinate_schema_version", STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION)
        or STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION
    )
    preview_chars = int(app_config.get("structure_recovery_document_map_preview_chars", 120) or 120)
    payload = {
        "stage": "document_map_v1",
        "model": str(app_config.get("structure_recovery_document_map_model", "") or ""),
        "max_input_paragraphs": int(app_config.get("structure_recovery_document_map_max_input_paragraphs", 6000) or 6000),
        "max_input_tokens": int(app_config.get("structure_recovery_document_map_max_input_tokens", 180000) or 180000),
        "preview_chars": preview_chars,
        "prompt_version": DOCUMENT_MAP_PROMPT_VERSION,
        "descriptor_schema_version": DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION,
        "postprocess_version": DOCUMENT_MAP_POSTPROCESS_VERSION,
        "split_hint_schema_version": DOCUMENT_MAP_SPLIT_HINT_SCHEMA_VERSION,
        "outline_membership_schema_version": DOCUMENT_MAP_OUTLINE_MEMBERSHIP_SCHEMA_VERSION,
        "structure_recovery_enabled": structure_recovery_enabled,
        "structure_recovery_mode": structure_recovery_mode,
        "coordinate_schema_version": coordinate_schema_version,
        "paragraphs": [
            {
                "index": int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1))),
                "text_preview": str(paragraph.text or "")[:preview_chars],
                "style_name": str(paragraph.style_name or ""),
                "is_bold": bool(getattr(paragraph, "is_bold", False)),
                "paragraph_alignment": getattr(paragraph, "paragraph_alignment", None),
                "font_size_pt": getattr(paragraph, "font_size_pt", None),
                "explicit_heading_level": getattr(paragraph, "heading_level", None)
                if getattr(paragraph, "heading_source", None) == "explicit"
                else None,
                "heuristic_role_hint": normalize_heuristic_role_hint(getattr(paragraph, "heuristic_role_hint", None)),
                "heuristic_structural_role_hint": normalize_heuristic_structural_role_hint(
                    getattr(paragraph, "heuristic_structural_role_hint", None)
                ),
                "heuristic_list_kind_hint": normalize_heuristic_list_kind_hint(getattr(paragraph, "heuristic_list_kind_hint", None)),
                "heuristic_heading_level_hint": getattr(paragraph, "heuristic_heading_level_hint", None),
                "is_repeated_across_pages": bool(getattr(paragraph, "is_repeated_across_pages", False)),
                "is_likely_page_number": bool(getattr(paragraph, "is_likely_page_number", False)),
                "embedded_structure_hints": [
                    {
                        "text": str(getattr(hint, "text", "") or "")[:preview_chars],
                        "role": normalize_heuristic_role_hint(getattr(hint, "role", "body")) or "body",
                        "structural_role": normalize_heuristic_structural_role_hint(getattr(hint, "structural_role", "body"))
                        or "body",
                        "heading_level": getattr(hint, "heading_level", None),
                        "list_kind": normalize_heuristic_list_kind_hint(getattr(hint, "list_kind", None)),
                    }
                    for hint in getattr(paragraph, "heuristic_embedded_structure_hints", ()) or ()
                ],
            }
            for paragraph in paragraphs
        ],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _read_cached_structure_map(cache_key: str) -> StructureMap | None:
    with _structure_map_cache_lock:
        cached = _structure_map_cache.get(cache_key)
        if cached is None:
            return None
        _structure_map_cache.move_to_end(cache_key)
        return deepcopy(cached)


def _store_cached_structure_map(cache_key: str, structure_map: StructureMap) -> None:
    with _structure_map_cache_lock:
        _structure_map_cache[cache_key] = deepcopy(structure_map)
        _structure_map_cache.move_to_end(cache_key)
        while len(_structure_map_cache) > _STRUCTURE_MAP_CACHE_LIMIT:
            _structure_map_cache.popitem(last=False)


def _write_structure_map_debug_artifact(*, cache_key: str, structure_map: StructureMap, app_config: Mapping[str, Any]) -> str:
    _STRUCTURE_MAP_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = _STRUCTURE_MAP_DEBUG_DIR / f"{cache_key}.json"
    coordinate_schema_version = int(
        app_config.get("structure_recovery_coordinate_schema_version", STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION)
        or STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION
    )
    artifact_path.write_text(
        json.dumps(
            {
                "cache_key": cache_key,
                "stage": "structure_recognition_v1",
                "model": get_model_role_value(app_config, "structure_recognition"),
                "prompt_version": STRUCTURE_RECOGNITION_PROMPT_VERSION,
                "descriptor_schema_version": STRUCTURE_RECOGNITION_DESCRIPTOR_SCHEMA_VERSION,
                "coordinate_schema_version": coordinate_schema_version,
                "window_count": structure_map.window_count,
                "classified_count": structure_map.classified_count,
                "heading_count": structure_map.heading_count,
                "fallback_stats": structure_map.fallback_stats.as_metrics(),
                "total_tokens_used": structure_map.total_tokens_used,
                "processing_time_seconds": structure_map.processing_time_seconds,
                "classifications": [
                    {
                        "index": classification.index,
                        "role": classification.role,
                        "heading_level": classification.heading_level,
                        "confidence": classification.confidence,
                    }
                    for classification in structure_map.classifications.values()
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    prune_artifact_dir(
        target_dir=_STRUCTURE_MAP_DEBUG_DIR,
        max_age_seconds=STRUCTURE_MAPS_MAX_AGE_SECONDS,
        max_count=STRUCTURE_MAPS_MAX_COUNT,
    )
    return str(artifact_path)


def _read_cached_document_map(cache_key: str) -> DocumentMap | None:
    with _document_map_cache_lock:
        cached = _document_map_cache.get(cache_key)
        if cached is None:
            return None
        _document_map_cache.move_to_end(cache_key)
        return deepcopy(cached)


def _store_cached_document_map(cache_key: str, document_map: DocumentMap) -> None:
    with _document_map_cache_lock:
        _document_map_cache[cache_key] = deepcopy(document_map)
        _document_map_cache.move_to_end(cache_key)
        while len(_document_map_cache) > _DOCUMENT_MAP_CACHE_LIMIT:
            _document_map_cache.popitem(last=False)


def _write_document_map_debug_artifact(*, cache_key: str, document_map: DocumentMap, app_config: Mapping[str, Any]) -> str:
    _DOCUMENT_MAP_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = _DOCUMENT_MAP_DEBUG_DIR / f"{cache_key}.json"
    coordinate_schema_version = int(
        app_config.get("structure_recovery_coordinate_schema_version", STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION)
        or STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION
    )
    artifact_path.write_text(
        json.dumps(
            {
                "cache_key": cache_key,
                "stage": "document_map_v1",
                "model": str(app_config.get("structure_recovery_document_map_model", "") or ""),
                "prompt_version": DOCUMENT_MAP_PROMPT_VERSION,
                "descriptor_schema_version": DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION,
                "postprocess_version": DOCUMENT_MAP_POSTPROCESS_VERSION,
                "split_hint_schema_version": DOCUMENT_MAP_SPLIT_HINT_SCHEMA_VERSION,
                "coordinate_schema_version": coordinate_schema_version,
                "sampled": bool(document_map.sampled),
                "sampled_logical_indexes": list(document_map.sampled_logical_indexes),
                "total_tokens_used": int(document_map.total_tokens_used or 0),
                "processing_time_seconds": float(document_map.processing_time_seconds or 0.0),
                "document_map": asdict(document_map),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    prune_artifact_dir(
        target_dir=_DOCUMENT_MAP_DEBUG_DIR,
        max_age_seconds=STRUCTURE_MAPS_MAX_AGE_SECONDS,
        max_count=STRUCTURE_MAPS_MAX_COUNT,
    )
    return str(artifact_path)


def _write_document_topology_debug_artifact(*, projection: DocumentTopologyProjection) -> str:
    _DOCUMENT_TOPOLOGY_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = _DOCUMENT_TOPOLOGY_DEBUG_DIR / f"{projection.cache_key}.json"
    artifact_path.write_text(json.dumps(asdict(projection), ensure_ascii=False, indent=2), encoding="utf-8")
    prune_artifact_dir(
        target_dir=_DOCUMENT_TOPOLOGY_DEBUG_DIR,
        max_age_seconds=DOCUMENT_TOPOLOGY_MAX_AGE_SECONDS,
        max_count=DOCUMENT_TOPOLOGY_MAX_COUNT,
    )
    return str(artifact_path)


def _write_reconciliation_report_artifact(
    *,
    cache_key: str,
    report: ReconciliationReport,
    app_config: Mapping[str, Any],
) -> str:
    _RECONCILIATION_REPORT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = _RECONCILIATION_REPORT_DEBUG_DIR / f"{cache_key}.json"
    coordinate_schema_version = int(
        app_config.get("structure_recovery_coordinate_schema_version", STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION)
        or STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION
    )
    artifact_path.write_text(
        json.dumps(
            {
                "cache_key": cache_key,
                "stage": "reconciliation_v1",
                "reconciliation_schema_version": STRUCTURE_RECONCILIATION_SCHEMA_VERSION,
                "targeted_prompt_version": RECONCILIATION_TARGETED_PROMPT_VERSION,
                "targeted_descriptor_schema_version": RECONCILIATION_TARGETED_DESCRIPTOR_SCHEMA_VERSION,
                "coordinate_schema_version": coordinate_schema_version,
                "report": {
                    "missing_outline_entries": list(report.missing_outline_entries),
                    "unexpected_headings": list(report.unexpected_headings),
                    "toc_entries_without_body_match": list(report.toc_entries_without_body_match),
                    "front_matter_leaks": list(report.front_matter_leaks),
                    "front_matter_body_advisories": list(report.front_matter_body_advisories),
                    "anchor_disagreements_seen": list(report.anchor_disagreements_seen),
                    "targeted_recall_invoked": report.targeted_recall_invoked,
                    "targeted_recall_count": report.targeted_recall_count,
                    "targeted_selected_logical_indexes": list(report.targeted_selected_logical_indexes),
                    "targeted_selection_reasons": [
                        {
                            "logical_index": selection.logical_index,
                            "reasons": list(selection.reasons),
                        }
                        for selection in report.targeted_selection_reasons
                    ],
                    "outline_coverage_ratio": report.outline_coverage_ratio,
                    "patched_logical_indexes": list(report.patched_logical_indexes),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    prune_artifact_dir(
        target_dir=_RECONCILIATION_REPORT_DEBUG_DIR,
        max_age_seconds=STRUCTURE_MAPS_MAX_AGE_SECONDS,
        max_count=STRUCTURE_MAPS_MAX_COUNT,
    )
    return str(artifact_path)


def _run_structure_recognition(
    *,
    paragraphs: list,
    image_assets: list,
    app_config: Mapping[str, Any],
    get_client_fn,
    progress_callback,
    normalization_report,
    relation_report,
    cleanup_report=None,
    document_map: DocumentMap | None = None,
    topology_projection: DocumentTopologyProjection | None = None,
    source_format: str = "docx",
    conversion_backend: str | None = None,
) -> tuple[StructureMap | None, StructureRecognitionSummary]:
    base_metrics = _build_preparation_stage_metrics(
        paragraph_count=len(paragraphs),
        image_count=len(image_assets),
        normalization_report=normalization_report,
        relation_report=relation_report,
        cleanup_report=cleanup_report,
    )
    emit_preparation_progress(
        progress_callback,
        stage="Распознавание структуры…",
        detail="Анализирую роли абзацев с помощью AI.",
        progress=0.35,
        metrics={**base_metrics, "source_format": source_format, "conversion_backend": conversion_backend},
    )

    def _emit_structure_progress(event) -> None:
        event_metrics = {**base_metrics, "source_format": source_format, "conversion_backend": conversion_backend}
        if event.current_window is not None:
            event_metrics["structure_current_window"] = event.current_window
        if event.total_windows:
            event_metrics["structure_total_windows"] = event.total_windows
        if event.processed_windows:
            event_metrics["structure_processed_windows"] = event.processed_windows
        if event.descriptor_count is not None:
            event_metrics["structure_descriptor_count"] = event.descriptor_count
        if event.fallback_depth:
            event_metrics["structure_fallback_depth"] = event.fallback_depth
        if event.event == "prepared":
            detail = f"Подготовлено {event.descriptor_count or 0} абзацев, запускаю AI-классификацию."
        elif event.event == "window_started":
            detail = f"Ожидаю ответ модели для окна {event.current_window or 1}/{max(event.total_windows, 1)}."
        elif event.event == "window_failed":
            detail = f"Окно {event.current_window or 1}/{max(event.total_windows, 1)} не классифицировано, продолжаю по остальным окнам."
        elif event.event == "window_completed":
            detail = f"Анализирую роли абзацев с помощью AI (окно {event.processed_windows}/{max(event.total_windows, 1)})."
        elif event.event == "window_split":
            detail = "Таймаут AI на большом окне структуры; продолжаю меньшими окнами."
        elif event.event == "completed":
            detail = "AI-анализ завершён. Применяю структуру к документу."
        else:
            detail = "Анализирую роли абзацев с помощью AI."
        emit_preparation_progress(
            progress_callback,
            stage="Распознавание структуры…",
            detail=detail,
            progress=0.41,
            metrics=event_metrics,
        )

    baseline = _capture_structure_baseline(paragraphs)

    def _degrade_ai_first(*, fallback_stage: str, reason: str, detail: str) -> tuple[None, StructureRecognitionSummary]:
        log_event(
            logging.WARNING,
            "structure_recognition_fallback",
            "AI-распознавание структуры завершилось fallback-путём.",
            ai_first_degraded=True,
            fallback_stage=fallback_stage,
            document_map_present=document_map is not None,
            error_message=reason,
        )
        emit_preparation_progress(
            progress_callback,
            stage="Структура: деградация",
            detail=detail,
            progress=0.55,
            metrics={**base_metrics, "source_format": source_format, "conversion_backend": conversion_backend},
        )
        return None, _build_ai_first_degraded_summary(
            fallback_stage=fallback_stage,
            reason=reason,
            document_map_present=document_map is not None,
        )

    structure_map = None
    resolved_model: str | None = None
    cache_key: str | None = None
    if bool(app_config.get("structure_recognition_cache_enabled", True)):
        try:
            resolved_model = get_model_role_value(app_config, "structure_recognition")
            cache_key = _build_structure_map_cache_key(
                paragraphs=paragraphs,
                app_config=app_config,
                document_map=document_map,
                topology_projection=topology_projection,
                resolved_model=resolved_model,
            )
            structure_map = _read_cached_structure_map(cache_key)
        except Exception as exc:
            reason = _format_ai_first_fallback_reason(exc)
            return _degrade_ai_first(
                fallback_stage="stage2_structure_recognition_cache",
                reason=reason,
                detail="AI-first cache path недоступен. Используются текущие правила.",
            )
    if structure_map is None:
        try:
            max_window_paragraphs, overlap_paragraphs, preview_chars, target_input_tokens = _resolve_structure_recognition_window_settings(
                app_config=app_config,
                document_map=document_map,
            )
            if resolved_model is None:
                resolved_model = get_model_role_value(app_config, "structure_recognition")
            client = _resolve_responses_client_for_model(
                get_client_fn=get_client_fn,
                model_selector=resolved_model,
                app_config=app_config,
            )
            if cache_key is None:
                cache_key = _build_structure_map_cache_key(
                    paragraphs=paragraphs,
                    app_config=app_config,
                    document_map=document_map,
                    topology_projection=topology_projection,
                    resolved_model=resolved_model,
                )
            structure_map = build_structure_map(
                paragraphs,
                client=client,
                model=resolved_model,
                max_window_paragraphs=max_window_paragraphs,
                overlap_paragraphs=overlap_paragraphs,
                timeout=float(app_config.get("structure_recognition_timeout_seconds", 60) or 60),
                document_map=document_map,
                topology_projection=topology_projection,
                preview_chars=preview_chars,
                target_input_tokens=target_input_tokens,
                timeout_retry_multiplier=float(app_config.get("structure_recognition_timeout_retry_multiplier", 1.5) or 1.5),
                timeout_retry_max_seconds=float(app_config.get("structure_recognition_timeout_retry_max_seconds", 120) or 120),
                split_fallback_max_depth=int(app_config.get("structure_recognition_split_fallback_max_depth", 3) or 3),
                split_fallback_max_expansions=int(app_config.get("structure_recognition_split_fallback_max_expansions", 8) or 8),
                progress_callback=_emit_structure_progress,
            )
            if bool(app_config.get("structure_recognition_cache_enabled", True)):
                _store_cached_structure_map(cache_key, structure_map)
        except ValueError as exc:
            reason = _format_ai_first_fallback_reason(exc)
            return _degrade_ai_first(
                fallback_stage="stage2_structure_recognition_window",
                reason=reason,
                detail="AI-first window settings invalid. Используются текущие правила.",
            )
        except StructureRecognitionRequestTimeout as exc:
            reason = _format_ai_first_fallback_reason(exc)
            return _degrade_ai_first(
                fallback_stage="stage2_structure_recognition_provider",
                reason=reason,
                detail="AI-first provider path недоступен. Используются текущие правила.",
            )
        except RuntimeError as exc:
            if not _is_structure_provider_runtime_error(exc):
                raise
            reason = _format_ai_first_fallback_reason(exc)
            return _degrade_ai_first(
                fallback_stage="stage2_structure_recognition_provider",
                reason=reason,
                detail="AI-first provider path недоступен. Используются текущие правила.",
            )

    if document_map is not None:
        reconciliation_report = ReconciliationReport(outline_coverage_ratio=1.0)
        try:
            initial_reconciliation_report = reconciliation_report
            structure_map, reconciliation_report = reconcile_with_document_map(
                paragraphs,
                document_map,
                structure_map,
                topology_projection=topology_projection,
            )
            initial_reconciliation_report = reconciliation_report
            targeted_enabled = bool(app_config.get("structure_recovery_reconciliation_targeted_enabled", False))
            targeted_threshold = int(app_config.get("structure_recovery_reconciliation_targeted_threshold", 3) or 3)
            targeted_max_paragraphs = int(app_config.get("structure_recovery_reconciliation_targeted_max_paragraphs", 60) or 60)
            targeted_selection = None
            invoke_targeted_recall = False
            if targeted_enabled:
                targeted_selection = _build_targeted_selection(
                    paragraphs,
                    document_map=document_map,
                    report=reconciliation_report,
                    max_paragraphs=targeted_max_paragraphs,
                )
                advisory_only_front_matter_context = bool(reconciliation_report.front_matter_body_advisories) and (
                    reconciliation_report.actionable_divergence_count == 0
                    and all(
                        set(selection_reason.reasons).issubset({"body_start_neighborhood"})
                        for selection_reason in targeted_selection.reasons
                    )
                )
                invoke_targeted_recall = bool(targeted_selection.logical_indexes) and (
                    reconciliation_report.actionable_divergence_count > targeted_threshold
                    or (
                        selection_has_authority_uncertainty_context(targeted_selection)
                        and not advisory_only_front_matter_context
                    )
                )
            if invoke_targeted_recall:
                try:
                    targeted_kwargs = {
                        "client": _resolve_responses_client_for_model(
                            get_client_fn=get_client_fn,
                            model_selector=get_model_role_value(app_config, "structure_recognition"),
                            app_config=app_config,
                        ),
                        "model": get_model_role_value(app_config, "structure_recognition"),
                        "timeout": float(app_config.get("structure_recovery_reconciliation_targeted_timeout_seconds", 60) or 60),
                        "max_paragraphs": targeted_max_paragraphs,
                    }
                    targeted_signature = inspect.signature(targeted_reclassify_with_reconciliation_context)
                    if "selection" in targeted_signature.parameters:
                        targeted_kwargs["selection"] = targeted_selection
                    structure_map = targeted_reclassify_with_reconciliation_context(
                        paragraphs,
                        document_map,
                        structure_map,
                        reconciliation_report,
                        **targeted_kwargs,
                    )
                except (StructureRecognitionRequestTimeout, TimeoutError, RuntimeError) as exc:
                    reason = _format_ai_first_fallback_reason(exc)
                    return _degrade_ai_first(
                        fallback_stage="stage3_reconciliation_provider",
                        reason=reason,
                        detail="AI-first reconciliation provider path недоступен. Используются текущие правила.",
                    )
                structure_map, reconciliation_report = reconcile_with_document_map(
                    paragraphs,
                    document_map,
                    structure_map,
                    topology_projection=topology_projection,
                )
                reconciliation_report = ReconciliationReport(
                    missing_outline_entries=reconciliation_report.missing_outline_entries,
                    unexpected_headings=reconciliation_report.unexpected_headings,
                    toc_entries_without_body_match=reconciliation_report.toc_entries_without_body_match,
                    front_matter_leaks=reconciliation_report.front_matter_leaks,
                    front_matter_body_advisories=reconciliation_report.front_matter_body_advisories,
                    anchor_disagreements_seen=reconciliation_report.anchor_disagreements_seen,
                    targeted_recall_invoked=True,
                    targeted_recall_count=1,
                    targeted_selection_reasons=()
                    if targeted_selection is None
                    else targeted_selection.reasons,
                    outline_coverage_ratio=reconciliation_report.outline_coverage_ratio,
                    patched_logical_indexes=tuple(
                        sorted(
                            dict.fromkeys(
                                [
                                    *initial_reconciliation_report.patched_logical_indexes,
                                    *reconciliation_report.patched_logical_indexes,
                                ]
                            )
                        )
                    ),
                )
        except Exception:
            raise

        effective_cache_key = cache_key
        if effective_cache_key is None:
            effective_cache_key = _build_structure_map_cache_key(
                paragraphs=paragraphs,
                app_config=app_config,
                document_map=document_map,
                topology_projection=topology_projection,
                resolved_model=resolved_model or get_model_role_value(app_config, "structure_recognition"),
            )

        try:
            artifact_path = _write_reconciliation_report_artifact(
                cache_key=effective_cache_key,
                report=reconciliation_report,
                app_config=app_config,
            )
            log_event(
                logging.INFO,
                "reconciliation_report_saved",
                "Сохранён reconciliation report структуры.",
                artifact_path=artifact_path,
                outline_coverage_ratio=reconciliation_report.outline_coverage_ratio,
                front_matter_leaks=list(reconciliation_report.front_matter_leaks),
                front_matter_body_advisories=list(reconciliation_report.front_matter_body_advisories),
                anchor_disagreements_seen=list(reconciliation_report.anchor_disagreements_seen),
                patched_logical_indexes=list(reconciliation_report.patched_logical_indexes),
                targeted_recall_invoked=reconciliation_report.targeted_recall_invoked,
                targeted_selected_logical_indexes=list(reconciliation_report.targeted_selected_logical_indexes),
            )
        except Exception as exc:
            log_event(
                logging.WARNING,
                "reconciliation_report_save_failed",
                "Не удалось сохранить reconciliation report структуры.",
                error_message=_format_ai_first_fallback_reason(exc),
                outline_coverage_ratio=reconciliation_report.outline_coverage_ratio,
                targeted_recall_invoked=reconciliation_report.targeted_recall_invoked,
            )
    if bool(app_config.get("structure_recognition_save_debug_artifacts", True)):
        effective_cache_key = cache_key
        if effective_cache_key is None:
            effective_cache_key = _build_structure_map_cache_key(
                paragraphs=paragraphs,
                app_config=app_config,
                document_map=document_map,
                topology_projection=topology_projection,
                resolved_model=resolved_model or get_model_role_value(app_config, "structure_recognition"),
            )
        try:
            artifact_path = _write_structure_map_debug_artifact(
                cache_key=effective_cache_key,
                structure_map=structure_map,
                app_config=app_config,
            )
            log_event(
                logging.INFO,
                "structure_recognition_debug_artifact_saved",
                "Сохранён debug artifact распознанной структуры.",
                artifact_path=artifact_path,
            )
        except Exception as exc:
            log_event(
                logging.WARNING,
                "structure_recognition_debug_artifact_save_failed",
                "Не удалось сохранить debug artifact распознанной структуры.",
                error_message=_format_ai_first_fallback_reason(exc),
            )
    emit_preparation_progress(
        progress_callback,
        stage="Применение структуры…",
        detail="Применяю результаты AI-классификации к абзацам.",
        progress=0.53,
        metrics={**base_metrics, "source_format": source_format, "conversion_backend": conversion_backend},
    )
    try:
        applied_metrics = apply_structure_map(
            paragraphs,
            structure_map,
            min_confidence=str(
                app_config.get(
                    "structure_recovery_anchored_classification_min_confidence",
                    app_config.get("structure_recognition_min_confidence", "medium"),
                )
                if document_map is not None
                else app_config.get("structure_recognition_min_confidence", "medium")
            ),
            document_map=document_map,
            topology_projection=topology_projection,
        )
    except Exception as exc:
        _restore_structure_baseline(baseline=baseline, paragraphs=paragraphs)
        reason = _format_ai_first_fallback_reason(exc)
        return _degrade_ai_first(
            fallback_stage="stage3_apply",
            reason=reason,
            detail="AI-first apply path недоступен. Используются текущие правила.",
        )
    divergence_metrics = _build_structure_divergence_metrics(baseline=baseline, paragraphs=paragraphs)

    structure_summary = _build_structure_recognition_summary(
        applied_metrics=applied_metrics,
        divergence_metrics=divergence_metrics,
        structure_map=structure_map,
    )
    if structure_summary.ai_classified_count > 0:
        detail = (
            f"Классифицировано {structure_summary.ai_classified_count} абзацев, "
            f"найдено {structure_summary.ai_heading_count} заголовков."
        )
        stage = "Структура распознана"
    else:
        detail = "AI не внёс изменений. Используются текущие правила."
        stage = "Структура: эвристика"
    emit_preparation_progress(
        progress_callback,
        stage=stage,
        detail=detail,
        progress=0.55,
        metrics={
            **base_metrics,
            **structure_summary.as_progress_metrics(structure_map=structure_map),
            "source_format": source_format,
            "conversion_backend": conversion_backend,
        },
    )
    return structure_map, structure_summary


def _run_document_map_stage(
    *,
    paragraphs: list,
    image_assets: list,
    app_config: Mapping[str, Any],
    get_client_fn=None,
    progress_callback,
    normalization_report,
    relation_report,
    cleanup_report=None,
    structure_repair_report=None,
    source_format: str = "docx",
    conversion_backend: str | None = None,
    fallback_state: dict[str, object] | None = None,
) -> DocumentMap | None:
    if get_client_fn is None:
        get_client_fn = get_client
    if not bool(app_config.get("structure_recovery_enabled", False)):
        _record_document_map_state(
            fallback_state,
            status="disabled",
            reason="structure_recovery_disabled",
            document_map_present=False,
        )
        return None
    if not bool(app_config.get("structure_recovery_document_map_enabled", False)):
        _record_document_map_state(
            fallback_state,
            status="disabled",
            reason="document_map_disabled",
            document_map_present=False,
        )
        return None

    base_metrics = _build_preparation_stage_metrics(
        paragraph_count=len(paragraphs),
        image_count=len(image_assets),
        normalization_report=normalization_report,
        relation_report=relation_report,
        cleanup_report=cleanup_report,
        structure_repair_report=structure_repair_report,
    )

    def _emit_document_map_progress(event) -> None:
        if event.event == "descriptors_built":
            detail = (
                f"Подготовлено {event.descriptor_count or 0} абзацев, "
                f"выбрано {event.sampled_count or 0} координат для карты."
            )
            progress = 0.37
        else:
            detail = "Глобальная карта документа подготовлена."
            progress = 0.4
        emit_preparation_progress(
            progress_callback,
            stage="Карта документа…",
            detail=detail,
            progress=progress,
            metrics={
                **base_metrics,
                "source_format": source_format,
                "conversion_backend": conversion_backend,
                "document_map_descriptor_count": event.descriptor_count,
                "document_map_sampled_count": event.sampled_count,
            },
        )

    try:
        cache_key = _build_document_map_cache_key(paragraphs=paragraphs, app_config=app_config)
        emit_preparation_progress(
            progress_callback,
            stage="Карта документа…",
            detail="Строю глобальную карту документа для последующих Stage 2/3.",
            progress=0.36,
            metrics={**base_metrics, "source_format": source_format, "conversion_backend": conversion_backend},
        )
        document_map = None
        if bool(app_config.get("structure_recovery_document_map_cache_enabled", True)):
            document_map = _read_cached_document_map(cache_key)
    except Exception as exc:
        reason = _format_ai_first_fallback_reason(exc)
        _record_document_map_state(
            fallback_state,
            status="cache_failed",
            reason=reason,
            document_map_present=False,
        )
        _record_ai_first_fallback(
            fallback_state,
            fallback_stage="stage1_document_map_cache",
            reason=reason,
            document_map_present=False,
        )
        log_event(
            logging.WARNING,
            "document_map_fallback",
            "Построение глобальной карты документа завершилось fallback-путём.",
            ai_first_degraded=True,
            fallback_stage="stage1_document_map_cache",
            document_map_present=False,
            error_message=reason,
        )
        emit_preparation_progress(
            progress_callback,
            stage="Карта документа: fallback",
            detail="Глобальная карта документа недоступна из-за cache failure. Продолжаю без неё.",
            progress=0.4,
            metrics={**base_metrics, "source_format": source_format, "conversion_backend": conversion_backend},
        )
        return None

    try:
        if document_map is None:
            model_selector = str(app_config.get("structure_recovery_document_map_model", "") or "")
            client = _resolve_responses_client_for_model(
                get_client_fn=get_client_fn,
                model_selector=model_selector,
                app_config=app_config,
            )
            document_map = build_document_map(
                paragraphs,
                client=client,
                model=model_selector,
                timeout=float(app_config.get("structure_recovery_document_map_timeout_seconds", 120) or 120),
                max_input_paragraphs=int(app_config.get("structure_recovery_document_map_max_input_paragraphs", 6000) or 6000),
                max_input_tokens=int(app_config.get("structure_recovery_document_map_max_input_tokens", 180000) or 180000),
                preview_chars=int(app_config.get("structure_recovery_document_map_preview_chars", 120) or 120),
                progress_callback=_emit_document_map_progress,
            )
            if bool(app_config.get("structure_recovery_document_map_cache_enabled", True)):
                _store_cached_document_map(cache_key, document_map)
            _record_document_map_state(
                fallback_state,
                status="ai",
                document_map_present=True,
            )
        else:
            _record_document_map_state(
                fallback_state,
                status="cache",
                document_map_present=True,
            )
            emit_preparation_progress(
                progress_callback,
                stage="Карта документа…",
                detail="Использую сохранённую карту документа.",
                progress=0.4,
                metrics={
                    **base_metrics,
                    "source_format": source_format,
                    "conversion_backend": conversion_backend,
                    "document_map_descriptor_count": len(paragraphs),
                    "document_map_sampled_count": len(document_map.sampled_logical_indexes),
                },
            )
    except DocumentMapSchemaError as exc:
        reason = _format_ai_first_fallback_reason(exc)
        _record_document_map_state(
            fallback_state,
            status="schema_failed",
            reason=reason,
            document_map_present=False,
        )
        _record_ai_first_fallback(
            fallback_state,
            fallback_stage="stage1_document_map_schema",
            reason=reason,
            document_map_present=False,
        )
        log_event(
            logging.WARNING,
            "document_map_fallback",
            "Построение глобальной карты документа завершилось fallback-путём.",
            ai_first_degraded=True,
            fallback_stage="stage1_document_map_schema",
            document_map_present=False,
            error_message=reason,
        )
        emit_preparation_progress(
            progress_callback,
            stage="Карта документа: fallback",
            detail="Глобальная карта документа недоступна из-за schema failure. Продолжаю без неё.",
            progress=0.4,
            metrics={**base_metrics, "source_format": source_format, "conversion_backend": conversion_backend},
        )
        return None
    except DocumentMapRequestTimeout as exc:
        reason = _format_ai_first_fallback_reason(exc)
        _record_document_map_state(
            fallback_state,
            status="provider_failed",
            reason=reason,
            document_map_present=False,
        )
        _record_ai_first_fallback(
            fallback_state,
            fallback_stage="stage1_document_map_provider",
            reason=reason,
            document_map_present=False,
        )
        log_event(
            logging.WARNING,
            "document_map_fallback",
            "Построение глобальной карты документа завершилось fallback-путём.",
            ai_first_degraded=True,
            fallback_stage="stage1_document_map_provider",
            document_map_present=False,
            error_message=reason,
        )
        emit_preparation_progress(
            progress_callback,
            stage="Карта документа: fallback",
            detail="Глобальная карта документа недоступна. Продолжаю без неё.",
            progress=0.4,
            metrics={**base_metrics, "source_format": source_format, "conversion_backend": conversion_backend},
        )
        return None
    except RuntimeError as exc:
        if not _is_document_map_provider_runtime_error(exc):
            raise
        reason = _format_ai_first_fallback_reason(exc)
        _record_document_map_state(
            fallback_state,
            status="provider_failed",
            reason=reason,
            document_map_present=False,
        )
        _record_ai_first_fallback(
            fallback_state,
            fallback_stage="stage1_document_map_provider",
            reason=reason,
            document_map_present=False,
        )
        log_event(
            logging.WARNING,
            "document_map_fallback",
            "Построение глобальной карты документа завершилось fallback-путём.",
            ai_first_degraded=True,
            fallback_stage="stage1_document_map_provider",
            document_map_present=False,
            error_message=reason,
        )
        emit_preparation_progress(
            progress_callback,
            stage="Карта документа: fallback",
            detail="Глобальная карта документа недоступна. Продолжаю без неё.",
            progress=0.4,
            metrics={**base_metrics, "source_format": source_format, "conversion_backend": conversion_backend},
        )
        return None

    if bool(app_config.get("structure_recovery_document_map_save_debug_artifacts", True)):
        artifact_path = _write_document_map_debug_artifact(
            cache_key=cache_key,
            document_map=document_map,
            app_config=app_config,
        )
        log_event(
            logging.INFO,
            "document_map_debug_artifact_saved",
            "Сохранён debug artifact глобальной карты документа.",
            artifact_path=artifact_path,
        )
    return document_map


def _run_document_topology_projection_stage(
    *,
    paragraphs: list,
    document_map: DocumentMap | None,
    app_config: Mapping[str, Any],
) -> tuple[DocumentTopologyProjection | None, str, str]:
    if not bool(app_config.get("structure_recovery_enabled", False)):
        log_event(
            logging.INFO,
            "document_topology_projection_skipped",
            "Topology projection отключён вместе с structure recovery.",
            reason="structure_recovery_disabled",
        )
        return None, "disabled", "structure_recovery_disabled"
    if not bool(app_config.get("structure_recovery_topology_projection_enabled", False)):
        log_event(
            logging.INFO,
            "document_topology_projection_skipped",
            "Topology projection отключён конфигурацией.",
            reason="topology_projection_disabled",
        )
        return None, "disabled", "topology_projection_disabled"
    if document_map is None:
        log_event(
            logging.INFO,
            "document_topology_projection_skipped",
            "Topology projection пропущен, потому что карта документа отсутствует.",
            reason="document_map_absent",
        )
        return None, "skipped", "document_map_absent"

    try:
        document_map_cache_key = _build_document_map_cache_key(paragraphs=paragraphs, app_config=app_config)
        projection = apply_document_map_topology(
            paragraphs,
            document_map,
            app_config=app_config,
            document_map_cache_key=document_map_cache_key,
        )
    except Exception as exc:
        reason = _format_ai_first_fallback_reason(exc)
        log_event(
            logging.WARNING,
            "document_topology_projection_skipped",
            "Не удалось построить topology projection, продолжаю без него.",
            reason="projection_failed",
            error_message=reason,
        )
        return None, "failed", reason

    artifact_path = None
    if bool(app_config.get("structure_recovery_topology_projection_save_debug_artifacts", True)):
        artifact_path = _write_document_topology_debug_artifact(projection=projection)

    operation_counts = dict(Counter(operation.op for operation in projection.operations))
    unit_type_counts = dict(Counter(unit.unit_type for unit in projection.projected_units))
    authority_counts = dict(Counter(unit.authority for unit in projection.projected_units))
    if projection.operations or projection.projected_units:
        log_event(
            logging.INFO,
            "document_topology_projection_built",
            "Построен topology projection документа.",
            cache_key=projection.cache_key,
            document_map_cache_key=projection.document_map_cache_key,
            operation_count=len(projection.operations),
            projected_unit_count=len(projection.projected_units),
            operation_counts=operation_counts,
            unit_type_counts=unit_type_counts,
            authority_counts=authority_counts,
            artifact_path=artifact_path,
        )
        return projection, "built", ""

    log_event(
        logging.INFO,
        "document_topology_projection_skipped",
        "Topology projection не выявил binding operations.",
        reason="no_operations",
        cache_key=projection.cache_key,
        operation_count=0,
        projected_unit_count=0,
        artifact_path=artifact_path,
    )
    return projection, "no_operations", ""


PREPARATION_CACHE_LIMIT = 2
_shared_preparation_cache: OrderedDict[str, PreparedDocumentData] = OrderedDict()
_shared_preparation_cache_lock = Lock()
_shared_preparation_inflight: dict[str, Event] = {}


def emit_preparation_progress(progress_callback, *, stage: str, detail: str, progress: float, metrics: dict[str, Any] | None = None) -> None:
    if progress_callback is None:
        return
    progress_callback(stage=stage, detail=detail, progress=progress, metrics=metrics or {})


def _build_source_import_progress(*, source_format: str) -> tuple[str, str]:
    normalized = str(source_format or "docx").strip().lower()
    if normalized == "pdf":
        return (
            "Разбор DOCX (из PDF)",
            "Извлекаю абзацы, встроенные изображения и структуру из сконвертированного DOCX.",
        )
    if normalized == "doc":
        return (
            "Разбор DOCX (из DOC)",
            "Извлекаю абзацы, встроенные изображения и структуру из сконвертированного DOCX.",
        )
    return ("Разбор DOCX", "Извлекаю абзацы и встроенные изображения.")


def _resolve_structure_recognition_mode(app_config: Mapping[str, Any]) -> str:
    mode = str(app_config.get("structure_recognition_mode", "")).strip().lower()
    if mode in {"off", "auto", "always"}:
        return mode
    return "always" if bool(app_config.get("structure_recognition_enabled", False)) else "off"


def build_layout_cleanup_status_note(cleanup_report) -> str:
    if cleanup_report is None:
        return ""
    cleanup_mode = str(getattr(cleanup_report, "cleanup_mode", "remove") or "remove").strip().lower()
    if cleanup_mode == "flag":
        flagged_count = int(
            getattr(cleanup_report, "flagged_page_number_count", 0)
            or 0
        ) + int(
            getattr(cleanup_report, "flagged_repeated_artifact_count", 0)
            or 0
        ) + int(
            getattr(cleanup_report, "flagged_empty_or_whitespace_count", 0)
            or 0
        )
        if flagged_count <= 0:
            return ""
        page_numbers = int(getattr(cleanup_report, "flagged_page_number_count", 0) or 0)
        repeated = int(getattr(cleanup_report, "flagged_repeated_artifact_count", 0) or 0)
        empty = int(getattr(cleanup_report, "flagged_empty_or_whitespace_count", 0) or 0)
        return (
            f"Очистка: помечено {flagged_count} служебных элементов "
            f"({page_numbers} номеров страниц, {repeated} повторяющихся колонтитулов, {empty} пустых абзацев)."
        )
    removed_count = int(getattr(cleanup_report, "removed_paragraph_count", 0) or 0)
    if removed_count <= 0:
        return ""
    page_numbers = int(getattr(cleanup_report, "removed_page_number_count", 0) or 0)
    repeated = int(getattr(cleanup_report, "removed_repeated_artifact_count", 0) or 0)
    empty = int(getattr(cleanup_report, "removed_empty_or_whitespace_count", 0) or 0)
    return (
        f"Очистка: удалено {removed_count} служебных элементов "
        f"({page_numbers} номеров страниц, {repeated} повторяющихся колонтитулов, {empty} пустых абзацев)."
    )


def _resolve_layout_cleanup_cache_key(app_config: Mapping[str, Any]) -> str:
    if not bool(app_config.get("layout_artifact_cleanup_enabled", True)):
        return "off"
    min_repeat_count = max(2, int(app_config.get("layout_artifact_cleanup_min_repeat_count", 3) or 3))
    max_repeated_text_chars = max(1, int(app_config.get("layout_artifact_cleanup_max_repeated_text_chars", 80) or 80))
    return f"1:{min_repeat_count}:{max_repeated_text_chars}"


def _run_structure_validation(
    *,
    paragraphs: list,
    image_assets: list,
    app_config: Mapping[str, Any],
    progress_callback,
    normalization_report,
    relation_report,
    cleanup_report=None,
    structure_repair_report: StructureRepairReport | None = None,
    document_map: DocumentMap | None = None,
    outline_coverage_ratio: float | None = None,
    phase: str = "pre_ai_diagnostic",
    source_format: str = "docx",
    conversion_backend: str | None = None,
) -> StructureValidationReport:
    base_metrics = _build_preparation_stage_metrics(
        paragraph_count=len(paragraphs),
        image_count=len(image_assets),
        normalization_report=normalization_report,
        relation_report=relation_report,
        cleanup_report=cleanup_report,
        structure_repair_report=structure_repair_report,
    )
    is_pre_ai = phase == "pre_ai_diagnostic"
    stage = "Структура: валидация" if is_pre_ai else "Структура: финальная валидация"
    detail = (
        "Оцениваю структурный риск документа детерминированно."
        if is_pre_ai
        else "Проверяю итоговую структуру после AI и reconciliation."
    )
    progress = 0.30 if is_pre_ai else 0.56
    emit_preparation_progress(
        progress_callback,
        stage=stage,
        detail=detail,
        progress=progress,
        metrics={**base_metrics, "source_format": source_format, "conversion_backend": conversion_backend},
    )
    try:
        report = validate_structure_quality(
            paragraphs=paragraphs,
            app_config=app_config,
            structure_repair_report=structure_repair_report,
            document_map_present=document_map is not None,
            outline_coverage_ratio=outline_coverage_ratio,
            phase=phase,
        )
    except TypeError as exc:
        if "phase" not in str(exc):
            raise
        report = validate_structure_quality(
            paragraphs=paragraphs,
            app_config=app_config,
            structure_repair_report=structure_repair_report,
            document_map_present=document_map is not None,
            outline_coverage_ratio=outline_coverage_ratio,
        )
    if bool(app_config.get("structure_validation_save_debug_artifacts", True)):
        artifact_path = write_structure_validation_debug_artifact(report=report, app_config=app_config)
        log_event(
            logging.INFO,
            "structure_validation_debug_artifact_saved",
            "Сохранён debug artifact структурной валидации.",
            artifact_path=artifact_path,
            validation_phase=phase,
            escalation_recommended=report.escalation_recommended,
        )
    return report


def _compute_outline_coverage_ratio(*, paragraphs: Sequence[Any], document_map: DocumentMap | None) -> float | None:
    if document_map is None:
        return None
    outline = tuple(cast(Sequence[Any], getattr(document_map, "outline", ()) or ()))
    if not outline:
        return 1.0

    paragraphs_by_logical_index = {
        int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1))): paragraph
        for paragraph in paragraphs
    }
    matched = 0
    for entry in outline:
        paragraph = paragraphs_by_logical_index.get(int(getattr(entry, "logical_index", -1)))
        if paragraph is None:
            continue
        role = str(getattr(paragraph, "role", "") or "").strip().lower()
        heading_level = getattr(paragraph, "heading_level", None)
        if role == "heading" and heading_level == getattr(entry, "level", None):
            matched += 1
    return matched / len(outline)


def _resolve_pre_translation_quality_gate(
    *,
    structure_validation_report: StructureValidationReport | None,
    diagnostic_structure_validation_report: StructureValidationReport | None = None,
    structure_ai_attempted: bool,
    structure_summary: StructureRecognitionSummary,
    app_config: Mapping[str, Any],
) -> tuple[str, tuple[str, ...]]:
    if structure_validation_report is None:
        return "pass", ()

    diagnostic_report = diagnostic_structure_validation_report or structure_validation_report

    reasons: list[str] = []
    readiness_status = str(getattr(structure_validation_report, "readiness_status", "") or "")
    if readiness_status in {"blocked_needs_structure_repair", "blocked_unsafe_best_effort_only"}:
        for reason in getattr(structure_validation_report, "readiness_reasons", ()) or ():
            reason_text = str(reason)
            if (
                reason_text == "heading_count_far_below_toc_expectation"
                and bool(getattr(structure_validation_report, "document_map_present", False))
                and float(getattr(structure_validation_report, "outline_coverage_ratio", 0.0) or 0.0) >= 1.0
            ):
                continue
            reasons.append(reason_text)

    if (
        bool(app_config.get("structure_validation_block_on_high_risk_noop", True))
        and bool(getattr(diagnostic_report, "escalation_recommended", False))
        and structure_ai_attempted
        and structure_summary.ai_classified_count == 0
    ):
        reasons.append("structure_recognition_noop_on_high_risk")

    unique_reasons = tuple(dict.fromkeys(reason for reason in reasons if reason))
    return ("warning" if unique_reasons else "pass", unique_reasons)


def _apply_first_block_composition_quality_gate(
    *,
    blocks: list,
    processing_operation: str,
    quality_gate_status: str,
    quality_gate_reasons: tuple[str, ...],
    structure_phase: str = "post_ai_final",
) -> tuple[str, tuple[str, ...]]:
    if processing_operation != "translate" or not blocks:
        return quality_gate_status, quality_gate_reasons
    first_block_paragraphs = list(getattr(blocks[0], "paragraphs", ()) or ())
    if not first_block_paragraphs:
        return quality_gate_status, quality_gate_reasons

    additional_reasons: list[str] = []
    if _block_has_toc_roles(first_block_paragraphs, structure_phase=structure_phase):
        if _block_has_epigraph_roles(first_block_paragraphs, structure_phase=structure_phase):
            additional_reasons.append("first_block_mixed_toc_and_epigraph")
        if _block_has_body_start_roles(first_block_paragraphs, structure_phase=structure_phase):
            additional_reasons.append("first_block_mixed_toc_and_body_start")
    if not additional_reasons:
        return quality_gate_status, quality_gate_reasons

    merged_reasons = tuple(dict.fromkeys([*quality_gate_reasons, *additional_reasons]))
    return "warning", merged_reasons


def _block_has_toc_roles(paragraphs: list, *, structure_phase: str) -> bool:
    return any(get_effective_structural_role(paragraph, phase=structure_phase) in {"toc_header", "toc_entry"} for paragraph in paragraphs)


def _block_has_epigraph_roles(paragraphs: list, *, structure_phase: str) -> bool:
    return any(
        get_effective_structural_role(paragraph, phase=structure_phase) in {"epigraph", "attribution", "dedication"}
        for paragraph in paragraphs
    )


def _block_has_body_start_roles(paragraphs: list, *, structure_phase: str) -> bool:
    for paragraph in paragraphs:
        role = str(getattr(paragraph, "role", "") or "").strip().lower()
        structural_role = get_effective_structural_role(paragraph, phase=structure_phase)
        if role in {"heading", "body", "list"} and structural_role not in {"toc_header", "toc_entry", "epigraph", "attribution", "dedication"}:
            return True
    return False


def build_prepared_source_key(
    uploaded_file_token: str,
    chunk_size: int,
    *,
    processing_operation: str = "edit",
    paragraph_boundary_normalization_mode: str = "high_only",
    paragraph_boundary_ai_review_mode: str = "off",
    relation_normalization_key: str = "phase2_default:epigraph_attribution,image_caption,table_caption,toc_region",
    layout_artifact_cleanup_key: str = "1:3:80",
    structure_recognition_enabled: bool = False,
    structure_recognition_mode: str | None = None,
    structure_recovery_enabled: bool = False,
    structure_recovery_mode: str = "ai_first",
    structure_recovery_coordinate_schema_version: int = STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION,
    structure_validation_enabled: bool = True,
) -> str:
    resolved_mode = (structure_recognition_mode or ("always" if structure_recognition_enabled else "off")).strip().lower()
    resolved_operation = str(processing_operation or "edit").strip().lower() or "edit"
    structure_recognition_suffix = f":sr={resolved_mode}"
    structure_recovery_suffix = (
        ":srec="
        f"{1 if structure_recovery_enabled else 0}:"
        f"{str(structure_recovery_mode or 'ai_first').strip().lower() or 'ai_first'}:"
        f"c{int(structure_recovery_coordinate_schema_version or STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION)}"
    )
    if resolved_mode == "auto":
        structure_recognition_suffix += f":sv={1 if structure_validation_enabled else 0}"
    operation_suffix = "" if resolved_operation == "edit" else f":op={resolved_operation}"
    return (
        f"{uploaded_file_token}:{chunk_size}:{paragraph_boundary_normalization_mode}:"
        f"{paragraph_boundary_ai_review_mode}:{relation_normalization_key}:lc={layout_artifact_cleanup_key}"
        f"{structure_recognition_suffix}{structure_recovery_suffix}{operation_suffix}"
    )


def _attach_prepared_job_ids(jobs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    prepared_jobs: list[dict[str, Any]] = []
    for index, job in enumerate(jobs):
        normalized_job = dict(job)
        normalized_job["job_id"] = str(normalized_job.get("job_id", "") or "").strip() or f"job_{index:04d}"
        prepared_jobs.append(normalized_job)
    return prepared_jobs


def _build_editing_jobs_with_optional_operation(*, blocks, max_chars: int, processing_operation: str, structure_phase: str):
    signature = inspect.signature(build_editing_jobs)
    accepts_processing_operation = "processing_operation" in signature.parameters
    accepts_structure_phase = "structure_phase" in signature.parameters
    if not accepts_processing_operation and not accepts_structure_phase:
        if str(getattr(build_editing_jobs, "__module__", "")) not in {"document", "document_semantic_blocks"}:
            return build_editing_jobs(blocks, max_chars=max_chars)
        raise RuntimeError("build_editing_jobs must accept processing_operation or structure_phase")
    try:
        kwargs: dict[str, Any] = {"max_chars": max_chars}
        if accepts_processing_operation:
            kwargs["processing_operation"] = processing_operation
        if accepts_structure_phase:
            kwargs["structure_phase"] = structure_phase
        return build_editing_jobs(blocks, **kwargs)
    except TypeError:
        return build_editing_jobs(blocks, max_chars=max_chars)


def _build_semantic_blocks_with_optional_boundaries(*, paragraphs, max_chars: int, relations, hard_boundary_paragraph_ids: set[str], structure_phase: str):
    signature = inspect.signature(build_semantic_blocks)
    accepts_hard_boundaries = "hard_boundary_paragraph_ids" in signature.parameters
    accepts_structure_phase = "structure_phase" in signature.parameters
    if accepts_hard_boundaries:
        try:
            kwargs = {
                "max_chars": max_chars,
                "relations": relations,
                "hard_boundary_paragraph_ids": hard_boundary_paragraph_ids,
            }
            if accepts_structure_phase:
                kwargs["structure_phase"] = structure_phase
            return build_semantic_blocks(paragraphs, **kwargs)
        except TypeError:
            pass
    if accepts_structure_phase:
        return build_semantic_blocks(paragraphs, max_chars=max_chars, relations=relations, structure_phase=structure_phase)
    return build_semantic_blocks(paragraphs, max_chars=max_chars, relations=relations)


def _detect_document_segments_with_optional_phase(*, paragraphs, source_content_hash16: str, chunk_size: int, structure_phase: str):
    signature = inspect.signature(detect_document_segments)
    if "structure_phase" in signature.parameters:
        try:
            return detect_document_segments(
                paragraphs,
                source_content_hash16=source_content_hash16,
                chunk_size=chunk_size,
                structure_phase=structure_phase,
            )
        except TypeError:
            pass
    return detect_document_segments(
        paragraphs,
        source_content_hash16=source_content_hash16,
        chunk_size=chunk_size,
    )


def _build_document_context_glossary_terms(*, translation_domain: str, source_text: str) -> tuple[GlossaryTerm, ...]:
    terminology_plan = build_terminology_plan(source_text=source_text, translation_domain=translation_domain)
    if not terminology_plan:
        return ()

    glossary_terms: list[GlossaryTerm] = []
    for line in terminology_plan.splitlines():
        normalized_line = str(line or "").strip()
        if not normalized_line or "->" not in normalized_line:
            continue
        source_term, target_term = normalized_line.split("->", 1)
        source_term = source_term.strip()
        target_term = target_term.strip()
        if not source_term or not target_term:
            continue
        glossary_terms.append(
            GlossaryTerm(
                source_term=source_term,
                target_term=target_term,
                confidence="medium",
            )
        )
    return tuple(glossary_terms)


def _extract_docx_detected_author(*, source_bytes: bytes, source_format: str) -> str | None:
    if str(source_format or "").strip().lower() != "docx" or not source_bytes:
        return None
    try:
        document = DocxDocument(BytesIO(source_bytes))
    except Exception:
        return None
    author = str(getattr(document.core_properties, "author", "") or "").strip()
    return author or None


def _build_document_context_profile(
    *,
    segments: Sequence[DocumentSegment],
    translation_domain: str,
    translation_domain_instructions: str,
    source_text: str,
    source_token: str,
    source_title: str,
    detected_author: str | None,
    structure_fingerprint: str,
    source_language: str,
    target_language: str,
) -> DocumentContextProfile:
    outline_entries = tuple(
        SegmentOutlineEntry(
            segment_id=str(getattr(segment, "segment_id", "") or "").strip(),
            title=str(getattr(segment, "title", "") or "").strip(),
            level=max(1, int(getattr(segment, "level", 1) or 1)),
            structural_role=str(getattr(segment, "structural_role", "body_range") or "body_range").strip() or "body_range",
        )
        for segment in segments
        if str(getattr(segment, "segment_id", "") or "").strip() and str(getattr(segment, "title", "") or "").strip()
    )
    glossary_terms = _build_document_context_glossary_terms(
        translation_domain=translation_domain,
        source_text=source_text,
    )
    return DocumentContextProfile(
        source_token=source_token,
        structure_fingerprint=structure_fingerprint,
        source_title=source_title,
        detected_author=detected_author,
        source_language=source_language,
        target_language=target_language,
        translation_domain=translation_domain,
        style_instructions=translation_domain_instructions,
        outline_entries=outline_entries,
        glossary_terms=glossary_terms,
    )


def _supports_segment_detection(paragraphs: Sequence[Any]) -> bool:
    return all(hasattr(paragraph, "text") and hasattr(paragraph, "role") for paragraph in paragraphs)


def _extract_document_content_with_optional_app_config(*, uploaded_file, app_config: Mapping[str, Any]):
    signature = inspect.signature(extract_document_content_with_normalization_reports)
    accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())
    if accepts_kwargs or "app_config" in signature.parameters:
        return extract_document_content_with_normalization_reports(uploaded_file, app_config=app_config)
    return extract_document_content_with_normalization_reports(uploaded_file)


def _prepare_document_for_processing(
    source_name: str,
    source_bytes: bytes,
    chunk_size: int,
    *,
    source_token: str = "",
    source_format: str = "docx",
    conversion_backend: str | None = None,
    app_config: Mapping[str, Any],
    processing_operation: str = "edit",
    get_client_fn,
    progress_callback=None,
):
    initial_stage, initial_detail = _build_source_import_progress(source_format=source_format)
    emit_preparation_progress(
        progress_callback,
        stage=initial_stage,
        detail=initial_detail,
        progress=0.2,
        metrics={
            "source_format": source_format,
            "conversion_backend": conversion_backend,
        },
    )
    uploaded_file = build_in_memory_uploaded_file(source_name=source_name, source_bytes=source_bytes)
    with HeartbeatBeacon(
        progress_callback,
        stage=initial_stage,
        detail_template=(
            initial_detail
            + " ({elapsed} сек идёт чтение DOCX-архива и извлечение абзацев/изображений.)"
        ),
        progress=0.22,
        metrics={"source_format": source_format, "conversion_backend": conversion_backend},
        interval_seconds=2.0,
    ):
        extraction_result = _extract_document_content_with_optional_app_config(uploaded_file=uploaded_file, app_config=app_config)
    paragraphs, image_assets, normalization_report, relations, relation_report, cleanup_report = extraction_result[:6]
    structure_repair_report = extraction_result[6] if len(extraction_result) > 6 else None
    emit_preparation_progress(
        progress_callback,
        stage="Структура извлечена",
        detail="Документ прочитан, собираю текст для анализа.",
        progress=0.3,
        metrics={
            "paragraph_count": len(paragraphs),
            "image_count": len(image_assets),
            "source_format": source_format,
            "conversion_backend": conversion_backend,
            **_build_normalization_metrics(normalization_report, relation_report, cleanup_report, structure_repair_report),
        },
    )
    structure_validation_report = None
    diagnostic_structure_validation_report = None
    structure_mode = _resolve_structure_recognition_mode(app_config)
    should_run_ai = False
    structure_ai_attempted = False
    if structure_mode in {"auto", "always"}:
        diagnostic_structure_validation_report = _run_structure_validation(
            paragraphs=paragraphs,
            image_assets=image_assets,
            app_config=app_config,
            progress_callback=progress_callback,
            normalization_report=normalization_report,
            relation_report=relation_report,
            cleanup_report=cleanup_report,
            structure_repair_report=structure_repair_report,
            source_format=source_format,
            conversion_backend=conversion_backend,
        )
        structure_validation_report = diagnostic_structure_validation_report
        if not bool(app_config.get("structure_validation_enabled", True)):
            emit_preparation_progress(
                progress_callback,
                stage="Структура: детерминированно",
                detail="Структурная валидация отключена. Используются текущие правила.",
                progress=0.35,
                metrics={
                    **_build_preparation_stage_metrics(
                        paragraph_count=len(paragraphs),
                        image_count=len(image_assets),
                        normalization_report=normalization_report,
                        relation_report=relation_report,
                        cleanup_report=cleanup_report,
                        structure_repair_report=structure_repair_report,
                    ),
                    "source_format": source_format,
                    "conversion_backend": conversion_backend,
                },
            )
            should_run_ai = structure_mode == "always"
        else:
            should_run_ai = True if structure_mode == "always" else diagnostic_structure_validation_report.escalation_recommended
            if not should_run_ai:
                emit_preparation_progress(
                    progress_callback,
                    stage="Структура: детерминированно",
                    detail="Структурный риск не найден. Используются текущие правила.",
                    progress=0.35,
                    metrics={
                        **_build_preparation_stage_metrics(
                            paragraph_count=len(paragraphs),
                            image_count=len(image_assets),
                            normalization_report=normalization_report,
                            relation_report=relation_report,
                            cleanup_report=cleanup_report,
                            structure_repair_report=structure_repair_report,
                        ),
                        "source_format": source_format,
                        "conversion_backend": conversion_backend,
                    },
                )
    ai_first_fallback_state: dict[str, object] = {
        "document_map_status": "not_requested",
        "document_map_status_reason": "",
        "document_map_present": False,
    }
    document_map = (
        _run_document_map_stage(
            paragraphs=paragraphs,
            image_assets=image_assets,
            app_config=app_config,
            get_client_fn=get_client_fn,
            progress_callback=progress_callback,
            normalization_report=normalization_report,
            relation_report=relation_report,
            cleanup_report=cleanup_report,
            structure_repair_report=structure_repair_report,
            source_format=source_format,
            conversion_backend=conversion_backend,
            fallback_state=ai_first_fallback_state,
        )
        if should_run_ai
        else None
    )
    document_topology_projection, document_topology_projection_status, document_topology_projection_status_reason = (
        _run_document_topology_projection_stage(
            paragraphs=paragraphs,
            document_map=document_map,
            app_config=app_config,
        )
        if should_run_ai
        else (None, "not_requested", "")
    )
    structure_ai_attempted = should_run_ai
    structure_map, structure_summary = (
        _run_structure_recognition(
            paragraphs=paragraphs,
            image_assets=image_assets,
            app_config=app_config,
            get_client_fn=get_client_fn,
            progress_callback=progress_callback,
            normalization_report=normalization_report,
            relation_report=relation_report,
            cleanup_report=cleanup_report,
            document_map=document_map,
            topology_projection=document_topology_projection,
            source_format=source_format,
            conversion_backend=conversion_backend,
        )
        if should_run_ai
        else (None, StructureRecognitionSummary())
    )
    if should_run_ai:
        structure_summary = _finalize_ai_first_structure_summary(
            structure_summary=structure_summary,
            fallback_state=ai_first_fallback_state,
            document_map_present=document_map is not None,
        )
    if should_run_ai and bool(app_config.get("structure_validation_enabled", True)):
        structure_validation_report = _run_structure_validation(
            paragraphs=paragraphs,
            image_assets=image_assets,
            app_config=app_config,
            progress_callback=progress_callback,
            normalization_report=normalization_report,
            relation_report=relation_report,
            cleanup_report=cleanup_report,
            structure_repair_report=structure_repair_report,
            document_map=document_map,
            outline_coverage_ratio=_compute_outline_coverage_ratio(paragraphs=paragraphs, document_map=document_map),
            phase="post_ai_readiness",
            source_format=source_format,
            conversion_backend=conversion_backend,
        )
    quality_gate_status, quality_gate_reasons = _resolve_pre_translation_quality_gate(
        structure_validation_report=structure_validation_report,
        diagnostic_structure_validation_report=diagnostic_structure_validation_report,
        structure_ai_attempted=structure_ai_attempted,
        structure_summary=structure_summary,
        app_config=app_config,
    )
    downstream_structure_phase = _resolve_downstream_structure_phase(
        structure_ai_attempted=structure_ai_attempted,
        structure_summary=structure_summary,
    )
    if _supports_segment_detection(paragraphs):
        source_content_hash16 = hashlib.sha256(source_bytes).hexdigest()[:16]
        segments, segment_diagnostics, structure_fingerprint = _detect_document_segments_with_optional_phase(
            paragraphs=paragraphs,
            source_content_hash16=source_content_hash16,
            chunk_size=chunk_size,
            structure_phase=downstream_structure_phase,
        )
        for segment in segments:
            for index in range(segment.start_paragraph_index, segment.end_paragraph_index + 1):
                paragraph = paragraphs[index]
                paragraph.segment_id = segment.segment_id
                paragraph.segment_level = segment.level
                if index == segment.start_paragraph_index:
                    paragraph.segment_boundary_before = segment.ordinal > 1
    else:
        segments = []
        segment_diagnostics = SegmentDetectionReport()
        structure_fingerprint = ""
    source_text = build_document_text(paragraphs)
    translation_domain = str(app_config.get("translation_domain_default", "general") or "general").strip().lower() or "general"
    translation_domain_instructions = build_translation_domain_instructions(
        translation_domain=translation_domain,
        source_text=source_text,
    )
    detected_author = _extract_docx_detected_author(source_bytes=source_bytes, source_format=source_format)
    document_context_profile = _build_document_context_profile(
        segments=segments,
        translation_domain=translation_domain,
        translation_domain_instructions=translation_domain_instructions,
        source_text=source_text,
        source_token=str(source_token or "").strip(),
        source_title=Path(str(source_name or "")).stem,
        detected_author=detected_author,
        structure_fingerprint=structure_fingerprint,
        source_language=str(app_config.get("source_language", app_config.get("source_language_default", "en")) or "en").strip().lower() or "en",
        target_language=str(app_config.get("target_language", app_config.get("target_language_default", "ru")) or "ru").strip().lower() or "ru",
    )
    emit_preparation_progress(
        progress_callback,
        stage="Текст собран",
        detail="Формирую цельный текст документа и считаю объём.",
        progress=0.6,
        metrics={
            **_build_preparation_stage_metrics(
                paragraph_count=len(paragraphs),
                image_count=len(image_assets),
                normalization_report=normalization_report,
                relation_report=relation_report,
                cleanup_report=cleanup_report,
                structure_repair_report=structure_repair_report,
                structure_map=structure_map,
                structure_summary=structure_summary,
                source_text=source_text,
            ),
            "source_format": source_format,
            "conversion_backend": conversion_backend,
        },
    )
    downstream_relations = relations
    if structure_ai_attempted:
        relation_normalization_enabled = bool(app_config.get("relation_normalization_enabled", True))
        enabled_relation_kinds = tuple(
            str(kind or "").strip()
            for kind in app_config.get(
                "relation_normalization_enabled_relation_kinds",
                ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            )
            if str(kind or "").strip()
        ) if relation_normalization_enabled else ()
        try:
            relations, relation_report = _build_paragraph_relations_with_optional_phase(
                paragraphs=paragraphs,
                enabled_relation_kinds=enabled_relation_kinds,
                structure_phase=downstream_structure_phase,
                document_map=document_map,
            )
            downstream_relations = relations
        except Exception as exc:
            preserved_relation_phase, preserved_relation_source = _relation_report_phase_and_source(relation_report)
            downstream_relations = []
            log_event(
                logging.WARNING,
                "relation_rebuild_after_structure_failed",
                "Не удалось перестроить relation-решения после AI-обработки структуры; downstream relation grouping отключён, diagnostic-версия сохранена отдельно.",
                structure_phase=downstream_structure_phase,
                enabled_relation_kinds=list(enabled_relation_kinds),
                error_message=_format_ai_first_fallback_reason(exc),
                downstream_relations_disabled=True,
                preserved_relation_phase=preserved_relation_phase,
                preserved_relation_source=preserved_relation_source,
            )
    hard_boundary_paragraph_ids = resolve_segment_hard_boundary_paragraph_ids(segments)
    blocks = _build_semantic_blocks_with_optional_boundaries(
        paragraphs=paragraphs,
        max_chars=chunk_size,
        relations=downstream_relations,
        hard_boundary_paragraph_ids=hard_boundary_paragraph_ids,
        structure_phase=downstream_structure_phase,
    )
    quality_gate_status, quality_gate_reasons = _apply_first_block_composition_quality_gate(
        blocks=blocks,
        processing_operation=processing_operation,
        quality_gate_status=quality_gate_status,
        quality_gate_reasons=quality_gate_reasons,
        structure_phase=downstream_structure_phase,
    )
    structure_status_note = build_structure_processing_status_note(
        type(
            "StructureProcessingStatusSource",
            (),
            {
                "structure_recognition_mode": structure_mode,
                "structure_validation_report": structure_validation_report,
                "structure_map": structure_map,
                "structure_recognition_summary": structure_summary,
                "structure_ai_attempted": structure_ai_attempted,
                "document_map_status": str(ai_first_fallback_state.get("document_map_status", "") or ""),
                "document_map_status_reason": str(ai_first_fallback_state.get("document_map_status_reason", "") or ""),
            },
        )()
    )
    log_event(
        logging.INFO,
        "structure_processing_outcome",
        "Определён итог обработки структуры документа.",
        structure_recognition_mode=structure_mode,
        structure_ai_attempted=structure_ai_attempted,
        structure_ai_succeeded=structure_map is not None,
        escalation_recommended=bool(getattr(structure_validation_report, "escalation_recommended", False)),
        escalation_reasons=list(getattr(structure_validation_report, "escalation_reasons", ())),
        readiness_status=str(getattr(structure_validation_report, "readiness_status", "") or ""),
        readiness_reasons=list(getattr(structure_validation_report, "readiness_reasons", ())),
        document_map_present=bool(document_map is not None or getattr(structure_validation_report, "document_map_present", False)),
        document_map_status=str(ai_first_fallback_state.get("document_map_status", "") or ""),
        document_map_status_reason=str(ai_first_fallback_state.get("document_map_status_reason", "") or ""),
        document_topology_projection_present=bool(document_topology_projection is not None),
        document_topology_projection_status=document_topology_projection_status,
        document_topology_projection_status_reason=document_topology_projection_status_reason,
        outline_coverage_ratio=getattr(structure_validation_report, "outline_coverage_ratio", None),
        ai_first_degraded=structure_summary.ai_first_degraded,
        fallback_stage=structure_summary.fallback_stage,
        fallback_reason=structure_summary.fallback_reason,
        quality_gate_status=quality_gate_status,
        quality_gate_reasons=list(quality_gate_reasons),
        ai_classified_count=structure_summary.ai_classified_count,
        ai_heading_count=structure_summary.ai_heading_count,
        structure_primary_classified_count=structure_summary.structure_primary_classified_count,
        structure_retry_classified_count=structure_summary.structure_retry_classified_count,
        structure_split_fallback_classified_count=structure_summary.structure_split_fallback_classified_count,
        **structure_summary.fallback_stats.as_metrics(),
        first_block_has_toc=(
            _block_has_toc_roles(
                list(getattr(blocks[0], "paragraphs", ()) or []),
                structure_phase=downstream_structure_phase,
            )
            if blocks
            else False
        ),
        first_block_has_epigraph=(
            _block_has_epigraph_roles(
                list(getattr(blocks[0], "paragraphs", ()) or []),
                structure_phase=downstream_structure_phase,
            )
            if blocks
            else False
        ),
        first_block_has_body_start=(
            _block_has_body_start_roles(
                list(getattr(blocks[0], "paragraphs", ()) or []),
                structure_phase=downstream_structure_phase,
            )
            if blocks
            else False
        ),
        structure_status_note=structure_status_note,
        **flatten_layout_cleanup_metrics(cleanup_report),
        **flatten_structure_repair_metrics(structure_repair_report),
    )
    if (
        structure_mode in {"auto", "always"}
        and bool(getattr(structure_validation_report, "escalation_recommended", False))
        and structure_ai_attempted
        and structure_summary.ai_classified_count == 0
    ):
        log_event(
            logging.WARNING,
            "structure_recognition_noop_on_high_risk",
            "AI-распознавание структуры не внесло изменений для high-risk документа.",
            escalation_reasons=list(getattr(structure_validation_report, "escalation_reasons", ())),
            readiness_status=str(getattr(structure_validation_report, "readiness_status", "") or ""),
        )
    emit_preparation_progress(
        progress_callback,
        stage="Смысловые блоки",
        detail="Группирую абзацы в блоки для модели.",
        progress=0.75,
        metrics={
            **_build_preparation_stage_metrics(
                paragraph_count=len(paragraphs),
                image_count=len(image_assets),
                normalization_report=normalization_report,
                relation_report=relation_report,
                cleanup_report=cleanup_report,
                structure_repair_report=structure_repair_report,
                structure_map=structure_map,
                structure_summary=structure_summary,
                source_text=source_text,
                block_count=len(blocks),
            ),
            "source_format": source_format,
            "conversion_backend": conversion_backend,
        },
    )
    jobs = _build_editing_jobs_with_optional_operation(
        blocks=blocks,
        max_chars=chunk_size,
        processing_operation=processing_operation,
        structure_phase=downstream_structure_phase,
    )
    jobs = _attach_prepared_job_ids(jobs)
    if _supports_segment_detection(paragraphs):
        segment_to_job = build_segment_to_job_mapping(segments, jobs)
        coverage_warnings = validate_segment_coverage(
            paragraphs=paragraphs,
            segments=segments,
            jobs=jobs,
            segment_to_job=segment_to_job,
        )
        if coverage_warnings:
            segment_diagnostics = replace(
                segment_diagnostics,
                warnings=tuple(dict.fromkeys((*segment_diagnostics.warnings, *coverage_warnings))),
            )
    else:
        segment_to_job = {}
    emit_preparation_progress(
        progress_callback,
        stage="Задания собраны",
        detail="Готовлю финальный набор задач для обработки.",
        progress=0.9,
        metrics={
            **_build_preparation_stage_metrics(
                paragraph_count=len(paragraphs),
                image_count=len(image_assets),
                normalization_report=normalization_report,
                relation_report=relation_report,
                cleanup_report=cleanup_report,
                structure_repair_report=structure_repair_report,
                structure_map=structure_map,
                structure_summary=structure_summary,
                source_text=source_text,
                block_count=len(jobs),
            ),
            "source_format": source_format,
            "conversion_backend": conversion_backend,
        },
    )
    return PreparedDocumentData(
        source_text=source_text,
        paragraphs=paragraphs,
        image_assets=image_assets,
        relations=relations,
        jobs=jobs,
        segments=segments,
        segment_diagnostics=segment_diagnostics,
        structure_fingerprint=structure_fingerprint,
        detector_version=CHAPTER_SEGMENTS_DETECTOR_VERSION,
        segment_to_job=segment_to_job,
        prepared_source_key="",
        source_format=source_format,
        conversion_backend=conversion_backend,
        normalization_report=normalization_report,
        relation_report=relation_report,
        cleanup_report=cleanup_report,
        structure_repair_report=structure_repair_report,
        document_map=document_map,
        document_topology_projection=document_topology_projection,
        document_map_status=str(ai_first_fallback_state.get("document_map_status", "not_requested") or "not_requested"),
        document_map_status_reason=str(ai_first_fallback_state.get("document_map_status_reason", "") or ""),
        document_topology_projection_status=document_topology_projection_status,
        document_topology_projection_status_reason=document_topology_projection_status_reason,
        structure_map=structure_map,
        structure_recognition_summary=structure_summary,
        structure_validation_report=structure_validation_report,
        structure_recognition_mode=structure_mode,
        structure_ai_attempted=structure_ai_attempted,
        quality_gate_status=quality_gate_status,
        quality_gate_reasons=quality_gate_reasons,
        translation_domain=translation_domain,
        translation_domain_instructions=translation_domain_instructions,
        document_context_profile=document_context_profile,
        cached=False,
    )


def _get_preparation_cache(session_state) -> dict[str, PreparedDocumentData]:
    if session_state is None:
        return {}
    cache = session_state.get("preparation_cache")
    if not isinstance(cache, dict):
        cache = {}
        session_state["preparation_cache"] = cache
    return cache


def _touch_cache_entry(cache: dict[str, PreparedDocumentData], prepared_source_key: str, prepared_document: PreparedDocumentData) -> None:
    cache.pop(prepared_source_key, None)
    cache[prepared_source_key] = prepared_document


def _trim_cache(cache: dict[str, PreparedDocumentData]) -> None:
    while len(cache) > PREPARATION_CACHE_LIMIT:
        oldest_key = next(iter(cache))
        cache.pop(oldest_key, None)


def _read_cache_entry(cache: dict[str, PreparedDocumentData], prepared_source_key: str):
    cached = cache.get(prepared_source_key)
    if cached is None:
        return None
    _touch_cache_entry(cache, prepared_source_key, cached)
    return cached


def _clone_prepared_document(data: PreparedDocumentData, prepared_source_key: str, *, cached: bool) -> PreparedDocumentData:
    return PreparedDocumentData(
        source_text=data.source_text,
        paragraphs=deepcopy(data.paragraphs),
        image_assets=[clone_prepared_image_asset(asset) for asset in data.image_assets],
        relations=deepcopy(data.relations),
        jobs=[dict(job) for job in data.jobs],
        segments=deepcopy(data.segments),
        segment_diagnostics=deepcopy(data.segment_diagnostics),
        structure_fingerprint=data.structure_fingerprint,
        detector_version=data.detector_version,
        segment_to_job=deepcopy(data.segment_to_job),
        prepared_source_key=prepared_source_key,
        normalization_report=deepcopy(data.normalization_report),
        relation_report=deepcopy(data.relation_report),
        cleanup_report=deepcopy(data.cleanup_report),
        structure_repair_report=deepcopy(data.structure_repair_report),
        document_map=deepcopy(data.document_map),
        document_topology_projection=deepcopy(data.document_topology_projection),
        document_map_status=data.document_map_status,
        document_map_status_reason=data.document_map_status_reason,
        document_topology_projection_status=data.document_topology_projection_status,
        document_topology_projection_status_reason=data.document_topology_projection_status_reason,
        structure_map=deepcopy(data.structure_map),
        structure_recognition_summary=data.structure_recognition_summary,
        structure_validation_report=deepcopy(data.structure_validation_report),
        structure_recognition_mode=data.structure_recognition_mode,
        structure_ai_attempted=data.structure_ai_attempted,
        quality_gate_status=data.quality_gate_status,
        quality_gate_reasons=tuple(data.quality_gate_reasons),
        source_format=data.source_format,
        conversion_backend=data.conversion_backend,
        translation_domain=data.translation_domain,
        translation_domain_instructions=data.translation_domain_instructions,
        document_context_profile=data.document_context_profile,
        cached=cached,
    )


def _read_or_reserve_cached_prepared_document(*, session_state, prepared_source_key: str):
    # Session cache is only touched from the Streamlit rerun thread. Background preparation
    # workers always pass session_state=None and only participate in the shared cache path.
    session_cache = _get_preparation_cache(session_state) if session_state is not None else None
    if session_cache is not None:
        cached = _read_cache_entry(session_cache, prepared_source_key)
        if cached is not None:
            return _clone_prepared_document(cached, prepared_source_key, cached=True), None, "session"

    while True:
        with _shared_preparation_cache_lock:
            cached = _read_cache_entry(_shared_preparation_cache, prepared_source_key)
            if cached is not None:
                if session_cache is not None:
                    _touch_cache_entry(session_cache, prepared_source_key, cached)
                    _trim_cache(session_cache)
                return _clone_prepared_document(cached, prepared_source_key, cached=True), None, "shared"

            in_flight = _shared_preparation_inflight.get(prepared_source_key)
            if in_flight is None:
                in_flight = Event()
                _shared_preparation_inflight[prepared_source_key] = in_flight
                return None, in_flight, None

        in_flight.wait()


def _release_shared_preparation(prepared_source_key: str) -> None:
    with _shared_preparation_cache_lock:
        in_flight = _shared_preparation_inflight.pop(prepared_source_key, None)
    if in_flight is not None:
        in_flight.set()


def _store_cached_prepared_document(*, session_state, prepared_source_key: str, prepared_document: PreparedDocumentData) -> None:
    prepared_document.prepared_source_key = ""
    prepared_document.cached = False
    if session_state is not None:
        cache = _get_preparation_cache(session_state)
        _touch_cache_entry(cache, prepared_source_key, prepared_document)
        _trim_cache(cache)

    with _shared_preparation_cache_lock:
        _touch_cache_entry(_shared_preparation_cache, prepared_source_key, prepared_document)
        _trim_cache(_shared_preparation_cache)


def clear_preparation_cache(*, session_state=None, clear_shared: bool = False) -> None:
    if session_state is not None:
        session_state["preparation_cache"] = {}
    if clear_shared:
        with _shared_preparation_cache_lock:
            _shared_preparation_cache.clear()
        with _document_map_cache_lock:
            _document_map_cache.clear()


def prepare_document_for_processing(
    *,
    uploaded_payload: FrozenUploadPayload,
    chunk_size: int,
    app_config: dict[str, Any] | None = None,
    processing_operation: str | None = None,
    session_state=None,
    get_client_fn=None,
    progress_callback=None,
) -> PreparedDocumentData:
    resolved_config = load_app_config() if app_config is None else app_config
    resolved_get_client_fn = get_client if get_client_fn is None else get_client_fn
    resolved_processing_operation = str(
        processing_operation if processing_operation is not None else resolved_config.get("processing_operation", "edit")
    ).strip().lower() or "edit"
    normalization_mode = (
        str(resolved_config["paragraph_boundary_normalization_mode"])
        if bool(resolved_config["paragraph_boundary_normalization_enabled"])
        else "off"
    )
    ai_review_mode = (
        str(resolved_config.get("paragraph_boundary_ai_review_mode", "off"))
        if bool(resolved_config.get("paragraph_boundary_ai_review_enabled", False))
        else "off"
    )
    relation_normalization_key = "off"
    if bool(resolved_config.get("relation_normalization_enabled", True)):
        relation_profile = str(resolved_config.get("relation_normalization_profile", "phase2_default"))
        configured_relation_kinds = resolved_config.get("relation_normalization_enabled_relation_kinds", ())
        if not isinstance(configured_relation_kinds, (list, tuple, set)):
            configured_relation_kinds = ()
        enabled_relation_kinds = ",".join(
            sorted(str(kind) for kind in configured_relation_kinds)
        )
        relation_normalization_key = f"{relation_profile}:{enabled_relation_kinds}"
    layout_cleanup_key = _resolve_layout_cleanup_cache_key(resolved_config)
    prepared_source_key = build_prepared_source_key(
        uploaded_payload.file_token,
        chunk_size,
        processing_operation=resolved_processing_operation,
        paragraph_boundary_normalization_mode=normalization_mode,
        paragraph_boundary_ai_review_mode=ai_review_mode,
        relation_normalization_key=relation_normalization_key,
        layout_artifact_cleanup_key=layout_cleanup_key,
        structure_recognition_enabled=bool(resolved_config.get("structure_recognition_enabled", False)),
        structure_recognition_mode=str(resolved_config.get("structure_recognition_mode", "") or ""),
        structure_recovery_enabled=bool(resolved_config.get("structure_recovery_enabled", False)),
        structure_recovery_mode=str(resolved_config.get("structure_recovery_mode", "ai_first") or "ai_first"),
        structure_recovery_coordinate_schema_version=int(
            resolved_config.get("structure_recovery_coordinate_schema_version", STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION)
            or STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION
        ),
        structure_validation_enabled=bool(resolved_config.get("structure_validation_enabled", True)),
    )
    cached, in_flight, cache_level = _read_or_reserve_cached_prepared_document(
        session_state=session_state,
        prepared_source_key=prepared_source_key,
    )
    if cached is not None:
        structure_status_note = build_structure_processing_status_note(cached)
        log_event(
            logging.INFO,
            "preparation_cache_hit",
            "Использован кэш подготовки документа.",
            prepared_source_key=prepared_source_key,
            cache_level=cache_level,
            structure_status_note=structure_status_note,
            structure_recognition_mode=cached.structure_recognition_mode,
            structure_ai_attempted=cached.structure_ai_attempted,
            escalation_recommended=bool(getattr(cached.structure_validation_report, "escalation_recommended", False)),
            escalation_reasons=list(getattr(cached.structure_validation_report, "escalation_reasons", ())),
        )
        emit_preparation_progress(
            progress_callback,
            stage="Подготовка документа",
            detail="Использую кэш подготовки для текущего файла.",
            progress=0.95,
            metrics={
                "paragraph_count": len(cached.paragraphs),
                "image_count": len(cached.image_assets),
                "source_chars": len(cached.source_text),
                "block_count": len(cached.jobs),
                "cached": cached.cached,
                "source_format": cached.source_format,
                "conversion_backend": cached.conversion_backend,
                **_build_normalization_metrics(
                    cached.normalization_report,
                    cached.relation_report,
                    cached.cleanup_report,
                    cached.structure_repair_report,
                ),
                **cached.structure_recognition_summary.as_progress_metrics(structure_map=cached.structure_map),
            },
        )
        return cached

    log_event(
        logging.INFO,
        "preparation_cache_miss",
        "Подготовка документа выполняется без готового cache-hit.",
        prepared_source_key=prepared_source_key,
    )

    try:
        prepared_document = _prepare_document_for_processing(
            uploaded_payload.filename,
            uploaded_payload.content_bytes,
            chunk_size,
            source_token=str(uploaded_payload.file_token or "").strip(),
            source_format=str(getattr(uploaded_payload, "source_format", "docx") or "docx"),
            conversion_backend=getattr(uploaded_payload, "conversion_backend", None),
            app_config=resolved_config,
            processing_operation=resolved_processing_operation,
            get_client_fn=resolved_get_client_fn,
            progress_callback=progress_callback,
        )
        _store_cached_prepared_document(
            session_state=session_state,
            prepared_source_key=prepared_source_key,
            prepared_document=prepared_document,
        )
    except Exception:
        if in_flight is not None:
            _release_shared_preparation(prepared_source_key)
        raise

    if in_flight is not None:
        _release_shared_preparation(prepared_source_key)
    return _clone_prepared_document(prepared_document, prepared_source_key, cached=False)
