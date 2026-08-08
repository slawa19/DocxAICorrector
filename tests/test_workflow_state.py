from docxaicorrector.runtime.workflow_state import (
    IdleViewState,
    ProcessingOutcome,
    derive_idle_view_state,
    has_restartable_outcome,
    preparation_start_discards_delivered_result,
)


def _delivered(**overrides):
    payload = {
        "source_token": "report.docx:3:token",
        "docx_bytes": b"paid-docx",
        "narration_text": None,
        "markdown_text": "# paid markdown",
    }
    payload.update(overrides)
    return payload


def test_has_restartable_outcome_accepts_stopped_and_failed():
    assert has_restartable_outcome(ProcessingOutcome.STOPPED.value) is True
    assert has_restartable_outcome(ProcessingOutcome.FAILED.value) is True
    assert has_restartable_outcome(ProcessingOutcome.IDLE.value) is False
    assert has_restartable_outcome(ProcessingOutcome.SUCCEEDED.value) is False


def test_preparation_start_discards_delivered_result_for_the_same_source():
    assert preparation_start_discards_delivered_result(
        current_result=_delivered(),
        uploaded_file_token="report.docx:3:token",
    ) is True
    # An audiobook run delivers narration instead of a DOCX; it is a paid result too.
    assert preparation_start_discards_delivered_result(
        current_result=_delivered(docx_bytes=None, narration_text="narration", markdown_text=""),
        uploaded_file_token="report.docx:3:token",
    ) is True
    # A REFUSED delivery whose only payload is the markdown: the renderer suppresses its
    # download buttons without a DOCX, but the markdown and the refusal explanation are
    # exactly what the user paid the run for, and they are on screen.
    assert preparation_start_discards_delivered_result(
        current_result=_delivered(
            docx_bytes=None,
            markdown_text="# refused output",
            delivery_disposition={"status": "blocked", "explanation": "quality gate"},
        ),
        uploaded_file_token="report.docx:3:token",
    ) is True


def test_preparation_start_discards_nothing_without_a_delivered_result():
    # Nothing delivered yet: the first run of a freshly uploaded file.
    assert preparation_start_discards_delivered_result(
        current_result=None,
        uploaded_file_token="report.docx:3:token",
    ) is False
    # A different document: replacing the upload is a legitimate reset, not a loss.
    assert preparation_start_discards_delivered_result(
        current_result=_delivered(source_token="other.docx:9:othertoken"),
        uploaded_file_token="report.docx:3:token",
    ) is False
    # A run that ended carrying nothing at all: no DOCX, no narration, no markdown. The
    # screen holds no download button and no output text, so there is nothing to lose.
    assert preparation_start_discards_delivered_result(
        current_result=_delivered(docx_bytes=None, markdown_text=""),
        uploaded_file_token="report.docx:3:token",
    ) is False
    # Same, for a refused delivery that was blocked before it produced any markdown: the
    # explanation renders, but no payload of the run survives to be destroyed.
    assert preparation_start_discards_delivered_result(
        current_result=_delivered(
            docx_bytes=None,
            markdown_text="   ",
            delivery_disposition={"status": "blocked", "explanation": "quality gate"},
        ),
        uploaded_file_token="report.docx:3:token",
    ) is False
    # No identity on either side is no evidence of a same-source loss.
    assert preparation_start_discards_delivered_result(
        current_result=_delivered(source_token=""),
        uploaded_file_token="",
    ) is False


def test_derive_idle_view_state_selects_expected_branch():
    assert derive_idle_view_state(current_result=None, uploaded_file=object(), has_restartable_source=False) == IdleViewState.FILE_SELECTED
    assert derive_idle_view_state(current_result={"docx_bytes": b"x"}, uploaded_file=None, has_restartable_source=False) == IdleViewState.COMPLETED
    assert derive_idle_view_state(current_result=None, uploaded_file=None, has_restartable_source=True) == IdleViewState.RESTARTABLE
    assert derive_idle_view_state(current_result=None, uploaded_file=None, has_restartable_source=False) == IdleViewState.EMPTY
