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
    document (a legitimate reset), and a run that ended carrying nothing — never started,
    failed, or stopped before it produced output — has nothing to lose.

    "Carrying something" is read off the renderer (``ui/_ui.py:render_result_bundle``), not
    guessed: it hands back exactly three payloads — the DOCX when ``docx_bytes`` is present,
    the narration when ``narration_text`` is present, and the markdown, whose download button
    is unconditional. A refused (``blocked``) delivery offers the SAME three, relabelled as
    diagnostics; when it has no DOCX the renderer returns before the buttons, but its markdown
    is still the run's output on screen in the preview block, together with the explanation of
    the refusal — the one thing a refused run exists to give the user. So the condition is the
    same for both dispositions and needs no branch on ``blocked``: is any content left to lose.

    The rule is keyed on state (which source the delivery belongs to, what it carries), not on
    which setting the user touched.
    """
    if not isinstance(current_result, Mapping):
        return False
    result_source_token = str(current_result.get("source_token") or "")
    if not result_source_token or result_source_token != str(uploaded_file_token or ""):
        return False
    return (
        bool(current_result.get("docx_bytes"))
        or bool(current_result.get("narration_text"))
        or bool(str(current_result.get("markdown_text") or "").strip())
    )


def derive_idle_view_state(*, current_result, uploaded_file, has_restartable_source: bool) -> IdleViewState:
    if uploaded_file is not None:
        return IdleViewState.FILE_SELECTED
    if current_result:
        return IdleViewState.COMPLETED
    if has_restartable_source:
        return IdleViewState.RESTARTABLE
    return IdleViewState.EMPTY
