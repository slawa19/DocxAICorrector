import base64
import json
import logging
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from typing import Any, cast

import docxaicorrector.generation._generation as generation
import docxaicorrector.pipeline._pipeline as document_pipeline
import docxaicorrector.pipeline.late_phases as document_pipeline_late_phases
import docxaicorrector.pipeline.output_validation as document_pipeline_output_validation
import docxaicorrector.pipeline.reassembly as document_pipeline_reassembly
from docx import Document

from docxaicorrector.core.models import DocumentMap
from docxaicorrector.core.models import DocumentMapTocRegion
from docxaicorrector.core.models import DocumentTopologyOperation
from docxaicorrector.core.models import DocumentTopologyProjection
from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.core.models import StructuralUnit
from docxaicorrector.document._document import extract_document_content_from_docx
from docxaicorrector.pipeline.contracts import SegmentSelection
from docxaicorrector.reader_cleanup_mvp import build_cleanup_blocks


PNG_BYTES = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII=")


class AssetStub:
    def __init__(self, image_id: str):
        self.image_id = image_id
        self.placeholder_status = None

    def update_pipeline_metadata(self, **values):
        self.placeholder_status = values.get("placeholder_status")


class PlannedJobs:
    def __init__(self, jobs, *, planned_len: int):
        self._jobs = list(jobs)
        self._planned_len = planned_len

    def __iter__(self):
        return iter(self._jobs)

    def __len__(self):
        return self._planned_len


class ParagraphStub:
    role = "body"


def _bounded_toc_document_map() -> DocumentMap:
    return DocumentMap(
        body_start_logical_index=10,
        toc_region=DocumentMapTocRegion(
            start_logical_index=0,
            end_logical_index=9,
            header_logical_index=0,
            entries=(),
            confidence="high",
        ),
        outline=(),
        paragraph_anchors={},
        review_zones=(),
        split_hints=(),
        sampled=False,
        sampled_logical_indexes=(0,),
    )


def _build_runtime_capture():
    return {"state": {}, "finalize": [], "activity": [], "log": [], "status": []}


def _emit_state(runtime, **values):
    runtime.setdefault("state", {}).update(values)


def _emit_finalize(runtime, stage, detail, progress, terminal_kind=None):
    runtime.setdefault("finalize", []).append((stage, detail, progress, terminal_kind))


def _emit_activity(runtime, message):
    runtime.setdefault("activity", []).append(message)


def _emit_log(runtime, **payload):
    runtime.setdefault("log", []).append(payload)


def _emit_status(runtime, **payload):
    runtime.setdefault("status", []).append(payload)


def _inspect_placeholder_integrity(markdown_text, image_assets):
    return {asset.image_id: "ok" for asset in image_assets}


def _convert_markdown_to_docx_bytes(markdown_text):
    return b"docx-bytes"


def _reinsert_inline_images(docx_bytes, image_assets):
    return docx_bytes


def _run_processing(runtime, **overrides):
    params = {
        "uploaded_file": "report.docx",
        "source_token": "",
        "run_id": "",
        "jobs": [{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        "output_mode": None,
        "source_paragraphs": [],
        "image_assets": [],
        "image_mode": "safe",
        "app_config": {},
        "model": "gpt-5.4",
        "max_retries": 1,
        "on_progress": lambda **kwargs: None,
        "runtime": runtime,
        "resolve_uploaded_filename": lambda uploaded_file: str(uploaded_file),
        "get_client": lambda: object(),
        "ensure_pandoc_available": lambda: None,
        "load_system_prompt": lambda **_kw: "system",
        "log_event": lambda *args, **kwargs: None,
        "present_error": lambda code, exc, title, **kwargs: f"{title}: {exc}",
        "emit_state": _emit_state,
        "emit_finalize": _emit_finalize,
        "emit_activity": _emit_activity,
        "emit_log": _emit_log,
        "emit_status": _emit_status,
        "should_stop_processing": lambda runtime: False,
        "generate_markdown_block": lambda **kwargs: "Обработанный блок",
        "process_document_images": lambda **kwargs: [],
        "inspect_placeholder_integrity": _inspect_placeholder_integrity,
        "convert_markdown_to_docx_bytes": _convert_markdown_to_docx_bytes,
        "preserve_source_paragraph_properties": lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        "reinsert_inline_images": _reinsert_inline_images,
        "write_ui_result_artifacts": lambda **kwargs: {"markdown_path": "/tmp/final.result.md", "docx_path": "/tmp/final.result.docx"},
    }
    params.update(overrides)
    return document_pipeline.run_document_processing(**params)


def _run_processing_and_read_quality_report(tmp_path, runtime, **overrides):
    quality_dir = tmp_path / "quality_reports"
    overrides.setdefault("app_config", {"translation_output_quality_gate_policy": "strict"})
    overrides.setdefault("processing_operation", "translate")
    overrides.setdefault("generate_markdown_block", lambda **kwargs: "Обработанный блок")
    result = _run_processing(runtime, **overrides)
    report_files = list(quality_dir.glob("*.json"))
    payload = json.loads(report_files[0].read_text(encoding="utf-8")) if report_files else None
    return result, payload


def _capture_log_events():
    captured = []

    def log_event(level, event_id, message, **context):
        captured.append({"level": level, "event_id": event_id, "message": message, "context": context})

    return captured, log_event


def test_run_document_processing_happy_path_updates_runtime_state():
    runtime = _build_runtime_capture()
    progress_calls = []
    image_assets = [AssetStub("img_001")]

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=image_assets,
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: progress_calls.append(kwargs),
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: image_assets,
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_docx_bytes"] == b"final-docx"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["finalize"][-1] == ("Обработка завершена", runtime["finalize"][-1][1], 1.0, "completed")
    assert runtime["log"][-1]["status"] == "DONE"
    assert len(progress_calls) == 3


def test_run_document_processing_builds_docx_once_when_reader_cleanup_disabled():
    runtime = _build_runtime_capture()
    converted_markdown_inputs = []

    def convert_markdown_to_docx_bytes(markdown_text):
        converted_markdown_inputs.append(markdown_text)
        return markdown_text.encode("utf-8")

    result = _run_processing(
        runtime,
        app_config={"reader_cleanup_enabled": False},
        generate_markdown_block=lambda **kwargs: "final block",
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "final block"
    assert runtime["state"]["latest_docx_bytes"] == b"final block"
    assert converted_markdown_inputs == ["final block"]


def test_pre_cleanup_formatting_baseline_is_diagnostic_only_rebuild_identity_snapshot():
    baseline = document_pipeline_late_phases._build_pre_cleanup_formatting_baseline(
        markdown_text="Intro translated\n\nBody translated",
        generated_paragraph_registry=[
            {"paragraph_id": "p0001", "text": "Intro translated"},
            {"paragraph_id": "p0002", "text": "Missing source"},
        ],
    )

    assert baseline == {
        "stage": "pre_reader_cleanup_rebuild_identity",
        "classification": "diagnostic_only",
        "mapping_basis": "ordered_exact_text_rebuild_sidecar",
        "metric_scope": "sidecar_only_proxy",
        "status": "computed",
        "source_count": 2,
        "target_count": 2,
        "mapped_count": 1,
        "unmapped_source_count": 1,
        "unmapped_target_count": 1,
        "unmapped_source_ids": ["p0002"],
        "unmapped_target_indexes": [1],
    }


def test_run_document_processing_passes_text_transform_context_to_system_prompt_loader():
    runtime = _build_runtime_capture()
    captured = {}

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"editorial_intensity_default": "conservative"},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="de",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: captured.setdefault("prompt", dict(kwargs)) or "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert captured["prompt"] == {
        "operation": "translate",
        "source_language": "en",
        "target_language": "de",
        "editorial_intensity": "conservative",
        "prompt_variant": "default",
        "translation_domain": "general",
        "source_text": "",
    }


def test_run_document_processing_routes_provider_aware_text_and_image_clients():
    runtime = _build_runtime_capture()
    text_calls = []
    image_calls = []
    openrouter_client = object()
    openai_client = object()

    def resolve_model_selector(selector, required_capability=None):
        if selector == "openrouter:google/gemini-3.1-flash-lite-preview":
            return SimpleNamespace(
                raw_selector=selector,
                canonical_selector=selector,
                provider="openrouter",
                model_id="google/gemini-3.1-flash-lite-preview",
            )
        return SimpleNamespace(
            raw_selector=selector,
            canonical_selector=f"openai:{selector}",
            provider="openai",
            model_id=selector.removeprefix("openai:"),
        )

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[AssetStub("img_001")],
        image_mode="semantic_redraw_direct",
        app_config={},
        model="openrouter:google/gemini-3.1-flash-lite-preview",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: openai_client,
        get_provider_client=lambda provider_name: openai_client if provider_name == "openai" else openrouter_client,
        get_client_for_model_selector=lambda selector, required_capability: openrouter_client,
        resolve_model_selector=resolve_model_selector,
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: text_calls.append(kwargs) or "Обработанный блок",
        process_document_images=lambda **kwargs: image_calls.append(kwargs) or kwargs["image_assets"],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert text_calls[0]["client"] is openrouter_client
    assert text_calls[0]["model"] == "google/gemini-3.1-flash-lite-preview"
    assert image_calls[0]["client"] is openai_client


def test_run_document_processing_does_not_fallback_to_text_client_for_openai_image_phase():
    runtime = _build_runtime_capture()
    openrouter_client = object()
    image_calls = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[AssetStub("img_001")],
        image_mode="semantic_redraw_direct",
        app_config={},
        model="openrouter:google/gemini-3.1-flash-lite-preview",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: (_ for _ in ()).throw(AssertionError("legacy get_client fallback must not run")),
        get_provider_client=lambda provider_name: (_ for _ in ()).throw(RuntimeError("missing OpenAI client")),
        get_client_for_model_selector=lambda selector, required_capability: openrouter_client,
        resolve_model_selector=lambda selector, required_capability=None: SimpleNamespace(
            raw_selector=selector,
            canonical_selector=selector,
            provider="openrouter",
            model_id="google/gemini-3.1-flash-lite-preview",
        ),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: image_calls.append(kwargs) or kwargs["image_assets"],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "failed"
    assert image_calls == []


def test_run_document_processing_routes_second_pass_through_provider_aware_selector():
    runtime = _build_runtime_capture()
    text_calls = []
    main_client = object()
    second_pass_client = object()

    def resolve_model_selector(selector, required_capability=None):
        if selector == "openrouter:google/gemini-3.1-flash-lite-preview":
            return SimpleNamespace(
                raw_selector=selector,
                canonical_selector=selector,
                provider="openrouter",
                model_id="google/gemini-3.1-flash-lite-preview",
            )
        return SimpleNamespace(
            raw_selector=selector,
            canonical_selector=f"openai:{selector}",
            provider="openai",
            model_id=selector.removeprefix("openai:"),
        )

    def get_client_for_model_selector(selector, required_capability):
        if selector == "openrouter:google/gemini-3.1-flash-lite-preview":
            return second_pass_client
        return main_client

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={
            "translation_second_pass_enabled": True,
            "translation_second_pass_model": "openrouter:google/gemini-3.1-flash-lite-preview",
        },
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="translate",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: main_client,
        get_client_for_model_selector=get_client_for_model_selector,
        resolve_model_selector=resolve_model_selector,
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: text_calls.append(kwargs) or "Обработанный блок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert len(text_calls) == 2
    assert text_calls[0]["client"] is main_client
    assert text_calls[0]["model"] == "gpt-5.4-mini"
    assert text_calls[1]["client"] is second_pass_client
    assert text_calls[1]["model"] == "google/gemini-3.1-flash-lite-preview"


def test_run_document_processing_persists_final_ui_result_artifacts_and_logs_paths():
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/mariana.result.md",
            "docx_path": "/tmp/mariana.result.docx",
        }

    result = _run_processing(
        runtime,
        log_event=log_event,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert captured["artifact_kwargs"] == {
        "source_name": "report.docx",
        "markdown_text": "Обработанный блок",
        "docx_bytes": b"docx-bytes",
        "assembly_mode": "full_document",
        "result_manifest": {
            "schema_version": 1,
            "source_name": "report.docx",
            "assembly_mode": "full_document",
            "output_mode": "legacy_full_document",
            "selected_segment_count": 0,
            "included_segment_count": 0,
            "included_segment_ids": [],
            "coverage": {
                "segment_ids": [],
                "paragraph_ranges": [],
            },
            "segments": [],
        },
    }
    info_events = [event for event in events if event["level"] == logging.INFO]
    saved_event = next(event for event in info_events if event["event_id"] == "ui_result_artifacts_saved")
    assert saved_event["context"]["artifact_paths"] == {
        "markdown_path": "/tmp/mariana.result.md",
        "docx_path": "/tmp/mariana.result.docx",
    }


def test_run_document_processing_passes_selected_chapters_assembly_mode_to_artifact_writer():
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/mariana.result.md",
            "docx_path": "/tmp/mariana.result.docx",
        }

    result = _run_processing(
        runtime,
        log_event=log_event,
        write_ui_result_artifacts=write_ui_result_artifacts,
        selected_segment_ids=["seg_0001", "seg_0002"],
    )

    assert result == "succeeded"
    assert captured["artifact_kwargs"]["assembly_mode"] == "selected_chapters"
    assert captured["artifact_kwargs"]["selected_segment_count"] == 2
    assert captured["artifact_kwargs"]["result_manifest"] == {
        "schema_version": 1,
        "source_name": "report.docx",
        "assembly_mode": "selected_chapters",
        "output_mode": "selected_only",
        "selected_segment_count": 2,
        "included_segment_count": 2,
        "included_segment_ids": ["seg_0001", "seg_0002"],
        "coverage": {
            "segment_ids": ["seg_0001", "seg_0002"],
            "paragraph_ranges": [],
        },
        "selected_segment_ids": ["seg_0001", "seg_0002"],
        "segments": [
            {"segment_id": "seg_0001", "job_count": 0, "selected": True},
            {"segment_id": "seg_0002", "job_count": 0, "selected": True},
        ],
    }


def test_run_document_processing_preserves_selected_with_context_output_mode_for_selected_runs():
    runtime = _build_runtime_capture()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/mariana.result.md",
            "docx_path": "/tmp/mariana.result.docx",
            "manifest_path": "/tmp/mariana.result.manifest.json",
        }

    result = _run_processing(
        runtime,
        output_mode="selected_with_context",
        selected_segment_ids=["seg_0001", "seg_0002"],
        jobs=[
            {"target_text": "block 1", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0, "segment_id": "seg_0001"},
            {"target_text": "block 2", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0, "segment_id": "seg_0002"},
        ],
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert captured["artifact_kwargs"]["assembly_mode"] == "selected_chapters"
    assert captured["artifact_kwargs"]["result_manifest"]["output_mode"] == "selected_with_context"
    assert captured["artifact_kwargs"]["result_manifest"]["selected_segment_ids"] == ["seg_0001", "seg_0002"]


def test_run_document_processing_persists_segment_selection_in_result_manifest():
    runtime = _build_runtime_capture()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/mariana.result.md",
            "docx_path": "/tmp/mariana.result.docx",
        }

    result = _run_processing(
        runtime,
        write_ui_result_artifacts=write_ui_result_artifacts,
        selected_segment_ids=None,
        segment_selection=SegmentSelection(
            selected_segment_ids=("seg_0003",),
            include_descendants=False,
            output_mode="selected_only",
        ),
    )

    assert result == "succeeded"
    assert captured["artifact_kwargs"]["result_manifest"]["selected_segment_ids"] == ["seg_0003"]
    assert captured["artifact_kwargs"]["result_manifest"]["segment_selection"] == {
        "selected_segment_ids": ["seg_0003"],
        "include_descendants": False,
        "include_front_matter": False,
        "include_toc": False,
        "output_mode": "selected_only",
    }


def test_build_reassembly_plan_expands_selected_with_context_with_structural_context_only():
    plan = document_pipeline_reassembly.build_reassembly_plan(
        selected_segment_ids=["seg_0003"],
        output_mode="selected_with_context",
        include_front_matter=True,
        include_toc=True,
        jobs=[{"segment_id": "seg_0003"}],
        source_paragraphs=[
            SimpleNamespace(segment_id="seg_front", text="Title", structural_role="front_matter"),
            SimpleNamespace(segment_id="seg_0002", text="Chapter 2", structural_role="body"),
            SimpleNamespace(segment_id="seg_toc", text="Contents", structural_role="toc_entry"),
            SimpleNamespace(segment_id="seg_0003", text="Chapter 3", structural_role="body"),
            SimpleNamespace(segment_id="seg_0004", text="Chapter 4", structural_role="body"),
        ],
    )

    assert plan.output_mode == "selected_with_context"
    assert plan.selected_segment_ids == ("seg_0003",)
    assert plan.included_segment_ids == ("seg_front", "seg_toc", "seg_0003")


def test_build_reassembly_plan_respects_selected_with_context_include_flags_independently():
    plan = document_pipeline_reassembly.build_reassembly_plan(
        selected_segment_ids=["seg_0003"],
        output_mode="selected_with_context",
        include_front_matter=True,
        include_toc=False,
        jobs=[{"segment_id": "seg_0003"}],
        source_paragraphs=[
            SimpleNamespace(segment_id="seg_front", text="Title", structural_role="front_matter"),
            SimpleNamespace(segment_id="seg_toc", text="Contents", structural_role="toc_entry"),
            SimpleNamespace(segment_id="seg_0003", text="Chapter 3", structural_role="body"),
        ],
    )

    assert plan.included_segment_ids == ("seg_front", "seg_0003")


def test_run_document_processing_assembles_selected_with_context_document(monkeypatch):
    runtime = _build_runtime_capture()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/context.result.md",
            "docx_path": "/tmp/context.result.docx",
            "manifest_path": "/tmp/context.result.manifest.json",
        }

    monkeypatch.setattr(
        document_pipeline_late_phases,
        "build_segment_result_records",
        lambda **kwargs: [
            {
                "segment_id": "seg_0003",
                "translated_markdown": "Translated chapter 3",
                "paragraph_ids": ["p3"],
            }
        ],
    )

    result = _run_processing(
        runtime,
        output_mode="selected_with_context",
        include_front_matter=True,
        include_toc=True,
        selected_segment_ids=["seg_0003"],
        jobs=[
            {
                "segment_id": "seg_0003",
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
            }
        ],
        source_paragraphs=[
            SimpleNamespace(segment_id="seg_front", paragraph_id="p1", text="# Title", rendered_text="# Title", structural_role="front_matter"),
            SimpleNamespace(segment_id="seg_0002", paragraph_id="p2", text="Earlier chapter", rendered_text="Earlier chapter", structural_role="body"),
            SimpleNamespace(segment_id="seg_toc", paragraph_id="p3", text="Contents", rendered_text="Contents", structural_role="toc_entry"),
            SimpleNamespace(segment_id="seg_0003", paragraph_id="p4", text="Chapter 3", rendered_text="Chapter 3", structural_role="body"),
            SimpleNamespace(segment_id="seg_0004", paragraph_id="p5", text="Chapter 4", rendered_text="Chapter 4", structural_role="body"),
        ],
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "# Title\n\nContents\n\nTranslated chapter 3"
    assert captured["artifact_kwargs"]["markdown_text"] == "# Title\n\nContents\n\nTranslated chapter 3"
    assert captured["artifact_kwargs"]["result_manifest"]["segments"] == [
        {"segment_id": "seg_front", "job_count": 0, "selected": False, "provenance": "source"},
        {"segment_id": "seg_toc", "job_count": 0, "selected": False, "provenance": "source"},
        {"segment_id": "seg_0003", "job_count": 1, "selected": True, "provenance": "translated"},
    ]


def test_run_document_processing_builds_segment_aware_manifest_for_full_document_output():
    runtime = _build_runtime_capture()
    captured = {}
    source_paragraphs = [
        SimpleNamespace(role="body", segment_id="seg_0001", text="Chapter 1"),
        SimpleNamespace(role="body", segment_id="seg_0002", text="Chapter 2"),
    ]

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/mariana.result.md",
            "docx_path": "/tmp/mariana.result.docx",
            "manifest_path": "/tmp/mariana.result.manifest.json",
        }

    result = _run_processing(
        runtime,
        source_token="report.docx:3:token",
        run_id="run-123",
        jobs=[
            {"target_text": "block 1", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0, "segment_id": "seg_0001"},
            {"target_text": "block 2", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0, "segment_id": "seg_0002"},
            {"target_text": "block 3", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0, "segment_id": "seg_0002"},
        ],
        source_paragraphs=source_paragraphs,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert captured["artifact_kwargs"]["assembly_mode"] == "full_document"
    assert "selected_segment_count" not in captured["artifact_kwargs"]
    assert captured["artifact_kwargs"]["result_manifest"] == {
        "schema_version": 1,
        "source_name": "report.docx",
        "source_token": "report.docx:3:token",
        "run_id": "run-123",
        "assembly_mode": "full_document",
        "output_mode": "legacy_full_document",
        "selected_segment_count": 0,
        "included_segment_count": 2,
        "included_segment_ids": ["seg_0001", "seg_0002"],
        "coverage": {
            "segment_ids": ["seg_0001", "seg_0002"],
            "paragraph_ranges": [
                {"segment_id": "seg_0001", "start_paragraph_index": 0, "end_paragraph_index": 0, "paragraph_count": 1},
                {"segment_id": "seg_0002", "start_paragraph_index": 1, "end_paragraph_index": 1, "paragraph_count": 1},
            ],
        },
        "segments": [
            {"segment_id": "seg_0001", "job_count": 1, "selected": False},
            {"segment_id": "seg_0002", "job_count": 2, "selected": False},
        ],
    }


def test_run_document_processing_manifest_omits_noncanonical_segment_titles():
    runtime = _build_runtime_capture()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/mariana.result.md",
            "docx_path": "/tmp/mariana.result.docx",
            "manifest_path": "/tmp/mariana.result.manifest.json",
        }

    result = _run_processing(
        runtime,
        jobs=[
            {"target_text": "block 1", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0, "segment_id": "seg_0001"},
        ],
        source_paragraphs=[SimpleNamespace(role="body", segment_id="seg_0001", text="This is body text, not a canonical heading")],
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert captured["artifact_kwargs"]["result_manifest"]["segments"] == [
        {"segment_id": "seg_0001", "job_count": 1, "selected": False}
    ]


def test_run_document_processing_passes_machine_readable_quality_warning_to_artifact_writer_with_diagnostics(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/report.result.md",
            "docx_path": "/tmp/report.result.docx",
            "manifest_path": "/tmp/report.result.manifest.json",
        }

    result = _run_processing(
        runtime,
        output_mode="legacy_full_document",
        jobs=[
            {
                "segment_id": "seg_0001",
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
            }
        ],
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert captured["artifact_kwargs"]["result_manifest"]["output_mode"] == "legacy_full_document"


def test_run_document_processing_passes_machine_readable_quality_warning_to_artifact_writer(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    diagnostics_dir = tmp_path / "formatting_diagnostics"
    quality_dir = tmp_path / "quality_reports"
    artifact_calls = {}

    monkeypatch.setattr(document_pipeline, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    quality_dir.mkdir(parents=True, exist_ok=True)

    def preserve_with_unmapped_artifact(docx_bytes, paragraphs, generated_paragraph_registry=None):
        (diagnostics_dir / "preserve_001.json").write_text(
            json.dumps(
                {
                    "stage": "restore",
                    "source_count": 50,
                    "target_count": 48,
                    "mapped_count": 48,
                    "unmapped_source_ids": ["p0048", "p0049"],
                    "unmapped_target_indexes": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return docx_bytes

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[ParagraphStub()],
        image_assets=[],
        image_mode="safe",
        app_config={"translation_output_quality_gate_policy": "advisory"},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="translate",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=preserve_with_unmapped_artifact,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=lambda **kwargs: artifact_calls.setdefault("kwargs", dict(kwargs)) or {"markdown_path": "/tmp/report.result.md", "docx_path": "/tmp/report.result.docx", "metadata_path": "/tmp/report.result.meta.json"},
    )

    assert result == "succeeded"
    assert artifact_calls["kwargs"]["quality_warning"] == {
        "kind": "translation_quality_gate",
        "quality_status": "warn",
        "gate_reasons": ["unmapped_source_paragraphs_above_advisory_threshold"],
        "message": "Результат собран, но quality report зафиксировал document-level structural warnings.",
    }


def test_run_document_processing_preserves_final_translated_book_output_mode_in_manifest(monkeypatch):
    runtime = _build_runtime_capture()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/report.result.md",
            "docx_path": "/tmp/report.result.docx",
            "manifest_path": "/tmp/report.result.manifest.json",
        }

    monkeypatch.setattr(
        document_pipeline_late_phases,
        "build_segment_result_records",
        lambda **kwargs: [
            {"segment_id": "seg_0001", "translated_markdown": "Translated chapter 1", "paragraph_ids": ["p1"]},
        ],
    )

    result = _run_processing(
        runtime,
        output_mode="final_translated_book",
        jobs=[
            {
                "segment_id": "seg_0001",
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
            }
        ],
        source_paragraphs=[
            SimpleNamespace(segment_id="seg_0001", paragraph_id="p1", text="Source 1", rendered_text="Source 1", structural_role="body"),
        ],
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert captured["artifact_kwargs"]["result_manifest"]["output_mode"] == "final_translated_book"


def test_run_document_processing_assembles_final_translated_book_from_translated_segments(monkeypatch):
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/report.result.md",
            "docx_path": "/tmp/report.result.docx",
            "manifest_path": "/tmp/report.result.manifest.json",
        }

    monkeypatch.setattr(
        document_pipeline_late_phases,
        "build_segment_result_records",
        lambda **kwargs: [
            {"segment_id": "seg_0001", "translated_markdown": "Translated chapter 1", "paragraph_ids": ["p1"]},
            {"segment_id": "seg_0002", "translated_markdown": "Translated chapter 2", "paragraph_ids": ["p2"]},
        ],
    )

    result = _run_processing(
        runtime,
        output_mode="final_translated_book",
        jobs=[
            {"segment_id": "seg_0001", "target_text": "block 1", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0},
            {"segment_id": "seg_0002", "target_text": "block 2", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0},
        ],
        source_paragraphs=[
            SimpleNamespace(segment_id="seg_0001", paragraph_id="p1", text="Source 1", rendered_text="Source 1", structural_role="body"),
            SimpleNamespace(segment_id="seg_0002", paragraph_id="p2", text="Source 2", rendered_text="Source 2", structural_role="body"),
        ],
        write_ui_result_artifacts=write_ui_result_artifacts,
        log_event=log_event,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "Translated chapter 1\n\nTranslated chapter 2"
    assert captured["artifact_kwargs"]["result_manifest"]["segments"] == [
        {"segment_id": "seg_0001", "job_count": 1, "selected": False, "provenance": "translated"},
        {"segment_id": "seg_0002", "job_count": 1, "selected": False, "provenance": "translated"},
    ]
    assert any(event["event_id"] == "final_translated_book_assembled" for event in events)


def test_run_document_processing_fails_final_translated_book_when_segment_translation_is_missing(monkeypatch):
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()

    monkeypatch.setattr(
        document_pipeline_late_phases,
        "build_segment_result_records",
        lambda **kwargs: [
            {"segment_id": "seg_0001", "translated_markdown": "Translated chapter 1", "paragraph_ids": ["p1"]},
        ],
    )

    result = _run_processing(
        runtime,
        output_mode="final_translated_book",
        jobs=[
            {"segment_id": "seg_0001", "target_text": "block 1", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0},
            {"segment_id": "seg_0002", "target_text": "block 2", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0},
        ],
        source_paragraphs=[
            SimpleNamespace(segment_id="seg_0001", paragraph_id="p1", text="Source 1", rendered_text="Source 1", structural_role="body"),
            SimpleNamespace(segment_id="seg_0002", paragraph_id="p2", text="Source 2", rendered_text="Source 2", structural_role="body"),
        ],
        log_event=log_event,
    )

    assert result == "failed"
    assert runtime["finalize"][-1][0] == "Итоговая книга недоступна"
    assert "seg_0002" in str(runtime["state"].get("last_error") or "")
    assert any(event["event_id"] == "final_translated_book_incomplete" for event in events)


def test_run_document_processing_preserves_hybrid_document_output_mode_in_manifest():
    runtime = _build_runtime_capture()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/report.result.md",
            "docx_path": "/tmp/report.result.docx",
            "manifest_path": "/tmp/report.result.manifest.json",
        }

    result = _run_processing(
        runtime,
        output_mode="hybrid_document",
        jobs=[
            {
                "segment_id": "seg_0001",
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
            }
        ],
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert captured["artifact_kwargs"]["result_manifest"]["output_mode"] == "hybrid_document"


def test_run_document_processing_persists_segment_result_records(monkeypatch):
    runtime = _build_runtime_capture()
    captured = {}
    expected_records = [
        {
            "schema_version": 1,
            "source_name": "report.docx",
            "prepared_source_key": "prep:report:1234",
            "structure_fingerprint": "struct-abc",
            "segment_id": "seg_0001",
            "assembly_mode": "selected_chapters",
            "output_mode": "selected_only",
            "selected": True,
            "result_artifact_paths": {
                "markdown_path": "/tmp/report.result.md",
                "docx_path": "/tmp/report.result.docx",
                "manifest_path": "/tmp/report.result.manifest.json",
            },
            "paragraph_ids": ["p0001"],
            "source_indexes": [0],
            "entry_count": 1,
            "translated_markdown": "Обработанный блок",
        }
    ]

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/report.result.md",
            "docx_path": "/tmp/report.result.docx",
            "manifest_path": "/tmp/report.result.manifest.json",
        }

    def write_segment_result_registry(*, records):
        captured["segment_records"] = list(records)
        return {"seg_0001": "/tmp/segment-results/seg_0001.segment-result.json"}

    monkeypatch.setattr(document_pipeline, "write_segment_result_registry_impl", write_segment_result_registry)
    monkeypatch.setattr(document_pipeline_late_phases, "build_segment_result_records", lambda **kwargs: list(expected_records))

    result = _run_processing(
        runtime,
        prepared_source_key="prep:report:1234",
        structure_fingerprint="struct-abc",
        selected_segment_ids=["seg_0001"],
        output_mode="selected_only",
        jobs=[
            {
                "segment_id": "seg_0001",
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
            }
        ],
        source_paragraphs=[
            SimpleNamespace(
                role="body",
                paragraph_id="p0001",
                segment_id="seg_0001",
                text="Original paragraph",
            )
        ],
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert captured["segment_records"] == expected_records


def test_run_document_processing_persists_completed_job_result_records(monkeypatch):
    runtime = _build_runtime_capture()
    captured = {}

    def write_job_result_registry(*, records):
        captured["job_records"] = list(records)
        return {"job_0000": "/tmp/job-results/job_0000.job-result.json"}

    monkeypatch.setattr(document_pipeline, "write_job_result_registry_impl", write_job_result_registry)

    result = _run_processing(
        runtime,
        prepared_source_key="prep:report:1234",
        structure_fingerprint="struct-abc",
        jobs=[
            {
                "job_id": "job_0000",
                "segment_id": "seg_0001",
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
            }
        ],
    )

    assert result == "succeeded"
    assert len(captured["job_records"]) == 1
    completed_record = dict(captured["job_records"][0])
    assert isinstance(completed_record.pop("updated_at", ""), str)
    assert completed_record == {
        "schema_version": 1,
        "prepared_source_key": "prep:report:1234",
        "structure_fingerprint": "struct-abc",
        "job_id": "job_0000",
        "segment_id": "seg_0001",
        "status": "completed",
        "block_index": 1,
        "target_chars": 5,
        "context_chars": 0,
    }


def test_build_segment_result_records_maps_assembly_entries_to_segments():
    plan = document_pipeline_reassembly.build_reassembly_plan(
        selected_segment_ids=["seg_0001"],
        output_mode="selected_only",
        jobs=[{"segment_id": "seg_0001"}],
    )

    records = document_pipeline_reassembly.build_segment_result_records(
        source_name="report.docx",
        prepared_source_key="prep:report:1234",
        structure_fingerprint="struct-abc",
        plan=plan,
        source_paragraphs=[SimpleNamespace(paragraph_id="p0001", segment_id="seg_0001")],
        assembly_entries=[SimpleNamespace(text="Обработанный блок", paragraph_id="p0001", source_index=0, merged_paragraph_ids=())],
        result_artifact_paths={
            "markdown_path": "/tmp/report.result.md",
            "docx_path": "/tmp/report.result.docx",
            "manifest_path": "/tmp/report.result.manifest.json",
        },
    )

    assert records == [
        {
            "schema_version": 1,
            "source_name": "report.docx",
            "prepared_source_key": "prep:report:1234",
            "structure_fingerprint": "struct-abc",
            "segment_id": "seg_0001",
            "assembly_mode": "selected_chapters",
            "output_mode": "selected_only",
            "selected": True,
            "result_artifact_paths": {
                "markdown_path": "/tmp/report.result.md",
                "docx_path": "/tmp/report.result.docx",
                "manifest_path": "/tmp/report.result.manifest.json",
            },
            "paragraph_ids": ["p0001"],
            "source_indexes": [0],
            "entry_count": 1,
            "translated_markdown": "Обработанный блок",
        }
    ]


def test_load_segment_result_records_returns_latest_record_per_segment(tmp_path):
    target_dir = tmp_path / "prep_report_1234" / "struct-abc"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "seg_0001.segment-result.json").write_text(
        json.dumps(
            {
                "segment_id": "seg_0001",
                "translated_markdown": "Stored translation",
                "prepared_source_key": "prep:report:1234",
                "structure_fingerprint": "struct-abc",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    records = document_pipeline_reassembly.load_segment_result_records(
        prepared_source_key="prep:report:1234",
        structure_fingerprint="struct-abc",
        input_dir=tmp_path,
    )

    assert records == {
        "seg_0001": {
            "segment_id": "seg_0001",
            "translated_markdown": "Stored translation",
            "prepared_source_key": "prep:report:1234",
            "structure_fingerprint": "struct-abc",
        }
    }


def test_assemble_hybrid_document_prefers_current_then_persisted_then_source():
    plan = document_pipeline_reassembly.build_reassembly_plan(
        selected_segment_ids=None,
        output_mode="hybrid_document",
        jobs=[{"segment_id": "seg_0001"}],
        source_paragraphs=[
            SimpleNamespace(segment_id="seg_0001", paragraph_id="p1", text="Source 1", rendered_text="Source 1"),
            SimpleNamespace(segment_id="seg_0002", paragraph_id="p2", text="Source 2", rendered_text="Source 2"),
            SimpleNamespace(segment_id="seg_0003", paragraph_id="p3", text="Source 3", rendered_text="Source 3"),
        ],
    )

    result = document_pipeline_reassembly.assemble_hybrid_document(
        plan=plan,
        source_paragraphs=[
            SimpleNamespace(segment_id="seg_0001", paragraph_id="p1", text="Source 1", rendered_text="Source 1"),
            SimpleNamespace(segment_id="seg_0002", paragraph_id="p2", text="Source 2", rendered_text="Source 2"),
            SimpleNamespace(segment_id="seg_0003", paragraph_id="p3", text="Source 3", rendered_text="Source 3"),
        ],
        current_segment_records={
            "seg_0001": {
                "segment_id": "seg_0001",
                "translated_markdown": "Current translation 1",
                "paragraph_ids": ["p1"],
            }
        },
        persisted_segment_records={
            "seg_0002": {
                "segment_id": "seg_0002",
                "translated_markdown": "Stored translation 2",
                "paragraph_ids": ["p2"],
            }
        },
    )

    assert result.final_markdown == "Current translation 1\n\nStored translation 2\n\nSource 3"
    assert result.segment_provenance_by_id == {
        "seg_0001": "translated",
        "seg_0002": "translated",
        "seg_0003": "source",
    }
    assert result.generated_paragraph_registry == [
        {"block_index": 0, "paragraph_id": "p1", "text": "Current translation 1"},
        {"block_index": 1, "paragraph_id": "p2", "text": "Stored translation 2"},
        {"block_index": 2, "paragraph_id": "p3", "text": "Source 3"},
    ]


def test_run_document_processing_assembles_true_hybrid_document(monkeypatch):
    runtime = _build_runtime_capture()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/report.result.md",
            "docx_path": "/tmp/report.result.docx",
            "manifest_path": "/tmp/report.result.manifest.json",
        }

    monkeypatch.setattr(
        document_pipeline_late_phases,
        "build_segment_result_records",
        lambda **kwargs: [
            {
                "segment_id": "seg_0001",
                "translated_markdown": "Current translation 1",
                "paragraph_ids": ["p1"],
            }
        ],
    )
    monkeypatch.setattr(
        document_pipeline_late_phases,
        "load_segment_result_records",
        lambda **kwargs: {
            "seg_0002": {
                "segment_id": "seg_0002",
                "translated_markdown": "Stored translation 2",
                "paragraph_ids": ["p2"],
            }
        },
    )

    result = _run_processing(
        runtime,
        prepared_source_key="prep:report:1234",
        structure_fingerprint="struct-abc",
        output_mode="hybrid_document",
        jobs=[
            {
                "segment_id": "seg_0001",
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
            }
        ],
        source_paragraphs=[
            SimpleNamespace(segment_id="seg_0001", paragraph_id="p1", text="Source 1", rendered_text="Source 1"),
            SimpleNamespace(segment_id="seg_0002", paragraph_id="p2", text="Source 2", rendered_text="Source 2"),
            SimpleNamespace(segment_id="seg_0003", paragraph_id="p3", text="Source 3", rendered_text="Source 3"),
        ],
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "Current translation 1\n\nStored translation 2\n\nSource 3"
    assert captured["artifact_kwargs"]["markdown_text"] == "Current translation 1\n\nStored translation 2\n\nSource 3"
    assert captured["artifact_kwargs"]["result_manifest"]["output_mode"] == "hybrid_document"
    assert captured["artifact_kwargs"]["result_manifest"]["segments"] == [
        {"segment_id": "seg_0001", "job_count": 1, "selected": False, "provenance": "translated"},
        {"segment_id": "seg_0002", "job_count": 0, "selected": False, "provenance": "translated"},
        {"segment_id": "seg_0003", "job_count": 0, "selected": False, "provenance": "source"},
    ]


def test_run_document_processing_builds_standalone_audiobook_artifact_and_coerces_image_mode():
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    captured = {}

    def write_ui_result_artifacts(**kwargs):
        captured["artifact_kwargs"] = kwargs
        return {
            "markdown_path": "/tmp/report.result.md",
            "docx_path": "/tmp/report.result.docx",
            "tts_text_path": "/tmp/report.result.tts.txt",
        }

    processed_image_modes = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "# Title\n\n[thoughtful] Body text",
            "context_before": "",
            "context_after": "",
            "target_chars": 29,
            "context_chars": 0,
            "narration_include": True,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="audiobook",
        source_language="auto",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "# Title\n\n[thoughtful] Body text",
        process_document_images=lambda **kwargs: processed_image_modes.append(kwargs["image_mode"]) or [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert processed_image_modes == ["no_change"]
    assert runtime["state"]["latest_narration_text"] == "Title\n\n[thoughtful] Body text"
    assert captured["artifact_kwargs"]["narration_text"] == "Title\n\n[thoughtful] Body text"
    info_events = [event for event in events if event["level"] == logging.INFO]
    saved_event = next(event for event in info_events if event["event_id"] == "ui_audiobook_artifact_saved")
    assert saved_event["context"]["mode"] == "standalone"
    assert saved_event["context"]["filename"] == "report.docx"
    assert saved_event["context"]["artifact_paths"] == {
        "markdown_path": "/tmp/report.result.md",
        "docx_path": "/tmp/report.result.docx",
        "tts_text_path": "/tmp/report.result.tts.txt",
    }
    assert saved_event["context"]["tts_text_path"] == "/tmp/report.result.tts.txt"


def test_run_document_processing_runs_audiobook_postprocess_without_mutating_base_docx_branch():
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    generated_calls = []
    artifact_calls = {}

    def generate_markdown_block(**kwargs):
        generated_calls.append(dict(kwargs))
        if kwargs["system_prompt"] == "system:translate":
            return f"TRANSLATED::{kwargs['target_text']}"
        return f"# Narration\n\n[thoughtful] {kwargs['target_text']}"

    def write_ui_result_artifacts(**kwargs):
        artifact_calls["kwargs"] = dict(kwargs)
        return {
            "markdown_path": "/tmp/report.result.md",
            "docx_path": "/tmp/report.result.docx",
            "tts_text_path": "/tmp/report.result.tts.txt",
        }

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {
                "target_text": "Chapter one text",
                "context_before": "",
                "context_after": "Chapter two text",
                "target_chars": 16,
                "context_chars": 16,
                "narration_include": True,
            },
            {
                "target_text": "Index tail",
                "context_before": "Chapter two text",
                "context_after": "",
                "target_chars": 10,
                "context_chars": 16,
                "narration_include": False,
            },
            {
                "target_text": "Chapter two text",
                "context_before": "Chapter one text",
                "context_after": "",
                "target_chars": 16,
                "context_chars": 16,
                "narration_include": True,
            },
        ],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={
            "audiobook_postprocess_enabled": True,
            "audiobook_model": "gpt-5.4-audio",
            "chunk_size": 20,
            "editorial_intensity_default": "literary",
        },
        model="gpt-5.4-translate",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "TRANSLATED::Chapter one text\n\nTRANSLATED::Index tail\n\nTRANSLATED::Chapter two text"
    assert runtime["state"]["latest_docx_bytes"] == runtime["state"]["latest_markdown"].encode("utf-8")
    narration_text = runtime["state"]["latest_narration_text"]
    assert narration_text is not None
    assert "TRANSLATED::Chapter one text" in narration_text
    assert "TRANSLATED::Chapter two text" in narration_text
    assert "TRANSLATED::Index tail" not in narration_text
    assert narration_text.count("[thoughtful]") == 1
    assert artifact_calls["kwargs"]["markdown_text"] == runtime["state"]["latest_markdown"]
    assert artifact_calls["kwargs"]["docx_bytes"] == runtime["state"]["latest_docx_bytes"]
    assert artifact_calls["kwargs"]["narration_text"] == narration_text

    assert [call["model"] for call in generated_calls] == [
        "gpt-5.4-translate",
        "gpt-5.4-translate",
        "gpt-5.4-translate",
        "gpt-5.4-audio",
    ]
    assert [call["target_text"] for call in generated_calls[3:]] == [
        "TRANSLATED::Chapter one text\n\nTRANSLATED::Chapter two text",
    ]
    assert generated_calls[3]["context_before"] == ""
    assert generated_calls[3]["context_after"] == ""

    info_events = [event for event in events if event["level"] == logging.INFO]
    saved_event = next(event for event in info_events if event["event_id"] == "ui_audiobook_artifact_saved")
    assert saved_event["context"]["mode"] == "postprocess"
    assert saved_event["context"]["filename"] == "report.docx"
    assert saved_event["context"]["artifact_paths"] == {
        "markdown_path": "/tmp/report.result.md",
        "docx_path": "/tmp/report.result.docx",
        "tts_text_path": "/tmp/report.result.tts.txt",
    }
    postprocess_started = [event for event in info_events if event["event_id"] == "audiobook_postprocess_chunk_started"]
    postprocess_completed = [event for event in info_events if event["event_id"] == "audiobook_postprocess_chunk_completed"]
    assert len(postprocess_started) == 1
    assert len(postprocess_completed) == 1
    assert all(event["context"]["operation"] == "audiobook" for event in postprocess_started)
    assert all(event["context"]["pass"] == "postprocess" for event in postprocess_started)
    completed_event = next(event for event in info_events if event["event_id"] == "processing_completed")
    assert completed_event["context"]["audiobook_postprocess_enabled"] is True


def test_run_document_processing_preserves_base_result_when_audiobook_postprocess_fails():
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    artifact_calls = {}

    def generate_markdown_block(**kwargs):
        if kwargs["system_prompt"] == "system:audiobook":
            raise RuntimeError("postprocess exploded")
        return "edited"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0, "narration_include": True}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"audiobook_postprocess_enabled": True, "audiobook_model": "gpt-5.4-audio"},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="edit",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=lambda **kwargs: artifact_calls.setdefault("kwargs", dict(kwargs)) or {"markdown_path": "/tmp/report.result.md", "docx_path": "/tmp/report.result.docx"},
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "edited"
    assert runtime["state"]["latest_docx_bytes"] == b"edited"
    assert runtime["state"]["latest_narration_text"] is None
    assert "narration_text" not in artifact_calls["kwargs"]
    warning_events = [event for event in events if event["level"] == logging.WARNING]
    assert any(event["event_id"] == "audiobook_postprocess_failed_base_result_preserved" for event in warning_events)


def test_run_document_processing_applies_reader_cleanup_and_saves_raw_markdown_report_artifacts(tmp_path: Path):
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    artifact_calls = {}
    converted_markdown_inputs = []

    def generate_markdown_block(**kwargs):
        if kwargs["system_prompt"].startswith("You are cleaning translated book Markdown"):
            payload = json.loads(kwargs["target_text"])
            cleanup_operations = []
            for block in payload["blocks"]:
                if block["text"] == "Header":
                    cleanup_operations.append(
                        {
                            "id": block["id"],
                            "text_hash": block["text_hash"],
                            "operation": "delete_block",
                            "reason": "repeated_running_header",
                            "confidence": "high",
                            "evidence_before": block["text"],
                            "expected_after_preview": "",
                            "safety_note": "Test fixture deletes only the repeated running header block.",
                        }
                    )
            return json.dumps({"cleanup_operations": cleanup_operations, "warnings": []}, ensure_ascii=False)
        return kwargs["target_text"]

    def write_ui_result_artifacts(**kwargs):
        artifact_calls["kwargs"] = dict(kwargs)
        return {
            "markdown_path": str(tmp_path / "final.result.md"),
            "docx_path": str(tmp_path / "final.result.docx"),
        }

    def convert_markdown_to_docx_bytes(markdown_text):
        converted_markdown_inputs.append(markdown_text)
        return markdown_text.encode("utf-8")

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"target_text": "Intro", "context_before": "", "context_after": "Header", "target_chars": 5, "context_chars": 6, "narration_include": True},
            {"target_text": "Header", "context_before": "Intro", "context_after": "Body paragraph", "target_chars": 6, "context_chars": 19, "narration_include": True},
            {"target_text": "Body paragraph", "context_before": "Header", "context_after": "Header", "target_chars": 14, "context_chars": 12, "narration_include": True},
            {"target_text": "Header", "context_before": "Body paragraph", "context_after": "Outro", "target_chars": 6, "context_chars": 19, "narration_include": True},
            {"target_text": "Outro", "context_before": "Header", "context_after": "", "target_chars": 5, "context_chars": 6, "narration_include": True},
        ],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={
            "reader_cleanup_enabled": True,
            "reader_cleanup_policy": "advisory",
            "reader_cleanup_chunk_size": 50,
            "reader_cleanup_keep_toc": True,
            "reader_cleanup_max_delete_block_ratio": 0.8,
            "reader_cleanup_max_delete_char_ratio": 0.8,
        },
        model="gpt-5.4-translate",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "Intro\n\nBody paragraph\n\nOutro"
    assert runtime["state"]["latest_docx_bytes"] == b"Intro\n\nBody paragraph\n\nOutro"
    assert converted_markdown_inputs == ["Intro\n\nBody paragraph\n\nOutro"]
    assert artifact_calls["kwargs"]["markdown_text"] == "Intro\n\nBody paragraph\n\nOutro"
    info_events = [event for event in events if event["level"] == logging.INFO]
    saved_event = next(event for event in info_events if event["event_id"] == "ui_result_artifacts_saved")
    assert "reader_cleanup_raw_markdown_path" in saved_event["context"]["artifact_paths"]
    assert "reader_cleanup_report_path" in saved_event["context"]["artifact_paths"]
    cleanup_event = next(event for event in info_events if event["event_id"] == "reader_cleanup_applied")
    assert cleanup_event["context"]["accepted_delete_block_count"] == 2


def test_run_document_processing_records_pre_cleanup_formatting_baseline_without_extra_docx_build(
    tmp_path: Path,
    monkeypatch,
):
    runtime = _build_runtime_capture()
    converted_markdown_inputs = []
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    def generate_markdown_block(**kwargs):
        if kwargs["system_prompt"].startswith("You are cleaning translated book Markdown"):
            payload = json.loads(kwargs["target_text"])
            return json.dumps(
                {
                    "cleanup_operations": [
                        {
                            "id": block["id"],
                            "text_hash": block["text_hash"],
                            "operation": "delete_block",
                            "reason": "repeated_running_header",
                            "confidence": "high",
                            "evidence_before": "Header",
                            "expected_after_preview": "",
                            "safety_note": "Test fixture deletes only the repeated running header block.",
                        }
                        for block in payload["blocks"]
                        if block["text"] == "Header"
                    ],
                    "warnings": [],
                },
                ensure_ascii=False,
            )
        return kwargs["target_text"]

    def convert_markdown_to_docx_bytes(markdown_text):
        converted_markdown_inputs.append(markdown_text)
        return markdown_text.encode("utf-8")

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"target_text": "Intro", "context_before": "", "context_after": "Header", "target_chars": 5, "context_chars": 6, "narration_include": True},
            {"target_text": "Header", "context_before": "Intro", "context_after": "Body", "target_chars": 6, "context_chars": 4, "narration_include": True},
            {"target_text": "Body", "context_before": "Header", "context_after": "Header", "target_chars": 4, "context_chars": 12, "narration_include": True},
            {"target_text": "Header", "context_before": "Body", "context_after": "Outro", "target_chars": 6, "context_chars": 9, "narration_include": True},
            {"target_text": "Outro", "context_before": "Header", "context_after": "", "target_chars": 5, "context_chars": 6, "narration_include": True},
        ],
        source_paragraphs=[
            ParagraphUnit(text="Intro", role="body", paragraph_id="p0001"),
            ParagraphUnit(text="Header", role="body", paragraph_id="p0002"),
            ParagraphUnit(text="Body", role="body", paragraph_id="p0003"),
            ParagraphUnit(text="Header", role="body", paragraph_id="p0004"),
            ParagraphUnit(text="Outro", role="body", paragraph_id="p0005"),
        ],
        image_assets=[],
        image_mode="safe",
        app_config={
            "reader_cleanup_enabled": True,
            "reader_cleanup_policy": "advisory",
            "reader_cleanup_chunk_size": 50,
            "reader_cleanup_max_delete_block_ratio": 0.8,
            "reader_cleanup_max_delete_char_ratio": 0.8,
        },
        model="gpt-5.4-translate",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=lambda **kwargs: {
            "markdown_path": str(tmp_path / "final.result.md"),
            "docx_path": str(tmp_path / "final.result.docx"),
        },
    )

    assert result == "succeeded"
    assert converted_markdown_inputs == ["Intro\n\nBody\n\nOutro"]
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    quality_payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert quality_payload["formatting_diagnostics_artifact_count"] == 0
    assert quality_payload["pre_cleanup_formatting_baseline"] == {
        "stage": "pre_reader_cleanup_rebuild_identity",
        "classification": "diagnostic_only",
        "mapping_basis": "ordered_exact_text_rebuild_sidecar",
        "metric_scope": "sidecar_only_proxy",
        "status": "missing_registry",
        "source_count": 0,
        "target_count": 5,
        "mapped_count": 0,
        "unmapped_source_count": 0,
        "unmapped_target_count": 5,
        "unmapped_source_ids": [],
        "unmapped_target_indexes": [0, 1, 2, 3, 4],
    }


def test_run_document_processing_fails_on_empty_lazy_docx_after_reader_cleanup_noop():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0, "narration_include": True}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"reader_cleanup_enabled": True, "reader_cleanup_policy": "advisory"},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{code}:{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)
        if kwargs["system_prompt"].startswith("You are cleaning translated book Markdown")
        else "block",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: b"",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "failed"
    assert "empty_docx_bytes" in runtime["state"]["last_error"]
    assert runtime["state"]["latest_docx_bytes"] is None


def test_run_document_processing_fails_on_empty_lazy_docx_before_cleanup_quality_gate():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0, "narration_include": True}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={
            "reader_cleanup_enabled": True,
            "reader_cleanup_policy": "advisory",
            "translation_output_quality_gate_policy": "strict",
        },
        model="gpt-5.4",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{code}:{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Заключение……29 Введение",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: b"",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "failed"
    assert "empty_docx_bytes" in runtime["state"]["last_error"]
    assert "translation_quality_gate_failed" not in runtime["state"]["last_error"]


def test_run_document_processing_reader_cleanup_uses_exact_raw_markdown_for_sidecar_and_hashes(tmp_path: Path):
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    artifact_calls = {}
    cleanup_payloads = []
    noisy_block = "This page intentionally left blank Chapter Nine STRATEGIES FOR NGO S"
    raw_markdown = f"Intro\n\n{noisy_block}\n\n{noisy_block}\n\nOutro"
    display_markdown = document_pipeline_late_phases._normalize_final_markdown_for_runtime_display(raw_markdown)

    assert display_markdown != raw_markdown
    assert len(build_cleanup_blocks(raw_markdown)) == 4
    assert len(build_cleanup_blocks(display_markdown)) == 6

    def generate_markdown_block(**kwargs):
        if kwargs["system_prompt"].startswith("You are cleaning translated book Markdown"):
            payload = json.loads(kwargs["target_text"])
            cleanup_payloads.append(payload)
            cleanup_operations = []
            for block in payload["blocks"]:
                if block["text"] == noisy_block:
                    cleanup_operations.append(
                        {
                            "id": block["id"],
                            "text_hash": block["text_hash"],
                            "operation": "delete_block",
                            "reason": "repeated_running_header",
                            "confidence": "high",
                            "evidence_before": block["text"],
                            "expected_after_preview": "",
                            "safety_note": "Test fixture deletes only exact repeated running-header blocks.",
                        }
                    )
            return json.dumps({"cleanup_operations": cleanup_operations, "warnings": []}, ensure_ascii=False)
        return kwargs["target_text"]

    def write_ui_result_artifacts(**kwargs):
        artifact_calls["kwargs"] = dict(kwargs)
        return {
            "markdown_path": str(tmp_path / "final.result.md"),
            "docx_path": str(tmp_path / "final.result.docx"),
        }

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"target_text": "Intro", "context_before": "", "context_after": noisy_block, "target_chars": 5, "context_chars": len(noisy_block), "narration_include": True},
            {"target_text": noisy_block, "context_before": "Intro", "context_after": noisy_block, "target_chars": len(noisy_block), "context_chars": 10, "narration_include": True},
            {"target_text": noisy_block, "context_before": noisy_block, "context_after": "Outro", "target_chars": len(noisy_block), "context_chars": 10, "narration_include": True},
            {"target_text": "Outro", "context_before": noisy_block, "context_after": "", "target_chars": 5, "context_chars": len(noisy_block), "narration_include": True},
        ],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={
            "reader_cleanup_enabled": True,
            "reader_cleanup_policy": "advisory",
            "reader_cleanup_chunk_size": 500,
            "reader_cleanup_keep_toc": True,
            "reader_cleanup_max_delete_block_ratio": 0.8,
            "reader_cleanup_max_delete_char_ratio": 0.95,
        },
        model="gpt-5.4-translate",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "Intro\n\nOutro"
    assert artifact_calls["kwargs"]["markdown_text"] == "Intro\n\nOutro"
    assert cleanup_payloads
    assert [block["text"] for block in cleanup_payloads[0]["blocks"]].count(noisy_block) == 2

    raw_sidecar_path = tmp_path / "final.raw.result.md"
    report_path = tmp_path / "final.reader_cleanup_report.json"
    assert raw_sidecar_path.read_text(encoding="utf-8") == raw_markdown
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    expected_hashes = {block.text_hash for block in build_cleanup_blocks(raw_markdown) if block.text == noisy_block}
    accepted_hashes = {entry["text_hash"] for entry in report_payload["accepted_delete_blocks"]}
    assert report_payload["stats"]["accepted_delete_block_count"] == 2
    assert accepted_hashes == expected_hashes

    info_events = [event for event in events if event["level"] == logging.INFO]
    cleanup_event = next(event for event in info_events if event["event_id"] == "reader_cleanup_applied")
    assert cleanup_event["context"]["proposed_delete_block_count"] == 2


def test_run_document_processing_reader_cleanup_applies_runtime_anchor_repair(tmp_path: Path):
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    artifact_calls = {}
    cleanup_payloads = []
    target = "КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь."
    raw_markdown = f"Intro\n\n{target}\n\nOutro"
    blocks = build_cleanup_blocks(raw_markdown)

    def generate_markdown_block(**kwargs):
        if kwargs["system_prompt"].startswith("You are cleaning translated book Markdown"):
            payload = json.loads(kwargs["target_text"])
            cleanup_payloads.append(payload)
            if payload.get("pass_name") == "anchor_repair":
                target_block = next(block for block in payload["blocks"] if block["id"] == blocks[1].block_id)
                return json.dumps(
                    {
                        "cleanup_operations": [
                            {
                                "id": target_block["id"],
                                "text_hash": target_block["text_hash"],
                                "operation": "normalize_heading_boundary",
                                "reason": "page_furniture_heading",
                                "confidence": "high",
                                "evidence_before": target_block["text"],
                                "expected_after_preview": "КАК ЭТО РАБОТАЕТ:\n\nМестные органы власти могут помочь.",
                                "safety_note": "Split only the exact heading/body boundary from a verifier anchor.",
                                "heading_substring": "КАК ЭТО РАБОТАЕТ:",
                                "body_substring": "Местные органы власти могут помочь.",
                            }
                        ],
                        "warnings": [],
                    },
                    ensure_ascii=False,
                )
            return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)
        return kwargs["target_text"]

    def write_ui_result_artifacts(**kwargs):
        artifact_calls["kwargs"] = dict(kwargs)
        return {
            "markdown_path": str(tmp_path / "final.result.md"),
            "docx_path": str(tmp_path / "final.result.docx"),
        }

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"target_text": "Intro", "context_before": "", "context_after": target, "target_chars": 5, "context_chars": len(target), "narration_include": True},
            {"target_text": target, "context_before": "Intro", "context_after": "Outro", "target_chars": len(target), "context_chars": 10, "narration_include": True},
            {"target_text": "Outro", "context_before": target, "context_after": "", "target_chars": 5, "context_chars": len(target), "narration_include": True},
        ],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={
            "reader_cleanup_enabled": True,
            "reader_cleanup_policy": "advisory",
            "reader_cleanup_chunk_size": 500,
            "reader_cleanup_keep_toc": True,
            "reader_cleanup_anchor_repair_enabled": True,
            "reader_cleanup_anchor_targets": [
                {
                    "anchor_id": "runtime-anchor-1",
                    "category": "heading_fused_with_body",
                    "block_id": blocks[1].block_id,
                    "line_ref": "cleaned_markdown:3",
                    "snippet": target,
                }
            ],
        },
        model="gpt-5.4-translate",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "Intro\n\nКАК ЭТО РАБОТАЕТ:\n\nМестные органы власти могут помочь.\n\nOutro"
    assert artifact_calls["kwargs"]["markdown_text"] == runtime["state"]["latest_markdown"]
    assert any(payload.get("pass_name") == "anchor_repair" for payload in cleanup_payloads)

    report_path = tmp_path / "final.reader_cleanup_report.json"
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    anchor_pass = report_payload["passes"]["anchor_repair_pass"]
    assert anchor_pass["selected_anchor_count"] == 1
    assert anchor_pass["stats"]["accepted_cleanup_operation_count"] == 1
    assert report_payload["stats"]["accepted_cleanup_operation_count"] == 1

    info_events = [event for event in events if event["level"] == logging.INFO]
    anchor_events = [
        event for event in info_events if event["context"].get("pass") == "anchor_repair"
    ]
    assert any(event["event_id"] == "reader_cleanup_chunk_started" for event in anchor_events)
    cleanup_event = next(event for event in info_events if event["event_id"] == "reader_cleanup_applied")
    assert cleanup_event["context"]["accepted_cleanup_operation_count"] == 1


def test_run_document_processing_preserves_base_result_when_reader_cleanup_fails():
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    artifact_calls = {}
    converted_markdown_inputs = []

    def generate_markdown_block(**kwargs):
        if kwargs["system_prompt"].startswith("You are cleaning translated book Markdown"):
            raise RuntimeError("cleanup exploded")
        return kwargs["target_text"]

    def write_ui_result_artifacts(**kwargs):
        artifact_calls["kwargs"] = dict(kwargs)
        return {"markdown_path": "/tmp/report.result.md", "docx_path": "/tmp/report.result.docx"}

    def convert_markdown_to_docx_bytes(markdown_text):
        converted_markdown_inputs.append(markdown_text)
        return markdown_text.encode("utf-8")

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0, "narration_include": True}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"reader_cleanup_enabled": True, "reader_cleanup_policy": "advisory"},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "block"
    assert runtime["state"]["latest_docx_bytes"] == b"block"
    assert converted_markdown_inputs == ["block"]
    assert artifact_calls["kwargs"]["markdown_text"] == "block"
    info_events = [event for event in events if event["level"] == logging.INFO]
    noop_event = next(event for event in info_events if event["event_id"] == "reader_cleanup_noop")
    assert any("reader_cleanup_chunk_failed" in warning for warning in noop_event["context"]["warnings"])


def test_run_document_processing_reader_cleanup_rebuild_preserves_images():
    reinsert_calls = []

    class FakeImageAsset:
        image_id = "img-1"

        def update_pipeline_metadata(self, **values):
            return None

    def reinsert_inline_images(docx_bytes, image_assets):
        reinsert_calls.append([asset.image_id for asset in image_assets])
        return docx_bytes + f"|images={len(image_assets)}".encode("utf-8")

    rebuilt = document_pipeline_late_phases._rebuild_docx_for_markdown(
        markdown_text="Intro\n\nBody\n\nOutro",
        context=SimpleNamespace(source_paragraphs=[]),
        dependencies=SimpleNamespace(
            convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
            preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
            reinsert_inline_images=reinsert_inline_images,
        ),
        state=SimpleNamespace(generated_paragraph_registry=[]),
        processed_image_assets=[FakeImageAsset()],
    )

    assert rebuilt == b"Intro\n\nBody\n\nOutro|images=1"
    assert reinsert_calls
    assert reinsert_calls[-1] == ["img-1"]


def test_reader_cleanup_docx_rebuild_markdown_restores_missing_image_placeholder_without_display_regression():
    rebuilt_markdown = document_pipeline_late_phases._build_docx_rebuild_markdown_after_reader_cleanup(
        raw_markdown="Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph\n\nOutro",
        cleaned_markdown="Intro\n\nBody paragraph\n\nOutro",
        accepted_delete_block_ids=[],
    )

    assert rebuilt_markdown == "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph\n\nOutro"


def test_reader_cleanup_docx_rebuild_markdown_does_not_duplicate_existing_image_placeholder():
    rebuilt_markdown = document_pipeline_late_phases._build_docx_rebuild_markdown_after_reader_cleanup(
        raw_markdown="Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph",
        cleaned_markdown="Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph",
        accepted_delete_block_ids=[],
    )

    assert rebuilt_markdown.count("[[DOCX_IMAGE_img_001]]") == 1
    assert rebuilt_markdown == "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph"


def test_reader_cleanup_docx_rebuild_markdown_preserves_consecutive_image_placeholder_order():
    rebuilt_markdown = document_pipeline_late_phases._build_docx_rebuild_markdown_after_reader_cleanup(
        raw_markdown="Intro\n\n[[DOCX_IMAGE_img_001]]\n\n[[DOCX_IMAGE_img_002]]\n\nBody paragraph",
        cleaned_markdown="Intro\n\nBody paragraph",
        accepted_delete_block_ids=[],
    )

    assert rebuilt_markdown == "Intro\n\n[[DOCX_IMAGE_img_001]]\n\n[[DOCX_IMAGE_img_002]]\n\nBody paragraph"


def test_reader_cleanup_docx_rebuild_markdown_anchors_missing_image_placeholder_by_paragraph_id():
    rebuilt_markdown = document_pipeline_late_phases._build_docx_rebuild_markdown_after_reader_cleanup(
        raw_markdown="Intro before cleanup\n\n[[DOCX_IMAGE_img_001]]\n\nBody before cleanup",
        cleaned_markdown="Intro after cleanup\n\nBody after cleanup",
        accepted_delete_block_ids=[],
        cleanup_block_metadata_by_index={
            0: {"paragraph_id": "p0001"},
            2: {"paragraph_id": "p0002"},
        },
        generated_paragraph_registry=[
            {"paragraph_id": "p0001", "text": "Intro after cleanup"},
            {"paragraph_id": "p0002", "text": "Body after cleanup"},
        ],
    )

    assert rebuilt_markdown == "Intro after cleanup\n\n[[DOCX_IMAGE_img_001]]\n\nBody after cleanup"


def test_run_document_processing_reader_cleanup_preserves_docx_image_anchor_when_markdown_cleanup_deletes_placeholder():
    runtime = _build_runtime_capture()
    artifact_calls = {}
    converted_markdown_inputs = []

    class FakeImageAsset:
        image_id = "img-1"

        def update_pipeline_metadata(self, **values):
            return None

    def generate_markdown_block(**kwargs):
        if kwargs["system_prompt"].startswith("You are cleaning translated book Markdown"):
            payload = json.loads(kwargs["target_text"])
            cleanup_operations = [
                {
                    "id": block["id"],
                    "text_hash": block["text_hash"],
                    "operation": "delete_block",
                    "reason": "extraction_artifact",
                    "confidence": "high",
                    "evidence_before": block["text"],
                    "expected_after_preview": "",
                    "safety_note": "Test fixture deletes only the exact placeholder block from display Markdown.",
                }
                for block in payload["blocks"]
                if block["text"] == "[[DOCX_IMAGE_img_001]]"
            ]
            return json.dumps({"cleanup_operations": cleanup_operations, "warnings": []}, ensure_ascii=False)
        return kwargs["target_text"]

    def convert_markdown_to_docx_bytes(markdown_text):
        converted_markdown_inputs.append(markdown_text)
        return markdown_text.encode("utf-8")

    def write_ui_result_artifacts(**kwargs):
        artifact_calls["kwargs"] = dict(kwargs)
        return {"markdown_path": "/tmp/report.result.md", "docx_path": "/tmp/report.result.docx"}

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"target_text": "Intro", "context_before": "", "context_after": "[[DOCX_IMAGE_img_001]]", "target_chars": 5, "context_chars": 22, "narration_include": True},
            {"target_text": "[[DOCX_IMAGE_img_001]]", "context_before": "Intro", "context_after": "Body paragraph", "target_chars": 22, "context_chars": 19, "narration_include": True},
            {"target_text": "Body paragraph", "context_before": "[[DOCX_IMAGE_img_001]]", "context_after": "Outro", "target_chars": 14, "context_chars": 27, "narration_include": True},
            {"target_text": "Outro", "context_before": "Body paragraph", "context_after": "", "target_chars": 5, "context_chars": 14, "narration_include": True},
        ],
        source_paragraphs=[],
        image_assets=[FakeImageAsset()],
        image_mode="safe",
        app_config={
            "reader_cleanup_enabled": True,
            "reader_cleanup_policy": "advisory",
            "reader_cleanup_chunk_size": 500,
            "reader_cleanup_max_delete_block_ratio": 0.8,
            "reader_cleanup_max_delete_char_ratio": 0.8,
        },
        model="gpt-5.4-translate",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [FakeImageAsset()],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes + f"|images={len(image_assets)}".encode("utf-8"),
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "Intro\n\nBody paragraph\n\nOutro"
    assert artifact_calls["kwargs"]["markdown_text"] == "Intro\n\nBody paragraph\n\nOutro"
    assert converted_markdown_inputs[-1] == "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph\n\nOutro"
    assert runtime["state"]["latest_docx_bytes"] == b"Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph\n\nOutro|images=1"


def test_run_document_processing_reader_cleanup_strict_failure_preserves_base_result(tmp_path: Path):
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()
    artifact_calls = {}

    def generate_markdown_block(**kwargs):
        if kwargs["system_prompt"].startswith("You are cleaning translated book Markdown"):
            raise RuntimeError("cleanup exploded")
        return kwargs["target_text"]

    def write_ui_result_artifacts(**kwargs):
        artifact_calls["kwargs"] = dict(kwargs)
        return {
            "markdown_path": str(tmp_path / "report.result.md"),
            "docx_path": str(tmp_path / "report.result.docx"),
        }

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0, "narration_include": True}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"reader_cleanup_enabled": True, "reader_cleanup_policy": "strict"},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "block"
    assert artifact_calls["kwargs"]["markdown_text"] == "block"
    assert runtime["state"]["latest_result_notice"] == {
        "level": "warning",
        "message": "Reader cleanup strict stage failed; preserved the raw translated result without cleanup.",
    }
    warning_events = [event for event in events if event["level"] == logging.WARNING]
    assert any(event["event_id"] == "reader_cleanup_strict_failed_base_result_preserved" for event in warning_events)
    raw_sidecar_path = tmp_path / "report.raw.result.md"
    report_path = tmp_path / "report.reader_cleanup_report.json"
    assert raw_sidecar_path.read_text(encoding="utf-8") == "block"
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_payload["stage_status"] == "failed_preserved_base_result"
    assert report_payload["failure"]["kind"] == "chunk_failed"


def test_run_document_processing_fails_standalone_audiobook_with_invalid_narration_artifact():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0, "narration_include": True}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="audiobook",
        source_language="auto",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "[angry] text with DOI:10.1000/xyz",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "failed"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["latest_narration_text"] is None
    assert runtime["finalize"][-1][0] == "Ошибка проверки narration"


def test_run_document_processing_clears_stale_narration_on_docx_build_failure():
    runtime = _build_runtime_capture()
    runtime["state"]["latest_narration_text"] = "stale narration"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="edit",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "edited",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: (_ for _ in ()).throw(RuntimeError("docx exploded")),
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "failed"
    assert runtime["state"]["latest_narration_text"] is None


def test_run_document_processing_does_not_run_translation_second_pass_for_audiobook_even_if_flag_is_stale():
    runtime = _build_runtime_capture()
    generated_calls = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0, "narration_include": True}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"translation_second_pass_enabled": True},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="audiobook",
        source_language="auto",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generated_calls.append(dict(kwargs)) or "[thoughtful] edited",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "succeeded"
    assert len(generated_calls) == 1


def test_run_document_processing_logs_effective_second_pass_flags_for_standalone_audiobook():
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0, "narration_include": True}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={
            "translation_second_pass_enabled": True,
            "audiobook_postprocess_enabled": True,
        },
        model="gpt-5.4",
        max_retries=1,
        processing_operation="audiobook",
        source_language="auto",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "[thoughtful] edited",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "succeeded"
    info_events = [event for event in events if event["level"] == logging.INFO]
    started_event = next(event for event in info_events if event["event_id"] == "processing_started")
    summary_event = next(event for event in info_events if event["event_id"] == "block_plan_summary")
    completed_event = next(event for event in info_events if event["event_id"] == "processing_completed")

    assert started_event["context"]["translation_second_pass_enabled"] is False
    assert summary_event["context"]["translation_second_pass_enabled"] is False
    assert completed_event["context"]["translation_second_pass_enabled"] is False
    assert completed_event["context"]["audiobook_postprocess_enabled"] is False


def test_run_document_processing_uses_base_model_for_audiobook_postprocess_when_configured_model_blank():
    runtime = _build_runtime_capture()
    generated_calls = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "block",
            "context_before": "",
            "context_after": "",
            "target_chars": 5,
            "context_chars": 0,
            "narration_include": True,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={
            "audiobook_postprocess_enabled": True,
            "audiobook_model": "   ",
            "chunk_size": 6000,
        },
        model="gpt-5.4-base",
        max_retries=1,
        processing_operation="edit",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: "system:audiobook" if kwargs["operation"] == "audiobook" else "system:edit",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generated_calls.append(dict(kwargs)) or ("edited" if len(generated_calls) == 1 else "[thoughtful] edited"),
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert len(generated_calls) == 2
    assert generated_calls[1]["model"] == "gpt-5.4-base"
    assert runtime["state"]["latest_narration_text"] == "[thoughtful] edited"


def test_resolve_audiobook_postprocess_chunk_size_clamps_to_config_minimum():
    context = type("Context", (), {"app_config": {"chunk_size": 1200}})()

    assert document_pipeline_late_phases._resolve_audiobook_postprocess_chunk_size(context=context) == 3000


def test_run_document_processing_does_not_fail_when_ui_result_artifact_save_fails():
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()

    result = _run_processing(
        runtime,
        log_event=log_event,
        write_ui_result_artifacts=lambda **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    assert result == "succeeded"
    warning_events = [event for event in events if event["level"] == logging.WARNING]
    failed_event = next(event for event in warning_events if event["event_id"] == "ui_result_artifacts_save_failed")
    assert failed_event["context"]["error_message"] == "disk full"


def test_resolve_system_prompt_does_not_mask_internal_type_errors():
    def broken_loader(
        *,
        operation: str = "edit",
        source_language: str = "en",
        target_language: str = "ru",
        editorial_intensity: str = "literary",
        prompt_variant: str = "default",
        translation_domain: str = "general",
        source_text: str = "",
    ):
        raise TypeError("broken template")

    with pytest.raises(TypeError, match="broken template"):
        document_pipeline._resolve_system_prompt(
            broken_loader,
            operation="translate",
            source_language="en",
            target_language="de",
            editorial_intensity="literary",
        )


def test_resolve_system_prompt_falls_back_for_legacy_loader_without_editorial_intensity():
    captured = {}

    def legacy_loader(*, operation: str = "edit", source_language: str = "en", target_language: str = "ru"):
        captured["prompt"] = {
            "operation": operation,
            "source_language": source_language,
            "target_language": target_language,
        }
        return "system"

    resolved = document_pipeline._resolve_system_prompt(
        legacy_loader,  # type: ignore[arg-type]  # intentional: testing backward-compat fallback for pre-prompt_variant loaders
        operation="translate",
        source_language="en",
        target_language="de",
        editorial_intensity="conservative",
        translation_domain="theology",
        source_text="Great Tribulation",
    )

    assert resolved == "system"
    assert captured["prompt"] == {
        "operation": "translate",
        "source_language": "en",
        "target_language": "de",
    }


def test_run_document_processing_runs_second_pass_only_when_enabled():
    runtime = _build_runtime_capture()
    prompts = []
    generated_calls = []
    events, log_event = _capture_log_events()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "before", "context_after": "after", "target_chars": 5, "context_chars": 10}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={
            "editorial_intensity_default": "conservative",
            "translation_domain_default": "theology",
            "translation_domain_instructions": "ДОМЕН ПЕРЕВОДА: богословие / эсхатология.",
            "translation_second_pass_enabled": True,
            "translation_second_pass_model": "gpt-5.4",
        },
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="de",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: prompts.append(dict(kwargs)) or f"system:{kwargs.get('prompt_variant', 'default')}",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generated_calls.append(dict(kwargs)) or ("перевод" if len(generated_calls) == 1 else "полировка"),
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert len(prompts) == 2
    assert prompts[0]["prompt_variant"] == "default"
    assert prompts[1]["prompt_variant"] == "literary_polish"
    assert prompts[0]["translation_domain"] == "theology"
    assert "богословие" in prompts[0]["source_text"]
    assert prompts[1]["translation_domain"] == "theology"
    assert generated_calls[0]["model"] == "gpt-5.4-mini"
    assert generated_calls[0]["target_text"] == "block"
    assert generated_calls[0]["context_before"] == "before"
    assert generated_calls[1]["model"] == "gpt-5.4"
    assert generated_calls[1]["target_text"] == "перевод"
    assert generated_calls[1]["context_before"] == ""
    assert runtime["state"]["latest_markdown"] == "полировка"
    info_events = [event for event in events if event["level"] == logging.INFO]
    assert any(event["event_id"] == "block_second_pass_started" for event in info_events)
    completed_event = next(event for event in info_events if event["event_id"] == "processing_completed")
    assert completed_event["context"]["translation_second_pass_enabled"] is True


def test_run_document_processing_merges_document_context_prompt_into_system_prompt_source():
    runtime = _build_runtime_capture()
    prompts = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={
            "translation_domain_default": "theology",
            "translation_domain_instructions": "ДОМЕН ПЕРЕВОДА: богословие / эсхатология.",
        },
        document_context_prompt="КОНТЕКСТ ДОКУМЕНТА: Chapter 1; Great Tribulation -> die grosse Trubsal",
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="de",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: prompts.append(dict(kwargs)) or "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "translated",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert "ДОМЕН ПЕРЕВОДА" in prompts[0]["source_text"]
    assert "КОНТЕКСТ ДОКУМЕНТА" in prompts[0]["source_text"]
    assert "Great Tribulation -> die grosse Trubsal" in prompts[0]["source_text"]


def test_run_document_processing_appends_block_segment_focus_to_generation_prompt():
    runtime = _build_runtime_capture()
    generated_calls = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {
                "segment_id": "seg_0002",
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
            }
        ],
        document_segments=[
            SimpleNamespace(segment_id="seg_0001", ordinal=1, level=1, structural_role="chapter", title="Chapter 1"),
            SimpleNamespace(segment_id="seg_0002", ordinal=2, level=1, structural_role="chapter", title="Chapter 2"),
            SimpleNamespace(segment_id="seg_0003", ordinal=3, level=1, structural_role="chapter", title="Chapter 3"),
        ],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="de",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generated_calls.append(dict(kwargs)) or "translated",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert "ТЕКУЩИЙ БЛОК ДОКУМЕНТА" in generated_calls[0]["system_prompt"]
    assert "Текущий сегмент: #2 | L1 | chapter | Chapter 2" in generated_calls[0]["system_prompt"]
    assert "Предыдущий сегмент: Chapter 1" in generated_calls[0]["system_prompt"]
    assert "Следующий сегмент: Chapter 3" in generated_calls[0]["system_prompt"]


def test_run_document_processing_appends_previous_completed_segment_summary_to_next_segment_prompt():
    runtime = _build_runtime_capture()
    generated_calls = []

    def generate_markdown_block(**kwargs):
        generated_calls.append(dict(kwargs))
        if kwargs["target_text"] == "chapter-one-block":
            return "Translated chapter one summary sentence. Additional translated detail for continuity."
        return "Translated chapter two body."

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {
                "segment_id": "seg_0001",
                "target_text": "chapter-one-block",
                "context_before": "",
                "context_after": "",
                "target_chars": 17,
                "context_chars": 0,
            },
            {
                "segment_id": "seg_0002",
                "target_text": "chapter-two-block",
                "context_before": "",
                "context_after": "",
                "target_chars": 17,
                "context_chars": 0,
            },
        ],
        document_segments=[
            SimpleNamespace(segment_id="seg_0001", ordinal=1, level=1, structural_role="chapter", title="Chapter 1"),
            SimpleNamespace(segment_id="seg_0002", ordinal=2, level=1, structural_role="chapter", title="Chapter 2"),
        ],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="de",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert len(generated_calls) == 2
    assert "СВОДКА ПРЕДЫДУЩЕГО ЗАВЕРШЁННОГО СЕГМЕНТА" in generated_calls[1]["system_prompt"]
    assert "Сегмент: Chapter 1" in generated_calls[1]["system_prompt"]
    assert "Translated chapter one summary sentence." in generated_calls[1]["system_prompt"]


def test_run_document_processing_skips_second_pass_outside_translate_mode():
    runtime = _build_runtime_capture()
    generated_calls = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "before", "context_after": "after", "target_chars": 5, "context_chars": 10}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"translation_second_pass_enabled": True},
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="edit",
        source_language="en",
        target_language="de",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generated_calls.append(dict(kwargs)) or "edited",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert len(generated_calls) == 1


def test_run_document_processing_fails_when_second_pass_raises():
    runtime = _build_runtime_capture()

    def generate_markdown_block(**kwargs):
        if kwargs["target_text"] == "перевод":
            raise RuntimeError("second pass exploded")
        return "перевод"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "before", "context_after": "after", "target_chars": 5, "context_chars": 10}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"translation_second_pass_enabled": True},
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="de",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "failed"
    assert "second pass exploded" in runtime["state"]["last_error"]


def test_run_document_processing_routes_toc_dominant_translate_block_through_toc_prompt_variant_and_retries():
    runtime = _build_runtime_capture()
    prompts = []
    generated_calls = []
    events, log_event = _capture_log_events()

    def generate_markdown_block(**kwargs):
        generated_calls.append(dict(kwargs))
        if len(generated_calls) == 1:
            return "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9"
        return "Содержание\n\nВведение ........ 1\n\nЗаключение ........ 9"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "job_kind": "passthrough",
            "target_text": "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9",
            "target_text_with_markers": "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9",
            "paragraph_ids": ["p0000", "p0001", "p0002"],
            "structural_roles": ["toc_header", "toc_entry", "toc_entry"],
            "toc_dominant": True,
            "toc_paragraph_count": 3,
            "paragraph_count": 3,
            "context_before": "",
            "context_after": "",
            "target_chars": 58,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"translation_domain_default": "theology", "translation_domain_instructions": "ДОМЕН ПЕРЕВОДА: богословие / эсхатология."},
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: prompts.append(dict(kwargs)) or f"system:{kwargs.get('prompt_variant', 'default')}",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert prompts[0]["prompt_variant"] == "toc_translate"
    assert prompts[0]["translation_domain"] == "theology"
    assert len(generated_calls) == 2
    assert runtime["state"]["latest_markdown"].startswith("Содержание")
    info_events = [event for event in events if event["level"] == logging.INFO]
    assert any(event["event_id"] == "toc_prompt_routing_selected" for event in info_events)
    warning_events = [event for event in events if event["level"] == logging.WARNING]
    assert any(event["event_id"] == "toc_validation_rejected" for event in warning_events)


def test_run_document_processing_uses_hardened_toc_retry_prompt_on_final_attempt():
    runtime = _build_runtime_capture()
    generated_calls = []

    def generate_markdown_block(**kwargs):
        generated_calls.append(dict(kwargs))
        if len(generated_calls) < 3:
            return "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9"
        return "Содержание\n\nВведение ........ 1\n\nЗаключение ........ 9"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "job_kind": "passthrough",
            "target_text": "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9",
            "target_text_with_markers": "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9",
            "paragraph_ids": ["p0000", "p0001", "p0002"],
            "structural_roles": ["toc_header", "toc_entry", "toc_entry"],
            "toc_dominant": True,
            "toc_paragraph_count": 3,
            "paragraph_count": 3,
            "context_before": "",
            "context_after": "",
            "target_chars": 58,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs.get('prompt_variant', 'default')}",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=generate_markdown_block,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert len(generated_calls) == 3
    assert "TOC retry hardening." in generated_calls[2]["system_prompt"]


def test_run_document_processing_routes_mixed_toc_dominant_translate_block_through_toc_prompt_variant():
    runtime = _build_runtime_capture()
    prompts = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "job_kind": "llm",
            "target_text": "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9\n\nNote on sources",
            "target_text_with_markers": "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9\n\nNote on sources",
            "paragraph_ids": ["p0000", "p0001", "p0002", "p0003"],
            "structural_roles": ["toc_header", "toc_entry", "toc_entry", "body"],
            "toc_dominant": True,
            "toc_paragraph_count": 3,
            "paragraph_count": 4,
            "context_before": "",
            "context_after": "",
            "target_chars": 75,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: prompts.append(dict(kwargs)) or f"system:{kwargs.get('prompt_variant', 'default')}",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Содержание\n\nВведение ........ 1\n\nЗаключение ........ 9\n\nПримечание к источникам",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert prompts[0]["prompt_variant"] == "toc_translate"
    assert "Примечание к источникам" in runtime["state"]["latest_markdown"]


def test_run_document_processing_fails_with_dedicated_toc_error_after_retry_budget_exhausted():
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "job_kind": "passthrough",
            "target_text": "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9",
            "target_text_with_markers": "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9",
            "paragraph_ids": ["p0000", "p0001", "p0002"],
            "structural_roles": ["toc_header", "toc_entry", "toc_entry"],
            "toc_dominant": True,
            "toc_paragraph_count": 3,
            "paragraph_count": 3,
            "context_before": "",
            "context_after": "",
            "target_chars": 58,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4-mini",
        max_retries=1,
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: "system",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "failed"
    assert "Ошибка обработки блока оглавления" in runtime["state"]["last_error"]
    assert runtime["activity"][-1] == "Блок 1: отклонён TOC validation после исчерпания retry budget."
    warning_events = [event for event in events if event["level"] == logging.WARNING]
    terminal_event = next(event for event in warning_events if event["event_id"] == "toc_validation_failed_terminal")
    assert terminal_event["context"]["retry_attempt"] == 2
    assert terminal_event["context"]["structural_roles"] == ["toc_header", "toc_entry", "toc_entry"]
    assert terminal_event["context"]["toc_paragraph_count"] == 3
    assert terminal_event["context"]["paragraph_count"] == 3


def test_run_document_processing_applies_semantic_output_normalization_before_image_reinsertion():
    runtime = _build_runtime_capture()
    call_order = []
    image_assets = [AssetStub("img_001")]

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[ParagraphStub()],
        image_assets=image_assets,
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: image_assets,
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: call_order.append("convert") or b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: call_order.append("preserve") or docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: call_order.append("reinsert") or docx_bytes,
    )

    assert result == "succeeded"
    assert call_order == ["convert", "preserve", "reinsert"]


def test_run_document_processing_surfaces_formatting_diagnostics_artifacts(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    diagnostics_dir = tmp_path / "formatting_diagnostics"
    monkeypatch.setattr(document_pipeline, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)

    def preserve_with_artifact(docx_bytes, paragraphs, generated_paragraph_registry=None):
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        (diagnostics_dir / "preserve_001.json").write_text(
            json.dumps(
                {
                    "stage": "preserve",
                    "source_count": 5,
                    "target_count": 4,
                    "mapped_count": 4,
                    "unmapped_source_ids": ["p0004"],
                    "unmapped_target_indexes": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return docx_bytes

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[ParagraphStub()],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=preserve_with_artifact,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "succeeded"
    assert runtime["activity"][-2] == "Сборка DOCX завершена; сохранена служебная диагностика форматирования."
    assert runtime["state"]["latest_result_notice"] == {
        "level": "info",
        "message": (
            "DOCX собран. Дополнительное восстановление форматирования было частично пропущено, "
            "потому что точное сопоставление абзацев нашлось не везде. Это нормально, когда модель объединяет, "
            "делит или переформулирует абзацы. Совпадение найдено для 4 из 5 исходных абзацев; "
            "без точного соответствия осталось 1."
        ),
    }
    assert all(entry["status"] != "INFO" for entry in runtime["log"])


def test_run_document_processing_warns_user_only_for_conflicting_formatting_diagnostics(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    diagnostics_dir = tmp_path / "formatting_diagnostics"
    monkeypatch.setattr(document_pipeline, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)

    def preserve_with_conflict_artifact(docx_bytes, paragraphs, generated_paragraph_registry=None):
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        (diagnostics_dir / "preserve_001.json").write_text(
            json.dumps(
                {
                    "stage": "preserve",
                    "source_count": 5,
                    "target_count": 5,
                    "mapped_count": 5,
                    "unmapped_source_ids": [],
                    "unmapped_target_indexes": [],
                    "caption_heading_conflicts": [
                        {"paragraph_id": "p0002", "target_heading_level": 2}
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return docx_bytes

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[ParagraphStub()],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=preserve_with_conflict_artifact,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "succeeded"
    assert runtime["activity"][-2] == "Сборка DOCX завершена; найдены места, где форматирование стоит проверить вручную."
    assert runtime["log"][-2]["status"] == "WARN"
    assert "спорные места форматирования" in runtime["log"][-2]["details"]
    assert "Конфликтов подписи/заголовка: 1." in runtime["log"][-2]["details"]
    assert runtime["state"].get("latest_result_notice") is None


def test_run_document_processing_fails_on_strict_unmapped_source_quality_gate(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    diagnostics_dir = tmp_path / "formatting_diagnostics"
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [str(diagnostics_dir / "preserve_001.json")])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    def preserve_with_unmapped_artifact(docx_bytes, paragraphs, generated_paragraph_registry=None):
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        (diagnostics_dir / "preserve_001.json").write_text(
            json.dumps(
                {
                    "stage": "restore",
                    "source_count": 5,
                    "target_count": 4,
                    "mapped_count": 4,
                    "unmapped_source_ids": ["p0004"],
                    "unmapped_target_indexes": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return docx_bytes

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[ParagraphStub()],
        image_assets=[],
        image_mode="safe",
        app_config={"translation_output_quality_gate_policy": "strict"},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="translate",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=preserve_with_unmapped_artifact,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "failed"
    assert "translation_quality_gate_failed" in runtime["state"]["last_error"]
    assert runtime["activity"][-1] == "Итоговый перевод отклонён quality gate: unmapped_source_paragraphs_present."
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "fail"
    assert payload["gate_reasons"] == ["unmapped_source_paragraphs_present"]
    assert payload["bullet_heading_count"] == 0
    assert payload["toc_body_concat_detected"] is False


def test_run_document_processing_surfaces_advisory_quality_notice_on_mapping_drift(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    diagnostics_dir = tmp_path / "formatting_diagnostics"
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [str(diagnostics_dir / "preserve_001.json")])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    def preserve_with_unmapped_artifact(docx_bytes, paragraphs, generated_paragraph_registry=None):
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        (diagnostics_dir / "preserve_001.json").write_text(
            json.dumps(
                {
                    "stage": "restore",
                    "source_count": 50,
                    "target_count": 48,
                    "mapped_count": 48,
                    "unmapped_source_ids": ["p0048", "p0049"],
                    "unmapped_target_indexes": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return docx_bytes

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[ParagraphStub()],
        image_assets=[],
        image_mode="safe",
        app_config={"translation_output_quality_gate_policy": "advisory"},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="translate",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=preserve_with_unmapped_artifact,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_result_notice"] == {
        "level": "warning",
        "message": "Результат собран, но quality report зафиксировал document-level structural warnings.",
    }
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "warn"
    assert payload["gate_reasons"] == ["unmapped_source_paragraphs_above_advisory_threshold"]


def test_run_document_processing_keeps_false_fragment_cleanup_display_only_after_quality_gate_decoupling(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "strict"},
        processing_operation="translate",
        generate_markdown_block=lambda **kwargs: (
            "Христос предупреждает нас\n\n"
            "## (Матфея 24:36)\n\n"
            "что день неизвестен.\n\n"
            "Это обсуждение подводит к вопросу\n\n"
            "## Спутники? Ракеты?)\n\n"
            "который дальше раскрывается в тексте."
        ),
    )

    assert result == "failed"
    assert "## (Матфея 24:36)" not in runtime["state"]["latest_markdown"]
    assert "## Спутники? Ракеты?)" not in runtime["state"]["latest_markdown"]
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "fail"
    assert payload["gate_reasons"] == ["false_fragment_headings_present"]
    assert payload["false_fragment_heading_count"] == 2
    assert payload["scripture_reference_heading_count"] == 1


def test_run_document_processing_quality_report_uses_pre_display_gate_input_for_sentence_split_case(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "strict"},
        processing_operation="translate",
        jobs=[{
            "target_text": "Исходный блок",
            "target_text_with_markers": "[[DOCX_PARA_p1]]\n[[DOCX_PARA_p2]]\n[[DOCX_PARA_p3]]\n[[DOCX_PARA_p4]]",
            "paragraph_ids": ["p1", "p2", "p3", "p4"],
            "context_before": "",
            "context_after": "",
            "target_chars": 13,
            "context_chars": 0,
        }],
        source_paragraphs=[
            SimpleNamespace(paragraph_id="p1", source_index=0, role="body", structural_role="body", heading_level=None, list_kind=None, boundary_source="raw", boundary_confidence="explicit"),
            SimpleNamespace(paragraph_id="p2", source_index=1, role="heading", structural_role="heading", heading_level=2, list_kind=None, boundary_source="raw", boundary_confidence="explicit"),
            SimpleNamespace(paragraph_id="p3", source_index=2, role="body", structural_role="body", heading_level=None, list_kind=None, boundary_source="raw", boundary_confidence="explicit"),
            SimpleNamespace(paragraph_id="p4", source_index=3, role="body", structural_role="body", heading_level=None, list_kind=None, boundary_source="raw", boundary_confidence="explicit"),
        ],
        generate_markdown_block=lambda **kwargs: (
            "Пожалуй, главный вывод состоит в том, что каждое поколение христиан должно приготовиться к возможности пережить\n\n"
            "## Великая скорбь\n\n"
            ".\n\n"
            "Практические шаги начинаются здесь."
        ),
    )

    assert result == "failed"
    assert "## Великая скорбь\n\n." not in runtime["state"]["latest_markdown"]
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "fail"
    assert payload["gate_reasons"] == ["false_fragment_headings_present"]
    assert payload["false_fragment_heading_count"] == 1


def test_run_document_processing_applies_residual_bullet_cleanup_before_display_hygiene_gating(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "strict"},
        processing_operation="translate",
        generate_markdown_block=lambda **kwargs: (
            "Посттрибулационисты считают, что Иисус придёт в конце ● скорби.\n\n"
            "● собирают армию в 200 миллионов солдат.\n\n"
            "- Соединённые Штаты формируют мировую ● культуру и политику?"
        ),
    )

    assert result == "succeeded"
    assert "●" not in runtime["state"]["latest_markdown"]
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "pass"
    assert payload["gate_reasons"] == []
    assert payload["residual_bullet_glyph_count"] == 0
    assert payload["residual_bullet_glyph_gate_source"] == "legacy_markdown"
    assert payload["raw_residual_bullet_glyph_count"] == 3


def test_run_document_processing_normalizes_list_fragment_regressions_before_quality_gate(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "strict"},
        processing_operation="translate",
        generate_markdown_block=lambda **kwargs: (
            "Поразительно, но все петли следуют одной и той же схеме: 1.\n\n"
            "Духовные существа восстают против Бога.\n\n"
            "2. Бог судит их за грех.\n\n"
            "3. Бог спасает остаток верных."
        ),
    )

    report_files = list(quality_dir.glob("*.json"))
    if report_files:
        payload = json.loads(report_files[0].read_text(encoding="utf-8"))
        assert payload["quality_status"] == "pass", json.dumps(payload, ensure_ascii=False, indent=2)

    assert result == "succeeded"
    assert "схеме: 1." not in runtime["state"]["latest_markdown"]
    assert "1. Духовные существа восстают против Бога." in runtime["state"]["latest_markdown"]
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "pass"
    assert payload["list_fragment_regression_count"] == 0


def test_run_document_processing_uses_runtime_normalized_markdown_for_docx_build(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    captured = {}
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "strict"},
        processing_operation="translate",
        generate_markdown_block=lambda **kwargs: (
            "Поразительно, но все петли следуют одной и той же схеме: 1.\n\n"
            "Духовные существа восстают против Бога.\n\n"
            "2. Бог судит их за грех."
        ),
        convert_markdown_to_docx_bytes=lambda markdown_text: captured.setdefault("markdown", markdown_text) or markdown_text.encode("utf-8"),
    )

    assert result == "succeeded"
    assert captured["markdown"] == runtime["state"]["latest_markdown"]
    assert "схеме: 1." not in captured["markdown"]
    assert "1. Духовные существа восстают против Бога." in captured["markdown"]


def test_run_document_processing_normalizes_mixed_script_before_quality_gate(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "strict"},
        processing_operation="translate",
        generate_markdown_block=lambda **kwargs: (
            "Прежде чем суперразумa догонит квантовый скачок.\n\n"
            "Это просто тестовая cтрока с латинскими символами."
        ),
    )

    assert result == "succeeded"
    assert "суперразумa" not in runtime["state"]["latest_markdown"]
    assert "суперразума" in runtime["state"]["latest_markdown"]
    assert "cтрока" not in runtime["state"]["latest_markdown"]
    assert "строка" in runtime["state"]["latest_markdown"]
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "pass"
    assert payload["mixed_script_term_count"] == 0


def test_build_translation_quality_report_flags_bullet_marker_headings_in_strict_translate_mode():
    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown="## ●\n\nПереведённый абзац",
        formatting_diagnostics_artifacts=[],
    )

    assert report["quality_status"] == "warn"
    assert report["gate_reasons"] == ["bullet_marker_headings_review_required"]
    assert report["bullet_heading_count"] == 1
    assert report["bullet_heading_gate_source"] == "legacy_markdown"
    assert report["bullet_heading_classification"] == "markdown_gate"
    assert report["raw_bullet_heading_count"] == 1
    assert report["formatting_review_items"] == [
        {
            "reason": "bullet_marker_headings_review_required",
            "label": "Маркер списка попал в заголовок",
            "count": 1,
            "severity": "fix",
            "sample": {
                "line": 1,
                "text": "## ●",
                "reason": "bullet_marker_heading",
            },
        }
    ]


@pytest.mark.parametrize(
    "markdown_text",
    [
        "Заключение ........ 29 Введение",
        "Заключение……29 Введение",
        "Заключение··29 Введение",
        "Заключение  29 Введение",
    ],
)
def test_build_translation_quality_report_detects_toc_body_concat_across_leader_variants(markdown_text):
    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown=markdown_text,
        formatting_diagnostics_artifacts=[],
    )

    assert report["quality_status"] == "warn"
    assert report["gate_reasons"] == ["toc_body_concatenation_review_required"]
    assert report["toc_body_concat_detected"] is True
    assert report["formatting_review_items"][0]["reason"] == "toc_body_concatenation_review_required"
    assert report["formatting_review_items"][0]["severity"] == "fix"


def test_normalize_final_markdown_for_runtime_display_splits_placeholder_from_chapter_heading():
    normalized = document_pipeline_late_phases._normalize_final_markdown_for_runtime_display(
        "This page intentionally left blank Chapter Nine STRATEGIES FOR NGO S"
    )

    assert normalized == "This page intentionally left blank\n\nChapter Nine STRATEGIES FOR NGO S"


def test_restore_image_heading_lines_from_registry_splits_placeholder_and_heading_markers():
    restored = document_pipeline_late_phases._restore_image_heading_lines_from_registry(
        "[[DOCX_IMAGE_img_009]] Глава десятая ИСТИНА И ПОСЛЕДСТВИЯ\n\nBody",
        [
            {"paragraph_id": "p0076", "text": "## Глава десятая"},
            {"paragraph_id": "p0077", "text": "# ИСТИНА И ПОСЛЕДСТВИЯ"},
        ],
    )

    assert restored == "[[DOCX_IMAGE_img_009]]\n\n## Глава десятая\n# ИСТИНА И ПОСЛЕДСТВИЯ\n\nBody"


def test_restore_image_heading_lines_from_registry_leaves_unbacked_concat_unchanged():
    markdown = "[[DOCX_IMAGE_img_009]] Глава десятая ИСТИНА И ПОСЛЕДСТВИЯ"

    assert document_pipeline_late_phases._restore_image_heading_lines_from_registry(markdown, []) == markdown


def test_build_translation_quality_report_classifies_placeholder_heading_concat_as_display_hygiene_with_raw_observability():
    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown="This page intentionally left blank Chapter Nine STRATEGIES FOR NGO S",
        formatting_diagnostics_artifacts=[],
    )

    assert report["quality_status"] == "pass"
    assert report["gate_reasons"] == []
    assert report["page_placeholder_heading_concat_count"] == 0
    assert report["page_placeholder_heading_concat_source"] == "legacy_markdown"
    assert report["page_placeholder_heading_concat_classification"] == "display_hygiene"
    assert report["raw_page_placeholder_heading_concat_count"] == 1
    assert report["page_placeholder_heading_concat_samples"] == []
    raw_page_placeholder_heading_concat_samples = cast(
        list[dict[str, object]],
        report["raw_page_placeholder_heading_concat_samples"],
    )
    assert raw_page_placeholder_heading_concat_samples[0]["reason"] == "page_placeholder_heading_concat_markdown_present"


def test_normalize_final_markdown_for_quality_gate_preserves_placeholder_cleanup_as_non_gate_input():
    normalized = document_pipeline_late_phases._normalize_final_markdown_for_quality_gate(
        "This page intentionally left blank Chapter Nine STRATEGIES FOR NGO S"
    )

    assert normalized == "This page intentionally left blank Chapter Nine STRATEGIES FOR NGO S"


def test_normalize_final_markdown_for_display_hygiene_reporting_applies_residual_bullet_cleanup():
    normalized = document_pipeline_late_phases._normalize_final_markdown_for_display_hygiene_reporting(
        "Посттрибулационисты считают, что Иисус придёт в конце ● скорби."
    )

    assert normalized == "Посттрибулационисты считают, что Иисус придёт в конце скорби."


def test_normalize_final_markdown_for_runtime_display_applies_structure_compatibility_cleanup_only():
    normalized = document_pipeline_late_phases._normalize_final_markdown_for_runtime_display(
        "Наблюдайте внимательно.\n\n"
        "## (Матфея 24:36)\n\n"
        "Это продолжение абзаца.\n\n"
        "Поразительно, но все петли следуют одной и той же схеме: 1.\n\n"
        "Духовные существа восстают против Бога.\n\n"
        "2. Бог судит их за грех."
    )

    assert normalized == (
        "Наблюдайте внимательно.\n\n"
        "(Матфея 24:36)\n\n"
        "Это продолжение абзаца.\n\n"
        "Поразительно, но все петли следуют одной и той же схеме:\n\n"
        "1. Духовные существа восстают против Бога.\n\n"
        "2. Бог судит их за грех."
    )


def test_resolve_runtime_display_markdown_prefers_explicit_runtime_display_payload():
    resolved = document_pipeline_late_phases._resolve_runtime_display_markdown(
        docx_phase={
            "runtime_display_markdown": "display-cleaned",
        },
        fallback_markdown="raw-gate-input",
    )

    assert resolved == "display-cleaned"


def test_resolve_runtime_display_markdown_ignores_legacy_final_markdown_alias():
    resolved = document_pipeline_late_phases._resolve_runtime_display_markdown(
        docx_phase={"final_markdown": "legacy-display-cleaned"},
        fallback_markdown="This page intentionally left blank Chapter Nine STRATEGIES FOR NGO S",
    )

    assert resolved == "This page intentionally left blank\n\nChapter Nine STRATEGIES FOR NGO S"


def test_build_translation_quality_report_exposes_new_residual_quality_metrics_and_gate_reasons():
    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict", "translation_domain": "theology"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="theology",
        ),
        final_markdown=(
            "Является ли\n\n"
            "## начертание зверя\n\n"
            "на самом деле - квантовая технология?\n\n"
            "## (Матфея 24:36)\n\n"
            "- Сторонники мидтрибулационного взгляда считают, что христиане будут восхищены в середине\n"
            "- Великой скорби.\n\n"
            "Китай ... технологическими ● достижениями?\n\n"
            "## Суд над пятым печатью\n\n"
            "Создавайте кoinonia-сообщества и богословие imago Dei."
        ),
        formatting_diagnostics_artifacts=[],
    )

    assert report["quality_status"] == "fail"
    assert report["gate_reasons"] == [
        "false_fragment_headings_present",
        "list_fragment_regressions_present",
        "mixed_script_terms_review_required",
    ]
    assert report["bullet_heading_count"] == 0
    assert report["false_fragment_heading_count"] == 2
    assert report["scripture_reference_heading_count"] == 1
    assert report["residual_bullet_glyph_count"] == 0
    assert report["residual_bullet_glyph_classification"] == "display_hygiene"
    assert report["raw_residual_bullet_glyph_count"] == 1
    assert report["list_fragment_regression_count"] == 1
    mixed_script_term_count = report["mixed_script_term_count"]
    theology_style_issue_count = report["theology_style_deterministic_issue_count"]
    assert isinstance(mixed_script_term_count, int)
    assert isinstance(theology_style_issue_count, int)
    assert mixed_script_term_count >= 1
    assert theology_style_issue_count >= 2
    assert report["mixed_script_term_gate_source"] == "legacy_markdown"
    assert report["mixed_script_term_classification"] == "non_structural_hygiene"
    assert report["raw_mixed_script_term_count"] == mixed_script_term_count
    assert report["theology_style_deterministic_issue_source"] == "legacy_markdown"
    assert report["theology_style_deterministic_issue_classification"] == "domain_style_advisory"
    assert report["raw_theology_style_deterministic_issue_count"] == theology_style_issue_count
    assert report["translation_domain"] == "theology"
    assert report["worst_unmapped_source_count"] == 0
    assert report["suspicious_heading_repetition_count"] == 0


def test_build_translation_quality_report_prefers_entry_aware_false_heading_detection():
    assembly_result = document_pipeline_output_validation.FinalMarkdownAssemblyResult(
        final_markdown="## Введение\n\nТекст раздела.",
        entries=(
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="## Введение",
                block_index=1,
                paragraph_id="p1",
                source_index=0,
                role="heading",
                structural_role="heading",
                heading_level=2,
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="Текст раздела.",
                block_index=1,
                paragraph_id="p2",
                source_index=1,
                role="body",
                structural_role="body",
                from_registry=True,
            ),
        ),
        diagnostics=document_pipeline_output_validation.FinalAssemblyDiagnostics(),
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown="## Введение\n\nТекст раздела.",
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly_result,
    )

    assert report["quality_status"] == "pass"
    assert report["false_fragment_heading_count"] == 0
    assert report["gate_reasons"] == []
    boundary_recovery = cast(dict[str, Any], report["boundary_recovery"])

    assert boundary_recovery["recovered_heading_entries"] == [
        {
            "paragraph_id": "p1",
            "source_index": 0,
            "role": "heading",
            "structural_role": "heading",
            "generated_heading_kind": None,
            "text": "## Введение",
        }
    ]


def test_build_translation_quality_report_reports_entry_aware_false_heading_sample():
    assembly_result = document_pipeline_output_validation.FinalMarkdownAssemblyResult(
        final_markdown="На людей, получивших начертание зверя и поклонявшихся его образу.",
        entries=(
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="На людей, получивших",
                block_index=1,
                paragraph_id="p1",
                source_index=0,
                role="body",
                structural_role="body",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="## начертание зверя",
                block_index=2,
                paragraph_id="p2",
                source_index=1,
                role="heading",
                structural_role="heading",
                heading_level=2,
                from_registry=True,
                generated_heading_kind="false_fragment_heading",
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="и поклонявшихся его образу.",
                block_index=3,
                paragraph_id="p3",
                source_index=2,
                role="body",
                structural_role="body",
                from_registry=True,
            ),
        ),
        diagnostics=document_pipeline_output_validation.FinalAssemblyDiagnostics(
            demoted_false_headings=1,
        ),
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown="На людей, получивших начертание зверя и поклонявшихся его образу.",
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly_result,
    )

    assert report["quality_status"] == "pass"
    assert report["gate_reasons"] == []
    assert report["false_fragment_heading_count"] == 0
    assert report["false_fragment_heading_samples"] == []


def test_build_translation_quality_report_flags_raw_false_fragment_without_entry_authority():
    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown=(
            "Иисус постоянно говорит о том, как важно распознавать знамения, чтобы, если им будет даровано пережить\n\n"
            "## Великую скорбь\n\n"
            "они могли устоять до конца."
        ),
        formatting_diagnostics_artifacts=[],
    )

    assert report["quality_status"] == "fail"
    assert report["gate_reasons"] == ["false_fragment_headings_present"]
    assert report["false_fragment_heading_count"] == 1
    assert report["false_fragment_heading_gate_source"] == "legacy_markdown"
    assert report["raw_false_fragment_heading_count"] == 1
    assert report["false_fragment_heading_samples"] == [
        {
            "line": 3,
            "text": "## Великую скорбь",
            "reason": "inline_term_heading_present",
        }
    ]


def test_build_translation_quality_report_allows_opening_chapter_marker_followed_by_title_heading():
    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown=(
            "ГЛАВА 1\n\n"
            "## Что такое богатство?\n\n"
            "Первый абзац главы начинается здесь."
        ),
        formatting_diagnostics_artifacts=[],
    )

    assert report["quality_status"] == "pass"
    assert report["gate_reasons"] == []
    assert report["false_fragment_heading_count"] == 0
    assert report["raw_false_fragment_heading_count"] == 0
    assert report["false_fragment_heading_samples"] == []


def test_build_translation_quality_report_flags_scripture_reference_false_heading_without_normalizer_override():
    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown="Наблюдайте внимательно.\n\n## (Матфея 24:36)\n\nЭто продолжение абзаца.",
        formatting_diagnostics_artifacts=[],
    )

    assert report["quality_status"] == "fail"
    assert report["gate_reasons"] == ["false_fragment_headings_present"]
    assert report["false_fragment_heading_count"] == 1
    assert report["scripture_reference_heading_count"] == 1
    assert report["scripture_reference_heading_samples"] == [
        {
            "line": 3,
            "text": "## (Матфея 24:36)",
            "reason": "scripture_reference_heading_present",
        }
    ]


def test_build_translation_quality_report_prefers_entry_authority_over_raw_false_fragment_markdown():
    assembly_result = document_pipeline_output_validation.FinalMarkdownAssemblyResult(
        final_markdown="Иисус постоянно говорит о том, как важно распознавать знамения, чтобы, если им будет даровано пережить Великую скорбь они могли устоять до конца.",
        entries=(
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="Иисус постоянно говорит о том, как важно распознавать знамения, чтобы, если им будет даровано пережить",
                block_index=1,
                paragraph_id="p1",
                source_index=0,
                role="body",
                structural_role="body",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="Великую скорбь",
                block_index=1,
                paragraph_id="p2",
                source_index=1,
                role="body",
                structural_role="body",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="они могли устоять до конца.",
                block_index=1,
                paragraph_id="p3",
                source_index=2,
                role="body",
                structural_role="body",
                from_registry=True,
            ),
        ),
        diagnostics=document_pipeline_output_validation.FinalAssemblyDiagnostics(),
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown=(
            "Иисус постоянно говорит о том, как важно распознавать знамения, чтобы, если им будет даровано пережить\n\n"
            "## Великую скорбь\n\n"
            "они могли устоять до конца."
        ),
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly_result,
    )

    assert report["quality_status"] == "pass"
    assert report["gate_reasons"] == []
    assert report["false_fragment_heading_count"] == 0
    assert report["false_fragment_heading_samples"] == []
    assert report["false_fragment_heading_gate_source"] == "entry_assembly"
    assert report["raw_false_fragment_heading_count"] == 1


def test_build_translation_quality_report_keeps_entry_authority_with_mixed_fallback_entries():
    assembly_result = document_pipeline_output_validation.FinalMarkdownAssemblyResult(
        final_markdown=(
            "Иисус постоянно говорит о том, как важно распознавать знамения, чтобы, если им будет даровано пережить\n\n"
            "## Великую скорбь\n\n"
            "они могли устоять до конца."
        ),
        entries=(
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="Иисус постоянно говорит о том, как важно распознавать знамения, чтобы, если им будет даровано пережить",
                block_index=1,
                paragraph_id="p1",
                source_index=0,
                role="body",
                structural_role="body",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="## Великую скорбь",
                block_index=2,
                paragraph_id="p2",
                source_index=1,
                role="heading",
                structural_role="heading",
                heading_level=2,
                from_registry=True,
                generated_heading_kind="real_heading",
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="они могли устоять до конца.",
                block_index=3,
                used_fallback=True,
            ),
        ),
        diagnostics=document_pipeline_output_validation.FinalAssemblyDiagnostics(),
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown=(
            "Иисус постоянно говорит о том, как важно распознавать знамения, чтобы, если им будет даровано пережить\n\n"
            "## Великую скорбь\n\n"
            "они могли устоять до конца."
        ),
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly_result,
    )

    assert report["quality_status"] == "pass"
    assert report["gate_reasons"] == []
    assert report["false_fragment_heading_count"] == 0
    assert report["false_fragment_heading_gate_source"] == "entry_assembly"
    assert report["raw_false_fragment_heading_count"] == 1


def test_collect_false_fragment_heading_samples_from_entries_preserves_source_backed_real_heading():
    entries = (
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="Незавершённая вводная фраза о разделе",
            block_index=1,
            paragraph_id="p1",
            source_index=0,
            role="body",
            structural_role="body",
            from_registry=True,
        ),
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="## Размышление о верности",
            block_index=2,
            paragraph_id="p2",
            source_index=1,
            role="heading",
            structural_role="heading",
            heading_level=2,
            from_registry=True,
            generated_heading_kind="real_heading",
        ),
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="Этот раздел открывается полноценным абзацем.",
            block_index=3,
            paragraph_id="p3",
            source_index=2,
            role="body",
            structural_role="body",
            from_registry=True,
        ),
    )

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples_from_entries(entries)

    assert samples == []


def test_collect_false_fragment_heading_samples_from_entries_allows_opening_chapter_marker_pair():
    entries = (
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="ГЛАВА 1",
            block_index=1,
            paragraph_id="p1",
            source_index=0,
            role="body",
            structural_role="body",
            from_registry=True,
        ),
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="## Что такое богатство?",
            block_index=2,
            paragraph_id="p2",
            source_index=1,
            role="heading",
            structural_role="heading",
            heading_level=2,
            from_registry=True,
        ),
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="Первый абзац главы начинается здесь.",
            block_index=3,
            paragraph_id="p3",
            source_index=2,
            role="body",
            structural_role="body",
            from_registry=True,
        ),
    )

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples_from_entries(entries)

    assert samples == []


def test_collect_false_fragment_heading_samples_from_entries_overrides_source_heading_for_parenthetical_question_tail():
    entries = (
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="Кометы? Астероиды?",
            block_index=1,
            paragraph_id="p1",
            source_index=0,
            role="body",
            structural_role="body",
            from_registry=True,
        ),
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="## Спутники? Ракеты?)",
            block_index=2,
            paragraph_id="p2",
            source_index=1,
            role="heading",
            structural_role="heading",
            heading_level=2,
            from_registry=True,
            generated_heading_kind=None,
        ),
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="Треть земли будет сожжена.",
            block_index=3,
            paragraph_id="p3",
            source_index=2,
            role="body",
            structural_role="body",
            from_registry=True,
        ),
    )

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples_from_entries(entries)

    assert samples == [
        document_pipeline_output_validation.QualityIssueSample(
            line=3,
            text="## Спутники? Ракеты?)",
            reason="sentence_split_heading_present",
        )
    ]


def test_run_document_processing_quality_report_uses_same_final_markdown_as_runtime_state(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    final_markdown = "На людей, получивших начертание зверя и поклонявшихся его образу, приходят язвы."
    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "strict", "enable_paragraph_markers": True},
        processing_operation="translate",
        jobs=[{
            "target_text": "Исходный блок",
            "target_text_with_markers": "[[DOCX_PARA_p1]]\n[[DOCX_PARA_p2]]\n[[DOCX_PARA_p3]]",
            "paragraph_ids": ["p1", "p2", "p3"],
            "context_before": "",
            "context_after": "",
            "target_chars": 13,
            "context_chars": 0,
        }],
        source_paragraphs=[
            SimpleNamespace(paragraph_id="p1", source_index=0, role="body", structural_role="body", heading_level=None, list_kind=None, boundary_source="raw", boundary_confidence="explicit"),
            SimpleNamespace(paragraph_id="p2", source_index=1, role="body", structural_role="body", heading_level=None, list_kind=None, boundary_source="raw", boundary_confidence="explicit"),
            SimpleNamespace(paragraph_id="p3", source_index=2, role="body", structural_role="body", heading_level=None, list_kind=None, boundary_source="raw", boundary_confidence="explicit"),
        ],
        generate_markdown_block=lambda **kwargs: "На людей, получивших\n\n## начертание зверя\n\nи поклонявшихся его образу, приходят язвы.",
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == final_markdown
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "pass"
    assert payload["final_markdown_chars"] == len(final_markdown)
    assert payload["false_fragment_heading_count"] == 0

def test_run_document_processing_warns_on_legacy_markdown_toc_concat_quality_gate(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "strict"},
        processing_operation="translate",
        generate_markdown_block=lambda **kwargs: "Заключение........ 29 Введение",
    )

    assert result == "succeeded"
    assert runtime["state"]["last_error"] == ""
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "warn"
    assert payload["gate_reasons"] == ["toc_body_concatenation_review_required"]
    assert payload["bullet_heading_count"] == 0
    assert payload["toc_body_concat_detected"] is True
    assert runtime["state"]["latest_result_notice"] == {
        "level": "warning",
        "message": "Готово. 1 абзац требует проверки оформления. Подробности: formatting_review.txt",
    }


def test_build_translation_quality_report_flags_suspicious_heading_repetition_without_intervening_body():
    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown=(
            "## Начертание зверя\n\n"
            "## Начертание зверя\n\n"
            "Новый текст после подозрительного дубля."
        ),
        formatting_diagnostics_artifacts=[],
    )

    assert report["quality_status"] == "fail"
    assert report["gate_reasons"] == ["false_fragment_headings_present"]
    assert report["suspicious_heading_repetition_count"] == 1
    assert report["suspicious_heading_repetition_samples"] == [
        {
            "line": 3,
            "text": "Начертание зверя",
            "reason": "suspicious_heading_repetition_present",
        }
    ]


def test_build_translation_quality_report_keeps_list_fragment_runtime_cleanup_display_only():
    final_markdown = (
        "Поразительно, но все петли следуют одной и той же схеме: 1.\n"
        "Духовные существа восстают против Бога.\n"
        "2. Бог судит их за грех.\n"
        "3. Бог спасает остаток верных."
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown=final_markdown,
        formatting_diagnostics_artifacts=[],
    )

    display_markdown = document_pipeline_late_phases._normalize_final_markdown_for_runtime_display(final_markdown)

    assert report["quality_status"] == "fail"
    assert report["gate_reasons"] == ["list_fragment_regressions_present"]
    assert report["list_fragment_regression_count"] == 1
    assert report["list_fragment_regression_gate_source"] == "legacy_markdown"
    assert report["raw_list_fragment_regression_count"] == 1
    assert "схеме: 1." in final_markdown
    assert "схеме: 1." not in display_markdown
    assert "1. Духовные существа восстают против Бога." in display_markdown


def test_build_translation_quality_report_keeps_list_fragment_markdown_observability_advisory_with_topology_authority():
    final_markdown = (
        "Поразительно, но все петли следуют одной и той же схеме: 1.\n"
        "Духовные существа восстают против Бога.\n"
        "2. Бог судит их за грех.\n"
        "3. Бог спасает остаток верных."
    )
    assembly_result = document_pipeline_output_validation.FinalMarkdownAssemblyResult(
        final_markdown=(
            "Поразительно, но все петли следуют одной и той же схеме.\n\n"
            "1. Духовные существа восстают против Бога.\n"
            "2. Бог судит их за грех.\n"
            "3. Бог спасает остаток верных."
        ),
        entries=(
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="Поразительно, но все петли следуют одной и той же схеме.",
                block_index=1,
                paragraph_id="p1",
                source_index=0,
                role="body",
                structural_role="body",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="1. Духовные существа восстают против Бога.",
                block_index=2,
                paragraph_id="p2",
                source_index=1,
                role="body",
                structural_role="body",
                list_kind="ordered",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="2. Бог судит их за грех.",
                block_index=3,
                paragraph_id="p3",
                source_index=2,
                role="body",
                structural_role="body",
                list_kind="ordered",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="3. Бог спасает остаток верных.",
                block_index=4,
                paragraph_id="p4",
                source_index=3,
                role="body",
                structural_role="body",
                list_kind="ordered",
                from_registry=True,
            ),
        ),
        diagnostics=document_pipeline_output_validation.FinalAssemblyDiagnostics(),
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
            document_topology_projection=SimpleNamespace(
                projected_units=[SimpleNamespace(authority="document_map", confidence="high")],
                operations=[],
            ),
        ),
        final_markdown=final_markdown,
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly_result,
    )

    assert report["quality_status"] == "pass"
    assert report["gate_reasons"] == []
    assert report["list_fragment_regression_count"] == 0
    assert report["list_fragment_regression_samples"] == []
    assert report["list_fragment_regression_gate_source"] == "topology_projection"
    assert report["raw_list_fragment_regression_count"] == 1
    assert report["raw_list_fragment_regression_samples"] == [
        {
            "line": 1,
            "text": "Поразительно, но все петли следуют одной и той же схеме: 1.",
            "reason": "list_fragment_regressions_present",
        }
    ]


def test_build_translation_quality_report_credits_source_backed_numbered_references_without_topology():
    final_markdown = (
        "2. Goldman Sachs Annual Report, 2010.\n\n"
        "14. Forbes, 2017."
    )
    assembly_result = document_pipeline_output_validation.FinalMarkdownAssemblyResult(
        final_markdown=final_markdown,
        entries=(
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="2. Goldman Sachs Annual Report, 2010.",
                block_index=1,
                paragraph_id="p1",
                source_index=0,
                role="list",
                structural_role="list",
                list_kind="ordered",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="14. Forbes, 2017.",
                block_index=1,
                paragraph_id="p2",
                source_index=1,
                role="list",
                structural_role="list",
                list_kind="ordered",
                from_registry=True,
            ),
        ),
        diagnostics=document_pipeline_output_validation.FinalAssemblyDiagnostics(),
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown=final_markdown,
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly_result,
    )

    assert report["quality_status"] == "pass"
    assert report["gate_reasons"] == []
    assert report["list_fragment_regression_count"] == 0
    assert report["list_fragment_regression_samples"] == []
    assert report["list_fragment_regression_gate_source"] == "entry_assembly"
    assert report["raw_list_fragment_regression_count"] == 2


def test_build_translation_quality_report_keeps_standalone_numeric_continuation_after_reference_credit():
    final_markdown = (
        "26. Барба и де Виво, «Взгляд на финансы как на непроизводительный труд», с.\n\n"
        "1491.\n\n"
        "27. Хаттон и Кент, «Рынок валютных деривативов», с. 225."
    )
    assembly_result = document_pipeline_output_validation.FinalMarkdownAssemblyResult(
        final_markdown=final_markdown,
        entries=(
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="26. Барба и де Виво, «Взгляд на финансы как на непроизводительный труд», с.",
                block_index=1,
                paragraph_id="p1",
                source_index=0,
                role="list",
                structural_role="list",
                list_kind="ordered",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="1491.",
                block_index=1,
                paragraph_id="p2",
                source_index=1,
                role="body",
                structural_role="body",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="27. Хаттон и Кент, «Рынок валютных деривативов», с. 225.",
                block_index=1,
                paragraph_id="p3",
                source_index=2,
                role="list",
                structural_role="list",
                list_kind="ordered",
                from_registry=True,
            ),
        ),
        diagnostics=document_pipeline_output_validation.FinalAssemblyDiagnostics(),
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown=final_markdown,
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly_result,
    )

    assert report["quality_status"] == "warn"
    assert report["gate_reasons"] == ["list_fragment_regressions_review_required"]
    assert report["list_fragment_regression_count"] == 1
    assert report["list_fragment_regression_samples"] == [
        {
            "line": 3,
            "text": "1491.",
            "reason": "list_fragment_regressions_present",
        }
    ]
    assert report["list_fragment_regression_gate_source"] == "entry_assembly"
    assert report["raw_list_fragment_regression_count"] == 2
    assert report["formatting_review_required_count"] == 1
    assert report["formatting_review_items"] == [
        {
            "reason": "list_fragment_regressions_review_required",
            "label": "Одиночный номер в сносках или библиографии",
            "count": 1,
            "severity": "review",
            "sample": {
                "line": 3,
                "text": "1491.",
                "reason": "list_fragment_regressions_present",
            },
        }
    ]


def test_build_translation_quality_report_credits_source_backed_reference_by_exact_text_when_line_offsets_drift():
    final_markdown = (
        "Intro paragraph that shifts assembly offsets.\n\n"
        "2. Goldman Sachs Annual Report, 2010.\n\n"
        "1491."
    )
    assembly_result = document_pipeline_output_validation.FinalMarkdownAssemblyResult(
        final_markdown=final_markdown,
        entries=(
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="2. Goldman Sachs Annual Report, 2010.",
                block_index=1,
                paragraph_id="p1",
                source_index=0,
                role="list",
                structural_role="list",
                list_kind="ordered",
                from_registry=True,
            ),
            document_pipeline_output_validation.FinalAssemblyEntry(
                text="1490–1491.",
                block_index=1,
                paragraph_id="p2",
                source_index=1,
                role="body",
                structural_role="body",
                from_registry=True,
            ),
        ),
        diagnostics=document_pipeline_output_validation.FinalAssemblyDiagnostics(),
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
        ),
        final_markdown=final_markdown,
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly_result,
    )

    assert report["quality_status"] == "warn"
    assert report["gate_reasons"] == ["list_fragment_regressions_review_required"]
    assert report["list_fragment_regression_count"] == 1
    assert report["list_fragment_regression_samples"] == [
        {
            "line": 5,
            "text": "1491.",
            "reason": "list_fragment_regressions_present",
        }
    ]
    assert report["list_fragment_regression_gate_source"] == "entry_assembly"
    assert report["raw_list_fragment_regression_count"] == 2
    assert report["formatting_review_required_count"] == 1


def test_run_document_processing_warns_on_advisory_structural_markdown_quality_gate(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    artifact_calls = {}
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "advisory"},
        processing_operation="translate",
        generate_markdown_block=lambda **kwargs: "Заключение……29 Введение",
        write_ui_result_artifacts=lambda **kwargs: artifact_calls.setdefault("kwargs", dict(kwargs)) or {"markdown_path": "/tmp/report.result.md", "docx_path": "/tmp/report.result.docx", "metadata_path": "/tmp/report.result.meta.json"},
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_result_notice"] == {
        "level": "warning",
        "message": "Готово. 1 абзац требует проверки оформления. Подробности: formatting_review.txt",
    }
    assert artifact_calls["kwargs"]["quality_warning"]["gate_reasons"] == ["toc_body_concatenation_review_required"]
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "warn"
    assert payload["gate_reasons"] == ["toc_body_concatenation_review_required"]
    assert payload["toc_body_concat_detected"] is True


def test_run_document_processing_quality_report_prefers_topology_authority_over_markdown_toc_concat(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "strict"},
        processing_operation="translate",
        document_map=_bounded_toc_document_map(),
        document_topology_projection=DocumentTopologyProjection(
            cache_key="topology-authoritative-toc",
            projected_units=(
                StructuralUnit(
                    unit_type="toc_entry",
                    logical_indexes=(8,),
                    canonical_text="10 Truth and Consequences",
                    role="toc_entry",
                    heading_level=None,
                    confidence="high",
                    authority="document_map_toc",
                ),
                StructuralUnit(
                    unit_type="toc_entry",
                    logical_indexes=(8,),
                    canonical_text="11 Governance and We, the Citizens",
                    role="toc_entry",
                    heading_level=None,
                    confidence="high",
                    authority="document_map_toc",
                ),
            ),
        ),
        generate_markdown_block=lambda **kwargs: "Заключение........ 29 Введение",
    )

    assert result == "succeeded"
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "pass"
    assert payload["gate_reasons"] == []
    assert payload["toc_body_concat_gate_source"] == "topology_projection"
    assert payload["toc_body_concat_markdown_detected"] is True
    assert payload["toc_body_concat_structure_detected"] is False
    assert payload["toc_body_concat_detected"] is False
    assert payload["document_map_toc_detected"] is True
    assert payload["document_map_toc_region_count"] == 1
    assert payload["topology_toc_entry_count"] == 2
    assert payload["topology_split_compound_toc_operation_count"] == 0
    assert payload["document_map_compound_toc_split_hint_count"] == 0


def test_run_document_processing_quality_report_keeps_candidate_page_artifact_non_binding(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(document_pipeline_late_phases, "collect_recent_formatting_diagnostics_artifacts", lambda since_epoch_seconds, diagnostics_dir: [])
    monkeypatch.setattr(document_pipeline_late_phases, "QUALITY_REPORTS_DIR", quality_dir)

    result = _run_processing(
        runtime,
        app_config={"translation_output_quality_gate_policy": "strict"},
        processing_operation="translate",
        document_map=_bounded_toc_document_map(),
        document_topology_projection=DocumentTopologyProjection(
            cache_key="candidate-page-artifact-only",
            operations=(
                DocumentTopologyOperation(
                    op="candidate_page_artifact_split",
                    logical_indexes=(9, 10),
                    canonical_text="This page intentionally left blank Chapter 11",
                    authority="document_map_outline",
                    confidence="candidate",
                    evidence=("page_artifact_phrase", "local_heading_neighborhood", "page_break_boundary"),
                ),
            ),
        ),
        generate_markdown_block=lambda **kwargs: "Заключение........ 29 Введение",
    )

    assert result == "succeeded"
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "warn"
    assert payload["gate_reasons"] == ["toc_body_concatenation_review_required"]
    assert payload["toc_body_concat_gate_source"] == "legacy_markdown"
    assert payload["toc_body_concat_markdown_detected"] is True
    assert payload["toc_body_concat_structure_detected"] is False
    assert payload["toc_body_concat_detected"] is True
    assert payload["topology_split_compound_toc_operation_count"] == 0
    assert payload["topology_merge_heading_operation_count"] == 0
    assert payload["document_map_compound_toc_split_hint_count"] == 0


def test_build_translation_quality_report_prefers_role_aware_source_basis_over_topology_unit(monkeypatch):
    monkeypatch.setattr(
        document_pipeline_late_phases,
        "_load_formatting_diagnostics_payloads",
        lambda artifact_paths: [
            {
                "unmapped_source_ids": ["p0000", "p0001"],
                "unmapped_target_indexes": [],
                "source_count": 2,
                "target_count": 2,
                "unmapped_source_residual_diagnostics": {
                    "effective_formatting_coverage_diagnostics": {
                        "format_neutral_creditable_count": 0,
                    }
                },
            }
        ],
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
            source_paragraphs=[
                ParagraphUnit(text="Governance and We,", role="heading", paragraph_id="p0000", source_index=0, logical_index=10),
                ParagraphUnit(text="the Citizens", role="heading", paragraph_id="p0001", source_index=1, logical_index=11),
            ],
            document_map=None,
            document_topology_projection=DocumentTopologyProjection(
                cache_key="topology-merged-heading",
                projected_units=(
                    StructuralUnit(
                        unit_type="chapter_heading",
                        logical_indexes=(10, 11),
                        canonical_text="Governance and We, the Citizens",
                        role="heading",
                        heading_level=1,
                        confidence="high",
                        authority="document_map_outline",
                    ),
                ),
            ),
        ),
        final_markdown="## Governance and We, the Citizens",
        formatting_diagnostics_artifacts=["ignored.json"],
    )

    assert report["raw_unmapped_source_paragraph_count"] == 2
    assert report["raw_unmapped_target_paragraph_count"] == 0
    assert report["structure_unit_unmapped_source_count"] == 1
    assert report["structure_unit_unmapped_target_count"] == 0
    assert report["unmapped_source_count_basis"] == "role_aware_formatting_coverage"
    assert report["unmapped_target_count_basis"] == "topology_unit"
    assert report["unit_unmapped_source_gate_source"] == "topology_unit"
    assert report["unit_unmapped_target_gate_source"] == "topology_unit"
    assert report["unmapped_source_count"] == 2


def test_build_translation_quality_report_uses_role_aware_effective_unmapped_source_count(monkeypatch):
    monkeypatch.setattr(
        document_pipeline_late_phases,
        "_load_formatting_diagnostics_payloads",
        lambda artifact_paths: [
            {
                "unmapped_source_ids": ["p0001", "p0002", "p0003"],
                "unmapped_target_indexes": [],
                "source_count": 3,
                "target_count": 2,
                "source_registry": [
                    {"paragraph_id": "p0001", "source_index": 0, "role": "body", "structural_role": "body", "text_preview": "Body one"},
                    {"paragraph_id": "p0002", "source_index": 1, "role": "body", "structural_role": "body", "text_preview": "Body two"},
                    {"paragraph_id": "p0003", "source_index": 2, "role": "body", "structural_role": "body", "text_preview": "Body three"},
                ],
                "unmapped_source_residual_diagnostics": {
                    "effective_formatting_coverage_diagnostics": {
                        "format_neutral_creditable_count": 2,
                    }
                },
            }
        ],
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
            document_map=None,
            document_topology_projection=None,
        ),
        final_markdown="Body one\n\nBody two",
        formatting_diagnostics_artifacts=["ignored.json"],
    )

    assert report["raw_unmapped_source_paragraph_count"] == 3
    assert report["filtered_unmapped_source_count"] == 3
    assert report["format_neutral_creditable_count"] == 2
    assert report["effective_unmapped_source_count"] == 1
    assert report["unmapped_source_count_basis"] == "role_aware_formatting_coverage"
    assert report["unmapped_source_count"] == 1
    assert report["worst_unmapped_source_count"] == 1


def test_build_translation_quality_report_warns_on_small_role_aware_unmapped_source_residue(monkeypatch):
    monkeypatch.setattr(
        document_pipeline_late_phases,
        "_load_formatting_diagnostics_payloads",
        lambda artifact_paths: [
            {
                "unmapped_source_ids": [f"p{index:04d}" for index in range(8)],
                "unmapped_target_indexes": [],
                "source_count": 1140,
                "target_count": 1135,
                "source_registry": [
                    {
                        "paragraph_id": f"p{index:04d}",
                        "source_index": index,
                        "role": "body",
                        "structural_role": "body",
                        "text_preview": f"Body {index}",
                    }
                    for index in range(8)
                ],
                "unmapped_source_residual_diagnostics": {
                    "effective_formatting_coverage_diagnostics": {
                        "format_neutral_creditable_count": 0,
                    }
                },
            }
        ],
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
            document_map=None,
            document_topology_projection=None,
        ),
        final_markdown="Body",
        formatting_diagnostics_artifacts=["ignored.json"],
    )

    assert report["quality_status"] == "warn"
    assert report["gate_reasons"] == ["unmapped_source_paragraphs_review_required"]
    assert report["unmapped_source_count_basis"] == "role_aware_formatting_coverage"
    assert report["unmapped_source_count"] == 8
    assert report["formatting_review_required_count"] == 8
    assert report["formatting_review_items"] == [
        {
            "reason": "unmapped_source_paragraphs_review_required",
            "label": "Абзацы без явного соответствия оригиналу",
            "count": 8,
            "severity": "review",
        }
    ]


def test_build_translation_quality_report_surfaces_role_loss_as_fix_not_generic_review(monkeypatch):
    monkeypatch.setattr(
        document_pipeline_late_phases,
        "_load_formatting_diagnostics_payloads",
        lambda artifact_paths: [
            {
                "unmapped_source_ids": ["p0001"],
                "unmapped_target_indexes": [],
                "source_count": 1140,
                "target_count": 1139,
                "source_registry": [
                    {
                        "paragraph_id": "p0001",
                        "source_index": 1,
                        "role": "heading",
                        "structural_role": "heading",
                        "text_preview": "Chapter 10",
                    }
                ],
                "unmapped_source_residual_diagnostics": {
                    "effective_formatting_coverage_diagnostics": {
                        "counts": {
                            "content_survived_but_format_role_lost": 1,
                        },
                        "format_neutral_creditable_count": 0,
                    },
                    "samples": [
                        {
                            "paragraph_id": "p0001",
                            "source_index": 1,
                            "role": "heading",
                            "structural_role": "heading",
                            "text_preview": "Chapter 10",
                            "effective_formatting_coverage_class": "content_survived_but_format_role_lost",
                        }
                    ],
                },
            }
        ],
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
            document_map=None,
            document_topology_projection=None,
        ),
        final_markdown="Chapter 10 inline body text",
        formatting_diagnostics_artifacts=["ignored.json"],
    )

    assert report["quality_status"] == "warn"
    assert report["gate_reasons"] == ["role_loss_review_required"]
    assert report["unmapped_source_count_basis"] == "role_aware_formatting_coverage"
    assert report["unmapped_source_count"] == 1
    assert report["formatting_review_items"] == [
        {
            "reason": "role_loss_review_required",
            "label": "Структурный абзац стал обычным текстом",
            "count": 1,
            "severity": "fix",
            "sample": {
                "line": None,
                "text": "Chapter 10",
                "reason": "content_survived_but_format_role_lost",
                "role": "heading",
                "structural_role": "heading",
            },
        }
    ]


def test_build_translation_quality_report_fails_large_role_loss_set(monkeypatch):
    role_loss_ids = [f"p{index:04d}" for index in range(11)]
    monkeypatch.setattr(
        document_pipeline_late_phases,
        "_load_formatting_diagnostics_payloads",
        lambda artifact_paths: [
            {
                "unmapped_source_ids": role_loss_ids,
                "unmapped_target_indexes": [],
                "source_count": 1000,
                "target_count": 989,
                "source_registry": [
                    {
                        "paragraph_id": paragraph_id,
                        "source_index": index,
                        "role": "heading",
                        "structural_role": "heading",
                        "text_preview": f"Chapter {index}",
                    }
                    for index, paragraph_id in enumerate(role_loss_ids)
                ],
                "unmapped_source_residual_diagnostics": {
                    "effective_formatting_coverage_diagnostics": {
                        "counts": {
                            "content_survived_but_format_role_lost": 11,
                        },
                        "format_neutral_creditable_count": 0,
                    },
                    "samples": [
                        {
                            "paragraph_id": paragraph_id,
                            "source_index": index,
                            "role": "heading",
                            "structural_role": "heading",
                            "text_preview": f"Chapter {index}",
                            "effective_formatting_coverage_class": "content_survived_but_format_role_lost",
                        }
                        for index, paragraph_id in enumerate(role_loss_ids)
                    ],
                },
            }
        ],
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
            document_map=None,
            document_topology_projection=None,
        ),
        final_markdown="Many headings collapsed into body text",
        formatting_diagnostics_artifacts=["ignored.json"],
    )

    assert report["quality_status"] == "fail"
    assert report["gate_reasons"] == ["role_loss_above_manual_review_threshold"]
    assert report["formatting_review_required_count"] == 11
    review_items = cast(list[dict[str, object]], report["formatting_review_items"])
    assert all(item["severity"] == "fix" for item in review_items)
    assert all(item["reason"] == "role_loss_above_manual_review_threshold" for item in review_items)
    assert review_items[0]["aggregate_count"] == 11


def test_build_translation_quality_report_uses_role_aware_effective_unmapped_target_count(monkeypatch):
    monkeypatch.setattr(
        document_pipeline_late_phases,
        "_load_formatting_diagnostics_payloads",
        lambda artifact_paths: [
            {
                "unmapped_source_ids": [],
                "unmapped_target_indexes": [1, 2, 3],
                "source_count": 2,
                "target_count": 5,
                "unmapped_target_residual_diagnostics": {
                    "split_accounting_creditable_count": 2,
                },
            }
        ],
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
            document_map=None,
            document_topology_projection=None,
        ),
        final_markdown="Body one\n\nBody two",
        formatting_diagnostics_artifacts=["ignored.json"],
    )

    assert report["raw_unmapped_target_paragraph_count"] == 3
    assert report["target_split_accounting_creditable_count"] == 2
    assert report["effective_unmapped_target_count"] == 1
    assert report["unmapped_target_count_basis"] == "role_aware_formatting_coverage"
    assert report["unmapped_target_count"] == 1


def test_build_translation_quality_report_prefers_role_aware_target_basis_over_topology_unit(monkeypatch):
    monkeypatch.setattr(
        document_pipeline_late_phases,
        "_load_formatting_diagnostics_payloads",
        lambda artifact_paths: [
            {
                "unmapped_source_ids": [],
                "unmapped_target_indexes": [1, 2, 3],
                "source_count": 2,
                "target_count": 5,
                "unmapped_target_residual_diagnostics": {
                    "split_accounting_creditable_count": 2,
                },
            }
        ],
    )
    monkeypatch.setattr(
        document_pipeline_late_phases,
        "_derive_translation_quality_authority_fields",
        lambda **kwargs: {
            "raw_unmapped_source_paragraph_count": 0,
            "raw_unmapped_target_paragraph_count": 3,
            "structure_unit_unmapped_source_count": 0,
            "structure_unit_unmapped_target_count": 3,
            "unmapped_source_count_basis": "legacy_paragraph",
            "unmapped_target_count_basis": "topology_unit",
        },
    )

    report = document_pipeline_late_phases._build_translation_quality_report(
        context=SimpleNamespace(
            app_config={"translation_output_quality_gate_policy": "strict"},
            processing_operation="translate",
            uploaded_filename="report.docx",
            translation_domain="general",
            document_map=None,
            document_topology_projection=None,
        ),
        final_markdown="Body one\n\nBody two",
        formatting_diagnostics_artifacts=["ignored.json"],
    )

    assert report["raw_unmapped_target_paragraph_count"] == 3
    assert report["target_split_accounting_creditable_count"] == 2
    assert report["effective_unmapped_target_count"] == 1
    assert report["structure_unit_unmapped_target_count"] == 3
    assert report["unmapped_target_count_basis"] == "role_aware_formatting_coverage"
    assert report["unmapped_target_count"] == 1


def test_run_document_processing_logs_compact_block_plan_summary_at_info() -> None:
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()

    result = _run_processing(
        runtime,
        jobs=[
            {"target_text": "alpha", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0},
            {"target_text": "beta", "context_before": "", "context_after": "", "target_chars": 8, "context_chars": 0, "job_kind": "passthrough"},
        ],
        log_event=log_event,
    )

    assert result == "succeeded"
    info_events = [event for event in events if event["level"] == logging.INFO]
    summary_event = next(event for event in info_events if event["event_id"] == "block_plan_summary")
    assert summary_event["context"]["block_count"] == 2
    assert summary_event["context"]["llm_block_count"] == 1
    assert summary_event["context"]["passthrough_block_count"] == 1
    assert summary_event["context"]["total_target_chars"] == 13
    assert summary_event["context"]["first_block_target_chars"] == [5, 8]
    assert "blocks" not in summary_event["context"]
    assert all(event["event_id"] != "block_map" for event in info_events)


def test_run_document_processing_demotes_block_chatter_to_debug() -> None:
    runtime = _build_runtime_capture()
    events, log_event = _capture_log_events()

    result = _run_processing(
        runtime,
        app_config={"enable_paragraph_markers": True},
        jobs=[{
            "target_text": "Исходный блок",
            "target_text_with_markers": "[[DOCX_PARA_p0001]]\nИсходный блок",
            "paragraph_ids": ["p0001"],
            "context_before": "",
            "context_after": "",
            "target_chars": 13,
            "context_chars": 0,
        }],
        generate_markdown_block=lambda **kwargs: "Очищенный блок",
        log_event=log_event,
    )

    assert result == "succeeded"
    info_event_ids = {event["event_id"] for event in events if event["level"] == logging.INFO}
    debug_event_ids = {event["event_id"] for event in events if event["level"] == logging.DEBUG}
    assert "processing_started" in info_event_ids
    assert "processing_completed" in info_event_ids
    assert "block_started" not in info_event_ids
    assert "block_completed" not in info_event_ids
    assert "block_marker_registry_built" not in info_event_ids
    assert {"block_started", "block_completed", "block_marker_registry_built"}.issubset(debug_event_ids)


def test_run_document_processing_passes_marker_wrapped_text_only_when_marker_mode_enabled():
    runtime = _build_runtime_capture()
    generate_calls = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Исходный блок",
            "target_text_with_markers": "[[DOCX_PARA_p0001]]\nИсходный блок",
            "paragraph_ids": ["p0001"],
            "context_before": "",
            "context_after": "",
            "target_chars": 13,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"enable_paragraph_markers": True},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generate_calls.append(kwargs) or "Очищенный блок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert generate_calls[0]["target_text"] == "[[DOCX_PARA_p0001]]\nИсходный блок"
    assert generate_calls[0]["expected_paragraph_ids"] == ["p0001"]
    assert generate_calls[0]["marker_mode"] is True
    assert runtime["state"]["latest_markdown"] == "Очищенный блок"
    assert runtime["state"]["processed_paragraph_registry"] == [
        {"block_index": 1, "paragraph_id": "p0001", "text": "Очищенный блок"}
    ]


def test_run_document_processing_passes_generated_paragraph_registry_into_docx_restoration():
    runtime = _build_runtime_capture()
    preserve_calls = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Исходный блок",
            "target_text_with_markers": "[[DOCX_PARA_p0001]]\nИсходный блок",
            "paragraph_ids": ["p0001"],
            "context_before": "",
            "context_after": "",
            "target_chars": 13,
            "context_chars": 0,
        }],
        source_paragraphs=[ParagraphStub()],
        image_assets=[],
        image_mode="safe",
        app_config={"enable_paragraph_markers": True},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Очищенный блок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: preserve_calls.append(generated_paragraph_registry) or docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    expected_registry = [{"block_index": 1, "paragraph_id": "p0001", "text": "Очищенный блок"}]
    assert preserve_calls == [expected_registry]


def test_run_document_processing_registry_uses_logical_marker_for_merged_source_paragraph():
    runtime = _build_runtime_capture()
    generate_calls = []
    merged_paragraph = ParagraphUnit(
        text="Слитый логический абзац",
        role="body",
        paragraph_id="p0007",
        origin_raw_indexes=[0, 1],
        origin_raw_texts=["Слитый", "логический абзац"],
        boundary_source="normalized_merge",
        boundary_confidence="high",
    )

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Слитый логический абзац",
            "target_text_with_markers": "[[DOCX_PARA_p0007]]\nСлитый логический абзац",
            "paragraph_ids": ["p0007"],
            "context_before": "",
            "context_after": "",
            "target_chars": 24,
            "context_chars": 0,
        }],
        source_paragraphs=[merged_paragraph],
        image_assets=[],
        image_mode="safe",
        app_config={"enable_paragraph_markers": True},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generate_calls.append(kwargs) or "Слитый логический абзац",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert generate_calls[0]["expected_paragraph_ids"] == ["p0007"]
    assert runtime["state"]["processed_paragraph_registry"] == [
        {"block_index": 1, "paragraph_id": "p0007", "text": "Слитый логический абзац"}
    ]


def test_run_document_processing_passes_assembly_aware_registry_into_docx_restoration():
    runtime = _build_runtime_capture()
    preserve_calls = []
    source_paragraphs = [
        ParagraphUnit(text="Первый фрагмент", role="body", paragraph_id="p0001"),
        ParagraphUnit(text="Второй фрагмент", role="body", paragraph_id="p0002"),
    ]

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Исходный блок",
            "target_text_with_markers": "[[DOCX_PARA_p0001]]\n[[DOCX_PARA_p0002]]",
            "paragraph_ids": ["p0001", "p0002"],
            "context_before": "",
            "context_after": "",
            "target_chars": 13,
            "context_chars": 0,
        }],
        source_paragraphs=source_paragraphs,
        image_assets=[],
        image_mode="safe",
        app_config={"enable_paragraph_markers": True},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Первый фрагмент\n\nВторой фрагмент",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: preserve_calls.append(generated_paragraph_registry) or docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert preserve_calls == [[
        {"block_index": 1, "paragraph_id": "p0001", "text": "Первый фрагмент Второй фрагмент", "merged_paragraph_ids": ["p0001", "p0002"]}
    ]]


def test_reader_cleanup_formatting_lineage_removes_deleted_registry_entries():
    raw_markdown = "Intro\n\nHeader\n\nBody paragraph"
    registry = [
        {"block_index": 1, "paragraph_id": "p0001", "text": "Intro"},
        {"block_index": 2, "paragraph_id": "p0002", "text": "Header"},
        {"block_index": 3, "paragraph_id": "p0003", "text": "Body paragraph"},
    ]
    cleanup_report = {
        "accepted_cleanup_operations": [
            {
                "id": "b_000001",
                "operation": "delete_block",
                "expected_after_preview": "",
            }
        ]
    }

    derived_registry, diagnostics = document_pipeline_late_phases._derive_reader_cleanup_generated_paragraph_registry(
        generated_paragraph_registry=registry,
        cleanup_report=cleanup_report,
        raw_markdown=raw_markdown,
    )

    assert diagnostics["status"] == "derived"
    assert diagnostics["deleted_registry_entry_count"] == 1
    assert derived_registry == [
        {"block_index": 1, "paragraph_id": "p0001", "text": "Intro"},
        {"block_index": 3, "paragraph_id": "p0003", "text": "Body paragraph"},
    ]


def test_reader_cleanup_formatting_lineage_updates_split_and_heading_boundary_text():
    raw_markdown = "HEADING Body paragraph"
    registry = [{"block_index": 1, "paragraph_id": "p0001", "text": "HEADING Body paragraph"}]
    cleanup_report = {
        "accepted_cleanup_operations": [
            {
                "id": "b_000000",
                "operation": "normalize_heading_boundary",
                "expected_after_preview": "### HEADING\n\nBody paragraph",
            }
        ]
    }

    derived_registry, diagnostics = document_pipeline_late_phases._derive_reader_cleanup_generated_paragraph_registry(
        generated_paragraph_registry=registry,
        cleanup_report=cleanup_report,
        raw_markdown=raw_markdown,
    )

    assert diagnostics["updated_registry_entry_count"] == 1
    assert derived_registry == [
        {
            "block_index": 1,
            "paragraph_id": "p0001",
            "text": "### HEADING\n\nBody paragraph",
            "reader_cleanup_operations": ["normalize_heading_boundary"],
        }
    ]


def test_reader_cleanup_formatting_lineage_merges_joined_registry_entries():
    raw_markdown = "First fragment\n\nsecond fragment"
    registry = [
        {"block_index": 1, "paragraph_id": "p0001", "text": "First fragment"},
        {"block_index": 2, "paragraph_id": "p0002", "text": "second fragment"},
    ]
    cleanup_report = {
        "accepted_cleanup_operations": [
            {
                "id": "b_000000",
                "operation": "join_fragmented_paragraph",
                "next_id": "b_000001",
                "expected_after_preview": "First fragment second fragment",
            }
        ]
    }

    derived_registry, diagnostics = document_pipeline_late_phases._derive_reader_cleanup_generated_paragraph_registry(
        generated_paragraph_registry=registry,
        cleanup_report=cleanup_report,
        raw_markdown=raw_markdown,
    )

    assert diagnostics["joined_registry_entry_count"] == 1
    assert derived_registry == [
        {
            "block_index": 1,
            "paragraph_id": "p0001",
            "text": "First fragment second fragment",
            "merged_paragraph_ids": ["p0001", "p0002"],
            "reader_cleanup_operations": ["join_fragmented_paragraph"],
        }
    ]


def test_reader_cleanup_formatting_lineage_skips_anchor_repair_operations():
    raw_markdown = "Intro\n\nHEADING Body"
    registry = [
        {"block_index": 1, "paragraph_id": "p0001", "text": "Intro"},
        {"block_index": 2, "paragraph_id": "p0002", "text": "HEADING Body"},
    ]
    cleanup_report = {
        "accepted_cleanup_operations": [
            {
                "id": "b_000001",
                "operation": "normalize_heading_boundary",
                "pass_name": "anchor_repair",
                "expected_after_preview": "### HEADING\n\nBody",
            }
        ]
    }

    derived_registry, diagnostics = document_pipeline_late_phases._derive_reader_cleanup_generated_paragraph_registry(
        generated_paragraph_registry=registry,
        cleanup_report=cleanup_report,
        raw_markdown=raw_markdown,
    )

    assert diagnostics["status"] == "derived"
    assert diagnostics["applied_operation_count"] == 0
    assert diagnostics["skipped_operation_count"] == 1
    assert derived_registry == registry


def test_reader_cleanup_formatting_lineage_skips_when_block_count_is_ambiguous():
    raw_markdown = "Intro\n\nBody"
    registry = [{"block_index": 1, "paragraph_id": "p0001", "text": "Intro"}]

    derived_registry, diagnostics = document_pipeline_late_phases._derive_reader_cleanup_generated_paragraph_registry(
        generated_paragraph_registry=registry,
        cleanup_report={"accepted_cleanup_operations": []},
        raw_markdown=raw_markdown,
    )

    assert diagnostics == {
        "status": "skipped",
        "reason": "cleanup_block_registry_count_mismatch",
        "sparse_alignment_failure_reason": "non_image_placeholder_registry_gaps",
        "alignment_gap_count": 1,
        "raw_cleanup_block_count": 2,
        "generated_registry_count": 1,
    }
    assert derived_registry == registry


def test_reader_cleanup_formatting_lineage_allows_sparse_image_placeholder_gap():
    raw_markdown = "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph"
    registry = [
        {"block_index": 7, "paragraph_id": "p0001", "text": "Intro"},
        {"block_index": 7, "paragraph_id": "p0003", "text": "Body paragraph"},
    ]
    cleanup_report = {
        "accepted_cleanup_operations": [
            {
                "id": "b_000001",
                "operation": "delete_block",
                "expected_after_preview": "",
            }
        ]
    }

    derived_registry, diagnostics = document_pipeline_late_phases._derive_reader_cleanup_generated_paragraph_registry(
        generated_paragraph_registry=registry,
        cleanup_report=cleanup_report,
        raw_markdown=raw_markdown,
    )

    assert diagnostics["status"] == "derived"
    assert diagnostics["alignment_mode"] == "sparse_image_placeholders"
    assert diagnostics["alignment_gap_count"] == 1
    assert diagnostics["applied_operation_count"] == 0
    assert diagnostics["skipped_operation_count"] == 1
    assert derived_registry == registry


def test_reader_cleanup_formatting_lineage_uses_paragraph_id_when_cleanup_text_drifted():
    raw_markdown = "Intro before cleanup\n\n[[DOCX_IMAGE_img_001]]\n\nBody before cleanup"
    registry = [
        {"block_index": 7, "paragraph_id": "p0001", "text": "Intro after cleanup"},
        {"block_index": 7, "paragraph_id": "p0003", "text": "Body after cleanup"},
    ]

    derived_registry, diagnostics = document_pipeline_late_phases._derive_reader_cleanup_generated_paragraph_registry(
        generated_paragraph_registry=registry,
        cleanup_report={"accepted_cleanup_operations": []},
        raw_markdown=raw_markdown,
        cleanup_block_metadata_by_index={
            0: {"paragraph_id": "p0001"},
            2: {"paragraph_id": "p0003"},
        },
    )

    assert diagnostics["status"] == "derived"
    assert diagnostics["alignment_mode"] == "identity_sparse_image_placeholders"
    assert diagnostics["alignment_gap_count"] == 1
    assert diagnostics["applied_operation_count"] == 0
    assert derived_registry == registry


def test_reader_cleanup_formatting_lineage_rejects_sparse_non_image_gap():
    raw_markdown = "Intro\n\nDropped semantic text\n\nBody paragraph"
    registry = [
        {"block_index": 7, "paragraph_id": "p0001", "text": "Intro"},
        {"block_index": 7, "paragraph_id": "p0003", "text": "Body paragraph"},
    ]

    derived_registry, diagnostics = document_pipeline_late_phases._derive_reader_cleanup_generated_paragraph_registry(
        generated_paragraph_registry=registry,
        cleanup_report={"accepted_cleanup_operations": []},
        raw_markdown=raw_markdown,
    )

    assert diagnostics == {
        "status": "skipped",
        "reason": "cleanup_block_registry_count_mismatch",
        "sparse_alignment_failure_reason": "non_image_placeholder_registry_gaps",
        "alignment_gap_count": 1,
        "raw_cleanup_block_count": 3,
        "generated_registry_count": 2,
    }
    assert derived_registry == registry


def test_reader_cleanup_block_identity_metadata_does_not_leak_to_model_payload():
    blocks = build_cleanup_blocks(
        "Intro",
        block_metadata_by_index={0: {"paragraph_id": "p0001", "merged_paragraph_ids": ["p0001", "p0002"]}},
    )

    assert blocks[0].paragraph_id == "p0001"
    assert blocks[0].merged_paragraph_ids == ("p0001", "p0002")
    payload = blocks[0].to_payload()
    assert "paragraph_id" not in payload
    assert "merged_paragraph_ids" not in payload


def test_reader_cleanup_block_identity_metadata_reports_id_match_and_gaps():
    raw_markdown = "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph"
    registry = [
        {"block_index": 7, "paragraph_id": "p0001", "text": "Intro"},
        {"block_index": 7, "paragraph_id": "p0003", "text": "Body paragraph"},
    ]

    metadata, diagnostics = document_pipeline_late_phases._build_reader_cleanup_block_identity_metadata(
        raw_markdown=raw_markdown,
        generated_paragraph_registry=registry,
    )

    assert metadata == {
        0: {"paragraph_id": "p0001"},
        2: {"paragraph_id": "p0003"},
    }
    assert diagnostics == {
        "status": "available",
        "reason": None,
        "raw_cleanup_block_count": 3,
        "generated_registry_count": 2,
        "id_matched_block_count": 2,
        "missing_id_registry_entry_count": 0,
        "gap_count": 1,
        "image_gap_count": 1,
        "text_gap_count": 0,
    }


def test_reader_cleanup_postprocess_prefers_assembly_formatting_registry_over_stale_state_registry(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(document_pipeline_late_phases, "READER_CLEANUP_LINEAGE_DIR", tmp_path / "reader_cleanup_lineage")
    runtime = _build_runtime_capture()
    preserve_calls = []
    log_events = []
    raw_markdown = "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph"
    assembly_registry = [
        {"block_index": 1, "paragraph_id": "p0001", "text": "Intro"},
        {"block_index": 3, "paragraph_id": "p0003", "text": "Body paragraph"},
    ]
    stale_state_registry = [{"block_index": 1, "paragraph_id": "stale", "text": raw_markdown}]

    def generate_markdown_block(**kwargs):
        payload = json.loads(kwargs["target_text"])
        delete_target = next(block for block in payload["blocks"] if block["text"] == "[[DOCX_IMAGE_img_001]]")
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": delete_target["id"],
                        "text_hash": delete_target["text_hash"],
                        "operation": "delete_block",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "[[DOCX_IMAGE_img_001]]",
                        "expected_after_preview": "",
                        "safety_note": "test fixture",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = document_pipeline_late_phases._run_reader_cleanup_postprocess(
        context=SimpleNamespace(
            processing_operation="translate",
            app_config={
                "reader_cleanup_enabled": True,
                "reader_cleanup_policy": "advisory",
                "reader_cleanup_chunk_size": 500,
                "reader_cleanup_max_delete_block_ratio": 0.8,
                "reader_cleanup_max_delete_char_ratio": 0.8,
            },
            model="anthropic:claude-sonnet-4-6",
            max_retries=1,
            uploaded_filename="report.docx",
            runtime=runtime,
            source_paragraphs=[ParagraphUnit(text="Intro", role="body", paragraph_id="p0001")],
        ),
        dependencies=SimpleNamespace(
            get_client=lambda: object(),
            generate_markdown_block=generate_markdown_block,
            convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
            preserve_source_paragraph_properties=(
                lambda docx_bytes, paragraphs, generated_paragraph_registry=None: preserve_calls.append(
                    generated_paragraph_registry
                )
                or docx_bytes
            ),
            reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
            log_event=lambda level, event_id, message, **context: log_events.append(
                {"level": level, "event_id": event_id, "message": message, "context": context}
            ),
            present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        ),
        emitters=SimpleNamespace(
            emit_activity=lambda *args, **kwargs: None,
            emit_state=lambda *args, **kwargs: None,
        ),
        state=SimpleNamespace(generated_paragraph_registry=stale_state_registry),
        cleanup_input_markdown=raw_markdown,
        runtime_display_markdown=raw_markdown,
        base_docx_bytes=b"base-docx",
        job_count=1,
        processed_image_assets=[],
        formatting_registry=assembly_registry,
    )
    cleaned_markdown = result.markdown
    cleaned_docx_bytes = result.docx_bytes
    report = result.report
    final_registry = result.final_generated_paragraph_registry

    assert cleaned_markdown == "Intro\n\nBody paragraph"
    assert cleaned_docx_bytes == b"Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph"
    assert report is not None
    assert final_registry == [
        {"block_index": 1, "paragraph_id": "p0001", "text": "Intro", "target_paragraph_indexes": [0]},
        {"block_index": 3, "paragraph_id": "p0003", "text": "Body paragraph", "target_paragraph_indexes": [2]},
    ]
    assert preserve_calls == [[
        {"block_index": 1, "paragraph_id": "p0001", "text": "Intro", "target_paragraph_indexes": [0]},
        {"block_index": 3, "paragraph_id": "p0003", "text": "Body paragraph", "target_paragraph_indexes": [2]},
    ]]
    applied_event = next(event for event in log_events if event["event_id"] == "reader_cleanup_applied")
    assert applied_event["context"]["formatting_lineage_status"] == "derived"
    assert applied_event["context"]["formatting_lineage_reason"] is None
    assert applied_event["context"]["cleanup_identity_status"] == "available"
    assert applied_event["context"]["cleanup_identity_id_matched_block_count"] == 2
    assert applied_event["context"]["cleanup_identity_image_gap_count"] == 1
    assert applied_event["context"]["cleanup_identity_text_gap_count"] == 0
    lineage_artifact_path = Path(applied_event["context"]["reader_cleanup_lineage_artifact_path"])
    assert lineage_artifact_path.exists()
    lineage_payload = json.loads(lineage_artifact_path.read_text(encoding="utf-8"))
    assert lineage_payload["stage"] == "reader_cleanup_lineage"
    assert lineage_payload["active_formatting_registry"] == assembly_registry
    assert lineage_payload["cleanup_identity_diagnostics"]["text_gap_count"] == 0
    assert lineage_payload["cleanup_formatting_lineage"]["status"] == "derived"


def test_reader_cleanup_noop_restores_image_heading_concats_from_registry():
    runtime = _build_runtime_capture()
    raw_markdown = "[[DOCX_IMAGE_img_001]] Глава восьмая\n\nBody paragraph"
    assembly_registry = [
        {"block_index": 1, "paragraph_id": "p0026", "text": "## Глава восьмая"},
        {"block_index": 2, "paragraph_id": "p0027", "text": "Body paragraph"},
    ]

    result = document_pipeline_late_phases._run_reader_cleanup_postprocess(
        context=SimpleNamespace(
            processing_operation="translate",
            app_config={
                "reader_cleanup_enabled": True,
                "reader_cleanup_policy": "advisory",
                "reader_cleanup_chunk_size": 500,
                "reader_cleanup_max_delete_block_ratio": 0.8,
                "reader_cleanup_max_delete_char_ratio": 0.8,
            },
            model="anthropic:claude-sonnet-4-6",
            max_retries=1,
            uploaded_filename="report.docx",
            runtime=runtime,
            source_paragraphs=[ParagraphUnit(text="Chapter Eight", role="heading", paragraph_id="p0026")],
        ),
        dependencies=SimpleNamespace(
            get_client=lambda: object(),
            generate_markdown_block=lambda **kwargs: json.dumps({"cleanup_operations": [], "warnings": []}),
            convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
            preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
            reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
            log_event=lambda *args, **kwargs: None,
            present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        ),
        emitters=SimpleNamespace(
            emit_activity=lambda *args, **kwargs: None,
            emit_state=lambda *args, **kwargs: None,
        ),
        state=SimpleNamespace(generated_paragraph_registry=[]),
        cleanup_input_markdown=raw_markdown,
        runtime_display_markdown=raw_markdown,
        base_docx_bytes=None,
        base_docx_builder=None,
        job_count=1,
        processed_image_assets=[],
        formatting_registry=assembly_registry,
    )

    assert result.markdown == "[[DOCX_IMAGE_img_001]]\n\n## Глава восьмая\n\nBody paragraph"
    assert result.final_generated_paragraph_registry == [
        {"block_index": 1, "paragraph_id": "p0026", "text": "## Глава восьмая", "target_paragraph_indexes": [1]},
        {"block_index": 2, "paragraph_id": "p0027", "text": "Body paragraph", "target_paragraph_indexes": [2]},
    ]


def test_reader_cleanup_postprocess_persists_final_generated_registry_in_runtime_state(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(document_pipeline_late_phases, "READER_CLEANUP_LINEAGE_DIR", tmp_path / "reader_cleanup_lineage")
    runtime = _build_runtime_capture()
    raw_markdown = "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph"
    assembly_registry = [
        {"block_index": 1, "paragraph_id": "p0001", "text": "Intro"},
        {"block_index": 3, "paragraph_id": "p0003", "text": "Body paragraph"},
    ]

    def generate_markdown_block(**kwargs):
        payload = json.loads(kwargs["target_text"])
        delete_target = next(block for block in payload["blocks"] if block["text"] == "[[DOCX_IMAGE_img_001]]")
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": delete_target["id"],
                        "text_hash": delete_target["text_hash"],
                        "operation": "delete_block",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "[[DOCX_IMAGE_img_001]]",
                        "expected_after_preview": "",
                        "safety_note": "test fixture",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = document_pipeline_late_phases._run_reader_cleanup_postprocess(
        context=SimpleNamespace(
            processing_operation="translate",
            app_config={
                "reader_cleanup_enabled": True,
                "reader_cleanup_policy": "advisory",
                "reader_cleanup_chunk_size": 500,
                "reader_cleanup_max_delete_block_ratio": 0.8,
                "reader_cleanup_max_delete_char_ratio": 0.8,
            },
            model="anthropic:claude-sonnet-4-6",
            max_retries=1,
            uploaded_filename="report.docx",
            runtime=runtime,
            source_paragraphs=[ParagraphUnit(text="Intro", role="body", paragraph_id="p0001")],
        ),
        dependencies=SimpleNamespace(
            get_client=lambda: object(),
            generate_markdown_block=generate_markdown_block,
            convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
            preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
            reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
            log_event=lambda *args, **kwargs: None,
            present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        ),
        emitters=SimpleNamespace(
            emit_activity=lambda *args, **kwargs: None,
            emit_state=_emit_state,
        ),
        state=SimpleNamespace(generated_paragraph_registry=None),
        cleanup_input_markdown=raw_markdown,
        runtime_display_markdown=raw_markdown,
        base_docx_bytes=b"base-docx",
        job_count=1,
        processed_image_assets=[],
        formatting_registry=assembly_registry,
    )

    assert result.final_generated_paragraph_registry == [
        {"block_index": 1, "paragraph_id": "p0001", "text": "Intro", "target_paragraph_indexes": [0]},
        {"block_index": 3, "paragraph_id": "p0003", "text": "Body paragraph", "target_paragraph_indexes": [2]},
    ]
    assert runtime["state"]["final_generated_paragraph_registry"] == [
        {"block_index": 1, "paragraph_id": "p0001", "text": "Intro", "target_paragraph_indexes": [0]},
        {"block_index": 3, "paragraph_id": "p0003", "text": "Body paragraph", "target_paragraph_indexes": [2]},
    ]


def test_rebuild_docx_for_markdown_prefers_cleanup_formatting_registry_override():
    preserve_calls = []
    override_registry = [{"block_index": 1, "paragraph_id": "p0001", "text": "Cleaned"}]

    document_pipeline_late_phases._rebuild_docx_for_markdown(
        markdown_text="Cleaned",
        context=SimpleNamespace(source_paragraphs=[ParagraphUnit(text="Source", role="body", paragraph_id="p0001")]),
        dependencies=SimpleNamespace(
            convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
            preserve_source_paragraph_properties=(
                lambda docx_bytes, paragraphs, generated_paragraph_registry=None: preserve_calls.append(
                    generated_paragraph_registry
                )
                or docx_bytes
            ),
            reinsert_inline_images=lambda docx_bytes, processed_assets: docx_bytes,
        ),
        state=SimpleNamespace(generated_paragraph_registry=[{"block_index": 1, "paragraph_id": "stale", "text": "Stale"}]),
        processed_image_assets=[],
        generated_paragraph_registry=override_registry,
    )

    assert preserve_calls == [
        [{"block_index": 1, "paragraph_id": "p0001", "text": "Cleaned", "target_paragraph_indexes": [0]}]
    ]


def test_rebuild_identity_formatting_registry_attaches_target_indexes_without_visible_markers():
    registry = document_pipeline_late_phases._build_rebuild_identity_formatting_registry(
        markdown_text="# Translated Heading\n\nTranslated body",
        generated_paragraph_registry=[
            {"paragraph_id": "p0001", "text": "# Translated Heading"},
            {"paragraph_id": "p0002", "text": "Translated body"},
        ],
    )

    assert registry == [
        {"paragraph_id": "p0001", "text": "# Translated Heading", "target_paragraph_indexes": [0]},
        {"paragraph_id": "p0002", "text": "Translated body", "target_paragraph_indexes": [1]},
    ]


def test_rebuild_identity_formatting_registry_rolls_back_partial_multiblock_match():
    registry = document_pipeline_late_phases._build_rebuild_identity_formatting_registry(
        markdown_text="First block\n\nNext stable block",
        generated_paragraph_registry=[
            {"paragraph_id": "p0001", "text": "First block\n\nMissing continuation"},
            {"paragraph_id": "p0002", "text": "Next stable block"},
        ],
    )

    assert registry == [
        {"paragraph_id": "p0001", "text": "First block\n\nMissing continuation"},
        {"paragraph_id": "p0002", "text": "Next stable block", "target_paragraph_indexes": [1]},
    ]


def test_reader_cleanup_lineage_rebuild_harness_accepts_runtime_lineage_artifact(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    artifact_path = tmp_path / "reader_cleanup_lineage.json"
    output_path = tmp_path / "harness_result.json"
    artifact_path.write_text(
        json.dumps(
            {
                "stage": "reader_cleanup_lineage",
                "raw_markdown": "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody",
                "cleaned_markdown": "Intro\n\nBody",
                "cleanup_report": {"accepted_cleanup_operations": []},
                "active_formatting_registry": [
                    {"block_index": 1, "paragraph_id": "p0001", "text": "Intro"},
                    {"block_index": 3, "paragraph_id": "p0003", "text": "Body"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts/run-reader-cleanup-lineage-rebuild-harness.py"),
            "--lineage-artifact",
            str(artifact_path),
            "--output",
            str(output_path),
        ],
        cwd=project_root,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    attempt = payload["candidate_attempts"][0]
    assert attempt["lineage_diagnostics"]["status"] == "derived"
    assert attempt["lineage_diagnostics"]["alignment_mode"] == "identity_sparse_image_placeholders"
    assert attempt["artifact_shape"]["raw_image_placeholder_count"] == 1
    assert attempt["artifact_shape"]["cleaned_image_placeholder_count"] == 0
    assert attempt["artifact_shape"]["rebuilt_image_placeholder_count"] == 1


def test_run_document_processing_writes_marker_generation_diagnostics_artifact_on_marker_validation_failure(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    diagnostics_dir = tmp_path / "formatting_diagnostics"
    monkeypatch.setattr(document_pipeline, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Исходный блок",
            "target_text_with_markers": "[[DOCX_PARA_p0001]]\nИсходный блок",
            "paragraph_ids": ["p0001"],
            "context_before": "prev",
            "context_after": "next",
            "target_chars": 13,
            "context_chars": 8,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"enable_paragraph_markers": True},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("paragraph_marker_validation_failed:markers_missing")),
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    artifact_path = Path(runtime["state"]["latest_marker_diagnostics_artifact"])
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["stage"] == "generation"
    assert payload["error_code"] == "markers_missing"
    assert payload["paragraph_ids"] == ["p0001"]
    assert "marker diagnostics:" in runtime["log"][-1]["details"]


def test_run_document_processing_marker_generation_artifact_includes_found_ids_and_raw_response_preview(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    diagnostics_dir = tmp_path / "formatting_diagnostics"
    monkeypatch.setattr(document_pipeline, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Исходный блок",
            "target_text_with_markers": "[[DOCX_PARA_p0001]]\nИсходный блок",
            "paragraph_ids": ["p0001"],
            "context_before": "prev",
            "context_after": "next",
            "target_chars": 13,
            "context_chars": 8,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"enable_paragraph_markers": True},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: (_ for _ in ()).throw(
            generation.MarkerValidationError(
                "marker_order_or_identity",
                raw_markdown="[[DOCX_PARA_p9999]]\nЧужой маркер",
                expected_paragraph_ids=["p0001"],
                found_paragraph_ids=["p9999"],
            )
        ),
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    artifact_path = Path(runtime["state"]["latest_marker_diagnostics_artifact"])
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["error_code"] == "marker_order_or_identity"
    assert payload["expected_paragraph_ids"] == ["p0001"]
    assert payload["found_paragraph_ids"] == ["p9999"]
    assert payload["raw_response_preview"] == "[[DOCX_PARA_p9999]]\nЧужой маркер"


def test_run_document_processing_writes_marker_registry_diagnostics_artifact_on_registry_mismatch(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    diagnostics_dir = tmp_path / "formatting_diagnostics"
    monkeypatch.setattr(document_pipeline, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Исходный блок",
            "target_text_with_markers": "[[DOCX_PARA_p0001]]\nИсходный блок",
            "paragraph_ids": ["p0001", "p0002"],
            "context_before": "prev",
            "context_after": "next",
            "target_chars": 13,
            "context_chars": 8,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"enable_paragraph_markers": True},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Только один абзац",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    artifact_path = Path(runtime["state"]["latest_marker_diagnostics_artifact"])
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["stage"] == "registry"
    assert payload["error_code"].startswith("block=1:expected=2:actual=1")
    assert payload["processed_chunk_preview"] == "Только один абзац"
    assert "marker diagnostics:" in runtime["log"][-1]["details"]


def test_run_document_processing_stops_before_second_block():
    runtime = _build_runtime_capture()
    stop_checks = {"count": 0}

    def should_stop(runtime):
        stop_checks["count"] += 1
        return stop_checks["count"] >= 2

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"target_text": "block-1", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0},
            {"target_text": "block-2", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0},
        ],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=should_stop,
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "stopped"
    assert runtime["finalize"][-1][0] == "Остановлено пользователем"
    assert runtime["finalize"][-1][3] == "stopped"
    assert runtime["log"][-1]["status"] == "STOP"


def test_run_document_processing_emits_segment_statuses_during_segmented_run_before_stopped():
    runtime = _build_runtime_capture()
    stop_checks = {"count": 0}

    def should_stop(runtime):
        stop_checks["count"] += 1
        return stop_checks["count"] >= 2

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {
                "target_text": "block-1",
                "context_before": "",
                "context_after": "",
                "target_chars": 7,
                "context_chars": 0,
                "segment_id": "seg_0001",
            },
            {
                "target_text": "block-2",
                "context_before": "",
                "context_after": "",
                "target_chars": 7,
                "context_chars": 0,
                "segment_id": "seg_0002",
            },
        ],
        source_paragraphs=cast(Any, [
            SimpleNamespace(segment_id="seg_0001", text="Chapter 1"),
            SimpleNamespace(segment_id="seg_0002", text="Chapter 2"),
        ]),
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=should_stop,
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    segment_status_events = [payload for payload in runtime["status"] if "segment_status_by_id" in payload]

    assert result == "stopped"
    assert segment_status_events[0]["segment_status_by_id"] == {"seg_0001": "processing", "seg_0002": "pending"}
    assert segment_status_events[1]["segment_status_by_id"] == {"seg_0001": "completed", "seg_0002": "pending"}


def test_run_document_processing_stops_after_image_phase_before_placeholder_validation(monkeypatch):
    runtime = _build_runtime_capture()
    stop_checks = {"count": 0}
    calls = {
        "image": 0,
        "image_integrity": 0,
        "late_validate": 0,
        "docx": 0,
        "artifacts": 0,
    }

    monkeypatch.setattr(
        document_pipeline,
        "_validate_placeholder_integrity_phase",
        lambda **kwargs: calls.__setitem__("late_validate", calls["late_validate"] + 1) or True,
    )

    def should_stop(runtime):
        stop_checks["count"] += 1
        return stop_checks["count"] >= 2

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"target_text": "block-1", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0},
        ],
        source_paragraphs=[],
        image_assets=[AssetStub("img_001")],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=should_stop,
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: calls.__setitem__("image", calls["image"] + 1) or kwargs["image_assets"],
        inspect_placeholder_integrity=lambda markdown_text, image_assets: calls.__setitem__("image_integrity", calls["image_integrity"] + 1) or {},
        convert_markdown_to_docx_bytes=lambda markdown_text: calls.__setitem__("docx", calls["docx"] + 1) or b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=lambda **kwargs: calls.__setitem__("artifacts", calls["artifacts"] + 1) or {"markdown_path": "/tmp/final.result.md", "docx_path": "/tmp/final.result.docx"},
    )

    assert result == "stopped"
    assert calls == {
        "image": 1,
        "image_integrity": 1,
        "late_validate": 0,
        "docx": 0,
        "artifacts": 0,
    }
    assert runtime["finalize"][-1][0] == "Остановлено пользователем"
    assert runtime["finalize"][-1][3] == "stopped"
    assert runtime["log"][-1]["status"] == "STOP"


def test_run_document_processing_emits_active_segment_before_failed_terminal_result():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {
                "target_text": "block-1",
                "context_before": "",
                "context_after": "",
                "target_chars": 7,
                "context_chars": 0,
                "segment_id": "seg_0001",
            },
        ],
        source_paragraphs=cast(Any, [SimpleNamespace(segment_id="seg_0001", text="Chapter 1")]),
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["status"][0]["active_segment_id"] == "seg_0001"
    assert runtime["status"][0]["segment_status_by_id"] == {"seg_0001": "processing"}
    assert runtime["finalize"][-1][3] == "error"


def test_run_document_processing_persists_failed_job_result_records(monkeypatch):
    runtime = _build_runtime_capture()
    captured = {}

    def write_job_result_registry(*, records):
        captured.setdefault("job_records", []).extend(list(records))
        return {"job_0000": "/tmp/job-results/job_0000.job-result.json"}

    monkeypatch.setattr(document_pipeline, "write_job_result_registry_impl", write_job_result_registry)

    result = _run_processing(
        runtime,
        prepared_source_key="prep:report:1234",
        structure_fingerprint="struct-abc",
        jobs=[
            {
                "job_id": "job_0000",
                "segment_id": "seg_0001",
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
            }
        ],
        source_paragraphs=cast(Any, [SimpleNamespace(segment_id="seg_0001", text="Chapter 1")]),
        generate_markdown_block=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert result == "failed"
    assert len(captured["job_records"]) == 1
    failed_record = dict(captured["job_records"][0])
    assert isinstance(failed_record.pop("updated_at", ""), str)
    assert failed_record == {
        "schema_version": 1,
        "prepared_source_key": "prep:report:1234",
        "structure_fingerprint": "struct-abc",
        "job_id": "job_0000",
        "segment_id": "seg_0001",
        "status": "failed",
        "block_index": 1,
        "target_chars": 5,
        "context_chars": 0,
        "error_code": "block_failed",
        "error_message": "Ошибка обработки блока: boom",
    }


def test_run_document_processing_end_to_end_produces_openable_docx_artifact(tmp_path):
    image_path = tmp_path / "pipeline-image.png"
    image_path.write_bytes(PNG_BYTES)

    source_doc = Document()
    source_doc.add_heading("Глава", level=1)
    source_doc.add_paragraph().add_run().add_picture(str(image_path))
    source_doc.add_paragraph("Рисунок 1. Подпись")
    source_doc.add_paragraph("Исходный абзац")
    source_buffer = BytesIO()
    source_doc.save(source_buffer)
    source_buffer.seek(0)

    source_paragraphs, image_assets = extract_document_content_from_docx(source_buffer)
    runtime = _build_runtime_capture()
    final_markdown = "Глава\n\n[[DOCX_IMAGE_img_001]]\n\nРисунок 1. Подпись\n\nОбновленный абзац"

    def build_docx_from_markdown(markdown_text):
        doc = Document()
        for block in markdown_text.split("\n\n"):
            doc.add_paragraph(block)
        buffer = BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    result = _run_processing(
        runtime,
        jobs=[{"target_text": "Исходный блок", "context_before": "", "context_after": "", "target_chars": 13, "context_chars": 0}],
        source_paragraphs=source_paragraphs,
        image_assets=image_assets,
        generate_markdown_block=lambda **kwargs: final_markdown,
        process_document_images=lambda **kwargs: image_assets,
        convert_markdown_to_docx_bytes=build_docx_from_markdown,
        preserve_source_paragraph_properties=__import__(
            "docxaicorrector.generation.formatting_transfer", fromlist=["preserve_source_paragraph_properties"]
        ).preserve_source_paragraph_properties,
        reinsert_inline_images=__import__(
            "docxaicorrector.image.reinsertion", fromlist=["reinsert_inline_images"]
        ).reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == final_markdown
    assert runtime["state"]["latest_docx_bytes"]

    output_doc = Document(BytesIO(runtime["state"]["latest_docx_bytes"]))
    visible_text = "\n".join(paragraph.text for paragraph in output_doc.paragraphs)

    assert output_doc.paragraphs[0].style is not None
    assert output_doc.paragraphs[0].style.name == "Normal"
    assert output_doc.paragraphs[2].style is not None
    assert output_doc.paragraphs[2].style.name == "Caption"
    assert "Обновленный абзац" in visible_text
    assert "[[DOCX_IMAGE_img_001]]" not in output_doc._element.xml
    assert len(output_doc.inline_shapes) == 1
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"
