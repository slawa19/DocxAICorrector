from io import BytesIO
import json
from threading import Event, Thread

from docx import Document
import pytest

import docxaicorrector.document.segments as document_segments
import docxaicorrector.processing.preparation as preparation
from docxaicorrector.core.config import ModelRegistry, TextModelConfig
from docxaicorrector.core.models import DocumentBlock
from docxaicorrector.core.models import ImageAsset, ImageVariantCandidate
from docxaicorrector.core.models import LayoutArtifactCleanupReport, ParagraphBoundaryNormalizationReport
from docxaicorrector.core.models import DocumentMap, DocumentMapAnchor, DocumentMapOutlineEntry, EmbeddedStructureHint, ParagraphClassification, ParagraphUnit, StructureMap
from docxaicorrector.core.models import StructureRecognitionSummary, StructureRepairReport
from docxaicorrector.document.segments import CHAPTER_SEGMENTS_DETECTOR_VERSION
from docxaicorrector.processing.processing_runtime import FrozenUploadPayload, build_in_memory_uploaded_file, build_preparation_request_marker


def setup_function():
    preparation.clear_preparation_cache(clear_shared=True)


def _build_report(*, raw=0, logical=0, merged_groups=0, merged_raw=0):
    return ParagraphBoundaryNormalizationReport(
        total_raw_paragraphs=raw,
        total_logical_paragraphs=logical,
        merged_group_count=merged_groups,
        merged_raw_paragraph_count=merged_raw,
    )


def _build_cleanup_report(*, original=0, cleaned=0, removed=0, page_numbers=0, repeated=0):
    return LayoutArtifactCleanupReport(
        original_paragraph_count=original,
        cleaned_paragraph_count=cleaned,
        removed_paragraph_count=removed,
        removed_page_number_count=page_numbers,
        removed_repeated_artifact_count=repeated,
        removed_empty_or_whitespace_count=0,
        cleanup_applied=True,
    )


def test_build_layout_cleanup_status_note_includes_empty_paragraphs():
    note = preparation.build_layout_cleanup_status_note(
        LayoutArtifactCleanupReport(
            original_paragraph_count=5,
            cleaned_paragraph_count=2,
            removed_paragraph_count=3,
            removed_page_number_count=1,
            removed_repeated_artifact_count=1,
            removed_empty_or_whitespace_count=1,
            cleanup_applied=True,
        )
    )

    assert note == "Очистка: удалено 3 служебных элементов (1 номеров страниц, 1 повторяющихся колонтитулов, 1 пустых абзацев)."


def test_build_layout_cleanup_status_note_uses_flagged_counts_for_signal_mode():
    note = preparation.build_layout_cleanup_status_note(
        LayoutArtifactCleanupReport(
            original_paragraph_count=5,
            cleaned_paragraph_count=5,
            removed_paragraph_count=0,
            removed_page_number_count=0,
            removed_repeated_artifact_count=0,
            removed_empty_or_whitespace_count=0,
            cleanup_applied=True,
            cleanup_mode="flag",
            flagged_page_number_count=1,
            flagged_repeated_artifact_count=1,
            flagged_empty_or_whitespace_count=1,
        )
    )

    assert note == "Очистка: помечено 3 служебных элементов (1 номеров страниц, 1 повторяющихся колонтитулов, 1 пустых абзацев)."


def test_flatten_layout_cleanup_metrics_includes_empty_paragraphs():
    metrics = preparation.flatten_layout_cleanup_metrics(
        LayoutArtifactCleanupReport(
            original_paragraph_count=5,
            cleaned_paragraph_count=2,
            removed_paragraph_count=3,
            removed_page_number_count=1,
            removed_repeated_artifact_count=1,
            removed_empty_or_whitespace_count=1,
            cleanup_applied=True,
        )
    )

    assert metrics == {
        "layout_cleanup_removed_count": 3,
        "layout_cleanup_page_number_count": 1,
        "layout_cleanup_repeated_artifact_count": 1,
        "layout_cleanup_empty_or_whitespace_count": 1,
    }


def test_prepare_document_for_processing_normalizes_layout_cleanup_cache_key(monkeypatch):
    calls = {"count": 0}
    session_state = {"preparation_cache": {}}
    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (
            "image_caption",
            "table_caption",
            "epigraph_attribution",
            "toc_region",
        ),
        "layout_artifact_cleanup_enabled": True,
        "layout_artifact_cleanup_min_repeat_count": 1,
        "layout_artifact_cleanup_max_repeated_text_chars": 0,
        "structure_recognition_enabled": False,
        "structure_recognition_mode": "off",
        "structure_validation_enabled": True,
    }

    def fake_extract(uploaded_file, *, app_config=None):
        calls["count"] += 1
        assert app_config is not None
        assert app_config["layout_artifact_cleanup_min_repeat_count"] == 1
        assert app_config["layout_artifact_cleanup_max_repeated_text_chars"] == 0
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))

    first = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    config_state["layout_artifact_cleanup_min_repeat_count"] = 2
    config_state["layout_artifact_cleanup_max_repeated_text_chars"] = 80

    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert calls["count"] == 1
    assert first.prepared_source_key == second.prepared_source_key
    assert first.prepared_source_key.endswith(":lc=1:2:80:sr=off:srec=0:ai_first:c1")


def test_prepare_document_for_processing_passes_app_config_to_extraction(monkeypatch):
    captured = {}
    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (
            "image_caption",
            "table_caption",
            "epigraph_attribution",
            "toc_region",
        ),
        "layout_artifact_cleanup_enabled": False,
        "structure_recognition_enabled": False,
        "structure_recognition_mode": "off",
        "structure_validation_enabled": True,
    }

    def fake_extract(uploaded_file, *, app_config=None):
        captured["app_config"] = app_config
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state={"preparation_cache": {}},
    )

    assert captured["app_config"] is not None
    assert captured["app_config"]["layout_artifact_cleanup_enabled"] is False


def _build_extract_result(paragraphs, image_assets, report, relations=None, relation_report=None, cleanup_report=None):
    if cleanup_report is None:
        cleanup_report = _build_cleanup_report(original=len(paragraphs), cleaned=len(paragraphs))
    return (
        paragraphs,
        image_assets,
        report,
        ([] if relations is None else relations),
        relation_report,
        cleanup_report,
        StructureRepairReport(
            applied=False,
            repaired_bullet_items=0,
            repaired_numbered_items=0,
            bounded_toc_regions=0,
            toc_body_boundary_repairs=0,
            heading_candidates_from_toc=0,
            remaining_isolated_marker_count=0,
        ),
    )


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _build_uploaded_payload(
    filename: str,
    content_bytes: bytes,
    file_token: str,
    *,
    source_format: str = "docx",
    conversion_backend: str | None = None,
) -> FrozenUploadPayload:
    return FrozenUploadPayload(
        filename=filename,
        content_bytes=content_bytes,
        file_size=len(content_bytes),
        content_hash="test-hash",
        file_token=file_token,
        source_format=source_format,
        conversion_backend=conversion_backend,
    )


def _build_paragraph(*, source_index: int, text: str, role: str = "body") -> ParagraphUnit:
    return ParagraphUnit(text=text, role=role, source_index=source_index, logical_index=source_index)


def _build_runtime_model_registry(*, structure_recognition_model: str = "gpt-4o-mini") -> ModelRegistry:
    return ModelRegistry(
        text=TextModelConfig(default="gpt-5.4-mini", options=("gpt-5.4-mini",)),
        structure_recognition=structure_recognition_model,
        image_analysis="gpt-5.4-mini",
        image_validation="gpt-5.4-mini",
        image_reconstruction="gpt-5.4-mini",
        image_generation="gpt-image-1.5",
        image_edit="gpt-image-1.5",
        image_generation_vision="gpt-5.4-mini",
    )


def test_prepare_document_for_processing_uses_cache_for_identical_inputs(monkeypatch):
    calls = {"count": 0}
    session_state = {"preparation_cache": {}}
    progress_events = []

    def fake_extract(uploaded_file):
        calls["count"] += 1
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    source_bytes = b"docx-bytes"
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: progress_events.append(payload),
    )
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: progress_events.append(payload),
    )

    assert calls["count"] == 1
    assert progress_events[-1]["metrics"]["cached"] is True


def test_build_prepared_source_key_includes_normalization_mode():
    assert preparation.build_prepared_source_key(
        "report.docx:10:hash",
        6000,
        paragraph_boundary_normalization_mode="high_only",
    ) == "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=off:srec=0:ai_first:c1"


def test_build_prepared_source_key_adds_structure_recognition_suffix_when_enabled():
    assert preparation.build_prepared_source_key(
        "report.docx:10:hash",
        6000,
        paragraph_boundary_normalization_mode="high_only",
        structure_recognition_enabled=True,
    ) == "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=always:srec=0:ai_first:c1"


def test_build_prepared_source_key_includes_auto_mode_and_validation_flag():
    assert preparation.build_prepared_source_key(
        "report.docx:10:hash",
        6000,
        paragraph_boundary_normalization_mode="high_only",
        structure_recognition_mode="auto",
        structure_validation_enabled=False,
    ) == "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=auto:sv=0:srec=0:ai_first:c1"


def test_build_prepared_source_key_includes_translate_operation_suffix_when_not_default():
    assert preparation.build_prepared_source_key(
        "report.docx:10:hash",
        6000,
        processing_operation="translate",
        paragraph_boundary_normalization_mode="high_only",
    ) == "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=off:srec=0:ai_first:c1:op=translate"


def test_build_structure_map_cache_key_uses_logical_index_coordinate():
    paragraph_a = _build_paragraph(source_index=7, text="Section A")
    paragraph_b = _build_paragraph(source_index=7, text="Section A")
    paragraph_a.logical_index = 3
    paragraph_b.logical_index = 9

    app_config = {
        "structure_recognition_max_window_paragraphs": 1800,
        "structure_recognition_overlap_paragraphs": 50,
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "models": _build_runtime_model_registry(),
    }

    key_a = preparation._build_structure_map_cache_key(paragraphs=[paragraph_a], app_config=app_config)
    key_b = preparation._build_structure_map_cache_key(paragraphs=[paragraph_b], app_config=app_config)

    assert key_a != key_b


def test_build_structure_map_cache_key_includes_document_map_anchor_fingerprint():
    paragraph = _build_paragraph(source_index=7, text="Section A")
    paragraph.logical_index = 3

    app_config = {
        "structure_recognition_max_window_paragraphs": 1800,
        "structure_recognition_overlap_paragraphs": 50,
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "models": _build_runtime_model_registry(),
    }
    document_map_a = DocumentMap(
        body_start_logical_index=3,
        toc_region=None,
        outline=(),
        paragraph_anchors={3: DocumentMapAnchor(role="body", heading_level=None, confidence="low")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(3,),
    )
    document_map_b = DocumentMap(
        body_start_logical_index=3,
        toc_region=None,
        outline=(),
        paragraph_anchors={3: DocumentMapAnchor(role="heading", heading_level=2, confidence="high")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(3,),
    )

    key_a = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=app_config, document_map=document_map_a)
    key_b = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=app_config, document_map=document_map_b)

    assert key_a != key_b


def test_build_structure_map_cache_key_includes_anchored_window_profile_when_document_map_present():
    paragraph = _build_paragraph(source_index=7, text="Section A")
    paragraph.logical_index = 3
    document_map = DocumentMap(
        body_start_logical_index=3,
        toc_region=None,
        outline=(),
        paragraph_anchors={3: DocumentMapAnchor(role="heading", heading_level=2, confidence="high")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(3,),
    )

    app_config_a = {
        "structure_recognition_max_window_paragraphs": 1800,
        "structure_recognition_overlap_paragraphs": 50,
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
        "structure_recovery_anchored_classification_overlap_paragraphs": 0,
        "structure_recovery_anchored_classification_preview_chars": 1500,
        "structure_recovery_anchored_classification_target_input_tokens": 180000,
        "models": _build_runtime_model_registry(),
    }
    app_config_b = {**app_config_a, "structure_recovery_anchored_classification_preview_chars": 1200}

    key_a = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=app_config_a, document_map=document_map)
    key_b = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=app_config_b, document_map=document_map)

    assert key_a != key_b


def test_build_structure_map_cache_key_includes_prompt_and_descriptor_versions(monkeypatch):
    paragraph = _build_paragraph(source_index=7, text="Section A")
    paragraph.logical_index = 3

    app_config = {
        "structure_recognition_max_window_paragraphs": 1800,
        "structure_recognition_overlap_paragraphs": 50,
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "models": _build_runtime_model_registry(),
    }

    key_a = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=app_config)
    monkeypatch.setattr(preparation, "STRUCTURE_RECOGNITION_PROMPT_VERSION", preparation.STRUCTURE_RECOGNITION_PROMPT_VERSION + 1)
    key_b = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=app_config)

    assert key_a != key_b


def test_build_structure_map_cache_key_includes_reconciliation_schema_version(monkeypatch):
    paragraph = _build_paragraph(source_index=7, text="Section A")
    paragraph.logical_index = 3

    app_config = {
        "structure_recognition_max_window_paragraphs": 1800,
        "structure_recognition_overlap_paragraphs": 50,
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "models": _build_runtime_model_registry(),
    }

    key_a = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=app_config)
    monkeypatch.setattr(preparation, "STRUCTURE_RECONCILIATION_SCHEMA_VERSION", preparation.STRUCTURE_RECONCILIATION_SCHEMA_VERSION + 1)
    key_b = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=app_config)

    assert key_a != key_b


def test_build_document_map_cache_key_uses_logical_index_coordinate():
    paragraph_a = _build_paragraph(source_index=7, text="Section A")
    paragraph_b = _build_paragraph(source_index=7, text="Section A")
    paragraph_a.logical_index = 3
    paragraph_b.logical_index = 9

    app_config = {
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "structure_recovery_document_map_model": "openrouter:test/document-map",
        "structure_recovery_document_map_max_input_paragraphs": 6000,
        "structure_recovery_document_map_max_input_tokens": 180000,
        "structure_recovery_document_map_preview_chars": 120,
    }

    key_a = preparation._build_document_map_cache_key(paragraphs=[paragraph_a], app_config=app_config)
    key_b = preparation._build_document_map_cache_key(paragraphs=[paragraph_b], app_config=app_config)

    assert key_a != key_b


def test_build_document_map_cache_key_includes_embedded_structure_hints():
    paragraph_a = _build_paragraph(source_index=2, text="Compound paragraph")
    paragraph_b = _build_paragraph(source_index=2, text="Compound paragraph")
    paragraph_a.logical_index = 2
    paragraph_b.logical_index = 2
    paragraph_b.heuristic_embedded_structure_hints = [
        EmbeddedStructureHint(text="Introduction", role="heading", structural_role="body", heading_level=2)
    ]

    app_config = {
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "structure_recovery_document_map_model": "openrouter:test/document-map",
        "structure_recovery_document_map_max_input_paragraphs": 6000,
        "structure_recovery_document_map_max_input_tokens": 180000,
        "structure_recovery_document_map_preview_chars": 120,
    }

    key_a = preparation._build_document_map_cache_key(paragraphs=[paragraph_a], app_config=app_config)
    key_b = preparation._build_document_map_cache_key(paragraphs=[paragraph_b], app_config=app_config)

    assert key_a != key_b


def test_prepare_document_for_processing_passes_processing_operation_to_job_builder(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result([_build_paragraph(source_index=0, text="Contents")], [], None),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "Contents")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])

    def fake_build_editing_jobs(blocks, max_chars, processing_operation="edit"):
        captured["processing_operation"] = processing_operation
        return [{"target_text": "Contents", "target_chars": 8, "context_chars": 0}]

    monkeypatch.setattr(preparation, "build_editing_jobs", fake_build_editing_jobs)

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        processing_operation="translate",
        session_state={"preparation_cache": {}},
    )

    assert captured["processing_operation"] == "translate"


def test_prepare_document_for_processing_assigns_stable_job_ids(monkeypatch):
    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result([_build_paragraph(source_index=0, text="Contents")], [], None),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "Contents")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block-1", "block-2"])
    monkeypatch.setattr(
        preparation,
        "build_editing_jobs",
        lambda blocks, max_chars, processing_operation="edit": [
            {"target_text": "First block", "target_chars": 11, "context_chars": 0},
            {"target_text": "Second block", "target_chars": 12, "context_chars": 0},
        ],
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state={"preparation_cache": {}},
    )

    assert [job["job_id"] for job in result.jobs] == ["job_0000", "job_0001"]


def test_prepare_document_for_processing_keeps_toc_jobs_operation_aware_across_cache_entries(monkeypatch):
    calls = {"count": 0}
    session_state = {"preparation_cache": {}}
    toc_paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0),
        ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", source_index=1),
    ]

    def fake_extract(uploaded_file):
        calls["count"] += 1
        return _build_extract_result(toc_paragraphs, [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "\n\n".join(paragraph.text for paragraph in paragraphs))
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [DocumentBlock(paragraphs=list(paragraphs))])

    edit_result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        processing_operation="edit",
        session_state=session_state,
    )
    translate_result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        processing_operation="translate",
        session_state=session_state,
    )

    assert calls["count"] == 2
    assert edit_result.jobs[0]["job_kind"] == "passthrough"
    assert translate_result.jobs[0]["job_kind"] == "llm"
    assert edit_result.jobs[0]["narration_include"] is False
    assert translate_result.jobs[0]["narration_include"] is False


def test_prepare_document_for_processing_cache_key_changes_with_ai_review_mode(monkeypatch):
    calls = {"count": 0}
    session_state = {"preparation_cache": {}}

    def fake_extract(uploaded_file):
        calls["count"] += 1
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (
            "image_caption",
            "table_caption",
            "epigraph_attribution",
            "toc_region",
        ),
    }
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    config_state["paragraph_boundary_ai_review_enabled"] = True
    config_state["paragraph_boundary_ai_review_mode"] = "review_only"

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert calls["count"] == 2
    assert list(session_state["preparation_cache"].keys()) == [
        "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=off:srec=0:ai_first:c1",
        "report.docx:10:hash:6000:high_only:review_only:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=off:srec=0:ai_first:c1",
    ]


def test_prepare_document_for_processing_jobs_include_narration_metadata_without_affecting_cache_key(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0),
        ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", source_index=1),
        ParagraphUnit(text="Actual body", role="body", source_index=2),
    ]
    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (
            "image_caption",
            "table_caption",
            "epigraph_attribution",
            "toc_region",
        ),
        "structure_recognition_enabled": False,
        "structure_recognition_mode": "off",
        "structure_validation_enabled": True,
        "translation_domain_default": "theology",
    }

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], None),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda items: "\n\n".join(paragraph.text for paragraph in items))
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))

    prepared = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        processing_operation="edit",
        session_state=session_state,
    )

    assert [job["narration_include"] for job in prepared.jobs] == [False, True]
    assert list(session_state["preparation_cache"].keys()) == [
        "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=off:srec=0:ai_first:c1"
    ]


def test_prepare_document_for_processing_detects_segments_and_builds_segment_mapping(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", paragraph_id="p0000", source_index=0),
        ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001", source_index=1),
        ParagraphUnit(text="Chapter 1", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0002", source_index=2),
        ParagraphUnit(text="First chapter body about Great Tribulation", role="body", paragraph_id="p0003", source_index=3),
        ParagraphUnit(text="Chapter 2", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0004", source_index=4),
        ParagraphUnit(text="Second chapter body about the Antichrist", role="body", paragraph_id="p0005", source_index=5),
    ]
    captured = {}

    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (
            "image_caption",
            "table_caption",
            "epigraph_attribution",
            "toc_region",
        ),
        "structure_recognition_enabled": False,
        "structure_recognition_mode": "off",
        "structure_validation_enabled": True,
        "translation_domain_default": "theology",
    }

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file, app_config=None: _build_extract_result(paragraphs, [], None),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda items: "\n\n".join(paragraph.text for paragraph in items))
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))

    def fake_build_semantic_blocks(paragraphs, max_chars, relations=None, hard_boundary_paragraph_ids=None):
        captured["hard_boundary_paragraph_ids"] = set(hard_boundary_paragraph_ids or set())
        return [
            DocumentBlock(paragraphs=list(paragraphs[:2])),
            DocumentBlock(paragraphs=list(paragraphs[2:4])),
            DocumentBlock(paragraphs=list(paragraphs[4:])),
        ]

    monkeypatch.setattr(preparation, "build_semantic_blocks", fake_build_semantic_blocks)

    prepared = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        processing_operation="translate",
        session_state=session_state,
    )

    assert prepared.detector_version == CHAPTER_SEGMENTS_DETECTOR_VERSION
    assert prepared.structure_fingerprint
    assert prepared.segment_diagnostics.segment_count >= 3
    assert [segment.title for segment in prepared.segments or []][:3] == ["Table of Contents", "Chapter 1", "Chapter 2"]
    assert captured["hard_boundary_paragraph_ids"] == {"p0002", "p0004"}
    segments = prepared.segments
    segment_to_job = prepared.segment_to_job
    assert segments is not None
    assert segment_to_job is not None
    assert segment_to_job[segments[0].segment_id] == (0,)
    assert segment_to_job[segments[1].segment_id] == (1,)
    assert segment_to_job[segments[2].segment_id] == (2,)
    assert paragraphs[2].segment_boundary_before is True
    assert paragraphs[4].segment_boundary_before is True
    document_context_profile = prepared.document_context_profile
    assert document_context_profile.source_token == "report.docx:10:hash"
    assert document_context_profile.structure_fingerprint == prepared.structure_fingerprint
    assert document_context_profile.source_title == "report"
    assert document_context_profile.source_language == "en"
    assert document_context_profile.target_language == "ru"
    assert document_context_profile.translation_domain == "theology"
    assert document_context_profile.style_instructions == prepared.translation_domain_instructions
    assert [entry.title for entry in document_context_profile.outline_entries[:3]] == [
        "Table of Contents",
        "Chapter 1",
        "Chapter 2",
    ]
    assert {term.source_term for term in document_context_profile.glossary_terms} >= {
        "Great Tribulation",
        "Antichrist",
    }
    assert "КОНТЕКСТ ДОКУМЕНТА" in document_context_profile.to_prompt_text()


def test_prepare_document_for_processing_populates_detected_author_from_docx_metadata(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        ParagraphUnit(text="Chapter 1", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0000", source_index=0),
        ParagraphUnit(text="Body text", role="body", paragraph_id="p0001", source_index=1),
    ]
    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (),
        "structure_recognition_enabled": False,
        "structure_recognition_mode": "off",
        "structure_validation_enabled": True,
        "translation_domain_default": "general",
        "source_language_default": "en",
        "target_language_default": "ru",
    }
    document = Document()
    document.core_properties.author = "Jane Example"
    document.add_paragraph("Ignored by stub")
    buffer = BytesIO()
    document.save(buffer)

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file, *, app_config=None: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda prepared_paragraphs: "\n".join(paragraph.text for paragraph in prepared_paragraphs))
    monkeypatch.setattr(
        preparation,
        "build_semantic_blocks",
        lambda prepared_paragraphs, max_chars, relations=None, hard_boundary_paragraph_ids=None: [DocumentBlock(paragraphs=list(prepared_paragraphs))],
    )
    monkeypatch.setattr(
        preparation,
        "build_editing_jobs",
        lambda blocks, max_chars, processing_operation="edit": [{"target_text": "Body text", "context_before": "", "context_after": ""}],
    )
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))

    prepared = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", buffer.getvalue(), "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert prepared.document_context_profile.detected_author == "Jane Example"


def test_prepare_document_for_processing_adds_warning_when_job_spans_multiple_segments(monkeypatch):
    session_state = {"preparation_cache": {}}
    warning_messages = []
    paragraphs = [
        ParagraphUnit(text="Chapter 1", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0000", source_index=0),
        ParagraphUnit(text="First chapter body", role="body", paragraph_id="p0001", source_index=1),
        ParagraphUnit(text="Chapter 2", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0002", source_index=2),
        ParagraphUnit(text="Second chapter body", role="body", paragraph_id="p0003", source_index=3),
    ]
    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (),
        "structure_recognition_enabled": False,
        "structure_recognition_mode": "off",
        "structure_validation_enabled": True,
    }

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file, app_config=None: _build_extract_result(paragraphs, [], None),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda items: "\n\n".join(paragraph.text for paragraph in items))
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))
    monkeypatch.setattr(
        document_segments.logger,
        "warning",
        lambda message, *args: warning_messages.append(message % args if args else message),
    )
    monkeypatch.setattr(
        preparation,
        "build_semantic_blocks",
        lambda paragraphs, max_chars, relations=None, hard_boundary_paragraph_ids=None: [DocumentBlock(paragraphs=list(paragraphs))],
    )
    monkeypatch.setattr(
        preparation,
        "build_editing_jobs",
        lambda blocks, max_chars, processing_operation=None: [
            {
                "job_id": "job-cross-boundary",
                "paragraph_ids": ["p0001", "p0002"],
                "paragraph_count": 2,
                "target_text": "cross-segment job",
                "context_text": "",
            }
        ],
    )

    prepared = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        processing_operation="translate",
        session_state=session_state,
    )

    assert prepared.segment_to_job is not None
    assert all(indexes == () for indexes in prepared.segment_to_job.values())
    assert "segment_job_mapping_incomplete" in prepared.segment_diagnostics.warnings
    assert any(
        "segment_to_job_mapping_unassigned" in message
        and "job-cross-boundary" in message
        and "p0001" in message
        and "p0002" in message
        for message in warning_messages
    )


def test_prepare_document_for_processing_fails_on_invalid_segment_coverage(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        ParagraphUnit(text="Chapter 1", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0000", source_index=0),
        ParagraphUnit(text="Body 1", role="body", paragraph_id="p0001", source_index=1),
        ParagraphUnit(text="Body 2", role="body", paragraph_id="p0002", source_index=2),
    ]
    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (),
        "structure_recognition_enabled": False,
        "structure_recognition_mode": "off",
        "structure_validation_enabled": True,
    }

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file, app_config=None: _build_extract_result(paragraphs, [], None),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda items: "\n\n".join(paragraph.text for paragraph in items))
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))
    monkeypatch.setattr(
        preparation,
        "build_semantic_blocks",
        lambda paragraphs, max_chars, relations=None, hard_boundary_paragraph_ids=None: [DocumentBlock(paragraphs=list(paragraphs))],
    )
    monkeypatch.setattr(
        preparation,
        "build_editing_jobs",
        lambda blocks, max_chars, processing_operation=None: [
            {
                "paragraph_ids": ["p0000", "p0001", "p0002"],
                "paragraph_count": 3,
                "target_text": "full job",
                "context_text": "",
            }
        ],
    )

    invalid_segments = [
        preparation.DocumentSegment(
            segment_id="seg_0001",
            ordinal=1,
            level=1,
            title="Chapter 1",
            normalized_title="chapter 1",
            start_paragraph_index=0,
            end_paragraph_index=1,
            start_paragraph_id="p0000",
            end_paragraph_id="p0001",
            paragraph_ids=("p0000", "p0001"),
            paragraph_count=2,
            char_count=10,
            word_count=2,
            estimated_token_count=4,
            structural_role="chapter",
            confidence="high",
            boundary_fingerprint="fp1",
        )
    ]
    monkeypatch.setattr(
        preparation,
        "detect_document_segments",
        lambda paragraphs, source_content_hash16, chunk_size: (
            invalid_segments,
            preparation.SegmentDetectionReport(segment_count=1),
            "fp-structure",
        ),
    )

    with pytest.raises(ValueError, match="invalid_segment_coverage: uncovered_paragraph_indexes"):
        preparation.prepare_document_for_processing(
            uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
            chunk_size=6000,
            processing_operation="translate",
            session_state=session_state,
        )


def test_detect_document_segments_splits_oversized_heading_ranges_into_parent_and_children():
    paragraphs = [
        ParagraphUnit(text="Chapter 1", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0000", source_index=0),
        ParagraphUnit(text="A" * 12000, role="body", paragraph_id="p0001", source_index=1),
        ParagraphUnit(text="B" * 12000, role="body", paragraph_id="p0002", source_index=2),
        ParagraphUnit(text="C" * 12000, role="body", paragraph_id="p0003", source_index=3),
    ]

    segments, diagnostics, structure_fingerprint = preparation.detect_document_segments(
        paragraphs,
        source_content_hash16="abcd1234ef567890",
        chunk_size=6000,
    )

    assert structure_fingerprint
    assert [segment.title for segment in segments] == ["Chapter 1", "Chapter 1 Part 1", "Chapter 1 Part 2"]
    assert [segment.level for segment in segments] == [1, 2, 2]
    assert segments[0].parent_segment_id is None
    assert segments[1].parent_segment_id == segments[0].segment_id
    assert segments[2].parent_segment_id == segments[0].segment_id
    assert segments[0].start_paragraph_index == 0 and segments[0].end_paragraph_index == 0
    assert segments[1].start_paragraph_index == 1 and segments[1].end_paragraph_index == 2
    assert segments[2].start_paragraph_index == 3 and segments[2].end_paragraph_index == 3
    assert diagnostics.segment_count == 3
    assert diagnostics.low_confidence_count == 2
    assert "low_confidence_segments_present" in diagnostics.warnings


def test_detect_document_segments_adds_all_caps_typography_evidence_for_heading_candidates():
    paragraphs = [
        ParagraphUnit(text="APPENDIX", role="body", paragraph_id="p0000", source_index=0),
        ParagraphUnit(text="Body paragraph", role="body", paragraph_id="p0001", source_index=1),
    ]

    segments, diagnostics, structure_fingerprint = preparation.detect_document_segments(
        paragraphs,
        source_content_hash16="abcd1234ef567890",
        chunk_size=6000,
    )

    assert structure_fingerprint
    assert diagnostics.segment_count >= 1
    typography_evidence = [
        evidence
        for evidence in segments[0].boundary_evidence
        if evidence.source == "typography"
    ]
    assert typography_evidence
    assert typography_evidence[0].details["is_all_caps"] is True
    assert typography_evidence[0].details["is_bold"] is False


def test_detect_document_segments_is_deterministic_for_same_input():
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", paragraph_id="p0000", source_index=0),
        ParagraphUnit(text="1 Chapter 1", role="body", structural_role="toc_entry", paragraph_id="p0001", source_index=1),
        ParagraphUnit(text="Chapter 1", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0002", source_index=2),
        ParagraphUnit(text="First chapter body", role="body", paragraph_id="p0003", source_index=3),
        ParagraphUnit(text="Chapter 2", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0004", source_index=4),
        ParagraphUnit(text="Second chapter body", role="body", paragraph_id="p0005", source_index=5),
    ]

    first_segments, first_diagnostics, first_structure_fingerprint = preparation.detect_document_segments(
        paragraphs,
        source_content_hash16="abcd1234ef567890",
        chunk_size=6000,
    )
    second_segments, second_diagnostics, second_structure_fingerprint = preparation.detect_document_segments(
        paragraphs,
        source_content_hash16="abcd1234ef567890",
        chunk_size=6000,
    )

    assert first_structure_fingerprint == second_structure_fingerprint
    assert first_diagnostics == second_diagnostics
    assert [
        (
            segment.segment_id,
            segment.parent_segment_id,
            segment.boundary_fingerprint,
            segment.start_paragraph_id,
            segment.end_paragraph_id,
            segment.title,
        )
        for segment in first_segments
    ] == [
        (
            segment.segment_id,
            segment.parent_segment_id,
            segment.boundary_fingerprint,
            segment.start_paragraph_id,
            segment.end_paragraph_id,
            segment.title,
        )
        for segment in second_segments
    ]


def test_prepare_document_for_processing_maps_jobs_for_split_oversized_heading_segments(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        ParagraphUnit(text="Chapter 1", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0000", source_index=0),
        ParagraphUnit(text="A" * 12000, role="body", paragraph_id="p0001", source_index=1),
        ParagraphUnit(text="B" * 12000, role="body", paragraph_id="p0002", source_index=2),
        ParagraphUnit(text="C" * 12000, role="body", paragraph_id="p0003", source_index=3),
    ]
    captured = {}
    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (),
        "structure_recognition_enabled": False,
        "structure_recognition_mode": "off",
        "structure_validation_enabled": True,
    }

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file, app_config=None: _build_extract_result(paragraphs, [], None),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda items: "\n\n".join(paragraph.text for paragraph in items))
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))

    def fake_build_semantic_blocks(paragraphs, max_chars, relations=None, hard_boundary_paragraph_ids=None):
        captured["hard_boundary_paragraph_ids"] = set(hard_boundary_paragraph_ids or set())
        blocks = []
        current_block = []
        for paragraph in paragraphs:
            paragraph_id = str(getattr(paragraph, "paragraph_id", "") or "")
            if current_block and paragraph_id in captured["hard_boundary_paragraph_ids"]:
                blocks.append(DocumentBlock(paragraphs=list(current_block)))
                current_block = []
            current_block.append(paragraph)
        if current_block:
            blocks.append(DocumentBlock(paragraphs=list(current_block)))
        return blocks

    monkeypatch.setattr(preparation, "build_semantic_blocks", fake_build_semantic_blocks)
    monkeypatch.setattr(
        preparation,
        "build_editing_jobs",
        lambda blocks, max_chars, processing_operation=None: [
            {
                "paragraph_ids": [str(getattr(paragraph, "paragraph_id", "") or "") for paragraph in block.paragraphs],
                "paragraph_count": len(block.paragraphs),
                "target_text": "block",
                "context_text": "",
            }
            for block in blocks
        ],
    )

    prepared = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        processing_operation="translate",
        session_state=session_state,
    )

    assert [segment.title for segment in prepared.segments or []] == ["Chapter 1", "Chapter 1 Part 1", "Chapter 1 Part 2"]
    assert captured["hard_boundary_paragraph_ids"] == {"p0001", "p0003"}
    assert prepared.segments is not None
    assert prepared.segment_to_job == {
        prepared.segments[0].segment_id: (0,),
        prepared.segments[1].segment_id: (1,),
        prepared.segments[2].segment_id: (2,),
    }


def test_prepare_document_for_processing_postprocess_toggle_does_not_change_cache_key_or_request_marker(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        ParagraphUnit(text="Chapter 1", role="heading", source_index=0),
        ParagraphUnit(text="Actual body", role="body", source_index=1),
    ]
    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (
            "image_caption",
            "table_caption",
            "epigraph_attribution",
            "toc_region",
        ),
        "structure_recognition_enabled": False,
        "structure_recognition_mode": "off",
        "structure_validation_enabled": True,
        "audiobook_postprocess_enabled": False,
    }

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], None),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda items: "\n\n".join(paragraph.text for paragraph in items))
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))

    uploaded_payload = _build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash")
    request_marker = build_preparation_request_marker(
        build_in_memory_uploaded_file(source_name=uploaded_payload.filename, source_bytes=uploaded_payload.content_bytes),
        chunk_size=6000,
    )

    first = preparation.prepare_document_for_processing(
        uploaded_payload=uploaded_payload,
        chunk_size=6000,
        processing_operation="edit",
        session_state=session_state,
    )

    config_state["audiobook_postprocess_enabled"] = True

    second = preparation.prepare_document_for_processing(
        uploaded_payload=uploaded_payload,
        chunk_size=6000,
        processing_operation="edit",
        session_state=session_state,
    )

    assert first.prepared_source_key == second.prepared_source_key
    assert list(session_state["preparation_cache"].keys()) == [first.prepared_source_key]
    assert request_marker == build_preparation_request_marker(
        build_in_memory_uploaded_file(source_name=uploaded_payload.filename, source_bytes=uploaded_payload.content_bytes),
        chunk_size=6000,
    )


def test_prepare_document_for_processing_returns_independent_copies():
    session_state = {"preparation_cache": {}}
    source_bytes = _build_docx_bytes(["Первый абзац.", "Второй абзац."])

    first = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:token"),
        chunk_size=6000,
        session_state=session_state,
    )
    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:token"),
        chunk_size=6000,
        session_state=session_state,
    )

    first.paragraphs[0].text = "Изменено"
    first.jobs[0]["target_text"] = "Изменено"

    assert second.paragraphs[0].text == "Первый абзац.\n\nВторой абзац." or second.paragraphs[0].text == "Первый абзац."
    assert str(second.jobs[0]["target_text"]).strip() != "Изменено"


def test_prepare_document_for_processing_clones_attempt_variants_independently(monkeypatch):
    session_state = {"preparation_cache": {}}
    source_bytes = b"docx-bytes"

    asset = ImageAsset(
        image_id="img-1",
        placeholder="[[DOCX_IMAGE_img-1]]",
        original_bytes=b"orig",
        mime_type="image/png",
        position_index=0,
        attempt_variants=[
            ImageVariantCandidate(
                mode="safe",
                validation_result={"score": 0.5},
                final_reason="initial",
            )
        ],
    )

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([{"text": "p"}], [asset], None))
    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([{"text": "p"}], [asset], None))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    first = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )
    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    first.image_assets[0].attempt_variants[0].final_reason = "mutated"
    first.image_assets[0].attempt_variants[0].validation_result["score"] = 0.1

    assert len(second.image_assets[0].attempt_variants) == 1
    assert second.image_assets[0].attempt_variants[0].final_reason == "initial"
    assert second.image_assets[0].attempt_variants[0].validation_result == {"score": 0.5}


def test_prepare_document_for_processing_clones_comparison_variants_independently(monkeypatch):
    session_state = {"preparation_cache": {}}
    source_bytes = b"docx-bytes"

    asset = ImageAsset(
        image_id="img-1",
        placeholder="[[DOCX_IMAGE_img-1]]",
        original_bytes=b"orig",
        mime_type="image/png",
        position_index=0,
        comparison_variants={
            "safe": {
                "mode": "safe",
                "validation_result": {"score": 0.7},
                "final_reason": "initial",
            }
        },
    )

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([{"text": "p"}], [asset], None))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    first = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )
    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    first.image_assets[0].comparison_variants["safe"]["final_reason"] = "mutated"
    first.image_assets[0].comparison_variants["safe"]["validation_result"]["score"] = 0.2

    assert second.image_assets[0].comparison_variants["safe"]["final_reason"] == "initial"
    assert second.image_assets[0].comparison_variants["safe"]["validation_result"] == {"score": 0.7}


def test_prepare_document_for_processing_limits_session_cache_size(monkeypatch):
    session_state = {"preparation_cache": {}}

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([], [], None))
    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([], [], None))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("one.docx", b"one", "one:3:a"),
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("two.docx", b"two", "two:3:b"),
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("three.docx", b"three", "three:5:c"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert list(session_state["preparation_cache"].keys()) == [
        "two:3:b:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=auto:sv=1:srec=0:ai_first:c1",
        "three:5:c:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=auto:sv=1:srec=0:ai_first:c1",
    ]


def test_prepare_document_for_processing_uses_shared_cache_without_session_state(monkeypatch):
    calls = {"count": 0}
    progress_events = []

    def fake_extract(uploaded_file):
        calls["count"] += 1
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    source_bytes = b"docx-bytes"
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=None,
        progress_callback=lambda **payload: progress_events.append(payload),
    )
    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=None,
        progress_callback=lambda **payload: progress_events.append(payload),
    )

    assert calls["count"] == 1
    assert second.cached is True
    assert progress_events[-1]["metrics"]["cached"] is True


def test_prepare_document_for_processing_uses_single_flight_for_shared_cache(monkeypatch):
    calls = {"count": 0}
    extract_started = Event()
    release_extract = Event()
    second_finished = Event()
    results = {}

    def fake_extract(uploaded_file):
        calls["count"] += 1
        extract_started.set()
        assert release_extract.wait(timeout=5)
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    def worker(result_key: str, finished_event: Event):
        results[result_key] = preparation.prepare_document_for_processing(
            uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
            chunk_size=6000,
            session_state=None,
        )
        finished_event.set()

    first_finished = Event()
    first_thread = Thread(target=worker, args=("first", first_finished))
    second_thread = Thread(target=worker, args=("second", second_finished))

    first_thread.start()
    assert extract_started.wait(timeout=5)
    second_thread.start()

    assert not second_finished.wait(timeout=0.2)

    release_extract.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert calls["count"] == 1
    assert results["first"].cached is False
    assert results["second"].cached is True


def test_clear_preparation_cache_requires_explicit_shared_clear(monkeypatch):
    calls = {"count": 0}

    def fake_extract(uploaded_file):
        calls["count"] += 1
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=None,
    )

    session_state = {"preparation_cache": {"stale": object()}}
    preparation.clear_preparation_cache(session_state=session_state)

    assert session_state["preparation_cache"] == {}

    cached_again = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=None,
    )

    preparation.clear_preparation_cache(clear_shared=True)

    uncached_after_explicit_clear = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=None,
    )

    assert calls["count"] == 2
    assert cached_again.cached is True
    assert uncached_after_explicit_clear.cached is False


def test_prepare_document_for_processing_miss_returns_clone_separate_from_cached_entry(monkeypatch):
    session_state = {"preparation_cache": {}}

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([{"text": "p"}], [{"image": b"x"}], None))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([{"text": "p"}], [{"image": b"x"}], None))
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    cached_entry = session_state["preparation_cache"]["report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=auto:sv=1:srec=0:ai_first:c1"]

    assert result is not cached_entry
    assert result.paragraphs is not cached_entry.paragraphs
    assert result.image_assets is not cached_entry.image_assets
    assert result.jobs is not cached_entry.jobs
    assert result.jobs[0] is not cached_entry.jobs[0]


def test_prepare_document_for_processing_reports_stage_metrics(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(["p1", "p2"], ["img"], _build_report(raw=3, logical=2, merged_groups=1, merged_raw=2)),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text-value")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block-a", "block-b"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "a", "target_chars": 1, "context_chars": 0}, {"target_text": "b", "target_chars": 1, "context_chars": 0}])

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    assert [event["stage"] for event in events] == [
        "Разбор DOCX",
        "Структура извлечена",
        "Структура: валидация",
        "Структура: детерминированно",
        "Текст собран",
        "Смысловые блоки",
        "Задания собраны",
    ]
    assert events[1]["metrics"]["paragraph_count"] == 2
    assert events[1]["metrics"]["image_count"] == 1
    assert events[1]["metrics"]["raw_paragraph_count"] == 3
    assert events[1]["metrics"]["logical_paragraph_count"] == 2
    assert events[1]["metrics"]["merged_group_count"] == 1
    assert events[1]["metrics"]["merged_raw_paragraph_count"] == 2
    assert events[4]["metrics"]["source_chars"] == len("text-value")
    assert events[5]["metrics"]["block_count"] == 2


def test_prepare_document_for_processing_runs_structure_recognition_when_enabled(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1"), _build_paragraph(source_index=1, text="Основной текст")]

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda *args, **kwargs: StructureMap(
            classifications={0: ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")},
            model_used="gpt-4o-mini",
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "always",
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    assert [event["stage"] for event in events] == [
        "Разбор DOCX",
        "Структура извлечена",
        "Структура: валидация",
        "Распознавание структуры…",
        "Применение структуры…",
        "Структура распознана",
        "Текст собран",
        "Смысловые блоки",
        "Задания собраны",
    ]
    assert events[5]["metrics"]["ai_classified"] == 1
    assert events[5]["metrics"]["ai_headings"] == 1
    assert events[5]["metrics"]["ai_role_changes"] == 1
    assert events[5]["metrics"]["ai_heading_promotions"] == 1
    assert events[5]["metrics"]["ai_structural_role_changes"] == 1
    assert result.ai_classified_count == 1
    assert result.ai_heading_count == 1
    assert result.ai_role_change_count == 1
    assert result.ai_heading_promotion_count == 1
    assert result.ai_heading_demotion_count == 0
    assert result.ai_structural_role_change_count == 1
    assert result.structure_map is not None


def test_prepare_document_for_processing_passes_document_map_into_structure_recognition(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1"), _build_paragraph(source_index=1, text="Основной текст")]
    captured = {}

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda paragraphs, *, client, model, timeout, max_input_paragraphs, max_input_tokens, preview_chars, progress_callback: DocumentMap(
            body_start_logical_index=0,
            toc_region=None,
            outline=(),
            paragraph_anchors={0: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
            review_zones=(),
            model_used=model,
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(0, 1),
        ),
    )

    def _fake_build_structure_map(paragraphs, *, client, model, max_window_paragraphs, overlap_paragraphs, timeout, document_map, preview_chars, target_input_tokens, progress_callback):
        captured["document_map"] = document_map
        captured["preview_chars"] = preview_chars
        captured["target_input_tokens"] = target_input_tokens
        return StructureMap(
            classifications={0: ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")},
            model_used=model,
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        )

    monkeypatch.setattr(preparation, "build_structure_map", _fake_build_structure_map)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "always",
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_timeout_seconds": 45,
            "structure_recovery_document_map_max_input_paragraphs": 200,
            "structure_recovery_document_map_cache_enabled": False,
            "structure_recovery_document_map_save_debug_artifacts": False,
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert captured["document_map"] is not None
    assert captured["preview_chars"] == 1500
    assert captured["target_input_tokens"] == 180000
    assert captured["document_map"].get_anchor(0) == DocumentMapAnchor(role="heading", heading_level=1, confidence="high")
    assert result.document_map is not None


def test_prepare_document_for_processing_uses_anchored_window_profile_when_document_map_present(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1"), _build_paragraph(source_index=1, text="Основной текст")]
    captured = {}

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda paragraphs, *, client, model, timeout, max_input_paragraphs, max_input_tokens, preview_chars, progress_callback: DocumentMap(
            body_start_logical_index=0,
            toc_region=None,
            outline=(),
            paragraph_anchors={0: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
            review_zones=(),
            model_used=model,
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(0, 1),
        ),
    )

    def _fake_build_structure_map(paragraphs, *, client, model, max_window_paragraphs, overlap_paragraphs, timeout, document_map, preview_chars, target_input_tokens, progress_callback):
        captured["max_window_paragraphs"] = max_window_paragraphs
        captured["overlap_paragraphs"] = overlap_paragraphs
        captured["preview_chars"] = preview_chars
        captured["target_input_tokens"] = target_input_tokens
        return StructureMap(
            classifications={0: ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")},
            model_used=model,
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        )

    monkeypatch.setattr(preparation, "build_structure_map", _fake_build_structure_map)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "always",
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_timeout_seconds": 45,
            "structure_recovery_document_map_max_input_paragraphs": 200,
            "structure_recovery_document_map_cache_enabled": False,
            "structure_recovery_document_map_save_debug_artifacts": False,
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
        },
    )

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert captured["max_window_paragraphs"] == 3000
    assert captured["overlap_paragraphs"] == 0
    assert captured["preview_chars"] == 1500
    assert captured["target_input_tokens"] == 180000


def test_prepare_document_for_processing_uses_anchored_min_confidence_when_document_map_present(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1"), _build_paragraph(source_index=1, text="Основной текст")]
    captured = {}

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda paragraphs, *, client, model, timeout, max_input_paragraphs, max_input_tokens, preview_chars, progress_callback: DocumentMap(
            body_start_logical_index=0,
            toc_region=None,
            outline=(),
            paragraph_anchors={0: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
            review_zones=(),
            model_used=model,
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(0, 1),
        ),
    )
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda paragraphs, *, client, model, max_window_paragraphs, overlap_paragraphs, timeout, document_map, preview_chars, target_input_tokens, progress_callback: StructureMap(
            classifications={0: ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")},
            model_used=model,
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )

    def _fake_apply_structure_map(paragraphs, structure_map, *, min_confidence="medium", document_map=None):
        captured["min_confidence"] = min_confidence
        captured["document_map"] = document_map
        return {"ai_classified": 1, "ai_headings": 1}

    monkeypatch.setattr(preparation, "apply_structure_map", _fake_apply_structure_map)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "always",
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_timeout_seconds": 45,
            "structure_recovery_document_map_max_input_paragraphs": 200,
            "structure_recovery_document_map_cache_enabled": False,
            "structure_recovery_document_map_save_debug_artifacts": False,
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
        },
    )

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert captured["min_confidence"] == "high"
    assert captured["document_map"] is not None


def test_prepare_document_for_processing_reconciles_high_confidence_document_map_heading_before_apply(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1"), _build_paragraph(source_index=1, text="Основной текст")]
    paragraphs[0].logical_index = 10
    paragraphs[1].logical_index = 11

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda paragraphs, *, client, model, timeout, max_input_paragraphs, max_input_tokens, preview_chars, progress_callback: DocumentMap(
            body_start_logical_index=10,
            toc_region=None,
            outline=(
                DocumentMapOutlineEntry(
                    title="ГЛАВА 1",
                    level=1,
                    logical_index=10,
                    confidence="high",
                    evidence=("bold",),
                ),
            ),
            paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
            review_zones=(),
            model_used=model,
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(10, 11),
        ),
    )
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda paragraphs, *, client, model, max_window_paragraphs, overlap_paragraphs, timeout, document_map, preview_chars, target_input_tokens, progress_callback: StructureMap(
            classifications={0: ParagraphClassification(index=0, role="body", heading_level=None, confidence="high")},
            model_used=model,
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "always",
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_timeout_seconds": 45,
            "structure_recovery_document_map_max_input_paragraphs": 200,
            "structure_recovery_document_map_max_input_tokens": 180000,
            "structure_recovery_document_map_preview_chars": 120,
            "structure_recovery_document_map_cache_enabled": False,
            "structure_recovery_document_map_save_debug_artifacts": False,
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.structure_map is not None
    assert result.structure_map.classifications[0].role == "heading"
    assert result.structure_map.classifications[0].heading_level == 1
    assert result.paragraphs[0].role == "heading"
    assert result.paragraphs[0].heading_level == 1


def test_prepare_document_for_processing_builds_document_map_when_structure_recovery_document_map_enabled(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1"), _build_paragraph(source_index=1, text="Основной текст")]
    captured = {}

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())

    def _fake_build_document_map(paragraphs, *, client, model, timeout, max_input_paragraphs, max_input_tokens, preview_chars, progress_callback):
        captured["call"] = {
            "paragraphs": paragraphs,
            "client": client,
            "model": model,
            "timeout": timeout,
            "max_input_paragraphs": max_input_paragraphs,
            "max_input_tokens": max_input_tokens,
            "preview_chars": preview_chars,
        }
        captured["result"] = preparation.DocumentMap(
            body_start_logical_index=0,
            toc_region=None,
            outline=(),
            paragraph_anchors={},
            review_zones=(),
            model_used=model,
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(0, 1),
        )
        return captured["result"]

    monkeypatch.setattr(preparation, "build_document_map", _fake_build_document_map)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "off",
            "structure_recognition_enabled": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_timeout_seconds": 45,
            "structure_recovery_document_map_max_input_paragraphs": 200,
            "structure_recovery_document_map_max_input_tokens": 32000,
            "structure_recovery_document_map_preview_chars": 90,
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    assert captured["call"]["paragraphs"] == paragraphs
    assert captured["call"]["model"] == "openrouter:test/document-map"
    assert captured["call"]["timeout"] == 45.0
    assert captured["call"]["max_input_paragraphs"] == 200
    assert captured["call"]["max_input_tokens"] == 32000
    assert captured["call"]["preview_chars"] == 90
    assert result.document_map == captured["result"]
    assert [event["stage"] for event in events] == [
        "Разбор DOCX",
        "Структура извлечена",
        "Карта документа…",
        "Текст собран",
        "Смысловые блоки",
        "Задания собраны",
    ]


def test_run_document_map_stage_uses_cache_and_skips_second_builder_call(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="Heading"), _build_paragraph(source_index=1, text="Body")]
    calls = {"count": 0}

    def _fake_build_document_map(paragraphs, *, client, model, timeout, max_input_paragraphs, max_input_tokens, preview_chars, progress_callback):
        calls["count"] += 1
        return preparation.DocumentMap(
            body_start_logical_index=0,
            toc_region=None,
            outline=(),
            paragraph_anchors={},
            review_zones=(),
            model_used=model,
            total_tokens_used=17,
            processing_time_seconds=0.2,
            sampled=False,
            sampled_logical_indexes=(0, 1),
        )

    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(preparation, "build_document_map", _fake_build_document_map)

    app_config = {
        "structure_recovery_enabled": True,
        "structure_recovery_document_map_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "structure_recovery_document_map_model": "openrouter:test/document-map",
        "structure_recovery_document_map_timeout_seconds": 45,
        "structure_recovery_document_map_max_input_paragraphs": 200,
        "structure_recovery_document_map_preview_chars": 120,
        "structure_recovery_document_map_max_input_tokens": 180000,
        "structure_recovery_document_map_cache_enabled": True,
        "structure_recovery_document_map_save_debug_artifacts": False,
    }

    result_a = preparation._run_document_map_stage(
        paragraphs=paragraphs,
        image_assets=[],
        app_config=app_config,
        progress_callback=None,
        normalization_report=None,
        relation_report=None,
    )
    result_b = preparation._run_document_map_stage(
        paragraphs=paragraphs,
        image_assets=[],
        app_config=app_config,
        progress_callback=None,
        normalization_report=None,
        relation_report=None,
    )

    assert calls["count"] == 1
    assert result_a == result_b
    assert result_a is not result_b


def test_run_document_map_stage_writes_debug_artifact(monkeypatch, tmp_path):
    paragraphs = [_build_paragraph(source_index=0, text="Heading"), _build_paragraph(source_index=1, text="Body")]

    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(preparation, "_DOCUMENT_MAP_DEBUG_DIR", tmp_path)
    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda paragraphs, *, client, model, timeout, max_input_paragraphs, max_input_tokens, preview_chars, progress_callback: preparation.DocumentMap(
            body_start_logical_index=0,
            toc_region=None,
            outline=(),
            paragraph_anchors={},
            review_zones=(),
            model_used=model,
            total_tokens_used=17,
            processing_time_seconds=0.2,
            sampled=False,
            sampled_logical_indexes=(0, 1),
        ),
    )

    app_config = {
        "structure_recovery_enabled": True,
        "structure_recovery_document_map_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "structure_recovery_document_map_model": "openrouter:test/document-map",
        "structure_recovery_document_map_timeout_seconds": 45,
        "structure_recovery_document_map_max_input_paragraphs": 200,
        "structure_recovery_document_map_preview_chars": 120,
        "structure_recovery_document_map_max_input_tokens": 180000,
        "structure_recovery_document_map_cache_enabled": False,
        "structure_recovery_document_map_save_debug_artifacts": True,
    }

    document_map = preparation._run_document_map_stage(
        paragraphs=paragraphs,
        image_assets=[],
        app_config=app_config,
        progress_callback=None,
        normalization_report=None,
        relation_report=None,
    )

    cache_key = preparation._build_document_map_cache_key(paragraphs=paragraphs, app_config=app_config)
    artifact_path = tmp_path / f"{cache_key}.json"

    assert document_map is not None
    assert artifact_path.exists()

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert payload["cache_key"] == cache_key
    assert payload["stage"] == "document_map_v1"
    assert payload["model"] == "openrouter:test/document-map"
    assert payload["prompt_version"] == 1
    assert payload["descriptor_schema_version"] == 1
    assert payload["coordinate_schema_version"] == 1
    assert payload["sampled"] is False
    assert payload["sampled_logical_indexes"] == [0, 1]
    assert payload["document_map"]["model_used"] == "openrouter:test/document-map"


def test_prepare_document_for_processing_reports_pdf_import_stage(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(["p1"], [], _build_report(raw=1, logical=1)),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text-value")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block-a"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "a", "target_chars": 1, "context_chars": 0}])

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload(
            "report.docx",
            b"docx-bytes",
            "report.pdf:10:hash",
            source_format="pdf",
            conversion_backend="libreoffice",
        ),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    assert events[0]["stage"] == "Разбор DOCX (из PDF)"
    assert events[0]["detail"] == "Извлекаю абзацы, встроенные изображения и структуру из сконвертированного DOCX."
    assert events[0]["metrics"]["source_format"] == "pdf"


def test_prepare_document_for_processing_tracks_ai_heading_demotions_against_heuristics(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraph = _build_paragraph(source_index=0, text="Короткий заголовок", role="heading")
    paragraph.heading_source = "heuristic"
    paragraph.heading_level = 2
    paragraph.structural_role = "heading"

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result([paragraph], [], _build_report(raw=1, logical=1)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda *args, **kwargs: StructureMap(
            classifications={0: ParagraphClassification(index=0, role="body", heading_level=None, confidence="high")},
            model_used="gpt-4o-mini",
            total_tokens_used=9,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "Короткий заголовок")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "always",
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.ai_classified_count == 1
    assert result.ai_heading_count == 0
    assert result.ai_role_change_count == 1
    assert result.ai_heading_promotion_count == 0
    assert result.ai_heading_demotion_count == 1
    assert result.ai_structural_role_change_count == 1


def test_prepare_document_for_processing_falls_back_to_heuristics_when_structure_recognition_setup_fails(monkeypatch):
    session_state = {"preparation_cache": {}}

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result([_build_paragraph(source_index=0, text="text")], [], _build_report(raw=1, logical=1)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: (_ for _ in ()).throw(RuntimeError("missing api key")))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "always",
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
        },
    )
    logged_events = []
    monkeypatch.setattr(preparation, "log_event", lambda level, event, message, **context: logged_events.append((event, context)))

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.ai_classified_count == 0
    assert result.ai_heading_count == 0
    assert result.ai_role_change_count == 0
    assert result.ai_heading_promotion_count == 0
    assert result.ai_heading_demotion_count == 0
    assert result.ai_structural_role_change_count == 0
    assert result.structure_map is None
    assert logged_events[1][0] == "structure_recognition_fallback"


def test_prepare_document_for_processing_logs_cache_miss_and_hit(monkeypatch):
    session_state = {"preparation_cache": {}}
    logged_events = []

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([], [], None))
    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([], [], None))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])
    monkeypatch.setattr(preparation, "log_event", lambda level, event, message, **context: logged_events.append((event, context)))

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    relevant_events = [entry for entry in logged_events if entry[0] in {"preparation_cache_miss", "preparation_cache_hit"}]

    assert relevant_events == [
        (
            "preparation_cache_miss",
            {"prepared_source_key": "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=auto:sv=1:srec=0:ai_first:c1"},
        ),
        (
            "preparation_cache_hit",
            {
                "prepared_source_key": "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=auto:sv=1:srec=0:ai_first:c1",
                "cache_level": "session",
                "structure_status_note": "Структура: auto-режим, эскалация в AI не потребовалась; структурный риск не найден.",
                "structure_recognition_mode": "auto",
                "structure_ai_attempted": False,
                "escalation_recommended": False,
                "escalation_reasons": [],
            },
        ),
    ]


def test_prepare_document_for_processing_auto_mode_runs_validation_and_skips_ai_without_risk(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []
    paragraphs = [
        _build_paragraph(source_index=0, text="Heading", role="heading"),
        _build_paragraph(source_index=1, text="Long body paragraph with enough words to avoid escalation."),
    ]
    paragraphs[0].heading_source = "explicit"

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    build_structure_calls = {"count": 0}
    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: build_structure_calls.__setitem__("count", build_structure_calls["count"] + 1))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "auto",
            "structure_recognition_enabled": False,
            "structure_recognition_model": "gpt-5-mini",
            "structure_validation_enabled": True,
            "structure_validation_min_paragraphs_for_auto_gate": 40,
            "structure_validation_min_explicit_heading_density": 0.003,
            "structure_validation_max_suspicious_short_body_ratio_without_escalation": 0.05,
            "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation": 0.03,
            "structure_validation_toc_like_sequence_min_length": 4,
            "structure_validation_forbid_heading_only_collapse": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_validation_block_on_high_risk_noop": True,
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-5-mini"),
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    assert [event["stage"] for event in events] == [
        "Разбор DOCX",
        "Структура извлечена",
        "Структура: валидация",
        "Структура: детерминированно",
        "Текст собран",
        "Смысловые блоки",
        "Задания собраны",
    ]
    assert build_structure_calls["count"] == 0
    assert result.structure_map is None
    assert result.structure_validation_report is not None
    assert result.structure_validation_report.escalation_recommended is False


def test_prepare_document_for_processing_auto_mode_runs_ai_when_gate_escalates(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []
    paragraphs = [_build_paragraph(source_index=index, text=f"Section {index}") for index in range(50)]

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=50, logical=50)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda *args, **kwargs: StructureMap(
            classifications={0: ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")},
            model_used="gpt-5-mini",
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "auto",
            "structure_recognition_enabled": False,
            "structure_recognition_model": "gpt-5-mini",
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_min_paragraphs_for_auto_gate": 40,
            "structure_validation_min_explicit_heading_density": 0.5,
            "structure_validation_max_suspicious_short_body_ratio_without_escalation": 0.05,
            "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation": 0.03,
            "structure_validation_toc_like_sequence_min_length": 4,
            "structure_validation_forbid_heading_only_collapse": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_validation_block_on_high_risk_noop": True,
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-5-mini"),
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    assert [event["stage"] for event in events][:6] == [
        "Разбор DOCX",
        "Структура извлечена",
        "Структура: валидация",
        "Распознавание структуры…",
        "Применение структуры…",
        "Структура распознана",
    ]
    assert result.structure_validation_report is not None
    assert result.structure_validation_report.escalation_recommended is True
    assert result.structure_map is not None
    assert result.structure_recognition_mode == "auto"
    assert result.structure_ai_attempted is True


def test_prepare_document_for_processing_marks_quality_gate_blocked_on_high_risk_ai_noop(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [_build_paragraph(source_index=index, text=f"Section {index}") for index in range(50)]

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=50, logical=50)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda *args, **kwargs: StructureMap(
            classifications={},
            model_used="gpt-5-mini",
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "auto",
            "structure_recognition_enabled": False,
            "structure_recognition_model": "gpt-5-mini",
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_min_paragraphs_for_auto_gate": 40,
            "structure_validation_min_explicit_heading_density": 0.5,
            "structure_validation_max_suspicious_short_body_ratio_without_escalation": 0.05,
            "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation": 0.03,
            "structure_validation_toc_like_sequence_min_length": 4,
            "structure_validation_forbid_heading_only_collapse": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_validation_block_on_high_risk_noop": True,
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-5-mini"),
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.quality_gate_status == "warning"
    assert result.quality_gate_reasons == (
        "toc_like_sequence_without_bounded_region",
        "structure_recognition_noop_on_high_risk",
    )


def test_prepare_document_for_processing_runs_readiness_gate_in_always_mode(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [_build_paragraph(source_index=index, text=f"Section {index}") for index in range(50)]

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=50, logical=50)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda *args, **kwargs: StructureMap(
            classifications={},
            model_used="gpt-5-mini",
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "always",
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-5-mini",
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_min_paragraphs_for_auto_gate": 40,
            "structure_validation_min_explicit_heading_density": 0.5,
            "structure_validation_max_suspicious_short_body_ratio_without_escalation": 0.05,
            "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation": 0.03,
            "structure_validation_toc_like_sequence_min_length": 4,
            "structure_validation_forbid_heading_only_collapse": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_validation_block_on_high_risk_noop": True,
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-5-mini"),
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.structure_recognition_mode == "always"
    assert result.structure_validation_report is not None
    assert result.quality_gate_status == "warning"
    assert "structure_recognition_noop_on_high_risk" in result.quality_gate_reasons


def test_prepare_document_for_processing_blocks_mixed_first_block_toc_and_body_start(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0),
        ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", source_index=1),
        ParagraphUnit(text="Epigraph line", role="body", structural_role="epigraph", source_index=2),
        ParagraphUnit(text="Introduction", role="heading", structural_role="body", heading_source="heuristic", source_index=3),
        ParagraphUnit(
            text="Body paragraph with enough words to remain ordinary prose after the heading.",
            role="body",
            structural_role="body",
            source_index=4,
        ),
    ]

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=5, logical=5)),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(
        preparation,
        "build_semantic_blocks",
        lambda paragraphs, max_chars, relations=None: [DocumentBlock(paragraphs=list(paragraphs))],
    )
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_mode": "off",
            "structure_recognition_enabled": False,
            "structure_validation_enabled": True,
            "structure_validation_min_paragraphs_for_auto_gate": 40,
            "structure_validation_min_explicit_heading_density": 0.003,
            "structure_validation_max_suspicious_short_body_ratio_without_escalation": 0.05,
            "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation": 0.03,
            "structure_validation_toc_like_sequence_min_length": 4,
            "structure_validation_forbid_heading_only_collapse": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_validation_block_on_high_risk_noop": True,
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-5-mini"),
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        processing_operation="translate",
        session_state=session_state,
    )

    assert result.quality_gate_status == "warning"
    assert result.quality_gate_reasons == (
        "first_block_mixed_toc_and_epigraph",
        "first_block_mixed_toc_and_body_start",
    )


def test_build_structure_processing_status_note_describes_auto_escalation():
    report = preparation.StructureValidationReport(
        paragraph_count=50,
        nonempty_paragraph_count=50,
        explicit_heading_count=0,
        heuristic_heading_count=0,
        suspicious_short_body_count=8,
        all_caps_body_count=0,
        centered_body_count=0,
        toc_like_sequence_count=1,
        ambiguous_paragraph_count=8,
        explicit_heading_density=0.0,
        suspicious_short_body_ratio=0.16,
        all_caps_or_centered_body_ratio=0.0,
        escalation_recommended=True,
        escalation_reasons=("low_explicit_heading_density", "toc_like_sequence_detected"),
        isolated_marker_paragraph_count=0,
        large_front_matter_block_risk=False,
        toc_region_bounded_count=0,
        expected_heading_candidates_from_toc=3,
        structure_quality_risk_level="high",
        readiness_status="blocked_unsafe_best_effort_only",
        readiness_reasons=("toc_like_sequence_without_bounded_region",),
    )
    source = type(
        "StructureSource",
        (),
        {
            "structure_recognition_mode": "auto",
            "structure_validation_report": report,
            "structure_map": object(),
            "structure_ai_attempted": True,
            "structure_recognition_summary": StructureRecognitionSummary(ai_classified_count=6, ai_heading_count=2),
        },
    )()

    note = preparation.build_structure_processing_status_note(source)

    assert note == (
        "Структура: auto-режим, выполнена эскалация в AI; классифицировано 6 абзацев, найдено 2 заголовков. "
        "Причины: мало явных заголовков, обнаружен TOC-подобный фрагмент."
    )


def test_build_structure_processing_status_note_marks_high_risk_noop_as_blocked():
    report = preparation.StructureValidationReport(
        paragraph_count=50,
        nonempty_paragraph_count=50,
        explicit_heading_count=0,
        heuristic_heading_count=0,
        suspicious_short_body_count=8,
        all_caps_body_count=0,
        centered_body_count=0,
        toc_like_sequence_count=1,
        ambiguous_paragraph_count=8,
        explicit_heading_density=0.0,
        suspicious_short_body_ratio=0.16,
        all_caps_or_centered_body_ratio=0.0,
        escalation_recommended=True,
        escalation_reasons=("low_explicit_heading_density", "toc_like_sequence_detected"),
        isolated_marker_paragraph_count=1,
        large_front_matter_block_risk=False,
        toc_region_bounded_count=0,
        expected_heading_candidates_from_toc=3,
        structure_quality_risk_level="high",
        readiness_status="blocked_unsafe_best_effort_only",
        readiness_reasons=("toc_like_sequence_without_bounded_region",),
    )
    source = type(
        "StructureSource",
        (),
        {
            "structure_recognition_mode": "auto",
            "structure_validation_report": report,
            "structure_map": object(),
            "structure_ai_attempted": True,
            "structure_recognition_summary": StructureRecognitionSummary(ai_classified_count=0, ai_heading_count=0),
        },
    )()

    note = preparation.build_structure_processing_status_note(source)

    assert note == (
        "Структура: auto-режим, выполнена эскалация в AI; AI не внёс изменений, документ помечен как "
        "требующий structural repair. Причины: мало явных заголовков, обнаружен TOC-подобный фрагмент."
    )


def test_prepare_document_for_processing_retains_normalization_report_on_fresh_preparation(monkeypatch):
    session_state = {"preparation_cache": {}}
    report = _build_report(raw=4, logical=3, merged_groups=1, merged_raw=2)

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result([{"text": "p"}], [], report),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.normalization_report == report
    assert result.normalization_report is not report


def test_prepare_document_for_processing_retains_normalization_report_across_cache_hit_clone(monkeypatch):
    session_state = {"preparation_cache": {}}
    extract_calls = {"count": 0}

    def fake_extract(uploaded_file):
        extract_calls["count"] += 1
        return _build_extract_result([{"text": "p"}], [], _build_report(raw=4, logical=3, merged_groups=1, merged_raw=2))

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    first = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )
    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert first.normalization_report is not None
    first.normalization_report.merged_group_count = 99

    assert extract_calls["count"] == 1
    assert second.cached is True
    assert second.normalization_report is not None
    assert second.normalization_report.merged_group_count == 1
    assert second.normalization_report is not first.normalization_report


def test_prepare_document_for_processing_reports_cache_hit_normalization_metrics(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(["p1", "p2"], ["img"], _build_report(raw=3, logical=2, merged_groups=1, merged_raw=2)),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text-value")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block-a", "block-b"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "a", "target_chars": 1, "context_chars": 0}, {"target_text": "b", "target_chars": 1, "context_chars": 0}])

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    assert len(events) == 1
    assert events[0]["stage"] == "Подготовка документа"
    assert events[0]["metrics"]["cached"] is True
    assert events[0]["metrics"]["raw_paragraph_count"] == 3
    assert events[0]["metrics"]["logical_paragraph_count"] == 2
    assert events[0]["metrics"]["merged_group_count"] == 1
    assert events[0]["metrics"]["merged_raw_paragraph_count"] == 2


def test_prepare_document_for_processing_emits_heartbeat_during_extraction(monkeypatch):
    """Live-progress contract: while the blocking DOCX extraction call runs,
    `HeartbeatBeacon` must continue to emit progress events so the UI activity
    feed and progress bar do not freeze.
    """
    import time as _time

    import docxaicorrector.processing.processing_runtime as _processing_runtime

    events: list[dict] = []
    session_state = {"preparation_cache": {}}

    class _FastBeacon(_processing_runtime.HeartbeatBeacon):
        def __init__(self, *args, **kwargs):
            kwargs["interval_seconds"] = 0.05
            super().__init__(*args, **kwargs)

    def _slow_extract(uploaded_file, *, app_config=None):
        _time.sleep(0.3)
        return _build_extract_result(["p1"], [], _build_report(raw=1, logical=1))

    monkeypatch.setattr(preparation, "HeartbeatBeacon", _FastBeacon)
    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", _slow_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text-value")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block-a"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "a", "target_chars": 1, "context_chars": 0}])

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    initial_stage = "Разбор DOCX"
    heartbeat_events = [e for e in events if e.get("stage") == initial_stage and "сек идёт чтение" in (e.get("detail") or "")]
    # Extraction takes ~0.3s with 0.05s heartbeat interval — expect at least 2 ticks.
    assert len(heartbeat_events) >= 2, [e.get("detail") for e in events]
    # Progress value during heartbeat should match the wired-in 0.22 anchor.
    assert all(abs(float(e["progress"]) - 0.22) < 1e-6 for e in heartbeat_events)
