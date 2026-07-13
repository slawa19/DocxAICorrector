from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias, TypeVar, cast

from docxaicorrector.core.constants import SEGMENT_RESULT_REGISTRY_DIR


AssemblyMode: TypeAlias = Literal["full_document"]
OutputMode: TypeAlias = Literal["legacy_full_document"]


@dataclass(frozen=True)
class ReassemblyPlan:
    assembly_mode: AssemblyMode
    output_mode: OutputMode
    selected_segment_ids: tuple[str, ...]
    included_segment_ids: tuple[str, ...]
    selected_segment_count: int | None


T = TypeVar("T")


def build_reassembly_plan(
    *,
    output_mode: str | None = None,
    jobs: Sequence[object],
    source_paragraphs: Sequence[object] | None = None,
) -> ReassemblyPlan:
    included_segment_ids = _resolve_included_segment_ids(jobs=jobs)
    return ReassemblyPlan(
        assembly_mode="full_document",
        output_mode="legacy_full_document",
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


def _resolve_included_segment_ids(*, jobs: Sequence[object]) -> tuple[str, ...]:
    return _collect_job_segment_ids(jobs)


def _build_segment_job_totals(jobs: Sequence[object]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for job in jobs:
        segment_id = _coerce_job_segment_id(job)
        if segment_id is None:
            continue
        totals[segment_id] = totals.get(segment_id, 0) + 1
    return totals


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


def _sanitize_identity_component(value: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in str(value or "").strip())
    compacted = "_".join(part for part in sanitized.split("_") if part)
    return compacted[:80]


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