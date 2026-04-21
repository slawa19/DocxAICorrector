import app
from runtime_artifacts import AppReadyMarkerWriter
from conftest import SessionState as SessionState


class FakeColumn:
    def __init__(self, result=False):
        self.result = result
        self.calls = []

    def button(self, label, **kwargs):
        self.calls.append((label, kwargs))
        return self.result


def test_main_logs_app_start_only_once(monkeypatch):
    session_state = SessionState(app_start_logged=False)
    logged_events = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: session_state.setdefault("app_start_logged", False))
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
    monkeypatch.setattr(app, "log_event", lambda *args, **kwargs: logged_events.append((args, kwargs)))
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", True))
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)

    app.main()
    app.main()

    assert len(logged_events) == 1
    assert session_state.app_start_logged is True


def test_schedule_stale_persisted_sources_cleanup_resets_flag_under_lock(monkeypatch):
    session_state = SessionState(persisted_source_cleanup_done=False)
    lock_events = []

    class TrackingLock:
        def __enter__(self):
            lock_events.append("enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            lock_events.append("exit")

    class ImmediateThread:
        def __init__(self, *, target, daemon, name):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "_CLEANUP_THREAD_LOCK", TrackingLock())
    monkeypatch.setattr(app, "_CLEANUP_THREAD_STARTED", False)
    monkeypatch.setattr(app.threading, "Thread", ImmediateThread)

    import restart_store

    cleanup_calls = []
    monkeypatch.setattr(restart_store, "cleanup_stale_persisted_sources", lambda **kwargs: cleanup_calls.append(kwargs))

    app._schedule_stale_persisted_sources_cleanup()

    assert cleanup_calls == [{"max_age_seconds": app.PERSISTED_SOURCE_TTL_SECONDS}]
    assert app._CLEANUP_THREAD_STARTED is False
    assert lock_events == ["enter", "exit", "enter", "exit"]


def test_app_ready_marker_writer_throttles_repeated_writes_within_window(tmp_path):
    ready_path = tmp_path / ".run" / "app.ready"
    time_values = iter([100.0, 105.0, 116.0])
    writer = AppReadyMarkerWriter(
        path=ready_path,
        freshness_window_seconds=15.0,
        time_fn=lambda: next(time_values),
    )

    assert writer.mark_ready() is True
    first_contents = ready_path.read_text(encoding="utf-8")

    assert writer.mark_ready() is False
    assert ready_path.read_text(encoding="utf-8") == first_contents

    assert writer.mark_ready() is True
    assert ready_path.read_text(encoding="utf-8") == "116.000000\n"


def test_mark_app_ready_uses_shared_throttled_writer(monkeypatch):
    calls = []

    class WriterStub:
        def mark_ready(self):
            calls.append("mark_ready")
            return False

    monkeypatch.setattr(app, "_APP_READY_MARKER_WRITER", WriterStub())

    app._mark_app_ready()

    assert calls == ["mark_ready"]


def test_render_processing_controls_keeps_start_visible_while_processing(monkeypatch):
    session_state = SessionState(processing_stop_requested=False)
    start_column = FakeColumn(result=False)
    stop_column = FakeColumn(result=False)

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [start_column, stop_column])
    action = app._render_processing_controls(can_start=False, is_processing=True)

    assert action is None
    assert start_column.calls == [(
        "Обработка запущена",
        {
            "type": "primary",
            "use_container_width": True,
            "disabled": True,
            "key": "start_processing_button",
        },
    )]
    assert stop_column.calls == [(
        "Стоп",
        {
            "use_container_width": True,
            "disabled": False,
            "key": "stop_processing_button",
        },
    )]


def test_render_processing_controls_enables_start_and_disables_stop_when_idle(monkeypatch):
    session_state = SessionState(processing_stop_requested=False)
    start_column = FakeColumn(result=True)
    stop_column = FakeColumn(result=False)

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [start_column, stop_column])
    action = app._render_processing_controls(can_start=True, is_processing=False)

    assert action == "start"
    assert start_column.calls == [(
        "Начать обработку",
        {
            "type": "primary",
            "use_container_width": True,
            "disabled": False,
            "key": "start_processing_button",
        },
    )]
    assert stop_column.calls == []


def test_render_processing_controls_demotes_start_after_completed_result(monkeypatch):
    session_state = SessionState(processing_stop_requested=False)
    start_column = FakeColumn(result=False)
    stop_column = FakeColumn(result=False)

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [start_column, stop_column])
    action = app._render_processing_controls(can_start=True, is_processing=False, emphasize_start=False)

    assert action is None
    assert start_column.calls == [(
        "Обработать повторно",
        {
            "type": "secondary",
            "use_container_width": True,
            "disabled": False,
            "key": "start_processing_button",
        },
    )]
    assert stop_column.calls == [(
        "Стоп",
        {
            "use_container_width": True,
            "disabled": True,
            "key": "stop_processing_button",
        },
    )]