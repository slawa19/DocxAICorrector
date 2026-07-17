# Feature Specification: Coverage is review DATA — neutralize the structural passthrough coverage gate

Date: 2026-07-17
Status: **PLANNED (2026-07-17).** Fix a defect against the Constitution. Constitution VII already
binds (lines 139-158): *"Formatting coverage is review DATA, not a verdict gate … Any check that
treats residual unmapped coverage as a HARD failure — including the real-document structural
passthrough gate — is a defect against this principle: it MUST emit the residual as review data, and a
genuine coverage tail with no general repair rule is ACCEPTED, not gated."* The acceptance verdict
still hard-gates on the unmapped-source / unmapped-target coverage axes. This spec removes that hard
gate: the coverage checks become ADVISORY (review data), matching the constitution + specs 008/010/011,
while all NON-coverage structural gates (openable DOCX, placeholder markup, caption/heading conflicts,
translation-quality fails, image/block integrity) stay hard.

Supersedes the GATE decision of spec 037 (variant 2 "hard-gate the genuine remainder"). Spec 037's
furniture-crediting arithmetic (`resolve_genuine_unmapped_count` + the credited/genuine audit fields) is
KEPT — it now feeds the review-DATA payload instead of a pass/fail branch. Owner surface:
`validation/acceptance.py` (the `unmapped_source_threshold`, `unmapped_target_threshold`, and the
coverage half of `formatting_diagnostics_threshold` checks).

Verification: the rewritten synthetic + breadth tests below stay green (genuine loss SURFACED in the
payload, never in `failed_checks`); the golden `acceptance_verdict_clean.json` regenerates additively;
pyright ratchet ≤246; the saved real mazzucato/lietaer breadth reports (`test_breadth_*`) — which
previously failed acceptance PURELY on these coverage checks — now report `passed` free of the three
coverage checks. Changelog: 2026-07-17 — created after owner chose "coverage → review-data" over
spec-037 variant-2, once the furniture credit proved necessary-but-insufficient (source genuine 18 >
per-book 12; target furniture unclassified → 139) and the Constitution was found to already mandate
this.

## Problem (verified — Constitution VII lines 149-153 vs the live verdict)

`build_acceptance_verdict` (`validation/acceptance.py`) still emits three checks whose FAILURE enters
`failed_checks` on residual unmapped COVERAGE:

1. `unmapped_source_threshold` (~596): fails when `genuine_unmapped_source_count > mismatch_threshold`.
2. `unmapped_target_threshold` (~622): fails when `genuine_unmapped_target_count > unmapped_target_threshold`.
3. `formatting_diagnostics_threshold` (~562): its pass condition ANDs a coverage clause
   (`explicit_unmapped_source_count <= mismatch_threshold`) with the genuine structural clause
   (`total_caption_heading_conflicts == 0`).

The Constitution binds these coverage axes as review DATA, not a gate. The real-document structural
passthrough gate (`test_corpus_structural_passthrough`) is named IN the constitution as a check that
must NOT hard-fail on this. Furniture-crediting (spec 037) reduced the count but cannot green the gate,
because a genuine coverage tail with no general repair rule is — per the constitution — ACCEPTED, not
gated. So the gate itself is the defect, not the residual.

## Scope

1. In `validation/acceptance.py`:
   - `unmapped_source_threshold` and `unmapped_target_threshold` become ADVISORY exactly like the
     existing `emphasis_coverage_advisory` / `paragraph_break_advisory` checks: `passed=True`
     unconditionally, `applicable=True`, add `failed_reason="advisory_only"` and `review_data=True`.
     KEEP every existing detail field (genuine counts, credited furniture, per-category provenance,
     region indices) — the review DATA must stay fully auditable. ADD a NON-gating
     `genuine_exceeds_threshold: bool` (genuine > threshold) so the residual severity is visible in the
     payload WITHOUT gating.
   - `formatting_diagnostics_threshold`: drop the coverage clause from its `passed` condition — gate ONLY
     on `total_caption_heading_conflicts == 0` (a genuine structural conflict, not coverage). Keep the
     unmapped-count fields in the payload; add the same `genuine_exceeds_threshold` review marker for the
     source axis.

     > **Superseded by spec 041 P1-4.** `formatting_diagnostics_threshold` is `applicable` only when a
     > `mismatch_threshold` is configured, but production resolves `mismatch_threshold=None`, so its caption
     > clause was ignored by the roll-up and a real caption→heading conflict published GREEN. Spec 041
     > moves the hard caption/heading gate to a SEPARATE `caption_heading_conflict_absent` check that is
     > `applicable` whenever formatting diagnostics were computed (independent of any threshold), so it
     > gates unconditionally in production. `formatting_diagnostics_threshold` keeps its (now
     > redundant-safe) caption clause for backward compatibility with existing goldens/tests.
2. Do NOT touch any other check. `pipeline_succeeded`, `output_docx_openable`, `no_placeholder_markup`,
   `reader_cleanup_stage_completed`, `page_placeholder_heading_concat_hygiene_applied`,
   `translation_quality_report_not_failed`, the bullet/fragment/mixed-script quality checks, the
   TOC-body-concat check, and the injected structural-comparison checks all keep their current gating.
3. Keep spec 037's `resolve_genuine_unmapped_count` and all credited/genuine audit fields — they now
   populate the advisory review DATA rather than a pass/fail branch.

## Non-goals

- NOT loosening any NON-coverage gate. Caption/heading conflict stays hard-gated; openability, placeholder
  markup, translation-quality fails, image/block integrity are untouched.
- NO per-book literals, NO new region detectors (Constitution VII; the anchor-lexicon residual is an
  accepted tail).
- NOT the deeper structure recognition of real PDFs (F13/F14) — the genuine coverage tail is now
  ACCEPTED review data, which is the whole point; there is nothing left to "fix" to green the gate.

## Anti-regression (Constitution VII — the anti-vacuum is now enforced on the DATA, not the gate)

The furniture credit must not HIDE genuine loss in the review data, even though coverage no longer gates:

- **Anti-vacuum (mandatory):** a synthetic verdict where a GENUINE body paragraph is unmapped and exceeds
  the threshold → `genuine_unmapped_source_count` / `..._target_count` STILL rises by exactly one and
  `genuine_exceeds_threshold` is `True` (the loss is honestly surfaced), while the check's `passed`
  stays `True` and the name is NOT in `failed_checks` (coverage is review data, not a gate).
- A synthetic verdict where ALL unmapped paragraphs are furniture → genuine count is 0,
  `genuine_exceeds_threshold` is `False`.
- A mixed verdict → only the genuine remainder is reflected in the genuine count; furniture is credited.
- The saved real mazzucato/lietaer breadth reports (`test_breadth_*`): the three coverage checks are
  absent from `failed_checks`, the genuine/furniture provenance is present, and the counter-proof
  (inject one genuine body loss) still raises the genuine COUNT by one (DATA honest) — but no longer
  flips a gate.
- Existing `tests/test_acceptance*` / `tests/test_real_document_pipeline_validation.py` /
  `tests/test_document_pipeline_output_validation.py` stay green; golden `acceptance_verdict_clean.json`
  regenerates (additive review fields only, `passed`/`failed_checks` unchanged for the clean fixture);
  pyright ratchet ≤246.

## SaaS rationale

Correctness/honesty: the verdict now matches the single enshrined acceptance policy — a book with a
bibliography, index, front-matter, or a genuine untranslatable coverage tail no longer FAILS the run;
the residual is surfaced for human review. Genuine structural defects (caption/heading conflicts,
placeholder markup, unopenable output, quality-gate fails) still hard-fail. This aligns the real-document
test gate with production, which already treats coverage as review data (spec 010).
