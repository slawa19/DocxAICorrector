# Codebase Maintainability Implementation Spec

Date: 2026-03-24
Status: Proposed
Scope type: multi-phase maintainability and architecture cleanup
Primary input: `docs/reviews/CODEBASE_MAINTAINABILITY_REVIEW_2026-03-24.md`

## 1. Problem Statement

The current codebase is functional and test-covered enough to support feature work, but several maintenance costs are now structural rather than incidental:

- orchestration responsibility is split across `app.py`, `app_runtime.py`, `application_flow.py`, `processing_runtime.py`, `processing_service.py`, and `document_pipeline.py`;
- low-risk duplication exists in core runtime paths, including OpenAI response parsing, upload helper construction, and image-processing summary defaults;
- one confirmed correctness/performance issue exists in the synchronous preparation path, where upload normalization can be performed twice for the same request;
- `config.py` exposes an unlocked singleton client initialization path, unlike the already lock-protected service singleton in `processing_service.py`;
- `ImageAsset` mixes immutable source data, runtime processing state, validation state, compare-all state, and logging payload shape into one mutable object;
- the real-document validation harness partially reassembles production orchestration instead of consuming a tighter shared runtime contract;
- at least one developer script is stale and references a removed API surface.

None of these issues alone justifies a full redesign. Together they increase regression risk, slow targeted changes, and make it harder to reason about which module owns which contract.

This specification defines a phased implementation plan that reduces those costs without changing the core product workflow, startup contract, or test workflow contract.

## 2. Goals

1. Remove validated low-risk duplication in critical paths first.
2. Re-establish explicit ownership boundaries for upload preparation, processing orchestration, response parsing, and validation harness execution.
3. Preserve current user-visible behavior unless a change is explicitly called out in this spec.
4. Reduce the number of places where the same runtime contract is reconstructed differently.
5. Improve confidence for future changes by making state transitions and shared helpers easier to test in isolation.

## 3. Non-Goals

This spec does not authorize the following:

- redesigning the product UX;
- changing the WSL-first test workflow contract;
- changing the startup performance contract unless required by a bug fix and explicitly reviewed against `docs/STARTUP_PERFORMANCE_CONTRACT.md`;
- replacing Streamlit or re-platforming the application;
- broad reorganization of the image pipeline prompts/algorithms;
- deleting real-document validation coverage as a class of tooling;
- splitting modules purely for aesthetic reasons without a contract simplification benefit.

## 4. Protected Contracts

The following repository contracts remain in force throughout implementation:

1. Startup performance contract in `docs/STARTUP_PERFORMANCE_CONTRACT.md`.
2. WSL/bash pytest workflow and visible verification requirement via existing VS Code tasks.
3. Real-document validation entrypoints and artifact conventions documented in repo instructions.
4. Existing processing semantics for legacy `.doc` upload identity tokens: token identity remains derived from original source bytes, not converted DOCX bytes.
5. Streamlit rerun model remains the primary UI/runtime execution model.

Any phase that appears to pressure one of these contracts must explicitly document why and must update the canonical contract docs if behavior is intentionally changed.

## 5. Current-State Findings in Scope

This spec is driven by the validated findings from the maintainability review.

Revalidation note against the current repository snapshot on 2026-03-24:

- `REL-001`, `PERF-001`, `DUP-002`, `DUP-004`, `APP-002`, `STALE-001`, `ARCH-001`, `DATA-001`, and the validation-harness drift findings are still present in code;
- the image-processing summary default shape is no longer duplicated as two independently maintained dict literals; `state.py` is already the authoritative shape source, and the remaining cleanup is removal of redundant wrapper aliases rather than re-unifying diverged implementations;
- `real_document_validation_profiles.py` still exposes `expected_acceptance_policy`, but current runtime paths and registry resolution do not consume it outside parsing/tests, so this remains an active maintainability issue that should be folded into validation-harness convergence rather than left implicit.

### P0 findings

- `REL-001`: `config.py:get_client()` performs unlocked singleton initialization.
- `PERF-001`: `_prepare_run_context_core()` can normalize the same upload twice in the synchronous path when `uploaded_payload is None`.
- `DUP-002`: response parsing logic is duplicated between `generation.py` and `image_shared.py`.
- `DUP-003`: image-processing summary defaults are already single-sourced in `state.py`, but redundant wrapper aliases remain in `processing_runtime.py` and `state.py`.
- `DUP-004`: in-memory uploaded-file builders are duplicated between `processing_runtime.py` and `preparation.py`.
- `GEN-001`: duplicated raise branch in `generation.py`.
- `APP-002`: `app.py` contains repeated frame-finalization calls and avoidable late imports.
- `STALE-001`: `scripts/run_pic1_modes.py` references a removed surface (`app.process_document_images`).

### P1-P3 findings

- `ARCH-001`: orchestration ownership is spread across too many modules.
- `DATA-001`: `models.py:ImageAsset` is overloaded with multiple lifecycle concerns.
- `BOUNDARY-001`: real-document structural validation partially duplicates production orchestration behavior.
- `DEAD-001`: `real_document_validation_profiles.py` still exposes `expected_acceptance_policy`, but no runtime validation path meaningfully consumes it.

## 6. Design Principles

Implementation must follow these principles:

1. Fix root ownership problems before adding local patches.
2. Prefer one shared helper or contract over two “almost the same” call-site utilities.
3. Do not create a new abstraction layer unless at least two real consumers use it.
4. Keep public API movement incremental; each phase must leave the system in a stable, testable state.
5. Prefer production-path reuse over validator-only or debug-only orchestration forks.
6. Preserve current behavior first; behavior changes require an explicit acceptance section.

## 7. Target Architecture

The target is not a large rewrite. It is a clarified boundary model.

### 7.1 UI Layer

`app.py` remains the Streamlit entrypoint and page composition root.

`app.py` should own:

- page config;
- top-level rerun flow;
- widget rendering order;
- user-facing control decisions.

`app.py` should not own:

- ad hoc runtime helper factories;
- duplicated end-of-frame lifecycle calls scattered across branches;
- late imports used only to work around ownership ambiguity.

### 7.2 Upload and Preparation Layer

One shared contract must own upload identity and normalization semantics.

That contract includes:

- reading uploaded bytes;
- source format detection;
- legacy `.doc` normalization to `.docx`;
- file token generation;
- in-memory uploaded file reconstruction for downstream DOCX readers.

The contract currently spans `processing_runtime.py`, `application_flow.py`, and `preparation.py`. After implementation, preparation and runtime code should both consume the same canonical helper surface.

### 7.3 Processing Orchestration Layer

`application_flow.py` should own preparation and idle-state flow decisions.

`processing_runtime.py` should own upload freezing, upload markers, background runtime primitives, and event-queue mechanics.

`processing_service.py` should own dependency assembly for the background worker.

`document_pipeline.py` should own document-processing orchestration once inputs are already prepared.

`app_runtime.py` should not remain a second ownership center for runtime mechanics. After cleanup it should either:

- be reduced to a thin Streamlit-facing facade over `processing_runtime.py`; or
- be collapsed if that produces a clearer ownership split with fewer forwarding layers.

The target boundary is:

- `application_flow.py`: decides what to prepare and when;
- `processing_runtime.py`: owns runtime worker/event primitives and upload/runtime helper contracts used by UI and workers;
- `app_runtime.py`: at most a UI-facing adapter over runtime primitives, not a parallel orchestration layer;
- `processing_service.py`: wires dependencies for worker execution;
- `document_pipeline.py`: executes the processing pipeline on prepared inputs.

### 7.4 OpenAI Response Parsing Layer

OpenAI Responses API text extraction must live in one shared utility surface.

This utility should be neutral to text-generation vs image-generation callers. It should not remain embedded in `generation.py` and should not remain implicitly “owned” by `image_shared.py`, whose module name suggests image-domain ownership rather than general Responses API parsing.

Preferred target: extract shared response-shape parsing into a small dedicated module, for example `openai_response_utils.py` or an equivalent neutral helper module.

### 7.5 Image Pipeline State Layer

`ImageAsset` should continue to represent a document image unit, but mutable pipeline state should be narrowed.

The target is not necessarily to delete `ImageAsset`. The target is to stop using one object as all of the following simultaneously:

- source asset descriptor;
- working mutable pipeline record;
- compare-all variant container;
- final decision record;
- logging payload serializer.

Implementation may keep `ImageAsset` as the base document-facing shape and introduce one additional runtime state structure if that materially reduces mutation ambiguity.

### 7.6 Validation Harness Layer

Real-document validation should consume the narrowest possible production contract.

The structural harness should reuse production preparation/runtime helpers rather than recreating orchestration logic inline wherever practical. The goal is to reduce drift between validator behavior and application behavior without forcing the validator to depend on Streamlit session machinery.

## 8. Workstreams and Priorities

## 8.1 Priority P0: Safe Hardening and Duplication Removal

Objective: land low-risk changes that reduce immediate maintenance cost without changing architecture boundaries in a disruptive way.

### P0.1 Lock-protect `config.py:get_client()`

Files in scope:

- `config.py`
- `tests/test_config.py`

Required change:

- add lock-protected, double-checked singleton initialization equivalent in spirit to `processing_service.py:get_processing_service()`;
- preserve lazy import of `openai.OpenAI` and preserve current error messages.

Acceptance:

- repeated calls still return the same client instance;
- concurrent initialization cannot construct multiple clients;
- no startup-regression from eager client creation.

### P0.2 Remove sync-path duplicate normalization

Files in scope:

- `application_flow.py`
- `processing_runtime.py`
- `tests/test_application_flow.py`
- `tests/test_processing_runtime.py`

Required change:

- ensure the synchronous preparation path does not normalize the same upload twice;
- preserve existing legacy `.doc` token contract based on original source bytes;
- keep background path behavior unchanged except for shared-helper reuse if introduced.

Acceptance:

- the sync path performs one normalization pass per upload request;
- background path remains correct;
- the existing legacy `.doc` token stability test keeps passing.

### P0.3 Deduplicate Responses API parsing

Files in scope:

- `generation.py`
- `image_shared.py`
- new neutral shared helper module

Required change:

- extract the currently duplicated low-level Responses API traversal helpers into one shared neutral module;
- keep current supported response shape behavior unchanged;
- keep current error strings and empty/collapsed-output classification unless a specific correction is required.

Explicit decision:

- do not leave general response parsing inside `image_shared.py`; that keeps a cross-domain dependency pointing to the wrong ownership concept.
- do not force `generation.py` and image modules onto one monolithic extractor if their higher-level empty-response logging/classification remains intentionally different; only the shared response-shape traversal contract must be single-sourced.

Acceptance:

- text generation and image-related callers consume the same response-shape traversal implementation;
- no behavior regression in response-shape tests;
- module ownership becomes obvious from import direction.

### P0.4 Deduplicate small runtime helpers

Files in scope:

- `processing_runtime.py`
- `preparation.py`
- `state.py`

Required change:

- keep `state.py` as the authoritative source for default image-processing summary shape and remove redundant wrapper aliases that no longer add behavior;
- unify in-memory uploaded-file reconstruction;
- avoid creating a “misc utils” dump module.

Preferred target:

- upload-file reconstruction stays next to upload/runtime semantics;
- image summary defaults stay next to session/runtime state semantics in `state.py`.

Acceptance:

- each shared shape/helper has one authoritative implementation, with wrapper aliases retained only when they carry real behavior;
- import direction remains simple and acyclic.

### P0.5 Remove stale developer surface

Files in scope:

- `scripts/run_pic1_modes.py`
- any related documentation mentioning this script

Required change:

- either repair the script to call the current production image-processing surface or remove it if it no longer serves a supported workflow.

Decision rule:

- if the script supports active debugging workflows and can be restored cheaply, repair it;
- otherwise delete it rather than preserving a broken surface.

### P0.6 Reduce `app.py` branch repetition

Files in scope:

- `app.py`

Required change:

- centralize repeated `_mark_app_ready()` and `_schedule_stale_persisted_sources_cleanup()` tail calls into one helper or one controlled frame-finalization path;
- eliminate avoidable late imports when ownership can be made explicit without circular imports.

Acceptance:

- no UI behavior change;
- fewer repeated tail blocks;
- no new import cycle.

## 8.2 Priority P1: Upload and Preparation Contract Consolidation

Objective: make upload identity, normalization, and preparation reuse explicit and single-sourced.

### Problem

Upload handling currently spans multiple modules with overlapping responsibilities:

- `processing_runtime.py` owns normalization, token building, payload freezing, and in-memory upload rebuilding;
- `application_flow.py` re-enters normalization logic in the synchronous path;
- `preparation.py` reconstructs a similar in-memory uploaded file object for DOCX parsing.

### Target

Create one canonical upload/preparation helper surface with these properties:

- one normalization entrypoint;
- one identity/token rule set;
- one in-memory uploaded-file builder;
- clear distinction between source identity bytes and normalized processing bytes.

### Preferred implementation shape

The project does not need a large new subsystem. A small, explicit contract module is enough if it removes cross-module ambiguity.

Acceptable outcomes:

- keep these helpers in `processing_runtime.py` and make `preparation.py` consume them; or
- extract them into a small neutral module with an upload-focused name.

Not acceptable:

- leaving normalization/token semantics duplicated across multiple call sites;
- changing legacy `.doc` identity behavior to normalized-byte identity.

### Deliverables

1. A single authoritative upload normalization contract.
2. Clear separation between upload identity and normalized processing payload.
3. Reduced branch-specific logic inside `_prepare_run_context_core()`.
4. Tests covering sync and background preparation equivalence.

## 8.3 Priority P2: Orchestration Boundary Cleanup

Objective: simplify where high-level processing decisions live, without breaking the existing runtime model.

### Problem

The current orchestration story is readable only after following control across several modules:

- `app.py` decides many flow branches and background transitions;
- `app_runtime.py` mostly forwards worker/event/session bridging to `processing_runtime.py`;
- `application_flow.py` manages idle and preparation logic;
- `processing_runtime.py` owns upload freezing/normalization helpers plus worker/event plumbing;
- `processing_service.py` assembles worker dependencies;
- `document_pipeline.py` coordinates processing work.

This is not fully broken, but boundaries are not explicit enough. That drives late imports, duplicated helper wiring, and review friction when changing a single flow. In the current snapshot, `app_runtime.py` is particularly important to reassess because it acts more like a forwarding shell than a distinct ownership boundary.

### Target boundary contract

1. `app.py`
   - owns page composition and UI-triggered decisions only.
2. `application_flow.py`
   - owns input resolution, preparation flow, and idle-state decisions.
3. `processing_runtime.py`
   - owns event queues, worker start/stop primitives, upload freeze/normalization helpers, and runtime markers.
4. `app_runtime.py`
   - if retained, remains a thin Streamlit-facing adapter for applying runtime events/state helpers and nothing more.
5. `processing_service.py`
   - owns dependency assembly for worker execution and nothing UI-specific.
6. `document_pipeline.py`
   - owns processing execution over already prepared inputs.

### Required refactor direction

- reduce `app.py` to a composition root rather than a mixed orchestration shell;
- avoid moving Streamlit session mutation into modules that should remain runtime-agnostic;
- avoid pushing too much orchestration into `document_pipeline.py`, which should stay downstream of prepared inputs.

### Deliverables

1. A documented call graph for the normal processing flow.
2. An explicit decision on whether `app_runtime.py` stays as a minimal adapter or is collapsed, with the resulting ownership documented.
3. Removal of avoidable late imports introduced by fuzzy ownership.
4. Fewer top-level modules that need to be touched for a single orchestration change.

## 8.4 Priority P3: Image Pipeline State Model Narrowing

Objective: reduce mutation ambiguity in image processing without destabilizing the image pipeline.

### Problem

`models.py:ImageAsset` currently carries:

- original source payload;
- mutable analysis results;
- mutable redraw outputs;
- mutable validation state;
- compare-all variants;
- final decision metadata;
- logging serialization behavior.

This makes the object convenient but too broad. It increases the chance of partial mutation, stale fields, or unclear invariants.

### Target

Narrow lifecycle responsibilities so that a reader can distinguish:

- immutable source asset identity;
- runtime processing state;
- final selected output state.

### Preferred implementation shape

Two acceptable options:

1. keep `ImageAsset` as source-plus-final-state and introduce one runtime state container; or
2. keep `ImageAsset` mutable but extract compare/validation attempt state into a dedicated nested structure.

Option 1 is preferred if the delta remains modest and avoids a wide, risky rewrite.

### Non-goal within this phase

- do not redesign image generation algorithms or validation policies;
- do not rewrite all image modules around a new framework.

### Deliverables

1. A clearer state boundary for image processing mutations.
2. Smaller, more focused serializer/logging behavior.
3. Fewer unrelated fields on the main asset object.

## 8.5 Priority P3: Validation Harness Convergence

Objective: make real-document validation reuse production behavior more directly.

### Problem

`real_document_validation_structural.py` currently composes a partial runtime using adapters and inline orchestration assembly. It works, but it duplicates production wiring concepts and can drift.

`real_document_validation_profiles.py` also exposes configuration surface that is currently narrower in practice than its type surface suggests, for example around acceptance policy handling.

### Target

- validators should execute through a narrow production-compatible contract rather than rebuilding orchestration shape inline;
- registry schema should expose only real, supported runtime choices.
- `expected_acceptance_policy` should either become a real enforced contract or be removed from the registry/type surface.

### Required implementation direction

- identify the minimal production contract that structural validation needs;
- move structural validation to that contract rather than importing a large set of low-level production pieces directly;
- prune or tighten registry/config fields that are technically present but not meaningfully variable today, especially `expected_acceptance_policy` if enforcement is not added.

### Deliverables

1. Reduced drift between app execution and validation execution.
2. Smaller adapter surface in the structural validator.
3. Clearer registry semantics.
4. No dead validation-policy field that appears configurable but does not affect runtime behavior.

## 9. Implementation Sequence

Implementation should be delivered in small, reviewable PRs.

### PR-1: Runtime Safety and Duplication Cleanup

- lock-protect `config.py:get_client()`;
- deduplicate response parsing into a neutral helper;
- remove redundant small helper wrappers and unify remaining helper duplicates;
- remove duplicate raise branch in `generation.py`;
- repair or remove stale `run_pic1_modes.py`.

### PR-2: Upload and Preparation Consolidation

- remove sync-path duplicate normalization;
- make preparation consume the canonical upload helper contract;
- add or refine tests for sync/background equivalence and legacy `.doc` identity semantics.

### PR-3: `app.py` Frame and Flow Cleanup

- centralize end-of-frame finalization;
- reduce repeated branch tails;
- eliminate avoidable late imports that are no longer necessary after PR-2.

### PR-4: Orchestration Boundary Narrowing

- align `app.py`, `application_flow.py`, `processing_runtime.py`, `app_runtime.py`, `processing_service.py`, and `document_pipeline.py` with the target boundary contract;
- make an explicit keep-or-collapse decision for `app_runtime.py` based on whether it still owns a meaningful boundary;
- document the resulting call graph in the spec or follow-up docs if needed.

### PR-5: Image Pipeline State Narrowing

- reduce `ImageAsset` lifecycle overload;
- migrate image modules incrementally to the narrower state contract.

### PR-6: Validation Harness Convergence

- route structural validation through the narrow production contract;
- tighten registry/config semantics and related tests/docs.

## 10. Testing Strategy

Each PR must include only the smallest necessary test additions.

### Required verification themes

1. Config singleton safety
   - concurrent singleton initialization behavior;
   - unchanged error handling when `OPENAI_API_KEY` is missing.

2. Upload normalization and identity
   - sync path and background path equivalence;
   - one-pass normalization in the sync path;
   - stable legacy `.doc` token identity contract.

3. Responses API parsing
   - same supported output shapes as before;
   - unchanged empty/collapsed-output behavior.

4. App orchestration
   - no regression in visible idle/preparation/processing state transitions;
   - no regression in restart/completed-source handling;
   - `app_runtime.py` keep-or-collapse choice leaves a clearer and still-correct runtime call graph.

5. Image pipeline state migration
   - compare-all behavior preserved;
   - validation/fallback behavior preserved;
   - logging context remains complete enough for diagnostics.

6. Validation harness
   - structural validator still produces the same class of output artifacts;
   - registry-driven runtime override behavior remains correct;
   - no dead acceptance-policy field remains unless it is actually enforced.

### Verification commands/tasks

User-visible final verification must use existing VS Code test tasks.

Expected task usage:

- `Run Current Test File` for targeted file-level verification during each PR;
- `Run Full Pytest` after the final integrated phase or at agreed checkpoints;
- `Run Lietaer Real Validation` or the registry-driven validation tasks when a phase touches real-document validation behavior.

## 11. Risks and Mitigations

### Risk 1: Import cycles while extracting shared helpers

Mitigation:

- prefer neutral helper modules with narrow dependencies;
- do not move Streamlit-dependent helpers into cross-domain modules.

### Risk 2: Silent behavior change in response parsing

Mitigation:

- move code first, then simplify only after equivalence is covered by tests.

### Risk 3: Breaking legacy `.doc` token identity

Mitigation:

- explicitly preserve source-byte-based identity semantics;
- keep the existing stability test as a protected regression.

### Risk 4: Over-refactoring `app.py`

Mitigation:

- first centralize repeated tails and imports;
- do not split UI code into speculative presenter layers unless ownership reduction is concrete.

### Risk 5: Wide image-pipeline churn

Mitigation:

- defer image-state narrowing until after runtime/orchestration cleanup;
- keep state migration incremental and serialization-compatible where possible.

### Risk 6: Validator drift during refactor

Mitigation:

- converge validators onto a narrow production contract instead of preserving a parallel orchestration fork.

## 12. Acceptance Criteria

This initiative is complete when all of the following are true:

1. The validated P0 issues are removed.
2. Upload normalization and identity semantics are single-sourced.
3. `app.py`, `application_flow.py`, `processing_runtime.py`, `processing_service.py`, and `document_pipeline.py` have a documented and visible ownership split, and `app_runtime.py` is either reduced to a minimal adapter or intentionally removed.
4. Shared Responses API parsing no longer lives in duplicate implementations.
5. The image pipeline no longer relies on one overly broad mutable asset structure for every lifecycle concern.
6. Structural validation consumes a tighter production contract with less inline orchestration assembly, and validation registry surface no longer advertises dead policy knobs.
7. The existing protected contracts remain intact unless explicitly updated as part of an approved change.

## 13. Deferred Items

The following items are intentionally deferred unless later evidence elevates them:

- broader decomposition of `document_pipeline.py` beyond what is needed to clarify orchestration boundaries;
- cleanup of thin wiring tests unless they directly obstruct refactoring confidence;
- speculative optimization work not tied to a measured bottleneck;
- UI redesign or component-library style changes.

## 14. Recommended Execution Order

If implementation begins from this spec, the recommended order is:

1. P0 runtime safety and duplication cleanup.
2. P1 upload/preparation contract consolidation.
3. P2 orchestration boundary cleanup.
4. P3 image-state narrowing.
5. P3 validation harness convergence.

This order is deliberate. It removes cheap risk first, then consolidates shared contracts, then applies larger architectural cleanup on top of a more stable base.
