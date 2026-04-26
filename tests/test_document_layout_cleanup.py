import time

import document_layout_cleanup
from document_layout_cleanup import clean_paragraph_layout_artifacts, normalize_layout_artifact_text
from models import ParagraphUnit


def _paragraph(text: str, *, role: str = "body", structural_role: str = "body", source_index: int = 0, list_kind: str | None = None) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role=role,
        structural_role=structural_role,
        source_index=source_index,
        paragraph_id=f"p{source_index:04d}",
        list_kind=list_kind,
        origin_raw_indexes=[source_index],
    )


def test_removes_standalone_page_numbers_and_keeps_guardrails():
    paragraphs = [
        _paragraph("1", source_index=0),
        _paragraph("- 12 -", source_index=1),
        _paragraph("Page 4", source_index=2),
        _paragraph("стр. 5", source_index=3),
        _paragraph("12 / 40", source_index=4),
        _paragraph("Chapter 12", source_index=5),
        _paragraph("1. Real item", role="list", structural_role="list", source_index=6, list_kind="ordered"),
        _paragraph("Introduction........4", structural_role="toc_entry", source_index=7),
    ]

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert [paragraph.text for paragraph in cleaned] == ["Chapter 12", "1. Real item", "Introduction........4"]
    assert report.removed_page_number_count == 5
    assert report.removed_paragraph_count == 5
    assert {decision.reason for decision in report.decisions if decision.action == "remove"} == {"page_number_pattern"}


def test_removes_repeated_safe_artifacts_but_keeps_prose_and_low_repeat():
    paragraphs = [
        _paragraph("Are We In the End Times?", role="heading", structural_role="heading", source_index=0),
        _paragraph("Real body one.", source_index=1),
        _paragraph("www.example.com", source_index=2),
        _paragraph("www.example.com", source_index=3),
        _paragraph("www.example.com", source_index=4),
        _paragraph("Confidential", source_index=5),
        _paragraph("Confidential", source_index=6),
        _paragraph("Confidential", source_index=7),
        _paragraph("Are We In the End Times?", source_index=8),
        _paragraph("Are We In the End Times?", source_index=9),
        _paragraph("Are We In the End Times?", source_index=10),
        _paragraph("To be or not to be.", source_index=11),
        _paragraph("To be or not to be.", source_index=12),
        _paragraph("To be or not to be.", source_index=13),
        _paragraph("Introduction", source_index=14),
        _paragraph("Introduction", source_index=15),
    ]

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    cleaned_texts = [paragraph.text for paragraph in cleaned]
    assert cleaned_texts.count("www.example.com") == 0
    assert cleaned_texts.count("Confidential") == 0
    assert cleaned_texts.count("Are We In the End Times?") == 1
    assert cleaned_texts.count("To be or not to be.") == 3
    assert cleaned_texts.count("Introduction") == 2
    assert report.removed_repeated_artifact_count == 9
    assert {decision.reason for decision in report.decisions if decision.action == "remove"} == {
        "repeated_url_footer",
        "repeated_boilerplate_token",
        "repeated_title_header",
    }


def test_disabled_mode_returns_original_list_and_report():
    paragraphs = [_paragraph("1")]

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs, enabled=False)

    assert cleaned is paragraphs
    assert report.cleanup_applied is False
    assert report.skipped_reason == "disabled"
    assert report.removed_paragraph_count == 0


def test_fail_open_when_internal_cleanup_raises(monkeypatch):
    paragraphs = [_paragraph("1")]

    def raise_error(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(document_layout_cleanup, "_clean_paragraph_layout_artifacts", raise_error)

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert cleaned is paragraphs
    assert report.cleanup_applied is False
    assert report.skipped_reason == "cleanup_failed"
    assert report.error_code == "cleanup_runtime_error"


def test_protected_structural_whitespace_is_preserved():
    paragraphs = [
        _paragraph("   ", structural_role="epigraph", source_index=0),
        _paragraph("1", source_index=1),
    ]

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert [paragraph.structural_role for paragraph in cleaned] == ["epigraph"]
    assert cleaned[0].text == "   "
    assert report.removed_paragraph_count == 1
    assert report.removed_empty_or_whitespace_count == 0


def test_language_neutral_cleanup_keeps_unsupported_short_repetition():
    paragraphs = [
        _paragraph("www.example.com", source_index=0),
        _paragraph("www.example.com", source_index=1),
        _paragraph("www.example.com", source_index=2),
        _paragraph("未知标题", source_index=3),
        _paragraph("未知标题", source_index=4),
        _paragraph("未知标题", source_index=5),
    ]

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert [paragraph.text for paragraph in cleaned] == ["未知标题", "未知标题", "未知标题"]
    assert report.removed_repeated_artifact_count == 3


def test_normalization_and_large_input_are_linear_style():
    assert normalize_layout_artifact_text(" **Draft** ") == "draft"
    paragraphs = [_paragraph(f"Content {index}.", source_index=index) for index in range(10_000)]
    paragraphs.extend(_paragraph("www.example.com", source_index=10_000 + index) for index in range(5))

    started = time.perf_counter()
    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)
    elapsed = time.perf_counter() - started

    assert len(cleaned) == 10_000
    assert report.removed_repeated_artifact_count == 5
    assert elapsed < 2.0
