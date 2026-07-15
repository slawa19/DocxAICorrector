from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from ._constants import (  # noqa: F401
    READER_CLEANUP_DEFAULT_SELECTOR,
    CleanupConfidence,
    CleanupPolicy,
    _ALLOWED_ANCHOR_REPAIR_CATEGORIES,
    _ALLOWED_CONFIDENCE,
    _ALLOWED_DELETE_REASONS,
    _ALLOWED_OPERATIONS,
    _ALLOWED_POLICIES,
    _ALLOWED_REANNOTATION_ROLES,
    _ALLOWED_RECLASSIFY_TARGET_ROLES,
    _BLANK_PAGE_PATTERN,
    _BLOCK_RESPONSE_FIELDS,
    _DEFAULT_CLEANUP_CHUNK_SIZE,
    _DEFAULT_GLOBAL_PLAN_ENABLED,
    _DEFAULT_OVERLAP_BLOCKS_AFTER,
    _DEFAULT_OVERLAP_BLOCKS_BEFORE,
    _DOCX_IMAGE_PLACEHOLDER_ONLY_PATTERN,
    _DOCX_IMAGE_PLACEHOLDER_PATTERN,
    _DUPLICATE_FRAGMENT_MAX_NEARBY_BLOCK_DISTANCE,
    _DUPLICATE_FRAGMENT_MIN_NON_WHITESPACE_CHARS,
    _EXTRACTION_ARTIFACT_PATTERN,
    _FOOTNOTE_BODY_PATTERN,
    _GENERIC_RUNNING_HEADER_TOKENS,
    _HEADER_CONNECTOR_WORDS,
    _INLINE_NOISE_REASON_GUIDANCE,
    _NUMERIC_UPPERCASE_MAX_TOKENS_WITHOUT_GENERIC_HEADER,
    _NUMERIC_UPPERCASE_RUNNING_HEADER_PATTERN,
    _OPERATION_RESPONSE_FIELDS,
    _ORPHAN_FOOTNOTE_PATTERN,
    _PAGE_NUMBER_PATTERN,
    _RECLASSIFY_MARKDOWN_HEADING_PREFIX,
    _REMOVE_INLINE_NOISE_REASON_GUIDANCE,
    _RUNNING_HEADER_TRAILING_PUNCTUATION,
    _SAFE_CONFIDENCE_INFERENCE,
    _SAFE_INLINE_NOISE_PATTERN,
    _TOC_LIKE_PATTERN,
    _TOP_LEVEL_RESPONSE_FIELDS,
)


from ._models import (  # noqa: F401
    AnchorRepairChunk,
    AnchorRepairPassResult,
    CleanupBlock,
    CleanupChunk,
    CleanupOperation,
    ReaderCleanupConfig,
    ReaderCleanupResult,
    ReaderCleanupStageError,
    ReannotationDecision,
)


def resolve_reader_cleanup_config(*, app_config: Mapping[str, object], fallback_model: str) -> ReaderCleanupConfig:
    raw_policy = str(app_config.get("reader_cleanup_policy", "advisory") or "advisory").strip().lower()
    policy = raw_policy if raw_policy in _ALLOWED_POLICIES else "advisory"
    enabled = bool(app_config.get("reader_cleanup_enabled", False)) and policy != "off"
    model = str(app_config.get("reader_cleanup_model", "") or "").strip() or READER_CLEANUP_DEFAULT_SELECTOR
    return ReaderCleanupConfig(
        enabled=enabled,
        model=model,
        chunk_size=_coerce_int(
            app_config.get("reader_cleanup_chunk_size", _DEFAULT_CLEANUP_CHUNK_SIZE),
            default=_DEFAULT_CLEANUP_CHUNK_SIZE,
            minimum=3000,
        ),
        overlap_blocks_before=_coerce_int(
            app_config.get("reader_cleanup_overlap_blocks_before", _DEFAULT_OVERLAP_BLOCKS_BEFORE),
            default=_DEFAULT_OVERLAP_BLOCKS_BEFORE,
            minimum=0,
        ),
        overlap_blocks_after=_coerce_int(
            app_config.get("reader_cleanup_overlap_blocks_after", _DEFAULT_OVERLAP_BLOCKS_AFTER),
            default=_DEFAULT_OVERLAP_BLOCKS_AFTER,
            minimum=0,
        ),
        global_plan_enabled=_coerce_bool(
            app_config.get("reader_cleanup_global_plan_enabled", _DEFAULT_GLOBAL_PLAN_ENABLED),
            default=_DEFAULT_GLOBAL_PLAN_ENABLED,
        ),
        keep_toc=bool(app_config.get("reader_cleanup_keep_toc", True)),
        drop_back_matter=bool(app_config.get("reader_cleanup_drop_back_matter", False)),
        max_delete_block_ratio=_coerce_float(app_config.get("reader_cleanup_max_delete_block_ratio", 0.03), default=0.03),
        max_delete_char_ratio=_coerce_float(app_config.get("reader_cleanup_max_delete_char_ratio", 0.05), default=0.05),
        max_reclassify_block_ratio=_coerce_float(
            app_config.get("reader_cleanup_max_reclassify_block_ratio", 0.05),
            default=0.05,
        ),
        max_failed_chunk_ratio=_coerce_float(
            app_config.get("reader_cleanup_max_failed_chunk_ratio", 1.0),
            default=1.0,
        ),
        max_consecutive_deleted_blocks=_coerce_int(
            app_config.get("reader_cleanup_max_consecutive_deleted_blocks", 3),
            default=3,
            minimum=1,
        ),
        max_deleted_block_chars=_coerce_int(
            app_config.get("reader_cleanup_max_deleted_block_chars", 300),
            default=300,
            minimum=1,
        ),
        policy=cast(CleanupPolicy, policy),
        allowed_operations=_coerce_allowed_operations(app_config.get("reader_cleanup_allowed_operations")),
    )


def _coerce_allowed_operations(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    raw_values: Sequence[object]
    if isinstance(value, str):
        raw_values = [part.strip() for part in value.split(",")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_values = value
    else:
        return ()

    allowed: list[str] = []
    for raw_value in raw_values:
        operation = str(raw_value or "").strip()
        if not operation or operation not in _ALLOWED_OPERATIONS or operation in allowed:
            continue
        allowed.append(operation)
    return tuple(allowed)


from ._prompts import (  # noqa: F401
    build_reader_cleanup_global_plan_system_prompt,
    build_reader_cleanup_reannotation_system_prompt,
    build_reader_cleanup_schema_repair_system_prompt,
    build_reader_cleanup_system_prompt,
)


def build_cleanup_blocks(
    markdown_text: str,
    *,
    block_metadata_by_index: Mapping[int, Mapping[str, object]] | None = None,
) -> list[CleanupBlock]:
    normalized_markdown = str(markdown_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_markdown:
        return []

    raw_blocks = [part.strip("\n") for part in re.split(r"\n\s*\n+", normalized_markdown) if part.strip()]
    blocks: list[CleanupBlock] = []
    for index, raw_block in enumerate(raw_blocks):
        normalized_text = _normalize_block_text(raw_block)
        kind = _detect_block_kind(normalized_text)
        metadata = block_metadata_by_index.get(index) if block_metadata_by_index is not None else None
        paragraph_id = None
        merged_paragraph_ids: tuple[str, ...] = ()
        layout_signals: dict[str, object] = _derive_cleanup_block_layout_signals(
            text=raw_block,
            normalized_text=normalized_text,
            kind=kind,
        )
        if isinstance(metadata, Mapping):
            raw_paragraph_id = metadata.get("paragraph_id")
            if isinstance(raw_paragraph_id, str) and raw_paragraph_id.strip():
                paragraph_id = raw_paragraph_id.strip()
            raw_merged_ids = metadata.get("merged_paragraph_ids")
            if isinstance(raw_merged_ids, Sequence) and not isinstance(raw_merged_ids, (str, bytes, bytearray)):
                merged_paragraph_ids = tuple(str(value).strip() for value in raw_merged_ids if str(value).strip())
            raw_layout_signals = metadata.get("layout_signals")
            if isinstance(raw_layout_signals, Mapping):
                layout_signals.update(_sanitize_layout_signals(raw_layout_signals))
        blocks.append(
            CleanupBlock(
                index=index,
                block_id=f"b_{index:06d}",
                text=raw_block,
                normalized_text=normalized_text,
                text_hash=hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16],
                char_count=len(raw_block),
                non_whitespace_char_count=len(re.sub(r"\s+", "", raw_block)),
                kind=kind,
                is_heading=kind == "heading",
                is_toc_like=kind == "toc_like",
                paragraph_id=paragraph_id,
                merged_paragraph_ids=merged_paragraph_ids,
                layout_signals=layout_signals,
            )
        )
    return blocks


def _derive_cleanup_block_layout_signals(*, text: str, normalized_text: str, kind: str) -> dict[str, object]:
    stripped = normalized_text.strip()
    line_count = len([line for line in str(text or "").splitlines() if line.strip()])
    visible_char_count = len(stripped)
    word_count = len(re.findall(r"\S+", stripped))
    digit_only = bool(re.fullmatch(r"\[?\d{1,3}\]?|\(\d{1,3}\)", stripped))
    image_placeholder_ids = _extract_docx_image_placeholder_ids(stripped)
    return {
        "standalone_short_line": line_count <= 1 and 0 < visible_char_count <= 90,
        "line_count": line_count,
        "word_count": word_count,
        "looks_like_superscript_marker": digit_only,
        "is_docx_image_anchor": bool(image_placeholder_ids) and bool(_DOCX_IMAGE_PLACEHOLDER_ONLY_PATTERN.fullmatch(stripped)),
        "docx_image_ids": image_placeholder_ids,
        "detected_kind": kind,
    }


def _sanitize_layout_signals(raw_signals: Mapping[str, object]) -> dict[str, object]:
    allowed_keys = {
        "font_size",
        "body_font_size",
        "font_size_delta_from_body",
        "font_size_ratio_to_body",
        "standalone_short_line",
        "indent",
        "left_indent",
        "first_line_indent",
        "centered",
        "alignment",
        "superscript",
        "looks_like_superscript_marker",
        "line_count",
        "word_count",
        "is_docx_image_anchor",
        "docx_image_ids",
        "detected_kind",
    }
    sanitized: dict[str, object] = {}
    for key, value in raw_signals.items():
        normalized_key = str(key or "").strip()
        if normalized_key not in allowed_keys:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[normalized_key] = value
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            sanitized[normalized_key] = [str(item) for item in value]
    return sanitized


def _select_cleanup_blocks(*, blocks: Sequence[CleanupBlock], keep_toc: bool) -> tuple[list[CleanupBlock], list[str]]:
    if keep_toc:
        return list(blocks), []

    filtered_blocks = [block for block in blocks if not block.is_toc_like]
    ignored_toc_count = len(blocks) - len(filtered_blocks)
    warnings: list[str] = []
    if ignored_toc_count > 0:
        warnings.append(f"reader_cleanup_toc_blocks_ignored:{ignored_toc_count}")
    return filtered_blocks, warnings


def run_reader_cleanup(
    *,
    markdown_text: str,
    config: ReaderCleanupConfig,
    operation_provider: Callable[[dict[str, Any], int, int], str],
    repair_provider: Callable[[dict[str, Any], int, int], str] | None = None,
    global_plan_provider: Callable[[dict[str, Any]], str] | None = None,
    anchor_operation_provider: Callable[[dict[str, Any], int, int], str] | None = None,
    anchor_targets: Sequence[Mapping[str, object]] | None = None,
    model_resolution: Mapping[str, object] | None = None,
    block_metadata_by_index: Mapping[int, Mapping[str, object]] | None = None,
) -> ReaderCleanupResult:
    blocks = build_cleanup_blocks(markdown_text, block_metadata_by_index=block_metadata_by_index)
    cleanup_blocks, selection_warnings = _select_cleanup_blocks(blocks=blocks, keep_toc=config.keep_toc)
    raw_markdown = str(markdown_text or "")
    if not blocks:
        report_payload = {
            "version": 1,
            "policy": config.policy,
            "model": config.model,
            "cleanup_settings": _serialize_cleanup_settings(config),
            "stage_status": "completed",
            "changed": False,
            "warnings": ["reader_cleanup_skipped_empty_markdown"],
            "stats": {"raw_block_count": 0, "cleanup_chunk_count": 0},
            "global_plan": {"repeated_noise_patterns": [], "candidate_block_ids": [], "warnings": []},
            "accepted_delete_blocks": [],
            "ignored_cleanup_operations": [],
            "ignored_delete_blocks": [],
            "chunk_results": [],
        }
        return ReaderCleanupResult(
            changed=False,
            raw_markdown=raw_markdown,
            cleaned_markdown=raw_markdown,
            report_payload=report_payload,
            accepted_delete_block_ids=(),
        )

    global_plan = _build_global_plan(
        blocks=cleanup_blocks,
        raw_markdown=raw_markdown,
        config=config,
        global_plan_provider=global_plan_provider,
    )
    chunks = _build_cleanup_chunks(
        blocks=cleanup_blocks,
        chunk_size=config.chunk_size,
        overlap_blocks_before=config.overlap_blocks_before,
        overlap_blocks_after=config.overlap_blocks_after,
    )
    all_operations: list[CleanupOperation] = []
    raw_global_warnings = global_plan.get("warnings")
    warnings: list[str] = list(selection_warnings)
    if isinstance(raw_global_warnings, list):
        warnings.extend(str(item) for item in raw_global_warnings)
    ignored_cleanup_operations: list[dict[str, object]] = []
    chunk_results: list[dict[str, object]] = []

    for chunk in chunks:
        request_payload = _build_chunk_request_payload(chunk=chunk, global_plan=global_plan, config=config)
        request_payload_char_count = len(json.dumps(request_payload, ensure_ascii=False))
        started_at = time.perf_counter()
        raw_response = ""
        schema_validation_error = ""
        parse_error_message = ""
        repair_error = ""
        repair_attempted = False
        repair_status = "not_attempted"
        retry_attempted = False
        retry_status = "not_attempted"
        retry_error = ""
        ignored_chunk_operations: list[dict[str, object]] = []
        try:
            raw_response = operation_provider(request_payload, chunk.chunk_index, len(chunks))
            editable_blocks = {block.block_id: block for block in chunk.blocks}
            readonly_context_blocks = _readonly_context_blocks_by_id(chunk)
            try:
                operations, chunk_warnings, ignored_chunk_operations = _parse_cleanup_response(
                    raw_response=raw_response,
                    editable_blocks=editable_blocks,
                    readonly_context_blocks=readonly_context_blocks,
                    chunk_index=chunk.chunk_index,
                )
            except Exception as exc:
                parse_error_message = str(exc)
                original_response_payload = _load_cleanup_response_object(raw_response)
                if original_response_payload is None:
                    retry_attempted = True
                    retry_status = "attempted"
                    warnings.append(f"reader_cleanup_non_json_response_retry_attempted:{chunk.chunk_index}:{parse_error_message}")
                    try:
                        raw_response = operation_provider(request_payload, chunk.chunk_index, len(chunks))
                        operations, chunk_warnings, ignored_chunk_operations = _parse_cleanup_response(
                            raw_response=raw_response,
                            editable_blocks=editable_blocks,
                            readonly_context_blocks=readonly_context_blocks,
                            chunk_index=chunk.chunk_index,
                        )
                    except Exception as retry_exc:
                        retry_status = "failed"
                        retry_error = str(retry_exc)
                        parse_error_message = retry_error
                        warnings.append(f"reader_cleanup_non_json_response_retry_failed:{chunk.chunk_index}:{retry_error}")
                        raise
                    retry_status = "succeeded"
                    warnings.append(f"reader_cleanup_non_json_response_retry_succeeded:{chunk.chunk_index}")
                    original_response_payload = None
                if original_response_payload is None:
                    pass
                else:
                    schema_validation_error = str(exc)
                    repair_attempted = True
                    repair_status = "attempted"
                    warnings.append(f"reader_cleanup_schema_validation_failed:{chunk.chunk_index}:{schema_validation_error}")
                    warnings.append(f"reader_cleanup_schema_repair_attempted:{chunk.chunk_index}")
                    repaired_response = repair_provider(
                        _build_cleanup_schema_repair_payload(
                            request_payload=request_payload,
                            original_response=original_response_payload,
                            validation_error=schema_validation_error,
                        ),
                        chunk.chunk_index,
                        len(chunks),
                    ) if repair_provider is not None else None
                    if repaired_response is None:
                        raise
                    try:
                        operations, chunk_warnings, ignored_chunk_operations = _parse_cleanup_response(
                            raw_response=repaired_response,
                            editable_blocks=editable_blocks,
                            readonly_context_blocks=readonly_context_blocks,
                            chunk_index=chunk.chunk_index,
                        )
                    except Exception as repair_exc:
                        repair_status = "failed"
                        repair_error = str(repair_exc)
                        warnings.append(f"reader_cleanup_schema_repair_failed:{chunk.chunk_index}:{repair_error}")
                        raise
                    repair_status = "succeeded"
                    warnings.append(f"reader_cleanup_schema_repair_succeeded:{chunk.chunk_index}")
                if retry_status == "succeeded":
                    pass
                elif original_response_payload is None:
                    raise
        except Exception as exc:
            warning = f"reader_cleanup_chunk_failed:{chunk.chunk_index}:{exc}"
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
            is_auth_failure = _is_auth_or_credential_error(exc)
            chunk_results.append(
                {
                    "chunk_index": chunk.chunk_index,
                    "status": "failed",
                    "failure_kind": "auth_or_credential_error" if is_auth_failure else "chunk_failed",
                    "target_block_count": len(chunk.blocks),
                    "target_chars": sum(block.char_count for block in chunk.blocks),
                    "readonly_context_before_count": len(chunk.context_before_blocks),
                    "readonly_context_after_count": len(chunk.context_after_blocks),
                    "elapsed_ms": elapsed_ms,
                    "proposed_cleanup_operation_count": 0,
                    "proposed_delete_block_count": 0,
                    "accepted_cleanup_operation_count": 0,
                    "accepted_delete_block_count": 0,
                    "ignored_cleanup_operation_count": 0,
                    "ignored_delete_block_count": 0,
                    "repair_attempted": repair_attempted,
                    "repair_status": repair_status,
                    "retry_attempted": retry_attempted,
                    "retry_status": retry_status,
                    "retry_error": retry_error,
                    "schema_validation_error": schema_validation_error,
                    "parse_error_message": parse_error_message or str(exc),
                    "repair_error": repair_error,
                    "failure_diagnostics": _build_failed_chunk_diagnostics(
                        chunk=chunk,
                        config=config,
                        request_payload_char_count=request_payload_char_count,
                        raw_response=raw_response,
                        parse_error_message=parse_error_message or str(exc),
                        retry_attempted=retry_attempted,
                        retry_status=retry_status,
                        retry_error=retry_error,
                        repair_attempted=repair_attempted,
                        repair_status=repair_status,
                        repair_error=repair_error,
                    ),
                    "warning": warning,
                }
            )
            warnings.append(warning)
            if is_auth_failure or config.policy == "strict":
                failure_kind = "auth_or_credential_error" if is_auth_failure else "chunk_failed"
                report_payload = _build_reader_cleanup_report_payload(
                    raw_markdown=raw_markdown,
                    config=config,
                    blocks=blocks,
                    global_plan=global_plan,
                    warnings=warnings,
                    accepted_delete_blocks=[],
                    accepted_cleanup_operations=[],
                    ignored_cleanup_operations=ignored_cleanup_operations,
                    chunk_results=chunk_results,
                    deleted_char_count=0,
                    changed=False,
                    model_resolution=model_resolution,
                    failure={
                        "kind": failure_kind,
                        "chunk_index": chunk.chunk_index,
                        "error_message": str(exc),
                        "status_code": _extract_http_status_code(exc),
                    },
                )
                raise ReaderCleanupStageError(
                    f"reader_cleanup_{failure_kind}:{chunk.chunk_index}:{exc}",
                    report_payload=report_payload,
                    raw_markdown=raw_markdown,
                ) from exc
            continue

        all_operations.extend(operations)
        warnings.extend(chunk_warnings)
        ignored_cleanup_operations.extend(ignored_chunk_operations)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        chunk_results.append(
            {
                "chunk_index": chunk.chunk_index,
                "status": "completed",
                "target_block_count": len(chunk.blocks),
                "target_chars": sum(block.char_count for block in chunk.blocks),
                "readonly_context_before_count": len(chunk.context_before_blocks),
                "readonly_context_after_count": len(chunk.context_after_blocks),
                "elapsed_ms": elapsed_ms,
                "proposed_cleanup_operation_count": len(operations) + len(ignored_chunk_operations),
                "proposed_delete_block_count": sum(1 for operation in operations if operation.operation == "delete_block"),
                "accepted_cleanup_operation_count": 0,
                "accepted_delete_block_count": 0,
                "ignored_cleanup_operation_count": 0,
                "ignored_delete_block_count": 0,
                "repair_attempted": repair_attempted,
                "repair_status": repair_status,
                "retry_attempted": retry_attempted,
                "retry_status": retry_status,
                "retry_error": retry_error,
                "schema_validation_error": schema_validation_error,
                "parse_error_message": parse_error_message,
                "repair_error": repair_error,
                "request_payload_char_count": request_payload_char_count,
            }
        )

    failure_ratio = _failed_chunk_ratio(chunk_results)
    if _failed_chunk_ratio_exceeds_threshold(chunk_results=chunk_results, config=config):
        warnings.append(
            "reader_cleanup_failed_chunk_ratio_exceeded:"
            f"{failure_ratio:.6f}:threshold={config.max_failed_chunk_ratio:.6f}"
        )
        report_payload = _build_reader_cleanup_report_payload(
            raw_markdown=raw_markdown,
            config=config,
            blocks=blocks,
            global_plan=global_plan,
            warnings=warnings,
            accepted_delete_blocks=[],
            accepted_cleanup_operations=[],
            ignored_cleanup_operations=ignored_cleanup_operations,
            chunk_results=chunk_results,
            deleted_char_count=0,
            changed=False,
            model_resolution=model_resolution,
            failure={
                "kind": "failed_chunk_ratio_exceeded",
                "failed_chunk_ratio": failure_ratio,
                "max_failed_chunk_ratio": config.max_failed_chunk_ratio,
            },
        )
        return ReaderCleanupResult(
            changed=False,
            raw_markdown=raw_markdown,
            cleaned_markdown=raw_markdown,
            report_payload=report_payload,
            accepted_delete_block_ids=(),
        )

    cleaned_markdown, accepted_ids, accepted_cleanup_operations, ignored = _apply_cleanup_operations(
        raw_markdown=raw_markdown,
        blocks=blocks,
        operations=all_operations,
        config=config,
        global_candidate_block_ids={
            str(block_id)
            for block_id in cast(Sequence[object], global_plan.get("candidate_block_ids") or [])
            if str(block_id).strip()
        },
    )
    ignored_cleanup_operations.extend(ignored)
    cleaned_markdown, image_reconciliation = _reconcile_docx_image_placeholders(
        raw_markdown=raw_markdown,
        cleaned_markdown=cleaned_markdown,
        raw_blocks=blocks,
    )
    image_reconciliation_warnings = _image_reconciliation_warnings(image_reconciliation)
    warnings.extend(image_reconciliation_warnings)

    accepted_delete_blocks: list[dict[str, object]] = []
    accepted_counts_by_chunk: Counter[int] = Counter()
    for block_id, entry in accepted_ids.items():
        block = _block_by_id(blocks, block_id)
        chunk_index = _coerce_int(entry.get("chunk_index"), default=0, minimum=0)
        accepted_delete_blocks.append(
            {
                **_serialize_delete_block(block=block, reason=str(entry["reason"]), confidence=str(entry["confidence"])),
                "chunk_index": chunk_index,
                "after_state": "deleted",
            }
        )
        accepted_counts_by_chunk[chunk_index] += 1

    ignored_counts_by_chunk: Counter[int] = Counter()
    for entry in ignored_cleanup_operations:
        chunk_index = entry.get("chunk_index")
        if isinstance(chunk_index, int):
            ignored_counts_by_chunk[chunk_index] += 1

    for chunk_result in chunk_results:
        chunk_index = chunk_result.get("chunk_index")
        if not isinstance(chunk_index, int) or chunk_result.get("status") != "completed":
            continue
        accepted_cleanup_count = sum(1 for entry in accepted_cleanup_operations if entry.get("chunk_index") == chunk_index)
        chunk_result["accepted_delete_block_count"] = accepted_counts_by_chunk.get(chunk_index, 0)
        chunk_result["accepted_cleanup_operation_count"] = accepted_cleanup_count
        chunk_result["ignored_delete_block_count"] = ignored_counts_by_chunk.get(chunk_index, 0)
        chunk_result["ignored_cleanup_operation_count"] = ignored_counts_by_chunk.get(chunk_index, 0)

    deleted_char_count = sum(_block_by_id(blocks, block_id).non_whitespace_char_count for block_id in accepted_ids)
    report_payload = _build_reader_cleanup_report_payload(
        raw_markdown=raw_markdown,
        config=config,
        blocks=blocks,
        global_plan=global_plan,
        warnings=warnings,
        accepted_delete_blocks=accepted_delete_blocks,
        accepted_cleanup_operations=accepted_cleanup_operations,
        ignored_cleanup_operations=ignored_cleanup_operations,
        chunk_results=chunk_results,
        deleted_char_count=deleted_char_count,
        changed=cleaned_markdown != raw_markdown,
        model_resolution=model_resolution,
        image_reconciliation=image_reconciliation,
    )

    if anchor_operation_provider is not None and anchor_targets:
        anchor_pass_result = _run_anchor_repair_pass(
            markdown_text=cleaned_markdown,
            config=config,
            global_plan=global_plan,
            anchor_targets=anchor_targets,
            operation_provider=anchor_operation_provider,
            repair_provider=repair_provider,
        )
        cleaned_markdown = anchor_pass_result.cleaned_markdown
        report_payload = _merge_anchor_repair_pass_into_report(
            report_payload=report_payload,
            raw_markdown=raw_markdown,
            raw_blocks=blocks,
            anchor_pass_result=anchor_pass_result,
        )
        cleaned_markdown, image_reconciliation = _reconcile_docx_image_placeholders(
            raw_markdown=raw_markdown,
            cleaned_markdown=cleaned_markdown,
            raw_blocks=blocks,
        )
        if image_reconciliation.get("missing_after_repair"):
            report_payload.setdefault("warnings", [])
            if isinstance(report_payload["warnings"], list):
                report_payload["warnings"].extend(_image_reconciliation_warnings(image_reconciliation))
        report_payload["image_reconciliation"] = image_reconciliation

    return ReaderCleanupResult(
        changed=cleaned_markdown != raw_markdown,
        raw_markdown=raw_markdown,
        cleaned_markdown=cleaned_markdown,
        report_payload=report_payload,
        accepted_delete_block_ids=tuple(accepted_ids.keys()),
    )


def run_reader_cleanup_reannotation(
    *,
    markdown_text: str,
    config: ReaderCleanupConfig,
    annotation_provider: Callable[[dict[str, Any], int, int], str],
    model_resolution: Mapping[str, object] | None = None,
    block_metadata_by_index: Mapping[int, Mapping[str, object]] | None = None,
) -> ReaderCleanupResult:
    raw_markdown = str(markdown_text or "")
    blocks = build_cleanup_blocks(raw_markdown, block_metadata_by_index=block_metadata_by_index)
    cleanup_blocks, selection_warnings = _select_cleanup_blocks(blocks=blocks, keep_toc=config.keep_toc)
    if not blocks:
        report_payload = {
            "version": 1,
            "mode": "reannotation",
            "policy": config.policy,
            "model": config.model,
            "cleanup_settings": _serialize_cleanup_settings(config),
            "stage_status": "completed",
            "changed": False,
            "warnings": ["reader_cleanup_reannotation_skipped_empty_markdown"],
            "stats": {"raw_block_count": 0, "cleanup_chunk_count": 0},
            "accepted_cleanup_operations": [],
            "accepted_delete_blocks": [],
            "ignored_cleanup_operations": [],
            "ignored_delete_blocks": [],
            "chunk_results": [],
            "model_resolution": dict(model_resolution or {}),
            "image_reconciliation": {},
        }
        return ReaderCleanupResult(
            changed=False,
            raw_markdown=raw_markdown,
            cleaned_markdown=raw_markdown,
            report_payload=report_payload,
            accepted_delete_block_ids=(),
        )

    chunks = _build_cleanup_chunks(
        blocks=cleanup_blocks,
        chunk_size=config.chunk_size,
        overlap_blocks_before=config.overlap_blocks_before,
        overlap_blocks_after=config.overlap_blocks_after,
    )
    warnings = list(selection_warnings)
    decisions: list[ReannotationDecision] = []
    ignored: list[dict[str, object]] = []
    chunk_results: list[dict[str, object]] = []
    for chunk in chunks:
        payload = _build_reannotation_request_payload(chunk=chunk, config=config)
        started_at = time.perf_counter()
        raw_response = ""
        try:
            raw_response = annotation_provider(payload, chunk.chunk_index, len(chunks))
            parsed_decisions, parsed_ignored, parsed_warnings = _parse_reannotation_response(
                raw_response=raw_response,
                editable_blocks={block.block_id: block for block in chunk.blocks},
                chunk_index=chunk.chunk_index,
            )
            decisions.extend(parsed_decisions)
            ignored.extend(parsed_ignored)
            warnings.extend(parsed_warnings)
            chunk_results.append(
                {
                    "chunk_index": chunk.chunk_index,
                    "status": "completed",
                    "target_block_count": len(chunk.blocks),
                    "target_chars": sum(block.char_count for block in chunk.blocks),
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    "proposed_reannotation_count": len(parsed_decisions) + len(parsed_ignored),
                    "accepted_cleanup_operation_count": 0,
                    "ignored_cleanup_operation_count": len(parsed_ignored),
                    "request_payload_char_count": len(json.dumps(payload, ensure_ascii=False)),
                }
            )
        except Exception as exc:
            warning = f"reader_cleanup_reannotation_chunk_failed:{chunk.chunk_index}:{exc}"
            warnings.append(warning)
            chunk_results.append(
                {
                    "chunk_index": chunk.chunk_index,
                    "status": "failed",
                    "target_block_count": len(chunk.blocks),
                    "target_chars": sum(block.char_count for block in chunk.blocks),
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    "parse_error_message": str(exc),
                    "raw_response_preview": str(raw_response or "")[:1000],
                    "warning": warning,
                }
            )
            if config.policy == "strict":
                break

    cleaned_markdown, accepted_operations, apply_ignored = _apply_reannotation_decisions(
        raw_markdown=raw_markdown,
        blocks=blocks,
        decisions=decisions,
    )
    ignored.extend(apply_ignored)
    cleaned_markdown, image_reconciliation = _reconcile_docx_image_placeholders(
        raw_markdown=raw_markdown,
        cleaned_markdown=cleaned_markdown,
        raw_blocks=blocks,
    )
    warnings.extend(_image_reconciliation_warnings(image_reconciliation))
    accepted_by_chunk = Counter(int(entry.get("chunk_index") or 0) for entry in accepted_operations)
    ignored_by_chunk = Counter(int(entry.get("chunk_index") or 0) for entry in ignored if isinstance(entry.get("chunk_index"), int))
    for chunk_result in chunk_results:
        chunk_index = chunk_result.get("chunk_index")
        if isinstance(chunk_index, int):
            chunk_result["accepted_cleanup_operation_count"] = accepted_by_chunk.get(chunk_index, 0)
            chunk_result["ignored_cleanup_operation_count"] = ignored_by_chunk.get(chunk_index, 0)

    report_payload = _build_reader_cleanup_report_payload(
        raw_markdown=raw_markdown,
        config=config,
        blocks=blocks,
        global_plan={"mode": "reannotation"},
        warnings=warnings,
        accepted_delete_blocks=[],
        accepted_cleanup_operations=accepted_operations,
        ignored_cleanup_operations=ignored,
        chunk_results=chunk_results,
        deleted_char_count=0,
        changed=cleaned_markdown != raw_markdown,
        model_resolution={"mode": "reannotation", **dict(model_resolution or {})},
        image_reconciliation=image_reconciliation,
    )
    report_payload["mode"] = "reannotation"
    return ReaderCleanupResult(
        changed=cleaned_markdown != raw_markdown,
        raw_markdown=raw_markdown,
        cleaned_markdown=cleaned_markdown,
        report_payload=report_payload,
        accepted_delete_block_ids=(),
    )


def run_reader_cleanup_anchor_repair(
    *,
    markdown_text: str,
    config: ReaderCleanupConfig,
    base_report_payload: Mapping[str, object],
    anchor_targets: Sequence[Mapping[str, object]],
    operation_provider: Callable[[dict[str, Any], int, int], str],
    repair_provider: Callable[[dict[str, Any], int, int], str] | None = None,
    model_resolution: Mapping[str, object] | None = None,
) -> ReaderCleanupResult:
    raw_markdown = str(markdown_text or "")
    blocks = build_cleanup_blocks(raw_markdown)
    if not blocks:
        merged_report = dict(base_report_payload)
        existing_warnings = merged_report.get("warnings")
        if isinstance(existing_warnings, list):
            warnings_list: list[str] = [str(item) for item in existing_warnings]
        else:
            warnings_list = []
        merged_report["warnings"] = [
            *warnings_list,
            "reader_cleanup_anchor_repair_skipped_empty_markdown",
        ]
        return ReaderCleanupResult(
            changed=False,
            raw_markdown=raw_markdown,
            cleaned_markdown=raw_markdown,
            report_payload=merged_report,
            accepted_delete_block_ids=(),
        )

    base_report = dict(base_report_payload)
    base_global_plan = cast(Mapping[str, object], base_report.get("global_plan") or {})
    global_plan = {
        "repeated_noise_patterns": list(cast(Sequence[object], base_global_plan.get("repeated_noise_patterns") or [])),
        "candidate_block_ids": list(cast(Sequence[object], base_global_plan.get("candidate_block_ids") or [])),
        "document_specific_running_headers": list(
            cast(Sequence[object], base_global_plan.get("document_specific_running_headers") or [])
        ),
        "examples_do_not_delete": list(cast(Sequence[object], base_global_plan.get("examples_do_not_delete") or [])),
        "likely_heading_body_patterns": list(cast(Sequence[object], base_global_plan.get("likely_heading_body_patterns") or [])),
        "likely_fragmentation_patterns": list(cast(Sequence[object], base_global_plan.get("likely_fragmentation_patterns") or [])),
        "warnings": list(cast(Sequence[object], base_global_plan.get("warnings") or [])),
    }
    anchor_pass_result = _run_anchor_repair_pass(
        markdown_text=raw_markdown,
        config=config,
        global_plan=global_plan,
        anchor_targets=anchor_targets,
        operation_provider=operation_provider,
        repair_provider=repair_provider,
    )
    merged_report = _merge_anchor_repair_pass_into_report(
        report_payload=base_report,
        raw_markdown=raw_markdown,
        raw_blocks=blocks,
        anchor_pass_result=anchor_pass_result,
    )
    if model_resolution is not None:
        merged_report["model_resolution"] = dict(model_resolution)
    accepted_delete_block_ids = tuple(
        str(entry.get("id") or "")
        for entry in anchor_pass_result.accepted_delete_blocks
        if str(entry.get("id") or "").strip()
    )
    return ReaderCleanupResult(
        changed=anchor_pass_result.cleaned_markdown != raw_markdown,
        raw_markdown=raw_markdown,
        cleaned_markdown=anchor_pass_result.cleaned_markdown,
        report_payload=merged_report,
        accepted_delete_block_ids=accepted_delete_block_ids,
    )


def write_reader_cleanup_diagnostics(
    *,
    cleaned_artifact_paths: Mapping[str, str],
    raw_markdown: str,
    report_payload: Mapping[str, object],
) -> dict[str, str]:
    markdown_path = Path(str(cleaned_artifact_paths["markdown_path"]))
    if markdown_path.name.endswith(".result.md"):
        base_name = markdown_path.name[: -len(".result.md")]
    else:
        base_name = markdown_path.stem

    raw_markdown_path = markdown_path.with_name(f"{base_name}.raw.result.md")
    report_path = markdown_path.with_name(f"{base_name}.reader_cleanup_report.json")

    raw_markdown_path.write_text(raw_markdown, encoding="utf-8")
    try:
        report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        try:
            if raw_markdown_path.exists():
                raw_markdown_path.unlink()
        except OSError:
            pass
        raise

    return {
        "reader_cleanup_raw_markdown_path": str(raw_markdown_path),
        "reader_cleanup_report_path": str(report_path),
    }


def _build_cleanup_chunks(
    *,
    blocks: Sequence[CleanupBlock],
    chunk_size: int,
    overlap_blocks_before: int = 0,
    overlap_blocks_after: int = 0,
) -> list[CleanupChunk]:
    if not blocks:
        return []

    chunks: list[CleanupChunk] = []
    current_blocks: list[CleanupBlock] = []
    current_chars = 0
    chunk_start_position = 0
    for block_position, block in enumerate(blocks):
        separator_chars = 2 if current_blocks else 0
        projected_chars = current_chars + separator_chars + block.char_count
        if current_blocks and projected_chars > chunk_size:
            chunks.append(
                _make_cleanup_chunk(
                    blocks=blocks,
                    selected_blocks=current_blocks,
                    chunk_index=len(chunks) + 1,
                    start_position=chunk_start_position,
                    end_position=block_position - 1,
                    overlap_blocks_before=overlap_blocks_before,
                    overlap_blocks_after=overlap_blocks_after,
                )
            )
            chunk_start_position = block_position
            current_blocks = [block]
            current_chars = block.char_count
            continue

        current_blocks.append(block)
        current_chars = projected_chars

    if current_blocks:
        chunks.append(
            _make_cleanup_chunk(
                blocks=blocks,
                selected_blocks=current_blocks,
                chunk_index=len(chunks) + 1,
                start_position=chunk_start_position,
                end_position=len(blocks) - 1,
                overlap_blocks_before=overlap_blocks_before,
                overlap_blocks_after=overlap_blocks_after,
            )
        )
    return chunks


def _make_cleanup_chunk(
    *,
    blocks: Sequence[CleanupBlock],
    selected_blocks: Sequence[CleanupBlock],
    chunk_index: int,
    start_position: int,
    end_position: int,
    overlap_blocks_before: int = 0,
    overlap_blocks_after: int = 0,
) -> CleanupChunk:
    readonly_before = (
        tuple(blocks[max(0, start_position - overlap_blocks_before) : start_position])
        if overlap_blocks_before > 0
        else ()
    )
    readonly_after = (
        tuple(blocks[end_position + 1 : min(len(blocks), end_position + 1 + overlap_blocks_after)])
        if overlap_blocks_after > 0
        else ()
    )
    adjacent_before = blocks[start_position - 1].text if start_position > 0 else ""
    adjacent_after = blocks[end_position + 1].text if end_position + 1 < len(blocks) else ""
    context_before = "\n\n".join(block.text for block in readonly_before) if readonly_before else adjacent_before
    context_after = "\n\n".join(block.text for block in readonly_after) if readonly_after else adjacent_after
    return CleanupChunk(
        chunk_index=chunk_index,
        start_index=selected_blocks[0].index,
        end_index=selected_blocks[-1].index,
        blocks=tuple(selected_blocks),
        context_before=context_before,
        context_after=context_after,
        context_before_blocks=readonly_before,
        context_after_blocks=readonly_after,
    )


def _readonly_context_blocks_by_id(chunk: CleanupChunk) -> dict[str, CleanupBlock]:
    return {
        block.block_id: block
        for block in (*chunk.context_before_blocks, *chunk.context_after_blocks)
    }


def _normalize_anchor_targets(
    *,
    anchor_targets: Sequence[Mapping[str, object]],
    blocks: Sequence[CleanupBlock],
) -> tuple[list[dict[str, str]], list[str]]:
    block_by_id = {block.block_id: block for block in blocks}
    block_ids = set(block_by_id)
    normalized: list[dict[str, str]] = []
    warnings: list[str] = []
    seen_identity_keys: set[str] = set()
    for index, raw_target in enumerate(anchor_targets, start=1):
        category = str(raw_target.get("category") or "").strip()
        if category not in _ALLOWED_ANCHOR_REPAIR_CATEGORIES:
            warnings.append(f"reader_cleanup_anchor_target_ignored:{index}:unsupported_category")
            continue
        block_id = str(raw_target.get("block_id") or "").strip()
        if not block_id or block_id not in block_ids:
            warnings.append(f"reader_cleanup_anchor_target_ignored:{index}:unknown_block_id")
            continue
        anchor_id = str(raw_target.get("anchor_id") or "").strip()
        line_ref = str(raw_target.get("line_ref") or "").strip()
        snippet = str(raw_target.get("snippet") or "").strip()
        anchor_block = block_by_id[block_id]
        if snippet and snippet not in anchor_block.text:
            snippet_matches = [block for block in blocks if snippet in block.text]
            if len(snippet_matches) == 1:
                warnings.append(
                    f"reader_cleanup_anchor_target_reanchored_by_exact_snippet:{index}:{block_id}->{snippet_matches[0].block_id}"
                )
                block_id = snippet_matches[0].block_id
            elif category == "page_furniture_inline":
                resolved_block = _resolve_page_furniture_caption_anchor_block(
                    snippet=snippet,
                    anchor_block=anchor_block,
                    blocks=blocks,
                )
                if resolved_block is not None:
                    warnings.append(
                        "reader_cleanup_anchor_target_reanchored_by_page_caption_signal:"
                        f"{index}:{block_id}->{resolved_block.block_id}"
                    )
                    block_id = resolved_block.block_id
                else:
                    warnings.append(f"reader_cleanup_anchor_target_snippet_not_in_block:{index}:{block_id}")
            else:
                warnings.append(f"reader_cleanup_anchor_target_snippet_not_in_block:{index}:{block_id}")
        identity_key = anchor_id or f"{category}|{block_id}|{line_ref}|{snippet}"
        if identity_key in seen_identity_keys:
            continue
        seen_identity_keys.add(identity_key)
        normalized.append(
            {
                "anchor_id": anchor_id or f"anchor_{len(normalized) + 1:03d}",
                "category": category,
                "block_id": block_id,
                "line_ref": line_ref,
                "snippet": snippet,
            }
        )
    return normalized, warnings


def _resolve_page_furniture_caption_anchor_block(
    *,
    snippet: str,
    anchor_block: CleanupBlock,
    blocks: Sequence[CleanupBlock],
) -> CleanupBlock | None:
    if not _has_generic_caption_marker(snippet):
        return None

    start_index = max(0, anchor_block.index - 2)
    end_index = min(len(blocks) - 1, anchor_block.index + 2)
    candidates: list[tuple[int, int, CleanupBlock]] = []
    for block in blocks[start_index : end_index + 1]:
        if not _has_generic_caption_marker(block.text):
            continue
        overlap_score = _anchor_overlap_score(snippet=snippet, text=block.text)
        if overlap_score < 4:
            continue
        distance = abs(block.index - anchor_block.index)
        candidates.append((overlap_score, -distance, block))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
        return None
    return candidates[0][2]


def _has_generic_caption_marker(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in ("фото:", "photo:", "photo credit:", "caption:", "иллюстрация:", "рисунок:"))


def _anchor_overlap_score(*, snippet: str, text: str) -> int:
    snippet_tokens = set(_anchor_signal_tokens(snippet))
    if not snippet_tokens:
        return 0
    text_tokens = set(_anchor_signal_tokens(text))
    return len(snippet_tokens & text_tokens)


def _anchor_signal_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9]{4,}", text.lower())
    return [token for token in tokens if not token.isdigit()]


def _build_anchor_repair_chunks(
    *,
    blocks: Sequence[CleanupBlock],
    anchor_targets: Sequence[Mapping[str, str]],
    chunk_size: int,
) -> tuple[list[AnchorRepairChunk], int]:
    if not blocks or not anchor_targets:
        return [], 0

    block_by_id = {block.block_id: block for block in blocks}
    anchor_block_ids = {str(target.get("block_id") or "") for target in anchor_targets}
    selected_indexes: set[int] = set()
    for target in anchor_targets:
        anchor_block_id = str(target.get("block_id") or "")
        block = block_by_id.get(anchor_block_id)
        if block is None:
            continue
        category = str(target.get("category") or "")
        window_radius = 2 if category == "fragmented_paragraph" else 1
        start_index = max(0, block.index - window_radius)
        end_index = min(len(blocks) - 1, block.index + window_radius)
        selected_indexes.update(range(start_index, end_index + 1))

    selected_blocks = [block for block in blocks if block.index in selected_indexes]
    if not selected_blocks:
        return [], 0

    chunks: list[AnchorRepairChunk] = []
    current_blocks: list[CleanupBlock] = []
    current_chars = 0
    for block in selected_blocks:
        separator_chars = 2 if current_blocks else 0
        projected_chars = current_chars + separator_chars + block.char_count
        has_gap = bool(current_blocks) and block.index != current_blocks[-1].index + 1
        if current_blocks and (has_gap or projected_chars > chunk_size):
            base_chunk = _make_manual_cleanup_chunk(blocks=blocks, selected_blocks=current_blocks, chunk_index=len(chunks) + 1)
            chunk_anchor_block_ids = {selected_block.block_id for selected_block in current_blocks} & anchor_block_ids
            chunks.append(
                AnchorRepairChunk(
                    chunk=base_chunk,
                    anchors=tuple(
                        dict(target)
                        for target in anchor_targets
                        if str(target.get("block_id") or "") in chunk_anchor_block_ids
                    ),
                )
            )
            current_blocks = [block]
            current_chars = block.char_count
            continue
        current_blocks.append(block)
        current_chars = projected_chars

    if current_blocks:
        base_chunk = _make_manual_cleanup_chunk(blocks=blocks, selected_blocks=current_blocks, chunk_index=len(chunks) + 1)
        chunk_anchor_block_ids = {selected_block.block_id for selected_block in current_blocks} & anchor_block_ids
        chunks.append(
            AnchorRepairChunk(
                chunk=base_chunk,
                anchors=tuple(
                    dict(target) for target in anchor_targets if str(target.get("block_id") or "") in chunk_anchor_block_ids
                ),
            )
        )

    return chunks, len(selected_blocks)


def _make_manual_cleanup_chunk(
    *,
    blocks: Sequence[CleanupBlock],
    selected_blocks: Sequence[CleanupBlock],
    chunk_index: int,
) -> CleanupChunk:
    start_index = selected_blocks[0].index
    end_index = selected_blocks[-1].index
    return CleanupChunk(
        chunk_index=chunk_index,
        start_index=start_index,
        end_index=end_index,
        blocks=tuple(selected_blocks),
        context_before=blocks[start_index - 1].text if start_index > 0 else "",
        context_after=blocks[end_index + 1].text if end_index + 1 < len(blocks) else "",
    )


def _build_global_plan(
    *,
    blocks: Sequence[CleanupBlock],
    raw_markdown: str,
    config: ReaderCleanupConfig,
    global_plan_provider: Callable[[dict[str, Any]], str] | None,
) -> dict[str, object]:
    repeated_noise_patterns: list[dict[str, object]] = []
    candidate_block_ids: list[str] = []
    warnings: list[str] = []
    ai_plan: dict[str, object] = {
        "repeated_noise_patterns": [],
        "document_specific_running_headers": [],
        "examples_do_not_delete": [],
        "likely_heading_body_patterns": [],
        "likely_fragmentation_patterns": [],
        "warnings": [],
    }
    repeated_counter = Counter(
        block.normalized_text
        for block in blocks
        if 0 < block.char_count <= 120 and not block.is_heading and not block.is_toc_like
    )
    for block in blocks:
        normalized = block.normalized_text
        count = repeated_counter.get(normalized, 0)
        if count < 2:
            continue
        if normalized not in {entry["pattern"] for entry in repeated_noise_patterns}:
            repeated_noise_patterns.append(
                {
                    "pattern": normalized,
                    "reason": _heuristic_reason(block),
                    "confidence": "high" if count >= 3 else "medium",
                    "count": count,
                }
            )
        candidate_block_ids.append(block.block_id)

    if config.keep_toc:
        warnings.append("toc_blocks_protected_keep_toc_true")
    if config.drop_back_matter:
        warnings.append("drop_back_matter_unsupported_noop")

    if config.global_plan_enabled and global_plan_provider is not None:
        try:
            ai_plan = _parse_global_plan_response(
                global_plan_provider(
                    {
                        "raw_markdown": raw_markdown,
                        "block_count": len(blocks),
                        "blocks": [block.to_payload() for block in blocks],
                        "required_fields": list(ai_plan.keys()),
                    }
                )
            )
        except Exception as exc:
            warnings.append(f"reader_cleanup_global_plan_failed:{exc}")

    ai_warnings = ai_plan.get("warnings")
    if isinstance(ai_warnings, list):
        warnings.extend(str(item) for item in ai_warnings if str(item).strip())

    return {
        "repeated_noise_patterns": _coerce_string_list(ai_plan.get("repeated_noise_patterns")) + repeated_noise_patterns,
        "candidate_block_ids": candidate_block_ids,
        "document_specific_running_headers": _coerce_string_list(ai_plan.get("document_specific_running_headers")),
        "examples_do_not_delete": _coerce_string_list(ai_plan.get("examples_do_not_delete")),
        "likely_heading_body_patterns": _coerce_string_list(ai_plan.get("likely_heading_body_patterns")),
        "likely_fragmentation_patterns": _coerce_string_list(ai_plan.get("likely_fragmentation_patterns")),
        "warnings": warnings,
    }


def _parse_global_plan_response(raw_response: str) -> dict[str, object]:
    payload = json.loads(raw_response)
    if not isinstance(payload, dict):
        raise RuntimeError("reader_cleanup_global_plan_must_be_object")
    allowed_fields = {
        "repeated_noise_patterns",
        "document_specific_running_headers",
        "examples_do_not_delete",
        "likely_heading_body_patterns",
        "likely_fragmentation_patterns",
        "warnings",
    }
    unknown_fields = sorted(set(payload.keys()) - allowed_fields)
    if unknown_fields:
        raise RuntimeError(f"reader_cleanup_global_plan_unknown_fields:{','.join(unknown_fields)}")
    normalized: dict[str, object] = {}
    for field in allowed_fields:
        value = payload.get(field, [])
        if not isinstance(value, list):
            raise RuntimeError(f"reader_cleanup_global_plan_field_must_be_list:{field}")
        normalized[field] = value[:50]
    return normalized


def _build_chunk_request_payload(
    *,
    chunk: CleanupChunk,
    global_plan: Mapping[str, object],
    config: ReaderCleanupConfig,
) -> dict[str, object]:
    readonly_before = [block.to_payload() for block in chunk.context_before_blocks]
    readonly_after = [block.to_payload() for block in chunk.context_after_blocks]
    operation_selection_targets = _build_operation_selection_targets(blocks=chunk.blocks)
    allowed_operations = _allowed_operations_for_config(config)
    payload: dict[str, object] = {
        "policy": config.policy,
        "keep_toc": config.keep_toc,
        "drop_back_matter": config.drop_back_matter,
        "cleanup_settings": _serialize_cleanup_settings(config),
        "output_format_requirements": {
            "format": "single_json_object",
            "markdown_fences_allowed": False,
            "prose_before_or_after_json_allowed": False,
            "noop_response": {"cleanup_operations": [], "warnings": []},
        },
        "response_contract": {
            "top_level_fields": ["cleanup_operations", "warnings"],
            "legacy_top_level_fields": ["delete_blocks"],
            "required_cleanup_operation_fields": [
                "id",
                "text_hash",
                "operation",
                "reason",
                "confidence",
                "evidence_before",
                "expected_after_preview",
                "safety_note",
            ],
            "allowed_operations": sorted(allowed_operations),
            "allowed_delete_reasons": sorted(_ALLOWED_DELETE_REASONS),
            "reason_guidance_by_operation": {
                "delete_block": sorted(_ALLOWED_DELETE_REASONS),
                "extract_side_heading_and_reattach_body": ["heading_fused_with_body", "extraction_artifact"],
                "remove_inline_noise": sorted(_REMOVE_INLINE_NOISE_REASON_GUIDANCE),
                "reclassify_role": [
                    "semantic_heading",
                    "semantic_body",
                    "semantic_attribution",
                    "semantic_caption",
                    "role_assignment_correction",
                ],
            },
            "operation_specific_fields": {
                "extract_side_heading_and_reattach_body": [
                    "pre_body_stub",
                    "heading_substring",
                    "post_body_continuation",
                ],
                "split_block": ["split_substrings"],
                "remove_inline_noise": ["noise_substring"],
                "join_fragmented_paragraph": ["next_id", "next_text_hash"],
                "normalize_heading_boundary": ["heading_substring", "body_substring"],
                "reclassify_role": ["target_role"],
            },
            "allowed_reclassify_target_roles": sorted(_ALLOWED_RECLASSIFY_TARGET_ROLES),
            "allowed_confidence": ["low", "medium", "high"],
            "example": {
                "cleanup_operations": [
                    {
                        "id": "b_000123",
                        "text_hash": "7f83b1657ff1fc53",
                        "operation": "delete_block",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "standalone placeholder block",
                        "expected_after_preview": "",
                        "safety_note": "non-semantic extraction artifact only",
                    }
                ],
                "warnings": [],
            },
        },
        "editable_block_ids": [block.block_id for block in chunk.blocks],
        "context_before_preview": chunk.context_before[:240],
        "context_after_preview": chunk.context_after[:240],
        "global_plan": global_plan,
        "operation_selection_targets": operation_selection_targets,
        "blocks": [block.to_payload() for block in chunk.blocks],
    }
    if readonly_before or readonly_after:
        payload.update(
            {
                "readonly_context_block_ids": [block["id"] for block in readonly_before + readonly_after],
                "readonly_context_blocks_before": readonly_before,
                "readonly_context_blocks_after": readonly_after,
            }
        )
    return payload


def _build_reannotation_request_payload(*, chunk: CleanupChunk, config: ReaderCleanupConfig) -> dict[str, object]:
    return {
        "mode": "reannotation",
        "policy": config.policy,
        "cleanup_settings": _serialize_cleanup_settings(config),
        "output_format_requirements": {
            "format": "single_json_object",
            "markdown_fences_allowed": False,
            "noop_response": {"annotations": [], "warnings": []},
        },
        "response_contract": {
            "top_level_fields": ["annotations", "warnings"],
            "required_annotation_fields": ["id", "text_hash", "role", "confidence", "reason"],
            "allowed_roles": sorted(_ALLOWED_REANNOTATION_ROLES),
            "optional_boundary_fields": ["heading_text", "body_text", "marker_text", "list_items"],
            "content_safety": "visible content must be preserved; only role markers and heading/body block boundaries may change",
        },
        "editable_block_ids": [block.block_id for block in chunk.blocks],
        "context_before_preview": chunk.context_before[:240],
        "context_after_preview": chunk.context_after[:240],
        "blocks": [block.to_payload() for block in chunk.blocks],
    }


def _parse_reannotation_response(
    *,
    raw_response: str,
    editable_blocks: Mapping[str, CleanupBlock],
    chunk_index: int,
) -> tuple[list[ReannotationDecision], list[dict[str, object]], list[str]]:
    payload = _load_cleanup_response_object(raw_response)
    if payload is None:
        raise RuntimeError("reader_cleanup_reannotation_response_must_be_json_object")
    annotations = payload.get("annotations")
    if not isinstance(annotations, list):
        raise RuntimeError("reader_cleanup_reannotation_annotations_must_be_list")
    warnings = [str(item) for item in payload.get("warnings") or [] if str(item).strip()] if isinstance(payload.get("warnings"), list) else []
    decisions: list[ReannotationDecision] = []
    ignored: list[dict[str, object]] = []
    for item in annotations:
        if not isinstance(item, Mapping):
            ignored.append({"chunk_index": chunk_index, "ignored_reason": "annotation_not_object"})
            continue
        block_id = str(item.get("id") or "").strip()
        block = editable_blocks.get(block_id)
        role = str(item.get("role") or "").strip()
        text_hash = str(item.get("text_hash") or "").strip()
        confidence = str(item.get("confidence") or "medium").strip().lower()
        if block is None:
            ignored.append({"chunk_index": chunk_index, "id": block_id, "ignored_reason": "unknown_block_id"})
            continue
        if text_hash != block.text_hash:
            ignored.append({"chunk_index": chunk_index, **block.to_payload(), "ignored_reason": "text_hash_mismatch"})
            continue
        if role not in _ALLOWED_REANNOTATION_ROLES:
            ignored.append({"chunk_index": chunk_index, **block.to_payload(), "ignored_reason": "role_invalid", "role": role})
            continue
        if confidence not in _ALLOWED_CONFIDENCE:
            confidence = "medium"
        decisions.append(
            ReannotationDecision(
                block_id=block_id,
                text_hash=text_hash,
                role=role,
                chunk_index=chunk_index,
                heading_text=str(item.get("heading_text") or "").strip(),
                body_text=str(item.get("body_text") or "").strip(),
                marker_text=str(item.get("marker_text") or "").strip(),
                list_items=tuple(
                    str(value).strip()
                    for value in cast(Sequence[object], item.get("list_items") or ())
                    if str(value).strip()
                )
                if isinstance(item.get("list_items"), Sequence)
                and not isinstance(item.get("list_items"), (str, bytes, bytearray))
                else (),
                confidence=cast(CleanupConfidence, confidence),
                reason=str(item.get("reason") or "role_boundary_reannotation").strip(),
            )
        )
    return decisions, ignored, warnings


def _allowed_operations_for_config(config: ReaderCleanupConfig) -> set[str]:
    return set(config.allowed_operations) if config.allowed_operations else set(_ALLOWED_OPERATIONS)


def _build_operation_selection_targets(*, blocks: Sequence[CleanupBlock]) -> list[dict[str, object]]:
    targets: list[dict[str, object]] = []
    for index, block in enumerate(blocks):
        duplicate_target = _build_duplicate_semantic_heading_target(block=block)
        if duplicate_target is not None:
            targets.append(duplicate_target)
        isolated_numeric_heading_target = _build_isolated_semantic_heading_numeric_prefix_target(block=block)
        if isolated_numeric_heading_target is not None:
            targets.append(isolated_numeric_heading_target)
        else:
            semantic_title_target = _build_semantic_page_title_deletion_risk_target(block=block)
            if semantic_title_target is not None:
                targets.append(semantic_title_target)
        next_block = blocks[index + 1] if index + 1 < len(blocks) else None
        heading_fused_target = _build_heading_fused_with_body_target(block=block, next_block=next_block)
        if heading_fused_target is not None:
            targets.append(heading_fused_target)
        targets.extend(_build_side_heading_island_targets(block=block))
    return targets[:20]


def _build_heading_fused_with_body_target(
    *,
    block: CleanupBlock,
    next_block: CleanupBlock | None,
) -> dict[str, object] | None:
    single_block_candidate = _find_heading_fused_with_body_parts(block.text)
    if single_block_candidate is not None:
        return {
            "category": "heading_fused_with_body_candidate",
            "id": block.block_id,
            "text_hash": block.text_hash,
            "preferred_operation": "normalize_heading_boundary",
            "reason_hint": "heading_fused_with_body",
            "heading_substring": single_block_candidate["heading_substring"],
            "body_substring": single_block_candidate["body_substring"],
            "expected_after_preview": single_block_candidate["expected_after_preview"],
            "forbidden_operations": ["remove_inline_noise", "delete_block"],
            "safety_note": "This is a semantic heading/body boundary, not noise. Preserve the full heading and full body text exactly; skip if exact substrings do not match.",
        }

    if next_block is None:
        return None
    wrapped_candidate = _find_wrapped_heading_fused_with_body_parts(block=block, next_block=next_block)
    if wrapped_candidate is None:
        return None
    return {
        "category": "heading_fused_with_body_candidate",
        "id": block.block_id,
        "text_hash": block.text_hash,
        "preferred_operation_chain": ["join_fragmented_paragraph", "normalize_heading_boundary"],
        "reason_hint": "heading_fused_with_body",
        "next_id": next_block.block_id,
        "next_text_hash": next_block.text_hash,
        "heading_substring": wrapped_candidate["heading_substring"],
        "body_substring": wrapped_candidate["body_substring"],
        "expected_after_preview": wrapped_candidate["expected_after_preview"],
        "forbidden_operations": ["remove_inline_noise", "delete_block"],
        "safety_note": "The heading wraps into the adjacent block. Join the exact adjacent block first, then normalize the heading/body boundary; preserve all semantic text.",
    }


def _find_wrapped_heading_fused_with_body_parts(
    *,
    block: CleanupBlock,
    next_block: CleanupBlock,
) -> dict[str, str] | None:
    current_heading = block.text.strip()
    if not current_heading or "\n" in current_heading:
        return None
    if not _looks_like_fused_heading_prefix(current_heading, min_words=2):
        return None
    next_candidate = _find_heading_fused_with_body_parts(next_block.text, min_heading_words=1)
    if next_candidate is None:
        return None
    heading = f"{current_heading} {next_candidate['heading_substring']}".strip()
    if len(heading) > 180:
        return None
    body = next_candidate["body_substring"]
    return {
        "heading_substring": heading,
        "body_substring": body,
        "expected_after_preview": f"{heading}\n\n{body}",
    }


def _find_heading_fused_with_body_parts(text: str, *, min_heading_words: int = 2) -> dict[str, str] | None:
    value = str(text or "").strip()
    if not value or "\n" in value or len(value) < 32:
        return None
    tokens = list(re.finditer(r"[A-Za-zА-Яа-яЁё]{1,}", value))
    if len(tokens) < min_heading_words + 2:
        return None
    max_heading_tokens = min(16, len(tokens) - 1)
    for split_index in range(min_heading_words, max_heading_tokens + 1):
        body_token = tokens[split_index]
        body_word = body_token.group(0)
        if body_word.upper() == body_word:
            continue
        heading = value[: body_token.start()].strip()
        body = value[body_token.start() :].strip()
        if not _looks_like_fused_heading_prefix(heading, min_words=min_heading_words):
            continue
        if not _looks_like_heading_body_remainder(body):
            continue
        return {
            "heading_substring": heading,
            "body_substring": body,
            "expected_after_preview": f"{heading}\n\n{body}",
        }
    return None


def _looks_like_fused_heading_prefix(text: str, *, min_words: int) -> bool:
    value = str(text or "").strip()
    if not value or len(value) > 180:
        return False
    if re.match(r"^(?:[-*]|\d+\.)\s+", value):
        return False
    words = _semantic_word_tokens(value)
    if len(words) < min_words or len(words) > 16:
        return False
    if any(word.isdigit() for word in words):
        return False
    uppercase_words = [word for word in words if word.upper() == word]
    return len(uppercase_words) == len(words)


def _looks_like_heading_body_remainder(text: str) -> bool:
    value = str(text or "").strip()
    if len(value) < 12 or value.startswith(("-", "—", "–", "•")):
        return False
    words = _semantic_word_tokens(value)
    if len(words) < 2:
        return False
    return any(any(char.islower() for char in word) for word in words)


def _build_isolated_semantic_heading_numeric_prefix_target(*, block: CleanupBlock) -> dict[str, object] | None:
    candidate = _find_isolated_semantic_heading_numeric_prefix(block.text)
    if candidate is None or block.is_toc_like:
        return None
    numeric_prefix = candidate["numeric_prefix"]
    heading = candidate["semantic_heading_must_remain"]
    return {
        "category": "isolated_semantic_heading_numeric_prefix",
        "id": block.block_id,
        "text_hash": block.text_hash,
        "preferred_operation": "remove_inline_noise",
        "reason_hint": "page_number",
        "forbidden_operation": "full-heading remove_inline_noise",
        "numeric_prefix": numeric_prefix,
        "semantic_heading_must_remain": heading,
        "expected_after_preview": candidate["expected_after_preview"],
        "safety_note": "Remove only the exact numeric prefix if it is still present once; never remove the semantic heading text.",
    }


def _find_isolated_semantic_heading_numeric_prefix(text: str) -> dict[str, str] | None:
    value = str(text or "").strip()
    if not value or "\n" in value:
        return None
    match = re.match(
        r"^(?P<markdown_prefix>#{1,6}\s*)?(?P<number>\d{1,4})(?P<space>\s+)(?P<heading>.+?)\s*$",
        value,
    )
    if match is None:
        return None
    markdown_prefix = match.group("markdown_prefix") or ""
    numeric_prefix = f"{match.group('number')}{match.group('space')}"
    heading = match.group("heading").strip()
    if not _looks_like_isolated_semantic_heading_text(heading):
        return None
    return {
        "numeric_prefix": numeric_prefix,
        "semantic_heading_must_remain": heading,
        "expected_after_preview": f"{markdown_prefix}{heading}",
    }


def _looks_like_isolated_semantic_heading_text(text: str) -> bool:
    value = str(text or "").strip()
    if not value or len(value) > 120:
        return False
    if re.match(r"^(?:[-*]|\d+\.)\s+", value):
        return False
    words = _semantic_word_tokens(value)
    if len(words) > 12:
        return False
    if any(word.isdigit() for word in words):
        return False
    if len(words) == 1:
        return len(words[0]) >= 4 and words[0].upper() == words[0]
    uppercase_words = [word for word in words if word.upper() == word]
    if len(uppercase_words) == len(words):
        return True
    return len(words) <= 6 and sum(1 for word in words if word[0].isupper()) >= 2


def _build_duplicate_semantic_heading_target(*, block: CleanupBlock) -> dict[str, object] | None:
    duplicate = _find_adjacent_duplicate_phrase(block.text)
    if duplicate is None:
        return None
    noise_substring = duplicate["noise_substring"]
    return {
        "category": "duplicate_semantic_heading_text",
        "id": block.block_id,
        "text_hash": block.text_hash,
        "operation_hint": "remove_inline_noise",
        "reason_hint": "duplicate_fragment",
        "noise_substring": noise_substring,
        "expected_after_preview": _inline_noise_removed_text(current_text=block.text, noise=noise_substring),
        "safety_note": "Apply only if this exact adjacent repeated phrase is still present once in the editable block.",
    }


def _find_adjacent_duplicate_phrase(text: str) -> dict[str, str] | None:
    tokens = list(re.finditer(r"[A-Za-zА-Яа-яЁё]{2,}", text or ""))
    if len(tokens) < 4:
        return None
    for phrase_len in range(8, 1, -1):
        if len(tokens) < phrase_len * 2:
            continue
        for start in range(0, len(tokens) - (phrase_len * 2) + 1):
            first = tokens[start : start + phrase_len]
            second = tokens[start + phrase_len : start + (phrase_len * 2)]
            first_words = [match.group(0).lower() for match in first]
            second_words = [match.group(0).lower() for match in second]
            if first_words != second_words:
                continue
            noise_start = second[0].start()
            noise_end = second[-1].end()
            while noise_end < len(text) and text[noise_end].isspace():
                noise_end += 1
            return {"noise_substring": text[noise_start:noise_end]}
    return None


def _build_semantic_page_title_deletion_risk_target(*, block: CleanupBlock) -> dict[str, object] | None:
    if block.is_toc_like or block.char_count < 20:
        return None
    candidate = _find_trailing_page_like_semantic_title(block.text)
    if candidate is None:
        return None
    return {
        "category": "semantic_page_title_deletion_risk",
        "id": block.block_id,
        "text_hash": block.text_hash,
        "semantic_title_candidate": candidate["semantic_title_candidate"],
        "page_like_number": candidate["page_like_number"],
        "numeric_prefix": candidate["numeric_prefix"],
        "forbidden_operation": "remove_inline_noise",
        "operation_hint": "preserve_title_with_exact_structural_operation_or_skip",
        "after_structural_split_followup_operation": "remove_inline_noise",
        "same_pass_followup_supported": True,
        "followup_targets_same_original_block_id": True,
        "after_structural_split_noise_substring": candidate["numeric_prefix"],
        "semantic_heading_must_remain_after_followup": candidate["semantic_title_candidate"],
        "after_structural_split_expected_after_preview": candidate["semantic_title_candidate"],
        "safety_note": "A page-like number adjacent to a semantic section title is not enough to classify the title as noise. Do not delete the title with remove_inline_noise; remove only exact non-semantic page residue if safe, or skip with a warning.",
    }


def _find_trailing_page_like_semantic_title(text: str) -> dict[str, str] | None:
    value = str(text or "").strip()
    if not value:
        return None
    match = re.search(
        r"(?P<candidate>(?P<number>\d{1,4})\s+"
        r"(?P<title>[A-ZА-ЯЁ][A-ZА-ЯЁ0-9«»\"'(),:;!?-]*"
        r"(?:\s+[A-ZА-ЯЁ][A-ZА-ЯЁ0-9«»\"'(),:;!?-]*){1,9}"
        r"[.!?…]?))\s*$",
        value,
    )
    if match is None:
        return None
    candidate = match.group("candidate").strip()
    title = match.group("title").strip()
    words = _semantic_word_tokens(title)
    if len(words) < 2 or len(words) > 10:
        return None
    if not all(word.upper() == word for word in words):
        return None
    if match.start("candidate") == 0 and _looks_like_numeric_uppercase_running_header_noise(
        normalized_noise=candidate,
        current_text=value,
    ):
        return None
    return {
        "page_like_number": match.group("number"),
        "numeric_prefix": f"{match.group('number')} ",
        "semantic_title_candidate": title,
    }


def _build_side_heading_island_targets(*, block: CleanupBlock) -> list[dict[str, object]]:
    if block.is_heading or block.is_toc_like or block.char_count < 40:
        return []
    targets: list[dict[str, object]] = []
    tokens = list(re.finditer(r"[A-Za-zА-Яа-яЁё]{2,}", block.text))
    if len(tokens) < 6:
        return []
    for phrase_len in range(3, 6):
        for start in range(1, len(tokens) - phrase_len):
            phrase_tokens = tokens[start : start + phrase_len]
            before_text = block.text[: phrase_tokens[0].start()]
            after_text = block.text[phrase_tokens[-1].end() :]
            if not _has_side_heading_left_context(before_text):
                continue
            if not _has_side_heading_right_context(after_text):
                continue
            phrase = block.text[phrase_tokens[0].start() : phrase_tokens[-1].end()]
            if not _looks_like_side_heading_phrase(phrase):
                continue
            targets.append(
                {
                    "category": "side_heading_island_candidate",
                    "id": block.block_id,
                    "text_hash": block.text_hash,
                    "heading_candidate": phrase,
                    "operation_hint": "preserve_heading_text_with_split_block_or_normalize_heading_boundary",
                    "preferred_operation_order": ["split_block", "normalize_heading_boundary"],
                    "reattach_operation_hint": "extract_side_heading_and_reattach_body",
                    "forbidden_default_operation": "remove_inline_noise",
                    "stub_continuation_risk": "If this heading interrupts one sentence, do not leave a pre-heading stub or orphan post-heading continuation; use exact reattach operation or skip.",
                    "reattach_expected_after_preview_shape": "heading_substring + blank line + pre_body_stub + space + post_body_continuation; no labels and no body-first preview.",
                    "safety_note": "Semantic heading islands are not noise. Do not delete with remove_inline_noise; preserve all semantic text with exact extract_side_heading_and_reattach_body, split_block, or normalize_heading_boundary, or skip if boundaries are unclear.",
                }
            )
            if len(targets) >= 3:
                return targets
    return targets


def _has_side_heading_left_context(text: str) -> bool:
    before = str(text or "").rstrip()
    if not before:
        return False
    if before[-1] in ".!?;:…":
        return False
    return re.search(r"[a-zа-яё][,\s\"'«»“”„-]*$", before) is not None


def _has_side_heading_right_context(text: str) -> bool:
    after = str(text or "").lstrip()
    return re.match(r"[a-zа-яё]", after) is not None


def _looks_like_side_heading_phrase(phrase: str) -> bool:
    if re.search(r"\b(?:and|for|from|in|of|or|the|to|в|во|для|и|или|к|на|о|от|по|с|со|у)\b", phrase, re.IGNORECASE):
        return False
    words = _semantic_word_tokens(phrase)
    if len(words) < 3 or len(words) > 5:
        return False
    if any(word.isdigit() for word in words):
        return False
    if not words[0][0].isupper():
        return False
    uppercase_count = sum(1 for word in words if word[0].isupper())
    return uppercase_count == 1


def _build_failed_chunk_diagnostics(
    *,
    chunk: CleanupChunk,
    config: ReaderCleanupConfig,
    request_payload_char_count: int,
    raw_response: str,
    parse_error_message: str,
    retry_attempted: bool,
    retry_status: str,
    retry_error: str,
    repair_attempted: bool,
    repair_status: str,
    repair_error: str,
) -> dict[str, object]:
    stripped_response = str(raw_response or "").strip()
    return {
        "chunk_index": chunk.chunk_index,
        "primary_block_id_range": {
            "first": chunk.blocks[0].block_id if chunk.blocks else "",
            "last": chunk.blocks[-1].block_id if chunk.blocks else "",
        },
        "cleanup_model_selector": config.model,
        "request_payload_char_count": request_payload_char_count,
        "approx_prompt_input_char_count": request_payload_char_count,
        "raw_response_empty": not bool(stripped_response),
        "raw_response_char_count": len(raw_response or ""),
        "raw_response_preview": _preview_text(raw_response, limit=1000),
        "parse_error_message": parse_error_message,
        "retry_attempted": retry_attempted,
        "retry_status": retry_status,
        "retry_error": retry_error,
        "repair_attempted": repair_attempted,
        "repair_status": repair_status,
        "repair_error": repair_error,
    }


def _preview_text(value: object, *, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _build_anchor_repair_request_payload(
    *,
    chunk: CleanupChunk,
    anchors: Sequence[Mapping[str, str]],
    global_plan: Mapping[str, object],
    config: ReaderCleanupConfig,
) -> dict[str, object]:
    payload = _build_chunk_request_payload(chunk=chunk, global_plan=global_plan, config=config)
    payload.update(
        {
            "pass_name": "anchor_repair",
            "anchor_targets": [dict(anchor) for anchor in anchors],
            "anchor_window_block_ids": [block.block_id for block in chunk.blocks],
        }
    )
    return payload


def _build_cleanup_stats(
    *,
    raw_markdown: str,
    blocks: Sequence[CleanupBlock],
    accepted_delete_blocks: Sequence[Mapping[str, object]],
    accepted_cleanup_operations: Sequence[Mapping[str, object]],
    ignored_cleanup_operations: Sequence[Mapping[str, object]],
    chunk_results: Sequence[Mapping[str, object]],
    deleted_char_count: int,
) -> dict[str, object]:
    total_non_whitespace_chars = sum(block.non_whitespace_char_count for block in blocks)
    failed_chunk_count = sum(1 for entry in chunk_results if entry.get("status") == "failed")
    proposed_cleanup_operation_count = sum(
        _coerce_int(
            entry.get("proposed_cleanup_operation_count", entry.get("proposed_delete_block_count")),
            default=0,
            minimum=0,
        )
        for entry in chunk_results
    )
    proposed_delete_block_count = sum(
        _coerce_int(entry.get("proposed_delete_block_count"), default=0, minimum=0) for entry in chunk_results
    )
    accepted_reclassify_role_count = sum(
        1 for entry in accepted_cleanup_operations if entry.get("operation") == "reclassify_role"
    )
    return {
        "raw_block_count": len(blocks),
        "raw_char_count": len(raw_markdown),
        "cleanup_chunk_count": len(chunk_results),
        "failed_chunk_count": failed_chunk_count,
        "proposed_cleanup_operation_count": proposed_cleanup_operation_count,
        "proposed_delete_block_count": proposed_delete_block_count,
        "accepted_cleanup_operation_count": len(accepted_cleanup_operations),
        "accepted_delete_block_count": len(accepted_delete_blocks),
        "accepted_reclassify_role_count": accepted_reclassify_role_count,
        "ignored_cleanup_operation_count": len(ignored_cleanup_operations),
        "ignored_delete_block_count": len(ignored_cleanup_operations),
        "deleted_non_whitespace_char_count": deleted_char_count,
        "deleted_char_ratio": 0.0 if total_non_whitespace_chars <= 0 else round(deleted_char_count / total_non_whitespace_chars, 6),
    }


def _extract_docx_image_placeholder_ids(text: str) -> list[str]:
    ids: list[str] = []
    for match in _DOCX_IMAGE_PLACEHOLDER_PATTERN.finditer(str(text or "")):
        placeholder = match.group(0)
        image_id = placeholder[len("[[DOCX_IMAGE_") : -len("]]")]
        ids.append(image_id)
    return ids


def _docx_image_placeholder_counts(text: str) -> Counter[str]:
    return Counter(_extract_docx_image_placeholder_ids(text))


def _reconcile_docx_image_placeholders(
    *,
    raw_markdown: str,
    cleaned_markdown: str,
    raw_blocks: Sequence[CleanupBlock],
) -> tuple[str, dict[str, object]]:
    before_counts = _docx_image_placeholder_counts(raw_markdown)
    after_counts = _docx_image_placeholder_counts(cleaned_markdown)
    missing_ids = sorted((before_counts - after_counts).elements())
    extra_ids = sorted((after_counts - before_counts).elements())
    if not missing_ids:
        return cleaned_markdown, {
            "before_image_id_count": sum(before_counts.values()),
            "after_image_id_count": sum(after_counts.values()),
            "missing_image_ids": [],
            "missing_after_repair": [],
            "extra_image_ids": extra_ids,
            "reinserted_image_ids": [],
            "touched": bool(extra_ids),
        }

    missing_counter = Counter(missing_ids)
    reinsertion_blocks: list[str] = []
    for block in raw_blocks:
        block_ids = _extract_docx_image_placeholder_ids(block.text)
        if not block_ids:
            continue
        selected_ids: list[str] = []
        for image_id in block_ids:
            if missing_counter[image_id] <= 0:
                continue
            missing_counter[image_id] -= 1
            selected_ids.append(image_id)
        if selected_ids:
            reinsertion_blocks.append("\n".join(f"[[DOCX_IMAGE_{image_id}]]" for image_id in selected_ids))

    rebuilt = cleaned_markdown.strip()
    if reinsertion_blocks:
        rebuilt = "\n\n".join([part for part in [rebuilt, *reinsertion_blocks] if part.strip()])

    reconciled_counts = _docx_image_placeholder_counts(rebuilt)
    remaining_missing_ids = sorted((before_counts - reconciled_counts).elements())
    return rebuilt, {
        "before_image_id_count": sum(before_counts.values()),
        "after_image_id_count": sum(reconciled_counts.values()),
        "missing_image_ids": missing_ids,
        "missing_after_repair": remaining_missing_ids,
        "extra_image_ids": extra_ids,
        "reinserted_image_ids": sorted((reconciled_counts - after_counts).elements()),
        "touched": True,
    }


def _image_reconciliation_warnings(image_reconciliation: Mapping[str, object]) -> list[str]:
    missing = [str(item) for item in image_reconciliation.get("missing_image_ids") or [] if str(item).strip()]
    remaining = [str(item) for item in image_reconciliation.get("missing_after_repair") or [] if str(item).strip()]
    extra = [str(item) for item in image_reconciliation.get("extra_image_ids") or [] if str(item).strip()]
    warnings: list[str] = []
    if missing:
        warnings.append(f"reader_cleanup_image_ids_reinserted:{len(missing)}")
    if remaining:
        warnings.append(f"reader_cleanup_image_ids_missing_after_reconcile:{len(remaining)}")
    if extra:
        warnings.append(f"reader_cleanup_image_ids_extra_after_cleanup:{len(extra)}")
    return warnings


def _extract_http_status_code(exc: BaseException) -> int | None:
    visited: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        status_code = getattr(current, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(current, "response", None)
        response_status_code = getattr(response, "status_code", None)
        if isinstance(response_status_code, int):
            return response_status_code
        current = current.__cause__ or current.__context__
    return None


def _is_auth_or_credential_error(exc: BaseException) -> bool:
    status_code = _extract_http_status_code(exc)
    if status_code in {401, 403}:
        return True
    return any(type(current).__name__ in {"AuthenticationError", "PermissionDeniedError"} for current in _iter_exception_chain(exc))


def _iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    visited: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _failed_chunk_ratio(chunk_results: Sequence[Mapping[str, object]]) -> float:
    if not chunk_results:
        return 0.0
    failed_chunk_count = sum(1 for entry in chunk_results if entry.get("status") == "failed")
    return failed_chunk_count / len(chunk_results)


def _failed_chunk_ratio_exceeds_threshold(
    *,
    chunk_results: Sequence[Mapping[str, object]],
    config: ReaderCleanupConfig,
) -> bool:
    if not chunk_results:
        return False
    threshold = min(1.0, max(0.0, float(config.max_failed_chunk_ratio)))
    return _failed_chunk_ratio(chunk_results) >= threshold


def _serialize_cleanup_settings(config: ReaderCleanupConfig) -> dict[str, object]:
    return {
        "model_selector": config.model,
        "chunk_size": config.chunk_size,
        "overlap_blocks_before": config.overlap_blocks_before,
        "overlap_blocks_after": config.overlap_blocks_after,
        "global_plan_enabled": config.global_plan_enabled,
        "allowed_operations": sorted(config.allowed_operations),
        "max_reclassify_block_ratio": config.max_reclassify_block_ratio,
        "max_failed_chunk_ratio": config.max_failed_chunk_ratio,
    }


def _build_reader_cleanup_report_payload(
    *,
    raw_markdown: str,
    config: ReaderCleanupConfig,
    blocks: Sequence[CleanupBlock],
    global_plan: Mapping[str, object],
    warnings: Sequence[str],
    accepted_delete_blocks: Sequence[Mapping[str, object]],
    accepted_cleanup_operations: Sequence[Mapping[str, object]] = (),
    ignored_cleanup_operations: Sequence[Mapping[str, object]],
    chunk_results: Sequence[Mapping[str, object]],
    deleted_char_count: int,
    changed: bool,
    model_resolution: Mapping[str, object] | None = None,
    image_reconciliation: Mapping[str, object] | None = None,
    failure: Mapping[str, object] | None = None,
) -> dict[str, object]:
    stats = _build_cleanup_stats(
        raw_markdown=raw_markdown,
        blocks=blocks,
        accepted_delete_blocks=accepted_delete_blocks,
        accepted_cleanup_operations=accepted_cleanup_operations,
        ignored_cleanup_operations=ignored_cleanup_operations,
        chunk_results=chunk_results,
        deleted_char_count=deleted_char_count,
    )
    report_payload = {
        "version": 1,
        "policy": config.policy,
        "model": config.model,
        "cleanup_settings": _serialize_cleanup_settings(config),
        "stage_status": "failed" if failure is not None else "completed",
        "changed": changed,
        "warnings": list(warnings),
        "stats": stats,
        "global_plan": dict(global_plan),
        "model_resolution": dict(model_resolution or {}),
        "image_reconciliation": dict(image_reconciliation or {}),
        "accepted_cleanup_operations": list(accepted_cleanup_operations),
        "accepted_delete_blocks": list(accepted_delete_blocks),
        "ignored_cleanup_operations": list(ignored_cleanup_operations),
        "ignored_delete_blocks": list(ignored_cleanup_operations),
        "heading_boundary_application_diagnostics": _build_heading_boundary_application_diagnostics(
            accepted_cleanup_operations=accepted_cleanup_operations,
            ignored_cleanup_operations=ignored_cleanup_operations,
        ),
        "chunk_results": [dict(entry) for entry in chunk_results],
    }
    if failure is not None:
        report_payload["failure"] = dict(failure)
    return report_payload


def _build_heading_boundary_application_diagnostics(
    *,
    accepted_cleanup_operations: Sequence[Mapping[str, object]],
    ignored_cleanup_operations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    accepted_heading_operations = [
        dict(entry) for entry in accepted_cleanup_operations if entry.get("operation") == "normalize_heading_boundary"
    ]
    ignored_heading_operations = [
        dict(entry) for entry in ignored_cleanup_operations if entry.get("operation") == "normalize_heading_boundary"
    ]
    ignored_reason_counts: Counter[str] = Counter(
        str(entry.get("ignored_reason") or "unknown") for entry in ignored_heading_operations
    )
    return {
        "accepted_count": len(accepted_heading_operations),
        "ignored_count": len(ignored_heading_operations),
        "ignored_reason_counts": dict(sorted(ignored_reason_counts.items())),
        "ignored_examples": [
            _build_heading_boundary_diagnostic_example(entry)
            for entry in ignored_heading_operations[:5]
        ],
    }


def _build_heading_boundary_diagnostic_example(entry: Mapping[str, object]) -> dict[str, object]:
    preview = str(entry.get("raw_text_preview") or entry.get("evidence_before") or "").replace("\n", " ").strip()
    if len(preview) > 180:
        preview = preview[:177].rstrip() + "..."
    heading = str(entry.get("heading_substring") or "").replace("\n", " ").strip()
    body = str(entry.get("body_substring") or "").replace("\n", " ").strip()
    if len(body) > 180:
        body = body[:177].rstrip() + "..."
    return {
        "chunk_index": _coerce_int(entry.get("chunk_index"), default=0, minimum=0),
        "ignored_reason": str(entry.get("ignored_reason") or "unknown"),
        "reason": str(entry.get("reason") or ""),
        "preview": preview,
        "heading_substring": heading,
        "body_substring_preview": body,
    }


def _load_cleanup_response_object(raw_response: str) -> dict[str, object] | None:
    try:
        payload = _load_cleanup_response_payload(raw_response)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return cast(dict[str, object], payload)


def _load_cleanup_response_payload(raw_response: str) -> object:
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        extracted = _extract_first_json_object_text(raw_response)
        if extracted is None:
            raise
        return json.loads(extracted)


def _extract_first_json_object_text(raw_response: str) -> str | None:
    text = str(raw_response or "")
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _build_cleanup_schema_repair_payload(
    *,
    request_payload: Mapping[str, object],
    original_response: Mapping[str, object],
    validation_error: str,
) -> dict[str, object]:
    payload = {
        "task": "repair_cleanup_response_schema",
        "pass_name": str(request_payload.get("pass_name") or "first_pass"),
        "response_contract": dict(cast(Mapping[str, object], request_payload.get("response_contract") or {})),
        "editable_block_ids": [str(item) for item in cast(Sequence[object], request_payload.get("editable_block_ids") or [])],
        "context_before_preview": str(request_payload.get("context_before_preview") or ""),
        "context_after_preview": str(request_payload.get("context_after_preview") or ""),
        "blocks": [dict(cast(Mapping[str, object], item)) for item in cast(Sequence[object], request_payload.get("blocks") or []) if isinstance(item, Mapping)],
        "validation_error": validation_error,
        "original_response": dict(original_response),
    }
    for key in ("readonly_context_block_ids", "readonly_context_blocks_before", "readonly_context_blocks_after"):
        value = request_payload.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            payload[key] = [
                dict(cast(Mapping[str, object], item)) if isinstance(item, Mapping) else str(item)
                for item in value
            ]
    anchor_targets = request_payload.get("anchor_targets")
    if isinstance(anchor_targets, Sequence) and not isinstance(anchor_targets, (str, bytes, bytearray)):
        payload["anchor_targets"] = [
            dict(cast(Mapping[str, object], item))
            for item in anchor_targets
            if isinstance(item, Mapping)
        ]
    anchor_window_block_ids = request_payload.get("anchor_window_block_ids")
    if isinstance(anchor_window_block_ids, Sequence) and not isinstance(anchor_window_block_ids, (str, bytes, bytearray)):
        payload["anchor_window_block_ids"] = [str(item) for item in anchor_window_block_ids]
    return payload


def _run_anchor_repair_pass(
    *,
    markdown_text: str,
    config: ReaderCleanupConfig,
    global_plan: Mapping[str, object],
    anchor_targets: Sequence[Mapping[str, object]],
    operation_provider: Callable[[dict[str, Any], int, int], str],
    repair_provider: Callable[[dict[str, Any], int, int], str] | None,
) -> AnchorRepairPassResult:
    raw_markdown = str(markdown_text or "")
    blocks = build_cleanup_blocks(raw_markdown)
    normalized_targets, warnings = _normalize_anchor_targets(anchor_targets=anchor_targets, blocks=blocks)
    anchor_chunks, selected_window_block_count = _build_anchor_repair_chunks(
        blocks=blocks,
        anchor_targets=normalized_targets,
        chunk_size=config.chunk_size,
    )
    if not anchor_chunks:
        return AnchorRepairPassResult(
            cleaned_markdown=raw_markdown,
            warnings=tuple(warnings),
            accepted_delete_blocks=(),
            accepted_cleanup_operations=(),
            ignored_cleanup_operations=(),
            chunk_results=(),
            deleted_char_count=0,
            requested_anchor_count=len(anchor_targets),
            selected_anchor_count=len(normalized_targets),
            selected_window_block_count=selected_window_block_count,
            selected_anchors=tuple(normalized_targets),
        )

    all_operations: list[CleanupOperation] = []
    ignored_cleanup_operations: list[dict[str, object]] = []
    chunk_results: list[dict[str, object]] = []
    for anchor_chunk in anchor_chunks:
        chunk = anchor_chunk.chunk
        request_payload = _build_anchor_repair_request_payload(
            chunk=chunk,
            anchors=anchor_chunk.anchors,
            global_plan=global_plan,
            config=config,
        )
        started_at = time.perf_counter()
        raw_response = ""
        schema_validation_error = ""
        repair_error = ""
        repair_attempted = False
        repair_status = "not_attempted"
        ignored_chunk_operations: list[dict[str, object]] = []
        try:
            raw_response = operation_provider(request_payload, chunk.chunk_index, len(anchor_chunks))
            editable_blocks = {block.block_id: block for block in chunk.blocks}
            try:
                operations, chunk_warnings, ignored_chunk_operations = _parse_cleanup_response(
                    raw_response=raw_response,
                    editable_blocks=editable_blocks,
                    chunk_index=chunk.chunk_index,
                )
            except Exception as exc:
                original_response_payload = _load_cleanup_response_object(raw_response)
                if repair_provider is None or original_response_payload is None:
                    raise
                schema_validation_error = str(exc)
                repair_attempted = True
                repair_status = "attempted"
                warnings.append(
                    f"reader_cleanup_anchor_schema_validation_failed:{chunk.chunk_index}:{schema_validation_error}"
                )
                warnings.append(f"reader_cleanup_anchor_schema_repair_attempted:{chunk.chunk_index}")
                repaired_response = repair_provider(
                    _build_cleanup_schema_repair_payload(
                        request_payload=request_payload,
                        original_response=original_response_payload,
                        validation_error=schema_validation_error,
                    ),
                    chunk.chunk_index,
                    len(anchor_chunks),
                )
                try:
                    operations, chunk_warnings, ignored_chunk_operations = _parse_cleanup_response(
                        raw_response=repaired_response,
                        editable_blocks=editable_blocks,
                        chunk_index=chunk.chunk_index,
                    )
                except Exception as repair_exc:
                    repair_status = "failed"
                    repair_error = str(repair_exc)
                    warnings.append(f"reader_cleanup_anchor_schema_repair_failed:{chunk.chunk_index}:{repair_error}")
                    raise
                repair_status = "succeeded"
                warnings.append(f"reader_cleanup_anchor_schema_repair_succeeded:{chunk.chunk_index}")
        except Exception as exc:
            warnings.append(f"reader_cleanup_anchor_chunk_failed:{chunk.chunk_index}:{exc}")
            chunk_results.append(
                {
                    "pass_name": "anchor_repair",
                    "chunk_index": chunk.chunk_index,
                    "status": "failed",
                    "target_block_count": len(chunk.blocks),
                    "target_chars": sum(block.char_count for block in chunk.blocks),
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    "proposed_cleanup_operation_count": 0,
                    "proposed_delete_block_count": 0,
                    "accepted_cleanup_operation_count": 0,
                    "accepted_delete_block_count": 0,
                    "ignored_cleanup_operation_count": 0,
                    "ignored_delete_block_count": 0,
                    "repair_attempted": repair_attempted,
                    "repair_status": repair_status,
                    "schema_validation_error": schema_validation_error,
                    "repair_error": repair_error,
                    "anchor_ids": [str(anchor.get("anchor_id") or "") for anchor in anchor_chunk.anchors],
                    "warning": f"reader_cleanup_anchor_chunk_failed:{chunk.chunk_index}:{exc}",
                }
            )
            continue

        operations, scope_ignored_operations = _filter_anchor_repair_operations_to_anchor_targets(
            operations=operations,
            anchors=anchor_chunk.anchors,
            editable_blocks=editable_blocks,
        )
        all_operations.extend(operations)
        warnings.extend(chunk_warnings)
        ignored_cleanup_operations.extend(ignored_chunk_operations)
        ignored_cleanup_operations.extend(scope_ignored_operations)
        chunk_results.append(
            {
                "pass_name": "anchor_repair",
                "chunk_index": chunk.chunk_index,
                "status": "completed",
                "target_block_count": len(chunk.blocks),
                "target_chars": sum(block.char_count for block in chunk.blocks),
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "proposed_cleanup_operation_count": len(operations)
                + len(ignored_chunk_operations)
                + len(scope_ignored_operations),
                "proposed_delete_block_count": sum(1 for operation in operations if operation.operation == "delete_block")
                + sum(1 for operation in scope_ignored_operations if operation.get("operation") == "delete_block"),
                "accepted_cleanup_operation_count": 0,
                "accepted_delete_block_count": 0,
                "ignored_cleanup_operation_count": 0,
                "ignored_delete_block_count": 0,
                "repair_attempted": repair_attempted,
                "repair_status": repair_status,
                "schema_validation_error": schema_validation_error,
                "repair_error": repair_error,
                "anchor_ids": [str(anchor.get("anchor_id") or "") for anchor in anchor_chunk.anchors],
            }
        )

    cleaned_markdown, accepted_ids, accepted_cleanup_operations, apply_ignored_cleanup_operations = _apply_cleanup_operations(
        raw_markdown=raw_markdown,
        blocks=blocks,
        operations=all_operations,
        config=config,
        global_candidate_block_ids={block.block_id for anchor_chunk in anchor_chunks for block in anchor_chunk.chunk.blocks},
    )
    ignored_cleanup_operations.extend(apply_ignored_cleanup_operations)
    accepted_counts_by_chunk: Counter[int] = Counter()
    accepted_delete_blocks: list[dict[str, object]] = []
    for block_id, entry in accepted_ids.items():
        block = _block_by_id(blocks, block_id)
        chunk_index = _coerce_int(entry.get("chunk_index"), default=0, minimum=0)
        accepted_delete_blocks.append(
            {
                **_serialize_delete_block(block=block, reason=str(entry["reason"]), confidence=str(entry["confidence"])),
                "pass_name": "anchor_repair",
                "chunk_index": chunk_index,
                "after_state": "deleted",
            }
        )
        accepted_counts_by_chunk[chunk_index] += 1

    ignored_counts_by_chunk: Counter[int] = Counter()
    for entry in ignored_cleanup_operations:
        chunk_index = entry.get("chunk_index")
        if isinstance(chunk_index, int):
            ignored_counts_by_chunk[chunk_index] += 1

    normalized_accepted_cleanup_operations = [
        {**entry, "pass_name": "anchor_repair"} for entry in accepted_cleanup_operations
    ]
    normalized_ignored_cleanup_operations = [{**entry, "pass_name": "anchor_repair"} for entry in ignored_cleanup_operations]

    for chunk_result in chunk_results:
        chunk_index = chunk_result.get("chunk_index")
        if not isinstance(chunk_index, int) or chunk_result.get("status") != "completed":
            continue
        accepted_cleanup_count = sum(
            1 for entry in normalized_accepted_cleanup_operations if entry.get("chunk_index") == chunk_index
        )
        chunk_result["accepted_delete_block_count"] = accepted_counts_by_chunk.get(chunk_index, 0)
        chunk_result["accepted_cleanup_operation_count"] = accepted_cleanup_count
        chunk_result["ignored_delete_block_count"] = ignored_counts_by_chunk.get(chunk_index, 0)
        chunk_result["ignored_cleanup_operation_count"] = ignored_counts_by_chunk.get(chunk_index, 0)

    deleted_char_count = sum(_block_by_id(blocks, block_id).non_whitespace_char_count for block_id in accepted_ids)
    return AnchorRepairPassResult(
        cleaned_markdown=cleaned_markdown,
        warnings=tuple(warnings),
        accepted_delete_blocks=tuple(accepted_delete_blocks),
        accepted_cleanup_operations=tuple(normalized_accepted_cleanup_operations),
        ignored_cleanup_operations=tuple(normalized_ignored_cleanup_operations),
        chunk_results=tuple(chunk_results),
        deleted_char_count=deleted_char_count,
        requested_anchor_count=len(anchor_targets),
        selected_anchor_count=len(normalized_targets),
        selected_window_block_count=selected_window_block_count,
        selected_anchors=tuple(normalized_targets),
    )


def _filter_anchor_repair_operations_to_anchor_targets(
    *,
    operations: Sequence[CleanupOperation],
    anchors: Sequence[Mapping[str, str]],
    editable_blocks: Mapping[str, CleanupBlock],
) -> tuple[list[CleanupOperation], list[dict[str, object]]]:
    anchor_categories_by_block: dict[str, set[str]] = {}
    for anchor in anchors:
        block_id = str(anchor.get("block_id") or "")
        category = str(anchor.get("category") or "")
        if block_id and category:
            anchor_categories_by_block.setdefault(block_id, set()).add(category)
    anchor_block_ids = set(anchor_categories_by_block)
    page_anchor_block_ids = {
        block_id
        for block_id, categories in anchor_categories_by_block.items()
        if "page_furniture_inline" in categories
    }
    page_anchor_blocks_with_noise_removal = {
        operation.block_id
        for operation in operations
        if operation.operation == "remove_inline_noise"
        and operation.block_id in page_anchor_block_ids
        and operation.reason in _INLINE_NOISE_REASON_GUIDANCE
    }

    filtered_operations: list[CleanupOperation] = []
    ignored_operations: list[dict[str, object]] = []
    for operation in operations:
        ignored_reason = ""
        if operation.block_id not in anchor_block_ids and not _is_allowed_page_anchor_followup_join(
            operation=operation,
            page_anchor_blocks_with_noise_removal=page_anchor_blocks_with_noise_removal,
            editable_blocks=editable_blocks,
        ):
            ignored_reason = "anchor_repair_operation_outside_anchor_targets"
        elif (
            "page_furniture_inline" in anchor_categories_by_block.get(operation.block_id, set())
            and operation.operation in {"delete_block", "join_fragmented_paragraph"}
            and not _is_allowed_page_anchor_followup_join(
                operation=operation,
                page_anchor_blocks_with_noise_removal=page_anchor_blocks_with_noise_removal,
                editable_blocks=editable_blocks,
            )
        ):
            ignored_reason = "anchor_repair_page_furniture_requires_remove_inline_noise"

        if not ignored_reason:
            filtered_operations.append(operation)
            continue

        block = editable_blocks.get(operation.block_id)
        if block is None:
            ignored_operations.append(
                {
                    "id": operation.block_id,
                    "text_hash": operation.text_hash,
                    "operation": operation.operation,
                    "reason": operation.reason,
                    "confidence": operation.confidence,
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": ignored_reason,
                }
            )
            continue
        ignored_operations.append(
            {
                **_serialize_cleanup_operation(operation=operation, block=block),
                "chunk_index": operation.chunk_index,
                "ignored_reason": ignored_reason,
            }
        )
    return filtered_operations, ignored_operations


def _is_allowed_page_anchor_followup_join(
    *,
    operation: CleanupOperation,
    page_anchor_blocks_with_noise_removal: set[str],
    editable_blocks: Mapping[str, CleanupBlock],
) -> bool:
    if operation.operation != "join_fragmented_paragraph":
        return False
    block = editable_blocks.get(operation.block_id)
    next_block = editable_blocks.get(operation.next_id)
    if block is None or next_block is None:
        return False
    if next_block.index != block.index + 1:
        return False
    return operation.next_id in page_anchor_blocks_with_noise_removal or operation.block_id in page_anchor_blocks_with_noise_removal


def _merge_anchor_repair_pass_into_report(
    *,
    report_payload: Mapping[str, object],
    raw_markdown: str,
    raw_blocks: Sequence[CleanupBlock],
    anchor_pass_result: AnchorRepairPassResult,
) -> dict[str, object]:
    merged_report = dict(report_payload)
    first_pass_stats = dict(cast(Mapping[str, object], merged_report.get("stats") or {}))
    first_pass_chunk_results = [
        {**dict(entry), "pass_name": str(dict(entry).get("pass_name") or "first_pass")}
        for entry in cast(Sequence[Mapping[str, object]], merged_report.get("chunk_results") or [])
    ]
    first_pass_accepted_cleanup_operations = [
        {**dict(entry), "pass_name": str(dict(entry).get("pass_name") or "first_pass")}
        for entry in cast(Sequence[Mapping[str, object]], merged_report.get("accepted_cleanup_operations") or [])
    ]
    first_pass_accepted_delete_blocks = [
        {**dict(entry), "pass_name": str(dict(entry).get("pass_name") or "first_pass")}
        for entry in cast(Sequence[Mapping[str, object]], merged_report.get("accepted_delete_blocks") or [])
    ]
    first_pass_ignored_cleanup_operations = [
        {**dict(entry), "pass_name": str(dict(entry).get("pass_name") or "first_pass")}
        for entry in cast(
            Sequence[Mapping[str, object]],
            merged_report.get("ignored_cleanup_operations") or merged_report.get("ignored_delete_blocks") or [],
        )
    ]

    combined_chunk_results = first_pass_chunk_results + [dict(entry) for entry in anchor_pass_result.chunk_results]
    combined_accepted_cleanup_operations = first_pass_accepted_cleanup_operations + [
        dict(entry) for entry in anchor_pass_result.accepted_cleanup_operations
    ]
    combined_accepted_delete_blocks = first_pass_accepted_delete_blocks + [
        dict(entry) for entry in anchor_pass_result.accepted_delete_blocks
    ]
    combined_ignored_cleanup_operations = first_pass_ignored_cleanup_operations + [
        dict(entry) for entry in anchor_pass_result.ignored_cleanup_operations
    ]
    combined_deleted_char_count = _coerce_int(
        cast(Mapping[str, object], merged_report.get("stats") or {}).get("deleted_non_whitespace_char_count"),
        default=0,
        minimum=0,
    ) + anchor_pass_result.deleted_char_count
    merged_report["warnings"] = list(cast(Sequence[str], merged_report.get("warnings") or [])) + list(anchor_pass_result.warnings)
    merged_report["accepted_cleanup_operations"] = combined_accepted_cleanup_operations
    merged_report["accepted_delete_blocks"] = combined_accepted_delete_blocks
    merged_report["ignored_cleanup_operations"] = combined_ignored_cleanup_operations
    merged_report["ignored_delete_blocks"] = combined_ignored_cleanup_operations
    merged_report["heading_boundary_application_diagnostics"] = _build_heading_boundary_application_diagnostics(
        accepted_cleanup_operations=combined_accepted_cleanup_operations,
        ignored_cleanup_operations=combined_ignored_cleanup_operations,
    )
    merged_report["chunk_results"] = combined_chunk_results
    merged_report["stats"] = _build_cleanup_stats(
        raw_markdown=raw_markdown,
        blocks=raw_blocks,
        accepted_delete_blocks=combined_accepted_delete_blocks,
        accepted_cleanup_operations=combined_accepted_cleanup_operations,
        ignored_cleanup_operations=combined_ignored_cleanup_operations,
        chunk_results=combined_chunk_results,
        deleted_char_count=combined_deleted_char_count,
    )
    merged_report["passes"] = {
        "first_pass": {
            "stats": first_pass_stats,
        },
        "anchor_repair_pass": {
            "requested_anchor_count": anchor_pass_result.requested_anchor_count,
            "selected_anchor_count": anchor_pass_result.selected_anchor_count,
            "selected_window_block_count": anchor_pass_result.selected_window_block_count,
            "selected_anchors": [dict(anchor) for anchor in anchor_pass_result.selected_anchors],
            "warnings": list(anchor_pass_result.warnings),
            "stats": _build_cleanup_stats(
                raw_markdown=anchor_pass_result.cleaned_markdown,
                blocks=build_cleanup_blocks(anchor_pass_result.cleaned_markdown),
                accepted_delete_blocks=anchor_pass_result.accepted_delete_blocks,
                accepted_cleanup_operations=anchor_pass_result.accepted_cleanup_operations,
                ignored_cleanup_operations=anchor_pass_result.ignored_cleanup_operations,
                chunk_results=anchor_pass_result.chunk_results,
                deleted_char_count=anchor_pass_result.deleted_char_count,
            ),
            "chunk_results": [dict(entry) for entry in anchor_pass_result.chunk_results],
        },
    }
    return merged_report


def _parse_cleanup_response(
    *,
    raw_response: str,
    editable_blocks: Mapping[str, CleanupBlock],
    readonly_context_blocks: Mapping[str, CleanupBlock] | None = None,
    chunk_index: int,
) -> tuple[list[CleanupOperation], list[str], list[dict[str, object]]]:
    payload = _load_cleanup_response_payload(raw_response)
    if not isinstance(payload, dict):
        raise RuntimeError("reader_cleanup_response_must_be_object")

    unknown_top_level = sorted(set(payload.keys()) - _TOP_LEVEL_RESPONSE_FIELDS)
    if unknown_top_level:
        raise RuntimeError(f"reader_cleanup_unknown_top_level_fields:{','.join(unknown_top_level)}")

    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        raise RuntimeError("reader_cleanup_warnings_must_be_string_list")

    delete_blocks = payload.get("delete_blocks", [])
    if not isinstance(delete_blocks, list):
        raise RuntimeError("reader_cleanup_delete_blocks_must_be_list")

    cleanup_operations = payload.get("cleanup_operations")
    cleanup_source = "cleanup_operations"
    if cleanup_operations is None:
        if delete_blocks:
            raise RuntimeError("reader_cleanup_legacy_delete_blocks_require_schema_repair")
        cleanup_items = delete_blocks
        cleanup_source = "legacy_delete_blocks"
    else:
        cleanup_items = cleanup_operations
    if not isinstance(cleanup_items, list):
        raise RuntimeError("reader_cleanup_operations_must_be_list")

    operations: list[CleanupOperation] = []
    ignored_operations: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for item in cleanup_items:
        if not isinstance(item, dict):
            raise RuntimeError("reader_cleanup_operation_item_must_be_object")
        item_with_operation = dict(item)
        if "operation" not in item_with_operation:
            item_with_operation["operation"] = "delete_block"
        normalized_item, normalization_warnings = _normalize_delete_block_item(
            item=item_with_operation,
            editable_blocks=editable_blocks,
            cleanup_source=cleanup_source,
        )
        if "operation" not in normalized_item:
            normalized_item["operation"] = "delete_block"
        warnings.extend(normalization_warnings)

        block_id = _require_nonempty_str(normalized_item, "id")
        text_hash = _require_nonempty_str(normalized_item, "text_hash")
        operation_name = _require_nonempty_str(normalized_item, "operation")
        reason = _require_nonempty_str(normalized_item, "reason")
        confidence = _require_nonempty_str(normalized_item, "confidence").lower()
        if operation_name == "delete_block":
            unknown_block_fields = sorted(
                set(item.keys()) - (_BLOCK_RESPONSE_FIELDS | {"operation", "evidence_before", "expected_after_preview", "safety_note"})
            )
        else:
            unknown_block_fields = sorted(set(item.keys()) - _OPERATION_RESPONSE_FIELDS)
        if unknown_block_fields:
            raise RuntimeError(f"reader_cleanup_unknown_operation_fields:{','.join(unknown_block_fields)}")

        if operation_name not in _ALLOWED_OPERATIONS:
            raise RuntimeError(f"reader_cleanup_unknown_operation:{operation_name}")
        if operation_name == "delete_block" and reason not in _ALLOWED_DELETE_REASONS:
            raise RuntimeError(f"reader_cleanup_unknown_reason:{reason}")
        if confidence not in _ALLOWED_CONFIDENCE:
            raise RuntimeError(f"reader_cleanup_unknown_confidence:{confidence}")
        target_role = str(normalized_item.get("target_role") or "").strip().lower()
        if operation_name == "reclassify_role":
            if not target_role:
                raise RuntimeError(f"reader_cleanup_operation_missing_required_field:{block_id}:target_role")
            if target_role not in _ALLOWED_RECLASSIFY_TARGET_ROLES:
                raise RuntimeError(f"reader_cleanup_unknown_target_role:{target_role}")
        split_substrings = normalized_item.get("split_substrings")
        readonly_context_block = (readonly_context_blocks or {}).get(block_id)
        if block_id not in editable_blocks:
            if readonly_context_block is None:
                raise RuntimeError(f"reader_cleanup_block_outside_chunk:{block_id}")
            ignored_operation = CleanupOperation(
                block_id=block_id,
                text_hash=text_hash,
                operation=operation_name,
                reason=reason,
                confidence=cast(CleanupConfidence, confidence),
                chunk_index=chunk_index,
                evidence_before=str(normalized_item.get("evidence_before") or "").strip(),
                expected_after_preview=str(normalized_item.get("expected_after_preview") or "").strip(),
                safety_note=str(normalized_item.get("safety_note") or "").strip(),
                split_substrings=tuple(
                    str(part).strip() for part in split_substrings if str(part).strip()
                )
                if isinstance(split_substrings, list)
                else (),
                noise_substring=str(normalized_item.get("noise_substring") or ""),
                next_id=str(normalized_item.get("next_id") or "").strip(),
                next_text_hash=str(normalized_item.get("next_text_hash") or "").strip(),
                pre_body_stub=str(normalized_item.get("pre_body_stub") or ""),
                heading_substring=str(normalized_item.get("heading_substring") or ""),
                body_substring=str(normalized_item.get("body_substring") or ""),
                post_body_continuation=str(normalized_item.get("post_body_continuation") or ""),
                target_role=target_role,
            )
            ignored_operations.append(
                {
                    **_serialize_cleanup_operation(operation=ignored_operation, block=readonly_context_block),
                    "chunk_index": chunk_index,
                    "ignored_reason": "readonly_context_block",
                }
            )
            warnings.append(f"reader_cleanup_readonly_context_operation_ignored:{chunk_index}:{block_id}")
            continue
        for required_field in ("evidence_before", "safety_note"):
            if not str(normalized_item.get(required_field) or "").strip():
                raise RuntimeError(f"reader_cleanup_operation_missing_required_field:{block_id}:{required_field}")

        seen_ids.add(block_id)
        if operation_name == "delete_block":
            if "expected_after_preview" not in normalized_item:
                normalized_item = dict(normalized_item)
                normalized_item["expected_after_preview"] = ""
                warnings.append(
                    f"reader_cleanup_expected_after_preview_recovered:{chunk_index}:{block_id}:{operation_name}"
                )
        elif not str(normalized_item.get("expected_after_preview") or "").strip():
            if operation_name in {
                "extract_side_heading_and_reattach_body",
                "remove_inline_noise",
                "normalize_heading_boundary",
            }:
                raise RuntimeError(f"reader_cleanup_operation_missing_required_field:{block_id}:expected_after_preview")
            recovered_preview = _recover_expected_after_preview(
                operation_name=operation_name,
                normalized_item=normalized_item,
                block=editable_blocks[block_id],
                editable_blocks=editable_blocks,
            )
            if recovered_preview is None:
                ignored_operation = CleanupOperation(
                    block_id=block_id,
                    text_hash=text_hash,
                    operation=operation_name,
                    reason=reason,
                    confidence=cast(CleanupConfidence, confidence),
                    chunk_index=chunk_index,
                    evidence_before=str(normalized_item.get("evidence_before") or "").strip(),
                    expected_after_preview="",
                    safety_note=str(normalized_item.get("safety_note") or "").strip(),
                    split_substrings=tuple(
                        str(part).strip() for part in split_substrings if str(part).strip()
                    )
                    if isinstance(split_substrings, list)
                    else (),
                    noise_substring=str(normalized_item.get("noise_substring") or ""),
                    next_id=str(normalized_item.get("next_id") or "").strip(),
                    next_text_hash=str(normalized_item.get("next_text_hash") or "").strip(),
                    pre_body_stub=str(normalized_item.get("pre_body_stub") or ""),
                    heading_substring=str(normalized_item.get("heading_substring") or ""),
                    body_substring=str(normalized_item.get("body_substring") or ""),
                    post_body_continuation=str(normalized_item.get("post_body_continuation") or ""),
                    target_role=target_role,
                )
                ignored_operations.append(
                    {
                        **_serialize_cleanup_operation(operation=ignored_operation, block=editable_blocks[block_id]),
                        "chunk_index": chunk_index,
                        "ignored_reason": "expected_after_preview_missing_unrecoverable",
                    }
                )
                warnings.append(
                    f"reader_cleanup_expected_after_preview_ignored:{chunk_index}:{block_id}:{operation_name}"
                )
                continue
            normalized_item = dict(normalized_item)
            normalized_item["expected_after_preview"] = recovered_preview
            warnings.append(
                f"reader_cleanup_expected_after_preview_recovered:{chunk_index}:{block_id}:{operation_name}"
            )

        normalized_item, exact_field_warnings = _recover_missing_operation_exact_fields(
            operation_name=operation_name,
            normalized_item=normalized_item,
            block=editable_blocks[block_id],
            chunk_index=chunk_index,
            block_id=block_id,
        )
        warnings.extend(exact_field_warnings)

        operations.append(
            CleanupOperation(
                block_id=block_id,
                text_hash=text_hash,
                operation=operation_name,
                reason=reason,
                confidence=cast(CleanupConfidence, confidence),
                chunk_index=chunk_index,
                evidence_before=str(normalized_item.get("evidence_before") or "").strip(),
                expected_after_preview=str(normalized_item.get("expected_after_preview") or "").strip(),
                safety_note=str(normalized_item.get("safety_note") or "").strip(),
                split_substrings=tuple(
                    str(part).strip() for part in split_substrings if str(part).strip()
                )
                if isinstance(split_substrings, list)
                else (),
                noise_substring=str(normalized_item.get("noise_substring") or ""),
                next_id=str(normalized_item.get("next_id") or "").strip(),
                next_text_hash=str(normalized_item.get("next_text_hash") or "").strip(),
                pre_body_stub=str(normalized_item.get("pre_body_stub") or ""),
                heading_substring=str(normalized_item.get("heading_substring") or ""),
                body_substring=str(normalized_item.get("body_substring") or ""),
                post_body_continuation=str(normalized_item.get("post_body_continuation") or ""),
                target_role=target_role,
            )
        )

    return operations, [str(item) for item in warnings], ignored_operations


def _recover_expected_after_preview(
    *,
    operation_name: str,
    normalized_item: Mapping[str, object],
    block: CleanupBlock,
    editable_blocks: Mapping[str, CleanupBlock],
) -> str | None:
    current_text = block.text
    if operation_name == "delete_block":
        return ""
    if operation_name == "split_block":
        raw_parts = normalized_item.get("split_substrings")
        if not isinstance(raw_parts, list):
            return None
        parts = [str(part).strip() for part in raw_parts if str(part).strip()]
        if len(parts) not in {2, 3}:
            return None
        pos = 0
        for part in parts:
            idx = current_text.find(part, pos)
            if idx == -1:
                return None
            if current_text[pos:idx].strip():
                return None
            pos = idx + len(part)
        if current_text[pos:].strip():
            return None
        return "\n\n".join(parts)
    if operation_name == "join_fragmented_paragraph":
        next_id = str(normalized_item.get("next_id") or "").strip()
        next_text_hash = str(normalized_item.get("next_text_hash") or "").strip()
        next_block = editable_blocks.get(next_id)
        if not next_id or not next_text_hash or next_block is None:
            return None
        if next_block.index != block.index + 1:
            return None
        if next_block.text_hash != next_text_hash:
            return None
        return f"{current_text.rstrip()} {next_block.text.lstrip()}"
    if operation_name == "reclassify_role":
        target_role = str(normalized_item.get("target_role") or "").strip().lower()
        if target_role not in _ALLOWED_RECLASSIFY_TARGET_ROLES:
            return None
        return _reclassify_role_expected_markdown(current_text=current_text, target_role=target_role)
    return None


def _inline_noise_removed_text(*, current_text: str, noise: str) -> str:
    noise_index = current_text.find(noise)
    if noise_index < 0:
        return re.sub(r"\s{2,}", " ", current_text.replace(noise, "", 1)).strip()
    before_raw = current_text[:noise_index]
    after_raw = current_text[noise_index + len(noise) :]
    if re.search(r"\n\s*\n\s*$", before_raw):
        return f"{before_raw.rstrip()}\n\n{after_raw.lstrip()}".strip()
    before = before_raw.rstrip()
    after = after_raw.lstrip()
    joiner = " " if before and after else ""
    return re.sub(r"\s{2,}", " ", f"{before}{joiner}{after}").strip()


def _recover_inline_noise_substring_from_preview(
    *,
    normalized_item: Mapping[str, object],
    block: CleanupBlock,
) -> str | None:
    current_text = block.text.strip()
    expected_after = str(normalized_item.get("expected_after_preview") or "")
    expected_after = expected_after.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not current_text or not expected_after or expected_after == current_text:
        return None

    prefix_len = 0
    max_prefix_len = min(len(current_text), len(expected_after))
    while prefix_len < max_prefix_len and current_text[prefix_len] == expected_after[prefix_len]:
        prefix_len += 1

    suffix_len = 0
    max_suffix_len = min(len(current_text) - prefix_len, len(expected_after) - prefix_len)
    while (
        suffix_len < max_suffix_len
        and current_text[len(current_text) - suffix_len - 1]
        == expected_after[len(expected_after) - suffix_len - 1]
    ):
        suffix_len += 1

    candidate_end = len(current_text) - suffix_len
    candidate = current_text[prefix_len:candidate_end]
    if not candidate.strip():
        return None
    if current_text.count(candidate) != 1:
        return None
    reason = str(normalized_item.get("reason") or "").strip()
    if not _is_recoverable_inline_noise_substring_from_preview(
        noise=candidate,
        current_text=current_text,
        reason=reason,
    ):
        return None
    if _inline_noise_removed_text(current_text=current_text, noise=candidate) != expected_after:
        return None
    return candidate


def _is_recoverable_inline_noise_substring_from_preview(*, noise: str, current_text: str, reason: str) -> bool:
    normalized_noise = str(noise or "").strip()
    if not normalized_noise:
        return False
    if _SAFE_INLINE_NOISE_PATTERN.fullmatch(normalized_noise) is not None:
        return True
    return _looks_like_duplicate_inline_fragment_noise(
        normalized_noise=normalized_noise,
        current_text=current_text,
        reason=reason,
    )


def _recover_missing_operation_exact_fields(
    *,
    operation_name: str,
    normalized_item: Mapping[str, object],
    block: CleanupBlock,
    chunk_index: int,
    block_id: str,
) -> tuple[dict[str, object], list[str]]:
    if operation_name == "remove_inline_noise":
        if str(normalized_item.get("noise_substring") or ""):
            return dict(normalized_item), []
        evidence_before = str(normalized_item.get("evidence_before") or "").strip()
        reason = str(normalized_item.get("reason") or "").strip()
        if (
            evidence_before
            and evidence_before in block.text
            and block.text.count(evidence_before) == 1
            and _is_safe_inline_noise_substring(noise=evidence_before, current_text=block.text, reason=reason)
        ):
            recovered = dict(normalized_item)
            recovered["noise_substring"] = evidence_before
            return recovered, [f"reader_cleanup_exact_fields_recovered:{chunk_index}:{block_id}:{operation_name}"]
        preview_noise = _recover_inline_noise_substring_from_preview(
            normalized_item=normalized_item,
            block=block,
        )
        if preview_noise is not None:
            recovered = dict(normalized_item)
            recovered["noise_substring"] = preview_noise
            return recovered, [f"reader_cleanup_exact_fields_recovered:{chunk_index}:{block_id}:{operation_name}"]
        return dict(normalized_item), []
    if operation_name != "normalize_heading_boundary":
        return dict(normalized_item), []
    if str(normalized_item.get("heading_substring") or "").strip() and str(
        normalized_item.get("body_substring") or ""
    ).strip():
        return dict(normalized_item), []

    recovered_parts = _recover_heading_boundary_parts_from_preview(
        normalized_item=normalized_item,
        block=block,
    )
    if recovered_parts is None:
        return dict(normalized_item), []
    heading, body = recovered_parts

    recovered = dict(normalized_item)
    if not str(recovered.get("heading_substring") or "").strip():
        recovered["heading_substring"] = heading
    if not str(recovered.get("body_substring") or "").strip():
        recovered["body_substring"] = body
    return recovered, [f"reader_cleanup_exact_fields_recovered:{chunk_index}:{block_id}:{operation_name}"]


def _recover_heading_boundary_parts_from_preview(
    *,
    normalized_item: Mapping[str, object],
    block: CleanupBlock,
) -> tuple[str, str] | None:
    preview = str(normalized_item.get("expected_after_preview") or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [part.strip() for part in re.split(r"\n\s*\n", preview, maxsplit=1) if part.strip()]
    if len(parts) != 2:
        return None
    heading, body_preview = parts
    if not heading or not body_preview:
        return None

    current_text = block.text.strip()
    heading_start = current_text.find(heading)
    if heading_start < 0 or current_text.count(heading) != 1:
        return None
    prefix = current_text[:heading_start]
    if prefix.strip() and not _is_safe_inline_noise_substring(
        noise=prefix,
        current_text=current_text,
        reason=str(normalized_item.get("reason") or ""),
    ):
        return None

    remainder = current_text[heading_start + len(heading) :].lstrip()
    body_prefix = _strip_preview_ellipsis(body_preview)
    if not body_prefix or not remainder.startswith(body_prefix):
        return None
    if len(re.sub(r"\s+", "", body_prefix)) < 8:
        return None
    return heading, remainder


def _strip_preview_ellipsis(value: str) -> str:
    text = str(value or "").strip()
    while text.endswith(("...", "…")):
        text = text[:-3].rstrip() if text.endswith("...") else text[:-1].rstrip()
    return text


def _normalize_delete_block_item(
    *,
    item: Mapping[str, object],
    editable_blocks: Mapping[str, CleanupBlock],
    cleanup_source: str,
) -> tuple[dict[str, object], list[str]]:
    normalized_item = dict(item)
    warnings: list[str] = []
    confidence = normalized_item.get("confidence")

    block_id = normalized_item.get("id")
    reason = normalized_item.get("reason")
    if not isinstance(block_id, str) or not block_id.strip():
        return normalized_item, warnings
    if not isinstance(reason, str) or not reason.strip():
        return normalized_item, warnings

    block = editable_blocks.get(block_id.strip())
    if not isinstance(confidence, str) or not confidence.strip():
        expected_kind = _SAFE_CONFIDENCE_INFERENCE.get(reason.strip())
        if block is not None and expected_kind is not None and block.kind == expected_kind:
            normalized_item["confidence"] = "high"
            warnings.append(f"reader_cleanup_missing_confidence_inferred:{block.block_id}:high")

    return normalized_item, warnings


def _apply_cleanup_operations(
    *,
    raw_markdown: str,
    blocks: Sequence[CleanupBlock],
    operations: Sequence[CleanupOperation],
    config: ReaderCleanupConfig,
    global_candidate_block_ids: set[str],
) -> tuple[str, dict[str, dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    if not operations:
        return raw_markdown, {}, [], []

    protected_ids = _build_protected_block_ids(blocks=blocks, keep_toc=config.keep_toc)
    accepted: dict[str, dict[str, object]] = {}
    accepted_cleanup_operations: list[dict[str, object]] = []
    ignored: list[dict[str, object]] = []
    same_block_operation_history: dict[str, list[str]] = {}
    same_block_applied_history: dict[str, list[str]] = {}
    rewritten_blocks: list[str | None] = [block.text for block in blocks]
    operations_by_index = _canonicalize_cleanup_operation_sequence(blocks=blocks, operations=operations)
    allowed_operations = _allowed_operations_for_config(config)
    accepted_reclassify_count = 0
    max_reclassify_count = _max_allowed_reclassify_operations(blocks=blocks, config=config)

    for _, _, _, operation, sequence_decision in operations_by_index:
        block = _block_by_id(blocks, operation.block_id)
        if operation.operation not in allowed_operations:
            ignored.append(
                {
                    **_serialize_cleanup_operation(operation=operation, block=block),
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": "operation_not_allowed_by_cleanup_contract",
                    **({"sequence_decision": sequence_decision} if sequence_decision else {}),
                }
            )
            continue
        if operation.operation == "reclassify_role" and accepted_reclassify_count >= max_reclassify_count:
            ignored.append(
                {
                    **_serialize_cleanup_operation(operation=operation, block=block),
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": "reclassify_global_safety_limit_exceeded",
                    **({"sequence_decision": sequence_decision} if sequence_decision else {}),
                }
            )
            continue
        previous_encountered = same_block_operation_history.get(block.block_id, [])
        previous_applied = same_block_applied_history.get(block.block_id, [])
        sequence_ignore_reason = _validate_same_block_operation_sequence(
            previous_encountered=previous_encountered,
            previous_applied=previous_applied,
            operation=operation,
        )
        same_block_operation_history.setdefault(block.block_id, []).append(operation.operation)
        if sequence_ignore_reason is not None:
            ignored.append(
                {
                    **_serialize_cleanup_operation(operation=operation, block=block),
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": sequence_ignore_reason,
                    **({"sequence_decision": sequence_decision} if sequence_decision else {}),
                }
            )
            continue
        ignore_reason = _validate_operation(
            blocks=blocks,
            block=block,
            operation=operation,
            protected_ids=protected_ids,
            config=config,
            global_candidate_block_ids=global_candidate_block_ids,
        )
        if ignore_reason is not None:
            ignored.append(
                {
                    **_serialize_cleanup_operation(operation=operation, block=block),
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": ignore_reason,
                    **({"sequence_decision": sequence_decision} if sequence_decision else {}),
                }
            )
            continue

        applied, after_state, apply_ignore_reason = _apply_single_operation_to_blocks(
            blocks=blocks,
            rewritten_blocks=rewritten_blocks,
            operation=operation,
            block=block,
        )
        if not applied:
            ignored.append(
                {
                    **_serialize_cleanup_operation(operation=operation, block=block),
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": apply_ignore_reason or "operation_not_applicable_exact_match",
                    **({"sequence_decision": sequence_decision} if sequence_decision else {}),
                }
            )
            continue
        if operation.operation == "delete_block":
            accepted[block.block_id] = {
                "reason": operation.reason,
                "confidence": operation.confidence,
                "chunk_index": operation.chunk_index,
            }
        if operation.operation == "reclassify_role":
            accepted_reclassify_count += 1
        accepted_cleanup_operations.append(
            {
                **_serialize_cleanup_operation(operation=operation, block=block),
                "chunk_index": operation.chunk_index,
                "after_state": after_state,
                **({"sequence_decision": sequence_decision} if sequence_decision else {}),
            }
        )
        same_block_applied_history.setdefault(block.block_id, []).append(operation.operation)

    if not accepted_cleanup_operations:
        return raw_markdown, {}, [], ignored

    if _violates_global_safety(blocks=blocks, accepted_ids=tuple(accepted.keys()), config=config):
        for block_id, metadata in list(accepted.items()):
            block = _block_by_id(blocks, block_id)
            ignored.append(
                {
                    **_serialize_delete_block(block=block, reason=str(metadata["reason"]), confidence=str(metadata["confidence"])),
                    "chunk_index": metadata["chunk_index"],
                    "ignored_reason": "global_safety_limit_exceeded",
                }
            )
            accepted.pop(block_id, None)
        accepted_cleanup_operations = [entry for entry in accepted_cleanup_operations if entry.get("operation") != "delete_block"]

    if not accepted_cleanup_operations:
        return raw_markdown, {}, [], ignored

    kept_blocks = [block_text for block_text in rewritten_blocks if block_text is not None and block_text.strip()]
    cleaned_markdown = "\n\n".join(kept_blocks)
    if not cleaned_markdown.strip():
        return raw_markdown, {}, [], ignored
    return cleaned_markdown, accepted, accepted_cleanup_operations, ignored


def _apply_reannotation_decisions(
    *,
    raw_markdown: str,
    blocks: Sequence[CleanupBlock],
    decisions: Sequence[ReannotationDecision],
) -> tuple[str, list[dict[str, object]], list[dict[str, object]]]:
    if not decisions:
        return raw_markdown, [], []
    rewritten_blocks = [block.text for block in blocks]
    block_by_id = {block.block_id: block for block in blocks}
    accepted: list[dict[str, object]] = []
    ignored: list[dict[str, object]] = []
    seen_block_ids: set[str] = set()
    for decision in decisions:
        block = block_by_id.get(decision.block_id)
        if block is None:
            ignored.append({"id": decision.block_id, "chunk_index": decision.chunk_index, "ignored_reason": "unknown_block_id"})
            continue
        if block.block_id in seen_block_ids:
            ignored.append({**block.to_payload(), "chunk_index": decision.chunk_index, "ignored_reason": "duplicate_reannotation"})
            continue
        seen_block_ids.add(block.block_id)
        replacement, operation_name, ignore_reason = _replacement_for_reannotation_decision(block=block, decision=decision)
        if ignore_reason is not None or replacement is None:
            ignored.append(
                {
                    **block.to_payload(),
                    "chunk_index": decision.chunk_index,
                    "operation": "reannotate_role_boundary",
                    "role": decision.role,
                    "ignored_reason": ignore_reason or "reannotation_not_applicable",
                }
            )
            continue
        if not _reannotation_replacement_preserves_visible_content(
            before=block.text,
            after=replacement,
            operation_name=operation_name,
        ):
            ignored.append(
                {
                    **block.to_payload(),
                    "chunk_index": decision.chunk_index,
                    "operation": operation_name,
                    "role": decision.role,
                    "ignored_reason": "visible_content_containment_failed",
                    "expected_after_preview": replacement,
                }
            )
            continue
        if replacement == block.text:
            continue
        rewritten_blocks[block.index] = replacement
        accepted.append(
            {
                **_serialize_delete_block(block=block, reason=decision.reason or "role_boundary_reannotation", confidence=decision.confidence),
                "operation": operation_name,
                "chunk_index": decision.chunk_index,
                "target_role": decision.role,
                "expected_after_preview": replacement,
                "after_state": "reannotated",
            }
        )
    if not accepted:
        return raw_markdown, [], ignored
    return "\n\n".join(block for block in rewritten_blocks if block.strip()), accepted, ignored


def _replacement_for_reannotation_decision(
    *,
    block: CleanupBlock,
    decision: ReannotationDecision,
) -> tuple[str | None, str, str | None]:
    if _DOCX_IMAGE_PLACEHOLDER_PATTERN.search(block.text):
        return None, "reannotate_role_boundary", "docx_image_anchor_protected"
    text = block.text.strip()
    if decision.list_items:
        return _replacement_for_reannotation_list_items(block=block, decision=decision)
    if decision.role == "footnote" and decision.marker_text:
        return _replacement_for_reannotation_footnote_marker(block=block, decision=decision)
    if decision.heading_text or decision.body_text:
        heading = decision.heading_text.strip()
        body = decision.body_text.strip()
        if not heading or not body:
            return None, "reannotate_heading_body_boundary", "boundary_parts_incomplete"
        if not _normalize_block_text(text).startswith(_normalize_block_text(heading)):
            return None, "reannotate_heading_body_boundary", "heading_not_exact_prefix"
        expected_source = f"{heading}{body}"
        if _visible_content_fingerprint(expected_source) != _visible_content_fingerprint(text):
            joined_with_space = f"{heading} {body}"
            if _visible_content_fingerprint(joined_with_space) != _visible_content_fingerprint(text):
                return None, "reannotate_heading_body_boundary", "boundary_parts_do_not_cover_block"
        return f"## {heading.lstrip('#').strip()}\n\n{body}", "reannotate_heading_body_boundary", None

    visible = text.lstrip("#").strip()
    if decision.role == "heading":
        return f"## {visible}", "reannotate_role", None
    if decision.role == "list_item":
        return visible if re.match(r"^(?:[-*]|\d+\.)\s+", visible) else f"- {visible}", "reannotate_role", None
    return visible, "reannotate_role", None


def _reannotation_replacement_preserves_visible_content(*, before: str, after: str, operation_name: str) -> bool:
    if operation_name == "reannotate_list_items":
        return _list_visible_content_fingerprint(before) == _list_visible_content_fingerprint(after)
    return _visible_content_fingerprint(before) == _visible_content_fingerprint(after)


def _replacement_for_reannotation_list_items(
    *,
    block: CleanupBlock,
    decision: ReannotationDecision,
) -> tuple[str | None, str, str | None]:
    items = [item.strip() for item in decision.list_items if item.strip()]
    if not items:
        return None, "reannotate_list_items", "list_items_empty"
    source_fingerprint = _list_visible_content_fingerprint(block.text)
    joined_items = " ".join(items)
    if _list_visible_content_fingerprint(joined_items) != source_fingerprint:
        return None, "reannotate_list_items", "list_items_do_not_cover_block"
    rendered_items = []
    for item in items:
        stripped = re.sub(r"^(?:[-*]|\d+\.)\s+", "", item).strip()
        rendered_items.append(f"- {stripped}")
    return "\n".join(rendered_items), "reannotate_list_items", None


def _replacement_for_reannotation_footnote_marker(
    *,
    block: CleanupBlock,
    decision: ReannotationDecision,
) -> tuple[str | None, str, str | None]:
    marker = decision.marker_text.strip()
    body = decision.body_text.strip()
    if not marker or not body:
        return None, "reannotate_footnote_marker", "footnote_marker_parts_incomplete"
    normalized_text = _normalize_block_text(block.text)
    if not normalized_text.endswith(marker):
        return None, "reannotate_footnote_marker", "marker_not_exact_suffix"
    prefix = normalized_text[: -len(marker)].rstrip()
    if _visible_content_fingerprint(prefix) != _visible_content_fingerprint(body):
        return None, "reannotate_footnote_marker", "footnote_body_not_exact_prefix"
    return f"{body}\n\n{marker}", "reannotate_footnote_marker", None


def _visible_content_fingerprint(text: str) -> str:
    lines = []
    for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        stripped = line.strip()
        stripped = re.sub(r"^#{1,6}\s+", "", stripped)
        stripped = re.sub(r"^(?:[-*]|\d+\.)\s+", "", stripped)
        if stripped:
            lines.append(stripped)
    return re.sub(r"\s+", "", " ".join(lines)).casefold()


def _list_visible_content_fingerprint(text: str) -> str:
    normalized = _normalize_block_text(text)
    normalized = re.sub(r"(?:(?<=^)|(?<=\s))(?:[-*]|\d+\.)\s+", " ", normalized)
    return re.sub(r"\s+", "", normalized).casefold()


def _apply_single_operation_to_blocks(
    *,
    blocks: Sequence[CleanupBlock],
    rewritten_blocks: list[str | None],
    operation: CleanupOperation,
    block: CleanupBlock,
) -> tuple[bool, str, str | None]:
    current_text = rewritten_blocks[block.index]
    if current_text is None:
        if operation.operation == "normalize_heading_boundary":
            return _apply_heading_boundary_to_joined_previous_block(
                rewritten_blocks=rewritten_blocks,
                operation=operation,
                block=block,
            )
        return False, "", "block_already_removed"
    if operation.operation == "delete_block":
        if operation.reason == "duplicate_fragment":
            duplicate_fragment_ignore_reason = _validate_duplicate_fragment_delete(
                blocks=blocks,
                rewritten_blocks=rewritten_blocks,
                block=block,
                current_text=current_text,
            )
            if duplicate_fragment_ignore_reason is not None:
                return False, "", duplicate_fragment_ignore_reason
        rewritten_blocks[block.index] = None
        return True, "deleted", None
    if operation.operation == "extract_side_heading_and_reattach_body":
        applied_text, ignore_reason = _apply_side_heading_reattach_to_text(
            current_text=current_text,
            operation=operation,
        )
        if applied_text is None:
            return False, "", ignore_reason or "side_heading_reattach_not_applicable"
        rewritten_blocks[block.index] = applied_text
        return True, "side_heading_reattached", None
    if operation.operation == "split_block":
        parts = list(operation.split_substrings)
        if len(parts) not in {2, 3}:
            return False, "", "split_substrings_count_invalid"
        pos = 0
        for part in parts:
            idx = block.text.find(part, pos)
            if idx == -1 or block.text[pos:idx].strip():
                return False, "", "split_substrings_not_exact_block_cover"
            pos = idx + len(part)
        if block.text[pos:].strip():
            return False, "", "split_substrings_not_exact_block_cover"
        rewritten_blocks[block.index] = "\n\n".join(parts)
        return True, "split", None
    if operation.operation == "remove_inline_noise":
        noise = operation.noise_substring
        if not noise or noise not in current_text:
            return False, "", "noise_substring_not_found"
        if not _is_safe_inline_noise_substring(noise=noise, current_text=current_text, reason=operation.reason):
            return False, "", "remove_inline_noise_not_exact_noise_pattern"
        if current_text.count(noise) != 1:
            return False, "", "remove_inline_noise_substring_ambiguous"
        replacement = _inline_noise_removed_text(current_text=current_text, noise=noise)
        if not replacement:
            return False, "", "remove_inline_noise_would_drop_semantic_body"
        if len(re.sub(r"\s+", "", replacement)) < 20 and not _is_exact_isolated_semantic_heading_numeric_prefix_cleanup(
            current_text=current_text,
            noise=noise,
            replacement=replacement,
            expected_after_preview=operation.expected_after_preview,
        ):
            return False, "", "remove_inline_noise_would_drop_semantic_body"
        rewritten_blocks[block.index] = replacement
        return True, "inline_noise_removed", None
    if operation.operation == "join_fragmented_paragraph":
        if not operation.next_id or not operation.next_text_hash:
            return False, "", "join_missing_next_block_reference"
        try:
            next_block = _block_by_id(blocks, operation.next_id)
        except KeyError:
            return False, "", "join_next_block_missing"
        if next_block.index != block.index + 1:
            return False, "", "join_blocks_not_adjacent"
        if operation.next_text_hash != next_block.text_hash:
            return False, "", "join_next_text_hash_mismatch"
        next_text = rewritten_blocks[next_block.index]
        if next_text is None:
            return False, "", "join_next_block_already_removed"
        rewritten_blocks[block.index] = f"{current_text.rstrip()} {next_text.lstrip()}"
        rewritten_blocks[next_block.index] = None
        return True, "joined_with_next", None
    if operation.operation == "normalize_heading_boundary":
        applied_text, ignore_reason = _apply_heading_boundary_to_text(
            current_text=current_text,
            operation=operation,
        )
        if applied_text is None:
            adjacent_applied, adjacent_after_state, _adjacent_ignore_reason = (
                _apply_heading_boundary_across_adjacent_block(
                    rewritten_blocks=rewritten_blocks,
                    operation=operation,
                    block=block,
                )
            )
            if adjacent_applied:
                return True, adjacent_after_state, None
            return False, "", ignore_reason or "heading_boundary_not_applicable"
        rewritten_blocks[block.index] = applied_text
        return True, "heading_boundary_normalized", None
    if operation.operation == "reclassify_role":
        applied_text, ignore_reason = _apply_reclassify_role_to_text(
            current_text=current_text,
            block=block,
            operation=operation,
        )
        if applied_text is None:
            return False, "", ignore_reason or "reclassify_role_not_applicable"
        rewritten_blocks[block.index] = applied_text
        return True, f"role_reclassified_to_{operation.target_role}", None
    return False, "", "unsupported_operation"


def _apply_heading_boundary_to_joined_previous_block(
    *,
    rewritten_blocks: list[str | None],
    operation: CleanupOperation,
    block: CleanupBlock,
) -> tuple[bool, str, str | None]:
    if block.index <= 0:
        return False, "", "block_already_removed"
    previous_text = rewritten_blocks[block.index - 1]
    if previous_text is None:
        return False, "", "block_already_removed"
    evidence = operation.evidence_before.strip()
    if evidence and evidence not in previous_text:
        return False, "", "block_already_removed"
    applied_text, ignore_reason = _apply_heading_boundary_to_text(
        current_text=previous_text,
        operation=operation,
    )
    if applied_text is None:
        return False, "", ignore_reason or "block_already_removed"
    rewritten_blocks[block.index - 1] = applied_text
    return True, "heading_boundary_normalized_after_join", None


def _apply_side_heading_reattach_to_text(
    *,
    current_text: str,
    operation: CleanupOperation,
) -> tuple[str | None, str | None]:
    pre_body_stub = operation.pre_body_stub.strip()
    heading = operation.heading_substring.strip()
    post_body_continuation = operation.post_body_continuation.strip()
    if not pre_body_stub or not heading or not post_body_continuation:
        return None, "side_heading_reattach_missing_exact_parts"
    if "\n" in pre_body_stub or "\n" in heading or "\n" in post_body_continuation:
        return None, "side_heading_reattach_multiline_parts_unsupported"
    if re.search(r"\d", heading):
        return None, "side_heading_reattach_heading_contains_digits"
    if current_text.lstrip().startswith(("-", "—", "–", "•")):
        return None, "side_heading_reattach_context_unsupported"
    if (
        current_text.count(pre_body_stub) != 1
        or current_text.count(heading) != 1
        or current_text.count(post_body_continuation) != 1
    ):
        return None, "side_heading_reattach_substring_ambiguous"
    if not _ordered_substrings_cover_text(
        text=current_text,
        parts=(pre_body_stub, heading, post_body_continuation),
    ):
        return None, "side_heading_reattach_substrings_not_exact_block_cover"
    if not _has_side_heading_left_context(pre_body_stub):
        return None, "side_heading_reattach_pre_stub_not_continuation"
    if not _has_side_heading_right_context(post_body_continuation):
        return None, "side_heading_reattach_post_body_not_continuation"
    if not _looks_like_side_heading_phrase(heading):
        return None, "side_heading_reattach_heading_not_plausible"

    body = _join_body_stub_and_continuation(
        pre_body_stub=pre_body_stub,
        post_body_continuation=post_body_continuation,
    )
    if not body:
        return None, "side_heading_reattach_empty_body"
    applied_text = f"{heading}\n\n{body}"
    expected_after = operation.expected_after_preview.replace("\r\n", "\n").replace("\r", "\n").strip()
    if expected_after != applied_text:
        return None, "side_heading_reattach_expected_after_preview_mismatch"
    source_semantic = Counter(re.sub(r"\s+", "", f"{pre_body_stub}{heading}{post_body_continuation}"))
    output_semantic = Counter(re.sub(r"\s+", "", applied_text))
    if source_semantic != output_semantic:
        return None, "side_heading_reattach_would_drop_semantic_text"
    return applied_text, None


def _ordered_substrings_cover_text(*, text: str, parts: Sequence[str]) -> bool:
    pos = 0
    for part in parts:
        idx = text.find(part, pos)
        if idx == -1:
            return False
        if text[pos:idx].strip():
            return False
        pos = idx + len(part)
    return not text[pos:].strip()


def _join_body_stub_and_continuation(*, pre_body_stub: str, post_body_continuation: str) -> str:
    return f"{pre_body_stub.rstrip()} {post_body_continuation.lstrip()}".strip()


def _apply_heading_boundary_across_adjacent_block(
    *,
    rewritten_blocks: list[str | None],
    operation: CleanupOperation,
    block: CleanupBlock,
) -> tuple[bool, str, str | None]:
    if block.index + 1 >= len(rewritten_blocks):
        return False, "", "heading_boundary_adjacent_body_missing"
    current_text = rewritten_blocks[block.index]
    next_text = rewritten_blocks[block.index + 1]
    if current_text is None or next_text is None:
        return False, "", "heading_boundary_adjacent_body_missing"

    heading = operation.heading_substring.strip()
    body = operation.body_substring.strip()
    current_prefix = current_text.strip()
    next_remainder = next_text.lstrip()
    if not heading or not body or not current_prefix or not next_remainder:
        return False, "", "heading_boundary_missing_exact_parts"
    if not heading.startswith(current_prefix):
        return False, "", "heading_boundary_unaccounted_text"
    if body not in next_text:
        return False, "", "heading_boundary_substrings_not_found"

    heading_tail = heading[len(current_prefix) :].lstrip()
    if heading_tail and not next_remainder.startswith(heading_tail):
        return False, "", "heading_boundary_substrings_not_found"
    if not heading_tail and not next_remainder.startswith(body):
        return False, "", "heading_boundary_substrings_not_found"

    combined_text = f"{current_prefix} {next_remainder}"
    applied_text, ignore_reason = _apply_heading_boundary_to_text(
        current_text=combined_text,
        operation=operation,
    )
    if applied_text is None:
        return False, "", ignore_reason or "heading_boundary_not_applicable"
    rewritten_blocks[block.index] = applied_text
    rewritten_blocks[block.index + 1] = None
    return True, "heading_boundary_normalized_across_adjacent_block", None


def _apply_heading_boundary_to_text(
    *,
    current_text: str,
    operation: CleanupOperation,
) -> tuple[str | None, str | None]:
    heading = operation.heading_substring.strip()
    body = operation.body_substring.strip()
    if not heading or not body:
        return None, "heading_boundary_missing_exact_parts"
    if heading not in current_text or body not in current_text:
        return None, "heading_boundary_substrings_not_found"
    if current_text.count(heading) > 1:
        return None, "heading_boundary_heading_ambiguous"
    if current_text.count(body) > 1:
        return None, "heading_boundary_body_ambiguous"
    heading_start = current_text.find(heading)
    body_start = current_text.find(body)
    if heading_start > body_start:
        return None, "heading_boundary_order_invalid"
    body_end = body_start + len(body)
    if heading_start == 0 and body_start > heading_start:
        preserved_body = current_text[body_start:].strip()
        gap = current_text[len(heading) : body_start].strip()
        if gap and len(re.sub(r"\s+", "", gap)) > 12:
            return None, "heading_boundary_unaccounted_text"
        return f"{heading}\n\n{preserved_body}", None
    remainder = f"{current_text[:heading_start]}{current_text[len(heading):body_start]}{current_text[body_end:]}".strip()
    if remainder and len(re.sub(r"\s+", "", remainder)) > 12:
        return None, "heading_boundary_unaccounted_text"
    return f"{heading}\n\n{body}", None


def _apply_reclassify_role_to_text(
    *,
    current_text: str,
    block: CleanupBlock,
    operation: CleanupOperation,
) -> tuple[str | None, str | None]:
    target_role = operation.target_role.strip().lower()
    if target_role not in _ALLOWED_RECLASSIFY_TARGET_ROLES:
        return None, "reclassify_target_role_invalid"
    if "\n" in current_text.strip():
        return None, "reclassify_multiline_block_unsupported"
    expected = _reclassify_role_expected_markdown(current_text=current_text, target_role=target_role)
    if expected is None:
        return None, "reclassify_role_not_applicable"
    if operation.expected_after_preview.strip() != expected:
        return None, "reclassify_expected_after_preview_mismatch"
    if target_role == "heading" and block.is_heading:
        return None, "reclassify_role_noop"
    if target_role != "heading" and not block.is_heading:
        return None, "reclassify_source_role_incompatible"
    if _strip_markdown_heading_marker(current_text) != _strip_markdown_heading_marker(expected):
        return None, "reclassify_would_change_visible_text"
    return expected, None


def _reclassify_role_expected_markdown(*, current_text: str, target_role: str) -> str | None:
    visible_text = _strip_markdown_heading_marker(current_text).strip()
    if not visible_text:
        return None
    if target_role == "heading":
        return f"{_RECLASSIFY_MARKDOWN_HEADING_PREFIX}{visible_text}"
    if target_role in {"body", "attribution", "caption"}:
        return visible_text
    return None


def _strip_markdown_heading_marker(text: str) -> str:
    return re.sub(r"^\s*#{1,6}\s+", "", str(text or "").strip(), count=1)


def _is_safe_inline_noise_substring(*, noise: str, current_text: str, reason: str) -> bool:
    normalized_noise = str(noise or "").strip()
    if not normalized_noise:
        return False
    if _SAFE_INLINE_NOISE_PATTERN.fullmatch(normalized_noise) is not None:
        return True
    if _looks_like_numeric_uppercase_running_header_noise(
        normalized_noise=normalized_noise,
        current_text=current_text,
    ):
        return True
    if _looks_like_page_furniture_caption_bridge_noise(
        normalized_noise=normalized_noise,
        current_text=current_text,
        reason=reason,
    ):
        return True
    if _looks_like_inline_caption_noise(
        normalized_noise=normalized_noise,
        current_text=current_text,
        reason=reason,
    ):
        return True
    if _looks_like_duplicate_inline_fragment_noise(
        normalized_noise=normalized_noise,
        current_text=current_text,
        reason=reason,
    ):
        return True
    if reason not in _INLINE_NOISE_REASON_GUIDANCE:
        return False
    return _looks_like_title_case_running_header_noise(normalized_noise=normalized_noise, current_text=current_text)


def _is_exact_isolated_semantic_heading_numeric_prefix_cleanup(
    *,
    current_text: str,
    noise: str,
    replacement: str,
    expected_after_preview: str,
) -> bool:
    if not noise or not re.fullmatch(r"\d{1,4}\s+", noise):
        return False
    if not expected_after_preview or replacement != expected_after_preview.strip():
        return False
    candidate = _find_isolated_semantic_heading_numeric_prefix(current_text)
    if candidate is None:
        return False
    return (
        candidate["numeric_prefix"] == noise
        and candidate["expected_after_preview"] == replacement
        and candidate["semantic_heading_must_remain"] in replacement
    )


def _looks_like_duplicate_inline_fragment_noise(*, normalized_noise: str, current_text: str, reason: str) -> bool:
    if reason != "duplicate_fragment":
        return False
    candidate = normalized_noise.strip()
    if not candidate or "\n" in candidate:
        return False

    candidate_words = _semantic_word_tokens(candidate)
    if len(candidate_words) < 2 or len(candidate_words) > 8:
        return False
    if any(token.isdigit() for token in candidate_words):
        return False

    noise_index = current_text.find(candidate)
    if noise_index < 0:
        return False
    before_words = _semantic_word_tokens(current_text[:noise_index])
    after_words = _semantic_word_tokens(current_text[noise_index + len(candidate) :])
    candidate_lower = [word.lower() for word in candidate_words]
    return (
        len(before_words) >= len(candidate_words)
        and [word.lower() for word in before_words[-len(candidate_words) :]] == candidate_lower
    ) or (
        len(after_words) >= len(candidate_words)
        and [word.lower() for word in after_words[: len(candidate_words)]] == candidate_lower
    )


def _semantic_word_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁё]{2,}", value or "")


def _looks_like_page_furniture_caption_bridge_noise(*, normalized_noise: str, current_text: str, reason: str) -> bool:
    if reason != "page_furniture_inline":
        return False
    candidate = normalized_noise.strip()
    if not candidate:
        return False

    noise_index = current_text.find(candidate)
    if noise_index < 0:
        return False
    noise_end_index = noise_index + len(candidate)
    continuation = current_text[noise_end_index:].lstrip()
    if not continuation or not continuation[0].islower():
        return False

    header_match = re.match(r"^\s*(?:\d{1,4}\s+){1,2}(?:[A-ZА-ЯЁ][A-ZА-ЯЁ-]{2,})(?:\s+[A-ZА-ЯЁ][A-ZА-ЯЁ-]{2,}){0,5}\b", candidate)
    if header_match is None:
        return False
    header = header_match.group(0).strip().rstrip(_RUNNING_HEADER_TRAILING_PUNCTUATION)
    if _NUMERIC_UPPERCASE_RUNNING_HEADER_PATTERN.fullmatch(header) is None:
        return False
    caption_tail = candidate[header_match.end():].strip()
    if len(caption_tail) < 24:
        return False
    caption_tail_lower = caption_tail.lower()
    if not any(marker in caption_tail_lower for marker in ("фото:", "photo:", "photo credit:", "caption:", "иллюстрация:", "рисунок:")):
        return False
    return True


def _looks_like_inline_caption_noise(*, normalized_noise: str, current_text: str, reason: str) -> bool:
    if reason != "page_furniture_inline":
        return False
    candidate = normalized_noise.strip()
    if len(candidate) < 24 or not _has_generic_caption_marker(candidate):
        return False

    noise_index = current_text.find(candidate)
    if noise_index < 0:
        return False
    before = current_text[:noise_index].rstrip()
    after = current_text[noise_index + len(candidate) :].lstrip()
    if after and after[0].islower():
        return True
    return _has_continuation_signal_before_inline_noise(before)


def _has_continuation_signal_before_inline_noise(text: str) -> bool:
    candidate = str(text or "").rstrip()
    if not candidate:
        return False
    if candidate.endswith(("«", "“", "„", "(", "[", "...", "…", ",", ";", ":", "—", "-")):
        return True
    if candidate.endswith((".", "!", "?", "»", "”", '"')):
        return False
    trailing_token_match = re.search(r"([A-Za-zА-Яа-яЁё]{1,12})\s*$", candidate)
    if trailing_token_match is None:
        return False
    return trailing_token_match.group(1).lower() in {
        "a",
        "an",
        "and",
        "as",
        "at",
        "for",
        "from",
        "if",
        "in",
        "of",
        "or",
        "that",
        "the",
        "to",
        "в",
        "во",
        "и",
        "или",
        "к",
        "ко",
        "на",
        "но",
        "о",
        "об",
        "от",
        "по",
        "с",
        "со",
        "что",
    }


def _looks_like_numeric_uppercase_running_header_noise(*, normalized_noise: str, current_text: str) -> bool:
    candidate = normalized_noise.strip()
    if not candidate:
        return False

    shape_candidate = candidate.rstrip(_RUNNING_HEADER_TRAILING_PUNCTUATION).rstrip()
    if not shape_candidate or _NUMERIC_UPPERCASE_RUNNING_HEADER_PATTERN.fullmatch(shape_candidate) is None:
        return False

    noise_index = current_text.find(candidate)
    if noise_index < 0:
        return False
    if noise_index > 0 and current_text[noise_index - 1].isalnum():
        return False
    noise_end_index = noise_index + len(candidate)
    if noise_end_index < len(current_text) and current_text[noise_end_index].isalnum():
        return False

    tokens = [token.strip("()[]{}\"'.,:;!?«»") for token in shape_candidate.split() if token.strip()]
    number_tokens: list[str] = []
    while tokens and tokens[0].isdigit():
        number_tokens.append(tokens.pop(0))
    if not number_tokens or not tokens:
        return False
    if len(number_tokens) > 2:
        return False

    phrase_tokens = [token.lower() for token in tokens if token]
    has_generic_header_token = any(token in _GENERIC_RUNNING_HEADER_TOKENS for token in phrase_tokens)
    has_page_number_shape = any(len(token) >= 3 for token in number_tokens)
    if not has_generic_header_token and not has_page_number_shape:
        return False
    if not has_generic_header_token and len(tokens) > _NUMERIC_UPPERCASE_MAX_TOKENS_WITHOUT_GENERIC_HEADER:
        return False
    return all(token.isupper() for token in tokens)


def _looks_like_title_case_running_header_noise(*, normalized_noise: str, current_text: str) -> bool:
    candidate = normalized_noise.strip()
    if not candidate:
        return False

    noise_index = current_text.find(candidate)
    if noise_index < 0:
        return False

    if noise_index > 0 and current_text[noise_index - 1].isalnum():
        return False
    noise_end_index = noise_index + len(candidate)
    if noise_end_index < len(current_text) and current_text[noise_end_index].isalnum():
        return False

    leading_marker_match = re.match(r"^\d{1,3}\s+", candidate)
    if leading_marker_match is not None:
        candidate = candidate[leading_marker_match.end():].strip()
    if not candidate:
        return False

    header_match = re.fullmatch(r"(.+?)\s+(\d{1,4})", candidate)
    if header_match is None:
        return False
    phrase = header_match.group(1).strip()
    tokens = [token for token in phrase.split() if token]
    if not 2 <= len(tokens) <= 6:
        return False

    capitalized_tokens = 0
    for token in tokens:
        cleaned = token.strip("()[]{}\"'.,:;!?«»")
        if not cleaned:
            return False
        lowered = cleaned.lower()
        if lowered in _HEADER_CONNECTOR_WORDS:
            continue
        if len(cleaned) > 24:
            return False
        if cleaned.isupper() and len(cleaned) >= 2:
            capitalized_tokens += 1
            continue
        if cleaned[0].isupper():
            capitalized_tokens += 1
            continue
        if not cleaned.isalpha():
            return False

    last_cleaned = tokens[-1].strip("()[]{}\"'.,:;!?«»").lower()
    if last_cleaned in _HEADER_CONNECTOR_WORDS:
        return False
    return capitalized_tokens >= 1


def _violates_global_safety(
    *,
    blocks: Sequence[CleanupBlock],
    accepted_ids: Sequence[str],
    config: ReaderCleanupConfig,
) -> bool:
    if not accepted_ids:
        return False

    total_blocks = len(blocks)
    total_chars = sum(block.non_whitespace_char_count for block in blocks)
    deleted_blocks = [_block_by_id(blocks, block_id) for block_id in accepted_ids]
    deleted_char_count = sum(block.non_whitespace_char_count for block in deleted_blocks)
    if total_blocks > 0 and (len(deleted_blocks) / total_blocks) > config.max_delete_block_ratio:
        return True
    if total_chars > 0 and (deleted_char_count / total_chars) > config.max_delete_char_ratio:
        return True

    sorted_indexes = sorted(block.index for block in deleted_blocks)
    longest_run = 1
    current_run = 1
    for previous, current in zip(sorted_indexes, sorted_indexes[1:]):
        if current == previous + 1:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 1
    return longest_run > config.max_consecutive_deleted_blocks


def _max_allowed_reclassify_operations(*, blocks: Sequence[CleanupBlock], config: ReaderCleanupConfig) -> int:
    ratio = max(0.0, config.max_reclassify_block_ratio)
    if ratio <= 0.0 or not blocks:
        return 0
    count = int(len(blocks) * ratio)
    return max(1, count)


def _build_protected_block_ids(*, blocks: Sequence[CleanupBlock], keep_toc: bool) -> set[str]:
    protected_ids: set[str] = set()
    nonempty_blocks = [block for block in blocks if block.text.strip()]
    if nonempty_blocks:
        # The MVP intentionally stays stricter than the minimum spec wording here:
        # the first and last non-empty blocks are always protected.
        protected_ids.add(nonempty_blocks[0].block_id)
        protected_ids.add(nonempty_blocks[-1].block_id)
    if keep_toc:
        protected_ids.update(block.block_id for block in blocks if block.is_toc_like)
    return protected_ids


def _validate_operation(
    *,
    blocks: Sequence[CleanupBlock],
    block: CleanupBlock,
    operation: CleanupOperation,
    protected_ids: set[str],
    config: ReaderCleanupConfig,
    global_candidate_block_ids: set[str],
) -> str | None:
    if operation.text_hash != block.text_hash:
        return "text_hash_mismatch"
    if operation.confidence == "low":
        return "low_confidence"
    if operation.operation == "reclassify_role":
        return _validate_reclassify_role_operation(block=block, operation=operation, protected_ids=protected_ids)
    if operation.operation != "delete_block":
        if block.kind == "footnote_body":
            return "footnote_body_protected"
        if block.is_toc_like:
            return "toc_protected"
        if block.block_id in protected_ids:
            return "protected_block"
        return None
    if _DOCX_IMAGE_PLACEHOLDER_PATTERN.search(block.text):
        return "docx_image_anchor_protected"
    if operation.reason == "page_number" and block.kind != "page_number":
        return "reason_kind_incompatible"
    if operation.reason == "blank_page_marker" and block.kind != "blank_page_marker":
        return "reason_kind_incompatible"
    if operation.reason == "orphan_footnote_marker" and block.kind != "orphan_footnote_marker":
        return "reason_kind_incompatible"
    if operation.reason == "extraction_artifact" and block.kind != "extraction_artifact":
        return "reason_kind_incompatible"
    if block.kind == "footnote_body":
        return "footnote_body_protected"
    if operation.reason == "repeated_running_header":
        if block.block_id not in global_candidate_block_ids:
            return "missing_repetition_evidence"
        if block.kind not in {"paragraph", "page_number", "blank_page_marker", "orphan_footnote_marker", "extraction_artifact"}:
            return "reason_kind_incompatible"
    if operation.reason == "page_furniture_heading":
        if block.kind != "heading":
            return "reason_kind_incompatible"
        if operation.confidence != "high":
            return "heading_protected"
    if block.is_heading and not (
        operation.reason in {"repeated_running_header", "page_furniture_heading"}
        and operation.confidence == "high"
    ):
        return "heading_protected"
    if block.block_id in protected_ids:
        return "protected_block"
    if operation.reason == "page_number" and not _has_safe_standalone_number_delete_context(
        blocks=blocks,
        block=block,
        global_candidate_block_ids=global_candidate_block_ids,
    ):
        return "standalone_number_delete_requires_page_context"
    if block.char_count > config.max_deleted_block_chars:
        return "block_char_limit_exceeded"
    return None


def _validate_reclassify_role_operation(
    *,
    block: CleanupBlock,
    operation: CleanupOperation,
    protected_ids: set[str],
) -> str | None:
    target_role = operation.target_role.strip().lower()
    if target_role not in _ALLOWED_RECLASSIFY_TARGET_ROLES:
        return "reclassify_target_role_invalid"
    if block.kind == "footnote_body":
        return "footnote_body_protected"
    if block.is_toc_like:
        return "toc_protected"
    if block.block_id in protected_ids:
        return "protected_block"
    if target_role == "heading":
        if block.is_heading:
            return "reclassify_role_noop"
        if block.kind not in {"paragraph", "blockquote"}:
            return "reclassify_source_kind_incompatible"
        return None
    if not block.is_heading:
        return "reclassify_source_role_incompatible"
    return None


def _has_safe_standalone_number_delete_context(
    *,
    blocks: Sequence[CleanupBlock],
    block: CleanupBlock,
    global_candidate_block_ids: set[str],
) -> bool:
    text = block.normalized_text.strip()
    if not re.fullmatch(r"\d{1,4}", text):
        return True

    nearby_blocks = [
        candidate
        for candidate in blocks
        if candidate.block_id != block.block_id and abs(candidate.index - block.index) <= 1
    ]
    return any(
        candidate.block_id in global_candidate_block_ids
        or candidate.kind in {"blank_page_marker", "extraction_artifact"}
        for candidate in nearby_blocks
    )


def _validate_same_block_operation_sequence(
    *,
    previous_encountered: Sequence[str],
    previous_applied: Sequence[str],
    operation: CleanupOperation,
) -> str | None:
    if not previous_encountered:
        return None
    if list(previous_encountered) != list(previous_applied):
        return "prior_same_block_operation_not_applied"
    candidate_sequence = tuple(previous_applied) + (operation.operation,)
    if "delete_block" in candidate_sequence and len(candidate_sequence) > 1:
        return "duplicate_operation_incompatible"
    if _is_allowed_join_then_heading_boundary_sequence(candidate_sequence):
        return None

    seen_split = False
    seen_split_count = 0
    seen_normalize_count = 0
    seen_join_count = 0
    previous_phase = 0
    previous_operation = ""
    for operation_name in candidate_sequence:
        phase = _same_block_operation_phase(operation_name=operation_name, seen_split=seen_split)
        if phase < previous_phase:
            return "duplicate_operation_incompatible"
        if phase == previous_phase and operation_name != "remove_inline_noise":
            return "duplicate_operation_incompatible"
        if operation_name == "split_block":
            seen_split_count += 1
            if seen_split_count > 1:
                return "duplicate_operation_incompatible"
            seen_split = True
        elif operation_name == "normalize_heading_boundary":
            seen_normalize_count += 1
            if seen_normalize_count > 1:
                return "duplicate_operation_incompatible"
        elif operation_name == "join_fragmented_paragraph":
            seen_join_count += 1
            if seen_join_count > 1:
                return "duplicate_operation_incompatible"
        if previous_operation == "join_fragmented_paragraph":
            return "duplicate_operation_incompatible"
        previous_phase = phase
        previous_operation = operation_name
    return None


def _is_allowed_join_then_heading_boundary_sequence(candidate_sequence: Sequence[str]) -> bool:
    return tuple(candidate_sequence) in {
        ("join_fragmented_paragraph", "normalize_heading_boundary"),
        ("remove_inline_noise", "join_fragmented_paragraph", "normalize_heading_boundary"),
    }


def _same_block_operation_phase(*, operation_name: str, seen_split: bool) -> int:
    if operation_name == "remove_inline_noise":
        return 3 if seen_split else 1
    if operation_name == "extract_side_heading_and_reattach_body":
        return 2
    if operation_name == "split_block":
        return 3
    if operation_name == "normalize_heading_boundary":
        return 4
    if operation_name == "join_fragmented_paragraph":
        return 5
    if operation_name == "reclassify_role":
        return 6
    if operation_name == "delete_block":
        return 7
    return 99


def _canonicalize_cleanup_operation_sequence(
    *,
    blocks: Sequence[CleanupBlock],
    operations: Sequence[CleanupOperation],
) -> list[tuple[int, int, int, CleanupOperation, str | None]]:
    block_index_by_id = {block.block_id: block.index for block in blocks}
    split_index_by_block_id: dict[str, int] = {}
    join_then_heading_boundary_block_ids: set[str] = set()
    inline_noise_operation_block_ids = {
        operation.block_id for operation in operations if operation.operation == "remove_inline_noise"
    }
    join_next_inline_noise_block_indexes: dict[str, int] = {}
    original_indexes_by_block_id: dict[str, list[int]] = {}
    operation_names_by_block_id: dict[str, set[str]] = {}
    mixed_delete_block_ids: set[str] = set()
    for operation_index, operation in enumerate(operations):
        original_indexes_by_block_id.setdefault(operation.block_id, []).append(operation_index)
        operation_names_by_block_id.setdefault(operation.block_id, set()).add(operation.operation)
        if operation.operation == "split_block" and operation.block_id not in split_index_by_block_id:
            split_index_by_block_id[operation.block_id] = operation_index
        if operation.operation == "join_fragmented_paragraph" and operation.next_id in inline_noise_operation_block_ids:
            next_block_index = block_index_by_id.get(operation.next_id)
            if next_block_index is not None:
                join_next_inline_noise_block_indexes[operation.block_id] = max(
                    join_next_inline_noise_block_indexes.get(operation.block_id, next_block_index),
                    next_block_index,
                )
    join_then_heading_boundary_block_ids = {
        block_id
        for block_id, operation_names in operation_names_by_block_id.items()
        if {"join_fragmented_paragraph", "normalize_heading_boundary"}.issubset(operation_names)
        and not ({"delete_block", "split_block", "extract_side_heading_and_reattach_body"} & operation_names)
    }

    sequenced_entries: list[tuple[int, int, int, CleanupOperation, str | None]] = []
    reordered_block_ids: set[str] = set()
    per_block_entries: dict[str, list[tuple[int, int, CleanupOperation]]] = {}
    for operation_index, operation in enumerate(operations):
        phase = _same_block_original_phase(
            operation=operation,
            operation_index=operation_index,
            split_index_by_block_id=split_index_by_block_id,
            join_then_heading_boundary_block_ids=join_then_heading_boundary_block_ids,
        )
        per_block_entries.setdefault(operation.block_id, []).append((phase, operation_index, operation))

    for block_id, entries in per_block_entries.items():
        operation_names = {operation.operation for _, _, operation in entries}
        if "delete_block" in operation_names and len(operation_names) > 1:
            mixed_delete_block_ids.add(block_id)
            continue
        original_order = [operation_index for _, operation_index, _ in entries]
        canonical_order = [
            operation_index
            for _, operation_index, _ in sorted(entries, key=lambda item: (item[0], item[1]))
        ]
        if canonical_order != original_order:
            reordered_block_ids.add(block_id)

    for operation_index, operation in enumerate(operations):
        if operation.block_id in mixed_delete_block_ids:
            phase = 0 if operation.operation == "delete_block" else 1
        else:
            phase = _same_block_original_phase(
                operation=operation,
                operation_index=operation_index,
                split_index_by_block_id=split_index_by_block_id,
                join_then_heading_boundary_block_ids=join_then_heading_boundary_block_ids,
            )
        block_index = block_index_by_id[operation.block_id]
        deferred_next_block_index = join_next_inline_noise_block_indexes.get(operation.block_id)
        if deferred_next_block_index is not None and operation.operation in {
            "join_fragmented_paragraph",
            "normalize_heading_boundary",
        }:
            block_index = max(block_index, deferred_next_block_index)
            if operation.operation == "join_fragmented_paragraph":
                phase = max(
                    phase,
                    _same_block_operation_phase(operation_name="join_fragmented_paragraph", seen_split=False),
                )
            else:
                phase = max(
                    phase,
                    _same_block_operation_phase(operation_name="join_fragmented_paragraph", seen_split=False) + 1,
                )
        sequence_decision = "operation_sequence_reordered" if operation.block_id in reordered_block_ids else None
        sequenced_entries.append((block_index, phase, operation_index, operation, sequence_decision))

    return sorted(sequenced_entries, key=lambda item: (item[0], item[1], item[2]))


def _same_block_original_phase(
    *,
    operation: CleanupOperation,
    operation_index: int,
    split_index_by_block_id: Mapping[str, int],
    join_then_heading_boundary_block_ids: set[str],
) -> int:
    if operation.block_id in join_then_heading_boundary_block_ids:
        if operation.operation == "join_fragmented_paragraph":
            return 4
        if operation.operation == "normalize_heading_boundary":
            return 5
    split_index = split_index_by_block_id.get(operation.block_id)
    if operation.operation == "remove_inline_noise" and split_index is not None and operation_index > split_index:
        return 3
    return _same_block_operation_phase(operation_name=operation.operation, seen_split=False)


def _validate_duplicate_fragment_delete(
    *,
    blocks: Sequence[CleanupBlock],
    rewritten_blocks: Sequence[str | None],
    block: CleanupBlock,
    current_text: str,
) -> str | None:
    candidate = _normalize_block_text(current_text)
    candidate_non_whitespace = len(re.sub(r"\s+", "", candidate))
    if candidate_non_whitespace < _DUPLICATE_FRAGMENT_MIN_NON_WHITESPACE_CHARS:
        return "duplicate_fragment_too_short"

    nearby_matches = 0
    for other_block in blocks:
        if other_block.block_id == block.block_id:
            continue
        if abs(other_block.index - block.index) > _DUPLICATE_FRAGMENT_MAX_NEARBY_BLOCK_DISTANCE:
            continue
        other_text = rewritten_blocks[other_block.index]
        if other_text is None:
            continue
        other_normalized = _normalize_block_text(other_text)
        if not other_normalized:
            continue
        if candidate == other_normalized or candidate in other_normalized or other_normalized.endswith(candidate):
            nearby_matches += 1
            if nearby_matches > 1:
                return "duplicate_fragment_ambiguous_neighbor_match"

    if nearby_matches != 1:
        return "duplicate_fragment_unique_continuation"
    return None


def _detect_block_kind(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "empty"
    first_line = stripped.splitlines()[0].strip()
    if first_line.startswith("#"):
        return "heading"
    if _PAGE_NUMBER_PATTERN.fullmatch(stripped):
        return "page_number"
    if _BLANK_PAGE_PATTERN.fullmatch(stripped):
        return "blank_page_marker"
    if _ORPHAN_FOOTNOTE_PATTERN.fullmatch(stripped):
        return "orphan_footnote_marker"
    if _FOOTNOTE_BODY_PATTERN.match(stripped):
        return "footnote_body"
    if _EXTRACTION_ARTIFACT_PATTERN.fullmatch(stripped):
        return "extraction_artifact"
    if _TOC_LIKE_PATTERN.search(stripped):
        return "toc_like"
    if first_line.startswith(">"):
        return "blockquote"
    if re.match(r"^(?:[-*]|\d+\.)\s+", first_line):
        return "list"
    return "paragraph"


def _heuristic_reason(block: CleanupBlock) -> str:
    stripped = block.normalized_text
    if _PAGE_NUMBER_PATTERN.fullmatch(stripped):
        return "page_number"
    if _BLANK_PAGE_PATTERN.fullmatch(stripped):
        return "blank_page_marker"
    if _ORPHAN_FOOTNOTE_PATTERN.fullmatch(stripped):
        return "orphan_footnote_marker"
    if _EXTRACTION_ARTIFACT_PATTERN.fullmatch(stripped):
        return "extraction_artifact"
    if block.is_heading:
        return "page_furniture_heading"
    return "repeated_running_header"


def _normalize_block_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")]
    return "\n".join(lines).strip()


def _require_nonempty_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"reader_cleanup_missing_field:{key}")
    return value.strip()


def _serialize_delete_block(*, block: CleanupBlock, reason: str, confidence: str) -> dict[str, object]:
    preview = block.text.replace("\n", " ").strip()
    if len(preview) > 160:
        preview = preview[:157].rstrip() + "..."
    return {
        "id": block.block_id,
        "text_hash": block.text_hash,
        "reason": reason,
        "confidence": confidence,
        "raw_text_preview": preview,
        "char_count": block.char_count,
        "kind": block.kind,
    }


def _serialize_cleanup_operation(*, operation: CleanupOperation, block: CleanupBlock) -> dict[str, object]:
    payload = _serialize_delete_block(block=block, reason=operation.reason, confidence=operation.confidence)
    payload.update(
        {
            "operation": operation.operation,
            "evidence_before": operation.evidence_before,
            "expected_after_preview": operation.expected_after_preview,
            "safety_note": operation.safety_note,
        }
    )
    if operation.split_substrings:
        payload["split_substrings"] = list(operation.split_substrings)
    if operation.noise_substring:
        payload["noise_substring"] = operation.noise_substring
    if operation.next_id:
        payload["next_id"] = operation.next_id
    if operation.next_text_hash:
        payload["next_text_hash"] = operation.next_text_hash
    if operation.pre_body_stub:
        payload["pre_body_stub"] = operation.pre_body_stub
    if operation.heading_substring:
        payload["heading_substring"] = operation.heading_substring
    if operation.body_substring:
        payload["body_substring"] = operation.body_substring
    if operation.post_body_continuation:
        payload["post_body_continuation"] = operation.post_body_continuation
    if operation.target_role:
        payload["target_role"] = operation.target_role
    return payload


def _block_by_id(blocks: Sequence[CleanupBlock], block_id: str) -> CleanupBlock:
    for block in blocks:
        if block.block_id == block_id:
            return block
    raise KeyError(block_id)


def _coerce_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _coerce_int(value: object, *, default: int, minimum: int) -> int:
    try:
        return max(int(cast(Any, value)), minimum)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped in {"1", "true", "yes", "on"}:
            return True
        if stripped in {"0", "false", "no", "off"}:
            return False
        if not stripped:
            return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_float(value: object, *, default: float) -> float:
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return default
