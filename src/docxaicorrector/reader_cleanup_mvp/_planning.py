from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from ._constants import (
    _ALLOWED_CONFIDENCE,
    _ALLOWED_DELETE_REASONS,
    _ALLOWED_REANNOTATION_ROLES,
    _ALLOWED_RECLASSIFY_TARGET_ROLES,
    _REMOVE_INLINE_NOISE_REASON_GUIDANCE,
)
from ._detectors import _allowed_operations_for_config, _build_operation_selection_targets
from ._models import (
    CleanupBlock,
    CleanupChunk,
    CleanupConfidence,
    ReaderCleanupConfig,
    ReannotationDecision,
)
from ._parse import _load_cleanup_response_object
from ._report import _serialize_cleanup_settings
from ._utils import _coerce_string_list, _heuristic_reason


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
