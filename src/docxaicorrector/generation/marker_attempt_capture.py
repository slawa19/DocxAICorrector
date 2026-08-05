"""Persist the answer a marker-validation attempt REJECTED, at the moment of rejection.

Why this exists at all (spec 056, decision D'). ``pipeline/support.write_marker_diagnostics_artifact``
already records a ``raw_response_preview``, but it is reachable only from
``handle_block_generation_failure`` — the path where a block *raises*. When the retry budget
is spent and ``generate_markdown_block`` takes its controlled source-text fallback it
returns a plain string, so the call site holds neither the rejected answer nor the
exception, and nothing is written. The 2026-08-04 audiobook run therefore cost real money
and left **no record of what the model actually answered** for the six blocks it dropped;
every claim about which paragraph emptied had to be inferred from an error code.

Reusing that writer was considered and refused. It truncates to 1000/600 characters, keeps
only the LAST exception, and writes into the formatting-diagnostics feed consumed by
``formatting_diagnostics_feedback.py`` — so a rejected attempt landing there would be read
back as formatting evidence. This family has its own schema, its own directory and its own
retention budget, and nothing else consumes it: it is a forensic record for a human.

Retention follows the ``CONTROLLED_BLOCK_FALLBACK_DIR`` pattern (``pipeline/block_execution.py``):
uuid-suffixed files that never overwrite, pruned by age AND count right after each write.
The contract is registered in ``docs/LOGGING_AND_ARTIFACT_RETENTION.md`` §5.1.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from docxaicorrector.core.logger import log_event
from docxaicorrector.runtime.artifact_retention import (
    MARKER_ATTEMPT_ARTIFACTS_MAX_AGE_SECONDS,
    MARKER_ATTEMPT_ARTIFACTS_MAX_COUNT,
    prune_artifact_dir,
)


MARKER_ATTEMPT_DIAGNOSTICS_DIR = Path(".run") / "marker_attempts"
MARKER_ATTEMPT_ARTIFACT_SCHEMA_VERSION = 1
MARKER_ATTEMPT_REJECTED_EVENT = "marker_attempt_rejected"


def get_marker_attempt_diagnostics_dir() -> Path:
    return MARKER_ATTEMPT_DIAGNOSTICS_DIR


def write_marker_attempt_artifact(
    *,
    block_index: int | None,
    attempt: int,
    max_attempts: int,
    stage: str,
    error_code: str,
    expected_paragraph_ids: Sequence[str] | None,
    found_paragraph_ids: Sequence[str] | None,
    raw_response: str,
    leading_text: str = "",
    target_chars: int = 0,
) -> str | None:
    """Write ONE rejected attempt to disk and return its path, or ``None`` on I/O failure.

    ``raw_response`` is stored in FULL and deliberately so: the whole point of the record
    is that a later reader can replay the exact answer offline instead of paying for
    another run. Nothing downstream consumes this directory, so size is bounded by the
    retention budget rather than by truncation.

    Never raises. Losing a diagnostic must not take down the generation it observes.
    """

    payload: dict[str, object] = {
        "schema_version": MARKER_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
        "block_index": block_index,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "stage": stage,
        "error_code": error_code,
        "expected_paragraph_ids": list(expected_paragraph_ids or []),
        "found_paragraph_ids": list(found_paragraph_ids or []),
        "target_chars": target_chars,
        "raw_response_chars": len(raw_response),
        "raw_response": raw_response,
        "leading_text": leading_text,
        "note": (
            "Model answer REJECTED by paragraph-marker validation. Kept verbatim so the "
            "attempt can be replayed offline; no pipeline stage reads this directory."
        ),
    }
    try:
        MARKER_ATTEMPT_DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
        block_component = "unknown" if block_index is None else f"{block_index:03d}"
        artifact_path = (
            MARKER_ATTEMPT_DIAGNOSTICS_DIR
            / f"marker_attempt_block_{block_component}_a{attempt:02d}_{uuid4().hex[:8]}.json"
        )
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_artifact_dir(
            target_dir=MARKER_ATTEMPT_DIAGNOSTICS_DIR,
            max_age_seconds=MARKER_ATTEMPT_ARTIFACTS_MAX_AGE_SECONDS,
            max_count=MARKER_ATTEMPT_ARTIFACTS_MAX_COUNT,
            glob="*.json",
            emit_log=False,
        )
        return str(artifact_path)
    except (OSError, ValueError, TypeError):
        return None


def capture_rejected_marker_attempt(
    *,
    block_index: int | None,
    attempt: int,
    max_attempts: int,
    stage: str,
    error_code: str,
    expected_paragraph_ids: Sequence[str] | None,
    found_paragraph_ids: Sequence[str] | None,
    raw_response: str,
    leading_text: str = "",
    target_chars: int = 0,
) -> str | None:
    """Persist the rejected attempt and announce it. Returns the artifact path or ``None``.

    The log line carries the ids and the code — never the model payload
    (LOGGING_AND_ARTIFACT_RETENTION §1.5); the answer itself lives in the artifact.
    """

    artifact_path = write_marker_attempt_artifact(
        block_index=block_index,
        attempt=attempt,
        max_attempts=max_attempts,
        stage=stage,
        error_code=error_code,
        expected_paragraph_ids=expected_paragraph_ids,
        found_paragraph_ids=found_paragraph_ids,
        raw_response=raw_response,
        leading_text=leading_text,
        target_chars=target_chars,
    )
    try:
        log_event(
            logging.WARNING,
            MARKER_ATTEMPT_REJECTED_EVENT,
            "Ответ модели отклонён проверкой маркеров абзацев; ответ сохранён для офлайн-разбора.",
            block_index=block_index,
            attempt=attempt,
            max_attempts=max_attempts,
            stage=stage,
            error_code=error_code,
            expected_paragraph_ids=list(expected_paragraph_ids or []),
            found_paragraph_ids=list(found_paragraph_ids or []),
            raw_response_chars=len(raw_response),
            target_chars=target_chars,
            artifact_path=artifact_path,
        )
    except Exception:
        pass
    return artifact_path
