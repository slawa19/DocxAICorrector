import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

from formatting_diagnostics_retention import collect_recent_formatting_diagnostics, load_formatting_diagnostics_payloads
from generation import strip_markdown_for_narration


PipelineResult = Literal["succeeded", "failed", "stopped"]
_ELEVENLABS_TAG_PATTERN = re.compile(r"\[(?:thoughtful|curious|serious|sad|excited|annoyed|sarcastic|whispers|short pause|long pause|sighs|laughs|chuckles|exhales)\]")


def collect_recent_formatting_diagnostics_artifacts(*, since_epoch_seconds: float, diagnostics_dir: Path) -> list[str]:
    return collect_recent_formatting_diagnostics(
        since_epoch_seconds=since_epoch_seconds,
        diagnostics_dir=diagnostics_dir,
    )


def _load_formatting_diagnostics_payloads(artifact_paths: Sequence[str]) -> list[dict[str, object]]:
    return load_formatting_diagnostics_payloads(artifact_paths)


def _formatting_diagnostics_requires_user_warning(payload: Mapping[str, object]) -> bool:
    caption_heading_conflicts = payload.get("caption_heading_conflicts")
    if isinstance(caption_heading_conflicts, list) and caption_heading_conflicts:
        return True

    source_count = payload.get("source_count")
    mapped_count = payload.get("mapped_count")
    if isinstance(source_count, int) and isinstance(mapped_count, int):
        if source_count >= 8 and mapped_count == 0:
            return True

    return False


def _build_formatting_diagnostics_user_message(payload: Mapping[str, object], *, warn_user: bool) -> str:
    source_count = payload.get("source_count")
    mapped_count = payload.get("mapped_count")
    unmapped_source_ids = payload.get("unmapped_source_ids")
    unmapped_source_count = len(unmapped_source_ids) if isinstance(unmapped_source_ids, list) else None
    caption_heading_conflicts = payload.get("caption_heading_conflicts")
    caption_conflict_count = len(caption_heading_conflicts) if isinstance(caption_heading_conflicts, list) else 0

    coverage_summary = None
    if isinstance(mapped_count, int) and isinstance(source_count, int) and source_count > 0:
        coverage_summary = f"Совпадение найдено для {mapped_count} из {source_count} исходных абзацев"
        if unmapped_source_count:
            coverage_summary += f"; без точного соответствия осталось {unmapped_source_count}"

    if warn_user:
        message = (
            "DOCX собран, но найдены спорные места форматирования, которые стоит проверить вручную. "
            "Обычно это означает, что часть подписей, заголовков или абзацной структуры перестроилась при генерации."
        )
        if coverage_summary:
            message += f" {coverage_summary}."
        if caption_conflict_count:
            message += f" Конфликтов подписи/заголовка: {caption_conflict_count}."
        return message

    message = (
        "DOCX собран. Дополнительное восстановление форматирования было частично пропущено, "
        "потому что точное сопоставление абзацев нашлось не везде. Это нормально, когда модель объединяет, делит или переформулирует абзацы."
    )
    if coverage_summary:
        message += f" {coverage_summary}."
    return message


def build_formatting_diagnostics_user_feedback(artifact_paths: Sequence[str]) -> tuple[str, str, str]:
    payloads = _load_formatting_diagnostics_payloads(artifact_paths)
    if not payloads:
        return (
            "INFO",
            "Сборка DOCX завершена; сохранена служебная диагностика форматирования.",
            "DOCX собран; сохранена служебная диагностика форматирования.",
        )

    warning_payloads = [payload for payload in payloads if _formatting_diagnostics_requires_user_warning(payload)]
    if warning_payloads:
        return (
            "WARN",
            "Сборка DOCX завершена; найдены места, где форматирование стоит проверить вручную.",
            _build_formatting_diagnostics_user_message(warning_payloads[0], warn_user=True),
        )

    return (
        "INFO",
        "Сборка DOCX завершена; сохранена служебная диагностика форматирования.",
        _build_formatting_diagnostics_user_message(payloads[0], warn_user=False),
    )


def _emit_terminal_result(
    *,
    emitters: Any,
    runtime: object,
    finalize_stage: str,
    detail: str,
    progress: float,
    terminal_kind: str,
    activity_message: str,
    log_status: str,
    block_index: int,
    block_count: int,
    target_chars: int,
    context_chars: int,
    log_details: str,
) -> None:
    emitters.emit_finalize(runtime, finalize_stage, detail, progress, terminal_kind)
    emitters.emit_activity(runtime, activity_message)
    emitters.emit_log(
        runtime,
        status=log_status,
        block_index=block_index,
        block_count=block_count,
        target_chars=target_chars,
        context_chars=context_chars,
        details=log_details,
    )


def emit_failed_result(
    *,
    emitters: Any,
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
    _emit_terminal_result(
        emitters=emitters,
        runtime=runtime,
        finalize_stage=finalize_stage,
        detail=detail,
        progress=progress,
        terminal_kind="error",
        activity_message=activity_message,
        log_status="ERROR",
        block_index=block_index,
        block_count=block_count,
        target_chars=target_chars,
        context_chars=context_chars,
        log_details=log_details,
    )
    return "failed"


def emit_stopped_result(
    *,
    emitters: Any,
    runtime: object,
    detail: str,
    progress: float,
    block_index: int,
    block_count: int,
) -> PipelineResult:
    _emit_terminal_result(
        emitters=emitters,
        runtime=runtime,
        finalize_stage="Остановлено пользователем",
        detail=detail,
        progress=progress,
        terminal_kind="stopped",
        activity_message=detail,
        log_status="STOP",
        block_index=block_index,
        block_count=block_count,
        target_chars=0,
        context_chars=0,
        log_details=detail,
    )
    return "stopped"


def fail_empty_processing_plan(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
) -> PipelineResult:
    error_message = dependencies.present_error(
        "empty_processing_plan",
        RuntimeError("План обработки документа пуст."),
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
    return emit_failed_result(
        emitters=emitters,
        runtime=context.runtime,
        finalize_stage="Ошибка подготовки обработки",
        detail=error_message,
        progress=0.0,
        activity_message="Обработка документа остановлена: не найдено ни одного блока для обработки.",
        block_index=0,
        block_count=0,
        target_chars=0,
        context_chars=0,
        log_details=error_message,
    )


def run_image_processing_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    current_markdown_fn: Callable[[Sequence[str]], str],
) -> Any | None:
    final_markdown = current_markdown_fn(state.processed_chunks)
    emitters.emit_state(context.runtime, latest_markdown=final_markdown)
    try:
        processed_image_assets = dependencies.process_document_images(
            image_assets=context.image_assets,
            image_mode=context.image_mode,
            config=context.app_config,
            on_progress=context.on_progress,
            runtime=context.runtime,
            client=initialization.client,
        )
        if processed_image_assets is None:
            raise RuntimeError("Пайплайн обработки изображений вернул None вместо коллекции ассетов.")

        normalized_image_assets = list(processed_image_assets)
        placeholder_integrity = dependencies.inspect_placeholder_integrity(final_markdown, normalized_image_assets)
        if not isinstance(placeholder_integrity, Mapping):
            raise TypeError("Проверка целостности placeholder вернула неподдерживаемый тип результата.")

        for asset in normalized_image_assets:
            asset.update_pipeline_metadata(placeholder_status=placeholder_integrity.get(asset.image_id))
    except Exception as exc:
        error_message = dependencies.present_error(
            "image_processing_failed",
            exc,
            "Ошибка обработки изображений",
            filename=context.uploaded_filename,
            final_markdown_chars=len(final_markdown),
            image_count=len(context.image_assets),
            image_mode=context.image_mode,
        )
        emitters.emit_state(
            context.runtime,
            latest_markdown=final_markdown,
            last_error=error_message,
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        emit_failed_result(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Ошибка обработки изображений",
            detail=error_message,
            progress=1.0,
            activity_message="Ошибка на этапе обработки изображений документа.",
            block_index=initialization.job_count,
            block_count=initialization.job_count,
            target_chars=len(final_markdown),
            context_chars=0,
            log_details=error_message,
        )
        return None

    return {
        "processed_image_assets": normalized_image_assets,
        "placeholder_integrity": placeholder_integrity,
    }


def _reconcile_placeholder_integrity(
    placeholder_integrity: Mapping[str, str],
    image_assets: Sequence[Any],
) -> dict[str, str]:
    expected_ids = {asset.image_id for asset in image_assets}
    observed_ids = {image_id for image_id in placeholder_integrity if image_id in expected_ids}
    mismatches = {
        image_id: placeholder_status
        for image_id, placeholder_status in placeholder_integrity.items()
        if placeholder_status != "ok"
    }
    for missing_image_id in sorted(expected_ids - observed_ids):
        mismatches[missing_image_id] = "missing_status"
    return mismatches


def validate_placeholder_integrity_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    final_markdown: str,
    image_phase: Mapping[str, object],
    job_count: int,
) -> bool:
    placeholder_mismatches = _reconcile_placeholder_integrity(
        cast(Mapping[str, str], image_phase["placeholder_integrity"]),
        cast(Sequence[Any], image_phase["processed_image_assets"]),
    )
    for image_id, placeholder_status in placeholder_mismatches.items():
        dependencies.log_event(
            logging.WARNING,
            "image_placeholder_mismatch",
            "Обнаружено нарушение контракта image placeholder.",
            filename=context.uploaded_filename,
            image_id=image_id,
            placeholder_status=placeholder_status,
        )
    if not placeholder_mismatches:
        return True

    mismatch_details = ", ".join(
        f"{image_id}:{placeholder_status}"
        for image_id, placeholder_status in sorted(placeholder_mismatches.items())
    )
    critical_message = dependencies.present_error(
        "image_placeholder_integrity_failed",
        RuntimeError(f"Нарушен контракт placeholder-ов: {mismatch_details}"),
        "Критическая ошибка подготовки изображений",
        filename=context.uploaded_filename,
        mismatch_count=len(placeholder_mismatches),
        mismatch_details=mismatch_details,
    )
    emitters.emit_state(
        context.runtime,
        last_error=critical_message,
        latest_docx_bytes=None,
        latest_narration_text=None,
    )
    emit_failed_result(
        emitters=emitters,
        runtime=context.runtime,
        finalize_stage="Критическая ошибка",
        detail=critical_message,
        progress=1.0,
        activity_message="Сборка DOCX остановлена из-за потери или дублирования image placeholder.",
        block_index=job_count,
        block_count=job_count,
        target_chars=len(final_markdown),
        context_chars=0,
        log_details=critical_message,
    )
    return False


def run_docx_build_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    image_phase: Mapping[str, object],
    job_count: int,
    diagnostics_dir: Path,
    current_markdown_fn: Callable[[Sequence[str]], str],
    call_docx_restorer_with_optional_registry_fn: Callable[[Any, bytes, Any, Any], bytes],
) -> Any | None:
    final_markdown = current_markdown_fn(state.processed_chunks)
    emitters.emit_status(
        context.runtime,
        stage="Сборка DOCX",
        detail="Все блоки готовы. Собираю итоговый DOCX из Markdown.",
        current_block=job_count,
        block_count=job_count,
        target_chars=len(final_markdown),
        context_chars=0,
        progress=1.0,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, "Все блоки готовы. Начата сборка итогового DOCX.")
    context.on_progress(preview_title="Текущий Markdown")
    build_started_at_epoch = time.time()

    try:
        docx_bytes = dependencies.convert_markdown_to_docx_bytes(final_markdown)
        if context.source_paragraphs:
            docx_bytes = call_docx_restorer_with_optional_registry_fn(
                dependencies.preserve_source_paragraph_properties,
                docx_bytes,
                context.source_paragraphs,
                state.generated_paragraph_registry or None,
            )
        processed_image_assets = image_phase["processed_image_assets"]
        if processed_image_assets:
            docx_bytes = dependencies.reinsert_inline_images(docx_bytes, processed_image_assets)
    except Exception as exc:
        error_message = dependencies.present_error(
            "docx_build_failed",
            exc,
            "Ошибка сборки DOCX",
            filename=context.uploaded_filename,
            final_markdown_chars=len(final_markdown),
        )
        emitters.emit_state(
            context.runtime,
            last_error=error_message,
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        emit_failed_result(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Ошибка сборки DOCX",
            detail=error_message,
            progress=1.0,
            activity_message="Ошибка на этапе сборки DOCX.",
            block_index=job_count,
            block_count=job_count,
            target_chars=len(final_markdown),
            context_chars=0,
            log_details=error_message,
        )
        return None

    latest_result_notice: dict[str, str] | None = None
    formatting_diagnostics_artifacts = collect_recent_formatting_diagnostics_artifacts(
        since_epoch_seconds=build_started_at_epoch,
        diagnostics_dir=diagnostics_dir,
    )
    if formatting_diagnostics_artifacts:
        severity, activity_message, user_summary = build_formatting_diagnostics_user_feedback(
            formatting_diagnostics_artifacts
        )
        emitters.emit_activity(context.runtime, activity_message)
        if severity == "INFO":
            latest_result_notice = {"level": "info", "message": user_summary}
        else:
            emitters.emit_log(
                context.runtime,
                status=severity,
                block_index=job_count,
                block_count=job_count,
                target_chars=len(final_markdown),
                context_chars=0,
                details=user_summary,
            )
        dependencies.log_event(
            logging.WARNING,
            "formatting_diagnostics_artifacts_detected",
            "Во время сборки DOCX сохранены formatting diagnostics artifacts.",
            filename=context.uploaded_filename,
            artifact_paths=formatting_diagnostics_artifacts,
        )

    if not docx_bytes:
        critical_message = dependencies.present_error(
            "empty_docx_bytes",
            RuntimeError("Сборка DOCX завершилась без содержимого файла."),
            "Критическая ошибка сборки DOCX",
            filename=context.uploaded_filename,
        )
        emitters.emit_state(
            context.runtime,
            last_error=critical_message,
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        emit_failed_result(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Критическая ошибка",
            detail=critical_message,
            progress=1.0,
            activity_message="DOCX собран без содержимого.",
            block_index=job_count,
            block_count=job_count,
            target_chars=len(final_markdown),
            context_chars=0,
            log_details=critical_message,
        )
        return None

    return {
        "docx_bytes": docx_bytes,
        "latest_result_notice": latest_result_notice,
    }


def finalize_processing_success(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    docx_phase: Mapping[str, object],
    job_count: int,
    current_markdown_fn: Callable[[Sequence[str]], str],
) -> PipelineResult:
    final_markdown = current_markdown_fn(state.processed_chunks)
    try:
        narration_text = _build_narration_text(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
        )
    except Exception as exc:
        error_message = dependencies.present_error(
            "audiobook_postprocess_failed",
            exc,
            "Ошибка подготовки текста для ElevenLabs",
            filename=context.uploaded_filename,
            processing_operation=context.processing_operation,
        )
        emitters.emit_state(
            context.runtime,
            latest_markdown=final_markdown,
            latest_docx_bytes=None,
            latest_narration_text=None,
            last_error=error_message,
        )
        return emit_failed_result(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Ошибка подготовки narration",
            detail=error_message,
            progress=1.0,
            activity_message="Ошибка на этапе подготовки текста для ElevenLabs.",
            block_index=job_count,
            block_count=job_count,
            target_chars=len(final_markdown),
            context_chars=0,
            log_details=error_message,
        )
    emitters.emit_state(
        context.runtime,
        latest_docx_bytes=docx_phase["docx_bytes"],
        latest_markdown=final_markdown,
        latest_narration_text=narration_text,
        latest_result_notice=docx_phase["latest_result_notice"],
        last_error="",
    )
    try:
        artifact_writer_kwargs = {
            "source_name": context.uploaded_filename,
            "markdown_text": final_markdown,
            "docx_bytes": docx_phase["docx_bytes"],
        }
        if narration_text is not None:
            artifact_writer_kwargs["narration_text"] = narration_text
        result_artifact_paths = dict(
            dependencies.write_ui_result_artifacts(**artifact_writer_kwargs)
        )
    except OSError as exc:
        dependencies.log_event(
            logging.WARNING,
            "ui_result_artifacts_save_failed",
            "Не удалось сохранить итоговые UI-артефакты обработки.",
            filename=context.uploaded_filename,
            error_message=str(exc),
        )
    else:
        dependencies.log_event(
            logging.INFO,
            "ui_result_artifacts_saved",
            "Сохранены итоговые UI-артефакты обработки.",
            filename=context.uploaded_filename,
            artifact_paths=result_artifact_paths,
        )
        if narration_text is not None and "tts_text_path" in result_artifact_paths:
            dependencies.log_event(
                logging.INFO,
                "ui_audiobook_artifact_saved",
                "Сохранён итоговый narration artifact для ElevenLabs.",
                filename=context.uploaded_filename,
                source_name=context.uploaded_filename,
                artifact_paths=result_artifact_paths,
                tts_text_path=result_artifact_paths["tts_text_path"],
                char_count=len(narration_text),
                tag_count=len(_ELEVENLABS_TAG_PATTERN.findall(narration_text)),
                excluded_blocks=int(getattr(state, "excluded_narration_block_count", 0) or 0),
                mode="standalone" if context.processing_operation == "audiobook" else "postprocess",
            )
    emitters.emit_finalize(
        context.runtime,
        "Обработка завершена",
        f"Документ обработан за {time.perf_counter() - state.started_at:.1f} сек.",
        1.0,
        "completed",
    )
    emitters.emit_activity(context.runtime, "Документ обработан полностью.")
    dependencies.log_event(
        logging.INFO,
        "processing_completed",
        "Документ обработан полностью",
        filename=context.uploaded_filename,
        block_count=job_count,
        final_markdown_chars=len(final_markdown),
        narration_chars=len(narration_text or ""),
        elapsed_seconds=round(time.perf_counter() - state.started_at, 2),
        translation_second_pass_enabled=_is_translation_second_pass_effectively_enabled(context=context),
        audiobook_postprocess_enabled=_should_run_audiobook_postprocess(context=context),
    )
    emitters.emit_log(
        context.runtime,
        status="DONE",
        block_index=job_count,
        block_count=job_count,
        target_chars=len(final_markdown),
        context_chars=0,
        details=f"весь документ обработан за {time.perf_counter() - state.started_at:.1f} сек.",
    )
    return "succeeded"


def _build_narration_text(*, context: Any, dependencies: Any, emitters: Any, state: Any) -> str | None:
    if context.processing_operation != "audiobook":
        if not _should_run_audiobook_postprocess(context=context):
            return None
        return _run_audiobook_postprocess(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
        )
    narration_source = "\n\n".join(_collect_narration_chunks(state=state))
    if not narration_source:
        return None
    return strip_markdown_for_narration(narration_source)


def _should_run_audiobook_postprocess(*, context: Any) -> bool:
    return context.processing_operation in {"edit", "translate"} and bool(
        context.app_config.get("audiobook_postprocess_enabled", False)
    )


def _is_translation_second_pass_effectively_enabled(*, context: Any) -> bool:
    return context.processing_operation == "translate" and bool(
        context.app_config.get("translation_second_pass_enabled", False)
    )


def _collect_narration_chunks(*, state: Any) -> list[str]:
    return [str(chunk).strip() for chunk in getattr(state, "narration_chunks", []) if str(chunk).strip()]


def _resolve_audiobook_postprocess_model(*, context: Any) -> str:
    configured_model = str(context.app_config.get("audiobook_model", "")).strip()
    return configured_model or context.model


def _resolve_audiobook_postprocess_chunk_size(*, context: Any) -> int:
    configured_chunk_size = context.app_config.get("chunk_size", 6000)
    try:
        return max(int(configured_chunk_size), 3000)
    except (TypeError, ValueError):
        return 6000


def _build_narration_postprocess_groups(*, narration_chunks: Sequence[str], chunk_size: int) -> list[dict[str, object]]:
    if not narration_chunks:
        return []

    groups: list[dict[str, object]] = []
    group_start = 0
    current_chunks: list[str] = []
    current_chars = 0

    for chunk_index, chunk in enumerate(narration_chunks):
        chunk_chars = len(chunk)
        separator_chars = 2 if current_chunks else 0
        if current_chunks and current_chars + separator_chars + chunk_chars > chunk_size:
            group_end = group_start + len(current_chunks) - 1
            groups.append(
                {
                    "group_index": len(groups) + 1,
                    "start_index": group_start,
                    "end_index": group_end,
                    "target_text": "\n\n".join(current_chunks),
                    "context_before": narration_chunks[group_start - 1] if group_start > 0 else "",
                    "context_after": narration_chunks[group_end + 1] if group_end + 1 < len(narration_chunks) else "",
                }
            )
            group_start = chunk_index
            current_chunks = [chunk]
            current_chars = chunk_chars
            continue

        current_chunks.append(chunk)
        current_chars += separator_chars + chunk_chars

    if current_chunks:
        group_end = group_start + len(current_chunks) - 1
        groups.append(
            {
                "group_index": len(groups) + 1,
                "start_index": group_start,
                "end_index": group_end,
                "target_text": "\n\n".join(current_chunks),
                "context_before": narration_chunks[group_start - 1] if group_start > 0 else "",
                "context_after": narration_chunks[group_end + 1] if group_end + 1 < len(narration_chunks) else "",
            }
        )

    return groups


def _run_audiobook_postprocess(*, context: Any, dependencies: Any, emitters: Any, state: Any) -> str | None:
    narration_chunks = _collect_narration_chunks(state=state)
    if not narration_chunks:
        return None

    system_prompt = dependencies.load_system_prompt(
        operation="audiobook",
        source_language=context.source_language,
        target_language=context.target_language,
        editorial_intensity=str(context.app_config.get("editorial_intensity_default", "literary")),
        prompt_variant="default",
    )
    model = _resolve_audiobook_postprocess_model(context=context)
    client = dependencies.get_client()
    groups = _build_narration_postprocess_groups(
        narration_chunks=narration_chunks,
        chunk_size=_resolve_audiobook_postprocess_chunk_size(context=context),
    )

    emitters.emit_status(
        context.runtime,
        stage="Подготовка narration",
        detail="Запущен отдельный audiobook post-pass для текста ElevenLabs.",
        current_block=len(state.processed_chunks),
        block_count=max(len(state.processed_chunks), 1),
        target_chars=sum(len(chunk) for chunk in narration_chunks),
        context_chars=0,
        progress=1.0,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, "Запущена отдельная подготовка narration text для ElevenLabs.")

    processed_groups: list[str] = []
    for group in groups:
        target_text = str(group["target_text"])
        context_before = str(group["context_before"])
        context_after = str(group["context_after"])
        group_index = int(group["group_index"])
        dependencies.log_event(
            logging.INFO,
            "audiobook_postprocess_chunk_started",
            "Запущен audiobook post-pass для narration chunk group.",
            filename=context.uploaded_filename,
            operation="audiobook",
            **{"pass": "postprocess"},
            model=model,
            chunk_index=group_index,
            chunk_count=len(groups),
            target_chars=len(target_text),
            context_before_chars=len(context_before),
            context_after_chars=len(context_after),
            start_index=int(group["start_index"]),
            end_index=int(group["end_index"]),
        )
        processed_chunk = dependencies.generate_markdown_block(
            client=client,
            model=model,
            system_prompt=system_prompt,
            target_text=target_text,
            context_before=context_before,
            context_after=context_after,
            max_retries=context.max_retries,
            expected_paragraph_ids=None,
            marker_mode=False,
        )
        processed_groups.append(processed_chunk)
        dependencies.log_event(
            logging.INFO,
            "audiobook_postprocess_chunk_completed",
            "Audiobook post-pass для narration chunk group завершён.",
            filename=context.uploaded_filename,
            operation="audiobook",
            **{"pass": "postprocess"},
            model=model,
            chunk_index=group_index,
            chunk_count=len(groups),
            output_chars=len(processed_chunk),
        )

    emitters.emit_activity(context.runtime, "Подготовка narration text для ElevenLabs завершена.")
    return strip_markdown_for_narration("\n\n".join(processed_groups))
