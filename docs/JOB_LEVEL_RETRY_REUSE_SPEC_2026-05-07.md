# Job-Level Retry Reuse Spec

Date: 2026-05-07
Status: Implementation in progress

## Problem

The core durable retry slice is now implemented. The chapter review flow supports three practical retry levels with defined precedence:

- segment-level `Retry Failed` for failed segments from the current session;
- current-session job-level narrowing when the visible block journal (`run_log`) clearly identifies failed jobs inside those failed segments.
- persisted job-level narrowing for the same prepared document identity when current-session journal evidence is no longer available.

The remaining Phase 3 follow-up is narrower now:

- explicit `stopped` persistence still depends on finding a stop boundary that truly knows the active in-flight `job_id`;
- prompt enrichment is now block-aware during execution, but persisted per-segment continuity handoff still does not exist.

## Current State

### Existing working behavior

- `ui/structure_review_panel.py` can build a retry payload from failed segments.
- The same helper now resolves retry candidates with precedence `current-session run_log -> persisted job registry -> segment fallback`.
- `runtime/artifacts.py` persists and loads job-result records under `.run/job_results/…`, preferring payload `updated_at` over filesystem mtime when selecting the latest record per `job_id`.
- `pipeline.job_results.persist_terminal_job_result(...)` already writes terminal `completed` and `failed` job outcomes with `updated_at`, `block_index`, `target_chars`, and `context_chars` when available.
- `processing/preparation.py` now populates `DocumentContextProfile.detected_author` from DOCX core properties when reliable metadata exists on the source bytes.
- Segment-scoped actions now fail fast when the current prepared identity advertises `segment_job_mapping_incomplete`, so stale cross-boundary jobs are not reused for `Process Selected` or `Retry Failed`.
- Prompt enrichment now works at two levels: selected/retry launches append run-scoped chapter scope and immediate neighboring segment titles to `document_context_prompt`, and block execution appends current-segment framing plus previous/next segment titles to the effective generation prompt for each translated block.
- Direct regression coverage now protects deterministic `segment_id`, `boundary_fingerprint`, and `structure_fingerprint` behavior in `tests/test_preparation.py`.

### Current gaps

- Explicit `stopped` persistence is still not wired. The current stop check in block execution happens before the next job starts, so the default stop boundary only knows the last completed block index, not a reliable active in-flight `job_id`.
- Reliable author extraction is currently DOCX-only. PDF/DOC and other non-DOCX paths still do not expose trustworthy author metadata through the current extraction/runtime contract.
- Prompt enrichment now provides current-run continuity through block framing plus previous completed segment summary, but there is still no persisted per-segment summary handoff across runs.

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

1. Keep the existing `job_id` and persisted job-result registry contract stable.
2. Decide whether any stop boundary can surface an active in-flight `job_id` without a broad pipeline refactor; only then add explicit `stopped` persistence.
3. Decide whether the current run-scoped plus block-scoped continuity should gain persisted per-segment handoff across runs, rather than only current-run state.
4. Keep captions, tests, and spec text aligned with the already-implemented retry precedence and registry behavior.

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

## Adjacent Follow-Up Backlog

These items were re-checked against the current code after multiple chapter-workflow reviews. Only still-relevant gaps are tracked here; already implemented or stale review comments are intentionally excluded.

### P0. Reconcile the canonical reassembly contract

- The chapter-workflow spec still points to `src/docxaicorrector/document/reassembly.py`, while the implementation lives in `src/docxaicorrector/pipeline/reassembly.py`.
- The current reassembly manifest also drifted from the chapter-workflow spec example: runtime payloads already include `source_token` and `run_id`, but `coverage.paragraph_ranges` uses structured range objects and `segments[]` does not yet expose the richer per-segment artifact/status shape shown in the spec.
- Resolve this as one contract change: either move/alias the module and align the runtime manifest to the documented shape, or update the chapter-workflow spec and tests to the implementation contract.

### P1. Complete chapter-scoped prompt context enrichment

- Selected and retry runs now append selected chapter scope plus immediate previous/next segment titles to the shared `document_context_prompt`.
- `_build_document_context_profile(...)` now populates `detected_author` from DOCX core properties when reliable source metadata exists.
- Prompt enrichment now injects per-job continuity during execution through current block framing and previous completed segment summary.
- Required follow-up: extend author extraction beyond DOCX when reliable non-DOCX metadata becomes available, and decide whether continuity needs persisted per-segment handoff across runs.

### P3. Clean up transitional compatibility surface once contracts settle

- `DocumentContextProfile.__init__(..., outline_entries=...)` still accepts the legacy alias in addition to `segment_outline`.
- Session/UI guidance in the chapter-workflow spec still mentions optional keys such as `expanded_segment_ids` and `reassembly_mode`, while the implementation derives that behavior without dedicated stored keys.
- After the chapter workflow contract stabilizes, either remove these compatibility leftovers from code or make them explicit in the canonical spec instead of leaving them ambiguous.

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

This change crosses multiple runtime, pipeline, artifact, and UI boundaries. Implementation is now in progress and should continue against this specification in small, validated slices.