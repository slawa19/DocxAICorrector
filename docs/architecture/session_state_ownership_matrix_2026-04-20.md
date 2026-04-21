# Session State Ownership Matrix

Date: 2026-04-20
Scope: `P1a` first migrated key family, active `P1b.1` recommendation-state ownership, and 2026-04-21 follow-up ownership closure for preparation and restart metadata keys from `docs/specs/CODEBASE_REFACTOR_FOLLOWUP_SPEC_2026-04-20.md`
Status: active ownership inventory

## Purpose

This matrix defines the enforced ownership boundary for the shared processing lifecycle, source identity, preparation metadata, restart metadata, and recommendation-state keys currently migrated under this spec.

The initial `P1a` goal is narrow on purpose:

1. centralize write ownership for the first migrated key family in `state.py`;
2. document the remaining enforced ownership boundary during the migration slice;
3. provide a stable artifact for the ownership regression test.
4. extend the same ownership contract to the first recommendation-state keys migrated under `P1b.1`.
5. close the remaining ad hoc write paths for preparation worker state, restart/completed source metadata, app-start markers, and preparation summary state confirmed by the 2026-04-21 review reconciliation.

The `selected_source_token` write-side gap identified during review is now closed in the current working slice: `application_flow.py` retains a narrow read for file-selection comparison, but writes delegate to `state.set_selected_source_token()`.

## Ownership Rules

1. `state.py` is the long-term owner for all keys listed in this matrix.
2. Raw writes outside `state.py` for these keys are not allowed.
3. Raw reads outside `state.py` are not allowed for these keys in the current enforced contract.
4. `processing_runtime.py` may orchestrate start/stop behavior, but it must delegate owned state transitions to `state.py` helpers.

## Key Inventory

| key | owner module | canonical writer helpers | current reader callers | migration phase |
|---|---|---|---|---|
| `processing_outcome` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_preparation_complete()`, `apply_preparation_failure()`, `apply_processing_start()`, `apply_processing_completion()` | `state.get_processing_outcome()`, `application_flow.has_restartable_source()`, `app.main()` via `get_processing_outcome()` | `P1a` |
| `processing_worker` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()`, `apply_processing_completion()` | `processing_runtime.processing_worker_is_active()` | `P1a` |
| `processing_event_queue` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()`, `apply_processing_completion()` | `processing_runtime.drain_processing_events()` | `P1a` |
| `processing_stop_event` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()`, `apply_processing_completion()` | `processing_runtime.request_processing_stop()` via `state.request_processing_stop()` | `P1a` |
| `processing_stop_requested` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()`, `request_processing_stop()`, `apply_processing_completion()` | `state.is_processing_stop_requested()`, `app._render_processing_controls()` via helper | `P1a` |
| `preparation_worker` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_preparation_runtime()`, `apply_preparation_complete()`, `apply_preparation_failure()` | `processing_runtime.preparation_worker_is_active()` via helper | `2026-04-21 follow-up` |
| `preparation_event_queue` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_preparation_runtime()`, `apply_preparation_complete()`, `apply_preparation_failure()` | `processing_runtime.drain_preparation_events()` via helper | `2026-04-21 follow-up` |
| `latest_source_name` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()` | `processing_runtime.get_current_result_bundle()` | `P1a` |
| `latest_source_token` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()` | `processing_runtime.get_current_result_bundle()`, `app.main()` via `get_processing_session_snapshot()` | `P1a` |
| `selected_source_token` | `state.py` | `init_session_state()`, `set_selected_source_token()`, `apply_preparation_complete()`, `apply_processing_start()` | `application_flow.sync_selected_file_context()`, `state.apply_preparation_complete()` | `P1a` |
| `latest_image_mode` | `state.py` | `init_session_state()`, `reset_run_state()`, `apply_processing_start()` | `app.main()` via `get_latest_image_mode()` | `P1a` |
| `latest_preparation_summary` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_latest_preparation_summary()` | `app.main()` via helper-backed preparation summary rendering | `2026-04-21 follow-up` |
| `prepared_source_key` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_prepared_source_key()`, `apply_preparation_complete()` | `application_flow.should_log_document_prepared()` raw read for comparison | `2026-04-21 follow-up` |
| `restart_source` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_restart_source()`, `apply_processing_completion()` | `application_flow.get_cached_restart_file()`, `application_flow.has_restartable_source()`, `processing_runtime.start_background_processing()` via helper | `2026-04-21 follow-up` |
| `completed_source` | `state.py` | `init_session_state()`, `clear_completed_source()`, `apply_processing_completion()`, `reset_run_state()` | `application_flow.get_cached_completed_file()`, `application_flow.consume_completed_source_if_used()` read-side comparison | `2026-04-21 follow-up` |
| `persisted_source_cleanup_done` | `state.py` | `init_session_state()`, `mark_persisted_source_cleanup_done()` | `app._schedule_stale_persisted_sources_cleanup()` via helper | `2026-04-21 follow-up` |
| `app_start_logged` | `state.py` | `init_session_state()`, `mark_app_start_logged()` | `app.main()` via helper | `2026-04-21 follow-up` |
| `text_transform_assessment` | `state.py` | `init_session_state()`, `set_text_transform_assessment()` | `app._assess_text_transform()` caller tests and UI flows via session-backed state | `P1b.1` |
| `recommended_text_settings` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_recommended_text_settings()` | `app._maybe_apply_file_recommendations()` via helper reads | `P1b.1` |
| `recommended_text_settings_applied_for_token` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_recommended_text_settings_applied()` | `app._maybe_apply_file_recommendations()` via helper reads | `P1b.1` |
| `recommended_text_settings_applied_snapshot` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_recommended_text_settings_applied()` | `app._maybe_apply_file_recommendations()` via helper reads | `P1b.1` |
| `recommended_text_settings_pending_widget_state` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_recommended_text_settings_pending_widget_state()`, `consume_recommended_text_settings_pending_widget_state()` | `app._apply_pending_recommended_widget_state()` via helper | `P1b.1` |
| `recommended_text_settings_notice_token` | `state.py` | `init_session_state()`, `reset_run_state()`, `clear_recommended_text_settings_notice_token()`, `set_recommended_text_settings_notice()` | `app._should_render_recommended_text_settings_notice()` via helper | `P1b.1` |
| `recommended_text_settings_notice_details` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_recommended_text_settings_notice()` | `app._build_recommended_text_settings_notice()` via helper | `P1b.1` |
| `manual_text_settings_override_for_token` | `state.py` | `init_session_state()`, `reset_run_state()`, `set_manual_text_settings_override_for_token()` | `app._maybe_apply_file_recommendations()` via helper reads | `P1b.1` |

## Raw Read Exceptions

There are no active temporary raw-read exceptions in the current enforced contract.

`application_flow.py` and `app.py` now read the owned keys in this matrix through `state.py` helpers or higher-level helper APIs rather than direct `st.session_state` access. `state.py` remains the only allowed direct owner surface.

## Enforcement Scope For Current Test

The regression test checks the keys in this matrix and now covers both raw `st.session_state` access and injected `session_state` writes for the owned-key set.

It fails when these keys are accessed through raw `st.session_state` outside:

1. `state.py`;
2. test files.

## Additional Findings Captured During Implementation

The key family was previously split by lifecycle phase rather than by module ownership:

1. processing start lived in `processing_runtime.py`;
2. preparation completion and resets lived in `state.py`;
3. source-token reselection previously lived in `application_flow.py` and now delegates its write path to `state.set_selected_source_token()` while retaining a narrow read for file-selection comparison.
4. the 2026-04-21 follow-up also moved app-start markers, preparation-summary writes, preparation worker/event queue writes, restart-source writes, completed-source clearing, and prepared-source-key writes behind `state.py` helpers.

`P1a`/`P1b.1` plus the 2026-04-21 follow-up do not eliminate every legacy helper-mediated read path yet, but they establish one authoritative write owner for the current lifecycle, source-identity, preparation metadata, restart metadata, and recommendation-state keys and close the earlier `selected_source_token`, `completed_source`, and `prepared_source_key` write-side ownership gaps in `application_flow.py` without leaving active raw session-state read exceptions.
