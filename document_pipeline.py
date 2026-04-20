import logging
import json
import inspect
import re
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence, Sized
from pathlib import Path
from typing import Literal, Protocol, TypeAlias

from formatting_diagnostics_retention import (
    collect_recent_formatting_diagnostics,
    get_formatting_diagnostics_dir,
    load_formatting_diagnostics_payloads,
    write_formatting_diagnostics_artifact,
)
from runtime_artifacts import write_ui_result_artifacts as write_ui_result_artifacts_impl


JobValue: TypeAlias = object
ProcessingJob: TypeAlias = Mapping[str, JobValue]
PipelineResult: TypeAlias = Literal["succeeded", "failed", "stopped"]
ProcessedBlockStatus: TypeAlias = Literal["valid", "empty", "heading_only_output"]
FORMATTING_DIAGNOSTICS_DIR = get_formatting_diagnostics_dir()


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
    def __call__(self, *, operation: str = "edit", source_language: str = "en", target_language: str = "ru") -> str: ...


class EventLogger(Protocol):
    def __call__(self, level: int, event_id: str, message: str, **context: object) -> None: ...


class ErrorPresenter(Protocol):
    def __call__(self, code: str, exc: Exception, title: str, **context: object) -> str: ...


class StateEmitter(Protocol):
    def __call__(self, runtime: object, **values: object) -> None: ...


class FinalizeEmitter(Protocol):
    def __call__(self, runtime: object, stage: str, detail: str, progress: float, terminal_kind: str | None = None) -> None: ...


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
        expected_paragraph_ids: Sequence[str] | None = None,
        marker_mode: bool = False,
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
    def __call__(
        self,
        docx_bytes: bytes,
        paragraphs: Sequence[ParagraphLike],
        generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
    ) -> bytes: ...


class SemanticDocxNormalizer(Protocol):
    def __call__(
        self,
        docx_bytes: bytes,
        paragraphs: Sequence[ParagraphLike],
        generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
    ) -> bytes: ...


class ImageReinserter(Protocol):
    def __call__(self, docx_bytes: bytes, image_assets: Sequence[ImageAssetLike]) -> bytes: ...


class ResultArtifactWriter(Protocol):
    def __call__(self, *, source_name: str, markdown_text: str, docx_bytes: bytes) -> Mapping[str, str]: ...


class ProcessingJobs(Sized, Protocol):
    def __iter__(self) -> Iterator[ProcessingJob]: ...


def _coerce_required_text_field(job: ProcessingJob, field_name: str, *, allow_blank: bool = True) -> str:
    value = job[field_name]
    if value is None:
        raise ValueError(f"{field_name} is None")
    text = str(value)
    if not allow_blank and not text.strip():
        raise ValueError(f"{field_name} is empty")
    return text


def _coerce_optional_string_list(job: ProcessingJob, field_name: str) -> list[str] | None:
    value = job.get(field_name)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise TypeError(f"{field_name} must be a non-empty string list")
    return list(value)


def _coerce_optional_text_field(job: ProcessingJob, field_name: str) -> str | None:
    value = job.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _coerce_required_int_field(job: ProcessingJob, field_name: str) -> int:
    value = job[field_name]
    if value is None:
        raise ValueError(f"{field_name} is None")
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"{field_name} must be an integer or numeric string")


def _coerce_job_kind(job: ProcessingJob) -> str:
    value = job.get("job_kind", "llm")
    if not isinstance(value, str):
        raise TypeError("job_kind must be a string")
    normalized = value.strip() or "llm"
    if normalized not in {"llm", "passthrough"}:
        raise ValueError(f"Unsupported job_kind: {normalized}")
    return normalized


def _resolve_system_prompt(
    load_system_prompt: SystemPromptLoader,
    *,
    operation: str,
    source_language: str,
    target_language: str,
) -> str:
    try:
        signature = inspect.signature(load_system_prompt)
    except (TypeError, ValueError):
        signature = None

    if signature is None:
        return load_system_prompt(
            operation=operation,
            source_language=source_language,
            target_language=target_language,
        )

    parameters = signature.parameters.values()
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return load_system_prompt(
            operation=operation,
            source_language=source_language,
            target_language=target_language,
        )

    parameter_names = {parameter.name for parameter in parameters}
    if {"operation", "source_language", "target_language"}.issubset(parameter_names):
        return load_system_prompt(
            operation=operation,
            source_language=source_language,
            target_language=target_language,
        )

    return load_system_prompt()


def _iter_nonempty_markdown_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_markdown_heading_line(line: str) -> bool:
    return bool(re.match(r"#{1,6}\s+\S", line))


def _is_heading_only_markdown(text: str) -> bool:
    nonempty_lines = _iter_nonempty_markdown_lines(text)
    return bool(nonempty_lines) and all(_is_markdown_heading_line(line) for line in nonempty_lines)


def _is_heading_like_alpha_token(token: str) -> bool:
    stripped = token.strip("\"'“”‘’()[]{}<>«»,-—–:;,.!?")
    if not stripped:
        return False

    alpha_chars = [char for char in stripped if char.isalpha()]
    if not alpha_chars:
        return False

    if all(char.isupper() for char in alpha_chars):
        return True

    for char in stripped:
        if char.isalpha():
            return char.isupper()
    return False


def _is_plaintext_heading_like_line(line: str) -> bool:
    if any(symbol in line for symbol in ".!?;"):
        return False

    tokens = [token for token in re.split(r"[\s\t]+", line.strip()) if token]
    alpha_tokens = [token for token in tokens if any(char.isalpha() for char in token)]
    if not alpha_tokens or len(alpha_tokens) > 14:
        return False

    letters = [char for char in line if char.isalpha()]
    if not letters:
        return False

    uppercase_letters = [char for char in letters if char.isupper()]
    uppercase_ratio = len(uppercase_letters) / len(letters)
    heading_like_token_ratio = sum(1 for token in alpha_tokens if _is_heading_like_alpha_token(token)) / len(alpha_tokens)
    if line.count(":") == 1:
        prefix, suffix = [part.strip() for part in line.split(":", maxsplit=1)]
        prefix_tokens = [token for token in re.split(r"[\s\t]+", prefix) if any(char.isalpha() for char in token)]
        suffix_tokens = [token for token in re.split(r"[\s\t]+", suffix) if any(char.isalpha() for char in token)]
        if (
            prefix_tokens
            and suffix_tokens
            and len(prefix_tokens) <= 4
            and len(suffix_tokens) <= 8
            and all(_is_heading_like_alpha_token(token) for token in prefix_tokens)
        ):
            return True
    if "\t" in line and uppercase_ratio >= 0.6:
        return True
    if uppercase_ratio >= 0.6:
        return True
    if heading_like_token_ratio >= 0.8:
        return True
    return False


def _input_has_body_text_signal(text: str) -> bool:
    nonempty_lines = _iter_nonempty_markdown_lines(text)
    body_lines = [line for line in nonempty_lines if not _is_markdown_heading_line(line)]
    if not body_lines:
        return False
    if len(body_lines) >= 2:
        return True
    body_line = body_lines[0]
    if _is_plaintext_heading_like_line(body_line):
        return False
    if len(body_line) >= 40:
        return True
    if len(body_line.split()) >= 5 and any(symbol in body_line for symbol in ".,;:!?"):
        return True
    return False


def _classify_processed_block(target_text: str, processed_chunk: str) -> ProcessedBlockStatus:
    if not processed_chunk.strip():
        return "empty"
    if _is_heading_only_markdown(processed_chunk) and _input_has_body_text_signal(target_text):
        return "heading_only_output"
    return "valid"


def _reconcile_placeholder_integrity(
    placeholder_integrity: Mapping[str, str],
    image_assets: Sequence[ImageAssetLike],
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


def _collect_recent_formatting_diagnostics(*, since_epoch_seconds: float) -> list[str]:
    return collect_recent_formatting_diagnostics(
        since_epoch_seconds=since_epoch_seconds,
        diagnostics_dir=FORMATTING_DIAGNOSTICS_DIR,
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


def _build_formatting_diagnostics_user_feedback(artifact_paths: Sequence[str]) -> tuple[str, str, str]:
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


def _extract_marker_diagnostics_code(exc: Exception) -> str | None:
    message = str(exc)
    marker_prefix = "paragraph_marker_validation_failed:"
    registry_prefix = "paragraph_marker_registry_mismatch:"
    if marker_prefix in message:
        return message.split(marker_prefix, 1)[1].strip() or "unknown_marker_validation_failure"
    if registry_prefix in message:
        return message.split(registry_prefix, 1)[1].strip() or "unknown_marker_registry_failure"
    return None


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
    return write_formatting_diagnostics_artifact(
        stage=stage,
        filename_prefix=f"marker_block_{stage}_{block_index:03d}",
        diagnostics_dir=FORMATTING_DIAGNOSTICS_DIR,
        diagnostics={
            "uploaded_filename": uploaded_filename,
            "block_index": block_index,
            "block_count": block_count,
            "error_code": error_code,
            "paragraph_ids": list(paragraph_ids or []),
            "target_text_preview": target_text[:1000],
            "context_before_preview": context_before[:600],
            "context_after_preview": context_after[:600],
            "processed_chunk_preview": (processed_chunk or "")[:1000],
        },
    )


def _summarize_block_plan(jobs: ProcessingJobs) -> dict[str, object]:
    block_sizes: list[int] = []
    job_kinds: dict[str, int] = {"llm": 0, "passthrough": 0}
    first_block_sizes: list[int] = []

    for block_job in jobs:
        try:
            target_chars = _coerce_required_int_field(block_job, "target_chars")
        except (KeyError, TypeError, ValueError):
            target_chars = -1
        block_sizes.append(target_chars)
        if len(first_block_sizes) < 5:
            first_block_sizes.append(target_chars)
        try:
            job_kind = _coerce_job_kind(block_job)
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
                "job_kind": _coerce_job_kind(block_job) if isinstance(block_job, Mapping) else "llm",
                "preview": str(block_job.get("target_text", ""))[:120] if isinstance(block_job, Mapping) else "",
            }
            for block_index, block_job in enumerate(jobs, start=1)
        ],
    }


def _build_processed_paragraph_registry_entries(*, block_index: int, paragraph_ids: Sequence[str], processed_chunk: str) -> list[dict[str, object]]:
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


def _call_docx_restorer_with_optional_registry(restorer, docx_bytes: bytes, paragraphs, generated_paragraph_registry):
    try:
        return restorer(
            docx_bytes,
            paragraphs,
            generated_paragraph_registry=generated_paragraph_registry,
        )
    except TypeError as exc:
        if "generated_paragraph_registry" not in str(exc):
            raise
        return restorer(docx_bytes, paragraphs)


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
    normalize_semantic_output_docx: SemanticDocxNormalizer,
    reinsert_inline_images: ImageReinserter,
    write_ui_result_artifacts: ResultArtifactWriter = write_ui_result_artifacts_impl,
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
        emit_finalize(runtime, "Ошибка подготовки обработки", error_message, 0.0, "error")
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
        block_plan_summary = _summarize_block_plan(jobs)
        log_event(
            logging.INFO,
            "block_plan_summary",
            "План блоков документа подготовлен",
            filename=uploaded_filename,
            block_count=block_plan_summary["block_count"],
            llm_block_count=block_plan_summary["llm_block_count"],
            passthrough_block_count=block_plan_summary["passthrough_block_count"],
            total_target_chars=block_plan_summary["total_target_chars"],
            min_target_chars=block_plan_summary["min_target_chars"],
            max_target_chars=block_plan_summary["max_target_chars"],
            avg_target_chars=block_plan_summary["avg_target_chars"],
            first_block_target_chars=block_plan_summary["first_block_target_chars"],
        )
        log_event(
            logging.DEBUG,
            "block_plan_detail",
            "Детальная карта блоков документа подготовлена",
            filename=uploaded_filename,
            blocks=block_plan_summary["blocks"],
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
        emit_finalize(runtime, "Ошибка инициализации", error_message, 0.0, "error")
        return "failed"

    system_prompt: str | None = None

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
        emit_finalize(runtime, 'Ошибка подготовки обработки', error_message, 0.0, "error")
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
    generated_paragraph_registry: list[dict[str, object]] = []
    started_at = time.perf_counter()

    for index, job in enumerate(jobs, start=1):
        if should_stop_processing(runtime):
            stop_message = "Обработка остановлена пользователем."
            emit_finalize(runtime, "Остановлено пользователем", stop_message, (index - 1) / job_count, "stopped")
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
            job_kind = _coerce_job_kind(job)
            target_chars = _coerce_required_int_field(job, "target_chars")
            context_chars = _coerce_required_int_field(job, "context_chars")
            target_text = _coerce_required_text_field(job, "target_text", allow_blank=False)
            target_text_with_markers = _coerce_optional_text_field(job, "target_text_with_markers") or target_text
            paragraph_ids = _coerce_optional_string_list(job, "paragraph_ids")
            context_before = _coerce_required_text_field(job, "context_before")
            context_after = _coerce_required_text_field(job, "context_after")
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
            emit_finalize(runtime, "Ошибка подготовки блока", formatted_error, (index - 1) / job_count, "error")
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
            detail=(
                f"Готовлю блок {index} из {job_count} к отправке в OpenAI."
                if job_kind == "llm"
                else f"Готовлю passthrough-блок {index} из {job_count} без вызова OpenAI."
            ),
            current_block=index,
            block_count=job_count,
            target_chars=target_chars,
            context_chars=context_chars,
            progress=(index - 1) / job_count,
            is_running=True,
        )
        emit_activity(runtime, f"Начата обработка блока {index} из {job_count}.")
        log_event(
            logging.DEBUG,
            "block_started",
            "Начата обработка блока",
            filename=uploaded_filename,
            block_index=index,
            block_count=job_count,
            target_chars=target_chars,
            context_chars=context_chars,
            model=model,
            job_kind=job_kind,
        )
        marker_mode_enabled = False
        try:
            if job_kind == "passthrough":
                emit_status(
                    runtime,
                    stage="Passthrough блока",
                    detail=f"Блок {index} не требует LLM-обработки и будет перенесён в Markdown как есть.",
                    current_block=index,
                    block_count=job_count,
                    target_chars=target_chars,
                    context_chars=context_chars,
                    progress=(index - 1) / job_count,
                    is_running=True,
                )
                emit_activity(runtime, f"Блок {index} пропущен через passthrough без OpenAI.")
                on_progress(preview_title="Текущий Markdown")
                processed_chunk = target_text
            else:
                marker_mode_enabled = bool(app_config.get("enable_paragraph_markers", False)) and bool(paragraph_ids)
                if system_prompt is None:
                    system_prompt = _resolve_system_prompt(
                        load_system_prompt,
                        operation=processing_operation,
                        source_language=source_language,
                        target_language=target_language,
                    )
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
                    target_text=target_text_with_markers if marker_mode_enabled else target_text,
                    context_before=context_before,
                    context_after=context_after,
                    max_retries=max_retries,
                    expected_paragraph_ids=paragraph_ids if marker_mode_enabled else None,
                    marker_mode=marker_mode_enabled,
                )
        except Exception as exc:
            marker_diagnostics_artifact = None
            marker_error_code = _extract_marker_diagnostics_code(exc) if marker_mode_enabled else None
            if marker_error_code is not None:
                marker_diagnostics_artifact = _write_marker_diagnostics_artifact(
                    stage="generation",
                    uploaded_filename=uploaded_filename,
                    block_index=index,
                    block_count=job_count,
                    error_code=marker_error_code,
                    target_text=target_text_with_markers,
                    context_before=context_before,
                    context_after=context_after,
                    paragraph_ids=paragraph_ids,
                )
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
            emit_state(
                runtime,
                last_error=formatted_error,
                latest_docx_bytes=None,
                latest_marker_diagnostics_artifact=marker_diagnostics_artifact,
            )
            emit_finalize(runtime, "Ошибка обработки", formatted_error, (index - 1) / job_count, "error")
            emit_activity(runtime, f"Блок {index}: ошибка обработки.")
            emit_log(
                runtime,
                status="ERROR",
                block_index=index,
                block_count=job_count,
                target_chars=target_chars,
                context_chars=context_chars,
                details=(
                    f"{error_message}; marker diagnostics: {marker_diagnostics_artifact}"
                    if marker_diagnostics_artifact
                    else error_message
                ),
            )
            if marker_diagnostics_artifact is not None:
                log_event(
                    logging.WARNING,
                    "marker_diagnostics_artifact_created",
                    "Сохранён marker diagnostics artifact для блока с ошибкой generation.",
                    filename=uploaded_filename,
                    block_index=index,
                    block_count=job_count,
                    artifact_path=marker_diagnostics_artifact,
                    error_code=marker_error_code,
                )
            return "failed"

        processed_block_status = _classify_processed_block(target_text, processed_chunk)
        if processed_block_status == "empty":
            critical_message = present_error(
                "empty_processed_block",
                RuntimeError("Модель вернула пустой Markdown-блок после успешного вызова (empty_processed_block)."),
                "Критическая ошибка обработки блока",
                filename=uploaded_filename,
                block_index=index,
                output_classification="empty_processed_block",
            )
            formatted_error = f"Ошибка на блоке {index}: {critical_message}"
            emit_state(runtime, last_error=formatted_error, latest_docx_bytes=None)
            emit_finalize(runtime, "Критическая ошибка", formatted_error, (index - 1) / job_count, "error")
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
        if processed_block_status == "heading_only_output":
            critical_message = present_error(
                "structurally_insufficient_processed_block",
                RuntimeError(
                    "Модель вернула только заголовок при наличии основного текста во входном блоке (heading_only_output)."
                ),
                "Критическая ошибка обработки блока",
                filename=uploaded_filename,
                block_index=index,
                output_classification="heading_only_output",
            )
            formatted_error = f"Ошибка на блоке {index}: {critical_message}"
            emit_state(runtime, last_error=formatted_error, latest_docx_bytes=None)
            emit_finalize(runtime, "Критическая ошибка", formatted_error, (index - 1) / job_count, "error")
            emit_activity(runtime, f"Блок {index}: отклонён структурно недостаточный Markdown.")
            emit_log(
                runtime,
                status="ERROR",
                block_index=index,
                block_count=job_count,
                target_chars=target_chars,
                context_chars=context_chars,
                details=critical_message,
            )
            log_event(
                logging.WARNING,
                "block_rejected",
                "Блок отклонён по acceptance-контракту",
                filename=uploaded_filename,
                block_index=index,
                block_count=job_count,
                target_chars=target_chars,
                context_chars=context_chars,
                output_classification="heading_only_output",
                input_preview=target_text[:300],
                output_preview=processed_chunk[:300],
            )
            return "failed"

        processed_chunks.append(processed_chunk)
        if job_kind == "llm" and marker_mode_enabled and paragraph_ids:
            try:
                generated_paragraph_registry.extend(
                    _build_processed_paragraph_registry_entries(
                        block_index=index,
                        paragraph_ids=paragraph_ids,
                        processed_chunk=processed_chunk,
                    )
                )
                log_event(
                    logging.DEBUG,
                    "block_marker_registry_built",
                    "Для блока собран marker-aware paragraph registry.",
                    filename=uploaded_filename,
                    block_index=index,
                    block_count=job_count,
                    paragraph_count=len(paragraph_ids),
                )
            except Exception as exc:
                marker_diagnostics_artifact = _write_marker_diagnostics_artifact(
                    stage="registry",
                    uploaded_filename=uploaded_filename,
                    block_index=index,
                    block_count=job_count,
                    error_code=_extract_marker_diagnostics_code(exc) or "marker_registry_build_failed",
                    target_text=target_text_with_markers,
                    context_before=context_before,
                    context_after=context_after,
                    paragraph_ids=paragraph_ids,
                    processed_chunk=processed_chunk,
                )
                emit_state(runtime, latest_markdown="\n\n".join(processed_chunks).strip(), latest_docx_bytes=None)
                error_message = present_error(
                    "block_marker_registry_failed",
                    exc,
                    "Ошибка marker-реестра блока",
                    filename=uploaded_filename,
                    block_index=index,
                    block_count=job_count,
                )
                formatted_error = f"Ошибка на блоке {index}: {error_message}"
                emit_state(
                    runtime,
                    last_error=formatted_error,
                    latest_docx_bytes=None,
                    latest_marker_diagnostics_artifact=marker_diagnostics_artifact,
                )
                emit_finalize(runtime, "Ошибка marker-реестра", formatted_error, index / job_count, "error")
                emit_activity(runtime, f"Блок {index}: не удалось собрать marker-aware paragraph registry.")
                emit_log(
                    runtime,
                    status="ERROR",
                    block_index=index,
                    block_count=job_count,
                    target_chars=target_chars,
                    context_chars=context_chars,
                    details=(
                        f"{error_message}; marker diagnostics: {marker_diagnostics_artifact}"
                        if marker_diagnostics_artifact
                        else error_message
                    ),
                )
                if marker_diagnostics_artifact is not None:
                    log_event(
                        logging.WARNING,
                        "marker_diagnostics_artifact_created",
                        "Сохранён marker diagnostics artifact для блока с ошибкой registry build.",
                        filename=uploaded_filename,
                        block_index=index,
                        block_count=job_count,
                        artifact_path=marker_diagnostics_artifact,
                    )
                return "failed"
        emit_state(
            runtime,
            processed_block_markdowns=processed_chunks.copy(),
            latest_markdown="\n\n".join(processed_chunks).strip(),
            processed_paragraph_registry=generated_paragraph_registry.copy(),
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
        output_chars = len(processed_chunk)
        output_ratio = round(output_chars / max(target_chars, 1), 2)
        log_event(
            logging.DEBUG,
            "block_completed",
            "Блок обработан успешно",
            filename=uploaded_filename,
            block_index=index,
            block_count=job_count,
            target_chars=target_chars,
            context_chars=context_chars,
            output_chars=output_chars,
            output_ratio=output_ratio,
            input_preview=target_text[:300],
            output_preview=processed_chunk[:300],
            job_kind=job_kind,
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
            incomplete_count=max(job_count - len(processed_chunks), 0),
        )
        emit_state(runtime, last_error=critical_message, latest_docx_bytes=None)
        emit_finalize(runtime, "Критическая ошибка", critical_message, len(processed_chunks) / max(job_count, 1), "error")
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
        emit_finalize(runtime, "Ошибка обработки изображений", error_message, 1.0, "error")
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
        emit_finalize(runtime, "Остановлено пользователем", "Обработка остановлена пользователем.", 1.0, "stopped")
        emit_activity(runtime, "Обработка документа остановлена пользователем.")
        return "stopped"

    placeholder_mismatches = _reconcile_placeholder_integrity(placeholder_integrity, processed_image_assets)
    for image_id, placeholder_status in placeholder_mismatches.items():
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
        emit_finalize(runtime, "Критическая ошибка", critical_message, 1.0, "error")
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
    build_started_at_epoch = time.time()

    try:
        docx_bytes = convert_markdown_to_docx_bytes(final_markdown)
        if source_paragraphs:
            docx_bytes = _call_docx_restorer_with_optional_registry(
                preserve_source_paragraph_properties,
                docx_bytes,
                source_paragraphs,
                generated_paragraph_registry or None,
            )
            docx_bytes = _call_docx_restorer_with_optional_registry(
                normalize_semantic_output_docx,
                docx_bytes,
                source_paragraphs,
                generated_paragraph_registry or None,
            )
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
        emit_finalize(runtime, "Ошибка сборки DOCX", error_message, 1.0, "error")
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

    latest_result_notice: dict[str, str] | None = None

    formatting_diagnostics_artifacts = _collect_recent_formatting_diagnostics(
        since_epoch_seconds=build_started_at_epoch
    )
    if formatting_diagnostics_artifacts:
        severity, activity_message, user_summary = _build_formatting_diagnostics_user_feedback(
            formatting_diagnostics_artifacts
        )
        emit_activity(runtime, activity_message)
        if severity == "INFO":
            latest_result_notice = {"level": "info", "message": user_summary}
        else:
            emit_log(
                runtime,
                status=severity,
                block_index=job_count,
                block_count=job_count,
                target_chars=len(final_markdown),
                context_chars=0,
                details=user_summary,
            )
        log_event(
            logging.WARNING,
            "formatting_diagnostics_artifacts_detected",
            "Во время сборки DOCX сохранены formatting diagnostics artifacts.",
            filename=uploaded_filename,
            artifact_paths=formatting_diagnostics_artifacts,
        )

    if not docx_bytes:
        critical_message = present_error(
            "empty_docx_bytes",
            RuntimeError("Сборка DOCX завершилась без содержимого файла."),
            "Критическая ошибка сборки DOCX",
            filename=uploaded_filename,
        )
        emit_state(runtime, last_error=critical_message, latest_docx_bytes=None)
        emit_finalize(runtime, "Критическая ошибка", critical_message, 1.0, "error")
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

    emit_state(
        runtime,
        latest_docx_bytes=docx_bytes,
        latest_markdown=final_markdown,
        latest_result_notice=latest_result_notice,
        last_error="",
    )
    try:
        result_artifact_paths = dict(
            write_ui_result_artifacts(
                source_name=uploaded_filename,
                markdown_text=final_markdown,
                docx_bytes=docx_bytes,
            )
        )
    except OSError as exc:
        log_event(
            logging.WARNING,
            "ui_result_artifacts_save_failed",
            "Не удалось сохранить итоговые UI-артефакты обработки.",
            filename=uploaded_filename,
            error_message=str(exc),
        )
    else:
        log_event(
            logging.INFO,
            "ui_result_artifacts_saved",
            "Сохранены итоговые UI-артефакты обработки.",
            filename=uploaded_filename,
            artifact_paths=result_artifact_paths,
        )
    emit_finalize(
        runtime,
        "Обработка завершена",
        f"Документ обработан за {time.perf_counter() - started_at:.1f} сек.",
        1.0,
        "completed",
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
