# Structure Recognition PR Backlog

Date: 2026-05-21
Status: Archived 2026-05-30; dead-end / superseded by reader-first migration
Source specs:

- `docs/specs/STRUCTURE_RECOGNITION_INPUT_FIDELITY_SPEC_2026-05-21.md`
- `docs/specs/OUTPUT_DISPLAY_HYGIENE_AND_STRUCTURE_DETECTORS_SPEC_2026-05-21.md`
- `docs/AI_FIRST_STRUCTURE_RECOVERY_SPEC_2026-05-08.md`
- `docs/specs/TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md`

## Purpose

This document converts the agreed structure-recovery work into a practical,
small-PR engineering backlog.

The ordering is intentional:

1. establish one shared page-furniture detector and output observability;
2. improve Stage 1 input fidelity and sampling stability;
3. make page-furniture handling an explicit AI responsibility and add upstream
   diagnostics;
4. add narrow display-hygiene cleanup with artifacted raw/cleaned detector
   observability;
5. roll out strict thresholds only after bounded-profile evidence exists.

This backlog supersedes the phase numbering inside the individual specs when
planning implementation order.

## Global Rules

- Use one shared page-furniture phrase library only.
- The initial shared phrase library must preserve the currently implemented
  topology baseline exactly; this backlog must not enumerate or expand the
  phrase set by copying literals from a particular source document.
- The shared library is a document-agnostic page-furniture taxonomy, not a
  vocabulary extracted from any single test book. Document-specific headers,
  footers, or page labels belong in profile diagnostics / evidence, not in the
  global phrase library.
- Do not expand the phrase list in any PR unless the shared library contract is
  updated first with document-agnostic rationale and cross-corpus tests.
- Do not add final Markdown structural rewrites.
- Do not implement adjacent-H1 AI repair in this package.
- Do not tune Stage 2 window sizes or overlap in this package.
- Do not raise the Stage 1 preview clamp above `400` in this package.
- Keep output thresholds advisory until upstream diagnostics from PR-3A land and
  bounded-profile baseline artifacts from PR-3C are reviewed.
- If a profile still fails on R3/R4/R5-class defects, do not widen cleanup to
  make it green.

Terminology note: this backlog uses `DH-R1` and `DH-R2-Narrow` for output
display-hygiene cleanup rules. Do not confuse them with topology-remediation
`R1` / `R2` / `R3` in
`TOPOLOGY_FIRST_STRUCTURE_RECOVERY_REMEDIATION_SPEC_2026-05-12.md`.

## Authority Boundary Rules

- This package is not an active full-book failure fix. The latest official
  full-book milestone has `failed_checks = []`; treat this work as input
  fidelity, observability, and bounded display-hygiene hardening.
- Detector/check plumbing must not turn heuristic hints into final structural
  authority.
- Any post-AI readiness or structural validation change must state whether it is
  reading pre-AI diagnostics, advisory hints, applied `StructureMap` state, or
  explicit reconciliation/report fields.
- If implementation touches helper APIs that can read heuristic hints, add tests
  proving post-AI readiness does not treat those hints as final structure unless
  `DocumentMap` / reconciled `StructureMap` projects the same role.
- Full-book runs are milestone proof only. Do not use full-book as an inner-loop
  tuning step.

## Runtime And Verification Rules

- Follow `AGENTS.md` runtime rules.
- Canonical tests must run through WSL shell entrypoints, not PowerShell pytest.
- Use:

```bash
bash scripts/test.sh tests/test_file.py -vv
bash scripts/test.sh tests/ -q
```

- For structural diagnostics use:

```bash
bash scripts/run-structural-preparation-diagnostic.sh <document_profile_id>
```

- Before any final verification, check dirty worktree with:

```bash
git status --porcelain
```

## PR-1 Shared Detector And Output Observability

### Goal

Create one shared page-furniture detector library and add read-only output
detectors / acceptance plumbing without changing Markdown or topology behavior.

### Scope

- Shared page-furniture detector extraction.
- Detector-only output plumbing.
- Advisory acceptance metrics and samples.

### Files Likely Affected

- new `src/docxaicorrector/structure/page_furniture_detection.py`
- `src/docxaicorrector/structure/topology.py`
- new `src/docxaicorrector/pipeline/display_hygiene.py`
- `src/docxaicorrector/validation/structural.py`
- `src/docxaicorrector/validation/profiles.py`
- optional helper adjustments in `src/docxaicorrector/core/models.py`
- `tests/test_output_display_hygiene.py`
- `tests/test_real_document_validation_corpus.py`
- existing topology test file such as `tests/test_structure_topology.py`

### Required Work

1. Extract `_PAGE_FURNITURE_PHRASES`, matching, normalization, and offset logic
   into `page_furniture_detection.py`.
2. Switch `topology.py` to the shared detector library.
3. Preserve current topology semantics for `candidate_page_artifact_split`.
4. Implement detector-only APIs for:
   - `pdf_blank_page_marker_leakage`
   - `inline_page_furniture_leakage`
   - `adjacent_h1_without_body`
   - `heading_body_concat_detected`
   - `h1_epigraph_attribution_pattern`
5. Add metrics, samples, and advisory threshold plumbing to structural
   validation.
6. Keep cleanup disabled. No Markdown rewriting in this PR.

### Tests Required

- shared detector preserves existing baseline phrase coverage and offsets;
ё- topology regression: `candidate_page_artifact_split` behavior unchanged;
- detector tests for all five output detectors;
- advisory profiles collect metrics without failing;
- strict profile fields serialize and report correctly when configured.

### Definition Of Done

- one shared phrase library exists and topology imports it;
- no second phrase list remains in `topology.py`;
- structural reports include detector counts and samples;
- no Markdown output changes occur;
- focused tests pass.

### Forbidden Changes

- no phrase-library expansion;
- no `DH-R1` / `DH-R2-Narrow` cleanup;
- no Stage 1 prompt/schema changes;
- no Stage 2 tuning;
- no adjacent-H1 repair.

### Canonical Verification

```bash
bash scripts/test.sh tests/test_structure_topology.py -vv
bash scripts/test.sh tests/test_output_display_hygiene.py -vv
bash scripts/test.sh tests/test_real_document_validation_corpus.py -vv -x
```

### Agent Instructions

- Keep this PR behavior-preserving for topology and Markdown output.
- Reuse the shared detector everywhere; do not create a local fallback phrase
  list.
- If a test suggests widening phrases, stop and record it as follow-up instead.

### Reviewer Checklist

- Does topology still use the same initial phrase set?
- Are all output detectors read-only?
- Is there any accidental Markdown cleanup in this PR?
- Are advisory metrics visible in the report payload?

## PR-2 Stage 1 Input Fidelity

### Goal

Make page-furniture contamination and related structural-damage signals visible
to Stage 1, increase preview fidelity to `400`, and add token-budget/sampling
observability.

### Scope

- Stage 1 descriptor signals.
- Stage 1 preview `120 -> 400`.
- Ordered sampling priority.
- Token-budget coverage diagnostics.

### Files Likely Affected

- `src/docxaicorrector/structure/document_map.py`
- `src/docxaicorrector/processing/preparation.py`
- `src/docxaicorrector/core/config_structure_sections.py`
- `src/docxaicorrector/core/config_loader_layers.py`
- `src/docxaicorrector/core/config.py`
- `config.toml`
- optional helper/model adjustments in `src/docxaicorrector/core/models.py`
- `tests/test_document_map.py`
- config-loader tests
- `tests/test_real_document_validation_corpus.py`

### Required Work

1. Add deterministic Stage 1 descriptor signals:
   - `contains_page_furniture_phrase`
   - `page_furniture_phrase_kinds`
   - `page_furniture_offsets`
   - `contains_blank_page_marker`
   - `contains_inline_page_number_island`
   - `running_header_candidate`
   - `heading_body_concat_candidate`
2. Add compact descriptor / prompt-payload keys for the new signals so the
   prompt builder can serialize them, but do not add new Stage 1 responsibility
   wording in this PR.
3. Bump `DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION`.
4. Raise default `structure_recovery.document_map.preview_chars` from `120` to
   `400`.
5. Keep the clamp unchanged at max `400`.
6. Add token-budget diagnostics:
   - sampled before token budget
   - sampled after token budget
   - dropped signal counts
7. Replace flat sampling importance with ordered tiers:
   - hard structural
   - anchor structural
   - damage signal
   - soft context
8. Persist sampled counts by tier in debug artifacts.

### Tests Required

- contaminated paragraph after char 120 still gets signal;
- descriptor schema version changes cache identity;
- config default resolves to preview `400`;
- config-loader tests cover the new default and clamp behavior;
- token-budget diagnostics report before/after sampled counts;
- ordered sampling preserves hard > anchor > damage > soft priority;
- short-text soft context does not starve headings or TOC anchors.

### Definition Of Done

- Stage 1 descriptors carry new signals without mutating paragraph text;
- preview default is `400`;
- token-budget fallout is observable in diagnostics;
- ordered sampling works by tier, not flat OR;
- output thresholds are still advisory after this PR.

### Forbidden Changes

- no Stage 1 responsibility wording change yet; compact payload/key plumbing is
  allowed only to carry PR-2 descriptor signals forward to PR-3A;
- no cleanup yet;
- no Stage 2 window/overlap tuning;
- no clamp increase above `400`;
- no output-threshold tightening.

### Canonical Verification

```bash
bash scripts/test.sh tests/test_document_map.py -vv
bash scripts/test.sh tests/test_config.py -vv
bash scripts/test.sh tests/test_real_document_validation_corpus.py -vv -x
```

Focused structural diagnostic:

```bash
bash scripts/run-structural-preparation-diagnostic.sh <representative_pdf_core_profile>
```

### Agent Instructions

- Do not “fix” token-budget fallout with broader cleanup.
- If raising preview to `400` drops descriptors, expose that clearly in
  diagnostics first.
- Keep all changes bounded to Stage 1 input fidelity and observability.
- Do not add prompt responsibility prose in PR-2; defer wording and prompt
  version changes to PR-3A.

### Reviewer Checklist

- Are new signals deterministic and text-preserving?
- Did descriptor/cache versions bump correctly?
- Is preview default `400` everywhere it should be?
- Are tiered sampling counts visible in artifacts?

## PR-3A Prompt Responsibility And Upstream Diagnostics

### Goal

Make page-furniture handling an explicit Stage 1 AI responsibility and add
read-only upstream diagnostics/checks. Do not enable display-hygiene cleanup or
tighten output thresholds in this PR.

### Scope

- DocumentMap prompt responsibility update.
- Prompt version/cache invalidation.
- Upstream structural diagnostic checks.
- Stage 2 seam diagnostics as read-only report/artifact fields.

### Files Likely Affected

- `src/docxaicorrector/structure/document_map.py`
- DocumentMap prompt tests / prompt builder tests
- `src/docxaicorrector/processing/preparation.py`
- `src/docxaicorrector/validation/structural.py`
- existing structural diagnostic validation test file or new focused diagnostic
  payload test
- `tests/test_document_map.py`
- `tests/test_real_document_validation_corpus.py`

### Required Work

1. Update Stage 1 prompt responsibilities:
   - page furniture is non-semantic;
   - blank-page markers must not pollute outline/body;
   - use `split_hint` vs `review_zone` deliberately;
   - preserve semantic text order;
   - do not treat contamination as outline title text;
   - explicitly mention the PR-2 descriptor keys and their meanings.
2. Bump `DOCUMENT_MAP_PROMPT_VERSION` and ensure cache identity changes.
3. Add upstream checks:
   - `document_map_page_furniture_signal_visibility`
   - `document_map_page_artifact_resolution_coverage`
   - `structure_model_runtime_stability`
4. Add Stage 2 seam diagnostics with seam locations and near-seam signal counts.
5. Keep all new checks advisory unless an existing profile already opts into a
   strict threshold.

### Tests Required

- prompt tests for key page-furniture instructions and descriptor-key meanings;
- prompt version bump changes cache identity;
- upstream checks appear in structural diagnostic payload;
- seam diagnostics include seam locations and near-seam counts;
- a focused structural diagnostic test asserts the new upstream-check keys and
  Stage 2 seam fields at the `evaluate_structural_preparation_diagnostic(...)`
  payload level;
- structural validation/report code remains phase-aware and does not treat
  heuristic hints as final post-AI structure.

### Definition Of Done

- page-furniture handling is explicit in Stage 1 prompt contract;
- upstream checks and runtime fallback counters are visible in reports;
- Stage 2 seam diagnostics are read-only and artifacted;
- output thresholds are still advisory after this PR.

### Forbidden Changes

- no phrase-library expansion;
- no display-hygiene cleanup;
- no `corpus_registry.toml` threshold tightening;
- no adjacent-H1 AI repair;
- no Stage 2 tuning;
- no clamp increase above `400`.

### Canonical Verification

```bash
bash scripts/test.sh tests/test_document_map.py -vv
bash scripts/test.sh tests/test_real_document_validation_corpus.py -vv -x
```

Focused structural diagnostics:

```bash
bash scripts/run-structural-preparation-diagnostic.sh <representative_pdf_core_profile>
bash scripts/run-structural-preparation-diagnostic.sh <representative_late_region_profile>
```

### Agent Instructions

- Do not use full-book runs as a tuning loop.
- If a model improves split hints but worsens timeout/split-fallback counters,
  do not switch globally inside this PR.
- Keep output thresholds advisory until upstream checks are present and reviewed
  on bounded profiles.

### Reviewer Checklist

- Does the prompt now make page-furniture responsibility explicit?
- Are descriptor keys explained in prompt text?
- Are upstream checks present before stricter rollout?
- Are seam diagnostics read-only and visible in the diagnostic payload?
- Does validation avoid heuristic hints as final post-AI authority?

## PR-3B Display-Hygiene Cleanup And Artifact Contract

### Goal

Enable narrow final-output display-hygiene cleanup for confirmed page-furniture
noise, with raw/cleaned detector observability and fail-closed heading inventory
protection. Do not tighten profile thresholds in this PR.

### Scope

- `DH-R1` blank-page marker cleanup.
- `DH-R2-Narrow` inline page-furniture cleanup.
- Display hygiene artifact retention and log event.
- Late-phase integration before formatting transfer / DOCX conversion consumes
  user-visible Markdown.

### Files Likely Affected

- `src/docxaicorrector/pipeline/display_hygiene.py`
- `src/docxaicorrector/pipeline/late_phases.py`
- `src/docxaicorrector/validation/structural.py`
- `tests/test_output_display_hygiene.py`
- `tests/test_document_pipeline.py`
- `tests/test_real_document_validation_corpus.py`

### Required Work

1. Define the exact insertion point relative to existing transitional late
   normalizers before editing code.
2. Collect detector counts before and after display hygiene over the final
   Markdown that is intended for user-visible DOCX output.
3. Implement `DH-R1` blank-page cleanup with heading-inventory fail-closed
   invariant.
4. Implement `DH-R2-Narrow` inline page-furniture cleanup only when all guards
   pass.
5. Persist `.run/display_hygiene_reports/<run_id>.json` with raw/cleaned detector
   counts, samples, input/output hashes, rule counts, and
   `heading_inventory_preserved`.
6. Emit `display_hygiene_report_saved` with artifact path, changed flag, rule
   counts, cleaned detector counts, and heading-inventory status.
7. Expose display-hygiene report path and detector counts through existing
   docx-phase / quality-report payloads so structural validation can consume
   them without rescanning when possible.

### Tests Required

- `DH-R1` removes only high-confidence blank markers and preserves heading
  inventory;
- `DH-R1` fails closed if heading inventory changes;
- `DH-R2-Narrow` negative tests cover TOC, index ranges, citations, years,
  numbered lists, and legal short headings;
- raw and cleaned detector counts are reported separately;
- `.run/display_hygiene_reports/<run_id>.json` shape is covered by a focused
  artifact/logging test or equivalent pipeline test;
- cleanup does not repair adjacent-H1, heading/body concat, or epigraph
  attribution structural defects.

### Definition Of Done

- `DH-R1` / `DH-R2-Narrow` cleanup use the shared detector library, not local
  phrase forks;
- heading inventory is preserved or cleanup fails closed with diagnostics;
- display-hygiene reports and `display_hygiene_report_saved` logs exist;
- structural defects remain detector-visible rather than hidden by cleanup;
- output thresholds remain advisory after this PR.

### Forbidden Changes

- no phrase-library expansion;
- no Stage 1 prompt/schema changes;
- no adjacent-H1 AI repair;
- no Stage 2 tuning;
- no `corpus_registry.toml` threshold tightening;
- no regex rewrite for R3/R4/R5 structural defects.

### Canonical Verification

```bash
bash scripts/test.sh tests/test_output_display_hygiene.py -vv
bash scripts/test.sh tests/test_document_pipeline.py -vv -x
bash scripts/test.sh tests/test_real_document_validation_corpus.py -vv -x
```

### Agent Instructions

- If cleanup is tempted to make a red profile green, stop and record the defect
  as future topology-side work.
- If a detector hit requires creating, deleting, merging, splitting, promoting,
  demoting, or renaming headings, leave it as a detector result; do not repair it
  in display hygiene.
- Use direct Markdown scanning as source of truth when both direct Markdown and a
  persisted report are available for the current run.

### Reviewer Checklist

- Is the insertion point relative to existing normalizers explicit?
- Do `DH-R1` / `DH-R2-Narrow` use the shared detector library?
- Is heading inventory preserved or fail-closed?
- Are raw and cleaned detector counts persisted and logged?
- Are structural defects surfaced rather than hidden?

## PR-3C Bounded Rollout And Threshold Tightening

### Goal

Turn advisory detector metrics into strict bounded-profile thresholds only after
PR-3A upstream diagnostics and PR-3B display-hygiene reports provide reviewed
evidence for each profile.

### Scope

- Bounded profile diagnostics and saved baseline evidence.
- Profile-specific threshold updates in `corpus_registry.toml`.
- Expected-failed-check metadata where a profile intentionally becomes red.
- Full-book milestone proof only after bounded profiles stabilize.

### Preconditions

- PR-3A is merged and upstream checks are present in structural diagnostic
  payloads.
- PR-3B is merged and display-hygiene artifacts/logging are present.
- A bounded late/chapter-region profile is registered and runnable before rollout
  verification claims coverage for late-document structure cases.

### Files Likely Affected

- `src/docxaicorrector/validation/profiles.py`
- `corpus_registry.toml`
- `tests/test_real_document_validation_corpus.py`
- bounded-profile baseline artifacts or report fixtures, if this repository
  tracks them for the relevant profile class

### Required Work

1. Run and save reviewed baseline diagnostic evidence for each bounded profile
   class selected from `corpus_registry.toml` for this rollout:
   - a representative early/core PDF structure profile;
   - a representative late/chapter-region PDF structure profile;
   - a representative cross-document page-furniture profile.
2. Record, per profile, upstream-check values, raw/cleaned detector counts,
   display-hygiene report path, and any remaining detector samples.
3. Update bounded-profile detector thresholds in `corpus_registry.toml` only when
   the saved baseline evidence supports the exact threshold.
4. If a profile intentionally becomes red after detector rollout, update
   `structural_expected_failed_checks` or profile-specific expectation metadata
   with recorded rationale.
5. Use full-book only as milestone proof after bounded profiles stabilize.

### Tests Required

- profile threshold fields serialize and report correctly;
- advisory profiles collect metrics without failing;
- strict bounded profiles fail/pass according to configured thresholds;
- expected-failed-check metadata is explicit when a rollout profile is knowingly
  red;
- bounded profile diagnostics are stable and explain failures honestly.

### Definition Of Done

- every threshold change has a matching saved baseline artifact/report for that
  exact profile;
- `corpus_registry.toml` only tightens thresholds where bounded rollout evidence
  exists;
- remaining R3/R4/R5 failures are recorded as topology-side backlog, not hidden;
- no full-book tuning loop was used.

### Forbidden Changes

- no phrase-library expansion;
- no new cleanup rules;
- no adjacent-H1 AI repair;
- no Stage 2 tuning;
- no clamp increase above `400`;
- no threshold changes without saved bounded-profile evidence.

### Canonical Verification

```bash
bash scripts/test.sh tests/test_real_document_validation_corpus.py -vv -x
```

Bounded structural diagnostics:

```bash
bash scripts/run-structural-preparation-diagnostic.sh <representative_pdf_core_profile>
bash scripts/run-structural-preparation-diagnostic.sh <representative_late_region_profile>
bash scripts/run-structural-preparation-diagnostic.sh <representative_page_furniture_profile>
```

### Agent Instructions

- Do not use full-book runs as a tuning loop.
- Do not hide new detector failures by raising thresholds without a recorded
  profile-specific rationale.
- If bounded diagnostics expose R3/R4/R5 structural defects, record them as
  topology-side backlog instead of widening display cleanup.

### Reviewer Checklist

- Does every threshold edit have saved bounded-profile evidence?
- Is the representative late/chapter-region profile registered and runnable?
- Are expected failures declared explicitly rather than hidden by thresholds?
- Was full-book used only as milestone proof?

## Handoff Notes For Any Agent

- Start with PR-1. Do not parallelize PR-2, PR-3A, PR-3B, or PR-3C on top of
  assumptions from unmerged shared-detector work.
- Keep each PR small enough that its causal effect is obvious from tests and
  diagnostics.
- When a failure appears, prefer adding visibility and samples before changing
  behavior.
- Use the specs as authority. Do not invent extra cleanup rules, role taxonomies,
  or phrase-list expansions outside approved follow-up work.
