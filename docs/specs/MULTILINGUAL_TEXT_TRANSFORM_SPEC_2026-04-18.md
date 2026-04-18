# Multilingual Text Transform Spec

Date: 2026-04-18

## Goal

Add support for:

1. Multi-page document translation, initially English to a user-selected target language.
2. Extended translation from any source language to any target language.
3. Literary editing not only for Russian, but for any selected language.
4. Combined workflows where the user chooses whether to translate, edit, or do both.

The implementation must preserve the current document-processing architecture and minimize refactoring. The document extraction, semantic blocking, formatting restoration, and image pipeline are not to be redesigned as part of this work.

## Problem Statement

The current application already supports long-form DOCX processing by:

1. Extracting logical paragraphs and semantic blocks.
2. Building block jobs with neighboring context.
3. Running each block through the text-generation path.
4. Reassembling the final DOCX with formatting and image preservation.

This makes the runtime fundamentally suitable for book-length translation and editing.

The current limitation is not the block pipeline itself. The limitation is that text processing semantics are effectively hardcoded for one scenario: literary editing of machine-translated text with Russian-specific instructions. Those assumptions currently live in:

1. The system prompt file in `prompts/system_prompt.txt`.
2. User-prompt builders and recovery prompts in `generation.py`.
3. UI semantics that expose only one text-processing mode.
4. The prompt-loading contract, which currently assumes a zero-argument system-prompt loader.

As a result, the product cannot cleanly express:

1. Edit text in-place in a selected language.
2. Translate from one language to another without changing the rest of the pipeline.
3. Translate and then apply literary polishing in the target language.
4. Support future multilingual workflows without proliferating ad hoc prompt variants.

## Current State

### Stable parts of the architecture

The following parts are already language-agnostic enough for the first implementation phase and should remain intact:

1. `document.py`
   Handles DOCX extraction, semantic block building, context excerpts, and job construction.
2. `preparation.py`
   Builds prepared document data and caches preparation results.
3. `application_flow.py`
   Orchestrates upload, preparation, idle/restart behavior, and processing setup.
4. `document_pipeline.py`
   Executes the block-processing loop, assembles processed markdown, and restores DOCX output.
5. `formatting_transfer.py`, `image_pipeline.py`, `image_generation.py`, `image_reinsertion.py`
   Do not need multilingual-specific changes for text transformation support.

### Current language-coupled parts

The following parts are coupled to the current Russian-centric editing behavior:

1. `prompts/system_prompt.txt`
   Encodes Russian editorial and typographic assumptions.
2. `config.py`
   Exposes `load_system_prompt()` as a zero-argument loader for a single prompt file.
3. `generation.py`
   Contains Russian editing-oriented user prompts and recovery prompts.
4. `ui.py`
   Exposes only general processing settings, not text-operation mode or languages.
5. `processing_service.py` and `document_pipeline.py`
   Assume prompt loading does not depend on per-run text-transform context.

## Product Scope

### In scope for Phase 1

Phase 1 introduces a minimal, production-oriented feature set:

1. Two user-visible text modes in the UI: literary editing and translation.
2. User-selectable target language for editing.
3. User-selectable source and target languages for translation.
4. Book-length processing using the existing block pipeline.
5. Prompt composition that adapts behavior based on selected mode and languages.
6. Neutral user prompts so the same block pipeline supports editing and translation.

### Out of scope for Phase 1

The following items are explicitly deferred:

1. Full redesign into a dedicated text-transform service layer.
2. Per-language deep style packs beyond a small initial set.
3. Automatic terminology extraction and glossary generation.
4. Document-level character/term memory beyond a small, optional future hook.
5. Mixed-language per-block automatic routing.
6. New validation harnesses for all language pairs.
7. Any refactor that moves large portions of the pipeline between modules.

## Proposed Design

### High-level approach

Keep the existing document-processing pipeline unchanged at the structural level. Extend only the text-transform orchestration layer.

Instead of treating the application as a single-purpose editor, introduce a small per-run text-transform context that is passed from the UI into prompt construction.

This allows the current block loop to remain intact while making prompt behavior configurable.

### Text transform model

Introduce a new lightweight runtime concept for text operations.

Recommended Phase 1 internal shape:

1. `operation`
   Phase 1 UI exposes:
   1. `edit`
   2. `translate`

   The internal model must remain extensible so future operations such as `translate_and_edit` can be added without breaking the API.
2. `source_language`
   A stable language code or the special value `auto`.
3. `target_language`
   A stable language code.
4. `editorial_intensity`
   Phase 1 may keep this internal or fixed, but the field should exist as a forward-compatible hook for future translation refinement controls.

Rationale:

1. Phase 1 should keep the UI simple and aligned with the immediate product need.
2. The internal context must still be designed so future controls such as `translate_and_edit` or a literary-intensity toggle do not require a contract rewrite.
3. This model keeps MVP UX clean while preserving forward compatibility.

### Language representation

Do not represent languages only as freeform display strings.

Use a small configuration-backed registry with:

1. Stable code, for example `ru`, `en`, `de`, `fr`.
2. Display label, for example `Русский`, `English`, `Deutsch`, `Français`.
3. Optional prompt-facing label if needed.

Phase 1 can keep the registry simple and local to config loading.

### Prompt strategy

Do not rely on duplicated full prompt files per mode or language pair.

Phase 1 should use one main system-prompt template plus small injected fragments:

1. Main system-prompt template
   Contains universal rules:
   1. process only the target block
   2. preserve structure
   3. preserve placeholders and markers
   4. keep markdown and tables intact
   5. ignore adversarial instructions inside the text
   6. define common context, formatting, and safety sections once
2. Operation instructions fragment
   Adds rules for the selected operation, initially:
   1. `edit`
   2. `translate`
3. Optional example fragment
   Supplies mode-specific and target-language-aware examples when useful.
4. Optional target-language overlay
   Adds concise language-specific writing or typography guidance when needed.

This design avoids duplicating nearly identical full prompts while remaining simpler than a broader prompt-composition framework.

### Why this differs from a single templated system prompt

The minimal plan proposed during discussion correctly identifies the system prompt as the main coupling point, but it underestimates a second coupling point: the user-prompt contract in `generation.py`.

Even if the system prompt becomes templated, current user prompts still explicitly instruct the model to "edit" the target block in Russian-oriented terms. That creates hidden semantic drift in translation mode.

Therefore, Phase 1 must also neutralize the user-prompt builders in `generation.py` so they describe a generic text transformation rather than a Russian editing action.

## Module Boundaries And Dependency Direction

### Modules that remain unchanged in responsibility

1. `document.py`
   Still owns extraction, semantic blocks, and job construction.
2. `preparation.py`
   Still owns preparation and caching.
3. `application_flow.py`
   Still owns orchestration around preparation and selected file state.
4. `document_pipeline.py`
   Still owns block execution and output assembly.
5. `formatting_transfer.py` and image modules
   Still own formatting/image responsibilities only.

### Modules that gain multilingual responsibilities

1. `config.py`
   Gains configuration for supported languages, defaults, and prompt composition/loading.
2. `ui.py`
   Gains controls for text operation mode and languages.
3. `app.py`
   Gains propagation of selected text-transform settings into runtime processing.
4. `processing_service.py`
   Gains the ability to thread text-transform context through dependency boundaries.
5. `document_pipeline.py`
   Gains consumption of text-transform context when loading the system prompt.
6. `generation.py`
   Keeps the same role, but prompt builders become operation-neutral.

Dependency direction should remain:

1. UI and app layer produce a text-transform context.
2. Processing orchestration passes that context downstream.
3. Prompt loading and user-prompt building consume the context.
4. Core document preparation and reconstruction remain upstream-agnostic.

The context must flow downward only. Extraction and formatting layers must not become dependent on translation or editing semantics.

## Detailed Phase 1 Changes

### 1. Add text-transform settings to configuration

Update `config.toml` and `config.py` to support:

1. `processing_operation_default`
2. `source_language_default`
3. `target_language_default`
4. `supported_languages`

Configuration should also expose a language registry that the UI can render without hardcoding labels separately.

Phase 1 language set is fixed as:

1. `ru`
2. `en`
3. `de`
4. `fr`
5. `es`
6. `it`
7. `pl`
8. `zh`
9. `ja`

Recommended `supported_languages` shape in `config.toml`:

```toml
supported_languages = [
   { code = "ru", label = "Русский" },
   { code = "en", label = "English" },
   { code = "de", label = "Deutsch" },
   { code = "fr", label = "Français" },
   { code = "es", label = "Español" },
   { code = "it", label = "Italiano" },
   { code = "pl", label = "Polski" },
   { code = "zh", label = "中文" },
   { code = "ja", label = "日本語" },
]
```

The implementation should parse this into a small typed structure rather than passing raw dictionaries through the runtime.

### 2. Replace single-prompt loading with a parameterized template loader

Replace the current zero-argument `load_system_prompt()` with a parameterized loader that accepts at least:

1. `operation`
2. `source_language`
3. `target_language`

The loader must build the final system prompt from one main template plus small fragments and cache the result by those inputs.

Recommended Phase 1 interface:

```python
def load_system_prompt(
    *,
    operation: str,
    source_language: str,
    target_language: str,
) -> str:
    ...
```

This necessarily changes the loader contract used by `processing_service.py` and `document_pipeline.py`.

Recommended implementation conventions for Phase 1:

1. Use standard Python `str.format(...)` for template substitution.
2. The main shared template should expose placeholders such as:
   1. `{operation_instructions}`
   2. `{example_block}`
   3. optional target-language placeholders when needed
3. Do not add Jinja2 or any new templating dependency for Phase 1.
4. Use `@lru_cache(maxsize=32)` for the parameterized prompt loader.

The previous single-entry prompt cache shape is not sufficient once prompt loading depends on operation and language inputs.

### 3. Add text-operation controls to sidebar

Update `ui.py` so `render_sidebar(...)` returns additional text-transform settings.

Required UI behavior:

1. `edit`
   Show target language only.
2. `translate`
   Show source and target languages.
3. `source_language == auto`
   Allowed only for translation mode.

The implementation may internally map `translate` to a translation flow that already includes literary polishing in the target language, because that matches the current product request. Future translation-intensity controls are explicitly deferred.

The sidebar contract must be expanded in a controlled way. All callers must be updated in the same change.

### 4. Propagate text-transform context through processing startup

Update `app.py` and `processing_service.py` so the selected operation and languages are passed into runtime processing.

This context must become part of the processing run contract, not an implicit UI-only variable.

The Phase 1 propagation path must explicitly cover all of the following call sites:

1. `app.py` `_start_background_processing(...)`
2. `app.py` `worker_entrypoint(...)`
3. `processing_service.py` `run_processing_worker(...)`
4. `processing_service.py` `run_document_processing(...)`
5. `document_pipeline.py` `run_document_processing(...)`

In addition, `processing_service.py` `run_prepared_background_document(...)` must be updated as an alternate entry point used by tests and integration flows.

### 5. Update prompt consumption in the block pipeline

Update `document_pipeline.py` so the system prompt is loaded with the run-specific text-transform context instead of a global prompt.

This should happen once per processing run, not per block.

### 6. Neutralize user prompts in generation

Update prompt-builder functions in `generation.py` so they are no longer specifically framed as Russian literary editing.

Required changes:

1. Standard prompt should say the model must transform only the target block according to system instructions.
2. Marker-preserving prompt should use the same neutral framing.
3. Recovery prompts must avoid editing-only assumptions.
4. Context placeholders for missing context should become language-neutral or system-neutral.
5. `_normalize_context_text(...)` must stop returning a Russian-language placeholder such as `"[контекст отсутствует]"`.
6. `_CONTEXT_LEAKAGE_RETRY_WARNING` must be rewritten to neutral wording consistent with translation and editing modes.

These changes are intentionally small. They do not alter retry logic, block acceptance, marker validation, or request mechanics.

## Prompt Files For Phase 1

Recommended prompt structure under `prompts/`:

1. One main system-prompt template file for shared rules.
2. `operation_edit.txt`
3. `operation_translate.txt`
4. Optional example fragments keyed by operation and, when useful, by target language.
5. Optional target-language overlay fragments for concise editorial guidance.

The preferred Phase 1 shape is one shared template with injected operation-specific fragments, not two duplicated full prompt files.

If the existing `system_prompt.txt` is reused as the implementation base, it should be explicitly converted into a generic text-transform template rather than continuing to represent a Russian-only editorial prompt implicitly.

## Handling Source Language `auto`

Phase 1 must support `auto` conservatively.

Recommended behavior:

1. `auto` is accepted for translation operations only.
2. The initial implementation may pass `auto-detect the source language from the target block and context` into the prompt rather than adding a separate detection stage.
3. The chosen strategy must be documented in the UI and implementation notes as best-effort, not guaranteed language identification.

Deferred future improvement:

1. A document-level language detection prepass.
2. Storing the resolved source language in run metadata.

## Optional Forward-Compatible Hook: Document Style Guide

Although Phase 1 does not require a new prepass, the design should leave a clean path for a later document-level style guide.

This is important for long-form books where consistency across blocks matters for:

1. names
2. transliteration
3. terminology
4. narrative tone
5. level of literary polish

Phase 1 does not need to implement it, but must not block adding a small `document_style_guide` field to the text-transform context later.

## Consumer Update Plan

The following consumer-facing contracts must be updated together in one implementation change:

1. `ui.render_sidebar(...)`
   Return type changes to include text-transform settings.
2. `app.py`
   Must accept and propagate the expanded sidebar result.
3. `processing_service.py`
   Must pass the context to downstream processing.
4. `document_pipeline.py`
   Must request the system prompt with parameters.
5. `config.py`
   Must load prompts and language configuration using the new API.
6. Relevant tests
   Must be updated for the new loader signature and new sidebar contract.

No external public API beyond the app itself is expected to break, but internal call sites must be updated atomically.

## What Must Not Change

This specification does not authorize changes to the following architectural boundaries:

1. No redesign of semantic block construction in `document.py`.
2. No dedicated alternate translation pipeline.
3. No movement of formatting restoration out of current modules.
4. No changes to image-processing architecture.
5. No changes to startup/runtime contract unrelated to the new text-transform settings.
6. No broad refactor across multiple modules beyond the narrow propagation of text-transform context.

## Risks

### 1. Hidden prompt drift

Risk:
System prompt becomes multilingual, but user prompts in `generation.py` remain editing-specific.

Mitigation:
Update user-prompt builders in the same change.

### 2. Prompt-file sprawl

Risk:
Every language pair gets a full prompt copy.

Mitigation:
Use base plus overlays from the start, or at minimum design the loader API to support it.

### 3. Weak `auto` language detection

Risk:
Mixed-language or noisy documents may be misdetected.

Mitigation:
Constrain `auto` to translation flows and document it as best-effort in Phase 1.

### 4. UX ambiguity between translation and literary editing

Risk:
Phase 1 keeps the UI intentionally simple, but later product requirements may need finer control over literal versus literary translation.

Mitigation:
Keep Phase 1 UI to two modes, but design the internal processing context and prompt loader so future translation-intensity or additional operation variants can be added without breaking the contract.

### 5. Incomplete test coverage

Risk:
Signature and prompt changes may silently break processing startup or test doubles.

Mitigation:
Update targeted unit tests for config, sidebar contract, and document pipeline prompt loading.

## Verification Criteria

Implementation will be considered complete for Phase 1 when all of the following are true:

1. The user can choose `edit` or `translate` in the sidebar.
2. The user can choose source and target languages as required by the selected operation.
3. The selected values propagate through the runtime into prompt loading.
4. The system prompt is built from run-specific operation and language settings.
5. `generation.py` user prompts are operation-neutral and work for both editing and translation flows.
6. Existing document preparation, block processing, formatting preservation, and image handling continue to work.
7. Targeted unit tests cover:
   1. config loading of supported languages and defaults
   2. sidebar return contract
   3. prompt loading with parameters
   4. document pipeline passing operation and languages into prompt loading
   5. generation prompt builders no longer containing editing-only assumptions

## Suggested Implementation Order

1. Add config support for text operations and supported languages.
2. Implement parameterized system-prompt loading.
3. Add sidebar controls and propagate selected values through `app.py`.
4. Update `processing_service.py` and `document_pipeline.py` for the new loader contract.
5. Neutralize user-prompt builders in `generation.py`.
6. Add and update targeted tests.

## Implementation Checklist

### Priority 0: Lock the runtime contract

- [x] Confirm the Phase 1 UI exposes exactly two modes: `edit` and `translate`.
- [x] Confirm that Phase 1 `translate` means translation with literary polishing in the target language.
- [x] Confirm the initial supported language list and stable language codes.
- [x] Confirm the `supported_languages` config shape as `{ code, label }` entries.
- [x] Confirm whether the existing `prompts/system_prompt.txt` will be converted in place or replaced by a new main template file.
- [x] Confirm that Phase 1 prompt rendering uses Python `str.format(...)` rather than introducing a templating dependency.
- [x] Confirm that prompt caching will use `@lru_cache(maxsize=32)`.

### Priority 1: Add the configuration and prompt-loading foundation

- [x] Add `processing_operation_default`, `source_language_default`, `target_language_default`, and `supported_languages` to config.
- [x] Implement a stable language registry shape in `config.py` using codes plus labels.
- [x] Replace the zero-argument system prompt loader with a parameterized loader.
- [x] Add caching keyed by operation, source language, and target language.
- [x] Implement the main template plus operation fragment loading path.
- [x] Add optional target-language overlay or example fragment loading hooks, even if only one or two are used initially.

### Priority 2: Thread the processing context through the runtime

- [x] Expand the sidebar return contract in `ui.py`.
- [x] Update `app.py` to receive and pass the selected operation and languages.
- [x] Update `app.py` `_start_background_processing(...)` and `worker_entrypoint(...)`.
- [x] Update `processing_service.py` `run_processing_worker(...)`.
- [x] Update `processing_service.py` `run_document_processing(...)`.
- [x] Update `processing_service.py` `run_prepared_background_document(...)`.
- [x] Update `processing_service.py` dependency typing and forwarding.
- [x] Update `document_pipeline.py` protocol typing for the prompt loader.
- [x] Ensure the system prompt is loaded once per processing run with the selected context.

### Priority 3: Remove semantic prompt drift in generation

- [x] Neutralize the standard user prompt builder in `generation.py`.
- [x] Neutralize the marker-preserving prompt builder in `generation.py`.
- [x] Neutralize empty-response recovery prompts.
- [x] Neutralize marker-recovery prompts.
- [x] Replace editing-specific retry-warning wording with operation-neutral wording.
- [x] Replace language-specific missing-context placeholders with neutral wording.
- [x] Explicitly update `_normalize_context_text(...)` to return a neutral placeholder.

### Priority 4: Add the Phase 1 prompt assets

- [x] Create or convert the shared system-prompt template.
- [x] Add the `edit` operation fragment.
- [x] Add the `translate` operation fragment.
- [x] Add at least one target-language-aware example or overlay for the initial target languages.
- [x] Verify that prompt composition does not duplicate common formatting, safety, and context rules.

### Priority 5: Test the contract changes

- [x] Update config tests for language registry and defaults.
- [x] Update UI tests for the expanded sidebar contract.
- [x] Update pipeline tests for the parameterized prompt-loader signature.
- [x] Add tests that confirm prompt loading uses operation and language parameters.
- [x] Add tests that confirm `generation.py` prompt builders no longer contain editing-only wording.
- [x] Update tests that assert the exact context-leakage retry warning text, including `test_generate_markdown_block_retries_on_context_leakage_and_reinforces_prompt`.
- [x] Verify existing document-processing tests still pass where behavior should remain unchanged.

### Priority 6: Manual verification before broader rollout

- [ ] Verify literary editing on a same-language document.
- [ ] Verify translation on a multi-page English document.
- [ ] Verify `source_language=auto` behavior on a clean single-language document.
- [ ] Verify marker-preserving mode still works under translation.
- [ ] Verify formatting, lists, headings, tables, and image placeholders remain intact.
- [ ] Verify the result is still assembled into DOCX correctly.

## Phase 2 Follow-Ups

After Phase 1 ships, the next improvements should be evaluated separately:

1. Document-level language detection prepass.
2. Document-level glossary and style guide.
3. Target-language-specific editorial overlays beyond the initial set.
4. More explicit control over translation literalness versus literary polish.
5. Validation fixtures for long-form multilingual real documents.

## Readiness Assessment

This specification is sufficient to start implementation.

The architecture, scope, boundaries, runtime propagation, prompt strategy, and verification criteria are now concrete enough for development work to begin without additional design work.

The remaining choices are implementation details already fixed by this document for Phase 1:

1. Phase 1 UI modes: `edit`, `translate`
2. Phase 1 language set: `ru`, `en`, `de`, `fr`, `es`, `it`, `pl`, `zh`, `ja`
3. Config language registry shape: `{ code, label }`
4. Prompt rendering mechanism: `str.format(...)`
5. Prompt cache shape: `@lru_cache(maxsize=32)`

No further specification work is required before coding unless the product owner wants to change the Phase 1 language set or UI behavior.

## Approval Boundary

This specification authorizes only a localized feature implementation for multilingual text transformation on top of the current pipeline.

It does not authorize a broader architectural refactor into a new service layer, module split, or pipeline redesign.