from docxaicorrector.core.models import DocumentMap, DocumentMapAnchor, DocumentMapOutlineEntry, DocumentMapTocEntry, DocumentMapTocRegion, ParagraphClassification, ParagraphUnit, StructureMap
from docxaicorrector.structure.reconciliation import reconcile_with_document_map


def _paragraph(*, source_index: int, logical_index: int, text: str) -> ParagraphUnit:
    paragraph = ParagraphUnit(text=text, role="body", structural_role="body", source_index=source_index, logical_index=logical_index)
    return paragraph


def test_reconcile_with_document_map_projects_high_confidence_heading_anchor():
    paragraphs = [_paragraph(source_index=0, logical_index=10, text="ГЛАВА 1")]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(DocumentMapOutlineEntry(title="ГЛАВА 1", level=1, logical_index=10, confidence="high", evidence=("bold",)),),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(10,),
    )
    structure_map = StructureMap(
        classifications={0: ParagraphClassification(index=0, role="body", heading_level=None, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    reconciled_map, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert reconciled_map.classifications[0].role == "heading"
    assert reconciled_map.classifications[0].heading_level == 1
    assert report.patched_anchor_count == 1
    assert report.missing_outline_entry_count == 1


def test_reconcile_with_document_map_does_not_project_medium_confidence_anchor():
    paragraphs = [_paragraph(source_index=0, logical_index=10, text="ГЛАВА 1")]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(DocumentMapOutlineEntry(title="ГЛАВА 1", level=1, logical_index=10, confidence="medium", evidence=("bold",)),),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="medium")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(10,),
    )
    structure_map = StructureMap(
        classifications={0: ParagraphClassification(index=0, role="body", heading_level=None, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    reconciled_map, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert reconciled_map.classifications[0].role == "body"
    assert report.patched_anchor_count == 0
    assert report.missing_outline_entry_count == 1


def test_reconcile_with_document_map_reports_unexpected_headings_and_unmatched_toc_entries():
    paragraphs = [
        _paragraph(source_index=0, logical_index=10, text="ГЛАВА 1"),
        _paragraph(source_index=1, logical_index=40, text="ГЛАВА 2"),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=DocumentMapTocRegion(
            start_logical_index=0,
            end_logical_index=5,
            header_logical_index=None,
            entries=(DocumentMapTocEntry(title="ГЛАВА 3", target_level=1, candidate_body_logical_index=100, confidence="medium"),),
            confidence="medium",
        ),
        outline=(DocumentMapOutlineEntry(title="ГЛАВА 1", level=1, logical_index=10, confidence="high", evidence=("bold",)),),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(10, 40),
    )
    structure_map = StructureMap(
        classifications={
            0: ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high"),
            1: ParagraphClassification(index=1, role="heading", heading_level=1, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    _, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert report.unexpected_heading_count == 1
    assert report.toc_entry_without_body_match_count == 1