"""Spec 069 FR-001: the translation-mode config contract and the one resolution function.

Contract: ``specs/069-translation-modes/contracts/translation-modes-config.md``.
"""

from __future__ import annotations

import logging

import pytest

import docxaicorrector.core.config as config
import docxaicorrector.core.translation_modes as translation_modes
from docxaicorrector.core.translation_modes import (
    EffectiveTranslationConfig,
    TranslationPassSpec,
    apply_effective_translation_config,
    resolve_effective_translation_config,
)

_MODE_ENV_PREFIX = "DOCX_AI_TRANSLATION_MODES_"
_SHIPPED_STANDARD_MODEL = "openrouter:google/gemini-3.1-flash-lite-preview"
_SHIPPED_QUALITY_MODEL = "openrouter:google/gemini-3.7-flash"
_SHIPPED_POLISH_MODEL = "openrouter:anthropic/claude-haiku-5.5"


@pytest.fixture(autouse=True)
def _isolate_config_cache():
    config.reset_app_config_cache()
    yield
    config.reset_app_config_cache()


@pytest.fixture
def log_calls(monkeypatch):
    calls: list[tuple[int, str, dict[str, object]]] = []

    def fake_log_event(level, event, message, **context):
        calls.append((level, event, context))
        return "evt"

    monkeypatch.setattr(translation_modes, "log_event", fake_log_event)
    monkeypatch.setattr(config, "log_event", fake_log_event)
    return calls


def _shipped_text_without_modes() -> str:
    kept: list[str] = []
    skipping = False
    for line in config.CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[translation_modes"):
            skipping = True
            continue
        if stripped.startswith("translation_mode_default"):
            continue
        if skipping and stripped.startswith("["):
            skipping = False
        if skipping:
            continue
        kept.append(line)
    return "\n".join(kept) + "\n"


def _use_config(monkeypatch, tmp_path, modes_toml: str):
    """Shipped config minus its mode sections plus ``modes_toml`` (top-level keys first)."""
    path = tmp_path / "config.toml"
    text = _shipped_text_without_modes()
    top_level, _, tables = modes_toml.partition("\n[")
    path.write_text(top_level + "\n" + text + (("\n[" + tables) if tables else "") + "\n", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    return path


_VALID_MODES = f"""translation_mode_default = "standard"

[translation_modes.standard]
model = "{_SHIPPED_STANDARD_MODEL}"
editorial_intensity = "literary"
polish_model = "{_SHIPPED_POLISH_MODEL}"

[translation_modes.quality]
model = "{_SHIPPED_QUALITY_MODEL}"
editorial_intensity = "conservative"
reasoning_effort = "low"
"""


def _load():
    config.reset_app_config_cache()
    return config.load_app_config()


# ---------------------------------------------------------------------------------------
# T1.2: TOML + env contract
# ---------------------------------------------------------------------------------------


def test_shipped_config_declares_both_modes_per_the_contract():
    app_config = config.load_app_config()

    assert app_config.translation_mode_default == "standard"
    modes = app_config.translation_modes
    assert set(modes) == {"standard", "quality"}
    standard, quality = modes["standard"], modes["quality"]
    assert standard.first_pass == TranslationPassSpec(
        model=_SHIPPED_STANDARD_MODEL, editorial_intensity="literary", reasoning_effort=None
    )
    assert standard.polish_pass is not None
    assert standard.polish_pass.model == _SHIPPED_POLISH_MODEL
    assert standard.polish_pass.reasoning_effort is None
    assert quality.first_pass == TranslationPassSpec(
        model=_SHIPPED_QUALITY_MODEL, editorial_intensity="conservative", reasoning_effort="low"
    )
    assert quality.polish_pass is None


def test_toml_values_are_read(monkeypatch, tmp_path):
    _use_config(monkeypatch, tmp_path, _VALID_MODES.replace('"literary"', '"conservative"', 1))

    modes = _load().translation_modes

    assert modes["standard"].first_pass.editorial_intensity == "conservative"


def test_env_overrides_toml_for_every_field(monkeypatch, tmp_path):
    _use_config(monkeypatch, tmp_path, _VALID_MODES)
    monkeypatch.setenv("DOCX_AI_TRANSLATION_MODE_DEFAULT", "quality")
    monkeypatch.setenv(_MODE_ENV_PREFIX + "STANDARD_MODEL", "openrouter:vendor/other-model")
    monkeypatch.setenv(_MODE_ENV_PREFIX + "STANDARD_EDITORIAL_INTENSITY", "conservative")
    monkeypatch.setenv(_MODE_ENV_PREFIX + "STANDARD_REASONING_EFFORT", "medium")
    monkeypatch.setenv(_MODE_ENV_PREFIX + "STANDARD_POLISH_MODEL", "openrouter:vendor/polisher")
    monkeypatch.setenv(_MODE_ENV_PREFIX + "STANDARD_POLISH_REASONING_EFFORT", "high")

    app_config = _load()

    assert app_config.translation_mode_default == "quality"
    standard = app_config.translation_modes["standard"]
    assert standard.first_pass == TranslationPassSpec(
        model="openrouter:vendor/other-model", editorial_intensity="conservative", reasoning_effort="medium"
    )
    assert standard.polish_pass == TranslationPassSpec(
        model="openrouter:vendor/polisher", editorial_intensity=None, reasoning_effort="high"
    )


def test_env_none_removes_reasoning_and_the_second_pass(monkeypatch, tmp_path):
    _use_config(monkeypatch, tmp_path, _VALID_MODES)
    monkeypatch.setenv(_MODE_ENV_PREFIX + "QUALITY_REASONING_EFFORT", "none")
    monkeypatch.setenv(_MODE_ENV_PREFIX + "STANDARD_POLISH_MODEL", "none")

    modes = _load().translation_modes

    assert modes["quality"].first_pass.reasoning_effort is None
    assert modes["standard"].polish_pass is None


def test_unknown_key_inside_a_mode_section_is_reported_as_ignored(monkeypatch, tmp_path, log_calls):
    _use_config(monkeypatch, tmp_path, _VALID_MODES + 'surprise_knob = "x"\n')

    _load()

    ignored = [ctx["ignored_keys"] for _, event, ctx in log_calls if event == "config_key_ignored"]
    assert ignored == [["translation_modes.quality.surprise_knob"]]


def test_valid_mode_sections_report_no_ignored_keys(monkeypatch, tmp_path, log_calls):
    _use_config(monkeypatch, tmp_path, _VALID_MODES)

    _load()

    assert [event for _, event, _ in log_calls if event == "config_key_ignored"] == []


def test_third_mode_section_is_a_load_error(monkeypatch, tmp_path):
    _use_config(monkeypatch, tmp_path, _VALID_MODES + f'\n[translation_modes.foo]\nmodel = "{_SHIPPED_QUALITY_MODEL}"\n')

    with pytest.raises(RuntimeError, match="foo"):
        _load()


@pytest.mark.parametrize(
    "mutation",
    [
        ("model = \"" + _SHIPPED_QUALITY_MODEL + "\"\neditorial_intensity = \"conservative\"", 'model = "nosuchprovider:x"\neditorial_intensity = "conservative"'),
        ('editorial_intensity = "conservative"', 'editorial_intensity = "shouting"'),
        ('reasoning_effort = "low"', 'reasoning_effort = "extreme"'),
        ('reasoning_effort = "low"', 'reasoning_effort = "low"\npolish_reasoning_effort = "low"'),
        ('translation_mode_default = "standard"', 'translation_mode_default = "single"'),
        ('translation_mode_default = "standard"', 'translation_mode_default = "nonsense"'),
    ],
    ids=["model", "intensity", "reasoning", "polish-reasoning-without-model", "default-single", "default-unknown"],
)
def test_invalid_values_are_load_errors(monkeypatch, tmp_path, mutation):
    old, new = mutation
    assert old in _VALID_MODES
    _use_config(monkeypatch, tmp_path, _VALID_MODES.replace(old, new, 1))

    with pytest.raises(RuntimeError):
        _load()


def test_invalid_env_values_are_load_errors(monkeypatch, tmp_path):
    _use_config(monkeypatch, tmp_path, _VALID_MODES)
    monkeypatch.setenv(_MODE_ENV_PREFIX + "QUALITY_REASONING_EFFORT", "extreme")

    with pytest.raises(RuntimeError):
        _load()


def test_default_pointing_at_an_undeclared_mode_is_a_load_error(monkeypatch, tmp_path):
    only_quality = _VALID_MODES.split("[translation_modes.standard]")[0] + "[translation_modes.quality]" + _VALID_MODES.split(
        "[translation_modes.quality]"
    )[1]
    _use_config(monkeypatch, tmp_path, only_quality)

    with pytest.raises(RuntimeError, match="standard"):
        _load()


def test_modes_resolved_event_names_the_source_of_each_value(monkeypatch, tmp_path, log_calls):
    _use_config(monkeypatch, tmp_path, _VALID_MODES)
    monkeypatch.setenv(_MODE_ENV_PREFIX + "QUALITY_REASONING_EFFORT", "medium")

    _load()

    events = [(level, ctx) for level, event, ctx in log_calls if event == "translation_modes_resolved"]
    assert len(events) == 1
    level, context = events[0]
    assert level == logging.DEBUG
    sources = context["sources"]
    assert sources["quality.reasoning_effort"] == "env"
    assert sources["quality.model"] == "toml"


def test_config_without_any_mode_section_still_loads(monkeypatch, tmp_path):
    _use_config(monkeypatch, tmp_path, "")

    app_config = _load()

    assert app_config.translation_mode_default == "standard"
    assert dict(app_config.translation_modes) == {}
    # ... but asking for a mode that was never configured is an error, not a silent fallback.
    with pytest.raises(RuntimeError, match="standard"):
        resolve_effective_translation_config(
            app_config,
            processing_operation="translate",
            requested_mode=None,
            requested_model=None,
            requested_intensity=None,
            origin="ui",
        )


# ---------------------------------------------------------------------------------------
# T1.3: the one resolution function
# ---------------------------------------------------------------------------------------


def _resolve(app_config, *, operation="translate", mode=None, model=None, intensity=None, origin="ui"):
    return resolve_effective_translation_config(
        app_config,
        processing_operation=operation,
        requested_mode=mode,
        requested_model=model,
        requested_intensity=intensity,
        origin=origin,
    )


@pytest.mark.parametrize("mode", ["standard", "quality"])
def test_mode_beats_requested_model_and_intensity_with_a_warning(mode, log_calls):
    app_config = config.load_app_config()
    spec = app_config.translation_modes[mode]

    effective = _resolve(
        app_config,
        mode=mode,
        model="openrouter:vendor/user-picked",
        intensity="conservative" if spec.first_pass.editorial_intensity == "literary" else "literary",
        origin="run_profile:demo",
    )

    assert effective is not None
    assert effective.mode == mode
    assert effective.first_pass.model == spec.first_pass.model
    assert effective.first_pass.editorial_intensity == spec.first_pass.editorial_intensity
    assert effective.first_pass.reasoning_effort == spec.first_pass.reasoning_effort
    assert effective.polish_pass == spec.polish_pass
    assert effective.overridden_settings == ("model", "editorial_intensity")
    warnings = [ctx for level, event, ctx in log_calls if event == "translation_mode_overrides_setting"]
    assert len(warnings) == 1
    assert warnings[0]["origin"] == "run_profile:demo"
    assert warnings[0]["fields"] == ["model", "editorial_intensity"]
    assert [level for level, event, _ in log_calls if event == "translation_mode_overrides_setting"] == [logging.WARNING]


def test_no_warning_when_the_requested_values_equal_the_modes(log_calls):
    app_config = config.load_app_config()
    spec = app_config.translation_modes["standard"]

    effective = _resolve(
        app_config,
        mode="standard",
        model=spec.first_pass.model,
        intensity=spec.first_pass.editorial_intensity,
    )

    assert effective is not None and effective.overridden_settings == ()
    assert [event for _, event, _ in log_calls if event == "translation_mode_overrides_setting"] == []


def test_mode_defaults_to_translation_mode_default(log_calls):
    app_config = config.load_app_config()

    effective = _resolve(app_config)

    assert effective is not None
    assert effective.mode == app_config.translation_mode_default
    assert effective.origin == "ui"


def test_single_keeps_the_requested_model_and_intensity_without_reasoning_or_second_pass(log_calls):
    app_config = config.load_app_config()

    effective = _resolve(app_config, mode="single", model="openrouter:vendor/pinned", intensity="conservative")

    assert effective is not None
    assert effective.mode == "single"
    assert effective.first_pass == TranslationPassSpec(
        model="openrouter:vendor/pinned", editorial_intensity="conservative", reasoning_effort=None
    )
    assert effective.polish_pass is None
    assert effective.overridden_settings == ()
    assert [event for _, event, _ in log_calls if event.startswith("translation_mode_")] == []


def test_single_without_requests_uses_the_shared_defaults():
    app_config = config.load_app_config()

    effective = _resolve(app_config, mode="single")

    assert effective is not None
    assert effective.first_pass.model == config.get_text_model_default(app_config)
    assert effective.first_pass.editorial_intensity == app_config["editorial_intensity_default"]


@pytest.mark.parametrize("operation", ["edit", "audiobook"])
def test_edit_and_audiobook_resolve_to_none_and_leave_app_config_untouched(operation):
    app_config = config.load_app_config()

    effective = _resolve(app_config, operation=operation)
    applied = apply_effective_translation_config(app_config, effective)

    assert effective is None
    assert applied == app_config.to_dict()
    assert applied is not app_config.to_dict()
    assert not [key for key in applied if key.startswith("translation_") and key not in app_config.to_dict()]


def test_a_mode_on_a_non_translate_operation_is_ignored_with_a_warning(log_calls):
    app_config = config.load_app_config()

    effective = _resolve(app_config, operation="edit", mode="quality", origin="run_profile:demo")

    assert effective is None
    warnings = [ctx for _, event, ctx in log_calls if event == "translation_mode_ignored_for_operation"]
    assert len(warnings) == 1 and warnings[0]["origin"] == "run_profile:demo"


def test_unknown_requested_mode_is_an_error():
    with pytest.raises(RuntimeError, match="turbo"):
        _resolve(config.load_app_config(), mode="turbo")


def test_apply_writes_the_effective_fields_the_pipeline_and_the_report_read(log_calls):
    app_config = config.load_app_config()
    effective = _resolve(app_config, mode="standard")
    assert effective is not None

    applied = apply_effective_translation_config(app_config, effective)

    assert applied["model"] == effective.first_pass.model
    assert applied["editorial_intensity_default"] == effective.first_pass.editorial_intensity
    assert applied["translation_mode"] == "standard"
    assert applied["translation_first_pass_model"] == effective.first_pass.model
    assert applied["translation_first_pass_reasoning_effort"] is None
    assert effective.polish_pass is not None
    assert applied["translation_polish_model"] == effective.polish_pass.model
    assert applied["translation_polish_reasoning_effort"] is None


def test_apply_states_an_absent_second_pass_explicitly(log_calls):
    app_config = config.load_app_config()
    effective = _resolve(app_config, mode="quality")
    assert effective is not None

    applied = apply_effective_translation_config(app_config, effective)

    assert "translation_polish_model" in applied and applied["translation_polish_model"] is None
    assert applied["translation_first_pass_reasoning_effort"] == "low"


def test_ui_and_runner_paths_give_identical_results(log_calls):
    """The runner's resolution goes through the same function as the UI's."""
    import docxaicorrector.validation.profiles as profiles

    app_config = config.load_app_config()
    profile = profiles.RunProfile(
        id="demo", processing_operation="translate", translation_mode="quality", model=None, editorial_intensity=None
    )

    resolution = profiles.resolve_runtime_resolution(app_config, profile)
    direct = _resolve(app_config, mode="quality", origin="run_profile:demo")
    assert direct is not None

    assert resolution.effective.model == direct.first_pass.model
    assert resolution.effective.editorial_intensity == direct.first_pass.editorial_intensity
    assert resolution.effective.translation_mode == "quality"
    assert resolution.effective.translation_first_pass_model == direct.first_pass.model
    assert resolution.effective.translation_first_pass_reasoning_effort == "low"
    assert resolution.effective.translation_polish_model is None
    applied_by_runner = profiles.apply_runtime_resolution_to_app_config(app_config, resolution)
    applied_directly = apply_effective_translation_config(app_config, direct)
    for key in (
        "model",
        "editorial_intensity_default",
        "translation_mode",
        "translation_first_pass_model",
        "translation_first_pass_reasoning_effort",
        "translation_polish_model",
        "translation_polish_reasoning_effort",
    ):
        assert applied_by_runner[key] == applied_directly[key], key


def test_effective_config_is_frozen():
    effective = EffectiveTranslationConfig(
        mode="single",
        first_pass=TranslationPassSpec(model="m"),
        polish_pass=None,
        overridden_settings=(),
        origin="ui",
    )
    with pytest.raises(Exception):
        effective.mode = "standard"  # type: ignore[misc]


# ---------------------------------------------------------------------------------------
# T1.5: run-profile field and the runtime resolution
# ---------------------------------------------------------------------------------------


def test_run_profile_translation_mode_reaches_runtime_overrides_and_resolved_config(log_calls):
    import docxaicorrector.validation.profiles as profiles

    app_config = config.load_app_config()
    profile = profiles.RunProfile(id="demo", processing_operation="translate", translation_mode="standard")

    resolution = profiles.resolve_runtime_resolution(app_config, profile)

    spec = app_config.translation_modes["standard"]
    assert resolution.effective.model == spec.first_pass.model
    assert resolution.effective.translation_mode == "standard"
    assert spec.polish_pass is not None
    assert resolution.effective.translation_polish_model == spec.polish_pass.model
    assert resolution.overrides["translation_mode"] == "standard"
    assert resolution.overrides["translation_first_pass_model"] == spec.first_pass.model
    assert resolution.effective.to_dict()["translation_mode"] == "standard"


def test_run_profile_single_resolves_to_the_previous_single_pass(log_calls):
    import docxaicorrector.validation.profiles as profiles

    app_config = config.load_app_config()
    profile = profiles.RunProfile(
        id="demo", processing_operation="translate", translation_mode="single", model="openrouter:vendor/pinned"
    )

    resolution = profiles.resolve_runtime_resolution(app_config, profile)

    assert resolution.effective.model == "openrouter:vendor/pinned"
    assert resolution.effective.translation_mode == "single"
    assert resolution.effective.translation_first_pass_reasoning_effort is None
    assert resolution.effective.translation_polish_model is None


def test_run_profile_without_the_field_resolves_to_the_default_mode(log_calls):
    import docxaicorrector.validation.profiles as profiles

    app_config = config.load_app_config()
    profile = profiles.RunProfile(id="demo", processing_operation="translate")

    resolution = profiles.resolve_runtime_resolution(app_config, profile)

    assert resolution.effective.translation_mode == app_config.translation_mode_default


def test_run_profile_for_edit_carries_no_translation_fields(log_calls):
    import docxaicorrector.validation.profiles as profiles

    app_config = config.load_app_config()
    profile = profiles.RunProfile(id="demo", processing_operation="edit")

    resolution = profiles.resolve_runtime_resolution(app_config, profile)

    assert resolution.effective.translation_mode is None
    assert not [key for key in resolution.overrides if key.startswith("translation_")]


def test_registry_rejects_an_unknown_translation_mode():
    import docxaicorrector.validation.profiles as profiles

    with pytest.raises(RuntimeError, match="translation_mode"):
        profiles._build_run_profile({"id": "x", "processing_operation": "translate", "translation_mode": "turbo"})


def test_registry_accepts_the_three_translation_modes():
    import docxaicorrector.validation.profiles as profiles

    for mode in ("standard", "quality", "single"):
        built = profiles._build_run_profile({"id": "x", "processing_operation": "translate", "translation_mode": mode})
        assert built.translation_mode == mode


def _translate_quality_defaults(monkeypatch):
    import dataclasses

    app_config = config.load_app_config()
    return dataclasses.replace(
        app_config,
        processing_operation_default="translate",
        translation_mode_default="quality",
    )


@pytest.mark.parametrize("operation", ["edit", "audiobook"])
def test_translate_defaults_do_not_leak_into_non_translate_run_profile(log_calls, monkeypatch, operation):
    """Codex 069 P1: mode model/intensity must not be inherited by edit/audiobook profiles."""
    import docxaicorrector.validation.profiles as profiles

    app_config = _translate_quality_defaults(monkeypatch)
    general = profiles.resolve_runtime_resolution(
        dataclasses_replace(app_config, processing_operation_default="edit"),
        profiles.RunProfile(id="demo", processing_operation=operation),
    ).effective
    resolution = profiles.resolve_runtime_resolution(app_config, profiles.RunProfile(id="demo", processing_operation=operation))

    assert resolution.effective.model == general.model
    assert resolution.effective.model != _SHIPPED_QUALITY_MODEL
    assert resolution.effective.editorial_intensity == "literary"
    assert resolution.effective.translation_mode is None


def test_translate_run_profile_still_gets_the_mode_under_translate_defaults(log_calls, monkeypatch):
    import docxaicorrector.validation.profiles as profiles

    app_config = _translate_quality_defaults(monkeypatch)
    resolution = profiles.resolve_runtime_resolution(app_config, profiles.RunProfile(id="demo", processing_operation="translate"))

    assert resolution.effective.translation_mode == "quality"
    assert resolution.effective.model == _SHIPPED_QUALITY_MODEL


def dataclasses_replace(obj, **kwargs):
    import dataclasses

    return dataclasses.replace(obj, **kwargs)
