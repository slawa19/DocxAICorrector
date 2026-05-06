from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias


AssemblyMode: TypeAlias = Literal["selected_chapters", "full_document"]
OutputMode: TypeAlias = Literal["selected_only", "selected_with_context", "legacy_full_document", "hybrid_document", "final_translated_book"]


@dataclass(frozen=True)
class ReassemblyPlan:
    assembly_mode: AssemblyMode
    output_mode: OutputMode
    selected_segment_ids: tuple[str, ...]
    included_segment_ids: tuple[str, ...]
    selected_segment_count: int | None


def build_reassembly_plan(*, selected_segment_ids: Sequence[object] | None, output_mode: str | None, jobs: Sequence[object]) -> ReassemblyPlan:
    normalized_selected_ids = _normalize_segment_ids(selected_segment_ids)
    included_segment_ids = normalized_selected_ids or _collect_job_segment_ids(jobs)
    if normalized_selected_ids:
        effective_output_mode = str(output_mode or "").strip() or "selected_only"
        if effective_output_mode not in {"selected_only", "selected_with_context"}:
            effective_output_mode = "selected_only"
        return ReassemblyPlan(
            assembly_mode="selected_chapters",
            output_mode=effective_output_mode,
            selected_segment_ids=normalized_selected_ids,
            included_segment_ids=included_segment_ids,
            selected_segment_count=len(normalized_selected_ids),
        )
    effective_output_mode = str(output_mode or "").strip() or "legacy_full_document"
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
    plan: ReassemblyPlan,
    jobs: Sequence[object],
    source_paragraphs: Sequence[object] | None,
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
        segments.append(segment_payload)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "source_name": source_name,
        "assembly_mode": plan.assembly_mode,
        "output_mode": plan.output_mode,
        "selected_segment_count": len(plan.selected_segment_ids),
        "included_segment_count": len(plan.included_segment_ids),
        "included_segment_ids": list(plan.included_segment_ids),
        "segments": segments,
    }
    if plan.selected_segment_ids:
        manifest["selected_segment_ids"] = list(plan.selected_segment_ids)
    return manifest


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


def _build_segment_job_totals(jobs: Sequence[object]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for job in jobs:
        segment_id = _coerce_job_segment_id(job)
        if segment_id is None:
            continue
        totals[segment_id] = totals.get(segment_id, 0) + 1
    return totals

def _coerce_job_segment_id(job: object) -> str | None:
    if not isinstance(job, Mapping):
        return None
    raw_segment_id = job.get("segment_id")
    segment_id = str(raw_segment_id or "").strip()
    return segment_id or None