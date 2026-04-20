from typing import Any

import pytest

import app
import application_flow
import compare_panel
import processing_runtime
import state
from structure_validation import StructureValidationReport
from runtime_artifacts import AppReadyMarkerWriter
from constants import MAX_DOCX_ARCHIVE_SIZE_BYTES
from models import ImageAsset, StructureRecognitionSummary
from conftest import SessionState as SessionState


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


def test_main_logs_app_start_only_once(monkeypatch):
    session_state = SessionState(app_start_logged=False)
    logged_events = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: session_state.setdefault("app_start_logged", False))
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
    monkeypatch.setattr(app, "log_event", lambda *args, **kwargs: logged_events.append((args, kwargs)))
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", True))
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)

    app.main()
    app.main()

    assert len(logged_events) == 1
    assert session_state.app_start_logged is True


def test_resolve_sidebar_settings_accepts_new_text_transform_tuple():
    result = app._resolve_sidebar_settings(("gpt-5.4", 6000, 3, "safe", True, "translate", "auto", "de"))

    assert result == ("gpt-5.4", 6000, 3, "safe", True, "translate", "auto", "de")


def test_resolve_sidebar_settings_keeps_legacy_tuple_compatible():
    result = app._resolve_sidebar_settings(("gpt-5.4", 6000, 3, "safe", True))

    assert result == ("gpt-5.4", 6000, 3, "safe", True, "edit", "en", "ru")


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


class FakeColumn:
    def __init__(self, result=False):
        self.result = result
        self.calls = []

    def button(self, label, **kwargs):
        self.calls.append((label, kwargs))
        return self.result


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
        "structure_map": None,
        "structure_recognition_summary": StructureRecognitionSummary(),
        "structure_validation_report": None,
        "structure_recognition_mode": "off",
        "structure_ai_attempted": False,
    }
    payload.update(overrides)
    return application_flow.PreparedRunContext(**payload)


def test_build_uploaded_file_token_uses_name_size_and_content_hash():
    token = processing_runtime.build_uploaded_file_token(UploadedFileStub("report.docx", b"abc"))

    assert token == "report.docx:3:ba7816bf8f01cfea"


def test_build_preparation_request_marker_includes_chunk_size():
    marker = processing_runtime.build_preparation_request_marker(UploadedFileStub("report.docx", b"abc"), chunk_size=6000)

    assert marker == "report.docx:3:ba7816bf8f01cfea:6000"


def test_build_preparation_request_marker_uses_content_hash_for_same_name_same_size_files():
    marker_one = processing_runtime.build_preparation_request_marker(UploadedFileStub("report.docx", b"abc"), chunk_size=6000)
    marker_two = processing_runtime.build_preparation_request_marker(UploadedFileStub("report.docx", b"xyz"), chunk_size=6000)

    assert marker_one != marker_two


def test_store_preparation_summary_uses_preparation_context_not_processing_status(monkeypatch):
    session_state = SessionState(
        processing_status={
            "stage": "Ожидание запуска",
            "detail": "stale detail",
            "cached": False,
            "started_at": 1.0,
        }
    )
    prepared_run_context = type("PreparedRunContextStub", (), {
        "uploaded_file_bytes": b"abc",
        "paragraphs": ["p1", "p2"],
        "image_assets": ["img"],
        "source_text": "text-value",
        "jobs": [{"target_text": "block"}],
        "ai_classified_count": 4,
        "ai_heading_count": 2,
        "ai_role_change_count": 1,
        "ai_heading_promotion_count": 1,
        "ai_heading_demotion_count": 0,
        "ai_structural_role_change_count": 1,
        "preparation_stage": "Документ подготовлен",
        "preparation_detail": "Анализ завершён без фонового worker.",
        "preparation_cached": True,
        "preparation_elapsed_seconds": 1.25,
        "normalization_report": type("NormalizationReportStub", (), {
            "total_raw_paragraphs": 3,
            "total_logical_paragraphs": 2,
            "merged_group_count": 1,
            "merged_raw_paragraph_count": 2,
        })(),
    })()

    monkeypatch.setattr(app.st, "session_state", session_state)

    app._store_preparation_summary(prepared_run_context=prepared_run_context)

    assert session_state.latest_preparation_summary == {
        "stage": "Документ подготовлен",
        "detail": "Анализ завершён без фонового worker.",
        "file_size_bytes": 3,
        "paragraph_count": 2,
        "image_count": 1,
        "source_chars": len("text-value"),
        "block_count": 1,
        "cached": True,
        "ai_classified": 4,
        "ai_headings": 2,
        "ai_role_changes": 1,
        "ai_heading_promotions": 1,
        "ai_heading_demotions": 0,
        "ai_structural_role_changes": 1,
        "elapsed": "1.2 c",
        "progress": 1.0,
        "status_notes": ["Структура: AI выключен, использованы текущие правила."],
        "raw_paragraph_count": 3,
        "logical_paragraph_count": 2,
        "merged_group_count": 1,
        "merged_raw_paragraph_count": 2,
        "high_confidence_merge_count": 0,
        "medium_accepted_merge_count": 0,
        "medium_rejected_candidate_count": 0,
    }


def test_schedule_stale_persisted_sources_cleanup_resets_flag_under_lock(monkeypatch):
    session_state = SessionState(persisted_source_cleanup_done=False)
    lock_events = []

    class TrackingLock:
        def __enter__(self):
            lock_events.append("enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            lock_events.append("exit")

    class ImmediateThread:
        def __init__(self, *, target, daemon, name):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "_CLEANUP_THREAD_LOCK", TrackingLock())
    monkeypatch.setattr(app, "_CLEANUP_THREAD_STARTED", False)
    monkeypatch.setattr(app.threading, "Thread", ImmediateThread)

    import restart_store

    cleanup_calls = []
    monkeypatch.setattr(restart_store, "cleanup_stale_persisted_sources", lambda **kwargs: cleanup_calls.append(kwargs))

    app._schedule_stale_persisted_sources_cleanup()

    assert cleanup_calls == [{"max_age_seconds": app.PERSISTED_SOURCE_TTL_SECONDS}]
    assert app._CLEANUP_THREAD_STARTED is False
    assert lock_events == ["enter", "exit", "enter", "exit"]


def test_app_ready_marker_writer_throttles_repeated_writes_within_window(tmp_path):
    ready_path = tmp_path / ".run" / "app.ready"
    time_values = iter([100.0, 105.0, 116.0])
    writer = AppReadyMarkerWriter(
        path=ready_path,
        freshness_window_seconds=15.0,
        time_fn=lambda: next(time_values),
    )

    assert writer.mark_ready() is True
    first_contents = ready_path.read_text(encoding="utf-8")

    assert writer.mark_ready() is False
    assert ready_path.read_text(encoding="utf-8") == first_contents

    assert writer.mark_ready() is True
    assert ready_path.read_text(encoding="utf-8") == "116.000000\n"


def test_mark_app_ready_uses_shared_throttled_writer(monkeypatch):
    calls = []

    class WriterStub:
        def mark_ready(self):
            calls.append("mark_ready")
            return False

    monkeypatch.setattr(app, "_APP_READY_MARKER_WRITER", WriterStub())

    app._mark_app_ready()

    assert calls == ["mark_ready"]


def test_render_processing_controls_keeps_start_visible_while_processing(monkeypatch):
    session_state = SessionState(processing_stop_requested=False)
    start_column = FakeColumn(result=False)
    stop_column = FakeColumn(result=False)

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [start_column, stop_column])
    action = app._render_processing_controls(can_start=False, is_processing=True)

    assert action is None
    assert start_column.calls == [(
        "Обработка запущена",
        {
            "type": "primary",
            "use_container_width": True,
            "disabled": True,
            "key": "start_processing_button",
        },
    )]
    assert stop_column.calls == [(
        "Стоп",
        {
            "use_container_width": True,
            "disabled": False,
            "key": "stop_processing_button",
        },
    )]


def test_render_processing_controls_enables_start_and_disables_stop_when_idle(monkeypatch):
    session_state = SessionState(processing_stop_requested=False)
    start_column = FakeColumn(result=True)
    stop_column = FakeColumn(result=False)

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [start_column, stop_column])
    action = app._render_processing_controls(can_start=True, is_processing=False)

    assert action == "start"
    assert start_column.calls == [(
        "Начать обработку",
        {
            "type": "primary",
            "use_container_width": True,
            "disabled": False,
            "key": "start_processing_button",
        },
    )]
    assert stop_column.calls == []


def test_render_processing_controls_demotes_start_after_completed_result(monkeypatch):
    session_state = SessionState(processing_stop_requested=False)
    start_column = FakeColumn(result=False)
    stop_column = FakeColumn(result=False)

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [start_column, stop_column])
    action = app._render_processing_controls(can_start=True, is_processing=False, emphasize_start=False)

    assert action is None
    assert start_column.calls == [(
        "Обработать повторно",
        {
            "type": "secondary",
            "use_container_width": True,
            "disabled": False,
            "key": "start_processing_button",
        },
    )]
    assert stop_column.calls == [(
        "Стоп",
        {
            "use_container_width": True,
            "disabled": True,
            "key": "stop_processing_button",
        },
    )]


def test_main_restarts_background_preparation_when_chunk_size_changes(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=object(),
        processing_status={},
        activity_feed=[],
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    start_calls = []

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 7000, 3, "safe", True))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app, "get_processing_session_snapshot", lambda: type("ProcessingSnapshot", (), {"latest_source_token": ""})())
    monkeypatch.setattr(app, "get_latest_image_mode", lambda: "safe")
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_start_background_preparation", lambda **kwargs: start_calls.append(kwargs))
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    try:
        app.main()
    except RerunRequested:
        pass
    else:
        raise AssertionError("Expected rerun after starting background preparation")

    assert len(start_calls) == 1
    assert start_calls[0]["upload_marker"] == "report.docx:3:ba7816bf8f01cfea:7000"
    assert start_calls[0]["chunk_size"] == 7000
    assert start_calls[0]["image_mode"] == "safe"
    assert start_calls[0]["keep_all_image_variants"] is True
    assert isinstance(start_calls[0]["uploaded_payload"], processing_runtime.FrozenUploadPayload)
    assert start_calls[0]["uploaded_payload"].filename == "report.docx"
    assert start_calls[0]["uploaded_payload"].content_bytes == b"abc"
    assert start_calls[0]["uploaded_payload"].file_token == "report.docx:3:ba7816bf8f01cfea"


def test_start_background_processing_passes_translate_context_to_runtime(monkeypatch):
    start_calls = []

    monkeypatch.setattr(app, "start_background_processing", lambda **kwargs: start_calls.append(kwargs))

    app._start_background_processing(
        uploaded_filename="report.docx",
        uploaded_token="report.docx:3:token",
        source_bytes=b"abc",
        jobs=[{"target_text": "block"}],
        source_paragraphs=["p1"],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=3,
        processing_operation="translate",
        source_language="auto",
        target_language="de",
    )

    assert len(start_calls) == 1
    assert start_calls[0]["processing_operation"] == "translate"
    assert start_calls[0]["source_language"] == "auto"
    assert start_calls[0]["target_language"] == "de"


def test_assess_text_transform_stores_assessment_in_session_state(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(state.st, "session_state", session_state)

    assessment = app._assess_text_transform(
        source_text="Привет, это уже русский текст.",
        target_language="ru",
    )

    assert assessment == session_state.text_transform_assessment
    assert assessment["dominant_language"] == "ru"
    assert assessment["dominant_script"] == "cyrillic"
    assert assessment["target_language_script_match"] is True


def test_maybe_apply_file_recommendations_auto_applies_once(monkeypatch):
    session_state = SessionState(
        sidebar_text_operation="Литературное редактирование",
        sidebar_source_language="English",
        sidebar_target_language="Русский",
    )
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "report.docx:3:abc"})()

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    with pytest.raises(RerunRequested):
        app._maybe_apply_file_recommendations(
            app_config={
                "processing_operation_default": "edit",
                "source_language_default": "en",
                "target_language_default": "ru",
                "supported_languages": [
                    type("Lang", (), {"code": "ru", "label": "Русский"})(),
                    type("Lang", (), {"code": "en", "label": "English"})(),
                ],
            },
            prepared_run_context=prepared_run_context,
            assessment={
                "dominant_language": None,
                "dominant_script": "latin",
                "target_language_script_match": False,
                "mixed_script_detected": False,
            },
            processing_operation="edit",
            source_language="en",
            target_language="ru",
        )

    assert session_state.recommended_text_settings["file_token"] == "report.docx:3:abc"
    assert session_state.recommended_text_settings_applied_for_token == "report.docx:3:abc"
    assert session_state.recommended_text_settings_notice_token == "report.docx:3:abc"
    assert session_state.recommended_text_settings_pending_widget_state == {
        "file_token": "report.docx:3:abc",
        "widget_state": {
            "sidebar_text_operation": "Перевод",
            "sidebar_source_language": "Авто",
        },
    }


def test_maybe_apply_file_recommendations_auto_applies_once_for_cached_preparation_context(monkeypatch):
    session_state = SessionState(
        sidebar_text_operation="Литературное редактирование",
        sidebar_source_language="English",
        sidebar_target_language="Русский",
    )
    prepared_run_context = type(
        "PreparedRunContextStub",
        (),
        {"uploaded_file_token": "report.docx:3:cached", "preparation_cached": True},
    )()

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    with pytest.raises(RerunRequested):
        app._maybe_apply_file_recommendations(
            app_config={
                "processing_operation_default": "edit",
                "source_language_default": "en",
                "target_language_default": "ru",
                "supported_languages": [
                    type("Lang", (), {"code": "ru", "label": "Русский"})(),
                    type("Lang", (), {"code": "en", "label": "English"})(),
                ],
            },
            prepared_run_context=prepared_run_context,
            assessment={
                "dominant_language": None,
                "dominant_script": "latin",
                "target_language_script_match": False,
                "mixed_script_detected": False,
            },
            processing_operation="edit",
            source_language="en",
            target_language="ru",
        )

    assert session_state.recommended_text_settings_applied_for_token == "report.docx:3:cached"
    assert session_state.recommended_text_settings_pending_widget_state == {
        "file_token": "report.docx:3:cached",
        "widget_state": {
            "sidebar_text_operation": "Перевод",
            "sidebar_source_language": "Авто",
        },
    }


def test_maybe_apply_file_recommendations_auto_applies_for_new_file_after_stale_widget_state_cleared(monkeypatch):
    session_state = SessionState(
        sidebar_text_operation="Перевод",
        sidebar_source_language="Авто",
        sidebar_target_language="Русский",
    )
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "new.docx:3:fresh"})()

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    # Simulate the file-switch cleanup that removes inherited widget ownership.
    del session_state["sidebar_text_operation"]
    del session_state["sidebar_source_language"]
    del session_state["sidebar_target_language"]

    with pytest.raises(RerunRequested):
        app._maybe_apply_file_recommendations(
            app_config={
                "processing_operation_default": "edit",
                "source_language_default": "en",
                "target_language_default": "ru",
                "supported_languages": [
                    type("Lang", (), {"code": "ru", "label": "Русский"})(),
                    type("Lang", (), {"code": "en", "label": "English"})(),
                ],
            },
            prepared_run_context=prepared_run_context,
            assessment={
                "dominant_language": None,
                "dominant_script": "latin",
                "target_language_script_match": False,
                "mixed_script_detected": False,
            },
            processing_operation="edit",
            source_language="en",
            target_language="ru",
        )

    assert session_state.manual_text_settings_override_for_token == {
        "file_token": "new.docx:3:fresh",
        "processing_operation": False,
        "source_language": False,
        "target_language": False,
    }
    assert session_state.recommended_text_settings_applied_for_token == "new.docx:3:fresh"
    assert session_state.recommended_text_settings_notice_token == "new.docx:3:fresh"
    assert session_state.recommended_text_settings_pending_widget_state == {
        "file_token": "new.docx:3:fresh",
        "widget_state": {
            "sidebar_text_operation": "Перевод",
            "sidebar_source_language": "Авто",
            "sidebar_target_language": "Русский",
        },
    }



def test_maybe_apply_file_recommendations_respects_preanalysis_manual_override(monkeypatch):
    session_state = SessionState(
        sidebar_text_operation="Перевод",
        sidebar_source_language="English",
        sidebar_target_language="Русский",
    )
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "report.docx:3:abc"})()

    rerun_calls = []
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "rerun", lambda: rerun_calls.append("rerun"))

    app._maybe_apply_file_recommendations(
        app_config={
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "supported_languages": [
                type("Lang", (), {"code": "ru", "label": "Русский"})(),
                type("Lang", (), {"code": "en", "label": "English"})(),
            ],
        },
        prepared_run_context=prepared_run_context,
        assessment={
            "dominant_language": "ru",
            "dominant_script": "cyrillic",
            "target_language_script_match": True,
            "mixed_script_detected": False,
        },
        processing_operation="translate",
        source_language="en",
        target_language="ru",
    )

    assert rerun_calls == []
    assert session_state.manual_text_settings_override_for_token == {
        "file_token": "report.docx:3:abc",
        "processing_operation": True,
        "source_language": False,
        "target_language": False,
    }
    assert session_state.recommended_text_settings_notice_token is None
    assert session_state.recommended_text_settings_pending_widget_state is None


def test_maybe_apply_file_recommendations_marks_manual_override_after_auto_apply(monkeypatch):
    session_state = SessionState(
        recommended_text_settings={
            "file_token": "report.docx:3:abc",
            "processing_operation": "edit",
            "source_language": "en",
            "target_language": "ru",
            "reason_summary": None,
        },
        recommended_text_settings_applied_for_token="report.docx:3:abc",
        recommended_text_settings_notice_token="report.docx:3:abc",
        manual_text_settings_override_for_token={
            "file_token": "report.docx:3:abc",
            "processing_operation": False,
            "source_language": False,
            "target_language": False,
        },
    )
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "report.docx:3:abc"})()

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "rerun", lambda: None)

    app._maybe_apply_file_recommendations(
        app_config={
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "supported_languages": [
                type("Lang", (), {"code": "ru", "label": "Русский"})(),
                type("Lang", (), {"code": "en", "label": "English"})(),
            ],
        },
        prepared_run_context=prepared_run_context,
        assessment={
            "dominant_language": "ru",
            "dominant_script": "cyrillic",
            "target_language_script_match": True,
            "mixed_script_detected": False,
        },
        processing_operation="translate",
        source_language="en",
        target_language="ru",
    )

    assert session_state.manual_text_settings_override_for_token["processing_operation"] is True
    assert session_state.recommended_text_settings_notice_token is None


def test_maybe_apply_file_recommendations_keeps_notice_after_own_auto_apply_rerun(monkeypatch):
    session_state = SessionState(
        recommended_text_settings={
            "file_token": "report.docx:3:abc",
            "processing_operation": "translate",
            "source_language": "auto",
            "target_language": "ru",
            "reason_summary": None,
        },
        recommended_text_settings_applied_for_token="report.docx:3:abc",
        recommended_text_settings_applied_snapshot={
            "file_token": "report.docx:3:abc",
            "processing_operation": "translate",
            "source_language": "auto",
            "target_language": "ru",
        },
        recommended_text_settings_notice_token="report.docx:3:abc",
        manual_text_settings_override_for_token={
            "file_token": "report.docx:3:abc",
            "processing_operation": False,
            "source_language": False,
            "target_language": False,
        },
    )
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "report.docx:3:abc"})()

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "rerun", lambda: None)

    app._maybe_apply_file_recommendations(
        app_config={
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "supported_languages": [
                type("Lang", (), {"code": "ru", "label": "Русский"})(),
                type("Lang", (), {"code": "en", "label": "English"})(),
            ],
        },
        prepared_run_context=prepared_run_context,
        assessment={
            "dominant_language": None,
            "dominant_script": "latin",
            "target_language_script_match": False,
            "mixed_script_detected": False,
        },
        processing_operation="translate",
        source_language="auto",
        target_language="ru",
    )

    assert session_state.manual_text_settings_override_for_token == {
        "file_token": "report.docx:3:abc",
        "processing_operation": False,
        "source_language": False,
        "target_language": False,
    }
    assert session_state.recommended_text_settings_notice_token == "report.docx:3:abc"


def test_maybe_apply_file_recommendations_keeps_notice_for_preanalysis_owned_field(monkeypatch):
    session_state = SessionState(
        recommended_text_settings={
            "file_token": "report.docx:3:abc",
            "processing_operation": "translate",
            "source_language": "auto",
            "target_language": "ru",
            "reason_summary": None,
        },
        recommended_text_settings_applied_for_token="report.docx:3:abc",
        recommended_text_settings_notice_token="report.docx:3:abc",
        manual_text_settings_override_for_token={
            "file_token": "report.docx:3:abc",
            "processing_operation": False,
            "source_language": True,
            "target_language": False,
        },
    )
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "report.docx:3:abc"})()

    rerun_calls = []
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "rerun", lambda: rerun_calls.append("rerun"))

    app._maybe_apply_file_recommendations(
        app_config={
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "supported_languages": [
                type("Lang", (), {"code": "ru", "label": "Русский"})(),
                type("Lang", (), {"code": "en", "label": "English"})(),
                type("Lang", (), {"code": "de", "label": "Deutsch"})(),
            ],
        },
        prepared_run_context=prepared_run_context,
        assessment={
            "dominant_language": None,
            "dominant_script": "latin",
            "target_language_script_match": False,
            "mixed_script_detected": False,
        },
        processing_operation="translate",
        source_language="de",
        target_language="ru",
    )

    assert rerun_calls == []
    assert session_state.manual_text_settings_override_for_token == {
        "file_token": "report.docx:3:abc",
        "processing_operation": False,
        "source_language": True,
        "target_language": False,
    }
    assert session_state.recommended_text_settings_notice_token == "report.docx:3:abc"


def test_maybe_apply_file_recommendations_preserves_user_owned_source_when_hidden(monkeypatch):
    session_state = SessionState(
        recommended_text_settings={
            "file_token": "report.docx:3:abc",
            "processing_operation": "translate",
            "source_language": "en",
            "target_language": "ru",
            "reason_summary": None,
        },
        recommended_text_settings_applied_for_token="report.docx:3:abc",
        manual_text_settings_override_for_token={
            "file_token": "report.docx:3:abc",
            "processing_operation": False,
            "source_language": True,
            "target_language": False,
        },
    )
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "report.docx:3:abc"})()

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "rerun", lambda: None)

    app._maybe_apply_file_recommendations(
        app_config={
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "supported_languages": [
                type("Lang", (), {"code": "ru", "label": "Русский"})(),
                type("Lang", (), {"code": "en", "label": "English"})(),
            ],
        },
        prepared_run_context=prepared_run_context,
        assessment={
            "dominant_language": "ru",
            "dominant_script": "cyrillic",
            "target_language_script_match": True,
            "mixed_script_detected": False,
        },
        processing_operation="edit",
        source_language="auto",
        target_language="ru",
    )

    assert session_state.manual_text_settings_override_for_token["source_language"] is True


def test_maybe_apply_file_recommendations_allows_non_owned_fields_to_auto_apply(monkeypatch):
    session_state = SessionState(
        sidebar_text_operation="Литературное редактирование",
        sidebar_source_language="English",
        sidebar_target_language="English",
    )
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "report.docx:3:partial"})()

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    with pytest.raises(RerunRequested):
        app._maybe_apply_file_recommendations(
            app_config={
                "processing_operation_default": "edit",
                "source_language_default": "en",
                "target_language_default": "ru",
                "supported_languages": [
                    type("Lang", (), {"code": "ru", "label": "Русский"})(),
                    type("Lang", (), {"code": "en", "label": "English"})(),
                ],
            },
            prepared_run_context=prepared_run_context,
            assessment={
                "dominant_language": None,
                "dominant_script": "latin",
                "target_language_script_match": False,
                "mixed_script_detected": False,
            },
            processing_operation="edit",
            source_language="en",
            target_language="en",
        )

    assert session_state.manual_text_settings_override_for_token == {
        "file_token": "report.docx:3:partial",
        "processing_operation": False,
        "source_language": False,
        "target_language": True,
    }
    assert session_state.recommended_text_settings_pending_widget_state == {
        "file_token": "report.docx:3:partial",
        "widget_state": {
            "sidebar_text_operation": "Перевод",
            "sidebar_source_language": "Авто",
        },
    }


def test_maybe_apply_file_recommendations_keeps_manual_override_after_restart(monkeypatch):
    session_state = SessionState(
        recommended_text_settings={
            "file_token": "report.docx:3:restart",
            "processing_operation": "translate",
            "source_language": "auto",
            "target_language": "ru",
            "reason_summary": None,
        },
        recommended_text_settings_applied_for_token="report.docx:3:restart",
        manual_text_settings_override_for_token={
            "file_token": "report.docx:3:restart",
            "processing_operation": True,
            "source_language": False,
            "target_language": False,
        },
    )
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "report.docx:3:restart"})()

    rerun_calls = []
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "rerun", lambda: rerun_calls.append("rerun"))

    app._maybe_apply_file_recommendations(
        app_config={
            "processing_operation_default": "edit",
            "source_language_default": "en",
            "target_language_default": "ru",
            "supported_languages": [
                type("Lang", (), {"code": "ru", "label": "Русский"})(),
                type("Lang", (), {"code": "en", "label": "English"})(),
            ],
        },
        prepared_run_context=prepared_run_context,
        assessment={
            "dominant_language": None,
            "dominant_script": "latin",
            "target_language_script_match": False,
            "mixed_script_detected": False,
        },
        processing_operation="edit",
        source_language="auto",
        target_language="ru",
    )

    assert rerun_calls == []
    assert session_state.manual_text_settings_override_for_token == {
        "file_token": "report.docx:3:restart",
        "processing_operation": True,
        "source_language": False,
        "target_language": False,
    }


def test_should_render_recommended_text_settings_notice_only_for_real_auto_apply(monkeypatch):
    session_state = SessionState(recommended_text_settings_notice_token="report.docx:3:token")

    monkeypatch.setattr(app.st, "session_state", session_state)

    assert app._should_render_recommended_text_settings_notice("report.docx:3:token") is True
    assert app._should_render_recommended_text_settings_notice("other.docx:5:token") is False
    assert app._should_render_recommended_text_settings_notice("") is False


def test_build_recommended_text_settings_notice_lists_changed_settings(monkeypatch):
    session_state = SessionState(
        recommended_text_settings_notice_token="report.docx:3:token",
        recommended_text_settings_notice_details={
            "file_token": "report.docx:3:token",
            "changes": [
                "режим: Литературное редактирование -> Перевод",
                "язык оригинала: English -> Авто",
            ],
        },
    )

    monkeypatch.setattr(app.st, "session_state", session_state)

    notice = app._build_recommended_text_settings_notice("report.docx:3:token")

    assert notice == (
        "После анализа файла приложение скорректировало текстовые настройки: "
        "режим: Литературное редактирование -> Перевод; язык оригинала: English -> Авто."
    )


def test_main_places_recommended_text_settings_notice_inside_preparation_summary(monkeypatch):
    prepared_run_context = _build_prepared_run_context(
        preparation_cached=True,
        normalization_report=type("NormalizationReportStub", (), {
            "total_raw_paragraphs": 4,
            "total_logical_paragraphs": 3,
            "merged_group_count": 1,
            "merged_raw_paragraph_count": 2,
        })(),
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        image_assets=[],
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=prepared_run_context,
        latest_docx_bytes=None,
        latest_source_token="",
        latest_markdown="",
        latest_image_mode="safe",
        last_error="",
        last_log_hint="hint",
        processing_outcome="idle",
        recommended_text_settings_notice_token=prepared_run_context.uploaded_file_token,
        recommended_text_settings_notice_details={
            "file_token": prepared_run_context.uploaded_file_token,
            "changes": [
                "режим: Литературное редактирование -> Перевод",
                "язык оригинала: English -> Авто",
            ],
        },
    )
    summary_calls = []
    caption_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: caption_calls.append(args))
    monkeypatch.setattr(app, "render_preparation_summary", lambda summary, *args, **kwargs: summary_calls.append(summary))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)
    monkeypatch.setattr(app, "get_processing_session_snapshot", lambda: type("ProcessingSnapshot", (), {"latest_source_token": ""})())
    monkeypatch.setattr(app, "get_latest_image_mode", lambda: "safe")
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "file_selected")
    monkeypatch.setattr(application_flow, "prepare_run_context", lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")))

    app.main()

    assert len(summary_calls) == 1
    assert summary_calls[0]["status_notes"] == [
        "Структура: AI выключен, использованы текущие правила.",
        "После анализа файла приложение скорректировало текстовые настройки: "
        "режим: Литературное редактирование -> Перевод; язык оригинала: en -> Авто.",
    ]
    assert caption_calls == []


def test_apply_pending_recommended_widget_state_applies_before_sidebar(monkeypatch):
    session_state = SessionState(
        recommended_text_settings_pending_widget_state={
            "file_token": "report.docx:3:abc",
            "widget_state": {
                "sidebar_text_operation": "Перевод",
                "sidebar_source_language": "Авто",
            },
        }
    )

    monkeypatch.setattr(app.st, "session_state", session_state)

    app._apply_pending_recommended_widget_state()

    assert session_state.sidebar_text_operation == "Перевод"
    assert session_state.sidebar_source_language == "Авто"
    assert session_state.recommended_text_settings_pending_widget_state is None


def test_apply_pending_recommended_widget_state_uses_state_consumer(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app,
        "consume_recommended_text_settings_pending_widget_state",
        lambda: {
            "file_token": "report.docx:3:abc",
            "widget_state": {
                "sidebar_text_operation": "Перевод",
                "sidebar_source_language": "Авто",
            },
        },
    )

    app._apply_pending_recommended_widget_state()

    assert session_state.sidebar_text_operation == "Перевод"
    assert session_state.sidebar_source_language == "Авто"


def test_apply_pending_recommended_widget_state_uses_state_widget_apply_helper(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(app.st, "session_state", session_state)
    apply_calls = []
    monkeypatch.setattr(
        app,
        "consume_recommended_text_settings_pending_widget_state",
        lambda: {
            "file_token": "report.docx:3:abc",
            "widget_state": {"sidebar_text_operation": "Перевод"},
        },
    )
    monkeypatch.setattr(app, "apply_recommended_widget_state", lambda payload: apply_calls.append(payload))

    app._apply_pending_recommended_widget_state()

    assert apply_calls == [{"sidebar_text_operation": "Перевод"}]


def test_main_normalizes_legacy_doc_before_starting_background_preparation(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
    )
    uploaded_file = UploadedFileStub("legacy.doc", bytes.fromhex("D0CF11E0A1B11AE1") + b"legacy")
    start_calls = []

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        processing_runtime,
        "_convert_legacy_doc_to_docx",
        lambda **kwargs: (b"converted-docx", "antiword+pandoc"),
    )
    monkeypatch.setattr(app, "_start_background_preparation", lambda **kwargs: start_calls.append(kwargs))
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    try:
        app.main()
    except RerunRequested:
        pass
    else:
        raise AssertionError("Expected rerun after starting background preparation")

    assert len(start_calls) == 1
    assert isinstance(start_calls[0]["uploaded_payload"], processing_runtime.FrozenUploadPayload)
    assert start_calls[0]["uploaded_payload"].filename == "legacy.docx"
    assert start_calls[0]["uploaded_payload"].content_bytes == b"converted-docx"
    assert start_calls[0]["uploaded_payload"].file_token.startswith("legacy.docx:")
    assert start_calls[0]["upload_marker"].startswith("legacy.docx:")


def test_main_renders_live_status_during_active_preparation(monkeypatch):
    session_state = SessionState(app_start_logged=True, processing_status={}, activity_feed=[])
    calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: True)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: calls.append("live_status"))
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: calls.append("run_log"))

    app.main()

    assert calls == ["live_status", "run_log"]


def test_main_keeps_processing_panel_visible_while_outcome_is_running(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        processing_outcome="running",
        processing_stop_requested=False,
    )
    calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_intro_layout_styles", lambda: calls.append("intro"))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: calls.append("live_status"))
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: calls.append("run_log"))
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: calls.append("image_summary"))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: calls.append("partial_result"))
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)

    app.main()

    assert calls == ["live_status", "run_log", "image_summary", "partial_result"]


def test_main_renders_preparation_summary_for_prepared_file(monkeypatch):
    prepared_run_context = _build_prepared_run_context(
        preparation_cached=True,
        normalization_report=type("NormalizationReportStub", (), {
            "total_raw_paragraphs": 4,
            "total_logical_paragraphs": 3,
            "merged_group_count": 1,
            "merged_raw_paragraph_count": 2,
        })(),
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        image_assets=[],
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=prepared_run_context,
        latest_docx_bytes=None,
        latest_source_token="",
        latest_markdown="",
        latest_image_mode="safe",
        last_error="",
        last_log_hint="hint",
        processing_outcome="idle",
    )
    summary_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app, "get_processing_session_snapshot", lambda: type("ProcessingSnapshot", (), {"latest_source_token": ""})())
    monkeypatch.setattr(app, "get_latest_image_mode", lambda: "safe")
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_preparation_summary", lambda summary, *args, **kwargs: summary_calls.append(summary))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "file_selected")
    monkeypatch.setattr(application_flow, "prepare_run_context", lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")))

    app.main()

    assert len(summary_calls) == 1
    expected_summary = dict(session_state.latest_preparation_summary)
    if "status_notes" in summary_calls[0]:
        expected_summary["status_notes"] = summary_calls[0]["status_notes"]
    assert summary_calls[0] == expected_summary
    assert summary_calls[0]["cached"] is True
    assert summary_calls[0]["block_count"] == 2
    assert summary_calls[0]["ai_classified"] == 0
    assert summary_calls[0]["ai_headings"] == 0
    assert summary_calls[0]["raw_paragraph_count"] == 4
    assert summary_calls[0]["logical_paragraph_count"] == 3
    assert summary_calls[0]["merged_group_count"] == 1
    assert summary_calls[0]["merged_raw_paragraph_count"] == 2
    assert summary_calls[0]["high_confidence_merge_count"] == 0
    assert summary_calls[0]["medium_accepted_merge_count"] == 0
    assert summary_calls[0]["medium_rejected_candidate_count"] == 0


def test_main_marks_prepared_status_with_completed_terminal_kind(monkeypatch):
    prepared_run_context = _build_prepared_run_context(
        normalization_report=type("NormalizationReportStub", (), {
            "total_raw_paragraphs": 4,
            "total_logical_paragraphs": 3,
            "merged_group_count": 1,
            "merged_raw_paragraph_count": 2,
        })(),
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        image_assets=[],
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=prepared_run_context,
        latest_docx_bytes=None,
        latest_source_token="",
        latest_markdown="",
        latest_image_mode="safe",
        last_error="",
        last_log_hint="hint",
        processing_outcome="idle",
    )
    status_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_preparation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)
    monkeypatch.setattr(app, "set_processing_status", lambda **kwargs: status_calls.append(kwargs))
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "file_selected")
    monkeypatch.setattr(application_flow, "prepare_run_context", lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")))

    app.main()

    assert len(status_calls) == 1
    assert status_calls[0]["stage"] == "Документ подготовлен"
    assert status_calls[0]["phase"] == "preparing"
    assert status_calls[0]["terminal_kind"] == "completed"
    assert status_calls[0]["raw_paragraph_count"] == 4
    assert status_calls[0]["logical_paragraph_count"] == 3
    assert status_calls[0]["merged_group_count"] == 1
    assert status_calls[0]["merged_raw_paragraph_count"] == 2


def test_store_preparation_summary_includes_auto_structure_status_note(monkeypatch):
    session_state = SessionState()
    prepared_run_context = _build_prepared_run_context(
        structure_recognition_mode="auto",
        structure_ai_attempted=True,
        structure_map=object(),
        structure_recognition_summary=StructureRecognitionSummary(ai_classified_count=6, ai_heading_count=2),
        structure_validation_report=StructureValidationReport(
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
        ),
    )

    monkeypatch.setattr(app.st, "session_state", session_state)

    app._store_preparation_summary(prepared_run_context=prepared_run_context)

    assert session_state.latest_preparation_summary["status_notes"] == [
        "Структура: auto-режим, выполнена эскалация в AI; классифицировано 6 абзацев, найдено 2 заголовков. Причины: мало явных заголовков, обнаружен TOC-подобный фрагмент."
    ]


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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
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
            "Обработка файла «report.docx» была остановлена. Можно изменить настройки и запустить заново без повторной загрузки."
        ]
        assert error_calls == []
    else:
        assert warning_calls == []
        assert error_calls[0] == "Обработка файла «report.docx» завершилась ошибкой. Можно изменить настройки и запустить заново без повторной загрузки."


@pytest.mark.parametrize("outcome", ["stopped", "failed"])
def test_restartable_idle_view_shows_typed_outcome_notice(monkeypatch, outcome):
    """When idle_view_state == RESTARTABLE, the outcome-specific notice must appear."""
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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app, "render_file_uploader_state_styles", lambda **kwargs: None)
    monkeypatch.setattr(app.st, "info", lambda text: info_calls.append(text))
    monkeypatch.setattr(app.st, "warning", lambda text: warning_calls.append(text))
    monkeypatch.setattr(app.st, "error", lambda text, *args, **kwargs: error_calls.append(text))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
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


def test_sync_selected_file_context_resets_run_state_for_new_file(monkeypatch):
    session_state = SessionState(
        selected_source_token="old.docx:10",
        sidebar_text_operation="Перевод",
        sidebar_source_language="Авто",
        sidebar_target_language="Русский",
        previous_result=None,
        latest_docx_bytes=b"docx",
        latest_source_name="old.docx",
        latest_source_token="old.docx:10",
        latest_markdown="markdown",
        run_log=[{"status": "STOP"}],
        activity_feed=[{"time": "10:00:00", "message": "stale"}],
        processed_block_markdowns=["partial"],
        last_error="",
        image_assets=[],
        image_validation_failures=[],
        image_processing_summary={},
        processing_status={},
        processing_stop_requested=False,
        processing_worker=None,
        processing_event_queue=None,
        processing_stop_event=None,
        processing_outcome="idle",
        prepared_source_key="old.docx:10:6000",
        restart_source={"filename": "old.docx", "storage_path": "old.bin"},
    )
    reset_calls = []
    monkeypatch.setattr(state.st, "session_state", session_state)

    application_flow.sync_selected_file_context(
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: (reset_calls.append(kwargs), session_state.update(run_log=[], activity_feed=[], restart_source=None)),
        uploaded_file_token="new.docx:20",
    )

    assert reset_calls == [{"keep_restart_source": False}]
    assert session_state.selected_source_token == "new.docx:20"
    assert session_state.restart_source is None
    assert session_state.run_log == []
    assert session_state.activity_feed == []
    assert "sidebar_text_operation" not in session_state
    assert "sidebar_source_language" not in session_state
    assert "sidebar_target_language" not in session_state


def test_has_resettable_state_depends_on_restartable_source(tmp_path):
    restart_path = tmp_path / "restart.bin"
    restart_path.write_bytes(b"abc")
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": str(restart_path)})

    assert application_flow.has_resettable_state(current_result=None, session_state=session_state) is True  # type: ignore[arg-type]

    session_state.processing_outcome = "idle"

    assert application_flow.has_resettable_state(current_result=None, session_state=session_state) is False  # type: ignore[arg-type]


def test_derive_idle_view_state_covers_idle_paths(tmp_path):
    restart_path = tmp_path / "restart.bin"
    restart_path.write_bytes(b"abc")
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": str(restart_path)})

    assert application_flow.derive_app_idle_view_state(current_result=None, uploaded_file=object(), session_state=session_state) == "file_selected"
    assert application_flow.derive_app_idle_view_state(current_result={"docx_bytes": b"x"}, uploaded_file=None, session_state=session_state) == "completed"
    assert application_flow.derive_app_idle_view_state(current_result=None, uploaded_file=None, session_state=session_state) == "restartable"

    session_state.processing_outcome = "idle"

    assert application_flow.derive_app_idle_view_state(current_result=None, uploaded_file=None, session_state=session_state) == "empty"


def test_get_cached_restart_file_returns_none_when_storage_missing(monkeypatch):
    session_state = SessionState(restart_source={"filename": "report.docx", "storage_path": "missing.bin"})
    monkeypatch.setattr(application_flow, "load_restart_source_bytes", lambda restart_source: None)

    assert application_flow.get_cached_restart_file(session_state=session_state) is None  # type: ignore[arg-type]


def test_resolve_effective_uploaded_file_uses_completed_source_after_success():
    session_state = SessionState(
        completed_source={"filename": "report.docx", "storage_path": "completed.bin", "token": "report.docx:3:abc"}
    )

    uploaded_file = application_flow.resolve_effective_uploaded_file(
        uploaded_file=None,
        current_result={"docx_bytes": b"done"},
        session_state=session_state,
        load_restart_source_bytes_fn=lambda source: b"abc",
    )

    assert uploaded_file is not None
    assert uploaded_file.name == "report.docx"
    assert uploaded_file.getvalue() == b"abc"


def test_main_rejects_oversized_upload_before_preparation(monkeypatch):
    session_state = SessionState(app_start_logged=True, processing_status={}, activity_feed=[])
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    uploaded_file.size = MAX_DOCX_ARCHIVE_SIZE_BYTES + 1
    errors = []
    preparation_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: session_state.setdefault("persisted_source_cleanup_done", False))
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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


def test_has_restartable_source_does_not_materialize_restart_bytes(tmp_path, monkeypatch):
    restart_path = tmp_path / "restart.bin"
    restart_path.write_bytes(b"abc")
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": str(restart_path)})
    load_calls = []
    monkeypatch.setattr(application_flow, "load_restart_source_bytes", lambda restart_source: load_calls.append(restart_source) or b"abc")

    assert application_flow.has_restartable_source(session_state=session_state) is True  # type: ignore[arg-type]
    assert load_calls == []


def test_has_restartable_source_returns_false_when_restart_file_was_removed(tmp_path):
    restart_path = tmp_path / "restart.bin"
    restart_path.write_bytes(b"abc")
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": str(restart_path)})
    restart_path.unlink()

    assert application_flow.has_restartable_source(session_state=session_state) is False  # type: ignore[arg-type]
def test_compare_panel_is_noop_for_completed_compare_assets(monkeypatch):
    calls = []

    monkeypatch.setattr(compare_panel.st, "info", lambda message: calls.append(("info", message)))
    monkeypatch.setattr(compare_panel.st, "caption", lambda message: calls.append(("caption", message)))

    compare_panel.render_compare_all_apply_panel(
        latest_image_mode="compare_all",
        image_assets=[ImageAsset(image_id="img_001", placeholder="[[DOCX_IMAGE_img_001]]", original_bytes=b"x", mime_type="image/png", position_index=0, comparison_variants={"safe": {"bytes": b"safe"}}, validation_status="compared", final_decision="compared")],
        render_section_gap=lambda gap: calls.append(("gap", gap)),
    )

    assert calls == []


def test_compare_panel_does_not_render_apply_controls(monkeypatch):
    calls = []

    monkeypatch.setattr(compare_panel.st, "info", lambda message: calls.append(("info", message)))
    monkeypatch.setattr(compare_panel.st, "caption", lambda message: calls.append(("caption", message)))

    compare_panel.render_compare_all_apply_panel(
        latest_image_mode="compare_all",
        image_assets=[ImageAsset(image_id="img_001", placeholder="[[DOCX_IMAGE_img_001]]", original_bytes=b"x", mime_type="image/png", position_index=0, comparison_variants={"safe": {"bytes": b"safe"}}, validation_status="compared", final_decision="compared")],
        render_section_gap=lambda gap: calls.append(("gap", gap)),
    )

    assert not any(kind == "apply" for kind, _ in calls)
    assert not any(kind == "selector" for kind, _ in calls)


def test_compare_panel_hides_incomplete_compare_assets(monkeypatch):
    calls = []

    monkeypatch.setattr(compare_panel.st, "info", lambda message: calls.append(("info", message)))
    monkeypatch.setattr(compare_panel.st, "caption", lambda message: calls.append(("caption", message)))

    compare_panel.render_compare_all_apply_panel(
        latest_image_mode="compare_all",
        image_assets=[ImageAsset(image_id="img_001", placeholder="[[DOCX_IMAGE_img_001]]", original_bytes=b"x", mime_type="image/png", position_index=0, comparison_variants={"safe": {"bytes": b"safe"}}, validation_status="failed", final_decision="fallback_safe")],
        render_section_gap=lambda gap: calls.append(("gap", gap)),
    )

    assert calls == []
