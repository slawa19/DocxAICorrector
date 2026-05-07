from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias, TypeVar, cast

from docxaicorrector.core.constants import SEGMENT_RESULT_REGISTRY_DIR


AssemblyMode: TypeAlias = Literal["selected_chapters", "full_document"]
OutputMode: TypeAlias = Literal["selected_only", "selected_with_context", "legacy_full_document", "hybrid_document", "final_translated_book"]


@dataclass(frozen=True)
class ReassemblyPlan:
    assembly_mode: AssemblyMode
    output_mode: OutputMode
    selected_segment_ids: tuple[str, ...]
    included_segment_ids: tuple[str, ...]
    selected_segment_count: int | None


@dataclass(frozen=True)
class HybridAssemblyResult:
    final_markdown: str
    generated_paragraph_registry: list[dict[str, object]]
    segment_provenance_by_id: dict[str, str]


T = TypeVar("T")


def build_reassembly_plan(
    *,
    selected_segment_ids: Sequence[object] | None,
    output_mode: str | None,
    include_front_matter: bool = False,
    include_toc: bool = False,
    jobs: Sequence[object],
    source_paragraphs: Sequence[object] | None = None,
) -> ReassemblyPlan:
    normalized_selected_ids = _normalize_segment_ids(selected_segment_ids)
    if normalized_selected_ids:
        effective_output_mode = _coerce_selected_output_mode(output_mode)
        if effective_output_mode == "selected_with_context":
            included_segment_ids = _resolve_selected_with_context_included_segment_ids(
                selected_segment_ids=normalized_selected_ids,
                include_front_matter=include_front_matter,
                include_toc=include_toc,
                source_paragraphs=source_paragraphs,
            )
        else:
            included_segment_ids = normalized_selected_ids
        return ReassemblyPlan(
            assembly_mode="selected_chapters",
            output_mode=effective_output_mode,
            selected_segment_ids=normalized_selected_ids,
            included_segment_ids=included_segment_ids,
            selected_segment_count=len(normalized_selected_ids),
        )
    effective_output_mode = _coerce_full_document_output_mode(output_mode)
    included_segment_ids = _resolve_included_segment_ids(
        jobs=jobs,
        source_paragraphs=source_paragraphs,
        output_mode=effective_output_mode,
    )
    return ReassemblyPlan(
        assembly_mode="full_document",
        output_mode=effective_output_mode,
        selected_segment_ids=(),
        included_segment_ids=included_segment_ids,
        selected_segment_count=None,
    )


def build_reassembly_result_manifest(
    *,
    source_name: str,
    source_token: str = "",
    run_id: str = "",
    plan: ReassemblyPlan,
    jobs: Sequence[object],
    source_paragraphs: Sequence[object] | None,
    segment_provenance_by_id: Mapping[str, str] | None = None,
) -> dict[str, object]:
    segment_job_totals = _build_segment_job_totals(jobs)
    selected_segment_id_set = set(plan.selected_segment_ids)
    segments: list[dict[str, object]] = []

    for segment_id in plan.included_segment_ids:
        segment_payload: dict[str, object] = {
            "segment_id": segment_id,
            "job_count": segment_job_totals.get(segment_id, 0),
            "selected": segment_id in selected_segment_id_set,
        }
        if segment_provenance_by_id and segment_id in segment_provenance_by_id:
            segment_payload["provenance"] = str(segment_provenance_by_id[segment_id])
        segments.append(segment_payload)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "source_name": source_name,
        "assembly_mode": plan.assembly_mode,
        "output_mode": plan.output_mode,
        "selected_segment_count": len(plan.selected_segment_ids),
        "included_segment_count": len(plan.included_segment_ids),
        "included_segment_ids": list(plan.included_segment_ids),
        "coverage": _build_reassembly_coverage(plan=plan, source_paragraphs=source_paragraphs),
        "segments": segments,
    }
    if str(source_token or "").strip():
        manifest["source_token"] = str(source_token).strip()
    if str(run_id or "").strip():
        manifest["run_id"] = str(run_id).strip()
    if plan.selected_segment_ids:
        manifest["selected_segment_ids"] = list(plan.selected_segment_ids)
    return manifest


def _coerce_selected_output_mode(output_mode: str | None) -> OutputMode:
    normalized = str(output_mode or "").strip()
    if normalized == "selected_with_context":
        return "selected_with_context"
    return "selected_only"


def _coerce_full_document_output_mode(output_mode: str | None) -> OutputMode:
    normalized = str(output_mode or "").strip()
    if normalized == "hybrid_document":
        return "hybrid_document"
    if normalized == "final_translated_book":
        return "final_translated_book"
    return "legacy_full_document"


def load_segment_result_records(
    *,
    prepared_source_key: str,
    structure_fingerprint: str,
    input_dir: Path = SEGMENT_RESULT_REGISTRY_DIR,
) -> dict[str, dict[str, object]]:
    normalized_source_key = _sanitize_identity_component(prepared_source_key)
    normalized_fingerprint = _sanitize_identity_component(structure_fingerprint)
    if not normalized_source_key or not normalized_fingerprint:
        return {}

    target_dir = input_dir / normalized_source_key / normalized_fingerprint
    if not target_dir.exists():
        return {}

    records_by_segment: dict[str, tuple[float, dict[str, object]]] = {}
    for artifact_path in target_dir.glob("*.segment-result.json"):
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        segment_id = str(payload.get("segment_id") or "").strip()
        translated_markdown = str(payload.get("translated_markdown") or "").strip()
        if not segment_id or not translated_markdown:
            continue
        try:
            modified_at = artifact_path.stat().st_mtime
        except OSError:
            modified_at = 0.0
        previous = records_by_segment.get(segment_id)
        if previous is None or modified_at >= previous[0]:
            records_by_segment[segment_id] = (modified_at, payload)
    return {segment_id: payload for segment_id, (_, payload) in records_by_segment.items()}


def assemble_hybrid_document(
    *,
    plan: ReassemblyPlan,
    source_paragraphs: Sequence[object] | None,
    current_segment_records: Mapping[str, Mapping[str, object]] | None = None,
    persisted_segment_records: Mapping[str, Mapping[str, object]] | None = None,
) -> HybridAssemblyResult:
    ordered_segment_ids = _collect_source_segment_ids(source_paragraphs) or plan.included_segment_ids
    paragraphs_by_segment = _group_source_paragraphs_by_segment(source_paragraphs)
    merged_segment_records: dict[str, Mapping[str, object]] = dict(persisted_segment_records or {})
    merged_segment_records.update(dict(current_segment_records or {}))

    markdown_parts: list[str] = []
    generated_paragraph_registry: list[dict[str, object]] = []
    segment_provenance_by_id: dict[str, str] = {}

    for segment_id in ordered_segment_ids:
        if segment_id not in plan.included_segment_ids:
            continue
        record = merged_segment_records.get(segment_id)
        translated_markdown = _coerce_record_text(record, "translated_markdown")
        if translated_markdown:
            markdown_parts.append(translated_markdown)
            generated_paragraph_registry.extend(
                _build_generated_registry_from_segment_record(
                    record=record,
                    fallback_block_index=len(generated_paragraph_registry),
                )
            )
            segment_provenance_by_id[segment_id] = "translated"
            continue

        source_markdown_parts = _build_source_segment_markdown_parts(paragraphs_by_segment.get(segment_id, ()))
        if not source_markdown_parts:
            continue
        markdown_parts.append("\n\n".join(source_markdown_parts))
        generated_paragraph_registry.extend(
            _build_generated_registry_from_source_paragraphs(
                segment_id=segment_id,
                paragraphs=paragraphs_by_segment.get(segment_id, ()),
                starting_block_index=len(generated_paragraph_registry),
            )
        )
        segment_provenance_by_id[segment_id] = "source"

    return HybridAssemblyResult(
        final_markdown="\n\n".join(part for part in markdown_parts if part.strip()).strip(),
        generated_paragraph_registry=generated_paragraph_registry,
        segment_provenance_by_id=segment_provenance_by_id,
    )


def build_segment_result_records(
    *,
    source_name: str,
    prepared_source_key: str,
    structure_fingerprint: str,
    plan: ReassemblyPlan,
    source_paragraphs: Sequence[object] | None,
    assembly_entries: Sequence[object],
    result_artifact_paths: Mapping[str, object],
) -> list[dict[str, object]]:
    prepared_source_key = str(prepared_source_key or "").strip()
    structure_fingerprint = str(structure_fingerprint or "").strip()
    if not prepared_source_key or not structure_fingerprint or not source_paragraphs or not assembly_entries:
        return []

    paragraph_segment_index = _build_paragraph_segment_index(source_paragraphs)
    selected_segment_ids = set(plan.selected_segment_ids)
    included_segment_ids = set(plan.included_segment_ids)
    records_by_segment: dict[str, dict[str, object]] = {}

    for entry in assembly_entries:
        segment_id = _resolve_entry_segment_id(entry, paragraph_segment_index)
        if segment_id is None or segment_id not in included_segment_ids:
            continue
        text = _coerce_entry_value(entry, "text")
        if not text:
            continue
        record = records_by_segment.setdefault(
            segment_id,
            {
                "schema_version": 1,
                "source_name": source_name,
                "prepared_source_key": prepared_source_key,
                "structure_fingerprint": structure_fingerprint,
                "segment_id": segment_id,
                "assembly_mode": plan.assembly_mode,
                "output_mode": plan.output_mode,
                "selected": segment_id in selected_segment_ids,
                "result_artifact_paths": dict(result_artifact_paths),
                "translated_markdown_parts": [],
                "paragraph_ids": [],
                "source_indexes": [],
                "entry_count": 0,
            },
        )
        translated_markdown_parts = cast(list[str], record["translated_markdown_parts"])
        paragraph_ids = cast(list[str], record["paragraph_ids"])
        source_indexes = cast(list[int], record["source_indexes"])
        translated_markdown_parts.append(text)
        raw_entry_count = record.get("entry_count", 0)
        record["entry_count"] = raw_entry_count if isinstance(raw_entry_count, int) else 0
        record["entry_count"] = int(record["entry_count"]) + 1
        _extend_unique(paragraph_ids, _collect_entry_paragraph_ids(entry))
        _extend_unique(source_indexes, _collect_entry_source_indexes(entry))

    records: list[dict[str, object]] = []
    for segment_id in plan.included_segment_ids:
        record = records_by_segment.get(segment_id)
        if record is None:
            continue
        raw_translated_markdown_parts = record.pop("translated_markdown_parts", [])
        translated_markdown_parts = (
            [part for part in raw_translated_markdown_parts if isinstance(part, str)]
            if isinstance(raw_translated_markdown_parts, list)
            else []
        )
        record["translated_markdown"] = "\n\n".join(translated_markdown_parts)
        records.append(record)
    return records


def _normalize_segment_ids(segment_ids: Sequence[object] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_segment_id in segment_ids or ():
        segment_id = str(raw_segment_id or "").strip()
        if not segment_id or segment_id in seen:
            continue
        seen.add(segment_id)
        normalized.append(segment_id)
    return tuple(normalized)


def _build_reassembly_coverage(*, plan: ReassemblyPlan, source_paragraphs: Sequence[object] | None) -> dict[str, object]:
    included_segment_ids = set(plan.included_segment_ids)
    paragraph_ranges_by_segment: dict[str, dict[str, int | str]] = {}

    for fallback_index, paragraph in enumerate(source_paragraphs or ()):
        segment_id = _coerce_object_text(paragraph, "segment_id")
        if segment_id is None or segment_id not in included_segment_ids:
            continue
        raw_source_index = getattr(paragraph, "source_index", fallback_index)
        paragraph_index = raw_source_index if isinstance(raw_source_index, int) and raw_source_index >= 0 else fallback_index
        entry = paragraph_ranges_by_segment.setdefault(
            segment_id,
            {
                "segment_id": segment_id,
                "start_paragraph_index": paragraph_index,
                "end_paragraph_index": paragraph_index,
                "paragraph_count": 0,
            },
        )
        entry["start_paragraph_index"] = min(int(entry["start_paragraph_index"]), paragraph_index)
        entry["end_paragraph_index"] = max(int(entry["end_paragraph_index"]), paragraph_index)
        entry["paragraph_count"] = int(entry["paragraph_count"]) + 1

    paragraph_ranges = [
        paragraph_ranges_by_segment[segment_id]
        for segment_id in plan.included_segment_ids
        if segment_id in paragraph_ranges_by_segment
    ]
    return {
        "segment_ids": list(plan.included_segment_ids),
        "paragraph_ranges": paragraph_ranges,
    }


def _collect_job_segment_ids(jobs: Sequence[object]) -> tuple[str, ...]:
    segment_ids: list[str] = []
    seen: set[str] = set()
    for job in jobs:
        segment_id = _coerce_job_segment_id(job)
        if segment_id is None or segment_id in seen:
            continue
        seen.add(segment_id)
        segment_ids.append(segment_id)
    return tuple(segment_ids)


def _resolve_included_segment_ids(
    *,
    jobs: Sequence[object],
    source_paragraphs: Sequence[object] | None,
    output_mode: str,
) -> tuple[str, ...]:
    if output_mode in {"hybrid_document", "final_translated_book"}:
        source_segment_ids = _collect_source_segment_ids(source_paragraphs)
        if source_segment_ids:
            return source_segment_ids
    return _collect_job_segment_ids(jobs)


def _resolve_selected_with_context_included_segment_ids(
    *,
    selected_segment_ids: Sequence[str],
    include_front_matter: bool,
    include_toc: bool,
    source_paragraphs: Sequence[object] | None,
) -> tuple[str, ...]:
    ordered_segment_ids = _collect_source_segment_ids(source_paragraphs)
    if not ordered_segment_ids:
        return tuple(selected_segment_ids)

    paragraphs_by_segment = _group_source_paragraphs_by_segment(source_paragraphs)

    selected_segment_set = set(selected_segment_ids)
    first_selected_index = next(
        (index for index, segment_id in enumerate(ordered_segment_ids) if segment_id in selected_segment_set),
        None,
    )
    if first_selected_index is None:
        return tuple(selected_segment_ids)

    included_segment_ids: list[str] = []
    seen: set[str] = set()
    for segment_id in ordered_segment_ids[:first_selected_index]:
        segment_kind = _resolve_leading_context_segment_kind(paragraphs_by_segment.get(segment_id, ()))
        if segment_kind == "front_matter" and not include_front_matter:
            continue
        if segment_kind == "toc" and not include_toc:
            continue
        if segment_kind is None:
            continue
        if segment_id in seen:
            continue
        seen.add(segment_id)
        included_segment_ids.append(segment_id)
    for segment_id in ordered_segment_ids[first_selected_index:]:
        if segment_id not in selected_segment_set or segment_id in seen:
            continue
        seen.add(segment_id)
        included_segment_ids.append(segment_id)
    return tuple(included_segment_ids) if included_segment_ids else tuple(selected_segment_ids)


def _collect_source_segment_ids(source_paragraphs: Sequence[object] | None) -> tuple[str, ...]:
    segment_ids: list[str] = []
    seen: set[str] = set()
    for paragraph in source_paragraphs or ():
        segment_id = _coerce_object_text(paragraph, "segment_id")
        if not segment_id or segment_id in seen:
            continue
        seen.add(segment_id)
        segment_ids.append(segment_id)
    return tuple(segment_ids)


def _build_segment_job_totals(jobs: Sequence[object]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for job in jobs:
        segment_id = _coerce_job_segment_id(job)
        if segment_id is None:
            continue
        totals[segment_id] = totals.get(segment_id, 0) + 1
    return totals


def _group_source_paragraphs_by_segment(source_paragraphs: Sequence[object] | None) -> dict[str, list[object]]:
    grouped: dict[str, list[object]] = {}
    for paragraph in source_paragraphs or ():
        segment_id = _coerce_object_text(paragraph, "segment_id")
        if not segment_id:
            continue
        grouped.setdefault(segment_id, []).append(paragraph)
    return grouped


def _resolve_leading_context_segment_kind(paragraphs: Sequence[object]) -> str | None:
    structural_roles = {
        _coerce_object_text(paragraph, "structural_role")
        for paragraph in paragraphs
        if _coerce_object_text(paragraph, "structural_role")
    }
    if not structural_roles:
        return None
    if structural_roles & {"toc", "toc_header", "toc_entry"}:
        return "toc"
    if structural_roles & {"front_matter", "epigraph", "attribution", "dedication"}:
        return "front_matter"
    if structural_roles & {"body", "body_range", "heading", "chapter", "section", "appendix", "bibliography"}:
        return None
    return None


def _build_paragraph_segment_index(source_paragraphs: Sequence[object]) -> dict[str, dict[object, str]]:
    paragraph_ids: dict[object, str] = {}
    source_indexes: dict[object, str] = {}
    for index, paragraph in enumerate(source_paragraphs):
        segment_id = _coerce_object_text(paragraph, "segment_id")
        if not segment_id:
            continue
        paragraph_id = _coerce_object_text(paragraph, "paragraph_id")
        if paragraph_id:
            paragraph_ids[paragraph_id] = segment_id
        source_indexes[index] = segment_id
    return {"paragraph_ids": paragraph_ids, "source_indexes": source_indexes}


def _resolve_entry_segment_id(entry: object, paragraph_segment_index: Mapping[str, dict[object, str]]) -> str | None:
    paragraph_ids = _collect_entry_paragraph_ids(entry)
    segment_ids = {
        paragraph_segment_index["paragraph_ids"][paragraph_id]
        for paragraph_id in paragraph_ids
        if paragraph_id in paragraph_segment_index["paragraph_ids"]
    }
    if len(segment_ids) == 1:
        return next(iter(segment_ids))
    source_indexes = _collect_entry_source_indexes(entry)
    indexed_segment_ids = {
        paragraph_segment_index["source_indexes"][source_index]
        for source_index in source_indexes
        if source_index in paragraph_segment_index["source_indexes"]
    }
    if len(indexed_segment_ids) == 1:
        return next(iter(indexed_segment_ids))
    return None


def _collect_entry_paragraph_ids(entry: object) -> list[str]:
    paragraph_ids: list[str] = []
    paragraph_id = _coerce_entry_value(entry, "paragraph_id")
    if paragraph_id:
        paragraph_ids.append(paragraph_id)
    merged_paragraph_ids = _coerce_entry_sequence(entry, "merged_paragraph_ids")
    _extend_unique(paragraph_ids, [item for item in merged_paragraph_ids if isinstance(item, str) and item.strip()])
    return paragraph_ids


def _collect_entry_source_indexes(entry: object) -> list[int]:
    raw_source_index = _coerce_entry_raw_value(entry, "source_index")
    return [raw_source_index] if isinstance(raw_source_index, int) and not isinstance(raw_source_index, bool) else []


def _coerce_entry_sequence(entry: object, field_name: str) -> Sequence[object]:
    value = _coerce_entry_raw_value(entry, field_name)
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _coerce_entry_value(entry: object, field_name: str) -> str:
    value = _coerce_entry_raw_value(entry, field_name)
    return str(value or "").strip()


def _coerce_entry_raw_value(entry: object, field_name: str) -> object:
    if isinstance(entry, Mapping):
        return entry.get(field_name)
    return getattr(entry, field_name, None)


def _coerce_object_text(value: object, attribute_name: str) -> str:
    return str(getattr(value, attribute_name, "") or "").strip()


def _coerce_record_text(record: Mapping[str, object] | None, field_name: str) -> str:
    if not isinstance(record, Mapping):
        return ""
    return str(record.get(field_name) or "").strip()


def _sanitize_identity_component(value: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in str(value or "").strip())
    compacted = "_".join(part for part in sanitized.split("_") if part)
    return compacted[:80]


def _build_source_segment_markdown_parts(paragraphs: Sequence[object]) -> list[str]:
    return [rendered_text for rendered_text in (_render_source_paragraph(paragraph) for paragraph in paragraphs) if rendered_text]


def _render_source_paragraph(paragraph: object) -> str:
    rendered_text = getattr(paragraph, "rendered_text", None)
    if isinstance(rendered_text, str) and rendered_text.strip():
        return rendered_text.strip()

    text = _coerce_object_text(paragraph, "text")
    if not text:
        return ""

    role = _coerce_object_text(paragraph, "role")
    structural_role = _coerce_object_text(paragraph, "structural_role")
    heading_level = getattr(paragraph, "heading_level", None)
    list_kind = _coerce_object_text(paragraph, "list_kind")
    list_level = getattr(paragraph, "list_level", 0)

    if role == "heading" and isinstance(heading_level, int) and heading_level > 0 and not text.startswith("#"):
        return f"{'#' * min(max(heading_level, 1), 6)} {text}"
    if structural_role in {"epigraph", "attribution", "dedication"}:
        return "\n".join(">" if not line.strip() else f"> {line}" for line in text.splitlines() or [text])
    if role == "list" and not re_matches_explicit_list_marker(text):
        indent = "  " * max(0, int(list_level) if isinstance(list_level, int) else 0)
        marker = "1." if list_kind == "ordered" else "-"
        return f"{indent}{marker} {text}"
    return text


def _build_generated_registry_from_source_paragraphs(
    *,
    segment_id: str,
    paragraphs: Sequence[object],
    starting_block_index: int,
) -> list[dict[str, object]]:
    registry: list[dict[str, object]] = []
    for offset, paragraph in enumerate(paragraphs):
        rendered_text = _render_source_paragraph(paragraph)
        if not rendered_text:
            continue
        paragraph_id = _coerce_object_text(paragraph, "paragraph_id") or f"{segment_id}:source:{offset}"
        registry.append(
            {
                "block_index": starting_block_index + len(registry),
                "paragraph_id": paragraph_id,
                "text": rendered_text,
            }
        )
    return registry


def _build_generated_registry_from_segment_record(
    *,
    record: Mapping[str, object] | None,
    fallback_block_index: int,
) -> list[dict[str, object]]:
    if not isinstance(record, Mapping):
        return []
    translated_markdown = _coerce_record_text(record, "translated_markdown")
    raw_paragraph_ids = record.get("paragraph_ids", [])
    paragraph_ids = [item for item in raw_paragraph_ids if isinstance(item, str) and item.strip()] if isinstance(raw_paragraph_ids, list) else []
    paragraph_id = paragraph_ids[0] if paragraph_ids else _coerce_record_text(record, "segment_id")
    if not translated_markdown or not paragraph_id:
        return []
    payload: dict[str, object] = {
        "block_index": fallback_block_index,
        "paragraph_id": paragraph_id,
        "text": translated_markdown,
    }
    if len(paragraph_ids) > 1:
        payload["merged_paragraph_ids"] = paragraph_ids
    return [payload]


def re_matches_explicit_list_marker(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith(("- ", "* ", "• ")) or (len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in {".", ")"})


def _extend_unique(target: list[T], values: Sequence[T]) -> None:
    for value in values:
        if value in target:
            continue
        target.append(value)

def _coerce_job_segment_id(job: object) -> str | None:
    if not isinstance(job, Mapping):
        return None
    raw_segment_id = job.get("segment_id")
    segment_id = str(raw_segment_id or "").strip()
    return segment_id or None