# Formatting Coverage Consolidation Plan

Date: 2026-06-13
Status: Active plan, not yet implemented
Owner surface: Final formatting restore, acceptance gate, reader-cleanup rebuild,
proof harness
Related:
`docs/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md`,
`docs/specs/PDF_TEXT_LAYER_SOURCE_IMPORT_PIVOT_SPEC_2026-06-01.md`

## Why This Document Exists

PR-I2 mapping quality has been pushed close to its ceiling: the final restore now
reaches `mapped=89`, `unmapped_source=29`, `unmapped_target=36`,
`paragraph_id_rebuild_key=73` on the chapter-region proof
(`20260613T_pr_i2c_rebuild_identity_key_proof`). The acceptance gate still fails
(`29 > 12`, `36 > 6`), but the residual is no longer a mapping problem:

- `relation_id_populated_count = 0/135` (relation layer is empty);
- residual closability (full unmapped set): `target_exists_text_align_missed=7`,
  `target_absent_or_unproven=14`, `true_aggregate_relation_gap=3`,
  `real_uncovered=1`;
- `embedded_marker_upper_bound_count = 7` (a true id-marker closes at most 7);
- `format_neutral_creditable_count = 0` under exact-substring evidence.

Conclusion already established: the gate demands near 1:1 mapping while the
pipeline is fundamentally N-to-M (translation/cleanup legitimately merge, split,
and reword). No additional matcher or marker moves a `29 -> 12` threshold,
because the threshold itself measures the wrong thing. This plan closes every
open hole in one iteration, ordered by gain.

## Goal / End State

One branch, one PR, eight ordered commits. After this iteration:

- the gate measures role-aware coverage, so PR-I2 either passes or fails with a
  short list of *real* structural-role losses instead of an uninformative `29`;
- formatting restore runs once (single final DOCX build);
- the LLM verifier is fully advisory and off by default in proof profiles;
- dormant runtime cleanup surface is removed;
- every change is its own clean commit;
- exactly one fresh real-document proof confirms the consolidated behaviour at
  the end, not once per slice.

## Non-Negotiable Rules (inherited)

- Gemini remains the translation baseline. This iteration does not touch the
  translation model or prompt.
- Deterministic metrics are the acceptance source of truth. The LLM verifier may
  only suggest issue categories/anchors; its verdict/confidence never gates.
- Coverage evidence is measurement only. Containment/overlap may credit "content
  survived into the output" for gate accounting, but must never drive formatting
  transfer (mapping). Measurement != mapping.
- No document-specific literals, no phrase lists, no broad containment matcher
  heuristics.
- Reader cleanup stays AI-first and observer-only validation stays observer-only.

## Baseline Facts To Measure Against

All numbers below are from `20260613T_pr_i2c_rebuild_identity_key_proof`
(final/post-cleanup restore pass) and are the before-state for this iteration:

| Metric | Baseline |
| --- | ---: |
| mapped | 89 |
| unmapped_source (raw 1:1) | 29 |
| unmapped_target (raw 1:1) | 36 |
| paragraph_id_rebuild_key | 73 |
| relation_id_populated_count | 0/135 |
| target_exists_text_align_missed (marker-closable) | 7 |
| target_absent_or_unproven | 14 |
| true_aggregate_relation_gap | 3 |
| real_uncovered | 1 |
| format_neutral_creditable (exact evidence) | 0 |
| images | 12/12 |

The whole iteration is judged by how these move and by whether the gate becomes
a meaningful pass/fail.

---

# PRs Ordered By Gain (max first)

## PR-FC1. Role-Aware Coverage Gate — largest gain

**Intent:** stop counting legitimate N-to-M aggregation as a defect. Promote
`effective_formatting_coverage_diagnostics` from diagnostic-only into the
acceptance gate.

**Changes:**
- The unmapped-source/target gate inputs become role-aware effective counts:
  - `heading` / `list` / `caption` source whose structural role is not
    represented anywhere in the output -> counts as real loss;
  - `body` source legitimately dissolved into a body neighbor target *with
    evidence* (PR-FC2) -> credited as covered, not counted;
  - `true_aggregate` / dissolved with proven coverage -> credited.
- Gate threshold semantics documented in the backlog: the target is
  "every structural role represented", not "every paragraph mapped 1:1".

**Verifiable result:**
- Run via the PR-FC3 offline replay on the saved `20260613T_pr_i2c...` artifact.
- Gate input drops from raw `29/36` to a role-aware effective count whose
  remainder is only genuine `heading/list/caption -> body` role loss.
- The report exposes both numbers side by side: `raw_unmapped_*` and
  `role_aware_effective_unmapped_*`, with `unmapped_source_count_basis` /
  gate-source naming the new basis.
- Acceptance: PR-I2 either passes, or fails with an effective count that equals a
  hand-checkable list of real role losses (each entry is a heading/list source
  whose content landed in a body target).

**Risk:** never blanket-credit body. Credit requires PR-FC2 evidence, else the
gate is relaxed by assertion. Heading/list dissolved into body is real loss and
must stay counted even when content survives.

**Depends on:** PR-FC2 (evidence), validated through PR-FC3 (replay).

**Local implementation note, 2026-06-13:**
- Source-side acceptance now uses `role_aware_formatting_coverage` when
  formatting diagnostics expose `effective_formatting_coverage_diagnostics`.
  The gate actual is `filtered_raw_unmapped_source_count -
  format_neutral_creditable_count`, with raw/effective/credit counts recorded on
  `formatting_diagnostics_threshold` and `unmapped_source_threshold`.
- Explicit `topology_unit` / `accepted_aggregation_legacy` bases still take
  precedence.
- Target-side threshold remains raw paragraph count for now and exposes
  `count_basis`; no target-side role-aware credit is invented without a separate
  target coverage diagnostic.
- The same role-aware summary is now shared by the product
  `translation_quality_report`, structural validation, and the Lietaer proof
  runner instead of living only in the proof harness.

## PR-FC2. Stronger Coverage Evidence Collector (measurement-only)

**Intent:** make PR-FC1 honest. Exact-substring containment under-proves
coverage, so `target_absent_or_unproven=14` is inflated by reworded-but-present
content.

**Changes:**
- Replace exact normalized containment with a bounded token-overlap / fuzzy
  threshold for gate-credit evidence only.
- Keep it strictly measurement: it answers "did this source's content survive
  into a nearby mapped target", and never selects a target for style transfer.

**Verifiable result:**
- On the saved i2c artifact (offline), `target_absent_or_unproven` drops below
  `14`, and the freed entries split into provable `covered` vs provable `lost`.
- A diagnostics field records the evidence basis (`exact` vs `token_overlap`,
  threshold value) so the credit is auditable, not believed.
- No change to `mapped_count`, mapping strategies, or applied styles (proves it
  is measurement, not mapping).

**Depends on:** none. Build alongside PR-FC1.

**Local implementation note, 2026-06-13:**
- Live diagnostics and `scripts/classify-formatting-residuals.py` now use
  `registry_text_exact_or_fuzzy_overlap_in_already_mapped_neighbor_target`.
- Evidence remains measurement-only: it is recorded in
  `effective_formatting_coverage_diagnostics` and `occupied_neighbor_candidate_evidence`;
  it does not change `mapped_count`, mapping strategy selection, or style
  application.
- Focused tests cover both sides of the role-aware rule: fuzzy body->body is
  creditable, while fuzzy heading->body remains formatting loss.
- Exact/free-target evidence still drives marker closability
  (`target_exists_text_align_missed`), while fuzzy/overlap evidence drives
  role-aware coverage credit. These counters are intentionally different and are
  not directly comparable.

## PR-FC3. No-LLM Diagnostic Replay Harness — build first

**Intent:** remove the expensive, flaky full-translation proof from the inner
loop. Almost every check above is deterministic post-processing of restore.

**Changes:**
- A script/entry point that recomputes full-set restore + formatting diagnostics
  from a saved run (`report.json` + final `.md` + `.docx` + registries) with no
  model call.

**Verifiable result:**
- `python scripts/<replay> <run_dir_or_report>` reproduces full-set
  `residual_closability_diagnostics` and `effective_formatting_coverage_diagnostics`
  with `classification_basis=full_unmapped_source_set`.
- Output matches the live run's diagnostics for `20260613T_pr_i2c...` within
  tolerance, and the harness asserts no network/model call occurred.
- Runtime is seconds, not a full translation pass; it cannot hang on block-36 or
  the verifier.

**Depends on:** none. This is the scaffolding; build it before FC1/FC2 so they
are validated cheaply.

**Local implementation note, 2026-06-13:**
- Future restore diagnostics now persist full `residual_rows` in addition to the
  capped `samples` preview. This makes no-LLM replay possible without relying on
  the sample limit.
- `scripts/classify-formatting-residuals.py --replay` now recomputes restore
  diagnostics from the saved final DOCX with current mapping code and no model
  call. Replay now treats the saved `source_registry` preview as the canonical
  source paragraph set for parity with the saved run; source DOCX is only an
  explicit override/debug path. Results are labelled with
  `source_reconstruction_basis`.
- Replay output now also labels fidelity against the saved report
  (`replay_fidelity` plus saved/replayed source counts), so older artifacts do
  not masquerade as exact historical parity when the available source artifact
  differs from the saved source paragraph set.
- For saved artifacts that only retain source-language `source_registry`
  previews, replay may report `count_parity_only_source_language_preview`: this
  is enough to preserve source count/order, but not enough to reproduce the
  translated rebuild-key sidecar exactly. FC5 decisions must not use that mode
  as marker-proof parity.
- Future live proof artifacts should also persist the final post-cleanup
  generated paragraph registry that fed rebuild-key restore, so replay can
  recover exact translated identity inputs instead of relying on source-language
  previews only.
- Plain non-replay mode still supports legacy report inspection from saved
  `residual_rows` / `samples`, but that path is now explicitly a viewer for
  baked diagnostics rather than the primary FC3 verification path.

## PR-FC4. Single Final DOCX Build

**Intent:** remove the redundant pre-cleanup formatted DOCX build. The final,
user-visible DOCX is already the post-cleanup one.

**Changes:**
- When cleanup is enabled, do not build/restore a formatted DOCX before cleanup;
  build and restore exactly once after cleanup.
- Preserve the pre-cleanup mapping diagnostic as a diagnostic-only snapshot (the
  37/29 vs 52/29 baseline), without persisting a full formatted intermediate.
- Handle cleanup disabled and cleanup noop: exactly one build in all three paths.

**Verifiable result:**
- `formatting_diagnostics` length is `1` (was `2`) on a cleanup-enabled run;
  still `1` on disabled and noop runs.
- Final DOCX remains openable, images remain `12/12`, no mapping regression vs
  the FC1/FC2 effective counts.
- The pre-cleanup mapping baseline is still emitted as a labelled
  diagnostic-only field.

**Risk:** remove build #1, not build #2 (build #2 carries the I2c rebuild-key
sidecar). Do not lose the pre-cleanup baseline.

**Depends on:** PR-FC3 to verify cheaply.

**Local implementation note (2026-06-13):**
- The pipeline now carries a lazy `base_docx_builder` through `DocxBuildPhaseResult`.
  When reader cleanup is enabled, the pre-cleanup DOCX is not built eagerly.
  Changed-cleanup runs build the final post-cleanup DOCX once; cleanup-disabled
  and cleanup-noop/fallback paths still materialize exactly one base DOCX.
- Regression coverage in `tests/test_document_pipeline.py` asserts the one-build
  invariant for disabled, changed-cleanup, and fallback/noop paths.
- The pre-cleanup mapping baseline is now carried as
  `translation_quality_report.pre_cleanup_formatting_baseline`, labelled
  `classification=diagnostic_only`,
  `metric_scope=sidecar_only_proxy`, and
  `mapping_basis=ordered_exact_text_rebuild_sidecar`. This preserves pre-cleanup
  observability without writing a formatted intermediate or incrementing
  `formatting_diagnostics_artifact_count`.
- FC4 status: complete for the code path. The next proof artifact should verify
  the expected single final formatting diagnostic on the real cleanup-enabled
  profile.

## PR-FC5. Embedded Id-Marker — dropped for this iteration

**Intent:** the only thing that closes `target_exists_text_align_missed` without
text equality. Historical optimistic upper bound is `7`, so it cannot pass the
gate alone.

**Decision (2026-06-13):** drop from the current implementation branch.

**Why this is a real decision, not deferral:**
- even the optimistic historical upper bound (`7`) cannot move
  `unmapped_source 29 -> <=12`;
- PR-FC1 changes the gate semantics toward role-aware coverage, so the right
  next lever is coverage accounting, not identity plumbing;
- the FC3 replay on the saved i2c artifact is intentionally labelled
  `count_parity_only_source_language_preview`, so there is no value in trying to
  squeeze marker-proof parity out of a stale artifact that does not persist the
  final translated rebuild registry;
- all available measurements point the same way: marker is not the main
  leverage, and the residual is dominated by images, aggregates, and real role
  loss rather than marker-closable single-origin misses.

**Durable follow-through kept:** future live proof artifacts should persist the
final post-cleanup generated paragraph registry that actually feeds rebuild-key
restore. That improves future replay fidelity, but it is not a blocker for the
FC5 drop decision on this iteration.

**Decision gate (made after PR-FC1):**
- If the role-aware gate already credits/closes those cases or reduces them to an
  accepted real-loss list, **do not build the marker this iteration** — record
  the decision and the `<=7` upper bound as the justification.
- Only if a material heading/list role-loss is genuinely marker-closable: carry
  `paragraph_id` through cleanup split/merge as an invisible rebuild attribute
  and read it back at restore, removing text equality from the binding. Reuse the
  existing cleanup identity infrastructure; no parallel id system.

**Verifiable result (if built):** the formerly text-missed set maps via a binding
not derived from text equality; `mapped` rises for that set with zero false maps
(checked by `rebuild_key_mapping_quality`). **If dropped:** a written decision
note plus the upper-bound evidence.

**Depends on:** PR-FC1 outcome.

## PR-FC6. Verifier Fully Advisory + Off By Default In Proofs

**Intent:** take the flaky LLM judge out of the measurement critical path.

**Changes:**
- Contract: verifier verdict/confidence never enters `gate_reasons`.
- Proof profiles default `reader_verifier_enabled=false`; the deterministic
  report is always written regardless of verifier state.

**Verifiable result:**
- A proof run with verifier disabled completes and writes the full deterministic
  report; verifier output, when present, never appears in `gate_reasons`.
- A run where the verifier would stall still completes (no hang in the critical
  path).

**Depends on:** none.

## PR-FC7. PR-CLEANUP0 — Dormant Runtime Surface Removal

**Intent:** remove cleanup-adjacent runtime surface that is dormant in the
shipping configuration, now safe because PR-FC1 stabilizes the formatting gate.

**Changes (remove or deprecate only what the accepted contract does not use):**
- global-plan pass (`reader_cleanup_global_plan_enabled` default false);
- anchor-repair pass (empty `reader_cleanup_anchor_targets`);
- runtime `reader_verifier_*` config whose scoring lives only in the proof
  harness, not in `src/`.

**Verifiable result:**
- Full test suite green; no runtime path references the removed config; reduced
  code/runtime surface.
- Proof harnesses and safety guards are untouched.

**Risk:** the backlog forbids cutting surface while restore is moving — this is
why FC7 runs last, after FC1 settles the gate.

**Depends on:** PR-FC1 (gate stabilized).

## PR-FC8. Clean Commits / Scope Split — smallest

**Intent:** bank the work as reviewable units; untangle leftover mixed
workstreams in the working tree.

**Verifiable result:**
- `git log` shows eight separate commits, one per FC item, each diff coherent and
  single-purpose; no mixed R0 / verifier-hardening / formatting in one commit.

**Depends on:** all of the above (final hygiene pass).

---

# Execution Order (build order != gain order)

1. **PR-FC3** (replay harness) — scaffolding, makes everything else cheap.
2. **PR-FC1 + PR-FC2** (role-aware gate + evidence) — the head hole; validated
   through FC3 on the saved i2c artifact.
3. **PR-FC4** (single build).
4. **PR-FC5 decision** (build only if FC1 justifies it; expected: drop).
5. **PR-FC6** (verifier advisory/off).
6. **PR-FC7** (dormant surface removal).
7. **PR-FC8** (clean commits).
8. **One** fresh chapter-region proof at the very end to confirm consolidated
   behaviour on live data — not a metric chase, a regression check that the
   offline-validated changes hold end to end.

# Verification Contract

- Every per-PR check above runs through PR-FC3 offline on the saved
  `20260613T_pr_i2c_rebuild_identity_key_proof` artifact. No full translation run
  is spent until the final end-to-end confirmation.
- Each PR must show before/after numbers against the Baseline Facts table.
- A change is only "done" when its verifiable result is recorded in the backlog
  with the measured numbers, not the intended ones.

# Non-Goals

- No new reader-cleanup operations, no translation model/prompt changes.
- No formatting application onto mixed targets a single Word style would corrupt.
- No relation-fact population in this iteration beyond what FC1/FC2 need for
  accounting (full relation-layer population stays a later, separate workstream
  for the `3` true aggregates).
- No deletion of proof harnesses or safety guards.

# Definition Of Done

- Role-aware gate live: PR-I2 is either green or fails with a short, hand-checked
  list of real `heading/list/caption -> body` role losses.
- Single final DOCX build; `formatting_diagnostics` length `1`.
- Verifier advisory and off by default in proofs; never in `gate_reasons`.
- Dormant runtime surface removed; suite green.
- Eight clean commits; one final live proof confirming the consolidated state.
