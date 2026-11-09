"""Spec 070 FR-001 (WP-B): the audiobook mode has no language pair.

The input of an audiobook run is an already translated document; a pair (``auto -> ru``,
``ru -> ru``) would be a fabricated fact that steers the language rules of other operations.
Every statement below is paired with the behaviour of ``translate``/``edit`` it must not touch.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import docxaicorrector.core.config as config
import docxaicorrector.pipeline.footnote_markers as footnote_markers
import docxaicorrector.ui._app as app
import docxaicorrector.ui._ui as ui
import docxaicorrector.validation.profiles as vp
from docxaicorrector.core.audiobook_mode import language_pair_for_operation
from docxaicorrector.core.models import LANGUAGE_CHANGING_OPERATIONS
from docxaicorrector.pipeline import block_execution
from docxaicorrector.pipeline.setup import build_processing_context
from docxaicorrector.processing.preparation import build_prepared_source_key
from docxaicorrector.processing.processing_runtime import build_preparation_request_marker
from test_app_preparation import _PAID_SOURCE_TOKEN, _run_main_for_processing_start_guard

_PAIRS = [("en", "ru"), ("auto", "ru"), ("ru", "ru"), ("de", "fr")]


# ------------------------------------------------------------- the one helper


@pytest.mark.parametrize("source,target", _PAIRS)
def test_audiobook_has_no_pair_whatever_the_caller_holds(source, target):
    assert language_pair_for_operation("audiobook", source, target) == (None, None)
    assert language_pair_for_operation(" Audiobook ", source, target) == (None, None)


@pytest.mark.parametrize("operation", ["translate", "edit", "", "something_else"])
@pytest.mark.parametrize("source,target", _PAIRS)
def test_every_other_operation_keeps_the_pair_untouched(operation, source, target):
    assert language_pair_for_operation(operation, source, target) == (source, target)


# ------------------------------------------- preparation marker and cache key do not depend on the pair


def test_the_audiobook_preparation_marker_is_the_same_for_any_pair_in_the_session():
    file_stub = SimpleNamespace(name="a.docx", file_token="tok", size=3, getvalue=lambda: b"abc")

    markers = {
        build_preparation_request_marker(file_stub, chunk_size=6000, processing_operation="audiobook", source_language=s, target_language=t)
        for s, t in _PAIRS
    }

    assert len(markers) == 1
    assert ":sl=" not in next(iter(markers))


def test_the_translate_marker_still_depends_on_the_pair():
    # Counter-proof: the suffix is not simply gone for every operation.
    file_stub = SimpleNamespace(name="a.docx", file_token="tok", size=3, getvalue=lambda: b"abc")

    markers = {
        build_preparation_request_marker(file_stub, chunk_size=6000, processing_operation="translate", source_language=s, target_language=t)
        for s, t in _PAIRS
    }

    assert len(markers) == len(_PAIRS)


def test_the_audiobook_preparation_cache_key_does_not_depend_on_the_pair_and_translate_does():
    audiobook_keys = {
        build_prepared_source_key("tok", 6000, processing_operation="audiobook", source_language=s, target_language=t)
        for s, t in _PAIRS
    }
    translate_keys = {
        build_prepared_source_key("tok", 6000, processing_operation="translate", source_language=s, target_language=t)
        for s, t in _PAIRS
    }

    assert len(audiobook_keys) == 1
    assert ":sl=" not in next(iter(audiobook_keys))
    assert len(translate_keys) == len(_PAIRS)


# ------------------------------------------------------- the processing context carries absence


def _context_kwargs(operation: str, source, target) -> dict[str, object]:
    return dict(
        uploaded_file=object(),
        jobs=[],
        image_assets=[],
        source_paragraphs=[],
        image_mode="safe",
        app_config={},
        model="m",
        max_retries=1,
        processing_operation=operation,
        source_language=source,
        target_language=target,
        on_progress=lambda **kw: None,
        runtime=object(),
        dependencies=SimpleNamespace(resolve_uploaded_filename=lambda f: "a.docx", log_event=lambda *a, **k: None),
        context_factory_fn=lambda **kwargs: SimpleNamespace(**kwargs),
    )


@pytest.mark.parametrize("source,target", _PAIRS)
def test_the_audiobook_processing_context_carries_none_not_a_pair(source, target):
    context = build_processing_context(**_context_kwargs("audiobook", source, target))  # type: ignore[arg-type]

    assert (context.source_language, context.target_language) == (None, None)


def test_the_translate_processing_context_keeps_its_pair():
    context = build_processing_context(**_context_kwargs("translate", "en", "ru"))  # type: ignore[arg-type]

    assert (context.source_language, context.target_language) == ("en", "ru")


# ------------------------------------------------------ the language rules no longer see audiobook


def test_audiobook_left_the_language_changing_set_and_translate_stayed():
    assert LANGUAGE_CHANGING_OPERATIONS == frozenset({"translate"})


@pytest.mark.parametrize("source,target", [("en", "ru"), ("auto", "ru"), ("ru", "en")])
def test_the_completeness_invariant_does_not_treat_audiobook_as_a_language_change(source, target):
    assert block_execution.job_changes_language(processing_operation="audiobook", source_language=source, target_language=target) is False
    # Counter-proof: the same codes on translate still mean a language change.
    assert block_execution.job_changes_language(processing_operation="translate", source_language=source, target_language=target) is True



def test_auto_source_language_is_accepted_only_for_translate():
    codes = {"ru", "en"}
    config._validate_text_transform_context(operation="translate", source_language="auto", target_language="ru", supported_language_codes=codes)
    # Spec 070: the audiobook mode reads no pair, so a stale `auto` default is simply not validated.
    config._validate_text_transform_context(operation="audiobook", source_language="auto", target_language="ru", supported_language_codes=codes)
    with pytest.raises(RuntimeError):
        config._validate_text_transform_context(operation="edit", source_language="auto", target_language="ru", supported_language_codes=codes)


def test_footnote_markers_are_skipped_for_audiobook_by_operation_name_not_by_the_set(monkeypatch):
    # Independent of LANGUAGE_CHANGING_OPERATIONS: ``audiobook`` is not in it, yet is still skipped.
    def boom(*args, **kwargs):
        raise AssertionError("restore_block_footnote_markers must not run for audiobook")

    monkeypatch.setattr(footnote_markers, "restore_block_footnote_markers", boom)
    payload = SimpleNamespace(paragraph_ids=["p1"])

    unchanged = footnote_markers.preserve_footnote_markers_for_block(
        processed_chunk="text", payload=payload, processing_operation="audiobook", block_index=1, log_event=None
    )

    assert unchanged == "text"
    # Counter-proof: for translate the restore step IS reached.
    with pytest.raises(AssertionError):
        footnote_markers.preserve_footnote_markers_for_block(
            processed_chunk="text", payload=payload, processing_operation="translate", block_index=1, log_event=None
        )


# ------------------------------------------------------------------------- the sidebar (AppTest)

_SIDEBAR_SCRIPT = """
import streamlit as st
from docxaicorrector.core.config import load_app_config
from docxaicorrector.ui._ui import render_sidebar

st.session_state["_sidebar_result"] = render_sidebar(load_app_config())
"""


def _switch(at: AppTest, operation: str) -> None:
    at.sidebar.selectbox(key="sidebar_text_operation").select(ui.TEXT_OPERATION_LABELS[operation]).run()
    assert not at.exception, at.exception


def _keys(at: AppTest) -> list[str]:
    return [str(widget.key) for widget in at.sidebar.selectbox]


def test_values_left_in_the_session_by_translate_do_not_reach_audiobook():
    at = AppTest.from_string(_SIDEBAR_SCRIPT, default_timeout=30)
    at.run()
    _switch(at, "translate")
    assert {"sidebar_target_language", "sidebar_source_language"} <= set(_keys(at))
    # The user picked a pair for translate.
    at.sidebar.selectbox(key="sidebar_target_language").select("English").run()
    translate_result = at.session_state["_sidebar_result"]
    assert translate_result[7] == "en"  # counter-proof: translate really reads the widgets

    _switch(at, "audiobook")

    keys = _keys(at)
    assert "sidebar_target_language" not in keys
    assert "sidebar_source_language" not in keys
    result = at.session_state["_sidebar_result"]
    assert result[5] == "audiobook"
    assert (result[6], result[7]) == (None, None)


# ------------------------------------------------- main(): no estimation, no recommendations, no pair


def _audiobook_main(monkeypatch, *, operation: str):
    calls: list[str] = []
    real_assess = app._assess_text_transform

    def spy(**kwargs):
        calls.append("assess")
        return real_assess(**kwargs)

    monkeypatch.setattr(app, "_assess_text_transform", spy)
    if operation == "audiobook":
        record = _run_main_for_processing_start_guard(
            monkeypatch,
            current_result=None,
            sidebar_result=("gpt-5.4", 6000, 3, "safe", False, "audiobook", "auto", "ru"),
            session_overrides={"preparation_input_marker": f"{_PAID_SOURCE_TOKEN}:6000:op=audiobook"},
        )
    else:
        record = _run_main_for_processing_start_guard(
            monkeypatch,
            current_result=None,
            sidebar_result=("gpt-5.4", 6000, 3, "safe", False, "edit", "en", "de"),
            session_overrides={"preparation_input_marker": f"{_PAID_SOURCE_TOKEN}:6000:sl=en:tl=de"},
        )
    return record, calls


def test_main_runs_no_language_estimation_for_audiobook_and_starts_without_a_pair(monkeypatch):
    record, calls = _audiobook_main(monkeypatch, operation="audiobook")

    assert calls == []
    assert len(record["processing_starts"]) == 1
    start = record["processing_starts"][0]
    assert (start["source_language"], start["target_language"]) == (None, None)
    assert start["app_config"]["source_language"] is None
    assert start["app_config"]["target_language"] is None


def test_main_still_estimates_the_language_for_edit(monkeypatch):
    # Counter-proof for the test above: the same harness on a language-bearing operation reaches
    # the estimation (translate would first rerun for its cost estimate, so edit is the clean case).
    record, calls = _audiobook_main(monkeypatch, operation="edit")

    assert calls == ["assess"]
    start = record["processing_starts"][0]
    assert (start["source_language"], start["target_language"]) == ("en", "de")


# ------------------------------------------------------------------- profile and runner report


def test_the_standalone_audiobook_profile_declares_no_pair_and_resolves_to_none():
    profile = next(p for p in vp.load_validation_registry().run_profiles if p.id == "ui-parity-standalone-audiobook")
    assert (profile.source_language, profile.target_language) == (None, None)

    resolution = vp.resolve_runtime_resolution(config.load_app_config(), profile)
    effective = resolution.effective.to_dict()

    assert effective["source_language"] is None
    assert effective["target_language"] is None
    # Absence is reported as null (effective None differs from the UI default), never as a pair.
    assert resolution.overrides.get("source_language") is None and resolution.overrides.get("target_language") is None


def test_a_profile_that_still_names_a_pair_for_audiobook_resolves_to_no_pair():
    import dataclasses

    profile = next(p for p in vp.load_validation_registry().run_profiles if p.id == "ui-parity-standalone-audiobook")
    stale = dataclasses.replace(profile, source_language="en", target_language="ru")

    resolution = vp.resolve_runtime_resolution(config.load_app_config(), stale)

    assert (resolution.effective.source_language, resolution.effective.target_language) == (None, None)
    assert resolution.overrides.get("source_language") is None


def test_a_translate_profile_keeps_its_pair():
    profile = next(p for p in vp.load_validation_registry().run_profiles if p.id == "ui-parity-translate-baseline")

    effective = vp.resolve_runtime_resolution(config.load_app_config(), profile).effective

    assert (effective.source_language, effective.target_language) == ("auto", "ru")


def test_the_runner_report_language_for_audiobook_is_the_default_ui_language_not_a_pair():
    from importlib import util
    from pathlib import Path

    from docxaicorrector.ui.i18n import DEFAULT_LANGUAGE

    runner_path = Path(__file__).resolve().parent / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py"
    spec = util.spec_from_file_location("run_lietaer_validation_wp_b", runner_path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def report(operation: str, target: str | None) -> dict[str, object]:
        return {"runtime_config": {"effective": {"processing_operation": operation, "target_language": target}, "ui_defaults": {"target_language": "en"}}}

    assert module._resolve_reader_mvp_status_language(report("audiobook", None)) == DEFAULT_LANGUAGE
    # A pair left in the report does not change it for audiobook...
    assert module._resolve_reader_mvp_status_language(report("audiobook", "de")) == DEFAULT_LANGUAGE
    # ...and translate still reports in its target language.
    assert module._resolve_reader_mvp_status_language(report("translate", "de")) == "de"
