from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import logging
from docxaicorrector.structure._responses_timeout import call_responses_with_hard_timeout
from typing import Any, Sequence, cast

from docxaicorrector.core.constants import PROMPTS_DIR
from docxaicorrector.core.models import DocumentMap, ParagraphClassification, ParagraphDescriptor, ParagraphUnit, StructureMap
from docxaicorrector.generation._generation import normalize_model_output
from docxaicorrector.generation.openai_response_utils import collect_response_text_traversal
from docxaicorrector.structure.recognition import _as_responses_create_client, _parse_classification_payload, _with_request_timeout
from docxaicorrector.structure.recognition import build_paragraph_descriptors


_LOGGER = logging.getLogger(__name__)
STRUCTURE_RECONCILIATION_SCHEMA_VERSION = 5
RECONCILIATION_TARGETED_PROMPT_VERSION = 1
RECONCILIATION_TARGETED_DESCRIPTOR_SCHEMA_VERSION = 1
_FRONT_MATTER_ALLOWED_ROLES = frozenset({"toc_entry", "toc_header", "dedication", "epigraph", "attribution"})
_RECONCILIATION_TARGETED_SYSTEM_PROMPT_PATH = PROMPTS_DIR / "reconciliation_targeted_system.txt"
_OUTLINE_HEADING_MATCH_DISTANCE = 1


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
    outline_coverage_ratio: float = 1.0
    patched_logical_indexes: tuple[int, ...] = ()

    @property
    def patched_anchor_count(self) -> int:
        return len(self.patched_logical_indexes)

    @property
    def patched_source_indexes(self) -> tuple[int, ...]:
        # Compatibility alias: reconciliation uses logical indexes end-to-end.
        return self.patched_logical_indexes

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
    def anchor_conflict_count(self) -> int:
        return len(self.anchor_disagreements_seen)

    @property
    def anchor_conflicts(self) -> tuple[int, ...]:
        # Compatibility alias: the semantics are pre-patch disagreements seen
        # before deterministic reconciliation applies high-confidence anchors.
        return self.anchor_disagreements_seen

    @property
    def actionable_divergence_count(self) -> int:
        return (
            self.missing_outline_entry_count
            + self.unexpected_heading_count
            + self.toc_entry_without_body_match_count
            + self.front_matter_leak_count
            + self.anchor_conflict_count
        )


@dataclass(frozen=True)
class _ParagraphIndexes:
    logical_to_paragraph: dict[int, ParagraphUnit]


def reconcile_with_document_map(
    paragraphs: list[ParagraphUnit],
    document_map: DocumentMap,
    structure_map: StructureMap,
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

    reconciled_structure_map = StructureMap(
        classifications=patched_classifications,
        model_used=structure_map.model_used,
        total_tokens_used=structure_map.total_tokens_used,
        processing_time_seconds=structure_map.processing_time_seconds,
        window_count=structure_map.window_count,
    )
    report = _build_reconciliation_report(
        paragraphs=paragraphs,
        document_map=document_map,
        structure_map=reconciled_structure_map,
        anchor_disagreements_seen=anchor_disagreements_seen,
        patched_logical_indexes=tuple(sorted(patched_logical_indexes)),
    )
    return reconciled_structure_map, report


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
) -> StructureMap:
    selected_paragraphs = _select_targeted_paragraphs(
        paragraphs,
        report=report,
        max_paragraphs=max_paragraphs,
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
        report=report,
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
) -> int | None:
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
    report: ReconciliationReport,
    max_paragraphs: int,
) -> list[ParagraphUnit]:
    limit = max(1, int(max_paragraphs or 0))
    ordered = sorted(paragraphs, key=lambda paragraph: int(getattr(paragraph, "logical_index", paragraph.source_index)))
    by_logical = {
        int(getattr(paragraph, "logical_index", paragraph.source_index)): paragraph
        for paragraph in ordered
    }
    flagged_logical_indexes = tuple(
        sorted(
            dict.fromkeys(
                [
                    *report.missing_outline_entries,
                    *report.unexpected_headings,
                    *report.toc_entries_without_body_match,
                    *report.front_matter_leaks,
                    *report.anchor_disagreements_seen,
                ]
            )
        )
    )
    selected_logical_indexes: list[int] = []
    for logical_index in flagged_logical_indexes:
        for candidate in range(logical_index - 2, logical_index + 3):
            if candidate not in by_logical:
                continue
            if candidate in selected_logical_indexes:
                continue
            selected_logical_indexes.append(candidate)
            if len(selected_logical_indexes) >= limit:
                return [by_logical[index] for index in sorted(selected_logical_indexes)]
    return [by_logical[index] for index in sorted(selected_logical_indexes)]


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
            "model": model,
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
        "Reconciliation report:\n"
        f"{json.dumps(_report_payload(report), ensure_ascii=False)}\n\n"
        "Paragraphs:\n"
        f"{json.dumps(list(descriptors), ensure_ascii=False)}"
    )


def _report_payload(report: ReconciliationReport) -> dict[str, object]:
    # Compatibility policy: keep `anchor_conflicts` for one more cleanup pass
    # and remove it on the next reconciliation schema bump after downstream
    # readers/docs/tests have been updated to consume only
    # `anchor_disagreements_seen`.
    return {
        "missing_outline_entries": list(report.missing_outline_entries),
        "unexpected_headings": list(report.unexpected_headings),
        "toc_entries_without_body_match": list(report.toc_entries_without_body_match),
        "front_matter_leaks": list(report.front_matter_leaks),
        "front_matter_body_advisories": list(report.front_matter_body_advisories),
        "anchor_disagreements_seen": list(report.anchor_disagreements_seen),
        "anchor_conflicts": list(report.anchor_conflicts),
        "anchor_conflicts_deprecated": True,
        "anchor_conflicts_alias_of": "anchor_disagreements_seen",
        "outline_coverage_ratio": report.outline_coverage_ratio,
    }