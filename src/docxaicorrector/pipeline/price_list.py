"""OpenRouter price list with a dated on-disk cache (spec 069 FR-007, contracts/cost-estimate.md section 3).

Pure of Streamlit and of ``model_accounting``. ``get_price_list`` is the only entry point:

- a cache younger than 24 hours is returned without touching the network;
- otherwise ``GET https://openrouter.ai/api/v1/models`` with a 5 second timeout; success
  rewrites the cache atomically (tmp + replace);
- a failed fetch returns the last cache with ITS date and logs WARNING ``price_list_fetch_failed``;
- no cache and no network -> ``None`` (the UI shows "price unknown", never zero).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from docxaicorrector.core import constants
from docxaicorrector.core.logger import log_event

PRICE_LIST_SOURCE_URL = "https://openrouter.ai/api/v1/models"
PRICE_LIST_FETCH_TIMEOUT_SECONDS = 5.0
PRICE_LIST_FRESHNESS = timedelta(hours=24)
PRICE_LIST_CACHE_NAME = "openrouter_models.json"

SOURCE_NETWORK = "network"
SOURCE_CACHE = "cache"


@dataclass(frozen=True)
class PriceList:
    """Prices per 1M tokens, ``prices[model_id] = (input_per_1m, output_per_1m)``."""

    fetched_at: str
    source: str
    prices: Mapping[str, tuple[float, float]] = field(default_factory=dict)

    def price_for(self, model_id: str) -> tuple[float, float] | None:
        """OpenRouter price of a model, or None. Native ``anthropic:`` / ``openai:`` models are not
        priced here (they are not on OpenRouter), an ``openrouter:`` prefix is tolerated."""
        model = (model_id or "").strip()
        if model.startswith("openrouter:"):
            model = model[len("openrouter:"):]
        if ":" in model:
            return None
        return self.prices.get(model)


def default_cache_path() -> Path:
    return constants.RUN_DIR / "price_list" / PRICE_LIST_CACHE_NAME


def _per_million(raw: object) -> float | None:
    """Per-token price string -> per 1M tokens without float rounding of the string itself."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value < 0:
        return None
    return float(value * 1_000_000)


def parse_openrouter_models(payload: object) -> dict[str, tuple[float, float]]:
    """``/api/v1/models`` body -> ``{model_id: (input_per_1m, output_per_1m)}``; unpriced entries are skipped."""
    prices: dict[str, tuple[float, float]] = {}
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return prices
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        pricing = item.get("pricing")
        if not isinstance(model_id, str) or not isinstance(pricing, dict):
            continue
        price_in = _per_million(pricing.get("prompt"))
        price_out = _per_million(pricing.get("completion"))
        if price_in is None or price_out is None:
            continue
        prices[model_id] = (price_in, price_out)
    return prices


def _fetch_models_json(timeout: float = PRICE_LIST_FETCH_TIMEOUT_SECONDS) -> Any:
    request = urllib.request.Request(PRICE_LIST_SOURCE_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URL
        return json.loads(response.read().decode("utf-8"))


def _utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def _read_cache(path: Path) -> tuple[datetime, dict[str, tuple[float, float]], str] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        fetched_at_text = raw["fetched_at"]
        fetched_at = _utc(datetime.fromisoformat(str(fetched_at_text).replace("Z", "+00:00")))
        prices = {
            str(model): (float(entry["input_per_1m"]), float(entry["output_per_1m"]))
            for model, entry in raw["prices"].items()
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if not prices:
        return None
    return fetched_at, prices, str(fetched_at_text)


def _write_cache(path: Path, fetched_at: datetime, prices: Mapping[str, tuple[float, float]]) -> None:
    body = {
        "fetched_at": fetched_at.isoformat(),
        "source_url": PRICE_LIST_SOURCE_URL,
        "prices": {model: {"input_per_1m": pin, "output_per_1m": pout} for model, (pin, pout) in prices.items()},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def get_price_list(now: datetime | None = None, *, cache_path: Path | None = None) -> PriceList | None:
    """Price list for the estimate, or None when there is neither a cache nor a network."""
    current = _utc(now) if now is not None else datetime.now(timezone.utc)
    path = cache_path if cache_path is not None else default_cache_path()
    cached = _read_cache(path)
    if cached is not None and current - cached[0] < PRICE_LIST_FRESHNESS:
        return PriceList(fetched_at=cached[2], source=SOURCE_CACHE, prices=cached[1])

    try:
        prices = parse_openrouter_models(_fetch_models_json(PRICE_LIST_FETCH_TIMEOUT_SECONDS))
        if not prices:
            raise ValueError("price list response carried no priced models")
    except Exception as exc:  # noqa: BLE001 - any fetch/parse failure falls back to the cache
        log_event(
            logging.WARNING,
            "price_list_fetch_failed",
            "OpenRouter price list could not be fetched; falling back to the cached copy",
            error=f"{type(exc).__name__}: {exc}",
            cache_fetched_at=cached[2] if cached is not None else None,
            cache_path=str(path),
        )
        if cached is None:
            return None
        return PriceList(fetched_at=cached[2], source=SOURCE_CACHE, prices=cached[1])

    try:
        _write_cache(path, current, prices)
    except OSError as exc:
        log_event(
            logging.WARNING,
            "price_list_cache_write_failed",
            "Price list cache could not be written",
            error=f"{type(exc).__name__}: {exc}",
            cache_path=str(path),
        )
    return PriceList(fetched_at=current.isoformat(), source=SOURCE_NETWORK, prices=prices)
