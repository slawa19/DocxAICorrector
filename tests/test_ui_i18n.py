"""Tests for the UI internationalization foundation (i18n.py)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from docxaicorrector.ui import i18n


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Ensure each test starts and ends with a clean catalog cache."""
    i18n.clear_catalog_cache()
    yield
    i18n.clear_catalog_cache()


def _force_language(monkeypatch: pytest.MonkeyPatch, lang: str | None) -> None:
    """Pin ``get_ui_language`` to a specific language for a test."""
    monkeypatch.setattr(i18n, "get_ui_language", lambda: lang or i18n.DEFAULT_LANGUAGE)


def test_default_lookup_returns_ru_value() -> None:
    assert i18n.t("app.title") == "AI-редактор DOCX/DOC/PDF через Markdown"
    assert i18n.t("sidebar.settings_header") == "Настройки"


def test_fallback_to_ru_when_key_missing_in_en(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_language(monkeypatch, "en")
    # sidebar.model_label is intentionally absent from en.json.
    assert i18n.t("sidebar.model_label") == "Модель"


def test_english_value_used_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_language(monkeypatch, "en")
    assert i18n.t("sidebar.settings_header") == "Settings"


def test_missing_key_returns_key_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_language(monkeypatch, "en")
    assert i18n.t("no.such.key") == "no.such.key"


def test_interpolation_applies_named_placeholders() -> None:
    assert i18n.t("structure.visible_count", visible=3, total=10) == "Видно разделов: 3/10"


def test_interpolation_with_missing_placeholder_returns_unformatted() -> None:
    # Supplying the wrong kwargs must not raise; returns the raw template.
    assert i18n.t("structure.visible_count", wrong=1) == "Видно разделов: {visible}/{total}"


def test_get_ui_language_defaults_to_ru(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(i18n, "_session_ui_language", lambda: None)
    assert i18n.get_ui_language() == "ru"


def test_get_ui_language_honors_supported_session_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(i18n, "_session_ui_language", lambda: "en")
    assert i18n.get_ui_language() == "en"


def test_get_ui_language_ignores_unsupported_session_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(i18n, "_session_ui_language", lambda: "fr")
    assert i18n.get_ui_language() == "ru"


def test_get_ui_language_ignores_empty_session_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(i18n, "_session_ui_language", lambda: "   ")
    assert i18n.get_ui_language() == "ru"


def _locale_path(name: str) -> Path:
    return Path(i18n.__file__).resolve().parent / "locales" / name


def test_catalog_files_are_valid_json() -> None:
    for name in ("ru.json", "en.json"):
        data = json.loads(_locale_path(name).read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in data.items())


def test_ru_is_superset_of_referenced_and_en_keys() -> None:
    ru = json.loads(_locale_path("ru.json").read_text(encoding="utf-8"))
    en = json.loads(_locale_path("en.json").read_text(encoding="utf-8"))
    referenced = {
        "app.title",
        "sidebar.settings_header",
        "sidebar.model_label",
        "structure.visible_count",
    }
    assert referenced <= set(ru)
    # ru is the complete default: it must contain every key that en defines.
    assert set(en) <= set(ru)
    # And en must be genuinely partial to exercise the fallback path.
    assert set(ru) - set(en)


def _panel_source() -> str:
    panel_path = Path(i18n.__file__).resolve().parent / "structure_review_panel.py"
    return panel_path.read_text(encoding="utf-8")


def test_structure_panel_keys_present_in_ru_catalog() -> None:
    """Every ``structure.*`` key referenced by the panel must exist in ru.json."""
    referenced_keys = set(re.findall(r't\(\s*["\'](structure\.[a-z0-9_]+)["\']', _panel_source()))
    assert referenced_keys, "expected the panel to reference structure.* i18n keys"
    ru = json.loads(_locale_path("ru.json").read_text(encoding="utf-8"))
    missing = sorted(referenced_keys - set(ru))
    assert not missing, f"structure.* keys referenced by the panel but missing from ru.json: {missing}"


def test_structure_panel_key_sets_match_between_catalogs() -> None:
    """Every ``structure.*`` key defined in ru.json is also defined in en.json (and vice versa)."""
    ru = json.loads(_locale_path("ru.json").read_text(encoding="utf-8"))
    en = json.loads(_locale_path("en.json").read_text(encoding="utf-8"))
    ru_structure = {key for key in ru if key.startswith("structure.")}
    en_structure = {key for key in en if key.startswith("structure.")}
    assert ru_structure == en_structure


def _ui_module_source() -> str:
    ui_path = Path(i18n.__file__).resolve().parent / "_ui.py"
    return ui_path.read_text(encoding="utf-8")


def test_ui_module_keys_present_in_both_catalogs() -> None:
    """Every i18n key referenced by _ui.py must exist in both ru.json and en.json."""
    referenced_keys = set(re.findall(r't\(\s*["\']([a-z_]+\.[a-z0-9_]+)["\']', _ui_module_source()))
    assert referenced_keys, "expected _ui.py to reference i18n keys"
    ru = json.loads(_locale_path("ru.json").read_text(encoding="utf-8"))
    en = json.loads(_locale_path("en.json").read_text(encoding="utf-8"))
    missing_ru = sorted(referenced_keys - set(ru))
    assert not missing_ru, f"keys referenced by _ui.py but missing from ru.json: {missing_ru}"
    missing_en = sorted(referenced_keys - set(en))
    assert not missing_en, f"keys referenced by _ui.py but missing from en.json: {missing_en}"


def _module_source(filename: str) -> str:
    return (Path(i18n.__file__).resolve().parent / filename).read_text(encoding="utf-8")


@pytest.mark.parametrize("filename", ["_app.py", "application_flow.py"])
def test_migrated_ui_module_keys_present_in_both_catalogs(filename: str) -> None:
    """Every i18n key referenced by the migrated ui modules exists in both catalogs."""
    referenced_keys = set(re.findall(r't\(\s*["\']([a-z_]+\.[a-z0-9_]+)["\']', _module_source(filename)))
    assert referenced_keys, f"expected {filename} to reference i18n keys"
    ru = json.loads(_locale_path("ru.json").read_text(encoding="utf-8"))
    en = json.loads(_locale_path("en.json").read_text(encoding="utf-8"))
    missing_ru = sorted(referenced_keys - set(ru))
    assert not missing_ru, f"keys referenced by {filename} but missing from ru.json: {missing_ru}"
    missing_en = sorted(referenced_keys - set(en))
    assert not missing_en, f"keys referenced by {filename} but missing from en.json: {missing_en}"


def test_app_and_flow_namespace_key_sets_match_between_catalogs() -> None:
    """The app.*, recommend.*, and flow.* key sets are identical across ru.json and en.json."""
    ru = json.loads(_locale_path("ru.json").read_text(encoding="utf-8"))
    en = json.loads(_locale_path("en.json").read_text(encoding="utf-8"))
    for namespace in ("app.", "recommend.", "flow."):
        ru_keys = {key for key in ru if key.startswith(namespace)}
        en_keys = {key for key in en if key.startswith(namespace)}
        assert ru_keys == en_keys, f"{namespace}* key sets differ between catalogs"
