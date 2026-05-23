from docxaicorrector.pipeline.display_hygiene import collect_structure_quality_detector_samples, summarize_structure_quality_detectors


def _samples_by_id(markdown: str) -> dict[str, list[object]]:
    grouped: dict[str, list[object]] = {}
    for sample in collect_structure_quality_detector_samples(markdown):
        grouped.setdefault(sample.detector_id, []).append(sample)
    return grouped


def test_collect_structure_quality_detector_samples_detects_spec_bounded_positive_shapes() -> None:
    markdown = """# Chapter One
# Chapter Two

# This heading contains far more than eighteen words, ends one sentence. then continues like body prose so the detector must flag it conservatively.

This page intentionally left blank

Introduction 12
Introduction 13
Introduction 14

“Stay hungry, stay foolish.”
# Steve Jobs, founder
"""

    samples_by_id = _samples_by_id(markdown)

    assert [sample.line for sample in samples_by_id["adjacent_h1_without_body"]] == [1, 2]
    assert samples_by_id["heading_body_concat_detected"][0].line == 4
    assert samples_by_id["heading_body_concat_detected"][0].reason == "heading_exceeds_closed_concat_threshold"
    assert samples_by_id["pdf_blank_page_marker_leakage"][0].line == 6
    assert samples_by_id["pdf_blank_page_marker_leakage"][0].reason == "blank_page_marker_visible_in_output"
    assert [sample.line for sample in samples_by_id["inline_page_furniture_leakage"]] == [8, 9, 10]
    assert all(
        sample.reason == "page_number_island_with_repeated_running_header_context"
        for sample in samples_by_id["inline_page_furniture_leakage"]
    )
    assert [sample.line for sample in samples_by_id["h1_epigraph_attribution_pattern"]] == [13]
    assert all(sample.text != "# Chapter One" for sample in samples_by_id["h1_epigraph_attribution_pattern"])
    assert all(sample.text != "# Chapter Two" for sample in samples_by_id["h1_epigraph_attribution_pattern"])


def test_collect_structure_quality_detector_samples_ignores_blank_markers_in_headings_code_and_blockquotes() -> None:
    markdown = """# This page intentionally left blank
> This page intentionally left blank
Inline `This page intentionally left blank` sample.

```md
This page intentionally left blank
Introduction 12
Introduction 13
Introduction 14
```
"""

    detector_ids = {sample.detector_id for sample in collect_structure_quality_detector_samples(markdown)}

    assert "pdf_blank_page_marker_leakage" not in detector_ids
    assert "inline_page_furniture_leakage" not in detector_ids


def test_collect_structure_quality_detector_samples_preserves_d4_and_d5_exclusions() -> None:
    markdown = """# Appendix A A Very Long Title With Many Words That Still Reads Like A Formal Heading Rather Than Body Prose In Markdown Output

# Chapter One

# Mark 13:13 A Long Scripture Style Heading Without Body Continuation And Without Sentence Punctuation In The Title Text
"""

    detector_ids = {sample.detector_id for sample in collect_structure_quality_detector_samples(markdown)}

    assert "heading_body_concat_detected" not in detector_ids
    assert "h1_epigraph_attribution_pattern" not in detector_ids


def test_summarize_structure_quality_detectors_returns_counts_and_capped_samples() -> None:
    markdown = """# Chapter One
# Chapter Two

This page intentionally left blank

Introduction 12
Introduction 13
Introduction 14
"""

    counts, samples = summarize_structure_quality_detectors(markdown, max_samples_per_detector=2)

    assert counts["adjacent_h1_without_body"] == 1
    assert counts["pdf_blank_page_marker_leakage"] == 1
    assert counts["inline_page_furniture_leakage"] == 3
    assert len(samples["inline_page_furniture_leakage"]) == 2
