# Document Entity Round-Trip Development Plan

**Date:** 2026-03-21  
**Status:** active plan  
**Source spec:** `docs/DOCUMENT_ENTITY_ROUNDTRIP_REFACTOR_SPEC_2026-03-21.md`

## 0. Purpose

This plan turns the refactor spec into an execution sequence with the correct priorities.

The governing rule is:

1. first simplify the current pipeline so it stops breaking good Pandoc output;
2. then stabilize validation and reference styling;
3. only then decide whether a larger IR program is justified.

## 1. Priority Order

### Priority 0. Stop Breaking Good Output

Goal:

1. remove mainline behaviors that degrade correct Pandoc headings and lists.

This is the most important work because it directly addresses the current user-visible failures.

### Priority 1. Stabilize Clean Output Baseline

Goal:

1. make the reference DOCX and minimal post-Pandoc formatting sufficient for clean final output.

### Priority 2. Lock In Regression Protection

Goal:

1. make Universal test systems fail on the known heading and list regressions before any broader refactor starts.

### Priority 3. Remove No-Longer-Needed Complexity

Goal:

1. delete extraction and model payloads that only existed for source XML restoration.

### Priority 4. Reassess Architecture

Goal:

1. decide whether ParagraphUnit is now sufficient or whether a true DocumentIR is still needed.

## 2. Non-Goals For Phase 1

Phase 1 must explicitly avoid these scope expansions:

1. do not replace Pandoc;
2. do not build a custom Markdown-to-DOCX renderer;
3. do not start broad module splitting into IR architecture before simplified pipeline validation passes;
4. do not preserve source paragraph XML as a product requirement;
5. do not expand testing into full entity snapshot infrastructure yet.

## 3. Workstreams

## 3.1. Workstream A: Simplify Post-Pandoc Formatting

**Priority:** P0  
**Outcome:** `formatting_transfer.py` stops overriding correct Pandoc semantics.

### Scope

Remove from the default path:

1. source paragraph XML replay;
2. source numbering XML replay;
3. fuzzy source-target paragraph mapping;
4. compatibility wrappers that only serve those behaviors.

Keep in the default path:

1. caption formatting;
2. image-placeholder centering;
3. baseline table styling.

### Target files

1. `formatting_transfer.py`
2. `processing_service.py`
3. `document_pipeline.py`
4. `tests/test_document.py`
5. `tests/test_document_pipeline.py`

### Deliverables

1. minimal `apply_output_formatting()`-style mainline behavior;
2. no numbering restoration after Pandoc list creation;
3. no broad paragraph property replay after semantic style assignment.

### Acceptance

1. Markdown ordered lists that Pandoc renders correctly remain numbered in final DOCX;
2. headings rendered by Pandoc keep clean target heading appearance;
3. image placeholders and captions still format correctly.

## 3.2. Workstream B: Improve Reference DOCX Baseline

**Priority:** P1  
**Outcome:** target styles, not restoration code, control the final visual baseline.

### Scope

Improve the reference DOCX or equivalent baseline style source so the output document looks intentional without source formatting replay.

### Required style coverage

1. `Heading 1` through `Heading 6` defined and visually coherent;
2. ordered and unordered list numbering definitions present and stable;
3. `List Paragraph` spacing appropriate for Pandoc-produced lists;
4. `Caption` style defined;
5. table baseline style defined, such as `Table Grid`;
6. body paragraph defaults reviewed.

### Target files

1. reference DOCX asset used by generation path, if present in repo workflow;
2. `generation.py`
3. any config or docs describing reference-document use.

### Acceptance

1. headings no longer need formatting-transfer fixes for spacing or style identity;
2. list appearance is acceptable from Pandoc plus reference DOCX alone;
3. structural tests confirm that reference DOCX styles are actually inherited.

## 3.3. Workstream C: Fix Heading Detection Separately

**Priority:** P1  
**Outcome:** extraction recognizes heading cases that currently fall through due to under-detection.

### Scope

Improve detection only. Do not mix this with DOCX restoration logic.

### Likely changes

1. prefer resolved alignment or style-chain-aware checks over direct local XML-only checks where appropriate;
2. keep heuristics conservative;
3. avoid promoting generic centered body text to headings.

### Target files

1. `document.py`
2. `tests/test_document.py`
3. new targeted extraction-tier tests if needed.

### Acceptance

1. the known subheading case is detected correctly in extraction;
2. no broad increase in heading false positives in existing tests.

## 3.4. Workstream D: Universal Testing Gates For Simplified Pipeline

**Priority:** P2  
**Outcome:** the simplified path is protected before further cleanup.

### Tier 1: Extraction

Add targeted tests for:

1. style-chain or inherited-alignment heading detection;
2. specific failing heading examples, including `Переосмысление богатства` class cases.

### Tier 2: Structural

Add deterministic tests for:

1. Markdown -> Pandoc -> DOCX preserves headings;
2. Markdown -> Pandoc -> DOCX preserves ordered lists with working Word numbering;
3. minimal output formatting applies `Caption`, image centering, and table styling;
4. no source XML restoration is required for those outcomes.

### Tier 3: Real document regression

Add or strengthen `lietaer-core` assertions for:

1. heading `Переосмысление богатства` exists as `Heading 2` in output DOCX;
2. the known ordered-list block of 3 items survives as real Word numbering.

### Target files

1. `tests/test_document.py`
2. `tests/test_format_restoration.py`
3. `real_document_validation_structural.py`
4. `corpus_registry.toml`
5. real-document validation reporting or assertion helpers.

### Acceptance

1. simplified pipeline is guarded by deterministic tests before cleanup proceeds;
2. lietaer real-document validation fails if known heading or list regressions return.

## 3.5. Workstream E: Remove Restoration Payloads From Extraction And Models

**Priority:** P3  
**Outcome:** data model reflects semantic needs instead of restoration legacy.

### Scope

After Workstreams A through D are green, remove fields and code paths that only supported source-format replay.

### Planned removals

1. `preserved_ppr_xml` from `ParagraphUnit`;
2. `list_num_xml` from `ParagraphUnit`;
3. `list_abstract_num_xml` from `ParagraphUnit`;
4. broad preserved paragraph property capture in extraction;
5. extraction logic whose only consumer was removed restoration code.

### Fields to retain

1. `role`;
2. `heading_level`;
3. `heading_source` if still useful diagnostically;
4. `list_kind`;
5. `list_level`;
6. image and caption semantic metadata;
7. stable paragraph or entity identifiers if they still help marker mode.

### Target files

1. `models.py`
2. `document.py`
3. `formatting_transfer.py`
4. tests covering extraction payloads and rendering assumptions.

### Acceptance

1. no remaining mainline code depends on removed restoration payloads;
2. extraction model is materially simpler;
3. tests reflect semantic, not XML-restoration, contracts.

## 3.6. Workstream F: Architecture Reassessment

**Priority:** P4  
**Outcome:** explicit go or no-go decision on DocumentIR.

### Decision questions

1. does simplified ParagraphUnit-based pipeline now satisfy product requirements for headings, lists, captions, images, and tables?
2. are remaining failures caused by missing semantic model strength, or by smaller local logic gaps?
3. do we have a concrete Phase 2 need for entity-diff validation or richer structural transforms?

### Possible outcomes

1. **No IR needed now:** keep ParagraphUnit, continue targeted cleanup.
2. **IR justified:** start a scoped Phase 2 spec and implementation track.

## 4. Recommended Sequence

Implementation order:

1. Workstream A: simplify `formatting_transfer.py`;
2. Workstream B: improve reference DOCX baseline;
3. Workstream C: fix heading detection;
4. Workstream D: lock in Universal testing gates;
5. Workstream E: remove restoration payloads from extraction and models;
6. Workstream F: reassess need for DocumentIR.

This order is intentional:

1. first stop current damage;
2. then strengthen clean-output defaults;
3. then protect regressions;
4. only then delete legacy payloads;
5. only after that discuss bigger architecture.

## 5. Dependency Graph

1. Workstream A has no dependency on IR.
2. Workstream B has no dependency on IR.
3. Workstream C has no dependency on IR.
4. Workstream D depends on A and partially on B or C, because tests should protect the simplified path that will actually ship.
5. Workstream E depends on A and D, because payload cleanup is safe only after the new path is green.
6. Workstream F depends on A through E.

## 6. Suggested Delivery Units

To avoid one risky mega-change, implement as small reviewable units.

### Unit 1

1. remove list-numbering restoration from `formatting_transfer.py`;
2. keep Pandoc numbering untouched;
3. add deterministic regression test proving numbering survives.

### Unit 2

1. remove paragraph-property replay from mainline output path;
2. keep only minimal caption or image or table formatting;
3. add deterministic regression test proving headings remain clean.

### Unit 3

1. improve reference DOCX styles;
2. add structural test proving style inheritance in output.

### Unit 4

1. fix heading detection;
2. add extraction-tier regression test.

### Unit 5

1. add `lietaer-core` assertions for heading and ordered-list survival;
2. make real-document validation fail on those regressions.

### Unit 6

1. remove obsolete model and extraction payloads;
2. update tests accordingly.

## 7. Verification Gates

## 7.1. Gate A: Local Deterministic Coverage

Required before moving to real-document validation:

1. extraction tests for heading detection;
2. structural tests for Markdown -> Pandoc -> DOCX headings and lists;
3. tests for minimal output formatting.

## 7.2. Gate B: Real-Document Structural Validation

Required before removing legacy extraction payloads:

1. `lietaer-core` structural path passes on simplified pipeline;
2. heading and ordered-list assertions pass;
3. no reliance on source XML replay remains for those cases.

## 7.3. Gate C: Model Cleanup Approval

Required before deleting restoration payloads:

1. all deterministic and real-document gates are green;
2. remaining use sites of restoration payloads are understood and removed or isolated.

## 8. User-Visible Definition Of Done For Phase 1

Phase 1 is complete when:

1. final DOCX uses clean target styles rather than source formatting carryover;
2. headings that Pandoc renders correctly remain visually correct in the final DOCX;
3. lists that Pandoc renders correctly remain real Word lists in the final DOCX;
4. captions, image placement, and table styling still look acceptable;
5. Universal validation fails on reintroduction of the known heading and list regressions;
6. the pipeline no longer depends on source XML replay for normal success.

## 9. Open Decisions After Phase 1

These questions should be answered only after Phase 1 completes:

1. is ParagraphUnit still too overloaded after payload cleanup?
2. do we need entity snapshots and entity diffs immediately, or can corpus-level assertions carry the next stage?
3. do tables or more complex caption relationships expose limitations that justify DocumentIR?
4. should marker mode continue to exist in its current form once simplified pipeline behavior is stable?

## 10. Recommended Ownership Model

If work is split across multiple changes or contributors, ownership should follow concern boundaries:

1. output simplification: `formatting_transfer.py`, pipeline integration, structural tests;
2. reference DOCX and style baseline: generation path plus fixture assets;
3. heading detection: extraction logic plus extraction-tier tests;
4. Universal validation: corpus assertions and structural validators.

This reduces the risk of mixing detection, rendering, and validation changes in one opaque patch.