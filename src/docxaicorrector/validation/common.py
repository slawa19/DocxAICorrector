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
    forward_event: Callable[..., object] | None = None,
) -> Callable[..., None]:
    """Build the ``log_event_fn`` a validation run injects into the pipeline.

    Every event is appended to ``event_log``, the in-memory list the run's report is built
    from. ``forward_event``, when given, receives the same call
    ``(level, event_id, message, **context)`` as well: the real-document runner passes
    ``docxaicorrector.core.logger.log_event`` there, so the pipeline's injected events reach
    the run's log file the way they reach ``.run/app.log`` in the app (spec 068 FR-002).
    Without it the list is the only sink and the events reach no log at all.
    """

    def _log_event(level: int, event_id: str, message: str, **context: object) -> None:
        payload: ValidationEventPayload = {
            "level": level,
            "event_id": event_id,
            "message": message,
            "context": dict(context),
        }
        event_log.append(payload)
        if forward_event is not None:
            forward_event(level, event_id, message, **context)
        if on_event is not None:
            on_event(payload)

    return _log_event


__all__ = [
    "build_validation_runtime_config",
    "build_validation_event_logger",
]