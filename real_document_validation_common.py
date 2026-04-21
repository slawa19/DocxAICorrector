from __future__ import annotations

from collections.abc import Callable, MutableSequence
from typing import Any


ValidationEventPayload = dict[str, object]
ValidationEventHook = Callable[[ValidationEventPayload], None]


def build_validation_runtime_config(runtime_resolution) -> dict[str, object]:
    return {
        "effective": runtime_resolution.effective.to_dict() if runtime_resolution is not None else None,
        "ui_defaults": runtime_resolution.ui_defaults.to_dict() if runtime_resolution is not None else None,
        "overrides": runtime_resolution.overrides if runtime_resolution is not None else {},
    }


def build_validation_event_logger(
    event_log: MutableSequence[ValidationEventPayload],
    *,
    on_event: ValidationEventHook | None = None,
) -> Callable[..., None]:
    def _log_event(level: int, event_id: str, message: str, **context: object) -> None:
        payload: ValidationEventPayload = {
            "level": level,
            "event_id": event_id,
            "message": message,
            "context": dict(context),
        }
        event_log.append(payload)
        if on_event is not None:
            on_event(payload)

    return _log_event


__all__ = [
    "build_validation_runtime_config",
    "build_validation_event_logger",
]