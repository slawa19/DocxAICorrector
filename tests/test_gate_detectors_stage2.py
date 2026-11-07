"""GATE_TRUSTWORTHINESS Stage 2 detectors (universal, main-content scoped):

  1. Body-integrity axis 1‑D — heading-demotion over MAPPED source→target pairs
     (`classify_heading_demotions`): a source heading rendered as body/list in the main
     content (content survived via the mapping) is flagged; TOC / front-matter /
     references / caption / part demotions are excluded by main-content scoping.
  2. 3A pass-through — index-region + attribution categories in
     `classify_passthrough_unmapped_source`, with the anti-vacuum valve preserved.
  3. list_fragment references crediting + hard-fail review-item emission
     (`_is_reviewable_list_fragment_residue` / `_is_citation_form_list_fragment_sample`).
  4. Spec 064 (end of file): a policy-kept source paragraph is not untranslated body
     (FR-004), list-fragment residue is credited by region/status before form (FR-005), and
     the prose-delivery acceptance check respects the anchor floor (FR-008).

Every assertion is form/region based (no per-book literal). The anti-vacuum counter-proofs
prove a real body paragraph and a real demoted body heading are STILL counted.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

from docxaicorrector.validation.formatting_coverage import (
    classify_heading_demotions,
    classify_passthrough_unmapped_source,
    classify_passthrough_unmapped_target,
    resolve_role_aware_formatting_unmapped_target_summary,
    _is_attribution_text,
    _is_index_row_text,
)
import docxaicorrector.pipeline.late_phases as late_phases
from docxaicorrector.core.models import PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
from docxaicorrector.pipeline import output_validation
from docxaicorrector.pipeline import quality_gate
from docxaicorrector.pipeline import quality_gate_text_detectors
from docxaicorrector.validation import acceptance
from docxaicorrector.validation.acceptance import build_acceptance_verdict


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


# --------------------------------------------------------------------------- #
# 003 list-fragment source list context — the gate-sample resolver (FR-001..005).
# `_is_reviewable_list_fragment_residue` (above) is a DIFFERENT function: it decides
# residue credit for samples that already reached the gate. The list-context filter
# below runs earlier, in `_resolve_list_fragment_regression_gate_samples`, and decides
# which carry-over samples reach the gate at all. The residue tests keep testing the
# credit predicate on entry-less samples; these test the context filter on entries.
# --------------------------------------------------------------------------- #


def _lf_entry(text, list_kind=None, *, from_registry=True, used_fallback=False):
    return SimpleNamespace(
        text=text,
        list_kind=list_kind,
        from_registry=from_registry,
        used_fallback=used_fallback,
    )


def _lf_sample(text, line):
    return SimpleNamespace(text=text, line=line, reason="list_fragment_regressions_present")


def test_resolve_list_fragment_drops_prose_ending_in_number_without_list_context():
    # FR-001/FR-002 (the Mazzucato "…как мы видели в главе 7." class): a body paragraph
    # ending in a trailing ordinal, whose entry and both neighbours are non-list, has no
    # source list context and is DROPPED from the axis — never reaching the hard-fail.
    entries = [
        _lf_entry("Вводный абзац главы."),
        _lf_entry("Как мы видели в главе 7."),
        _lf_entry("Следующий заголовок"),
    ]
    final_markdown = "Вводный абзац главы.\nКак мы видели в главе 7.\nСледующий заголовок"
    sample = _lf_sample("Как мы видели в главе 7.", line=2)
    resolved, source = late_phases._resolve_list_fragment_regression_gate_samples(
        raw_samples=[sample],
        final_markdown=final_markdown,
        assembly_entries=entries,
        source_backed_entry_authority=True,
        topology_projection_supported=False,
    )
    assert source == "entry_assembly"
    assert resolved == []


def test_resolve_list_fragment_keeps_fragment_adjacent_to_ordered_list_entry():
    # FR-005: a genuinely broken fragment whose neighbour IS a source-backed ordered list
    # entry has list context and is KEPT — priority 4 is not blunted where the signal exists.
    entries = [
        _lf_entry("Первый пункт списка", list_kind="ordered"),
        _lf_entry("продолжение оборванной мысли 7."),
        _lf_entry("Обычный абзац."),
    ]
    final_markdown = "Первый пункт списка\nпродолжение оборванной мысли 7.\nОбычный абзац."
    sample = _lf_sample("продолжение оборванной мысли 7.", line=2)
    resolved, source = late_phases._resolve_list_fragment_regression_gate_samples(
        raw_samples=[sample],
        final_markdown=final_markdown,
        assembly_entries=entries,
        source_backed_entry_authority=True,
        topology_projection_supported=False,
    )
    assert source == "entry_assembly"
    assert [getattr(item, "text") for item in resolved] == ["продолжение оборванной мысли 7."]


def test_resolve_list_fragment_still_drops_sample_matching_real_list_entry():
    # FR-003: the existing source-backed-list credit survives — a sample whose own entry is
    # a real ordered list entry is still collapsed (the Lietaer 20→0 / Mazzucato 66→5 credit).
    entries = [
        _lf_entry("Первый пункт списка 7.", list_kind="ordered"),
        _lf_entry("Обычный абзац."),
    ]
    final_markdown = "Первый пункт списка 7.\nОбычный абзац."
    sample = _lf_sample("Первый пункт списка 7.", line=1)
    resolved, source = late_phases._resolve_list_fragment_regression_gate_samples(
        raw_samples=[sample],
        final_markdown=final_markdown,
        assembly_entries=entries,
        source_backed_entry_authority=True,
        topology_projection_supported=False,
    )
    assert source == "entry_assembly"
    assert resolved == []


def test_resolve_list_fragment_legacy_path_returns_raw_samples_unchanged():
    # FR-004: no source-backed entry authority ⇒ no list-context signal ⇒ behave as today.
    sample = _lf_sample("что угодно 7.", line=1)
    resolved, source = late_phases._resolve_list_fragment_regression_gate_samples(
        raw_samples=[sample],
        final_markdown="что угодно 7.",
        assembly_entries=[],
        source_backed_entry_authority=False,
        topology_projection_supported=False,
    )
    assert source == "legacy_markdown"
    assert resolved == [sample]


def test_resolve_list_fragment_drops_sample_with_unresolvable_line():
    # FR-002 edge: a carry-over sample that cannot be resolved to an entry (no `line`) has no
    # list-context signal and is dropped, not hard-failed.
    entries = [_lf_entry("Единственный абзац.")]
    sample = _lf_sample("оторванный фрагмент 7.", line=None)
    resolved, source = late_phases._resolve_list_fragment_regression_gate_samples(
        raw_samples=[sample],
        final_markdown="Единственный абзац.",
        assembly_entries=entries,
        source_backed_entry_authority=True,
        topology_projection_supported=False,
    )
    assert source == "entry_assembly"
    assert resolved == []


# --------------------------------------------------------------------------- #
# 002 gate-report-honesty — review-item anchors (FR-004 / FR-005 / FR-006).    #
# --------------------------------------------------------------------------- #


def _item_sample(item: dict[str, object]) -> dict[str, object]:
    sample = item["sample"]
    assert isinstance(sample, dict)
    return sample


def test_review_item_strips_internal_docx_placeholders_from_anchor():
    # FR-004: a leaked [[DOCX_PARA_…]] + markdown heading marker becomes clean anchor text.
    item = late_phases._build_formatting_review_item(
        reason="content_survived_but_format_role_lost",
        label="loss",
        sample={"text": "[[DOCX_PARA_p0052]]\n### CONTENTS"},
    )
    sample = _item_sample(item)
    assert "[[DOCX_" not in str(sample["text"])
    assert sample["text"] == "CONTENTS"
    assert sample.get("anchor_usable") is not False


def test_review_item_strips_image_placeholder_and_keeps_words():
    item = late_phases._build_formatting_review_item(
        reason="content_survived_but_format_role_lost",
        label="loss",
        sample={"text": "[[DOCX_IMAGE_img7]] Рисунок с подписью"},
    )
    assert _item_sample(item)["text"] == "Рисунок с подписью"


# --------------------------------------------------------------------------- #
# 011 unmapped-TARGET review-items — itemize the retained target residue.      #
# The source side already itemizes (`unmapped_source_paragraphs_review_required`);
# these tests prove the target counterpart carries per-paragraph text_preview,
# credits passthrough (anti-vacuum), caps like the source emitter, and touches   #
# no verdict.                                                                     #
# --------------------------------------------------------------------------- #

# A genuine body target paragraph after the front-matter boundary (source_index 3
# heading → target_boundary 3): long real prose, not furniture/caption/attribution.
_REAL_TARGET_BODY = (
    "Длинный абзац настоящей прозы перевода, который излагает содержательную "
    "экономическую мысль на протяжении целого предложения реального текста и "
    "корректно заканчивается точкой."
)


def _target_payload(unmapped_target_indexes, *, extra_tgt=None, creditable=0):
    return {
        "source_registry": _base_source_rows(),
        "target_registry": _base_target_rows() + list(extra_tgt or []),
        "unmapped_target_indexes": list(unmapped_target_indexes),
        # Presence of split_accounting_creditable_count is what makes the role-aware
        # target summary include this payload (formatting_coverage.py:878).
        "unmapped_target_residual_diagnostics": {"split_accounting_creditable_count": creditable},
    }


def _emit_target_items_from_summary(payload):
    """Drive the production emitter exactly as late_phases does: resolve the role-aware
    target summary, then feed its threaded retained samples/count into the emitter."""
    summary = resolve_role_aware_formatting_unmapped_target_summary([payload])
    items: list[dict[str, object]] = []
    if summary is not None:
        raw_samples = summary.get("retained_target_samples")
        samples = raw_samples if isinstance(raw_samples, list) else []
        raw_retained_count = summary.get("retained_target_count")
        retained_count = raw_retained_count if isinstance(raw_retained_count, int) else 0
        raw_effective = summary.get("effective_unmapped_target_count")
        effective = raw_effective if isinstance(raw_effective, int) else 0
    else:
        samples = []
        retained_count = 0
        effective = 0
    late_phases._emit_unmapped_target_discrepancy_review_items(
        formatting_review_items=items,
        has_role_aware_summary=summary is not None,
        retained_samples=samples,
        retained_count=retained_count,
        effective_unmapped_target_count=effective,
    )
    return items


def _target_items(items):
    return [item for item in items if item["reason"] == "unmapped_target_paragraphs_review_required"]


def test_sc001_genuine_unmapped_body_target_is_itemized_with_text():
    # SC-001/FR-001: the classifier returns a retained_samples row carrying text_preview.
    payload = _target_payload([5], extra_tgt=[_tgt(5, None, _REAL_TARGET_BODY)])
    classified = classify_passthrough_unmapped_target(payload)
    assert classified["retained_indexes"] == [5]
    assert classified["retained_samples"] == [{"target_index": 5, "text_preview": _REAL_TARGET_BODY}]
    # End-to-end through the summary + emitter: exactly one review item carrying the text.
    items = _target_items(_emit_target_items_from_summary(payload))
    assert len(items) == 1
    item = items[0]
    assert item["severity"] == "review"
    assert _item_sample(item)["text"] == _REAL_TARGET_BODY


def test_sc002a_all_passthrough_target_emits_no_item():
    # SC-002(a) ANTI-VACUUM: unmapped target indexes all front-matter (< boundary 3) →
    # retained empty → NO review item (credited passthrough is never surfaced).
    payload = _target_payload([0, 1, 2])
    classified = classify_passthrough_unmapped_target(payload)
    assert classified["retained_indexes"] == []
    assert classified["retained_samples"] == []
    counts = classified["category_counts"]
    assert isinstance(counts, dict)
    assert counts["front_matter"] == 3
    assert _target_items(_emit_target_items_from_summary(payload)) == []


def test_sc002b_one_body_among_passthrough_noise_emits_exactly_one():
    # SC-002(b) ANTI-VACUUM: one genuine body paragraph among front-matter passthrough noise
    # → exactly one item, for the body paragraph, carrying its text.
    payload = _target_payload([0, 1, 2, 5], extra_tgt=[_tgt(5, None, _REAL_TARGET_BODY)])
    classified = classify_passthrough_unmapped_target(payload)
    assert classified["retained_indexes"] == [5]
    items = _target_items(_emit_target_items_from_summary(payload))
    assert len(items) == 1
    assert _item_sample(items[0])["text"] == _REAL_TARGET_BODY


def test_sc003_retained_above_cap_first_item_carries_aggregate_count():
    # SC-003: more retained body targets than the sample cap (8) → first item carries
    # aggregate_count = the true retained total, mirroring the source emitter.
    extra = [_tgt(idx, None, f"{_REAL_TARGET_BODY} №{idx}") for idx in range(5, 17)]
    payload = _target_payload(list(range(5, 17)), extra_tgt=extra)  # 12 genuine body targets
    classified = classify_passthrough_unmapped_target(payload)
    assert classified["retained_count"] == 12
    items = _target_items(_emit_target_items_from_summary(payload))
    assert len(items) == 8  # capped
    assert items[0]["aggregate_count"] == 12
    assert all("aggregate_count" not in item for item in items[1:])


def test_fr004_no_role_aware_summary_falls_back_to_count_only_item():
    # FR-004: no target-split accounting (no summary) but a positive effective count →
    # a single count-only item, never silence.
    items: list[dict[str, object]] = []
    late_phases._emit_unmapped_target_discrepancy_review_items(
        formatting_review_items=items,
        has_role_aware_summary=False,
        retained_samples=[],
        retained_count=0,
        effective_unmapped_target_count=7,
    )
    target = _target_items(items)
    assert len(target) == 1
    assert target[0]["count"] == 7
    assert target[0]["severity"] == "review"
    assert "sample" not in target[0]


def test_sc004_emitter_only_appends_review_items_touches_no_check():
    # SC-004 (DATA-only): the emitter mutates ONLY the passed review-item list; it returns
    # None and takes/returns no failed_checks / verdict structure. A pre-seeded unrelated
    # item is preserved and the addition is purely appended.
    sentinel = {"reason": "unrelated", "label": "x", "count": 1, "severity": "fix"}
    items: list[dict[str, object]] = [sentinel]
    result = late_phases._emit_unmapped_target_discrepancy_review_items(
        formatting_review_items=items,
        has_role_aware_summary=True,
        retained_samples=[{"target_index": 5, "text_preview": _REAL_TARGET_BODY}],
        retained_count=1,
        effective_unmapped_target_count=1,
    )
    assert result is None
    assert items[0] is sentinel
    assert len(items) == 2
    assert items[1]["reason"] == "unmapped_target_paragraphs_review_required"


def test_review_item_does_not_truncate_non_docx_double_bracket():
    # FR-004 anti-regression: a real code sample with "[[" survives untouched.
    item = late_phases._build_formatting_review_item(
        reason="mapping_text_quality_bad_pair",
        label="pair",
        sample={"text": "value = arr[[not a docx placeholder]] end"},
    )
    sample = _item_sample(item)
    assert sample["text"] == "value = arr[[not a docx placeholder]] end"
    assert sample.get("anchor_usable") is not False


def test_review_item_single_symbol_anchor_marked_unusable():
    # FR-006: "$" has <3 locatable characters → aggregated, not shown.
    item = late_phases._build_formatting_review_item(
        reason="content_survived_but_format_role_lost",
        label="loss",
        sample={"text": "$"},
    )
    assert _item_sample(item)["anchor_usable"] is False


def test_review_item_bare_heading_marker_marked_unusable():
    item = late_phases._build_formatting_review_item(
        reason="content_survived_but_format_role_lost",
        label="loss",
        sample={"text": "###"},
    )
    sample = _item_sample(item)
    assert sample["text"] == ""
    assert sample["anchor_usable"] is False


def test_review_item_role_loss_heading_level_names_word_style():
    # FR-005: heading_level=1 → "Заголовок 1".
    item = late_phases._build_formatting_review_item(
        reason="content_survived_but_heading_demoted",
        label="loss",
        sample={
            "text": "Глава десятая",
            "reason": "content_survived_but_heading_demoted",
            "role": "heading",
            "heading_level": 1,
        },
    )
    assert item["action_style"] == "Заголовок 1"


def test_review_item_heading_role_without_level_names_generic_style():
    item = late_phases._build_formatting_review_item(
        reason="content_survived_but_format_role_lost",
        label="loss",
        sample={
            "text": "Введение",
            "reason": "content_survived_but_format_role_lost",
            "role": "heading",
            "heading_level": None,
        },
    )
    assert item["action_style"] == "Заголовок"


def test_review_item_body_role_carries_no_action_style():
    item = late_phases._build_formatting_review_item(
        reason="mapping_text_quality_bad_pair",
        label="pair",
        sample={"text": "Совсем другой перевод", "source_text": "Original", "role": "body"},
    )
    assert "action_style" not in item


def test_review_item_word_style_map_is_pure():
    style = late_phases._review_item_word_style
    assert style(role="heading", structural_role=None, heading_level=2) == "Заголовок 2"
    assert style(role="body", structural_role=None, heading_level=5) == "Заголовок 5"
    assert style(role=None, structural_role="heading", heading_level=None) == "Заголовок"
    assert style(role="list", structural_role=None, heading_level=None) is None
    assert style(role=None, structural_role=None, heading_level=None) is None


def test_heading_demotion_serializer_carries_heading_level():
    serialized = late_phases._serialize_heading_demotion_sample(
        {
            "text_preview": "Глава десятая",
            "target_text_preview": "глава десятая",
            "source_role": "heading",
            "source_structural_role": None,
            "source_heading_level": 2,
            "source_index": 12,
            "mapped_target_index": 30,
        }
    )
    assert serialized["heading_level"] == 2


# =========================================================================== #
# Spec 064 — the gate half: FR-004 (R-2), FR-005 (R-3), FR-008 (R-6).          #
# =========================================================================== #
#
# Measured on the 2026-11-07 four-book rerun (`D:\Temp\docxai-runs\2026-11-07-translate-after`,
# outside git):
#
# * FR-004: Money & Sustainability was BLOCKED by ``untranslated_body_text_above_threshold`` on
#   19 027 chars / 3.5 % that were entirely ``policy_kept_source`` reference paragraphs.
# * FR-005: ``list_fragment_regressions_present`` hard-failed acceptance on Creating Wealth (11
#   gated), Rethinking Money (2) and The Value of Everything (42) — wrapped tails of notes /
#   bibliography entries ending in a year, all in the back-matter region or policy-kept.
# * FR-008: ``untranslated_prose_not_delivered`` failed Rethinking Money on one block of two
#   characters, the diagram label «2b».
#
# Every rule here keys on a recorded STATUS, a REGION resolved by the existing provenance, or
# the existing anchor floor — never on the words of a book (Constitution VII). Each credit has a
# counter-proof on the same input shape without the signal.


class _Context:
    def __init__(self, operation: str = "translate", *, policy: str = "strict") -> None:
        self.processing_operation = operation
        self.uploaded_filename = "book.docx"
        self.translation_domain = "general"
        self.app_config = {"translation_output_quality_gate_policy": policy}


# English running prose: >= 280 chars, >= 30 latin words, not bibliography/URL dominant.
_ENGLISH_BODY = (
    "The company kept the same policy for another year and nobody in the office was willing "
    "to explain why the numbers had moved so far away from the plan that everyone had signed "
    "in the spring, so the meeting ended without a decision and the team went back to work on "
    "the parts of the product that were still moving forward without any argument at all."
)
# One paragraph that alone crosses BOTH catastrophic thresholds (>= 2000 chars, >= 2 %).
_LONG_ENGLISH_BODY = " ".join([_ENGLISH_BODY] * 7)


def _entry(
    text: str,
    index: int,
    *,
    role: str = "body",
    list_kind: str | None = None,
    heading_level: int | None = None,
    status: str | None = "accepted",
    from_registry: bool = True,
    used_fallback: bool = False,
) -> output_validation.FinalAssemblyEntry:
    return output_validation.FinalAssemblyEntry(
        text=text,
        block_index=1,
        paragraph_id=f"p{index:04d}",
        source_index=index,
        role=role,
        structural_role=role,
        heading_level=heading_level,
        list_kind=list_kind,
        from_registry=from_registry,
        used_fallback=used_fallback,
        paragraph_status=status,
    )


def _assembly(entries) -> output_validation.FinalMarkdownAssemblyResult:
    entries = tuple(entries)
    return output_validation.FinalMarkdownAssemblyResult(
        final_markdown="\n\n".join(entry.text for entry in entries),
        entries=entries,
        diagnostics=output_validation.FinalAssemblyDiagnostics(),
    )


def _report(assembly, *, artifacts: list[str] | None = None, operation: str = "translate") -> dict:
    return quality_gate._build_translation_quality_report(
        context=_Context(operation),
        final_markdown=assembly.final_markdown,
        formatting_diagnostics_artifacts=artifacts or [],
        assembly_result=assembly,
        runtime_display_markdown=assembly.final_markdown,
    )


# --------------------------------------------------------------------------------------- #
# FR-004 — ``policy_kept_source`` is the third exemption of the untranslated-body numerator
# --------------------------------------------------------------------------------------- #


def _english_document(status: str | None):
    return _assembly(
        [
            _entry("## Библиография", 0, role="heading", heading_level=2),
            _entry(_LONG_ENGLISH_BODY, 1, status=status),
        ]
    )


def test_policy_kept_source_english_paragraph_is_not_untranslated_body():
    report = _report(_english_document(PARAGRAPH_STATUS_POLICY_KEPT_SOURCE))

    assert report["untranslated_body_text_count"] == 0
    assert report["untranslated_body_text_chars"] == 0
    assert "untranslated_body_text_above_threshold" not in report["gate_reasons"]
    assert "untranslated_body_text_review_required" not in report["gate_reasons"]
    assert report["quality_status"] != "fail"


def test_same_english_paragraph_without_the_status_still_blocks_translate():
    """Counter-proof (anti-regression 2): the exemption is the STATUS, not the text. The
    identical paragraph recorded ``accepted`` still crosses both thresholds and is fatal."""
    report = _report(_english_document("accepted"))

    assert report["untranslated_body_text_chars"] >= quality_gate._UNTRANSLATED_BODY_FAIL_MIN_CHARS
    assert report["untranslated_body_text_ratio"] >= quality_gate._UNTRANSLATED_BODY_FAIL_RATIO
    assert "untranslated_body_text_above_threshold" in report["gate_reasons"]
    assert report["quality_status"] == "fail"


def test_no_recorded_status_is_not_an_exemption():
    """A plain-text block carries ``paragraph_status=None`` — no disposition, no exemption."""
    report = _report(_english_document(None))

    assert "untranslated_body_text_above_threshold" in report["gate_reasons"]


def test_ratio_denominator_is_still_the_whole_delivered_markdown():
    """FR-004: the policy-kept paragraph leaves the NUMERATOR only. The denominator stays the
    whole delivered markdown, policy-kept text included."""
    assembly = _assembly(
        [
            _entry(_ENGLISH_BODY, 0, status="accepted"),
            _entry(_LONG_ENGLISH_BODY, 1, status=PARAGRAPH_STATUS_POLICY_KEPT_SOURCE),
        ]
    )
    report = _report(assembly)

    assert report["untranslated_body_text_count"] == 1
    assert report["untranslated_body_text_chars"] == len(_ENGLISH_BODY)
    expected_ratio = len(_ENGLISH_BODY) / len(
        quality_gate._strip_structural_markdown_prefix(assembly.final_markdown)
    )
    assert report["untranslated_body_text_ratio"] == round(expected_ratio, 4)


def test_policy_kept_source_heading_is_not_an_untranslated_structural_element():
    heading = "## Selected Bibliography Of Works Consulted"
    kept = _assembly([_entry(heading, 0, role="heading", heading_level=2, status=PARAGRAPH_STATUS_POLICY_KEPT_SOURCE)])
    accepted = _assembly([_entry(heading, 0, role="heading", heading_level=2, status="accepted")])

    assert quality_gate._collect_untranslated_structural_samples(
        final_markdown=kept.final_markdown, assembly_entries=kept.entries
    ) == []
    # Counter-proof: the same heading without the status is still reported.
    assert len(
        quality_gate._collect_untranslated_structural_samples(
            final_markdown=accepted.final_markdown, assembly_entries=accepted.entries
        )
    ) == 1


# --------------------------------------------------------------------------------------- #
# FR-005 — list-fragment residue credited by REGION and STATUS before form
# --------------------------------------------------------------------------------------- #

# The Creating Wealth shape: a notes entry wrapped by the PDF layer, its tail a separate
# body paragraph ending in a year. One citation signal (the year) — the form credit alone
# does NOT take it, which is exactly why it hard-failed acceptance.
_NOTE_HEAD = "- 13. Dennis and Donella Meadows, Jorgen Randers and William Behrens. *The Limits to Growth*. Universe Books, 1972; Donella"
_NOTE_TAIL = "Meadows, Jorgen Randers and Dennis L. Meadows. *Limits to Growth: The 30-Year Update*. Chelsea Green, 2004."
_NOTE_NEXT = "- 14. Расчёт предоставлен автором на основе его собственных данных."


def _registry_row(index: int, role: str, text: str, heading_level: int | None = None) -> dict[str, object]:
    return {
        "paragraph_id": f"p{index:04d}",
        "source_index": index,
        "role": role,
        "structural_role": role,
        "heading_level": heading_level,
        "list_kind": None,
        "mapped_target_index": index,
        "text_preview": text,
    }


def _notes_document(tmp_path: Path, *, notes_title: bool, tail_status: str = "accepted"):
    """Body, a bare back-matter title, then a wrapped note. ``notes_title=False`` drops the
    title from the source registry: the same text with no region anchor."""
    entries = [
        _entry("Основной текст главы, переведённый полностью и без замечаний.", 0),
        _entry("## Примечания", 1, role="heading", heading_level=2),
        _entry(_NOTE_HEAD, 2, role="list", list_kind="unordered"),
        _entry(_NOTE_TAIL, 3, status=tail_status),
        _entry(_NOTE_NEXT, 4, role="list", list_kind="unordered"),
    ]
    registry = [
        _registry_row(0, "body", "chapter text"),
        _registry_row(1, "heading", "notes" if notes_title else "a chapter heading", 1),
        _registry_row(2, "list", "13. dennis and donella meadows"),
        _registry_row(3, "body", "meadows, jorgen randers"),
        _registry_row(4, "list", "14. calculation"),
    ]
    artifact = tmp_path / "formatting_diagnostics.json"
    artifact.write_text(json.dumps({"source_registry": registry}), encoding="utf-8")
    return _assembly(entries), [str(artifact)]


def _broken_body_list_document(tmp_path: Path):
    """The same wrapped-tail shape, but in the MAIN BODY, BEFORE the back-matter title."""
    entries = [
        _entry("- 1. Первый пункт списка в основном тексте главы, без завершения", 0, role="list", list_kind="ordered"),
        _entry("Green, 2004.", 1),
        _entry("- 2. Второй пункт списка.", 2, role="list", list_kind="ordered"),
        _entry("## Примечания", 3, role="heading", heading_level=2),
        _entry("- 1. См. главу 9.", 4, role="list", list_kind="ordered"),
    ]
    registry = [
        _registry_row(0, "list", "1. first item"),
        _registry_row(1, "body", "green, 2004."),
        _registry_row(2, "list", "2. second item"),
        _registry_row(3, "heading", "notes", 1),
        _registry_row(4, "list", "1. see chapter 9."),
    ]
    artifact = tmp_path / "formatting_diagnostics.json"
    artifact.write_text(json.dumps({"source_registry": registry}), encoding="utf-8")
    return _assembly(entries), [str(artifact)]


def test_note_tail_in_back_matter_region_is_credited_to_review(tmp_path):
    assembly, artifacts = _notes_document(tmp_path, notes_title=True)
    report = _report(assembly, artifacts=artifacts)

    assert report["list_fragment_regression_gate_source"] == "entry_assembly"
    assert report["list_fragment_regression_count"] == 1
    # Precondition: form alone does not credit this line (the measured defect).
    sample = report["list_fragment_regression_samples"][0]
    assert not quality_gate._is_citation_form_list_fragment_sample(
        type("S", (), {"text": sample["text"], "line": sample["line"]})()
    )
    assert "list_fragment_regressions_review_required" in report["gate_reasons"]
    assert "list_fragment_regressions_present" not in report["gate_reasons"]
    verdict = build_acceptance_verdict({"translation_quality_report": report})
    assert "list_fragment_regressions_present" not in verdict["failed_checks"]


def test_note_tail_without_region_anchor_still_hard_fails(tmp_path):
    """Counter-proof: identical text and neighbours, no back-matter title in the registry —
    no region signal, no credit (Constitution VII)."""
    assembly, artifacts = _notes_document(tmp_path, notes_title=False)
    report = _report(assembly, artifacts=artifacts)

    assert report["list_fragment_regression_count"] == 1
    assert "list_fragment_regressions_present" in report["gate_reasons"]
    verdict = build_acceptance_verdict({"translation_quality_report": report})
    assert "list_fragment_regressions_present" in verdict["failed_checks"]


def test_policy_kept_source_tail_is_credited_without_a_region_anchor(tmp_path):
    """The Rethinking Money shape: the entry is ``policy_kept_source`` — STATUS alone
    credits it, whatever the registry says about the region."""
    assembly, artifacts = _notes_document(
        tmp_path, notes_title=False, tail_status=PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
    )
    report = _report(assembly, artifacts=artifacts)

    assert report["list_fragment_regression_count"] == 1
    assert "list_fragment_regressions_review_required" in report["gate_reasons"]
    assert "list_fragment_regressions_present" not in report["gate_reasons"]


def test_broken_body_list_before_the_back_matter_region_still_hard_fails(tmp_path):
    """Anti-regression 3: a broken list in the MAIN BODY is not credited by a back-matter
    region that exists later in the same document."""
    assembly, artifacts = _broken_body_list_document(tmp_path)
    report = _report(assembly, artifacts=artifacts)

    assert report["list_fragment_regression_count"] >= 1
    assert "list_fragment_regressions_present" in report["gate_reasons"]
    assert "list_fragment_regressions_review_required" not in report["gate_reasons"]


def test_apparatus_credit_needs_a_source_backed_resolved_entry():
    samples = [type("S", (), {"text": _NOTE_TAIL, "line": line})() for line in (1, 3, 5, 99)]
    entries = (
        _entry("x", 10),  # line 1 -> region (source_index 10 >= 5)
        _entry("y", 11, from_registry=False, used_fallback=True),  # line 3 -> fallback entry
        _entry("z", 2),  # line 5 -> before the region
    )
    markdown = "x\n\ny\n\nz"
    credited = quality_gate._list_fragment_apparatus_credited_lines(
        samples=samples,
        final_markdown=markdown,
        assembly_entries=entries,
        references_region_start=5,
    )
    # line 99 does not resolve to an entry: no signal, no credit.
    assert credited == frozenset({1})
    assert (
        quality_gate._list_fragment_apparatus_credited_lines(
            samples=samples,
            final_markdown=markdown,
            assembly_entries=entries,
            references_region_start=None,
        )
        == frozenset()
    )


def test_residue_with_one_uncredited_body_fragment_still_hard_fails():
    credited = type("S", (), {"text": _NOTE_TAIL, "line": 1})()
    broken = type("S", (), {"text": "- продолжение мысли без завершения", "line": 2})()
    assert quality_gate._is_reviewable_list_fragment_residue(
        samples=[credited], gate_source="entry_assembly", apparatus_credited_lines={1}
    )
    assert not quality_gate._is_reviewable_list_fragment_residue(
        samples=[credited, broken], gate_source="entry_assembly", apparatus_credited_lines={1}
    )
    # The credit never reaches the legacy markdown path (no entries, no region, no status).
    assert not quality_gate._is_reviewable_list_fragment_residue(
        samples=[credited], gate_source="legacy_markdown", apparatus_credited_lines={1}
    )


# --------------------------------------------------------------------------------------- #
# FR-008 — prose residue under the anchor floor is not "untranslated prose delivered"
# --------------------------------------------------------------------------------------- #


def _prose_check(count: int, chars: int) -> dict[str, object]:
    verdict = build_acceptance_verdict(
        {
            "model_accounting": {
                "untranslated_prose_block_delivery_count": count,
                "untranslated_prose_block_delivery_chars": chars,
                "untranslated_prose_block_delivery_kind_counts": {"source_text_fallback": count} if count else {},
            }
        }
    )
    return next(check for check in verdict["checks"] if check["name"] == "untranslated_prose_not_delivered")


def test_two_character_block_under_the_anchor_floor_passes():
    """The recorded Rethinking Money case: one block, «2b», 2 characters."""
    check = _prose_check(1, 2)
    assert check["passed"] is True
    assert check["untranslated_prose_below_anchor_floor"] is True
    assert check["untranslated_prose_block_delivery_count"] == 1


def test_block_at_the_anchor_floor_still_fails():
    check = _prose_check(1, quality_gate_text_detectors.REVIEW_ANCHOR_MIN_VISIBLE_CHARS)
    assert check["passed"] is False
    assert check["untranslated_prose_below_anchor_floor"] is False


def test_several_tiny_blocks_whose_total_reaches_the_floor_still_fail():
    """The ledger holds only the run total; it cannot prove each of two 2-character blocks
    is below the floor, so it does not guess."""
    assert _prose_check(2, 4)["passed"] is False


def test_real_prose_block_still_fails_and_zero_still_passes():
    assert _prose_check(1, 33)["passed"] is False
    assert _prose_check(0, 0)["passed"] is True


def test_one_anchor_floor_in_the_repository():
    """FR-008 reuses the floor; it does not add a second one. The acceptance module and the
    gate share the same object, and the gate no longer spells the floor as a literal."""
    assert acceptance.REVIEW_ANCHOR_MIN_VISIBLE_CHARS is quality_gate.REVIEW_ANCHOR_MIN_VISIBLE_CHARS
    assert quality_gate_text_detectors.REVIEW_ANCHOR_MIN_VISIBLE_CHARS == 3
    tree = ast.parse(Path(quality_gate.__file__).read_text(encoding="utf-8"))
    literal_floor_comparisons = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Call)
        and isinstance(node.left.func, ast.Name)
        and node.left.func.id == "_review_anchor_visible_char_count"
        and any(isinstance(comparator, ast.Constant) for comparator in node.comparators)
    ]
    assert literal_floor_comparisons == []
