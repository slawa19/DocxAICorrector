"""Domain preparation contract and orchestration (ui-free).

Holds ``PreparedRunContext`` and the document-preparation orchestration that the
processing core and a future headless backend/worker need. It must NOT import
the ``ui`` package (guarded by tests/test_layer_boundaries.py).

Localization: the preparation error/quality-gate messages default to the domain's
canonical Russian strings (``_DEFAULT_FLOW_MESSAGES``, kept in sync with the ru
catalog by a test). The ui layer passes ``translate_fn=ui.i18n.t`` to localize for
non-default UI languages; the background path (no UI session, always the default
language) uses the defaults — byte-identical to the previous behavior.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypedDict

from docxaicorrector.document._document import summarize_boundary_normalization_metrics, validate_docx_source_bytes
from docxaicorrector.document.segments import (
    CHAPTER_SEGMENTS_DETECTOR_VERSION,
    DocumentContextProfile,
    DocumentSegment,
    SegmentDetectionReport,
)
from docxaicorrector.processing.preparation import (
    emit_preparation_progress,
    humanize_quality_gate_reasons,
    prepare_document_for_processing,
)
from docxaicorrector.processing.processing_runtime import (
    FrozenUploadPayload,
    freeze_uploaded_file,
    resolve_uploaded_filename,
)
from docxaicorrector.runtime.state import get_selected_source_token, set_selected_source_token


# Canonical domain messages (default language). The ui layer overrides these via
# translate_fn for other languages; kept in sync with the ru catalog by
# tests/test_layer_boundaries.py::test_flow_message_defaults_match_ru_catalog.
_DEFAULT_FLOW_MESSAGES: dict[str, str] = {
    "flow.no_jobs_built": "Не удалось собрать ни одного блока для обработки.",
    "flow.empty_target_block": "Обнаружен пустой целевой блок перед отправкой в модель.",
    "flow.quality_gate_blocked": "Подготовка заблокирована quality gate: документ требует structural repair перед обработкой.",
    "flow.quality_gate_blocked_with_reasons": "Подготовка заблокирована quality gate: документ требует structural repair перед обработкой. Причины: {reasons}",
    "flow.quality_gate_warning": "Обработка продолжена в best-effort режиме: структура документа распознана с повышенным риском.",
    "flow.quality_gate_warning_with_reasons": "Обработка продолжена в best-effort режиме: структура документа распознана с повышенным риском. Причины: {reasons}",
}

TranslateFn = Callable[..., str]


def _default_translate(key: str, /, **kwargs: object) -> str:
    """Default-language message lookup, mirroring ui.i18n.t's contract (key
    fallback + tolerant str.format)."""
    value = _DEFAULT_FLOW_MESSAGES.get(key, key)
    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return value
    return value


def _resolve_translate(translate_fn: TranslateFn | None) -> TranslateFn:
    return _default_translate if translate_fn is None else translate_fn


class NormalizationMetrics(TypedDict, total=False):
    raw_paragraph_count: int
    logical_paragraph_count: int
    merged_group_count: int
    merged_raw_paragraph_count: int
    high_confidence_merge_count: int
    medium_accepted_merge_count: int
    medium_rejected_candidate_count: int


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
    segments: list[DocumentSegment] = field(default_factory=list)
    segment_diagnostics: SegmentDetectionReport = field(default_factory=SegmentDetectionReport)
    structure_fingerprint: str = ""
    detector_version: str = CHAPTER_SEGMENTS_DETECTOR_VERSION
    segment_to_job: dict[str, tuple[int, ...]] = field(default_factory=dict)
    source_format: str = "docx"
    conversion_backend: str | None = None
    normalization_report: object | None = None
    relation_report: object | None = None
    cleanup_report: object | None = None
    structure_repair_report: object | None = None
    quality_gate_status: str = "pass"
    quality_gate_reasons: tuple[str, ...] = ()
    translation_domain: str = "general"
    translation_domain_instructions: str = ""
    document_context_profile: DocumentContextProfile = field(default_factory=DocumentContextProfile)
    exported_structure_manifest_path: str = ""


def flatten_normalization_metrics(normalization_report) -> NormalizationMetrics:
    if normalization_report is None:
        return {}
    metrics: NormalizationMetrics = {
        "raw_paragraph_count": int(getattr(normalization_report, "total_raw_paragraphs", 0) or 0),
        "logical_paragraph_count": int(getattr(normalization_report, "total_logical_paragraphs", 0) or 0),
        "merged_group_count": int(getattr(normalization_report, "merged_group_count", 0) or 0),
        "merged_raw_paragraph_count": int(getattr(normalization_report, "merged_raw_paragraph_count", 0) or 0),
    }
    boundary_metrics = summarize_boundary_normalization_metrics(normalization_report)
    for key, value in boundary_metrics.items():
        metrics[key] = value
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


def flatten_layout_cleanup_metrics(cleanup_report) -> dict[str, int]:
    if cleanup_report is None:
        return {}
    cleanup_mode = str(getattr(cleanup_report, "cleanup_mode", "remove") or "remove").strip().lower()
    if cleanup_mode == "flag":
        return {
            "layout_cleanup_removed_count": int(getattr(cleanup_report, "flagged_page_number_count", 0) or 0)
            + int(getattr(cleanup_report, "flagged_repeated_artifact_count", 0) or 0)
            + int(getattr(cleanup_report, "flagged_empty_or_whitespace_count", 0) or 0),
            "layout_cleanup_page_number_count": int(getattr(cleanup_report, "flagged_page_number_count", 0) or 0),
            "layout_cleanup_repeated_artifact_count": int(
                getattr(cleanup_report, "flagged_repeated_artifact_count", 0) or 0
            ),
            "layout_cleanup_empty_or_whitespace_count": int(
                getattr(cleanup_report, "flagged_empty_or_whitespace_count", 0) or 0
            ),
        }
    return {
        "layout_cleanup_removed_count": int(getattr(cleanup_report, "removed_paragraph_count", 0) or 0),
        "layout_cleanup_page_number_count": int(getattr(cleanup_report, "removed_page_number_count", 0) or 0),
        "layout_cleanup_repeated_artifact_count": int(getattr(cleanup_report, "removed_repeated_artifact_count", 0) or 0),
        "layout_cleanup_empty_or_whitespace_count": int(
            getattr(cleanup_report, "removed_empty_or_whitespace_count", 0) or 0
        ),
    }


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
        metrics={
            "file_size_bytes": len(uploaded_file_bytes),
            "source_format": str(getattr(resolved_upload.uploaded_payload, "source_format", "docx") or "docx"),
            "conversion_backend": getattr(resolved_upload.uploaded_payload, "conversion_backend", None),
        },
    )
    try:
        validate_docx_source_bytes(uploaded_file_bytes)
    except Exception as exc:
        if fail_critical_fn is not None:
            fail_critical_fn("doc_validation_failed", str(exc), filename=uploaded_filename)
        raise
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


def _raise_or_fail_preparation(*, prepared_document, uploaded_filename: str, fail_critical_fn=None, translate_fn: TranslateFn | None = None) -> None:
    translate = _resolve_translate(translate_fn)
    if str(getattr(prepared_document, "quality_gate_status", "pass") or "pass") == "blocked":
        message = _build_quality_gate_blocked_message(prepared_document=prepared_document, translate_fn=translate)
        if fail_critical_fn is not None:
            fail_critical_fn(
                "quality_gate_blocked",
                message,
                filename=uploaded_filename,
                quality_gate_reasons=list(getattr(prepared_document, "quality_gate_reasons", ()) or ()),
            )
        raise ValueError(message)
    if not prepared_document.jobs:
        message = translate("flow.no_jobs_built")
        if fail_critical_fn is not None:
            fail_critical_fn("no_jobs_built", message, filename=uploaded_filename)
        raise ValueError(message)
    if any(not str(job.get("target_text") or "").strip() for job in prepared_document.jobs):
        message = translate("flow.empty_target_block")
        if fail_critical_fn is not None:
            fail_critical_fn("empty_target_block", message, filename=uploaded_filename)
        raise ValueError(message)


def _build_quality_gate_blocked_message(*, prepared_document, translate_fn: TranslateFn | None = None) -> str:
    translate = _resolve_translate(translate_fn)
    reasons = humanize_quality_gate_reasons(getattr(prepared_document, "quality_gate_reasons", ()) or ())
    if not reasons:
        return translate("flow.quality_gate_blocked")
    return translate("flow.quality_gate_blocked_with_reasons", reasons=", ".join(reasons))


def _build_quality_gate_warning_message(*, prepared_document, translate_fn: TranslateFn | None = None) -> str:
    translate = _resolve_translate(translate_fn)
    reasons = humanize_quality_gate_reasons(getattr(prepared_document, "quality_gate_reasons", ()) or ())
    if not reasons:
        return translate("flow.quality_gate_warning")
    return translate("flow.quality_gate_warning_with_reasons", reasons=", ".join(reasons))


def _build_prepared_run_context(*, uploaded_filename: str, uploaded_file_bytes: bytes, uploaded_file_token: str, prepared_document, elapsed_seconds: float, translate_fn: TranslateFn | None = None) -> PreparedRunContext:
    quality_gate_status = str(getattr(prepared_document, "quality_gate_status", "pass") or "pass")
    preparation_detail = ""
    if quality_gate_status == "warning":
        preparation_detail = _build_quality_gate_warning_message(prepared_document=prepared_document, translate_fn=translate_fn)
    return PreparedRunContext(
        uploaded_filename=uploaded_filename,
        uploaded_file_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        source_text=prepared_document.source_text,
        paragraphs=prepared_document.paragraphs,
        image_assets=prepared_document.image_assets,
        jobs=prepared_document.jobs,
        prepared_source_key=prepared_document.prepared_source_key,
        segments=list(getattr(prepared_document, "segments", []) or []),
        segment_diagnostics=getattr(prepared_document, "segment_diagnostics", SegmentDetectionReport()),
        structure_fingerprint=str(getattr(prepared_document, "structure_fingerprint", "") or ""),
        detector_version=str(getattr(prepared_document, "detector_version", CHAPTER_SEGMENTS_DETECTOR_VERSION) or CHAPTER_SEGMENTS_DETECTOR_VERSION),
        segment_to_job=dict(getattr(prepared_document, "segment_to_job", {}) or {}),
        preparation_stage="Документ подготовлен",
        preparation_detail=preparation_detail,
        preparation_cached=prepared_document.cached,
        preparation_elapsed_seconds=elapsed_seconds,
        source_format=str(getattr(prepared_document, "source_format", "docx") or "docx"),
        conversion_backend=getattr(prepared_document, "conversion_backend", None),
        normalization_report=getattr(prepared_document, "normalization_report", None),
        relation_report=getattr(prepared_document, "relation_report", None),
        cleanup_report=getattr(prepared_document, "cleanup_report", None),
        structure_repair_report=getattr(prepared_document, "structure_repair_report", None),
        quality_gate_status=quality_gate_status,
        quality_gate_reasons=tuple(getattr(prepared_document, "quality_gate_reasons", ()) or ()),
        translation_domain=str(getattr(prepared_document, "translation_domain", "general") or "general"),
        translation_domain_instructions=str(
            getattr(prepared_document, "translation_domain_instructions", "") or ""
        ),
        document_context_profile=getattr(prepared_document, "document_context_profile", DocumentContextProfile()),
        exported_structure_manifest_path=str(getattr(prepared_document, "exported_structure_manifest_path", "") or ""),
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
    translate_fn: TranslateFn | None = None,
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
    _raise_or_fail_preparation(prepared_document=prepared_document, uploaded_filename=uploaded_filename, translate_fn=translate_fn)
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
            **flatten_layout_cleanup_metrics(getattr(prepared_document, "cleanup_report", None)),
        },
    )
    return _build_prepared_run_context(
        uploaded_filename=uploaded_filename,
        uploaded_file_bytes=uploaded_file_bytes,
        uploaded_file_token=uploaded_file_token,
        prepared_document=prepared_document,
        elapsed_seconds=elapsed_seconds,
        translate_fn=translate_fn,
    )
