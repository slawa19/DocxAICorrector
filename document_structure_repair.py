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
_TOC_PAGE_SUFFIX_PATTERN = re.compile(r"^(?P<title>.+?)(?:[.\u2024\u2025\u2026\u2027\u2219\u22c5\u00b7\s]+)(?P<page>\d+)\s*$")
_COMPOUND_TOC_ENTRY_PATTERN = re.compile(
    r"^(?P<toc>.+?(?:\.{2,}|[\u2024\u2025\u2026\u2027\u2219\u22c5\u00b7]{2,}|\u2026)\s*\d+)\s+(?P<rest>.+)$"
)
_LIST_LEAD_FRAGMENT_TERMINATOR_PATTERN = re.compile(r"[,;:]$")
_SCRIPTURE_REFERENCE_PATTERN = re.compile(r"\b(?:[A-Za-zА-Яа-яЁё]+)\s+\d+:\d+(?:-\d+)?\b")
_INLINE_CONTINUATION_ENDING_PATTERN = re.compile(
    r"\b(?:is|are|was|were|the|a|an|and|or|of|to|for|with|in|on|at|by|from|about|regarding|called|named|что|относительно|с|в|на|к|по|для|о|у|при|об|под|над|между|является)$",
    re.IGNORECASE,
)
_INLINE_CONTINUATION_START_PATTERN = re.compile(r"^(?:[a-zа-яё]|[)\],.;:!?-])", re.IGNORECASE)


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
    repaired, repaired_bullet_items, repaired_numbered_items = _merge_list_fragments(
        repaired,
        decisions=decisions,
        repaired_bullet_items=repaired_bullet_items,
        repaired_numbered_items=repaired_numbered_items,
    )

    toc_regions = _find_bounded_toc_regions(repaired)
    toc_title_variants: dict[str, str] = {}
    for start, end in toc_regions:
        bounded_toc_regions += 1
        toc_title_variants.update(_collect_toc_title_variants(repaired, start=start, end=end))
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

    repaired, split_boundary_repairs, split_heading_candidates = _split_compound_toc_aligned_paragraphs(
        repaired,
        toc_title_variants=toc_title_variants,
        decisions=decisions,
    )
    toc_body_boundary_repairs += split_boundary_repairs
    heading_candidates_from_toc += split_heading_candidates

    repaired, repaired_bullet_items, repaired_numbered_items = _merge_list_fragments(
        repaired,
        decisions=decisions,
        repaired_bullet_items=repaired_bullet_items,
        repaired_numbered_items=repaired_numbered_items,
    )

    toc_titles = set(toc_title_variants)
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
    text = str(paragraph.text or "").strip()
    if not text:
        return None
    if _ISOLATED_BULLET_PATTERN.fullmatch(text):
        return "unordered"
    if _ISOLATED_NUMERIC_MARKER_PATTERN.fullmatch(text):
        return "ordered"
    return None


def _merge_list_fragments(
    paragraphs: list[ParagraphUnit],
    *,
    decisions: list[StructureRepairDecision],
    repaired_bullet_items: int,
    repaired_numbered_items: int,
) -> tuple[list[ParagraphUnit], int, int]:
    repaired = list(paragraphs)
    index = 0
    while index < len(repaired) - 1:
        current = repaired[index]
        following = repaired[index + 1]
        marker_kind = _isolated_marker_kind(current)
        if marker_kind is not None and _can_merge_marker_with_following(current, following):
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

        fragment_kind = _split_list_lead_fragment_kind(current)
        if fragment_kind is None or not _can_merge_marker_with_following(current, following):
            index += 1
            continue
        merged = _merge_split_list_lead_with_following(current, following, marker_kind=fragment_kind)
        repaired[index : index + 2] = [merged]
        decisions.append(
            StructureRepairDecision(
                action="merge_split_list_lead_fragment",
                paragraph_indexes=(current.source_index, following.source_index),
                reason=f"split_{fragment_kind}_item_lead_followed_by_body",
                details={"merged_text_preview": merged.text[:120]},
            )
        )
        if fragment_kind == "unordered":
            repaired_bullet_items += 1
        else:
            repaired_numbered_items += 1
    return repaired, repaired_bullet_items, repaired_numbered_items


def _split_list_lead_fragment_kind(paragraph: ParagraphUnit) -> str | None:
    if paragraph.role == "heading":
        return None
    text = str(paragraph.text or "").strip()
    explicit_kind = detect_explicit_list_kind(text)
    if explicit_kind is None:
        return None
    stripped = re.sub(r"^(?:\s*[-*•]\s+|\s*\d+[\.)]\s+)", "", text).strip()
    if not stripped:
        return None
    if _LIST_LEAD_FRAGMENT_TERMINATOR_PATTERN.search(stripped):
        return explicit_kind
    if len(stripped.split()) <= 3 and not stripped.endswith((".", "?", "!")):
        return explicit_kind
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


def _merge_split_list_lead_with_following(current: ParagraphUnit, following: ParagraphUnit, *, marker_kind: str) -> ParagraphUnit:
    merged = deepcopy(current)
    merged.role = "list"
    merged.structural_role = "list"
    merged.list_kind = marker_kind
    merged.text = f"{str(current.text or '').strip()} {str(following.text or '').strip()}".strip()
    merged.origin_raw_indexes = list(dict.fromkeys([*current.origin_raw_indexes, *following.origin_raw_indexes]))
    merged.origin_raw_texts = [*current.origin_raw_texts, *following.origin_raw_texts]
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
        while look_ahead < len(paragraphs) and _is_toc_candidate_text(
            paragraphs[look_ahead].text,
            allow_plain_entry=look_ahead > index + 1,
        ):
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


def _collect_toc_title_variants(paragraphs: Sequence[ParagraphUnit], *, start: int, end: int) -> dict[str, str]:
    titles: dict[str, str] = {}
    for paragraph in paragraphs[start + 1 : end + 1]:
        display_text = _strip_toc_page_reference(paragraph.text)
        normalized = _normalize_outline_text(display_text)
        if normalized and display_text:
            titles.setdefault(normalized, display_text)
    return titles


def _strip_toc_page_reference(text: str) -> str:
    stripped = str(text or "").strip()
    match = _TOC_PAGE_SUFFIX_PATTERN.match(stripped)
    if match is not None:
        return match.group("title").strip(" .\t")
    return stripped


def _normalize_outline_text(text: str) -> str:
    stripped = _strip_toc_page_reference(text)
    if not stripped:
        return ""
    stripped = re.sub(r"\s+", " ", stripped).strip(" .\t")
    return stripped.casefold()


def _split_compound_toc_aligned_paragraphs(
    paragraphs: Sequence[ParagraphUnit],
    *,
    toc_title_variants: Mapping[str, str],
    decisions: list[StructureRepairDecision],
) -> tuple[list[ParagraphUnit], int, int]:
    if not toc_title_variants:
        return list(paragraphs), 0, 0

    split_boundary_repairs = 0
    split_heading_candidates = 0
    repaired: list[ParagraphUnit] = []
    for paragraph in paragraphs:
        split_result = _split_toc_aligned_compound_paragraph(paragraph, toc_title_variants=toc_title_variants)
        if split_result is None:
            repaired.append(paragraph)
            continue
        split_paragraphs, boundary_repairs, heading_candidates = split_result
        repaired.extend(split_paragraphs)
        split_boundary_repairs += boundary_repairs
        split_heading_candidates += heading_candidates
        decisions.append(
            StructureRepairDecision(
                action="split_compound_toc_aligned_paragraph",
                paragraph_indexes=(paragraph.source_index,),
                reason="toc_or_heading_fragment_embedded_inside_single_paragraph",
                details={"split_texts": [item.text[:120] for item in split_paragraphs]},
            )
        )
    return repaired, split_boundary_repairs, split_heading_candidates


def _split_toc_aligned_compound_paragraph(
    paragraph: ParagraphUnit,
    *,
    toc_title_variants: Mapping[str, str],
) -> tuple[list[ParagraphUnit], int, int] | None:
    if paragraph.structural_role in {"toc_header", "toc_entry", "image", "table", "caption"}:
        return None
    if paragraph.role == "list":
        return None
    text = str(paragraph.text or "").strip()
    if not text:
        return None

    pieces: list[ParagraphUnit] = []
    boundary_repairs = 0
    heading_candidates = 0

    compound_match = _COMPOUND_TOC_ENTRY_PATTERN.match(text)
    if compound_match is not None:
        toc_text = compound_match.group("toc").strip()
        rest_text = compound_match.group("rest").strip()
        if _is_toc_candidate_text(toc_text) and rest_text:
            toc_paragraph = _clone_as_toc_entry(paragraph, toc_text)
            pieces.append(toc_paragraph)
            text = rest_text
            boundary_repairs += 1

    anchor = _find_toc_title_anchor(text, toc_title_variants)
    if anchor is not None and anchor[0] > 0:
        before_title = text[: anchor[0]].strip()
        anchored_text = text[anchor[0] :].strip()
        title_match = _match_toc_title_at_start(anchored_text, toc_title_variants)
        if title_match is not None and _looks_like_inline_continuation_fragment(before_title, title_match[1]):
            return None
        text = anchored_text
        if before_title:
            pieces.append(_clone_with_role(paragraph, before_title, structural_role=_infer_structural_role_for_prefix(before_title)))

    title_match = _match_toc_title_at_start(text, toc_title_variants)
    if title_match is None:
        if pieces:
            pieces.append(_clone_with_role(paragraph, text, structural_role=_infer_structural_role_for_prefix(text)))
            return pieces, boundary_repairs, heading_candidates
        return None

    title_text, remainder = title_match
    if not remainder:
        return None if not pieces else (pieces, boundary_repairs, heading_candidates)

    pieces.append(_clone_as_heading(paragraph, title_text))
    heading_candidates += 1
    remainder = remainder.strip()
    remainder = re.sub(r"^[\s:;?!,]+", "", remainder).strip()
    if not remainder:
        return pieces, boundary_repairs, heading_candidates
    if _ISOLATED_NUMERIC_MARKER_PATTERN.fullmatch(remainder):
        pieces.append(_clone_with_role(paragraph, remainder, structural_role="body"))
        return pieces, boundary_repairs, heading_candidates
    explicit_kind = detect_explicit_list_kind(remainder)
    if explicit_kind is not None:
        pieces.append(_clone_as_list(paragraph, remainder, list_kind=explicit_kind))
        return pieces, boundary_repairs, heading_candidates
    pieces.append(_clone_with_role(paragraph, remainder, structural_role=_infer_structural_role_for_prefix(remainder)))
    return pieces, boundary_repairs, heading_candidates


def _find_toc_title_anchor(text: str, toc_title_variants: Mapping[str, str]) -> tuple[int, str] | None:
    best_match: tuple[int, str] | None = None
    for title_text in toc_title_variants.values():
        if len(title_text.split()) > 8:
            continue
        match = re.search(rf"(?<!\w){re.escape(title_text)}(?!\w)", text, flags=re.IGNORECASE)
        if match is None:
            continue
        candidate = (match.start(), text[match.start() : match.end()])
        if best_match is None or candidate[0] < best_match[0] or (
            candidate[0] == best_match[0] and len(candidate[1]) > len(best_match[1])
        ):
            best_match = candidate
    return best_match


def _match_toc_title_at_start(text: str, toc_title_variants: Mapping[str, str]) -> tuple[str, str] | None:
    for title_text in sorted(toc_title_variants.values(), key=len, reverse=True):
        if len(title_text.split()) > 8:
            continue
        match = re.match(rf"^{re.escape(title_text)}(?!\w)", text, flags=re.IGNORECASE)
        if match is None:
            continue
        matched_text = text[: match.end()].strip()
        remainder = text[match.end() :].strip()
        return matched_text, remainder
    return _match_normalized_toc_title_prefix(text, toc_title_variants)


def _match_normalized_toc_title_prefix(text: str, toc_title_variants: Mapping[str, str]) -> tuple[str, str] | None:
    tokens = text.split()
    max_words = min(8, len(tokens))
    toc_titles = set(toc_title_variants)
    for word_count in range(max_words, 0, -1):
        prefix = " ".join(tokens[:word_count]).strip()
        normalized_prefix = _normalize_outline_text(prefix).strip(" :;?!.,")
        if normalized_prefix not in toc_titles:
            continue
        remainder = " ".join(tokens[word_count:]).strip(" :;?!.,")
        if remainder:
            return prefix, remainder
    return None


def _clone_with_role(paragraph: ParagraphUnit, text: str, *, structural_role: str) -> ParagraphUnit:
    clone = deepcopy(paragraph)
    clone.text = text.strip()
    clone.role = "body"
    clone.structural_role = structural_role
    clone.heading_level = None
    clone.heading_source = None
    clone.list_kind = None
    return clone


def _clone_as_toc_entry(paragraph: ParagraphUnit, text: str) -> ParagraphUnit:
    clone = deepcopy(paragraph)
    clone.text = text.strip()
    clone.role = "body"
    clone.structural_role = "toc_entry"
    clone.heading_level = None
    clone.heading_source = None
    clone.list_kind = None
    return clone


def _clone_as_heading(paragraph: ParagraphUnit, text: str) -> ParagraphUnit:
    clone = deepcopy(paragraph)
    clone.text = text.strip()
    clone.role = "heading"
    clone.structural_role = "heading"
    clone.heading_source = "heuristic"
    clone.heading_level = clone.heading_level or 2
    clone.list_kind = None
    return clone


def _clone_as_list(paragraph: ParagraphUnit, text: str, *, list_kind: str) -> ParagraphUnit:
    clone = deepcopy(paragraph)
    clone.text = text.strip()
    clone.role = "list"
    clone.structural_role = "list"
    clone.list_kind = list_kind
    clone.heading_level = None
    clone.heading_source = None
    return clone


def _infer_structural_role_for_prefix(text: str) -> str:
    if _looks_like_epigraph_prefix(text):
        return "epigraph"
    return "body"


def _looks_like_inline_continuation_fragment(before_title: str, remainder: str) -> bool:
    before = str(before_title or "").strip()
    after = str(remainder or "").strip()
    if not before or not after:
        return False
    if _looks_like_citation_or_marker(before) or _looks_like_citation_or_marker(after):
        return False
    if not _INLINE_CONTINUATION_ENDING_PATTERN.search(before):
        return False
    return bool(_INLINE_CONTINUATION_START_PATTERN.match(after))


def _looks_like_epigraph_prefix(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    if any(quote in stripped for quote in ('"', "“", "”", "«", "»", "'")):
        return True
    if _SCRIPTURE_REFERENCE_PATTERN.search(stripped):
        return True
    return stripped.startswith(("—", "-"))


def _is_toc_header(text: str) -> bool:
    return str(text or "").strip().casefold() in _TOC_HEADER_VALUES


def _is_toc_candidate_text(text: str, *, allow_plain_entry: bool = False) -> bool:
    stripped = str(text or "").strip()
    if not stripped or len(stripped) > 160:
        return False
    if _ISOLATED_BULLET_PATTERN.fullmatch(stripped):
        return False
    if detect_explicit_list_kind(stripped) is not None:
        return False
    if re.match(r"^[A-Za-zА-Яа-я]+\s+\d+:\d+(?:-\d+)?$", stripped):
        return False
    words = len(_TOC_WORD_PATTERN.findall(stripped))
    if words < 1 or words > 16:
        return False
    if stripped.endswith((".", ";", ":")):
        return False
    if bool(re.search(r"(?:\.{2,}|[\u2024\u2025\u2026\u2027\u2219\u22c5\u00b7]{2,}|\s\d+\s*$)", stripped)):
        return True
    if has_heading_text_signal(stripped):
        return True
    return allow_plain_entry and words <= 8


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
