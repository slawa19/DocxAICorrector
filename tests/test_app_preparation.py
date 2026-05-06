import docxaicorrector.processing.processing_runtime as processing_runtime
import docxaicorrector.ui._app as app
import docxaicorrector.ui.application_flow as application_flow
import docxaicorrector.ui.compare_panel as compare_panel
from docxaicorrector.core.models import StructureRecognitionSummary
from docxaicorrector.core.models import StructureRepairReport
from docxaicorrector.document.segments import DocumentSegment, SegmentBoundaryEvidence, SegmentDetectionReport
from docxaicorrector.structure.validation import StructureValidationReport
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
        "structure_map": None,
        "structure_recognition_summary": StructureRecognitionSummary(),
        "structure_validation_report": None,
        "structure_recognition_mode": "off",
        "structure_ai_attempted": False,
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
            "removed_paragraph_count": 3,
            "removed_page_number_count": 2,
            "removed_repeated_artifact_count": 1,
            "removed_empty_or_whitespace_count": 0,
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
        "ai_classified": 4,
        "ai_headings": 2,
        "ai_role_changes": 1,
        "ai_heading_promotions": 1,
        "ai_heading_demotions": 0,
        "ai_structural_role_changes": 1,
        "elapsed": "1.2 c",
        "progress": 1.0,
        "status_notes": [
            "Структура: AI выключен, использованы текущие правила.",
            "Восстановление структуры: списки 2, TOC-регионов 1, подсказок заголовков 3.",
            "Очистка: удалено 3 служебных элементов (2 номеров страниц, 1 повторяющихся колонтитулов, 0 пустых абзацев).",
        ],
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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
    monkeypatch.setattr(app, "_cached_load_app_config", lambda: {})
    monkeypatch.setattr(app, "render_sidebar", lambda config: ("gpt-5.4", 7000, 3, "safe", True, "audiobook", "auto", "ru", False, False))
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
    assert start_calls[0]["upload_marker"] == "report.docx:3:ba7816bf8f01cfea:7000:op=audiobook"
    assert start_calls[0]["chunk_size"] == 7000
    assert start_calls[0]["image_mode"] == "safe"
    assert start_calls[0]["keep_all_image_variants"] is True
    assert start_calls[0]["processing_operation"] == "audiobook"
    assert start_calls[0]["app_config"]["processing_operation"] == "audiobook"
    assert isinstance(start_calls[0]["uploaded_payload"], processing_runtime.FrozenUploadPayload)
    assert start_calls[0]["uploaded_payload"].filename == "report.docx"
    assert start_calls[0]["uploaded_payload"].content_bytes == b"abc"
    assert start_calls[0]["uploaded_payload"].file_token == "report.docx:3:ba7816bf8f01cfea"


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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    assert start_calls[0]["uploaded_payload"].filename == "legacy.docx"
    assert start_calls[0]["uploaded_payload"].content_bytes == b"converted-docx"
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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
        f"Размер DOCX/DOC/PDF превышает допустимый предел {app.MAX_DOCX_ARCHIVE_SIZE_BYTES // (1024 * 1024)} МБ. Загрузите файл меньшего размера."
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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app, "freeze_uploaded_file", lambda uploaded_file: (_ for _ in ()).throw(RuntimeError("pdf converter missing")))
    monkeypatch.setattr(
        app,
        "present_error",
        lambda event, exc, message, **context: present_error_calls.append((event, str(exc), message, context)) or str(exc),
    )

    app.main()

    assert present_error_calls == [
        (
            "document_read_failed",
            "pdf converter missing",
            "Ошибка чтения документа",
            {"filename": "source.pdf"},
        )
    ]
    assert error_calls == ["Ошибка чтения документа: pdf converter missing"]
    assert finalized == [{}]


def test_main_renders_live_status_during_active_preparation(monkeypatch):
    session_state = SessionState(app_start_logged=True, processing_status={}, activity_feed=[])
    calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)

    app.main()

    assert calls == ["intro", "live_status", "run_log", "image_summary", "partial_result"]


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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app, "render_file_uploader_state_styles", lambda **kwargs: None)
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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app, "render_file_uploader_state_styles", lambda **kwargs: None)
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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
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
    assert summary_calls[0]["ai_classified"] == 0
    assert summary_calls[0]["ai_headings"] == 0
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
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
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


def test_store_preparation_summary_includes_auto_structure_status_note(monkeypatch):
    session_state = SessionState()
    prepared_run_context = _build_prepared_run_context(
        structure_recognition_mode="auto",
        structure_ai_attempted=True,
        structure_map=object(),
        structure_recognition_summary=StructureRecognitionSummary(ai_classified_count=6, ai_heading_count=2),
        structure_validation_report=StructureValidationReport(
            paragraph_count=50,
            nonempty_paragraph_count=50,
            explicit_heading_count=0,
            heuristic_heading_count=0,
            suspicious_short_body_count=8,
            all_caps_body_count=0,
            centered_body_count=0,
            toc_like_sequence_count=1,
            ambiguous_paragraph_count=8,
            explicit_heading_density=0.0,
            suspicious_short_body_ratio=0.16,
            all_caps_or_centered_body_ratio=0.0,
            escalation_recommended=True,
            escalation_reasons=("low_explicit_heading_density", "toc_like_sequence_detected"),
            isolated_marker_paragraph_count=0,
            large_front_matter_block_risk=False,
            toc_region_bounded_count=1,
            expected_heading_candidates_from_toc=4,
            structure_quality_risk_level="high",
            readiness_status="ready_with_warnings",
            readiness_reasons=(),
        ),
    )

    monkeypatch.setattr(app.st, "session_state", session_state)

    app._store_preparation_summary(prepared_run_context=prepared_run_context)

    assert session_state.latest_preparation_summary["status_notes"] == [
        "Структура: auto-режим, выполнена эскалация в AI; классифицировано 6 абзацев, найдено 2 заголовков. Причины: мало явных заголовков, обнаружен TOC-подобный фрагмент."
    ]


def test_store_preparation_summary_includes_exported_structure_manifest_path(monkeypatch):
    session_state = SessionState()
    prepared_run_context = _build_prepared_run_context(
        exported_structure_manifest_path=".run/structure_manifests/20260506_094000_report.segments.json",
    )

    monkeypatch.setattr(app.st, "session_state", session_state)

    app._store_preparation_summary(prepared_run_context=prepared_run_context)

    assert session_state.latest_preparation_summary["manifest_path"] == ".run/structure_manifests/20260506_094000_report.segments.json"
    assert "Structure manifest: .run/structure_manifests/20260506_094000_report.segments.json" in session_state.latest_preparation_summary["status_notes"]


def test_store_preparation_summary_includes_structure_review_metrics(monkeypatch):
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


def test_main_exports_structure_manifest_from_prepared_state(monkeypatch):
    prepared_run_context = _build_prepared_run_context()
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
    render_calls = []
    export_calls = []
    notice_calls = []
    reruns = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app.st, "button", lambda label, **kwargs: label == "Export Structure Manifest")
    monkeypatch.setattr(app, "render_preparation_summary", lambda summary, *args, **kwargs: render_calls.append(summary))
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: None)
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "file_selected")
    monkeypatch.setattr(application_flow, "prepare_run_context", lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")))
    def fake_export_structure_manifest(**kwargs):
        export_calls.append(kwargs)
        kwargs["prepared_run_context"].exported_structure_manifest_path = ".run/structure_manifests/20260506_094000_report.segments.json"
        return ".run/structure_manifests/20260506_094000_report.segments.json"

    monkeypatch.setattr(application_flow, "export_structure_manifest", fake_export_structure_manifest)
    monkeypatch.setattr(app, "set_structure_manifest_notice", lambda **kwargs: notice_calls.append(kwargs))
    monkeypatch.setattr(app, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "rerun", lambda: reruns.append(True))

    app.main()

    assert len(render_calls) == 1
    assert len(export_calls) == 1
    assert export_calls[0]["app_config"]["chunk_size"] == 6000
    assert notice_calls == [{
        "file_token": "report.docx:3:token",
        "details": {
            "file_token": "report.docx:3:token",
            "manifest_path": ".run/structure_manifests/20260506_094000_report.segments.json",
            "structure_fingerprint": "",
        },
    }]
    assert reruns


def test_render_analysis_review_panel_renders_selector_and_disabled_process_selected(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
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
                boundary_evidence=(
                    SegmentBoundaryEvidence(source="heading_style", confidence="high", details={"heading_level": 1}),
                ),
            )
        ],
        segment_diagnostics=SegmentDetectionReport(segment_count=1, toc_entry_count=1, toc_matched_count=1),
        segment_to_job={"seg_0001": (0, 1)},
    )
    confirm_col = FakeColumn(result=False)
    selected_col = FakeColumn(result=False)
    full_book_col = FakeColumn(result=False)
    checkbox_calls = []
    info_calls = []
    subheader_calls = []
    caption_calls = []
    expander_calls = []
    write_calls = []
    selectbox_calls = []
    text_input_calls = []

    class FakeExpander:
        def __init__(self, label, expanded):
            expander_calls.append((label, expanded))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    bulk_select_col = FakeColumn(result=False)
    bulk_clear_col = FakeColumn(result=False)
    bulk_all_col = FakeColumn(result=False)

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [bulk_select_col, bulk_clear_col, bulk_all_col],
            [confirm_col, selected_col, full_book_col],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: checkbox_calls.append((label, kwargs)) or kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: selectbox_calls.append((label, tuple(options), index)) or options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: text_input_calls.append((label, value)) or value)
    monkeypatch.setattr(app.st, "info", lambda message, **kwargs: info_calls.append(message))
    monkeypatch.setattr(app.st, "subheader", lambda message, **kwargs: subheader_calls.append(message))
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: caption_calls.append(message))
    monkeypatch.setattr(app.st, "expander", lambda label, expanded=False, **kwargs: FakeExpander(label, expanded))
    monkeypatch.setattr(app.st, "write", lambda message, **kwargs: write_calls.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)

    action = app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert action is None
    assert subheader_calls == ["Chapter Selector"]
    assert caption_calls[0] == "Structure fingerprint: abc123def456"
    assert caption_calls[1] == "Detector version: chapter_segments_v1"
    assert selectbox_calls == [("Status Filter", ("All segments", "Pending", "Queued", "Processing", "Completed", "Failed", "Skipped", "Low confidence"), 0)]
    assert text_input_calls == [("Search Chapters", "")]
    assert checkbox_calls and checkbox_calls[0][1]["value"] is True
    assert expander_calls == [("Boundary preview: Chapter 1", False)]
    assert any(message == "Starts: p1" for message in caption_calls)
    assert any(message == "Ends: p2" for message in caption_calls)
    assert any(message == "Boundary fingerprint: beefcafe" for message in caption_calls)
    assert write_calls == ["Boundary evidence:"]
    assert selected_col.calls == [(
        "Process Selected",
        {
            "use_container_width": True,
            "disabled": True,
            "help": "Process Selected unavailable: confirm the current outline before running the current chapter selection.",
            "key": "process_selected_button",
        },
    )]
    assert full_book_col.calls == [(
        "Process Entire Book",
        {
            "type": "primary",
            "use_container_width": True,
            "key": "process_entire_book_button",
        },
    )]
    assert any("Selected: 1/1 segments" in message for message in info_calls)
    assert any("Confidence H/M/L:" in message for message in info_calls)
    assert any("TOC matched: 1/1" in message for message in info_calls)
    assert any(
        message == "Structure not confirmed. Process Selected stays disabled until the current outline is reviewed and confirmed."
        for message in caption_calls
    )
    assert any(
        message == "Current selection is ready for review, but chapter-based processing stays disabled until confirmation."
        for message in caption_calls
    )


def test_render_analysis_review_panel_renders_bulk_selection_buttons(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            )
        ],
        segment_to_job={"seg_0001": (0,)},
    )
    bulk_select_col = FakeColumn(result=False)
    bulk_clear_col = FakeColumn(result=False)
    bulk_all_col = FakeColumn(result=False)
    confirm_col = FakeColumn(result=False)
    selected_col = FakeColumn(result=False)
    full_book_col = FakeColumn(result=False)

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    columns_calls = []

    def fake_columns(count):
        columns_calls.append(count)
        if len(columns_calls) == 1:
            return [bulk_select_col, bulk_clear_col, bulk_all_col]
        return [confirm_col, selected_col, full_book_col]

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", fake_columns)
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert columns_calls == [3, 3]
    assert bulk_select_col.calls == [(
        "Select Visible",
        {
            "use_container_width": True,
            "disabled": False,
            "key": "select_visible_segments_button",
        },
    )]
    assert bulk_clear_col.calls == [(
        "Clear Visible",
        {
            "use_container_width": True,
            "disabled": False,
            "key": "clear_visible_segments_button",
        },
    )]
    assert bulk_all_col.calls == [(
        "Select Entire Book",
        {
            "use_container_width": True,
            "disabled": False,
            "key": "select_entire_book_segments_button",
        },
    )]


def test_render_analysis_review_panel_filters_segments_by_status_and_search(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001", "seg_0002"],
        segment_status_by_id={"seg_0001": "completed", "seg_0002": "failed"},
        segment_progress_by_id={"seg_0001": 1.0, "seg_0002": 0.0},
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
        chapter_selector_search="",
        chapter_selector_filter="all",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_0002",
                ordinal=2,
                level=1,
                title="Appendix Notes",
                normalized_title="appendix notes",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="appendix",
                confidence="high",
                boundary_fingerprint="fp2",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
                warnings=("Needs review",),
            ),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,)},
    )
    checkbox_labels = []
    info_calls = []
    caption_calls = []
    selectbox_values = iter(["Failed"])

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: checkbox_labels.append(label) or kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: next(selectbox_values))
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: "appendix")
    monkeypatch.setattr(app.st, "info", lambda message, **kwargs: info_calls.append(message))
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: caption_calls.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert checkbox_labels == [
        "Appendix Notes | 2 words | high | appendix | approx. 1 jobs | failed 0%"
    ]
    assert session_state.chapter_selector_filter == "failed"
    assert session_state.chapter_selector_search == "appendix"
    assert session_state.selected_segment_ids == ["seg_0001", "seg_0002"]
    assert any(message == "Visible segments: 1/2" for message in caption_calls)
    assert any("Selected: 2/2 segments" in message for message in info_calls)


def test_render_analysis_review_panel_shows_empty_filter_result_notice(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        segment_status_by_id={"seg_0001": "pending"},
        segment_progress_by_id={"seg_0001": 0.0},
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            )
        ],
        segment_to_job={"seg_0001": (0,)},
    )
    info_calls = []

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: (_ for _ in ()).throw(AssertionError("checkbox should not render when filter is empty")))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: "Completed")
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: "missing")
    monkeypatch.setattr(app.st, "info", lambda message, **kwargs: info_calls.append(message))
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert "No segments match the current filter/search." in info_calls


def test_render_analysis_review_panel_disables_locked_segment_checkboxes(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001", "seg_0002"],
        segment_status_by_id={"seg_0001": "queued", "seg_0002": "processing", "seg_0003": "pending"},
        segment_progress_by_id={"seg_0001": 0.0, "seg_0002": 0.5, "seg_0003": 0.0},
        active_segment_id="seg_0002",
        active_segment_title="Chapter 2",
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_0002",
                ordinal=2,
                level=1,
                title="Chapter 2",
                normalized_title="chapter 2",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp2",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_0003",
                ordinal=3,
                level=1,
                title="Chapter 3",
                normalized_title="chapter 3",
                start_paragraph_index=2,
                end_paragraph_index=2,
                start_paragraph_id="p0002",
                end_paragraph_id="p0002",
                paragraph_ids=("p0002",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp3",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,), "seg_0003": (2,)},
    )
    checkbox_calls = []
    caption_calls = []

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: checkbox_calls.append((label, kwargs)) or kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: caption_calls.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert checkbox_calls[0][1]["disabled"] is True
    assert checkbox_calls[1][1]["disabled"] is True
    assert checkbox_calls[2][1]["disabled"] is False
    assert any(message == "Locked while queued/processing: 2" for message in caption_calls)


def test_render_analysis_review_panel_supports_skipped_status_filter(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001", "seg_0002"],
        segment_status_by_id={"seg_0001": "skipped", "seg_0002": "pending"},
        segment_progress_by_id={"seg_0001": 0.0, "seg_0002": 0.0},
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Appendix A",
                normalized_title="appendix a",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="appendix",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_0002",
                ordinal=2,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp2",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,)},
    )
    checkbox_labels = []

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: checkbox_labels.append(label) or kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: "Skipped")
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert checkbox_labels == [
        "Appendix A | 2 words | high | appendix | approx. 1 jobs | skipped"
    ]


def test_render_analysis_review_panel_select_visible_updates_selection(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        segment_status_by_id={"seg_0001": "completed", "seg_0002": "pending", "seg_0003": "queued"},
        segment_progress_by_id={"seg_0001": 1.0, "seg_0002": 0.0, "seg_0003": 0.0},
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(segment_id="seg_0001", ordinal=1, level=1, title="Chapter 1", normalized_title="chapter 1", start_paragraph_index=0, end_paragraph_index=0, start_paragraph_id="p0000", end_paragraph_id="p0000", paragraph_ids=("p0000",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp1", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0002", ordinal=2, level=1, title="Chapter 2", normalized_title="chapter 2", start_paragraph_index=1, end_paragraph_index=1, start_paragraph_id="p0001", end_paragraph_id="p0001", paragraph_ids=("p0001",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp2", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0003", ordinal=3, level=1, title="Chapter 3", normalized_title="chapter 3", start_paragraph_index=2, end_paragraph_index=2, start_paragraph_id="p0002", end_paragraph_id="p0002", paragraph_ids=("p0002",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp3", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,), "seg_0003": (2,)},
    )
    bulk_select_col = FakeColumn(result=True)
    bulk_clear_col = FakeColumn(result=False)
    bulk_all_col = FakeColumn(result=False)

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [bulk_select_col, bulk_clear_col, bulk_all_col],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert session_state.selected_segment_ids == ["seg_0001", "seg_0002"]


def test_render_analysis_review_panel_clear_visible_removes_visible_selection(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001", "seg_0002"],
        segment_status_by_id={"seg_0001": "pending", "seg_0002": "pending", "seg_0003": "pending"},
        segment_progress_by_id={"seg_0001": 0.0, "seg_0002": 0.0, "seg_0003": 0.0},
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(segment_id="seg_0001", ordinal=1, level=1, title="Chapter 1", normalized_title="chapter 1", start_paragraph_index=0, end_paragraph_index=0, start_paragraph_id="p0000", end_paragraph_id="p0000", paragraph_ids=("p0000",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp1", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0002", ordinal=2, level=1, title="Chapter 2", normalized_title="chapter 2", start_paragraph_index=1, end_paragraph_index=1, start_paragraph_id="p0001", end_paragraph_id="p0001", paragraph_ids=("p0001",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp2", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,)},
    )
    bulk_select_col = FakeColumn(result=False)
    bulk_clear_col = FakeColumn(result=True)
    bulk_all_col = FakeColumn(result=False)

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [bulk_select_col, bulk_clear_col, bulk_all_col],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert session_state.selected_segment_ids == []


def test_render_analysis_review_panel_select_entire_book_selects_all_unlocked_segments(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        segment_status_by_id={"seg_0001": "pending", "seg_0002": "queued", "seg_0003": "completed"},
        segment_progress_by_id={"seg_0001": 0.0, "seg_0002": 0.0, "seg_0003": 1.0},
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(segment_id="seg_0001", ordinal=1, level=1, title="Chapter 1", normalized_title="chapter 1", start_paragraph_index=0, end_paragraph_index=0, start_paragraph_id="p0000", end_paragraph_id="p0000", paragraph_ids=("p0000",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp1", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0002", ordinal=2, level=1, title="Chapter 2", normalized_title="chapter 2", start_paragraph_index=1, end_paragraph_index=1, start_paragraph_id="p0001", end_paragraph_id="p0001", paragraph_ids=("p0001",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp2", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0003", ordinal=3, level=1, title="Chapter 3", normalized_title="chapter 3", start_paragraph_index=2, end_paragraph_index=2, start_paragraph_id="p0002", end_paragraph_id="p0002", paragraph_ids=("p0002",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp3", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,), "seg_0003": (2,)},
    )
    bulk_select_col = FakeColumn(result=False)
    bulk_clear_col = FakeColumn(result=False)
    bulk_all_col = FakeColumn(result=True)

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [bulk_select_col, bulk_clear_col, bulk_all_col],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert session_state.selected_segment_ids == ["seg_0001", "seg_0003"]


def test_render_analysis_review_panel_shows_low_confidence_warning_and_manifest(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0002"],
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        exported_structure_manifest_path=".run/structure_manifests/20260506_094000_report.segments.json",
        paragraphs=[
            type("ParagraphStub", (), {"text": "Chapter 2 heading"})(),
            type("ParagraphStub", (), {"text": "Ending paragraph text"})(),
        ],
        segments=[
            DocumentSegment(
                segment_id="seg_0002",
                ordinal=2,
                level=1,
                title="Chapter 2",
                normalized_title="chapter 2",
                start_paragraph_index=0,
                end_paragraph_index=1,
                start_paragraph_id="p0002",
                end_paragraph_id="p0003",
                paragraph_ids=("p0002", "p0003"),
                paragraph_count=2,
                char_count=120,
                word_count=22,
                estimated_token_count=30,
                structural_role="chapter",
                confidence="low",
                boundary_fingerprint="deadbeef",
                boundary_evidence=(
                    SegmentBoundaryEvidence(source="numbering_pattern", confidence="medium", details={"text_preview": "Chapter 2"}),
                ),
                warnings=("No TOC match",),
            )
        ],
        segment_diagnostics=SegmentDetectionReport(
            segment_count=1,
            high_confidence_count=0,
            medium_confidence_count=0,
            low_confidence_count=1,
            toc_entry_count=4,
            toc_matched_count=2,
            warnings=("1 low-confidence segment detected",),
        ),
        segment_to_job={"seg_0002": (1, 2)},
    )
    warnings = []
    captions = []

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: captions.append(message))
    monkeypatch.setattr(app.st, "warning", lambda message, **kwargs: warnings.append(message))
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert warnings == [
        "Structure warnings: 1 low-confidence segment detected",
        "Low-confidence segment: Chapter 2. No TOC match",
    ]
    assert any(message == "Manifest path: .run/structure_manifests/20260506_094000_report.segments.json" for message in captions)


def test_render_analysis_review_panel_shows_last_exported_manifest_comparison_notice(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
        structure_manifest_notice_token="report.docx:3:token",
        structure_manifest_notice_details={
            "file_token": "report.docx:3:token",
            "manifest_path": ".run/structure_manifests/20260506_083400_report.segments.json",
            "structure_fingerprint": "oldfingerprint",
        },
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="newfingerprint",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            )
        ],
        segment_to_job={"seg_0001": (0,)},
    )
    warnings = []

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda message, **kwargs: warnings.append(message))
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert any(
        message
        == "Current analysis differs from the last exported structure manifest.\n"
        "Manifest path: .run/structure_manifests/20260506_083400_report.segments.json\n"
        "Exported fingerprint: oldfingerprint\n"
        "Current fingerprint: newfingerprint"
        for message in warnings
    )


def test_render_analysis_review_panel_shows_segment_runtime_badges(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001", "seg_0002"],
        segment_status_by_id={"seg_0001": "completed", "seg_0002": "processing"},
        segment_progress_by_id={"seg_0001": 1.0, "seg_0002": 0.5},
        active_segment_id="seg_0002",
        active_segment_title="Chapter 2",
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_0002",
                ordinal=2,
                level=1,
                title="Chapter 2",
                normalized_title="chapter 2",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp2",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,)},
    )
    checkbox_labels = []

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: checkbox_labels.append(label) or kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert any("completed 100%" in label for label in checkbox_labels)
    assert any("processing 50% | active" in label for label in checkbox_labels)


def test_render_analysis_review_panel_returns_start_final_book_when_all_required_segments_completed(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        segment_status_by_id={"seg_0001": "completed", "seg_0002": "skipped", "seg_0003": "completed"},
        segment_progress_by_id={"seg_0001": 1.0, "seg_0002": 0.0, "seg_0003": 1.0},
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(segment_id="seg_0001", ordinal=1, level=1, title="Chapter 1", normalized_title="chapter 1", start_paragraph_index=0, end_paragraph_index=0, start_paragraph_id="p0000", end_paragraph_id="p0000", paragraph_ids=("p0000",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp1", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0002", ordinal=2, level=1, title="TOC", normalized_title="toc", start_paragraph_index=1, end_paragraph_index=1, start_paragraph_id="p0001", end_paragraph_id="p0001", paragraph_ids=("p0001",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="toc", confidence="high", boundary_fingerprint="fp2", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0003", ordinal=3, level=1, title="Chapter 2", normalized_title="chapter 2", start_paragraph_index=2, end_paragraph_index=2, start_paragraph_id="p0002", end_paragraph_id="p0002", paragraph_ids=("p0002",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp3", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (), "seg_0003": (1,)},
    )

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=True)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    action = app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert action == "start_final_book"


def test_render_analysis_review_panel_shows_completed_and_failed_status_hints(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001", "seg_0002"],
        segment_status_by_id={"seg_0001": "completed", "seg_0002": "failed"},
        segment_progress_by_id={"seg_0001": 1.0, "seg_0002": 0.0},
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(segment_id="seg_0001", ordinal=1, level=1, title="Chapter 1", normalized_title="chapter 1", start_paragraph_index=0, end_paragraph_index=0, start_paragraph_id="p0000", end_paragraph_id="p0000", paragraph_ids=("p0000",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp1", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0002", ordinal=2, level=1, title="Chapter 2", normalized_title="chapter 2", start_paragraph_index=1, end_paragraph_index=1, start_paragraph_id="p0001", end_paragraph_id="p0001", paragraph_ids=("p0001",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp2", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,)},
    )
    captions = []

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: captions.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert any(
        message == "Completed in this session. This segment can be selected again for reprocess/export later."
        for message in captions
    )
    assert any(
        message == "Failed in this session. Retry UI is not available yet in the current phase."
        for message in captions
    )


def test_render_analysis_review_panel_shows_segment_status_summary(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001", "seg_0002", "seg_0003", "seg_0004"],
        segment_status_by_id={
            "seg_0001": "completed",
            "seg_0002": "processing",
            "seg_0003": "pending",
            "seg_0004": "failed",
        },
        segment_progress_by_id={
            "seg_0001": 1.0,
            "seg_0002": 0.5,
            "seg_0003": 0.0,
            "seg_0004": 0.0,
        },
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_0002",
                ordinal=2,
                level=1,
                title="Chapter 2",
                normalized_title="chapter 2",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp2",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_0003",
                ordinal=3,
                level=1,
                title="Chapter 3",
                normalized_title="chapter 3",
                start_paragraph_index=2,
                end_paragraph_index=2,
                start_paragraph_id="p0002",
                end_paragraph_id="p0002",
                paragraph_ids=("p0002",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp3",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_0004",
                ordinal=4,
                level=1,
                title="Chapter 4",
                normalized_title="chapter 4",
                start_paragraph_index=3,
                end_paragraph_index=3,
                start_paragraph_id="p0003",
                end_paragraph_id="p0003",
                paragraph_ids=("p0003",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp4",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,), "seg_0003": (2,), "seg_0004": (3,)},
    )
    captions = []

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)])
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: captions.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert any(
        message == "Segment status summary: pending 1 | processing 1 | completed 1 | failed 1"
        for message in captions
    )


def test_render_analysis_review_panel_shows_selected_status_summary(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001", "seg_0002", "seg_0004"],
        segment_status_by_id={
            "seg_0001": "completed",
            "seg_0002": "processing",
            "seg_0003": "pending",
            "seg_0004": "failed",
        },
        segment_progress_by_id={
            "seg_0001": 1.0,
            "seg_0002": 0.5,
            "seg_0003": 0.0,
            "seg_0004": 0.0,
        },
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(segment_id="seg_0001", ordinal=1, level=1, title="Chapter 1", normalized_title="chapter 1", start_paragraph_index=0, end_paragraph_index=0, start_paragraph_id="p0000", end_paragraph_id="p0000", paragraph_ids=("p0000",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp1", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0002", ordinal=2, level=1, title="Chapter 2", normalized_title="chapter 2", start_paragraph_index=1, end_paragraph_index=1, start_paragraph_id="p0001", end_paragraph_id="p0001", paragraph_ids=("p0001",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp2", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0003", ordinal=3, level=1, title="Chapter 3", normalized_title="chapter 3", start_paragraph_index=2, end_paragraph_index=2, start_paragraph_id="p0002", end_paragraph_id="p0002", paragraph_ids=("p0002",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp3", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_0004", ordinal=4, level=1, title="Chapter 4", normalized_title="chapter 4", start_paragraph_index=3, end_paragraph_index=3, start_paragraph_id="p0003", end_paragraph_id="p0003", paragraph_ids=("p0003",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp4", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,), "seg_0003": (2,), "seg_0004": (3,)},
    )
    captions = []

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: captions.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert any(
        message == "Selected segment statuses: completed 1 | failed 1"
        for message in captions
    )
    assert any(
        message == "Selected launch payload excludes 1 locked segment(s) that are currently queued or processing."
        for message in captions
    )


def test_render_analysis_review_panel_preserves_confirmation_when_selection_changes(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_0002",
                ordinal=2,
                level=1,
                title="Chapter 2",
                normalized_title="chapter 2",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp2",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
        ],
    )
    checkbox_values = iter([False, True])

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)])
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: next(checkbox_values))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert session_state.selected_segment_ids == ["seg_0002"]
    assert session_state.structure_confirmed is True
    assert session_state.confirmed_structure_fingerprint == "abc123def456"
    assert session_state.confirmed_at_settings_hash == "settings123"


def test_render_analysis_review_panel_shows_explicit_fingerprint_invalidation_summary(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=True,
        confirmed_structure_fingerprint="oldfingerprint",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="newfingerprint",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            )
        ],
        segment_to_job={"seg_0001": (0,)},
    )
    warnings = []

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)])
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda message, **kwargs: warnings.append(message))
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app.st,
        "expander",
        lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})(),
    )

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert session_state.structure_confirmed is False
    assert session_state.confirmed_structure_fingerprint == ""
    assert session_state.confirmed_at_settings_hash == ""
    assert warnings == [
        "Structure confirmation invalidated.\n"
        "Previous confirmed fingerprint: oldfingerprint\n"
        "Current fingerprint: newfingerprint\n"
        "Detected chapter structure changed after re-analysis.\n"
        "Review the chapter list and confirm structure again before processing selected chapters."
    ]


def test_render_analysis_review_panel_shows_explicit_settings_invalidation_summary(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=True,
        confirmed_structure_fingerprint="samefingerprint",
        confirmed_at_settings_hash="oldsettings",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="samefingerprint",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            )
        ],
        segment_to_job={"seg_0001": (0,)},
    )
    warnings = []

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "newsettings")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)])
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda message, **kwargs: warnings.append(message))
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app.st,
        "expander",
        lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})(),
    )

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert session_state.structure_confirmed is False
    assert session_state.confirmed_structure_fingerprint == ""
    assert session_state.confirmed_at_settings_hash == ""
    assert warnings == [
        "Structure confirmation invalidated.\n"
        "Previous confirmed fingerprint: samefingerprint\n"
        "Current fingerprint: samefingerprint\n"
        "Detection-affecting settings changed since the last confirmation.\n"
        "Review the chapter list and confirm structure again before processing selected chapters."
    ]


def test_render_analysis_review_panel_invalidates_confirmation_when_additional_detection_settings_change(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=True,
        confirmed_structure_fingerprint="samefingerprint",
        confirmed_at_settings_hash="baseline123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="samefingerprint",
        detector_version="segments_v2",
        source_format="pdf",
        conversion_backend="libreoffice",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            )
        ],
        segment_to_job={"seg_0001": (0,)},
    )
    warnings = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)])
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda message, **kwargs: warnings.append(message))
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app.st,
        "expander",
        lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})(),
    )

    baseline_hash = app._build_structure_settings_hash(
        uploaded_file_token="report.docx:3:token",
        prepared_run_context=prepared_run_context,
        chunk_size=6000,
        app_config={
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "structure_recognition_min_confidence": "medium",
            "structure_validation_enabled": True,
        },
    )
    session_state.confirmed_at_settings_hash = baseline_hash

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
        app_config={
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_and_medium",
            "paragraph_boundary_ai_review_enabled": True,
            "paragraph_boundary_ai_review_mode": "medium_and_low",
            "structure_recognition_min_confidence": "high",
            "structure_validation_enabled": True,
        },
    )

    assert session_state.structure_confirmed is False
    assert warnings == [
        "Structure confirmation invalidated.\n"
        "Previous confirmed fingerprint: samefingerprint\n"
        "Current fingerprint: samefingerprint\n"
        "Detection-affecting settings changed since the last confirmation.\n"
        "Review the chapter list and confirm structure again before processing selected chapters."
    ]


def test_render_analysis_review_panel_confirms_structure(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
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
    confirm_col = FakeColumn(result=True)
    selected_col = FakeColumn(result=False)
    full_book_col = FakeColumn(result=False)
    reruns = []
    log_calls = []

    bulk_select_col = FakeColumn(result=False)
    bulk_clear_col = FakeColumn(result=False)
    bulk_all_col = FakeColumn(result=False)

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [bulk_select_col, bulk_clear_col, bulk_all_col],
            [confirm_col, selected_col, full_book_col],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app.st,
        "expander",
        lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})(),
    )
    monkeypatch.setattr(app.st, "rerun", lambda: reruns.append(True))
    monkeypatch.setattr(app, "log_event", lambda *args, **kwargs: log_calls.append((args, kwargs)))

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert session_state.structure_confirmed is True
    assert session_state.confirmed_structure_fingerprint == "abc123def456"
    assert session_state.confirmed_at_settings_hash
    assert session_state.segments_loaded_for_source_token == "report.docx:3:token"
    assert reruns == [True]
    assert log_calls and log_calls[0][0][1] == "structure_confirmed"


def test_render_analysis_review_panel_returns_selected_action_when_confirmed(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
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
        segment_to_job={"seg_0001": (0,)},
    )
    confirm_col = FakeColumn(result=False)
    selected_col = FakeColumn(result=True)
    full_book_col = FakeColumn(result=False)

    bulk_select_col = FakeColumn(result=False)
    bulk_clear_col = FakeColumn(result=False)
    bulk_all_col = FakeColumn(result=False)

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [bulk_select_col, bulk_clear_col, bulk_all_col],
            [confirm_col, selected_col, full_book_col],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(
        app.st,
        "expander",
        lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})(),
    )

    action = app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert action == "start_selected"
    assert selected_col.calls == [(
        "Process Selected",
        {
            "use_container_width": True,
            "disabled": False,
            "help": "Processes only the selected chapters and produces a partial output artifact.",
            "key": "process_selected_button",
        },
    )]


def test_render_analysis_review_panel_shows_confirmed_outline_summary(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_parent", "seg_child"],
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
        segment_status_by_id={"seg_parent": "pending", "seg_child": "pending"},
        segment_progress_by_id={"seg_parent": 0.0, "seg_child": 0.0},
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_parent",
                ordinal=1,
                level=1,
                title="Part I",
                normalized_title="part i",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="part",
                confidence="high",
                boundary_fingerprint="fp_parent",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_child",
                parent_segment_id="seg_parent",
                ordinal=2,
                level=2,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp_child",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
        ],
        segment_to_job={"seg_parent": (), "seg_child": (0,)},
    )
    caption_calls = []

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)])
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: caption_calls.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app.st,
        "expander",
        lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})(),
    )

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert any(
        message == "Structure confirmed for fingerprint abc123def456 | selected top-level 1 | selected nested 1"
        for message in caption_calls
    )


def test_render_analysis_review_panel_returns_full_book_action(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
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
    confirm_col = FakeColumn(result=False)
    selected_col = FakeColumn(result=False)
    full_book_col = FakeColumn(result=True)

    bulk_select_col = FakeColumn(result=False)
    bulk_clear_col = FakeColumn(result=False)
    bulk_all_col = FakeColumn(result=False)

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [bulk_select_col, bulk_clear_col, bulk_all_col],
            [confirm_col, selected_col, full_book_col],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app.st,
        "expander",
        lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})(),
    )

    action = app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert action == "start_full_book"


def test_main_starts_full_book_processing_from_analysis_panel(monkeypatch):
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
        selected_segment_ids=["seg_0001"],
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    start_calls = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})())
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=True)],
        ),
    )
    monkeypatch.setattr(app, "render_preparation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: (_ for _ in ()).throw(AssertionError("generic controls should not be used when analysis action returns full-book start")))
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


def test_main_starts_selected_processing_from_analysis_panel(monkeypatch):
    image_asset = type("ImageAssetStub", (), {"image_id": "img_001"})()
    paragraph_a = type("ParagraphStub", (), {"paragraph_id": "p0000", "asset_id": None, "attached_to_asset_id": None})()
    paragraph_b = type("ParagraphStub", (), {"paragraph_id": "p0001", "asset_id": "img_001", "attached_to_asset_id": None})()
    paragraph_c = type("ParagraphStub", (), {"paragraph_id": "p0002", "asset_id": None, "attached_to_asset_id": None})()
    prepared_run_context = _build_prepared_run_context(
        paragraphs=[paragraph_a, paragraph_b, paragraph_c],
        image_assets=[image_asset],
        jobs=[
            {"target_text": "block-1", "paragraph_ids": ["p0000", "p0001"]},
            {"target_text": "block-2", "paragraph_ids": ["p0002"]},
        ],
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
            ),
            DocumentSegment(
                segment_id="seg_0002",
                ordinal=2,
                level=1,
                title="Chapter 2",
                normalized_title="chapter 2",
                start_paragraph_index=2,
                end_paragraph_index=2,
                start_paragraph_id="p0002",
                end_paragraph_id="p0002",
                paragraph_ids=("p0002",),
                paragraph_count=1,
                char_count=50,
                word_count=10,
                estimated_token_count=12,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="deadbeef",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,)},
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
        selected_segment_ids=["seg_0001"],
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    start_calls = []
    reruns = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})())
    monkeypatch.setattr(app.st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=True), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app, "render_preparation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_maybe_apply_file_recommendations", lambda **kwargs: None)
    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: (_ for _ in ()).throw(AssertionError("generic controls should not be used when analysis action returns selected start")))
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "file_selected")
    monkeypatch.setattr(application_flow, "prepare_run_context", lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")))
    monkeypatch.setattr(app, "_start_background_processing", lambda **kwargs: start_calls.append(kwargs))
    monkeypatch.setattr(app.st, "rerun", lambda: reruns.append(True))

    app.main()

    assert len(start_calls) == 1
    assert start_calls[0]["uploaded_filename"] == "report.docx"
    assert start_calls[0]["uploaded_token"] == "report.docx:3:token"
    assert start_calls[0]["selected_segment_ids"] == ["seg_0001"]
    assert start_calls[0]["jobs"] == [{"target_text": "block-1", "paragraph_ids": ["p0000", "p0001"]}]
    assert start_calls[0]["source_paragraphs"] == [paragraph_a, paragraph_b]
    assert start_calls[0]["image_assets"] == [image_asset]
    assert reruns == [True]


def test_main_starts_selected_processing_excludes_locked_descendants(monkeypatch):
    paragraph_parent = type("ParagraphStub", (), {"paragraph_id": "p0000", "asset_id": None, "attached_to_asset_id": None})()
    paragraph_child = type("ParagraphStub", (), {"paragraph_id": "p0001", "asset_id": None, "attached_to_asset_id": None})()
    prepared_run_context = _build_prepared_run_context(
        paragraphs=[paragraph_parent, paragraph_child],
        jobs=[
            {"target_text": "parent-block", "paragraph_ids": ["p0000"]},
            {"target_text": "child-block", "paragraph_ids": ["p0001"]},
        ],
        segments=[
            DocumentSegment(
                segment_id="seg_parent",
                ordinal=1,
                level=1,
                title="Part I",
                normalized_title="part i",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="part",
                confidence="high",
                boundary_fingerprint="fp_parent",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_child",
                parent_segment_id="seg_parent",
                ordinal=2,
                level=2,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp_child",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
        ],
        segment_to_job={"seg_parent": (0,), "seg_child": (1,)},
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
        selected_segment_ids=["seg_parent"],
        segment_status_by_id={"seg_parent": "pending", "seg_child": "processing"},
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    start_calls = []
    reruns = []

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app, "init_session_state", lambda: None)
    monkeypatch.setattr(app, "inject_ui_styles", lambda: None)
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
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})())
    monkeypatch.setattr(app.st, "button", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=True), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app, "render_preparation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_partial_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_run_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_image_validation_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "render_section_gap", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_maybe_apply_file_recommendations", lambda **kwargs: None)
    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app, "_render_processing_controls", lambda **kwargs: (_ for _ in ()).throw(AssertionError("generic controls should not be used when analysis action returns selected start")))
    monkeypatch.setattr(compare_panel, "render_compare_all_apply_panel", lambda **kwargs: None)
    monkeypatch.setattr(application_flow, "resolve_effective_uploaded_file", lambda **kwargs: uploaded_file)
    monkeypatch.setattr(application_flow, "has_resettable_state", lambda **kwargs: False)
    monkeypatch.setattr(application_flow, "derive_app_idle_view_state", lambda **kwargs: "file_selected")
    monkeypatch.setattr(application_flow, "prepare_run_context", lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_run_context should not be called")))
    monkeypatch.setattr(app, "_start_background_processing", lambda **kwargs: start_calls.append(kwargs))
    monkeypatch.setattr(app.st, "rerun", lambda: reruns.append(True))

    app.main()

    assert len(start_calls) == 1
    assert start_calls[0]["selected_segment_ids"] == ["seg_parent"]
    assert start_calls[0]["jobs"] == [{"target_text": "parent-block", "paragraph_ids": ["p0000"]}]
    assert start_calls[0]["source_paragraphs"] == [paragraph_parent]
    assert reruns == [True]


def test_start_background_processing_accepts_selected_segment_ids(monkeypatch):
    start_calls = []

    monkeypatch.setattr(app, "start_background_processing", lambda **kwargs: start_calls.append(kwargs))

    app._start_background_processing(
        uploaded_filename="report.docx",
        uploaded_token="report.docx:3:token",
        source_bytes=b"abc",
        jobs=[{"target_text": "block"}],
        selected_segment_ids=["seg_0001"],
        source_paragraphs=["p1"],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=3,
        processing_operation="edit",
        source_language="en",
        target_language="ru",
    )

    assert len(start_calls) == 1
    assert start_calls[0]["selected_segment_ids"] == ["seg_0001"]


def test_build_selected_processing_payload_filters_jobs_paragraphs_and_images():
    image_asset = type("ImageAssetStub", (), {"image_id": "img_001"})()
    paragraphs = [
        type("ParagraphStub", (), {"paragraph_id": "p0000", "asset_id": None, "attached_to_asset_id": None})(),
        type("ParagraphStub", (), {"paragraph_id": "p0001", "asset_id": "img_001", "attached_to_asset_id": None})(),
        type("ParagraphStub", (), {"paragraph_id": "p0002", "asset_id": None, "attached_to_asset_id": None})(),
    ]
    prepared_run_context = _build_prepared_run_context(
        paragraphs=paragraphs,
        image_assets=[image_asset],
        jobs=[
            {"target_text": "block-1", "paragraph_ids": ["p0000", "p0001"]},
            {"target_text": "block-2", "paragraph_ids": ["p0002"]},
        ],
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                title="Chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=1,
                start_paragraph_id="p0000",
                end_paragraph_id="p0001",
                paragraph_ids=("p0000", "p0001"),
            ),
            DocumentSegment(
                segment_id="seg_0002",
                ordinal=2,
                title="Chapter 2",
                start_paragraph_index=2,
                end_paragraph_index=2,
                start_paragraph_id="p0002",
                end_paragraph_id="p0002",
                paragraph_ids=("p0002",),
            ),
        ],
        segment_to_job={"seg_0001": (0,), "seg_0002": (1,)},
    )

    payload = app._build_selected_processing_payload(
        prepared_run_context=prepared_run_context,
        selected_segment_ids=["seg_0001"],
    )

    assert payload["selected_segment_ids"] == ["seg_0001"]
    assert payload["jobs"] == [{"target_text": "block-1", "paragraph_ids": ["p0000", "p0001"]}]
    assert payload["source_paragraphs"] == paragraphs[:2]
    assert payload["image_assets"] == [image_asset]


def test_build_selected_processing_payload_returns_empty_payload_when_nothing_selected():
    payload = app._build_selected_processing_payload(
        prepared_run_context=_build_prepared_run_context(),
        selected_segment_ids=[],
    )

    assert payload == {
        "selected_segment_ids": [],
        "jobs": [],
        "source_paragraphs": [],
        "image_assets": [],
    }


def test_render_analysis_review_panel_selects_parent_with_descendants(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=[],
        segment_status_by_id={"seg_parent": "pending", "seg_child": "pending", "seg_other": "pending"},
        segment_progress_by_id={"seg_parent": 0.0, "seg_child": 0.0, "seg_other": 0.0},
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_parent",
                ordinal=1,
                level=1,
                title="Part I",
                normalized_title="part i",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="part",
                confidence="high",
                boundary_fingerprint="fp_parent",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_child",
                parent_segment_id="seg_parent",
                ordinal=2,
                level=2,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp_child",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_other",
                ordinal=3,
                level=1,
                title="Appendix",
                normalized_title="appendix",
                start_paragraph_index=2,
                end_paragraph_index=2,
                start_paragraph_id="p0002",
                end_paragraph_id="p0002",
                paragraph_ids=("p0002",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="appendix",
                confidence="high",
                boundary_fingerprint="fp_other",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
        ],
        segment_to_job={"seg_parent": (), "seg_child": (0,), "seg_other": (1,)},
    )
    checkbox_values = iter([True, False, False])
    checkbox_labels = []
    info_calls = []
    caption_calls = []

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)])
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: checkbox_labels.append(label) or next(checkbox_values))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda message, **kwargs: info_calls.append(message))
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: caption_calls.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert session_state.selected_segment_ids == ["seg_parent", "seg_child"]
    assert any(
        "Part I | 2 words | high | part | +1 descendants | approx. 0 direct jobs | 1 descendant jobs | pending"
        in label
        for label in checkbox_labels
    )
    assert any("- Chapter 1 | 2 words | high | chapter | parent: Part I | approx. 1 jobs | pending" in label for label in checkbox_labels)
    assert any(message == "Selected: 2/3 segments | 4/6 words | approx. 1/2 jobs" for message in info_calls)
    assert any(message == "Visible structure: 2 top-level | 1 nested | max level 2" for message in caption_calls)
    assert any(message == "Selected structure: top-level 1 | nested 1" for message in caption_calls)
    assert any(
        message == "Selected coverage includes 1 descendant segments under selected parent sections."
        for message in caption_calls
    )


def test_render_analysis_review_panel_clear_visible_clears_parent_and_descendants(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_parent", "seg_child", "seg_other"],
        segment_status_by_id={"seg_parent": "pending", "seg_child": "pending", "seg_other": "pending"},
        segment_progress_by_id={"seg_parent": 0.0, "seg_child": 0.0, "seg_other": 0.0},
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(segment_id="seg_parent", ordinal=1, level=1, title="Part I", normalized_title="part i", start_paragraph_index=0, end_paragraph_index=0, start_paragraph_id="p0000", end_paragraph_id="p0000", paragraph_ids=("p0000",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="part", confidence="high", boundary_fingerprint="fp_parent", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_child", parent_segment_id="seg_parent", ordinal=2, level=2, title="Chapter 1", normalized_title="chapter 1", start_paragraph_index=1, end_paragraph_index=1, start_paragraph_id="p0001", end_paragraph_id="p0001", paragraph_ids=("p0001",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp_child", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_other", ordinal=3, level=1, title="Appendix", normalized_title="appendix", start_paragraph_index=2, end_paragraph_index=2, start_paragraph_id="p0002", end_paragraph_id="p0002", paragraph_ids=("p0002",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="appendix", confidence="high", boundary_fingerprint="fp_other", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
        ],
        segment_to_job={"seg_parent": (), "seg_child": (0,), "seg_other": (1,)},
    )
    bulk_select_col = FakeColumn(result=False)
    bulk_clear_col = FakeColumn(result=True)
    bulk_all_col = FakeColumn(result=False)

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [bulk_select_col, bulk_clear_col, bulk_all_col],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert session_state.selected_segment_ids == []


def test_build_selected_processing_payload_expands_parent_to_descendants():
    paragraphs = [
        type("ParagraphStub", (), {"paragraph_id": "p0000", "asset_id": None, "attached_to_asset_id": None})(),
        type("ParagraphStub", (), {"paragraph_id": "p0001", "asset_id": None, "attached_to_asset_id": None})(),
    ]
    prepared_run_context = _build_prepared_run_context(
        paragraphs=paragraphs,
        jobs=[
            {"target_text": "parent-block", "paragraph_ids": ["p0000"]},
            {"target_text": "child-block", "paragraph_ids": ["p0001"]},
        ],
        segments=[
            DocumentSegment(
                segment_id="seg_parent",
                ordinal=1,
                title="Part I",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
            ),
            DocumentSegment(
                segment_id="seg_child",
                parent_segment_id="seg_parent",
                ordinal=2,
                title="Chapter 1",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
            ),
        ],
        segment_to_job={"seg_parent": (0,), "seg_child": (1,)},
    )

    payload = app._build_selected_processing_payload(
        prepared_run_context=prepared_run_context,
        selected_segment_ids=["seg_parent"],
    )

    assert payload["selected_segment_ids"] == ["seg_parent", "seg_child"]
    assert payload["jobs"] == [
        {"target_text": "parent-block", "paragraph_ids": ["p0000"]},
        {"target_text": "child-block", "paragraph_ids": ["p0001"]},
    ]
    assert payload["source_paragraphs"] == paragraphs


def test_build_selected_processing_payload_skips_locked_descendants():
    paragraphs = [
        type("ParagraphStub", (), {"paragraph_id": "p0000", "asset_id": None, "attached_to_asset_id": None})(),
        type("ParagraphStub", (), {"paragraph_id": "p0001", "asset_id": None, "attached_to_asset_id": None})(),
    ]
    prepared_run_context = _build_prepared_run_context(
        paragraphs=paragraphs,
        jobs=[
            {"target_text": "parent-block", "paragraph_ids": ["p0000"]},
            {"target_text": "child-block", "paragraph_ids": ["p0001"]},
        ],
        segments=[
            DocumentSegment(
                segment_id="seg_parent",
                ordinal=1,
                title="Part I",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
            ),
            DocumentSegment(
                segment_id="seg_child",
                parent_segment_id="seg_parent",
                ordinal=2,
                title="Chapter 1",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
            ),
        ],
        segment_to_job={"seg_parent": (0,), "seg_child": (1,)},
    )

    payload = app._build_selected_processing_payload(
        prepared_run_context=prepared_run_context,
        selected_segment_ids=["seg_parent"],
        segment_status_by_id={"seg_child": "processing"},
    )

    assert payload["selected_segment_ids"] == ["seg_parent"]
    assert payload["jobs"] == [{"target_text": "parent-block", "paragraph_ids": ["p0000"]}]
    assert payload["source_paragraphs"] == [paragraphs[0]]


def test_render_analysis_review_panel_uses_effective_selected_payload_for_ready_state(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_parent"],
        segment_status_by_id={"seg_parent": "pending", "seg_child": "processing"},
        segment_progress_by_id={"seg_parent": 0.0, "seg_child": 0.5},
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(segment_id="seg_parent", ordinal=1, level=1, title="Part I", normalized_title="part i", start_paragraph_index=0, end_paragraph_index=0, start_paragraph_id="p0000", end_paragraph_id="p0000", paragraph_ids=("p0000",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="part", confidence="high", boundary_fingerprint="fp_parent", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
            DocumentSegment(segment_id="seg_child", parent_segment_id="seg_parent", ordinal=2, level=2, title="Chapter 1", normalized_title="chapter 1", start_paragraph_index=1, end_paragraph_index=1, start_paragraph_id="p0001", end_paragraph_id="p0001", paragraph_ids=("p0001",), paragraph_count=1, char_count=10, word_count=2, estimated_token_count=3, structural_role="chapter", confidence="high", boundary_fingerprint="fp_child", boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),)),
        ],
        segment_to_job={"seg_parent": (), "seg_child": (0,)},
    )
    info_calls = []
    caption_calls = []

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
            [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda message, **kwargs: info_calls.append(message))
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: caption_calls.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: type("FakeExpander", (), {"__enter__": lambda self: self, "__exit__": lambda self, exc_type, exc, tb: False})())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert any(message == "Selected: 1/2 segments | 2/4 words | approx. 0/1 jobs" for message in info_calls)
    assert any(
        message == "Process Selected unavailable: the current selection does not resolve to any selectable jobs."
        for message in caption_calls
    )
    assert not any(message == "Ready: confirmed structure | selection resolves to processable jobs." for message in caption_calls)
    assert any(
        message == "Selected launch payload excludes 1 locked segment(s) that are currently queued or processing."
        for message in caption_calls
    )


def test_render_analysis_review_panel_shows_visible_structure_summary_only_for_nested_segments(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_parent", "seg_child"],
        segment_status_by_id={"seg_parent": "pending", "seg_child": "pending"},
        segment_progress_by_id={"seg_parent": 0.0, "seg_child": 0.0},
        structure_confirmed=False,
        confirmed_structure_fingerprint="",
        confirmed_at_settings_hash="",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_parent",
                ordinal=1,
                level=1,
                title="Part I",
                normalized_title="part i",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="part",
                confidence="high",
                boundary_fingerprint="fp_parent",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
            DocumentSegment(
                segment_id="seg_child",
                parent_segment_id="seg_parent",
                ordinal=2,
                level=2,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=1,
                end_paragraph_index=1,
                start_paragraph_id="p0001",
                end_paragraph_id="p0001",
                paragraph_ids=("p0001",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp_child",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            ),
        ],
        segment_to_job={"seg_parent": (), "seg_child": (0,)},
    )
    caption_calls = []

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)])
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: caption_calls.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert any(message == "Visible structure: 1 top-level | 1 nested | max level 2" for message in caption_calls)


def test_render_analysis_review_panel_shows_ready_caption_when_can_process_selected(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            )
        ],
        segment_to_job={"seg_0001": (0,)},
    )
    caption_calls = []

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(app.st, "columns", lambda n: [FakeColumn(result=False), FakeColumn(result=False), FakeColumn(result=False)])
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda message, **kwargs: caption_calls.append(message))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert any(
        message == "Ready: confirmed structure | selection resolves to processable jobs."
        for message in caption_calls
    )
    assert not any(
        "Process Selected unavailable" in message
        for message in caption_calls
    )


def test_render_analysis_review_panel_shows_reconfirm_button_label_when_already_confirmed(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            )
        ],
        segment_to_job={"seg_0001": (0,)},
    )

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    confirm_col = FakeColumn(result=False)
    selected_col = FakeColumn(result=False)
    full_book_col = FakeColumn(result=False)
    bulk_select_col = FakeColumn(result=False)
    bulk_clear_col = FakeColumn(result=False)
    bulk_all_col = FakeColumn(result=False)

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [bulk_select_col, bulk_clear_col, bulk_all_col],
            [confirm_col, selected_col, full_book_col],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert confirm_col.calls
    assert confirm_col.calls[0][0] == "Re-confirm Structure"


def test_render_analysis_review_panel_shows_failed_segment_retry_notice(monkeypatch):
    session_state = SessionState(
        selected_segment_ids=["seg_0001"],
        structure_confirmed=True,
        confirmed_structure_fingerprint="abc123def456",
        confirmed_at_settings_hash="settings123",
        segments_loaded_for_source_token="report.docx:3:token",
        segment_status_by_id={"seg_0001": "failed"},
    )
    prepared_run_context = _build_prepared_run_context(
        structure_fingerprint="abc123def456",
        segments=[
            DocumentSegment(
                segment_id="seg_0001",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=0,
                start_paragraph_id="p0000",
                end_paragraph_id="p0000",
                paragraph_ids=("p0000",),
                paragraph_count=1,
                char_count=10,
                word_count=2,
                estimated_token_count=3,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="fp1",
                boundary_evidence=(SegmentBoundaryEvidence(source="heading_style", confidence="high", details={}),),
            )
        ],
        segment_to_job={"seg_0001": (0,)},
    )

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    captions = []
    confirm_col = FakeColumn(result=False)
    selected_col = FakeColumn(result=False)
    full_book_col = FakeColumn(result=False)
    bulk_select_col = FakeColumn(result=False)
    bulk_clear_col = FakeColumn(result=False)
    bulk_all_col = FakeColumn(result=False)

    monkeypatch.setattr(app, "_build_structure_settings_hash", lambda **kwargs: "settings123")
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(
        app.st,
        "columns",
        _two_stage_columns(
            [bulk_select_col, bulk_clear_col, bulk_all_col],
            [confirm_col, selected_col, full_book_col],
        ),
    )
    monkeypatch.setattr(app.st, "checkbox", lambda label, **kwargs: kwargs.get("value", False))
    monkeypatch.setattr(app.st, "selectbox", lambda label, options, index=0, **kwargs: options[index])
    monkeypatch.setattr(app.st, "text_input", lambda label, value="", **kwargs: value)
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda msg, **kwargs: captions.append(msg))
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: FakeExpander())

    app._render_analysis_review_panel(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="report.docx:3:token",
        chunk_size=6000,
    )

    assert any("failed" in c and "retry" in c.lower() and "not available" in c.lower() for c in captions), (
        f"Expected a failed-segment retry notice in captions, got: {captions}"
    )
