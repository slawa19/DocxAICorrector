# Codebase Maintainability Implementation Spec

Date: 2026-03-24
Status: Completed
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

Revalidation note against the current repository snapshot after the latest P0-P3 implementation waves:

- `REL-001`, `PERF-001`, `DUP-002`, `DUP-004`, and `DEAD-001` are now addressed in code;
- `APP-002` is only partially open: repeated frame-finalization tails in `app.py` have been centralized, but some avoidable late imports still remain and should be evaluated against the final ownership split rather than treated as closed by naming cleanup alone;
- `STALE-001` is addressed: `scripts/run_pic1_modes.py` now uses the supported service-level image-processing surface instead of the removed `app.process_document_images` surface;
- `DUP-003` is functionally resolved: `state.py` is the authoritative owner for the image-processing summary default shape and `processing_runtime.py` consumes that owner rather than maintaining a parallel default literal;
- `ARCH-001` is now closed in practice: `processing_service.py` no longer depends on `app_runtime.py`, validation entrypoints run through the shared production-compatible service facade, and the normal call graph remains documented without new ownership overlap;
- `DATA-001` is now closed for the runtime-attempt scope tracked by this spec: `ImageAsset` retains the broad public model, but runtime-attempt mutations now flow through the dedicated nested owner and its transition helpers rather than open-coded field mutation across orchestration paths;
- validation-harness convergence is now closed for both maintained entrypoints: `real_document_validation_structural.py` and `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` both consume the shared production-compatible execution facade instead of rebuilding low-level orchestration directly;
- report-surface ownership is now closed for runtime configuration reporting: `runtime_config` is the sole canonical field and the transitional `runtime_configuration` alias has been removed.
- the final real-document acceptance regression discovered after convergence is now closed: mapped paragraph direct alignment is preserved/restored again, and the latest Lietaer validation run passes `centered_short_paragraphs_preserved`.

### 5.1 Implementation Status Snapshot

Completed or effectively closed:

- lock-protected `config.py:get_client()`;
- single-sourced upload identity and normalization contract for sync/background preparation;
- shared Responses API traversal helpers extracted into `openai_response_utils.py`;
- in-memory uploaded-file reconstruction unified on the runtime-side owner;
- central frame-finalization helper introduced in `app.py`;
- `processing_service.py` boundary cleaned up so service/domain wiring no longer depends on `app_runtime.py`;
- structural validation switched to a narrow production-compatible facade;
- dead `expected_acceptance_policy` registry/runtime surface removed.

Final closure items completed in the closing implementation wave:

- `ImageAsset` runtime-attempt state now has a dedicated nested owner and orchestrators update it through owner helpers;
- the full real-document validation harness now runs through `ProcessingService.run_prepared_background_document(...)` via `clone_processing_service(...)` instead of manual low-level prepare/process orchestration;
- runtime configuration reporting now uses only `runtime_config` across structural and full validation reports;
- direct paragraph alignment from source paragraphs is now preserved in extracted paragraph units and restored for mapped output paragraphs, closing the centered-short-paragraph acceptance regression;
- this spec has been refreshed to reflect final closure status.

### P0 findings

- `REL-001`: closed. `config.py:get_client()` is now lock-protected with double-checked singleton initialization.
- `PERF-001`: closed. `_prepare_run_context_core()` now runs through one resolved upload path instead of re-normalizing in the sync path.
- `DUP-002`: closed. response parsing traversal is single-sourced in a neutral helper module.
- `DUP-003`: closed in practice. `state.py` is the default-shape owner and runtime code consumes that owner.
- `DUP-004`: closed. in-memory uploaded-file reconstruction is single-sourced on the runtime-side owner and `preparation.py` consumes that helper.
- `GEN-001`: closed. the redundant recovery-path raise duplication in `generation.py` has been removed.
- `APP-002`: partially closed. repeated frame-finalization calls have been centralized; remaining late imports should be revisited as part of final orchestration cleanup.
- `STALE-001`: closed. `scripts/run_pic1_modes.py` now uses the supported processing service surface.

### P1-P3 findings

- `ARCH-001`: closed. ownership is materially cleaner and the maintained validation entrypoints now consume the shared service facade instead of rebuilding low-level runtime wiring.
- `DATA-001`: closed for this spec scope. runtime-attempt state ownership is narrowed behind `ImageRuntimeAttemptState` plus owner helpers, and orchestration paths update the nested owner instead of open-coding those transitions.
- `BOUNDARY-001`: closed. both structural and full real-document validation entrypoints now use the narrow production-compatible service facade.
- `DEAD-001`: closed. `expected_acceptance_policy` has been removed from the registry and runtime type surface.
- `REPORT-001`: closed. `runtime_config` is canonical and `runtime_configuration` has been removed from maintained validation reports.

## 6. Design Principles

Implementation must follow these principles:

1. Fix root ownership problems before adding local patches.
2. Prefer one shared helper or contract over two “almost the same” call-site utilities.
3. Do not create a new abstraction layer unless at least two real consumers use it.
4. Keep public API movement incremental; each phase must leave the system in a stable, testable state.
5. Prefer production-path reuse over validator-only or debug-only orchestration forks.
6. Preserve current behavior first; behavior changes require an explicit acceptance section.

### 6.1 Dependency Direction Rule

Implementation must preserve one-way dependency direction.

- lower layers must not import UI-facing or adapter-facing modules;
- service/domain layers must not depend on `app_runtime.py`, `app.py`, or UI modules;
- `document_pipeline.py` and downstream processing modules must not depend on Streamlit session machinery, page composition helpers, or UI event transport details;
- adapter modules may depend inward on runtime/service/domain contracts, but inward layers must not depend back on adapters.

Forbidden outcome:

- solving ownership ambiguity by introducing a new bidirectional import path or by moving UI concerns into service/domain modules.

### 6.2 Session-State Ownership Rule

Session state must have a single writer per concern.

- each session key or state family must have one authoritative mutation owner;
- orchestrators may decide when a state transition happens, but they must call the owner contract instead of open-coding equivalent mutations;
- `application_flow.py` and other orchestration modules may coordinate transition timing, but must not become parallel writers for the same runtime/session-state concern;
- if a state value must be mirrored for compatibility during migration, one field remains canonical and the mirror must be treated as a temporary alias.

### 6.3 Source-of-Truth Ownership Rule

Each runtime concept must have one authoritative owner.

- one concept must not be represented by multiple equally authoritative helpers, fields, session keys, or report fields;
- if compatibility aliases are temporarily required, the canonical owner must be documented and all aliases must be explicitly marked transitional;
- duplicate field names, session keys, or report fields must not remain indefinitely once the canonical owner exists.

### 6.4 Orchestrator Responsibility Rule

Orchestrators coordinate when work happens, not the detailed semantics of how lower-level contracts work.

- orchestration modules may choose order, retries, and high-level flow branches;
- they must not reimplement normalization, persistence, parsing, or state-shape semantics that belong to lower-level owners;
- `document_pipeline.py` must operate on prepared inputs and must not silently recreate upload-preparation semantics downstream.

### 6.5 Boundary Justification Rule

Adapter layers must justify their existence with a real boundary role.

- a retained adapter layer must translate contracts, isolate framework/runtime coupling, or narrow a public facade;
- forwarding-only layers with no ownership, translation, or compatibility role should be collapsed;
- this rule applies specifically to `app_runtime.py` and to validator-side adapter surfaces.

## 7. Target Architecture

The target is not a large rewrite. It is a clarified boundary model.

### 7.0 Boundary and Ownership Clarifications

The following ownership rules apply across the target architecture:

- upload contract ownership: one upload/preparation contract owns source-byte identity, normalization, prepared payload shape, and in-memory uploaded-file reconstruction;
- preparation cache ownership: one preparation-layer owner must own cache key semantics, cache writes, and invalidation rules for prepared inputs;
- runtime event transport ownership: one runtime-layer owner must own background event queue creation, transport, and event application entrypoints;
- session-state mutation ownership: UI/session state mutations must flow through designated owner helpers rather than ad hoc writes across multiple modules;
- restart/completed-source persistence ownership: one runtime/session-state owner must own persisted-source lifecycle, including restart carry-forward, completion marking, and cleanup scheduling;
- validation facade ownership: validation entrypoints must consume one narrow production-compatible facade rather than assemble low-level runtime parts ad hoc.

If ownership for one of these concerns is moved during implementation, the new owner must be explicit in code and tests within the same PR.

### 7.1 UI Layer

`app.py` remains the Streamlit entrypoint and page composition root.

`app.py` should own:

- page config;
- top-level rerun flow;
- widget rendering order;
- user-facing control decisions.

`app.py` must not become the authoritative owner for restart/completed-source persistence semantics, upload normalization semantics, or background event transport semantics.

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

Prepared-input rule:

- once a document enters `document_pipeline.py` or any downstream processing stage, it must already be represented as a prepared input under the canonical preparation contract;
- downstream modules must not re-detect upload format, rebuild token semantics, or perform a second authoritative normalization pass;
- if a downstream conversion/cache artifact is needed for processing efficiency, it must derive from the prepared input contract rather than redefine it.

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

Additional boundary requirements:

- `application_flow.py` coordinates when preparation and runtime transitions occur, but does not own the semantics of upload normalization, persistence payload shape, or event transport;
- `processing_service.py` may assemble dependencies, but must not absorb UI/session-state policy;
- `document_pipeline.py` may coordinate processing stages, but must not become an alternate source of truth for upload, restart-persistence, or session-key semantics.

### 7.4 OpenAI Response Parsing Layer

OpenAI Responses API text extraction must live in one shared utility surface.

This utility should be neutral to text-generation vs image-generation callers. It should not remain embedded in `generation.py` and should not remain implicitly “owned” by `image_shared.py`, whose module name suggests image-domain ownership rather than general Responses API parsing.

Preferred target: extract shared response-shape parsing into a small dedicated module, for example `openai_response_utils.py` or an equivalent neutral helper module.

### 7.5 Image Pipeline State Layer

`ImageAsset` should continue to represent a document image unit, but mutable pipeline state should be narrowed.

Current status note:

- lifecycle snapshots and controlled mutation helpers already exist and are useful intermediate scaffolding;
- this does not by itself satisfy the target state while compare-all state, attempt state, validation state, and final-selection state still live on one broad mutable object.

The target is not necessarily to delete `ImageAsset`. The target is to stop using one object as all of the following simultaneously:

- source asset descriptor;
- working mutable pipeline record;
- compare-all variant container;
- final decision record;
- logging payload serializer.

Implementation may keep `ImageAsset` as the base document-facing shape and introduce one additional runtime state structure if that materially reduces mutation ambiguity.

Lifecycle invariants guidance:

- immutable source identity fields must not be repurposed after construction;
- runtime attempt state, validation state, and compare-all candidate state must have explicit ownership and reset rules;
- final selected-output state must be distinguishable from in-progress candidate state;
- logging/report serialization must not depend on partially mutated incidental fields when a more explicit finalized state exists.

### 7.6 Validation Harness Layer

Real-document validation should consume the narrowest possible production contract.

The structural harness should reuse production preparation/runtime helpers rather than recreating orchestration logic inline wherever practical. The goal is to reduce drift between validator behavior and application behavior without forcing the validator to depend on Streamlit session machinery.

Validation-facade rule:

- validation code must prefer a narrow production facade that exposes prepared-input execution and result capture;
- validation code must not wire together low-level runtime helpers ad hoc when the same behavior can be reached through the shared facade;
- if the facade is too wide or Streamlit-coupled, narrow the production facade rather than reproducing production wiring in validator-only code.

Current status note:

- `real_document_validation_structural.py` has already moved onto a production-compatible facade and now preserves the legacy `.doc` source-byte identity contract in that path;
- the full Lietaer/real-document runner under `tests/artifacts/real_document_pipeline/` still uses direct low-level preparation and processing wiring and therefore remains in scope for convergence.

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

Status update:

- upload-file reconstruction is already unified on the runtime-side owner;
- image summary defaults are already owned by `state.py`.

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

Status update:

- the repeated frame-finalization tail is already centralized via a dedicated helper;
- remaining work in this item is limited to justified late-import cleanup, not to the already-closed tail duplication itself.

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
- allowing `document_pipeline.py` or other downstream modules to accept raw upload objects as an alternate processing contract.

### Deliverables

1. A single authoritative upload normalization contract.
2. Clear separation between upload identity and normalized processing payload.
3. Reduced branch-specific logic inside `_prepare_run_context_core()`.
4. Tests covering sync and background preparation equivalence.
5. One explicit owner for prepared-input cache writes, reads, and invalidation rules if a preparation cache remains in use.

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

Forbidden outcomes:

- `app_runtime.py` remains as a forwarding-only layer with no translation or boundary role;
- service/domain modules import `app.py`, `app_runtime.py`, or UI modules;
- restart persistence, completed-source persistence, or session-state mutation remain split across multiple peer writers for the same concern;
- `document_pipeline.py` accepts raw uploads or reconstructs preparation semantics internally.

### Deliverables

1. A documented call graph for the normal processing flow.
2. An explicit decision on whether `app_runtime.py` stays as a minimal adapter or is collapsed, with the resulting ownership documented.
3. Removal of avoidable late imports introduced by fuzzy ownership.
4. Fewer top-level modules that need to be touched for a single orchestration change.
5. One explicit owner for restart/completed-source persistence lifecycle and one explicit owner for runtime event transport.

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

Field and alias rule:

- duplicate field names for the same lifecycle concept must be consolidated to one canonical field;
- if migration compatibility requires an alias, the alias must be documented as transitional and must not become a second writable source of truth;
- the same rule applies to session keys and report/output fields derived from image state.

### Non-goal within this phase

- do not redesign image generation algorithms or validation policies;
- do not rewrite all image modules around a new framework.

### Deliverables

1. A clearer state boundary for image processing mutations.
2. Smaller, more focused serializer/logging behavior.
3. Fewer unrelated fields on the main asset object.
4. Explicit lifecycle invariants for source identity, runtime attempt state, and finalized output state.

Remaining closure criteria:

- introduce one explicit runtime-attempt or compare-state owner rather than keeping those concerns as peer mutable fields on `ImageAsset`;
- ensure final-selection state and runtime-attempt state are not simultaneously writable through unrelated field mutation paths;
- remove the need to treat snapshot/helper additions as the only boundary, because the data model itself must reflect the boundary.

## 8.5 Priority P3: Validation Harness Convergence

Objective: make real-document validation reuse production behavior more directly.

### Problem

`real_document_validation_structural.py` currently composes a partial runtime using adapters and inline orchestration assembly. It works, but it duplicates production wiring concepts and can drift.

`real_document_validation_profiles.py` also exposes configuration surface that is currently narrower in practice than its type surface suggests, for example around acceptance policy handling.

Current remaining gap after recent implementation:

- structural validation has been converged onto the shared facade, but the full Lietaer/real-document runner still follows a validator-local wiring path;
- structural validation reports still expose both `runtime_config` and `runtime_configuration`, which violates the source-of-truth ownership rule unless one is explicitly transitional.

### Target

- validators should execute through a narrow production-compatible contract rather than rebuilding orchestration shape inline;
- registry schema should expose only real, supported runtime choices.
- `expected_acceptance_policy` should either become a real enforced contract or be removed from the registry/type surface.

### Required implementation direction

- identify the minimal production contract that structural validation needs;
- move structural validation to that contract rather than importing a large set of low-level production pieces directly;
- prune or tighten registry/config fields that are technically present but not meaningfully variable today, especially `expected_acceptance_policy` if enforcement is not added.

Forbidden outcomes:

- replacing one validator-only wiring fork with another low-level assembly path under a different module name;
- keeping broad low-level helper imports in the validator when a narrower production facade exists;
- preserving duplicate registry/report field names without a canonical owner and deprecation path.

### Deliverables

1. Reduced drift between app execution and validation execution.
2. Smaller adapter surface in the structural validator.
3. Clearer registry semantics.
4. No dead validation-policy field that appears configurable but does not affect runtime behavior.
5. Validation execution flows through a documented narrow facade, not ad hoc low-level production wiring.
6. One canonical runtime-config report field, with any compatibility alias explicitly deprecated and then removed.

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
    - import direction remains one-way from UI/adapters toward runtime/service/domain modules.

5. Image pipeline state migration
   - compare-all behavior preserved;
   - validation/fallback behavior preserved;
   - logging context remains complete enough for diagnostics.

6. Validation harness
    - structural validator still produces the same class of output artifacts;
    - registry-driven runtime override behavior remains correct;
    - no dead acceptance-policy field remains unless it is actually enforced.
    - validator entrypoints use the shared narrow production facade instead of ad hoc low-level wiring.
   - the full real-document runner entrypoint also converges on the same production-compatible facade rather than preserving a separate low-level assembly path.
   - only one runtime-config report field remains canonical once convergence is complete.

### Architectural verification expectations

In addition to behavior tests, each architectural PR should include the lightest practical verification for boundary cleanliness, for example:

- targeted tests around canonical owner helpers instead of duplicate call-site wiring tests;
- import- or module-level assertions where practical for critical forbidden dependencies;
- explicit tests that only the canonical field/session key/report field remains writable when aliases are transitional.

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

### Risk 4a: Cleaner names but unchanged ownership

Mitigation:

- reject refactors that only rename modules while preserving duplicate writers or duplicate semantic owners;
- require each phase to identify the authoritative owner for every moved concern.

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
8. Dependency direction is enforceable from code structure: lower layers do not import UI/adapters, and service/domain modules do not depend on `app.py`, `app_runtime.py`, or UI modules.
9. Session-state mutation, restart/completed-source persistence, and prepared-input cache ownership each have one explicit authoritative owner.
10. `document_pipeline.py` and downstream processing consume prepared inputs rather than reconstructing upload semantics.
11. Duplicate field names, session keys, or report fields either have one canonical owner with a documented deprecation alias or are removed.
12. The structural validator and the full real-document runner both execute through the same production-compatible facade class of contract rather than maintaining separate low-level orchestration wiring.

## 13. Deferred Items

The following items are intentionally deferred unless later evidence elevates them:

- broader decomposition of `document_pipeline.py` beyond what is needed to clarify orchestration boundaries;
- cleanup of thin wiring tests unless they directly obstruct refactoring confidence;
- speculative optimization work not tied to a measured bottleneck;
- remaining non-critical `app.py` late-import cleanup after the frame-finalization centralization;
- UI redesign or component-library style changes.

## 14. Recommended Execution Order

If implementation begins from this spec, the recommended order is:

1. P0 runtime safety and duplication cleanup.
2. P1 upload/preparation contract consolidation.
3. P2 orchestration boundary cleanup.
4. P3 image-state narrowing.
5. P3 validation harness convergence.

This order is deliberate. It removes cheap risk first, then consolidates shared contracts, then applies larger architectural cleanup on top of a more stable base.
