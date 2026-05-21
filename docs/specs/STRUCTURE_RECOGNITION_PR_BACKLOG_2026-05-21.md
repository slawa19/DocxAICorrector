# Structure Recognition PR Backlog

Date: 2026-05-21
Status: Proposed implementation backlog
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
3. make page-furniture handling an explicit AI responsibility, then add narrow
   late cleanup and bounded rollout.

This backlog supersedes the phase numbering inside the individual specs when
planning implementation order.

## Global Rules

- Use one shared page-furniture phrase library only.
- The initial shared phrase library must match the current topology set exactly:
  - `this page intentionally left blank`
  - `page intentionally left blank`
  - `intentionally blank`
  - `intentionally left blank`
  - `эта страница намеренно оставлена пустой`
- Do not expand the phrase list in any PR unless the shared library contract is
  updated first.
- Do not add final Markdown structural rewrites.
- Do not implement adjacent-H1 AI repair in this package.
- Do not tune Stage 2 window sizes or overlap in this package.
- Do not raise the Stage 1 preview clamp above `400` in this package.
- Keep output thresholds advisory until upstream diagnostics from PR-3 land.
- If a profile still fails on R3/R4/R5-class defects, do not widen cleanup to
  make it green.

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

- shared detector finds EN/RU phrases and offsets;
- topology regression: `candidate_page_artifact_split` behavior unchanged;
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
- no R1/R2 cleanup;
- no Stage 1 prompt/schema changes;
- no Stage 2 tuning;
- no adjacent-H1 repair.

### Canonical Verification

```bash
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
2. Add compact prompt payload keys for the new signals.
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

- no prompt wording change yet;
- no cleanup yet;
- no Stage 2 window/overlap tuning;
- no clamp increase above `400`;
- no output-threshold tightening.

### Canonical Verification

```bash
bash scripts/test.sh tests/test_document_map.py -vv
bash scripts/test.sh tests/test_real_document_validation_corpus.py -vv -x
```

### Agent Instructions

- Do not “fix” token-budget fallout with broader cleanup.
- If raising preview to `400` drops descriptors, expose that clearly in
  diagnostics first.
- Keep all changes bounded to Stage 1 input fidelity and observability.

### Reviewer Checklist

- Are new signals deterministic and text-preserving?
- Did descriptor/cache versions bump correctly?
- Is preview default `400` everywhere it should be?
- Are tiered sampling counts visible in artifacts?

## PR-3 Prompt Responsibility, Upstream Checks, Cleanup, Rollout

### Goal

Make page-furniture handling an explicit Stage 1 AI responsibility, add upstream
diagnostics/checks, then enable narrow late cleanup and bounded rollout.

### Scope

- DocumentMap prompt responsibility update.
- Upstream diagnostics and acceptance checks.
- R1 blank-page cleanup.
- R2 narrow inline page-furniture cleanup.
- Bounded profile rollout.

### Files Likely Affected

- `src/docxaicorrector/structure/document_map.py`
- DocumentMap prompt tests / prompt builder tests
- `src/docxaicorrector/processing/preparation.py`
- `src/docxaicorrector/validation/structural.py`
- `src/docxaicorrector/pipeline/display_hygiene.py`
- `src/docxaicorrector/pipeline/late_phases.py`
- `src/docxaicorrector/validation/profiles.py`
- `corpus_registry.toml`
- `tests/test_document_map.py`
- `tests/test_output_display_hygiene.py`
- `tests/test_document_pipeline.py`
- existing structural diagnostic validation test file or new focused diagnostic
   payload test
- `tests/test_real_document_validation_corpus.py`

### Required Work

1. Update Stage 1 prompt responsibilities:
   - page furniture is non-semantic;
   - blank-page markers must not pollute outline/body;
   - use `split_hint` vs `review_zone` deliberately;
   - preserve semantic text order;
   - do not treat contamination as outline title text.
2. Bump `DOCUMENT_MAP_PROMPT_VERSION`.
3. Add upstream checks:
   - `document_map_page_furniture_signal_visibility`
   - `document_map_page_artifact_resolution_coverage`
   - `structure_model_runtime_stability`
   - Stage 2 seam diagnostics
4. Implement R1 blank-page cleanup with heading-inventory fail-closed invariant.
5. Implement R2 narrow inline page-furniture cleanup only when all guards pass.
6. Roll out on bounded profiles:
   - `lietaer-pdf-first-20-structure-core`
   - `lietaer-pdf-chapter-region-core`
   - `end-times-pdf-core`
7. Update bounded-profile detector thresholds in `corpus_registry.toml` only
   after the new upstream checks are present and reviewed on those profiles.
8. Use full-book only as milestone proof after bounded profiles stabilize.

### Tests Required

- prompt tests for key page-furniture instructions;
- prompt version bump changes cache identity;
- upstream checks appear in structural diagnostic payload;
- seam diagnostics include seam locations and near-seam counts;
- a focused structural diagnostic test asserts the new upstream-check keys and
   Stage 2 seam fields at the `evaluate_structural_preparation_diagnostic(...)`
   payload level;
- R1 removes only high-confidence blank markers and preserves heading inventory;
- R1 fails closed if heading inventory changes;
- R2 negative tests cover TOC, index ranges, citations, years, numbered lists,
  and legal short headings;
- bounded profile diagnostics are stable and explain failures honestly.

### Definition Of Done

- page-furniture handling is explicit in Stage 1 prompt contract;
- upstream checks and runtime fallback counters are visible in reports;
- R1/R2 cleanup use the shared detector library, not local phrase forks;
- bounded-profile thresholds are recorded in `corpus_registry.toml` only after
   rollout evidence exists for those exact profiles;
- output thresholds are tightened only where bounded rollout evidence exists;
- remaining R3/R4/R5 failures are recorded as topology-side backlog, not hidden.

### Forbidden Changes

- no phrase-library expansion;
- no adjacent-H1 AI repair;
- no Stage 2 tuning;
- no clamp increase above `400`;
- no regex rewrite for R3/R4/R5 structural defects.

### Canonical Verification

```bash
bash scripts/test.sh tests/test_document_map.py -vv
bash scripts/test.sh tests/test_output_display_hygiene.py -vv
bash scripts/test.sh tests/test_document_pipeline.py -vv -x
bash scripts/test.sh tests/test_real_document_validation_corpus.py -vv -x
```

Bounded structural diagnostics:

```bash
bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-first-20-structure-core
bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-chapter-region-core
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core
```

### Agent Instructions

- Do not use full-book runs as a tuning loop.
- If a model improves split hints but worsens timeout/split-fallback counters,
  do not switch globally inside this PR.
- If cleanup is tempted to make a red profile green, stop and record the defect
  as future topology-side work.
- Keep output thresholds advisory until upstream checks are actually present and
  reviewed.

### Reviewer Checklist

- Does the prompt now make page-furniture responsibility explicit?
- Are upstream checks present before stricter rollout?
- Do R1/R2 use the shared detector library?
- Is heading inventory preserved by cleanup?
- Does `corpus_registry.toml` only tighten thresholds for profiles with bounded
   evidence?
- Are remaining structural defects surfaced rather than hidden?

## Handoff Notes For Any Agent

- Start with PR-1. Do not parallelize PR-2/PR-3 on top of assumptions from
  unmerged shared-detector work.
- Keep each PR small enough that its causal effect is obvious from tests and
  diagnostics.
- When a failure appears, prefer adding visibility and samples before changing
  behavior.
- Use the specs as authority. Do not invent extra cleanup rules, role taxonomies,
  or phrase-list expansions outside approved follow-up work.
