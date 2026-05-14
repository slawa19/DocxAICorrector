from dataclasses import asdict
import json

import pytest

from docxaicorrector.core.models import DocumentMap, DocumentMapAnchor, DocumentMapOutlineEntry, DocumentMapSplitHint, DocumentMapTocEntry, DocumentMapTocRegion, EmbeddedStructureHint, ParagraphUnit
from docxaicorrector.structure.document_map import (
    DocumentMapSchemaError,
    _parse_document_map_payload,
    build_default_document_map,
    build_document_map,
    build_document_map_paragraph_descriptors,
    select_document_map_logical_indexes,
)


def _paragraph(index: int, text: str, **overrides) -> ParagraphUnit:
    paragraph = ParagraphUnit(text=text, role="body", structural_role="body", source_index=index, logical_index=index)
    for key, value in overrides.items():
        setattr(paragraph, key, value)
    return paragraph


def test_build_document_map_paragraph_descriptors_uses_preview_and_stage0_signals():
    paragraph = _paragraph(
        3,
        "Contents........ 12 " + ("A" * 150),
        style_name="Heading 1",
        is_bold=True,
        paragraph_alignment="center",
        font_size_pt=18,
        heading_level=1,
        heading_source="explicit",
        is_repeated_across_pages=True,
        is_likely_page_number=True,
        heuristic_structural_role_hint="toc_entry",
    )

    descriptor = build_document_map_paragraph_descriptors([paragraph], preview_chars=20)[0]

    assert descriptor.to_prompt_dict() == {
        "i": 3,
        "t": "Contents........ 12",
        "len": len(paragraph.text.strip()),
        "sty": None,
        "b": True,
        "ctr": True,
        "caps": False,
        "sz": 0.0,
        "pg": 12,
        "pos": 0.0,
        "gap": None,
        "rep": True,
        "pn": True,
        "iso": False,
        "toc": True,
        "scr": False,
        "hl": 1,
    }


def test_build_document_map_paragraph_descriptors_prefers_persisted_stage0_fields_when_present():
    paragraph = _paragraph(
        3,
        "Plain body line",
        style_name="Body Text",
        font_size_pt=18,
        style_cluster_id=7,
        font_size_z_score=2.5,
        page_number=12,
        position_fraction=0.625,
        vertical_gap_before_pt=14.5,
        is_isolated_marker=True,
        toc_pattern_hint=True,
        scripture_reference_hint=True,
    )

    descriptor = build_document_map_paragraph_descriptors([paragraph], preview_chars=20)[0]

    assert descriptor.style_cluster_id == 7
    assert descriptor.font_size_z_score == 2.5
    assert descriptor.page_number == 12
    assert descriptor.position_fraction == 0.625
    assert descriptor.vertical_gap_before_pt == 14.5
    assert descriptor.is_isolated_marker is True
    assert descriptor.toc_pattern_hint is True
    assert descriptor.scripture_reference_hint is True


def test_build_document_map_paragraph_descriptors_sanitizes_invalid_embedded_hints():
    paragraph = _paragraph(
        0,
        "Фрагмент",
        heuristic_embedded_structure_hints=(
            EmbeddedStructureHint(
                text="bad",
                role="not-a-role",
                structural_role="not-a-structural-role",
                list_kind="not-a-list-kind",
            ),
        ),
    )

    descriptor = build_document_map_paragraph_descriptors([paragraph])[0]

    assert descriptor.embedded_structure_hints == (
        {"t": "bad", "r": "body", "sr": "body", "hl": None, "lk": None, "iso": False, "scr": False},
    )


def test_build_document_map_paragraph_descriptors_extracts_vertical_gap_from_paragraph_properties_xml():
    paragraph = _paragraph(
        2,
        "Chapter title",
        paragraph_properties_xml='<w:pPr><w:spacing w:before="230"/></w:pPr>',
    )

    descriptor = build_document_map_paragraph_descriptors([paragraph])[0]

    assert descriptor.vertical_gap_before_pt == 11.5
    assert descriptor.to_prompt_dict()["gap"] == 11.5


def test_build_document_map_paragraph_descriptors_include_embedded_structure_hints_and_sampling_priority():
    paragraphs = [
        _paragraph(0, "ordinary body paragraph with enough text to avoid short-priority and uniform bias"),
        _paragraph(1, "Compound paragraph that now stays intact before Stage 1."),
    ]
    paragraphs[1].heuristic_embedded_structure_hints = [
        EmbeddedStructureHint(text="Conclusion........ 29", role="body", structural_role="toc_entry"),
        EmbeddedStructureHint(text="Introduction", role="heading", structural_role="body", heading_level=2),
    ]

    descriptors = build_document_map_paragraph_descriptors(paragraphs, preview_chars=24)

    assert descriptors[1].toc_pattern_hint is True
    assert descriptors[1].embedded_structure_hints == (
        {"t": "Conclusion........ 29", "r": "body", "sr": "toc_entry", "hl": None, "lk": None, "iso": False, "scr": False},
        {"t": "Introduction", "r": "heading", "sr": "body", "hl": 2, "lk": None, "iso": False, "scr": False},
    )
    assert descriptors[1].to_prompt_dict()["emb"] == [
        {"t": "Conclusion........ 29", "r": "body", "sr": "toc_entry", "hl": None, "lk": None, "iso": False, "scr": False},
        {"t": "Introduction", "r": "heading", "sr": "body", "hl": 2, "lk": None, "iso": False, "scr": False},
    ]

    sampled = select_document_map_logical_indexes(descriptors, max_input_paragraphs=1)

    assert sampled == (1,)


def test_select_document_map_logical_indexes_prioritizes_structural_signals_before_uniform_sampling():
    paragraphs = [
        _paragraph(0, "ordinary body paragraph with enough text to avoid short-priority"),
        _paragraph(1, "BOLD SIGNAL", is_bold=True),
        _paragraph(2, "Contents........ 5", heuristic_structural_role_hint="toc_entry"),
        _paragraph(3, "Gen 1:1"),
        _paragraph(4, "another ordinary body paragraph with enough text to avoid short-priority"),
        _paragraph(5, "Heading", heading_level=1, heading_source="explicit"),
    ]

    descriptors = build_document_map_paragraph_descriptors(paragraphs, preview_chars=120)
    sampled = select_document_map_logical_indexes(descriptors, max_input_paragraphs=4)

    assert 1 in sampled
    assert 2 in sampled
    assert 3 in sampled
    assert 5 in sampled
    assert len(sampled) == 4


def test_select_document_map_logical_indexes_prioritizes_large_vertical_gap_before_uniform_sampling():
    paragraphs = [
        _paragraph(0, "ordinary body paragraph with enough text to avoid short-priority and uniform bias"),
        _paragraph(1, "another ordinary body paragraph with enough text to avoid short-priority and uniform bias"),
        _paragraph(2, "third ordinary body paragraph with enough text to avoid short-priority and uniform bias"),
        _paragraph(
            3,
            "chapter start paragraph with enough text to avoid short-priority and rely on gap signal only",
            paragraph_properties_xml='<w:pPr><w:spacing w:before="240"/></w:pPr>',
        ),
        _paragraph(4, "fourth ordinary body paragraph with enough text to avoid short-priority and uniform bias"),
    ]

    descriptors = build_document_map_paragraph_descriptors(paragraphs, preview_chars=120)
    sampled = select_document_map_logical_indexes(descriptors, max_input_paragraphs=1)

    assert sampled == (3,)


def test_build_default_document_map_creates_low_confidence_body_anchors_and_sampling_metadata():
    paragraphs = [
        _paragraph(0, "ordinary body paragraph with enough text to avoid short-priority"),
        _paragraph(1, "BOLD SIGNAL", is_bold=True),
        _paragraph(2, "Contents........ 5", heuristic_structural_role_hint="toc_entry"),
        _paragraph(3, "Gen 1:1"),
        _paragraph(4, "another ordinary body paragraph with enough text to avoid short-priority"),
        _paragraph(5, "Heading", heading_level=1, heading_source="explicit"),
    ]

    document_map = build_default_document_map(
        paragraphs,
        model_used="openrouter:test/document-map",
        max_input_paragraphs=4,
        preview_chars=120,
    )

    assert document_map.body_start_logical_index == 0
    assert document_map.model_used == "openrouter:test/document-map"
    assert document_map.sampled is True
    assert document_map.sampled_logical_indexes == (1, 2, 3, 5)
    assert document_map.get_anchor(0) == DocumentMapAnchor(role="body", heading_level=None, confidence="low")
    assert document_map.get_anchor(5) == DocumentMapAnchor(role="body", heading_level=None, confidence="low")


def test_build_document_map_returns_deterministic_map_when_ai_path_is_disabled_and_emits_progress_events():
    paragraphs = [
        _paragraph(0, "ordinary body paragraph with enough text to avoid short-priority"),
        _paragraph(1, "BOLD SIGNAL", is_bold=True),
        _paragraph(2, "Contents........ 5", heuristic_structural_role_hint="toc_entry"),
        _paragraph(3, "Gen 1:1"),
        _paragraph(4, "another ordinary body paragraph with enough text to avoid short-priority"),
        _paragraph(5, "Heading", heading_level=1, heading_source="explicit"),
    ]
    progress_events = []

    document_map = build_document_map(
        paragraphs,
        client=object(),
        model="",
        timeout=30.0,
        max_input_paragraphs=4,
        max_input_tokens=180000,
        progress_callback=progress_events.append,
    )

    assert document_map.model_used == ""
    assert document_map.sampled is True
    assert document_map.sampled_logical_indexes == (1, 2, 3, 5)
    assert [event.event for event in progress_events] == ["descriptors_built", "completed"]
    assert progress_events[-1].descriptor_count == 6
    assert progress_events[-1].sampled_count == 4


def test_build_document_map_uses_preview_chars_and_token_budget(monkeypatch):
    paragraphs = [
        _paragraph(0, "Alpha " + ("A" * 80), is_bold=True),
        _paragraph(1, "Beta " + ("B" * 80), is_bold=True),
        _paragraph(2, "Gamma " + ("C" * 80), is_bold=True),
    ]

    monkeypatch.setattr(
        "docxaicorrector.structure.document_map._estimate_document_map_descriptor_tokens",
        lambda descriptors: 200 if len(descriptors) > 1 else 50,
    )

    document_map = build_document_map(
        paragraphs,
        client=object(),
        model="",
        timeout=30.0,
        max_input_paragraphs=3,
        max_input_tokens=100,
        preview_chars=5,
    )

    assert len(document_map.sampled_logical_indexes) == 1
    assert document_map.sampled_logical_indexes[0] in {0, 1, 2}

    descriptors = build_document_map_paragraph_descriptors(paragraphs, preview_chars=5)
    assert [descriptor.text_preview for descriptor in descriptors] == ["Alpha", "Beta", "Gamma"]


def test_parse_document_map_payload_fills_missing_anchors_with_default_body_role():
    document_map = _parse_document_map_payload(
        {
            "body_start_logical_index": 0,
            "toc_region": None,
            "outline": [
                {
                    "title": "Chapter 1",
                    "level": 1,
                    "logical_index": 1,
                    "confidence": "high",
                    "evidence": ["bold"],
                }
            ],
            "paragraph_anchors": {
                "1": {"role": "heading", "heading_level": 1, "confidence": "high"}
            },
            "review_zones": [],
        },
        all_logical_indexes={0, 1, 2},
        sampled_logical_indexes=(0, 1),
        model_used="openrouter:test/document-map",
        total_tokens_used=42,
        processing_time_seconds=0.5,
    )

    assert document_map.body_start_logical_index == 0
    assert document_map.outline[0].logical_index == 1
    assert document_map.get_anchor(1) == DocumentMapAnchor(role="heading", heading_level=1, confidence="high")
    assert document_map.get_anchor(2) == DocumentMapAnchor(role="body", heading_level=None, confidence="low")
    assert document_map.total_tokens_used == 42
    assert document_map.sampled is True


def test_parse_document_map_payload_drops_heading_level_for_non_heading_anchor():
    document_map = _parse_document_map_payload(
        {
            "body_start_logical_index": 0,
            "toc_region": None,
            "outline": [],
            "paragraph_anchors": {
                "0": {"role": "body", "heading_level": 1, "confidence": "medium"},
                "1": {"role": "toc_entry", "heading_level": 2, "confidence": "high"},
            },
            "review_zones": [],
        },
        all_logical_indexes={0, 1},
        sampled_logical_indexes=(0, 1),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
    )

    assert document_map.get_anchor(0).role == "body"
    assert document_map.get_anchor(0).heading_level is None
    assert document_map.get_anchor(1).role == "toc_entry"
    assert document_map.get_anchor(1).heading_level is None


def test_parse_document_map_payload_accepts_missing_split_hints_as_empty_tuple():
    document_map = _parse_document_map_payload(
        {
            "body_start_logical_index": 0,
            "toc_region": None,
            "outline": [],
            "paragraph_anchors": {},
            "review_zones": [],
        },
        all_logical_indexes={0, 1},
        sampled_logical_indexes=(0, 1),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
    )

    assert document_map.split_hints == ()


def test_document_map_round_trips_with_split_hints_from_json_payload():
    source = DocumentMap(
        body_start_logical_index=0,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter 1: An Ancient Future?",
                level=1,
                logical_index=1,
                confidence="high",
                evidence=("toc_match",),
                member_logical_indexes=(1, 2),
            ),
        ),
        paragraph_anchors={1: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        split_hints=(
            DocumentMapSplitHint(
                logical_index=1,
                split_kind="page_artifact_heading",
                expected_parts=("artifact", "heading"),
                authority="document_map_outline",
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        model_used="openrouter:test/document-map",
        total_tokens_used=10,
        processing_time_seconds=0.1,
        sampled=False,
        sampled_logical_indexes=(0, 1),
    )

    parsed = _parse_document_map_payload(
        json.loads(json.dumps(asdict(source))),
        all_logical_indexes={0, 1, 2},
        sampled_logical_indexes=(0, 1, 2),
        model_used=source.model_used,
        total_tokens_used=source.total_tokens_used,
        processing_time_seconds=source.processing_time_seconds,
    )

    assert parsed.split_hints == source.split_hints
    assert parsed.outline == source.outline


def test_document_map_round_trips_without_split_hints_from_json_payload():
    source = DocumentMap(
        body_start_logical_index=0,
        toc_region=None,
        outline=(),
        paragraph_anchors={0: DocumentMapAnchor(role="body", heading_level=None, confidence="low")},
        review_zones=(),
        split_hints=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(0,),
    )

    parsed = _parse_document_map_payload(
        json.loads(json.dumps(asdict(source))),
        all_logical_indexes={0},
        sampled_logical_indexes=(0,),
        model_used=source.model_used,
        total_tokens_used=source.total_tokens_used,
        processing_time_seconds=source.processing_time_seconds,
    )

    assert parsed.split_hints == ()


def test_parse_document_map_payload_rejects_unknown_split_kind():
    with pytest.raises(DocumentMapSchemaError, match="Unsupported split kind"):
        _parse_document_map_payload(
            {
                "body_start_logical_index": 0,
                "toc_region": None,
                "outline": [],
                "paragraph_anchors": {},
                "review_zones": [],
                "split_hints": [
                    {
                        "logical_index": 0,
                        "split_kind": "unknown_kind",
                        "expected_parts": ["a", "b"],
                        "authority": "document_map_outline",
                        "confidence": "high",
                        "evidence": ["outline_entry"],
                    }
                ],
            },
            all_logical_indexes={0},
            sampled_logical_indexes=(0,),
            model_used="openrouter:test/document-map",
            total_tokens_used=0,
            processing_time_seconds=0.0,
        )


def test_parse_document_map_payload_coerces_scalar_split_hint_expected_parts_to_single_item_tuple():
    parsed = _parse_document_map_payload(
        {
            "body_start_logical_index": 0,
            "toc_region": None,
            "outline": [],
            "paragraph_anchors": {},
            "review_zones": [],
            "split_hints": [
                {
                    "logical_index": 0,
                    "split_kind": "compound_toc_entries",
                    "expected_parts": "single part",
                    "authority": "document_map_toc",
                    "confidence": "high",
                    "evidence": ["bounded_toc_region"],
                }
            ],
        },
        all_logical_indexes={0},
        sampled_logical_indexes=(0,),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
    )

    assert parsed.split_hints == (
        DocumentMapSplitHint(
            logical_index=0,
            split_kind="compound_toc_entries",
            expected_parts=("single part",),
            authority="document_map_toc",
            confidence="high",
            evidence=("bounded_toc_region",),
        ),
    )


def test_parse_document_map_payload_rejects_out_of_range_split_hint_logical_index():
    with pytest.raises(DocumentMapSchemaError, match="split_hints.logical_index references unknown logical index"):
        _parse_document_map_payload(
            {
                "body_start_logical_index": 0,
                "toc_region": None,
                "outline": [],
                "paragraph_anchors": {},
                "review_zones": [],
                "split_hints": [
                    {
                        "logical_index": 9,
                        "split_kind": "compound_toc_entries",
                        "expected_parts": ["a", "b"],
                        "authority": "document_map_toc",
                        "confidence": "medium",
                        "evidence": ["toc_entry"],
                    }
                ],
            },
            all_logical_indexes={0},
            sampled_logical_indexes=(0,),
            model_used="openrouter:test/document-map",
            total_tokens_used=0,
            processing_time_seconds=0.0,
        )


def test_parse_document_map_payload_accepts_outline_member_logical_indexes():
    parsed = _parse_document_map_payload(
        {
            "body_start_logical_index": 0,
            "toc_region": None,
            "outline": [
                {
                    "title": "11 Governance and We, the Citizens: An Ancient Future?",
                    "level": 1,
                    "logical_index": 1,
                    "confidence": "high",
                    "evidence": ["toc_match", "body_heading_match"],
                    "member_logical_indexes": [1, 2, 3, 4],
                }
            ],
            "paragraph_anchors": {},
            "review_zones": [],
            "split_hints": [],
        },
        all_logical_indexes={0, 1, 2, 3, 4},
        sampled_logical_indexes=(0, 1, 2, 3, 4),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
    )

    assert parsed.outline == (
        DocumentMapOutlineEntry(
            title="11 Governance and We, the Citizens: An Ancient Future?",
            level=1,
            logical_index=1,
            confidence="high",
            evidence=("toc_match", "body_heading_match"),
            member_logical_indexes=(1, 2, 3, 4),
        ),
    )


def test_document_map_round_trip_preserves_outline_member_logical_indexes_and_full_title_in_json_payload():
    source = DocumentMap(
        body_start_logical_index=1,
        toc_region=DocumentMapTocRegion(
            start_logical_index=0,
            end_logical_index=0,
            header_logical_index=None,
            entries=(
                DocumentMapTocEntry(
                    title="11 Governance and We, the Citizens: An Ancient Future?",
                    target_level=1,
                    candidate_body_logical_index=1,
                    confidence="high",
                ),
            ),
            confidence="high",
        ),
        outline=(
            DocumentMapOutlineEntry(
                title="11 Governance and We, the Citizens: An Ancient Future?",
                level=1,
                logical_index=1,
                confidence="high",
                evidence=("toc_match", "body_heading_match"),
                member_logical_indexes=(1, 2, 3, 4),
            ),
        ),
        paragraph_anchors={1: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        split_hints=(),
        sampled=False,
        sampled_logical_indexes=(0, 1, 2, 3, 4),
    )

    parsed = _parse_document_map_payload(
        json.loads(json.dumps(asdict(source))),
        all_logical_indexes={0, 1, 2, 3, 4},
        sampled_logical_indexes=(0, 1, 2, 3, 4),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
    )

    assert parsed.outline == source.outline
    assert parsed.toc_region == source.toc_region


def test_parse_document_map_payload_rejects_outline_member_logical_indexes_without_anchor():
    with pytest.raises(DocumentMapSchemaError, match="outline.member_logical_indexes must include outline.logical_index"):
        _parse_document_map_payload(
            {
                "body_start_logical_index": 0,
                "toc_region": None,
                "outline": [
                    {
                        "title": "Chapter 11",
                        "level": 1,
                        "logical_index": 1,
                        "confidence": "high",
                        "evidence": ["outline_entry"],
                        "member_logical_indexes": [2, 3],
                    }
                ],
                "paragraph_anchors": {},
                "review_zones": [],
                "split_hints": [],
            },
            all_logical_indexes={0, 1, 2, 3},
            sampled_logical_indexes=(0, 1, 2, 3),
            model_used="openrouter:test/document-map",
            total_tokens_used=0,
            processing_time_seconds=0.0,
        )


def test_parse_document_map_payload_rejects_non_contiguous_outline_member_logical_indexes():
    with pytest.raises(DocumentMapSchemaError, match="outline.member_logical_indexes must be contiguous"):
        _parse_document_map_payload(
            {
                "body_start_logical_index": 0,
                "toc_region": None,
                "outline": [
                    {
                        "title": "Chapter 11",
                        "level": 1,
                        "logical_index": 1,
                        "confidence": "high",
                        "evidence": ["outline_entry"],
                        "member_logical_indexes": [1, 3],
                    }
                ],
                "paragraph_anchors": {},
                "review_zones": [],
                "split_hints": [],
            },
            all_logical_indexes={0, 1, 2, 3},
            sampled_logical_indexes=(0, 1, 2, 3),
            model_used="openrouter:test/document-map",
            total_tokens_used=0,
            processing_time_seconds=0.0,
        )


def test_parse_document_map_payload_normalizes_review_zone_severity_synonyms():
    document_map = _parse_document_map_payload(
        {
            "body_start_logical_index": 0,
            "toc_region": None,
            "outline": [],
            "paragraph_anchors": {},
            "review_zones": [
                {"start_logical_index": 0, "end_logical_index": 0, "reason": "minor", "severity": "minor"},
                {"start_logical_index": 1, "end_logical_index": 1, "reason": "minor", "severity": "low"},
                {"start_logical_index": 2, "end_logical_index": 2, "reason": "check", "severity": "medium"},
                {"start_logical_index": 3, "end_logical_index": 3, "reason": "severe", "severity": "high"},
            ],
        },
        all_logical_indexes={0, 1, 2, 3},
        sampled_logical_indexes=(0, 1, 2, 3),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
    )

    assert [zone.severity for zone in document_map.review_zones] == ["info", "info", "warning", "critical"]


def test_parse_document_map_payload_drops_outline_entries_inside_toc_region():
    document_map = _parse_document_map_payload(
        {
            "body_start_logical_index": 2,
            "toc_region": {
                "start_logical_index": 0,
                "end_logical_index": 1,
                "header_logical_index": 0,
                "entries": [],
                "confidence": "medium",
            },
            "outline": [
                {
                    "title": "Contents placeholder",
                    "level": 1,
                    "logical_index": 0,
                    "confidence": "low",
                    "evidence": ["toc_region"],
                },
                {
                    "title": "Chapter 1",
                    "level": 1,
                    "logical_index": 2,
                    "confidence": "high",
                    "evidence": ["bold"],
                },
            ],
            "paragraph_anchors": {
                "2": {"role": "heading", "heading_level": 1, "confidence": "high"}
            },
            "review_zones": [],
        },
        all_logical_indexes={0, 1, 2},
        sampled_logical_indexes=(0, 1, 2),
        model_used="openrouter:test/document-map",
        total_tokens_used=42,
        processing_time_seconds=0.5,
    )

    assert [entry.logical_index for entry in document_map.outline] == [2]


def test_parse_document_map_payload_rejects_unknown_logical_indexes():
    with pytest.raises(DocumentMapSchemaError):
        _parse_document_map_payload(
            {
                "body_start_logical_index": 99,
                "toc_region": None,
                "outline": [],
                "paragraph_anchors": {},
                "review_zones": [],
            },
            all_logical_indexes={0, 1, 2},
            sampled_logical_indexes=(0, 1, 2),
            model_used="openrouter:test/document-map",
            total_tokens_used=0,
            processing_time_seconds=0.0,
        )


def test_parse_document_map_payload_rejects_non_string_outline_evidence_entries():
    with pytest.raises(DocumentMapSchemaError, match="outline evidence items must be strings"):
        _parse_document_map_payload(
            {
                "body_start_logical_index": 0,
                "toc_region": None,
                "outline": [
                    {
                        "title": "Chapter 1",
                        "level": 1,
                        "logical_index": 1,
                        "confidence": "high",
                        "evidence": ["bold", 7],
                    }
                ],
                "paragraph_anchors": {},
                "review_zones": [],
            },
            all_logical_indexes={0, 1, 2},
            sampled_logical_indexes=(0, 1, 2),
            model_used="openrouter:test/document-map",
            total_tokens_used=0,
            processing_time_seconds=0.0,
        )


def test_build_document_map_uses_ai_payload_when_available(monkeypatch):
    paragraphs = [_paragraph(0, "Contents"), _paragraph(1, "Chapter 1", is_bold=True)]

    monkeypatch.setattr(
        "docxaicorrector.structure.document_map._generate_document_map_from_ai",
        lambda **kwargs: _parse_document_map_payload(
            {
                "body_start_logical_index": 1,
                "toc_region": {
                    "start_logical_index": 0,
                    "end_logical_index": 0,
                    "header_logical_index": 0,
                    "entries": [],
                    "confidence": "medium",
                },
                "outline": [
                    {
                        "title": "Chapter 1",
                        "level": 1,
                        "logical_index": 1,
                        "confidence": "high",
                        "evidence": ["bold"],
                    }
                ],
                "paragraph_anchors": {
                    "1": {"role": "heading", "heading_level": 1, "confidence": "high"}
                },
                "review_zones": [],
            },
            all_logical_indexes={0, 1},
            sampled_logical_indexes=(0, 1),
            model_used="openrouter:test/document-map",
            total_tokens_used=17,
            processing_time_seconds=0.0,
        ),
    )

    document_map = build_document_map(
        paragraphs,
        client=object(),
        model="openrouter:test/document-map",
        timeout=30.0,
        max_input_paragraphs=10,
        max_input_tokens=180000,
    )

    assert document_map.body_start_logical_index == 1
    assert document_map.toc_region is not None
    assert document_map.get_anchor(1) == DocumentMapAnchor(role="heading", heading_level=1, confidence="high")


def test_build_document_map_recovers_missing_toc_and_outline_entry_from_candidate_body_heading(monkeypatch):
    paragraphs = [
        _paragraph(35, "Contents", structural_role="toc_header"),
        _paragraph(36, "8 Strategies for Governments 141", structural_role="toc_entry"),
        _paragraph(37, "9 Strategies for NGOs 159", structural_role="toc_entry"),
        _paragraph(38, "10 Truth and Consequences 179", structural_role="toc_entry"),
        _paragraph(141, "STRATEGIES FOR GOVERNMENTS", role="heading", structural_role="body"),
        _paragraph(159, "STRATEGIES FOR NGOS", role="heading", structural_role="body"),
        _paragraph(179, "TRUTH AND CONSEQUENCES", role="heading", structural_role="body"),
    ]

    monkeypatch.setattr(
        "docxaicorrector.structure.document_map._generate_document_map_from_ai",
        lambda **kwargs: _parse_document_map_payload(
            {
                "body_start_logical_index": 141,
                "toc_region": {
                    "start_logical_index": 35,
                    "end_logical_index": 38,
                    "header_logical_index": 35,
                    "entries": [
                        {
                            "title": "Strategies for Governments",
                            "target_level": 1,
                            "candidate_body_logical_index": 141,
                            "confidence": "high",
                        },
                        {
                            "title": "Truth and Consequences",
                            "target_level": 1,
                            "candidate_body_logical_index": 159,
                            "confidence": "high",
                        },
                        {
                            "title": "Truth and Consequences",
                            "target_level": 1,
                            "candidate_body_logical_index": 179,
                            "confidence": "high",
                        },
                    ],
                    "confidence": "high",
                },
                "outline": [
                    {
                        "title": "Strategies for Governments",
                        "level": 1,
                        "logical_index": 141,
                        "confidence": "high",
                        "evidence": ["toc_match"],
                    },
                    {
                        "title": "Truth and Consequences",
                        "level": 1,
                        "logical_index": 179,
                        "confidence": "high",
                        "evidence": ["toc_match"],
                    },
                ],
                "paragraph_anchors": {
                    "141": {"role": "heading", "heading_level": 1, "confidence": "high"},
                    "159": {"role": "heading", "heading_level": 1, "confidence": "high"},
                    "179": {"role": "heading", "heading_level": 1, "confidence": "high"},
                },
                "review_zones": [],
            },
            all_logical_indexes={35, 36, 37, 38, 141, 159, 179},
            sampled_logical_indexes=(35, 36, 37, 38, 141, 159, 179),
            model_used="openrouter:test/document-map",
            total_tokens_used=17,
            processing_time_seconds=0.0,
        ),
    )

    document_map = build_document_map(
        paragraphs,
        client=object(),
        model="openrouter:test/document-map",
        timeout=30.0,
        max_input_paragraphs=20,
        max_input_tokens=180000,
    )

    assert document_map.toc_region is not None
    assert [entry.title for entry in document_map.toc_region.entries] == [
        "Strategies for Governments",
        "STRATEGIES FOR NGOS",
        "Truth and Consequences",
    ]
    assert [entry.candidate_body_logical_index for entry in document_map.toc_region.entries] == [141, 159, 179]
    assert [entry.title for entry in document_map.outline] == [
        "Strategies for Governments",
        "STRATEGIES FOR NGOS",
        "Truth and Consequences",
    ]
    assert [entry.logical_index for entry in document_map.outline] == [141, 159, 179]


def test_build_document_map_recovers_missing_chapter_sequence_from_heading_gap(monkeypatch):
    paragraphs = [
        _paragraph(35, "Contents", structural_role="toc_header"),
        _paragraph(40, "8 Strategies for Governments 141 9 Strategies for NGOs 159", structural_role="toc_entry"),
        _paragraph(42, "10 Truth and Consequences: Lessons Learned 175", structural_role="toc_entry"),
        _paragraph(141, "Chapter Eight", role="heading", structural_role="body"),
        _paragraph(142, "STRATEGIES FOR GOVERNMENTS", role="heading", structural_role="body"),
        _paragraph(159, "Chapter Nine", role="heading", structural_role="body"),
        _paragraph(160, "STRATEGIES FOR NGOS", role="heading", structural_role="body"),
        _paragraph(175, "Chapter Ten", role="heading", structural_role="body"),
        _paragraph(176, "TRUTH AND CONSEQUENCES", role="heading", structural_role="body"),
    ]

    monkeypatch.setattr(
        "docxaicorrector.structure.document_map._generate_document_map_from_ai",
        lambda **kwargs: _parse_document_map_payload(
            {
                "body_start_logical_index": 141,
                "toc_region": {
                    "start_logical_index": 35,
                    "end_logical_index": 42,
                    "header_logical_index": 35,
                    "entries": [
                        {
                            "title": "8 Strategies for Governments",
                            "target_level": 1,
                            "candidate_body_logical_index": 141,
                            "confidence": "high",
                        },
                        {
                            "title": "10 Truth and Consequences: Lessons Learned",
                            "target_level": 1,
                            "candidate_body_logical_index": 175,
                            "confidence": "high",
                        },
                    ],
                    "confidence": "high",
                },
                "outline": [
                    {
                        "title": "Chapter Eight",
                        "level": 1,
                        "logical_index": 141,
                        "confidence": "high",
                        "evidence": ["toc_match"],
                    },
                    {
                        "title": "Chapter Ten",
                        "level": 1,
                        "logical_index": 175,
                        "confidence": "high",
                        "evidence": ["toc_match"],
                    },
                ],
                "paragraph_anchors": {
                    "141": {"role": "heading", "heading_level": 1, "confidence": "high"},
                    "142": {"role": "heading", "heading_level": 2, "confidence": "high"},
                    "159": {"role": "heading", "heading_level": 1, "confidence": "high"},
                    "160": {"role": "heading", "heading_level": 2, "confidence": "high"},
                    "175": {"role": "heading", "heading_level": 1, "confidence": "high"},
                    "176": {"role": "heading", "heading_level": 2, "confidence": "high"},
                },
                "review_zones": [],
            },
            all_logical_indexes={35, 40, 42, 141, 142, 159, 160, 175, 176},
            sampled_logical_indexes=(35, 40, 42, 141, 142, 159, 160, 175, 176),
            model_used="openrouter:test/document-map",
            total_tokens_used=17,
            processing_time_seconds=0.0,
        ),
    )

    document_map = build_document_map(
        paragraphs,
        client=object(),
        model="openrouter:test/document-map",
        timeout=30.0,
        max_input_paragraphs=20,
        max_input_tokens=180000,
    )

    assert document_map.toc_region is not None
    assert [entry.candidate_body_logical_index for entry in document_map.toc_region.entries] == [141, 159, 175]
    assert [entry.title for entry in document_map.toc_region.entries] == [
        "8 Strategies for Governments",
        "STRATEGIES FOR NGOS",
        "10 Truth and Consequences: Lessons Learned",
    ]
    assert [entry.title for entry in document_map.outline] == ["Chapter Eight", "Chapter Nine", "Chapter Ten"]
    assert [entry.logical_index for entry in document_map.outline] == [141, 159, 175]


def test_build_document_map_recovers_compound_toc_entries_and_split_hint_from_bounded_toc_region(monkeypatch):
    paragraphs = [
        _paragraph(0, "Contents", structural_role="toc_header"),
        _paragraph(
            1,
            "8 Strategies for Governments 141 9 Strategies for NGOs 159 10 Truth and Consequences 175",
            structural_role="toc_entry",
        ),
        _paragraph(141, "STRATEGIES FOR GOVERNMENTS", role="heading", structural_role="body"),
        _paragraph(159, "STRATEGIES FOR NGOS", role="heading", structural_role="body"),
        _paragraph(175, "TRUTH AND CONSEQUENCES", role="heading", structural_role="body"),
    ]

    monkeypatch.setattr(
        "docxaicorrector.structure.document_map._generate_document_map_from_ai",
        lambda **kwargs: _parse_document_map_payload(
            {
                "body_start_logical_index": 141,
                "toc_region": {
                    "start_logical_index": 0,
                    "end_logical_index": 1,
                    "header_logical_index": 0,
                    "entries": [],
                    "confidence": "high",
                },
                "outline": [
                    {
                        "title": "STRATEGIES FOR GOVERNMENTS",
                        "level": 1,
                        "logical_index": 141,
                        "confidence": "high",
                        "evidence": ["toc_match"],
                    },
                    {
                        "title": "STRATEGIES FOR NGOS",
                        "level": 1,
                        "logical_index": 159,
                        "confidence": "high",
                        "evidence": ["toc_match"],
                    },
                    {
                        "title": "TRUTH AND CONSEQUENCES",
                        "level": 1,
                        "logical_index": 175,
                        "confidence": "high",
                        "evidence": ["toc_match"],
                    },
                ],
                "paragraph_anchors": {
                    "0": {"role": "body", "heading_level": None, "confidence": "low"},
                    "1": {"role": "body", "heading_level": None, "confidence": "low"},
                    "141": {"role": "heading", "heading_level": 1, "confidence": "high"},
                    "159": {"role": "heading", "heading_level": 1, "confidence": "high"},
                    "175": {"role": "heading", "heading_level": 1, "confidence": "high"},
                },
                "review_zones": [],
                "split_hints": [],
            },
            all_logical_indexes={0, 1, 141, 159, 175},
            sampled_logical_indexes=(0, 1, 141, 159, 175),
            model_used="openrouter:test/document-map",
            total_tokens_used=17,
            processing_time_seconds=0.0,
        ),
    )

    document_map = build_document_map(
        paragraphs,
        client=object(),
        model="openrouter:test/document-map",
        timeout=30.0,
        max_input_paragraphs=20,
        max_input_tokens=180000,
    )

    assert document_map.toc_region is not None
    assert document_map.get_anchor(0) == DocumentMapAnchor(role="toc_header", heading_level=None, confidence="high")
    assert document_map.get_anchor(1) == DocumentMapAnchor(role="toc_entry", heading_level=None, confidence="high")
    assert [entry.title for entry in document_map.toc_region.entries] == [
        "STRATEGIES FOR GOVERNMENTS",
        "STRATEGIES FOR NGOS",
        "TRUTH AND CONSEQUENCES",
    ]
    assert [entry.candidate_body_logical_index for entry in document_map.toc_region.entries] == [141, 159, 175]
    assert document_map.split_hints == (
        DocumentMapSplitHint(
            logical_index=1,
            split_kind="compound_toc_entries",
            expected_parts=(
                "STRATEGIES FOR GOVERNMENTS",
                "STRATEGIES FOR NGOS",
                "TRUTH AND CONSEQUENCES",
            ),
            authority="document_map_toc",
            confidence="high",
            evidence=("bounded_toc_region", "one_to_one_toc_entry_match", "toc_entry"),
        ),
    )


def test_build_document_map_retries_once_after_schema_error(monkeypatch):
    paragraphs = [_paragraph(0, "Contents"), _paragraph(1, "Chapter 1", is_bold=True)]
    calls = {"count": 0}

    def _fake_request_document_map_payload(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return ("{\"body_start_logical_index\": 99}", 0)
        return (
            json.dumps(
                {
                    "body_start_logical_index": 1,
                    "toc_region": None,
                    "outline": [],
                    "paragraph_anchors": {
                        "1": {"role": "heading", "heading_level": 1, "confidence": "high"}
                    },
                    "review_zones": [],
                },
                ensure_ascii=False,
            ),
            0,
        )

    monkeypatch.setattr("docxaicorrector.structure.document_map._request_document_map_payload", _fake_request_document_map_payload)

    class _FakeResponses:
        def create(self, *, model, input, timeout):
            raise AssertionError("create should not be called directly in this test")

    class _FakeResponsesClient:
        responses = _FakeResponses()

    document_map = build_document_map(
        paragraphs,
        client=_FakeResponsesClient(),
        model="openrouter:test/document-map",
        timeout=30.0,
        max_input_paragraphs=10,
        max_input_tokens=180000,
    )

    assert calls["count"] == 2
    assert document_map.body_start_logical_index == 1


def test_build_document_map_saves_malformed_artifact_after_terminal_schema_failure(monkeypatch, tmp_path):
    paragraphs = [_paragraph(0, "Contents"), _paragraph(1, "Chapter 1", is_bold=True)]
    calls = {"count": 0}

    def _fake_request_document_map_payload(**kwargs):
        calls["count"] += 1
        return ("{\"body_start_logical_index\": 99}", 0)

    monkeypatch.setattr("docxaicorrector.structure.document_map._request_document_map_payload", _fake_request_document_map_payload)
    monkeypatch.setattr("docxaicorrector.structure.document_map._DOCUMENT_MAP_MALFORMED_DIR", tmp_path)

    class _FakeResponses:
        def create(self, *, model, input, timeout):
            raise AssertionError("create should not be called directly in this test")

    class _FakeResponsesClient:
        responses = _FakeResponses()

    with pytest.raises(DocumentMapSchemaError):
        build_document_map(
            paragraphs,
            client=_FakeResponsesClient(),
            model="openrouter:test/document-map",
            timeout=30.0,
            max_input_paragraphs=10,
            max_input_tokens=180000,
        )

    artifacts = list(tmp_path.glob("*.malformed.json"))

    assert calls["count"] == 2
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["artifact_kind"] == "document_map_malformed_output"
    assert payload["model"] == "openrouter:test/document-map"
    assert payload["schema_error_summary"]
    assert payload["raw_payload"] == "{\"body_start_logical_index\": 99}"
