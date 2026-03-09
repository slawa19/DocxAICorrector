import app
from models import ImageAsset


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def test_main_logs_app_start_only_once(monkeypatch):
    session_state = SessionState(app_start_logged=False)
    logged_events = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: session_state.setdefault("app_start_logged", False))
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
    monkeypatch.setattr(app, "log_event", lambda *args, **kwargs: logged_events.append((args, kwargs)))
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "load_app_config", lambda: {})
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


class UploadedFileStub:
    def __init__(self, name: str, size: int):
        self.name = name
        self.size = size


def test_build_uploaded_file_token_uses_name_and_size():
    token = app.build_uploaded_file_token(UploadedFileStub("report.docx", 321))

    assert token == "report.docx:321"


def test_build_start_button_label_changes_with_result_state():
    assert app.build_start_button_label(has_current_result=False, has_previous_result=False) == "Начать обработку"
    assert app.build_start_button_label(has_current_result=True, has_previous_result=False) == "Запустить заново"
    assert app.build_start_button_label(has_current_result=False, has_previous_result=True) == "Начать обработку нового файла"


def test_sync_selected_file_context_resets_run_state_for_new_file(monkeypatch):
    session_state = SessionState(
        selected_source_token="old.docx:10",
        previous_result=None,
        latest_docx_bytes=b"docx",
        latest_source_name="old.docx",
        latest_source_token="old.docx:10",
        latest_markdown="markdown",
        run_log=[{"status": "STOP"}],
        activity_feed=[{"time": "10:00:00", "message": "stale"}],
        processed_block_markdowns=["partial"],
        markdown_preview_render_nonce=1,
        last_error="",
        markdown_preview_block_index=1,
        image_assets=[],
        image_validation_failures=[],
        image_processing_summary={},
        processing_status={},
        processing_stop_requested=False,
        processing_worker=None,
        processing_event_queue=None,
        processing_stop_event=None,
        processing_outcome="idle",
        prepared_source_key="old.docx:10:6000",
    )
    monkeypatch.setattr(app.st, "session_state", session_state)

    app._sync_selected_file_context("new.docx:20")

    assert session_state.selected_source_token == "new.docx:20"
    assert session_state.previous_result["source_token"] == "old.docx:10"
    assert session_state.run_log == []
    assert session_state.activity_feed == []


def test_run_document_processing_fails_on_placeholder_integrity_mismatch(monkeypatch):
    emitted_state = {}
    activity_messages = []
    log_entries = []

    monkeypatch.setattr(app, "get_client", lambda: object())
    monkeypatch.setattr(app, "ensure_pandoc_available", lambda: None)
    monkeypatch.setattr(app, "load_system_prompt", lambda: "system")
    monkeypatch.setattr(app, "generate_markdown_block", lambda **kwargs: "Обработанный блок без placeholder")
    monkeypatch.setattr(app, "process_document_images", lambda **kwargs: kwargs["image_assets"])
    monkeypatch.setattr(app, "inspect_placeholder_integrity", lambda markdown, assets: {"img_001": "lost"})
    monkeypatch.setattr(app, "convert_markdown_to_docx_bytes", lambda markdown: (_ for _ in ()).throw(AssertionError("must not build docx")))
    monkeypatch.setattr(app, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "present_error", lambda code, exc, title, **kwargs: f"{title}: {exc}")
    monkeypatch.setattr(app, "_emit_or_apply_state", lambda runtime, **values: emitted_state.update(values))
    monkeypatch.setattr(app, "_emit_or_apply_finalize", lambda runtime, stage, detail, progress: emitted_state.update(final_stage=stage, final_detail=detail, final_progress=progress))
    monkeypatch.setattr(app, "_emit_or_apply_activity", lambda runtime, message: activity_messages.append(message))
    monkeypatch.setattr(app, "_emit_or_apply_log", lambda runtime, **payload: log_entries.append(payload))
    monkeypatch.setattr(app, "_emit_or_apply_status", lambda runtime, **payload: None)

    result = app.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {
                "target_text": "Исходный блок",
                "context_before": "",
                "context_after": "",
                "target_chars": 13,
                "context_chars": 0,
            }
        ],
        image_assets=[
            ImageAsset(
                image_id="img_001",
                placeholder="[[DOCX_IMAGE_img_001]]",
                original_bytes=b"png",
                mime_type="image/png",
                position_index=0,
            )
        ],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=None,
    )

    assert result == "failed"
    assert emitted_state["last_error"].startswith("Критическая ошибка подготовки изображений")
    assert emitted_state["final_stage"] == "Критическая ошибка"
    assert activity_messages[-1] == "Сборка DOCX остановлена из-за потери или дублирования image placeholder."
    assert log_entries[-1]["status"] == "ERROR"


def test_run_processing_worker_emits_worker_complete_after_unhandled_crash(monkeypatch):
    emitted_events = []

    class RuntimeStub:
        def emit(self, event_type, **payload):
            emitted_events.append({"type": event_type, **payload})

    monkeypatch.setattr(app, "run_document_processing", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(app, "present_error", lambda code, exc, title, **kwargs: f"{title}: {exc}")

    app._run_processing_worker(
        runtime=RuntimeStub(),
        uploaded_filename="report.docx",
        jobs=[{"target_text": "x", "context_before": "", "context_after": "", "target_chars": 1, "context_chars": 0}],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
    )

    assert emitted_events[-1] == {"type": "worker_complete", "outcome": "failed"}
    assert any(event["type"] == "set_state" and event["values"]["last_error"].startswith("Критическая ошибка фоновой обработки") for event in emitted_events)
    assert any(event["type"] == "finalize_processing_status" for event in emitted_events)
