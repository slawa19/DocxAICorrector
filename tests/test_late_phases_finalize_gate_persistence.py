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

import logging
import time
from types import SimpleNamespace

import docxaicorrector.pipeline.late_phases as late_phases


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


def _cleanup_result(*, markdown: str, docx_bytes: bytes = b"final-docx"):
    return late_phases.ReaderCleanupPostprocessResult(
        markdown=markdown,
        docx_bytes=docx_bytes,
        report=None,
        raw_markdown=None,
        result_notice=None,
        final_generated_paragraph_registry=None,
    )


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


def test_finalize_artifact_save_success_logs_completed_info(monkeypatch):
    """Companion: when persistence succeeds the terminal log stays INFO
    ``processing_completed`` and no unpersisted-warning notice is emitted."""
    gate_input = "Чистый переведённый абзац."

    def _report(**kwargs):
        return {"quality_status": "pass", "gate_reasons": []}

    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=_report)

    deps = _RecordingDependencies(artifact_writer=lambda: {"markdown_path": "result.md"})
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


# --------------------------------------------------------------------------- #
# F12 — a registry-only save failure (primary result files saved fine) must NOT
# claim the result was not delivered; it logs a distinct WARNING and completes.
# --------------------------------------------------------------------------- #


def test_finalize_registry_only_oserror_completes_without_unpersisted_notice(monkeypatch):
    gate_input = "Чистый переведённый абзац."

    def _report(**kwargs):
        return {"quality_status": "pass", "gate_reasons": []}

    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
    _install_stubs(monkeypatch, gate_input_markdown=gate_input, cleanup_result=cleanup, report_fn=_report)
    # Non-empty segment records so the registry write is actually attempted.
    monkeypatch.setattr(
        late_phases, "build_segment_result_records", lambda **k: [{"segment_id": "seg_0001"}]
    )

    # Primary artifacts save fine; only the segment registry write raises OSError.
    deps = _RecordingDependencies(
        artifact_writer=lambda: {"markdown_path": "result.md", "docx_path": "result.docx"}
    )

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


def test_finalize_completes_when_cleanup_changes_markdown_but_still_passes(monkeypatch):
    gate_input = "Чистый переведённый абзац."
    cleaned_ok = "Отредактированный, но всё ещё качественный абзац."

    report_fn, report_calls = _fail_when_marker_report()
    cleanup = _cleanup_result(markdown=cleaned_ok, docx_bytes=b"final-docx")
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


def test_finalize_skips_regate_when_cleanup_leaves_markdown_unchanged(monkeypatch):
    """No behaviour change when cleanup is a no-op: the gate is computed exactly
    once (the pre-cleanup call), so unchanged content keeps its existing behaviour."""
    gate_input = "Чистый переведённый абзац."

    report_fn, report_calls = _fail_when_marker_report()
    cleanup = _cleanup_result(markdown=gate_input, docx_bytes=b"final-docx")
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

    assert result == "succeeded"
    # Exactly one gate computation — the pre-cleanup call. The re-gate was skipped.
    assert report_calls == [gate_input]
    assert "processing_completed" in _events(deps)
