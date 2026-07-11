# Gate Trustworthiness & UI-Data Refactor

Date: 2026-07-09
Status: **IMPLEMENTED / SUPERSEDED (2026-07-11) by `specs/001-…` through `specs/009-…`.** This document was the
planning spec that opened the gate-honesty workstream; all six pre-UI blockers below are discharged (see
"Discharge status" at the end). It is kept as lineage. New work goes in `specs/<NNN>-<slug>/`, not here.

Changelog:
- 2026-07-09 — Corrected the heading-demotion sections after tracing the Money `24. Глава IV` root cause to
  `output_validation._normalize_final_entry_list_fragments` (final-markdown assembly), NOT PDF import as previously
  claimed. The defect was fixed in `da6789b`; the 1‑D detector's expected count on Money is now zero.
- 2026-07-10 — **The entry above is RETRACTED: it was wrong.** A fresh full-tier run (`20260710T_money_verify`)
  shows the defect is LIVE. The output markdown still contains `24. Глава IV`, `16. Глава V`, `30. Глава VI`,
  `3. Глава VII`, and the DOCX renders them `Normal` + `numPr`, while chapters VIII/IX are correct `Heading 1`.
  `da6789b` closed only ONE demotion path (the entry-assembly carry-over in `_normalize_final_entry_list_fragments`).
  The LIVE path is `output_validation.normalize_false_fragment_headings_markdown`, reached from
  `late_phases._apply_runtime_display_structure_compatibility_cleanup` (`late_phases.py:127`) — a source-blind regex
  pass whose own comment calls it "display-only" even though `late_phases.py:1080` feeds its output to the DOCX
  rebuild. The 2026-07-09 claim was made from `classify_heading_demotions == 0` and the registry, without opening the
  produced document. Constitution VIII exists for exactly this: verify against the artifact, not the report.
- 2026-07-11 — **CLOSED.** `specs/001-heading-role-preservation` fixed the LIVE demotion: it found TWO
  markdown demotion paths (`normalize_false_fragment_headings_markdown` AND
  `normalize_list_fragment_regressions_markdown`), both now keyed to the source role via the assembly registry.
  Verified on a live run — Money chapters IV–VII render `Heading 1`. All six blockers are discharged by
  `specs/001…009` (mapping in "Discharge status"). The stale Anti-regression note that still asserted
  "`da6789b` closed it; expected count zero" was corrected in place (it was a survivor of the 2026-07-09
  mistake this Changelog already retracted).
Owner surface: production translation-quality gate + acceptance verdict + `formatting_review.txt` writer.
Companion: `docs/specs/GLOBAL_PLAN_2026-06-16.md` (this discharged its Remaining-Work items **1** (gate stability
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
  source**; a heading mapped 1:1 to its target but rendered as list/body (text survived) is invisible — this is the
  reason the axis is needed. The Money chapters IV/V/VI/VII (`24. Глава IV` …, numbered list) are STILL demoted as of
  the 2026-07-10 run; see the Changelog retraction and the finding below. The 1‑D detector reports 0 on them because
  they are UNMAPPED (`mapped_target_index = None`), not mis-mapped — so a MAPPED-pair detector structurally cannot
  see them. They surface on the unmapped-source axis instead, and are what pushes Money to 17 vs threshold 16.
- **The gate validates a different document than the user receives** (2026-07-10, verified on
  `20260710T_money_verify`). Quality/report logic reads `final_markdown` (source-aware, headings intact →
  `false_fragment_heading_count = 0`), while the DOCX is rebuilt from `runtime_display_markdown`
  (`late_phases.py:1080`), which has been through the source-blind `normalize_false_fragment_headings_markdown`
  (`raw_false_fragment_heading_count = 52`). That normalizer demotes a short heading whenever the preceding line
  lacks sentence-terminal punctuation (`_is_continuation_like_previous_line`) — chapters IV–VII follow footnote/URL
  tails; VIII/IX follow prose sentences and survive. This is the primary defect on the project's top-priority axis
  (heading transfer with correct style weight), and no gate signal reports it.
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
  review-items. **Money**'s 4 chapters must remain HEADINGS **in the produced DOCX** — verified by opening the
  artifact, never by reading `heading_demotion_count`. As of 2026-07-10 this criterion FAILS: chapters IV–VII render
  `Normal` with `numPr`, VIII/IX are correct `Heading 1`. The `da6789b` regression test guards a different demotion
  path and does not cover this one. **lietaer/mazzucato/creatingwealth** show NO false heading-demotions
  (back-matter/index/attribution credited). Lietaer 2026-07-10: 16 of its 25 loss-counted paragraphs are source
  headings — the same defect class, so this is systemic, not per-book.
- Anti-vacuum COUNTER-PROOF: a synthetic real unmapped body paragraph (and a real demoted body heading) still counts.
- Verdict PARITY: production finalization and the harness call the same shared acceptance assembly; same numbers.
- Every hard-fail/warn class emits a review-item (Money `review_items > 0`).
- 4-book verification + full suite green; 1‑A/1‑B/structure/import fixes intact; no per-book literals.

## Anti-regression

- `classify_passthrough_*` extensions keep counting real body (synthetic counter-example test); Money fixture
  (effective 16≤16) not regressed.
- Structure/import fixes untouched. CORRECTED 2026-07-11: the earlier version of this note claimed Money's
  `24. Глава IV` demotion "was closed in `da6789b`; the 4 chapters now stay headings; expected count zero" — that
  claim was FALSE (the 2026-07-10 Changelog retraction proved the defect was LIVE at that date) and is now removed.
  The actual resolution: `specs/001-heading-role-preservation` found the demotion happens in the DISPLAY-markdown
  passes, on TWO paths (`output_validation.normalize_false_fragment_headings_markdown` AND
  `normalize_list_fragment_regressions_markdown`), each of which demoted a short heading following a
  non-terminal line. Both are now guarded by the source role carried in the assembly registry (a heading entry is
  never demoted), verified on a live Money run (chapters IV–VII render `Heading 1`). The mapped-pair 1‑D detector
  idea in Blocker 1 was found STRUCTURALLY UNABLE to see this defect (the chapters are UNMAPPED, `mapped_target_index
  = None`, not mis-mapped — see Verified findings), so the fix lives at the demotion source, not in a new mapped-pair
  gate. WARNING to future readers: the saved report fixtures (`tests/fixtures/money_gemini_passthrough_fixture.json`,
  committed 2026-06-21) PREDATE these fixes, so any claim about a live heading-demotion defect must be re-verified
  against a fresh run or a deterministic unit test — never against those stale fixtures (Constitution VIII).

## Implementation notes (stage 2 — scope honesty)

- **Blocker 4 (list_fragment references crediting).** Literal `source_index ≥ references_region_start` scoping was
  NOT implemented: `QualityIssueSample` (`output_validation.py:96`) carries only a markdown line number, no source
  index. The credit is therefore FORM-based (standalone numeric back-matter residue, or a citation/notes-form line
  with ≥2 citation signals), and the helper is named `_is_citation_form_list_fragment_sample` to say so. Region
  scoping would require a line→source_index bridge; deliberately deferred as unnecessary wiring.
- **Blocker 5 (passthrough 3A attribution).** The English occupation word-list route was removed as a
  per-book/English-specific heuristic (Working Rule #7). Attribution is now credited only by explicit structural role
  or a short dash-led credit without sentence-terminal punctuation (a dash-led line ending in `.`/`!`/`?` is dialogue,
  not a credit). Measured effect on Money: effective unmapped source 11 → 12 (threshold 16); the acceptance invariant
  still holds.

## Discharge status (added 2026-07-11)

Each pre-UI blocker mapped to the `specs/<NNN>-…/` unit that discharged it. Verified per Constitution VIII
(live run where possible, else deterministic test).

| # | Blocker | Discharged by | Status |
| --- | --- | --- | --- |
| 1 | Body-integrity axis / heading-demotion | `specs/001-heading-role-preservation` | **DONE.** Fixed at the demotion source (two display-markdown passes, keyed to registry role). Live-verified: Money IV–VII render `Heading 1`. The mapped-pair detector was found structurally unable to see the (unmapped) defect, so it was NOT the fix. |
| 2 | Policy-independent discrepancy emission | `specs/002-gate-report-honesty` | **DONE.** Three-state verdict (passed/failed/not-applicable); production no longer judges what it cannot; review-item anchors cleaned. |
| 3 | `[КРИТ]`/false_pair rendering | (`runtime/artifacts.py` severity consumer) | **PARTIAL — residual UI-data gap.** The severity path exists, but NO book in the corpus has `bad_pair_count > 0`, so the `[КРИТ]` branch is never EXERCISED. Carried into the UI-data gaps list in GLOBAL_PLAN — implement/exercise or scope out with UI. |
| 4 | list_fragment references crediting | `specs/003-list-fragment-detector` | **DONE** (form-based credit, not region-based — see Implementation notes; scope-honest). |
| 5 | Passthrough index/attribution (3A) | this spec's stage-2 impl | **DONE** (structural role / dash-credit; the per-book word-list route was removed per Constitution VII). |
| 6 | Harness↔prod verdict parity | `specs/002` + `specs/006-gate-on-delivered-markdown` | **DONE.** Shared `validation/acceptance.py`; production measures the DELIVERED markdown (006), closing the "gate validates a different document" finding. |

Adjacent work from the same workstream (not original blockers here): `004` emphasis-coverage advisory,
`005` hygiene-pass safety, `007` list-marker-from-role (SHELVED — unverifiable under non-deterministic
translation), `008` paragraph-break detection (advisory), `009` controlled-fallback for
`non_completed_response` (discharges GLOBAL_PLAN Remaining-Work item 2).

**Residual UI-data gaps (carried to UI, not blockers to reliability):** (a) Blocker 3 `[КРИТ]` never exercised;
(b) `unmapped_target` / `note_fragment` review-item classes from the UI spec not yet emitted; (c) the acceptance
PRODUCT semantics — a universal threshold (ratio, not absolute count) and what a production verdict MEANS — is an
open product decision, since production currently emits NOT-APPLICABLE by design (spec 002).
