from __future__ import annotations

import importlib
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from typing import Any, Callable, TypeVar, cast

import pytest


T = TypeVar("T")

PACKAGE_MODULES = (
    "docxaicorrector.ui._app",
    "docxaicorrector.ui._ui",
    "docxaicorrector.ui.app_runtime",
    "docxaicorrector.ui.application_flow",
    "docxaicorrector.ui.compare_panel",
    "docxaicorrector.core.config",
    "docxaicorrector.core.constants",
    "docxaicorrector.core.logger",
    "docxaicorrector.core.models",
    "docxaicorrector.processing.preparation",
    "docxaicorrector.processing.processing_runtime",
    "docxaicorrector.processing.processing_service",
    "docxaicorrector.runtime.state",
    "docxaicorrector.generation._generation",
    "docxaicorrector.generation.formatting_transfer",
    "docxaicorrector.generation.formatting_diagnostics_retention",
    "docxaicorrector.generation.message_formatting",
    "docxaicorrector.generation.openai_response_utils",
    "docxaicorrector.generation.search",
    "docxaicorrector.real_image.manifest",
    "docxaicorrector.validation.common",
    "docxaicorrector.validation.profiles",
    "docxaicorrector.validation.structural",
)


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


@pytest.mark.parametrize("module_name", PACKAGE_MODULES)
def test_package_module_imports_succeed_without_root_shims(module_name: str) -> None:
    module = importlib.import_module(module_name)

    assert module.__name__ == module_name


def test_package_exports_remain_directly_reachable() -> None:
    from docxaicorrector.processing.preparation import PreparedDocumentData as prepared_document_data
    from docxaicorrector.processing.preparation import PreparedDocumentData as prepared_document_data_again

    assert prepared_document_data is prepared_document_data_again


def test_app_script_execution_delegates_to_package_main(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    app_target = importlib.import_module("docxaicorrector.ui._app")

    def _fake_main() -> None:
        captured["called"] = True
        captured["target_module"] = sys.modules.get(app_target.__name__)
        captured["app_module"] = sys.modules.get("app")

    monkeypatch.setattr(app_target, "main", _fake_main)
    sys.modules.pop("app", None)

    runpy.run_path(str(Path(__file__).resolve().parents[1] / "app.py"), run_name="__main__")

    assert captured["called"] is True
    assert captured["target_module"] is app_target
    assert captured["app_module"] is None
