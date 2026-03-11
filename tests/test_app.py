import app
import application_flow
import compare_panel
import processing_runtime
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
    def __init__(self, name: str, content: bytes):
        self.name = name
        self.size = len(content)
        self._content = content

    def getvalue(self):
        return self._content


def test_build_uploaded_file_token_uses_name_size_and_content_hash():
    token = processing_runtime.build_uploaded_file_token(UploadedFileStub("report.docx", b"abc"))

    assert token == "report.docx:3:ba7816bf8f01cfea"


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
        restart_source={"filename": "old.docx", "storage_path": "old.bin"},
    )
    reset_calls = []

    application_flow.sync_selected_file_context(
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: (reset_calls.append(kwargs), session_state.update(run_log=[], activity_feed=[], restart_source=None)),
        uploaded_file_token="new.docx:20",
    )

    assert reset_calls == [{"keep_restart_source": False}]
    assert session_state.selected_source_token == "new.docx:20"
    assert session_state.restart_source is None
    assert session_state.run_log == []
    assert session_state.activity_feed == []


def test_has_resettable_state_depends_on_restartable_source(monkeypatch):
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": "restart.bin"})

    assert application_flow.has_resettable_state(current_result=None, session_state=session_state) is True

    session_state.processing_outcome = "idle"

    assert application_flow.has_resettable_state(current_result=None, session_state=session_state) is False


def test_derive_idle_view_state_covers_idle_paths(monkeypatch):
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": "restart.bin"})

    assert application_flow.derive_app_idle_view_state(current_result=None, uploaded_file=object(), session_state=session_state) == "file_selected"
    assert application_flow.derive_app_idle_view_state(current_result={"docx_bytes": b"x"}, uploaded_file=None, session_state=session_state) == "completed"
    assert application_flow.derive_app_idle_view_state(current_result=None, uploaded_file=None, session_state=session_state) == "restartable"

    session_state.processing_outcome = "idle"

    assert application_flow.derive_app_idle_view_state(current_result=None, uploaded_file=None, session_state=session_state) == "empty"


def test_get_cached_restart_file_returns_none_when_storage_missing(monkeypatch):
    session_state = SessionState(restart_source={"filename": "report.docx", "storage_path": "missing.bin"})
    monkeypatch.setattr(application_flow, "load_restart_source_bytes", lambda restart_source: None)

    assert application_flow.get_cached_restart_file(session_state=session_state) is None


def test_resolve_effective_uploaded_file_uses_completed_source_after_success():
    session_state = SessionState(
        completed_source={"filename": "report.docx", "source_bytes": b"abc", "token": "report.docx:3:abc"}
    )

    uploaded_file = application_flow.resolve_effective_uploaded_file(
        uploaded_file=None,
        current_result={"docx_bytes": b"done"},
        session_state=session_state,
    )

    assert uploaded_file is not None
    assert uploaded_file.name == "report.docx"
    assert uploaded_file.getvalue() == b"abc"


def test_has_restartable_source_does_not_materialize_restart_bytes(monkeypatch):
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": "restart.bin"})
    load_calls = []

    assert application_flow.has_restartable_source(session_state=session_state) is True
    assert load_calls == []
def test_compare_panel_applies_selected_variants_and_shows_success(monkeypatch):
    calls = []

    monkeypatch.setattr(compare_panel.st, "info", lambda message: calls.append(("info", message)))
    monkeypatch.setattr(compare_panel.st, "caption", lambda message: calls.append(("caption", message)))

    compare_panel.render_compare_all_apply_panel(
        latest_image_mode="compare_all",
        image_assets=[ImageAsset(image_id="img_001", placeholder="[[DOCX_IMAGE_img_001]]", original_bytes=b"x", mime_type="image/png", position_index=0, comparison_variants={"safe": {"bytes": b"safe"}}, final_decision="compared")],
        render_section_gap=lambda gap: calls.append(("gap", gap)),
    )

    assert ("gap", "lg") in calls
    assert any(kind == "info" for kind, _ in calls)


def test_compare_panel_reports_apply_errors(monkeypatch):
    calls = []

    monkeypatch.setattr(compare_panel.st, "info", lambda message: calls.append(("info", message)))
    monkeypatch.setattr(compare_panel.st, "caption", lambda message: calls.append(("caption", message)))

    compare_panel.render_compare_all_apply_panel(
        latest_image_mode="compare_all",
        image_assets=[ImageAsset(image_id="img_001", placeholder="[[DOCX_IMAGE_img_001]]", original_bytes=b"x", mime_type="image/png", position_index=0, comparison_variants={"safe": {"bytes": b"safe"}}, final_decision="compared")],
        render_section_gap=lambda gap: calls.append(("gap", gap)),
    )

    assert not any(kind == "apply" for kind, _ in calls)
    assert not any(kind == "selector" for kind, _ in calls)
