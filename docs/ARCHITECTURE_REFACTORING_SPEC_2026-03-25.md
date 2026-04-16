# Architecture Refactoring Spec

Date: 2026-03-25
Status: Proposed
Scope type: next-wave monolith boundary cleanup and contract hardening
Primary inputs: `docs/archive/specs/CODEBASE_MAINTAINABILITY_IMPLEMENTATION_SPEC_2026-03-24.md`, `docs/STARTUP_PERFORMANCE_CONTRACT.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md`, `docs/architecture/normal_processing_call_graph.md`

## 0. Review-Validated Current State

This spec is still active, but parts of the baseline have already shifted in code.

Confirmed in the current repository state as of 2026-04-16:

1. upload-contract vocabulary already exists in code via `NormalizedUploadedDocument`, `ResolvedUploadContract`, and `FrozenUploadPayload`;
2. `app_runtime.py` is already a materially thin Streamlit-facing adapter rather than a second orchestration center;
3. validation registry and structural-tier architecture have already landed far enough that this spec should treat them as maintained seams to tighten, not as greenfield architecture to invent.

Still open and still relevant from this spec:

1. `document.py:_read_uploaded_docx_bytes()` still performs a redundant `normalize_uploaded_document()` call instead of consuming the canonical resolved upload boundary;
2. `processing_runtime.py:_reset_image_state()` still directly mutates session state owned conceptually by `state.py`;
3. runtime/session ownership is still spread across `processing_runtime.py`, `state.py`, `application_flow.py`, and `app.py` enough to justify the P0 workstreams.

Reading rule for this document:

1. keep the P0 ownership fixes as the immediate priority;
2. read the later validation and adapter sections as cleanup and convergence work on top of an already-improved baseline, not as evidence that those areas remain wholly unimplemented.

## 1. Problem Statement

The repository is now materially cleaner than the earlier refactor waves, but the remaining maintenance cost is still architectural rather than purely local.

The application works, the current tests are meaningful, and the monolith remains the correct deployment shape. However, several core concerns still span too many modules or depend on transitional adapters:

- upload normalization, prepared-input assembly, and in-memory upload reconstruction are conceptually one contract, but the call flow still crosses `application_flow.py`, `processing_runtime.py`, `preparation.py`, and `document.py` in a way that requires engineers to remember multiple ownership rules at once;
- runtime event transport, session mutation, restart/completed-source persistence, and Streamlit-facing worker lifecycle are cleaner than before, but `app.py`, `app_runtime.py`, `processing_runtime.py`, and `state.py` still expose a boundary that is understandable only after reading several files together;
- `processing_service.py` is no longer entangled with `app_runtime.py`, but it still carries a broad dependency-assembly surface and some mixed concerns between worker wiring, production facade duties, and runtime-specific helpers;
- validation entrypoints now reuse production-compatible paths, but the structural/full validation layer still has room for tighter boundary naming and thinner seams to reduce future drift;
- the codebase still contains transitional shapes and broad public surfaces whose semantics are stable in practice but not yet reduced to the smallest credible ownership model.

This wave is needed not because the current system is broken, but because future changes will keep getting more expensive unless the remaining ownership seams are simplified while current contracts are still fresh and validated.

This specification defines the next architecture refactoring wave that engineers can begin immediately without redesigning the product, breaking startup behavior, or splitting the monolith.

## 2. Goals

1. Clarify and reduce the remaining ambiguous ownership seams in upload preparation, runtime/session transitions, and processing service assembly.
2. Make the prepared-input contract explicit enough that downstream processing never needs to infer or recreate upload semantics.
3. Narrow Streamlit-facing adapter code so the UI entrypoint remains orchestration-focused rather than runtime-contract-aware.
4. Keep validation and real-document tooling aligned with production contracts rather than allowing parallel orchestration paths to reappear.
5. Reduce the cognitive load for future feature work by making module responsibilities more obvious from file names and public APIs.
6. Preserve existing user-visible behavior, runtime workflow, and performance-sensitive startup characteristics.

## 3. Non-Goals

This spec does not authorize the following:

- splitting the repository into services, packages, or microservices;
- replacing Streamlit, replacing the worker model, or introducing async/event-loop architecture for its own sake;
- changing the WSL-first runtime contract;
- changing the startup performance contract except for directly defensive fixes that preserve or improve current startup behavior;
- redesigning image processing algorithms, prompt strategy, or validator policy as part of architectural cleanup alone;
- broad file churn that only renames symbols without reducing boundary ambiguity;
- introducing generic framework layers, plugin systems, registries, or domain abstractions without at least two real consumers and an immediate ownership benefit.

## 4. Protected Contracts

The following repository contracts remain protected throughout this wave.

1. WSL-first runtime remains the canonical runtime for development, diagnostics, tests, and live validation. The source of truth stays `/mnt/d/www/projects/2025/DocxAICorrector` inside WSL together with project `.venv`.
2. Startup performance contract in `docs/STARTUP_PERFORMANCE_CONTRACT.md` remains in force. No new heavy synchronous work may be added to early `app.py` startup paths, and one-time resource caching must remain intact.
3. Upload normalization contract in `docs/WORKFLOW_AND_IMAGE_MODES.md` remains in force. Legacy `.doc` identity tokens remain source-byte-based, while downstream processing continues to consume normalized DOCX bytes.
4. The application remains a monolith. Refactoring may improve boundaries inside the monolith, but must not introduce distributed architecture or faux-service decomposition.
5. Real-document validation remains a supported verification layer and must continue to reflect production-compatible execution paths.
6. Existing user-visible workflow contracts for preparation, processing, restart, and completed-source reuse remain behaviorally stable unless a task explicitly documents a justified change and its acceptance criteria.

Any change-set that appears to pressure these contracts must explicitly reference the contract being protected and explain why the change does not violate it.

## 5. Current-State Hotspot Summary

The current repository snapshot suggests the next hotspot set is narrower and more structural than the previous wave.

### 5.1 `application_flow.py`

- Owns valid preparation orchestration, but still combines flow coordination with some contract-level preparation decisions.
- Contains restart/completed-source helpers that are useful, but they broaden the module beyond pure run-context assembly.
- The distinction between "prepare the document" and "resolve a prepared upload contract" is present in code but not yet explicit enough as a first-class boundary.
- Restart/completed-source ownership is materially cleaner than before, but not fully centralized yet: `processing_runtime.py` remains the primary transition owner, while `application_flow.py`, `state.py`, and `app.py` still participate in narrower read/write paths that should be made more explicit.

### 5.2 `processing_runtime.py`

- Correctly owns upload normalization, event transport, background runtime primitives, and restart/completed-source transitions.
- Has grown into a very broad runtime owner: normalization, token identity, runtime events, session application, persistence transitions, worker bootstrapping, and markers all live in one module.
- The module is internally coherent, but the public surface is broad enough that future drift is likely unless sub-boundaries are made more explicit.
- Contains `_reset_image_state()` which directly mutates session state keys that also belong to `state.py` — a minor ownership overlap that should be reconciled during P0.2.

### 5.3 `app_runtime.py`

- Is intentionally thin, but still acts as a forwarding layer with many near-pass-through exports.
- Its continued existence is justified only if it remains a clearly Streamlit-facing adapter and does not grow back into a second runtime ownership center.
- This is a hotspot because adapter thinness tends to regress over time unless the allowed surface is explicitly constrained.

### 5.4 `processing_service.py`

- Correctly owns dependency assembly for background processing and a production-compatible facade used by validation.
- Still exposes a relatively broad object graph and multiple responsibilities: service singleton lifecycle, collaborator assembly, worker facade, and production-compatible convenience entrypoints.
- It is a prime candidate for boundary tightening, but not for speculative generalization.

### 5.5 Validation entrypoints

- `real_document_validation_structural.py` and `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` now depend on shared service-level execution paths.
- Remaining risk is not major correctness divergence, but gradual drift in reporting shape, runtime-facade assumptions, or helper ownership if future work reintroduces validator-only branches.

### 5.6 `app.py`

- Remains the correct composition root.
- Direct session mutations are minimal (3 lines: `persisted_source_cleanup_done`, `latest_preparation_summary`, `app_start_logged`); however, `app.py` still reads and reasons about runtime markers and persistence state such as `preparation_input_marker`, `preparation_failed_marker`, `processing_outcome`, `restart_source`, and `completed_source` — this is the primary coupling concern, not bulk session writes.
- Any architecture work that increases `app.py` knowledge of lower-level contracts would be a regression.

### 5.7 `formatting_transfer.py`

- Imports 12 shared symbols from `document.py`: 8 private (`_`-prefixed) helpers (`_is_image_only_text`, `_detect_explicit_list_kind`, `_find_child_element`, `_get_xml_attribute`, `_infer_heuristic_heading_level`, `_is_likely_caption_text`, `_resolve_paragraph_outline_level`, `_xml_local_name`) plus 4 public constants.
- The 8 private helper imports represent an unstable coupling boundary: any internal refactoring of `document.py` silently breaks `formatting_transfer.py`.
- This is a real ownership problem — `document.py`'s private API is the de facto public API for formatting transfer.
- Not a blocking concern for this wave, but should be acknowledged and tracked.

### 5.8 `state.py` — asymmetric contract

- Owns 8 write/mutation helpers (`push_activity`, `set_processing_status`, `append_log`, etc.) but zero read helpers.
- Consumers (`ui.py`, `app.py`, `processing_runtime.py`) read 30+ session state keys via raw `st.session_state.get(...)` with no contract enforcement.
- This asymmetry means any session key rename requires grep-and-fix across the codebase; a read-helper surface would centralize breakage detection.

### 5.9 Verified implementation baseline for this wave

The following current-state facts are treated as verified baseline context for implementation planning:

- `processing_runtime.py` currently exposes 41 public top-level symbols and is the broadest remaining runtime boundary in the repo;
- `app_runtime.py` currently exposes 14 public adapter functions, all of which are forwarding or binding helpers over `processing_runtime.py` + `state.py`;
- `runtime_events.py` currently defines 10 frozen event types (`SetStateEvent`, `ResetImageStateEvent`, `SetProcessingStatusEvent`, `FinalizeProcessingStatusEvent`, `PushActivityEvent`, `AppendLogEvent`, `AppendImageLogEvent`, `WorkerCompleteEvent`, `PreparationCompleteEvent`, `PreparationFailedEvent`);
- no import cycle was found across the main hotspot modules for this wave: `app.py`, `app_runtime.py`, `application_flow.py`, `document.py`, `formatting_transfer.py`, `preparation.py`, `processing_runtime.py`, `processing_service.py`, `runtime_events.py`, `state.py`, `ui.py`;
- `app.py` currently performs exactly 3 direct session writes (`persisted_source_cleanup_done`, `latest_preparation_summary`, `app_start_logged`), so this wave must optimize ownership clarity rather than chase raw write-count reduction.

## 6. Design Principles

Implementation in this wave must follow these principles.

1. Preserve the monolith and improve its internal seams instead of simulating distributed architecture.
2. Prefer explicit ownership over abstract layering. If one concern has one owner, state that directly in code and tests.
3. Keep the prepared-input boundary authoritative. Downstream pipeline code must consume prepared inputs, not recreate upload semantics.
4. Do not solve broad modules by scattering tiny utility modules without a clear contract advantage.
5. Keep `app.py` as the composition root, not as a contract owner for normalization, persistence, or worker internals.
6. Protect startup performance by keeping new work off the first useful render path.
7. Reuse production paths in validation and diagnostics wherever feasible.
8. Prefer contract-revealing names and small public surfaces over deep abstraction trees.
9. No overengineering: introduce a new type, module, or facade only when it removes real ambiguity in current code.

### 6.1 Dependency Direction Rule

- UI-facing modules may depend inward on runtime/service/domain modules.
- Runtime/service/domain modules must not depend back on Streamlit page composition concerns.
- Validation tooling may depend on production-compatible facades, but production modules must not absorb validator-specific reporting policy.
- Downstream pipeline modules must never become alternate owners of upload normalization, session-state mutation, or restart persistence semantics.

### 6.2 Contract Narrowing Rule

- Each wave item must either reduce a public surface, reduce an ownership overlap, or make a protected contract more explicit.
- A change that only moves code without clarifying ownership is not sufficient.

## 7. Target Architecture For This Wave

The target is a clearer monolith, not a redesigned system.

### 7.1 Desired boundary model

- `app.py` remains the Streamlit composition root and UI orchestration entrypoint.
- `app_runtime.py` remains only if it is a narrow Streamlit adapter over runtime/session helpers; otherwise it should shrink further, not expand.
- `processing_runtime.py` remains the owner of runtime event transport and upload/runtime contracts, but its internal public seams should be partitioned more intentionally.
- `application_flow.py` owns run-context orchestration and top-level preparation decisions, but not lower-level upload contract semantics.
- `preparation.py` owns prepared-document assembly and cache semantics once normalized input bytes are already known.
- `processing_service.py` owns collaborator assembly and service facade behavior for worker/validation entrypoints, but not UI policy or session-state semantics.
- `document_pipeline.py` remains the prepared-input consumer and document-processing orchestrator.

### 7.2 Structural target for this wave

This wave should leave the codebase in the following shape:

1. One explicit prepared-upload contract boundary that `application_flow.py`, `processing_runtime.py`, and `preparation.py` all consume consistently.
2. One explicit runtime-session transition boundary for preparation completion/failure, processing completion, restart persistence, and completed-source transitions.
3. A smaller and more intentional `app_runtime.py` surface, documented by tests as adapter-only behavior.
4. A tightened `processing_service.py` surface that distinguishes collaborator assembly from execution facade methods.
5. Validation entrypoints that continue to consume production-compatible service facades and do not reach lower-level runtime mechanics except through documented adapters.

### 7.3 Explicitly rejected target for this wave

The following outcomes are considered regressions:

- a new `core/`, `services/`, or `adapters/` hierarchy created mainly for aesthetics;
- multiple new wrapper modules that only forward calls and add naming indirection;
- runtime/session ownership split between `app.py`, `app_runtime.py`, and `processing_runtime.py` more than it is today;
- downstream pipeline code gaining new responsibility for upload normalization or identity-token semantics;
- startup-sensitive work being moved earlier in `app.py` in the name of architectural neatness.

## 8. Prioritized Workstreams

## P0 - Freeze and narrow protected seams

Objective: make the next wave safe by locking down the boundaries most likely to regress under refactoring.

### P0.1 Prepared upload contract extraction and naming hardening

Files in scope:

- `processing_runtime.py`
- `application_flow.py`
- `preparation.py`
- `document.py`
- `tests/test_processing_runtime.py`
- `tests/test_application_flow.py`
- `tests/test_preparation.py`

Tasks:

- introduce or formalize a single named contract for "resolved normalized upload plus source identity" and make its use obvious at call sites;
- remove any remaining call-site ambiguity between raw uploaded file handling and already-resolved prepared upload handling;
- make preparation helpers accept the narrowest credible normalized/prepared input surface rather than a mix of raw and normalized assumptions;
- ensure `document.py` continues to consume the shared normalizer boundary rather than inventing an alternate upload path;
- **concrete fix required:** remove the redundant `normalize_uploaded_document()` call inside `document.py:_read_uploaded_docx_bytes()` — this is a live double-normalization path where bytes that were already normalized by `resolve_upload_contract()` are normalized again during paragraph extraction; for `.docx` the second pass is identity, but for legacy `.doc` it re-invokes conversion unnecessarily (the previous spec's `PERF-001` did not address this path).

Acceptance criteria:

- there is one clearly named canonical upload/prepared-input boundary used across sync and background preparation;
- no maintained code path performs a second authoritative upload normalization pass after the canonical boundary;
- specifically: `document.py:_read_uploaded_docx_bytes()` must not call `normalize_uploaded_document()` when receiving already-normalized bytes from the canonical upload contract;
- tests cover both `.docx` and legacy `.doc` identity semantics without changing the current contract;
- no startup path regresses.

Implementation notes:

- prefer tightening around the existing contract vocabulary (`NormalizedUploadedDocument`, `ResolvedUploadContract`, `FrozenUploadPayload`, `PreparedRunContext`) rather than introducing a second family of near-duplicate types;
- the likely boundary split is: `processing_runtime.py` owns authoritative normalization/identity, `application_flow.py` owns run-context orchestration, `preparation.py` owns prepared-document assembly after normalized bytes are known;
- if a helper still accepts a raw uploaded file after this slice, that should be an explicit UI-entry exception rather than a hidden mixed contract.

### P0.2 Runtime-session transition ownership lock-down

Files in scope:

- `processing_runtime.py`
- `app_runtime.py`
- `state.py`
- `app.py`
- `tests/test_processing_runtime.py`
- `tests/test_app.py`
- `tests/test_state.py`

Tasks:

- identify the exact transition owners for preparation success/failure, processing completion, restart-source carry-forward, and completed-source cleanup;
- convert any remaining ad hoc session mutation patterns into owner-helper calls where the concern already has an owner;
- keep `app.py` orchestration-visible but reduce its need to reason about lower-level transition details.

Acceptance criteria:

- each transition family has one obvious owner in code;
- `app.py` does not gain new direct session mutation logic for runtime internals;
- `processing_runtime.py:_reset_image_state()` direct session writes are reconciled with `state.py` ownership (moved or delegated);
- adapter-only behavior in `app_runtime.py` is validated by tests;
- restart/completed-source behavior remains unchanged from a user perspective.

Default owner map for implementation:

- `processing_runtime.py` should remain the primary owner for background worker lifecycle, event draining/application, and restart/completed-source transition choreography;
- `state.py` should own the concrete read/write helpers for session keys once a key family has an explicit contract;
- `app_runtime.py` should only bind runtime primitives to state-owner functions or expose stable UI-facing entrypoints;
- `app.py` should decide when a transition is triggered, but not perform the transition mechanics inline.

## P1 - Tighten runtime and adapter boundaries

Objective: reduce the broad public surface of runtime/adapter modules without changing behavior.

### P1.1 Partition `processing_runtime.py` by public surface, not by speculative package structure

Files in scope:

- `processing_runtime.py`
- optionally one or two new focused modules if justified by current public surface, for example upload-contract or runtime-transition owners
- `app_runtime.py`
- `application_flow.py`
- `processing_service.py`
- tests covering all touched boundaries

Tasks:

- identify whether `processing_runtime.py` should remain one file with a reduced public API or split into one or two contract-revealing modules;
- if splitting, move only cohesive contract owners, such as upload contract logic or runtime transition application logic;
- keep import direction one-way and avoid circular adapter/runtime relationships;
- update call sites to use the narrowed public seam.

Acceptance criteria:

- any new module has a real ownership role and at least two real consumers or a clear reduction in ambiguity;
- `processing_runtime.py` no longer reads like a catch-all bag of runtime helpers;
- no new forwarding-only layer is added;
- existing tests pass with equal or better readability.

Implementation defaults for this slice:

- default decision: keep `processing_runtime.py` as one file unless an extraction produces a clearly named owner such as `upload_contract.py` or `runtime_transitions.py`;
- do not split purely by helper category (`utils`, `misc`, `helpers`) or by line count alone;
- if extracting, move one cohesive cluster at a time and keep the old module as a temporary delegator only within the same PR if needed for safe call-site migration;
- preferred first extraction candidates are the upload/normalization contract cluster and the runtime transition/drain cluster, because both already have multiple consumers and testable ownership semantics.

### P1.2 Reduce `app_runtime.py` to a documented adapter-only surface

Files in scope:

- `app_runtime.py`
- `app.py`
- `tests/test_app.py`
- `tests/test_processing_runtime.py`

Tasks:

- audit each `app_runtime.py` export and remove or collapse any export that does not justify a Streamlit-facing adapter role;
- keep only the functions that bind runtime primitives to session/state owner helpers or expose stable UI-facing worker entrypoints;
- make the adapter constraint explicit in docstring/tests.

Acceptance criteria:

- `app_runtime.py` is measurably smaller or semantically narrower;
- it does not become a second orchestration layer;
- `app.py` remains readable and does not absorb lower-level concerns as a side effect.

Implementation defaults for this slice:

- treat the current 14-function public surface as the baseline under review, not as a target count that must be preserved;
- keep wrappers that bind runtime primitives to `state.py` owners (`emit_*`, `drain_*`, `start_*`, stop/worker-status helpers) if removing them would force `app.py` to learn runtime internals or state-owner wiring;
- if a wrapper is retained, make its adapter role explicit by docstring/tests instead of renaming it cosmetically;
- if a wrapper is removed, the replacement call site must still keep `app.py` orchestration-focused and must not introduce direct binding of state-owner dependencies in page code.

## P2 - Tighten service facade and validation convergence

Objective: make the execution facade easier to extend safely without mixing responsibilities.

### P2.1 Narrow collaborator assembly inside `processing_service.py`

Files in scope:

- `processing_service.py`
- `document_pipeline.py`
- `real_document_validation_structural.py`
- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- `tests/test_processing_service.py`
- `tests/test_real_document_pipeline_validation.py`

Tasks:

- distinguish collaborator assembly concerns from public execution facade methods more clearly;
- reduce constructor/factory noise where possible without adding generic DI infrastructure;
- make validation-facing service cloning/facade usage more explicit and stable;
- keep service singleton and clone semantics behaviorally unchanged unless explicitly justified.

Acceptance criteria:

- `processing_service.py` responsibilities are easier to describe in one sentence;
- validation entrypoints continue to use production-compatible service execution paths;
- no validator-specific policy is pushed into production modules;
- worker execution behavior remains unchanged.

Implementation defaults for this slice:

- treat the current module as having three practical roles to clarify rather than redesign: dependency assembly, execution facade methods, and production-compatible validation entrypoints;
- prefer tightening collaborator construction through named helper builders or dependency bundles over introducing generic DI abstractions;
- preserve the existing service singleton/getter pattern unless a change removes real ambiguity in the same PR;
- keep validation-facing methods behaviorally aligned with production entrypoints even if internal helper names or assembly structure change.

### P2.2 Guard validation/reporting contract drift

Files in scope:

- `real_document_validation_structural.py`
- `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- `real_document_validation_profiles.py`
- `tests/test_real_document_pipeline_validation.py`
- `tests/test_real_document_validation_profiles.py`

Tasks:

- tighten shared helper usage for report/runtime config fields and service entrypoints;
- remove any remaining transitional naming or reporting alias if still present;
- ensure validation helpers consume narrow production-compatible contracts rather than low-level runtime details.

Acceptance criteria:

- validation reports use one canonical naming set;
- maintained validation entrypoints do not bypass the production-compatible service facade;
- real-document tooling remains aligned with production semantics.

## P3 - Cleanup, debt retirement, and guardrails

Objective: remove transitional clutter that remains after the main boundary work lands.

### P3.1 Retire transitional helpers and compatibility shims no longer justified

Files in scope:

- any touched runtime/service/validation modules
- corresponding tests
- only the minimum docs needed if public contracts actually change

Tasks:

- remove helper aliases, compatibility shims, or transitional wrappers that became unnecessary during P0-P2;
- reduce duplicated marker/session-field accessors where one canonical owner now exists;
- refresh local module docstrings where they materially aid future maintenance.

Acceptance criteria:

- no dead transitional path remains in maintained runtime/service code;
- each removed helper has test-backed confidence or replacement coverage;
- cleanup stays local and avoids broad churn.

### P3.2 Add regression guardrails for architecture-sensitive contracts

Files in scope:

- targeted tests only

Tasks:

- add behavior-level tests for prepared-upload boundary reuse, runtime transition ownership, and adapter-only boundaries where current coverage is weak;
- avoid spec-like documentation tests and thin wiring tests that do not protect behavior.

Acceptance criteria:

- new tests protect runtime/user-visible behavior or strong contract semantics;
- no low-signal spec-header tests are added to the main suite.

### P3.3 Promote shared `document.py` / `formatting_transfer.py` helpers to explicit public surface

Files in scope:

- `document.py`
- `formatting_transfer.py`
- `tests/test_document.py`
- `tests/test_format_restoration.py`

Tasks:

- audit the 12 shared symbols that `formatting_transfer.py` imports from `document.py`, with primary focus on the 8 private (`_`-prefixed) helpers;
- promote symbols with two or more real consumers to explicit public names (remove `_` prefix, add to `__all__` if used);
- do not create a new shared utility module unless the set is large enough to justify standalone ownership;
- keep internal-only helpers private.

Acceptance criteria:

- `formatting_transfer.py` no longer depends on `_`-prefixed internals of `document.py`;
- promoted symbols have stable, contract-compatible names;
- no new coupling is introduced between unrelated modules.

### P3.4 Add state read contract to `state.py`

Files in scope:

- `state.py`
- `ui.py` (primary consumer)
- `app.py` (secondary consumer)

Tasks:

- add read helpers for the most frequently accessed session keys (at minimum: `get_processing_status()`, `get_image_assets()`, `get_run_log()`, `get_activity_feed()`, `is_processing_stop_requested()`);
- migrate `ui.py` direct session reads to use the new helpers;
- keep `app.py` migration optional in this slice if the key set is large.

Acceptance criteria:

- `state.py` owns both read and write contracts for the primary session keys;
- `ui.py` no longer reads raw `st.session_state` keys that have a read helper;
- no behavioral change.

### P3.5 Guard `SetStateEvent` allowed-key surface

Files in scope:

- `runtime_events.py`
- `processing_runtime.py` (event drain)

Tasks:

- add an allowed-key set or assertion to `SetStateEvent` drain handling so that arbitrary session keys cannot be set by background workers through the generic escape hatch;
- keep the allowed-key set minimal and colocated with the drain logic.

Acceptance criteria:

- unknown keys in `SetStateEvent.values` trigger a warning or assertion during drain;
- existing event producers continue to work without modification.

Implementation notes:

- the initial allowed-key baseline should be derived from current maintained producers before any cleanup expands it;
- known currently used worker-set keys include at least `last_error`, `last_background_error`, `latest_markdown`, `processed_block_markdowns`, `latest_docx_bytes`, `latest_result_notice`, `image_assets`, `processed_paragraph_registry`, and `latest_marker_diagnostics_artifact`;
- the allowlist should remain colocated with the drain logic in `processing_runtime.py`, not hidden behind a generic registry or config file.

## 9. Specific Task Matrix

This section is the implementation-ready checklist by area.

### 9.1 Upload and preparation boundary

- Files: `processing_runtime.py`, `application_flow.py`, `preparation.py`, `document.py`
- Tasks: introduce explicit prepared-upload owner naming; narrow helper signatures; remove mixed raw-vs-normalized ambiguity; confirm background and sync preparation share the same contract surface
- Acceptance: one canonical normalization/prepared-upload path; legacy `.doc` token identity preserved; downstream processing receives normalized DOCX bytes only
- Current code anchors: `processing_runtime.normalize_uploaded_document()`, `processing_runtime.resolve_upload_contract()`, `application_flow._resolve_preparation_upload()`, `application_flow.prepare_run_context_for_background()`, `document._read_uploaded_docx_bytes()`

### 9.2 Runtime transition boundary

- Files: `processing_runtime.py`, `app_runtime.py`, `state.py`, `app.py`, `restart_store.py`
- Tasks: single-owner transition helpers for preparation completion/failure and processing completion lifecycle; keep `app.py` orchestration-only; avoid open-coded session transitions
- Acceptance: session transition ownership is obvious and stable; restart/completed-source behavior preserved
- Current code anchors: `processing_runtime.drain_processing_events()`, `processing_runtime.drain_preparation_events()`, `processing_runtime.start_background_processing()`, `processing_runtime.start_background_preparation()`, `state.reset_run_state()`

### 9.3 Service facade boundary

- Files: `processing_service.py`, `document_pipeline.py`, validation entrypoints
- Tasks: separate collaborator assembly from execution facade methods; keep validation using the same facade family; do not introduce generic DI framework
- Acceptance: production and validation paths remain converged; service module is smaller or easier to reason about
- Current code anchors: `ProcessingService.run_document_processing()`, `ProcessingService.run_processing_worker()`, `ProcessingService.run_prepared_background_document()`, `get_processing_service()`

### 9.4 Validation/reporting convergence

- Files: `real_document_validation_structural.py`, `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`, `real_document_validation_profiles.py`
- Tasks: tighten report field ownership; keep canonical runtime config/report names; ensure service-facade-only execution paths
- Acceptance: no maintained validator bypasses the shared production-compatible service facade

### 9.5 Document/formatting coupling boundary

- Files: `document.py`, `formatting_transfer.py`
- Tasks: promote private `_`-prefixed symbols consumed by `formatting_transfer.py` to explicit public names; keep internal-only symbols private; do not create a shared utility module unless the set exceeds ~8 promoted symbols
- Acceptance: `formatting_transfer.py` imports zero `_`-prefixed symbols from `document.py`; no behavioral change
- Current code anchors: `formatting_transfer.py` imports 8 private helpers and 4 public constants from `document.py`

### 9.6 State read contract

- Files: `state.py`, `ui.py`, optionally `app.py`
- Tasks: add read helpers for the 5 most-accessed session keys (`processing_status`, `image_assets`, `run_log`, `activity_feed`, `processing_stop_requested`); migrate `ui.py` raw reads; optionally migrate `app.py` reads
- Acceptance: `state.py` owns both read and write directions for primary session keys; `ui.py` direct session reads reduced by at least 50%
- Current code anchors: `ui.render_live_status()`, `ui.render_run_log()`, `ui.render_image_validation_summary()`, `ui.render_markdown_preview()`, `ui.render_partial_result()`

### 9.7 SetStateEvent guardrail

- Files: `runtime_events.py`, `processing_runtime.py`
- Tasks: add allowed-key assertion or warning during `SetStateEvent` drain; document allowed key surface colocated with drain logic
- Acceptance: unknown keys trigger visible warning; existing producers pass without change
- Current code anchors: `runtime_events.SetStateEvent`, `processing_runtime.emit_or_apply_state()`, `processing_runtime.drain_processing_events()`, worker producers in `document_pipeline.py` and `processing_service.py`

## 10. Recommended PR Slices

The wave should be delivered in small, behavior-safe PRs.

### PR slice 1 - prepared upload contract tightening

- scope: P0.1 only
- files: `processing_runtime.py`, `application_flow.py`, `preparation.py`, `document.py`, related tests
- purpose: make normalized upload/prepared-input ownership explicit before any broader runtime cleanup

### PR slice 2 - runtime transition ownership cleanup

- scope: P0.2 only
- files: `processing_runtime.py`, `app_runtime.py`, `state.py`, `app.py`, related tests
- purpose: reduce session mutation ambiguity while behavior is still easy to compare against current state

### PR slice 3 - runtime/adapter boundary narrowing

- scope: P1.1 and P1.2
- files: `processing_runtime.py`, optional focused runtime submodule(s), `app_runtime.py`, call sites, tests
- purpose: shrink and document the adapter/runtime public surfaces without changing contracts

### PR slice 4 - processing service facade tightening

- scope: P2.1
- files: `processing_service.py`, `document_pipeline.py`, validation consumers, tests
- purpose: make collaborator assembly and execution facade responsibilities easier to maintain

### PR slice 5 - validation/reporting convergence and debt cleanup

- scope: P2.2 and selected P3 items (P3.1, P3.2)
- files: validation entrypoints, tests, any local cleanup in touched modules
- purpose: finish convergence work and remove transitional leftovers only after primary boundaries have stabilized

### PR slice 6 - document/formatting boundary and state read contract

- scope: P3.3, P3.4, P3.5
- files: `document.py`, `formatting_transfer.py`, `state.py`, `ui.py`, `runtime_events.py`, `processing_runtime.py`, related tests
- purpose: stabilize the document/formatting_transfer coupling boundary, add state read helpers, and guard SetStateEvent allowed-key surface

## 11. Verification And Test Plan

All verification must respect the repository's WSL-first runtime contract.

### 11.1 Canonical command rules

- Use WSL project runtime at `/mnt/d/www/projects/2025/DocxAICorrector`.
- For agent-side shell execution from the repository environment, use `wsl -- bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest ...'` when direct execution is needed from the Bash tool.
- For canonical repo commands, the source of truth remains `bash scripts/test.sh ...` run inside WSL/official tasks.

### 11.2 Minimum per-PR verification

For PR slice 1:

```bash
bash scripts/test.sh tests/test_processing_runtime.py -q
bash scripts/test.sh tests/test_application_flow.py -q
bash scripts/test.sh tests/test_preparation.py -q
bash scripts/test.sh tests/test_document.py -q
```

For PR slice 2:

```bash
bash scripts/test.sh tests/test_processing_runtime.py -q
bash scripts/test.sh tests/test_app.py -q
bash scripts/test.sh tests/test_state.py -q
```

For PR slice 3:

```bash
bash scripts/test.sh tests/test_processing_runtime.py -q
bash scripts/test.sh tests/test_app.py -q
bash scripts/test.sh tests/test_application_flow.py -q
```

For PR slice 4:

```bash
bash scripts/test.sh tests/test_processing_service.py -q
bash scripts/test.sh tests/test_document_pipeline.py -q
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q
```

For PR slice 5:

```bash
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q
bash scripts/test.sh tests/test_real_document_validation_profiles.py -q
bash scripts/test.sh tests/test_real_document_validation_corpus.py -q
```

For PR slice 6:

```bash
bash scripts/test.sh tests/test_document.py -q
bash scripts/test.sh tests/test_format_restoration.py -q
bash scripts/test.sh tests/test_ui.py -q
bash scripts/test.sh tests/test_state.py -q
bash scripts/test.sh tests/test_processing_runtime.py -q
bash scripts/test.sh tests/test_app.py -q
```

### 11.3 Cross-cutting guard verification

After any change touching startup-sensitive imports or early app wiring:

```bash
bash scripts/test.sh tests/test_startup_performance_contract.py -q
bash scripts/test.sh tests/test_app.py -q
```

After any change touching upload normalization or runtime preparation boundaries:

```bash
bash scripts/test.sh tests/test_processing_runtime.py -q
bash scripts/test.sh tests/test_application_flow.py -q
bash scripts/test.sh tests/test_preparation.py -q
```

After any change touching production-compatible validation facade paths:

```bash
bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q
bash scripts/test.sh tests/test_processing_service.py -q
```

### 11.4 Full-wave confidence pass

At the end of the wave:

```bash
bash scripts/test.sh tests/ -q
```

And for real-document confidence when the touched slice affects validation-facing runtime/service seams:

- run the official visible real-document validation entrypoint for Lietaer or the relevant validation profile;
- confirm that production-compatible facade usage and report output still match current contract expectations.

## 12. Risks And Mitigations

### Risk 1: startup regression through seemingly harmless import movement

- mitigation: keep architecture edits off early `app.py` startup path; run `tests/test_startup_performance_contract.py`; review imports added to `app.py`, `config.py`, and `generation.py`

### Risk 2: accidental upload contract drift between sync, background, and validation paths

- mitigation: land prepared-upload boundary tightening first; test `.docx` and legacy `.doc` semantics explicitly; do not add alternate normalization helpers

### Risk 3: adapter cleanup pushes lower-level concerns back into `app.py`

- mitigation: treat `app.py` as composition root only; if removing an adapter function requires `app.py` to learn runtime internals, the slice is not ready

### Risk 4: runtime-session cleanup changes restart/completed-source behavior

- mitigation: keep behavior-level tests around processing completion and preparation completion flows; verify restart/completed-source user paths explicitly

### Risk 5: service tightening accidentally creates generic infrastructure

- mitigation: require every new type/module to justify a current ownership benefit; reject DI-framework or registry-style proposals without two immediate real consumers

### Risk 6: validation convergence silently regresses report compatibility

- mitigation: keep canonical report field names; run validation tests and one visible real-document validation flow for affected slices

### Risk 7: promoting `document.py` private helpers changes downstream behavior

- mitigation: promote only symbols already consumed by `formatting_transfer.py` with identical semantics; rename to stable names only if the `_` prefix removal is not sufficient; run `tests/test_document.py` and `tests/test_format_restoration.py` after each promotion

### Risk 8: state read helpers create verbose boilerplate without reducing coupling

- mitigation: start with the 5 most-read keys in `ui.py`; do not add read helpers for keys that are only read in one place; measure coupling reduction by the number of raw `st.session_state` accesses removed

## 13. Definition Of Ready

A task in this wave is ready to implement only if all conditions below are met.

1. The task names one concrete ownership ambiguity or public-surface problem.
2. The task lists the exact files in scope and avoids open-ended repo-wide churn.
3. The task identifies which protected contracts could be affected and how they will be protected.
4. The task has behavior-level acceptance criteria, not only code-movement goals.
5. The task has a bounded verification plan using canonical repo commands.
6. The task can land in a stable PR without depending on an all-at-once rewrite.

Not ready:

- "split big module because it is big";
- "create shared utils" without a named ownership problem;
- "clean architecture pass" without explicit file scope and acceptance criteria.

## 14. Recommended First Implementation Slice

Start with PR slice 1: prepared upload contract tightening.

Reasoning:

- it directly protects one of the most important current repository contracts: upload normalization;
- it reduces ambiguity for both sync and background preparation before touching broader runtime/session transitions;
- it has the lowest risk of startup regression because the main work stays in preparation/runtime boundaries rather than early app startup;
- it creates a cleaner foundation for later adapter and service tightening;
- it is small enough to verify with focused tests and can be reviewed without loading the full runtime stack at once.

### First-slice implementation target

- make the canonical resolved upload/prepared-upload contract the only visible input shape across preparation entrypoints;
- update `application_flow.py` and `preparation.py` signatures to reflect that contract clearly;
- keep `processing_runtime.py` as the normalization owner while making the handoff to preparation more explicit;
- add or strengthen tests that prove one normalization pass, preserved legacy `.doc` identity semantics, and normalized DOCX downstream payload behavior.

### First-slice done criteria

- the sync and background preparation flows consume the same named prepared-upload boundary;
- the repository has no maintained alternate normalization path in the touched area;
- focused tests pass via canonical repo commands;
- no unrelated files are changed.
