from dataclasses import dataclass
from threading import Lock

from app_runtime import (
    emit_activity as emit_activity_impl,
    emit_finalize as emit_finalize_impl,
    emit_image_log as emit_image_log_impl,
    emit_image_reset as emit_image_reset_impl,
    emit_log as emit_log_impl,
    emit_state as emit_state_impl,
    emit_status as emit_status_impl,
)
from config import get_client, load_system_prompt
from document import inspect_placeholder_integrity, reinsert_inline_images
from document_pipeline import run_document_processing as run_document_processing_impl
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
from processing_runtime import resolve_uploaded_filename, should_stop_processing
from runtime_events import AppendLogEvent, FinalizeProcessingStatusEvent, PushActivityEvent, SetStateEvent, WorkerCompleteEvent


@dataclass
class ProcessingService:
    get_client_fn: object
    load_system_prompt_fn: object
    ensure_pandoc_available_fn: object
    generate_markdown_block_fn: object
    convert_markdown_to_docx_bytes_fn: object
    process_document_images_impl_fn: object
    analyze_image_fn: object
    generate_image_candidate_fn: object
    validate_redraw_result_fn: object
    detect_image_mime_type_fn: object
    inspect_placeholder_integrity_fn: object
    reinsert_inline_images_fn: object
    run_document_processing_impl_fn: object
    present_error_fn: object
    log_event_fn: object
    emit_state_fn: object
    emit_finalize_fn: object
    emit_activity_fn: object
    emit_log_fn: object
    emit_status_fn: object
    emit_image_log_fn: object
    emit_image_reset_fn: object
    should_stop_processing_fn: object
    resolve_uploaded_filename_fn: object
    image_model_call_budget_cls: type
    image_model_call_budget_exceeded_cls: type

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
        pipeline_context = ImageProcessingContext(
            config=config,
            on_progress=on_progress,
            runtime=runtime,
            client=client,
            emit_state=self.emit_state_fn,
            emit_image_reset=self.emit_image_reset_fn,
            emit_finalize=self.emit_finalize_fn,
            emit_activity=self.emit_activity_fn,
            emit_status=self.emit_status_fn,
            emit_image_log=self.emit_image_log_fn,
            should_stop=self.should_stop_processing_fn,
            analyze_image_fn=self.analyze_image_fn,
            generate_image_candidate_fn=self.generate_image_candidate_fn,
            validate_redraw_result_fn=self.validate_redraw_result_fn,
            get_client_fn=self.get_client_fn,
            log_event_fn=self.log_event_fn,
            detect_image_mime_type_fn=self.detect_image_mime_type_fn,
            image_model_call_budget_cls=self.image_model_call_budget_cls,
            image_model_call_budget_exceeded_cls=self.image_model_call_budget_exceeded_cls,
        )
        return self.process_document_images_impl_fn(
            image_assets=image_assets,
            image_mode=image_mode,
            context=pipeline_context,
        )

    def run_document_processing(
        self,
        *,
        uploaded_file,
        jobs: list[dict[str, str | int]],
        image_assets: list,
        image_mode: str,
        app_config: dict[str, object],
        model: str,
        max_retries: int,
        on_progress,
        runtime=None,
    ) -> str:
        return self.run_document_processing_impl_fn(
            uploaded_file=uploaded_file,
            jobs=jobs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
            on_progress=on_progress,
            runtime=runtime,
            resolve_uploaded_filename=self.resolve_uploaded_filename_fn,
            get_client=self.get_client_fn,
            ensure_pandoc_available=self.ensure_pandoc_available_fn,
            load_system_prompt=self.load_system_prompt_fn,
            log_event=self.log_event_fn,
            present_error=self.present_error_fn,
            emit_state=self.emit_state_fn,
            emit_finalize=self.emit_finalize_fn,
            emit_activity=self.emit_activity_fn,
            emit_log=self.emit_log_fn,
            emit_status=self.emit_status_fn,
            should_stop_processing=self.should_stop_processing_fn,
            generate_markdown_block=self.generate_markdown_block_fn,
            process_document_images=self.process_document_images,
            inspect_placeholder_integrity=self.inspect_placeholder_integrity_fn,
            convert_markdown_to_docx_bytes=self.convert_markdown_to_docx_bytes_fn,
            reinsert_inline_images=self.reinsert_inline_images_fn,
        )

    def run_processing_worker(
        self,
        *,
        runtime,
        uploaded_filename: str,
        jobs: list[dict[str, str | int]],
        image_assets: list,
        image_mode: str,
        app_config: dict[str, object],
        model: str,
        max_retries: int,
    ) -> None:
        outcome = "failed"
        try:
            outcome = self.run_document_processing(
                uploaded_file=uploaded_filename,
                jobs=jobs,
                image_assets=image_assets,
                image_mode=image_mode,
                app_config=app_config,
                model=model,
                max_retries=max_retries,
                on_progress=lambda **kwargs: None,
                runtime=runtime,
            )
        except Exception as exc:
            error_message = self.present_error_fn(
                "processing_worker_crashed",
                exc,
                "Критическая ошибка фоновой обработки",
                filename=uploaded_filename,
                block_count=len(jobs),
            )
            runtime.emit(SetStateEvent(values={"last_error": error_message}))
            runtime.emit(FinalizeProcessingStatusEvent(stage="Критическая ошибка", detail=error_message, progress=1.0))
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


def build_processing_service() -> ProcessingService:
    return ProcessingService(
        get_client_fn=get_client,
        load_system_prompt_fn=load_system_prompt,
        ensure_pandoc_available_fn=ensure_pandoc_available,
        generate_markdown_block_fn=generate_markdown_block,
        convert_markdown_to_docx_bytes_fn=convert_markdown_to_docx_bytes,
        process_document_images_impl_fn=process_document_images_impl,
        analyze_image_fn=analyze_image,
        generate_image_candidate_fn=generate_image_candidate,
        validate_redraw_result_fn=validate_redraw_result,
        detect_image_mime_type_fn=detect_image_mime_type,
        inspect_placeholder_integrity_fn=inspect_placeholder_integrity,
        reinsert_inline_images_fn=reinsert_inline_images,
        run_document_processing_impl_fn=run_document_processing_impl,
        present_error_fn=present_error,
        log_event_fn=log_event,
        emit_state_fn=emit_state_impl,
        emit_finalize_fn=emit_finalize_impl,
        emit_activity_fn=emit_activity_impl,
        emit_log_fn=emit_log_impl,
        emit_status_fn=emit_status_impl,
        emit_image_log_fn=emit_image_log_impl,
        emit_image_reset_fn=emit_image_reset_impl,
        should_stop_processing_fn=should_stop_processing,
        resolve_uploaded_filename_fn=resolve_uploaded_filename,
        image_model_call_budget_cls=ImageModelCallBudget,
        image_model_call_budget_exceeded_cls=ImageModelCallBudgetExceeded,
    )


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