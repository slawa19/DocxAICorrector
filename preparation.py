from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import inspect
import json
import logging
from pathlib import Path
from threading import Event, Lock
from collections.abc import Mapping
from typing import Any

from config import get_client, get_model_role_value, load_app_config
from document import (
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    extract_document_content_with_normalization_reports,
    summarize_boundary_normalization_metrics,
)
from logger import log_event
from models import LayoutArtifactCleanupReport, ParagraphBoundaryNormalizationReport, ParagraphRelation, RelationNormalizationReport
from models import StructureRecognitionSummary
from models import StructureRepairReport
from models import clone_prepared_image_asset
from models import StructureMap
from translation_domains import build_translation_domain_instructions
from processing_runtime import FrozenUploadPayload, build_in_memory_uploaded_file
from runtime_artifact_retention import (
    STRUCTURE_MAPS_MAX_AGE_SECONDS,
    STRUCTURE_MAPS_MAX_COUNT,
    prune_artifact_dir,
)
from structure_recognition import apply_structure_map, build_structure_map
from structure_validation import StructureValidationReport, validate_structure_quality, write_structure_validation_debug_artifact


@dataclass
class PreparedDocumentData:
    source_text: str
    paragraphs: list
    image_assets: list
    relations: list[ParagraphRelation]
    jobs: list[dict[str, Any]]
    prepared_source_key: str
    normalization_report: ParagraphBoundaryNormalizationReport | None = None
    relation_report: RelationNormalizationReport | None = None
    cleanup_report: LayoutArtifactCleanupReport | None = None
    structure_repair_report: StructureRepairReport | None = None
    structure_map: StructureMap | None = None
    structure_recognition_summary: StructureRecognitionSummary = StructureRecognitionSummary()
    structure_validation_report: StructureValidationReport | None = None
    structure_recognition_mode: str = "off"
    structure_ai_attempted: bool = False
    quality_gate_status: str = "pass"
    quality_gate_reasons: tuple[str, ...] = ()
    translation_domain: str = "general"
    translation_domain_instructions: str = ""
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


def _capture_structure_baseline(paragraphs: list) -> dict[int, tuple[str, str]]:
    return {
        paragraph.source_index: (paragraph.role, paragraph.structural_role)
        for paragraph in paragraphs
    }


def _build_structure_divergence_metrics(*, baseline: dict[int, tuple[str, str]], paragraphs: list) -> dict[str, int]:
    metrics = {
        "ai_role_changes": 0,
        "ai_heading_promotions": 0,
        "ai_heading_demotions": 0,
        "ai_structural_role_changes": 0,
    }
    for paragraph in paragraphs:
        if paragraph.role_confidence != "ai":
            continue
        previous = baseline.get(paragraph.source_index)
        if previous is None:
            continue
        previous_role, previous_structural_role = previous
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
_STRUCTURE_MAP_DEBUG_DIR = Path(__file__).resolve().parent / ".run" / "structure_maps"


def _build_structure_recognition_summary(*, applied_metrics: dict[str, int], divergence_metrics: dict[str, int]) -> StructureRecognitionSummary:
    return StructureRecognitionSummary(
        ai_classified_count=int(applied_metrics.get("ai_classified", 0) or 0),
        ai_heading_count=int(applied_metrics.get("ai_headings", 0) or 0),
        ai_role_change_count=int(divergence_metrics.get("ai_role_changes", 0) or 0),
        ai_heading_promotion_count=int(divergence_metrics.get("ai_heading_promotions", 0) or 0),
        ai_heading_demotion_count=int(divergence_metrics.get("ai_heading_demotions", 0) or 0),
        ai_structural_role_change_count=int(divergence_metrics.get("ai_structural_role_changes", 0) or 0),
    )


def _format_structure_escalation_reasons(report: StructureValidationReport | None) -> str:
    if report is None or not report.escalation_reasons:
        return ""
    labels = {
        "low_explicit_heading_density": "мало явных заголовков",
        "high_suspicious_short_body_ratio": "много коротких body-абзацев",
        "high_all_caps_or_centered_body_ratio": "много CAPS/центрированных body-абзацев",
        "toc_like_sequence_detected": "обнаружен TOC-подобный фрагмент",
        "heading_only_collapse_risk": "есть риск потери заголовочной структуры",
        "isolated_list_marker_fragments": "остались изолированные маркеры списков",
    }
    return ", ".join(labels.get(reason, reason) for reason in report.escalation_reasons)


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


def _build_structure_map_cache_key(*, paragraphs: list, app_config: Mapping[str, Any]) -> str:
    payload = {
        "model": get_model_role_value(app_config, "structure_recognition"),
        "max_window_paragraphs": int(app_config.get("structure_recognition_max_window_paragraphs", 1800) or 1800),
        "overlap_paragraphs": int(app_config.get("structure_recognition_overlap_paragraphs", 50) or 50),
        "paragraphs": [
            {
                "index": int(paragraph.source_index),
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
    artifact_path.write_text(
        json.dumps(
            {
                "cache_key": cache_key,
                "model": get_model_role_value(app_config, "structure_recognition"),
                "window_count": structure_map.window_count,
                "classified_count": structure_map.classified_count,
                "heading_count": structure_map.heading_count,
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


def _run_structure_recognition(*, paragraphs: list, image_assets: list, app_config: Mapping[str, Any], progress_callback, normalization_report, relation_report, cleanup_report=None) -> tuple[StructureMap | None, StructureRecognitionSummary]:
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
        metrics=base_metrics,
    )

    try:
        baseline = _capture_structure_baseline(paragraphs)
        cache_key = _build_structure_map_cache_key(paragraphs=paragraphs, app_config=app_config)
        structure_map = None
        if bool(app_config.get("structure_recognition_cache_enabled", True)):
            structure_map = _read_cached_structure_map(cache_key)
        if structure_map is None:
            structure_map = build_structure_map(
                paragraphs,
                client=get_client(),
                model=get_model_role_value(app_config, "structure_recognition"),
                max_window_paragraphs=int(app_config.get("structure_recognition_max_window_paragraphs", 1800) or 1800),
                overlap_paragraphs=int(app_config.get("structure_recognition_overlap_paragraphs", 50) or 50),
                timeout=float(app_config.get("structure_recognition_timeout_seconds", 60) or 60),
            )
            if bool(app_config.get("structure_recognition_cache_enabled", True)):
                _store_cached_structure_map(cache_key, structure_map)
        if bool(app_config.get("structure_recognition_save_debug_artifacts", True)):
            artifact_path = _write_structure_map_debug_artifact(cache_key=cache_key, structure_map=structure_map, app_config=app_config)
            log_event(
                logging.INFO,
                "structure_recognition_debug_artifact_saved",
                "Сохранён debug artifact распознанной структуры.",
                artifact_path=artifact_path,
            )
        applied_metrics = apply_structure_map(
            paragraphs,
            structure_map,
            min_confidence=str(app_config.get("structure_recognition_min_confidence", "medium")),
        )
        divergence_metrics = _build_structure_divergence_metrics(baseline=baseline, paragraphs=paragraphs)
    except Exception as exc:
        log_event(
            logging.WARNING,
            "structure_recognition_fallback",
            "AI-распознавание структуры завершилось fallback-путём.",
            error_message=str(exc),
        )
        emit_preparation_progress(
            progress_callback,
            stage="Структура: эвристика",
            detail="AI-распознавание недоступно. Используются текущие правила.",
            progress=0.55,
            metrics=base_metrics,
        )
        return None, StructureRecognitionSummary()

    structure_summary = _build_structure_recognition_summary(
        applied_metrics=applied_metrics,
        divergence_metrics=divergence_metrics,
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
        metrics={**base_metrics, **structure_summary.as_progress_metrics(structure_map=structure_map)},
    )
    return structure_map, structure_summary


PREPARATION_CACHE_LIMIT = 2
_shared_preparation_cache: OrderedDict[str, PreparedDocumentData] = OrderedDict()
_shared_preparation_cache_lock = Lock()
_shared_preparation_inflight: dict[str, Event] = {}


def emit_preparation_progress(progress_callback, *, stage: str, detail: str, progress: float, metrics: dict[str, Any] | None = None) -> None:
    if progress_callback is None:
        return
    progress_callback(stage=stage, detail=detail, progress=progress, metrics=metrics or {})


def _resolve_structure_recognition_mode(app_config: Mapping[str, Any]) -> str:
    mode = str(app_config.get("structure_recognition_mode", "")).strip().lower()
    if mode in {"off", "auto", "always"}:
        return mode
    return "always" if bool(app_config.get("structure_recognition_enabled", False)) else "off"


def build_layout_cleanup_status_note(cleanup_report) -> str:
    if cleanup_report is None:
        return ""
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
) -> StructureValidationReport:
    base_metrics = _build_preparation_stage_metrics(
        paragraph_count=len(paragraphs),
        image_count=len(image_assets),
        normalization_report=normalization_report,
        relation_report=relation_report,
        cleanup_report=cleanup_report,
        structure_repair_report=structure_repair_report,
    )
    emit_preparation_progress(
        progress_callback,
        stage="Структура: валидация",
        detail="Оцениваю структурный риск документа детерминированно.",
        progress=0.30,
        metrics=base_metrics,
    )
    report = validate_structure_quality(
        paragraphs=paragraphs,
        app_config=app_config,
        structure_repair_report=structure_repair_report,
    )
    if bool(app_config.get("structure_validation_save_debug_artifacts", True)):
        artifact_path = write_structure_validation_debug_artifact(report=report, app_config=app_config)
        log_event(
            logging.INFO,
            "structure_validation_debug_artifact_saved",
            "Сохранён debug artifact структурной валидации.",
            artifact_path=artifact_path,
            escalation_recommended=report.escalation_recommended,
        )
    return report


def _resolve_pre_translation_quality_gate(
    *,
    structure_validation_report: StructureValidationReport | None,
    structure_ai_attempted: bool,
    structure_summary: StructureRecognitionSummary,
    app_config: Mapping[str, Any],
) -> tuple[str, tuple[str, ...]]:
    if structure_validation_report is None:
        return "pass", ()

    reasons: list[str] = []
    readiness_status = str(getattr(structure_validation_report, "readiness_status", "") or "")
    if readiness_status in {"blocked_needs_structure_repair", "blocked_unsafe_best_effort_only"}:
        reasons.extend(str(reason) for reason in getattr(structure_validation_report, "readiness_reasons", ()) or ())

    if (
        bool(app_config.get("structure_validation_block_on_high_risk_noop", True))
        and bool(getattr(structure_validation_report, "escalation_recommended", False))
        and structure_ai_attempted
        and structure_summary.ai_classified_count == 0
    ):
        reasons.append("structure_recognition_noop_on_high_risk")

    unique_reasons = tuple(dict.fromkeys(reason for reason in reasons if reason))
    return ("blocked" if unique_reasons else "pass", unique_reasons)


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
    structure_validation_enabled: bool = True,
) -> str:
    resolved_mode = (structure_recognition_mode or ("always" if structure_recognition_enabled else "off")).strip().lower()
    resolved_operation = str(processing_operation or "edit").strip().lower() or "edit"
    structure_recognition_suffix = f":sr={resolved_mode}"
    if resolved_mode == "auto":
        structure_recognition_suffix += f":sv={1 if structure_validation_enabled else 0}"
    operation_suffix = "" if resolved_operation == "edit" else f":op={resolved_operation}"
    return (
        f"{uploaded_file_token}:{chunk_size}:{paragraph_boundary_normalization_mode}:"
        f"{paragraph_boundary_ai_review_mode}:{relation_normalization_key}:lc={layout_artifact_cleanup_key}"
        f"{structure_recognition_suffix}{operation_suffix}"
    )


def _build_editing_jobs_with_optional_operation(*, blocks, max_chars: int, processing_operation: str):
    signature = inspect.signature(build_editing_jobs)
    if "processing_operation" not in signature.parameters:
        if str(getattr(build_editing_jobs, "__module__", "")) not in {"document", "document_semantic_blocks"}:
            return build_editing_jobs(blocks, max_chars=max_chars)
        raise RuntimeError("build_editing_jobs must accept processing_operation")
    try:
        return build_editing_jobs(blocks, max_chars=max_chars, processing_operation=processing_operation)
    except TypeError:
        return build_editing_jobs(blocks, max_chars=max_chars)


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
    app_config: Mapping[str, Any],
    processing_operation: str = "edit",
    progress_callback=None,
):
    emit_preparation_progress(
        progress_callback,
        stage="Разбор DOCX",
        detail="Извлекаю абзацы и встроенные изображения.",
        progress=0.2,
    )
    uploaded_file = build_in_memory_uploaded_file(source_name=source_name, source_bytes=source_bytes)
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
            **_build_normalization_metrics(normalization_report, relation_report, cleanup_report, structure_repair_report),
        },
    )
    structure_validation_report = None
    structure_mode = _resolve_structure_recognition_mode(app_config)
    should_run_ai = False
    structure_ai_attempted = False
    if structure_mode in {"auto", "always"}:
        structure_validation_report = _run_structure_validation(
            paragraphs=paragraphs,
            image_assets=image_assets,
            app_config=app_config,
            progress_callback=progress_callback,
            normalization_report=normalization_report,
            relation_report=relation_report,
            cleanup_report=cleanup_report,
            structure_repair_report=structure_repair_report,
        )
        if not bool(app_config.get("structure_validation_enabled", True)):
            emit_preparation_progress(
                progress_callback,
                stage="Структура: детерминированно",
                detail="Структурная валидация отключена. Используются текущие правила.",
                progress=0.35,
                metrics=_build_preparation_stage_metrics(
                    paragraph_count=len(paragraphs),
                    image_count=len(image_assets),
                    normalization_report=normalization_report,
                    relation_report=relation_report,
                    cleanup_report=cleanup_report,
                    structure_repair_report=structure_repair_report,
                ),
            )
            should_run_ai = structure_mode == "always"
        else:
            should_run_ai = True if structure_mode == "always" else structure_validation_report.escalation_recommended
            if not should_run_ai:
                emit_preparation_progress(
                    progress_callback,
                    stage="Структура: детерминированно",
                    detail="Структурный риск не найден. Используются текущие правила.",
                    progress=0.35,
                    metrics=_build_preparation_stage_metrics(
                        paragraph_count=len(paragraphs),
                        image_count=len(image_assets),
                        normalization_report=normalization_report,
                        relation_report=relation_report,
                        cleanup_report=cleanup_report,
                        structure_repair_report=structure_repair_report,
                    ),
                )
    structure_ai_attempted = should_run_ai
    structure_map, structure_summary = (
        _run_structure_recognition(
            paragraphs=paragraphs,
            image_assets=image_assets,
            app_config=app_config,
            progress_callback=progress_callback,
            normalization_report=normalization_report,
            relation_report=relation_report,
            cleanup_report=cleanup_report,
        )
        if should_run_ai
        else (None, StructureRecognitionSummary())
    )
    quality_gate_status, quality_gate_reasons = _resolve_pre_translation_quality_gate(
        structure_validation_report=structure_validation_report,
        structure_ai_attempted=structure_ai_attempted,
        structure_summary=structure_summary,
        app_config=app_config,
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
        quality_gate_status=quality_gate_status,
        quality_gate_reasons=list(quality_gate_reasons),
        ai_classified_count=structure_summary.ai_classified_count,
        ai_heading_count=structure_summary.ai_heading_count,
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
    source_text = build_document_text(paragraphs)
    translation_domain = str(app_config.get("translation_domain_default", "general") or "general").strip().lower() or "general"
    translation_domain_instructions = build_translation_domain_instructions(
        translation_domain=translation_domain,
        source_text=source_text,
    )
    emit_preparation_progress(
        progress_callback,
        stage="Текст собран",
        detail="Формирую цельный текст документа и считаю объём.",
        progress=0.6,
        metrics=_build_preparation_stage_metrics(
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
    )
    blocks = build_semantic_blocks(paragraphs, max_chars=chunk_size, relations=relations)
    emit_preparation_progress(
        progress_callback,
        stage="Смысловые блоки",
        detail="Группирую абзацы в блоки для модели.",
        progress=0.75,
        metrics=_build_preparation_stage_metrics(
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
    )
    jobs = _build_editing_jobs_with_optional_operation(
        blocks=blocks,
        max_chars=chunk_size,
        processing_operation=processing_operation,
    )
    emit_preparation_progress(
        progress_callback,
        stage="Задания собраны",
        detail="Готовлю финальный набор задач для обработки.",
        progress=0.9,
        metrics=_build_preparation_stage_metrics(
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
    )
    return PreparedDocumentData(
        source_text=source_text,
        paragraphs=paragraphs,
        image_assets=image_assets,
        relations=relations,
        jobs=jobs,
        prepared_source_key="",
        normalization_report=normalization_report,
        relation_report=relation_report,
        cleanup_report=cleanup_report,
        structure_repair_report=structure_repair_report,
        structure_map=structure_map,
        structure_recognition_summary=structure_summary,
        structure_validation_report=structure_validation_report,
            structure_recognition_mode=structure_mode,
            structure_ai_attempted=structure_ai_attempted,
            quality_gate_status=quality_gate_status,
            quality_gate_reasons=quality_gate_reasons,
            translation_domain=translation_domain,
            translation_domain_instructions=translation_domain_instructions,
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
        prepared_source_key=prepared_source_key,
        normalization_report=deepcopy(data.normalization_report),
        relation_report=deepcopy(data.relation_report),
        cleanup_report=deepcopy(data.cleanup_report),
        structure_repair_report=deepcopy(data.structure_repair_report),
        structure_map=deepcopy(data.structure_map),
        structure_recognition_summary=data.structure_recognition_summary,
        structure_validation_report=deepcopy(data.structure_validation_report),
        structure_recognition_mode=data.structure_recognition_mode,
        structure_ai_attempted=data.structure_ai_attempted,
        quality_gate_status=data.quality_gate_status,
        quality_gate_reasons=tuple(data.quality_gate_reasons),
        translation_domain=data.translation_domain,
        translation_domain_instructions=data.translation_domain_instructions,
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


def prepare_document_for_processing(
    *,
    uploaded_payload: FrozenUploadPayload,
    chunk_size: int,
    app_config: dict[str, Any] | None = None,
    processing_operation: str | None = None,
    session_state=None,
    progress_callback=None,
) -> PreparedDocumentData:
    resolved_config = load_app_config() if app_config is None else app_config
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
            app_config=resolved_config,
            processing_operation=resolved_processing_operation,
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
