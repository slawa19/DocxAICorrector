import inspect
import time

import docxaicorrector.document.layout_cleanup as document_layout_cleanup
from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.document.layout_cleanup import clean_paragraph_layout_artifacts, normalize_layout_artifact_text


def _paragraph(
    text: str,
    *,
    role: str = "body",
    structural_role: str = "body",
    source_index: int = 0,
    list_kind: str | None = None,
    layout_origin: str = "paragraph",
) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role=role,
        structural_role=structural_role,
        source_index=source_index,
        paragraph_id=f"p{source_index:04d}",
        list_kind=list_kind,
        layout_origin=layout_origin,
        origin_raw_indexes=[source_index],
    )


def _document_with_recurring_block(
    *,
    block_text: str,
    stride: int,
    paragraph_count: int,
    block_role: str = "body",
    block_structural_role: str = "body",
    block_layout_origin: str = "paragraph",
    first_position: int = 0,
    last_position: int | None = None,
) -> list[ParagraphUnit]:
    """A synthetic book whose only repetition is ``block_text`` every ``stride`` units."""
    limit = paragraph_count if last_position is None else last_position
    positions = set(range(first_position, limit, stride))
    paragraphs: list[ParagraphUnit] = []
    for index in range(paragraph_count):
        if index in positions:
            paragraphs.append(
                _paragraph(
                    block_text,
                    role=block_role,
                    structural_role=block_structural_role,
                    layout_origin=block_layout_origin,
                    source_index=index,
                )
            )
        else:
            paragraphs.append(_paragraph(f"Unique body sentence number {index}.", source_index=index))
    return paragraphs


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

    assert [paragraph.text for paragraph in cleaned] == [
        "1",
        "- 12 -",
        "Page 4",
        "стр. 5",
        "12 / 40",
        "Chapter 12",
        "1. Real item",
        "Introduction........4",
    ]
    assert report.cleanup_mode == "flag"
    assert report.flagged_page_number_count == 5
    assert report.removed_page_number_count == 0
    assert report.removed_paragraph_count == 0
    assert {decision.reason for decision in report.decisions if decision.action == "flag"} == {"page_number_pattern"}


def test_ai_first_signal_mode_flags_page_numbers_without_removing_paragraphs():
    paragraphs = [
        _paragraph("1", source_index=0),
        _paragraph("Page 4", source_index=1),
        _paragraph("Chapter 12", source_index=2),
    ]

    cleaned, report = clean_paragraph_layout_artifacts(
        paragraphs,
        structure_recovery_enabled=True,
        structure_recovery_mode="ai_first",
    )

    assert [paragraph.text for paragraph in cleaned] == ["1", "Page 4", "Chapter 12"]
    assert report.cleanup_mode == "flag"
    assert report.cleaned_paragraph_count == 3
    assert report.removed_paragraph_count == 0
    assert report.flagged_page_number_count == 2
    assert cleaned[0].is_likely_page_number is True
    assert cleaned[1].is_likely_page_number is True
    assert cleaned[2].is_likely_page_number is False
    assert {decision.action for decision in report.decisions[:2]} == {"flag"}


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
    assert cleaned_texts.count("www.example.com") == 3
    assert cleaned_texts.count("Confidential") == 3
    assert cleaned_texts.count("Are We In the End Times?") == 4
    assert cleaned_texts.count("To be or not to be.") == 3
    assert cleaned_texts.count("Introduction") == 2
    assert report.cleanup_mode == "flag"
    assert report.flagged_repeated_artifact_count == 9
    assert report.removed_repeated_artifact_count == 0
    assert {decision.reason for decision in report.decisions if decision.action == "flag"} == {
        "repeated_url_footer",
        "repeated_boilerplate_token",
        "repeated_title_header",
    }


def test_ai_first_signal_mode_flags_repeated_artifacts_without_removal():
    paragraphs = [
        _paragraph("Are We In the End Times?", role="heading", structural_role="heading", source_index=0),
        _paragraph("www.example.com", source_index=1),
        _paragraph("www.example.com", source_index=2),
        _paragraph("www.example.com", source_index=3),
    ]

    cleaned, report = clean_paragraph_layout_artifacts(
        paragraphs,
        structure_recovery_enabled=True,
        structure_recovery_mode="ai_first",
    )

    assert [paragraph.text for paragraph in cleaned] == [
        "Are We In the End Times?",
        "www.example.com",
        "www.example.com",
        "www.example.com",
    ]
    assert report.cleanup_mode == "flag"
    assert report.flagged_repeated_artifact_count == 3
    assert report.removed_repeated_artifact_count == 0
    assert [paragraph.is_repeated_across_pages for paragraph in cleaned] == [False, True, True, True]
    assert {decision.action for decision in report.decisions[1:]} == {"flag"}


def test_remove_mode_removes_high_confidence_source_artifacts_and_preserves_semantic_text():
    paragraphs = [
        _paragraph("1", source_index=0),
        _paragraph("This page intentionally left blank", source_index=1),
        _paragraph("[[DOCX_IMAGE_img_001]]", source_index=2),
        _paragraph("Real body paragraph.", source_index=3),
        _paragraph("Introduction", source_index=4),
        _paragraph("Introduction", source_index=5),
    ]

    cleaned, report = clean_paragraph_layout_artifacts(
        paragraphs,
        cleanup_mode="remove",
        min_repeat_count=3,
    )

    assert [paragraph.text for paragraph in cleaned] == [
        "Real body paragraph.",
        "Introduction",
        "Introduction",
    ]
    assert report.cleanup_mode == "remove"
    assert report.removed_page_number_count == 1
    assert report.removed_repeated_artifact_count == 2
    assert report.removed_paragraph_count == 3
    removed_reasons = {decision.reason for decision in report.decisions if decision.action == "remove"}
    assert removed_reasons == {"page_number_pattern", "blank_page_marker", "extraction_artifact"}


def test_keeps_uncertain_repeated_artifact_examples_for_review():
    paragraphs = [
        _paragraph("Introduction", source_index=0),
        _paragraph("Introduction", source_index=1),
        _paragraph("Real body paragraph.", source_index=2),
    ]

    cleaned, report = clean_paragraph_layout_artifacts(
        paragraphs,
        cleanup_mode="remove",
        min_repeat_count=3,
    )

    assert [paragraph.text for paragraph in cleaned] == [
        "Introduction",
        "Introduction",
        "Real body paragraph.",
    ]
    uncertain = [decision for decision in report.decisions if decision.reason == "uncertain_repeated_artifact"]
    assert len(uncertain) == 2
    assert {decision.confidence for decision in uncertain} == {"low"}


def test_disabled_mode_returns_original_list_and_report():
    paragraphs = [_paragraph("1")]

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs, enabled=False)

    assert cleaned is paragraphs
    assert report.cleanup_applied is False
    assert report.skipped_reason == "disabled"
    assert report.removed_paragraph_count == 0


def test_disabled_mode_emits_structured_outcome_log(monkeypatch):
    paragraphs = [_paragraph("1")]
    logged_reports = []

    monkeypatch.setattr(document_layout_cleanup, "_log_cleanup_outcome", lambda report, **kwargs: logged_reports.append(report))

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs, enabled=False)

    assert cleaned is paragraphs
    assert logged_reports == [report]


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


def test_repeated_cleanup_does_not_remove_non_candidate_terminal_paragraphs():
    paragraphs = [
        _paragraph("www.example.com", source_index=0),
        _paragraph("www.example.com", source_index=1),
        _paragraph("www.example.com", source_index=2),
        _paragraph("www.example.com.", source_index=3),
    ]

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert [paragraph.text for paragraph in cleaned] == [
        "www.example.com",
        "www.example.com",
        "www.example.com",
        "www.example.com.",
    ]
    assert report.flagged_repeated_artifact_count == 3
    assert report.removed_repeated_artifact_count == 0
    assert report.decisions[3].action == "keep"
    assert report.decisions[3].reason == "keep"


def test_repeated_title_header_uses_medium_confidence_in_report():
    paragraphs = [
        _paragraph("Are We In the End Times?", role="heading", structural_role="heading", source_index=0),
        _paragraph("Are We In the End Times?", source_index=1),
        _paragraph("Are We In the End Times?", source_index=2),
        _paragraph("Are We In the End Times?", source_index=3),
    ]

    _cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    removed_decisions = [decision for decision in report.decisions if decision.reason == "repeated_title_header"]
    assert removed_decisions
    assert {decision.confidence for decision in removed_decisions} == {"medium"}


def test_protected_structural_whitespace_is_preserved():
    paragraphs = [
        _paragraph("   ", structural_role="epigraph", source_index=0),
        _paragraph("1", source_index=1),
    ]

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert [paragraph.structural_role for paragraph in cleaned] == ["epigraph", "body"]
    assert cleaned[0].text == "   "
    assert report.flagged_page_number_count == 1
    assert report.removed_paragraph_count == 0
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

    assert [paragraph.text for paragraph in cleaned] == [
        "www.example.com",
        "www.example.com",
        "www.example.com",
        "未知标题",
        "未知标题",
        "未知标题",
    ]
    assert report.flagged_repeated_artifact_count == 3
    assert report.removed_repeated_artifact_count == 0


def test_page_cadence_stamp_is_removed_even_in_default_flag_mode():
    """Spec 017: a stamp recurring once per page is furniture, not content.

    The block is deliberately a nonsense token: the rule must key on cadence, never on
    the word (Constitution VII). It arrives with ``role="heading"`` and
    ``layout_origin="paragraph"`` — the two gates that made the real OCR stamp survive.
    """
    paragraphs = _document_with_recurring_block(
        block_text="QX-4471",
        stride=10,
        paragraph_count=400,
        block_role="heading",
        block_structural_role="heading",
    )

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert report.cleanup_mode == "flag"
    assert "QX-4471" not in [paragraph.text for paragraph in cleaned]
    assert report.removed_page_furniture_count == 40
    assert report.removed_paragraph_count == 40
    assert report.cleaned_paragraph_count == 360
    assert len(cleaned) == 360
    furniture_decisions = [
        decision for decision in report.decisions if decision.reason == "repeated_page_furniture"
    ]
    assert len(furniture_decisions) == 40
    assert {decision.action for decision in furniture_decisions} == {"remove"}
    assert {decision.confidence for decision in furniture_decisions} == {"high"}
    # Everything that is not the stamp survives untouched.
    assert [paragraph.text for paragraph in cleaned if paragraph.text.startswith("Unique")] == [
        paragraph.text for paragraph in paragraphs if paragraph.text.startswith("Unique")
    ]


def test_page_cadence_furniture_is_detected_regardless_of_role_and_layout_origin():
    """The import accident (textbox vs paragraph, heading vs caption) is not evidence."""
    for role, structural_role, layout_origin in (
        ("body", "body", "paragraph"),
        ("body", "body", "textbox"),
        ("heading", "heading", "paragraph"),
        ("heading", "toc_entry", "textbox"),
        ("caption", "caption", "textbox"),
    ):
        paragraphs = _document_with_recurring_block(
            block_text="QX-4471",
            stride=12,
            paragraph_count=300,
            block_role=role,
            block_structural_role=structural_role,
            block_layout_origin=layout_origin,
        )

        cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

        assert report.removed_page_furniture_count == 25, (role, structural_role, layout_origin)
        assert "QX-4471" not in [paragraph.text for paragraph in cleaned], (role, layout_origin)


def test_page_cadence_furniture_is_removed_in_remove_mode_too():
    paragraphs = _document_with_recurring_block(
        block_text="QX-4471",
        stride=10,
        paragraph_count=400,
        block_role="heading",
        block_structural_role="heading",
    )

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs, cleanup_mode="remove")

    assert report.cleanup_mode == "remove"
    assert report.removed_page_furniture_count == 40
    assert report.removed_paragraph_count == 40
    assert "QX-4471" not in [paragraph.text for paragraph in cleaned]


def test_case_variants_of_the_same_stamp_collapse_into_one_furniture_block():
    """Real OCR emits SECRET / Secret / secret for one stamp; normalization folds case."""
    paragraphs = _document_with_recurring_block(
        block_text="QX-4471",
        stride=10,
        paragraph_count=400,
        block_role="heading",
        block_structural_role="heading",
    )
    for index, paragraph in enumerate(paragraphs):
        if paragraph.text == "QX-4471" and index % 40 == 0:
            paragraph.text = "qx-4471"

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert report.removed_page_furniture_count == 40
    assert not [paragraph for paragraph in cleaned if paragraph.text.lower() == "qx-4471"]


# --- Anti-vacuum counter-proofs (Constitution VII) -----------------------------------


def test_chapter_cadence_repeated_heading_is_not_page_furniture():
    """A per-chapter heading repeats across the whole book but at CHAPTER cadence.

    This is the real 'Footnotes' block from
    tests/sources/book/bernardlietaer-moneyandsustainabilitypdffromepub-*.docx:
    10 occurrences, mean gap ~149 paragraphs. It MUST survive.
    """
    paragraphs = _document_with_recurring_block(
        block_text="Footnotes",
        stride=150,
        paragraph_count=1500,
        block_role="heading",
        block_structural_role="heading",
    )

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert [paragraph.text for paragraph in cleaned].count("Footnotes") == 10
    assert report.removed_page_furniture_count == 0
    assert report.removed_paragraph_count == 0
    assert not [decision for decision in report.decisions if decision.reason == "repeated_page_furniture"]


def test_clustered_repetition_is_not_page_furniture():
    """A refrain repeated tightly inside ONE region does not span the document."""
    paragraphs = _document_with_recurring_block(
        block_text="And so it goes",
        stride=5,
        paragraph_count=1000,
        first_position=0,
        last_position=60,
    )

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert [paragraph.text for paragraph in cleaned].count("And so it goes") == 12
    assert report.removed_page_furniture_count == 0


def test_page_cadence_needs_more_repeats_than_the_generic_minimum():
    """Five wide-spread repeats are structure-scale evidence, not page-scale evidence."""
    paragraphs = _document_with_recurring_block(
        block_text="Part Two",
        stride=20,
        paragraph_count=100,
        block_role="heading",
        block_structural_role="heading",
    )

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert [paragraph.text for paragraph in cleaned].count("Part Two") == 5
    assert report.removed_page_furniture_count == 0


def test_operator_repeat_threshold_can_only_tighten_the_page_cadence_rule():
    """A deleting rule must not be tunable below its own floor, only above it."""
    paragraphs = _document_with_recurring_block(
        block_text="QX-4471",
        stride=10,
        paragraph_count=400,
        block_role="heading",
        block_structural_role="heading",
    )

    _cleaned, lowered = clean_paragraph_layout_artifacts(list(paragraphs), min_repeat_count=2)
    assert lowered.removed_page_furniture_count == 40

    _cleaned, raised = clean_paragraph_layout_artifacts(list(paragraphs), min_repeat_count=60)
    assert raised.removed_page_furniture_count == 0


def test_a_block_that_is_a_large_share_of_the_document_is_never_page_furniture():
    """Anti-vacuum: a recurring speaker label or refrain is content, not an overlay.

    Page furniture is a thin overlay — the real "SECRET" stamp is 8% of its document. A
    block that is a fifth of the document meets page cadence trivially, and deleting it
    would gut the text, so cadence alone must not be enough.
    """
    paragraphs = _document_with_recurring_block(
        block_text="HAMLET",
        stride=3,
        paragraph_count=600,
        block_role="heading",
        block_structural_role="heading",
    )

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert [paragraph.text for paragraph in cleaned].count("HAMLET") == 200
    assert report.removed_page_furniture_count == 0
    assert report.removed_paragraph_count == 0


def test_page_cadence_still_fires_below_the_document_share_bound():
    """The bound must not swallow the case the rule exists for (8% in the real corpus)."""
    paragraphs = _document_with_recurring_block(
        block_text="QX-4471",
        stride=13,
        paragraph_count=600,
        block_role="heading",
        block_structural_role="heading",
    )
    share = [paragraph.text for paragraph in paragraphs].count("QX-4471") / len(paragraphs)
    assert 0.05 < share < document_layout_cleanup.PAGE_FURNITURE_MAX_DOCUMENT_SHARE

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert report.removed_page_furniture_count == 47
    assert "QX-4471" not in [paragraph.text for paragraph in cleaned]


def test_page_cadence_never_drops_an_image_anchor():
    paragraphs = _document_with_recurring_block(
        block_text="[[DOCX_IMAGE_img_007]]",
        stride=10,
        paragraph_count=400,
    )

    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

    assert [paragraph.text for paragraph in cleaned].count("[[DOCX_IMAGE_img_007]]") == 40
    assert report.removed_page_furniture_count == 0


def test_table_and_image_roles_are_never_page_furniture():
    for role in ("table", "image"):
        paragraphs = _document_with_recurring_block(
            block_text="QX-4471",
            stride=10,
            paragraph_count=400,
            block_role=role,
            block_structural_role=role,
        )

        cleaned, report = clean_paragraph_layout_artifacts(paragraphs)

        assert [paragraph.text for paragraph in cleaned].count("QX-4471") == 40, role
        assert report.removed_page_furniture_count == 0, role


def test_furniture_detection_carries_no_classification_marker_vocabulary():
    """Constitution VII deny-list over the furniture-detection module.

    Spec 017 could have been 'fixed' by adding {"secret", "секретно", "ДСП", ...} to
    BOILERPLATE_TOKENS. That is a word list and is forbidden; this test pins its absence.
    """
    source = inspect.getsource(document_layout_cleanup).casefold()
    forbidden_markers = (
        "secret",
        "classified",
        "restricted",
        "for official use",
        "секрет",
        "совершенно секретно",
        "для служебного пользования",
        "дсп",
        "geheim",
        "vertraulich",
        "50x1",
    )
    for marker in forbidden_markers:
        assert marker not in source, f"classification-marker literal leaked into the detector: {marker!r}"
    assert document_layout_cleanup.BOILERPLATE_TOKENS == {
        "confidential",
        "draft",
        "copyright",
        "all rights reserved",
        "конфиденциально",
        "черновик",
        "все права защищены",
    }


def test_normalization_and_large_input_are_linear_style():
    assert normalize_layout_artifact_text(" **Draft** ") == "draft"
    paragraphs = [_paragraph(f"Content {index}.", source_index=index) for index in range(10_000)]
    paragraphs.extend(_paragraph("www.example.com", source_index=10_000 + index) for index in range(5))

    started = time.perf_counter()
    cleaned, report = clean_paragraph_layout_artifacts(paragraphs)
    elapsed = time.perf_counter() - started

    assert len(cleaned) == 10_005
    assert report.flagged_repeated_artifact_count == 5
    assert report.removed_repeated_artifact_count == 0
    assert elapsed < 2.0
