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

## 2. What Is Not Yet Complete

### 2.1 Layout Signal Evidence slice

The runtime behavior is mostly implemented, but the slice is not fully closed as an acceptance package until all of the following are true:

1. `LAYOUT_SIGNAL_EVIDENCE_SLICE_SPEC_2026-05-14.md` clearly states the implemented runtime dependency on both topology acceptance and runtime flag propagation.
2. The spec clearly states that `document_topology_layout_signals` may be populated by event-log context or prepared-snapshot backfill.
3. Chapter-region regression fixtures are updated to the current live payload, including layout-enriched evidence and populated layout-signals summary.
4. `git diff --check` is clean.
5. Focused canonical WSL tests and the chapter-region diagnostic pass from the updated repo state.

### 2.2 Topology-first parent remediation

The parent remediation is not complete. Current status by area:

- R1 Stage 1.5 topology projection: substantially implemented.
- R2 structure-aware quality gates: partially implemented, not complete as a universal gate migration.
- R3 markdown structural postprocessor retirement: not complete.
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
6. Keep legacy/markdown signals visible as advisory diagnostics during migration, without letting them override stronger structural authority.
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
9. Tracked fixture trio under `tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/` matches the accepted diagnostic state.

### 4.3 Structure-aware gate acceptance

When topology projection is present:

1. `toc_body_concat_markdown_detected` remains visible as raw/advisory evidence.
2. `toc_body_concat_structure_detected` is the authoritative gate signal when projection support is sufficient.
3. `toc_body_concat_gate_source` clearly states whether the gate used `topology_projection` or `legacy_markdown`.
4. `candidate_page_artifact_split` never flips the gate to topology authority.
5. Binding split operations and projected TOC units may flip the gate to topology authority.
6. Raw unmapped counts remain visible.
7. Structure-unit unmapped counts are used for structural gate decisions when topology projection is present.

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

A3. Normalize intentional line endings / whitespace without unrelated churn.

A4. Regenerate or update the tracked chapter-region fixture trio:

- `tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/structural_diagnostic.json`
- `tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/document_map.json`
- `tests/artifacts/structural_diagnostics/lietaer-pdf-chapter-region-core/document_topology_projection.json`

A5. Update fixture tests so they assert the current accepted state, including layout-signals summary and enriched evidence.

Acceptance:

- `git diff --check` passes.
- fixture tests pass.
- live chapter-region diagnostic and tracked fixture expectations agree.

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

- keep markdown detector as advisory;
- use topology projection when bounded TOC and binding projected TOC units/splits are present;
- never use `candidate_page_artifact_split` as binding gate support.

C3. For unmapped thresholds:

- expose raw counts;
- expose structure-unit counts;
- make gate basis explicit through `*_gate_source` or `*_count_basis` fields;
- use structure-unit basis when topology projection exists.

C4. Add focused tests covering:

- legacy fallback path when no projection exists;
- topology path when binding TOC split exists;
- candidate-only page artifact remains non-binding;
- raw vs structure-unit unmapped counts.

Acceptance:

- structural profiles pass/fail from structure-aware gate fields when projection is authoritative;
- markdown fields remain visible but advisory;
- tests prove the fallback behavior is conservative.

### Workstream D: Markdown structural normalizer retirement

Goal: stop using final markdown cleanup as structural proof.

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

Current code already contains topology-aware descriptor fields and several fallback-hardening pieces. This workstream verifies and completes them against the parent spec.

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

1. Update tracked chapter-region fixtures to match current live diagnostic.
2. Make `git diff --check` clean.
3. Finish spec synchronization in the two active spec files.
4. Run focused verification:

```bash
bash scripts/test.sh tests/test_structure_topology.py::test_apply_document_map_topology_layout_confirms_explicit_authority_across_mixed_heading_tiers -q
bash scripts/test.sh tests/test_preparation.py::test_apply_prepared_snapshot_fields_backfills_layout_signals_context_when_enabled_runtime_config_present -q
bash scripts/test.sh tests/test_real_document_validation_corpus.py::test_build_preparation_diagnostic_defaults_includes_layout_signals_event_context -q
bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-chapter-region-core
```

5. If fixtures changed, run the fixture-lock test(s) in `tests/test_real_document_validation_corpus.py`.

### Next implementation tasks after hygiene

1. Complete structure-aware gate migration for `toc_body_concat` and unmapped thresholds.
2. Add or tighten tests proving markdown structural signals are advisory when topology authority is present.
3. Audit markdown structural normalizers and mark each use as advisory/display/hygiene or remove structural authority usage.
4. Verify Stage 2 topology precedence and fallback hardening against parent-spec Slice 1-5 invariants.
5. Perform one milestone full-book diagnostic only after the above passes.

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

The next safest step is Workstream A plus B:

1. update chapter-region fixture trio from the accepted live diagnostic;
2. clean whitespace/EOL issues;
3. finish spec synchronization;
4. rerun focused fixture and chapter-region diagnostics.

Only after that should implementation move deeper into Workstream C and D for complete structure-aware gate migration and markdown structural normalizer retirement.
