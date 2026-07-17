"""Event-log context extractors from ``validation/structural.py`` (spec 034, Step 1, Cluster N).

Pure leaf helpers that read typed values out of a validation event log. No dependency on the
``structural`` orchestration module (imports only stdlib / typing). Bodies are byte-identical to
their former in-module definitions; ``structural`` re-exports them so the qualified names keep
resolving.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast


def _extract_event_context(event_log: Sequence[Mapping[str, object]], event_id: str) -> Mapping[str, object]:
    for event in reversed(event_log):
        if str(event.get("event_id") or "") != event_id:
            continue
        context = event.get("context")
        if isinstance(context, Mapping):
            return context
        break
    return {}


def _extract_event_context_value(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> str:
    context = _extract_event_context(event_log, event_id)
    value = context.get(key)
    return "" if value is None else str(value)


def _extract_event_context_list(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> list[str]:
    context = _extract_event_context(event_log, event_id)
    values = context.get(key)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return []
    return [str(value) for value in values]


def _extract_event_context_int(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> int:
    context = _extract_event_context(event_log, event_id)
    value = context.get(key)
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return 0


def _extract_event_context_float(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> float | None:
    context = _extract_event_context(event_log, event_id)
    value = context.get(key)
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _extract_event_context_bool(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> bool:
    context = _extract_event_context(event_log, event_id)
    value = context.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _extract_event_context_int_list(event_log: Sequence[Mapping[str, object]], event_id: str, key: str) -> list[int]:
    context = _extract_event_context(event_log, event_id)
    values = context.get(key)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return []
    result: list[int] = []
    for value in values:
        try:
            result.append(int(cast(Any, value)))
        except (TypeError, ValueError):
            continue
    return result
