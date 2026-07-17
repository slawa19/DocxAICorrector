from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ._constants import (
    CleanupConfidence,
    CleanupPolicy,
    _DEFAULT_CLEANUP_CHUNK_SIZE,
    _DEFAULT_GLOBAL_PLAN_ENABLED,
    _DEFAULT_OVERLAP_BLOCKS_AFTER,
    _DEFAULT_OVERLAP_BLOCKS_BEFORE,
)


@dataclass(frozen=True)
class ReaderCleanupConfig:
    enabled: bool = False
    model: str = ""
    chunk_size: int = _DEFAULT_CLEANUP_CHUNK_SIZE
    overlap_blocks_before: int = _DEFAULT_OVERLAP_BLOCKS_BEFORE
    overlap_blocks_after: int = _DEFAULT_OVERLAP_BLOCKS_AFTER
    global_plan_enabled: bool = _DEFAULT_GLOBAL_PLAN_ENABLED
    keep_toc: bool = True
    drop_back_matter: bool = False
    max_delete_block_ratio: float = 0.03
    max_delete_char_ratio: float = 0.05
    max_reclassify_block_ratio: float = 0.05
    max_failed_chunk_ratio: float = 1.0
    max_consecutive_deleted_blocks: int = 3
    max_deleted_block_chars: int = 300
    policy: CleanupPolicy = "advisory"
    allowed_operations: tuple[str, ...] = ()


@dataclass(frozen=True)
class CleanupBlock:
    index: int
    block_id: str
    text: str
    normalized_text: str
    text_hash: str
    char_count: int
    non_whitespace_char_count: int
    kind: str
    is_heading: bool
    is_toc_like: bool
    paragraph_id: str | None = None
    merged_paragraph_ids: tuple[str, ...] = ()
    layout_signals: Mapping[str, object] | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.block_id,
            "text_hash": self.text_hash,
            "kind": self.kind,
            "char_count": self.char_count,
            "is_heading": self.is_heading,
            "is_toc_like": self.is_toc_like,
            "text": self.text,
        }
        if self.paragraph_id:
            payload["paragraph_id"] = self.paragraph_id
        if self.merged_paragraph_ids:
            payload["merged_paragraph_ids"] = list(self.merged_paragraph_ids)
        if self.layout_signals:
            payload["layout_signals"] = dict(self.layout_signals)
        return payload


@dataclass(frozen=True)
class CleanupChunk:
    chunk_index: int
    start_index: int
    end_index: int
    blocks: tuple[CleanupBlock, ...]
    context_before: str
    context_after: str
    context_before_blocks: tuple[CleanupBlock, ...] = ()
    context_after_blocks: tuple[CleanupBlock, ...] = ()


@dataclass(frozen=True)
class CleanupOperation:
    block_id: str
    text_hash: str
    operation: str
    reason: str
    confidence: CleanupConfidence
    chunk_index: int
    evidence_before: str = ""
    expected_after_preview: str = ""
    safety_note: str = ""
    split_substrings: tuple[str, ...] = ()
    noise_substring: str = ""
    next_id: str = ""
    next_text_hash: str = ""
    pre_body_stub: str = ""
    heading_substring: str = ""
    body_substring: str = ""
    post_body_continuation: str = ""
    target_role: str = ""


class ReaderCleanupStageError(RuntimeError):
    def __init__(self, message: str, *, report_payload: Mapping[str, Any], raw_markdown: str) -> None:
        super().__init__(message)
        self.report_payload = dict(report_payload)
        self.raw_markdown = raw_markdown


@dataclass(frozen=True)
class ReaderCleanupResult:
    changed: bool
    raw_markdown: str
    cleaned_markdown: str
    report_payload: dict[str, Any]
    accepted_delete_block_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReannotationDecision:
    block_id: str
    text_hash: str
    role: str
    chunk_index: int
    heading_text: str = ""
    body_text: str = ""
    marker_text: str = ""
    list_items: tuple[str, ...] = ()
    confidence: CleanupConfidence = "medium"
    reason: str = ""


@dataclass(frozen=True)
class AnchorRepairChunk:
    chunk: CleanupChunk
    anchors: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class AnchorRepairPassResult:
    cleaned_markdown: str
    warnings: tuple[str, ...]
    accepted_delete_blocks: tuple[dict[str, object], ...]
    accepted_cleanup_operations: tuple[dict[str, object], ...]
    ignored_cleanup_operations: tuple[dict[str, object], ...]
    chunk_results: tuple[dict[str, object], ...]
    deleted_char_count: int
    requested_anchor_count: int
    selected_anchor_count: int
    selected_window_block_count: int
    selected_anchors: tuple[dict[str, str], ...]
