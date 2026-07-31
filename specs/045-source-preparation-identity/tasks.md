# Tasks: Stable Source and Preparation Identity

**Input**: Design documents in `specs/045-source-preparation-identity/`

**Global order**: 044 → 045 → 046 → 048 → 047; start after 044.

## Phase 1: Setup

- [X] T001 Confirm current persisted-source and marker evidence in `specs/045-source-preparation-identity/spec.md`
- [X] T002 Run focused pre-change selectors from `specs/045-source-preparation-identity/quickstart.md`

## Phase 2: Foundational persistence contract

- [X] T003 Add failing metadata round-trip and confined-path tests in `tests/test_restart_store.py`
- [X] T004 Extend persisted restart/completed record metadata and integrity validation in `src/docxaicorrector/processing/restart_store.py`

## Phase 3: User Story 1 - Reuse converted source (P1) MVP

**Independent Test**: PDF/DOC restored payload keeps original token and invokes zero conversion calls.

- [X] T005 [P] [US1] Add failing PDF and DOC persist/restore token-stability tests in `tests/test_application_flow.py`
- [X] T006 [P] [US1] Add failing no-reconversion tests with converter spies in `tests/test_processing_runtime.py`
- [X] T007 [US1] Restore a verified token-bearing frozen payload in `src/docxaicorrector/ui/application_flow.py`
- [X] T008 [US1] Preserve source format/provenance through restart and completed transitions in `src/docxaicorrector/runtime/state.py`
- [X] T009 [US1] Pass the restored frozen payload without identity recomputation in `src/docxaicorrector/processing/application_flow.py`

## Phase 4: User Story 2 - Language-sensitive preparation (P1)

**Independent Test**: Either language change selects a new request; canonical equivalents reuse it.

- [X] T010 [P] [US2] Add failing marker normalization/differentiation tests in `tests/test_processing_runtime.py`
- [X] T011 [P] [US2] Add failing UI stale-context tests for both marker call sites in `tests/test_app_restartable_state.py`
- [X] T012 [US2] Add canonical source/target language axes to `build_preparation_request_marker` in `src/docxaicorrector/processing/processing_runtime.py`
- [X] T013 [US2] Pass resolved languages at both preparation marker call sites in `src/docxaicorrector/ui/_app.py`

## Phase 5: User Story 3 - Reject unusable cache (P2)

**Independent Test**: Changed/missing bytes or metadata are unavailable and fresh upload recovers.

- [X] T014 [P] [US3] Add failing corruption, truncation, missing-metadata, and legacy-record tests in `tests/test_restart_store.py`
- [X] T015 [US3] Reject unverifiable records with existing safe observability in `src/docxaicorrector/processing/restart_store.py`
- [X] T016 [US3] Add a failing same-process fresh-upload recovery test after persisted-record rejection in `tests/test_application_flow.py`
- [X] T017 [US3] Keep the UI recoverable through fresh upload after rejection in `src/docxaicorrector/ui/application_flow.py`

## Final Phase: Verification

- [X] T018 Run focused canonical validation from `specs/045-source-preparation-identity/quickstart.md`
- [X] T019 Run VS Code `Run Full Pytest` and `git diff --check`

## Dependencies & strategy

T003→T004 is foundational. US1 then establishes restoration; US2 is independently testable; US3 hardens failure behavior. Tests precede implementation. Complete 045 before 046.

## Parallel example

T005/T006 and T010/T011 may be authored in parallel after T004 because they target distinct contracts.

## Phase 6: Convergence

- [X] T020 [US1] Add deterministic PDF- and legacy-DOC-derived restored-payload regressions in `tests/test_application_flow.py` that pass the real `FrozenUploadPayload` returned by completed/restart restoration through synchronous `prepare_run_context`, preserve the authoritative source token, and prove zero upload rereads and zero PDF/DOC reconversion attempts per US1/AC1–2 and SC-001/SC-002 (missing)
- [X] T021 [US1] Update `_resolve_preparation_upload` in `src/docxaicorrector/processing/application_flow.py` to recognize a verified `FrozenUploadPayload` supplied through `uploaded_file` as already materialized (`needs_read_stage=False`) while preserving the existing fresh-upload and explicit `uploaded_payload` paths per FR-004/FR-005 (partial)
