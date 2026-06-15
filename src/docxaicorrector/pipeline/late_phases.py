import logging
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
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
    collect_page_placeholder_heading_concat_samples,
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
from docxaicorrector.validation.formatting_coverage import (
    resolve_role_aware_formatting_unmapped_source_summary,
    resolve_role_aware_formatting_unmapped_target_summary,
)
from docxaicorrector.reader_cleanup_mvp import (
    build_cleanup_blocks,
    build_reader_cleanup_global_plan_system_prompt,
    build_reader_cleanup_schema_repair_system_prompt,
    build_reader_cleanup_system_prompt,
    ReaderCleanupStageError,
    resolve_reader_cleanup_config,
    run_reader_cleanup,
    write_reader_cleanup_diagnostics,
)
from docxaicorrector.runtime.artifact_retention import (
    READER_CLEANUP_LINEAGE_MAX_AGE_SECONDS,
    READER_CLEANUP_LINEAGE_MAX_COUNT,
    prune_artifact_dir,
)


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
READER_CLEANUP_LINEAGE_DIR = Path(".run") / "reader_cleanup_lineage"


@dataclass(frozen=True)
class ReaderCleanupPostprocessResult:
    markdown: str
    docx_bytes: bytes
    report: dict[str, object] | None
    raw_markdown: str | None
    result_notice: dict[str, str] | None
    final_generated_paragraph_registry: Sequence[Mapping[str, object]] | None
_BULLET_MARKDOWN_HEADING_PATTERN = re.compile(r"(?m)^\s{0,3}#{1,6}\s*[\u2022\u25cf\u25e6\u2023*\-]\s*$")
_DOCX_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"^\[\[DOCX_IMAGE_[A-Za-z0-9_]+\]\]$")
_DOCX_IMAGE_HEADING_CONCAT_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?P<placeholder>\[\[DOCX_IMAGE_[A-Za-z0-9_]+\]\])\s+(?P<text>\S.*)$"
)
_MARKDOWN_HEADING_LINE_PATTERN = re.compile(r"^\s*(?P<marker>#{1,6})\s+(?P<text>\S.*)$")


def _format_translation_quality_gate_failure_message(gate_reasons: Sequence[str]) -> str:
    reasons = humanize_quality_gate_reasons(gate_reasons)
    base = "Итоговый перевод не прошёл document-level quality gate."
    if not reasons:
        return f"{base} (translation_quality_gate_failed)"
    return f"{base} (translation_quality_gate_failed) Причины: {', '.join(reasons)}."


def _normalize_final_markdown_for_quality_gate(text: str) -> str:
    normalized = text
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if "\n" not in normalized and "\n\n" in text:
        return text
    return normalized


def _normalize_final_markdown_for_display_hygiene_reporting(text: str) -> str:
    normalized = normalize_page_placeholder_heading_concats_markdown(text)
    normalized = normalize_residual_bullet_glyphs_markdown(normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if "\n" not in normalized and "\n\n" in text:
        return text
    return normalized


def _apply_runtime_display_structure_compatibility_cleanup(text: str) -> str:
    # These repairs are display-only compatibility cleanup; quality/report logic keeps using raw gate input.
    normalized = normalize_false_fragment_headings_markdown(text)
    return normalize_list_fragment_regressions_markdown(normalized)


def _apply_runtime_display_hygiene_cleanup(text: str) -> str:
    normalized = normalize_page_placeholder_heading_concats_markdown(text)
    normalized = normalize_residual_bullet_glyphs_markdown(normalized)
    return normalize_mixed_script_markdown(normalized)


def _normalize_final_markdown_for_runtime_display(text: str) -> str:
    normalized = _apply_runtime_display_structure_compatibility_cleanup(text)
    normalized = _apply_runtime_display_hygiene_cleanup(normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if "\n" not in normalized and "\n\n" in text:
        return text
    return normalized


def _normalize_heading_match_text(text: str) -> str:
    normalized = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip().lower()
    return re.sub(r"\s+", " ", normalized)


def _registry_heading_markdown_lines(
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> list[tuple[str, str]]:
    heading_lines: list[tuple[str, str]] = []
    for entry in generated_paragraph_registry or []:
        text = str(entry.get("text") or entry.get("generated_text") or "").strip()
        match = _MARKDOWN_HEADING_LINE_PATTERN.match(text)
        if match is None:
            continue
        heading_text = str(match.group("text") or "").strip()
        normalized_heading = _normalize_heading_match_text(heading_text)
        if not normalized_heading:
            continue
        heading_lines.append((normalized_heading, f"{match.group('marker')} {heading_text}"))
    return heading_lines


def _restore_image_heading_lines_from_registry(
    markdown_text: str,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> str:
    heading_lines = _registry_heading_markdown_lines(generated_paragraph_registry)
    if not heading_lines:
        return markdown_text

    restored_lines: list[str] = []
    changed = False
    for raw_line in markdown_text.splitlines():
        match = _DOCX_IMAGE_HEADING_CONCAT_PATTERN.match(raw_line.rstrip())
        if match is None:
            restored_lines.append(raw_line.rstrip())
            continue

        concat_text = str(match.group("text") or "")
        normalized_concat = _normalize_heading_match_text(concat_text)
        matched_headings: list[str] = []
        for normalized_heading, heading_markdown in heading_lines:
            if normalized_heading in normalized_concat and heading_markdown not in matched_headings:
                matched_headings.append(heading_markdown)
        if not matched_headings:
            restored_lines.append(raw_line.rstrip())
            continue

        restored_lines.append(f"{match.group('indent')}{match.group('placeholder')}")
        restored_lines.append("")
        restored_lines.extend(f"{match.group('indent')}{heading}" for heading in matched_headings)
        changed = True

    if not changed:
        return markdown_text
    return re.sub(r"\n{3,}", "\n\n", "\n".join(restored_lines)).strip()


def _resolve_runtime_display_markdown(*, docx_phase: Mapping[str, object], fallback_markdown: str) -> str:
    runtime_display_markdown = docx_phase.get("runtime_display_markdown")
    if isinstance(runtime_display_markdown, str) and runtime_display_markdown:
        return runtime_display_markdown

    return _normalize_final_markdown_for_runtime_display(fallback_markdown)


def _should_run_reader_cleanup(*, context: Any) -> bool:
    return context.processing_operation == "translate" and bool(
        context.app_config.get("reader_cleanup_enabled", False)
    )


def _resolve_reader_cleanup_anchor_repair_targets(*, context: Any) -> list[dict[str, object]]:
    if not bool(context.app_config.get("reader_cleanup_anchor_repair_enabled", False)):
        return []
    raw_targets = context.app_config.get("reader_cleanup_anchor_targets") or []
    if not isinstance(raw_targets, Sequence) or isinstance(raw_targets, (str, bytes, bytearray)):
        return []

    targets: list[dict[str, object]] = []
    for item in raw_targets:
        if isinstance(item, Mapping):
            targets.append(dict(item))
    return targets


def _rebuild_docx_for_markdown(
    *,
    markdown_text: str,
    context: Any,
    dependencies: Any,
    state: Any,
    processed_image_assets: Sequence[Any],
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> bytes:
    formatting_registry = (
        generated_paragraph_registry
        if generated_paragraph_registry is not None
        else state.generated_paragraph_registry or None
    )
    rebuild_identity_registry = _build_rebuild_identity_formatting_registry(
        markdown_text=markdown_text,
        generated_paragraph_registry=formatting_registry,
    )
    docx_bytes = dependencies.convert_markdown_to_docx_bytes(markdown_text)
    if context.source_paragraphs:
        docx_bytes = dependencies.preserve_source_paragraph_properties(
            docx_bytes,
            context.source_paragraphs,
            rebuild_identity_registry or formatting_registry,
        )
    if processed_image_assets:
        docx_bytes = dependencies.reinsert_inline_images(docx_bytes, processed_image_assets)
    return docx_bytes


def _resolve_final_generated_paragraph_registry(
    *,
    markdown_text: str,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> Sequence[Mapping[str, object]] | None:
    if generated_paragraph_registry is None:
        return None
    rebuild_identity_registry = _build_rebuild_identity_formatting_registry(
        markdown_text=markdown_text,
        generated_paragraph_registry=generated_paragraph_registry,
    )
    return rebuild_identity_registry or generated_paragraph_registry


def _resolve_docx_phase_bytes(docx_phase: Mapping[str, object]) -> bytes:
    docx_bytes = docx_phase.get("docx_bytes")
    if isinstance(docx_bytes, bytes):
        return docx_bytes
    builder = docx_phase.get("base_docx_builder")
    if callable(builder):
        resolved_docx_bytes = builder()
        if isinstance(docx_phase, dict):
            docx_phase["docx_bytes"] = resolved_docx_bytes
        return resolved_docx_bytes
    return b""


def _build_empty_docx_failure_result(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    runtime_display_markdown: str,
    job_count: int,
) -> PipelineResult:
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
    return emit_failed_result(
        emitters=emitters,
        runtime=context.runtime,
        finalize_stage="Критическая ошибка",
        detail=critical_message,
        progress=1.0,
        activity_message="DOCX собран без содержимого.",
        block_index=job_count,
        block_count=job_count,
        target_chars=len(runtime_display_markdown),
        context_chars=0,
        log_details=critical_message,
    )


def _validate_nonempty_docx_bytes_or_fail(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    runtime_display_markdown: str,
    job_count: int,
    docx_bytes: bytes,
) -> PipelineResult | None:
    if docx_bytes:
        return None
    return _build_empty_docx_failure_result(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        runtime_display_markdown=runtime_display_markdown,
        job_count=job_count,
    )


def _build_pre_cleanup_formatting_baseline(
    *,
    markdown_text: str,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> dict[str, object] | None:
    target_blocks = build_cleanup_blocks(markdown_text)
    if not generated_paragraph_registry:
        return {
            "stage": "pre_reader_cleanup_rebuild_identity",
            "classification": "diagnostic_only",
            "mapping_basis": "ordered_exact_text_rebuild_sidecar",
            "metric_scope": "sidecar_only_proxy",
            "status": "missing_registry",
            "source_count": 0,
            "target_count": len(target_blocks),
            "mapped_count": 0,
            "unmapped_source_count": 0,
            "unmapped_target_count": len(target_blocks),
            "unmapped_source_ids": [],
            "unmapped_target_indexes": list(range(len(target_blocks))),
        }
    aligned_registry = _build_rebuild_identity_formatting_registry(
        markdown_text=markdown_text,
        generated_paragraph_registry=generated_paragraph_registry,
    )
    if aligned_registry is None:
        aligned_registry = [dict(entry) for entry in generated_paragraph_registry]
    mapped_target_indexes: set[int] = set()
    unmapped_source_ids: list[str] = []
    mapped_count = 0
    for entry in aligned_registry:
        target_indexes = entry.get("target_paragraph_indexes")
        paragraph_id = str(entry.get("paragraph_id") or "").strip()
        if isinstance(target_indexes, list) and target_indexes:
            mapped_count += 1
            mapped_target_indexes.update(index for index in target_indexes if isinstance(index, int))
        elif paragraph_id:
            unmapped_source_ids.append(paragraph_id)
    target_count = len(target_blocks)
    unmapped_target_indexes = [index for index in range(target_count) if index not in mapped_target_indexes]
    return {
        "stage": "pre_reader_cleanup_rebuild_identity",
        "classification": "diagnostic_only",
        "mapping_basis": "ordered_exact_text_rebuild_sidecar",
        "metric_scope": "sidecar_only_proxy",
        "status": "computed",
        "source_count": len(aligned_registry),
        "target_count": target_count,
        "mapped_count": mapped_count,
        "unmapped_source_count": len(unmapped_source_ids),
        "unmapped_target_count": len(unmapped_target_indexes),
        "unmapped_source_ids": unmapped_source_ids,
        "unmapped_target_indexes": unmapped_target_indexes,
    }


def _build_rebuild_identity_formatting_registry(
    *,
    markdown_text: str,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> list[dict[str, object]] | None:
    """Attach rebuild-only target paragraph indexes to formatting registry entries.

    The indexes are a sidecar for final DOCX restore. They are not written into
    reader-facing Markdown, not sent to the model, and not persisted into the
    final DOCX. Matching is intentionally exact and ordered: if a registry entry
    cannot be aligned to the rebuilt Markdown blocks, that entry is left without
    target indexes and the formatter falls back to its existing conservative
    strategies.
    """
    if not generated_paragraph_registry:
        return None

    markdown_blocks = build_cleanup_blocks(markdown_text)
    if not markdown_blocks:
        return [dict(entry) for entry in generated_paragraph_registry if isinstance(entry, Mapping)]

    registry_entries = [dict(entry) for entry in generated_paragraph_registry if isinstance(entry, Mapping)]
    target_indexes_by_registry_index: dict[int, list[int]] = {}
    search_start_index = 0

    for registry_index, entry in enumerate(registry_entries):
        entry_text = str(entry.get("text") or "").strip()
        entry_blocks = build_cleanup_blocks(entry_text)
        if not entry_blocks:
            continue

        matched_indexes: list[int] = []
        candidate_search_start_index = search_start_index
        for entry_block in entry_blocks:
            for markdown_index in range(candidate_search_start_index, len(markdown_blocks)):
                if markdown_blocks[markdown_index].normalized_text == entry_block.normalized_text:
                    matched_indexes.append(markdown_index)
                    candidate_search_start_index = markdown_index + 1
                    break
            else:
                matched_indexes = []
                break

        if matched_indexes:
            target_indexes_by_registry_index[registry_index] = matched_indexes
            search_start_index = candidate_search_start_index

    if not target_indexes_by_registry_index:
        return registry_entries

    for registry_index, target_indexes in target_indexes_by_registry_index.items():
        registry_entries[registry_index]["target_paragraph_indexes"] = target_indexes
    return registry_entries


def _cleanup_block_index(block_id: object) -> int | None:
    if not isinstance(block_id, str):
        return None
    match = re.fullmatch(r"b_(\d{6})", block_id.strip())
    if match is None:
        return None
    return int(match.group(1))


def _append_reader_cleanup_lineage_operation(entry: dict[str, object], operation_name: str) -> None:
    lineage_operations = entry.get("reader_cleanup_operations")
    if not isinstance(lineage_operations, list):
        lineage_operations = []
        entry["reader_cleanup_operations"] = lineage_operations
    lineage_operations.append(operation_name)


def _registry_entry_paragraph_ids(entry: Mapping[str, object] | None) -> list[str]:
    if not isinstance(entry, Mapping):
        return []
    paragraph_ids: list[str] = []
    paragraph_id = entry.get("paragraph_id")
    if isinstance(paragraph_id, str) and paragraph_id.strip():
        paragraph_ids.append(paragraph_id.strip())
    merged_ids = entry.get("merged_paragraph_ids")
    if isinstance(merged_ids, Sequence) and not isinstance(merged_ids, (str, bytes, bytearray)):
        paragraph_ids.extend(str(value).strip() for value in merged_ids if str(value).strip())
    deduped: list[str] = []
    for paragraph_id_value in paragraph_ids:
        if paragraph_id_value not in deduped:
            deduped.append(paragraph_id_value)
    return deduped


def _dedupe_paragraph_ids(paragraph_ids: Sequence[object]) -> list[str]:
    deduped: list[str] = []
    for value in paragraph_ids:
        if not isinstance(value, str) or not value.strip():
            continue
        paragraph_id = value.strip()
        if paragraph_id not in deduped:
            deduped.append(paragraph_id)
    return deduped


def _build_reader_cleanup_block_identity_metadata(
    *,
    raw_markdown: str,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> tuple[dict[int, dict[str, object]], dict[str, object]]:
    """Build diagnostic-only cleanup block identity metadata.

    The metadata is deliberately not serialized into the model cleanup payload.
    It lets the pipeline measure whether stable paragraph ids are available for
    post-cleanup stitching while keeping reader-facing Markdown and prompt
    behavior unchanged.
    """
    if not generated_paragraph_registry:
        return {}, {"status": "skipped", "reason": "missing_generated_paragraph_registry"}

    raw_blocks = build_cleanup_blocks(raw_markdown)
    if not raw_blocks:
        return {}, {"status": "skipped", "reason": "missing_raw_cleanup_blocks"}

    registry_entries = [dict(entry) for entry in generated_paragraph_registry if isinstance(entry, Mapping)]
    metadata_by_index: dict[int, dict[str, object]] = {}
    raw_index = 0
    gap_indexes: list[int] = []
    matched_count = 0
    missing_id_count = 0
    failure_reason = ""

    def _normalized_registry_entry_text(entry: Mapping[str, object]) -> str:
        text = str(entry.get("text") or "").strip()
        blocks = build_cleanup_blocks(text)
        if len(blocks) != 1:
            return re.sub(r"\s+", " ", text).strip()
        return blocks[0].normalized_text

    for entry in registry_entries:
        expected_text = _normalized_registry_entry_text(entry)
        while raw_index < len(raw_blocks) and raw_blocks[raw_index].normalized_text != expected_text:
            gap_indexes.append(raw_index)
            raw_index += 1
        if raw_index >= len(raw_blocks):
            failure_reason = "registry_text_not_found_in_raw_order"
            break

        paragraph_ids = _registry_entry_paragraph_ids(entry)
        if paragraph_ids:
            metadata: dict[str, object] = {"paragraph_id": paragraph_ids[0]}
            if len(paragraph_ids) > 1:
                metadata["merged_paragraph_ids"] = paragraph_ids
            metadata_by_index[raw_index] = metadata
            matched_count += 1
        else:
            missing_id_count += 1
        raw_index += 1

    if not failure_reason and raw_index < len(raw_blocks):
        gap_indexes.extend(range(raw_index, len(raw_blocks)))

    image_gap_count = sum(
        1 for index in gap_indexes if _DOCX_IMAGE_PLACEHOLDER_PATTERN.fullmatch(raw_blocks[index].normalized_text)
    )
    text_gap_count = len(gap_indexes) - image_gap_count
    status = "available" if matched_count else "skipped"
    reason = None
    if failure_reason:
        status = "partial"
        reason = failure_reason
    elif not matched_count:
        reason = "no_registry_entries_with_paragraph_ids"

    diagnostics: dict[str, object] = {
        "status": status,
        "reason": reason,
        "raw_cleanup_block_count": len(raw_blocks),
        "generated_registry_count": len(registry_entries),
        "id_matched_block_count": matched_count,
        "missing_id_registry_entry_count": missing_id_count,
        "gap_count": len(gap_indexes),
        "image_gap_count": image_gap_count,
        "text_gap_count": text_gap_count,
    }
    return metadata_by_index, diagnostics


def _derive_reader_cleanup_generated_paragraph_registry(
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
    cleanup_report: Mapping[str, object],
    raw_markdown: str,
    cleanup_block_metadata_by_index: Mapping[int, Mapping[str, object]] | None = None,
) -> tuple[list[dict[str, object]] | None, dict[str, object]]:
    """Return a best-effort formatting registry that mirrors accepted cleanup.

    The contract is intentionally conservative: block ids are positional
    `build_cleanup_blocks()` ids, so we only rewrite the registry when the raw
    cleanup block count exactly matches the registry entry count. A second
    bounded path allows sparse registry alignment only when registry entries
    exact-match raw cleanup blocks in order and every skipped raw block is a
    DOCX image placeholder. Otherwise the caller keeps the original registry
    and formatting diagnostics can report the mismatch instead of receiving
    guessed lineage.
    """
    if not generated_paragraph_registry:
        return None, {"status": "skipped", "reason": "missing_generated_paragraph_registry"}

    registry_entries = [dict(entry) for entry in generated_paragraph_registry if isinstance(entry, Mapping)]
    raw_blocks = build_cleanup_blocks(raw_markdown, block_metadata_by_index=cleanup_block_metadata_by_index)
    raw_block_count = len(raw_blocks)
    if not raw_blocks:
        return registry_entries, {
            "status": "skipped",
            "reason": "missing_raw_cleanup_blocks",
        }

    def _normalized_registry_entry_text(entry: Mapping[str, object]) -> str:
        text = str(entry.get("text") or "").strip()
        blocks = build_cleanup_blocks(text)
        if len(blocks) != 1:
            return re.sub(r"\s+", " ", text).strip()
        return blocks[0].normalized_text

    registry_entry_count = len(registry_entries)
    alignment_gap_count = 0
    alignment_mode = "positional"
    if raw_block_count == registry_entry_count:
        mutable_entries: list[dict[str, object] | None] = list(registry_entries)
    else:
        mutable_entries = [None] * raw_block_count
        identity_alignment_gap_count = 0
        identity_alignment_failed = True
        identity_alignment_failure_reason = ""
        if cleanup_block_metadata_by_index:
            registry_indexes_by_paragraph_id: dict[str, list[int]] = {}
            for registry_index, entry in enumerate(registry_entries):
                for paragraph_id in _registry_entry_paragraph_ids(entry):
                    registry_indexes_by_paragraph_id.setdefault(paragraph_id, []).append(registry_index)

            used_registry_indexes: set[int] = set()
            identity_gap_indexes: list[int] = []
            identity_mutable_entries: list[dict[str, object] | None] = [None] * raw_block_count
            ambiguous_identity_match = False
            for raw_index, raw_block in enumerate(raw_blocks):
                block_paragraph_ids = _dedupe_paragraph_ids(
                    [raw_block.paragraph_id, *raw_block.merged_paragraph_ids]
                )
                matched_registry_indexes = {
                    registry_index
                    for paragraph_id in block_paragraph_ids
                    for registry_index in registry_indexes_by_paragraph_id.get(paragraph_id, [])
                }
                matched_registry_indexes -= used_registry_indexes
                if len(matched_registry_indexes) == 1:
                    matched_registry_index = next(iter(matched_registry_indexes))
                    identity_mutable_entries[raw_index] = registry_entries[matched_registry_index]
                    used_registry_indexes.add(matched_registry_index)
                    continue
                if len(matched_registry_indexes) > 1:
                    ambiguous_identity_match = True
                    break
                identity_gap_indexes.append(raw_index)

            if ambiguous_identity_match:
                identity_alignment_failure_reason = "ambiguous_paragraph_id_alignment"
            elif len(used_registry_indexes) != registry_entry_count:
                identity_alignment_failure_reason = "not_all_registry_entries_matched_by_paragraph_id"
            else:
                identity_alignment_gap_count = len(identity_gap_indexes)
                non_image_gap_indexes = [
                    index
                    for index in identity_gap_indexes
                    if not _DOCX_IMAGE_PLACEHOLDER_PATTERN.fullmatch(raw_blocks[index].normalized_text)
                ]
                if non_image_gap_indexes:
                    identity_alignment_failure_reason = "non_image_placeholder_identity_gaps"
                else:
                    mutable_entries = identity_mutable_entries
                    alignment_gap_count = identity_alignment_gap_count
                    alignment_mode = "identity_sparse_image_placeholders"
                    identity_alignment_failed = False

        if not identity_alignment_failed:
            pass
        else:
            mutable_entries = [None] * raw_block_count
            sparse_alignment_failed = False
            sparse_alignment_failure_reason = identity_alignment_failure_reason
            raw_index = 0

            gap_indexes: list[int] = []
            for entry in registry_entries:
                expected_text = _normalized_registry_entry_text(entry)
                while raw_index < raw_block_count and raw_blocks[raw_index].normalized_text != expected_text:
                    gap_indexes.append(raw_index)
                    raw_index += 1
                if raw_index >= raw_block_count:
                    sparse_alignment_failed = True
                    sparse_alignment_failure_reason = "registry_text_not_found_in_raw_order"
                    break
                mutable_entries[raw_index] = entry
                raw_index += 1
            if not sparse_alignment_failed and raw_index < raw_block_count:
                gap_indexes.extend(range(raw_index, raw_block_count))

            if not sparse_alignment_failed:
                alignment_gap_count = len(gap_indexes)
                non_image_gap_indexes = [
                    index
                    for index in gap_indexes
                    if not _DOCX_IMAGE_PLACEHOLDER_PATTERN.fullmatch(raw_blocks[index].normalized_text)
                ]
                sparse_alignment_failed = bool(non_image_gap_indexes)
                if sparse_alignment_failed:
                    sparse_alignment_failure_reason = "non_image_placeholder_registry_gaps"

            if sparse_alignment_failed:
                return registry_entries, {
                    "status": "skipped",
                    "reason": "cleanup_block_registry_count_mismatch",
                    "sparse_alignment_failure_reason": sparse_alignment_failure_reason or "unknown",
                    "alignment_gap_count": alignment_gap_count,
                    "raw_cleanup_block_count": raw_block_count,
                    "generated_registry_count": registry_entry_count,
                }
            alignment_mode = "sparse_image_placeholders"

    accepted_operations = cleanup_report.get("accepted_cleanup_operations") or []
    if not isinstance(accepted_operations, Sequence) or isinstance(accepted_operations, (str, bytes, bytearray)):
        return registry_entries, {"status": "unchanged", "reason": "missing_accepted_cleanup_operations"}

    applied_operations = 0
    deleted_entries = 0
    joined_entries = 0
    updated_entries = 0
    skipped_operations = 0

    for raw_operation in accepted_operations:
        if not isinstance(raw_operation, Mapping):
            skipped_operations += 1
            continue

        pass_name = str(raw_operation.get("pass_name") or "").strip()
        if pass_name and pass_name != "first_pass":
            skipped_operations += 1
            continue

        operation_name = str(raw_operation.get("operation") or "").strip()
        block_index = _cleanup_block_index(raw_operation.get("id"))
        if block_index is None or block_index >= len(mutable_entries):
            skipped_operations += 1
            continue
        current_entry = mutable_entries[block_index]
        if current_entry is None:
            skipped_operations += 1
            continue

        if operation_name == "delete_block":
            mutable_entries[block_index] = None
            applied_operations += 1
            deleted_entries += 1
            continue

        if operation_name == "join_fragmented_paragraph":
            next_index = _cleanup_block_index(raw_operation.get("next_id"))
            if next_index is None or next_index != block_index + 1 or next_index >= len(mutable_entries):
                skipped_operations += 1
                continue
            next_entry = mutable_entries[next_index]
            if next_entry is None:
                skipped_operations += 1
                continue
            expected_after_preview = str(raw_operation.get("expected_after_preview") or "").strip()
            current_text = str(current_entry.get("text") or "").strip()
            next_text = str(next_entry.get("text") or "").strip()
            current_entry["text"] = expected_after_preview or f"{current_text} {next_text}".strip()
            merged_ids = _registry_entry_paragraph_ids(current_entry) + _registry_entry_paragraph_ids(next_entry)
            if merged_ids:
                current_entry["paragraph_id"] = merged_ids[0]
                if len(merged_ids) > 1:
                    current_entry["merged_paragraph_ids"] = merged_ids
            _append_reader_cleanup_lineage_operation(current_entry, operation_name)
            mutable_entries[next_index] = None
            applied_operations += 1
            joined_entries += 1
            continue

        if operation_name in {
            "remove_inline_noise",
            "extract_side_heading_and_reattach_body",
            "split_block",
            "normalize_heading_boundary",
        }:
            replacement_text = str(raw_operation.get("expected_after_preview") or "").strip()
            if not replacement_text and operation_name == "split_block":
                split_substrings = raw_operation.get("split_substrings")
                if isinstance(split_substrings, Sequence) and not isinstance(split_substrings, (str, bytes, bytearray)):
                    replacement_text = "\n\n".join(str(value).strip() for value in split_substrings if str(value).strip())
            if not replacement_text:
                skipped_operations += 1
                continue
            current_entry["text"] = replacement_text
            _append_reader_cleanup_lineage_operation(current_entry, operation_name)
            applied_operations += 1
            updated_entries += 1
            continue

        skipped_operations += 1

    derived_registry = [entry for entry in mutable_entries if entry is not None]
    return derived_registry, {
        "status": "derived",
        "alignment_mode": alignment_mode,
        "alignment_gap_count": alignment_gap_count,
        "raw_cleanup_block_count": raw_block_count,
        "original_registry_count": registry_entry_count,
        "derived_registry_count": len(derived_registry),
        "applied_operation_count": applied_operations,
        "deleted_registry_entry_count": deleted_entries,
        "joined_registry_entry_count": joined_entries,
        "updated_registry_entry_count": updated_entries,
        "skipped_operation_count": skipped_operations,
    }


def _build_docx_rebuild_markdown_after_reader_cleanup(
    *,
    raw_markdown: str,
    cleaned_markdown: str,
    accepted_delete_block_ids: Sequence[str],
    cleanup_block_metadata_by_index: Mapping[int, Mapping[str, object]] | None = None,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> str:
    raw_blocks = build_cleanup_blocks(raw_markdown, block_metadata_by_index=cleanup_block_metadata_by_index)
    if not raw_blocks:
        return cleaned_markdown

    accepted_delete_ids = {str(block_id) for block_id in accepted_delete_block_ids if str(block_id).strip()}
    deleted_docx_image_placeholder_ids = {
        block.block_id
        for block in raw_blocks
        if block.block_id in accepted_delete_ids and _DOCX_IMAGE_PLACEHOLDER_PATTERN.fullmatch(block.normalized_text)
    }
    missing_docx_image_placeholder_blocks = [
        (index, block)
        for index, block in enumerate(raw_blocks)
        if _DOCX_IMAGE_PLACEHOLDER_PATTERN.fullmatch(block.normalized_text)
        and block.normalized_text not in cleaned_markdown
    ]
    if not deleted_docx_image_placeholder_ids and not missing_docx_image_placeholder_blocks:
        return cleaned_markdown

    if deleted_docx_image_placeholder_ids:
        rebuilt_blocks = [
            block.text
            for block in raw_blocks
            if block.block_id not in accepted_delete_ids or block.block_id in deleted_docx_image_placeholder_ids
        ]
        rebuilt_markdown = "\n\n".join(rebuilt_blocks)
        return rebuilt_markdown if rebuilt_markdown.strip() else cleaned_markdown

    cleaned_blocks = [block.text for block in build_cleanup_blocks(cleaned_markdown)]
    if not cleaned_blocks:
        cleaned_blocks = [block.text for _, block in missing_docx_image_placeholder_blocks]
        return "\n\n".join(cleaned_blocks)

    def _find_cleaned_block_index(raw_normalized_text: str) -> int | None:
        for cleaned_index, cleaned_block in enumerate(build_cleanup_blocks("\n\n".join(cleaned_blocks))):
            if cleaned_block.normalized_text == raw_normalized_text:
                return cleaned_index
        return None

    cleaned_index_range_by_paragraph_id: dict[str, tuple[int, int]] = {}
    if generated_paragraph_registry:
        cleaned_cleanup_blocks = build_cleanup_blocks("\n\n".join(cleaned_blocks))
        search_start_index = 0
        for entry in generated_paragraph_registry:
            if not isinstance(entry, Mapping):
                continue
            paragraph_ids = _registry_entry_paragraph_ids(entry)
            if not paragraph_ids:
                continue
            entry_text = str(entry.get("text") or "").strip()
            entry_blocks = build_cleanup_blocks(entry_text)
            if not entry_blocks:
                continue

            matched_indexes: list[int] = []
            for entry_block in entry_blocks:
                for cleaned_index in range(search_start_index, len(cleaned_cleanup_blocks)):
                    if cleaned_cleanup_blocks[cleaned_index].normalized_text == entry_block.normalized_text:
                        matched_indexes.append(cleaned_index)
                        search_start_index = cleaned_index + 1
                        break
                else:
                    matched_indexes = []
                    break
            if not matched_indexes:
                continue
            index_range = (matched_indexes[0], matched_indexes[-1])
            for paragraph_id in paragraph_ids:
                cleaned_index_range_by_paragraph_id.setdefault(paragraph_id, index_range)

    def _find_cleaned_block_index_by_identity(raw_block: Any, *, side: str) -> int | None:
        paragraph_ids = _dedupe_paragraph_ids([raw_block.paragraph_id, *raw_block.merged_paragraph_ids])
        for paragraph_id in paragraph_ids:
            index_range = cleaned_index_range_by_paragraph_id.get(paragraph_id)
            if index_range is None:
                continue
            return index_range[1] if side == "previous" else index_range[0]
        return None

    inserted_placeholders: set[str] = set()
    for raw_index, image_block in missing_docx_image_placeholder_blocks:
        placeholder_text = image_block.text.strip()
        if not placeholder_text or placeholder_text in inserted_placeholders:
            continue
        if any(placeholder_text in block for block in cleaned_blocks):
            continue

        insertion_index: int | None = None
        for previous_block in reversed(raw_blocks[:raw_index]):
            if _DOCX_IMAGE_PLACEHOLDER_PATTERN.fullmatch(previous_block.normalized_text):
                if previous_block.normalized_text in inserted_placeholders:
                    for cleaned_index, cleaned_block in enumerate(cleaned_blocks):
                        if previous_block.normalized_text in cleaned_block:
                            insertion_index = cleaned_index + 1
                            break
                    if insertion_index is not None:
                        break
                continue
            previous_index = _find_cleaned_block_index_by_identity(previous_block, side="previous")
            if previous_index is None:
                previous_index = _find_cleaned_block_index(previous_block.normalized_text)
            if previous_index is not None:
                insertion_index = previous_index + 1
                break
        if insertion_index is None:
            for next_block in raw_blocks[raw_index + 1 :]:
                if _DOCX_IMAGE_PLACEHOLDER_PATTERN.fullmatch(next_block.normalized_text):
                    continue
                next_index = _find_cleaned_block_index_by_identity(next_block, side="next")
                if next_index is None:
                    next_index = _find_cleaned_block_index(next_block.normalized_text)
                if next_index is not None:
                    insertion_index = next_index
                    break
        if insertion_index is None:
            insertion_index = len(cleaned_blocks)

        cleaned_blocks.insert(insertion_index, placeholder_text)
        inserted_placeholders.add(placeholder_text)

    rebuilt_markdown = "\n\n".join(block for block in cleaned_blocks if block.strip())
    return rebuilt_markdown if rebuilt_markdown.strip() else cleaned_markdown


def _write_reader_cleanup_lineage_artifact(
    *,
    filename: str,
    raw_markdown: str,
    cleaned_markdown: str,
    cleanup_report: Mapping[str, object],
    active_formatting_registry: Sequence[Mapping[str, object]] | None,
    cleanup_identity_metadata: Mapping[int, Mapping[str, object]],
    cleanup_identity_diagnostics: Mapping[str, object],
    cleanup_formatting_registry: Sequence[Mapping[str, object]] | None,
    cleanup_formatting_lineage: Mapping[str, object],
) -> str | None:
    generated_at_epoch_ms = int(time.time() * 1000)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename or "reader_cleanup").strip("._") or "reader_cleanup"
    payload = {
        "schema_version": 1,
        "stage": "reader_cleanup_lineage",
        "generated_at_epoch_ms": generated_at_epoch_ms,
        "filename": filename,
        "raw_markdown": raw_markdown,
        "cleaned_markdown": cleaned_markdown,
        "cleanup_report": dict(cleanup_report),
        "active_formatting_registry": [dict(entry) for entry in active_formatting_registry or []],
        "cleanup_identity_metadata": {str(index): dict(metadata) for index, metadata in cleanup_identity_metadata.items()},
        "cleanup_identity_diagnostics": dict(cleanup_identity_diagnostics),
        "cleanup_formatting_registry": [dict(entry) for entry in cleanup_formatting_registry or []],
        "cleanup_formatting_lineage": dict(cleanup_formatting_lineage),
    }
    try:
        READER_CLEANUP_LINEAGE_DIR.mkdir(parents=True, exist_ok=True)
        artifact_path = READER_CLEANUP_LINEAGE_DIR / f"{safe_name}_{generated_at_epoch_ms}.json"
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_artifact_dir(
            target_dir=READER_CLEANUP_LINEAGE_DIR,
            max_age_seconds=READER_CLEANUP_LINEAGE_MAX_AGE_SECONDS,
            max_count=READER_CLEANUP_LINEAGE_MAX_COUNT,
            emit_log=False,
        )
        return str(artifact_path)
    except Exception:
        return None


def _run_reader_cleanup_postprocess(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    cleanup_input_markdown: str,
    runtime_display_markdown: str,
    base_docx_bytes: bytes | None,
    job_count: int,
    processed_image_assets: Sequence[Any],
    formatting_registry: Sequence[Mapping[str, object]] | None = None,
    base_docx_builder: Callable[[], bytes] | None = None,
) -> ReaderCleanupPostprocessResult:
    def _base_docx_bytes() -> bytes:
        if base_docx_bytes is not None:
            return base_docx_bytes
        if base_docx_builder is not None:
            return base_docx_builder()
        return b""

    active_formatting_registry = formatting_registry or state.generated_paragraph_registry or None
    base_final_generated_registry = _resolve_final_generated_paragraph_registry(
        markdown_text=runtime_display_markdown,
        generated_paragraph_registry=active_formatting_registry,
    )

    if not _should_run_reader_cleanup(context=context):
        return ReaderCleanupPostprocessResult(
            markdown=runtime_display_markdown,
            docx_bytes=_base_docx_bytes(),
            report=None,
            raw_markdown=None,
            result_notice=None,
            final_generated_paragraph_registry=base_final_generated_registry,
        )

    config = resolve_reader_cleanup_config(app_config=context.app_config, fallback_model=context.model)
    if not config.enabled:
        return ReaderCleanupPostprocessResult(
            markdown=runtime_display_markdown,
            docx_bytes=_base_docx_bytes(),
            report=None,
            raw_markdown=None,
            result_notice=None,
            final_generated_paragraph_registry=base_final_generated_registry,
        )
    if config.drop_back_matter:
        dependencies.log_event(
            logging.WARNING,
            "reader_cleanup_drop_back_matter_unsupported",
            "Reader cleanup drop_back_matter is currently unsupported; proceeding without semantic back-matter deletion.",
            filename=context.uploaded_filename,
            policy=config.policy,
            model=config.model,
        )

    system_prompt = build_reader_cleanup_system_prompt()
    schema_repair_system_prompt = build_reader_cleanup_schema_repair_system_prompt()
    global_plan_system_prompt = build_reader_cleanup_global_plan_system_prompt()
    fallback_client = None
    if not callable(getattr(dependencies, "resolve_model_selector", None)) or not callable(
        getattr(dependencies, "get_client_for_model_selector", None)
    ):
        fallback_client = dependencies.get_client()
    client, model_id, model_selector, model_provider = _resolve_text_call_target(
        selector=config.model,
        context=context,
        dependencies=dependencies,
        fallback_client=fallback_client,
    )

    emitters.emit_activity(context.runtime, "Запущен reader cleanup post-pass для итогового Markdown.")
    cleanup_identity_metadata, cleanup_identity_diagnostics = _build_reader_cleanup_block_identity_metadata(
        raw_markdown=cleanup_input_markdown,
        generated_paragraph_registry=active_formatting_registry,
    )

    def _global_plan_provider(request_payload: Mapping[str, object]) -> str:
        target_text = json.dumps(request_payload, ensure_ascii=False, indent=2)
        started_at = time.perf_counter()
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_global_plan_started",
            "Запущен advisory global reader cleanup plan для полного raw Markdown.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": "reader_cleanup_global_plan"},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            target_chars=len(target_text),
        )
        response = dependencies.generate_markdown_block(
            client=client,
            model=model_id,
            system_prompt=global_plan_system_prompt,
            target_text=target_text,
            context_before="",
            context_after="",
            max_retries=context.max_retries,
            expected_paragraph_ids=None,
            marker_mode=False,
        )
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_global_plan_completed",
            "Advisory global reader cleanup plan завершён.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": "reader_cleanup_global_plan"},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            output_chars=len(response),
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        return response

    def _operation_provider(request_payload: Mapping[str, object], chunk_index: int, chunk_count: int) -> str:
        target_text = json.dumps(request_payload, ensure_ascii=False, indent=2)
        context_before = str(request_payload.get("context_before_preview", "") or "")
        context_after = str(request_payload.get("context_after_preview", "") or "")
        pass_name = str(request_payload.get("pass_name") or "reader_cleanup")
        started_at = time.perf_counter()
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_chunk_started",
            "Запущен reader cleanup post-pass для cleanup chunk.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": pass_name},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            target_chars=len(target_text),
            context_before_chars=len(context_before),
            context_after_chars=len(context_after),
        )
        response = dependencies.generate_markdown_block(
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
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_chunk_completed",
            "Reader cleanup post-pass для cleanup chunk завершён.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": pass_name},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            output_chars=len(response),
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        return response

    def _repair_provider(request_payload: Mapping[str, object], chunk_index: int, chunk_count: int) -> str:
        target_text = json.dumps(request_payload, ensure_ascii=False, indent=2)
        started_at = time.perf_counter()
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_schema_repair_started",
            "Запущен schema-repair retry для cleanup chunk.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": "reader_cleanup_schema_repair"},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            target_chars=len(target_text),
        )
        response = dependencies.generate_markdown_block(
            client=client,
            model=model_id,
            system_prompt=schema_repair_system_prompt,
            target_text=target_text,
            context_before="",
            context_after="",
            max_retries=context.max_retries,
            expected_paragraph_ids=None,
            marker_mode=False,
        )
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_schema_repair_completed",
            "Schema-repair retry для cleanup chunk завершён.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": "reader_cleanup_schema_repair"},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            output_chars=len(response),
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        return response

    anchor_targets = _resolve_reader_cleanup_anchor_repair_targets(context=context)

    try:
        cleanup_result = run_reader_cleanup(
            markdown_text=cleanup_input_markdown,
            config=config,
            operation_provider=_operation_provider,
            repair_provider=_repair_provider,
            global_plan_provider=_global_plan_provider,
            anchor_operation_provider=_operation_provider if anchor_targets else None,
            anchor_targets=anchor_targets,
            model_resolution={
                "requested_selector": config.model,
                "canonical_selector": model_selector,
                "provider": model_provider,
                "model_id": model_id,
            },
            block_metadata_by_index=cleanup_identity_metadata,
        )
        if not cleanup_result.changed:
            runtime_display_markdown = _restore_image_heading_lines_from_registry(
                runtime_display_markdown,
                base_final_generated_registry,
            )
            base_final_generated_registry = _resolve_final_generated_paragraph_registry(
                markdown_text=runtime_display_markdown,
                generated_paragraph_registry=active_formatting_registry,
            )
            stats = cast(Mapping[str, object], cleanup_result.report_payload.get("stats") or {})
            dependencies.log_event(
                logging.INFO,
                "reader_cleanup_noop",
                "Reader cleanup post-pass завершён без принятых удалений.",
                filename=context.uploaded_filename,
                policy=config.policy,
                model=config.model,
                warnings=list(cleanup_result.report_payload.get("warnings", []) or []),
                cleanup_chunk_count=stats.get("cleanup_chunk_count"),
                failed_chunk_count=stats.get("failed_chunk_count"),
                proposed_delete_block_count=stats.get("proposed_delete_block_count"),
                ignored_delete_block_count=stats.get("ignored_delete_block_count"),
                cleanup_identity_status=cleanup_identity_diagnostics.get("status"),
                cleanup_identity_reason=cleanup_identity_diagnostics.get("reason"),
                cleanup_identity_id_matched_block_count=cleanup_identity_diagnostics.get("id_matched_block_count"),
                cleanup_identity_gap_count=cleanup_identity_diagnostics.get("gap_count"),
                cleanup_identity_image_gap_count=cleanup_identity_diagnostics.get("image_gap_count"),
                cleanup_identity_text_gap_count=cleanup_identity_diagnostics.get("text_gap_count"),
            )
            return ReaderCleanupPostprocessResult(
                markdown=runtime_display_markdown,
                docx_bytes=_base_docx_bytes(),
                report=cleanup_result.report_payload,
                raw_markdown=cleanup_result.raw_markdown,
                result_notice=None,
                final_generated_paragraph_registry=base_final_generated_registry,
            )

        cleanup_formatting_registry, cleanup_formatting_lineage = _derive_reader_cleanup_generated_paragraph_registry(
            generated_paragraph_registry=active_formatting_registry,
            cleanup_report=cleanup_result.report_payload,
            raw_markdown=cleanup_result.raw_markdown,
            cleanup_block_metadata_by_index=cleanup_identity_metadata,
        )
        cleaned_runtime_display_markdown = _restore_image_heading_lines_from_registry(
            _normalize_final_markdown_for_runtime_display(cleanup_result.cleaned_markdown),
            cleanup_formatting_registry,
        )
        docx_rebuild_markdown = _build_docx_rebuild_markdown_after_reader_cleanup(
            raw_markdown=cleanup_result.raw_markdown,
            cleaned_markdown=cleaned_runtime_display_markdown,
            accepted_delete_block_ids=cleanup_result.accepted_delete_block_ids,
            cleanup_block_metadata_by_index=cleanup_identity_metadata,
            generated_paragraph_registry=cleanup_formatting_registry,
        )
        preliminary_final_generated_registry = _resolve_final_generated_paragraph_registry(
            markdown_text=docx_rebuild_markdown,
            generated_paragraph_registry=cleanup_formatting_registry,
        )
        docx_rebuild_markdown = _restore_image_heading_lines_from_registry(
            docx_rebuild_markdown,
            preliminary_final_generated_registry,
        )
        cleaned_runtime_display_markdown = _restore_image_heading_lines_from_registry(
            cleaned_runtime_display_markdown,
            preliminary_final_generated_registry,
        )
        cleanup_lineage_artifact_path = _write_reader_cleanup_lineage_artifact(
            filename=context.uploaded_filename,
            raw_markdown=cleanup_result.raw_markdown,
            cleaned_markdown=cleaned_runtime_display_markdown,
            cleanup_report=cleanup_result.report_payload,
            active_formatting_registry=active_formatting_registry,
            cleanup_identity_metadata=cleanup_identity_metadata,
            cleanup_identity_diagnostics=cleanup_identity_diagnostics,
            cleanup_formatting_registry=cleanup_formatting_registry,
            cleanup_formatting_lineage=cleanup_formatting_lineage,
        )
        cleaned_docx_bytes = _rebuild_docx_for_markdown(
            markdown_text=docx_rebuild_markdown,
            context=context,
            dependencies=dependencies,
            state=state,
            processed_image_assets=processed_image_assets,
            generated_paragraph_registry=preliminary_final_generated_registry,
        )
        final_generated_registry = _resolve_final_generated_paragraph_registry(
            markdown_text=docx_rebuild_markdown,
            generated_paragraph_registry=preliminary_final_generated_registry,
        )
        emitters.emit_state(
            context.runtime,
            final_generated_paragraph_registry=final_generated_registry,
            latest_markdown=cleaned_runtime_display_markdown,
            latest_docx_bytes=cleaned_docx_bytes,
        )
        stats = cast(Mapping[str, object], cleanup_result.report_payload.get("stats") or {})
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_applied",
            "Reader cleanup post-pass применил bounded cleanup operations к итоговому Markdown.",
            filename=context.uploaded_filename,
            policy=config.policy,
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            accepted_delete_block_count=len(cleanup_result.accepted_delete_block_ids),
            accepted_cleanup_operation_count=stats.get("accepted_cleanup_operation_count"),
            ignored_delete_block_count=stats.get("ignored_delete_block_count"),
            ignored_cleanup_operation_count=stats.get("ignored_cleanup_operation_count"),
            proposed_delete_block_count=stats.get("proposed_delete_block_count"),
            proposed_cleanup_operation_count=stats.get("proposed_cleanup_operation_count"),
            cleanup_chunk_count=stats.get("cleanup_chunk_count"),
            failed_chunk_count=stats.get("failed_chunk_count"),
            formatting_lineage_status=cleanup_formatting_lineage.get("status"),
            formatting_lineage_reason=cleanup_formatting_lineage.get("reason"),
            formatting_lineage_sparse_alignment_failure_reason=cleanup_formatting_lineage.get("sparse_alignment_failure_reason"),
            formatting_lineage_alignment_mode=cleanup_formatting_lineage.get("alignment_mode"),
            formatting_lineage_alignment_gap_count=cleanup_formatting_lineage.get("alignment_gap_count"),
            formatting_lineage_raw_cleanup_block_count=cleanup_formatting_lineage.get("raw_cleanup_block_count"),
            formatting_lineage_generated_registry_count=cleanup_formatting_lineage.get("generated_registry_count")
            or cleanup_formatting_lineage.get("original_registry_count"),
            formatting_lineage_derived_registry_count=cleanup_formatting_lineage.get("derived_registry_count"),
            formatting_lineage_applied_operation_count=cleanup_formatting_lineage.get("applied_operation_count"),
            cleanup_identity_status=cleanup_identity_diagnostics.get("status"),
            cleanup_identity_reason=cleanup_identity_diagnostics.get("reason"),
            cleanup_identity_raw_cleanup_block_count=cleanup_identity_diagnostics.get("raw_cleanup_block_count"),
            cleanup_identity_generated_registry_count=cleanup_identity_diagnostics.get("generated_registry_count"),
            cleanup_identity_id_matched_block_count=cleanup_identity_diagnostics.get("id_matched_block_count"),
            cleanup_identity_missing_id_registry_entry_count=cleanup_identity_diagnostics.get("missing_id_registry_entry_count"),
            cleanup_identity_gap_count=cleanup_identity_diagnostics.get("gap_count"),
            cleanup_identity_image_gap_count=cleanup_identity_diagnostics.get("image_gap_count"),
            cleanup_identity_text_gap_count=cleanup_identity_diagnostics.get("text_gap_count"),
            reader_cleanup_lineage_artifact_path=cleanup_lineage_artifact_path,
            cleaned_markdown_chars=len(cleaned_runtime_display_markdown),
            raw_markdown_chars=len(cleanup_result.raw_markdown),
        )
        return ReaderCleanupPostprocessResult(
            markdown=cleaned_runtime_display_markdown,
            docx_bytes=cleaned_docx_bytes,
            report=cleanup_result.report_payload,
            raw_markdown=cleanup_result.raw_markdown,
            result_notice=None,
            final_generated_paragraph_registry=final_generated_registry,
        )
    except Exception as exc:
        error_message = dependencies.present_error(
            "reader_cleanup_failed",
            exc,
            "Ошибка reader cleanup post-pass",
            filename=context.uploaded_filename,
            processing_operation=context.processing_operation,
        )
        strict_report = exc.report_payload if isinstance(exc, ReaderCleanupStageError) else None
        strict_raw_markdown = exc.raw_markdown if isinstance(exc, ReaderCleanupStageError) else cleanup_input_markdown
        result_notice: dict[str, str] | None = None
        if config.policy == "strict":
            result_notice = {
                "level": "warning",
                "message": "Reader cleanup strict stage failed; preserved the raw translated result without cleanup.",
            }
            dependencies.log_event(
                logging.WARNING,
                "reader_cleanup_strict_failed_base_result_preserved",
                "Reader cleanup strict stage failed; base DOCX/Markdown result is preserved.",
                filename=context.uploaded_filename,
                processing_operation=context.processing_operation,
                policy=config.policy,
                error_message=str(exc),
                report_stage_status=(strict_report or {}).get("stage_status") if isinstance(strict_report, Mapping) else None,
            )
        else:
            dependencies.log_event(
                logging.WARNING,
                "reader_cleanup_failed_base_result_preserved",
                "Reader cleanup post-pass failed; base DOCX/Markdown result is preserved.",
                filename=context.uploaded_filename,
                processing_operation=context.processing_operation,
                policy=config.policy,
                error_message=str(exc),
            )
        emitters.emit_state(
            context.runtime,
            final_generated_paragraph_registry=base_final_generated_registry,
            latest_docx_bytes=_base_docx_bytes(),
            latest_markdown=runtime_display_markdown,
            latest_narration_text=None,
            latest_result_notice=result_notice,
            last_error=error_message,
        )
        return ReaderCleanupPostprocessResult(
            markdown=runtime_display_markdown,
            docx_bytes=_base_docx_bytes(),
            report=cast(dict[str, object] | None, strict_report),
            raw_markdown=strict_raw_markdown,
            result_notice=result_notice,
            final_generated_paragraph_registry=base_final_generated_registry,
        )


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
    pre_cleanup_formatting_baseline: Mapping[str, object] | None = None,
) -> dict[str, object]:
    normalized_quality_markdown = _normalize_final_markdown_for_quality_gate(final_markdown)
    display_hygiene_markdown = _normalize_final_markdown_for_display_hygiene_reporting(final_markdown)
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
    raw_bullet_heading_samples = collect_bullet_heading_samples(final_markdown)
    bullet_heading_count = len(bullet_heading_samples)
    raw_page_placeholder_heading_concat_samples = collect_page_placeholder_heading_concat_samples(final_markdown)
    page_placeholder_heading_concat_samples = collect_page_placeholder_heading_concat_samples(display_hygiene_markdown)
    assembly_entries = tuple(getattr(assembly_result, "entries", ()) or ())
    assembly_uses_fallback = any(bool(getattr(entry, "used_fallback", False)) for entry in assembly_entries)
    source_backed_entry_authority = _has_source_backed_entry_authority(assembly_entries)
    entry_false_fragment_heading_samples = collect_false_fragment_heading_samples_from_entries(assembly_entries) if assembly_entries else []
    raw_false_fragment_heading_samples = collect_false_fragment_heading_samples(final_markdown)
    raw_residual_bullet_glyph_samples = collect_residual_bullet_glyph_samples(final_markdown)
    residual_bullet_glyph_samples = collect_residual_bullet_glyph_samples(display_hygiene_markdown)
    raw_list_fragment_regression_samples = collect_list_fragment_regression_samples(final_markdown)
    raw_mixed_script_samples = collect_mixed_script_samples(final_markdown)
    mixed_script_samples = list(raw_mixed_script_samples)
    recovered_heading_entries = collect_recovered_heading_entries(assembly_entries) if assembly_entries and not assembly_uses_fallback else []
    translation_domain = str(getattr(context, "translation_domain", "") or context.app_config.get("translation_domain", "general") or "general")
    raw_theology_style_samples = (
        collect_theology_style_issue_samples(normalized_quality_markdown)
        if translation_domain.strip().lower() == "theology"
        else []
    )
    theology_style_samples = list(raw_theology_style_samples)
    authority_fields = _derive_translation_quality_authority_fields(
        context=context,
        final_markdown=final_markdown,
        formatting_payload=latest_payload if isinstance(latest_payload, Mapping) else None,
        assembly_result=assembly_result,
    )
    role_aware_summary = resolve_role_aware_formatting_unmapped_source_summary(payloads)
    role_aware_target_summary = resolve_role_aware_formatting_unmapped_target_summary(payloads)
    authoritative_unmapped_source_basis = str(
        authority_fields.get("unmapped_source_count_basis") or "legacy_paragraph"
    ).strip().lower() or "legacy_paragraph"
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
    if role_aware_summary is not None:
        authority_fields = dict(authority_fields)
        authority_fields["unmapped_source_count_basis"] = "role_aware_formatting_coverage"
        worst_unmapped_source_count = int(role_aware_summary["effective_unmapped_source_count"])
    effective_unmapped_target_count = _effective_authoritative_unmapped_count(
        authority_fields,
        basis_key="unmapped_target_count_basis",
        raw_count_key="raw_unmapped_target_paragraph_count",
        structure_count_key="structure_unit_unmapped_target_count",
    )
    authoritative_unmapped_target_basis = str(
        authority_fields.get("unmapped_target_count_basis") or "legacy_paragraph"
    ).strip().lower() or "legacy_paragraph"
    if role_aware_target_summary is not None and authoritative_unmapped_target_basis not in {
        "topology_unit",
        "accepted_aggregation_legacy",
    }:
        authority_fields = dict(authority_fields)
        authority_fields["unmapped_target_count_basis"] = "role_aware_formatting_coverage"
        authority_fields["raw_unmapped_target_paragraph_count"] = int(
            role_aware_target_summary["raw_unmapped_target_count"]
        )
        effective_unmapped_target_count = int(role_aware_target_summary["effective_unmapped_target_count"])
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
        "filtered_unmapped_source_count": role_aware_summary.get("filtered_unmapped_source_count") if role_aware_summary else None,
        "format_neutral_creditable_count": role_aware_summary.get("format_neutral_creditable_count") if role_aware_summary else 0,
        "effective_unmapped_source_count": role_aware_summary.get("effective_unmapped_source_count") if role_aware_summary else None,
        "target_split_accounting_creditable_count": (
            role_aware_target_summary.get("target_split_accounting_creditable_count")
            if role_aware_target_summary
            else 0
        ),
        "effective_unmapped_target_count": (
            role_aware_target_summary.get("effective_unmapped_target_count")
            if role_aware_target_summary
            else None
        ),
        "raw_unmapped_target_paragraph_count": authority_fields.get("raw_unmapped_target_paragraph_count", len(unmapped_target_indexes) if isinstance(unmapped_target_indexes, list) else 0),
        "structure_unit_total_count": authority_fields.get("structure_unit_total_count"),
        "structure_unit_unmapped_source_count": authority_fields.get("structure_unit_unmapped_source_count"),
        "structure_unit_unmapped_target_count": authority_fields.get("structure_unit_unmapped_target_count"),
        "accepted_aggregated_source_unit_count": authority_fields.get("accepted_aggregated_source_unit_count"),
        "accepted_aggregated_target_index_count": authority_fields.get("accepted_aggregated_target_index_count"),
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
        "bullet_heading_gate_source": "legacy_markdown",
        "bullet_heading_classification": "markdown_gate",
        "raw_bullet_heading_count": len(raw_bullet_heading_samples),
        "bullet_heading_samples": _serialize_quality_samples(bullet_heading_samples),
        "raw_bullet_heading_samples": _serialize_quality_samples(raw_bullet_heading_samples),
        "page_placeholder_heading_concat_count": len(page_placeholder_heading_concat_samples),
        "page_placeholder_heading_concat_samples": _serialize_quality_samples(page_placeholder_heading_concat_samples),
        "page_placeholder_heading_concat_source": "legacy_markdown",
        "page_placeholder_heading_concat_classification": "display_hygiene",
        "raw_page_placeholder_heading_concat_count": len(raw_page_placeholder_heading_concat_samples),
        "raw_page_placeholder_heading_concat_samples": _serialize_quality_samples(raw_page_placeholder_heading_concat_samples),
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
        "residual_bullet_glyph_gate_source": "legacy_markdown",
        "residual_bullet_glyph_classification": "display_hygiene",
        "raw_residual_bullet_glyph_count": len(raw_residual_bullet_glyph_samples),
        "residual_bullet_glyph_samples": _serialize_quality_samples(residual_bullet_glyph_samples),
        "raw_residual_bullet_glyph_samples": _serialize_quality_samples(raw_residual_bullet_glyph_samples),
        "list_fragment_regression_count": len(list_fragment_regression_samples),
        "list_fragment_regression_samples": _serialize_quality_samples(list_fragment_regression_samples),
        "list_fragment_regression_gate_source": list_fragment_regression_gate_source,
        "raw_list_fragment_regression_count": len(raw_list_fragment_regression_samples),
        "raw_list_fragment_regression_samples": _serialize_quality_samples(raw_list_fragment_regression_samples),
        "mixed_script_term_count": len(mixed_script_samples),
        "mixed_script_term_gate_source": "legacy_markdown",
        "mixed_script_term_classification": "non_structural_hygiene",
        "raw_mixed_script_term_count": len(raw_mixed_script_samples),
        "mixed_script_term_samples": _serialize_quality_samples(mixed_script_samples),
        "raw_mixed_script_term_samples": _serialize_quality_samples(raw_mixed_script_samples),
        "theology_style_deterministic_issue_count": len(theology_style_samples),
        "theology_style_deterministic_issue_source": "legacy_markdown",
        "theology_style_deterministic_issue_classification": "domain_style_advisory",
        "raw_theology_style_deterministic_issue_count": len(raw_theology_style_samples),
        "theology_style_deterministic_issue_samples": _serialize_quality_samples(theology_style_samples),
        "raw_theology_style_deterministic_issue_samples": _serialize_quality_samples(raw_theology_style_samples),
        "toc_body_concat_detected": toc_body_concat_detected,
        "toc_body_concat_markdown_detected": authority_fields.get("toc_body_concat_markdown_detected", False),
        "toc_body_concat_structure_detected": authority_fields.get("toc_body_concat_structure_detected", False),
        "toc_body_concat_gate_source": authority_fields.get("toc_body_concat_gate_source", "legacy_markdown"),
        "formatting_diagnostics_artifact_count": len(formatting_diagnostics_artifacts),
        "role_aware_formatting_coverage_note": (
            role_aware_summary.get("counting_note") if role_aware_summary else None
        ),
        "pre_cleanup_formatting_baseline": dict(pre_cleanup_formatting_baseline)
        if isinstance(pre_cleanup_formatting_baseline, Mapping)
        else None,
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
                "accepted_aggregated_source_unit_count",
                "accepted_aggregated_target_index_count",
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
    candidate = (
        fields.get(structure_count_key)
        if basis in {"topology_unit", "accepted_aggregation_legacy"}
        else fields.get(raw_count_key)
    )
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
    assembly_registry = build_generated_paragraph_registry_from_entries(assembly_result.entries)
    runtime_display_markdown = _restore_image_heading_lines_from_registry(
        _normalize_final_markdown_for_runtime_display(final_markdown),
        assembly_registry or state.generated_paragraph_registry or None,
    )
    emitters.emit_state(context.runtime, latest_markdown=runtime_display_markdown)
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
        placeholder_integrity = dependencies.inspect_placeholder_integrity(runtime_display_markdown, normalized_image_assets)
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
            final_markdown_chars=len(runtime_display_markdown),
            image_count=len(context.image_assets),
            image_mode=context.image_mode,
        )
        emitters.emit_state(
            context.runtime,
            latest_markdown=runtime_display_markdown,
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
            target_chars=len(runtime_display_markdown),
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
    runtime_display_markdown = _restore_image_heading_lines_from_registry(
        _normalize_final_markdown_for_runtime_display(final_markdown),
        assembly_registry or state.generated_paragraph_registry or None,
    )
    emitters.emit_status(
        context.runtime,
        stage="Сборка DOCX",
        detail="Все блоки готовы. Собираю итоговый DOCX из Markdown.",
        current_block=job_count,
        block_count=job_count,
        target_chars=len(runtime_display_markdown),
        context_chars=0,
        progress=1.0,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, "Все блоки готовы. Начата сборка итогового DOCX.")
    context.on_progress(preview_title="Текущий Markdown")
    build_started_at_epoch = time.time()
    processed_image_assets = image_phase["processed_image_assets"]
    docx_bytes_cache: bytes | None = None

    def _build_base_docx_bytes() -> bytes:
        nonlocal docx_bytes_cache
        if docx_bytes_cache is not None:
            return docx_bytes_cache
        docx_bytes = dependencies.convert_markdown_to_docx_bytes(runtime_display_markdown)
        if context.source_paragraphs:
            docx_bytes = call_docx_restorer_with_optional_registry_fn(
                dependencies.preserve_source_paragraph_properties,
                docx_bytes,
                context.source_paragraphs,
                assembly_registry or state.generated_paragraph_registry or None,
            )
        if processed_image_assets:
            docx_bytes = dependencies.reinsert_inline_images(docx_bytes, processed_image_assets)
        docx_bytes_cache = docx_bytes
        return docx_bytes

    docx_bytes: bytes | None = None
    should_defer_base_docx_build = _should_run_reader_cleanup(context=context)
    pre_cleanup_formatting_baseline = (
        _build_pre_cleanup_formatting_baseline(
            markdown_text=runtime_display_markdown,
            generated_paragraph_registry=assembly_registry or state.generated_paragraph_registry or None,
        )
        if should_defer_base_docx_build
        else None
    )
    try:
        if not should_defer_base_docx_build:
            docx_bytes = _build_base_docx_bytes()
    except Exception as exc:
        error_message = dependencies.present_error(
            "docx_build_failed",
            exc,
            "Ошибка сборки DOCX",
            filename=context.uploaded_filename,
            final_markdown_chars=len(runtime_display_markdown),
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
            target_chars=len(runtime_display_markdown),
            context_chars=0,
            log_details=error_message,
        )
        return None

    latest_result_notice: dict[str, str] | None = None
    formatting_diagnostics_artifacts: Sequence[str] = []
    if docx_bytes is not None:
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
                target_chars=len(runtime_display_markdown),
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

    if docx_bytes is not None and not docx_bytes:
        _build_empty_docx_failure_result(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            runtime_display_markdown=runtime_display_markdown,
            job_count=job_count,
        )
        return None

    return {
        "docx_bytes": docx_bytes,
        "base_docx_builder": _build_base_docx_bytes,
        "runtime_display_markdown": runtime_display_markdown,
        "latest_result_notice": latest_result_notice,
        "pre_cleanup_formatting_baseline": pre_cleanup_formatting_baseline,
        "formatting_diagnostics_artifacts": list(formatting_diagnostics_artifacts),
        "assembly_entries": list(assembly_result.entries),
        "result_manifest": result_manifest,
        "processed_image_assets": list(cast(Sequence[Any], image_phase.get("processed_image_assets") or [])),
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
    runtime_display_markdown = _resolve_runtime_display_markdown(
        docx_phase=docx_phase,
        fallback_markdown=gate_input_markdown,
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
        pre_cleanup_formatting_baseline=cast(Mapping[str, object] | None, docx_phase.get("pre_cleanup_formatting_baseline")),
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
        resolved_docx_bytes = _resolve_docx_phase_bytes(docx_phase)
        empty_docx_failure = _validate_nonempty_docx_bytes_or_fail(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            runtime_display_markdown=runtime_display_markdown,
            job_count=job_count,
            docx_bytes=resolved_docx_bytes,
        )
        if empty_docx_failure is not None:
            return empty_docx_failure
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
            latest_markdown=runtime_display_markdown,
            latest_docx_bytes=resolved_docx_bytes,
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
            target_chars=len(runtime_display_markdown),
            context_chars=0,
            log_details=error_message,
        )
    narration_error_message = ""
    reader_cleanup_report: dict[str, object] | None = None
    reader_cleanup_raw_markdown: str | None = None
    reader_cleanup_result_notice: dict[str, str] | None = None
    reader_cleanup_postprocess = _run_reader_cleanup_postprocess(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        cleanup_input_markdown=gate_input_markdown,
        runtime_display_markdown=runtime_display_markdown,
        base_docx_bytes=cast(bytes | None, docx_phase.get("docx_bytes")),
        job_count=job_count,
        processed_image_assets=cast(Sequence[Any], docx_phase.get("processed_image_assets") or []),
        formatting_registry=build_generated_paragraph_registry_from_entries(assembly_result.entries),
        base_docx_builder=cast(Callable[[], bytes] | None, docx_phase.get("base_docx_builder")),
    )
    runtime_display_markdown = reader_cleanup_postprocess.markdown
    final_docx_bytes = reader_cleanup_postprocess.docx_bytes
    reader_cleanup_report = reader_cleanup_postprocess.report
    reader_cleanup_raw_markdown = reader_cleanup_postprocess.raw_markdown
    reader_cleanup_result_notice = reader_cleanup_postprocess.result_notice
    final_generated_paragraph_registry = reader_cleanup_postprocess.final_generated_paragraph_registry
    if final_generated_paragraph_registry is not None:
        docx_phase = dict(docx_phase)
        docx_phase["final_generated_paragraph_registry"] = final_generated_paragraph_registry
    empty_docx_failure = _validate_nonempty_docx_bytes_or_fail(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        runtime_display_markdown=runtime_display_markdown,
        job_count=job_count,
        docx_bytes=final_docx_bytes,
    )
    if empty_docx_failure is not None:
        return empty_docx_failure
    current_docx_bytes = docx_phase.get("docx_bytes")
    if not isinstance(current_docx_bytes, bytes) or final_docx_bytes != current_docx_bytes or runtime_display_markdown != _resolve_runtime_display_markdown(
        docx_phase=docx_phase,
        fallback_markdown=gate_input_markdown,
    ):
        docx_phase = dict(docx_phase)
        docx_phase["docx_bytes"] = final_docx_bytes
        docx_phase["runtime_display_markdown"] = runtime_display_markdown
    if reader_cleanup_result_notice is not None:
        docx_phase = dict(docx_phase)
        docx_phase["latest_result_notice"] = reader_cleanup_result_notice

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
                latest_docx_bytes=_resolve_docx_phase_bytes(docx_phase),
                latest_markdown=runtime_display_markdown,
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
                latest_markdown=runtime_display_markdown,
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
                target_chars=len(runtime_display_markdown),
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
                    latest_docx_bytes=_resolve_docx_phase_bytes(docx_phase),
                    latest_markdown=runtime_display_markdown,
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
                    latest_markdown=runtime_display_markdown,
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
                    target_chars=len(runtime_display_markdown),
                    context_chars=0,
                    log_details=error_message,
                )
    emitters.emit_state(
        context.runtime,
        final_generated_paragraph_registry=cast(
            Sequence[Mapping[str, object]] | None, docx_phase.get("final_generated_paragraph_registry")
        ),
        latest_docx_bytes=_resolve_docx_phase_bytes(docx_phase),
        latest_markdown=runtime_display_markdown,
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
            "markdown_text": runtime_display_markdown,
            "docx_bytes": _resolve_docx_phase_bytes(docx_phase),
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
        if reader_cleanup_report is not None:
            result_artifact_paths.update(
                write_reader_cleanup_diagnostics(
                    cleaned_artifact_paths=result_artifact_paths,
                    raw_markdown=reader_cleanup_raw_markdown or gate_input_markdown,
                    report_payload=reader_cleanup_report,
                )
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
        final_markdown_chars=len(runtime_display_markdown),
        narration_chars=len(narration_text or ""),
        elapsed_seconds=round(time.perf_counter() - state.started_at, 2),
        translation_second_pass_enabled=_is_translation_second_pass_effectively_enabled(context=context),
        audiobook_postprocess_enabled=_should_run_audiobook_postprocess(context=context),
        reader_cleanup_enabled=_should_run_reader_cleanup(context=context),
    )
    emitters.emit_log(
        context.runtime,
        status="DONE",
        block_index=job_count,
        block_count=job_count,
        target_chars=len(runtime_display_markdown),
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
