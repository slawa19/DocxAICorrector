"""Spec 069 WP-7: OpenRouter price list cache (contracts/cost-estimate.md section 3). The network is always mocked."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from docxaicorrector.pipeline import price_list as pl

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
BODY = {
    "data": [
        {"id": "google/gemini-3.1-flash-lite-preview", "pricing": {"prompt": "0.00000025", "completion": "0.0000015"}},
        {"id": "anthropic/claude-haiku-5.5", "pricing": {"prompt": "0.0000001", "completion": "0.0000005"}},
        {"id": "openrouter/auto", "pricing": {"prompt": "-1", "completion": "-1"}},
        {"id": "broken/no-pricing"},
    ]
}


def _write_cache(path: Path, fetched_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "fetched_at": fetched_at.isoformat(),
            "source_url": pl.PRICE_LIST_SOURCE_URL,
            "prices": {"cached/model": {"input_per_1m": 1.0, "output_per_1m": 2.0}},
        }),
        encoding="utf-8",
    )


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    return tmp_path / "price_list" / "openrouter_models.json"


@pytest.fixture
def warnings_seen(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    seen: list[tuple[int, str]] = []
    monkeypatch.setattr(pl, "log_event", lambda level, event, message, **ctx: seen.append((level, event)) or "id")
    return seen


def _network_forbidden(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def fail(timeout: float = 0) -> object:
        calls.append(1)
        raise AssertionError("network must not be touched")

    monkeypatch.setattr(pl, "_fetch_models_json", fail)
    return calls


def test_fresh_cache_means_no_network(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _write_cache(cache, NOW - timedelta(hours=23))
    calls = _network_forbidden(monkeypatch)
    result = pl.get_price_list(NOW, cache_path=cache)
    assert calls == []
    assert result is not None and result.source == "cache"
    assert result.price_for("cached/model") == (1.0, 2.0)


def test_anti_vacuum_the_network_mock_fails_the_test_when_called_with_a_fresh_cache(
    monkeypatch: pytest.MonkeyPatch, cache: Path
) -> None:
    """The mock raises AssertionError; with a STALE cache the code must reach it and survive it
    (fall back), which proves the mock is wired to the code path under test."""
    _write_cache(cache, NOW - timedelta(hours=30))
    calls = _network_forbidden(monkeypatch)
    pl.get_price_list(NOW, cache_path=cache)
    assert calls == [1]


def test_stale_cache_triggers_a_fetch_with_a_five_second_timeout_and_rewrites_the_cache(
    monkeypatch: pytest.MonkeyPatch, cache: Path
) -> None:
    _write_cache(cache, NOW - timedelta(hours=25))
    timeouts: list[float] = []
    monkeypatch.setattr(pl, "_fetch_models_json", lambda timeout=0: timeouts.append(timeout) or BODY)
    result = pl.get_price_list(NOW, cache_path=cache)
    assert timeouts == [5.0]
    assert result is not None and result.source == "network"
    assert result.fetched_at == NOW.isoformat()
    assert result.price_for("google/gemini-3.1-flash-lite-preview") == pytest.approx((0.25, 1.5))
    assert result.price_for("anthropic/claude-haiku-5.5") == pytest.approx((0.10, 0.50))
    assert result.price_for("openrouter/auto") is None and result.price_for("broken/no-pricing") is None
    stored = json.loads(cache.read_text(encoding="utf-8"))
    assert stored["fetched_at"] == NOW.isoformat() and stored["source_url"] == pl.PRICE_LIST_SOURCE_URL
    assert stored["prices"]["anthropic/claude-haiku-5.5"]["output_per_1m"] == pytest.approx(0.5)
    assert not list(cache.parent.glob("*.tmp"))


def test_no_cache_fetches_and_creates_it(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    monkeypatch.setattr(pl, "_fetch_models_json", lambda timeout=0: BODY)
    assert pl.get_price_list(NOW, cache_path=cache) is not None
    assert cache.exists()


def test_network_failure_returns_the_old_cache_with_its_date_and_warns(
    monkeypatch: pytest.MonkeyPatch, cache: Path, warnings_seen: list[tuple[int, str]]
) -> None:
    old = NOW - timedelta(days=3)
    _write_cache(cache, old)
    _network_forbidden(monkeypatch)
    result = pl.get_price_list(NOW, cache_path=cache)
    assert result is not None
    assert result.source == "cache" and result.fetched_at == old.isoformat()
    assert (logging.WARNING, "price_list_fetch_failed") in warnings_seen


def test_no_cache_and_no_network_returns_none(
    monkeypatch: pytest.MonkeyPatch, cache: Path, warnings_seen: list[tuple[int, str]]
) -> None:
    _network_forbidden(monkeypatch)
    assert pl.get_price_list(NOW, cache_path=cache) is None
    assert (logging.WARNING, "price_list_fetch_failed") in warnings_seen


def test_empty_response_is_a_failure_not_an_empty_price_list(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    _write_cache(cache, NOW - timedelta(days=2))
    monkeypatch.setattr(pl, "_fetch_models_json", lambda timeout=0: {"data": []})
    result = pl.get_price_list(NOW, cache_path=cache)
    assert result is not None and result.source == "cache"


def test_corrupt_cache_is_treated_as_missing(monkeypatch: pytest.MonkeyPatch, cache: Path) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(pl, "_fetch_models_json", lambda timeout=0: BODY)
    result = pl.get_price_list(NOW, cache_path=cache)
    assert result is not None and result.source == "network"


def test_native_provider_models_are_not_priced() -> None:
    prices = pl.PriceList("2026-11-09T00:00:00+00:00", "cache", {"anthropic/claude-haiku-5.5": (0.1, 0.5)})
    assert prices.price_for("anthropic/claude-haiku-5.5") == (0.1, 0.5)
    assert prices.price_for("openrouter:anthropic/claude-haiku-5.5") == (0.1, 0.5)
    assert prices.price_for("anthropic:claude-haiku-5.5") is None
    assert prices.price_for("openai:gpt-5.4") is None


def test_default_cache_lives_under_the_run_directory() -> None:
    path = pl.default_cache_path()
    assert path.parts[-2:] == ("price_list", "openrouter_models.json")
