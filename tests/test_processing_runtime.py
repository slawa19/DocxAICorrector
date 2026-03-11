import queue

import processing_runtime
import state
from runtime_events import (
    AppendImageLogEvent,
    AppendLogEvent,
    FinalizeProcessingStatusEvent,
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


def test_drain_processing_events_moves_restart_source_to_completed_cache_on_success(monkeypatch):
    session_state = SessionState(
        processing_event_queue=queue.Queue(),
        restart_source={"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "restart.bin"},
        processing_worker=object(),
        processing_stop_event=object(),
        processing_stop_requested=True,
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(processing_runtime, "load_restart_source_bytes", lambda restart_source: b"abc")
    cleared = []
    monkeypatch.setattr(processing_runtime, "clear_restart_source", lambda restart_source: cleared.append(restart_source))

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
        "source_bytes": b"abc",
        "size": 3,
    }
    assert session_state.restart_source is None
    assert cleared == [{"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "restart.bin"}]


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