import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from document import summarize_boundary_normalization_metrics, validate_docx_source_bytes
from models import StructureRecognitionSummary
from preparation import build_structure_processing_status_note, emit_preparation_progress, prepare_document_for_processing
from processing_runtime import (
    FrozenUploadPayload,
    build_in_memory_uploaded_file,
    freeze_uploaded_file,
    resolve_uploaded_filename,
)
from restart_store import clear_restart_source, load_restart_source_bytes
from state import (
    clear_completed_source,
    get_completed_source,
    get_prepared_source_key,
    get_processing_outcome,
    get_restart_source,
    get_selected_source_token,
    set_prepared_source_key,
    set_selected_source_token,
)
from workflow_state import IdleViewState, derive_idle_view_state, has_restartable_outcome


class SessionStateLike(Protocol):
    def get(self, key: str, default: object | None = None) -> Any: ...

    def __getitem__(self, key: str): ...

    def __setitem__(self, key: str, value) -> None: ...


@dataclass
class PreparedRunContext:
    uploaded_filename: str
    uploaded_file_bytes: bytes
    uploaded_file_token: str
    source_text: str
    paragraphs: list
    image_assets: list
    jobs: list[dict[str, object]]
    prepared_source_key: str
    preparation_stage: str
    preparation_detail: str
    preparation_cached: bool
    preparation_elapsed_seconds: float
    normalization_report: object | None = None
    relation_report: object | None = None
    structure_map: object | None = None
    structure_recognition_summary: StructureRecognitionSummary = StructureRecognitionSummary()
    structure_validation_report: object | None = None
    structure_recognition_mode: str = "off"
    structure_ai_attempted: bool = False

    @property
    def ai_classified_count(self) -> int:
        return self.structure_recognition_summary.ai_classified_count

    @property
    def ai_heading_count(self) -> int:
        return self.structure_recognition_summary.ai_heading_count

    @property
    def ai_role_change_count(self) -> int:
        return self.structure_recognition_summary.ai_role_change_count

    @property
    def ai_heading_promotion_count(self) -> int:
        return self.structure_recognition_summary.ai_heading_promotion_count

    @property
    def ai_heading_demotion_count(self) -> int:
        return self.structure_recognition_summary.ai_heading_demotion_count

    @property
    def ai_structural_role_change_count(self) -> int:
        return self.structure_recognition_summary.ai_structural_role_change_count


def resolve_structure_recognition_summary(source: object | None) -> StructureRecognitionSummary:
    summary = getattr(source, "structure_recognition_summary", source)
    return StructureRecognitionSummary.from_source(summary)


def flatten_normalization_metrics(normalization_report) -> dict[str, int]:
    if normalization_report is None:
        return {}
    metrics = {
        "raw_paragraph_count": int(getattr(normalization_report, "total_raw_paragraphs", 0) or 0),
        "logical_paragraph_count": int(getattr(normalization_report, "total_logical_paragraphs", 0) or 0),
        "merged_group_count": int(getattr(normalization_report, "merged_group_count", 0) or 0),
        "merged_raw_paragraph_count": int(getattr(normalization_report, "merged_raw_paragraph_count", 0) or 0),
    }
    metrics.update(summarize_boundary_normalization_metrics(normalization_report))
    return metrics


def flatten_relation_metrics(relation_report) -> dict[str, int]:
    if relation_report is None:
        return {}
    metrics = {
        "relation_count": int(getattr(relation_report, "total_relations", 0) or 0),
        "rejected_relation_candidate_count": int(getattr(relation_report, "rejected_candidate_count", 0) or 0),
    }
    relation_counts = getattr(relation_report, "relation_counts", {}) or {}
    for relation_kind, count in relation_counts.items():
        metrics[f"relation_{relation_kind}_count"] = int(count or 0)
    return metrics


@dataclass(frozen=True)
class ResolvedPreparationUpload:
    uploaded_payload: FrozenUploadPayload
    needs_read_stage: bool

    @property
    def uploaded_filename(self) -> str:
        return self.uploaded_payload.filename

    @property
    def uploaded_file_bytes(self) -> bytes:
        return self.uploaded_payload.content_bytes

    @property
    def uploaded_file_token(self) -> str:
        return self.uploaded_payload.file_token

def sync_selected_file_context(*, session_state, reset_run_state_fn, uploaded_file_token: str) -> None:
    previous_token = get_selected_source_token(session_state=session_state)
    if not previous_token or previous_token == uploaded_file_token:
        set_selected_source_token(uploaded_file_token, session_state=session_state)
        return

    reset_run_state_fn(keep_restart_source=False)
    for widget_key in ("sidebar_text_operation", "sidebar_source_language", "sidebar_target_language"):
        if widget_key in session_state:
            del session_state[widget_key]
    set_selected_source_token(uploaded_file_token, session_state=session_state)


def get_cached_restart_file(
    *,
    session_state: SessionStateLike,
    load_restart_source_bytes_fn=None,
    build_in_memory_uploaded_file_fn=None,
):
    if load_restart_source_bytes_fn is None:
        load_restart_source_bytes_fn = load_restart_source_bytes
    if build_in_memory_uploaded_file_fn is None:
        build_in_memory_uploaded_file_fn = build_in_memory_uploaded_file
    restart_source = get_restart_source(session_state=session_state)
    if not isinstance(restart_source, dict):
        return None
    if not restart_source:
        return None
    source_name = str(restart_source.get("filename", ""))
    source_bytes = load_restart_source_bytes_fn(restart_source)
    if not source_name or not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
        return None
    return build_in_memory_uploaded_file_fn(source_name=source_name, source_bytes=bytes(source_bytes))


def get_cached_completed_file(
    *,
    session_state: SessionStateLike,
    build_in_memory_uploaded_file_fn=None,
    load_completed_source_bytes_fn=None,
):
    if build_in_memory_uploaded_file_fn is None:
        build_in_memory_uploaded_file_fn = build_in_memory_uploaded_file
    if load_completed_source_bytes_fn is None:
        load_completed_source_bytes_fn = load_restart_source_bytes
    completed_source = get_completed_source(session_state=session_state)
    if not isinstance(completed_source, dict):
        return None
    if not completed_source:
        return None
    source_name = str(completed_source.get("filename", ""))
    source_bytes = load_completed_source_bytes_fn(completed_source)
    if not source_name or not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
        return None
    return build_in_memory_uploaded_file_fn(source_name=source_name, source_bytes=bytes(source_bytes))


def should_log_document_prepared(*, session_state, prepared_source_key: str) -> bool:
    return get_prepared_source_key(session_state=session_state) != prepared_source_key


def consume_completed_source_if_used(*, session_state, uploaded_file_token: str) -> None:
    completed_source = get_completed_source(session_state=session_state)
    if not completed_source:
        return
    if str(completed_source.get("token", "")) != uploaded_file_token:
        return
    clear_completed_source(
        completed_source=completed_source,
        clear_restart_source_fn=clear_restart_source,
        session_state=session_state,
    )


def _resolve_preparation_dependencies(
    *,
    prepare_document_for_processing_fn,
    resolve_uploaded_filename_fn,
):
    return (
        prepare_document_for_processing if prepare_document_for_processing_fn is None else prepare_document_for_processing_fn,
        resolve_uploaded_filename if resolve_uploaded_filename_fn is None else resolve_uploaded_filename_fn,
    )


def _resolve_preparation_upload(*, uploaded_file=None, uploaded_payload: FrozenUploadPayload | None = None) -> ResolvedPreparationUpload:
    if uploaded_payload is not None:
        return ResolvedPreparationUpload(uploaded_payload=uploaded_payload, needs_read_stage=False)
    if uploaded_file is None:
        raise ValueError("Для синхронной подготовки требуется uploaded_file.")
    return ResolvedPreparationUpload(uploaded_payload=freeze_uploaded_file(uploaded_file), needs_read_stage=True)


def _prepare_run_context_core(
    *,
    uploaded_file=None,
    uploaded_payload: FrozenUploadPayload | None = None,
    chunk_size: int,
    processing_operation: str = "edit",
    app_config: dict[str, object] | None,
    session_state,
    progress_callback,
    prepare_document_for_processing_fn,
    resolve_uploaded_filename_fn,
    reset_run_state_fn=None,
    fail_critical_fn=None,
):
    started_at = time.perf_counter()
    (
        prepare_document_for_processing_fn,
        resolve_uploaded_filename_fn,
    ) = _resolve_preparation_dependencies(
        prepare_document_for_processing_fn=prepare_document_for_processing_fn,
        resolve_uploaded_filename_fn=resolve_uploaded_filename_fn,
    )
    upload_filename_for_read = resolve_uploaded_filename_fn(uploaded_file) if uploaded_payload is None else uploaded_payload.filename
    if uploaded_payload is None:
        emit_preparation_progress(
            progress_callback,
            stage="Чтение файла",
            detail=f"Читаю содержимое {upload_filename_for_read}",
            progress=0.05,
        )
        try:
            resolved_upload = _resolve_preparation_upload(uploaded_file=uploaded_file, uploaded_payload=None)
        except RuntimeError as exc:
            if fail_critical_fn is not None:
                fail_critical_fn("doc_conversion_failed", str(exc), filename=upload_filename_for_read)
            raise
    else:
        resolved_upload = _resolve_preparation_upload(uploaded_payload=uploaded_payload)

    uploaded_filename = resolved_upload.uploaded_filename
    uploaded_file_bytes = resolved_upload.uploaded_file_bytes
    uploaded_file_token = resolved_upload.uploaded_file_token
    emit_preparation_progress(
        progress_callback,
        stage="Файл прочитан",
        detail="Формирую идентификатор источника и подготавливаю анализ.",
        progress=0.15,
        metrics={"file_size_bytes": len(uploaded_file_bytes)},
    )
    validate_docx_source_bytes(uploaded_file_bytes)
    if session_state is not None and reset_run_state_fn is not None:
        sync_selected_file_context(
            session_state=session_state,
            reset_run_state_fn=reset_run_state_fn,
            uploaded_file_token=uploaded_file_token,
        )
    prepared_document = prepare_document_for_processing_fn(
        uploaded_payload=resolved_upload.uploaded_payload,
        chunk_size=chunk_size,
        app_config=app_config,
        processing_operation=processing_operation,
        session_state=session_state,
        progress_callback=progress_callback,
    )
    elapsed_seconds = max(0.0, time.perf_counter() - started_at)
    return uploaded_filename, uploaded_file_bytes, uploaded_file_token, prepared_document, elapsed_seconds


def _raise_or_fail_preparation(*, prepared_document, uploaded_filename: str, fail_critical_fn=None) -> None:
    if not prepared_document.jobs:
        if fail_critical_fn is not None:
            fail_critical_fn("no_jobs_built", "Не удалось собрать ни одного блока для обработки.", filename=uploaded_filename)
        raise ValueError("Не удалось собрать ни одного блока для обработки.")
    if any(not str(job.get("target_text") or "").strip() for job in prepared_document.jobs):
        if fail_critical_fn is not None:
            fail_critical_fn("empty_target_block", "Обнаружен пустой целевой блок перед отправкой в модель.", filename=uploaded_filename)
        raise ValueError("Обнаружен пустой целевой блок перед отправкой в модель.")


def _build_prepared_run_context(*, uploaded_filename: str, uploaded_file_bytes: bytes, uploaded_file_token: str, prepared_document, elapsed_seconds: float) -> PreparedRunContext:
    structure_summary = resolve_structure_recognition_summary(prepared_document)
    return PreparedRunContext(
        uploaded_filename=uploaded_filename,
        uploaded_file_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        source_text=prepared_document.source_text,
        paragraphs=prepared_document.paragraphs,
        image_assets=prepared_document.image_assets,
        jobs=prepared_document.jobs,
        prepared_source_key=prepared_document.prepared_source_key,
        preparation_stage="Документ подготовлен",
        preparation_detail="",
        preparation_cached=prepared_document.cached,
        preparation_elapsed_seconds=elapsed_seconds,
        normalization_report=getattr(prepared_document, "normalization_report", None),
        relation_report=getattr(prepared_document, "relation_report", None),
        structure_map=getattr(prepared_document, "structure_map", None),
        structure_recognition_summary=structure_summary,
        structure_validation_report=getattr(prepared_document, "structure_validation_report", None),
        structure_recognition_mode=str(getattr(prepared_document, "structure_recognition_mode", "off") or "off"),
        structure_ai_attempted=bool(getattr(prepared_document, "structure_ai_attempted", False)),
    )


def has_restartable_source(
    *,
    session_state: SessionStateLike,
) -> bool:
    restart_source = get_restart_source(session_state=session_state)
    if not isinstance(restart_source, dict) or not restart_source:
        return False
    if not has_restartable_outcome(get_processing_outcome(session_state=session_state)):
        return False
    source_name = str(restart_source.get("filename", ""))
    storage_path = str(restart_source.get("storage_path", ""))
    if not source_name or not storage_path:
        return False
    return Path(storage_path).is_file()


def has_resettable_state(
    *,
    current_result,
    session_state: SessionStateLike,
) -> bool:
    if current_result:
        return True
    return has_restartable_source(session_state=session_state)


def resolve_effective_uploaded_file(
    *,
    uploaded_file,
    current_result,
    session_state,
    load_restart_source_bytes_fn=None,
    build_in_memory_uploaded_file_fn=None,
):
    if uploaded_file is not None:
        return uploaded_file
    if current_result is not None:
        completed_file = get_cached_completed_file(
            session_state=session_state,
            build_in_memory_uploaded_file_fn=build_in_memory_uploaded_file_fn,
            load_completed_source_bytes_fn=load_restart_source_bytes_fn,
        )
        if completed_file is not None:
            return completed_file
    if current_result is None and has_restartable_source(session_state=session_state):
        return get_cached_restart_file(
            session_state=session_state,
            load_restart_source_bytes_fn=load_restart_source_bytes_fn,
            build_in_memory_uploaded_file_fn=build_in_memory_uploaded_file_fn,
        )
    return None


def derive_app_idle_view_state(
    *,
    current_result,
    uploaded_file,
    session_state,
) -> IdleViewState:
    return derive_idle_view_state(
        current_result=current_result,
        uploaded_file=uploaded_file,
        has_restartable_source=has_restartable_source(session_state=session_state),
    )


def prepare_run_context(
    *,
    uploaded_file,
    chunk_size: int,
    image_mode: str,
    keep_all_image_variants: bool,
    processing_operation: str = "edit",
    app_config: dict[str, object] | None = None,
    session_state,
    reset_run_state_fn,
    fail_critical_fn,
    log_event_fn,
    prepare_document_for_processing_fn=None,
    resolve_uploaded_filename_fn=None,
    progress_callback=None,
) -> PreparedRunContext:
    uploaded_filename, uploaded_file_bytes, uploaded_file_token, prepared_document, elapsed_seconds = _prepare_run_context_core(
        uploaded_file=uploaded_file,
        chunk_size=chunk_size,
        processing_operation=processing_operation,
        app_config=app_config,
        session_state=session_state,
        progress_callback=progress_callback,
        prepare_document_for_processing_fn=prepare_document_for_processing_fn,
        resolve_uploaded_filename_fn=resolve_uploaded_filename_fn,
        reset_run_state_fn=reset_run_state_fn,
        fail_critical_fn=fail_critical_fn,
    )
    consume_completed_source_if_used(session_state=session_state, uploaded_file_token=uploaded_file_token)
    _raise_or_fail_preparation(prepared_document=prepared_document, uploaded_filename=uploaded_filename, fail_critical_fn=fail_critical_fn)
    if should_log_document_prepared(session_state=session_state, prepared_source_key=prepared_document.prepared_source_key):
        log_event_fn(
            logging.INFO,
            "document_prepared",
            "Документ подготовлен к обработке",
            filename=uploaded_filename,
            paragraph_count=len(prepared_document.paragraphs),
            block_count=len(prepared_document.jobs),
            image_count=len(prepared_document.image_assets),
            source_chars=len(prepared_document.source_text),
            chunk_size=chunk_size,
            image_mode=image_mode,
            keep_all_image_variants=keep_all_image_variants,
            **flatten_normalization_metrics(getattr(prepared_document, "normalization_report", None)),
            **flatten_relation_metrics(getattr(prepared_document, "relation_report", None)),
        )
        set_prepared_source_key(prepared_document.prepared_source_key, session_state=session_state)
    emit_preparation_progress(
        progress_callback,
        stage="Документ подготовлен",
        detail="",
        progress=1.0,
        metrics={
            "file_size_bytes": len(uploaded_file_bytes),
            "paragraph_count": len(prepared_document.paragraphs),
            "image_count": len(prepared_document.image_assets),
            "source_chars": len(prepared_document.source_text),
            "block_count": len(prepared_document.jobs),
            "cached": prepared_document.cached,
            **flatten_normalization_metrics(getattr(prepared_document, "normalization_report", None)),
            **flatten_relation_metrics(getattr(prepared_document, "relation_report", None)),
        },
    )
    return _build_prepared_run_context(
        uploaded_filename=uploaded_filename,
        uploaded_file_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        prepared_document=prepared_document,
        elapsed_seconds=elapsed_seconds,
    )


def prepare_run_context_for_background(
    *,
    uploaded_payload: FrozenUploadPayload,
    chunk_size: int,
    image_mode: str,
    keep_all_image_variants: bool,
    processing_operation: str = "edit",
    app_config: dict[str, object] | None = None,
    prepare_document_for_processing_fn=None,
    resolve_uploaded_filename_fn=None,
    progress_callback=None,
) -> PreparedRunContext:
    uploaded_filename, uploaded_file_bytes, uploaded_file_token, prepared_document, elapsed_seconds = _prepare_run_context_core(
        uploaded_payload=uploaded_payload,
        chunk_size=chunk_size,
        processing_operation=processing_operation,
        app_config=app_config,
        session_state=None,
        progress_callback=progress_callback,
        prepare_document_for_processing_fn=prepare_document_for_processing_fn,
        resolve_uploaded_filename_fn=resolve_uploaded_filename_fn,
        fail_critical_fn=None,
    )
    _raise_or_fail_preparation(prepared_document=prepared_document, uploaded_filename=uploaded_filename)
    emit_preparation_progress(
        progress_callback,
        stage="Документ подготовлен",
        detail="",
        progress=1.0,
        metrics={
            "file_size_bytes": len(uploaded_file_bytes),
            "paragraph_count": len(prepared_document.paragraphs),
            "image_count": len(prepared_document.image_assets),
            "source_chars": len(prepared_document.source_text),
            "block_count": len(prepared_document.jobs),
            "cached": prepared_document.cached,
            **flatten_normalization_metrics(getattr(prepared_document, "normalization_report", None)),
            **flatten_relation_metrics(getattr(prepared_document, "relation_report", None)),
        },
    )
    return _build_prepared_run_context(
        uploaded_filename=uploaded_filename,
        uploaded_file_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        prepared_document=prepared_document,
        elapsed_seconds=elapsed_seconds,
    )
