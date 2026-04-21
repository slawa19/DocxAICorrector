from models import ImageAsset
import processing_service
from processing_service import ProcessingService
from runtime_events import AppendLogEvent, FinalizeProcessingStatusEvent, SetStateEvent, WorkerCompleteEvent


def _build_service(**overrides):
    defaults = {
        "get_client_fn": lambda: object(),
        "load_system_prompt_fn": lambda: "system",
        "ensure_pandoc_available_fn": lambda: None,
        "generate_markdown_block_fn": lambda **kwargs: "markdown",
        "convert_markdown_to_docx_bytes_fn": lambda markdown: b"docx",
        "process_document_images_impl_fn": lambda **kwargs: kwargs["image_assets"],
        "analyze_image_fn": lambda *args, **kwargs: None,
        "generate_image_candidate_fn": lambda *args, **kwargs: None,
        "validate_redraw_result_fn": lambda *args, **kwargs: None,
        "detect_image_mime_type_fn": lambda *args, **kwargs: "image/png",
        "inspect_placeholder_integrity_fn": lambda markdown, assets: {},
        "preserve_source_paragraph_properties_fn": lambda docx_bytes, paragraphs: docx_bytes,
        "reinsert_inline_images_fn": lambda *args, **kwargs: b"final-docx",
        "run_document_processing_impl_fn": None,
        "present_error_fn": lambda code, exc, title, **kwargs: f"{title}: {exc}",
        "log_event_fn": lambda *args, **kwargs: None,
        "emit_state_fn": lambda runtime, **values: runtime.setdefault("state", {}).update(values) if isinstance(runtime, dict) else None,
        "emit_finalize_fn": lambda runtime, stage, detail, progress, terminal_kind=None: runtime.setdefault("finalize", []).append((stage, detail, progress, terminal_kind)) if isinstance(runtime, dict) else None,
        "emit_activity_fn": lambda runtime, message: runtime.setdefault("activity", []).append(message) if isinstance(runtime, dict) else None,
        "emit_log_fn": lambda runtime, **payload: runtime.setdefault("log", []).append(payload) if isinstance(runtime, dict) else None,
        "emit_status_fn": lambda runtime, **payload: runtime.setdefault("status", []).append(payload) if isinstance(runtime, dict) else None,
        "emit_image_log_fn": lambda runtime, **payload: runtime.setdefault("image_log", []).append(payload) if isinstance(runtime, dict) else None,
        "emit_image_reset_fn": lambda runtime: runtime.setdefault("image_reset", []).append(True) if isinstance(runtime, dict) else None,
        "should_stop_processing_fn": lambda runtime: False,
        "resolve_uploaded_filename_fn": lambda uploaded_file: str(uploaded_file),
        "image_model_call_budget_cls": object,
        "image_model_call_budget_exceeded_cls": RuntimeError,
    }
    defaults.update(overrides)
    return ProcessingService(dependencies=processing_service.build_processing_service_dependencies(**defaults))


def test_run_document_processing_fails_on_placeholder_integrity_mismatch():
    emitted_runtime = {}

    service = _build_service(
        generate_markdown_block_fn=lambda **kwargs: "Обработанный блок без placeholder",
        inspect_placeholder_integrity_fn=lambda markdown, assets: {"img_001": "lost"},
        convert_markdown_to_docx_bytes_fn=lambda markdown: (_ for _ in ()).throw(AssertionError("must not build docx")),
        run_document_processing_impl_fn=__import__("document_pipeline").run_document_processing,
    )

    result = service.run_document_processing(
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
        runtime=emitted_runtime,
    )

    assert result == "failed"
    assert emitted_runtime["state"]["last_error"].startswith("Критическая ошибка подготовки изображений")
    assert emitted_runtime["finalize"][-1][0] == "Критическая ошибка"
    assert emitted_runtime["activity"][-1] == "Сборка DOCX остановлена из-за потери или дублирования image placeholder."
    assert emitted_runtime["log"][-1]["status"] == "ERROR"


def test_run_processing_worker_emits_worker_complete_after_unhandled_crash():
    emitted_events = []

    class RuntimeStub:
        def emit(self, event):
            emitted_events.append(event)

    service = _build_service(
        run_document_processing_impl_fn=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    service.run_processing_worker(
        runtime=RuntimeStub(),
        uploaded_filename="report.docx",
        jobs=[{"target_text": "x", "context_before": "", "context_after": "", "target_chars": 1, "context_chars": 0}],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
    )

    assert emitted_events[-1] == WorkerCompleteEvent(outcome="failed")
    assert any(isinstance(event, SetStateEvent) and str(event.values["last_error"]).startswith("Критическая ошибка фоновой обработки") for event in emitted_events)
    def _is_processing_background_error(event) -> bool:
        if not isinstance(event, SetStateEvent):
            return False
        payload = event.values.get("last_background_error")
        return isinstance(payload, dict) and payload.get("stage") == "processing"

    assert any(_is_processing_background_error(event) for event in emitted_events)
    assert any(isinstance(event, FinalizeProcessingStatusEvent) for event in emitted_events)
    assert any(isinstance(event, AppendLogEvent) for event in emitted_events)


def test_run_processing_worker_emits_success_outcome_and_runtime_events():
    emitted_events = []

    class RuntimeStub:
        def emit(self, event):
            emitted_events.append(event)

    def run_document_processing_impl(**kwargs):
        kwargs["emit_state"](kwargs["runtime"], latest_markdown="Готово", latest_docx_bytes=b"docx")
        kwargs["emit_finalize"](
            kwargs["runtime"],
            "Обработка завершена",
            "DOCX собран",
            1.0,
            "completed",
        )
        kwargs["emit_log"](kwargs["runtime"], status="DONE", block_index=1, block_count=1, target_chars=6, context_chars=0, details="ok")
        return "succeeded"

    service = _build_service(
        run_document_processing_impl_fn=run_document_processing_impl,
        emit_state_fn=lambda runtime, **values: runtime.emit(SetStateEvent(values=values)),
        emit_finalize_fn=lambda runtime, stage, detail, progress, terminal_kind=None: runtime.emit(
            FinalizeProcessingStatusEvent(stage=stage, detail=detail, progress=progress, terminal_kind=terminal_kind)
        ),
        emit_log_fn=lambda runtime, **payload: runtime.emit(AppendLogEvent(payload=payload)),
    )

    service.run_processing_worker(
        runtime=RuntimeStub(),
        uploaded_filename="report.docx",
        jobs=[{"target_text": "x", "context_before": "", "context_after": "", "target_chars": 1, "context_chars": 0}],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
    )

    assert any(isinstance(event, SetStateEvent) and event.values["latest_markdown"] == "Готово" for event in emitted_events)
    assert any(isinstance(event, FinalizeProcessingStatusEvent) and event.stage == "Обработка завершена" and event.terminal_kind == "completed" for event in emitted_events)
    assert any(isinstance(event, AppendLogEvent) and event.payload["status"] == "DONE" for event in emitted_events)
    assert emitted_events[-1] == WorkerCompleteEvent(outcome="succeeded")


def test_get_processing_service_returns_singleton_until_reset(monkeypatch):
    processing_service.reset_processing_service()

    build_calls = []
    singleton = _build_service()
    monkeypatch.setattr(processing_service, "build_processing_service", lambda: (build_calls.append(True), singleton)[1])

    first = processing_service.get_processing_service()
    second = processing_service.get_processing_service()

    assert first is singleton
    assert second is singleton
    assert len(build_calls) == 1

    processing_service.reset_processing_service()


def test_build_processing_service_builds_runtime_emitters_from_processing_runtime(monkeypatch):
    processing_service.reset_processing_service()

    emit_state = object()
    emit_finalize = object()
    emit_activity = object()
    emit_log = object()
    emit_status = object()
    emit_image_log = object()
    emit_image_reset = object()
    captured = {}

    monkeypatch.setattr(processing_service, "set_processing_status", object())
    monkeypatch.setattr(processing_service, "finalize_processing_status", object())
    monkeypatch.setattr(processing_service, "push_activity", object())
    monkeypatch.setattr(processing_service, "append_log", object())
    monkeypatch.setattr(processing_service, "append_image_log", object())
    monkeypatch.setattr(
        processing_service,
        "build_runtime_event_emitters",
        lambda *, dependencies: (
            captured.setdefault("dependencies", dependencies),
            type(
                "Emitters",
                (),
                {
                    "emit_state": emit_state,
                    "emit_finalize": emit_finalize,
                    "emit_activity": emit_activity,
                    "emit_log": emit_log,
                    "emit_status": emit_status,
                    "emit_image_log": emit_image_log,
                    "emit_image_reset": emit_image_reset,
                },
            )(),
        )[1],
    )
    monkeypatch.setattr(processing_service, "ProcessingService", lambda **kwargs: (captured.setdefault("kwargs", kwargs), object())[1])

    processing_service.build_processing_service()

    assert captured["dependencies"].set_processing_status is processing_service.set_processing_status
    assert captured["dependencies"].finalize_processing_status is processing_service.finalize_processing_status
    assert captured["dependencies"].push_activity is processing_service.push_activity
    assert captured["dependencies"].append_log is processing_service.append_log
    assert captured["dependencies"].append_image_log is processing_service.append_image_log
    service_dependencies = captured["kwargs"]["dependencies"]
    assert service_dependencies.emit_state_fn is emit_state
    assert service_dependencies.emit_finalize_fn is emit_finalize
    assert service_dependencies.emit_activity_fn is emit_activity
    assert service_dependencies.emit_log_fn is emit_log
    assert service_dependencies.emit_status_fn is emit_status
    assert service_dependencies.emit_image_log_fn is emit_image_log
    assert service_dependencies.emit_image_reset_fn is emit_image_reset


def test_run_prepared_background_document_uses_preparation_and_job_mutator(monkeypatch):
    service = _build_service(run_document_processing_impl_fn=lambda **kwargs: "succeeded")
    prepared = type(
        "PreparedRunContextStub",
        (),
        {
            "uploaded_filename": "prepared-report.docx",
            "jobs": [{"target_text": "one"}],
            "paragraphs": ["p1"],
            "image_assets": ["img1"],
        },
    )()
    captured = {}

    monkeypatch.setattr(processing_service, "freeze_uploaded_file", lambda uploaded_file: {"frozen": uploaded_file})
    monkeypatch.setattr(
        processing_service.application_flow,
        "prepare_run_context_for_background",
        lambda **kwargs: (captured.setdefault("prepare", kwargs), prepared)[1],
    )

    result, returned_prepared = service.run_prepared_background_document(
        uploaded_file="report.docx",
        chunk_size=123,
        image_mode="safe",
        keep_all_image_variants=False,
        app_config={"x": 1},
        model="gpt-5.4",
        max_retries=2,
        job_mutator=lambda job: {**job, "job_kind": "passthrough"},
        progress_callback=None,
        runtime={"state": {}},
    )

    assert captured["prepare"]["uploaded_payload"] == {"frozen": "report.docx"}
    assert captured["prepare"]["chunk_size"] == 123
    assert captured["prepare"]["app_config"] == {"x": 1}
    assert result == "succeeded"
    assert returned_prepared is prepared


def test_run_prepared_background_document_passes_prepared_payload_into_processing(monkeypatch):
    captured = {}
    service = _build_service(
        run_document_processing_impl_fn=lambda **kwargs: (captured.setdefault("run", kwargs), "succeeded")[1],
    )
    prepared = type(
        "PreparedRunContextStub",
        (),
        {
            "uploaded_filename": "prepared-report.docx",
            "jobs": [{"target_text": "one"}],
            "paragraphs": ["p1"],
            "image_assets": ["img1"],
        },
    )()

    monkeypatch.setattr(processing_service, "freeze_uploaded_file", lambda uploaded_file: uploaded_file)
    monkeypatch.setattr(
        processing_service.application_flow,
        "prepare_run_context_for_background",
        lambda **kwargs: prepared,
    )

    service.run_prepared_background_document(
        uploaded_file="report.docx",
        chunk_size=123,
        image_mode="safe",
        keep_all_image_variants=True,
        app_config={"x": 1, "translation_second_pass_enabled": True, "translation_second_pass_model": "gpt-5.4"},
        model="gpt-5.4",
        max_retries=2,
        job_mutator=lambda job: {**job, "job_kind": "passthrough"},
        progress_callback=None,
        runtime={"state": {}},
    )

    assert captured["run"]["uploaded_file"] == "prepared-report.docx"
    assert captured["run"]["jobs"] == [{"target_text": "one", "job_kind": "passthrough"}]
    assert captured["run"]["source_paragraphs"] == ["p1"]
    assert captured["run"]["image_assets"] == ["img1"]
    assert captured["run"]["app_config"]["translation_second_pass_enabled"] is True
    assert captured["run"]["app_config"]["translation_second_pass_model"] == "gpt-5.4"


def test_run_prepared_background_document_supports_distinct_prepare_and_processing_callbacks(monkeypatch):
    captured = {}
    service = _build_service(
        run_document_processing_impl_fn=lambda **kwargs: (captured.setdefault("run", kwargs), "succeeded")[1],
    )
    prepared = type(
        "PreparedRunContextStub",
        (),
        {
            "uploaded_filename": "prepared-report.docx",
            "jobs": [{"target_text": "one"}],
            "paragraphs": ["p1"],
            "image_assets": ["img1"],
        },
    )()
    prepare_progress_calls = []
    processing_progress_calls = []

    def _prepare_run_context_for_background(**kwargs):
        kwargs["progress_callback"](stage="prepare", detail="prepared", progress=0.25)
        return prepared

    def _run_document_processing_impl(**kwargs):
        kwargs["on_progress"](stage="process", detail="running", progress=0.75)
        captured["run"] = kwargs
        return "succeeded"

    service = _build_service(run_document_processing_impl_fn=_run_document_processing_impl)
    monkeypatch.setattr(processing_service, "freeze_uploaded_file", lambda uploaded_file: uploaded_file)
    monkeypatch.setattr(
        processing_service.application_flow,
        "prepare_run_context_for_background",
        _prepare_run_context_for_background,
    )

    service.run_prepared_background_document(
        uploaded_file="report.docx",
        chunk_size=123,
        image_mode="safe",
        keep_all_image_variants=True,
        app_config={"x": 1},
        model="gpt-5.4",
        max_retries=2,
        prepare_progress_callback=lambda **payload: prepare_progress_calls.append(payload),
        processing_progress_callback=lambda **payload: processing_progress_calls.append(payload),
        runtime={"state": {}},
    )

    assert prepare_progress_calls == [{"stage": "prepare", "detail": "prepared", "progress": 0.25}]
    assert processing_progress_calls == [{"stage": "process", "detail": "running", "progress": 0.75}]


def test_clone_processing_service_returns_overridden_copy_without_mutating_singleton(monkeypatch):
    processing_service.reset_processing_service()
    default_service = _build_service()
    monkeypatch.setattr(processing_service, "build_processing_service", lambda: default_service)

    cloned_service = processing_service.clone_processing_service(load_system_prompt_fn=lambda: "override")

    assert cloned_service is not default_service
    assert cloned_service.dependencies.load_system_prompt_fn() == "override"
    assert default_service.dependencies.load_system_prompt_fn() == "system"

    processing_service.reset_processing_service()
