from __future__ import annotations

import re
from copy import deepcopy
from collections.abc import Mapping, Sequence

from document_roles import detect_explicit_list_kind, has_heading_text_signal
from models import ParagraphUnit, StructureRepairDecision, StructureRepairReport


_TOC_HEADER_VALUES = {"contents", "table of contents", "содержание"}
_TOC_WORD_PATTERN = re.compile(r"\w+(?:[-']\w+)*", re.UNICODE)
_ISOLATED_BULLET_PATTERN = re.compile(r"^[\s\u2022\u25cf\u25e6\u2023\-*]+$")
_ISOLATED_NUMERIC_MARKER_PATTERN = re.compile(r"^\s*\d+[\.)]\s*$")
_EPIGRAPH_ATTRIBUTION_PATTERN = re.compile(r"^[\s\u2014\-].+")


def repair_pdf_derived_structure(
    paragraphs: Sequence[ParagraphUnit],
    *,
    app_config: Mapping[str, object] | None = None,
) -> tuple[list[ParagraphUnit], StructureRepairReport]:
    repaired = [deepcopy(paragraph) for paragraph in paragraphs]
    decisions: list[StructureRepairDecision] = []
    repaired_bullet_items = 0
    repaired_numbered_items = 0
    bounded_toc_regions = 0
    toc_body_boundary_repairs = 0
    heading_candidates_from_toc = 0

    index = 0
    while index < len(repaired) - 1:
        current = repaired[index]
        following = repaired[index + 1]
        marker_kind = _isolated_marker_kind(current)
        if marker_kind is None or not _can_merge_marker_with_following(current, following):
            index += 1
            continue
        merged = _merge_marker_with_following(current, following, marker_kind=marker_kind)
        repaired[index : index + 2] = [merged]
        decisions.append(
            StructureRepairDecision(
                action="merge_isolated_list_marker",
                paragraph_indexes=(current.source_index, following.source_index),
                reason=f"isolated_{marker_kind}_marker_followed_by_body",
                details={"merged_text_preview": merged.text[:120]},
            )
        )
        if marker_kind == "unordered":
            repaired_bullet_items += 1
        else:
            repaired_numbered_items += 1
        continue

    toc_regions = _find_bounded_toc_regions(repaired)
    toc_titles = set()
    for start, end in toc_regions:
        bounded_toc_regions += 1
        toc_titles.update(_collect_toc_titles(repaired, start=start, end=end))
        if end + 1 < len(repaired) and _is_body_boundary_candidate(repaired[end + 1]):
            toc_body_boundary_repairs += 1
            decisions.append(
                StructureRepairDecision(
                    action="bound_toc_region",
                    paragraph_indexes=tuple(paragraph.source_index for paragraph in repaired[start : end + 2]),
                    reason="bounded_toc_region_before_body_start",
                    details={
                        "toc_start": repaired[start].source_index,
                        "toc_end": repaired[end].source_index,
                        "body_start": repaired[end + 1].source_index,
                    },
                )
            )

    if toc_titles:
        for paragraph in repaired:
            if paragraph.structural_role in {"toc_header", "toc_entry"}:
                continue
            if paragraph.role == "heading":
                continue
            normalized = _normalize_outline_text(paragraph.text)
            if not normalized or normalized not in toc_titles:
                continue
            if _looks_like_citation_or_marker(paragraph.text):
                continue
            paragraph.role = "heading"
            paragraph.structural_role = "heading"
            paragraph.heading_source = "heuristic"
            paragraph.heading_level = paragraph.heading_level or 2
            heading_candidates_from_toc += 1
            decisions.append(
                StructureRepairDecision(
                    action="promote_heading_from_toc_hint",
                    paragraph_indexes=(paragraph.source_index,),
                    reason="body_line_matches_toc_entry",
                    details={"text_preview": paragraph.text[:120]},
                )
            )

    remaining_isolated_marker_count = sum(1 for paragraph in repaired if _isolated_marker_kind(paragraph) is not None)
    report = StructureRepairReport(
        applied=bool(decisions),
        repaired_bullet_items=repaired_bullet_items,
        repaired_numbered_items=repaired_numbered_items,
        bounded_toc_regions=bounded_toc_regions,
        toc_body_boundary_repairs=toc_body_boundary_repairs,
        heading_candidates_from_toc=heading_candidates_from_toc,
        remaining_isolated_marker_count=remaining_isolated_marker_count,
        decisions=decisions,
    )
    return repaired, report


def _isolated_marker_kind(paragraph: ParagraphUnit) -> str | None:
    if paragraph.role == "heading":
        return None
    text = str(paragraph.text or "").strip()
    if not text:
        return None
    if _ISOLATED_BULLET_PATTERN.fullmatch(text):
        return "unordered"
    if _ISOLATED_NUMERIC_MARKER_PATTERN.fullmatch(text):
        return "ordered"
    return None


def _can_merge_marker_with_following(current: ParagraphUnit, following: ParagraphUnit) -> bool:
    if following.role in {"heading", "image", "table", "caption"}:
        return False
    if following.structural_role in {"toc_header", "toc_entry", "caption"}:
        return False
    if not str(following.text or "").strip():
        return False
    if _isolated_marker_kind(following) is not None:
        return False
    return True


def _merge_marker_with_following(current: ParagraphUnit, following: ParagraphUnit, *, marker_kind: str) -> ParagraphUnit:
    merged = deepcopy(following)
    text = str(following.text or "").strip()
    if marker_kind == "unordered":
        merged.role = "list"
        merged.structural_role = "list"
        merged.list_kind = "unordered"
        merged.text = f"- {text}" if not text.startswith("- ") else text
    else:
        merged.role = "list"
        merged.structural_role = "list"
        merged.list_kind = "ordered"
        marker_text = str(current.text or "").strip()
        merged.text = f"{marker_text} {text}"
    merged.origin_raw_indexes = list(dict.fromkeys([*current.origin_raw_indexes, *following.origin_raw_indexes]))
    merged.origin_raw_texts = [*current.origin_raw_texts, *following.origin_raw_texts]
    merged.source_index = current.source_index
    merged.paragraph_id = current.paragraph_id or following.paragraph_id
    merged.heading_level = None
    merged.heading_source = None
    return merged


def _find_bounded_toc_regions(paragraphs: Sequence[ParagraphUnit]) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    index = 0
    while index < len(paragraphs):
        paragraph = paragraphs[index]
        if not _is_toc_header(paragraph.text):
            index += 1
            continue
        look_ahead = index + 1
        while look_ahead < len(paragraphs) and _is_toc_candidate_text(paragraphs[look_ahead].text):
            entry = paragraphs[look_ahead]
            entry.role = "body"
            entry.structural_role = "toc_entry"
            entry.heading_level = None
            entry.heading_source = None
            look_ahead += 1
        if look_ahead - index >= 3:
            paragraph.role = "body"
            paragraph.structural_role = "toc_header"
            paragraph.heading_level = None
            paragraph.heading_source = None
            regions.append((index, look_ahead - 1))
            index = look_ahead
            continue
        index += 1
    return regions


def _collect_toc_titles(paragraphs: Sequence[ParagraphUnit], *, start: int, end: int) -> set[str]:
    titles: set[str] = set()
    for paragraph in paragraphs[start + 1 : end + 1]:
        normalized = _normalize_outline_text(paragraph.text)
        if normalized:
            titles.add(normalized)
    return titles


def _normalize_outline_text(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return ""
    stripped = re.sub(r"[.\u2024\u2025\u2026\u2027\u2219\u22c5\u00b7\s]+\d+\s*$", "", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip(" .\t")
    return stripped.casefold()


def _is_toc_header(text: str) -> bool:
    return str(text or "").strip().casefold() in _TOC_HEADER_VALUES


def _is_toc_candidate_text(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped or len(stripped) > 160:
        return False
    if _ISOLATED_BULLET_PATTERN.fullmatch(stripped):
        return False
    if re.match(r"^[A-Za-zА-Яа-я]+\s+\d+:\d+(?:-\d+)?$", stripped):
        return False
    words = len(_TOC_WORD_PATTERN.findall(stripped))
    if words < 1 or words > 16:
        return False
    if stripped.endswith((".", ";", ":")):
        return False
    return bool(re.search(r"(?:\.{2,}|\u2026|\s\d+\s*$)", stripped)) or has_heading_text_signal(stripped)


def _is_body_boundary_candidate(paragraph: ParagraphUnit) -> bool:
    text = str(paragraph.text or "").strip()
    if not text:
        return False
    if paragraph.role == "heading":
        return True
    if paragraph.paragraph_alignment == "center" and not _is_toc_candidate_text(text):
        return True
    if _EPIGRAPH_ATTRIBUTION_PATTERN.match(text):
        return True
    if len(text.split()) >= 6 and not _is_toc_candidate_text(text):
        return True
    return False


def _looks_like_citation_or_marker(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return True
    if detect_explicit_list_kind(stripped) is not None:
        return True
    if _ISOLATED_BULLET_PATTERN.fullmatch(stripped):
        return True
    if re.match(r"^[A-Za-zА-Яа-я]+\s+\d+:\d+(?:-\d+)?$", stripped):
        return True
    return False


__all__ = ["repair_pdf_derived_structure"]
