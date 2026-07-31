import pytest

import ast
import inspect

import docxaicorrector.ui._app as app
import docxaicorrector.ui._ui as result_ui
import docxaicorrector.ui.application_flow as application_flow
import docxaicorrector.ui.compare_panel as compare_panel
import docxaicorrector.processing.processing_runtime as processing_runtime
from docxaicorrector.core.constants import MAX_DOCX_ARCHIVE_SIZE_BYTES
from conftest import SessionState as SessionState


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


class UploadedFileStub:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self.size = len(content)
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
            raise ValueError("Unsupported whence")
        self._position = min(self._position, len(self._content))
        return self._position


def test_both_ui_preparation_marker_calls_include_resolved_languages():
    module = ast.parse(inspect.getsource(app))
    marker_calls = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_preparation_request_marker"
    ]

    assert len(marker_calls) == 2
    for marker_call in marker_calls:
        keyword_names = {keyword.arg for keyword in marker_call.keywords}
        assert {"source_language", "target_language"} <= keyword_names


def _build_prepared_run_context(**overrides):
    payload = {
        "uploaded_filename": "report.docx",
        "uploaded_file_bytes": b"abc",
        "uploaded_file_token": "report.docx:3:token",
        "source_text": "source-text",
        "paragraphs": ["p1", "p2"],
        "image_assets": [],
        "jobs": [{"target_text": "block one"}, {"target_text": "block two"}],
        "prepared_source_key": "report.docx:3:token:6000",
        "preparation_stage": "Документ подготовлен",
        "preparation_detail": "Анализ завершён. Можно запускать обработку.",
        "preparation_cached": False,
        "preparation_elapsed_seconds": 1.4,
        "normalization_report": None,
        "relation_report": None,
        "cleanup_report": None,
    }
    payload.update(overrides)
    return application_flow.PreparedRunContext(**payload)


def test_same_source_rerun_forwards_blocked_delivery_contract_to_shared_renderer(monkeypatch):
    captured = {}
    blocked_result = {
        "source_name": "report.docx",
        "source_token": "report.docx:3:token",
        "docx_bytes": b"blocked-docx",
        "markdown_text": "blocked markdown",
        "narration_text": None,
        "processing_operation": "translate",
        "audiobook_postprocess_enabled": False,
        "quality_warning": None,
        "delivery_disposition": {
            "status": "blocked",
            "explanation": "Result blocked by quality gate",
        },
        "result_notices": [
            {"kind": "delivery", "level": "error", "message": "Result blocked by quality gate"}
        ],
    }
    monkeypatch.setattr(app, "render_markdown_preview", lambda **kwargs: None)
    monkeypatch.setattr(app, "render_result_bundle", lambda **kwargs: captured.update(kwargs))

    selected_result = app._select_current_result_for_source(
        blocked_result,
        source_token="report.docx:3:token",
    )
    assert selected_result is blocked_result
    assert selected_result is not None
    app._render_completed_result_view(selected_result)

    assert captured["delivery_disposition"] == blocked_result["delivery_disposition"]
    assert captured["result_notices"] == blocked_result["result_notices"]

    blocked_result_without_bytes = {**blocked_result, "docx_bytes": None}
    assert app._select_current_result_for_source(
        blocked_result_without_bytes,
        source_token="report.docx:3:token",
    ) is blocked_result_without_bytes
    assert app._select_current_result_for_source(
        blocked_result,
        source_token="other.docx:3:token",
    ) is None


def test_completed_unpersisted_result_rerender_shows_typed_warning_and_normal_downloads(monkeypatch):
    notices = [
        {"kind": "cleanup", "level": "warning", "message_key": "result.cleanup_advisory_failed"},
        {"kind": "persistence", "level": "warning", "message_key": "result.primary_artifacts_not_saved"},
    ]
    session_state = SessionState(
        latest_docx_bytes=b"accepted-docx",
        latest_markdown="accepted markdown",
        latest_delivery_disposition={"status": "accepted_with_advisory"},
        latest_result_notices=notices,
        latest_result_notice={
            "level": "warning",
            "message": "Result processed, but result files could not be saved to disk.",
        },
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(processing_runtime, "get_latest_source_name", lambda: "report.docx")
    monkeypatch.setattr(processing_runtime, "get_latest_source_token", lambda: "report.docx:3:token")
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
        "localized:result.primary_artifacts_not_saved",
    ]
    assert len(download_calls) == 2
    assert all(call["type"] == "primary" for call in download_calls)


def test_completed_quality_warning_rerender_deduplicates_semantic_legacy_notice(monkeypatch):
    quality_message = "Review formatting"
    quality_warning = {
        "kind": "translation_quality_gate",
        "quality_status": "warn",
        "message": quality_message,
    }
    session_state = SessionState(
        latest_docx_bytes=b"accepted-docx",
        latest_markdown="accepted markdown",
        latest_delivery_disposition={"status": "accepted_with_advisory"},
        latest_quality_warning=quality_warning,
        latest_result_notices=[],
        latest_result_notice={"level": "warning", "message": quality_message},
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(processing_runtime, "get_latest_source_name", lambda: "report.docx")
    monkeypatch.setattr(processing_runtime, "get_latest_source_token", lambda: "report.docx:3:token")
    monkeypatch.setattr(app, "render_markdown_preview", lambda **kwargs: None)
    success_calls = []
    warning_calls = []
    review_calls = []

    class FakeColumn:
        def download_button(self, *args, **kwargs):
            return None

    monkeypatch.setattr(result_ui.st, "success", lambda message: success_calls.append(message))
    monkeypatch.setattr(result_ui.st, "warning", lambda message: warning_calls.append(message))
    monkeypatch.setattr(result_ui.st, "columns", lambda count: [FakeColumn() for _ in range(count)])
    monkeypatch.setattr(
        result_ui,
        "_render_formatting_review_block",
        lambda **kwargs: review_calls.append(kwargs["quality_warning"]),
    )

    current_result = processing_runtime.get_current_result_bundle()
    assert current_result is not None
    assert current_result["result_notices"] == []
    app._render_completed_result_view(current_result)

    assert success_calls
    assert warning_calls == []
    assert review_calls == [quality_warning]


@pytest.mark.parametrize("outcome", ["stopped", "failed"])
def test_main_hides_preparation_summary_for_restartable_outcome(monkeypatch, outcome):
    prepared_run_context = _build_prepared_run_context()
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    session_state = SessionState(
        app_start_logged=True,
        processing_status={"stage": "Остановлено пользователем", "detail": "Обработка остановлена пользователем.", "phase": "processing"},
        activity_feed=[],
        image_assets=[],
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=prepared_run_context,
        latest_docx_bytes=None,
        latest_source_token="",
        latest_markdown="",
        latest_image_mode="safe",
        last_error="Ошибка обработки" if outcome == "failed" else "",
        last_log_hint="hint",
        processing_outcome=outcome,
    )
    warning_calls = []
    error_calls = []
    summary_calls = []
    status_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda text: warning_calls.append(text))
    monkeypatch.setattr(app.st, "error", lambda text, *args, **kwargs: error_calls.append(text))
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_preparation_summary", lambda summary, *args, **kwargs: summary_calls.append(summary))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)
    monkeypatch.setattr(app, "set_processing_status", lambda **kwargs: status_calls.append(kwargs))
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "file_selected")
    monkeypatch.setattr(application_flow, "prepare_run_context", lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")))

    app.main()

    assert summary_calls == []
    assert status_calls == []
    if outcome == "stopped":
        assert warning_calls == [
            app.t("app.restartable_stopped_notice", filename="report.docx")
        ]
        assert error_calls == []
    else:
        assert warning_calls == []
        assert error_calls[0] == app.t("app.restartable_failed_notice", filename="report.docx")


@pytest.mark.parametrize("outcome", ["stopped", "failed"])
def test_restartable_idle_view_shows_typed_outcome_notice(monkeypatch, outcome):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={"stage": "Ожидание", "detail": "", "phase": "processing"},
        activity_feed=[],
        image_assets=[],
        latest_docx_bytes=None,
        latest_source_token="",
        latest_markdown="",
        latest_image_mode="safe",
        processing_outcome=outcome,
        restart_source={"filename": "report.docx", "storage_path": "/tmp/restart.bin"},
    )
    warning_calls = []
    error_calls = []
    info_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "info", lambda text: info_calls.append(text))
    monkeypatch.setattr(app.st, "warning", lambda text: warning_calls.append(text))
    monkeypatch.setattr(app.st, "error", lambda text, *args, **kwargs: error_calls.append(text))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "restartable")

    app.main()

    if outcome == "stopped":
        assert any("остановлена" in m for m in warning_calls)
        assert error_calls == []
        assert info_calls == []
    else:
        assert any("ошибкой" in m for m in error_calls)
        assert warning_calls == []
        assert info_calls == []


@pytest.mark.parametrize("outcome", ["stopped", "failed"])
def test_restartable_idle_view_keeps_shared_layout(monkeypatch, outcome):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={"stage": "Ожидание", "detail": "", "phase": "processing"},
        activity_feed=[],
        image_assets=[],
        latest_docx_bytes=None,
        latest_source_token="",
        latest_markdown="",
        latest_image_mode="safe",
        processing_outcome=outcome,
        restart_source={"filename": "report.docx", "storage_path": "/tmp/restart.bin"},
    )
    calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_intro_layout_styles", lambda: calls.append("intro"))
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: calls.append("info"))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: calls.append("warning"))
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: calls.append("error"))
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: calls.append("run_log"))
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: calls.append("image_summary"))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: calls.append("partial_result"))
    monkeypatch.setattr(app, "_finalize_app_frame", lambda **kwargs: calls.append("finalize"))
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "restartable")

    app.main()

    assert calls[0] == "intro"
    assert "run_log" in calls
    assert "image_summary" in calls
    assert "partial_result" in calls
    assert calls[-1] == "finalize"


def test_main_rejects_oversized_upload_before_preparation(monkeypatch):
    session_state = SessionState(app_start_logged=True, processing_status={}, activity_feed=[])
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    uploaded_file.size = MAX_DOCX_ARCHIVE_SIZE_BYTES + 1
    errors = []
    preparation_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: session_state.setdefault("persisted_source_cleanup_done", False))
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", True))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "error", lambda message: errors.append(message))
    monkeypatch.setattr(app, "_start_background_preparation", lambda **kwargs: preparation_calls.append(kwargs))

    app.main()

    assert len(errors) == 1
    assert "25 МБ" in errors[0]
    assert preparation_calls == []
