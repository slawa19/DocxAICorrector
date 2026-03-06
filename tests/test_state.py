import state


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def test_set_processing_status_preserves_started_at_while_running(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.init_session_state()

    timestamps = iter([1000.0, 1001.0, 1002.0])
    monkeypatch.setattr(state.time, "time", lambda: next(timestamps))

    state.set_processing_status(stage="start", detail="first", is_running=True, progress=0.1)
    first_started_at = session_state.processing_status["started_at"]

    state.set_processing_status(stage="continue", detail="second", is_running=True, progress=0.5)

    assert first_started_at == 1001.0
    assert session_state.processing_status["started_at"] == first_started_at
    assert session_state.processing_status["last_update_at"] == 1002.0


def test_append_log_keeps_only_last_thirty_entries(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.init_session_state()

    for index in range(35):
        state.append_log("OK", index, 35, 10, 5, f"entry-{index}")

    assert len(session_state.run_log) == 30
    assert session_state.run_log[0]["details"] == "entry-5"
    assert session_state.run_log[-1]["details"] == "entry-34"