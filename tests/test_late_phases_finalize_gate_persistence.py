"""Behaviour tests for two pipeline-correctness fixes in
``pipeline/late_phases.finalize_processing_success``:

- **F4** — an artifact-save (``write_ui_result_artifacts``) OSError must stop being a
  silent success: the delivered result still reaches session state, but the terminal
  log becomes a DISTINCT WARNING ``processing_completed_unpersisted`` (not INFO
  ``processing_completed``) and a user-visible WARNING result notice is emitted.
- **F10** — the reader-cleanup post-pass REPLACES the delivered markdown AFTER the
  pre-cleanup gate ran, so a cleanup-introduced regression must be re-gated on the
  DELIVERED markdown and BLOCKED (``translation_quality_gate_failed_post_cleanup``)
  when it flips to fail. When cleanup leaves the markdown unchanged the re-gate is
  skipped entirely (no behaviour change); when it changes but still passes, the run
  completes normally.

The heavy collaborators (quality-report builder, acceptance verdict, reader-cleanup
post-pass, narration, reassembly, artifact writer) are stubbed so the test exercises
only the finalize control flow these two fixes touch. Everything is offline.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from types import SimpleNamespace

import pytest

import docxaicorrector.pipeline.late_phases as late_phases
import docxaicorrector.pipeline.quality_gate as quality_gate
import docxaicorrector.pipeline.reader_cleanup_postprocess as reader_cleanup_postprocess
import docxaicorrector.processing.processing_runtime as processing_runtime
import docxaicorrector.ui._app as app
import docxaicorrector.ui._ui as result_ui

# Captured at import time, before any test stubs it, so Finding 7's test can restore the
# REAL acceptance-verdict builder over ``_install_stubs``' lightweight stub.
_REAL_BUILD_VERDICT = late_phases.build_report_acceptance_verdict


class _RecordingEmitters:
    def __init__(self) -> None:
        self.state_calls: list[dict[str, object]] = []
        self.finalize_calls: list[dict[str, object]] = []
        self.activity_calls: list[str] = []
        self.log_calls: list[dict[str, object]] = []

    def emit_state(self, runtime, **values):
        self.state_calls.append(values)

    def emit_finalize(self, runtime, stage, detail, progress, terminal_kind=None):
        self.finalize_calls.append(
            {"stage": stage, "detail": detail, "progress": progress, "terminal_kind": terminal_kind}
        )

    def emit_activity(self, runtime, message):
        self.activity_calls.append(message)

    def emit_log(self, runtime, **payload):
        self.log_calls.append(payload)


class _RecordingDependencies:
    def __init__(self, *, artifact_writer) -> None:
        self.events: list[tuple[int, str, str, dict[str, object]]] = []
        self.write_ui_result_artifacts_calls = 0
        self._artifact_writer = artifact_writer
        self.should_stop_processing: Callable[[object], bool] = lambda runtime: False
        self.get_client: Callable[[], object] = lambda: object()

    def log_event(self, level, event, message, **context):
        self.events.append((level, event, message, context))

    def present_error(self, code, exc, title, **kwargs):
        return f"{title}: {exc}"

    def write_ui_result_artifacts(self, **kwargs):
        self.write_ui_result_artifacts_calls += 1
        return self._artifact_writer()

    def write_segment_result_registry(self, *, records):
        return {}


def _events(deps: _RecordingDependencies) -> list[str]:
    return [event for _level, event, _msg, _ctx in deps.events]


def _event(deps: _RecordingDependencies, name: str) -> tuple[int, dict[str, object]]:
    for level, event, _msg, ctx in deps.events:
        if event == name:
            return level, ctx
    raise AssertionError(f"event not found: {name}")


def _state_mapping_value(
    state_call: Mapping[str, object],
    state_key: str,
    nested_key: str,
) -> object | None:
    value = state_call.get(state_key)
    return value.get(nested_key) if isinstance(value, Mapping) else None


def _cleanup_result(*, markdown: str, docx_bytes: bytes = b"final-docx"):
    return late_phases.ReaderCleanupPostprocessResult(
        markdown=markdown,
        docx_bytes=docx_bytes,
        report=None,
        raw_markdown=None,
        result_notice=None,
        final_generated_paragraph_registry=None,
    )


def _real_primary_artifact_writer(tmp_path, *, extra=None):
    """Return a ``write_ui_result_artifacts`` stub that actually writes non-empty
    primary files (``markdown_path`` + ``docx_path``) to ``tmp_path`` — the shape
    Finding 13 requires for a genuine persistence success."""

    def _write():
        markdown_path = tmp_path / "report.result.md"
        docx_path = tmp_path / "report.result.docx"
        markdown_path.write_text("итоговый markdown", encoding="utf-8")
        docx_path.write_bytes(b"PK\x03\x04 final-docx bytes")
        paths = {"markdown_path": str(markdown_path), "docx_path": str(docx_path)}
        if extra:
            paths.update(extra)
        return paths

    return _write


def _install_stubs(monkeypatch, *, gate_input_markdown, cleanup_result, report_fn):
    assembly = SimpleNamespace(final_markdown=gate_input_markdown, entries=(), diagnostics=None)
    monkeypatch.setattr(late_phases, "assemble_final_markdown", lambda **k: assembly)
    monkeypatch.setattr(late_phases, "_build_translation_quality_report", report_fn)
    monkeypatch.setattr(late_phases, "build_report_acceptance_verdict", lambda *a, **k: {})
    monkeypatch.setattr(late_phases, "_write_quality_report_artifact", lambda **k: None)
    monkeypatch.setattr(late_phases, "_run_reader_cleanup_postprocess", lambda **k: cleanup_result)
    monkeypatch.setattr(late_phases, "_build_narration_text", lambda **k: None)
    monkeypatch.setattr(
        late_phases,
        "build_reassembly_plan",
        lambda **k: SimpleNamespace(assembly_mode="whole", selected_segment_count=None),
    )
    monkeypatch.setattr(late_phases, "build_segment_result_records", lambda **k: [])


def _make_context():
    return SimpleNamespace(
        app_config={},
        processing_operation="translate",
        uploaded_filename="report.docx",
        runtime={},
        output_mode="",
        jobs=[],
        source_paragraphs=[],
        model="",
        max_retries=0,
        run_id="run-main",
        source_token="source-main",
    )


def _make_state():
    return SimpleNamespace(
        processed_chunks=["текст"],
        generated_paragraph_registry=[],
        started_at=time.perf_counter(),
        excluded_narration_block_count=0,
    )


def _make_docx_phase(gate_input_markdown):
    return {
        "runtime_display_markdown": gate_input_markdown,
        "latest_result_notice": None,
        "result_manifest": {"manifest": True},
        "base_docx_builder": None,
        "processed_image_assets": [],
        "pre_cleanup_formatting_baseline": None,
    }


def _run_finalize(*, context, dependencies, emitters, state, docx_phase):
    return late_phases.finalize_processing_success(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        docx_phase=docx_phase,
        job_count=1,
        current_markdown_fn=lambda chunks: "",
    )


# --------------------------------------------------------------------------- #
# F4 — artifact-save failure must be terminal-visible, not a silent success.
# --------------------------------------------------------------------------- #


def test_finalize_artifact_save_oserror_is_terminal_visible_but_still_succeeds(monkeypatch):
    gate_input = "Чистый переведённый абзац."

    def _report(**kwargs):
        return {"quality_status": "pass", "gate_reasons": []}

    # Cleanup leaves the markdown unchanged (re-gate must NOT fire), delivers a DOCX.
    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=_report)

    def _raise_oserror():
        raise OSError("disk full")

    deps = _RecordingDependencies(artifact_writer=_raise_oserror)
    emitters = _RecordingEmitters()

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    # The run still genuinely produced a delivered result.
    assert result == "succeeded"

    # The result markdown + DOCX were still delivered to session state.
    delivered = [
        call
        for call in emitters.state_calls
        if call.get("latest_markdown") == gate_input and call.get("latest_docx_bytes") == b"final-docx"
    ]
    assert delivered, "delivered markdown/docx did not reach emit_state"

    # A user-visible WARNING result notice reached state.
    warning_notices: list[dict[str, object]] = []
    for call in emitters.state_calls:
        notice = call.get("latest_result_notice")
        if isinstance(notice, dict) and notice.get("level") == "warning":
            warning_notices.append(notice)
    assert warning_notices, "no warning result-notice reached state"
    assert "сохранить файлы результата" in str(warning_notices[-1]["message"])

    # The failed persistence was logged.
    assert "ui_result_artifacts_save_failed" in _events(deps)

    # Terminal log is the DISTINCT WARNING event, NOT the INFO completed event.
    assert "processing_completed_unpersisted" in _events(deps)
    assert "processing_completed" not in _events(deps)
    level, ctx = _event(deps, "processing_completed_unpersisted")
    assert level == logging.WARNING
    assert "reason" in ctx
    # Progress frame is still "completed".
    assert any(call["terminal_kind"] == "completed" for call in emitters.finalize_calls)


def test_finalize_artifact_save_success_logs_completed_info(monkeypatch, tmp_path):
    """Companion: when persistence succeeds the terminal log stays INFO
    ``processing_completed`` and no unpersisted-warning notice is emitted."""
    gate_input = "Чистый переведённый абзац."

    def _report(**kwargs):
        return {"quality_status": "pass", "gate_reasons": []}

    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=_report)

    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    emitters = _RecordingEmitters()

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    assert result == "succeeded"
    assert "processing_completed" in _events(deps)
    assert "processing_completed_unpersisted" not in _events(deps)
    level, _ctx = _event(deps, "processing_completed")
    assert level == logging.INFO
    # No unpersisted-warning notice.
    unpersisted_notices: list[dict[str, object]] = []
    for call in emitters.state_calls:
        notice = call.get("latest_result_notice")
        if isinstance(notice, dict) and "сохранить файлы результата" in str(notice.get("message", "")):
            unpersisted_notices.append(notice)
    assert not unpersisted_notices
    assert not any(
        notice.get("kind") == "persistence"
        for call in emitters.state_calls
        for notice in call.get("latest_result_notices", [])
        if isinstance(notice, Mapping)
    )


def test_finalize_quality_warning_keeps_legacy_notice_while_cleanup_notice_coexists(
    monkeypatch,
    tmp_path,
):
    gate_input = "translated body"
    quality_message = (
        "Перевод завершён. Документ готов к использованию, но требует ручной "
        "проверки оформления: 2 абзаца с замечаниями. "
        "Подробности — в отчёте проверки (formatting_review.txt)."
    )
    cleanup_message = "Reader cleanup was partially unavailable."
    cleanup_notice = {
        "kind": "cleanup",
        "level": "warning",
        "message_key": "result.cleanup_advisory_failed",
        "message": cleanup_message,
    }
    cleanup = late_phases.ReaderCleanupPostprocessResult(
        markdown=gate_input,
        docx_bytes=b"final-docx",
        report=None,
        raw_markdown=None,
        result_notice={"level": "warning", "message": cleanup_message},
        final_generated_paragraph_registry=None,
        result_notices=(cleanup_notice,),
    )
    _install_stubs(
        monkeypatch,
        gate_input_markdown=gate_input,
        cleanup_result=cleanup,
        report_fn=lambda **kwargs: {
            "quality_status": "warn",
            "gate_reasons": ["formatting_review_required"],
            "formatting_review_required_count": 2,
            "formatting_review_items": [{"count": 2}],
        },
    )
    monkeypatch.setattr(
        late_phases,
        "_build_quality_warn_notice_message",
        lambda report: quality_message,
    )
    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    emitters = _RecordingEmitters()

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    assert result == "succeeded"
    delivered = next(
        call for call in reversed(emitters.state_calls) if "latest_delivery_disposition" in call
    )
    assert delivered["latest_delivery_disposition"] == {"status": "accepted_with_advisory"}
    assert delivered["latest_result_notice"] == {
        "level": "warning",
        "message": quality_message,
    }
    assert delivered["latest_result_notices"] == [cleanup_notice]
    assert _state_mapping_value(delivered, "latest_quality_warning", "message") == quality_message


def test_finalize_primary_persistence_failure_accumulates_typed_degradations(
    monkeypatch,
    make_session_state,
):
    gate_input = "translated body"
    cleanup_notice = {
        "kind": "cleanup",
        "level": "warning",
        "message_key": "result.cleanup_advisory_failed",
    }
    cleanup = late_phases.ReaderCleanupPostprocessResult(
        markdown=gate_input,
        docx_bytes=b"final-docx",
        report=None,
        raw_markdown=None,
        result_notice={"level": "warning", "message": "Cleanup degraded"},
        final_generated_paragraph_registry=None,
        result_notices=(cleanup_notice,),
    )
    _install_stubs(
        monkeypatch,
        gate_input_markdown=gate_input,
        cleanup_result=cleanup,
        report_fn=lambda **kwargs: {
            "quality_status": "warn",
            "gate_reasons": ["formatting_review_required"],
            "formatting_review_required_count": 1,
            "formatting_review_items": [{"count": 1}],
        },
    )
    monkeypatch.setattr(
        late_phases,
        "_build_narration_text",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("narration_cleanup_projection_unsafe:missing_final_registry")
        ),
    )

    def _raise_oserror():
        raise OSError("disk full")

    deps = _RecordingDependencies(artifact_writer=_raise_oserror)
    session_state = make_session_state()
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)

    class _ApplyingEmitters(_RecordingEmitters):
        def emit_state(self, runtime, **values):
            super().emit_state(runtime, **values)
            processing_runtime.emit_or_apply_state(None, **values)

    emitters = _ApplyingEmitters()

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    persistence_state = next(
        call
        for call in reversed(emitters.state_calls)
        if isinstance(call.get("latest_result_notice"), Mapping)
        and "сохранить файлы результата" in str(call["latest_result_notice"].get("message", ""))
    )
    assert result == "succeeded"
    assert persistence_state["latest_result_notice"] == {
        "level": "warning",
        "message": "Результат обработан, но не удалось сохранить файлы результата на диск.",
    }
    assert persistence_state["latest_result_notices"] == [
        cleanup_notice,
        {
            "kind": "narration",
            "level": "warning",
            "message_key": "result.narration_omitted",
        },
        {
            "kind": "persistence",
            "level": "warning",
            "message_key": "result.primary_artifacts_not_saved",
        },
    ]
    assert "ui_result_artifacts_saved" not in _events(deps)
    assert "processing_completed_unpersisted" in _events(deps)
    assert "processing_completed" not in _events(deps)
    delivered = next(
        call for call in emitters.state_calls if "latest_delivery_disposition" in call
    )
    assert delivered["latest_delivery_disposition"] == {"status": "accepted_with_advisory"}
    assert delivered["latest_docx_bytes"] == b"final-docx"
    assert delivered["latest_markdown"] == gate_input

    monkeypatch.setattr(processing_runtime, "get_latest_source_name", lambda: "report.docx")
    monkeypatch.setattr(processing_runtime, "get_latest_source_token", lambda: "source-main")
    monkeypatch.setattr(app, "render_markdown_preview", lambda **kwargs: None)
    monkeypatch.setattr(app, "t", lambda key, **kwargs: f"localized:{key}")
    monkeypatch.setattr(result_ui, "t", lambda key, **kwargs: f"localized:{key}")
    success_calls = []
    warning_calls = []
    download_calls = []

    class FakeColumn:
        def download_button(self, *args, **kwargs):
            download_calls.append(kwargs)

    monkeypatch.setattr(result_ui.st, "success", lambda message: success_calls.append(message))
    monkeypatch.setattr(result_ui.st, "warning", lambda message: warning_calls.append(message))
    monkeypatch.setattr(result_ui.st, "columns", lambda count: [FakeColumn() for _ in range(count)])
    monkeypatch.setattr(result_ui, "_render_formatting_review_block", lambda **kwargs: None)

    current_result = processing_runtime.get_current_result_bundle()
    assert current_result is not None
    app._render_completed_result_view(current_result)

    assert success_calls == ["localized:result.success_document_processed"]
    assert warning_calls == [
        "localized:result.cleanup_advisory_failed",
        "localized:result.narration_omitted",
        "localized:result.primary_artifacts_not_saved",
    ]
    assert len(download_calls) == 2
    assert all(call["type"] == "primary" for call in download_calls)


# --------------------------------------------------------------------------- #
# F12 — a registry-only save failure (primary result files saved fine) must NOT
# claim the result was not delivered; it logs a distinct WARNING and completes.
# --------------------------------------------------------------------------- #


def test_finalize_registry_only_oserror_completes_without_unpersisted_notice(monkeypatch, tmp_path):
    gate_input = "Чистый переведённый абзац."

    def _report(**kwargs):
        return {"quality_status": "pass", "gate_reasons": []}

    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=_report)
    # Non-empty segment records so the registry write is actually attempted.
    monkeypatch.setattr(
        late_phases, "build_segment_result_records", lambda **k: [{"segment_id": "seg_0001"}]
    )

    # Primary artifacts save fine (real non-empty files); only the segment registry
    # write raises OSError.
    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))

    def _raise_registry_oserror(*, records):
        raise OSError("registry disk full")

    deps.write_segment_result_registry = _raise_registry_oserror  # type: ignore[method-assign]
    emitters = _RecordingEmitters()

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    # The run genuinely delivered its result files, so it completes normally.
    assert result == "succeeded"
    assert "processing_completed" in _events(deps)
    assert "processing_completed_unpersisted" not in _events(deps)
    level, _ctx = _event(deps, "processing_completed")
    assert level == logging.INFO

    # A DISTINCT registry-save WARNING was logged.
    assert "segment_result_registry_save_failed" in _events(deps)
    reg_level, _reg_ctx = _event(deps, "segment_result_registry_save_failed")
    assert reg_level == logging.WARNING

    # NO user-facing "result files not saved" notice was emitted.
    unpersisted_notices: list[dict[str, object]] = []
    for call in emitters.state_calls:
        notice = call.get("latest_result_notice")
        if isinstance(notice, dict) and "сохранить файлы результата" in str(notice.get("message", "")):
            unpersisted_notices.append(notice)
    assert not unpersisted_notices
    assert not any(
        notice.get("kind") == "persistence"
        for call in emitters.state_calls
        for notice in call.get("latest_result_notices", [])
        if isinstance(notice, Mapping)
    )


# --------------------------------------------------------------------------- #
# F10 — re-gate the DELIVERED post-cleanup markdown.
# --------------------------------------------------------------------------- #


def _fail_when_marker_report():
    """Report builder that fails only when the measured markdown carries the marker."""
    calls: list[str] = []

    def _report(*, final_markdown, **kwargs):
        calls.append(final_markdown)
        if "GATE_FAIL" in final_markdown:
            return {
                "quality_status": "fail",
                "gate_reasons": ["untranslated_body_text_above_threshold"],
            }
        return {"quality_status": "pass", "gate_reasons": []}

    return _report, calls


def test_finalize_regates_post_cleanup_and_blocks_when_cleanup_flips_to_fail(monkeypatch):
    gate_input = "Чистый переведённый абзац."  # passes the pre-cleanup gate
    cleaned_bad = "GATE_FAIL regression introduced by reader cleanup."

    report_fn, report_calls = _fail_when_marker_report()
    cleanup = _cleanup_result(markdown=cleaned_bad, docx_bytes=b"final-docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=report_fn)

    deps = _RecordingDependencies(artifact_writer=lambda: {"markdown_path": "result.md"})
    emitters = _RecordingEmitters()

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    # Delivery BLOCKED.
    assert result == "failed"
    assert "translation_quality_gate_failed_post_cleanup" in _events(deps)
    level, _ctx = _event(deps, "translation_quality_gate_failed_post_cleanup")
    assert level == logging.WARNING

    # The bad result is NOT emitted as a completed success.
    assert "processing_completed" not in _events(deps)
    assert "processing_completed_unpersisted" not in _events(deps)
    assert not any(call["terminal_kind"] == "completed" for call in emitters.finalize_calls)
    assert any(call["terminal_kind"] == "error" for call in emitters.finalize_calls)

    # The gate was recomputed on the DELIVERED (cleaned) markdown, and artifacts were
    # never written because delivery was blocked first.
    assert cleaned_bad in report_calls
    assert deps.write_ui_result_artifacts_calls == 0


def test_finalize_completes_when_cleanup_changes_markdown_but_still_passes(monkeypatch, tmp_path):
    gate_input = "Чистый переведённый абзац."
    cleaned_ok = "Отредактированный, но всё ещё качественный абзац."

    report_fn, report_calls = _fail_when_marker_report()
    cleanup = _cleanup_result(markdown=cleaned_ok, docx_bytes=b"final-docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=report_fn)

    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    emitters = _RecordingEmitters()

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    assert result == "succeeded"
    # Re-gate DID run on the changed-but-passing delivered markdown.
    assert cleaned_ok in report_calls
    assert "translation_quality_gate_failed_post_cleanup" not in _events(deps)
    assert "processing_completed" in _events(deps)
    assert any(call["terminal_kind"] == "completed" for call in emitters.finalize_calls)
    # The delivered markdown is the cleaned one.
    delivered = [
        call for call in emitters.state_calls if call.get("latest_markdown") == cleaned_ok
    ]
    assert delivered


def test_finalize_skips_regate_when_cleanup_leaves_markdown_unchanged(monkeypatch, tmp_path):
    """No behaviour change when cleanup is a no-op: the gate is computed exactly
    once (the pre-cleanup call), so unchanged content keeps its existing behaviour."""
    gate_input = "Чистый переведённый абзац."

    report_fn, report_calls = _fail_when_marker_report()
    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=report_fn)

    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    emitters = _RecordingEmitters()

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    assert result == "succeeded"
    # Exactly one gate computation — the pre-cleanup call. The re-gate was skipped.
    assert report_calls == [gate_input]
    assert "processing_completed" in _events(deps)


# --------------------------------------------------------------------------- #
# spec 042 P1-B — a caption→heading structural conflict must BLOCK delivery.
# End-to-end through the REAL quality-report builder: the conflict flips
# quality_status to "fail", which drives the terminal fail branch (:664) so the
# primary UI result artifacts (``.result.md``/``.result.docx``) are never written.
# --------------------------------------------------------------------------- #


def test_finalize_caption_heading_conflict_blocks_primary_artifacts(monkeypatch, tmp_path):
    gate_input = "Чистый переведённый абзац для итоговой проверки."

    # A real formatting-diagnostics artifact carrying a caption→heading conflict.
    conflict_artifact = tmp_path / "formatting_diagnostics_1.json"
    conflict_artifact.write_text(
        json.dumps(
            {
                "stage": "post_formatting_transfer",
                "caption_heading_conflicts": [
                    {"caption_text": "Рисунок 1. Схема", "heading_text": "## Рисунок 1. Схема"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Stub the heavy collaborators but KEEP the real quality-report builder so the
    # conflict is gated by the production logic under test (not a hand-fed verdict).
    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
    _install_stubs(
        monkeypatch,
        gate_input_markdown=gate_input,
        cleanup_result=cleanup,
        report_fn=lambda **k: {"quality_status": "pass", "gate_reasons": []},
    )
    monkeypatch.setattr(
        late_phases,
        "_build_translation_quality_report",
        quality_gate._build_translation_quality_report,
    )

    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    emitters = _RecordingEmitters()

    docx_phase = _make_docx_phase(gate_input)
    docx_phase["formatting_diagnostics_artifacts"] = [str(conflict_artifact)]
    # Non-empty delivered DOCX so the quality-gate fail branch (not the empty-docx guard)
    # is the one that fires.
    docx_phase["docx_bytes"] = b"PK\x03\x04 non-empty final docx"

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=docx_phase,
    )

    # Delivery BLOCKED by the caption→heading conflict.
    assert result == "failed"
    assert "translation_quality_gate_failed" in _events(deps)
    _level, ctx = _event(deps, "translation_quality_gate_failed")
    gate_reasons = ctx.get("gate_reasons") or []
    assert isinstance(gate_reasons, list)
    assert "caption_heading_conflict" in gate_reasons
    blocked_states = [
        call
        for call in emitters.state_calls
        if _state_mapping_value(call, "latest_delivery_disposition", "status") == "blocked"
    ]
    assert blocked_states
    assert _state_mapping_value(
        blocked_states[-1], "latest_delivery_disposition", "explanation"
    )

    # The PRIMARY UI result artifacts were NEVER written — the fail path returns first.
    assert deps.write_ui_result_artifacts_calls == 0
    assert "ui_result_artifacts_saved" not in _events(deps)
    assert "processing_completed" not in _events(deps)
    assert "processing_completed_unpersisted" not in _events(deps)
    assert not any(call["terminal_kind"] == "completed" for call in emitters.finalize_calls)
    assert any(call["terminal_kind"] == "error" for call in emitters.finalize_calls)


def test_finalize_no_caption_conflict_publishes_normally(monkeypatch, tmp_path):
    """Companion: the SAME real-builder path with ZERO caption→heading conflicts
    publishes normally (quality_status stays pass, primary artifacts written)."""
    gate_input = "Чистый переведённый абзац для итоговой проверки."

    clean_artifact = tmp_path / "formatting_diagnostics_1.json"
    clean_artifact.write_text(
        json.dumps({"stage": "post_formatting_transfer", "caption_heading_conflicts": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
    _install_stubs(
        monkeypatch,
        gate_input_markdown=gate_input,
        cleanup_result=cleanup,
        report_fn=lambda **k: {"quality_status": "pass", "gate_reasons": []},
    )
    monkeypatch.setattr(
        late_phases,
        "_build_translation_quality_report",
        quality_gate._build_translation_quality_report,
    )

    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    emitters = _RecordingEmitters()

    docx_phase = _make_docx_phase(gate_input)
    docx_phase["formatting_diagnostics_artifacts"] = [str(clean_artifact)]
    docx_phase["docx_bytes"] = b"PK\x03\x04 non-empty final docx"

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=docx_phase,
    )

    assert result == "succeeded"
    assert "translation_quality_gate_failed" not in _events(deps)
    assert deps.write_ui_result_artifacts_calls == 1
    assert "processing_completed" in _events(deps)
    assert any(
        _state_mapping_value(call, "latest_delivery_disposition", "status") == "accepted"
        for call in emitters.state_calls
    )


# --------------------------------------------------------------------------- #
# spec 043 P1 — the caption→heading delivery gate must judge the FINAL (post
# reader-cleanup) DOCX diagnostics. When reader cleanup is enabled the base DOCX
# is built LATE, so the pre-cleanup gate runs on an EMPTY diagnostics list; a
# caption conflict introduced by the FINAL DOCX must still BLOCK delivery on BOTH
# the markdown-changed AND markdown-unchanged reader-cleanup sub-paths (the
# unchanged path is the one the pre-043 code missed entirely).
# --------------------------------------------------------------------------- #


def _make_reader_cleanup_context():
    """A translate context with reader cleanup ENABLED, so the finalize base DOCX
    build is DEFERRED (``docx_bytes`` is None at the pre-cleanup gate) and the FINAL
    diagnostics are re-collected after the reader-cleanup build."""
    context = _make_context()
    context.app_config = {"reader_cleanup_enabled": True}
    return context


def test_finalize_late_stop_before_cleanup_uses_stopped_outcome_without_persistence(monkeypatch, tmp_path):
    gate_input = "translated body"
    cleanup = _cleanup_result(markdown=gate_input)
    _install_stubs(
        monkeypatch,
        gate_input_markdown=gate_input,
        cleanup_result=cleanup,
        report_fn=lambda **kwargs: {"quality_status": "pass", "gate_reasons": []},
    )
    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    deps.should_stop_processing = lambda runtime: True
    emitters = _RecordingEmitters()

    result = _run_finalize(
        context=_make_reader_cleanup_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    assert result == "stopped"
    assert deps.write_ui_result_artifacts_calls == 0
    assert emitters.finalize_calls[-1]["terminal_kind"] == "stopped"
    assert "processing_completed" not in _events(deps)


@pytest.mark.parametrize("stop_during", ["successful_rebuild", "advisory_base_builder"])
def test_finalize_stop_observed_immediately_after_cleanup_builder_has_no_later_side_effects(
    monkeypatch,
    tmp_path,
    stop_during,
):
    gate_input = "translated body"
    assembly = SimpleNamespace(final_markdown=gate_input, entries=(), diagnostics=None)
    monkeypatch.setattr(late_phases, "assemble_final_markdown", lambda **kwargs: assembly)
    monkeypatch.setattr(
        late_phases,
        "_build_translation_quality_report",
        lambda **kwargs: {"quality_status": "pass", "gate_reasons": []},
    )
    monkeypatch.setattr(late_phases, "build_report_acceptance_verdict", lambda *args, **kwargs: {})
    report_writes = []
    monkeypatch.setattr(
        late_phases,
        "_write_quality_report_artifact",
        lambda **kwargs: report_writes.append(kwargs) or None,
    )
    narration_calls = []
    monkeypatch.setattr(
        late_phases,
        "_build_narration_text",
        lambda **kwargs: narration_calls.append(kwargs) or "must-not-run",
    )
    monkeypatch.setattr(
        late_phases,
        "build_reassembly_plan",
        lambda **kwargs: SimpleNamespace(assembly_mode="whole", selected_segment_count=None),
    )
    monkeypatch.setattr(late_phases, "build_segment_result_records", lambda **kwargs: [])
    monkeypatch.setattr(
        reader_cleanup_postprocess,
        "_resolve_text_call_target",
        lambda **kwargs: (object(), "model-id", "model-selector", "provider"),
    )
    monkeypatch.setattr(
        reader_cleanup_postprocess,
        "_write_reader_cleanup_lineage_artifact",
        lambda **kwargs: None,
    )

    stop_requested = False

    def request_stop_and_return_docx(*args, **kwargs):
        nonlocal stop_requested
        stop_requested = True
        return b"PK\x03\x04 final docx"

    if stop_during == "successful_rebuild":
        monkeypatch.setattr(
            reader_cleanup_postprocess,
            "run_reader_cleanup",
            lambda **kwargs: SimpleNamespace(
                changed=True,
                report_payload={"stats": {}, "accepted_cleanup_operations": []},
                raw_markdown=gate_input,
                cleaned_markdown="cleaned translated body",
                accepted_delete_block_ids=[],
            ),
        )
        monkeypatch.setattr(
            reader_cleanup_postprocess,
            "_rebuild_docx_for_markdown",
            request_stop_and_return_docx,
        )
    else:
        monkeypatch.setattr(
            reader_cleanup_postprocess,
            "run_reader_cleanup",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("cleanup unavailable")),
        )

    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    deps.should_stop_processing = lambda runtime: stop_requested
    deps.get_client = lambda: object()
    emitters = _RecordingEmitters()
    docx_phase = _make_docx_phase(gate_input)
    if stop_during == "advisory_base_builder":
        docx_phase["base_docx_builder"] = request_stop_and_return_docx

    result = _run_finalize(
        context=_make_reader_cleanup_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=docx_phase,
    )

    assert result == "stopped"
    assert stop_requested is True
    assert emitters.state_calls == []
    assert narration_calls == []
    assert deps.write_ui_result_artifacts_calls == 0
    assert emitters.finalize_calls[-1]["terminal_kind"] == "stopped"
    assert len(report_writes) == 1  # pre-cleanup report only; no post-stop report write
    assert not {
        "reader_cleanup_applied",
        "processing_completed",
        "processing_completed_unpersisted",
        "processing_failed",
    }.intersection(_events(deps))


def _write_caption_conflict_artifact(
    diagnostics_dir,
    name="preserve_001.json",
    *,
    run_id="run-main",
    source_token="source-main",
):
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / name).write_text(
        json.dumps(
            {
                "stage": "preserve",
                "ownership": {
                    "scope": "live",
                    "run_id": run_id,
                    "source_token": source_token,
                },
                "caption_heading_conflicts": [
                    {"paragraph_id": "p0002", "target_heading_level": 2}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _run_deferred_finalize_with_final_diagnostics(monkeypatch, tmp_path, *, cleaned_markdown):
    """Drive finalize with reader cleanup ENABLED (deferred base build) and a FINAL
    DOCX that wrote a caption→heading conflict artifact during its (deferred) build.
    ``cleaned_markdown`` controls the reader-cleanup sub-path: equal to the pre-cleanup
    markdown → UNCHANGED sub-path; different → CHANGED sub-path."""
    gate_input = "Чистый переведённый абзац для итоговой проверки."

    diagnostics_dir = tmp_path / "formatting_diagnostics"
    _write_caption_conflict_artifact(diagnostics_dir)

    cleanup = _cleanup_result(markdown=cleaned_markdown, docx_bytes=b"PK\x03\x04 final docx")
    _install_stubs(
        monkeypatch,
        gate_input_markdown=gate_input,
        cleanup_result=cleanup,
        report_fn=lambda **k: {"quality_status": "pass", "gate_reasons": []},
    )
    # KEEP the real quality-report builder so the conflict is gated by production logic.
    monkeypatch.setattr(
        late_phases,
        "_build_translation_quality_report",
        quality_gate._build_translation_quality_report,
    )

    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    emitters = _RecordingEmitters()

    docx_phase = _make_docx_phase(gate_input)
    # Deferred base build: no docx_bytes at the pre-cleanup gate, and the diagnostics
    # diagnostics directory is threaded so finalize can RE-COLLECT only final-DOCX
    # artifacts owned by this run and source.
    docx_phase["docx_bytes"] = None
    docx_phase["diagnostics_dir"] = diagnostics_dir

    result = _run_finalize(
        context=_make_reader_cleanup_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=docx_phase,
    )
    return result, deps, emitters, gate_input


def test_finalize_caption_conflict_in_final_docx_blocks_delivery_markdown_changed(monkeypatch, tmp_path):
    # Reader-cleanup CHANGED the delivered markdown; the FINAL DOCX (built during the
    # deferred build) carries a caption→heading conflict the pre-cleanup gate never saw.
    result, deps, emitters, _gate_input = _run_deferred_finalize_with_final_diagnostics(
        monkeypatch, tmp_path, cleaned_markdown="Отредактированный, но всё ещё качественный абзац."
    )

    assert result == "failed"
    assert "translation_quality_gate_failed_post_cleanup" in _events(deps)
    _level, ctx = _event(deps, "translation_quality_gate_failed_post_cleanup")
    gate_reasons = ctx.get("gate_reasons") or []
    assert isinstance(gate_reasons, list)
    assert "caption_heading_conflict" in gate_reasons
    blocked_states = [
        call
        for call in emitters.state_calls
        if _state_mapping_value(call, "latest_delivery_disposition", "status") == "blocked"
    ]
    assert blocked_states
    assert _state_mapping_value(
        blocked_states[-1], "latest_delivery_disposition", "explanation"
    )
    # Primary UI artifacts were NEVER written — delivery blocked first.
    assert deps.write_ui_result_artifacts_calls == 0
    assert "ui_result_artifacts_saved" not in _events(deps)
    assert "processing_completed" not in _events(deps)
    assert not any(call["terminal_kind"] == "completed" for call in emitters.finalize_calls)
    assert any(call["terminal_kind"] == "error" for call in emitters.finalize_calls)


def test_finalize_caption_conflict_in_final_docx_blocks_delivery_markdown_unchanged(monkeypatch, tmp_path):
    # Reader cleanup left the delivered markdown UNCHANGED, so the pre-043 code skipped
    # the whole re-gate — yet the deferred FINAL DOCX still produced a caption→heading
    # conflict. spec 043 P1 makes the caption gate authoritative on the FINAL diagnostics
    # even on this sub-path, so delivery must be BLOCKED.
    gate_input = "Чистый переведённый абзац для итоговой проверки."
    result, deps, emitters, resolved_gate_input = _run_deferred_finalize_with_final_diagnostics(
        monkeypatch, tmp_path, cleaned_markdown=gate_input
    )
    assert resolved_gate_input == gate_input  # markdown genuinely UNCHANGED by cleanup

    assert result == "failed"
    assert "translation_quality_gate_failed_post_cleanup" in _events(deps)
    _level, ctx = _event(deps, "translation_quality_gate_failed_post_cleanup")
    gate_reasons = ctx.get("gate_reasons") or []
    assert isinstance(gate_reasons, list)
    assert "caption_heading_conflict" in gate_reasons
    blocked_states = [
        call
        for call in emitters.state_calls
        if _state_mapping_value(call, "latest_delivery_disposition", "status") == "blocked"
    ]
    assert blocked_states
    assert deps.write_ui_result_artifacts_calls == 0
    assert "ui_result_artifacts_saved" not in _events(deps)
    assert "processing_completed" not in _events(deps)
    assert not any(call["terminal_kind"] == "completed" for call in emitters.finalize_calls)
    assert any(call["terminal_kind"] == "error" for call in emitters.finalize_calls)


def test_finalize_reader_cleanup_without_caption_conflict_publishes(monkeypatch, tmp_path):
    # Reader cleanup ENABLED (deferred base build), markdown unchanged, and the FINAL
    # diagnostics carry NO caption conflict -> the run publishes normally and the
    # unchanged-markdown path stays byte-identical (no re-gate, no spurious rebuild).
    gate_input = "Чистый переведённый абзац для итоговой проверки."

    diagnostics_dir = tmp_path / "formatting_diagnostics"
    # Overlapping foreign runs may write conflicts into the shared directory. Neither
    # same-run/different-source nor different-run/same-source artifacts belong here.
    _write_caption_conflict_artifact(
        diagnostics_dir,
        "foreign_source.json",
        source_token="source-foreign",
    )
    _write_caption_conflict_artifact(
        diagnostics_dir,
        "foreign_run.json",
        run_id="run-foreign",
    )
    owned_path = diagnostics_dir / "owned_non_caption.json"
    owned_path.write_text(
        json.dumps(
            {
                "stage": "preserve",
                "ownership": {
                    "scope": "live",
                    "run_id": "run-main",
                    "source_token": "source-main",
                },
                "source_count": 5,
                "target_count": 4,
                "mapped_count": 4,
                "unmapped_source_ids": ["p0004"],
                "unmapped_target_indexes": [],
                "caption_heading_conflicts": [],
            }
        ),
        encoding="utf-8",
    )

    report_calls: list[list[str]] = []

    def report_fn(*, formatting_diagnostics_artifacts, **kwargs):
        report_calls.append(list(formatting_diagnostics_artifacts))
        return {
            "quality_status": "pass",
            "gate_reasons": [],
            "formatting_diagnostics_artifact_count": len(formatting_diagnostics_artifacts),
            "formatting_diagnostics_artifact_paths": list(formatting_diagnostics_artifacts),
        }

    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"PK\x03\x04 final docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=report_fn)

    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    emitters = _RecordingEmitters()

    docx_phase = _make_docx_phase(gate_input)
    docx_phase["docx_bytes"] = None
    docx_phase["diagnostics_dir"] = diagnostics_dir

    result = _run_finalize(
        context=_make_reader_cleanup_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=docx_phase,
    )

    assert result == "succeeded"
    # Unchanged markdown still rebuilds the authoritative report when the deferred
    # build contributes a new exact-owned non-caption diagnostic.
    assert report_calls == [[], [str(owned_path)]]
    assert "translation_quality_gate_failed_post_cleanup" not in _events(deps)
    detected_events = [event for event in deps.events if event[1] == "formatting_diagnostics_artifacts_detected"]
    assert len(detected_events) == 1
    assert detected_events[0][3]["artifact_paths"] == [str(owned_path)]
    assert emitters.activity_calls
    assert any(
        _state_mapping_value(call, "latest_result_notice", "level") == "info"
        for call in emitters.state_calls
    )
    assert deps.write_ui_result_artifacts_calls == 1
    assert "processing_completed" in _events(deps)


# --------------------------------------------------------------------------- #
# spec 043 P2 — the DELIVERY gate must aggregate caption→heading conflicts across
# ALL current formatting-diagnostics payloads (mirroring the acceptance verdict),
# not only the LAST artifact. A conflict in a NON-last artifact must still fail.
# --------------------------------------------------------------------------- #


def test_quality_report_aggregates_caption_conflicts_across_all_artifacts(tmp_path):
    # Conflict lives in the FIRST (non-last) artifact; the LAST artifact is clean.
    first_artifact = tmp_path / "a_preserve.json"
    first_artifact.write_text(
        json.dumps(
            {
                "stage": "preserve",
                "caption_heading_conflicts": [{"paragraph_id": "p0002", "target_heading_level": 2}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    last_artifact = tmp_path / "z_restore.json"
    last_artifact.write_text(
        json.dumps({"stage": "restore", "caption_heading_conflicts": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = quality_gate._build_translation_quality_report(
        context=_make_context(),
        final_markdown="Чистый переведённый абзац для итоговой проверки.",
        formatting_diagnostics_artifacts=[str(first_artifact), str(last_artifact)],
    )

    # Pre-043 the single-latest-payload count would be 0 (last artifact clean) and the
    # gate would PASS; the aggregate now counts the non-last conflict and BLOCKS delivery.
    assert report["quality_status"] == "fail"
    gate_reasons = report.get("gate_reasons") or []
    assert isinstance(gate_reasons, list)
    assert "caption_heading_conflict" in gate_reasons
    assert report["caption_heading_conflicts_count"] == 1


# --------------------------------------------------------------------------- #
# Finding 13 — a returned artifact mapping is NOT proof of persistence.
# --------------------------------------------------------------------------- #


def _warn_notices(emitters: _RecordingEmitters) -> list[dict[str, object]]:
    notices: list[dict[str, object]] = []
    for call in emitters.state_calls:
        notice = call.get("latest_result_notice")
        if isinstance(notice, dict) and "сохранить файлы результата" in str(notice.get("message", "")):
            notices.append(notice)
    return notices


def test_finalize_zero_byte_primary_docx_is_unpersisted(monkeypatch, tmp_path):
    """A write that returns a mapping but leaves a zero-byte primary DOCX must be
    treated as unpersisted (WARNING ``processing_completed_unpersisted`` + not-saved
    notice), never a false ``processing_completed`` success."""
    gate_input = "Чистый переведённый абзац."

    def _report(**kwargs):
        return {"quality_status": "pass", "gate_reasons": []}

    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=_report)

    markdown_path = tmp_path / "report.result.md"
    markdown_path.write_text("итоговый markdown", encoding="utf-8")
    docx_path = tmp_path / "report.result.docx"
    docx_path.write_bytes(b"")  # primary DOCX exists but is ZERO-BYTE

    deps = _RecordingDependencies(
        artifact_writer=lambda: {"markdown_path": str(markdown_path), "docx_path": str(docx_path)}
    )
    emitters = _RecordingEmitters()

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    # The delivered result still reached session state, so the run still "succeeds",
    # but persistence is reported as failed.
    assert result == "succeeded"
    assert "ui_result_artifacts_save_failed" in _events(deps)
    assert "processing_completed_unpersisted" in _events(deps)
    assert "processing_completed" not in _events(deps)
    assert _warn_notices(emitters), "no user-visible not-saved notice was emitted"


def test_finalize_missing_primary_docx_key_is_unpersisted(monkeypatch, tmp_path):
    """A mapping that omits the primary ``docx_path`` key entirely is unpersisted."""
    gate_input = "Чистый переведённый абзац."

    def _report(**kwargs):
        return {"quality_status": "pass", "gate_reasons": []}

    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=_report)

    markdown_path = tmp_path / "report.result.md"
    markdown_path.write_text("итоговый markdown", encoding="utf-8")

    # docx_path missing from the mapping — the write "succeeded" but the primary DOCX
    # was never actually reported as persisted.
    deps = _RecordingDependencies(artifact_writer=lambda: {"markdown_path": str(markdown_path)})
    emitters = _RecordingEmitters()

    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    assert result == "succeeded"
    assert "ui_result_artifacts_save_failed" in _events(deps)
    assert "processing_completed_unpersisted" in _events(deps)
    assert "processing_completed" not in _events(deps)
    assert _warn_notices(emitters)


# --------------------------------------------------------------------------- #
# Finding 7 — a no-op reader cleanup must still refresh the output-artifact
# verdict fields (``output_docx_openable``) once the delivered DOCX exists.
# --------------------------------------------------------------------------- #


def _openable_check(verdict: dict) -> dict:
    for check in verdict.get("checks", []):
        if check.get("name") == "output_docx_openable":
            return check
    raise AssertionError("output_docx_openable check not found in verdict")


def test_finalize_noop_cleanup_refreshes_output_docx_openable_verdict(monkeypatch, tmp_path):
    """No-op reader cleanup, non-empty delivered DOCX: the pre-cleanup verdict records
    ``output_docx_openable`` NOT-APPLICABLE (the base docx build is deferred, so no bytes
    exist yet), and the finalize path must REFRESH just that output-artifact verdict field
    on the delivered bytes so the saved record reflects the real DOCX — even though the
    markdown never changed and its metrics are not recomputed."""
    import copy

    from io import BytesIO

    from docx import Document

    buf = BytesIO()
    Document().save(buf)
    real_docx_bytes = buf.getvalue()

    gate_input = "Чистый переведённый абзац."

    def _report(**kwargs):
        return {"quality_status": "pass", "gate_reasons": []}

    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=real_docx_bytes)
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=_report)
    # Restore the REAL acceptance-verdict machinery (``_install_stubs`` stubbed it) so the
    # verdict genuinely reflects the delivered DOCX bytes.
    monkeypatch.setattr(late_phases, "build_report_acceptance_verdict", _REAL_BUILD_VERDICT)

    written_reports: list[dict] = []

    def _capture_report(*, source_name, payload):
        written_reports.append(copy.deepcopy(payload))
        return "quality_report.json"

    monkeypatch.setattr(late_phases, "_write_quality_report_artifact", _capture_report)

    deps = _RecordingDependencies(artifact_writer=_real_primary_artifact_writer(tmp_path))
    emitters = _RecordingEmitters()

    # docx_phase has NO ``docx_bytes`` (deferred base build), so the pre-cleanup verdict is N/A.
    result = _run_finalize(
        context=_make_context(),
        dependencies=deps,
        emitters=emitters,
        state=_make_state(),
        docx_phase=_make_docx_phase(gate_input),
    )

    assert result == "succeeded"
    # The report was written twice: the pre-cleanup record (N/A) then the refreshed one.
    assert len(written_reports) == 2
    pre_check = _openable_check(written_reports[0]["acceptance_verdict"])
    assert pre_check.get("applicable") is False  # N/A before the delivered DOCX existed
    post_check = _openable_check(written_reports[-1]["acceptance_verdict"])
    assert post_check.get("applicable") is True
    assert post_check.get("passed") is True  # reflects the real, openable DOCX
