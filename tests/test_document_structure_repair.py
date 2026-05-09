from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.document.structure_repair import repair_pdf_derived_structure


def _paragraph(index: int, text: str, *, role: str = "body", structural_role: str = "body", paragraph_alignment=None) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role=role,
        structural_role=structural_role,
        source_index=index,
        paragraph_id=f"p{index:04d}",
        paragraph_alignment=paragraph_alignment,
    )


def test_repair_pdf_derived_structure_hints_isolated_bullet_without_merging():
    paragraphs = [
        _paragraph(0, "●"),
        _paragraph(1, "Text of item"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == ["●", "Text of item"]
    assert repaired[0].role == "body"
    assert repaired[0].structural_role == "body"
    assert repaired[1].role == "body"
    assert repaired[1].heuristic_role_hint == "list"
    assert repaired[1].heuristic_list_kind_hint == "unordered"
    assert repaired[1].list_kind is None
    assert report.repaired_bullet_items == 0
    assert report.remaining_isolated_marker_count == 1


def test_repair_pdf_derived_structure_ai_first_hints_isolated_bullet_without_merging():
    paragraphs = [
        _paragraph(0, "●"),
        _paragraph(1, "Text of item"),
    ]

    repaired, report = repair_pdf_derived_structure(
        paragraphs,
        structure_recovery_enabled=True,
        structure_recovery_mode="ai_first",
    )

    assert [paragraph.text for paragraph in repaired] == ["●", "Text of item"]
    assert repaired[0].role == "body"
    assert repaired[0].structural_role == "body"
    assert repaired[1].role == "body"
    assert repaired[1].structural_role == "body"
    assert repaired[1].heuristic_role_hint == "list"
    assert repaired[1].heuristic_list_kind_hint == "unordered"
    assert repaired[1].list_kind is None
    assert report.repaired_bullet_items == 0
    assert report.remaining_isolated_marker_count == 1


def test_repair_pdf_derived_structure_builds_bounded_toc_and_keeps_body_boundary():
    paragraphs = [
        _paragraph(0, "Содержание"),
        _paragraph(1, "Введение .... 1"),
        _paragraph(2, "Заключение .... 29"),
        _paragraph(3, "Марк 13:13", paragraph_alignment="center"),
        _paragraph(4, "Введение"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert repaired[0].structural_role == "body"
    assert repaired[0].heuristic_structural_role_hint == "toc_header"
    assert repaired[1].structural_role == "body"
    assert repaired[1].heuristic_structural_role_hint == "toc_entry"
    assert repaired[2].structural_role == "body"
    assert repaired[2].heuristic_structural_role_hint == "toc_entry"
    assert repaired[3].structural_role == "body"
    assert repaired[4].role == "body"
    assert repaired[4].structural_role == "body"
    assert repaired[4].heuristic_role_hint == "heading"
    assert repaired[4].heuristic_heading_level_hint == 2
    assert report.bounded_toc_regions == 1
    assert report.toc_body_boundary_repairs == 1
    assert report.heading_candidates_from_toc == 1


def test_repair_pdf_derived_structure_ai_first_hints_toc_matched_body_line_without_promoting_heading():
    paragraphs = [
        _paragraph(0, "Содержание"),
        _paragraph(1, "Введение .... 1"),
        _paragraph(2, "Заключение .... 29"),
        _paragraph(3, "Марк 13:13", paragraph_alignment="center"),
        _paragraph(4, "Введение"),
    ]

    repaired, report = repair_pdf_derived_structure(
        paragraphs,
        structure_recovery_enabled=True,
        structure_recovery_mode="ai_first",
    )

    assert repaired[0].structural_role == "body"
    assert repaired[0].heuristic_structural_role_hint == "toc_header"
    assert repaired[1].structural_role == "body"
    assert repaired[1].heuristic_structural_role_hint == "toc_entry"
    assert repaired[2].structural_role == "body"
    assert repaired[2].heuristic_structural_role_hint == "toc_entry"
    assert repaired[4].text == "Введение"
    assert repaired[4].role == "body"
    assert repaired[4].structural_role == "body"
    assert repaired[4].heuristic_role_hint == "heading"
    assert repaired[4].heuristic_heading_level_hint == 2
    assert repaired[4].heading_source is None
    assert repaired[4].heading_level is None
    assert report.heading_candidates_from_toc == 1


def test_repair_pdf_derived_structure_splits_compound_toc_tail_from_epigraph_and_heading_start():
    paragraphs = [
        _paragraph(0, "Table of Contents", structural_role="toc_header"),
        _paragraph(1, "Introduction........ 4", structural_role="toc_entry"),
        _paragraph(2, "Conclusion........ 29", structural_role="toc_entry"),
        _paragraph(
            3,
            "Conclusion........ 29 \"You will be hated by all for my name's sake.\" - Mark 13:13 Introduction My grandfather was convinced",
        ),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "Table of Contents",
        "Introduction........ 4",
        "Conclusion........ 29",
        "Conclusion........ 29 \"You will be hated by all for my name's sake.\" - Mark 13:13 Introduction My grandfather was convinced",
    ]
    assert repaired[3].structural_role == "body"
    assert repaired[3].heuristic_structural_role_hint is None
    assert [hint.text for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "Conclusion........ 29",
        '"You will be hated by all for my name\'s sake." - Mark 13:13',
        "Introduction",
        "My grandfather was convinced",
    ]
    assert [hint.structural_role for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "toc_entry",
        "epigraph",
        "body",
        "body",
    ]
    assert [hint.role for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "body",
        "body",
        "heading",
        "body",
    ]
    assert report.toc_body_boundary_repairs >= 1
    assert report.heading_candidates_from_toc >= 1


def test_repair_pdf_derived_structure_ai_first_hints_compound_toc_split_entry_without_binding_structural_role():
    paragraphs = [
        _paragraph(0, "Table of Contents", structural_role="toc_header"),
        _paragraph(1, "Introduction........ 4", structural_role="toc_entry"),
        _paragraph(2, "Conclusion........ 29", structural_role="toc_entry"),
        _paragraph(
            3,
            "Conclusion........ 29 \"You will be hated by all for my name's sake.\" - Mark 13:13 Introduction My grandfather was convinced",
        ),
    ]

    repaired, report = repair_pdf_derived_structure(
        paragraphs,
        structure_recovery_enabled=True,
        structure_recovery_mode="ai_first",
    )

    assert [paragraph.text for paragraph in repaired] == [
        "Table of Contents",
        "Introduction........ 4",
        "Conclusion........ 29",
        "Conclusion........ 29 \"You will be hated by all for my name's sake.\" - Mark 13:13 Introduction My grandfather was convinced",
    ]
    assert repaired[3].role == "body"
    assert repaired[3].structural_role == "body"
    assert [hint.text for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "Conclusion........ 29",
        '"You will be hated by all for my name\'s sake." - Mark 13:13',
        "Introduction",
        "My grandfather was convinced",
    ]
    assert [hint.structural_role for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "toc_entry",
        "epigraph",
        "body",
        "body",
    ]
    assert [hint.role for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "body",
        "body",
        "heading",
        "body",
    ]
    assert report.toc_body_boundary_repairs >= 1
    assert report.heading_candidates_from_toc >= 1


def test_repair_pdf_derived_structure_hints_split_numbered_list_lead_without_merging():
    paragraphs = [
        _paragraph(0, "4. Daniel 9:27,"),
        _paragraph(1, "11:31 and Matthew 24:15 describe the abomination of desolation."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "4. Daniel 9:27,",
        "11:31 and Matthew 24:15 describe the abomination of desolation.",
    ]
    assert repaired[0].role == "body"
    assert repaired[0].structural_role == "body"
    assert repaired[0].heuristic_role_hint == "list"
    assert repaired[0].heuristic_list_kind_hint == "ordered"
    assert repaired[0].list_kind is None
    assert repaired[1].role == "body"
    assert report.repaired_numbered_items == 0


def test_repair_pdf_derived_structure_ai_first_hints_split_numbered_list_lead_without_merging():
    paragraphs = [
        _paragraph(0, "4. Daniel 9:27,"),
        _paragraph(1, "11:31 and Matthew 24:15 describe the abomination of desolation."),
    ]

    repaired, report = repair_pdf_derived_structure(
        paragraphs,
        structure_recovery_enabled=True,
        structure_recovery_mode="ai_first",
    )

    assert [paragraph.text for paragraph in repaired] == [
        "4. Daniel 9:27,",
        "11:31 and Matthew 24:15 describe the abomination of desolation.",
    ]
    assert repaired[0].role == "body"
    assert repaired[0].structural_role == "body"
    assert repaired[0].heuristic_role_hint == "list"
    assert repaired[0].heuristic_list_kind_hint == "ordered"
    assert repaired[0].list_kind is None
    assert repaired[1].role == "body"
    assert report.repaired_numbered_items == 0


def test_repair_pdf_derived_structure_splits_heading_prefix_from_numbered_list_start():
    paragraphs = [
        _paragraph(0, "Contents", structural_role="toc_header"),
        _paragraph(1, "Action Steps for Individuals........ 27", structural_role="toc_entry"),
        _paragraph(2, "Action Steps for Nations........ 28", structural_role="toc_entry"),
        _paragraph(3, "Action Steps for Individuals 1. Prepare your spirit for faithful endurance."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "Contents",
        "Action Steps for Individuals........ 27",
        "Action Steps for Nations........ 28",
        "Action Steps for Individuals 1. Prepare your spirit for faithful endurance.",
    ]
    assert repaired[3].role == "body"
    assert repaired[3].structural_role == "body"
    assert [hint.text for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "Action Steps for Individuals",
        "1. Prepare your spirit for faithful endurance.",
    ]
    assert [hint.role for hint in repaired[3].heuristic_embedded_structure_hints] == ["heading", "list"]
    assert [hint.heading_level for hint in repaired[3].heuristic_embedded_structure_hints] == [2, None]
    assert [hint.list_kind for hint in repaired[3].heuristic_embedded_structure_hints] == [None, "ordered"]
    assert report.heading_candidates_from_toc >= 1


def test_repair_pdf_derived_structure_ai_first_hints_split_heading_prefix_without_heading_role():
    paragraphs = [
        _paragraph(0, "Contents", structural_role="toc_header"),
        _paragraph(1, "Action Steps for Individuals........ 27", structural_role="toc_entry"),
        _paragraph(2, "Action Steps for Nations........ 28", structural_role="toc_entry"),
        _paragraph(3, "Action Steps for Individuals 1. Prepare your spirit for faithful endurance."),
    ]

    repaired, report = repair_pdf_derived_structure(
        paragraphs,
        structure_recovery_enabled=True,
        structure_recovery_mode="ai_first",
    )

    assert [paragraph.text for paragraph in repaired] == [
        "Contents",
        "Action Steps for Individuals........ 27",
        "Action Steps for Nations........ 28",
        "Action Steps for Individuals 1. Prepare your spirit for faithful endurance.",
    ]
    assert repaired[3].role == "body"
    assert repaired[3].structural_role == "body"
    assert [hint.text for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "Action Steps for Individuals",
        "1. Prepare your spirit for faithful endurance.",
    ]
    assert [hint.role for hint in repaired[3].heuristic_embedded_structure_hints] == ["heading", "list"]
    assert [hint.heading_level for hint in repaired[3].heuristic_embedded_structure_hints] == [2, None]
    assert [hint.list_kind for hint in repaired[3].heuristic_embedded_structure_hints] == [None, "ordered"]
    assert report.heading_candidates_from_toc >= 1


def test_repair_pdf_derived_structure_splits_heading_prefix_with_punctuation_variant():
    paragraphs = [
        _paragraph(0, "Contents", structural_role="toc_header"),
        _paragraph(1, "The Rapture........ 7", structural_role="toc_entry"),
        _paragraph(2, "Great Tribulation........ 9", structural_role="toc_entry"),
        _paragraph(3, "The Rapture: why this matters for endurance."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "Contents",
        "The Rapture........ 7",
        "Great Tribulation........ 9",
        "The Rapture: why this matters for endurance.",
    ]
    assert repaired[3].role == "body"
    assert repaired[3].structural_role == "body"
    assert [hint.text for hint in repaired[3].heuristic_embedded_structure_hints] == [
        "The Rapture",
        "why this matters for endurance.",
    ]
    assert [hint.role for hint in repaired[3].heuristic_embedded_structure_hints] == ["heading", "body"]
    assert [hint.heading_level for hint in repaired[3].heuristic_embedded_structure_hints] == [2, None]
    assert report.heading_candidates_from_toc >= 1


def test_repair_pdf_derived_structure_does_not_promote_inline_toc_title_fragment_inside_sentence():
    paragraphs = [
        _paragraph(0, "Contents", structural_role="toc_header"),
        _paragraph(1, "The Mark of the Beast........ 19", structural_role="toc_entry"),
        _paragraph(2, "Is the Mark of the Beast actually a quantum technology?"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "Contents",
        "The Mark of the Beast........ 19",
        "Is the Mark of the Beast actually a quantum technology?",
    ]
    assert repaired[2].role == "body"
    assert report.heading_candidates_from_toc == 0


def test_repair_pdf_derived_structure_accepts_plain_toc_entries_inside_bounded_region():
    paragraphs = [
        _paragraph(0, "Содержание"),
        _paragraph(1, "Введение .... 1"),
        _paragraph(2, "Восхищение"),
        _paragraph(3, "Великая скорбь"),
        _paragraph(4, "Заключение .... 29"),
        _paragraph(5, "Марк 13:13", paragraph_alignment="center"),
        _paragraph(6, "Это обычный абзац после содержания с достаточной длиной."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.structural_role for paragraph in repaired[:5]] == [
        "body",
        "body",
        "body",
        "body",
        "body",
    ]
    assert [paragraph.heuristic_structural_role_hint for paragraph in repaired[:5]] == [
        "toc_header",
        "toc_entry",
        "toc_entry",
        "toc_entry",
        "toc_entry",
    ]
    assert repaired[5].structural_role == "body"
    assert repaired[6].role == "body"
    assert report.bounded_toc_regions == 1


def test_repair_pdf_derived_structure_keeps_standalone_bullet_before_heading_boundary():
    paragraphs = [
        _paragraph(0, "●"),
        _paragraph(1, "Figure Overview", role="heading", structural_role="heading"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == ["●", "Figure Overview"]
    assert repaired[0].role == "body"
    assert repaired[0].structural_role == "body"
    assert report.repaired_bullet_items == 0
    assert report.remaining_isolated_marker_count == 1


def test_repair_pdf_derived_structure_keeps_standalone_number_before_structural_boundary():
    paragraphs = [
        _paragraph(0, "1."),
        _paragraph(1, "Figure 1. Market structure", role="caption", structural_role="caption"),
        _paragraph(2, "2."),
        _paragraph(3, "Section Heading", role="heading", structural_role="heading"),
        _paragraph(4, "3."),
        _paragraph(5, "Contents", role="body", structural_role="toc_header"),
        _paragraph(6, "4."),
        _paragraph(7, "Image placeholder", role="image", structural_role="image"),
        _paragraph(8, "5."),
        _paragraph(9, "Table placeholder", role="table", structural_role="table"),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "1.",
        "Figure 1. Market structure",
        "2.",
        "Section Heading",
        "3.",
        "Contents",
        "4.",
        "Image placeholder",
        "5.",
        "Table placeholder",
    ]
    assert repaired[0].role == "body"
    assert repaired[1].role == "caption"
    assert report.repaired_numbered_items == 0
    assert report.remaining_isolated_marker_count == 5


def test_repair_pdf_derived_structure_does_not_infer_toc_from_short_front_matter_without_header():
    paragraphs = [
        _paragraph(0, "Foreword"),
        _paragraph(1, "Author's Note"),
        _paragraph(2, "This edition preserves the original argument without adding a table of contents."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.structural_role for paragraph in repaired] == ["body", "body", "body"]
    assert [paragraph.role for paragraph in repaired] == ["body", "body", "body"]
    assert report.bounded_toc_regions == 0
    assert report.heading_candidates_from_toc == 0
    assert report.applied is False


def test_repair_pdf_derived_structure_keeps_body_prose_with_ellipsis_outside_toc_region():
    paragraphs = [
        _paragraph(0, "He paused... then continued with the same argument in the next sentence."),
        _paragraph(1, "The discussion remains ordinary body prose and not a TOC entry."),
    ]

    repaired, report = repair_pdf_derived_structure(paragraphs)

    assert [paragraph.text for paragraph in repaired] == [
        "He paused... then continued with the same argument in the next sentence.",
        "The discussion remains ordinary body prose and not a TOC entry.",
    ]
    assert [paragraph.structural_role for paragraph in repaired] == ["body", "body"]
    assert report.bounded_toc_regions == 0
    assert report.applied is False
