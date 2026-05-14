from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Sequence

from docxaicorrector.core.models import ParagraphUnit

LAYOUT_SIGNALS_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class FontClusterTier:
    tier_id: int
    representative_pt: float
    member_logical_indexes: tuple[int, ...]
    is_body_baseline: bool
    is_heading_candidate: bool


@dataclass(frozen=True)
class LayoutSignalsRecord:
    logical_index: int
    tier_id: int
    is_heading_tier: bool
    is_body_tier: bool
    font_size_pt: float | None
    page_number: int | None
    vertical_gap_before_pt: float | None
    is_first_on_page: bool
    is_short_line: bool
    is_above_baseline: bool


@dataclass(frozen=True)
class LayoutSignals:
    schema_version: int
    body_baseline_pt: float | None
    body_baseline_tolerance_pt: float
    heading_ratio: float
    tiers: tuple[FontClusterTier, ...]
    records_by_logical_index: dict[int, LayoutSignalsRecord]

    def get(self, logical_index: int) -> LayoutSignalsRecord | None:
        return self.records_by_logical_index.get(logical_index)

    def is_same_heading_tier(self, a: int, b: int) -> bool:
        first = self.get(a)
        second = self.get(b)
        if first is None or second is None:
            return False
        return first.is_heading_tier and second.is_heading_tier and first.tier_id == second.tier_id

    def is_page_break_between(self, a: int, b: int) -> bool:
        first = self.get(a)
        second = self.get(b)
        if first is None or second is None:
            return False
        if first.page_number is None or second.page_number is None:
            return False
        return first.page_number != second.page_number


def derive_layout_signals(
    paragraphs: Sequence[ParagraphUnit],
    *,
    heading_ratio: float = 1.15,
    short_line_chars: int = 80,
    baseline_tolerance_pt: float = 0.25,
    min_tier_population: int = 2,
) -> LayoutSignals:
    qualifying_font_sizes = [
        rounded_size
        for paragraph in paragraphs
        if _qualifies_for_baseline(paragraph)
        for rounded_size in (_round_font_size(paragraph.font_size_pt),)
        if rounded_size is not None
    ]

    if len(qualifying_font_sizes) < 8:
        return LayoutSignals(
            schema_version=LAYOUT_SIGNALS_SCHEMA_VERSION,
            body_baseline_pt=None,
            body_baseline_tolerance_pt=baseline_tolerance_pt,
            heading_ratio=heading_ratio,
            tiers=(),
            records_by_logical_index=_build_degraded_records(
                paragraphs,
                short_line_chars=short_line_chars,
            ),
        )

    body_baseline_pt = _mode_font_size(qualifying_font_sizes)
    tiers, tier_id_by_rounded_size = _build_tiers(
        paragraphs,
        body_baseline_pt=body_baseline_pt,
        heading_ratio=heading_ratio,
        baseline_tolerance_pt=baseline_tolerance_pt,
        min_tier_population=min_tier_population,
    )
    records_by_logical_index = _build_records(
        paragraphs,
        body_baseline_pt=body_baseline_pt,
        heading_ratio=heading_ratio,
        baseline_tolerance_pt=baseline_tolerance_pt,
        short_line_chars=short_line_chars,
        tier_id_by_rounded_size=tier_id_by_rounded_size,
    )
    return LayoutSignals(
        schema_version=LAYOUT_SIGNALS_SCHEMA_VERSION,
        body_baseline_pt=body_baseline_pt,
        body_baseline_tolerance_pt=baseline_tolerance_pt,
        heading_ratio=heading_ratio,
        tiers=tiers,
        records_by_logical_index=records_by_logical_index,
    )


def _qualifies_for_baseline(paragraph: ParagraphUnit) -> bool:
    if paragraph.role in {"image", "table"}:
        return False
    if paragraph.is_likely_page_number or paragraph.is_repeated_across_pages:
        return False
    return paragraph.font_size_pt is not None and paragraph.font_size_pt > 0


def _round_font_size(font_size_pt: float | None) -> float | None:
    if font_size_pt is None or font_size_pt <= 0:
        return None
    return round(font_size_pt, 1)


def _mode_font_size(rounded_sizes: Sequence[float]) -> float:
    counts = Counter(rounded_sizes)
    max_count = max(counts.values())
    return min(size for size, count in counts.items() if count == max_count)


def _is_observed_page_hint_transition(previous_page_number: int | None, current_page_number: int | None) -> bool:
    return (
        previous_page_number is not None
        and current_page_number is not None
        and previous_page_number != current_page_number
    )


def _build_tiers(
    paragraphs: Sequence[ParagraphUnit],
    *,
    body_baseline_pt: float,
    heading_ratio: float,
    baseline_tolerance_pt: float,
    min_tier_population: int,
) -> tuple[tuple[FontClusterTier, ...], dict[float, int]]:
    body_members: list[int] = []
    above_baseline_members: dict[float, list[int]] = defaultdict(list)
    tier_id_by_rounded_size: dict[float, int] = {}

    for paragraph in paragraphs:
        rounded_size = _round_font_size(paragraph.font_size_pt)
        if rounded_size is None:
            continue
        if abs(paragraph.font_size_pt - body_baseline_pt) <= baseline_tolerance_pt:
            body_members.append(paragraph.logical_index)
            tier_id_by_rounded_size[rounded_size] = 0
            continue
        if paragraph.font_size_pt > body_baseline_pt + baseline_tolerance_pt:
            above_baseline_members[rounded_size].append(paragraph.logical_index)

    tiers: list[FontClusterTier] = [
        FontClusterTier(
            tier_id=0,
            representative_pt=body_baseline_pt,
            member_logical_indexes=tuple(body_members),
            is_body_baseline=True,
            is_heading_candidate=False,
        )
    ]

    sorted_above_sizes = sorted(above_baseline_members, reverse=True)
    next_tier_id = 1
    largest_above_size = sorted_above_sizes[0] if sorted_above_sizes else None
    for rounded_size in sorted_above_sizes:
        members = above_baseline_members[rounded_size]
        keep_tier = len(members) >= min_tier_population or rounded_size == largest_above_size
        if not keep_tier:
            continue
        tier_id_by_rounded_size[rounded_size] = next_tier_id
        tiers.append(
            FontClusterTier(
                tier_id=next_tier_id,
                representative_pt=rounded_size,
                member_logical_indexes=tuple(members),
                is_body_baseline=False,
                is_heading_candidate=rounded_size >= body_baseline_pt * heading_ratio,
            )
        )
        next_tier_id += 1

    return tuple(tiers), tier_id_by_rounded_size


def _build_records(
    paragraphs: Sequence[ParagraphUnit],
    *,
    body_baseline_pt: float,
    heading_ratio: float,
    baseline_tolerance_pt: float,
    short_line_chars: int,
    tier_id_by_rounded_size: dict[float, int],
) -> dict[int, LayoutSignalsRecord]:
    records_by_logical_index: dict[int, LayoutSignalsRecord] = {}

    for offset, paragraph in enumerate(paragraphs):
        rounded_size = _round_font_size(paragraph.font_size_pt)
        tier_id = -1
        if rounded_size is not None:
            if abs(paragraph.font_size_pt - body_baseline_pt) <= baseline_tolerance_pt:
                tier_id = 0
            elif paragraph.font_size_pt > body_baseline_pt + baseline_tolerance_pt:
                tier_id = tier_id_by_rounded_size.get(rounded_size, -1)

        representative_pt = body_baseline_pt if tier_id == 0 else rounded_size
        is_body_tier = tier_id == 0
        is_heading_tier = (
            tier_id > 0
            and representative_pt is not None
            and representative_pt >= body_baseline_pt * heading_ratio
        )
        previous_page_number = paragraphs[offset - 1].page_number if offset > 0 else None
        is_first_on_page = _is_observed_page_hint_transition(previous_page_number, paragraph.page_number)
        is_above_baseline = (
            paragraph.font_size_pt is not None
            and paragraph.font_size_pt > body_baseline_pt + baseline_tolerance_pt
        )
        records_by_logical_index[paragraph.logical_index] = LayoutSignalsRecord(
            logical_index=paragraph.logical_index,
            tier_id=tier_id,
            is_heading_tier=is_heading_tier,
            is_body_tier=is_body_tier,
            font_size_pt=paragraph.font_size_pt,
            page_number=paragraph.page_number,
            vertical_gap_before_pt=paragraph.vertical_gap_before_pt,
            is_first_on_page=is_first_on_page,
            is_short_line=len(paragraph.text.strip()) <= short_line_chars,
            is_above_baseline=is_above_baseline,
        )

    return records_by_logical_index


def _build_degraded_records(
    paragraphs: Sequence[ParagraphUnit],
    *,
    short_line_chars: int,
) -> dict[int, LayoutSignalsRecord]:
    records_by_logical_index: dict[int, LayoutSignalsRecord] = {}

    for offset, paragraph in enumerate(paragraphs):
        previous_page_number = paragraphs[offset - 1].page_number if offset > 0 else None
        is_first_on_page = _is_observed_page_hint_transition(previous_page_number, paragraph.page_number)
        records_by_logical_index[paragraph.logical_index] = LayoutSignalsRecord(
            logical_index=paragraph.logical_index,
            tier_id=-1,
            is_heading_tier=False,
            is_body_tier=False,
            font_size_pt=paragraph.font_size_pt,
            page_number=paragraph.page_number,
            vertical_gap_before_pt=paragraph.vertical_gap_before_pt,
            is_first_on_page=is_first_on_page,
            is_short_line=len(paragraph.text.strip()) <= short_line_chars,
            is_above_baseline=False,
        )

    return records_by_logical_index