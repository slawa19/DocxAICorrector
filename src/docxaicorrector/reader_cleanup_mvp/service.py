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


from ._config import (  # noqa: F401
    resolve_reader_cleanup_config,
    _coerce_allowed_operations,
)


from ._prompts import (  # noqa: F401
    build_reader_cleanup_global_plan_system_prompt,
    build_reader_cleanup_reannotation_system_prompt,
    build_reader_cleanup_schema_repair_system_prompt,
    build_reader_cleanup_system_prompt,
)


from ._blocks import (  # noqa: F401
    build_cleanup_blocks,
    _derive_cleanup_block_layout_signals,
    _sanitize_layout_signals,
    _select_cleanup_blocks,
)


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


from ._detectors import (  # noqa: F401
    _allowed_operations_for_config,
    _build_duplicate_semantic_heading_target,
    _build_heading_fused_with_body_target,
    _build_isolated_semantic_heading_numeric_prefix_target,
    _build_operation_selection_targets,
    _build_semantic_page_title_deletion_risk_target,
    _build_side_heading_island_targets,
    _find_adjacent_duplicate_phrase,
    _find_heading_fused_with_body_parts,
    _find_isolated_semantic_heading_numeric_prefix,
    _find_trailing_page_like_semantic_title,
    _find_wrapped_heading_fused_with_body_parts,
    _has_side_heading_left_context,
    _has_side_heading_right_context,
    _looks_like_fused_heading_prefix,
    _looks_like_heading_body_remainder,
    _looks_like_isolated_semantic_heading_text,
    _looks_like_side_heading_phrase,
)


from ._report import (  # noqa: F401
    _build_anchor_repair_request_payload,
    _build_cleanup_stats,
    _build_failed_chunk_diagnostics,
    _build_heading_boundary_application_diagnostics,
    _build_heading_boundary_diagnostic_example,
    _build_reader_cleanup_report_payload,
    _docx_image_placeholder_counts,
    _extract_docx_image_placeholder_ids,
    _extract_http_status_code,
    _failed_chunk_ratio,
    _failed_chunk_ratio_exceeds_threshold,
    _image_reconciliation_warnings,
    _is_auth_or_credential_error,
    _iter_exception_chain,
    _preview_text,
    _reconcile_docx_image_placeholders,
    _serialize_cleanup_settings,
)


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


from ._apply import (  # noqa: F401
    _apply_cleanup_operations,
    _apply_heading_boundary_across_adjacent_block,
    _apply_heading_boundary_to_joined_previous_block,
    _apply_heading_boundary_to_text,
    _apply_reannotation_decisions,
    _apply_reclassify_role_to_text,
    _apply_side_heading_reattach_to_text,
    _apply_single_operation_to_blocks,
    _join_body_stub_and_continuation,
    _list_visible_content_fingerprint,
    _ordered_substrings_cover_text,
    _reannotation_replacement_preserves_visible_content,
    _reclassify_role_expected_markdown,
    _replacement_for_reannotation_decision,
    _replacement_for_reannotation_footnote_marker,
    _replacement_for_reannotation_list_items,
    _strip_markdown_heading_marker,
    _visible_content_fingerprint,
)


from ._validate import (  # noqa: F401
    _build_protected_block_ids,
    _canonicalize_cleanup_operation_sequence,
    _has_continuation_signal_before_inline_noise,
    _has_safe_standalone_number_delete_context,
    _is_allowed_join_then_heading_boundary_sequence,
    _is_exact_isolated_semantic_heading_numeric_prefix_cleanup,
    _is_safe_inline_noise_substring,
    _looks_like_duplicate_inline_fragment_noise,
    _looks_like_inline_caption_noise,
    _looks_like_numeric_uppercase_running_header_noise,
    _looks_like_page_furniture_caption_bridge_noise,
    _looks_like_title_case_running_header_noise,
    _max_allowed_reclassify_operations,
    _same_block_operation_phase,
    _same_block_original_phase,
    _semantic_word_tokens,
    _validate_duplicate_fragment_delete,
    _validate_operation,
    _validate_reclassify_role_operation,
    _validate_same_block_operation_sequence,
    _violates_global_safety,
)


from ._utils import (  # noqa: F401
    _block_by_id,
    _coerce_bool,
    _coerce_float,
    _coerce_int,
    _coerce_string_list,
    _detect_block_kind,
    _heuristic_reason,
    _normalize_block_text,
    _require_nonempty_str,
    _serialize_cleanup_operation,
    _serialize_delete_block,
)
