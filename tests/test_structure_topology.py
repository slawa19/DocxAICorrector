from dataclasses import asdict

import pytest

from docxaicorrector.core.models import DocumentMap, DocumentMapAnchor, DocumentMapOutlineEntry, DocumentMapSplitHint, ParagraphUnit, StructuralUnit
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


def test_apply_document_map_topology_merges_numeric_chapter_label_prefix_when_outline_title_keeps_only_subtitle():
    paragraphs = [
        _paragraph(10, "11"),
        _paragraph(11, "Governance and We"),
        _paragraph(12, "the Citizens"),
        _paragraph(13, "An Ancient Future?"),
        _paragraph(14, "Body paragraph starts here."),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Governance and We the Citizens An Ancient Future",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={
            10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high"),
            11: DocumentMapAnchor(role="heading", heading_level=1, confidence="high"),
        },
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
    assert projection.projected_units[0].logical_indexes == (10, 11, 12, 13)
    assert projection.operations[0].op == "merge_heading_continuation"


def test_apply_document_map_topology_merges_preceding_chapter_label_when_outline_anchor_starts_on_second_fragment():
    paragraphs = [
        _paragraph(10, "Chapter Eleven"),
        _paragraph(11, "Governance and We"),
        _paragraph(12, "the Citizens"),
        _paragraph(13, "Body paragraph starts here."),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Governance and We the Citizens",
                level=1,
                logical_index=11,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={11: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(10, 11, 12, 13),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
    )

    assert len(projection.projected_units) == 1
    assert projection.projected_units[0].logical_indexes == (10, 11, 12)
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


def test_apply_document_map_topology_creates_binding_page_artifact_split_only_with_high_confidence_hint_and_flag_enabled():
    paragraphs = [_paragraph(10, "this page intentionally left blank chapter nine")]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Nine",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=10,
                split_kind="page_artifact_heading",
                expected_parts=("this page intentionally left blank", "chapter nine"),
                authority="document_map_outline",
                confidence="high",
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(10,),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={
            "structure_recovery_document_map_preview_chars": 120,
            "structure_recovery_topology_projection_binding_splits_enabled": True,
        },
        document_map_cache_key="doc-map-key",
    )

    assert [operation.op for operation in projection.operations] == ["split_page_artifact_from_heading"]
    assert len(projection.projected_units) == 2
    page_artifact_unit = next(unit for unit in projection.projected_units if unit.unit_type == "page_artifact")
    heading_unit = next(unit for unit in projection.projected_units if unit.unit_type == "chapter_heading")
    assert page_artifact_unit.logical_indexes == (10,)
    assert page_artifact_unit.authority == "document_map_split_hint"
    assert page_artifact_unit.evidence == ("split_hint", "page_artifact_phrase", "local_heading_neighborhood")
    assert heading_unit.logical_indexes == (10,)
    assert heading_unit.canonical_text == "Chapter Nine"
    assert heading_unit.authority == "document_map_split_hint"
    assert heading_unit.evidence == ("split_hint", "outline_entry", "local_heading_neighborhood")
    assert projection.get_unit(10) == heading_unit


def test_apply_document_map_topology_does_not_create_binding_page_artifact_split_without_hint():
    paragraphs = [_paragraph(10, "this page intentionally left blank chapter nine")]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Nine",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        split_hints=(),
        sampled=False,
        sampled_logical_indexes=(10,),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={
            "structure_recovery_document_map_preview_chars": 120,
            "structure_recovery_topology_projection_binding_splits_enabled": True,
        },
        document_map_cache_key="doc-map-key",
    )

    assert projection.projected_units == ()
    assert projection.operations == ()


@pytest.mark.parametrize("confidence", ["medium", "low"])
def test_apply_document_map_topology_ignores_non_high_confidence_page_artifact_split_hints(confidence: str):
    paragraphs = [_paragraph(10, "this page intentionally left blank chapter nine")]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Nine",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=10,
                split_kind="page_artifact_heading",
                expected_parts=("this page intentionally left blank", "chapter nine"),
                authority="document_map_outline",
                confidence=confidence,
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(10,),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={
            "structure_recovery_document_map_preview_chars": 120,
            "structure_recovery_topology_projection_binding_splits_enabled": True,
        },
        document_map_cache_key="doc-map-key",
    )

    assert projection.projected_units == ()
    assert projection.operations == ()


def test_apply_document_map_topology_ignores_wrong_split_kind_for_page_artifact_binding_split():
    paragraphs = [_paragraph(10, "this page intentionally left blank chapter nine")]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Nine",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=10,
                split_kind="compound_toc_entries",
                expected_parts=("this page intentionally left blank", "chapter nine"),
                authority="document_map_outline",
                confidence="high",
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(10,),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={
            "structure_recovery_document_map_preview_chars": 120,
            "structure_recovery_topology_projection_binding_splits_enabled": True,
        },
        document_map_cache_key="doc-map-key",
    )

    assert projection.projected_units == ()
    assert projection.operations == ()


def test_apply_document_map_topology_does_not_create_binding_page_artifact_split_when_flag_is_disabled():
    paragraphs = [_paragraph(10, "this page intentionally left blank chapter nine")]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Nine",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=10,
                split_kind="page_artifact_heading",
                expected_parts=("this page intentionally left blank", "chapter nine"),
                authority="document_map_outline",
                confidence="high",
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(10,),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
    )

    assert projection.projected_units == ()
    assert projection.operations == ()


def test_apply_document_map_topology_binding_page_artifact_split_unit_ids_are_stable():
    paragraphs = [_paragraph(10, "this page intentionally left blank chapter nine")]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Nine",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=10,
                split_kind="page_artifact_heading",
                expected_parts=("this page intentionally left blank", "chapter nine"),
                authority="document_map_outline",
                confidence="high",
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(10,),
    )
    app_config = {
        "structure_recovery_document_map_preview_chars": 120,
        "structure_recovery_topology_projection_binding_splits_enabled": True,
    }

    first = apply_document_map_topology(paragraphs, document_map, app_config=app_config, document_map_cache_key="doc-map-key")
    second = apply_document_map_topology(paragraphs, document_map, app_config=app_config, document_map_cache_key="doc-map-key")

    assert [(unit.unit_type, unit.unit_id) for unit in first.projected_units] == [
        (unit.unit_type, unit.unit_id) for unit in second.projected_units
    ]