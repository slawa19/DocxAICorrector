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


def test_fallback_to_ru_when_key_missing_in_en(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The ru fallback is exercised on synthetic catalogs, not on the shipped ones.

    Pinning this path to a key the delivered ``en.json`` happens to be missing made the
    catalog a hostage: finishing the English translation would have turned the build
    red. The lookup order is a property of :func:`i18n.t`, so it is proven here on
    catalogs this test owns, and ``en.json`` is free to reach parity with ``ru``.
    """
    (tmp_path / "ru.json").write_text(
        json.dumps({"synthetic.only_in_ru": "Только в ru", "synthetic.in_both": "РУ"}),
        encoding="utf-8",
    )
    (tmp_path / "en.json").write_text(
        json.dumps({"synthetic.in_both": "EN"}), encoding="utf-8"
    )
    monkeypatch.setattr(i18n, "_LOCALES_DIR", tmp_path)
    i18n.clear_catalog_cache()
    _force_language(monkeypatch, "en")

    assert i18n.t("synthetic.in_both") == "EN"
    assert i18n.t("synthetic.only_in_ru") == "Только в ru"


def test_english_value_used_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_language(monkeypatch, "en")
    assert i18n.t("sidebar.settings_header") == "Settings"


def test_missing_key_returns_key_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_language(monkeypatch, "en")
    assert i18n.t("no.such.key") == "no.such.key"


def test_interpolation_applies_named_placeholders() -> None:
    assert i18n.t("status.prep_manifest_meta", path="X") == "Structure manifest: X"


def test_interpolation_with_missing_placeholder_returns_unformatted() -> None:
    # Supplying the wrong kwargs must not raise; returns the raw template.
    assert i18n.t("status.prep_manifest_meta", wrong=1) == "Structure manifest: {path}"


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
    }
    assert referenced <= set(ru)
    # ru is the complete default: it must contain every key that en defines.
    # The other direction is deliberately left free. en may stay partial (t() falls
    # back to ru) and en may also reach full parity; requiring it to stay partial
    # forbade finishing the translation. The fallback path is covered by
    # test_fallback_to_ru_when_key_missing_in_en on catalogs that test owns.
    assert set(en) <= set(ru)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_narration_source_fallback_notice_renders_its_counts(
    monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    """Spec 054: the excluded-block loss is a USER-visible notice, in both catalogs.

    The result screen renders notices through ``t(message_key, **params)``, so a template
    whose placeholders do not match the emitted params would silently ship the raw braces.
    """
    _force_language(monkeypatch, lang)

    message = i18n.t("result.narration_source_fallback_excluded", count=6, chars=20597)

    assert "{" not in message
    assert "6" in message
    assert "20597" in message


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_narration_omitted_paragraph_notice_renders_its_counts(
    monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    """Spec 056 E, rev41: the per-PARAGRAPH loss is user-visible too, in both catalogs.

    It shipped with neither characters nor a notice, which made the remedy quieter than the
    block-level failure it replaced.
    """
    _force_language(monkeypatch, lang)

    message = i18n.t("result.narration_omitted_paragraphs_excluded", count=5, chars=1378)

    assert "{" not in message
    assert "5" in message
    assert "1378" in message


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


# application_flow.py no longer references i18n keys directly: the flow.* keys moved
# to processing/application_flow.py (spec 027). Their catalog presence is covered by
# test_app_and_flow_namespace_key_sets_match_between_catalogs and
# tests/test_layer_boundaries.py::test_flow_message_defaults_match_ru_catalog.
@pytest.mark.parametrize("filename", ["_app.py"])
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


def test_acceptance_check_names_have_catalog_entries_in_both_locales() -> None:
    """Spec 059 FR-B3 / anti-regression #18 — a guard that SEES the naming scheme.

    ``test_ui_module_keys_present_in_both_catalogs`` collects keys with a regex over
    ``t("literal")`` occurrences, so ``t(f"result.acceptance_check.{name}")`` is invisible
    to it: the guard would stay green while the screen printed a raw identifier. The check
    names are a CLOSED enumeration owned by ``validation/acceptance.py`` (a structural fact,
    not a literal from a book — Constitution VII), so the guard enumerates them from there.

    Only the checks a production screen may NAME are required: the harness-only
    source↔output comparison is never shown (production owns no source DOCX).
    """
    from docxaicorrector.ui.review_presentation import ACCEPTANCE_CHECK_KEY_PREFIX
    from docxaicorrector.validation.acceptance import (
        PRODUCTION_ACCEPTANCE_CHECK_NAMES,
        production_reportable_failed_checks,
    )

    reportable = production_reportable_failed_checks(
        {"failed_checks": list(PRODUCTION_ACCEPTANCE_CHECK_NAMES)}
    )
    assert reportable, "expected at least one production-reportable acceptance check"
    expected_keys = {f"{ACCEPTANCE_CHECK_KEY_PREFIX}{name}" for name in reportable}

    ru = json.loads(_locale_path("ru.json").read_text(encoding="utf-8"))
    en = json.loads(_locale_path("en.json").read_text(encoding="utf-8"))
    assert not sorted(expected_keys - set(ru)), (
        f"acceptance check keys missing from ru.json: {sorted(expected_keys - set(ru))}"
    )
    assert not sorted(expected_keys - set(en)), (
        f"acceptance check keys missing from en.json: {sorted(expected_keys - set(en))}"
    )
    # And the other direction: a catalog entry for a name the enumeration no longer has is
    # a dead string that would quietly outlive its check.
    for catalog, label in ((ru, "ru.json"), (en, "en.json")):
        stale = {
            key for key in catalog if key.startswith(ACCEPTANCE_CHECK_KEY_PREFIX)
        } - expected_keys
        assert not stale, f"{label} carries acceptance check keys with no check: {sorted(stale)}"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_acceptance_and_source_text_notices_render_their_params(
    monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    """Spec 059 FR-B3/FR-B5: the two new notice templates interpolate what the pipeline sends."""
    _force_language(monkeypatch, lang)

    verdict_message = i18n.t("result.acceptance_not_passed", count=2, checks="A, B")
    assert "{" not in verdict_message
    assert "2" in verdict_message and "A, B" in verdict_message

    delivered = i18n.t(
        "result.source_text_delivered", count=3, blocks=1, chars=5581, anchors="«Once upon»"
    )
    assert "{" not in delivered
    assert "3" in delivered and "5581" in delivered and "Once upon" in delivered

    unanchored = i18n.t(
        "result.source_text_delivered_with_unanchored",
        count=3,
        blocks=1,
        chars=5581,
        anchors="«Once upon»",
        unanchored=1,
    )
    assert "{" not in unanchored
    assert "Once upon" in unanchored

    without_anchors = i18n.t(
        "result.source_text_delivered_without_anchors", count=3, blocks=1, chars=5581, unanchored=3
    )
    assert "{" not in without_anchors
    assert "3" in without_anchors

    # Spec 059 FR-B4, review finding 4: ``edit`` rewrites text that is already in the target
    # language, so the translating wording is false there. Second family, same three anchor
    # variants, both catalogs.
    for key in (
        "result.unedited_text_delivered",
        "result.unedited_text_delivered_with_unanchored",
        "result.unedited_text_delivered_without_anchors",
    ):
        message = i18n.t(key, count=3, blocks=1, chars=5581, anchors="«Абзац»", unanchored=1)
        assert "{" not in message, key
        assert "5581" in message, key

    artifact = i18n.t("result.controlled_block_fallback_artifact", path="/x/y.json")
    assert "{" not in artifact
    assert "/x/y.json" in artifact


def test_app_and_flow_namespace_key_sets_match_between_catalogs() -> None:
    """The app.*, recommend.*, and flow.* key sets are identical across ru.json and en.json."""
    ru = json.loads(_locale_path("ru.json").read_text(encoding="utf-8"))
    en = json.loads(_locale_path("en.json").read_text(encoding="utf-8"))
    for namespace in ("app.", "recommend.", "flow."):
        ru_keys = {key for key in ru if key.startswith(namespace)}
        en_keys = {key for key in en if key.startswith(namespace)}
        assert ru_keys == en_keys, f"{namespace}* key sets differ between catalogs"
