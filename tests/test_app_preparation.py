from types import SimpleNamespace

import docxaicorrector.chapter_workflow.service as chapter_workflow_service
import docxaicorrector.processing.processing_runtime as processing_runtime
import docxaicorrector.ui._app as app
import docxaicorrector.ui.application_flow as application_flow
import docxaicorrector.ui.compare_panel as compare_panel
from docxaicorrector.core.models import StructureRepairReport
from docxaicorrector.document.segments import DocumentContextProfile, DocumentSegment, GlossaryTerm, SegmentBoundaryEvidence, SegmentDetectionReport
from docxaicorrector.structure.validation import StructureValidationReport
from docxaicorrector.ui.i18n import t
from conftest import SessionState as SessionState


class UploadedFileStub:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self.size = len(content)
        self._content = content
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            data = self._content[self._position :]
            self._position = len(self._content)
            return data
        start = self._position
        end = min(len(self._content), start + size)
        self._position = end
        return self._content[start:end]

    def getvalue(self) -> bytes:
        return self._content

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._position = max(0, offset)
        elif whence == 1:
            self._position = max(0, self._position + offset)
        elif whence == 2:
            self._position = max(0, len(self._content) + offset)
        else:
            raise ValueError("Unsupported whence")
        self._position = min(self._position, len(self._content))
        return self._position


def _build_prepared_run_context(**overrides):
    payload = {
        "uploaded_filename": "report.docx",
        "uploaded_file_bytes": b"abc",
        "uploaded_file_token": "report.docx:3:token",
        "source_text": "source-text",
        "paragraphs": ["p1", "p2"],
        "image_assets": [],
        "jobs": [{"target_text": "block one"}, {"target_text": "block two"}],
        "prepared_source_key": "report.docx:3:token:6000",
        "preparation_stage": "Документ подготовлен",
        "preparation_detail": "Анализ завершён. Можно запускать обработку.",
        "preparation_cached": False,
        "preparation_elapsed_seconds": 1.4,
        "normalization_report": None,
        "relation_report": None,
        "cleanup_report": None,
        "structure_repair_report": None,
        "segments": [],
        "segment_diagnostics": SegmentDetectionReport(),
        "structure_fingerprint": "",
        "detector_version": "chapter_segments_v1",
        "segment_to_job": {},
    }
    payload.update(overrides)
    return application_flow.PreparedRunContext(**payload)


class FakeColumn:
    def __init__(self, result=False):
        self.result = result
        self.calls = []

    def button(self, label, **kwargs):
        self.calls.append((label, kwargs))
        return self.result


def _two_stage_columns(first_columns, second_columns):
    state = {"count": 0}

    def fake_columns(n):
        state["count"] += 1
        if state["count"] == 1:
            return list(first_columns)
        return list(second_columns)

    return fake_columns


def test_store_preparation_summary_uses_preparation_context_not_processing_status(monkeypatch):
    session_state = SessionState(
        processing_status={
            "stage": "Ожидание запуска",
            "detail": "stale detail",
            "cached": False,
            "started_at": 1.0,
        }
    )
    prepared_run_context = type("PreparedRunContextStub", (), {
        "uploaded_file_bytes": b"abc",
        "paragraphs": ["p1", "p2"],
        "image_assets": ["img"],
        "source_text": "text-value",
        "jobs": [{"target_text": "block"}],
        "ai_classified_count": 4,
        "ai_heading_count": 2,
        "ai_role_change_count": 1,
        "ai_heading_promotion_count": 1,
        "ai_heading_demotion_count": 0,
        "ai_structural_role_change_count": 1,
        "preparation_stage": "Документ подготовлен",
        "preparation_detail": "Анализ завершён без фонового worker.",
        "preparation_cached": True,
        "preparation_elapsed_seconds": 1.25,
        "normalization_report": type("NormalizationReportStub", (), {
            "total_raw_paragraphs": 3,
            "total_logical_paragraphs": 2,
            "merged_group_count": 1,
            "merged_raw_paragraph_count": 2,
        })(),
        "cleanup_report": type("CleanupReportStub", (), {
            "removed_paragraph_count": 0,
            "removed_page_number_count": 0,
            "removed_repeated_artifact_count": 0,
            "removed_empty_or_whitespace_count": 0,
            "cleanup_mode": "flag",
            "flagged_page_number_count": 2,
            "flagged_repeated_artifact_count": 1,
            "flagged_empty_or_whitespace_count": 0,
        })(),
        "structure_repair_report": StructureRepairReport(
            applied=True,
            repaired_bullet_items=1,
            repaired_numbered_items=1,
            bounded_toc_regions=1,
            toc_body_boundary_repairs=1,
            heading_candidates_from_toc=3,
            remaining_isolated_marker_count=0,
        ),
    })()

    monkeypatch.setattr(app.st, "session_state", session_state)

    app._store_preparation_summary(prepared_run_context=prepared_run_context)

    assert session_state.latest_preparation_summary == {
        "stage": "Документ подготовлен",
        "detail": "Анализ завершён без фонового worker.",
        "file_size_bytes": 3,
        "paragraph_count": 2,
        "image_count": 1,
        "source_chars": len("text-value"),
        "block_count": 1,
        "cached": True,
        "source_format": "docx",
        "conversion_backend": None,
        "quality_gate_status": "pass",
        "elapsed": "1.2 c",
        "progress": 1.0,
        "status_notes": [],
        "raw_paragraph_count": 3,
        "logical_paragraph_count": 2,
        "merged_group_count": 1,
        "merged_raw_paragraph_count": 2,
        "high_confidence_merge_count": 0,
        "medium_accepted_merge_count": 0,
        "medium_rejected_candidate_count": 0,
        "layout_cleanup_removed_count": 3,
        "layout_cleanup_page_number_count": 2,
        "layout_cleanup_repeated_artifact_count": 1,
        "layout_cleanup_empty_or_whitespace_count": 0,
    }


def test_main_restarts_background_preparation_when_chunk_size_changes(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=object(),
        processing_status={},
        activity_feed=[],
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    start_calls = []

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {"reader_cleanup_default": True})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 7000, 3, "safe", True, "audiobook", "auto", "ru", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app, "get_processing_session_snapshot", lambda: type("ProcessingSnapshot", (), {"latest_source_token": ""})())
    monkeypatch.setattr(app, "get_latest_image_mode", lambda: "safe")
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_start_background_preparation", lambda **kwargs: start_calls.append(kwargs))
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    try:
        app.main()
    except RerunRequested:
        pass
    else:
        raise AssertionError("Expected rerun after starting background preparation")

    assert len(start_calls) == 1
    assert start_calls[0]["upload_marker"] == "report.docx:3:ba7816bf8f01cfea:7000:op=audiobook:sl=auto:tl=ru"
    assert start_calls[0]["chunk_size"] == 7000
    assert start_calls[0]["image_mode"] == "safe"
    assert start_calls[0]["keep_all_image_variants"] is True
    assert start_calls[0]["processing_operation"] == "audiobook"
    assert start_calls[0]["app_config"]["processing_operation"] == "audiobook"
    assert start_calls[0]["app_config"]["reader_cleanup_enabled"] is True
    assert isinstance(start_calls[0]["uploaded_payload"], processing_runtime.FrozenUploadPayload)
    assert start_calls[0]["uploaded_payload"].filename == "report.docx"
    assert start_calls[0]["uploaded_payload"].content_bytes == b"abc"
    assert start_calls[0]["uploaded_payload"].file_token == "report.docx:3:ba7816bf8f01cfea"


def test_main_restarts_background_preparation_when_uploaded_file_changes(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=object(),
        processing_status={},
        activity_feed=[],
    )
    uploaded_file = UploadedFileStub("new-report.docx", b"xyz")
    start_calls = []

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app, "get_processing_session_snapshot", lambda: type("ProcessingSnapshot", (), {"latest_source_token": ""})())
    monkeypatch.setattr(app, "get_latest_image_mode", lambda: "safe")
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_start_background_preparation", lambda **kwargs: start_calls.append(kwargs))
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    try:
        app.main()
    except RerunRequested:
        pass
    else:
        raise AssertionError("Expected rerun after starting background preparation")

    assert len(start_calls) == 1
    assert start_calls[0]["chunk_size"] == 6000
    assert start_calls[0]["image_mode"] == "safe"
    assert start_calls[0]["keep_all_image_variants"] is False
    assert start_calls[0]["processing_operation"] == "edit"
    assert isinstance(start_calls[0]["uploaded_payload"], processing_runtime.FrozenUploadPayload)
    assert start_calls[0]["uploaded_payload"].filename == "new-report.docx"
    assert start_calls[0]["uploaded_payload"].content_bytes == b"xyz"
    assert start_calls[0]["uploaded_payload"].file_token != "report.docx:3:ba7816bf8f01cfea"
    assert start_calls[0]["upload_marker"] == f"{start_calls[0]['uploaded_payload'].file_token}:6000"


def test_start_background_processing_passes_translate_context_to_runtime(monkeypatch):
    start_calls = []

    monkeypatch.setattr(app, "start_background_processing", lambda **kwargs: start_calls.append(kwargs))

    app._start_background_processing(
        uploaded_filename="report.docx",
        uploaded_token="report.docx:3:token",
        source_bytes=b"abc",
        jobs=[{"target_text": "block"}],
        source_paragraphs=["p1"],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=3,
        processing_operation="translate",
        source_language="auto",
        target_language="de",
    )

    assert len(start_calls) == 1
    assert start_calls[0]["processing_operation"] == "translate"
    assert start_calls[0]["source_language"] == "auto"
    assert start_calls[0]["target_language"] == "de"


def test_main_normalizes_legacy_doc_before_starting_background_preparation(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
    )
    uploaded_file = UploadedFileStub("legacy.doc", bytes.fromhex("D0CF11E0A1B11AE1") + b"legacy")
    start_calls = []

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", True))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        processing_runtime,
        "_convert_legacy_doc_to_docx",
        lambda **kwargs: (b"converted-docx", "antiword+pandoc"),
    )
    monkeypatch.setattr(app, "_start_background_preparation", lambda **kwargs: start_calls.append(kwargs))
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    try:
        app.main()
    except RerunRequested:
        pass
    else:
        raise AssertionError("Expected rerun after starting background preparation")

    assert len(start_calls) == 1
    assert isinstance(start_calls[0]["uploaded_payload"], processing_runtime.FrozenUploadPayload)
    # Lightweight freeze: legacy DOC keeps original filename/bytes; conversion is
    # deferred to the preparation worker (architectural contract).
    assert start_calls[0]["uploaded_payload"].filename == "legacy.doc"
    assert start_calls[0]["uploaded_payload"].source_format == "doc"
    assert start_calls[0]["uploaded_payload"].conversion_backend is None
    assert start_calls[0]["uploaded_payload"].file_token.startswith("legacy.docx:")
    assert start_calls[0]["upload_marker"].startswith("legacy.docx:")


def test_main_supports_pdf_upload_and_updates_user_facing_copy(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
    )
    uploader_calls = []
    title_calls = []
    write_calls = []
    caption_calls = []

    def file_uploader_stub(*args, **kwargs):
        uploader_calls.append((args, kwargs))
        return None

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda value, *args, **kwargs: title_calls.append(value))
    monkeypatch.setattr(app.st, "write", lambda value, *args, **kwargs: write_calls.append(value))
    monkeypatch.setattr(app.st, "caption", lambda value, *args, **kwargs: caption_calls.append(value))
    monkeypatch.setattr(app.st, "file_uploader", file_uploader_stub)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_finalize_app_frame", lambda **kwargs: None)

    app.main()

    assert title_calls == ["AI-редактор DOCX/DOC/PDF через Markdown"]
    assert any("PDF" in call for call in write_calls)
    assert caption_calls == [
        "PDF импортируется через преобразование в DOCX; качество структуры и форматирования зависит от исходного PDF и конвертера."
    ]
    assert len(uploader_calls) == 1
    assert uploader_calls[0][0][0] == "Загрузите DOCX/DOC/PDF-файл"
    assert uploader_calls[0][1]["type"] == ["docx", "doc", "pdf"]


def test_main_shows_pdf_size_limit_error_copy(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
    )
    uploaded_file = UploadedFileStub("source.pdf", b"%PDF-1.7\ncontent")
    uploaded_file.size = app.MAX_DOCX_ARCHIVE_SIZE_BYTES + 1
    error_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "error", lambda value, *args, **kwargs: error_calls.append(value))
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_finalize_app_frame", lambda **kwargs: None)

    app.main()

    assert error_calls == [
        t("app.file_too_large", limit=app.MAX_DOCX_ARCHIVE_SIZE_BYTES // (1024 * 1024))
    ]


def test_main_reports_pdf_freeze_failure_without_uncaught_streamlit_error(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
    )
    uploaded_file = UploadedFileStub("source.pdf", b"%PDF-1.7\ncontent")
    error_calls = []
    present_error_calls = []
    finalized = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "error", lambda value, *args, **kwargs: error_calls.append(value))
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_finalize_app_frame", lambda **kwargs: finalized.append(kwargs))
    monkeypatch.setattr(app, "freeze_uploaded_file_lightweight", lambda uploaded_file: (_ for _ in ()).throw(RuntimeError("pdf read failed")))
    monkeypatch.setattr(
        app,
        "present_error",
        lambda event, exc, message, **context: present_error_calls.append((event, str(exc), message, context)) or str(exc),
    )

    app.main()

    assert present_error_calls == [
        (
            "document_read_failed",
            "pdf read failed",
            "Ошибка чтения документа",
            {"filename": "source.pdf"},
        )
    ]
    assert error_calls == [t("app.document_read_error", message="pdf read failed")]
    assert finalized == [{}]


def test_main_renders_live_status_during_active_preparation(monkeypatch):
    session_state = SessionState(app_start_logged=True, processing_status={}, activity_feed=[])
    calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: True)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: calls.append("live_status"))
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: calls.append("run_log"))

    app.main()

    assert calls == ["live_status", "run_log"]


def test_main_keeps_processing_panel_visible_while_outcome_is_running(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        processing_outcome="running",
        processing_stop_requested=False,
    )
    calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_intro_layout_styles", lambda: calls.append("intro"))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: calls.append("live_status"))
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: calls.append("run_log"))
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: calls.append("image_summary"))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: calls.append("partial_result"))
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)

    app.main()

    assert calls == ["intro", "live_status", "run_log", "image_summary", "partial_result"]


def test_main_renders_current_preparation_failure_without_restarting(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={"stage": "Ошибка подготовки", "detail": "bad archive", "phase": "preparing"},
        activity_feed=[],
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="report.docx:3:ba7816bf8f01cfea:6000",
        prepared_run_context=None,
        last_error="bad archive",
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    error_calls = []
    calls = []
    start_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda value, *args, **kwargs: error_calls.append(value))
    monkeypatch.setattr(app.st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: calls.append("live_status"))
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: calls.append("run_log"))
    monkeypatch.setattr(app, "_finalize_app_frame", lambda **kwargs: calls.append("finalize"))
    monkeypatch.setattr(app, "_start_background_preparation", lambda **kwargs: start_calls.append(kwargs))
    monkeypatch.setattr(app, "get_prepared_run_context_for_marker", lambda marker: None)
    monkeypatch.setattr(app, "should_start_preparation_for_marker", lambda marker: False)
    monkeypatch.setattr(app, "is_preparation_failed_for_marker", lambda marker: True)
    monkeypatch.setattr(
        application_flow,
        "prepare_run_context",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")),
    )

    app.main()

    assert error_calls == ["bad archive"]
    assert start_calls == []
    assert calls == ["live_status", "run_log", "finalize"]


def test_main_retry_button_clears_failure_and_reruns_in_failed_branch(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={"stage": "Ошибка подготовки", "detail": "bad archive", "phase": "preparing"},
        activity_feed=[],
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="report.docx:3:ba7816bf8f01cfea:6000",
        prepared_run_context=None,
        last_error="bad archive",
        last_background_error={"kind": "bad archive"},
        processing_outcome="failed",
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    button_calls = []
    clear_calls = []

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "button", lambda label, *args, **kwargs: button_calls.append(label) or True)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_finalize_app_frame", lambda **kwargs: None)
    monkeypatch.setattr(app, "get_prepared_run_context_for_marker", lambda marker: None)
    monkeypatch.setattr(app, "should_start_preparation_for_marker", lambda marker: False)
    monkeypatch.setattr(app, "is_preparation_failed_for_marker", lambda marker: True)
    monkeypatch.setattr(
        app,
        "clear_preparation_failure",
        lambda marker: clear_calls.append(marker),
    )
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    try:
        app.main()
    except RerunRequested:
        pass
    else:
        raise AssertionError("Expected rerun after clearing preparation failure via retry")

    assert button_calls == [t("app.button_reprocess")]
    assert clear_calls == ["report.docx:3:ba7816bf8f01cfea:6000"]


def test_main_warns_when_current_preparation_state_is_unavailable(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={"stage": "Подготовка", "detail": "ожидание state", "phase": "preparing"},
        activity_feed=[],
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=None,
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    warning_calls = []
    calls = []
    start_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda value, *args, **kwargs: warning_calls.append(value))
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected error render")))
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: calls.append("live_status"))
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: calls.append("run_log"))
    monkeypatch.setattr(app, "_finalize_app_frame", lambda **kwargs: calls.append("finalize"))
    monkeypatch.setattr(app, "_start_background_preparation", lambda **kwargs: start_calls.append(kwargs))
    monkeypatch.setattr(app, "get_prepared_run_context_for_marker", lambda marker: None)
    monkeypatch.setattr(app, "should_start_preparation_for_marker", lambda marker: False)
    monkeypatch.setattr(app, "is_preparation_failed_for_marker", lambda marker: False)
    monkeypatch.setattr(
        application_flow,
        "prepare_run_context",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")),
    )

    app.main()

    assert warning_calls == [t("app.preparation_state_unavailable")]
    assert start_calls == []
    assert calls == ["live_status", "run_log", "finalize"]


def test_main_keeps_completed_view_with_shared_layout(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        image_assets=[],
        latest_docx_bytes=b"docx-bytes",
        latest_source_token="report.docx:3:token",
        latest_markdown="# markdown",
        latest_image_mode="safe",
        last_error="",
        last_log_hint="",
        processing_outcome="succeeded",
    )
    calls = []
    completed_result = {
        "docx_bytes": b"docx-bytes",
        "markdown_text": "# markdown",
        "source_name": "report.docx",
        "processing_operation": "edit",
        "audiobook_postprocess_enabled": False,
    }

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: completed_result)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_intro_layout_styles", lambda: calls.append("intro"))
    monkeypatch.setattr(app.st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: calls.append("run_log"))
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: calls.append("image_summary"))
    monkeypatch.setattr(app, "render_markdown_preview", lambda *args, **kwargs: calls.append("markdown_preview"))
    monkeypatch.setattr(app, "render_result_bundle", lambda **kwargs: calls.append("result_bundle"))
    monkeypatch.setattr(app, "_finalize_app_frame", lambda **kwargs: calls.append("finalize"))
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: True)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "completed")

    app.main()

    assert calls == ["intro", "run_log", "image_summary", "markdown_preview", "result_bundle", "finalize"]


def test_main_passes_completed_result_bundle_mode_metadata_to_renderer(monkeypatch):
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        image_assets=[],
        latest_docx_bytes=b"docx-bytes",
        latest_source_token="report.docx:3:token",
        latest_markdown="# markdown",
        latest_image_mode="safe",
        last_error="",
        last_log_hint="",
        processing_outcome="succeeded",
    )
    captured = {}
    completed_result = {
        "docx_bytes": b"docx-bytes",
        "markdown_text": "# markdown",
        "source_name": "report.docx",
        "narration_text": "[thoughtful] narration",
        "processing_operation": "translate",
        "audiobook_postprocess_enabled": True,
    }

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: completed_result)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_intro_layout_styles", lambda: None)
    monkeypatch.setattr(app.st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_markdown_preview", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_result_bundle", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(app, "_finalize_app_frame", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: True)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "completed")

    app.main()

    assert captured["docx_bytes"] == b"docx-bytes"
    assert captured["markdown_text"] == "# markdown"
    assert captured["original_filename"] == "report.docx"
    assert captured["narration_text"] == "[thoughtful] narration"
    assert captured["processing_operation"] == "translate"
    assert captured["audiobook_postprocess_enabled"] is True


def test_main_renders_preparation_summary_for_prepared_file(monkeypatch):
    prepared_run_context = _build_prepared_run_context(
        preparation_cached=True,
        normalization_report=type("NormalizationReportStub", (), {
            "total_raw_paragraphs": 4,
            "total_logical_paragraphs": 3,
            "merged_group_count": 1,
            "merged_raw_paragraph_count": 2,
        })(),
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        image_assets=[],
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=prepared_run_context,
        latest_docx_bytes=None,
        latest_source_token="",
        latest_markdown="",
        latest_image_mode="safe",
        last_error="",
        last_log_hint="hint",
        processing_outcome="idle",
    )
    summary_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app, "get_processing_session_snapshot", lambda: type("ProcessingSnapshot", (), {"latest_source_token": ""})())
    monkeypatch.setattr(app, "get_latest_image_mode", lambda: "safe")
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_preparation_summary", lambda summary, *args, **kwargs: summary_calls.append(summary))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "file_selected")
    monkeypatch.setattr(application_flow, "prepare_run_context", lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")))

    app.main()

    assert len(summary_calls) == 1
    expected_summary = dict(session_state.latest_preparation_summary)
    if "status_notes" in summary_calls[0]:
        expected_summary["status_notes"] = summary_calls[0]["status_notes"]
    assert summary_calls[0] == expected_summary
    assert summary_calls[0]["cached"] is True
    assert summary_calls[0]["block_count"] == 2
    assert summary_calls[0]["raw_paragraph_count"] == 4
    assert summary_calls[0]["logical_paragraph_count"] == 3
    assert summary_calls[0]["merged_group_count"] == 1
    assert summary_calls[0]["merged_raw_paragraph_count"] == 2
    assert summary_calls[0]["high_confidence_merge_count"] == 0
    assert summary_calls[0]["medium_accepted_merge_count"] == 0
    assert summary_calls[0]["medium_rejected_candidate_count"] == 0


def test_main_marks_prepared_status_with_completed_terminal_kind(monkeypatch):
    prepared_run_context = _build_prepared_run_context(
        normalization_report=type("NormalizationReportStub", (), {
            "total_raw_paragraphs": 4,
            "total_logical_paragraphs": 3,
            "merged_group_count": 1,
            "merged_raw_paragraph_count": 2,
        })(),
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        image_assets=[],
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=prepared_run_context,
        latest_docx_bytes=None,
        latest_source_token="",
        latest_markdown="",
        latest_image_mode="safe",
        last_error="",
        last_log_hint="hint",
        processing_outcome="idle",
    )
    status_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_preparation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)
    monkeypatch.setattr(app, "set_processing_status", lambda **kwargs: status_calls.append(kwargs))
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "file_selected")
    monkeypatch.setattr(application_flow, "prepare_run_context", lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")))

    app.main()

    assert len(status_calls) == 1
    assert status_calls[0]["stage"] == "Документ подготовлен"
    assert status_calls[0]["phase"] == "preparing"
    assert status_calls[0]["terminal_kind"] == "completed"
    assert status_calls[0]["raw_paragraph_count"] == 4
    assert status_calls[0]["logical_paragraph_count"] == 3
    assert status_calls[0]["merged_group_count"] == 1
    assert status_calls[0]["merged_raw_paragraph_count"] == 2


def test_main_ignores_stale_completed_result_for_different_uploaded_file(monkeypatch):
    prepared_run_context = _build_prepared_run_context(
        uploaded_filename="new.docx",
        uploaded_file_bytes=b"abc",
        uploaded_file_token="new.docx:3:new",
        prepared_source_key="new.docx:3:new:6000",
    )
    uploaded_file = UploadedFileStub("new.docx", b"abc")
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        image_assets=[],
        preparation_input_marker="new.docx:3:new:6000",
        preparation_failed_marker="",
        prepared_run_context=prepared_run_context,
        latest_docx_bytes=b"old-docx-bytes",
        latest_source_token="old.docx:3:old",
        latest_markdown="# old markdown",
        latest_image_mode="safe",
        last_error="",
        last_log_hint="hint",
        processing_outcome="succeeded",
    )
    summary_calls = []
    result_bundle_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(
        app,
        "get_current_result_bundle",
        lambda: {
            "docx_bytes": b"old-docx-bytes",
            "markdown_text": "# old markdown",
            "source_name": "old.docx",
            "source_token": "old.docx:3:old",
            "processing_operation": "edit",
            "audiobook_postprocess_enabled": False,
        },
    )
    monkeypatch.setattr(app, "get_processing_session_snapshot", lambda: type("ProcessingSnapshot", (), {"latest_source_token": "old.docx:3:old"})())
    monkeypatch.setattr(app, "get_latest_image_mode", lambda: "safe")
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(app, "render_preparation_summary", lambda summary, *args, **kwargs: summary_calls.append(summary))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)
    monkeypatch.setattr(app, "render_markdown_preview", lambda *args, **kwargs: result_bundle_calls.append("markdown_preview"))
    monkeypatch.setattr(app, "render_result", lambda *args, **kwargs: result_bundle_calls.append((args, kwargs)))
    monkeypatch.setattr(app, "render_result_bundle", lambda **kwargs: result_bundle_calls.append(kwargs))
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(app, "get_prepared_run_context_for_marker", lambda marker: prepared_run_context)
    monkeypatch.setattr(app, "should_start_preparation_for_marker", lambda marker: False)
    monkeypatch.setattr(app, "is_preparation_failed_for_marker", lambda marker: False)
    monkeypatch.setattr(
        application_flow,
        "prepare_run_context",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")),
    )

    app.main()

    assert len(summary_calls) == 1
    assert result_bundle_calls == []


def test_store_preparation_summary_includes_exported_structure_manifest_path(monkeypatch):
    session_state = SessionState()
    prepared_run_context = _build_prepared_run_context(
        exported_structure_manifest_path=".run/structure_manifests/20260506_094000_report.segments.json",
    )

    monkeypatch.setattr(app.st, "session_state", session_state)

    app._store_preparation_summary(prepared_run_context=prepared_run_context)

    assert session_state.latest_preparation_summary["manifest_path"] == ".run/structure_manifests/20260506_094000_report.segments.json"
    assert "Structure manifest: .run/structure_manifests/20260506_094000_report.segments.json" in session_state.latest_preparation_summary["status_notes"]


def test_store_preparation_summary_includes_segment_detection_metrics(monkeypatch):
    session_state = SessionState()
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        detector_version="chapter_segments_v1",
        segments=[DocumentSegment(segment_id="seg_0001")],
        segment_diagnostics=SegmentDetectionReport(
            segment_count=1,
            high_confidence_count=1,
            medium_confidence_count=2,
            low_confidence_count=3,
            toc_entry_count=7,
            toc_matched_count=5,
        ),
    )

    monkeypatch.setattr(app.st, "session_state", session_state)

    app._store_preparation_summary(prepared_run_context=prepared_run_context)

    assert session_state.latest_preparation_summary["structure_fingerprint"] == "abc123def456"
    assert session_state.latest_preparation_summary["detector_version"] == "chapter_segments_v1"
    assert session_state.latest_preparation_summary["segment_count"] == 1
    assert session_state.latest_preparation_summary["high_confidence_count"] == 1
    assert session_state.latest_preparation_summary["medium_confidence_count"] == 2
    assert session_state.latest_preparation_summary["low_confidence_count"] == 3
    assert session_state.latest_preparation_summary["toc_entry_count"] == 7
    assert session_state.latest_preparation_summary["toc_matched_count"] == 5


def test_store_preparation_summary_leaves_prepared_context_data_unchanged(monkeypatch):
    session_state = SessionState()
    prepared_run_context = _build_prepared_run_context(
        paragraphs=["p1", "p2", "p3"],
        jobs=[{"target_text": "block one"}, {"target_text": "block two"}],
        segments=[DocumentSegment(segment_id="seg_0001"), DocumentSegment(segment_id="seg_0002")],
        structure_fingerprint="abc123def456",
    )

    # Snapshot the load-bearing preparation OUTPUT before rendering-only summary work runs.
    paragraphs_before = list(prepared_run_context.paragraphs)
    jobs_before = [dict(job) for job in prepared_run_context.jobs]
    segment_ids_before = [segment.segment_id for segment in prepared_run_context.segments]
    fingerprint_before = prepared_run_context.structure_fingerprint

    monkeypatch.setattr(app.st, "session_state", session_state)

    app._store_preparation_summary(prepared_run_context=prepared_run_context)

    # Preparation output must be byte-identical: the summary only surfaces it, never mutates it.
    assert list(prepared_run_context.paragraphs) == paragraphs_before
    assert [dict(job) for job in prepared_run_context.jobs] == jobs_before
    assert [segment.segment_id for segment in prepared_run_context.segments] == segment_ids_before
    assert prepared_run_context.structure_fingerprint == fingerprint_before
    # And the summary still carries the same data for downstream engineer artifacts.
    summary = session_state.latest_preparation_summary
    assert summary["paragraph_count"] == len(paragraphs_before)
    assert summary["block_count"] == len(jobs_before)
    assert summary["segment_count"] == len(segment_ids_before)
    assert summary["structure_fingerprint"] == fingerprint_before


def test_main_starts_full_document_processing_from_bottom_control(monkeypatch):
    prepared_run_context = _build_prepared_run_context(
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=1,
                start_paragraph_id="p0000",
                end_paragraph_id="p0001",
                paragraph_ids=("p0000", "p0001"),
                paragraph_count=2,
                char_count=100,
                word_count=20,
                estimated_token_count=25,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="beefcafe",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            )
        ],
    )
    uploaded_file = UploadedFileStub("report.docx", b"abc")
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
        image_assets=[],
        preparation_input_marker="report.docx:3:ba7816bf8f01cfea:6000",
        preparation_failed_marker="",
        prepared_run_context=prepared_run_context,
        latest_docx_bytes=None,
        latest_source_token="",
        latest_markdown="",
        latest_image_mode="safe",
        last_error="",
        last_log_hint="hint",
        processing_outcome="idle",
    )
    start_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {"reader_cleanup_default": True})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app, "get_processing_session_snapshot", lambda: type("ProcessingSnapshot", (), {"latest_source_token": ""})())
    monkeypatch.setattr(app, "get_latest_image_mode", lambda: "safe")
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})())
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "button", lambda *args, **kwargs: False)
    # seg_0001 is pending, so the analysis panel no longer offers a full-document
    # start; the panel returns None and the full-document start is driven by the
    # bottom "Начать обработку" control (_render_processing_controls -> "start").
    monkeypatch.setattr(app.st, "container", lambda *args, **kwargs: FakeColumn(result=False))
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=True)],
        ),
    )
    monkeypatch.setattr(app, "render_preparation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: "start")
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "file_selected")
    monkeypatch.setattr(application_flow, "prepare_run_context", lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")))
    monkeypatch.setattr(app, "_start_background_processing", lambda **kwargs: start_calls.append(kwargs))

    app.main()

    assert len(start_calls) == 1
    assert start_calls[0]["uploaded_filename"] == "report.docx"
    assert start_calls[0]["uploaded_token"] == "report.docx:3:token"
    assert start_calls[0]["jobs"] == prepared_run_context.jobs
    assert start_calls[0]["output_mode"] == "legacy_full_document"
    assert start_calls[0]["app_config"]["reader_cleanup_enabled"] is True


def test_main_uses_lightweight_freeze_for_pdf_upload(monkeypatch):
    """UI wiring contract: PDF upload on main thread MUST go through
    `freeze_uploaded_file_lightweight` (no LibreOffice on main thread).
    The eager `freeze_uploaded_file` must NOT be called from `app.main()`.
    """
    session_state = SessionState(
        app_start_logged=True,
        processing_status={},
        activity_feed=[],
    )
    uploaded_file = UploadedFileStub("source.pdf", b"%PDF-1.7\nfake")
    start_calls = []
    eager_calls = []
    lightweight_calls = []

    class RerunRequested(Exception):
        pass

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 6000, 3, "safe", False))
    monkeypatch.setattr(app, "_drain_processing_events", lambda: None)
    monkeypatch.setattr(app, "_drain_preparation_events", lambda: None)
    monkeypatch.setattr(app, "_processing_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "_preparation_worker_is_active", lambda: False)
    monkeypatch.setattr(app, "get_current_result_bundle", lambda: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "error", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "file_uploader", lambda *args, **kwargs: uploaded_file)
    monkeypatch.setattr(app.st, "fragment", lambda **kw: (lambda fn: fn))
    monkeypatch.setattr(app, "render_live_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_finalize_app_frame", lambda **kwargs: None)
    monkeypatch.setattr(app, "_start_background_preparation", lambda **kwargs: start_calls.append(kwargs))
    monkeypatch.setattr(app.st, "rerun", lambda: (_ for _ in ()).throw(RerunRequested()))

    real_lightweight = processing_runtime.freeze_uploaded_file_lightweight

    def _spy_lightweight(uploaded):
        lightweight_calls.append(uploaded)
        return real_lightweight(uploaded)

    def _eager_guard(uploaded):
        eager_calls.append(uploaded)
        raise AssertionError(
            "freeze_uploaded_file (eager) must not be called from main thread for PDF uploads"
        )

    monkeypatch.setattr(app, "freeze_uploaded_file_lightweight", _spy_lightweight)
    monkeypatch.setattr(app, "freeze_uploaded_file", _eager_guard)
    monkeypatch.setattr(processing_runtime, "freeze_uploaded_file", _eager_guard)

    try:
        app.main()
    except RerunRequested:
        pass

    assert eager_calls == []
    assert len(lightweight_calls) == 1
    assert len(start_calls) == 1
    payload = start_calls[0]["uploaded_payload"]
    assert isinstance(payload, processing_runtime.FrozenUploadPayload)
    # Lightweight payload preserves original PDF bytes; conversion is deferred to worker.
    assert payload.source_format == "pdf"
    assert payload.conversion_backend is None
    assert payload.content_bytes == b"%PDF-1.7\nfake"
