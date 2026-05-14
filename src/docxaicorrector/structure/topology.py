from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from docxaicorrector.core.models import (
    DocumentMap,
    DocumentMapSplitHint,
    DocumentTopologyOperation,
    DocumentTopologyProjection,
    ParagraphUnit,
    StructuralUnit,
)
from docxaicorrector.structure.layout_signals import LAYOUT_SIGNALS_SCHEMA_VERSION, LayoutSignals
from docxaicorrector.structure.document_map import DOCUMENT_MAP_OUTLINE_MEMBERSHIP_SCHEMA_VERSION, DOCUMENT_MAP_SPLIT_HINT_SCHEMA_VERSION


TOPOLOGY_PROJECTION_SCHEMA_VERSION = 2
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
        "font_cluster_match",
        "page_break_boundary",
        "body_font_baseline_outlier",
    }
)
VALID_TOPOLOGY_OPERATIONS = frozenset(
    {
        "merge_heading_continuation",
        "split_page_artifact_from_heading",
        "split_compound_toc_entries",
        "candidate_page_artifact_split",
    }
)
_HEADING_CONTINUATION_WINDOW = 3
_HEADING_PRELUDE_WINDOW = 1
_TOPOLOGY_TEXT_PREVIEW_CHARS = 120
_WHITESPACE_PATTERN = re.compile(r"\s+")
_PUNCT_TRANSLATION = str.maketrans({char: " " for char in ",;:!?()[]{}\"'`"})
_ROMAN_NUMERAL_TOKENS = frozenset({"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx"})
_ENGLISH_NUMBER_TOKENS = frozenset(
    {
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
    }
)
_BINDING_SPLIT_HEADING_NEIGHBORHOOD = 1
_PAGE_FURNITURE_PHRASES = (
    "this page intentionally left blank",
    "эта страница намеренно оставлена пустой",
    "page intentionally left blank",
    "intentionally blank",
    "intentionally left blank",
)


@dataclass(frozen=True)
class _AuthoritativeHeadingTarget:
    authority: str
    logical_index: int
    heading_level: int
    canonical_text: str
    evidence: tuple[str, ...]
    member_logical_indexes: tuple[int, ...] = ()


def build_document_topology_projection_cache_key(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    *,
    app_config: Mapping[str, Any],
    document_map_cache_key: str | None = None,
    layout_signals: LayoutSignals | None = None,
) -> str:
    preview_chars = int(app_config.get("structure_recovery_document_map_preview_chars", _TOPOLOGY_TEXT_PREVIEW_CHARS) or _TOPOLOGY_TEXT_PREVIEW_CHARS)
    payload = {
        "stage": "document_topology_projection_v1",
        "document_map_cache_key": str(document_map_cache_key or ""),
        "topology_projection_schema_version": TOPOLOGY_PROJECTION_SCHEMA_VERSION,
        "topology_hint_schema_version": DOCUMENT_MAP_SPLIT_HINT_SCHEMA_VERSION,
        "outline_membership_schema_version": DOCUMENT_MAP_OUTLINE_MEMBERSHIP_SCHEMA_VERSION,
        "binding_splits_enabled": bool(app_config.get("structure_recovery_topology_projection_binding_splits_enabled", False)),
        "outline_fingerprint": [
            {
                "logical_index": int(entry.logical_index),
                "title": str(entry.title or "").strip(),
                "member_logical_indexes": [int(index) for index in getattr(entry, "member_logical_indexes", ()) or ()],
            }
            for entry in document_map.outline or ()
        ],
        "paragraph_fingerprint": [
            {
                "logical_index": int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1))),
                "text_preview": str(getattr(paragraph, "text", "") or "")[:preview_chars],
            }
            for paragraph in paragraphs
        ],
    }
    if layout_signals is not None:
        payload["layout_signals_schema_version"] = int(getattr(layout_signals, "schema_version", LAYOUT_SIGNALS_SCHEMA_VERSION) or LAYOUT_SIGNALS_SCHEMA_VERSION)
        payload["layout_signals_fingerprint"] = _build_layout_signals_fingerprint(layout_signals)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def apply_document_map_topology(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    *,
    app_config: Mapping[str, Any],
    document_map_cache_key: str | None = None,
    layout_signals: LayoutSignals | None = None,
) -> DocumentTopologyProjection:
    cache_key = build_document_topology_projection_cache_key(
        paragraphs,
        document_map,
        app_config=app_config,
        document_map_cache_key=document_map_cache_key,
        layout_signals=layout_signals,
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
    authoritative_heading_targets = tuple(_iter_authoritative_heading_targets(document_map))
    projected_units: list[StructuralUnit] = []
    operations: list[DocumentTopologyOperation] = []
    occupied_logical_indexes: set[int] = set()

    for target in authoritative_heading_targets:
        if int(target.logical_index) in occupied_logical_indexes:
            continue
        unit = _build_heading_continuation_unit(
            paragraphs=paragraphs,
            position_by_logical_index=position_by_logical_index,
            target=target,
            layout_signals=layout_signals,
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

    if bool(app_config.get("structure_recovery_topology_projection_binding_splits_enabled", False)):
        split_operations, split_units = _build_binding_split_units(
            paragraphs=paragraphs,
            position_by_logical_index=position_by_logical_index,
            document_map=document_map,
            authoritative_heading_targets=authoritative_heading_targets,
        )
        operations.extend(split_operations)
        projected_units.extend(split_units)

    if layout_signals is not None:
        operations.extend(
            _build_candidate_page_artifact_operations(
                paragraphs=paragraphs,
                authoritative_heading_targets=authoritative_heading_targets,
                layout_signals=layout_signals,
            )
        )

    _validate_projection_values(operations=operations, projected_units=projected_units)

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
        yield _AuthoritativeHeadingTarget(
            authority="document_map_outline",
            logical_index=logical_index,
            heading_level=int(entry.level),
            canonical_text=str(entry.title or "").strip(),
            evidence=("outline_entry",) if getattr(entry, "member_logical_indexes", ()) else ("outline_entry", "adjacent_short_heading_fragments"),
            member_logical_indexes=tuple(int(index) for index in getattr(entry, "member_logical_indexes", ()) or ()),
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
        yield _AuthoritativeHeadingTarget(
            authority="document_map_toc",
            logical_index=int(logical_index),
            heading_level=max(1, int(entry.target_level)),
            canonical_text=str(entry.title or "").strip(),
            evidence=("toc_entry", "adjacent_short_heading_fragments"),
        )


def _build_heading_continuation_unit(
    *,
    paragraphs: list[ParagraphUnit],
    position_by_logical_index: dict[int, int],
    target: _AuthoritativeHeadingTarget,
    layout_signals: LayoutSignals | None = None,
) -> StructuralUnit | None:
    logical_index = int(target.logical_index)
    heading_level = int(target.heading_level)
    canonical_text = str(target.canonical_text or "").strip()
    authority = str(target.authority or "").strip()
    evidence = tuple(target.evidence)
    member_logical_indexes = tuple(int(index) for index in target.member_logical_indexes)
    start_position = position_by_logical_index.get(int(logical_index))
    normalized_canonical_tokens = _heading_tokens(canonical_text)
    if start_position is None or len(normalized_canonical_tokens) < 2:
        return None
    if member_logical_indexes:
        return _build_explicit_heading_membership_unit(
            paragraphs=paragraphs,
            position_by_logical_index=position_by_logical_index,
            logical_index=logical_index,
            member_logical_indexes=member_logical_indexes,
            heading_level=heading_level,
            canonical_text=canonical_text,
            authority=authority,
            evidence=evidence,
            layout_signals=layout_signals,
        )

    collected_indexes: list[int] = []
    collected_tokens: list[str] = []
    collected_evidence: list[str] = list(evidence)
    anchor_paragraph = paragraphs[start_position]
    for offset in range(_HEADING_CONTINUATION_WINDOW + 1):
        position = start_position + offset
        if position >= len(paragraphs):
            break
        paragraph = paragraphs[position]
        paragraph_text = str(getattr(paragraph, "text", "") or "").strip()
        paragraph_tokens = _heading_tokens(paragraph_text)
        if not paragraph_tokens:
            break
        candidate_tokens = [*collected_tokens, *paragraph_tokens]
        if offset > 0:
            is_candidate, evidence_tags = _is_heading_continuation_candidate(
                paragraph,
                paragraph_text,
                candidate_tokens=candidate_tokens,
                canonical_tokens=normalized_canonical_tokens,
                anchor_style_cluster_id=getattr(anchor_paragraph, "style_cluster_id", None),
            )
            if not is_candidate:
                break
            _extend_stable_evidence(collected_evidence, evidence_tags)
        collected_indexes.append(int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1))))
        collected_tokens = candidate_tokens
        if _normalized_heading_tokens(candidate_tokens) == _normalized_heading_tokens(normalized_canonical_tokens):
            break

    for prelude_offset in range(1, _HEADING_PRELUDE_WINDOW + 1):
        position = start_position - prelude_offset
        if position < 0:
            break
        paragraph = paragraphs[position]
        paragraph_text = str(getattr(paragraph, "text", "") or "").strip()
        paragraph_tokens = _heading_tokens(paragraph_text)
        if not paragraph_tokens:
            break
        candidate_tokens = [*paragraph_tokens, *collected_tokens]
        is_candidate, evidence_tags = _is_heading_continuation_candidate(
            paragraph,
            paragraph_text,
            candidate_tokens=candidate_tokens,
            canonical_tokens=normalized_canonical_tokens,
            anchor_style_cluster_id=getattr(anchor_paragraph, "style_cluster_id", None),
        )
        if not is_candidate:
            break
        collected_indexes.insert(0, int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1))))
        collected_tokens = candidate_tokens
        _extend_stable_evidence(collected_evidence, evidence_tags)
        if _normalized_heading_tokens(candidate_tokens) == _normalized_heading_tokens(normalized_canonical_tokens):
            break

    if len(collected_indexes) <= 1:
        return None
    if _normalized_heading_tokens(collected_tokens) != _normalized_heading_tokens(normalized_canonical_tokens):
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
        evidence=tuple(collected_evidence),
    )


def _build_explicit_heading_membership_unit(
    *,
    paragraphs: list[ParagraphUnit],
    position_by_logical_index: dict[int, int],
    logical_index: int,
    member_logical_indexes: tuple[int, ...],
    heading_level: int,
    canonical_text: str,
    authority: str,
    evidence: tuple[str, ...],
    layout_signals: LayoutSignals | None = None,
) -> StructuralUnit | None:
    if len(member_logical_indexes) <= 1 or int(logical_index) not in member_logical_indexes:
        return None
    if tuple(member_logical_indexes) != tuple(sorted(member_logical_indexes)):
        return None
    for left_index, right_index in zip(member_logical_indexes, member_logical_indexes[1:], strict=False):
        if int(right_index) != int(left_index) + 1:
            return None

    positions: list[int] = []
    collected_tokens: list[str] = []
    collected_evidence: list[str] = list(evidence)
    anchor_position = position_by_logical_index.get(int(logical_index))
    if anchor_position is None:
        return None
    anchor_paragraph = paragraphs[anchor_position]
    for member_logical_index in member_logical_indexes:
        position = position_by_logical_index.get(int(member_logical_index))
        if position is None:
            return None
        positions.append(position)
        paragraph = paragraphs[position]
        paragraph_text = str(getattr(paragraph, "text", "") or "").strip()
        paragraph_tokens = _heading_tokens(paragraph_text)
        if not paragraph_tokens:
            return None
        if layout_signals is not None and int(member_logical_index) != int(logical_index):
            is_candidate, evidence_tags = _is_heading_continuation_candidate(
                paragraph,
                paragraph_text,
                layout_signals=layout_signals,
                anchor_logical_index=int(logical_index),
                anchor_style_cluster_id=getattr(anchor_paragraph, "style_cluster_id", None),
            )
            if not is_candidate:
                return None
            _extend_stable_evidence(collected_evidence, evidence_tags)
        collected_tokens.extend(paragraph_tokens)

    for left_position, right_position in zip(positions, positions[1:], strict=False):
        if int(right_position) != int(left_position) + 1:
            return None
    if _normalized_heading_tokens(collected_tokens) != _normalized_heading_tokens(_heading_tokens(canonical_text)):
        return None

    unit_type = "chapter_heading" if int(heading_level) <= 1 else "section_heading"
    return StructuralUnit(
        unit_type=unit_type,
        logical_indexes=tuple(int(index) for index in member_logical_indexes),
        canonical_text=str(canonical_text or "").strip(),
        role="heading",
        heading_level=int(heading_level),
        confidence="high",
        authority=authority,
        evidence=tuple(collected_evidence),
    )


def _build_candidate_page_artifact_operations(
    *,
    paragraphs: list[ParagraphUnit],
    authoritative_heading_targets: tuple[_AuthoritativeHeadingTarget, ...],
    layout_signals: LayoutSignals,
) -> list[DocumentTopologyOperation]:
    operations: list[DocumentTopologyOperation] = []

    for position, paragraph in enumerate(paragraphs):
        paragraph_text = _collapse_whitespace(str(getattr(paragraph, "text", "") or ""))
        if not paragraph_text:
            continue
        lowered_text = paragraph_text.casefold()
        matched_phrase = next(
            (
                phrase
                for phrase in _PAGE_FURNITURE_PHRASES
                if (match_position := lowered_text[:120].find(phrase)) >= 0
                and len(lowered_text[match_position + len(phrase) :].strip()) >= 6
            ),
            None,
        )
        if matched_phrase is None:
            continue
        phrase_position = lowered_text[:120].find(matched_phrase)
        remainder_text = paragraph_text[phrase_position + len(matched_phrase) :].strip()
        heading_target = _find_candidate_page_artifact_heading_target(
            paragraphs=paragraphs,
            position=position,
            remainder_text=remainder_text,
            authoritative_heading_targets=authoritative_heading_targets,
        )
        if heading_target is None:
            continue
        logical_index = int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1)))
        evidence = ["page_artifact_phrase", "local_heading_neighborhood"]
        if _local_window_has_observed_page_hint_transition(paragraphs=paragraphs, position=position, layout_signals=layout_signals):
            evidence.append("page_break_boundary")
        operations.append(
            DocumentTopologyOperation(
                op="candidate_page_artifact_split",
                logical_indexes=(logical_index,),
                canonical_text=str(heading_target.canonical_text or "").strip(),
                authority=heading_target.authority,
                confidence="candidate",
                evidence=tuple(evidence),
            )
        )

    return operations


def _find_candidate_page_artifact_heading_target(
    *,
    paragraphs: list[ParagraphUnit],
    position: int,
    remainder_text: str,
    authoritative_heading_targets: tuple[_AuthoritativeHeadingTarget, ...],
) -> _AuthoritativeHeadingTarget | None:
    paragraph = paragraphs[position]
    logical_index = int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1)))
    remainder_tokens = _heading_tokens(remainder_text)
    if remainder_tokens:
        target = _find_local_heading_target(
            logical_index=logical_index,
            heading_hint_tokens=remainder_tokens,
            authoritative_heading_targets=authoritative_heading_targets,
        )
        if target is not None:
            return target
    if position + 1 >= len(paragraphs):
        return None
    next_paragraph = paragraphs[position + 1]
    next_tokens = _heading_tokens(str(getattr(next_paragraph, "text", "") or "").strip())
    if not next_tokens:
        return None
    next_logical_index = int(getattr(next_paragraph, "logical_index", getattr(next_paragraph, "source_index", -1)))
    return _find_local_heading_target(
        logical_index=next_logical_index,
        heading_hint_tokens=next_tokens,
        authoritative_heading_targets=authoritative_heading_targets,
    )


def _local_window_has_observed_page_hint_transition(
    *,
    paragraphs: list[ParagraphUnit],
    position: int,
    layout_signals: LayoutSignals,
) -> bool:
    for candidate_position in (position, position + 1):
        if candidate_position < 0 or candidate_position >= len(paragraphs):
            continue
        logical_index = int(getattr(paragraphs[candidate_position], "logical_index", getattr(paragraphs[candidate_position], "source_index", -1)))
        record = layout_signals.get(logical_index)
        if record is not None and record.is_first_on_page:
            return True
    return False


def _build_binding_split_units(
    *,
    paragraphs: list[ParagraphUnit],
    position_by_logical_index: dict[int, int],
    document_map: DocumentMap,
    authoritative_heading_targets: tuple[tuple[str, int, int, str, tuple[str, ...]], ...],
) -> tuple[list[DocumentTopologyOperation], list[StructuralUnit]]:
    operations: list[DocumentTopologyOperation] = []
    projected_units: list[StructuralUnit] = []
    resolved_compound_toc_split_indexes: set[int] = set()
    for split_hint in document_map.split_hints or ():
        split_result = _resolve_page_artifact_heading_split(
            split_hint=split_hint,
            paragraphs=paragraphs,
            position_by_logical_index=position_by_logical_index,
            authoritative_heading_targets=authoritative_heading_targets,
        )
        if split_result is None:
            continue
        logical_index, page_artifact_text, heading_authority_evidence, heading_level, canonical_text = split_result
        operations.append(
            DocumentTopologyOperation(
                op="split_page_artifact_from_heading",
                logical_indexes=(logical_index,),
                canonical_text=canonical_text,
                authority="document_map_split_hint",
                confidence="high",
                evidence=("split_hint", "page_artifact_phrase", "local_heading_neighborhood", heading_authority_evidence),
            )
        )
        projected_units.append(
            StructuralUnit(
                unit_type="page_artifact",
                logical_indexes=(logical_index,),
                canonical_text=page_artifact_text,
                role="body",
                heading_level=None,
                confidence="high",
                authority="document_map_split_hint",
                evidence=("split_hint", "page_artifact_phrase", "local_heading_neighborhood"),
            )
        )
        projected_units.append(
            StructuralUnit(
                unit_type="chapter_heading" if int(heading_level) <= 1 else "section_heading",
                logical_indexes=(logical_index,),
                canonical_text=canonical_text,
                role="heading",
                heading_level=int(heading_level),
                confidence="high",
                authority="document_map_split_hint",
                evidence=("split_hint", heading_authority_evidence, "local_heading_neighborhood"),
            )
        )
    for split_hint in document_map.split_hints or ():
        split_result = _resolve_compound_toc_entry_split(
            split_hint=split_hint,
            paragraphs=paragraphs,
            position_by_logical_index=position_by_logical_index,
            toc_region=document_map.toc_region,
        )
        if split_result is None:
            continue
        logical_index, canonical_titles, evidence = split_result
        resolved_compound_toc_split_indexes.add(logical_index)
        operations.append(
            DocumentTopologyOperation(
                op="split_compound_toc_entries",
                logical_indexes=(logical_index,),
                canonical_text=" | ".join(canonical_titles),
                authority="document_map_split_hint",
                confidence="high",
                evidence=evidence,
            )
        )
        projected_units.extend(
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(logical_index,),
                canonical_text=canonical_title,
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_split_hint",
                evidence=evidence,
            )
            for canonical_title in canonical_titles
        )

    implicit_toc_region = document_map.toc_region
    if _is_high_confidence_bounded_toc_region(implicit_toc_region):
        for paragraph in paragraphs:
            logical_index = int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1)))
            if logical_index in resolved_compound_toc_split_indexes:
                continue
            split_result = _resolve_implicit_compound_toc_entry_split(
                paragraph=paragraph,
                toc_region=implicit_toc_region,
            )
            if split_result is None:
                continue
            logical_index, canonical_titles = split_result
            operations.append(
                DocumentTopologyOperation(
                    op="split_compound_toc_entries",
                    logical_indexes=(logical_index,),
                    canonical_text=" | ".join(canonical_titles),
                    authority="document_map_toc",
                    confidence="high",
                    evidence=("bounded_toc_region", "one_to_one_toc_entry_match", "toc_entry"),
                )
            )
            projected_units.extend(
                StructuralUnit(
                    unit_type="toc_entry",
                    logical_indexes=(logical_index,),
                    canonical_text=canonical_title,
                    role="toc_entry",
                    heading_level=None,
                    confidence="high",
                    authority="document_map_toc",
                    evidence=("bounded_toc_region", "one_to_one_toc_entry_match", "toc_entry"),
                )
                for canonical_title in canonical_titles
            )
    return operations, projected_units


def _resolve_compound_toc_entry_split(
    *,
    split_hint: DocumentMapSplitHint,
    paragraphs: list[ParagraphUnit],
    position_by_logical_index: dict[int, int],
    toc_region,
) -> tuple[int, tuple[str, ...], tuple[str, ...]] | None:
    if str(split_hint.split_kind or "").strip().lower() != "compound_toc_entries":
        return None
    if str(split_hint.confidence or "").strip().lower() != "high":
        return None
    if not _is_high_confidence_bounded_toc_region(toc_region):
        return None
    logical_index = int(split_hint.logical_index)
    if not _logical_index_in_toc_region(logical_index, toc_region):
        return None
    position = position_by_logical_index.get(logical_index)
    if position is None:
        return None
    paragraph_text = str(getattr(paragraphs[position], "text", "") or "").strip()
    paragraph_tokens = _heading_tokens(paragraph_text)
    if not paragraph_tokens:
        return None
    expected_parts = tuple(str(value or "").strip() for value in split_hint.expected_parts if str(value or "").strip())
    if len(expected_parts) < 2:
        return None
    if not _titles_match_paragraph_tokens(paragraph_tokens, expected_parts):
        return None
    matched_region_titles = _match_high_confidence_toc_region_titles(paragraph_tokens=paragraph_tokens, toc_region=toc_region)
    if not _same_title_sequence(expected_parts, matched_region_titles):
        return None
    evidence = ["split_hint", "bounded_toc_region", "toc_entry"]
    evidence.append("one_to_one_toc_entry_match")
    return logical_index, expected_parts, tuple(evidence)


def _resolve_implicit_compound_toc_entry_split(
    *,
    paragraph: ParagraphUnit,
    toc_region,
) -> tuple[int, tuple[str, ...]] | None:
    if not _is_high_confidence_bounded_toc_region(toc_region):
        return None
    logical_index = int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1)))
    if not _logical_index_in_toc_region(logical_index, toc_region):
        return None
    paragraph_tokens = _heading_tokens(str(getattr(paragraph, "text", "") or "").strip())
    if not paragraph_tokens:
        return None
    matched_titles = _match_high_confidence_toc_region_titles(paragraph_tokens=paragraph_tokens, toc_region=toc_region)
    if len(matched_titles) < 2:
        return None
    return logical_index, matched_titles


def _is_high_confidence_bounded_toc_region(toc_region) -> bool:
    if toc_region is None:
        return False
    if str(getattr(toc_region, "confidence", "") or "").strip().lower() != "high":
        return False
    return int(getattr(toc_region, "start_logical_index", 0)) <= int(getattr(toc_region, "end_logical_index", -1))


def _logical_index_in_toc_region(logical_index: int, toc_region) -> bool:
    return int(getattr(toc_region, "start_logical_index", 0)) <= int(logical_index) <= int(
        getattr(toc_region, "end_logical_index", -1)
    )


def _match_high_confidence_toc_region_titles(*, paragraph_tokens: list[str], toc_region) -> tuple[str, ...]:
    cursor = 0
    matched_titles: list[str] = []
    for entry in getattr(toc_region, "entries", ()):
        if str(getattr(entry, "confidence", "") or "").strip().lower() != "high":
            continue
        match = _find_title_token_match(paragraph_tokens, str(getattr(entry, "title", "") or ""), start=cursor)
        if match is None:
            continue
        _, cursor = match
        matched_titles.append(str(getattr(entry, "title", "") or "").strip())
    return tuple(matched_titles) if len(matched_titles) >= 2 else ()


def _titles_match_paragraph_tokens(paragraph_tokens: list[str], titles: tuple[str, ...]) -> bool:
    cursor = 0
    matched_count = 0
    for title in titles:
        match = _find_title_token_match(paragraph_tokens, title, start=cursor)
        if match is None:
            return False
        _, cursor = match
        matched_count += 1
    return matched_count >= 2


def _find_title_token_match(paragraph_tokens: list[str], title: str, *, start: int) -> tuple[int, int] | None:
    best_match: tuple[int, int, int] | None = None
    for variant in _title_token_variants(title):
        position = _find_token_subsequence(paragraph_tokens, variant, start=start)
        if position is None:
            continue
        candidate = (position, position + len(variant), len(variant))
        if best_match is None or candidate[0] < best_match[0] or (candidate[0] == best_match[0] and candidate[2] > best_match[2]):
            best_match = candidate
    if best_match is None:
        return None
    return best_match[0], best_match[1]


def _title_token_variants(title: str) -> tuple[list[str], ...]:
    tokens = _heading_tokens(title)
    if not tokens:
        return ()
    trimmed_tokens = _trim_heading_prefix(tokens)
    variants = [tokens]
    if trimmed_tokens and trimmed_tokens != tokens:
        variants.append(trimmed_tokens)
    return tuple(variants)


def _find_token_subsequence(tokens: list[str], needle: list[str], *, start: int) -> int | None:
    if not needle:
        return None
    max_start = len(tokens) - len(needle)
    for position in range(max(0, int(start)), max_start + 1):
        if tokens[position : position + len(needle)] == needle:
            return position
    return None


def _same_title_sequence(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if len(left) != len(right):
        return False
    return all(_heading_tokens(left_title) == _heading_tokens(right_title) for left_title, right_title in zip(left, right, strict=False))


def _resolve_page_artifact_heading_split(
    *,
    split_hint: DocumentMapSplitHint,
    paragraphs: list[ParagraphUnit],
    position_by_logical_index: dict[int, int],
    authoritative_heading_targets: tuple[_AuthoritativeHeadingTarget, ...],
) -> tuple[int, str, str, int, str] | None:
    if str(split_hint.split_kind or "").strip().lower() != "page_artifact_heading":
        return None
    if str(split_hint.confidence or "").strip().lower() != "high":
        return None
    expected_parts = tuple(str(value or "").strip() for value in split_hint.expected_parts if str(value or "").strip())
    if len(expected_parts) < 2:
        return None
    logical_index = int(split_hint.logical_index)
    position = position_by_logical_index.get(logical_index)
    if position is None:
        return None
    paragraph_text = str(getattr(paragraphs[position], "text", "") or "").strip()
    paragraph_tokens = _heading_tokens(paragraph_text)
    if not paragraph_tokens:
        return None
    page_artifact_text = expected_parts[0]
    page_artifact_tokens = _heading_tokens(page_artifact_text)
    heading_hint_text = " ".join(expected_parts[1:])
    heading_hint_tokens = _heading_tokens(heading_hint_text)
    if not page_artifact_tokens or not heading_hint_tokens:
        return None
    if not _is_token_prefix(page_artifact_tokens, paragraph_tokens):
        return None
    remaining_tokens = paragraph_tokens[len(page_artifact_tokens) :]
    if not remaining_tokens:
        return None
    if not _token_sequences_compatible(remaining_tokens, heading_hint_tokens):
        return None
    heading_target = _find_local_heading_target(
        logical_index=logical_index,
        heading_hint_tokens=heading_hint_tokens,
        authoritative_heading_targets=authoritative_heading_targets,
    )
    if heading_target is None:
        return None
    heading_level = int(heading_target.heading_level)
    canonical_text = str(heading_target.canonical_text or "").strip()
    evidence = tuple(heading_target.evidence)
    authority_evidence = "toc_entry" if "toc_entry" in evidence else "outline_entry"
    canonical_tokens = _heading_tokens(canonical_text)
    if not canonical_tokens:
        return None
    if not (_token_sequences_compatible(heading_hint_tokens, canonical_tokens) or _token_sequences_compatible(canonical_tokens, heading_hint_tokens)):
        return None
    return logical_index, page_artifact_text, authority_evidence, int(heading_level), str(canonical_text or "").strip()


def _find_local_heading_target(
    *,
    logical_index: int,
    heading_hint_tokens: list[str],
    authoritative_heading_targets: tuple[_AuthoritativeHeadingTarget, ...],
) -> _AuthoritativeHeadingTarget | None:
    matched_targets: list[tuple[tuple[int, int], _AuthoritativeHeadingTarget]] = []
    for target in authoritative_heading_targets:
        if abs(int(target.logical_index) - int(logical_index)) > _BINDING_SPLIT_HEADING_NEIGHBORHOOD:
            continue
        canonical_tokens = _heading_tokens(target.canonical_text)
        if not canonical_tokens:
            continue
        if not (_token_sequences_compatible(heading_hint_tokens, canonical_tokens) or _token_sequences_compatible(canonical_tokens, heading_hint_tokens)):
            continue
        priority = 0 if target.authority == "document_map_outline" else 1
        matched_targets.append(((abs(int(target.logical_index) - int(logical_index)), priority), target))
    if not matched_targets:
        return None
    matched_targets.sort(key=lambda item: item[0])
    return matched_targets[0][1]


def _is_heading_continuation_candidate(
    paragraph: ParagraphUnit,
    paragraph_text: str,
    *,
    candidate_tokens: list[str] | None = None,
    canonical_tokens: list[str] | None = None,
    layout_signals: LayoutSignals | None = None,
    anchor_logical_index: int | None = None,
    anchor_style_cluster_id: int | None = None,
) -> tuple[bool, tuple[str, ...]]:
    normalized = _collapse_whitespace(paragraph_text)
    if not normalized:
        return False, ()
    if bool(getattr(paragraph, "is_repeated_across_pages", False)) or bool(getattr(paragraph, "is_likely_page_number", False)):
        return False, ()
    if len(normalized) > 120:
        return False, ()
    words = normalized.split()
    if len(words) > 14:
        return False, ()
    if not any(char.isalpha() for char in normalized):
        return False, ()
    if normalized.endswith("."):
        return False, ()
    if candidate_tokens is not None and canonical_tokens is not None and _token_sequences_compatible(candidate_tokens, canonical_tokens):
        return True, ("adjacent_short_heading_fragments",)
    if layout_signals is not None and anchor_logical_index is not None:
        logical_index = int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", -1)))
        paragraph_record = layout_signals.get(logical_index)
        candidate_style_cluster_id = getattr(paragraph, "style_cluster_id", None)
        if (
            paragraph_record is not None
            and layout_signals.is_same_heading_tier(anchor_logical_index, logical_index)
            and paragraph_record.is_short_line
            and not layout_signals.is_page_break_between(anchor_logical_index, logical_index)
            and (candidate_style_cluster_id is None or candidate_style_cluster_id == anchor_style_cluster_id)
        ):
            return True, ("adjacent_short_heading_fragments", "font_cluster_match")
    return False, ()


def _extend_stable_evidence(current: list[str], extra: tuple[str, ...]) -> None:
    for tag in extra:
        if tag not in current:
            current.append(tag)


def _build_layout_signals_fingerprint(layout_signals: LayoutSignals) -> str:
    payload = {
        "schema_version": int(getattr(layout_signals, "schema_version", LAYOUT_SIGNALS_SCHEMA_VERSION) or LAYOUT_SIGNALS_SCHEMA_VERSION),
        "body_baseline_pt": layout_signals.body_baseline_pt,
        "body_baseline_tolerance_pt": layout_signals.body_baseline_tolerance_pt,
        "heading_ratio": layout_signals.heading_ratio,
        "tiers": [
            {
                "tier_id": tier.tier_id,
                "representative_pt": tier.representative_pt,
                "member_logical_indexes": list(tier.member_logical_indexes),
                "is_body_baseline": tier.is_body_baseline,
                "is_heading_candidate": tier.is_heading_candidate,
            }
            for tier in layout_signals.tiers
        ],
        "records": [
            {
                "logical_index": logical_index,
                "tier_id": record.tier_id,
                "is_heading_tier": record.is_heading_tier,
                "is_body_tier": record.is_body_tier,
                "font_size_pt": record.font_size_pt,
                "page_number": record.page_number,
                "vertical_gap_before_pt": record.vertical_gap_before_pt,
                "is_first_on_page": record.is_first_on_page,
                "is_short_line": record.is_short_line,
                "is_above_baseline": record.is_above_baseline,
            }
            for logical_index, record in sorted(layout_signals.records_by_logical_index.items())
        ],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _validate_projection_values(
    *,
    operations: list[DocumentTopologyOperation],
    projected_units: list[StructuralUnit],
) -> None:
    for operation in operations:
        if operation.op not in VALID_TOPOLOGY_OPERATIONS:
            raise ValueError(f"Invalid topology operation: {operation.op}")
        if operation.authority not in VALID_TOPOLOGY_AUTHORITIES:
            raise ValueError(f"Invalid topology operation authority: {operation.authority}")
        for evidence_tag in operation.evidence:
            if evidence_tag not in VALID_TOPOLOGY_EVIDENCE:
                raise ValueError(f"Invalid topology evidence tag: {evidence_tag}")
    for unit in projected_units:
        if unit.unit_type not in VALID_TOPOLOGY_UNIT_TYPES:
            raise ValueError(f"Invalid topology unit type: {unit.unit_type}")
        if unit.authority not in VALID_TOPOLOGY_AUTHORITIES:
            raise ValueError(f"Invalid topology unit authority: {unit.authority}")
        for evidence_tag in unit.evidence:
            if evidence_tag not in VALID_TOPOLOGY_EVIDENCE:
                raise ValueError(f"Invalid topology evidence tag: {evidence_tag}")


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
            if _is_chapter_label_fragment(candidate_tokens):
                return True
            continue
        for canonical_variant in canonical_variants:
            if _is_token_prefix(candidate_variant, canonical_variant):
                return True
    return False


def _trim_heading_prefix(tokens: list[str]) -> list[str]:
    if len(tokens) >= 2 and tokens[0] in {"chapter", "глава"}:
        return tokens[2:]
    if tokens and _is_chapter_label_token(tokens[0]):
        return tokens[1:]
    return list(tokens)


def _is_chapter_label_token(token: str) -> bool:
    normalized = str(token or "").strip().casefold()
    if not normalized:
        return False
    if normalized.isdigit():
        return True
    if normalized in _ROMAN_NUMERAL_TOKENS:
        return True
    return normalized in _ENGLISH_NUMBER_TOKENS


def _is_chapter_label_fragment(tokens: list[str]) -> bool:
    if not tokens:
        return False
    if len(tokens) >= 2 and tokens[0] in {"chapter", "глава"}:
        return all(_is_chapter_label_token(token) for token in tokens[1:])
    return all(_is_chapter_label_token(token) for token in tokens)


def _is_token_prefix(candidate_tokens: list[str], canonical_tokens: list[str]) -> bool:
    if len(candidate_tokens) > len(canonical_tokens):
        return False
    return canonical_tokens[: len(candidate_tokens)] == candidate_tokens


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", str(text or "").strip())
