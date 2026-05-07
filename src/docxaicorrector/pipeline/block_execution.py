import logging
import time
from typing import Any, Literal, TypeAlias

from docxaicorrector.pipeline.job_results import persist_terminal_job_result
from docxaicorrector.pipeline.output_validation import validate_translated_toc_block


PipelineResult: TypeAlias = Literal["succeeded", "failed", "stopped"]
TOC_VALIDATION_RETRY_BUDGET = 2
TOC_RETRY_HARDENING_ATTEMPT = 2


def _resolve_segment_status_payload(*, initialization: Any, index: int, status: str) -> tuple[dict[str, str], dict[str, float], str, str]:
    segment_ids_by_job = tuple(getattr(initialization, "segment_ids_by_job", ()) or ())
    segment_titles_by_id = dict(getattr(initialization, "segment_titles_by_id", {}) or {})
    segment_job_totals = dict(getattr(initialization, "segment_job_totals", {}) or {})
    if not segment_ids_by_job:
        return {}, {}, "", ""

    active_segment_index = max(0, min(index - 1, len(segment_ids_by_job) - 1))
    active_segment_id = segment_ids_by_job[active_segment_index]
    if active_segment_id is None:
        return {}, {}, "", ""

    active_segment_title = str(segment_titles_by_id.get(active_segment_id, active_segment_id) or active_segment_id)
    completed_jobs_by_segment: dict[str, int] = {}
    for segment_index in range(max(0, min(index, len(segment_ids_by_job)))):
        segment_id = segment_ids_by_job[segment_index]
        if segment_id is None:
            continue
        completed_jobs_by_segment[segment_id] = completed_jobs_by_segment.get(segment_id, 0) + 1

    status_by_id: dict[str, str] = {}
    progress_by_id: dict[str, float] = {}
    for segment_id, total_jobs in segment_job_totals.items():
        completed_jobs = completed_jobs_by_segment.get(segment_id, 0)
        if segment_id == active_segment_id:
            status_by_id[segment_id] = status
        elif completed_jobs >= total_jobs > 0:
            status_by_id[segment_id] = "completed"
        elif completed_jobs > 0:
            status_by_id[segment_id] = "processing"
        else:
            status_by_id[segment_id] = "pending"
        progress_by_id[segment_id] = 0.0 if total_jobs <= 0 else min(completed_jobs / total_jobs, 1.0)
    return status_by_id, progress_by_id, str(active_segment_id), active_segment_title


def _is_toc_dominant_payload(*, payload: Any) -> bool:
    return bool(getattr(payload, "toc_dominant", False))


def _should_route_toc_through_llm(*, context: Any, payload: Any) -> bool:
    return context.processing_operation == "translate" and _is_toc_dominant_payload(payload=payload)


def _resolve_block_prompt_variant(*, context: Any, payload: Any) -> str:
    if _should_route_toc_through_llm(context=context, payload=payload):
        return "toc_translate"
    return "default"


def _build_prompt_source_text(*, context: Any) -> str:
    parts: list[str] = []
    translation_domain_instructions = str(getattr(context, "translation_domain_instructions", "") or "").strip()
    if translation_domain_instructions:
        parts.append(translation_domain_instructions)
    if getattr(context, "processing_operation", "") == "translate":
        document_context_prompt = str(
            getattr(context, "document_context_prompt", "")
            or getattr(context, "app_config", {}).get("document_context_prompt", "")
            or ""
        ).strip()
        if document_context_prompt:
            parts.append(document_context_prompt)
    return "\n\n".join(parts)


def _get_cached_system_prompt(*, context: Any, dependencies: Any, state: Any, resolve_system_prompt_fn: Any, prompt_variant: str) -> str:
    prompt_source_text = _build_prompt_source_text(context=context)
    if prompt_variant == "toc_translate":
        if state.toc_system_prompt is None:
            state.toc_system_prompt = resolve_system_prompt_fn(
                dependencies.load_system_prompt,
                operation=context.processing_operation,
                source_language=context.source_language,
                target_language=context.target_language,
                editorial_intensity=str(context.app_config.get("editorial_intensity_default", "literary")),
                prompt_variant="toc_translate",
                translation_domain=context.translation_domain,
                source_text=prompt_source_text,
            )
        return state.toc_system_prompt

    if state.system_prompt is None:
        state.system_prompt = resolve_system_prompt_fn(
            dependencies.load_system_prompt,
            operation=context.processing_operation,
            source_language=context.source_language,
            target_language=context.target_language,
            editorial_intensity=str(context.app_config.get("editorial_intensity_default", "literary")),
            translation_domain=context.translation_domain,
            source_text=prompt_source_text,
        )
    return state.system_prompt


def _build_toc_retry_system_prompt(*, system_prompt: str, source_language: str, target_language: str) -> str:
    return (
        f"{system_prompt}\n\n"
        "TOC retry hardening.\n"
        f"Translate each input paragraph from {source_language} to {target_language} as a table-of-contents entry, not as prose.\n"
        "Keep one output paragraph for each input paragraph.\n"
        "Preserve ordering, numbering, Roman numerals, and page-reference-like suffixes.\n"
        "Do not leave the TOC header or substantive entries unchanged unless they are proper names or acronyms."
    )


def _generate_block_chunk(
    *,
    context: Any,
    dependencies: Any,
    initialization: Any,
    payload: Any,
    marker_mode_enabled: bool,
    system_prompt: str,
) -> str:
    client = initialization.text_client or initialization.client
    model_id = context.model_id or initialization.text_model_id or context.model
    return dependencies.generate_markdown_block(
        client=client,
        model=model_id,
        system_prompt=system_prompt,
        target_text=payload.target_text_with_markers if marker_mode_enabled else payload.target_text,
        context_before=payload.context_before,
        context_after=payload.context_after,
        max_retries=context.max_retries,
        expected_paragraph_ids=payload.paragraph_ids if marker_mode_enabled else None,
        marker_mode=marker_mode_enabled,
    )


def _validate_toc_chunk_with_retries(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    marker_mode_enabled: bool,
    resolve_system_prompt_fn: Any,
) -> str:
    prompt_variant = _resolve_block_prompt_variant(context=context, payload=payload)
    retry_budget = TOC_VALIDATION_RETRY_BUDGET
    rejection_reasons: list[str] = []

    for attempt in range(retry_budget + 1):
        base_prompt = _get_cached_system_prompt(
            context=context,
            dependencies=dependencies,
            state=state,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
            prompt_variant=prompt_variant,
        )
        system_prompt = (
            _build_toc_retry_system_prompt(
                system_prompt=base_prompt,
                source_language=context.source_language,
                target_language=context.target_language,
            )
            if attempt == TOC_RETRY_HARDENING_ATTEMPT
            else base_prompt
        )
        dependencies.log_event(
            logging.INFO,
            "toc_prompt_routing_selected",
            "Для блока выбран TOC-ориентированный prompt path.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            prompt_variant=prompt_variant,
            retry_attempt=attempt,
            toc_paragraph_count=getattr(payload, "toc_paragraph_count", 0),
            paragraph_count=getattr(payload, "paragraph_count", 0),
            structural_roles=list(getattr(payload, "structural_roles", []) or []),
        )
        processed_chunk = _generate_block_chunk(
            context=context,
            dependencies=dependencies,
            initialization=initialization,
            payload=payload,
            marker_mode_enabled=marker_mode_enabled,
            system_prompt=system_prompt,
        )
        validation_result = validate_translated_toc_block(
            source_text=payload.target_text,
            processed_chunk=processed_chunk,
            structural_roles=getattr(payload, "structural_roles", None),
            source_language=context.source_language,
            target_language=context.target_language,
        )
        if validation_result.is_valid:
            return processed_chunk

        dependencies.log_event(
            logging.WARNING,
            "toc_validation_rejected",
            "TOC-блок отклонён deterministic validation и будет перегенерирован или завершится ошибкой.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            prompt_variant=prompt_variant,
            retry_attempt=attempt,
            rejection_reason=validation_result.reason,
            toc_paragraph_count=getattr(payload, "toc_paragraph_count", 0),
            paragraph_count=getattr(payload, "paragraph_count", 0),
            structural_roles=list(getattr(payload, "structural_roles", []) or []),
            input_preview=payload.target_text[:300],
            output_preview=processed_chunk[:300],
        )
        rejection_reasons.append(str(validation_result.reason or "unknown"))
        if attempt >= retry_budget:
            raise RuntimeError(
                "toc_language_validation_failed:"
                f"{validation_result.reason};attempt={attempt};history={'|'.join(rejection_reasons)}"
            )
        prompt_variant = "toc_translate"

    raise RuntimeError("toc_language_validation_failed:retry_budget_exhausted;attempt=2;history=retry_budget_exhausted")


def _should_run_translation_second_pass(*, context: Any) -> bool:
    return context.processing_operation == "translate" and bool(
        context.app_config.get("translation_second_pass_enabled", False)
    )


def _resolve_translation_second_pass_model(*, context: Any) -> str:
    configured_model = str(context.app_config.get("translation_second_pass_model", "")).strip()
    return configured_model or context.model


def _resolve_text_call_target(*, selector: str, context: Any, dependencies: Any, initialization: Any) -> tuple[object, str, str, str | None]:
    resolver: Any = getattr(dependencies, "resolve_model_selector", None)
    client_factory: Any = getattr(dependencies, "get_client_for_model_selector", None)
    if not callable(resolver) or not callable(client_factory):
        return initialization.text_client or initialization.client, selector, selector, None

    resolved_selector: Any = resolver(selector, "responses_text")
    if resolved_selector.canonical_selector == (context.canonical_model_selector or context.model):
        return (
            initialization.text_client or initialization.client,
            resolved_selector.model_id,
            resolved_selector.canonical_selector,
            resolved_selector.provider,
        )
    return (
        client_factory(selector, "responses_text"),
        resolved_selector.model_id,
        resolved_selector.canonical_selector,
        resolved_selector.provider,
    )


def _run_translation_second_pass(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    marker_mode_enabled: bool,
    resolve_system_prompt_fn: Any,
) -> str:
    if state.second_pass_system_prompt is None:
        state.second_pass_system_prompt = resolve_system_prompt_fn(
            dependencies.load_system_prompt,
            operation="translate",
            source_language=context.target_language,
            target_language=context.target_language,
            editorial_intensity="literary",
            prompt_variant="literary_polish",
            translation_domain=context.translation_domain,
            source_text=context.translation_domain_instructions,
        )

    second_pass_model = _resolve_translation_second_pass_model(context=context)
    second_pass_client, second_pass_model_id, second_pass_selector, second_pass_provider = _resolve_text_call_target(
        selector=second_pass_model,
        context=context,
        dependencies=dependencies,
        initialization=initialization,
    )
    emitters.emit_status(
        context.runtime,
        stage="Литературная полировка",
        detail=f"Блок {index} проходит дополнительный литературный проход.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=0,
        progress=(index - 1) / initialization.job_count,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, f"Запущен второй литературный проход для блока {index}.")
    dependencies.log_event(
        logging.INFO,
        "block_second_pass_started",
        "Запущен второй литературный проход для блока.",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        model=second_pass_model,
        model_selector=second_pass_selector,
        model_provider=second_pass_provider,
        model_id=second_pass_model_id,
    )
    polished_chunk = dependencies.generate_markdown_block(
        client=second_pass_client,
        model=second_pass_model_id,
        system_prompt=state.second_pass_system_prompt,
        target_text=processed_chunk,
        context_before="",
        context_after="",
        max_retries=context.max_retries,
        expected_paragraph_ids=payload.paragraph_ids if marker_mode_enabled else None,
        marker_mode=marker_mode_enabled,
    )
    dependencies.log_event(
        logging.INFO,
        "block_second_pass_completed",
        "Второй литературный проход для блока завершён.",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        model=second_pass_model,
        model_selector=second_pass_selector,
        model_provider=second_pass_provider,
        model_id=second_pass_model_id,
    )
    return polished_chunk


def build_processed_paragraph_registry_entries(
    *,
    block_index: int,
    paragraph_ids: list[str] | tuple[str, ...],
    processed_chunk: str,
) -> list[dict[str, object]]:
    paragraph_chunks = [chunk.strip() for chunk in processed_chunk.split("\n\n") if chunk.strip()]
    if len(paragraph_chunks) != len(paragraph_ids):
        raise RuntimeError(
            f"paragraph_marker_registry_mismatch:block={block_index}:expected={len(paragraph_ids)}:actual={len(paragraph_chunks)}"
        )
    return [
        {
            "block_index": block_index,
            "paragraph_id": paragraph_id,
            "text": paragraph_chunk,
        }
        for paragraph_id, paragraph_chunk in zip(paragraph_ids, paragraph_chunks)
    ]


def emit_block_started(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    initialization: Any,
    index: int,
    payload: Any,
) -> None:
    segment_status_by_id, segment_progress_by_id, active_segment_id, active_segment_title = _resolve_segment_status_payload(
        initialization=initialization,
        index=index,
        status="processing",
    )
    emitters.emit_status(
        context.runtime,
        stage="Подготовка блока",
        detail=(
            f"Готовлю блок {index} из {initialization.job_count} к отправке в модель."
            if payload.job_kind == "llm"
            else f"Готовлю passthrough-блок {index} из {initialization.job_count} без вызова модели."
        ),
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        segment_status_by_id=segment_status_by_id,
        segment_progress_by_id=segment_progress_by_id,
        active_segment_id=active_segment_id,
        active_segment_title=active_segment_title,
        progress=(index - 1) / initialization.job_count,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, f"Начата обработка блока {index} из {initialization.job_count}.")
    dependencies.log_event(
        logging.DEBUG,
        "block_started",
        "Начата обработка блока",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        model=context.model,
        model_selector=context.model_selector or context.model,
        canonical_model_selector=context.canonical_model_selector or context.model,
        model_provider=context.model_provider,
        model_id=context.model_id or context.model,
        job_kind=payload.job_kind,
    )


def execute_processing_block(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    is_marker_mode_enabled_fn: Any,
    resolve_system_prompt_fn: Any,
) -> tuple[str, bool]:
    if payload.job_kind == "passthrough" and not _should_route_toc_through_llm(context=context, payload=payload):
        emitters.emit_status(
            context.runtime,
            stage="Passthrough блока",
            detail=f"Блок {index} не требует LLM-обработки и будет перенесён в Markdown как есть.",
            current_block=index,
            block_count=initialization.job_count,
            target_chars=payload.target_chars,
            context_chars=payload.context_chars,
            progress=(index - 1) / initialization.job_count,
            is_running=True,
        )
        emitters.emit_activity(context.runtime, f"Блок {index} пропущен через passthrough без вызова модели.")
        context.on_progress(preview_title="Текущий Markdown")
        return payload.target_text, False

    marker_mode_enabled = is_marker_mode_enabled_fn(context, payload)
    emitters.emit_status(
        context.runtime,
        stage="Ожидание ответа модели",
        detail=f"Блок {index} отправлен в модель. Приложение работает, ожидаю ответ.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        progress=(index - 1) / initialization.job_count,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, f"Блок {index} отправлен в модель.")
    context.on_progress(preview_title="Текущий Markdown")
    if _should_route_toc_through_llm(context=context, payload=payload):
        processed_chunk = _validate_toc_chunk_with_retries(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            marker_mode_enabled=marker_mode_enabled,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
        )
    else:
        system_prompt = _get_cached_system_prompt(
            context=context,
            dependencies=dependencies,
            state=state,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
            prompt_variant="default",
        )
        processed_chunk = _generate_block_chunk(
            context=context,
            dependencies=dependencies,
            initialization=initialization,
            payload=payload,
            marker_mode_enabled=marker_mode_enabled,
            system_prompt=system_prompt,
        )
    if _should_run_translation_second_pass(context=context):
        processed_chunk = _run_translation_second_pass(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            processed_chunk=processed_chunk,
            marker_mode_enabled=marker_mode_enabled,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
        )
    return processed_chunk, marker_mode_enabled


def append_marker_registry_entries(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    build_processed_paragraph_registry_entries_fn: Any,
) -> None:
    paragraph_ids = payload.paragraph_ids or []
    state.generated_paragraph_registry.extend(
        build_processed_paragraph_registry_entries_fn(
            block_index=index,
            paragraph_ids=paragraph_ids,
            processed_chunk=processed_chunk,
        )
    )
    dependencies.log_event(
        logging.DEBUG,
        "block_marker_registry_built",
        "Для блока собран marker-aware paragraph registry.",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        paragraph_count=len(paragraph_ids),
    )


def emit_block_completed(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    current_markdown_fn: Any,
) -> None:
    segment_status_by_id, segment_progress_by_id, active_segment_id, active_segment_title = _resolve_segment_status_payload(
        initialization=initialization,
        index=index,
        status="completed",
    )
    emitters.emit_state(
        context.runtime,
        processed_block_markdowns=state.processed_chunks.copy(),
        latest_markdown=current_markdown_fn(state.processed_chunks),
        processed_paragraph_registry=state.generated_paragraph_registry.copy(),
    )
    emitters.emit_log(
        context.runtime,
        status="OK",
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        details=f"готово за {time.perf_counter() - state.started_at:.1f} сек. с начала запуска",
    )
    persist_terminal_job_result(
        context=context,
        dependencies=dependencies,
        index=index,
        status="completed",
    )
    emitters.emit_status(
        context.runtime,
        stage="Блок обработан",
        detail=f"Получен ответ для блока {index}. Обновляю промежуточный Markdown.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        segment_status_by_id=segment_status_by_id,
        segment_progress_by_id=segment_progress_by_id,
        active_segment_id=active_segment_id,
        active_segment_title=active_segment_title,
        progress=index / initialization.job_count,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, f"Блок {index} обработан успешно.")
    output_chars = len(processed_chunk)
    output_ratio = round(output_chars / max(payload.target_chars, 1), 2)
    dependencies.log_event(
        logging.DEBUG,
        "block_completed",
        "Блок обработан успешно",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        output_chars=output_chars,
        output_ratio=output_ratio,
        input_preview=payload.target_text[:300],
        output_preview=processed_chunk[:300],
        job_kind=payload.job_kind,
    )
    context.on_progress(preview_title="Текущий Markdown")


def process_single_block(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    job: Any,
    parse_processing_job_fn: Any,
    handle_invalid_processing_job_fn: Any,
    emit_block_started_fn: Any,
    is_marker_mode_enabled_fn: Any,
    execute_processing_block_fn: Any,
    handle_block_generation_failure_fn: Any,
    classify_processed_block_fn: Any,
    handle_processed_block_rejection_fn: Any,
    append_marker_registry_entries_fn: Any,
    handle_marker_registry_failure_fn: Any,
    emit_block_completed_fn: Any,
) -> PipelineResult | None:
    try:
        payload = parse_processing_job_fn(job=job)
    except (KeyError, TypeError, ValueError) as exc:
        return handle_invalid_processing_job_fn(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            exc=exc,
        )

    emit_block_started_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        initialization=initialization,
        index=index,
        payload=payload,
    )
    marker_mode_enabled = is_marker_mode_enabled_fn(context, payload)
    try:
        processed_chunk, marker_mode_enabled = execute_processing_block_fn(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
        )
    except Exception as exc:
        return handle_block_generation_failure_fn(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            marker_mode_enabled=marker_mode_enabled,
            exc=exc,
        )

    processed_block_status = classify_processed_block_fn(payload.target_text, processed_chunk)
    if processed_block_status != "valid":
        return handle_processed_block_rejection_fn(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            initialization=initialization,
            index=index,
            target_chars=payload.target_chars,
            context_chars=payload.context_chars,
            target_text=payload.target_text,
            processed_chunk=processed_chunk,
            rejection_kind=processed_block_status,
        )

    state.processed_chunks.append(processed_chunk)
    if payload.narration_include:
        state.narration_chunks.append(processed_chunk)
    else:
        state.excluded_narration_block_count += 1
    if payload.job_kind == "llm" and marker_mode_enabled and payload.paragraph_ids:
        try:
            append_marker_registry_entries_fn(
                context=context,
                dependencies=dependencies,
                state=state,
                initialization=initialization,
                index=index,
                payload=payload,
                processed_chunk=processed_chunk,
            )
        except Exception as exc:
            return handle_marker_registry_failure_fn(
                context=context,
                dependencies=dependencies,
                emitters=emitters,
                state=state,
                initialization=initialization,
                index=index,
                payload=payload,
                processed_chunk=processed_chunk,
                exc=exc,
            )
    emit_block_completed_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        index=index,
        payload=payload,
        processed_chunk=processed_chunk,
    )
    return None


def run_block_processing_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    emit_stopped_result_fn: Any,
    process_single_block_fn: Any,
    current_markdown_fn: Any,
    emit_failed_result_fn: Any,
) -> PipelineResult | None:
    for index, job in enumerate(context.jobs, start=1):
        if dependencies.should_stop_processing(context.runtime):
            stop_message = "Обработка остановлена пользователем."
            return emit_stopped_result_fn(
                emitters=emitters,
                runtime=context.runtime,
                detail=stop_message,
                progress=(index - 1) / initialization.job_count,
                block_index=max(0, index - 1),
                block_count=initialization.job_count,
            )

        block_outcome = process_single_block_fn(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            job=job,
        )
        if block_outcome is not None:
            return block_outcome

    if len(state.processed_chunks) != initialization.job_count:
        critical_message = dependencies.present_error(
            "processed_block_count_mismatch",
            RuntimeError("Количество обработанных блоков не совпало с планом обработки."),
            "Критическая ошибка финализации",
            filename=context.uploaded_filename,
            processed_count=len(state.processed_chunks),
            planned_count=initialization.job_count,
            incomplete_count=max(initialization.job_count - len(state.processed_chunks), 0),
        )
        emitters.emit_state(
            context.runtime,
            last_error=critical_message,
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        return emit_failed_result_fn(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Критическая ошибка",
            detail=critical_message,
            progress=len(state.processed_chunks) / max(initialization.job_count, 1),
            activity_message="Обнаружено несоответствие количества обработанных блоков.",
            block_index=len(state.processed_chunks),
            block_count=initialization.job_count,
            target_chars=len(current_markdown_fn(state.processed_chunks)),
            context_chars=0,
            log_details=critical_message,
        )

    return None
