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


def test_init_session_state_initializes_image_processing_summary(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.init_session_state()

    assert session_state.image_assets == []
    assert session_state.image_validation_failures == []
    assert session_state.image_processing_summary == {
        "total_images": 0,
        "processed_images": 0,
        "images_validated": 0,
        "validation_passed": 0,
        "fallbacks_applied": 0,
        "validation_errors": [],
    }


def test_append_image_log_updates_summary_and_activity(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.init_session_state()

    state.append_image_log(
        image_id="img-1",
        status="validated",
        decision="accept",
        confidence=0.92,
        missing_labels=[],
        suspicious_reasons=[],
    )
    state.append_image_log(
        image_id="img-2",
        status="error",
        decision="fallback_safe",
        confidence=0.10,
        suspicious_reasons=["validator_exception:RuntimeError"],
    )

    assert session_state.image_processing_summary["total_images"] == 2
    assert session_state.image_processing_summary["processed_images"] == 2
    assert session_state.image_processing_summary["images_validated"] == 1
    assert session_state.image_processing_summary["validation_passed"] == 1
    assert session_state.image_processing_summary["fallbacks_applied"] == 0
    assert session_state.image_processing_summary["validation_errors"] == ["img-2: validator_exception:RuntimeError"]
    assert session_state.image_validation_failures == ["img-2: validator_exception:RuntimeError"]
    assert session_state.activity_feed[-1]["message"] == "[IMG] img-2: error | conf: 0.10 | fallback_safe"
