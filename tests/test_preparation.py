from io import BytesIO
import json
from threading import Event, Thread
from types import SimpleNamespace
from typing import Any, cast

from docx import Document
import pytest

import docxaicorrector.document.segments as document_segments
import docxaicorrector.processing.preparation as preparation
import docxaicorrector.structure.document_map as document_map_module
import docxaicorrector.structure.recognition as recognition_module
import docxaicorrector.validation.structural as structural_validation
from docxaicorrector.core.config import ModelRegistry, TextModelConfig
from docxaicorrector.core.models import DocumentBlock
from docxaicorrector.core.models import DocumentMap, DocumentMapAnchor, DocumentMapOutlineEntry, DocumentMapReviewZone, DocumentMapSplitHint, DocumentMapTocEntry, DocumentMapTocRegion
from docxaicorrector.core.models import DocumentTopologyProjection, EmbeddedStructureHint, ParagraphClassification
from docxaicorrector.core.models import ImageAsset, ImageVariantCandidate
from docxaicorrector.core.models import LayoutArtifactCleanupReport, ParagraphBoundaryNormalizationReport
from docxaicorrector.core.models import ParagraphRelation, ParagraphRelationDecision, ParagraphUnit, RelationNormalizationReport
from docxaicorrector.core.models import StructuralUnit, StructureMap
from docxaicorrector.core.models import StructureRecognitionSummary, StructureRepairReport
from docxaicorrector.document.segments import CHAPTER_SEGMENTS_DETECTOR_VERSION
from docxaicorrector.processing.processing_runtime import FrozenUploadPayload, build_in_memory_uploaded_file, build_preparation_request_marker
from docxaicorrector.structure.document_map import DocumentMapRequestTimeout, DocumentMapSchemaError
from docxaicorrector.structure.reconciliation import ReconciliationReport


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


def _build_default_prepared_source_key(file_token: str, chunk_size: int = 6000) -> str:
    app_config = preparation.load_app_config()
    configured_relation_kinds = app_config.get("relation_normalization_enabled_relation_kinds", ())
    if not isinstance(configured_relation_kinds, (list, tuple, set)):
        configured_relation_kinds = ()
    relation_key = (
        f"{str(app_config.get('relation_normalization_profile', 'phase2_default') or 'phase2_default')}:"
        f"{','.join(sorted(str(kind) for kind in configured_relation_kinds))}"
    )
    return preparation.build_prepared_source_key(
        file_token,
        chunk_size,
        paragraph_boundary_normalization_mode=str(
            app_config.get("paragraph_boundary_normalization_mode", "high_only") or "high_only"
        ),
        paragraph_boundary_ai_review_mode=str(app_config.get("paragraph_boundary_ai_review_mode", "off") or "off"),
        relation_normalization_key=relation_key,
        layout_artifact_cleanup_key=preparation._resolve_layout_cleanup_cache_key(app_config),
        structure_recognition_enabled=bool(app_config.get("structure_recognition_enabled", False)),
        structure_recognition_mode=str(app_config.get("structure_recognition_mode", "") or ""),
        structure_recovery_enabled=bool(app_config.get("structure_recovery_enabled", False)),
        structure_recovery_mode=str(app_config.get("structure_recovery_mode", "ai_first") or "ai_first"),
        structure_recovery_coordinate_schema_version=int(
            app_config.get(
                "structure_recovery_coordinate_schema_version",
                preparation.STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION,
            )
            or preparation.STRUCTURE_RECOVERY_COORDINATE_SCHEMA_VERSION
        ),
        structure_validation_enabled=bool(app_config.get("structure_validation_enabled", True)),
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


def test_flatten_layout_cleanup_metrics_uses_flagged_counts_for_signal_mode():
    metrics = preparation.flatten_layout_cleanup_metrics(
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


def _make_ai_first_config(
    *,
    structure_recognition_model: str = "gpt-4o-mini",
    relation_kinds: tuple[str, ...] = ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
    **overrides,
):
    config = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": relation_kinds,
        "structure_recognition_mode": "always",
        "structure_recognition_enabled": True,
        "structure_recognition_model": structure_recognition_model,
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
        "structure_recovery_topology_projection_enabled": False,
        "structure_recovery_topology_projection_save_debug_artifacts": True,
        "structure_recovery_topology_projection_binding_splits_enabled": False,
        "models": _build_runtime_model_registry(structure_recognition_model=structure_recognition_model),
    }
    config.update(overrides)
    if "models" not in overrides:
        resolved_model = str(config.get("structure_recognition_model", structure_recognition_model) or structure_recognition_model)
        config["models"] = _build_runtime_model_registry(structure_recognition_model=resolved_model)
    return config


def test_run_document_topology_projection_stage_disabled_does_not_write_artifact(monkeypatch, tmp_path):
    paragraph = _build_paragraph(source_index=10, text="Chapter Eleven")
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(
                title="Chapter Eleven",
                level=1,
                logical_index=10,
                confidence="high",
                evidence=("outline_entry",),
            ),
        ),
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(10,),
    )
    artifact_dir = tmp_path / "document_topology"
    monkeypatch.setattr(preparation, "_DOCUMENT_TOPOLOGY_DEBUG_DIR", artifact_dir)

    projection, status, reason = preparation._run_document_topology_projection_stage(
        paragraphs=[paragraph],
        document_map=document_map,
        app_config=_make_ai_first_config(structure_recovery_topology_projection_enabled=False),
    )

    assert projection is None
    assert status == "disabled"
    assert reason == "topology_projection_disabled"
    assert not artifact_dir.exists()


def test_run_document_topology_projection_stage_writes_empty_projection_artifact_when_enabled(monkeypatch, tmp_path):
    paragraphs = [
        _build_paragraph(source_index=10, text="Body paragraph."),
        _build_paragraph(source_index=11, text="Another body paragraph."),
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
        sampled_logical_indexes=(10, 11),
    )
    artifact_dir = tmp_path / "document_topology"
    monkeypatch.setattr(preparation, "_DOCUMENT_TOPOLOGY_DEBUG_DIR", artifact_dir)

    projection, status, reason = preparation._run_document_topology_projection_stage(
        paragraphs=paragraphs,
        document_map=document_map,
        app_config=_make_ai_first_config(
            structure_recovery_topology_projection_enabled=True,
            structure_recovery_topology_projection_save_debug_artifacts=True,
        ),
    )

    assert projection is not None
    assert status == "no_operations"
    assert reason == ""
    artifact_path = artifact_dir / f"{projection.cache_key}.json"
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["stage"] == "document_topology_projection_v1"
    assert payload["operations"] == []
    assert payload["projected_units"] == []


def test_run_document_topology_projection_stage_writes_binding_split_payload_when_enabled(monkeypatch, tmp_path):
    paragraphs = [_build_paragraph(source_index=10, text="this page intentionally left blank chapter nine")]
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
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(10,),
    )
    artifact_dir = tmp_path / "document_topology"
    monkeypatch.setattr(preparation, "_DOCUMENT_TOPOLOGY_DEBUG_DIR", artifact_dir)

    projection, status, reason = preparation._run_document_topology_projection_stage(
        paragraphs=paragraphs,
        document_map=document_map,
        app_config=_make_ai_first_config(
            structure_recovery_topology_projection_enabled=True,
            structure_recovery_topology_projection_binding_splits_enabled=True,
            structure_recovery_topology_projection_save_debug_artifacts=True,
        ),
    )

    assert projection is not None
    assert status == "built"
    assert reason == ""
    artifact_path = artifact_dir / f"{projection.cache_key}.json"
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert [operation["op"] for operation in payload["operations"]] == ["split_page_artifact_from_heading"]
    assert [unit["unit_type"] for unit in payload["projected_units"]] == ["page_artifact", "chapter_heading"]


def test_run_document_topology_projection_stage_logs_compound_toc_split_operation_counts_when_enabled(monkeypatch, tmp_path):
    paragraphs = [_build_paragraph(source_index=40, text="73 6 Strategies for Banking 95 7 Strategies for Business and Entrepreneurs")]
    document_map = DocumentMap(
        body_start_logical_index=141,
        toc_region=DocumentMapTocRegion(
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
            confidence="high",
        ),
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
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(40,),
    )
    artifact_dir = tmp_path / "document_topology"
    captured_events: list[tuple[str, dict[str, object]]] = []

    def _fake_log_event(level, event_id, message, **kwargs):
        _ = level, message
        captured_events.append((event_id, kwargs))

    monkeypatch.setattr(preparation, "_DOCUMENT_TOPOLOGY_DEBUG_DIR", artifact_dir)
    monkeypatch.setattr(preparation, "log_event", _fake_log_event)

    projection, status, reason = preparation._run_document_topology_projection_stage(
        paragraphs=paragraphs,
        document_map=document_map,
        app_config=_make_ai_first_config(
            structure_recovery_topology_projection_enabled=True,
            structure_recovery_topology_projection_binding_splits_enabled=True,
            structure_recovery_topology_projection_save_debug_artifacts=True,
        ),
    )

    assert projection is not None
    assert status == "built"
    assert reason == ""
    artifact_path = artifact_dir / f"{projection.cache_key}.json"
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert [operation["op"] for operation in payload["operations"]] == ["split_compound_toc_entries"]
    assert [unit["unit_type"] for unit in payload["projected_units"]] == ["toc_entry", "toc_entry"]
    built_event = next(kwargs for event_id, kwargs in captured_events if event_id == "document_topology_projection_built")
    assert built_event["operation_counts"] == {"split_compound_toc_entries": 1}
    assert built_event["unit_type_counts"] == {"toc_entry": 2}


def test_apply_prepared_snapshot_fields_exposes_document_topology_projection_from_prepared():
    projection = DocumentTopologyProjection(
        cache_key="topology-key",
        document_map_cache_key="document-map-key",
        projected_units=(
            StructuralUnit(
                unit_type="chapter_heading",
                logical_indexes=(10, 11),
                canonical_text="Chapter Eleven Governance and We",
                role="heading",
                heading_level=1,
                confidence="high",
                authority="document_map_outline",
                evidence=("outline_entry", "adjacent_short_heading_fragments"),
            ),
        ),
    )
    prepared = SimpleNamespace(
        document_map=None,
        document_map_status="not_requested",
        document_map_status_reason="",
        document_topology_projection=projection,
        document_topology_projection_status="built",
        document_topology_projection_status_reason="",
        structure_recognition_summary=StructureRecognitionSummary(),
    )

    snapshot = structural_validation._build_preparation_diagnostic_defaults([])
    structural_validation._apply_prepared_snapshot_fields(snapshot, prepared)

    assert snapshot["document_topology_projection_status"] == "built"
    assert snapshot["document_topology_projection_status_reason"] == ""
    assert snapshot["document_topology_projection"]["cache_key"] == "topology-key"
    assert snapshot["document_topology_projection"]["projected_units"][0]["logical_indexes"] == (10, 11)


def test_apply_topology_projection_snapshot_fallback_reconstructs_projection_from_prepared_document_map():
    paragraphs = [
        ParagraphUnit(text="11", role="body", structural_role="body", source_index=10, logical_index=10),
        ParagraphUnit(text="Governance and We", role="body", structural_role="body", source_index=11, logical_index=11),
        ParagraphUnit(text="the Citizens", role="body", structural_role="body", source_index=12, logical_index=12),
        ParagraphUnit(text="An Ancient Future?", role="body", structural_role="body", source_index=13, logical_index=13),
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
        paragraph_anchors={10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
        review_zones=(),
        sampled=False,
        sampled_logical_indexes=(10, 11, 12, 13),
    )
    prepared = SimpleNamespace(
        paragraphs=paragraphs,
        document_map=document_map,
        document_topology_projection=None,
        document_topology_projection_status="not_requested",
        document_topology_projection_status_reason="",
    )

    snapshot = structural_validation._build_preparation_diagnostic_defaults([])
    structural_validation._apply_topology_projection_snapshot_fallback(
        snapshot,
        prepared,
        app_config=_make_ai_first_config(structure_recovery_topology_projection_enabled=True),
    )

    assert snapshot["document_topology_projection_status"] == "built"
    assert snapshot["document_topology_projection_status_reason"] == ""
    assert len(snapshot["document_topology_projection"]["operations"]) == 1
    assert snapshot["document_topology_projection"]["projected_units"][0]["logical_indexes"] == (10, 11, 12, 13)


def test_clone_prepared_document_preserves_document_topology_projection_fields():
    projection = DocumentTopologyProjection(
        cache_key="topology-key",
        document_map_cache_key="document-map-key",
        operations=(),
        projected_units=(
            StructuralUnit(
                unit_type="toc_entry",
                logical_indexes=(6,),
                canonical_text="8 Strategies for Governments",
                role="toc_entry",
                heading_level=None,
                confidence="high",
                authority="document_map_toc",
                evidence=("bounded_toc_region",),
                unit_id="u_topology_test",
            ),
        ),
    )
    prepared = preparation.PreparedDocumentData(
        source_text="",
        paragraphs=[],
        image_assets=[],
        relations=[],
        jobs=[],
        prepared_source_key="original-key",
        document_topology_projection=projection,
        document_topology_projection_status="built",
        document_topology_projection_status_reason="",
    )

    cloned = preparation._clone_prepared_document(prepared, "cached-key", cached=True)

    assert cloned.document_topology_projection is not None
    assert cloned.document_topology_projection is not projection
    assert cloned.document_topology_projection.cache_key == "topology-key"
    assert cloned.document_topology_projection.projected_units[0].unit_id == "u_topology_test"
    assert cloned.document_topology_projection_status == "built"
    assert cloned.document_topology_projection_status_reason == ""


def _stub_single_block_preparation_builders(monkeypatch, *, source_text: str, job_text: str = "block"):
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: source_text)

    def _fake_build_semantic_blocks(
        paragraphs,
        max_chars,
        relations=None,
        hard_boundary_paragraph_ids=None,
        structure_phase="post_ai_final",
    ):
        return ["block"]

    def _fake_build_editing_jobs(blocks, max_chars, processing_operation="edit", structure_phase="post_ai_final"):
        return [{"target_text": job_text, "target_chars": len(job_text), "context_chars": 0}]

    monkeypatch.setattr(preparation, "build_semantic_blocks", _fake_build_semantic_blocks)
    monkeypatch.setattr(preparation, "build_editing_jobs", _fake_build_editing_jobs)


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


def test_build_structure_map_cache_key_includes_targeted_reconciliation_settings():
    paragraph = _build_paragraph(source_index=7, text="Section A")
    paragraph.logical_index = 3

    base_config = {
        "structure_recognition_max_window_paragraphs": 1800,
        "structure_recognition_overlap_paragraphs": 50,
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "structure_recovery_reconciliation_targeted_enabled": True,
        "structure_recovery_reconciliation_targeted_threshold": 3,
        "structure_recovery_reconciliation_targeted_timeout_seconds": 45,
        "structure_recovery_reconciliation_targeted_max_paragraphs": 60,
        "models": _build_runtime_model_registry(),
    }

    changed_threshold = dict(base_config)
    changed_threshold["structure_recovery_reconciliation_targeted_threshold"] = 5

    changed_timeout = dict(base_config)
    changed_timeout["structure_recovery_reconciliation_targeted_timeout_seconds"] = 30

    changed_max_paragraphs = dict(base_config)
    changed_max_paragraphs["structure_recovery_reconciliation_targeted_max_paragraphs"] = 24

    key_base = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=base_config)
    key_threshold = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=changed_threshold)
    key_timeout = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=changed_timeout)
    key_max_paragraphs = preparation._build_structure_map_cache_key(paragraphs=[paragraph], app_config=changed_max_paragraphs)

    assert key_base != key_threshold
    assert key_base != key_timeout
    assert key_base != key_max_paragraphs


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


def test_build_document_map_cache_key_ignores_invalid_hint_values_that_normalize_away():
    paragraph_a = _build_paragraph(source_index=2, text="Compound paragraph")
    paragraph_b = _build_paragraph(source_index=2, text="Compound paragraph")
    paragraph_a.logical_index = 2
    paragraph_b.logical_index = 2
    paragraph_a.heuristic_role_hint = "not-a-role"
    paragraph_a.heuristic_structural_role_hint = "not-a-structural-role"
    paragraph_a.heuristic_list_kind_hint = "not-a-list-kind"
    paragraph_a.heuristic_embedded_structure_hints = [
        EmbeddedStructureHint(
            text="Introduction",
            role="not-a-role",
            structural_role="not-a-structural-role",
            list_kind="not-a-list-kind",
        )
    ]
    paragraph_b.heuristic_embedded_structure_hints = [EmbeddedStructureHint(text="Introduction")]

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

    assert key_a == key_b


def test_build_document_map_cache_key_includes_prompt_and_descriptor_versions(monkeypatch):
    paragraph = _build_paragraph(source_index=7, text="Section A")
    paragraph.logical_index = 3

    app_config = {
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_coordinate_schema_version": 1,
        "structure_recovery_document_map_model": "openrouter:test/document-map",
        "structure_recovery_document_map_max_input_paragraphs": 6000,
        "structure_recovery_document_map_max_input_tokens": 180000,
        "structure_recovery_document_map_preview_chars": 120,
    }

    key_a = preparation._build_document_map_cache_key(paragraphs=[paragraph], app_config=app_config)
    monkeypatch.setattr(preparation, "DOCUMENT_MAP_PROMPT_VERSION", preparation.DOCUMENT_MAP_PROMPT_VERSION + 1)
    key_b = preparation._build_document_map_cache_key(paragraphs=[paragraph], app_config=app_config)
    monkeypatch.setattr(
        preparation,
        "DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION",
        preparation.DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION + 1,
    )
    key_c = preparation._build_document_map_cache_key(paragraphs=[paragraph], app_config=app_config)

    assert key_a != key_b
    assert key_b != key_c


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
        structure_phase="pre_ai_diagnostic",
    )

    assert structure_fingerprint
    assert diagnostics.segment_count >= 1
    typography_evidence = [
        evidence
        for evidence in segments[0].boundary_evidence
        if evidence.source == "typography_fallback"
    ]
    assert typography_evidence
    assert typography_evidence[0].details["is_all_caps"] is True
    assert typography_evidence[0].details["is_bold"] is False


def test_detect_document_segments_post_ai_final_ignores_typography_only_heading_fallbacks():
    paragraphs = [
        ParagraphUnit(text="APPENDIX", role="body", paragraph_id="p0000", source_index=0),
        ParagraphUnit(text="Body paragraph", role="body", paragraph_id="p0001", source_index=1),
    ]

    segments, diagnostics, structure_fingerprint = preparation.detect_document_segments(
        paragraphs,
        source_content_hash16="abcd1234ef567890",
        chunk_size=6000,
        structure_phase="post_ai_final",
    )

    assert structure_fingerprint
    assert diagnostics.segment_count == 1
    assert segments[0].title == "Body Range 1"


def test_detect_document_segments_helper_propagates_resolved_structure_phase(monkeypatch):
    captured = {}

    def fake_detect_document_segments(paragraphs, *, source_content_hash16, chunk_size, structure_phase="post_ai_final"):
        captured["structure_phase"] = structure_phase
        return [], preparation.SegmentDetectionReport(), "fp"

    monkeypatch.setattr(preparation, "detect_document_segments", fake_detect_document_segments)

    _segments, _diagnostics, structure_fingerprint = preparation._detect_document_segments_with_optional_phase(
        paragraphs=[],
        source_content_hash16="abcd1234ef567890",
        chunk_size=6000,
        structure_phase="ai_first_degraded_fallback",
    )

    assert structure_fingerprint == "fp"
    assert captured["structure_phase"] == "ai_first_degraded_fallback"


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


def test_detect_document_segments_counts_hinted_toc_entries():
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="body", paragraph_id="p0000", source_index=0, heuristic_structural_role_hint="toc_header"),
        ParagraphUnit(text="1 Chapter 1", role="body", structural_role="body", paragraph_id="p0001", source_index=1, heuristic_structural_role_hint="toc_entry"),
        ParagraphUnit(text="Chapter 1", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0002", source_index=2),
        ParagraphUnit(text="First chapter body", role="body", paragraph_id="p0003", source_index=3),
    ]

    _segments, diagnostics, _structure_fingerprint = preparation.detect_document_segments(
        paragraphs,
        source_content_hash16="abcd1234ef567890",
        chunk_size=6000,
        structure_phase="pre_ai_diagnostic",
    )

    assert diagnostics.toc_entry_count == 2


def test_detect_document_segments_ignores_advisory_toc_hints_in_post_ai_final_phase():
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="body", paragraph_id="p0000", source_index=0, heuristic_structural_role_hint="toc_header"),
        ParagraphUnit(text="1 Chapter 1", role="body", structural_role="body", paragraph_id="p0001", source_index=1, heuristic_structural_role_hint="toc_entry"),
        ParagraphUnit(text="Chapter 1", role="heading", heading_level=1, heading_source="explicit", paragraph_id="p0002", source_index=2),
        ParagraphUnit(text="First chapter body", role="body", paragraph_id="p0003", source_index=3),
    ]

    _segments, diagnostics, _structure_fingerprint = preparation.detect_document_segments(
        paragraphs,
        source_content_hash16="abcd1234ef567890",
        chunk_size=6000,
        structure_phase="post_ai_final",
    )

    assert diagnostics.toc_entry_count == 0


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
    expected_keys = [
        _build_default_prepared_source_key("two:3:b"),
        _build_default_prepared_source_key("three:5:c"),
    ]

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

    assert list(session_state["preparation_cache"].keys()) == expected_keys


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
    expected_key = _build_default_prepared_source_key("report.docx:10:hash")

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

    cached_entry = session_state["preparation_cache"][expected_key]

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
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
    )
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
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
        "Структура: финальная валидация",
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
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
    )
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
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
    _stub_single_block_preparation_builders(monkeypatch, source_text="# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "load_app_config", lambda: _make_ai_first_config())

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
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
    )
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
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
    _stub_single_block_preparation_builders(monkeypatch, source_text="# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "load_app_config", lambda: _make_ai_first_config())

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
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
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
    _stub_single_block_preparation_builders(monkeypatch, source_text="# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "load_app_config", lambda: _make_ai_first_config())

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
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
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
            classifications={10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high")},
            model_used=model,
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    _stub_single_block_preparation_builders(monkeypatch, source_text="# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "load_app_config", lambda: _make_ai_first_config())

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.structure_map is not None
    assert result.structure_map.classifications[10].role == "heading"
    assert result.structure_map.classifications[10].heading_level == 1
    assert result.paragraphs[0].role == "heading"
    assert result.paragraphs[0].heading_level == 1


def test_prepare_document_for_processing_invokes_targeted_reconciliation_when_gap_exceeds_threshold(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        _build_paragraph(source_index=0, text="ГЛАВА 1"),
        _build_paragraph(source_index=1, text="Текст 1"),
        _build_paragraph(source_index=2, text="ГЛАВА 2"),
        _build_paragraph(source_index=3, text="Текст 2"),
    ]
    for logical_index, paragraph in enumerate(paragraphs, start=10):
        paragraph.logical_index = logical_index

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=4, logical=4)),
    )
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda paragraphs, *, client, model, timeout, max_input_paragraphs, max_input_tokens, preview_chars, progress_callback: DocumentMap(
            body_start_logical_index=10,
            toc_region=None,
            outline=(
                DocumentMapOutlineEntry(title="ГЛАВА 1", level=1, logical_index=10, confidence="high", evidence=("bold",)),
                DocumentMapOutlineEntry(title="ГЛАВА 2", level=1, logical_index=12, confidence="high", evidence=("bold",)),
            ),
            paragraph_anchors={
                10: DocumentMapAnchor(role="heading", heading_level=1, confidence="medium"),
                12: DocumentMapAnchor(role="heading", heading_level=1, confidence="medium"),
            },
            review_zones=(),
            model_used=model,
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(10, 11, 12, 13),
        ),
    )
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda paragraphs, *, client, model, max_window_paragraphs, overlap_paragraphs, timeout, document_map, preview_chars, target_input_tokens, progress_callback: StructureMap(
            classifications={
                10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high"),
                11: ParagraphClassification(index=11, role="body", heading_level=None, confidence="high"),
                12: ParagraphClassification(index=12, role="body", heading_level=None, confidence="high"),
                13: ParagraphClassification(index=13, role="body", heading_level=None, confidence="high"),
            },
            model_used=model,
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    targeted_calls = {"count": 0}

    def _fake_targeted(paragraphs, document_map, structure_map, report, *, client, model, timeout, max_paragraphs):
        targeted_calls["count"] += 1
        assert report.missing_outline_entries == (10, 12)
        return StructureMap(
            classifications={
                **structure_map.classifications,
                10: ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high"),
                12: ParagraphClassification(index=12, role="heading", heading_level=1, confidence="high"),
            },
            model_used=structure_map.model_used,
            total_tokens_used=structure_map.total_tokens_used + 50,
            processing_time_seconds=structure_map.processing_time_seconds,
            window_count=structure_map.window_count,
        )

    monkeypatch.setattr(preparation, "targeted_reclassify_with_reconciliation_context", _fake_targeted)
    _stub_single_block_preparation_builders(
        monkeypatch,
        source_text="# ГЛАВА 1\n\nТекст 1\n\n# ГЛАВА 2\n\nТекст 2",
    )
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: _make_ai_first_config(
            structure_recovery_reconciliation_targeted_enabled=True,
            structure_recovery_reconciliation_targeted_threshold=1,
            structure_recovery_reconciliation_targeted_max_paragraphs=10,
            structure_recovery_reconciliation_targeted_timeout_seconds=45,
        ),
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert targeted_calls["count"] == 1
    assert result.structure_map is not None
    assert result.structure_map.classifications[10].role == "heading"
    assert result.structure_map.classifications[12].role == "heading"


def test_run_structure_recognition_applies_final_reconciled_map_after_targeted_recall(monkeypatch):
    paragraphs = [
        _build_paragraph(source_index=0, text="ГЛАВА 1"),
        _build_paragraph(source_index=1, text="Текст 1"),
        _build_paragraph(source_index=2, text="ГЛАВА 2"),
        _build_paragraph(source_index=3, text="Текст 2"),
    ]
    for logical_index, paragraph in enumerate(paragraphs, start=10):
        paragraph.logical_index = logical_index

    initial_structure_map = StructureMap(
        classifications={
            10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high"),
            11: ParagraphClassification(index=11, role="body", heading_level=None, confidence="high"),
            12: ParagraphClassification(index=12, role="body", heading_level=None, confidence="high"),
            13: ParagraphClassification(index=13, role="body", heading_level=None, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    targeted_structure_map = StructureMap(
        classifications={
            **initial_structure_map.classifications,
            10: ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=42,
        processing_time_seconds=0.1,
        window_count=1,
    )
    final_reconciled_map = StructureMap(
        classifications={
            **targeted_structure_map.classifications,
            12: ParagraphClassification(index=12, role="heading", heading_level=1, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=42,
        processing_time_seconds=0.1,
        window_count=1,
    )
    captured = {"reconcile_calls": 0, "targeted_calls": 0, "fallback_error": None}
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=DocumentMapTocRegion(
            start_logical_index=10,
            end_logical_index=11,
            header_logical_index=None,
            entries=(),
            confidence="medium",
        ),
        outline=(
            DocumentMapOutlineEntry(title="ГЛАВА 1", level=1, logical_index=10, confidence="high", evidence=("bold",)),
            DocumentMapOutlineEntry(title="ГЛАВА 2", level=1, logical_index=12, confidence="high", evidence=("bold",)),
        ),
        paragraph_anchors={
            10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high"),
            12: DocumentMapAnchor(role="heading", heading_level=1, confidence="high"),
        },
        review_zones=(
            DocumentMapReviewZone(
                start_logical_index=10,
                end_logical_index=11,
                reason="uncertain_body_start",
                severity="critical",
            ),
        ),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(10, 11, 12, 13),
    )

    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda paragraphs, *, client, model, max_window_paragraphs, overlap_paragraphs, timeout, document_map, preview_chars, target_input_tokens, progress_callback: initial_structure_map,
    )

    def _fake_reconcile(paragraphs, document_map, structure_map, topology_projection=None):
        captured["reconcile_calls"] += 1
        if captured["reconcile_calls"] == 1:
            assert structure_map is initial_structure_map
            return initial_structure_map, ReconciliationReport(
                missing_outline_entries=(10, 12),
                outline_coverage_ratio=0.0,
                patched_logical_indexes=(),
            )
        assert structure_map is targeted_structure_map
        return final_reconciled_map, ReconciliationReport(
            missing_outline_entries=(),
            unexpected_headings=(),
            toc_entries_without_body_match=(),
            front_matter_leaks=(),
            front_matter_body_advisories=(11,),
            outline_coverage_ratio=1.0,
            patched_logical_indexes=(10, 12),
        )

    monkeypatch.setattr(preparation, "reconcile_with_document_map", _fake_reconcile)
    monkeypatch.setattr(preparation, "get_model_role_value", lambda app_config, role: "gpt-4o-mini")
    monkeypatch.setattr(
        preparation,
        "targeted_reclassify_with_reconciliation_context",
        lambda paragraphs, document_map, structure_map, report, *, client, model, timeout, max_paragraphs: captured.__setitem__("targeted_calls", captured["targeted_calls"] + 1) or targeted_structure_map,
    )

    def _fake_write_reconciliation_report_artifact(*, cache_key, report, app_config):
        captured["report"] = report
        return ".run/reconciliation_reports/fake.json"

    def _fake_apply_structure_map(paragraphs, structure_map, *, min_confidence="medium", document_map=None):
        captured["applied_structure_map"] = structure_map
        return {"ai_classified": 2, "ai_headings": 2}

    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", _fake_write_reconciliation_report_artifact)
    monkeypatch.setattr(preparation, "apply_structure_map", _fake_apply_structure_map)
    monkeypatch.setattr(
        preparation,
        "log_event",
        lambda level, event, message, **context: captured.__setitem__("fallback_error", context.get("error_message"))
        if event == "structure_recognition_fallback"
        else None,
    )
    app_config = {
        "structure_recognition_model": "gpt-4o-mini",
        "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
        "structure_recognition_max_window_paragraphs": 1800,
        "structure_recognition_overlap_paragraphs": 50,
        "structure_recognition_timeout_seconds": 60,
        "structure_recognition_min_confidence": "medium",
        "structure_recognition_cache_enabled": False,
        "structure_recognition_save_debug_artifacts": False,
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
        "structure_recovery_anchored_classification_overlap_paragraphs": 0,
        "structure_recovery_anchored_classification_preview_chars": 1500,
        "structure_recovery_anchored_classification_target_input_tokens": 180000,
        "structure_recovery_anchored_classification_min_confidence": "high",
        "structure_recovery_reconciliation_targeted_enabled": True,
        "structure_recovery_reconciliation_targeted_threshold": 1,
        "structure_recovery_reconciliation_targeted_max_paragraphs": 10,
        "structure_recovery_reconciliation_targeted_timeout_seconds": 60,
    }

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config=app_config,
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=4, logical=4),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert captured["reconcile_calls"] == 2
    assert captured["targeted_calls"] == 1
    assert captured["fallback_error"] is None
    assert captured["applied_structure_map"] is final_reconciled_map
    assert captured["applied_structure_map"].classifications[12].role == "heading"
    assert captured["report"].patched_logical_indexes == (10, 12)
    assert captured["report"].front_matter_body_advisories == (11,)
    assert captured["report"].targeted_recall_invoked is True
    assert captured["report"].targeted_selected_logical_indexes == (10, 11, 12, 13)
    reason_map = {
        selection.logical_index: set(selection.reasons)
        for selection in captured["report"].targeted_selection_reasons
    }
    assert reason_map[10] == {"missing_outline_entry", "review_zone", "body_start_neighborhood", "toc_boundary_neighborhood"}
    assert "missing_outline_entry" in reason_map[12]
    assert result is final_reconciled_map
    assert summary.ai_heading_count == 2


def test_run_structure_recognition_preserves_first_reconcile_patch_indexes_after_targeted_recall(monkeypatch):
    paragraphs = [
        _build_paragraph(source_index=0, text="ГЛАВА 1"),
        _build_paragraph(source_index=1, text="Текст 1"),
        _build_paragraph(source_index=2, text="ГЛАВА 2"),
    ]
    for logical_index, paragraph in enumerate(paragraphs, start=10):
        paragraph.logical_index = logical_index

    initial_structure_map = StructureMap(
        classifications={
            10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high"),
            11: ParagraphClassification(index=11, role="body", heading_level=None, confidence="high"),
            12: ParagraphClassification(index=12, role="body", heading_level=None, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    targeted_structure_map = StructureMap(
        classifications={
            **initial_structure_map.classifications,
            11: ParagraphClassification(index=11, role="heading", heading_level=2, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=21,
        processing_time_seconds=0.1,
        window_count=1,
    )
    final_reconciled_map = StructureMap(
        classifications={
            **targeted_structure_map.classifications,
            12: ParagraphClassification(index=12, role="heading", heading_level=1, confidence="high"),
        },
        model_used="gpt-4o-mini",
        total_tokens_used=21,
        processing_time_seconds=0.1,
        window_count=1,
    )
    captured = {"reconcile_calls": 0}
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(
            DocumentMapOutlineEntry(title="ГЛАВА 1", level=1, logical_index=10, confidence="high", evidence=("bold",)),
            DocumentMapOutlineEntry(title="ГЛАВА 2", level=1, logical_index=12, confidence="high", evidence=("bold",)),
        ),
        paragraph_anchors={
            10: DocumentMapAnchor(role="heading", heading_level=1, confidence="high"),
            12: DocumentMapAnchor(role="heading", heading_level=1, confidence="high"),
        },
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(10, 11, 12),
    )

    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda *args, **kwargs: initial_structure_map,
    )

    def _fake_reconcile(paragraphs, document_map, structure_map, topology_projection=None):
        captured["reconcile_calls"] += 1
        if captured["reconcile_calls"] == 1:
            return initial_structure_map, ReconciliationReport(
                missing_outline_entries=(12,),
                outline_coverage_ratio=0.5,
                patched_logical_indexes=(10,),
            )
        return final_reconciled_map, ReconciliationReport(
            missing_outline_entries=(),
            unexpected_headings=(),
            toc_entries_without_body_match=(),
            front_matter_leaks=(),
            outline_coverage_ratio=1.0,
            patched_logical_indexes=(12,),
        )

    monkeypatch.setattr(preparation, "reconcile_with_document_map", _fake_reconcile)
    monkeypatch.setattr(preparation, "get_model_role_value", lambda app_config, role: "gpt-4o-mini")
    monkeypatch.setattr(
        preparation,
        "targeted_reclassify_with_reconciliation_context",
        lambda *args, **kwargs: targeted_structure_map,
    )
    monkeypatch.setattr(
        preparation,
        "_write_reconciliation_report_artifact",
        lambda *, cache_key, report, app_config: report,
    )
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: {"ai_classified": 2, "ai_headings": 2})

    captured_report = {}

    def _capture_artifact(*, cache_key, report, app_config):
        captured_report["report"] = report
        return ".run/reconciliation_reports/fake.json"

    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", _capture_artifact)

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "structure_recognition_model": "gpt-4o-mini",
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": True,
            "structure_recovery_reconciliation_targeted_threshold": -1,
            "structure_recovery_reconciliation_targeted_max_paragraphs": 10,
            "structure_recovery_reconciliation_targeted_timeout_seconds": 60,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=3, logical=3),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is final_reconciled_map
    assert summary.ai_heading_count == 2
    assert captured_report["report"].targeted_recall_invoked is True
    assert captured_report["report"].patched_logical_indexes == (10, 12)


def test_run_document_map_stage_uses_120_second_timeout_fallback(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
    captured = {}

    def _fake_build_document_map(
        paragraphs,
        *,
        client,
        model,
        timeout,
        max_input_paragraphs,
        max_input_tokens,
        preview_chars,
        progress_callback,
    ):
        captured["timeout"] = timeout
        return DocumentMap(
            body_start_logical_index=10,
            toc_region=None,
            outline=(),
            paragraph_anchors={10: DocumentMapAnchor(role="body", heading_level=None, confidence="low")},
            review_zones=(),
            model_used=model,
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(10,),
        )

    monkeypatch.setattr(preparation, "build_document_map", _fake_build_document_map)

    document_map = preparation._run_document_map_stage(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "structure_recovery_enabled": True,
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_max_input_paragraphs": 200,
            "structure_recovery_document_map_max_input_tokens": 180000,
            "structure_recovery_document_map_preview_chars": 120,
            "structure_recovery_document_map_cache_enabled": False,
            "structure_recovery_document_map_save_debug_artifacts": False,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
    )

    assert document_map is not None
    assert captured["timeout"] == 120.0


def test_run_document_map_stage_sets_ai_status_on_success(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
    fallback_state = {}

    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda paragraphs, **kwargs: DocumentMap(
            body_start_logical_index=10,
            toc_region=None,
            outline=(),
            paragraph_anchors={10: DocumentMapAnchor(role="body", heading_level=None, confidence="low")},
            review_zones=(),
            model_used="openrouter:test/document-map",
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(10,),
        ),
    )

    document_map = preparation._run_document_map_stage(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "structure_recovery_enabled": True,
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_cache_enabled": False,
            "structure_recovery_document_map_save_debug_artifacts": False,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        fallback_state=fallback_state,
    )

    assert document_map is not None
    assert fallback_state["document_map_status"] == "ai"
    assert fallback_state["document_map_status_reason"] == ""
    assert fallback_state["document_map_present"] is True


def test_run_document_map_stage_sets_cache_status_on_cache_hit(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
    fallback_state = {}
    cached_document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(),
        paragraph_anchors={10: DocumentMapAnchor(role="body", heading_level=None, confidence="low")},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(10,),
    )

    monkeypatch.setattr(preparation, "_read_cached_document_map", lambda cache_key: cached_document_map)
    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda *args, **kwargs: pytest.fail("builder should not run on document-map cache hit"),
    )

    document_map = preparation._run_document_map_stage(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "structure_recovery_enabled": True,
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_cache_enabled": True,
            "structure_recovery_document_map_save_debug_artifacts": False,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        fallback_state=fallback_state,
    )

    assert document_map == cached_document_map
    assert fallback_state["document_map_status"] == "cache"
    assert fallback_state["document_map_status_reason"] == ""
    assert fallback_state["document_map_present"] is True


def test_run_document_map_stage_sets_schema_failed_status(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    fallback_state = {}

    def _failing_build_document_map(paragraphs, **kwargs):
        raise DocumentMapSchemaError("schema-invalid output")

    monkeypatch.setattr(preparation, "build_document_map", _failing_build_document_map)

    document_map = preparation._run_document_map_stage(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "structure_recovery_enabled": True,
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_cache_enabled": False,
            "structure_recovery_document_map_save_debug_artifacts": False,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        fallback_state=fallback_state,
    )

    assert document_map is None
    assert fallback_state["document_map_status"] == "schema_failed"
    assert fallback_state["document_map_status_reason"] == "DocumentMapSchemaError: schema-invalid output"
    assert fallback_state["document_map_present"] is False


def test_run_document_map_stage_degrades_provider_runtime_failures(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    fallback_state = {}

    def _failing_build_document_map(
        paragraphs,
        *,
        client,
        model,
        timeout,
        max_input_paragraphs,
        max_input_tokens,
        preview_chars,
        progress_callback,
    ):
        raise RuntimeError("Unsupported document-map client")

    monkeypatch.setattr(preparation, "build_document_map", _failing_build_document_map)

    document_map = preparation._run_document_map_stage(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "structure_recovery_enabled": True,
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_cache_enabled": False,
            "structure_recovery_document_map_save_debug_artifacts": False,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        fallback_state=fallback_state,
    )

    assert document_map is None
    assert fallback_state["ai_first_degraded"] is True
    assert fallback_state["fallback_stage"] == "stage1_document_map_provider"
    assert fallback_state["document_map_status"] == "provider_failed"
    assert fallback_state["document_map_status_reason"] == "RuntimeError: Unsupported document-map client"
    assert fallback_state["document_map_present"] is False


def test_run_document_map_stage_uses_model_aware_client_factory_for_default_runtime(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    captured = {}

    monkeypatch.setattr(preparation, "_read_cached_document_map", lambda cache_key: None)
    monkeypatch.setattr(preparation, "_store_cached_document_map", lambda cache_key, document_map: None)
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: captured.setdefault(
            "client_request",
            (selector, required_capability, config_like),
        )
        or object(),
    )

    def _fake_build_document_map(paragraphs, **kwargs):
        captured["client"] = kwargs["client"]
        captured["model"] = kwargs["model"]
        return DocumentMap(
            body_start_logical_index=0,
            toc_region=None,
            outline=(),
            paragraph_anchors={0: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
            review_zones=(),
            model_used=kwargs["model"],
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(0,),
        )

    monkeypatch.setattr(preparation, "build_document_map", _fake_build_document_map)

    app_config = {
        "structure_recovery_enabled": True,
        "structure_recovery_document_map_enabled": True,
        "structure_recovery_document_map_model": "openrouter:test/document-map",
        "structure_recovery_document_map_cache_enabled": False,
        "structure_recovery_document_map_save_debug_artifacts": False,
        "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
    }

    document_map = preparation._run_document_map_stage(
        paragraphs=paragraphs,
        image_assets=[],
        app_config=app_config,
        get_client_fn=preparation.get_client,
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        fallback_state={},
    )

    assert document_map is not None
    assert captured["client_request"] == ("openrouter:test/document-map", "responses_text", app_config)
    assert captured["model"] == "openrouter:test/document-map"


def test_run_document_map_stage_uses_selector_aware_injected_client_factory(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    captured = {}
    document_map_client = object()

    def _selector_client_factory(selector, required_capability, *, config_like=None):
        captured["client_request"] = (selector, required_capability, config_like)
        return document_map_client

    def _fake_build_document_map(paragraphs, **kwargs):
        captured["client"] = kwargs["client"]
        captured["model"] = kwargs["model"]
        return DocumentMap(
            body_start_logical_index=0,
            toc_region=None,
            outline=(),
            paragraph_anchors={0: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
            review_zones=(),
            model_used=kwargs["model"],
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(0,),
        )

    monkeypatch.setattr(preparation, "build_document_map", _fake_build_document_map)
    app_config = {
        "structure_recovery_enabled": True,
        "structure_recovery_document_map_enabled": True,
        "structure_recovery_document_map_model": "openrouter:test/document-map",
        "structure_recovery_document_map_cache_enabled": False,
        "structure_recovery_document_map_save_debug_artifacts": False,
    }

    document_map = preparation._run_document_map_stage(
        paragraphs=paragraphs,
        image_assets=[],
        app_config=app_config,
        get_client_fn=_selector_client_factory,
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        fallback_state={},
    )

    assert document_map is not None
    assert captured["client_request"] == ("openrouter:test/document-map", "responses_text", app_config)
    assert captured["client"] is document_map_client
    assert captured["model"] == "openrouter:test/document-map"


def test_run_document_map_stage_keeps_internal_failures_fatal(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]

    def _failing_build_document_map(
        paragraphs,
        *,
        client,
        model,
        timeout,
        max_input_paragraphs,
        max_input_tokens,
        preview_chars,
        progress_callback,
    ):
        raise AssertionError("broken document-map invariant")

    monkeypatch.setattr(preparation, "build_document_map", _failing_build_document_map)

    with pytest.raises(AssertionError, match="broken document-map invariant"):
        preparation._run_document_map_stage(
            paragraphs=paragraphs,
            image_assets=[],
            app_config={
                "structure_recovery_enabled": True,
                "structure_recovery_document_map_enabled": True,
                "structure_recovery_document_map_model": "openrouter:test/document-map",
                "structure_recovery_document_map_cache_enabled": False,
                "structure_recovery_document_map_save_debug_artifacts": False,
            },
            get_client_fn=lambda: object(),
            progress_callback=None,
            normalization_report=_build_report(raw=1, logical=1),
            relation_report=None,
        )


def test_run_structure_recognition_uses_60_second_targeted_timeout_fallback(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
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
    captured = {}

    monkeypatch.setattr(preparation, "get_model_role_value", lambda app_config, role: "gpt-4o-mini")
    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (
            structure_map,
            ReconciliationReport(missing_outline_entries=(10, 11), outline_coverage_ratio=0.0),
        ),
    )

    def _fake_targeted(paragraphs, document_map, structure_map, report, *, client, model, timeout, max_paragraphs):
        captured["timeout"] = timeout
        return structure_map

    monkeypatch.setattr(preparation, "targeted_reclassify_with_reconciliation_context", _fake_targeted)
    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", lambda **kwargs: None)
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: {"ai_classified": 0, "ai_headings": 0})

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": True,
            "structure_recovery_reconciliation_targeted_threshold": 1,
            "structure_recovery_reconciliation_targeted_max_paragraphs": 10,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is structure_map
    assert summary.ai_heading_count == 0
    assert captured["timeout"] == 60.0


def test_run_structure_recognition_targeted_recall_uses_selector_aware_injected_client_factory(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
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
        model_used="openrouter:test/structure",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    captured = {}
    targeted_client = object()

    def _selector_client_factory(selector, required_capability, *, config_like=None):
        captured["client_request"] = (selector, required_capability, config_like)
        return targeted_client

    def _fake_targeted(paragraphs, document_map, structure_map, report, *, client, model, timeout, max_paragraphs):
        captured["targeted_client"] = client
        captured["targeted_model"] = model
        return structure_map

    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (
            structure_map,
            ReconciliationReport(missing_outline_entries=(10, 11), outline_coverage_ratio=0.0),
        ),
    )
    monkeypatch.setattr(preparation, "targeted_reclassify_with_reconciliation_context", _fake_targeted)
    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", lambda **kwargs: None)
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: {"ai_classified": 0, "ai_headings": 0})

    app_config = {
        "models": _build_runtime_model_registry(structure_recognition_model="openrouter:test/structure"),
        "structure_recognition_cache_enabled": False,
        "structure_recognition_save_debug_artifacts": False,
        "structure_recognition_timeout_seconds": 60,
        "structure_recognition_min_confidence": "medium",
        "structure_recovery_enabled": True,
        "structure_recovery_mode": "ai_first",
        "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
        "structure_recovery_anchored_classification_overlap_paragraphs": 0,
        "structure_recovery_anchored_classification_preview_chars": 1500,
        "structure_recovery_anchored_classification_target_input_tokens": 180000,
        "structure_recovery_anchored_classification_min_confidence": "high",
        "structure_recovery_reconciliation_targeted_enabled": True,
        "structure_recovery_reconciliation_targeted_threshold": 1,
        "structure_recovery_reconciliation_targeted_max_paragraphs": 10,
    }

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config=app_config,
        get_client_fn=_selector_client_factory,
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is structure_map
    assert summary.ai_heading_count == 0
    assert captured["client_request"] == ("openrouter:test/structure", "responses_text", app_config)
    assert captured["targeted_client"] is targeted_client
    assert captured["targeted_model"] == "openrouter:test/structure"


def test_run_structure_recognition_degrades_targeted_recall_provider_failures_as_stage3_reconciliation_provider(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
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

    monkeypatch.setattr(preparation, "get_model_role_value", lambda app_config, role: "gpt-4o-mini")
    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (
            structure_map,
            ReconciliationReport(missing_outline_entries=(10, 11), outline_coverage_ratio=0.0),
        ),
    )
    monkeypatch.setattr(
        preparation,
        "targeted_reclassify_with_reconciliation_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("targeted recall timed out")),
    )
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: pytest.fail("apply should not run"))

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": True,
            "structure_recovery_reconciliation_targeted_threshold": 1,
            "structure_recovery_reconciliation_targeted_max_paragraphs": 10,
            "structure_recovery_reconciliation_targeted_timeout_seconds": 60,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is None
    assert summary.ai_first_degraded is True
    assert summary.fallback_stage == "stage3_reconciliation_provider"


def test_run_structure_recognition_triggers_targeted_recall_on_anchor_disagreements(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
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
        sampled_logical_indexes=(10,),
    )
    structure_map = StructureMap(
        classifications={10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    captured: dict[str, Any] = {"events": []}

    monkeypatch.setattr(preparation, "get_model_role_value", lambda app_config, role: "gpt-4o-mini")
    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (
            structure_map,
            ReconciliationReport(anchor_disagreements_seen=(10, 11, 12, 13), outline_coverage_ratio=1.0),
        ),
    )

    def _fake_targeted(paragraphs, document_map, structure_map, report, *, client, model, timeout, max_paragraphs):
        captured["report"] = report
        return structure_map

    monkeypatch.setattr(preparation, "targeted_reclassify_with_reconciliation_context", _fake_targeted)
    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", lambda **kwargs: None)
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: {"ai_classified": 0, "ai_headings": 0})
    monkeypatch.setattr(
        preparation,
        "log_event",
        lambda level, event, message, **context: captured["events"].append((event, context)),
    )

    preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": True,
            "structure_recovery_reconciliation_targeted_threshold": 3,
            "structure_recovery_reconciliation_targeted_max_paragraphs": 10,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    report = cast(ReconciliationReport, captured["report"])
    assert report.anchor_disagreements_seen == (10, 11, 12, 13)
    reconciliation_saved_context = next(context for event, context in captured["events"] if event == "reconciliation_report_saved")
    assert reconciliation_saved_context["anchor_disagreements_seen"] == [10, 11, 12, 13]
    assert reconciliation_saved_context["patched_logical_indexes"] == []
    assert "anchor_conflicts" not in reconciliation_saved_context
    assert "patched_source_indexes" not in reconciliation_saved_context


def test_run_structure_recognition_does_not_trigger_targeted_recall_for_front_matter_advisories_only(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="Посвящение")]
    paragraphs[0].logical_index = 10
    document_map = DocumentMap(
        body_start_logical_index=10,
        toc_region=None,
        outline=(),
        paragraph_anchors={10: DocumentMapAnchor(role="body", heading_level=None, confidence="high")},
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

    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (
            structure_map,
            ReconciliationReport(front_matter_body_advisories=(10,), outline_coverage_ratio=1.0),
        ),
    )
    monkeypatch.setattr(
        preparation,
        "targeted_reclassify_with_reconciliation_context",
        lambda *args, **kwargs: pytest.fail("targeted recall should not run for advisory-only divergence"),
    )
    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", lambda **kwargs: None)
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: {"ai_classified": 0, "ai_headings": 0})

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": True,
            "structure_recovery_reconciliation_targeted_threshold": 0,
            "structure_recovery_reconciliation_targeted_max_paragraphs": 10,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is structure_map
    assert summary.ai_first_degraded is False


def test_run_structure_recognition_triggers_targeted_recall_from_review_zone_context_below_divergence_threshold(monkeypatch):
    paragraphs = [_build_paragraph(source_index=index, text=f"P{index}") for index in range(4)]
    for logical_index, paragraph in enumerate(paragraphs, start=10):
        paragraph.logical_index = logical_index
    document_map = DocumentMap(
        body_start_logical_index=100,
        toc_region=None,
        outline=(),
        paragraph_anchors={},
        review_zones=(
            DocumentMapReviewZone(
                start_logical_index=10,
                end_logical_index=11,
                reason="uncertain_body_start",
                severity="critical",
            ),
        ),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(10, 11, 12, 13),
    )
    structure_map = StructureMap(
        classifications={10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    captured: dict[str, Any] = {"targeted_calls": 0}

    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(preparation, "get_model_role_value", lambda app_config, role: "gpt-4o-mini")
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (
            structure_map,
            ReconciliationReport(missing_outline_entries=(10,), outline_coverage_ratio=0.0),
        ),
    )

    def _fake_targeted(paragraphs, document_map, structure_map, report, *, client, model, timeout, max_paragraphs, selection=None):
        captured["targeted_calls"] = int(captured["targeted_calls"]) + 1
        captured["selection"] = selection
        return structure_map

    monkeypatch.setattr(preparation, "targeted_reclassify_with_reconciliation_context", _fake_targeted)
    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", lambda **kwargs: None)
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: {"ai_classified": 0, "ai_headings": 0})

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": True,
            "structure_recovery_reconciliation_targeted_threshold": 10,
            "structure_recovery_reconciliation_targeted_max_paragraphs": 4,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=4, logical=4),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is structure_map
    assert summary.ai_first_degraded is False
    assert captured["targeted_calls"] == 1
    selection = captured.get("selection")
    assert selection is not None
    assert cast(Any, selection).logical_indexes == (10, 11, 12, 13)


def test_run_structure_recognition_triggers_targeted_recall_from_body_start_context_alone(monkeypatch):
    paragraphs = [_build_paragraph(source_index=index, text=f"P{index}") for index in range(5)]
    for logical_index, paragraph in enumerate(paragraphs, start=8):
        paragraph.logical_index = logical_index
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
        sampled_logical_indexes=(8, 9, 10, 11, 12),
    )
    structure_map = StructureMap(
        classifications={10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    captured: dict[str, Any] = {"targeted_calls": 0}

    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(preparation, "get_model_role_value", lambda app_config, role: "gpt-4o-mini")
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (structure_map, ReconciliationReport(outline_coverage_ratio=1.0)),
    )

    def _fake_targeted(paragraphs, document_map, structure_map, report, *, client, model, timeout, max_paragraphs, selection=None):
        captured["targeted_calls"] = int(captured["targeted_calls"]) + 1
        captured["selection"] = selection
        return structure_map

    monkeypatch.setattr(preparation, "targeted_reclassify_with_reconciliation_context", _fake_targeted)
    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", lambda **kwargs: None)
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: {"ai_classified": 0, "ai_headings": 0})

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": True,
            "structure_recovery_reconciliation_targeted_threshold": 10,
            "structure_recovery_reconciliation_targeted_max_paragraphs": 10,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=5, logical=5),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is structure_map
    assert summary.ai_first_degraded is False
    assert captured["targeted_calls"] == 1
    selection = captured.get("selection")
    assert selection is not None
    assert cast(Any, selection).logical_indexes == (8, 9, 10, 11, 12)


def test_run_structure_recognition_triggers_targeted_recall_from_toc_boundary_context_alone(monkeypatch):
    paragraphs = [_build_paragraph(source_index=index, text=f"P{index}") for index in range(7)]
    for logical_index, paragraph in enumerate(paragraphs, start=8):
        paragraph.logical_index = logical_index
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
        sampled_logical_indexes=(8, 9, 10, 11, 12, 13, 14),
    )
    structure_map = StructureMap(
        classifications={10: ParagraphClassification(index=10, role="body", heading_level=None, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    captured: dict[str, Any] = {"targeted_calls": 0}

    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(preparation, "get_model_role_value", lambda app_config, role: "gpt-4o-mini")
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (structure_map, ReconciliationReport(outline_coverage_ratio=1.0)),
    )

    def _fake_targeted(paragraphs, document_map, structure_map, report, *, client, model, timeout, max_paragraphs, selection=None):
        captured["targeted_calls"] = int(captured["targeted_calls"]) + 1
        captured["selection"] = selection
        return structure_map

    monkeypatch.setattr(preparation, "targeted_reclassify_with_reconciliation_context", _fake_targeted)
    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", lambda **kwargs: None)
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: {"ai_classified": 0, "ai_headings": 0})

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": True,
            "structure_recovery_reconciliation_targeted_threshold": 10,
            "structure_recovery_reconciliation_targeted_max_paragraphs": 10,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=7, logical=7),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is structure_map
    assert summary.ai_first_degraded is False
    assert captured["targeted_calls"] == 1
    selection = captured.get("selection")
    assert selection is not None
    assert cast(Any, selection).logical_indexes == (8, 9, 10, 11, 12, 13, 14)


def test_run_structure_recognition_keeps_reconciliation_invariant_failures_fatal(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
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

    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("broken reconciliation")),
    )

    with pytest.raises(ValueError, match="broken reconciliation"):
        preparation._run_structure_recognition(
            paragraphs=paragraphs,
            image_assets=[],
            app_config={
                "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
                "structure_recognition_cache_enabled": False,
                "structure_recognition_save_debug_artifacts": False,
                "structure_recognition_timeout_seconds": 60,
                "structure_recognition_min_confidence": "medium",
                "structure_recovery_enabled": True,
                "structure_recovery_mode": "ai_first",
                "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
                "structure_recovery_anchored_classification_overlap_paragraphs": 0,
                "structure_recovery_anchored_classification_preview_chars": 1500,
                "structure_recovery_anchored_classification_target_input_tokens": 180000,
                "structure_recovery_anchored_classification_min_confidence": "high",
                "structure_recovery_reconciliation_targeted_enabled": False,
            },
            get_client_fn=lambda: object(),
            progress_callback=None,
            normalization_report=_build_report(raw=1, logical=1),
            relation_report=None,
            cleanup_report=None,
            document_map=document_map,
        )


def test_run_structure_recognition_keeps_stage2_internal_failures_fatal(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10

    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("broken internal prep")))

    with pytest.raises(AssertionError, match="broken internal prep"):
        preparation._run_structure_recognition(
            paragraphs=paragraphs,
            image_assets=[],
            app_config={
                "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
                "structure_recognition_cache_enabled": False,
                "structure_recognition_save_debug_artifacts": False,
                "structure_recognition_timeout_seconds": 60,
                "structure_recognition_min_confidence": "medium",
                "structure_recovery_enabled": True,
                "structure_recovery_mode": "ai_first",
                "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
                "structure_recovery_anchored_classification_overlap_paragraphs": 0,
                "structure_recovery_anchored_classification_preview_chars": 1500,
                "structure_recovery_anchored_classification_target_input_tokens": 180000,
                "structure_recovery_anchored_classification_min_confidence": "high",
            },
            get_client_fn=lambda: object(),
            progress_callback=None,
            normalization_report=_build_report(raw=1, logical=1),
            relation_report=None,
            cleanup_report=None,
            document_map=None,
        )


def test_run_structure_recognition_degrades_apply_failures_as_stage3_apply(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
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
        classifications={10: ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (structure_map, ReconciliationReport(outline_coverage_ratio=1.0)),
    )
    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", lambda **kwargs: None)
    monkeypatch.setattr(
        preparation,
        "apply_structure_map",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("apply failed")),
    )

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": False,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is None
    assert summary.ai_first_degraded is True
    assert summary.fallback_stage == "stage3_apply"


def test_run_structure_recognition_restores_paragraphs_after_partial_apply_failure(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
    paragraphs[0].role = "body"
    paragraphs[0].structural_role = "body"
    paragraphs[0].role_confidence = "heuristic"
    paragraphs[0].heading_source = None
    paragraphs[0].heading_level = None
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
        classifications={10: ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )

    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (structure_map, ReconciliationReport(outline_coverage_ratio=1.0)),
    )
    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", lambda **kwargs: None)

    def _partial_apply(*args, **kwargs):
        paragraphs[0].role = "heading"
        paragraphs[0].structural_role = "heading"
        paragraphs[0].role_confidence = "ai"
        paragraphs[0].heading_source = "ai"
        paragraphs[0].heading_level = 1
        raise RuntimeError("apply failed after mutation")

    monkeypatch.setattr(preparation, "apply_structure_map", _partial_apply)

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": False,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is None
    assert summary.fallback_stage == "stage3_apply"
    assert paragraphs[0].role == "body"
    assert paragraphs[0].structural_role == "body"
    assert paragraphs[0].role_confidence == "heuristic"
    assert paragraphs[0].heading_source is None
    assert paragraphs[0].heading_level is None


def test_run_structure_recognition_keeps_structure_when_reconciliation_report_save_fails(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
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
        classifications={10: ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high")},
        model_used="gpt-4o-mini",
        total_tokens_used=12,
        processing_time_seconds=0.1,
        window_count=1,
    )
    logged_events = []

    monkeypatch.setattr(preparation, "build_structure_map", lambda *args, **kwargs: structure_map)
    monkeypatch.setattr(
        preparation,
        "reconcile_with_document_map",
        lambda paragraphs, document_map, structure_map: (structure_map, ReconciliationReport(outline_coverage_ratio=1.0)),
    )
    monkeypatch.setattr(
        preparation,
        "_write_reconciliation_report_artifact",
        lambda **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: {"ai_classified": 1, "ai_headings": 1})
    monkeypatch.setattr(preparation, "log_event", lambda level, event, message, **context: logged_events.append((event, context)))

    result, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config={
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_anchored_classification_max_window_paragraphs": 3000,
            "structure_recovery_anchored_classification_overlap_paragraphs": 0,
            "structure_recovery_anchored_classification_preview_chars": 1500,
            "structure_recovery_anchored_classification_target_input_tokens": 180000,
            "structure_recovery_anchored_classification_min_confidence": "high",
            "structure_recovery_reconciliation_targeted_enabled": False,
        },
        get_client_fn=lambda: object(),
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        cleanup_report=None,
        document_map=document_map,
    )

    assert result is structure_map
    assert summary.ai_first_degraded is False
    assert any(event == "reconciliation_report_save_failed" for event, _context in logged_events)
    assert all(event != "structure_recognition_fallback" for event, _context in logged_events)


def test_prepare_document_for_processing_falls_back_to_legacy_non_anchored_stage2_when_document_map_stage_fails(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1"), _build_paragraph(source_index=1, text="Основной текст")]
    paragraphs[0].logical_index = 10
    paragraphs[1].logical_index = 11
    captured = {}

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())

    def _failing_build_document_map(
        paragraphs,
        *,
        client,
        model,
        timeout,
        max_input_paragraphs,
        max_input_tokens,
        preview_chars,
        progress_callback,
    ):
        raise DocumentMapRequestTimeout("document-map provider timed out")

    monkeypatch.setattr(preparation, "build_document_map", _failing_build_document_map)

    def _fake_build_structure_map(
        paragraphs,
        *,
        client,
        model,
        max_window_paragraphs,
        overlap_paragraphs,
        timeout,
        document_map,
        preview_chars,
        target_input_tokens,
        progress_callback,
    ):
        captured["document_map"] = document_map
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

    assert captured == {
        "document_map": None,
        "max_window_paragraphs": 1800,
        "overlap_paragraphs": 50,
        "preview_chars": 600,
        "target_input_tokens": None,
    }
    assert result.document_map is None


def test_prepare_document_for_processing_skips_document_map_when_structure_mode_off(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1"), _build_paragraph(source_index=1, text="Основной текст")]
    captured = {}

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
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

    assert "call" not in captured
    assert result.document_map is None
    assert [event["stage"] for event in events] == [
        "Разбор DOCX",
        "Структура извлечена",
        "Текст собран",
        "Смысловые блоки",
        "Задания собраны",
    ]


@pytest.mark.parametrize(
    ("summary", "expected_phase"),
    [
        (StructureRecognitionSummary(ai_classified_count=1, ai_heading_count=1), "post_ai_final"),
        (
            StructureRecognitionSummary(
                ai_first_degraded=True,
                fallback_stage="stage2_structure_recognition_provider",
                fallback_reason="TimeoutError: timed out",
            ),
            "ai_first_degraded_fallback",
        ),
    ],
)
def test_prepare_document_for_processing_rebuilds_downstream_relations_and_jobs_with_final_structure_phase(
    monkeypatch,
    summary,
    expected_phase,
):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        _build_paragraph(source_index=0, text="Содержание"),
        _build_paragraph(source_index=1, text="Глава 1........ 12"),
        _build_paragraph(source_index=2, text="Первый обычный абзац."),
    ]
    captured = {}
    diagnostic_relations = [
        ParagraphRelation(
            relation_id="rel-diagnostic",
            relation_kind="toc_region_candidate",
            member_paragraph_ids=("p0000", "p0001"),
        )
    ]
    diagnostic_report = RelationNormalizationReport(
        total_relations=1,
        relation_counts={"toc_region_candidate": 1},
        rejected_candidate_count=0,
        decisions=[
            ParagraphRelationDecision(
                relation_kind="toc_region_candidate",
                decision="accept",
                member_paragraph_ids=("p0000", "p0001"),
                structure_phase="pre_ai_diagnostic",
                structure_source="pre_ai_diagnostic_hint",
            )
        ],
    )

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(
            paragraphs,
            [],
            _build_report(raw=3, logical=3),
            relations=diagnostic_relations,
            relation_report=diagnostic_report,
        ),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(preparation, "_run_document_map_stage", lambda **kwargs: None)
    monkeypatch.setattr(
        preparation,
        "_run_structure_recognition",
        lambda **kwargs: (
            StructureMap(
                classifications={0: ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")},
                model_used="gpt-4o-mini",
                total_tokens_used=12,
                processing_time_seconds=0.1,
                window_count=1,
            )
            if not summary.ai_first_degraded
            else None,
            summary,
        ),
    )
    monkeypatch.setattr(preparation, "_run_structure_validation", lambda **kwargs: None)
    monkeypatch.setattr(
        preparation,
        "build_paragraph_relations",
        lambda paragraphs, *, enabled_relation_kinds, structure_phase: (
            captured.setdefault("relation_phases", []).append(structure_phase),
            captured.setdefault("relation_kinds", []).append(tuple(enabled_relation_kinds)),
            (
                [
                    ParagraphRelation(
                        relation_id="rel-final",
                        relation_kind="toc_region",
                        member_paragraph_ids=("p0000", "p0001"),
                    )
                ],
                RelationNormalizationReport(
                    total_relations=1,
                    relation_counts={"toc_region": 1},
                    rejected_candidate_count=0,
                    decisions=[
                        ParagraphRelationDecision(
                            relation_kind="toc_region",
                            decision="accept",
                            member_paragraph_ids=("p0000", "p0001"),
                            structure_phase=structure_phase,
                            structure_source=(
                                "ai_first_degraded_fallback"
                                if structure_phase == "ai_first_degraded_fallback"
                                else "post_ai_final_binding"
                            ),
                        )
                    ],
                ),
            ),
        )[-1],
    )

    def _fake_build_semantic_blocks(paragraphs, max_chars, relations=None, structure_phase="post_ai_final"):
        captured["block_phase"] = structure_phase
        captured["block_relations"] = relations
        return [DocumentBlock(paragraphs=list(paragraphs))]

    def _fake_build_editing_jobs(blocks, max_chars, processing_operation="edit", structure_phase="post_ai_final"):
        captured["job_phase"] = structure_phase
        return [{"target_text": "joined", "target_chars": 6, "context_chars": 0, "structure_phase": structure_phase}]

    monkeypatch.setattr(preparation, "build_semantic_blocks", _fake_build_semantic_blocks)
    monkeypatch.setattr(preparation, "build_editing_jobs", _fake_build_editing_jobs)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "\n\n".join(paragraph.text for paragraph in paragraphs))
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
            "relation_normalization_enabled_relation_kinds": ("toc_region",),
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

    assert captured["relation_phases"] == [expected_phase]
    assert captured["relation_kinds"] == [("toc_region",)]
    assert captured["block_phase"] == expected_phase
    assert captured["block_relations"] == result.relations
    assert captured["job_phase"] == expected_phase
    assert result.relations[0].relation_id == "rel-final"
    assert result.relations[0].relation_kind == "toc_region"
    assert result.relation_report is not None
    assert result.relation_report.decisions[0].structure_phase == expected_phase
    assert result.relation_report.decisions[0].relation_kind == "toc_region"


def test_prepare_document_for_processing_projects_final_toc_relation_from_document_map(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        _build_paragraph(source_index=0, text="Contents"),
        _build_paragraph(source_index=1, text="Chapter 1........ 12"),
        _build_paragraph(source_index=2, text="Chapter 2........ 18"),
        _build_paragraph(source_index=3, text="Первый обычный абзац."),
    ]
    captured = {}
    diagnostic_relations = [
        ParagraphRelation(
            relation_id="rel-diagnostic",
            relation_kind="toc_region_candidate",
            member_paragraph_ids=("p0000", "p0001", "p0002"),
        )
    ]
    diagnostic_report = RelationNormalizationReport(
        total_relations=1,
        relation_counts={"toc_region_candidate": 1},
        rejected_candidate_count=0,
        decisions=[
            ParagraphRelationDecision(
                relation_kind="toc_region_candidate",
                decision="accept",
                member_paragraph_ids=("p0000", "p0001", "p0002"),
                structure_phase="pre_ai_diagnostic",
                structure_source="pre_ai_diagnostic_hint",
            )
        ],
    )
    document_map = DocumentMap(
        body_start_logical_index=3,
        toc_region=DocumentMapTocRegion(
            start_logical_index=1,
            end_logical_index=2,
            header_logical_index=0,
            entries=(),
            confidence="high",
        ),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        model_used="openrouter:test/document-map",
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=False,
        sampled_logical_indexes=(0, 1, 2, 3),
    )

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(
            paragraphs,
            [],
            _build_report(raw=4, logical=4),
            relations=diagnostic_relations,
            relation_report=diagnostic_report,
        ),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(preparation, "_run_document_map_stage", lambda **kwargs: document_map)
    monkeypatch.setattr(
        preparation,
        "_run_structure_recognition",
        lambda **kwargs: (
            StructureMap(
                classifications={},
                model_used="gpt-4o-mini",
                total_tokens_used=12,
                processing_time_seconds=0.1,
                window_count=1,
            ),
            StructureRecognitionSummary(ai_classified_count=1),
        ),
    )
    monkeypatch.setattr(preparation, "_run_structure_validation", lambda **kwargs: None)

    def _fake_build_semantic_blocks(paragraphs, max_chars, relations=None, structure_phase="post_ai_final"):
        captured["block_phase"] = structure_phase
        captured["block_relations"] = relations
        return [DocumentBlock(paragraphs=list(paragraphs))]

    monkeypatch.setattr(preparation, "build_semantic_blocks", _fake_build_semantic_blocks)
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars, processing_operation="edit", structure_phase="post_ai_final": [{"target_text": "joined", "target_chars": 6, "context_chars": 0, "structure_phase": structure_phase}])
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "\n\n".join(paragraph.text for paragraph in paragraphs))
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: _make_ai_first_config(relation_kinds=("toc_region",)),
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert [relation.relation_kind for relation in result.relations] == ["toc_region"]
    assert result.relations[0].member_paragraph_ids == ("p0000", "p0001", "p0002")
    assert result.relation_report is not None
    assert result.relation_report.decisions[0].structure_phase == "post_ai_final"
    assert result.relation_report.decisions[0].structure_source == "post_ai_final_document_map"
    assert captured["block_phase"] == "post_ai_final"
    assert [relation.relation_kind for relation in captured["block_relations"]] == ["toc_region"]


def test_prepare_document_for_processing_compact_ai_first_integration_uses_post_ai_authority_downstream(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        _build_paragraph(source_index=0, text="Preface"),
        _build_paragraph(source_index=1, text="Contents"),
        _build_paragraph(source_index=2, text="Chapter 1........ 12"),
        _build_paragraph(source_index=3, text="CHAPTER 1"),
        _build_paragraph(source_index=4, text="First body paragraph."),
    ]
    for logical_index, paragraph in enumerate(paragraphs):
        paragraph.logical_index = logical_index

    captured: dict[str, Any] = {}
    diagnostic_relations = [
        ParagraphRelation(
            relation_id="rel-diagnostic",
            relation_kind="toc_region_candidate",
            member_paragraph_ids=("p0001", "p0002"),
        )
    ]
    diagnostic_report = RelationNormalizationReport(
        total_relations=1,
        relation_counts={"toc_region_candidate": 1},
        rejected_candidate_count=0,
        decisions=[
            ParagraphRelationDecision(
                relation_kind="toc_region_candidate",
                decision="accept",
                member_paragraph_ids=("p0001", "p0002"),
                structure_phase="pre_ai_diagnostic",
                structure_source="pre_ai_diagnostic_hint",
            )
        ],
    )

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(
            paragraphs,
            [],
            _build_report(raw=5, logical=5),
            relations=diagnostic_relations,
            relation_report=diagnostic_report,
        ),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
    )
    monkeypatch.setattr(preparation, "get_model_role_value", lambda app_config, role: "gpt-4o-mini")
    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda paragraphs, *, client, model, timeout, max_input_paragraphs, max_input_tokens, preview_chars, progress_callback: DocumentMap(
            body_start_logical_index=3,
            toc_region=DocumentMapTocRegion(
                start_logical_index=1,
                end_logical_index=2,
                header_logical_index=1,
                entries=(),
                confidence="high",
            ),
            outline=(
                DocumentMapOutlineEntry(
                    title="CHAPTER 1",
                    level=1,
                    logical_index=3,
                    confidence="high",
                    evidence=("toc_match",),
                ),
            ),
            paragraph_anchors={3: DocumentMapAnchor(role="heading", heading_level=1, confidence="high")},
            review_zones=(),
            model_used=model,
            total_tokens_used=0,
            processing_time_seconds=0.0,
            sampled=False,
            sampled_logical_indexes=(0, 1, 2, 3, 4),
        ),
    )
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda paragraphs, *, client, model, max_window_paragraphs, overlap_paragraphs, timeout, document_map, preview_chars, target_input_tokens, progress_callback: StructureMap(
            classifications={
                3: ParagraphClassification(index=3, role="body", heading_level=None, confidence="high"),
                4: ParagraphClassification(index=4, role="body", heading_level=None, confidence="high"),
            },
            model_used=model,
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    monkeypatch.setattr(preparation, "_write_reconciliation_report_artifact", lambda **kwargs: None)
    monkeypatch.setattr(preparation, "_run_structure_validation", lambda **kwargs: None)

    def _fake_build_paragraph_relations(paragraphs, *, enabled_relation_kinds, structure_phase):
        captured["relation_phase"] = structure_phase
        captured["enabled_relation_kinds"] = tuple(enabled_relation_kinds)
        captured["heading_role"] = paragraphs[3].role
        captured["heading_level"] = paragraphs[3].heading_level
        return (
            [
                ParagraphRelation(
                    relation_id="rel-final",
                    relation_kind="toc_region",
                    member_paragraph_ids=("p0001", "p0002"),
                )
            ],
            RelationNormalizationReport(
                total_relations=1,
                relation_counts={"toc_region": 1},
                rejected_candidate_count=0,
                decisions=[
                    ParagraphRelationDecision(
                        relation_kind="toc_region",
                        decision="accept",
                        member_paragraph_ids=("p0001", "p0002"),
                        structure_phase=structure_phase,
                        structure_source="post_ai_final_document_map",
                    )
                ],
            ),
        )

    def _fake_build_semantic_blocks(paragraphs, max_chars, relations=None, hard_boundary_paragraph_ids=None, structure_phase="post_ai_final"):
        captured["block_phase"] = structure_phase
        captured["block_relations"] = relations
        captured["block_heading_role"] = paragraphs[3].role
        return [DocumentBlock(paragraphs=list(paragraphs))]

    def _fake_build_editing_jobs(blocks, max_chars, processing_operation="edit", structure_phase="post_ai_final"):
        captured["job_phase"] = structure_phase
        return [{"target_text": "chapter block", "target_chars": 13, "context_chars": 0, "structure_phase": structure_phase}]

    monkeypatch.setattr(preparation, "build_paragraph_relations", _fake_build_paragraph_relations)
    monkeypatch.setattr(preparation, "build_semantic_blocks", _fake_build_semantic_blocks)
    monkeypatch.setattr(preparation, "build_editing_jobs", _fake_build_editing_jobs)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "\n\n".join(paragraph.text for paragraph in paragraphs))
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: _make_ai_first_config(
            relation_kinds=("toc_region",),
            structure_recovery_reconciliation_targeted_enabled=False,
        ),
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.document_map is not None
    assert result.structure_map is not None
    assert result.structure_map.classifications[3].role == "heading"
    assert result.structure_map.classifications[3].heading_level == 1
    assert result.paragraphs[3].role == "heading"
    assert result.paragraphs[3].heading_level == 1
    assert captured["relation_phase"] == "post_ai_final"
    assert captured["enabled_relation_kinds"] == ("toc_region",)
    assert captured["heading_role"] == "heading"
    assert captured["heading_level"] == 1
    assert captured["block_phase"] == "post_ai_final"
    assert captured["block_heading_role"] == "heading"
    assert captured["job_phase"] == "post_ai_final"
    assert [relation.relation_kind for relation in result.relations] == ["toc_region"]
    assert result.relation_report is not None
    assert result.relation_report.decisions[0].structure_phase == "post_ai_final"
    assert result.relation_report.decisions[0].structure_source == "post_ai_final_document_map"
    assert captured["block_relations"] == result.relations


def test_prepare_document_for_processing_does_not_promote_diagnostic_toc_candidate_without_final_authority(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        _build_paragraph(source_index=0, text="Contents"),
        _build_paragraph(source_index=1, text="Chapter 1........ 12"),
        _build_paragraph(source_index=2, text="Chapter 2........ 18"),
        _build_paragraph(source_index=3, text="Первый обычный абзац."),
    ]
    captured = {}
    diagnostic_relations = [
        ParagraphRelation(
            relation_id="rel-diagnostic",
            relation_kind="toc_region_candidate",
            member_paragraph_ids=("p0000", "p0001", "p0002"),
        )
    ]
    diagnostic_report = RelationNormalizationReport(
        total_relations=1,
        relation_counts={"toc_region_candidate": 1},
        rejected_candidate_count=0,
        decisions=[
            ParagraphRelationDecision(
                relation_kind="toc_region_candidate",
                decision="accept",
                member_paragraph_ids=("p0000", "p0001", "p0002"),
                structure_phase="pre_ai_diagnostic",
                structure_source="pre_ai_diagnostic_hint",
            )
        ],
    )

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(
            paragraphs,
            [],
            _build_report(raw=4, logical=4),
            relations=diagnostic_relations,
            relation_report=diagnostic_report,
        ),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(preparation, "_run_document_map_stage", lambda **kwargs: None)
    monkeypatch.setattr(
        preparation,
        "_run_structure_recognition",
        lambda **kwargs: (
            StructureMap(
                classifications={},
                model_used="gpt-4o-mini",
                total_tokens_used=12,
                processing_time_seconds=0.1,
                window_count=1,
            ),
            StructureRecognitionSummary(ai_classified_count=1),
        ),
    )
    monkeypatch.setattr(preparation, "_run_structure_validation", lambda **kwargs: None)

    def _fake_build_semantic_blocks(paragraphs, max_chars, relations=None, structure_phase="post_ai_final"):
        captured["block_phase"] = structure_phase
        captured["block_relations"] = relations
        return [DocumentBlock(paragraphs=list(paragraphs))]

    monkeypatch.setattr(preparation, "build_semantic_blocks", _fake_build_semantic_blocks)
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars, processing_operation="edit", structure_phase="post_ai_final": [{"target_text": "joined", "target_chars": 6, "context_chars": 0, "structure_phase": structure_phase}])
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "\n\n".join(paragraph.text for paragraph in paragraphs))
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: _make_ai_first_config(relation_kinds=("toc_region",)),
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.relations == []
    assert result.relation_report is not None
    assert result.relation_report.total_relations == 0
    assert result.relation_report.relation_counts == {}
    assert captured["block_phase"] == "post_ai_final"
    assert captured["block_relations"] == []


def test_prepare_document_for_processing_uses_empty_relation_kinds_for_post_ai_rebuild_when_relation_normalization_disabled(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        _build_paragraph(source_index=0, text="Содержание"),
        _build_paragraph(source_index=1, text="Глава 1........ 12"),
        _build_paragraph(source_index=2, text="Первый обычный абзац."),
    ]
    captured = {}
    diagnostic_relations = [
        ParagraphRelation(
            relation_id="rel-diagnostic",
            relation_kind="toc_region_candidate",
            member_paragraph_ids=("p0000", "p0001"),
        )
    ]

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(
            paragraphs,
            [],
            _build_report(raw=3, logical=3),
            relations=diagnostic_relations,
            relation_report=RelationNormalizationReport(total_relations=1, relation_counts={"toc_region": 1}, rejected_candidate_count=0, decisions=[]),
        ),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(preparation, "_run_document_map_stage", lambda **kwargs: None)
    monkeypatch.setattr(
        preparation,
        "_run_structure_recognition",
        lambda **kwargs: (
            StructureMap(
                classifications={0: ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")},
                model_used="gpt-4o-mini",
                total_tokens_used=12,
                processing_time_seconds=0.1,
                window_count=1,
            ),
            StructureRecognitionSummary(ai_classified_count=1, ai_heading_count=1),
        ),
    )
    monkeypatch.setattr(preparation, "_run_structure_validation", lambda **kwargs: None)

    def _fake_build_paragraph_relations(paragraphs, *, enabled_relation_kinds, structure_phase):
        captured.setdefault("relation_kinds", []).append(tuple(enabled_relation_kinds))
        return [], RelationNormalizationReport(total_relations=0, relation_counts={}, rejected_candidate_count=0, decisions=[])

    def _fake_build_semantic_blocks(paragraphs, max_chars, relations=None, structure_phase="post_ai_final"):
        captured["block_relations"] = relations
        return [DocumentBlock(paragraphs=list(paragraphs))]

    monkeypatch.setattr(preparation, "build_paragraph_relations", _fake_build_paragraph_relations)
    monkeypatch.setattr(preparation, "build_semantic_blocks", _fake_build_semantic_blocks)
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars, processing_operation="edit", structure_phase="post_ai_final": [{"target_text": "joined", "target_chars": 6, "context_chars": 0}])
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "\n\n".join(paragraph.text for paragraph in paragraphs))
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: _make_ai_first_config(
            relation_kinds=(),
            relation_normalization_enabled=False,
        ),
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert captured["relation_kinds"] == [()]
    assert captured["block_relations"] == []
    assert result.relations == []
    assert result.relation_report is not None
    assert result.relation_report.total_relations == 0


def test_prepare_document_for_processing_disables_downstream_relation_grouping_with_disabled_relation_normalization_when_post_ai_rebuild_fails(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        _build_paragraph(source_index=0, text="Содержание"),
        _build_paragraph(source_index=1, text="Глава 1........ 12"),
        _build_paragraph(source_index=2, text="Первый обычный абзац."),
    ]
    captured: dict[str, Any] = {"events": [], "relation_kinds": []}
    diagnostic_relations = [
        ParagraphRelation(
            relation_id="rel-diagnostic",
            relation_kind="toc_region_candidate",
            member_paragraph_ids=("p0000", "p0001"),
        )
    ]
    diagnostic_report = RelationNormalizationReport(
        total_relations=1,
        relation_counts={"toc_region_candidate": 1},
        rejected_candidate_count=0,
        decisions=[
            ParagraphRelationDecision(
                relation_kind="toc_region_candidate",
                decision="accept",
                member_paragraph_ids=("p0000", "p0001"),
                structure_phase="pre_ai_diagnostic",
                structure_source="pre_ai_diagnostic_hint",
            )
        ],
    )

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(
            paragraphs,
            [],
            _build_report(raw=3, logical=3),
            relations=diagnostic_relations,
            relation_report=diagnostic_report,
        ),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(preparation, "_run_document_map_stage", lambda **kwargs: None)
    monkeypatch.setattr(
        preparation,
        "_run_structure_recognition",
        lambda **kwargs: (
            None,
            StructureRecognitionSummary(
                ai_first_degraded=True,
                fallback_stage="stage2_structure_recognition_provider",
                fallback_reason="TimeoutError: timed out",
            ),
        ),
    )
    monkeypatch.setattr(preparation, "_run_structure_validation", lambda **kwargs: None)

    def _failing_build_paragraph_relations(paragraphs, *, enabled_relation_kinds, structure_phase):
        relation_kinds = cast(list[tuple[str, ...]], captured["relation_kinds"])
        relation_kinds.append(tuple(str(kind) for kind in enabled_relation_kinds))
        raise RuntimeError("relation rebuild failed")

    def _capturing_build_semantic_blocks(paragraphs, max_chars, relations=None, structure_phase="post_ai_final"):
        captured["block_relations"] = relations or []
        return [DocumentBlock(paragraphs=list(paragraphs))]

    monkeypatch.setattr(preparation, "build_paragraph_relations", _failing_build_paragraph_relations)
    monkeypatch.setattr(preparation, "build_semantic_blocks", _capturing_build_semantic_blocks)
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars, processing_operation="edit", structure_phase="post_ai_final": [{"target_text": "joined", "target_chars": 6, "context_chars": 0}])
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "\n\n".join(paragraph.text for paragraph in paragraphs))
    monkeypatch.setattr(
        preparation,
        "log_event",
        lambda level, event, message, **context: captured["events"].append((event, context)),
    )
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": False,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("toc_region",),
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

    assert captured["relation_kinds"] == [()]
    assert captured["block_relations"] == []
    assert result.relations == diagnostic_relations
    assert result.relation_report == diagnostic_report
    assert any(
        event == "relation_rebuild_after_structure_failed" and context.get("enabled_relation_kinds") == []
        for event, context in captured["events"]
    )


@pytest.mark.parametrize(
    (
        "document_map_status",
        "document_map_status_reason",
        "document_map",
        "expected_degraded",
        "expected_fallback_stage",
    ),
    [
        (
            "ai",
            "",
            DocumentMap(
                body_start_logical_index=10,
                toc_region=None,
                outline=(),
                paragraph_anchors={10: DocumentMapAnchor(role="body", heading_level=None, confidence="low")},
                review_zones=(),
                model_used="openrouter:test/document-map",
                total_tokens_used=0,
                processing_time_seconds=0.0,
                sampled=False,
                sampled_logical_indexes=(10,),
            ),
            False,
            "",
        ),
        (
            "cache",
            "",
            DocumentMap(
                body_start_logical_index=10,
                toc_region=None,
                outline=(),
                paragraph_anchors={10: DocumentMapAnchor(role="body", heading_level=None, confidence="low")},
                review_zones=(),
                model_used="openrouter:test/document-map",
                total_tokens_used=0,
                processing_time_seconds=0.0,
                sampled=False,
                sampled_logical_indexes=(10,),
            ),
            False,
            "",
        ),
        (
            "schema_failed",
            "DocumentMapSchemaError: schema-invalid output",
            None,
            True,
            "stage1_document_map_schema",
        ),
        (
            "provider_failed",
            "RuntimeError: Unsupported document-map client",
            None,
            True,
            "stage1_document_map_provider",
        ),
    ],
)
def test_prepare_document_for_processing_persists_document_map_status_into_prepared_data_logs_and_snapshot(
    monkeypatch,
    document_map_status,
    document_map_status_reason,
    document_map,
    expected_degraded,
    expected_fallback_stage,
):
    session_state = {"preparation_cache": {}}
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
    events = []

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=1, logical=1)),
    )

    def _fake_run_document_map_stage(*, fallback_state, **kwargs):
        fallback_state["document_map_status"] = document_map_status
        fallback_state["document_map_status_reason"] = document_map_status_reason
        fallback_state["document_map_present"] = document_map is not None
        if document_map is None and document_map_status in {"schema_failed", "provider_failed"}:
            fallback_state["ai_first_degraded"] = True
            fallback_state["fallback_stage"] = (
                "stage1_document_map_schema" if document_map_status == "schema_failed" else "stage1_document_map_provider"
            )
            fallback_state["fallback_reason"] = document_map_status_reason
        return document_map

    monkeypatch.setattr(preparation, "_run_document_map_stage", _fake_run_document_map_stage)
    monkeypatch.setattr(
        preparation,
        "_run_structure_recognition",
        lambda **kwargs: (
            None,
            StructureRecognitionSummary(),
        ),
    )
    monkeypatch.setattr(preparation, "_run_structure_validation", lambda **kwargs: None)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None, structure_phase="post_ai_final": [DocumentBlock(paragraphs=list(paragraphs))])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars, processing_operation="edit", structure_phase="post_ai_final": [{"target_text": "text", "target_chars": 4, "context_chars": 0}])
    monkeypatch.setattr(preparation, "log_event", lambda level, event, message, **context: events.append((event, context)))
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": False,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": (),
            "structure_recognition_mode": "always",
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
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

    snapshot = structural_validation._build_preparation_diagnostic_defaults([])
    structural_validation._apply_prepared_snapshot_fields(snapshot, result)

    assert result.document_map_status == document_map_status
    assert result.document_map_status_reason == document_map_status_reason
    assert result.structure_recognition_summary.ai_first_degraded is expected_degraded
    assert result.structure_recognition_summary.fallback_stage == expected_fallback_stage
    assert result.structure_recognition_summary.fallback_reason == (
        document_map_status_reason if expected_degraded else ""
    )
    assert snapshot["document_map_status"] == document_map_status
    assert snapshot["document_map_status_reason"] == document_map_status_reason
    assert snapshot["ai_first_degraded"] is expected_degraded
    assert snapshot["fallback_stage"] == expected_fallback_stage
    assert snapshot["fallback_reason"] == (document_map_status_reason if expected_degraded else "")
    structure_outcome_context = next(context for event, context in events if event == "structure_processing_outcome")
    assert structure_outcome_context["document_map_status"] == document_map_status
    assert structure_outcome_context["document_map_status_reason"] == document_map_status_reason
    assert structure_outcome_context["ai_first_degraded"] is expected_degraded
    assert structure_outcome_context["fallback_stage"] == expected_fallback_stage
    assert structure_outcome_context["fallback_reason"] == (document_map_status_reason if expected_degraded else "")
    if expected_degraded:
        assert structure_outcome_context["structure_status_note"].startswith(
            f"Структура: AI-first degraded ({expected_fallback_stage})"
        )


@pytest.mark.parametrize(
    ("fallback_stage", "fallback_reason"),
    [
        ("stage2_structure_recognition_provider", "TimeoutError: timed out"),
        ("stage3_reconciliation_provider", "TimeoutError: retry budget exhausted"),
        ("stage3_apply", "RuntimeError: final apply failed"),
    ],
)
def test_prepare_document_for_processing_exposes_stage_specific_degraded_ai_first_surfaces(
    monkeypatch,
    fallback_stage,
    fallback_reason,
):
    session_state = {"preparation_cache": {}}
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
    events = []
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
        sampled_logical_indexes=(10,),
    )

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=1, logical=1)),
    )
    monkeypatch.setattr(preparation, "_run_document_map_stage", lambda **kwargs: document_map)
    monkeypatch.setattr(
        preparation,
        "_run_structure_recognition",
        lambda **kwargs: (
            None,
            StructureRecognitionSummary(
                ai_first_degraded=True,
                fallback_stage=fallback_stage,
                fallback_reason=fallback_reason,
                document_map_present=True,
            ),
        ),
    )
    monkeypatch.setattr(preparation, "_run_structure_validation", lambda **kwargs: None)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(
        preparation,
        "build_semantic_blocks",
        lambda paragraphs, max_chars, relations=None, structure_phase="post_ai_final": [DocumentBlock(paragraphs=list(paragraphs))],
    )
    monkeypatch.setattr(
        preparation,
        "build_editing_jobs",
        lambda blocks, max_chars, processing_operation="edit", structure_phase="post_ai_final": [{"target_text": "text", "target_chars": 4, "context_chars": 0}],
    )
    monkeypatch.setattr(preparation, "log_event", lambda level, event, message, **context: events.append((event, context)))
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": False,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": (),
            "structure_recognition_mode": "always",
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-4o-mini"),
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
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

    event_log = [{"event_id": event, "context": context} for event, context in events]
    snapshot_from_log = structural_validation._build_preparation_diagnostic_defaults(event_log)
    snapshot_from_prepared = structural_validation._build_preparation_diagnostic_defaults([])
    structural_validation._apply_prepared_snapshot_fields(snapshot_from_prepared, result)
    structure_outcome_context = next(context for event, context in events if event == "structure_processing_outcome")

    assert result.document_map_status == "not_requested"
    assert result.structure_recognition_summary.ai_first_degraded is True
    assert result.structure_recognition_summary.fallback_stage == fallback_stage
    assert result.structure_recognition_summary.fallback_reason == fallback_reason
    assert snapshot_from_log["ai_first_degraded"] is True
    assert snapshot_from_log["fallback_stage"] == fallback_stage
    assert snapshot_from_log["fallback_reason"] == fallback_reason
    assert snapshot_from_log["document_map_present"] is True
    assert snapshot_from_prepared["ai_first_degraded"] is True
    assert snapshot_from_prepared["fallback_stage"] == fallback_stage
    assert snapshot_from_prepared["fallback_reason"] == fallback_reason
    assert snapshot_from_prepared["document_map_present"] is True
    assert structure_outcome_context["ai_first_degraded"] is True
    assert structure_outcome_context["fallback_stage"] == fallback_stage
    assert structure_outcome_context["fallback_reason"] == fallback_reason
    assert structure_outcome_context["structure_status_note"].startswith(
        f"Структура: AI-first degraded ({fallback_stage})"
    )


def test_run_structure_recognition_uses_model_aware_client_factory_for_default_runtime(monkeypatch):
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1")]
    paragraphs[0].logical_index = 10
    captured = {}

    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: captured.setdefault(
            "client_request",
            (selector, required_capability, config_like),
        )
        or object(),
    )
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda paragraphs, *, client, model, **kwargs: (
            captured.setdefault("client", client),
            captured.setdefault("model", model),
            StructureMap(
                classifications={10: ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high")},
                model_used=model,
                total_tokens_used=12,
                processing_time_seconds=0.1,
                window_count=1,
            ),
        )[-1],
    )
    monkeypatch.setattr(preparation, "apply_structure_map", lambda *args, **kwargs: {"ai_classified": 1, "ai_headings": 1})
    monkeypatch.setattr(preparation, "log_event", lambda *args, **kwargs: None)

    app_config = {
        "structure_recognition_cache_enabled": False,
        "structure_recognition_save_debug_artifacts": False,
        "structure_recognition_timeout_seconds": 60,
        "structure_recognition_min_confidence": "medium",
        "structure_recognition_model": "openrouter:test/structure",
        "models": _build_runtime_model_registry(structure_recognition_model="openrouter:test/structure"),
    }

    structure_map, summary = preparation._run_structure_recognition(
        paragraphs=paragraphs,
        image_assets=[],
        app_config=app_config,
        get_client_fn=preparation.get_client,
        progress_callback=None,
        normalization_report=_build_report(raw=1, logical=1),
        relation_report=None,
        document_map=None,
    )

    assert structure_map is not None
    assert summary.ai_classified_count == 1
    assert captured["client_request"] == ("openrouter:test/structure", "responses_text", app_config)
    assert captured["model"] == "openrouter:test/structure"


def test_build_document_map_strips_provider_prefix_before_openrouter_request(monkeypatch):
    captured = {}

    class _ResponsesClient:
        class responses:
            @staticmethod
            def create(**kwargs):
                captured["model"] = kwargs["model"]
                return type(
                    "ResponseStub",
                    (),
                    {
                        "output": [
                            type(
                                "OutputItem",
                                (),
                                {
                                    "content": [
                                        type(
                                            "ContentItem",
                                            (),
                                            {
                                                "type": "output_text",
                                                "text": json.dumps(
                                                    {
                                                        "body_start_logical_index": 0,
                                                        "toc_region": None,
                                                        "outline": [],
                                                        "paragraph_anchors": {
                                                            "0": {
                                                                "role": "body",
                                                                "heading_level": None,
                                                                "confidence": "low",
                                                            }
                                                        },
                                                        "review_zones": [],
                                                    },
                                                    ensure_ascii=False,
                                                ),
                                            },
                                        )()
                                    ]
                                },
                            )()
                        ],
                        "output_text": "",
                        "usage": type("UsageStub", (), {"total_tokens": 0})(),
                    },
                )()

    monkeypatch.setattr(document_map_module, "_with_request_timeout", lambda client, timeout: client)
    monkeypatch.setattr(document_map_module, "_load_system_prompt", lambda: "system")

    document_map = document_map_module.build_document_map(
        [_build_paragraph(source_index=0, text="Body")],
        client=_ResponsesClient(),
        model="openrouter:test/document-map",
        timeout=10.0,
        max_input_paragraphs=100,
        max_input_tokens=1000,
        preview_chars=120,
    )

    assert document_map is not None
    assert captured["model"] == "test/document-map"


def test_build_structure_map_strips_provider_prefix_before_openrouter_request(monkeypatch):
    captured = {}

    class _ResponsesClient:
        class responses:
            @staticmethod
            def create(**kwargs):
                captured["model"] = kwargs["model"]
                return type(
                    "ResponseStub",
                    (),
                    {
                        "output": [
                            type(
                                "OutputItem",
                                (),
                                {
                                    "content": [
                                        type(
                                            "ContentItem",
                                            (),
                                            {
                                                "type": "output_text",
                                                "text": json.dumps(
                                                    [{"i": 0, "r": "body", "l": None, "c": "low"}],
                                                    ensure_ascii=False,
                                                ),
                                            },
                                        )()
                                    ]
                                },
                            )()
                        ],
                        "output_text": "",
                        "usage": type("UsageStub", (), {"total_tokens": 0})(),
                    },
                )()

    monkeypatch.setattr(recognition_module, "_load_system_prompt", lambda: "system")

    structure_map = recognition_module.build_structure_map(
        [_build_paragraph(source_index=0, text="Body")],
        client=_ResponsesClient(),
        model="openrouter:test/structure",
        max_window_paragraphs=10,
        overlap_paragraphs=0,
        timeout=10.0,
    )

    assert structure_map is not None
    assert captured["model"] == "test/structure"


def test_prepare_document_for_processing_disables_downstream_relation_grouping_when_post_ai_relation_rebuild_fails(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [
        _build_paragraph(source_index=0, text="Содержание"),
        _build_paragraph(source_index=1, text="Глава 1........ 12"),
        _build_paragraph(source_index=2, text="Первый обычный абзац."),
    ]
    captured: dict[str, Any] = {"events": []}
    diagnostic_relations = [
        ParagraphRelation(
            relation_id="rel-diagnostic",
            relation_kind="toc_region_candidate",
            member_paragraph_ids=("p0000", "p0001"),
        )
    ]
    diagnostic_report = RelationNormalizationReport(
        total_relations=1,
        relation_counts={"toc_region_candidate": 1},
        rejected_candidate_count=0,
        decisions=[
            ParagraphRelationDecision(
                relation_kind="toc_region_candidate",
                decision="accept",
                member_paragraph_ids=("p0000", "p0001"),
                structure_phase="pre_ai_diagnostic",
                structure_source="pre_ai_diagnostic_hint",
            )
        ],
    )

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(
            paragraphs,
            [],
            _build_report(raw=3, logical=3),
            relations=diagnostic_relations,
            relation_report=diagnostic_report,
        ),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(preparation, "_run_document_map_stage", lambda **kwargs: None)
    monkeypatch.setattr(
        preparation,
        "_run_structure_recognition",
        lambda **kwargs: (
            None,
            StructureRecognitionSummary(
                ai_first_degraded=True,
                fallback_stage="stage2_structure_recognition_provider",
                fallback_reason="TimeoutError: timed out",
            ),
        ),
    )
    monkeypatch.setattr(preparation, "_run_structure_validation", lambda **kwargs: None)
    monkeypatch.setattr(
        preparation,
        "build_paragraph_relations",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("relation rebuild failed")),
    )

    def _fake_build_semantic_blocks(paragraphs, max_chars, relations=None, structure_phase="post_ai_final"):
        captured["block_phase"] = structure_phase
        captured["block_relations"] = relations
        return [DocumentBlock(paragraphs=list(paragraphs))]

    def _fake_build_editing_jobs(blocks, max_chars, processing_operation="edit", structure_phase="post_ai_final"):
        captured["job_phase"] = structure_phase
        return [{"target_text": "joined", "target_chars": 6, "context_chars": 0, "structure_phase": structure_phase}]

    monkeypatch.setattr(preparation, "build_semantic_blocks", _fake_build_semantic_blocks)
    monkeypatch.setattr(preparation, "build_editing_jobs", _fake_build_editing_jobs)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "\n\n".join(paragraph.text for paragraph in paragraphs))
    monkeypatch.setattr(
        preparation,
        "log_event",
        lambda level, event, message, **context: captured["events"].append((event, context)),
    )
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
            "relation_normalization_enabled_relation_kinds": ("toc_region",),
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

    assert captured["block_phase"] == "ai_first_degraded_fallback"
    assert captured["block_relations"] == []
    assert captured["job_phase"] == "ai_first_degraded_fallback"
    assert result.relations == diagnostic_relations
    assert result.relation_report == diagnostic_report
    assert result.relation_report is not None
    assert result.relation_report.decisions[0].decision == "accept"
    assert result.relation_report.decisions[0].relation_kind == "toc_region_candidate"
    assert result.relation_report.decisions[0].structure_phase == "pre_ai_diagnostic"
    assert any(
        event == "relation_rebuild_after_structure_failed"
        and context.get("downstream_relations_disabled") is True
        and context.get("preserved_relation_phase") == "pre_ai_diagnostic"
        for event, context in captured["events"]
    )


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

    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
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

    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
    )
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
    assert payload["prompt_version"] == preparation.DOCUMENT_MAP_PROMPT_VERSION
    assert payload["descriptor_schema_version"] == preparation.DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION
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
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
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
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: (_ for _ in ()).throw(RuntimeError("missing api key")),
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
    expected_key = _build_default_prepared_source_key("report.docx:10:hash")

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
            {"prepared_source_key": expected_key},
        ),
        (
            "preparation_cache_hit",
            {
                "prepared_source_key": expected_key,
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
    build_document_map_calls = {"count": 0}
    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda *args, **kwargs: build_document_map_calls.__setitem__("count", build_document_map_calls["count"] + 1),
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
            "structure_recovery_enabled": True,
            "structure_recovery_mode": "ai_first",
            "structure_recovery_document_map_enabled": True,
            "structure_recovery_document_map_model": "openrouter:test/document-map",
            "structure_recovery_document_map_cache_enabled": False,
            "structure_recovery_document_map_save_debug_artifacts": False,
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
    assert build_document_map_calls["count"] == 0
    assert build_structure_calls["count"] == 0
    assert result.document_map is None
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
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda *args, **kwargs: StructureMap(
            classifications={10: ParagraphClassification(index=10, role="heading", heading_level=1, confidence="high")},
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
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
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
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
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


def test_prepare_document_for_processing_uses_post_ai_validation_report_for_final_gate(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1"), _build_paragraph(source_index=1, text="Основной текст")]
    paragraphs[0].logical_index = 10
    paragraphs[1].logical_index = 11
    validation_calls = {"count": 0}

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(
        preparation,
        "get_client_for_model_selector",
        lambda selector, required_capability, *, config_like=None: object(),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_document_map",
        lambda paragraphs, *, client, model, timeout, max_input_paragraphs, max_input_tokens, preview_chars, progress_callback: DocumentMap(
            body_start_logical_index=10,
            toc_region=None,
            outline=(DocumentMapOutlineEntry(title="ГЛАВА 1", level=1, logical_index=10, confidence="high", evidence=("bold",)),),
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
        lambda *args, **kwargs: StructureMap(
            classifications={0: ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")},
            model_used="gpt-5-mini",
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    monkeypatch.setattr(
        preparation,
        "apply_structure_map",
        lambda paragraphs, structure_map, *, min_confidence="medium", document_map=None: (
            setattr(paragraphs[0], "role", "heading"),
            setattr(paragraphs[0], "heading_level", 1),
            {"ai_classified": 1, "ai_headings": 1},
        )[-1],
    )

    def _fake_validate_structure_quality(
        *,
        paragraphs,
        app_config,
        structure_repair_report=None,
        document_map_present=False,
        outline_coverage_ratio=None,
        phase="pre_ai_diagnostic",
    ):
        validation_calls["count"] += 1
        if phase == "pre_ai_diagnostic":
            return preparation.StructureValidationReport(
                paragraph_count=2,
                nonempty_paragraph_count=2,
                explicit_heading_count=0,
                heuristic_heading_count=0,
                suspicious_short_body_count=2,
                all_caps_body_count=0,
                centered_body_count=0,
                toc_like_sequence_count=1,
                ambiguous_paragraph_count=2,
                explicit_heading_density=0.0,
                suspicious_short_body_ratio=1.0,
                all_caps_or_centered_body_ratio=0.0,
                escalation_recommended=True,
                escalation_reasons=("toc_like_sequence_detected",),
                readiness_status="blocked_unsafe_best_effort_only",
                readiness_reasons=("toc_like_sequence_without_bounded_region",),
                document_map_present=False,
                outline_coverage_ratio=None,
            )
        assert phase == "post_ai_readiness"
        assert getattr(paragraphs[0], "role", "") == "heading"
        return preparation.StructureValidationReport(
            paragraph_count=2,
            nonempty_paragraph_count=2,
            explicit_heading_count=0,
            heuristic_heading_count=1,
            suspicious_short_body_count=0,
            all_caps_body_count=0,
            centered_body_count=0,
            toc_like_sequence_count=0,
            ambiguous_paragraph_count=0,
            explicit_heading_density=0.0,
            suspicious_short_body_ratio=0.0,
            all_caps_or_centered_body_ratio=0.0,
            escalation_recommended=False,
            escalation_reasons=(),
            readiness_status="ready",
            readiness_reasons=(),
            document_map_present=document_map_present,
            outline_coverage_ratio=outline_coverage_ratio,
        )

    monkeypatch.setattr(preparation, "validate_structure_quality", _fake_validate_structure_quality)
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
            "structure_recognition_model": "gpt-5-mini",
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
            "structure_recognition_cache_enabled": False,
            "structure_recognition_save_debug_artifacts": False,
            "structure_validation_enabled": True,
            "structure_validation_save_debug_artifacts": False,
            "structure_validation_block_on_high_risk_noop": True,
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
            "models": _build_runtime_model_registry(structure_recognition_model="gpt-5-mini"),
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert validation_calls["count"] == 2
    assert result.structure_validation_report is not None
    assert result.structure_validation_report.readiness_status == "ready"
    assert result.structure_validation_report.document_map_present is True
    assert result.structure_validation_report.outline_coverage_ratio == 1.0
    assert result.quality_gate_status == "pass"


def test_resolve_pre_translation_quality_gate_trusts_full_document_map_outline_for_toc_heading_expectation():
    report = preparation.StructureValidationReport(
        paragraph_count=85,
        nonempty_paragraph_count=85,
        explicit_heading_count=0,
        heuristic_heading_count=0,
        suspicious_short_body_count=19,
        all_caps_body_count=3,
        centered_body_count=0,
        toc_like_sequence_count=0,
        ambiguous_paragraph_count=19,
        explicit_heading_density=0.0,
        suspicious_short_body_ratio=0.22,
        all_caps_or_centered_body_ratio=0.03,
        escalation_recommended=True,
        escalation_reasons=("low_explicit_heading_density", "high_suspicious_short_body_ratio"),
        isolated_marker_paragraph_count=0,
        large_front_matter_block_risk=False,
        toc_region_bounded_count=0,
        expected_heading_candidates_from_toc=6,
        structure_quality_risk_level="high",
        readiness_status="blocked_unsafe_best_effort_only",
        readiness_reasons=("heading_count_far_below_toc_expectation",),
        document_map_present=True,
        outline_coverage_ratio=1.0,
    )

    status, reasons = preparation._resolve_pre_translation_quality_gate(
        structure_validation_report=report,
        structure_ai_attempted=True,
        structure_summary=StructureRecognitionSummary(ai_classified_count=81, ai_heading_count=2),
        app_config={"structure_validation_block_on_high_risk_noop": True},
    )

    assert status == "pass"
    assert reasons == ()


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


def test_apply_first_block_composition_quality_gate_uses_hint_toc_only_in_pre_ai_diagnostic():
    first_block = DocumentBlock(
        paragraphs=[
            ParagraphUnit(text="Contents", role="body", structural_role="body", heuristic_structural_role_hint="toc_header", source_index=0),
            ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="body", heuristic_structural_role_hint="toc_entry", source_index=1),
            ParagraphUnit(text="Epigraph line", role="body", structural_role="epigraph", source_index=2),
            ParagraphUnit(text="Introduction", role="heading", structural_role="body", heading_source="heuristic", source_index=3),
        ]
    )

    diagnostic_status, diagnostic_reasons = preparation._apply_first_block_composition_quality_gate(
        blocks=[first_block],
        processing_operation="translate",
        quality_gate_status="pass",
        quality_gate_reasons=(),
        structure_phase="pre_ai_diagnostic",
    )
    final_status, final_reasons = preparation._apply_first_block_composition_quality_gate(
        blocks=[first_block],
        processing_operation="translate",
        quality_gate_status="pass",
        quality_gate_reasons=(),
        structure_phase="post_ai_final",
    )

    assert diagnostic_status == "warning"
    assert diagnostic_reasons == (
        "first_block_mixed_toc_and_epigraph",
        "first_block_mixed_toc_and_body_start",
    )
    assert final_status == "pass"
    assert final_reasons == ()


def test_apply_first_block_composition_quality_gate_preserves_final_binding_mixed_block_warnings():
    first_block = DocumentBlock(
        paragraphs=[
            ParagraphUnit(text="Contents", role="body", structural_role="toc_header", source_index=0),
            ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", source_index=1),
            ParagraphUnit(text="Epigraph line", role="body", structural_role="epigraph", source_index=2),
            ParagraphUnit(text="Introduction", role="heading", structural_role="body", heading_source="heuristic", source_index=3),
        ]
    )

    status, reasons = preparation._apply_first_block_composition_quality_gate(
        blocks=[first_block],
        processing_operation="translate",
        quality_gate_status="pass",
        quality_gate_reasons=(),
        structure_phase="post_ai_final",
    )

    assert status == "warning"
    assert reasons == (
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


def test_build_structure_processing_status_note_marks_partial_ai_result_as_degraded():
    source = type(
        "StructureSource",
        (),
        {
            "structure_recognition_mode": "always",
            "structure_validation_report": None,
            "structure_map": object(),
            "structure_ai_attempted": True,
            "structure_recognition_summary": StructureRecognitionSummary(
                ai_classified_count=4,
                ai_heading_count=1,
                ai_first_degraded=True,
                fallback_stage="stage3_apply",
                fallback_reason="RuntimeError: final apply failed",
                document_map_present=True,
            ),
        },
    )()

    note = preparation.build_structure_processing_status_note(source)

    assert note == (
        "Структура: AI-first degraded (stage3_apply); продолжен ограниченный fallback-путь, "
        "классифицировано 4 абзацев. Причина: RuntimeError: final apply failed."
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
