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


def _reader_cleanup_failed_chunk_ratio_notice(report_payload: Mapping[str, object] | None) -> dict[str, object] | None:
    """Typed result notice for a pass aborted by ``max_failed_chunk_ratio`` (spec 052 item 2).

    ``run_reader_cleanup`` does not raise for this: under ``policy="advisory"`` it returns a
    report with ``stage_status="failed"`` and ``changed=False``. Without this branch the run
    reached the user as the same yellow "cleanup was only partially available" warning a
    single unavailable chunk produces — i.e. a book that was cleaned not at all looked exactly
    like a book that was cleaned almost entirely.
    """
    if not isinstance(report_payload, Mapping):
        return None
    failure = report_payload.get("failure")
    if not isinstance(failure, Mapping) or str(failure.get("kind") or "") != "failed_chunk_ratio_exceeded":
        return None
    stats = report_payload.get("stats")
    stats_mapping = stats if isinstance(stats, Mapping) else {}
    failed_chunk_count = stats_mapping.get("failed_chunk_count")
    cleanup_chunk_count = stats_mapping.get("cleanup_chunk_count")
    try:
        failed_chunk_ratio_pct = round(float(cast(Any, failure.get("failed_chunk_ratio"))) * 100, 1)
    except (TypeError, ValueError):
        failed_chunk_ratio_pct = 0.0
    try:
        max_failed_chunk_ratio_pct = round(float(cast(Any, failure.get("max_failed_chunk_ratio"))) * 100, 1)
    except (TypeError, ValueError):
        max_failed_chunk_ratio_pct = 0.0
    params: dict[str, object] = {
        "failed_chunk_count": failed_chunk_count if isinstance(failed_chunk_count, int) else 0,
        "cleanup_chunk_count": cleanup_chunk_count if isinstance(cleanup_chunk_count, int) else 0,
        "failed_chunk_ratio_pct": failed_chunk_ratio_pct,
        "max_failed_chunk_ratio_pct": max_failed_chunk_ratio_pct,
    }
    return {
        "kind": "cleanup",
        "level": "error",
        "message_key": "result.cleanup_aborted_failed_chunk_ratio",
        "params": params,
        "message": (
            f"Reader cleanup was aborted: {params['failed_chunk_count']} of {params['cleanup_chunk_count']} "
            f"chunks failed ({failed_chunk_ratio_pct}%), above the allowed {max_failed_chunk_ratio_pct}%. "
            "No cleanup was applied; the translated document was preserved."
        ),
    }


def _reader_cleanup_image_anchor_discard_notice(report_payload: Mapping[str, object] | None) -> dict[str, object] | None:
    """Typed result notice for a cleanup discarded to keep an image anchor in place.

    Spec 052 item 5 refuses to deliver a cleanup that lost an image anchor, because the
    only alternative — re-appending the anchor — moves a figure to the end of the book.
    Refusing is right; refusing SILENTLY was not. The discard produced ``changed=False``
    with ``stage_status="completed"``, no failure and no notice, so a run that threw away
    every accepted operation was indistinguishable from a run that found nothing to do.
    """
    if not isinstance(report_payload, Mapping):
        return None
    failure = report_payload.get("failure")
    if not isinstance(failure, Mapping) or str(failure.get("kind") or "") != "docx_image_anchor_lost_cleanup_discarded":
        return None
    missing_image_id_count = failure.get("missing_docx_image_id_count")
    discarded_cleanup_operation_count = failure.get("discarded_cleanup_operation_count")
    # No ``rejected_cleanup_operation_count`` param: the failure never carried a real one.
    # Reaching this branch means the rejection did NOT succeed, and the entries it counted are
    # only written when it did, so the number was a hardcoded zero dressed as a measurement.
    params: dict[str, object] = {
        "missing_image_id_count": missing_image_id_count if isinstance(missing_image_id_count, int) else 0,
        "discarded_cleanup_operation_count": (
            discarded_cleanup_operation_count if isinstance(discarded_cleanup_operation_count, int) else 0
        ),
    }
    return {
        "kind": "cleanup",
        "level": "error",
        "message_key": "result.cleanup_discarded_image_anchor_lost",
        "params": params,
        "message": (
            f"Reader cleanup was discarded: {params['missing_image_id_count']} image anchor(s) would have been "
            f"lost, and the operation responsible could not be identified and rejected. All "
            f"{params['discarded_cleanup_operation_count']} accepted operation(s) were dropped; the translated "
            "document was preserved with every image in place."
        ),
    }


def _reader_cleanup_anchor_repair_rollback_notice(report_payload: Mapping[str, object] | None) -> dict[str, object] | None:
    """Typed result notice for an anchor-repair pass rolled back to keep an anchor in place.

    Round-10 P2-2. The partial sibling of the wholesale discard above: the first pass ships,
    but the anchor-repair increment lost an image anchor and was thrown away. It is not a
    stage failure — ``stage_status`` stays "completed" and the delivered document is a real
    cleanup — so it gets a warning, not an error. What it must not be is invisible, which is
    what it was: no ``failure``, no notice, and the only record a raw string in ``warnings``
    that the UI never renders. The owner asked for figure captions to be repaired, paid for
    the pass, and got a document where they were not, with nothing on screen saying so.
    """
    if not isinstance(report_payload, Mapping):
        return None
    image_reconciliation = report_payload.get("image_reconciliation")
    if not isinstance(image_reconciliation, Mapping):
        return None
    if not image_reconciliation.get("anchor_repair_discarded_for_missing_image_ids"):
        return None
    missing_after_repair = image_reconciliation.get("missing_after_repair")
    missing_image_id_count = len(missing_after_repair) if isinstance(missing_after_repair, (list, tuple)) else 0
    discarded_count = image_reconciliation.get("anchor_repair_discarded_cleanup_operation_count")
    params: dict[str, object] = {
        "missing_image_id_count": missing_image_id_count,
        "discarded_cleanup_operation_count": discarded_count if isinstance(discarded_count, int) else 0,
    }
    return {
        "kind": "cleanup",
        "level": "warning",
        "message_key": "result.cleanup_anchor_repair_rolled_back",
        "params": params,
        "message": (
            f"The reader-cleanup image-anchor repair pass was rolled back: it would have lost "
            f"{params['missing_image_id_count']} image anchor(s), so its "
            f"{params['discarded_cleanup_operation_count']} operation(s) were dropped. The rest of the "
            "cleanup was delivered with every image in place."
        ),
    }


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

    # The anchor-repair guidance must ship with the anchor-repair requests and ONLY with
    # them. Both prompts used to be built once, before ``anchor_targets`` was even
    # resolved (~170 lines below), and without the flag — so an anchor-repair pass would
    # have gone out without its own instructions, while every ordinary cleanup request
    # would have carried them had the flag simply been set here. Build both variants and
    # pick per request from the payload's ``pass_name``, which ``run_reader_cleanup`` sets
    # to "anchor_repair" for that pass and which the schema-repair payload copies through
    # (``_parse._build_cleanup_schema_repair_payload``).
    system_prompt = build_reader_cleanup_system_prompt()
    anchor_repair_system_prompt = build_reader_cleanup_system_prompt(include_anchor_repair_guidance=True)
    schema_repair_system_prompt = build_reader_cleanup_schema_repair_system_prompt()
    anchor_repair_schema_repair_system_prompt = build_reader_cleanup_schema_repair_system_prompt(
        include_anchor_repair_guidance=True
    )
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
        request_system_prompt = anchor_repair_system_prompt if pass_name == "anchor_repair" else system_prompt
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
            system_prompt=request_system_prompt,
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
        repair_pass_name = str(request_payload.get("pass_name") or "reader_cleanup")
        request_system_prompt = (
            anchor_repair_schema_repair_system_prompt
            if repair_pass_name == "anchor_repair"
            else schema_repair_system_prompt
        )
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
            system_prompt=request_system_prompt,
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
            cleanup_notice: dict[str, object] | None = None
            legacy_cleanup_notice = None
            # Spec 052 item 2: a run aborted by the failed-chunk ratio must not read like an
            # ordinary "nothing to clean" run. It carries stage_status="failed" and applied
            # NOTHING, so it gets its own error-level notice naming the numbers, not the
            # generic advisory warning a single unavailable chunk produces.
            aborted_notice = _reader_cleanup_failed_chunk_ratio_notice(cleanup_result.report_payload)
            # Spec 052 item 5 + round-9 P1-A: the other way a pass can apply nothing while
            # having done all the work — every accepted operation discarded to keep an
            # image anchor where it belongs. Same standing as the ratio abort: an
            # error-level notice with the numbers, not silence.
            discarded_notice = _reader_cleanup_image_anchor_discard_notice(cleanup_result.report_payload)
            # Round-10 P2-2: and the partial form of the same event. Reachable here too — a
            # first pass that changed nothing still runs the anchor-repair pass, and rolling
            # that increment back leaves the run at changed=False.
            anchor_rollback_notice = _reader_cleanup_anchor_repair_rollback_notice(cleanup_result.report_payload)
            if aborted_notice is not None:
                cleanup_notice = aborted_notice
                dependencies.log_event(
                    logging.WARNING,
                    "reader_cleanup_failed_chunk_ratio_exceeded",
                    "Reader cleanup post-pass прерван: доля упавших чанков превысила порог; очистка не применялась.",
                    filename=context.uploaded_filename,
                    policy=config.policy,
                    model=config.model,
                    # ``params`` already carries cleanup_chunk_count / failed_chunk_count
                    # and the two percentages; do not also pass them explicitly.
                    **cast(Mapping[str, object], aborted_notice.get("params") or {}),
                )
            elif discarded_notice is not None:
                cleanup_notice = discarded_notice
                dependencies.log_event(
                    logging.WARNING,
                    "reader_cleanup_image_anchor_lost_cleanup_discarded",
                    "Reader cleanup post-pass отброшен целиком: очистка потеряла якорь изображения; документ сохранён.",
                    filename=context.uploaded_filename,
                    policy=config.policy,
                    model=config.model,
                    **cast(Mapping[str, object], discarded_notice.get("params") or {}),
                )
            elif anchor_rollback_notice is not None:
                cleanup_notice = anchor_rollback_notice
                dependencies.log_event(
                    logging.WARNING,
                    "reader_cleanup_anchor_repair_discarded_for_missing_image_anchor",
                    "Anchor-repair проход reader cleanup откачен: он терял якорь изображения; остальная очистка сохранена.",
                    filename=context.uploaded_filename,
                    policy=config.policy,
                    model=config.model,
                    **cast(Mapping[str, object], anchor_rollback_notice.get("params") or {}),
                )
            elif _reader_cleanup_count_is_positive(stats.get("failed_chunk_count")):
                cleanup_notice = {
                    "kind": "cleanup",
                    "level": "warning",
                    "message_key": "result.cleanup_advisory_failed",
                    "message": "Reader cleanup was only partially available; the accepted base content was preserved.",
                }
            if cleanup_notice is not None:
                legacy_cleanup_notice = {
                    "level": str(cleanup_notice["level"]),
                    "message": str(cleanup_notice["message"]),
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
        # Round-10 P2-2. This is the ordinary way an anchor-repair rollback reaches an owner:
        # the first pass changed the document, so delivery goes down this branch. It takes
        # precedence over the generic "some chunks were unavailable" advisory because it names
        # a specific thing that did not happen to the delivered book.
        anchor_rollback_notice = _reader_cleanup_anchor_repair_rollback_notice(cleanup_result.report_payload)
        if anchor_rollback_notice is not None:
            cleanup_notice = anchor_rollback_notice
            dependencies.log_event(
                logging.WARNING,
                "reader_cleanup_anchor_repair_discarded_for_missing_image_anchor",
                "Anchor-repair проход reader cleanup откачен: он терял якорь изображения; остальная очистка доставлена.",
                filename=context.uploaded_filename,
                policy=config.policy,
                model=config.model,
                **cast(Mapping[str, object], anchor_rollback_notice.get("params") or {}),
            )
        elif _reader_cleanup_count_is_positive(stats.get("failed_chunk_count")):
            cleanup_notice = {
                "kind": "cleanup",
                "level": "warning",
                "message_key": "result.cleanup_advisory_failed",
                "message": "Reader cleanup completed with unavailable chunks; accepted cleanup operations were preserved.",
            }
        if cleanup_notice is not None:
            legacy_cleanup_notice = {
                "level": str(cleanup_notice["level"]),
                "message": str(cleanup_notice["message"]),
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
