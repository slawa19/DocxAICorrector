from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from ._constants import (
    _BLANK_PAGE_PATTERN,
    _DOCX_IMAGE_ANCHOR_KIND,
    _DOCX_IMAGE_PLACEHOLDER_PATTERN,
    _EXTRACTION_ARTIFACT_PATTERN,
    _FOOTNOTE_BODY_PATTERN,
    _ORPHAN_FOOTNOTE_PATTERN,
    _PAGE_NUMBER_PATTERN,
    _TOC_ENTRY_BOUNDARY_TRIM_CHARS,
    _TOC_INDEX_PAGE_REFERENCE_PATTERN,
    _TOC_LEADER_ENTRY_PATTERN,
    _TOC_MIN_CONTENTS_ENTRY_TOKENS,
    _TOC_MIN_CONTENTS_ENTRY_TOKENS_WITH_ROMAN,
    _TOC_MIN_PAGE_REFERENCE_TOKEN_RATIO,
    _TOC_MIN_PAGE_REFERENCE_TOKENS,
    _TOC_MIN_ROMAN_PAGE_NUMBER_CHARS,
    _TOC_PAGE_RANGE_PATTERN,
    _TOC_PAGE_REFERENCE_RUN_PATTERN,
    _TOC_PAGE_REFERENCE_TOKEN_PATTERN,
    _TOC_ROMAN_PAGE_NUMBER_PATTERN,
)
from ._models import CleanupBlock, CleanupOperation


def _is_at_entry_boundary(words: Sequence[str], index: int) -> bool:
    """Whether the word at ``index`` ends a contents entry.

    A page number in a table of contents ends its entry, so the word after it opens the
    next one — the next entry's number, a capitalised title, or nothing at all. In prose
    the sentence simply carries on in lowercase.
    """
    if index == len(words) - 1:
        return True
    following = words[index + 1].strip(_TOC_ENTRY_BOUNDARY_TRIM_CHARS)
    return following.isdigit() or (following.isalpha() and following[:1].isupper())


def _is_roman_page_number(word: str) -> bool:
    """Whether a word has the FORM of a lowercase front-matter page number.

    Form only, never vocabulary: a numeral of at least two characters, spelled from the
    symbols a book's front matter can reach (i, v, x, l — below one hundred). Whether the
    token is ALSO a word in some language is not asked here; position decides that, in
    ``_is_contents_entry_run``. See ``_constants`` for why each half is what it is.
    """
    if len(word) < _TOC_MIN_ROMAN_PAGE_NUMBER_CHARS:
        return False
    return bool(_TOC_ROMAN_PAGE_NUMBER_PATTERN.fullmatch(word))


def _is_contents_entry_run(stripped: str) -> bool:
    """A run of contents entries: page numbers, every one of them at an entry boundary.

    Entry boundaries are what tell "1 Крах денег: конкурентное общество 11 2 Миф о деньгах
    ... 23" from "In 1990 value was 5 and in 2000 rose to 10" even though the second is the
    denser of the two. Arabic page numbers carry the run: at least one is required, and any
    that does not end its entry disqualifies the block. A roman page number joins the count
    only where an arabic one would be counted — at an entry boundary — which is what lets
    the line crossing the front-matter pagination seam ("Предисловие ix Введение: ... 1") in
    on two references instead of three.
    """
    words = stripped.split()
    arabic_positions = [index for index, word in enumerate(words) if word.isdigit() and len(word) <= 4]
    if not arabic_positions:
        return False
    if not all(_is_at_entry_boundary(words, index) for index in arabic_positions):
        return False
    roman_count = sum(
        1
        for index, word in enumerate(words)
        if _is_roman_page_number(word) and _is_at_entry_boundary(words, index)
    )
    minimum = _TOC_MIN_CONTENTS_ENTRY_TOKENS_WITH_ROMAN if roman_count else _TOC_MIN_CONTENTS_ENTRY_TOKENS
    return len(arabic_positions) + roman_count >= minimum


def _is_toc_like_text(stripped: str) -> bool:
    """Whether a block should be passed through as contents/index material.

    ``toc_like`` grants immunity from every cleanup operation, so the question is not
    "does this contain a number?" but "is this number in a position only a contents or
    index line puts it in?". Four shapes answer yes: a dotted leader terminated by a page
    number; a block that is nothing but page numbers and separators; an index run, whose
    page references are introduced by a comma or semicolon (or written as ranges) and are
    dense against the word count; and a contents run of page numbers, arabic or roman,
    every one of them at an entry boundary. See ``_constants`` for what each spelling is
    paying for.

    A paragraph of prose that merely ends in a number matches none of them; that used to
    be sufficient on its own, and it is the reason the pass did nothing on those blocks.
    Telling contents from index from bibliography is NOT attempted: all of them are
    pass-through material, so a mislabel among them changes nothing.
    """
    text = stripped.strip()
    if not text:
        return False
    if _TOC_LEADER_ENTRY_PATTERN.search(text):
        return True
    if (
        _TOC_PAGE_REFERENCE_RUN_PATTERN.fullmatch(text)
        and len(_TOC_PAGE_REFERENCE_TOKEN_PATTERN.findall(text)) >= 2
    ):
        return True
    word_count = len(text.split())
    page_reference_count = len(_TOC_INDEX_PAGE_REFERENCE_PATTERN.findall(text)) + len(
        _TOC_PAGE_RANGE_PATTERN.findall(text)
    )
    if (
        page_reference_count >= _TOC_MIN_PAGE_REFERENCE_TOKENS
        and page_reference_count / word_count >= _TOC_MIN_PAGE_REFERENCE_TOKEN_RATIO
    ):
        return True
    return _is_contents_entry_run(text)


def _is_docx_image_anchor_text(stripped: str) -> bool:
    """True when the block is nothing but one or more ``[[DOCX_IMAGE_*]]`` anchors.

    Spec 052 item 4: these must never be classified ``extraction_artifact``, which is an
    allowed ``delete_block`` reason. Blocks that mix an anchor with real text (a caption,
    say) are ordinary paragraphs and keep their previous kind.
    """
    if not _DOCX_IMAGE_PLACEHOLDER_PATTERN.search(stripped):
        return False
    return not _DOCX_IMAGE_PLACEHOLDER_PATTERN.sub("", stripped).strip()


def _detect_block_kind(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "empty"
    first_line = stripped.splitlines()[0].strip()
    if first_line.startswith("#"):
        return "heading"
    if _is_docx_image_anchor_text(stripped):
        return _DOCX_IMAGE_ANCHOR_KIND
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
    if _is_toc_like_text(stripped):
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
