# Structure Recognition Completion Plan

Date: 2026-05-14
Status: Working single source of truth
Scope: DocxAICorrector AI-first structure recognition, topology projection, structure-aware gates, and regression acceptance.

This document is the continuation source of truth for the current structure-recognition remediation work. It consolidates the active state from:

- `docs/AI_FIRST_STRUCTURE_RECOVERY_SPEC_2026-05-08.md`
- `docs/specs/TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md`
- `docs/specs/LAYOUT_SIGNAL_EVIDENCE_SLICE_SPEC_2026-05-14.md`

It does not replace those design specs historically. It defines the current implementation status, the target end state, the acceptance criteria, and the ordered work plan required to reach reliable document-structure recognition.

## 1. Current Verified State

### 1.1 Implemented and verified

The current workspace has moved beyond the original baseline in several important ways:

1. Stage 1 `DocumentMap` authority remediation for the Lietaer Chapter 11 region is present.
2. `DocumentMapSplitHint` / `split_hints` schema support exists.
3. `DocumentTopologyProjection` / `StructuralUnit` sidecar projection exists.
4. Topology projection schema is bumped to version `2`.
5. Layout-signal evidence support exists:
   - `derive_layout_signals(...)` computes body baseline, font tiers, short-line and page-hint records.
   - `apply_document_map_topology(...)` accepts `layout_signals`.
   - `font_cluster_match`, `page_break_boundary`, and `body_font_baseline_outlier` evidence tags are in the topology vocabulary.
   - `candidate_page_artifact_split` exists as candidate-only observability.
6. Chapter heading continuation is authority-bounded:
   - layout evidence can only confirm members already inside the Stage 1 authority envelope;
   - it must not synthesize missing Stage 1 title text or missing membership;
   - it still fails closed when Stage 1 does not provide full enough authority.
7. Mixed heading-tier Chapter 11 case is handled:
   - `Chapter Eleven`
   - `GOVERNANCE AND WE,`
   - `THE CITIZENS`
   - `An Ancient Future?`
   can be represented as one `chapter_heading` unit when Stage 1 already provides canonical title and member bounds.
8. Runtime propagation for `structure_recovery_topology_projection_layout_signals_enabled` exists through validation run profiles.
9. Live structural diagnostic snapshots now expose `document_topology_layout_signals` either from the event log or via prepared-snapshot backfill.
10. Canonical chapter-region diagnostic for `lietaer-pdf-chapter-region-core` currently passes in the dirty workspace:
    - `failed_checks: []`
    - `document_topology_projection_status: built`
    - `document_topology_layout_signals` populated
    - Chapter 11 merge on logical indexes `[221, 222, 223, 224]`
11. Core Workstream C authority/provenance wiring is now aligned across both structural validation and late-phase runtime quality reporting for the touched surfaces:
   - `toc_body_concat_detected` can remain topology-authoritative while `toc_body_concat_markdown_detected` stays advisory;
   - `toc_body_concat_gate_source` is carried together with supporting TOC/topology provenance fields in diagnostics/reporting;
   - raw unmapped counts remain visible while structure-unit basis and gate-source fields are explicit in runtime reporting.
12. Workstream D is now materially advanced on the late-phase report surface:
   - `false_fragment_heading_count` now follows explicit authority (`entry_assembly` or `legacy_markdown`) instead of silently collapsing raw markdown and source-backed assembly evidence;
  - `page_placeholder_heading_concat_count` now flows through late-phase reporting, structural passthrough, acceptance, and summary/export as explicit `legacy_markdown` plus `display_hygiene`, while the raw markdown observation remains separately visible through `raw_page_placeholder_heading_concat_count`;
  - `residual_bullet_glyph_count` now carries explicit `legacy_markdown` provenance together with matching raw-count observability on the touched late-phase, structural-passthrough, acceptance, and summary/export surfaces instead of remaining an unlabeled markdown-only report fact;
   - `list_fragment_regression_count` now becomes non-binding when topology projection support and source-backed assembly authority are both present, while raw markdown evidence remains visible through `raw_*` report fields;
   - real-document acceptance now consumes those authoritative counts while preserving raw markdown observability in check details;
   - structural validation metrics/snapshots now default these touched fields to explicit `legacy_markdown` provenance and, when a saved quality report exists, reuse its authoritative counts plus raw-count observability instead of silently rebuilding the report surface from runtime markdown alone;
  - the real-document harness summary/export surface now serializes those touched authoritative/raw fields directly from the saved quality report instead of flattening the user-visible summary back down to generic translation-quality status and gate reasons alone;
  - remaining runtime/display call sites around placeholder and residual-bullet cleanup are now more explicitly scoped: placeholder splitting no longer runs through the quality-gate normalizer, TOC-body markdown detection uses it only as advisory preprocessing, residual-bullet cleanup no longer rewrites final assembly text before late-phase gating, and runtime display remains the explicit cleanup boundary for user-visible markdown and DOCX build input;
  - the touched late-phase runtime path now also labels that projection more explicitly internally: runtime-display structural cleanup and display-hygiene cleanup are split into separate helpers, and DOCX/finalize consumers prefer an explicit `runtime_display_markdown` payload instead of implicitly treating user-visible markdown as gate-input authority.

### 1.2 Important correction to earlier narrative

The chapter-region pass must not be attributed only to the topology acceptance rule.

The verified passing state depends on both layers:

1. topology acceptance logic for authority-bounded same-style heading fragments across mixed heading-sized tiers;
2. runtime propagation that enables `structure_recovery_topology_projection_layout_signals_enabled` for structural diagnostics.

Any future PR summary, spec update, or commit message must state both parts.

### 1.3 Current hygiene state

The workspace is dirty. Current known hygiene issues:

- multiple modified source, test, config, and spec files;
- CRLF warnings on several files;
- untracked diagnostic scratch files such as `diagnostic_snapshot.json`, `test_output.json`, and `git_*.txt`;
- tracked chapter-region fixture artifacts exist, but may be stale relative to the latest live diagnostic evidence.

Before any PR or commit, the fixture and whitespace state must be made clean and intentional.

Repo-root diagnostic clutter is not an accepted steady state. Manual drift-investigation snapshots, ad-hoc comparison scripts, and local evidence files must be moved under specialized ignored `.run/...` directories, with `.run/manual_investigations/<topic>/...` as the default path for local investigation evidence. Versioned regression fixtures belong only under `tests/artifacts/...`.

The current tracked repo-root deletion set is an intentional cleanup set, not a fixture regression. Historical root artifacts such as `diagnostic_snapshot.json`, `test_output.json`, `git_*.txt`, `run{1,2}_*.{json,txt}`, `persist_run{1,2}_*.{json,txt}`, `pre_reconciliation_run{1,2}_*.{json,txt}`, and `post_topology_run{1,2}_*.{json,txt}` are obsolete manual-investigation evidence and must not be restored to repo root. If any of that evidence still needs to be kept locally, it belongs under `.run/manual_investigations/...`; accepted versioned fixtures still belong only under `tests/artifacts/...`. The tracked zero-byte repo-root file `$null` is historical clutter with no accepted repository role.

### 1.4 Current drift investigation status

Reviewer-safe status for the current workspace:

- Confirmed:
  - persisted `DocumentMap` reuse is stable in the current workspace;
  - the earliest saved divergence boundary is now localized to the pre-projection SDK-native `to_json()` boundary;
  - divergence is already visible after `_call_structure_responses_with_timeout(...)`, before `_project_provider_native_response(...)`, and before `collect_response_text_traversal(...)`.
  - the current canonical chapter-region structural diagnostic still passes with `toc_entry_count = 9`, `outline_coverage_ratio = 1.0`, and the refreshed tracked fixture trio now records that accepted focused baseline.
- Partially confirmed:
  - the earliest content-level diff is already visible inside the serialized SDK-native payload produced by `to_json()`;
  - downstream artifacts continue to drift later as well, so later counters and snapshots are not the earliest source.
- Unconfirmed:
  - true wire-level upstream/provider payload drift;
  - whether the earliest divergence comes from upstream payload variability or from SDK `to_json()` serialization behavior.
- Caveats:
  - do not claim the projected provider-native artifacts become equal after removing volatile metadata keys; current evidence does not support that narrative because content-level diff remains in `output[0].content[0].text.value`;
  - for the focused chapter-region fixture package, this pre-projection boundary is now accepted as the current baseline limitation; the tracked chapter-region trio is refreshed to the current canonical structural diagnostic payload, but that is not a claim that wire-level or SDK-serialization drift has been resolved;
  - live structural passthrough and tracked fixture locks remain separate proof surfaces even after that accepted baseline decision.

## 2. What Is Not Yet Complete

### 2.1 Layout Signal Evidence slice

The runtime behavior is mostly implemented, but the slice is not fully closed as an acceptance package until all of the following are true:

1. `LAYOUT_SIGNAL_EVIDENCE_SLICE_SPEC_2026-05-14.md` clearly states the implemented runtime dependency on both topology acceptance and runtime flag propagation.
2. The spec clearly states that `document_topology_layout_signals` may be populated by event-log context or prepared-snapshot backfill.
3. Chapter-region regression fixtures are refreshed to the accepted current canonical payload, including layout-enriched evidence and populated layout-signals summary.
4. `git diff --check` is clean.
5. Focused canonical WSL tests and the chapter-region diagnostic pass from the updated repo state.

This package takes that explicit decision: for the focused chapter-region fixture boundary, the pre-projection SDK-native `to_json()` drift caveat is accepted as the current baseline limitation. The refresh records the current canonical structural diagnostic payload as the tracked baseline without claiming that upstream/provider or SDK-serialization drift has disappeared.

### 2.2 Topology-first parent remediation

The parent remediation is not complete. Current status by area:

- R1 Stage 1.5 topology projection: substantially implemented.
- R2 structure-aware quality gates: materially advanced for `toc_body_concat` and unmapped-threshold authority/provenance, but not complete as a universal gate migration.
- R3 markdown structural postprocessor retirement: materially advanced on labelling/provenance for touched late-phase, acceptance, and structural-validation report surfaces, but actual normalizer retirement/removal has not started globally.
- Workstream E Stage 2 fallback hardening and topology protection: implemented and verified against the parent-spec Slice 1-6 surfaces; Slice 7 root-window tuning remains a future diagnostic/config-only milestone if telemetry proves it is needed.
- Full-book acceptance: not complete.

The code still uses markdown-side structural normalizers and markdown detectors in runtime paths. That is allowed during migration, but it means the end-state architecture has not yet been reached.

## 3. Final Target

The final goal is not merely to make one Lietaer chapter-region diagnostic pass. The final goal is reliable, auditable, AI-first structure recognition for difficult DOCX/PDF-derived books.

A document is considered structurally recognized when the pipeline can:

1. Identify front matter, TOC region, body start, chapter/section outline, and review zones from Stage 1 authority.
2. Project document topology into explicit structural units before local classification can fragment them.
3. Preserve Stage 1 authority through Stage 2 and Stage 3 without allowing local classifier fallback to override high-confidence topology units.
4. Represent multi-line headings, compound TOC entries, page artifacts, and TOC/body boundaries as structural facts, not as markdown cleanup side effects.
5. Make quality gates depend on structure-aware signals when Stage 1 and topology projection are present.
6. Keep legacy/markdown signals visible as advisory diagnostics during migration when stronger topology authority is present, while preserving explicit `legacy_markdown` fallback authority for conservative gating when topology support is insufficient.
7. Produce reproducible diagnostics and tracked fixtures that survive clean checkout.

## 4. Final Acceptance Criteria

### 4.1 Global acceptance criteria

All of these must hold before declaring the structure-recognition remediation complete:

1. Stage 1 `DocumentMap` authority is the only source of new final structure authority.
2. Stage 1.5 topology projection may validate and materialize Stage 1 authority, but must not invent missing titles, members, or split boundaries.
3. Stage 2 sees topology unit fields and must not recreate standalone fragment headings for protected units.
4. Stage 3 reconciliation considers outline entries covered by projected heading units.
5. Quality gates use structure-aware signals when topology projection is present.
6. Markdown structural normalizers are no longer readiness authority.
7. Diagnostic snapshots expose both raw and structure-aware metrics.
8. Real-document regression fixtures are tracked in the repo, not only in `.run`.
9. Canonical WSL verification passes from a clean checkout or from an explicitly documented dirty state.
10. No full-book loop is used as the ordinary development loop.

### 4.2 Chapter-region acceptance

For `lietaer-pdf-chapter-region-core`:

1. `bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-chapter-region-core` passes.
2. `failed_checks == []`.
3. `document_topology_projection_status == "built"`.
4. `document_topology_layout_signals` is populated with at least:
   - `body_baseline_pt`
   - `tier_count`
   - `heading_tier_count`
   - `paragraphs_with_font_size_count`
   - `heading_ratio`
5. Chapter 11 is represented as one `chapter_heading` unit covering `[221, 222, 223, 224]`.
6. The Chapter 11 unit canonical text is exactly the Stage 1 canonical title:
   `Chapter Eleven GOVERNANCE AND WE, THE CITIZENS An Ancient Future?`
7. The Chapter 11 unit evidence includes layout evidence when layout signals are enabled.
8. Existing Chapter 8, Chapter 9, and Chapter 10 topology behavior is not regressed.
9. Tracked fixture trio under `tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/` matches the accepted current canonical chapter-region baseline refreshed in this package.

### 4.3 Structure-aware gate acceptance

When topology projection is present:

1. `toc_body_concat_markdown_detected` remains visible as raw/advisory evidence.
2. `toc_body_concat_structure_detected` is the authoritative gate signal when projection support is sufficient.
3. `toc_body_concat_gate_source` clearly states whether the gate used `topology_projection` or `legacy_markdown`.
4. When projection support is insufficient, `legacy_markdown` remains the conservative authoritative fallback and `toc_body_concat_markdown_detected` may still decide the gate.
5. `candidate_page_artifact_split` never flips the gate to topology authority.
6. Binding split operations and projected TOC units may flip the gate to topology authority.
7. Raw unmapped counts remain visible.
8. Structure-unit unmapped counts are used for structural gate decisions when topology projection is present.

### 4.4 Full-book checkpoint acceptance

Only after focused chapter-region and gate tests are green:

1. Run the full-book structural diagnostic once as a milestone, not as a loop.
2. Confirm Stage 1 retains late-book chapters, including Chapter 9 and Chapter 11.
3. Confirm projected composite headings are present.
4. Confirm structure-unit coverage improves affected heading-fragment accounting relative to raw physical paragraph accounting.
5. Bucket any remaining failures into explicit classes:
   - Stage 1 missing authority;
   - projection unable to validate authority;
   - Stage 2 fallback/timeout problem;
   - restore/reassembly unit coverage problem;
   - markdown-only advisory issue;
   - unsupported topology class.

## 5. Work Plan

### Workstream A: Repo hygiene and fixture readiness

Goal: make the current passing state reproducible from tracked repo state.

Tasks:

A1. Recheck working tree:

```bash
git status --porcelain
git diff --check
git diff --stat
```

A2. Remove or ignore scratch diagnostic files only if they are confirmed not required:

- `diagnostic_snapshot.json`
- `test_output.json`
- `git_check.txt`
- `git_stat.txt`
- `git_status.txt`

When scratch artifacts are still needed for active investigation, move them out of repo root into a specialized ignored `.run/...` directory instead of leaving them in root or legalizing them with new root-level ignore patterns.

A3. Normalize intentional line endings / whitespace without unrelated churn.

A4. Refresh the tracked chapter-region fixture trio to the accepted current canonical chapter-region payload:

- `tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/structural_diagnostic.json`
- `tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/document_map.json`
- `tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/document_topology_projection.json`

A5. Keep fixture-adjacent tests aligned with the accepted baseline boundary: tracked fixture locks assert the refreshed versioned artifact contract, while live passthrough remains a separate runtime proof surface rather than implicit fixture-refresh authorization.

Acceptance:

- `git diff --check` passes.
- fixture tests pass.
- live chapter-region diagnostics and tracked fixture locks remain separate proof surfaces after the accepted baseline decision.

### Workstream B: Spec and narrative synchronization

Goal: make docs match implementation and prevent future agents from repeating stale assumptions.

Tasks:

B1. Update `LAYOUT_SIGNAL_EVIDENCE_SLICE_SPEC_2026-05-14.md` to state:

- pass state depends on topology acceptance plus runtime layout-signals propagation;
- mixed heading-tier continuation uses `body_font_baseline_outlier` inside Stage 1 member bounds;
- diagnostic layout-signal context may come from event log or prepared-snapshot backfill;
- `candidate_page_artifact_split` remains candidate-only and non-binding.

B2. Update `TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md` with a status addendum:

- R1 mostly implemented;
- layout evidence slice implemented as an intermediate slice;
- R2 partially implemented;
- R3 not complete;
- Stage 2 fallback hardening / topology protection Slices 1-6 implemented;
- full-book acceptance pending.

B3. Keep this document as the continuation index. Future agents should read this file first.

Acceptance:

- specs no longer imply that topology logic alone caused the chapter-region pass;
- specs no longer imply that event-log capture is the only source of `document_topology_layout_signals`;
- specs clearly separate candidate diagnostics from binding topology authority.

### Workstream C: Structure-aware gate completion

Goal: make quality gates use structure authority whenever the required structural evidence is present.

Tasks:

C1. Audit every gate that still depends on markdown-only structural signals.

C2. For `toc_body_concat`:

- keep markdown detector as advisory when topology authority is sufficient, and keep explicit `legacy_markdown` fallback authoritative when topology support is insufficient;
- use topology projection when bounded TOC and binding projected TOC units/splits are present;
- never use `candidate_page_artifact_split` as binding gate support.

C3. For unmapped thresholds:

- expose raw counts;
- expose structure-unit counts;
- make gate basis explicit through `*_gate_source` or `*_count_basis` fields;
- use structure-unit basis when topology projection exists.

C4. Add focused tests covering:

- legacy fallback path when projection support is absent or insufficient;
- topology path when binding TOC split exists;
- candidate-only page artifact remains non-binding;
- raw vs structure-unit unmapped counts.

Current focused coverage map for these scenarios:

- legacy fallback path when projection support is absent or insufficient:
  `tests/test_structure_validation.py::test_candidate_page_artifact_projection_remains_non_binding_for_toc_body_concat_gate`
  and `tests/test_document_pipeline.py::test_run_document_processing_quality_report_keeps_candidate_page_artifact_non_binding`;
- topology-authoritative TOC/body path:
  `tests/test_real_document_validation_corpus.py::test_build_structural_checks_prefers_structure_toc_body_gate_when_topology_authority_is_present`,
  `tests/test_structure_validation.py::test_apply_prepared_snapshot_fields_prefers_topology_authority_for_toc_body_concat_detected`,
  and `tests/test_document_pipeline.py::test_run_document_processing_quality_report_prefers_topology_authority_over_markdown_toc_concat`;
- candidate-only page artifact remains non-binding:
  `tests/test_document_pipeline.py::test_run_document_processing_quality_report_keeps_candidate_page_artifact_non_binding`;
- raw vs structure-unit unmapped counts:
  `tests/test_document_pipeline.py::test_build_translation_quality_report_exposes_structure_unit_unmapped_basis_without_raw_override`
  and `tests/test_real_document_pipeline_validation.py::test_evaluate_lietaer_acceptance_prefers_structure_unit_unmapped_basis_over_raw_formatting_counts`.

If these tests are renamed later, keep this mapping updated or use names that preserve the C4 scenario wording.

Acceptance:

- structural profiles pass/fail from structure-aware gate fields when projection is authoritative;
- markdown fields remain visible as advisory evidence when topology is authoritative, while `legacy_markdown` remains the conservative fallback gate source when topology support is insufficient;
- tests prove the fallback behavior is conservative.

### Workstream D: Markdown structural normalizer retirement

Goal: stop using final markdown cleanup as structural proof.

Current status: materially advanced for authority labelling/provenance on late-phase, acceptance, and structural-validation reporting for `false_fragment_heading`, `page_placeholder_heading_concat`, `residual_bullet_glyph`, and `list_fragment_regression`. Authoritative or explicitly fallback-labelled counts are now visible together with raw markdown observability on the touched surfaces, and structural validation now reuses saved quality-report authority when available instead of flattening everything back into runtime markdown-only counts. The remaining runtime/display call sites around placeholder and residual-bullet cleanup are also narrower: placeholder splitting is now display/advisory-only rather than quality-gate preprocessing, residual-bullet cleanup no longer rewrites final assembly text before late-phase gate classification, and runtime display remains the explicit cleanup boundary for user-visible markdown. Inside the touched late-phase path, the user-visible projection is now explicitly named `runtime_display_markdown`, the temporary `docx_phase["final_markdown"]` alias is removed, and the `false_fragment_heading` / `list_fragment_regression` normalizers now sit behind an explicit runtime display compatibility helper rather than an authority-facing carrier. Structural passthrough fallback metrics for `false_fragment_heading_*` and `list_fragment_regression_*` now also consume raw structural markdown built from `processed_block_markdowns`, so display-cleaned `latest_markdown` is no longer a silent fallback source for those touched metrics when no saved quality report exists. Touched acceptance/summary/export consumers continue to read explicit quality-report authority/raw-observability fields rather than republishing runtime display cleanup as structural proof. This is not yet normalizer retirement: `normalize_false_fragment_headings_markdown` and `normalize_list_fragment_regressions_markdown` still run in the pipeline, residual bullet cleanup remains markdown-side hygiene, and D3 removal of structural authority usage has not started globally. Broader retirement of remaining markdown cleanup and untouched call sites is still pending.

Tasks:

D1. Inventory current structural markdown normalizers:

- `normalize_page_placeholder_heading_concats_markdown`
- `normalize_false_fragment_headings_markdown`
- `normalize_list_fragment_regressions_markdown`

D2. Classify each call site as:

- structural authority;
- quality advisory;
- display-only cleanup;
- non-structural text hygiene.

D3. Remove structural authority usage only after equivalent structure-aware gates exist.

D4. Keep non-structural text hygiene only when documented.

Acceptance:

- no structural readiness gate depends on these markdown normalizers when topology authority is present;
- raw markdown issues remain visible as advisory diagnostics;
- output display remains stable.

### Workstream E: Stage 2 fallback hardening and topology protection

Goal: prevent local classifier fallback from damaging high-confidence topology units.

Status: Done for parent-spec Slices 1-6 in the current implementation. The topology precedence guard, fallback telemetry, bounded retry, recursion cap, topology-aware boundary snapping, and side-map fallback metadata are implemented and covered by focused tests. Slice 7 root-window tuning is intentionally not part of this done state; it is a future diagnostic/config-only decision if telemetry shows it is needed.

The remaining work here is maintenance-only unless a future diagnostic proves a concrete protected-unit fragmentation or override regression.

Tasks:

E1. Confirm `apply_structure_map(...)` topology precedence guard behavior:

- guard inactive without projection;
- guard active only for high-confidence `document_map_outline` / `document_map_toc` units;
- concord classifications apply;
- conflicts defer and increment counters.

E2. Confirm split fallback telemetry:

- split count;
- max fallback depth;
- descriptor count;
- retry counts;
- capped fallback counts.

E3. Confirm split fallback boundaries do not cut through protected topology units.

E4. Confirm progress text is honest and telemetry is machine-readable.

Acceptance:

- focused `tests/test_structure_recognition.py` coverage exists for every guard and fallback invariant;
- diagnostic snapshots include fallback counters;
- no high-confidence topology unit is split or overwritten by emergency fallback behavior.

### Workstream F: Real-document acceptance ladder

Goal: avoid expensive full-book loops while proving real-world stability.

Tasks:

F1. Inner loop profiles:

- `lietaer-pdf-chapter-region-core`
- `lietaer-pdf-first-20-structure-core`
- `end-times-pdf-core` when TOC/list/page-artifact behavior is touched

F2. Use canonical diagnostic script only:

```bash
bash scripts/run-structural-preparation-diagnostic.sh <document_profile_id> [--run-profile-id <id>]
```

F3. Save diagnostic outputs only when needed for fixture updates.

F4. Run full-book checkpoint only after focused surfaces are green and the milestone question is explicit.

Acceptance:

- each real-document profile has tracked fixture expectations where needed;
- full-book runs are milestone evidence, not tuning loops;
- remaining failures are classified, not treated as generic quality regressions.

## 6. Task Breakdown

### Immediate next tasks

1. Continue Workstream D migration on adjacent reporting/passthrough surfaces: keep authoritative counts, gate source/basis, and raw markdown observability separate.
2. Treat the chapter-region fixture trio as refreshed to the accepted current canonical baseline; unresolved pre-projection drift attribution now belongs to a separate reproducibility/observability package rather than blocking this fixture boundary.
3. Treat Workstream E as implemented for Slices 1-6; do not reopen fallback hardening unless a concrete protected-unit fragmentation regression is found.
4. Keep this plan aligned with the current reviewer-safe drift classification and landed slice status.
5. If reproducibility attribution becomes necessary later, make it a separate explicit package that proves more than this focused baseline decision instead of reopening the refreshed chapter-region fixture boundary by default.

### Next implementation tasks after hygiene

1. Continue Workstream D only on untouched markdown-normalizer surfaces after the touched `false_fragment_heading` / `list_fragment_regression` runtime-display boundary work; keep authoritative counts, conservative fallback, advisory raw observability, and display/hygiene cleanup explicitly separated.
2. Keep or tighten tests proving markdown structural signals are advisory when topology/source-backed authority is present.
3. Leave Workstream E closed unless new diagnostics prove a concrete protected-unit fragmentation or override regression.
4. Keep the accepted chapter-region fixture baseline in place unless a later reproducibility package produces stronger saved-boundary evidence or a concrete regression.
5. Perform one milestone full-book diagnostic only after focused surfaces and tracked fixtures are intentionally aligned.

## 7. Verification Matrix

### Unit and focused tests

Use WSL canonical runner:

```bash
bash scripts/test.sh tests/test_structure_layout_signals.py -q
bash scripts/test.sh tests/test_structure_topology.py -q
bash scripts/test.sh tests/test_structure_recognition.py -q
bash scripts/test.sh tests/test_structure_validation.py -q
bash scripts/test.sh tests/test_preparation.py -q
bash scripts/test.sh tests/test_real_document_validation_corpus.py -q
```

Do not run all of these by default after small edits. Pick the smallest touched surface.

### Structural diagnostics

Preferred command:

```bash
bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-chapter-region-core
```

File-capture fallback when stdout transport is fragile:

```bash
bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-chapter-region-core > .run/lietaer_chapter_region_snapshot.json 2>&1
```

### Full-book checkpoint

Not part of the normal loop. Use only as explicit milestone evidence.

## 8. Guardrails

1. Do not change Stage 1 prompt/schema/cache unless the task explicitly targets Stage 1 authority or split hints.
2. Do not recover missing Stage 1 title or membership from projection-side layout evidence.
3. Do not use candidate-only operations as binding gate authority.
4. Do not use full-book reruns as the tuning loop.
5. Do not replace canonical WSL validation with debug-only Windows Python runs.
6. Do not revert unrelated dirty worktree changes.
7. Do not treat markdown cleanup as structural proof once topology authority is present.
8. Do not declare clean CI parity from a dirty worktree.

## 9. Definition Of Done

The structure-recognition remediation can be called complete when:

1. The chapter-region, first-20, and relevant End Times structural diagnostics pass from tracked repo state.
2. Full-book milestone diagnostic no longer fails in generic `unmapped_*` / markdown regex classes without a classified root cause.
3. Structure-aware gates are authoritative when topology projection exists.
4. Markdown structural normalizers are retired from readiness authority.
5. All regression fixtures needed for clean checkout are tracked.
6. Specs and this continuation document agree with the implementation.
7. `git diff --check` is clean.
8. Focused canonical WSL tests pass.
9. Any remaining limitations are documented as explicit unsupported topology classes, not hidden quality regressions.

## 10. Recommended Next Action

The next safest session-sized package is no longer another touched false-fragment/list-fragment runtime/display cleanup slice; that local boundary is now exhausted on the touched pipeline, structural-passthrough, and acceptance/summary surfaces.

1. Continue Workstream D only on still-untouched markdown-normalizer or reporting surfaces, keeping authoritative count/source, conservative fallback, advisory raw observability, and display/hygiene cleanup explicitly separated.
2. Do not reopen Workstream E unless a concrete protected-unit fragmentation regression is found.
3. If no adjacent untouched Workstream D surface is ready, move the next non-micro package to the fixture-baseline / pre-projection drift acceptance boundary instead of reopening the touched runtime/display path.
