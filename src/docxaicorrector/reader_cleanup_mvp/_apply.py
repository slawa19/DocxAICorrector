from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from ._constants import (
    _ALLOWED_RECLASSIFY_TARGET_ROLES,
    _DOCX_IMAGE_PLACEHOLDER_PATTERN,
    _RECLASSIFY_MARKDOWN_HEADING_PREFIX,
)
from ._detectors import (
    _allowed_operations_for_config,
    _has_side_heading_left_context,
    _has_side_heading_right_context,
    _looks_like_side_heading_phrase,
)
from ._models import (
    CleanupBlock,
    CleanupOperation,
    ReaderCleanupConfig,
    ReannotationDecision,
)
from ._utils import (
    _block_by_id,
    _normalize_block_text,
    _serialize_cleanup_operation,
    _serialize_delete_block,
)
from ._validate import (
    _build_protected_block_ids,
    _canonicalize_cleanup_operation_sequence,
    _is_exact_isolated_semantic_heading_numeric_prefix_cleanup,
    _is_safe_inline_noise_substring,
    _max_allowed_reclassify_operations,
    _validate_duplicate_fragment_delete,
    _validate_operation,
    _validate_same_block_operation_sequence,
    _violates_global_safety,
)


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
    from .service import _inline_noise_removed_text  # local import breaks _apply<->service load cycle

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
