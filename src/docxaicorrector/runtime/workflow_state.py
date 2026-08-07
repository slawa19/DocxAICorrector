from collections.abc import Mapping
from enum import StrEnum


class ProcessingOutcome(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    SUCCEEDED = "succeeded"


class IdleViewState(StrEnum):
    EMPTY = "empty"
    FILE_SELECTED = "file_selected"
    RESTARTABLE = "restartable"
    COMPLETED = "completed"


def has_restartable_outcome(outcome: str | None) -> bool:
    return outcome in {ProcessingOutcome.STOPPED.value, ProcessingOutcome.FAILED.value}


def preparation_start_discards_delivered_result(*, current_result, uploaded_file_token: str) -> bool:
    """True when starting preparation for ``uploaded_file_token`` destroys a delivered result.

    ``start_background_preparation`` opens with an unconditional
    ``reset_run_state(keep_restart_source=False)``, so every start wipes the ``latest_*``
    delivery. That is a LOSS only when the delivered result was produced from the very
    source that is about to be re-prepared: a different upload is the user replacing the
    document (a legitimate reset), and a run that ended without a downloadable artifact —
    never started, failed, stopped, or refused delivery — has nothing to lose.

    The rule is keyed on state (which source the delivery belongs to, whether it carries an
    artifact), not on which setting the user touched.
    """
    if not isinstance(current_result, Mapping):
        return False
    result_source_token = str(current_result.get("source_token") or "")
    if not result_source_token or result_source_token != str(uploaded_file_token or ""):
        return False
    return bool(current_result.get("docx_bytes")) or bool(current_result.get("narration_text"))


def derive_idle_view_state(*, current_result, uploaded_file, has_restartable_source: bool) -> IdleViewState:
    if uploaded_file is not None:
        return IdleViewState.FILE_SELECTED
    if current_result:
        return IdleViewState.COMPLETED
    if has_restartable_source:
        return IdleViewState.RESTARTABLE
    return IdleViewState.EMPTY
