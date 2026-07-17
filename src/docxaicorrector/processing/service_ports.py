"""UI-free processing-service ports (round-4 finding 5).

Holds the pure, Streamlit-free helpers that ``processing_service`` needs at
import time so importing ``processing_service`` in a headless process never
transitively loads Streamlit. This module MUST NOT import ``streamlit`` (directly
or transitively) and MUST NOT import ``processing_runtime``/``runtime.state`` at
module load time. ``processing_runtime`` re-exports these names for backward
compatibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docxaicorrector.processing.processing_runtime import BackgroundRuntime


def normalize_background_error(
    *,
    stage: str,
    exc: Exception,
    user_message: str,
    severity: str = "error",
    recoverable: bool = False,
) -> dict[str, object]:
    return {
        "stage": stage,
        "severity": severity,
        "user_message": user_message,
        "technical_message": str(exc),
        "error_type": exc.__class__.__name__,
        "recoverable": recoverable,
    }


def should_stop_processing(runtime: "BackgroundRuntime | None") -> bool:
    if runtime is None:
        return False
    return runtime.should_stop()
