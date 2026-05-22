from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast


CleanupPolicy = Literal["off", "advisory", "strict"]
CleanupConfidence = Literal["low", "medium", "high"]

_ALLOWED_POLICIES = {"off", "advisory", "strict"}
_ALLOWED_CONFIDENCE = {"low", "medium", "high"}
_ALLOWED_REASONS = {
    "blank_page_marker",
    "extraction_artifact",
    "orphan_footnote_marker",
    "page_furniture_heading",
    "page_number",
    "repeated_running_header",
}
_TOP_LEVEL_RESPONSE_FIELDS = {"delete_blocks", "warnings"}
_BLOCK_RESPONSE_FIELDS = {"id", "text_hash", "reason", "confidence"}
_PAGE_NUMBER_PATTERN = re.compile(r"^(?:\(?\d{1,4}\)?|[Pp]age\s+\d{1,4}|стр\.\s*\d{1,4})$")
_BLANK_PAGE_PATTERN = re.compile(r"^(?:blank\s+page|this page intentionally left blank)$", re.IGNORECASE)
_ORPHAN_FOOTNOTE_PATTERN = re.compile(r"^(?:\[?\d{1,3}\]?|\(\d{1,3}\))$")
_FOOTNOTE_BODY_PATTERN = re.compile(r"^(?:\[\d{1,3}\]|\(\d{1,3}\))\s+\S")
_TOC_LIKE_PATTERN = re.compile(r"(?:\.{3,}|…{2,}|\s\d{1,4}\s*$)")
_EXTRACTION_ARTIFACT_PATTERN = re.compile(
    r"^(?:\[\[DOCX_[A-Za-z0-9_]+\]\]|\[\[IMAGE_[A-Za-z0-9_]+\]\]|<\/?placeholder>|---+|===+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReaderCleanupConfig:
    enabled: bool = False
    model: str = ""
    chunk_size: int = 30000
    global_plan_enabled: bool = True
    keep_toc: bool = True
    drop_back_matter: bool = False
    max_delete_block_ratio: float = 0.03
    max_delete_char_ratio: float = 0.05
    max_consecutive_deleted_blocks: int = 3
    max_deleted_block_chars: int = 300
    policy: CleanupPolicy = "advisory"


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

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.block_id,
            "text_hash": self.text_hash,
            "kind": self.kind,
            "char_count": self.char_count,
            "is_heading": self.is_heading,
            "is_toc_like": self.is_toc_like,
            "text": self.text,
        }


@dataclass(frozen=True)
class CleanupChunk:
    chunk_index: int
    start_index: int
    end_index: int
    blocks: tuple[CleanupBlock, ...]
    context_before: str
    context_after: str


@dataclass(frozen=True)
class CleanupOperation:
    block_id: str
    text_hash: str
    reason: str
    confidence: CleanupConfidence
    chunk_index: int


class ReaderCleanupStageError(RuntimeError):
    def __init__(self, message: str, *, report_payload: Mapping[str, object], raw_markdown: str) -> None:
        super().__init__(message)
        self.report_payload = dict(report_payload)
        self.raw_markdown = raw_markdown


@dataclass(frozen=True)
class ReaderCleanupResult:
    changed: bool
    raw_markdown: str
    cleaned_markdown: str
    report_payload: dict[str, object]
    accepted_delete_block_ids: tuple[str, ...]


def resolve_reader_cleanup_config(*, app_config: Mapping[str, object], fallback_model: str) -> ReaderCleanupConfig:
    raw_policy = str(app_config.get("reader_cleanup_policy", "advisory") or "advisory").strip().lower()
    policy = raw_policy if raw_policy in _ALLOWED_POLICIES else "advisory"
    enabled = bool(app_config.get("reader_cleanup_enabled", False)) and policy != "off"
    model = str(app_config.get("reader_cleanup_model", "") or "").strip() or fallback_model
    return ReaderCleanupConfig(
        enabled=enabled,
        model=model,
        chunk_size=_coerce_int(app_config.get("reader_cleanup_chunk_size", 30000), default=30000, minimum=3000),
        global_plan_enabled=bool(app_config.get("reader_cleanup_global_plan_enabled", True)),
        keep_toc=bool(app_config.get("reader_cleanup_keep_toc", True)),
        drop_back_matter=bool(app_config.get("reader_cleanup_drop_back_matter", False)),
        max_delete_block_ratio=_coerce_float(app_config.get("reader_cleanup_max_delete_block_ratio", 0.03), default=0.03),
        max_delete_char_ratio=_coerce_float(app_config.get("reader_cleanup_max_delete_char_ratio", 0.05), default=0.05),
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
        policy=policy,
    )


def build_reader_cleanup_system_prompt() -> str:
    return (
        "You are cleaning translated book Markdown for reading.\n"
        "Do not translate, rewrite, summarize, reorder, or reformat the book.\n"
        "Return JSON only with top-level fields delete_blocks and warnings.\n"
        "Delete only non-semantic PDF/OCR/layout noise: repeated running headers, footers, "
        "page numbers, blank-page markers, orphaned footnote markers, and obvious extraction artifacts.\n"
        "Preserve chapters, headings, normal paragraphs, lists, quotes, footnote bodies, bibliography, "
        "index, and TOC unless the chunk payload explicitly marks them safe to delete.\n"
        "Each delete_blocks item must contain id, text_hash, reason, confidence.\n"
        "If uncertain, keep the text and add a warning."
    )


def build_cleanup_blocks(markdown_text: str) -> list[CleanupBlock]:
    normalized_markdown = str(markdown_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_markdown:
        return []

    raw_blocks = [part.strip("\n") for part in re.split(r"\n\s*\n+", normalized_markdown) if part.strip()]
    blocks: list[CleanupBlock] = []
    for index, raw_block in enumerate(raw_blocks):
        normalized_text = _normalize_block_text(raw_block)
        kind = _detect_block_kind(normalized_text)
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
            )
        )
    return blocks


def run_reader_cleanup(
    *,
    markdown_text: str,
    config: ReaderCleanupConfig,
    operation_provider: Callable[[Mapping[str, object], int, int], str],
) -> ReaderCleanupResult:
    blocks = build_cleanup_blocks(markdown_text)
    raw_markdown = str(markdown_text or "")
    if not blocks:
        report_payload = {
            "version": 1,
            "policy": config.policy,
            "stage_status": "completed",
            "changed": False,
            "warnings": ["reader_cleanup_skipped_empty_markdown"],
            "stats": {"raw_block_count": 0, "cleanup_chunk_count": 0},
            "global_plan": {"repeated_noise_patterns": [], "candidate_block_ids": [], "warnings": []},
            "accepted_delete_blocks": [],
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

    global_plan = _build_global_plan(blocks=blocks, config=config)
    chunks = _build_cleanup_chunks(blocks=blocks, chunk_size=config.chunk_size)
    all_operations: list[CleanupOperation] = []
    warnings: list[str] = list(global_plan.get("warnings", [])) if isinstance(global_plan.get("warnings"), list) else []
    ignored_delete_blocks: list[dict[str, object]] = []
    chunk_results: list[dict[str, object]] = []

    for chunk in chunks:
        request_payload = _build_chunk_request_payload(chunk=chunk, global_plan=global_plan, config=config)
        started_at = time.perf_counter()
        try:
            raw_response = operation_provider(request_payload, chunk.chunk_index, len(chunks))
            operations, chunk_warnings = _parse_cleanup_response(
                raw_response=raw_response,
                editable_block_ids={block.block_id for block in chunk.blocks},
                chunk_index=chunk.chunk_index,
            )
        except Exception as exc:
            warning = f"reader_cleanup_chunk_failed:{chunk.chunk_index}:{exc}"
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
            chunk_results.append(
                {
                    "chunk_index": chunk.chunk_index,
                    "status": "failed",
                    "target_block_count": len(chunk.blocks),
                    "target_chars": sum(block.char_count for block in chunk.blocks),
                    "elapsed_ms": elapsed_ms,
                    "proposed_delete_block_count": 0,
                    "accepted_delete_block_count": 0,
                    "ignored_delete_block_count": 0,
                    "warning": warning,
                }
            )
            warnings.append(warning)
            if config.policy == "strict":
                report_payload = _build_reader_cleanup_report_payload(
                    raw_markdown=raw_markdown,
                    config=config,
                    blocks=blocks,
                    global_plan=global_plan,
                    warnings=warnings,
                    accepted_delete_blocks=[],
                    ignored_delete_blocks=ignored_delete_blocks,
                    chunk_results=chunk_results,
                    deleted_char_count=0,
                    changed=False,
                    failure={
                        "kind": "chunk_failed",
                        "chunk_index": chunk.chunk_index,
                        "error_message": str(exc),
                    },
                )
                raise ReaderCleanupStageError(
                    f"reader_cleanup_chunk_failed:{chunk.chunk_index}:{exc}",
                    report_payload=report_payload,
                    raw_markdown=raw_markdown,
                ) from exc
            continue

        all_operations.extend(operations)
        warnings.extend(chunk_warnings)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        chunk_results.append(
            {
                "chunk_index": chunk.chunk_index,
                "status": "completed",
                "target_block_count": len(chunk.blocks),
                "target_chars": sum(block.char_count for block in chunk.blocks),
                "elapsed_ms": elapsed_ms,
                "proposed_delete_block_count": len(operations),
                "accepted_delete_block_count": 0,
                "ignored_delete_block_count": 0,
            }
        )

    cleaned_markdown, accepted_ids, ignored = _apply_cleanup_operations(
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
    ignored_delete_blocks.extend(ignored)

    accepted_delete_blocks: list[dict[str, object]] = []
    accepted_counts_by_chunk: Counter[int] = Counter()
    for block_id, entry in accepted_ids.items():
        block = _block_by_id(blocks, block_id)
        chunk_index = int(entry["chunk_index"])
        accepted_delete_blocks.append(
            {
                **_serialize_delete_block(block=block, reason=str(entry["reason"]), confidence=str(entry["confidence"])),
                "chunk_index": chunk_index,
                "after_state": "deleted",
            }
        )
        accepted_counts_by_chunk[chunk_index] += 1

    ignored_counts_by_chunk: Counter[int] = Counter()
    for entry in ignored_delete_blocks:
        chunk_index = entry.get("chunk_index")
        if isinstance(chunk_index, int):
            ignored_counts_by_chunk[chunk_index] += 1

    for chunk_result in chunk_results:
        chunk_index = chunk_result.get("chunk_index")
        if not isinstance(chunk_index, int) or chunk_result.get("status") != "completed":
            continue
        chunk_result["accepted_delete_block_count"] = accepted_counts_by_chunk.get(chunk_index, 0)
        chunk_result["ignored_delete_block_count"] = ignored_counts_by_chunk.get(chunk_index, 0)

    deleted_char_count = sum(_block_by_id(blocks, block_id).non_whitespace_char_count for block_id in accepted_ids)
    report_payload = _build_reader_cleanup_report_payload(
        raw_markdown=raw_markdown,
        config=config,
        blocks=blocks,
        global_plan=global_plan,
        warnings=warnings,
        accepted_delete_blocks=accepted_delete_blocks,
        ignored_delete_blocks=ignored_delete_blocks,
        chunk_results=chunk_results,
        deleted_char_count=deleted_char_count,
        changed=cleaned_markdown != raw_markdown,
    )
    return ReaderCleanupResult(
        changed=cleaned_markdown != raw_markdown,
        raw_markdown=raw_markdown,
        cleaned_markdown=cleaned_markdown,
        report_payload=report_payload,
        accepted_delete_block_ids=tuple(accepted_ids.keys()),
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


def _build_cleanup_chunks(*, blocks: Sequence[CleanupBlock], chunk_size: int) -> list[CleanupChunk]:
    if not blocks:
        return []

    chunks: list[CleanupChunk] = []
    current_blocks: list[CleanupBlock] = []
    current_chars = 0
    chunk_start = 0
    for block in blocks:
        separator_chars = 2 if current_blocks else 0
        projected_chars = current_chars + separator_chars + block.char_count
        if current_blocks and projected_chars > chunk_size:
            chunk_end = current_blocks[-1].index
            chunks.append(
                CleanupChunk(
                    chunk_index=len(chunks) + 1,
                    start_index=chunk_start,
                    end_index=chunk_end,
                    blocks=tuple(current_blocks),
                    context_before=blocks[chunk_start - 1].text if chunk_start > 0 else "",
                    context_after=blocks[chunk_end + 1].text if chunk_end + 1 < len(blocks) else "",
                )
            )
            chunk_start = block.index
            current_blocks = [block]
            current_chars = block.char_count
            continue

        current_blocks.append(block)
        current_chars = projected_chars

    if current_blocks:
        chunk_end = current_blocks[-1].index
        chunks.append(
            CleanupChunk(
                chunk_index=len(chunks) + 1,
                start_index=chunk_start,
                end_index=chunk_end,
                blocks=tuple(current_blocks),
                context_before=blocks[chunk_start - 1].text if chunk_start > 0 else "",
                context_after=blocks[chunk_end + 1].text if chunk_end + 1 < len(blocks) else "",
            )
        )
    return chunks


def _build_global_plan(*, blocks: Sequence[CleanupBlock], config: ReaderCleanupConfig) -> dict[str, object]:
    repeated_noise_patterns: list[dict[str, object]] = []
    candidate_block_ids: list[str] = []
    warnings: list[str] = []
    if not config.global_plan_enabled:
        return {
            "repeated_noise_patterns": repeated_noise_patterns,
            "candidate_block_ids": candidate_block_ids,
            "warnings": warnings,
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

    return {
        "repeated_noise_patterns": repeated_noise_patterns,
        "candidate_block_ids": candidate_block_ids,
        "warnings": warnings,
    }


def _build_chunk_request_payload(
    *,
    chunk: CleanupChunk,
    global_plan: Mapping[str, object],
    config: ReaderCleanupConfig,
) -> dict[str, object]:
    return {
        "policy": config.policy,
        "keep_toc": config.keep_toc,
        "drop_back_matter": config.drop_back_matter,
        "editable_block_ids": [block.block_id for block in chunk.blocks],
        "context_before_preview": chunk.context_before[:240],
        "context_after_preview": chunk.context_after[:240],
        "global_plan": global_plan,
        "blocks": [block.to_payload() for block in chunk.blocks],
    }


def _build_reader_cleanup_report_payload(
    *,
    raw_markdown: str,
    config: ReaderCleanupConfig,
    blocks: Sequence[CleanupBlock],
    global_plan: Mapping[str, object],
    warnings: Sequence[str],
    accepted_delete_blocks: Sequence[Mapping[str, object]],
    ignored_delete_blocks: Sequence[Mapping[str, object]],
    chunk_results: Sequence[Mapping[str, object]],
    deleted_char_count: int,
    changed: bool,
    failure: Mapping[str, object] | None = None,
) -> dict[str, object]:
    total_non_whitespace_chars = sum(block.non_whitespace_char_count for block in blocks)
    failed_chunk_count = sum(1 for entry in chunk_results if entry.get("status") == "failed")
    proposed_delete_block_count = sum(
        int(entry.get("proposed_delete_block_count", 0) or 0) for entry in chunk_results
    )
    report_payload = {
        "version": 1,
        "policy": config.policy,
        "model": config.model,
        "stage_status": "failed_preserved_base_result" if failure is not None else "completed",
        "changed": changed,
        "warnings": list(warnings),
        "stats": {
            "raw_block_count": len(blocks),
            "raw_char_count": len(raw_markdown),
            "cleanup_chunk_count": len(chunk_results),
            "failed_chunk_count": failed_chunk_count,
            "proposed_delete_block_count": proposed_delete_block_count,
            "accepted_delete_block_count": len(accepted_delete_blocks),
            "ignored_delete_block_count": len(ignored_delete_blocks),
            "deleted_non_whitespace_char_count": deleted_char_count,
            "deleted_char_ratio": 0.0 if total_non_whitespace_chars <= 0 else round(deleted_char_count / total_non_whitespace_chars, 6),
        },
        "global_plan": dict(global_plan),
        "accepted_delete_blocks": list(accepted_delete_blocks),
        "ignored_delete_blocks": list(ignored_delete_blocks),
        "chunk_results": [dict(entry) for entry in chunk_results],
    }
    if failure is not None:
        report_payload["failure"] = dict(failure)
    return report_payload


def _parse_cleanup_response(
    *,
    raw_response: str,
    editable_block_ids: set[str],
    chunk_index: int,
) -> tuple[list[CleanupOperation], list[str]]:
    payload = json.loads(raw_response)
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

    operations: list[CleanupOperation] = []
    seen_ids: set[str] = set()
    for item in delete_blocks:
        if not isinstance(item, dict):
            raise RuntimeError("reader_cleanup_delete_block_item_must_be_object")
        unknown_block_fields = sorted(set(item.keys()) - _BLOCK_RESPONSE_FIELDS)
        if unknown_block_fields:
            raise RuntimeError(f"reader_cleanup_unknown_operation_fields:{','.join(unknown_block_fields)}")

        block_id = _require_nonempty_str(item, "id")
        text_hash = _require_nonempty_str(item, "text_hash")
        reason = _require_nonempty_str(item, "reason")
        confidence = _require_nonempty_str(item, "confidence").lower()

        if block_id in seen_ids:
            raise RuntimeError(f"reader_cleanup_duplicate_block_id:{block_id}")
        if block_id not in editable_block_ids:
            raise RuntimeError(f"reader_cleanup_block_outside_chunk:{block_id}")
        if reason not in _ALLOWED_REASONS:
            raise RuntimeError(f"reader_cleanup_unknown_reason:{reason}")
        if confidence not in _ALLOWED_CONFIDENCE:
            raise RuntimeError(f"reader_cleanup_unknown_confidence:{confidence}")

        seen_ids.add(block_id)
        operations.append(
            CleanupOperation(
                block_id=block_id,
                text_hash=text_hash,
                reason=reason,
                confidence=confidence,
                chunk_index=chunk_index,
            )
        )

    return operations, [str(item) for item in warnings]


def _apply_cleanup_operations(
    *,
    raw_markdown: str,
    blocks: Sequence[CleanupBlock],
    operations: Sequence[CleanupOperation],
    config: ReaderCleanupConfig,
    global_candidate_block_ids: set[str],
) -> tuple[str, dict[str, dict[str, object]], list[dict[str, object]]]:
    if not operations:
        return raw_markdown, {}, []

    protected_ids = _build_protected_block_ids(blocks=blocks, keep_toc=config.keep_toc)
    accepted: dict[str, dict[str, object]] = {}
    ignored: list[dict[str, object]] = []
    operations_by_index = sorted(
        ((
            _block_by_id(blocks, operation.block_id).index,
            operation,
        ) for operation in operations),
        key=lambda item: item[0],
    )

    for _, operation in operations_by_index:
        block = _block_by_id(blocks, operation.block_id)
        ignore_reason = _validate_operation(
            block=block,
            operation=operation,
            protected_ids=protected_ids,
            config=config,
            global_candidate_block_ids=global_candidate_block_ids,
        )
        if ignore_reason is not None:
            ignored.append(
                {
                    **_serialize_delete_block(block=block, reason=operation.reason, confidence=operation.confidence),
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": ignore_reason,
                }
            )
            continue
        accepted[block.block_id] = {
            "reason": operation.reason,
            "confidence": operation.confidence,
            "chunk_index": operation.chunk_index,
        }

    if not accepted:
        return raw_markdown, {}, ignored

    if _violates_global_safety(blocks=blocks, accepted_ids=tuple(accepted.keys()), config=config):
        for block_id, metadata in list(accepted.items()):
            block = _block_by_id(blocks, block_id)
            ignored.append(
                {
                    **_serialize_delete_block(block=block, reason=metadata["reason"], confidence=metadata["confidence"]),
                    "chunk_index": metadata["chunk_index"],
                    "ignored_reason": "global_safety_limit_exceeded",
                }
            )
            accepted.pop(block_id, None)

    # The raw input is the authority for ids, hashes, and report evidence, but the cleaned
    # MVP artifact is still reconstructed from retained blocks instead of raw-span surgery.
    kept_blocks = [block.text for block in blocks if block.block_id not in accepted]
    cleaned_markdown = "\n\n".join(kept_blocks)
    if not cleaned_markdown.strip():
        return raw_markdown, {}, ignored
    return cleaned_markdown, accepted, ignored


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
    if block.char_count > config.max_deleted_block_chars:
        return "block_char_limit_exceeded"
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


def _block_by_id(blocks: Sequence[CleanupBlock], block_id: str) -> CleanupBlock:
    for block in blocks:
        if block.block_id == block_id:
            return block
    raise KeyError(block_id)


def _coerce_int(value: object, *, default: int, minimum: int) -> int:
    try:
        return max(int(value), minimum)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
