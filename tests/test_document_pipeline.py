import base64
import json
import logging
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


def test_run_document_processing_normalizes_false_fragment_headings_before_quality_gate(tmp_path, monkeypatch):
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

    report_files = list(quality_dir.glob("*.json"))
    if report_files:
        payload = json.loads(report_files[0].read_text(encoding="utf-8"))
        assert payload["quality_status"] == "pass", json.dumps(payload, ensure_ascii=False, indent=2)

    assert result == "succeeded"
    assert "## (Матфея 24:36)" not in runtime["state"]["latest_markdown"]
    assert "## Спутники? Ракеты?)" not in runtime["state"]["latest_markdown"]
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "pass"
    assert payload["false_fragment_heading_count"] == 0


def test_run_document_processing_quality_report_uses_runtime_normalized_heading_text_for_sentence_split_case(tmp_path, monkeypatch):
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

    assert result == "succeeded"
    assert "## Великая скорбь\n\n." not in runtime["state"]["latest_markdown"]
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "pass"
    assert payload["false_fragment_heading_count"] == 0


def test_run_document_processing_normalizes_residual_bullet_glyphs_before_quality_gate(tmp_path, monkeypatch):
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
    assert payload["residual_bullet_glyph_count"] == 0


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

    assert report["quality_status"] == "fail"
    assert report["gate_reasons"] == ["bullet_marker_headings_present"]
    assert report["bullet_heading_count"] == 1


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

    assert report["quality_status"] == "fail"
    assert report["gate_reasons"] == ["toc_body_concatenation_detected"]
    assert report["toc_body_concat_detected"] is True


def test_normalize_final_markdown_for_runtime_display_splits_placeholder_from_chapter_heading():
    normalized = document_pipeline_late_phases._normalize_final_markdown_for_runtime_display(
        "This page intentionally left blank Chapter Nine STRATEGIES FOR NGO S"
    )

    assert normalized == "This page intentionally left blank\n\nChapter Nine STRATEGIES FOR NGO S"


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
        "residual_bullet_glyphs_present",
        "list_fragment_regressions_present",
        "mixed_script_terms_present",
    ]
    assert report["bullet_heading_count"] == 0
    assert report["false_fragment_heading_count"] == 0
    assert report["scripture_reference_heading_count"] == 0
    assert report["residual_bullet_glyph_count"] == 1
    assert report["list_fragment_regression_count"] == 1
    mixed_script_term_count = report["mixed_script_term_count"]
    theology_style_issue_count = report["theology_style_deterministic_issue_count"]
    assert isinstance(mixed_script_term_count, int)
    assert isinstance(theology_style_issue_count, int)
    assert mixed_script_term_count >= 1
    assert theology_style_issue_count >= 2
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

def test_run_document_processing_fails_on_strict_structural_markdown_quality_gate(tmp_path, monkeypatch):
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

    assert result == "failed"
    assert "translation_quality_gate_failed" in runtime["state"]["last_error"]
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "fail"
    assert payload["gate_reasons"] == ["toc_body_concatenation_detected"]
    assert payload["bullet_heading_count"] == 0
    assert payload["toc_body_concat_detected"] is True
    assert runtime["activity"][-1] == "Итоговый перевод отклонён quality gate: toc_body_concatenation_detected."


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
        "message": "Результат собран, но quality report зафиксировал document-level structural warnings.",
    }
    assert artifact_calls["kwargs"]["quality_warning"]["gate_reasons"] == ["toc_body_concatenation_detected"]
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "warn"
    assert payload["gate_reasons"] == ["toc_body_concatenation_detected"]
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

    assert result == "failed"
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "fail"
    assert payload["gate_reasons"] == ["toc_body_concatenation_detected"]
    assert payload["toc_body_concat_gate_source"] == "legacy_markdown"
    assert payload["toc_body_concat_markdown_detected"] is True
    assert payload["toc_body_concat_structure_detected"] is False
    assert payload["toc_body_concat_detected"] is True


def test_build_translation_quality_report_exposes_structure_unit_unmapped_basis_without_raw_override(monkeypatch):
    monkeypatch.setattr(
        document_pipeline_late_phases,
        "_load_formatting_diagnostics_payloads",
        lambda artifact_paths: [{"unmapped_source_ids": ["p0000", "p0001"], "unmapped_target_indexes": [], "source_count": 2, "target_count": 2}],
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
    assert report["structure_unit_unmapped_source_count"] == 1
    assert report["unmapped_source_count_basis"] == "topology_unit"
    assert report["unmapped_source_count"] == 1


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

    def should_stop(_runtime):
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
