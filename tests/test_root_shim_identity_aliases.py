from __future__ import annotations

import importlib
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from typing import Any, Callable, TypeVar, cast

import pytest


T = TypeVar("T")


def _identity_cache_resource(func: T | None = None, **_: object) -> T | Callable[[T], T]:
    if func is None:
        return lambda inner: inner
    return func


@pytest.fixture(autouse=True)
def _streamlit_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = SimpleNamespace(
        session_state={},
        set_page_config=lambda *args, **kwargs: None,
        cache_resource=_identity_cache_resource,
    )
    monkeypatch.setitem(sys.modules, "streamlit", cast(Any, stub))


@pytest.mark.parametrize(
    ("root_module_name", "target_module_name"),
    [
        ("app", "docxaicorrector.ui._app"),
        ("ui", "docxaicorrector.ui._ui"),
        ("app_runtime", "docxaicorrector.ui.app_runtime"),
        ("application_flow", "docxaicorrector.ui.application_flow"),
        ("compare_panel", "docxaicorrector.ui.compare_panel"),
        ("config", "docxaicorrector.core.config"),
        ("constants", "docxaicorrector.core.constants"),
        ("logger", "docxaicorrector.core.logger"),
        ("models", "docxaicorrector.core.models"),
        ("preparation", "docxaicorrector.processing.preparation"),
        ("processing_runtime", "docxaicorrector.processing.processing_runtime"),
        ("processing_service", "docxaicorrector.processing.processing_service"),
        ("state", "docxaicorrector.runtime.state"),
        ("generation", "docxaicorrector.generation._generation"),
        ("formatting_transfer", "docxaicorrector.generation.formatting_transfer"),
        ("formatting_diagnostics_retention", "docxaicorrector.generation.formatting_diagnostics_retention"),
        ("message_formatting", "docxaicorrector.generation.message_formatting"),
        ("openai_response_utils", "docxaicorrector.generation.openai_response_utils"),
        ("search", "docxaicorrector.generation.search"),
        ("real_image_manifest", "docxaicorrector.real_image.manifest"),
        ("real_document_validation_common", "docxaicorrector.validation.common"),
        ("real_document_validation_profiles", "docxaicorrector.validation.profiles"),
        ("real_document_validation_structural", "docxaicorrector.validation.structural"),
    ],
)
def test_root_shim_is_identity_alias(root_module_name: str, target_module_name: str) -> None:
    root_module = importlib.import_module(root_module_name)
    target_module = importlib.import_module(target_module_name)

    assert root_module is target_module


def test_acceptance_module_identities_hold() -> None:
    import app
    import config
    import generation
    import models
    import state
    import docxaicorrector.core.config as config_target
    import docxaicorrector.core.models as models_target
    import docxaicorrector.generation._generation as generation_target
    import docxaicorrector.runtime.state as state_target
    import docxaicorrector.ui._app as app_target

    assert config is config_target
    assert generation is generation_target
    assert models is models_target
    assert state is state_target
    assert app is app_target


def test_acceptance_export_identities_hold() -> None:
    from preparation import PreparedDocumentData as root_prepared_document_data
    from docxaicorrector.processing.preparation import PreparedDocumentData as package_prepared_document_data

    assert root_prepared_document_data is package_prepared_document_data


def test_app_script_execution_reuses_single_app_module_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    app_target = importlib.import_module("docxaicorrector.ui._app")

    def _fake_main() -> None:
        captured["app_module"] = sys.modules.get("app")
        captured["target_module"] = app_target

    monkeypatch.setattr(app_target, "main", _fake_main)
    sys.modules.pop("app", None)

    runpy.run_path(str(Path(__file__).resolve().parents[1] / "app.py"), run_name="__main__")

    assert captured["app_module"] is captured["target_module"]
