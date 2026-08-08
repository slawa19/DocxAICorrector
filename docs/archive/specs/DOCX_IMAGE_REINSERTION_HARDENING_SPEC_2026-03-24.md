# Image Delivery And Reinsertion Hardening Spec

Date: 2026-03-24
Status: Proposed
Scope type: targeted architecture and correctness hardening
Primary input: code review of image insertion, semantic output restoration, and reinsertion flows on 2026-03-24

## 1. Problem Statement

The current image delivery path is feature-complete enough to support the product workflow, but the implementation has accumulated three different classes of responsibility:

- semantic output restoration after model-driven image edit/generate steps;
- safe single-image placeholder replacement inside existing paragraph/run structure;
- synthetic multi-variant block generation for compare-all and preserve-all review modes.

The single-image reinsertion path is relatively stable. The multi-variant path is structurally more fragile because it rewrites one placeholder paragraph into multiple generated block paragraphs and currently achieves that by cloning source paragraph properties aggressively.

There is also a validated geometry bug in the structured semantic redraw path: the primary `Images.edit` restore flow prepares a square edit canvas, then restores the result by cropping back to the original rectangle and optionally applying `ImageOps.fit(...)`. That means the conservative structured mode can still lose valid edge content when the model legitimately expands spacing or shifts content toward the canvas boundaries.

That creates five concrete risks:

1. valid structured redraw content can be cropped away during semantic output restoration;
2. excess formatting inheritance from the placeholder paragraph into synthetic image blocks;
3. unnecessary repeated variant-resolution work in hot reinsertion paths;
4. fallback behavior that is safe against corruption but weak diagnostically when multi-variant insertion cannot be completed cleanly.
5. source Word crop semantics may be silently dropped because crop metadata is not yet treated as an explicit extraction/reinsertion contract.

This specification defines a narrow hardening pass that keeps the existing product contract intact while making image restoration and reinsertion logic easier to reason about, cheaper to execute, and less likely to produce geometry loss or formatting drift in real DOCX outputs.

## 2. Goals

1. Preserve the stable behavior of single-image reinsertion.
2. Separate inline replacement behavior from synthetic multi-variant block generation as explicit contracts.
3. Add an explicit geometry-safe restoration contract for semantic image output, especially the primary structured `Images.edit` path.
4. Eliminate unnecessary paragraph-format inheritance for generated multi-variant image blocks.
5. Reduce repeated `resolve_image_insertions()` work in reinsertion hot paths.
6. Improve diagnostics when multi-variant placeholders cannot be resolved into final output safely.
7. Add regression coverage for formatting-sensitive multi-variant scenarios.
8. Make the repository’s stance on source Word crop metadata explicit so the refactor does not claim closure while leaving that boundary ambiguous.

## 3. Non-Goals

This spec does not authorize the following:

- redesigning image generation, validation, or compare-panel UI behavior;
- changing model choice or forcing `semantic_redraw_structured` onto one internal route if multiple routes can satisfy the same visible contract;
- changing the product decision that compare-all output DOCX contains all generated variants;
- changing placeholder syntax or upstream `ImageAsset` preparation semantics;
- broad refactoring across unrelated document extraction or formatting-transfer modules;
- lossless preservation of every source DOCX paragraph property in synthetic image-only output blocks.

## 4. Protected Contracts

The following repository contracts remain in force throughout this work:

1. Compare-all contract: final DOCX may contain all generated image variants for review workflows.
2. Startup performance contract in `docs/STARTUP_PERFORMANCE_CONTRACT.md`.
3. Existing WSL/bash test workflow and visible verification requirement via VS Code tasks.
4. Existing single-image placeholder replacement behavior for body paragraphs, table cells, headers, footers, and textboxes.
5. Existing image metadata behavior that stores variant labels in image description metadata rather than visible document body text.
6. `docs/WORKFLOW_AND_IMAGE_MODES.md` remains the source of truth for user-visible image mode intent and delivery semantics.
7. Internal square-canvas preparation is allowed, but it must not become a visible crop defect in the final delivered image merely because the restoration helper reimposes the original rectangle too aggressively.

Any change that pressures one of these contracts must be explicitly called out in implementation and verification notes.

## 5. Current-State Findings in Scope

This spec is driven by validated findings in `image_generation.py`, `image_reinsertion.py`, and related tests.

### IDR-001: Structured semantic edit restoration can crop valid edge content

The primary `semantic_redraw_structured` path prefers direct `Images.edit`. That flow prepares a square canvas, restores with a scaled `crop_box`, and can then apply `ImageOps.fit(...)`. This creates a real content-loss path for diagrams whose regenerated content legitimately expands toward the edge of the square canvas.

### IDR-002: Generated-image anti-crop coverage currently protects the fallback path better than the primary path

There is focused coverage for preserving edge content in the structured generate fallback path, but not an equivalent regression that proves the primary structured edit path cannot crop away valid edge content.

### IR-001: Multi-variant block generation clones too much paragraph formatting

Current behavior clones the source paragraph `pPr` and applies it to every generated image-only paragraph. This is too broad for synthetic blocks and can copy list semantics, pagination flags, indentation, or other paragraph-level properties that were meaningful for the original placeholder paragraph but not for generated image variants.

### IR-002: Multi-variant insertion changes paragraph structure without a narrow formatting contract

The current compare-all and preserve-all flows split one paragraph into several sibling paragraphs. That is acceptable as a product behavior, but it is currently implemented as a low-level XML rewrite rather than as an explicit block contract with minimal formatting rules.

### IR-003: Variant resolution work is repeated unnecessarily

`resolve_image_insertions()` is called multiple times for the same asset across strategy selection and output construction in the same reinsertion flow.

### IR-004: Fallback paths are safe but diagnostically weak

When multi-variant placeholders fall through to paragraph-level helpers that only support one final image, the placeholder may be left as text without a dedicated warning that explains the multi-variant-specific reason.

### IR-005: XML targeting for description metadata is broader than necessary

The current metadata helper uses a broad descendant XPath lookup for `wp:docPr`. It works in normal cases but is looser than necessary for a run-scoped image insertion helper.

### IR-006: Coverage is strong on containers, but weak on formatting drift for synthetic blocks

The test suite already covers split-run placeholders, hyperlinks, headers, footers, textboxes, and compare-all insertion. It does not yet sufficiently protect against list-numbering, keep-with-next, or other paragraph-format inheritance leaking into generated multi-variant blocks.

### IDR-003: Source Word crop semantics are not yet a first-class boundary contract

The current extraction and reinsertion code preserves drawing extents, but it does not yet model source crop semantics such as OOXML crop metadata as an explicit repository contract. That leaves an adjacent class of apparent “image clipping” bugs ambiguous during refactoring unless the implementation either supports that metadata or explicitly logs and documents the current non-support boundary.

## 6. Design Principles

Implementation must follow these principles:

1. Treat image delivery as an end-to-end contract from semantic output restoration through DOCX reinsertion, not as two unrelated local optimizations.
2. Treat multi-variant reinsertion as a block-generation concern, not as an extension of inline single-image replacement.
3. Preserve source formatting only where it remains semantically correct after block synthesis.
4. Prefer one resolved insertion set per asset per reinsertion pass over repeated re-derivation.
5. Fail safely, but log specifically enough that unresolved output can be diagnosed from runtime evidence.
6. Keep OOXML mutation localized and explicit; avoid broad cloning when a narrow helper is sufficient.
7. Preserve current behavior first unless a formatting regression is already the problem being solved.
8. Do not allow an internal square-canvas edit helper to silently redefine the visible crop contract for structured redraw.
9. If source Word crop metadata is not implemented, the code and spec must say so explicitly rather than accidentally implying full fidelity.

## 7. Current Behavior Model

## 7.1 Inline Single-Image Reinsertion

This path handles:

- ordinary image placeholders inside a standalone paragraph;
- placeholders inside existing runs;
- placeholders split across multiple runs;
- placeholders inside table cells, headers, footers, and textboxes.

This path should continue to preserve surrounding paragraph/run structure as much as possible.

## 7.2 Multi-Variant Reinsertion

This path currently handles:

- compare-all output where multiple prepared variants must be embedded into the DOCX;
- preserve-all review output where safe plus candidate variants are emitted together.

This path is structurally different from inline reinsertion. It creates synthetic output blocks and should therefore have its own explicit formatting and logging contract.

## 7.3 Semantic Output Restoration

This path currently has two materially different behaviors:

- direct semantic edit restore, which uses square-canvas preparation and then restores the image back toward original geometry;
- generate/reconstruction restore, which trims outer padding conservatively and then uses contain-style restoration.

The refactor must treat this difference as a correctness concern, not as an implementation detail, because the structured mode currently prefers the direct edit path.

## 8. Target Architecture

## 8.1 Canonical Reinsertion Contracts

After implementation, the reinsertion layer should expose two clearly separated contracts:

1. inline image replacement contract;
2. synthetic multi-variant block contract.

The inline contract should keep existing paragraph ownership.

The synthetic block contract should own:

- how many output paragraphs are emitted;
- which paragraph properties are preserved;
- how images are aligned and spaced;
- how variant metadata is attached;
- what happens when generation is impossible.

The synthetic block contract should also be named according to its current block-paragraph behavior rather than historical table terminology. Legacy table-oriented naming should be treated as cleanup-in-scope because it obscures the actual OOXML structure being generated.

## 8.2 Minimal Paragraph Property Contract for Synthetic Blocks

Synthetic multi-variant image paragraphs should not clone the full `pPr` from the source placeholder paragraph.

Preferred preserved properties:

- explicit alignment when needed;
- conservative spacing if required for visual separation;
- no numbering/list inheritance by default;
- no heading/outline semantics by default;
- no keep-with-next or keep-lines semantics by default unless explicitly justified.

Implementation may preserve a very small approved subset of paragraph properties, but full `pPr` cloning is not the target state.

This narrowing applies only to synthetic image-only block paragraphs. Textual continuation paragraphs created before or after a multi-variant block should continue to preserve the full source paragraph properties where they remain semantically correct, so the hardening pass does not accidentally strip formatting from ordinary text fragments.

The preferred implementation shape is to keep the existing full-clone helper for text-fragment paragraphs and introduce a separate helper for synthetic image-block paragraph creation with a minimal approved `pPr` contract.

## 8.3 Cached Insertion Resolution

The reinsertion pass should compute variant insertion payloads once per relevant asset and reuse them across:

- strategy selection;
- multi-variant detection;
- final block construction;
- fallback decision logging.

This can be a per-paragraph cache or a reinsertion-pass cache keyed by placeholder string or asset identity.

For the current implementation shape, the preferred target is a reinsertion-pass cache owned by `reinsert_inline_images()` and keyed by placeholder string. That scope covers the known repeated call sites without forcing broader architectural changes or eager precomputation for unrelated assets.

This cache design assumes `ImageAsset` is effectively immutable for reinsertion purposes within a single `reinsert_inline_images()` call.

## 8.4 Explicit Multi-Variant Failure Contract

When multi-variant output cannot be emitted, the code must remain corruption-safe, but the reason must be specific and observable.

Preferred behavior:

1. do not silently degrade to placeholder text without a multi-variant-specific warning;
2. emit a dedicated event describing why block insertion was skipped or degraded;
3. retain the placeholder text only as an intentional safe fallback, not as an invisible side effect.

The preferred diagnostic choke point is the multi-variant gatekeeping path itself, so the code logs when multi-variant expansion was detected but intentionally abandoned before generic one-image helpers fall back to text preservation.

## 8.5 Narrow XML Metadata Targeting

Image description metadata should be attached to the image just inserted by the helper that created it, not to an arbitrary descendant `docPr` node selected through a broad XPath search.

The target state is not a large XML abstraction layer. It is a tighter helper contract with narrower selection semantics.

Where practical, the tightened helper should avoid relying on implicit global namespace registration for prefixed XPath queries and should instead pass the required namespace mapping explicitly for the narrowed metadata lookup.

## 8.6 Geometry-Safe Semantic Restore Contract

The semantic image restoration layer should expose an explicit visible-output contract:

1. structured redraw must not lose valid edge content merely because the intermediate edit canvas was square;
2. if restoration normalizes back toward original geometry, it should prefer containment or expansion over center-cropping when those choices avoid content loss;
3. if a crop is still necessary for a specific route, the reason must be intentional and test-covered rather than an incidental side effect of `fit(...)` after a square edit round-trip;
4. the primary structured edit path and the structured generate fallback path must satisfy the same no-unintended-crop contract.

The preferred implementation direction is to unify the visible geometry contract across structured routes even if the internal model APIs remain different.

## 8.7 Source Drawing Crop Boundary Contract

The refactor must make one of the following outcomes explicit:

1. source Word crop metadata is extracted, carried, and reapplied as part of the image delivery contract; or
2. source Word crop metadata remains unsupported, but the limitation is documented clearly and does not get conflated with semantic redraw clipping.

This work does not require a large OOXML geometry abstraction layer, but it does require the boundary to stop being implicit.

## 9. Workstreams

## 9.1 Workstream A: Separate Inline and Synthetic Block Semantics

Files in scope:

- `image_reinsertion.py`
- `tests/test_document.py`

Required changes:

- make synthetic multi-variant block generation explicitly named and clearly distinct from the old table-oriented naming;
- remove table-oriented leftovers that no longer describe the implementation, including the unused `Table` import if it remains present;
- rename the currently misleading table-oriented identifiers and strings, including the multi-variant replacement helper name, the multi-variant block-building section label, the internal fragment tag value, the matching fragment-tag condition, and the module docstring wording that still refers to comparison tables;
- keep single-image inline helpers focused on one-image replacement only;
- centralize block generation through one narrow helper path.

Acceptance:

- function naming reflects current block-based behavior rather than historical table behavior;
- synthetic multi-variant insertion path is identifiable without reading low-level XML details.

## 9.2 Workstream B: Reduce Synthetic Paragraph Formatting Inheritance

Files in scope:

- `image_reinsertion.py`
- `tests/test_document.py`

Required changes:

- replace full source `pPr` cloning for synthetic image-only paragraphs with a narrow paragraph formatting contract;
- keep full source `pPr` cloning for textual continuation paragraphs that still represent ordinary paragraph content around the expanded block;
- prefer introducing a dedicated synthetic image-block paragraph builder rather than weakening the existing paragraph-clone helper used for text fragments;
- document which properties are preserved and which are intentionally dropped.

Required regression coverage:

- multi-variant placeholder inside a numbered or bulleted paragraph;
- multi-variant placeholder inside a paragraph with explicit indentation;
- multi-variant placeholder inside a paragraph with keep-with-next or comparable pagination property if practical to assert;
- proof that generated image blocks do not inherit unintended list semantics.

Acceptance:

- generated multi-variant image paragraphs remain visually correct;
- list or heading semantics are not leaked into synthetic image-only blocks by default;
- surrounding before/after text still preserves its formatting where already covered today.

## 9.3 Workstream C: Add Reinsertion Caching for Variant Resolution

Files in scope:

- `image_reinsertion.py`
- optional related tests if helper boundaries change

Required changes:

- compute insertions once per relevant asset per reinsertion pass;
- prefer a cache owned by `reinsert_inline_images()` and keyed by placeholder string unless implementation evidence justifies a different scope;
- reuse computed results in detection and rendering branches.

Acceptance:

- `resolve_image_insertions()` is no longer called redundantly for the same asset within one reinsertion flow;
- cache scope is documented clearly enough that future maintainers can tell why placeholder-keyed reuse is safe;
- behavior remains unchanged for final output ordering and bytes selection.

## 9.4 Workstream D: Improve Multi-Variant Diagnostics

Files in scope:

- `image_reinsertion.py`
- `tests/test_document.py` or logging tests if available

Required changes:

- emit dedicated warnings when a multi-variant placeholder is intentionally left as text or cannot be safely expanded;
- prefer logging at the multi-variant gatekeeping decision point when expansion was detected but skipped, in addition to any narrower helper-level fallback logging that remains useful;
- distinguish this case from generic unhandled placeholder warnings.

Acceptance:

- logs make it possible to tell the difference between generic reinsertion failure and multi-variant-safe fallback;
- output remains corruption-safe.

## 9.5 Workstream E: Tighten Image Description Targeting

Files in scope:

- `image_reinsertion.py`
- `tests/test_document.py`

Required changes:

- narrow the `docPr` targeting helper to the inserted image scope;
- where practical, make the tightened lookup explicit about XML namespaces rather than depending on implicit global registration side effects;
- preserve current visible behavior and existing metadata labeling contract.

Acceptance:

- labels continue to appear in image metadata for compare-all and preserve-all flows;
- helper no longer relies on overly broad descendant selection.

## 9.6 Workstream F: Remove Unintended Crop From Structured Semantic Restore

Files in scope:

- `image_generation.py`
- `tests/test_image_generation.py`

Required changes:

- make the primary structured `Images.edit` restore path satisfy the same no-unintended-crop contract already expected from the generate fallback path;
- eliminate or constrain any restore step where square-canvas recovery plus `ImageOps.fit(...)` can crop valid edge content without an explicit product reason;
- document the intended geometry rule for direct edit restore versus generate/reconstruction restore.

Required regression coverage:

- a focused test proving the primary structured edit path preserves edge markers or equivalent boundary content after square-canvas restoration;
- proof that the same structured source image does not pass only because the code fell back to generate;
- coverage that distinguishes legitimate margin trimming from destructive content crop.

Acceptance:

- the primary structured edit path no longer crops away valid edge content in covered scenarios;
- structured edit and structured generate satisfy the same visible anti-crop contract;
- tests fail if a future refactor reintroduces crop-through-restore behavior.

## 9.7 Workstream G: Make Source Crop Metadata Handling Explicit

Files in scope:

- `document.py`
- `models.py`
- `image_reinsertion.py`
- tests only if the implementation elects to support the boundary now

Required changes:

- decide explicitly whether Word-native crop metadata is in-scope for current support or explicitly deferred;
- if implemented now, carry the needed crop metadata through extraction and reinsertion with focused tests;
- if deferred, document the boundary clearly in code and spec language so semantic redraw clipping and source crop semantics are not mixed together during future debugging.

Acceptance:

- the repository no longer has an implicit or ambiguous position on source crop metadata;
- future regressions can distinguish “semantic redraw restore cropped content” from “source DOCX contained crop metadata that is not yet replayed.”

## 10. Files in Scope

Primary:

- `image_generation.py`
- `image_reinsertion.py`
- `tests/test_image_generation.py`
- `tests/test_document.py`

Potentially touched if helper boundaries justify it:

- `document.py`
- `models.py`

Assumptions to keep explicit during implementation:

- `ImageAsset` and `get_image_variant_bytes` are key reinsertion dependencies, not incidental helpers;
- caching keyed by placeholder is only safe while `ImageAsset` contents relevant to reinsertion are not mutated during a single reinsertion pass.

Not expected to change unless a dependency boundary requires it:

- `formatting_transfer.py`
- `image_pipeline.py`
- `compare_panel.py`

## 11. Test and Verification Plan

Visible verification must use existing VS Code tasks.

Minimum focused verification:

1. run the current image-generation-focused and document-focused tests through the matching VS Code pytest task(s);
2. confirm structured semantic restore scenarios still pass:
   - primary structured edit path preserves edge content after restore;
   - structured generate fallback preserves edge content after restore;
   - large generated outer margins can still be trimmed without destructive crop.
3. confirm existing reinsertion scenarios still pass:
   - same-paragraph single-image replacement;
   - split-run placeholder replacement;
   - hyperlink preservation;
   - header/footer insertion;
   - textbox insertion;
   - compare-all multi-variant insertion;
   - preserve-all review insertion.
4. add and verify the new formatting-sensitive regression tests for synthetic multi-variant blocks.
5. if source crop metadata support is deferred rather than implemented, verify that the limitation is documented explicitly in the touched code/spec surface.

Recommended broader verification after implementation:

1. relevant DOCX/document test file task run;
2. full visible pytest task run if the repository-wide suite is otherwise green.

## 12. Risks

1. Narrowing paragraph-property inheritance too aggressively may make generated image blocks look less integrated in some source documents.
2. Caching insertion payloads at the wrong layer could accidentally reuse stale state if an asset is mutated after cache construction.
3. Tightening XML targeting may expose hidden assumptions in how `python-docx` emits inline drawing XML.
4. Changing block naming and helper boundaries can require test updates even if visible behavior stays the same.
5. Unifying structured restore geometry across edit and generate paths may expose hidden assumptions in existing image-generation tests.
6. Bringing source crop metadata into scope may reveal that some apparent clipping reports come from pre-existing DOCX crop semantics rather than semantic redraw itself.

## 13. Rollout Strategy

Recommended implementation order:

1. remove unintended crop from the primary structured semantic restore path and lock it with focused tests;
2. decide and document the source crop metadata boundary;
3. rename and isolate synthetic block helpers;
4. narrow synthetic paragraph formatting inheritance;
5. add caching for variant insertion resolution;
6. add dedicated multi-variant fallback diagnostics;
7. tighten image-description XML targeting;
8. run focused visible verification, then broader verification if appropriate.

Each step should land in a stable state with matching tests.

## 14. Acceptance Criteria

This spec is satisfied when all of the following are true:

1. single-image reinsertion behavior remains stable in existing covered scenarios;
2. the primary structured semantic edit path no longer crops valid edge content as an incidental consequence of square-canvas restoration;
3. the repository has an explicit supported-or-deferred position on source Word crop metadata;
4. multi-variant image output is generated through an explicit synthetic block contract rather than broad paragraph cloning;
5. generated multi-variant image blocks no longer inherit unintended list or heading semantics by default;
6. reinsertion no longer repeats insertion resolution work unnecessarily for the same asset in one pass;
7. multi-variant fallback behavior produces explicit diagnostics;
8. image variant labels remain attached in metadata correctly;
9. focused image-generation and reinsertion regression tests pass through the repository’s visible VS Code task workflow.

## 15. What Does Not Change

The following behavior remains unchanged unless a separate approved spec says otherwise:

- the app still supports compare-all output with all generated image variants present in the DOCX;
- `semantic_redraw_structured` may still use edit, generate, or deterministic reconstruction internally as long as the visible anti-crop contract is preserved;
- variant labels remain hidden from body text and stored in image metadata;
- single-image placeholders still resolve to a single final image in-place where possible;
- support for headers, footers, textboxes, table cells, split-run placeholders, and nearby hyperlinks remains part of the reinsertion contract.