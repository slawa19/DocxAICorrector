import pytest

import state


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


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
    assert session_state.run_log[0]["kind"] == "block"
    assert session_state.run_log[0]["details"] == "entry-5"
    assert session_state.run_log[0]["message"].endswith("entry-5")
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
    assert session_state.latest_source_token == ""
    assert session_state.selected_source_token == ""
    assert session_state.last_background_error is None
    assert session_state.processing_stop_requested is False
    assert session_state.processing_worker is None
    assert session_state.processing_event_queue is None
    assert session_state.processing_stop_event is None
    assert session_state.preparation_worker is None
    assert session_state.preparation_event_queue is None
    assert session_state.prepared_run_context is None
    assert session_state.latest_preparation_summary is None
    assert session_state.preparation_input_marker == ""
    assert session_state.preparation_failed_marker == ""
    assert session_state.processing_outcome == "idle"
    assert session_state.prepared_source_key == ""
    assert session_state.preparation_cache == {}
    assert session_state.processing_status["cached"] is False
    assert session_state.processing_status["terminal_kind"] is None
    assert session_state.restart_source is None
    assert session_state.completed_source is None


def test_set_processing_status_updates_preparation_metrics(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.init_session_state()
    state.set_processing_status(
        stage="Разбор DOCX",
        detail="detail",
        progress=0.5,
        is_running=True,
        phase="preparing",
        file_size_bytes=1024,
        paragraph_count=12,
        image_count=3,
        source_chars=5000,
        cached=True,
    )

    assert session_state.processing_status["phase"] == "preparing"
    assert session_state.processing_status["file_size_bytes"] == 1024
    assert session_state.processing_status["paragraph_count"] == 12
    assert session_state.processing_status["image_count"] == 3
    assert session_state.processing_status["source_chars"] == 5000
    assert session_state.processing_status["cached"] is True


def test_reset_run_state_can_clear_restart_source(monkeypatch):
    session_state = SessionState(
        restart_source={"filename": "report.docx", "storage_path": "restart.bin"},
        completed_source={"filename": "report.docx", "storage_path": "completed.bin"},
        last_background_error={"stage": "processing"},
    )
    monkeypatch.setattr(state.st, "session_state", session_state)
    cleared = []
    monkeypatch.setattr(state, "clear_restart_source", lambda restart_source: cleared.append(restart_source))

    state.init_session_state()
    state.reset_run_state(keep_restart_source=False)

    assert cleared == [
        {"filename": "report.docx", "storage_path": "completed.bin"},
        {"filename": "report.docx", "storage_path": "restart.bin"},
    ]
    assert session_state.restart_source is None
    assert session_state.completed_source is None
    assert session_state.last_background_error is None


def test_append_image_log_updates_summary_and_run_log(monkeypatch):
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
    assert session_state.image_processing_summary["fallbacks_applied"] == 1
    assert session_state.image_processing_summary["validation_errors"] == ["img-2: validator_exception:RuntimeError"]
    assert session_state.image_validation_failures == ["img-2: validator_exception:RuntimeError"]
    assert session_state.run_log[0]["kind"] == "image"
    assert session_state.run_log[0]["message"] == "[IMG OK] Изображение img-1 | обработка завершена | confidence: 0.92"
    assert session_state.run_log[1]["kind"] == "image"
    assert session_state.run_log[1]["message"] == "[IMG ERR] Изображение img-2 | ошибка обработки | ошибка валидации: RuntimeError"
    # append_image_log no longer writes to activity_feed — image results go only to run_log
    assert session_state.activity_feed == []


def test_append_image_log_counts_soft_accept_as_success(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.init_session_state()

    state.append_image_log(
        image_id="img-3",
        status="validated",
        decision="accept_soft",
        confidence=0.81,
        missing_labels=[],
        suspicious_reasons=["structure_mismatch"],
    )

    assert session_state.image_processing_summary["images_validated"] == 1
    assert session_state.image_processing_summary["validation_passed"] == 1


def test_append_image_log_counts_skipped_fallback_without_validation_error(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.init_session_state()

    state.append_image_log(
        image_id="img-unsupported",
        status="skipped",
        decision="fallback_original",
        confidence=0.0,
        suspicious_reasons=["unsupported_source_image_format:image/x-emf"],
    )

    assert session_state.image_processing_summary["total_images"] == 1
    assert session_state.image_processing_summary["processed_images"] == 1
    assert session_state.image_processing_summary["images_validated"] == 0
    assert session_state.image_processing_summary["fallbacks_applied"] == 1
    assert session_state.image_processing_summary["validation_errors"] == []
    assert session_state.image_validation_failures == []
    assert session_state.run_log[-1]["message"] == (
        "[IMG WARN] Изображение img-unsupported | оставлен оригинал | неподдерживаемый формат исходного изображения: image/x-emf"
    )


def test_append_image_log_does_not_count_compared_as_validated_but_counts_fallback(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.init_session_state()

    state.append_image_log(
        image_id="img-compared",
        status="compared",
        decision="fallback_safe",
        confidence=0.0,
        final_variant="safe",
        final_reason="compare_all_variants_incomplete:safe",
    )

    assert session_state.image_processing_summary["images_validated"] == 0
    assert session_state.image_processing_summary["fallbacks_applied"] == 1
    assert session_state.image_processing_summary["validation_errors"] == []
