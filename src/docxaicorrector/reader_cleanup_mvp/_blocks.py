from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

from ._constants import _DOCX_IMAGE_PLACEHOLDER_ONLY_PATTERN
from ._models import CleanupBlock
from ._report import _extract_docx_image_placeholder_ids
from ._utils import _detect_block_kind, _normalize_block_text


def build_cleanup_blocks(
    markdown_text: str,
    *,
    block_metadata_by_index: Mapping[int, Mapping[str, object]] | None = None,
) -> list[CleanupBlock]:
    normalized_markdown = str(markdown_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_markdown:
        return []

    raw_blocks = [part.strip("\n") for part in re.split(r"\n\s*\n+", normalized_markdown) if part.strip()]
    blocks: list[CleanupBlock] = []
    for index, raw_block in enumerate(raw_blocks):
        normalized_text = _normalize_block_text(raw_block)
        kind = _detect_block_kind(normalized_text)
        metadata = block_metadata_by_index.get(index) if block_metadata_by_index is not None else None
        paragraph_id = None
        merged_paragraph_ids: tuple[str, ...] = ()
        layout_signals: dict[str, object] = _derive_cleanup_block_layout_signals(
            text=raw_block,
            normalized_text=normalized_text,
            kind=kind,
        )
        if isinstance(metadata, Mapping):
            raw_paragraph_id = metadata.get("paragraph_id")
            if isinstance(raw_paragraph_id, str) and raw_paragraph_id.strip():
                paragraph_id = raw_paragraph_id.strip()
            raw_merged_ids = metadata.get("merged_paragraph_ids")
            if isinstance(raw_merged_ids, Sequence) and not isinstance(raw_merged_ids, (str, bytes, bytearray)):
                merged_paragraph_ids = tuple(str(value).strip() for value in raw_merged_ids if str(value).strip())
            raw_layout_signals = metadata.get("layout_signals")
            if isinstance(raw_layout_signals, Mapping):
                layout_signals.update(_sanitize_layout_signals(raw_layout_signals))
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
                paragraph_id=paragraph_id,
                merged_paragraph_ids=merged_paragraph_ids,
                layout_signals=layout_signals,
            )
        )
    return blocks


def _derive_cleanup_block_layout_signals(*, text: str, normalized_text: str, kind: str) -> dict[str, object]:
    stripped = normalized_text.strip()
    line_count = len([line for line in str(text or "").splitlines() if line.strip()])
    visible_char_count = len(stripped)
    word_count = len(re.findall(r"\S+", stripped))
    digit_only = bool(re.fullmatch(r"\[?\d{1,3}\]?|\(\d{1,3}\)", stripped))
    image_placeholder_ids = _extract_docx_image_placeholder_ids(stripped)
    return {
        "standalone_short_line": line_count <= 1 and 0 < visible_char_count <= 90,
        "line_count": line_count,
        "word_count": word_count,
        "looks_like_superscript_marker": digit_only,
        "is_docx_image_anchor": bool(image_placeholder_ids) and bool(_DOCX_IMAGE_PLACEHOLDER_ONLY_PATTERN.fullmatch(stripped)),
        "docx_image_ids": image_placeholder_ids,
        "detected_kind": kind,
    }


def _sanitize_layout_signals(raw_signals: Mapping[str, object]) -> dict[str, object]:
    allowed_keys = {
        "font_size",
        "body_font_size",
        "font_size_delta_from_body",
        "font_size_ratio_to_body",
        "standalone_short_line",
        "indent",
        "left_indent",
        "first_line_indent",
        "centered",
        "alignment",
        "superscript",
        "looks_like_superscript_marker",
        "line_count",
        "word_count",
        "is_docx_image_anchor",
        "docx_image_ids",
        "detected_kind",
    }
    sanitized: dict[str, object] = {}
    for key, value in raw_signals.items():
        normalized_key = str(key or "").strip()
        if normalized_key not in allowed_keys:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[normalized_key] = value
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            sanitized[normalized_key] = [str(item) for item in value]
    return sanitized


def _select_cleanup_blocks(*, blocks: Sequence[CleanupBlock], keep_toc: bool) -> tuple[list[CleanupBlock], list[str]]:
    if keep_toc:
        return list(blocks), []

    filtered_blocks = [block for block in blocks if not block.is_toc_like]
    ignored_toc_count = len(blocks) - len(filtered_blocks)
    warnings: list[str] = []
    if ignored_toc_count > 0:
        warnings.append(f"reader_cleanup_toc_blocks_ignored:{ignored_toc_count}")
    return filtered_blocks, warnings
