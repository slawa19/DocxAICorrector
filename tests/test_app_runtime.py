import app_runtime


def test_emit_state_delegates_to_runtime_impl(monkeypatch):
    calls = []
    monkeypatch.setattr(app_runtime, "emit_or_apply_state_impl", lambda runtime, **values: calls.append((runtime, values)))

    app_runtime.emit_state("runtime", last_error="boom")

    assert calls == [("runtime", {"last_error": "boom"})]


def test_emit_finalize_uses_state_finalize_callback(monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_runtime,
        "emit_or_apply_finalize_impl",
        lambda runtime, *, finalize_processing_status, stage, detail, progress: calls.append(
            (runtime, finalize_processing_status, stage, detail, progress)
        ),
    )
    finalize_stub = object()
    monkeypatch.setattr(app_runtime, "finalize_processing_status", finalize_stub)

    app_runtime.emit_finalize("runtime", "done", "ok", 1.0)

    assert calls == [("runtime", finalize_stub, "done", "ok", 1.0)]


def test_start_background_preparation_passes_state_callbacks(monkeypatch):
    captured = {}
    monkeypatch.setattr(app_runtime, "start_background_preparation_impl", lambda **kwargs: captured.update(kwargs))
    reset_stub = object()
    push_stub = object()
    status_stub = object()
    monkeypatch.setattr(app_runtime, "reset_run_state", reset_stub)
    monkeypatch.setattr(app_runtime, "push_activity", push_stub)
    monkeypatch.setattr(app_runtime, "set_processing_status", status_stub)

    app_runtime.start_background_preparation(
        worker_target="worker",
        uploaded_file="file",
        upload_marker="marker",
        chunk_size=6000,
        image_mode="safe",
        enable_post_redraw_validation=True,
    )

    assert captured["worker_target"] == "worker"
    assert captured["reset_run_state"] is reset_stub
    assert captured["push_activity"] is push_stub
    assert captured["set_processing_status"] is status_stub
    assert captured["upload_marker"] == "marker"


def test_start_background_processing_passes_state_callbacks(monkeypatch):
    captured = {}
    monkeypatch.setattr(app_runtime, "start_background_processing_impl", lambda **kwargs: captured.update(kwargs))
    reset_stub = object()
    push_stub = object()
    status_stub = object()
    monkeypatch.setattr(app_runtime, "reset_run_state", reset_stub)
    monkeypatch.setattr(app_runtime, "push_activity", push_stub)
    monkeypatch.setattr(app_runtime, "set_processing_status", status_stub)

    app_runtime.start_background_processing(
        worker_target="worker",
        uploaded_filename="report.docx",
        uploaded_token="token",
        source_bytes=b"abc",
        jobs=[{"target_text": "block"}],
        image_assets=[],
        image_mode="safe",
        app_config={"x": 1},
        model="gpt-5.4",
        max_retries=2,
    )

    assert captured["worker_target"] == "worker"
    assert captured["reset_run_state"] is reset_stub
    assert captured["push_activity"] is push_stub
    assert captured["set_processing_status"] is status_stub
    assert captured["uploaded_filename"] == "report.docx"
    assert captured["model"] == "gpt-5.4"