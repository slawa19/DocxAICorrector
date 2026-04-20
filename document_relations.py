import hashlib
import json
import re
from pathlib import Path

from runtime_artifact_retention import prune_artifact_dir
from models import (
    RELATION_NORMALIZATION_KIND_VALUES,
    ParagraphRelation,
    ParagraphRelationDecision,
    ParagraphUnit,
    RelationNormalizationReport,
)


TOC_ENTRY_PATTERN = re.compile(r"^.{1,120}(?:\.{2,}|\s{2,})\d+\s*$")


def resolve_effective_relation_kinds() -> tuple[str, ...]:
    enabled, _, enabled_relation_kinds, _ = _resolve_relation_normalization_settings()
    if not enabled:
        return ()
    return enabled_relation_kinds


def build_paragraph_relations(
    paragraphs: list[ParagraphUnit],
    *,
    enabled_relation_kinds: tuple[str, ...] | list[str] | set[str] | None = None,
) -> tuple[list[ParagraphRelation], RelationNormalizationReport]:
    relations: list[ParagraphRelation] = []
    decisions: list[ParagraphRelationDecision] = []
    relation_counts: dict[str, int] = {}
    rejected_candidate_count = 0
    next_relation_id = 1
    enabled_kinds = set(enabled_relation_kinds or RELATION_NORMALIZATION_KIND_VALUES)

    def append_relation(
        *,
        relation_kind: str,
        member_paragraph_ids: tuple[str, ...],
        anchor_asset_id: str | None = None,
        rationale: tuple[str, ...] = (),
    ) -> None:
        nonlocal next_relation_id
        relation_id = f"rel_{next_relation_id:04d}"
        next_relation_id += 1
        relations.append(
            ParagraphRelation(
                relation_id=relation_id,
                relation_kind=relation_kind,
                member_paragraph_ids=member_paragraph_ids,
                anchor_asset_id=anchor_asset_id,
                confidence="high",
                rationale=rationale,
            )
        )
        relation_counts[relation_kind] = relation_counts.get(relation_kind, 0) + 1
        decisions.append(
            ParagraphRelationDecision(
                relation_kind=relation_kind,
                decision="accept",
                member_paragraph_ids=member_paragraph_ids,
                anchor_asset_id=anchor_asset_id,
                reasons=rationale,
            )
        )

    def append_rejection(
        *,
        relation_kind: str,
        member_paragraph_ids: tuple[str, ...],
        reasons: tuple[str, ...],
        anchor_asset_id: str | None = None,
    ) -> None:
        nonlocal rejected_candidate_count
        rejected_candidate_count += 1
        decisions.append(
            ParagraphRelationDecision(
                relation_kind=relation_kind,
                decision="reject",
                member_paragraph_ids=member_paragraph_ids,
                anchor_asset_id=anchor_asset_id,
                reasons=reasons,
            )
        )

    for index, paragraph in enumerate(paragraphs):
        paragraph_role = getattr(paragraph, "role", None)
        paragraph_id = getattr(paragraph, "paragraph_id", None)
        is_caption_candidate = paragraph_role == "caption"
        if not is_caption_candidate and index > 0:
            previous_paragraph = paragraphs[index - 1]
            if previous_paragraph.role in {"image", "table"} and _is_likely_caption_candidate_for_relation(paragraph):
                is_caption_candidate = True
        if not is_caption_candidate:
            continue
        if index == 0:
            append_rejection(
                relation_kind="caption_attachment",
                member_paragraph_ids=((paragraph_id or f"p{index:04d}"),),
                reasons=("caption_without_preceding_asset",),
            )
            continue
        previous_paragraph = paragraphs[index - 1]
        previous_role = getattr(previous_paragraph, "role", None)
        previous_paragraph_id = getattr(previous_paragraph, "paragraph_id", None)
        relation_kind = f"{previous_role}_caption" if previous_role in {"image", "table"} else "caption_attachment"
        if previous_role not in {"image", "table"}:
            append_rejection(
                relation_kind="caption_attachment",
                member_paragraph_ids=((paragraph_id or f"p{index:04d}"),),
                reasons=("caption_not_adjacent_to_asset",),
            )
            continue
        if relation_kind not in enabled_kinds:
            continue
        if not previous_paragraph_id or not paragraph_id or getattr(previous_paragraph, "asset_id", None) is None:
            append_rejection(
                relation_kind=relation_kind,
                member_paragraph_ids=tuple(
                    paragraph_key
                    for paragraph_key in (previous_paragraph_id, paragraph_id)
                    if paragraph_key
                ) or ((paragraph_id or f"p{index:04d}"),),
                reasons=("missing_caption_anchor_identity",),
                anchor_asset_id=getattr(previous_paragraph, "asset_id", None),
            )
            continue
        append_relation(
            relation_kind=relation_kind,
            member_paragraph_ids=(previous_paragraph_id, paragraph_id),
            anchor_asset_id=getattr(previous_paragraph, "asset_id", None),
            rationale=("adjacent_asset_caption",),
        )

    if "epigraph_attribution" in enabled_kinds:
        for index in range(len(paragraphs) - 1):
            left = paragraphs[index]
            right = paragraphs[index + 1]
            left_paragraph_id = getattr(left, "paragraph_id", None)
            right_paragraph_id = getattr(right, "paragraph_id", None)
            if not left_paragraph_id or not right_paragraph_id:
                continue
            if not _is_epigraph_relation_candidate(left, right):
                rejection_reasons = _epigraph_relation_rejection_reasons(left, right)
                if rejection_reasons:
                    append_rejection(
                        relation_kind="epigraph_attribution",
                        member_paragraph_ids=(left_paragraph_id, right_paragraph_id),
                        reasons=rejection_reasons,
                    )
                continue
            append_relation(
                relation_kind="epigraph_attribution",
                member_paragraph_ids=(left_paragraph_id, right_paragraph_id),
                rationale=("adjacent_epigraph_attribution",),
            )

    index = 0
    while index < len(paragraphs):
        paragraph = paragraphs[index]
        if _is_toc_header_paragraph(paragraph):
            member_indexes = [index]
            look_ahead = index + 1
            while look_ahead < len(paragraphs) and _is_toc_entry_paragraph(paragraphs[look_ahead]):
                member_indexes.append(look_ahead)
                look_ahead += 1
            if len(member_indexes) >= 2:
                if "toc_region" in enabled_kinds:
                    append_relation(
                        relation_kind="toc_region",
                        member_paragraph_ids=tuple(
                            paragraphs[member_index].paragraph_id or f"p{member_index:04d}" for member_index in member_indexes
                        ),
                        rationale=("toc_header_with_entries",),
                    )
                index = look_ahead
                continue
            append_rejection(
                relation_kind="toc_region",
                member_paragraph_ids=((paragraph.paragraph_id or f"p{index:04d}"),),
                reasons=("toc_header_without_entries",),
            )

        if _is_toc_entry_paragraph(paragraph):
            member_indexes = [index]
            look_ahead = index + 1
            while look_ahead < len(paragraphs) and _is_toc_entry_paragraph(paragraphs[look_ahead]):
                member_indexes.append(look_ahead)
                look_ahead += 1
            if len(member_indexes) >= 2:
                if "toc_region" in enabled_kinds:
                    append_relation(
                        relation_kind="toc_region",
                        member_paragraph_ids=tuple(
                            paragraphs[member_index].paragraph_id or f"p{member_index:04d}" for member_index in member_indexes
                        ),
                        rationale=("contiguous_toc_entries",),
                    )
                index = look_ahead
                continue
            append_rejection(
                relation_kind="toc_region",
                member_paragraph_ids=((paragraph.paragraph_id or f"p{index:04d}"),),
                reasons=("isolated_toc_entry",),
            )
        index += 1

    report = RelationNormalizationReport(
        total_relations=len(relations),
        relation_counts=relation_counts,
        rejected_candidate_count=rejected_candidate_count,
        decisions=decisions,
    )
    return relations, report


def apply_relation_side_effects(paragraphs: list[ParagraphUnit], relations: list[ParagraphRelation]) -> None:
    paragraph_by_id = {paragraph.paragraph_id: paragraph for paragraph in paragraphs if paragraph.paragraph_id}
    for paragraph in paragraphs:
        if paragraph.role == "caption":
            paragraph.attached_to_asset_id = None

    for relation in relations:
        if relation.relation_kind not in {"image_caption", "table_caption"}:
            continue
        if len(relation.member_paragraph_ids) < 2:
            continue
        caption_paragraph = paragraph_by_id.get(relation.member_paragraph_ids[-1])
        if caption_paragraph is not None:
            caption_paragraph.attached_to_asset_id = relation.anchor_asset_id


def write_relation_normalization_report_artifact(
    *,
    source_name: str,
    source_bytes: bytes,
    profile: str,
    enabled_relation_kinds: tuple[str, ...],
    report: RelationNormalizationReport,
    target_dir: Path,
    max_age_seconds: int,
    max_count: int,
) -> str | None:
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        source_hash = hashlib.sha1(source_bytes).hexdigest()[:8]
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source_name or "document.docx").strip("_") or "document.docx"
        artifact_path = target_dir / f"{safe_name}_{source_hash}.json"
        payload = {
            "version": 1,
            "source_file": source_name,
            "source_hash": source_hash,
            "profile": profile,
            "enabled_relation_kinds": list(enabled_relation_kinds),
            "total_relations": report.total_relations,
            "relation_counts": dict(report.relation_counts),
            "rejected_candidate_count": report.rejected_candidate_count,
            "decisions": [
                {
                    "relation_kind": decision.relation_kind,
                    "decision": decision.decision,
                    "member_paragraph_ids": list(decision.member_paragraph_ids),
                    "anchor_asset_id": decision.anchor_asset_id,
                    "reasons": list(decision.reasons),
                }
                for decision in report.decisions
            ],
        }
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_artifact_dir(
            target_dir=target_dir,
            max_age_seconds=max_age_seconds,
            max_count=max_count,
        )
        return str(artifact_path)
    except Exception:
        return None


def _is_likely_caption_candidate_for_relation(paragraph: ParagraphUnit) -> bool:
    if paragraph.role == "heading" and paragraph.heading_source != "heuristic":
        return False
    return _is_likely_caption_text(paragraph.text)


def _is_epigraph_relation_candidate(left: ParagraphUnit, right: ParagraphUnit) -> bool:
    left_role = getattr(left, "role", None)
    right_role = getattr(right, "role", None)
    if left_role in {"image", "table", "caption", "list"} or right_role in {"image", "table", "caption", "list"}:
        return False
    left_structural = _paragraph_structural_kind(left)
    right_structural = _paragraph_structural_kind(right)
    if left_structural == "epigraph" and right_structural == "attribution":
        return True
    if left_structural == "epigraph" and _is_likely_attribution_text(str(getattr(right, "text", ""))):
        return True
    if right_structural == "attribution" and getattr(left, "paragraph_alignment", None) == "center":
        return True
    return False


def _epigraph_relation_rejection_reasons(left: ParagraphUnit, right: ParagraphUnit) -> tuple[str, ...]:
    left_role = getattr(left, "role", None)
    right_role = getattr(right, "role", None)
    left_structural = _paragraph_structural_kind(left)
    right_structural = _paragraph_structural_kind(right)
    right_text = str(getattr(right, "text", ""))
    reasons: list[str] = []

    if left_structural == "epigraph" and right_structural != "attribution":
        reasons.append("epigraph_without_attribution")
    elif right_structural == "attribution" and left_structural != "epigraph":
        reasons.append("attribution_without_epigraph")
    elif left_structural == "epigraph" and _is_likely_attribution_text(right_text):
        reasons.append("epigraph_candidate_rejected")
    elif right_structural == "attribution" and getattr(left, "paragraph_alignment", None) != "center":
        reasons.append("attribution_alignment_mismatch")

    return tuple(reasons)


def _is_toc_header_paragraph(paragraph: ParagraphUnit) -> bool:
    return _paragraph_structural_kind(paragraph) == "toc_header" or str(getattr(paragraph, "text", "")).strip().lower() in {
        "содержание",
        "contents",
    }


def _is_toc_entry_paragraph(paragraph: ParagraphUnit) -> bool:
    if _paragraph_structural_kind(paragraph) == "toc_entry":
        return True
    return _is_likely_toc_entry_text(str(getattr(paragraph, "text", "")))


def _paragraph_structural_kind(paragraph: ParagraphUnit) -> str:
    return str(getattr(paragraph, "structural_role", None) or getattr(paragraph, "role", None) or "").strip().lower()


def _is_likely_attribution_text(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and len(stripped) <= 120 and stripped.startswith(("-", "—", "–"))


def _is_likely_toc_entry_text(text: str) -> bool:
    return TOC_ENTRY_PATTERN.match(text.strip()) is not None


def _is_likely_caption_text(text: str) -> bool:
    from document_roles import is_likely_caption_text

    return is_likely_caption_text(text)


def _resolve_relation_normalization_settings() -> tuple[bool, str, tuple[str, ...], bool]:
    from config import load_app_config

    app_config = load_app_config()
    enabled = bool(app_config.get("relation_normalization_enabled", True))
    profile = str(app_config.get("relation_normalization_profile", "phase2_default") or "phase2_default")
    configured_relation_kinds = app_config.get(
        "relation_normalization_enabled_relation_kinds",
        RELATION_NORMALIZATION_KIND_VALUES,
    )
    if not isinstance(configured_relation_kinds, (list, tuple, set)):
        configured_relation_kinds = RELATION_NORMALIZATION_KIND_VALUES
    enabled_relation_kinds = tuple(
        kind
        for kind in configured_relation_kinds
        if kind in RELATION_NORMALIZATION_KIND_VALUES
    )
    if not enabled:
        enabled_relation_kinds = ()
    return (
        enabled,
        profile,
        enabled_relation_kinds,
        bool(app_config.get("relation_normalization_save_debug_artifacts", True)),
    )
