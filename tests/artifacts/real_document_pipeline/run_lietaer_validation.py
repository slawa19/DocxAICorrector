from __future__ import annotations

import queue
import threading
import traceback
from collections.abc import Mapping, Sequence
import json
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from docx import Document

import app_runtime
import application_flow
import document_pipeline
import logger as app_logger
import processing_runtime
import processing_service
from config import get_client, load_app_config, load_system_prompt
from document import (
    inspect_placeholder_integrity,
    normalize_semantic_output_docx,
    preserve_source_paragraph_properties,
    reinsert_inline_images,
)
from generation import (
    convert_markdown_to_docx_bytes,
    ensure_pandoc_available,
    generate_markdown_block,
)
from logger import present_error
from runtime_events import (
    AppendImageLogEvent,
    AppendLogEvent,
    FinalizeProcessingStatusEvent,
    PushActivityEvent,
    ResetImageStateEvent,
    SetProcessingStatusEvent,
    SetStateEvent,
)


service = processing_service.get_processing_service()


class UploadedFileStub:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            data = self._content[self._position :]
            self._position = len(self._content)
            return data
        start = self._position
        end = min(len(self._content), start + size)
        self._position = end
        return self._content[start:end]

    def getvalue(self) -> bytes:
        return self._content

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._position = max(0, offset)
        elif whence == 1:
            self._position = max(0, self._position + offset)
        elif whence == 2:
            self._position = max(0, len(self._content) + offset)
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        return self._position


def present_error_adapter(code: str, exc: Exception, title: str, **context: object) -> str:
    return present_error(code, exc, title, **context)


def emit_state_adapter(runtime: object, **values: object) -> None:
    app_runtime.emit_state(cast(Any, runtime), **values)


def emit_finalize_adapter(runtime: object, stage: str, detail: str, progress: float) -> None:
    app_runtime.emit_finalize(cast(Any, runtime), stage, detail, progress)


def emit_activity_adapter(runtime: object, message: str) -> None:
    app_runtime.emit_activity(cast(Any, runtime), message)


def emit_log_adapter(runtime: object, **payload: object) -> None:
    app_runtime.emit_log(cast(Any, runtime), **payload)


def emit_status_adapter(runtime: object, **payload: object) -> None:
    app_runtime.emit_status(cast(Any, runtime), **payload)


def should_stop_processing_adapter(runtime: object) -> bool:
    return processing_runtime.should_stop_processing(cast(Any, runtime))


def generate_markdown_block_adapter(
    *,
    client: object,
    model: str,
    system_prompt: str,
    target_text: str,
    context_before: str,
    context_after: str,
    max_retries: int,
) -> str:
    return generate_markdown_block(
        client=cast(Any, client),
        model=model,
        system_prompt=system_prompt,
        target_text=target_text,
        context_before=context_before,
        context_after=context_after,
        max_retries=max_retries,
    )


def process_document_images_adapter(
    *,
    image_assets: Sequence[object],
    image_mode: str,
    config: Mapping[str, object],
    on_progress,
    runtime: object,
    client: object,
):
    return service.process_document_images(
        image_assets=cast(Any, image_assets),
        image_mode=image_mode,
        config=dict(config),
        on_progress=on_progress,
        runtime=cast(Any, runtime),
        client=cast(Any, client),
    )


def inspect_placeholder_integrity_adapter(markdown_text: str, image_assets: Sequence[object]) -> Mapping[str, str]:
    return inspect_placeholder_integrity(markdown_text, cast(Any, list(image_assets)))


def preserve_source_paragraph_properties_adapter(docx_bytes: bytes, paragraphs: Sequence[object]) -> bytes:
    return preserve_source_paragraph_properties(docx_bytes, cast(Any, list(paragraphs)))


def normalize_semantic_output_docx_adapter(docx_bytes: bytes, paragraphs: Sequence[object]) -> bytes:
    return normalize_semantic_output_docx(docx_bytes, cast(Any, list(paragraphs)))


def reinsert_inline_images_adapter(docx_bytes: bytes, image_assets: Sequence[object]) -> bytes:
    return reinsert_inline_images(docx_bytes, cast(Any, list(image_assets)))


def drain_runtime_events(event_queue: queue.Queue, runtime_snapshot: dict) -> None:
    while True:
        try:
            event = event_queue.get_nowait()
        except queue.Empty:
            break

        if isinstance(event, SetStateEvent):
            runtime_snapshot.setdefault("state", {}).update(event.values)
        elif isinstance(event, ResetImageStateEvent):
            runtime_snapshot["image_reset_count"] = int(
                runtime_snapshot.get("image_reset_count", 0)
            ) + 1
        elif isinstance(event, SetProcessingStatusEvent):
            runtime_snapshot.setdefault("status", []).append(event.payload)
        elif isinstance(event, FinalizeProcessingStatusEvent):
            runtime_snapshot.setdefault("finalize", []).append(
                {
                    "stage": event.stage,
                    "detail": event.detail,
                    "progress": event.progress,
                }
            )
        elif isinstance(event, PushActivityEvent):
            runtime_snapshot.setdefault("activity", []).append(event.message)
        elif isinstance(event, AppendLogEvent):
            runtime_snapshot.setdefault("log", []).append(event.payload)
        elif isinstance(event, AppendImageLogEvent):
            runtime_snapshot.setdefault("image_log", []).append(event.payload)


def sanitize_for_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_for_json(item) for item in value]
    return app_logger.sanitize_log_context(value)


def classify_failure(report: dict) -> str | None:
    candidates = []
    last_error = str(report.get("last_error") or "")
    candidates.append(last_error)
    exc = report.get("exception") or {}
    if isinstance(exc, dict):
        candidates.append(str(exc.get("message") or ""))
        candidates.append(str(exc.get("traceback") or ""))
    for event in report.get("event_log", []):
        if isinstance(event, dict):
            candidates.append(str(event.get("event_id") or ""))
            candidates.append(json.dumps(event, ensure_ascii=False))
    joined = "\n".join(text for text in candidates if text)
    for marker in (
        "heading_only_output",
        "empty_processed_block",
        "empty_response",
        "collapsed_output",
        "unsupported_response_shape",
        "image_placeholder_integrity_failed",
        "docx_build_failed",
        "image_processing_failed",
        "processing_init_failed",
    ):
        if marker in joined:
            return marker
    if report.get("result") == "failed":
        return "failed_unclassified"
    if report.get("result") == "stopped":
        return "stopped"
    return None


def is_heading_only_markdown(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("#") and len(line.split()) >= 2 for line in lines)


def main() -> None:
    source_path = Path("tests/sources/Лиетар глава1.docx")
    artifact_dir = Path("tests/artifacts/real_document_pipeline")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    for handler in app_logger.get_logger().handlers:
        if hasattr(handler, "maxBytes"):
            setattr(handler, "maxBytes", 1_000_000_000)

    report_path = artifact_dir / "lietaer_validation_report.json"
    summary_path = artifact_dir / "lietaer_validation_summary.txt"
    markdown_artifact = artifact_dir / "Лиетар глава1_validated.md"
    docx_artifact = artifact_dir / "Лиетर глава1_validated.docx"

    progress_events = []
    event_log = []
    event_queue: queue.Queue = queue.Queue()
    runtime = processing_runtime.BackgroundRuntime(event_queue, threading.Event())
    runtime_snapshot = {
        "state": {},
        "finalize": [],
        "activity": [],
        "log": [],
        "status": [],
        "image_log": [],
        "image_reset_count": 0,
    }

    source_bytes = source_path.read_bytes()
    uploaded_payload = processing_runtime.freeze_uploaded_file(
        UploadedFileStub(source_path.name, source_bytes)
    )
    app_config = load_app_config()

    prepared = application_flow.prepare_run_context_for_background(
        uploaded_payload=uploaded_payload,
        chunk_size=app_config.chunk_size,
        image_mode=app_config.image_mode_default,
        keep_all_image_variants=app_config.keep_all_image_variants,
        progress_callback=lambda **payload: progress_events.append(
            {"phase": "prepare", **payload}
        ),
    )

    result = "not_started"
    exception_payload = None

    def log_event_capture(level, event_id, message, **context):
        event_log.append(
            {
                "level": level,
                "event_id": event_id,
                "message": message,
                "context": context,
            }
        )

    try:
        result = document_pipeline.run_document_processing(
            uploaded_file=prepared.uploaded_filename,
            jobs=prepared.jobs,
            source_paragraphs=prepared.paragraphs,
            image_assets=prepared.image_assets,
            image_mode=app_config.image_mode_default,
            app_config=app_config.to_dict(),
            model=app_config.default_model,
            max_retries=app_config.max_retries,
            on_progress=lambda **payload: progress_events.append(
                {"phase": "process", **payload}
            ),
            runtime=runtime,
            resolve_uploaded_filename=processing_runtime.resolve_uploaded_filename,
            get_client=get_client,
            ensure_pandoc_available=ensure_pandoc_available,
            load_system_prompt=load_system_prompt,
            log_event=log_event_capture,
            present_error=present_error_adapter,
            emit_state=emit_state_adapter,
            emit_finalize=emit_finalize_adapter,
            emit_activity=emit_activity_adapter,
            emit_log=emit_log_adapter,
            emit_status=emit_status_adapter,
            should_stop_processing=should_stop_processing_adapter,
            generate_markdown_block=generate_markdown_block_adapter,
            process_document_images=process_document_images_adapter,
            inspect_placeholder_integrity=inspect_placeholder_integrity_adapter,
            convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
            preserve_source_paragraph_properties=preserve_source_paragraph_properties_adapter,
            normalize_semantic_output_docx=normalize_semantic_output_docx_adapter,
            reinsert_inline_images=reinsert_inline_images_adapter,
        )
    except Exception as exc:
        exception_payload = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }

    drain_runtime_events(event_queue, runtime_snapshot)

    state = runtime_snapshot.get("state", {})
    final_markdown = str(state.get("latest_markdown") or "")
    latest_docx_bytes = state.get("latest_docx_bytes")
    last_error = str(state.get("last_error") or "")
    source_chars = len(prepared.source_text)
    final_markdown_chars = len(final_markdown)
    output_ratio = round(final_markdown_chars / max(source_chars, 1), 3)

    block_completed_events = [
        event for event in event_log if event.get("event_id") == "block_completed"
    ]
    block_rejected_events = [
        event for event in event_log if event.get("event_id") == "block_rejected"
    ]
    block_output_ratios = [
        event.get("context", {}).get("output_ratio")
        for event in block_completed_events
        if isinstance(event.get("context", {}).get("output_ratio"), (int, float))
    ]

    openable_output = False
    output_paragraphs = 0
    output_inline_shapes = 0
    output_visible_text_chars = 0
    output_contains_placeholder_markup = False

    if final_markdown:
        markdown_artifact.write_text(final_markdown, encoding="utf-8")

    if isinstance(latest_docx_bytes, (bytes, bytearray)) and latest_docx_bytes:
        latest_docx_bytes = bytes(latest_docx_bytes)
        docx_artifact.write_bytes(latest_docx_bytes)
        try:
            output_doc = Document(BytesIO(latest_docx_bytes))
            openable_output = True
            output_paragraphs = len(output_doc.paragraphs)
            output_inline_shapes = len(output_doc.inline_shapes)
            output_visible_text_chars = len(
                "\n".join(paragraph.text for paragraph in output_doc.paragraphs)
            )
            output_contains_placeholder_markup = (
                "[[DOCX_IMAGE_" in output_doc._element.xml
            )
        except Exception:
            openable_output = False

    report = {
        "source_file": str(source_path),
        "artifact_dir": str(artifact_dir),
        "result": result,
        "model": app_config.default_model,
        "chunk_size": app_config.chunk_size,
        "max_retries": app_config.max_retries,
        "image_mode": app_config.image_mode_default,
        "preparation": {
            "uploaded_filename": prepared.uploaded_filename,
            "uploaded_file_token": prepared.uploaded_file_token,
            "paragraph_count": len(prepared.paragraphs),
            "image_count": len(prepared.image_assets),
            "job_count": len(prepared.jobs),
            "source_chars": source_chars,
            "cached": prepared.preparation_cached,
            "elapsed_seconds": round(prepared.preparation_elapsed_seconds, 3),
        },
        "runtime": runtime_snapshot,
        "last_error": last_error,
        "exception": exception_payload,
        "failure_classification": None,
        "signals": {
            "heading_only_output_detected": is_heading_only_markdown(final_markdown),
            "heading_only_rejection_logged": bool(block_rejected_events),
            "silent_text_loss_suspected": bool(final_markdown.strip()) and output_ratio < 0.6,
            "output_ratio_vs_source_text": output_ratio,
            "min_block_output_ratio": min(block_output_ratios) if block_output_ratios else None,
            "max_block_output_ratio": max(block_output_ratios) if block_output_ratios else None,
            "image_reset_emitted": runtime_snapshot.get("image_reset_count", 0),
        },
        "output_artifacts": {
            "markdown_path": str(markdown_artifact) if final_markdown else None,
            "docx_path": str(docx_artifact)
            if isinstance(latest_docx_bytes, (bytes, bytearray)) and latest_docx_bytes
            else None,
            "output_docx_openable": openable_output,
            "output_paragraphs": output_paragraphs,
            "output_inline_shapes": output_inline_shapes,
            "output_visible_text_chars": output_visible_text_chars,
            "output_contains_placeholder_markup": output_contains_placeholder_markup,
            "report_json": str(report_path),
            "summary_txt": str(summary_path),
        },
        "progress_events_tail": progress_events[-12:],
        "event_log": event_log[-25:],
        "image_log_tail": runtime_snapshot.get("image_log", [])[-25:],
    }
    report["failure_classification"] = classify_failure(report)
    sanitized_report = sanitize_for_json(report)

    summary_lines = [
        f"source={source_path}",
        f"result={report['result']}",
        f"failure_classification={report['failure_classification']}",
        f"model={report['model']}",
        f"chunk_size={report['chunk_size']}",
        f"max_retries={report['max_retries']}",
        f"image_mode={report['image_mode']}",
        f"paragraph_count={report['preparation']['paragraph_count']}",
        f"image_count={report['preparation']['image_count']}",
        f"job_count={report['preparation']['job_count']}",
        f"source_chars={report['preparation']['source_chars']}",
        f"final_markdown_chars={final_markdown_chars}",
        f"output_ratio_vs_source_text={report['signals']['output_ratio_vs_source_text']}",
        f"min_block_output_ratio={report['signals']['min_block_output_ratio']}",
        f"heading_only_output_detected={report['signals']['heading_only_output_detected']}",
        f"heading_only_rejection_logged={report['signals']['heading_only_rejection_logged']}",
        f"silent_text_loss_suspected={report['signals']['silent_text_loss_suspected']}",
        f"image_reset_emitted={report['signals']['image_reset_emitted']}",
        f"output_docx_openable={report['output_artifacts']['output_docx_openable']}",
        f"output_inline_shapes={report['output_artifacts']['output_inline_shapes']}",
        f"output_contains_placeholder_markup={report['output_artifacts']['output_contains_placeholder_markup']}",
        f"last_error={last_error}",
        f"markdown_path={report['output_artifacts']['markdown_path']}",
        f"docx_path={report['output_artifacts']['docx_path']}",
    ]
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    report_path.write_text(
        json.dumps(sanitized_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(sanitized_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
