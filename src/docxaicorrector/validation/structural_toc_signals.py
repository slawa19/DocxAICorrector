"""Topology / document-map / TOC-region detectors from ``validation/structural.py``
(spec 034, Step 3, Cluster D).

Pure leaf helpers over projection / document-map / paragraph objects. Depend only on
stdlib / typing -- never on the ``structural`` orchestration module -- so no import cycle
is introduced. Bodies are byte-identical to their former in-module definitions; ``structural``
re-exports them so the qualified names keep resolving (incl. ``quality_gate``'s deferred
``structural._derive_toc_body_concat_gate_fields`` attribute access).
"""

from __future__ import annotations

from collections.abc import Sequence


def _count_effective_toc_regions_from_source(paragraphs: Sequence[object]) -> int:
    count = 0
    index = 0
    paragraph_units = list(paragraphs)
    while index < len(paragraph_units):
        structural_role = _normalized_structural_role(paragraph_units[index])
        if structural_role != "toc_header":
            index += 1
            continue
        look_ahead = index + 1
        while look_ahead < len(paragraph_units) and _normalized_structural_role(paragraph_units[look_ahead]) == "toc_entry":
            look_ahead += 1
        if look_ahead - index >= 3:
            count += 1
            index = look_ahead
            continue
        index += 1
    return count


def _normalized_structural_role(paragraph: object) -> str:
    return str(getattr(paragraph, "structural_role", "") or "").strip().lower()


def _has_high_confidence_bounded_document_map_toc_region(document_map: object | None) -> bool:
    toc_region = getattr(document_map, "toc_region", None)
    if toc_region is None:
        return False
    if str(getattr(toc_region, "confidence", "") or "").strip().lower() != "high":
        return False
    return int(getattr(toc_region, "start_logical_index", 0)) <= int(getattr(toc_region, "end_logical_index", -1))


def _count_document_map_anchor_roles(document_map: object | None, *, role: str) -> int:
    paragraph_anchors = getattr(document_map, "paragraph_anchors", None)
    if not paragraph_anchors:
        return 0
    normalized_role = str(role or "").strip().lower()
    return sum(
        1
        for anchor in dict(paragraph_anchors).values()
        if str(getattr(anchor, "role", "") or "").strip().lower() == normalized_role
    )


def _count_topology_toc_entry_units(projection: object | None) -> int:
    projected_units = getattr(projection, "projected_units", None)
    if not projected_units:
        return 0
    return sum(
        1
        for unit in tuple(projected_units)
        if str(getattr(unit, "role", "") or "").strip().lower() == "toc_entry"
        or str(getattr(unit, "unit_type", "") or "").strip().lower() == "toc_entry"
    )


def _count_topology_operations(projection: object | None, *, op: str) -> int:
    operations = getattr(projection, "operations", None)
    if not operations:
        return 0
    normalized_op = str(op or "").strip().lower()
    count = 0
    for operation in tuple(operations):
        if str(getattr(operation, "op", "") or "").strip().lower() == normalized_op:
            count += 1
    return count


def _resolve_bounded_toc_region_range(document_map: object | None) -> tuple[int, int] | None:
    if not _has_high_confidence_bounded_document_map_toc_region(document_map):
        return None
    toc_region = getattr(document_map, "toc_region", None)
    if toc_region is None:
        return None
    return int(getattr(toc_region, "start_logical_index", 0)), int(getattr(toc_region, "end_logical_index", -1))


def _count_high_confidence_compound_toc_split_hints(document_map: object | None) -> int:
    toc_bounds = _resolve_bounded_toc_region_range(document_map)
    split_hints = getattr(document_map, "split_hints", None)
    if toc_bounds is None or not split_hints:
        return 0
    start_logical_index, end_logical_index = toc_bounds
    count = 0
    for split_hint in tuple(split_hints):
        if str(getattr(split_hint, "split_kind", "") or "").strip().lower() != "compound_toc_entries":
            continue
        if str(getattr(split_hint, "confidence", "") or "").strip().lower() != "high":
            continue
        logical_index = int(getattr(split_hint, "logical_index", -1) or -1)
        if logical_index < start_logical_index or logical_index > end_logical_index:
            continue
        expected_parts = tuple(
            str(value or "").strip()
            for value in tuple(getattr(split_hint, "expected_parts", ()) or ())
            if str(value or "").strip()
        )
        if len(expected_parts) < 2:
            continue
        count += 1
    return count


def _projection_has_heading_inside_toc_region(
    projection: object | None,
    *,
    start_logical_index: int,
    end_logical_index: int,
) -> bool:
    projected_units = getattr(projection, "projected_units", None)
    if not projected_units:
        return False
    for unit in tuple(projected_units):
        role = str(getattr(unit, "role", "") or "").strip().lower()
        unit_type = str(getattr(unit, "unit_type", "") or "").strip().lower()
        if role != "heading" and unit_type not in {"chapter_heading", "section_heading"}:
            continue
        logical_indexes = tuple(int(index) for index in tuple(getattr(unit, "logical_indexes", ()) or ()))
        if any(start_logical_index <= logical_index <= end_logical_index for logical_index in logical_indexes):
            return True
    return False


def _projection_has_toc_entry_outside_toc_region(
    projection: object | None,
    *,
    start_logical_index: int,
    end_logical_index: int,
) -> bool:
    projected_units = getattr(projection, "projected_units", None)
    if not projected_units:
        return False
    for unit in tuple(projected_units):
        role = str(getattr(unit, "role", "") or "").strip().lower()
        unit_type = str(getattr(unit, "unit_type", "") or "").strip().lower()
        if role != "toc_entry" and unit_type != "toc_entry":
            continue
        logical_indexes = tuple(int(index) for index in tuple(getattr(unit, "logical_indexes", ()) or ()))
        if any(logical_index < start_logical_index or logical_index > end_logical_index for logical_index in logical_indexes):
            return True
    return False


def _document_map_has_high_confidence_outline_inside_toc_region(
    document_map: object | None,
    *,
    start_logical_index: int,
    end_logical_index: int,
) -> bool:
    outline = getattr(document_map, "outline", None)
    if not outline:
        return False
    for entry in tuple(outline):
        if str(getattr(entry, "confidence", "") or "").strip().lower() != "high":
            continue
        logical_index = int(getattr(entry, "logical_index", -1) or -1)
        if start_logical_index <= logical_index <= end_logical_index:
            return True
    return False


def _projection_has_units_or_operations(projection: object | None) -> bool:
    if projection is None:
        return False
    return bool(getattr(projection, "operations", None) or getattr(projection, "projected_units", None))


def _is_authoritative_topology_signal(*, authority: object, confidence: object) -> bool:
    normalized_authority = str(authority or "").strip().lower()
    normalized_confidence = str(confidence or "").strip().lower()
    return normalized_confidence == "high" and normalized_authority.startswith("document_map")


def _count_authoritative_topology_toc_entry_units(projection: object | None) -> int:
    projected_units = getattr(projection, "projected_units", None)
    if not projected_units:
        return 0
    count = 0
    for unit in tuple(projected_units):
        if not _is_authoritative_topology_signal(
            authority=getattr(unit, "authority", ""),
            confidence=getattr(unit, "confidence", ""),
        ):
            continue
        role = str(getattr(unit, "role", "") or "").strip().lower()
        unit_type = str(getattr(unit, "unit_type", "") or "").strip().lower()
        if role == "toc_entry" or unit_type == "toc_entry":
            count += 1
    return count


def _count_authoritative_topology_operations(projection: object | None, *, op: str) -> int:
    operations = getattr(projection, "operations", None)
    if not operations:
        return 0
    normalized_op = str(op or "").strip().lower()
    count = 0
    for operation in tuple(operations):
        if str(getattr(operation, "op", "") or "").strip().lower() != normalized_op:
            continue
        if not _is_authoritative_topology_signal(
            authority=getattr(operation, "authority", ""),
            confidence=getattr(operation, "confidence", ""),
        ):
            continue
        count += 1
    return count


def has_toc_body_concat_structure(topology_projection: object | None) -> bool:
    projected_units = getattr(topology_projection, "projected_units", None)
    if not projected_units:
        return False
    roles_by_logical_index: dict[int, set[str]] = {}
    for unit in tuple(projected_units):
        if not _is_authoritative_topology_signal(
            authority=getattr(unit, "authority", ""),
            confidence=getattr(unit, "confidence", ""),
        ):
            continue
        role = str(getattr(unit, "role", "") or "").strip().lower()
        unit_type = str(getattr(unit, "unit_type", "") or "").strip().lower()
        normalized_role = ""
        if role == "toc_entry" or unit_type == "toc_entry":
            normalized_role = "toc_entry"
        elif role == "heading" or unit_type in {"chapter_heading", "section_heading"}:
            normalized_role = "heading"
        if not normalized_role:
            continue
        for logical_index in tuple(getattr(unit, "logical_indexes", ()) or ()):
            roles_by_logical_index.setdefault(int(logical_index), set()).add(normalized_role)
    return any({"toc_entry", "heading"}.issubset(roles) for roles in roles_by_logical_index.values())


def _projection_supports_toc_body_concat_gate(
    *,
    document_map: object | None,
    topology_projection: object | None,
) -> bool:
    if _resolve_bounded_toc_region_range(document_map) is None:
        return False
    if not _projection_has_units_or_operations(topology_projection):
        return False
    return bool(
        _count_authoritative_topology_operations(topology_projection, op="split_compound_toc_entries")
        or _count_authoritative_topology_toc_entry_units(topology_projection)
    )


def _derive_toc_body_concat_gate_fields(
    *,
    document_map: object | None,
    topology_projection: object | None,
    markdown_detected: bool,
) -> dict[str, object]:
    split_hint_count = _count_high_confidence_compound_toc_split_hints(document_map)
    split_operation_count = _count_topology_operations(topology_projection, op="split_compound_toc_entries")
    merge_heading_count = _count_topology_operations(topology_projection, op="merge_heading_continuation")
    topology_toc_entry_count = _count_topology_toc_entry_units(topology_projection)
    if not _projection_supports_toc_body_concat_gate(
        document_map=document_map,
        topology_projection=topology_projection,
    ):
        return {
            "toc_body_concat_detected": bool(markdown_detected),
            "toc_body_concat_markdown_detected": bool(markdown_detected),
            "toc_body_concat_structure_detected": False,
            "toc_body_concat_gate_source": "legacy_markdown",
            "topology_split_compound_toc_operation_count": split_operation_count,
            "topology_merge_heading_operation_count": merge_heading_count,
            "document_map_compound_toc_split_hint_count": split_hint_count,
        }
    structure_detected = has_toc_body_concat_structure(topology_projection)
    return {
        "toc_body_concat_detected": structure_detected,
        "toc_body_concat_markdown_detected": bool(markdown_detected),
        "toc_body_concat_structure_detected": structure_detected,
        "toc_body_concat_gate_source": "topology_projection",
        "topology_split_compound_toc_operation_count": split_operation_count,
        "topology_merge_heading_operation_count": merge_heading_count,
        "document_map_compound_toc_split_hint_count": split_hint_count,
    }
