"""Paragraph mapping and DOCX formatting restoration.

Handles source-to-target paragraph alignment, preserved property transfer,
semantic style normalization, and list numbering restoration.
"""

import json
import logging
import re
import time
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import Mapping, Sequence

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from document import (
    HEADING_STYLE_PATTERN,
    IMAGE_PLACEHOLDER_PATTERN,
    INLINE_HTML_TAG_PATTERN,
    MARKDOWN_LINK_PATTERN,
    PRESERVED_PARAGRAPH_PROPERTY_NAMES,
    _detect_explicit_list_kind,
    _find_child_element,
    _get_xml_attribute,
    _is_likely_caption_text,
    _resolve_paragraph_outline_level,
    _xml_local_name,
)
from logger import log_event
from models import ParagraphUnit

FORMATTING_DIAGNOSTICS_DIR = Path(".run") / "formatting_diagnostics"
MARKDOWN_HEADING_LINE_PATTERN = re.compile(r"^#{1,6}\s+\S")


def _paragraph_preview(text: str, *, limit: int = 120) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _normalize_text_for_mapping(text: str) -> str:
    normalized = text.strip()
    normalized = re.sub(r"^#{1,6}\s+", "", normalized)
    normalized = MARKDOWN_LINK_PATTERN.sub(r"\1", normalized)
    normalized = INLINE_HTML_TAG_PATTERN.sub("", normalized)
    normalized = normalized.replace("***", "").replace("**", "").replace("*", "")
    normalized = normalized.replace("<br/>", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


def _build_generated_registry_candidates(source_paragraph: ParagraphUnit, generated_text: str) -> list[str]:
    candidates: list[str] = []

    def add_candidate(text: str) -> None:
        normalized = _normalize_text_for_mapping(text)
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


def _collect_target_paragraphs(document) -> list[Paragraph]:
    return [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text.strip() or IMAGE_PLACEHOLDER_PATTERN.search(paragraph.text)
    ]


def _build_source_registry_entry(
    paragraph: ParagraphUnit,
    fallback_index: int,
    *,
    mapped_target_index: int | None,
    strategy: str | None,
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

    outline_level = _resolve_paragraph_outline_level(paragraph)
    if outline_level is not None:
        return outline_level
    return None


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


def _mapping_similarity_score(source_paragraph: ParagraphUnit, target_text: str) -> float:
    source_text = _normalize_text_for_mapping(source_paragraph.text)
    normalized_target = _normalize_text_for_mapping(target_text)
    if not source_text or not normalized_target:
        return 0.0

    score = SequenceMatcher(None, source_text, normalized_target).ratio()
    if source_paragraph.role == "caption" and _is_likely_caption_text(target_text):
        score += 0.08
    if source_paragraph.role == "list":
        target_list_kind = _detect_explicit_list_kind(target_text)
        if target_list_kind is not None and target_list_kind == source_paragraph.list_kind:
            score += 0.05
    if source_paragraph.role == "heading" and len(target_text.split()) <= 18:
        score += 0.03
    return min(score, 1.0)


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
) -> dict[str, str]:
    registry_by_id: dict[str, str] = {}
    if not generated_paragraph_registry:
        return registry_by_id

    for entry in generated_paragraph_registry:
        paragraph_id = entry.get("paragraph_id")
        text = entry.get("text")
        if isinstance(paragraph_id, str) and paragraph_id and isinstance(text, str) and text.strip():
            registry_by_id[paragraph_id] = text
    return registry_by_id


def _map_source_target_paragraphs(
    source_paragraphs: list[ParagraphUnit],
    target_paragraphs: list[Paragraph],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
):
    mapped_target_by_source: dict[int, int] = {}
    strategy_by_source: dict[int, str] = {}
    generated_registry_by_id = _build_generated_registry_by_paragraph_id(generated_paragraph_registry)

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
        if not paragraph_id or source_index in mapped_target_by_source:
            continue
        generated_text = generated_registry_by_id.get(paragraph_id)
        if not generated_text:
            continue
        matching_target_indexes: set[int] = set()
        for normalized_generated_text in _build_generated_registry_candidates(source_paragraph, generated_text):
            matching_target_indexes.update(
                target_index
                for target_index in target_indexes_by_normalized_text.get(normalized_generated_text, [])
                if target_index in available_target_indexes
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
        generated_text = generated_registry_by_id.get(paragraph_id)
        if not generated_text:
            continue

        scored_candidates: list[tuple[float, int]] = []
        registry_candidates = _build_generated_registry_candidates(source_paragraph, generated_text)
        if not registry_candidates:
            continue

        for target_index in sorted(available_target_indexes):
            if abs(target_index - source_index) > 3:
                continue
            score = max(
                SequenceMatcher(None, candidate_text, _normalize_text_for_mapping(target_paragraphs[target_index].text)).ratio()
                for candidate_text in registry_candidates
            )
            if score >= 0.75:
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
        if len(candidates) == 1:
            _register_mapping(
                source_index,
                candidates[0],
                "image_anchor",
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
            _is_likely_caption_text(candidate_text)
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
        if source_index in mapped_target_by_source or source_paragraph.role == "image":
            continue

        scored_candidates: list[tuple[float, int]] = []
        for target_index in sorted(available_target_indexes):
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

    mapping_pairs = [
        (source_paragraphs[source_index], target_paragraphs[target_index])
        for source_index, target_index in sorted(mapped_target_by_source.items())
    ]

    diagnostics = {
        "source_count": len(source_paragraphs),
        "target_count": len(target_paragraphs),
        "mapped_count": len(mapping_pairs),
        "unmapped_source_ids": [
            source_paragraphs[source_index].paragraph_id or f"p{source_index:04d}"
            for source_index in range(len(source_paragraphs))
            if source_index not in mapped_target_by_source
        ],
        "unmapped_target_indexes": [
            target_index
            for target_index in range(len(target_paragraphs))
            if target_index not in mapped_target_by_source.values()
        ],
        "source_registry": [
            _build_source_registry_entry(
                paragraph,
                index,
                mapped_target_index=mapped_target_by_source.get(index),
                strategy=strategy_by_source.get(index),
            )
            for index, paragraph in enumerate(source_paragraphs)
        ],
        "target_registry": [
            _build_target_registry_entry(
                paragraph,
                index,
                mapped=index in mapped_target_by_source.values(),
            )
            for index, paragraph in enumerate(target_paragraphs)
        ],
        "caption_heading_conflicts": _build_caption_heading_conflicts(
            source_paragraphs,
            target_paragraphs,
            mapped_target_by_source,
            strategy_by_source,
        ),
        "list_restoration_decisions": [],
    }
    return mapping_pairs, diagnostics


def _write_formatting_diagnostics_artifact(stage: str, diagnostics: dict[str, object]) -> str | None:
    try:
        FORMATTING_DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
        artifact_path = FORMATTING_DIAGNOSTICS_DIR / f"{stage}_{int(time.time() * 1000)}.json"
        payload = {
            "stage": stage,
            "generated_at_epoch_ms": int(time.time() * 1000),
            **diagnostics,
        }
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(artifact_path)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Formatting preservation and semantic normalization
# ---------------------------------------------------------------------------


def preserve_source_paragraph_properties(
    docx_bytes: bytes,
    paragraphs: list[ParagraphUnit],
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> bytes:
    if not docx_bytes or not paragraphs:
        return docx_bytes

    source_paragraphs = [paragraph for paragraph in paragraphs if paragraph.role != "table"]
    if not any(paragraph.preserved_ppr_xml for paragraph in source_paragraphs):
        return docx_bytes

    document = Document(BytesIO(docx_bytes))
    target_paragraphs = _collect_target_paragraphs(document)
    mapping_pairs, diagnostics = _map_source_target_paragraphs(
        source_paragraphs,
        target_paragraphs,
        generated_paragraph_registry=generated_paragraph_registry,
    )

    if len(source_paragraphs) != len(target_paragraphs) or diagnostics["mapped_count"] != len(source_paragraphs):
        artifact_path = _write_formatting_diagnostics_artifact("preserve", diagnostics)
        log_event(
            logging.WARNING,
            "paragraph_count_mismatch_preserve",
            "Число source/target абзацев не совпадает при переносе свойств форматирования; применяю только консервативно сопоставленные абзацы.",
            source_count=len(source_paragraphs),
            target_count=len(target_paragraphs),
            mapped_count=diagnostics["mapped_count"],
            unmapped_source_count=len(diagnostics["unmapped_source_ids"]),
            unmapped_target_count=len(diagnostics["unmapped_target_indexes"]),
            artifact_path=artifact_path,
        )

    if not mapping_pairs:
        return docx_bytes

    for source_paragraph, target_paragraph in mapping_pairs:
        _apply_preserved_paragraph_properties(target_paragraph, source_paragraph.preserved_ppr_xml)

    output_stream = BytesIO()
    document.save(output_stream)
    return output_stream.getvalue()


def normalize_semantic_output_docx(
    docx_bytes: bytes,
    paragraphs: list[ParagraphUnit],
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> bytes:
    if not docx_bytes or not paragraphs:
        return docx_bytes

    source_paragraphs = [paragraph for paragraph in paragraphs if paragraph.role != "table"]
    document = Document(BytesIO(docx_bytes))
    target_paragraphs = _collect_target_paragraphs(document)
    mapping_pairs, diagnostics = _map_source_target_paragraphs(
        source_paragraphs,
        target_paragraphs,
        generated_paragraph_registry=generated_paragraph_registry,
    )

    mismatch_detected = (
        len(source_paragraphs) != len(target_paragraphs)
        or diagnostics["mapped_count"] != len(source_paragraphs)
    )

    if not mapping_pairs:
        if mismatch_detected:
            artifact_path = _write_formatting_diagnostics_artifact("normalize", diagnostics)
            log_event(
                logging.WARNING,
                "paragraph_count_mismatch_normalize",
                "Число source/target абзацев не совпадает при semantic-normalization; нормализую только консервативно сопоставленные абзацы.",
                source_count=len(source_paragraphs),
                target_count=len(target_paragraphs),
                mapped_count=diagnostics["mapped_count"],
                unmapped_source_count=len(diagnostics["unmapped_source_ids"]),
                unmapped_target_count=len(diagnostics["unmapped_target_indexes"]),
                artifact_path=artifact_path,
            )
        return docx_bytes

    for source_paragraph, target_paragraph in mapping_pairs:
        _normalize_output_paragraph(document, target_paragraph, source_paragraph)

    diagnostics["list_restoration_decisions"] = _restore_list_numbering_for_mapped_paragraphs(document, mapping_pairs)

    if mismatch_detected:
        artifact_path = _write_formatting_diagnostics_artifact("normalize", diagnostics)
        log_event(
            logging.WARNING,
            "paragraph_count_mismatch_normalize",
            "Число source/target абзацев не совпадает при semantic-normalization; нормализую только консервативно сопоставленные абзацы.",
            source_count=len(source_paragraphs),
            target_count=len(target_paragraphs),
            mapped_count=diagnostics["mapped_count"],
            unmapped_source_count=len(diagnostics["unmapped_source_ids"]),
            unmapped_target_count=len(diagnostics["unmapped_target_indexes"]),
            artifact_path=artifact_path,
        )

    if _style_exists(document, "Table Grid"):
        for table in document.tables:
            table.style = "Table Grid"

    output_stream = BytesIO()
    document.save(output_stream)
    return output_stream.getvalue()


# ---------------------------------------------------------------------------
# Paragraph-level normalization and list numbering restoration
# ---------------------------------------------------------------------------


def _normalize_output_paragraph(document, paragraph, source_paragraph: ParagraphUnit) -> None:
    if source_paragraph.role == "heading":
        level = min(max(source_paragraph.heading_level or 1, 1), 6)
        heading_style = f"Heading {level}"
        if _style_exists(document, heading_style):
            paragraph.style = document.styles[heading_style]
        return

    if source_paragraph.role == "caption":
        if _style_exists(document, "Caption"):
            paragraph.style = document.styles["Caption"]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return

    if source_paragraph.role == "image":
        if _style_exists(document, "Normal"):
            paragraph.style = document.styles["Normal"]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return

    if source_paragraph.role == "list":
        if _style_exists(document, "List Paragraph"):
            paragraph.style = document.styles["List Paragraph"]
        return

    if _style_exists(document, "Body Text"):
        paragraph.style = document.styles["Body Text"]
    elif _style_exists(document, "Normal"):
        paragraph.style = document.styles["Normal"]


def _restore_list_numbering_for_mapped_paragraphs(document, mapping_pairs: list[tuple[ParagraphUnit, Paragraph]]) -> list[dict[str, object]]:
    numbering_root = _get_target_numbering_root(document)
    decisions: list[dict[str, object]] = []
    if numbering_root is None:
        for source_paragraph, _ in mapping_pairs:
            if source_paragraph.role != "list":
                continue
            decisions.append(
                {
                    "paragraph_id": source_paragraph.paragraph_id,
                    "text_preview": _paragraph_preview(source_paragraph.text),
                    "action": "target_numbering_part_missing",
                }
            )
        return decisions

    numbering_id_map: dict[tuple[str, str, str, str], tuple[int, int]] = {}
    next_abstract_num_id = _next_numbering_identifier(numbering_root, "abstractNum", "abstractNumId")
    next_num_id = _next_numbering_identifier(numbering_root, "num", "numId")

    for source_paragraph, target_paragraph in mapping_pairs:
        if source_paragraph.role != "list":
            continue
        if not source_paragraph.list_num_xml or not source_paragraph.list_abstract_num_xml:
            decisions.append(
                {
                    "paragraph_id": source_paragraph.paragraph_id,
                    "text_preview": _paragraph_preview(source_paragraph.text),
                    "action": "missing_source_numbering_xml",
                    "list_kind": source_paragraph.list_kind,
                    "list_level": source_paragraph.list_level,
                }
            )
            continue

        mapping_key = (
            source_paragraph.list_num_id or "",
            source_paragraph.list_abstract_num_id or "",
            source_paragraph.list_num_xml,
            source_paragraph.list_abstract_num_xml,
        )
        mapped_ids = numbering_id_map.get(mapping_key)
        if mapped_ids is None:
            abstract_num_id = next_abstract_num_id
            num_id = next_num_id
            next_abstract_num_id += 1
            next_num_id += 1
            if not _append_numbering_definition(numbering_root, source_paragraph, abstract_num_id, num_id):
                decisions.append(
                    {
                        "paragraph_id": source_paragraph.paragraph_id,
                        "text_preview": _paragraph_preview(source_paragraph.text),
                        "action": "append_definition_failed",
                        "list_kind": source_paragraph.list_kind,
                        "list_level": source_paragraph.list_level,
                    }
                )
                continue
            mapped_ids = (abstract_num_id, num_id)
            numbering_id_map[mapping_key] = mapped_ids

        _apply_list_numbering_to_paragraph(target_paragraph, list_level=source_paragraph.list_level, num_id=mapped_ids[1])
        decisions.append(
            {
                "paragraph_id": source_paragraph.paragraph_id,
                "text_preview": _paragraph_preview(source_paragraph.text),
                "action": "restored",
                "list_kind": source_paragraph.list_kind,
                "list_level": source_paragraph.list_level,
                "target_num_id": mapped_ids[1],
                "target_abstract_num_id": mapped_ids[0],
            }
        )

    return decisions


def _get_target_numbering_root(document):
    numbering_part = getattr(document.part, "numbering_part", None)
    return getattr(numbering_part, "element", None)


def _next_numbering_identifier(numbering_root, tag_name: str, attribute_name: str) -> int:
    max_identifier = 0
    for child in numbering_root:
        if _xml_local_name(child.tag) != tag_name:
            continue
        value = _get_xml_attribute(child, attribute_name)
        try:
            max_identifier = max(max_identifier, int(value or "0"))
        except ValueError:
            continue
    return max_identifier + 1


def _append_numbering_definition(numbering_root, source_paragraph: ParagraphUnit, abstract_num_id: int, num_id: int) -> bool:
    try:
        abstract_num_element = parse_xml(source_paragraph.list_abstract_num_xml or "")
        num_element = parse_xml(source_paragraph.list_num_xml or "")
    except Exception:
        return False

    abstract_num_element.set(qn("w:abstractNumId"), str(abstract_num_id))
    num_element.set(qn("w:numId"), str(num_id))

    abstract_num_id_element = _find_child_element(num_element, "abstractNumId")
    if abstract_num_id_element is None:
        abstract_num_id_element = OxmlElement("w:abstractNumId")
        num_element.insert(0, abstract_num_id_element)
    abstract_num_id_element.set(qn("w:val"), str(abstract_num_id))

    numbering_root.append(abstract_num_element)
    numbering_root.append(num_element)
    return True


def _apply_list_numbering_to_paragraph(paragraph, *, list_level: int, num_id: int) -> None:
    paragraph_properties = _ensure_paragraph_properties(paragraph)
    existing_num_pr = _find_child_element(paragraph_properties, "numPr")
    if existing_num_pr is not None:
        paragraph_properties.remove(existing_num_pr)

    num_pr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), str(max(0, list_level)))
    num_id_element = OxmlElement("w:numId")
    num_id_element.set(qn("w:val"), str(num_id))
    num_pr.append(ilvl)
    num_pr.append(num_id_element)
    paragraph_properties.append(num_pr)


def _style_exists(document, style_name: str) -> bool:
    try:
        document.styles[style_name]
    except KeyError:
        return False
    return True


def _apply_preserved_paragraph_properties(paragraph, preserved_ppr_xml: tuple[str, ...]) -> None:
    if not preserved_ppr_xml:
        return

    paragraph_properties = _ensure_paragraph_properties(paragraph)
    for child in list(paragraph_properties):
        if _xml_local_name(child.tag) in PRESERVED_PARAGRAPH_PROPERTY_NAMES:
            paragraph_properties.remove(child)

    for xml_fragment in preserved_ppr_xml:
        try:
            paragraph_properties.append(parse_xml(xml_fragment))
        except Exception:
            continue


def _ensure_paragraph_properties(paragraph):
    paragraph_properties = _find_child_element(paragraph._element, "pPr")
    if paragraph_properties is not None:
        return paragraph_properties

    paragraph_properties = OxmlElement("w:pPr")
    paragraph._element.insert(0, paragraph_properties)
    return paragraph_properties
