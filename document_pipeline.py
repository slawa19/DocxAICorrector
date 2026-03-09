import logging
import time


def run_document_processing(
    *,
    uploaded_file,
    jobs: list[dict[str, str | int]],
    image_assets: list,
    image_mode: str,
    app_config: dict[str, object],
    model: str,
    max_retries: int,
    on_progress,
    runtime,
    resolve_uploaded_filename,
    get_client,
    ensure_pandoc_available,
    load_system_prompt,
    log_event,
    present_error,
    emit_state,
    emit_finalize,
    emit_activity,
    emit_log,
    emit_status,
    should_stop_processing,
    generate_markdown_block,
    process_document_images,
    inspect_placeholder_integrity,
    convert_markdown_to_docx_bytes,
    reinsert_inline_images,
):
    uploaded_filename = resolve_uploaded_filename(uploaded_file)
    try:
        client = get_client()
        ensure_pandoc_available()
        system_prompt = load_system_prompt()
        log_event(
            logging.INFO,
            "processing_started",
            "Запуск обработки документа",
            filename=uploaded_filename,
            model=model,
            block_count=len(jobs),
            max_retries=max_retries,
            image_count=len(image_assets),
        )
        emit_activity(runtime, f"Инициализация завершена. Модель: {model}.")
    except Exception as exc:
        error_message = present_error(
            "processing_init_failed",
            exc,
            "Ошибка инициализации обработки",
            filename=uploaded_filename,
            model=model,
        )
        emit_state(runtime, last_error=error_message)
        emit_finalize(runtime, "Ошибка инициализации", error_message, 0.0)
        return "failed"

    processed_chunks: list[str] = []
    started_at = time.perf_counter()

    for index, job in enumerate(jobs, start=1):
        if should_stop_processing(runtime):
            stop_message = "Обработка остановлена пользователем."
            emit_finalize(runtime, "Остановлено пользователем", stop_message, (index - 1) / len(jobs))
            emit_activity(runtime, stop_message)
            emit_log(
                runtime,
                status="STOP",
                block_index=max(0, index - 1),
                block_count=len(jobs),
                target_chars=0,
                context_chars=0,
                details=stop_message,
            )
            return "stopped"

        target_chars = int(job["target_chars"])
        context_chars = int(job["context_chars"])
        emit_status(
            runtime,
            stage="Подготовка блока",
            detail=f"Готовлю блок {index} из {len(jobs)} к отправке в OpenAI.",
            current_block=index,
            block_count=len(jobs),
            target_chars=target_chars,
            context_chars=context_chars,
            progress=(index - 1) / len(jobs),
            is_running=True,
        )
        emit_activity(runtime, f"Начата обработка блока {index} из {len(jobs)}.")
        log_event(
            logging.INFO,
            "block_started",
            "Начата обработка блока",
            filename=uploaded_filename,
            block_index=index,
            block_count=len(jobs),
            target_chars=target_chars,
            context_chars=context_chars,
            model=model,
        )
        try:
            emit_status(
                runtime,
                stage="Ожидание ответа OpenAI",
                detail=f"Блок {index} отправлен в модель. Приложение работает, ожидаю ответ.",
                current_block=index,
                block_count=len(jobs),
                target_chars=target_chars,
                context_chars=context_chars,
                progress=(index - 1) / len(jobs),
                is_running=True,
            )
            emit_activity(runtime, f"Блок {index} отправлен в OpenAI.")
            on_progress(preview_title="Текущий Markdown")
            processed_chunk = generate_markdown_block(
                client=client,
                model=model,
                system_prompt=system_prompt,
                target_text=str(job["target_text"]),
                context_before=str(job["context_before"]),
                context_after=str(job["context_after"]),
                max_retries=max_retries,
            )
        except Exception as exc:
            emit_state(runtime, latest_markdown="\n\n".join(processed_chunks).strip())
            error_message = present_error(
                "block_failed",
                exc,
                "Ошибка обработки блока",
                filename=uploaded_filename,
                block_index=index,
                block_count=len(jobs),
                target_chars=target_chars,
                context_chars=context_chars,
                model=model,
            )
            formatted_error = f"Ошибка на блоке {index}: {error_message}"
            emit_state(runtime, last_error=formatted_error)
            emit_finalize(runtime, "Ошибка обработки", formatted_error, (index - 1) / len(jobs))
            emit_activity(runtime, f"Блок {index}: ошибка обработки.")
            emit_log(
                runtime,
                status="ERROR",
                block_index=index,
                block_count=len(jobs),
                target_chars=target_chars,
                context_chars=context_chars,
                details=error_message,
            )
            return "failed"

        if not processed_chunk.strip():
            critical_message = present_error(
                "empty_processed_block",
                RuntimeError("Модель вернула пустой Markdown-блок после успешного вызова."),
                "Критическая ошибка обработки блока",
                filename=uploaded_filename,
                block_index=index,
            )
            formatted_error = f"Ошибка на блоке {index}: {critical_message}"
            emit_state(runtime, last_error=formatted_error)
            emit_finalize(runtime, "Критическая ошибка", formatted_error, (index - 1) / len(jobs))
            emit_activity(runtime, f"Блок {index}: модель вернула пустой Markdown.")
            emit_log(
                runtime,
                status="ERROR",
                block_index=index,
                block_count=len(jobs),
                target_chars=target_chars,
                context_chars=context_chars,
                details=critical_message,
            )
            return "failed"

        processed_chunks.append(processed_chunk)
        emit_state(
            runtime,
            processed_block_markdowns=processed_chunks.copy(),
            markdown_preview_block_index=len(processed_chunks),
            latest_markdown="\n\n".join(processed_chunks).strip(),
        )
        emit_log(
            runtime,
            status="OK",
            block_index=index,
            block_count=len(jobs),
            target_chars=target_chars,
            context_chars=context_chars,
            details=f"готово за {time.perf_counter() - started_at:.1f} сек. с начала запуска",
        )
        emit_status(
            runtime,
            stage="Блок обработан",
            detail=f"Получен ответ для блока {index}. Обновляю промежуточный Markdown.",
            current_block=index,
            block_count=len(jobs),
            target_chars=target_chars,
            context_chars=context_chars,
            progress=index / len(jobs),
            is_running=True,
        )
        emit_activity(runtime, f"Блок {index} обработан успешно.")
        log_event(
            logging.INFO,
            "block_completed",
            "Блок обработан успешно",
            filename=uploaded_filename,
            block_index=index,
            block_count=len(jobs),
            target_chars=int(job["target_chars"]),
            context_chars=int(job["context_chars"]),
            output_chars=len(processed_chunk),
        )
        on_progress(preview_title="Текущий Markdown")

    if len(processed_chunks) != len(jobs):
        critical_message = present_error(
            "processed_block_count_mismatch",
            RuntimeError("Количество обработанных блоков не совпало с планом обработки."),
            "Критическая ошибка финализации",
            filename=uploaded_filename,
            processed_count=len(processed_chunks),
            planned_count=len(jobs),
        )
        emit_state(runtime, last_error=critical_message)
        emit_finalize(runtime, "Критическая ошибка", critical_message, len(processed_chunks) / len(jobs))
        emit_activity(runtime, "Обнаружено несоответствие количества обработанных блоков.")
        emit_log(
            runtime,
            status="ERROR",
            block_index=len(processed_chunks),
            block_count=len(jobs),
            target_chars=len("\n\n".join(processed_chunks).strip()),
            context_chars=0,
            details=critical_message,
        )
        return "failed"

    final_markdown = "\n\n".join(processed_chunks).strip()
    emit_state(runtime, latest_markdown=final_markdown)
    processed_image_assets = process_document_images(
        image_assets=image_assets,
        image_mode=image_mode,
        config=app_config,
        on_progress=on_progress,
        runtime=runtime,
        client=client,
    )
    if should_stop_processing(runtime):
        emit_finalize(runtime, "Остановлено пользователем", "Обработка остановлена пользователем.", 1.0)
        emit_activity(runtime, "Обработка документа остановлена пользователем.")
        return "stopped"

    placeholder_integrity = inspect_placeholder_integrity(final_markdown, processed_image_assets)
    for asset in processed_image_assets:
        asset.update_pipeline_metadata(placeholder_status=placeholder_integrity.get(asset.image_id))
    placeholder_mismatches: dict[str, str] = {}
    for image_id, placeholder_status in placeholder_integrity.items():
        if placeholder_status == "ok":
            continue
        placeholder_mismatches[image_id] = placeholder_status
        log_event(
            logging.WARNING,
            "image_placeholder_mismatch",
            "Обнаружено нарушение контракта image placeholder.",
            filename=uploaded_filename,
            image_id=image_id,
            placeholder_status=placeholder_status,
        )
    if placeholder_mismatches:
        mismatch_details = ", ".join(
            f"{image_id}:{placeholder_status}" for image_id, placeholder_status in sorted(placeholder_mismatches.items())
        )
        critical_message = present_error(
            "image_placeholder_integrity_failed",
            RuntimeError(f"Нарушен контракт placeholder-ов: {mismatch_details}"),
            "Критическая ошибка подготовки изображений",
            filename=uploaded_filename,
            mismatch_count=len(placeholder_mismatches),
            mismatch_details=mismatch_details,
        )
        emit_state(runtime, last_error=critical_message)
        emit_finalize(runtime, "Критическая ошибка", critical_message, 1.0)
        emit_activity(runtime, "Сборка DOCX остановлена из-за потери или дублирования image placeholder.")
        emit_log(
            runtime,
            status="ERROR",
            block_index=len(jobs),
            block_count=len(jobs),
            target_chars=len(final_markdown),
            context_chars=0,
            details=critical_message,
        )
        return "failed"
    emit_status(
        runtime,
        stage="Сборка DOCX",
        detail="Все блоки готовы. Собираю итоговый DOCX из Markdown.",
        current_block=len(jobs),
        block_count=len(jobs),
        target_chars=len(final_markdown),
        context_chars=0,
        progress=1.0,
        is_running=True,
    )
    emit_activity(runtime, "Все блоки готовы. Начата сборка итогового DOCX.")
    on_progress(preview_title="Текущий Markdown")

    try:
        docx_bytes = convert_markdown_to_docx_bytes(final_markdown)
        if processed_image_assets:
            docx_bytes = reinsert_inline_images(docx_bytes, processed_image_assets)
    except Exception as exc:
        error_message = present_error(
            "docx_build_failed",
            exc,
            "Ошибка сборки DOCX",
            filename=uploaded_filename,
            final_markdown_chars=len(final_markdown),
        )
        emit_state(runtime, last_error=error_message)
        emit_finalize(runtime, "Ошибка сборки DOCX", error_message, 1.0)
        emit_activity(runtime, "Ошибка на этапе сборки DOCX.")
        emit_log(
            runtime,
            status="ERROR",
            block_index=len(jobs),
            block_count=len(jobs),
            target_chars=len(final_markdown),
            context_chars=0,
            details=error_message,
        )
        return "failed"

    if not docx_bytes:
        critical_message = present_error(
            "empty_docx_bytes",
            RuntimeError("Сборка DOCX завершилась без содержимого файла."),
            "Критическая ошибка сборки DOCX",
            filename=uploaded_filename,
        )
        emit_state(runtime, last_error=critical_message)
        emit_finalize(runtime, "Критическая ошибка", critical_message, 1.0)
        emit_activity(runtime, "DOCX собран без содержимого.")
        emit_log(
            runtime,
            status="ERROR",
            block_index=len(jobs),
            block_count=len(jobs),
            target_chars=len(final_markdown),
            context_chars=0,
            details=critical_message,
        )
        return "failed"

    emit_state(runtime, latest_docx_bytes=docx_bytes, latest_markdown=final_markdown, last_error="")
    emit_finalize(
        runtime,
        "Обработка завершена",
        f"Документ обработан за {time.perf_counter() - started_at:.1f} сек.",
        1.0,
    )
    emit_activity(runtime, "Документ обработан полностью.")
    log_event(
        logging.INFO,
        "processing_completed",
        "Документ обработан полностью",
        filename=uploaded_filename,
        block_count=len(jobs),
        final_markdown_chars=len(final_markdown),
        elapsed_seconds=round(time.perf_counter() - started_at, 2),
    )
    emit_log(
        runtime,
        status="DONE",
        block_index=len(jobs),
        block_count=len(jobs),
        target_chars=len(final_markdown),
        context_chars=0,
        details=f"весь документ обработан за {time.perf_counter() - started_at:.1f} сек.",
    )
    return "succeeded"