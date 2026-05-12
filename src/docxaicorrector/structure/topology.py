from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from typing import Any

from docxaicorrector.core.models import (
    DocumentMap,
    DocumentTopologyOperation,
    DocumentTopologyProjection,
    ParagraphUnit,
    StructuralUnit,
)
from docxaicorrector.structure.document_map import DOCUMENT_MAP_SPLIT_HINT_SCHEMA_VERSION


TOPOLOGY_PROJECTION_SCHEMA_VERSION = 1
VALID_TOPOLOGY_UNIT_TYPES = frozenset({"chapter_heading", "section_heading", "toc_entry", "page_artifact", "body", "unknown"})
VALID_TOPOLOGY_AUTHORITIES = frozenset(
    {
        "document_map_outline",
        "document_map_toc",
        "document_map_review_zone",
        "document_map_anchor",
        "document_map_split_hint",
    }
)
VALID_TOPOLOGY_EVIDENCE = frozenset(
    {
        "outline_entry",
        "toc_entry",
        "split_hint",
        "adjacent_short_heading_fragments",
        "local_heading_neighborhood",
        "bounded_toc_region",
        "page_artifact_phrase",
        "one_to_one_toc_entry_match",
    }
)
_HEADING_CONTINUATION_WINDOW = 3
_TOPOLOGY_TEXT_PREVIEW_CHARS = 120
_WHITESPACE_PATTERN = re.compile(r"\s+")
_PUNCT_TRANSLATION = str.maketrans({char: " " for char in ",;:!?()[]{}\"'`"})


def build_document_topology_projection_cache_key(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    *,
    app_config: Mapping[str, Any],
    document_map_cache_key: str | None = None,
) -> str:
    preview_chars = int(app_config.get("structure_recovery_document_map_preview_chars", _TOPOLOGY_TEXT_PREVIEW_CHARS) or _TOPOLOGY_TEXT_PREVIEW_CHARS)
    payload = {
        "stage": "document_topology_projection_v1",
        "document_map_cache_key": str(document_map_cache_key or ""),
        "topology_projection_schema_version": TOPOLOGY_PROJECTION_SCHEMA_VERSION,
        "topology_hint_schema_version": DOCUMENT_MAP_SPLIT_HINT_SCHEMA_VERSION,
        "binding_splits_enabled": bool(app_config.get("structure_recovery_topology_projection_binding_splits_enabled", False)),
        "paragraph_fingerprint": [
            {
                "logical_index": int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1))),
                "text_preview": str(getattr(paragraph, "text", "") or "")[:preview_chars],
            }
            for paragraph in paragraphs
        ],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def apply_document_map_topology(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    *,
    app_config: Mapping[str, Any],
    document_map_cache_key: str | None = None,
) -> DocumentTopologyProjection:
    cache_key = build_document_topology_projection_cache_key(
        paragraphs,
        document_map,
        app_config=app_config,
        document_map_cache_key=document_map_cache_key,
    )
    projection = DocumentTopologyProjection(
        cache_key=cache_key,
        document_map_cache_key=document_map_cache_key,
        topology_projection_schema_version=TOPOLOGY_PROJECTION_SCHEMA_VERSION,
        topology_hint_schema_version=DOCUMENT_MAP_SPLIT_HINT_SCHEMA_VERSION,
    )
    if not paragraphs:
        return projection

    position_by_logical_index = {
        int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1))): position
        for position, paragraph in enumerate(paragraphs)
    }
    projected_units: list[StructuralUnit] = []
    operations: list[DocumentTopologyOperation] = []
    occupied_logical_indexes: set[int] = set()

    for authority, logical_index, heading_level, canonical_text, evidence in _iter_authoritative_heading_targets(document_map):
        if logical_index in occupied_logical_indexes:
            continue
        unit = _build_heading_continuation_unit(
            paragraphs=paragraphs,
            position_by_logical_index=position_by_logical_index,
            logical_index=logical_index,
            heading_level=heading_level,
            canonical_text=canonical_text,
            authority=authority,
            evidence=evidence,
        )
        if unit is None:
            continue
        projected_units.append(unit)
        operations.append(
            DocumentTopologyOperation(
                op="merge_heading_continuation",
                logical_indexes=unit.logical_indexes,
                canonical_text=unit.canonical_text,
                authority=unit.authority,
                confidence=unit.confidence,
                evidence=unit.evidence,
            )
        )
        occupied_logical_indexes.update(unit.logical_indexes)

    return DocumentTopologyProjection(
        cache_key=cache_key,
        document_map_cache_key=document_map_cache_key,
        topology_projection_schema_version=TOPOLOGY_PROJECTION_SCHEMA_VERSION,
        topology_hint_schema_version=DOCUMENT_MAP_SPLIT_HINT_SCHEMA_VERSION,
        operations=tuple(operations),
        projected_units=tuple(projected_units),
    )


def _iter_authoritative_heading_targets(document_map: DocumentMap):
    seen_logical_indexes: set[int] = set()
    for entry in document_map.outline or ():
        if str(entry.confidence or "").strip().lower() != "high":
            continue
        logical_index = int(entry.logical_index)
        seen_logical_indexes.add(logical_index)
        yield (
            "document_map_outline",
            logical_index,
            int(entry.level),
            str(entry.title or "").strip(),
            ("outline_entry", "adjacent_short_heading_fragments"),
        )
    toc_region = document_map.toc_region
    if toc_region is None:
        return
    for entry in toc_region.entries:
        logical_index = entry.candidate_body_logical_index
        if logical_index is None or int(logical_index) in seen_logical_indexes:
            continue
        if str(entry.confidence or "").strip().lower() != "high":
            continue
        yield (
            "document_map_toc",
            int(logical_index),
            max(1, int(entry.target_level)),
            str(entry.title or "").strip(),
            ("toc_entry", "adjacent_short_heading_fragments"),
        )


def _build_heading_continuation_unit(
    *,
    paragraphs: list[ParagraphUnit],
    position_by_logical_index: dict[int, int],
    logical_index: int,
    heading_level: int,
    canonical_text: str,
    authority: str,
    evidence: tuple[str, ...],
) -> StructuralUnit | None:
    start_position = position_by_logical_index.get(int(logical_index))
    normalized_canonical_tokens = _heading_tokens(canonical_text)
    if start_position is None or len(normalized_canonical_tokens) < 2:
        return None

    collected_indexes: list[int] = []
    collected_texts: list[str] = []
    collected_tokens: list[str] = []
    for offset in range(_HEADING_CONTINUATION_WINDOW + 1):
        position = start_position + offset
        if position >= len(paragraphs):
            break
        paragraph = paragraphs[position]
        paragraph_text = str(getattr(paragraph, "text", "") or "").strip()
        paragraph_tokens = _heading_tokens(paragraph_text)
        if not paragraph_tokens:
            break
        if offset > 0 and not _is_heading_continuation_candidate(paragraph, paragraph_text):
            break
        candidate_tokens = [*collected_tokens, *paragraph_tokens]
        if not _token_sequences_compatible(candidate_tokens, normalized_canonical_tokens):
            break
        collected_indexes.append(int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1))))
        collected_texts.append(paragraph_text)
        collected_tokens = candidate_tokens
        if _normalized_heading_tokens(candidate_tokens) == _normalized_heading_tokens(normalized_canonical_tokens):
            break

    if len(collected_indexes) <= 1:
        return None
    if not _token_sequences_compatible(collected_tokens, normalized_canonical_tokens):
        return None

    unit_type = "chapter_heading" if int(heading_level) <= 1 else "section_heading"
    return StructuralUnit(
        unit_type=unit_type,
        logical_indexes=tuple(collected_indexes),
        canonical_text=str(canonical_text or "").strip(),
        role="heading",
        heading_level=int(heading_level),
        confidence="high",
        authority=authority,
        evidence=tuple(evidence),
    )


def _is_heading_continuation_candidate(paragraph: ParagraphUnit, paragraph_text: str) -> bool:
    normalized = _collapse_whitespace(paragraph_text)
    if not normalized:
        return False
    if bool(getattr(paragraph, "is_repeated_across_pages", False)) or bool(getattr(paragraph, "is_likely_page_number", False)):
        return False
    if len(normalized) > 120:
        return False
    words = normalized.split()
    if len(words) > 14:
        return False
    if not any(char.isalpha() for char in normalized):
        return False
    if normalized.endswith("."):
        return False
    return True


def _heading_tokens(text: str) -> list[str]:
    normalized = _collapse_whitespace(str(text or "").strip().translate(_PUNCT_TRANSLATION))
    if not normalized:
        return []
    return [token for token in normalized.casefold().split(" ") if token]


def _normalized_heading_tokens(tokens: list[str]) -> list[str]:
    return _trim_heading_prefix(list(tokens))


def _token_sequences_compatible(candidate_tokens: list[str], canonical_tokens: list[str]) -> bool:
    candidate_variants = (candidate_tokens, _trim_heading_prefix(candidate_tokens))
    canonical_variants = (canonical_tokens, _trim_heading_prefix(canonical_tokens))
    for candidate_variant in candidate_variants:
        if not candidate_variant:
            continue
        for canonical_variant in canonical_variants:
            if _is_token_prefix(candidate_variant, canonical_variant):
                return True
    return False


def _trim_heading_prefix(tokens: list[str]) -> list[str]:
    if len(tokens) >= 2 and tokens[0] in {"chapter", "глава"}:
        return tokens[2:]
    return list(tokens)


def _is_token_prefix(candidate_tokens: list[str], canonical_tokens: list[str]) -> bool:
    if len(candidate_tokens) > len(canonical_tokens):
        return False
    return canonical_tokens[: len(candidate_tokens)] == candidate_tokens


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", str(text or "").strip())