"""Shared text-call helpers (spec 031).

Behaviour-preserving extraction from ``pipeline/late_phases.py`` of the pure helper used by
the reader-cleanup post-pass (Cluster C): resolving a provider-aware text client for a model
selector. (The narration post-pass that shared it, and its group-field helper, were removed
by spec 070.) ``late_phases`` re-exports the name. No module-level mutable state.
"""

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
