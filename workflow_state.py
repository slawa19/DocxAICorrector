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


def derive_idle_view_state(*, current_result, uploaded_file, has_restartable_source: bool) -> IdleViewState:
    if uploaded_file is not None:
        return IdleViewState.FILE_SELECTED
    if current_result:
        return IdleViewState.COMPLETED
    if has_restartable_source:
        return IdleViewState.RESTARTABLE
    return IdleViewState.EMPTY