import pytest

import app
from conftest import SessionState as SessionState


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


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