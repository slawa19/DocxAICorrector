from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from ._constants import (
    _ALLOWED_RECLASSIFY_TARGET_ROLES,
    _DOCX_IMAGE_PLACEHOLDER_PATTERN,
    _DUPLICATE_FRAGMENT_MAX_NEARBY_BLOCK_DISTANCE,
    _DUPLICATE_FRAGMENT_MIN_NON_WHITESPACE_CHARS,
    _GENERIC_RUNNING_HEADER_TOKENS,
    _HEADER_CONNECTOR_WORDS,
    _INLINE_NOISE_REASON_GUIDANCE,
    _NUMERIC_UPPERCASE_MAX_TOKENS_WITHOUT_GENERIC_HEADER,
    _NUMERIC_UPPERCASE_RUNNING_HEADER_PATTERN,
    _RUNNING_HEADER_TRAILING_PUNCTUATION,
    _SAFE_INLINE_NOISE_PATTERN,
)
from ._detectors import _find_isolated_semantic_heading_numeric_prefix
from ._models import CleanupBlock, CleanupOperation, ReaderCleanupConfig
from ._utils import _block_by_id, _normalize_block_text


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
    from .service import _has_generic_caption_marker  # local import breaks _validate<->service load cycle

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
