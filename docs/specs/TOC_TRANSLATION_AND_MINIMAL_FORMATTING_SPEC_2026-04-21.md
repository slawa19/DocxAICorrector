# TOC Translation And Minimal Formatting Spec

Date: 2026-04-21
Status: Implemented and verified on 2026-04-22
Scope type: document-structure translation and post-Pandoc formatting hardening
Primary inputs:

- latest Mariana Mazzucato UI run analysis on 2026-04-21
- final UI artifacts under `.run/ui_results/20260421_153724_...`
- formatting diagnostics artifact `.run/formatting_diagnostics/restore_1776785843759.json`
- current semantic block grouping in `document_semantic_blocks.py`
- current formatting replay behavior in `formatting_transfer.py`
- current output-validation expectations in `tests/test_document_pipeline_output_validation.py`
- existing translation-quality work in `docs/specs/TRANSLATION_QUALITY_AND_SECOND_PASS_SPEC_2026-04-20.md`

## 1. Purpose

This specification defines a focused follow-up workstream for three linked defects revealed by the latest UI translation run:

1. table-of-contents regions are detected, but translation quality for TOC lines is unreliable and often falls back to source-language output;
2. semantic or promoted headings can inherit direct paragraph alignment from the source DOCX, causing visually wrong right-aligned headings in the result;
3. the current post-Pandoc formatter still replays more source-specific geometry than the product should preserve by default.

The intended direction is reference-DOCX-first and minimal post-formatting, not broader source-style replay.

Implementation closure note:

1. TOC-dominant translate blocks now route deterministically through a dedicated `toc_translate` prompt path.
2. Deterministic TOC validation plus bounded retry rejects unchanged TOC output before DOCX assembly.
3. Preparation and cache seams now preserve operation-aware TOC planning behavior.
4. Direct paragraph alignment replay is guarded by explicit allowlist rules and heading protection.
5. Formatter diagnostics now record alignment restoration decisions alongside existing mismatch and list-restoration artifacts.
6. Regression coverage includes pure-TOC routing, mixed TOC-dominant routing, dedicated TOC terminal failure, heading/list alignment deny cases, and constrained list/table preservation behavior.

## 2. Problem Statement

The latest Mariana Mazzucato run exposed a split failure mode:

1. prose quality improved materially after the recent translation work;
2. TOC-like regions remained mostly untranslated or partially untranslated;
3. at least one body subheading was promoted to `Heading 2` yet rendered right-aligned;
4. the result therefore looks semantically inconsistent even when the core body translation is stronger.

Verified run facts:

1. the latest relevant UI output is `.run/ui_results/20260421_153724_The_Value_of_Everything_Making_and_Taking_in_the_Global_Economy_by_Mariana_Mazzu.result.docx` plus the paired markdown artifact;
2. the run log shows structure AI escalation with `toc_like_sequence_detected` and `ai_heading_count = 2`, so the TOC problem is not “structure was never detected”;
3. the same run also emitted a formatting-diagnostics mismatch artifact with `source_count = 161`, `target_count = 153`, `mapped_count = 150`, `unmapped_source_count = 11`, and `unmapped_target_count = 3`;
4. the source OOXML for the real body heading `WHAT IS VALUE?` already contains `w:jc="end"`, and the formatter replays that direct alignment into the final result.

## 3. Goals

This work must achieve the following:

1. make TOC headers and TOC entries translate reliably when `processing_operation = translate`;
2. preserve TOC ordering, numbering, and page-reference-like tokens without forcing the model to treat TOC lines like normal prose;
3. prevent direct alignment replay from pushing semantic headings to the wrong visual edge;
4. move the formatter closer to the intended minimal-output contract: keep only the source formatting that is product-relevant and structurally safe;
5. add automated checks that catch untranslated TOC output and heading-alignment regressions before DOCX assembly is accepted.

### 3.1 Binding implementation decisions

The following decisions are fixed by this specification and must not be left to local implementation guesswork:

1. lists remain part of the minimal product contract and must be preserved as structural content in final markdown and DOCX output;
2. tables remain part of the minimal product contract and must be preserved with baseline readable output styling;
3. target reference-DOCX defaults are the canonical styling baseline for headings, body paragraphs, and list appearance unless a narrow whitelist exception explicitly overrides them;
4. direct alignment replay is not a general formatting recovery mechanism and must be guarded by an explicit allowlist;
5. TOC validation is deterministic and heuristic, not an extra LLM review pass;
6. mixed TOC/prose blocks must choose the TOC-preserving path when TOC paragraphs are the clear majority;
7. source numbering XML, if still needed temporarily, is a narrow compatibility fallback rather than an architectural source of truth.

## 4. Non-Goals

This spec does not authorize the following:

1. a full outline-reconstruction engine for Word TOCs;
2. document-wide layout redesign or template replacement;
3. broad restoration of source paragraph XML beyond the already accepted minimal formatter contract;
4. replacing the current block pipeline with whole-document generation;
5. changing the already implemented translation second-pass feature as part of this work.

## 5. Current State

### 5.1 TOC detection already exists

Current verified behavior:

1. relation normalization already groups contiguous TOC paragraphs into `toc_region` relations;
2. semantic block building already keeps TOC clusters together rather than interleaving them with arbitrary body text;
3. structure recognition already uses `toc_header` and `toc_entry` as valid structural roles;
4. the latest Mariana run showed successful TOC-like detection and AI involvement.

Implication:

1. the next defect is downstream of detection;
2. this is primarily a translation-path and acceptance-path problem, not a first-order structure-recognition problem.

### 5.2 TOC translation is not specialized enough

Current verified behavior:

1. formatting diagnostics show source paragraphs in the TOC region tagged as `toc_header` and `toc_entry`;
2. the corresponding target registry entries remain `Body Text` with untranslated English text previews such as `contents`, `preface: stories about wealth creation`, and `introduction: making versus taking`;
3. current output validation already tolerates aggressive shape changes for TOC-like lines, including heading-only output for a table-of-contents line.

Implication:

1. the pipeline currently has too little TOC-specific generation discipline and too little TOC-specific acceptance validation;
2. the system is allowing structurally valid but linguistically wrong TOC output to pass.

### 5.3 Direct alignment replay is broader than it should be

Current verified behavior:

1. the post-Pandoc formatter intentionally remains minimal and currently restores direct paragraph alignment for mapped pairs;
2. `_restore_direct_paragraph_alignment_for_mapped_pairs(...)` replays `source_paragraph.paragraph_alignment` without filtering by semantic role or normalized target style;
3. this behavior previously closed a real-document regression for short centered paragraphs, so the alignment replay is not accidental dead code;
4. however, it now causes promoted or normalized headings to inherit source-specific geometry such as `w:jc="end"`.

Implication:

1. the formatter needs a narrower allowlist, not wholesale removal of alignment restoration;
2. “minimal formatter” in practice is still too permissive for headings.

### 5.4 Default-document styling is the intended baseline

Current verified behavior from docs and code:

1. Pandoc plus the dynamic reference DOCX are supposed to be the primary styling source for headings, body text, and lists;
2. the formatter was already simplified away from broad paragraph XML replay;
3. the current issue shows that direct alignment replay is one of the remaining excess behaviors when applied to semantically normalized headings.

Decision basis:

1. the correct default is to keep document/template defaults unless there is a product-aligned reason to restore a source-side direct override;
2. this change should continue the earlier simplification rather than undo it.

## 6. Root Cause Summary

### 6.1 TOC defect

The TOC is already detected and grouped, but later stages still treat it too much like generic body content.

Practical consequence:

1. the model is not given a dedicated TOC contract;
2. acceptance logic does not reject high-source-language leakage inside a translated TOC region;
3. the final DOCX therefore accepts semantically grouped but linguistically wrong TOC output.

### 6.2 Heading-alignment defect

The system correctly promotes or styles a paragraph as a heading, then incorrectly re-applies source direct alignment afterward.

Practical consequence:

1. the semantic output says “this is a heading”;
2. the formatter then says “but keep the source right/left edge geometry anyway”;
3. short or pseudo-centered headings visibly drift to the wrong side.

### 6.3 Contract drift in formatter scope

The formatter’s documented minimal role and its real behavior are no longer perfectly aligned.

Practical consequence:

1. the system still behaves as if some source-local geometry is universally trustworthy;
2. that assumption is false once semantic normalization changes paragraph roles or heading levels.

## 7. Proposed Product Behavior

## 7.1 Dedicated TOC translation path

When a block is wholly or primarily a TOC cluster in translate mode:

1. the system must use a TOC-specific prompt contract;
2. the model must translate entry titles, not rewrite them as prose;
3. the model must preserve order and line boundaries as strictly as possible;
4. the model must preserve numbering prefixes and page-reference-like suffixes if they exist;
5. the model must not add commentary, summaries, or explanatory transitions.

Recommended prompt posture:

1. “translate each line as a TOC entry, not as narrative text”;
2. “keep one output line per input line unless the input line already contains an inline forced break contract”;
3. “preserve numbering, roman numerals, chapter markers, and page references”.

### 7.1a Mixed TOC/prose block policy

Mixed blocks must not fall into ambiguous behavior.

Required behavior:

1. if all paragraphs in the block are `toc_header` or `toc_entry`, always route through the TOC-specific path;
2. if TOC-tagged paragraphs are the clear majority, route through the TOC-specific path and preserve non-TOC spillover lines conservatively rather than treating the whole block as prose;
3. if the block is genuinely mixed without a clear TOC majority, prefer conservative splitting when the current seam allows it; otherwise choose the safer TOC-preserving path;
4. do not route a TOC-dominant block through the generic prose prompt just because one or two lines are noisy or weakly classified.

Recommended default threshold:

1. treat the block as TOC-dominant when at least 70 percent of its paragraphs are `toc_header` or `toc_entry`, or when all non-TOC lines are short separators or obvious spillover lines;
2. if implementation constraints require a different deterministic threshold, document it in code comments and tests.

### 7.2 Alignment guard for promoted or normalized headings

Direct paragraph alignment must not be replayed blindly.

Required behavior:

1. if the target paragraph is a semantic heading or has a heading style applied through normalization, do not restore source `jc=start/end/both` by default;
2. allow center restoration only where the product explicitly needs it and where the target paragraph remains a non-heading centered short paragraph or another approved category;
3. prefer reference-DOCX default heading alignment for normalized headings;
4. preserve existing image-placeholder centering and other already accepted minimal special cases.

Decision rule:

1. heading semantics win over source-side direct alignment;
2. source alignment replay becomes opt-in by safe category rather than opt-out by exception.

### 7.3 TOC-specific language validation before DOCX assembly

Translated TOC blocks need a lightweight acceptance gate.

Required behavior:

1. after generation and before final DOCX acceptance, evaluate TOC regions for source-language leakage;
2. if a translated TOC region still contains too many source-language lines, reject and retry that block with the TOC-specific contract;
3. the gate should tolerate proper names, titles that legitimately remain unchanged, and acronyms;
4. the gate should be cheaper and narrower than full semantic validation.

Practical heuristic examples:

1. high ratio of unchanged English TOC lines in an `en -> ru` run;
2. `Contents` left untranslated in a block tagged with `toc_header`;
3. multiple `toc_entry` lines that remain nearly identical to source outside an allowlisted set.

### 7.3a TOC retry and failure contract

TOC validation must have a bounded retry policy.

Required behavior:

1. on the first validation failure for a TOC block, retry that block once with the TOC-specific contract if the first attempt did not already use it;
2. if the first attempt already used the TOC-specific contract, allow at most one focused retry with the same contract and stricter preservation instructions if the current execution seam supports that without new architecture;
3. after the retry budget is exhausted, return a normal pipeline failure result rather than silently accepting a linguistically wrong TOC block;
4. failure reporting must identify TOC-language validation as the rejection reason.

Out-of-scope behavior:

1. this spec does not require a second LLM acting as a TOC critic;
2. this spec does not authorize indefinite retries or whole-document restart because one TOC block failed validation.

## 8. Architectural Approach

### 8.1 Respect the existing semantic seams

This work should use current seams rather than patching random call sites.

Preferred implementation direction:

1. keep TOC grouping in relation normalization and semantic block building as-is unless a verified defect requires adjustment;
2. introduce TOC-specific generation behavior at the block-execution or prompt-resolution layer, not by DOM/CSS-like DOCX post-fixes;
3. implement heading-alignment protection inside `formatting_transfer.py`, because that is where the unsafe replay currently happens;
4. implement TOC validation before DOCX assembly, not as a manual post-hoc visual check.

### 8.2 Keep formatter minimal

The formatter should continue moving toward a small, product-aligned contract.

Allowed formatter responsibilities after this work:

1. image-placeholder centering;
2. minimal caption formatting;
3. safe list-number restoration for mapped pairs;
4. safe direct alignment restoration only for explicitly approved non-heading categories;
5. safe semantic heading normalization.

Disallowed direction:

1. broad re-expansion into source paragraph XML replay;
2. generalized restoration of arbitrary source paragraph geometry for all mapped paragraphs.

### 8.3 Minimal-formatting policy checklist

The implementation must treat structural preservation and source-style replay as different categories.

Keep by default:

1. headings and heading levels, because they are core semantic structure and should resolve through target default heading styles rather than source paragraph geometry;
2. body paragraphs, because they are the baseline content model and should inherit target-document defaults unless a narrow exception is explicitly approved;
3. ordered and unordered lists with nesting, because lists are minimal document structure rather than style noise;
4. tables, because table structure is product-relevant content and belongs in the minimal output contract;
5. images and captions, because they are already accepted structural/minimal-formatting exceptions;
6. safe inline emphasis such as bold, italic, underline, superscript, subscript, hyperlinks, and line breaks, because these are semantic text-level signals rather than paragraph-geometry replay.

Drop from the default path:

1. source paragraph style names, because target reference-DOCX defaults should determine final style families;
2. direct paragraph-property replay beyond explicitly approved cases, because it reintroduces source-local layout noise;
3. source tab stops, left or right indents, spacing values, and similar paragraph geometry, because they are not part of the minimal semantic contract;
4. custom source fonts, colors, and local style hierarchies, because the product should not drag the source style zoo into the result document by default;
5. blind direct alignment replay for all mapped paragraphs, because semantic normalization can legitimately change the correct visual alignment.

Allow only as explicit whitelist exceptions:

1. center alignment for image-only blocks, image placeholders, and other already accepted minimal special cases;
2. narrowly approved centered short non-heading paragraphs where a verified regression shows that target defaults are insufficient;
3. baseline target-side table styling such as `Table Grid` when used as a canonical output normalization rather than as source-style replay;
4. list rendering compatibility shims only to the extent required to preserve list semantics reliably.

Additional decision for lists:

1. the product must preserve list semantics, nesting, and ordered-vs-unordered intent;
2. preserving list structure does not automatically justify preserving source Word numbering XML as a default behavior;
3. if source numbering XML remains in the implementation, it must be treated as a narrow compatibility mechanism rather than as the styling model for the result document.

Additional decision for tables:

1. the product must preserve table structure and readable baseline styling;
2. preserving tables does not justify replaying source-specific table themes, custom palette choices, or local table-layout quirks by default.

## 9. Detailed Design

### 9.1 TOC-aware prompt routing

Introduce one explicit TOC-oriented prompt variant for translate mode.

Recommended shape:

1. keep the normal translation prompt for prose blocks;
2. add a dedicated prompt variant such as `toc_translate` or equivalent internal routing;
3. the variant may reuse the common system prompt shell but must inject TOC-specific operation instructions and examples;
4. examples should include:
   - `Contents` -> `Содержание`
   - chapter/section entry lines
   - entries containing punctuation, subtitles, and page markers.

Routing rule:

1. when all or nearly all paragraphs in a block are `toc_header`/`toc_entry`, use the TOC prompt variant;
2. if a block mixes TOC and non-TOC content unexpectedly, either split more conservatively or explicitly choose the safer TOC-preserving path.

Implementation contract:

1. routing must be driven by structural roles already present in paragraph units or semantic blocks, not by loose regex-only text guessing;
2. the routing helper must be deterministic and independently unit-testable;
3. prompt selection must be inspectable in logs so a failed real-document run can confirm whether TOC routing was actually used.

### 9.2 TOC output validation contract

Add a small validation helper dedicated to translated TOC blocks.

Required contract:

1. input: source paragraphs, generated text, source language, target language, and block structural makeup;
2. output: accept, retryable-failure, or hard-failure if the shape is irrecoverably broken;
3. for now, validation should remain deterministic and heuristic rather than requiring another LLM call.

Recommended checks:

1. TOC header translated or explicitly allowlisted;
2. too many unchanged source lines triggers retry;
3. paragraph-count or line-count drift beyond TOC tolerance triggers retry;
4. page references and numbering patterns still present when they existed in source.

Authoritative validation rules for `en -> ru` and analogous translation runs:

1. normalize lines by trimming whitespace, collapsing repeated spaces, and ignoring trailing page-number spacing differences;
2. treat proper names, acronyms, roman numerals, and pure page-reference tokens as allowlisted unchanged fragments;
3. fail validation when a `toc_header` line remains identical to source and is not allowlisted;
4. fail validation when two or more substantive `toc_entry` lines remain effectively unchanged from source in a block that contains at least three substantive TOC lines;
5. fail validation when numbering or page-reference-like suffixes disappear from multiple lines that had them in source;
6. tolerate minor punctuation drift if entry titles clearly translated and line ordering is preserved;
7. validation must operate on generated block text before DOCX assembly and must not depend on manual inspection.

Substantive-line rule:

1. a substantive TOC line is a non-empty line that is not only a page number, delimiter, roman numeral marker, or decorative punctuation;
2. the implementation may use a helper for this classification, but the helper must remain deterministic and test-covered.

### 9.3 Alignment replay guard

Narrow `_restore_direct_paragraph_alignment_for_mapped_pairs(...)`.

Required logic:

1. inspect both source semantic role and target normalized role/style;
2. skip restoring direct alignment when the target paragraph is a heading or when the source paragraph was promoted/normalized into a heading;
3. keep restoring center alignment for product-approved categories such as image placeholders and verified centered short paragraphs when still semantically appropriate;
4. skip restoring `start`, `end`, or `both` when they would override default heading geometry.

Recommended rule shape:

1. implement a small helper like `_should_restore_direct_alignment(source_paragraph, target_paragraph) -> bool`;
2. keep the rule explicit and conservative;
3. do not hide semantic exceptions inside a large generic mapping heuristic.

Authoritative allowlist:

1. center alignment may be restored for image-only paragraphs, image-placeholder paragraphs, and similarly narrow existing product-approved non-heading cases;
2. center alignment may be restored for verified short non-heading paragraphs only if accepted tests or real-document evidence require it;
3. alignment must not be restored when the target paragraph has a heading style, is semantically classified as a heading, or was promoted into a heading during normalization;
4. `start`, `end`, and `both` must not be replayed onto normalized headings under any default-path behavior;
5. if category membership is uncertain, the safe default is to skip restoration rather than restore it.

Short-paragraph compatibility rule:

1. “short non-heading paragraph” must be defined in code by an explicit, test-covered heuristic rather than informal intuition;
2. that heuristic must not match TOC headers, semantic headings, captions already handled by dedicated styling, or list items.

### 9.3a List and table preservation boundary

The implementation should make the keep-vs-replay boundary explicit for lists and tables.

Required logic:

1. preserve lists because they are structural content, not because the source document's numbering XML is inherently authoritative;
2. prefer target-side list rendering defaults where feasible, while allowing a narrow fallback only if required for reliable ordered-list output;
3. preserve tables because they are structural content, while limiting formatting to baseline readable output styling;
4. avoid expanding list or table handling into a new source-style replay channel.

Binding list policy:

1. ordered-vs-unordered intent and nesting depth are the source of truth for list preservation;
2. source numbering XML may remain temporarily only if the current renderer still needs it for stable ordered-list DOCX output;
3. if source numbering XML is used, it must be applied narrowly to list paragraphs only and must not justify replaying other paragraph geometry;
4. implementation work under this spec must not expand numbering XML reuse beyond current list-preservation needs;
5. future work that removes numbering XML fallback entirely is compatible with this spec and does not require product-direction changes.

Binding table policy:

1. preserve table structure, cell content, and readable baseline borders or grid styling;
2. do not preserve source-specific table themes, palette choices, or local Word style hierarchies by default;
3. baseline target-side styling such as `Table Grid` is acceptable only as output normalization rather than as source-style replay.

### 9.4 Acceptance and diagnostics

The system must stay inspectable.

Required diagnostics additions:

1. log when a TOC block uses the TOC-specific prompt path;
2. log when TOC validation rejects a block and forces retry;
3. extend formatting diagnostics or runtime logs to show when heading-alignment replay is intentionally skipped due to semantic-heading protection.

Recommended diagnostic payload shape:

1. TOC-routing diagnostics should include block identifier, structural-role summary, selected prompt variant, and retry attempt number if any;
2. TOC-validation rejection diagnostics should include the rejection reason category such as unchanged-header, too-many-unchanged-lines, or lost-page-markers;
3. alignment-skip diagnostics should include the source paragraph id when available, the source alignment value, and the reason replay was denied.

These diagnostics do not need to become a stable external API, but they must be structured enough for real-document debugging.

### 9.5 Pseudocode-level execution contract

The intended execution order for a translated TOC-capable block is:

1. build or receive the semantic block with paragraph structural roles already assigned;
2. choose prompt routing deterministically using structural-role composition;
3. generate translated block text;
4. run TOC-specific validation when the block is TOC-routed or TOC-dominant;
5. retry within the bounded retry policy if validation fails;
6. only after block acceptance, continue normal markdown aggregation and DOCX assembly;
7. during post-Pandoc formatting, apply the heading-alignment guard before any direct alignment replay can override normalized heading behavior.

Any implementation that preserves this ordering is acceptable even if helper names or file seams differ slightly.

## 10. Files Expected To Change

Primary implementation files likely affected:

1. `document_pipeline_block_execution.py`
2. `document_pipeline_output_validation.py` or the current equivalent output-validation seam if naming differs
3. `document_pipeline_support.py` and/or prompt-resolution helpers if a new prompt variant is introduced
4. `config.py` if prompt composition gains a TOC-specific variant
5. `prompts/operation_translate.txt` only if the shared translation contract needs minor TOC guardrails
6. new prompt/example fragments for TOC translation if routing is prompt-variant based
7. `formatting_transfer.py`
8. `tests/test_document_pipeline_output_validation.py`
9. `tests/test_document_pipeline.py`
10. formatter-focused tests such as `tests/test_formatting_transfer.py` if present, otherwise a new targeted test file
11. `README.md` and/or relevant docs if user-visible behavior or diagnostics need documentation

## 11. Test Plan

### 11.1 TOC translation tests

Add or update tests to cover:

1. `Contents` becomes `Содержание` in `en -> ru` translation mode;
2. TOC entry lines translate while preserving order and numbering;
3. TOC blocks are retried or rejected when too many lines remain unchanged in the source language;
4. mixed TOC/prose edge cases choose the safe path;
5. TOC-dominant blocks route to the TOC prompt path even when one or two non-TOC spillover lines exist.

### 11.2 Heading alignment tests

Add or update tests to cover:

1. source `jc=end` is not replayed onto a paragraph that is normalized into `Heading 2`;
2. centered short non-heading paragraphs still preserve center alignment where required by the accepted real-document contract;
3. existing image-placeholder and caption behavior does not regress;
4. list items do not get accidentally swept into the short-centered-paragraph compatibility path.

### 11.3 Integration tests

Add or update tests to cover:

1. a real or synthetic TOC cluster round-trips through translate mode with translated entries in final markdown;
2. semantic headings keep template-default alignment in final DOCX even when source direct alignment differs;
3. formatting diagnostics still emit useful mismatch artifacts when structural drift occurs;
4. a TOC-validation failure is observable in runtime diagnostics and does not degrade into a silent success.

### 11.4 Deterministic-helper tests

Add small unit tests for any new deterministic helpers such as:

1. TOC-dominance routing decision;
2. substantive TOC-line detection;
3. unchanged-line comparison with allowlisted fragments;
4. direct-alignment allowlist or denylist helper.

### 11.5 Suggested verification commands

Targeted verification should at minimum include:

1. `bash scripts/test.sh tests/test_document_pipeline.py -q`
2. `bash scripts/test.sh tests/test_document_pipeline_output_validation.py -q`
3. `bash scripts/test.sh tests/test_config.py -q` if prompt routing changes touch config composition
4. formatter-focused test file once the implementation file is finalized

If the user asks for a visible final verification path in VS Code and an existing task fits the scope, use the matching repo pytest task rather than relying on agent-only shell capture.

## 12. Risks And Tradeoffs

1. if the alignment guard is too aggressive, previously fixed centered-short-paragraph regressions may return;
2. if TOC validation is too strict, legitimate untranslated proper names or mixed-language entries may cause noisy retries;
3. if TOC prompt routing is too broad, some short non-TOC clusters may be treated as TOC and lose prose quality;
4. if the formatter tries to solve TOC translation failures post hoc, the implementation will drift back toward the wrong architecture.

Mitigation strategy:

1. keep TOC routing based on verified structural roles, not on loose text heuristics alone;
2. keep the alignment allowlist explicit;
3. add real-document-style regression fixtures for both centered paragraphs and TOC fragments.

Additional implementation cautions:

1. do not solve untranslated TOC lines by weakening acceptance until English leakage passes;
2. do not solve heading misalignment by disabling all alignment restoration globally, because that would knowingly re-open previously fixed centered-paragraph regressions;
3. do not let list-preservation work expand into general paragraph-geometry replay.

## 13. Acceptance Criteria

This spec is complete when all of the following are true:

1. TOC headers and TOC entries in translate mode reliably translate in final markdown and final DOCX output;
2. promoted or semantic-normalized headings no longer drift right because of source `jc=end/start` replay;
3. the formatter continues to preserve only product-aligned alignment behavior rather than broad source geometry;
4. automated tests cover TOC translation, TOC validation, and heading-alignment protection;
5. lists and tables remain preserved as minimal structural content while source-specific style replay remains constrained;
6. the implementation contains an explicit deterministic routing and validation seam for TOC blocks rather than hidden prompt-side heuristics only;
7. documentation reflects the refined minimal-formatting contract if the implementation changes that contract in a user-meaningful way.

## 14. Recommended Execution Order

Implement in the following order:

1. add formatter alignment guard with narrow tests first, because that defect is deterministic and low-ambiguity;
2. add TOC-specific translation prompt routing;
3. add TOC-specific language validation before DOCX assembly;
4. add integration tests and, if needed, minimal documentation updates;
5. validate against the Mariana-like TOC scenario before considering any broader structure-recognition changes.

This order keeps the work close to the real defects and avoids broad speculative changes to structure recognition or formatting restoration.

## 15. Explicitly Deferred Work

The following work is intentionally out of scope for this implementation even if it becomes tempting during coding:

1. replacing Pandoc or building a custom Markdown-to-DOCX renderer;
2. full Word TOC reconstruction including dynamic field regeneration;
3. template redesign beyond the current reference-DOCX-driven styling model;
4. document-wide language-quality re-review unrelated to TOC blocks;
5. a larger refactor that removes paragraph mapping from every formatter path in one step.

These items may become later follow-up work, but they are not prerequisites for implementing this specification.