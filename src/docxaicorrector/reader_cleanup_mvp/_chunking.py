from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from ._constants import _ALLOWED_ANCHOR_REPAIR_CATEGORIES
from ._models import AnchorRepairChunk, CleanupBlock, CleanupChunk


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
