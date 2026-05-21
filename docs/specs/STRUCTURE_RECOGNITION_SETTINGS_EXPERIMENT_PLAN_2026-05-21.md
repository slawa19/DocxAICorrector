# Structure Recognition Settings Experiment Plan

Date: 2026-05-21
Status: Proposed bounded experiment plan

## Purpose

Провести ограниченный и воспроизводимый эксперимент по настройкам AI-first
structure recognition на книге `lietaer-pdf-full-benchmark`, чтобы ответить на
один практический вопрос:

```text
Какие 1-2 изменения настроек реально улучшают распознавание структуры и итоговый
reader-visible результат, не ломая текущий benchmark profile и не превращая
full-book run в бесконечный tuning loop?
```

План намеренно ограничен:

- baseline + 2 обязательных experiment set;
- 1 дополнительный conditional set только если первые два дают смешанный сигнал;
- сравнение и машинное, и читательское;
- без изменения `default_run_profile`;
- без подмены задачи на Simple Reader-First MVP.

## Scope

Этот документ касается только настроек upstream structure recognition.

Вне scope:

- `chunk_size` как translation/downstream parameter;
- reader-cleanup / second-pass cleanup;
- расширение phrase library;
- Stage 2 prompt/schema redesign;
- open-ended full-book tuning loop.

## Current Baseline

Canonical benchmark document:

- document profile: `lietaer-pdf-full-benchmark`
- current default run profile: `ui-parity-translate-benchmark-topology-advisory`

Important fixed properties of the baseline profile in `corpus_registry.toml`:

- `processing_operation = "translate"`
- `translation_output_quality_gate_policy = "advisory"`
- `structure_recognition_mode = "always"`
- `structure_recovery_topology_projection_enabled = true`
- `structure_recovery_topology_projection_binding_splits_enabled = true`

This experiment keeps those properties fixed and only varies structure settings.

## Why These Settings

The current code suggests three likely pressure points for book-scale structure
quality:

1. Stage 1 document-map preview is too short for contaminated or late-appearing
   heading evidence.
2. Anchored Stage 2 classification currently uses `overlap = 0`, which makes
   seam/boundary errors harder to recover.
3. Anchored Stage 2 `max_window_paragraphs = 3000` is large enough that the
   actual effective window may be token-budget-trimmed, producing unstable window
   boundaries relative to what the nominal setting implies.

The candidate knobs are therefore:

- `DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_PREVIEW_CHARS`
- `DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_MAX_WINDOW_PARAGRAPHS`
- `DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_OVERLAP_PARAGRAPHS`
- optional only if needed: `DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_MAX_INPUT_TOKENS`

## Execution Model

For the first pass, do **not** add new run-profile fields to `RunProfile`. The
registry does not currently expose these structure settings directly.

Fastest reproducible execution path for this experiment:

- keep using the existing benchmark run profile
  `ui-parity-translate-benchmark-topology-advisory`;
- inject structure-setting overrides via WSL environment variables;
- record the exact env set used for each run in the comparison notes.

If the experiment finds a winning setting set, those values can later be promoted
into dedicated registry-wired profiles in a separate implementation slice.

## Preflight Rules

Before any run:

1. Check dirty worktree with `git status --porcelain`.
2. Record current `git rev-parse HEAD`.
3. Compare current commit with the commit of the latest baseline report.
4. If the latest baseline report was produced from a different commit or the
   current worktree is materially dirty, rerun baseline on the current state
   before comparing experiments.

Do not interpret cross-commit differences as setting effects.

## Fixed Constants For All Experiment Runs

Keep these fixed across baseline and experiments:

- document profile: `lietaer-pdf-full-benchmark`
- run profile: `ui-parity-translate-benchmark-topology-advisory`
- `DOCX_AI_CHUNK_SIZE` unset unless a separate chunk experiment is explicitly run
  outside this plan
- model selector unchanged from active baseline
- no reader-cleanup logic
- no prompt changes
- no topology phrase-library changes

Optional debug capture to keep constant across all experimental runs:

- `DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_SAVE_DEBUG_ARTIFACTS=1`
- `DOCX_AI_STRUCTURE_RECOVERY_TOPOLOGY_SAVE_DEBUG_ARTIFACTS=1`

## Experiment Matrix

### B0 Baseline

Purpose:

- establish current-commit baseline under the existing settings.

Overrides:

- none beyond optional debug-artifact flags.

### E1 Stage 1 Fidelity

Purpose:

- test whether the biggest current bottleneck is simply too little Stage 1 text
  visibility.

Overrides:

```text
DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_PREVIEW_CHARS=400
```

Expected upside:

- better heading contamination visibility;
- better compound TOC / heading-body boundary evidence;
- better late-line contamination visibility.

Main risk:

- prompt gets heavier and Stage 1 may sample fewer descriptors unless the token
  budget is still sufficient.

### E2 Stage 1 Fidelity + Stage 2 Seam Stabilization

Purpose:

- test whether seam/boundary handling is currently the second real bottleneck.

Overrides:

```text
DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_PREVIEW_CHARS=400
DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_MAX_WINDOW_PARAGRAPHS=1200
DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_OVERLAP_PARAGRAPHS=50
```

Expected upside:

- fewer boundary-related heading splits;
- fewer late-window seam errors;
- more stable Stage 2 decisions around adjacent heading/body transitions.

Main risk:

- more windows, longer runtime, more cost.

### E3 Conditional Budget Compensation

Run this set only if:

- E1 or E2 shows reader-visible structural improvement, but
- Stage 1 metrics suggest sampling shrinkage or outline coverage degradation.

Overrides:

```text
DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_PREVIEW_CHARS=400
DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_MAX_WINDOW_PARAGRAPHS=1200
DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_OVERLAP_PARAGRAPHS=50
DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_MAX_INPUT_TOKENS=240000
```

Expected upside:

- recover Stage 1 descriptor coverage after the preview increase.

Main risk:

- slower and more expensive DocumentMap call without guaranteed quality gain.

## Run Count Policy

Bounded run plan:

1. B0 baseline run if needed on current commit.
2. E1 mandatory.
3. E2 mandatory.
4. E3 only if E1/E2 give mixed or contradictory signals.

This keeps the plan within 2-3 new full-book runs instead of open-ended tuning.

## Canonical Command Template

Use the canonical WSL entrypoint:

```bash
bash scripts/run-real-document-validation.sh
```

When agent-side transport is needed from non-WSL shell, use `wsl.exe` with echo
markers.

Template for a run with overrides:

```bash
echo START && wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector; export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-full-benchmark; export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-benchmark-topology-advisory; export DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_PREVIEW_CHARS=400; export DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_MAX_WINDOW_PARAGRAPHS=1200; export DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_OVERLAP_PARAGRAPHS=50; export DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_SAVE_DEBUG_ARTIFACTS=1; export DOCX_AI_STRUCTURE_RECOVERY_TOPOLOGY_SAVE_DEBUG_ARTIFACTS=1; bash scripts/run-real-document-validation.sh 2>&1" && echo DONE
```

For B0 baseline, remove the experiment-specific env vars.

## Required Artifacts Per Run

For each run, capture:

- report path;
- run id;
- git head;
- exact env override set;
- latest Markdown artifact path;
- any saved structural debug artifacts.

Primary report locations:

- `tests/artifacts/real_document_pipeline/lietaer_pdf_full_benchmark_report.json`
- run-scoped report under `tests/artifacts/real_document_pipeline/runs/<run_id>/`

## Machine Comparison Checklist

For each run, record these fields side by side.

### Runtime Config

- `runtime_config.effective.model`
- `runtime_config.effective.chunk_size`
- `runtime_config.effective.structure_recognition_mode`
- `runtime_config.effective.structure_recognition_enabled`

### Preparation Counters

- `preparation.paragraph_count`
- `preparation.job_count`
- `preparation.ai_classified_count`
- `preparation.ai_heading_count`
- `preparation.ai_role_change_count`
- `preparation.ai_heading_promotion_count`
- `preparation.ai_heading_demotion_count`
- `preparation.ai_structural_role_change_count`

### Structural Snapshot

- `preparation_diagnostic_snapshot.heading_count`
- `preparation_diagnostic_snapshot.toc_header_count`
- `preparation_diagnostic_snapshot.toc_entry_count`
- `preparation_diagnostic_snapshot.bounded_toc_region_count`
- `preparation_diagnostic_snapshot.remaining_isolated_marker_count`
- `preparation_diagnostic_snapshot.readiness_status`
- `preparation_diagnostic_snapshot.readiness_reasons`
- `preparation_diagnostic_snapshot.document_map_present`
- `preparation_diagnostic_snapshot.outline_coverage_ratio`
- `preparation_diagnostic_snapshot.document_topology_projection_status`
- `preparation_diagnostic_snapshot.document_topology_projection_status_reason`

### Acceptance / Quality Checks

- `failed_checks`
- formatting-diagnostics threshold actual vs threshold
- unmapped-source threshold actual vs threshold
- unmapped-target threshold actual vs threshold
- key-headings / heading-drift outcomes if present
- bullet-heading / toc-body-concat outcomes if present

### Optional Debug Comparison

If debug artifacts are present, also compare:

- DocumentMap sampled logical-index count;
- number of split hints;
- number of review zones;
- topology projected-unit count;
- seam-adjacent or contaminated-unit diagnostics if emitted.

## Human Review Checklist

Do a short side-by-side read of baseline vs experiment artifacts. Review exactly
these zones, not the whole book.

### Zone 1 Front Matter / TOC Boundary

Check:

- TOC still detected;
- TOC lines not merged into body;
- first narrative section begins cleanly;
- page furniture is not promoted to heading.

### Zone 2 Early Chapter Entry

Check:

- chapter heading integrity;
- heading/body separation;
- adjacent heading fragments;
- blank-page/page-number contamination.

### Zone 3 Late Chapter Region

Use the known late composite-heading / TOC-sensitive area around Chapter 8-11.

Check:

- chapter heading continuity;
- no seam-induced heading collapse;
- no phantom heading promotion from page furniture;
- no body paragraph swallowed into heading.

### Zone 4 Back Matter / Index Region

Check:

- index-like material remains bounded;
- no major bleed of index/page-range text into narrative headings;
- no obvious false chapter promotion in late-book utility sections.

## Human Scorecard

Score each run against baseline on the following six dimensions:

- chapter heading integrity
- heading/body separation
- TOC/body boundary cleanliness
- page-furniture leakage
- late-book seam stability
- back-matter containment

Scoring per dimension:

- `+1` = clearly better than baseline
- `0` = no clear difference
- `-1` = clearly worse than baseline

Human-review guardrails:

- any catastrophic regression in chapter boundaries or TOC/body transition is an
  automatic reject;
- one cosmetic improvement does not outweigh a structural regression.

## Machine Decision Rules

Treat a setting set as **machine-pass** only if all conditions hold:

1. `failed_checks` does not become worse than baseline.
2. `document_map_present = true` remains true.
3. `document_topology_projection_status = "built"` remains true.
4. `outline_coverage_ratio` does not drop by more than `0.02` from baseline.
5. `bounded_toc_region_count` does not decrease.
6. `remaining_isolated_marker_count` does not increase.
7. formatting-diagnostics actual count does not increase by more than `2`.
8. unmapped-source actual count does not increase by more than `2`.
9. unmapped-target actual count does not increase by more than `1`.

## Promotion Rules

Choose the winning setting set using this order:

1. machine-pass status;
2. no catastrophic human-review regression;
3. highest net human score;
4. lower runtime/cost if quality is otherwise tied.

If both E1 and E2 machine-pass and human-score is tied, prefer E1 because it is
the smaller, easier-to-explain change.

If E1 improves Stage 1 visibility but degrades `outline_coverage_ratio`, run E3.

If E2 improves human readability but worsens acceptance metrics beyond the allowed
guardrails, do not promote it without a narrower follow-up plan.

## Stop Criteria

Stop the experiment early if any run shows one of these:

- `failed_checks` regresses badly relative to baseline;
- `document_map_present = false`;
- `document_topology_projection_status != "built"`;
- severe chapter-boundary regression in human review;
- evidence that a config change was not actually applied or cache state is
  inconsistent.

## Deliverables

At the end of the bounded experiment, produce one summary note with:

1. baseline run id and commit;
2. experiment run ids and exact env overrides;
3. machine-comparison table;
4. human-scorecard table;
5. recommended winning setting set, or explicit `no change` outcome;
6. whether the winning set should be promoted into a registry-wired benchmark
   profile or kept as ad-hoc research only.

## Implementation Notes For Start

The work can start immediately with no code changes if executed via env-var
overrides.

If later you want persistent run profiles for these settings, that is a separate
implementation task because `RunProfile` in `src/docxaicorrector/validation/profiles.py`
does not currently expose the tested structure settings directly.
