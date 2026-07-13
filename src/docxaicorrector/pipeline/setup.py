import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from docxaicorrector.core.models import ImageMode
from docxaicorrector.pipeline.contracts import SegmentSelection


PipelineResult = Literal["succeeded", "failed", "stopped"]


def _coerce_job_segment_id(job: Mapping[str, object] | object) -> str | None:
    if not isinstance(job, Mapping):
        return None
    value = job.get("segment_id")
    normalized = str(value or "").strip()
    return normalized or None


def _build_segment_title_lookup(context: Any) -> dict[str, str]:
    paragraphs = list(getattr(context, "source_paragraphs", ()) or ())
    titles: dict[str, str] = {}
    for paragraph in paragraphs:
        segment_id = str(getattr(paragraph, "segment_id", "") or "").strip()
        if not segment_id or segment_id in titles:
            continue
        title = str(getattr(paragraph, "text", "") or "").strip()
        if title:
            titles[segment_id] = title
    return titles


def _build_segment_runtime_payload(*, context: Any) -> tuple[tuple[str | None, ...], dict[str, str], dict[str, int]]:
    jobs = list(context.jobs)
    segment_ids_by_job = tuple(_coerce_job_segment_id(job) for job in jobs)
    segment_job_totals: dict[str, int] = {}
    for segment_id in segment_ids_by_job:
        if segment_id is None:
            continue
        segment_job_totals[segment_id] = segment_job_totals.get(segment_id, 0) + 1
    return segment_ids_by_job, _build_segment_title_lookup(context), segment_job_totals


def summarize_block_plan(
    *,
    jobs: Sequence[object],
    coerce_required_int_field_fn: Callable[[Mapping[str, object], str], int],
    coerce_job_kind_fn: Callable[[Mapping[str, object]], str],
) -> dict[str, object]:
    block_sizes: list[int] = []
    job_kinds: dict[str, int] = {"llm": 0, "passthrough": 0}
    first_block_sizes: list[int] = []

    for block_job in jobs:
        try:
            if not isinstance(block_job, Mapping):
                raise TypeError("Processing job must be a mapping.")
            target_chars = coerce_required_int_field_fn(block_job, "target_chars")
        except (KeyError, TypeError, ValueError):
            target_chars = -1
        block_sizes.append(target_chars)
        if len(first_block_sizes) < 5:
            first_block_sizes.append(target_chars)
        try:
            if not isinstance(block_job, Mapping):
                raise TypeError("Processing job must be a mapping.")
            job_kind = coerce_job_kind_fn(block_job)
        except (TypeError, ValueError):
            job_kind = "llm"
        job_kinds[job_kind] = job_kinds.get(job_kind, 0) + 1

    valid_sizes = [size for size in block_sizes if size >= 0]
    total_target_chars = sum(valid_sizes)
    return {
        "block_count": len(block_sizes),
        "llm_block_count": job_kinds.get("llm", 0),
        "passthrough_block_count": job_kinds.get("passthrough", 0),
        "total_target_chars": total_target_chars,
        "min_target_chars": min(valid_sizes) if valid_sizes else None,
        "max_target_chars": max(valid_sizes) if valid_sizes else None,
        "avg_target_chars": round(total_target_chars / len(valid_sizes), 1) if valid_sizes else None,
        "first_block_target_chars": first_block_sizes,
        "blocks": [
            {
                "block_index": block_index,
                "target_chars": block_sizes[block_index - 1],
                "job_kind": coerce_job_kind_fn(block_job) if isinstance(block_job, Mapping) else "llm",
                "preview": str(block_job.get("target_text", ""))[:120] if isinstance(block_job, Mapping) else "",
            }
            for block_index, block_job in enumerate(jobs, start=1)
        ],
    }


def build_processing_emitters(
    *,
    emit_state: Any,
    emit_finalize: Any,
    emit_activity: Any,
    emit_log: Any,
    emit_status: Any,
    emitters_factory_fn: Callable[..., Any],
) -> Any:
    return emitters_factory_fn(
        emit_state=emit_state,
        emit_finalize=emit_finalize,
        emit_activity=emit_activity,
        emit_log=emit_log,
        emit_status=emit_status,
    )


def build_processing_context(
    *,
    uploaded_file: object,
    source_token: str | None = None,
    run_id: str | None = None,
    prepared_source_key: str | None = None,
    structure_fingerprint: str | None = None,
    jobs: object,
    selected_segment_ids: Sequence[Any] | None = None,
    segment_selection: SegmentSelection | None = None,
    document_segments: Sequence[Any] | None = None,
    output_mode: str | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
    source_paragraphs: object,
    image_assets: object,
    image_mode: str,
    app_config: Mapping[str, object],
    model: str,
    max_retries: int,
    processing_operation: str,
    source_language: str,
    target_language: str,
    on_progress: Any,
    runtime: object,
    dependencies: Any,
    context_factory_fn: Callable[..., Any],
    document_context_prompt: str = "",
) -> Any:
    effective_image_mode = ImageMode.NO_CHANGE.value if processing_operation == "audiobook" else image_mode
    model_selector = model
    canonical_model_selector = model
    model_provider: str | None = None
    model_id = model
    if callable(getattr(dependencies, "resolve_model_selector", None)):
        resolved_selector = dependencies.resolve_model_selector(model, "responses_text")
        model_selector = resolved_selector.raw_selector
        canonical_model_selector = resolved_selector.canonical_selector
        model_provider = resolved_selector.provider
        model_id = resolved_selector.model_id
    normalized_selected_segment_ids = tuple(
        str(segment_id).strip()
        for segment_id in (
            getattr(segment_selection, "selected_segment_ids", ()) if segment_selection is not None else (selected_segment_ids or ())
        )
        if str(segment_id).strip()
    )
    resolved_segment_selection = None
    if segment_selection is not None and normalized_selected_segment_ids:
        resolved_segment_selection = SegmentSelection(
            selected_segment_ids=normalized_selected_segment_ids,
            include_descendants=bool(segment_selection.include_descendants),
            include_front_matter=bool(segment_selection.include_front_matter),
            include_toc=bool(segment_selection.include_toc),
            output_mode=str(segment_selection.output_mode or "selected_only") or "selected_only",
        )
    return context_factory_fn(
        uploaded_file=uploaded_file,
        uploaded_filename=dependencies.resolve_uploaded_filename(uploaded_file),
        source_token=str(source_token or "").strip(),
        run_id=str(run_id or "").strip(),
        prepared_source_key=str(prepared_source_key or "").strip(),
        structure_fingerprint=str(structure_fingerprint or "").strip(),
        jobs=jobs,
        selected_segment_ids=normalized_selected_segment_ids or None,
        document_segments=tuple(document_segments or ()),
        segment_selection_mode="selected" if normalized_selected_segment_ids else "all",
        output_mode=str(output_mode or "").strip() or ("selected_only" if normalized_selected_segment_ids else "legacy_full_document"),
        include_front_matter=bool(include_front_matter),
        include_toc=bool(include_toc),
        source_paragraphs=source_paragraphs,
        image_assets=image_assets,
        image_mode=effective_image_mode,
        app_config=app_config,
        model=model,
        max_retries=max_retries,
        processing_operation=processing_operation,
        source_language=source_language,
        target_language=target_language,
        translation_domain=str(app_config.get("translation_domain_default", "general") or "general"),
        translation_domain_instructions=str(app_config.get("translation_domain_instructions", "") or ""),
        on_progress=on_progress,
        runtime=runtime,
        model_selector=model_selector,
        canonical_model_selector=canonical_model_selector,
        model_provider=model_provider,
        model_id=model_id,
        document_context_prompt=str(document_context_prompt or app_config.get("document_context_prompt", "") or ""),
        segment_selection=resolved_segment_selection,
    )


def build_processing_run_components(
    *,
    uploaded_file: object,
    source_token: str | None = None,
    run_id: str | None = None,
    prepared_source_key: str | None = None,
    structure_fingerprint: str | None = None,
    jobs: object,
    selected_segment_ids: object = None,
    segment_selection: SegmentSelection | None = None,
    document_segments: object = None,
    output_mode: str | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
    source_paragraphs: object,
    image_assets: object,
    image_mode: str,
    app_config: Mapping[str, object],
    model: str,
    max_retries: int,
    processing_operation: str,
    source_language: str,
    target_language: str,
    on_progress: Any,
    runtime: object,
    dependency_builder_fn: Callable[..., Any],
    emitters_builder_fn: Callable[..., Any],
    context_builder_fn: Callable[..., Any],
    run_components_factory_fn: Callable[..., Any],
    resolve_uploaded_filename: Any,
    get_client: Any,
    ensure_pandoc_available: Any,
    load_system_prompt: Any,
    log_event: Any,
    present_error: Any,
    emit_state: Any,
    emit_finalize: Any,
    emit_activity: Any,
    emit_log: Any,
    emit_status: Any,
    should_stop_processing: Any,
    generate_markdown_block: Any,
    process_document_images: Any,
    inspect_placeholder_integrity: Any,
    convert_markdown_to_docx_bytes: Any,
    preserve_source_paragraph_properties: Any,
    reinsert_inline_images: Any,
    write_ui_result_artifacts: Any,
    write_segment_result_registry: Any,
    write_job_result_registry: Any = None,
    get_provider_client_fn: Any = None,
    get_client_for_model_selector_fn: Any = None,
    resolve_model_selector_fn: Any = None,
    document_context_prompt: str = "",
) -> Any:
    dependencies = dependency_builder_fn(
        resolve_uploaded_filename=resolve_uploaded_filename,
        get_client=get_client,
        get_provider_client=get_provider_client_fn,
        get_client_for_model_selector=get_client_for_model_selector_fn,
        resolve_model_selector=resolve_model_selector_fn,
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
    emitters = emitters_builder_fn(
        emit_state=emit_state,
        emit_finalize=emit_finalize,
        emit_activity=emit_activity,
        emit_log=emit_log,
        emit_status=emit_status,
    )
    context = context_builder_fn(
        uploaded_file=uploaded_file,
        source_token=source_token,
        run_id=run_id,
        prepared_source_key=prepared_source_key,
        structure_fingerprint=structure_fingerprint,
        jobs=jobs,
        selected_segment_ids=selected_segment_ids,
        segment_selection=segment_selection,
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
        document_context_prompt=document_context_prompt,
    )
    return run_components_factory_fn(
        dependencies=dependencies,
        emitters=emitters,
        context=context,
    )


def execute_processing_run(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    initialize_processing_run_fn: Callable[..., Any],
    fail_empty_processing_plan_fn: Callable[..., PipelineResult],
    processing_state_factory_fn: Callable[[], Any],
    run_block_processing_phase_fn: Callable[..., PipelineResult | None],
    run_image_processing_phase_fn: Callable[..., Any | None],
    emit_stopped_result_fn: Callable[..., PipelineResult],
    current_markdown_fn: Callable[[Sequence[str]], str],
    validate_placeholder_integrity_phase_fn: Callable[..., bool],
    run_docx_build_phase_fn: Callable[..., Any | None],
    finalize_processing_success_fn: Callable[..., PipelineResult],
    initialization_type: type,
) -> PipelineResult:
    initialization = initialize_processing_run_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
    )
    if not isinstance(initialization, initialization_type):
        return initialization or "failed"
    if initialization.job_count == 0:
        return fail_empty_processing_plan_fn(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
        )

    state = processing_state_factory_fn()
    block_phase_outcome = run_block_processing_phase_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
    )
    if block_phase_outcome is not None:
        return block_phase_outcome

    image_phase = run_image_processing_phase_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
    )
    if image_phase is None:
        return "failed"
    if dependencies.should_stop_processing(context.runtime):
        return emit_stopped_result_fn(
            emitters=emitters,
            runtime=context.runtime,
            detail="Обработка остановлена пользователем.",
            progress=1.0,
            block_index=initialization.job_count,
            block_count=initialization.job_count,
        )

    final_markdown = current_markdown_fn(state.processed_chunks)
    if not validate_placeholder_integrity_phase_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        final_markdown=final_markdown,
        image_phase=image_phase,
        job_count=initialization.job_count,
    ):
        return "failed"

    docx_phase = run_docx_build_phase_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        image_phase=image_phase,
        job_count=initialization.job_count,
    )
    if docx_phase is None:
        return "failed"

    return finalize_processing_success_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        docx_phase=docx_phase,
        job_count=initialization.job_count,
    )


def initialize_processing_run(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    emit_failed_result_fn: Callable[..., PipelineResult],
    summarize_block_plan_fn: Callable[..., dict[str, object]],
    initialization_factory_fn: Callable[..., Any],
) -> Any | PipelineResult | None:
    try:
        job_count = len(context.jobs)
    except Exception as exc:
        error_message = dependencies.present_error(
            "invalid_processing_plan",
            exc,
            "Ошибка подготовки обработки",
            filename=context.uploaded_filename,
        )
        emitters.emit_state(
            context.runtime,
            last_error=error_message,
            latest_markdown="",
            processed_block_markdowns=[],
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        return emit_failed_result_fn(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Ошибка подготовки обработки",
            detail=error_message,
            progress=0.0,
            activity_message="Обработка документа остановлена: план обработки некорректен.",
            block_index=0,
            block_count=0,
            target_chars=0,
            context_chars=0,
            log_details=error_message,
        )

    segment_ids_by_job, segment_titles_by_id, segment_job_totals = _build_segment_runtime_payload(context=context)

    try:
        resolved_selector = None
        if callable(getattr(dependencies, "resolve_model_selector", None)):
            resolved_selector = dependencies.resolve_model_selector(context.model, "responses_text")
        text_client = (
            dependencies.get_client_for_model_selector(context.model, "responses_text")
            if callable(getattr(dependencies, "get_client_for_model_selector", None))
            else dependencies.get_client()
        )
        openai_client = None
        image_mode_requires_openai_client = context.image_mode not in {
            ImageMode.NO_CHANGE.value,
            ImageMode.SAFE.value,
        }
        if image_mode_requires_openai_client:
            provider_client_factory = getattr(dependencies, "get_provider_client", None)
            if callable(provider_client_factory):
                openai_client = provider_client_factory("openai")
            else:
                openai_client = dependencies.get_client()
        dependencies.ensure_pandoc_available()
        dependencies.log_event(
            logging.INFO,
            "processing_started",
            "Запуск обработки документа",
            filename=context.uploaded_filename,
            model=context.model,
            model_selector=context.model_selector or context.model,
            canonical_model_selector=(
                context.canonical_model_selector
                or getattr(resolved_selector, "canonical_selector", context.model)
            ),
            model_provider=context.model_provider or getattr(resolved_selector, "provider", None),
            model_id=context.model_id or getattr(resolved_selector, "model_id", context.model),
            block_count=job_count,
            max_retries=context.max_retries,
            image_count=len(context.image_assets),
        )
        block_plan_summary = summarize_block_plan_fn(context.jobs)
        dependencies.log_event(
            logging.INFO,
            "block_plan_summary",
            "План блоков документа подготовлен",
            filename=context.uploaded_filename,
            block_count=block_plan_summary["block_count"],
            llm_block_count=block_plan_summary["llm_block_count"],
            passthrough_block_count=block_plan_summary["passthrough_block_count"],
            total_target_chars=block_plan_summary["total_target_chars"],
            min_target_chars=block_plan_summary["min_target_chars"],
            max_target_chars=block_plan_summary["max_target_chars"],
            avg_target_chars=block_plan_summary["avg_target_chars"],
            first_block_target_chars=block_plan_summary["first_block_target_chars"],
        )
        dependencies.log_event(
            logging.DEBUG,
            "block_plan_detail",
            "Детальная карта блоков документа подготовлена",
            filename=context.uploaded_filename,
            blocks=block_plan_summary["blocks"],
        )
        emitters.emit_activity(
            context.runtime,
            f"Инициализация завершена. Модель: {context.canonical_model_selector or context.model}.",
        )
    except Exception as exc:
        error_message = dependencies.present_error(
            "processing_init_failed",
            exc,
            "Ошибка инициализации обработки",
            filename=context.uploaded_filename,
            model=context.model,
            model_selector=context.model_selector or context.model,
        )
        emitters.emit_state(
            context.runtime,
            last_error=error_message,
            latest_markdown="",
            processed_block_markdowns=[],
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        emit_failed_result_fn(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Ошибка инициализации",
            detail=error_message,
            progress=0.0,
            activity_message="Обработка документа остановлена: ошибка инициализации.",
            block_index=0,
            block_count=0,
            target_chars=0,
            context_chars=0,
            log_details=error_message,
        )
        return None

    return initialization_factory_fn(
        client=text_client,
        job_count=job_count,
        segment_ids_by_job=segment_ids_by_job,
        segment_titles_by_id=segment_titles_by_id,
        segment_job_totals=segment_job_totals,
        text_client=text_client,
        text_model_id=context.model_id or getattr(resolved_selector, "model_id", context.model),
        openai_client=openai_client,
    )
