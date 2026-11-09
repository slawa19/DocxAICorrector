"""Spec 069 WP-8: the translation-mode UI, the frozen price snapshot and the estimate-vs-actual event.

Three layers, each proven against the behaviour it replaces:

* the sidebar (headless ``AppTest`` on ``render_sidebar``) -- a mode radio with the price for
  "translate", the old model/intensity widgets for "edit", nothing price-related before a document
  is prepared;
* ``ui/_app.py`` -- the estimate is keyed and recomputed only when a component of the key changes,
  ``main`` resolves the mode through the same resolver as the runner, Start freezes the snapshot;
* the result and the pipeline -- the actual is shown next to ITS OWN snapshot, and
  ``cost_estimate_vs_actual`` carries the documented error formula and ``run_complete``.

No test reaches the network: the price list is a fixture.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
from typing import cast
from collections.abc import Iterator

import pytest
from streamlit.testing.v1 import AppTest

import docxaicorrector.pipeline._pipeline as pipeline
import docxaicorrector.ui._app as app
import docxaicorrector.ui._ui as ui
from conftest import SessionState
from docxaicorrector.pipeline.cost_estimate import load_coefficient_table
from docxaicorrector.pipeline.price_list import PriceList
from docxaicorrector.ui import i18n
from test_app_preparation import (
    _APP_CONFIG_WITH_MODES,
    _PAID_SOURCE_TOKEN,
    _run_main_for_processing_start_guard,
)
from test_cost_estimate import _schema, _validate

FLASH_LITE = "google/gemini-3.1-flash-lite-preview"
HAIKU = "anthropic/claude-haiku-5.5"
GEMINI_37 = "google/gemini-3.7-flash"

PRICES = PriceList(
    fetched_at="2026-11-09T10:00:00+00:00",
    source="network",
    prices={FLASH_LITE: (0.25, 1.50), HAIKU: (0.10, 0.50), GEMINI_37: (0.75, 3.75)},
)

KEY = ui.TRANSLATION_COST_ESTIMATES_KEY


@pytest.fixture(autouse=True)
def _clear_catalog_cache() -> Iterator[None]:
    i18n.clear_catalog_cache()
    yield
    i18n.clear_catalog_cache()


# ---------------------------------------------------------------- the sidebar (AppTest)

_SIDEBAR_SCRIPT = """
import streamlit as st
from docxaicorrector.core.config import load_app_config
from docxaicorrector.ui._ui import render_sidebar

st.session_state["_sidebar_result"] = render_sidebar(load_app_config())
"""


def _sidebar(operation: str, *, estimates: dict | None = None) -> AppTest:
    at = AppTest.from_string(_SIDEBAR_SCRIPT, default_timeout=30)
    if estimates is not None:
        at.session_state[KEY] = estimates
    at.run()
    assert not at.exception, at.exception
    at.sidebar.selectbox(key="sidebar_text_operation").select(ui.TEXT_OPERATION_LABELS[operation]).run()
    assert not at.exception, at.exception
    return at


def _selectbox_keys(at: AppTest) -> list[str]:
    return [str(widget.key) for widget in at.sidebar.selectbox]


def _snapshot(mode: str, upper: float | None, lower: float | None, *, extrapolated: bool = False) -> dict:
    return {
        "mode": mode,
        "total_upper_usd": upper,
        "total_lower_usd": lower,
        "extrapolated": extrapolated,
    }


def test_edit_keeps_the_model_selector_and_the_intensity_widget_and_has_no_mode_radio() -> None:
    # T8.1 characterization: what "edit" shows must not change. It holds on the unmodified code.
    at = _sidebar("edit")

    keys = _selectbox_keys(at)
    assert "sidebar_model" in keys
    assert "sidebar_editorial_intensity" in keys
    assert len(at.sidebar.radio) == 0
    assert at.session_state["_sidebar_result"][11] == ""


def test_audiobook_has_no_mode_radio_and_keeps_the_model_selector() -> None:
    at = _sidebar("audiobook")

    assert "sidebar_model_audiobook" in _selectbox_keys(at)
    assert len(at.sidebar.radio) == 0
    assert at.session_state["_sidebar_result"][11] == ""


def test_translate_shows_a_two_way_mode_radio_standard_first_and_no_model_or_intensity_widget() -> None:
    at = _sidebar("translate")

    radio = at.sidebar.radio(key="sidebar_translation_mode")
    assert [option for option in radio.options] == [
        i18n.t("sidebar.translation_mode_standard"),
        i18n.t("sidebar.translation_mode_quality"),
    ]
    assert radio.value == "standard"
    keys = _selectbox_keys(at)
    assert "sidebar_model" not in keys
    assert "sidebar_editorial_intensity" not in keys
    assert at.session_state["_sidebar_result"][11] == "standard"


def test_translate_mode_radio_returns_the_chosen_mode() -> None:
    at = _sidebar("translate")

    at.sidebar.radio(key="sidebar_translation_mode").set_value("quality").run()

    assert at.session_state["_sidebar_result"][11] == "quality"


def test_before_a_document_is_prepared_the_radio_carries_no_price() -> None:
    at = _sidebar("translate")

    radio = at.sidebar.radio(key="sidebar_translation_mode")
    assert not any("$" in option for option in radio.options)
    assert i18n.t("sidebar.translation_mode_price_pending") in [caption.value for caption in at.sidebar.caption]


def test_after_preparation_the_radio_shows_the_range_and_the_without_images_caption() -> None:
    estimates = {
        "key": ["tok", "key", "en->ru", "069-v1", PRICES.fetched_at],
        "snapshots": {
            "standard": _snapshot("standard", 1.1, 0.82),
            "quality": _snapshot("quality", 1.88, 1.88),
        },
    }
    at = _sidebar("translate", estimates=estimates)

    options = list(at.sidebar.radio(key="sidebar_translation_mode").options)
    assert options[0] == "Стандарт — ≈ 0,82–1,10 $"
    assert options[1] == "Качество — ≈ 1,88 $"
    captions = [caption.value for caption in at.sidebar.caption]
    assert i18n.t("sidebar.translation_mode_price_caption") in captions
    assert i18n.t("sidebar.translation_mode_price_pending") not in captions
    assert i18n.t("sidebar.translation_mode_price_approximate") not in captions


def test_an_unknown_price_is_said_so_not_shown_as_zero() -> None:
    estimates = {
        "key": ["tok", "key", "en->ru", "069-v1", None],
        "snapshots": {"standard": _snapshot("standard", None, None), "quality": _snapshot("quality", None, None)},
    }
    at = _sidebar("translate", estimates=estimates)

    options = list(at.sidebar.radio(key="sidebar_translation_mode").options)
    assert options == [
        "Стандарт — цена неизвестна",
        "Качество — цена неизвестна",
    ]


def test_an_extrapolated_estimate_is_labelled_approximate() -> None:
    estimates = {
        "key": ["tok", "key", "de->ru", "069-v1", PRICES.fetched_at],
        "snapshots": {
            "standard": _snapshot("standard", 1.0, 0.8, extrapolated=True),
            "quality": _snapshot("quality", 1.9, 1.9),
        },
    }
    at = _sidebar("translate", estimates=estimates)

    assert i18n.t("sidebar.translation_mode_price_approximate") in [caption.value for caption in at.sidebar.caption]


def test_the_availability_warning_checks_both_models_of_the_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def fake_availability(model: str, *, app_config: object) -> object:
        asked.append(model)
        return type("Availability", (), {"error_message": f"нет ключа для {model}"})()

    monkeypatch.setattr(ui, "describe_provider_availability", fake_availability)

    at = _sidebar("translate")

    assert "openrouter:google/gemini-3.1-flash-lite-preview" in asked
    assert "openrouter:anthropic/claude-haiku-5.5" in asked
    warnings = [warning.value for warning in at.sidebar.warning]
    assert any("claude-haiku-5.5" in text for text in warnings)
    assert any("gemini-3.1-flash-lite-preview" in text for text in warnings)


def test_the_availability_warning_for_edit_checks_the_selected_model_only(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def fake_availability(model: str, *, app_config: object) -> object:
        asked.append(model)
        return type("Availability", (), {"error_message": ""})()

    monkeypatch.setattr(ui, "describe_provider_availability", fake_availability)

    _sidebar("edit")

    assert len(set(asked)) == 1
    assert "claude-haiku-5.5" not in asked[-1]


# ---------------------------------------------------------------- the estimate in the session


def _prepared_context(**overrides: object) -> object:
    from test_app_preparation import _build_prepared_run_context

    return _build_prepared_run_context(
        uploaded_file_token=str(overrides.pop("uploaded_file_token", "tok")),
        prepared_source_key=str(overrides.pop("prepared_source_key", "tok:6000")),
        **overrides,
    )


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> SessionState:
    state = SessionState()
    monkeypatch.setattr(app.st, "session_state", state)
    monkeypatch.setattr(ui.st, "session_state", state)
    monkeypatch.setattr(app, "get_price_list", lambda: PRICES)
    return state


def _refresh(**overrides: object) -> bool:
    arguments: dict[str, object] = dict(
        app_config=dict(_APP_CONFIG_WITH_MODES),
        prepared_run_context=_prepared_context(),
        uploaded_file_token="tok",
        source_language="en",
        target_language="ru",
        source_text="x" * 1000,
    )
    arguments.update(overrides)
    return app._refresh_translation_cost_estimates(**arguments)  # type: ignore[arg-type]


def test_the_estimate_covers_both_modes_with_known_prices_and_is_valid_by_schema(session: SessionState) -> None:
    assert _refresh() is True

    snapshots = session[KEY]["snapshots"]
    assert set(snapshots) == {"standard", "quality"}
    for mode, snapshot in snapshots.items():
        assert _validate(snapshot, _schema(), _schema()) == [], mode
        assert snapshot["mode"] == mode
        assert snapshot["excludes"] == ["images"]
        assert snapshot["total_upper_usd"] is not None and snapshot["total_upper_usd"] > 0
        assert snapshot["price_unknown_models"] == []
    # standard = glossary + translation on flash-lite, then the haiku polish; quality = gemini 3.7 only.
    assert set(snapshots["standard"]["stages"]) == {"glossary_extraction", "text_generation", "literary_polish"}
    assert set(snapshots["quality"]["stages"]) == {"glossary_extraction", "text_generation"}
    assert snapshots["standard"]["passes"][-1]["model"] == HAIKU
    assert snapshots["quality"]["passes"][0]["reasoning_effort"] == "low"


def test_the_openrouter_prefix_of_a_config_model_does_not_make_the_price_unknown(session: SessionState) -> None:
    # The config names models as ``openrouter:<id>``; the coefficient table is keyed by the bare id.
    # Without the prefix being stripped every mode would report "coefficients missing".
    _refresh()

    for snapshot in session[KEY]["snapshots"].values():
        assert snapshot["price_unknown_models"] == []
        assert all(stage["upper_usd"] is not None for stage in snapshot["stages"].values())


def test_without_a_price_list_the_prices_are_unknown(
    session: SessionState, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "get_price_list", lambda: None)

    _refresh()

    for snapshot in session[KEY]["snapshots"].values():
        assert snapshot["total_upper_usd"] is None
        assert snapshot["price_list_date"] is None
        assert ui.format_cost_range(snapshot) == i18n.t("sidebar.translation_mode_price_unknown")


def test_an_unchanged_key_does_no_work_and_asks_for_no_rerun(
    session: SessionState, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real = app.estimate_text_stages
    monkeypatch.setattr(app, "estimate_text_stages", lambda *a, **k: calls.append("x") or real(*a, **k))

    assert _refresh() is True
    first_calls = len(calls)
    assert first_calls == 2  # one estimate per mode
    assert _refresh() is False
    assert len(calls) == first_calls


@pytest.mark.parametrize(
    "component",
    ["file_token", "prepared_source_key", "language_pair", "coefficients_version", "price_list_date"],
)
def test_a_change_of_any_key_component_resets_the_estimate(
    session: SessionState, monkeypatch: pytest.MonkeyPatch, component: str
) -> None:
    _refresh()
    before = copy.deepcopy(session[KEY])

    overrides: dict[str, object] = {}
    if component == "file_token":
        overrides = dict(uploaded_file_token="other-tok", prepared_run_context=_prepared_context(uploaded_file_token="other-tok"))
    elif component == "prepared_source_key":
        overrides = dict(prepared_run_context=_prepared_context(prepared_source_key="tok:9000"))
    elif component == "language_pair":
        overrides = dict(target_language="de")
    elif component == "coefficients_version":
        table = load_coefficient_table()
        monkeypatch.setattr(app, "load_coefficient_table", lambda: dataclasses.replace(table, version="069-v2"))
    elif component == "price_list_date":
        monkeypatch.setattr(app, "get_price_list", lambda: dataclasses.replace(PRICES, fetched_at="2026-11-10T10:00:00+00:00"))
        # the price list lookup is remembered for a few minutes; a later fetch is what changes the date
        session.pop(app._PRICE_LIST_SESSION_KEY)

    assert _refresh(**overrides) is True
    assert session[KEY]["key"] != before["key"]


def test_the_price_list_is_looked_up_once_per_recheck_window(
    session: SessionState, monkeypatch: pytest.MonkeyPatch
) -> None:
    lookups: list[int] = []
    monkeypatch.setattr(app, "get_price_list", lambda: lookups.append(1) or PRICES)

    _refresh()
    _refresh(target_language="de")
    _refresh(uploaded_file_token="t3", prepared_run_context=_prepared_context(uploaded_file_token="t3"))

    assert len(lookups) == 1


def test_a_snapshot_is_frozen_only_from_an_estimate_of_the_same_document(session: SessionState) -> None:
    _refresh()
    effective = _effective("quality")

    own = app._freeze_cost_estimate_snapshot(effective, "tok")
    other = app._freeze_cost_estimate_snapshot(effective, "another-document")

    assert own is not None and own["mode"] == "quality"
    assert other is None
    own["total_upper_usd"] = -1  # a copy: the session estimate is not rewritten through it
    assert session[KEY]["snapshots"]["quality"]["total_upper_usd"] != -1


def test_single_mode_has_no_snapshot(session: SessionState) -> None:
    _refresh()

    assert app._freeze_cost_estimate_snapshot(_effective("single"), "tok") is None
    assert app._freeze_cost_estimate_snapshot(None, "tok") is None


def _effective(mode: str):
    from docxaicorrector.core.translation_modes import (
        EffectiveTranslationConfig,
        TranslationPassSpec,
        resolve_effective_translation_config,
    )

    if mode == "single":
        # ``single`` is the pre-069 one pass; it needs the shared model default, so it is built directly.
        return EffectiveTranslationConfig(
            mode="single",
            first_pass=TranslationPassSpec(model="gpt-5.4", editorial_intensity="literary"),
            polish_pass=None,
            overridden_settings=(),
            origin="ui",
        )
    return resolve_effective_translation_config(
        dict(_APP_CONFIG_WITH_MODES, editorial_intensity_default="literary"),
        processing_operation="translate",
        requested_mode=mode,
        requested_model=None,
        requested_intensity=None,
        origin="ui",
    )


# ---------------------------------------------------------------- main(): one resolver, Start freezes

_TRANSLATE = ("gpt-5.4", 6000, 3, "safe", False, "translate", "en", "de", "literary", "", "")
_EDIT_MARKER = f"{_PAID_SOURCE_TOKEN}:6000"
_EDIT = ("gpt-5.4", 6000, 3, "safe", False, "edit", "en", "ru", "conservative", "", "", "")


def _start_kwargs(record: dict) -> dict:
    assert len(record["processing_starts"]) == 1, record
    return record["processing_starts"][0]


def _prepare_estimates_then_run(monkeypatch: pytest.MonkeyPatch, sidebar_result: tuple) -> dict:
    """Two passes, as Streamlit does: the first computes the estimate and reruns, the second starts."""
    monkeypatch.setattr(app, "get_price_list", lambda: PRICES)
    first = _run_main_for_processing_start_guard(
        monkeypatch, current_result=None, sidebar_result=sidebar_result
    )
    assert first["rerun"] is True and first["processing_starts"] == []
    assert first["session"][KEY]["snapshots"]
    return _run_main_for_processing_start_guard(
        monkeypatch,
        current_result=None,
        sidebar_result=sidebar_result,
        session_overrides={KEY: first["session"][KEY]},
    )


def test_main_computes_the_estimate_then_reruns_once_before_anything_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "get_price_list", lambda: PRICES)

    record = _run_main_for_processing_start_guard(monkeypatch, current_result=None, sidebar_result=_TRANSLATE + ("standard",))

    assert record["rerun"] is True
    assert record["processing_starts"] == []
    assert set(record["session"][KEY]["snapshots"]) == {"standard", "quality"}


def test_translate_start_runs_the_effective_config_of_the_chosen_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _prepare_estimates_then_run(monkeypatch, _TRANSLATE + ("quality",))

    start = _start_kwargs(record)
    config = start["app_config"]
    # The sidebar sent the placeholder model "gpt-5.4" and intensity "literary": the mode wins (FR-001).
    assert start["model"] == "openrouter:google/gemini-3.7-flash"
    assert config["model"] == "openrouter:google/gemini-3.7-flash"
    assert config["editorial_intensity_default"] == "conservative"
    assert config["translation_mode"] == "quality"
    assert config["translation_first_pass_reasoning_effort"] == "low"
    assert config["translation_polish_model"] is None


def test_standard_start_carries_the_second_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _prepare_estimates_then_run(monkeypatch, _TRANSLATE + ("standard",))

    config = _start_kwargs(record)["app_config"]
    assert config["translation_mode"] == "standard"
    assert config["translation_polish_model"] == "openrouter:anthropic/claude-haiku-5.5"
    assert _start_kwargs(record)["model"] == "openrouter:google/gemini-3.1-flash-lite-preview"


def test_an_empty_mode_resolves_to_the_configured_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # A legacy 12-element sidebar carries no mode: the default of the config applies, not a crash.
    record = _prepare_estimates_then_run(monkeypatch, _TRANSLATE)

    assert _start_kwargs(record)["app_config"]["translation_mode"] == "standard"


def test_start_freezes_the_snapshot_of_the_chosen_mode_for_the_pipeline_and_the_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _prepare_estimates_then_run(monkeypatch, _TRANSLATE + ("quality",))

    snapshot = _start_kwargs(record)["app_config"]["cost_estimate_snapshot"]
    assert snapshot["mode"] == "quality"
    assert snapshot["document"]["source_token"] == _PAID_SOURCE_TOKEN
    assert _validate(snapshot, _schema(), _schema()) == []
    session = record["session"]
    assert session["latest_cost_estimate_snapshot"] == snapshot
    assert session["latest_cost_actual"] is None
    # frozen: a copy, so a later estimate cannot rewrite what this run is judged against
    assert snapshot is not session[KEY]["snapshots"]["quality"]


def test_start_clears_the_previous_runs_actual_and_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "get_price_list", lambda: PRICES)
    first = _run_main_for_processing_start_guard(monkeypatch, current_result=None, sidebar_result=_TRANSLATE + ("standard",))

    record = _run_main_for_processing_start_guard(
        monkeypatch,
        current_result=None,
        sidebar_result=_TRANSLATE + ("standard",),
        session_overrides={
            KEY: first["session"][KEY],
            "latest_cost_actual": {"total_usd": 9.99},
            "latest_cost_estimate_snapshot": {"mode": "stale"},
        },
    )

    assert record["session"]["latest_cost_actual"] is None
    assert record["session"]["latest_cost_estimate_snapshot"]["mode"] == "standard"


def test_edit_start_is_untouched_by_the_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    # T8.1 / T8.2 / SC-006: for "edit" the sidebar model and intensity are the run's, no translation_*
    # field appears, no estimate is built and no snapshot is carried.
    monkeypatch.setattr(app, "get_price_list", lambda: (_ for _ in ()).throw(AssertionError("no price for edit")))

    record = _run_main_for_processing_start_guard(
        monkeypatch, current_result=None, sidebar_result=_EDIT, session_overrides={"preparation_input_marker": _EDIT_MARKER}
    )

    start = _start_kwargs(record)
    assert start["model"] == "gpt-5.4"
    assert start["app_config"]["editorial_intensity_default"] == "conservative"
    assert "translation_mode" not in start["app_config"]
    assert "translation_first_pass_model" not in start["app_config"]
    assert "cost_estimate_snapshot" not in start["app_config"]
    assert record["session"]["latest_cost_estimate_snapshot"] is None
    assert KEY not in record["session"]


def test_edit_after_translate_after_edit_keeps_the_edit_model_and_intensity(monkeypatch: pytest.MonkeyPatch) -> None:
    def edit_run() -> tuple:
        record = _run_main_for_processing_start_guard(
            monkeypatch, current_result=None, sidebar_result=_EDIT, session_overrides={"preparation_input_marker": _EDIT_MARKER}
        )
        start = _start_kwargs(record)
        return start["model"], start["app_config"]["editorial_intensity_default"]

    before = edit_run()
    _prepare_estimates_then_run(monkeypatch, _TRANSLATE + ("quality",))
    after = edit_run()

    assert before == after == ("gpt-5.4", "conservative")


def test_the_recommendation_never_touches_model_or_intensity() -> None:
    # T8.2: applying a text-settings recommendation moves operation / languages only, so neither
    # "edit"'s model nor its intensity can be changed by it, whatever mode translate was in.
    from docxaicorrector.ui.recommended_text_settings import TEXT_SETTINGS_FIELDS

    assert not {"model", "editorial_intensity", "translation_mode"} & set(TEXT_SETTINGS_FIELDS)


def test_a_new_document_forgets_the_estimate_of_the_previous_one(monkeypatch: pytest.MonkeyPatch) -> None:
    state = SessionState({KEY: {"key": ["old"], "snapshots": {"standard": {}}}})
    monkeypatch.setattr(app.st, "session_state", state)

    assert app._discard_translation_cost_estimates() is True
    assert KEY not in state
    assert app._discard_translation_cost_estimates() is False


# ---------------------------------------------------------------- the result: actual next to ITS estimate

_RESULT_SCRIPT = """
import streamlit as st
from docxaicorrector.ui._ui import render_result_bundle

# The sidebar of THIS session holds a different (current) estimate; it must never reach the result.
st.session_state["translation_cost_estimates"] = {
    "key": ["tok"],
    "snapshots": {"standard": {"total_upper_usd": 7.77, "total_lower_usd": 7.77}},
}
render_result_bundle(
    docx_bytes=b"docx",
    markdown_text="# body",
    original_filename="report.docx",
    processing_operation="translate",
    success_message="Документ обработан.",
    cost_estimate_snapshot=SNAPSHOT,
    cost_actual=ACTUAL,
)
"""


def _result(snapshot: dict | None, actual: dict | None) -> list[str]:
    script = f"SNAPSHOT = {snapshot!r}\nACTUAL = {actual!r}\n" + _RESULT_SCRIPT
    at = AppTest.from_string(script, default_timeout=30).run()
    assert not at.exception, at.exception
    return [caption.value for caption in at.caption]


def test_the_result_shows_the_actual_next_to_its_own_frozen_estimate() -> None:
    captions = _result(
        {"mode": "standard", "total_upper_usd": 1.1, "total_lower_usd": 0.82},
        {"total_usd": 0.95, "run_complete": True, "cost_accounting_complete": True},
    )

    assert "Факт: 0,95 $ · оценка при старте: ≈ 0,82–1,10 $ (без картинок)." in captions
    assert not any("7,77" in text for text in captions)  # the session's current estimate is not shown
    assert i18n.t("result.cost_actual_partial") not in captions


def test_a_bundle_without_a_snapshot_shows_no_estimate_even_when_a_current_one_exists() -> None:
    captions = _result(None, None)

    assert not any("$" in text for text in captions)
    assert not any("оценк" in text.lower() for text in captions)


def test_a_snapshot_without_an_actual_shows_the_estimate_alone() -> None:
    captions = _result({"mode": "quality", "total_upper_usd": 1.9, "total_lower_usd": 1.9}, None)

    assert "Оценка цены при старте: ≈ 1,90 $ (без картинок)." in captions


def test_an_unknown_price_snapshot_says_unknown_next_to_the_actual() -> None:
    captions = _result(
        {"mode": "quality", "total_upper_usd": None, "total_lower_usd": None},
        {"total_usd": 1.2, "run_complete": True, "cost_accounting_complete": True},
    )

    assert "Факт: 1,20 $ · оценка при старте: цена неизвестна (без картинок)." in captions


@pytest.mark.parametrize(
    "actual",
    [
        {"total_usd": 0.4, "run_complete": False, "cost_accounting_complete": True},
        {"total_usd": 0.4, "run_complete": True, "cost_accounting_complete": False},
    ],
)
def test_a_partial_actual_is_labelled_incomplete(actual: dict) -> None:
    captions = _result({"mode": "standard", "total_upper_usd": 1.0, "total_lower_usd": 1.0}, actual)

    assert i18n.t("result.cost_actual_partial") in captions


def test_the_completed_result_view_passes_the_bundles_own_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(app, "render_markdown_preview", lambda **kwargs: None)
    monkeypatch.setattr(app, "render_result_bundle", lambda **kwargs: captured.update(kwargs))
    state = SessionState({KEY: {"key": ["tok"], "snapshots": {"standard": {"total_upper_usd": 7.77}}}})
    monkeypatch.setattr(app.st, "session_state", state)
    bundle = {
        "source_name": "report.docx",
        "docx_bytes": b"d",
        "markdown_text": "m",
        "cost_estimate_snapshot": {"mode": "quality", "total_upper_usd": 1.9},
        "cost_actual": {"total_usd": 1.8},
    }

    app._render_completed_result_view(bundle)

    assert captured["cost_estimate_snapshot"] == {"mode": "quality", "total_upper_usd": 1.9}
    assert captured["cost_actual"] == {"total_usd": 1.8}

    app._render_completed_result_view({"source_name": "r.docx", "docx_bytes": b"d", "markdown_text": "m"})
    assert captured["cost_estimate_snapshot"] is None and captured["cost_actual"] is None


# ---------------------------------------------------------------- cost_estimate_vs_actual


def _snapshot_for_event(upper: float | None = 1.0, lower: float | None = 0.8) -> dict:
    return {
        "mode": "standard",
        "coefficients_version": "069-v1",
        "price_list_date": PRICES.fetched_at,
        "total_upper_usd": upper,
        "total_lower_usd": lower,
        "document": {"source_token": "tok"},
        "stages": {
            "glossary_extraction": {"upper_usd": 0.05, "lower_usd": 0.04},
            "text_generation": {"upper_usd": 0.8, "lower_usd": 0.64},
            "literary_polish": {"upper_usd": 0.15, "lower_usd": 0.12},
        },
    }


def _accounting(*, glossary: float = 0.04, text: float = 0.7, polish: float = 0.1, **overrides: object) -> dict:
    def stage(cost: float, calls: int = 3, without_cost: int = 0) -> dict:
        return {"cost_usd_reported_by_provider": cost, "model_call_count": calls, "model_calls_without_cost": without_cost}

    accounting: dict = {
        "stages": {
            "glossary_extraction": stage(glossary, 1),
            "text_generation": stage(text, 30),
            # a stage the estimate does not cover must not enter the actual
            "boundary_review": stage(5.0, 2),
            "literary_polish": stage(polish, 30),
        }
    }
    accounting.update(overrides)
    return accounting


def test_the_error_is_relative_to_the_actual_and_signed_by_the_upper_bound() -> None:
    comparison = pipeline.build_cost_estimate_vs_actual(
        snapshot=_snapshot_for_event(upper=1.0, lower=0.8),
        accounting=_accounting(glossary=0.04, text=0.7, polish=0.1),
        run_status="succeeded",
    )

    assert comparison["actual_usd"] == pytest.approx(0.84)
    assert comparison["relative_error_vs_upper"] == pytest.approx((0.84 - 1.0) / 0.84)
    assert cast(float, comparison["relative_error_vs_upper"]) < 0  # the upper bound overestimated
    assert comparison["within_range"] is True
    assert comparison["run_complete"] is True and comparison["cost_accounting_complete"] is True
    assert cast(dict, comparison["stages"])["text_generation"] == {"estimate_upper": 0.8, "estimate_lower": 0.64, "actual": 0.7}


def test_an_actual_above_the_upper_bound_is_a_positive_error_outside_the_range() -> None:
    comparison = pipeline.build_cost_estimate_vs_actual(
        snapshot=_snapshot_for_event(upper=1.0, lower=0.8),
        accounting=_accounting(glossary=0.1, text=1.0, polish=0.2),
        run_status="succeeded",
    )

    assert comparison["actual_usd"] == pytest.approx(1.3)
    assert comparison["relative_error_vs_upper"] == pytest.approx(0.3 / 1.3)
    assert comparison["within_range"] is False


def test_an_actual_below_the_lower_bound_is_outside_the_range() -> None:
    comparison = pipeline.build_cost_estimate_vs_actual(
        snapshot=_snapshot_for_event(upper=1.0, lower=0.8),
        accounting=_accounting(glossary=0.01, text=0.3, polish=0.1),
        run_status="succeeded",
    )

    assert comparison["within_range"] is False


@pytest.mark.parametrize("status", ["failed", "stopped", None])
def test_a_run_that_did_not_succeed_is_flagged_and_its_error_is_not_compared(status: str | None) -> None:
    comparison = pipeline.build_cost_estimate_vs_actual(
        snapshot=_snapshot_for_event(), accounting=_accounting(), run_status=status
    )

    assert comparison["run_complete"] is False
    assert comparison["relative_error_vs_upper"] is None
    assert comparison["within_range"] is None
    assert comparison["actual_usd"] == pytest.approx(0.84)  # the spend is still reported


def test_a_call_without_a_reported_price_makes_the_cost_incomplete_and_uncompared() -> None:
    accounting = _accounting()
    accounting["stages"]["text_generation"]["model_calls_without_cost"] = 2

    comparison = pipeline.build_cost_estimate_vs_actual(
        snapshot=_snapshot_for_event(), accounting=accounting, run_status="succeeded"
    )

    assert comparison["cost_accounting_complete"] is False
    assert comparison["relative_error_vs_upper"] is None and comparison["within_range"] is None


def test_an_estimated_stage_that_made_no_call_is_incomplete() -> None:
    accounting = _accounting()
    del accounting["stages"]["literary_polish"]

    comparison = pipeline.build_cost_estimate_vs_actual(
        snapshot=_snapshot_for_event(), accounting=accounting, run_status="succeeded"
    )

    assert comparison["cost_accounting_complete"] is False
    assert comparison["relative_error_vs_upper"] is None


def test_an_unknown_price_estimate_is_not_compared() -> None:
    comparison = pipeline.build_cost_estimate_vs_actual(
        snapshot=_snapshot_for_event(upper=None, lower=None), accounting=_accounting(), run_status="succeeded"
    )

    assert comparison["estimate_upper_usd"] is None
    assert comparison["relative_error_vs_upper"] is None and comparison["within_range"] is None
    assert cast(float, comparison["actual_usd"]) > 0


def _emit(app_config: dict, *, status: str | None = "succeeded") -> tuple[list, list, object]:
    events: list = []
    states: list = []
    result = pipeline.emit_cost_estimate_vs_actual(
        app_config=app_config,
        accounting=_accounting(),
        run_status=status,
        run_id="run-1",
        filename="report.docx",
        log_event=lambda level, event_id, message, **fields: events.append((level, event_id, fields)),
        emit_state=lambda runtime, **values: states.append((runtime, values)),
        runtime="runtime",
    )
    return events, states, result


def test_the_event_is_emitted_once_at_info_with_the_documented_fields() -> None:
    events, states, _ = _emit({"cost_estimate_snapshot": _snapshot_for_event()})

    assert len(events) == 1
    level, name, fields = events[0]
    assert (level, name) == (logging.INFO, "cost_estimate_vs_actual")
    assert set(fields) == {
        "filename", "run_id", "mode", "coefficients_version", "price_list_date", "stages",
        "estimate_upper_usd", "estimate_lower_usd", "actual_usd", "relative_error_vs_upper",
        "within_range", "run_complete", "cost_accounting_complete",
    }
    assert fields["run_id"] == "run-1" and fields["mode"] == "standard"
    # the bundle gets the actual through session state, tagged with the source it belongs to
    runtime, values = states[0]
    assert runtime == "runtime"
    assert values["latest_cost_actual"]["total_usd"] == pytest.approx(0.84)
    assert values["latest_cost_actual"]["run_complete"] is True
    assert values["latest_cost_actual"]["stages"]["literary_polish"] == 0.1


@pytest.mark.parametrize("config", [{}, {"cost_estimate_snapshot": None}, {"cost_estimate_snapshot": "garbage"}])
def test_a_run_without_a_snapshot_emits_nothing(config: dict) -> None:
    events, states, result = _emit(config)

    assert events == [] and states == [] and result is None


def test_a_failing_logger_never_takes_the_run_down() -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("logger down")

    result = pipeline.emit_cost_estimate_vs_actual(
        app_config={"cost_estimate_snapshot": _snapshot_for_event()},
        accounting=_accounting(),
        run_status="succeeded",
        run_id="r",
        filename="f",
        log_event=broken,
        emit_state=lambda runtime, **values: None,
        runtime=None,
    )

    assert result is None


def _run_wrapper(monkeypatch: pytest.MonkeyPatch, *, outcome: object, app_config: dict) -> tuple[list, list]:
    events: list = []
    states: list = []
    monkeypatch.setattr(pipeline, "emit_run_model_accounting_event", lambda **kwargs: _accounting())

    def fake_run(**kwargs: object) -> object:
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(pipeline, "_run_document_processing_accounted", fake_run)
    noop = lambda *a, **k: None  # noqa: E731
    kwargs: dict = dict(
        uploaded_file="report.docx", jobs=[], image_assets=[], image_mode="safe", app_config=app_config,
        model="m", max_retries=1, on_progress=noop, runtime="rt", resolve_uploaded_filename=noop,
        get_client=noop, ensure_pandoc_available=noop, load_system_prompt=noop,
        log_event=lambda level, name, message, **fields: events.append((name, fields)),
        present_error=noop, emit_state=lambda runtime, **values: states.append(values), emit_finalize=noop,
        emit_log=noop, emit_status=noop, should_stop_processing=noop, generate_markdown_block=noop,
        process_document_images=noop, inspect_placeholder_integrity=noop, convert_markdown_to_docx_bytes=noop,
        preserve_source_paragraph_properties=noop, reinsert_inline_images=noop, run_id="run-9",
    )
    try:
        pipeline.run_document_processing(**kwargs)
    except RuntimeError:
        pass
    return events, states


def test_the_pipeline_publishes_the_comparison_after_a_successful_run(monkeypatch: pytest.MonkeyPatch) -> None:
    events, states = _run_wrapper(
        monkeypatch, outcome="succeeded", app_config={"cost_estimate_snapshot": _snapshot_for_event()}
    )

    fields = dict(events)["cost_estimate_vs_actual"]
    assert fields["run_complete"] is True and fields["run_id"] == "run-9"
    assert fields["relative_error_vs_upper"] is not None
    assert states[0]["latest_cost_actual"]["run_complete"] is True


@pytest.mark.parametrize("outcome", ["failed", "stopped", RuntimeError("boom")])
def test_the_pipeline_marks_a_failed_stopped_or_crashed_run_incomplete(
    monkeypatch: pytest.MonkeyPatch, outcome: object
) -> None:
    events, states = _run_wrapper(
        monkeypatch, outcome=outcome, app_config={"cost_estimate_snapshot": _snapshot_for_event()}
    )

    fields = dict(events)["cost_estimate_vs_actual"]
    assert fields["run_complete"] is False
    assert fields["relative_error_vs_upper"] is None and fields["within_range"] is None
    assert states[0]["latest_cost_actual"]["run_complete"] is False


def test_the_pipeline_emits_no_comparison_for_a_run_without_a_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    events, states = _run_wrapper(monkeypatch, outcome="succeeded", app_config={})

    assert "cost_estimate_vs_actual" not in dict(events)
    assert states == []


# ---------------------------------------------------------------- review 069 acceptance, findings 3 and 4


def test_edit_translate_edit_keeps_the_chosen_edit_model() -> None:
    # Finding 3: the model selectbox is not drawn for translate, so Streamlit drops its widget state;
    # coming back to edit must show the user's choice, not the default model.
    custom = "openrouter:vendor/review-custom"
    at = AppTest.from_string(_SIDEBAR_SCRIPT, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    at.sidebar.selectbox(key="sidebar_model").select("custom").run()
    at.sidebar.text_input[0].set_value(custom).run()
    assert not at.exception, at.exception
    assert at.session_state["_sidebar_result"][0] == custom

    at.sidebar.selectbox(key="sidebar_text_operation").select(ui.TEXT_OPERATION_LABELS["translate"]).run()
    assert "sidebar_model" not in _selectbox_keys(at)
    at.sidebar.selectbox(key="sidebar_text_operation").select(ui.TEXT_OPERATION_LABELS["edit"]).run()

    assert not at.exception, at.exception
    assert at.sidebar.selectbox(key="sidebar_model").value == "custom"
    assert at.session_state["_sidebar_result"][0] == custom


def test_a_changed_pass_configuration_recomputes_the_estimate_and_the_start_never_freezes_a_stale_one(
    session: SessionState,
) -> None:
    # Finding 4: same document, same prices, but the effective ``quality`` pass moved low -> high.
    assert _refresh() is True
    assert session[KEY]["snapshots"]["quality"]["passes"][0]["reasoning_effort"] == "low"

    high = copy.deepcopy(_APP_CONFIG_WITH_MODES)
    high["translation_modes"]["quality"] = dataclasses.replace(
        high["translation_modes"]["quality"],
        first_pass=dataclasses.replace(high["translation_modes"]["quality"].first_pass, reasoning_effort="high"),
    )
    effective = app.resolve_effective_translation_config(
        high, processing_operation="translate", requested_mode="quality",
        requested_model=None, requested_intensity=None, origin="ui",
    )

    # Start on the stale estimate: nothing frozen, rather than a snapshot of another configuration.
    assert app._freeze_cost_estimate_snapshot(effective, "tok") is None
    assert _refresh(app_config=high) is True
    frozen = app._freeze_cost_estimate_snapshot(effective, "tok")
    assert frozen is not None
    assert cast(list, frozen["passes"])[0]["reasoning_effort"] == "high"
