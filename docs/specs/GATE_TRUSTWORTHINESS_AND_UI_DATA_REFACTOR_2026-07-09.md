# Gate Trustworthiness & UI-Data Refactor

Date: 2026-07-09
Status: ACTIVE forward spec. **Prerequisite for UI** (`docs/specs/UI/FORMATTING_DISCREPANCY_REPORTING_SPEC_2026-06-15.md`).
Owner surface: production translation-quality gate + acceptance verdict + `formatting_review.txt` writer.
Companion: `docs/specs/GLOBAL_PLAN_2026-06-16.md` (this discharges its Remaining-Work items **1** (gate stability
/ vision, incl. 1‑C/1‑D), **3** (acceptance meaning), and **4** (harness↔prod parity)).

## Purpose

Make the **production** gate emit a **trustworthy, complete** set of formatting-discrepancy data (and a
policy-consistent verdict) that the UI can surface. The UI spec is presentation-only over gate output — so the
gate must produce that output correctly, universally, on any book (no per-book literals — Working Rule #7).

## Verified findings (orchestrator, 2026-07-09)

- **Two gates.** Production `late_phases.py::_build_translation_quality_report` → `quality_status`/`gate_reasons`/
  `formatting_review_items`. Acceptance verdict `acceptance_passed`/`acceptance_failed_checks` is assembled by
  `evaluate_lietaer_acceptance` **entirely in the harness** (`run_lietaer_validation.py`; none in `src/`).
- **Advisory is blind.** Under the run profile (`ui-parity-…-advisory`) production only WARNs, never fails
  (`late_phases.py:2591`), and `role_loss` review-items are emitted **only in the strict branch** → the UI
  (advisory path) gets no `role_loss` data. The trustworthy failing verdict lives only in the harness.
- **Gate blind to heading-demotion.** `role_loss` (`formatting_transfer.py:722`) is computed **only over UNMAPPED
  source**; a heading mapped 1:1 to its target but rendered as list/body (text survived) is invisible. LIVE: Money
  chapters IV/V/VI/VII rendered as `24. Глава IV` … (numbered list) passed silently (`acceptance` failed only on an
  unrelated references `list_fragment`).
- **`[КРИТ]`/false_pair not rendered** — `runtime/artifacts.py:60` knows 2 severities and hardcodes `КРИТ 0`.
- **`list_fragment_regressions_present` false hard-fails on references** — 1‑A references crediting not extended to it.
- **0/4 books pass** — effective unmapped > threshold from mis-tagged back-matter/index (1‑A not extended to
  index-region/attribution); the residue is itself pass-through, not body loss.

## Scope — universal fixes (no per-book literals)

BLOCKERS before UI:
1. **Body-integrity axis (1‑D).** Heading-demotion detector over MAPPED pairs: `_source_format_role==heading`
   (or `heading_level != None`) AND `_target_format_role in {body,list}` AND text survived (containment) AND
   **main-content scoped** (reuse `classify_passthrough_*` provenance: `[front_matter_boundary … references_region_start]`,
   excl. caption/part). New class `content_survived_but_heading_demoted` → `role_loss`, severity `fix`.
2. **Policy-independent discrepancy emission.** Emit review-items (role_loss, unmapped, list_fragment, `[КРИТ]`)
   regardless of strict/advisory, so the UI has data. (Pass/fail severity may stay policy-scaled; the DATA must not.)
3. **`[КРИТ]`/false_pair rendering.** `artifacts.py` becomes a pure `severity` consumer with 3 classes
   (`fix→[ПРАВКА]`, `review→[ПРОВЕРКА]`, `defect→[КРИТ]` from `mapping_text_quality.bad_pair_count`).
4. **list_fragment references crediting** — extend 1‑A: `_is_reviewable_list_fragment_residue` credits samples with
   `source_index ≥ references_region_start` as review, not hard-fail; every hard-fail path emits a review-item.
5. **Passthrough extension (3A).** `classify_passthrough_*` (`formatting_coverage.py`) covers index-region (after
   `references_region_start`, index-like `«…, 60–61»`) + attribution, WITH the anti-vacuum valve (real body still counts).
6. **Harness↔prod verdict parity (item 4).** Extract acceptance-verdict assembly (passthrough summary + thresholds +
   checks) from the harness into a SHARED module (e.g. `validation/acceptance.py`) called by BOTH the harness and
   production finalization → the UI path produces the same trustworthy verdict.

DESIRABLE (not blockers): fold `list_fragment`/`untranslated_*`/`controlled_fallback` into `_HYGIENE_GATE_SPECS`
(1‑C, kills report↔`formatting_review.txt` drift); sentence-break advisory metric; "О" caption-drop rule
(target-heading ≤2 chars with a live source caption = content loss).

NON-GOALS (after UI): item 2 (general controlled-fallback reliability — inactive in these runs; the critical
untranslated-as-success is already a finite hard-fail); item 5 (mazzucato cosmetic tail — partly absorbed by 3A/4).

## Staging (verify between stages)

1. **Foundation** — shared acceptance-verdict module (parity) + policy-independent review-item emission.
2. **Detectors** — heading-demotion (1‑D, main-content scoped) + passthrough index/attribution (3A) + list_fragment
   references credit.
3. **UI-data** — review-item per class + `[КРИТ]` rendering; severity-table completion (1‑C).
4. **Verify** on 4 books (money/lietaer/mazzucato/creatingwealth) + full suite.

## Safe architectural improvements (opportunistic, behavior-preserving, MUST NOT derail the refactor)

`late_phases.py` is ~3871 lines; `_build_translation_quality_report` ~474. Only inside iterations already editing
this code: extract the newly-shared verdict + the hygiene-gate emission into focused modules
(`validation/acceptance.py`, the `_HYGIENE_GATE_SPECS` table as single source). Every change behaviour-preserving:
full test files green before AND after. Do NOT start a standalone big refactor — decompose as the gate edits land.

## Acceptance criteria

- Production (even under advisory) emits `role_loss` (incl. heading-demotion) + `unmapped_source_present` + `[КРИТ]`
  review-items. **Money** surfaces the 4 demoted chapters as `role_loss`; **lietaer/mazzucato/creatingwealth** show
  NO false heading-demotions (back-matter/index/attribution credited).
- Anti-vacuum COUNTER-PROOF: a synthetic real unmapped body paragraph (and a real demoted body heading) still counts.
- Verdict PARITY: production finalization and the harness call the same shared acceptance assembly; same numbers.
- Every hard-fail/warn class emits a review-item (Money `review_items > 0`).
- 4-book verification + full suite green; 1‑A/1‑B/structure/import fixes intact; no per-book literals.

## Anti-regression

- `classify_passthrough_*` extensions keep counting real body (synthetic counter-example test); Money fixture
  (effective 16≤16) not regressed.
- Structure/import fixes untouched — the 1‑D detector is READ-ONLY in the gate. NOTE: enabling 1‑D will HONESTLY
  expose Money's 4 still-demoted chapters (a residual import defect the structure-fix didn't fully close) — that is
  the detector working, not a regression; decide import-follow-up vs conscious accept when it surfaces.
