from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any, cast

from docx import Document
from docx.oxml.ns import qn

import docxaicorrector.processing.processing_runtime as processing_runtime
from docxaicorrector.core.config import get_client, get_client_for_model_selector, get_provider_client, load_app_config, resolve_model_selector
from docxaicorrector.pipeline.output_validation import (
    collect_false_fragment_heading_samples,
    collect_list_fragment_regression_samples,
    collect_mixed_script_samples,
    collect_residual_bullet_glyph_samples,
    collect_theology_style_issue_samples,
    has_toc_body_concat_markdown as _shared_has_toc_body_concat_markdown,
)
from docxaicorrector.document._document import (
    build_semantic_blocks,
    build_document_text,
    extract_document_content_from_docx,
    extract_document_content_with_normalization_reports,
    extract_document_content_with_boundary_report,
    inspect_placeholder_integrity,
    summarize_boundary_normalization_metrics,
)
from docxaicorrector.generation.formatting_transfer import preserve_source_paragraph_properties
from docxaicorrector.generation._generation import convert_markdown_to_docx_bytes, ensure_pandoc_available
from docxaicorrector.image.reinsertion import reinsert_inline_images
from docxaicorrector.core.models import ParagraphBoundaryNormalizationReport
from docxaicorrector.processing.processing_service import clone_processing_service
from docxaicorrector.structure.topology import apply_document_map_topology
from docxaicorrector.validation.common import build_validation_event_logger, build_validation_runtime_config
from docxaicorrector.validation.profiles import (
    DocumentProfile,
    RunProfile,
    apply_runtime_resolution_to_app_config,
    load_validation_registry,
    resolve_runtime_resolution,
)
from docxaicorrector.processing.preparation import flatten_structure_repair_metrics


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
from docxaicorrector.structure.validation import validate_structure_quality

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FORMATTING_DIAGNOSTICS_DIR = PROJECT_ROOT / ".run" / "formatting_diagnostics"


def _build_markdown_quality_metrics(*, latest_markdown: str, translation_domain: str) -> dict[str, object]:
    false_fragment_heading_samples = collect_false_fragment_heading_samples(latest_markdown)
    residual_bullet_glyph_samples = collect_residual_bullet_glyph_samples(latest_markdown)
    list_fragment_regression_samples = collect_list_fragment_regression_samples(latest_markdown)
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
        "false_fragment_heading_count": len(false_fragment_heading_samples),
        "residual_bullet_glyph_count": len(residual_bullet_glyph_samples),
        "list_fragment_regression_count": len(list_fragment_regression_samples),
        "mixed_script_term_count": len(mixed_script_samples),
        "theology_style_deterministic_issue_count": len(theology_style_samples),
        "suspicious_heading_repetition_count": suspicious_heading_repetition_count,
        "scripture_reference_heading_count": scripture_reference_heading_count,
    }


def _count_effective_toc_regions_from_source(paragraphs: Sequence[object]) -> int:
    count = 0
    index = 0
    paragraph_units = list(paragraphs)
    while index < len(paragraph_units):
        structural_role = _normalized_structural_role(paragraph_units[index])
        if structural_role != "toc_header":
            index += 1
            continue
        look_ahead = index + 1
        while look_ahead < len(paragraph_units) and _normalized_structural_role(paragraph_units[look_ahead]) == "toc_entry":
            look_ahead += 1
        if look_ahead - index >= 3:
            count += 1
            index = look_ahead
            continue
        index += 1
    return count


def _normalized_structural_role(paragraph: object) -> str:
    return str(getattr(paragraph, "structural_role", "") or "").strip().lower()


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


def _unpack_extraction_result(extraction_result):
    paragraphs, image_assets, normalization_report, relations, relation_report, cleanup_report = extraction_result[:6]
    structure_repair_report = extraction_result[6] if len(extraction_result) > 6 else None
    return (
        paragraphs,
        image_assets,
        normalization_report,
        relations,
        relation_report,
        cleanup_report,
        structure_repair_report,
    )


@dataclass
class UploadedFileStub:
    name: str
    content: bytes
    position: int = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            data = self.content[self.position :]
            self.position = len(self.content)
            return data
        start = self.position
        end = min(len(self.content), start + size)
        self.position = end
        return self.content[start:end]

    def getvalue(self) -> bytes:
        return self.content

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.position = max(0, offset)
        elif whence == 1:
            self.position = max(0, self.position + offset)
        elif whence == 2:
            self.position = max(0, len(self.content) + offset)
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        return self.position


def evaluate_extraction_profile(document_profile: DocumentProfile) -> dict[str, object]:
    source_path = document_profile.resolved_source_path(PROJECT_ROOT)
    source_bytes = source_path.read_bytes()
    normalized_source = processing_runtime.normalize_uploaded_document(filename=source_path.name, source_bytes=source_bytes)
    (
        paragraphs,
        image_assets,
        normalization_report,
        _,
        relation_report,
        cleanup_report,
        _,
    ) = _unpack_extraction_result(extract_document_content_with_normalization_reports(BytesIO(normalized_source.content_bytes)))
    metrics = _build_structural_metrics(
        paragraphs=paragraphs,
        image_assets=image_assets,
        normalization_report=normalization_report,
        relation_report=relation_report,
        cleanup_report=cleanup_report,
    )
    checks = _build_extraction_checks(document_profile, metrics)
    return _build_validation_result(
        document_profile=document_profile,
        run_profile=None,
        tier="extraction",
        source_path=source_path,
        result="succeeded",
        metrics=metrics,
        checks=checks,
        runtime_config=None,
        output_artifacts=None,
        formatting_diagnostics=[],
    )


def run_structural_passthrough_validation(
    document_profile: DocumentProfile,
    run_profile: RunProfile,
) -> dict[str, object]:
    source_path = document_profile.resolved_source_path(PROJECT_ROOT)
    source_bytes = source_path.read_bytes()
    app_config = load_app_config()
    runtime_resolution = resolve_runtime_resolution(app_config, run_profile)
    runtime_config = apply_runtime_resolution_to_app_config(app_config, runtime_resolution)
    runtime = _build_runtime_capture()
    event_log: list[dict[str, object]] = []
    formatting_before = _snapshot_formatting_diagnostics_paths()
    try:
        result, prepared = _build_validation_processing_service(event_log).run_prepared_background_document(
            uploaded_file=UploadedFileStub(source_path.name, source_bytes),
            chunk_size=int(runtime_resolution.effective.chunk_size),
            image_mode=str(runtime_resolution.effective.image_mode),
            keep_all_image_variants=bool(runtime_resolution.effective.keep_all_image_variants),
            app_config=runtime_config,
            model=str(runtime_resolution.effective.model),
            max_retries=int(runtime_resolution.effective.max_retries),
            job_mutator=_build_passthrough_job,
            progress_callback=None,
            runtime=runtime,
        )
    except Exception as exc:
        checks = [
            {
                "name": "preparation_quality_gate_blocked",
                "passed": False,
                "error": str(exc),
            }
        ]
        preparation_diagnostic_snapshot = _build_preparation_diagnostic_snapshot_from_source(
            source_path=source_path,
            source_bytes=source_bytes,
            chunk_size=int(runtime_resolution.effective.chunk_size),
            event_log=event_log,
        )
        _apply_preparation_error_snapshot_fallback(preparation_diagnostic_snapshot, str(exc))
        return _build_validation_result(
            document_profile=document_profile,
            run_profile=run_profile,
            tier="structural",
            source_path=source_path,
            result="failed",
            metrics={
                "preparation_error": str(exc),
                "quality_gate_status": "",
                "quality_gate_reasons": [],
                "readiness_status": "",
            },
            checks=checks,
            runtime_config=build_validation_runtime_config(runtime_resolution),
            output_artifacts=None,
            formatting_diagnostics=[],
            event_log=event_log,
            preparation_diagnostic_snapshot=preparation_diagnostic_snapshot,
            validation_execution_mode="passthrough",
        )

    formatting_after = _snapshot_formatting_diagnostics_paths()
    formatting_paths = _collect_new_formatting_diagnostics_paths(formatting_before, formatting_after)
    formatting_diagnostics = _load_formatting_diagnostics_payloads(formatting_paths)
    canonical_formatting_diagnostics = _select_canonical_formatting_diagnostics_payload(formatting_diagnostics)
    canonical_formatting_payloads = [] if canonical_formatting_diagnostics is None else [canonical_formatting_diagnostics]

    runtime_state = _runtime_state(runtime)
    latest_docx_bytes = runtime_state.get("latest_docx_bytes")
    latest_markdown = str(runtime_state.get("latest_markdown") or "")
    if not isinstance(latest_docx_bytes, (bytes, bytearray)):
        latest_docx_bytes = b""
    output_artifacts = _build_output_artifacts(bytes(latest_docx_bytes), latest_markdown)

    (
        source_paragraphs,
        source_image_assets,
        source_normalization_report,
        source_relations,
        source_relation_report,
        source_cleanup_report,
        source_structure_repair_report,
    ) = _unpack_extraction_result(extract_document_content_with_normalization_reports(BytesIO(prepared.uploaded_file_bytes)))
    preparation_diagnostic_snapshot = build_preparation_diagnostic_snapshot(
        paragraphs=source_paragraphs,
        relations=source_relations,
        structure_repair_report=source_structure_repair_report,
        chunk_size=int(runtime_resolution.effective.chunk_size),
        event_log=event_log,
    )
    _apply_prepared_snapshot_fields(preparation_diagnostic_snapshot, prepared)
    _apply_topology_projection_snapshot_fallback(
        preparation_diagnostic_snapshot,
        prepared,
        app_config=runtime_config,
    )
    output_paragraphs = []
    output_image_assets = []
    if output_artifacts["output_docx_openable"]:
        output_paragraphs, output_image_assets = extract_document_content_from_docx(BytesIO(bytes(latest_docx_bytes)))
    metrics = _build_structural_metrics(
        paragraphs=source_paragraphs,
        image_assets=source_image_assets,
        normalization_report=source_normalization_report,
        relation_report=source_relation_report,
        cleanup_report=source_cleanup_report,
    )
    metrics.update(flatten_structure_repair_metrics(source_structure_repair_report))
    metrics.update(
        {
            "output_paragraph_count": len(output_paragraphs),
            "output_heading_count": sum(1 for paragraph in output_paragraphs if paragraph.role == "heading"),
            "output_numbered_item_count": sum(
                1 for paragraph in output_paragraphs if paragraph.role == "list" and paragraph.list_kind == "ordered"
            ),
            "output_image_count": len(output_image_assets),
            "output_table_count": sum(1 for paragraph in output_paragraphs if paragraph.role == "table"),
            "formatting_diagnostics_count": len(canonical_formatting_payloads),
            "max_unmapped_source_paragraphs": _max_payload_length(canonical_formatting_payloads, "unmapped_source_ids"),
            "max_unmapped_target_paragraphs": _max_payload_length(canonical_formatting_payloads, "unmapped_target_indexes"),
            "accepted_merged_sources_count": _count_payload_items(canonical_formatting_payloads, "accepted_merged_sources"),
            "max_accepted_merged_sources": _max_accepted_merged_sources(canonical_formatting_payloads),
            "relation_count": source_relation_report.total_relations,
            "rejected_relation_candidate_count": source_relation_report.rejected_candidate_count,
            "relation_counts": dict(source_relation_report.relation_counts),
            "text_similarity": _calculate_text_similarity(source_paragraphs, output_paragraphs),
            "heading_level_drift": _calculate_heading_level_drift(source_paragraphs, output_paragraphs),
            "heading_only_output_detected": _is_heading_only_markdown(latest_markdown),
            "output_docx_openable": bool(output_artifacts["output_docx_openable"]),
            "source_toc_detected": _has_toc_structural_roles(source_paragraphs),
            "output_toc_detected": _has_toc_structural_roles(output_paragraphs),
            "source_toc_region_count": _relation_count(source_relation_report, "toc_region"),
            "effective_source_toc_region_count": _count_effective_toc_regions_from_source(source_paragraphs),
            "bullet_heading_count": _count_bullet_headings(latest_markdown),
            "toc_body_concat_detected": _has_toc_body_concat_markdown(latest_markdown),
            "require_pdf_conversion_satisfied": source_path.suffix.lower() == ".pdf",
            "runtime_translation_domain": str(runtime_resolution.effective.translation_domain),
            "quality_gate_status": _extract_event_context_value(event_log, "structure_processing_outcome", "quality_gate_status"),
            "quality_gate_reasons": _extract_event_context_list(event_log, "structure_processing_outcome", "quality_gate_reasons"),
            "readiness_status": _extract_event_context_value(event_log, "structure_processing_outcome", "readiness_status"),
            "block_count": _extract_event_context_int(event_log, "block_plan_summary", "block_count"),
            "llm_block_count": _extract_event_context_int(event_log, "block_plan_summary", "llm_block_count"),
            "passthrough_block_count": _extract_event_context_int(event_log, "block_plan_summary", "passthrough_block_count"),
            "first_block_target_chars": _extract_event_context_int_list(
                event_log,
                "block_plan_summary",
                "first_block_target_chars",
            ),
        }
    )
    metrics.update(
        _build_markdown_quality_metrics(
            latest_markdown=latest_markdown,
            translation_domain=str(runtime_resolution.effective.translation_domain),
        )
    )
    _apply_prepared_metric_fields(metrics, prepared)
    _normalize_snapshot_or_metric_statuses(metrics)
    checks = _build_extraction_checks(document_profile, metrics)
    checks.extend(
        _build_structural_checks(
            document_profile=document_profile,
            result=result,
            metrics=metrics,
            output_artifacts=output_artifacts,
        )
    )
    return _build_validation_result(
        document_profile=document_profile,
        run_profile=run_profile,
        tier="structural",
        source_path=source_path,
        result=result,
        metrics=metrics,
        checks=checks,
        runtime_config=build_validation_runtime_config(runtime_resolution),
        output_artifacts=output_artifacts,
        formatting_diagnostics=formatting_diagnostics,
        event_log=event_log,
        preparation_diagnostic_snapshot=preparation_diagnostic_snapshot,
        validation_execution_mode="passthrough",
    )


def evaluate_structural_preparation_diagnostic(
    document_profile: DocumentProfile,
    run_profile: RunProfile,
) -> dict[str, object]:
    result = run_structural_passthrough_validation(document_profile, run_profile)
    metrics = cast(dict[str, object], result.get("metrics") or {})
    return {
        "document_profile_id": document_profile.id,
        "run_profile_id": run_profile.id,
        "validation_tier": result.get("validation_tier"),
        "validation_execution_mode": result.get("validation_execution_mode"),
        "passed": bool(result.get("passed")),
        "failed_checks": list(cast(list[str], result.get("failed_checks") or [])),
        "preparation_error": metrics.get("preparation_error"),
        "preparation_diagnostic_snapshot": result.get("preparation_diagnostic_snapshot"),
    }


def _build_validation_result(
    *,
    document_profile: DocumentProfile,
    run_profile: RunProfile | None,
    tier: str,
    source_path: Path,
    result: str,
    metrics: dict[str, object],
    checks: list[dict[str, object]],
    runtime_config: dict[str, object] | None,
    output_artifacts: dict[str, object] | None,
    formatting_diagnostics: list[dict[str, object]],
    event_log: list[dict[str, object]] | None = None,
    preparation_diagnostic_snapshot: dict[str, object] | None = None,
    validation_execution_mode: str | None = None,
) -> dict[str, object]:
    failed_checks = [str(check["name"]) for check in checks if not bool(check["passed"])]
    return {
        "document_profile_id": document_profile.id,
        "run_profile_id": None if run_profile is None else run_profile.id,
        "validation_tier": tier,
        "validation_execution_mode": validation_execution_mode,
        "source_document_path": str(source_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "result": result,
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "metrics": metrics,
        "checks": checks,
        "runtime_config": runtime_config,
        "output_artifacts": output_artifacts,
        "formatting_diagnostics": formatting_diagnostics,
        "event_log": event_log or [],
        "preparation_diagnostic_snapshot": preparation_diagnostic_snapshot,
    }


def _build_preparation_diagnostic_snapshot_from_source(
    *,
    source_path: Path,
    source_bytes: bytes,
    chunk_size: int,
    event_log: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    try:
        normalized_source = processing_runtime.normalize_uploaded_document(filename=source_path.name, source_bytes=source_bytes)
        (
            paragraphs,
            _,
            _,
            relations,
            _,
            _,
            structure_repair_report,
        ) = _unpack_extraction_result(
            extract_document_content_with_normalization_reports(BytesIO(normalized_source.content_bytes))
        )
    except Exception as exc:
        snapshot = _build_preparation_diagnostic_defaults(event_log)
        snapshot["snapshot_error"] = str(exc)
        return snapshot
    snapshot = build_preparation_diagnostic_snapshot(
        paragraphs=paragraphs,
        relations=relations,
        structure_repair_report=structure_repair_report,
        chunk_size=chunk_size,
        event_log=event_log,
    )
    app_config = load_app_config()
    if isinstance(app_config, Mapping):
        app_config_mapping = cast(Mapping[str, Any], app_config)
    elif hasattr(app_config, "to_dict") and callable(getattr(app_config, "to_dict")):
        app_config_mapping = cast(Mapping[str, Any], app_config.to_dict())
    else:
        app_config_mapping = {}
    structure_validation_report = validate_structure_quality(
        paragraphs=cast(Sequence[Any], paragraphs),
        app_config=app_config_mapping,
        structure_repair_report=structure_repair_report,
    )
    _apply_structure_validation_snapshot_fields(snapshot, structure_validation_report)
    return snapshot


def build_preparation_diagnostic_snapshot(
    *,
    paragraphs: Sequence[object],
    relations: Sequence[object] | None,
    structure_repair_report: object | None,
    chunk_size: int,
    event_log: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    snapshot = _build_preparation_diagnostic_defaults(event_log)
    paragraph_units = list(paragraphs)
    semantic_blocks = build_semantic_blocks(
        cast(list[Any], paragraph_units),
        max_chars=chunk_size,
        relations=None if relations is None else cast(list[Any], list(relations)),
    )
    first_block_paragraphs = [] if not semantic_blocks else list(semantic_blocks[0].paragraphs)
    first_block_target_chars = _extract_first_block_target_chars(
        event_log=event_log,
        semantic_blocks=semantic_blocks,
    )
    snapshot.update(
        {
            "paragraph_count": len(paragraph_units),
            "heading_count": sum(1 for paragraph in paragraph_units if getattr(paragraph, "role", None) == "heading"),
            "toc_header_count": sum(
                1
                for paragraph in paragraph_units
                if str(getattr(paragraph, "structural_role", "") or "").strip().lower() == "toc_header"
            ),
            "toc_entry_count": sum(
                1
                for paragraph in paragraph_units
                if str(getattr(paragraph, "structural_role", "") or "").strip().lower() == "toc_entry"
            ),
            "bounded_toc_region_count": int(getattr(structure_repair_report, "bounded_toc_regions", 0) or 0),
            "repaired_bullet_items": int(getattr(structure_repair_report, "repaired_bullet_items", 0) or 0),
            "repaired_numbered_items": int(getattr(structure_repair_report, "repaired_numbered_items", 0) or 0),
            "toc_body_boundary_repairs": int(getattr(structure_repair_report, "toc_body_boundary_repairs", 0) or 0),
            "remaining_isolated_marker_count": int(
                getattr(structure_repair_report, "remaining_isolated_marker_count", 0) or 0
            ),
            "semantic_block_count": len(semantic_blocks),
            "first_block_target_chars": first_block_target_chars,
            "first_block_has_toc": _block_has_toc(first_block_paragraphs),
            "first_block_has_epigraph": _block_has_epigraph(first_block_paragraphs),
            "first_block_has_body_start": _block_has_body_start(first_block_paragraphs),
            "first_block_has_isolated_marker": _block_has_isolated_marker(first_block_paragraphs),
        }
    )
    return snapshot


def _build_preparation_diagnostic_defaults(event_log: Sequence[Mapping[str, object]]) -> dict[str, object]:
    outline_coverage_ratio = _extract_event_context_float(event_log, "structure_processing_outcome", "outline_coverage_ratio")
    if outline_coverage_ratio is None:
        outline_coverage_ratio = _extract_event_context_float(event_log, "reconciliation_report_saved", "outline_coverage_ratio")
    document_map_status = str(
        _extract_event_context_value(event_log, "structure_processing_outcome", "document_map_status") or ""
    ).strip()
    document_map_status_reason = str(
        _extract_event_context_value(event_log, "structure_processing_outcome", "document_map_status_reason") or ""
    ).strip()
    topology_status = str(
        _extract_event_context_value(event_log, "structure_processing_outcome", "document_topology_projection_status") or ""
    ).strip()
    topology_status_reason = str(
        _extract_event_context_value(event_log, "structure_processing_outcome", "document_topology_projection_status_reason") or ""
    ).strip()
    topology_artifact_path = ""
    for event in reversed(list(event_log)):
        event_id = str(event.get("event_id") or "").strip()
        if event_id not in {"document_topology_projection_built", "document_topology_projection_skipped"}:
            continue
        context = cast(Mapping[str, object], event.get("context") or {})
        if not topology_status:
            if event_id == "document_topology_projection_built":
                topology_status = "built"
            else:
                reason = str(context.get("reason") or "").strip()
                topology_status = "no_operations" if reason == "no_operations" else "skipped"
                if not topology_status_reason:
                    topology_status_reason = reason
        topology_artifact_path = str(context.get("artifact_path") or "").strip()
        if topology_artifact_path:
            break
    topology_projection = None
    if topology_artifact_path:
        artifact_path = Path(topology_artifact_path)
        if not artifact_path.is_absolute():
            artifact_path = (PROJECT_ROOT / artifact_path).resolve()
        if artifact_path.exists():
            try:
                topology_projection = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                topology_projection = None
    snapshot = {
        "paragraph_count": 0,
        "heading_count": 0,
        "toc_header_count": 0,
        "toc_entry_count": 0,
        "bounded_toc_region_count": 0,
        "repaired_bullet_items": 0,
        "repaired_numbered_items": 0,
        "toc_body_boundary_repairs": 0,
        "remaining_isolated_marker_count": 0,
        "readiness_status": _extract_event_context_value(event_log, "structure_processing_outcome", "readiness_status"),
        "readiness_reasons": _extract_event_context_list(event_log, "structure_processing_outcome", "readiness_reasons"),
        "document_map_present": _extract_event_context_bool(event_log, "structure_processing_outcome", "document_map_present"),
        "outline_coverage_ratio": outline_coverage_ratio,
        "document_topology_projection_status": topology_status or "not_requested",
        "document_topology_projection_status_reason": topology_status_reason,
        "document_topology_projection": topology_projection,
        "front_matter_leaks": _extract_event_context_int_list(event_log, "reconciliation_report_saved", "front_matter_leaks"),
        "front_matter_body_advisories": _extract_event_context_int_list(
            event_log,
            "reconciliation_report_saved",
            "front_matter_body_advisories",
        ),
        "targeted_recall_invoked": _extract_event_context_bool(event_log, "reconciliation_report_saved", "targeted_recall_invoked"),
        "quality_gate_status": _extract_event_context_value(event_log, "structure_processing_outcome", "quality_gate_status"),
        "quality_gate_reasons": _extract_event_context_list(event_log, "structure_processing_outcome", "quality_gate_reasons"),
        "structure_ai_attempted": _extract_event_context_bool(event_log, "structure_processing_outcome", "structure_ai_attempted"),
        "ai_first_degraded": _extract_event_context_bool(event_log, "structure_processing_outcome", "ai_first_degraded"),
        "fallback_stage": _extract_event_context_value(event_log, "structure_processing_outcome", "fallback_stage"),
        "fallback_reason": _extract_event_context_value(event_log, "structure_processing_outcome", "fallback_reason"),
        "document_map_status": document_map_status or "not_requested",
        "document_map_status_reason": document_map_status_reason,
        "ai_classified_count": _extract_event_context_int(event_log, "structure_processing_outcome", "ai_classified_count"),
        "ai_heading_count": _extract_event_context_int(event_log, "structure_processing_outcome", "ai_heading_count"),
        "semantic_block_count": 0,
        "first_block_target_chars": 0,
        "first_block_has_toc": False,
        "first_block_has_epigraph": False,
        "first_block_has_body_start": False,
        "first_block_has_isolated_marker": False,
    }
    return snapshot


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


def _apply_prepared_snapshot_fields(snapshot: dict[str, object], prepared: object) -> None:
    structure_validation_report = getattr(prepared, "structure_validation_report", None)
    structure_summary = getattr(prepared, "structure_recognition_summary", None)
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
        snapshot["document_map_present"] = bool(getattr(prepared, "document_map", None) is not None)
    current_topology_status = str(snapshot.get("document_topology_projection_status") or "").strip().lower()
    prepared_topology_status = str(getattr(prepared, "document_topology_projection_status", "") or "").strip()
    if prepared_topology_status and current_topology_status in {"", "not_requested"}:
        snapshot["document_topology_projection_status"] = prepared_topology_status
    current_topology_reason = str(snapshot.get("document_topology_projection_status_reason") or "")
    prepared_topology_reason = str(getattr(prepared, "document_topology_projection_status_reason", "") or "").strip()
    if not current_topology_reason and prepared_topology_reason:
        snapshot["document_topology_projection_status_reason"] = prepared_topology_reason
    prepared_topology_projection = getattr(prepared, "document_topology_projection", None)
    if prepared_topology_projection is not None:
        snapshot["document_topology_projection"] = asdict(prepared_topology_projection)
    _apply_quality_gate_readiness_fallback(snapshot)
    _normalize_snapshot_or_metric_statuses(snapshot)


def _apply_topology_projection_snapshot_fallback(
    snapshot: dict[str, object],
    prepared: object,
    *,
    app_config: Mapping[str, Any],
) -> None:
    current_topology_status = str(snapshot.get("document_topology_projection_status") or "").strip().lower()
    if current_topology_status not in {"", "not_requested"}:
        return
    if not bool(app_config.get("structure_recovery_enabled", False)):
        return
    if not bool(app_config.get("structure_recovery_topology_projection_enabled", False)):
        return
    paragraphs = list(getattr(prepared, "paragraphs", []) or [])
    document_map = getattr(prepared, "document_map", None)
    if not paragraphs or document_map is None:
        return
    try:
        projection = apply_document_map_topology(
            paragraphs,
            document_map,
            app_config=app_config,
        )
    except Exception:
        return
    snapshot["document_topology_projection"] = asdict(projection)
    snapshot["document_topology_projection_status"] = "built" if projection.operations or projection.projected_units else "no_operations"
    snapshot["document_topology_projection_status_reason"] = ""
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


def _apply_prepared_metric_fields(metrics: dict[str, object], prepared: object) -> None:
    structure_validation_report = getattr(prepared, "structure_validation_report", None)
    structure_summary = getattr(prepared, "structure_recognition_summary", None)
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


def _build_passthrough_job(job: Mapping[str, object]) -> dict[str, object]:
    cloned = dict(job)
    cloned["job_kind"] = "passthrough"
    return cloned


def _build_validation_processing_service(event_log: list[dict[str, object]]):
    def _run_document_processing_impl(**kwargs: Any) -> str:
        from docxaicorrector.pipeline._pipeline import run_document_processing

        return cast(str, run_document_processing(**kwargs))

    return clone_processing_service(
        get_client_fn=get_client,
        get_provider_client_fn=get_provider_client,
        get_client_for_model_selector_fn=get_client_for_model_selector,
        resolve_model_selector_fn=resolve_model_selector,
        load_system_prompt_fn=lambda: "",
        ensure_pandoc_available_fn=ensure_pandoc_available,
        generate_markdown_block_fn=lambda **kwargs: cast(str, kwargs.get("target_text") or ""),
        convert_markdown_to_docx_bytes_fn=convert_markdown_to_docx_bytes,
        process_document_images_impl_fn=lambda **kwargs: list(kwargs.get("image_assets") or []),
        analyze_image_fn=lambda *args, **kwargs: None,
        generate_image_candidate_fn=lambda *args, **kwargs: b"",
        validate_redraw_result_fn=lambda *args, **kwargs: None,
        detect_image_mime_type_fn=lambda *args, **kwargs: None,
        inspect_placeholder_integrity_fn=_inspect_placeholder_integrity_adapter,
        preserve_source_paragraph_properties_fn=_preserve_source_paragraph_properties_adapter,
        reinsert_inline_images_fn=_reinsert_inline_images_adapter,
        run_document_processing_impl_fn=_run_document_processing_impl,
        present_error_fn=lambda code, exc, title, **context: f"{title}: {exc}",
        log_event_fn=build_validation_event_logger(event_log),
        emit_state_fn=_emit_state,
        emit_finalize_fn=_emit_finalize,
        emit_activity_fn=_emit_activity,
        emit_log_fn=_emit_log,
        emit_status_fn=_emit_status,
        emit_image_log_fn=lambda runtime, **payload: None,
        emit_image_reset_fn=lambda runtime: None,
        should_stop_processing_fn=lambda runtime: False,
        resolve_uploaded_filename_fn=processing_runtime.resolve_uploaded_filename,
        image_model_call_budget_cls=object,
        image_model_call_budget_exceeded_cls=RuntimeError,
    )


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
    checks = [
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
            "passed": _as_int(metrics, "max_unmapped_source_paragraphs") <= document_profile.max_unmapped_source_paragraphs,
            "actual": metrics["max_unmapped_source_paragraphs"],
            "allowed": document_profile.max_unmapped_source_paragraphs,
        },
        {
            "name": "unmapped_target_threshold",
            "passed": _as_int(metrics, "max_unmapped_target_paragraphs") <= document_profile.max_unmapped_target_paragraphs,
            "actual": metrics["max_unmapped_target_paragraphs"],
            "allowed": document_profile.max_unmapped_target_paragraphs,
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
        source_toc_boundary_repaired = (
            _as_int(metrics, "structure_repair_toc_body_boundary_repairs") > 0
            or _as_int(metrics, "effective_source_toc_region_count") > 0
        )
        checks.append(
            {
                "name": "no_toc_body_concat_required",
                "passed": not bool(metrics.get("toc_body_concat_detected")) and source_toc_boundary_repaired,
                "toc_body_concat_detected": metrics.get("toc_body_concat_detected"),
                "structure_repair_toc_body_boundary_repairs": metrics.get("structure_repair_toc_body_boundary_repairs"),
                "effective_source_toc_region_count": metrics.get("effective_source_toc_region_count"),
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


def _check_minimum(name: str, actual: int, minimum: int) -> dict[str, object]:
    return {"name": name, "passed": actual >= minimum, "actual": actual, "minimum": minimum}


def _snapshot_formatting_diagnostics_paths() -> set[str]:
    if not FORMATTING_DIAGNOSTICS_DIR.exists():
        return set()
    return {str(path.resolve()) for path in FORMATTING_DIAGNOSTICS_DIR.glob("*.json") if path.is_file()}


def _collect_new_formatting_diagnostics_paths(before: set[str], after: set[str]) -> list[str]:
    new_paths = [Path(path) for path in after - before]
    return [str(path) for path in sorted(new_paths, key=lambda candidate: (candidate.stat().st_mtime, str(candidate)))]


def _load_formatting_diagnostics_payloads(artifact_paths: Sequence[str]) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for artifact_path in artifact_paths:
        try:
            payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _select_canonical_formatting_diagnostics_payload(
    payloads: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    if not payloads:
        return None
    return payloads[-1]


def _max_payload_length(payloads: Sequence[Mapping[str, object]], key: str) -> int:
    maximum = 0
    for payload in payloads:
        values = payload.get(key) or []
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)):
            maximum = max(maximum, len(values))
    return maximum


def _count_payload_items(payloads: Sequence[Mapping[str, object]], key: str) -> int:
    total = 0
    for payload in payloads:
        values = payload.get(key) or []
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)):
            total += len(values)
    return total


def _max_accepted_merged_sources(payloads: Sequence[Mapping[str, object]]) -> int:
    maximum = 0
    for payload in payloads:
        explicit_value = payload.get("max_accepted_merged_sources")
        if explicit_value is not None:
            try:
                maximum = max(maximum, int(cast(Any, explicit_value)))
                continue
            except (TypeError, ValueError):
                pass

        accepted_sources = payload.get("accepted_merged_sources") or []
        if not isinstance(accepted_sources, Sequence) or isinstance(accepted_sources, (str, bytes, bytearray)):
            continue
        for entry in accepted_sources:
            if not isinstance(entry, Mapping):
                continue
            explicit_count = entry.get("accepted_merged_sources_count")
            if explicit_count is not None:
                try:
                    maximum = max(maximum, int(explicit_count))
                    continue
                except (TypeError, ValueError):
                    pass
            raw_indexes = entry.get("origin_raw_indexes") or []
            if isinstance(raw_indexes, Sequence) and not isinstance(raw_indexes, (str, bytes, bytearray)):
                maximum = max(maximum, len(raw_indexes))
    return maximum


def _calculate_text_similarity(source_paragraphs: Sequence[object], output_paragraphs: Sequence[object]) -> float:
    source_text = _normalize_text(build_document_text(cast(list[Any], list(source_paragraphs))))
    output_text = _normalize_text(build_document_text(cast(list[Any], list(output_paragraphs))))
    if not source_text and not output_text:
        return 1.0
    return round(SequenceMatcher(None, source_text, output_text).ratio(), 4)


def _calculate_heading_level_drift(source_paragraphs: Sequence[object], output_paragraphs: Sequence[object]) -> int:
    output_levels: dict[str, int] = {}
    for paragraph in output_paragraphs:
        if getattr(paragraph, "role", None) != "heading":
            continue
        normalized = _normalize_text(str(getattr(paragraph, "text", "")))
        if not normalized:
            continue
        output_levels[normalized] = int(getattr(paragraph, "heading_level", 0) or 0)

    max_drift = 0
    for paragraph in source_paragraphs:
        if getattr(paragraph, "role", None) != "heading":
            continue
        normalized = _normalize_text(str(getattr(paragraph, "text", "")))
        if not normalized or normalized not in output_levels:
            continue
        source_level = int(getattr(paragraph, "heading_level", 0) or 0)
        max_drift = max(max_drift, abs(source_level - output_levels[normalized]))
    return max_drift


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    normalized = re.sub(r"^#{1,6}\s+", "", normalized)
    return normalized


def _is_heading_only_markdown(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("#") and len(line.split()) >= 2 for line in lines)


def _has_toc_structural_roles(paragraphs: Sequence[object]) -> bool:
    for paragraph in paragraphs:
        structural_role = str(getattr(paragraph, "structural_role", "") or "").strip().lower()
        if structural_role in {"toc_header", "toc_entry"}:
            return True
    return False


def _count_bullet_headings(markdown_text: str) -> int:
    return sum(
        1
        for line in markdown_text.splitlines()
        if re.match(r"^#{1,6}\s*[●•\-*]\s*$", line.strip())
    )


def _has_toc_body_concat_markdown(markdown_text: str) -> bool:
    return _shared_has_toc_body_concat_markdown(markdown_text)


def _relation_count(relation_report: object, key: str) -> int:
    relation_counts = getattr(relation_report, "relation_counts", {}) or {}
    if not isinstance(relation_counts, Mapping):
        return 0
    value = relation_counts.get(key, 0)
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return 0


def _extract_event_context(event_log: Sequence[Mapping[str, object]], event_id: str) -> Mapping[str, object]:
    for event in reversed(event_log):
        if str(event.get("event_id") or "") != event_id:
            continue
        context = event.get("context")
        if isinstance(context, Mapping):
            return context
        break
    return {}


def _extract_event_context_value(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> str:
    context = _extract_event_context(event_log, event_id)
    value = context.get(key)
    return "" if value is None else str(value)


def _extract_event_context_list(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> list[str]:
    context = _extract_event_context(event_log, event_id)
    values = context.get(key)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return []
    return [str(value) for value in values]


def _extract_event_context_int(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> int:
    context = _extract_event_context(event_log, event_id)
    value = context.get(key)
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return 0


def _extract_event_context_float(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> float | None:
    context = _extract_event_context(event_log, event_id)
    value = context.get(key)
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _extract_event_context_bool(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> bool:
    context = _extract_event_context(event_log, event_id)
    value = context.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _extract_event_context_int_list(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> list[int]:
    context = _extract_event_context(event_log, event_id)
    values = context.get(key)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return []
    result: list[int] = []
    for value in values:
        try:
            result.append(int(cast(Any, value)))
        except (TypeError, ValueError):
            continue
    return result


def _build_output_artifacts(docx_bytes: bytes, markdown_text: str) -> dict[str, object]:
    openable = False
    output_paragraphs = 0
    output_inline_shapes = 0
    output_visible_text_chars = 0
    output_contains_placeholder_markup = False
    if docx_bytes:
        try:
            document = Document(BytesIO(docx_bytes))
        except Exception:
            document = None
        if document is not None:
            openable = True
            output_paragraphs = len(document.paragraphs)
            output_inline_shapes = len(document.inline_shapes)
            output_visible_text_chars = len("\n".join(paragraph.text for paragraph in document.paragraphs))
            output_contains_placeholder_markup = "[[DOCX_IMAGE_" in document._element.xml
    return {
        "output_docx_openable": openable,
        "output_paragraphs": output_paragraphs,
        "output_inline_shapes": output_inline_shapes,
        "output_visible_text_chars": output_visible_text_chars,
        "output_contains_placeholder_markup": output_contains_placeholder_markup,
        "markdown_chars": len(markdown_text),
    }


def _build_runtime_capture() -> dict[str, object]:
    return {"state": {}, "finalize": [], "activity": [], "log": [], "status": []}


def _runtime_mapping(runtime: object) -> dict[str, object]:
    return cast(dict[str, object], runtime)


def _runtime_state(runtime: object) -> dict[str, object]:
    return cast(dict[str, object], _runtime_mapping(runtime).setdefault("state", {}))


def _emit_state(runtime: object, **values: object) -> None:
    _runtime_state(runtime).update(values)


def _emit_finalize(
    runtime: object,
    stage: str,
    detail: str,
    progress: float,
    terminal_kind: str | None = None,
) -> None:
    cast(list[object], _runtime_mapping(runtime).setdefault("finalize", [])).append(
        (stage, detail, progress, terminal_kind)
    )


def _emit_activity(runtime: object, message: str) -> None:
    cast(list[object], _runtime_mapping(runtime).setdefault("activity", [])).append(message)


def _emit_log(runtime: object, **payload: object) -> None:
    cast(list[object], _runtime_mapping(runtime).setdefault("log", [])).append(payload)


def _emit_status(runtime: object, **payload: object) -> None:
    cast(list[object], _runtime_mapping(runtime).setdefault("status", [])).append(payload)


def _inspect_placeholder_integrity_adapter(markdown_text: str, image_assets: Sequence[object]) -> Mapping[str, str]:
    return inspect_placeholder_integrity(markdown_text, cast(list[Any], list(image_assets)))


def _parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print a structural preparation diagnostic snapshot for a validation profile.")
    parser.add_argument("document_profile_id", help="Validation document profile id, for example end-times-pdf-core.")
    parser.add_argument("--run-profile-id", dest="run_profile_id", help="Optional run profile override.")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_cli_args(argv)
    registry = load_validation_registry()
    document_profile = registry.get_document_profile(str(args.document_profile_id))
    run_profile_id = str(args.run_profile_id or getattr(document_profile, "structural_run_profile", "") or "").strip()
    run_profile = registry.get_run_profile(run_profile_id) if run_profile_id else registry.get_run_profile("structural-passthrough-default")
    payload = evaluate_structural_preparation_diagnostic(document_profile, run_profile)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _preserve_source_paragraph_properties_adapter(
    docx_bytes: bytes,
    paragraphs: Sequence[object],
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> bytes:
    return preserve_source_paragraph_properties(
        docx_bytes,
        cast(list[Any], list(paragraphs)),
        generated_paragraph_registry=generated_paragraph_registry,
    )


def _reinsert_inline_images_adapter(docx_bytes: bytes, image_assets: Sequence[object]) -> bytes:
    return reinsert_inline_images(docx_bytes, cast(list[Any], list(image_assets)))


def _as_int(metrics: Mapping[str, object], key: str) -> int:
    return int(cast(int, metrics.get(key, 0) or 0))


def _as_float(metrics: Mapping[str, object], key: str) -> float:
    return float(cast(float, metrics[key]))


if __name__ == "__main__":
    raise SystemExit(main())
