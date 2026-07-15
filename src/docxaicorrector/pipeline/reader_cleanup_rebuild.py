"""Reader-cleanup DOCX rebuild + formatting-registry identity (spec 031 Cluster B).

Behaviour-preserving extraction from ``pipeline/late_phases.py``: the reader-cleanup
rebuild helpers that align the generated-paragraph formatting registry to rebuilt Markdown
blocks, derive the cleanup-time registry, stitch DOCX image placeholders back into the
rebuilt Markdown, and write the reader-cleanup lineage artifact. The LLM-driven orchestrator
``_run_reader_cleanup_postprocess`` (Cluster C) stays separate. ``late_phases`` re-exports
every name here so ``late_phases.<name>`` keeps resolving for the test namespace, the
still-in-``late_phases`` build/finalize callers, and the reader-cleanup lineage rebuild
harness (namespace importer). No module-level mutable state; ``emit_failed_result``
(Cluster G) is reached via a lazy import to avoid a circular import back into ``late_phases``.
"""

import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from docxaicorrector.reader_cleanup_mvp import build_cleanup_blocks
from docxaicorrector.runtime.artifact_retention import (
    READER_CLEANUP_LINEAGE_MAX_AGE_SECONDS,
    READER_CLEANUP_LINEAGE_MAX_COUNT,
    prune_artifact_dir,
)


PipelineResult = Literal["succeeded", "failed", "stopped"]
READER_CLEANUP_LINEAGE_DIR = Path(".run") / "reader_cleanup_lineage"
_DOCX_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"^\[\[DOCX_IMAGE_[A-Za-z0-9_]+\]\]$")


@dataclass(frozen=True)
class ReaderCleanupPostprocessResult:
    markdown: str
    docx_bytes: bytes
    report: dict[str, object] | None
    raw_markdown: str | None
    result_notice: dict[str, str] | None
    final_generated_paragraph_registry: Sequence[Mapping[str, object]] | None


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
    from docxaicorrector.pipeline.late_phases import emit_failed_result

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


def _coerce_optional_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _reader_cleanup_layout_signals_from_registry_entry(
    *,
    entry: Mapping[str, object],
    normalized_text: str,
) -> dict[str, object]:
    raw_layout = entry.get("layout_signals")
    signals: dict[str, object] = dict(raw_layout) if isinstance(raw_layout, Mapping) else {}
    formatting = entry.get("formatting")
    if isinstance(formatting, Mapping):
        for source_key, target_key in {
            "font_size": "font_size",
            "body_font_size": "body_font_size",
            "left_indent": "left_indent",
            "first_line_indent": "first_line_indent",
            "alignment": "alignment",
            "centered": "centered",
            "superscript": "superscript",
        }.items():
            if source_key in formatting and target_key not in signals:
                signals[target_key] = formatting[source_key]

    for source_key, target_key in {
        "font_size": "font_size",
        "body_font_size": "body_font_size",
        "font_size_delta_from_body": "font_size_delta_from_body",
        "font_size_ratio_to_body": "font_size_ratio_to_body",
        "left_indent": "left_indent",
        "indent": "indent",
        "first_line_indent": "first_line_indent",
        "alignment": "alignment",
        "centered": "centered",
        "superscript": "superscript",
    }.items():
        if source_key in entry and target_key not in signals:
            signals[target_key] = entry[source_key]

    font_size = _coerce_optional_float(signals.get("font_size"))
    body_font_size = _coerce_optional_float(signals.get("body_font_size"))
    if font_size is not None and body_font_size is not None and body_font_size > 0:
        signals.setdefault("font_size_delta_from_body", round(font_size - body_font_size, 3))
        signals.setdefault("font_size_ratio_to_body", round(font_size / body_font_size, 4))

    alignment = str(signals.get("alignment") or "").strip().casefold()
    if alignment:
        signals.setdefault("centered", alignment == "center")
    stripped = normalized_text.strip()
    signals.setdefault("standalone_short_line", bool(stripped) and "\n" not in stripped and len(stripped) <= 90)
    signals.setdefault("looks_like_superscript_marker", bool(re.fullmatch(r"\[?\d{1,3}\]?|\(\d{1,3}\)", stripped)))
    return signals


def _build_reader_cleanup_block_identity_metadata(
    *,
    raw_markdown: str,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> tuple[dict[int, dict[str, object]], dict[str, object]]:
    """Build cleanup block identity and layout metadata for payloads and stitching."""
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
        layout_signals = _reader_cleanup_layout_signals_from_registry_entry(
            entry=entry,
            normalized_text=expected_text,
        )
        if paragraph_ids:
            metadata: dict[str, object] = {"paragraph_id": paragraph_ids[0]}
            if len(paragraph_ids) > 1:
                metadata["merged_paragraph_ids"] = paragraph_ids
            if layout_signals:
                metadata["layout_signals"] = layout_signals
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
