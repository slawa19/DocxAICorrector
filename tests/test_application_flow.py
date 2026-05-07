from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import docxaicorrector.processing.preparation as preparation
import docxaicorrector.processing.processing_runtime as processing_runtime
import docxaicorrector.processing.restart_store as restart_store
import docxaicorrector.runtime.state as state
import docxaicorrector.ui.application_flow as application_flow
from conftest import SessionState as SessionState  # noqa: F811
from docx import Document
from docxaicorrector.document.segments import DocumentContextProfile, DocumentSegment, SegmentBoundaryEvidence, SegmentDetectionReport, SegmentOutlineEntry


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


class UploadedFileStub:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content
        self.size = len(content)
        self._cursor = 0

    def getvalue(self):
        return self._content

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._content[self._cursor :]
            self._cursor = len(self._content)
            return chunk
        end = min(len(self._content), self._cursor + size)
        chunk = self._content[self._cursor : end]
        self._cursor = end
        return chunk

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._cursor = max(0, offset)
        elif whence == 1:
            self._cursor = max(0, self._cursor + offset)
        elif whence == 2:
            self._cursor = max(0, len(self._content) + offset)
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        self._cursor = min(self._cursor, len(self._content))
        return self._cursor


def _freeze_uploaded_file(name: str, content: bytes):
    return processing_runtime.freeze_uploaded_file(UploadedFileStub(name, content))


def test_prepare_run_context_updates_selected_token_and_prepared_key(monkeypatch):
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: None)
    session_state = SessionState(
        selected_source_token="",
        prepared_source_key="",
        completed_source={"filename": "report.docx", "token": "report.docx:3:ba7816bf8f01cfea", "storage_path": "completed.bin"},
    )
    monkeypatch.setattr(state.st, "session_state", session_state)
    logged = []
    progress_events = []

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=["img"],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="report.docx:hash:6000",
        structure_map={"kind": "structure-map"},
        ai_classified_count=3,
        ai_heading_count=2,
        ai_role_change_count=1,
        ai_heading_promotion_count=1,
        ai_heading_demotion_count=0,
        ai_structural_role_change_count=1,
        normalization_report=SimpleNamespace(
            total_raw_paragraphs=3,
            total_logical_paragraphs=2,
            merged_group_count=1,
            merged_raw_paragraph_count=2,
        ),
        cached=False,
    )

    result = application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("report.docx", b"abc"),
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected critical error")),
        log_event_fn=lambda *args, **kwargs: logged.append((args, kwargs)),
        prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
        progress_callback=lambda **payload: progress_events.append(payload),
    )

    assert result.uploaded_filename == "report.docx"
    assert result.uploaded_file_bytes == b"abc"
    assert result.uploaded_file_token.startswith("report.docx:3:")
    assert result.jobs == prepared_document.jobs
    assert result.preparation_stage == "Документ подготовлен"
    assert result.preparation_detail == ""
    assert result.preparation_cached is False
    assert result.preparation_elapsed_seconds >= 0.0
    assert result.normalization_report is prepared_document.normalization_report
    assert result.structure_map == {"kind": "structure-map"}
    assert result.ai_classified_count == 3
    assert result.ai_heading_count == 2
    assert result.ai_role_change_count == 1
    assert result.ai_heading_promotion_count == 1
    assert result.ai_heading_demotion_count == 0
    assert result.ai_structural_role_change_count == 1
    assert session_state.selected_source_token == result.uploaded_file_token
    assert session_state.prepared_source_key == "report.docx:hash:6000"
    assert session_state.completed_source is None
    assert len(logged) == 1
    assert progress_events[0]["stage"] == "Чтение файла"
    assert progress_events[1]["metrics"]["file_size_bytes"] == 3
    assert progress_events[-1]["stage"] == "Документ подготовлен"
    assert progress_events[-1]["metrics"]["block_count"] == 1
    assert progress_events[-1]["metrics"]["raw_paragraph_count"] == 3
    assert progress_events[-1]["metrics"]["logical_paragraph_count"] == 2
    assert progress_events[-1]["metrics"]["merged_group_count"] == 1
    assert progress_events[-1]["metrics"]["merged_raw_paragraph_count"] == 2
    assert logged[0][1]["raw_paragraph_count"] == 3
    assert logged[0][1]["logical_paragraph_count"] == 2
    assert logged[0][1]["merged_group_count"] == 1
    assert logged[0][1]["merged_raw_paragraph_count"] == 2


def test_sync_selected_file_context_delegates_selected_token_write_to_state(monkeypatch):
    session_state = SessionState(selected_source_token="")
    monkeypatch.setattr(state.st, "session_state", session_state)
    delegated_tokens = []

    def record_selected_token(token, session_state=None):
        delegated_tokens.append(token)
        if session_state is not None:
            session_state.selected_source_token = token

    monkeypatch.setattr(application_flow, "set_selected_source_token", record_selected_token)

    application_flow.sync_selected_file_context(
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        uploaded_file_token="report.docx:3:abc",
    )

    assert delegated_tokens == ["report.docx:3:abc"]
    assert session_state.selected_source_token == "report.docx:3:abc"


def test_prepare_run_context_raises_on_empty_job_target(monkeypatch):
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: None)
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    failures = []

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "   ", "target_chars": 0, "context_chars": 0}],
        prepared_source_key="prepared-key",
        cached=False,
    )

    def fail_critical_stub(event, message, **context):
        failures.append((event, message, context))
        raise RuntimeError(message)

    try:
        application_flow.prepare_run_context(
            uploaded_file=UploadedFileStub("report.docx", b"abc"),
            chunk_size=6000,
            image_mode="safe",
            keep_all_image_variants=True,
            session_state=session_state,
            reset_run_state_fn=lambda **kwargs: None,
            fail_critical_fn=fail_critical_stub,
            log_event_fn=lambda *args, **kwargs: None,
            prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("prepare_run_context must fail on empty target_text")

    assert failures[0][0] == "empty_target_block"


def test_prepare_run_context_raises_on_none_job_target(monkeypatch):
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: None)
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    failures = []

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": None, "target_chars": 0, "context_chars": 0}],
        prepared_source_key="prepared-key",
        cached=False,
    )

    def fail_critical_stub(event, message, **context):
        failures.append((event, message, context))
        raise RuntimeError(message)

    try:
        application_flow.prepare_run_context(
            uploaded_file=UploadedFileStub("report.docx", b"abc"),
            chunk_size=6000,
            image_mode="safe",
            keep_all_image_variants=True,
            session_state=session_state,
            reset_run_state_fn=lambda **kwargs: None,
            fail_critical_fn=fail_critical_stub,
            log_event_fn=lambda *args, **kwargs: None,
            prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("prepare_run_context must fail on None target_text")

    assert failures[0][0] == "empty_target_block"


def test_prepare_run_context_keeps_best_effort_warning_when_quality_gate_warns(monkeypatch):
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: None)
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    failures = []

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="prepared-key",
        quality_gate_status="warning",
        quality_gate_reasons=("toc_like_sequence_without_bounded_region", "structure_recognition_noop_on_high_risk"),
        cached=False,
        source_format="pdf",
        conversion_backend="libreoffice",
    )

    prepared_run_context = application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("report.docx", b"abc"),
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: failures.append((args, kwargs)),
        log_event_fn=lambda *args, **kwargs: None,
        prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
    )

    assert failures == []
    assert prepared_run_context.quality_gate_status == "warning"
    assert prepared_run_context.source_format == "pdf"
    assert prepared_run_context.conversion_backend == "libreoffice"
    assert prepared_run_context.preparation_detail.endswith(
        "Причины: обнаружен TOC-подобный фрагмент без надёжно выделенной границы, AI-распознавание структуры не внесло изменений для документа с высоким структурным риском"
    )


def test_prepare_run_context_copies_segment_fields_from_prepared_document(monkeypatch):
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: None)
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    document_context_profile = DocumentContextProfile(
        outline_entries=(SegmentOutlineEntry(segment_id="seg_0001_abcd1234", title="Chapter 1", level=1),),
    )

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="prepared-key",
        cached=False,
        segments=[SimpleNamespace(segment_id="seg_0001_abcd1234", title="Chapter 1")],
        segment_diagnostics=SimpleNamespace(segment_count=1, toc_matched_count=0),
        structure_fingerprint="abc123def456",
        detector_version="chapter_segments_v1",
        segment_to_job={"seg_0001_abcd1234": (0,)},
        document_context_profile=document_context_profile,
    )

    prepared_run_context = application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("report.docx", b"abc"),
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected critical error")),
        log_event_fn=lambda *args, **kwargs: None,
        prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
    )

    assert prepared_run_context.segments == prepared_document.segments
    assert prepared_run_context.segment_diagnostics is prepared_document.segment_diagnostics
    assert prepared_run_context.structure_fingerprint == "abc123def456"
    assert prepared_run_context.detector_version == "chapter_segments_v1"
    assert prepared_run_context.segment_to_job == {"seg_0001_abcd1234": (0,)}
    assert prepared_run_context.document_context_profile == document_context_profile


def test_build_structure_manifest_payload_serializes_detected_segments():
    prepared_run_context = application_flow.PreparedRunContext(
        uploaded_filename="report.docx",
        uploaded_file_bytes=b"abc",
        uploaded_file_token="report.docx:3:token",
        source_text="source-text",
        paragraphs=["p1", "p2", "p3"],
        image_assets=[],
        jobs=[{"target_text": "block one"}],
        prepared_source_key="report.docx:3:token:6000",
        preparation_stage="Документ подготовлен",
        preparation_detail="",
        preparation_cached=False,
        preparation_elapsed_seconds=0.1,
        segments=[
            DocumentSegment(
                segment_id="seg_0001_abcd1234",
                ordinal=1,
                level=1,
                title="Chapter 1",
                normalized_title="chapter 1",
                start_paragraph_index=0,
                end_paragraph_index=2,
                start_paragraph_id="p0000",
                end_paragraph_id="p0002",
                paragraph_ids=("p0000", "p0001", "p0002"),
                paragraph_count=3,
                char_count=120,
                word_count=20,
                estimated_token_count=30,
                structural_role="chapter",
                confidence="high",
                boundary_fingerprint="beefcafe",
                boundary_evidence=(
                    SegmentBoundaryEvidence(
                        source="heading_style",
                        confidence="high",
                        details={"heading_level": 1},
                    ),
                ),
            )
        ],
        segment_diagnostics=SegmentDetectionReport(
            segment_count=1,
            high_confidence_count=1,
            toc_entry_count=2,
            toc_matched_count=1,
        ),
        structure_fingerprint="abc123def456",
        detector_version="chapter_segments_v1",
        segment_to_job={"seg_0001_abcd1234": (0,)},
    )

    payload = application_flow.build_structure_manifest_payload(
        prepared_run_context=prepared_run_context,
        app_config={"chunk_size": 6000, "structure_recognition_min_confidence": "medium"},
    )

    assert payload["schema_version"] == 1
    assert payload["source_name"] == "report.docx"
    assert payload["prepared_source_key"] == "report.docx:3:token:6000"
    assert payload["ordered_segment_ids"] == ["seg_0001_abcd1234"]
    assert payload["detector_version"] == "chapter_segments_v1"
    assert payload["detector_config"] == {
        "chunk_size": 6000,
        "structure_recognition_mode": "off",
        "min_confidence": "medium",
    }
    assert payload["structure_fingerprint"] == "abc123def456"
    assert payload["summary"] == {
        "paragraph_count": 3,
        "segment_count": 1,
        "toc_entry_count": 2,
        "toc_matched_count": 1,
        "low_confidence_count": 0,
    }
    assert payload["segments"][0]["segment_id"] == "seg_0001_abcd1234"
    assert payload["segments"][0]["evidence"] == [
        {
            "source": "heading_style",
            "confidence": "high",
            "details": {"heading_level": 1},
        }
    ]


def test_document_facade_build_semantic_blocks_forwards_hard_boundaries(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        application_flow,
        "build_structure_manifest_payload",
        application_flow.build_structure_manifest_payload,
    )

    import docxaicorrector.document._document as document_facade

    monkeypatch.setattr(
        document_facade,
        "_build_semantic_blocks_impl",
        lambda paragraphs, max_chars=6000, *, relations=None, hard_boundary_paragraph_ids=None: captured.update(
            {
                "paragraphs": paragraphs,
                "max_chars": max_chars,
                "relations": relations,
                "hard_boundary_paragraph_ids": hard_boundary_paragraph_ids,
            }
        ) or ["ok"],
    )

    result = document_facade.build_semantic_blocks(
        cast(Any, ["p1", "p2"]),
        max_chars=7000,
        relations=["rel"],
        hard_boundary_paragraph_ids={"p0002"},
    )

    assert result == ["ok"]
    assert captured == {
        "paragraphs": ["p1", "p2"],
        "max_chars": 7000,
        "relations": ["rel"],
        "hard_boundary_paragraph_ids": {"p0002"},
    }


def test_prepare_run_context_keeps_other_completed_source_tokens(monkeypatch):
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: None)
    session_state = SessionState(
        selected_source_token="",
        prepared_source_key="",
        completed_source={"filename": "other.docx", "token": "other.docx:3:def", "storage_path": "other.bin"},
    )

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=["img"],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="report.docx:hash:6000",
        cached=False,
    )

    application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("report.docx", b"abc"),
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected critical error")),
        log_event_fn=lambda *args, **kwargs: None,
        prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
    )

    assert session_state.completed_source == {"filename": "other.docx", "token": "other.docx:3:def", "storage_path": "other.bin"}


def test_get_cached_completed_file_loads_bytes_from_store():
    session_state = SessionState(completed_source={"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "completed.bin"})

    uploaded_file = application_flow.get_cached_completed_file(
        session_state=cast(application_flow.SessionStateLike, session_state),
        load_completed_source_bytes_fn=lambda source: b"abc",
    )

    assert uploaded_file is not None
    assert uploaded_file.name == "report.docx"
    assert uploaded_file.getvalue() == b"abc"


def test_consume_completed_source_if_used_clears_persisted_file(monkeypatch):
    session_state = SessionState(completed_source={"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "completed.bin"})
    cleared = []
    monkeypatch.setattr(application_flow, "clear_restart_source", lambda source: cleared.append(source))

    application_flow.consume_completed_source_if_used(session_state=session_state, uploaded_file_token="report.docx:3:abc")

    assert session_state.completed_source is None
    assert cleared == [{"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "completed.bin"}]


def test_prepare_run_context_validates_archive_before_preparation(monkeypatch):
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    validated = []

    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: validated.append(source_bytes) or (_ for _ in ()).throw(RuntimeError("bad archive")))

    try:
        application_flow.prepare_run_context(
            uploaded_file=UploadedFileStub("report.docx", b"abc"),
            chunk_size=6000,
            image_mode="safe",
            keep_all_image_variants=True,
            session_state=session_state,
            reset_run_state_fn=lambda **kwargs: None,
            fail_critical_fn=lambda *args, **kwargs: None,
            log_event_fn=lambda *args, **kwargs: None,
            prepare_document_for_processing_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("prepare_document_for_processing must not run")),
        )
    except RuntimeError as exc:
        assert str(exc) == "bad archive"
    else:
        raise AssertionError("prepare_run_context must fail on invalid archive")

    assert validated == [b"abc"]


def test_prepare_run_context_normalizes_legacy_doc_before_validation(monkeypatch):
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    validated = []
    received = {}
    freeze_calls = []

    monkeypatch.setattr(
        application_flow,
        "freeze_uploaded_file",
        lambda uploaded_file: freeze_calls.append(uploaded_file.name)
        or SimpleNamespace(filename="legacy.docx", content_bytes=b"converted-docx", file_token="legacy.docx:6:mocked"),
    )
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: validated.append(source_bytes) or None)

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="legacy.docx:hash:6000",
        cached=False,
    )

    def prepare_document_for_processing_stub(**kwargs):
        received.update(kwargs)
        return prepared_document

    result = application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("legacy.doc", b"legacy"),
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected critical error")),
        log_event_fn=lambda *args, **kwargs: None,
        prepare_document_for_processing_fn=prepare_document_for_processing_stub,
    )

    assert freeze_calls == ["legacy.doc"]
    assert validated == [b"converted-docx"]
    assert received["uploaded_payload"].filename == "legacy.docx"
    assert received["uploaded_payload"].content_bytes == b"converted-docx"
    assert received["uploaded_payload"].file_token == "legacy.docx:6:mocked"
    assert result.uploaded_filename == "legacy.docx"
    assert result.uploaded_file_bytes == b"converted-docx"
    assert result.uploaded_file_token == "legacy.docx:6:mocked"


def test_prepare_run_context_normalizes_pdf_before_validation(monkeypatch):
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    validated = []
    received = {}
    freeze_calls = []

    monkeypatch.setattr(
        application_flow,
        "freeze_uploaded_file",
        lambda uploaded_file: freeze_calls.append(uploaded_file.name)
        or SimpleNamespace(filename="source.docx", content_bytes=b"PK\x03\x04converted-docx", file_token="source.docx:16:mocked"),
    )
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: validated.append(source_bytes) or None)

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="source.docx:hash:6000",
        cached=False,
    )

    def prepare_document_for_processing_stub(**kwargs):
        received.update(kwargs)
        return prepared_document

    result = application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("source.pdf", b"%PDF-1.7\nsource"),
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected critical error")),
        log_event_fn=lambda *args, **kwargs: None,
        prepare_document_for_processing_fn=prepare_document_for_processing_stub,
    )

    assert freeze_calls == ["source.pdf"]
    assert validated == [b"PK\x03\x04converted-docx"]
    assert received["uploaded_payload"].filename == "source.docx"
    assert received["uploaded_payload"].content_bytes == b"PK\x03\x04converted-docx"
    assert received["uploaded_payload"].file_token == "source.docx:16:mocked"
    assert result.uploaded_filename == "source.docx"
    assert result.uploaded_file_bytes == b"PK\x03\x04converted-docx"
    assert result.uploaded_file_token == "source.docx:16:mocked"


def test_prepare_run_context_reports_doc_conversion_failure_via_fail_critical(monkeypatch):
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    failures = []

    monkeypatch.setattr(
        application_flow,
        "freeze_uploaded_file",
        lambda uploaded_file: (_ for _ in ()).throw(RuntimeError("converter missing")),
    )

    def fail_critical_stub(event, message, **context):
        failures.append((event, message, context))
        raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="converter missing"):
        application_flow.prepare_run_context(
            uploaded_file=UploadedFileStub("legacy.doc", b"legacy"),
            chunk_size=6000,
            image_mode="safe",
            keep_all_image_variants=True,
            session_state=session_state,
            reset_run_state_fn=lambda **kwargs: None,
            fail_critical_fn=fail_critical_stub,
            log_event_fn=lambda *args, **kwargs: None,
            prepare_document_for_processing_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected")),
        )

    assert failures == [("doc_conversion_failed", "converter missing", {"filename": "legacy.doc"})]


def test_prepare_run_context_reports_pdf_conversion_failure_via_fail_critical(monkeypatch):
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    failures = []

    monkeypatch.setattr(
        application_flow,
        "freeze_uploaded_file",
        lambda uploaded_file: (_ for _ in ()).throw(RuntimeError("pdf converter missing")),
    )

    def fail_critical_stub(event, message, **context):
        failures.append((event, message, context))
        raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="pdf converter missing"):
        application_flow.prepare_run_context(
            uploaded_file=UploadedFileStub("source.pdf", b"%PDF-1.7\nsource"),
            chunk_size=6000,
            image_mode="safe",
            keep_all_image_variants=True,
            session_state=session_state,
            reset_run_state_fn=lambda **kwargs: None,
            fail_critical_fn=fail_critical_stub,
            log_event_fn=lambda *args, **kwargs: None,
            prepare_document_for_processing_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected")),
        )

    assert failures == [("doc_conversion_failed", "pdf converter missing", {"filename": "source.pdf"})]


def test_prepare_run_context_sync_path_freezes_upload_once(monkeypatch):
    session_state = SessionState(selected_source_token="", prepared_source_key="")
    freeze_calls = []
    validate_calls = []

    monkeypatch.setattr(
        application_flow,
        "freeze_uploaded_file",
        lambda uploaded_file: freeze_calls.append(uploaded_file.name)
        or SimpleNamespace(filename="legacy.docx", content_bytes=b"converted-docx", file_token="legacy.docx:token"),
    )
    monkeypatch.setattr(
        application_flow,
        "validate_docx_source_bytes",
        lambda source_bytes: validate_calls.append(source_bytes),
    )

    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="prepared-key",
        cached=False,
    )

    application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("legacy.doc", b"legacy"),
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        session_state=session_state,
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: None,
        log_event_fn=lambda *args, **kwargs: None,
        prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
    )

    assert freeze_calls == ["legacy.doc"]
    assert validate_calls == [b"converted-docx"]


def test_restart_flow_restores_uploaded_file_from_run_store_and_cleans_up(tmp_path, monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(restart_store, "RUN_DIR", tmp_path)

    state.init_session_state()
    session_state.restart_session_id = "session-a"

    processing_runtime.start_background_processing(
        worker_target=lambda **kwargs: None,
        reset_run_state=state.reset_run_state,
        push_activity=state.push_activity,
        set_processing_status=state.set_processing_status,
        uploaded_filename="report.docx",
        uploaded_token="report.docx:3:abc",
        source_bytes=b"abc",
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
    )

    session_state.processing_worker.join(timeout=5)
    session_state.processing_worker = None
    session_state.processing_outcome = "stopped"

    restored_file = application_flow.resolve_effective_uploaded_file(
        uploaded_file=None,
        current_result=None,
        session_state=session_state,
    )

    restart_path = session_state.restart_source["storage_path"]

    assert restored_file is not None
    assert restored_file.name == "report.docx"
    assert restored_file.getvalue() == b"abc"

    state.reset_run_state(keep_restart_source=False)


def test_sync_selected_file_context_resets_run_state_for_new_file(monkeypatch):
    session_state = SessionState(
        selected_source_token="old.docx:10",
        sidebar_text_operation="Перевод",
        sidebar_source_language="Авто",
        sidebar_target_language="Русский",
        previous_result=None,
        latest_docx_bytes=b"docx",
        latest_source_name="old.docx",
        latest_source_token="old.docx:10",
        latest_markdown="markdown",
        run_log=[{"status": "STOP"}],
        activity_feed=[{"time": "10:00:00", "message": "stale"}],
        processed_block_markdowns=["partial"],
        last_error="",
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
    monkeypatch.setattr(state.st, "session_state", session_state)

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
    assert "sidebar_text_operation" not in session_state
    assert "sidebar_source_language" not in session_state
    assert "sidebar_target_language" not in session_state


def test_has_resettable_state_depends_on_restartable_source(tmp_path):
    restart_path = tmp_path / "restart.bin"
    restart_path.write_bytes(b"abc")
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": str(restart_path)})

    assert application_flow.has_resettable_state(current_result=None, session_state=session_state) is True  # type: ignore[arg-type]

    session_state.processing_outcome = "idle"

    assert application_flow.has_resettable_state(current_result=None, session_state=session_state) is False  # type: ignore[arg-type]


def test_derive_idle_view_state_covers_idle_paths(tmp_path):
    restart_path = tmp_path / "restart.bin"
    restart_path.write_bytes(b"abc")
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": str(restart_path)})

    assert application_flow.derive_app_idle_view_state(current_result=None, uploaded_file=object(), session_state=session_state) == "file_selected"
    assert application_flow.derive_app_idle_view_state(current_result={"docx_bytes": b"x"}, uploaded_file=None, session_state=session_state) == "completed"
    assert application_flow.derive_app_idle_view_state(current_result=None, uploaded_file=None, session_state=session_state) == "restartable"

    session_state.processing_outcome = "idle"

    assert application_flow.derive_app_idle_view_state(current_result=None, uploaded_file=None, session_state=session_state) == "empty"


def test_get_cached_restart_file_returns_none_when_storage_missing(monkeypatch):
    session_state = SessionState(restart_source={"filename": "report.docx", "storage_path": "missing.bin"})
    monkeypatch.setattr(application_flow, "load_restart_source_bytes", lambda restart_source: None)

    assert application_flow.get_cached_restart_file(session_state=session_state) is None  # type: ignore[arg-type]


def test_resolve_effective_uploaded_file_uses_completed_source_after_success():
    session_state = SessionState(
        completed_source={"filename": "report.docx", "storage_path": "completed.bin", "token": "report.docx:3:abc"}
    )

    uploaded_file = application_flow.resolve_effective_uploaded_file(
        uploaded_file=None,
        current_result={"docx_bytes": b"done"},
        session_state=session_state,
        load_restart_source_bytes_fn=lambda source: b"abc",
    )

    assert uploaded_file is not None
    assert uploaded_file.name == "report.docx"
    assert uploaded_file.getvalue() == b"abc"


def test_has_restartable_source_does_not_materialize_restart_bytes(tmp_path, monkeypatch):
    restart_path = tmp_path / "restart.bin"
    restart_path.write_bytes(b"abc")
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": str(restart_path)})
    load_calls = []
    monkeypatch.setattr(application_flow, "load_restart_source_bytes", lambda restart_source: load_calls.append(restart_source) or b"abc")

    assert application_flow.has_restartable_source(session_state=session_state) is True  # type: ignore[arg-type]
    assert load_calls == []


def test_has_restartable_source_returns_false_when_restart_file_was_removed(tmp_path):
    restart_path = tmp_path / "restart.bin"
    restart_path.write_bytes(b"abc")
    session_state = SessionState(processing_outcome="stopped", restart_source={"filename": "report.docx", "storage_path": str(restart_path)})
    restart_path.unlink()

    assert application_flow.has_restartable_source(session_state=session_state) is False  # type: ignore[arg-type]


def test_prepare_run_context_for_background_uses_frozen_upload_payload(monkeypatch):
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: None)
    captured = {}
    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="prepared-key",
        cached=False,
    )
    payload = _freeze_uploaded_file("report.docx", b"abc")

    result = application_flow.prepare_run_context_for_background(
        uploaded_payload=payload,
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        processing_operation="audiobook",
        app_config={"structure_recognition_mode": "always", "structure_recognition_enabled": True},
        prepare_document_for_processing_fn=lambda **kwargs: (captured.setdefault("prepare", kwargs), prepared_document)[1],
    )

    assert result.uploaded_filename == "report.docx"
    assert result.uploaded_file_bytes == b"abc"
    assert result.uploaded_file_token == payload.file_token
    assert captured["prepare"]["app_config"] == {"structure_recognition_mode": "always", "structure_recognition_enabled": True}
    assert captured["prepare"]["processing_operation"] == "audiobook"


def test_prepare_run_context_for_background_uses_real_cache(monkeypatch):
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: None)
    preparation.clear_preparation_cache(clear_shared=True)
    calls = {"extract": 0}
    progress_events = []

    def fake_extract(uploaded_file):
        calls["extract"] += 1
        return ["paragraph"], [], None, [], None, None

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])

    uploaded_payload = _freeze_uploaded_file("report.docx", b"abc")
    application_flow.prepare_run_context_for_background(
        uploaded_payload=uploaded_payload,
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        progress_callback=lambda **payload: progress_events.append(payload),
    )
    second = application_flow.prepare_run_context_for_background(
        uploaded_payload=uploaded_payload,
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        progress_callback=lambda **payload: progress_events.append(payload),
    )

    assert calls["extract"] == 1
    assert second.prepared_source_key.endswith(":6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:lc=1:3:80:sr=auto:sv=1")
    assert second.preparation_cached is True
    assert second.preparation_stage == "Документ подготовлен"
    assert progress_events[-1]["stage"] == "Документ подготовлен"
    assert progress_events[-1]["metrics"]["cached"] is True


def test_prepare_run_context_for_background_processes_real_docx_without_mocks():
    preparation.clear_preparation_cache(clear_shared=True)
    source_doc = Document()
    source_doc.add_heading("Глава 1", level=1)
    source_doc.add_paragraph(
        "Первый абзац документа содержит достаточно длинный связный текст, чтобы не считаться подозрительно коротким body-блоком."
    )
    source_doc.add_paragraph(
        "Второй абзац документа тоже содержит несколько обычных слов и завершенное предложение для стабильной подготовки."
    )
    source_buffer = BytesIO()
    source_doc.save(source_buffer)

    payload = _freeze_uploaded_file("report.docx", source_buffer.getvalue())
    progress_events = []

    result = application_flow.prepare_run_context_for_background(
        uploaded_payload=payload,
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        progress_callback=lambda **payload: progress_events.append(payload),
    )

    assert result.uploaded_filename == "report.docx"
    assert result.uploaded_file_bytes == source_buffer.getvalue()
    assert result.source_text
    assert len(result.paragraphs) == 3
    assert len(result.jobs) >= 1
    assert any("Глава 1" in str(job.get("target_text", "")) for job in result.jobs)
    assert any(event["stage"] == "Разбор DOCX" for event in progress_events)
    assert progress_events[-1]["stage"] == "Документ подготовлен"


def test_prepare_run_context_for_background_skips_renormalization_for_frozen_payload(monkeypatch):
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: None)
    monkeypatch.setattr(
        application_flow,
        "freeze_uploaded_file",
        lambda uploaded_file: (_ for _ in ()).throw(AssertionError("unexpected refreeze")),
    )
    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="prepared-key",
        cached=False,
    )
    payload = _freeze_uploaded_file("report.docx", b"abc")

    result = application_flow.prepare_run_context_for_background(
        uploaded_payload=payload,
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        prepare_document_for_processing_fn=lambda **kwargs: prepared_document,
    )

    assert result.uploaded_filename == payload.filename
    assert result.uploaded_file_bytes == payload.content_bytes
    assert result.uploaded_file_token == payload.file_token


def test_prepare_run_context_sync_and_background_share_same_upload_contract(monkeypatch):
    monkeypatch.setattr(application_flow, "validate_docx_source_bytes", lambda source_bytes: None)
    prepared_document = SimpleNamespace(
        source_text="text",
        paragraphs=["p1"],
        image_assets=[],
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        prepared_source_key="prepared-key",
        cached=False,
    )
    sync_calls = []
    background_calls = []
    payload = _freeze_uploaded_file("report.docx", b"abc")

    def prepare_sync(**kwargs):
        sync_calls.append(kwargs)
        return prepared_document

    def prepare_background(**kwargs):
        background_calls.append(kwargs)
        return prepared_document

    sync_result = application_flow.prepare_run_context(
        uploaded_file=UploadedFileStub("report.docx", b"abc"),
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        session_state=SessionState(selected_source_token="", prepared_source_key=""),
        reset_run_state_fn=lambda **kwargs: None,
        fail_critical_fn=lambda *args, **kwargs: None,
        log_event_fn=lambda *args, **kwargs: None,
        prepare_document_for_processing_fn=prepare_sync,
    )
    background_result = application_flow.prepare_run_context_for_background(
        uploaded_payload=payload,
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
        prepare_document_for_processing_fn=prepare_background,
    )

    assert sync_calls[0]["uploaded_payload"].filename == background_calls[0]["uploaded_payload"].filename == "report.docx"
    assert sync_calls[0]["uploaded_payload"].content_bytes == background_calls[0]["uploaded_payload"].content_bytes == b"abc"
    assert sync_calls[0]["uploaded_payload"].file_token == background_calls[0]["uploaded_payload"].file_token == payload.file_token
    assert sync_result.uploaded_filename == background_result.uploaded_filename
    assert sync_result.uploaded_file_bytes == background_result.uploaded_file_bytes
    assert sync_result.uploaded_file_token == background_result.uploaded_file_token
