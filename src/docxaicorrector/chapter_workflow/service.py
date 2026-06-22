from __future__ import annotations

import re
from hashlib import sha256
from collections.abc import Sequence
from typing import Any, Mapping, Protocol, TypedDict, cast

from docxaicorrector.document.segments import (
    CHAPTER_SEGMENTS_DETECTOR_VERSION,
    SegmentDetectionReport,
    humanize_segment_warnings,
)
from docxaicorrector.pipeline.contracts import SegmentSelection
from docxaicorrector.runtime.artifacts import load_job_result_registry, write_structure_manifest_artifact


class SegmentLike(Protocol):
    segment_id: str
    parent_segment_id: str | None
    title: str
    word_count: int
    paragraph_ids: tuple[str, ...]


class SelectedProcessingPayload(TypedDict):
    selected_segment_ids: list[str]
    jobs: list[dict[str, object]]
    source_paragraphs: list[object]
    image_assets: list[object]
    include_front_matter: bool
    include_toc: bool


class EffectiveSelectedProcessingState(TypedDict):
    payload: SelectedProcessingPayload
    effective_selected_segment_ids: list[str]
    effective_selected_segments: list[SegmentLike]
    selected_word_count: int
    selected_job_count: int
    excluded_locked_segment_ids: list[str]
    uses_job_index_filter: bool
    retry_job_source: str
    selection_blocked_reason: str


def _get_prepared_segments(prepared_run_context: object) -> list[SegmentLike]:
    return cast(list[SegmentLike], list(getattr(prepared_run_context, "segments", None) or []))


def _normalize_selected_segment_ids(selected_segment_ids: Sequence[object] | None = None) -> list[str]:
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for raw_segment_id in list(selected_segment_ids or []):
        segment_id = str(raw_segment_id or "").strip()
        if not segment_id or segment_id in seen:
            continue
        seen.add(segment_id)
        normalized_ids.append(segment_id)
    return normalized_ids


def _resolve_segment_selection(
    *,
    selected_segment_ids: Sequence[object] | None = None,
    segment_selection: SegmentSelection | None = None,
) -> SegmentSelection | None:
    if segment_selection is not None:
        normalized_ids = _normalize_selected_segment_ids(segment_selection.selected_segment_ids)
        if normalized_ids:
            return SegmentSelection(
                selected_segment_ids=tuple(normalized_ids),
                include_descendants=bool(segment_selection.include_descendants),
            )

    normalized_ids = _normalize_selected_segment_ids(selected_segment_ids)
    if not normalized_ids:
        return None
    return SegmentSelection(selected_segment_ids=tuple(normalized_ids))


def _build_selected_segment_scope_prompt(
    *,
    prepared_run_context: object,
    selected_segment_ids: Sequence[object] | None = None,
    segment_selection: SegmentSelection | None = None,
    max_selected_segments: int = 5,
) -> str:
    resolved_selection = _resolve_segment_selection(
        selected_segment_ids=selected_segment_ids,
        segment_selection=segment_selection,
    )
    if resolved_selection is None:
        return ""
    normalized_selected_segment_ids = list(resolved_selection.selected_segment_ids)

    segments = _get_prepared_segments(prepared_run_context)
    if not segments:
        return ""

    selected_segment_id_set = set(normalized_selected_segment_ids)
    ordered_selected_segments = [
        segment
        for segment in segments
        if str(getattr(segment, "segment_id", "") or "").strip() in selected_segment_id_set
    ]
    if not ordered_selected_segments:
        return ""

    ordered_selected_id_set = {
        str(getattr(segment, "segment_id", "") or "").strip()
        for segment in ordered_selected_segments
        if str(getattr(segment, "segment_id", "") or "").strip()
    }
    first_selected_index = next(
        (index for index, segment in enumerate(segments) if str(getattr(segment, "segment_id", "") or "").strip() in ordered_selected_id_set),
        0,
    )
    last_selected_index = max(
        index
        for index, segment in enumerate(segments)
        if str(getattr(segment, "segment_id", "") or "").strip() in ordered_selected_id_set
    )
    previous_segment = segments[first_selected_index - 1] if first_selected_index > 0 else None
    next_segment = segments[last_selected_index + 1] if last_selected_index + 1 < len(segments) else None

    scope_lines = [f"- Сегментов в текущем запуске: {len(ordered_selected_segments)}"]
    for segment in ordered_selected_segments[:max_selected_segments]:
        title = str(getattr(segment, "title", "") or "").strip()
        if not title:
            continue
        level = max(1, int(getattr(segment, "level", 1) or 1))
        ordinal = max(1, int(getattr(segment, "ordinal", 1) or 1))
        structural_role = str(getattr(segment, "structural_role", "body_range") or "body_range").strip() or "body_range"
        scope_lines.append(f"- L{level} | {structural_role} | #{ordinal} | {title}")
    if len(ordered_selected_segments) > max_selected_segments:
        scope_lines.append("- ...")
    if previous_segment is not None:
        previous_title = str(getattr(previous_segment, "title", "") or "").strip()
        if previous_title:
            scope_lines.append(f"- Предыдущий сегмент: {previous_title}")
    if next_segment is not None:
        next_title = str(getattr(next_segment, "title", "") or "").strip()
        if next_title:
            scope_lines.append(f"- Следующий сегмент: {next_title}")
    return "ФОКУС ТЕКУЩЕГО ЗАПУСКА:\n" + "\n".join(scope_lines)


def build_document_context_prompt(
    *,
    prepared_run_context: object,
    selected_segment_ids: Sequence[object] | None = None,
    segment_selection: SegmentSelection | None = None,
) -> str:
    document_context_profile = getattr(prepared_run_context, "document_context_profile", None)
    prompt_builder = getattr(document_context_profile, "to_prompt_text", None)
    base_prompt = ""
    if callable(prompt_builder):
        base_prompt = str(prompt_builder() or "").strip()
    selected_segment_scope_prompt = _build_selected_segment_scope_prompt(
        prepared_run_context=prepared_run_context,
        selected_segment_ids=selected_segment_ids,
        segment_selection=segment_selection,
    )
    prompt_parts = [part for part in (base_prompt, selected_segment_scope_prompt) if part]
    return "\n\n".join(prompt_parts)


def _normalize_segment_status(value: object) -> str:
    return str(value or "pending").strip().lower() or "pending"


def _is_segment_selection_locked(segment_status: str) -> bool:
    return _normalize_segment_status(segment_status) in {"queued", "processing"}


def _build_segment_parent_to_children_map(segments: list[SegmentLike]) -> dict[str, list[str]]:
    parent_to_children_map: dict[str, list[str]] = {}
    for segment in segments:
        segment_id = str(getattr(segment, "segment_id", "") or "").strip()
        parent_segment_id = str(getattr(segment, "parent_segment_id", "") or "").strip()
        if not segment_id or not parent_segment_id:
            continue
        parent_to_children_map.setdefault(parent_segment_id, []).append(segment_id)
    return parent_to_children_map


def _collect_descendant_segment_ids(*, segment_id: str, parent_to_children_map: dict[str, list[str]]) -> list[str]:
    descendants: list[str] = []
    pending = list(parent_to_children_map.get(segment_id, ()))
    seen: set[str] = set()
    while pending:
        current_segment_id = pending.pop(0)
        if current_segment_id in seen:
            continue
        seen.add(current_segment_id)
        descendants.append(current_segment_id)
        pending.extend(parent_to_children_map.get(current_segment_id, ()))
    return descendants


def _expand_segment_ids_for_selection(
    *,
    segment_ids: list[str],
    parent_to_children_map: dict[str, list[str]],
    segment_status_by_id: dict[str, str],
    include_locked: bool,
) -> list[str]:
    expanded_segment_ids: list[str] = []
    seen: set[str] = set()
    for segment_id in segment_ids:
        descendants = _collect_descendant_segment_ids(
            segment_id=segment_id,
            parent_to_children_map=parent_to_children_map,
        )
        for candidate_segment_id in [segment_id, *descendants]:
            if candidate_segment_id in seen:
                continue
            if not include_locked and _is_segment_selection_locked(segment_status_by_id.get(candidate_segment_id, "pending")):
                continue
            seen.add(candidate_segment_id)
            expanded_segment_ids.append(candidate_segment_id)
    return expanded_segment_ids


def _build_latest_block_status_by_job_index(run_log: Sequence[object] | None = None) -> dict[int, str]:
    latest_status_by_job_index: dict[int, str] = {}
    for entry in list(run_log or []):
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("kind", "") or "").strip().lower() != "block":
            continue
        raw_block_index = entry.get("block_index")
        if isinstance(raw_block_index, bool) or not isinstance(raw_block_index, int) or raw_block_index <= 0:
            continue
        status = str(entry.get("status", "") or "").strip().lower()
        if not status:
            continue
        latest_status_by_job_index[raw_block_index - 1] = status
    return latest_status_by_job_index


def _load_persisted_job_records(*, prepared_run_context: object) -> dict[str, dict[str, object]]:
    prepared_source_key = str(getattr(prepared_run_context, "prepared_source_key", "") or "").strip()
    structure_fingerprint = str(getattr(prepared_run_context, "structure_fingerprint", "") or "").strip()
    if not prepared_source_key or not structure_fingerprint:
        return {}
    return load_job_result_registry(
        prepared_source_key=prepared_source_key,
        structure_fingerprint=structure_fingerprint,
    )


def _resolve_selection_blocked_reason(*, prepared_run_context: object) -> str:
    diagnostics = getattr(prepared_run_context, "segment_diagnostics", None)
    warnings = tuple(getattr(diagnostics, "warnings", ()) or ())
    if "segment_job_mapping_incomplete" in warnings:
        return "segment_job_mapping_incomplete"
    return ""


def _resolve_persisted_failed_job_indexes(*, prepared_run_context: object) -> list[int]:
    persisted_job_records = _load_persisted_job_records(prepared_run_context=prepared_run_context)
    if not persisted_job_records:
        return []

    persisted_failed_job_indexes: list[int] = []
    for job_index, job in enumerate(list(getattr(prepared_run_context, "jobs", []) or [])):
        if not isinstance(job, Mapping):
            continue
        job_id = str(job.get("job_id") or "").strip()
        if not job_id:
            continue
        persisted_record = persisted_job_records.get(job_id, {})
        status = str(persisted_record.get("status") or "").strip().lower()
        if status == "failed":
            persisted_failed_job_indexes.append(job_index)
    return persisted_failed_job_indexes


def _resolve_failed_segment_ids(*, prepared_run_context, segment_status_by_id: dict[str, str] | None = None) -> list[str]:
    segments = _get_prepared_segments(prepared_run_context)
    current_failed_segment_ids = [
        segment.segment_id
        for segment in segments
        if str(getattr(segment, "segment_id", "") or "").strip()
        and _normalize_segment_status(
            (segment_status_by_id or {}).get(str(getattr(segment, "segment_id", "") or ""), "pending")
        )
        == "failed"
    ]
    if current_failed_segment_ids:
        return current_failed_segment_ids

    persisted_failed_job_indexes = set(_resolve_persisted_failed_job_indexes(prepared_run_context=prepared_run_context))
    if not persisted_failed_job_indexes:
        return []

    segment_to_job = dict(getattr(prepared_run_context, "segment_to_job", {}) or {})
    return [
        segment.segment_id
        for segment in segments
        if str(getattr(segment, "segment_id", "") or "").strip()
        and any(job_index in persisted_failed_job_indexes for job_index in (segment_to_job.get(segment.segment_id, ()) or ()))
    ]


def _resolve_retry_failed_job_indexes(
    *,
    prepared_run_context,
    failed_segment_ids: list[str],
    run_log: Sequence[object] | None = None,
) -> tuple[list[int], str]:
    if not failed_segment_ids:
        return [], ""
    segment_to_job = dict(getattr(prepared_run_context, "segment_to_job", {}) or {})
    candidate_job_indexes = {
        int(job_index)
        for segment_id in failed_segment_ids
        for job_index in (segment_to_job.get(segment_id, ()) or ())
        if isinstance(job_index, int) and job_index >= 0
    }
    if not candidate_job_indexes:
        return [], ""
    latest_status_by_job_index = _build_latest_block_status_by_job_index(run_log)
    current_session_job_indexes = sorted(
        job_index
        for job_index in candidate_job_indexes
        if latest_status_by_job_index.get(job_index) in {"error", "failed"}
    )
    if current_session_job_indexes:
        return current_session_job_indexes, "current_session_jobs"

    persisted_failed_job_index_set = set(_resolve_persisted_failed_job_indexes(prepared_run_context=prepared_run_context))
    if not persisted_failed_job_index_set:
        return [], ""
    persisted_job_indexes = [
        job_index
        for job_index in sorted(candidate_job_indexes)
        if job_index in persisted_failed_job_index_set
    ]
    if persisted_job_indexes:
        return persisted_job_indexes, "persisted_jobs"
    return [], ""


def build_selected_processing_payload(
    *,
    prepared_run_context,
    selected_segment_ids: list[str] | None,
    segment_selection: SegmentSelection | None = None,
    selected_job_indexes: list[int] | None = None,
    segment_status_by_id: dict[str, str] | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
) -> SelectedProcessingPayload:
    explicit_selected_job_indexes = list(selected_job_indexes or [])
    resolved_selection = _resolve_segment_selection(
        selected_segment_ids=selected_segment_ids,
        segment_selection=segment_selection,
    )
    segments = _get_prepared_segments(prepared_run_context)
    parent_to_children_map = _build_segment_parent_to_children_map(segments)
    if resolved_selection is None:
        expanded_selected_segment_ids = []
    elif resolved_selection.include_descendants:
        expanded_selected_segment_ids = _expand_segment_ids_for_selection(
            segment_ids=list(resolved_selection.selected_segment_ids),
            parent_to_children_map=parent_to_children_map,
            segment_status_by_id=dict(segment_status_by_id or {}),
            include_locked=False,
        )
    else:
        expanded_selected_segment_ids = [
            segment_id
            for segment_id in resolved_selection.selected_segment_ids
            if not _is_segment_selection_locked((segment_status_by_id or {}).get(segment_id, "pending"))
        ]
    selected_segment_id_set = set(expanded_selected_segment_ids)
    if not selected_segment_id_set:
        return {
            "selected_segment_ids": [],
            "jobs": [],
            "source_paragraphs": [],
            "image_assets": [],
            "include_front_matter": bool(include_front_matter),
            "include_toc": bool(include_toc),
        }
    if _resolve_selection_blocked_reason(prepared_run_context=prepared_run_context) == "segment_job_mapping_incomplete":
        return {
            "selected_segment_ids": [segment_id for segment_id in expanded_selected_segment_ids if segment_id in selected_segment_id_set],
            "jobs": [],
            "source_paragraphs": [],
            "image_assets": [],
            "include_front_matter": bool(include_front_matter),
            "include_toc": bool(include_toc),
        }

    selected_segments = [segment for segment in segments if segment.segment_id in selected_segment_id_set]
    selected_paragraph_ids = {
        str(paragraph_id).strip()
        for segment in selected_segments
        for paragraph_id in getattr(segment, "paragraph_ids", ()) or ()
        if str(paragraph_id).strip()
    }
    segment_to_job = dict(getattr(prepared_run_context, "segment_to_job", {}) or {})
    resolved_job_indexes = sorted(
        {
            int(job_index)
            for segment in selected_segments
            for job_index in (segment_to_job.get(segment.segment_id, ()) or ())
        }
    )
    explicit_selected_job_index_set = {
        int(job_index)
        for job_index in explicit_selected_job_indexes
        if isinstance(job_index, int) and job_index >= 0
    }
    if explicit_selected_job_index_set:
        resolved_job_indexes = [
            job_index for job_index in resolved_job_indexes if job_index in explicit_selected_job_index_set
        ]
    all_jobs = list(getattr(prepared_run_context, "jobs", []) or [])
    filtered_jobs = [all_jobs[job_index] for job_index in resolved_job_indexes if 0 <= job_index < len(all_jobs)]
    job_selected_paragraph_ids = {
        str(paragraph_id).strip()
        for job in filtered_jobs
        if isinstance(job, Mapping)
        for paragraph_id in (job.get("paragraph_ids", ()) or ())
        if str(paragraph_id).strip()
    }
    all_paragraphs = list(getattr(prepared_run_context, "paragraphs", []) or [])
    filtered_paragraphs = [
        paragraph
        for paragraph in all_paragraphs
        if str(getattr(paragraph, "paragraph_id", "") or "").strip() in (job_selected_paragraph_ids or selected_paragraph_ids)
    ]
    # Use the full selected-segment paragraph coverage for image lookup, not just
    # the subset that appears in job paragraph_ids. Image paragraphs may be part of
    # a segment without being explicitly listed in any job's paragraph_ids (e.g.
    # standalone image paragraphs between text blocks). If they are omitted from
    # image_assets, inspect_placeholder_integrity will mark their placeholders as
    # "unexpected" and the DOCX build will fail even though the LLM output correctly
    # retained those placeholders.
    #
    # Additionally, images can be INLINE within body/heading paragraphs. Such paragraphs
    # have role != "image", so asset_id is None. We must also scan paragraph texts for
    # [[DOCX_IMAGE_img_NNN]] placeholders to catch all inline images.
    _inline_image_pattern = re.compile(r"\[\[DOCX_IMAGE_(img_\d+)\]\]")
    selected_asset_ids: set[str] = set()
    for paragraph in all_paragraphs:
        if str(getattr(paragraph, "paragraph_id", "") or "").strip() not in selected_paragraph_ids:
            continue
        # Standalone image paragraph or caption attachment
        for attr in ("asset_id", "attached_to_asset_id"):
            asset_id = getattr(paragraph, attr, None)
            if asset_id:
                selected_asset_ids.add(str(asset_id).strip())
        # Inline images embedded within any paragraph text
        text = str(getattr(paragraph, "text", "") or "")
        for match in _inline_image_pattern.finditer(text):
            selected_asset_ids.add(match.group(1))
    filtered_image_assets = [
        asset
        for asset in list(getattr(prepared_run_context, "image_assets", []) or [])
        if str(getattr(asset, "image_id", "") or "").strip() in selected_asset_ids
    ]
    return {
        "selected_segment_ids": [segment.segment_id for segment in selected_segments],
        "jobs": filtered_jobs,
        "source_paragraphs": filtered_paragraphs,
        "image_assets": filtered_image_assets,
        "include_front_matter": bool(include_front_matter),
        "include_toc": bool(include_toc),
    }


def build_effective_selected_processing_state(
    *,
    prepared_run_context,
    selected_segment_ids: list[str] | None,
    segment_selection: SegmentSelection | None = None,
    selected_job_indexes: list[int] | None = None,
    segment_status_by_id: dict[str, str] | None = None,
    include_front_matter: bool = False,
    include_toc: bool = False,
) -> EffectiveSelectedProcessingState:
    resolved_selection = _resolve_segment_selection(
        selected_segment_ids=selected_segment_ids,
        segment_selection=segment_selection,
    )
    payload = build_selected_processing_payload(
        prepared_run_context=prepared_run_context,
        selected_segment_ids=selected_segment_ids,
        segment_selection=resolved_selection,
        selected_job_indexes=selected_job_indexes,
        segment_status_by_id=segment_status_by_id,
        include_front_matter=include_front_matter,
        include_toc=include_toc,
    )
    segments = _get_prepared_segments(prepared_run_context)
    effective_selected_segment_ids = [
        str(segment_id).strip() for segment_id in payload["selected_segment_ids"] if str(segment_id).strip()
    ]
    effective_selected_segment_id_set = set(effective_selected_segment_ids)
    effective_selected_segments = [
        segment for segment in segments if str(getattr(segment, "segment_id", "") or "") in effective_selected_segment_id_set
    ]
    selected_word_count = sum(int(getattr(segment, "word_count", 0) or 0) for segment in effective_selected_segments)
    selected_job_count = len(payload["jobs"])
    parent_to_children_map = _build_segment_parent_to_children_map(segments)
    if resolved_selection is None:
        expanded_with_locked = []
    elif resolved_selection.include_descendants:
        expanded_with_locked = _expand_segment_ids_for_selection(
            segment_ids=list(resolved_selection.selected_segment_ids),
            parent_to_children_map=parent_to_children_map,
            segment_status_by_id=dict(segment_status_by_id or {}),
            include_locked=True,
        )
    else:
        expanded_with_locked = list(resolved_selection.selected_segment_ids)
    excluded_locked_segment_ids = [
        segment_id for segment_id in expanded_with_locked if segment_id not in effective_selected_segment_id_set
    ]
    selection_blocked_reason = _resolve_selection_blocked_reason(prepared_run_context=prepared_run_context)
    return {
        "payload": payload,
        "effective_selected_segment_ids": effective_selected_segment_ids,
        "effective_selected_segments": effective_selected_segments,
        "selected_word_count": selected_word_count,
        "selected_job_count": selected_job_count,
        "excluded_locked_segment_ids": excluded_locked_segment_ids,
        "uses_job_index_filter": bool(selected_job_indexes),
        "retry_job_source": "",
        "selection_blocked_reason": selection_blocked_reason,
    }


def build_retry_failed_processing_state(
    *,
    prepared_run_context,
    segment_status_by_id: dict[str, str] | None = None,
    run_log: Sequence[object] | None = None,
) -> EffectiveSelectedProcessingState:
    failed_segment_ids = _resolve_failed_segment_ids(
        prepared_run_context=prepared_run_context,
        segment_status_by_id=segment_status_by_id,
    )
    retry_failed_job_indexes, retry_job_source = _resolve_retry_failed_job_indexes(
        prepared_run_context=prepared_run_context,
        failed_segment_ids=failed_segment_ids,
        run_log=run_log,
    )
    retry_state = build_effective_selected_processing_state(
        prepared_run_context=prepared_run_context,
        selected_segment_ids=failed_segment_ids,
        segment_selection=SegmentSelection(selected_segment_ids=tuple(failed_segment_ids)),
        selected_job_indexes=retry_failed_job_indexes or None,
        segment_status_by_id=segment_status_by_id,
    )
    if failed_segment_ids and retry_state["selection_blocked_reason"] == "segment_job_mapping_incomplete":
        retry_state["retry_job_source"] = "blocked_incomplete_mapping"
    else:
        retry_state["retry_job_source"] = retry_job_source or ("segment_fallback" if failed_segment_ids else "")
    return retry_state


def build_structure_manifest_payload(*, prepared_run_context: object, app_config: dict[str, object] | None = None) -> dict[str, Any]:
    config: dict[str, Any] = cast(dict[str, Any], {} if app_config is None else dict(app_config))
    uploaded_bytes = bytes(getattr(prepared_run_context, "uploaded_file_bytes", b"") or b"")
    source_name = str(getattr(prepared_run_context, "uploaded_filename", "document.docx") or "document.docx")
    segments = list(getattr(prepared_run_context, "segments", []) or [])
    diagnostics = getattr(prepared_run_context, "segment_diagnostics", SegmentDetectionReport())
    return {
        "schema_version": 1,
        "source_name": source_name,
        "source_content_hash16": sha256(uploaded_bytes).hexdigest()[:16],
        "prepared_source_key": str(getattr(prepared_run_context, "prepared_source_key", "") or ""),
        "ordered_segment_ids": [segment.segment_id for segment in segments if str(segment.segment_id or "").strip()],
        "warning_messages": list(humanize_segment_warnings(getattr(diagnostics, "warnings", ()) or ())),
        "detector_version": str(
            getattr(prepared_run_context, "detector_version", CHAPTER_SEGMENTS_DETECTOR_VERSION)
            or CHAPTER_SEGMENTS_DETECTOR_VERSION
        ),
        "detector_config": {
            "chunk_size": int(config.get("chunk_size", 0) or 0),
        },
        "structure_fingerprint": str(getattr(prepared_run_context, "structure_fingerprint", "") or ""),
        "summary": {
            "paragraph_count": len(getattr(prepared_run_context, "paragraphs", []) or []),
            "segment_count": int(getattr(diagnostics, "segment_count", len(segments)) or len(segments)),
            "toc_entry_count": int(getattr(diagnostics, "toc_entry_count", 0) or 0),
            "toc_matched_count": int(getattr(diagnostics, "toc_matched_count", 0) or 0),
            "low_confidence_count": int(getattr(diagnostics, "low_confidence_count", 0) or 0),
        },
        "segments": [
            {
                "segment_id": segment.segment_id,
                "parent_segment_id": segment.parent_segment_id,
                "ordinal": segment.ordinal,
                "level": segment.level,
                "title": segment.title,
                "normalized_title": segment.normalized_title,
                "start_paragraph_index": segment.start_paragraph_index,
                "end_paragraph_index": segment.end_paragraph_index,
                "start_paragraph_id": segment.start_paragraph_id,
                "end_paragraph_id": segment.end_paragraph_id,
                "paragraph_count": segment.paragraph_count,
                "word_count": segment.word_count,
                "char_count": segment.char_count,
                "estimated_token_count": segment.estimated_token_count,
                "structural_role": segment.structural_role,
                "confidence": segment.confidence,
                "boundary_fingerprint": segment.boundary_fingerprint,
                "warnings": list(segment.warnings),
                "warning_messages": list(humanize_segment_warnings(segment.warnings)),
                "evidence": [
                    {
                        "source": evidence.source,
                        "confidence": evidence.confidence,
                        "details": dict(evidence.details),
                    }
                    for evidence in segment.boundary_evidence
                ],
            }
            for segment in segments
        ],
    }


def export_structure_manifest(*, prepared_run_context: object, app_config: dict[str, object] | None = None) -> str:
    manifest_payload = build_structure_manifest_payload(
        prepared_run_context=prepared_run_context,
        app_config=app_config,
    )
    manifest_path = write_structure_manifest_artifact(
        source_name=str(getattr(prepared_run_context, "uploaded_filename", "document.docx") or "document.docx"),
        manifest_payload=manifest_payload,
    )
    cast(Any, prepared_run_context).exported_structure_manifest_path = manifest_path
    return manifest_path