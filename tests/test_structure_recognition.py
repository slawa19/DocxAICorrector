from typing import cast
from types import SimpleNamespace

from models import ParagraphClassification, ParagraphUnit, StructureMap
import structure_recognition


def _paragraph(
    *,
    source_index: int,
    text: str,
    role: str = "body",
    structural_role: str = "body",
    role_confidence: str = "heuristic",
    style_name: str = "Body Text",
    is_bold: bool = False,
    paragraph_alignment: str | None = None,
    font_size_pt: float | None = None,
    list_kind: str | None = None,
    heading_level: int | None = None,
    heading_source: str | None = None,
):
    return ParagraphUnit(
        text=text,
        role=role,
        structural_role=structural_role,
        role_confidence=role_confidence,
        style_name=style_name,
        is_bold=is_bold,
        paragraph_alignment=paragraph_alignment,
        font_size_pt=font_size_pt,
        list_kind=list_kind,
        source_index=source_index,
        heading_level=heading_level,
        heading_source=heading_source,
    )


def test_build_paragraph_descriptors_skips_blank_paragraphs_and_preserves_metadata():
    paragraphs = [
        _paragraph(source_index=0, text="  "),
        _paragraph(source_index=1, text="ГЛАВА 1", role="heading", style_name="Heading 1", is_bold=True, paragraph_alignment="center", font_size_pt=16.0, heading_level=1, heading_source="explicit"),
        _paragraph(source_index=2, text="Первый пункт", role="list", list_kind="ordered", style_name="List Paragraph"),
    ]

    descriptors = structure_recognition.build_paragraph_descriptors(paragraphs)

    assert [descriptor.index for descriptor in descriptors] == [1, 2]
    assert descriptors[0].explicit_heading_level == 1
    assert descriptors[0].is_centered is True
    assert descriptors[0].is_all_caps is True
    assert descriptors[0].context_after_preview == "Первый пункт"
    assert descriptors[1].has_numbering is True


def test_build_paragraph_descriptors_includes_richer_context_and_risk_flags():
    paragraphs = [
        _paragraph(source_index=0, text="Содержание"),
        _paragraph(source_index=1, text="Mark 13:13"),
        _paragraph(source_index=2, text="●"),
        _paragraph(source_index=3, text="Очень длинный абзац " + ("текста " * 200)),
    ]

    descriptors = structure_recognition.build_paragraph_descriptors(paragraphs)

    assert descriptors[0].toc_candidate is True
    assert descriptors[0].context_after_preview == "Mark 13:13"
    assert descriptors[1].scripture_reference_candidate is True
    assert descriptors[1].context_before_preview == "Содержание"
    assert descriptors[2].isolated_marker is True
    assert len(descriptors[3].text_preview) == 600


def test_apply_structure_map_respects_explicit_and_adjacent_priority_rules():
    explicit_heading = _paragraph(source_index=0, text="Глава", role="heading", role_confidence="explicit", heading_level=1, heading_source="explicit")
    adjacent_caption = _paragraph(source_index=1, text="Рисунок 1", role="caption", role_confidence="adjacent", structural_role="caption")
    heuristic_body = _paragraph(source_index=2, text="Переосмысление богатства", role="body")
    heuristic_heading = _paragraph(source_index=3, text="ЭПИКТЕТ", role="heading", structural_role="heading", role_confidence="heuristic", heading_level=2, heading_source="heuristic")
    structure_map = StructureMap(
        classifications={
            0: ParagraphClassification(index=0, role="body", heading_level=None, confidence="high"),
            1: ParagraphClassification(index=1, role="body", heading_level=None, confidence="high"),
            2: ParagraphClassification(index=2, role="heading", heading_level=3, confidence="high"),
            3: ParagraphClassification(index=3, role="attribution", heading_level=None, confidence="medium"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=10,
        processing_time_seconds=0.1,
        window_count=1,
    )

    structure_recognition.apply_structure_map(
        [explicit_heading, adjacent_caption, heuristic_body, heuristic_heading],
        structure_map,
    )

    assert explicit_heading.role == "heading"
    assert adjacent_caption.role == "caption"
    assert heuristic_body.role == "heading"
    assert heuristic_body.heading_level == 3
    assert heuristic_body.role_confidence == "ai"
    assert heuristic_heading.role == "body"
    assert heuristic_heading.structural_role == "attribution"
    assert heuristic_heading.heading_level is None
    assert heuristic_heading.heading_source is None


def test_iter_descriptor_windows_uses_overlap_for_large_inputs():
    descriptors = [
        SimpleNamespace(index=index)
        for index in range(6)
    ]

    windows = list(
        structure_recognition._iter_descriptor_windows(
            cast(list, descriptors),
            max_window_paragraphs=4,
            overlap_paragraphs=1,
        )
    )

    assert [[descriptor.index for descriptor in window] for window in windows] == [
        [0, 1, 2, 3],
        [3, 4, 5],
    ]


def test_build_structure_map_returns_empty_map_on_classifier_failure(monkeypatch):
    paragraphs = [_paragraph(source_index=0, text="Глава")]
    monkeypatch.setattr(
        structure_recognition,
        "_classify_descriptor_window",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    structure_map = structure_recognition.build_structure_map(
        paragraphs,
        client=object(),
        model="gpt-4o-mini",
    )

    assert structure_map.classifications == {}
    assert structure_map.window_count == 1


def test_build_structure_map_keeps_successful_windows_when_later_window_fails(monkeypatch):
    paragraphs = [
        _paragraph(source_index=0, text="ГЛАВА 1"),
        _paragraph(source_index=1, text="Основной текст"),
        _paragraph(source_index=2, text="Подзаголовок"),
    ]
    calls = {"count": 0}

    def _classify(**kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("boom")
        return ([ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")], 11)

    monkeypatch.setattr(structure_recognition, "_classify_descriptor_window", _classify)

    structure_map = structure_recognition.build_structure_map(
        paragraphs,
        client=object(),
        model="gpt-4o-mini",
        max_window_paragraphs=2,
        overlap_paragraphs=1,
    )

    assert structure_map.window_count == 2
    assert structure_map.total_tokens_used == 11
    assert structure_map.get(0) == ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")


def test_build_structure_map_splits_timeout_windows_and_merges_subwindow_results(monkeypatch):
    paragraphs = [
        _paragraph(source_index=0, text="Heading A"),
        _paragraph(source_index=1, text="Body A"),
        _paragraph(source_index=2, text="Heading B"),
        _paragraph(source_index=3, text="Body B"),
    ]
    calls: list[list[int]] = []

    class APITimeoutError(Exception):
        pass

    def _classify(**kwargs):
        descriptors = list(kwargs["descriptors"])
        calls.append([descriptor.index for descriptor in descriptors])
        if len(descriptors) > 2:
            raise APITimeoutError("Request timed out.")
        return (
            [
                ParagraphClassification(
                    index=descriptor.index,
                    role="heading" if descriptor.index % 2 == 0 else "body",
                    heading_level=1 if descriptor.index % 2 == 0 else None,
                    confidence="high",
                )
                for descriptor in descriptors
            ],
            len(descriptors) * 10,
        )

    monkeypatch.setattr(structure_recognition, "_classify_descriptor_window", _classify)

    structure_map = structure_recognition.build_structure_map(
        paragraphs,
        client=object(),
        model="gpt-4o-mini",
        max_window_paragraphs=4,
        overlap_paragraphs=1,
    )

    assert calls == [[0, 1, 2, 3], [0, 1], [2, 3]]
    assert structure_map.window_count == 2
    assert structure_map.total_tokens_used == 40
    assert structure_map.get(0) == ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")
    assert structure_map.get(1) == ParagraphClassification(index=1, role="body", heading_level=None, confidence="high")
    assert structure_map.get(2) == ParagraphClassification(index=2, role="heading", heading_level=1, confidence="high")
    assert structure_map.get(3) == ParagraphClassification(index=3, role="body", heading_level=None, confidence="high")


def test_classify_descriptor_window_normalizes_fenced_json_output(monkeypatch):
    captured = {}

    class _FakeClient:
        class responses:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    output_text='```json\n[{"i": 3, "r": "heading", "l": 2, "c": "high"}]\n```',
                    usage=SimpleNamespace(total_tokens=42),
                    status="completed",
                )

    classifications, total_tokens = structure_recognition._classify_descriptor_window(
        client=cast(structure_recognition._StructureRecognitionClient, _FakeClient()),
        model="gpt-5.4",
        descriptors=cast(list, [SimpleNamespace(to_prompt_dict=lambda: {"i": 3})]),
        timeout=12.0,
    )

    assert captured["input"][0]["content"][0]["type"] == "input_text"
    assert captured["input"][1]["content"][0]["type"] == "input_text"
    assert total_tokens == 42
    assert classifications == [
        ParagraphClassification(index=3, role="heading", heading_level=2, confidence="high", rationale=None)
    ]


def test_parse_classification_payload_accepts_compact_json_array():
    classifications = structure_recognition._parse_classification_payload(
        '[{"i": 3, "r": "heading", "l": 2, "c": "high"}, {"i": 4, "r": "body", "l": null, "c": "medium"}]'
    )

    assert classifications == [
        ParagraphClassification(index=3, role="heading", heading_level=2, confidence="high", rationale=None),
        ParagraphClassification(index=4, role="body", heading_level=None, confidence="medium", rationale=None),
    ]


def test_parse_classification_payload_rejects_invalid_role_and_confidence():
    try:
        structure_recognition._parse_classification_payload('[{"i": 1, "r": "__del__", "l": null, "c": "high"}]')
    except ValueError as exc:
        assert "role" in str(exc)
    else:
        raise AssertionError("Expected invalid AI role to be rejected")

    try:
        structure_recognition._parse_classification_payload('[{"i": 1, "r": "body", "l": null, "c": "wild"}]')
    except ValueError as exc:
        assert "confidence" in str(exc)
    else:
        raise AssertionError("Expected invalid AI confidence to be rejected")


def test_parse_classification_payload_clamps_heading_level():
    classifications = structure_recognition._parse_classification_payload(
        '[{"i": 3, "r": "heading", "l": 99, "c": "high"}, {"i": 4, "r": "heading", "l": -3, "c": "medium"}]'
    )

    assert classifications == [
        ParagraphClassification(index=3, role="heading", heading_level=6, confidence="high", rationale=None),
        ParagraphClassification(index=4, role="heading", heading_level=1, confidence="medium", rationale=None),
    ]
