from dataclasses import asdict

import pytest

from docxaicorrector.core.models import DocumentMap, DocumentMapAnchor, DocumentMapOutlineEntry, DocumentMapSplitHint, DocumentMapTocEntry, DocumentMapTocRegion, ParagraphUnit, StructuralUnit
from docxaicorrector.structure.layout_signals import derive_layout_signals
from docxaicorrector.structure.topology import TOPOLOGY_PROJECTION_SCHEMA_VERSION, apply_document_map_topology


def _paragraph(index: int, text: str, **kwargs) -> ParagraphUnit:
    return ParagraphUnit(text=text, role="body", structural_role="body", source_index=index, logical_index=index, **kwargs)


def _compound_toc_text() -> str:
    return "73 6 Strategies for Banking 95 7 Strategies for Business and Entrepreneurs"


def _compound_toc_region(*, confidence: str = "high") -> DocumentMapTocRegion:
    return DocumentMapTocRegion(
        start_logical_index=35,
        end_logical_index=42,
        header_logical_index=35,
        entries=(
            DocumentMapTocEntry(
                title="6 Strategies for Banking",
                target_level=1,
                candidate_body_logical_index=141,
                confidence="high",
            ),
            DocumentMapTocEntry(
                title="7 Strategies for Business and Entrepreneurs",
                target_level=1,
                candidate_body_logical_index=159,
                confidence="high",
            ),
        ),
        confidence=confidence,
    )


def _non_matching_compound_toc_region() -> DocumentMapTocRegion:
    return DocumentMapTocRegion(
        start_logical_index=35,
        end_logical_index=42,
        header_logical_index=35,
        entries=(
            DocumentMapTocEntry(
                title="6 Strategies for Banking",
                target_level=1,
                candidate_body_logical_index=141,
                confidence="high",
            ),
            DocumentMapTocEntry(
                title="8 Strategies for Governments",
                target_level=1,
                candidate_body_logical_index=175,
                confidence="high",
            ),
        ),
        confidence="high",
    )


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


def test_apply_document_map_topology_disabled_path_is_semantically_identical_when_layout_signals_are_absent():
    paragraphs = [
        _paragraph(10, "Chapter Eleven"),
        _paragraph(11, "Governance and We"),
        _paragraph(12, "the Citizens"),
        _paragraph(13, "An Ancient Future"),
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
        sampled_logical_indexes=(10, 11, 12, 13),
    )

    current = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
    )
    explicit_none = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
        layout_signals=None,
    )

    assert asdict(current) == asdict(explicit_none)


def test_apply_document_map_topology_layout_confirms_explicit_authority_bounded_members_when_enabled():
    paragraphs = [
        _paragraph(10, "Chapter Eleven", font_size_pt=18.0, style_cluster_id=7, page_number=1),
        _paragraph(11, "Governance and We", font_size_pt=18.0, style_cluster_id=7, page_number=1),
        _paragraph(12, "the Citizens", font_size_pt=18.0, style_cluster_id=7, page_number=1),
        _paragraph(14, "Body paragraph one.", font_size_pt=12.0, page_number=1),
        _paragraph(15, "Body paragraph two.", font_size_pt=12.0, page_number=1),
        _paragraph(16, "Body paragraph three.", font_size_pt=12.0, page_number=1),
        _paragraph(17, "Body paragraph four.", font_size_pt=12.0, page_number=1),
        _paragraph(18, "Body paragraph five.", font_size_pt=12.0, page_number=1),
        _paragraph(19, "Body paragraph six.", font_size_pt=12.0, page_number=1),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Eleven Governance and We the Citizens",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
                member_logical_indexes=(10, 11, 12),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(10, 11, 12, 14, 15, 16, 17, 18, 19),
    )
    layout_signals = derive_layout_signals(paragraphs)

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
        layout_signals=layout_signals,
    )

    assert len(projection.projected_units) == 1
    unit = projection.projected_units[0]
    assert unit.logical_indexes == (10, 11, 12)
    assert unit.canonical_text == "Chapter Eleven Governance and We the Citizens"
    assert unit.evidence == ("outline_entry", "adjacent_short_heading_fragments", "font_cluster_match")
    assert projection.operations[0].evidence == ("outline_entry", "adjacent_short_heading_fragments", "font_cluster_match")


def test_apply_document_map_topology_layout_confirms_explicit_authority_across_mixed_heading_tiers():
    paragraphs = [
        _paragraph(10, "Chapter Eleven", font_size_pt=16.0, page_number=1),
        _paragraph(11, "GOVERNANCE AND WE,", font_size_pt=23.5, page_number=1),
        _paragraph(12, "THE CITIZENS", font_size_pt=23.5, page_number=1),
        _paragraph(13, "An Ancient Future?", font_size_pt=20.0, page_number=1),
        _paragraph(14, "Body paragraph starts here.", font_size_pt=11.0, page_number=1),
        _paragraph(15, "Body paragraph two.", font_size_pt=11.0, page_number=1),
        _paragraph(16, "Body paragraph three.", font_size_pt=11.0, page_number=1),
        _paragraph(17, "Body paragraph four.", font_size_pt=11.0, page_number=1),
        _paragraph(18, "Body paragraph five.", font_size_pt=11.0, page_number=1),
        _paragraph(19, "Body paragraph six.", font_size_pt=11.0, page_number=1),
        _paragraph(20, "Appendix Preview", font_size_pt=16.0, page_number=2),
        _paragraph(21, "Closing Reflection", font_size_pt=20.0, page_number=2),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Eleven GOVERNANCE AND WE, THE CITIZENS An Ancient Future?",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
                member_logical_indexes=(10, 11, 12, 13),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
        layout_signals=derive_layout_signals(paragraphs),
    )

    assert len(projection.projected_units) == 1
    unit = projection.projected_units[0]
    assert unit.logical_indexes == (10, 11, 12, 13)
    assert unit.canonical_text == "Chapter Eleven GOVERNANCE AND WE, THE CITIZENS An Ancient Future?"
    assert unit.evidence == ("outline_entry", "adjacent_short_heading_fragments", "body_font_baseline_outlier")
    assert projection.operations[0].evidence == (
        "outline_entry",
        "adjacent_short_heading_fragments",
        "body_font_baseline_outlier",
    )


def test_apply_document_map_topology_layout_rejects_explicit_membership_on_font_mismatch():
    paragraphs = [
        _paragraph(10, "Chapter Eleven", font_size_pt=18.0, style_cluster_id=7, page_number=1),
        _paragraph(11, "Governance and We", font_size_pt=18.0, style_cluster_id=7, page_number=1),
        _paragraph(12, "the Citizens", font_size_pt=12.0, style_cluster_id=7, page_number=1),
        _paragraph(14, "Body paragraph one.", font_size_pt=12.0, page_number=1),
        _paragraph(15, "Body paragraph two.", font_size_pt=12.0, page_number=1),
        _paragraph(16, "Body paragraph three.", font_size_pt=12.0, page_number=1),
        _paragraph(17, "Body paragraph four.", font_size_pt=12.0, page_number=1),
        _paragraph(18, "Body paragraph five.", font_size_pt=12.0, page_number=1),
        _paragraph(19, "Body paragraph six.", font_size_pt=12.0, page_number=1),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Eleven Governance and We the Citizens",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
                member_logical_indexes=(10, 11, 12),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(10, 11, 12, 14, 15, 16, 17, 18, 19),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
        layout_signals=derive_layout_signals(paragraphs),
    )

    assert projection.projected_units == ()
    assert projection.operations == ()


def test_apply_document_map_topology_layout_rejects_explicit_membership_on_observed_page_hint_transition():
    paragraphs = [
        _paragraph(10, "Chapter Eleven", font_size_pt=18.0, style_cluster_id=7, page_number=1),
        _paragraph(11, "Governance and We", font_size_pt=18.0, style_cluster_id=7, page_number=1),
        _paragraph(12, "the Citizens", font_size_pt=18.0, style_cluster_id=7, page_number=2),
        _paragraph(14, "Body paragraph one.", font_size_pt=12.0, page_number=2),
        _paragraph(15, "Body paragraph two.", font_size_pt=12.0, page_number=2),
        _paragraph(16, "Body paragraph three.", font_size_pt=12.0, page_number=2),
        _paragraph(17, "Body paragraph four.", font_size_pt=12.0, page_number=2),
        _paragraph(18, "Body paragraph five.", font_size_pt=12.0, page_number=2),
        _paragraph(19, "Body paragraph six.", font_size_pt=12.0, page_number=2),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Eleven Governance and We the Citizens",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
                member_logical_indexes=(10, 11, 12),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(10, 11, 12, 14, 15, 16, 17, 18, 19),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
        layout_signals=derive_layout_signals(paragraphs),
    )

    assert projection.projected_units == ()
    assert projection.operations == ()


def test_apply_document_map_topology_does_not_use_layout_signals_to_recover_missing_stage1_membership():
    paragraphs = [
        _paragraph(10, "Governance and We", font_size_pt=18.0, style_cluster_id=7, page_number=1),
        _paragraph(11, "the Citizens", font_size_pt=18.0, style_cluster_id=7, page_number=1),
        _paragraph(12, "An Ancient Future?", font_size_pt=18.0, style_cluster_id=7, page_number=1),
        _paragraph(13, "Body paragraph one.", font_size_pt=12.0, page_number=1),
        _paragraph(14, "Body paragraph two.", font_size_pt=12.0, page_number=1),
        _paragraph(15, "Body paragraph three.", font_size_pt=12.0, page_number=1),
        _paragraph(16, "Body paragraph four.", font_size_pt=12.0, page_number=1),
        _paragraph(17, "Body paragraph five.", font_size_pt=12.0, page_number=1),
        _paragraph(18, "Body paragraph six.", font_size_pt=12.0, page_number=1),
        _paragraph(19, "Body paragraph seven.", font_size_pt=12.0, page_number=1),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Governance and We",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(10, 11, 12, 13, 14, 15, 16, 17, 18, 19),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
        layout_signals=derive_layout_signals(paragraphs),
    )

    assert projection.projected_units == ()
    assert projection.operations == ()


def test_apply_document_map_topology_emits_candidate_page_artifact_split_with_optional_page_break_evidence():
    paragraphs = [
        _paragraph(9, "3", font_size_pt=12.0, page_number=1, is_likely_page_number=True),
        _paragraph(10, "this page intentionally left blank chapter nine", font_size_pt=18.0, page_number=2, style_cluster_id=7),
        _paragraph(11, "Body paragraph one.", font_size_pt=12.0, page_number=2),
        _paragraph(12, "Body paragraph two.", font_size_pt=12.0, page_number=2),
        _paragraph(13, "Body paragraph three.", font_size_pt=12.0, page_number=2),
        _paragraph(14, "Body paragraph four.", font_size_pt=12.0, page_number=2),
        _paragraph(15, "Body paragraph five.", font_size_pt=12.0, page_number=2),
        _paragraph(16, "Body paragraph six.", font_size_pt=12.0, page_number=2),
        _paragraph(17, "Body paragraph seven.", font_size_pt=12.0, page_number=2),
        _paragraph(18, "Body paragraph eight.", font_size_pt=12.0, page_number=2),
    ]
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
        sampled=False,
        sampled_logical_indexes=(9, 10, 11, 12, 13, 14, 15, 16, 17, 18),
    )

    with_transition = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
        layout_signals=derive_layout_signals(paragraphs),
    )
    without_transition_paragraphs = [
        _paragraph(9, "Prelude", font_size_pt=12.0, page_number=None),
        _paragraph(10, "this page intentionally left blank chapter nine", font_size_pt=18.0, page_number=None, style_cluster_id=7),
        _paragraph(11, "Body paragraph one.", font_size_pt=12.0, page_number=2),
        _paragraph(12, "Body paragraph two.", font_size_pt=12.0, page_number=2),
        _paragraph(13, "Body paragraph three.", font_size_pt=12.0, page_number=2),
        _paragraph(14, "Body paragraph four.", font_size_pt=12.0, page_number=2),
        _paragraph(15, "Body paragraph five.", font_size_pt=12.0, page_number=2),
        _paragraph(16, "Body paragraph six.", font_size_pt=12.0, page_number=2),
        _paragraph(17, "Body paragraph seven.", font_size_pt=12.0, page_number=2),
        _paragraph(18, "Body paragraph eight.", font_size_pt=12.0, page_number=2),
    ]
    without_transition = apply_document_map_topology(
        without_transition_paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
        layout_signals=derive_layout_signals(without_transition_paragraphs),
    )

    with_transition_op = next(operation for operation in with_transition.operations if operation.op == "candidate_page_artifact_split")
    without_transition_op = next(operation for operation in without_transition.operations if operation.op == "candidate_page_artifact_split")
    assert with_transition_op.confidence == "candidate"
    assert with_transition_op.authority == "document_map_outline"
    assert with_transition_op.evidence == ("page_artifact_phrase", "local_heading_neighborhood", "page_break_boundary")
    assert without_transition_op.evidence == ("page_artifact_phrase", "local_heading_neighborhood")


def test_apply_document_map_topology_raises_when_emitted_operation_vocab_is_invalid(monkeypatch):
    paragraphs = [_paragraph(0, "Body paragraph.")]
    document_map = DocumentMap(
        body_start_logical_index=0,
        toc_region=None,
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(0,),
    )

    monkeypatch.setattr(
        "docxaicorrector.structure.topology._build_candidate_page_artifact_operations",
        lambda **kwargs: [
            __import__("docxaicorrector.core.models", fromlist=["DocumentTopologyOperation"]).DocumentTopologyOperation(
                op="invalid_candidate_op",
                logical_indexes=(0,),
                canonical_text="Body paragraph.",
                authority="document_map_outline",
                confidence="candidate",
                evidence=("page_artifact_phrase",),
            )
        ],
    )

    with pytest.raises(ValueError, match="Invalid topology operation"):
        apply_document_map_topology(
            paragraphs,
            document_map,
            app_config={"structure_recovery_document_map_preview_chars": 120},
            document_map_cache_key="doc-map-key",
            layout_signals=derive_layout_signals(
                [
                    _paragraph(0, "Body one", font_size_pt=12.0),
                    _paragraph(1, "Body two", font_size_pt=12.0),
                    _paragraph(2, "Body three", font_size_pt=12.0),
                    _paragraph(3, "Body four", font_size_pt=12.0),
                    _paragraph(4, "Body five", font_size_pt=12.0),
                    _paragraph(5, "Body six", font_size_pt=12.0),
                    _paragraph(6, "Body seven", font_size_pt=12.0),
                    _paragraph(7, "Body eight", font_size_pt=12.0),
                ]
            ),
        )


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


def test_apply_document_map_topology_uses_explicit_outline_membership_for_multi_paragraph_heading():
    paragraphs = [
        _paragraph(10, "Chapter Eleven"),
        _paragraph(11, "Governance and We,"),
        _paragraph(12, "the Citizens"),
        _paragraph(13, "An Ancient Future?"),
        _paragraph(14, "Body paragraph starts here."),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="11 Governance and We the Citizens An Ancient Future",
                level=1,
                logical_index=11,
                confidence="high",
                evidence=("outline_entry",),
                member_logical_indexes=(10, 11, 12, 13),
            ),
        ),
        paragraph_anchors={11: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
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
    assert unit.canonical_text == "11 Governance and We the Citizens An Ancient Future"
    assert unit.evidence == ("outline_entry",)
    assert projection.operations[0].op == "merge_heading_continuation"


def test_apply_document_map_topology_does_not_extend_membership_past_canonical_outline_title_without_explicit_stage1_membership():
    paragraphs = [
        _paragraph(10, "Chapter Eleven"),
        _paragraph(11, "Governance and We,"),
        _paragraph(12, "the Citizens"),
        _paragraph(13, "An Ancient Future?"),
        _paragraph(14, "Body paragraph starts here."),
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
    assert unit.logical_indexes == (10, 11, 12)
    assert unit.canonical_text == "Governance and We the Citizens"
    assert projection.operations[0].op == "merge_heading_continuation"


def test_apply_document_map_topology_does_not_add_trailing_subtitle_or_prefix_once_canonical_title_boundary_is_reached():
    paragraphs = [
        _paragraph(10, "11"),
        _paragraph(11, "Governance and We,"),
        _paragraph(12, "the Citizens"),
        _paragraph(13, "An Ancient Future?"),
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
    assert projection.projected_units[0].logical_indexes == (11, 12)
    assert projection.projected_units[0].canonical_text == "Governance and We the Citizens"


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


def test_apply_document_map_topology_creates_binding_compound_toc_split_from_high_confidence_hint_when_flag_enabled():
    paragraphs = [_paragraph(40, _compound_toc_text())]
    document_map = DocumentMap(
        body_start_logical_index=141,
        toc_region=_compound_toc_region(),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=40,
                split_kind="compound_toc_entries",
                expected_parts=("6 Strategies for Banking", "7 Strategies for Business and Entrepreneurs"),
                authority="document_map_toc",
                confidence="high",
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(40,),
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

    assert [operation.op for operation in projection.operations] == ["split_compound_toc_entries"]
    assert projection.operations[0].authority == "document_map_split_hint"
    assert projection.operations[0].evidence == (
        "split_hint",
        "bounded_toc_region",
        "toc_entry",
        "one_to_one_toc_entry_match",
    )
    assert [unit.canonical_text for unit in projection.get_units(40)] == [
        "6 Strategies for Banking",
        "7 Strategies for Business and Entrepreneurs",
    ]
    assert [unit.unit_type for unit in projection.get_units(40)] == ["toc_entry", "toc_entry"]
    assert projection.get_unit(40) is None


def test_apply_document_map_topology_does_not_bind_explicit_compound_toc_hint_without_one_to_one_toc_entry_match():
    paragraphs = [_paragraph(40, _compound_toc_text())]
    document_map = DocumentMap(
        body_start_logical_index=141,
        toc_region=_non_matching_compound_toc_region(),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=40,
                split_kind="compound_toc_entries",
                expected_parts=("6 Strategies for Banking", "7 Strategies for Business and Entrepreneurs"),
                authority="document_map_toc",
                confidence="high",
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(40,),
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


def test_apply_document_map_topology_does_not_create_binding_compound_toc_split_when_flag_is_disabled():
    paragraphs = [_paragraph(40, _compound_toc_text())]
    document_map = DocumentMap(
        body_start_logical_index=141,
        toc_region=_compound_toc_region(),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=40,
                split_kind="compound_toc_entries",
                expected_parts=("6 Strategies for Banking", "7 Strategies for Business and Entrepreneurs"),
                authority="document_map_toc",
                confidence="high",
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(40,),
    )

    projection = apply_document_map_topology(
        paragraphs,
        document_map,
        app_config={"structure_recovery_document_map_preview_chars": 120},
        document_map_cache_key="doc-map-key",
    )

    assert projection.projected_units == ()
    assert projection.operations == ()


@pytest.mark.parametrize("confidence", ["medium", "low"])
def test_apply_document_map_topology_ignores_non_high_confidence_compound_toc_split_hints(confidence: str):
    paragraphs = [_paragraph(40, _compound_toc_text())]
    document_map = DocumentMap(
        body_start_logical_index=141,
        toc_region=_non_matching_compound_toc_region(),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=40,
                split_kind="compound_toc_entries",
                expected_parts=("6 Strategies for Banking", "7 Strategies for Business and Entrepreneurs"),
                authority="document_map_toc",
                confidence=confidence,
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(40,),
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


def test_apply_document_map_topology_ignores_wrong_split_kind_for_compound_toc_binding_split():
    paragraphs = [_paragraph(40, _compound_toc_text())]
    document_map = DocumentMap(
        body_start_logical_index=141,
        toc_region=_non_matching_compound_toc_region(),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=40,
                split_kind="page_artifact_heading",
                expected_parts=("6 Strategies for Banking", "7 Strategies for Business and Entrepreneurs"),
                authority="document_map_toc",
                confidence="high",
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(40,),
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


def test_apply_document_map_topology_allows_implicit_high_confidence_toc_entries_as_compound_split_authority():
    paragraphs = [_paragraph(40, _compound_toc_text())]
    document_map = DocumentMap(
        body_start_logical_index=141,
        toc_region=_compound_toc_region(),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(),
        sampled=False,
        sampled_logical_indexes=(40,),
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

    assert [operation.op for operation in projection.operations] == ["split_compound_toc_entries"]
    assert projection.operations[0].authority == "document_map_toc"
    assert projection.operations[0].evidence == ("bounded_toc_region", "one_to_one_toc_entry_match", "toc_entry")
    assert [unit.authority for unit in projection.get_units(40)] == ["document_map_toc", "document_map_toc"]


def test_apply_document_map_topology_leaves_compound_toc_projection_conservative_without_one_to_one_match():
    paragraphs = [_paragraph(40, _compound_toc_text())]
    document_map = DocumentMap(
        body_start_logical_index=141,
        toc_region=_non_matching_compound_toc_region(),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(),
        sampled=False,
        sampled_logical_indexes=(40,),
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


def test_apply_document_map_topology_applies_compound_toc_split_only_inside_bounded_toc_region():
    paragraphs = [_paragraph(50, _compound_toc_text())]
    document_map = DocumentMap(
        body_start_logical_index=141,
        toc_region=_compound_toc_region(),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=50,
                split_kind="compound_toc_entries",
                expected_parts=("6 Strategies for Banking", "7 Strategies for Business and Entrepreneurs"),
                authority="document_map_toc",
                confidence="high",
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(50,),
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


def test_apply_document_map_topology_binding_compound_toc_split_unit_ids_are_stable():
    paragraphs = [_paragraph(40, _compound_toc_text())]
    document_map = DocumentMap(
        body_start_logical_index=141,
        toc_region=_compound_toc_region(),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=40,
                split_kind="compound_toc_entries",
                expected_parts=("6 Strategies for Banking", "7 Strategies for Business and Entrepreneurs"),
                authority="document_map_toc",
                confidence="high",
                evidence=("split_hint",),
            ),
        ),
        sampled=False,
        sampled_logical_indexes=(40,),
    )
    app_config = {
        "structure_recovery_document_map_preview_chars": 120,
        "structure_recovery_topology_projection_binding_splits_enabled": True,
    }

    first = apply_document_map_topology(paragraphs, document_map, app_config=app_config, document_map_cache_key="doc-map-key")
    second = apply_document_map_topology(paragraphs, document_map, app_config=app_config, document_map_cache_key="doc-map-key")

    assert [(unit.canonical_text, unit.unit_id) for unit in first.get_units(40)] == [
        (unit.canonical_text, unit.unit_id) for unit in second.get_units(40)
    ]
