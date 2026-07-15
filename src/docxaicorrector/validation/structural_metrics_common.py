"""Common metric coercion helpers extracted from ``validation/structural.py`` (spec 034, Step 0m).

Pure leaf helpers with no dependency on the ``structural`` orchestration module. Hoisted
first so later leaf modules can depend on them without introducing an import cycle. Bodies
are byte-identical to their former in-module definitions; ``structural`` re-exports them so
``structural._as_int`` / ``from ...structural import _as_int`` keep resolving.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast


def _as_int(metrics: Mapping[str, object], key: str) -> int:
    return int(cast(int, metrics.get(key, 0) or 0))


def _as_float(metrics: Mapping[str, object], key: str) -> float:
    return float(cast(float, metrics[key]))
