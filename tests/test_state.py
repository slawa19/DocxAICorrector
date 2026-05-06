import pytest

from docxaicorrector.core.models import StructureRecognitionSummary
from docxaicorrector.runtime import state
from docxaicorrector.ui.application_flow import PreparedRunContext
from conftest import SessionState as SessionState  # noqa: F811


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
    assert session_state.latest_processing_operation == "edit"
    assert session_state.latest_audiobook_postprocess_enabled is False
    assert session_state.selected_source_token == ""
    assert session_state.last_background_error is None
    assert session_state.processing_stop_requested is False
    assert session_state.processing_worker is None
    assert session_state.processing_event_queue is None
    assert session_state.processing_stop_event is None
    assert session_state.latest_narration_text is None
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
    assert session_state.processing_status["raw_paragraph_count"] == 0
    assert session_state.processing_status["logical_paragraph_count"] == 0
    assert session_state.processing_status["merged_group_count"] == 0
    assert session_state.processing_status["merged_raw_paragraph_count"] == 0
    assert session_state.processing_status["terminal_kind"] is None
    assert session_state.restart_source is None
    assert session_state.completed_source is None
    assert session_state.recommended_text_settings is None
    assert session_state.recommended_text_settings_applied_for_token is None
    assert session_state.manual_text_settings_override_for_token is None
    assert session_state.selected_segment_ids == []
    assert session_state.segment_status_by_id == {}
    assert session_state.segment_progress_by_id == {}
    assert session_state.active_segment_id == ""
    assert session_state.active_segment_title == ""
    assert session_state.structure_confirmed is False
    assert session_state.confirmed_structure_fingerprint == ""
    assert session_state.confirmed_at_settings_hash == ""
    assert session_state.segments_loaded_for_source_token == ""
    assert session_state.chapter_selector_search == ""
    assert session_state.chapter_selector_filter == "all"


def test_reset_image_state_restores_image_defaults(monkeypatch):
    session_state = SessionState(
        image_assets=["stale"],
        image_validation_failures=["boom"],
        image_processing_summary={"total_images": 9, "validation_errors": ["boom"]},
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.reset_image_state()

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
        source_format="pdf",
        conversion_backend="libreoffice",
        raw_paragraph_count=14,
        logical_paragraph_count=12,
        merged_group_count=2,
        merged_raw_paragraph_count=4,
        cached=True,
    )

    assert session_state.processing_status["phase"] == "preparing"
    assert session_state.processing_status["file_size_bytes"] == 1024
    assert session_state.processing_status["paragraph_count"] == 12
    assert session_state.processing_status["image_count"] == 3
    assert session_state.processing_status["source_chars"] == 5000
    assert session_state.processing_status["source_format"] == "pdf"
    assert session_state.processing_status["conversion_backend"] == "libreoffice"
    assert session_state.processing_status["raw_paragraph_count"] == 14
    assert session_state.processing_status["logical_paragraph_count"] == 12
    assert session_state.processing_status["merged_group_count"] == 2
    assert session_state.processing_status["merged_raw_paragraph_count"] == 4
    assert session_state.processing_status["cached"] is True


def test_set_processing_status_updates_segment_runtime_metrics(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.init_session_state()
    state.set_processing_status(
        stage="Обработка блока",
        detail="Идет работа.",
        progress=0.5,
        is_running=True,
        phase="processing",
        segment_status_by_id={"seg_0001": "processing", "seg_0002": "pending"},
        segment_progress_by_id={"seg_0001": 0.5, "seg_0002": 0.0},
        active_segment_id="seg_0001",
        active_segment_title="Chapter 1",
    )

    assert session_state.processing_status["segment_status_by_id"] == {"seg_0001": "processing", "seg_0002": "pending"}
    assert session_state.processing_status["segment_progress_by_id"] == {"seg_0001": 0.5, "seg_0002": 0.0}
    assert session_state.processing_status["active_segment_id"] == "seg_0001"
    assert session_state.processing_status["active_segment_title"] == "Chapter 1"
    assert session_state.segment_status_by_id == {"seg_0001": "processing", "seg_0002": "pending"}
    assert session_state.segment_progress_by_id == {"seg_0001": 0.5, "seg_0002": 0.0}
    assert session_state.active_segment_id == "seg_0001"
    assert session_state.active_segment_title == "Chapter 1"


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


def test_reset_run_state_can_preserve_preparation_state(monkeypatch):
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "report.docx:3:abc"})()
    session_state = SessionState(
        prepared_run_context=prepared_run_context,
        latest_preparation_summary={"stage": "Документ подготовлен"},
        preparation_input_marker="report.docx:3:token:6000",
        preparation_failed_marker="",
        prepared_source_key="report.docx:3:token:6000",
        preparation_cache={"report.docx:3:token:6000": {"cached": True}},
        recommended_text_settings={
            "file_token": "report.docx:3:abc",
            "processing_operation": "edit",
            "source_language": "en",
            "target_language": "ru",
            "reason_summary": None,
        },
        recommended_text_settings_applied_for_token="report.docx:3:abc",
        recommended_text_settings_applied_snapshot={
            "file_token": "report.docx:3:abc",
            "processing_operation": "edit",
            "source_language": "en",
            "target_language": "ru",
        },
        recommended_text_settings_pending_widget_state={
            "file_token": "report.docx:3:abc",
            "widget_state": {"sidebar_text_operation": "Перевод"},
        },
        recommended_text_settings_notice_details={
            "file_token": "report.docx:3:abc",
            "changes": ["режим: Литературное редактирование -> Перевод"],
        },
        manual_text_settings_override_for_token={
            "file_token": "report.docx:3:abc",
            "processing_operation": True,
            "source_language": False,
            "target_language": False,
        },
        structure_manifest_notice_token="report.docx:3:abc",
        structure_manifest_notice_details={
            "file_token": "report.docx:3:abc",
            "manifest_path": ".run/structure_manifests/report.segments.json",
        },
        selected_segment_ids=["seg_0001", "seg_0002"],
        chapter_selector_search="chapter",
        chapter_selector_filter="failed",
        segment_status_by_id={"seg_0001": "completed", "seg_0002": "processing"},
        segment_progress_by_id={"seg_0001": 1.0, "seg_0002": 0.5},
        active_segment_id="seg_0002",
        active_segment_title="Chapter 2",
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:abc",
        latest_markdown="stale",
        latest_narration_text="stale narration",
        run_log=[{"message": "stale"}],
        activity_feed=[{"message": "stale"}],
    )
    monkeypatch.setattr(state.st, "session_state", session_state)
    monkeypatch.setattr(state, "clear_restart_source", lambda restart_source: None)

    state.init_session_state()
    state.reset_run_state(preserve_preparation=True)

    assert session_state.prepared_run_context is prepared_run_context
    assert session_state.latest_preparation_summary == {"stage": "Документ подготовлен"}
    assert session_state.preparation_input_marker == "report.docx:3:token:6000"
    assert session_state.prepared_source_key == "report.docx:3:token:6000"
    assert session_state.preparation_cache == {"report.docx:3:token:6000": {"cached": True}}
    assert session_state.latest_narration_text is None
    assert session_state.recommended_text_settings["file_token"] == "report.docx:3:abc"
    assert session_state.recommended_text_settings_applied_for_token == "report.docx:3:abc"
    assert session_state.recommended_text_settings_applied_snapshot["file_token"] == "report.docx:3:abc"
    assert session_state.recommended_text_settings_pending_widget_state["file_token"] == "report.docx:3:abc"
    assert session_state.recommended_text_settings_notice_details["file_token"] == "report.docx:3:abc"
    assert session_state.manual_text_settings_override_for_token["file_token"] == "report.docx:3:abc"
    assert session_state.structure_manifest_notice_token == "report.docx:3:abc"
    assert session_state.structure_manifest_notice_details["file_token"] == "report.docx:3:abc"
    assert session_state.selected_segment_ids == ["seg_0001", "seg_0002"]
    assert session_state.chapter_selector_search == "chapter"
    assert session_state.chapter_selector_filter == "failed"
    assert session_state.segment_status_by_id == {"seg_0001": "completed", "seg_0002": "processing"}
    assert session_state.segment_progress_by_id == {"seg_0001": 1.0, "seg_0002": 0.5}
    assert session_state.active_segment_id == "seg_0002"
    assert session_state.active_segment_title == "Chapter 2"
    assert session_state.structure_confirmed is True
    assert session_state.confirmed_structure_fingerprint == "abc123"
    assert session_state.confirmed_at_settings_hash == "settings123"
    assert session_state.segments_loaded_for_source_token == "report.docx:3:abc"
    assert session_state.latest_markdown == ""
    assert session_state.run_log == []
    assert session_state.activity_feed == []


def test_reset_run_state_drops_recommendation_state_for_different_preserved_file(monkeypatch):
    prepared_run_context = type("PreparedRunContextStub", (), {"uploaded_file_token": "new.docx:3:def"})()
    session_state = SessionState(
        prepared_run_context=prepared_run_context,
        recommended_text_settings={
            "file_token": "old.docx:3:abc",
            "processing_operation": "edit",
            "source_language": "en",
            "target_language": "ru",
            "reason_summary": None,
        },
        recommended_text_settings_applied_for_token="old.docx:3:abc",
        recommended_text_settings_applied_snapshot={
            "file_token": "old.docx:3:abc",
            "processing_operation": "edit",
            "source_language": "en",
            "target_language": "ru",
        },
        recommended_text_settings_pending_widget_state={
            "file_token": "old.docx:3:abc",
            "widget_state": {"sidebar_text_operation": "Перевод"},
        },
        recommended_text_settings_notice_details={
            "file_token": "old.docx:3:abc",
            "changes": ["режим: Литературное редактирование -> Перевод"],
        },
        manual_text_settings_override_for_token={
            "file_token": "old.docx:3:abc",
            "processing_operation": True,
            "source_language": False,
            "target_language": False,
        },
        structure_manifest_notice_token="old.docx:3:abc",
        structure_manifest_notice_details={
            "file_token": "old.docx:3:abc",
            "manifest_path": ".run/structure_manifests/old.segments.json",
        },
        selected_segment_ids=["seg_old"],
        segment_status_by_id={"seg_old": "completed"},
        segment_progress_by_id={"seg_old": 1.0},
        active_segment_id="seg_old",
        active_segment_title="Old Chapter",
        structure_confirmed=True,
        confirmed_structure_fingerprint="oldfp",
        confirmed_at_settings_hash="oldsettings",
        segments_loaded_for_source_token="old.docx:3:abc",
    )
    monkeypatch.setattr(state.st, "session_state", session_state)
    monkeypatch.setattr(state, "clear_restart_source", lambda restart_source: None)

    state.init_session_state()
    state.reset_run_state(preserve_preparation=True)

    assert session_state.recommended_text_settings is None
    assert session_state.recommended_text_settings_applied_for_token is None
    assert session_state.recommended_text_settings_applied_snapshot is None
    assert session_state.recommended_text_settings_pending_widget_state is None
    assert session_state.recommended_text_settings_notice_details is None
    assert session_state.manual_text_settings_override_for_token is None
    assert session_state.structure_manifest_notice_token is None
    assert session_state.structure_manifest_notice_details is None
    assert session_state.selected_segment_ids == []
    assert session_state.segment_status_by_id == {}
    assert session_state.segment_progress_by_id == {}
    assert session_state.active_segment_id == ""
    assert session_state.active_segment_title == ""
    assert session_state.structure_confirmed is False
    assert session_state.confirmed_structure_fingerprint == ""
    assert session_state.confirmed_at_settings_hash == ""
    assert session_state.segments_loaded_for_source_token == ""


def test_recommended_text_settings_helpers_roundtrip_state(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.set_recommended_text_settings({"file_token": "report.docx:3:abc"})
    state.set_manual_text_settings_override_for_token({"file_token": "report.docx:3:abc", "processing_operation": True})
    state.set_recommended_text_settings_applied(
        file_token="report.docx:3:abc",
        snapshot={
            "file_token": "report.docx:3:abc",
            "processing_operation": "translate",
            "source_language": "auto",
            "target_language": "ru",
        },
    )
    state.set_recommended_text_settings_pending_widget_state(
        {"file_token": "report.docx:3:abc", "widget_state": {"sidebar_text_operation": "Перевод"}}
    )
    state.set_recommended_text_settings_notice(
        file_token="report.docx:3:abc",
        details={"file_token": "report.docx:3:abc", "changes": ["режим: edit -> translate"]},
    )

    assert state.get_recommended_text_settings() == {"file_token": "report.docx:3:abc"}
    assert state.get_manual_text_settings_override_for_token() == {
        "file_token": "report.docx:3:abc",
        "processing_operation": True,
    }
    assert state.get_recommended_text_settings_applied_for_token() == "report.docx:3:abc"
    assert state.get_recommended_text_settings_applied_snapshot() == {
        "file_token": "report.docx:3:abc",
        "processing_operation": "translate",
        "source_language": "auto",
        "target_language": "ru",
    }
    assert state.get_recommended_text_settings_pending_widget_state() == {
        "file_token": "report.docx:3:abc",
        "widget_state": {"sidebar_text_operation": "Перевод"},
    }
    assert state.get_recommended_text_settings_notice_token() == "report.docx:3:abc"
    assert state.get_recommended_text_settings_notice_details() == {
        "file_token": "report.docx:3:abc",
        "changes": ["режим: edit -> translate"],
    }


def test_structure_manifest_notice_helpers_roundtrip_state(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.set_structure_manifest_notice(
        file_token="report.docx:3:abc",
        details={
            "file_token": "report.docx:3:abc",
            "manifest_path": ".run/structure_manifests/20260506_094000_report.segments.json",
            "structure_fingerprint": "abc123def456",
        },
    )

    assert state.get_structure_manifest_notice_token() == "report.docx:3:abc"
    assert state.get_structure_manifest_notice_details() == {
        "file_token": "report.docx:3:abc",
        "manifest_path": ".run/structure_manifests/20260506_094000_report.segments.json",
        "structure_fingerprint": "abc123def456",
    }


def test_structure_review_state_helpers_roundtrip(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.set_selected_segment_ids(["seg_0001", "seg_0002"])
    state.set_structure_confirmation_state(
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:abc",
    )

    assert state.get_selected_segment_ids() == ["seg_0001", "seg_0002"]
    assert state.get_structure_confirmed() is True
    assert state.get_confirmed_structure_fingerprint() == "abc123def456"
    assert state.get_confirmed_at_settings_hash() == "settings123"
    assert state.get_segments_loaded_for_source_token() == "report.docx:3:abc"


def test_segment_runtime_state_helpers_roundtrip(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.set_segment_runtime_state(
        segment_status_by_id={"seg_0001": "processing", "seg_0002": "completed"},
        segment_progress_by_id={"seg_0001": 0.5, "seg_0002": 1.0},
        active_segment_id="seg_0001",
        active_segment_title="Chapter 1",
    )

    assert state.get_segment_status_by_id() == {"seg_0001": "processing", "seg_0002": "completed"}
    assert state.get_segment_progress_by_id() == {"seg_0001": 0.5, "seg_0002": 1.0}
    assert state.get_active_segment_id() == "seg_0001"
    assert state.get_active_segment_title() == "Chapter 1"


def test_clear_structure_review_state_resets_analysis_flags(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        segment_status_by_id={"seg_0001": "processing"},
        segment_progress_by_id={"seg_0001": 0.5},
        active_segment_id="seg_0001",
        active_segment_title="Chapter 1",
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc",
        confirmed_at_settings_hash="settings",
        segments_loaded_for_source_token="report.docx:3:abc",
        chapter_selector_search="chapter",
        chapter_selector_filter="failed",
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.clear_structure_review_state()

    assert session_state.selected_segment_ids == []
    assert session_state.segment_status_by_id == {}
    assert session_state.segment_progress_by_id == {}
    assert session_state.active_segment_id == ""
    assert session_state.active_segment_title == ""
    assert session_state.structure_confirmed is False
    assert session_state.confirmed_structure_fingerprint == ""
    assert session_state.confirmed_at_settings_hash == ""
    assert session_state.segments_loaded_for_source_token == ""
    assert session_state.chapter_selector_search == ""
    assert session_state.chapter_selector_filter == "all"


def test_text_transform_assessment_helper_roundtrip_state(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.set_text_transform_assessment({"dominant_language": "ru"})

    assert state.get_text_transform_assessment() == {"dominant_language": "ru"}


def test_consume_recommended_text_settings_pending_widget_state_clears_valid_payload(monkeypatch):
    session_state = SessionState(
        recommended_text_settings_pending_widget_state={
            "file_token": "report.docx:3:abc",
            "widget_state": {"sidebar_text_operation": "Перевод"},
        }
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    payload = state.consume_recommended_text_settings_pending_widget_state()

    assert payload == {
        "file_token": "report.docx:3:abc",
        "widget_state": {"sidebar_text_operation": "Перевод"},
    }
    assert session_state.recommended_text_settings_pending_widget_state is None


def test_consume_recommended_text_settings_pending_widget_state_clears_malformed_payload(monkeypatch):
    session_state = SessionState(recommended_text_settings_pending_widget_state={"file_token": "report.docx:3:abc", "widget_state": None})
    monkeypatch.setattr(state.st, "session_state", session_state)

    payload = state.consume_recommended_text_settings_pending_widget_state()

    assert payload is None
    assert session_state.recommended_text_settings_pending_widget_state is None


def test_apply_recommended_widget_state_updates_streamlit_widget_keys(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.apply_recommended_widget_state(
        {
            "sidebar_text_operation": "Перевод",
            "sidebar_source_language": "Авто",
        }
    )

    assert session_state.sidebar_text_operation == "Перевод"
    assert session_state.sidebar_source_language == "Авто"


def test_preparation_marker_helpers_track_request_state(monkeypatch):
    prepared_run_context = PreparedRunContext(
        uploaded_filename="report.docx",
        uploaded_file_bytes=b"abc",
        uploaded_file_token="report.docx:3:token",
        source_text="source-text",
        paragraphs=[],
        image_assets=[],
        jobs=[],
        prepared_source_key="report.docx:3:token:6000",
        preparation_stage="Документ подготовлен",
        preparation_detail="Анализ завершён.",
        preparation_cached=False,
        preparation_elapsed_seconds=0.1,
        structure_recognition_summary=StructureRecognitionSummary(),
    )
    session_state = SessionState(
        preparation_input_marker="report.docx:3:token:6000",
        preparation_failed_marker="",
        prepared_run_context=prepared_run_context,
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    assert state.should_start_preparation_for_marker("report.docx:3:token:6000") is False
    assert state.get_prepared_run_context_for_marker("report.docx:3:token:6000") is prepared_run_context
    assert state.is_preparation_failed_for_marker("report.docx:3:token:6000") is False


def test_mark_preparation_started_clears_previous_failure_and_context(monkeypatch):
    session_state = SessionState(
        preparation_input_marker="old",
        preparation_failed_marker="old",
        prepared_run_context=object(),
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.mark_preparation_started("new")

    assert session_state.preparation_input_marker == "new"
    assert session_state.preparation_failed_marker == ""
    assert session_state.prepared_run_context is None


def test_apply_preparation_complete_initializes_structure_review_state(monkeypatch):
    session_state = SessionState(selected_source_token="", chapter_selector_search="old", chapter_selector_filter="completed")
    monkeypatch.setattr(state.st, "session_state", session_state)

    prepared_run_context = type(
        "PreparedRunContextStub",
        (),
        {
            "uploaded_file_token": "report.docx:3:abc",
            "prepared_source_key": "report.docx:3:abc:6000",
            "segments": [
                type("SegmentStub", (), {"segment_id": "seg_0001"})(),
                type("SegmentStub", (), {"segment_id": "seg_0002"})(),
            ],
        },
    )()

    state.apply_preparation_complete(
        prepared_run_context=prepared_run_context,
        upload_marker="report.docx:3:abc:6000",
        reset_run_state_fn=lambda **kwargs: None,
    )

    assert session_state.selected_source_token == "report.docx:3:abc"
    assert session_state.selected_segment_ids == ["seg_0001", "seg_0002"]
    assert session_state.segment_status_by_id == {"seg_0001": "pending", "seg_0002": "pending"}
    assert session_state.segment_progress_by_id == {"seg_0001": 0.0, "seg_0002": 0.0}
    assert session_state.active_segment_id == ""
    assert session_state.active_segment_title == ""
    assert session_state.structure_confirmed is False
    assert session_state.confirmed_structure_fingerprint == ""
    assert session_state.confirmed_at_settings_hash == ""
    assert session_state.segments_loaded_for_source_token == "report.docx:3:abc"
    assert session_state.chapter_selector_search == ""
    assert session_state.chapter_selector_filter == "all"


def test_state_read_helpers_expose_processing_and_persisted_source_state(monkeypatch):
    session_state = SessionState(
        processing_outcome="stopped",
        processing_status={"stage": "run"},
        run_log=[{"message": "entry"}],
        activity_feed=[{"message": "activity"}],
        restart_source={"filename": "restart.docx", "storage_path": "restart.bin"},
        completed_source={"filename": "completed.docx", "storage_path": "completed.bin"},
        image_assets=["img-1"],
        image_processing_summary={"total_images": 1},
        processed_block_markdowns=["block-1"],
        latest_docx_bytes=b"docx",
        processing_stop_requested=True,
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    assert state.get_processing_outcome() == "stopped"
    assert state.get_processing_status() == {"stage": "run"}
    assert state.get_run_log() == [{"message": "entry"}]
    assert state.get_activity_feed() == [{"message": "activity"}]
    assert state.get_restart_source() == {"filename": "restart.docx", "storage_path": "restart.bin"}
    assert state.get_completed_source() == {"filename": "completed.docx", "storage_path": "completed.bin"}
    assert state.get_image_assets() == ["img-1"]
    assert state.get_image_processing_summary() == {"total_images": 1}
    assert state.get_processed_block_markdowns() == ["block-1"]
    assert state.get_latest_docx_bytes() == b"docx"
    assert state.is_processing_stop_requested() is True
    assert state.get_restart_source_filename() == "restart.docx"
    assert state.has_persisted_source() is True


def test_processing_session_snapshot_exposes_p1a_owned_keys(monkeypatch):
    worker = object()
    event_queue = object()
    stop_event = object()
    session_state = SessionState(
        processing_outcome="running",
        processing_worker=worker,
        processing_event_queue=event_queue,
        processing_stop_event=stop_event,
        processing_stop_requested=True,
        latest_source_name="report.docx",
        latest_source_token="report.docx:3:abc",
        latest_processing_operation="translate",
        latest_audiobook_postprocess_enabled=True,
        selected_source_token="report.docx:3:abc",
        latest_image_mode="safe",
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    snapshot = state.get_processing_session_snapshot()

    assert snapshot.outcome == "running"
    assert snapshot.worker is worker
    assert snapshot.event_queue is event_queue
    assert snapshot.stop_event is stop_event
    assert snapshot.stop_requested is True
    assert snapshot.latest_source_name == "report.docx"
    assert snapshot.latest_source_token == "report.docx:3:abc"
    assert snapshot.latest_processing_operation == "translate"
    assert snapshot.latest_audiobook_postprocess_enabled is True
    assert snapshot.selected_source_token == "report.docx:3:abc"
    assert snapshot.latest_image_mode == "safe"
    assert state.get_latest_source_name() == "report.docx"
    assert state.get_latest_source_token() == "report.docx:3:abc"
    assert state.get_latest_processing_operation() == "translate"
    assert state.get_latest_audiobook_postprocess_enabled() is True
    assert state.get_selected_source_token() == "report.docx:3:abc"
    assert state.get_latest_image_mode() == "safe"
    assert state.get_processing_worker() is worker
    assert state.get_processing_event_queue() is event_queue
    assert state.get_processing_stop_event() is stop_event


def test_apply_preparation_complete_updates_owned_session_keys(monkeypatch):
    prepared_run_context = type("PreparedRunContextStub", (), {
        "uploaded_file_token": "report.docx:3:abc",
        "prepared_source_key": "report.docx:3:abc:6000",
    })()
    session_state = SessionState(
        selected_source_token="",
        processing_outcome="running",
        preparation_worker=object(),
        preparation_event_queue=object(),
    )
    monkeypatch.setattr(state.st, "session_state", session_state)
    reset_calls = []

    state.apply_preparation_complete(
        prepared_run_context=prepared_run_context,
        upload_marker="report.docx:3:ba7816bf8f01cfea:6000",
        reset_run_state_fn=lambda **kwargs: reset_calls.append(kwargs),
    )

    assert reset_calls == []
    assert session_state.prepared_run_context is prepared_run_context
    assert session_state.preparation_input_marker == "report.docx:3:ba7816bf8f01cfea:6000"
    assert session_state.preparation_failed_marker == ""
    assert session_state.selected_source_token == "report.docx:3:abc"
    assert session_state.prepared_source_key == "report.docx:3:abc:6000"
    assert session_state.preparation_worker is None
    assert session_state.preparation_event_queue is None
    assert session_state.processing_outcome == "idle"


def test_apply_preparation_failure_updates_owned_session_keys(monkeypatch):
    session_state = SessionState(
        prepared_run_context=object(),
        preparation_worker=object(),
        preparation_event_queue=object(),
        last_error="",
        processing_outcome="running",
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.apply_preparation_failure(
        upload_marker="report.docx:3:ba7816bf8f01cfea:6000",
        error_message="boom",
        error_details={"stage": "preparation", "error_type": "RuntimeError"},
    )

    assert session_state.prepared_run_context is None
    assert session_state.preparation_input_marker == "report.docx:3:ba7816bf8f01cfea:6000"
    assert session_state.preparation_failed_marker == "report.docx:3:ba7816bf8f01cfea:6000"
    assert session_state.preparation_worker is None
    assert session_state.preparation_event_queue is None
    assert session_state.last_error == "boom"
    assert session_state.last_background_error == {"stage": "preparation", "error_type": "RuntimeError"}
    assert session_state.processing_outcome == "failed"


def test_apply_processing_completion_moves_restart_source_to_completed_cache(monkeypatch):
    session_state = SessionState(
        restart_source={"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "restart.bin", "session_id": "session-a"},
        processing_worker=object(),
        processing_event_queue=object(),
        processing_stop_event=object(),
        processing_stop_requested=True,
        restart_session_id="session-a",
    )
    monkeypatch.setattr(state.st, "session_state", session_state)
    cleared = []

    state.apply_processing_completion(
        outcome="succeeded",
        push_activity=lambda message: None,
        load_restart_source_bytes_fn=lambda restart_source: b"abc",
        clear_restart_source_fn=lambda restart_source: cleared.append(restart_source),
        store_completed_source_fn=lambda **kwargs: {
            "filename": kwargs["source_name"],
            "token": kwargs["source_token"],
            "storage_path": "completed.bin",
            "size": len(kwargs["source_bytes"]),
            "session_id": kwargs["session_id"],
            "storage_kind": "completed",
        },
        should_cache_completed_source_fn=lambda **kwargs: True,
        log_event_fn=lambda *args, **kwargs: None,
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
    assert session_state.processing_outcome == "succeeded"
    assert session_state.processing_worker is None
    assert session_state.processing_event_queue is None
    assert session_state.processing_stop_event is None
    assert session_state.processing_stop_requested is False
    assert cleared == [{"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "restart.bin", "session_id": "session-a"}]


def test_apply_processing_start_updates_owned_p1a_keys(monkeypatch):
    worker = object()
    event_queue = object()
    stop_event = object()
    session_state = SessionState(processing_stop_requested=True)
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.apply_processing_start(
        uploaded_filename="report.docx",
        uploaded_token="report.docx:3:abc",
        image_mode="safe",
        processing_operation="translate",
        audiobook_postprocess_enabled=True,
        worker=worker,
        event_queue=event_queue,
        stop_event=stop_event,
    )

    assert session_state.latest_source_name == "report.docx"
    assert session_state.latest_source_token == "report.docx:3:abc"
    assert session_state.latest_processing_operation == "translate"
    assert session_state.latest_audiobook_postprocess_enabled is True
    assert session_state.selected_source_token == "report.docx:3:abc"
    assert session_state.latest_image_mode == "safe"
    assert session_state.processing_outcome == "running"
    assert session_state.processing_worker is worker
    assert session_state.processing_event_queue is event_queue
    assert session_state.processing_stop_event is stop_event
    assert session_state.processing_stop_requested is False


def test_finalize_processing_status_clears_active_segment(monkeypatch):
    session_state = SessionState(
        processing_status={"stage": "run", "detail": "detail", "active_segment_id": "seg_0001", "active_segment_title": "Chapter 1"},
        active_segment_id="seg_0001",
        active_segment_title="Chapter 1",
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.finalize_processing_status("done", "ok", 1.0, "completed")

    assert session_state.processing_status["active_segment_id"] == ""
    assert session_state.processing_status["active_segment_title"] == ""
    assert session_state.active_segment_id == ""
    assert session_state.active_segment_title == ""


def test_finalize_processing_status_reverts_queued_and_processing_segments_on_stopped(monkeypatch):
    session_state = SessionState(
        processing_status={
            "stage": "run",
            "detail": "detail",
            "segment_status_by_id": {
                "seg_0001": "completed",
                "seg_0002": "queued",
                "seg_0003": "processing",
                "seg_0004": "failed",
            },
            "segment_progress_by_id": {
                "seg_0001": 1.0,
                "seg_0002": 0.0,
                "seg_0003": 0.5,
                "seg_0004": 0.25,
            },
            "active_segment_id": "seg_0003",
            "active_segment_title": "Chapter 3",
        },
        segment_status_by_id={
            "seg_0001": "completed",
            "seg_0002": "queued",
            "seg_0003": "processing",
            "seg_0004": "failed",
        },
        segment_progress_by_id={
            "seg_0001": 1.0,
            "seg_0002": 0.0,
            "seg_0003": 0.5,
            "seg_0004": 0.25,
        },
        active_segment_id="seg_0003",
        active_segment_title="Chapter 3",
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.finalize_processing_status("stopped", "user stop", 0.5, "stopped")

    assert session_state.processing_status["segment_status_by_id"] == {
        "seg_0001": "completed",
        "seg_0002": "pending",
        "seg_0003": "pending",
        "seg_0004": "failed",
    }
    assert session_state.processing_status["segment_progress_by_id"] == {
        "seg_0001": 1.0,
        "seg_0002": 0.0,
        "seg_0003": 0.0,
        "seg_0004": 0.25,
    }
    assert session_state.segment_status_by_id == {
        "seg_0001": "completed",
        "seg_0002": "pending",
        "seg_0003": "pending",
        "seg_0004": "failed",
    }
    assert session_state.segment_progress_by_id == {
        "seg_0001": 1.0,
        "seg_0002": 0.0,
        "seg_0003": 0.0,
        "seg_0004": 0.25,
    }


def test_finalize_processing_status_marks_active_segment_failed_on_error(monkeypatch):
    session_state = SessionState(
        processing_status={
            "stage": "run",
            "detail": "detail",
            "segment_status_by_id": {
                "seg_0001": "completed",
                "seg_0002": "processing",
                "seg_0003": "pending",
            },
            "segment_progress_by_id": {
                "seg_0001": 1.0,
                "seg_0002": 0.5,
                "seg_0003": 0.0,
            },
            "active_segment_id": "seg_0002",
            "active_segment_title": "Chapter 2",
        },
        segment_status_by_id={
            "seg_0001": "completed",
            "seg_0002": "processing",
            "seg_0003": "pending",
        },
        segment_progress_by_id={
            "seg_0001": 1.0,
            "seg_0002": 0.5,
            "seg_0003": 0.0,
        },
        active_segment_id="seg_0002",
        active_segment_title="Chapter 2",
    )
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.finalize_processing_status("failed", "boom", 0.5, "error")

    assert session_state.processing_status["segment_status_by_id"] == {
        "seg_0001": "completed",
        "seg_0002": "failed",
        "seg_0003": "pending",
    }
    assert session_state.processing_status["segment_progress_by_id"] == {
        "seg_0001": 1.0,
        "seg_0002": 0.5,
        "seg_0003": 0.0,
    }
    assert session_state.segment_status_by_id == {
        "seg_0001": "completed",
        "seg_0002": "failed",
        "seg_0003": "pending",
    }


def test_request_processing_stop_marks_flag_and_sets_event(monkeypatch):
    class StopEvent:
        def __init__(self) -> None:
            self.set_calls = 0

        def set(self) -> None:
            self.set_calls += 1

    stop_event = StopEvent()
    session_state = SessionState(processing_stop_event=stop_event, processing_stop_requested=False)
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.request_processing_stop()

    assert stop_event.set_calls == 1
    assert session_state.processing_stop_requested is True


def test_apply_processing_completion_reports_large_restart_source_without_completed_cache(monkeypatch):
    session_state = SessionState(
        restart_source={"filename": "report.docx", "token": "report.docx:12:abc", "storage_path": "restart.bin", "session_id": "session-a"},
        processing_worker=object(),
        processing_event_queue=object(),
        processing_stop_event=object(),
        processing_stop_requested=True,
    )
    monkeypatch.setattr(state.st, "session_state", session_state)
    activities = []
    cleared = []

    state.apply_processing_completion(
        outcome="succeeded",
        push_activity=lambda message: activities.append(message),
        load_restart_source_bytes_fn=lambda restart_source: b"abcdef",
        clear_restart_source_fn=lambda restart_source: cleared.append(restart_source),
        store_completed_source_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("completed cache should not be written")),
        should_cache_completed_source_fn=lambda **kwargs: False,
        log_event_fn=lambda *args, **kwargs: None,
    )

    assert session_state.completed_source is None
    assert session_state.restart_source is None
    assert len(activities) == 1
    assert "слишком большой" in activities[0].lower()
    assert cleared == [{"filename": "report.docx", "token": "report.docx:12:abc", "storage_path": "restart.bin", "session_id": "session-a"}]


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
