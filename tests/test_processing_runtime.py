import queue

import processing_runtime
import state
from runtime_events import (
    AppendImageLogEvent,
    AppendLogEvent,
    FinalizeProcessingStatusEvent,
    PreparationCompleteEvent,
    PreparationFailedEvent,
    PushActivityEvent,
    ResetImageStateEvent,
    SetProcessingStatusEvent,
    SetStateEvent,
    WorkerCompleteEvent,
)


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def test_drain_processing_events_applies_typed_runtime_events(monkeypatch):
    session_state = SessionState(
        processing_event_queue=queue.Queue(),
        image_assets=["stale"],
        image_validation_failures=["stale"],
        restart_source=None,
        processing_worker=object(),
        processing_stop_event=object(),
        processing_stop_requested=True,
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)

    calls = {
        "status": [],
        "finalize": [],
        "activity": [],
        "log": [],
        "image_log": [],
    }

    session_state.processing_event_queue.put(SetStateEvent(values={"last_error": "boom"}))
    session_state.processing_event_queue.put(ResetImageStateEvent())
    session_state.processing_event_queue.put(SetProcessingStatusEvent(payload={"stage": "run", "detail": "detail"}))
    session_state.processing_event_queue.put(FinalizeProcessingStatusEvent(stage="done", detail="ok", progress=1.0))
    session_state.processing_event_queue.put(PushActivityEvent(message="hello"))
    session_state.processing_event_queue.put(AppendLogEvent(payload={"status": "OK", "block_index": 1, "block_count": 2, "target_chars": 3, "context_chars": 4, "details": "done"}))
    session_state.processing_event_queue.put(AppendImageLogEvent(payload={"image_id": "img_1", "status": "validated", "decision": "accept", "confidence": 0.9}))
    session_state.processing_event_queue.put(WorkerCompleteEvent(outcome="succeeded"))

    processing_runtime.drain_processing_events(
        set_processing_status=lambda **payload: calls["status"].append(payload),
        finalize_processing_status=lambda stage, detail, progress: calls["finalize"].append((stage, detail, progress)),
        push_activity=lambda message: calls["activity"].append(message),
        append_log=lambda **payload: calls["log"].append(payload),
        append_image_log=lambda **payload: calls["image_log"].append(payload),
    )

    assert session_state.last_error == "boom"
    assert session_state.image_assets == []
    assert session_state.image_validation_failures == []
    assert calls["status"] == [{"stage": "run", "detail": "detail"}]
    assert calls["finalize"] == [("done", "ok", 1.0)]
    assert calls["activity"] == ["hello"]
    assert calls["log"][0]["status"] == "OK"
    assert calls["image_log"][0]["image_id"] == "img_1"
    assert session_state.processing_outcome == "succeeded"
    assert session_state.processing_worker is None
    assert session_state.processing_event_queue is None
    assert session_state.processing_stop_event is None
    assert session_state.processing_stop_requested is False


def test_drain_preparation_events_stores_prepared_context(monkeypatch):
    prepared_run_context = type("PreparedRunContextStub", (), {
        "uploaded_file_token": "report.docx:3:abc",
        "prepared_source_key": "report.docx:3:abc:6000",
    })()
    session_state = SessionState(
        preparation_event_queue=queue.Queue(),
        preparation_worker=object(),
        selected_source_token="",
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    finalized = []

    session_state.preparation_event_queue.put(
        PreparationCompleteEvent(prepared_run_context=prepared_run_context, upload_marker="report.docx:3")
    )

    processing_runtime.drain_preparation_events(
        reset_run_state=lambda **kwargs: None,
        set_processing_status=lambda **payload: None,
        finalize_processing_status=lambda stage, detail, progress: finalized.append((stage, detail, progress)),
        push_activity=lambda message: None,
    )

    assert session_state.prepared_run_context is prepared_run_context
    assert session_state.preparation_input_marker == "report.docx:3"
    assert session_state.selected_source_token == "report.docx:3:abc"
    assert session_state.preparation_worker is None
    assert session_state.preparation_event_queue is None
    assert finalized == [("Документ подготовлен", "Анализ файла завершён. Можно запускать обработку.", 1.0)]


def test_drain_preparation_events_marks_failure(monkeypatch):
    session_state = SessionState(
        preparation_event_queue=queue.Queue(),
        preparation_worker=object(),
        last_error="",
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    finalized = []
    activities = []

    session_state.preparation_event_queue.put(
        PreparationFailedEvent(upload_marker="report.docx:3", error_message="boom")
    )

    processing_runtime.drain_preparation_events(
        reset_run_state=lambda **kwargs: None,
        set_processing_status=lambda **payload: None,
        finalize_processing_status=lambda stage, detail, progress: finalized.append((stage, detail, progress)),
        push_activity=lambda message: activities.append(message),
    )

    assert session_state.prepared_run_context is None
    assert session_state.preparation_failed_marker == "report.docx:3"
    assert session_state.last_error == "boom"
    assert session_state.preparation_worker is None
    assert session_state.preparation_event_queue is None
    assert finalized == [("Ошибка подготовки", "boom", 1.0)]
    assert activities == ["Не удалось прочитать и проанализировать DOCX-файл."]


def test_start_background_preparation_creates_worker_and_status(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    statuses = []
    activities = []

    processing_runtime.start_background_preparation(
        worker_target=lambda **kwargs: None,
        reset_run_state=lambda **kwargs: None,
        push_activity=lambda message: activities.append(message),
        set_processing_status=lambda **payload: statuses.append(payload),
        uploaded_file=type("UploadedFileStub", (), {"name": "report.docx", "size": 3, "getvalue": lambda self: b"abc"})(),
        upload_marker="report.docx:3",
        chunk_size=6000,
        image_mode="safe",
        enable_post_redraw_validation=True,
    )

    session_state.preparation_worker.join(timeout=5)

    assert session_state.preparation_input_marker == "report.docx:3"
    assert session_state.preparation_event_queue is not None
    assert session_state.preparation_worker is not None
    assert statuses[0]["phase"] == "preparing"
    assert statuses[0]["stage"] == "Файл получен"
    assert activities == ["Файл получен сервером. Запускаю анализ DOCX."]


def test_start_background_preparation_propagates_cached_flag(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    statuses = []
    activities = []

    def worker_target(**kwargs):
        kwargs["progress_callback"](
            stage="Подготовка документа",
            detail="cache hit",
            progress=0.9,
            metrics={"cached": True, "block_count": 5, "paragraph_count": 10, "image_count": 1, "source_chars": 2000},
        )

    processing_runtime.start_background_preparation(
        worker_target=worker_target,
        reset_run_state=lambda **kwargs: None,
        push_activity=lambda message: activities.append(message),
        set_processing_status=lambda **payload: statuses.append(payload),
        uploaded_file=type("UploadedFileStub", (), {"name": "report.docx", "size": 3, "getvalue": lambda self: b"abc"})(),
        upload_marker="report.docx:3:6000",
        chunk_size=6000,
        image_mode="safe",
        enable_post_redraw_validation=True,
    )

    session_state.preparation_worker.join(timeout=5)
    processing_runtime.drain_preparation_events(
        reset_run_state=lambda **kwargs: None,
        set_processing_status=lambda **payload: statuses.append(payload),
        finalize_processing_status=lambda stage, detail, progress: None,
        push_activity=lambda message: activities.append(message),
    )
    assert any(payload.get("cached") is True for payload in statuses)
    assert "[Анализ] Подготовка документа: cache hit" in activities


def test_drain_processing_events_moves_restart_source_to_completed_cache_on_success(monkeypatch):
    session_state = SessionState(
        processing_event_queue=queue.Queue(),
        restart_source={"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "restart.bin", "session_id": "session-a"},
        processing_worker=object(),
        processing_stop_event=object(),
        processing_stop_requested=True,
        restart_session_id="session-a",
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(processing_runtime, "load_restart_source_bytes", lambda restart_source: b"abc")
    cleared = []
    monkeypatch.setattr(processing_runtime, "clear_restart_source", lambda restart_source: cleared.append(restart_source))
    monkeypatch.setattr(
        processing_runtime,
        "store_completed_source",
        lambda **kwargs: {
            "filename": kwargs["source_name"],
            "token": kwargs["source_token"],
            "storage_path": "completed.bin",
            "size": len(kwargs["source_bytes"]),
            "session_id": kwargs["session_id"],
            "storage_kind": "completed",
        },
    )

    session_state.processing_event_queue.put(WorkerCompleteEvent(outcome="succeeded"))

    processing_runtime.drain_processing_events(
        set_processing_status=lambda **payload: None,
        finalize_processing_status=lambda stage, detail, progress: None,
        push_activity=lambda message: None,
        append_log=lambda **payload: None,
        append_image_log=lambda **payload: None,
    )

    assert session_state.completed_source == {
        "filename": "report.docx",
        "token": "report.docx:3:abc",
        "storage_path": "completed.bin",
        "size": 3,
        "session_id": "session-a",
        "storage_kind": "completed",
    }
    assert session_state.restart_source is None
    assert cleared == [{"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "restart.bin", "session_id": "session-a"}]


def test_drain_processing_events_skips_completed_cache_for_large_sources(monkeypatch):
    session_state = SessionState(
        processing_event_queue=queue.Queue(),
        restart_source={"filename": "report.docx", "token": "report.docx:12:abc", "storage_path": "restart.bin", "session_id": "session-a"},
        processing_worker=object(),
        processing_stop_event=object(),
        processing_stop_requested=True,
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(processing_runtime, "MAX_COMPLETED_SOURCE_BYTES", 4)
    monkeypatch.setattr(processing_runtime, "load_restart_source_bytes", lambda restart_source: b"abcdef")
    cleared = []
    activities = []
    monkeypatch.setattr(processing_runtime, "clear_restart_source", lambda restart_source: cleared.append(restart_source))

    session_state.processing_event_queue.put(WorkerCompleteEvent(outcome="succeeded"))

    processing_runtime.drain_processing_events(
        set_processing_status=lambda **payload: None,
        finalize_processing_status=lambda stage, detail, progress: None,
        push_activity=lambda message: activities.append(message),
        append_log=lambda **payload: None,
        append_image_log=lambda **payload: None,
    )

    assert session_state.completed_source is None
    assert session_state.restart_source is None
    assert len(activities) == 1
    assert "слишком большой" in activities[0].lower()
    assert cleared == [{"filename": "report.docx", "token": "report.docx:12:abc", "storage_path": "restart.bin", "session_id": "session-a"}]


def test_start_background_processing_degrades_gracefully_when_restart_store_fails(monkeypatch):
    session_state = SessionState(restart_session_id="session-a")
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    state_monkey_session = session_state
    monkeypatch.setattr(state.st, "session_state", state_monkey_session)
    state.init_session_state()
    session_state.restart_session_id = "session-a"

    activity_messages = []
    monkeypatch.setattr(processing_runtime, "store_restart_source", lambda **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    log_events = []
    monkeypatch.setattr(processing_runtime, "log_event", lambda *args, **kwargs: log_events.append((args, kwargs)))

    processing_runtime.start_background_processing(
        worker_target=lambda **kwargs: None,
        reset_run_state=state.reset_run_state,
        push_activity=lambda message: activity_messages.append(message),
        set_processing_status=lambda **kwargs: None,
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

    assert session_state.restart_source is None
    assert session_state.processing_worker is not None
    assert any("restart" in message.lower() for message in activity_messages)
    assert len(log_events) == 1