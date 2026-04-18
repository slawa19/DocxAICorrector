from dataclasses import dataclass, replace
from collections.abc import Callable, Mapping, Sequence
from threading import Lock
from typing import Any, cast

from config import get_client, load_system_prompt
from document import inspect_placeholder_integrity
from formatting_transfer import normalize_semantic_output_docx, preserve_source_paragraph_properties
from image_reinsertion import reinsert_inline_images
from document_pipeline import (
    ActivityEmitter,
    ClientFactory,
    ErrorPresenter,
    EventLogger,
    FilenameResolver,
    FinalizeEmitter,
    LogEmitter,
    MarkdownGenerator,
    MarkdownToDocxConverter,
    ParagraphPropertiesPreserver,
    PlaceholderInspector,
    SemanticDocxNormalizer,
    StateEmitter,
    StatusEmitter,
    StopPredicate,
    SystemPromptLoader,
    ImageReinserter,
    run_document_processing as run_document_processing_impl,
)
from generation import convert_markdown_to_docx_bytes, ensure_pandoc_available, generate_markdown_block
from image_analysis import analyze_image
from image_generation import (
    ImageModelCallBudget,
    ImageModelCallBudgetExceeded,
    detect_image_mime_type,
    generate_image_candidate,
)
from image_pipeline import ImageProcessingContext, process_document_images as process_document_images_impl
from image_validation import validate_redraw_result
from logger import log_event, present_error
from processing_runtime import (
    RuntimeEventEmitterDependencies,
    build_runtime_event_emitters,
    freeze_uploaded_file,
    normalize_background_error,
    resolve_uploaded_filename,
    should_stop_processing,
)
import application_flow
from runtime_events import AppendLogEvent, FinalizeProcessingStatusEvent, PushActivityEvent, SetStateEvent, WorkerCompleteEvent
from state import append_image_log, append_log, finalize_processing_status, push_activity, set_processing_status


@dataclass(frozen=True)
class ProcessingServiceDependencies:
    get_client_fn: ClientFactory
    load_system_prompt_fn: SystemPromptLoader
    ensure_pandoc_available_fn: Callable[[], None]
    generate_markdown_block_fn: MarkdownGenerator
    convert_markdown_to_docx_bytes_fn: MarkdownToDocxConverter
    process_document_images_impl_fn: Callable[..., list]
    analyze_image_fn: Callable[..., Any]
    generate_image_candidate_fn: Callable[..., Any]
    validate_redraw_result_fn: Callable[..., Any]
    detect_image_mime_type_fn: Callable[..., str | None]
    inspect_placeholder_integrity_fn: PlaceholderInspector
    preserve_source_paragraph_properties_fn: ParagraphPropertiesPreserver
    normalize_semantic_output_docx_fn: SemanticDocxNormalizer
    reinsert_inline_images_fn: ImageReinserter
    run_document_processing_impl_fn: Callable[..., str]
    present_error_fn: ErrorPresenter
    log_event_fn: EventLogger
    emit_state_fn: StateEmitter
    emit_finalize_fn: FinalizeEmitter
    emit_activity_fn: ActivityEmitter
    emit_log_fn: LogEmitter
    emit_status_fn: StatusEmitter
    emit_image_log_fn: Callable[..., object]
    emit_image_reset_fn: Callable[..., object]
    should_stop_processing_fn: StopPredicate
    resolve_uploaded_filename_fn: FilenameResolver
    image_model_call_budget_cls: type
    image_model_call_budget_exceeded_cls: type


@dataclass
class ProcessingService:
    dependencies: ProcessingServiceDependencies

    def clone(self, **dependency_overrides: Any) -> "ProcessingService":
        return ProcessingService(dependencies=replace(self.dependencies, **dependency_overrides))

    def process_document_images(
        self,
        *,
        image_assets,
        image_mode: str,
        config: dict[str, object],
        on_progress,
        runtime=None,
        client=None,
    ) -> list:
        deps = self.dependencies
        pipeline_context = ImageProcessingContext(
            config=config,
            on_progress=on_progress,
            runtime=runtime,
            client=client,
            emit_state=deps.emit_state_fn,
            emit_image_reset=deps.emit_image_reset_fn,
            emit_finalize=deps.emit_finalize_fn,
            emit_activity=deps.emit_activity_fn,
            emit_status=deps.emit_status_fn,
            emit_image_log=deps.emit_image_log_fn,
            should_stop=deps.should_stop_processing_fn,
            analyze_image_fn=deps.analyze_image_fn,
            generate_image_candidate_fn=deps.generate_image_candidate_fn,
            validate_redraw_result_fn=deps.validate_redraw_result_fn,
            get_client_fn=deps.get_client_fn,
            log_event_fn=deps.log_event_fn,
            detect_image_mime_type_fn=deps.detect_image_mime_type_fn,
            image_model_call_budget_cls=deps.image_model_call_budget_cls,
            image_model_call_budget_exceeded_cls=deps.image_model_call_budget_exceeded_cls,
        )
        return deps.process_document_images_impl_fn(
            image_assets=image_assets,
            image_mode=image_mode,
            context=pipeline_context,
        )

    def run_document_processing(
        self,
        *,
        uploaded_file,
        jobs: Sequence[Mapping[str, object]],
        source_paragraphs: list | None = None,
        image_assets: list,
        image_mode: str,
        app_config: dict[str, object],
        model: str,
        max_retries: int,
        processing_operation: str = "edit",
        source_language: str = "en",
        target_language: str = "ru",
        on_progress,
        runtime=None,
    ) -> str:
        deps = self.dependencies
        return deps.run_document_processing_impl_fn(
            uploaded_file=uploaded_file,
            jobs=cast(list[dict[str, str | int]], list(jobs)),
            source_paragraphs=source_paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
            on_progress=on_progress,
            runtime=runtime,
            resolve_uploaded_filename=deps.resolve_uploaded_filename_fn,
            get_client=deps.get_client_fn,
            ensure_pandoc_available=deps.ensure_pandoc_available_fn,
            load_system_prompt=deps.load_system_prompt_fn,
            log_event=deps.log_event_fn,
            present_error=deps.present_error_fn,
            emit_state=deps.emit_state_fn,
            emit_finalize=deps.emit_finalize_fn,
            emit_activity=deps.emit_activity_fn,
            emit_log=deps.emit_log_fn,
            emit_status=deps.emit_status_fn,
            should_stop_processing=deps.should_stop_processing_fn,
            generate_markdown_block=deps.generate_markdown_block_fn,
            process_document_images=self.process_document_images,
            inspect_placeholder_integrity=deps.inspect_placeholder_integrity_fn,
            convert_markdown_to_docx_bytes=deps.convert_markdown_to_docx_bytes_fn,
            preserve_source_paragraph_properties=deps.preserve_source_paragraph_properties_fn,
            normalize_semantic_output_docx=deps.normalize_semantic_output_docx_fn,
            reinsert_inline_images=deps.reinsert_inline_images_fn,
        )

    def run_processing_worker(
        self,
        *,
        runtime,
        uploaded_filename: str,
        jobs: Sequence[Mapping[str, object]],
        source_paragraphs: list | None = None,
        image_assets: list,
        image_mode: str,
        app_config: dict[str, object],
        model: str,
        max_retries: int,
        processing_operation: str = "edit",
        source_language: str = "en",
        target_language: str = "ru",
    ) -> None:
        outcome = "failed"
        deps = self.dependencies
        try:
            outcome = self.run_document_processing(
                uploaded_file=uploaded_filename,
                jobs=jobs,
                source_paragraphs=source_paragraphs,
                image_assets=image_assets,
                image_mode=image_mode,
                app_config=app_config,
                model=model,
                max_retries=max_retries,
                processing_operation=processing_operation,
                source_language=source_language,
                target_language=target_language,
                on_progress=lambda **kwargs: None,
                runtime=runtime,
            )
        except Exception as exc:
            error_message = deps.present_error_fn(
                "processing_worker_crashed",
                exc,
                "Критическая ошибка фоновой обработки",
                filename=uploaded_filename,
                block_count=len(jobs),
            )
            background_error = normalize_background_error(
                stage="processing",
                exc=exc,
                user_message=error_message,
            )
            runtime.emit(SetStateEvent(values={"last_error": error_message, "last_background_error": background_error}))
            runtime.emit(FinalizeProcessingStatusEvent(stage="Критическая ошибка", detail=error_message, progress=1.0, terminal_kind="error"))
            runtime.emit(PushActivityEvent(message="Фоновый worker аварийно завершился; runtime-state принудительно очищается."))
            runtime.emit(
                AppendLogEvent(
                    payload={
                        "status": "ERROR",
                        "block_index": 0,
                        "block_count": len(jobs),
                        "target_chars": 0,
                        "context_chars": 0,
                        "details": error_message,
                    }
                )
            )
        finally:
            runtime.emit(WorkerCompleteEvent(outcome=outcome))

    def run_prepared_background_document(
        self,
        *,
        uploaded_file,
        chunk_size: int,
        image_mode: str,
        keep_all_image_variants: bool,
        app_config: dict[str, object],
        model: str,
        max_retries: int,
        processing_operation: str = "edit",
        source_language: str = "en",
        target_language: str = "ru",
        job_mutator: Callable[[Mapping[str, object]], dict[str, object]] | None = None,
        progress_callback=None,
        prepare_progress_callback=None,
        processing_progress_callback=None,
        runtime=None,
    ) -> tuple[str, application_flow.PreparedRunContext]:
        resolved_prepare_progress_callback = prepare_progress_callback or progress_callback
        resolved_processing_progress_callback = processing_progress_callback or progress_callback or (lambda **kwargs: None)
        uploaded_payload = freeze_uploaded_file(uploaded_file)
        prepared = application_flow.prepare_run_context_for_background(
            uploaded_payload=uploaded_payload,
            chunk_size=chunk_size,
            image_mode=image_mode,
            keep_all_image_variants=keep_all_image_variants,
            app_config=app_config,
            progress_callback=resolved_prepare_progress_callback,
        )
        jobs = _mutate_processing_jobs(prepared.jobs, job_mutator=job_mutator)
        result = self.run_document_processing(
            uploaded_file=prepared.uploaded_filename,
            jobs=cast(Sequence[Mapping[str, object]], jobs),
            source_paragraphs=prepared.paragraphs,
            image_assets=prepared.image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
            processing_operation=processing_operation,
            source_language=source_language,
            target_language=target_language,
            on_progress=resolved_processing_progress_callback,
            runtime=runtime,
        )
        return result, prepared


def _mutate_processing_jobs(
    jobs: Sequence[Mapping[str, object]],
    *,
    job_mutator: Callable[[Mapping[str, object]], dict[str, object]] | None,
) -> list[dict[str, object]]:
    if job_mutator is None:
        return [dict(job) for job in jobs]
    return [job_mutator(job) for job in jobs]


def build_processing_service_dependencies(**overrides: Any) -> ProcessingServiceDependencies:
    return ProcessingServiceDependencies(**overrides)


def build_default_processing_service_dependencies() -> ProcessingServiceDependencies:
    from config import load_app_config as _load_app_config

    _cfg = _load_app_config()
    _body_font = _cfg.output_body_font
    _heading_font = _cfg.output_heading_font

    def _convert_markdown_with_fonts(markdown_text: str) -> bytes:
        return convert_markdown_to_docx_bytes(
            markdown_text,
            body_font=_body_font,
            heading_font=_heading_font,
        )

    def _generate_markdown_block(**kwargs: Any) -> str:
        return generate_markdown_block(**kwargs)

    def _inspect_placeholder_integrity(markdown_text: str, image_assets) -> Mapping[str, str]:
        return inspect_placeholder_integrity(markdown_text, list(image_assets))

    def _preserve_source_paragraph_properties(docx_bytes: bytes, paragraphs, generated_paragraph_registry=None) -> bytes:
        return preserve_source_paragraph_properties(
            docx_bytes,
            list(paragraphs),
            generated_paragraph_registry=generated_paragraph_registry,
        )

    def _normalize_semantic_output_docx(docx_bytes: bytes, paragraphs, generated_paragraph_registry=None) -> bytes:
        return normalize_semantic_output_docx(
            docx_bytes,
            list(paragraphs),
            generated_paragraph_registry=generated_paragraph_registry,
        )

    def _reinsert_inline_images(docx_bytes: bytes, image_assets) -> bytes:
        return reinsert_inline_images(docx_bytes, list(image_assets))

    def _present_error(code: str, exc: Exception, title: str, **context: object) -> str:
        return present_error(code, exc, title, **context)

    def _log_event(level: int, event_id: str, message: str, **context: object) -> None:
        log_event(level, event_id, message, **context)

    def _should_stop_processing(runtime: Any) -> bool:
        return should_stop_processing(runtime)

    runtime_emitters = build_runtime_event_emitters(
        dependencies=RuntimeEventEmitterDependencies(
            set_processing_status=set_processing_status,
            finalize_processing_status=finalize_processing_status,
            push_activity=push_activity,
            append_log=append_log,
            append_image_log=append_image_log,
        )
    )

    return build_processing_service_dependencies(
        get_client_fn=get_client,
        load_system_prompt_fn=load_system_prompt,
        ensure_pandoc_available_fn=ensure_pandoc_available,
        generate_markdown_block_fn=_generate_markdown_block,
        convert_markdown_to_docx_bytes_fn=_convert_markdown_with_fonts,
        process_document_images_impl_fn=process_document_images_impl,
        analyze_image_fn=analyze_image,
        generate_image_candidate_fn=generate_image_candidate,
        validate_redraw_result_fn=validate_redraw_result,
        detect_image_mime_type_fn=detect_image_mime_type,
        inspect_placeholder_integrity_fn=_inspect_placeholder_integrity,
        preserve_source_paragraph_properties_fn=_preserve_source_paragraph_properties,
        normalize_semantic_output_docx_fn=_normalize_semantic_output_docx,
        reinsert_inline_images_fn=_reinsert_inline_images,
        run_document_processing_impl_fn=run_document_processing_impl,
        present_error_fn=_present_error,
        log_event_fn=_log_event,
        emit_state_fn=runtime_emitters.emit_state,
        emit_finalize_fn=runtime_emitters.emit_finalize,
        emit_activity_fn=runtime_emitters.emit_activity,
        emit_log_fn=runtime_emitters.emit_log,
        emit_status_fn=runtime_emitters.emit_status,
        emit_image_log_fn=runtime_emitters.emit_image_log,
        emit_image_reset_fn=runtime_emitters.emit_image_reset,
        should_stop_processing_fn=_should_stop_processing,
        resolve_uploaded_filename_fn=resolve_uploaded_filename,
        image_model_call_budget_cls=ImageModelCallBudget,
        image_model_call_budget_exceeded_cls=ImageModelCallBudgetExceeded,
    )


def build_processing_service() -> ProcessingService:
    return ProcessingService(dependencies=build_default_processing_service_dependencies())


_DEFAULT_PROCESSING_SERVICE: ProcessingService | None = None
_DEFAULT_PROCESSING_SERVICE_LOCK = Lock()


def get_processing_service() -> ProcessingService:
    global _DEFAULT_PROCESSING_SERVICE
    if _DEFAULT_PROCESSING_SERVICE is None:
        with _DEFAULT_PROCESSING_SERVICE_LOCK:
            if _DEFAULT_PROCESSING_SERVICE is None:
                _DEFAULT_PROCESSING_SERVICE = build_processing_service()
    return _DEFAULT_PROCESSING_SERVICE


def reset_processing_service() -> None:
    global _DEFAULT_PROCESSING_SERVICE
    with _DEFAULT_PROCESSING_SERVICE_LOCK:
        _DEFAULT_PROCESSING_SERVICE = None


def clone_processing_service(**overrides: Any) -> ProcessingService:
    return get_processing_service().clone(**overrides)


__all__ = [
    "ProcessingServiceDependencies",
    "ProcessingService",
    "build_processing_service_dependencies",
    "build_default_processing_service_dependencies",
    "build_processing_service",
    "get_processing_service",
    "reset_processing_service",
    "clone_processing_service",
]
