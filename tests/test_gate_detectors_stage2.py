"""GATE_TRUSTWORTHINESS Stage 2 detectors (universal, main-content scoped):

  1. Body-integrity axis 1‑D — heading-demotion over MAPPED source→target pairs
     (`classify_heading_demotions`): a source heading rendered as body/list in the main
     content (content survived via the mapping) is flagged; TOC / front-matter /
     references / caption / part demotions are excluded by main-content scoping.
  2. 3A pass-through — index-region + attribution categories in
     `classify_passthrough_unmapped_source`, with the anti-vacuum valve preserved.
  3. list_fragment references crediting + hard-fail review-item emission
     (`_is_reviewable_list_fragment_residue` / `_is_citation_form_list_fragment_sample`).

Every assertion is form/region based (no per-book literal). The anti-vacuum counter-proofs
prove a real body paragraph and a real demoted body heading are STILL counted.
"""

from __future__ import annotations

from types import SimpleNamespace

from docxaicorrector.validation.formatting_coverage import (
    classify_heading_demotions,
    classify_passthrough_unmapped_source,
    _is_attribution_text,
    _is_index_row_text,
)
import docxaicorrector.pipeline.late_phases as late_phases


def _src(index, role, hl, mti, text, struct=None):
    return {
        "paragraph_id": f"p{index:04d}",
        "source_index": index,
        "role": role,
        "structural_role": struct or role,
        "heading_level": hl,
        "list_kind": None,
        "mapped_target_index": mti,
        "text_preview": text,
    }


def _tgt(index, hl, text, style=None):
    return {"target_index": index, "heading_level": hl, "text_preview": text, "style_name": style, "mapped": True}


def _payload_with_boundaries(source_rows, target_rows, unmapped_ids=None):
    return {
        "source_registry": source_rows,
        "target_registry": target_rows,
        "unmapped_source_ids": unmapped_ids or [],
    }


# A minimal document whose body begins at a "Chapter I — Title" heading (source_index 3)
# and whose back-matter references region opens with a bare "Notes" title (source_index 20).
def _base_source_rows():
    return [
        _src(0, "body", None, 0, "title page front matter line"),
        _src(1, "body", None, 1, "copyright front matter line"),
        _src(2, "body", None, 2, "dedication front matter line"),
        _src(3, "heading", 1, 3, "chapter i — the real beginning of the report body"),
        _src(4, "body", None, 4, "A long body paragraph of real running prose that ends here."),
    ]


def _base_target_rows():
    return [
        _tgt(0, None, "титульная страница"),
        _tgt(1, None, "копирайт"),
        _tgt(2, None, "посвящение"),
        _tgt(3, 1, "глава i — настоящее начало текста отчета"),
        _tgt(4, None, "Длинный абзац реальной прозы, который заканчивается здесь."),
    ]


# --------------------------------------------------------------------------- #
# Detector 1 — heading-demotion over mapped pairs                             #
# --------------------------------------------------------------------------- #


def test_heading_demotion_fires_in_main_content():
    src = _base_source_rows() + [
        _src(5, "heading", 1, 5, "chapter ii — a demoted body heading in the main content"),
        _src(20, "heading", 1, None, "notes"),
    ]
    tgt = _base_target_rows() + [
        _tgt(5, None, "глава ii — разжалованный заголовок тела", style="Normal"),
    ]
    result = classify_heading_demotions(_payload_with_boundaries(src, tgt))
    assert result["demotion_count"] == 1
    samples = result["samples"]
    assert isinstance(samples, list)
    sample = samples[0]
    assert sample["source_index"] == 5
    assert sample["reason"] == "content_survived_but_heading_demoted"
    assert sample["mapped_target_index"] == 5
    # Provenance boundaries were resolved, not hard-coded.
    assert result["front_matter_boundary_source_index"] == 3
    assert result["references_region_source_start_index"] == 20


def test_heading_demotion_excluded_in_toc_frontmatter_and_backmatter():
    src = _base_source_rows() + [
        # front-matter heading→body (before the body boundary) — must NOT count
        _src(1, "heading", 1, 1, "front matter heading demoted"),
        _src(20, "heading", 1, 20, "notes"),
        # back-matter heading→body (at/after references start) — must NOT count
        _src(21, "heading", 1, 21, "back matter heading demoted after notes"),
    ]
    tgt = _base_target_rows() + [
        _tgt(20, None, "примечания"),
        _tgt(21, None, "разжаловано в конце"),
    ]
    # Rewrite the front-matter target row (index 1) to be a non-heading body target.
    tgt[1] = _tgt(1, None, "заголовок во вводной части разжалован")
    result = classify_heading_demotions(_payload_with_boundaries(src, tgt))
    assert result["demotion_count"] == 0


def test_heading_demotion_ignores_unmapped_and_heading_targets():
    src = _base_source_rows() + [
        # mapped heading -> heading target (NOT a demotion)
        _src(5, "heading", 1, 5, "chapter ii — still a heading"),
        # unmapped heading (belongs to the UNMAPPED role_loss axis, not this one)
        _src(6, "heading", 1, None, "chapter iii — unmapped heading"),
        _src(20, "heading", 1, None, "notes"),
    ]
    tgt = _base_target_rows() + [_tgt(5, 1, "глава ii — по-прежнему заголовок", style="Heading 1")]
    result = classify_heading_demotions(_payload_with_boundaries(src, tgt))
    assert result["demotion_count"] == 0


def test_heading_demotion_skips_caption_and_furniture_target():
    src = _base_source_rows() + [
        _src(5, "caption", None, 5, "figure 2 — a caption carrying a heading-ish role"),
        _src(6, "heading", 1, 6, "chapter ii — mapped onto a page-number furniture target"),
        _src(20, "heading", 1, None, "notes"),
    ]
    tgt = _base_target_rows() + [
        _tgt(5, None, "рисунок 2 — подпись"),
        _tgt(6, None, "12"),  # bare page number -> furniture, not a demotion target
    ]
    result = classify_heading_demotions(_payload_with_boundaries(src, tgt))
    assert result["demotion_count"] == 0


# --------------------------------------------------------------------------- #
# Anti-vacuum counter-proofs                                                   #
# --------------------------------------------------------------------------- #


def test_anti_vacuum_real_unmapped_body_paragraph_is_retained():
    real_body = (
        "This is a genuinely unmapped main-body prose paragraph that argues a substantive "
        "economic point across a full sentence of real running text well outside any "
        "front-matter, table of contents, or page-furniture region and ends properly."
    )
    src = _base_source_rows() + [
        _src(6, "body", None, None, real_body),
        _src(20, "heading", 1, None, "notes"),
    ]
    tgt = _base_target_rows()
    passthrough = classify_passthrough_unmapped_source(
        _payload_with_boundaries(src, tgt, unmapped_ids=["p0006"])
    )
    # The real body paragraph is NOT credited as any pass-through category.
    retained_ids = passthrough["retained_ids"]
    assert isinstance(retained_ids, list)
    assert "p0006" in retained_ids
    assert passthrough["retained_count"] == 1


def test_anti_vacuum_real_demoted_body_heading_is_counted():
    src = _base_source_rows() + [
        _src(5, "heading", 1, 5, "chapter ii — a real demoted body heading"),
        _src(20, "heading", 1, None, "notes"),
    ]
    tgt = _base_target_rows() + [_tgt(5, None, "глава ii — разжалованный заголовок", style="Normal")]
    assert classify_heading_demotions(_payload_with_boundaries(src, tgt))["demotion_count"] == 1


# --------------------------------------------------------------------------- #
# Detector 2 — index / attribution pass-through                               #
# --------------------------------------------------------------------------- #


def test_attribution_detection_form():
    # A short dash-led author credit is attribution; the "Name, <role>" appositive form is
    # NOT credited BY DESIGN (the English occupation word list was removed as a per-book
    # heuristic), and a plain heading / body prose never match.
    assert _is_attribution_text("— gwendolyn and bernard", "body", "body")
    assert not _is_attribution_text("sir mervyn king, governor of the bank of england", "heading", "heading")
    assert not _is_attribution_text("richard timberlake, former professor emeritus of", "heading", "heading")
    assert not _is_attribution_text("households: consumers, employees, savers, investors", "heading", "heading")
    assert not _is_attribution_text(
        "The economy grew rapidly during this decade, and the effects were felt widely across the sector.",
        "body",
        "body",
    )


def test_attribution_does_not_credit_dialogue_line():
    # A short dash-led line ending in sentence-terminal punctuation is a lost dialogue
    # reply (real body loss), NOT an author credit — it must not be credited.
    assert not _is_attribution_text("— Я не согласен с этим решением.", "body", "body")


def test_index_row_detection_form():
    assert _is_index_row_text("chicago plan, 3, 69– 71, 231n15, 231n16")
    assert _is_index_row_text("local currency, 5, 58– 59; berkshare, 75, 88")
    # A body sentence that merely ends in a year is NOT an index row.
    assert not _is_index_row_text("The reform finally arrived in 2010.")
    assert not _is_index_row_text("a plain heading")


def test_passthrough_credits_index_and_attribution_after_references():
    src = _base_source_rows() + [
        _src(20, "heading", 1, None, "notes"),
        _src(21, "heading", 1, None, "chicago plan, 3, 69– 71, 231n15, 231n16"),  # index
        _src(22, "heading", 1, None, "— gwendolyn and bernard"),  # dash-led attribution credit
        _src(23, "body", None, None,
             "A genuine notes-region body paragraph that is long real running prose spanning well past the "
             "substantial-body-prose length threshold, opening with a capital letter and ending with a period."),
    ]
    tgt = _base_target_rows()
    unmapped = ["p0020", "p0021", "p0022", "p0023"]
    passthrough = classify_passthrough_unmapped_source(_payload_with_boundaries(src, tgt, unmapped_ids=unmapped))
    counts = passthrough["category_counts"]
    assert isinstance(counts, dict)
    assert counts["index"] == 1
    assert counts["attribution"] == 1
    # Anti-vacuum: the real notes-region body paragraph is still retained, not silenced.
    retained_ids = passthrough["retained_ids"]
    assert isinstance(retained_ids, list)
    assert "p0023" in retained_ids


# --------------------------------------------------------------------------- #
# Detector 3 — list_fragment references crediting + hard-fail emission        #
# --------------------------------------------------------------------------- #


def _sample(text):
    return SimpleNamespace(text=text, line=1, reason="list_fragment_regressions_present")


def test_list_fragment_standalone_numeric_credited_as_review():
    samples = [_sample("18."), _sample("1491."), _sample("249.")]
    assert late_phases._is_reviewable_list_fragment_residue(samples=samples, gate_source="entry_assembly")


def test_list_fragment_bibliography_notes_line_credited_as_review():
    # A Money-style notes/bibliography residue line (quoted titles, years, "стр.").
    bib = (
        "*Journal of Public Health*, том 87 (1997), № 9, стр. 1491–1498. 56 Джеймс Бьюкен, "
        "«Застывшее желание: смысл денег» (1997). 57 Кеннеди и Литер, «Региональные валюты» (2004), стр. 30."
    )
    assert late_phases._is_citation_form_list_fragment_sample(_sample(bib))
    assert late_phases._is_reviewable_list_fragment_residue(samples=[_sample(bib)], gate_source="entry_assembly")


def test_list_fragment_broken_body_list_still_hard_fails():
    # A genuine broken body list fragment (bullet-led continuation) is NOT credited.
    broken = _sample("- продолжение мысли без завершения")
    assert not late_phases._is_citation_form_list_fragment_sample(broken)
    assert not late_phases._is_reviewable_list_fragment_residue(
        samples=[_sample("18."), broken], gate_source="entry_assembly"
    )
