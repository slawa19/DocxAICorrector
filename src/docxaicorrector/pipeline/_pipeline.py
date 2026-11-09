import logging
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TypeAlias, cast

from docxaicorrector.core.model_accounting import (
    run_model_accounting_scope,
    snapshot_run_model_accounting,
)
from docxaicorrector.generation.formatting_diagnostics_retention import (
    get_formatting_diagnostics_dir,
    write_formatting_diagnostics_artifact,
)
from docxaicorrector.pipeline.late_phases import (
    build_formatting_diagnostics_user_feedback as _build_formatting_diagnostics_user_feedback_impl,
    emit_failed_result as _emit_failed_result_impl,
    emit_stopped_result as _emit_stopped_result_impl,
    fail_empty_processing_plan as _fail_empty_processing_plan_impl,
    finalize_processing_success as _finalize_processing_success_impl,
    run_docx_build_phase as _run_docx_build_phase_impl,
    run_image_processing_phase as _run_image_processing_phase_impl,
    validate_placeholder_integrity_phase as _validate_placeholder_integrity_phase_impl,
)
from docxaicorrector.pipeline.block_failures import (
    handle_block_generation_failure as _handle_block_generation_failure_impl,
    handle_invalid_processing_job as _handle_invalid_processing_job_impl,
    handle_marker_registry_failure as _handle_marker_registry_failure_impl,
    handle_processed_block_rejection as _handle_processed_block_rejection_impl,
)
from docxaicorrector.pipeline.block_execution import (
    append_marker_registry_entries as _append_marker_registry_entries_impl,
    build_processed_paragraph_registry_entries as _build_processed_paragraph_registry_entries_impl,
    emit_block_completed as _emit_block_completed_impl,
    emit_block_started as _emit_block_started_impl,
    execute_processing_block as _execute_processing_block_impl,
    process_single_block as _process_single_block_impl,
    run_block_processing_phase as _run_block_processing_phase_impl,
)
from docxaicorrector.pipeline.glossary_phase import run_glossary_phase as _run_glossary_phase_impl
from docxaicorrector.pipeline.job_parsing import (
    coerce_job_kind as _coerce_job_kind_impl,
    coerce_optional_string_list as _coerce_optional_string_list_impl,
    coerce_optional_text_field as _coerce_optional_text_field_impl,
    coerce_required_int_field as _coerce_required_int_field_impl,
    coerce_required_text_field as _coerce_required_text_field_impl,
    is_marker_mode_enabled as _is_marker_mode_enabled_impl,
    parse_processing_job as _parse_processing_job_impl,
)
from docxaicorrector.pipeline.output_validation import (
    ProcessedBlockStatus,
    classify_processed_block as _classify_processed_block_impl,
)
from docxaicorrector.pipeline.setup import (
    build_processing_context as _build_processing_context_impl,
    build_processing_emitters as _build_processing_emitters_impl,
    build_processing_run_components as _build_processing_run_components_impl,
    execute_processing_run as _execute_processing_run_impl,
    initialize_processing_run as _initialize_processing_run_impl,
    summarize_block_plan as _summarize_block_plan_impl,
)
from docxaicorrector.pipeline.support import (
    call_docx_restorer_with_optional_registry as _call_docx_restorer_with_optional_registry_impl,
    current_markdown as _current_markdown_impl,
    extract_marker_diagnostics_code as _extract_marker_diagnostics_code_impl,
    resolve_system_prompt as _resolve_system_prompt_impl,
    write_marker_diagnostics_artifact as _write_marker_diagnostics_artifact_impl,
)
from docxaicorrector.pipeline.contracts import (
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
    ImageReinserter,
    build_processing_dependencies as _build_processing_dependencies_impl,
    ModelSelectorClientFactory,
    ModelSelectorResolver,
    ProviderClientFactory,
)
from docxaicorrector.runtime.artifacts import (
    write_job_result_registry as write_job_result_registry_impl,
    write_segment_result_registry as write_segment_result_registry_impl,
    write_ui_result_artifacts as write_ui_result_artifacts_impl,
)


JobValue: TypeAlias = object
ProcessingJob: TypeAlias = Mapping[str, JobValue]
PipelineResult: TypeAlias = ContractsPipelineResult
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
    document_context_prompt: str = "",
) -> str:
    return _resolve_system_prompt_impl(
        load_system_prompt,
        operation=operation,
        source_language=source_language,
        target_language=target_language,
        editorial_intensity=editorial_intensity,
        prompt_variant=prompt_variant,
        document_context_prompt=document_context_prompt,
    )


def _classify_processed_block(
    target_text: str,
    processed_chunk: str,
    *,
    languages_differ: bool = True,
) -> ProcessedBlockStatus:
    return _classify_processed_block_impl(target_text, processed_chunk, languages_differ=languages_differ)


def _build_formatting_diagnostics_user_feedback(artifact_paths: Sequence[str]) -> tuple[str, str]:
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
    run_id: str,
    source_token: str,
    processed_chunk: str | None = None,
    exc: Exception | None = None,
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
        run_id=run_id,
        source_token=source_token,
        processed_chunk=processed_chunk,
        exc=exc,
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


def _call_docx_restorer_with_optional_registry(
    restorer,
    docx_bytes: bytes,
    paragraphs,
    generated_paragraph_registry,
    *,
    run_id: str,
    source_token: str,
):
    return _call_docx_restorer_with_optional_registry_impl(
        restorer,
        docx_bytes,
        paragraphs,
        generated_paragraph_registry,
        run_id=run_id,
        source_token=source_token,
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
    write_segment_result_registry,
    write_job_result_registry,
    get_provider_client: ProviderClientFactory | None = None,
    get_client_for_model_selector: ModelSelectorClientFactory | None = None,
    resolve_model_selector: ModelSelectorResolver | None = None,
) -> ProcessingDependencies:
    return _build_processing_dependencies_impl(
        resolve_uploaded_filename=resolve_uploaded_filename,
        get_client=get_client,
        get_provider_client=get_provider_client,
        get_client_for_model_selector=get_client_for_model_selector,
        resolve_model_selector=resolve_model_selector,
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
        write_segment_result_registry=write_segment_result_registry,
        write_job_result_registry=write_job_result_registry,
    )


def _build_processing_emitters(
    *,
    emit_state: StateEmitter,
    emit_finalize: FinalizeEmitter,
    emit_log: LogEmitter,
    emit_status: StatusEmitter,
) -> ProcessingEmitters:
    return _build_processing_emitters_impl(
        emit_state=emit_state,
        emit_finalize=emit_finalize,
        emit_log=emit_log,
        emit_status=emit_status,
        emitters_factory_fn=ProcessingEmitters,
    )


def _build_processing_context(
    *,
    uploaded_file: object,
    source_token: str | None = None,
    run_id: str | None = None,
    prepared_source_key: str | None = None,
    structure_fingerprint: str | None = None,
    jobs: ProcessingJobs,
    selected_segment_ids: Sequence[str] | None = None,
    document_segments: Sequence[object] | None = None,
    output_mode: str | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
    source_paragraphs: Sequence[ParagraphLike] | None,
    image_assets: Sequence[ImageAssetLike],
    image_mode: str,
    app_config: Mapping[str, object],
    model: str,
    max_retries: int,
    processing_operation: str,
    source_language: str | None,
    target_language: str | None,
    on_progress: ProgressCallback,
    runtime: object,
    dependencies: ProcessingDependencies,
    document_context_prompt: str = "",
) -> ProcessingContext:
    return _build_processing_context_impl(
        uploaded_file=uploaded_file,
        source_token=source_token,
        run_id=run_id,
        prepared_source_key=prepared_source_key,
        structure_fingerprint=structure_fingerprint,
        jobs=jobs,
        selected_segment_ids=selected_segment_ids,
        document_segments=document_segments,
        output_mode=output_mode,
        include_front_matter=include_front_matter,
        include_toc=include_toc,
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
        document_context_prompt=document_context_prompt,
    )


def _build_processing_run_components(
    *,
    uploaded_file: object,
    source_token: str | None = None,
    run_id: str | None = None,
    prepared_source_key: str | None = None,
    structure_fingerprint: str | None = None,
    jobs: ProcessingJobs,
    selected_segment_ids: Sequence[str] | None = None,
    document_segments: Sequence[object] | None = None,
    output_mode: str | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
    source_paragraphs: Sequence[ParagraphLike] | None,
    image_assets: Sequence[ImageAssetLike],
    image_mode: str,
    app_config: Mapping[str, object],
    model: str,
    max_retries: int,
    processing_operation: str,
    source_language: str | None,
    target_language: str | None,
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
    write_segment_result_registry,
    write_job_result_registry,
    get_provider_client: Callable[[str], object] | None = None,
    get_client_for_model_selector: Callable[[str, str], object] | None = None,
    resolve_model_selector: Callable[[str, str | None], object] | None = None,
    document_context_prompt: str = "",
) -> ProcessingRunComponents:
    return _build_processing_run_components_impl(
        uploaded_file=uploaded_file,
        source_token=source_token,
        run_id=run_id,
        prepared_source_key=prepared_source_key,
        structure_fingerprint=structure_fingerprint,
        jobs=jobs,
        selected_segment_ids=selected_segment_ids,
        document_segments=document_segments,
        output_mode=output_mode,
        include_front_matter=include_front_matter,
        include_toc=include_toc,
        source_paragraphs=source_paragraphs,
        image_assets=image_assets,
        image_mode=image_mode,
        app_config=app_config,
        document_context_prompt=document_context_prompt,
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
        get_provider_client_fn=get_provider_client,
        get_client_for_model_selector_fn=get_client_for_model_selector,
        resolve_model_selector_fn=resolve_model_selector,
        ensure_pandoc_available=ensure_pandoc_available,
        load_system_prompt=load_system_prompt,
        log_event=log_event,
        present_error=present_error,
        emit_state=emit_state,
        emit_finalize=emit_finalize,
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
        write_segment_result_registry=write_segment_result_registry,
        write_job_result_registry=write_job_result_registry,
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
        run_glossary_phase_fn=_run_glossary_phase,
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


def _run_glossary_phase(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
) -> ProcessingContext:
    return _run_glossary_phase_impl(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
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
        docx_bytes=cast(bytes | None, phase_result.get("docx_bytes")),
        final_markdown=str(phase_result.get("runtime_display_markdown") or phase_result.get("final_markdown") or ""),
        latest_result_notice=phase_result["latest_result_notice"],
        formatting_diagnostics_artifacts=list(phase_result.get("formatting_diagnostics_artifacts") or []),
        pre_cleanup_formatting_baseline=cast(
            Mapping[str, object] | None,
            phase_result.get("pre_cleanup_formatting_baseline"),
        ),
        assembly_entries=list(phase_result.get("assembly_entries") or []),
        result_manifest=cast(Mapping[str, object] | None, phase_result.get("result_manifest")),
        processed_image_assets=list(cast(Sequence[ImageAssetLike], phase_result.get("processed_image_assets") or [])),
        base_docx_builder=cast(Callable[[], bytes] | None, phase_result.get("base_docx_builder")),
        diagnostics_dir=cast(Path | None, phase_result.get("diagnostics_dir")),
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
            "base_docx_builder": docx_phase.base_docx_builder,
            "final_markdown": docx_phase.final_markdown,
            "runtime_display_markdown": docx_phase.final_markdown,
            "latest_result_notice": docx_phase.latest_result_notice,
            "formatting_diagnostics_artifacts": list(docx_phase.formatting_diagnostics_artifacts),
            "pre_cleanup_formatting_baseline": docx_phase.pre_cleanup_formatting_baseline,
            "assembly_entries": list(docx_phase.assembly_entries),
            "result_manifest": docx_phase.result_manifest,
            "processed_image_assets": list(docx_phase.processed_image_assets),
            # Deferred builds re-collect only artifacts owned by this processing context.
            "diagnostics_dir": docx_phase.diagnostics_dir,
        },
        job_count=job_count,
        current_markdown_fn=_current_markdown,
    )


def run_document_processing(
    *,
    uploaded_file: object,
    source_token: str | None = None,
    run_id: str | None = None,
    prepared_source_key: str | None = None,
    structure_fingerprint: str | None = None,
    jobs: ProcessingJobs,
    selected_segment_ids: Sequence[str] | None = None,
    document_segments: Sequence[object] | None = None,
    output_mode: str | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
    source_paragraphs: Sequence[ParagraphLike] | None = None,
    image_assets: Sequence[ImageAssetLike],
    image_mode: str,
    app_config: Mapping[str, object],
    model: str,
    max_retries: int,
    processing_operation: str = "edit",
    source_language: str | None = "en",
    target_language: str | None = "ru",
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
    get_provider_client: Callable[[str], object] | None = None,
    get_client_for_model_selector: Callable[[str, str], object] | None = None,
    resolve_model_selector: Callable[[str, str | None], object] | None = None,
    document_context_prompt: str = "",
) -> PipelineResult:
    # Run boundary for token/cost accounting. The scope owns a ledger of its own, keyed to
    # THIS run's identity, so a second run admitted concurrently (the default limit is 2)
    # cannot reset or share these counters. Reported in the ``finally`` below, so a run
    # that FAILED still tells the user what it spent — money is spent per call, not per
    # successful outcome.
    with run_model_accounting_scope(run_id=run_id, source_token=source_token):
        return _run_document_processing_in_scope(
            uploaded_file=uploaded_file,
            source_token=source_token,
            run_id=run_id,
            prepared_source_key=prepared_source_key,
            structure_fingerprint=structure_fingerprint,
            jobs=jobs,
            selected_segment_ids=selected_segment_ids,
            document_segments=document_segments,
            output_mode=output_mode,
            include_front_matter=include_front_matter,
            include_toc=include_toc,
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
            get_provider_client=get_provider_client,
            get_client_for_model_selector=get_client_for_model_selector,
            resolve_model_selector=resolve_model_selector,
            document_context_prompt=document_context_prompt,
        )


def _run_document_processing_in_scope(
    *,
    uploaded_file: object,
    source_token: str | None = None,
    run_id: str | None = None,
    prepared_source_key: str | None = None,
    structure_fingerprint: str | None = None,
    jobs: ProcessingJobs,
    selected_segment_ids: Sequence[str] | None = None,
    document_segments: Sequence[object] | None = None,
    output_mode: str | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
    source_paragraphs: Sequence[ParagraphLike] | None = None,
    image_assets: Sequence[ImageAssetLike],
    image_mode: str,
    app_config: Mapping[str, object],
    model: str,
    max_retries: int,
    processing_operation: str = "edit",
    source_language: str | None = "en",
    target_language: str | None = "ru",
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
    get_provider_client: Callable[[str], object] | None = None,
    get_client_for_model_selector: Callable[[str, str], object] | None = None,
    resolve_model_selector: Callable[[str, str | None], object] | None = None,
    document_context_prompt: str = "",
) -> PipelineResult:
    # Emitting the accounting event INSIDE the run's scope is what makes the snapshot this
    # run's own: taken after the scope exits it would read whatever ledger the context
    # falls back to.
    run_result: PipelineResult | None = None
    try:
        run_result = _run_document_processing_accounted(
            uploaded_file=uploaded_file,
            source_token=source_token,
            run_id=run_id,
            prepared_source_key=prepared_source_key,
            structure_fingerprint=structure_fingerprint,
            jobs=jobs,
            selected_segment_ids=selected_segment_ids,
            document_segments=document_segments,
            output_mode=output_mode,
            include_front_matter=include_front_matter,
            include_toc=include_toc,
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
            get_provider_client=get_provider_client,
            get_client_for_model_selector=get_client_for_model_selector,
            resolve_model_selector=resolve_model_selector,
            document_context_prompt=document_context_prompt,
        )
        return run_result
    finally:
        accounting = emit_run_model_accounting_event(log_event=log_event, filename=str(uploaded_file))
        emit_cost_estimate_vs_actual(
            app_config=app_config,
            accounting=accounting,
            run_status=run_result,
            run_id=run_id,
            filename=str(uploaded_file),
            log_event=log_event,
            emit_state=emit_state,
            runtime=runtime,
        )


COST_COMPARISON_STAGES = ("glossary_extraction", "text_generation", "literary_polish")


def build_cost_estimate_vs_actual(
    *,
    snapshot: Mapping[str, object],
    accounting: Mapping[str, object],
    run_status: str | None,
) -> dict[str, object]:
    """Compare the estimate frozen at Start with what the run cost (spec 069 FR-007).

    The actual is the sum of ``cost_usd_reported_by_provider`` of the same text stages the
    estimate covers (glossary + text generation + literary polish); images are out of both.
    ``relative_error_vs_upper = (actual - upper) / actual`` and ``within_range`` are computed
    only for a COMPLETE run with complete cost accounting: a stopped or failed run, or one with
    a call that reported no price, is flagged and carries ``None`` so it never reaches a future
    calibration. A stage the estimate priced but that made no call also counts as incomplete.
    """
    raw_estimated = snapshot.get("stages")
    estimated_stages: Mapping[str, object] = raw_estimated if isinstance(raw_estimated, Mapping) else {}
    raw_accounted = accounting.get("stages")
    accounted_stages: Mapping[str, object] = raw_accounted if isinstance(raw_accounted, Mapping) else {}

    run_complete = run_status == "succeeded"
    cost_accounting_complete = True
    stages: dict[str, dict[str, object]] = {}
    actual_total = 0.0
    for stage in COST_COMPARISON_STAGES:
        estimate = estimated_stages.get(stage)
        estimate = estimate if isinstance(estimate, Mapping) else None
        spent = accounted_stages.get(stage)
        spent = spent if isinstance(spent, Mapping) else None
        actual = float(cast(float, spent.get("cost_usd_reported_by_provider") or 0.0)) if spent else 0.0
        actual_total += actual
        if spent is not None and int(cast(int, spent.get("model_calls_without_cost") or 0)) > 0:
            cost_accounting_complete = False
        if estimate is not None and (spent is None or int(cast(int, spent.get("model_call_count") or 0)) == 0):
            cost_accounting_complete = False
        stages[stage] = {
            "estimate_upper": estimate.get("upper_usd") if estimate is not None else None,
            "estimate_lower": estimate.get("lower_usd") if estimate is not None else None,
            "actual": round(actual, 6),
        }

    upper = snapshot.get("total_upper_usd")
    lower = snapshot.get("total_lower_usd")
    actual_total = round(actual_total, 6)
    relative_error: float | None = None
    within_range: bool | None = None
    comparable = run_complete and cost_accounting_complete and isinstance(upper, (int, float)) and actual_total > 0
    if comparable:
        upper_value = float(cast(float, upper))
        relative_error = (actual_total - upper_value) / actual_total
        if isinstance(lower, (int, float)):
            within_range = float(lower) <= actual_total <= upper_value
    raw_document = snapshot.get("document")
    return {
        "mode": snapshot.get("mode"),
        "coefficients_version": snapshot.get("coefficients_version"),
        "price_list_date": snapshot.get("price_list_date"),
        "stages": stages,
        "estimate_upper_usd": upper,
        "estimate_lower_usd": lower,
        "actual_usd": actual_total,
        "relative_error_vs_upper": relative_error,
        "within_range": within_range,
        "run_complete": run_complete,
        "cost_accounting_complete": cost_accounting_complete,
        "source_token": raw_document.get("source_token") if isinstance(raw_document, Mapping) else None,
    }


def emit_cost_estimate_vs_actual(
    *,
    app_config: Mapping[str, object],
    accounting: Mapping[str, object],
    run_status: str | None,
    run_id: str | None,
    filename: str,
    log_event: EventLogger,
    emit_state: StateEmitter,
    runtime: object,
) -> dict[str, object] | None:
    """Publish ``cost_estimate_vs_actual`` once per run and hand the actual to the result bundle.

    Nothing happens for a run without a frozen snapshot (edit, audiobook, a runner that did not
    estimate). INFO, once per run, beside ``model_usage_accounted``. Logging must never take a
    run down, so a failure here is swallowed.
    """
    snapshot = app_config.get("cost_estimate_snapshot") if isinstance(app_config, Mapping) else None
    if not isinstance(snapshot, Mapping):
        return None
    try:
        comparison = build_cost_estimate_vs_actual(snapshot=snapshot, accounting=accounting, run_status=run_status)
        source_token = comparison.pop("source_token", None)
        log_event(
            logging.INFO,
            "cost_estimate_vs_actual",
            "Сопоставлены оценка цены при старте и фактическая стоимость текстовых стадий.",
            filename=filename,
            run_id=run_id,
            **comparison,
        )
        emit_state(
            runtime,
            latest_cost_actual={
                "stages": {stage: item["actual"] for stage, item in cast(dict[str, dict[str, object]], comparison["stages"]).items()},
                "total_usd": comparison["actual_usd"],
                "cost_accounting_complete": comparison["cost_accounting_complete"],
                "run_complete": comparison["run_complete"],
                "source_token": source_token,
            },
        )
        return comparison
    except Exception:
        return None


def emit_run_model_accounting_event(*, log_event: EventLogger, filename: str) -> dict[str, object]:
    """Publish the run's token/cost/retry/discard totals as ONE structured event.

    Registered in ``docs/LOGGING_AND_ARTIFACT_RETENTION.md`` §3.3 as
    ``model_usage_accounted``. INFO because it is a run-level aggregate emitted once per
    run (§2), and it is emitted even when the run failed. Logging must never take a run
    down, so a broken logger is swallowed here.
    """

    accounting = snapshot_run_model_accounting()
    try:
        log_event(
            logging.INFO,
            "model_usage_accounted",
            "Учтены токены, стоимость и повторные попытки прогона.",
            filename=filename,
            **accounting,
        )
    except Exception:
        pass
    return accounting


def _run_document_processing_accounted(
    *,
    uploaded_file: object,
    source_token: str | None = None,
    run_id: str | None = None,
    prepared_source_key: str | None = None,
    structure_fingerprint: str | None = None,
    jobs: ProcessingJobs,
    selected_segment_ids: Sequence[str] | None = None,
    document_segments: Sequence[object] | None = None,
    output_mode: str | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
    source_paragraphs: Sequence[ParagraphLike] | None = None,
    image_assets: Sequence[ImageAssetLike],
    image_mode: str,
    app_config: Mapping[str, object],
    model: str,
    max_retries: int,
    processing_operation: str = "edit",
    source_language: str | None = "en",
    target_language: str | None = "ru",
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
    get_provider_client: Callable[[str], object] | None = None,
    get_client_for_model_selector: Callable[[str, str], object] | None = None,
    resolve_model_selector: Callable[[str, str | None], object] | None = None,
    document_context_prompt: str = "",
) -> PipelineResult:
    components = _build_processing_run_components(
        uploaded_file=uploaded_file,
        source_token=source_token,
        run_id=run_id,
        prepared_source_key=prepared_source_key,
        structure_fingerprint=structure_fingerprint,
        jobs=jobs,
        selected_segment_ids=selected_segment_ids,
        document_segments=document_segments,
        output_mode=output_mode,
        include_front_matter=include_front_matter,
        include_toc=include_toc,
        source_paragraphs=source_paragraphs,
        image_assets=image_assets,
        image_mode=image_mode,
        app_config=app_config,
        document_context_prompt=document_context_prompt,
        model=model,
        max_retries=max_retries,
        processing_operation=processing_operation,
        source_language=source_language,
        target_language=target_language,
        on_progress=on_progress,
        runtime=runtime,
        resolve_uploaded_filename=resolve_uploaded_filename,
        get_client=get_client,
        get_provider_client=get_provider_client,
        get_client_for_model_selector=get_client_for_model_selector,
        resolve_model_selector=resolve_model_selector,
        ensure_pandoc_available=ensure_pandoc_available,
        load_system_prompt=load_system_prompt,
        log_event=log_event,
        present_error=present_error,
        emit_state=emit_state,
        emit_finalize=emit_finalize,
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
        write_job_result_registry=write_job_result_registry_impl,
        write_segment_result_registry=write_segment_result_registry_impl,
    )
    return _execute_processing_run(
        context=components.context,
        dependencies=components.dependencies,
        emitters=components.emitters,
    )
