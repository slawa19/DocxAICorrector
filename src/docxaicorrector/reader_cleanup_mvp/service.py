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


from ._chunking import (  # noqa: F401
    _anchor_overlap_score,
    _anchor_signal_tokens,
    _build_anchor_repair_chunks,
    _build_cleanup_chunks,
    _has_generic_caption_marker,
    _make_cleanup_chunk,
    _make_manual_cleanup_chunk,
    _normalize_anchor_targets,
    _readonly_context_blocks_by_id,
    _resolve_page_furniture_caption_anchor_block,
)


from ._planning import (  # noqa: F401
    _build_chunk_request_payload,
    _build_global_plan,
    _build_reannotation_request_payload,
    _parse_global_plan_response,
    _parse_reannotation_response,
)


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


from ._parse import (  # noqa: F401
    _build_cleanup_schema_repair_payload,
    _extract_first_json_object_text,
    _filter_anchor_repair_operations_to_anchor_targets,
    _inline_noise_removed_text,
    _is_allowed_page_anchor_followup_join,
    _is_recoverable_inline_noise_substring_from_preview,
    _load_cleanup_response_object,
    _load_cleanup_response_payload,
    _merge_anchor_repair_pass_into_report,
    _normalize_delete_block_item,
    _parse_cleanup_response,
    _recover_expected_after_preview,
    _recover_heading_boundary_parts_from_preview,
    _recover_inline_noise_substring_from_preview,
    _recover_missing_operation_exact_fields,
    _run_anchor_repair_pass,
    _strip_preview_ellipsis,
)


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
