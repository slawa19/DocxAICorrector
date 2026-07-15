"""Text-similarity / drift / markdown-detector helpers from ``validation/structural.py``
(spec 034, Step 2, Cluster M).

Pure leaf helpers. Depend only on stdlib / typing and on lower-layer library functions
(``build_document_text``, ``has_toc_body_concat_markdown``) -- never on the ``structural``
orchestration module -- so no import cycle is introduced. Bodies are byte-identical to their
former in-module definitions; ``structural`` re-exports them so the qualified names keep
resolving.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
import re
from typing import Any, cast

from docxaicorrector.document.extraction import build_document_text
from docxaicorrector.pipeline.output_validation import (
    has_toc_body_concat_markdown as _shared_has_toc_body_concat_markdown,
)


def _calculate_text_similarity(source_paragraphs: Sequence[object], output_paragraphs: Sequence[object]) -> float:
    source_text = _normalize_text(build_document_text(cast(list[Any], list(source_paragraphs))))
    output_text = _normalize_text(build_document_text(cast(list[Any], list(output_paragraphs))))
    if not source_text and not output_text:
        return 1.0
    return round(SequenceMatcher(None, source_text, output_text).ratio(), 4)


def _calculate_heading_level_drift(source_paragraphs: Sequence[object], output_paragraphs: Sequence[object]) -> int:
    output_levels: dict[str, int] = {}
    for paragraph in output_paragraphs:
        if getattr(paragraph, "role", None) != "heading":
            continue
        normalized = _normalize_text(str(getattr(paragraph, "text", "")))
        if not normalized:
            continue
        output_levels[normalized] = int(getattr(paragraph, "heading_level", 0) or 0)

    max_drift = 0
    for paragraph in source_paragraphs:
        if getattr(paragraph, "role", None) != "heading":
            continue
        normalized = _normalize_text(str(getattr(paragraph, "text", "")))
        if not normalized or normalized not in output_levels:
            continue
        source_level = int(getattr(paragraph, "heading_level", 0) or 0)
        max_drift = max(max_drift, abs(source_level - output_levels[normalized]))
    return max_drift


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    normalized = re.sub(r"^#{1,6}\s+", "", normalized)
    return normalized


def _is_heading_only_markdown(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("#") and len(line.split()) >= 2 for line in lines)


def _has_toc_structural_roles(paragraphs: Sequence[object]) -> bool:
    for paragraph in paragraphs:
        structural_role = str(getattr(paragraph, "structural_role", "") or "").strip().lower()
        if structural_role in {"toc_header", "toc_entry"}:
            return True
    return False


def _count_bullet_headings(markdown_text: str) -> int:
    return sum(
        1
        for line in markdown_text.splitlines()
        if re.match(r"^#{1,6}\s*[●•\-*]\s*$", line.strip())
    )


def _has_toc_body_concat_markdown(markdown_text: str) -> bool:
    return _shared_has_toc_body_concat_markdown(markdown_text)


def _relation_count(relation_report: object, key: str) -> int:
    relation_counts = getattr(relation_report, "relation_counts", {}) or {}
    if not isinstance(relation_counts, Mapping):
        return 0
    value = relation_counts.get(key, 0)
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return 0
