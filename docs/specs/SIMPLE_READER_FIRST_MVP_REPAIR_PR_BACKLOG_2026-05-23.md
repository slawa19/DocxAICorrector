# Simple Reader-First MVP Repair PR Backlog

Date: 2026-05-23
Status: Proposed implementation backlog for the next developer agent

Source specs and evidence:

- `docs/specs/SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md`
- `docs/specs/STRUCTURE_RECOGNITION_PR_BACKLOG_2026-05-21.md`
- Latest comparison-only run:
   `tests/artifacts/real_document_pipeline/runs/20260524T085558Z_976_Rethinking-money-chapter-region-pages-10-11-and-156-217/`
- Latest cleanup report:
   `.run/ui_results/20260524_120055_Rethinking-money-chapter-region-pages-10-11-and-156-217.reader_cleanup_report.json`

## Purpose

Convert the latest Simple Reader-First MVP findings into a small, ordered PR
backlog that preserves the agreed AI-first cleanup architecture.

The current MVP run proved that the pipeline can produce reviewable raw and
cleaned artifacts, and that cleanup improves readability. The cleanup contract
now runs without failed chunks, so the next bottleneck is product-visible output
quality: page furniture still appears inside prose, headings are still fused
with body text, and fragmented paragraphs remain.

This backlog is not a request to make the comparison-only run green by adding
document-specific deterministic fixes. It is a request to improve bounded AI
cleanup operations on the remaining reader-visible defects while preserving the
code-owned safety and verifier evidence contracts.

## User-Facing Summary

The MVP works as a draft-quality comparison tool: it creates output and makes
the text more readable. It is not yet final-quality because many page headers,
page numbers, fused headings, and paragraph breaks remain.

The main reason is now product-quality, not validator architecture: cleanup
successfully runs, but the remaining reader-visible defects are still too common
for final output. The next work should target PR-H and rerun the same
comparison-only profile.

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
- Validation must remain observational: it may run profiles, read artifacts,
   score results, build evidence, and report findings, but it must not implement
   production repair behavior or mutate final Markdown/DOCX artifacts.
- Keep code responsible for IDs, hashes, schema validation, exact-match
  application, protected-block rules, safety budgets, and reporting.
- Keep AI responsible for document-specific judgement: what is page furniture,
  what heading boundary is intended, and whether adjacent blocks are one broken
  paragraph.

## Ownership Map

Use this map to decide where a defect belongs before writing code:

| Defect | Owning layer | Allowed mechanism | Not allowed |
| --- | --- | --- | --- |
| Old page numbers, running headers, footers | `reader_cleanup_mvp` | AI-selected bounded operations: `delete_block` for standalone furniture, `remove_inline_noise` for exact inline furniture | Global number deletion, document-specific phrases, regexes for this book |
| Heading fused with body text | `reader_cleanup_mvp` | `normalize_heading_boundary`, `split_block`, or composed exact operations after removing page furniture | Deterministic heading detection, invented heading/body text, unaccounted source text |
| TOC page numbers / generated TOC fidelity | not a target for this reader-first repair backlog | Delete or ignore TOC page numbers when they harm reader output; optionally drop TOC as text in an explicit reader profile | Rebuilding a correct translated TOC, preserving original page numbers, or treating TOC reconstruction as acceptance-critical |
| Footnote markers/footnote blocks | `reader_cleanup_mvp` only after explicit MVP policy | `delete_block` or `remove_inline_noise` with exact evidence and a `drop_footnotes`/equivalent policy | Silent deletion of semantic numbers, numbered lists, citations needed by the selected mode |
| Bold, italic, emphasis, heading/subheading styles, list styles | formatting transfer / intermediate model / DOCX writer | Preserve source run-level formatting and structural style evidence through final DOCX | Guessing styles from plain cleanup text alone or mixing this into reader-cleanup deletion work |
| Images from PDF-derived documents | PDF import / image extraction / main pipeline asset handoff / DOCX reinsertion | Locate where image assets disappear in the main pipeline; restore asset placeholders/reinsertion in a dedicated image PR | Restoring images through reader-cleanup prompts, replacing images with descriptions, or hiding image loss inside formatting work |
| Verifier blind spots | verifier/reporting layer | Add checks only after the output behavior is fixed or as a small supporting change | Treating verifier prompt tuning as the primary fix for bad output |
| Validation applying cleanup or rewriting DOCX | runtime pipeline / reader cleanup orchestration | Move repair execution into the main pipeline and let validation consume produced artifacts | Validation scripts applying AI cleanup, overwriting cleaned Markdown, or rebuilding DOCX |

## Current Visual MVP Roadmap

The post-PR-F/PR-G visual review changed the next priorities. Correct TOC
reconstruction is explicitly not a goal for this backlog. In translated output,
source page numbers become stale and do not need to be preserved; TOC page
numbers may be removed, and TOC itself may be dropped by an explicit reader
profile if it harms the reading experience.

The visible failures to address are old page furniture, running headers/footers,
page numbers glued into prose, heading/body fusion, fragmented paragraphs,
basic list readability, source formatting preservation (bold, italic, emphasis,
heading/subheading styles, list styles), and missing images.

Work must be split by owner:

- **PR-G: Validator Boundary Refactor**
   - Scope: validation architecture and reader-cleanup runtime orchestration.
   - Remove validation-owned anchor repair execution and artifact mutation.
   - Ensure any second cleanup/anchor repair pass runs inside the main pipeline
      or is not run at all; validation may only record verifier anchors as
      evidence.
   - Must happen before PR-H/PR-I/PR-J proof work, because visual/formatting
      evidence is unreliable while validation can rewrite DOCX through a
      simplified path.
- **PR-H: Reader Cleanup Visual Blockers**
   - Scope: `reader_cleanup_mvp` only.
   - Fix old page numbers, running headers/footers, page-furniture glued into
      prose, heading/body fusion, fragmented paragraphs, and reader-visible list
      marker cleanup.
   - TOC reconstruction is out of scope. Only remove/ignore TOC page numbers or
      drop TOC as ordinary text when an explicit reader profile allows it.
   - Do not touch image reinsertion, bold/italic/style preservation, or verifier
      tuning except as small supporting evidence.
- **PR-I: Formatting Preservation**
   - Scope: formatting transfer / intermediate representation / DOCX writer.
   - Preserve bold, italic, emphasis/highlight where source evidence exists.
   - Preserve heading and subheading style levels, plus list styling/numbering
      when source evidence and translated structure can be mapped safely.
   - Do not infer formatting purely from plain cleanup text, and do not treat
      stale TOC page numbers as formatting to preserve.
- **PR-J: Image Handoff/Reinsertion**
   - Scope: PDF import, image extraction, artifact handoff, DOCX reinsertion.
   - If images are expected to flow through the main pipeline, dedicate this PR
      to finding why PDF-origin images disappear during conversion/handoff.
   - Find where `image_count`, image placeholders, processed image assets, or
      output inline shapes becomes zero and fix that layer or document the
      upstream blocker.
   - Do not attempt image recovery in reader cleanup.

Future implementation slices must name exactly one of these scopes unless this
backlog is updated first. If a slice discovers a defect belongs to a different
owner, it must record the evidence and stop instead of broadening the PR.

## Latest Evidence To Preserve

Latest comparison-only run:

- `run_id`: `20260524T085558Z_976_Rethinking-money-chapter-region-pages-10-11-and-156-217`
- `validation_run_type`: `comparison_only`
- `acceptance_contract_active`: `False`
- pipeline result: succeeded; the previous post-processing/finalization hang did
   not reproduce
- cleanup stage: completed
- cleanup changed output: true
- cleanup chunks: 4
- failed cleanup chunks: 0
- proposed cleanup operations: 67
- accepted cleanup operations: 36
- ignored cleanup operations: 31
- accepted delete blocks: 3
- deleted non-whitespace chars: 71 (`deleted_char_ratio=0.000713`)
- verifier verdict: `cleaned_better`
- cleaned audit verdict: `improved_but_has_remaining_issues`
- raw score: 3.0
- cleaned score: 5.0
- remaining reader-visible issues: 26
- high severity issues: 22
- output DOCX openable: true
- formatting diagnostics: failed diagnostic threshold; `mapped_count=282`,
   `unmapped_source_count=30`, `unmapped_target_count=31`

Main remaining issue categories:

- `heading_fused_with_body`: 14
- `page_furniture_inline`: 7
- `fragmented_paragraph`: 5

Current primary product blockers:

- page numbers / running headers glued into normal prose;
- paragraphs still fused to headings or subheadings;
- remaining fragmented paragraphs around page/caption/list boundaries;
- formatting preservation is not solved yet: bold, italic, emphasis/highlight,
   heading/subheading styles, and list styles need a later formatting PR;
- images are not solved here and need a dedicated image handoff/reinsertion PR.

## Historical PR Order (PR-A Through PR-G)

PR-A through PR-G are historical context for how the backlog reached the current
state. Do not start a new implementation from these completed/superseded slices.
The next active implementation slice is PR-H from the Current Visual MVP Roadmap.

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

## Post-PR-E Real-Run Evidence

PR-A through PR-E have now been implemented and validated on the same
comparison-only chapter-region profile. The latest real-document evidence is:

- `run_id`: `20260523T134507Z_967_Rethinking-money-chapter-region-pages-10-11-and-156-217`
- `validation_run_type`: `comparison_only`
- pipeline result: `succeeded`
- acceptance result: `failed`, diagnostic-only for this profile
- verifier verdict: `cleaned_better`
- cleaned audit verdict: `improved_but_has_remaining_issues`
- raw score: 3.0
- cleaned score: 5.0
- remaining reader-visible issues: 10
- high severity issues: 6
- MVP status artifact:
   `tests/artifacts/real_document_pipeline/runs/20260523T134507Z_967_Rethinking-money-chapter-region-pages-10-11-and-156-217/lietaer_pdf_chapter_region_reader_mvp_status.md`
- cleaned Markdown artifact:
   `.run/ui_results/20260523_164936_Rethinking-money-chapter-region-pages-10-11-and-156-217.result.md`
- cleanup report:
   `.run/ui_results/20260523_164936_Rethinking-money-chapter-region-pages-10-11-and-156-217.reader_cleanup_report.json`

The current reader-facing quality is readable draft, not final quality. The
document is materially easier to read than the raw output, and the verifier did
not report false deletions or readability regressions. Remaining defects are
visible but localized.

Current blocker groups from the PR-E status report:

- cleanup contract: `cleanup_chunk_failures=2`
- reader-visible cleanup defects:
   - `heading_fused_with_body=5`
   - `page_furniture_inline=3`
   - `fragmented_paragraph=2`
- mapping/quality-gate diagnostics:
   - `translation_quality_status=warn`
   - `translation_quality_gate_reasons=unmapped_source_paragraphs_above_advisory_threshold`
   - `acceptance_diagnostic_checks=formatting_diagnostics_threshold,unmapped_source_threshold,unmapped_target_threshold`

Reader-visible examples from the latest cleaned Markdown:

- fused TOC heading:
   `СОДЕРЖАНИЕ Предисловие ix Введение: от дефицита к процветанию за одно поколение 1`
- fragmented paragraph after an image caption:
   `деньги по-другому и при этом быть уверенными, что их дети ходят в школу», — вспоминает Лернер. Множество инициатив...`
- inline page furniture before a heading:
   `11 ФУРЕАЙ КИППУ`
- fused heading/body:
   `ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ. Авиационный бизнес...`
- page number plus running header fused into body:
   `200 ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ Наконец-то признана необходимость...`

## Historical PR-F Repair Slice (Completed/Superseded)

This section is retained as implementation history. It is not the current next
slice. The current next slice is PR-H: Reader Cleanup Visual Blockers.

### PR-F: Anchor Repair Reliability and Remaining Reader Defects

#### Goal

Reduce the remaining reader-visible defects without violating the AI-first
cleanup contract. The first target is to eliminate anchor-repair schema/chunk
failures; the second target is to improve the same anchor pass on the three
remaining defect families: fused headings, inline page furniture, and fragmented
paragraphs.

#### Why This Can Be One Iteration

These improvements touch the same bounded cleanup surface:

- anchor-repair prompt and schema-repair prompt;
- cleanup operation contract guidance;
- verifier/pre-audit anchor payload shaping;
- tests around `run_reader_cleanup_anchor_repair` and comparison-only verifier
   integration.

Combining them is optimal if the implementation remains limited to prompt,
schema-repair, anchor payload, exact-match validation, and tests. It is not
optimal if it requires a new cleanup operation type, document-specific detection,
or live app runtime wiring. In that case, split the work and update this backlog
before coding further.

#### Required Work

1. Fix anchor-repair schema reliability:
    - harden the anchor-repair request instructions so every proposed operation
       includes all required audit fields;
    - harden schema-repair instructions so the model only adds or corrects
       missing operation fields and does not rewrite Markdown;
    - preserve advisory behavior: failed anchor chunks are reported and leave
       selected text unchanged;
    - preserve strict validation and exact-match application.
2. Improve fused heading repair guidance:
    - add document-agnostic examples for uppercase heading + body prose;
    - include examples with leading page number/running header plus heading/body;
    - prefer composed AI operations where needed, for example
       `remove_inline_noise` followed by `normalize_heading_boundary` on the same
       block when both are justified by exact evidence;
    - do not add deterministic heading detection or heading literals.
3. Improve inline page-furniture guidance:
    - clarify that a leading page/footnote number before a heading can be a
       candidate only when the model provides exact evidence and safe preview;
    - keep code-owned safety strict: exact unique substring, semantic remainder,
       ID/hash match, and no broad numeric-prefix rule.
4. Improve fragmented paragraph guidance:
    - pass enough neighboring context in anchor windows for the model to decide
       whether a fragment is a page/caption split;
    - use existing bounded operations such as `join_fragmented_paragraph` when
       the required exact evidence is present;
    - do not add a duplicate-removal operation in this PR unless the existing
       operation contract already supports it safely. If a new operation type is
       required, write a separate contract update first.
5. Improve developer-facing diagnostics:
    - make anchor chunk failure warnings easy to distinguish from first-pass
       cleanup failures;
    - include accepted/ignored operation counts for the anchor pass;
    - keep the PR-E user status report unchanged except for naturally improved
       numbers from the same fields.

#### Suggested Files

- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- `tests/test_reader_cleanup_mvp.py`
- `tests/test_real_document_pipeline_validation.py`

Do not change `src/docxaicorrector/pipeline/late_phases.py` for this PR unless
the task is explicitly expanded to live app runtime wiring. The next repair
target is the comparison-only validation path.

#### Tests Required

- anchor response missing `evidence_before` is repaired and applied when the
   corrected operation is valid;
- anchor response missing `expected_after_preview` is repaired and applied when
   safe;
- unrepaired invalid anchor response leaves the selected text unchanged in
   advisory mode and reports the failure;
- composed page-furniture plus heading-boundary repair on one block preserves
   all semantic body text exactly;
- numeric prefix that is semantic content is rejected, not deleted;
- fragmented paragraph anchor receives enough neighbor context and applies only
   through an existing safe operation;
- comparison-only verifier loop still reruns after anchor repair and refreshes
   reader MVP status fields.

#### Validation

Run focused tests first:

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'
```

If the focused tests pass, rerun the same real-document comparison-only profile:

```bash
export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-chapter-region-core
export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-simple-reader-cleanup-comparison-only
bash scripts/run-real-document-validation.sh
```

Expected improvement:

- `cleanup_chunk_failures` decreases, ideally to 0;
- remaining reader-visible issue count decreases below 10;
- high severity count decreases below 6;
- no false deletions or readability regressions appear;
- status remains readable draft unless the verifier reports the cleaned artifact
   is actually clean;
- comparison-only acceptance may still be diagnostic failed because mapping and
   quality-gate diagnostics are separate from reader cleanup.

#### Stop Conditions

Stop and update this backlog instead of widening the PR if any of these become
true:

- fixing the fragmented paragraph requires a new cleanup operation type;
- the proposed fix needs Lietaer-specific literals or regexes;
- the proposed fix changes acceptance thresholds or structure-recognition
   behavior;
- the proposed fix changes live app runtime behavior in `late_phases.py`;
- real-document evidence reports possible false deletions or readability
   regressions.

## Architecture Review Findings Before Remaining Visual Work

The post-PR-F architecture review found that the comparison-only validator has
drifted beyond validation responsibility. It currently runs verifier review, then
uses verifier issues to execute `run_reader_cleanup_anchor_repair`, overwrites
the cleaned Markdown artifact, and rebuilds the cleaned DOCX through a simplified
Markdown-to-DOCX path. That makes validation a second repair pipeline instead of
an observer.

This must be fixed before PR-H/PR-I/PR-J, because remaining visual proof depends
on knowing whether the final DOCX came from the real runtime pipeline or from a
validation-only rewrite path.

Current concrete findings:

- validation-owned mutation: `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
   applies anchor repair and rewrites cleaned Markdown/DOCX instead of only
   reporting verifier anchors;
- DOCX parity risk: validation rebuilds post-anchor DOCX with
   `convert_markdown_to_docx_bytes(...)`, while live runtime cleanup uses the
   full rebuild path with source paragraph property preservation and image
   reinsertion hooks;
- composed-operation mismatch: cleanup prompts allow page-furniture removal plus
   heading/body normalization on the same block, but the parser currently ignores
   a second non-join operation for the same block;
- audit-contract drift: legacy `delete_blocks` responses can still bypass the
   full `cleanup_operations` audit fields required by the MVP contract;
- numeric-prefix safety gap: the inline-noise safety layer still accepts a broad
   number-plus-uppercase substring class, which is too close to the forbidden
   "delete any number before an uppercase phrase" shortcut;
- verifier taxonomy drift: `recommended_next_changes.change_type` accepts
   `cleanup_core` / `ai_operation_contract`, while the spec names
   `model_selection`, `operation_contract`, `safety_application`, and
   `deterministic_last_resort` as the stable categories;
- latest evidence caveat: the latest comparison-only evidence still says
   `cleaned_better`, but reports readability regressions, so it must not be used
   as success proof for PR-H until the boundary and contract issues are fixed.

### PR-G: Validator Boundary Refactor And Cleanup Contract Preflight

#### Goal

Restore the architecture boundary: validation evaluates and reports only; all
reader cleanup and anchor repair execution must happen in the main runtime
pipeline or not happen at all. While touching that boundary, fix the small
cleanup-contract mismatches that would otherwise make PR-H visual repair evidence
ambiguous.

#### Why Before PR-H / PR-I / PR-J

PR-H needs visual evidence from the actual pipeline output. PR-I and PR-J are
about formatting and image preservation. If validation can still rewrite cleaned
Markdown and rebuild DOCX by a simplified path, visual regressions can be caused
by the validator rather than by the production pipeline. That would make the next
formatting/image work chase the wrong layer.

#### Required Work

1. Remove validation-owned repair execution:
   - delete or disable the call from `_write_reader_verifier_artifacts(...)` to
      `_run_reader_cleanup_anchor_repair_validation_pass(...)`;
   - validation may still build and persist anchor targets as diagnostic evidence;
   - validation must not call cleanup models to mutate output artifacts;
   - validation must not overwrite cleaned Markdown, cleaned DOCX, or cleanup
      reports except to add validation/report metadata in run-scoped reports.
2. Decide the runtime home for anchor repair:
   - either move anchor repair orchestration into the main pipeline where the full
      DOCX rebuild path is available;
   - or leave anchor repair disabled as a future runtime feature and expose
      verifier anchors as backlog evidence only;
   - do not keep a validation-only repair path as an MVP shortcut.
3. Preserve verifier value without mutation:
   - write verifier evidence, review JSON/Markdown, and reader MVP status as
      before;
   - include `recommended_anchor_targets` or equivalent diagnostic fields in
      verifier/summary artifacts;
   - if anchor repair is not runtime-enabled yet, clearly report
      `anchor_repair_status=diagnostic_only_not_applied`.
4. Align cleanup operation parsing with the AI-first contract:
   - allow compatible composed operations on the same block when exact evidence
      supports them, especially `remove_inline_noise` followed by
      `normalize_heading_boundary`;
   - reject incompatible duplicate edits explicitly instead of silently ignoring
      them;
   - keep operation order deterministic and report accepted/ignored composed
      operations clearly.
5. Tighten audit and safety contracts before visual repair:
   - require full audit fields for new cleanup operations;
   - either deprecate legacy `delete_blocks` or convert it into fully audited
      `cleanup_operations` before application;
   - narrow the number-plus-uppercase inline-noise acceptance path so semantic
      numeric headings or numbered prose are rejected unless AI evidence is exact
      and the operation fits a document-agnostic safety rule.
6. Align verifier recommendation taxonomy with the spec:
   - support `prompt`, `model_selection`, `operation_contract`,
      `safety_application`, and `deterministic_last_resort`;
   - keep legacy values only as normalized compatibility input, not as the
      preferred output contract.

#### Suggested Files

- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- `src/docxaicorrector/pipeline/late_phases.py` only if anchor repair execution
   is moved into runtime in this PR
- `src/docxaicorrector/reader_cleanup_mvp/service.py`
- `tests/test_reader_cleanup_mvp.py`
- `tests/test_real_document_pipeline_validation.py`
- `docs/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md` only if
   the runtime-anchor decision needs a follow-up slice

#### Tests Required

- verifier run no longer mutates cleaned Markdown or cleaned DOCX artifacts;
- verifier artifacts still contain remaining issues, evidence anchors, and
   recommended anchor targets;
- comparison-only status distinguishes diagnostic anchor targets from applied
   cleanup;
- if runtime anchor repair is implemented, it uses the same DOCX rebuild path as
   normal reader cleanup and validation only observes its artifacts;
- composed same-block page-furniture removal plus heading-boundary normalization
   is accepted when exact and safe;
- incompatible duplicate operations on one block are rejected with an explicit
   ignored reason;
- legacy `delete_blocks` cannot bypass the required audit contract for new
   cleanup behavior;
- semantic numeric uppercase text is preserved when AI proposes it as inline
   noise;
- verifier recommendation change types match the spec taxonomy.

#### Validation

Run focused tests first:

```bash
bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'
```

If the focused tests pass, rerun the same comparison-only profile:

```bash
export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-chapter-region-core
export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-simple-reader-cleanup-comparison-only
bash scripts/run-real-document-validation.sh
```

Expected result:

- comparison-only run still completes and writes raw/cleaned/verifier/status
   artifacts;
- validation no longer applies anchor repair or rewrites primary output
   artifacts;
- verifier anchors are preserved as diagnostic evidence;
- if no runtime anchor repair is implemented yet, remaining issue counts may not
   improve, and that is acceptable for this PR;
- no false deletions or readability regressions are introduced by cleanup
   contract changes;
- downstream PR-H/PR-I/PR-J can trust that visual artifacts came from the real
   pipeline path.

#### Stop Conditions

Stop and update this backlog instead of widening the PR if any of these become
true:

- moving anchor repair into runtime requires a broad pipeline refactor beyond
   `late_phases.py` and `reader_cleanup_mvp`;
- preserving verifier anchors requires changing the verifier review JSON schema
   incompatibly with existing artifacts;
- fixing duplicate fragments requires a new cleanup operation type;
- the change needs document-specific literals, regexes, or page-header strings;
- comparison-only artifacts stop being produced.

#### PR-G Completion Report For Orchestrator

Result

- Completed: restored the validator boundary so validation is observational
   only; validator-owned anchor repair execution was removed; verifier output now
   records diagnostic-only anchor metadata and surfaces
   `anchor_repair_status=diagnostic_only_not_applied`; cleanup contract preflight
   was tightened for same-block composed operations, explicit duplicate rejection,
   legacy `delete_blocks` now requiring schema repair/full audit instead of
   code-generated audit fields, numeric-uppercase inline-noise safety, and
   verifier recommendation taxonomy normalization.
- Changed files:
   `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`,
   `src/docxaicorrector/reader_cleanup_mvp/service.py`,
   `tests/test_real_document_pipeline_validation.py`,
   `tests/test_reader_cleanup_mvp.py`.
- Checks:
   `git status --porcelain` confirmed a dirty worktree before final verification;
   `bash scripts/test.sh tests/test_reader_cleanup_mvp.py -q` passed
   (`49 passed`);
   `bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q -k 'reader_verifier or comparison_only'`
   passed (`19 passed`, `48 deselected`);
   touched files had no editor/type errors.
- Iterations: two implementation slices plus one real-document comparison-only
   rerun attempt.
- Risks: the requested comparison-only real-document rerun for
   `lietaer-pdf-chapter-region-core` with
   `ui-parity-translate-simple-reader-cleanup-comparison-only` did not finish;
   processing reached `phase=process`, `stage=DONE`, but the run never finalized
   report/summary artifacts and root latest still stayed `status=in_progress`, so
   runtime proof is incomplete and the exact finalization failure location is not
   yet isolated.

Continuation

PR-G is complete for the validator-boundary goal. The later comparison-only run
`20260524T085558Z_976_Rethinking-money-chapter-region-pages-10-11-and-156-217`
completed and produced report/summary/UI artifacts, so the old stalled-run
triage is no longer the next work item. Do not reopen validator-boundary edits
unless a new run reproduces a validation-owned mutation or finalization failure.
Proceed to PR-H: Reader Cleanup Visual Blockers.

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

- validation does not mutate cleaned Markdown/DOCX after pipeline artifact
   production;
- cleanup chunk failures decrease;
- accepted bounded operations increase for valid cases;
- ignored operations remain explainable;
- reader quality score improves or stays improved;
- remaining reader-visible issues decrease;
- no false deletions or readability regressions appear;
- raw and cleaned artifacts remain reviewable.

## Stop Conditions

Stop and update this backlog instead of coding further if any of these become
true:

- PR-A requires changing the cleanup operation contract beyond schema repair;
- a proposed fix needs document-specific deterministic cleanup logic;
- a change would modify structure-recognition authority boundaries;
- real-document evidence shows false deletions or readability regressions;
- comparison-only artifacts stop being produced.
