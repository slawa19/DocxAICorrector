from pathlib import Path
from types import SimpleNamespace

import application_flow
import preparation
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
    session_state = SessionState(
        selected_source_token="",
        prepared_source_key="",
        completed_source={"filename": "report.docx", "token": "report.docx:3:ba7816bf8f01cfea", "storage_path": "completed.bin"},
    )
    logged = []
    progress_events = []

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=["img"],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="report.docx:hash:6000",
        cached=False,
    )

    result = application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("report.docx", b"abc"),
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected critical error")),
        log_event_fn=lambda *args, **kwargs: logged.append((args, kwargs)),
        prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
        progress_callback=lambda **payload: progress_events.append(payload),
    )

    assert result.uploaded_filename == "report.docx"
    assert result.uploaded_file_bytes == b"abc"
    assert result.uploaded_file_token.startswith("report.docx:3:")
    assert result.jobs == prepared_document.jobs
    assert result.preparation_stage == "Документ подготовлен"
    assert result.preparation_detail == "Анализ завершён. Можно запускать обработку."
    assert result.preparation_cached is False
    assert result.preparation_elapsed_seconds >= 0.0
    assert session_state.selected_source_token == result.uploaded_file_token
    assert session_state.prepared_source_key == "report.docx:hash:6000"
    assert session_state.completed_source is None
    assert len(logged) == 1
    assert progress_events[0]["stage"] == "Чтение файла"
    assert progress_events[1]["metrics"]["file_size_bytes"] == 3
    assert progress_events[-1]["stage"] == "Документ подготовлен"
    assert progress_events[-1]["metrics"]["block_count"] == 1


def test_prepare_run_context_raises_on_empty_job_target():
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    failures = []

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "   ", "target_chars": 0, "context_chars": 0}],
        prepared_source_key="prepared-key",
        cached=False,
    )

    def fail_critical_stub(event, message, **context):
        failures.append((event, message, context))
        raise RuntimeError(message)

    try:
        application_flow.prepare_run_context(
            uploaded_file=UploadedFileStub("report.docx", b"abc"),
            chunk_size=6000,
            image_mode="safe",
            keep_all_image_variants=True,
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


def test_prepare_run_context_keeps_other_completed_source_tokens():
    session_state = SessionState(
        selected_source_token="",
        prepared_source_key="",
        completed_source={"filename": "other.docx", "token": "other.docx:3:def", "storage_path": "other.bin"},
    )

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=["img"],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="report.docx:hash:6000",
        cached=False,
    )

    application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("report.docx", b"abc"),
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected critical error")),
        log_event_fn=lambda *args, **kwargs: None,
        prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
    )

    assert session_state.completed_source == {"filename": "other.docx", "token": "other.docx:3:def", "storage_path": "other.bin"}


def test_get_cached_completed_file_loads_bytes_from_store():
    session_state = SessionState(completed_source={"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "completed.bin"})

    uploaded_file = application_flow.get_cached_completed_file(
        session_state=session_state,
        load_completed_source_bytes_fn=lambda source: b"abc",
    )

    assert uploaded_file is not None
    assert uploaded_file.name == "report.docx"
    assert uploaded_file.getvalue() == b"abc"


def test_consume_completed_source_if_used_clears_persisted_file(monkeypatch):
    session_state = SessionState(completed_source={"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "completed.bin"})
    cleared = []
    monkeypatch.setattr(application_flow, "clear_restart_source", lambda source: cleared.append(source))

    application_flow.consume_completed_source_if_used(session_state=session_state, uploaded_file_token="report.docx:3:abc")

    assert session_state.completed_source is None
    assert cleared == [{"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "completed.bin"}]


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


def test_prepare_run_context_for_background_uses_real_cache(monkeypatch):
    preparation.clear_preparation_cache()
    calls = {"extract": 0}
    progress_events = []

    def fake_extract(uploaded_file):
        calls["extract"] += 1
        return ["paragraph"], []

    monkeypatch.setattr(preparation, "extract_document_content_from_docx", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])

    uploaded_file = UploadedFileStub("report.docx", b"abc")
    application_flow.prepare_run_context_for_background(
        uploaded_file=uploaded_file,
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        progress_callback=lambda **payload: progress_events.append(payload),
    )
    second = application_flow.prepare_run_context_for_background(
        uploaded_file=uploaded_file,
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        progress_callback=lambda **payload: progress_events.append(payload),
    )

    assert calls["extract"] == 1
    assert second.prepared_source_key.endswith(":6000")
    assert second.preparation_cached is True
    assert second.preparation_stage == "Документ подготовлен"
    assert progress_events[-1]["stage"] == "Документ подготовлен"
    assert progress_events[-1]["metrics"]["cached"] is True