import hashlib
import json
import re
from pathlib import Path
from typing import cast

from document_roles import HEADING_STYLE_PATTERN, is_caption_style, is_likely_caption_text
from models import ParagraphBoundaryDecision, ParagraphBoundaryNormalizationReport, RawBlock, RawParagraph
from runtime_artifact_retention import prune_artifact_dir


STRONG_PARAGRAPH_TERMINATOR_PATTERN = re.compile(r"[.!?…]\s*$")
TOC_ENTRY_PATTERN = re.compile(r"^.{1,120}(?:\.{2,}|\s{2,})\d+\s*$")


def resolve_paragraph_boundary_normalization_settings(
    *,
    allowed_modes: tuple[str, ...] | list[str] | set[str],
) -> tuple[str, bool]:
    from config import load_app_config

    app_config = load_app_config()
    enabled = bool(app_config.get("paragraph_boundary_normalization_enabled", True))
    mode = str(app_config.get("paragraph_boundary_normalization_mode", "high_only"))
    if mode not in allowed_modes:
        mode = "high_only"
    if not enabled:
        mode = "off"
    return mode, bool(app_config.get("paragraph_boundary_normalization_save_debug_artifacts", True))


def summarize_boundary_normalization_metrics(
    report: ParagraphBoundaryNormalizationReport | None,
) -> dict[str, int]:
    if report is None:
        return {}
    high_confidence_merge_count = 0
    medium_accepted_merge_count = 0
    medium_rejected_candidate_count = 0
    decisions = getattr(report, "decisions", ()) or ()
    for decision in decisions:
        if decision.decision == "merge" and decision.confidence == "high":
            high_confidence_merge_count += 1
        elif decision.decision == "merge" and decision.confidence == "medium":
            medium_accepted_merge_count += 1
        elif decision.decision == "keep" and decision.confidence == "medium":
            medium_rejected_candidate_count += 1
    return {
        "high_confidence_merge_count": high_confidence_merge_count,
        "medium_accepted_merge_count": medium_accepted_merge_count,
        "medium_rejected_candidate_count": medium_rejected_candidate_count,
    }


def normalize_paragraph_boundaries(
    raw_blocks: list[RawBlock],
    *,
    mode: str,
    detect_explicit_list_kind,
    has_heading_text_signal,
) -> tuple[list[RawBlock], ParagraphBoundaryNormalizationReport]:
    total_raw_paragraphs = sum(1 for block in raw_blocks if isinstance(block, RawParagraph))
    if mode == "off":
        report = ParagraphBoundaryNormalizationReport(
            total_raw_paragraphs=total_raw_paragraphs,
            total_logical_paragraphs=total_raw_paragraphs,
            merged_group_count=0,
            merged_raw_paragraph_count=0,
            decisions=[],
        )
        return list(raw_blocks), report

    normalized_blocks: list[RawBlock] = []
    decisions: list[ParagraphBoundaryDecision] = []
    merged_group_count = 0
    merged_raw_paragraph_count = 0
    index = 0

    while index < len(raw_blocks):
        block = raw_blocks[index]
        if not isinstance(block, RawParagraph):
            normalized_blocks.append(block)
            index += 1
            continue

        group = [block]
        group_reasons: list[str] = []
        group_confidences: list[str] = []
        look_ahead = index
        while look_ahead + 1 < len(raw_blocks) and isinstance(raw_blocks[look_ahead + 1], RawParagraph):
            next_block = cast(RawParagraph, raw_blocks[look_ahead + 1])
            decision = evaluate_paragraph_boundary(
                group[-1],
                next_block,
                detect_explicit_list_kind=detect_explicit_list_kind,
                has_heading_text_signal=has_heading_text_signal,
            )
            effective_decision = decision
            if decision.decision == "merge" and decision.confidence == "medium" and mode != "high_and_medium":
                effective_decision = ParagraphBoundaryDecision(
                    left_raw_index=decision.left_raw_index,
                    right_raw_index=decision.right_raw_index,
                    decision="keep",
                    confidence="medium",
                    reasons=tuple((*decision.reasons, "medium_mode_disabled")),
                )
            decisions.append(effective_decision)
            if effective_decision.decision != "merge":
                break
            group.append(next_block)
            group_reasons.extend(effective_decision.reasons)
            group_confidences.append(effective_decision.confidence)
            look_ahead += 1

        if len(group) == 1:
            normalized_blocks.append(block)
            index += 1
            continue

        merged_group_count += 1
        merged_raw_paragraph_count += len(group)
        normalized_blocks.append(merge_raw_paragraph_group(group, group_reasons, group_confidences))
        index += len(group)

    report = ParagraphBoundaryNormalizationReport(
        total_raw_paragraphs=total_raw_paragraphs,
        total_logical_paragraphs=sum(1 for block in normalized_blocks if isinstance(block, RawParagraph)),
        merged_group_count=merged_group_count,
        merged_raw_paragraph_count=merged_raw_paragraph_count,
        decisions=decisions,
    )
    return normalized_blocks, report


def evaluate_paragraph_boundary(
    left: RawParagraph,
    right: RawParagraph,
    *,
    detect_explicit_list_kind,
    has_heading_text_signal,
) -> ParagraphBoundaryDecision:
    blocked_reasons: list[str] = []
    positive_reasons: list[str] = []

    if left.heading_level is not None or right.heading_level is not None:
        blocked_reasons.append("heading_boundary")
    if left.role_hint != "body" or right.role_hint != "body":
        blocked_reasons.append("non_body_role")
    if left.list_kind is not None or right.list_kind is not None:
        blocked_reasons.append("list_metadata")
    if detect_explicit_list_kind(right.text) is not None:
        blocked_reasons.append("right_explicit_list_marker")
    if is_likely_caption_text(left.text) or is_likely_caption_text(right.text):
        blocked_reasons.append("caption_like_boundary")
    if is_likely_attribution_text(right.text):
        blocked_reasons.append("right_attribution_like")
    if is_likely_toc_entry_text(right.text):
        blocked_reasons.append("right_toc_like")
    if style_transition_implies_structure(left, right):
        blocked_reasons.append("style_transition")
    if alignment_transition_implies_structure(left, right):
        blocked_reasons.append("alignment_transition")
    if ends_with_strong_paragraph_terminator(left.text) and starts_with_new_sentence_signal(
        right.text,
        has_heading_text_signal=has_heading_text_signal,
    ):
        blocked_reasons.append("terminal_punctuation_sentence_reset")

    if blocked_reasons:
        return ParagraphBoundaryDecision(
            left_raw_index=left.raw_index,
            right_raw_index=right.raw_index,
            decision="keep",
            confidence="blocked",
            reasons=tuple(blocked_reasons),
        )

    if styles_are_compatible(left, right):
        positive_reasons.append("same_body_style")
    if alignments_are_compatible(left, right):
        positive_reasons.append("compatible_alignment")
    if not ends_with_strong_paragraph_terminator(left.text):
        positive_reasons.append("left_not_terminal")
    if starts_with_continuation_signal(right.text):
        positive_reasons.append("right_starts_continuation")
    if left_paragraph_looks_incomplete(left.text):
        positive_reasons.append("left_incomplete")
    if combined_text_reads_as_continuation(left.text, right.text):
        positive_reasons.append("combined_sentence_plausible")

    if {"same_body_style", "left_not_terminal", "right_starts_continuation"}.issubset(set(positive_reasons)):
        return ParagraphBoundaryDecision(
            left_raw_index=left.raw_index,
            right_raw_index=right.raw_index,
            decision="merge",
            confidence="high",
            reasons=tuple(positive_reasons),
        )

    if should_promote_medium_merge(positive_reasons):
        return ParagraphBoundaryDecision(
            left_raw_index=left.raw_index,
            right_raw_index=right.raw_index,
            decision="merge",
            confidence="medium",
            reasons=tuple(positive_reasons),
        )

    return ParagraphBoundaryDecision(
        left_raw_index=left.raw_index,
        right_raw_index=right.raw_index,
        decision="keep",
        confidence="medium",
        reasons=tuple(positive_reasons or ("insufficient_merge_signals",)),
    )


def merge_raw_paragraph_group(group: list[RawParagraph], reasons: list[str], confidences: list[str]) -> RawParagraph:
    dominant = group[0]
    merged_text = join_merged_paragraph_text(group)
    merged_indexes = tuple(index for paragraph in group for index in paragraph.origin_raw_indexes)
    merged_texts = tuple(text for paragraph in group for text in paragraph.origin_raw_texts)
    rationale = ", ".join(dict.fromkeys(reasons)) or None
    boundary_confidence = "medium" if "medium" in confidences else "high"
    return RawParagraph(
        raw_index=dominant.raw_index,
        text=merged_text,
        style_name=dominant.style_name,
        paragraph_alignment=dominant.paragraph_alignment,
        is_bold=dominant.is_bold,
        is_italic=dominant.is_italic,
        font_size_pt=dominant.font_size_pt,
        explicit_heading_level=dominant.explicit_heading_level,
        heading_level=dominant.heading_level,
        heading_source=dominant.heading_source,
        list_kind=dominant.list_kind,
        list_level=dominant.list_level,
        list_numbering_format=dominant.list_numbering_format,
        list_num_id=dominant.list_num_id,
        list_abstract_num_id=dominant.list_abstract_num_id,
        list_num_xml=dominant.list_num_xml,
        list_abstract_num_xml=dominant.list_abstract_num_xml,
        role_hint=dominant.role_hint,
        source_xml_fingerprint=dominant.source_xml_fingerprint,
        origin_raw_indexes=merged_indexes,
        origin_raw_texts=merged_texts,
        boundary_source="normalized_merge",
        boundary_confidence=boundary_confidence,
        boundary_rationale=rationale,
    )


def join_merged_paragraph_text(group: list[RawParagraph]) -> str:
    merged_text = " ".join(paragraph.text.strip() for paragraph in group if paragraph.text.strip())
    merged_text = re.sub(r"\s+([,.;:!?…])", r"\1", merged_text)
    merged_text = re.sub(r"\s+", " ", merged_text)
    return merged_text.strip()


def styles_are_compatible(left: RawParagraph, right: RawParagraph) -> bool:
    left_style = left.style_name.strip().lower()
    right_style = right.style_name.strip().lower()
    if left_style == right_style:
        return True
    body_aliases = {"", "normal", "body text", "текст", "обычный"}
    return left_style in body_aliases and right_style in body_aliases


def alignments_are_compatible(left: RawParagraph, right: RawParagraph) -> bool:
    compatible = {None, "left", "start", "both"}
    if left.paragraph_alignment == right.paragraph_alignment:
        return True
    return left.paragraph_alignment in compatible and right.paragraph_alignment in compatible


def alignment_transition_implies_structure(left: RawParagraph, right: RawParagraph) -> bool:
    if alignments_are_compatible(left, right):
        return False
    structured_alignments = {"center", "right", "end"}
    return left.paragraph_alignment in structured_alignments or right.paragraph_alignment in structured_alignments


def style_transition_implies_structure(left: RawParagraph, right: RawParagraph) -> bool:
    for style_name in (left.style_name, right.style_name):
        normalized_style = style_name.strip().lower()
        if is_caption_style(normalized_style):
            return True
        if HEADING_STYLE_PATTERN.match(normalized_style) is not None:
            return True
        if "list" in normalized_style or "спис" in normalized_style:
            return True
    return False


def ends_with_strong_paragraph_terminator(text: str) -> bool:
    return STRONG_PARAGRAPH_TERMINATOR_PATTERN.search(text.strip()) is not None


def starts_with_continuation_signal(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    for char in stripped:
        if char in {'"', "'", "«", "(", "["}:
            continue
        if char.islower() or char.isdigit():
            return True
        break
    first_word = stripped.split()[0].strip("\"'«»()[]").lower() if stripped.split() else ""
    return first_word in {"и", "а", "но", "или", "что", "как", "поэтому", "and", "but", "or", "that", "which"}


def starts_with_new_sentence_signal(text: str, *, has_heading_text_signal) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    for char in stripped:
        if char in {'"', "'", "«", "(", "["}:
            continue
        if char.isupper():
            return True
        break
    return has_heading_text_signal(stripped)


def left_paragraph_looks_incomplete(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    if ends_with_strong_paragraph_terminator(stripped):
        return False
    return stripped[-1].isalnum() or stripped.endswith((",", ";", ":", "-", "(", "["))


def combined_text_reads_as_continuation(left_text: str, right_text: str) -> bool:
    if not left_text.strip() or not right_text.strip():
        return False
    return left_paragraph_looks_incomplete(left_text) and starts_with_continuation_signal(right_text)


def should_promote_medium_merge(positive_reasons: list[str]) -> bool:
    positive_reason_set = set(positive_reasons)
    if not {"same_body_style", "compatible_alignment"}.issubset(positive_reason_set):
        return False
    supporting_signals = {
        "left_not_terminal",
        "left_incomplete",
        "right_starts_continuation",
        "combined_sentence_plausible",
    }
    return len(positive_reason_set & supporting_signals) >= 2


def is_likely_attribution_text(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and len(stripped) <= 120 and stripped.startswith(("-", "—", "–"))


def is_likely_toc_entry_text(text: str) -> bool:
    return TOC_ENTRY_PATTERN.match(text.strip()) is not None


def write_paragraph_boundary_report_artifact(
    *,
    source_name: str,
    source_bytes: bytes,
    mode: str,
    report: ParagraphBoundaryNormalizationReport,
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
            "mode": mode,
            "total_raw_paragraphs": report.total_raw_paragraphs,
            "total_logical_paragraphs": report.total_logical_paragraphs,
            "merged_group_count": report.merged_group_count,
            "merged_raw_paragraph_count": report.merged_raw_paragraph_count,
            **summarize_boundary_normalization_metrics(report),
            "decisions": [
                {
                    "left_raw_index": decision.left_raw_index,
                    "right_raw_index": decision.right_raw_index,
                    "decision": decision.decision,
                    "confidence": decision.confidence,
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
