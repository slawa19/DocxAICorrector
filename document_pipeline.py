import logging
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Literal, TypeAlias

from formatting_diagnostics_retention import get_formatting_diagnostics_dir, write_formatting_diagnostics_artifact
from document_pipeline_late_phases import (
    build_formatting_diagnostics_user_feedback as _build_formatting_diagnostics_user_feedback_impl,
    collect_recent_formatting_diagnostics_artifacts as _collect_recent_formatting_diagnostics_impl,
    emit_failed_result as _emit_failed_result_impl,
    emit_stopped_result as _emit_stopped_result_impl,
    fail_empty_processing_plan as _fail_empty_processing_plan_impl,
    finalize_processing_success as _finalize_processing_success_impl,
    run_docx_build_phase as _run_docx_build_phase_impl,
    run_image_processing_phase as _run_image_processing_phase_impl,
    validate_placeholder_integrity_phase as _validate_placeholder_integrity_phase_impl,
)
from document_pipeline_block_failures import (
    handle_block_generation_failure as _handle_block_generation_failure_impl,
    handle_invalid_processing_job as _handle_invalid_processing_job_impl,
    handle_marker_registry_failure as _handle_marker_registry_failure_impl,
    handle_processed_block_rejection as _handle_processed_block_rejection_impl,
)
from document_pipeline_block_execution import (
    append_marker_registry_entries as _append_marker_registry_entries_impl,
    build_processed_paragraph_registry_entries as _build_processed_paragraph_registry_entries_impl,
    emit_block_completed as _emit_block_completed_impl,
    emit_block_started as _emit_block_started_impl,
    execute_processing_block as _execute_processing_block_impl,
    process_single_block as _process_single_block_impl,
    run_block_processing_phase as _run_block_processing_phase_impl,
)
from document_pipeline_job_parsing import (
    coerce_job_kind as _coerce_job_kind_impl,
    coerce_optional_string_list as _coerce_optional_string_list_impl,
    coerce_optional_text_field as _coerce_optional_text_field_impl,
    coerce_required_int_field as _coerce_required_int_field_impl,
    coerce_required_text_field as _coerce_required_text_field_impl,
    is_marker_mode_enabled as _is_marker_mode_enabled_impl,
    parse_processing_job as _parse_processing_job_impl,
)
from document_pipeline_output_validation import (
    classify_processed_block as _classify_processed_block_impl,
)
from document_pipeline_setup import (
    build_processing_context as _build_processing_context_impl,
    build_processing_emitters as _build_processing_emitters_impl,
    build_processing_run_components as _build_processing_run_components_impl,
    execute_processing_run as _execute_processing_run_impl,
    initialize_processing_run as _initialize_processing_run_impl,
    summarize_block_plan as _summarize_block_plan_impl,
)
from document_pipeline_support import (
    call_docx_restorer_with_optional_registry as _call_docx_restorer_with_optional_registry_impl,
    current_markdown as _current_markdown_impl,
    extract_marker_diagnostics_code as _extract_marker_diagnostics_code_impl,
    resolve_system_prompt as _resolve_system_prompt_impl,
    write_marker_diagnostics_artifact as _write_marker_diagnostics_artifact_impl,
)
from document_pipeline_contracts import (
    BlockExecutionPayload,
    ClientFactory,
    DocxBuildPhaseResult,
    ErrorPresenter,
    EventLogger,
    FilenameResolver,
    FinalizeEmitter,
    ImageAssetLike,
    ImageProcessingPhaseResult,
    ImageProcessor,
    LogEmitter,
    MarkdownGenerator,
    MarkdownToDocxConverter,
    ParagraphLike,
    ParagraphPropertiesPreserver,
    PipelineResult as ContractsPipelineResult,
    PlaceholderInspector,
    ProcessingContext,
    ProcessingDependencies,
    ProcessingEmitters,
    ProcessingInitialization,
    ProcessingJobs,
    ProcessingRunComponents,
    ProcessingState,
    ProgressCallback,
    ResultArtifactWriter,
    StateEmitter,
    StatusEmitter,
    StopPredicate,
    SystemPromptLoader,
    ActivityEmitter,
    ImageReinserter,
    build_processing_dependencies as _build_processing_dependencies_impl,
)
from runtime_artifacts import write_ui_result_artifacts as write_ui_result_artifacts_impl


JobValue: TypeAlias = object
ProcessingJob: TypeAlias = Mapping[str, JobValue]
PipelineResult: TypeAlias = ContractsPipelineResult
ProcessedBlockStatus: TypeAlias = Literal["valid", "empty", "heading_only_output"]
FORMATTING_DIAGNOSTICS_DIR = get_formatting_diagnostics_dir()


def _coerce_required_text_field(job: ProcessingJob, field_name: str, *, allow_blank: bool = True) -> str:
    return _coerce_required_text_field_impl(job, field_name, allow_blank=allow_blank)


def _coerce_optional_string_list(job: ProcessingJob, field_name: str) -> list[str] | None:
    return _coerce_optional_string_list_impl(job, field_name)


def _coerce_optional_text_field(job: ProcessingJob, field_name: str) -> str | None:
    return _coerce_optional_text_field_impl(job, field_name)


def _coerce_required_int_field(job: ProcessingJob, field_name: str) -> int:
    return _coerce_required_int_field_impl(job, field_name)


def _coerce_job_kind(job: ProcessingJob) -> str:
    return _coerce_job_kind_impl(job)


def _resolve_system_prompt(
    load_system_prompt: SystemPromptLoader,
    *,
    operation: str,
    source_language: str,
    target_language: str,
    editorial_intensity: str = "literary",
    prompt_variant: str = "default",
) -> str:
    return _resolve_system_prompt_impl(
        load_system_prompt,
        operation=operation,
        source_language=source_language,
        target_language=target_language,
        editorial_intensity=editorial_intensity,
        prompt_variant=prompt_variant,
    )


def _classify_processed_block(target_text: str, processed_chunk: str) -> ProcessedBlockStatus:
    return _classify_processed_block_impl(target_text, processed_chunk)


def _collect_recent_formatting_diagnostics(*, since_epoch_seconds: float) -> list[str]:
    return _collect_recent_formatting_diagnostics_impl(
        since_epoch_seconds=since_epoch_seconds,
        diagnostics_dir=FORMATTING_DIAGNOSTICS_DIR,
    )


def _build_formatting_diagnostics_user_feedback(artifact_paths: Sequence[str]) -> tuple[str, str, str]:
    return _build_formatting_diagnostics_user_feedback_impl(artifact_paths)


def _extract_marker_diagnostics_code(exc: Exception) -> str | None:
    return _extract_marker_diagnostics_code_impl(exc)


def _write_marker_diagnostics_artifact(
    *,
    stage: str,
    uploaded_filename: str,
    block_index: int,
    block_count: int,
    error_code: str,
    target_text: str,
    context_before: str,
    context_after: str,
    paragraph_ids: Sequence[str] | None,
    processed_chunk: str | None = None,
) -> str | None:
    return _write_marker_diagnostics_artifact_impl(
        stage=stage,
        uploaded_filename=uploaded_filename,
        block_index=block_index,
        block_count=block_count,
        error_code=error_code,
        target_text=target_text,
        context_before=context_before,
        context_after=context_after,
        paragraph_ids=paragraph_ids,
        diagnostics_dir=FORMATTING_DIAGNOSTICS_DIR,
        processed_chunk=processed_chunk,
    )


def _summarize_block_plan(jobs: ProcessingJobs) -> dict[str, object]:
    return _summarize_block_plan_impl(
        jobs=list(jobs),
        coerce_required_int_field_fn=_coerce_required_int_field,
        coerce_job_kind_fn=_coerce_job_kind,
    )


def _build_processed_paragraph_registry_entries(*, block_index: int, paragraph_ids: Sequence[str], processed_chunk: str) -> list[dict[str, object]]:
    return _build_processed_paragraph_registry_entries_impl(
        block_index=block_index,
        paragraph_ids=tuple(paragraph_ids),
        processed_chunk=processed_chunk,
    )


def _call_docx_restorer_with_optional_registry(restorer, docx_bytes: bytes, paragraphs, generated_paragraph_registry):
    return _call_docx_restorer_with_optional_registry_impl(
        restorer,
        docx_bytes,
        paragraphs,
        generated_paragraph_registry,
    )


def _build_processing_dependencies(
    *,
    resolve_uploaded_filename: FilenameResolver,
    get_client: ClientFactory,
    ensure_pandoc_available: Callable[[], None],
    load_system_prompt: SystemPromptLoader,
    log_event: EventLogger,
    present_error: ErrorPresenter,
    should_stop_processing: StopPredicate,
    generate_markdown_block: MarkdownGenerator,
    process_document_images: ImageProcessor,
    inspect_placeholder_integrity: PlaceholderInspector,
    convert_markdown_to_docx_bytes: MarkdownToDocxConverter,
    preserve_source_paragraph_properties: ParagraphPropertiesPreserver,
    reinsert_inline_images: ImageReinserter,
    write_ui_result_artifacts: ResultArtifactWriter,
) -> ProcessingDependencies:
    return _build_processing_dependencies_impl(
        resolve_uploaded_filename=resolve_uploaded_filename,
        get_client=get_client,
        ensure_pandoc_available=ensure_pandoc_available,
        load_system_prompt=load_system_prompt,
        log_event=log_event,
        present_error=present_error,
        should_stop_processing=should_stop_processing,
        generate_markdown_block=generate_markdown_block,
        process_document_images=process_document_images,
        inspect_placeholder_integrity=inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=preserve_source_paragraph_properties,
        reinsert_inline_images=reinsert_inline_images,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )


def _build_processing_emitters(
    *,
    emit_state: StateEmitter,
    emit_finalize: FinalizeEmitter,
    emit_activity: ActivityEmitter,
    emit_log: LogEmitter,
    emit_status: StatusEmitter,
) -> ProcessingEmitters:
    return _build_processing_emitters_impl(
        emit_state=emit_state,
        emit_finalize=emit_finalize,
        emit_activity=emit_activity,
        emit_log=emit_log,
        emit_status=emit_status,
        emitters_factory_fn=ProcessingEmitters,
    )


def _build_processing_context(
    *,
    uploaded_file: object,
    jobs: ProcessingJobs,
    source_paragraphs: Sequence[ParagraphLike] | None,
    image_assets: Sequence[ImageAssetLike],
    image_mode: str,
    app_config: Mapping[str, object],
    model: str,
    max_retries: int,
    processing_operation: str,
    source_language: str,
    target_language: str,
    on_progress: ProgressCallback,
    runtime: object,
    dependencies: ProcessingDependencies,
) -> ProcessingContext:
    return _build_processing_context_impl(
        uploaded_file=uploaded_file,
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
        on_progress=on_progress,
        runtime=runtime,
        dependencies=dependencies,
        context_factory_fn=ProcessingContext,
    )


def _build_processing_run_components(
    *,
    uploaded_file: object,
    jobs: ProcessingJobs,
    source_paragraphs: Sequence[ParagraphLike] | None,
    image_assets: Sequence[ImageAssetLike],
    image_mode: str,
    app_config: Mapping[str, object],
    model: str,
    max_retries: int,
    processing_operation: str,
    source_language: str,
    target_language: str,
    on_progress: ProgressCallback,
    runtime: object,
    resolve_uploaded_filename: FilenameResolver,
    get_client: ClientFactory,
    ensure_pandoc_available: Callable[[], None],
    load_system_prompt: SystemPromptLoader,
    log_event: EventLogger,
    present_error: ErrorPresenter,
    emit_state: StateEmitter,
    emit_finalize: FinalizeEmitter,
    emit_activity: ActivityEmitter,
    emit_log: LogEmitter,
    emit_status: StatusEmitter,
    should_stop_processing: StopPredicate,
    generate_markdown_block: MarkdownGenerator,
    process_document_images: ImageProcessor,
    inspect_placeholder_integrity: PlaceholderInspector,
    convert_markdown_to_docx_bytes: MarkdownToDocxConverter,
    preserve_source_paragraph_properties: ParagraphPropertiesPreserver,
    reinsert_inline_images: ImageReinserter,
    write_ui_result_artifacts: ResultArtifactWriter,
) -> ProcessingRunComponents:
    return _build_processing_run_components_impl(
        uploaded_file=uploaded_file,
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
        on_progress=on_progress,
        runtime=runtime,
        dependency_builder_fn=_build_processing_dependencies,
        emitters_builder_fn=_build_processing_emitters,
        context_builder_fn=_build_processing_context,
        run_components_factory_fn=ProcessingRunComponents,
        resolve_uploaded_filename=resolve_uploaded_filename,
        get_client=get_client,
        ensure_pandoc_available=ensure_pandoc_available,
        load_system_prompt=load_system_prompt,
        log_event=log_event,
        present_error=present_error,
        emit_state=emit_state,
        emit_finalize=emit_finalize,
        emit_activity=emit_activity,
        emit_log=emit_log,
        emit_status=emit_status,
        should_stop_processing=should_stop_processing,
        generate_markdown_block=generate_markdown_block,
        process_document_images=process_document_images,
        inspect_placeholder_integrity=inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=preserve_source_paragraph_properties,
        reinsert_inline_images=reinsert_inline_images,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )


def _execute_processing_run(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
) -> PipelineResult:
    return _execute_processing_run_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        initialize_processing_run_fn=_initialize_processing_run,
        fail_empty_processing_plan_fn=_fail_empty_processing_plan,
        processing_state_factory_fn=ProcessingState,
        run_block_processing_phase_fn=_run_block_processing_phase,
        run_image_processing_phase_fn=_run_image_processing_phase,
        emit_stopped_result_fn=_emit_stopped_result,
        current_markdown_fn=_current_markdown,
        validate_placeholder_integrity_phase_fn=_validate_placeholder_integrity_phase,
        run_docx_build_phase_fn=_run_docx_build_phase,
        finalize_processing_success_fn=_finalize_processing_success,
        initialization_type=ProcessingInitialization,
    )


def _current_markdown(processed_chunks: Sequence[str]) -> str:
    return _current_markdown_impl(processed_chunks)


def _parse_processing_job(*, job: ProcessingJob) -> BlockExecutionPayload:
    return _parse_processing_job_impl(
        job=job,
        payload_factory=BlockExecutionPayload,
    )


def _is_marker_mode_enabled(context: ProcessingContext, payload: BlockExecutionPayload) -> bool:
    return _is_marker_mode_enabled_impl(context, payload)


def _emit_block_started(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    initialization: ProcessingInitialization,
    index: int,
    payload: BlockExecutionPayload,
) -> None:
    _emit_block_started_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        initialization=initialization,
        index=index,
        payload=payload,
    )


def _execute_processing_block(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
    index: int,
    payload: BlockExecutionPayload,
) -> tuple[str, bool]:
    return _execute_processing_block_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        index=index,
        payload=payload,
        is_marker_mode_enabled_fn=_is_marker_mode_enabled,
        resolve_system_prompt_fn=_resolve_system_prompt,
    )


def _append_marker_registry_entries(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    state: ProcessingState,
    initialization: ProcessingInitialization,
    index: int,
    payload: BlockExecutionPayload,
    processed_chunk: str,
) -> None:
    _append_marker_registry_entries_impl(
        context=context,
        dependencies=dependencies,
        state=state,
        initialization=initialization,
        index=index,
        payload=payload,
        processed_chunk=processed_chunk,
        build_processed_paragraph_registry_entries_fn=_build_processed_paragraph_registry_entries,
    )


def _emit_block_completed(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
    index: int,
    payload: BlockExecutionPayload,
    processed_chunk: str,
) -> None:
    _emit_block_completed_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        index=index,
        payload=payload,
        processed_chunk=processed_chunk,
        current_markdown_fn=_current_markdown,
    )


def _process_single_block(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
    index: int,
    job: ProcessingJob,
) -> PipelineResult | None:
    return _process_single_block_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        index=index,
        job=job,
        parse_processing_job_fn=_parse_processing_job,
        handle_invalid_processing_job_fn=_handle_invalid_processing_job,
        emit_block_started_fn=_emit_block_started,
        is_marker_mode_enabled_fn=_is_marker_mode_enabled,
        execute_processing_block_fn=_execute_processing_block,
        handle_block_generation_failure_fn=_handle_block_generation_failure,
        classify_processed_block_fn=_classify_processed_block,
        handle_processed_block_rejection_fn=_handle_processed_block_rejection,
        append_marker_registry_entries_fn=_append_marker_registry_entries,
        handle_marker_registry_failure_fn=_handle_marker_registry_failure,
        emit_block_completed_fn=_emit_block_completed,
    )


def _emit_failed_result(
    *,
    emitters: ProcessingEmitters,
    runtime: object,
    finalize_stage: str,
    detail: str,
    progress: float,
    activity_message: str,
    block_index: int,
    block_count: int,
    target_chars: int,
    context_chars: int,
    log_details: str,
) -> PipelineResult:
    return _emit_failed_result_impl(
        emitters=emitters,
        runtime=runtime,
        finalize_stage=finalize_stage,
        detail=detail,
        progress=progress,
        activity_message=activity_message,
        block_index=block_index,
        block_count=block_count,
        target_chars=target_chars,
        context_chars=context_chars,
        log_details=log_details,
    )


def _emit_stopped_result(
    *,
    emitters: ProcessingEmitters,
    runtime: object,
    detail: str,
    progress: float,
    block_index: int,
    block_count: int,
) -> PipelineResult:
    return _emit_stopped_result_impl(
        emitters=emitters,
        runtime=runtime,
        detail=detail,
        progress=progress,
        block_index=block_index,
        block_count=block_count,
    )


def _handle_invalid_processing_job(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
    index: int,
    exc: Exception,
) -> PipelineResult:
    return _handle_invalid_processing_job_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        index=index,
        exc=exc,
        current_markdown_fn=_current_markdown,
        emit_failed_result_fn=_emit_failed_result,
    )


def _handle_block_generation_failure(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
    index: int,
    payload: BlockExecutionPayload,
    marker_mode_enabled: bool,
    exc: Exception,
) -> PipelineResult:
    return _handle_block_generation_failure_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        index=index,
        payload=payload,
        marker_mode_enabled=marker_mode_enabled,
        exc=exc,
        extract_marker_diagnostics_code_fn=_extract_marker_diagnostics_code,
        write_marker_diagnostics_artifact_fn=_write_marker_diagnostics_artifact,
        current_markdown_fn=_current_markdown,
        emit_failed_result_fn=_emit_failed_result,
    )


def _handle_processed_block_rejection(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    initialization: ProcessingInitialization,
    index: int,
    target_chars: int,
    context_chars: int,
    target_text: str,
    processed_chunk: str,
    rejection_kind: ProcessedBlockStatus,
) -> PipelineResult:
    return _handle_processed_block_rejection_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        initialization=initialization,
        index=index,
        target_chars=target_chars,
        context_chars=context_chars,
        target_text=target_text,
        processed_chunk=processed_chunk,
        rejection_kind=rejection_kind,
        emit_failed_result_fn=_emit_failed_result,
    )


def _handle_marker_registry_failure(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
    index: int,
    payload: BlockExecutionPayload,
    processed_chunk: str,
    exc: Exception,
) -> PipelineResult:
    return _handle_marker_registry_failure_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        index=index,
        payload=payload,
        processed_chunk=processed_chunk,
        exc=exc,
        write_marker_diagnostics_artifact_fn=_write_marker_diagnostics_artifact,
        extract_marker_diagnostics_code_fn=_extract_marker_diagnostics_code,
        current_markdown_fn=_current_markdown,
        emit_failed_result_fn=_emit_failed_result,
    )


def _initialize_processing_run(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
) -> ProcessingInitialization | PipelineResult | None:
    return _initialize_processing_run_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        emit_failed_result_fn=_emit_failed_result,
        summarize_block_plan_fn=_summarize_block_plan,
        initialization_factory_fn=ProcessingInitialization,
    )


def _fail_empty_processing_plan(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
) -> PipelineResult:
    return _fail_empty_processing_plan_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
    )


def _run_block_processing_phase(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
) -> PipelineResult | None:
    return _run_block_processing_phase_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        emit_stopped_result_fn=_emit_stopped_result,
        process_single_block_fn=_process_single_block,
        current_markdown_fn=_current_markdown,
        emit_failed_result_fn=_emit_failed_result,
    )


def _run_image_processing_phase(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
) -> ImageProcessingPhaseResult | None:
    phase_result = _run_image_processing_phase_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        current_markdown_fn=_current_markdown,
    )
    if phase_result is None:
        return None
    return ImageProcessingPhaseResult(
        processed_image_assets=list(phase_result["processed_image_assets"]),
        placeholder_integrity=phase_result["placeholder_integrity"],
    )


def _validate_placeholder_integrity_phase(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    final_markdown: str,
    image_phase: ImageProcessingPhaseResult,
    job_count: int,
) -> bool:
    return _validate_placeholder_integrity_phase_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        final_markdown=final_markdown,
        image_phase={
            "placeholder_integrity": image_phase.placeholder_integrity,
            "processed_image_assets": image_phase.processed_image_assets,
        },
        job_count=job_count,
    )


def _run_docx_build_phase(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    image_phase: ImageProcessingPhaseResult,
    job_count: int,
) -> DocxBuildPhaseResult | None:
    phase_result = _run_docx_build_phase_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        image_phase={
            "processed_image_assets": image_phase.processed_image_assets,
            "placeholder_integrity": image_phase.placeholder_integrity,
        },
        job_count=job_count,
        diagnostics_dir=FORMATTING_DIAGNOSTICS_DIR,
        current_markdown_fn=_current_markdown,
        call_docx_restorer_with_optional_registry_fn=_call_docx_restorer_with_optional_registry,
    )
    if phase_result is None:
        return None
    return DocxBuildPhaseResult(
        docx_bytes=phase_result["docx_bytes"],
        latest_result_notice=phase_result["latest_result_notice"],
    )


def _finalize_processing_success(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    docx_phase: DocxBuildPhaseResult,
    job_count: int,
) -> PipelineResult:
    return _finalize_processing_success_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        docx_phase={
            "docx_bytes": docx_phase.docx_bytes,
            "latest_result_notice": docx_phase.latest_result_notice,
        },
        job_count=job_count,
        current_markdown_fn=_current_markdown,
    )


def run_document_processing(
    *,
    uploaded_file: object,
    jobs: ProcessingJobs,
    source_paragraphs: Sequence[ParagraphLike] | None = None,
    image_assets: Sequence[ImageAssetLike],
    image_mode: str,
    app_config: Mapping[str, object],
    model: str,
    max_retries: int,
    processing_operation: str = "edit",
    source_language: str = "en",
    target_language: str = "ru",
    on_progress: ProgressCallback,
    runtime: object,
    resolve_uploaded_filename: FilenameResolver,
    get_client: ClientFactory,
    ensure_pandoc_available: Callable[[], None],
    load_system_prompt: SystemPromptLoader,
    log_event: EventLogger,
    present_error: ErrorPresenter,
    emit_state: StateEmitter,
    emit_finalize: FinalizeEmitter,
    emit_activity: ActivityEmitter,
    emit_log: LogEmitter,
    emit_status: StatusEmitter,
    should_stop_processing: StopPredicate,
    generate_markdown_block: MarkdownGenerator,
    process_document_images: ImageProcessor,
    inspect_placeholder_integrity: PlaceholderInspector,
    convert_markdown_to_docx_bytes: MarkdownToDocxConverter,
    preserve_source_paragraph_properties: ParagraphPropertiesPreserver,
    reinsert_inline_images: ImageReinserter,
    write_ui_result_artifacts: ResultArtifactWriter = write_ui_result_artifacts_impl,
) -> PipelineResult:
    components = _build_processing_run_components(
        uploaded_file=uploaded_file,
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
        on_progress=on_progress,
        runtime=runtime,
        resolve_uploaded_filename=resolve_uploaded_filename,
        get_client=get_client,
        ensure_pandoc_available=ensure_pandoc_available,
        load_system_prompt=load_system_prompt,
        log_event=log_event,
        present_error=present_error,
        emit_state=emit_state,
        emit_finalize=emit_finalize,
        emit_activity=emit_activity,
        emit_log=emit_log,
        emit_status=emit_status,
        should_stop_processing=should_stop_processing,
        generate_markdown_block=generate_markdown_block,
        process_document_images=process_document_images,
        inspect_placeholder_integrity=inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=preserve_source_paragraph_properties,
        reinsert_inline_images=reinsert_inline_images,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )
    return _execute_processing_run(
        context=components.context,
        dependencies=components.dependencies,
        emitters=components.emitters,
    )
