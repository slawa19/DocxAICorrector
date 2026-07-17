# Feature Specification: Structural passthrough gate credits region furniture; gates only genuine unmapped

Date: 2026-07-17
Status: **PLANNED (2026-07-17).** Align the real-document structural passthrough gate with the
Constitution clause "formatting coverage is review DATA, not a gate" + specs 008/010/011: the
`unmapped_source_threshold` / `unmapped_target_threshold` acceptance checks must EXCLUDE agreed
passthrough furniture (front-matter / bounded-TOC / references / index / captions / part-dividers /
page-furniture) from the gated count, and hard-gate ONLY the genuine (non-furniture) remainder against
a generous threshold. No per-book literals; furniture is detected by the EXISTING general region/role/form
detectors. Owner surface: `validation/acceptance.py` (the two threshold checks + the already-computed
`passthrough_*_source/target_count` furniture classification).

Verification: the anti-vacuum + synthetic unit tests below stay green; a one-book real-document gate run
(`test_corpus_structural_passthrough[mazzucato-pdf-full-benchmark]`, ~25 min) shows the furniture no
longer trips the gate and reports what genuine unmapped (if any) remains.
Changelog: 2026-07-17 — created after round-5 characterization (see `## Evidence`).

## Problem (verified — Constitution VII / specs 008/010/011 vs the gate)

`test_corpus_structural_passthrough` requires each real book to structurally validate clean
(`passed=True`). It fails on `unmapped_source_threshold` / `unmapped_target_threshold` — but the gated
count INCLUDES the agreed passthrough furniture that the Constitution + specs 008/010/011 say is credited
and excluded. The furniture is already CLASSIFIED in the same `build_acceptance_verdict`
(`validation/acceptance.py` ~481-515: `passthrough_front_matter_source_count`,
`passthrough_bounded_toc_source_count`, `passthrough_references_source_count`,
`passthrough_index_source_count`, `passthrough_page_furniture_source_count`, caption/part/attribution)
— it is just not SUBTRACTED from the value compared against the threshold. So furniture trips a gate that
the Constitution says coverage must not be.

### Evidence (mazzucato, real gate run 2026-07-17, ~23 min)
`failed_checks = ["unmapped_source_threshold", "unmapped_target_threshold"]`, `passed=false`. Source
unmapped = **155**, of which `references=101`, `index=8`, `front_matter=24`, `page_furniture=4` → **~137
(88%) is furniture**. Target unmapped = 139: a mix of TOC/heading-like short entries ("Preface:",
"Introduction:") and some genuine body prose. `format_neutral_creditable_count=0`
(`filtered_unmapped_source_count == raw == 155` — furniture never subtracted).

## Scope

1. In `validation/acceptance.py`, for BOTH the `unmapped_source_threshold` (~498) and
   `unmapped_target_threshold` (~521) checks: compute a GENUINE-unmapped count = the current
   effective/filtered count MINUS the sum of the agreed passthrough-furniture categories already
   available in the summary (front-matter, bounded-TOC, references, index, page-furniture, caption,
   part-divider, attribution), floored at zero. Gate that GENUINE count against the (generous) threshold.
2. Keep a real hard threshold on the genuine remainder — this is variant 2 (furniture excused, genuine
   coverage regressions still fail). Reuse the existing config threshold
   (`acceptance_max_unmapped_source_paragraphs` / target analogue); do not lower protection for genuine
   body loss.
3. The genuine unmapped is ALREADY surfaced as review-items (spec 011) — unchanged. Emit the
   furniture-credited breakdown in the verdict payload so the credit is auditable.

## Non-goals

- NO per-book literals and NO new region detectors — reuse the EXISTING general
  `_resolve_source_front_matter_boundary` / `_resolve_references_region_start` /
  `_resolve_bounded_toc_region` family (`validation/formatting_coverage.py`) whose outputs are already
  in the summary. (The language-lexicon residual of those anchors is an accepted tail per the
  Constitution — NOT fixed here.)
- NOT weakening the gate for genuine body-paragraph coverage loss (the generous threshold still gates it).
- NOT changing production acceptance semantics beyond correctly excluding furniture from the count
  (production already treats coverage as review-data per spec 010).
- NOT the deeper structure-recognition of real PDFs (F13/F14 residual) — out of scope.

## Anti-regression

- **Anti-vacuum (Constitution VII, mandatory):** a synthetic verdict where a GENUINE body paragraph is
  unmapped and exceeds the genuine threshold → the check STILL FAILS (real body content is still gated).
- A synthetic verdict where ALL unmapped paragraphs are classified furniture (references/index/front-matter/
  TOC/caption) → the check PASSES (furniture excused).
- A mixed synthetic verdict → only the genuine remainder is counted against the threshold.
- Existing `tests/test_acceptance*` / `tests/test_real_document_pipeline_validation.py` /
  `tests/test_document_pipeline_output_validation.py` stay green; pyright ratchet ≤246.
- One real book (`mazzucato`) structural gate re-run: furniture no longer trips it; the report shows the
  genuine residual (accepted as review-data, or under the generous threshold).

## SaaS rationale

Neutral/correctness: the gate now matches the agreed acceptance policy — it no longer fails a run because a
book has a bibliography/index, while still catching genuine formatting-coverage loss on body content.
