from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from collections.abc import Sequence

from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.document.roles import has_heading_text_signal, infer_heuristic_heading_level
from docxaicorrector.document.structure_repair import _collect_toc_title_variants, _match_normalized_toc_title_prefix, _normalize_outline_text


CHAPTER_SEGMENTS_DETECTOR_VERSION = "chapter_segments_v1"
_FALLBACK_SEGMENT_MIN_CHARS = 24000
_APPENDIX_PATTERN = re.compile(r"^(?:appendix|appendices|приложение)\b", re.IGNORECASE)
_BIBLIOGRAPHY_PATTERN = re.compile(
    r"^(?:references|bibliography|works cited|литература|список литературы|bibliographie)\b",
    re.IGNORECASE,
)
_CHAPTER_PATTERN = re.compile(r"^(?:chapter|part|глава|часть)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SegmentBoundaryEvidence:
    source: str = "fallback"
    confidence: str = "low"
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentSegment:
    segment_id: str = ""
    parent_segment_id: str | None = None
    ordinal: int = 0
    level: int = 1
    title: str = ""
    normalized_title: str = ""
    start_paragraph_index: int = 0
    end_paragraph_index: int = 0
    start_paragraph_id: str = ""
    end_paragraph_id: str = ""
    paragraph_ids: tuple[str, ...] = ()
    paragraph_count: int = 0
    char_count: int = 0
    word_count: int = 0
    estimated_token_count: int = 1
    structural_role: str = "body_range"
    confidence: str = "low"
    boundary_fingerprint: str = ""
    boundary_evidence: tuple[SegmentBoundaryEvidence, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SegmentDetectionReport:
    segment_count: int = 0
    high_confidence_count: int = 0
    medium_confidence_count: int = 0
    low_confidence_count: int = 0
    fallback_segment_count: int = 0
    toc_entry_count: int = 0
    toc_matched_count: int = 0
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class GlossaryTerm:
    source_term: str = ""
    target_term: str = ""
    confidence: str = "medium"
    source_segment_id: str | None = None


@dataclass(frozen=True)
class SegmentOutlineEntry:
    segment_id: str = ""
    title: str = ""
    level: int = 1
    structural_role: str = "body_range"


@dataclass(frozen=True)
class _SegmentStartCandidate:
    start_index: int
    level: int
    title: str
    normalized_title: str
    structural_role: str
    confidence: str
    boundary_evidence: tuple[SegmentBoundaryEvidence, ...]
    toc_matched: bool = False


def detect_document_segments(
    paragraphs: Sequence[ParagraphUnit],
    *,
    source_content_hash16: str,
    chunk_size: int,
    detector_version: str = CHAPTER_SEGMENTS_DETECTOR_VERSION,
) -> tuple[list[DocumentSegment], SegmentDetectionReport, str]:
    paragraph_list = list(paragraphs)
    if not paragraph_list:
        return [], SegmentDetectionReport(), _build_structure_fingerprint(())

    toc_regions = _collect_toc_regions(paragraph_list)
    toc_title_variants: dict[str, str] = {}
    for start_index, end_index in toc_regions:
        toc_title_variants.update(_collect_toc_title_variants(paragraph_list, start=start_index, end=end_index))

    heading_candidates = _collect_heading_candidates(paragraph_list, toc_title_variants=toc_title_variants)
    fallback_max_chars = max(int(chunk_size or 0) * 4, _FALLBACK_SEGMENT_MIN_CHARS)
    segments: list[DocumentSegment] = []

    if not heading_candidates:
        segments.extend(
            _build_fallback_segments(
                paragraph_list,
                start_index=0,
                end_index=len(paragraph_list) - 1,
                start_ordinal=1,
                source_content_hash16=source_content_hash16,
                detector_version=detector_version,
                fallback_max_chars=fallback_max_chars,
                structural_role=_resolve_range_structural_role(paragraph_list, 0, len(paragraph_list) - 1, default_role="body_range"),
                title_prefix="Body Range",
            )
        )
    else:
        cursor = 0
        for candidate_index, candidate in enumerate(heading_candidates):
            if cursor < candidate.start_index:
                gap_end = candidate.start_index - 1
                segments.extend(
                    _build_gap_segments(
                        paragraph_list,
                        start_index=cursor,
                        end_index=gap_end,
                        start_ordinal=len(segments) + 1,
                        source_content_hash16=source_content_hash16,
                        detector_version=detector_version,
                        fallback_max_chars=fallback_max_chars,
                    )
                )
            next_start_index = (
                heading_candidates[candidate_index + 1].start_index
                if candidate_index + 1 < len(heading_candidates)
                else len(paragraph_list)
            )
            segment_end = next_start_index - 1
            segments.append(
                _build_segment(
                    paragraph_list,
                    start_index=candidate.start_index,
                    end_index=segment_end,
                    ordinal=len(segments) + 1,
                    level=candidate.level,
                    title=candidate.title,
                    normalized_title=candidate.normalized_title,
                    structural_role=candidate.structural_role,
                    confidence=candidate.confidence,
                    boundary_evidence=candidate.boundary_evidence,
                    source_content_hash16=source_content_hash16,
                    detector_version=detector_version,
                )
            )
            cursor = segment_end + 1
        if cursor < len(paragraph_list):
            segments.extend(
                _build_gap_segments(
                    paragraph_list,
                    start_index=cursor,
                    end_index=len(paragraph_list) - 1,
                    start_ordinal=len(segments) + 1,
                    source_content_hash16=source_content_hash16,
                    detector_version=detector_version,
                    fallback_max_chars=fallback_max_chars,
                )
            )

    parent_ids_by_ordinal = _resolve_parent_ids(segments)
    segments_with_parents = [
        DocumentSegment(
            **{
                **segment.__dict__,
                "parent_segment_id": parent_ids_by_ordinal.get(segment.ordinal),
            }
        )
        for segment in segments
    ]
    structure_fingerprint = _build_structure_fingerprint(segments_with_parents)
    warnings = _build_report_warnings(segments_with_parents, heading_candidates)
    report = SegmentDetectionReport(
        segment_count=len(segments_with_parents),
        high_confidence_count=sum(1 for segment in segments_with_parents if segment.confidence == "high"),
        medium_confidence_count=sum(1 for segment in segments_with_parents if segment.confidence == "medium"),
        low_confidence_count=sum(1 for segment in segments_with_parents if segment.confidence == "low"),
        fallback_segment_count=sum(1 for segment in segments_with_parents if _is_fallback_segment(segment)),
        toc_entry_count=sum(1 for paragraph in paragraph_list if _is_toc_structural_role(paragraph)),
        toc_matched_count=sum(1 for candidate in heading_candidates if candidate.toc_matched),
        warnings=warnings,
    )
    return segments_with_parents, report, structure_fingerprint


def resolve_segment_hard_boundary_paragraph_ids(segments: Sequence[DocumentSegment]) -> set[str]:
    return {
        str(segment.start_paragraph_id)
        for segment in segments
        if segment.ordinal > 1 and str(segment.start_paragraph_id).strip()
    }


def build_segment_to_job_mapping(
    segments: Sequence[DocumentSegment],
    jobs: Sequence[dict[str, object]],
) -> dict[str, tuple[int, ...]]:
    paragraph_sets = {segment.segment_id: set(segment.paragraph_ids) for segment in segments if segment.segment_id}
    mapping: dict[str, list[int]] = {segment.segment_id: [] for segment in segments if segment.segment_id}
    for job_index, job in enumerate(jobs):
        raw_ids = job.get("paragraph_ids") if isinstance(job, dict) else None
        paragraph_ids = {
            str(paragraph_id)
            for paragraph_id in (raw_ids if isinstance(raw_ids, (list, tuple, set, frozenset)) else ())
            if str(paragraph_id).strip()
        }
        if not paragraph_ids:
            continue
        for segment in segments:
            segment_id = segment.segment_id
            if not segment_id:
                continue
            segment_paragraph_ids = paragraph_sets.get(segment_id, set())
            if paragraph_ids.issubset(segment_paragraph_ids):
                mapping.setdefault(segment_id, []).append(job_index)
                break
    return {segment_id: tuple(indexes) for segment_id, indexes in mapping.items()}


def _collect_toc_regions(paragraphs: Sequence[ParagraphUnit]) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    index = 0
    while index < len(paragraphs):
        if not _is_toc_structural_role(paragraphs[index]):
            index += 1
            continue
        region_start = index
        while index + 1 < len(paragraphs) and _is_toc_structural_role(paragraphs[index + 1]):
            index += 1
        regions.append((region_start, index))
        index += 1
    return regions


def _collect_heading_candidates(
    paragraphs: Sequence[ParagraphUnit],
    *,
    toc_title_variants: dict[str, str],
) -> list[_SegmentStartCandidate]:
    candidates: list[_SegmentStartCandidate] = []
    for index, paragraph in enumerate(paragraphs):
        text = str(getattr(paragraph, "text", "") or "").strip()
        if not text:
            continue
        if str(getattr(paragraph, "structural_role", "") or "").strip().lower() in {
            "toc_header",
            "toc_entry",
            "caption",
            "image",
            "table",
        }:
            continue
        evidence: list[SegmentBoundaryEvidence] = []
        normalized_title = _normalize_segment_title(text)
        toc_match = _resolve_toc_match(text, normalized_title=normalized_title, toc_title_variants=toc_title_variants)
        if getattr(paragraph, "role", "") == "heading":
            evidence.extend(_build_heading_evidence(paragraph))
        if toc_match is not None:
            evidence.append(
                SegmentBoundaryEvidence(
                    source="toc_match",
                    confidence="high" if getattr(paragraph, "role", "") == "heading" else "medium",
                    details={"matched_title": toc_match},
                )
            )
        if has_heading_text_signal(text):
            evidence.append(
                SegmentBoundaryEvidence(
                    source="numbering_pattern",
                    confidence="medium",
                    details={"text_preview": text[:80]},
                )
            )
        if _has_typography_heading_signal(paragraph, text):
            evidence.append(
                SegmentBoundaryEvidence(
                    source="typography",
                    confidence="medium" if getattr(paragraph, "role", "") == "heading" else "low",
                    details={
                        "is_bold": bool(getattr(paragraph, "is_bold", False)),
                        "alignment": getattr(paragraph, "paragraph_alignment", None),
                        "font_size_pt": getattr(paragraph, "font_size_pt", None),
                    },
                )
            )
        if not evidence:
            continue
        if not _should_be_segment_candidate(paragraph, index=index, toc_match=toc_match, text=text):
            continue
        level = _resolve_segment_level(paragraph, text)
        confidence = _resolve_confidence(evidence)
        candidates.append(
            _SegmentStartCandidate(
                start_index=index,
                level=level,
                title=text,
                normalized_title=normalized_title,
                structural_role=_resolve_heading_structural_role(text=text, level=level),
                confidence=confidence,
                boundary_evidence=tuple(evidence),
                toc_matched=toc_match is not None,
            )
        )
    return candidates


def _build_heading_evidence(paragraph: ParagraphUnit) -> list[SegmentBoundaryEvidence]:
    source = str(getattr(paragraph, "heading_source", "") or "").strip().lower()
    confidence = str(getattr(paragraph, "role_confidence", "") or "").strip().lower()
    if source == "explicit" or confidence == "explicit":
        return [
            SegmentBoundaryEvidence(
                source="heading_style",
                confidence="high",
                details={
                    "heading_level": getattr(paragraph, "heading_level", None),
                    "style_name": getattr(paragraph, "style_name", ""),
                },
            )
        ]
    if source == "ai" or confidence == "ai":
        return [
            SegmentBoundaryEvidence(
                source="ai_structure",
                confidence="high",
                details={"heading_level": getattr(paragraph, "heading_level", None)},
            )
        ]
    return [
        SegmentBoundaryEvidence(
            source="fallback" if source == "" else source,
            confidence="medium",
            details={"heading_level": getattr(paragraph, "heading_level", None)},
        )
    ]


def _resolve_toc_match(text: str, *, normalized_title: str, toc_title_variants: dict[str, str]) -> str | None:
    if normalized_title and normalized_title in toc_title_variants:
        return toc_title_variants[normalized_title]
    matched_prefix = _match_normalized_toc_title_prefix(text, toc_title_variants)
    if matched_prefix is None:
        return None
    return matched_prefix[0]


def _should_be_segment_candidate(paragraph: ParagraphUnit, *, index: int, toc_match: str | None, text: str) -> bool:
    role = str(getattr(paragraph, "role", "") or "").strip().lower()
    structural_role = str(getattr(paragraph, "structural_role", "") or "").strip().lower()
    if structural_role in {"epigraph", "attribution", "dedication"} and role != "heading":
        return False
    if role == "heading":
        if index < 3 and toc_match is None and str(getattr(paragraph, "heading_source", "") or "") == "heuristic":
            if not has_heading_text_signal(text):
                return False
        return True
    if toc_match is not None:
        return True
    return _has_typography_heading_signal(paragraph, text) and has_heading_text_signal(text)


def _resolve_segment_level(paragraph: ParagraphUnit, text: str) -> int:
    level = getattr(paragraph, "heading_level", None)
    if isinstance(level, int) and level > 0:
        return min(level, 6)
    return min(max(infer_heuristic_heading_level(text), 1), 6)


def _resolve_heading_structural_role(*, text: str, level: int) -> str:
    normalized_text = str(text or "").strip()
    if _BIBLIOGRAPHY_PATTERN.match(normalized_text):
        return "bibliography"
    if _APPENDIX_PATTERN.match(normalized_text):
        return "appendix"
    if _CHAPTER_PATTERN.match(normalized_text):
        return "chapter"
    return "chapter" if level <= 1 else "section"


def _build_gap_segments(
    paragraphs: Sequence[ParagraphUnit],
    *,
    start_index: int,
    end_index: int,
    start_ordinal: int,
    source_content_hash16: str,
    detector_version: str,
    fallback_max_chars: int,
) -> list[DocumentSegment]:
    if start_index > end_index:
        return []
    structural_role = _resolve_range_structural_role(paragraphs, start_index, end_index, default_role="front_matter")
    title_prefix = "Table of Contents" if structural_role == "toc" else "Front Matter"
    if structural_role != "toc" and _range_char_count(paragraphs, start_index, end_index) > fallback_max_chars:
        return _build_fallback_segments(
            paragraphs,
            start_index=start_index,
            end_index=end_index,
            start_ordinal=start_ordinal,
            source_content_hash16=source_content_hash16,
            detector_version=detector_version,
            fallback_max_chars=fallback_max_chars,
            structural_role="body_range",
            title_prefix="Body Range",
        )
    return [
        _build_segment(
            paragraphs,
            start_index=start_index,
            end_index=end_index,
            ordinal=start_ordinal,
            level=1,
            title=title_prefix if start_index == 0 or structural_role == "toc" else f"{title_prefix} {start_ordinal}",
            normalized_title=_normalize_segment_title(title_prefix),
            structural_role=structural_role,
            confidence="high" if structural_role == "toc" else "medium",
            boundary_evidence=(
                SegmentBoundaryEvidence(
                    source="fallback" if structural_role != "toc" else "toc_match",
                    confidence="medium" if structural_role != "toc" else "high",
                    details={"range": [start_index, end_index]},
                ),
            ),
            source_content_hash16=source_content_hash16,
            detector_version=detector_version,
        )
    ]


def _build_fallback_segments(
    paragraphs: Sequence[ParagraphUnit],
    *,
    start_index: int,
    end_index: int,
    start_ordinal: int,
    source_content_hash16: str,
    detector_version: str,
    fallback_max_chars: int,
    structural_role: str,
    title_prefix: str,
) -> list[DocumentSegment]:
    segments: list[DocumentSegment] = []
    range_start = start_index
    current_chars = 0
    ordinal = start_ordinal
    for index in range(start_index, end_index + 1):
        paragraph = paragraphs[index]
        paragraph_chars = len(str(getattr(paragraph, "text", "") or ""))
        if index > range_start and current_chars >= fallback_max_chars:
            segments.append(
                _build_segment(
                    paragraphs,
                    start_index=range_start,
                    end_index=index - 1,
                    ordinal=ordinal,
                    level=1,
                    title=f"{title_prefix} {len(segments) + 1}",
                    normalized_title=_normalize_segment_title(f"{title_prefix} {len(segments) + 1}"),
                    structural_role=structural_role,
                    confidence="low",
                    boundary_evidence=(
                        SegmentBoundaryEvidence(
                            source="fallback",
                            confidence="low",
                            details={"fallback_segment_max_chars": fallback_max_chars},
                        ),
                    ),
                    source_content_hash16=source_content_hash16,
                    detector_version=detector_version,
                )
            )
            ordinal += 1
            range_start = index
            current_chars = 0
        current_chars += paragraph_chars
    if range_start <= end_index:
        segments.append(
            _build_segment(
                paragraphs,
                start_index=range_start,
                end_index=end_index,
                ordinal=ordinal,
                level=1,
                title=f"{title_prefix} {len(segments) + 1}",
                normalized_title=_normalize_segment_title(f"{title_prefix} {len(segments) + 1}"),
                structural_role=structural_role,
                confidence="low",
                boundary_evidence=(
                    SegmentBoundaryEvidence(
                        source="fallback",
                        confidence="low",
                        details={"fallback_segment_max_chars": fallback_max_chars},
                    ),
                ),
                source_content_hash16=source_content_hash16,
                detector_version=detector_version,
            )
        )
    return segments


def _build_segment(
    paragraphs: Sequence[ParagraphUnit],
    *,
    start_index: int,
    end_index: int,
    ordinal: int,
    level: int,
    title: str,
    normalized_title: str,
    structural_role: str,
    confidence: str,
    boundary_evidence: tuple[SegmentBoundaryEvidence, ...],
    source_content_hash16: str,
    detector_version: str,
) -> DocumentSegment:
    segment_paragraphs = list(paragraphs[start_index : end_index + 1])
    paragraph_ids = tuple(_resolve_paragraph_id(paragraph, fallback_index=index) for index, paragraph in enumerate(segment_paragraphs, start=start_index))
    char_count = sum(len(str(getattr(paragraph, "text", "") or "")) for paragraph in segment_paragraphs)
    word_count = sum(len(str(getattr(paragraph, "text", "") or "").split()) for paragraph in segment_paragraphs)
    start_paragraph_id = paragraph_ids[0] if paragraph_ids else ""
    end_paragraph_id = paragraph_ids[-1] if paragraph_ids else ""
    boundary_fingerprint = _build_boundary_fingerprint(
        normalized_title=normalized_title,
        level=level,
        start_paragraph_id=start_paragraph_id,
        end_paragraph_id=end_paragraph_id,
    )
    segment_id = _build_segment_id(
        ordinal=ordinal,
        source_content_hash16=source_content_hash16,
        normalized_title=normalized_title,
        level=level,
        start_paragraph_id=start_paragraph_id,
        end_paragraph_id=end_paragraph_id,
        start_index=start_index,
        end_index=end_index,
        detector_version=detector_version,
    )
    warnings = ("low_confidence_boundary",) if confidence == "low" else ()
    return DocumentSegment(
        segment_id=segment_id,
        ordinal=ordinal,
        level=level,
        title=title,
        normalized_title=normalized_title,
        start_paragraph_index=start_index,
        end_paragraph_index=end_index,
        start_paragraph_id=start_paragraph_id,
        end_paragraph_id=end_paragraph_id,
        paragraph_ids=paragraph_ids,
        paragraph_count=len(segment_paragraphs),
        char_count=char_count,
        word_count=word_count,
        estimated_token_count=max(1, char_count // 4),
        structural_role=structural_role,
        confidence=confidence,
        boundary_fingerprint=boundary_fingerprint,
        boundary_evidence=boundary_evidence,
        warnings=warnings,
    )


def _resolve_parent_ids(segments: Sequence[DocumentSegment]) -> dict[int, str | None]:
    parents: dict[int, str | None] = {}
    stack: list[DocumentSegment] = []
    for segment in segments:
        while stack and stack[-1].level >= segment.level:
            stack.pop()
        parents[segment.ordinal] = stack[-1].segment_id if stack else None
        stack.append(segment)
    return parents


def _build_report_warnings(
    segments: Sequence[DocumentSegment],
    heading_candidates: Sequence[_SegmentStartCandidate],
) -> tuple[str, ...]:
    warnings: list[str] = []
    if not heading_candidates:
        warnings.append("no_heading_boundaries_detected")
    if any(segment.confidence == "low" for segment in segments):
        warnings.append("low_confidence_segments_present")
    return tuple(warnings)


def _is_fallback_segment(segment: DocumentSegment) -> bool:
    return any(evidence.source == "fallback" for evidence in segment.boundary_evidence)


def _resolve_range_structural_role(
    paragraphs: Sequence[ParagraphUnit],
    start_index: int,
    end_index: int,
    *,
    default_role: str,
) -> str:
    selected = list(paragraphs[start_index : end_index + 1])
    if selected and all(_is_toc_structural_role(paragraph) for paragraph in selected):
        return "toc"
    if selected and all(
        str(getattr(paragraph, "structural_role", "") or "").strip().lower() in {"epigraph", "attribution", "dedication", "body"}
        for paragraph in selected
    ) and start_index == 0:
        return "front_matter"
    return default_role


def _range_char_count(paragraphs: Sequence[ParagraphUnit], start_index: int, end_index: int) -> int:
    return sum(len(str(getattr(paragraphs[index], "text", "") or "")) for index in range(start_index, end_index + 1))


def _normalize_segment_title(text: str) -> str:
    normalized = _normalize_outline_text(text)
    if normalized:
        return normalized
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def _resolve_confidence(evidence: Sequence[SegmentBoundaryEvidence]) -> str:
    if any(item.confidence == "high" for item in evidence):
        return "high"
    if any(item.confidence == "medium" for item in evidence):
        return "medium"
    return "low"


def _has_typography_heading_signal(paragraph: ParagraphUnit, text: str) -> bool:
    normalized_text = str(text or "").strip()
    if not normalized_text or len(normalized_text) > 140:
        return False
    if bool(getattr(paragraph, "is_bold", False)):
        return True
    if str(getattr(paragraph, "paragraph_alignment", "") or "").strip().lower() == "center":
        return True
    font_size = getattr(paragraph, "font_size_pt", None)
    return isinstance(font_size, (int, float)) and float(font_size) >= 14.0


def _is_toc_structural_role(paragraph: ParagraphUnit) -> bool:
    return str(getattr(paragraph, "structural_role", "") or "").strip().lower() in {"toc_header", "toc_entry"}


def _resolve_paragraph_id(paragraph: ParagraphUnit, *, fallback_index: int) -> str:
    paragraph_id = str(getattr(paragraph, "paragraph_id", "") or "").strip()
    if paragraph_id:
        return paragraph_id
    source_index = getattr(paragraph, "source_index", -1)
    if isinstance(source_index, int) and source_index >= 0:
        return f"p{source_index:04d}"
    return f"p{fallback_index:04d}"


def _build_segment_id(
    *,
    ordinal: int,
    source_content_hash16: str,
    normalized_title: str,
    level: int,
    start_paragraph_id: str,
    end_paragraph_id: str,
    start_index: int,
    end_index: int,
    detector_version: str,
) -> str:
    payload = "|".join(
        [
            source_content_hash16,
            normalized_title,
            str(level),
            start_paragraph_id,
            end_paragraph_id,
            str(start_index),
            str(end_index),
            detector_version,
        ]
    )
    return f"seg_{ordinal:04d}_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:8]}"


def _build_boundary_fingerprint(
    *,
    normalized_title: str,
    level: int,
    start_paragraph_id: str,
    end_paragraph_id: str,
) -> str:
    payload = f"{normalized_title}|{level}|{start_paragraph_id}|{end_paragraph_id}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def _build_structure_fingerprint(segments: Sequence[DocumentSegment]) -> str:
    payload = "\n".join(
        f"{segment.segment_id}|{segment.level}|{segment.normalized_title}|{segment.start_paragraph_id}|{segment.end_paragraph_id}"
        for segment in segments
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
