# Session State Ownership Matrix

Date: 2026-04-20
Scope: `P1a` first migrated key family from `docs/specs/CODEBASE_REFACTOR_FOLLOWUP_SPEC_2026-04-20.md`
Status: active ownership inventory

## Purpose

This matrix defines the first enforced ownership boundary for shared processing lifecycle and source-identity session keys.

The initial `P1a` goal is narrow on purpose:

1. centralize write ownership for the first migrated key family in `state.py`;
2. document temporary read exceptions that still exist at Streamlit composition edges;
3. provide a stable artifact for the whitelist-backed regression test.

## Ownership Rules

1. `state.py` is the long-term owner for all keys listed in this matrix.
2. Raw writes outside `state.py` for these keys are not allowed.
3. Temporary raw reads may exist only where explicitly listed in the whitelist section below.
4. `processing_runtime.py` may orchestrate start/stop behavior, but it must delegate owned state transitions to `state.py` helpers.

## Key Inventory

| key | owner module | canonical writer helpers | current reader callers | migration phase |
|---|---|---|---|---|
| `processing_outcome` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_preparation_complete()`, `apply_preparation_failure()`, `apply_processing_start()`, `apply_processing_completion()` | `state.get_processing_outcome()`, `application_flow.has_restartable_source()`, `app.main()` via `get_processing_outcome()` | `P1a` |
| `processing_worker` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()`, `apply_processing_completion()` | `processing_runtime.processing_worker_is_active()` | `P1a` |
| `processing_event_queue` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()`, `apply_processing_completion()` | `processing_runtime.drain_processing_events()` | `P1a` |
| `processing_stop_event` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()`, `apply_processing_completion()` | `processing_runtime.request_processing_stop()` via `state.request_processing_stop()` | `P1a` |
| `processing_stop_requested` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()`, `request_processing_stop()`, `apply_processing_completion()` | `state.is_processing_stop_requested()`, `app._render_processing_controls()` via helper | `P1a` |
| `latest_source_name` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()` | `processing_runtime.get_current_result_bundle()` | `P1a` |
| `latest_source_token` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()` | `processing_runtime.get_current_result_bundle()`, `app.main()` via `get_processing_session_snapshot()` | `P1a` |
| `selected_source_token` | `state.py` | `init_session_state()`, `apply_preparation_complete()`, `apply_processing_start()` | `application_flow.sync_selected_file_context()`, `state.apply_preparation_complete()` | `P1a` |
| `latest_image_mode` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()` | `app.main()` via `get_latest_image_mode()` | `P1a` |

## Temporary Read Whitelist

These are temporary raw-read exceptions still allowed during `P1a`.

| file | allowed raw read reason | sunset target |
|---|---|---|
| `application_flow.py` | `selected_source_token` comparison inside `sync_selected_file_context()` remains coupled to pre-processing file selection flow | revisit in `P1b` or earlier if file-selection state moves behind a typed store |
| `state.py` | owner module internals may read and write owned keys directly | long-term allowed owner surface |

## Enforcement Scope For Initial Test

The initial regression test checks only the keys in this matrix.

It fails when these keys are accessed through raw `st.session_state` outside:

1. `state.py`;
2. explicit temporary-whitelist locations listed above;
3. test files.

## Additional P1a Finding Captured During Implementation

The key family was previously split by lifecycle phase rather than by module ownership:

1. processing start lived in `processing_runtime.py`;
2. preparation completion and resets lived in `state.py`;
3. source-token reselection lived in `application_flow.py`.

`P1a` does not eliminate every legacy read path yet, but it establishes one authoritative write owner for the first migrated key family.
