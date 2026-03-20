# Lietaer Quality Regressions Spec

## Status

Draft. This spec covers the post-crash quality follow-up for the real document validation case `tests/sources/Лиетар глава1.docx`.

### Implementation Progress

- [x] fixed the multi-level numbering acceptance-counter bug in `run_lietaer_validation.py`
- [x] added regression coverage for the counter bug in `tests/test_real_document_pipeline_validation.py`
- [x] hardened registry-aware paragraph mapping in `formatting_transfer.py`
- [x] added focused regression coverage for registry-aware body mapping in `tests/test_document.py`
- [x] updated report loading so the validator prefers formatting diagnostics artifact paths from the current run event log
- [x] ran visible full pytest verification: `419 passed, 4 skipped`
- [ ] run a fresh end-to-end Lietaer validation after the latest mapping and diagnostics-scoping changes
- [ ] confirm the regenerated real-document acceptance report turns fully green

The runtime failure on block generation is already fixed separately. At spec creation time this document covered the remaining acceptance failures:

1. `formatting_diagnostics_threshold`
2. `word_numbering_preserved`

Current implementation status: `word_numbering_preserved` has been fixed; the active remaining acceptance target is `formatting_diagnostics_threshold` plus fresh end-to-end validation.

## Problem Statement

The real-document pipeline now completes successfully for `Лиетар глава1.docx`, produces an openable DOCX, and preserves images, but the acceptance contract is still red.

Current acceptance state from the latest validation artifacts:

1. `result=succeeded`
2. `output_docx_openable=True`
3. `formatting_diagnostics_count=10`
4. `acceptance_failed_checks=formatting_diagnostics_threshold,word_numbering_preserved`
5. `source_numbered_count=3`
6. `output_numbered_count=0`
7. `worst_unmapped_source_count=6`

This means the system no longer crashes, but still degrades final document fidelity in ways that are visible and measurable.

## Why This Work Is Necessary

Closing the runtime crash was sufficient to restore pipeline stability, but not sufficient to claim that this real document is processed correctly.

This follow-up is necessary because:

1. a succeeded pipeline with failed formatting acceptance still represents user-visible document corruption;
2. missing Word numbering is not cosmetic, it changes document meaning and navigation;
3. formatting diagnostics artifacts indicate that source-to-output mapping still loses or mismaps paragraphs during post-processing;
4. if these regressions are left unresolved, the system can silently produce plausible-looking but structurally wrong DOCX output.

## Current State

### What already works

1. generation completes for all blocks of the real document;
2. final markdown is produced;
3. final DOCX opens successfully;
4. image placeholders are resolved;
5. key headings are preserved;
6. caption-to-heading regression is currently not present in this artifact set;
7. list restoration code CAN succeed when mapping succeeds: at least one normalize diagnostics artifact (epoch 1774006910978) shows all three ordered list paragraphs (p0057–p0059) mapped via `similarity` strategy and restoration marked `"restored"` with `target_num_id=1002, target_abstract_num_id=99412`.

### What is still failing

#### 1. Formatting diagnostics threshold

The acceptance logic in `run_lietaer_validation.py` fails when either of these is true:

1. `worst_unmapped_source_count > mismatch_threshold`
2. `caption_heading_conflicts > 0`

For the current real-document result:

1. `mismatch_threshold=0`
2. `worst_unmapped_source_count=6`
3. `caption_heading_conflicts=0`

So the failure is specifically due to unmapped source paragraphs in formatting diagnostics, not due to caption-heading collisions.

The six unmapped source paragraphs in the worst diagnostics artifact (epoch 1774006972465) are:

| ID | Role | Content preview |
|----|------|-----------------|
| p0010 | body | «Как достичь благополучия, если оно не зависит лишь от больших денег?…» |
| p0039 | body | «Допустим, в городской совет избрали новую советницу…» |
| p0056 | body | «Миф (и потенциал) индивидуального богатства…» (heading+body merged in source) |
| p0057 | list/ordered | «Очевидная идея обладания большим количеством денег» |
| p0058 | list/ordered | «Благополучие, достигаемое путем удовлетворения…» |
| p0059 | list/ordered | «Социальные системы, которые мы разработали…» |

Notably, in the best-case diagnostics artifact (epoch 1774006910978) only 2 paragraphs were unmapped (p0010, p0056) — the three ordered list paragraphs were successfully mapped via `similarity` strategy. The `worst_unmapped_source_count` metric takes the maximum across all collected diagnostics artifacts, so the reported value of 6 reflects the worst individual artifact, not the only one.

#### 2. Word numbering preservation

The acceptance logic compares:

1. ordered list paragraphs extracted from source semantic structure;
2. actual Word-numbered paragraphs present in the output DOCX.

For the current real-document result:

1. `source_numbered_count=3`
2. `output_numbered_count=0`

This reported failure must be interpreted carefully. Current evidence shows that ordered list restoration can succeed in the final DOCX, but the acceptance counter currently under-counts ordered paragraphs when they live at a non-zero numbering level inside a shared multi-level numbering definition.

Update after implementation: the counter bug has been fixed, and re-evaluating the current Lietaer artifacts with the updated acceptance logic reports `word_numbering_preserved=True`. The remaining unresolved acceptance item is `formatting_diagnostics_threshold`, pending a fresh end-to-end validation rerun.

## Root Cause Hypothesis

This work starts from two concrete suspicions, both already consistent with the current module boundaries.

### A. Partial source-to-target mapping is still too weak on real output

`formatting_transfer.py` already supports conservative partial mapping using:

1. positional hints;
2. image anchors;
3. adjacent caption rescue;
4. exact normalized text;
5. bounded similarity;
6. generated paragraph registry.

The remaining diagnostics suggest that these strategies are still insufficient for some real paragraphs in `Лиетар глава1.docx`, especially where markdown conversion or paragraph splitting merges text differently from the source.

### B. Numbering restoration is gated on mapping quality and/or list metadata continuity

`normalize_semantic_output_docx()` already contains list restoration behavior and dedicated tests for restoring real Word numbering under mapped and partial-mismatch scenarios.

The remaining real-document failure suggests one or both of these conditions is true after the validation counter is fixed:

1. list paragraphs are not being mapped to their correct output paragraphs;
2. list metadata is not surviving the extraction or registry flow strongly enough for restoration to trigger;
3. numbering restoration is applied too conservatively when mapping confidence is mixed;
4. Pandoc output shape for this real document causes the current restoration heuristic to skip list recovery.

However, evidence from the best-case diagnostics artifact contradicts condition 1 in isolation: when mapping succeeds, the restoration code correctly applies `numPr` elements. The non-determinism of LLM output causes mapping to succeed or fail across different runs.

An additional detail: the three ordered list paragraphs (p0057–p0059) share `list_num_id="1"` and `list_abstract_num_id="1"` with the unordered bullet paragraphs (p0055, p0062). This is correct: the source DOCX uses a single multi-level numbering definition with level 0 = bullet, level 1 = decimal. The restoration code handles this correctly by creating one shared numbering definition for both levels.

### C. Validation counter misclassifies multi-level numbering definitions

`_resolve_numbering_format_by_num_id()` in `run_lietaer_validation.py` determines whether a numbering definition is ordered or unordered by inspecting only the **first** `<w:lvl>` child of each `<w:abstractNum>` element:

```python
for candidate in child:
    if candidate.tag == qn("w:lvl"):
        level = candidate
        break  # only first level inspected
```

For the Lietaer source document, the shared numbering definition has:

- level 0 (`<w:lvl w:ilvl="0">`): `numFmt="bullet"` (unordered)
- level 1 (`<w:lvl w:ilvl="1">`): `numFmt="decimal"` (ordered)

The counter classifies the entire definition as `"bullet"` and therefore reports `output_numbered_count=0` even when restoration has correctly applied `numPr` with `ilvl=1` (decimal format) to the ordered paragraphs.

This means the `word_numbering_preserved` acceptance check is structurally unable to pass for this document class without fixing the counter to inspect the per-paragraph `ilvl` and resolve the format at the correct level.

## Scope

This spec covers a focused quality-hardening pass for the Lietaer real-document workflow.

### In scope

1. improve source-to-output paragraph mapping robustness in the formatting restoration stage;
2. improve ordered-list recovery so real Word numbering is restored in final DOCX when the source contains ordered lists;
3. tighten diagnostics so the failure mode is explicit when mapping or numbering restoration does not trigger;
4. fix the `_resolve_numbering_format_by_num_id()` validation counter so it resolves the numbering format at the paragraph's actual `ilvl`, not just the first level of the abstract numbering definition;
5. add regression coverage anchored to the real acceptance contract for this document class.

### Out of scope

1. changing the startup contract;
2. changing model prompts or chunking strategy unless new evidence proves that formatting loss originates there;
3. broad refactoring of unrelated modules;
4. redesigning the full real-document validation workflow;
5. changing the acceptance thresholds to make the current output pass without fixing root causes.

## Proposed Changes

### 1. Strengthen paragraph mapping in formatting transfer

Primary module: `formatting_transfer.py`

Planned changes:

1. audit unmapped paragraphs from the Lietaer diagnostics artifacts and classify them by failure mode;
2. extend mapping heuristics only where the current diagnostics show stable, defensible recovery opportunities;
3. preserve the current conservative bias against incorrect mappings, but allow higher-confidence registry-assisted matching for reordered or slightly rewritten paragraphs;
4. ensure list paragraphs and adjacent structural paragraphs do not lose mapping solely because markdown conversion changed punctuation, inline emphasis, or heading markers.

Dependency direction:

1. `formatting_transfer.py` may continue importing shared helpers from `document.py`;
2. `document.py` must not begin importing formatting-transfer logic back, to avoid circular dependencies;
3. `document_pipeline.py` remains the orchestrator and should not absorb matching logic.

### 2. Harden numbering restoration for mapped ordered lists

Primary module: `formatting_transfer.py`

Planned changes:

1. trace why ordered source paragraphs in this document are not becoming Word-numbered target paragraphs;
2. make numbering restoration resilient to partial mapping mismatches when list identity is still clear;
3. preserve the requirement that numbering restoration must operate on real DOCX numbering properties, not only visible `1.` or `2.` text prefixes;
4. emit diagnostics that distinguish `list_not_mapped`, `list_mapped_but_not_restored`, and `list_restored` outcomes.

Guardrails:

1. do not restore numbering onto non-list paragraphs;
2. do not inflate output numbered-count by converting ordinary prose into lists;
3. do not rely on visual text prefixes as the primary representation of ordered lists.

### 3. Keep semantic extraction boundaries stable

Primary modules: `document.py`, `models.py`

Planned changes only if diagnostics justify them:

1. verify that source ordered lists in `Лиетар глава1.docx` are extracted with stable `list_kind`, `list_level`, and numbering metadata;
2. only adjust extraction if the real failure is caused by missing or degraded source list metadata before formatting restoration begins.

Constraint:

1. no speculative semantic-model refactor should be started under this spec;
2. extraction changes are allowed only if the real-document evidence shows that formatting transfer is receiving insufficient list semantics.

### 4. Fix validation counter for multi-level numbering

Primary module: `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`

Planned changes:

1. make `_resolve_numbering_format_by_num_id()` return per-`(num_id, ilvl)` format instead of per-`num_id` format;
2. update `_count_ordered_word_numbered_paragraphs()` to resolve the actual `ilvl` from each paragraph's `<w:numPr>` and look up the format at that level;
3. add a unit test that verifies the counter handles multi-level numbering definitions where level 0 is bullet and level 1 is decimal.

Constraint:

1. do not change the acceptance threshold or the semantic meaning of the check;
2. only fix the counting mechanism so it correctly recognizes ordered paragraphs at non-zero levels.

### 5. Preserve orchestration boundaries

Primary modules: `document_pipeline.py`, `processing_service.py`

Planned changes:

1. keep orchestration thin;
2. pass through any additional registry or diagnostics inputs needed by formatting restoration;
3. surface clearer logging when real-document runs produce formatting artifacts or numbering-restoration failures.

Constraint:

1. matching and restoration logic belongs in `formatting_transfer.py`, not in `document_pipeline.py`.

## Consumer Update Plan

No public API redesign is intended.

Expected consumer impact:

1. `processing_service.py` should continue wiring the same formatting functions;
2. `document_pipeline.py` may pass richer diagnostics or registry data, but should keep the same role in the pipeline;
3. the real-document validator in `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` will need a fix to the numbering counter for multi-level definitions, and may also receive diagnostics payload extensions;
4. user-visible behavior should improve only in final DOCX fidelity, not in workflow semantics.

## Files Expected To Change In The Implementation Phase

1. `formatting_transfer.py` — mapping heuristic improvements and numbering restoration hardening
2. `document.py` — only if list metadata extraction is proven incomplete for this document
3. `document_pipeline.py` — for diagnostics plumbing only, if needed
4. `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` — fix `_resolve_numbering_format_by_num_id()` multi-level counter bug and optionally refine diagnostics payload
5. `tests/test_document.py`
6. `tests/test_document_pipeline.py`
7. `tests/test_real_document_pipeline_validation.py`

## Non-Goals

This work does not aim to:

1. make the DOCX a lossless round-trip clone of the source;
2. preserve every visual quirk of the original file;
3. loosen the acceptance checks to accommodate current regressions;
4. start a new decomposition or architecture migration;
5. re-open the already fixed incomplete-response runtime bug.

## Implementation Order

1. [x] fix the validation counter bug in `_resolve_numbering_format_by_num_id()` so that multi-level numbering definitions are correctly resolved per paragraph `ilvl` — this unblocks accurate measurement of the remaining problems;
2. [x] inspect current formatting diagnostics artifacts for the real Lietaer run and classify the six unmapped source paragraphs (see table above for the concrete IDs and roles);
3. [x] trace the three ordered source paragraphs (p0057–p0059) through extraction, generated registry, target mapping, and final DOCX restoration;
4. [x] patch mapping robustness in `formatting_transfer.py` at the narrowest layer that explains the real-document failure;
5. [ ] harden numbering restoration for cases where mapping is partial but list identity remains clear;
6. [x] add focused regression tests that reproduce the observed real failure modes (including multi-level numbering counter edge case);
7. [ ] rerun the Lietaer validation flow;
8. [ ] verify acceptance turns green for both `formatting_diagnostics_threshold` and `word_numbering_preserved`.

## Risks

1. making mapping more permissive can create false-positive paragraph matches and misapply formatting;
2. list restoration can corrupt ordinary paragraphs if mapping confidence is overstated;
3. fixes that only target this one artifact shape may overfit unless backed by focused regression tests;
4. touching extraction unnecessarily could regress already-passing heading and caption behavior;
5. the `worst_unmapped_source_count` metric is sensitive to diagnostics artifact accumulation: if the `.run/formatting_diagnostics/` directory contains stale artifacts from previous runs, the metric inflates even when the latest run maps well.

## Verification Criteria

Implementation is complete only if all of the following hold.

### Real-document acceptance

For `tests/sources/Лиетар глава1.docx`:

1. `result=succeeded`
2. `output_docx_openable=True`
3. `formatting_diagnostics_threshold` passes
4. `word_numbering_preserved` passes
5. `acceptance_passed=True`

### Diagnostics expectations

1. `worst_unmapped_source_count=0` unless the acceptance contract is explicitly revised in a future, separately approved spec;
2. `caption_heading_conflicts=0` remains true;
3. numbering diagnostics, if added, clearly explain whether restoration was skipped, partially applied, or fully applied;
4. the validation counter correctly identifies ordered paragraphs in multi-level numbering definitions where ordered items are at `ilvl > 0`.

### Test coverage

Focused regression coverage should demonstrate:

1. ordered-list paragraphs survive mapping and regain real Word numbering in the output DOCX;
2. partial mapping mismatch does not unnecessarily suppress numbering restoration when list identity remains clear;
3. strengthened mapping does not regress caption preservation or heading normalization;
4. real-document acceptance evaluation fails for the old behavior and passes for the corrected one.

## Suggested Verification Commands

During implementation and final verification, use the repository test workflow contract:

1. targeted tests through the visible VS Code test tasks when matching the requested scope;
2. real validation rerun for `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`;
3. full visible pytest verification before claiming the work complete.
