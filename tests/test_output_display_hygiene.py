from docxaicorrector.pipeline.display_hygiene import collect_structure_quality_detector_samples, summarize_structure_quality_detectors


def test_collect_structure_quality_detector_samples_detects_all_five_pr1_detectors() -> None:
    markdown = """# Chapter One
# Chapter Two

# Introduction This begins the first sentence.

# -- T. S. Eliot

Body this page intentionally left blank Chapter Nine text.

Page 12
"""

    samples = collect_structure_quality_detector_samples(markdown)
    detector_ids = {sample.detector_id for sample in samples}

    assert detector_ids == {
        "pdf_blank_page_marker_leakage",
        "inline_page_furniture_leakage",
        "adjacent_h1_without_body",
        "heading_body_concat_detected",
        "h1_epigraph_attribution_pattern",
    }


def test_summarize_structure_quality_detectors_returns_counts_and_capped_samples() -> None:
    markdown = """# One
# Two

Body this page intentionally left blank Chapter Nine text.
"""

    counts, samples = summarize_structure_quality_detectors(markdown, max_samples_per_detector=1)

    assert counts["adjacent_h1_without_body"] == 1
    assert counts["pdf_blank_page_marker_leakage"] == 1
    assert counts["inline_page_furniture_leakage"] == 1
    assert len(samples["adjacent_h1_without_body"]) == 1
