"""Source-to-target paragraph mapping for formatting transfer (spec 033).

This module owns the *mapper* half of the formatting-transfer subsystem: the
paragraph-alignment engine ``_map_source_target_paragraphs`` and all of its passes,
the registry / evidence / similarity gates, the per-call ``_TargetRoleResolver``, the
shared low-level text/role helpers, and every diagnostics builder the mapper calls
inline (their whole output is inside the mapper golden's snapshot, so they live with
the mapper).

Extracted verbatim from ``generation/formatting_transfer.py`` (spec 033, Step 1). The
mapper internals are correctness-critical and were performance-tuned in spec 029; they
are kept byte-identical here and gated by ``tests/test_formatting_mapper_golden.py``.
The dependency direction is one-way: ``formatting_transfer`` (restoration + facade)
imports from this module; this module never imports ``formatting_transfer``.
"""

import functools
import re
from difflib import SequenceMatcher
from typing import Mapping, Sequence, cast

from docx.text.paragraph import Paragraph

from docxaicorrector.document.extraction import IMAGE_PLACEHOLDER_PATTERN
from docxaicorrector.document.relations import (
    build_paragraph_relations,
    resolve_effective_relation_kinds,
)
from docxaicorrector.document.roles import (
    HEADING_STYLE_PATTERN,
    INLINE_HTML_TAG_PATTERN,
    MARKDOWN_LINK_PATTERN,
    detect_explicit_list_kind,
    is_likely_caption_text,
    resolve_paragraph_outline_level,
)
from docxaicorrector.core.models import ParagraphUnit


MARKDOWN_HEADING_LINE_PATTERN = re.compile(r"^#{1,6}\s+\S")


_SYMBOL_ONLY_CARRYOVER_MARKER_PATTERN = re.compile(r"^(?P<body>.+?)\s+(?P<next_number>\d+)\.$")


# Emphasis-coverage diagnostic (spec 004): the inline emphasis dialect emitted by
# ``document/extraction.py::_apply_run_markdown`` — ``***x***`` bold+italic,
# ``**x**`` bold, ``*x*`` / ``_x_`` italic. Triple/double spans are consumed before
# single-asterisk italics so a bold span's inner asterisks are never miscounted.
_EMPHASIS_TRIPLE_SPAN_PATTERN = re.compile(r"\*\*\*(.+?)\*\*\*", re.DOTALL)


_EMPHASIS_BOLD_SPAN_PATTERN = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


_EMPHASIS_ASTERISK_ITALIC_SPAN_PATTERN = re.compile(r"\*(.+?)\*", re.DOTALL)


_EMPHASIS_UNDERSCORE_ITALIC_SPAN_PATTERN = re.compile(r"_(.+?)_", re.DOTALL)


def _paragraph_preview(text: str, *, limit: int = 120) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


@functools.lru_cache(maxsize=1 << 18)
def _normalize_text_for_mapping(text: str) -> str:
    normalized = text.strip()
    normalized = re.sub(r"^(?:>\s*)+", "", normalized)
    normalized = re.sub(r"^#{1,6}\s+", "", normalized)
    normalized = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", normalized)
    normalized = MARKDOWN_LINK_PATTERN.sub(r"\1", normalized)
    normalized = INLINE_HTML_TAG_PATTERN.sub("", normalized)
    normalized = normalized.replace("***", "").replace("**", "").replace("*", "")
    normalized = normalized.replace("<br/>", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    carryover_match = _SYMBOL_ONLY_CARRYOVER_MARKER_PATTERN.match(normalized.strip())
    if carryover_match:
        body = str(carryover_match.group("body") or "").strip()
        body_tokens = body.split()
        if len(body_tokens) <= 2 and not re.search(r"[A-Za-zА-Яа-яЁё]", body):
            normalized = body
    return normalized.strip().lower()


def _is_list_source_paragraph(paragraph: ParagraphUnit) -> bool:
    role = str(getattr(paragraph, "role", "") or "").strip().lower()
    structural_role = str(getattr(paragraph, "structural_role", "") or "").strip().lower()
    return role == "list" or structural_role in {"list", "list_item"} or bool(getattr(paragraph, "list_kind", None))


def _strip_markdown_list_prefixes_for_mapping(text: str) -> str:
    normalized = MARKDOWN_LINK_PATTERN.sub(r"\1", text.strip())
    normalized = INLINE_HTML_TAG_PATTERN.sub("", normalized)
    normalized = normalized.replace("***", "").replace("**", "").replace("*", "")
    previous = ""
    while previous != normalized:
        previous = normalized
        normalized = re.sub(r"^\s*(?:[-*+•]\s+|\d+[.)]\s+)", "", normalized).strip()
    return normalized


def _build_generated_registry_candidates(source_paragraph: ParagraphUnit, generated_text: str) -> list[str]:
    candidates: list[str] = []
    include_list_marker_stripped_variants = _is_list_source_paragraph(source_paragraph)

    def add_candidate(text: str) -> None:
        raw_candidates = [text]
        if include_list_marker_stripped_variants:
            raw_candidates.append(_strip_markdown_list_prefixes_for_mapping(text))
        for raw_candidate in raw_candidates:
            normalized = _normalize_text_for_mapping(raw_candidate)
            if normalized and normalized not in candidates:
                candidates.append(normalized)

    add_candidate(generated_text)

    lines = [line.strip() for line in generated_text.splitlines() if line.strip()]
    if not lines:
        return candidates

    non_heading_lines = [line for line in lines if not MARKDOWN_HEADING_LINE_PATTERN.match(line)]
    if source_paragraph.role == "body" and non_heading_lines:
        add_candidate(" ".join(non_heading_lines))
        for line in non_heading_lines:
            add_candidate(line)
        return candidates

    for line in lines:
        add_candidate(line)
    return candidates


def _is_toc_source_paragraph(paragraph: ParagraphUnit) -> bool:
    structural_role = str(getattr(paragraph, "structural_role", "") or "").strip().lower()
    return structural_role in {"toc_header", "toc_entry"}


def _build_source_registry_entry(
    paragraph: ParagraphUnit,
    fallback_index: int,
    *,
    mapped_target_index: int | None,
    strategy: str | None,
    relation_ids: Sequence[str],
) -> dict[str, object]:
    source_index = paragraph.source_index if paragraph.source_index >= 0 else fallback_index
    return {
        "paragraph_id": paragraph.paragraph_id or f"p{source_index:04d}",
        "source_index": source_index,
        "role": paragraph.role,
        "structural_role": paragraph.structural_role,
        "role_confidence": paragraph.role_confidence,
        "asset_id": paragraph.asset_id,
        "attached_to_asset_id": paragraph.attached_to_asset_id,
        "heading_level": paragraph.heading_level,
        "list_kind": paragraph.list_kind,
        "list_level": paragraph.list_level,
        "list_numbering_format": paragraph.list_numbering_format,
        "list_num_id": paragraph.list_num_id,
        "list_abstract_num_id": paragraph.list_abstract_num_id,
        "origin_raw_indexes": list(paragraph.origin_raw_indexes),
        "origin_raw_text_count": len(paragraph.origin_raw_texts),
        "boundary_source": paragraph.boundary_source,
        "boundary_confidence": paragraph.boundary_confidence,
        "boundary_rationale": paragraph.boundary_rationale,
        "relation_ids": list(relation_ids),
        "mapped_target_index": mapped_target_index,
        "mapping_strategy": strategy,
        "text_preview": _paragraph_preview(_normalize_text_for_mapping(paragraph.text) or paragraph.text),
    }


def _build_target_registry_entry(paragraph, target_index: int, *, mapped: bool) -> dict[str, object]:
    style = getattr(paragraph, "style", None)
    style_name = getattr(style, "name", None)
    return {
        "target_index": target_index,
        "mapped": mapped,
        "style_name": style_name,
        "heading_level": _extract_target_heading_level(paragraph),
        "text_preview": _paragraph_preview(_normalize_text_for_mapping(paragraph.text) or paragraph.text),
    }


def _extract_target_heading_level(paragraph) -> int | None:
    style = getattr(paragraph, "style", None)
    style_name = getattr(style, "name", "") or ""
    normalized_style = style_name.strip().lower()
    style_match = HEADING_STYLE_PATTERN.match(normalized_style)
    if style_match is not None:
        level_text = style_match.group(1)
        if level_text:
            try:
                return max(1, min(int(level_text), 6))
            except ValueError:
                return 1
        return 1

    outline_level = resolve_paragraph_outline_level(paragraph)
    if outline_level is not None:
        return outline_level
    return None


def _count_mapping_strategies(strategy_by_source: Mapping[int, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for strategy in strategy_by_source.values():
        if not strategy:
            continue
        counts[strategy] = counts.get(strategy, 0) + 1
    return dict(sorted(counts.items()))


def _build_unmapped_source_role_counts(
    source_paragraphs: Sequence[ParagraphUnit],
    unmapped_source_ids: Sequence[str],
) -> dict[str, int]:
    unmapped_id_set = set(unmapped_source_ids)
    counts: dict[str, int] = {}
    for index, paragraph in enumerate(source_paragraphs):
        paragraph_id = paragraph.paragraph_id or f"p{index:04d}"
        if paragraph_id not in unmapped_id_set:
            continue
        role = str(paragraph.role or paragraph.structural_role or "unknown").strip() or "unknown"
        counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items()))


def _build_unmapped_source_samples(
    source_paragraphs: Sequence[ParagraphUnit],
    unmapped_source_ids: Sequence[str],
    *,
    limit: int = 25,
) -> list[dict[str, object]]:
    unmapped_id_set = set(unmapped_source_ids)
    samples: list[dict[str, object]] = []
    for index, paragraph in enumerate(source_paragraphs):
        paragraph_id = paragraph.paragraph_id or f"p{index:04d}"
        if paragraph_id not in unmapped_id_set:
            continue
        samples.append(
            {
                "paragraph_id": paragraph_id,
                "source_index": paragraph.source_index if paragraph.source_index >= 0 else index,
                "role": paragraph.role,
                "structural_role": paragraph.structural_role,
                "heading_level": paragraph.heading_level,
                "list_kind": paragraph.list_kind,
                "asset_id": paragraph.asset_id,
                "origin_raw_indexes": list(paragraph.origin_raw_indexes),
                "origin_raw_text_count": len(paragraph.origin_raw_texts),
                "text_preview": _paragraph_preview(_normalize_text_for_mapping(paragraph.text) or paragraph.text),
            }
        )
        if len(samples) >= limit:
            break
    return samples


def _build_unmapped_target_samples(
    target_paragraphs: Sequence[Paragraph],
    unmapped_target_indexes: Sequence[int],
    *,
    limit: int = 25,
) -> list[dict[str, object]]:
    samples: list[dict[str, object]] = []
    for target_index in list(unmapped_target_indexes)[:limit]:
        if target_index < 0 or target_index >= len(target_paragraphs):
            continue
        samples.append(_build_target_registry_entry(target_paragraphs[target_index], target_index, mapped=False))
    return samples


def _build_unmapped_target_residual_diagnostics(
    source_paragraphs: Sequence[ParagraphUnit],
    target_paragraphs: Sequence[Paragraph],
    unmapped_target_indexes: Sequence[int],
    *,
    generated_registry_by_id: Mapping[str, Mapping[str, object]],
    mapped_target_by_source: Mapping[int, int],
    accepted_aggregated_sources: Sequence[Mapping[str, object]],
    limit: int = 25,
) -> dict[str, object]:
    accepted_anchor_by_source: dict[int, list[Mapping[str, object]]] = {}
    for accepted_source in accepted_aggregated_sources:
        source_index = accepted_source.get("source_index")
        target_index = accepted_source.get("target_index")
        if isinstance(source_index, int) and isinstance(target_index, int):
            accepted_anchor_by_source.setdefault(source_index, []).append(accepted_source)

    rows: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    classification_counts: dict[str, int] = {}

    for target_index in unmapped_target_indexes:
        if target_index < 0 or target_index >= len(target_paragraphs):
            continue
        target_paragraph = target_paragraphs[target_index]
        normalized_target = _normalize_text_for_mapping(target_paragraph.text)
        target_tokens = re.findall(r"\w+", normalized_target, flags=re.UNICODE)
        target_format_role = _target_format_role(target_paragraph)
        best_source: dict[str, object] | None = None
        classification = "spurious_or_unproven"

        if len(target_tokens) < 5:
            classification = "short_note_or_marker"
        else:
            for source_index, source_paragraph in enumerate(source_paragraphs):
                paragraph_id = source_paragraph.paragraph_id or f"p{source_index:04d}"
                generated_entry = generated_registry_by_id.get(paragraph_id)
                generated_text = _generated_registry_text(generated_entry)
                if not generated_text:
                    continue
                evidence = _text_coverage_evidence(normalized_target, generated_text)
                if evidence is None:
                    continue
                candidate = {
                    "paragraph_id": paragraph_id,
                    "source_index": source_index,
                    "source_format_role": _source_format_role(source_paragraph),
                    "mapped_target_index": mapped_target_by_source.get(source_index),
                    "evidence": evidence,
                    "source_text_preview": _paragraph_preview(source_paragraph.text),
                }
                if isinstance(generated_entry, Mapping) and bool(generated_entry.get("controlled_fallback")):
                    candidate["controlled_fallback"] = True
                    candidate["controlled_fallback_kind"] = generated_entry.get("controlled_fallback_kind")
                    candidate["controlled_fallback_block_index"] = generated_entry.get("block_index")
                if best_source is None:
                    best_source = candidate
                    continue
                best_evidence = cast(Mapping[str, object], best_source["evidence"])
                if (
                    float(evidence.get("token_overlap_ratio", 0.0)),
                    float(evidence.get("score", 0.0)),
                    int(evidence.get("common_token_count", 0) or 0),
                ) > (
                    float(best_evidence.get("token_overlap_ratio", 0.0)),
                    float(best_evidence.get("score", 0.0)),
                    int(best_evidence.get("common_token_count", 0) or 0),
                ):
                    best_source = candidate

            if best_source is not None:
                source_index = int(best_source["source_index"])
                mapped_anchor = best_source.get("mapped_target_index")
                anchors: list[dict[str, object]] = []
                if bool(best_source.get("controlled_fallback")):
                    classification = "controlled_fallback_covered"
                elif isinstance(mapped_anchor, int):
                    anchors.append({"target_index": mapped_anchor, "kind": "mapped_source_target"})
                    for accepted_anchor in accepted_anchor_by_source.get(source_index, []):
                        accepted_target_index = accepted_anchor.get("target_index")
                        if isinstance(accepted_target_index, int):
                            anchors.append(
                                {
                                    "target_index": accepted_target_index,
                                    "kind": accepted_anchor.get("kind") or "accepted_aggregated_source",
                                }
                            )
                    if any(abs(int(anchor["target_index"]) - target_index) == 1 for anchor in anchors):
                        classification = "split_accounting"
                        best_source["split_anchor_targets"] = anchors
                    else:
                        classification = "matcher_miss"

        classification_counts[classification] = classification_counts.get(classification, 0) + 1
        row: dict[str, object] = {
            "target_index": target_index,
            "target_format_role": target_format_role,
            "target_text_preview": _paragraph_preview(target_paragraph.text),
            "residual_class": classification,
            "target_token_count": len(target_tokens),
        }
        if best_source is not None:
            evidence = cast(Mapping[str, object], best_source.get("evidence") or {})
            row.update(
                {
                    "best_source_paragraph_id": best_source.get("paragraph_id"),
                    "best_source_index": best_source.get("source_index"),
                    "best_source_format_role": best_source.get("source_format_role"),
                    "best_source_mapped_target_index": best_source.get("mapped_target_index"),
                    "best_source_text_preview": best_source.get("source_text_preview"),
                    "text_evidence_type": evidence.get("evidence_type"),
                    "text_evidence_score": evidence.get("score"),
                    "text_evidence_token_overlap_ratio": evidence.get("token_overlap_ratio"),
                    "split_anchor_targets": best_source.get("split_anchor_targets", []),
                }
            )
            if bool(best_source.get("controlled_fallback")):
                row["controlled_fallback_kind"] = best_source.get("controlled_fallback_kind")
                row["controlled_fallback_block_index"] = best_source.get("controlled_fallback_block_index")
        rows.append(row)
        if len(samples) < limit:
            samples.append(row)

    split_accounting_count = classification_counts.get("split_accounting", 0)
    controlled_fallback_creditable_count = classification_counts.get("controlled_fallback_covered", 0)
    creditable_count = split_accounting_count + controlled_fallback_creditable_count

    return {
        "classification_basis": "full_unmapped_target_set",
        "evidence_basis": "target_registry text contained/fuzzy-covered by generated source registry text",
        "split_accounting_rule": (
            "Credit only unmapped target paragraphs whose text is covered by a source registry entry "
            "and that sit directly adjacent to that source's mapped or accepted aggregate target."
        ),
        "controlled_fallback_accounting_rule": (
            "Credit unmapped target paragraphs whose text is covered by a generated registry entry "
            "from a block explicitly retained through controlled fallback."
        ),
        "counts": dict(sorted(classification_counts.items())),
        "split_accounting_creditable_count": creditable_count,
        "split_accounting_only_creditable_count": split_accounting_count,
        "controlled_fallback_creditable_count": controlled_fallback_creditable_count,
        "residual_rows": rows,
        "samples": samples,
    }


def _count_relation_id_population(
    relation_ids_by_paragraph: Mapping[str, Sequence[str]],
    source_count: int,
) -> dict[str, int]:
    populated = sum(1 for relation_ids in relation_ids_by_paragraph.values() if relation_ids)
    return {
        "source_count": source_count,
        "relation_id_populated_count": populated,
        "relation_id_missing_count": max(source_count - populated, 0),
    }


def _target_indexes_containing_candidate(
    target_paragraphs: Sequence[Paragraph],
    candidate_text: str,
    *,
    limit: int = 5,
) -> list[int]:
    normalized_candidate = _normalize_text_for_mapping(candidate_text)
    if not normalized_candidate:
        return []

    indexes: list[int] = []
    for target_index, target_paragraph in enumerate(target_paragraphs):
        normalized_target = _normalize_text_for_mapping(target_paragraph.text)
        if not normalized_target:
            continue
        if normalized_candidate == normalized_target or normalized_candidate in normalized_target:
            indexes.append(target_index)
            if len(indexes) >= limit:
                break
    return indexes


def _target_indexes_containing_any_candidate(
    target_paragraphs: Sequence[Paragraph],
    candidate_texts: Sequence[str],
    *,
    limit: int = 5,
) -> list[int]:
    indexes: list[int] = []
    for candidate_text in candidate_texts:
        for target_index in _target_indexes_containing_candidate(target_paragraphs, candidate_text, limit=limit):
            if target_index not in indexes:
                indexes.append(target_index)
                if len(indexes) >= limit:
                    return indexes
    return indexes


def _classify_unmapped_source_residual(
    paragraph: ParagraphUnit,
    paragraph_id: str,
    *,
    generated_registry_by_id: Mapping[str, Mapping[str, object]],
    relation_ids_by_paragraph: Mapping[str, Sequence[str]],
) -> str:
    if paragraph.role == "image" or paragraph.asset_id:
        return "image_or_placeholder_accounted_elsewhere"

    registry_entry = generated_registry_by_id.get(paragraph_id)
    merged_ids = _generated_registry_merged_ids(registry_entry)
    relation_ids = relation_ids_by_paragraph.get(paragraph_id, ())
    if (
        len(paragraph.origin_raw_texts) > 1
        or len(paragraph.origin_raw_indexes) > 1
        or len(merged_ids) > 1
        or relation_ids
    ):
        return "true_aggregate_unmapped"

    if paragraph_id and registry_entry is not None:
        return "single_origin_lost_match"

    return "real_uncovered"


def _classify_residual_closability(
    residual_category: str,
    free_target_candidate_indexes: Sequence[int],
    occupied_neighbor_candidate_indexes: Sequence[int],
) -> str:
    if residual_category == "single_origin_lost_match":
        if free_target_candidate_indexes:
            return "target_exists_text_align_missed"
        if occupied_neighbor_candidate_indexes:
            return "target_occupied_by_mapped_neighbor"
        return "target_absent_or_unproven"
    if residual_category == "true_aggregate_unmapped":
        return "true_aggregate_relation_gap"
    if residual_category == "real_uncovered":
        return "real_uncovered"
    if residual_category == "image_or_placeholder_accounted_elsewhere":
        return "image_or_placeholder_accounted_elsewhere"
    return "unknown"


def _source_format_role(paragraph: ParagraphUnit) -> str:
    role = str(getattr(paragraph, "role", "") or "").strip().lower()
    structural_role = str(getattr(paragraph, "structural_role", "") or "").strip().lower()
    if role == "image" or getattr(paragraph, "asset_id", None):
        return "image"
    if _is_heading_like_source_paragraph(paragraph):
        return "heading"
    if role == "list" or structural_role in {"list", "list_item"} or getattr(paragraph, "list_kind", None):
        return "list"
    if role == "caption" or structural_role == "caption":
        return "caption"
    if structural_role in {"toc_header", "toc_entry"}:
        return "toc"
    if structural_role in {"epigraph", "attribution", "dedication"}:
        return structural_role
    return "body"


def _target_format_role(paragraph: Paragraph) -> str:
    if IMAGE_PLACEHOLDER_PATTERN.search(paragraph.text):
        return "image"
    if _extract_target_heading_level(paragraph) is not None:
        return "heading"
    if detect_explicit_list_kind(paragraph.text) is not None:
        return "list"
    return "body"


def _target_has_heading_format(paragraph: Paragraph) -> bool:
    return _extract_target_heading_level(paragraph) is not None


def _text_coverage_evidence(candidate_text: str, target_text: str) -> dict[str, object] | None:
    normalized_candidate = _normalize_text_for_mapping(candidate_text)
    normalized_target = _normalize_text_for_mapping(target_text)
    if not normalized_candidate or not normalized_target:
        return None
    if normalized_candidate == normalized_target or normalized_candidate in normalized_target:
        return {"evidence_type": "exact_contains", "score": 1.0, "token_overlap_ratio": 1.0}

    candidate_tokens = set(re.findall(r"\w+", normalized_candidate, flags=re.UNICODE))
    target_tokens = set(re.findall(r"\w+", normalized_target, flags=re.UNICODE))
    if not candidate_tokens or not target_tokens:
        return None
    common_count = len(candidate_tokens & target_tokens)
    token_overlap_ratio = common_count / len(candidate_tokens)
    sequence_ratio = SequenceMatcher(None, normalized_candidate, normalized_target).ratio()
    if (
        (common_count >= 4 and token_overlap_ratio >= 0.62)
        or (common_count >= 2 and token_overlap_ratio >= 0.8)
        or (len(normalized_candidate) >= 20 and sequence_ratio >= 0.75)
    ):
        return {
            "evidence_type": "fuzzy_token_overlap",
            "score": round(max(token_overlap_ratio, sequence_ratio), 4),
            "token_overlap_ratio": round(token_overlap_ratio, 4),
            "sequence_ratio": round(sequence_ratio, 4),
            "common_token_count": common_count,
            "candidate_token_count": len(candidate_tokens),
        }
    return None


def _neighbor_candidate_evidence(
    *,
    source_index: int,
    candidate_texts: Sequence[str],
    target_paragraphs: Sequence[Paragraph],
    mapped_source_by_target: Mapping[int, int],
    source_window: int = 3,
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for target_index, mapped_source_index in sorted(mapped_source_by_target.items()):
        if target_index >= len(target_paragraphs):
            continue
        source_distance = abs(mapped_source_index - source_index)
        if source_distance > source_window:
            continue
        text_evidence_candidates = [
            candidate_evidence
            for candidate_text in candidate_texts
            if (candidate_evidence := _text_coverage_evidence(candidate_text, target_paragraphs[target_index].text))
            is not None
        ]
        if not text_evidence_candidates:
            continue
        text_evidence_candidates.sort(
            key=lambda evidence: (
                float(evidence.get("score", 0.0)),
                float(evidence.get("token_overlap_ratio", 0.0)),
            ),
            reverse=True,
        )
        text_evidence = text_evidence_candidates[0]
        evidence.append(
            {
                "target_index": target_index,
                "mapped_source_index": mapped_source_index,
                "source_distance": source_distance,
                **text_evidence,
            }
        )
    return evidence


def _occupied_candidate_evidence(
    *,
    target_candidate_indexes: Sequence[int],
    candidate_texts: Sequence[str],
    target_paragraphs: Sequence[Paragraph],
    mapped_source_by_target: Mapping[int, int],
    source_index: int,
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for target_index in target_candidate_indexes:
        mapped_source_index = mapped_source_by_target.get(target_index)
        if mapped_source_index is None:
            continue
        text_evidence_candidates = [
            candidate_evidence
            for candidate_text in candidate_texts
            if (candidate_evidence := _text_coverage_evidence(candidate_text, target_paragraphs[target_index].text))
            is not None
        ]
        if not text_evidence_candidates:
            continue
        text_evidence_candidates.sort(
            key=lambda item: (
                float(item.get("score", 0.0)),
                float(item.get("token_overlap_ratio", 0.0)),
            ),
            reverse=True,
        )
        evidence.append(
            {
                "target_index": target_index,
                "mapped_source_index": mapped_source_index,
                "source_distance": abs(mapped_source_index - source_index),
                **text_evidence_candidates[0],
            }
        )
    return evidence


def _classify_effective_formatting_coverage(
    *,
    residual_category: str,
    source_format_role: str,
    neighbor_evidence: Sequence[Mapping[str, object]],
    occupied_candidate_evidence: Sequence[Mapping[str, object]],
    target_candidate_indexes: Sequence[int],
    target_roles_by_index: Mapping[int, str],
) -> str:
    if residual_category == "single_origin_lost_match":
        if not neighbor_evidence:
            if source_format_role != "body" and (
                occupied_candidate_evidence
                or any(target_roles_by_index.get(target_index) != source_format_role for target_index in target_candidate_indexes)
            ):
                return "content_survived_but_format_role_lost"
            return "unproven_or_marker_closable"
        if source_format_role == "body" and any(
            isinstance(evidence.get("target_index"), int)
            and target_roles_by_index.get(int(evidence["target_index"])) == "body"
            for evidence in neighbor_evidence
        ):
            return "format_neutral_body_dissolved_creditable"
        return "content_survived_but_format_role_lost"
    if residual_category == "true_aggregate_unmapped":
        return "true_aggregate_relation_gap"
    if residual_category == "real_uncovered":
        return "real_uncovered"
    if residual_category == "image_or_placeholder_accounted_elsewhere":
        return "image_or_placeholder_accounted_elsewhere"
    return "unknown"


def _build_unmapped_source_residual_diagnostics(
    source_paragraphs: Sequence[ParagraphUnit],
    target_paragraphs: Sequence[Paragraph],
    unmapped_source_ids: Sequence[str],
    *,
    generated_registry_by_id: Mapping[str, Mapping[str, object]],
    relation_ids_by_paragraph: Mapping[str, Sequence[str]],
    mapped_target_by_source: Mapping[int, int],
    limit: int = 25,
) -> dict[str, object]:
    unmapped_id_set = set(unmapped_source_ids)
    category_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    closability_counts: dict[str, int] = {}
    effective_coverage_counts: dict[str, int] = {}
    residual_rows: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    mapped_source_by_target = {target_index: source_index for source_index, target_index in mapped_target_by_source.items()}
    mapped_target_indexes = set(mapped_source_by_target)
    target_roles_by_index = {
        target_index: _target_format_role(target_paragraph)
        for target_index, target_paragraph in enumerate(target_paragraphs)
    }

    for index, paragraph in enumerate(source_paragraphs):
        paragraph_id = paragraph.paragraph_id or f"p{index:04d}"
        if paragraph_id not in unmapped_id_set:
            continue

        registry_entry = generated_registry_by_id.get(paragraph_id)
        registry_text = _generated_registry_text(registry_entry)
        registry_candidate_texts = _build_generated_registry_candidates(paragraph, registry_text) if registry_text else []
        coverage_candidate_texts = registry_candidate_texts or [paragraph.text]
        relation_ids = list(relation_ids_by_paragraph.get(paragraph_id, ()))
        merged_ids = _generated_registry_merged_ids(registry_entry)
        category = _classify_unmapped_source_residual(
            paragraph,
            paragraph_id,
            generated_registry_by_id=generated_registry_by_id,
            relation_ids_by_paragraph=relation_ids_by_paragraph,
        )
        category_counts[category] = category_counts.get(category, 0) + 1
        target_candidate_indexes = _target_indexes_containing_any_candidate(
            target_paragraphs,
            coverage_candidate_texts,
        )
        free_target_candidate_indexes = [
            target_index for target_index in target_candidate_indexes if target_index not in mapped_target_indexes
        ]
        neighbor_evidence = _neighbor_candidate_evidence(
            source_index=index,
            candidate_texts=coverage_candidate_texts,
            target_paragraphs=target_paragraphs,
            mapped_source_by_target=mapped_source_by_target,
        )
        occupied_candidate_evidence = _occupied_candidate_evidence(
            target_candidate_indexes=target_candidate_indexes,
            candidate_texts=coverage_candidate_texts,
            target_paragraphs=target_paragraphs,
            mapped_source_by_target=mapped_source_by_target,
            source_index=index,
        )
        occupied_neighbor_candidate_indexes = [
            int(evidence["target_index"])
            for evidence in neighbor_evidence
            if isinstance(evidence.get("target_index"), int)
        ]
        source_format_role = _source_format_role(paragraph)
        closability_class = _classify_residual_closability(
            category,
            free_target_candidate_indexes,
            occupied_neighbor_candidate_indexes,
        )
        closability_counts[closability_class] = closability_counts.get(closability_class, 0) + 1
        effective_coverage_class = _classify_effective_formatting_coverage(
            residual_category=category,
            source_format_role=source_format_role,
            neighbor_evidence=neighbor_evidence,
            occupied_candidate_evidence=occupied_candidate_evidence,
            target_candidate_indexes=target_candidate_indexes,
            target_roles_by_index=target_roles_by_index,
        )
        effective_coverage_counts[effective_coverage_class] = effective_coverage_counts.get(effective_coverage_class, 0) + 1

        if not paragraph.paragraph_id:
            first_missing_stage = "source_paragraph_id_missing"
        elif registry_entry is None:
            first_missing_stage = "translation_marker_or_generated_registry_missing"
        else:
            first_missing_stage = "rebuilt_docx_restore_match_missing"
        stage_counts[first_missing_stage] = stage_counts.get(first_missing_stage, 0) + 1

        row: dict[str, object] = {
            "paragraph_id": paragraph_id,
            "source_index": paragraph.source_index if paragraph.source_index >= 0 else index,
            "role": paragraph.role,
            "structural_role": paragraph.structural_role,
            "source_format_role": source_format_role,
            "residual_category": category,
            "residual_closability_class": closability_class,
            "effective_formatting_coverage_class": effective_coverage_class,
            "first_missing_identity_stage": first_missing_stage,
            "source_paragraph_id_available": bool(paragraph.paragraph_id),
            "generated_registry_entry_available": registry_entry is not None,
            "generated_registry_merged_ids": merged_ids,
            "relation_ids": relation_ids,
            "target_candidate_indexes_containing_registry_text": target_candidate_indexes,
            "free_target_candidate_indexes_containing_registry_text": free_target_candidate_indexes,
            "occupied_candidate_evidence": occupied_candidate_evidence,
            "occupied_neighbor_candidate_evidence": neighbor_evidence,
            "origin_raw_text_count": len(paragraph.origin_raw_texts),
            "origin_raw_indexes": list(paragraph.origin_raw_indexes),
            "text_preview": _paragraph_preview(_normalize_text_for_mapping(paragraph.text) or paragraph.text),
            "generated_text_preview": _paragraph_preview(registry_text) if registry_text else "",
        }
        residual_rows.append(row)
        if len(samples) < limit:
            samples.append(row)

    return {
        "category_counts": dict(sorted(category_counts.items())),
        "first_missing_identity_stage_counts": dict(sorted(stage_counts.items())),
        "residual_closability_diagnostics": {
            "classification_basis": "full_unmapped_source_set",
            "counts": dict(sorted(closability_counts.items())),
            "embedded_marker_upper_bound_count": closability_counts.get("target_exists_text_align_missed", 0),
            "embedded_marker_upper_bound_class": "target_exists_text_align_missed",
            "embedded_marker_upper_bound_note": "Counts only candidates on unmapped/free target paragraphs.",
        },
        "effective_formatting_coverage_diagnostics": {
            "classification_basis": "full_unmapped_source_set",
            "evidence_basis": "registry_text_exact_or_fuzzy_overlap_in_already_mapped_neighbor_target",
            "source_neighbor_window": 3,
            "fuzzy_evidence_rule": (
                "exact containment, or token overlap >=0.62 with >=4 common tokens, "
                "or token overlap >=0.8 with >=2 common tokens, or sequence ratio >=0.75 for longer text"
            ),
            "role_credit_rule": "Only body source dissolved into body target is format-neutral credit.",
            "counts": dict(sorted(effective_coverage_counts.items())),
            "format_neutral_creditable_count": effective_coverage_counts.get(
                "format_neutral_body_dissolved_creditable",
                0,
            ),
        },
        "residual_rows": residual_rows,
        "samples": samples,
    }


def _build_caption_heading_conflicts(
    source_paragraphs: list[ParagraphUnit],
    target_paragraphs: list[Paragraph],
    mapped_target_by_source: Mapping[int, int],
    strategy_by_source: Mapping[int, str],
) -> list[dict[str, object]]:
    conflicts: list[dict[str, object]] = []
    for source_index, target_index in sorted(mapped_target_by_source.items()):
        source_paragraph = source_paragraphs[source_index]
        if source_paragraph.role != "caption":
            continue

        target_paragraph = target_paragraphs[target_index]
        target_heading_level = _extract_target_heading_level(target_paragraph)
        if target_heading_level is None:
            continue

        conflicts.append(
            {
                "paragraph_id": source_paragraph.paragraph_id or f"p{source_index:04d}",
                "source_index": source_paragraph.source_index if source_paragraph.source_index >= 0 else source_index,
                "mapped_target_index": target_index,
                "mapping_strategy": strategy_by_source.get(source_index),
                "source_role": source_paragraph.role,
                "source_role_confidence": source_paragraph.role_confidence,
                "attached_to_asset_id": source_paragraph.attached_to_asset_id,
                "target_style_name": getattr(getattr(target_paragraph, "style", None), "name", None),
                "target_heading_level": target_heading_level,
                "source_text_preview": _paragraph_preview(source_paragraph.text),
                "target_text_preview": _paragraph_preview(target_paragraph.text),
            }
        )
    return conflicts


def _build_rebuild_key_mapping_quality_diagnostics(
    source_paragraphs: Sequence[ParagraphUnit],
    target_paragraphs: Sequence[Paragraph],
    mapped_target_by_source: Mapping[int, int],
    strategy_by_source: Mapping[int, str],
    *,
    limit: int = 25,
) -> dict[str, object]:
    mapped_count = 0
    suspicious_counts: dict[str, int] = {}
    samples: list[dict[str, object]] = []

    for source_index, target_index in sorted(mapped_target_by_source.items()):
        if strategy_by_source.get(source_index) != "paragraph_id_rebuild_key":
            continue
        if source_index >= len(source_paragraphs) or target_index >= len(target_paragraphs):
            continue
        mapped_count += 1
        source_paragraph = source_paragraphs[source_index]
        target_paragraph = target_paragraphs[target_index]
        source_role = str(source_paragraph.role or "").strip().lower()
        source_structural_role = str(getattr(source_paragraph, "structural_role", "") or "").strip().lower()
        target_heading_level = _extract_target_heading_level(target_paragraph)
        target_list_kind = detect_explicit_list_kind(target_paragraph.text)

        reasons: list[str] = []
        if target_heading_level is not None and source_role not in {"heading"} and source_structural_role != "heading":
            reasons.append("non_heading_source_to_heading_target")
        if (
            target_list_kind is not None
            and source_role not in {"list"}
            and source_structural_role not in {"list", "list_item"}
        ):
            reasons.append("non_list_source_to_list_target")

        if not reasons:
            continue

        for reason in reasons:
            suspicious_counts[reason] = suspicious_counts.get(reason, 0) + 1
        if len(samples) >= limit:
            continue
        samples.append(
            {
                "paragraph_id": source_paragraph.paragraph_id or f"p{source_index:04d}",
                "source_index": source_paragraph.source_index if source_paragraph.source_index >= 0 else source_index,
                "mapped_target_index": target_index,
                "reasons": reasons,
                "source_role": source_paragraph.role,
                "source_structural_role": source_paragraph.structural_role,
                "target_style_name": _target_paragraph_style_name(target_paragraph),
                "target_heading_level": target_heading_level,
                "target_list_kind": target_list_kind,
                "source_text_preview": _paragraph_preview(source_paragraph.text),
                "target_text_preview": _paragraph_preview(target_paragraph.text),
            }
        )

    return {
        "strategy": "paragraph_id_rebuild_key",
        "mapped_count": mapped_count,
        "suspicious_count": sum(suspicious_counts.values()),
        "suspicious_counts": dict(sorted(suspicious_counts.items())),
        "samples": samples,
    }


TEXT_VERIFIED_MAPPING_STRATEGIES = {
    "bounded_registry_fuzzy",
    "bounded_registry_heading_containment",
    "paragraph_id_registry_similarity",
    "projected_registry_fuzzy",
    "registry_repeated_note_sequence",
    "registry_free_target_text_floor",
}


def _mapping_text_floor_quality(candidate_text: str, target_text: str) -> dict[str, object]:
    normalized_candidate = _normalize_text_for_mapping(candidate_text)
    normalized_target = _normalize_text_for_mapping(target_text)
    candidate_tokens = _token_set(normalized_candidate)
    target_tokens = _token_set(normalized_target)
    common_count = len(candidate_tokens & target_tokens) if candidate_tokens and target_tokens else 0
    token_jaccard_ratio = (
        common_count / len(candidate_tokens | target_tokens)
        if candidate_tokens and target_tokens
        else 0.0
    )
    token_overlap_ratio = common_count / len(candidate_tokens) if candidate_tokens else 0.0
    target_token_overlap_ratio = common_count / len(target_tokens) if target_tokens else 0.0
    exact_or_contains = bool(
        normalized_candidate
        and normalized_target
        and (normalized_candidate == normalized_target or normalized_candidate in normalized_target)
    )
    return {
        "exact_or_contains": exact_or_contains,
        "token_jaccard_ratio": round(token_jaccard_ratio, 4),
        "token_overlap_ratio": round(token_overlap_ratio, 4),
        "target_token_overlap_ratio": round(target_token_overlap_ratio, 4),
        "common_token_count": common_count,
        "candidate_token_count": len(candidate_tokens),
        "target_token_count": len(target_tokens),
    }


def _mapping_text_floor_is_bad(quality: Mapping[str, object]) -> bool:
    return not (
        bool(quality.get("exact_or_contains"))
        or float(quality.get("token_jaccard_ratio", 0.0) or 0.0) >= 0.5
        or float(quality.get("token_overlap_ratio", 0.0) or 0.0) >= 0.85
        or float(quality.get("target_token_overlap_ratio", 0.0) or 0.0) >= 0.85
    )


def _build_mapping_text_quality_diagnostics(
    source_paragraphs: Sequence[ParagraphUnit],
    target_paragraphs: Sequence[Paragraph],
    mapped_target_by_source: Mapping[int, int],
    strategy_by_source: Mapping[int, str],
    generated_registry_by_id: Mapping[str, Mapping[str, object]],
    *,
    limit: int = 25,
) -> dict[str, object]:
    checked_count = 0
    bad_pair_count = 0
    strategy_counts: dict[str, int] = {}
    bad_strategy_counts: dict[str, int] = {}
    samples: list[dict[str, object]] = []

    for source_index, target_index in sorted(mapped_target_by_source.items()):
        strategy = strategy_by_source.get(source_index)
        if strategy not in TEXT_VERIFIED_MAPPING_STRATEGIES:
            continue
        if source_index >= len(source_paragraphs) or target_index >= len(target_paragraphs):
            continue
        source_paragraph = source_paragraphs[source_index]
        paragraph_id = source_paragraph.paragraph_id or f"p{source_index:04d}"
        source_text = _generated_registry_text(generated_registry_by_id.get(paragraph_id)) or source_paragraph.text
        target_paragraph = target_paragraphs[target_index]
        quality = _mapping_text_floor_quality(source_text, target_paragraph.text)

        checked_count += 1
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        if not _mapping_text_floor_is_bad(quality):
            continue

        bad_pair_count += 1
        bad_strategy_counts[strategy] = bad_strategy_counts.get(strategy, 0) + 1
        if len(samples) >= limit:
            continue
        samples.append(
            {
                "paragraph_id": paragraph_id,
                "source_index": source_paragraph.source_index if source_paragraph.source_index >= 0 else source_index,
                "mapped_target_index": target_index,
                "mapping_strategy": strategy,
                "source_role": source_paragraph.role,
                "target_style_name": _target_paragraph_style_name(target_paragraph),
                "source_text_preview": _paragraph_preview(source_text),
                "target_text_preview": _paragraph_preview(target_paragraph.text),
                **quality,
            }
        )

    return {
        "indexing_basis": "formatting_diagnostics.target_registry[mapped_target_index]",
        "source_text_basis": "runtime.state.final_generated_paragraph_registry when available; source paragraph text fallback",
        "strategy_filter": sorted(TEXT_VERIFIED_MAPPING_STRATEGIES),
        "checked_count": checked_count,
        "bad_pair_count": bad_pair_count,
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "bad_strategy_counts": dict(sorted(bad_strategy_counts.items())),
        "bad_pair_rule": (
            "bad when not exact/contained, token_jaccard < 0.50, "
            "source_token_overlap < 0.85, and target_token_overlap < 0.85"
        ),
        "samples": samples,
    }


def _mapping_similarity_score(source_paragraph: ParagraphUnit, target_text: str) -> float:
    source_text = _normalize_text_for_mapping(source_paragraph.text)
    normalized_target = _normalize_text_for_mapping(target_text)
    if not source_text or not normalized_target:
        return 0.0

    # Lever C (spec 029): pass 13 accepts only when the final score >= 0.9, and the role
    # bonuses add at most 0.08, so ratio() must be >= 0.82 for any acceptance. real_quick_ratio()
    # is a guaranteed upper bound on ratio(), so when it is below 0.82 the pair can never be
    # accepted and the O(L^2) ratio() is skipped. Provably identical (score stays < 0.9).
    matcher = SequenceMatcher(None, source_text, normalized_target)
    if matcher.real_quick_ratio() < 0.82:
        return 0.0
    score = matcher.ratio()
    if source_paragraph.role == "caption" and is_likely_caption_text(target_text):
        score += 0.08
    if source_paragraph.role == "list":
        target_list_kind = detect_explicit_list_kind(target_text)
        if target_list_kind is not None and target_list_kind == source_paragraph.list_kind:
            score += 0.05
    if source_paragraph.role == "heading" and len(target_text.split()) <= 18:
        score += 0.03
    return min(score, 1.0)


@functools.lru_cache(maxsize=1 << 18)
def _token_set(text: str) -> frozenset[str]:
    # Cached, immutable: callers only read via len / & / | (never mutate), so a shared
    # frozenset is safe and lets the cache serve repeated (source, target) comparisons.
    return frozenset(re.findall(r"\w+", text, flags=re.UNICODE))


def _registry_candidate_mapping_evidence(
    candidate_text: str,
    target_text: str,
    *,
    source_format_role: str,
) -> dict[str, object] | None:
    normalized_candidate = _normalize_text_for_mapping(candidate_text)
    normalized_target = _normalize_text_for_mapping(target_text)
    if not normalized_candidate or not normalized_target:
        return None

    candidate_tokens = _token_set(normalized_candidate)
    target_tokens = _token_set(normalized_target)
    common_count = len(candidate_tokens & target_tokens) if candidate_tokens and target_tokens else 0
    token_overlap_ratio = common_count / len(candidate_tokens) if candidate_tokens else 0.0
    target_token_overlap_ratio = common_count / len(target_tokens) if target_tokens else 0.0
    token_jaccard_ratio = (
        common_count / len(candidate_tokens | target_tokens)
        if candidate_tokens and target_tokens
        else 0.0
    )
    target_coverage_ratio = len(normalized_candidate) / max(len(normalized_target), 1)

    is_exact = normalized_candidate == normalized_target
    is_contained = (not is_exact) and normalized_candidate in normalized_target
    token_branch = common_count >= 3 and token_overlap_ratio >= 0.85 and target_coverage_ratio >= 0.65

    # Lever C (spec 029): the only accept path that depends on the O(L^2) char ratio() is the
    # `sequence_ratio >= 0.92` branch. The exact, substring, and token-overlap branches are decided
    # from cheap comparisons above. So when none of those can fire, gate ratio() behind its
    # guaranteed upper bound real_quick_ratio(): if that is below 0.92, sequence_ratio cannot reach
    # 0.92 either and no evidence can be produced. Provably identical (never drops a real match).
    matcher = SequenceMatcher(None, normalized_candidate, normalized_target)
    if not is_exact and not is_contained and not token_branch and matcher.real_quick_ratio() < 0.92:
        return None
    sequence_ratio = matcher.ratio()

    evidence_type: str | None = None
    if is_exact:
        evidence_type = "exact"
    elif is_contained:
        if source_format_role == "heading":
            evidence_type = "heading_exact_contained"
        elif target_coverage_ratio >= 0.65:
            evidence_type = "exact_contained"
    elif sequence_ratio >= 0.92 or token_branch:
        evidence_type = "bounded_fuzzy"

    if evidence_type is None:
        return None

    return {
        "evidence_type": evidence_type,
        "score": round(max(sequence_ratio, token_overlap_ratio), 4),
        "sequence_ratio": round(sequence_ratio, 4),
        "token_overlap_ratio": round(token_overlap_ratio, 4),
        "target_token_overlap_ratio": round(target_token_overlap_ratio, 4),
        "token_jaccard_ratio": round(token_jaccard_ratio, 4),
        "target_coverage_ratio": round(target_coverage_ratio, 4),
        "common_token_count": common_count,
        "candidate_token_count": len(candidate_tokens),
        "candidate_char_count": len(normalized_candidate),
    }


_ROLE_UNRESOLVED = object()


class _TargetRoleResolver:
    """Per-call memo of target-paragraph role resolution, keyed by target index (spec 029, Lever F).

    ``_target_format_role``, ``_target_has_heading_format`` and ``_extract_target_heading_level`` are
    pure functions of the target ``Paragraph``, and ``target_paragraphs`` is not mutated during
    ``_map_source_target_paragraphs``. Resolving each target's role/heading-level/has-heading-format
    at most once per call and reusing it across all passes/source iterations collapses the O(S*T)
    role re-resolution (the dominant offline cost) to O(T), while remaining byte-identical (same
    paragraph -> same value). This memo is deliberately local to a single mapping call and never a
    module global: its keys index one specific ``target_paragraphs`` list.
    """

    __slots__ = ("_targets", "_format_role_by_index", "_heading_level_by_index", "_has_heading_by_index")

    def __init__(self, target_paragraphs: Sequence[Paragraph]) -> None:
        self._targets = target_paragraphs
        self._format_role_by_index: dict[int, str] = {}
        self._heading_level_by_index: dict[int, int | None] = {}
        self._has_heading_by_index: dict[int, bool] = {}

    def heading_level(self, target_index: int) -> int | None:
        cached = self._heading_level_by_index.get(target_index, _ROLE_UNRESOLVED)
        if cached is _ROLE_UNRESOLVED:
            cached = _extract_target_heading_level(self._targets[target_index])
            self._heading_level_by_index[target_index] = cached
        return cast("int | None", cached)

    def has_heading_format(self, target_index: int) -> bool:
        cached = self._has_heading_by_index.get(target_index, _ROLE_UNRESOLVED)
        if cached is _ROLE_UNRESOLVED:
            cached = self.heading_level(target_index) is not None
            self._has_heading_by_index[target_index] = cached
        return cast(bool, cached)

    def format_role(self, target_index: int) -> str:
        cached = self._format_role_by_index.get(target_index, _ROLE_UNRESOLVED)
        if cached is _ROLE_UNRESOLVED:
            # Mirrors _target_format_role exactly, but reuses the shared heading-level memo so a
            # target's heading level is resolved at most once per call. Keep in sync with it.
            paragraph = self._targets[target_index]
            if IMAGE_PLACEHOLDER_PATTERN.search(paragraph.text):
                cached = "image"
            elif self.heading_level(target_index) is not None:
                cached = "heading"
            elif detect_explicit_list_kind(paragraph.text) is not None:
                cached = "list"
            else:
                cached = "body"
            self._format_role_by_index[target_index] = cached
        return cast(str, cached)


def _registry_mapping_role_compatible(
    source_format_role: str, target_role: str, target_has_heading_format: bool
) -> bool:
    if source_format_role == "heading":
        return target_has_heading_format
    if source_format_role in {"body", "toc", "epigraph", "attribution", "dedication"}:
        return target_role != "heading"
    if source_format_role == "list":
        return target_role in {"body", "list"}
    if source_format_role == "caption":
        return target_role in {"body", "caption"}
    return target_role != "heading"


def _try_register_bounded_registry_mapping(
    source_index: int,
    source_paragraph: ParagraphUnit,
    target_paragraphs: Sequence[Paragraph],
    generated_registry_by_id: Mapping[str, Mapping[str, object]],
    *,
    role_resolver: "_TargetRoleResolver",
    mapped_target_by_source: dict[int, int],
    strategy_by_source: dict[int, str],
    available_target_indexes: set[int],
    target_window: int = 32,
) -> bool:
    if source_index in mapped_target_by_source or source_paragraph.role == "image":
        return False
    paragraph_id = source_paragraph.paragraph_id
    if not paragraph_id:
        return False
    generated_text = _generated_registry_text(generated_registry_by_id.get(paragraph_id))
    if not generated_text:
        return False

    source_format_role = _source_format_role(source_paragraph)
    registry_candidates = [
        candidate
        for candidate in _build_generated_registry_candidates(source_paragraph, generated_text)
        if len(candidate) >= 8 or (source_format_role == "heading" and len(candidate) >= 4)
    ]
    if not registry_candidates:
        return False

    scored: list[tuple[float, int, dict[str, object]]] = []
    for target_index in range(
        max(0, source_index - target_window),
        min(len(target_paragraphs), source_index + target_window + 1),
    ):
        if target_index not in available_target_indexes:
            continue
        if abs(target_index - source_index) > target_window:
            continue
        target_paragraph = target_paragraphs[target_index]
        target_text = target_paragraph.text.strip()
        if not target_text or IMAGE_PLACEHOLDER_PATTERN.search(target_text):
            continue
        if not _registry_mapping_role_compatible(
            source_format_role,
            role_resolver.format_role(target_index),
            role_resolver.has_heading_format(target_index),
        ):
            continue

        best_evidence: dict[str, object] | None = None
        for candidate in registry_candidates:
            evidence = _registry_candidate_mapping_evidence(
                candidate,
                target_text,
                source_format_role=source_format_role,
            )
            if evidence is None:
                continue
            if best_evidence is None or (
                float(evidence["score"]),
                float(evidence["target_coverage_ratio"]),
                int(evidence["candidate_char_count"]),
            ) > (
                float(best_evidence["score"]),
                float(best_evidence["target_coverage_ratio"]),
                int(best_evidence["candidate_char_count"]),
            ):
                best_evidence = evidence

        if best_evidence is None:
            continue
        rank_score = (
            float(best_evidence["score"])
            + min(float(best_evidence["target_coverage_ratio"]), 1.0)
            + min(int(best_evidence["candidate_char_count"]) / 1000.0, 0.5)
        )
        scored.append((rank_score, target_index, best_evidence))

    if not scored:
        return False

    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    best_score, best_target_index, best_evidence = scored[0]
    if len(scored) > 1 and best_score - scored[1][0] < 0.08:
        return False

    if source_format_role == "heading":
        strategy = "bounded_registry_heading_containment"
    else:
        strategy = "bounded_registry_fuzzy"
    _register_mapping(
        source_index,
        best_target_index,
        strategy,
        mapped_target_by_source=mapped_target_by_source,
        strategy_by_source=strategy_by_source,
        available_target_indexes=available_target_indexes,
    )
    return True


def _projected_registry_text_floor_satisfied(evidence: Mapping[str, object]) -> bool:
    evidence_type = str(evidence.get("evidence_type") or "")
    if evidence_type in {"exact", "exact_contained", "heading_exact_contained"}:
        return True

    token_jaccard_ratio = float(evidence.get("token_jaccard_ratio", 0.0) or 0.0)
    token_overlap_ratio = float(evidence.get("token_overlap_ratio", 0.0) or 0.0)
    target_token_overlap_ratio = float(evidence.get("target_token_overlap_ratio", 0.0) or 0.0)
    sequence_ratio = float(evidence.get("sequence_ratio", 0.0) or 0.0)
    target_coverage_ratio = float(evidence.get("target_coverage_ratio", 0.0) or 0.0)
    return token_jaccard_ratio >= 0.5 or (
        token_overlap_ratio >= 0.85
        and target_token_overlap_ratio >= 0.5
        and sequence_ratio >= 0.85
        and target_coverage_ratio >= 0.65
    )


def _project_target_index_from_mapped_neighbors(
    source_index: int,
    mapped_target_by_source: Mapping[int, int],
) -> tuple[float | None, tuple[int, int] | None, tuple[int, int] | None]:
    previous_anchor: tuple[int, int] | None = None
    next_anchor: tuple[int, int] | None = None
    for mapped_source_index, mapped_target_index in sorted(mapped_target_by_source.items()):
        if mapped_source_index < source_index:
            previous_anchor = (mapped_source_index, mapped_target_index)
        elif mapped_source_index > source_index:
            next_anchor = (mapped_source_index, mapped_target_index)
            break

    if previous_anchor is not None and next_anchor is not None:
        previous_source, previous_target = previous_anchor
        next_source, next_target = next_anchor
        source_span = next_source - previous_source
        if source_span > 0:
            ratio = (source_index - previous_source) / source_span
            return previous_target + ((next_target - previous_target) * ratio), previous_anchor, next_anchor

    if previous_anchor is not None:
        previous_source, previous_target = previous_anchor
        return float(previous_target + (source_index - previous_source)), previous_anchor, None
    if next_anchor is not None:
        next_source, next_target = next_anchor
        return float(next_target - (next_source - source_index)), None, next_anchor
    return None, None, None


def _try_register_projected_registry_mapping(
    source_index: int,
    source_paragraph: ParagraphUnit,
    target_paragraphs: Sequence[Paragraph],
    generated_registry_by_id: Mapping[str, Mapping[str, object]],
    *,
    role_resolver: "_TargetRoleResolver",
    mapped_target_by_source: dict[int, int],
    strategy_by_source: dict[int, str],
    available_target_indexes: set[int],
    projected_window: int = 18,
) -> bool:
    if source_index in mapped_target_by_source or source_paragraph.role == "image":
        return False
    paragraph_id = source_paragraph.paragraph_id
    if not paragraph_id:
        return False
    generated_text = _generated_registry_text(generated_registry_by_id.get(paragraph_id))
    if not generated_text:
        return False

    projected_target_index, previous_anchor, next_anchor = _project_target_index_from_mapped_neighbors(
        source_index,
        mapped_target_by_source,
    )
    if projected_target_index is None:
        return False

    source_format_role = _source_format_role(source_paragraph)
    registry_candidates = [
        candidate
        for candidate in _build_generated_registry_candidates(source_paragraph, generated_text)
        if len(candidate) >= 8 or (source_format_role == "heading" and len(candidate) >= 4)
    ]
    if not registry_candidates:
        return False

    scored: list[tuple[float, int, dict[str, object]]] = []
    # Window [projected-W, projected+W] on the contiguous ascending index range; the
    # int() floor plus +/-1 padding keeps this a strict superset of the abs() guard
    # below (which still filters exactly), so the processed set is unchanged.
    _projected_floor = int(projected_target_index)
    for target_index in range(
        max(0, _projected_floor - projected_window - 1),
        min(len(target_paragraphs), _projected_floor + projected_window + 2),
    ):
        if target_index not in available_target_indexes:
            continue
        if abs(target_index - projected_target_index) > projected_window:
            continue
        if previous_anchor is not None and target_index < previous_anchor[1]:
            continue
        if next_anchor is not None and target_index > next_anchor[1]:
            continue
        target_paragraph = target_paragraphs[target_index]
        target_text = target_paragraph.text.strip()
        if not target_text or IMAGE_PLACEHOLDER_PATTERN.search(target_text):
            continue
        if not _registry_mapping_role_compatible(
            source_format_role,
            role_resolver.format_role(target_index),
            role_resolver.has_heading_format(target_index),
        ):
            continue

        best_evidence: dict[str, object] | None = None
        for candidate in registry_candidates:
            evidence = _registry_candidate_mapping_evidence(
                candidate,
                target_text,
                source_format_role=source_format_role,
            )
            if evidence is None:
                continue
            if not _projected_registry_text_floor_satisfied(evidence):
                continue
            if best_evidence is None or (
                float(evidence["score"]),
                float(evidence["target_coverage_ratio"]),
                int(evidence["candidate_char_count"]),
            ) > (
                float(best_evidence["score"]),
                float(best_evidence["target_coverage_ratio"]),
                int(best_evidence["candidate_char_count"]),
            ):
                best_evidence = evidence

        if best_evidence is None:
            continue
        candidate_token_count = int(best_evidence.get("candidate_token_count", 0))
        if candidate_token_count < 3 and (previous_anchor is None or next_anchor is None):
            continue
        projected_distance = abs(target_index - projected_target_index)
        rank_score = (
            float(best_evidence["score"])
            + min(float(best_evidence["target_coverage_ratio"]), 1.0)
            + max(0.0, (projected_window - projected_distance) / max(projected_window, 1)) * 0.25
        )
        scored.append((rank_score, target_index, best_evidence))

    if not scored:
        return False

    scored.sort(key=lambda item: (item[0], -abs(item[1] - projected_target_index)), reverse=True)
    best_score, best_target_index, _best_evidence = scored[0]
    if len(scored) > 1 and best_score - scored[1][0] < 0.08:
        return False

    _register_mapping(
        source_index,
        best_target_index,
        "projected_registry_fuzzy",
        mapped_target_by_source=mapped_target_by_source,
        strategy_by_source=strategy_by_source,
        available_target_indexes=available_target_indexes,
    )
    return True


def _try_register_unique_registry_text_floor_mapping(
    source_index: int,
    source_paragraph: ParagraphUnit,
    target_paragraphs: Sequence[Paragraph],
    generated_registry_by_id: Mapping[str, Mapping[str, object]],
    *,
    role_resolver: "_TargetRoleResolver",
    mapped_target_by_source: dict[int, int],
    strategy_by_source: dict[int, str],
    available_target_indexes: set[int],
) -> bool:
    if source_index in mapped_target_by_source or source_paragraph.role == "image":
        return False
    paragraph_id = source_paragraph.paragraph_id
    if not paragraph_id:
        return False
    generated_text = _generated_registry_text(generated_registry_by_id.get(paragraph_id))
    if not generated_text:
        return False

    source_format_role = _source_format_role(source_paragraph)
    registry_candidates = [
        candidate
        for candidate in _build_generated_registry_candidates(source_paragraph, generated_text)
        if (
            len(candidate) >= 24
            and len(_token_set(candidate)) >= 5
        )
        or (
            source_format_role == "heading"
            and len(candidate) >= 4
            and len(_token_set(candidate)) >= 1
        )
    ]
    if not registry_candidates:
        return False

    scored: list[tuple[float, int, dict[str, object]]] = []
    for target_index in range(len(target_paragraphs)):
        if target_index not in available_target_indexes:
            continue
        target_paragraph = target_paragraphs[target_index]
        target_text = target_paragraph.text.strip()
        if not target_text or IMAGE_PLACEHOLDER_PATTERN.search(target_text):
            continue
        if not _registry_mapping_role_compatible(
            source_format_role,
            role_resolver.format_role(target_index),
            role_resolver.has_heading_format(target_index),
        ):
            continue

        best_evidence: dict[str, object] | None = None
        for candidate in registry_candidates:
            evidence = _registry_candidate_mapping_evidence(
                candidate,
                target_text,
                source_format_role=source_format_role,
            )
            if evidence is None:
                continue
            if _mapping_text_floor_is_bad(_mapping_text_floor_quality(candidate, target_text)):
                continue
            if best_evidence is None or (
                float(evidence["score"]),
                float(evidence["target_coverage_ratio"]),
                int(evidence["candidate_char_count"]),
            ) > (
                float(best_evidence["score"]),
                float(best_evidence["target_coverage_ratio"]),
                int(best_evidence["candidate_char_count"]),
            ):
                best_evidence = evidence

        if best_evidence is None:
            continue
        rank_score = (
            float(best_evidence["score"])
            + min(float(best_evidence["target_coverage_ratio"]), 1.0)
            + min(int(best_evidence["candidate_char_count"]) / 1000.0, 0.5)
        )
        scored.append((rank_score, target_index, best_evidence))

    if len(scored) != 1:
        return False

    _register_mapping(
        source_index,
        scored[0][1],
        "registry_free_target_text_floor",
        mapped_target_by_source=mapped_target_by_source,
        strategy_by_source=strategy_by_source,
        available_target_indexes=available_target_indexes,
    )
    return True


def _note_marker_key(text: str) -> str:
    normalized = _normalize_text_for_mapping(text).strip(" \t\r\n\"'“”‘’«»()[]{}:;,.!?-–—")
    return normalized if normalized in {"ibid", "там же"} else ""


def _register_repeated_note_sequence_mappings(
    source_paragraphs: Sequence[ParagraphUnit],
    target_paragraphs: Sequence[Paragraph],
    generated_registry_by_id: Mapping[str, Mapping[str, object]],
    *,
    role_resolver: "_TargetRoleResolver",
    mapped_target_by_source: dict[int, int],
    strategy_by_source: dict[int, str],
    available_target_indexes: set[int],
) -> None:
    source_indexes_by_key: dict[str, list[int]] = {}
    for source_index, source_paragraph in enumerate(source_paragraphs):
        if source_index in mapped_target_by_source or source_paragraph.role == "image":
            continue
        if not _is_list_source_paragraph(source_paragraph):
            continue
        paragraph_id = source_paragraph.paragraph_id
        if not paragraph_id:
            continue
        generated_text = _generated_registry_text(generated_registry_by_id.get(paragraph_id))
        if not generated_text:
            continue
        note_key = next(
            (
                key
                for candidate in _build_generated_registry_candidates(source_paragraph, generated_text)
                if (key := _note_marker_key(candidate))
            ),
            "",
        )
        if not note_key:
            continue
        source_indexes_by_key.setdefault(note_key, []).append(source_index)

    if not source_indexes_by_key:
        return

    target_indexes_by_key: dict[str, list[int]] = {}
    for target_index in range(len(target_paragraphs)):
        if target_index not in available_target_indexes:
            continue
        if target_index >= len(target_paragraphs):
            continue
        target_paragraph = target_paragraphs[target_index]
        target_text = target_paragraph.text.strip()
        if not target_text or IMAGE_PLACEHOLDER_PATTERN.search(target_text):
            continue
        note_key = _note_marker_key(target_text)
        if not note_key:
            continue
        target_indexes_by_key.setdefault(note_key, []).append(target_index)

    for note_key, source_indexes in sorted(source_indexes_by_key.items()):
        target_indexes = target_indexes_by_key.get(note_key, [])
        if len(source_indexes) != len(target_indexes):
            continue
        for source_index, target_index in zip(sorted(source_indexes), sorted(target_indexes), strict=True):
            source_format_role = _source_format_role(source_paragraphs[source_index])
            if not _registry_mapping_role_compatible(
                source_format_role,
                role_resolver.format_role(target_index),
                role_resolver.has_heading_format(target_index),
            ):
                break
        else:
            for source_index, target_index in zip(sorted(source_indexes), sorted(target_indexes), strict=True):
                _register_mapping(
                    source_index,
                    target_index,
                    "registry_repeated_note_sequence",
                    mapped_target_by_source=mapped_target_by_source,
                    strategy_by_source=strategy_by_source,
                    available_target_indexes=available_target_indexes,
                )


def _generated_registry_target_text_compatible(
    source_paragraph: ParagraphUnit,
    target_paragraph: Paragraph,
    registry_entry: Mapping[str, object] | None,
    *,
    role_resolver: "_TargetRoleResolver",
    target_index: int,
) -> bool:
    generated_text = _generated_registry_text(registry_entry)
    if not generated_text:
        return False
    source_format_role = _source_format_role(source_paragraph)
    if not _registry_mapping_role_compatible(
        source_format_role,
        role_resolver.format_role(target_index),
        role_resolver.has_heading_format(target_index),
    ):
        return False
    return any(
        _registry_candidate_mapping_evidence(
            candidate,
            target_paragraph.text,
            source_format_role=source_format_role,
        )
        is not None
        for candidate in _build_generated_registry_candidates(source_paragraph, generated_text)
    )


def _register_mapping(
    source_index: int,
    target_index: int,
    strategy: str,
    *,
    mapped_target_by_source: dict[int, int],
    strategy_by_source: dict[int, str],
    available_target_indexes: set[int],
) -> None:
    mapped_target_by_source[source_index] = target_index
    strategy_by_source[source_index] = strategy
    available_target_indexes.discard(target_index)


def _build_generated_registry_by_paragraph_id(
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> dict[str, dict[str, object]]:
    registry_by_id: dict[str, dict[str, object]] = {}
    if not generated_paragraph_registry:
        return registry_by_id

    for entry in generated_paragraph_registry:
        paragraph_id = entry.get("paragraph_id")
        text = entry.get("text")
        if isinstance(paragraph_id, str) and paragraph_id and isinstance(text, str) and text.strip():
            payload: dict[str, object] = {"text": text}
            block_index = entry.get("block_index")
            if isinstance(block_index, int) and not isinstance(block_index, bool):
                payload["block_index"] = block_index
            if bool(entry.get("controlled_fallback")):
                payload["controlled_fallback"] = True
                fallback_kind = entry.get("controlled_fallback_kind")
                if isinstance(fallback_kind, str) and fallback_kind:
                    payload["controlled_fallback_kind"] = fallback_kind
            merged_ids = entry.get("merged_paragraph_ids")
            if isinstance(merged_ids, Sequence) and not isinstance(merged_ids, (str, bytes)):
                payload["merged_paragraph_ids"] = [value for value in merged_ids if isinstance(value, str) and value]
            target_indexes = entry.get("target_paragraph_indexes")
            if isinstance(target_indexes, Sequence) and not isinstance(target_indexes, (str, bytes)):
                payload["target_paragraph_indexes"] = [
                    int(value)
                    for value in target_indexes
                    if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
                ]
            registry_by_id[paragraph_id] = payload
    return registry_by_id


def _generated_registry_text(entry: Mapping[str, object] | None) -> str:
    if not isinstance(entry, Mapping):
        return ""
    text = entry.get("text")
    return text if isinstance(text, str) else ""


def _generated_registry_merged_ids(entry: Mapping[str, object] | None) -> list[str]:
    if not isinstance(entry, Mapping):
        return []
    merged_ids = entry.get("merged_paragraph_ids")
    if not isinstance(merged_ids, Sequence) or isinstance(merged_ids, (str, bytes)):
        return []
    return [value for value in merged_ids if isinstance(value, str) and value]


def _generated_registry_target_indexes(entry: Mapping[str, object] | None) -> list[int]:
    if not isinstance(entry, Mapping):
        return []
    target_indexes = entry.get("target_paragraph_indexes")
    if not isinstance(target_indexes, Sequence) or isinstance(target_indexes, (str, bytes)):
        return []
    indexes: list[int] = []
    for value in target_indexes:
        if isinstance(value, int):
            indexes.append(value)
        elif isinstance(value, str) and value.isdigit():
            indexes.append(int(value))
    return indexes


def _collect_accepted_split_targets(
    source_paragraphs: list[ParagraphUnit],
    target_paragraphs: list[Paragraph],
    mapped_target_by_source: Mapping[int, int],
    generated_registry_by_id: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    accepted_targets: list[dict[str, object]] = []
    accepted_target_indexes: set[int] = set()

    for source_index, target_index in sorted(mapped_target_by_source.items()):
        if target_index <= 0:
            continue

        source_paragraph = source_paragraphs[source_index]
        paragraph_id = source_paragraph.paragraph_id
        if not paragraph_id:
            continue

        generated_text = _generated_registry_text(generated_registry_by_id.get(paragraph_id))
        if not generated_text:
            continue

        generated_lines = [line.strip() for line in generated_text.splitlines() if line.strip()]
        if len(generated_lines) < 2:
            continue

        heading_line = generated_lines[0]
        if not MARKDOWN_HEADING_LINE_PATTERN.match(heading_line):
            continue

        body_lines = [line for line in generated_lines[1:] if not MARKDOWN_HEADING_LINE_PATTERN.match(line)]
        if not body_lines:
            continue

        candidate_target_index = target_index - 1
        if candidate_target_index in accepted_target_indexes:
            continue

        heading_target = target_paragraphs[candidate_target_index]
        if _extract_target_heading_level(heading_target) is None:
            continue

        body_target = target_paragraphs[target_index]
        normalized_heading_line = _normalize_text_for_mapping(heading_line)
        normalized_heading_target = _normalize_text_for_mapping(heading_target.text)
        normalized_body_text = _normalize_text_for_mapping(" ".join(body_lines))
        normalized_body_target = _normalize_text_for_mapping(body_target.text)

        if not normalized_heading_line or normalized_heading_line != normalized_heading_target:
            continue
        if not normalized_body_text or normalized_body_text != normalized_body_target:
            continue

        accepted_target_indexes.add(candidate_target_index)
        accepted_targets.append(
            {
                "target_index": candidate_target_index,
                "derived_from_source_index": source_index,
                "kind": "split_heading_prefix",
                "heading_level": _extract_target_heading_level(heading_target),
                "target_text_preview": _paragraph_preview(heading_target.text),
                "source_text_preview": _paragraph_preview(source_paragraph.text),
            }
        )

    return accepted_targets


def _collect_accepted_merged_sources(
    source_paragraphs: list[ParagraphUnit],
    target_paragraphs: list[Paragraph],
    mapped_target_by_source: Mapping[int, int],
) -> list[dict[str, object]]:
    accepted_sources: list[dict[str, object]] = []
    for source_index, target_index in sorted(mapped_target_by_source.items()):
        source_paragraph = source_paragraphs[source_index]
        if len(source_paragraph.origin_raw_indexes) <= 1:
            continue
        accepted_sources.append(
            {
                "logical_paragraph_id": source_paragraph.paragraph_id or f"p{source_index:04d}",
                "origin_raw_indexes": list(source_paragraph.origin_raw_indexes),
                "accepted_merged_sources_count": len(source_paragraph.origin_raw_indexes),
                "dominant_raw_index": source_paragraph.origin_raw_indexes[0],
                "kind": source_paragraph.boundary_source or "false_paragraph_boundary_merge",
                "boundary_confidence": source_paragraph.boundary_confidence,
                "boundary_decision_class": "medium_accepted" if source_paragraph.boundary_confidence == "medium" else "high",
                "boundary_rationale": source_paragraph.boundary_rationale,
                "target_index": target_index,
                "target_text_preview": _paragraph_preview(target_paragraphs[target_index].text),
                "source_text_preview": _paragraph_preview(source_paragraph.text),
            }
        )
    return accepted_sources


def _source_paragraph_aggregation_kind(paragraph: ParagraphUnit) -> str | None:
    structural_role = str(getattr(paragraph, "structural_role", "") or "").strip().lower()
    role = str(getattr(paragraph, "role", "") or "").strip().lower()
    if structural_role == "toc_entry":
        return "toc_entry"
    if role == "list" or structural_role in {"list", "list_item"} or getattr(paragraph, "list_kind", None):
        return "list_item"
    return None


def _collect_accepted_aggregated_sources(
    source_paragraphs: list[ParagraphUnit],
    target_paragraphs: list[Paragraph],
    mapped_target_by_source: Mapping[int, int],
    generated_registry_by_id: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    accepted_sources: list[dict[str, object]] = []
    mapped_source_indexes = set(mapped_target_by_source)
    accepted_source_indexes: set[int] = set()
    source_index_by_id = {
        (paragraph.paragraph_id or f"p{index:04d}"): index for index, paragraph in enumerate(source_paragraphs)
    }

    for anchor_source_index, target_index in sorted(mapped_target_by_source.items()):
        if target_index < 0 or target_index >= len(target_paragraphs):
            continue
        anchor_source = source_paragraphs[anchor_source_index]
        anchor_paragraph_id = anchor_source.paragraph_id or f"p{anchor_source_index:04d}"
        merged_ids = _generated_registry_merged_ids(generated_registry_by_id.get(anchor_paragraph_id))
        for merged_id in merged_ids:
            if merged_id == anchor_paragraph_id:
                continue
            source_index = source_index_by_id.get(merged_id)
            if source_index is None:
                continue
            if source_index in mapped_source_indexes or source_index in accepted_source_indexes:
                continue

            source_paragraph = source_paragraphs[source_index]
            accepted_source_indexes.add(source_index)
            aggregation_kind = _source_paragraph_aggregation_kind(source_paragraph)
            accepted_sources.append(
                {
                    "paragraph_id": merged_id,
                    "source_index": source_index,
                    "target_index": target_index,
                    "kind": (
                        f"{aggregation_kind}_generated_registry_target_aggregation"
                        if aggregation_kind is not None
                        else "generated_registry_target_aggregation"
                    ),
                    "anchor_source_index": anchor_source_index,
                    "anchor_paragraph_id": anchor_paragraph_id,
                    "target_text_preview": _paragraph_preview(target_paragraphs[target_index].text),
                    "source_text_preview": _paragraph_preview(source_paragraph.text),
                }
            )

    for anchor_source_index, target_index in sorted(mapped_target_by_source.items()):
        if target_index < 0 or target_index >= len(target_paragraphs):
            continue
        anchor_source = source_paragraphs[anchor_source_index]
        if anchor_source.role != "image":
            continue
        target_text = target_paragraphs[target_index].text
        if not IMAGE_PLACEHOLDER_PATTERN.search(target_text):
            continue
        if not _target_has_heading_format(target_paragraphs[target_index]):
            continue
        target_normalized = _normalize_text_for_mapping(target_text)
        if not target_normalized:
            continue

        for source_index in range(anchor_source_index + 1, min(len(source_paragraphs), anchor_source_index + 4)):
            if source_index in mapped_source_indexes or source_index in accepted_source_indexes:
                continue
            source_paragraph = source_paragraphs[source_index]
            structural_role = str(getattr(source_paragraph, "structural_role", "") or "").strip().lower()
            role = str(getattr(source_paragraph, "role", "") or "").strip().lower()
            if role != "heading" and structural_role != "heading":
                break

            paragraph_id = source_paragraph.paragraph_id or f"p{source_index:04d}"
            generated_text = _generated_registry_text(generated_registry_by_id.get(paragraph_id))
            if not generated_text:
                continue
            matched_candidate = next(
                (
                    candidate
                    for candidate in _build_generated_registry_candidates(source_paragraph, generated_text)
                    if len(candidate) >= 5 and candidate in target_normalized
                ),
                "",
            )
            if not matched_candidate:
                continue

            accepted_source_indexes.add(source_index)
            accepted_sources.append(
                {
                    "paragraph_id": paragraph_id,
                    "source_index": source_index,
                    "target_index": target_index,
                    "kind": "image_heading_shared_target",
                    "anchor_source_index": anchor_source_index,
                    "anchor_paragraph_id": anchor_source.paragraph_id or f"p{anchor_source_index:04d}",
                    "target_text_preview": _paragraph_preview(target_text),
                    "source_text_preview": _paragraph_preview(source_paragraph.text),
                }
            )

    for anchor_source_index, target_index in sorted(mapped_target_by_source.items()):
        if target_index < 0 or target_index >= len(target_paragraphs):
            continue
        if not _target_has_heading_format(target_paragraphs[target_index]):
            continue
        anchor_source = source_paragraphs[anchor_source_index]
        anchor_structural_role = str(getattr(anchor_source, "structural_role", "") or "").strip().lower()
        anchor_role = str(getattr(anchor_source, "role", "") or "").strip().lower()
        if anchor_role != "heading" and anchor_structural_role != "heading":
            continue

        target_normalized = _normalize_text_for_mapping(target_paragraphs[target_index].text)
        if not target_normalized:
            continue

        window_start = max(0, anchor_source_index - 3)
        window_end = min(len(source_paragraphs), anchor_source_index + 4)
        for source_index in range(window_start, window_end):
            if source_index == anchor_source_index:
                continue
            if source_index in mapped_source_indexes or source_index in accepted_source_indexes:
                continue
            source_paragraph = source_paragraphs[source_index]
            structural_role = str(getattr(source_paragraph, "structural_role", "") or "").strip().lower()
            role = str(getattr(source_paragraph, "role", "") or "").strip().lower()
            if role != "heading" and structural_role != "heading":
                continue

            paragraph_id = source_paragraph.paragraph_id or f"p{source_index:04d}"
            generated_text = _generated_registry_text(generated_registry_by_id.get(paragraph_id))
            if not generated_text:
                continue
            matched_candidate = next(
                (
                    candidate
                    for candidate in _build_generated_registry_candidates(source_paragraph, generated_text)
                    if len(candidate) >= 5 and candidate in target_normalized
                ),
                "",
            )
            if not matched_candidate:
                continue

            accepted_source_indexes.add(source_index)
            accepted_sources.append(
                {
                    "paragraph_id": paragraph_id,
                    "source_index": source_index,
                    "target_index": target_index,
                    "kind": "heading_shared_target",
                    "anchor_source_index": anchor_source_index,
                    "anchor_paragraph_id": anchor_source.paragraph_id or f"p{anchor_source_index:04d}",
                    "target_text_preview": _paragraph_preview(target_paragraphs[target_index].text),
                    "source_text_preview": _paragraph_preview(source_paragraph.text),
                }
            )

    for anchor_source_index, target_index in sorted(mapped_target_by_source.items()):
        if target_index < 0 or target_index >= len(target_paragraphs):
            continue
        anchor_source = source_paragraphs[anchor_source_index]
        aggregation_kind = _source_paragraph_aggregation_kind(anchor_source)
        if aggregation_kind is None:
            continue

        target_normalized = _normalize_text_for_mapping(target_paragraphs[target_index].text)
        if not target_normalized:
            continue

        for source_index, source_paragraph in enumerate(source_paragraphs):
            if source_index in mapped_source_indexes or source_index in accepted_source_indexes:
                continue
            if abs(source_index - anchor_source_index) > 12:
                continue
            if _source_paragraph_aggregation_kind(source_paragraph) != aggregation_kind:
                continue

            paragraph_id = source_paragraph.paragraph_id or f"p{source_index:04d}"
            candidate_texts = _build_generated_registry_candidates(
                source_paragraph,
                _generated_registry_text(generated_registry_by_id.get(paragraph_id)) or source_paragraph.text,
            )
            matched_candidate = next(
                (
                    candidate
                    for candidate in candidate_texts
                    if len(candidate) >= 8 and candidate != target_normalized and candidate in target_normalized
                ),
                "",
            )
            if not matched_candidate:
                continue

            accepted_source_indexes.add(source_index)
            accepted_sources.append(
                {
                    "paragraph_id": paragraph_id,
                    "source_index": source_index,
                    "target_index": target_index,
                    "kind": f"{aggregation_kind}_target_aggregation",
                    "anchor_source_index": anchor_source_index,
                    "target_text_preview": _paragraph_preview(target_paragraphs[target_index].text),
                    "source_text_preview": _paragraph_preview(source_paragraph.text),
                }
            )

    return accepted_sources


def _try_register_local_gap_fallback(
    source_index: int,
    source_paragraphs: list[ParagraphUnit],
    target_paragraphs: list[Paragraph],
    *,
    role_resolver: "_TargetRoleResolver",
    mapped_target_by_source: dict[int, int],
    strategy_by_source: dict[int, str],
    available_target_indexes: set[int],
) -> bool:
    if source_index <= 0 or source_index + 1 >= len(source_paragraphs):
        return False
    if source_index in mapped_target_by_source:
        return False

    previous_index = source_index - 1
    next_index = source_index + 1
    previous_target_index = mapped_target_by_source.get(previous_index)
    next_target_index = mapped_target_by_source.get(next_index)
    if previous_target_index is None or next_target_index is None:
        return False
    if next_target_index - previous_target_index != 2:
        return False

    candidate_index = previous_target_index + 1
    if candidate_index not in available_target_indexes or candidate_index >= len(target_paragraphs):
        return False

    source_paragraph = source_paragraphs[source_index]
    structural_role = str(getattr(source_paragraph, "structural_role", "") or "").strip().lower()
    candidate_target = target_paragraphs[candidate_index]
    candidate_text = candidate_target.text.strip()
    if not candidate_text or IMAGE_PLACEHOLDER_PATTERN.search(candidate_text):
        return False

    if structural_role == "heading":
        if role_resolver.heading_level(candidate_index) is None:
            return False
        strategy = "local_gap_heading_fallback"
    elif structural_role == "toc_entry":
        previous_source = source_paragraphs[previous_index]
        next_source = source_paragraphs[next_index]
        if not (_is_toc_source_paragraph(previous_source) and _is_toc_source_paragraph(next_source)):
            return False
        strategy = "local_gap_toc_fallback"
    else:
        return False

    _register_mapping(
        source_index,
        candidate_index,
        strategy,
        mapped_target_by_source=mapped_target_by_source,
        strategy_by_source=strategy_by_source,
        available_target_indexes=available_target_indexes,
    )
    return True


def _count_inline_emphasis_spans(text: str) -> tuple[int, int]:
    """Return ``(bold_span_count, italic_span_count)`` for inline markdown emphasis."""
    if not text:
        return 0, 0
    triple_matches = _EMPHASIS_TRIPLE_SPAN_PATTERN.findall(text)
    bold = len(triple_matches)
    italic = len(triple_matches)
    remaining = _EMPHASIS_TRIPLE_SPAN_PATTERN.sub(" ", text)
    bold += len(_EMPHASIS_BOLD_SPAN_PATTERN.findall(remaining))
    remaining = _EMPHASIS_BOLD_SPAN_PATTERN.sub(" ", remaining)
    italic += len(_EMPHASIS_ASTERISK_ITALIC_SPAN_PATTERN.findall(remaining))
    italic += len(_EMPHASIS_UNDERSCORE_ITALIC_SPAN_PATTERN.findall(remaining))
    return bold, italic


def _count_source_emphasis(source_paragraphs: Sequence[ParagraphUnit]) -> tuple[int, int, bool]:
    """Count source bold/italic signals, excluding heading-role paragraphs (FR-002).

    Prefers the PDF character-run signal (``pdf_emphasis_runs``); where that is absent,
    counts inline markdown spans in the paragraph text. ``has_signal`` is False only when
    NO paragraph carried either signal (spec FR-006 — no signal, not-measured).
    """
    source_bold = 0
    source_italic = 0
    has_signal = False
    for paragraph in source_paragraphs:
        if str(getattr(paragraph, "role", "") or "").strip().lower() == "heading":
            continue
        emphasis_runs = getattr(paragraph, "pdf_emphasis_runs", None) or []
        if emphasis_runs:
            has_signal = True
            for _run_text, run_bold, run_italic in emphasis_runs:
                if run_bold:
                    source_bold += 1
                if run_italic:
                    source_italic += 1
            continue
        bold_spans, italic_spans = _count_inline_emphasis_spans(str(getattr(paragraph, "text", "") or ""))
        if bold_spans or italic_spans:
            has_signal = True
            source_bold += bold_spans
            source_italic += italic_spans
    return source_bold, source_italic, has_signal


def _count_output_emphasis(target_paragraphs: Sequence[Paragraph]) -> tuple[int, int]:
    """Count produced-DOCX bold/italic runs, excluding Heading-styled paragraphs (FR-003)."""
    output_bold = 0
    output_italic = 0
    for paragraph in target_paragraphs:
        if _target_has_heading_format(paragraph):
            continue
        for run in paragraph.runs:
            if run.bold:
                output_bold += 1
            if run.italic:
                output_italic += 1
    return output_bold, output_italic


def _emphasis_retention_ratio(output_count: int, source_count: int) -> float | None:
    """output/source retention; None (not-applicable) when the source count is zero (FR-004)."""
    if source_count <= 0:
        return None
    return round(output_count / source_count, 4)


def _build_emphasis_coverage_diagnostics(
    source_paragraphs: Sequence[ParagraphUnit],
    target_paragraphs: Sequence[Paragraph],
) -> dict[str, object]:
    """Advisory emphasis-coverage metric (spec 004, FR-001..FR-006).

    Bold/italic retention was measured NOWHERE, so a book could lose all its italics
    and still pass acceptance. This surfaces the loss without gating on it.
    """
    source_bold, source_italic, has_signal = _count_source_emphasis(source_paragraphs)
    if not has_signal:
        return {
            "measured": False,
            "reason": "no_source_emphasis_signal",
            "source_bold": None,
            "source_italic": None,
            "output_bold": None,
            "output_italic": None,
            "bold_retention_ratio": None,
            "italic_retention_ratio": None,
        }
    output_bold, output_italic = _count_output_emphasis(target_paragraphs)
    return {
        "measured": True,
        "reason": None,
        "source_bold": source_bold,
        "source_italic": source_italic,
        "output_bold": output_bold,
        "output_italic": output_italic,
        "bold_retention_ratio": _emphasis_retention_ratio(output_bold, source_bold),
        "italic_retention_ratio": _emphasis_retention_ratio(output_italic, source_italic),
    }


def _map_source_target_paragraphs(
    source_paragraphs: list[ParagraphUnit],
    target_paragraphs: list[Paragraph],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
):
    mapped_target_by_source: dict[int, int] = {}
    strategy_by_source: dict[int, str] = {}
    generated_registry_by_id = _build_generated_registry_by_paragraph_id(generated_paragraph_registry)

    # Per-call memo of target role/heading resolution keyed by target index (spec 029, Lever F):
    # resolve each target at most once and reuse across all passes/source iterations.
    role_resolver = _TargetRoleResolver(target_paragraphs)

    available_target_indexes = set(range(len(target_paragraphs)))
    target_indexes_by_exact_text: dict[str, list[int]] = {}
    target_indexes_by_normalized_text: dict[str, list[int]] = {}

    for target_index, target_paragraph in enumerate(target_paragraphs):
        exact_text = target_paragraph.text.strip()
        target_indexes_by_exact_text.setdefault(exact_text, []).append(target_index)
        normalized_text = _normalize_text_for_mapping(target_paragraph.text)
        if normalized_text:
            target_indexes_by_normalized_text.setdefault(normalized_text, []).append(target_index)

    for source_index, source_paragraph in enumerate(source_paragraphs):
        paragraph_id = source_paragraph.paragraph_id
        if not paragraph_id or source_index in mapped_target_by_source or source_paragraph.role == "image":
            continue
        registry_entry = generated_registry_by_id.get(paragraph_id)
        target_indexes = [
            target_index
            for target_index in _generated_registry_target_indexes(registry_entry)
            if 0 <= target_index < len(target_paragraphs)
        ]
        if len(target_indexes) != 1:
            continue
        target_index = target_indexes[0]
        if target_index not in available_target_indexes:
            continue
        if not _generated_registry_target_text_compatible(
            source_paragraph,
            target_paragraphs[target_index],
            registry_entry,
            role_resolver=role_resolver,
            target_index=target_index,
        ):
            continue
        _register_mapping(
            source_index,
            target_index,
            "paragraph_id_rebuild_key",
            mapped_target_by_source=mapped_target_by_source,
            strategy_by_source=strategy_by_source,
            available_target_indexes=available_target_indexes,
        )

    for source_index, source_paragraph in enumerate(source_paragraphs):
        paragraph_id = source_paragraph.paragraph_id
        if not paragraph_id or source_index in mapped_target_by_source:
            continue
        generated_text = _generated_registry_text(generated_registry_by_id.get(paragraph_id))
        if not generated_text:
            continue
        matching_target_indexes: set[int] = set()
        source_format_role = _source_format_role(source_paragraph)
        for normalized_generated_text in _build_generated_registry_candidates(source_paragraph, generated_text):
            matching_target_indexes.update(
                target_index
                for target_index in target_indexes_by_normalized_text.get(normalized_generated_text, [])
                if target_index in available_target_indexes
                and _registry_mapping_role_compatible(
                    source_format_role,
                    role_resolver.format_role(target_index),
                    role_resolver.has_heading_format(target_index),
                )
            )
        if len(matching_target_indexes) == 1:
            _register_mapping(
                source_index,
                next(iter(matching_target_indexes)),
                "paragraph_id_registry",
                mapped_target_by_source=mapped_target_by_source,
                strategy_by_source=strategy_by_source,
                available_target_indexes=available_target_indexes,
            )

    for source_index, source_paragraph in enumerate(source_paragraphs):
        paragraph_id = source_paragraph.paragraph_id
        if not paragraph_id or source_index in mapped_target_by_source or source_paragraph.role == "image":
            continue

        registry_entry = generated_registry_by_id.get(paragraph_id)
        if not _generated_registry_merged_ids(registry_entry):
            continue

        registry_candidates = [
            candidate
            for candidate in _build_generated_registry_candidates(
                source_paragraph,
                _generated_registry_text(registry_entry),
            )
            if len(candidate) >= 30
        ]
        if not registry_candidates:
            continue

        aggregation_candidates: list[int] = []
        for target_index in range(
            max(0, source_index - 12), min(len(target_paragraphs), source_index + 13)
        ):
            if target_index not in available_target_indexes:
                continue
            if abs(target_index - source_index) > 12:
                continue
            target_normalized = _normalize_text_for_mapping(target_paragraphs[target_index].text)
            if not target_normalized:
                continue
            if any(
                candidate in target_normalized
                and len(candidate) / max(len(target_normalized), 1) >= 0.6
                for candidate in registry_candidates
            ):
                aggregation_candidates.append(target_index)

        if len(aggregation_candidates) != 1:
            continue

        _register_mapping(
            source_index,
            aggregation_candidates[0],
            "paragraph_id_registry_aggregation_anchor",
            mapped_target_by_source=mapped_target_by_source,
            strategy_by_source=strategy_by_source,
            available_target_indexes=available_target_indexes,
        )

    for source_index, source_paragraph in enumerate(source_paragraphs):
        paragraph_id = source_paragraph.paragraph_id
        if not paragraph_id or source_index in mapped_target_by_source or source_paragraph.role == "image":
            continue
        generated_text = _generated_registry_text(generated_registry_by_id.get(paragraph_id))
        if not generated_text:
            continue

        scored_candidates: list[tuple[float, int]] = []
        registry_candidates = _build_generated_registry_candidates(source_paragraph, generated_text)
        if not registry_candidates:
            continue

        source_format_role = _source_format_role(source_paragraph)
        if source_format_role == "heading":
            continue
        for target_index in range(
            max(0, source_index - 3), min(len(target_paragraphs), source_index + 4)
        ):
            if target_index not in available_target_indexes:
                continue
            if abs(target_index - source_index) > 3:
                continue
            if not _registry_mapping_role_compatible(
                source_format_role,
                role_resolver.format_role(target_index),
                role_resolver.has_heading_format(target_index),
            ):
                continue
            evidence_candidates = [
                evidence
                for candidate_text in registry_candidates
                if (
                    evidence := _registry_candidate_mapping_evidence(
                        candidate_text,
                        target_paragraphs[target_index].text,
                        source_format_role=source_format_role,
                    )
                )
                is not None
            ]
            if not evidence_candidates:
                continue
            best_evidence = max(
                evidence_candidates,
                key=lambda evidence: (
                    float(evidence["score"]),
                    float(evidence["target_coverage_ratio"]),
                    int(evidence["common_token_count"]),
                ),
            )
            if not _projected_registry_text_floor_satisfied(best_evidence):
                continue
            score = float(best_evidence["score"]) + min(float(best_evidence["target_coverage_ratio"]), 1.0)
            scored_candidates.append((score, target_index))

        if not scored_candidates:
            continue

        scored_candidates.sort(reverse=True)
        best_score, best_target_index = scored_candidates[0]
        next_best_score = scored_candidates[1][0] if len(scored_candidates) > 1 else 0.0
        if best_score - next_best_score < 0.05:
            continue

        _register_mapping(
            source_index,
            best_target_index,
            "paragraph_id_registry_similarity",
            mapped_target_by_source=mapped_target_by_source,
            strategy_by_source=strategy_by_source,
            available_target_indexes=available_target_indexes,
        )

    for source_index, source_paragraph in enumerate(source_paragraphs):
        if source_index in mapped_target_by_source or source_paragraph.role != "image":
            continue
        candidates = [
            target_index
            for target_index in target_indexes_by_exact_text.get(source_paragraph.text.strip(), [])
            if target_index in available_target_indexes
        ]
        strategy = "image_anchor"
        if not candidates:
            source_image_text = source_paragraph.text.strip()
            candidates = [
                target_index
                for target_index in range(len(target_paragraphs))
                if target_index in available_target_indexes
                and source_image_text
                and source_image_text in target_paragraphs[target_index].text
                and IMAGE_PLACEHOLDER_PATTERN.search(target_paragraphs[target_index].text)
            ]
            strategy = "image_anchor_contained"
        if len(candidates) == 1:
            _register_mapping(
                source_index,
                candidates[0],
                strategy,
                mapped_target_by_source=mapped_target_by_source,
                strategy_by_source=strategy_by_source,
                available_target_indexes=available_target_indexes,
            )

    for source_index, source_paragraph in enumerate(source_paragraphs):
        if source_index == 0 or source_index in mapped_target_by_source or source_paragraph.role != "caption":
            continue
        previous_paragraph = source_paragraphs[source_index - 1]
        previous_target_index = mapped_target_by_source.get(source_index - 1)
        if previous_paragraph.role not in {"image", "table"} or previous_target_index is None:
            continue
        candidate_index = previous_target_index + 1
        if candidate_index not in available_target_indexes or candidate_index >= len(target_paragraphs):
            continue
        candidate_text = target_paragraphs[candidate_index].text.strip()
        if candidate_text and (
            is_likely_caption_text(candidate_text)
            or _normalize_text_for_mapping(source_paragraph.text) == _normalize_text_for_mapping(candidate_text)
        ):
            _register_mapping(
                source_index,
                candidate_index,
                "adjacent_caption",
                mapped_target_by_source=mapped_target_by_source,
                strategy_by_source=strategy_by_source,
                available_target_indexes=available_target_indexes,
            )

    for source_index, _source_paragraph in enumerate(source_paragraphs):
        _try_register_local_gap_fallback(
            source_index,
            source_paragraphs,
            target_paragraphs,
            role_resolver=role_resolver,
            mapped_target_by_source=mapped_target_by_source,
            strategy_by_source=strategy_by_source,
            available_target_indexes=available_target_indexes,
        )

    for source_index, source_paragraph in enumerate(source_paragraphs):
        if source_index in mapped_target_by_source:
            continue
        normalized_text = _normalize_text_for_mapping(source_paragraph.text)
        if not normalized_text:
            continue
        candidates = [
            target_index
            for target_index in target_indexes_by_normalized_text.get(normalized_text, [])
            if target_index in available_target_indexes
        ]
        if len(candidates) == 1:
            _register_mapping(
                source_index,
                candidates[0],
                "exact_text",
                mapped_target_by_source=mapped_target_by_source,
                strategy_by_source=strategy_by_source,
                available_target_indexes=available_target_indexes,
            )

    for source_index, source_paragraph in enumerate(source_paragraphs):
        _try_register_bounded_registry_mapping(
            source_index,
            source_paragraph,
            target_paragraphs,
            generated_registry_by_id,
            role_resolver=role_resolver,
            mapped_target_by_source=mapped_target_by_source,
            strategy_by_source=strategy_by_source,
            available_target_indexes=available_target_indexes,
        )

    for source_index, source_paragraph in enumerate(source_paragraphs):
        _try_register_projected_registry_mapping(
            source_index,
            source_paragraph,
            target_paragraphs,
            generated_registry_by_id,
            role_resolver=role_resolver,
            mapped_target_by_source=mapped_target_by_source,
            strategy_by_source=strategy_by_source,
            available_target_indexes=available_target_indexes,
        )

    for source_index, source_paragraph in enumerate(source_paragraphs):
        _try_register_unique_registry_text_floor_mapping(
            source_index,
            source_paragraph,
            target_paragraphs,
            generated_registry_by_id,
            role_resolver=role_resolver,
            mapped_target_by_source=mapped_target_by_source,
            strategy_by_source=strategy_by_source,
            available_target_indexes=available_target_indexes,
        )

    _register_repeated_note_sequence_mappings(
        source_paragraphs,
        target_paragraphs,
        generated_registry_by_id,
        role_resolver=role_resolver,
        mapped_target_by_source=mapped_target_by_source,
        strategy_by_source=strategy_by_source,
        available_target_indexes=available_target_indexes,
    )

    for source_index, source_paragraph in enumerate(source_paragraphs):
        if source_index in mapped_target_by_source or source_paragraph.role == "image":
            continue

        scored_candidates: list[tuple[float, int]] = []
        for target_index in range(len(target_paragraphs)):
            if target_index not in available_target_indexes:
                continue
            score = _mapping_similarity_score(source_paragraph, target_paragraphs[target_index].text)
            if score >= 0.9:
                scored_candidates.append((score, target_index))

        if not scored_candidates:
            continue

        scored_candidates.sort(reverse=True)
        best_score, best_target_index = scored_candidates[0]
        next_best_score = scored_candidates[1][0] if len(scored_candidates) > 1 else 0.0
        if best_score - next_best_score < 0.05:
            continue

        _register_mapping(
            source_index,
            best_target_index,
            "similarity",
            mapped_target_by_source=mapped_target_by_source,
            strategy_by_source=strategy_by_source,
            available_target_indexes=available_target_indexes,
        )

    if len(source_paragraphs) == len(target_paragraphs):
        for source_index, source_paragraph in enumerate(source_paragraphs):
            if source_index in mapped_target_by_source or source_index not in available_target_indexes:
                continue

            target_paragraph = target_paragraphs[source_index]
            source_exact = source_paragraph.text.strip()
            target_exact = target_paragraph.text.strip()
            source_normalized = _normalize_text_for_mapping(source_paragraph.text)
            target_normalized = _normalize_text_for_mapping(target_paragraph.text)

            if (source_exact and source_exact == target_exact) or (
                source_normalized and source_normalized == target_normalized
            ):
                _register_mapping(
                    source_index,
                    source_index,
                    "positional_exact",
                    mapped_target_by_source=mapped_target_by_source,
                    strategy_by_source=strategy_by_source,
                    available_target_indexes=available_target_indexes,
                )

    if len(source_paragraphs) == len(target_paragraphs):
        for source_index, source_paragraph in enumerate(source_paragraphs):
            if source_index in mapped_target_by_source or source_index not in available_target_indexes:
                continue
            if not _is_toc_source_paragraph(source_paragraph):
                continue

            target_paragraph = target_paragraphs[source_index]
            if not target_paragraph.text.strip() or IMAGE_PLACEHOLDER_PATTERN.search(target_paragraph.text):
                continue

            _register_mapping(
                source_index,
                source_index,
                "positional_toc_fallback",
                mapped_target_by_source=mapped_target_by_source,
                strategy_by_source=strategy_by_source,
                available_target_indexes=available_target_indexes,
            )

    mapping_pairs = [
        (source_paragraphs[source_index], target_paragraphs[target_index])
        for source_index, target_index in sorted(mapped_target_by_source.items())
    ]

    accepted_merged_sources = _collect_accepted_merged_sources(
        source_paragraphs,
        target_paragraphs,
        mapped_target_by_source,
    )
    accepted_aggregated_sources = _collect_accepted_aggregated_sources(
        source_paragraphs,
        target_paragraphs,
        mapped_target_by_source,
        generated_registry_by_id,
    )
    accepted_split_targets = _collect_accepted_split_targets(
        source_paragraphs,
        target_paragraphs,
        mapped_target_by_source,
        generated_registry_by_id,
    )
    accepted_relations, relation_report = build_paragraph_relations(
        source_paragraphs,
        enabled_relation_kinds=resolve_effective_relation_kinds(),
        structure_phase="post_ai_final",
    )
    relation_ids_by_paragraph: dict[str, list[str]] = {}
    for relation in accepted_relations:
        for paragraph_id in relation.member_paragraph_ids:
            relation_ids_by_paragraph.setdefault(paragraph_id, []).append(relation.relation_id)
    paragraph_index_by_id = {
        (paragraph.paragraph_id or f"p{index:04d}"): index for index, paragraph in enumerate(source_paragraphs)
    }

    for relation in accepted_relations:
        if relation.relation_kind != "epigraph_attribution":
            continue
        if len(relation.member_paragraph_ids) != 2:
            continue

        first_id, second_id = relation.member_paragraph_ids
        first_index = paragraph_index_by_id.get(first_id)
        second_index = paragraph_index_by_id.get(second_id)
        if first_index is None or second_index is None:
            continue
        if first_index not in mapped_target_by_source or second_index in mapped_target_by_source:
            continue

        anchor_target_index = mapped_target_by_source[first_index]
        candidate_target_index = anchor_target_index + 1
        if candidate_target_index not in available_target_indexes:
            continue
        if candidate_target_index >= len(target_paragraphs):
            continue

        candidate_target = target_paragraphs[candidate_target_index]
        candidate_text = candidate_target.text.strip()
        if not candidate_text or IMAGE_PLACEHOLDER_PATTERN.search(candidate_text):
            continue
        if _target_paragraph_has_heading_style(candidate_target):
            continue

        source_paragraph = source_paragraphs[second_index]
        structural_role = str(getattr(source_paragraph, "structural_role", "") or "").strip().lower()
        if structural_role != "attribution":
            continue

        _register_mapping(
            second_index,
            candidate_target_index,
            "adjacent_epigraph_attribution",
            mapped_target_by_source=mapped_target_by_source,
            strategy_by_source=strategy_by_source,
            available_target_indexes=available_target_indexes,
        )

    accepted_split_target_indexes = {entry["target_index"] for entry in accepted_split_targets}

    diagnostics = {
        "basis": "role_aware_formatting_coverage",
        "unmapped_source_count_basis": "role_aware_formatting_coverage",
        "counting_note": "filtered_raw_unmapped_source_count minus format_neutral_creditable_count, floored at zero",
        "source_count": len(source_paragraphs),
        "target_count": len(target_paragraphs),
        "mapped_count": len(mapping_pairs),
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [
            target_index
            for target_index in range(len(target_paragraphs))
            if target_index not in mapped_target_by_source.values() and target_index not in accepted_split_target_indexes
        ],
        "source_registry": [
            _build_source_registry_entry(
                paragraph,
                index,
                mapped_target_index=mapped_target_by_source.get(index),
                strategy=strategy_by_source.get(index),
                relation_ids=relation_ids_by_paragraph.get(paragraph.paragraph_id or f"p{index:04d}", []),
            )
            for index, paragraph in enumerate(source_paragraphs)
        ],
        "target_registry": [
            _build_target_registry_entry(
                paragraph,
                index,
                mapped=index in mapped_target_by_source.values() or index in accepted_split_target_indexes,
            )
            for index, paragraph in enumerate(target_paragraphs)
        ],
        "accepted_split_targets": accepted_split_targets,
        "accepted_merged_sources": accepted_merged_sources,
        "accepted_merged_sources_count": len(accepted_merged_sources),
        "accepted_aggregated_sources": accepted_aggregated_sources,
        "accepted_aggregated_sources_count": len(accepted_aggregated_sources),
        "max_accepted_merged_sources": max(
            (int(cast(int, entry.get("accepted_merged_sources_count", 0)) or 0) for entry in accepted_merged_sources),
            default=0,
        ),
        "high_confidence_merge_count": sum(
            1 for entry in accepted_merged_sources if entry.get("boundary_decision_class") == "high"
        ),
        "medium_accepted_merge_count": sum(
            1 for entry in accepted_merged_sources if entry.get("boundary_decision_class") == "medium_accepted"
        ),
        "accepted_relations": [
            {
                "relation_id": relation.relation_id,
                "relation_kind": relation.relation_kind,
                "member_paragraph_ids": list(relation.member_paragraph_ids),
                "anchor_asset_id": relation.anchor_asset_id,
                "confidence": relation.confidence,
                "rationale": list(relation.rationale),
            }
            for relation in accepted_relations
        ],
        "relation_decisions": [
            {
                "relation_kind": decision.relation_kind,
                "decision": decision.decision,
                "member_paragraph_ids": list(decision.member_paragraph_ids),
                "anchor_asset_id": decision.anchor_asset_id,
                "reasons": list(decision.reasons),
                "structure_phase": decision.structure_phase,
                "structure_source": decision.structure_source,
            }
            for decision in relation_report.decisions
        ],
        "relation_count": relation_report.total_relations,
        "relation_counts": dict(relation_report.relation_counts),
        "rejected_relation_candidate_count": relation_report.rejected_candidate_count,
        "caption_heading_conflicts": _build_caption_heading_conflicts(
            source_paragraphs,
            target_paragraphs,
            mapped_target_by_source,
            strategy_by_source,
        ),
        "list_restoration_decisions": [],
    }

    source_index_by_id = {
        (paragraph.paragraph_id or f"p{index:04d}"): index
        for index, paragraph in enumerate(source_paragraphs)
    }
    covered_source_indexes = set(mapped_target_by_source)
    for source_index in sorted(mapped_target_by_source):
        paragraph_id = source_paragraphs[source_index].paragraph_id or f"p{source_index:04d}"
        merged_ids = _generated_registry_merged_ids(generated_registry_by_id.get(paragraph_id))
        for merged_id in merged_ids:
            covered_index = source_index_by_id.get(merged_id)
            if covered_index is not None:
                covered_source_indexes.add(covered_index)
    for accepted_source in accepted_aggregated_sources:
        source_index = accepted_source.get("source_index")
        if isinstance(source_index, int):
            covered_source_indexes.add(source_index)

    diagnostics["unmapped_source_ids"] = [
        source_paragraphs[source_index].paragraph_id or f"p{source_index:04d}"
        for source_index in range(len(source_paragraphs))
        if source_index not in covered_source_indexes
    ]
    diagnostics["mapping_strategy_counts"] = _count_mapping_strategies(strategy_by_source)
    diagnostics["rebuild_key_mapping_quality"] = _build_rebuild_key_mapping_quality_diagnostics(
        source_paragraphs,
        target_paragraphs,
        mapped_target_by_source,
        strategy_by_source,
    )
    diagnostics["mapping_text_quality"] = _build_mapping_text_quality_diagnostics(
        source_paragraphs,
        target_paragraphs,
        mapped_target_by_source,
        strategy_by_source,
        generated_registry_by_id,
    )
    diagnostics["emphasis_coverage"] = _build_emphasis_coverage_diagnostics(
        source_paragraphs,
        target_paragraphs,
    )
    diagnostics["unmapped_source_role_counts"] = _build_unmapped_source_role_counts(
        source_paragraphs,
        cast(Sequence[str], diagnostics["unmapped_source_ids"]),
    )
    diagnostics["unmapped_source_samples"] = _build_unmapped_source_samples(
        source_paragraphs,
        cast(Sequence[str], diagnostics["unmapped_source_ids"]),
    )
    diagnostics["unmapped_target_samples"] = _build_unmapped_target_samples(
        target_paragraphs,
        cast(Sequence[int], diagnostics["unmapped_target_indexes"]),
    )
    diagnostics["unmapped_target_residual_diagnostics"] = _build_unmapped_target_residual_diagnostics(
        source_paragraphs,
        target_paragraphs,
        cast(Sequence[int], diagnostics["unmapped_target_indexes"]),
        generated_registry_by_id=generated_registry_by_id,
        mapped_target_by_source=mapped_target_by_source,
        accepted_aggregated_sources=accepted_aggregated_sources,
    )
    diagnostics["relation_identity_population"] = _count_relation_id_population(
        relation_ids_by_paragraph,
        len(source_paragraphs),
    )
    diagnostics["unmapped_source_residual_diagnostics"] = _build_unmapped_source_residual_diagnostics(
        source_paragraphs,
        target_paragraphs,
        cast(Sequence[str], diagnostics["unmapped_source_ids"]),
        generated_registry_by_id=generated_registry_by_id,
        relation_ids_by_paragraph=relation_ids_by_paragraph,
        mapped_target_by_source=mapped_target_by_source,
    )
    return mapping_pairs, diagnostics


def _target_paragraph_has_heading_style(paragraph) -> bool:
    style = getattr(paragraph, "style", None)
    style_name = str(getattr(style, "name", "") or "").strip().lower()
    return style_name.startswith("heading ")


def _target_paragraph_style_name(paragraph) -> str | None:
    style = getattr(paragraph, "style", None)
    style_name = str(getattr(style, "name", "") or "").strip()
    return style_name or None


def _is_heading_like_source_paragraph(source_paragraph: ParagraphUnit) -> bool:
    source_role = str(getattr(source_paragraph, "role", "") or "").strip().lower()
    structural_role = str(getattr(source_paragraph, "structural_role", "") or "").strip().lower()
    return (
        source_role == "heading"
        or structural_role == "heading"
        or getattr(source_paragraph, "heading_level", None) is not None
        or bool(getattr(source_paragraph, "heading_source", None))
    )
