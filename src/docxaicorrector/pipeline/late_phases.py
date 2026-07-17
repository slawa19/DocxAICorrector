import logging
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

from docxaicorrector.core.models import ImageMode
from docxaicorrector.pipeline.output_validation import (
    assemble_final_markdown,
    build_generated_paragraph_registry_from_entries,
)
from docxaicorrector.pipeline.reassembly import (
    build_reassembly_plan,
    build_reassembly_result_manifest,
    build_segment_result_records,
)
from docxaicorrector.pipeline.quality_report_retention import (  # noqa: F401
    QUALITY_REPORTS_DIR,
    QUALITY_REPORTS_MAX_AGE_SECONDS,
    QUALITY_REPORTS_MAX_COUNT,
    _prune_quality_reports,
    _write_quality_report_artifact,
)
from docxaicorrector.pipeline.formatting_diagnostics_feedback import (  # noqa: F401
    collect_recent_formatting_diagnostics_artifacts,
    _load_formatting_diagnostics_payloads,
    _formatting_diagnostics_requires_user_warning,
    _build_formatting_diagnostics_user_message,
    build_formatting_diagnostics_user_feedback,
)
from docxaicorrector.pipeline.text_call_support import (  # noqa: F401
    _require_group_int,
    _resolve_text_call_target,
)
from docxaicorrector.pipeline.narration_postprocess import (  # noqa: F401
    _ELEVENLABS_TAG_PATTERN,
    _NARRATION_ANY_TAG_PATTERN,
    _NARRATION_DISALLOWED_PATTERNS,
    _build_narration_text,
    _validate_narration_artifact_text,
    _should_run_audiobook_postprocess,
    _collect_narration_chunks,
    _resolve_audiobook_postprocess_model,
    _resolve_audiobook_postprocess_chunk_size,
    _build_narration_postprocess_groups,
    _run_audiobook_postprocess,
)
from docxaicorrector.reader_cleanup_mvp import write_reader_cleanup_diagnostics


from docxaicorrector.pipeline.reader_cleanup_rebuild import (  # noqa: F401
    READER_CLEANUP_LINEAGE_DIR,
    ReaderCleanupPostprocessResult,
    _append_reader_cleanup_lineage_operation,
    _build_docx_rebuild_markdown_after_reader_cleanup,
    _build_empty_docx_failure_result,
    _build_pre_cleanup_formatting_baseline,
    _build_reader_cleanup_block_identity_metadata,
    _build_rebuild_identity_formatting_registry,
    _cleanup_block_index,
    _coerce_optional_float,
    _dedupe_paragraph_ids,
    _derive_reader_cleanup_generated_paragraph_registry,
    _reader_cleanup_layout_signals_from_registry_entry,
    _rebuild_docx_for_markdown,
    _registry_entry_paragraph_ids,
    _resolve_docx_phase_bytes,
    _resolve_final_generated_paragraph_registry,
    _resolve_reader_cleanup_anchor_repair_targets,
    _should_run_reader_cleanup,
    _validate_nonempty_docx_bytes_or_fail,
    _write_reader_cleanup_lineage_artifact,
)
from docxaicorrector.pipeline.reader_cleanup_postprocess import (  # noqa: F401
    _run_reader_cleanup_postprocess,
)
from docxaicorrector.pipeline.runtime_display_markdown import (  # noqa: F401
    _BULLET_MARKDOWN_HEADING_PATTERN,
    _DOCX_IMAGE_HEADING_CONCAT_PATTERN,
    _DOCX_INTERNAL_PLACEHOLDER_PATTERN,
    _MARKDOWN_HEADING_LINE_PATTERN,
    _REVIEW_ANCHOR_HEADING_MARKER_PATTERN,
    _apply_runtime_display_hygiene_cleanup,
    _apply_runtime_display_structure_compatibility_cleanup,
    _normalize_final_markdown_for_display_hygiene_reporting,
    _normalize_final_markdown_for_quality_gate,
    _normalize_final_markdown_for_runtime_display,
    _normalize_heading_match_text,
    _registry_heading_markdown_lines,
    _registry_protected_heading_texts,
    _resolve_runtime_display_markdown,
    _restore_image_heading_lines_from_registry,
)
from docxaicorrector.pipeline.terminal_results import (  # noqa: F401
    _emit_terminal_result,
    emit_failed_result,
    emit_stopped_result,
    fail_empty_processing_plan,
)
from docxaicorrector.pipeline.quality_gate import (  # noqa: F401
    _format_translation_quality_gate_failure_message,
    _serialize_assembly_decisions,
    _resolve_translation_quality_gate_policy,
    _count_bullet_markdown_headings,
    _has_toc_body_concat_markdown,
    _apply_quality_gate_reason,
    _apply_quality_review_reason,
    _FATAL_DOCUMENT_GATE_REASONS,
    _resolve_document_delivery_verdict,
    _serialize_quality_samples,
    _serialize_paragraph_break_samples,
    _serialize_recovered_heading_entries,
    _has_source_backed_entry_authority,
    _resolve_false_fragment_heading_gate_samples,
    _resolve_list_fragment_regression_gate_samples,
    _build_source_backed_entry_by_markdown_line,
    _build_source_backed_entry_index_by_markdown_line,
    _sample_has_source_list_context,
    _normalize_list_fragment_sample_text,
    _is_source_backed_list_entry,
    _build_source_backed_list_entry_texts,
    _is_source_backed_list_sample,
    _STANDALONE_NUMERIC_CONTINUATION_PATTERN,
    _ROLE_AWARE_UNMAPPED_SOURCE_REVIEW_RATIO,
    _ROLE_LOSS_MANUAL_REVIEW_MAX_COUNT,
    _ROLE_LOSS_MANUAL_REVIEW_MAX_RATIO,
    _LEGACY_HYGIENE_MANUAL_REVIEW_MAX_COUNT,
    _LEGACY_HYGIENE_MANUAL_REVIEW_MAX_RATIO,
    _UNTRANSLATED_BODY_MIN_CHARS,
    _UNTRANSLATED_BODY_MIN_LATIN_WORDS,
    _UNTRANSLATED_BODY_FAIL_MIN_CHARS,
    _UNTRANSLATED_BODY_FAIL_RATIO,
    _HygieneGateSpec,
    _UntranslatedStructuralSample,
    _HYGIENE_GATE_SPECS,
    _LATIN_LETTER_PATTERN,
    _LATIN_WORD_PATTERN,
    _CYRILLIC_LETTER_PATTERN,
    _MARKDOWN_STRUCTURAL_PREFIX_PATTERN,
    _URL_OR_DOMAIN_PATTERN,
    _BIBLIOGRAPHY_LIKE_PATTERN,
    _strip_structural_markdown_prefix,
    _is_untranslated_structural_text,
    _latin_letter_ratio,
    _is_bibliography_or_url_dominant_text,
    _is_untranslated_body_text,
    _collect_untranslated_structural_samples,
    _collect_untranslated_body_samples,
    _serialize_untranslated_structural_sample,
    _is_standalone_numeric_continuation_sample,
    _REFERENCES_BIB_MARKER_PATTERN,
    _MULTI_FOOTNOTE_MARKER_PATTERN,
    _is_citation_form_list_fragment_sample,
    _is_reviewable_list_fragment_residue,
    _sanitize_review_anchor_text,
    _review_anchor_visible_char_count,
    _ROLE_LOSS_SAMPLE_REASONS,
    _review_item_word_style,
    _build_formatting_review_item,
    _emit_mapping_text_quality_defect_items,
    _formatting_review_required_count,
    _effective_formatting_coverage_diagnostics,
    _effective_formatting_coverage_counts,
    _effective_formatting_coverage_samples_by_class,
    _serialize_role_loss_sample,
    _serialize_heading_demotion_sample,
    _controlled_fallback_review_samples,
    _emit_controlled_fallback_review_items,
    _is_reviewable_role_aware_unmapped_source_residue,
    _is_role_loss_within_manual_review_threshold,
    _is_legacy_hygiene_within_manual_review_threshold,
    _apply_manual_review_or_fail,
    _hygiene_threshold_fn,
    _emit_unmapped_source_discrepancy_review_items,
    _emit_unmapped_target_discrepancy_review_items,
    _emit_hygiene_gate,
    _ACCEPTANCE_MAX_UNMAPPED_SOURCE_CONFIG_KEY,
    _ACCEPTANCE_MAX_UNMAPPED_TARGET_CONFIG_KEY,
    _ACCEPTANCE_REQUIRE_NO_TOC_BODY_CONCAT_CONFIG_KEY,
    build_report_acceptance_verdict,
    _resolve_acceptance_thresholds,
    _build_report_context_for_acceptance,
    _resolve_acceptance_output_artifacts,
    _build_translation_quality_report,
    _derive_translation_quality_authority_fields,
    _effective_authoritative_unmapped_count,
    _build_result_quality_warning,
    _russian_paragraph_word,
    _build_quality_warn_notice_message,
    _build_quality_gate_activity_message,
)


PipelineResult = Literal["succeeded", "failed", "stopped"]


def _log_boundary_recovery_diagnostics(*, dependencies: Any, context: Any, assembly_result: Any) -> None:
    diagnostics = getattr(assembly_result, "diagnostics", None)
    if diagnostics is None:
        return
    dependencies.log_event(
        logging.INFO,
        "boundary_recovery_diagnostics",
        "Собраны diagnostics registry-aware paragraph boundary recovery.",
        filename=context.uploaded_filename,
        accepted_merges=getattr(diagnostics, "accepted_merges", 0),
        denied_merges=getattr(diagnostics, "denied_merges", 0),
        protected_boundary_denials=getattr(diagnostics, "protected_boundary_denials", 0),
        demoted_false_headings=getattr(diagnostics, "demoted_false_headings", 0),
        registry_covered_paragraphs=getattr(diagnostics, "registry_covered_paragraphs", 0),
        fallback_paragraphs=getattr(diagnostics, "fallback_paragraphs", 0),
        paragraph_count_drift=getattr(diagnostics, "paragraph_count_drift", 0),
        inconsistent_registry_blocks=list(getattr(diagnostics, "inconsistent_registry_blocks", ()) or ()),
        merge_decisions=_serialize_assembly_decisions(getattr(diagnostics, "merge_decisions", ()) or ()),
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
    assembly_result = assemble_final_markdown(
        processed_chunks=state.processed_chunks,
        generated_paragraph_registry=state.generated_paragraph_registry,
        source_paragraphs=context.source_paragraphs,
    )
    _log_boundary_recovery_diagnostics(dependencies=dependencies, context=context, assembly_result=assembly_result)
    final_markdown = assembly_result.final_markdown
    assembly_registry = build_generated_paragraph_registry_from_entries(assembly_result.entries)
    runtime_display_markdown = _restore_image_heading_lines_from_registry(
        _normalize_final_markdown_for_runtime_display(
            final_markdown,
            assembly_registry or state.generated_paragraph_registry or None,
        ),
        assembly_registry or state.generated_paragraph_registry or None,
    )
    emitters.emit_state(context.runtime, latest_markdown=runtime_display_markdown)
    try:
        image_client = initialization.openai_client
        image_mode_requires_openai_client = context.image_mode not in {
            ImageMode.NO_CHANGE.value,
            ImageMode.SAFE.value,
        }
        if (
            image_client is None
            and image_mode_requires_openai_client
            and callable(getattr(dependencies, "get_provider_client", None))
        ):
            image_client = dependencies.get_provider_client("openai")
        if image_client is None and image_mode_requires_openai_client:
            raise RuntimeError("Для image phase, требующей OpenAI, не удалось получить OpenAI client.")
        if image_client is None:
            image_client = initialization.client
        processed_image_assets = dependencies.process_document_images(
            image_assets=context.image_assets,
            image_mode=context.image_mode,
            config=context.app_config,
            on_progress=context.on_progress,
            runtime=context.runtime,
            client=image_client,
        )
        if processed_image_assets is None:
            raise RuntimeError("Пайплайн обработки изображений вернул None вместо коллекции ассетов.")

        normalized_image_assets = list(processed_image_assets)
        placeholder_integrity = dependencies.inspect_placeholder_integrity(runtime_display_markdown, normalized_image_assets)
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
            final_markdown_chars=len(runtime_display_markdown),
            image_count=len(context.image_assets),
            image_mode=context.image_mode,
        )
        emitters.emit_state(
            context.runtime,
            latest_markdown=runtime_display_markdown,
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
            target_chars=len(runtime_display_markdown),
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
    reassembly_plan = build_reassembly_plan(
        output_mode=str(getattr(context, "output_mode", "") or ""),
        jobs=list(getattr(context, "jobs", ()) or ()),
        source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
    )
    assembly_result = assemble_final_markdown(
        processed_chunks=state.processed_chunks,
        generated_paragraph_registry=state.generated_paragraph_registry,
        source_paragraphs=context.source_paragraphs,
    )
    _log_boundary_recovery_diagnostics(dependencies=dependencies, context=context, assembly_result=assembly_result)
    final_markdown = assembly_result.final_markdown
    assembly_registry = build_generated_paragraph_registry_from_entries(assembly_result.entries)
    result_manifest = build_reassembly_result_manifest(
        source_name=context.uploaded_filename,
        source_token=str(getattr(context, "source_token", "") or ""),
        run_id=str(getattr(context, "run_id", "") or ""),
        plan=reassembly_plan,
        jobs=list(getattr(context, "jobs", ()) or ()),
        source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
    )
    runtime_display_markdown = _restore_image_heading_lines_from_registry(
        _normalize_final_markdown_for_runtime_display(
            final_markdown,
            assembly_registry or state.generated_paragraph_registry or None,
        ),
        assembly_registry or state.generated_paragraph_registry or None,
    )
    emitters.emit_status(
        context.runtime,
        stage="Сборка DOCX",
        detail="Все блоки готовы. Собираю итоговый DOCX из Markdown.",
        current_block=job_count,
        block_count=job_count,
        target_chars=len(runtime_display_markdown),
        context_chars=0,
        progress=1.0,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, "Все блоки готовы. Начата сборка итогового DOCX.")
    context.on_progress(preview_title="Текущий Markdown")
    build_started_at_epoch = time.time()
    processed_image_assets = image_phase["processed_image_assets"]
    docx_bytes_cache: bytes | None = None

    def _build_base_docx_bytes() -> bytes:
        nonlocal docx_bytes_cache
        if docx_bytes_cache is not None:
            return docx_bytes_cache
        docx_bytes = dependencies.convert_markdown_to_docx_bytes(runtime_display_markdown)
        if context.source_paragraphs:
            docx_bytes = call_docx_restorer_with_optional_registry_fn(
                dependencies.preserve_source_paragraph_properties,
                docx_bytes,
                context.source_paragraphs,
                assembly_registry or state.generated_paragraph_registry or None,
            )
        if processed_image_assets:
            docx_bytes = dependencies.reinsert_inline_images(docx_bytes, processed_image_assets)
        docx_bytes_cache = docx_bytes
        return docx_bytes

    docx_bytes: bytes | None = None
    should_defer_base_docx_build = _should_run_reader_cleanup(context=context)
    pre_cleanup_formatting_baseline = (
        _build_pre_cleanup_formatting_baseline(
            markdown_text=runtime_display_markdown,
            generated_paragraph_registry=assembly_registry or state.generated_paragraph_registry or None,
        )
        if should_defer_base_docx_build
        else None
    )
    try:
        if not should_defer_base_docx_build:
            docx_bytes = _build_base_docx_bytes()
    except Exception as exc:
        error_message = dependencies.present_error(
            "docx_build_failed",
            exc,
            "Ошибка сборки DOCX",
            filename=context.uploaded_filename,
            final_markdown_chars=len(runtime_display_markdown),
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
            target_chars=len(runtime_display_markdown),
            context_chars=0,
            log_details=error_message,
        )
        return None

    latest_result_notice: dict[str, str] | None = None
    formatting_diagnostics_artifacts: Sequence[str] = []
    if docx_bytes is not None:
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
                target_chars=len(runtime_display_markdown),
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

    if docx_bytes is not None and not docx_bytes:
        _build_empty_docx_failure_result(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            runtime_display_markdown=runtime_display_markdown,
            job_count=job_count,
        )
        return None

    return {
        "docx_bytes": docx_bytes,
        "base_docx_builder": _build_base_docx_bytes,
        "runtime_display_markdown": runtime_display_markdown,
        "latest_result_notice": latest_result_notice,
        "pre_cleanup_formatting_baseline": pre_cleanup_formatting_baseline,
        "formatting_diagnostics_artifacts": list(formatting_diagnostics_artifacts),
        # spec 043 P1: carry the diagnostics window (start epoch + dir) into finalize so a
        # DEFERRED base build (reader cleanup enabled) can RE-COLLECT the FINAL-DOCX
        # formatting diagnostics written during the reader-cleanup build — the pre-cleanup
        # gate above ran on an empty list because ``docx_bytes`` was None at that point.
        "build_started_at_epoch": build_started_at_epoch,
        "diagnostics_dir": diagnostics_dir,
        "assembly_entries": list(assembly_result.entries),
        "result_manifest": result_manifest,
        "processed_image_assets": list(cast(Sequence[Any], image_phase.get("processed_image_assets") or [])),
    }


def _verify_primary_result_artifacts_or_raise(result_artifact_paths: Mapping[str, object]) -> None:
    """Finding 13: a returned artifact mapping is NOT proof of persistence.

    ``write_ui_result_artifacts`` returning without raising only means it did not hit an
    ``OSError`` mid-write; it does NOT guarantee the PRIMARY user-facing files
    (``.result.md`` + ``.result.docx``) are present, on disk, and non-empty. Verify exactly
    those two here so a mapping that omits a primary key, or points at a missing / zero-byte
    file, is funnelled into the SAME F4/F12 primary-persistence-failure path (WARNING
    ``processing_completed_unpersisted`` + user-visible not-saved notice) as an outright
    write ``OSError`` — never reported as a false success. Secondary artifacts
    (diagnostics/registries) are deliberately NOT checked here; their own failures are
    handled separately and must never claim the delivered result was not saved.
    """
    for artifact_key in ("markdown_path", "docx_path"):
        raw_path = result_artifact_paths.get(artifact_key)
        if not isinstance(raw_path, str) or not raw_path:
            raise OSError(f"primary result artifact '{artifact_key}' missing from write result")
        artifact_path = Path(raw_path)
        if not artifact_path.is_file():
            raise OSError(f"primary result artifact '{artifact_key}' not found on disk: {raw_path}")
        if artifact_path.stat().st_size <= 0:
            raise OSError(f"primary result artifact '{artifact_key}' is empty on disk: {raw_path}")


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
    assembly_result = assemble_final_markdown(
        processed_chunks=state.processed_chunks,
        generated_paragraph_registry=state.generated_paragraph_registry,
        source_paragraphs=context.source_paragraphs,
    )
    _log_boundary_recovery_diagnostics(dependencies=dependencies, context=context, assembly_result=assembly_result)
    gate_input_markdown = assembly_result.final_markdown
    runtime_display_markdown = _resolve_runtime_display_markdown(
        docx_phase=docx_phase,
        fallback_markdown=gate_input_markdown,
    )
    formatting_diagnostics_artifacts = cast(
        Sequence[str],
        docx_phase.get("formatting_diagnostics_artifacts") or [],
    )
    quality_report = _build_translation_quality_report(
        context=context,
        final_markdown=gate_input_markdown,
        formatting_diagnostics_artifacts=formatting_diagnostics_artifacts,
        assembly_result=assembly_result,
        pre_cleanup_formatting_baseline=cast(Mapping[str, object] | None, docx_phase.get("pre_cleanup_formatting_baseline")),
        runtime_display_markdown=runtime_display_markdown,
    )
    # Serialize the shared acceptance verdict into the quality report so the
    # production (incl. advisory) path carries the same trustworthy verdict the
    # validation harness computes (GATE_TRUSTWORTHINESS refactor — harness<->prod
    # parity). Thresholds come from config, not per-book literals.
    (
        _acceptance_mismatch_threshold,
        _acceptance_unmapped_target_threshold,
        _acceptance_require_no_toc_body_concat,
    ) = _resolve_acceptance_thresholds(context)
    # Thread the run's real output artifacts so ``output_docx_openable`` reflects
    # reality (spec FR-001). At this point the delivered DOCX may not be built yet
    # — reader cleanup defers the base build, leaving ``docx_bytes`` None — so we
    # only report openability when the bytes genuinely exist; otherwise the shared
    # verdict marks the check NOT-APPLICABLE rather than guessing (Constitution VII).
    _acceptance_output_artifacts = _resolve_acceptance_output_artifacts(
        docx_phase=docx_phase,
        runtime_display_markdown=runtime_display_markdown,
    )
    quality_report["acceptance_verdict"] = build_report_acceptance_verdict(
        _build_report_context_for_acceptance(
            context=context,
            quality_report=quality_report,
            formatting_diagnostics_payloads=_load_formatting_diagnostics_payloads(formatting_diagnostics_artifacts),
            output_artifacts=_acceptance_output_artifacts,
        ),
        mismatch_threshold=_acceptance_mismatch_threshold,
        unmapped_target_threshold=_acceptance_unmapped_target_threshold,
        require_no_toc_body_concat=_acceptance_require_no_toc_body_concat,
    )
    if quality_report.get("quality_status") == "warn":
        docx_phase = dict(docx_phase)
        docx_phase["latest_result_notice"] = {
            "level": "warning",
            "message": _build_quality_warn_notice_message(quality_report),
        }
    quality_report_path = _write_quality_report_artifact(source_name=context.uploaded_filename, payload=quality_report)
    if quality_report_path is not None:
        dependencies.log_event(
            logging.INFO,
            "quality_report_saved",
            "Сохранён quality report для итогового результата обработки.",
            filename=context.uploaded_filename,
            artifact_path=quality_report_path,
            quality_status=quality_report.get("quality_status"),
            gate_reasons=list(cast(Sequence[str], quality_report.get("gate_reasons") or [])),
        )
    if quality_report.get("quality_status") == "fail":
        gate_reasons = list(cast(Sequence[str], quality_report.get("gate_reasons") or []))
        resolved_docx_bytes = _resolve_docx_phase_bytes(docx_phase)
        empty_docx_failure = _validate_nonempty_docx_bytes_or_fail(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            runtime_display_markdown=runtime_display_markdown,
            job_count=job_count,
            docx_bytes=resolved_docx_bytes,
        )
        if empty_docx_failure is not None:
            return empty_docx_failure
        error_message = dependencies.present_error(
            "translation_quality_gate_failed",
            RuntimeError(_format_translation_quality_gate_failure_message(gate_reasons)),
            "Критическая ошибка качества перевода",
            filename=context.uploaded_filename,
            quality_status=quality_report.get("quality_status"),
            gate_reasons=gate_reasons,
            quality_report_path=quality_report_path,
        )
        emitters.emit_state(
            context.runtime,
            latest_markdown=runtime_display_markdown,
            latest_docx_bytes=resolved_docx_bytes,
            latest_narration_text=None,
            latest_result_notice={
                "level": "error",
                "message": "Результат заблокирован document-level quality gate.",
            },
            last_error=error_message,
        )
        dependencies.log_event(
            logging.WARNING,
            "translation_quality_gate_failed",
            "Итоговый перевод отклонён document-level quality gate.",
            filename=context.uploaded_filename,
            quality_report_path=quality_report_path,
            gate_reasons=gate_reasons,
            quality_status=quality_report.get("quality_status"),
        )
        return emit_failed_result(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Критическая ошибка качества перевода",
            detail=error_message,
            progress=1.0,
            activity_message=_build_quality_gate_activity_message(gate_reasons),
            block_index=job_count,
            block_count=job_count,
            target_chars=len(runtime_display_markdown),
            context_chars=0,
            log_details=error_message,
        )
    narration_error_message = ""
    reader_cleanup_report: dict[str, object] | None = None
    reader_cleanup_raw_markdown: str | None = None
    reader_cleanup_result_notice: dict[str, str] | None = None
    reader_cleanup_postprocess = _run_reader_cleanup_postprocess(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        cleanup_input_markdown=gate_input_markdown,
        runtime_display_markdown=runtime_display_markdown,
        base_docx_bytes=cast(bytes | None, docx_phase.get("docx_bytes")),
        job_count=job_count,
        processed_image_assets=cast(Sequence[Any], docx_phase.get("processed_image_assets") or []),
        formatting_registry=build_generated_paragraph_registry_from_entries(assembly_result.entries),
        base_docx_builder=cast(Callable[[], bytes] | None, docx_phase.get("base_docx_builder")),
    )
    # The delivered display markdown BEFORE reader cleanup. The pre-cleanup quality report
    # already describes this content (its hygiene metrics were measured on it), so only a
    # reader-cleanup change to it — NOT the earlier display-hygiene pass that produced it —
    # makes the saved report stale and warrants a rebuild (F8, below).
    pre_reader_cleanup_display_markdown = runtime_display_markdown
    runtime_display_markdown = reader_cleanup_postprocess.markdown
    final_docx_bytes = reader_cleanup_postprocess.docx_bytes
    reader_cleanup_report = reader_cleanup_postprocess.report
    reader_cleanup_raw_markdown = reader_cleanup_postprocess.raw_markdown
    reader_cleanup_result_notice = reader_cleanup_postprocess.result_notice
    final_generated_paragraph_registry = reader_cleanup_postprocess.final_generated_paragraph_registry
    if final_generated_paragraph_registry is not None:
        docx_phase = dict(docx_phase)
        docx_phase["final_generated_paragraph_registry"] = final_generated_paragraph_registry
    empty_docx_failure = _validate_nonempty_docx_bytes_or_fail(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        runtime_display_markdown=runtime_display_markdown,
        job_count=job_count,
        docx_bytes=final_docx_bytes,
    )
    if empty_docx_failure is not None:
        return empty_docx_failure
    current_docx_bytes = docx_phase.get("docx_bytes")
    if not isinstance(current_docx_bytes, bytes) or final_docx_bytes != current_docx_bytes or runtime_display_markdown != _resolve_runtime_display_markdown(
        docx_phase=docx_phase,
        fallback_markdown=gate_input_markdown,
    ):
        docx_phase = dict(docx_phase)
        docx_phase["docx_bytes"] = final_docx_bytes
        docx_phase["runtime_display_markdown"] = runtime_display_markdown
    if reader_cleanup_result_notice is not None:
        docx_phase = dict(docx_phase)
        docx_phase["latest_result_notice"] = reader_cleanup_result_notice

    # spec 043 P1: when the base DOCX build was DEFERRED (reader cleanup enabled), the
    # pre-cleanup quality gate above ran on an EMPTY formatting-diagnostics list —
    # ``docx_bytes`` was None then, so nothing was collected. The FINAL DOCX has now been
    # built by the reader-cleanup post-pass and has written FRESH formatting-diagnostics
    # artifacts (incl. ``caption_heading_conflicts``) to ``diagnostics_dir``. RE-COLLECT
    # them so the delivered-report rebuild and the caption→heading delivery gate judge the
    # DELIVERED artifact — not the stale pre-cleanup snapshot. When the base build was NOT
    # deferred the pre-cleanup list is already authoritative (spec 042 already gated it),
    # so we keep it verbatim and behaviour stays byte-identical.
    post_cleanup_formatting_diagnostics_artifacts: Sequence[str] = formatting_diagnostics_artifacts
    post_cleanup_caption_conflict_count = 0
    base_build_was_deferred = _should_run_reader_cleanup(context=context)
    if base_build_was_deferred:
        recollect_diagnostics_dir = docx_phase.get("diagnostics_dir")
        recollect_since_epoch = cast(float, docx_phase.get("build_started_at_epoch") or 0.0)
        if isinstance(recollect_diagnostics_dir, Path):
            post_cleanup_formatting_diagnostics_artifacts = collect_recent_formatting_diagnostics_artifacts(
                since_epoch_seconds=recollect_since_epoch,
                diagnostics_dir=recollect_diagnostics_dir,
            )
        # Aggregate the caption→heading conflict count across ALL final diagnostics payloads
        # (mirrors the acceptance verdict + spec 043 P2 delivery-gate aggregation) so the gate
        # fires even when a conflict lives in a non-last artifact. Keyed on the conflict signal
        # only (no per-book literal).
        post_cleanup_caption_conflict_count = sum(
            len(cast(Sequence[object], payload.get("caption_heading_conflicts") or []))
            for payload in _load_formatting_diagnostics_payloads(post_cleanup_formatting_diagnostics_artifacts)
            if isinstance(payload, Mapping)
        )

    # F10 + F8 (spec 006 increment / round-4): the FINAL authoritative quality report must
    # describe the DELIVERED post-cleanup markdown. The pre-cleanup report was written as the
    # record describing the pre-reader-cleanup delivered content; reader cleanup can REPLACE
    # that content afterwards, so when it does we rebuild the report on the delivered markdown,
    # carry the acceptance verdict into it, and SUPERSEDE the pre-cleanup artifact — dropping
    # the now-stale file — so the saved record, the delivered result notice, the result
    # artifact, and any gate error all reference the delivered content, never the outdated
    # pre-cleanup report. The trigger is a reader-cleanup change specifically (compared to the
    # pre-reader-cleanup delivered markdown, NOT ``gate_input_markdown`` whose raw/structural
    # metrics the report legitimately keeps): when reader cleanup leaves the delivered markdown
    # unchanged the pre-cleanup report is already authoritative, so behaviour is byte-identical
    # (no rebuild, no second write, no second gate pass). The empty-DOCX guard was already run.
    #
    # spec 043 P1: the caption→heading delivery gate must also fire when the base build was
    # DEFERRED and the RE-COLLECTED final diagnostics carry a conflict — even if reader
    # cleanup left the delivered markdown UNCHANGED (the deferred build still produced the
    # DOCX + diagnostics the pre-cleanup gate never saw). So the report rebuild is triggered
    # by a markdown change OR a final-diagnostics caption conflict; every rebuild judges the
    # RE-COLLECTED ``post_cleanup_formatting_diagnostics_artifacts`` (the delivered artifact)
    # instead of the stale pre-cleanup list. The non-caption, unchanged-markdown case takes
    # the ``else`` branch below and stays byte-identical.
    if runtime_display_markdown != pre_reader_cleanup_display_markdown or post_cleanup_caption_conflict_count > 0:
        quality_report = _build_translation_quality_report(
            context=context,
            final_markdown=runtime_display_markdown,
            formatting_diagnostics_artifacts=post_cleanup_formatting_diagnostics_artifacts,
            assembly_result=assembly_result,
            pre_cleanup_formatting_baseline=cast(Mapping[str, object] | None, docx_phase.get("pre_cleanup_formatting_baseline")),
            runtime_display_markdown=runtime_display_markdown,
        )
        # Carry the shared acceptance verdict into the delivered report. The DOCX bytes now
        # exist (reader cleanup built them), so ``output_docx_openable`` reflects reality.
        post_cleanup_output_artifacts = _resolve_acceptance_output_artifacts(
            docx_phase=docx_phase,
            runtime_display_markdown=runtime_display_markdown,
        )
        quality_report["acceptance_verdict"] = build_report_acceptance_verdict(
            _build_report_context_for_acceptance(
                context=context,
                quality_report=quality_report,
                formatting_diagnostics_payloads=_load_formatting_diagnostics_payloads(post_cleanup_formatting_diagnostics_artifacts),
                output_artifacts=post_cleanup_output_artifacts,
            ),
            mismatch_threshold=_acceptance_mismatch_threshold,
            unmapped_target_threshold=_acceptance_unmapped_target_threshold,
            require_no_toc_body_concat=_acceptance_require_no_toc_body_concat,
        )
        # Supersede the pre-cleanup artifact: write the delivered report and drop the
        # now-stale pre-cleanup file so the saved record is never the outdated one.
        superseded_report_path = quality_report_path
        quality_report_path = _write_quality_report_artifact(
            source_name=context.uploaded_filename, payload=quality_report
        )
        # Drop the stale pre-cleanup file only once its replacement is safely on disk, so a
        # rare write failure never leaves the run with zero saved reports.
        if quality_report_path is not None and superseded_report_path and superseded_report_path != quality_report_path:
            try:
                Path(superseded_report_path).unlink()
            except OSError:
                pass
        if quality_report_path is not None:
            dependencies.log_event(
                logging.INFO,
                "quality_report_saved",
                "Обновлён quality report по итогам reader cleanup (delivered markdown).",
                filename=context.uploaded_filename,
                artifact_path=quality_report_path,
                quality_status=quality_report.get("quality_status"),
                gate_reasons=list(cast(Sequence[str], quality_report.get("gate_reasons") or [])),
            )
        # Refresh the delivered result notice to reflect the authoritative report, unless
        # reader cleanup already set its own notice (which keeps precedence, as before).
        if reader_cleanup_result_notice is None:
            docx_phase = dict(docx_phase)
            if quality_report.get("quality_status") == "warn":
                docx_phase["latest_result_notice"] = {
                    "level": "warning",
                    "message": _build_quality_warn_notice_message(quality_report),
                }
            else:
                docx_phase["latest_result_notice"] = None
        if quality_report.get("quality_status") == "fail":
            post_cleanup_gate_reasons = list(
                cast(Sequence[str], quality_report.get("gate_reasons") or [])
            )
            error_message = dependencies.present_error(
                "translation_quality_gate_failed",
                RuntimeError(_format_translation_quality_gate_failure_message(post_cleanup_gate_reasons)),
                "Критическая ошибка качества перевода",
                filename=context.uploaded_filename,
                quality_status=quality_report.get("quality_status"),
                gate_reasons=post_cleanup_gate_reasons,
                quality_report_path=quality_report_path,
            )
            emitters.emit_state(
                context.runtime,
                latest_markdown=runtime_display_markdown,
                latest_docx_bytes=_resolve_docx_phase_bytes(docx_phase),
                latest_narration_text=None,
                latest_result_notice={
                    "level": "error",
                    "message": "Результат заблокирован document-level quality gate.",
                },
                last_error=error_message,
            )
            dependencies.log_event(
                logging.WARNING,
                "translation_quality_gate_failed_post_cleanup",
                "Итоговый перевод отклонён document-level quality gate после reader cleanup.",
                filename=context.uploaded_filename,
                quality_report_path=quality_report_path,
                gate_reasons=post_cleanup_gate_reasons,
                quality_status=quality_report.get("quality_status"),
            )
            return emit_failed_result(
                emitters=emitters,
                runtime=context.runtime,
                finalize_stage="Критическая ошибка качества перевода",
                detail=error_message,
                progress=1.0,
                activity_message=_build_quality_gate_activity_message(post_cleanup_gate_reasons),
                block_index=job_count,
                block_count=job_count,
                target_chars=len(runtime_display_markdown),
                context_chars=0,
                log_details=error_message,
            )
    else:
        # Finding 7: reader cleanup left the delivered markdown UNCHANGED, so the
        # markdown-derived report metrics stay authoritative and are NOT recomputed
        # (byte-identical behaviour preserved). But the final delivered DOCX bytes may
        # only exist NOW — the base docx build is deferred until reader cleanup on the
        # common production path — which the pre-cleanup verdict recorded as
        # ``output_docx_openable`` NOT-APPLICABLE. Refresh ONLY the output-artifact-
        # dependent verdict fields on the delivered bytes so the saved record reflects
        # the real DOCX; the markdown metrics carry over untouched. When the artifacts
        # are unchanged from the pre-cleanup evaluation (already-built bytes, or still
        # none) nothing is rebuilt or re-written, keeping the no-op path byte-identical.
        post_cleanup_output_artifacts = _resolve_acceptance_output_artifacts(
            docx_phase=docx_phase,
            runtime_display_markdown=runtime_display_markdown,
        )
        if post_cleanup_output_artifacts is not None and post_cleanup_output_artifacts != _acceptance_output_artifacts:
            quality_report["acceptance_verdict"] = build_report_acceptance_verdict(
                _build_report_context_for_acceptance(
                    context=context,
                    quality_report=quality_report,
                    formatting_diagnostics_payloads=_load_formatting_diagnostics_payloads(formatting_diagnostics_artifacts),
                    output_artifacts=post_cleanup_output_artifacts,
                ),
                mismatch_threshold=_acceptance_mismatch_threshold,
                unmapped_target_threshold=_acceptance_unmapped_target_threshold,
                require_no_toc_body_concat=_acceptance_require_no_toc_body_concat,
            )
            # Supersede the pre-cleanup report so the saved record's verdict reflects
            # the delivered DOCX. Only the acceptance verdict changed; the markdown
            # metrics (and thus quality_status/gate_reasons/result notice) are identical,
            # so no re-gate and no notice refresh are needed here.
            superseded_report_path = quality_report_path
            quality_report_path = _write_quality_report_artifact(
                source_name=context.uploaded_filename, payload=quality_report
            )
            # Drop the stale pre-cleanup file only once its replacement is safely on
            # disk, so a rare write failure never leaves the run with zero saved reports.
            if quality_report_path is not None and superseded_report_path and superseded_report_path != quality_report_path:
                try:
                    Path(superseded_report_path).unlink()
                except OSError:
                    pass
            if quality_report_path is not None:
                dependencies.log_event(
                    logging.INFO,
                    "quality_report_saved",
                    "Обновлён acceptance verdict quality report после reader cleanup (delivered DOCX openable).",
                    filename=context.uploaded_filename,
                    artifact_path=quality_report_path,
                    quality_status=quality_report.get("quality_status"),
                    gate_reasons=list(cast(Sequence[str], quality_report.get("gate_reasons") or [])),
                )

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
        if context.processing_operation in {"edit", "translate"}:
            narration_text = None
            narration_error_message = error_message
            emitters.emit_state(
                context.runtime,
                latest_docx_bytes=_resolve_docx_phase_bytes(docx_phase),
                latest_markdown=runtime_display_markdown,
                latest_narration_text=None,
                latest_result_notice=docx_phase["latest_result_notice"],
                last_error=error_message,
            )
            dependencies.log_event(
                logging.WARNING,
                "audiobook_postprocess_failed_base_result_preserved",
                "Audiobook post-pass failed; base DOCX/Markdown result is preserved.",
                filename=context.uploaded_filename,
                processing_operation=context.processing_operation,
                error_message=str(exc),
            )
        else:
            emitters.emit_state(
                context.runtime,
                latest_markdown=runtime_display_markdown,
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
                target_chars=len(runtime_display_markdown),
                context_chars=0,
                log_details=error_message,
            )

    if narration_text is not None:
        try:
            _validate_narration_artifact_text(narration_text)
        except Exception as exc:
            error_message = dependencies.present_error(
                "audiobook_artifact_validation_failed",
                exc,
                "Ошибка проверки текста для ElevenLabs",
                filename=context.uploaded_filename,
                processing_operation=context.processing_operation,
            )
            if context.processing_operation in {"edit", "translate"}:
                narration_text = None
                narration_error_message = error_message
                emitters.emit_state(
                    context.runtime,
                    latest_docx_bytes=_resolve_docx_phase_bytes(docx_phase),
                    latest_markdown=runtime_display_markdown,
                    latest_narration_text=None,
                    latest_result_notice=docx_phase["latest_result_notice"],
                    last_error=error_message,
                )
                dependencies.log_event(
                    logging.WARNING,
                    "audiobook_artifact_validation_failed_base_result_preserved",
                    "Narration artifact validation failed; base DOCX/Markdown result is preserved.",
                    filename=context.uploaded_filename,
                    processing_operation=context.processing_operation,
                    error_message=str(exc),
                )
            else:
                emitters.emit_state(
                    context.runtime,
                    latest_markdown=runtime_display_markdown,
                    latest_docx_bytes=None,
                    latest_narration_text=None,
                    last_error=error_message,
                )
                return emit_failed_result(
                    emitters=emitters,
                    runtime=context.runtime,
                    finalize_stage="Ошибка проверки narration",
                    detail=error_message,
                    progress=1.0,
                    activity_message="Текст для ElevenLabs не прошёл deterministic validation.",
                    block_index=job_count,
                    block_count=job_count,
                    target_chars=len(runtime_display_markdown),
                    context_chars=0,
                    log_details=error_message,
                )
    # Presentation-only: surface the SAME quality_warning the review artifact carries into
    # session state so the unified result screen can render the formatting-review block.
    quality_warning = _build_result_quality_warning(
        quality_report=quality_report,
        latest_result_notice=cast(Mapping[str, str] | None, docx_phase.get("latest_result_notice")),
    )
    emitters.emit_state(
        context.runtime,
        final_generated_paragraph_registry=cast(
            Sequence[Mapping[str, object]] | None, docx_phase.get("final_generated_paragraph_registry")
        ),
        latest_docx_bytes=_resolve_docx_phase_bytes(docx_phase),
        latest_markdown=runtime_display_markdown,
        latest_narration_text=narration_text,
        latest_quality_warning=quality_warning,
        latest_result_notice=docx_phase["latest_result_notice"],
        last_error=narration_error_message,
    )
    # F4 + F12: track the persistence of the PRIMARY result artifacts
    # (``.result.md``/``.result.docx`` via ``write_ui_result_artifacts``) SEPARATELY
    # from the secondary diagnostics and the resume/reuse registries. The result is
    # already delivered from session state (emit_state above), so a persistence
    # failure must NOT hard-fail the run — but only a PRIMARY-artifact failure may
    # claim the result files were not saved. A diagnostics- or registry-only failure
    # logs its own WARNING yet still counts as a fully delivered success, because the
    # user-facing result files DID reach disk.
    primary_artifacts_persisted = True
    primary_artifacts_persist_error: str | None = None
    try:
        reassembly_plan = build_reassembly_plan(
            output_mode=str(getattr(context, "output_mode", "") or ""),
            jobs=list(getattr(context, "jobs", ()) or ()),
            source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
        )
        artifact_writer_kwargs = {
            "source_name": context.uploaded_filename,
            "markdown_text": runtime_display_markdown,
            "docx_bytes": _resolve_docx_phase_bytes(docx_phase),
            "assembly_mode": reassembly_plan.assembly_mode,
            "result_manifest": docx_phase.get("result_manifest")
            or build_reassembly_result_manifest(
                source_name=context.uploaded_filename,
                plan=reassembly_plan,
                jobs=list(getattr(context, "jobs", ()) or ()),
                source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
            ),
        }
        if reassembly_plan.selected_segment_count is not None:
            artifact_writer_kwargs["selected_segment_count"] = reassembly_plan.selected_segment_count
        if quality_warning is not None:
            artifact_writer_kwargs["quality_warning"] = quality_warning
        if narration_text is not None:
            artifact_writer_kwargs["narration_text"] = narration_text
        result_artifact_paths = dict(
            dependencies.write_ui_result_artifacts(**artifact_writer_kwargs)
        )
        # Finding 13: a returned mapping is not proof the primary files reached disk;
        # verify markdown + docx are present, on disk, and non-empty. A failure raises
        # OSError so it funnels into the SAME primary-persistence-failure path below.
        _verify_primary_result_artifacts_or_raise(result_artifact_paths)
    except OSError as exc:
        primary_artifacts_persisted = False
        primary_artifacts_persist_error = f"ui_result_artifacts_save_failed: {exc}"
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
        # F12: reader-cleanup diagnostics are a SECONDARY artifact. A save failure
        # here must NOT claim the delivered result was not saved — it logs its own
        # WARNING and the primary result stays reported as persisted.
        if reader_cleanup_report is not None:
            try:
                result_artifact_paths.update(
                    write_reader_cleanup_diagnostics(
                        cleaned_artifact_paths=result_artifact_paths,
                        raw_markdown=reader_cleanup_raw_markdown or gate_input_markdown,
                        report_payload=reader_cleanup_report,
                    )
                )
            except OSError as exc:
                dependencies.log_event(
                    logging.WARNING,
                    "reader_cleanup_diagnostics_save_failed",
                    "Не удалось сохранить reader cleanup diagnostics; итоговый результат доставлен.",
                    filename=context.uploaded_filename,
                    error_message=str(exc),
                )
        segment_result_records = build_segment_result_records(
            source_name=context.uploaded_filename,
            prepared_source_key=str(getattr(context, "prepared_source_key", "") or ""),
            structure_fingerprint=str(getattr(context, "structure_fingerprint", "") or ""),
            plan=reassembly_plan,
            source_paragraphs=cast(Sequence[object] | None, getattr(context, "source_paragraphs", None)),
            assembly_entries=cast(Sequence[object], docx_phase.get("assembly_entries") or assembly_result.entries),
            result_artifact_paths=result_artifact_paths,
        )
        if segment_result_records:
            try:
                segment_registry_paths = dict(
                    dependencies.write_segment_result_registry(records=segment_result_records)
                )
            except OSError as exc:
                # F12: the segment-result registry is a resume/reuse cache written
                # AFTER the primary result files. Its failure must NOT flip the
                # terminal state to "unpersisted" — the delivered result reached
                # disk. Log a DISTINCT WARNING instead.
                dependencies.log_event(
                    logging.WARNING,
                    "segment_result_registry_save_failed",
                    "Не удалось сохранить persisted segment result registry; итоговый результат доставлен.",
                    filename=context.uploaded_filename,
                    error_message=str(exc),
                )
            else:
                dependencies.log_event(
                    logging.INFO,
                    "segment_result_registry_saved",
                    "Сохранён persisted segment result registry для итоговой сборки.",
                    filename=context.uploaded_filename,
                    segment_count=len(segment_result_records),
                    artifact_paths=segment_registry_paths,
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
    # F4 + F12: the delivered result is still available from session state, but when
    # the PRIMARY result files (``.result.md``/``.result.docx``) did not reach disk we
    # surface a user-visible WARNING notice so the UI shows the files were not saved, and
    # make the terminal log observably distinct from a fully persisted success (WARNING
    # ``processing_completed_unpersisted`` instead of INFO ``processing_completed``). This
    # fires ONLY on a primary-artifact failure — a diagnostics/registry-only failure was
    # already logged as its own WARNING above and never reaches here. The run still
    # genuinely produced a delivered result, so the "completed" progress frame and the
    # "succeeded" return are unchanged.
    if not primary_artifacts_persisted:
        emitters.emit_state(
            context.runtime,
            latest_result_notice={
                "level": "warning",
                "message": "Результат обработан, но не удалось сохранить файлы результата на диск.",
            },
        )
    emitters.emit_finalize(
        context.runtime,
        "Обработка завершена",
        f"Документ обработан за {time.perf_counter() - state.started_at:.1f} сек.",
        1.0,
        "completed",
    )
    emitters.emit_activity(context.runtime, "Документ обработан полностью.")
    _completed_log_fields = dict(
        filename=context.uploaded_filename,
        block_count=job_count,
        final_markdown_chars=len(runtime_display_markdown),
        narration_chars=len(narration_text or ""),
        elapsed_seconds=round(time.perf_counter() - state.started_at, 2),
        audiobook_postprocess_enabled=_should_run_audiobook_postprocess(context=context),
        reader_cleanup_enabled=_should_run_reader_cleanup(context=context),
    )
    if primary_artifacts_persisted:
        dependencies.log_event(
            logging.INFO,
            "processing_completed",
            "Документ обработан полностью",
            **_completed_log_fields,
        )
    else:
        dependencies.log_event(
            logging.WARNING,
            "processing_completed_unpersisted",
            "Документ обработан полностью, но итоговые файлы результата не сохранены на диск.",
            reason=primary_artifacts_persist_error or "ui_result_artifacts_save_failed",
            **_completed_log_fields,
        )
    emitters.emit_log(
        context.runtime,
        status="DONE",
        block_index=job_count,
        block_count=job_count,
        target_chars=len(runtime_display_markdown),
        context_chars=0,
        details=f"весь документ обработан за {time.perf_counter() - state.started_at:.1f} сек.",
    )
    return "succeeded"
