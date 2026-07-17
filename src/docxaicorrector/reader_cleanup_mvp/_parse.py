from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from ._apply import _apply_cleanup_operations, _reclassify_role_expected_markdown
from ._blocks import build_cleanup_blocks
from ._chunking import _build_anchor_repair_chunks, _normalize_anchor_targets
from ._constants import (
    _ALLOWED_CONFIDENCE,
    _ALLOWED_DELETE_REASONS,
    _ALLOWED_OPERATIONS,
    _ALLOWED_RECLASSIFY_TARGET_ROLES,
    _BLOCK_RESPONSE_FIELDS,
    _INLINE_NOISE_REASON_GUIDANCE,
    _OPERATION_RESPONSE_FIELDS,
    _SAFE_CONFIDENCE_INFERENCE,
    _SAFE_INLINE_NOISE_PATTERN,
    _TOP_LEVEL_RESPONSE_FIELDS,
)
from ._models import (
    AnchorRepairPassResult,
    CleanupBlock,
    CleanupConfidence,
    CleanupOperation,
    ReaderCleanupConfig,
)
from ._report import (
    _build_anchor_repair_request_payload,
    _build_cleanup_stats,
    _build_heading_boundary_application_diagnostics,
)
from ._utils import (
    _block_by_id,
    _coerce_int,
    _require_nonempty_str,
    _serialize_cleanup_operation,
    _serialize_delete_block,
)
from ._validate import _is_safe_inline_noise_substring, _looks_like_duplicate_inline_fragment_noise


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
