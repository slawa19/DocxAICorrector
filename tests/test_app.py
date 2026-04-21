import pytest

import app
import state
from conftest import SessionState as SessionState


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


def test_resolve_sidebar_settings_accepts_new_text_transform_tuple():
    result = app._resolve_sidebar_settings(("gpt-5.4", 6000, 3, "safe", True, "translate", "auto", "de"))

    assert result == ("gpt-5.4", 6000, 3, "safe", True, "translate", "auto", "de")


def test_resolve_sidebar_settings_keeps_legacy_tuple_compatible():
    result = app._resolve_sidebar_settings(("gpt-5.4", 6000, 3, "safe", True))

    assert result == ("gpt-5.4", 6000, 3, "safe", True, "edit", "en", "ru")


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


