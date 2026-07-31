# Tasks: Reader Cleanup Production Parity

**Input**: Design documents in `specs/047-reader-cleanup-production-parity/`

**Global order**: 044 → 045 → 046 → 048 → 047.

## Phase 1: Setup and dependency gate

- [X] T001 Verify spec 044 delivery disposition/notices focused tests pass using `specs/044-result-delivery-integrity/quickstart.md`
- [X] T002 Verify spec 048 owned diagnostics focused tests pass using `specs/048-run-scoped-formatting-diagnostics/quickstart.md`
- [X] T003 Confirm no mtime compatibility fallback is planned in `specs/047-reader-cleanup-production-parity/plan.md`

## Phase 2: Foundational late-phase contracts

- [X] T004 Add failing typed cleanup/narration notice coexistence tests in `tests/test_late_phases_finalize_gate_persistence.py`
- [X] T005 Add failing safe-boundary stop helper tests in `tests/test_document_pipeline.py`
- [X] T006 Extend late-phase dependency/result contracts for cooperative stop and typed degradation facts in `src/docxaicorrector/pipeline/contracts.py`

## Phase 3: User Story 1 - UI activation parity (P1) MVP

**Independent Test**: Explicitly enabled UI translation cleans; unset/default, off, edit and audiobook do not.

- [X] T007 [P] [US1] Add failing default/env/effective mapping tests in `tests/test_config.py`
- [X] T008 [P] [US1] Add failing UI translation/non-translation activation tests in `tests/test_app_preparation.py`
- [X] T009 [US1] Map supported reader-cleanup config into effective UI app config in `src/docxaicorrector/ui/_app.py`
- [X] T010 [US1] Preserve translation/off activation guard in `src/docxaicorrector/pipeline/reader_cleanup_rebuild.py`

## Phase 4: User Story 2 - Final owned evidence (P1)

**Independent Test**: Changed and no-op cleanup verdicts use final bytes and spec-048 owned final diagnostics.

- [X] T011 [P] [US2] Add failing no-op and changed cleanup final-evidence tests in `tests/test_late_phases_finalize_gate_persistence.py`
- [X] T012 [P] [US2] Add failing final caption-conflict aggregation regression in `tests/test_document_pipeline.py`
- [X] T013 [US2] Use final owned diagnostics for both changed and no-op verdict refresh in `src/docxaicorrector/pipeline/late_phases.py`
- [X] T014 [US2] Mark only the final safely produced report as authoritative in `src/docxaicorrector/pipeline/quality_gate.py`

## Phase 5: User Story 3 - Honest late stop (P1)

**Independent Test**: Stops at every boundary produce stopped outcome and zero subsequent calls/persistence.

- [X] T015 [P] [US3] Add stop-before-cleanup/rebuild/persistence tests in `tests/test_late_phases_finalize_gate_persistence.py` (verified: immediate pre-cleanup stop plus stop observed after successful rebuild and advisory base builder)
- [X] T016 [P] [US3] Add between-cleanup-call and between-narration-call stop tests in `tests/test_document_pipeline.py` (verified: no later narration provider group after stop observation)
- [X] T017 [US3] Check stop before/between cleanup side effects in `src/docxaicorrector/pipeline/reader_cleanup_postprocess.py`
- [X] T018 [US3] Check stop before rebuild/re-gate/narration/persistence and emit existing stopped outcome in `src/docxaicorrector/pipeline/late_phases.py`
- [X] T019 [US3] Check stop between narration provider groups in `src/docxaicorrector/pipeline/narration_postprocess.py`

## Phase 6: User Story 4 - Visible advisory failure (P1)

**Independent Test**: Base result is delivered and cleanup/narration facts survive rerun without changing disposition.

- [X] T020 [P] [US4] Add failing advisory cleanup preservation/notice tests in `tests/test_document_pipeline.py`
- [X] T021 [P] [US4] Add failing cleanup+narration coexistence and blocked-precedence tests in `tests/test_late_phases_finalize_gate_persistence.py`
- [X] T022 [P] [US4] Add failing renderer/locale tests for cleanup, narration, and stopped notices in `tests/test_ui.py`
- [X] T023 [US4] Produce typed advisory cleanup facts on fail-open paths in `src/docxaicorrector/pipeline/reader_cleanup_postprocess.py`
- [X] T024 [US4] Preserve multiple degradation facts through final state/result bundle in `src/docxaicorrector/pipeline/late_phases.py`
- [X] T025 [US4] Add localized cleanup, narration, and late-stop messages in `src/docxaicorrector/ui/locales/en.json` and `src/docxaicorrector/ui/locales/ru.json`

## Phase 7: User Story 5 - Final-text narration parity (P1)

**Independent Test**: Translation narration matches final cleanup lineage or is omitted with warning; audiobook is byte/behavior unchanged.

- [X] T026 [P] [US5] Add failing cleanup remove/replace/split/join narration projection tests in `tests/test_reader_cleanup_mvp.py`
- [X] T027 [P] [US5] Add failing ambiguous-projection omission test in `tests/test_document_pipeline.py`
- [X] T028 [P] [US5] Add standalone audiobook no-cleanup/no-new-warning counter-proof in `tests/test_document_pipeline.py`
- [X] T029 [US5] Project structurally eligible narration from final accepted cleanup lineage in `src/docxaicorrector/pipeline/narration_postprocess.py`
- [X] T030 [US5] Omit ambiguous additive narration with a typed advisory while preserving DOCX/Markdown in `src/docxaicorrector/pipeline/late_phases.py`

## Final Phase: Verification

- [X] T031 Run focused canonical validation from `specs/047-reader-cleanup-production-parity/quickstart.md`
- [X] T032 Verify disabled cleanup adds no calls/build churn and standalone audiobook remains unchanged in `tests/test_document_pipeline.py`
- [X] T033 Verify accepted/stopped/blocked artifact and event contracts in `tests/test_late_phases_finalize_gate_persistence.py`
- [X] T034 Run VS Code `Run Full Pytest` and `git diff --check`

## Dependencies & strategy

T001–T003 are hard gates. T004–T006 establish shared contracts. US1 is the activation MVP, but US2–US5 are required before enabling production use. Every test task precedes its implementation. No 047 implementation starts before 048 is proven.

## Parallel example

After T006, T007/T008, T011/T012, T015/T016, T020–T022, and T026–T028 are parallel test-authoring pairs/groups in different files where marked.

## Phase 8: Convergence

- [X] T035 [US5] Add deterministic narration regressions in `tests/test_document_pipeline.py` for the reachable cleanup-enabled, marker-disabled no-op path with no final identity registry, proving narration/TTS is omitted before any narration provider call with the existing typed warning while accepted base Markdown/DOCX is still delivered; add valid-lineage blank/image-only and ordinary cleanup-lineage counter-proofs so form-only content stays excluded without suppressing adjacent eligible narration per US5/AC1–4 and SC-005/SC-006 (verified: real `_run_processing` no-op seam plus projection matrix)
- [X] T036 [US5] Project additive narration only from validated cleanup-derived structural lineage in `src/docxaicorrector/pipeline/narration_postprocess.py`; require every eligible non-blank final entry to be safely projected in order or omit narration with the existing typed warning when the final registry is missing, incomplete, or mixed, while skipping blank/image-only entries only after lineage validation and never synthesizing paragraph IDs or guessing eligibility from text shape per FR-015/FR-016/FR-017 and Constitution VII (verified: fail-closed missing-registry production seam and valid-lineage counter-proofs)
