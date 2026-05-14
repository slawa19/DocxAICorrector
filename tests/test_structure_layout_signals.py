from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.structure.layout_signals import LAYOUT_SIGNALS_SCHEMA_VERSION, derive_layout_signals


def _paragraph(
    logical_index: int,
    text: str,
    *,
    font_size_pt: float | None = None,
    page_number: int | None = None,
    vertical_gap_before_pt: float | None = None,
    role: str = "body",
    is_likely_page_number: bool = False,
    is_repeated_across_pages: bool = False,
) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role=role,
        structural_role="body",
        source_index=logical_index,
        logical_index=logical_index,
        font_size_pt=font_size_pt,
        page_number=page_number,
        vertical_gap_before_pt=vertical_gap_before_pt,
        is_likely_page_number=is_likely_page_number,
        is_repeated_across_pages=is_repeated_across_pages,
    )


def test_derive_layout_signals_returns_empty_degraded_payload_for_empty_input():
    signals = derive_layout_signals([])

    assert signals.schema_version == LAYOUT_SIGNALS_SCHEMA_VERSION
    assert signals.body_baseline_pt is None
    assert signals.tiers == ()
    assert signals.records_by_logical_index == {}


def test_derive_layout_signals_degrades_when_too_few_qualifying_paragraphs():
    paragraphs = [
        _paragraph(0, "Visible heading", font_size_pt=18.0, page_number=1),
        _paragraph(1, "Regular body one", font_size_pt=12.0, page_number=1),
        _paragraph(2, "Regular body two", font_size_pt=12.0, page_number=1),
        _paragraph(3, "12", font_size_pt=30.0, page_number=1, is_likely_page_number=True),
        _paragraph(4, "Repeated footer", font_size_pt=9.0, page_number=1, is_repeated_across_pages=True),
        _paragraph(5, "Missing font paragraph", font_size_pt=None, page_number=2),
        _paragraph(6, "Inline emphasis", font_size_pt=11.5, page_number=2),
    ]

    signals = derive_layout_signals(paragraphs)

    assert signals.body_baseline_pt is None
    assert signals.tiers == ()
    assert set(signals.records_by_logical_index) == {0, 1, 2, 3, 4, 5, 6}
    assert all(record.tier_id == -1 for record in signals.records_by_logical_index.values())
    assert all(record.is_heading_tier is False for record in signals.records_by_logical_index.values())
    assert all(record.is_body_tier is False for record in signals.records_by_logical_index.values())
    assert all(record.is_above_baseline is False for record in signals.records_by_logical_index.values())
    assert signals.get(5).font_size_pt is None


def test_derive_layout_signals_uses_mode_of_rounded_font_sizes_with_smallest_tie_breaker():
    paragraphs = [
        _paragraph(0, "Body 1", font_size_pt=11.96),
        _paragraph(1, "Body 2", font_size_pt=12.04),
        _paragraph(2, "Body 3", font_size_pt=12.0),
        _paragraph(3, "Body 4", font_size_pt=12.02),
        _paragraph(4, "Alt 1", font_size_pt=12.96),
        _paragraph(5, "Alt 2", font_size_pt=12.98),
        _paragraph(6, "Alt 3", font_size_pt=13.01),
        _paragraph(7, "Alt 4", font_size_pt=13.04),
    ]

    signals = derive_layout_signals(paragraphs)

    assert signals.body_baseline_pt == 12.0
    assert signals.tiers[0].tier_id == 0
    assert signals.tiers[0].representative_pt == 12.0


def test_derive_layout_signals_detects_body_and_heading_tiers_in_mixed_font_document():
    paragraphs = [
        _paragraph(0, "Chapter Eleven", font_size_pt=18.0, page_number=1, vertical_gap_before_pt=30.0),
        _paragraph(1, "An Ancient Future?", font_size_pt=18.0, page_number=1, vertical_gap_before_pt=6.0),
        _paragraph(2, "Body paragraph one.", font_size_pt=12.0, page_number=1, vertical_gap_before_pt=12.0),
        _paragraph(3, "Body paragraph two.", font_size_pt=12.0, page_number=1, vertical_gap_before_pt=8.0),
        _paragraph(4, "Body paragraph three.", font_size_pt=12.0, page_number=1),
        _paragraph(5, "Body paragraph four.", font_size_pt=12.0, page_number=2),
        _paragraph(6, "Body paragraph five.", font_size_pt=12.0, page_number=2),
        _paragraph(7, "Body paragraph six.", font_size_pt=12.0, page_number=2),
        _paragraph(8, "Body paragraph seven.", font_size_pt=12.0, page_number=2),
        _paragraph(9, "Body paragraph eight.", font_size_pt=12.0, page_number=2),
    ]

    signals = derive_layout_signals(paragraphs)

    assert signals.body_baseline_pt == 12.0
    assert signals.tiers[0].tier_id == 0
    assert signals.tiers[0].is_body_baseline is True
    assert signals.tiers[1].representative_pt == 18.0
    assert signals.tiers[1].is_heading_candidate is True
    assert signals.get(0).is_heading_tier is True
    assert signals.get(0).tier_id == 1
    assert signals.get(2).is_body_tier is True
    assert signals.get(2).tier_id == 0


def test_derive_layout_signals_preserves_only_largest_sparse_above_baseline_tier():
    paragraphs = [
        _paragraph(0, "Book Title", font_size_pt=20.0, page_number=1),
        _paragraph(1, "Sparse emphasized line", font_size_pt=16.0, page_number=1),
        _paragraph(2, "Body one", font_size_pt=12.0, page_number=1),
        _paragraph(3, "Body two", font_size_pt=12.0, page_number=1),
        _paragraph(4, "Body three", font_size_pt=12.0, page_number=1),
        _paragraph(5, "Body four", font_size_pt=12.0, page_number=1),
        _paragraph(6, "Body five", font_size_pt=12.0, page_number=1),
        _paragraph(7, "Body six", font_size_pt=12.0, page_number=1),
        _paragraph(8, "Body seven", font_size_pt=12.0, page_number=1),
        _paragraph(9, "Body eight", font_size_pt=12.0, page_number=1),
    ]

    signals = derive_layout_signals(paragraphs, min_tier_population=2)

    assert [tier.representative_pt for tier in signals.tiers] == [12.0, 20.0]
    assert signals.get(0).is_heading_tier is True
    assert signals.get(0).tier_id == 1
    assert signals.get(1).tier_id == -1
    assert signals.get(1).is_heading_tier is False


def test_is_same_heading_tier_requires_matching_heading_records():
    paragraphs = [
        _paragraph(0, "Part I", font_size_pt=18.0, page_number=1),
        _paragraph(1, "Origins", font_size_pt=18.0, page_number=1),
        _paragraph(2, "Body one", font_size_pt=12.0, page_number=1),
        _paragraph(3, "Body two", font_size_pt=12.0, page_number=1),
        _paragraph(4, "Body three", font_size_pt=12.0, page_number=1),
        _paragraph(5, "Body four", font_size_pt=12.0, page_number=1),
        _paragraph(6, "Body five", font_size_pt=12.0, page_number=1),
        _paragraph(7, "Body six", font_size_pt=12.0, page_number=1),
        _paragraph(8, "No font", font_size_pt=None, page_number=1),
        _paragraph(9, "Body seven", font_size_pt=12.0, page_number=1),
    ]

    signals = derive_layout_signals(paragraphs)

    assert signals.is_same_heading_tier(0, 1) is True
    assert signals.is_same_heading_tier(0, 8) is False
    assert signals.is_same_heading_tier(0, 2) is False


def test_is_page_break_between_requires_both_page_numbers_and_different_pages():
    paragraphs = [
        _paragraph(0, "Heading", font_size_pt=18.0, page_number=1),
        _paragraph(1, "Body one", font_size_pt=12.0, page_number=1),
        _paragraph(2, "Body two", font_size_pt=12.0, page_number=1),
        _paragraph(3, "Body three", font_size_pt=12.0, page_number=2),
        _paragraph(4, "Body four", font_size_pt=12.0, page_number=2),
        _paragraph(5, "Body five", font_size_pt=12.0, page_number=None),
        _paragraph(6, "Body six", font_size_pt=12.0, page_number=2),
        _paragraph(7, "Body seven", font_size_pt=12.0, page_number=2),
    ]

    signals = derive_layout_signals(paragraphs)

    assert signals.is_page_break_between(1, 2) is False
    assert signals.is_page_break_between(1, 3) is True
    assert signals.is_page_break_between(3, 5) is False


def test_records_capture_short_line_first_on_page_and_above_baseline_flags():
    paragraphs = [
        _paragraph(0, "Short title", font_size_pt=18.0, page_number=1, vertical_gap_before_pt=24.0),
        _paragraph(1, "Body paragraph one.", font_size_pt=12.0, page_number=1),
        _paragraph(2, "Body paragraph two.", font_size_pt=12.0, page_number=1),
        _paragraph(3, "Body paragraph three.", font_size_pt=12.0, page_number=1),
        _paragraph(4, "Body paragraph four.", font_size_pt=12.0, page_number=1),
        _paragraph(5, "Body paragraph five.", font_size_pt=12.0, page_number=1),
        _paragraph(6, "Body paragraph six.", font_size_pt=12.0, page_number=1),
        _paragraph(
            7,
            "This is a deliberately long body paragraph that exceeds the short-line threshold by a comfortable margin.",
            font_size_pt=12.2,
            page_number=2,
        ),
    ]

    signals = derive_layout_signals(paragraphs, baseline_tolerance_pt=0.25, short_line_chars=80)

    title_record = signals.get(0)
    long_body_record = signals.get(7)
    new_page_record = signals.get(7)
    near_body_record = signals.get(1)

    assert title_record.is_short_line is True
    assert title_record.is_above_baseline is True
    assert long_body_record.is_short_line is False
    assert long_body_record.is_above_baseline is False
    assert new_page_record.is_first_on_page is True
    assert near_body_record.is_above_baseline is False