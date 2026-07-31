"""Reader-cleanup LLM post-pass orchestrator (spec 031 Cluster C).

Behaviour-preserving extraction from ``pipeline/late_phases.py`` of
``_run_reader_cleanup_postprocess``: the reader-cleanup post-pass that drives the LLM only
through injected ``dependencies`` callables (offline-drivable — no module-level SDK client),
then rebuilds the delivered DOCX/Markdown via the Cluster B rebuild helpers. ``late_phases``
re-exports the name so ``late_phases._run_reader_cleanup_postprocess`` keeps resolving for the
still-in-``late_phases`` finalize caller and the test namespace. The two runtime-display
normalizers it needs still live in ``late_phases`` (Cluster A) and are reached via a lazy
import to avoid a circular import. No module-level mutable state.
"""

import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from docxaicorrector.pipeline.reader_cleanup_rebuild import (
    ReaderCleanupPostprocessResult,
    _build_docx_rebuild_markdown_after_reader_cleanup,
    _build_reader_cleanup_block_identity_metadata,
    _derive_reader_cleanup_generated_paragraph_registry,
    _rebuild_docx_for_markdown,
    _resolve_final_generated_paragraph_registry,
    _resolve_reader_cleanup_anchor_repair_targets,
    _should_run_reader_cleanup,
    _write_reader_cleanup_lineage_artifact,
)
from docxaicorrector.pipeline.contracts import LatePhaseStopped
from docxaicorrector.pipeline.text_call_support import _resolve_text_call_target
from docxaicorrector.reader_cleanup_mvp import (
    ReaderCleanupStageError,
    build_reader_cleanup_global_plan_system_prompt,
    build_reader_cleanup_schema_repair_system_prompt,
    build_reader_cleanup_system_prompt,
    resolve_reader_cleanup_config,
    run_reader_cleanup,
)


def _reader_cleanup_count_is_positive(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return False
    try:
        return int(value) > 0
    except ValueError:
        return False


def _run_reader_cleanup_postprocess(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    cleanup_input_markdown: str,
    runtime_display_markdown: str,
    base_docx_bytes: bytes | None,
    job_count: int,
    processed_image_assets: Sequence[Any],
    formatting_registry: Sequence[Mapping[str, object]] | None = None,
    base_docx_builder: Callable[[], bytes] | None = None,
) -> ReaderCleanupPostprocessResult:
    from docxaicorrector.pipeline.late_phases import (
        _normalize_final_markdown_for_runtime_display,
        _restore_image_heading_lines_from_registry,
    )

    def _base_docx_bytes() -> bytes:
        _raise_if_stopped()
        if base_docx_bytes is not None:
            return base_docx_bytes
        if base_docx_builder is not None:
            built_docx_bytes = base_docx_builder()
            _raise_if_stopped()
            return built_docx_bytes
        return b""

    def _raise_if_stopped() -> None:
        stop_predicate = getattr(dependencies, "should_stop_processing", None)
        if callable(stop_predicate) and stop_predicate(context.runtime):
            raise LatePhaseStopped()

    active_formatting_registry = formatting_registry or state.generated_paragraph_registry or None
    base_final_generated_registry = _resolve_final_generated_paragraph_registry(
        markdown_text=runtime_display_markdown,
        generated_paragraph_registry=active_formatting_registry,
    )

    if not _should_run_reader_cleanup(context=context):
        return ReaderCleanupPostprocessResult(
            markdown=runtime_display_markdown,
            docx_bytes=_base_docx_bytes(),
            report=None,
            raw_markdown=None,
            result_notice=None,
            final_generated_paragraph_registry=base_final_generated_registry,
        )

    _raise_if_stopped()

    config = resolve_reader_cleanup_config(app_config=context.app_config, fallback_model=context.model)
    if not config.enabled:
        return ReaderCleanupPostprocessResult(
            markdown=runtime_display_markdown,
            docx_bytes=_base_docx_bytes(),
            report=None,
            raw_markdown=None,
            result_notice=None,
            final_generated_paragraph_registry=base_final_generated_registry,
        )
    if config.drop_back_matter:
        dependencies.log_event(
            logging.WARNING,
            "reader_cleanup_drop_back_matter_unsupported",
            "Reader cleanup drop_back_matter is currently unsupported; proceeding without semantic back-matter deletion.",
            filename=context.uploaded_filename,
            policy=config.policy,
            model=config.model,
        )

    system_prompt = build_reader_cleanup_system_prompt()
    schema_repair_system_prompt = build_reader_cleanup_schema_repair_system_prompt()
    global_plan_system_prompt = build_reader_cleanup_global_plan_system_prompt()
    fallback_client = None
    if not callable(getattr(dependencies, "resolve_model_selector", None)) or not callable(
        getattr(dependencies, "get_client_for_model_selector", None)
    ):
        fallback_client = dependencies.get_client()
    client, model_id, model_selector, model_provider = _resolve_text_call_target(
        selector=config.model,
        context=context,
        dependencies=dependencies,
        fallback_client=fallback_client,
    )

    emitters.emit_activity(context.runtime, "Запущен reader cleanup post-pass для итогового Markdown.")
    cleanup_identity_metadata, cleanup_identity_diagnostics = _build_reader_cleanup_block_identity_metadata(
        raw_markdown=cleanup_input_markdown,
        generated_paragraph_registry=active_formatting_registry,
    )

    def _global_plan_provider(request_payload: Mapping[str, object]) -> str:
        _raise_if_stopped()
        target_text = json.dumps(request_payload, ensure_ascii=False, indent=2)
        started_at = time.perf_counter()
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_global_plan_started",
            "Запущен advisory global reader cleanup plan для полного raw Markdown.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": "reader_cleanup_global_plan"},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            target_chars=len(target_text),
        )
        response = dependencies.generate_markdown_block(
            client=client,
            model=model_id,
            system_prompt=global_plan_system_prompt,
            target_text=target_text,
            context_before="",
            context_after="",
            max_retries=context.max_retries,
            expected_paragraph_ids=None,
            marker_mode=False,
        )
        _raise_if_stopped()
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_global_plan_completed",
            "Advisory global reader cleanup plan завершён.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": "reader_cleanup_global_plan"},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            output_chars=len(response),
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        return response

    def _operation_provider(request_payload: Mapping[str, object], chunk_index: int, chunk_count: int) -> str:
        _raise_if_stopped()
        target_text = json.dumps(request_payload, ensure_ascii=False, indent=2)
        context_before = str(request_payload.get("context_before_preview", "") or "")
        context_after = str(request_payload.get("context_after_preview", "") or "")
        pass_name = str(request_payload.get("pass_name") or "reader_cleanup")
        started_at = time.perf_counter()
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_chunk_started",
            "Запущен reader cleanup post-pass для cleanup chunk.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": pass_name},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            target_chars=len(target_text),
            context_before_chars=len(context_before),
            context_after_chars=len(context_after),
        )
        response = dependencies.generate_markdown_block(
            client=client,
            model=model_id,
            system_prompt=system_prompt,
            target_text=target_text,
            context_before=context_before,
            context_after=context_after,
            max_retries=context.max_retries,
            expected_paragraph_ids=None,
            marker_mode=False,
        )
        _raise_if_stopped()
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_chunk_completed",
            "Reader cleanup post-pass для cleanup chunk завершён.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": pass_name},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            output_chars=len(response),
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        return response

    def _repair_provider(request_payload: Mapping[str, object], chunk_index: int, chunk_count: int) -> str:
        _raise_if_stopped()
        target_text = json.dumps(request_payload, ensure_ascii=False, indent=2)
        started_at = time.perf_counter()
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_schema_repair_started",
            "Запущен schema-repair retry для cleanup chunk.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": "reader_cleanup_schema_repair"},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            target_chars=len(target_text),
        )
        response = dependencies.generate_markdown_block(
            client=client,
            model=model_id,
            system_prompt=schema_repair_system_prompt,
            target_text=target_text,
            context_before="",
            context_after="",
            max_retries=context.max_retries,
            expected_paragraph_ids=None,
            marker_mode=False,
        )
        _raise_if_stopped()
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_schema_repair_completed",
            "Schema-repair retry для cleanup chunk завершён.",
            filename=context.uploaded_filename,
            operation="translate",
            **{"pass": "reader_cleanup_schema_repair"},
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
            output_chars=len(response),
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        return response

    anchor_targets = _resolve_reader_cleanup_anchor_repair_targets(context=context)

    try:
        cleanup_result = run_reader_cleanup(
            markdown_text=cleanup_input_markdown,
            config=config,
            operation_provider=_operation_provider,
            repair_provider=_repair_provider,
            global_plan_provider=_global_plan_provider,
            anchor_operation_provider=_operation_provider if anchor_targets else None,
            anchor_targets=anchor_targets,
            model_resolution={
                "requested_selector": config.model,
                "canonical_selector": model_selector,
                "provider": model_provider,
                "model_id": model_id,
            },
            block_metadata_by_index=cleanup_identity_metadata,
        )
        if not cleanup_result.changed:
            runtime_display_markdown = _restore_image_heading_lines_from_registry(
                runtime_display_markdown,
                base_final_generated_registry,
            )
            base_final_generated_registry = _resolve_final_generated_paragraph_registry(
                markdown_text=runtime_display_markdown,
                generated_paragraph_registry=active_formatting_registry,
            )
            stats = cast(Mapping[str, object], cleanup_result.report_payload.get("stats") or {})
            cleanup_notice = None
            legacy_cleanup_notice = None
            if _reader_cleanup_count_is_positive(stats.get("failed_chunk_count")):
                cleanup_notice = {
                    "kind": "cleanup",
                    "level": "warning",
                    "message_key": "result.cleanup_advisory_failed",
                    "message": "Reader cleanup was only partially available; the accepted base content was preserved.",
                }
                legacy_cleanup_notice = {
                    "level": cleanup_notice["level"],
                    "message": cleanup_notice["message"],
                }
            dependencies.log_event(
                logging.INFO,
                "reader_cleanup_noop",
                "Reader cleanup post-pass завершён без принятых удалений.",
                filename=context.uploaded_filename,
                policy=config.policy,
                model=config.model,
                warnings=list(cleanup_result.report_payload.get("warnings", []) or []),
                cleanup_chunk_count=stats.get("cleanup_chunk_count"),
                failed_chunk_count=stats.get("failed_chunk_count"),
                proposed_delete_block_count=stats.get("proposed_delete_block_count"),
                ignored_delete_block_count=stats.get("ignored_delete_block_count"),
                cleanup_identity_status=cleanup_identity_diagnostics.get("status"),
                cleanup_identity_reason=cleanup_identity_diagnostics.get("reason"),
                cleanup_identity_id_matched_block_count=cleanup_identity_diagnostics.get("id_matched_block_count"),
                cleanup_identity_gap_count=cleanup_identity_diagnostics.get("gap_count"),
                cleanup_identity_image_gap_count=cleanup_identity_diagnostics.get("image_gap_count"),
                cleanup_identity_text_gap_count=cleanup_identity_diagnostics.get("text_gap_count"),
            )
            return ReaderCleanupPostprocessResult(
                markdown=runtime_display_markdown,
                docx_bytes=_base_docx_bytes(),
                report=cleanup_result.report_payload,
                raw_markdown=cleanup_result.raw_markdown,
                result_notice=legacy_cleanup_notice,
                final_generated_paragraph_registry=base_final_generated_registry,
                result_notices=(cleanup_notice,) if cleanup_notice is not None else (),
            )

        cleanup_formatting_registry, cleanup_formatting_lineage = _derive_reader_cleanup_generated_paragraph_registry(
            generated_paragraph_registry=active_formatting_registry,
            cleanup_report=cleanup_result.report_payload,
            raw_markdown=cleanup_result.raw_markdown,
            cleanup_block_metadata_by_index=cleanup_identity_metadata,
        )
        cleaned_runtime_display_markdown = _restore_image_heading_lines_from_registry(
            _normalize_final_markdown_for_runtime_display(
                cleanup_result.cleaned_markdown,
                cleanup_formatting_registry,
            ),
            cleanup_formatting_registry,
        )
        docx_rebuild_markdown = _build_docx_rebuild_markdown_after_reader_cleanup(
            raw_markdown=cleanup_result.raw_markdown,
            cleaned_markdown=cleaned_runtime_display_markdown,
            accepted_delete_block_ids=cleanup_result.accepted_delete_block_ids,
            cleanup_block_metadata_by_index=cleanup_identity_metadata,
            generated_paragraph_registry=cleanup_formatting_registry,
        )
        preliminary_final_generated_registry = _resolve_final_generated_paragraph_registry(
            markdown_text=docx_rebuild_markdown,
            generated_paragraph_registry=cleanup_formatting_registry,
        )
        docx_rebuild_markdown = _restore_image_heading_lines_from_registry(
            docx_rebuild_markdown,
            preliminary_final_generated_registry,
        )
        cleaned_runtime_display_markdown = _restore_image_heading_lines_from_registry(
            cleaned_runtime_display_markdown,
            preliminary_final_generated_registry,
        )
        _raise_if_stopped()
        cleanup_lineage_artifact_path = _write_reader_cleanup_lineage_artifact(
            filename=context.uploaded_filename,
            raw_markdown=cleanup_result.raw_markdown,
            cleaned_markdown=cleaned_runtime_display_markdown,
            cleanup_report=cleanup_result.report_payload,
            active_formatting_registry=active_formatting_registry,
            cleanup_identity_metadata=cleanup_identity_metadata,
            cleanup_identity_diagnostics=cleanup_identity_diagnostics,
            cleanup_formatting_registry=cleanup_formatting_registry,
            cleanup_formatting_lineage=cleanup_formatting_lineage,
        )
        _raise_if_stopped()
        cleaned_docx_bytes = _rebuild_docx_for_markdown(
            markdown_text=docx_rebuild_markdown,
            context=context,
            dependencies=dependencies,
            state=state,
            processed_image_assets=processed_image_assets,
            generated_paragraph_registry=preliminary_final_generated_registry,
        )
        _raise_if_stopped()
        final_generated_registry = _resolve_final_generated_paragraph_registry(
            markdown_text=docx_rebuild_markdown,
            generated_paragraph_registry=preliminary_final_generated_registry,
        )
        emitters.emit_state(
            context.runtime,
            final_generated_paragraph_registry=final_generated_registry,
            latest_markdown=cleaned_runtime_display_markdown,
            latest_docx_bytes=cleaned_docx_bytes,
        )
        stats = cast(Mapping[str, object], cleanup_result.report_payload.get("stats") or {})
        cleanup_notice = None
        legacy_cleanup_notice = None
        if _reader_cleanup_count_is_positive(stats.get("failed_chunk_count")):
            cleanup_notice = {
                "kind": "cleanup",
                "level": "warning",
                "message_key": "result.cleanup_advisory_failed",
                "message": "Reader cleanup completed with unavailable chunks; accepted cleanup operations were preserved.",
            }
            legacy_cleanup_notice = {
                "level": cleanup_notice["level"],
                "message": cleanup_notice["message"],
            }
        dependencies.log_event(
            logging.INFO,
            "reader_cleanup_applied",
            "Reader cleanup post-pass применил bounded cleanup operations к итоговому Markdown.",
            filename=context.uploaded_filename,
            policy=config.policy,
            model=config.model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            accepted_delete_block_count=len(cleanup_result.accepted_delete_block_ids),
            accepted_cleanup_operation_count=stats.get("accepted_cleanup_operation_count"),
            ignored_delete_block_count=stats.get("ignored_delete_block_count"),
            ignored_cleanup_operation_count=stats.get("ignored_cleanup_operation_count"),
            proposed_delete_block_count=stats.get("proposed_delete_block_count"),
            proposed_cleanup_operation_count=stats.get("proposed_cleanup_operation_count"),
            cleanup_chunk_count=stats.get("cleanup_chunk_count"),
            failed_chunk_count=stats.get("failed_chunk_count"),
            formatting_lineage_status=cleanup_formatting_lineage.get("status"),
            formatting_lineage_reason=cleanup_formatting_lineage.get("reason"),
            formatting_lineage_sparse_alignment_failure_reason=cleanup_formatting_lineage.get("sparse_alignment_failure_reason"),
            formatting_lineage_alignment_mode=cleanup_formatting_lineage.get("alignment_mode"),
            formatting_lineage_alignment_gap_count=cleanup_formatting_lineage.get("alignment_gap_count"),
            formatting_lineage_raw_cleanup_block_count=cleanup_formatting_lineage.get("raw_cleanup_block_count"),
            formatting_lineage_generated_registry_count=cleanup_formatting_lineage.get("generated_registry_count")
            or cleanup_formatting_lineage.get("original_registry_count"),
            formatting_lineage_derived_registry_count=cleanup_formatting_lineage.get("derived_registry_count"),
            formatting_lineage_applied_operation_count=cleanup_formatting_lineage.get("applied_operation_count"),
            cleanup_identity_status=cleanup_identity_diagnostics.get("status"),
            cleanup_identity_reason=cleanup_identity_diagnostics.get("reason"),
            cleanup_identity_raw_cleanup_block_count=cleanup_identity_diagnostics.get("raw_cleanup_block_count"),
            cleanup_identity_generated_registry_count=cleanup_identity_diagnostics.get("generated_registry_count"),
            cleanup_identity_id_matched_block_count=cleanup_identity_diagnostics.get("id_matched_block_count"),
            cleanup_identity_missing_id_registry_entry_count=cleanup_identity_diagnostics.get("missing_id_registry_entry_count"),
            cleanup_identity_gap_count=cleanup_identity_diagnostics.get("gap_count"),
            cleanup_identity_image_gap_count=cleanup_identity_diagnostics.get("image_gap_count"),
            cleanup_identity_text_gap_count=cleanup_identity_diagnostics.get("text_gap_count"),
            reader_cleanup_lineage_artifact_path=cleanup_lineage_artifact_path,
            cleaned_markdown_chars=len(cleaned_runtime_display_markdown),
            raw_markdown_chars=len(cleanup_result.raw_markdown),
        )
        return ReaderCleanupPostprocessResult(
            markdown=cleaned_runtime_display_markdown,
            docx_bytes=cleaned_docx_bytes,
            report=cleanup_result.report_payload,
            raw_markdown=cleanup_result.raw_markdown,
            result_notice=legacy_cleanup_notice,
            final_generated_paragraph_registry=final_generated_registry,
            result_notices=(cleanup_notice,) if cleanup_notice is not None else (),
        )
    except Exception as exc:
        error_message = dependencies.present_error(
            "reader_cleanup_failed",
            exc,
            "Ошибка reader cleanup post-pass",
            filename=context.uploaded_filename,
            processing_operation=context.processing_operation,
        )
        strict_report = exc.report_payload if isinstance(exc, ReaderCleanupStageError) else None
        strict_raw_markdown = exc.raw_markdown if isinstance(exc, ReaderCleanupStageError) else cleanup_input_markdown
        typed_result_notice: dict[str, str] = {
            "kind": "cleanup",
            "level": "warning",
            "message_key": "result.cleanup_advisory_failed",
            "message": "Reader cleanup could not be applied; the base translated result was preserved.",
        }
        if config.policy == "strict":
            typed_result_notice["message"] = "Reader cleanup strict stage failed; preserved the raw translated result without cleanup."
            dependencies.log_event(
                logging.WARNING,
                "reader_cleanup_strict_failed_base_result_preserved",
                "Reader cleanup strict stage failed; base DOCX/Markdown result is preserved.",
                filename=context.uploaded_filename,
                processing_operation=context.processing_operation,
                policy=config.policy,
                error_message=str(exc),
                report_stage_status=(strict_report or {}).get("stage_status") if isinstance(strict_report, Mapping) else None,
            )
        else:
            dependencies.log_event(
                logging.WARNING,
                "reader_cleanup_failed_base_result_preserved",
                "Reader cleanup post-pass failed; base DOCX/Markdown result is preserved.",
                filename=context.uploaded_filename,
                processing_operation=context.processing_operation,
                policy=config.policy,
                error_message=str(exc),
            )
        emitters.emit_state(
            context.runtime,
            final_generated_paragraph_registry=base_final_generated_registry,
            latest_docx_bytes=_base_docx_bytes(),
            latest_markdown=runtime_display_markdown,
            latest_narration_text=None,
            latest_result_notice={
                "level": typed_result_notice["level"],
                "message": typed_result_notice["message"],
            },
            last_error=error_message,
        )
        return ReaderCleanupPostprocessResult(
            markdown=runtime_display_markdown,
            docx_bytes=_base_docx_bytes(),
            report=cast(dict[str, object] | None, strict_report),
            raw_markdown=strict_raw_markdown,
            result_notice={
                "level": typed_result_notice["level"],
                "message": typed_result_notice["message"],
            },
            final_generated_paragraph_registry=base_final_generated_registry,
            result_notices=(typed_result_notice,),
        )
