import base64
import json
import logging
from io import BytesIO
from pathlib import Path

import pytest

import document_pipeline
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
        "load_system_prompt": lambda: "system",
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
        "preserve_source_paragraph_properties": lambda docx_bytes, paragraphs: docx_bytes,
        "normalize_semantic_output_docx": lambda docx_bytes, paragraphs: docx_bytes,
        "reinsert_inline_images": _reinsert_inline_images,
    }
    params.update(overrides)
    return document_pipeline.run_document_processing(**params)


def _capture_log_events():
    events = []

    def _log_event(level, event_id, message, **context):
        events.append({"level": level, "event_id": event_id, "message": message, "context": context})

    return events, _log_event


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
        load_system_prompt=lambda: "system",
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
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
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
        app_config={},
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
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: b"final-docx",
    )

    assert result == "succeeded"
    assert captured["prompt"] == {
        "operation": "translate",
        "source_language": "en",
        "target_language": "de",
    }


def test_resolve_system_prompt_does_not_mask_internal_type_errors():
    def broken_loader(*, operation: str = "edit", source_language: str = "en", target_language: str = "ru"):
        raise TypeError("broken template")

    with pytest.raises(TypeError, match="broken template"):
        document_pipeline._resolve_system_prompt(
            broken_loader,
            operation="translate",
            source_language="en",
            target_language="de",
        )


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
        load_system_prompt=lambda: "system",
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
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: call_order.append("preserve") or docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: call_order.append("normalize") or docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: call_order.append("reinsert") or docx_bytes,
    )

    assert result == "succeeded"
    # Pipeline order is unchanged; after the unified restore in preserve, normalize is expected to be a safe no-op.
    assert call_order == ["convert", "preserve", "normalize", "reinsert"]


def test_run_document_processing_surfaces_formatting_diagnostics_artifacts(tmp_path, monkeypatch):
    runtime = _build_runtime_capture()
    diagnostics_dir = tmp_path / "formatting_diagnostics"
    monkeypatch.setattr(document_pipeline, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)

    def preserve_with_artifact(docx_bytes, paragraphs):
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
        load_system_prompt=lambda: "system",
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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
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

    def preserve_with_conflict_artifact(docx_bytes, paragraphs):
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
        load_system_prompt=lambda: "system",
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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
    )

    assert result == "succeeded"
    assert runtime["activity"][-2] == "Сборка DOCX завершена; найдены места, где форматирование стоит проверить вручную."
    assert runtime["log"][-2]["status"] == "WARN"
    assert "спорные места форматирования" in runtime["log"][-2]["details"]
    assert "Конфликтов подписи/заголовка: 1." in runtime["log"][-2]["details"]
    assert runtime["state"].get("latest_result_notice") is None


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
        load_system_prompt=lambda: "system",
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
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
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
    normalize_calls = []

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
        load_system_prompt=lambda: "system",
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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: normalize_calls.append(generated_paragraph_registry) or docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    expected_registry = [{"block_index": 1, "paragraph_id": "p0001", "text": "Очищенный блок"}]
    # Registry is still threaded into both callbacks even though the effective restore work now happens in preserve.
    assert preserve_calls == [expected_registry]
    assert normalize_calls == [expected_registry]


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
        load_system_prompt=lambda: "system",
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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
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
        load_system_prompt=lambda: "system",
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
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
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
        load_system_prompt=lambda: "system",
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
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
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
        load_system_prompt=lambda: "system",
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
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "stopped"
    assert runtime["finalize"][-1][0] == "Остановлено пользователем"
    assert runtime["finalize"][-1][3] == "stopped"
    assert runtime["log"][-1]["status"] == "STOP"


def test_run_document_processing_fails_on_empty_processed_block():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "   ",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["last_error"].endswith("empty_processed_block).")
    assert runtime["finalize"][-1][0] == "Критическая ошибка"
    assert runtime["finalize"][-1][3] == "error"
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_rejects_heading_only_output_for_body_heavy_input():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "# Заголовок\n\nЭто полноценный абзац с несколькими словами и знаками препинания.",
            "context_before": "",
            "context_after": "",
            "target_chars": 71,
            "context_chars": 0,
        }],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "# Heading only",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert "heading_only_output" in runtime["state"]["last_error"]
    assert runtime["state"].get("latest_docx_bytes") is None
    assert runtime["finalize"][-1][0] == "Критическая ошибка"
    assert runtime["finalize"][-1][3] == "error"
    assert runtime["activity"][-1] == "Блок 1: отклонён структурно недостаточный Markdown."
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_accepts_heading_only_output_for_legitimate_heading_only_input():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "# Heading only", "context_before": "", "context_after": "", "target_chars": 14, "context_chars": 0}],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "# Heading only",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "# Heading only"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"


def test_run_document_processing_accepts_heading_only_output_for_uppercase_title_input():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "РАЗВИТИЕ МЕСТНОЙ ЭКОНОМИКИ С ПОМОЩЬЮ МЕСТНЫХ ВАЛЮТ",
            "context_before": "",
            "context_after": "",
            "target_chars": 50,
            "context_chars": 0,
        }],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "## Развитие местной экономики с помощью местных валют",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "## Развитие местной экономики с помощью местных валют"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"


def test_run_document_processing_accepts_heading_only_output_for_table_of_contents_line():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Предисловие Денниса Мидоуза Предисловие Хантера Ловинса Благодарности",
            "context_before": "",
            "context_after": "",
            "target_chars": 69,
            "context_chars": 0,
        }],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "## Предисловия и благодарности",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "## Предисловия и благодарности"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"


def test_run_document_processing_accepts_heading_only_output_for_colon_section_title():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Часть II: Примеры дополнительных валют",
            "context_before": "",
            "context_after": "",
            "target_chars": 38,
            "context_chars": 0,
        }],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "## Часть II: Примеры дополнительных валют",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "## Часть II: Примеры дополнительных валют"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"


def test_run_document_processing_accepts_heading_only_output_for_plaintext_banner_input():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "РАСТУЩЕЕ\tМЕСТНЫХ\tЭКОНОМИКИ С\tМЕСТНЫМИ\tВАЛЮТАМИ",
            "context_before": "",
            "context_after": "",
            "target_chars": 46,
            "context_chars": 0,
        }],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "## Развитие местных экономик с помощью местных валют",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "## Развитие местных экономик с помощью местных валют"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"


def test_run_document_processing_fails_on_empty_processing_plan():
    runtime = _build_runtime_capture()
    runtime["state"]["latest_docx_bytes"] = b"stale-docx"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == ""
    assert runtime["state"]["processed_block_markdowns"] == []
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка подготовки обработки: План обработки документа пуст."
    assert runtime["finalize"][-1] == (
        "Ошибка подготовки обработки",
        "Ошибка подготовки обработки: План обработки документа пуст.",
        0.0,
        "error",
    )
    assert runtime["activity"][-1] == "Обработка документа остановлена: не найдено ни одного блока для обработки."
    assert runtime["log"][-1]["status"] == "ERROR"
    assert runtime["log"][-1]["block_count"] == 0


def test_run_document_processing_fails_on_initialization_and_clears_stale_runtime_state():
    runtime = _build_runtime_capture()
    runtime["state"].update(
        {
            "latest_docx_bytes": b"stale-docx",
            "latest_markdown": "stale-markdown",
            "processed_block_markdowns": ["stale-block"],
        }
    )

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
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
        ensure_pandoc_available=lambda: (_ for _ in ()).throw(RuntimeError("pandoc is unavailable")),
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == ""
    assert runtime["state"]["processed_block_markdowns"] == []
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка инициализации обработки: pandoc is unavailable"
    assert runtime["finalize"][-1] == (
        "Ошибка инициализации",
        "Ошибка инициализации обработки: pandoc is unavailable",
        0.0,
        "error",
    )


def test_run_document_processing_fails_when_process_document_images_raises():
    runtime = _build_runtime_capture()
    runtime["state"]["latest_docx_bytes"] = b"stale-docx"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("image pipeline exploded")),
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка обработки изображений: image pipeline exploded"
    assert runtime["finalize"][-1] == (
        "Ошибка обработки изображений",
        "Ошибка обработки изображений: image pipeline exploded",
        1.0,
        "error",
    )
    assert runtime["activity"][-1] == "Ошибка на этапе обработки изображений документа."
    assert runtime["log"][-1]["status"] == "ERROR"
    assert runtime["log"][-1]["block_index"] == 1


def test_run_document_processing_fails_when_process_document_images_returns_none():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: None,
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["last_error"] == (
        "Ошибка обработки изображений: Пайплайн обработки изображений вернул None вместо коллекции ассетов."
    )
    assert runtime["finalize"][-1][0] == "Ошибка обработки изображений"
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_when_placeholder_integrity_check_raises():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: [AssetStub("img_001")],
        inspect_placeholder_integrity=lambda markdown_text, image_assets: (_ for _ in ()).throw(RuntimeError("placeholder integrity exploded")),
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["last_error"] == "Ошибка обработки изображений: placeholder integrity exploded"
    assert runtime["finalize"][-1][0] == "Ошибка обработки изображений"
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_on_invalid_job_shape():
    runtime = _build_runtime_capture()
    runtime["state"]["latest_docx_bytes"] = b"stale-docx"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "context_chars": 0}],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == ""
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка на блоке 1: Ошибка подготовки блока: 'target_chars'"
    assert runtime["finalize"][-1] == (
        "Ошибка подготовки блока",
        "Ошибка на блоке 1: Ошибка подготовки блока: 'target_chars'",
        0.0,
        "error",
    )
    assert runtime["activity"][-1] == "Блок 1: некорректный план обработки."
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_on_none_target_text_without_stringifying_none():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": None, "context_before": "", "context_after": "", "target_chars": 0, "context_chars": 0}],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["last_error"] == "Ошибка на блоке 1: Ошибка подготовки блока: target_text is None"


def test_run_document_processing_fails_on_missing_placeholder_status_entries():
    runtime = _build_runtime_capture()
    image_assets = [AssetStub("img_001")]

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "[[DOCX_IMAGE_img_001]]", "context_before": "", "context_after": "", "target_chars": 21, "context_chars": 0}],
        source_paragraphs=[],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "[[DOCX_IMAGE_img_001]]",
        process_document_images=lambda **kwargs: image_assets,
        inspect_placeholder_integrity=lambda markdown_text, image_assets: {},
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["last_error"].startswith("Критическая ошибка подготовки изображений")


def test_run_document_processing_preserves_passthrough_image_block_without_openai_call():
    runtime = _build_runtime_capture()
    image_assets = [AssetStub("img_001")]
    generate_calls = []
    inspected_markdowns = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"job_kind": "llm", "target_text": "Вступление", "context_before": "", "context_after": "", "target_chars": 10, "context_chars": 0},
            {"job_kind": "passthrough", "target_text": "[[DOCX_IMAGE_img_001]]", "context_before": "", "context_after": "", "target_chars": 21, "context_chars": 0},
            {"job_kind": "llm", "target_text": "Основной текст", "context_before": "", "context_after": "", "target_chars": 14, "context_chars": 0},
        ],
        source_paragraphs=[],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generate_calls.append(kwargs["target_text"]) or f"ok:{kwargs['target_text']}",
        process_document_images=lambda **kwargs: image_assets,
        inspect_placeholder_integrity=lambda markdown_text, image_assets: inspected_markdowns.append(markdown_text) or {asset.image_id: "ok" for asset in image_assets},
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert generate_calls == ["Вступление", "Основной текст"]
    assert inspected_markdowns == ["ok:Вступление\n\n[[DOCX_IMAGE_img_001]]\n\nok:Основной текст"]
    assert runtime["state"]["latest_markdown"] == "ok:Вступление\n\n[[DOCX_IMAGE_img_001]]\n\nok:Основной текст"


def test_run_document_processing_passthrough_only_does_not_require_system_prompt():
    runtime = _build_runtime_capture()
    image_assets = [AssetStub("img_001")]
    generate_calls = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"job_kind": "passthrough", "target_text": "[[DOCX_IMAGE_img_001]]", "context_before": "", "context_after": "", "target_chars": 21, "context_chars": 0},
        ],
        source_paragraphs=[],
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
        load_system_prompt=lambda: (_ for _ in ()).throw(RuntimeError("prompt exploded")),
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generate_calls.append(kwargs["target_text"]) or "unexpected",
        process_document_images=lambda **kwargs: image_assets,
        inspect_placeholder_integrity=lambda markdown_text, image_assets: {asset.image_id: "ok" for asset in image_assets},
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert generate_calls == []
    assert runtime["state"]["latest_markdown"] == "[[DOCX_IMAGE_img_001]]"


def test_run_document_processing_detects_processed_block_count_mismatch():
    runtime = _build_runtime_capture()
    jobs = PlannedJobs(
        [{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        planned_len=2,
    )

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=jobs,
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["finalize"][-1][0] == "Критическая ошибка"
    assert runtime["activity"][-1] == "Обнаружено несоответствие количества обработанных блоков."


def test_run_document_processing_fails_when_convert_markdown_to_docx_bytes_raises():
    runtime = _build_runtime_capture()

    result = _run_processing(
        runtime,
        convert_markdown_to_docx_bytes=lambda markdown_text: (_ for _ in ()).throw(RuntimeError("convert exploded")),
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка сборки DOCX: convert exploded"
    assert runtime["finalize"][-1] == ("Ошибка сборки DOCX", "Ошибка сборки DOCX: convert exploded", 1.0, "error")
    assert runtime["activity"][-1] == "Ошибка на этапе сборки DOCX."
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_when_preserve_source_paragraph_properties_raises():
    runtime = _build_runtime_capture()

    result = _run_processing(
        runtime,
        source_paragraphs=[ParagraphStub()],
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: (_ for _ in ()).throw(RuntimeError("preserve exploded")),
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка сборки DOCX: preserve exploded"
    assert runtime["finalize"][-1][0] == "Ошибка сборки DOCX"
    assert runtime["activity"][-1] == "Ошибка на этапе сборки DOCX."
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_when_normalize_semantic_output_docx_raises():
    runtime = _build_runtime_capture()

    result = _run_processing(
        runtime,
        source_paragraphs=[ParagraphStub()],
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: (_ for _ in ()).throw(RuntimeError("normalize exploded")),
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка сборки DOCX: normalize exploded"
    assert runtime["finalize"][-1][0] == "Ошибка сборки DOCX"
    assert runtime["activity"][-1] == "Ошибка на этапе сборки DOCX."
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_when_reinsert_inline_images_raises():
    runtime = _build_runtime_capture()
    image_assets = [AssetStub("img_001")]

    result = _run_processing(
        runtime,
        image_assets=image_assets,
        process_document_images=lambda **kwargs: image_assets,
        reinsert_inline_images=lambda docx_bytes, processed_assets: (_ for _ in ()).throw(RuntimeError("reinsert exploded")),
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка сборки DOCX: reinsert exploded"
    assert runtime["finalize"][-1][0] == "Ошибка сборки DOCX"
    assert runtime["activity"][-1] == "Ошибка на этапе сборки DOCX."
    assert runtime["log"][-1]["status"] == "ERROR"


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
        normalize_semantic_output_docx=__import__("formatting_transfer").normalize_semantic_output_docx,
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
