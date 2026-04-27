import base64
import json
import logging
from io import BytesIO
from pathlib import Path

import pytest

import document_pipeline
import document_pipeline_late_phases
from docx import Document

from document import extract_document_content_from_docx
from models import ParagraphUnit


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
        "jobs": [{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
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
    }
    info_events = [event for event in events if event["level"] == logging.INFO]
    saved_event = next(event for event in info_events if event["event_id"] == "ui_result_artifacts_saved")
    assert saved_event["context"]["artifact_paths"] == {
        "markdown_path": "/tmp/mariana.result.md",
        "docx_path": "/tmp/mariana.result.docx",
    }


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
    def broken_loader(*, operation: str = "edit", source_language: str = "en", target_language: str = "ru", editorial_intensity: str = "literary", prompt_variant: str = "default"):
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
    assert runtime["activity"][-1] == "Итоговый перевод отклонён quality gate из-за потери paragraph mapping."
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "fail"
    assert payload["gate_reasons"] == ["unmapped_source_paragraphs_present"]


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
        "message": "Результат собран, но quality report зафиксировал заметный paragraph mapping drift.",
    }
    report_files = list(quality_dir.glob("*.json"))
    assert len(report_files) == 1
    payload = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert payload["quality_status"] == "warn"
    assert payload["gate_reasons"] == ["unmapped_source_paragraphs_above_advisory_threshold"]


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
        preserve_source_paragraph_properties=__import__("formatting_transfer").preserve_source_paragraph_properties,
        reinsert_inline_images=__import__("image_reinsertion").reinsert_inline_images,
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
