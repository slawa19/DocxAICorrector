"""Unit-accounting / target-alignment helpers from ``validation/structural.py``
(spec 034, Step 4, Cluster E -- the largest cluster).

Source-paragraph unit membership, registry-text normalization, target-index alignment,
and the unit-aware unmapped-field derivation. Depends only on stdlib / typing and on
``_projection_has_units_or_operations`` from the lower ``structural_toc_signals`` leaf --
never on the ``structural`` orchestration module -- so no import cycle is introduced. Bodies
are byte-identical to their former in-module definitions; ``structural`` re-exports them so
the qualified names keep resolving. (``_emit_target_alignment_trace_artifact`` stays resident
in ``structural`` because a characterization golden monkeypatches
``structural.write_formatting_diagnostics_artifact``, which its body calls.)
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
import re
from typing import Any, cast

from docxaicorrector.validation.structural_toc_signals import _projection_has_units_or_operations


def _paragraph_id_for_unit_accounting(paragraph: object, fallback_index: int) -> str:
    paragraph_id = str(getattr(paragraph, "paragraph_id", "") or "").strip()
    if paragraph_id:
        return paragraph_id
    source_index = int(getattr(paragraph, "source_index", fallback_index) or fallback_index)
    return f"p{source_index:04d}"


def _logical_index_for_unit_accounting(paragraph: object, fallback_index: int) -> int:
    logical_index = getattr(paragraph, "logical_index", None)
    if logical_index is not None:
        return int(logical_index)
    source_index = getattr(paragraph, "source_index", fallback_index)
    return int(source_index if source_index is not None else fallback_index)


def _projection_units_for_logical_index(projection: object | None, logical_index: int) -> tuple[object, ...]:
    if projection is None:
        return ()
    get_units = getattr(projection, "get_units", None)
    if callable(get_units):
        try:
            resolved = get_units(int(logical_index))
        except Exception:
            resolved = ()
        return tuple(cast(Sequence[object], resolved or ()))
    return tuple(
        unit
        for unit in tuple(getattr(projection, "projected_units", ()) or ())
        if int(logical_index) in tuple(int(index) for index in tuple(getattr(unit, "logical_indexes", ()) or ()))
    )


def _build_source_paragraph_unit_membership(
    source_paragraphs: Sequence[object],
    topology_projection: object | None,
) -> tuple[dict[str, frozenset[str]], set[str]]:
    paragraph_unit_keys: dict[str, frozenset[str]] = {}
    all_unit_keys: set[str] = set()
    for fallback_index, paragraph in enumerate(source_paragraphs):
        paragraph_id = _paragraph_id_for_unit_accounting(paragraph, fallback_index)
        logical_index = _logical_index_for_unit_accounting(paragraph, fallback_index)
        unit_keys = {
            str(getattr(unit, "unit_id", "") or "").strip()
            for unit in _projection_units_for_logical_index(topology_projection, logical_index)
            if str(getattr(unit, "unit_id", "") or "").strip()
        }
        if not unit_keys:
            unit_keys = {f"paragraph:{paragraph_id}"}
        paragraph_unit_keys[paragraph_id] = frozenset(unit_keys)
        all_unit_keys.update(unit_keys)
    return paragraph_unit_keys, all_unit_keys


def _normalize_registry_text_for_unit_alignment(value: object) -> str:
    text = str(value or "")
    normalized_lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^#{1,6}\s+", "", stripped)
        stripped = re.sub(r"^\(?\d{1,4}[.)]\s+", "", stripped)
        normalized_lines.append(stripped)
    return re.sub(r"\s+", " ", " ".join(normalized_lines)).strip().lower()


def _normalize_registry_preview_for_unit_alignment(value: object, *, limit: int = 120) -> str:
    normalized = _normalize_registry_text_for_unit_alignment(value)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _registry_text_matches_target_preview(target_preview: object, generated_text: object) -> bool:
    normalized_target_preview = _normalize_registry_text_for_unit_alignment(target_preview)
    if not normalized_target_preview:
        return False
    normalized_generated_text = _normalize_registry_text_for_unit_alignment(generated_text)
    if normalized_target_preview == normalized_generated_text:
        return True
    return normalized_target_preview == _normalize_registry_preview_for_unit_alignment(generated_text)


def _build_generated_registry_text_by_paragraph_id(
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> dict[str, str]:
    registry_text_by_paragraph_id: dict[str, str] = {}
    if not generated_paragraph_registry:
        return registry_text_by_paragraph_id
    for entry in generated_paragraph_registry:
        paragraph_id = str(entry.get("paragraph_id") or "").strip()
        text = entry.get("text")
        if paragraph_id and isinstance(text, str) and text.strip():
            registry_text_by_paragraph_id[paragraph_id] = text
    return registry_text_by_paragraph_id


def _generated_paragraph_spans_empty_body_interval_target(
    *,
    generated_text: object,
    previous_target_preview: object,
    unresolved_target_preview: object,
) -> bool:
    normalized_generated_text = _normalize_registry_text_for_unit_alignment(generated_text)
    normalized_previous_target_preview = _normalize_registry_text_for_unit_alignment(previous_target_preview)
    normalized_unresolved_target_preview = _normalize_registry_text_for_unit_alignment(unresolved_target_preview)
    if not normalized_generated_text or not normalized_previous_target_preview or not normalized_unresolved_target_preview:
        return False
    if not normalized_generated_text.startswith(normalized_previous_target_preview):
        return False
    trailing_generated_text = normalized_generated_text[len(normalized_previous_target_preview) :].strip()
    if not trailing_generated_text:
        return False
    return _registry_text_matches_target_preview(normalized_unresolved_target_preview, trailing_generated_text)


def _registry_entry_unit_keys(
    entry: Mapping[str, object],
    paragraph_unit_keys: Mapping[str, frozenset[str]],
) -> frozenset[str]:
    paragraph_ids: list[str] = []
    primary_id = str(entry.get("paragraph_id") or "").strip()
    if primary_id:
        paragraph_ids.append(primary_id)
    merged_ids = entry.get("merged_paragraph_ids")
    if isinstance(merged_ids, Sequence) and not isinstance(merged_ids, (str, bytes, bytearray)):
        paragraph_ids.extend(str(value).strip() for value in merged_ids if str(value).strip())
    unit_keys: set[str] = set()
    for paragraph_id in paragraph_ids:
        unit_keys.update(paragraph_unit_keys.get(paragraph_id, frozenset()))
    return frozenset(unit_keys)


def _registry_entry_relation_ids(entry: Mapping[str, object]) -> tuple[str, ...]:
    raw_relation_ids = entry.get("relation_ids")
    if not isinstance(raw_relation_ids, Sequence) or isinstance(raw_relation_ids, (str, bytes, bytearray)):
        return ()
    relation_ids: list[str] = []
    for value in raw_relation_ids:
        relation_id = str(value).strip()
        if relation_id and relation_id not in relation_ids:
            relation_ids.append(relation_id)
    return tuple(relation_ids)


def _merge_target_alignment_unit_keys(
    alignments: dict[int, frozenset[str]],
    *,
    target_index: int,
    unit_keys: frozenset[str] | set[str],
) -> None:
    if target_index < 0 or not unit_keys:
        return
    merged_keys = set(alignments.get(target_index, frozenset()))
    merged_keys.update(str(value).strip() for value in unit_keys if str(value).strip())
    if merged_keys:
        alignments[target_index] = frozenset(merged_keys)


def _build_target_alignments_from_source_registry(
    formatting_payload: Mapping[str, object],
    *,
    paragraph_unit_keys: Mapping[str, frozenset[str]],
) -> tuple[dict[int, frozenset[str]], dict[int, list[int]], list[Mapping[str, object]]]:
    source_registry = formatting_payload.get("source_registry")
    if not isinstance(source_registry, list):
        return {}, {}, []
    alignments: dict[int, frozenset[str]] = {}
    source_positions_by_target_index: dict[int, list[int]] = {}
    normalized_source_entries: list[Mapping[str, object]] = []
    entry_unit_keys_by_position: list[frozenset[str]] = []
    relation_unit_keys_by_id: dict[str, set[str]] = {}
    for entry in source_registry:
        if not isinstance(entry, Mapping):
            continue
        normalized_entry = cast(Mapping[str, object], entry)
        normalized_source_entries.append(normalized_entry)
        unit_keys = _registry_entry_unit_keys(normalized_entry, paragraph_unit_keys)
        entry_unit_keys_by_position.append(unit_keys)
        for relation_id in _registry_entry_relation_ids(normalized_entry):
            relation_unit_keys_by_id.setdefault(relation_id, set()).update(unit_keys)
    for position, normalized_entry in enumerate(normalized_source_entries):
        unit_keys = set(entry_unit_keys_by_position[position])
        for relation_id in _registry_entry_relation_ids(normalized_entry):
            unit_keys.update(relation_unit_keys_by_id.get(relation_id, set()))
        try:
            raw_target_index = normalized_entry.get("mapped_target_index", -1)
            target_index = int(cast(Any, raw_target_index if raw_target_index is not None else -1))
        except (TypeError, ValueError):
            continue
        if target_index < 0:
            continue
        _merge_target_alignment_unit_keys(alignments, target_index=target_index, unit_keys=unit_keys)
        source_positions_by_target_index.setdefault(target_index, []).append(position)
    return alignments, source_positions_by_target_index, normalized_source_entries


def _infer_target_alignment_unit_keys_from_source_intervals(
    formatting_payload: Mapping[str, object],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
    paragraph_unit_keys: Mapping[str, frozenset[str]],
    alignments: dict[int, frozenset[str]],
    source_positions_by_target_index: Mapping[int, Sequence[int]],
    source_registry_entries: Sequence[Mapping[str, object]],
) -> None:
    target_registry = formatting_payload.get("target_registry")
    if not isinstance(target_registry, list):
        return
    candidate_unmapped_target_indexes = formatting_payload.get("unmapped_target_indexes")
    if not isinstance(candidate_unmapped_target_indexes, list):
        return
    unresolved_target_indexes: list[int] = []
    for value in candidate_unmapped_target_indexes:
        try:
            unresolved_target_indexes.append(int(cast(Any, value)))
        except (TypeError, ValueError):
            continue
    if not unresolved_target_indexes or not source_positions_by_target_index:
        return
    mapped_target_indexes = sorted(source_positions_by_target_index)
    if len(mapped_target_indexes) < 2:
        return
    target_registry_by_index: dict[int, Mapping[str, object]] = {}
    for entry in target_registry:
        if not isinstance(entry, Mapping):
            continue
        try:
            raw_target_index = entry.get("target_index", -1)
            target_index = int(cast(Any, raw_target_index if raw_target_index is not None else -1))
        except (TypeError, ValueError):
            continue
        if target_index >= 0:
            target_registry_by_index[target_index] = cast(Mapping[str, object], entry)
    generated_registry_text_by_paragraph_id = _build_generated_registry_text_by_paragraph_id(generated_paragraph_registry)
    unresolved_target_set = set(unresolved_target_indexes)
    for target_index in unresolved_target_indexes:
        if alignments.get(target_index):
            continue
        previous_target_indexes = [value for value in mapped_target_indexes if value < target_index]
        next_target_indexes = [value for value in mapped_target_indexes if value > target_index]
        if not previous_target_indexes or not next_target_indexes:
            continue
        previous_target_index = previous_target_indexes[-1]
        next_target_index = next_target_indexes[0]
        unresolved_targets_in_interval = [
            value
            for value in unresolved_target_set
            if previous_target_index < value < next_target_index and not alignments.get(value)
        ]
        if not unresolved_targets_in_interval or target_index != unresolved_targets_in_interval[0]:
            continue
        previous_source_position = max(int(value) for value in source_positions_by_target_index.get(previous_target_index, ()))
        next_source_position = min(int(value) for value in source_positions_by_target_index.get(next_target_index, ()))
        if previous_source_position >= next_source_position:
            continue
        interval_unit_keys: set[str] = set()
        for source_entry in source_registry_entries[previous_source_position + 1 : next_source_position]:
            try:
                raw_mapped_target_index = source_entry.get("mapped_target_index", -1)
                mapped_target_index = int(cast(Any, raw_mapped_target_index if raw_mapped_target_index is not None else -1))
            except (TypeError, ValueError):
                mapped_target_index = -1
            if mapped_target_index >= 0:
                continue
            interval_unit_keys.update(_registry_entry_unit_keys(source_entry, paragraph_unit_keys))
        if (
            not interval_unit_keys
            and next_source_position == previous_source_position + 1
            and len(unresolved_targets_in_interval) == 1
            and generated_registry_text_by_paragraph_id
        ):
            previous_source_entry = source_registry_entries[previous_source_position]
            previous_paragraph_id = str(previous_source_entry.get("paragraph_id") or "").strip()
            previous_generated_text = generated_registry_text_by_paragraph_id.get(previous_paragraph_id, "")
            previous_target_entry = target_registry_by_index.get(previous_target_index)
            unresolved_target_entry = target_registry_by_index.get(unresolved_targets_in_interval[0])
            if previous_target_entry is not None and unresolved_target_entry is not None and _generated_paragraph_spans_empty_body_interval_target(
                generated_text=previous_generated_text,
                previous_target_preview=previous_target_entry.get("text_preview"),
                unresolved_target_preview=unresolved_target_entry.get("text_preview"),
            ):
                interval_unit_keys.update(_registry_entry_unit_keys(previous_source_entry, paragraph_unit_keys))
        if not interval_unit_keys:
            continue
        for unresolved_target_index in unresolved_targets_in_interval:
            _merge_target_alignment_unit_keys(
                alignments,
                target_index=unresolved_target_index,
                unit_keys=interval_unit_keys,
            )


def _align_target_indexes_from_generated_registry(
    formatting_payload: Mapping[str, object],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
    paragraph_unit_keys: Mapping[str, frozenset[str]],
    trace_target_indexes: Collection[int] | None = None,
) -> tuple[dict[int, frozenset[str]], dict[int, dict[str, object]]]:
    target_registry = formatting_payload.get("target_registry")
    if not isinstance(target_registry, list) or not generated_paragraph_registry:
        return {}, {}
    generated_entries = [entry for entry in generated_paragraph_registry if isinstance(entry, Mapping)]
    if not generated_entries:
        return {}, {}

    requested_trace_indexes: set[int] = set()
    if trace_target_indexes is not None:
        for value in trace_target_indexes:
            try:
                requested_trace_indexes.add(int(cast(Any, value)))
            except (TypeError, ValueError):
                continue

    alignments: dict[int, frozenset[str]] = {}
    trace_by_target_index: dict[int, dict[str, object]] = {}
    generated_index = 0
    for target_entry in target_registry:
        if not isinstance(target_entry, Mapping):
            continue
        raw_target_index = target_entry.get("target_index", -1)
        target_index = int(cast(Any, raw_target_index if raw_target_index is not None else -1))
        if target_index < 0:
            continue
        target_preview = _normalize_registry_text_for_unit_alignment(target_entry.get("text_preview"))
        trace_entry: dict[str, object] | None = None
        if target_index in requested_trace_indexes:
            trace_entry = {
                "target_index": target_index,
                "target_preview": target_preview,
                "candidate_generated_previews": [],
                "match_result": "no_match",
                "chosen_generated_paragraph_id": None,
                "chosen_generated_preview": None,
                "unit_keys": [],
            }
        search_index = generated_index
        while search_index < len(generated_entries):
            generated_entry = generated_entries[search_index]
            generated_text = generated_entry.get("text")
            generated_preview = _normalize_registry_text_for_unit_alignment(generated_text)
            if not generated_preview:
                search_index += 1
                generated_index = search_index
                continue
            preview_matches = not target_preview or _registry_text_matches_target_preview(target_preview, generated_text)
            if trace_entry is not None:
                candidate_previews = cast(list[dict[str, object]], trace_entry["candidate_generated_previews"])
                candidate_previews.append(
                    {
                        "paragraph_id": str(generated_entry.get("paragraph_id") or "").strip() or None,
                        "generated_preview": generated_preview,
                        "matches_target_preview": preview_matches,
                    }
                )
            if not preview_matches:
                search_index += 1
                continue
            unit_keys = _registry_entry_unit_keys(generated_entry, paragraph_unit_keys)
            _merge_target_alignment_unit_keys(
                alignments,
                target_index=target_index,
                unit_keys=unit_keys,
            )
            if trace_entry is not None:
                trace_entry["match_result"] = "matched"
                trace_entry["chosen_generated_paragraph_id"] = str(generated_entry.get("paragraph_id") or "").strip() or None
                trace_entry["chosen_generated_preview"] = generated_preview
                trace_entry["unit_keys"] = sorted(unit_keys)
            generated_index = search_index + 1
            break
        if trace_entry is not None:
            trace_by_target_index[target_index] = trace_entry
    return alignments, trace_by_target_index


def _collect_target_alignment_preview_trace(
    formatting_payload: Mapping[str, object],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
    paragraph_unit_keys: Mapping[str, frozenset[str]],
    target_indexes: Sequence[int],
) -> list[dict[str, object]]:
    if not target_indexes:
        return []
    requested_indexes: list[int] = []
    for value in target_indexes:
        try:
            requested_indexes.append(int(cast(Any, value)))
        except (TypeError, ValueError):
            continue
    if not requested_indexes:
        return []
    _, trace_by_target_index = _align_target_indexes_from_generated_registry(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
        trace_target_indexes=requested_indexes,
    )
    return [trace_by_target_index[target_index] for target_index in requested_indexes if target_index in trace_by_target_index]


def _align_target_indexes_to_unit_keys(
    formatting_payload: Mapping[str, object],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
    paragraph_unit_keys: Mapping[str, frozenset[str]],
) -> dict[int, frozenset[str]] | None:
    alignments, source_positions_by_target_index, source_registry_entries = _build_target_alignments_from_source_registry(
        formatting_payload,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    target_registry = formatting_payload.get("target_registry")
    if not isinstance(target_registry, list):
        return None
    generated_registry_alignments, _ = _align_target_indexes_from_generated_registry(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    for target_index, unit_keys in generated_registry_alignments.items():
        _merge_target_alignment_unit_keys(
            alignments,
            target_index=target_index,
            unit_keys=unit_keys,
        )
    _infer_target_alignment_unit_keys_from_source_intervals(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
        alignments=alignments,
        source_positions_by_target_index=source_positions_by_target_index,
        source_registry_entries=source_registry_entries,
    )
    return alignments or None


def _truncate_target_alignment_trace_preview(value: object, *, limit: int = 80) -> str | None:
    normalized = _normalize_registry_text_for_unit_alignment(value)
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _serialize_compact_target_alignment_trace_entry(entry: Mapping[str, object]) -> dict[str, object]:
    unit_keys = entry.get("unit_keys")
    normalized_unit_keys = [
        str(value).strip()
        for value in cast(Sequence[object], unit_keys or ())
        if str(value).strip()
    ]
    return {
        "target_index": int(cast(Any, entry.get("target_index", -1))),
        "target_preview": _truncate_target_alignment_trace_preview(entry.get("target_preview")),
        "match_result": str(entry.get("match_result") or "").strip(),
        "chosen_generated_paragraph_id": str(entry.get("chosen_generated_paragraph_id") or "").strip() or None,
        "chosen_generated_preview": _truncate_target_alignment_trace_preview(entry.get("chosen_generated_preview")),
        "unit_keys": sorted(normalized_unit_keys),
    }


def _derive_unit_aware_unmapped_fields(
    *,
    source_paragraphs: Sequence[object],
    topology_projection: object | None,
    formatting_payload: Mapping[str, object] | None,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> dict[str, object]:
    unmapped_source_ids = []
    unmapped_target_indexes = []
    if formatting_payload is not None:
        candidate_source_ids = formatting_payload.get("unmapped_source_ids")
        if isinstance(candidate_source_ids, list):
            unmapped_source_ids = [str(value).strip() for value in candidate_source_ids if str(value).strip()]
        candidate_target_indexes = formatting_payload.get("unmapped_target_indexes")
        if isinstance(candidate_target_indexes, list):
            unresolved_indexes: list[int] = []
            for value in candidate_target_indexes:
                try:
                    unresolved_indexes.append(int(cast(Any, value)))
                except (TypeError, ValueError):
                    continue
            unmapped_target_indexes = unresolved_indexes
    accepted_aggregated_source_ids: set[str] = set()
    accepted_aggregated_target_indexes: set[int] = set()
    if formatting_payload is not None:
        accepted_aggregated_sources = formatting_payload.get("accepted_aggregated_sources")
        if isinstance(accepted_aggregated_sources, list):
            for raw_entry in accepted_aggregated_sources:
                if not isinstance(raw_entry, Mapping):
                    continue
                paragraph_id = str(raw_entry.get("paragraph_id") or "").strip()
                if paragraph_id:
                    accepted_aggregated_source_ids.add(paragraph_id)
                try:
                    target_index = int(cast(Any, raw_entry.get("target_index", -1)))
                except (TypeError, ValueError):
                    continue
                if target_index >= 0:
                    accepted_aggregated_target_indexes.add(target_index)
    legacy_effective_unmapped_source_ids = [
        paragraph_id for paragraph_id in unmapped_source_ids if paragraph_id not in accepted_aggregated_source_ids
    ]
    legacy_effective_unmapped_target_indexes = [
        target_index for target_index in unmapped_target_indexes if target_index not in accepted_aggregated_target_indexes
    ]
    legacy_aggregation_adjusted = (
        len(legacy_effective_unmapped_source_ids) != len(unmapped_source_ids)
        or len(legacy_effective_unmapped_target_indexes) != len(unmapped_target_indexes)
    )
    fields: dict[str, object] = {
        "raw_unmapped_source_paragraph_count": len(unmapped_source_ids),
        "raw_unmapped_target_paragraph_count": len(unmapped_target_indexes),
        "structure_unit_unmapped_source_count": len(legacy_effective_unmapped_source_ids),
        "structure_unit_unmapped_target_count": len(legacy_effective_unmapped_target_indexes),
        "unit_covered_source_fragment_count": 0,
        "unit_covered_target_fragment_count": 0,
        "accepted_aggregated_source_unit_count": len(accepted_aggregated_source_ids),
        "accepted_aggregated_target_index_count": len(accepted_aggregated_target_indexes),
        "unmapped_source_count_basis": "accepted_aggregation_legacy" if legacy_aggregation_adjusted else "legacy_paragraph",
        "unmapped_target_count_basis": "accepted_aggregation_legacy" if legacy_aggregation_adjusted else "legacy_paragraph",
        "unit_unmapped_source_gate_source": "accepted_aggregation_legacy" if legacy_aggregation_adjusted else "legacy_paragraph",
        "unit_unmapped_target_gate_source": "accepted_aggregation_legacy" if legacy_aggregation_adjusted else "legacy_paragraph",
    }
    if formatting_payload is None or not _projection_has_units_or_operations(topology_projection):
        return fields
    paragraph_unit_keys, all_unit_keys = _build_source_paragraph_unit_membership(source_paragraphs, topology_projection)
    if not paragraph_unit_keys:
        return fields
    unmapped_source_unit_keys: set[str] = set()
    for paragraph_id in unmapped_source_ids:
        unmapped_source_unit_keys.update(paragraph_unit_keys.get(paragraph_id, frozenset({f"paragraph:{paragraph_id}"})))
    accepted_aggregated_source_unit_keys: set[str] = set()
    accepted_aggregated_target_unit_keys_by_index: dict[int, set[str]] = {}
    accepted_aggregated_sources = formatting_payload.get("accepted_aggregated_sources")
    if isinstance(accepted_aggregated_sources, list):
        for raw_entry in accepted_aggregated_sources:
            if not isinstance(raw_entry, Mapping):
                continue
            paragraph_id = str(raw_entry.get("paragraph_id") or "").strip()
            if not paragraph_id:
                continue
            unit_keys = set(paragraph_unit_keys.get(paragraph_id, frozenset({f"paragraph:{paragraph_id}"})))
            accepted_aggregated_source_unit_keys.update(unit_keys)
            try:
                target_index = int(cast(Any, raw_entry.get("target_index", -1)))
            except (TypeError, ValueError):
                continue
            if target_index >= 0:
                accepted_aggregated_target_unit_keys_by_index.setdefault(target_index, set()).update(unit_keys)
    aligned_target_unit_keys = _align_target_indexes_to_unit_keys(
        formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
        paragraph_unit_keys=paragraph_unit_keys,
    )
    if accepted_aggregated_target_unit_keys_by_index:
        merged_alignments: dict[int, frozenset[str]] = dict(aligned_target_unit_keys or {})
        for target_index, unit_keys in accepted_aggregated_target_unit_keys_by_index.items():
            _merge_target_alignment_unit_keys(merged_alignments, target_index=target_index, unit_keys=unit_keys)
        aligned_target_unit_keys = merged_alignments
    generated_registry_aligned_target_indexes: set[int] = set()
    if generated_paragraph_registry:
        generated_registry_aligned_target_indexes = set(
            _align_target_indexes_from_generated_registry(
                formatting_payload,
                generated_paragraph_registry=generated_paragraph_registry,
                paragraph_unit_keys=paragraph_unit_keys,
            )[0]
        )
    target_registry = formatting_payload.get("target_registry")
    covered_target_unit_keys: set[str] = set()
    if aligned_target_unit_keys is not None and isinstance(target_registry, list):
        for target_entry in target_registry:
            if not isinstance(target_entry, Mapping):
                continue
            if not bool(target_entry.get("mapped")):
                continue
            try:
                raw_target_index = target_entry.get("target_index", -1)
                target_index = int(cast(Any, raw_target_index if raw_target_index is not None else -1))
            except (TypeError, ValueError):
                continue
            if target_index < 0:
                continue
            covered_target_unit_keys.update(aligned_target_unit_keys.get(target_index, frozenset()))
    for unit_keys in accepted_aggregated_target_unit_keys_by_index.values():
        covered_target_unit_keys.update(unit_keys)
    effective_unmapped_source_unit_keys = set(unmapped_source_unit_keys)
    if accepted_aggregated_source_unit_keys:
        effective_unmapped_source_unit_keys.difference_update(accepted_aggregated_source_unit_keys)
    if covered_target_unit_keys:
        effective_unmapped_source_unit_keys.difference_update(covered_target_unit_keys)
    fields.update(
        {
            "structure_unit_total_count": len(all_unit_keys),
            "structure_unit_unmapped_source_count": len(effective_unmapped_source_unit_keys),
            "unit_covered_source_fragment_count": max(0, len(all_unit_keys) - len(effective_unmapped_source_unit_keys)),
            "accepted_aggregated_source_unit_count": len(accepted_aggregated_source_unit_keys),
            "accepted_aggregated_target_index_count": len(accepted_aggregated_target_unit_keys_by_index),
            "unmapped_source_count_basis": "topology_unit",
            "unit_unmapped_source_gate_source": "topology_unit",
        }
    )
    if not unmapped_target_indexes:
        fields.update(
            {
                "structure_unit_unmapped_target_count": 0,
                "unit_covered_target_fragment_count": len(covered_target_unit_keys),
                "unmapped_target_count_basis": "topology_unit",
                "unit_unmapped_target_gate_source": "topology_unit",
            }
        )
        return fields
    if aligned_target_unit_keys is None:
        return fields
    aligned_unmapped_target_indexes = [
        target_index for target_index in unmapped_target_indexes if aligned_target_unit_keys.get(target_index)
    ]
    if not aligned_unmapped_target_indexes:
        return fields
    unmapped_target_unit_keys: set[str] = set()
    preserved_interval_topology_unit_keys: set[str] = set()
    for target_index in aligned_unmapped_target_indexes:
        target_unit_keys = aligned_target_unit_keys.get(target_index, frozenset())
        unmapped_target_unit_keys.update(target_unit_keys)
        if target_index in generated_registry_aligned_target_indexes:
            continue
        if unmapped_source_ids:
            preserved_interval_topology_unit_keys.update(
                key for key in target_unit_keys if isinstance(key, str) and not key.startswith("paragraph:")
            )
    if covered_target_unit_keys:
        unmapped_target_unit_keys.difference_update(covered_target_unit_keys)
        unmapped_target_unit_keys.update(preserved_interval_topology_unit_keys)
    shared_unmapped_unit_keys = effective_unmapped_source_unit_keys & unmapped_target_unit_keys
    if shared_unmapped_unit_keys:
        effective_unmapped_source_unit_keys.difference_update(shared_unmapped_unit_keys)
        unmapped_target_unit_keys.difference_update(shared_unmapped_unit_keys)
        fields.update(
            {
                "structure_unit_unmapped_source_count": len(effective_unmapped_source_unit_keys),
                "unit_covered_source_fragment_count": max(0, len(all_unit_keys) - len(effective_unmapped_source_unit_keys)),
            }
        )
    if len(aligned_unmapped_target_indexes) != len(unmapped_target_indexes):
        return fields
    fields.update(
        {
            "structure_unit_unmapped_source_count": len(effective_unmapped_source_unit_keys),
            "unit_covered_source_fragment_count": max(0, len(all_unit_keys) - len(effective_unmapped_source_unit_keys)),
            "structure_unit_unmapped_target_count": len(unmapped_target_unit_keys),
            "unit_covered_target_fragment_count": len(covered_target_unit_keys | shared_unmapped_unit_keys),
            "unmapped_target_count_basis": "topology_unit",
            "unit_unmapped_target_gate_source": "topology_unit",
        }
    )
    return fields
