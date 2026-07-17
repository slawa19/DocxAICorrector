"""Shared text-call helpers (spec 031).

Behaviour-preserving extraction from ``pipeline/late_phases.py`` of the two pure helpers
shared by the narration/audiobook post-pass (Cluster J) and the reader-cleanup post-pass
(Cluster C): resolving a provider-aware text client for a model selector, and validating
integer fields on a narration-postprocess group. Kept in a tiny module so both consumers
can import them without a cross-cluster dependency. ``late_phases`` re-exports both names.
No module-level mutable state.
"""

from collections.abc import Mapping
from typing import Any


def _resolve_text_call_target(*, selector: str, context: Any, dependencies: Any, fallback_client: object | None) -> tuple[object, str, str, str | None]:
    resolver: Any = getattr(dependencies, "resolve_model_selector", None)
    client_factory: Any = getattr(dependencies, "get_client_for_model_selector", None)
    if not callable(resolver) or not callable(client_factory):
        if fallback_client is None:
            raise RuntimeError("Provider-aware text client factory is unavailable for the requested selector.")
        return fallback_client, selector, selector, None

    resolved_selector: Any = resolver(selector, "responses_text")
    return (
        client_factory(selector, "responses_text"),
        resolved_selector.model_id,
        resolved_selector.canonical_selector,
        resolved_selector.provider,
    )


def _require_group_int(group: Mapping[str, object], key: str) -> int:
    value = group[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Narration postprocess group field '{key}' must be int, got {type(value).__name__}")
    return value
