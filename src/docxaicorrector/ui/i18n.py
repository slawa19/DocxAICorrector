"""UI internationalization foundation.

Provides a minimal, dependency-free lookup mechanism for user-facing UI
strings. String catalogs are flat JSON files under ``locales/`` keyed by
namespaced string keys (``area.element``). Russian (``ru``) is the complete
default catalog; other languages may be partial and fall back to ``ru``.

The public API is intentionally small:

* :func:`get_ui_language` — resolve the active UI language.
* :func:`t` — translate a key, with fallback and optional interpolation.

Both are importable and unit-testable without a running Streamlit session.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = ("ru", "en")
DEFAULT_LANGUAGE: Final[str] = "ru"

_LOCALES_DIR: Final[Path] = Path(__file__).resolve().parent / "locales"

# Module-level cache: language code -> parsed flat catalog. Populated lazily.
_CATALOG_CACHE: dict[str, dict[str, str]] = {}


def _load_catalog(lang: str) -> dict[str, str]:
    """Load and cache the flat string catalog for ``lang``.

    Returns an empty catalog for unknown languages or unreadable/invalid
    files rather than raising, so a missing translation file degrades to the
    fallback chain instead of crashing the UI.
    """
    cached = _CATALOG_CACHE.get(lang)
    if cached is not None:
        return cached

    catalog: dict[str, str] = {}
    path = _LOCALES_DIR / f"{lang}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, str):
                catalog[key] = value

    _CATALOG_CACHE[lang] = catalog
    return catalog


def clear_catalog_cache() -> None:
    """Drop all cached catalogs (primarily for tests)."""
    _CATALOG_CACHE.clear()


def _session_ui_language() -> str | None:
    """Best-effort read of ``st.session_state['ui_language']``.

    Imports Streamlit lazily and tolerates the absence of a running session
    so the module stays importable and testable outside Streamlit.
    """
    try:
        import streamlit as st

        value = st.session_state.get("ui_language")
    except Exception:
        return None
    if isinstance(value, str):
        return value
    return None


def get_ui_language() -> str:
    """Return the active UI language code.

    Resolution order: a supported, non-empty ``ui_language`` in the Streamlit
    session state, otherwise the default language (``ru``).
    """
    candidate = _session_ui_language()
    if isinstance(candidate, str):
        normalized = candidate.strip()
        if normalized in SUPPORTED_LANGUAGES:
            return normalized
    return DEFAULT_LANGUAGE


def t(key: str, /, **kwargs: Any) -> str:
    """Translate ``key`` for the active UI language.

    Lookup order: current-language catalog, then the ``ru`` default catalog,
    then ``key`` itself. When ``kwargs`` are supplied, the result is passed
    through :meth:`str.format`; malformed placeholders degrade to the
    unformatted string rather than raising.
    """
    lang = get_ui_language()
    catalog = _load_catalog(lang)
    value = catalog.get(key)
    if value is None and lang != DEFAULT_LANGUAGE:
        value = _load_catalog(DEFAULT_LANGUAGE).get(key)
    if value is None:
        value = key

    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return value
    return value
