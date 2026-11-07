"""Spec 062: the two image-model choices (reading / drawing) and how they meet per-role pins.

Resolution per image role, highest first:
  1. DOCX_AI_MODELS_IMAGE_<ROLE>_DEFAULT              (per-role pin, env)
  2. [models.image_<role>].default                    (per-role pin, config.toml)
  3. the UI selector / run profile image_vision_model, image_draw_model
  4. DOCX_AI_IMAGE_VISION_MODEL / DOCX_AI_IMAGE_DRAW_MODEL, then [models.image_vision|draw].default
"""

import logging
import tomllib
from dataclasses import replace
from types import SimpleNamespace

import pytest

from docxaicorrector.core import config
from docxaicorrector.core import model_accounting
from docxaicorrector.image import shared as image_shared
from docxaicorrector.validation import profiles

VISION_ROLES = ("image_analysis", "image_validation", "image_reconstruction", "image_generation_vision")
DRAW_ROLES = ("image_generation", "image_edit")
ALL_ROLE_ENV_NAMES = [f"DOCX_AI_MODELS_{role.upper()}_DEFAULT" for role in (*VISION_ROLES, *DRAW_ROLES)]


@pytest.fixture(autouse=True)
def _clean_image_model_env(monkeypatch):
    for env_name in (*ALL_ROLE_ENV_NAMES, "DOCX_AI_IMAGE_VISION_MODEL", "DOCX_AI_IMAGE_DRAW_MODEL"):
        monkeypatch.delenv(env_name, raising=False)
    config.reset_app_config_cache()
    yield
    config.reset_app_config_cache()


def _role_models(app_config) -> dict[str, str]:
    return {role: config.get_model_role_value(app_config, role) for role in (*VISION_ROLES, *DRAW_ROLES)}


def test_shipped_config_defaults_are_variant_1_and_offer_both_variants_and_terra():
    app_config = config.load_app_config()

    assert _role_models(app_config) == {
        **{role: "gpt-5.4-mini" for role in VISION_ROLES},
        **{role: "gpt-image-2.5-flare" for role in DRAW_ROLES},
    }
    assert app_config.image_vision_model_options == ("gpt-5.4-mini", "gpt-6.1-sol", "gpt-6.1-terra")
    assert app_config.image_draw_model_options == ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst")
    assert app_config.image_model_role_overrides == ()


def test_shipped_config_lists_match_the_builtin_fallback():
    # The built-in lists in core/config.py are what a config.toml without the two sections
    # gets; they must not drift from what the shipped file offers.
    shipped_models = tomllib.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))["models"]
    for group, section in (("vision", "image_vision"), ("draw", "image_draw")):
        builtin_default, builtin_options = config._BUILTIN_IMAGE_MODEL_GROUPS[group]
        assert shipped_models[section]["default"] == builtin_default
        assert tuple(shipped_models[section]["options"]) == builtin_options


def test_missing_config_falls_back_to_the_builtin_groups(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH.parent / "__missing_config__.toml")

    app_config = config.load_app_config()

    assert _role_models(app_config)["image_edit"] == "gpt-image-2.5-flare"
    assert app_config.image_vision_model_options == config._BUILTIN_IMAGE_MODEL_GROUPS["vision"][1]


def test_group_env_sets_the_default_for_every_role_of_its_group(monkeypatch):
    monkeypatch.setenv("DOCX_AI_IMAGE_VISION_MODEL", "gpt-6.1-terra")
    monkeypatch.setenv("DOCX_AI_IMAGE_DRAW_MODEL", "gpt-image-2.5-sunburst")

    app_config = config.load_app_config()

    assert _role_models(app_config) == {
        **{role: "gpt-6.1-terra" for role in VISION_ROLES},
        **{role: "gpt-image-2.5-sunburst" for role in DRAW_ROLES},
    }
    assert app_config.image_vision_model_default == "gpt-6.1-terra"


def test_selection_sets_the_six_roles_and_a_per_role_pin_still_wins(monkeypatch):
    monkeypatch.setenv("DOCX_AI_MODELS_IMAGE_EDIT_DEFAULT", "gpt-image-2.5-flare-2026-09-08")
    monkeypatch.setenv("DOCX_AI_MODELS_IMAGE_VALIDATION_DEFAULT", "gpt-5.4-mini")
    events: list[tuple[int, str, dict]] = []
    monkeypatch.setattr(config, "log_event", lambda level, event_id, message, **context: events.append((level, event_id, context)))
    config._EMITTED_MODEL_REGISTRY_LOG_KEYS.clear()

    app_config = config.load_app_config()
    selected = config.apply_image_model_selection(
        app_config,
        vision_model="gpt-6.1-sol",
        draw_model="gpt-image-2.5-sunburst",
    )

    assert _role_models(selected) == {
        "image_analysis": "gpt-6.1-sol",
        "image_validation": "gpt-5.4-mini",  # pinned
        "image_reconstruction": "gpt-6.1-sol",
        "image_generation_vision": "gpt-6.1-sol",
        "image_generation": "gpt-image-2.5-sunburst",
        "image_edit": "gpt-image-2.5-flare-2026-09-08",  # pinned
    }
    assert selected.validation_model == "gpt-5.4-mini"
    assert selected.reconstruction_model == "gpt-6.1-sol"
    override_events = [event for event in events if event[1] == "image_model_role_override_active"]
    assert len(override_events) == 1
    assert override_events[0][0] == logging.WARNING
    assert override_events[0][2]["role_overrides"] == {
        "image_edit": "gpt-image-2.5-flare-2026-09-08",
        "image_validation": "gpt-5.4-mini",
    }


def test_selection_outranks_the_group_env_default(monkeypatch):
    monkeypatch.setenv("DOCX_AI_IMAGE_VISION_MODEL", "gpt-6.1-terra")

    selected = config.apply_image_model_selection(config.load_app_config(), vision_model="gpt-6.1-sol")

    assert {role: _role_models(selected)[role] for role in VISION_ROLES} == {role: "gpt-6.1-sol" for role in VISION_ROLES}


def test_selection_works_on_the_plain_dict_the_ui_and_runner_pass(monkeypatch):
    app_config_dict = dict(config.load_app_config())

    selected = config.apply_image_model_selection(app_config_dict, draw_model="gpt-image-2.5-sunburst")

    assert isinstance(selected, dict)
    assert _role_models(selected)["image_edit"] == "gpt-image-2.5-sunburst"
    assert _role_models(app_config_dict)["image_edit"] == "gpt-image-2.5-flare"  # input untouched


def test_empty_selection_returns_the_config_unchanged():
    app_config = config.load_app_config()

    assert config.apply_image_model_selection(app_config, vision_model="", draw_model=None) is app_config


def test_selection_of_a_non_openai_model_is_refused():
    with pytest.raises(RuntimeError, match="только OpenAI"):
        config.apply_image_model_selection(config.load_app_config(), vision_model="openrouter:google/gemini-3.1-flash-lite-preview")


def test_a_non_openai_option_in_config_fails_the_load(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[models.image_vision]\ndefault = "gpt-5.4-mini"\noptions = ["gpt-5.4-mini", "openrouter:google/gemini-3.1-flash-lite-preview"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    # Rejected at load (provider lock), so the UI can never offer it.
    with pytest.raises(RuntimeError, match="openrouter"):
        config.load_app_config()


def test_run_profile_choice_lands_in_effective_config_and_in_the_run_app_config():
    app_config = config.load_app_config()
    run_profile = profiles.RunProfile(
        id="probe",
        image_mode="semantic_redraw_structured",
        image_vision_model="gpt-6.1-terra",
        image_draw_model="gpt-image-2.5-sunburst",
    )

    resolution = profiles.resolve_runtime_resolution(app_config, run_profile)
    run_app_config = profiles.apply_runtime_resolution_to_app_config(app_config, resolution)

    expected_roles = {
        **{role: "gpt-6.1-terra" for role in VISION_ROLES},
        **{role: "gpt-image-2.5-sunburst" for role in DRAW_ROLES},
    }
    effective = resolution.effective.to_dict()
    assert effective["image_vision_model"] == "gpt-6.1-terra"
    assert effective["image_draw_model"] == "gpt-image-2.5-sunburst"
    assert effective["image_models"] == {role: expected_roles[role] for role in config.IMAGE_MODEL_ROLE_NAMES}
    assert resolution.overrides["image_vision_model"] == "gpt-6.1-terra"
    assert resolution.ui_defaults.image_models["image_edit"] == "gpt-image-2.5-flare"
    assert _role_models(run_app_config) == expected_roles


def test_run_profile_without_a_choice_keeps_the_loaded_registry():
    app_config = config.load_app_config()
    resolution = profiles.resolve_runtime_resolution(app_config, profiles.RunProfile(id="plain"))

    run_app_config = profiles.apply_runtime_resolution_to_app_config(app_config, resolution)

    assert "image_vision_model" not in resolution.overrides
    assert run_app_config["models"] is app_config.models


def test_corpus_registry_ships_one_semantic_profile_per_variant_and_mode():
    registry = profiles.load_validation_registry()
    image_profiles = {
        profile.id: profile
        for profile in registry.run_profiles
        if profile.image_draw_model is not None or profile.image_vision_model is not None
    }
    combos = {
        (profile.image_mode, profile.image_vision_model, profile.image_draw_model)
        for profile in image_profiles.values()
    }

    assert combos == {
        (mode, vision, draw)
        for mode in ("semantic_redraw_structured", "semantic_redraw_direct")
        for vision, draw in (("gpt-5.4-mini", "gpt-image-2.5-flare"), ("gpt-6.1-sol", "gpt-image-2.5-sunburst"))
    }
    options = config.load_app_config()
    for profile in image_profiles.values():
        assert profile.image_vision_model in options.image_vision_model_options
        assert profile.image_draw_model in options.image_draw_model_options


def test_ledger_counts_calls_per_image_role_and_model():
    with model_accounting.run_model_accounting_scope(run_id="r", source_token="s"):
        model_accounting.record_model_call_usage(
            stage=model_accounting.STAGE_IMAGE_GENERATION,
            response=SimpleNamespace(usage=None),
            model="gpt-image-2.5-sunburst",
            image_role="image_edit",
        )
        model_accounting.record_model_call_usage(stage=model_accounting.STAGE_TEXT_GENERATION, response=SimpleNamespace(usage=None))

        class FakeResponses:
            def create(self, **kwargs):
                return SimpleNamespace(usage=None, output_text="{}")

        image_shared.call_responses_create_with_retry(
            SimpleNamespace(responses=FakeResponses()),
            {"model": "gpt-6.1-terra", "input": []},
            max_retries=1,
            retryable_error_predicate=lambda exc: False,
            usage_stage=model_accounting.STAGE_IMAGE_ANALYSIS,
        )
        snapshot = model_accounting.snapshot_run_model_accounting()

    # Text calls name no image role and stay out of the per-role map.
    assert snapshot["image_model_call_counts_by_role"] == {
        "image_analysis": {"gpt-6.1-terra": 1},
        "image_edit": {"gpt-image-2.5-sunburst": 1},
    }
    assert snapshot["model_call_count"] == 3


def test_override_caption_and_choice_helpers_read_stub_configs():
    stub = {"models": SimpleNamespace(text=SimpleNamespace(default="gpt-5.4", options=("gpt-5.4",)))}

    assert config.get_image_model_choice(stub, "vision") == ("gpt-5.4-mini", ("gpt-5.4-mini",))
    assert config.get_image_model_role_overrides(stub) == {}
    assert config.get_image_model_role_overrides({"image_model_role_overrides": (("image_edit", "x"),)}) == {"image_edit": "x"}


def test_model_registry_resolved_sources_name_the_group(monkeypatch):
    monkeypatch.setenv("DOCX_AI_IMAGE_DRAW_MODEL", "gpt-image-2.5-sunburst")
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(config, "log_event", lambda level, event_id, message, **context: events.append((event_id, context)))
    config._EMITTED_MODEL_REGISTRY_LOG_KEYS.clear()

    config.load_app_config()

    registry_event = next(context for event_id, context in events if event_id == "model_registry_resolved")
    assert registry_event["model_sources"]["image_edit"] == "group:draw<-env:DOCX_AI_IMAGE_DRAW_MODEL"
    assert registry_event["model_sources"]["image_analysis"] == "group:vision<-toml:models.image_vision.default"


def test_replace_keeps_app_config_hashable_fields():
    # The new AppConfig fields are tuples, so a selected config stays a frozen value.
    selected = config.apply_image_model_selection(config.load_app_config(), vision_model="gpt-6.1-terra")
    assert isinstance(selected, config.AppConfig)
    assert replace(selected).image_vision_model_options == selected.image_vision_model_options


def test_run_profile_naming_a_non_openai_image_model_stops_the_resolution():
    run_profile = profiles.RunProfile(id="bad", image_vision_model="anthropic:claude-sonnet-4-6")

    with pytest.raises(RuntimeError, match="только OpenAI"):
        profiles.resolve_runtime_resolution(config.load_app_config(), run_profile)
