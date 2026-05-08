import json

import pytest

from docxaicorrector.core.models import DocumentMapAnchor, ParagraphUnit
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


def test_build_document_map_returns_deterministic_fallback_and_emits_progress_events():
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
        model="openrouter:test/document-map",
        timeout=30.0,
        max_input_paragraphs=4,
        max_input_tokens=180000,
        progress_callback=progress_events.append,
    )

    assert document_map.model_used == "openrouter:test/document-map"
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
        model="openrouter:test/document-map",
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

    document_map = build_document_map(
        paragraphs,
        client=_FakeResponsesClient(),
        model="openrouter:test/document-map",
        timeout=30.0,
        max_input_paragraphs=10,
        max_input_tokens=180000,
    )

    artifacts = list(tmp_path.glob("*.malformed.json"))

    assert calls["count"] == 2
    assert document_map.body_start_logical_index == 0
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["artifact_kind"] == "document_map_malformed_output"
    assert payload["model"] == "openrouter:test/document-map"
    assert payload["schema_error_summary"]
    assert payload["raw_payload"] == "{\"body_start_logical_index\": 99}"