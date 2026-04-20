import logging
import json
import inspect
import re
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence, Sized
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class ProcessingDependencies:
    resolve_uploaded_filename: FilenameResolver
    get_client: ClientFactory
    ensure_pandoc_available: Callable[[], None]
    load_system_prompt: SystemPromptLoader
    log_event: EventLogger
    present_error: ErrorPresenter
    should_stop_processing: StopPredicate
    generate_markdown_block: MarkdownGenerator
    process_document_images: ImageProcessor
    inspect_placeholder_integrity: PlaceholderInspector
    convert_markdown_to_docx_bytes: MarkdownToDocxConverter
    preserve_source_paragraph_properties: ParagraphPropertiesPreserver
    normalize_semantic_output_docx: SemanticDocxNormalizer
    reinsert_inline_images: ImageReinserter
    write_ui_result_artifacts: ResultArtifactWriter


@dataclass(frozen=True)
class ProcessingEmitters:
    emit_state: StateEmitter
    emit_finalize: FinalizeEmitter
    emit_activity: ActivityEmitter
    emit_log: LogEmitter
    emit_status: StatusEmitter


@dataclass(frozen=True)
class ProcessingContext:
    uploaded_file: object
    uploaded_filename: str
    jobs: ProcessingJobs
    source_paragraphs: Sequence[ParagraphLike] | None
    image_assets: Sequence[ImageAssetLike]
    image_mode: str
    app_config: Mapping[str, object]
    model: str
    max_retries: int
    processing_operation: str
    source_language: str
    target_language: str
    on_progress: ProgressCallback
    runtime: object


@dataclass
class ProcessingState:
    processed_chunks: list[str] = field(default_factory=list)
    generated_paragraph_registry: list[dict[str, object]] = field(default_factory=list)
    system_prompt: str | None = None
    started_at: float = field(default_factory=time.perf_counter)


@dataclass(frozen=True)
class ProcessingInitialization:
    client: object
    job_count: int


@dataclass(frozen=True)
class ImageProcessingPhaseResult:
    processed_image_assets: list[ImageAssetLike]
    placeholder_integrity: Mapping[str, str]


@dataclass(frozen=True)
class DocxBuildPhaseResult:
    docx_bytes: bytes
    latest_result_notice: dict[str, str] | None


@dataclass(frozen=True)
class BlockExecutionPayload:
    job_kind: str
    target_chars: int
    context_chars: int
    target_text: str
    target_text_with_markers: str
    paragraph_ids: list[str] | None
    context_before: str
    context_after: str


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
    normalize_semantic_output_docx: SemanticDocxNormalizer,
    reinsert_inline_images: ImageReinserter,
    write_ui_result_artifacts: ResultArtifactWriter,
) -> ProcessingDependencies:
    return ProcessingDependencies(
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
        normalize_semantic_output_docx=normalize_semantic_output_docx,
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
    return ProcessingEmitters(
        emit_state=emit_state,
        emit_finalize=emit_finalize,
        emit_activity=emit_activity,
        emit_log=emit_log,
        emit_status=emit_status,
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
    return ProcessingContext(
        uploaded_file=uploaded_file,
        uploaded_filename=dependencies.resolve_uploaded_filename(uploaded_file),
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
    )


@dataclass(frozen=True)
class ProcessingRunComponents:
    dependencies: ProcessingDependencies
    emitters: ProcessingEmitters
    context: ProcessingContext


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
    normalize_semantic_output_docx: SemanticDocxNormalizer,
    reinsert_inline_images: ImageReinserter,
    write_ui_result_artifacts: ResultArtifactWriter,
) -> ProcessingRunComponents:
    dependencies = _build_processing_dependencies(
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
        normalize_semantic_output_docx=normalize_semantic_output_docx,
        reinsert_inline_images=reinsert_inline_images,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )
    emitters = _build_processing_emitters(
        emit_state=emit_state,
        emit_finalize=emit_finalize,
        emit_activity=emit_activity,
        emit_log=emit_log,
        emit_status=emit_status,
    )
    context = _build_processing_context(
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
    )
    return ProcessingRunComponents(
        dependencies=dependencies,
        emitters=emitters,
        context=context,
    )


def _execute_processing_run(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
) -> PipelineResult:
    initialization = _initialize_processing_run(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
    )
    if not isinstance(initialization, ProcessingInitialization):
        return initialization or "failed"
    if initialization.job_count == 0:
        return _fail_empty_processing_plan(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
        )

    state = ProcessingState()
    block_phase_outcome = _run_block_processing_phase(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
    )
    if block_phase_outcome is not None:
        return block_phase_outcome

    image_phase = _run_image_processing_phase(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
    )
    if image_phase is None:
        return "failed"
    if dependencies.should_stop_processing(context.runtime):
        return _emit_stopped_result(
            emitters=emitters,
            runtime=context.runtime,
            detail="Обработка остановлена пользователем.",
            progress=1.0,
            block_index=initialization.job_count,
            block_count=initialization.job_count,
        )

    final_markdown = _current_markdown(state.processed_chunks)
    if not _validate_placeholder_integrity_phase(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        final_markdown=final_markdown,
        image_phase=image_phase,
        job_count=initialization.job_count,
    ):
        return "failed"

    docx_phase = _run_docx_build_phase(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        image_phase=image_phase,
        job_count=initialization.job_count,
    )
    if docx_phase is None:
        return "failed"

    return _finalize_processing_success(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        docx_phase=docx_phase,
        job_count=initialization.job_count,
    )


def _current_markdown(processed_chunks: Sequence[str]) -> str:
    return "\n\n".join(processed_chunks).strip()


def _parse_processing_job(*, job: ProcessingJob) -> BlockExecutionPayload:
    job_kind = _coerce_job_kind(job)
    target_chars = _coerce_required_int_field(job, "target_chars")
    context_chars = _coerce_required_int_field(job, "context_chars")
    target_text = _coerce_required_text_field(job, "target_text", allow_blank=False)
    target_text_with_markers = _coerce_optional_text_field(job, "target_text_with_markers") or target_text
    paragraph_ids = _coerce_optional_string_list(job, "paragraph_ids")
    context_before = _coerce_required_text_field(job, "context_before")
    context_after = _coerce_required_text_field(job, "context_after")
    return BlockExecutionPayload(
        job_kind=job_kind,
        target_chars=target_chars,
        context_chars=context_chars,
        target_text=target_text,
        target_text_with_markers=target_text_with_markers,
        paragraph_ids=paragraph_ids,
        context_before=context_before,
        context_after=context_after,
    )


def _is_marker_mode_enabled(context: ProcessingContext, payload: BlockExecutionPayload) -> bool:
    return bool(context.app_config.get("enable_paragraph_markers", False)) and bool(payload.paragraph_ids)


def _emit_block_started(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    initialization: ProcessingInitialization,
    index: int,
    payload: BlockExecutionPayload,
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

    marker_mode_enabled = _is_marker_mode_enabled(context, payload)
    if state.system_prompt is None:
        state.system_prompt = _resolve_system_prompt(
            dependencies.load_system_prompt,
            operation=context.processing_operation,
            source_language=context.source_language,
            target_language=context.target_language,
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
    return processed_chunk, marker_mode_enabled


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
    paragraph_ids = payload.paragraph_ids or []
    state.generated_paragraph_registry.extend(
        _build_processed_paragraph_registry_entries(
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
    emitters.emit_state(
        context.runtime,
        processed_block_markdowns=state.processed_chunks.copy(),
        latest_markdown=_current_markdown(state.processed_chunks),
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
    try:
        payload = _parse_processing_job(job=job)
    except (KeyError, TypeError, ValueError) as exc:
        return _handle_invalid_processing_job(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            exc=exc,
        )

    _emit_block_started(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        initialization=initialization,
        index=index,
        payload=payload,
    )
    marker_mode_enabled = _is_marker_mode_enabled(context, payload)
    try:
        processed_chunk, marker_mode_enabled = _execute_processing_block(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
        )
    except Exception as exc:
        return _handle_block_generation_failure(
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

    processed_block_status = _classify_processed_block(payload.target_text, processed_chunk)
    if processed_block_status != "valid":
        return _handle_processed_block_rejection(
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
            _append_marker_registry_entries(
                context=context,
                dependencies=dependencies,
                state=state,
                initialization=initialization,
                index=index,
                payload=payload,
                processed_chunk=processed_chunk,
            )
        except Exception as exc:
            return _handle_marker_registry_failure(
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
    _emit_block_completed(
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


def _emit_terminal_result(
    *,
    emitters: ProcessingEmitters,
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


def _emit_stopped_result(
    *,
    emitters: ProcessingEmitters,
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
    emitters.emit_state(
        context.runtime,
        latest_markdown=_current_markdown(state.processed_chunks),
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
    return _emit_failed_result(
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
    marker_diagnostics_artifact = None
    marker_error_code = _extract_marker_diagnostics_code(exc) if marker_mode_enabled else None
    if marker_error_code is not None:
        marker_diagnostics_artifact = _write_marker_diagnostics_artifact(
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
        latest_markdown=_current_markdown(state.processed_chunks),
        latest_docx_bytes=None,
    )
    error_message = dependencies.present_error(
        "block_failed",
        exc,
        "Ошибка обработки блока",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        model=context.model,
    )
    formatted_error = f"Ошибка на блоке {index}: {error_message}"
    emitters.emit_state(
        context.runtime,
        last_error=formatted_error,
        latest_docx_bytes=None,
        latest_marker_diagnostics_artifact=marker_diagnostics_artifact,
    )
    outcome = _emit_failed_result(
        emitters=emitters,
        runtime=context.runtime,
        finalize_stage="Ошибка обработки",
        detail=formatted_error,
        progress=(index - 1) / initialization.job_count,
        activity_message=f"Блок {index}: ошибка обработки.",
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
    return outcome


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
        return _emit_failed_result(
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
    outcome = _emit_failed_result(
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
    marker_diagnostics_artifact = _write_marker_diagnostics_artifact(
        stage="registry",
        uploaded_filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        error_code=_extract_marker_diagnostics_code(exc) or "marker_registry_build_failed",
        target_text=payload.target_text_with_markers,
        context_before=payload.context_before,
        context_after=payload.context_after,
        paragraph_ids=payload.paragraph_ids,
        processed_chunk=processed_chunk,
    )
    emitters.emit_state(
        context.runtime,
        latest_markdown=_current_markdown(state.processed_chunks),
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
    outcome = _emit_failed_result(
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


def _initialize_processing_run(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
) -> ProcessingInitialization | PipelineResult | None:
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
        )
        return _emit_failed_result(
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

    try:
        client = dependencies.get_client()
        dependencies.ensure_pandoc_available()
        dependencies.log_event(
            logging.INFO,
            "processing_started",
            "Запуск обработки документа",
            filename=context.uploaded_filename,
            model=context.model,
            block_count=job_count,
            max_retries=context.max_retries,
            image_count=len(context.image_assets),
        )
        block_plan_summary = _summarize_block_plan(context.jobs)
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
        emitters.emit_activity(context.runtime, f"Инициализация завершена. Модель: {context.model}.")
    except Exception as exc:
        error_message = dependencies.present_error(
            "processing_init_failed",
            exc,
            "Ошибка инициализации обработки",
            filename=context.uploaded_filename,
            model=context.model,
        )
        emitters.emit_state(
            context.runtime,
            last_error=error_message,
            latest_markdown="",
            processed_block_markdowns=[],
            latest_docx_bytes=None,
        )
        _emit_failed_result(
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

    return ProcessingInitialization(client=client, job_count=job_count)


def _fail_empty_processing_plan(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
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
    )
    return _emit_failed_result(
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


def _run_block_processing_phase(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
) -> PipelineResult | None:
    for index, job in enumerate(context.jobs, start=1):
        if dependencies.should_stop_processing(context.runtime):
            stop_message = "Обработка остановлена пользователем."
            return _emit_stopped_result(
                emitters=emitters,
                runtime=context.runtime,
                detail=stop_message,
                progress=(index - 1) / initialization.job_count,
                block_index=max(0, index - 1),
                block_count=initialization.job_count,
            )

        block_outcome = _process_single_block(
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
        return _emit_failed_result(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Критическая ошибка",
            detail=critical_message,
            progress=len(state.processed_chunks) / max(initialization.job_count, 1),
            activity_message="Обнаружено несоответствие количества обработанных блоков.",
            block_index=len(state.processed_chunks),
            block_count=initialization.job_count,
            target_chars=len(_current_markdown(state.processed_chunks)),
            context_chars=0,
            log_details=critical_message,
        )

    return None


def _run_image_processing_phase(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    initialization: ProcessingInitialization,
) -> ImageProcessingPhaseResult | None:
    final_markdown = _current_markdown(state.processed_chunks)
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
        )
        _emit_failed_result(
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

    return ImageProcessingPhaseResult(
        processed_image_assets=normalized_image_assets,
        placeholder_integrity=placeholder_integrity,
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
    placeholder_mismatches = _reconcile_placeholder_integrity(
        image_phase.placeholder_integrity,
        image_phase.processed_image_assets,
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
    emitters.emit_state(context.runtime, last_error=critical_message, latest_docx_bytes=None)
    _emit_failed_result(
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


def _run_docx_build_phase(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    image_phase: ImageProcessingPhaseResult,
    job_count: int,
) -> DocxBuildPhaseResult | None:
    final_markdown = _current_markdown(state.processed_chunks)
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
            docx_bytes = _call_docx_restorer_with_optional_registry(
                dependencies.preserve_source_paragraph_properties,
                docx_bytes,
                context.source_paragraphs,
                state.generated_paragraph_registry or None,
            )
            docx_bytes = _call_docx_restorer_with_optional_registry(
                dependencies.normalize_semantic_output_docx,
                docx_bytes,
                context.source_paragraphs,
                state.generated_paragraph_registry or None,
            )
        if image_phase.processed_image_assets:
            docx_bytes = dependencies.reinsert_inline_images(docx_bytes, image_phase.processed_image_assets)
    except Exception as exc:
        error_message = dependencies.present_error(
            "docx_build_failed",
            exc,
            "Ошибка сборки DOCX",
            filename=context.uploaded_filename,
            final_markdown_chars=len(final_markdown),
        )
        emitters.emit_state(context.runtime, last_error=error_message, latest_docx_bytes=None)
        _emit_failed_result(
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
    formatting_diagnostics_artifacts = _collect_recent_formatting_diagnostics(
        since_epoch_seconds=build_started_at_epoch
    )
    if formatting_diagnostics_artifacts:
        severity, activity_message, user_summary = _build_formatting_diagnostics_user_feedback(
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
        emitters.emit_state(context.runtime, last_error=critical_message, latest_docx_bytes=None)
        _emit_failed_result(
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

    return DocxBuildPhaseResult(docx_bytes=docx_bytes, latest_result_notice=latest_result_notice)


def _finalize_processing_success(
    *,
    context: ProcessingContext,
    dependencies: ProcessingDependencies,
    emitters: ProcessingEmitters,
    state: ProcessingState,
    docx_phase: DocxBuildPhaseResult,
    job_count: int,
) -> PipelineResult:
    final_markdown = _current_markdown(state.processed_chunks)
    emitters.emit_state(
        context.runtime,
        latest_docx_bytes=docx_phase.docx_bytes,
        latest_markdown=final_markdown,
        latest_result_notice=docx_phase.latest_result_notice,
        last_error="",
    )
    try:
        result_artifact_paths = dict(
            dependencies.write_ui_result_artifacts(
                source_name=context.uploaded_filename,
                markdown_text=final_markdown,
                docx_bytes=docx_phase.docx_bytes,
            )
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
        elapsed_seconds=round(time.perf_counter() - state.started_at, 2),
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
        normalize_semantic_output_docx=normalize_semantic_output_docx,
        reinsert_inline_images=reinsert_inline_images,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )
    return _execute_processing_run(
        context=components.context,
        dependencies=components.dependencies,
        emitters=components.emitters,
    )
