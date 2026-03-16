import logging
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence, Sized
from typing import Literal, Protocol, TypeAlias


JobValue: TypeAlias = str | int
ProcessingJob: TypeAlias = Mapping[str, JobValue]
PipelineResult: TypeAlias = Literal["succeeded", "failed", "stopped"]


class ParagraphLike(Protocol):
    role: str


class ImageAssetLike(Protocol):
    image_id: str

    def update_pipeline_metadata(self, **values: object) -> None: ...


class ProgressCallback(Protocol):
    def __call__(self, *, preview_title: str) -> None: ...


class FilenameResolver(Protocol):
    def __call__(self, uploaded_file: object) -> str: ...


class ClientFactory(Protocol):
    def __call__(self) -> object: ...


class SystemPromptLoader(Protocol):
    def __call__(self) -> str: ...


class EventLogger(Protocol):
    def __call__(self, level: int, event_id: str, message: str, **context: object) -> None: ...


class ErrorPresenter(Protocol):
    def __call__(self, code: str, exc: Exception, title: str, **context: object) -> str: ...


class StateEmitter(Protocol):
    def __call__(self, runtime: object, **values: object) -> None: ...


class FinalizeEmitter(Protocol):
    def __call__(self, runtime: object, stage: str, detail: str, progress: float) -> None: ...


class ActivityEmitter(Protocol):
    def __call__(self, runtime: object, message: str) -> None: ...


class LogEmitter(Protocol):
    def __call__(self, runtime: object, **payload: object) -> None: ...


class StatusEmitter(Protocol):
    def __call__(self, runtime: object, **payload: object) -> None: ...


class StopPredicate(Protocol):
    def __call__(self, runtime: object) -> bool: ...


class MarkdownGenerator(Protocol):
    def __call__(
        self,
        *,
        client: object,
        model: str,
        system_prompt: str,
        target_text: str,
        context_before: str,
        context_after: str,
        max_retries: int,
    ) -> str: ...


class ImageProcessor(Protocol):
    def __call__(
        self,
        *,
        image_assets: Sequence[ImageAssetLike],
        image_mode: str,
        config: Mapping[str, object],
        on_progress: ProgressCallback,
        runtime: object,
        client: object,
    ) -> Iterable[ImageAssetLike] | None: ...


class PlaceholderInspector(Protocol):
    def __call__(self, markdown_text: str, image_assets: Sequence[ImageAssetLike]) -> Mapping[str, str]: ...


class MarkdownToDocxConverter(Protocol):
    def __call__(self, markdown_text: str) -> bytes: ...


class ParagraphPropertiesPreserver(Protocol):
    def __call__(self, docx_bytes: bytes, paragraphs: Sequence[ParagraphLike]) -> bytes: ...


class SemanticDocxNormalizer(Protocol):
    def __call__(self, docx_bytes: bytes, paragraphs: Sequence[ParagraphLike]) -> bytes: ...


class ImageReinserter(Protocol):
    def __call__(self, docx_bytes: bytes, image_assets: Sequence[ImageAssetLike]) -> bytes: ...


class ProcessingJobs(Sized, Protocol):
    def __iter__(self) -> Iterator[ProcessingJob]: ...


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
    normalize_semantic_output_docx: SemanticDocxNormalizer,
    reinsert_inline_images: ImageReinserter,
) -> PipelineResult:
    uploaded_filename = resolve_uploaded_filename(uploaded_file)
    try:
        job_count = len(jobs)
    except Exception as exc:
        error_message = present_error(
            "invalid_processing_plan",
            exc,
            "Ошибка подготовки обработки",
            filename=uploaded_filename,
        )
        emit_state(
            runtime,
            last_error=error_message,
            latest_markdown="",
            processed_block_markdowns=[],
            latest_docx_bytes=None,
        )
        emit_finalize(runtime, "Ошибка подготовки обработки", error_message, 0.0)
        emit_activity(runtime, "Обработка документа остановлена: план обработки некорректен.")
        emit_log(
            runtime,
            status="ERROR",
            block_index=0,
            block_count=0,
            target_chars=0,
            context_chars=0,
            details=error_message,
        )
        return "failed"

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
            block_count=job_count,
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
        emit_state(
            runtime,
            last_error=error_message,
            latest_markdown="",
            processed_block_markdowns=[],
            latest_docx_bytes=None,
        )
        emit_finalize(runtime, "Ошибка инициализации", error_message, 0.0)
        return "failed"

    if job_count == 0:
        error_message = present_error(
            'empty_processing_plan',
            RuntimeError('План обработки документа пуст.'),
            'Ошибка подготовки обработки',
            filename=uploaded_filename,
        )
        emit_state(
            runtime,
            last_error=error_message,
            latest_markdown='',
            processed_block_markdowns=[],
            latest_docx_bytes=None,
        )
        emit_finalize(runtime, 'Ошибка подготовки обработки', error_message, 0.0)
        emit_activity(runtime, 'Обработка документа остановлена: не найдено ни одного блока для обработки.')
        emit_log(
            runtime,
            status='ERROR',
            block_index=0,
            block_count=0,
            target_chars=0,
            context_chars=0,
            details=error_message,
        )
        return 'failed'

    processed_chunks: list[str] = []
    started_at = time.perf_counter()

    for index, job in enumerate(jobs, start=1):
        if should_stop_processing(runtime):
            stop_message = "Обработка остановлена пользователем."
            emit_finalize(runtime, "Остановлено пользователем", stop_message, (index - 1) / job_count)
            emit_activity(runtime, stop_message)
            emit_log(
                runtime,
                status="STOP",
                block_index=max(0, index - 1),
                block_count=job_count,
                target_chars=0,
                context_chars=0,
                details=stop_message,
            )
            return "stopped"

        try:
            target_chars = int(job["target_chars"])
            context_chars = int(job["context_chars"])
            target_text = str(job["target_text"])
            context_before = str(job["context_before"])
            context_after = str(job["context_after"])
        except (KeyError, TypeError, ValueError) as exc:
            emit_state(runtime, latest_markdown="\n\n".join(processed_chunks).strip(), latest_docx_bytes=None)
            error_message = present_error(
                "invalid_processing_job",
                exc,
                "Ошибка подготовки блока",
                filename=uploaded_filename,
                block_index=index,
                block_count=job_count,
                model=model,
            )
            formatted_error = f"Ошибка на блоке {index}: {error_message}"
            emit_state(runtime, last_error=formatted_error, latest_docx_bytes=None)
            emit_finalize(runtime, "Ошибка подготовки блока", formatted_error, (index - 1) / job_count)
            emit_activity(runtime, f"Блок {index}: некорректный план обработки.")
            emit_log(
                runtime,
                status="ERROR",
                block_index=index,
                block_count=job_count,
                target_chars=0,
                context_chars=0,
                details=error_message,
            )
            return "failed"

        emit_status(
            runtime,
            stage="Подготовка блока",
            detail=f"Готовлю блок {index} из {job_count} к отправке в OpenAI.",
            current_block=index,
            block_count=job_count,
            target_chars=target_chars,
            context_chars=context_chars,
            progress=(index - 1) / job_count,
            is_running=True,
        )
        emit_activity(runtime, f"Начата обработка блока {index} из {job_count}.")
        log_event(
            logging.INFO,
            "block_started",
            "Начата обработка блока",
            filename=uploaded_filename,
            block_index=index,
            block_count=job_count,
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
                block_count=job_count,
                target_chars=target_chars,
                context_chars=context_chars,
                progress=(index - 1) / job_count,
                is_running=True,
            )
            emit_activity(runtime, f"Блок {index} отправлен в OpenAI.")
            on_progress(preview_title="Текущий Markdown")
            processed_chunk = generate_markdown_block(
                client=client,
                model=model,
                system_prompt=system_prompt,
                target_text=target_text,
                context_before=context_before,
                context_after=context_after,
                max_retries=max_retries,
            )
        except Exception as exc:
            emit_state(runtime, latest_markdown="\n\n".join(processed_chunks).strip(), latest_docx_bytes=None)
            error_message = present_error(
                "block_failed",
                exc,
                "Ошибка обработки блока",
                filename=uploaded_filename,
                block_index=index,
                block_count=job_count,
                target_chars=target_chars,
                context_chars=context_chars,
                model=model,
            )
            formatted_error = f"Ошибка на блоке {index}: {error_message}"
            emit_state(runtime, last_error=formatted_error, latest_docx_bytes=None)
            emit_finalize(runtime, "Ошибка обработки", formatted_error, (index - 1) / job_count)
            emit_activity(runtime, f"Блок {index}: ошибка обработки.")
            emit_log(
                runtime,
                status="ERROR",
                block_index=index,
                block_count=job_count,
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
            emit_state(runtime, last_error=formatted_error, latest_docx_bytes=None)
            emit_finalize(runtime, "Критическая ошибка", formatted_error, (index - 1) / job_count)
            emit_activity(runtime, f"Блок {index}: модель вернула пустой Markdown.")
            emit_log(
                runtime,
                status="ERROR",
                block_index=index,
                block_count=job_count,
                target_chars=target_chars,
                context_chars=context_chars,
                details=critical_message,
            )
            return "failed"

        processed_chunks.append(processed_chunk)
        emit_state(
            runtime,
            processed_block_markdowns=processed_chunks.copy(),
            latest_markdown="\n\n".join(processed_chunks).strip(),
        )
        emit_log(
            runtime,
            status="OK",
            block_index=index,
            block_count=job_count,
            target_chars=target_chars,
            context_chars=context_chars,
            details=f"готово за {time.perf_counter() - started_at:.1f} сек. с начала запуска",
        )
        emit_status(
            runtime,
            stage="Блок обработан",
            detail=f"Получен ответ для блока {index}. Обновляю промежуточный Markdown.",
            current_block=index,
            block_count=job_count,
            target_chars=target_chars,
            context_chars=context_chars,
            progress=index / job_count,
            is_running=True,
        )
        emit_activity(runtime, f"Блок {index} обработан успешно.")
        log_event(
            logging.INFO,
            "block_completed",
            "Блок обработан успешно",
            filename=uploaded_filename,
            block_index=index,
            block_count=job_count,
            target_chars=int(job["target_chars"]),
            context_chars=int(job["context_chars"]),
            output_chars=len(processed_chunk),
        )
        on_progress(preview_title="Текущий Markdown")

    if len(processed_chunks) != job_count:
        critical_message = present_error(
            "processed_block_count_mismatch",
            RuntimeError("Количество обработанных блоков не совпало с планом обработки."),
            "Критическая ошибка финализации",
            filename=uploaded_filename,
            processed_count=len(processed_chunks),
            planned_count=job_count,
        )
        emit_state(runtime, last_error=critical_message, latest_docx_bytes=None)
        emit_finalize(runtime, "Критическая ошибка", critical_message, len(processed_chunks) / job_count)
        emit_activity(runtime, "Обнаружено несоответствие количества обработанных блоков.")
        emit_log(
            runtime,
            status="ERROR",
            block_index=len(processed_chunks),
            block_count=job_count,
            target_chars=len("\n\n".join(processed_chunks).strip()),
            context_chars=0,
            details=critical_message,
        )
        return "failed"

    final_markdown = "\n\n".join(processed_chunks).strip()
    emit_state(runtime, latest_markdown=final_markdown)
    try:
        processed_image_assets = process_document_images(
            image_assets=image_assets,
            image_mode=image_mode,
            config=app_config,
            on_progress=on_progress,
            runtime=runtime,
            client=client,
        )
        if processed_image_assets is None:
            raise RuntimeError("Пайплайн обработки изображений вернул None вместо коллекции ассетов.")

        processed_image_assets = list(processed_image_assets)
        placeholder_integrity = inspect_placeholder_integrity(final_markdown, processed_image_assets)
        if not isinstance(placeholder_integrity, Mapping):
            raise TypeError("Проверка целостности placeholder вернула неподдерживаемый тип результата.")

        for asset in processed_image_assets:
            asset.update_pipeline_metadata(placeholder_status=placeholder_integrity.get(asset.image_id))
    except Exception as exc:
        error_message = present_error(
            "image_processing_failed",
            exc,
            "Ошибка обработки изображений",
            filename=uploaded_filename,
            final_markdown_chars=len(final_markdown),
            image_count=len(image_assets),
            image_mode=image_mode,
        )
        emit_state(runtime, latest_markdown=final_markdown, last_error=error_message, latest_docx_bytes=None)
        emit_finalize(runtime, "Ошибка обработки изображений", error_message, 1.0)
        emit_activity(runtime, "Ошибка на этапе обработки изображений документа.")
        emit_log(
            runtime,
            status="ERROR",
            block_index=job_count,
            block_count=job_count,
            target_chars=len(final_markdown),
            context_chars=0,
            details=error_message,
        )
        return "failed"
    if should_stop_processing(runtime):
        emit_finalize(runtime, "Остановлено пользователем", "Обработка остановлена пользователем.", 1.0)
        emit_activity(runtime, "Обработка документа остановлена пользователем.")
        return "stopped"

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
        emit_state(runtime, last_error=critical_message, latest_docx_bytes=None)
        emit_finalize(runtime, "Критическая ошибка", critical_message, 1.0)
        emit_activity(runtime, "Сборка DOCX остановлена из-за потери или дублирования image placeholder.")
        emit_log(
            runtime,
            status="ERROR",
            block_index=job_count,
            block_count=job_count,
            target_chars=len(final_markdown),
            context_chars=0,
            details=critical_message,
        )
        return "failed"
    emit_status(
        runtime,
        stage="Сборка DOCX",
        detail="Все блоки готовы. Собираю итоговый DOCX из Markdown.",
        current_block=job_count,
        block_count=job_count,
        target_chars=len(final_markdown),
        context_chars=0,
        progress=1.0,
        is_running=True,
    )
    emit_activity(runtime, "Все блоки готовы. Начата сборка итогового DOCX.")
    on_progress(preview_title="Текущий Markdown")

    try:
        docx_bytes = convert_markdown_to_docx_bytes(final_markdown)
        if source_paragraphs:
            docx_bytes = preserve_source_paragraph_properties(docx_bytes, source_paragraphs)
            docx_bytes = normalize_semantic_output_docx(docx_bytes, source_paragraphs)
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
        emit_state(runtime, last_error=error_message, latest_docx_bytes=None)
        emit_finalize(runtime, "Ошибка сборки DOCX", error_message, 1.0)
        emit_activity(runtime, "Ошибка на этапе сборки DOCX.")
        emit_log(
            runtime,
            status="ERROR",
            block_index=job_count,
            block_count=job_count,
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
        emit_state(runtime, last_error=critical_message, latest_docx_bytes=None)
        emit_finalize(runtime, "Критическая ошибка", critical_message, 1.0)
        emit_activity(runtime, "DOCX собран без содержимого.")
        emit_log(
            runtime,
            status="ERROR",
            block_index=job_count,
            block_count=job_count,
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
        block_count=job_count,
        final_markdown_chars=len(final_markdown),
        elapsed_seconds=round(time.perf_counter() - started_at, 2),
    )
    emit_log(
        runtime,
        status="DONE",
        block_index=job_count,
        block_count=job_count,
        target_chars=len(final_markdown),
        context_chars=0,
        details=f"весь документ обработан за {time.perf_counter() - started_at:.1f} сек.",
    )
    return "succeeded"
