from __future__ import annotations

import re
from collections.abc import Sequence

from ._constants import _ALLOWED_OPERATIONS
from ._models import CleanupBlock, ReaderCleanupConfig


def _allowed_operations_for_config(config: ReaderCleanupConfig) -> set[str]:
    return set(config.allowed_operations) if config.allowed_operations else set(_ALLOWED_OPERATIONS)


def _build_operation_selection_targets(*, blocks: Sequence[CleanupBlock]) -> list[dict[str, object]]:
    targets: list[dict[str, object]] = []
    for index, block in enumerate(blocks):
        duplicate_target = _build_duplicate_semantic_heading_target(block=block)
        if duplicate_target is not None:
            targets.append(duplicate_target)
        isolated_numeric_heading_target = _build_isolated_semantic_heading_numeric_prefix_target(block=block)
        if isolated_numeric_heading_target is not None:
            targets.append(isolated_numeric_heading_target)
        else:
            semantic_title_target = _build_semantic_page_title_deletion_risk_target(block=block)
            if semantic_title_target is not None:
                targets.append(semantic_title_target)
        next_block = blocks[index + 1] if index + 1 < len(blocks) else None
        heading_fused_target = _build_heading_fused_with_body_target(block=block, next_block=next_block)
        if heading_fused_target is not None:
            targets.append(heading_fused_target)
        targets.extend(_build_side_heading_island_targets(block=block))
    return targets[:20]


def _build_heading_fused_with_body_target(
    *,
    block: CleanupBlock,
    next_block: CleanupBlock | None,
) -> dict[str, object] | None:
    single_block_candidate = _find_heading_fused_with_body_parts(block.text)
    if single_block_candidate is not None:
        return {
            "category": "heading_fused_with_body_candidate",
            "id": block.block_id,
            "text_hash": block.text_hash,
            "preferred_operation": "normalize_heading_boundary",
            "reason_hint": "heading_fused_with_body",
            "heading_substring": single_block_candidate["heading_substring"],
            "body_substring": single_block_candidate["body_substring"],
            "expected_after_preview": single_block_candidate["expected_after_preview"],
            "forbidden_operations": ["remove_inline_noise", "delete_block"],
            "safety_note": "This is a semantic heading/body boundary, not noise. Preserve the full heading and full body text exactly; skip if exact substrings do not match.",
        }

    if next_block is None:
        return None
    wrapped_candidate = _find_wrapped_heading_fused_with_body_parts(block=block, next_block=next_block)
    if wrapped_candidate is None:
        return None
    return {
        "category": "heading_fused_with_body_candidate",
        "id": block.block_id,
        "text_hash": block.text_hash,
        "preferred_operation_chain": ["join_fragmented_paragraph", "normalize_heading_boundary"],
        "reason_hint": "heading_fused_with_body",
        "next_id": next_block.block_id,
        "next_text_hash": next_block.text_hash,
        "heading_substring": wrapped_candidate["heading_substring"],
        "body_substring": wrapped_candidate["body_substring"],
        "expected_after_preview": wrapped_candidate["expected_after_preview"],
        "forbidden_operations": ["remove_inline_noise", "delete_block"],
        "safety_note": "The heading wraps into the adjacent block. Join the exact adjacent block first, then normalize the heading/body boundary; preserve all semantic text.",
    }


def _find_wrapped_heading_fused_with_body_parts(
    *,
    block: CleanupBlock,
    next_block: CleanupBlock,
) -> dict[str, str] | None:
    current_heading = block.text.strip()
    if not current_heading or "\n" in current_heading:
        return None
    if not _looks_like_fused_heading_prefix(current_heading, min_words=2):
        return None
    next_candidate = _find_heading_fused_with_body_parts(next_block.text, min_heading_words=1)
    if next_candidate is None:
        return None
    heading = f"{current_heading} {next_candidate['heading_substring']}".strip()
    if len(heading) > 180:
        return None
    body = next_candidate["body_substring"]
    return {
        "heading_substring": heading,
        "body_substring": body,
        "expected_after_preview": f"{heading}\n\n{body}",
    }


def _find_heading_fused_with_body_parts(text: str, *, min_heading_words: int = 2) -> dict[str, str] | None:
    value = str(text or "").strip()
    if not value or "\n" in value or len(value) < 32:
        return None
    tokens = list(re.finditer(r"[A-Za-zА-Яа-яЁё]{1,}", value))
    if len(tokens) < min_heading_words + 2:
        return None
    max_heading_tokens = min(16, len(tokens) - 1)
    for split_index in range(min_heading_words, max_heading_tokens + 1):
        body_token = tokens[split_index]
        body_word = body_token.group(0)
        if body_word.upper() == body_word:
            continue
        heading = value[: body_token.start()].strip()
        body = value[body_token.start() :].strip()
        if not _looks_like_fused_heading_prefix(heading, min_words=min_heading_words):
            continue
        if not _looks_like_heading_body_remainder(body):
            continue
        return {
            "heading_substring": heading,
            "body_substring": body,
            "expected_after_preview": f"{heading}\n\n{body}",
        }
    return None


def _looks_like_fused_heading_prefix(text: str, *, min_words: int) -> bool:
    from .service import _semantic_word_tokens  # local import breaks _detectors<->service load cycle

    value = str(text or "").strip()
    if not value or len(value) > 180:
        return False
    if re.match(r"^(?:[-*]|\d+\.)\s+", value):
        return False
    words = _semantic_word_tokens(value)
    if len(words) < min_words or len(words) > 16:
        return False
    if any(word.isdigit() for word in words):
        return False
    uppercase_words = [word for word in words if word.upper() == word]
    return len(uppercase_words) == len(words)


def _looks_like_heading_body_remainder(text: str) -> bool:
    from .service import _semantic_word_tokens  # local import breaks _detectors<->service load cycle

    value = str(text or "").strip()
    if len(value) < 12 or value.startswith(("-", "—", "–", "•")):
        return False
    words = _semantic_word_tokens(value)
    if len(words) < 2:
        return False
    return any(any(char.islower() for char in word) for word in words)


def _build_isolated_semantic_heading_numeric_prefix_target(*, block: CleanupBlock) -> dict[str, object] | None:
    candidate = _find_isolated_semantic_heading_numeric_prefix(block.text)
    if candidate is None or block.is_toc_like:
        return None
    numeric_prefix = candidate["numeric_prefix"]
    heading = candidate["semantic_heading_must_remain"]
    return {
        "category": "isolated_semantic_heading_numeric_prefix",
        "id": block.block_id,
        "text_hash": block.text_hash,
        "preferred_operation": "remove_inline_noise",
        "reason_hint": "page_number",
        "forbidden_operation": "full-heading remove_inline_noise",
        "numeric_prefix": numeric_prefix,
        "semantic_heading_must_remain": heading,
        "expected_after_preview": candidate["expected_after_preview"],
        "safety_note": "Remove only the exact numeric prefix if it is still present once; never remove the semantic heading text.",
    }


def _find_isolated_semantic_heading_numeric_prefix(text: str) -> dict[str, str] | None:
    value = str(text or "").strip()
    if not value or "\n" in value:
        return None
    match = re.match(
        r"^(?P<markdown_prefix>#{1,6}\s*)?(?P<number>\d{1,4})(?P<space>\s+)(?P<heading>.+?)\s*$",
        value,
    )
    if match is None:
        return None
    markdown_prefix = match.group("markdown_prefix") or ""
    numeric_prefix = f"{match.group('number')}{match.group('space')}"
    heading = match.group("heading").strip()
    if not _looks_like_isolated_semantic_heading_text(heading):
        return None
    return {
        "numeric_prefix": numeric_prefix,
        "semantic_heading_must_remain": heading,
        "expected_after_preview": f"{markdown_prefix}{heading}",
    }


def _looks_like_isolated_semantic_heading_text(text: str) -> bool:
    from .service import _semantic_word_tokens  # local import breaks _detectors<->service load cycle

    value = str(text or "").strip()
    if not value or len(value) > 120:
        return False
    if re.match(r"^(?:[-*]|\d+\.)\s+", value):
        return False
    words = _semantic_word_tokens(value)
    if len(words) > 12:
        return False
    if any(word.isdigit() for word in words):
        return False
    if len(words) == 1:
        return len(words[0]) >= 4 and words[0].upper() == words[0]
    uppercase_words = [word for word in words if word.upper() == word]
    if len(uppercase_words) == len(words):
        return True
    return len(words) <= 6 and sum(1 for word in words if word[0].isupper()) >= 2


def _build_duplicate_semantic_heading_target(*, block: CleanupBlock) -> dict[str, object] | None:
    duplicate = _find_adjacent_duplicate_phrase(block.text)
    if duplicate is None:
        return None
    from .service import _inline_noise_removed_text  # local import breaks _detectors<->service load cycle

    noise_substring = duplicate["noise_substring"]
    return {
        "category": "duplicate_semantic_heading_text",
        "id": block.block_id,
        "text_hash": block.text_hash,
        "operation_hint": "remove_inline_noise",
        "reason_hint": "duplicate_fragment",
        "noise_substring": noise_substring,
        "expected_after_preview": _inline_noise_removed_text(current_text=block.text, noise=noise_substring),
        "safety_note": "Apply only if this exact adjacent repeated phrase is still present once in the editable block.",
    }


def _find_adjacent_duplicate_phrase(text: str) -> dict[str, str] | None:
    tokens = list(re.finditer(r"[A-Za-zА-Яа-яЁё]{2,}", text or ""))
    if len(tokens) < 4:
        return None
    for phrase_len in range(8, 1, -1):
        if len(tokens) < phrase_len * 2:
            continue
        for start in range(0, len(tokens) - (phrase_len * 2) + 1):
            first = tokens[start : start + phrase_len]
            second = tokens[start + phrase_len : start + (phrase_len * 2)]
            first_words = [match.group(0).lower() for match in first]
            second_words = [match.group(0).lower() for match in second]
            if first_words != second_words:
                continue
            noise_start = second[0].start()
            noise_end = second[-1].end()
            while noise_end < len(text) and text[noise_end].isspace():
                noise_end += 1
            return {"noise_substring": text[noise_start:noise_end]}
    return None


def _build_semantic_page_title_deletion_risk_target(*, block: CleanupBlock) -> dict[str, object] | None:
    if block.is_toc_like or block.char_count < 20:
        return None
    candidate = _find_trailing_page_like_semantic_title(block.text)
    if candidate is None:
        return None
    return {
        "category": "semantic_page_title_deletion_risk",
        "id": block.block_id,
        "text_hash": block.text_hash,
        "semantic_title_candidate": candidate["semantic_title_candidate"],
        "page_like_number": candidate["page_like_number"],
        "numeric_prefix": candidate["numeric_prefix"],
        "forbidden_operation": "remove_inline_noise",
        "operation_hint": "preserve_title_with_exact_structural_operation_or_skip",
        "after_structural_split_followup_operation": "remove_inline_noise",
        "same_pass_followup_supported": True,
        "followup_targets_same_original_block_id": True,
        "after_structural_split_noise_substring": candidate["numeric_prefix"],
        "semantic_heading_must_remain_after_followup": candidate["semantic_title_candidate"],
        "after_structural_split_expected_after_preview": candidate["semantic_title_candidate"],
        "safety_note": "A page-like number adjacent to a semantic section title is not enough to classify the title as noise. Do not delete the title with remove_inline_noise; remove only exact non-semantic page residue if safe, or skip with a warning.",
    }


def _find_trailing_page_like_semantic_title(text: str) -> dict[str, str] | None:
    from .service import (  # local import breaks _detectors<->service load cycle
        _looks_like_numeric_uppercase_running_header_noise,
        _semantic_word_tokens,
    )

    value = str(text or "").strip()
    if not value:
        return None
    match = re.search(
        r"(?P<candidate>(?P<number>\d{1,4})\s+"
        r"(?P<title>[A-ZА-ЯЁ][A-ZА-ЯЁ0-9«»\"'(),:;!?-]*"
        r"(?:\s+[A-ZА-ЯЁ][A-ZА-ЯЁ0-9«»\"'(),:;!?-]*){1,9}"
        r"[.!?…]?))\s*$",
        value,
    )
    if match is None:
        return None
    candidate = match.group("candidate").strip()
    title = match.group("title").strip()
    words = _semantic_word_tokens(title)
    if len(words) < 2 or len(words) > 10:
        return None
    if not all(word.upper() == word for word in words):
        return None
    if match.start("candidate") == 0 and _looks_like_numeric_uppercase_running_header_noise(
        normalized_noise=candidate,
        current_text=value,
    ):
        return None
    return {
        "page_like_number": match.group("number"),
        "numeric_prefix": f"{match.group('number')} ",
        "semantic_title_candidate": title,
    }


def _build_side_heading_island_targets(*, block: CleanupBlock) -> list[dict[str, object]]:
    if block.is_heading or block.is_toc_like or block.char_count < 40:
        return []
    targets: list[dict[str, object]] = []
    tokens = list(re.finditer(r"[A-Za-zА-Яа-яЁё]{2,}", block.text))
    if len(tokens) < 6:
        return []
    for phrase_len in range(3, 6):
        for start in range(1, len(tokens) - phrase_len):
            phrase_tokens = tokens[start : start + phrase_len]
            before_text = block.text[: phrase_tokens[0].start()]
            after_text = block.text[phrase_tokens[-1].end() :]
            if not _has_side_heading_left_context(before_text):
                continue
            if not _has_side_heading_right_context(after_text):
                continue
            phrase = block.text[phrase_tokens[0].start() : phrase_tokens[-1].end()]
            if not _looks_like_side_heading_phrase(phrase):
                continue
            targets.append(
                {
                    "category": "side_heading_island_candidate",
                    "id": block.block_id,
                    "text_hash": block.text_hash,
                    "heading_candidate": phrase,
                    "operation_hint": "preserve_heading_text_with_split_block_or_normalize_heading_boundary",
                    "preferred_operation_order": ["split_block", "normalize_heading_boundary"],
                    "reattach_operation_hint": "extract_side_heading_and_reattach_body",
                    "forbidden_default_operation": "remove_inline_noise",
                    "stub_continuation_risk": "If this heading interrupts one sentence, do not leave a pre-heading stub or orphan post-heading continuation; use exact reattach operation or skip.",
                    "reattach_expected_after_preview_shape": "heading_substring + blank line + pre_body_stub + space + post_body_continuation; no labels and no body-first preview.",
                    "safety_note": "Semantic heading islands are not noise. Do not delete with remove_inline_noise; preserve all semantic text with exact extract_side_heading_and_reattach_body, split_block, or normalize_heading_boundary, or skip if boundaries are unclear.",
                }
            )
            if len(targets) >= 3:
                return targets
    return targets


def _has_side_heading_left_context(text: str) -> bool:
    before = str(text or "").rstrip()
    if not before:
        return False
    if before[-1] in ".!?;:…":
        return False
    return re.search(r"[a-zа-яё][,\s\"'«»“”„-]*$", before) is not None


def _has_side_heading_right_context(text: str) -> bool:
    after = str(text or "").lstrip()
    return re.match(r"[a-zа-яё]", after) is not None


def _looks_like_side_heading_phrase(phrase: str) -> bool:
    from .service import _semantic_word_tokens  # local import breaks _detectors<->service load cycle

    if re.search(r"\b(?:and|for|from|in|of|or|the|to|в|во|для|и|или|к|на|о|от|по|с|со|у)\b", phrase, re.IGNORECASE):
        return False
    words = _semantic_word_tokens(phrase)
    if len(words) < 3 or len(words) > 5:
        return False
    if any(word.isdigit() for word in words):
        return False
    if not words[0][0].isupper():
        return False
    uppercase_count = sum(1 for word in words if word[0].isupper())
    return uppercase_count == 1
