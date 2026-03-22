# Document Entity Round-Trip Refactor Spec

**Date:** 2026-03-21  
**Status:** archived after Phase 1 realization  
**Trigger:** heading and list regressions continue to reappear because the current extraction -> markdown -> DOCX restoration pipeline does not preserve document entities through a stable end-to-end contract.

Archive note:

1. the Phase 1 direction from this spec was realized by moving the mainline output path to a dynamic reference DOCX baseline plus a minimal post-Pandoc formatter;
2. the document remains useful as design history, but it is no longer the active source of truth.

## 0. Product Goal Clarification

This refactor is not trying to reproduce the source DOCX formatting zoo.

The intended output contract is narrower and more useful:

1. produce a clean, readable, consistent final DOCX;
2. use the new document's default style system as the visual baseline;
3. preserve document semantics and basic inline emphasis;
4. preserve images and their reasonable placement;
5. avoid replaying source-specific layout noise, custom style drift, and paragraph XML quirks.

This means the project should optimize for **semantic reconstruction into a clean target document**, not for **source-format round-trip fidelity**.

## 1. Problem Statement

The current implementation can detect many entities locally, but it still reconstructs the final DOCX through a lossy and heuristic pipeline.

Observed user-visible failures are not isolated bugs. They are symptoms of an architectural mismatch:

1. subheadings such as `Переосмысление богатства` can survive extraction yet still return as ordinary text in the final DOCX;
2. ordered lists can be represented correctly in final Markdown yet still fail to reappear as reliable Word numbering in the final DOCX;
3. fixes tend to improve one sample or one validation mode while re-breaking another because semantics are repeatedly inferred, flattened, and reconstructed instead of being carried explicitly.

This is why incremental fixes have not produced a durable result over the last several weeks.

## 2. Root Cause Summary

### 2.1. Semantics Are Flattened Too Early

Current flow:

1. `document.py` extracts paragraphs and classifies roles;
2. `ParagraphUnit.rendered_text` converts those roles into Markdown syntax such as `## Heading` or `1. List item`;
3. Pandoc converts the Markdown into DOCX paragraphs;
4. `formatting_transfer.py` tries to guess how new DOCX paragraphs correspond to original source paragraphs and reapply Word semantics afterward.

This means headings, lists, captions, and tables are not preserved as first-class entities end to end. They are converted into text syntax and later reconstructed heuristically.

### 2.2. One Data Model Carries Too Many Responsibilities

`ParagraphUnit` currently mixes together:

1. source extraction output;
2. semantic classification;
3. Markdown rendering hints;
4. source XML preservation data;
5. target restoration hints;
6. mapping identity.

That coupling makes every change risky. A field added for extraction immediately affects rendering, mapping, restoration, and validation.

### 2.3. Identity Exists Only At Paragraph Granularity

`paragraph_id` is useful, but it is still paragraph-centric and only partially enforced through marker mode.

This breaks down when one source paragraph becomes multiple semantic targets, for example:

1. body paragraph becomes heading + body split;
2. list block is normalized by the model;
3. caption is detached or merged;
4. table content expands into multiple target paragraphs.

Current code compensates with special cases such as `accepted_split_targets`, but those are local repairs, not a durable round-trip contract.

### 2.4. Formatting Transfer Is Doing Semantic Reconstruction

`preserve_source_paragraph_properties()` no longer only preserves formatting. It also:

1. maps source paragraphs to target paragraphs;
2. applies semantic styles;
3. restores list numbering;
4. emits diagnostics for semantic mismatches.

This is too much responsibility for one post-Pandoc step. It is effectively acting as a semantic recovery engine after semantics were already flattened away.

### 2.5. Semantic Normalization And Source Geometry Conflict

The current restoration step applies semantic styles and then reapplies preserved source paragraph properties such as:

1. `ind`;
2. `tabs`;
3. `spacing`;
4. `jc`;
5. other `pPr` fragments.

This is a direct source of regressions such as:

1. heading text visually behaving like body text with legacy tabs or indentation;
2. list paragraphs receiving numbering but retaining incompatible paragraph geometry;
3. semantic normalization being partially overwritten by source-layout residue.

### 2.6. The Current Pipeline Preserves Too Much Of The Wrong Thing

The code currently captures and replays a broad set of paragraph properties from the source DOCX.

That is misaligned with the real product goal.

The output document does not need source-specific:

1. tab stops;
2. indentation geometry inherited from arbitrary styles;
3. source spacing quirks;
4. direct paragraph alignment copied blindly;
5. pagination controls such as `keepNext` and `keepLines`;
6. low-level paragraph XML fragments that only made sense in the source template.

When those are replayed onto a newly generated document, they do not preserve quality. They import layout noise.

### 2.7. Validation Mostly Checks Aggregates, Not Entity Contracts

The Universal validation system is a strong base, but current checks are still mostly aggregate and tolerant:

1. counts of headings and numbered items;
2. text similarity;
3. formatting diagnostic thresholds;
4. heading-only collapse detection;
5. coarse preservation checks.

Those checks can pass while the actual entity graph is still wrong. For example:

1. an extra heading can appear while validation still passes;
2. a list can be counted yet not preserve the expected Word numbering contract at the exact location;
3. a restore diagnostic can exist and still be accepted under thresholds.

## 3. What Is Wrong With The Current Architecture

The core defect is this:

**The system does not own a canonical, entity-level intermediate representation of the document.**

Instead, it relies on a chain of partial representations:

1. source Word XML facts;
2. `ParagraphUnit` heuristics;
3. Markdown text markers;
4. Pandoc-generated DOCX paragraphs;
5. heuristic source-target remapping.

Because there is no canonical entity graph, every stage has to recover information that was already available earlier.

That creates four persistent failure modes:

1. classification drift: entity type changes from one stage to another;
2. structural drift: one source entity turns into a different count or arrangement of target paragraphs;
3. formatting drift: semantic style and copied source XML fight each other;
4. validation drift: tests prove approximate survival, not exact entity fidelity.

## 4. Refactoring Goals

The refactor must make document entities explicit and stable across the full pipeline.

Primary goals:

1. headings, lists, captions, tables, images, and body paragraphs have explicit typed entities;
2. every entity has a stable identity independent of paragraph count after editing;
3. Markdown becomes a projection of the entity graph for the LLM, not the source of truth;
4. final DOCX is generated from the entity graph plus a minimal formatting policy, not from heuristic source-target paragraph matching and raw source XML replay;
5. Universal test systems validate entity contracts per profile, not only aggregate counts.

Secondary goals:

1. aggressively reduce dependence on source paragraph XML;
2. prefer stable target styles over source formatting inheritance;
3. keep only a narrow set of source-derived facts when they are clearly product-relevant.

## 5. Proposed Target Architecture

Important scope correction:

1. this section describes a possible Phase 2 architecture, not the immediate recovery plan;
2. the immediate Phase 1 priority is simplification of the existing pipeline, especially removal of Category C restoration behavior from the mainline path;
3. the project should not start with broad module creation if the current failures can be removed by simplifying post-Pandoc behavior first.

### 5.1. Introduce A Canonical Document IR

Add a dedicated intermediate representation, for example in a new module such as `document_ir.py`.

Suggested core entities:

1. `DocumentIR`
2. `BlockNode`
3. `HeadingNode`
4. `ParagraphNode`
5. `ListNode`
6. `ListItemNode`
7. `ImageNode`
8. `CaptionNode`
9. `TableNode`

Each node should carry:

1. stable `entity_id`;
2. `entity_type`;
3. normalized text payload;
4. source anchor metadata;
5. semantic metadata such as heading level or list kind;
6. formatting intent, separated from raw source XML fragments.

The IR should not store arbitrary `pPr` fragments as a mainline rendering dependency.

### 5.2. Split The Pipeline Into Four Explicit Layers

#### Layer A. Source Analysis

Module candidates:

1. `document_source_reader.py`
2. `document_entity_detector.py`

Responsibilities:

1. ordered traversal of DOCX body;
2. extraction of source facts;
3. detection of headings, captions, tables, lists, images;
4. construction of `DocumentIR`.

No Markdown rendering here.

#### Layer B. LLM Projection

Module candidate: `document_llm_projection.py`

Responsibilities:

1. convert `DocumentIR` blocks into editable LLM payloads;
2. preserve `entity_id` markers at entity level, not only paragraph level;
3. allow controlled transformations such as heading promotion or list normalization;
4. parse edited output back into edited IR fragments.

Markdown remains useful here, but only as an interchange format. The canonical output of this layer is edited IR, not freeform Markdown text.

#### Layer C. Structural Assembly

Module candidate: `document_assembly.py`

Responsibilities:

1. merge edited IR fragments into a final `DocumentIR`;
2. enforce structural invariants;
3. reject illegal transforms such as orphan captions, broken list nesting, or heading-to-body demotion without explicit policy.

#### Layer D. DOCX Rendering

Module candidate: `document_docx_renderer.py`

Responsibilities:

1. convert edited Markdown to DOCX through Pandoc;
2. treat Pandoc as the canonical Markdown -> DOCX engine by design, not as a temporary convenience;
3. apply semantic styles from entity type and level through Markdown plus reference DOCX defaults;
4. apply only minimal post-Pandoc corrections for cases Pandoc does not express well enough for this product;
5. reinsert images and apply baseline table styling.

Pandoc should remain the only Markdown -> DOCX converter in the architecture.

Reasoning:

1. Pandoc already handles inline emphasis, nested lists, mixed formatting, escaped characters, and HTML tables better than a custom Python renderer would;
2. replacing Pandoc would force the project to build and maintain a Markdown-to-runs engine that is outside the current product need;
3. the current problem is not that Pandoc is insufficient, but that post-processing overrides good Pandoc output with source-driven restoration logic.

## 6. Critical Design Changes

### 6.1. Separate Semantic Intent From Minimal Formatting Hints

For each entity, store two different things:

1. semantic intent: heading level, list type, caption attachment, table structure;
2. minimal rendering hints: inline emphasis, image size hints, optional center alignment for image-only blocks, optional caption placement hints.

The renderer must have explicit precedence rules:

1. semantic intent wins for style family and structure;
2. default target styles win for typography, spacing, indentation, and paragraph geometry;
3. source-derived hints may refine rendering only when they are explicitly whitelisted;
4. source tabs and indentation must never be blindly replayed onto semantically normalized headings or regenerated lists.

### 6.1a. Explicit Simplification Policy

The project should adopt a hard simplification rule:

**If a formatting detail is not represented as semantic structure or safe inline markup, it should usually be dropped.**

Keep by default:

1. headings and heading levels;
2. body paragraphs;
3. ordered and unordered lists with nesting;
4. tables;
5. images;
6. captions;
7. bold, italic, underline, sup, sub, hyperlinks, line breaks;
8. basic image size or aspect ratio hints when available.

Do not preserve by default:

1. source paragraph style names;
2. direct `pPr` XML replay;
3. tab stops;
4. left or right indents from source styles;
5. source spacing values;
6. source justification except where product policy explicitly needs it;
7. page-break and widow or orphan controls;
8. custom fonts, colors, and local style hierarchies;
9. Word numbering XML copied from source;
10. arbitrary section-era layout artifacts.

Allow only as explicit exceptions:

1. image dimensions if needed to avoid destructive scaling;
2. center alignment for image-only or caption paragraphs when policy says so;
3. very narrow compatibility shims required for a deterministic renderer bug.

### 6.2. Remove Paragraph Mapping From The Mainline Path

The current `_map_source_target_paragraphs()` approach should be removed from the default pipeline, not replaced immediately with another complex mapping layer.

For the simplified mainline path, paragraph mapping is unnecessary.

The remaining post-Pandoc operations can use content-based target detection:

1. image placeholder paragraphs can be detected directly by placeholder text;
2. captions can be detected by short target paragraphs near image or table blocks plus lexical markers;
3. tables can be styled directly through `document.tables`.

Entity anchoring becomes relevant only if a later Phase 2 architecture genuinely needs entity-level transforms or entity-diff validation.

### 6.3. Make Lists A First-Class Structural Object

A Word list is not a paragraph style plus late `numPr` injection.

The IR must represent:

1. list block boundaries;
2. ordered vs unordered type;
3. nesting level;
4. item ordering;
5. optional renderer numbering policy.

DOCX rendering should construct list numbering intentionally from list entities and target defaults, not by replaying source numbering XML.

### 6.4. Make Heading Promotion And Demotion Explicit

If the model or deterministic structural path turns a source paragraph into a heading, this must be represented as an explicit entity transform.

Do not rely on:

1. Markdown `#` syntax surviving correctly;
2. target paragraph count coincidentally matching source paragraph count;
3. accepted split-target heuristics.

## 7. Proposed Module Layout

Suggested modules after refactor:

1. `document_source_reader.py`: ordered block traversal and raw Word facts
2. `document_entity_detector.py`: source classification into IR nodes
3. `document_ir.py`: canonical node and document models
4. `document_llm_projection.py`: IR <-> editable markdown projection with entity markers
5. `document_assembly.py`: merge, validation, and structural invariants
6. `document_docx_renderer.py`: final DOCX generation from IR
7. `document_style_policy.py`: target default styles and minimal allowed carryover rules
8. `document_validation.py`: entity-aware validation helpers shared by unit and universal tests

Legacy modules to slim down:

1. `document.py` becomes a compatibility facade or is split completely;
2. `formatting_transfer.py` shrinks to transitional fallback utilities and can later be retired from the mainline path;
3. `document_pipeline.py` orchestrates stages but no longer owns entity semantics.

## 8. Phased Refactor Plan

Scope correction:

1. Phase 1 is simplification of the current pipeline;
2. the IR architecture described later is Phase 2 and should start only if Phase 1 still leaves unsolved product requirements.

### Phase 1. Simplify The Existing Pipeline Immediately

Deliverables:

1. remove Category C behavior from `formatting_transfer.py` in the mainline path;
2. replace restoration-heavy logic with a minimal `apply_output_formatting()` layer;
3. keep only caption styling, image-placeholder centering, and baseline table styling as post-Pandoc formatting responsibilities;
4. improve the reference DOCX so target defaults carry more of the intended visual design;
5. fix heading detection separately where extraction is under-detecting heading semantics;
6. add focused Tier 1 and Tier 2 tests around heading detection and Markdown -> Pandoc -> DOCX preservation.

Success criteria:

1. lists created correctly by Pandoc remain untouched and preserve numbering in the final DOCX;
2. headings created correctly by Pandoc are no longer visually degraded by source XML replay;
3. `lietaer-core` validation passes on the simplified path;
4. extraction no longer needs broad paragraph XML payloads for output correctness.

### Phase 2. Establish The IR Without Changing User-Facing Behavior

Deliverables:

1. introduce `DocumentIR` and typed nodes;
2. build adapters from current `ParagraphUnit` extraction into IR;
3. add entity IDs and source anchors;
4. add debug serialization of IR for diagnostics.

Success criteria:

1. extraction tests pass against both legacy and IR views;
2. no pipeline behavior change yet;
3. Universal extraction tier can emit IR snapshots.

### Phase 3. Move Detection Logic Out Of `document.py`

Deliverables:

1. separate source reading from entity detection;
2. move heading/list/caption/table detection into dedicated detector module;
3. define explicit detection evidence for each entity.

Success criteria:

1. each entity has a detection trace;
2. heuristics become testable without invoking rendering;
3. false-positive and false-negative cases are covered independently.

### Phase 4. Replace Marker Mode With Entity-Preserving LLM Projection

Deliverables:

1. project IR nodes to editable markdown with `entity_id` markers;
2. parse edited output back into edited nodes;
3. allow controlled one-to-many transforms where policy permits;
4. forbid silent entity loss.

Success criteria:

1. no dependence on paragraph-count equality;
2. heading split and list normalization are explicit operations;
3. diagnostics report entity additions, removals, merges, and splits by ID.

### Phase 5. Evaluate Whether IR-Based Entity Assembly Is Still Needed

Decision gate:

1. if ParagraphUnit plus simplified Pandoc-centered pipeline satisfies product requirements, do not begin IR work immediately;
2. start IR work only if there are concrete remaining tasks that cannot be solved cleanly without a stronger intermediate representation.

Additional clarification:

1. the current ParagraphUnit is overloaded mainly because it carries source-restoration payloads;
2. after removal of `preserved_ppr_xml`, numbering-XML payloads, and related restoration fields, ParagraphUnit may become a sufficiently light semantic carrier for the next stage of work;
3. the team should explicitly reassess ParagraphUnit after simplification before committing to a larger IR program.

### Phase 6. Replace Heuristic DOCX Restoration With Deterministic Rendering

Deliverables:

1. render headings, paragraphs, lists, captions, and tables from IR directly;
2. use target default styles as the baseline and allow only narrow policy-governed compatibility rules;
3. demote `formatting_transfer.py` to fallback or migration-only role.

Success criteria:

1. mainline output no longer depends on `_map_source_target_paragraphs()`;
2. list numbering is created intentionally from list entities and target renderer rules;
3. heading styling no longer regresses through replayed `tabs` or `ind`.

### Phase 7. Retire Transitional Heuristics And Tighten Contracts

Deliverables:

1. remove accepted-split special cases from the primary path;
2. reduce tolerance-driven checks where deterministic entity validation becomes available;
3. preserve fallback tooling only for diagnostics and migration.

## 9. Refactoring Risks

1. short-term duplication while old and new paths coexist;
2. temporary validation noise during migration;
3. increased implementation scope if tables and images are included too early.

Risk management:

1. migrate headings and lists first;
2. keep tables and captions on the same IR but behind later renderer milestones;
3. preserve current pipeline as fallback until Universal structural tier proves parity.

## 9a. Transitional Simplification Diagnosis

Before the full IR refactor lands, the current codebase should explicitly recognize that `formatting_transfer.py` is doing far more than the product needs.

Practical diagnosis:

1. most of the file exists to repair or replay source formatting that the product no longer wants to preserve;
2. the only clearly product-aligned post-Pandoc operations are:
3. applying `Caption` style plus centered alignment to true captions;
4. centering image-placeholder paragraphs before image reinsertion;
5. applying `Table Grid` or equivalent target table styling.

Everything else belongs to a transitional or removable category:

1. paragraph XML replay from source;
2. source numbering XML replay;
3. fuzzy source-target paragraph mapping infrastructure;
4. compatibility wrappers that exist only to support those three categories.

### 9a.1. Why Lists Break In The Current Design

Current failure chain:

1. Markdown already contains correct ordered or unordered list syntax;
2. Pandoc generates valid list structure in the output DOCX;
3. `formatting_transfer.py` then attempts to restore list semantics from source numbering XML;
4. if paragraph mapping is incomplete or unstable, target paragraphs may keep `List Paragraph` styling but lose the effective numbering contract;
5. result: visual list indentation without working numbering.

This is the wrong direction of control.

The correct rule is simpler:

1. if Pandoc already created the correct target list from Markdown, the post-processing layer should not override it.

### 9a.2. Why Headings Regress Visually

There are two different classes of heading problems and they should be treated separately.

Detection problem:

1. current heading heuristics in `document.py` may miss style-inherited alignment or other signals.

Restoration problem:

1. even when Markdown already contains a proper heading and Pandoc creates a target heading style, post-processing may replay source paragraph XML such as spacing, tabs, or alignment and partially corrupt the clean target style.

These should not be solved by adding more restoration logic. They should be solved by reducing restoration scope and separately fixing detection.

## 9b. Transitional Simplification Plan

The spec should explicitly include a short-term simplification phase before or alongside the deeper IR refactor.

### 9b.1. Radically Reduce `formatting_transfer.py`

Target transitional state:

1. replace the current restoration-heavy module with a minimal `apply_output_formatting()` layer;
2. keep only post-Pandoc operations that Pandoc does not model well enough for this product.

Important Phase 1 compatibility rule:

1. do not redesign the public pipeline callback surface in the same change;
2. keep the existing `preserve_source_paragraph_properties()` and `normalize_semantic_output_docx()` entry points for compatibility with `processing_service.py`, `document_pipeline.py`, structural validators, and tests;
3. route real work through one effective mainline path only;
4. keep `normalize_semantic_output_docx()` as a compatibility no-op during Phase 1;
5. if a new internal helper such as `apply_output_formatting()` is introduced, it should sit behind the existing public entry point rather than replace the pipeline API immediately.

Transitional responsibilities of this layer:

1. apply `Caption` style and centered alignment to detected captions;
2. center image placeholder paragraphs so later image reinsertion lands in the right visual block;
3. apply `Table Grid` or equivalent table baseline style to output tables.

Notably absent from this layer:

1. no source XML replay;
2. no source numbering XML replay;
3. no fuzzy paragraph mapping infrastructure;
4. no semantic reconstruction from target text similarity.

This simplification should be treated as the immediate execution path, not as a side note.

### 9b.2. Remove Source XML Preservation From Extraction

`ParagraphUnit` should stop carrying raw source paragraph restoration payloads as part of the mainline pipeline.

Planned removals:

1. broad `PRESERVED_PARAGRAPH_PROPERTY_NAMES` capture policy;
2. `preserved_ppr_xml` as a standard extraction output;
3. `list_num_xml` and `list_abstract_num_xml` as required fields for output reconstruction.

Fields that remain useful:

1. `role`;
2. `heading_level`;
3. `list_kind`;
4. `list_level`;
5. image identity and placement metadata;
6. caption attachment semantics.

### 9b.3. Invest In Reference DOCX Instead Of Source XML Replay

The spec should explicitly shift complexity from restoration code into the reference document and renderer defaults.

Phase 1 implementation rule:

1. the current reference DOCX is built dynamically in `generation.py` via `_build_reference_docx()` and is not a checked-in asset;
2. Workstream B should start by extending that dynamic builder;
3. introducing a static reference DOCX file in the repository is optional and should happen only if Python-side style construction becomes insufficient, especially for stable numbering-definition control.

Recommended improvements:

1. define clean numbering styles for ordered and unordered lists in the reference DOCX;
2. ensure `Heading 1` through `Heading 6` are all defined, not only the first few levels;
3. tune heading spacing in `Heading 1` through `Heading 6`;
4. ensure `List Paragraph` spacing is configured for both tight and loose list cases as expected by Pandoc output;
5. ensure body, caption, and list paragraph defaults are visually coherent;
6. define table styling for the baseline output document;
7. verify through structural tests that Pandoc actually inherits the intended reference-document styles.

This is a better place to express output quality than trying to reverse-engineer source formatting from arbitrary Word XML.

### 9b.4. Fix Heading Detection As A Separate Workstream

The spec should distinguish simplification from detector fixes.

In particular:

1. heading detection should use higher-level resolved properties where possible, such as style-resolved alignment behavior, instead of only direct XML checks;
2. this work should be tested in extraction-tier coverage and should not be bundled together with output-format restoration logic;
3. the known `Переосмысление богатства` regression must not be treated as proven evidence of missed style-inheritance or alignment inheritance in the source DOCX without first verifying the actual source formatting;
4. if a corpus sample expresses a semantic heading as plain `Body Text` with no explicit heading cues, promoting it is a new heuristic contract and should be specified as such rather than described as recovery of an already encoded heading signal.

## 10. Testing Strategy With Universal Test Systems

The Universal test systems should become the main acceptance framework for the refactor, but the order of adoption matters.

Immediate priority:

1. focused regression coverage for the simplified pipeline;
2. structural confirmation that Pandoc output remains correct when post-processing stops overriding it.

Later priority:

1. richer entity-level validation only after the simplified pipeline stabilizes.

### 10.1. Add Entity Snapshot Fixtures

This is a Phase 2 enhancement, not a Phase 1 prerequisite.

For each registered corpus document, persist a reviewed source entity snapshot.

Suggested artifact family:

1. `source_entities.json`
2. `output_entities.json`
3. `entity_diff.json`

Each snapshot should describe:

1. ordered entity IDs;
2. entity types;
3. heading levels;
4. list block boundaries and item order;
5. caption attachments;
6. table presence and row or cell counts;
7. anchor metadata and confidence.

### 10.2. Extend Corpus Registry With Entity Contracts

This is directionally correct, but should be introduced after the simplified pipeline becomes stable enough that entity snapshots will not churn excessively.

However, the project should not wait for a full entity snapshot system before adding concrete corpus-level regression assertions.

Early assertions should be added where they protect known failures with low ambiguity.

Add optional declarative expectations such as:

1. `required_heading_texts`
2. `required_heading_levels`
3. `required_list_blocks`
4. `required_list_item_sequences`
5. `required_caption_pairs`
6. `forbid_entity_type_changes`
7. `max_entity_splits`
8. `max_entity_merges`

These are stronger than `min_headings` or `min_numbered_items` and reflect the real user-visible contract.

They should not assert source-specific typography. They should assert semantic output quality.

### 10.3. Split Universal Validation Into Four Explicit Layers

#### A. Extraction Contract Tests

Deterministic, no Pandoc, no LLM.

Verify:

1. entity graph shape from source document;
2. exact heading and list detection on corpus samples;
3. detector evidence for borderline cases.

Phase 1 emphasis:

1. concrete failing heading-detection cases with verified source evidence;
2. style-chain or inherited-alignment cases where the source document actually encodes those signals;
3. separately specified heuristic-promotion cases if the product decides to elevate plain body paragraphs into headings.

#### B. Structural Round-Trip Tests

Deterministic, no LLM.

Verify:

1. IR -> DOCX -> IR preserves entity graph;
2. heading levels survive exactly where required;
3. list blocks remain lists with the same item sequence and nesting;
4. renderer does not import source tab stops, legacy indentation, or paragraph geometry noise into normalized output.

Phase 1 structural scope should be simpler and more concrete:

1. Markdown -> Pandoc -> DOCX round-trip preserves headings and lists without formatting-transfer restoration;
2. minimal post-Pandoc formatting correctly applies caption style, image centering, and table baseline styling.

#### C. Projection Contract Tests

Deterministic, no model API.

Verify:

1. IR -> editable markdown -> IR preserves entity IDs;
2. allowed splits and merges are explicit and validated;
3. illegal entity loss is rejected before DOCX rendering.

#### D. Full Universal Validation

Model-backed.

### 10.4. Transitional Simplification Test Coverage

Before the full IR migration is complete, Universal test systems should also validate the simplified post-Pandoc strategy directly.

Required transitional coverage:

1. extraction-tier test for heading detection through style inheritance or style-chain alignment where those source cues actually exist;
2. structural-tier test proving that Markdown headings and lists survive Pandoc round-trip without source XML restoration;
3. structural-tier test proving that the minimal output-formatting layer correctly applies `Caption`, centered image-placeholder alignment, and table styling;
4. structural-tier test proving that ordered lists remain numbered when post-processing does not override Pandoc numbering;
5. real-document profile validation for `lietaer-core` under the simplified path.

Concrete test placement for Phase 1:

1. end-to-end DOCX byte behavior should live primarily in `tests/test_document.py`;
2. helper-level mapping or formatting utilities should live in `tests/test_format_restoration.py` while those helpers still exist;
3. pipeline orchestration and callback compatibility assertions should live in `tests/test_document_pipeline.py`;
4. corpus-level assertions should live in `real_document_validation_structural.py` and `corpus_registry.toml`.

This transitional coverage is the Phase 1 acceptance gate.

### 10.5. What Should No Longer Be Tested As A Product Contract

The new testing strategy should stop encoding the following as success criteria:

1. exact replay of source paragraph XML;
2. preservation of source numbering definitions in output DOCX;
3. paragraph-to-paragraph fuzzy mapping quality as a primary product metric;
4. source-specific spacing, tabs, or indentation values.

Those can remain migration diagnostics temporarily, but they should not define output correctness.

### 10.6. Early Corpus-Level Assertions Before Full Entity Snapshots

Before a full entity snapshot or entity-diff system exists, the Universal test system should still add a small number of concrete high-value corpus assertions.

Recommended early assertions for `lietaer-core`:

1. the heading `Переосмысление богатства` exists in the output DOCX with the expected heading level, currently `Heading 2`;
2. the known ordered-list block with 3 items survives in the output DOCX as real Word numbering, not only as visually indented text;
3. these checks should be introduced during the simplified-pipeline stabilization phase, not deferred until Phase 2 architecture work.

Clarification:

1. this output assertion does not, by itself, prove that source extraction must classify the original paragraph as a heading;
2. for `lietaer-core`, the Phase 1 contract is output-level preservation and regression detection;
3. any extraction-tier expectation for this exact paragraph must be backed either by verified source formatting evidence or by an explicitly approved new heuristic rule.

Verify:

1. UI-parity configuration;
2. entity diff against source and expected tolerance;
3. run-scoped artifacts for failed entity contracts;
4. repeat or soak instability by entity type, not only by final status.

### 10.4. Promote User-Found Regressions Into Corpus Profiles

Every manual UI failure of this class should create or update a corpus profile with:

1. source sample;
2. expected entity snapshot;
3. exact regression rule;
4. structural and full-tier coverage.

For the current case, add a profile dedicated to:

1. preservation of subheading `Переосмысление богатства` as a heading entity with the expected level;
2. preservation of the numbered list block that follows it as a real ordered list in DOCX, not only as Markdown text.

## 11. Immediate Testing Gaps To Close

Before implementation starts, the following missing tests should be added to the new plan and scheduled early:

1. heading entity survives extraction, projection, rendering, and re-extraction with the same `entity_id` and level;
2. source body geometry such as tabs or indentation does not override a rendered heading entity;
3. ordered list block survives as a list entity and as target-generated Word numbering in output DOCX;
4. no test relies on source numbering XML replay as the expected mechanism of success;
5. one-to-many transforms are represented explicitly in entity diff artifacts, not hidden by tolerance thresholds.

## 11a. Concrete Simplifications To Make In The Current Codebase

Short-term simplifications before the full refactor:

1. stop capturing broad `preserved_ppr_xml` as a product requirement;
2. remove `tabs`, `ind`, `spacing`, `jc`, `keepNext`, `keepLines`, `pageBreakBefore`, `mirrorIndents`, `textDirection`, `widowControl`, `adjustRightInd`, `contextualSpacing`, and similar paragraph geometry from the mainline carryover path;
3. stop treating source numbering XML as the preferred route for list success;
4. demote `preserve_source_paragraph_properties()` from semantic restorer to a minimal post-render normalizer;
5. keep image reinsertion, captions, inline emphasis, and semantic block detection as first-class concerns;
6. replace compatibility-by-XML with compatibility-by-render-policy using a reference DOCX or renderer defaults.

If a temporary transition layer is needed, it should be opt-in and narrow, not the default pipeline behavior.

## 11b. Concrete Transitional Scope For `formatting_transfer.py`

If the current module survives temporarily, the spec should narrow it to three product-justified operations:

1. caption paragraphs -> `Caption` style plus centered alignment;
2. image placeholder paragraphs -> centered alignment;
3. tables -> target baseline table style such as `Table Grid`.

Phase 1 API rule:

1. keep the public compatibility wrappers during this narrowing;
2. the mainline path should flow through one effective formatter implementation only;
3. removal of the redundant protocol or second callback belongs to later API cleanup, not to the simplification patch itself.

All other behavior should be marked deprecated in the spec and removed from the default path:

1. `_apply_preserved_paragraph_properties()`;
2. `_restore_list_numbering_for_mapped_paragraphs()` and related helpers;
3. `_map_source_target_paragraphs()` and the fuzzy matching stack around it;
4. dead or compatibility-only normalization wrappers that no longer change output.

## 11c. Recommended Immediate Execution Order

The recommended order for implementation is:

1. remove Category C behavior from `formatting_transfer.py`;
2. introduce minimal `apply_output_formatting()` behavior;
3. keep the current pipeline callback API stable while routing mainline behavior through the simplified formatter;
4. improve the dynamic reference DOCX style baseline in `_build_reference_docx()`;
5. fix heading detection only for verified source-signal gaps, and specify any new heuristic promotions explicitly;
6. add Tier 1 and Tier 2 regression tests for heading detection and Pandoc round-trip;
7. validate `lietaer-core` on the simplified pipeline;
8. remove no-longer-needed extraction payloads such as `preserved_ppr_xml`, `list_num_xml`, and `list_abstract_num_xml`;
9. clean up residual dead code in models and extraction logic.

Only after that should the team decide whether ParagraphUnit remains sufficient or whether a full DocumentIR is justified.

## 12. Recommended Execution Order

1. implement IR and entity snapshots;
2. migrate heading detection and heading rendering to the IR path;
3. migrate list detection and deterministic DOCX list rendering;
4. add entity-level structural round-trip validation to Universal test systems;
5. switch UI-parity full runs to the new renderer behind a feature flag;
6. retire paragraph-remap restoration from the mainline path after parity is demonstrated.

## 13. Acceptance Criteria

The refactor is complete when all of the following are true:

1. headings and lists are preserved by explicit entity contracts, not only by aggregate counts;
2. final DOCX generation no longer depends on heuristic source-target paragraph mapping for the primary path;
3. source formatting carryover cannot reintroduce body tabs or incompatible indentation into normalized headings or lists;
4. Universal structural validation can fail a run on exact entity regressions even when text similarity stays high;
5. UI-discovered regressions can be promoted into corpus-backed deterministic and full-tier validation with reusable entity snapshots;
6. the default pipeline no longer attempts to reproduce arbitrary source paragraph XML in the output DOCX.
