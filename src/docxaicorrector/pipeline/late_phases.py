import logging
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

from docxaicorrector.core.models import ImageMode
from docxaicorrector.pipeline.output_validation import (
    assemble_final_markdown,
    build_generated_paragraph_registry_from_entries,
    collect_bullet_heading_samples,
    collect_recovered_heading_entries,
    collect_false_fragment_heading_samples,
    collect_false_fragment_heading_samples_from_entries,
    collect_list_fragment_regression_samples,
    collect_mixed_script_samples,
    collect_residual_bullet_glyph_samples,
    collect_theology_style_issue_samples,
    has_toc_body_concat_markdown,
    normalize_false_fragment_headings_markdown,
    normalize_list_fragment_regressions_markdown,
    normalize_mixed_script_markdown,
    normalize_page_placeholder_heading_concats_markdown,
    normalize_residual_bullet_glyphs_markdown,
)
from docxaicorrector.generation.formatting_diagnostics_retention import (
    collect_recent_formatting_diagnostics,
    load_formatting_diagnostics_payloads,
)
from docxaicorrector.generation._generation import strip_markdown_for_narration
from docxaicorrector.pipeline.reassembly import (
    assemble_hybrid_document,
    build_reassembly_plan,
    build_reassembly_result_manifest,
    build_segment_result_records,
    load_segment_result_records,
)
from docxaicorrector.processing.preparation import humanize_quality_gate_reasons


PipelineResult = Literal["succeeded", "failed", "stopped"]
_ELEVENLABS_TAG_PATTERN = re.compile(r"\[(?:thoughtful|curious|serious|sad|excited|annoyed|sarcastic|whispers|short pause|long pause|sighs|laughs|chuckles|exhales)\]")
_NARRATION_ANY_TAG_PATTERN = re.compile(r"\[[^\]\n]{1,40}\]")
_NARRATION_DISALLOWED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("internal_placeholder", re.compile(r"\[\[DOCX_[A-Za-z0-9_]+\]\]")),
    ("raw_url", re.compile(r"(?:https?://\S+|www\.\S+)", re.IGNORECASE)),
    ("doi", re.compile(r"\bdoi\s*[:/]?\s*10\.\d{4,9}/\S+", re.IGNORECASE)),
    ("isbn", re.compile(r"\bisbn\b", re.IGNORECASE)),
    ("arxiv", re.compile(r"\barxiv\b", re.IGNORECASE)),
    ("inline_citation", re.compile(r"\((?:ibid\.|там же|[A-ZА-ЯЁ][^()]{0,80}?,\s*(?:19|20)\d{2})[^()]*\)", re.IGNORECASE)),
    ("superscript_footnote", re.compile(r"[\u00B9\u00B2\u00B3\u2070-\u2079]")),
    ("markdown_heading", re.compile(r"^\s{0,3}#", re.MULTILINE)),
)
QUALITY_REPORTS_DIR = Path(".run") / "quality_reports"
QUALITY_REPORTS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
QUALITY_REPORTS_MAX_COUNT = 100
_BULLET_MARKDOWN_HEADING_PATTERN = re.compile(r"(?m)^\s{0,3}#{1,6}\s*[\u2022\u25cf\u25e6\u2023*\-]\s*$")


def _format_translation_quality_gate_failure_message(gate_reasons: Sequence[str]) -> str:
    reasons = humanize_quality_gate_reasons(gate_reasons)
    base = "Итоговый перевод не прошёл document-level quality gate."
    if not reasons:
        return f"{base} (translation_quality_gate_failed)"
    return f"{base} (translation_quality_gate_failed) Причины: {', '.join(reasons)}."


def _normalize_final_markdown_for_quality_gate(text: str) -> str:
    normalized = normalize_page_placeholder_heading_concats_markdown(text)
    normalized = normalize_residual_bullet_glyphs_markdown(normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if "\n" not in normalized and "\n\n" in text:
        return text
    return normalized


def _normalize_final_markdown_for_runtime_display(text: str) -> str:
    normalized = normalize_page_placeholder_heading_concats_markdown(text)
    normalized = normalize_false_fragment_headings_markdown(normalized)
    normalized = normalize_residual_bullet_glyphs_markdown(normalized)
    normalized = normalize_list_fragment_regressions_markdown(normalized)
    normalized = normalize_mixed_script_markdown(normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if "\n" not in normalized and "\n\n" in text:
        return text
    return normalized


def _serialize_assembly_decisions(decisions: Sequence[object], *, limit: int = 20) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for decision in decisions[:limit]:
        action = getattr(decision, "action", None)
        block_index = getattr(decision, "block_index", None)
        paragraph_ids = getattr(decision, "paragraph_ids", ())
        reason = getattr(decision, "reason", None)
        serialized.append(
            {
                "action": action,
                "block_index": block_index,
                "paragraph_ids": list(paragraph_ids) if isinstance(paragraph_ids, tuple) else list(paragraph_ids or []),
                "reason": reason,
            }
        )
    return serialized


def _log_boundary_recovery_diagnostics(*, dependencies: Any, context: Any, assembly_result: Any) -> None:
    diagnostics = getattr(assembly_result, "diagnostics", None)
    if diagnostics is None:
        return
    dependencies.log_event(
        logging.INFO,
        "boundary_recovery_diagnostics",
        "Собраны diagnostics registry-aware paragraph boundary recovery.",
        filename=context.uploaded_filename,
        accepted_merges=getattr(diagnostics, "accepted_merges", 0),
        denied_merges=getattr(diagnostics, "denied_merges", 0),
        protected_boundary_denials=getattr(diagnostics, "protected_boundary_denials", 0),
        demoted_false_headings=getattr(diagnostics, "demoted_false_headings", 0),
        registry_covered_paragraphs=getattr(diagnostics, "registry_covered_paragraphs", 0),
        fallback_paragraphs=getattr(diagnostics, "fallback_paragraphs", 0),
        paragraph_count_drift=getattr(diagnostics, "paragraph_count_drift", 0),
        inconsistent_registry_blocks=list(getattr(diagnostics, "inconsistent_registry_blocks", ()) or ()),
        merge_decisions=_serialize_assembly_decisions(getattr(diagnostics, "merge_decisions", ()) or ()),
    )


def _require_group_int(group: Mapping[str, object], key: str) -> int:
    value = group[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Narration postprocess group field '{key}' must be int, got {type(value).__name__}")
    return value


def collect_recent_formatting_diagnostics_artifacts(*, since_epoch_seconds: float, diagnostics_dir: Path) -> list[str]:
    return collect_recent_formatting_diagnostics(
        since_epoch_seconds=since_epoch_seconds,
        diagnostics_dir=diagnostics_dir,
    )


def _load_formatting_diagnostics_payloads(artifact_paths: Sequence[str]) -> list[dict[str, object]]:
    return load_formatting_diagnostics_payloads(artifact_paths)


def _formatting_diagnostics_requires_user_warning(payload: Mapping[str, object]) -> bool:
    caption_heading_conflicts = payload.get("caption_heading_conflicts")
    if isinstance(caption_heading_conflicts, list) and caption_heading_conflicts:
        return True

    source_count = payload.get("source_count")
    mapped_count = payload.get("mapped_count")
    if isinstance(source_count, int) and isinstance(mapped_count, int):
        if source_count >= 8 and mapped_count == 0:
            return True

    return False


def _build_formatting_diagnostics_user_message(payload: Mapping[str, object], *, warn_user: bool) -> str:
    source_count = payload.get("source_count")
    mapped_count = payload.get("mapped_count")
    unmapped_source_ids = payload.get("unmapped_source_ids")
    unmapped_source_count = len(unmapped_source_ids) if isinstance(unmapped_source_ids, list) else None
    caption_heading_conflicts = payload.get("caption_heading_conflicts")
    caption_conflict_count = len(caption_heading_conflicts) if isinstance(caption_heading_conflicts, list) else 0

    coverage_summary = None
    if isinstance(mapped_count, int) and isinstance(source_count, int) and source_count > 0:
        coverage_summary = f"Совпадение найдено для {mapped_count} из {source_count} исходных абзацев"
        if unmapped_source_count:
            coverage_summary += f"; без точного соответствия осталось {unmapped_source_count}"

    if warn_user:
        message = (
            "DOCX собран, но найдены спорные места форматирования, которые стоит проверить вручную. "
            "Обычно это означает, что часть подписей, заголовков или абзацной структуры перестроилась при генерации."
        )
        if coverage_summary:
            message += f" {coverage_summary}."
        if caption_conflict_count:
            message += f" Конфликтов подписи/заголовка: {caption_conflict_count}."
        return message

    message = (
        "DOCX собран. Дополнительное восстановление форматирования было частично пропущено, "
        "потому что точное сопоставление абзацев нашлось не везде. Это нормально, когда модель объединяет, делит или переформулирует абзацы."
    )
    if coverage_summary:
        message += f" {coverage_summary}."
    return message


def build_formatting_diagnostics_user_feedback(artifact_paths: Sequence[str]) -> tuple[str, str, str]:
    payloads = _load_formatting_diagnostics_payloads(artifact_paths)
    if not payloads:
        return (
            "INFO",
            "Сборка DOCX завершена; сохранена служебная диагностика форматирования.",
            "DOCX собран; сохранена служебная диагностика форматирования.",
        )

    warning_payloads = [payload for payload in payloads if _formatting_diagnostics_requires_user_warning(payload)]
    if warning_payloads:
        return (
            "WARN",
            "Сборка DOCX завершена; найдены места, где форматирование стоит проверить вручную.",
            _build_formatting_diagnostics_user_message(warning_payloads[0], warn_user=True),
        )

    return (
        "INFO",
        "Сборка DOCX завершена; сохранена служебная диагностика форматирования.",
        _build_formatting_diagnostics_user_message(payloads[0], warn_user=False),
    )


def _prune_quality_reports(*, target_dir: Path, now_epoch_seconds: float | None = None) -> None:
    if not target_dir.exists():
        return
    reference_now = time.time() if now_epoch_seconds is None else now_epoch_seconds
    retained: list[tuple[float, Path]] = []
    for artifact_path in target_dir.glob("*.json"):
        try:
            mtime = artifact_path.stat().st_mtime
        except OSError:
            continue
        if max(0.0, reference_now - mtime) > QUALITY_REPORTS_MAX_AGE_SECONDS:
            try:
                artifact_path.unlink()
            except OSError:
                pass
            continue
        retained.append((mtime, artifact_path))
    if len(retained) <= QUALITY_REPORTS_MAX_COUNT:
        return
    retained.sort(key=lambda item: (item[0], item[1].name))
    for _, artifact_path in retained[: len(retained) - QUALITY_REPORTS_MAX_COUNT]:
        try:
            artifact_path.unlink()
        except OSError:
            continue


def _write_quality_report_artifact(*, source_name: str, payload: Mapping[str, object]) -> str | None:
    try:
        QUALITY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source_name or "document").strip("_") or "document"
        generated_at_epoch_ms = int(time.time() * 1000)
        artifact_path = QUALITY_REPORTS_DIR / f"{safe_name}_{generated_at_epoch_ms}.json"
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _prune_quality_reports(target_dir=QUALITY_REPORTS_DIR)
        return str(artifact_path)
    except Exception:
        return None


def _resolve_translation_quality_gate_policy(*, context: Any) -> str:
    configured = str(context.app_config.get("translation_output_quality_gate_policy", "")).strip().lower()
    if configured in {"strict", "advisory"}:
        return configured
    if context.processing_operation == "translate":
        return "strict"
    return "advisory"


def _count_bullet_markdown_headings(markdown_text: str) -> int:
    return len(_BULLET_MARKDOWN_HEADING_PATTERN.findall(markdown_text or ""))


def _has_toc_body_concat_markdown(markdown_text: str) -> bool:
    return has_toc_body_concat_markdown(markdown_text)


def _apply_quality_gate_reason(
    *,
    quality_status: str,
    gate_reasons: list[str],
    policy: str,
    reason: str,
) -> str:
    if policy == "strict":
        quality_status = "fail"
    elif quality_status != "fail":
        quality_status = "warn"
    gate_reasons.append(reason)
    return quality_status


def _serialize_quality_samples(samples: Sequence[object], *, limit: int = 8) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for sample in list(samples)[:limit]:
        line = getattr(sample, "line", None)
        text = getattr(sample, "text", None)
        reason = getattr(sample, "reason", None)
        serialized.append(
            {
                "line": line,
                "text": text,
                "reason": reason,
            }
        )
    return serialized


def _serialize_recovered_heading_entries(entries: Sequence[object], *, limit: int = 12) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for entry in list(entries)[:limit]:
        serialized.append(
            {
                "paragraph_id": getattr(entry, "paragraph_id", None),
                "source_index": getattr(entry, "source_index", None),
                "role": getattr(entry, "role", None),
                "structural_role": getattr(entry, "structural_role", None),
                "generated_heading_kind": getattr(entry, "generated_heading_kind", None),
                "text": getattr(entry, "text", None),
            }
        )
    return serialized


def _has_source_backed_entry_authority(assembly_entries: Sequence[object]) -> bool:
    return any(
        bool(getattr(entry, "from_registry", False)) and not bool(getattr(entry, "used_fallback", False))
        for entry in assembly_entries
    )


def _resolve_false_fragment_heading_gate_samples(
    *,
    raw_samples: Sequence[object],
    entry_samples: Sequence[object],
    source_backed_entry_authority: bool,
) -> tuple[list[object], str]:
    if source_backed_entry_authority:
        return list(entry_samples), "entry_assembly"
    return list(raw_samples), "legacy_markdown"


def _resolve_list_fragment_regression_gate_samples(
    *,
    raw_samples: Sequence[object],
    source_backed_entry_authority: bool,
    topology_projection_supported: bool,
) -> tuple[list[object], str]:
    if source_backed_entry_authority and topology_projection_supported:
        return [], "topology_projection"
    return list(raw_samples), "legacy_markdown"


def _build_translation_quality_report(
    *,
    context: Any,
    final_markdown: str,
    formatting_diagnostics_artifacts: Sequence[str],
    assembly_result: Any | None = None,
) -> dict[str, object]:
    normalized_quality_markdown = _normalize_final_markdown_for_quality_gate(final_markdown)
    payloads = _load_formatting_diagnostics_payloads(formatting_diagnostics_artifacts)
    latest_payload = payloads[-1] if payloads else {}
    unmapped_source_ids = latest_payload.get("unmapped_source_ids") if isinstance(latest_payload, Mapping) else []
    unmapped_target_indexes = latest_payload.get("unmapped_target_indexes") if isinstance(latest_payload, Mapping) else []
    accepted_merged_sources = latest_payload.get("accepted_merged_sources") if isinstance(latest_payload, Mapping) else []
    caption_heading_conflicts = latest_payload.get("caption_heading_conflicts") if isinstance(latest_payload, Mapping) else []
    policy = _resolve_translation_quality_gate_policy(context=context)
    quality_status = "pass"
    gate_reasons: list[str] = []
    bullet_heading_samples = collect_bullet_heading_samples(normalized_quality_markdown)
    bullet_heading_count = len(bullet_heading_samples)
    assembly_entries = tuple(getattr(assembly_result, "entries", ()) or ())
    assembly_uses_fallback = any(bool(getattr(entry, "used_fallback", False)) for entry in assembly_entries)
    source_backed_entry_authority = _has_source_backed_entry_authority(assembly_entries) and not assembly_uses_fallback
    entry_false_fragment_heading_samples = collect_false_fragment_heading_samples_from_entries(assembly_entries) if assembly_entries else []
    raw_false_fragment_heading_samples = collect_false_fragment_heading_samples(final_markdown)
    residual_bullet_glyph_samples = collect_residual_bullet_glyph_samples(final_markdown)
    raw_list_fragment_regression_samples = collect_list_fragment_regression_samples(final_markdown)
    mixed_script_samples = collect_mixed_script_samples(final_markdown)
    recovered_heading_entries = collect_recovered_heading_entries(assembly_entries) if assembly_entries and not assembly_uses_fallback else []
    translation_domain = str(getattr(context, "translation_domain", "") or context.app_config.get("translation_domain", "general") or "general")
    theology_style_samples = (
        collect_theology_style_issue_samples(normalized_quality_markdown)
        if translation_domain.strip().lower() == "theology"
        else []
    )
    authority_fields = _derive_translation_quality_authority_fields(
        context=context,
        final_markdown=final_markdown,
        formatting_payload=latest_payload if isinstance(latest_payload, Mapping) else None,
        assembly_result=assembly_result,
    )
    false_fragment_heading_samples, false_fragment_heading_gate_source = _resolve_false_fragment_heading_gate_samples(
        raw_samples=raw_false_fragment_heading_samples,
        entry_samples=entry_false_fragment_heading_samples,
        source_backed_entry_authority=source_backed_entry_authority,
    )
    list_fragment_regression_samples, list_fragment_regression_gate_source = _resolve_list_fragment_regression_gate_samples(
        raw_samples=raw_list_fragment_regression_samples,
        source_backed_entry_authority=source_backed_entry_authority,
        topology_projection_supported=bool(authority_fields.get("topology_projection_supported", False)),
    )
    suspicious_heading_repetition_samples = [
        sample for sample in false_fragment_heading_samples if getattr(sample, "reason", "") == "suspicious_heading_repetition_present"
    ]
    scripture_reference_heading_samples = [
        sample for sample in false_fragment_heading_samples if getattr(sample, "reason", "") == "scripture_reference_heading_present"
    ]
    toc_body_concat_detected = bool(authority_fields.get("toc_body_concat_detected", False))
    source_paragraph_count = latest_payload.get("source_count") if isinstance(latest_payload, Mapping) else None
    output_paragraph_count = latest_payload.get("target_count") if isinstance(latest_payload, Mapping) else None
    worst_unmapped_source_count = _effective_authoritative_unmapped_count(
        authority_fields,
        basis_key="unmapped_source_count_basis",
        raw_count_key="raw_unmapped_source_paragraph_count",
        structure_count_key="structure_unit_unmapped_source_count",
    )
    effective_unmapped_target_count = _effective_authoritative_unmapped_count(
        authority_fields,
        basis_key="unmapped_target_count_basis",
        raw_count_key="raw_unmapped_target_paragraph_count",
        structure_count_key="structure_unit_unmapped_target_count",
    )
    prepared_paragraph_count = getattr(context, "paragraph_count", None) or getattr(context, "total_paragraphs", None)
    if isinstance(prepared_paragraph_count, int) and prepared_paragraph_count > 0:
        if source_paragraph_count is None:
            source_paragraph_count = prepared_paragraph_count
        if output_paragraph_count is None:
            output_paragraph_count = prepared_paragraph_count
    if context.processing_operation == "translate":
        basis = str(authority_fields.get("unmapped_source_count_basis") or "legacy_paragraph").strip().lower() or "legacy_paragraph"
        effective_source_total = source_paragraph_count
        if basis == "topology_unit":
            structure_unit_total_count = authority_fields.get("structure_unit_total_count")
            if isinstance(structure_unit_total_count, int) and structure_unit_total_count > 0:
                effective_source_total = structure_unit_total_count
        if policy == "strict" and worst_unmapped_source_count > 0:
            quality_status = "fail"
            gate_reasons.append("unmapped_source_paragraphs_present")
        elif policy == "advisory" and worst_unmapped_source_count > 0:
            if isinstance(effective_source_total, int) and effective_source_total > 0 and (worst_unmapped_source_count / effective_source_total) > 0.01:
                quality_status = "warn"
                gate_reasons.append("unmapped_source_paragraphs_above_advisory_threshold")
        if bullet_heading_count > 0:
            quality_status = _apply_quality_gate_reason(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                policy=policy,
                reason="bullet_marker_headings_present",
            )
        if toc_body_concat_detected:
            quality_status = _apply_quality_gate_reason(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                policy=policy,
                reason="toc_body_concatenation_detected",
            )
        if false_fragment_heading_samples:
            quality_status = _apply_quality_gate_reason(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                policy=policy,
                reason="false_fragment_headings_present",
            )
        if residual_bullet_glyph_samples:
            quality_status = _apply_quality_gate_reason(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                policy=policy,
                reason="residual_bullet_glyphs_present",
            )
        if list_fragment_regression_samples:
            quality_status = _apply_quality_gate_reason(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                policy=policy,
                reason="list_fragment_regressions_present",
            )
        if mixed_script_samples:
            quality_status = _apply_quality_gate_reason(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                policy=policy,
                reason="mixed_script_terms_present",
            )
        if theology_style_samples:
            quality_status = "warn" if quality_status == "pass" else quality_status

    report = {
        "version": 2,
        "source_name": context.uploaded_filename,
        "processing_operation": context.processing_operation,
        "quality_gate_policy": policy,
        "translation_domain": translation_domain,
        "source_paragraph_count": source_paragraph_count,
        "target_paragraph_count": output_paragraph_count,
        "output_paragraph_count": output_paragraph_count,
        "mapped_count": latest_payload.get("mapped_count") if isinstance(latest_payload, Mapping) else None,
        "unmapped_source_count": worst_unmapped_source_count,
        "unmapped_target_count": effective_unmapped_target_count,
        "worst_unmapped_source_count": worst_unmapped_source_count,
        "raw_unmapped_source_paragraph_count": authority_fields.get("raw_unmapped_source_paragraph_count", len(unmapped_source_ids) if isinstance(unmapped_source_ids, list) else 0),
        "raw_unmapped_target_paragraph_count": authority_fields.get("raw_unmapped_target_paragraph_count", len(unmapped_target_indexes) if isinstance(unmapped_target_indexes, list) else 0),
        "structure_unit_total_count": authority_fields.get("structure_unit_total_count"),
        "structure_unit_unmapped_source_count": authority_fields.get("structure_unit_unmapped_source_count"),
        "structure_unit_unmapped_target_count": authority_fields.get("structure_unit_unmapped_target_count"),
        "unmapped_source_count_basis": authority_fields.get("unmapped_source_count_basis", "legacy_paragraph"),
        "unmapped_target_count_basis": authority_fields.get("unmapped_target_count_basis", "legacy_paragraph"),
        "unit_unmapped_source_gate_source": authority_fields.get(
            "unit_unmapped_source_gate_source",
            authority_fields.get("unmapped_source_count_basis", "legacy_paragraph"),
        ),
        "unit_unmapped_target_gate_source": authority_fields.get(
            "unit_unmapped_target_gate_source",
            authority_fields.get("unmapped_target_count_basis", "legacy_paragraph"),
        ),
        "document_map_toc_detected": authority_fields.get("document_map_toc_detected", False),
        "document_map_toc_region_count": authority_fields.get("document_map_toc_region_count", 0),
        "topology_toc_entry_count": authority_fields.get("topology_toc_entry_count", 0),
        "topology_split_compound_toc_operation_count": authority_fields.get(
            "topology_split_compound_toc_operation_count",
            0,
        ),
        "topology_merge_heading_operation_count": authority_fields.get("topology_merge_heading_operation_count", 0),
        "document_map_compound_toc_split_hint_count": authority_fields.get(
            "document_map_compound_toc_split_hint_count",
            0,
        ),
        "accepted_merged_sources_count": len(accepted_merged_sources) if isinstance(accepted_merged_sources, list) else 0,
        "caption_heading_conflicts_count": len(caption_heading_conflicts) if isinstance(caption_heading_conflicts, list) else 0,
        "bullet_heading_count": bullet_heading_count,
        "bullet_heading_samples": _serialize_quality_samples(bullet_heading_samples),
        "false_fragment_heading_count": len(false_fragment_heading_samples),
        "false_fragment_heading_samples": _serialize_quality_samples(false_fragment_heading_samples),
        "false_fragment_heading_gate_source": false_fragment_heading_gate_source,
        "raw_false_fragment_heading_count": len(raw_false_fragment_heading_samples),
        "raw_false_fragment_heading_samples": _serialize_quality_samples(raw_false_fragment_heading_samples),
        "suspicious_heading_repetition_count": len(suspicious_heading_repetition_samples),
        "suspicious_heading_repetition_samples": _serialize_quality_samples(suspicious_heading_repetition_samples),
        "scripture_reference_heading_count": len(scripture_reference_heading_samples),
        "scripture_reference_heading_samples": _serialize_quality_samples(scripture_reference_heading_samples),
        "residual_bullet_glyph_count": len(residual_bullet_glyph_samples),
        "residual_bullet_glyph_samples": _serialize_quality_samples(residual_bullet_glyph_samples),
        "list_fragment_regression_count": len(list_fragment_regression_samples),
        "list_fragment_regression_samples": _serialize_quality_samples(list_fragment_regression_samples),
        "list_fragment_regression_gate_source": list_fragment_regression_gate_source,
        "raw_list_fragment_regression_count": len(raw_list_fragment_regression_samples),
        "raw_list_fragment_regression_samples": _serialize_quality_samples(raw_list_fragment_regression_samples),
        "mixed_script_term_count": len(mixed_script_samples),
        "mixed_script_term_samples": _serialize_quality_samples(mixed_script_samples),
        "theology_style_deterministic_issue_count": len(theology_style_samples),
        "theology_style_deterministic_issue_samples": _serialize_quality_samples(theology_style_samples),
        "toc_body_concat_detected": toc_body_concat_detected,
        "toc_body_concat_markdown_detected": authority_fields.get("toc_body_concat_markdown_detected", False),
        "toc_body_concat_structure_detected": authority_fields.get("toc_body_concat_structure_detected", False),
        "toc_body_concat_gate_source": authority_fields.get("toc_body_concat_gate_source", "legacy_markdown"),
        "formatting_diagnostics_artifact_count": len(formatting_diagnostics_artifacts),
        "final_markdown_chars": len(normalized_quality_markdown),
        "quality_status": quality_status,
        "gate_reasons": gate_reasons,
        "formatting_diagnostics_artifact_paths": list(formatting_diagnostics_artifacts),
        "boundary_recovery": {
            "accepted_merges": getattr(getattr(assembly_result, "diagnostics", None), "accepted_merges", 0),
            "denied_merges": getattr(getattr(assembly_result, "diagnostics", None), "denied_merges", 0),
            "protected_boundary_denials": getattr(getattr(assembly_result, "diagnostics", None), "protected_boundary_denials", 0),
            "demoted_false_headings": getattr(getattr(assembly_result, "diagnostics", None), "demoted_false_headings", 0),
            "registry_covered_paragraphs": getattr(getattr(assembly_result, "diagnostics", None), "registry_covered_paragraphs", 0),
            "fallback_paragraphs": getattr(getattr(assembly_result, "diagnostics", None), "fallback_paragraphs", 0),
            "paragraph_count_drift": getattr(getattr(assembly_result, "diagnostics", None), "paragraph_count_drift", 0),
            "inconsistent_registry_blocks": list(getattr(getattr(assembly_result, "diagnostics", None), "inconsistent_registry_blocks", ()) or ()),
            "merge_decisions": _serialize_assembly_decisions(getattr(getattr(assembly_result, "diagnostics", None), "merge_decisions", ()) or ()),
            "recovered_heading_entries": _serialize_recovered_heading_entries(recovered_heading_entries),
        },
    }
    return report


def _derive_translation_quality_authority_fields(
    *,
    context: Any,
    final_markdown: str,
    formatting_payload: Mapping[str, object] | None,
    assembly_result: Any | None,
) -> dict[str, object]:
    markdown_detected = _has_toc_body_concat_markdown(final_markdown)
    raw_unmapped_source_count = 0
    raw_unmapped_target_count = 0
    if formatting_payload is not None:
        candidate_source_ids = formatting_payload.get("unmapped_source_ids")
        if isinstance(candidate_source_ids, list):
            raw_unmapped_source_count = len(candidate_source_ids)
        candidate_target_indexes = formatting_payload.get("unmapped_target_indexes")
        if isinstance(candidate_target_indexes, list):
            raw_unmapped_target_count = len(candidate_target_indexes)
    fields: dict[str, object] = {
        "toc_body_concat_detected": markdown_detected,
        "toc_body_concat_markdown_detected": markdown_detected,
        "toc_body_concat_structure_detected": False,
        "toc_body_concat_gate_source": "legacy_markdown",
        "topology_projection_supported": False,
        "document_map_toc_detected": False,
        "document_map_toc_region_count": 0,
        "topology_toc_entry_count": 0,
        "topology_split_compound_toc_operation_count": 0,
        "topology_merge_heading_operation_count": 0,
        "document_map_compound_toc_split_hint_count": 0,
        "raw_unmapped_source_paragraph_count": raw_unmapped_source_count,
        "raw_unmapped_target_paragraph_count": raw_unmapped_target_count,
        "structure_unit_unmapped_source_count": raw_unmapped_source_count,
        "structure_unit_unmapped_target_count": raw_unmapped_target_count,
        "unmapped_source_count_basis": "legacy_paragraph",
        "unmapped_target_count_basis": "legacy_paragraph",
        "unit_unmapped_source_gate_source": "legacy_paragraph",
        "unit_unmapped_target_gate_source": "legacy_paragraph",
    }
    document_map = getattr(context, "document_map", None)
    topology_projection = getattr(context, "document_topology_projection", None)
    source_paragraphs = cast(Sequence[object], getattr(context, "source_paragraphs", None) or ())
    if formatting_payload is None and document_map is None and topology_projection is None:
        return fields
    try:
        from docxaicorrector.validation import structural as structural_validation_runtime
    except Exception:
        return fields
    fields.update(
        {
            key: value
            for key, value in structural_validation_runtime._derive_toc_body_concat_gate_fields(
                document_map=document_map,
                topology_projection=topology_projection,
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
    fields["document_map_toc_detected"] = bool(
        structural_validation_runtime._has_high_confidence_bounded_document_map_toc_region(document_map)
        or structural_validation_runtime._count_document_map_anchor_roles(document_map, role="toc_header")
        or structural_validation_runtime._count_document_map_anchor_roles(document_map, role="toc_entry")
    )
    fields["topology_projection_supported"] = bool(
        structural_validation_runtime._projection_has_units_or_operations(topology_projection)
    )
    fields["document_map_toc_region_count"] = (
        1 if structural_validation_runtime._has_high_confidence_bounded_document_map_toc_region(document_map) else 0
    )
    fields["topology_toc_entry_count"] = structural_validation_runtime._count_topology_toc_entry_units(topology_projection)
    generated_paragraph_registry = None
    if assembly_result is not None:
        assembly_entries = tuple(getattr(assembly_result, "entries", ()) or ())
        if assembly_entries:
            generated_paragraph_registry = build_generated_paragraph_registry_from_entries(assembly_entries)
    unmapped_fields = structural_validation_runtime._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=topology_projection,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
    )
    fields.update(
        {
            key: value
            for key, value in unmapped_fields.items()
            if key
            in {
                "raw_unmapped_source_paragraph_count",
                "raw_unmapped_target_paragraph_count",
                "structure_unit_total_count",
                "structure_unit_unmapped_source_count",
                "structure_unit_unmapped_target_count",
                "unmapped_source_count_basis",
                "unmapped_target_count_basis",
                "unit_unmapped_source_gate_source",
                "unit_unmapped_target_gate_source",
            }
        }
    )
    return fields


def _effective_authoritative_unmapped_count(
    fields: Mapping[str, object],
    *,
    basis_key: str,
    raw_count_key: str,
    structure_count_key: str,
) -> int:
    basis = str(fields.get(basis_key) or "legacy_paragraph").strip().lower() or "legacy_paragraph"
    candidate = fields.get(structure_count_key) if basis == "topology_unit" else fields.get(raw_count_key)
    return int(candidate or 0) if isinstance(candidate, (int, float, bool)) else 0


def _build_result_quality_warning(
    *,
    quality_report: Mapping[str, object],
    latest_result_notice: Mapping[str, str] | None,
) -> dict[str, object] | None:
    quality_status = str(quality_report.get("quality_status", "") or "")
    if quality_status not in {"warn", "fail"}:
        return None
    return {
        "kind": "translation_quality_gate",
        "quality_status": quality_status,
        "gate_reasons": list(cast(Sequence[str], quality_report.get("gate_reasons") or [])),
        "message": str((latest_result_notice or {}).get("message", "") or ""),
    }


def _build_quality_gate_activity_message(gate_reasons: Sequence[str]) -> str:
    if not gate_reasons:
        return "Итоговый перевод отклонён document-level quality gate."
    joined_reasons = ", ".join(str(reason) for reason in gate_reasons if str(reason))
    if not joined_reasons:
        return "Итоговый перевод отклонён document-level quality gate."
    return f"Итоговый перевод отклонён quality gate: {joined_reasons}."


def _emit_terminal_result(
    *,
    emitters: Any,
    runtime: object,
    finalize_stage: str,
    detail: str,
    progress: float,
    terminal_kind: str,
    activity_message: str,
    log_status: str,
    block_index: int,
    block_count: int,
    target_chars: int,
    context_chars: int,
    log_details: str,
) -> None:
    emitters.emit_finalize(runtime, finalize_stage, detail, progress, terminal_kind)
    emitters.emit_activity(runtime, activity_message)
    emitters.emit_log(
        runtime,
        status=log_status,
        block_index=block_index,
        block_count=block_count,
        target_chars=target_chars,
        context_chars=context_chars,
        details=log_details,
    )


def emit_failed_result(
    *,
    emitters: Any,
    runtime: object,
    finalize_stage: str,
    detail: str,
    progress: float,
    activity_message: str,
    block_index: int,
    block_count: int,
    target_chars: int,
    context_chars: int,
    log_details: str,
) -> PipelineResult:
    _emit_terminal_result(
        emitters=emitters,
        runtime=runtime,
        finalize_stage=finalize_stage,
        detail=detail,
        progress=progress,
        terminal_kind="error",
        activity_message=activity_message,
        log_status="ERROR",
        block_index=block_index,
        block_count=block_count,
        target_chars=target_chars,
        context_chars=context_chars,
        log_details=log_details,
    )
    return "failed"


def emit_stopped_result(
    *,
    emitters: Any,
    runtime: object,
    detail: str,
    progress: float,
    block_index: int,
    block_count: int,
) -> PipelineResult:
    _emit_terminal_result(
        emitters=emitters,
        runtime=runtime,
        finalize_stage="Остановлено пользователем",
        detail=detail,
        progress=progress,
        terminal_kind="stopped",
        activity_message=detail,
        log_status="STOP",
        block_index=block_index,
        block_count=block_count,
        target_chars=0,
        context_chars=0,
        log_details=detail,
    )
    return "stopped"


def fail_empty_processing_plan(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
) -> PipelineResult:
    error_message = dependencies.present_error(
        "empty_processing_plan",
        RuntimeError("План обработки документа пуст."),
        "Ошибка подготовки обработки",
        filename=context.uploaded_filename,
    )
    emitters.emit_state(
        context.runtime,
        last_error=error_message,
        latest_markdown="",
        processed_block_markdowns=[],
        latest_docx_bytes=None,
        latest_narration_text=None,
    )
    return emit_failed_result(
        emitters=emitters,
        runtime=context.runtime,
        finalize_stage="Ошибка подготовки обработки",
        detail=error_message,
        progress=0.0,
        activity_message="Обработка документа остановлена: не найдено ни одного блока для обработки.",
        block_index=0,
        block_count=0,
        target_chars=0,
        context_chars=0,
        log_details=error_message,
    )


def run_image_processing_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    current_markdown_fn: Callable[[Sequence[str]], str],
) -> Any | None:
    assembly_result = assemble_final_markdown(
        processed_chunks=state.processed_chunks,
        generated_paragraph_registry=state.generated_paragraph_registry,
        source_paragraphs=context.source_paragraphs,
    )
    _log_boundary_recovery_diagnostics(dependencies=dependencies, context=context, assembly_result=assembly_result)
    final_markdown = assembly_result.final_markdown
    display_markdown = _normalize_final_markdown_for_runtime_display(final_markdown)
    emitters.emit_state(context.runtime, latest_markdown=display_markdown)
    try:
        image_client = initialization.openai_client
        image_mode_requires_openai_client = context.image_mode not in {
            ImageMode.NO_CHANGE.value,
            ImageMode.SAFE.value,
        }
        if (
            image_client is None
            and image_mode_requires_openai_client
            and callable(getattr(dependencies, "get_provider_client", None))
        ):
            image_client = dependencies.get_provider_client("openai")
        if image_client is None and image_mode_requires_openai_client:
            raise RuntimeError("Для image phase, требующей OpenAI, не удалось получить OpenAI client.")
        if image_client is None:
            image_client = initialization.client
        processed_image_assets = dependencies.process_document_images(
            image_assets=context.image_assets,
            image_mode=context.image_mode,
            config=context.app_config,
            on_progress=context.on_progress,
            runtime=context.runtime,
            client=image_client,
        )
        if processed_image_assets is None:
            raise RuntimeError("Пайплайн обработки изображений вернул None вместо коллекции ассетов.")

        normalized_image_assets = list(processed_image_assets)
        placeholder_integrity = dependencies.inspect_placeholder_integrity(display_markdown, normalized_image_assets)
        if not isinstance(placeholder_integrity, Mapping):
            raise TypeError("Проверка целостности placeholder вернула неподдерживаемый тип результата.")

        for asset in normalized_image_assets:
            asset.update_pipeline_metadata(placeholder_status=placeholder_integrity.get(asset.image_id))
    except Exception as exc:
        error_message = dependencies.present_error(
            "image_processing_failed",
            exc,
            "Ошибка обработки изображений",
            filename=context.uploaded_filename,
            final_markdown_chars=len(display_markdown),
            image_count=len(context.image_assets),
            image_mode=context.image_mode,
        )
        emitters.emit_state(
            context.runtime,
            latest_markdown=display_markdown,
            last_error=error_message,
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        emit_failed_result(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Ошибка обработки изображений",
            detail=error_message,
            progress=1.0,
            activity_message="Ошибка на этапе обработки изображений документа.",
            block_index=initialization.job_count,
            block_count=initialization.job_count,
            target_chars=len(display_markdown),
            context_chars=0,
            log_details=error_message,
        )
        return None

    return {
        "processed_image_assets": normalized_image_assets,
        "placeholder_integrity": placeholder_integrity,
    }


def _reconcile_placeholder_integrity(
    placeholder_integrity: Mapping[str, str],
    image_assets: Sequence[Any],
) -> dict[str, str]:
    expected_ids = {asset.image_id for asset in image_assets}
    observed_ids = {image_id for image_id in placeholder_integrity if image_id in expected_ids}
    mismatches = {
        image_id: placeholder_status
        for image_id, placeholder_status in placeholder_integrity.items()
        if placeholder_status != "ok"
    }
    for missing_image_id in sorted(expected_ids - observed_ids):
        mismatches[missing_image_id] = "missing_status"
    return mismatches


def validate_placeholder_integrity_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    final_markdown: str,
    image_phase: Mapping[str, object],
    job_count: int,
) -> bool:
    placeholder_mismatches = _reconcile_placeholder_integrity(
        cast(Mapping[str, str], image_phase["placeholder_integrity"]),
        cast(Sequence[Any], image_phase["processed_image_assets"]),
    )
    for image_id, placeholder_status in placeholder_mismatches.items():
        dependencies.log_event(
            logging.WARNING,
            "image_placeholder_mismatch",
            "Обнаружено нарушение контракта image placeholder.",
            filename=context.uploaded_filename,
            image_id=image_id,
            placeholder_status=placeholder_status,
        )
    if not placeholder_mismatches:
        return True

    mismatch_details = ", ".join(
        f"{image_id}:{placeholder_status}"
        for image_id, placeholder_status in sorted(placeholder_mismatches.items())
    )
    critical_message = dependencies.present_error(
        "image_placeholder_integrity_failed",
        RuntimeError(f"Нарушен контракт placeholder-ов: {mismatch_details}"),
        "Критическая ошибка подготовки изображений",
        filename=context.uploaded_filename,
        mismatch_count=len(placeholder_mismatches),
        mismatch_details=mismatch_details,
    )
    emitters.emit_state(
        context.runtime,
        last_error=critical_message,
        latest_docx_bytes=None,
        latest_narration_text=None,
    )
    emit_failed_result(
        emitters=emitters,
        runtime=context.runtime,
        finalize_stage="Критическая ошибка",
        detail=critical_message,
        progress=1.0,
        activity_message="Сборка DOCX остановлена из-за потери или дублирования image placeholder.",
        block_index=job_count,
        block_count=job_count,
        target_chars=len(final_markdown),
        context_chars=0,
        log_details=critical_message,
    )
    return False


def run_docx_build_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    image_phase: Mapping[str, object],
    job_count: int,
    diagnostics_dir: Path,
    current_markdown_fn: Callable[[Sequence[str]], str],
    call_docx_restorer_with_optional_registry_fn: Callable[[Any, bytes, Any, Any], bytes],
) -> Any | None:
    reassembly_plan = build_reassembly_plan(
        selected_segment_ids=getattr(context, "selected_segment_ids", None),
        segment_selection=getattr(context, "segment_selection", None),
        output_mode=str(getattr(context, "output_mode", "") or ""),
        include_front_matter=bool(getattr(context, "include_front_matter", False)),
        include_toc=bool(getattr(context, "include_toc", False)),
        jobs=list(getattr(context, "jobs", ()) or ()),
        source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
    )
    assembly_result = assemble_final_markdown(
        processed_chunks=state.processed_chunks,
        generated_paragraph_registry=state.generated_paragraph_registry,
        source_paragraphs=context.source_paragraphs,
    )
    _log_boundary_recovery_diagnostics(dependencies=dependencies, context=context, assembly_result=assembly_result)
    final_markdown = assembly_result.final_markdown
    assembly_registry = build_generated_paragraph_registry_from_entries(assembly_result.entries)
    result_manifest = build_reassembly_result_manifest(
        source_name=context.uploaded_filename,
        source_token=str(getattr(context, "source_token", "") or ""),
        run_id=str(getattr(context, "run_id", "") or ""),
        plan=reassembly_plan,
        jobs=list(getattr(context, "jobs", ()) or ()),
        source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
    )
    current_segment_records = {
        str(record.get("segment_id") or ""): record
        for record in build_segment_result_records(
            source_name=context.uploaded_filename,
            prepared_source_key=str(getattr(context, "prepared_source_key", "") or ""),
            structure_fingerprint=str(getattr(context, "structure_fingerprint", "") or ""),
            plan=reassembly_plan,
            source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
            assembly_entries=assembly_result.entries,
            result_artifact_paths={},
        )
        if str(record.get("segment_id") or "").strip()
    }
    if reassembly_plan.output_mode == "hybrid_document":
        persisted_segment_records = load_segment_result_records(
            prepared_source_key=str(getattr(context, "prepared_source_key", "") or ""),
            structure_fingerprint=str(getattr(context, "structure_fingerprint", "") or ""),
        )
        hybrid_result = assemble_hybrid_document(
            plan=reassembly_plan,
            source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
            current_segment_records=current_segment_records,
            persisted_segment_records=persisted_segment_records,
        )
        if hybrid_result.final_markdown:
            final_markdown = hybrid_result.final_markdown
            assembly_registry = hybrid_result.generated_paragraph_registry
            result_manifest = build_reassembly_result_manifest(
                source_name=context.uploaded_filename,
                source_token=str(getattr(context, "source_token", "") or ""),
                run_id=str(getattr(context, "run_id", "") or ""),
                plan=reassembly_plan,
                jobs=list(getattr(context, "jobs", ()) or ()),
                source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
                segment_provenance_by_id=hybrid_result.segment_provenance_by_id,
            )
            dependencies.log_event(
                logging.INFO,
                "hybrid_document_assembled",
                "Собран mixed hybrid_document из translated registry и source-backed fallback segments.",
                filename=context.uploaded_filename,
                translated_segment_count=sum(1 for value in hybrid_result.segment_provenance_by_id.values() if value == "translated"),
                source_segment_count=sum(1 for value in hybrid_result.segment_provenance_by_id.values() if value == "source"),
            )
    elif reassembly_plan.output_mode == "final_translated_book":
        final_book_result = assemble_hybrid_document(
            plan=reassembly_plan,
            source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
            current_segment_records=current_segment_records,
            persisted_segment_records={},
        )
        incomplete_segment_ids = [
            segment_id
            for segment_id in reassembly_plan.included_segment_ids
            if final_book_result.segment_provenance_by_id.get(segment_id) != "translated"
        ]
        if incomplete_segment_ids:
            error_message = dependencies.present_error(
                "final_translated_book_incomplete",
                RuntimeError(
                    "Missing translated segments for final_translated_book: " + ", ".join(incomplete_segment_ids)
                ),
                "Итоговая книга недоступна",
                filename=context.uploaded_filename,
                missing_segment_count=len(incomplete_segment_ids),
                missing_segment_ids=incomplete_segment_ids,
            )
            emitters.emit_state(
                context.runtime,
                last_error=error_message,
                latest_docx_bytes=None,
                latest_narration_text=None,
            )
            emit_failed_result(
                emitters=emitters,
                runtime=context.runtime,
                finalize_stage="Итоговая книга недоступна",
                detail=error_message,
                progress=1.0,
                activity_message="Сборка final_translated_book остановлена: не все обязательные сегменты переведены.",
                block_index=job_count,
                block_count=job_count,
                target_chars=len(final_markdown),
                context_chars=0,
                log_details=error_message,
            )
            dependencies.log_event(
                logging.WARNING,
                "final_translated_book_incomplete",
                "Не удалось собрать final_translated_book: не все обязательные сегменты имеют translated output.",
                filename=context.uploaded_filename,
                missing_segment_count=len(incomplete_segment_ids),
                missing_segment_ids=incomplete_segment_ids,
            )
            return None
        if final_book_result.final_markdown:
            final_markdown = final_book_result.final_markdown
            assembly_registry = final_book_result.generated_paragraph_registry
            result_manifest = build_reassembly_result_manifest(
                source_name=context.uploaded_filename,
                source_token=str(getattr(context, "source_token", "") or ""),
                run_id=str(getattr(context, "run_id", "") or ""),
                plan=reassembly_plan,
                jobs=list(getattr(context, "jobs", ()) or ()),
                source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
                segment_provenance_by_id=final_book_result.segment_provenance_by_id,
            )
            dependencies.log_event(
                logging.INFO,
                "final_translated_book_assembled",
                "Собран final_translated_book только из translated segment outputs текущего запуска.",
                filename=context.uploaded_filename,
                translated_segment_count=sum(1 for value in final_book_result.segment_provenance_by_id.values() if value == "translated"),
            )
    elif reassembly_plan.output_mode == "selected_with_context":
        selected_with_context_result = assemble_hybrid_document(
            plan=reassembly_plan,
            source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
            current_segment_records=current_segment_records,
            persisted_segment_records={},
        )
        if selected_with_context_result.final_markdown:
            final_markdown = selected_with_context_result.final_markdown
            assembly_registry = selected_with_context_result.generated_paragraph_registry
            result_manifest = build_reassembly_result_manifest(
                source_name=context.uploaded_filename,
                source_token=str(getattr(context, "source_token", "") or ""),
                run_id=str(getattr(context, "run_id", "") or ""),
                plan=reassembly_plan,
                jobs=list(getattr(context, "jobs", ()) or ()),
                source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
                segment_provenance_by_id=selected_with_context_result.segment_provenance_by_id,
            )
            dependencies.log_event(
                logging.INFO,
                "selected_with_context_assembled",
                "Собран selected_with_context из leading structural source context и translated selected segments.",
                filename=context.uploaded_filename,
                translated_segment_count=sum(1 for value in selected_with_context_result.segment_provenance_by_id.values() if value == "translated"),
                source_segment_count=sum(1 for value in selected_with_context_result.segment_provenance_by_id.values() if value == "source"),
            )
    display_markdown = _normalize_final_markdown_for_runtime_display(final_markdown)
    emitters.emit_status(
        context.runtime,
        stage="Сборка DOCX",
        detail="Все блоки готовы. Собираю итоговый DOCX из Markdown.",
        current_block=job_count,
        block_count=job_count,
        target_chars=len(display_markdown),
        context_chars=0,
        progress=1.0,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, "Все блоки готовы. Начата сборка итогового DOCX.")
    context.on_progress(preview_title="Текущий Markdown")
    build_started_at_epoch = time.time()

    try:
        docx_bytes = dependencies.convert_markdown_to_docx_bytes(display_markdown)
        if context.source_paragraphs:
            docx_bytes = call_docx_restorer_with_optional_registry_fn(
                dependencies.preserve_source_paragraph_properties,
                docx_bytes,
                context.source_paragraphs,
                assembly_registry or state.generated_paragraph_registry or None,
            )
        processed_image_assets = image_phase["processed_image_assets"]
        if processed_image_assets:
            docx_bytes = dependencies.reinsert_inline_images(docx_bytes, processed_image_assets)
    except Exception as exc:
        error_message = dependencies.present_error(
            "docx_build_failed",
            exc,
            "Ошибка сборки DOCX",
            filename=context.uploaded_filename,
            final_markdown_chars=len(display_markdown),
        )
        emitters.emit_state(
            context.runtime,
            last_error=error_message,
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        emit_failed_result(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Ошибка сборки DOCX",
            detail=error_message,
            progress=1.0,
            activity_message="Ошибка на этапе сборки DOCX.",
            block_index=job_count,
            block_count=job_count,
            target_chars=len(display_markdown),
            context_chars=0,
            log_details=error_message,
        )
        return None

    latest_result_notice: dict[str, str] | None = None
    formatting_diagnostics_artifacts = collect_recent_formatting_diagnostics_artifacts(
        since_epoch_seconds=build_started_at_epoch,
        diagnostics_dir=diagnostics_dir,
    )
    if formatting_diagnostics_artifacts:
        severity, activity_message, user_summary = build_formatting_diagnostics_user_feedback(
            formatting_diagnostics_artifacts
        )
        emitters.emit_activity(context.runtime, activity_message)
        if severity == "INFO":
            latest_result_notice = {"level": "info", "message": user_summary}
        else:
            emitters.emit_log(
                context.runtime,
                status=severity,
                block_index=job_count,
                block_count=job_count,
                target_chars=len(final_markdown),
                context_chars=0,
                details=user_summary,
            )
        dependencies.log_event(
            logging.WARNING,
            "formatting_diagnostics_artifacts_detected",
            "Во время сборки DOCX сохранены formatting diagnostics artifacts.",
            filename=context.uploaded_filename,
            artifact_paths=formatting_diagnostics_artifacts,
        )

    if not docx_bytes:
        critical_message = dependencies.present_error(
            "empty_docx_bytes",
            RuntimeError("Сборка DOCX завершилась без содержимого файла."),
            "Критическая ошибка сборки DOCX",
            filename=context.uploaded_filename,
        )
        emitters.emit_state(
            context.runtime,
            last_error=critical_message,
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        emit_failed_result(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Критическая ошибка",
            detail=critical_message,
            progress=1.0,
            activity_message="DOCX собран без содержимого.",
            block_index=job_count,
            block_count=job_count,
            target_chars=len(final_markdown),
            context_chars=0,
            log_details=critical_message,
        )
        return None

    return {
        "docx_bytes": docx_bytes,
        "final_markdown": display_markdown,
        "latest_result_notice": latest_result_notice,
        "formatting_diagnostics_artifacts": list(formatting_diagnostics_artifacts),
        "assembly_entries": list(assembly_result.entries),
        "result_manifest": result_manifest,
    }


def finalize_processing_success(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    docx_phase: Mapping[str, object],
    job_count: int,
    current_markdown_fn: Callable[[Sequence[str]], str],
) -> PipelineResult:
    assembly_result = assemble_final_markdown(
        processed_chunks=state.processed_chunks,
        generated_paragraph_registry=state.generated_paragraph_registry,
        source_paragraphs=context.source_paragraphs,
    )
    _log_boundary_recovery_diagnostics(dependencies=dependencies, context=context, assembly_result=assembly_result)
    gate_input_markdown = assembly_result.final_markdown
    final_markdown = str(
        docx_phase.get("final_markdown")
        or _normalize_final_markdown_for_runtime_display(gate_input_markdown)
    )
    formatting_diagnostics_artifacts = cast(
        Sequence[str],
        docx_phase.get("formatting_diagnostics_artifacts") or [],
    )
    quality_report = _build_translation_quality_report(
        context=context,
        final_markdown=gate_input_markdown,
        formatting_diagnostics_artifacts=formatting_diagnostics_artifacts,
        assembly_result=assembly_result,
    )
    if quality_report.get("quality_status") == "warn":
        docx_phase = dict(docx_phase)
        docx_phase["latest_result_notice"] = {
            "level": "warning",
            "message": "Результат собран, но quality report зафиксировал document-level structural warnings.",
        }
    quality_report_path = _write_quality_report_artifact(source_name=context.uploaded_filename, payload=quality_report)
    if quality_report_path is not None:
        dependencies.log_event(
            logging.INFO,
            "quality_report_saved",
            "Сохранён quality report для итогового результата обработки.",
            filename=context.uploaded_filename,
            artifact_path=quality_report_path,
            quality_status=quality_report.get("quality_status"),
            gate_reasons=list(cast(Sequence[str], quality_report.get("gate_reasons") or [])),
        )
    if quality_report.get("quality_status") == "fail":
        gate_reasons = list(cast(Sequence[str], quality_report.get("gate_reasons") or []))
        error_message = dependencies.present_error(
            "translation_quality_gate_failed",
            RuntimeError(_format_translation_quality_gate_failure_message(gate_reasons)),
            "Критическая ошибка качества перевода",
            filename=context.uploaded_filename,
            quality_status=quality_report.get("quality_status"),
            gate_reasons=gate_reasons,
            quality_report_path=quality_report_path,
        )
        emitters.emit_state(
            context.runtime,
            latest_markdown=final_markdown,
            latest_docx_bytes=docx_phase["docx_bytes"],
            latest_narration_text=None,
            latest_result_notice={
                "level": "error",
                "message": "Результат заблокирован document-level quality gate.",
            },
            last_error=error_message,
        )
        dependencies.log_event(
            logging.WARNING,
            "translation_quality_gate_failed",
            "Итоговый перевод отклонён document-level quality gate.",
            filename=context.uploaded_filename,
            quality_report_path=quality_report_path,
            gate_reasons=gate_reasons,
            quality_status=quality_report.get("quality_status"),
        )
        return emit_failed_result(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Критическая ошибка качества перевода",
            detail=error_message,
            progress=1.0,
            activity_message=_build_quality_gate_activity_message(gate_reasons),
            block_index=job_count,
            block_count=job_count,
            target_chars=len(final_markdown),
            context_chars=0,
            log_details=error_message,
        )
    narration_error_message = ""
    try:
        narration_text = _build_narration_text(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
        )
    except Exception as exc:
        error_message = dependencies.present_error(
            "audiobook_postprocess_failed",
            exc,
            "Ошибка подготовки текста для ElevenLabs",
            filename=context.uploaded_filename,
            processing_operation=context.processing_operation,
        )
        if context.processing_operation in {"edit", "translate"}:
            narration_text = None
            narration_error_message = error_message
            emitters.emit_state(
                context.runtime,
                latest_docx_bytes=docx_phase["docx_bytes"],
                latest_markdown=final_markdown,
                latest_narration_text=None,
                latest_result_notice=docx_phase["latest_result_notice"],
                last_error=error_message,
            )
            dependencies.log_event(
                logging.WARNING,
                "audiobook_postprocess_failed_base_result_preserved",
                "Audiobook post-pass failed; base DOCX/Markdown result is preserved.",
                filename=context.uploaded_filename,
                processing_operation=context.processing_operation,
                error_message=str(exc),
            )
        else:
            emitters.emit_state(
                context.runtime,
                latest_markdown=final_markdown,
                latest_docx_bytes=None,
                latest_narration_text=None,
                last_error=error_message,
            )
            return emit_failed_result(
                emitters=emitters,
                runtime=context.runtime,
                finalize_stage="Ошибка подготовки narration",
                detail=error_message,
                progress=1.0,
                activity_message="Ошибка на этапе подготовки текста для ElevenLabs.",
                block_index=job_count,
                block_count=job_count,
                target_chars=len(final_markdown),
                context_chars=0,
                log_details=error_message,
            )

    if narration_text is not None:
        try:
            _validate_narration_artifact_text(narration_text)
        except Exception as exc:
            error_message = dependencies.present_error(
                "audiobook_artifact_validation_failed",
                exc,
                "Ошибка проверки текста для ElevenLabs",
                filename=context.uploaded_filename,
                processing_operation=context.processing_operation,
            )
            if context.processing_operation in {"edit", "translate"}:
                narration_text = None
                narration_error_message = error_message
                emitters.emit_state(
                    context.runtime,
                    latest_docx_bytes=docx_phase["docx_bytes"],
                    latest_markdown=final_markdown,
                    latest_narration_text=None,
                    latest_result_notice=docx_phase["latest_result_notice"],
                    last_error=error_message,
                )
                dependencies.log_event(
                    logging.WARNING,
                    "audiobook_artifact_validation_failed_base_result_preserved",
                    "Narration artifact validation failed; base DOCX/Markdown result is preserved.",
                    filename=context.uploaded_filename,
                    processing_operation=context.processing_operation,
                    error_message=str(exc),
                )
            else:
                emitters.emit_state(
                    context.runtime,
                    latest_markdown=final_markdown,
                    latest_docx_bytes=None,
                    latest_narration_text=None,
                    last_error=error_message,
                )
                return emit_failed_result(
                    emitters=emitters,
                    runtime=context.runtime,
                    finalize_stage="Ошибка проверки narration",
                    detail=error_message,
                    progress=1.0,
                    activity_message="Текст для ElevenLabs не прошёл deterministic validation.",
                    block_index=job_count,
                    block_count=job_count,
                    target_chars=len(final_markdown),
                    context_chars=0,
                    log_details=error_message,
                )
    emitters.emit_state(
        context.runtime,
        latest_docx_bytes=docx_phase["docx_bytes"],
        latest_markdown=final_markdown,
        latest_narration_text=narration_text,
        latest_result_notice=docx_phase["latest_result_notice"],
        last_error=narration_error_message,
    )
    try:
        reassembly_plan = build_reassembly_plan(
            selected_segment_ids=getattr(context, "selected_segment_ids", None),
            segment_selection=getattr(context, "segment_selection", None),
            output_mode=str(getattr(context, "output_mode", "") or ""),
            include_front_matter=bool(getattr(context, "include_front_matter", False)),
            include_toc=bool(getattr(context, "include_toc", False)),
            jobs=list(getattr(context, "jobs", ()) or ()),
            source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
        )
        artifact_writer_kwargs = {
            "source_name": context.uploaded_filename,
            "markdown_text": final_markdown,
            "docx_bytes": docx_phase["docx_bytes"],
            "assembly_mode": reassembly_plan.assembly_mode,
            "result_manifest": docx_phase.get("result_manifest")
            or build_reassembly_result_manifest(
                source_name=context.uploaded_filename,
                plan=reassembly_plan,
                jobs=list(getattr(context, "jobs", ()) or ()),
                source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
            ),
        }
        if reassembly_plan.selected_segment_count is not None:
            artifact_writer_kwargs["selected_segment_count"] = reassembly_plan.selected_segment_count
        quality_warning = _build_result_quality_warning(
            quality_report=quality_report,
            latest_result_notice=cast(Mapping[str, str] | None, docx_phase.get("latest_result_notice")),
        )
        if quality_warning is not None:
            artifact_writer_kwargs["quality_warning"] = quality_warning
        if narration_text is not None:
            artifact_writer_kwargs["narration_text"] = narration_text
        result_artifact_paths = dict(
            dependencies.write_ui_result_artifacts(**artifact_writer_kwargs)
        )
    except OSError as exc:
        dependencies.log_event(
            logging.WARNING,
            "ui_result_artifacts_save_failed",
            "Не удалось сохранить итоговые UI-артефакты обработки.",
            filename=context.uploaded_filename,
            error_message=str(exc),
        )
    else:
        dependencies.log_event(
            logging.INFO,
            "ui_result_artifacts_saved",
            "Сохранены итоговые UI-артефакты обработки.",
            filename=context.uploaded_filename,
            artifact_paths=result_artifact_paths,
        )
        segment_result_records = build_segment_result_records(
            source_name=context.uploaded_filename,
            prepared_source_key=str(getattr(context, "prepared_source_key", "") or ""),
            structure_fingerprint=str(getattr(context, "structure_fingerprint", "") or ""),
            plan=reassembly_plan,
            source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
            assembly_entries=cast(Sequence[object], docx_phase.get("assembly_entries") or assembly_result.entries),
            result_artifact_paths=result_artifact_paths,
        )
        if segment_result_records:
            try:
                segment_registry_paths = dict(
                    dependencies.write_segment_result_registry(records=segment_result_records)
                )
            except OSError as exc:
                dependencies.log_event(
                    logging.WARNING,
                    "segment_result_registry_save_failed",
                    "Не удалось сохранить persisted segment result registry.",
                    filename=context.uploaded_filename,
                    error_message=str(exc),
                )
            else:
                dependencies.log_event(
                    logging.INFO,
                    "segment_result_registry_saved",
                    "Сохранён persisted segment result registry для итоговой сборки.",
                    filename=context.uploaded_filename,
                    segment_count=len(segment_result_records),
                    artifact_paths=segment_registry_paths,
                )
        if narration_text is not None and "tts_text_path" in result_artifact_paths:
            dependencies.log_event(
                logging.INFO,
                "ui_audiobook_artifact_saved",
                "Сохранён итоговый narration artifact для ElevenLabs.",
                filename=context.uploaded_filename,
                source_name=context.uploaded_filename,
                artifact_paths=result_artifact_paths,
                tts_text_path=result_artifact_paths["tts_text_path"],
                char_count=len(narration_text),
                tag_count=len(_ELEVENLABS_TAG_PATTERN.findall(narration_text)),
                excluded_blocks=int(getattr(state, "excluded_narration_block_count", 0) or 0),
                mode="standalone" if context.processing_operation == "audiobook" else "postprocess",
            )
    emitters.emit_finalize(
        context.runtime,
        "Обработка завершена",
        f"Документ обработан за {time.perf_counter() - state.started_at:.1f} сек.",
        1.0,
        "completed",
    )
    emitters.emit_activity(context.runtime, "Документ обработан полностью.")
    dependencies.log_event(
        logging.INFO,
        "processing_completed",
        "Документ обработан полностью",
        filename=context.uploaded_filename,
        block_count=job_count,
        final_markdown_chars=len(final_markdown),
        narration_chars=len(narration_text or ""),
        elapsed_seconds=round(time.perf_counter() - state.started_at, 2),
        translation_second_pass_enabled=_is_translation_second_pass_effectively_enabled(context=context),
        audiobook_postprocess_enabled=_should_run_audiobook_postprocess(context=context),
    )
    emitters.emit_log(
        context.runtime,
        status="DONE",
        block_index=job_count,
        block_count=job_count,
        target_chars=len(final_markdown),
        context_chars=0,
        details=f"весь документ обработан за {time.perf_counter() - state.started_at:.1f} сек.",
    )
    return "succeeded"


def _build_narration_text(*, context: Any, dependencies: Any, emitters: Any, state: Any) -> str | None:
    if context.processing_operation != "audiobook":
        if not _should_run_audiobook_postprocess(context=context):
            return None
        return _run_audiobook_postprocess(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
        )
    narration_source = "\n\n".join(_collect_narration_chunks(state=state))
    if not narration_source:
        return None
    return strip_markdown_for_narration(narration_source)


def _validate_narration_artifact_text(narration_text: str) -> None:
    violations = [name for name, pattern in _NARRATION_DISALLOWED_PATTERNS if pattern.search(narration_text)]
    disallowed_tags = sorted(
        {
            tag
            for tag in _NARRATION_ANY_TAG_PATTERN.findall(narration_text)
            if _ELEVENLABS_TAG_PATTERN.fullmatch(tag) is None
        }
    )
    if disallowed_tags:
        violations.append(f"disallowed_tags={','.join(disallowed_tags[:5])}")
    if violations:
        raise RuntimeError("narration_artifact_validation_failed:" + ";".join(violations))


def _should_run_audiobook_postprocess(*, context: Any) -> bool:
    return context.processing_operation in {"edit", "translate"} and bool(
        context.app_config.get("audiobook_postprocess_enabled", False)
    )


def _is_translation_second_pass_effectively_enabled(*, context: Any) -> bool:
    return context.processing_operation == "translate" and bool(
        context.app_config.get("translation_second_pass_enabled", False)
    )


def _collect_narration_chunks(*, state: Any) -> list[str]:
    return [str(chunk).strip() for chunk in getattr(state, "narration_chunks", []) if str(chunk).strip()]


def _resolve_audiobook_postprocess_model(*, context: Any) -> str:
    configured_model = str(context.app_config.get("audiobook_model", "")).strip()
    return configured_model or context.model


def _resolve_text_call_target(*, selector: str, context: Any, dependencies: Any, fallback_client: object | None) -> tuple[object, str, str, str | None]:
    resolver: Any = getattr(dependencies, "resolve_model_selector", None)
    client_factory: Any = getattr(dependencies, "get_client_for_model_selector", None)
    if not callable(resolver) or not callable(client_factory):
        if fallback_client is None:
            raise RuntimeError("Provider-aware text client factory is unavailable for the requested selector.")
        return fallback_client, selector, selector, None

    resolved_selector: Any = resolver(selector, "responses_text")
    return (
        client_factory(selector, "responses_text"),
        resolved_selector.model_id,
        resolved_selector.canonical_selector,
        resolved_selector.provider,
    )


def _resolve_audiobook_postprocess_chunk_size(*, context: Any) -> int:
    configured_chunk_size = context.app_config.get("chunk_size", 6000)
    try:
        return max(int(configured_chunk_size), 3000)
    except (TypeError, ValueError):
        return 6000


def _build_narration_postprocess_groups(*, narration_chunks: Sequence[str], chunk_size: int) -> list[dict[str, object]]:
    if not narration_chunks:
        return []

    groups: list[dict[str, object]] = []
    group_start = 0
    current_chunks: list[str] = []
    current_chars = 0

    for chunk_index, chunk in enumerate(narration_chunks):
        chunk_chars = len(chunk)
        separator_chars = 2 if current_chunks else 0
        if current_chunks and current_chars + separator_chars + chunk_chars > chunk_size:
            group_end = group_start + len(current_chunks) - 1
            groups.append(
                {
                    "group_index": len(groups) + 1,
                    "start_index": group_start,
                    "end_index": group_end,
                    "target_text": "\n\n".join(current_chunks),
                    "context_before": narration_chunks[group_start - 1] if group_start > 0 else "",
                    "context_after": narration_chunks[group_end + 1] if group_end + 1 < len(narration_chunks) else "",
                }
            )
            group_start = chunk_index
            current_chunks = [chunk]
            current_chars = chunk_chars
            continue

        current_chunks.append(chunk)
        current_chars += separator_chars + chunk_chars

    if current_chunks:
        group_end = group_start + len(current_chunks) - 1
        groups.append(
            {
                "group_index": len(groups) + 1,
                "start_index": group_start,
                "end_index": group_end,
                "target_text": "\n\n".join(current_chunks),
                "context_before": narration_chunks[group_start - 1] if group_start > 0 else "",
                "context_after": narration_chunks[group_end + 1] if group_end + 1 < len(narration_chunks) else "",
            }
        )

    return groups


def _run_audiobook_postprocess(*, context: Any, dependencies: Any, emitters: Any, state: Any) -> str | None:
    narration_chunks = _collect_narration_chunks(state=state)
    if not narration_chunks:
        return None

    system_prompt = dependencies.load_system_prompt(
        operation="audiobook",
        source_language=context.source_language,
        target_language=context.target_language,
        editorial_intensity=str(context.app_config.get("editorial_intensity_default", "literary")),
        prompt_variant="default",
    )
    model = _resolve_audiobook_postprocess_model(context=context)
    fallback_client = None
    if not callable(getattr(dependencies, "resolve_model_selector", None)) or not callable(
        getattr(dependencies, "get_client_for_model_selector", None)
    ):
        fallback_client = dependencies.get_client()
    client, model_id, model_selector, model_provider = _resolve_text_call_target(
        selector=model,
        context=context,
        dependencies=dependencies,
        fallback_client=fallback_client,
    )
    groups = _build_narration_postprocess_groups(
        narration_chunks=narration_chunks,
        chunk_size=_resolve_audiobook_postprocess_chunk_size(context=context),
    )

    emitters.emit_status(
        context.runtime,
        stage="Подготовка narration",
        detail="Запущен отдельный audiobook post-pass для текста ElevenLabs.",
        current_block=len(state.processed_chunks),
        block_count=max(len(state.processed_chunks), 1),
        target_chars=sum(len(chunk) for chunk in narration_chunks),
        context_chars=0,
        progress=1.0,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, "Запущена отдельная подготовка narration text для ElevenLabs.")

    processed_groups: list[str] = []
    for group in groups:
        target_text = str(group["target_text"])
        context_before = str(group["context_before"])
        context_after = str(group["context_after"])
        group_index = _require_group_int(group, "group_index")
        start_index = _require_group_int(group, "start_index")
        end_index = _require_group_int(group, "end_index")
        dependencies.log_event(
            logging.INFO,
            "audiobook_postprocess_chunk_started",
            "Запущен audiobook post-pass для narration chunk group.",
            filename=context.uploaded_filename,
            operation="audiobook",
            **{"pass": "postprocess"},
            model=model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=group_index,
            chunk_count=len(groups),
            target_chars=len(target_text),
            context_before_chars=len(context_before),
            context_after_chars=len(context_after),
            start_index=start_index,
            end_index=end_index,
        )
        processed_chunk = dependencies.generate_markdown_block(
            client=client,
            model=model_id,
            system_prompt=system_prompt,
            target_text=target_text,
            context_before=context_before,
            context_after=context_after,
            max_retries=context.max_retries,
            expected_paragraph_ids=None,
            marker_mode=False,
        )
        processed_groups.append(processed_chunk)
        dependencies.log_event(
            logging.INFO,
            "audiobook_postprocess_chunk_completed",
            "Audiobook post-pass для narration chunk group завершён.",
            filename=context.uploaded_filename,
            operation="audiobook",
            **{"pass": "postprocess"},
            model=model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=group_index,
            chunk_count=len(groups),
            output_chars=len(processed_chunk),
        )

    emitters.emit_activity(context.runtime, "Подготовка narration text для ElevenLabs завершена.")
    return strip_markdown_for_narration("\n\n".join(processed_groups))
