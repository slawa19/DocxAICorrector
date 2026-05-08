from __future__ import annotations

from dataclasses import dataclass

from docxaicorrector.core.models import DocumentMap, ParagraphClassification, ParagraphUnit, StructureMap


STRUCTURE_RECONCILIATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ReconciliationReport:
    patched_anchor_count: int = 0
    missing_outline_entry_count: int = 0
    unexpected_heading_count: int = 0
    toc_entry_without_body_match_count: int = 0
    patched_source_indexes: tuple[int, ...] = ()


def reconcile_with_document_map(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    structure_map: StructureMap,
) -> tuple[StructureMap, ReconciliationReport]:
    logical_to_paragraph = {
        int(getattr(paragraph, "logical_index", paragraph.source_index)): paragraph
        for paragraph in paragraphs
    }
    source_to_logical = {
        paragraph.source_index: int(getattr(paragraph, "logical_index", paragraph.source_index))
        for paragraph in paragraphs
    }
    patched_classifications = dict(structure_map.classifications)
    patched_source_indexes: set[int] = set()

    outline_targets = {
        entry.logical_index: entry.level
        for entry in document_map.outline
    }

    missing_outline_entry_count = 0
    for logical_index, level in outline_targets.items():
        paragraph = logical_to_paragraph.get(logical_index)
        if paragraph is None:
            continue
        classification = patched_classifications.get(paragraph.source_index)
        if classification is not None and classification.role == "heading" and classification.heading_level == level:
            continue
        missing_outline_entry_count += 1

    for logical_index, anchor in (document_map.paragraph_anchors or {}).items():
        if str(anchor.confidence or "").strip().lower() != "high":
            continue
        paragraph = logical_to_paragraph.get(int(logical_index))
        if paragraph is None:
            continue
        desired_heading_level = anchor.heading_level if anchor.role == "heading" else None
        existing = patched_classifications.get(paragraph.source_index)
        if (
            existing is not None
            and existing.role == anchor.role
            and existing.heading_level == desired_heading_level
        ):
            continue
        patched_classifications[paragraph.source_index] = ParagraphClassification(
            index=paragraph.source_index,
            role=anchor.role,
            heading_level=desired_heading_level,
            confidence="high",
            rationale="document_map_reconciliation",
        )
        patched_source_indexes.add(paragraph.source_index)

    heading_logical_indexes = {
        source_to_logical[source_index]
        for source_index, classification in patched_classifications.items()
        if classification.role == "heading" and source_index in source_to_logical
    }
    outline_logical_indexes = {entry.logical_index for entry in document_map.outline}
    unexpected_heading_count = sum(1 for logical_index in heading_logical_indexes if logical_index not in outline_logical_indexes)

    toc_entry_without_body_match_count = 0
    toc_region = document_map.toc_region
    if toc_region is not None:
        for entry in toc_region.entries:
            candidate = entry.candidate_body_logical_index
            if candidate is None:
                continue
            if not any(abs(logical_index - candidate) <= 5 for logical_index in heading_logical_indexes):
                toc_entry_without_body_match_count += 1

    reconciled_structure_map = StructureMap(
        classifications=patched_classifications,
        model_used=structure_map.model_used,
        total_tokens_used=structure_map.total_tokens_used,
        processing_time_seconds=structure_map.processing_time_seconds,
        window_count=structure_map.window_count,
    )
    report = ReconciliationReport(
        patched_anchor_count=len(patched_source_indexes),
        missing_outline_entry_count=missing_outline_entry_count,
        unexpected_heading_count=unexpected_heading_count,
        toc_entry_without_body_match_count=toc_entry_without_body_match_count,
        patched_source_indexes=tuple(sorted(patched_source_indexes)),
    )
    return reconciled_structure_map, report