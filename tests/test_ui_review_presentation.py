"""Tests for the formatting-review presenter and the result-screen review block."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from streamlit.testing.v1 import AppTest

from docxaicorrector.ui import i18n
from docxaicorrector.ui.review_presentation import ReviewPresentation, build_review_presentation


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    i18n.clear_catalog_cache()
    yield
    i18n.clear_catalog_cache()


# --- Pure presenter -------------------------------------------------------


def test_clean_when_quality_warning_is_none() -> None:
    presentation = build_review_presentation(None)
    assert isinstance(presentation, ReviewPresentation)
    assert presentation.level == "clean"
    assert presentation.counts == {"defect": 0, "fix": 0, "review": 0}
    assert presentation.review_available is False
    assert presentation.headline == i18n.t("result.notice_clean")


def test_clean_when_no_items() -> None:
    presentation = build_review_presentation({"quality_status": "warn", "formatting_review_items": []})
    assert presentation.level == "clean"
    # A present warning keeps the report downloadable even with no counted items.
    assert presentation.review_available is True


def test_review_level_and_headline() -> None:
    presentation = build_review_presentation(
        {"formatting_review_items": [{"severity": "review", "label": "x", "sample": {"text": "a"}}]}
    )
    assert presentation.level == "review"
    assert presentation.counts == {"defect": 0, "fix": 0, "review": 1}
    assert presentation.headline == i18n.t("result.notice_review", count=1)


def test_fix_outranks_review() -> None:
    presentation = build_review_presentation(
        {
            "formatting_review_items": [
                {"severity": "review", "label": "x", "sample": {"text": "a"}},
                {"severity": "fix", "label": "y", "sample": {"text": "b"}},
            ]
        }
    )
    assert presentation.level == "fix"
    assert presentation.counts == {"defect": 0, "fix": 1, "review": 1}
    assert presentation.headline == i18n.t("result.notice_fix", count=1)


def test_defect_outranks_everything() -> None:
    presentation = build_review_presentation(
        {
            "formatting_review_items": [
                {"severity": "review", "label": "x", "sample": {"text": "a"}},
                {"severity": "fix", "label": "y", "sample": {"text": "b"}},
                {"severity": "defect", "label": "z", "sample": {"text": "c"}},
            ]
        }
    )
    assert presentation.level == "defect"
    assert presentation.counts == {"defect": 1, "fix": 1, "review": 1}
    assert presentation.headline == i18n.t("result.notice_defect", count=1)


def test_counts_honor_aggregate_count() -> None:
    # aggregate_count wins over count, mirroring the writer's totals logic.
    presentation = build_review_presentation(
        {
            "formatting_review_items": [
                {"severity": "defect", "aggregate_count": 5, "count": 0, "sample": {"text": "a"}},
                {"severity": "defect", "count": 0, "sample": {"text": "b"}},
            ]
        }
    )
    assert presentation.counts["defect"] == 5
    assert presentation.level == "defect"
    assert presentation.headline == i18n.t("result.notice_defect", count=5)


def test_unknown_severity_falls_back_to_review() -> None:
    presentation = build_review_presentation(
        {"formatting_review_items": [{"severity": "weird", "count": 2, "sample": {"text": "a"}}]}
    )
    assert presentation.counts == {"defect": 0, "fix": 0, "review": 2}
    assert presentation.level == "review"


# --- Streamlit render block (headless AppTest) ----------------------------


# AppTest.from_function needs inspect.getsource, which fails under the pytest runner
# ("could not get source code"); use from_string with self-contained scripts instead.
_SCRIPT_FIX = """
from docxaicorrector.ui._ui import render_result_bundle

render_result_bundle(
    docx_bytes=b"docx",
    markdown_text="# body",
    original_filename="report.docx",
    processing_operation="edit",
    success_message="Документ обработан.",
    quality_warning={
        "quality_status": "warn",
        "formatting_review_items": [
            {"severity": "fix", "label": "Заголовок стал обычным текстом", "sample": {"text": "Глава 1"}},
        ],
    },
)
"""

_SCRIPT_REVIEW = """
from docxaicorrector.ui._ui import render_result_bundle

render_result_bundle(
    docx_bytes=b"docx",
    markdown_text="# body",
    original_filename="report.docx",
    processing_operation="edit",
    success_message="Документ обработан.",
    quality_warning={
        "quality_status": "warn",
        "formatting_review_items": [
            {"severity": "review", "label": "Абзац без соответствия", "sample": {"text": "abc"}},
        ],
    },
)
"""

_SCRIPT_CLEAN = """
from docxaicorrector.ui._ui import render_result_bundle

render_result_bundle(
    docx_bytes=b"docx",
    markdown_text="# body",
    original_filename="report.docx",
    processing_operation="edit",
    success_message="Документ обработан.",
)
"""


def test_apptest_fix_renders_notice_counts_and_review_download() -> None:
    at = AppTest.from_string(_SCRIPT_FIX).run()

    # Notice via st.warning (fix level).
    warnings = [w.value for w in at.warning]
    assert any("нужна ручная правка" in text for text in warnings)

    # Counts line honoring severity markers.
    captions = [c.value for c in at.caption]
    assert any("[КРИТ] 0 · [ПРАВКА] 1 · [ПРОВЕРКА] 0" in text for text in captions)

    labels = [str(getattr(btn, "label", "")) for btn in at.get("download_button")]
    # DOCX download is still present alongside the new review download.
    assert "Отредактированный DOCX" in labels
    assert "Скачать отчёт проверки" in labels


def test_apptest_review_shows_accepted_reassurance_note() -> None:
    at = AppTest.from_string(_SCRIPT_REVIEW).run()

    infos = [i.value for i in at.info]
    assert any("стоит проверить" in text for text in infos)
    captions = [c.value for c in at.caption]
    assert any(i18n.t("result.review_accepted_note") == text for text in captions)


def test_apptest_clean_run_has_no_review_block() -> None:
    at = AppTest.from_string(_SCRIPT_CLEAN).run()

    assert list(at.warning) == []
    assert list(at.info) == []
    assert list(at.error) == []
    labels = [str(getattr(btn, "label", "")) for btn in at.get("download_button")]
    assert "Отредактированный DOCX" in labels
    assert "Скачать отчёт проверки" not in labels
