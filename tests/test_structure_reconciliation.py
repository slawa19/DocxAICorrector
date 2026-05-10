import logging
from types import SimpleNamespace

import docxaicorrector.structure.reconciliation as structure_reconciliation
from docxaicorrector.core.models import DocumentMap, DocumentMapAnchor, DocumentMapOutlineEntry, DocumentMapReviewZone, DocumentMapTocEntry, DocumentMapTocRegion, ParagraphClassification, ParagraphUnit, StructureMap
from docxaicorrector.structure.reconciliation import ReconciliationReport, reconcile_with_document_map, targeted_reclassify_with_reconciliation_context


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
        classifications={10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    reconciled_map, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert reconciled_map.classifications[10].role == "heading"
    assert reconciled_map.classifications[10].heading_level == 1
    assert report.patched_anchor_count == 1
    assert report.anchor_disagreements_seen == (10,)
    assert report.missing_outline_entry_count == 0
    assert report.outline_coverage_ratio == 1.0
    assert report.patched_logical_indexes == (10,)


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
        classifications={10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    reconciled_map, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert reconciled_map.classifications[10].role == "body"
    assert report.patched_anchor_count == 0
    assert report.anchor_disagreements_seen == (10,)
    assert report.missing_outline_entry_count == 1
    assert report.missing_outline_entries == (10,)


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
            10: ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high"),
            40: ParagraphClassification(index=40, role="heading", heading_level=1, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    _, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert report.unexpected_heading_count == 1
    assert report.toc_entry_without_body_match_count == 1


def test_reconcile_with_document_map_matches_adjacent_heading_to_outline_entry():
    paragraphs = [
        _paragraph(source_index=0, logical_index=57, text="FROM SCARCITY TO PROSPERITY"),
        _paragraph(source_index=1, logical_index=58, text="WITHIN A GENERATION"),
        _paragraph(source_index=2, logical_index=59, text="INTRODUCTION"),
    ]
    document_map = DocumentMap(
        body_start_logical_index=59,
        toc_region=None,
        outline=(DocumentMapOutlineEntry(title="INTRODUCTION", level=1, logical_index=59, confidence="high", evidence=("body_start",)),),
        paragraph_anchors={59: DocumentMapAnchor(role="body", heading_level=None, confidence="high")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(57, 58, 59),
    )
    structure_map = StructureMap(
        classifications={
            57: ParagraphClassification(index=57, role="heading", heading_level=1, confidence="medium"),
            58: ParagraphClassification(index=58, role="heading", heading_level=1, confidence="high"),
            59: ParagraphClassification(index=59, role="body", heading_level=None, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    _, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert report.missing_outline_entries == ()
    assert report.outline_coverage_ratio == 1.0
    assert report.unexpected_headings == (57,)


def test_reconcile_with_document_map_reports_front_matter_leak():
    paragraphs = [
        _paragraph(source_index=0, logical_index=1, text="Предисловие"),
        _paragraph(source_index=1, logical_index=10, text="ГЛАВА 1"),
    ]
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
        sampled_logical_indexes=(1, 10),
    )
    structure_map = StructureMap(
        classifications={
            1: ParagraphClassification(index=1, role="body", heading_level=None, confidence="high"),
            10: ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    _, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert report.front_matter_leaks == (1,)


def test_reconcile_with_document_map_treats_anchored_front_matter_body_as_advisory():
    paragraphs = [
        _paragraph(source_index=0, logical_index=1, text="Вступление"),
        _paragraph(source_index=1, logical_index=10, text="ГЛАВА 1"),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(DocumentMapOutlineEntry(title="ГЛАВА 1", level=1, logical_index=10, confidence="high", evidence=("bold",)),),
        paragraph_anchors={
            1: DocumentMapAnchor(role="body", heading_level=None, confidence="medium"),
            10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high"),
        },
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(1, 10),
    )
    structure_map = StructureMap(
        classifications={
            1: ParagraphClassification(index=1, role="body", heading_level=None, confidence="high"),
            10: ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    _, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert report.front_matter_leaks == ()
    assert report.front_matter_body_advisories == (1,)


def test_reconcile_with_document_map_reports_anchor_disagreements_for_targeted_recall_scope():
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
        classifications={10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="medium")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    _, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert report.anchor_disagreements_seen == (10,)


def test_report_payload_uses_only_canonical_reconciliation_field_names():
    report = ReconciliationReport(
        missing_outline_entries=(10,),
        anchor_disagreements_seen=(12,),
        front_matter_body_advisories=(2,),
        outline_coverage_ratio=0.5,
        patched_logical_indexes=(10, 14),
    )

    payload = structure_reconciliation._report_payload(report)

    assert payload["front_matter_body_advisories"] == [2]
    assert payload["anchor_disagreements_seen"] == [12]
    assert payload["patched_logical_indexes"] == [10, 14]
    assert payload["front_matter_leaks"] == []
    assert "anchor_conflicts" not in payload
    assert "anchor_conflicts_deprecated" not in payload
    assert "anchor_conflicts_alias_of" not in payload
    assert "patched_source_indexes" not in payload


def test_report_payload_persists_targeted_selection_reasons():
    report = ReconciliationReport(
        missing_outline_entries=(10,),
        targeted_recall_invoked=True,
        targeted_recall_count=1,
        targeted_selection_reasons=(
            structure_reconciliation.TargetedSelectionReason(
                logical_index=10,
                reasons=("missing_outline_entry", "body_start_neighborhood"),
            ),
        ),
        outline_coverage_ratio=0.5,
    )

    payload = structure_reconciliation._report_payload(report)

    assert payload["targeted_selected_logical_indexes"] == [10]
    assert payload["targeted_selection_reasons"] == [
        {
            "logical_index": 10,
            "reasons": ["missing_outline_entry", "body_start_neighborhood"],
        }
    ]


def test_select_targeted_paragraphs_uses_document_map_boundaries_not_advisories():
    paragraphs = [
        _paragraph(source_index=0, logical_index=1, text="Вступление"),
        _paragraph(source_index=1, logical_index=10, text="ГЛАВА 1"),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(),
        paragraph_anchors={10: DocumentMapAnchor(role="body", heading_level=None, confidence="low")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(1, 10),
    )
    report = ReconciliationReport(front_matter_body_advisories=(1,))

    selected = structure_reconciliation._select_targeted_paragraphs(
        paragraphs,
        document_map=document_map,
        report=report,
        max_paragraphs=5,
    )

    assert [paragraph.logical_index for paragraph in selected] == [10]


def test_build_targeted_selection_uses_review_zone_only_when_high_severity_and_bounded():
    paragraphs = [_paragraph(source_index=index, logical_index=index, text=f"P{index}") for index in range(8, 17)]
    document_map = DocumentMap(
        body_start_logical_index=50,
        toc_region=None,
        outline=(),
        paragraph_anchors={},
        review_zones=(
            DocumentMapReviewZone(start_logical_index=10, end_logical_index=14, reason="uncertain_toc_boundary", severity="warning"),
            DocumentMapReviewZone(start_logical_index=12, end_logical_index=13, reason="low_priority", severity="info"),
        ),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=tuple(range(8, 17)),
    )

    selection = structure_reconciliation._build_targeted_selection(
        paragraphs,
        document_map=document_map,
        report=ReconciliationReport(),
        max_paragraphs=5,
    )

    assert selection.logical_indexes == (9, 10, 11, 13, 14)
    assert all(selection_reason.reasons == ("review_zone",) for selection_reason in selection.reasons)


def test_build_targeted_selection_adds_body_start_neighborhood_reason():
    paragraphs = [_paragraph(source_index=index, logical_index=index, text=f"P{index}") for index in range(8, 15)]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=tuple(range(8, 15)),
    )

    selection = structure_reconciliation._build_targeted_selection(
        paragraphs,
        document_map=document_map,
        report=ReconciliationReport(),
        max_paragraphs=10,
    )

    assert selection.logical_indexes == (8, 9, 10, 11, 12)
    assert all(selection_reason.reasons == ("body_start_neighborhood",) for selection_reason in selection.reasons)


def test_build_targeted_selection_adds_toc_boundary_neighborhood_reason():
    paragraphs = [_paragraph(source_index=index, logical_index=index, text=f"P{index}") for index in range(8, 20)]
    document_map = DocumentMap(
        body_start_logical_index=100,
        toc_region=DocumentMapTocRegion(
            start_logical_index=10,
            end_logical_index=12,
            header_logical_index=9,
            entries=(),
            confidence="medium",
        ),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=tuple(range(8, 20)),
    )

    selection = structure_reconciliation._build_targeted_selection(
        paragraphs,
        document_map=document_map,
        report=ReconciliationReport(),
        max_paragraphs=10,
    )

    assert selection.logical_indexes == (8, 9, 10, 11, 12, 13, 14)
    assert all(selection_reason.reasons == ("toc_boundary_neighborhood",) for selection_reason in selection.reasons)


def test_build_targeted_selection_respects_max_cap_for_mixed_reasons():
    paragraphs = [_paragraph(source_index=index, logical_index=index, text=f"P{index}") for index in range(8, 30)]
    document_map = DocumentMap(
        body_start_logical_index=20,
        toc_region=DocumentMapTocRegion(
            start_logical_index=24,
            end_logical_index=26,
            header_logical_index=None,
            entries=(),
            confidence="medium",
        ),
        outline=(),
        paragraph_anchors={},
        review_zones=(
            DocumentMapReviewZone(start_logical_index=15, end_logical_index=18, reason="uncertain_front_matter", severity="critical"),
        ),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=tuple(range(8, 30)),
    )
    report = ReconciliationReport(missing_outline_entries=(10,))

    selection = structure_reconciliation._build_targeted_selection(
        paragraphs,
        document_map=document_map,
        report=report,
        max_paragraphs=4,
    )

    assert selection.logical_indexes == (8, 9, 10, 11)
    assert len(selection.logical_indexes) == 4


def test_targeted_reclassify_with_reconciliation_context_uses_provided_selection_without_recomputing(monkeypatch):
    paragraphs = [
        _paragraph(source_index=0, logical_index=10, text="ГЛАВА 1"),
        _paragraph(source_index=1, logical_index=11, text="Основной текст"),
    ]
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(10, 11),
    )
    structure_map = StructureMap(
        classifications={10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    selection = structure_reconciliation.TargetedSelection(
        logical_indexes=(10,),
        reasons=(
            structure_reconciliation.TargetedSelectionReason(
                logical_index=10,
                reasons=("review_zone",),
            ),
        ),
    )
    captured = {}

    monkeypatch.setattr(
        structure_reconciliation,
        "_build_targeted_selection",
        lambda *args, **kwargs: pytest.fail("selection should be reused, not recomputed"),
    )
    monkeypatch.setattr(structure_reconciliation, "build_paragraph_descriptors", lambda selected_paragraphs, document_map=None: [])

    def _fake_request(*, descriptors, report, client, model, timeout):
        captured["report"] = report
        return ([ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high")], 7)

    monkeypatch.setattr(structure_reconciliation, "_request_targeted_classifications", _fake_request)

    updated = targeted_reclassify_with_reconciliation_context(
        paragraphs,
        document_map,
        structure_map,
        ReconciliationReport(outline_coverage_ratio=0.5),
        client=object(),
        model="gpt-4o-mini",
        timeout=60.0,
        max_paragraphs=5,
        selection=selection,
    )

    assert captured["report"].targeted_selection_reasons == selection.reasons
    assert updated.classifications[10].role == "heading"


def test_targeted_reclassify_with_reconciliation_context_updates_only_flagged_subset():
    paragraphs = [
        _paragraph(source_index=0, logical_index=8, text="Вступление"),
        _paragraph(source_index=1, logical_index=9, text="Перед главой"),
        _paragraph(source_index=2, logical_index=10, text="ГЛАВА 1"),
        _paragraph(source_index=3, logical_index=11, text="Основной текст"),
        _paragraph(source_index=4, logical_index=12, text="Еще текст"),
    ]
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
        sampled_logical_indexes=(8, 9, 10, 11, 12),
    )
    structure_map = StructureMap(
        classifications={
            8: ParagraphClassification(index=8, role="body", heading_level=None, confidence="high"),
            9: ParagraphClassification(index=9, role="body", heading_level=None, confidence="high"),
            10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high"),
            11: ParagraphClassification(index=11, role="body", heading_level=None, confidence="high"),
            12: ParagraphClassification(index=12, role="body", heading_level=None, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    report = ReconciliationReport(missing_outline_entries=(10,), outline_coverage_ratio=0.0)
    requested_payloads = []

    class _FakeResponses:
        def create(self, *, model, input, timeout):
            requested_payloads.append({"model": model, "input": input, "timeout": timeout})
            return SimpleNamespace(
                output_text='[{"i": 10, "r": "heading", "l": 1, "c": "high", "reason": "matched outline"}]',
                usage=SimpleNamespace(total_tokens=34),
            )

    class _FakeClient:
        responses = _FakeResponses()

    updated = targeted_reclassify_with_reconciliation_context(
        paragraphs,
        document_map,
        structure_map,
        report,
        client=_FakeClient(),
        model="gpt-4o-mini",
        timeout=30.0,
        max_paragraphs=5,
    )

    assert updated.classifications[10].role == "heading"
    assert updated.classifications[10].heading_level == 1
    assert updated.classifications[8].role == "body"
    assert requested_payloads


def test_targeted_reclassify_with_reconciliation_context_drops_out_of_scope_indexes(caplog):
    paragraphs = [
        _paragraph(source_index=0, logical_index=8, text="Вступление"),
        _paragraph(source_index=1, logical_index=9, text="Перед главой"),
        _paragraph(source_index=2, logical_index=10, text="ГЛАВА 1"),
    ]
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
        sampled_logical_indexes=(8, 9, 10),
    )
    structure_map = StructureMap(
        classifications={
            8: ParagraphClassification(index=8, role="body", heading_level=None, confidence="high"),
            9: ParagraphClassification(index=9, role="body", heading_level=None, confidence="high"),
            10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    report = ReconciliationReport(missing_outline_entries=(10,), outline_coverage_ratio=0.0)

    class _FakeResponses:
        def create(self, *, model, input, timeout):
            return SimpleNamespace(
                output_text='[{"i": 10, "r": "heading", "l": 1, "c": "high", "reason": "matched outline"}, {"i": 999, "r": "heading", "l": 1, "c": "high", "reason": "hallucinated"}]',
                usage=SimpleNamespace(total_tokens=55),
            )

    class _FakeClient:
        responses = _FakeResponses()

    with caplog.at_level(logging.WARNING):
        updated = targeted_reclassify_with_reconciliation_context(
            paragraphs,
            document_map,
            structure_map,
            report,
            client=_FakeClient(),
            model="gpt-4o-mini",
            timeout=30.0,
            max_paragraphs=3,
        )

    assert updated.classifications[10].role == "heading"
    assert 999 not in updated.classifications
    assert "out-of-scope targeted reconciliation classification" in caplog.text


def test_reconcile_with_document_map_uses_logical_indexes_for_duplicate_source_indexes():
    paragraphs = [
        _paragraph(source_index=7, logical_index=10, text="ГЛАВА 1"),
        _paragraph(source_index=7, logical_index=11, text="Основной текст"),
    ]
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
        sampled_logical_indexes=(10, 11),
    )
    structure_map = StructureMap(
        classifications={
            10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high"),
            11: ParagraphClassification(index=11, role="body", heading_level=None, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    reconciled_map, report = reconcile_with_document_map(paragraphs, document_map, structure_map)

    assert reconciled_map.classifications[10].role == "heading"
    assert reconciled_map.classifications[11].role == "body"
    assert report.patched_logical_indexes == (10,)


def test_targeted_reclassify_with_reconciliation_context_uses_logical_indexes_for_duplicate_source_indexes():
    paragraphs = [
        _paragraph(source_index=7, logical_index=10, text="ГЛАВА 1"),
        _paragraph(source_index=7, logical_index=11, text="Основной текст"),
    ]
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
        sampled_logical_indexes=(10, 11),
    )
    structure_map = StructureMap(
        classifications={
            10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high"),
            11: ParagraphClassification(index=11, role="body", heading_level=None, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    report = ReconciliationReport(missing_outline_entries=(10,), outline_coverage_ratio=0.0)

    class _FakeResponses:
        def create(self, *, model, input, timeout):
            return SimpleNamespace(
                output_text='[{"i": 10, "r": "heading", "l": 1, "c": "high", "reason": "matched outline"}]',
                usage=SimpleNamespace(total_tokens=21),
            )

    class _FakeClient:
        responses = _FakeResponses()

    updated = targeted_reclassify_with_reconciliation_context(
        paragraphs,
        document_map,
        structure_map,
        report,
        client=_FakeClient(),
        model="gpt-4o-mini",
        timeout=30.0,
        max_paragraphs=2,
    )

    assert updated.classifications[10].role == "heading"
    assert updated.classifications[11].role == "body"