from io import BytesIO
from typing import Any, cast

import docxaicorrector.processing.processing_service as processing_service
from docxaicorrector.core.models import ImageAnalysisResult, ImageAsset, ImageValidationResult
from docxaicorrector.document.segments import DocumentContextProfile, GlossaryTerm
from docxaicorrector.processing.processing_service import ProcessingService
from docxaicorrector.pipeline.contracts import ProcessingContext, ProcessingDependencies
from docxaicorrector.pipeline.setup import initialize_processing_run
from docxaicorrector.runtime.events import AppendLogEvent, FinalizeProcessingStatusEvent, SetStateEvent, WorkerCompleteEvent
from PIL import Image


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
        "get_provider_client_fn": None,
        "get_client_for_model_selector_fn": None,
        "resolve_model_selector_fn": None,
    }
    defaults.update(overrides)
    return ProcessingService(dependencies=processing_service.build_processing_service_dependencies(**defaults))


def test_run_document_processing_fails_on_placeholder_integrity_mismatch():
    emitted_runtime = {}

    service = _build_service(
        generate_markdown_block_fn=lambda **kwargs: "Обработанный блок без placeholder",
        inspect_placeholder_integrity_fn=lambda markdown, assets: {"img_001": "lost"},
        convert_markdown_to_docx_bytes_fn=lambda markdown: (_ for _ in ()).throw(AssertionError("must not build docx")),
        run_document_processing_impl_fn=__import__(
            "docxaicorrector.pipeline._pipeline", fromlist=["run_document_processing"]
        ).run_document_processing,
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


def test_process_document_images_stops_before_next_asset_after_stop_requested_during_first_image(resolved_test_model_registry):
    def _make_png_bytes(color):
        image = Image.new("RGB", (2, 2), color)
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    safe_png_bytes = _make_png_bytes((240, 240, 240))
    candidate_png_bytes = _make_png_bytes((40, 120, 220))
    runtime = {"state": {}, "finalize": [], "activity": [], "status": []}

    service = _build_service(
        process_document_images_impl_fn=processing_service.process_document_images_impl,
        should_stop_processing_fn=lambda current_runtime: bool(current_runtime.get("stop_requested")) if isinstance(current_runtime, dict) else False,
        image_model_call_budget_cls=processing_service.ImageModelCallBudget,
        analyze_image_fn=lambda *args, **kwargs: ImageAnalysisResult(
            image_type="diagram",
            image_subtype=None,
            contains_text=True,
            semantic_redraw_allowed=True,
            confidence=0.95,
            structured_parse_confidence=0.9,
            prompt_key="diagram_semantic_redraw",
            render_strategy="semantic_redraw_structured",
            structure_summary="two boxes connected by an arrow",
            extracted_labels=["Start", "Finish"],
            text_node_count=2,
            extracted_text="Start -> Finish",
            fallback_reason=None,
        ),
        generate_image_candidate_fn=lambda *args, **kwargs: (
            safe_png_bytes
            if kwargs.get("mode") == "safe"
            else runtime.__setitem__("stop_requested", True) or candidate_png_bytes
        ),
        validate_redraw_result_fn=lambda *args, **kwargs: ImageValidationResult(
            validation_passed=True,
            decision="accept",
            semantic_match_score=0.95,
            text_match_score=0.95,
            structure_match_score=0.95,
            validator_confidence=0.95,
            missing_labels=[],
            added_entities_detected=False,
            suspicious_reasons=[],
        ),
        detect_image_mime_type_fn=lambda image_bytes: "image/png",
    )

    result = service.process_document_images(
        image_assets=[
            ImageAsset(
                image_id="img_001",
                placeholder="[[DOCX_IMAGE_img_001]]",
                original_bytes=safe_png_bytes,
                mime_type="image/png",
                position_index=0,
            ),
            ImageAsset(
                image_id="img_002",
                placeholder="[[DOCX_IMAGE_img_002]]",
                original_bytes=safe_png_bytes,
                mime_type="image/png",
                position_index=1,
            ),
        ],
        image_mode="semantic_redraw_direct",
        config={"models": resolved_test_model_registry, "keep_all_image_variants": True},
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        client=object(),
    )

    assert [asset.image_id for asset in result] == ["img_001"]
    assert result[0].final_decision == "accept"
    assert runtime["finalize"][-1] == (
        "Остановлено пользователем",
        "Обработка изображений остановлена пользователем.",
        0.5,
        "stopped",
    )
    assert runtime["activity"][-1] == "Обработка изображений остановлена пользователем."


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
    import docxaicorrector.processing.processing_runtime as processing_runtime
    import docxaicorrector.runtime.state as runtime_state

    processing_service.reset_processing_service()

    emit_state = object()
    emit_finalize = object()
    emit_activity = object()
    emit_log = object()
    emit_status = object()
    emit_image_log = object()
    emit_image_reset = object()
    captured = {}

    push_activity_sentinel = object()
    append_log_sentinel = object()
    append_image_log_sentinel = object()

    # The default service wires the streamlit-backed runtime.state emitters + the
    # processing_runtime emitter machinery, both imported LAZILY (at call time)
    # inside build_default_processing_service_dependencies so that importing
    # processing_service stays streamlit-free (round-4 finding 5). A lazy
    # ``from module import name`` reads the SOURCE module attribute at call time,
    # so patch the source modules rather than a module-level processing_service name.
    monkeypatch.setattr(runtime_state, "set_processing_status", object())
    monkeypatch.setattr(runtime_state, "finalize_processing_status", object())
    monkeypatch.setattr(runtime_state, "push_activity", push_activity_sentinel)
    monkeypatch.setattr(runtime_state, "append_log", append_log_sentinel)
    monkeypatch.setattr(runtime_state, "append_image_log", append_image_log_sentinel)
    monkeypatch.setattr(
        processing_runtime,
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

    assert captured["dependencies"].push_activity is push_activity_sentinel
    assert captured["dependencies"].append_log is append_log_sentinel
    assert captured["dependencies"].append_image_log is append_image_log_sentinel
    service_dependencies = captured["kwargs"]["dependencies"]
    assert service_dependencies.emit_state_fn is emit_state
    assert service_dependencies.emit_finalize_fn is emit_finalize
    assert service_dependencies.emit_activity_fn is emit_activity
    assert service_dependencies.emit_log_fn is emit_log
    assert service_dependencies.emit_status_fn is emit_status
    assert service_dependencies.emit_image_log_fn is emit_image_log
    assert service_dependencies.emit_image_reset_fn is emit_image_reset


def test_run_prepared_background_document_uses_preparation_and_job_mutator(monkeypatch):
    sentinel_get_client = object()
    service = _build_service(run_document_processing_impl_fn=lambda **kwargs: "succeeded", get_client_fn=sentinel_get_client)
    prepared = type(
        "PreparedRunContextStub",
        (),
        {
            "uploaded_filename": "prepared-report.docx",
            "jobs": [{"target_text": "one"}],
            "paragraphs": ["p1"],
            "image_assets": ["img1"],
            "translation_domain": "theology",
            "translation_domain_instructions": "TERM PLAN",
            "document_context_profile": DocumentContextProfile(
                glossary_terms=(GlossaryTerm(source_term="Great Tribulation", target_term="Великая скорбь"),),
            ),
        },
    )()
    captured = {}

    monkeypatch.setattr(processing_service, "freeze_uploaded_file", lambda uploaded_file: {"frozen": uploaded_file})
    monkeypatch.setattr(
        processing_service,
        "prepare_document_for_processing",
        lambda **kwargs: captured.setdefault("prepare_document", kwargs) or object(),
    )
    monkeypatch.setattr(
        processing_service,
        "prepare_run_context_for_background",
        lambda **kwargs: (
            kwargs["prepare_document_for_processing_fn"](
                uploaded_payload={"payload": True},
                chunk_size=kwargs["chunk_size"],
                app_config=kwargs["app_config"],
                processing_operation=kwargs["processing_operation"],
                session_state=None,
                progress_callback=None,
            ),
            captured.setdefault("prepare", kwargs),
            prepared,
        )[-1],
    )

    result, returned_prepared = service.run_prepared_background_document(
        uploaded_file="report.docx",
        chunk_size=123,
        image_mode="safe",
        keep_all_image_variants=False,
        app_config={"x": 1},
        model="gpt-5.4",
        max_retries=2,
        processing_operation="audiobook",
        job_mutator=lambda job: {**job, "job_kind": "passthrough"},
        progress_callback=None,
        runtime={"state": {}},
    )

    assert captured["prepare"]["uploaded_payload"] == {"frozen": "report.docx"}
    assert captured["prepare"]["chunk_size"] == 123
    assert captured["prepare"]["app_config"] == {"x": 1}
    assert captured["prepare"]["processing_operation"] == "audiobook"
    assert callable(captured["prepare_document"]["get_client_fn"])
    assert captured["prepare_document"]["get_client_fn"]() is sentinel_get_client
    assert captured["prepare_document"]["chunk_size"] == 123
    assert captured["prepare_document"]["processing_operation"] == "audiobook"
    assert result == "succeeded"
    assert returned_prepared is prepared


def test_run_prepared_background_document_uses_model_aware_client_factory_for_preparation(monkeypatch):
    sentinel_model_client = object()
    sentinel_document_map_client = object()
    sentinel_default_client = object()
    app_config = {
        "structure_recognition_model": "openrouter:test/structure",
        "structure_recovery_document_map_model": "openrouter:test/document-map",
    }
    captured = {}

    def _selector_client_factory(selector, required_capability, *, config_like=None):
        captured.setdefault("selector_calls", []).append((selector, required_capability, config_like))
        if selector == "openrouter:test/document-map":
            return sentinel_document_map_client
        return sentinel_model_client

    service = _build_service(
        run_document_processing_impl_fn=lambda **kwargs: "succeeded",
        get_client_fn=lambda: sentinel_default_client,
        get_client_for_model_selector_fn=_selector_client_factory,
    )
    prepared = type(
        "PreparedRunContextStub",
        (),
        {
            "uploaded_filename": "prepared-report.docx",
            "jobs": [{"target_text": "one"}],
            "paragraphs": ["p1"],
            "image_assets": ["img1"],
            "translation_domain": "general",
            "translation_domain_instructions": "",
            "document_context_profile": DocumentContextProfile(),
        },
    )()

    monkeypatch.setattr(processing_service, "freeze_uploaded_file", lambda uploaded_file: {"frozen": uploaded_file})
    monkeypatch.setattr(
        processing_service,
        "prepare_document_for_processing",
        lambda **kwargs: captured.setdefault("prepare_document", kwargs) or object(),
    )
    monkeypatch.setattr(
        processing_service,
        "prepare_run_context_for_background",
        lambda **kwargs: (
            kwargs["prepare_document_for_processing_fn"](
                uploaded_payload={"payload": True},
                chunk_size=kwargs["chunk_size"],
                app_config=kwargs["app_config"],
                processing_operation=kwargs["processing_operation"],
                session_state=None,
                progress_callback=None,
            ),
            prepared,
        )[-1],
    )

    service.run_prepared_background_document(
        uploaded_file="report.docx",
        chunk_size=123,
        image_mode="safe",
        keep_all_image_variants=False,
        app_config=app_config,
        model="gpt-5.4",
        max_retries=2,
        processing_operation="edit",
        progress_callback=None,
        runtime={"state": {}},
    )

    assert callable(captured["prepare_document"]["get_client_fn"])
    assert captured["prepare_document"]["get_client_fn"]() is sentinel_model_client
    assert captured["prepare_document"]["get_client_fn"](
        "openrouter:test/document-map",
        "responses_text",
        config_like=app_config,
    ) is sentinel_document_map_client
    assert captured["selector_calls"] == [
        ("openrouter:test/structure", "responses_text", app_config),
        ("openrouter:test/document-map", "responses_text", app_config),
    ]


def test_run_prepared_background_document_model_factory_uses_default_when_selector_omitted(monkeypatch):
    sentinel_model_client = object()
    captured = {}

    def _selector_client_factory(selector, required_capability, *, config_like=None):
        captured["selector_call"] = (selector, required_capability, config_like)
        return sentinel_model_client

    service = _build_service(
        run_document_processing_impl_fn=lambda **kwargs: "succeeded",
        get_client_fn=lambda: object(),
        get_client_for_model_selector_fn=_selector_client_factory,
    )
    prepared = type(
        "PreparedRunContextStub",
        (),
        {
            "uploaded_filename": "prepared-report.docx",
            "jobs": [{"target_text": "one"}],
            "paragraphs": ["p1"],
            "image_assets": ["img1"],
            "translation_domain": "general",
            "translation_domain_instructions": "",
            "document_context_profile": DocumentContextProfile(),
        },
    )()

    monkeypatch.setattr(processing_service, "freeze_uploaded_file", lambda uploaded_file: {"frozen": uploaded_file})
    monkeypatch.setattr(
        processing_service,
        "prepare_document_for_processing",
        lambda **kwargs: captured.setdefault("prepare_document", kwargs) or object(),
    )
    monkeypatch.setattr(
        processing_service,
        "prepare_run_context_for_background",
        lambda **kwargs: (
            kwargs["prepare_document_for_processing_fn"](
                uploaded_payload={"payload": True},
                chunk_size=kwargs["chunk_size"],
                app_config=kwargs["app_config"],
                processing_operation=kwargs["processing_operation"],
                session_state=None,
                progress_callback=None,
            ),
            prepared,
        )[-1],
    )

    service.run_prepared_background_document(
        uploaded_file="report.docx",
        chunk_size=123,
        image_mode="safe",
        keep_all_image_variants=False,
        app_config={"structure_recognition_model": "openrouter:test/structure"},
        model="gpt-5.4",
        max_retries=2,
        processing_operation="edit",
        progress_callback=None,
        runtime={"state": {}},
    )

    assert captured["prepare_document"]["get_client_fn"]() is sentinel_model_client
    assert captured["selector_call"] == (
        "openrouter:test/structure",
        "responses_text",
        {"structure_recognition_model": "openrouter:test/structure"},
    )


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
            "jobs": [{"target_text": "one", "job_id": "job_0000"}],
            "selected_segment_ids": ["seg_0001", "seg_0002"],
            "segments": [
                type("SegmentStub", (), {"segment_id": "seg_0001", "ordinal": 1, "level": 1, "structural_role": "chapter", "title": "Chapter 1"})(),
                type("SegmentStub", (), {"segment_id": "seg_0002", "ordinal": 2, "level": 1, "structural_role": "chapter", "title": "Chapter 2"})(),
                type("SegmentStub", (), {"segment_id": "seg_0003", "ordinal": 3, "level": 1, "structural_role": "chapter", "title": "Chapter 3"})(),
            ],
            "paragraphs": ["p1"],
            "image_assets": ["img1"],
            "translation_domain": "theology",
            "translation_domain_instructions": "TERM PLAN",
            "document_context_profile": DocumentContextProfile(
                glossary_terms=(GlossaryTerm(source_term="Great Tribulation", target_term="Великая скорбь"),),
            ),
        },
    )()

    monkeypatch.setattr(processing_service, "freeze_uploaded_file", lambda uploaded_file: uploaded_file)
    monkeypatch.setattr(
        processing_service,
        "prepare_run_context_for_background",
        lambda **kwargs: prepared,
    )

    service.run_prepared_background_document(
        uploaded_file="report.docx",
        chunk_size=123,
        image_mode="safe",
        keep_all_image_variants=True,
        app_config={"x": 1},
        model="gpt-5.4",
        max_retries=2,
        job_mutator=lambda job: {**job, "job_kind": "passthrough"},
        progress_callback=None,
        runtime={"state": {}},
    )

    assert captured["run"]["uploaded_file"] == "prepared-report.docx"
    assert captured["run"]["jobs"] == [{"target_text": "one", "job_id": "job_0000", "job_kind": "passthrough"}]
    assert captured["run"]["source_paragraphs"] == ["p1"]
    assert captured["run"]["image_assets"] == ["img1"]
    assert captured["run"]["app_config"]["x"] == 1
    assert captured["run"]["app_config"]["translation_domain_default"] == "theology"
    assert captured["run"]["app_config"]["translation_domain_instructions"] == "TERM PLAN"
    # Full-document run: build_document_context_prompt still emits the base document
    # context (glossary) but no partial selected-segment focus block.
    assert "Great Tribulation" in captured["run"]["document_context_prompt"]
    assert "ФОКУС ТЕКУЩЕГО ЗАПУСКА" not in captured["run"]["document_context_prompt"]


def test_run_processing_worker_passes_selected_segment_ids_to_pipeline(monkeypatch):
    captured = {}
    service = _build_service(
        run_document_processing_impl_fn=lambda **kwargs: (captured.setdefault("run", kwargs), "succeeded")[1],
    )

    service.run_processing_worker(
        runtime=type("RuntimeStub", (), {"emit": lambda self, event: None})(),
        uploaded_filename="report.docx",
        jobs=[{"target_text": "x", "context_before": "", "context_after": "", "target_chars": 1, "context_chars": 0}],
        selected_segment_ids=["seg_0003"],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
    )

    assert captured["run"]["selected_segment_ids"] == ["seg_0003"]


def test_run_prepared_background_document_passes_selected_segment_ids_none_when_absent(monkeypatch):
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
            "translation_domain": "general",
            "translation_domain_instructions": "",
        },
    )()

    monkeypatch.setattr(processing_service, "freeze_uploaded_file", lambda uploaded_file: uploaded_file)
    monkeypatch.setattr(
        processing_service,
        "prepare_run_context_for_background",
        lambda **kwargs: prepared,
    )

    service.run_prepared_background_document(
        uploaded_file="report.docx",
        chunk_size=123,
        image_mode="safe",
        keep_all_image_variants=True,
        app_config={"x": 1},
        model="gpt-5.4",
        max_retries=2,
        progress_callback=None,
        runtime={"state": {}},
    )

    assert captured["run"]["selected_segment_ids"] is None


def test_initialize_processing_run_builds_segment_runtime_metadata():
    dependencies = ProcessingDependencies(
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "markdown",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=lambda markdown_text, image_assets: {},
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=lambda **kwargs: {},
    )
    emitters = type(
        "EmittersStub",
        (),
        {
            "emit_state": lambda *args, **kwargs: None,
            "emit_finalize": lambda *args, **kwargs: None,
            "emit_activity": lambda *args, **kwargs: None,
            "emit_log": lambda *args, **kwargs: None,
            "emit_status": lambda *args, **kwargs: None,
        },
    )()
    context = ProcessingContext(
        uploaded_file="report.docx",
        uploaded_filename="report.docx",
            source_token="report.docx:token",
            run_id="run-123",
        jobs=[
            {"target_text": "block-1", "target_chars": 7, "context_chars": 0, "segment_id": "seg_0001"},
            {"target_text": "block-2", "target_chars": 7, "context_chars": 0, "segment_id": "seg_0002"},
        ],
        selected_segment_ids=("seg_0001", "seg_0002"),
            document_segments=(),
            segment_selection_mode="selected_segments",
        output_mode="selected_only",
        include_front_matter=False,
        include_toc=False,
        source_paragraphs=cast(Any, [
            type("ParagraphStub", (), {"segment_id": "seg_0001", "text": "Chapter 1"})(),
            type("ParagraphStub", (), {"segment_id": "seg_0002", "text": "Chapter 2"})(),
        ]),
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        processing_operation="edit",
        source_language="en",
        target_language="ru",
        translation_domain="general",
        translation_domain_instructions="",
        on_progress=lambda **kwargs: None,
        runtime=None,
    )

    initialization: Any = initialize_processing_run(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        emit_failed_result_fn=lambda **kwargs: "failed",
        summarize_block_plan_fn=lambda jobs: {
            "block_count": len(jobs),
            "llm_block_count": len(jobs),
            "passthrough_block_count": 0,
            "total_target_chars": 14,
            "min_target_chars": 7,
            "max_target_chars": 7,
            "avg_target_chars": 7.0,
            "first_block_target_chars": [7, 7],
            "blocks": [],
        },
        initialization_factory_fn=lambda **kwargs: kwargs,
    )

    assert initialization["segment_ids_by_job"] == ("seg_0001", "seg_0002")
    assert initialization["segment_titles_by_id"] == {"seg_0001": "Chapter 1", "seg_0002": "Chapter 2"}
    assert initialization["segment_job_totals"] == {"seg_0001": 1, "seg_0002": 1}


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
        processing_service,
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


def test_run_prepared_background_document_emits_controlled_failure_when_preparation_blocks(monkeypatch):
    emitted_events = []

    class RuntimeStub:
        def emit(self, event):
            emitted_events.append(event)

    service = _build_service(run_document_processing_impl_fn=lambda **kwargs: "succeeded")

    monkeypatch.setattr(processing_service, "freeze_uploaded_file", lambda uploaded_file: uploaded_file)
    monkeypatch.setattr(
        processing_service,
        "prepare_run_context_for_background",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("quality gate blocked")),
    )

    try:
        service.run_prepared_background_document(
            uploaded_file="report.docx",
            chunk_size=123,
            image_mode="safe",
            keep_all_image_variants=True,
            app_config={"x": 1},
            model="gpt-5.4",
            max_retries=2,
            runtime=RuntimeStub(),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected preparation exception to be re-raised")

    assert emitted_events[-1] == WorkerCompleteEvent(outcome="failed")
    assert any(
        isinstance(event, SetStateEvent)
        and cast(dict[str, Any], event.values.get("last_background_error") or {}).get("stage") == "preparation"
        for event in emitted_events
    )
    assert any(isinstance(event, FinalizeProcessingStatusEvent) and event.stage == "Ошибка подготовки" for event in emitted_events)
    assert any(isinstance(event, AppendLogEvent) and event.payload["status"] == "ERROR" for event in emitted_events)


def test_clone_processing_service_returns_overridden_copy_without_mutating_singleton(monkeypatch):
    processing_service.reset_processing_service()
    default_service = _build_service()
    monkeypatch.setattr(processing_service, "build_processing_service", lambda: default_service)

    cloned_service = processing_service.clone_processing_service(load_system_prompt_fn=lambda: "override")

    assert cloned_service is not default_service
    assert cloned_service.dependencies.load_system_prompt_fn() == "override"
    assert default_service.dependencies.load_system_prompt_fn() == "system"

    processing_service.reset_processing_service()
