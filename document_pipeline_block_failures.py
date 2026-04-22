import logging
from typing import Any, Literal, TypeAlias


PipelineResult: TypeAlias = Literal["succeeded", "failed", "stopped"]


def _parse_toc_validation_failure_details(exc: Exception) -> tuple[str | None, int | None, list[str]]:
    prefix = "toc_language_validation_failed:"
    text = str(exc)
    if prefix not in text:
        return None, None, []
    payload = text.split(prefix, 1)[1].strip()
    parts = [part.strip() for part in payload.split(";") if part.strip()]
    reason = parts[0] if parts else "unknown_toc_validation_failure"
    retry_attempt = None
    rejection_history: list[str] = []
    for part in parts[1:]:
        if part.startswith("attempt="):
            try:
                retry_attempt = int(part.split("=", 1)[1])
            except ValueError:
                retry_attempt = None
        elif part.startswith("history="):
            rejection_history = [item for item in part.split("=", 1)[1].split("|") if item]
    return reason, retry_attempt, rejection_history


def handle_invalid_processing_job(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    exc: Exception,
    current_markdown_fn: Any,
    emit_failed_result_fn: Any,
) -> PipelineResult:
    emitters.emit_state(
        context.runtime,
        latest_markdown=current_markdown_fn(state.processed_chunks),
        latest_docx_bytes=None,
    )
    error_message = dependencies.present_error(
        "invalid_processing_job",
        exc,
        "Ошибка подготовки блока",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        model=context.model,
    )
    formatted_error = f"Ошибка на блоке {index}: {error_message}"
    emitters.emit_state(context.runtime, last_error=formatted_error, latest_docx_bytes=None)
    return emit_failed_result_fn(
        emitters=emitters,
        runtime=context.runtime,
        finalize_stage="Ошибка подготовки блока",
        detail=formatted_error,
        progress=(index - 1) / initialization.job_count,
        activity_message=f"Блок {index}: некорректный план обработки.",
        block_index=index,
        block_count=initialization.job_count,
        target_chars=0,
        context_chars=0,
        log_details=error_message,
    )


def handle_block_generation_failure(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    marker_mode_enabled: bool,
    exc: Exception,
    extract_marker_diagnostics_code_fn: Any,
    write_marker_diagnostics_artifact_fn: Any,
    current_markdown_fn: Any,
    emit_failed_result_fn: Any,
) -> PipelineResult:
    marker_diagnostics_artifact = None
    marker_error_code = extract_marker_diagnostics_code_fn(exc) if marker_mode_enabled else None
    toc_validation_reason, toc_retry_attempt, toc_rejection_history = _parse_toc_validation_failure_details(exc)
    if marker_error_code is not None:
        marker_diagnostics_artifact = write_marker_diagnostics_artifact_fn(
            stage="generation",
            uploaded_filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            error_code=marker_error_code,
            target_text=payload.target_text_with_markers,
            context_before=payload.context_before,
            context_after=payload.context_after,
            paragraph_ids=payload.paragraph_ids,
        )
    emitters.emit_state(
        context.runtime,
        latest_markdown=current_markdown_fn(state.processed_chunks),
        latest_docx_bytes=None,
    )
    error_code = "toc_language_validation_failed" if toc_validation_reason is not None else "block_failed"
    error_title = "Ошибка обработки блока оглавления" if toc_validation_reason is not None else "Ошибка обработки блока"
    error_message = dependencies.present_error(
        error_code,
        exc,
        error_title,
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        model=context.model,
        toc_validation_reason=toc_validation_reason,
        toc_retry_attempt=toc_retry_attempt,
    )
    formatted_error = f"Ошибка на блоке {index}: {error_message}"
    emitters.emit_state(
        context.runtime,
        last_error=formatted_error,
        latest_docx_bytes=None,
        latest_marker_diagnostics_artifact=marker_diagnostics_artifact,
    )
    outcome = emit_failed_result_fn(
        emitters=emitters,
        runtime=context.runtime,
        finalize_stage="Ошибка обработки блока оглавления" if toc_validation_reason is not None else "Ошибка обработки",
        detail=formatted_error,
        progress=(index - 1) / initialization.job_count,
        activity_message=(
            f"Блок {index}: отклонён TOC validation после исчерпания retry budget."
            if toc_validation_reason is not None
            else f"Блок {index}: ошибка обработки."
        ),
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        log_details=(
            f"{error_message}; marker diagnostics: {marker_diagnostics_artifact}"
            if marker_diagnostics_artifact
            else error_message
        ),
    )
    if marker_diagnostics_artifact is not None:
        dependencies.log_event(
            logging.WARNING,
            "marker_diagnostics_artifact_created",
            "Сохранён marker diagnostics artifact для блока с ошибкой generation.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            artifact_path=marker_diagnostics_artifact,
            error_code=marker_error_code,
        )
    if toc_validation_reason is not None:
        dependencies.log_event(
            logging.WARNING,
            "toc_validation_failed_terminal",
            "TOC-блок не прошёл validation после исчерпания retry budget.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            rejection_reason=toc_validation_reason,
            retry_attempt=toc_retry_attempt,
            rejection_reasons=toc_rejection_history,
            toc_paragraph_count=getattr(payload, "toc_paragraph_count", 0),
            paragraph_count=getattr(payload, "paragraph_count", 0),
            structural_roles=list(getattr(payload, "structural_roles", []) or []),
            input_preview=payload.target_text[:300],
        )
    return outcome


def handle_processed_block_rejection(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    initialization: Any,
    index: int,
    target_chars: int,
    context_chars: int,
    target_text: str,
    processed_chunk: str,
    rejection_kind: str,
    emit_failed_result_fn: Any,
) -> PipelineResult:
    if rejection_kind == "empty":
        critical_message = dependencies.present_error(
            "empty_processed_block",
            RuntimeError("Модель вернула пустой Markdown-блок после успешного вызова (empty_processed_block)."),
            "Критическая ошибка обработки блока",
            filename=context.uploaded_filename,
            block_index=index,
            output_classification="empty_processed_block",
        )
        formatted_error = f"Ошибка на блоке {index}: {critical_message}"
        emitters.emit_state(context.runtime, last_error=formatted_error, latest_docx_bytes=None)
        return emit_failed_result_fn(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Критическая ошибка",
            detail=formatted_error,
            progress=(index - 1) / initialization.job_count,
            activity_message=f"Блок {index}: модель вернула пустой Markdown.",
            block_index=index,
            block_count=initialization.job_count,
            target_chars=target_chars,
            context_chars=context_chars,
            log_details=critical_message,
        )

    critical_message = dependencies.present_error(
        "structurally_insufficient_processed_block",
        RuntimeError(
            "Модель вернула только заголовок при наличии основного текста во входном блоке (heading_only_output)."
        ),
        "Критическая ошибка обработки блока",
        filename=context.uploaded_filename,
        block_index=index,
        output_classification="heading_only_output",
    )
    formatted_error = f"Ошибка на блоке {index}: {critical_message}"
    emitters.emit_state(context.runtime, last_error=formatted_error, latest_docx_bytes=None)
    outcome = emit_failed_result_fn(
        emitters=emitters,
        runtime=context.runtime,
        finalize_stage="Критическая ошибка",
        detail=formatted_error,
        progress=(index - 1) / initialization.job_count,
        activity_message=f"Блок {index}: отклонён структурно недостаточный Markdown.",
        block_index=index,
        block_count=initialization.job_count,
        target_chars=target_chars,
        context_chars=context_chars,
        log_details=critical_message,
    )
    dependencies.log_event(
        logging.WARNING,
        "block_rejected",
        "Блок отклонён по acceptance-контракту",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        target_chars=target_chars,
        context_chars=context_chars,
        output_classification="heading_only_output",
        input_preview=target_text[:300],
        output_preview=processed_chunk[:300],
    )
    return outcome


def handle_marker_registry_failure(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    exc: Exception,
    write_marker_diagnostics_artifact_fn: Any,
    extract_marker_diagnostics_code_fn: Any,
    current_markdown_fn: Any,
    emit_failed_result_fn: Any,
) -> PipelineResult:
    marker_diagnostics_artifact = write_marker_diagnostics_artifact_fn(
        stage="registry",
        uploaded_filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        error_code=extract_marker_diagnostics_code_fn(exc) or "marker_registry_build_failed",
        target_text=payload.target_text_with_markers,
        context_before=payload.context_before,
        context_after=payload.context_after,
        paragraph_ids=payload.paragraph_ids,
        processed_chunk=processed_chunk,
    )
    emitters.emit_state(
        context.runtime,
        latest_markdown=current_markdown_fn(state.processed_chunks),
        latest_docx_bytes=None,
    )
    error_message = dependencies.present_error(
        "block_marker_registry_failed",
        exc,
        "Ошибка marker-реестра блока",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
    )
    formatted_error = f"Ошибка на блоке {index}: {error_message}"
    emitters.emit_state(
        context.runtime,
        last_error=formatted_error,
        latest_docx_bytes=None,
        latest_marker_diagnostics_artifact=marker_diagnostics_artifact,
    )
    outcome = emit_failed_result_fn(
        emitters=emitters,
        runtime=context.runtime,
        finalize_stage="Ошибка marker-реестра",
        detail=formatted_error,
        progress=index / initialization.job_count,
        activity_message=f"Блок {index}: не удалось собрать marker-aware paragraph registry.",
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        log_details=(
            f"{error_message}; marker diagnostics: {marker_diagnostics_artifact}"
            if marker_diagnostics_artifact
            else error_message
        ),
    )
    dependencies.log_event(
        logging.WARNING,
        "marker_diagnostics_artifact_created",
        "Сохранён marker diagnostics artifact для блока с ошибкой registry build.",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        artifact_path=marker_diagnostics_artifact,
    )
    return outcome