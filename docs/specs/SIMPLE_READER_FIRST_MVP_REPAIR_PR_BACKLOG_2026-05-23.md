# Simple Reader-First MVP Repair PR Backlog

Date: 2026-05-23
Status: Proposed implementation backlog for the next developer agent

Source specs and evidence:

- `docs/specs/SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md`
- `docs/specs/STRUCTURE_RECOGNITION_PR_BACKLOG_2026-05-21.md`
- Latest comparison-only run:
  `tests/artifacts/real_document_pipeline/runs/20260523T112909Z_970_Rethinking-money-chapter-region-pages-10-11-and-156-217/`
- Latest cleanup report:
  `.run/ui_results/20260523_143242_Rethinking-money-chapter-region-pages-10-11-and-156-217.reader_cleanup_report.json`

## Purpose

Convert the latest Simple Reader-First MVP findings into a small, ordered PR
backlog that preserves the agreed AI-first cleanup architecture.

The current MVP run proved that the pipeline can produce reviewable raw and
cleaned artifacts, and that cleanup improves readability. It also exposed the
next bottleneck: most remaining defects were not cleaned because the AI cleanup
contract failed on three of four chunks, primarily due to missing required
operation fields.

This backlog is not a request to make the comparison-only run green by adding
document-specific deterministic fixes. It is a request to make the AI cleanup
contract more reliable, then improve bounded AI operations and verifier-guided
repair.

## User-Facing Summary

The MVP works as a draft-quality comparison tool: it creates output and makes
the text more readable. It is not yet final-quality because many page headers,
page numbers, fused headings, and paragraph breaks remain.

The main reason is practical, not architectural: cleanup only fully ran on one
chunk out of four. The next work should make the AI cleanup response valid and
repairable, then rerun the same comparison-only profile.

## Non-Negotiable Architecture Rules

- Keep cleanup AI-first.
- Do not add Lietaer-specific regexes, phrase lists, heading literals, or page
  header strings as cleanup logic.
- Do not expand the shared page-furniture phrase library for this document.
- Do not use deterministic Markdown rewrites to split headings, merge
  paragraphs, or remove document-specific running headers.
- Do not tune Stage 1, Stage 2, topology, or structure-recognition windows for
  these reader-cleanup defects.
- Do not tighten or relax acceptance thresholds to make the comparison-only run
  look better.
- Keep code responsible for IDs, hashes, schema validation, exact-match
  application, protected-block rules, safety budgets, and reporting.
- Keep AI responsible for document-specific judgement: what is page furniture,
  what heading boundary is intended, and whether adjacent blocks are one broken
  paragraph.

## Latest Evidence To Preserve

Latest comparison-only run:

- `run_id`: `20260523T112909Z_970_Rethinking-money-chapter-region-pages-10-11-and-156-217`
- `validation_run_type`: `comparison_only`
- `acceptance_contract_active`: `False`
- pipeline result: succeeded
- cleanup stage: completed
- cleanup changed output: true
- cleanup chunks: 4
- failed cleanup chunks: 3
- proposed cleanup operations: 13
- accepted cleanup operations: 8
- ignored cleanup operations: 5
- verifier verdict: `cleaned_better`
- cleaned audit verdict: `improved_but_has_remaining_issues`
- raw score: 3.0
- cleaned score: 5.0
- remaining reader-visible issues: 36
- high severity issues: 31

Main remaining issue categories:

- `heading_fused_with_body`: 24
- `fragmented_paragraph`: 6
- `page_furniture_inline`: 6

Primary contract failure:

- `reader_cleanup_operation_missing_required_field:...:evidence_before`
  in chunks 1, 3, and 4.

## Recommended PR Order

### PR-A: Cleanup Schema Repair Retry

#### Goal

Make cleanup chunks recover from simple AI schema mistakes instead of becoming
no-op for a large part of the document.

#### Why First

The latest run cleaned only one of four chunks. Until invalid AI cleanup JSON can
be repaired, prompt and operation improvements will affect only part of the
document.

#### Required Work

1. Harden the cleanup system prompt so every operation must include all required
   fields:
   - `operation`
   - `id`
   - `text_hash`
   - `reason`
   - `confidence`
   - `evidence_before`
   - `expected_after_preview`
   - `safety_note`
2. Add a single schema-repair retry for cleanup chunk responses that are valid
   JSON but fail operation schema validation.
3. The repair prompt must ask the model to return only corrected JSON
   `cleanup_operations` and `warnings`.
4. The repair prompt must not allow rewritten Markdown or new operation types.
5. Advisory mode behavior:
   - original invalid response -> one repair retry;
   - valid repaired response -> continue normal validation/application;
   - invalid repaired response -> keep chunk unchanged and report warning.
6. Strict mode behavior:
   - preserve the existing fail-closed semantics; if repair still fails, fail
     cleanup while preserving base artifacts according to existing policy.
7. Add report fields or warnings that distinguish:
   - original schema failure;
   - repair attempted;
   - repair succeeded;
   - repair failed.

#### Suggested Files

- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/test_reader_cleanup_mvp.py`

#### Tests Required

- invalid operation missing `evidence_before` triggers exactly one repair retry;
- repaired valid operation is accepted and applied;
- repaired invalid operation leaves chunk unchanged in advisory mode;
- repair prompt forbids full rewritten Markdown;
- report includes repair attempt/success/failure evidence;
- existing ambiguous inline-noise safety tests still pass.

#### Validation

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
```

After focused tests, rerun the same comparison-only profile only if the unit
slice passes:

```bash
export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-chapter-region-core
export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-simple-reader-cleanup-comparison-only
bash scripts/run-real-document-validation.sh
```

Expected improvement: fewer failed cleanup chunks. Do not require acceptance to
pass.

### PR-B: Heading Boundary Operation Reliability

#### Goal

Improve AI cleanup's ability to split fused headings from body text without
adding deterministic heading rewrites.

#### Why Second

The largest remaining category is `heading_fused_with_body`. The latest report
also shows ignored `normalize_heading_boundary` operations because the model did
not provide exact enough parts.

#### Required Work

1. Add document-agnostic examples to the cleanup prompt for fused heading/body
   cases:
   - uppercase heading followed by prose;
   - chapter heading followed by epigraph;
   - section heading followed by first sentence;
   - part title followed by introductory paragraph.
2. Require the model to provide exact `heading_substring` and exact
   `body_substring` from the original block.
3. Tell the model that `body_substring` must cover the full semantic body portion
   it expects to remain after the heading, not just the first few words.
4. If prompt-only still produces `heading_boundary_unaccounted_text`, consider a
   bounded operation-contract refinement:
   - allow `normalize_heading_boundary` with a unique exact heading prefix;
   - code preserves the entire remaining text as body;
   - no words may be changed, dropped, or reordered.
5. This refinement is allowed only if it is implemented as exact-match
   application of an AI-selected boundary, not as deterministic heading
   detection.

#### Suggested Files

- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/test_reader_cleanup_mvp.py`

#### Tests Required

- fused uppercase heading/body is normalized when exact substrings are provided;
- operation is rejected when heading substring is ambiguous;
- operation is rejected when body text would be lost;
- optional prefix mode preserves the full remainder exactly;
- no operation creates new heading text that was not already present.

#### Validation

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
```

Expected improvement: fewer `heading_fused_with_body` issues after rerun.

### PR-C: Inline Page Furniture Application Hardening

#### Goal

Improve safe application of AI-proposed `remove_inline_noise` operations for
page furniture glued inside or at the start of paragraphs.

#### Why Third

The model already identified page furniture patterns, and some operations were
accepted. Remaining problems are mostly exactness/safety/application issues.

#### Required Work

1. Keep document-specific running headers inside the AI global cleanup plan and
   cleanup report only.
2. Do not promote run-specific phrases into shared deterministic code.
3. Accept `remove_inline_noise` only when:
   - the block ID and hash match;
   - the noise substring is exact and unique in that block;
   - the remaining block keeps semantic text;
   - deletion does not produce malformed spacing or empty semantic content;
   - the operation reason and evidence are consistent with page furniture,
     page-number island, blank-page marker, or running header residue.
4. Improve the model prompt to provide the full exact noise substring including
   surrounding spaces when needed.
5. Improve ignored-operation reporting so a developer can distinguish:
   - non-exact substring;
   - ambiguous repeated substring;
   - semantic deletion risk;
   - reason/kind mismatch.

#### Suggested Files

- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/test_reader_cleanup_mvp.py`

#### Tests Required

- prefix page furniture removal preserves prose;
- middle-of-paragraph page furniture removal preserves prose;
- ambiguous repeated substring is rejected;
- semantic phrase that merely resembles a header is rejected;
- report records ignored reason precisely.

#### Validation

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
```

Expected improvement: fewer `page_furniture_inline` issues after rerun.

### PR-D: Verifier-Guided Anchor Repair Pass

#### Goal

Use verifier/pre-audit findings to drive a second bounded AI cleanup pass over
only the remaining problem anchors.

#### Why Fourth

After basic cleanup is reliable, a second pass should focus on the exact places
still reported as reader-visible defects instead of reprocessing the whole book.

#### Required Work

1. After the first cleanup pass and verifier/pre-audit, collect top remaining
   anchors by category:
   - `heading_fused_with_body`
   - `page_furniture_inline`
   - `fragmented_paragraph`
2. Build small anchor windows around affected blocks.
3. Ask the cleanup model for the same bounded operations only.
4. Preserve all existing ID/hash/exact-match safety checks.
5. Keep the pass optional and advisory for MVP.
6. Report first-pass vs anchor-repair-pass operation counts separately.

#### Suggested Files

- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` only if
  verifier artifacts need additional machine-readable anchor grouping
- `tests/test_reader_cleanup_mvp.py`
- `tests/test_real_document_pipeline_validation.py`

#### Tests Required

- anchor pass receives only selected windows, not the full document;
- anchor pass cannot edit blocks outside its editable ID set;
- invalid anchor-pass response is no-op in advisory mode;
- report separates first-pass and anchor-pass stats;
- verifier/pre-audit anchors with equal category counts are preserved by
  identity, not category count alone.

#### Validation

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'
```

Expected improvement: lower remaining issue count with no false deletions.

### PR-E: User-Facing MVP Status Report

#### Goal

Make the comparison-only result understandable to a non-developer user.

#### Why Fifth

The current artifacts contain useful data, but the user-facing interpretation is
too easy to misread as either a failure or a final acceptance result.

#### Required Work

1. Add or improve summary fields that clearly separate:
   - pipeline success;
   - cleanup improvement;
   - acceptance diagnostic status;
   - remaining reader-visible risk.
2. Include positive safety signals:
   - no verifier-reported false deletions;
   - no verifier-reported readability regressions.
3. Include blocker grouping:
   - schema/operation contract failures;
   - remaining reader-visible cleanup defects;
   - mapping/quality-gate diagnostics.
4. Prefer concise Russian user summaries for this workflow when the source run
   profile is used by Russian-speaking operators.

#### Suggested Files

- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- `tests/test_real_document_pipeline_validation.py`

#### Tests Required

- comparison-only summary states that acceptance failure is diagnostic;
- summary includes cleanup score delta;
- summary includes remaining issue counts and top categories;
- summary includes false-deletion/regression status;
- summary distinguishes cleanup defects from unmapped source/target diagnostics.

#### Validation

```bash
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'
```

Expected improvement: users can understand whether the artifact is a readable
draft, acceptance-ready output, or a failed pipeline.

## Final Validation Strategy

For each PR, run focused tests first. Before any final verification, check the
dirty worktree:

```bash
git status --porcelain
```

For real-document evidence, use the same comparison-only profile:

```bash
export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-chapter-region-core
export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-simple-reader-cleanup-comparison-only
bash scripts/run-real-document-validation.sh
```

The proof target is not `acceptance_passed=True`. The proof target is:

- cleanup chunk failures decrease;
- accepted bounded operations increase for valid cases;
- ignored operations remain explainable;
- reader quality score improves or stays improved;
- remaining reader-visible issues decrease;
- no false deletions or readability regressions appear;
- raw and cleaned artifacts remain reviewable.

## Prompt For Developer Agent

Use this prompt to start implementation in a fresh coding-agent session.

```text
You are working in DocxAICorrector. Implement the next Simple Reader-First MVP
repair slice according to:

- docs/specs/SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md
- docs/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md
- AGENTS.md
- .github/copilot-instructions.md

Start with PR-A: Cleanup Schema Repair Retry.

Context from the latest comparison-only run:

- run_id: 20260523T112909Z_970_Rethinking-money-chapter-region-pages-10-11-and-156-217
- profile: lietaer-pdf-chapter-region-core
- run profile: ui-parity-translate-simple-reader-cleanup-comparison-only
- cleanup chunks: 4
- failed cleanup chunks: 3
- failure reason: reader_cleanup_operation_missing_required_field:...:evidence_before
- verifier verdict: cleaned_better
- remaining issues: heading_fused_with_body, fragmented_paragraph, page_furniture_inline

Architecture constraints:

- Keep cleanup AI-first.
- Do not add document-specific regexes, phrase lists, heading literals, or
  running-header strings as code cleanup logic.
- Do not expand the shared page-furniture phrase library for this document.
- Do not tune structure recognition, topology, Stage 1, Stage 2, chunk windows,
  or acceptance thresholds for this slice.
- Code may validate schema, retry schema repair, apply exact operations, enforce
  safety, and report failures.
- AI owns document-specific judgement through bounded cleanup operations.

Implementation target for PR-A:

1. Find the cleanup response parsing/schema validation path in
   src/docxaicorrector/reader_cleanup_mvp/service.py.
2. Add prompt hardening so every operation must include all required fields,
   especially evidence_before.
3. Add one schema-repair retry when a cleanup chunk response is JSON but fails
   operation schema validation.
4. The repair request must ask for corrected JSON only, with the same allowed
   top-level shape: cleanup_operations and warnings.
5. If repair succeeds, run the repaired operations through the same validation
   and application path as normal.
6. If repair fails in advisory mode, keep the chunk unchanged and report a clear
   warning.
7. Preserve strict-mode fail-closed behavior.
8. Add focused tests in tests/test_reader_cleanup_mvp.py.

Validation:

- Before final verification, run git status --porcelain and note if the worktree
  is dirty.
- Run: bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
- If that passes and runtime is available, rerun the comparison-only real
  document profile using the canonical WSL script path.
- Do not report acceptance_passed=False as a pipeline failure for comparison-only
  runs.

Deliverable:

- Small focused code change.
- Tests for repair success and repair failure/no-op behavior.
- Final summary stating whether failed cleanup chunks decreased on the real run
  if the real run was executed.
```

## Stop Conditions

Stop and update this backlog instead of coding further if any of these become
true:

- PR-A requires changing the cleanup operation contract beyond schema repair;
- a proposed fix needs document-specific deterministic cleanup logic;
- a change would modify structure-recognition authority boundaries;
- real-document evidence shows false deletions or readability regressions;
- comparison-only artifacts stop being produced.
