from pathlib import Path
from types import SimpleNamespace

import application_flow
import processing_runtime
import restart_store
import state


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class UploadedFileStub:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getvalue(self):
        return self._content


def test_prepare_run_context_updates_selected_token_and_prepared_key():
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    logged = []

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=["img"],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="report.docx:hash:6000",
    )

    result = application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("report.docx", b"abc"),
        chunk_size=6000,
        image_mode="safe",
        enable_post_redraw_validation=True,
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected critical error")),
        log_event_fn=lambda *args, **kwargs: logged.append((args, kwargs)),
        prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
    )

    assert result.uploaded_filename == "report.docx"
    assert result.uploaded_file_bytes == b"abc"
    assert result.uploaded_file_token.startswith("report.docx:3:")
    assert result.jobs == prepared_document.jobs
    assert session_state.selected_source_token == result.uploaded_file_token
    assert session_state.prepared_source_key == "report.docx:hash:6000"
    assert len(logged) == 1


def test_prepare_run_context_raises_on_empty_job_target():
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    failures = []

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "   ", "target_chars": 0, "context_chars": 0}],
        prepared_source_key="prepared-key",
    )

    def fail_critical_stub(event, message, **context):
        failures.append((event, message, context))
        raise RuntimeError(message)

    try:
        application_flow.prepare_run_context(
            uploaded_file=UploadedFileStub("report.docx", b"abc"),
            chunk_size=6000,
            image_mode="safe",
            enable_post_redraw_validation=True,
            session_state=session_state,
            reset_run_state_fn=lambda **kwargs: None,
            fail_critical_fn=fail_critical_stub,
            log_event_fn=lambda *args, **kwargs: None,
            prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("prepare_run_context must fail on empty target_text")

    assert failures[0][0] == "empty_target_block"


def test_restart_flow_restores_uploaded_file_from_run_store_and_cleans_up(tmp_path, monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    state.init_session_state()
    session_state.restart_session_id = "session-a"

    processing_runtime.start_background_processing(
        worker_target=lambda **kwargs: None,
        reset_run_state=state.reset_run_state,
        push_activity=state.push_activity,
        set_processing_status=state.set_processing_status,
        uploaded_filename="report.docx",
        uploaded_token="report.docx:3:abc",
        source_bytes=b"abc",
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
    )

    session_state.processing_worker.join(timeout=5)
    session_state.processing_worker = None
    session_state.processing_outcome = "stopped"

    restored_file = application_flow.resolve_effective_uploaded_file(
        uploaded_file=None,
        current_result=None,
        session_state=session_state,
    )

    restart_path = session_state.restart_source["storage_path"]

    assert restored_file is not None
    assert restored_file.name == "report.docx"
    assert restored_file.getvalue() == b"abc"

    state.reset_run_state(keep_restart_source=False)

    assert session_state.restart_source is None
    assert not Path(restart_path).exists()