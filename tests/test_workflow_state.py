from workflow_state import IdleViewState, ProcessingOutcome, derive_idle_view_state, has_restartable_outcome


def test_has_restartable_outcome_accepts_stopped_and_failed():
    assert has_restartable_outcome(ProcessingOutcome.STOPPED.value) is True
    assert has_restartable_outcome(ProcessingOutcome.FAILED.value) is True
    assert has_restartable_outcome(ProcessingOutcome.IDLE.value) is False
    assert has_restartable_outcome(ProcessingOutcome.SUCCEEDED.value) is False


def test_derive_idle_view_state_selects_expected_branch():
    assert derive_idle_view_state(current_result=None, uploaded_file=object(), has_restartable_source=False) == IdleViewState.FILE_SELECTED
    assert derive_idle_view_state(current_result={"docx_bytes": b"x"}, uploaded_file=None, has_restartable_source=False) == IdleViewState.COMPLETED
    assert derive_idle_view_state(current_result=None, uploaded_file=None, has_restartable_source=True) == IdleViewState.RESTARTABLE
    assert derive_idle_view_state(current_result=None, uploaded_file=None, has_restartable_source=False) == IdleViewState.EMPTY