from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from ._constants import (
    _BLANK_PAGE_PATTERN,
    _EXTRACTION_ARTIFACT_PATTERN,
    _FOOTNOTE_BODY_PATTERN,
    _ORPHAN_FOOTNOTE_PATTERN,
    _PAGE_NUMBER_PATTERN,
    _TOC_LIKE_PATTERN,
)
from ._models import CleanupBlock, CleanupOperation


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
