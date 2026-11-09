"""Spec 062 (owner request 2026-11-09): the image-model pair preselected per image mode.

The pair is the measured best one (``D:\\Temp\\docxai-runs\\image-compare-2026-11-07\\verdicts.md``):
the reading model ``gpt-6.1-terra`` everywhere, the drawing model ``flare`` for structured
redraw and compare-all, ``sunburst`` for direct redraw. The sidebar (headless ``AppTest``) and the
real-document runner resolve through the same ``core.config`` resolver; a user's pick in the UI
survives reruns of its mode, and another mode starts from its own default.

Also pins the trimmed ``[models.text].options`` list.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from docxaicorrector.core import config
from docxaicorrector.ui import _ui as ui
from docxaicorrector.validation import profiles

VISION_ROLES = ("image_analysis", "image_validation", "image_reconstruction", "image_generation_vision")
DRAW_ROLES = ("image_generation", "image_edit")

PER_MODE_PAIRS = {
    "semantic_redraw_structured": ("gpt-6.1-terra", "gpt-image-2.5-flare"),
    "semantic_redraw_direct": ("gpt-6.1-terra", "gpt-image-2.5-sunburst"),
    "compare_all": ("gpt-6.1-terra", "gpt-image-2.5-flare"),
}

_SIDEBAR_SCRIPT = """
import streamlit as st
from docxaicorrector.core.config import load_app_config
from docxaicorrector.ui._ui import render_sidebar

st.session_state["_sidebar_result"] = render_sidebar(load_app_config())
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for role in (*VISION_ROLES, *DRAW_ROLES):
        monkeypatch.delenv(f"DOCX_AI_MODELS_{role.upper()}_DEFAULT", raising=False)
    monkeypatch.delenv("DOCX_AI_IMAGE_VISION_MODEL", raising=False)
    monkeypatch.delenv("DOCX_AI_IMAGE_DRAW_MODEL", raising=False)
    config.reset_app_config_cache()
    yield
    config.reset_app_config_cache()


def _run_sidebar() -> AppTest:
    at = AppTest.from_string(_SIDEBAR_SCRIPT, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def _select_mode(at: AppTest, image_mode: str) -> AppTest:
    at.sidebar.selectbox(key="sidebar_image_mode").select(ui.IMAGE_MODE_LABELS[image_mode]).run()
    assert not at.exception, at.exception
    return at


def _pair(at: AppTest) -> tuple[str, str]:
    result = at.session_state["_sidebar_result"]
    return result[9], result[10]


def _selector_keys(at: AppTest) -> list[str]:
    return [str(widget.key) for widget in at.sidebar.selectbox if "image_vision" in str(widget.key) or "image_draw" in str(widget.key)]


@pytest.mark.parametrize("image_mode", sorted(PER_MODE_PAIRS))
def test_sidebar_preselects_the_measured_pair_of_each_mode(image_mode):
    at = _select_mode(_run_sidebar(), image_mode)

    assert _pair(at) == PER_MODE_PAIRS[image_mode]
    assert _selector_keys(at) == [
        f"sidebar_image_vision_model__{image_mode}",
        f"sidebar_image_draw_model__{image_mode}",
    ]


@pytest.mark.parametrize("image_mode", ["safe", "no_change"])
def test_safe_and_no_change_show_no_image_model_selector(image_mode):
    # safe analyses without vision (image/pipeline.py enable_vision=False) and draws with PIL only.
    at = _select_mode(_run_sidebar(), image_mode)

    assert _selector_keys(at) == []
    assert _pair(at) == ("", "")


def test_a_user_choice_survives_a_rerun_in_the_same_mode_and_does_not_leak_into_another():
    at = _select_mode(_run_sidebar(), "semantic_redraw_direct")
    at.sidebar.selectbox(key="sidebar_image_vision_model__semantic_redraw_direct").select("gpt-6.1-sol")
    at.sidebar.selectbox(key="sidebar_image_draw_model__semantic_redraw_direct").select("gpt-image-2.5-flare")
    at.run()
    assert _pair(at) == ("gpt-6.1-sol", "gpt-image-2.5-flare")

    at.run()  # an unrelated rerun keeps the user's pick
    assert _pair(at) == ("gpt-6.1-sol", "gpt-image-2.5-flare")

    _select_mode(at, "semantic_redraw_structured")  # another mode: its own default, not the pick
    assert _pair(at) == PER_MODE_PAIRS["semantic_redraw_structured"]

    _select_mode(at, "semantic_redraw_direct")  # back: the pick of that mode is still there
    assert _pair(at) == ("gpt-6.1-sol", "gpt-image-2.5-flare")


def test_a_pick_survives_switching_to_another_mode_and_operation_and_back():
    at = _select_mode(_run_sidebar(), "semantic_redraw_structured")
    at.sidebar.selectbox(key="sidebar_image_vision_model__semantic_redraw_structured").select("gpt-6.1-sol")
    at.sidebar.selectbox(key="sidebar_image_draw_model__semantic_redraw_structured").select("gpt-image-2.5-sunburst")
    at.run()
    picked = ("gpt-6.1-sol", "gpt-image-2.5-sunburst")
    assert _pair(at) == picked

    _select_mode(at, "semantic_redraw_direct")
    assert _pair(at) == PER_MODE_PAIRS["semantic_redraw_direct"]
    _select_mode(at, "semantic_redraw_structured")
    assert _pair(at) == picked

    at.sidebar.selectbox(key="sidebar_text_operation").select(ui.TEXT_OPERATION_LABELS["translate"]).run()
    assert not at.exception, at.exception
    at.sidebar.selectbox(key="sidebar_text_operation").select(ui.TEXT_OPERATION_LABELS["edit"]).run()
    assert not at.exception, at.exception
    _select_mode(at, "semantic_redraw_structured")
    assert _pair(at) == picked


def test_a_per_role_pin_still_outranks_the_mode_default(monkeypatch):
    monkeypatch.setenv("DOCX_AI_MODELS_IMAGE_EDIT_DEFAULT", "gpt-image-2.5-flare-2026-09-08")
    config.reset_app_config_cache()

    selected = config.apply_image_model_selection(
        config.load_app_config(), image_mode="semantic_redraw_direct"
    )

    assert config.get_model_role_value(selected, "image_edit") == "gpt-image-2.5-flare-2026-09-08"
    assert config.get_model_role_value(selected, "image_generation") == "gpt-image-2.5-sunburst"
    assert config.get_model_role_value(selected, "image_analysis") == "gpt-6.1-terra"


def test_a_group_env_pin_outranks_the_shipped_mode_table(monkeypatch):
    monkeypatch.setenv("DOCX_AI_IMAGE_VISION_MODEL", "gpt-6.1-sol")
    config.reset_app_config_cache()
    app_config = config.load_app_config()

    assert config.get_image_model_choice(app_config, "vision", "compare_all")[0] == "gpt-6.1-sol"
    assert config.get_image_model_choice(app_config, "draw", "compare_all")[0] == "gpt-image-2.5-flare"


@pytest.mark.parametrize("image_mode", sorted(PER_MODE_PAIRS))
def test_runner_resolves_the_same_pair_as_the_ui(image_mode):
    app_config = config.load_app_config()
    run_profile = profiles.RunProfile(id="probe", image_mode=image_mode)

    resolution = profiles.resolve_runtime_resolution(app_config, run_profile)
    run_app_config = profiles.apply_runtime_resolution_to_app_config(app_config, resolution)

    vision, draw = PER_MODE_PAIRS[image_mode]
    effective = resolution.effective.to_dict()
    assert (effective["image_vision_model"], effective["image_draw_model"]) == (vision, draw)
    assert {role: config.get_model_role_value(run_app_config, role) for role in (*VISION_ROLES, *DRAW_ROLES)} == {
        **{role: vision for role in VISION_ROLES},
        **{role: draw for role in DRAW_ROLES},
    }
    # The UI path: the same resolver, fed the mode.
    ui_config = config.apply_image_model_selection(app_config, image_mode=image_mode)
    assert {role: config.get_model_role_value(ui_config, role) for role in (*VISION_ROLES, *DRAW_ROLES)} == {
        role: config.get_model_role_value(run_app_config, role) for role in (*VISION_ROLES, *DRAW_ROLES)
    }


def test_a_profile_pin_outranks_the_mode_default_and_modes_without_an_entry_keep_the_plain_default():
    app_config = config.load_app_config()
    pinned = profiles.resolve_runtime_resolution(
        app_config,
        profiles.RunProfile(id="pin", image_mode="semantic_redraw_direct", image_draw_model="gpt-image-2.5-flare"),
    )
    assert pinned.effective.image_draw_model == "gpt-image-2.5-flare"
    assert pinned.effective.image_vision_model == "gpt-6.1-terra"

    for image_mode in ("safe", "no_change"):
        plain = profiles.resolve_runtime_resolution(app_config, profiles.RunProfile(id="plain", image_mode=image_mode))
        run_app_config = profiles.apply_runtime_resolution_to_app_config(app_config, plain)
        assert plain.effective.image_vision_model == "gpt-5.4-mini"
        assert run_app_config["models"] is app_config.models


def test_unknown_image_mode_in_mode_defaults_is_ignored_and_reported(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[models.image_vision.mode_defaults]\ncompare_all = "gpt-6.1-sol"\nnot_a_mode = "gpt-6.1-terra"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    events = []
    monkeypatch.setattr(config, "log_event", lambda level, event_id, message, **context: events.append((event_id, context)))
    config._EMITTED_MODEL_REGISTRY_LOG_KEYS.clear()

    app_config = config.load_app_config()

    assert config.get_image_model_choice(app_config, "vision", "compare_all")[0] == "gpt-6.1-sol"
    ignored = [context["ignored_keys"] for event_id, context in events if event_id == "config_key_ignored"]
    assert ignored == [["models.image_vision.mode_defaults.not_a_mode"]]


def test_a_non_openai_mode_default_fails_the_load(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[models.image_vision.mode_defaults]\ncompare_all = "openrouter:google/gemini-3.1-flash-lite-preview"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    with pytest.raises(RuntimeError, match="openrouter"):
        config.load_app_config()


def test_text_model_options_are_the_two_measured_models_only():
    app_config = config.load_app_config()

    assert tuple(app_config.models.text.options) == (
        "openrouter:google/gemini-3.1-flash-lite-preview",
        "openrouter:google/gemini-3.7-flash",
    )
    assert app_config.models.text.default == "openrouter:google/gemini-3.1-flash-lite-preview"
    for removed in (
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5-mini",
        "anthropic:claude-sonnet-4-6",
        "openrouter:anthropic/claude-sonnet-4.6",
    ):
        assert removed not in app_config.models.text.options
