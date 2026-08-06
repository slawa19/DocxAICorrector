import docxaicorrector.core.config as config
import docxaicorrector.document.semantic_blocks as semantic_blocks

from docxaicorrector.core.models import DocumentBlock, EmbeddedStructureHint, ParagraphRelation, ParagraphUnit
from docxaicorrector.document.relations import build_paragraph_relations
from docxaicorrector.document.semantic_blocks import (
    build_editing_jobs,
    build_marker_wrapped_block_text,
    build_semantic_blocks,
)


def test_build_semantic_blocks_keeps_heading_with_following_body():
    paragraphs = [
        ParagraphUnit(text="Глава 1", role="heading"),
        ParagraphUnit(text="Короткий абзац после заголовка.", role="body"),
        ParagraphUnit(text="Следующий абзац, который уже должен перейти в отдельный блок.", role="body"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=70)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Глава 1",
        "Короткий абзац после заголовка.",
    ]
    assert blocks[1].text == "Следующий абзац, который уже должен перейти в отдельный блок."


def test_build_semantic_blocks_keeps_consecutive_headings_with_following_body():
    paragraphs = [
        ParagraphUnit(text="Глава 1", role="heading", heading_level=1),
        ParagraphUnit(text="Раздел 1.1", role="heading", heading_level=2),
        ParagraphUnit(text="Первый содержательный абзац после цепочки заголовков.", role="body"),
        ParagraphUnit(text="Следующий абзац уже должен перейти в отдельный блок из-за лимита.", role="body"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=90)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Глава 1",
        "Раздел 1.1",
        "Первый содержательный абзац после цепочки заголовков.",
    ]
    assert blocks[1].text == "Следующий абзац уже должен перейти в отдельный блок из-за лимита."


def test_build_editing_jobs_uses_neighbor_blocks_for_context():
    paragraphs = [
        ParagraphUnit(text="Первый блок.", role="body"),
        ParagraphUnit(text="Второй блок.", role="body"),
        ParagraphUnit(text="Третий блок.", role="body"),
    ]
    blocks = build_semantic_blocks(paragraphs, max_chars=20)

    jobs = build_editing_jobs(blocks, max_chars=3000)

    assert len(jobs) == 3
    assert jobs[1]["target_text"] == "Второй блок."
    assert jobs[1]["context_before"] == "Первый блок."
    assert jobs[1]["context_after"] == "Третий блок."
    assert jobs[1]["structure_phase"] == "post_ai_final"
    assert jobs[1]["structure_source"] == "post_ai_final_binding"
    assert all(str(job["target_text"]).strip() for job in jobs)


def test_build_editing_jobs_marks_image_only_blocks_as_passthrough():
    paragraphs = [
        ParagraphUnit(text="Вступление", role="body"),
        ParagraphUnit(text="[[DOCX_IMAGE_img_001]]", role="image"),
        ParagraphUnit(text="Основной текст", role="body"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=20)
    jobs = build_editing_jobs(blocks, max_chars=3000)

    assert [job["target_text"] for job in jobs] == ["Вступление", "[[DOCX_IMAGE_img_001]]", "Основной текст"]
    assert [job["job_kind"] for job in jobs] == ["llm", "passthrough", "llm"]
    assert jobs[0]["paragraph_ids"] == ["p0000"]
    assert str(jobs[1]["target_text_with_markers"]).startswith("[[DOCX_PARA_p0001]]")
    assert jobs[1]["narration_include"] is False


def test_build_semantic_blocks_keeps_heading_with_following_epigraph_cluster_even_over_soft_limit():
    paragraphs = [
        ParagraphUnit(text="Глава 1", role="heading", paragraph_id="p0000", heading_level=1),
        ParagraphUnit(
            text="Богатство заключается не в количестве имущества, а в свободе желаний.",
            role="body",
            structural_role="epigraph",
            paragraph_id="p0001",
        ),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0002"),
        ParagraphUnit(text="Следующий обычный абзац.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=65, relations=[])

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Глава 1",
        "Богатство заключается не в количестве имущества, а в свободе желаний.",
        "— Эпиктет",
    ]


def test_build_semantic_blocks_uses_structural_roles_for_toc_grouping_without_relations():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Первый обычный абзац после содержания.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=60, relations=[])

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Содержание",
        "Глава 1........ 12",
        "Глава 2........ 18",
    ]


def test_build_semantic_blocks_uses_structural_hints_for_toc_grouping_without_relations():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="body", paragraph_id="p0000", heuristic_structural_role_hint="toc_header"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="body", paragraph_id="p0001", heuristic_structural_role_hint="toc_entry"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="body", paragraph_id="p0002", heuristic_structural_role_hint="toc_entry"),
        ParagraphUnit(text="Первый обычный абзац после содержания.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=60, relations=[], structure_phase="pre_ai_diagnostic")

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Содержание",
        "Глава 1........ 12",
        "Глава 2........ 18",
    ]


def test_build_semantic_blocks_default_post_ai_mode_ignores_structural_hints_for_toc_grouping():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="body", paragraph_id="p0000", heuristic_structural_role_hint="toc_header"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="body", paragraph_id="p0001", heuristic_structural_role_hint="toc_entry"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="body", paragraph_id="p0002", heuristic_structural_role_hint="toc_entry"),
        ParagraphUnit(text="Первый обычный абзац после содержания.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=60, relations=[])
    jobs = build_editing_jobs(blocks, max_chars=3000)

    assert jobs[0]["job_kind"] == "llm"
    assert jobs[0]["toc_dominant"] is False
    assert jobs[0]["structure_source"] == "post_ai_final_binding"


def test_build_editing_jobs_default_post_ai_mode_ignores_text_only_toc_heuristics():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="body", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="body", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="body", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=80, relations=[])
    jobs = build_editing_jobs(blocks, max_chars=3000)

    assert jobs[0]["job_kind"] == "llm"
    assert jobs[0]["toc_dominant"] is False
    assert jobs[0]["toc_paragraph_count"] == 0


def test_build_semantic_blocks_respects_hard_boundary_paragraph_ids():
    paragraphs = [
        ParagraphUnit(text="Chapter 1", role="heading", heading_level=1, paragraph_id="p0000"),
        ParagraphUnit(text="First chapter body paragraph.", role="body", paragraph_id="p0001"),
        ParagraphUnit(text="Chapter 2", role="heading", heading_level=1, paragraph_id="p0002"),
        ParagraphUnit(text="Second chapter body paragraph.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(
        paragraphs,
        max_chars=1000,
        relations=[],
        hard_boundary_paragraph_ids={"p0002"},
    )

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == ["Chapter 1", "First chapter body paragraph."]
    assert [paragraph.text for paragraph in blocks[1].paragraphs] == ["Chapter 2", "Second chapter body paragraph."]


def test_build_editing_jobs_marks_toc_only_blocks_as_passthrough():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Первый обычный абзац.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=80, relations=[])
    jobs = build_editing_jobs(blocks, max_chars=3000)

    assert [job["job_kind"] for job in jobs] == ["passthrough", "llm"]
    assert jobs[0]["paragraph_ids"] == ["p0000", "p0001", "p0002"]
    assert jobs[0]["toc_dominant"] is True
    assert jobs[0]["toc_paragraph_count"] == 3
    assert jobs[0]["structural_roles"] == ["toc_header", "toc_entry", "toc_entry"]
    assert jobs[0]["narration_include"] is False


def test_build_editing_jobs_marks_advisory_pre_ai_structure_source():
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="body", paragraph_id="p0000", heuristic_structural_role_hint="toc_header"),
        ParagraphUnit(text="Chapter 1........12", role="body", structural_role="body", paragraph_id="p0001", heuristic_structural_role_hint="toc_entry"),
        ParagraphUnit(text="Chapter 2........18", role="body", structural_role="body", paragraph_id="p0002", heuristic_structural_role_hint="toc_entry"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=80, relations=[], structure_phase="pre_ai_diagnostic")
    jobs = build_editing_jobs(blocks, max_chars=3000, structure_phase="pre_ai_diagnostic")

    assert jobs[0]["structure_phase"] == "pre_ai_diagnostic"
    assert jobs[0]["structure_source"] == "pre_ai_diagnostic_hint"


def test_build_editing_jobs_marks_degraded_ai_first_structure_source():
    paragraphs = [
        ParagraphUnit(text="Глава 1", role="heading", structural_role="heading", paragraph_id="p0000", heading_level=1),
        ParagraphUnit(text="Обычный абзац.", role="body", structural_role="body", paragraph_id="p0001"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=80, relations=[], structure_phase="ai_first_degraded_fallback")
    jobs = build_editing_jobs(blocks, max_chars=3000, structure_phase="ai_first_degraded_fallback")

    assert jobs[0]["structure_phase"] == "ai_first_degraded_fallback"
    assert jobs[0]["structure_source"] == "ai_first_degraded_fallback"


def test_build_editing_jobs_routes_toc_only_blocks_through_llm_in_translate_mode():
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Chapter 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=80, relations=[])
    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="translate")

    assert [job["job_kind"] for job in jobs] == ["llm"]
    assert jobs[0]["toc_dominant"] is True
    assert jobs[0]["narration_include"] is False


def test_build_editing_jobs_marks_reference_region_and_image_only_blocks_as_excluded_for_narration():
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Chapter 1", role="heading", paragraph_id="p0000", heading_level=1),
                ParagraphUnit(text="Narrative body paragraph.", role="body", paragraph_id="p0001"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="[[DOCX_IMAGE_img_001]]", role="image", structural_role="image", paragraph_id="p0002"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="References", role="heading", paragraph_id="p0003", heading_level=1),
                ParagraphUnit(text="[1] Smith, 2009. DOI:10.1000/xyz", role="body", paragraph_id="p0004"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [True, False, False]
    assert [job["job_kind"] for job in jobs] == ["llm", "passthrough", "passthrough"]


def test_build_editing_jobs_keeps_mixed_final_narrative_block_out_of_reference_region():
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Chapter 1", role="heading", paragraph_id="p0000", heading_level=1),
                ParagraphUnit(text="Narrative body paragraph.", role="body", paragraph_id="p0001"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Closing reflections", role="heading", paragraph_id="p0002", heading_level=1),
                ParagraphUnit(text="Final narrative paragraph.", role="body", paragraph_id="p0003"),
                ParagraphUnit(text="[1] Smith, 2009. DOI:10.1000/xyz", role="body", paragraph_id="p0004"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [True, True]


def test_build_editing_jobs_keeps_bibliography_shaped_suffix_that_no_section_title_anchors():
    """Counter-proof for the rule this replaced (spec 054, finding 1b).

    Until 2026-08-04 the region was resolved by requiring >= 70% "bibliography-like" LINES in
    the document suffix. That test never fired on a real book, and where it could fire it cut
    body prose that happened to sit next to citation lines — the first block below is exactly
    that shape. With no bare back-matter section title to anchor a region, nothing is cut:
    an unidentifiable region is kept (Constitution VII, "no source signal, no repair").
    """
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Chapter 1", role="heading", paragraph_id="p0000", heading_level=1),
                ParagraphUnit(text="Narrative body paragraph.", role="body", paragraph_id="p0001"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Overview of sources used in this chapter.", role="body", paragraph_id="p0002"),
                ParagraphUnit(text="[1] Smith, 2009. DOI:10.1000/xyz", role="body", paragraph_id="p0003"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="https://example.com/ref", role="body", paragraph_id="p0004"),
                ParagraphUnit(text="ISBN 978-1-4028-9462-6", role="body", paragraph_id="p0005"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [True, True, True]


def _pdf_shaped_bibliography_entry_paragraphs(start: int) -> list[ParagraphUnit]:
    """Bibliography entries in the shape PDF import actually produces: each entry wraps over
    several lines and only ONE of them carries a year, publisher or URL. Measured on the
    corpus (spec 054, finding 1b) this scores 9-21% "bibliography-like" lines — which is why
    a line-ratio region test can never recognise it and the region must be found structurally.
    """
    lines = [
        "Aghion, P., Van Reenen, J. and Zingales, L., ‘Innovation and",
        "institutional ownership’, *American Economic Review*, 103(1)",
        "(2013), pp. 277–304.",
        "Clark, J. B., *The Distribution of Wealth: A Theory of Wages,*",
        "*Interest and Profits* (New York: Macmillan, 1899).",
        "Gaus, G. F., *Value and Justification: The Foundations of Liberal*",
        "*Theory* (New York: Cambridge University Press, 1990).",
        "Keynes, J. M., *The General Theory of Employment, Interest and*",
        "*Money* (London: Macmillan, 1936).",
    ]
    return [
        ParagraphUnit(text=line, role="body", paragraph_id=f"p{start + offset:04d}")
        for offset, line in enumerate(lines)
    ]


def test_build_editing_jobs_excludes_pdf_shaped_bibliography_region_and_keeps_the_prose_around_it():
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="9. The Economics of Hope", role="heading", paragraph_id="p0000", heading_level=2),
                ParagraphUnit(
                    text=(
                        "What if it stemmed purely from a set of deeply ingrained ideas? "
                        "The point is not that value is subjective, but that the story we tell "
                        "about where it comes from decides who gets paid."
                    ),
                    role="body",
                    paragraph_id="p0001",
                ),
            ]
        ),
        DocumentBlock(paragraphs=[ParagraphUnit(text="Bibliography", role="heading", paragraph_id="p0002", heading_level=2)]),
        DocumentBlock(paragraphs=_pdf_shaped_bibliography_entry_paragraphs(3)),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Acknowledgements", role="heading", paragraph_id="p0020", heading_level=2),
                ParagraphUnit(
                    text=(
                        "In 2013 I wrote a book called The Entrepreneurial State. In it I debunked "
                        "how myths about lone entrepreneurs have hidden the collective effort behind "
                        "innovation, and many people helped me say so."
                    ),
                    role="body",
                    paragraph_id="p0021",
                ),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    # Prose before the region and the author's Acknowledgements after it stay in the narration;
    # only the bibliography heading and its wrapped entries are dropped.
    assert [job["narration_include"] for job in jobs] == [True, False, False, True]


def test_build_editing_jobs_keeps_notes_region_together_across_its_deeper_sub_headings():
    """The notes section of a real book carries per-chapter sub-headings. They are DEEPER than
    the "Notes" anchor, so the region runs through them and ends at the next heading of the
    anchor's own depth — the outline, not the shape of the entries, decides."""
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="9. The Economics of Hope", role="heading", paragraph_id="p0000", heading_level=2),
                ParagraphUnit(text="Closing narrative paragraph of the last chapter.", role="body", paragraph_id="p0001"),
            ]
        ),
        DocumentBlock(paragraphs=[ParagraphUnit(text="Notes", role="heading", paragraph_id="p0002", heading_level=2)]),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="PREFACE", role="heading", paragraph_id="p0003", heading_level=3),
                ParagraphUnit(text="1. Goldman Sachs Annual Report, 2010.", role="list", paragraph_id="p0004"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="2. THE VALUE OF EVERYTHING", role="heading", paragraph_id="p0005", heading_level=3),
                ParagraphUnit(text="4. Ibid., p. 115.", role="list", paragraph_id="p0006"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Acknowledgements", role="heading", paragraph_id="p0007", heading_level=2),
                ParagraphUnit(text="Many people helped me write this, and I want to name them.", role="body", paragraph_id="p0008"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [True, False, False, False, True]


def test_build_editing_jobs_stops_the_reference_region_at_a_heading_with_no_level():
    """A following heading whose level is unknown ends the region. Unknown depth is never
    treated as "deeper", so an import that drops heading levels can only cut the region
    SHORT — it can never widen it over the section that follows."""
    blocks = [
        DocumentBlock(paragraphs=[ParagraphUnit(text="Notes", role="heading", paragraph_id="p0000", heading_level=2)]),
        DocumentBlock(paragraphs=[ParagraphUnit(text="1. Goldman Sachs Annual Report, 2010.", role="list", paragraph_id="p0001")]),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="About the Authors", role="heading", paragraph_id="p0002"),
                ParagraphUnit(text="Bernard Lietaer has been active in money systems for 35 years.", role="body", paragraph_id="p0003"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [False, False, True]


def test_build_editing_jobs_drops_the_index_from_the_narration():
    """The index used to be kept: the owner's first framing named the table of contents, the
    notes and the sources, and said nothing about an index. **Reversed by the owner on
    2026-08-06**, once the price was measured — on Rethinking Money the index is 463 paragraphs
    of "Short- termism, 44– 46, 217" read out loud."""
    blocks = [
        DocumentBlock(paragraphs=[ParagraphUnit(text="Index", role="heading", paragraph_id="p0000", heading_level=2)]),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Short- termism, 44– 46, 217", role="body", paragraph_id="p0001"),
                ParagraphUnit(text="Trust, 19– 20, 46", role="body", paragraph_id="p0002"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [False, False]


def test_build_editing_jobs_anchors_a_reference_region_on_a_title_that_lost_its_heading_role():
    """Rethinking Money's NOTES and BIBLIOGRAPHY arrive from PDF import as `role=body` while its
    INDEX arrives as a heading — same book, same three section titles, two different import
    outcomes (measured 2026-08-06). Requiring the `heading` role therefore made the region fire
    zero times on that book. The signal the rule keys on is that a paragraph's whole text IS a
    blessed back-matter section title; the role is not part of it.

    The emphasis wrapper is part of the case: the PDF path carries bold inside the text, so the
    title arrives literally as `**BIBLIOGRAPHY**`."""
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="From Scarcity to Sustainable Abundance", role="heading", paragraph_id="p0000", heading_level=1),
                ParagraphUnit(text="The closing narrative paragraph of the final chapter.", role="body", paragraph_id="p0001"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="**BIBLIOGRAPHY**", role="body", paragraph_id="p0002"),
                ParagraphUnit(text="Amato, M. *Complementary Currency Systems.* Milan: Bocconi, 2003.", role="body", paragraph_id="p0003"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="ACKNOWLEDGEMENTS", role="heading", paragraph_id="p0004", heading_level=1),
                ParagraphUnit(text="Special thanks to Ed and Deb Shapiro, and to Frank Bailin.", role="body", paragraph_id="p0005"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    # The chapter before it and the acknowledgements after it are narrated; only the
    # bibliography goes. Losing the acknowledgements here would be the anti-vacuum failure.
    assert [job["narration_include"] for job in jobs] == [True, False, True]


def test_build_editing_jobs_starts_the_region_after_a_title_that_closes_its_block():
    """Rethinking Money's `**NOTES**` is paragraph 7 of 8: segmentation swept it onto the tail of
    the block that holds the closing paragraphs of the last chapter. The region therefore starts
    at the NEXT block, so that chapter text stays in the narration. The title line itself is
    then spoken — a word or two — which is the cheap side of the trade."""
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="She continues: “Take the fact that the Arab Spring became the story of 2011.”", role="body", paragraph_id="p0000"),
                ParagraphUnit(text="Rethinking money, we can enjoy an era of genuine and sustainable abundance.", role="body", paragraph_id="p0001"),
                ParagraphUnit(text="**NOTES**", role="body", paragraph_id="p0002"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Introduction", role="body", paragraph_id="p0003"),
                ParagraphUnit(text="1. Alan Wilson Watts, “From Time to Eternity.” Rutland, VT: C. E. Tuttle, 1999.", role="list", paragraph_id="p0004"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="ACKNOWLEDGEMENTS", role="heading", paragraph_id="p0005", heading_level=1),
                ParagraphUnit(text="Special thanks to Ed and Deb Shapiro, and to Frank Bailin.", role="body", paragraph_id="p0006"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [True, False, True]


def _rethinking_money_notes_entry_paragraphs(start: int) -> list[ParagraphUnit]:
    """Endnote entries in the shape Rethinking Money's PDF import actually produces: the
    per-chapter label and two lines of a quoted exchange inside note 4 arrive as
    `role=heading, heading_level=3, heading_source=explicit` (measured 2026-08-06, blocks
    232-234). Every synthetic fixture that gives the notes section flat body paragraphs proves
    the arithmetic and nothing else — this is Constitution VIII in its concrete form, and it is
    exactly how the region-end defect stayed invisible behind a green anchor test."""
    return [
        ParagraphUnit(text="Chapter 2", role="heading", paragraph_id=f"p{start:04d}", heading_level=3, heading_source="explicit"),
        ParagraphUnit(text="1. Aristotle, *Nichomachean Ethics* (350 bc), 1133.", role="list", paragraph_id=f"p{start + 1:04d}"),
        ParagraphUnit(
            text="4. A governor of the Bank of En gland was being questioned by the Bank Commission.",
            role="body",
            paragraph_id=f"p{start + 2:04d}",
        ),
        ParagraphUnit(
            text="“In ample suffi ciency, Sir.”",
            role="heading",
            paragraph_id=f"p{start + 3:04d}",
            heading_level=3,
            heading_source="explicit",
        ),
        ParagraphUnit(text="“Can you be more precise?”", role="body", paragraph_id=f"p{start + 4:04d}"),
    ]


def test_build_editing_jobs_carries_a_level_less_notes_region_to_the_next_reference_section():
    """The anchor has no depth at all and the entries under it were mis-promoted to headings —
    Rethinking Money, measured 2026-08-06. Until then the region ended at the "nearest following
    heading", which is a line of a quoted exchange INSIDE note 4, so 225 of 264 note paragraphs
    were still narrated. The bound that works is the start of the NEXT reference section: the
    same blessed lexicon, the same guards, and it needs no heading level to be believed."""
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Rethinking money, we can enjoy an era of sustainable abundance.", role="body", paragraph_id="p0000"),
                ParagraphUnit(text="**NOTES**", role="body", paragraph_id="p0001"),
            ]
        ),
        DocumentBlock(paragraphs=_rethinking_money_notes_entry_paragraphs(2)),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Chapter 3", role="heading", paragraph_id="p0007", heading_level=3, heading_source="explicit"),
                ParagraphUnit(text="7. See M. Amato, *Complementary Currency Systems.* Milan: Bocconi, 2003.", role="list", paragraph_id="p0008"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="**BIBLIOGRAPHY**", role="body", paragraph_id="p0009"),
                ParagraphUnit(text="Needleman, Jacob. *Money and the Meaning of Life.* New York: Doubleday, 1991.", role="body", paragraph_id="p0010"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="ACKNOWLEDGEMENTS", role="heading", paragraph_id="p0011", heading_level=1, heading_source="explicit"),
                ParagraphUnit(text="Special thanks to Ed and Deb Shapiro, and to Frank Bailin.", role="body", paragraph_id="p0012"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    # The whole notes section goes, not just its first block; the acknowledgements survive.
    assert [job["narration_include"] for job in jobs] == [True, False, False, False, True]


def test_build_editing_jobs_stops_a_level_less_reference_region_at_an_author_section_before_the_next_one():
    """Rethinking Money's `ACKNOWLEDGEMENTS` sits BETWEEN its bibliography and its index, so the
    "next reference section" bound alone would swallow it. Nothing in this repository knows the
    words "acknowledgements" or "about the authors" and Constitution VII forbids adding them, so
    the outline is the whole of the defence: the region also ends at the next section opening at
    the DOCUMENT's own top depth, which is what that heading is (level 1, one of the book's 23).
    """
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="From Scarcity to Sustainable Abundance", role="heading", paragraph_id="p0000", heading_level=1),
                ParagraphUnit(text="The closing narrative paragraph of the final chapter.", role="body", paragraph_id="p0001"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="**BIBLIOGRAPHY**", role="body", paragraph_id="p0002"),
                ParagraphUnit(text="Amato, M. *Complementary Currency Systems.* Milan: Bocconi, 2003.", role="body", paragraph_id="p0003"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="ACKNOWLEDGEMENTS", role="heading", paragraph_id="p0004", heading_level=1, heading_source="explicit"),
                ParagraphUnit(text="Special thanks to Ed and Deb Shapiro, and to Frank Bailin.", role="body", paragraph_id="p0005"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="**INDEX**", role="heading", paragraph_id="p0006", heading_level=2, heading_source="heuristic"),
                ParagraphUnit(text="Bank of En gland, 25– 26, 228n4", role="body", paragraph_id="p0007"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [True, False, True, False]


def test_build_editing_jobs_does_not_run_the_last_reference_region_to_the_end_of_the_document():
    """The accepted residual, asserted so it cannot be widened by accident.

    Rethinking Money's index is followed by `**ABOUT THE AUTHORS**` — a body paragraph with no
    heading role and no level, swept onto the tail of the last index block — and then by the
    publisher's advertising. The end of the document is a legitimate bound for a last reference
    section, but this book shows it is not distinguishable from "the author's biography is behind
    the index", so the region is NOT extended there. 422 of the 432 index paragraphs stay in the
    narration; the biography stays too, and that is the trade this rule is required to make.
    """
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="**INDEX**", role="heading", paragraph_id="p0000", heading_level=2, heading_source="heuristic"),
                ParagraphUnit(text="Bank of En gland, 25– 26, 228n4", role="body", paragraph_id="p0001"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Zumbara, 82 Voucher currency, 170", role="heading", paragraph_id="p0002", heading_level=3, heading_source="explicit"),
                ParagraphUnit(text="**ABOUT THE AUTHORS**", role="body", paragraph_id="p0003"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(
                    text="Bernard Lietaer is one of the most knowledgeable people in the world about money.",
                    role="body",
                    paragraph_id="p0004",
                ),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [False, True, True]


def test_build_editing_jobs_does_not_let_an_untagged_contents_list_anchor_a_reference_region():
    """The Value of Everything's front matter lists `*Notes*`, `*Bibliography*` and
    `*Acknowledgements*` as three ordinary body paragraphs inside ONE block, and — unlike Money &
    Sustainability's — they are NOT tagged with a TOC role (measured 2026-08-06). So the TOC guard
    cannot save this case and a second, structural one has to: a block carrying MORE THAN ONE
    back-matter section title is a list of titles, not a section opening. Without this guard the
    region would start in the front matter and swallow the whole book.

    `*Bibliography*` is deliberately placed LAST, at an edge of the block, so that the edge guard
    alone would let it through. Only the one-title-per-block guard refuses this."""
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Contents", role="body", paragraph_id="p0000"),
                ParagraphUnit(text="Introduction: Making versus Taking", role="body", paragraph_id="p0001"),
                ParagraphUnit(text="*Acknowledgements*", role="body", paragraph_id="p0002"),
                ParagraphUnit(text="*Notes*", role="body", paragraph_id="p0003"),
                ParagraphUnit(text="*Bibliography*", role="body", paragraph_id="p0004"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Chapter 1", role="heading", paragraph_id="p0005", heading_level=2),
                ParagraphUnit(text="The opening narrative paragraph of the book.", role="body", paragraph_id="p0006"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [True, True]


def test_build_editing_jobs_does_not_let_a_title_inside_a_block_anchor_a_reference_region():
    """A back-matter title with paragraphs on BOTH sides of it inside one block is a line in a
    list, not a section opening. There is no honest place to start a region there: including the
    block cuts the prose in front of the title, and skipping to the next block is a guess. So it
    is refused, and the material stays in the narration."""
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="A narrative paragraph that happens to precede the word.", role="body", paragraph_id="p0000"),
                ParagraphUnit(text="Sources", role="body", paragraph_id="p0001"),
                ParagraphUnit(text="A narrative paragraph that happens to follow it.", role="body", paragraph_id="p0002"),
            ]
        ),
        DocumentBlock(paragraphs=[ParagraphUnit(text="More narrative prose, still in the chapter.", role="body", paragraph_id="p0003")]),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    assert [job["narration_include"] for job in jobs] == [True, True]


def test_build_editing_jobs_does_not_let_a_role_less_toc_row_anchor_a_reference_region():
    """The companion of the heading-role TOC case below, for the relaxed anchor: a contents row
    reading "Notes" that carries the `toc_entry` structural role but NOT the heading role must
    still be refused. Dropping the heading requirement must not drop the TOC guard with it."""
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Notes", role="body", structural_role="toc_entry", paragraph_id="p0000"),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Introduction", role="heading", paragraph_id="p0001", heading_level=2),
                ParagraphUnit(text="The opening narrative paragraph of the book.", role="body", paragraph_id="p0002"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    # The row itself is dropped as TOC, by role — but the chapter that follows it is narrated,
    # which it would not be if the row had opened a region.
    assert [job["narration_include"] for job in jobs] == [False, True]


def test_build_editing_jobs_does_not_let_a_toc_row_anchor_a_reference_region():
    """A front-matter contents row reading "Notes" must never open a region: the whole point of
    matching the title EXACTLY, and of refusing a paragraph already tagged as a TOC row."""
    blocks = [
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Contents", role="heading", structural_role="toc_header", paragraph_id="p0000", heading_level=2),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Notes", role="heading", structural_role="toc_entry", paragraph_id="p0001", heading_level=3),
            ]
        ),
        DocumentBlock(
            paragraphs=[
                ParagraphUnit(text="Introduction", role="heading", paragraph_id="p0002", heading_level=2),
                ParagraphUnit(text="The opening narrative paragraph of the book.", role="body", paragraph_id="p0003"),
            ]
        ),
    ]

    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="audiobook")

    # Both contents rows are dropped as TOC, by role — but the chapter that follows them is
    # narrated, which it would not be if the "Notes" row had opened a region.
    assert [job["narration_include"] for job in jobs] == [False, False, True]


def test_build_editing_jobs_marks_mixed_toc_majority_blocks_as_toc_dominant():
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Chapter 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Chapter 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Note on sources", role="body", paragraph_id="p0003"),
    ]

    blocks = [DocumentBlock(paragraphs=paragraphs)]
    jobs = build_editing_jobs(blocks, max_chars=3000, processing_operation="translate")

    assert [job["job_kind"] for job in jobs] == ["llm"]
    assert jobs[0]["toc_dominant"] is True
    assert jobs[0]["toc_paragraph_count"] == 3
    assert jobs[0]["paragraph_count"] == 4


def test_build_editing_jobs_uses_explicit_seventy_percent_toc_dominance_threshold():
    dominant_paragraphs = [
        ParagraphUnit(text=f"Entry {index}", role="body", structural_role="toc_entry", paragraph_id=f"p{index:04d}")
        for index in range(7)
    ] + [
        ParagraphUnit(text=f"Body {index}", role="body", paragraph_id=f"p{index + 7:04d}")
        for index in range(3)
    ]
    non_dominant_paragraphs = [
        ParagraphUnit(text=f"Entry {index}", role="body", structural_role="toc_entry", paragraph_id=f"q{index:04d}")
        for index in range(6)
    ] + [
        ParagraphUnit(text=f"Body {index}", role="body", paragraph_id=f"q{index + 6:04d}")
        for index in range(4)
    ]

    dominant_jobs = build_editing_jobs([DocumentBlock(paragraphs=dominant_paragraphs)], max_chars=3000, processing_operation="translate")
    non_dominant_jobs = build_editing_jobs([DocumentBlock(paragraphs=non_dominant_paragraphs)], max_chars=3000, processing_operation="translate")

    assert dominant_jobs[0]["toc_dominant"] is True
    assert non_dominant_jobs[0]["toc_dominant"] is False


def test_build_editing_jobs_does_not_treat_mixed_embedded_toc_paragraph_as_toc_only():
    compound = ParagraphUnit(text="Conclusion........ 29 Introduction Body start", role="body", paragraph_id="p0000")
    compound.heuristic_embedded_structure_hints = [
        EmbeddedStructureHint(text="Conclusion........ 29", role="body", structural_role="toc_entry"),
        EmbeddedStructureHint(text="Introduction", role="heading", structural_role="body", heading_level=2),
        EmbeddedStructureHint(text="Body start", role="body", structural_role="body"),
    ]

    jobs = build_editing_jobs([DocumentBlock(paragraphs=[compound])], max_chars=3000)

    assert jobs[0]["job_kind"] == "llm"
    assert jobs[0]["toc_dominant"] is False
    assert jobs[0]["toc_paragraph_count"] == 0


def test_build_editing_jobs_post_ai_final_ignores_toc_only_embedded_hints_for_final_authority():
    compound = ParagraphUnit(text="Contents Chapter 1........ 12", role="body", structural_role="body", paragraph_id="p0000")
    compound.heuristic_embedded_structure_hints = [
        EmbeddedStructureHint(text="Contents", role="body", structural_role="toc_header"),
        EmbeddedStructureHint(text="Chapter 1........ 12", role="body", structural_role="toc_entry"),
    ]

    edit_jobs = build_editing_jobs([DocumentBlock(paragraphs=[compound])], max_chars=3000)
    audiobook_jobs = build_editing_jobs(
        [DocumentBlock(paragraphs=[compound])],
        max_chars=3000,
        processing_operation="audiobook",
    )

    assert edit_jobs[0]["job_kind"] == "llm"
    assert edit_jobs[0]["toc_dominant"] is False
    assert edit_jobs[0]["toc_paragraph_count"] == 0
    assert edit_jobs[0]["structure_source"] == "post_ai_final_binding"
    assert audiobook_jobs[0]["narration_include"] is True


def test_build_editing_jobs_pre_ai_diagnostic_uses_toc_only_embedded_hints_for_diagnostic_grouping():
    compound = ParagraphUnit(text="Contents Chapter 1........ 12", role="body", structural_role="body", paragraph_id="p0000")
    compound.heuristic_embedded_structure_hints = [
        EmbeddedStructureHint(text="Contents", role="body", structural_role="toc_header"),
        EmbeddedStructureHint(text="Chapter 1........ 12", role="body", structural_role="toc_entry"),
    ]

    jobs = build_editing_jobs(
        [DocumentBlock(paragraphs=[compound])],
        max_chars=3000,
        structure_phase="pre_ai_diagnostic",
    )

    assert jobs[0]["job_kind"] == "passthrough"
    assert jobs[0]["toc_dominant"] is True
    assert jobs[0]["toc_paragraph_count"] == 1
    assert jobs[0]["structure_source"] == "pre_ai_diagnostic_hint"


def test_build_editing_jobs_degraded_fallback_keeps_toc_only_embedded_hints_as_explicit_fallback():
    compound = ParagraphUnit(text="Contents Chapter 1........ 12", role="body", structural_role="body", paragraph_id="p0000")
    compound.heuristic_embedded_structure_hints = [
        EmbeddedStructureHint(text="Contents", role="body", structural_role="toc_header"),
        EmbeddedStructureHint(text="Chapter 1........ 12", role="body", structural_role="toc_entry"),
    ]

    jobs = build_editing_jobs(
        [DocumentBlock(paragraphs=[compound])],
        max_chars=3000,
        structure_phase="ai_first_degraded_fallback",
    )

    assert jobs[0]["job_kind"] == "passthrough"
    assert jobs[0]["toc_dominant"] is True
    assert jobs[0]["toc_paragraph_count"] == 1
    assert jobs[0]["structure_source"] == "ai_first_degraded_fallback"


def test_build_paragraph_relations_detects_caption_epigraph_and_toc_groups():
    paragraphs = [
        ParagraphUnit(text="[[DOCX_IMAGE_img_001]]", role="image", structural_role="image", paragraph_id="p0000", asset_id="img_001"),
        ParagraphUnit(
            text="Рис. 1. Подпись",
            role="caption",
            structural_role="caption",
            paragraph_id="p0001",
            attached_to_asset_id="img_001",
        ),
        ParagraphUnit(
            text="Богатство заключается не в том, чтобы иметь много имущества.",
            role="body",
            structural_role="epigraph",
            paragraph_id="p0002",
            paragraph_alignment="center",
        ),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0003"),
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0004"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0005"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0006"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert [relation.relation_kind for relation in relations] == [
        "image_caption",
        "epigraph_attribution",
        "toc_region",
    ]
    assert report.total_relations == 3
    assert report.relation_counts == {
        "image_caption": 1,
        "epigraph_attribution": 1,
        "toc_region": 1,
    }


def test_build_semantic_blocks_keeps_epigraph_attribution_pair_together():
    paragraphs = [
        ParagraphUnit(text="Богатство заключается в свободе желаний.", role="body", structural_role="epigraph", paragraph_id="p0000"),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0001"),
        ParagraphUnit(text="Следующий обычный абзац должен перейти в отдельный блок.", role="body", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=70)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Богатство заключается в свободе желаний.",
        "— Эпиктет",
    ]


def test_build_semantic_blocks_keeps_toc_region_together():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Первый обычный абзац после содержания.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=60)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Содержание",
        "Глава 1........ 12",
        "Глава 2........ 18",
    ]


def test_build_semantic_blocks_keeps_epigraph_pair_via_structural_role_even_when_relation_config_excludes_it(monkeypatch):
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("image_caption", "table_caption"),
            "relation_normalization_save_debug_artifacts": True,
        },
    )
    paragraphs = [
        ParagraphUnit(
            text="Богатство заключается не в накоплении вещей, а в свободе от лишнего.",
            role="body",
            structural_role="epigraph",
            paragraph_id="p0000",
        ),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0001"),
        ParagraphUnit(text="Следующий обычный абзац должен остаться отдельным блоком.", role="body", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=55)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Богатство заключается не в накоплении вещей, а в свободе от лишнего.",
        "— Эпиктет",
    ]
    assert [paragraph.text for paragraph in blocks[1].paragraphs] == ["Следующий обычный абзац должен остаться отдельным блоком."]


def test_build_paragraph_relations_records_epigraph_and_isolated_toc_rejections():
    paragraphs = [
        ParagraphUnit(text="Богатство заключается в свободе желаний.", role="body", structural_role="epigraph", paragraph_id="p0000"),
        ParagraphUnit(text="Комментарий редактора", role="body", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0002"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert relations == []
    assert report.rejected_candidate_count == 2
    assert [(decision.relation_kind, decision.reasons) for decision in report.decisions] == [
        ("epigraph_attribution", ("epigraph_without_attribution",)),
        ("toc_region", ("isolated_toc_entry",)),
    ]


def test_build_paragraph_relations_detects_table_caption_and_headerless_toc_run():
    paragraphs = [
        ParagraphUnit(text="<table><tr><td>1</td></tr></table>", role="table", structural_role="table", paragraph_id="p0000", asset_id="table_001"),
        ParagraphUnit(text="Табл. 1. Подпись", role="caption", structural_role="caption", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0003"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert [relation.relation_kind for relation in relations] == ["table_caption", "toc_region"]
    assert report.relation_counts == {"table_caption": 1, "toc_region": 1}


def test_build_paragraph_relations_detects_toc_region_from_structural_hints():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="body", paragraph_id="p0000", heuristic_structural_role_hint="toc_header"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="body", paragraph_id="p0001", heuristic_structural_role_hint="toc_entry"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="body", paragraph_id="p0002", heuristic_structural_role_hint="toc_entry"),
    ]

    relations, report = build_paragraph_relations(paragraphs, structure_phase="pre_ai_diagnostic")

    assert [relation.relation_kind for relation in relations] == ["toc_region_candidate"]
    assert report.relation_counts == {"toc_region_candidate": 1}
    assert report.decisions[0].relation_kind == "toc_region_candidate"
    assert report.decisions[0].structure_source == "pre_ai_diagnostic_hint"


def test_build_paragraph_relations_detects_text_only_toc_region_in_pre_ai_diagnostic():
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="body", paragraph_id="p0000"),
        ParagraphUnit(text="Chapter 1........12", role="body", structural_role="body", paragraph_id="p0001"),
        ParagraphUnit(text="Chapter 2........18", role="body", structural_role="body", paragraph_id="p0002"),
    ]

    relations, report = build_paragraph_relations(paragraphs, structure_phase="pre_ai_diagnostic")

    assert [relation.relation_kind for relation in relations] == ["toc_region_candidate"]
    assert report.relation_counts == {"toc_region_candidate": 1}


def test_semantic_block_units_allow_toc_region_candidate_grouping_only_in_pre_ai_diagnostic():
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="body", paragraph_id="p0000"),
        ParagraphUnit(text="Chapter 1........12", role="body", structural_role="body", paragraph_id="p0001"),
        ParagraphUnit(text="Chapter 2........18", role="body", structural_role="body", paragraph_id="p0002"),
    ]
    candidate_relation = ParagraphRelation(
        relation_id="rel-candidate",
        relation_kind="toc_region_candidate",
        member_paragraph_ids=("p0000", "p0001", "p0002"),
    )

    diagnostic_units = semantic_blocks._build_semantic_block_units(
        paragraphs,
        [candidate_relation],
        structure_phase="pre_ai_diagnostic",
    )
    final_units = semantic_blocks._build_semantic_block_units(
        paragraphs,
        [candidate_relation],
        structure_phase="post_ai_final",
    )

    assert [tuple(paragraph.paragraph_id for paragraph in unit) for unit in diagnostic_units] == [("p0000", "p0001", "p0002")]
    assert [tuple(paragraph.paragraph_id for paragraph in unit) for unit in final_units] == [
        ("p0000",),
        ("p0001",),
        ("p0002",),
    ]


def test_build_paragraph_relations_default_post_ai_mode_ignores_structural_hints():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="body", paragraph_id="p0000", heuristic_structural_role_hint="toc_header"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="body", paragraph_id="p0001", heuristic_structural_role_hint="toc_entry"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="body", paragraph_id="p0002", heuristic_structural_role_hint="toc_entry"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert relations == []
    assert report.relation_counts == {}


def test_build_paragraph_relations_default_post_ai_mode_ignores_text_only_toc_heuristics():
    paragraphs = [
        ParagraphUnit(text="Contents", role="body", structural_role="body", paragraph_id="p0000"),
        ParagraphUnit(text="Chapter 1........12", role="body", structural_role="body", paragraph_id="p0001"),
        ParagraphUnit(text="Chapter 2........18", role="body", structural_role="body", paragraph_id="p0002"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert relations == []
    assert report.relation_counts == {}


def test_build_paragraph_relations_records_rejected_caption_candidate():
    paragraphs = [
        ParagraphUnit(text="Рис. 3. Одинокая подпись", role="caption", structural_role="caption", paragraph_id="p0000"),
        ParagraphUnit(text="Обычный абзац", role="body", paragraph_id="p0001"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert relations == []
    assert report.total_relations == 0
    assert report.rejected_candidate_count == 1
    assert report.decisions[0].decision == "reject"
    assert report.decisions[0].relation_kind == "caption_attachment"
    assert report.decisions[0].reasons == ("caption_without_preceding_asset",)


def test_build_editing_jobs_preserves_marker_count_after_relation_grouping():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=200)
    jobs = build_editing_jobs(blocks, max_chars=200)

    assert len(blocks) == 1
    assert jobs[0]["paragraph_ids"] == ["p0000", "p0001", "p0002"]
    assert str(jobs[0]["target_text_with_markers"]).count("[[DOCX_PARA_") == 3


def test_build_marker_wrapped_block_text_preserves_paragraph_ids_and_boundaries():
    paragraphs = [
        ParagraphUnit(text="Глава", role="heading", paragraph_id="p0001", heading_level=1),
        ParagraphUnit(text="Основной текст", role="body", paragraph_id="p0002"),
    ]

    result = build_marker_wrapped_block_text(paragraphs)

    assert result == "[[DOCX_PARA_p0001]]\n# Глава\n\n[[DOCX_PARA_p0002]]\nОсновной текст"


def test_build_semantic_blocks_splits_front_matter_megablock_between_toc_epigraph_and_heading():
    paragraphs = [
        ParagraphUnit(text="Название документа", role="heading", paragraph_id="p0000", heading_level=1),
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0001"),
        ParagraphUnit(text="Введение........ 1", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Заключение........ 29", role="body", structural_role="toc_entry", paragraph_id="p0003"),
        ParagraphUnit(text="Вас будут ненавидеть всеми за имя Мое", role="body", structural_role="epigraph", paragraph_id="p0004"),
        ParagraphUnit(text="— Марка 13:13", role="body", structural_role="attribution", paragraph_id="p0005"),
        ParagraphUnit(text="Введение", role="heading", paragraph_id="p0006", heading_level=1),
        ParagraphUnit(text="Первый абзац главы.", role="body", paragraph_id="p0007"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=4000, relations=[])

    assert len(blocks) == 4
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == ["Название документа"]
    assert [paragraph.text for paragraph in blocks[1].paragraphs] == ["Содержание", "Введение........ 1", "Заключение........ 29"]
    assert [paragraph.text for paragraph in blocks[2].paragraphs] == ["Вас будут ненавидеть всеми за имя Мое", "— Марка 13:13"]
    assert [paragraph.text for paragraph in blocks[3].paragraphs] == ["Введение", "Первый абзац главы."]


def test_build_semantic_blocks_isolates_mixed_compound_paragraph_with_embedded_boundaries():
    compound = ParagraphUnit(
        text="Conclusion........ 29 \"You will be hated by all\" Introduction My grandfather was convinced",
        role="body",
        paragraph_id="p0003",
    )
    compound.heuristic_embedded_structure_hints = [
        EmbeddedStructureHint(text="Conclusion........ 29", role="body", structural_role="toc_entry"),
        EmbeddedStructureHint(text='"You will be hated by all"', role="body", structural_role="epigraph"),
        EmbeddedStructureHint(text="Introduction", role="heading", structural_role="body", heading_level=2),
        EmbeddedStructureHint(text="My grandfather was convinced", role="body", structural_role="body"),
    ]
    paragraphs = [
        ParagraphUnit(text="Title", role="heading", paragraph_id="p0000", heading_level=1),
        ParagraphUnit(text="Contents", role="body", structural_role="toc_header", paragraph_id="p0001"),
        ParagraphUnit(text="Conclusion........ 29", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        compound,
        ParagraphUnit(text="First ordinary body paragraph.", role="body", paragraph_id="p0004"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=4000, relations=[])

    assert len(blocks) == 4
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == ["Title"]
    assert [paragraph.text for paragraph in blocks[1].paragraphs] == ["Contents", "Conclusion........ 29"]
    assert [paragraph.text for paragraph in blocks[2].paragraphs] == [
        'Conclusion........ 29 "You will be hated by all" Introduction My grandfather was convinced'
    ]
    assert [paragraph.text for paragraph in blocks[3].paragraphs] == ["First ordinary body paragraph."]
