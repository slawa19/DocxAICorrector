import logging
import json
import time
import uuid
from pathlib import Path
from typing import Any, Literal, TypeAlias

from docxaicorrector.pipeline.job_results import persist_terminal_job_result
from docxaicorrector.pipeline.output_validation import validate_translated_toc_block
from docxaicorrector.runtime.artifact_retention import prune_artifact_dir


PipelineResult: TypeAlias = Literal["succeeded", "failed", "stopped"]
TOC_VALIDATION_RETRY_BUDGET = 2
TOC_RETRY_HARDENING_ATTEMPT = 2
CONTROLLED_BLOCK_FAILURE_POLICY: dict[str, dict[str, str]] = {
    "empty": {"decision": "fallback_continue", "fallback_kind": "empty_processed_block"},
    "empty_processed_block": {"decision": "fallback_continue", "fallback_kind": "empty_processed_block"},
    "source_text_fallback": {"decision": "fallback_continue", "fallback_kind": "source_text_fallback"},
    "english_residual_output": {"decision": "fallback_continue", "fallback_kind": "english_residual_output"},
    "heading_only_output": {"decision": "fallback_continue", "fallback_kind": "heading_only_output"},
    "bullet_heading_output": {"decision": "fallback_continue", "fallback_kind": "bullet_heading_output"},
    "toc_body_concat": {"decision": "fallback_continue", "fallback_kind": "toc_body_concat"},
    "missing_provider_client": {"decision": "fail"},
    "missing_provider_configuration": {"decision": "fail"},
    "missing_source_segment": {"decision": "fail"},
    "missing_translated_segment": {"decision": "fail"},
    "final_translated_book_incomplete": {"decision": "fail"},
    "marker_registry_failure": {"decision": "fail"},
    "marker_anchor_failure": {"decision": "fail"},
    "invalid_processing_job": {"decision": "fail"},
    "corrupted_block": {"decision": "fail"},
    "source_extraction_failure": {"decision": "fail"},
}
CONTROLLED_BLOCK_FALLBACK_DIR = Path(".run") / "block_fallbacks"
# Retention budget for controlled-block fallback diagnostics (F26). Each rejected
# block writes a uuid-suffixed artifact that never overwrites, so this flat family
# grew without bound. Values match the diagnostic tier used elsewhere under
# ``.run/`` (7-day age, small count); pruning runs right after each write.
BLOCK_FALLBACK_ARTIFACTS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
BLOCK_FALLBACK_ARTIFACTS_MAX_COUNT = 200


def _safe_artifact_stem(value: str) -> str:
    stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return stem.strip("_")[:80] or "document"


def _write_controlled_block_fallback_artifact(
    *,
    context: Any,
    initialization: Any,
    index: int,
    rejection_kind: str,
    target_text: str,
    processed_chunk: str,
) -> str | None:
    payload = {
        "schema_version": 1,
        "filename": str(getattr(context, "uploaded_filename", "") or ""),
        "block_index": index,
        "block_count": initialization.job_count,
        "fallback_kind": "controlled_processed_block_rejection",
        "output_classification": rejection_kind,
        "target_text_preview": target_text[:1000],
        "processed_chunk_preview": processed_chunk[:1000],
        "note": "Block output was retained so full-document assembly can continue; inspect this artifact before treating the block as clean.",
    }
    try:
        CONTROLLED_BLOCK_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        artifact_path = (
            CONTROLLED_BLOCK_FALLBACK_DIR
            / f"{_safe_artifact_stem(str(getattr(context, 'uploaded_filename', '') or 'document'))}_block_{index}_{uuid.uuid4().hex[:8]}.json"
        )
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_artifact_dir(
            target_dir=CONTROLLED_BLOCK_FALLBACK_DIR,
            max_age_seconds=BLOCK_FALLBACK_ARTIFACTS_MAX_AGE_SECONDS,
            max_count=BLOCK_FALLBACK_ARTIFACTS_MAX_COUNT,
            glob="*.json",
            emit_log=False,
        )
        return str(artifact_path)
    except OSError:
        return None


def _fallback_markdown_for_processed_block_rejection(*, payload: Any, processed_chunk: str, rejection_kind: str) -> str:
    if rejection_kind in {"empty", "empty_processed_block"}:
        return str(getattr(payload, "target_text", "") or "").strip()
    return processed_chunk


def _has_intact_controlled_fallback_substrate(
    *,
    payload: Any,
    fallback_markdown: str,
    build_processed_paragraph_registry_entries_fn: Any,
) -> bool:
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    if getattr(payload, "job_kind", None) != "llm":
        return False
    if not isinstance(paragraph_ids, list) or not paragraph_ids:
        return False
    if not str(getattr(payload, "target_text", "") or "").strip():
        return False
    if not str(getattr(payload, "target_text_with_markers", "") or "").strip():
        return False
    if not fallback_markdown.strip():
        return False
    try:
        build_processed_paragraph_registry_entries_fn(
            block_index=0,
            paragraph_ids=paragraph_ids,
            processed_chunk=fallback_markdown,
        )
    except Exception:
        return False
    return True


def classify_processed_block_failure_decision(
    *,
    rejection_kind: str,
    payload: Any,
    processed_chunk: str,
    build_processed_paragraph_registry_entries_fn: Any,
) -> dict[str, str]:
    policy = CONTROLLED_BLOCK_FAILURE_POLICY.get(rejection_kind, {"decision": "fail"})
    decision = str(policy.get("decision") or "fail")
    fallback_kind = str(policy.get("fallback_kind") or rejection_kind)
    if decision != "fallback_continue":
        return {"decision": decision, "fallback_kind": fallback_kind}
    fallback_markdown = _fallback_markdown_for_processed_block_rejection(
        payload=payload,
        processed_chunk=processed_chunk,
        rejection_kind=fallback_kind,
    )
    if not _has_intact_controlled_fallback_substrate(
        payload=payload,
        fallback_markdown=fallback_markdown,
        build_processed_paragraph_registry_entries_fn=build_processed_paragraph_registry_entries_fn,
    ):
        return {"decision": "fail", "fallback_kind": fallback_kind}
    return {
        "decision": "fallback_continue",
        "fallback_kind": fallback_kind,
        "fallback_markdown": fallback_markdown,
    }


def _resolve_segment_status_payload(*, initialization: Any, index: int, status: str) -> tuple[dict[str, str], dict[str, float], str, str]:
    segment_ids_by_job = tuple(getattr(initialization, "segment_ids_by_job", ()) or ())
    segment_titles_by_id = dict(getattr(initialization, "segment_titles_by_id", {}) or {})
    segment_job_totals = dict(getattr(initialization, "segment_job_totals", {}) or {})
    if not segment_ids_by_job:
        return {}, {}, "", ""

    active_segment_index = max(0, min(index - 1, len(segment_ids_by_job) - 1))
    active_segment_id = segment_ids_by_job[active_segment_index]
    if active_segment_id is None:
        return {}, {}, "", ""

    active_segment_title = str(segment_titles_by_id.get(active_segment_id, active_segment_id) or active_segment_id)
    completed_jobs_by_segment: dict[str, int] = {}
    for segment_index in range(max(0, min(index, len(segment_ids_by_job)))):
        segment_id = segment_ids_by_job[segment_index]
        if segment_id is None:
            continue
        completed_jobs_by_segment[segment_id] = completed_jobs_by_segment.get(segment_id, 0) + 1

    status_by_id: dict[str, str] = {}
    progress_by_id: dict[str, float] = {}
    for segment_id, total_jobs in segment_job_totals.items():
        completed_jobs = completed_jobs_by_segment.get(segment_id, 0)
        if segment_id == active_segment_id:
            status_by_id[segment_id] = status
        elif completed_jobs >= total_jobs > 0:
            status_by_id[segment_id] = "completed"
        elif completed_jobs > 0:
            status_by_id[segment_id] = "processing"
        else:
            status_by_id[segment_id] = "pending"
        progress_by_id[segment_id] = 0.0 if total_jobs <= 0 else min(completed_jobs / total_jobs, 1.0)
    return status_by_id, progress_by_id, str(active_segment_id), active_segment_title


def _is_toc_dominant_payload(*, payload: Any) -> bool:
    return bool(getattr(payload, "toc_dominant", False))


def _should_route_toc_through_llm(*, context: Any, payload: Any) -> bool:
    return context.processing_operation == "translate" and _is_toc_dominant_payload(payload=payload)


def _resolve_block_prompt_variant(*, context: Any, payload: Any) -> str:
    if _should_route_toc_through_llm(context=context, payload=payload):
        return "toc_translate"
    return "default"


def _build_prompt_source_text(*, context: Any) -> str:
    parts: list[str] = []
    translation_domain_instructions = str(getattr(context, "translation_domain_instructions", "") or "").strip()
    if translation_domain_instructions:
        parts.append(translation_domain_instructions)
    if getattr(context, "processing_operation", "") == "translate":
        document_context_prompt = str(
            getattr(context, "document_context_prompt", "")
            or getattr(context, "app_config", {}).get("document_context_prompt", "")
            or ""
        ).strip()
        if document_context_prompt:
            parts.append(document_context_prompt)
    return "\n\n".join(parts)


def _build_block_segment_focus_prompt(*, context: Any, initialization: Any, index: int) -> str:
    if getattr(context, "processing_operation", "") != "translate":
        return ""

    segment_ids_by_job = tuple(getattr(initialization, "segment_ids_by_job", ()) or ())
    if not segment_ids_by_job or index <= 0:
        return ""

    active_segment_index = min(index - 1, len(segment_ids_by_job) - 1)
    active_segment_id = segment_ids_by_job[active_segment_index]
    if active_segment_id is None:
        return ""

    ordered_segments = [
        segment
        for segment in list(getattr(context, "document_segments", ()) or ())
        if str(getattr(segment, "segment_id", "") or "").strip()
    ]
    if not ordered_segments:
        return ""

    ordered_segment_ids = [str(getattr(segment, "segment_id", "") or "").strip() for segment in ordered_segments]
    try:
        segment_position = ordered_segment_ids.index(str(active_segment_id))
    except ValueError:
        return ""

    active_segment = ordered_segments[segment_position]
    segment_titles_by_id = dict(getattr(initialization, "segment_titles_by_id", {}) or {})
    active_title = str(
        getattr(active_segment, "title", "") or segment_titles_by_id.get(str(active_segment_id), active_segment_id)
    ).strip()
    if not active_title:
        return ""

    active_level = max(1, int(getattr(active_segment, "level", 1) or 1))
    active_ordinal = max(1, int(getattr(active_segment, "ordinal", segment_position + 1) or (segment_position + 1)))
    active_role = str(getattr(active_segment, "structural_role", "body_range") or "body_range").strip() or "body_range"

    lines = [f"- Текущий сегмент: #{active_ordinal} | L{active_level} | {active_role} | {active_title}"]

    if segment_position > 0:
        previous_title = str(getattr(ordered_segments[segment_position - 1], "title", "") or "").strip()
        if previous_title:
            lines.append(f"- Предыдущий сегмент: {previous_title}")
    if segment_position + 1 < len(ordered_segments):
        next_title = str(getattr(ordered_segments[segment_position + 1], "title", "") or "").strip()
        if next_title:
            lines.append(f"- Следующий сегмент: {next_title}")

    return "ТЕКУЩИЙ БЛОК ДОКУМЕНТА:\n" + "\n".join(lines)


def _resolve_job_segment_id(*, initialization: Any, index: int) -> str | None:
    segment_ids_by_job = tuple(getattr(initialization, "segment_ids_by_job", ()) or ())
    if not segment_ids_by_job or index <= 0 or index > len(segment_ids_by_job):
        return None
    segment_id = segment_ids_by_job[index - 1]
    return str(segment_id).strip() if isinstance(segment_id, str) and str(segment_id).strip() else None


def _mark_segment_progress_after_completed_block(*, state: Any, initialization: Any, index: int, processed_chunk: str) -> None:
    segment_id = _resolve_job_segment_id(initialization=initialization, index=index)
    if not segment_id:
        return

    state.segment_outputs.setdefault(segment_id, []).append(str(processed_chunk or ""))

    segment_ids_by_job = tuple(getattr(initialization, "segment_ids_by_job", ()) or ())
    next_segment_id = None
    if index < len(segment_ids_by_job):
        raw_next_segment_id = segment_ids_by_job[index]
        if isinstance(raw_next_segment_id, str) and str(raw_next_segment_id).strip():
            next_segment_id = str(raw_next_segment_id).strip()
    if next_segment_id != segment_id:
        state.completed_segment_ids.add(segment_id)


def _build_previous_completed_segment_summary_prompt(*, context: Any, state: Any, initialization: Any, index: int) -> str:
    if getattr(context, "processing_operation", "") != "translate":
        return ""

    current_segment_id = _resolve_job_segment_id(initialization=initialization, index=index)
    if not current_segment_id:
        return ""

    ordered_segments = [
        segment
        for segment in list(getattr(context, "document_segments", ()) or ())
        if str(getattr(segment, "segment_id", "") or "").strip()
    ]
    if not ordered_segments:
        return ""

    ordered_segment_ids = [str(getattr(segment, "segment_id", "") or "").strip() for segment in ordered_segments]
    try:
        current_segment_position = ordered_segment_ids.index(current_segment_id)
    except ValueError:
        return ""

    previous_completed_segment = None
    for previous_position in range(current_segment_position - 1, -1, -1):
        candidate_segment = ordered_segments[previous_position]
        candidate_segment_id = str(getattr(candidate_segment, "segment_id", "") or "").strip()
        if not candidate_segment_id:
            continue
        if candidate_segment_id not in set(getattr(state, "completed_segment_ids", set()) or set()):
            continue
        candidate_outputs = list(getattr(state, "segment_outputs", {}).get(candidate_segment_id, []) or [])
        if not candidate_outputs:
            continue
        previous_completed_segment = (candidate_segment, candidate_outputs)
        break

    if previous_completed_segment is None:
        return ""

    segment, outputs = previous_completed_segment
    segment_title = str(getattr(segment, "title", "") or "").strip() or str(getattr(segment, "segment_id", "") or "").strip()
    summary_text = " ".join(part.strip() for part in outputs if str(part or "").strip())
    summary_text = " ".join(summary_text.split())
    if not summary_text:
        return ""
    summary_excerpt = summary_text[:280].rstrip()
    if len(summary_text) > 280:
        summary_excerpt += "..."
    return (
        "СВОДКА ПРЕДЫДУЩЕГО ЗАВЕРШЁННОГО СЕГМЕНТА:\n"
        f"- Сегмент: {segment_title}\n"
        f"- Краткое содержание текущего перевода: {summary_excerpt}"
    )


def _combine_system_prompt_with_block_focus(*, system_prompt: str, block_focus_prompt: str) -> str:
    base_prompt = str(system_prompt or "").strip()
    focus_prompt = str(block_focus_prompt or "").strip()
    if not focus_prompt:
        return base_prompt
    if not base_prompt:
        return focus_prompt
    return f"{base_prompt}\n\n{focus_prompt}"


def _get_cached_system_prompt(*, context: Any, dependencies: Any, state: Any, resolve_system_prompt_fn: Any, prompt_variant: str) -> str:
    prompt_source_text = _build_prompt_source_text(context=context)
    if prompt_variant == "toc_translate":
        if state.toc_system_prompt is None:
            state.toc_system_prompt = resolve_system_prompt_fn(
                dependencies.load_system_prompt,
                operation=context.processing_operation,
                source_language=context.source_language,
                target_language=context.target_language,
                editorial_intensity=str(context.app_config.get("editorial_intensity_default", "literary")),
                prompt_variant="toc_translate",
                translation_domain=context.translation_domain,
                source_text=prompt_source_text,
            )
        return state.toc_system_prompt

    if state.system_prompt is None:
        state.system_prompt = resolve_system_prompt_fn(
            dependencies.load_system_prompt,
            operation=context.processing_operation,
            source_language=context.source_language,
            target_language=context.target_language,
            editorial_intensity=str(context.app_config.get("editorial_intensity_default", "literary")),
            translation_domain=context.translation_domain,
            source_text=prompt_source_text,
        )
    return state.system_prompt


def _build_toc_retry_system_prompt(*, system_prompt: str, source_language: str, target_language: str) -> str:
    return (
        f"{system_prompt}\n\n"
        "TOC retry hardening.\n"
        f"Translate each input paragraph from {source_language} to {target_language} as a table-of-contents entry, not as prose.\n"
        "Keep one output paragraph for each input paragraph.\n"
        "Preserve ordering, numbering, Roman numerals, and page-reference-like suffixes.\n"
        "Do not leave the TOC header or substantive entries unchanged unless they are proper names or acronyms."
    )


def _generate_block_chunk(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    marker_mode_enabled: bool,
    system_prompt: str,
) -> str:
    client = initialization.text_client or initialization.client
    model_id = context.model_id or initialization.text_model_id or context.model
    block_system_prompt = _combine_system_prompt_with_block_focus(
        system_prompt=system_prompt,
        block_focus_prompt="\n\n".join(
            part
            for part in (
                _build_block_segment_focus_prompt(
                    context=context,
                    initialization=initialization,
                    index=index,
                ),
                _build_previous_completed_segment_summary_prompt(
                    context=context,
                    state=state,
                    initialization=initialization,
                    index=index,
                ),
            )
            if part
        ),
    )
    return dependencies.generate_markdown_block(
        client=client,
        model=model_id,
        system_prompt=block_system_prompt,
        target_text=payload.target_text_with_markers if marker_mode_enabled else payload.target_text,
        context_before=payload.context_before,
        context_after=payload.context_after,
        max_retries=context.max_retries,
        expected_paragraph_ids=payload.paragraph_ids if marker_mode_enabled else None,
        marker_mode=marker_mode_enabled,
    )


def _validate_toc_chunk_with_retries(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    marker_mode_enabled: bool,
    resolve_system_prompt_fn: Any,
) -> str:
    prompt_variant = _resolve_block_prompt_variant(context=context, payload=payload)
    retry_budget = TOC_VALIDATION_RETRY_BUDGET
    rejection_reasons: list[str] = []

    for attempt in range(retry_budget + 1):
        base_prompt = _get_cached_system_prompt(
            context=context,
            dependencies=dependencies,
            state=state,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
            prompt_variant=prompt_variant,
        )
        system_prompt = (
            _build_toc_retry_system_prompt(
                system_prompt=base_prompt,
                source_language=context.source_language,
                target_language=context.target_language,
            )
            if attempt == TOC_RETRY_HARDENING_ATTEMPT
            else base_prompt
        )
        dependencies.log_event(
            logging.INFO,
            "toc_prompt_routing_selected",
            "Для блока выбран TOC-ориентированный prompt path.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            prompt_variant=prompt_variant,
            retry_attempt=attempt,
            toc_paragraph_count=getattr(payload, "toc_paragraph_count", 0),
            paragraph_count=getattr(payload, "paragraph_count", 0),
            structural_roles=list(getattr(payload, "structural_roles", []) or []),
        )
        processed_chunk = _generate_block_chunk(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            marker_mode_enabled=marker_mode_enabled,
            system_prompt=system_prompt,
        )
        validation_result = validate_translated_toc_block(
            source_text=payload.target_text,
            processed_chunk=processed_chunk,
            structural_roles=getattr(payload, "structural_roles", None),
            source_language=context.source_language,
            target_language=context.target_language,
        )
        if validation_result.is_valid:
            return processed_chunk

        dependencies.log_event(
            logging.WARNING,
            "toc_validation_rejected",
            "TOC-блок отклонён deterministic validation и будет перегенерирован или завершится ошибкой.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            prompt_variant=prompt_variant,
            retry_attempt=attempt,
            rejection_reason=validation_result.reason,
            toc_paragraph_count=getattr(payload, "toc_paragraph_count", 0),
            paragraph_count=getattr(payload, "paragraph_count", 0),
            structural_roles=list(getattr(payload, "structural_roles", []) or []),
            input_preview=payload.target_text[:300],
            output_preview=processed_chunk[:300],
        )
        rejection_reasons.append(str(validation_result.reason or "unknown"))
        if attempt >= retry_budget:
            raise RuntimeError(
                "toc_language_validation_failed:"
                f"{validation_result.reason};attempt={attempt};history={'|'.join(rejection_reasons)}"
            )
        prompt_variant = "toc_translate"

    raise RuntimeError("toc_language_validation_failed:retry_budget_exhausted;attempt=2;history=retry_budget_exhausted")


def build_processed_paragraph_registry_entries(
    *,
    block_index: int,
    paragraph_ids: list[str] | tuple[str, ...],
    processed_chunk: str,
) -> list[dict[str, object]]:
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


def emit_block_started(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    initialization: Any,
    index: int,
    payload: Any,
) -> None:
    segment_status_by_id, segment_progress_by_id, active_segment_id, active_segment_title = _resolve_segment_status_payload(
        initialization=initialization,
        index=index,
        status="processing",
    )
    emitters.emit_status(
        context.runtime,
        stage="Подготовка блока",
        detail=(
            f"Готовлю блок {index} из {initialization.job_count} к отправке в модель."
            if payload.job_kind == "llm"
            else f"Готовлю passthrough-блок {index} из {initialization.job_count} без вызова модели."
        ),
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        segment_status_by_id=segment_status_by_id,
        segment_progress_by_id=segment_progress_by_id,
        active_segment_id=active_segment_id,
        active_segment_title=active_segment_title,
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
        model_selector=context.model_selector or context.model,
        canonical_model_selector=context.canonical_model_selector or context.model,
        model_provider=context.model_provider,
        model_id=context.model_id or context.model,
        job_kind=payload.job_kind,
    )


def execute_processing_block(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    is_marker_mode_enabled_fn: Any,
    resolve_system_prompt_fn: Any,
) -> tuple[str, bool]:
    if payload.job_kind == "passthrough" and not _should_route_toc_through_llm(context=context, payload=payload):
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
        emitters.emit_activity(context.runtime, f"Блок {index} пропущен через passthrough без вызова модели.")
        context.on_progress(preview_title="Текущий Markdown")
        return payload.target_text, False

    marker_mode_enabled = is_marker_mode_enabled_fn(context, payload)
    emitters.emit_status(
        context.runtime,
        stage="Ожидание ответа модели",
        detail=f"Блок {index} отправлен в модель. Приложение работает, ожидаю ответ.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        progress=(index - 1) / initialization.job_count,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, f"Блок {index} отправлен в модель.")
    context.on_progress(preview_title="Текущий Markdown")
    if _should_route_toc_through_llm(context=context, payload=payload):
        processed_chunk = _validate_toc_chunk_with_retries(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            marker_mode_enabled=marker_mode_enabled,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
        )
    else:
        system_prompt = _get_cached_system_prompt(
            context=context,
            dependencies=dependencies,
            state=state,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
            prompt_variant="default",
        )
        processed_chunk = _generate_block_chunk(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            marker_mode_enabled=marker_mode_enabled,
            system_prompt=system_prompt,
        )
    return processed_chunk, marker_mode_enabled


def append_marker_registry_entries(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    build_processed_paragraph_registry_entries_fn: Any,
) -> None:
    paragraph_ids = payload.paragraph_ids or []
    state.generated_paragraph_registry.extend(
        build_processed_paragraph_registry_entries_fn(
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


def append_controlled_fallback_registry_entries(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    rejection_kind: str,
    append_marker_registry_entries_fn: Any,
) -> None:
    if payload.job_kind != "llm" or not payload.paragraph_ids:
        return

    before_count = len(state.generated_paragraph_registry)
    append_marker_registry_entries_fn(
        context=context,
        dependencies=dependencies,
        state=state,
        initialization=initialization,
        index=index,
        payload=payload,
        processed_chunk=processed_chunk,
    )
    for entry in state.generated_paragraph_registry[before_count:]:
        entry["controlled_fallback"] = True
        entry["controlled_fallback_kind"] = rejection_kind


def emit_block_completed(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    current_markdown_fn: Any,
) -> None:
    _mark_segment_progress_after_completed_block(
        state=state,
        initialization=initialization,
        index=index,
        processed_chunk=processed_chunk,
    )
    segment_status_by_id, segment_progress_by_id, active_segment_id, active_segment_title = _resolve_segment_status_payload(
        initialization=initialization,
        index=index,
        status="completed",
    )
    emitters.emit_state(
        context.runtime,
        processed_block_markdowns=state.processed_chunks.copy(),
        latest_markdown=current_markdown_fn(state.processed_chunks),
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
    persist_terminal_job_result(
        context=context,
        dependencies=dependencies,
        index=index,
        status="completed",
    )
    emitters.emit_status(
        context.runtime,
        stage="Блок обработан",
        detail=f"Получен ответ для блока {index}. Обновляю промежуточный Markdown.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        segment_status_by_id=segment_status_by_id,
        segment_progress_by_id=segment_progress_by_id,
        active_segment_id=active_segment_id,
        active_segment_title=active_segment_title,
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


def continue_controlled_processed_block_rejection(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    rejection_kind: str,
    append_marker_registry_entries_fn: Any,
) -> None:
    artifact_path = _write_controlled_block_fallback_artifact(
        context=context,
        initialization=initialization,
        index=index,
        rejection_kind=rejection_kind,
        target_text=payload.target_text,
        processed_chunk=processed_chunk,
    )
    state.processed_chunks.append(processed_chunk)
    if payload.narration_include:
        state.narration_chunks.append(processed_chunk)
    else:
        state.excluded_narration_block_count += 1
    try:
        append_controlled_fallback_registry_entries(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            processed_chunk=processed_chunk,
            rejection_kind=rejection_kind,
            append_marker_registry_entries_fn=append_marker_registry_entries_fn,
        )
    except Exception as exc:
        dependencies.log_event(
            logging.WARNING,
            "controlled_fallback_registry_build_failed",
            "Не удалось собрать marker registry для controlled fallback блока.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            rejection_kind=rejection_kind,
            error_message=str(exc),
        )
    persist_terminal_job_result(
        context=context,
        dependencies=dependencies,
        index=index,
        status="controlled_fallback",
        error_code=rejection_kind,
        error_message="Controlled fallback retained rejected block output for full-document assembly.",
    )
    segment_status_by_id, segment_progress_by_id, active_segment_id, active_segment_title = _resolve_segment_status_payload(
        initialization=initialization,
        index=index,
        status="completed_with_fallback",
    )
    latest_markdown = "\n\n".join(state.processed_chunks).strip()
    emitters.emit_state(
        context.runtime,
        processed_block_markdowns=state.processed_chunks.copy(),
        latest_markdown=latest_markdown,
        processed_paragraph_registry=state.generated_paragraph_registry.copy(),
        latest_controlled_block_fallback_artifact=artifact_path,
    )
    emitters.emit_status(
        context.runtime,
        stage="Блок сохранён с предупреждением",
        detail=f"Блок {index} сохранён как controlled fallback: {rejection_kind}.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        segment_status_by_id=segment_status_by_id,
        segment_progress_by_id=segment_progress_by_id,
        active_segment_id=active_segment_id,
        active_segment_title=active_segment_title,
        progress=index / initialization.job_count,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, f"Блок {index}: сохранён с controlled fallback ({rejection_kind}).")
    emitters.emit_log(
        context.runtime,
        status="WARN",
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        details=f"controlled_fallback:{rejection_kind}",
    )
    dependencies.log_event(
        logging.WARNING,
        "block_controlled_fallback",
        "Блок сохранён с controlled fallback после quality rejection.",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        output_classification=rejection_kind,
        artifact_path=artifact_path,
        input_preview=payload.target_text[:300],
        output_preview=processed_chunk[:300],
    )
    context.on_progress(preview_title="Текущий Markdown")


def process_single_block(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    job: Any,
    parse_processing_job_fn: Any,
    handle_invalid_processing_job_fn: Any,
    emit_block_started_fn: Any,
    is_marker_mode_enabled_fn: Any,
    execute_processing_block_fn: Any,
    handle_block_generation_failure_fn: Any,
    classify_processed_block_fn: Any,
    handle_processed_block_rejection_fn: Any,
    append_marker_registry_entries_fn: Any,
    handle_marker_registry_failure_fn: Any,
    emit_block_completed_fn: Any,
) -> PipelineResult | None:
    try:
        payload = parse_processing_job_fn(job=job)
    except (KeyError, TypeError, ValueError) as exc:
        return handle_invalid_processing_job_fn(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            exc=exc,
        )

    emit_block_started_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        initialization=initialization,
        index=index,
        payload=payload,
    )
    marker_mode_enabled = is_marker_mode_enabled_fn(context, payload)
    try:
        processed_chunk, marker_mode_enabled = execute_processing_block_fn(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
        )
    except Exception as exc:
        return handle_block_generation_failure_fn(
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

    # A genuine passthrough block is emitted as the VERBATIM source markdown (no LLM call), so
    # the LLM-output-quality classifier (heading_only_output / untranslated / ...) must not gate
    # it — doing so produced hard failures and EMPTY DOCX for passthrough-heavy real documents
    # (round-5 finding 1). TOC blocks routed through the LLM are genuinely processed and stay
    # classified as before.
    is_genuine_passthrough = payload.job_kind == "passthrough" and not _should_route_toc_through_llm(
        context=context, payload=payload
    )
    if is_genuine_passthrough:
        processed_block_status = "valid"
    else:
        processed_block_status = classify_processed_block_fn(payload.target_text, processed_chunk)
    if processed_block_status != "valid":
        rejection_decision = classify_processed_block_failure_decision(
            rejection_kind=processed_block_status,
            payload=payload,
            processed_chunk=processed_chunk,
            build_processed_paragraph_registry_entries_fn=build_processed_paragraph_registry_entries,
        )
        if rejection_decision["decision"] == "fallback_continue":
            continue_controlled_processed_block_rejection(
                context=context,
                dependencies=dependencies,
                emitters=emitters,
                state=state,
                initialization=initialization,
                index=index,
                payload=payload,
                processed_chunk=rejection_decision["fallback_markdown"],
                rejection_kind=rejection_decision["fallback_kind"],
                append_marker_registry_entries_fn=append_marker_registry_entries_fn,
            )
            return None
        return handle_processed_block_rejection_fn(
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
    if payload.narration_include:
        state.narration_chunks.append(processed_chunk)
    else:
        state.excluded_narration_block_count += 1
    if payload.job_kind == "llm" and marker_mode_enabled and payload.paragraph_ids:
        try:
            append_marker_registry_entries_fn(
                context=context,
                dependencies=dependencies,
                state=state,
                initialization=initialization,
                index=index,
                payload=payload,
                processed_chunk=processed_chunk,
            )
        except Exception as exc:
            return handle_marker_registry_failure_fn(
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
    emit_block_completed_fn(
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


def run_block_processing_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    emit_stopped_result_fn: Any,
    process_single_block_fn: Any,
    current_markdown_fn: Any,
    emit_failed_result_fn: Any,
) -> PipelineResult | None:
    for index, job in enumerate(context.jobs, start=1):
        if dependencies.should_stop_processing(context.runtime):
            stop_message = "Обработка остановлена пользователем."
            return emit_stopped_result_fn(
                emitters=emitters,
                runtime=context.runtime,
                detail=stop_message,
                progress=(index - 1) / initialization.job_count,
                block_index=max(0, index - 1),
                block_count=initialization.job_count,
            )

        block_outcome = process_single_block_fn(
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
        emitters.emit_state(
            context.runtime,
            last_error=critical_message,
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        return emit_failed_result_fn(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Критическая ошибка",
            detail=critical_message,
            progress=len(state.processed_chunks) / max(initialization.job_count, 1),
            activity_message="Обнаружено несоответствие количества обработанных блоков.",
            block_index=len(state.processed_chunks),
            block_count=initialization.job_count,
            target_chars=len(current_markdown_fn(state.processed_chunks)),
            context_chars=0,
            log_details=critical_message,
        )

    return None
