# Output Acceptance Criteria Analysis Prompt

Date: 2026-05-21
Status: Prompt document for bounded deep review

## Purpose

Этот документ задаёт промпт для полного анализа текущих block-level rejection и
output-level acceptance критериев в pipeline, с явной целью решить:

```text
какие критерии нужно оставить как hard blockers,
какие перевести в advisory/warn,
какие ослабить порогами или scope,
а от каких вообще отказаться.
```

Документ нужен как отдельная исследовательская задача. Его можно дать другому
 агенту-разработчику или использовать как чек-лист для ручного ревью.

## Why This Review Exists

Последний full-book run с `chunk_size = 30000` не упал из-за технической поломки
pipeline, а был остановлен block-level rejection по
`english_residual_output`.

Relevant evidence:

- `src/docxaicorrector/pipeline/output_validation.py:234-245`
- `src/docxaicorrector/pipeline/output_validation.py:266-281`
- `src/docxaicorrector/pipeline/block_failures.py:239-245`
- `tests/test_document_pipeline_output_validation.py:1458-1500`
- `tests/artifacts/real_document_pipeline/lietaer_pdf_full_benchmark_report.json:1965-1976`

This suggests the repository may currently be over-indexed on narrow hard-fail
criteria that are valid as detectors but not necessarily valid as full-book run
blockers.

## Prompt

Use the prompt below as-is or with minimal edits.

```text
Task: perform a full review of the current output-acceptance and block-rejection
criteria in the document pipeline, with the explicit goal of deciding which
criteria should remain hard blockers, which should become advisory-only, which
need thresholds/scope narrowing, and which should be removed entirely.

Repository:
- D:\www\Projects\2025\DocxAICorrector

Primary question:
- Are the current output acceptance criteria preventing real failures, or are they
  increasingly acting as over-strict gates that block useful full-book comparison
  runs and hide the actual product signal?

You must analyze both code and tests. Do not stop at one observed failure.

## Required analysis scope

Review these code surfaces first:

1. `src/docxaicorrector/pipeline/output_validation.py`
   - especially `ProcessedBlockStatus`
   - `classify_processed_block(...)`
   - `has_unexplained_english_residuals(...)`
   - TOC validation helpers
   - bullet/heading-only/toc concat detectors

2. `src/docxaicorrector/pipeline/block_failures.py`
   - how each classification is turned into hard failure

3. `src/docxaicorrector/pipeline/_pipeline.py`
   - where these failures stop processing

4. `src/docxaicorrector/pipeline/late_phases.py`
   - translation quality reports and late-phase gates

5. `src/docxaicorrector/validation/structural.py`
   - acceptance/provenance plumbing for structural and translation-quality checks

6. `tests/test_document_pipeline_output_validation.py`
   - current test contract for block rejection behavior

7. `tests/test_real_document_validation_corpus.py`
   - acceptance-layer expectations for TOC/body concat and related metrics

8. latest run artifacts for concrete evidence:
   - `tests/artifacts/real_document_pipeline/lietaer_pdf_full_benchmark_report.json`
   - `tests/artifacts/real_document_pipeline/lietaer_pdf_full_benchmark_latest.json`

## Required criteria inventory

Build a complete inventory of all current block-level and output-level criteria
that can cause a run to fail, degrade, warn, or reject a block.

At minimum include:

- `empty`
- `heading_only_output`
- `bullet_heading_output`
- `toc_body_concat`
- `english_residual_output`
- late translation quality gate reasons
- any structural acceptance checks that are logically acting like output gates

For each criterion, produce a table row with:

1. criterion name
2. code location
3. current trigger logic
4. current effect
   - block reject
   - hard run fail
   - advisory only
   - report only
5. original product intent
6. likely true-positive value
7. likely false-positive risk on full books
8. interaction with PDF books / TOC / front matter / back matter
9. interaction with larger blocks
10. recommendation:
    - keep hard blocker
    - downgrade to advisory
    - threshold it
    - scope it to specific structural roles
    - move to end-of-run report only
    - remove entirely

## Specific questions you must answer

1. Is `english_residual_output` currently too strict for full-book benchmark runs?
   - It currently appears to fail on any mixed Cyrillic+English residual hit.
   - Determine whether this should remain a hard block, become thresholded, or be
     moved to advisory/report-only for benchmark/full-book profiles.

2. Are `heading_only_output` and `toc_body_concat` genuine hard blockers, or are
   they also partially over-broad in their current implementation?

3. Is there a mismatch between:
   - detectors that are useful for observability,
   - and gates that are too expensive as immediate fail-fast behavior?

4. Which criteria should be profile-sensitive?
   - e.g. stricter for small targeted tests,
   - softer for benchmark-only full-book runs,
   - possibly different for translate vs edit vs audiobook.

5. Which criteria should move from binary fail to thresholded fail?
   Examples of thresholding dimensions:
   - count of offending lines per block
   - count of offending blocks per run
   - ratio of problematic text
   - only fail if a protected structural role is affected

6. Which criteria should stop being fail-fast and instead allow the run to finish
   while emitting report samples for later inspection?

7. Which current tests encode policy choices rather than fundamental correctness,
   and therefore would need rewriting if policy is relaxed?

## Evidence standard

Do not answer abstractly. For every recommendation, cite:

- code location
- one or more tests
- one or more real-artifact/report examples when available

If you recommend weakening or removing a criterion, explicitly explain:

- what real defect would become less protected,
- what replacement visibility/reporting would remain,
- why the tradeoff is acceptable.

## Required deliverable structure

Return a single analysis with these sections:

1. Executive conclusion
   - Is there real overengineering here?
   - Which 2-3 criteria are the strongest candidates for downgrade/removal?

2. Criteria inventory table

3. Findings by severity
   - most harmful over-strict gates first

4. Recommendation package
   - minimal package: smallest safe relaxations
   - medium package: pragmatic benchmark-friendly policy
   - aggressive package: detector-first / fail-late policy

5. Test impact
   - which tests would need updating and why

6. Suggested implementation order
   - one small PR at a time

## Important constraints

- Do not propose broad prompt redesign in this task.
- Do not propose new structure-recognition architecture in this task.
- Keep focus on acceptance/gating policy.
- Distinguish clearly between:
  - detector usefulness,
  - hard-fail usefulness,
  - benchmark/full-book usability.

## Success criterion for this review

The review is successful only if it gives a concrete answer to this question:

"Which current output criteria are giving us valuable protection, and which are
mostly blocking useful experiments and masking the actual product signal?"
```

## Notes For Whoever Runs This Prompt

1. The target is analysis first, not immediate code changes.
2. The most likely first candidate for relaxation is
   `english_residual_output`, but the task must still review the full criterion
   set and not tunnel on one case only.
3. The most useful end state is probably a distinction between:
   - hard correctness blockers,
   - benchmark-safe advisory detectors,
   - report-only observability signals.
