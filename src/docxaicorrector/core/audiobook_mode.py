"""Spec 070 FR-001 / FR-008: the audiobook mode has no language pair and one model resolver.

Two small rules live here so that the UI, the pipeline and the validation runner cannot decide
them separately (the lesson of spec 069 FR-001: the UI and the runner diverged when each
resolved the model on its own).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeVar

from docxaicorrector.core.logger import log_event

AUDIOBOOK_OPERATION = "audiobook"

_LanguageT = TypeVar("_LanguageT")


def language_pair_for_operation(
    operation: object,
    source_language: _LanguageT,
    target_language: _LanguageT,
) -> tuple[_LanguageT | None, _LanguageT | None]:
    """``(None, None)`` for the audiobook operation, the inputs unchanged for every other one.

    The input of an audiobook run is a document that is already in its final language; a pair
    would be a fabricated fact (``auto -> ru``, ``ru -> ru``) that only steers the language
    rules of other operations. Absence stays absence at every layer below.
    """
    if str(operation or "").strip().casefold() == AUDIOBOOK_OPERATION:
        return None, None
    return source_language, target_language


@dataclass(frozen=True)
class AudiobookModelResolution:
    model: str
    source: Literal["requested", "config"]


def _config_model(app_config: object) -> str:
    value: object = None
    try:
        value = app_config["audiobook_model"]  # type: ignore[index]
    except (KeyError, TypeError, IndexError):
        value = getattr(app_config, "audiobook_model", None)
    return str(value or "").strip()


def resolve_audiobook_model(
    app_config: Mapping[str, object] | object,
    *,
    requested_model: str | None,
    origin: str,
) -> AudiobookModelResolution:
    """The one place that decides the model of an audiobook run (UI and runner).

    Order: a non-empty ``requested_model`` (the user's audiobook choice in the UI, the run
    profile's model in the runner) -> ``app_config["audiobook_model"]``, which the config
    loader has already resolved as ``[models.audiobook].default`` and, without that section,
    ``[models.text].default``.
    """
    requested = str(requested_model or "").strip()
    if requested:
        resolution = AudiobookModelResolution(model=requested, source="requested")
    else:
        configured = _config_model(app_config)
        if not configured:
            # A config that carries no resolved audiobook model (a hand-built mapping): the
            # third step of the chain, the shared text default. The loader already folds this in.
            from docxaicorrector.core.config import get_text_model_default

            configured = str(get_text_model_default(app_config) or "").strip()
        if not configured:
            raise RuntimeError("Не задана модель режима audiobook: ни выбор пользователя, ни [models.audiobook]/[models.text].")
        resolution = AudiobookModelResolution(model=configured, source="config")
    log_event(
        logging.DEBUG,
        "audiobook_model_resolved",
        "Выбрана модель режима audiobook.",
        origin=origin,
        model=resolution.model,
        source=resolution.source,
    )
    return resolution
