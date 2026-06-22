from __future__ import annotations

import argparse
from collections.abc import Collection, Mapping, Sequence
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
    collect_bullet_heading_samples,
    collect_false_fragment_heading_samples,
    collect_list_fragment_regression_samples,
    collect_mixed_script_samples,
    collect_page_placeholder_heading_concat_samples,
    collect_residual_bullet_glyph_samples,
    collect_theology_style_issue_samples,
    has_toc_body_concat_markdown as _shared_has_toc_body_concat_markdown,
)
from docxaicorrector.pipeline.display_hygiene import summarize_structure_quality_detectors
from docxaicorrector.document._document import (
    build_semantic_blocks,
    build_document_text,
    extract_document_content_from_docx,
    extract_document_content_with_normalization_reports,
    extract_document_content_with_boundary_report,
    inspect_placeholder_integrity,
    summarize_boundary_normalization_metrics,
)
from docxaicorrector.generation.formatting_diagnostics_retention import write_formatting_diagnostics_artifact
from docxaicorrector.generation.formatting_transfer import preserve_source_paragraph_properties
from docxaicorrector.generation._generation import convert_markdown_to_docx_bytes, ensure_pandoc_available
from docxaicorrector.image.reinsertion import reinsert_inline_images
from docxaicorrector.core.models import ParagraphBoundaryNormalizationReport, ParagraphUnit
from docxaicorrector.processing.processing_service import clone_processing_service
from docxaicorrector.structure.layout_signals import derive_layout_signals
from docxaicorrector.validation.common import build_validation_event_logger, build_validation_runtime_config
from docxaicorrector.validation.formatting_coverage import (
    resolve_role_aware_formatting_unmapped_source_summary,
)
from docxaicorrector.validation.profiles import (
    DocumentProfile,
    RunProfile,
    apply_runtime_resolution_to_app_config,
    load_validation_registry,
    resolve_runtime_resolution,
)
from docxaicorrector.validation.quality_gate_audit import quality_gate_audit_classifications_payload
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


def _extract_quality_report_artifact_path(event_log: Sequence[Mapping[str, object]]) -> str | None:
    for event in reversed(event_log):
        if str(event.get("event_id") or "").strip() != "quality_report_saved":
            continue
        context = event.get("context")
        if not isinstance(context, Mapping):
            continue
        artifact_path = context.get("artifact_path")
        if isinstance(artifact_path, str) and artifact_path.strip():
            return artifact_path.strip()
    return None


def _load_translation_quality_report(event_log: Sequence[Mapping[str, object]]) -> tuple[dict[str, object] | None, str | None]:
    artifact_path = _extract_quality_report_artifact_path(event_log)
    if not artifact_path:
        return None, None
    candidate = Path(artifact_path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return None, str(candidate)
    if not isinstance(payload, dict):
        return None, str(candidate)
    return payload, str(candidate)


def _merge_translation_quality_report_metrics(
    metrics: dict[str, object],
    translation_quality_report: Mapping[str, object],
) -> None:
    for key in (
        "unmapped_source_count_basis",
        "worst_unmapped_source_count",
        "raw_unmapped_source_paragraph_count",
        "filtered_unmapped_source_count",
        "format_neutral_creditable_count",
        "effective_unmapped_source_count",
        "role_aware_formatting_coverage_note",
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
        "scripture_reference_heading_count",
        "suspicious_heading_repetition_count",
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
    ):
        if key in translation_quality_report:
            metrics[key] = translation_quality_report[key]


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


def _has_high_confidence_bounded_document_map_toc_region(document_map: object | None) -> bool:
    toc_region = getattr(document_map, "toc_region", None)
    if toc_region is None:
        return False
    if str(getattr(toc_region, "confidence", "") or "").strip().lower() != "high":
        return False
    return int(getattr(toc_region, "start_logical_index", 0)) <= int(getattr(toc_region, "end_logical_index", -1))


def _count_document_map_anchor_roles(document_map: object | None, *, role: str) -> int:
    paragraph_anchors = getattr(document_map, "paragraph_anchors", None)
    if not paragraph_anchors:
        return 0
    normalized_role = str(role or "").strip().lower()
    return sum(
        1
        for anchor in dict(paragraph_anchors).values()
        if str(getattr(anchor, "role", "") or "").strip().lower() == normalized_role
    )


def _count_topology_toc_entry_units(projection: object | None) -> int:
    projected_units = getattr(projection, "projected_units", None)
    if not projected_units:
        return 0
    return sum(
        1
        for unit in tuple(projected_units)
        if str(getattr(unit, "role", "") or "").strip().lower() == "toc_entry"
        or str(getattr(unit, "unit_type", "") or "").strip().lower() == "toc_entry"
    )


def _count_topology_operations(projection: object | None, *, op: str) -> int:
    operations = getattr(projection, "operations", None)
    if not operations:
        return 0
    normalized_op = str(op or "").strip().lower()
    count = 0
    for operation in tuple(operations):
        if str(getattr(operation, "op", "") or "").strip().lower() == normalized_op:
            count += 1
    return count


def _resolve_bounded_toc_region_range(document_map: object | None) -> tuple[int, int] | None:
    if not _has_high_confidence_bounded_document_map_toc_region(document_map):
        return None
    toc_region = getattr(document_map, "toc_region", None)
    if toc_region is None:
        return None
    return int(getattr(toc_region, "start_logical_index", 0)), int(getattr(toc_region, "end_logical_index", -1))


def _count_high_confidence_compound_toc_split_hints(document_map: object | None) -> int:
    toc_bounds = _resolve_bounded_toc_region_range(document_map)
    split_hints = getattr(document_map, "split_hints", None)
    if toc_bounds is None or not split_hints:
        return 0
    start_logical_index, end_logical_index = toc_bounds
    count = 0
    for split_hint in tuple(split_hints):
        if str(getattr(split_hint, "split_kind", "") or "").strip().lower() != "compound_toc_entries":
            continue
        if str(getattr(split_hint, "confidence", "") or "").strip().lower() != "high":
            continue
        logical_index = int(getattr(split_hint, "logical_index", -1) or -1)
        if logical_index < start_logical_index or logical_index > end_logical_index:
            continue
        expected_parts = tuple(
            str(value or "").strip()
            for value in tuple(getattr(split_hint, "expected_parts", ()) or ())
            if str(value or "").strip()
        )
        if len(expected_parts) < 2:
            continue
        count += 1
    return count


def _projection_has_heading_inside_toc_region(
    projection: object | None,
    *,
    start_logical_index: int,
    end_logical_index: int,
) -> bool:
    projected_units = getattr(projection, "projected_units", None)
    if not projected_units:
        return False
    for unit in tuple(projected_units):
        role = str(getattr(unit, "role", "") or "").strip().lower()
        unit_type = str(getattr(unit, "unit_type", "") or "").strip().lower()
        if role != "heading" and unit_type not in {"chapter_heading", "section_heading"}:
            continue
        logical_indexes = tuple(int(index) for index in tuple(getattr(unit, "logical_indexes", ()) or ()))
        if any(start_logical_index <= logical_index <= end_logical_index for logical_index in logical_indexes):
            return True
    return False


def _projection_has_toc_entry_outside_toc_region(
    projection: object | None,
    *,
    start_logical_index: int,
    end_logical_index: int,
) -> bool:
    projected_units = getattr(projection, "projected_units", None)
    if not projected_units:
        return False
    for unit in tuple(projected_units):
        role = str(getattr(unit, "role", "") or "").strip().lower()
        unit_type = str(getattr(unit, "unit_type", "") or "").strip().lower()
        if role != "toc_entry" and unit_type != "toc_entry":
            continue
        logical_indexes = tuple(int(index) for index in tuple(getattr(unit, "logical_indexes", ()) or ()))
        if any(logical_index < start_logical_index or logical_index > end_logical_index for logical_index in logical_indexes):
            return True
    return False


def _document_map_has_high_confidence_outline_inside_toc_region(
    document_map: object | None,
    *,
    start_logical_index: int,
    end_logical_index: int,
) -> bool:
    outline = getattr(document_map, "outline", None)
    if not outline:
        return False
    for entry in tuple(outline):
        if str(getattr(entry, "confidence", "") or "").strip().lower() != "high":
            continue
        logical_index = int(getattr(entry, "logical_index", -1) or -1)
        if start_logical_index <= logical_index <= end_logical_index:
            return True
    return False


def _projection_has_units_or_operations(projection: object | None) -> bool:
    if projection is None:
        return False
    return bool(getattr(projection, "operations", None) or getattr(projection, "projected_units", None))


def _is_authoritative_topology_signal(*, authority: object, confidence: object) -> bool:
    normalized_authority = str(authority or "").strip().lower()
    normalized_confidence = str(confidence or "").strip().lower()
    return normalized_confidence == "high" and normalized_authority.startswith("document_map")


def _count_authoritative_topology_toc_entry_units(projection: object | None) -> int:
    projected_units = getattr(projection, "projected_units", None)
    if not projected_units:
        return 0
    count = 0
    for unit in tuple(projected_units):
        if not _is_authoritative_topology_signal(
            authority=getattr(unit, "authority", ""),
            confidence=getattr(unit, "confidence", ""),
        ):
            continue
        role = str(getattr(unit, "role", "") or "").strip().lower()
        unit_type = str(getattr(unit, "unit_type", "") or "").strip().lower()
        if role == "toc_entry" or unit_type == "toc_entry":
            count += 1
    return count


def _count_authoritative_topology_operations(projection: object | None, *, op: str) -> int:
    operations = getattr(projection, "operations", None)
    if not operations:
        return 0
    normalized_op = str(op or "").strip().lower()
    count = 0
    for operation in tuple(operations):
        if str(getattr(operation, "op", "") or "").strip().lower() != normalized_op:
            continue
        if not _is_authoritative_topology_signal(
            authority=getattr(operation, "authority", ""),
            confidence=getattr(operation, "confidence", ""),
        ):
            continue
        count += 1
    return count


def has_toc_body_concat_structure(topology_projection: object | None) -> bool:
    projected_units = getattr(topology_projection, "projected_units", None)
    if not projected_units:
        return False
    roles_by_logical_index: dict[int, set[str]] = {}
    for unit in tuple(projected_units):
        if not _is_authoritative_topology_signal(
            authority=getattr(unit, "authority", ""),
            confidence=getattr(unit, "confidence", ""),
        ):
            continue
        role = str(getattr(unit, "role", "") or "").strip().lower()
        unit_type = str(getattr(unit, "unit_type", "") or "").strip().lower()
        normalized_role = ""
        if role == "toc_entry" or unit_type == "toc_entry":
            normalized_role = "toc_entry"
        elif role == "heading" or unit_type in {"chapter_heading", "section_heading"}:
            normalized_role = "heading"
        if not normalized_role:
            continue
        for logical_index in tuple(getattr(unit, "logical_indexes", ()) or ()):
            roles_by_logical_index.setdefault(int(logical_index), set()).add(normalized_role)
    return any({"toc_entry", "heading"}.issubset(roles) for roles in roles_by_logical_index.values())


def _projection_supports_toc_body_concat_gate(
    *,
    document_map: object | None,
    topology_projection: object | None,
) -> bool:
    if _resolve_bounded_toc_region_range(document_map) is None:
        return False
    if not _projection_has_units_or_operations(topology_projection):
        return False
    return bool(
        _count_authoritative_topology_operations(topology_projection, op="split_compound_toc_entries")
        or _count_authoritative_topology_toc_entry_units(topology_projection)
    )


def _derive_toc_body_concat_gate_fields(
    *,
    document_map: object | None,
    topology_projection: object | None,
    markdown_detected: bool,
) -> dict[str, object]:
    split_hint_count = _count_high_confidence_compound_toc_split_hints(document_map)
    split_operation_count = _count_topology_operations(topology_projection, op="split_compound_toc_entries")
    merge_heading_count = _count_topology_operations(topology_projection, op="merge_heading_continuation")
    topology_toc_entry_count = _count_topology_toc_entry_units(topology_projection)
    if not _projection_supports_toc_body_concat_gate(
        document_map=document_map,
        topology_projection=topology_projection,
    ):
        return {
            "toc_body_concat_detected": bool(markdown_detected),
            "toc_body_concat_markdown_detected": bool(markdown_detected),
            "toc_body_concat_structure_detected": False,
            "toc_body_concat_gate_source": "legacy_markdown",
            "topology_split_compound_toc_operation_count": split_operation_count,
            "topology_merge_heading_operation_count": merge_heading_count,
            "document_map_compound_toc_split_hint_count": split_hint_count,
        }
    structure_detected = has_toc_body_concat_structure(topology_projection)
    return {
        "toc_body_concat_detected": structure_detected,
        "toc_body_concat_markdown_detected": bool(markdown_detected),
        "toc_body_concat_structure_detected": structure_detected,
        "toc_body_concat_gate_source": "topology_projection",
        "topology_split_compound_toc_operation_count": split_operation_count,
        "topology_merge_heading_operation_count": merge_heading_count,
        "document_map_compound_toc_split_hint_count": split_hint_count,
    }


def _paragraph_id_for_unit_accounting(paragraph: object, fallback_index: int) -> str:
    paragraph_id = str(getattr(paragraph, "paragraph_id", "") or "").strip()
    if paragraph_id:
        return paragraph_id
    source_index = int(getattr(paragraph, "source_index", fallback_index) or fallback_index)
    return f"p{source_index:04d}"


def _logical_index_for_unit_accounting(paragraph: object, fallback_index: int) -> int:
    logical_index = getattr(paragraph, "logical_index", None)
    if logical_index is not None:
        return int(logical_index)
    source_index = getattr(paragraph, "source_index", fallback_index)
    return int(source_index if source_index is not None else fallback_index)


def _projection_units_for_logical_index(projection: object | None, logical_index: int) -> tuple[object, ...]:
    if projection is None:
        return ()
    get_units = getattr(projection, "get_units", None)
    if callable(get_units):
        try:
            resolved = get_units(int(logical_index))
        except Exception:
            resolved = ()
        return tuple(cast(Sequence[object], resolved or ()))
    return tuple(
        unit
        for unit in tuple(getattr(projection, "projected_units", ()) or ())
        if int(logical_index) in tuple(int(index) for index in tuple(getattr(unit, "logical_indexes", ()) or ()))
    )


def _build_source_paragraph_unit_membership(
    source_paragraphs: Sequence[object],
    topology_projection: object | None,
) -> tuple[dict[str, frozenset[str]], set[str]]:
    paragraph_unit_keys: dict[str, frozenset[str]] = {}
    all_unit_keys: set[str] = set()
    for fallback_index, paragraph in enumerate(source_paragraphs):
        paragraph_id = _paragraph_id_for_unit_accounting(paragraph, fallback_index)
        logical_index = _logical_index_for_unit_accounting(paragraph, fallback_index)
        unit_keys = {
            str(getattr(unit, "unit_id", "") or "").strip()
            for unit in _projection_units_for_logical_index(topology_projection, logical_index)
            if str(getattr(unit, "unit_id", "") or "").strip()
        }
        if not unit_keys:
            unit_keys = {f"paragraph:{paragraph_id}"}
        paragraph_unit_keys[paragraph_id] = frozenset(unit_keys)
        all_unit_keys.update(unit_keys)
    return paragraph_unit_keys, all_unit_keys


def _normalize_registry_text_for_unit_alignment(value: object) -> str:
    text = str(value or "")
    normalized_lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^#{1,6}\s+", "", stripped)
        stripped = re.sub(r"^\(?\d{1,4}[.)]\s+", "", stripped)
        normalized_lines.append(stripped)
    return re.sub(r"\s+", " ", " ".join(normalized_lines)).strip().lower()


def _normalize_registry_preview_for_unit_alignment(value: object, *, limit: int = 120) -> str:
    normalized = _normalize_registry_text_for_unit_alignment(value)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _registry_text_matches_target_preview(target_preview: object, generated_text: object) -> bool:
    normalized_target_preview = _normalize_registry_text_for_unit_alignment(target_preview)
    if not normalized_target_preview:
        return False
    normalized_generated_text = _normalize_registry_text_for_unit_alignment(generated_text)
    if normalized_target_preview == normalized_generated_text:
        return True
    return normalized_target_preview == _normalize_registry_preview_for_unit_alignment(generated_text)


def _build_generated_registry_text_by_paragraph_id(
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> dict[str, str]:
    registry_text_by_paragraph_id: dict[str, str] = {}
    if not generated_paragraph_registry:
        return registry_text_by_paragraph_id
    for entry in generated_paragraph_registry:
        paragraph_id = str(entry.get("paragraph_id") or "").strip()
        text = entry.get("text")
        if paragraph_id and isinstance(text, str) and text.strip():
            registry_text_by_paragraph_id[paragraph_id] = text
    return registry_text_by_paragraph_id


def _generated_paragraph_spans_empty_body_interval_target(
    *,
    generated_text: object,
    previous_target_preview: object,
    unresolved_target_preview: object,
) -> bool:
    normalized_generated_text = _normalize_registry_text_for_unit_alignment(generated_text)
    normalized_previous_target_preview = _normalize_registry_text_for_unit_alignment(previous_target_preview)
    normalized_unresolved_target_preview = _normalize_registry_text_for_unit_alignment(unresolved_target_preview)
    if not normalized_generated_text or not normalized_previous_target_preview or not normalized_unresolved_target_preview:
        return False
    if not normalized_generated_text.startswith(normalized_previous_target_preview):
        return False
    trailing_generated_text = normalized_generated_text[len(normalized_previous_target_preview) :].strip()
    if not trailing_generated_text:
        return False
    return _registry_text_matches_target_preview(normalized_unresolved_target_preview, trailing_generated_text)


def _registry_entry_unit_keys(
    entry: Mapping[str, object],
    paragraph_unit_keys: Mapping[str, frozenset[str]],
) -> frozenset[str]:
    paragraph_ids: list[str] = []
    primary_id = str(entry.get("paragraph_id") or "").strip()
    if primary_id:
        paragraph_ids.append(primary_id)
    merged_ids = entry.get("merged_paragraph_ids")
    if isinstance(merged_ids, Sequence) and not isinstance(merged_ids, (str, bytes, bytearray)):
        paragraph_ids.extend(str(value).strip() for value in merged_ids if str(value).strip())
    unit_keys: set[str] = set()
    for paragraph_id in paragraph_ids:
        unit_keys.update(paragraph_unit_keys.get(paragraph_id, frozenset()))
    return frozenset(unit_keys)


def _registry_entry_relation_ids(entry: Mapping[str, object]) -> tuple[str, ...]:
    raw_relation_ids = entry.get("relation_ids")
    if not isinstance(raw_relation_ids, Sequence) or isinstance(raw_relation_ids, (str, bytes, bytearray)):
        return ()
    relation_ids: list[str] = []
    for value in raw_relation_ids:
        relation_id = str(value).strip()
        if relation_id and relation_id not in relation_ids:
            relation_ids.append(relation_id)
    return tuple(relation_ids)


def _merge_target_alignment_unit_keys(
    alignments: dict[int, frozenset[str]],
    *,
    target_index: int,
    unit_keys: frozenset[str] | set[str],
) -> None:
    if target_index < 0 or not unit_keys:
        return
    merged_keys = set(alignments.get(target_index, frozenset()))
    merged_keys.update(str(value).strip() for value in unit_keys if str(value).strip())
    if merged_keys:
        alignments[target_index] = frozenset(merged_keys)


def _build_target_alignments_from_source_registry(
    formatting_payload: Mapping[str, object],
    *,
    paragraph_unit_keys: Mapping[str, frozenset[str]],
) -> tuple[dict[int, frozenset[str]], dict[int, list[int]], list[Mapping[str, object]]]:
    source_registry = formatting_payload.get("source_registry")
    if not isinstance(source_registry, list):
        return {}, {}, []
    alignments: dict[int, frozenset[str]] = {}
    source_positions_by_target_index: dict[int, list[int]] = {}
    normalized_source_entries: list[Mapping[str, object]] = []
    entry_unit_keys_by_position: list[frozenset[str]] = []
    relation_unit_keys_by_id: dict[str, set[str]] = {}
    for entry in source_registry:
        if not isinstance(entry, Mapping):
            continue
        normalized_entry = cast(Mapping[str, object], entry)
        normalized_source_entries.append(normalized_entry)
        unit_keys = _registry_entry_unit_keys(normalized_entry, paragraph_unit_keys)
        entry_unit_keys_by_position.append(unit_keys)
        for relation_id in _registry_entry_relation_ids(normalized_entry):
            relation_unit_keys_by_id.setdefault(relation_id, set()).update(unit_keys)
    for position, normalized_entry in enumerate(normalized_source_entries):
        unit_keys = set(entry_unit_keys_by_position[position])
        for relation_id in _registry_entry_relation_ids(normalized_entry):
            unit_keys.update(relation_unit_keys_by_id.get(relation_id, set()))
        try:
            raw_target_index = normalized_entry.get("mapped_target_index", -1)
            target_index = int(cast(Any, raw_target_index if raw_target_index is not None else -1))
        except (TypeError, ValueError):
            continue
        if target_index < 0:
            continue
        _merge_target_alignment_unit_keys(alignments, target_index=target_index, unit_keys=unit_keys)
        source_positions_by_target_index.setdefault(target_index, []).append(position)
    return alignments, source_positions_by_target_index, normalized_source_entries


def _infer_target_alignment_unit_keys_from_source_intervals(
    formatting_payload: Mapping[str, object],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
    paragraph_unit_keys: Mapping[str, frozenset[str]],
    alignments: dict[int, frozenset[str]],
    source_positions_by_target_index: Mapping[int, Sequence[int]],
    source_registry_entries: Sequence[Mapping[str, object]],
) -> None:
    target_registry = formatting_payload.get("target_registry")
    if not isinstance(target_registry, list):
        return
    candidate_unmapped_target_indexes = formatting_payload.get("unmapped_target_indexes")
    if not isinstance(candidate_unmapped_target_indexes, list):
        return
    unresolved_target_indexes: list[int] = []
    for value in candidate_unmapped_target_indexes:
        try:
            unresolved_target_indexes.append(int(cast(Any, value)))
        except (TypeError, ValueError):
            continue
    if not unresolved_target_indexes or not source_positions_by_target_index:
        return
    mapped_target_indexes = sorted(source_positions_by_target_index)
    if len(mapped_target_indexes) < 2:
        return
    target_registry_by_index: dict[int, Mapping[str, object]] = {}
    for entry in target_registry:
        if not isinstance(entry, Mapping):
            continue
        try:
            raw_target_index = entry.get("target_index", -1)
            target_index = int(cast(Any, raw_target_index if raw_target_index is not None else -1))
        except (TypeError, ValueError):
            continue
        if target_index >= 0:
            target_registry_by_index[target_index] = cast(Mapping[str, object], entry)
    generated_registry_text_by_paragraph_id = _build_generated_registry_text_by_paragraph_id(generated_paragraph_registry)
    unresolved_target_set = set(unresolved_target_indexes)
    for target_index in unresolved_target_indexes:
        if alignments.get(target_index):
            continue
        previous_target_indexes = [value for value in mapped_target_indexes if value < target_index]
        next_target_indexes = [value for value in mapped_target_indexes if value > target_index]
        if not previous_target_indexes or not next_target_indexes:
            continue
        previous_target_index = previous_target_indexes[-1]
        next_target_index = next_target_indexes[0]
        unresolved_targets_in_interval = [
            value
            for value in unresolved_target_set
            if previous_target_index < value < next_target_index and not alignments.get(value)
        ]
        if not unresolved_targets_in_interval or target_index != unresolved_targets_in_interval[0]:
            continue
        previous_source_position = max(int(value) for value in source_positions_by_target_index.get(previous_target_index, ()))
        next_source_position = min(int(value) for value in source_positions_by_target_index.get(next_target_index, ()))
        if previous_source_position >= next_source_position:
            continue
        interval_unit_keys: set[str] = set()
        for source_entry in source_registry_entries[previous_source_position + 1 : next_source_position]:
            try:
                raw_mapped_target_index = source_entry.get("mapped_target_index", -1)
                mapped_target_index = int(cast(Any, raw_mapped_target_index if raw_mapped_target_index is not None else -1))
            except (TypeError, ValueError):
                mapped_target_index = -1
            if mapped_target_index >= 0:
                continue
            interval_unit_keys.update(_registry_entry_unit_keys(source_entry, paragraph_unit_keys))
        if (
            not interval_unit_keys
            and next_source_position == previous_source_position + 1
            and len(unresolved_targets_in_interval) == 1
            and generated_registry_text_by_paragraph_id
        ):
            previous_source_entry = source_registry_entries[previous_source_position]
            previous_paragraph_id = str(previous_source_entry.get("paragraph_id") or "").strip()
            previous_generated_text = generated_registry_text_by_paragraph_id.get(previous_paragraph_id, "")
            previous_target_entry = target_registry_by_index.get(previous_target_index)
            unresolved_target_entry = target_registry_by_index.get(unresolved_targets_in_interval[0])
            if previous_target_entry is not None and unresolved_target_entry is not None and _generated_paragraph_spans_empty_body_interval_target(
                generated_text=previous_generated_text,
                previous_target_preview=previous_target_entry.get("text_preview"),
                unresolved_target_preview=unresolved_target_entry.get("text_preview"),
            ):
                interval_unit_keys.update(_registry_entry_unit_keys(previous_source_entry, paragraph_unit_keys))
        if not interval_unit_keys:
            continue
        for unresolved_target_index in unresolved_targets_in_interval:
            _merge_target_alignment_unit_keys(
                alignments,
                target_index=unresolved_target_index,
                unit_keys=interval_unit_keys,
            )


def _align_target_indexes_from_generated_registry(
    formatting_payload: Mapping[str, object],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
    paragraph_unit_keys: Mapping[str, frozenset[str]],
    trace_target_indexes: Collection[int] | None = None,
) -> tuple[dict[int, frozenset[str]], dict[int, dict[str, object]]]:
    target_registry = formatting_payload.get("target_registry")
    if not isinstance(target_registry, list) or not generated_paragraph_registry:
        return {}, {}
    generated_entries = [entry for entry in generated_paragraph_registry if isinstance(entry, Mapping)]
    if not generated_entries:
        return {}, {}

    requested_trace_indexes: set[int] = set()
    if trace_target_indexes is not None:
        for value in trace_target_indexes:
            try:
                requested_trace_indexes.add(int(cast(Any, value)))
            except (TypeError, ValueError):
                continue

    alignments: dict[int, frozenset[str]] = {}
    trace_by_target_index: dict[int, dict[str, object]] = {}
    generated_index = 0
    for target_entry in target_registry:
        if not isinstance(target_entry, Mapping):
            continue
        raw_target_index = target_entry.get("target_index", -1)
        target_index = int(cast(Any, raw_target_index if raw_target_index is not None else -1))
        if target_index < 0:
            continue
        target_preview = _normalize_registry_text_for_unit_alignment(target_entry.get("text_preview"))
        trace_entry: dict[str, object] | None = None
        if target_index in requested_trace_indexes:
            trace_entry = {
                "target_index": target_index,
                "target_preview": target_preview,
                "candidate_generated_previews": [],
                "match_result": "no_match",
                "chosen_generated_paragraph_id": None,
                "chosen_generated_preview": None,
                "unit_keys": [],
            }
        search_index = generated_index
        while search_index < len(generated_entries):
            generated_entry = generated_entries[search_index]
            generated_text = generated_entry.get("text")
            generated_preview = _normalize_registry_text_for_unit_alignment(generated_text)
            if not generated_preview:
                search_index += 1
                generated_index = search_index
                continue
            preview_matches = not target_preview or _registry_text_matches_target_preview(target_preview, generated_text)
            if trace_entry is not None:
                candidate_previews = cast(list[dict[str, object]], trace_entry["candidate_generated_previews"])
                candidate_previews.append(
                    {
                        "paragraph_id": str(generated_entry.get("paragraph_id") or "").strip() or None,
                        "generated_preview": generated_preview,
                        "matches_target_preview": preview_matches,
                    }
                )
            if not preview_matches:
                search_index += 1
                continue
            unit_keys = _registry_entry_unit_keys(generated_entry, paragraph_unit_keys)
            _merge_target_alignment_unit_keys(
                alignments,
                target_index=target_index,
                unit_keys=unit_keys,
            )
            if trace_entry is not None:
                trace_entry["match_result"] = "matched"
                trace_entry["chosen_generated_paragraph_id"] = str(generated_entry.get("paragraph_id") or "").strip() or None
                trace_entry["chosen_generated_preview"] = generated_preview
                trace_entry["unit_keys"] = sorted(unit_keys)
            generated_index = search_index + 1
            break
        if trace_entry is not None:
            trace_by_target_index[target_index] = trace_entry
    return alignments, trace_by_target_index


def _collect_target_alignment_preview_trace(
    formatting_payload: Mapping[str, object],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
    paragraph_unit_keys: Mapping[str, frozenset[str]],
    target_indexes: Sequence[int],
) -> list[dict[str, object]]:
    if not target_indexes:
        return []
    requested_indexes: list[int] = []
    for value in target_indexes:
        try:
            requested_indexes.append(int(cast(Any, value)))
        except (TypeError, ValueError):
            continue
    if not requested_indexes:
        return []
    _, trace_by_target_index = _align_target_indexes_from_generated_registry(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
        trace_target_indexes=requested_indexes,
    )
    return [trace_by_target_index[target_index] for target_index in requested_indexes if target_index in trace_by_target_index]


def _align_target_indexes_to_unit_keys(
    formatting_payload: Mapping[str, object],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
    paragraph_unit_keys: Mapping[str, frozenset[str]],
) -> dict[int, frozenset[str]] | None:
    alignments, source_positions_by_target_index, source_registry_entries = _build_target_alignments_from_source_registry(
        formatting_payload,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    target_registry = formatting_payload.get("target_registry")
    if not isinstance(target_registry, list):
        return None
    generated_registry_alignments, _ = _align_target_indexes_from_generated_registry(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    for target_index, unit_keys in generated_registry_alignments.items():
        _merge_target_alignment_unit_keys(
            alignments,
            target_index=target_index,
            unit_keys=unit_keys,
        )
    _infer_target_alignment_unit_keys_from_source_intervals(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
        alignments=alignments,
        source_positions_by_target_index=source_positions_by_target_index,
        source_registry_entries=source_registry_entries,
    )
    return alignments or None


def _truncate_target_alignment_trace_preview(value: object, *, limit: int = 80) -> str | None:
    normalized = _normalize_registry_text_for_unit_alignment(value)
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _serialize_compact_target_alignment_trace_entry(entry: Mapping[str, object]) -> dict[str, object]:
    unit_keys = entry.get("unit_keys")
    normalized_unit_keys = [
        str(value).strip()
        for value in cast(Sequence[object], unit_keys or ())
        if str(value).strip()
    ]
    return {
        "target_index": int(cast(Any, entry.get("target_index", -1))),
        "target_preview": _truncate_target_alignment_trace_preview(entry.get("target_preview")),
        "match_result": str(entry.get("match_result") or "").strip(),
        "chosen_generated_paragraph_id": str(entry.get("chosen_generated_paragraph_id") or "").strip() or None,
        "chosen_generated_preview": _truncate_target_alignment_trace_preview(entry.get("chosen_generated_preview")),
        "unit_keys": sorted(normalized_unit_keys),
    }


def _emit_target_alignment_trace_artifact(
    *,
    source_paragraphs: Sequence[object],
    topology_projection: object | None,
    formatting_payload: Mapping[str, object] | None,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> None:
    if formatting_payload is None or not generated_paragraph_registry:
        return

    raw_unmapped_target_indexes = formatting_payload.get("unmapped_target_indexes")
    if not isinstance(raw_unmapped_target_indexes, list):
        return

    unmapped_target_indexes: list[int] = []
    for value in raw_unmapped_target_indexes:
        try:
            unmapped_target_indexes.append(int(cast(Any, value)))
        except (TypeError, ValueError):
            continue
    if not unmapped_target_indexes:
        return

    paragraph_unit_keys, _ = _build_source_paragraph_unit_membership(source_paragraphs, topology_projection)
    generated_registry_alignments, _ = _align_target_indexes_from_generated_registry(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
        trace_target_indexes=unmapped_target_indexes,
    )
    full_alignments = _align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    ) or {}
    compact_trace = [
        _serialize_compact_target_alignment_trace_entry(entry)
        for entry in _collect_target_alignment_preview_trace(
            formatting_payload,
            generated_paragraph_registry=generated_paragraph_registry,
            paragraph_unit_keys=paragraph_unit_keys,
            target_indexes=unmapped_target_indexes,
        )
    ]
    aligned_target_unit_keys_snapshot = {
        str(target_index): sorted(full_alignments.get(target_index, frozenset())) or None
        for target_index in unmapped_target_indexes
    }
    aligned_via_generated_registry = sum(
        1 for target_index in unmapped_target_indexes if generated_registry_alignments.get(target_index)
    )
    aligned_via_full_inference = sum(1 for target_index in unmapped_target_indexes if full_alignments.get(target_index))

    write_formatting_diagnostics_artifact(
        stage="target_alignment_trace",
        filename_prefix="target_alignment_trace",
        diagnostics={
            "unmapped_target_indexes": unmapped_target_indexes,
            "generated_registry_alignment_trace": compact_trace,
            "aligned_target_unit_keys_snapshot": aligned_target_unit_keys_snapshot,
            "alignment_coverage_summary": {
                "total_unmapped": len(unmapped_target_indexes),
                "aligned_via_generated_registry": aligned_via_generated_registry,
                "aligned_via_interval_inference": aligned_via_full_inference,
                "still_unaligned": max(0, len(unmapped_target_indexes) - aligned_via_full_inference),
            },
        },
    )


def _derive_unit_aware_unmapped_fields(
    *,
    source_paragraphs: Sequence[object],
    topology_projection: object | None,
    formatting_payload: Mapping[str, object] | None,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> dict[str, object]:
    unmapped_source_ids = []
    unmapped_target_indexes = []
    if formatting_payload is not None:
        candidate_source_ids = formatting_payload.get("unmapped_source_ids")
        if isinstance(candidate_source_ids, list):
            unmapped_source_ids = [str(value).strip() for value in candidate_source_ids if str(value).strip()]
        candidate_target_indexes = formatting_payload.get("unmapped_target_indexes")
        if isinstance(candidate_target_indexes, list):
            unresolved_indexes: list[int] = []
            for value in candidate_target_indexes:
                try:
                    unresolved_indexes.append(int(cast(Any, value)))
                except (TypeError, ValueError):
                    continue
            unmapped_target_indexes = unresolved_indexes
    accepted_aggregated_source_ids: set[str] = set()
    accepted_aggregated_target_indexes: set[int] = set()
    if formatting_payload is not None:
        accepted_aggregated_sources = formatting_payload.get("accepted_aggregated_sources")
        if isinstance(accepted_aggregated_sources, list):
            for raw_entry in accepted_aggregated_sources:
                if not isinstance(raw_entry, Mapping):
                    continue
                paragraph_id = str(raw_entry.get("paragraph_id") or "").strip()
                if paragraph_id:
                    accepted_aggregated_source_ids.add(paragraph_id)
                try:
                    target_index = int(cast(Any, raw_entry.get("target_index", -1)))
                except (TypeError, ValueError):
                    continue
                if target_index >= 0:
                    accepted_aggregated_target_indexes.add(target_index)
    legacy_effective_unmapped_source_ids = [
        paragraph_id for paragraph_id in unmapped_source_ids if paragraph_id not in accepted_aggregated_source_ids
    ]
    legacy_effective_unmapped_target_indexes = [
        target_index for target_index in unmapped_target_indexes if target_index not in accepted_aggregated_target_indexes
    ]
    legacy_aggregation_adjusted = (
        len(legacy_effective_unmapped_source_ids) != len(unmapped_source_ids)
        or len(legacy_effective_unmapped_target_indexes) != len(unmapped_target_indexes)
    )
    fields: dict[str, object] = {
        "raw_unmapped_source_paragraph_count": len(unmapped_source_ids),
        "raw_unmapped_target_paragraph_count": len(unmapped_target_indexes),
        "structure_unit_unmapped_source_count": len(legacy_effective_unmapped_source_ids),
        "structure_unit_unmapped_target_count": len(legacy_effective_unmapped_target_indexes),
        "unit_covered_source_fragment_count": 0,
        "unit_covered_target_fragment_count": 0,
        "accepted_aggregated_source_unit_count": len(accepted_aggregated_source_ids),
        "accepted_aggregated_target_index_count": len(accepted_aggregated_target_indexes),
        "unmapped_source_count_basis": "accepted_aggregation_legacy" if legacy_aggregation_adjusted else "legacy_paragraph",
        "unmapped_target_count_basis": "accepted_aggregation_legacy" if legacy_aggregation_adjusted else "legacy_paragraph",
        "unit_unmapped_source_gate_source": "accepted_aggregation_legacy" if legacy_aggregation_adjusted else "legacy_paragraph",
        "unit_unmapped_target_gate_source": "accepted_aggregation_legacy" if legacy_aggregation_adjusted else "legacy_paragraph",
    }
    if formatting_payload is None or not _projection_has_units_or_operations(topology_projection):
        return fields
    paragraph_unit_keys, all_unit_keys = _build_source_paragraph_unit_membership(source_paragraphs, topology_projection)
    if not paragraph_unit_keys:
        return fields
    unmapped_source_unit_keys: set[str] = set()
    for paragraph_id in unmapped_source_ids:
        unmapped_source_unit_keys.update(paragraph_unit_keys.get(paragraph_id, frozenset({f"paragraph:{paragraph_id}"})))
    accepted_aggregated_source_unit_keys: set[str] = set()
    accepted_aggregated_target_unit_keys_by_index: dict[int, set[str]] = {}
    accepted_aggregated_sources = formatting_payload.get("accepted_aggregated_sources")
    if isinstance(accepted_aggregated_sources, list):
        for raw_entry in accepted_aggregated_sources:
            if not isinstance(raw_entry, Mapping):
                continue
            paragraph_id = str(raw_entry.get("paragraph_id") or "").strip()
            if not paragraph_id:
                continue
            unit_keys = set(paragraph_unit_keys.get(paragraph_id, frozenset({f"paragraph:{paragraph_id}"})))
            accepted_aggregated_source_unit_keys.update(unit_keys)
            try:
                target_index = int(cast(Any, raw_entry.get("target_index", -1)))
            except (TypeError, ValueError):
                continue
            if target_index >= 0:
                accepted_aggregated_target_unit_keys_by_index.setdefault(target_index, set()).update(unit_keys)
    aligned_target_unit_keys = _align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    if accepted_aggregated_target_unit_keys_by_index:
        merged_alignments: dict[int, frozenset[str]] = dict(aligned_target_unit_keys or {})
        for target_index, unit_keys in accepted_aggregated_target_unit_keys_by_index.items():
            _merge_target_alignment_unit_keys(merged_alignments, target_index=target_index, unit_keys=unit_keys)
        aligned_target_unit_keys = merged_alignments
    generated_registry_aligned_target_indexes: set[int] = set()
    if generated_paragraph_registry:
        generated_registry_aligned_target_indexes = set(
            _align_target_indexes_from_generated_registry(
                formatting_payload,
                generated_paragraph_registry=generated_paragraph_registry,
                paragraph_unit_keys=paragraph_unit_keys,
            )[0]
        )
    target_registry = formatting_payload.get("target_registry")
    covered_target_unit_keys: set[str] = set()
    if aligned_target_unit_keys is not None and isinstance(target_registry, list):
        for target_entry in target_registry:
            if not isinstance(target_entry, Mapping):
                continue
            if not bool(target_entry.get("mapped")):
                continue
            try:
                raw_target_index = target_entry.get("target_index", -1)
                target_index = int(cast(Any, raw_target_index if raw_target_index is not None else -1))
            except (TypeError, ValueError):
                continue
            if target_index < 0:
                continue
            covered_target_unit_keys.update(aligned_target_unit_keys.get(target_index, frozenset()))
    for unit_keys in accepted_aggregated_target_unit_keys_by_index.values():
        covered_target_unit_keys.update(unit_keys)
    effective_unmapped_source_unit_keys = set(unmapped_source_unit_keys)
    if accepted_aggregated_source_unit_keys:
        effective_unmapped_source_unit_keys.difference_update(accepted_aggregated_source_unit_keys)
    if covered_target_unit_keys:
        effective_unmapped_source_unit_keys.difference_update(covered_target_unit_keys)
    fields.update(
        {
            "structure_unit_total_count": len(all_unit_keys),
            "structure_unit_unmapped_source_count": len(effective_unmapped_source_unit_keys),
            "unit_covered_source_fragment_count": max(0, len(all_unit_keys) - len(effective_unmapped_source_unit_keys)),
            "accepted_aggregated_source_unit_count": len(accepted_aggregated_source_unit_keys),
            "accepted_aggregated_target_index_count": len(accepted_aggregated_target_unit_keys_by_index),
            "unmapped_source_count_basis": "topology_unit",
            "unit_unmapped_source_gate_source": "topology_unit",
        }
    )
    if not unmapped_target_indexes:
        fields.update(
            {
                "structure_unit_unmapped_target_count": 0,
                "unit_covered_target_fragment_count": len(covered_target_unit_keys),
                "unmapped_target_count_basis": "topology_unit",
                "unit_unmapped_target_gate_source": "topology_unit",
            }
        )
        return fields
    if aligned_target_unit_keys is None:
        return fields
    aligned_unmapped_target_indexes = [
        target_index for target_index in unmapped_target_indexes if aligned_target_unit_keys.get(target_index)
    ]
    if not aligned_unmapped_target_indexes:
        return fields
    unmapped_target_unit_keys: set[str] = set()
    preserved_interval_topology_unit_keys: set[str] = set()
    for target_index in aligned_unmapped_target_indexes:
        target_unit_keys = aligned_target_unit_keys.get(target_index, frozenset())
        unmapped_target_unit_keys.update(target_unit_keys)
        if target_index in generated_registry_aligned_target_indexes:
            continue
        if unmapped_source_ids:
            preserved_interval_topology_unit_keys.update(
                key for key in target_unit_keys if isinstance(key, str) and not key.startswith("paragraph:")
            )
    if covered_target_unit_keys:
        unmapped_target_unit_keys.difference_update(covered_target_unit_keys)
        unmapped_target_unit_keys.update(preserved_interval_topology_unit_keys)
    shared_unmapped_unit_keys = effective_unmapped_source_unit_keys & unmapped_target_unit_keys
    if shared_unmapped_unit_keys:
        effective_unmapped_source_unit_keys.difference_update(shared_unmapped_unit_keys)
        unmapped_target_unit_keys.difference_update(shared_unmapped_unit_keys)
        fields.update(
            {
                "structure_unit_unmapped_source_count": len(effective_unmapped_source_unit_keys),
                "unit_covered_source_fragment_count": max(0, len(all_unit_keys) - len(effective_unmapped_source_unit_keys)),
            }
        )
    if len(aligned_unmapped_target_indexes) != len(unmapped_target_indexes):
        return fields
    fields.update(
        {
            "structure_unit_unmapped_source_count": len(effective_unmapped_source_unit_keys),
            "unit_covered_source_fragment_count": max(0, len(all_unit_keys) - len(effective_unmapped_source_unit_keys)),
            "structure_unit_unmapped_target_count": len(unmapped_target_unit_keys),
            "unit_covered_target_fragment_count": len(covered_target_unit_keys | shared_unmapped_unit_keys),
            "unmapped_target_count_basis": "topology_unit",
            "unit_unmapped_target_gate_source": "topology_unit",
        }
    )
    return fields


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
    processed_block_markdowns = cast(Sequence[object], runtime_state.get("processed_block_markdowns") or [])
    raw_structural_markdown = "\n\n".join(
        str(item) for item in processed_block_markdowns if isinstance(item, str) and item.strip()
    )
    raw_markdown = raw_structural_markdown
    if not raw_markdown:
        raw_markdown = latest_markdown
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
    _apply_prepared_snapshot_fields(
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
            "bullet_heading_gate_source": "legacy_markdown",
            "bullet_heading_classification": "markdown_gate",
            "raw_bullet_heading_count": _count_bullet_headings(latest_markdown),
            "toc_body_concat_detected": _has_toc_body_concat_markdown(latest_markdown),
            "toc_body_concat_markdown_detected": _has_toc_body_concat_markdown(latest_markdown),
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
    role_aware_summary = resolve_role_aware_formatting_unmapped_source_summary(canonical_formatting_payloads)
    if role_aware_summary is not None:
        metrics.update(role_aware_summary)
    metrics.update(
        _build_markdown_quality_metrics(
            latest_markdown=latest_markdown,
            raw_markdown=raw_markdown,
            raw_structural_markdown=raw_structural_markdown,
            translation_domain=str(runtime_resolution.effective.translation_domain),
        )
    )
    translation_quality_report, translation_quality_report_path = _load_translation_quality_report(event_log)
    if translation_quality_report is not None:
        _merge_translation_quality_report_metrics(metrics, translation_quality_report)
    metrics["pdf_blank_page_marker_leakage_threshold"] = getattr(document_profile, "max_pdf_blank_page_marker_leakage", None)
    metrics["inline_page_furniture_leakage_threshold"] = getattr(document_profile, "max_inline_page_furniture_leakage", None)
    metrics["adjacent_h1_without_body_threshold"] = getattr(document_profile, "max_adjacent_h1_without_body", None)
    metrics["heading_body_concat_detected_threshold"] = getattr(document_profile, "max_heading_body_concat_detected", None)
    metrics["h1_epigraph_attribution_pattern_threshold"] = getattr(document_profile, "max_h1_epigraph_attribution_pattern", None)
    if translation_quality_report_path:
        metrics["translation_quality_report_path"] = translation_quality_report_path
    generated_paragraph_registry = runtime_state.get("generated_paragraph_registry")
    if not isinstance(generated_paragraph_registry, list):
        generated_paragraph_registry = None
    _apply_prepared_metric_fields(
        metrics,
        prepared,
        source_paragraphs=source_paragraphs,
        formatting_payload=canonical_formatting_diagnostics,
        generated_paragraph_registry=cast(Sequence[Mapping[str, object]] | None, generated_paragraph_registry),
    )
    _emit_target_alignment_trace_artifact(
        source_paragraphs=source_paragraphs,
        topology_projection=getattr(prepared, "document_topology_projection", None),
        formatting_payload=canonical_formatting_diagnostics,
        generated_paragraph_registry=cast(Sequence[Mapping[str, object]] | None, generated_paragraph_registry),
    )
    _apply_metric_snapshot_fields(preparation_diagnostic_snapshot, metrics)
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
    layout_signals_context = dict(_extract_event_context(event_log, "document_topology_layout_signals_built"))
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
        "document_topology_layout_signals": None if not layout_signals_context else layout_signals_context,
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
        "structure_window_split_count": _extract_event_context_int(
            event_log,
            "structure_processing_outcome",
            "structure_window_split_count",
        ),
        "structure_max_fallback_depth": _extract_event_context_int(
            event_log,
            "structure_processing_outcome",
            "structure_max_fallback_depth",
        ),
        "structure_split_fallback_descriptor_count": _extract_event_context_int(
            event_log,
            "structure_processing_outcome",
            "structure_split_fallback_descriptor_count",
        ),
        "structure_timeout_retry_count": _extract_event_context_int(
            event_log,
            "structure_processing_outcome",
            "structure_timeout_retry_count",
        ),
        "structure_timeout_retry_succeeded_count": _extract_event_context_int(
            event_log,
            "structure_processing_outcome",
            "structure_timeout_retry_succeeded_count",
        ),
        "structure_timeout_retry_failed_count": _extract_event_context_int(
            event_log,
            "structure_processing_outcome",
            "structure_timeout_retry_failed_count",
        ),
        "structure_split_fallback_capped_descriptor_count": _extract_event_context_int(
            event_log,
            "structure_processing_outcome",
            "structure_split_fallback_capped_descriptor_count",
        ),
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
    parser.add_argument("document_profile_id", help="Validation document profile id, for example lietaer-pdf-first-20-structure-core.")
    parser.add_argument("--run-profile-id", dest="run_profile_id", help="Optional run profile override.")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_cli_args(argv)
    registry = load_validation_registry()
    document_profile = registry.get_document_profile(str(args.document_profile_id))
    run_profile_id = str(args.run_profile_id or getattr(document_profile, "structural_run_profile", "") or "").strip()
    run_profile = registry.get_run_profile(run_profile_id) if run_profile_id else registry.get_run_profile("ui-parity-translate-benchmark-advisory")
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
