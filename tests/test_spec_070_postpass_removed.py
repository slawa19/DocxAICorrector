"""Spec 070 FR-002 (WP-A): the optional second narration pass over translate/edit output is gone.

What is pinned here, each against the thing it removes:

* the old ``config.toml`` key is reported as ignored, not read (and not honoured via env either);
* the sidebar has no extra-narration checkbox and returns twelve values;
* the corpus registry and ``RunProfile`` carry no ``audiobook_postprocess_enabled``;
* the second-pass symbols are no longer importable;
* ``translate`` / ``edit`` produce no narration text (the standalone ``audiobook`` still does);
* the narration review keeps the identifier rules and no longer carries the four dead ones.
"""

from __future__ import annotations

import dataclasses
import importlib
import tomllib
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import docxaicorrector.core.config as config
from docxaicorrector.pipeline import late_phases, narration_postprocess
from docxaicorrector.ui import _ui as ui
from docxaicorrector.validation import profiles

_REMOVED_KEY = "audiobook_postprocess_default"
_REMOVED_ENV = "DOCX_AI_AUDIOBOOK_POSTPROCESS_DEFAULT"


# --------------------------------------------------------------------- config key (T-A2)


@pytest.fixture(autouse=True)
def _isolate_config_cache():
    config.reset_app_config_cache()
    config._EMITTED_MODEL_REGISTRY_LOG_KEYS.clear()
    yield
    config.reset_app_config_cache()
    config._EMITTED_MODEL_REGISTRY_LOG_KEYS.clear()


def _load_with_user_config(monkeypatch, tmp_path, toml_text: str):
    path = tmp_path / "config.toml"
    path.write_text(toml_text, encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    events: list[tuple[int, str, dict[str, object]]] = []
    monkeypatch.setattr(config, "log_event", lambda level, event_id, message, **context: events.append((level, event_id, context)))
    return config.load_app_config(), events


def test_the_old_config_key_is_reported_as_ignored_and_has_no_effect(monkeypatch, tmp_path):
    app_config, events = _load_with_user_config(monkeypatch, tmp_path, f"{_REMOVED_KEY} = true\n")

    ignored = [(level, ctx["ignored_keys"]) for level, event_id, ctx in events if event_id == "config_key_ignored"]
    assert ignored == [(30, [_REMOVED_KEY])]  # logging.WARNING == 30
    assert _REMOVED_KEY not in app_config


def test_a_config_without_the_old_key_reports_nothing_ignored(monkeypatch, tmp_path):
    # Anti-vacuum: the warning above comes from the key, not from the loader complaining about anything.
    _app_config, events = _load_with_user_config(monkeypatch, tmp_path, 'processing_operation_default = "edit"\n')

    assert [event_id for _level, event_id, _ctx in events if event_id == "config_key_ignored"] == []


def test_the_old_env_variable_is_not_read(monkeypatch, tmp_path):
    monkeypatch.setenv(_REMOVED_ENV, "true")

    app_config, _events = _load_with_user_config(monkeypatch, tmp_path, "")

    assert _REMOVED_KEY not in app_config
    assert "audiobook_postprocess_enabled" not in app_config


# ------------------------------------------------------------------------- sidebar (T-A3)

_SIDEBAR_SCRIPT = """
import streamlit as st
from docxaicorrector.core.config import load_app_config
from docxaicorrector.ui._ui import render_sidebar

st.session_state["_sidebar_result"] = render_sidebar(load_app_config())
"""


@pytest.mark.parametrize("operation", ["edit", "translate", "audiobook"])
def test_the_sidebar_has_no_extra_narration_checkbox_and_returns_twelve_values(operation):
    at = AppTest.from_string(_SIDEBAR_SCRIPT, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    at.sidebar.selectbox(key="sidebar_text_operation").select(ui.TEXT_OPERATION_LABELS[operation]).run()
    assert not at.exception, at.exception

    checkbox_keys = [str(widget.key) for widget in at.sidebar.checkbox]
    assert "sidebar_audiobook_postprocess" not in checkbox_keys
    assert len(at.session_state["_sidebar_result"]) == 12
    assert at.session_state["_sidebar_result"][5] == operation


# ----------------------------------------------------------------- registry / profile (T-A4)


def test_no_registry_profile_runs_the_removed_pass_and_no_profile_carries_its_field():
    with open(profiles.DEFAULT_REGISTRY_PATH, "rb") as handle:
        raw = tomllib.load(handle)

    ids = [str(item["id"]) for item in raw["run_profiles"]]
    assert "ui-parity-translate-audiobook-postprocess" not in ids
    assert ids, "the registry must still carry run profiles"
    assert not [item["id"] for item in raw["run_profiles"] if "audiobook_postprocess_enabled" in item]


def test_the_run_profile_and_the_resolved_config_have_no_such_field():
    for cls in (profiles.RunProfile, profiles.ResolvedRuntimeConfig):
        assert "audiobook_postprocess_enabled" not in {field.name for field in dataclasses.fields(cls)}


def test_a_profile_payload_that_still_names_the_field_does_not_resurrect_it():
    # The loader never errors on a stale key, so the removed field must simply not come back.
    run_profile = profiles._build_run_profile({"id": "x", "tier": "full", "audiobook_postprocess_enabled": True})

    assert not hasattr(run_profile, "audiobook_postprocess_enabled")


# --------------------------------------------------------------------- symbols (T-A5)


@pytest.mark.parametrize("module_name", ["docxaicorrector.pipeline.narration_postprocess", "docxaicorrector.pipeline.late_phases"])
@pytest.mark.parametrize(
    "symbol",
    [
        "_run_audiobook_postprocess",
        "_project_final_cleanup_narration_chunks",
        "_should_run_audiobook_postprocess",
        "_resolve_audiobook_postprocess_model",
        "_resolve_audiobook_postprocess_chunk_size",
        "_build_narration_postprocess_groups",
        "_record_postprocess_paragraph_shortfall",
        "_ELEVENLABS_TAG_PATTERN",
        "_NARRATION_ANY_TAG_PATTERN",
    ],
)
def test_the_second_pass_symbols_are_gone(module_name, symbol):
    module = importlib.import_module(module_name)

    with pytest.raises(AttributeError):
        getattr(module, symbol)
    with pytest.raises(ImportError):
        exec(f"from {module_name} import {symbol}", {})


def test_the_symbols_the_standalone_operation_needs_are_still_there():
    # Anti-vacuum for the block above: the module still imports, and these are the survivors.
    assert callable(narration_postprocess._collect_narration_chunks)
    assert callable(narration_postprocess._assemble_narration_recording_joins)
    assert callable(late_phases._build_narration_text)


# ------------------------------------------------------------- no narration off audiobook (T-A1)


def _narration_context(operation: str):
    return SimpleNamespace(processing_operation=operation, runtime=None, app_config={})


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_translate_and_edit_produce_no_narration_text(operation):
    state = SimpleNamespace(narration_chunks=["Абзац, который уже накоплен."], narration_joined_sentence_continuation_count=0)

    text = narration_postprocess._build_narration_text(
        context=_narration_context(operation), dependencies=None, emitters=None, state=state
    )

    assert text is None
    assert state.narration_joined_sentence_continuation_count == 0


def test_a_stale_session_flag_cannot_bring_the_pass_back():
    # The flag used to live in ``app_config``; a value left there by an old session must be inert.
    context = SimpleNamespace(processing_operation="edit", runtime=None, app_config={"audiobook_postprocess_enabled": True})
    state = SimpleNamespace(narration_chunks=["Абзац."], narration_joined_sentence_continuation_count=0)

    assert narration_postprocess._build_narration_text(context=context, dependencies=None, emitters=None, state=state) is None


def test_the_standalone_audiobook_still_produces_its_narration_text():
    state = SimpleNamespace(narration_chunks=["Первый абзац.", "Второй абзац."], narration_joined_sentence_continuation_count=0)

    text = narration_postprocess._build_narration_text(
        context=_narration_context("audiobook"), dependencies=None, emitters=None, state=state
    )

    assert text == "Первый абзац.\n\nВторой абзац."


# ----------------------------------------------------------------- review rules (T-A6)


def _rules(text: str) -> dict[str, int]:
    return {
        str(finding["rule"]): int(finding["match_count"])  # type: ignore[call-overload]
        for finding in narration_postprocess._collect_narration_artifact_review_findings(text)
    }


@pytest.mark.parametrize(
    "text",
    [
        "Картинка [[DOCX_IMAGE_img_001]] стоит в тексте.",
        "Смотрите https://example.org/page и www.example.org.",
        "# Заголовок\n\nТекст.",
        "Фраза [serious] с тегом в квадратных скобках и [любая метка].",
    ],
)
def test_the_four_dead_rules_no_longer_report(text):
    assert _rules(text) == {}


def test_the_identifier_rules_still_report_and_count_occurrences():
    text = "doi:10.5194/sapiens-2-1 и doi:10.1000/xyz123, ISBN 978-5-9614-1234-5, arXiv:2103.12345, (Смит, 2019) и (Джонс, 2020)."

    assert _rules(text) == {"doi": 2, "isbn_identifier": 1, "arxiv_identifier": 1, "inline_citation": 2}
