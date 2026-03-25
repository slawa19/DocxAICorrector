import queue
import subprocess

import pytest

import processing_runtime
import state
from runtime_events import (
    AppendImageLogEvent,
    AppendLogEvent,
    FinalizeProcessingStatusEvent,
    PreparationCompleteEvent,
    PreparationFailedEvent,
    PushActivityEvent,
    ResetImageStateEvent,
    SetProcessingStatusEvent,
    SetStateEvent,
    WorkerCompleteEvent,
)


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def test_drain_processing_events_applies_typed_runtime_events(monkeypatch):
    session_state = SessionState(
        processing_event_queue=queue.Queue(),
        image_assets=["stale"],
        image_validation_failures=["stale"],
        image_processing_summary={"total_images": 3, "processed_images": 2, "validation_errors": ["boom"]},
        restart_source=None,
        processing_worker=object(),
        processing_stop_event=object(),
        processing_stop_requested=True,
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)

    calls = {
        "status": [],
        "finalize": [],
        "activity": [],
        "log": [],
        "image_log": [],
    }

    session_state.processing_event_queue.put(SetStateEvent(values={"last_error": "boom"}))
    session_state.processing_event_queue.put(ResetImageStateEvent())
    session_state.processing_event_queue.put(SetProcessingStatusEvent(payload={"stage": "run", "detail": "detail"}))
    session_state.processing_event_queue.put(FinalizeProcessingStatusEvent(stage="done", detail="ok", progress=1.0, terminal_kind="completed"))
    session_state.processing_event_queue.put(PushActivityEvent(message="hello"))
    session_state.processing_event_queue.put(AppendLogEvent(payload={"status": "OK", "block_index": 1, "block_count": 2, "target_chars": 3, "context_chars": 4, "details": "done"}))
    session_state.processing_event_queue.put(AppendImageLogEvent(payload={"image_id": "img_1", "status": "validated", "decision": "accept", "confidence": 0.9}))
    session_state.processing_event_queue.put(WorkerCompleteEvent(outcome="succeeded"))

    processing_runtime.drain_processing_events(
        set_processing_status=lambda **payload: calls["status"].append(payload),
        finalize_processing_status=lambda stage, detail, progress, terminal_kind=None: calls["finalize"].append((stage, detail, progress, terminal_kind)),
        push_activity=lambda message: calls["activity"].append(message),
        append_log=lambda **payload: calls["log"].append(payload),
        append_image_log=lambda **payload: calls["image_log"].append(payload),
    )

    assert session_state.last_error == "boom"
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
    assert calls["status"] == [{"stage": "run", "detail": "detail"}]
    assert calls["finalize"] == [("done", "ok", 1.0, "completed")]
    assert calls["activity"] == ["hello"]
    assert calls["log"][0]["status"] == "OK"
    assert calls["image_log"][0]["image_id"] == "img_1"
    assert session_state.processing_outcome == "succeeded"
    assert session_state.processing_worker is None
    assert session_state.processing_event_queue is None
    assert session_state.processing_stop_event is None
    assert session_state.processing_stop_requested is False


def test_build_runtime_event_emitters_emits_typed_events_for_background_runtime():
    emitted_events = []

    class RuntimeStub:
        def emit(self, event):
            emitted_events.append(event)

    emitters = processing_runtime.build_runtime_event_emitters(
        dependencies=processing_runtime.RuntimeEventEmitterDependencies(
            set_processing_status=lambda **payload: None,
            finalize_processing_status=lambda stage, detail, progress, terminal_kind=None: None,
            push_activity=lambda message: None,
            append_log=lambda **payload: None,
            append_image_log=lambda **payload: None,
        )
    )

    runtime = RuntimeStub()
    emitters.emit_state(runtime, last_error="boom")
    emitters.emit_image_reset(runtime)
    emitters.emit_status(runtime, stage="run", detail="detail")
    emitters.emit_finalize(runtime, "done", "ok", 1.0, "completed")
    emitters.emit_activity(runtime, "hello")
    emitters.emit_log(runtime, status="OK", block_index=1, block_count=1, target_chars=2, context_chars=0, details="done")
    emitters.emit_image_log(runtime, image_id="img_1", status="validated", decision="accept", confidence=0.9)

    assert emitted_events == [
        SetStateEvent(values={"last_error": "boom"}),
        ResetImageStateEvent(),
        SetProcessingStatusEvent(payload={"stage": "run", "detail": "detail"}),
        FinalizeProcessingStatusEvent(stage="done", detail="ok", progress=1.0, terminal_kind="completed"),
        PushActivityEvent(message="hello"),
        AppendLogEvent(payload={"status": "OK", "block_index": 1, "block_count": 1, "target_chars": 2, "context_chars": 0, "details": "done"}),
        AppendImageLogEvent(payload={"image_id": "img_1", "status": "validated", "decision": "accept", "confidence": 0.9}),
    ]


def test_drain_preparation_events_stores_prepared_context(monkeypatch):
    prepared_run_context = type("PreparedRunContextStub", (), {
        "uploaded_file_token": "report.docx:3:abc",
        "prepared_source_key": "report.docx:3:abc:6000",
    })()
    session_state = SessionState(
        preparation_event_queue=queue.Queue(),
        preparation_worker=object(),
        selected_source_token="",
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    finalized = []

    session_state.preparation_event_queue.put(
        PreparationCompleteEvent(
            prepared_run_context=prepared_run_context,
            upload_marker="report.docx:3:ba7816bf8f01cfea:6000",
        )
    )

    processing_runtime.drain_preparation_events(
        reset_run_state=lambda **kwargs: None,
        set_processing_status=lambda **payload: None,
        finalize_processing_status=lambda stage, detail, progress, terminal_kind=None: finalized.append((stage, detail, progress, terminal_kind)),
        push_activity=lambda message: None,
    )

    assert session_state.prepared_run_context is prepared_run_context
    assert session_state.preparation_input_marker == "report.docx:3:ba7816bf8f01cfea:6000"
    assert session_state.selected_source_token == "report.docx:3:abc"
    assert session_state.preparation_worker is None
    assert session_state.preparation_event_queue is None
    assert finalized == [("Документ подготовлен", "Анализ файла завершён. Можно запускать обработку.", 1.0, "completed")]


def test_drain_preparation_events_marks_failure(monkeypatch):
    session_state = SessionState(
        preparation_event_queue=queue.Queue(),
        preparation_worker=object(),
        last_error="",
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    finalized = []
    activities = []

    session_state.preparation_event_queue.put(
        PreparationFailedEvent(
            upload_marker="report.docx:3:ba7816bf8f01cfea:6000",
            error_message="boom",
            error_details={
                "stage": "preparation",
                "severity": "error",
                "user_message": "boom",
                "technical_message": "boom",
                "error_type": "RuntimeError",
                "recoverable": False,
            },
        )
    )

    processing_runtime.drain_preparation_events(
        reset_run_state=lambda **kwargs: None,
        set_processing_status=lambda **payload: None,
        finalize_processing_status=lambda stage, detail, progress, terminal_kind=None: finalized.append((stage, detail, progress, terminal_kind)),
        push_activity=lambda message: activities.append(message),
    )

    assert session_state.prepared_run_context is None
    assert session_state.preparation_failed_marker == "report.docx:3:ba7816bf8f01cfea:6000"
    assert session_state.last_error == "boom"
    assert session_state.last_background_error["stage"] == "preparation"
    assert session_state.preparation_worker is None
    assert session_state.preparation_event_queue is None
    assert finalized == [("Ошибка подготовки", "boom", 1.0, "error")]
    assert activities == ["Не удалось прочитать и проанализировать DOCX-файл."]


def test_start_background_preparation_creates_worker_and_status(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    statuses = []
    activities = []
    payloads = []

    uploaded_file = processing_runtime.build_in_memory_uploaded_file(source_name="report.docx", source_bytes=b"abc")
    uploaded_payload = processing_runtime.freeze_uploaded_file(uploaded_file)

    processing_runtime.start_background_preparation(
        worker_target=lambda **kwargs: payloads.append(kwargs["uploaded_payload"]),
        reset_run_state=lambda **kwargs: None,
        push_activity=lambda message: activities.append(message),
        set_processing_status=lambda **payload: statuses.append(payload),
        uploaded_payload=uploaded_payload,
        upload_marker="report.docx:3:ba7816bf8f01cfea:6000",
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
    )

    session_state.preparation_worker.join(timeout=5)

    assert session_state.preparation_input_marker == "report.docx:3:ba7816bf8f01cfea:6000"
    assert session_state.preparation_event_queue is not None
    assert session_state.preparation_worker is not None
    assert statuses[0]["phase"] == "preparing"
    assert statuses[0]["stage"] == "Файл получен"
    assert activities == ["Файл получен сервером. Запускаю анализ DOCX."]
    assert payloads[0] == uploaded_payload


def test_start_background_preparation_propagates_cached_flag(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    statuses = []
    activities = []
    uploaded_file = processing_runtime.build_in_memory_uploaded_file(source_name="report.docx", source_bytes=b"abc")
    uploaded_payload = processing_runtime.freeze_uploaded_file(uploaded_file)

    def worker_target(**kwargs):
        kwargs["progress_callback"](
            stage="Подготовка документа",
            detail="cache hit",
            progress=0.9,
            metrics={"cached": True, "block_count": 5, "paragraph_count": 10, "image_count": 1, "source_chars": 2000},
        )

    processing_runtime.start_background_preparation(
        worker_target=worker_target,
        reset_run_state=lambda **kwargs: None,
        push_activity=lambda message: activities.append(message),
        set_processing_status=lambda **payload: statuses.append(payload),
        uploaded_payload=uploaded_payload,
        upload_marker="report.docx:3:ba7816bf8f01cfea:6000",
        chunk_size=6000,
        image_mode="safe",
        keep_all_image_variants=True,
    )

    session_state.preparation_worker.join(timeout=5)
    processing_runtime.drain_preparation_events(
        reset_run_state=lambda **kwargs: None,
        set_processing_status=lambda **payload: statuses.append(payload),
        finalize_processing_status=lambda stage, detail, progress, terminal_kind=None: None,
        push_activity=lambda message: activities.append(message),
    )
    assert any(payload.get("cached") is True for payload in statuses)
    assert "[Анализ] Подготовка документа: cache hit" in activities


def test_drain_processing_events_moves_restart_source_to_completed_cache_on_success(monkeypatch):
    session_state = SessionState(
        processing_event_queue=queue.Queue(),
        restart_source={"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "restart.bin", "session_id": "session-a"},
        processing_worker=object(),
        processing_stop_event=object(),
        processing_stop_requested=True,
        restart_session_id="session-a",
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(processing_runtime, "load_restart_source_bytes", lambda restart_source: b"abc")
    cleared = []
    monkeypatch.setattr(processing_runtime, "clear_restart_source", lambda restart_source: cleared.append(restart_source))
    monkeypatch.setattr(
        processing_runtime,
        "store_completed_source",
        lambda **kwargs: {
            "filename": kwargs["source_name"],
            "token": kwargs["source_token"],
            "storage_path": "completed.bin",
            "size": len(kwargs["source_bytes"]),
            "session_id": kwargs["session_id"],
            "storage_kind": "completed",
        },
    )

    session_state.processing_event_queue.put(WorkerCompleteEvent(outcome="succeeded"))

    processing_runtime.drain_processing_events(
        set_processing_status=lambda **payload: None,
        finalize_processing_status=lambda stage, detail, progress: None,
        push_activity=lambda message: None,
        append_log=lambda **payload: None,
        append_image_log=lambda **payload: None,
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
    assert cleared == [{"filename": "report.docx", "token": "report.docx:3:abc", "storage_path": "restart.bin", "session_id": "session-a"}]


def test_drain_processing_events_skips_completed_cache_for_large_sources(monkeypatch):
    session_state = SessionState(
        processing_event_queue=queue.Queue(),
        restart_source={"filename": "report.docx", "token": "report.docx:12:abc", "storage_path": "restart.bin", "session_id": "session-a"},
        processing_worker=object(),
        processing_stop_event=object(),
        processing_stop_requested=True,
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(processing_runtime, "MAX_COMPLETED_SOURCE_BYTES", 4)
    monkeypatch.setattr(processing_runtime, "load_restart_source_bytes", lambda restart_source: b"abcdef")
    cleared = []
    activities = []
    monkeypatch.setattr(processing_runtime, "clear_restart_source", lambda restart_source: cleared.append(restart_source))

    session_state.processing_event_queue.put(WorkerCompleteEvent(outcome="succeeded"))

    processing_runtime.drain_processing_events(
        set_processing_status=lambda **payload: None,
        finalize_processing_status=lambda stage, detail, progress: None,
        push_activity=lambda message: activities.append(message),
        append_log=lambda **payload: None,
        append_image_log=lambda **payload: None,
    )

    assert session_state.completed_source is None
    assert session_state.restart_source is None
    assert len(activities) == 1
    assert "слишком большой" in activities[0].lower()
    assert cleared == [{"filename": "report.docx", "token": "report.docx:12:abc", "storage_path": "restart.bin", "session_id": "session-a"}]


def test_start_background_processing_degrades_gracefully_when_restart_store_fails(monkeypatch):
    session_state = SessionState(restart_session_id="session-a")
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    state_monkey_session = session_state
    monkeypatch.setattr(state.st, "session_state", state_monkey_session)
    state.init_session_state()
    session_state.restart_session_id = "session-a"

    activity_messages = []
    monkeypatch.setattr(processing_runtime, "store_restart_source", lambda **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    log_events = []
    monkeypatch.setattr(processing_runtime, "log_event", lambda *args, **kwargs: log_events.append((args, kwargs)))

    processing_runtime.start_background_processing(
        worker_target=lambda **kwargs: None,
        reset_run_state=state.reset_run_state,
        push_activity=lambda message: activity_messages.append(message),
        set_processing_status=lambda **kwargs: None,
        uploaded_filename="report.docx",
        uploaded_token="report.docx:3:abc",
        source_bytes=b"abc",
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=["paragraph"],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
    )

    session_state.processing_worker.join(timeout=5)

    assert session_state.restart_source is None
    assert session_state.processing_worker is not None
    assert any("restart" in message.lower() for message in activity_messages)
    assert len(log_events) == 1


def test_start_background_processing_preserves_prepared_context(monkeypatch):
    prepared_run_context = object()
    session_state = SessionState(
        restart_session_id="session-a",
        prepared_run_context=prepared_run_context,
        latest_preparation_summary={"stage": "Документ подготовлен"},
        preparation_input_marker="report.docx:3:abc:6000",
        prepared_source_key="report.docx:3:abc:6000",
        preparation_cache={"report.docx:3:abc:6000": {"cached": True}},
    )
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(state.st, "session_state", session_state)
    state.init_session_state()
    session_state.restart_session_id = "session-a"
    monkeypatch.setattr(
        processing_runtime,
        "store_restart_source",
        lambda **kwargs: {
            "filename": kwargs["source_name"],
            "token": kwargs["source_token"],
            "storage_path": "restart.bin",
            "session_id": kwargs["session_id"],
        },
    )

    processing_runtime.start_background_processing(
        worker_target=lambda **kwargs: None,
        reset_run_state=state.reset_run_state,
        push_activity=lambda message: None,
        set_processing_status=lambda **kwargs: None,
        uploaded_filename="report.docx",
        uploaded_token="report.docx:3:abc",
        source_bytes=b"abc",
        jobs=[{"target_text": "block", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=["paragraph"],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
    )

    session_state.processing_worker.join(timeout=5)

    assert session_state.prepared_run_context is prepared_run_context
    assert session_state.latest_preparation_summary == {"stage": "Документ подготовлен"}
    assert session_state.preparation_input_marker == "report.docx:3:abc:6000"
    assert session_state.prepared_source_key == "report.docx:3:abc:6000"
    assert session_state.preparation_cache == {"report.docx:3:abc:6000": {"cached": True}}
    assert session_state.processing_outcome == "running"


def test_freeze_uploaded_file_normalizes_legacy_doc_payload(monkeypatch):
    uploaded_file = processing_runtime.build_in_memory_uploaded_file(
        source_name="legacy.doc",
        source_bytes=bytes.fromhex("D0CF11E0A1B11AE1") + b"legacy-binary",
    )
    monkeypatch.setattr(
        processing_runtime,
        "_convert_legacy_doc_to_docx",
        lambda **kwargs: (b"converted-docx", "antiword+pandoc"),
    )

    payload = processing_runtime.freeze_uploaded_file(uploaded_file)

    assert payload.filename == "legacy.docx"
    assert payload.content_bytes == b"converted-docx"
    assert payload.file_size == len(b"converted-docx")
    assert payload.file_token.startswith("legacy.docx:")


def test_build_uploaded_file_token_renames_zip_payloads_with_docx_magic_to_docx_extension():
    token = processing_runtime.build_uploaded_file_token(
        source_name="misnamed.doc",
        source_bytes=b"PK\x03\x04not-really-a-full-docx",
    )

    assert token.startswith("misnamed.docx:")


def test_detect_uploaded_document_format_rejects_non_doc_ole2_suffix() -> None:
    detected = processing_runtime._detect_uploaded_document_format(
        filename="worksheet.xls",
        source_bytes=bytes.fromhex("D0CF11E0A1B11AE1") + b"ole2-payload",
    )

    assert detected == "unknown"


def test_run_completed_process_raises_timeout_error(monkeypatch):
    def run_stub(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(processing_runtime.subprocess, "run", run_stub)

    with pytest.raises(RuntimeError, match="Превышено время ожидания"):
        processing_runtime._run_completed_process(["soffice"], error_message="boom")


def test_convert_legacy_doc_to_docx_falls_back_to_antiword_when_soffice_fails(monkeypatch):
    calls = []

    monkeypatch.setattr(
        processing_runtime.shutil,
        "which",
        lambda name: {
            "soffice": "/usr/bin/soffice",
            "libreoffice": None,
            "antiword": "/usr/bin/antiword",
        }.get(name),
    )

    def soffice_stub(**kwargs):
        calls.append("soffice")
        raise RuntimeError("soffice failed")

    def antiword_stub(**kwargs):
        calls.append("antiword")
        return b"converted-docx"

    monkeypatch.setattr(processing_runtime, "_convert_legacy_doc_with_soffice", soffice_stub)
    monkeypatch.setattr(processing_runtime, "_convert_legacy_doc_with_antiword", antiword_stub)

    converted_bytes, backend = processing_runtime._convert_legacy_doc_to_docx(
        filename="legacy.doc",
        source_bytes=bytes.fromhex("D0CF11E0A1B11AE1") + b"legacy",
    )

    assert converted_bytes == b"converted-docx"
    assert backend == "antiword+pandoc"
    assert calls == ["soffice", "antiword"]


def test_build_uploaded_file_token_for_legacy_doc_is_stable_across_converter_outputs(monkeypatch):
    converted_outputs = [b"converted-docx-a", b"converted-docx-b"]

    def convert_stub(**kwargs):
        return converted_outputs.pop(0), "libreoffice"

    monkeypatch.setattr(processing_runtime, "_convert_legacy_doc_to_docx", convert_stub)

    source_bytes = bytes.fromhex("D0CF11E0A1B11AE1") + b"same-legacy-doc"
    first = processing_runtime.build_uploaded_file_token(source_name="legacy.doc", source_bytes=source_bytes)
    second = processing_runtime.build_uploaded_file_token(source_name="legacy.doc", source_bytes=source_bytes)

    assert first == second


def test_resolve_upload_contract_separates_source_identity_from_normalized_payload(monkeypatch):
    source_bytes = bytes.fromhex("D0CF11E0A1B11AE1") + b"same-legacy-doc"
    monkeypatch.setattr(
        processing_runtime,
        "_convert_legacy_doc_to_docx",
        lambda **kwargs: (b"converted-docx", "libreoffice"),
    )

    contract = processing_runtime.resolve_upload_contract(filename="legacy.doc", source_bytes=source_bytes)
    payload = processing_runtime.freeze_resolved_upload(contract)

    assert contract.source_identity.original_filename == "legacy.doc"
    assert contract.source_identity.source_bytes == source_bytes
    assert contract.normalized_document.filename == "legacy.docx"
    assert contract.normalized_document.content_bytes == b"converted-docx"
    assert payload.filename == "legacy.docx"
    assert payload.content_bytes == b"converted-docx"
    assert payload.file_token == contract.file_token
    assert payload.file_token.endswith(f":{contract.source_identity.token_hash}")
