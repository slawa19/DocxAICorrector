# Job-Level Retry Reuse Spec

Date: 2026-05-07
Status: Draft for approval

## Problem

The chapter review flow now supports two retry levels:

- segment-level `Retry Failed` for failed segments from the current session;
- current-session job-level narrowing when the visible block journal (`run_log`) clearly identifies failed jobs inside those failed segments.

That still leaves the main remaining Phase 3 gap open: there is no durable retry contract for failed jobs across reruns, browser refreshes, or later sessions working on the same prepared document identity.

Today the app has no persisted source of truth for per-job terminal outcomes. The only job-granular signal is the current-session `run_log`, which is intentionally ephemeral and UI-oriented.

## Current State

### Existing working behavior

- `ui/structure_review_panel.py` can build a retry payload from failed segments.
- The same helper can now narrow that payload to failed jobs when current-session `run_log` block entries contain unambiguous latest `ERROR` or `FAILED` statuses for the corresponding block indexes.
- `pipeline/reassembly.py` and `runtime/artifacts.py` already persist segment-level translated result records under `.run/segment_results/` keyed by `prepared_source_key` and `structure_fingerprint`.

### Current gaps

- There is no persisted job outcome registry.
- `run_log` is session-scoped, UI-facing, truncated, and not a safe cross-session retry source.
- Segment result records are intentionally aggregate artifacts; they do not encode per-job failure state.
- Selected-run payloads currently pass filtered jobs only; they do not expose a durable original job identity contract that can be reused independently of current in-memory order.

## Goals

1. Add a durable, same-document job outcome registry for retry decisions.
2. Allow `Retry Failed` to reuse failed-job-only information even after a rerun or session restart, as long as the prepared document identity is unchanged.
3. Keep the current session-scoped behavior as the first priority when fresher `run_log` evidence exists.
4. Preserve the current segment-level fallback when durable job-level evidence is missing or incomplete.

## Non-Goals

- No retry reuse across different documents.
- No retry reuse across different `prepared_source_key` or different `structure_fingerprint` values.
- No attempt to infer job failures from translated segment output artifacts.
- No redesign of full processing, reassembly, or output-mode semantics.
- No cross-machine or external storage sync.

## Proposed Architecture

### 1. Introduce a durable job identity contract

Prepared jobs need a stable identity that survives:

- selected-run filtering;
- full-run versus selected-run execution;
- later reload of the same prepared document state.

Proposed contract:

- each prepared job gains a canonical `job_id` string;
- `job_id` is created during preparation from the original prepared job list order and structural anchors, not from transient selected-run order;
- selected payload builders must preserve this `job_id` when jobs are filtered for selected runs or retry runs.

Recommended shape:

- `job_id = job_<zero_based_index>` for the initial internal contract;
- later expansion to richer semantic identity remains possible, but is not required for this slice because `prepared_source_key + structure_fingerprint + original prepared job list` already defines the stable scope.

This keeps the first persisted implementation simple and avoids introducing a hash-based identity system before it is needed.

### 2. Add a dedicated job result registry

Do not overload `.run/segment_results/` for per-job status.

Instead add a new registry:

- `.run/job_results/<prepared_source_key>/<structure_fingerprint>/<job_id>.job-result.json`

Each record should contain at minimum:

- `schema_version`
- `prepared_source_key`
- `structure_fingerprint`
- `job_id`
- `segment_id`
- `status` with terminal values such as `completed`, `failed`, `stopped`
- `updated_at`
- optional debugging fields like `block_index`, `error_code`, `error_message`, `target_chars`, `context_chars`

The loader returns the latest record per `job_id` for the exact prepared identity.

### 3. Persist job outcomes at terminal points only

Persist the job registry from the processing pipeline at the same points where terminal block outcomes are already known.

Write paths:

- successful block completion writes `completed` for that `job_id`;
- failed block completion writes `failed` for that `job_id`;
- explicit stop writes `stopped` only for the active in-flight `job_id` when that identity is known.

Do not persist intermediate `queued` or `processing` states in the first slice. Retry decisions only need terminal outcomes.

### 4. Retry resolution precedence

`Retry Failed` should resolve candidates in this order:

1. current-session `run_log` block journal
2. persisted job result registry for the same `prepared_source_key` and `structure_fingerprint`
3. current segment-level fallback

This preserves the freshest local evidence while still enabling durable retry reuse when the session journal is gone.

### 5. UI behavior

The chapter review panel should keep the current single `Retry Failed` action.

Behavioral rules:

- if current-session failed jobs are known, retry only those jobs;
- else if persisted failed jobs are known for the same prepared identity, retry only those jobs;
- else retry failed segments as today;
- the caption should explain which source is being used: current session, persisted retry state, or segment fallback.

No second button is needed in this slice.

## Module Boundaries And Dependency Direction

### Preparation / run-context layer

Affected modules:

- `processing/preparation.py`
- `ui/application_flow.py`

Responsibilities:

- add and preserve `job_id` on prepared jobs;
- ensure filtered selected payloads keep the original job identity.

### Runtime artifact layer

Affected modules:

- `runtime/artifacts.py`
- `core/constants.py`

Responsibilities:

- define job registry location;
- add writer/loader helpers for persisted job results.

### Pipeline / processing layer

Affected modules:

- `pipeline/contracts.py`
- `pipeline/setup.py`
- `pipeline/_pipeline.py`
- `pipeline/block_execution.py`
- `pipeline/late_phases.py` or the closest terminal-outcome helpers

Responsibilities:

- thread the job result writer dependency;
- emit persisted terminal outcomes using canonical `job_id`.

### UI retry layer

Affected modules:

- `ui/structure_review_panel.py`
- `ui/_app.py`

Responsibilities:

- load persisted failed-job state for the current prepared identity;
- merge it with current-session `run_log` evidence using the stated precedence;
- build retry payloads from job ids rather than only from failed segments when possible.

Dependency direction:

- UI reads persisted retry state through dedicated loaders.
- UI does not parse registry files directly.
- pipeline writes terminal outcomes; UI never writes job result artifacts.

## Consumer Update Plan

1. Add `job_id` to prepared jobs and selected-payload builders.
2. Add job result artifact writer/loader helpers and constants.
3. Thread a `write_job_result_registry` dependency through processing contracts.
4. Persist `completed` and `failed` terminal job records from the pipeline.
5. Teach `Retry Failed` to use persisted failed-job records when current-session journal evidence is missing.
6. Update captions/tests/spec references.

## What Does Not Change

- `selected_with_context`, `hybrid_document`, and `final_translated_book` contracts remain unchanged.
- Structure manifest import/export remains unchanged.
- Segment result registry remains segment-granular and continues to serve reassembly only.
- Same-session retry behavior remains valid even if the persisted registry is absent.

## Risks And Mitigations

### Risk: stale retry state after document preparation changes

Mitigation:

- hard-scope persisted job records by both `prepared_source_key` and `structure_fingerprint`;
- if either changes, persisted retry reuse is ignored.

### Risk: selected-run filtered order breaks job identity

Mitigation:

- derive `job_id` before any filtering and keep it on every downstream job payload.

### Risk: over-coupling retry state to visible journal formatting

Mitigation:

- use `run_log` only as the highest-priority session signal;
- durable retry state comes from a dedicated registry, not from journal parsing alone.

## Verification Criteria

Targeted verification:

- `tests/test_app_preparation.py`
- `tests/test_processing_service.py`
- `tests/test_document_pipeline.py`
- new artifact tests for job result registry persistence/loading

Type/static verification:

- `bash scripts/test.sh tests/test_typecheck.py::test_pyright_no_regression -q`

Final verification:

- `bash scripts/test.sh tests/ -q`

## Approval Gate

This change crosses multiple runtime, pipeline, artifact, and UI boundaries. Implementation should not begin until this specification is explicitly approved.