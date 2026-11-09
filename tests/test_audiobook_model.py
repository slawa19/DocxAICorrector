"""Spec 070 FR-008 (WP-B): one resolver decides the model of an audiobook run, for the UI and the runner.

Priority: the user's audiobook choice (UI) or the run profile's model (runner) ->
``[models.audiobook].default`` -> ``[models.text].default``. Each statement below has a
counter-proof: break the rule it pins and the test fails.
"""

from __future__ import annotations

import dataclasses
import logging

import pytest
from streamlit.testing.v1 import AppTest

import docxaicorrector.core.config as config
import docxaicorrector.ui._app as app
import docxaicorrector.ui._ui as ui
import docxaicorrector.validation.profiles as vp
from docxaicorrector.core import audiobook_mode
from docxaicorrector.core.audiobook_mode import AudiobookModelResolution, resolve_audiobook_model
from test_app_preparation import _PAID_SOURCE_TOKEN, _run_main_for_processing_start_guard

TEXT_DEFAULT = "openrouter:google/gemini-3.1-flash-lite-preview"
AUDIOBOOK_DEFAULT = "openrouter:google/gemini-3.7-flash"


@pytest.fixture(autouse=True)
def _isolate_config_cache():
    config.reset_app_config_cache()
    config._EMITTED_MODEL_REGISTRY_LOG_KEYS.clear()
    yield
    config.reset_app_config_cache()
    config._EMITTED_MODEL_REGISTRY_LOG_KEYS.clear()


def _load(monkeypatch, tmp_path, toml_text: str):
    path = tmp_path / "config.toml"
    path.write_text(toml_text, encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    return config.load_app_config()


# ------------------------------------------------------------------- the resolver itself


def test_a_requested_model_wins_over_the_configured_one():
    resolution = resolve_audiobook_model({"audiobook_model": "from-config"}, requested_model="from-user", origin="test")

    assert resolution == AudiobookModelResolution(model="from-user", source="requested")


@pytest.mark.parametrize("requested", [None, "", "   "])
def test_without_a_request_the_configured_audiobook_model_is_used(requested):
    resolution = resolve_audiobook_model({"audiobook_model": "from-config"}, requested_model=requested, origin="test")

    assert resolution == AudiobookModelResolution(model="from-config", source="config")


def test_the_loader_folds_audiobook_section_then_text_default(monkeypatch, tmp_path):
    # Step two of the chain, as the loader computes it for ``app_config["audiobook_model"]``.
    with_section = _load(monkeypatch, tmp_path, '[models.audiobook]\ndefault = "gpt-5.4"\n')
    assert resolve_audiobook_model(with_section, requested_model=None, origin="test").model == "gpt-5.4"

    config.reset_app_config_cache()
    without_section = _load(monkeypatch, tmp_path, "")
    resolved = resolve_audiobook_model(without_section, requested_model=None, origin="test").model
    # Step three: no section -> the text default (not the audiobook value of the other load).
    assert resolved == config.get_text_model_default(without_section)
    assert resolved != "gpt-5.4"


def test_a_mapping_without_a_resolved_audiobook_model_falls_back_to_the_text_default():
    text_models = type("Models", (), {"text": type("T", (), {"default": "text-default", "options": ("text-default",)})()})()

    resolution = resolve_audiobook_model({"models": text_models}, requested_model=None, origin="test")

    assert resolution == AudiobookModelResolution(model="text-default", source="config")


def test_the_resolver_logs_origin_model_and_source(monkeypatch):
    events: list[tuple[int, str, dict[str, object]]] = []
    monkeypatch.setattr(audiobook_mode, "log_event", lambda level, event_id, message, **ctx: events.append((level, event_id, ctx)))

    resolve_audiobook_model({"audiobook_model": "m"}, requested_model=None, origin="run_profile:x")

    assert events == [(logging.DEBUG, "audiobook_model_resolved", {"origin": "run_profile:x", "model": "m", "source": "config"})]


# ------------------------------------------- UI and runner call THE SAME function (a spy sees both)


def _spy(monkeypatch):
    calls: list[tuple[str | None, str]] = []

    def spy(app_config, *, requested_model, origin):
        calls.append((requested_model, origin))
        return AudiobookModelResolution(model="spy-model", source="config")

    for module in (app, ui, vp):
        monkeypatch.setattr(module, "resolve_audiobook_model", spy)
    return calls


def test_the_ui_start_and_the_runner_both_go_through_the_one_resolver(monkeypatch):
    calls = _spy(monkeypatch)
    sidebar = ("gpt-5.4", 6000, 3, "safe", False, "audiobook", "en", "ru")
    record = _run_main_for_processing_start_guard(
        monkeypatch,
        current_result=None,
        sidebar_result=sidebar,
        session_overrides={"preparation_input_marker": f"{_PAID_SOURCE_TOKEN}:6000:op=audiobook"},
    )

    assert [origin for _requested, origin in calls] == ["ui"]
    assert calls[0][0] == "gpt-5.4"  # the sidebar's value is passed as the user's choice
    assert record["processing_starts"][0]["model"] == "spy-model"

    profile = next(p for p in vp.load_validation_registry().run_profiles if p.id == "ui-parity-standalone-audiobook")
    resolution = vp.resolve_runtime_resolution(config.load_app_config(), dataclasses.replace(profile, model="profile-model"))

    assert ("profile-model", "run_profile:ui-parity-standalone-audiobook") in calls
    assert resolution.effective.model == "spy-model"


def test_the_resolver_is_not_consulted_for_translate_and_edit(monkeypatch):
    calls = _spy(monkeypatch)
    profiles = {p.id: p for p in vp.load_validation_registry().run_profiles}

    translate = vp.resolve_runtime_resolution(config.load_app_config(), profiles["ui-parity-translate-baseline"])

    assert calls == []
    assert translate.effective.model != "spy-model"


def test_the_runner_profile_model_beats_the_config_model():
    profile = next(p for p in vp.load_validation_registry().run_profiles if p.id == "ui-parity-standalone-audiobook")
    app_config = config.load_app_config()

    pinned = vp.resolve_runtime_resolution(app_config, dataclasses.replace(profile, model="pinned-model"))
    unpinned = vp.resolve_runtime_resolution(app_config, dataclasses.replace(profile, model=None))

    assert pinned.effective.model == "pinned-model"
    assert unpinned.effective.model == app_config["audiobook_model"]


# ------------------------- the user's audiobook choice lives apart from the edit choice (AppTest)

_SIDEBAR_SCRIPT = """
import streamlit as st
from docxaicorrector.core.config import load_app_config
from docxaicorrector.ui._ui import render_sidebar

st.session_state["_sidebar_result"] = render_sidebar(load_app_config())
"""


def _sidebar_at(monkeypatch) -> AppTest:
    real_load = config.load_app_config

    def patched_load(*args, **kwargs):
        loaded = dict(real_load(*args, **kwargs))
        loaded["audiobook_model"] = AUDIOBOOK_DEFAULT
        return loaded

    monkeypatch.setattr(config, "load_app_config", patched_load)
    at = AppTest.from_string(_SIDEBAR_SCRIPT, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def _switch(at: AppTest, operation: str) -> None:
    at.sidebar.selectbox(key="sidebar_text_operation").select(ui.TEXT_OPERATION_LABELS[operation]).run()
    assert not at.exception, at.exception


def test_audiobook_starts_from_its_own_default_not_from_the_edit_selection(monkeypatch):
    at = _sidebar_at(monkeypatch)
    assert at.sidebar.selectbox(key="sidebar_model").value == TEXT_DEFAULT  # edit: the text default

    _switch(at, "audiobook")

    assert at.sidebar.selectbox(key="sidebar_model_audiobook").value == AUDIOBOOK_DEFAULT
    assert at.session_state["_sidebar_result"][0] == AUDIOBOOK_DEFAULT


def test_a_choice_made_in_audiobook_does_not_leak_into_edit_and_survives_a_round_trip(monkeypatch):
    at = _sidebar_at(monkeypatch)
    _switch(at, "audiobook")
    at.sidebar.selectbox(key="sidebar_model_audiobook").select(TEXT_DEFAULT).run()
    assert at.session_state["_sidebar_result"][0] == TEXT_DEFAULT

    _switch(at, "edit")
    # Edit keeps ITS value: with one shared key it would now show the audiobook pick.
    assert at.sidebar.selectbox(key="sidebar_model").value == TEXT_DEFAULT
    at.sidebar.selectbox(key="sidebar_model").select(AUDIOBOOK_DEFAULT).run()

    _switch(at, "audiobook")
    # ...and the audiobook choice outlives the widget (kept in its own non-widget key), not
    # replaced by what edit has now.
    assert at.sidebar.selectbox(key="sidebar_model_audiobook").value == TEXT_DEFAULT
    assert at.session_state["_sidebar_result"][0] == TEXT_DEFAULT


def test_a_configured_audiobook_model_outside_the_offered_options_is_shown_as_custom(monkeypatch):
    real_load = config.load_app_config

    def patched_load(*args, **kwargs):
        loaded = dict(real_load(*args, **kwargs))
        loaded["audiobook_model"] = "gpt-5.4"
        return loaded

    monkeypatch.setattr(config, "load_app_config", patched_load)
    at = AppTest.from_string(_SIDEBAR_SCRIPT, default_timeout=30)
    at.run()
    _switch(at, "audiobook")

    assert at.sidebar.selectbox(key="sidebar_model_audiobook").value == "custom"
    assert at.session_state["_sidebar_result"][0] == "gpt-5.4"
