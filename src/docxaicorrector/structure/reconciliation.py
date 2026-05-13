from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import logging
from docxaicorrector.structure._responses_timeout import call_responses_with_hard_timeout
from typing import Any, Sequence, cast

from docxaicorrector.core.constants import PROMPTS_DIR
from docxaicorrector.core.models import DocumentMap, DocumentTopologyProjection, ParagraphClassification, ParagraphDescriptor, ParagraphUnit, StructureMap
from docxaicorrector.generation._generation import normalize_model_output
from docxaicorrector.generation.openai_response_utils import collect_response_text_traversal
from docxaicorrector.structure.recognition import _as_responses_create_client, _parse_classification_payload, _with_request_timeout
from docxaicorrector.structure.recognition import build_paragraph_descriptors


_LOGGER = logging.getLogger(__name__)
STRUCTURE_RECONCILIATION_SCHEMA_VERSION = 7
RECONCILIATION_TARGETED_PROMPT_VERSION = 2
RECONCILIATION_TARGETED_DESCRIPTOR_SCHEMA_VERSION = 1
_FRONT_MATTER_ALLOWED_ROLES = frozenset({"toc_entry", "toc_header", "dedication", "epigraph", "attribution"})
_RECONCILIATION_TARGETED_SYSTEM_PROMPT_PATH = PROMPTS_DIR / "reconciliation_targeted_system.txt"
_OUTLINE_HEADING_MATCH_DISTANCE = 1
_TARGETED_SELECTION_REASONS = frozenset(
    {
        "missing_outline_entry",
        "unexpected_heading",
        "toc_entry_without_body_match",
        "front_matter_leak",
        "anchor_disagreement",
        "review_zone",
        "body_start_neighborhood",
        "toc_boundary_neighborhood",
    }
)
_TARGETED_INVOCATION_REASONS = frozenset({"review_zone", "body_start_neighborhood", "toc_boundary_neighborhood"})
_HIGH_SEVERITY_REVIEW_ZONE_LEVELS = frozenset({"warning", "critical"})
_TARGETED_NEIGHBORHOOD_RADIUS = 2


@dataclass(frozen=True)
class TargetedSelectionReason:
    logical_index: int
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetedSelection:
    logical_indexes: tuple[int, ...] = ()
    reasons: tuple[TargetedSelectionReason, ...] = ()


@dataclass(frozen=True)
class ReconciliationReport:
    missing_outline_entries: tuple[int, ...] = ()
    unexpected_headings: tuple[int, ...] = ()
    toc_entries_without_body_match: tuple[int, ...] = ()
    front_matter_leaks: tuple[int, ...] = ()
    front_matter_body_advisories: tuple[int, ...] = ()
    anchor_disagreements_seen: tuple[int, ...] = ()
    targeted_recall_invoked: bool = False
    targeted_recall_count: int = 0
    targeted_selection_reasons: tuple[TargetedSelectionReason, ...] = ()
    outline_coverage_ratio: float = 1.0
    patched_logical_indexes: tuple[int, ...] = ()

    @property
    def patched_anchor_count(self) -> int:
        return len(self.patched_logical_indexes)

    @property
    def targeted_selected_logical_indexes(self) -> tuple[int, ...]:
        return tuple(selection.logical_index for selection in self.targeted_selection_reasons)

    @property
    def targeted_selection_count(self) -> int:
        return len(self.targeted_selection_reasons)

    @property
    def missing_outline_entry_count(self) -> int:
        return len(self.missing_outline_entries)

    @property
    def unexpected_heading_count(self) -> int:
        return len(self.unexpected_headings)

    @property
    def toc_entry_without_body_match_count(self) -> int:
        return len(self.toc_entries_without_body_match)

    @property
    def front_matter_leak_count(self) -> int:
        return len(self.front_matter_leaks)

    @property
    def front_matter_body_advisory_count(self) -> int:
        return len(self.front_matter_body_advisories)

    @property
    def anchor_disagreement_count(self) -> int:
        return len(self.anchor_disagreements_seen)

    @property
    def actionable_divergence_count(self) -> int:
        return (
            self.missing_outline_entry_count
            + self.unexpected_heading_count
            + self.toc_entry_without_body_match_count
            + self.front_matter_leak_count
            + self.anchor_disagreement_count
        )


@dataclass(frozen=True)
class _ParagraphIndexes:
    logical_to_paragraph: dict[int, ParagraphUnit]


def reconcile_with_document_map(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    structure_map: StructureMap,
    topology_projection: DocumentTopologyProjection | None = None,
) -> tuple[StructureMap, ReconciliationReport]:
    paragraph_indexes = _build_paragraph_indexes(paragraphs)
    patched_classifications = dict(structure_map.classifications)
    patched_logical_indexes: set[int] = set()
    anchor_disagreements_seen = _collect_anchor_conflicts(document_map=document_map, structure_map=structure_map)

    for logical_index, anchor in (document_map.paragraph_anchors or {}).items():
        # Deterministic reconciliation remains intentionally high-confidence only.
        # Medium anchors are advisory Stage 2 inputs and may still trigger
        # targeted recall indirectly through report divergence, but they do not
        # patch the StructureMap by themselves.
        if str(anchor.confidence or "").strip().lower() != "high":
            continue
        paragraph = paragraph_indexes.logical_to_paragraph.get(int(logical_index))
        if paragraph is None:
            continue
        desired_heading_level = anchor.heading_level if anchor.role == "heading" else None
        resolved_logical_index = int(getattr(paragraph, "logical_index", paragraph.source_index))
        existing = patched_classifications.get(resolved_logical_index)
        if existing is not None and existing.role == anchor.role and existing.heading_level == desired_heading_level:
            continue
        patched_classifications[resolved_logical_index] = ParagraphClassification(
            index=resolved_logical_index,
            role=anchor.role,
            heading_level=desired_heading_level,
            confidence="high",
            rationale="document_map_reconciliation",
        )
        patched_logical_indexes.add(resolved_logical_index)

    toc_region = document_map.toc_region
    if toc_region is not None and str(toc_region.confidence or "").strip().lower() == "high":
        toc_header_index = toc_region.header_logical_index
        if toc_header_index is not None:
            _patch_document_map_classification(
                patched_classifications,
                paragraph_indexes=paragraph_indexes,
                patched_logical_indexes=patched_logical_indexes,
                logical_index=int(toc_header_index),
                role="toc_header",
                heading_level=None,
                force=True,
            )
        for logical_index in range(int(toc_region.start_logical_index), int(toc_region.end_logical_index) + 1):
            if logical_index == toc_header_index:
                continue
            _patch_document_map_classification(
                patched_classifications,
                paragraph_indexes=paragraph_indexes,
                patched_logical_indexes=patched_logical_indexes,
                logical_index=logical_index,
                role="toc_entry",
                heading_level=None,
                force=True,
            )

    for outline_entry in document_map.outline or ():
        if str(outline_entry.confidence or "").strip().lower() != "high":
            continue
        _patch_document_map_classification(
            patched_classifications,
            paragraph_indexes=paragraph_indexes,
            patched_logical_indexes=patched_logical_indexes,
            logical_index=int(outline_entry.logical_index),
            role="heading",
            heading_level=int(outline_entry.level),
        )

    reconciled_structure_map = StructureMap(
        classifications=patched_classifications,
        model_used=structure_map.model_used,
        total_tokens_used=structure_map.total_tokens_used,
        processing_time_seconds=structure_map.processing_time_seconds,
        window_count=structure_map.window_count,
        fallback_stats=structure_map.fallback_stats,
    )
    report = _build_reconciliation_report(
        paragraphs=paragraphs,
        document_map=document_map,
        structure_map=reconciled_structure_map,
        topology_projection=topology_projection,
        anchor_disagreements_seen=anchor_disagreements_seen,
        patched_logical_indexes=tuple(sorted(patched_logical_indexes)),
    )
    return reconciled_structure_map, report


def _patch_document_map_classification(
    patched_classifications: dict[int, ParagraphClassification],
    *,
    paragraph_indexes: _ParagraphIndexes,
    patched_logical_indexes: set[int],
    logical_index: int,
    role: str,
    heading_level: int | None,
    force: bool = False,
) -> None:
    paragraph = paragraph_indexes.logical_to_paragraph.get(int(logical_index))
    if paragraph is None:
        return
    resolved_logical_index = int(getattr(paragraph, "logical_index", paragraph.source_index))
    existing = patched_classifications.get(resolved_logical_index)
    if existing is not None:
        if existing.role == role and existing.heading_level == heading_level:
            return
        if (
            not force
            and existing.rationale != "document_map_reconciliation"
            and str(existing.confidence or "").strip().lower() == "high"
        ):
            return
    patched_classifications[resolved_logical_index] = ParagraphClassification(
        index=resolved_logical_index,
        role=role,
        heading_level=heading_level,
        confidence="high",
        rationale="document_map_reconciliation",
    )
    patched_logical_indexes.add(resolved_logical_index)


def _collect_anchor_conflicts(*, document_map: DocumentMap, structure_map: StructureMap) -> tuple[int, ...]:
    conflicts: list[int] = []
    for logical_index, classification in structure_map.classifications.items():
        anchor = document_map.get_anchor(int(logical_index))
        if anchor is None:
            continue
        anchor_confidence = str(anchor.confidence or "").strip().lower()
        if anchor_confidence not in {"high", "medium"}:
            continue
        desired_heading_level = anchor.heading_level if anchor.role == "heading" else None
        if classification.role == anchor.role and classification.heading_level == desired_heading_level:
            continue
        conflicts.append(int(logical_index))
    return tuple(sorted(dict.fromkeys(conflicts)))


def targeted_reclassify_with_reconciliation_context(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    structure_map: StructureMap,
    report: ReconciliationReport,
    *,
    client: object,
    model: str,
    timeout: float,
    max_paragraphs: int = 60,
    selection: TargetedSelection | None = None,
) -> StructureMap:
    selection = selection or _build_targeted_selection(
        paragraphs,
        document_map=document_map,
        report=report,
        max_paragraphs=max_paragraphs,
    )
    selected_paragraphs = _select_targeted_paragraphs(
        paragraphs,
        document_map=document_map,
        report=report,
        max_paragraphs=max_paragraphs,
        selection=selection,
    )
    if not selected_paragraphs or not str(model or "").strip():
        return structure_map

    allowed_logical_indexes = {
        int(getattr(paragraph, "logical_index", paragraph.source_index))
        for paragraph in selected_paragraphs
    }
    descriptors = build_paragraph_descriptors(selected_paragraphs, document_map=document_map)
    targeted_classifications, total_tokens = _request_targeted_classifications(
        descriptors=descriptors,
        report=_with_targeted_selection(report, selection=selection),
        client=client,
        model=model,
        timeout=timeout,
    )
    merged_classifications = dict(structure_map.classifications)
    for classification in targeted_classifications:
        if classification.index not in allowed_logical_indexes:
            _LOGGER.warning(
                "Ignoring out-of-scope targeted reconciliation classification index=%s allowed=%s",
                classification.index,
                sorted(allowed_logical_indexes),
            )
            continue
        merged_classifications[classification.index] = classification
    return StructureMap(
        classifications=merged_classifications,
        model_used=structure_map.model_used,
        total_tokens_used=structure_map.total_tokens_used + total_tokens,
        processing_time_seconds=structure_map.processing_time_seconds,
        window_count=structure_map.window_count,
        fallback_stats=structure_map.fallback_stats,
    )


def _build_paragraph_indexes(paragraphs: Sequence[ParagraphUnit]) -> _ParagraphIndexes:
    return _ParagraphIndexes(
        logical_to_paragraph={
            int(getattr(paragraph, "logical_index", paragraph.source_index)): paragraph
            for paragraph in paragraphs
        },
    )


def _build_reconciliation_report(
    *,
    paragraphs: Sequence[ParagraphUnit],
    document_map: DocumentMap,
    structure_map: StructureMap,
    topology_projection: DocumentTopologyProjection | None = None,
    anchor_disagreements_seen: tuple[int, ...] = (),
    patched_logical_indexes: tuple[int, ...] = (),
    targeted_recall_invoked: bool = False,
    targeted_recall_count: int = 0,
) -> ReconciliationReport:
    paragraph_indexes = _build_paragraph_indexes(paragraphs)
    outline_targets = {entry.logical_index: entry.level for entry in document_map.outline}
    heading_levels_by_logical_index = {
        logical_index: classification.heading_level
        for logical_index, classification in structure_map.classifications.items()
        if classification.role == "heading" and logical_index in paragraph_indexes.logical_to_paragraph
    }

    missing_outline_entries: list[int] = []
    matched_outline_count = 0
    matched_heading_logical_indexes: set[int] = set()
    for logical_index, level in outline_targets.items():
        matched_logical_index = _match_outline_heading_logical_index(
            logical_index,
            level,
            heading_levels_by_logical_index=heading_levels_by_logical_index,
            matched_heading_logical_indexes=matched_heading_logical_indexes,
            topology_projection=topology_projection,
        )
        if matched_logical_index is not None:
            matched_outline_count += 1
            matched_heading_logical_indexes.add(matched_logical_index)
            continue
        missing_outline_entries.append(logical_index)

    heading_logical_indexes = sorted(
        logical_index
        for logical_index, classification in structure_map.classifications.items()
        if classification.role == "heading" and logical_index in paragraph_indexes.logical_to_paragraph
    )
    unexpected_headings = tuple(logical_index for logical_index in heading_logical_indexes if logical_index not in matched_heading_logical_indexes)

    toc_entries_without_body_match: list[int] = []
    toc_region = document_map.toc_region
    if toc_region is not None:
        for entry in toc_region.entries:
            candidate = entry.candidate_body_logical_index
            if candidate is None:
                continue
            if not any(abs(logical_index - candidate) <= 5 for logical_index in heading_logical_indexes):
                toc_entries_without_body_match.append(candidate)

    front_matter_leaks: list[int] = []
    front_matter_body_advisories: list[int] = []
    body_start_logical_index = int(document_map.body_start_logical_index or 0)
    for paragraph in paragraphs:
        logical_index = int(getattr(paragraph, "logical_index", paragraph.source_index))
        if logical_index >= body_start_logical_index:
            continue
        if bool(getattr(paragraph, "is_repeated_across_pages", False)):
            continue
        classification = structure_map.classifications.get(logical_index)
        resolved_role = str(
            (classification.role if classification is not None else getattr(paragraph, "structural_role", "body")) or "body"
        ).strip().lower() or "body"
        if resolved_role == "body":
            anchor = document_map.get_anchor(logical_index)
            if anchor is not None and anchor.role == "body" and str(anchor.confidence or "").strip().lower() in {"medium", "high"}:
                front_matter_body_advisories.append(logical_index)
                continue
        if resolved_role not in _FRONT_MATTER_ALLOWED_ROLES:
            front_matter_leaks.append(logical_index)

    outline_total = len(outline_targets)
    outline_coverage_ratio = 1.0 if outline_total <= 0 else matched_outline_count / outline_total
    return ReconciliationReport(
        missing_outline_entries=tuple(sorted(dict.fromkeys(missing_outline_entries))),
        unexpected_headings=tuple(sorted(dict.fromkeys(unexpected_headings))),
        toc_entries_without_body_match=tuple(sorted(dict.fromkeys(toc_entries_without_body_match))),
        front_matter_leaks=tuple(sorted(dict.fromkeys(front_matter_leaks))),
        front_matter_body_advisories=tuple(sorted(dict.fromkeys(front_matter_body_advisories))),
        anchor_disagreements_seen=tuple(sorted(dict.fromkeys(anchor_disagreements_seen))),
        targeted_recall_invoked=targeted_recall_invoked,
        targeted_recall_count=targeted_recall_count,
        outline_coverage_ratio=outline_coverage_ratio,
        patched_logical_indexes=patched_logical_indexes,
    )


def _match_outline_heading_logical_index(
    logical_index: int,
    level: int,
    *,
    heading_levels_by_logical_index: dict[int, int | None],
    matched_heading_logical_indexes: set[int],
    topology_projection: DocumentTopologyProjection | None = None,
) -> int | None:
    if topology_projection is not None:
        projected_unit = topology_projection.get_unit(logical_index)
        if (
            projected_unit is not None
            and projected_unit.unit_type in {"chapter_heading", "section_heading"}
            and projected_unit.heading_level == level
        ):
            for candidate_logical_index in projected_unit.logical_indexes:
                if candidate_logical_index in matched_heading_logical_indexes:
                    continue
                if heading_levels_by_logical_index.get(candidate_logical_index) == level:
                    return candidate_logical_index
    for distance in range(_OUTLINE_HEADING_MATCH_DISTANCE + 1):
        candidate_indexes = [logical_index] if distance == 0 else [logical_index - distance, logical_index + distance]
        for candidate_logical_index in candidate_indexes:
            if candidate_logical_index in matched_heading_logical_indexes:
                continue
            if heading_levels_by_logical_index.get(candidate_logical_index) == level:
                return candidate_logical_index
    return None


def _select_targeted_paragraphs(
    paragraphs: Sequence[ParagraphUnit],
    *,
    document_map: DocumentMap,
    report: ReconciliationReport,
    max_paragraphs: int,
    selection: TargetedSelection | None = None,
) -> list[ParagraphUnit]:
    selection = selection or _build_targeted_selection(
        paragraphs,
        document_map=document_map,
        report=report,
        max_paragraphs=max_paragraphs,
    )
    limit = max(1, int(max_paragraphs or 0))
    ordered = sorted(paragraphs, key=lambda paragraph: int(getattr(paragraph, "logical_index", paragraph.source_index)))
    by_logical = {
        int(getattr(paragraph, "logical_index", paragraph.source_index)): paragraph
        for paragraph in ordered
    }
    if limit <= 0:
        return []
    return [by_logical[index] for index in selection.logical_indexes if index in by_logical]


def _build_targeted_selection(
    paragraphs: Sequence[ParagraphUnit],
    *,
    document_map: DocumentMap,
    report: ReconciliationReport,
    max_paragraphs: int,
) -> TargetedSelection:
    limit = max(1, int(max_paragraphs or 0))
    ordered = sorted(paragraphs, key=lambda paragraph: int(getattr(paragraph, "logical_index", paragraph.source_index)))
    by_logical = {
        int(getattr(paragraph, "logical_index", paragraph.source_index)): paragraph
        for paragraph in ordered
    }
    selected_reason_map: dict[int, list[str]] = {}

    def _add_candidates(candidates: Sequence[int], *, reason: str) -> None:
        if reason not in _TARGETED_SELECTION_REASONS:
            raise ValueError(f"Unsupported targeted selection reason: {reason}")
        for candidate in candidates:
            if candidate not in by_logical:
                continue
            reasons = selected_reason_map.get(candidate)
            if reasons is not None:
                if reason not in reasons:
                    reasons.append(reason)
                continue
            if len(selected_reason_map) >= limit:
                continue
            selected_reason_map[candidate] = [reason]

    for logical_index in report.missing_outline_entries:
        _add_candidates(_iter_interleaved_neighborhoods((int(logical_index),), radius=_TARGETED_NEIGHBORHOOD_RADIUS), reason="missing_outline_entry")
    for logical_index in report.unexpected_headings:
        _add_candidates(_iter_interleaved_neighborhoods((int(logical_index),), radius=_TARGETED_NEIGHBORHOOD_RADIUS), reason="unexpected_heading")
    for logical_index in report.toc_entries_without_body_match:
        _add_candidates(
            _iter_interleaved_neighborhoods((int(logical_index),), radius=_TARGETED_NEIGHBORHOOD_RADIUS),
            reason="toc_entry_without_body_match",
        )
    for logical_index in report.front_matter_leaks:
        _add_candidates(_iter_interleaved_neighborhoods((int(logical_index),), radius=_TARGETED_NEIGHBORHOOD_RADIUS), reason="front_matter_leak")
    for logical_index in report.anchor_disagreements_seen:
        _add_candidates(_iter_interleaved_neighborhoods((int(logical_index),), radius=_TARGETED_NEIGHBORHOOD_RADIUS), reason="anchor_disagreement")

    for review_zone in document_map.review_zones or ():
        severity = str(getattr(review_zone, "severity", "") or "").strip().lower()
        if severity not in _HIGH_SEVERITY_REVIEW_ZONE_LEVELS:
            continue
        _add_candidates(
            _iter_interleaved_neighborhoods(
                (int(review_zone.start_logical_index), int(review_zone.end_logical_index)),
                radius=_TARGETED_NEIGHBORHOOD_RADIUS,
            ),
            reason="review_zone",
        )

    _add_candidates(
        _iter_interleaved_neighborhoods((int(document_map.body_start_logical_index or 0),), radius=_TARGETED_NEIGHBORHOOD_RADIUS),
        reason="body_start_neighborhood",
    )

    toc_region = document_map.toc_region
    if toc_region is not None:
        _add_candidates(
            _iter_interleaved_neighborhoods(
                (int(toc_region.start_logical_index), int(toc_region.end_logical_index)),
                radius=_TARGETED_NEIGHBORHOOD_RADIUS,
            ),
            reason="toc_boundary_neighborhood",
        )

    logical_indexes = tuple(sorted(selected_reason_map))
    return TargetedSelection(
        logical_indexes=logical_indexes,
        reasons=tuple(
            TargetedSelectionReason(logical_index=index, reasons=tuple(selected_reason_map[index]))
            for index in logical_indexes
        ),
    )


def _iter_interleaved_neighborhoods(centers: Sequence[int], *, radius: int) -> tuple[int, ...]:
    unique_centers = tuple(dict.fromkeys(int(center) for center in centers))
    candidates: list[int] = []
    for offset in range(0, radius + 1):
        for center in unique_centers:
            if offset == 0:
                candidates.append(center)
                continue
            candidates.append(center - offset)
            candidates.append(center + offset)
    return tuple(candidates)


def _with_targeted_selection(report: ReconciliationReport, *, selection: TargetedSelection) -> ReconciliationReport:
    return ReconciliationReport(
        missing_outline_entries=report.missing_outline_entries,
        unexpected_headings=report.unexpected_headings,
        toc_entries_without_body_match=report.toc_entries_without_body_match,
        front_matter_leaks=report.front_matter_leaks,
        front_matter_body_advisories=report.front_matter_body_advisories,
        anchor_disagreements_seen=report.anchor_disagreements_seen,
        targeted_recall_invoked=report.targeted_recall_invoked,
        targeted_recall_count=report.targeted_recall_count,
        targeted_selection_reasons=selection.reasons,
        outline_coverage_ratio=report.outline_coverage_ratio,
        patched_logical_indexes=report.patched_logical_indexes,
    )


def selection_has_authority_uncertainty_context(selection: TargetedSelection) -> bool:
    return any(
        reason in _TARGETED_INVOCATION_REASONS
        for selection_reason in selection.reasons
        for reason in selection_reason.reasons
    )


def _request_targeted_classifications(
    *,
    descriptors: Sequence[ParagraphDescriptor],
    report: ReconciliationReport,
    client: object,
    model: str,
    timeout: float,
) -> tuple[list[ParagraphClassification], int]:
    timeout_scoped_client = _with_request_timeout(client, timeout=timeout)
    responses_client = _as_responses_create_client(timeout_scoped_client)
    if responses_client is None:
        raise RuntimeError("Unsupported structure reconciliation client")

    response = _call_targeted_responses_with_timeout(
        client=responses_client,
        request_payload={
            "model": model.split(":", 1)[1] if ":" in model else model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": _load_targeted_system_prompt()}]},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_targeted_user_prompt(
                                descriptors=[descriptor.to_prompt_dict() for descriptor in descriptors],
                                report=report,
                            ),
                        }
                    ],
                },
            ],
            "timeout": timeout,
        },
        timeout=timeout,
    )
    traversal = collect_response_text_traversal(
        response,
        unsupported_message="Targeted reconciliation response used an unsupported text shape.",
    )
    content = normalize_model_output("\n".join(traversal.collected_texts) if traversal.collected_texts else (traversal.raw_output_text or ""))
    usage = getattr(response, "usage", None)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    return _parse_classification_payload(content), total_tokens


def _call_targeted_responses_with_timeout(*, client: object, request_payload: dict[str, object], timeout: float) -> Any:
    return call_responses_with_hard_timeout(
        client=client,
        request_payload=request_payload,
        timeout=timeout,
        thread_name="reconciliation-targeted-request",
        logger=_LOGGER,
        request_kind="reconciliation_targeted_request",
        timeout_error_factory=lambda seconds: TimeoutError(
            f"Targeted reconciliation request timed out after {seconds:.3f}s."
        ),
    )


@lru_cache(maxsize=1)
def _load_targeted_system_prompt() -> str:
    return _RECONCILIATION_TARGETED_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_targeted_user_prompt(*, descriptors: Sequence[dict[str, object]], report: ReconciliationReport) -> str:
    return (
        "Repair only the flagged paragraph subset. Metadata format:\n"
        '{"i": index, "t": "text preview", "len": full_length, '
        '"s": "DOCX style", "b": bold, "ctr": centered, "caps": all_caps, '
        '"pt": font_size, "num": has_numbering, "hl": explicit_heading_level_or_null, '
        '"prev": "previous paragraph preview", "next": "next paragraph preview", '
        '"iso": isolated_marker, "toc": toc_candidate, "scr": scripture_reference_candidate, '
        '"anchor_r": optional_document_map_role, "anchor_l": optional_document_map_heading_level, '
        '"anchor_c": optional_document_map_confidence}\n\n'
        "`targeted_selection_reasons` lists why each selected logical index is in scope.\n\n"
        "Reconciliation report:\n"
        f"{json.dumps(_report_payload(report), ensure_ascii=False)}\n\n"
        "Paragraphs:\n"
        f"{json.dumps(list(descriptors), ensure_ascii=False)}"
    )


def _report_payload(report: ReconciliationReport) -> dict[str, object]:
    return {
        "missing_outline_entries": list(report.missing_outline_entries),
        "unexpected_headings": list(report.unexpected_headings),
        "toc_entries_without_body_match": list(report.toc_entries_without_body_match),
        "front_matter_leaks": list(report.front_matter_leaks),
        "front_matter_body_advisories": list(report.front_matter_body_advisories),
        "anchor_disagreements_seen": list(report.anchor_disagreements_seen),
        "targeted_selected_logical_indexes": list(report.targeted_selected_logical_indexes),
        "targeted_selection_reasons": [
            {
                "logical_index": selection.logical_index,
                "reasons": list(selection.reasons),
            }
            for selection in report.targeted_selection_reasons
        ],
        "outline_coverage_ratio": report.outline_coverage_ratio,
        "patched_logical_indexes": list(report.patched_logical_indexes),
    }
