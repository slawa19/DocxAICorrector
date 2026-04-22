import pytest

import app
import application_flow
import compare_panel
from conftest import SessionState as SessionState
from models import StructureRecognitionSummary


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
                "режим: изменено с Литературное редактирование на Перевод",
                "язык оригинала: изменено с English на Авто",
            ],
        },
    )

    monkeypatch.setattr(app.st, "session_state", session_state)

    notice = app._build_recommended_text_settings_notice("report.docx:3:token")

    assert notice == (
        "После анализа файла приложение скорректировало текстовые настройки: "
        "режим: изменено с Литературное редактирование на Перевод; язык оригинала: изменено с English на Авто."
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
                "режим: изменено с Литературное редактирование на Перевод",
                "язык оригинала: изменено с English на Авто",
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
        "режим: изменено с Литературное редактирование на Перевод; язык оригинала: изменено с en на Авто.",
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