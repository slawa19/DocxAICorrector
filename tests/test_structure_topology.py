from dataclasses import asdict

from docxaicorrector.core.models import DocumentMap, DocumentMapAnchor, DocumentMapOutlineEntry, ParagraphUnit, StructuralUnit
from docxaicorrector.structure.topology import TOPOLOGY_PROJECTION_SCHEMA_VERSION, apply_document_map_topology


def _paragraph(index: int, text: str) -> ParagraphUnit:
    return ParagraphUnit(text=text, role="body", structural_role="body", source_index=index, logical_index=index)


def test_structural_unit_id_is_stable_hash_not_sequence_based():
    first = StructuralUnit(
        unit_type="chapter_heading",
        logical_indexes=(10, 11, 12),
        canonical_text="Chapter Eleven Governance and We the Citizens An Ancient Future",
        role="heading",
        heading_level=1,
        confidence="high",
        authority="document_map_outline",
        evidence=("outline_entry", "adjacent_short_heading_fragments"),
    )
    _ = StructuralUnit(
        unit_type="section_heading",
        logical_indexes=(20, 21),
        canonical_text="Interlude",
        role="heading",
        heading_level=2,
        confidence="high",
        authority="document_map_outline",
        evidence=("outline_entry",),
    )
    second = StructuralUnit(
        unit_type="chapter_heading",
        logical_indexes=(10, 11, 12),
        canonical_text="Chapter Eleven Governance and We the Citizens An Ancient Future",
        role="heading",
        heading_level=1,
        confidence="high",
        authority="document_map_outline",
        evidence=("outline_entry", "adjacent_short_heading_fragments"),
    )

    assert first.unit_id == second.unit_id
    assert first.unit_id.startswith("u_")


def test_apply_document_map_topology_returns_schema_valid_empty_projection_when_no_authoritative_merge_exists():
    paragraphs = [_paragraph(0, "Ordinary body paragraph."), _paragraph(1, "Another ordinary body paragraph.")]
    document_map = DocumentMap(
        body_start_logical_index=0,
        toc_region=None,
        outline=(),
        paragraph_anchors={0: DocumentMapAnchor(role="body", heading_level=None, confidence="low")},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(0, 1),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
    )

    payload = asdict(projection)
    assert projection.stage == "document_topology_projection_v1"
    assert projection.schema_version == 1
    assert projection.topology_projection_schema_version == TOPOLOGY_PROJECTION_SCHEMA_VERSION
    assert payload["operations"] == ()
    assert payload["projected_units"] == ()


def test_apply_document_map_topology_merges_heading_continuation_from_high_confidence_outline():
    paragraphs = [
        _paragraph(10, "Chapter Eleven"),
        _paragraph(11, "Governance and We"),
        _paragraph(12, "the Citizens"),
        _paragraph(13, "An Ancient Future"),
        _paragraph(14, "Body paragraph starts here."),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Eleven Governance and We the Citizens An Ancient Future",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(10, 11, 12, 13, 14),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
    )

    assert len(projection.projected_units) == 1
    unit = projection.projected_units[0]
    assert unit.logical_indexes == (10, 11, 12, 13)
    assert unit.unit_type == "chapter_heading"
    assert unit.authority == "document_map_outline"
    assert unit.evidence == ("outline_entry", "adjacent_short_heading_fragments")
    assert len(projection.operations) == 1
    assert projection.operations[0].op == "merge_heading_continuation"


def test_apply_document_map_topology_does_not_merge_when_outline_confidence_is_not_high():
    paragraphs = [_paragraph(10, "Chapter Eleven"), _paragraph(11, "Governance and We"), _paragraph(12, "the Citizens")]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Eleven Governance and We the Citizens",
                level=1,
                logical_index=10,
                confidence="medium",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="medium")},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(10, 11, 12),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
    )

    assert projection.projected_units == ()
    assert projection.operations == ()


def test_apply_document_map_topology_does_not_merge_from_text_heuristics_alone_without_document_map_authority():
    paragraphs = [_paragraph(10, "Chapter Eleven"), _paragraph(11, "Governance and We"), _paragraph(12, "the Citizens")]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(10, 11, 12),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
    )

    assert projection.projected_units == ()
    assert projection.operations == ()