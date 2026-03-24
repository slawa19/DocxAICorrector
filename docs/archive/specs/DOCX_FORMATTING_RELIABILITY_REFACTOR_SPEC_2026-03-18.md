# DOCX Formatting Reliability Refactor Spec

**Date:** 2026-03-18  
**Status:** draft  
**Trigger:** real-run regressions on `Лиетар глава1.docx` where final DOCX lost structural fidelity even though text processing completed successfully.

---

## 1. Problem Statement

The current pipeline can finish successfully at the text level while still producing a structurally degraded DOCX.

Observed user-visible failures in the latest real run:

1. image/table captions can turn into headings;
2. section titles authored as visually emphasized body text can become `Heading 1` in some places and remain plain body text in others;
3. numbered lists are preserved during extraction into markdown, but DOCX-native list formatting is not reliably restored in the final `.docx`;
4. final semantic formatting passes can be skipped entirely when source and generated paragraph counts diverge.

This creates a misleading success mode:

1. the pipeline reports `processing_completed`;
2. the text is present;
3. but the final DOCX no longer preserves the authorial structure contract.

---

## 2. What Happened In The Latest Run

The last real run completed all 9 text blocks successfully and then emitted:

1. `paragraph_count_mismatch_preserve` with `source_count=65`, `target_count=64`;
2. `paragraph_count_mismatch_normalize` with `source_count=65`, `target_count=64`.

This means:

1. `convert_markdown_to_docx_bytes()` produced a DOCX whose paragraph sequence no longer had a strict 1:1 correspondence with the source paragraph sequence;
2. `preserve_source_paragraph_properties()` refused to apply preserved paragraph XML;
3. `normalize_semantic_output_docx()` refused to apply semantic styles;
4. the final output kept only raw Pandoc-produced paragraph structure plus later image reinsertion.

As a result, all semantic styling downstream became best-effort or absent.

---

## 3. Root Causes

### 3.1. Heading Classification Is Mixing Three Different Concerns

Current paragraph classification in `document.py` merges together:

1. explicit source semantics from style names and `w:outlineLvl`;
2. heuristic visual inference for heading-like body paragraphs;
3. caption disambiguation after extraction.

Relevant code:

1. `_extract_explicit_heading_level()`;
2. `_is_probable_heading()`;
3. `_reclassify_adjacent_captions()`;
4. `classify_paragraph_role()`.

Current failure mode:

1. a paragraph with centered or mostly bold text can be heuristically upgraded to `heading` even when it is author-authored body text used as a visual section label;
2. caption-style paragraphs already have an important safeguard: `_is_caption_style(normalized_style)` blocks heuristic heading promotion for paragraphs explicitly styled as Caption/Подпись;
3. the real failure window is narrower but still important: caption regressions happen when a caption has no caption style, is short plus bold/centered, and is not rescued by the immediate image/table adjacency rule;
4. this heuristic is local and paragraph-only, so similar-looking paragraphs can be classified differently depending on surrounding extraction conditions;
5. `_reclassify_adjacent_captions()` can rescue more than just heuristic-heading candidates: in practice it can reclassify any non-explicit-heading paragraph that immediately follows an `image` or `table` paragraph and looks like a caption;
6. even with that broader rescue path, the protection is still narrow because it only inspects the immediate predecessor and relies on caption-like text prefixes, so it misses caption-like cases once adjacency is disturbed.

Net effect:

1. false-positive headings;
2. inconsistent heading decisions across the same document class;
3. captions that are only protected in a subset of adjacency paths.

### 3.2. Semantic Normalization Is All-Or-Nothing

Both post-processing passes rely on exact positional zip-mapping between source and target paragraphs:

1. `preserve_source_paragraph_properties()`;
2. `normalize_semantic_output_docx()`.

Current behavior:

1. if paragraph counts differ, both passes bail out immediately;
2. no partial mapping is attempted;
3. no diagnostic tells us which paragraph was merged, split, or dropped.

This is safe against misapplication, but too brittle for a generative pipeline.

Net effect:

1. a single merge or split in one block disables formatting restoration for the entire document;
2. headings, captions, and list normalization all disappear together;
3. the system has no structured artifact for debugging the mismatch.

### 3.3. Lists Survive Extraction But Not DOCX-Native Restoration

Current list flow is asymmetric.

What works today:

1. extraction detects Word numbering metadata via `_extract_paragraph_list_metadata()`;
2. `ParagraphUnit.rendered_text` renders markdown list markers;
3. tests confirm markdown list preservation at extraction/rendering time.
4. when paragraph counts still match exactly, `preserve_source_paragraph_properties()` can copy preserved `numPr` XML into the corresponding target paragraph.

What does not work reliably in the final DOCX:

1. after markdown roundtrip, numbering becomes whatever Pandoc reconstructs from plain markdown;
2. `normalize_semantic_output_docx()` only sets `List Paragraph` style for `role == "list"`;
3. `preserve_source_paragraph_properties()` can copy preserved `numPr` XML into the target paragraph, but only under strict source/target paragraph-count equality;
4. even when `numPr` is copied, the Pandoc-generated target DOCX does not necessarily contain the matching `abstractNum` / `num` definitions in `numbering.xml`, so the copied numbering reference can be dangling;
5. `_detect_explicit_list_kind()` also falls back to visible text markers such as `- ` or `1.`; if the model rewrites the item text and removes those markers, list-kind evidence can disappear even when paragraph counts still match;
6. if paragraph-count mismatch occurs, even this weak normalization and the `numPr` copy path are skipped.

Important distinction:

1. a paragraph styled as `List Paragraph` is not equivalent to a real numbered Word list;
2. numbering in Word is paragraph-numbering XML, not just visible text markers.

Net effect:

1. lists may appear flattened into normal paragraphs;
2. numbering continuity and nesting can be lost;
3. even when text contains `1.` markers, the resulting DOCX is not structurally equivalent to the original list;
4. list semantics can also be lost when the LLM removes textual list markers that current detection logic depends on;
5. a formal `numPr` preservation mechanism exists today, but in practice it is too fragile to serve as reliable end-to-end list restoration.

### 3.4. Existing Metadata Separation Is Real, But It Is Coupled To Fragile Positional Mapping

The current architecture already keeps a parallel metadata structure in `source_paragraphs: list[ParagraphUnit]`.

That metadata includes, at minimum:

1. `role`;
2. `heading_level` / `heading_source`;
3. `list_kind` / `list_level`;
4. `preserved_ppr_xml`.

So markdown is not literally the only structural carrier in the pipeline.

The real problem is that this metadata is only usable through strict positional zip-mapping between source and target paragraphs. Once paragraph counts diverge, the metadata becomes effectively unavailable to reconstruction.

This is still lossy for DOCX-specific structure because:

1. paragraph identity is not stable across the LLM roundtrip;
2. list semantics degrade into textual markdown markers unless positional mapping survives intact;
3. caption identity is not carried as a durable reconstruction anchor;
4. paragraph boundaries are not represented in a way that survives merge/split behavior robustly.

---

## 4. Design Goal

Introduce a formatting-reliability layer that separates:

1. **source structural semantics** from DOCX extraction;
2. **editable text content** sent through the model;
3. **stable paragraph identity and block boundaries** across the LLM roundtrip;
4. **final DOCX reconstruction and style restoration**.

This should build on the existing `ParagraphUnit` metadata path rather than replacing it from scratch.

The target outcome is not lossless DOCX roundtripping, but stable preservation of:

1. headings;
2. captions;
3. numbered and bulleted lists;
4. paragraph boundaries where they matter for formatting;
5. predictable output styling even when the model rewrites aggressively.

---

## 5. Proposed Refactor

### 5.1. Introduce Source Structural Roles With Confidence Levels

Replace the current flat paragraph role decision with an explicit structural classification model.

Add to `ParagraphUnit`:

1. `structural_role: Literal["heading", "caption", "list", "image", "table", "body"]`;
2. `role_confidence: Literal["explicit", "adjacent", "heuristic"]`;
3. `paragraph_id: str`;
4. `source_index: int`.

Rules:

1. explicit DOCX semantics always win over heuristics;
2. caption style and caption-prefix after adjacent image/table outrank heading heuristics;
3. body-text paragraphs must not be upgraded to headings from formatting alone unless they pass stronger multi-signal validation.

Heading inference must require at least one of:

1. explicit style mapping;
2. explicit `outlineLvl`;
3. heuristic format plus short-length plus surrounding structural evidence.

Heuristic format alone must not be sufficient.

### 5.2. Add Stable Paragraph Markers For The LLM Roundtrip

Introduce an optional internal paragraph-boundary protocol for target text generation.

Concept:

1. each source paragraph receives a stable marker such as `[[DOCX_PARA_p012]]`;
2. markers are injected into the editable payload in a model-safe form;
3. the model is instructed to preserve markers and edit only paragraph content between them;
4. after generation, output is parsed back into paragraph units using those markers.

Constraints:

1. markers must be unique and impossible to confuse with user text;
2. markers must be stripped before final markdown shown to the user;
3. marker loss or duplication must be validated and retried at block level;
4. the system must have a non-marker fallback path, because marker mutation by the model is a realistic failure mode.

Expected benefit:

1. paragraph identity no longer depends only on blank lines;
2. paragraph count mismatches become diagnosable at block level;
3. reconstruction can preserve source-to-target mapping even when content changes heavily.

Important implementation note:

1. this is the highest-risk part of the design and should be treated as an experiment or opt-in hardening layer, not the first dependency for fixing current regressions.

### 5.3. Split Caption Handling Into A First-Class Structural Path

Captions should not be represented as generic paragraphs with only best-effort later normalization.

Refactor:

1. make caption a first-class structural role from extraction through reconstruction;
2. attach captions to adjacent image/table assets via `attached_to_asset_id` or equivalent linkage;
3. preserve caption identity during block generation and final reconstruction;
4. disallow heading heuristic promotion for any paragraph already classified as caption by explicit or adjacency evidence.

Additional rule:

1. if a paragraph starts with `Рис.`, `Рисунок`, `Figure`, `Таблица`, `Table` and follows an image/table block, it must remain caption unless explicit source heading metadata says otherwise.

### 5.4. Replace All-Or-Nothing Paragraph Remapping With A Mapping Layer

The current `len(source) == len(target)` contract is too brittle.

Replace it with a paragraph mapping phase that operates in this order:

1. exact positional mapping when counts still match;
2. placeholder-anchored mapping for image paragraphs and adjacent caption candidates;
3. exact text normalization match for unchanged short paragraphs;
4. bounded similarity mapping using source metadata anchors such as role, heading level, list metadata, and short text fingerprints;
5. exact marker-based mapping when paragraph markers are present;
6. fallback similarity mapping for diagnostics only, not for silent automatic style application.

Behavior:

1. if high-confidence mapping covers all paragraphs in a block, apply preserved properties and semantic normalization for that block;
2. if only partial mapping is available, apply formatting only to mapped paragraphs and log unmapped ones;
3. emit a machine-readable mismatch artifact instead of only a count warning.

This changes failure mode from document-global skip to localized degradation.

This is the highest-value near-term improvement because it can be implemented on top of the existing `ParagraphUnit` metadata without first introducing marker-dependent generation changes.

### 5.5. Rebuild DOCX Lists As Real Word Numbering, Not Just Styled Paragraphs

`normalize_semantic_output_docx()` must stop treating lists as only `List Paragraph` style.

Introduce a dedicated list restoration phase:

1. capture source numbering metadata during extraction, including:
   1. numbering kind;
   2. nesting level;
   3. relevant `numPr` fragments;
   4. source numbering-chain information needed to rebuild valid `abstractNum` / `num` definitions in the target package;
   5. restart boundaries where detectable;
2. preserve list item identity through paragraph markers;
3. on final DOCX reconstruction, reapply numbering XML to mapped list paragraphs together with the required numbering definitions in `numbering.xml`;
4. use style assignment only as secondary polish, not as numbering restoration.

Important rule:

1. numbered lists must be restored as real Word lists even if visible markdown markers are present.

### 5.6. Separate Content Editing Markdown From Reconstruction Metadata

Stop treating user-visible markdown as the only effective reconstruction source when positional mapping fails.

Introduce two parallel artifacts:

1. **editable markdown text** used for the model and UI preview;
2. **reconstruction metadata graph** carrying source paragraph ids, roles, numbering metadata, asset links, and style hints.

The final DOCX builder should consume both.

This keeps markdown simple while preserving DOCX-native structure outside markdown.

Part of this structure already exists today in `ParagraphUnit`; the refactor should strengthen the linkage and survivability of that metadata instead of inventing a second disconnected model unless proven necessary.

---

## 6. Proposed Code Changes

### 6.1. `models.py`

Extend `ParagraphUnit` with:

1. `paragraph_id`;
2. `source_index`;
3. `structural_role` or refactor existing `role` into a stricter semantic contract;
4. `role_confidence`;
5. preserved list metadata beyond `list_kind` / `list_level`.

Optional:

1. add a dedicated `DocumentParagraphMap` or `ReconstructionParagraph` model to avoid overloading `ParagraphUnit`.

### 6.2. `document.py`

Refactor extraction pipeline:

1. assign stable paragraph ids during ordered block traversal;
2. strengthen heading detection to require multi-signal evidence;
3. make caption classification explicit and irreversible once confidence is explicit/adjacent;
4. capture richer numbering metadata;
5. build paragraph-marker-aware rendering helpers for block generation;
6. replace count-only preserve/normalize guards with paragraph mapping driven by ids.

Add diagnostics:

1. per-block source paragraph count;
2. per-block output paragraph count after marker parse;
3. lost/duplicated paragraph ids;
4. list restoration failures;
5. caption-to-heading conflicts.

### 6.3. `generation.py`

If paragraph markers are enabled, update prompts to enforce paragraph-boundary preservation.

Requirements:

1. preserve paragraph markers exactly;
2. do not merge adjacent paragraphs;
3. do not split one marked paragraph into multiple paragraphs;
4. do not transform markers or move them across paragraphs.

Add block-level validation:

1. parse output markers;
2. reject output with lost/duplicated/out-of-order markers;
3. retry with a stricter recovery prompt before failing.

Do not make marker support a prerequisite for the first reconstruction improvements. Mapping-layer hardening should land first and remain usable even when marker mode is disabled.

### 6.4. `document_pipeline.py`

Refactor final reconstruction sequence:

1. markdown to DOCX conversion;
2. paragraph-marker or metadata-based mapping;
3. preserved paragraph property restoration for mapped paragraphs;
4. semantic normalization for headings, captions, and body;
5. true Word numbering restoration for lists;
6. image reinsertion;
7. final verification artifact generation if mapping gaps remain.

### 6.5. Diagnostics / Artifacts

When formatting reconstruction is degraded, emit a structured artifact under `.run/` or `tests/artifacts/real_document_pipeline/` containing:

1. source paragraph registry with ids, roles, first 120 chars;
2. output paragraph registry with ids if parsed, else plain index + text preview;
3. list of unmapped source paragraphs;
4. list of unmatched target paragraphs;
5. list restoration decisions;
6. caption-heading conflict notes.

This must replace the current opaque `65 -> 64` warning as the primary debugging surface.

---

## 7. Migration Strategy

### Phase 1. Instrumentation First

Do not change user-visible behavior yet.

Add:

1. paragraph ids;
2. richer diagnostics;
3. block-level paragraph count logs;
4. formatting mismatch artifacts.

Goal:

1. make future failures exact instead of count-only.

### Phase 2. Mapping Layer First

Add:

1. partial source-target paragraph mapping without document-global bail-out;
2. image and caption anchors in the mapping logic;
3. exact-match and bounded similarity strategies using existing `ParagraphUnit` metadata;
4. partial formatting application for mapped paragraphs.

Goal:

1. remove the current count-mismatch failure mode without introducing new LLM-side fragility.

### Phase 3. List And Caption Reconstruction Hardening

Add:

1. stronger heading-vs-caption precedence rules;
2. asset-linked caption reconstruction;
3. real numbering restoration or explicit numbering-definition transfer.

Goal:

1. stabilize the highest-value user-visible formatting structures.

### Phase 4. Optional Paragraph Marker Roundtrip

Add:

1. markers in generation payload;
2. output validation;
3. source-target paragraph remapping by id.

Goal:

1. improve paragraph identity guarantees in the cases where marker preservation proves reliable enough in practice.

### Phase 5. Heuristic Heading Tightening

Reduce false-positive heading upgrades.

Goal:

1. body-text section labels are treated consistently;
2. headings become explicit-leaning, not formatting-guess-driven.

---

## 8. Test Plan

Add regression coverage for:

### 8.1. Heading / Body Disambiguation

1. centered bold body-text section labels must not be auto-promoted without stronger evidence;
2. explicit Title / Heading styles must remain headings;
3. identical visual formatting in two locations must classify consistently.

### 8.2. Caption Preservation

1. caption after image remains caption after extraction, generation, markdown roundtrip, and final DOCX reconstruction;
2. caption must not become `Heading 1` or `Heading 2`;
3. table captions follow the same contract;
4. paragraphs explicitly styled as Caption/Подпись remain protected from heading promotion.

### 8.3. Paragraph Mapping Robustness

1. one mismatched paragraph must not disable formatting restoration for the entire document;
2. exact-match and bounded-similarity mapping can recover partial formatting without marker support;
3. when model preserves paragraph markers, formatting passes apply even after heavy textual rewrite;
4. marker loss triggers retry or explicit failure when marker mode is enabled.

### 8.4. List Restoration

1. numbered lists survive end-to-end as real Word lists;
2. nested bullet/numbered combinations preserve level;
3. list continuity is maintained across rewritten text;
4. visible markers alone are not accepted as sufficient if DOCX numbering is absent.

### 8.5. Real Sample Regression

Use `tests/sources/Лиетар глава1.docx` as a protected real-document regression.

Validate at minimum:

1. no caption becomes heading;
2. key section titles are classified consistently;
3. numbered lists are present as Word numbering in final DOCX;
4. formatting mismatch artifact is empty or below an explicit threshold.

---

## 9. Risks And Tradeoffs

1. paragraph markers increase prompt complexity and can themselves become a failure surface if the model mutates them;
2. richer reconstruction metadata adds implementation complexity and more moving parts;
3. restoring real numbering XML is more difficult than applying paragraph styles;
4. partial mapping must be conservative to avoid misapplying heading or caption styles to the wrong text.

Priority note:

1. mapping-layer hardening and better diagnostics have the highest ROI and lowest delivery risk;
2. marker-based identity preservation is useful but should not block earlier reconstruction fixes.

These tradeoffs are acceptable because the current architecture already demonstrates that plain markdown roundtrip is not strong enough for DOCX formatting fidelity.

---

## 10. Acceptance Criteria

This refactor is complete when all of the following are true:

1. image and table captions never silently upgrade to headings in protected regressions;
2. body-text section labels are classified consistently across repeated patterns;
3. numbered lists survive end-to-end as actual Word numbering, not only visible text markers;
4. final formatting restoration is no longer document-global all-or-nothing on a single paragraph mismatch;
5. any remaining mapping failures produce precise machine-readable diagnostics instead of only count warnings;
6. `Лиетар глава1.docx` passes a real-document validation run without the current formatting regressions.

---

## 11. Recommended Scope Boundary

This work should be treated as one cohesive formatting-reliability initiative, not as three isolated hotfixes.

Do not fix only:

1. caption-vs-heading heuristics;
2. or only list styling;
3. or only paragraph-count mismatch logging.

Those are symptoms of the same underlying architectural gap: missing stable paragraph identity and weak separation between editable markdown and reconstruction metadata.

The correct solution is a targeted refactor of the DOCX extraction -> generation -> reconstruction contract.

In practical delivery terms, that refactor should start with instrumentation and mapping over the metadata that already exists today, then add higher-risk identity-preservation mechanisms only if they prove necessary.