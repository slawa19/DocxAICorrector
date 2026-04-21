import logging
import time
from typing import Any, Literal, TypeAlias


PipelineResult: TypeAlias = Literal["succeeded", "failed", "stopped"]


def _should_run_translation_second_pass(*, context: Any) -> bool:
    return context.processing_operation == "translate" and bool(
        context.app_config.get("translation_second_pass_enabled", False)
    )


def _resolve_translation_second_pass_model(*, context: Any) -> str:
    configured_model = str(context.app_config.get("translation_second_pass_model", "")).strip()
    return configured_model or context.model


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
        )

    second_pass_model = _resolve_translation_second_pass_model(context=context)
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
    )
    polished_chunk = dependencies.generate_markdown_block(
        client=initialization.client,
        model=second_pass_model,
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
    emitters.emit_status(
        context.runtime,
        stage="Подготовка блока",
        detail=(
            f"Готовлю блок {index} из {initialization.job_count} к отправке в OpenAI."
            if payload.job_kind == "llm"
            else f"Готовлю passthrough-блок {index} из {initialization.job_count} без вызова OpenAI."
        ),
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
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
    if payload.job_kind == "passthrough":
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
        emitters.emit_activity(context.runtime, f"Блок {index} пропущен через passthrough без OpenAI.")
        context.on_progress(preview_title="Текущий Markdown")
        return payload.target_text, False

    marker_mode_enabled = is_marker_mode_enabled_fn(context, payload)
    if state.system_prompt is None:
        state.system_prompt = resolve_system_prompt_fn(
            dependencies.load_system_prompt,
            operation=context.processing_operation,
            source_language=context.source_language,
            target_language=context.target_language,
            editorial_intensity=str(context.app_config.get("editorial_intensity_default", "literary")),
        )
    emitters.emit_status(
        context.runtime,
        stage="Ожидание ответа OpenAI",
        detail=f"Блок {index} отправлен в модель. Приложение работает, ожидаю ответ.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        progress=(index - 1) / initialization.job_count,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, f"Блок {index} отправлен в OpenAI.")
    context.on_progress(preview_title="Текущий Markdown")
    processed_chunk = dependencies.generate_markdown_block(
        client=initialization.client,
        model=context.model,
        system_prompt=state.system_prompt,
        target_text=payload.target_text_with_markers if marker_mode_enabled else payload.target_text,
        context_before=payload.context_before,
        context_after=payload.context_after,
        max_retries=context.max_retries,
        expected_paragraph_ids=payload.paragraph_ids if marker_mode_enabled else None,
        marker_mode=marker_mode_enabled,
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
    emitters.emit_status(
        context.runtime,
        stage="Блок обработан",
        detail=f"Получен ответ для блока {index}. Обновляю промежуточный Markdown.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
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
        emitters.emit_state(context.runtime, last_error=critical_message, latest_docx_bytes=None)
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