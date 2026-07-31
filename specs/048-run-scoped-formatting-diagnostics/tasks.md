# Tasks: Run-Scoped Formatting Diagnostics

**Input**: Design documents in `specs/048-run-scoped-formatting-diagnostics/`

**Global order**: 044 → 045 → 046 → 048 → 047. This feature blocks 047.

## Phase 1: Setup

- [X] T001 Reconfirm all writer/collector evidence and classifications in `specs/048-run-scoped-formatting-diagnostics/research.md`
- [X] T002 Run the focused pre-change canonical selectors from `specs/048-run-scoped-formatting-diagnostics/quickstart.md`

## Phase 2: Foundational ownership contract

- [X] T003 Add failing ownership-envelope, exact-match, collision, and empty-set tests in `tests/test_format_restoration.py`
- [X] T004 Implement live run/source validation, unique naming, offline scope, and owned collection in `src/docxaicorrector/generation/formatting_diagnostics_retention.py`

## Phase 3: User Story 1 - Independent run verdicts (P1) MVP

**Independent Test**: Overlapping A/B runs collect zero foreign paths and only existing-policy outcomes follow owned evidence.

- [X] T005 [P] [US1] Add failing different-source and same-source-rerun overlap tests in `tests/test_late_phases_finalize_gate_persistence.py`
- [X] T006 [P] [US1] Add failing clean-run anti-vacuum test while a foreign run writes diagnostics in `tests/test_late_phases_finalize_gate_persistence.py`
- [X] T007 [US1] Thread existing run/source identity through formatting build dependencies in `src/docxaicorrector/pipeline/contracts.py`
- [X] T008 [US1] Pass ownership into normal formatting diagnostics writes in `src/docxaicorrector/generation/formatting_transfer.py`
- [X] T009 [US1] Pass live ownership into marker/block diagnostic writes in `src/docxaicorrector/pipeline/support.py`
- [X] T010 [US1] Replace recent-time collector wrappers with exact ownership inputs in `src/docxaicorrector/pipeline/formatting_diagnostics_feedback.py`
- [X] T011 [US1] Replace initial and deferred mtime collection with exact owned collection in `src/docxaicorrector/pipeline/late_phases.py`
- [X] T012 [US1] Ensure diagnostics-derived gate inputs consume only owned paths without policy changes in `src/docxaicorrector/pipeline/quality_gate.py`

## Phase 4: User Story 2 - Exact result review data (P2)

**Independent Test**: Each result notice/report/event contains only its own counts and existing paths.

- [X] T013 [P] [US2] Add failing owned-path report and event assertions in `tests/test_late_phases_finalize_gate_persistence.py`
- [X] T014 [P] [US2] Add failing formatting-review count isolation assertions in `tests/test_document_pipeline.py`
- [X] T015 [US2] Restrict UI/activity/report payload construction to the owned set in `src/docxaicorrector/pipeline/late_phases.py`
- [X] T016 [US2] Preserve exact owned artifact paths in existing quality-report fields in `src/docxaicorrector/pipeline/quality_gate.py`

## Phase 5: User Story 3 - Retention, offline validation and replay (P3)

**Independent Test**: Family stays ≤100/7 days, write failure is observable, legacy/offline artifacts are explicit-replay only, and no mtime collector remains.

- [X] T017 [P] [US3] Add family-wide retention and repeated-stage collision tests in `tests/test_format_restoration.py`
- [X] T018 [P] [US3] Add legacy explicit-replay/live-exclusion and write-failure tests in `tests/test_format_restoration.py`
- [X] T019 [P] [US3] Add target-alignment offline-scope characterization tests in `tests/test_structural_validation_characterization.py`
- [X] T020 [P] [US3] Add exact event-path collection and concurrent foreign-artifact exclusion tests in `tests/test_real_document_pipeline_validation.py`
- [X] T021 [US3] Mark target-alignment diagnostics explicit offline and retain their explicit validation paths in `src/docxaicorrector/validation/structural.py`
- [X] T022 [US3] Remove or replace recent-mtime compatibility collection with explicit paths/scope in `src/docxaicorrector/pipeline/_pipeline.py`
- [X] T023 [US3] Make real-document validation consume exact event paths or explicit-none, with no shared-directory snapshot fallback, in `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
- [X] T024 [US3] Preserve family-wide pruning and fail-open warning behavior in `src/docxaicorrector/generation/formatting_diagnostics_retention.py`
- [X] T025 [US3] Preserve explicit historical path loading without live ownership inference in `src/docxaicorrector/pipeline/quality_gate.py`

## Final Phase: Verification

- [X] T026 Run focused canonical validation from `specs/048-run-scoped-formatting-diagnostics/quickstart.md`
- [X] T027 Verify no process-global mutable owner or mtime ownership fallback remains across `src/docxaicorrector/pipeline/` and `src/docxaicorrector/validation/structural.py`
- [X] T028 Run VS Code `Run Full Pytest` and `git diff --check`

## Dependencies & strategy

T003→T004 blocks all stories. US1 establishes live ownership propagation; US2/US3 follow. T019–T025 close explicit offline consumers and cannot be skipped. Tests fail first. 047 MUST NOT start before T026–T028 pass.

## Parallel example

T005/T006, T013/T014, and T017–T020 are parallel test-authoring groups after foundational ownership exists.
