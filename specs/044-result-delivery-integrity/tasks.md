# Tasks: Result Delivery Integrity

**Input**: Design documents in `specs/044-result-delivery-integrity/`

**Global order**: 044 → 045 → 046 → 048 → 047

## Phase 1: Setup

- [X] T001 Confirm fresh F1/F2 line evidence and preserve baseline expectations in `specs/044-result-delivery-integrity/spec.md`
- [X] T002 Run the focused pre-change canonical selectors from `specs/044-result-delivery-integrity/quickstart.md`

## Phase 2: Foundational contract

- [X] T003 Add failing result-bundle contract tests for accepted, advisory, blocked-with-bytes, and blocked-without-bytes states in `tests/test_processing_runtime.py`
- [X] T004 Implement the delivery disposition and typed notice fields in `src/docxaicorrector/processing/processing_runtime.py`

## Phase 3: User Story 1 - Safe source fallback (P1) MVP

**Independent Test**: All four marker-mode controlled fallbacks preserve source text and expose zero markers.

- [X] T005 [P] [US1] Add failing incomplete/empty/non-completed marker fallback tests in `tests/test_generation.py`
- [X] T006 [P] [US1] Add failing anti-regression tests for non-marker text, ordinary bracketed text, Unicode, Markdown, and image placeholders in `tests/test_generation.py`
- [X] T007 [US1] Route every eligible fallback through the existing canonical marker-free substrate in `src/docxaicorrector/generation/_generation.py`
- [X] T008 [US1] Verify returned-length/event metadata describes sanitized output in `src/docxaicorrector/generation/_generation.py`

## Phase 4: User Story 2 - Honest blocked presentation (P1)

**Independent Test**: Both UI entry paths show blocked state and diagnostic labels, while pass/warn retain normal delivery.

- [X] T009 [P] [US2] Add failing late-gate bundle propagation tests in `tests/test_late_phases_finalize_gate_persistence.py`
- [X] T010 [P] [US2] Add failing renderer tests for blocked/accepted/advisory states and coexisting notices in `tests/test_ui.py`
- [X] T011 [P] [US2] Add failing rerun/same-source blocked-state test in `tests/test_app_restartable_state.py`
- [X] T012 [US2] Propagate final delivery disposition and explanation from `src/docxaicorrector/pipeline/late_phases.py`
- [X] T013 [US2] Select result presentation from disposition rather than byte presence in `src/docxaicorrector/ui/_app.py`
- [X] T014 [US2] Render blocked explanation and diagnostic download labels without success in `src/docxaicorrector/ui/_ui.py`
- [X] T015 [US2] Add blocked notice/download labels in `src/docxaicorrector/ui/locales/en.json` and `src/docxaicorrector/ui/locales/ru.json`

## Final Phase: Verification

- [X] T016 Run focused canonical files from `specs/044-result-delivery-integrity/quickstart.md`
- [X] T017 Verify blocked outcomes create no accepted `.run/ui_results/` group and emit no accepted-artifact signal in `tests/test_late_phases_finalize_gate_persistence.py`
- [X] T018 Run VS Code `Run Full Pytest` and `git diff --check`

## Dependencies & strategy

T003→T004 blocks US2 serialization. US1 and US2 tests may be authored in parallel; each test must fail before its implementation. Complete 044 before 045. MVP is US1, but feature completion requires US2.

## Parallel example

T005/T006 can run alongside T009/T010/T011 because they touch separate test surfaces.

## Phase 5: Convergence

- [X] T019 [US2] Add a failing end-to-end persistence-warning regression spanning `tests/test_late_phases_finalize_gate_persistence.py`, result-bundle reconstruction, and `tests/test_ui.py`: force primary `.result.*` artifact persistence to fail, retain the accepted in-session Markdown/DOCX and normal downloads, and prove the completed UI visibly renders one not-saved warning after rerender while emitting `processing_completed_unpersisted`, creating no accepted-artifact saved signal, and preserving coexisting cleanup/narration notices per FR-011/FR-013 and SC-004 (verified: real finalize -> applied SessionState -> reconstructed bundle -> completed renderer seam)
- [X] T020 [US2] Accumulate a typed persistence degradation notice in `src/docxaicorrector/pipeline/late_phases.py` when primary result artifact persistence fails, emit it through `latest_result_notices` without replacing cleanup/narration facts, and continue writing the legacy `latest_result_notice` warning for backward-compatible session consumers while leaving accepted delivery disposition, in-session result bytes, downloads, terminal outcome, and distinct `processing_completed_unpersisted` event unchanged per the plan typed-notice contract and Constitution V (verified: typed coexistence plus legacy compatibility selectors)
- [X] T021 [US2] Add localized persistence-not-saved notice keys to `src/docxaicorrector/ui/locales/en.json` and `src/docxaicorrector/ui/locales/ru.json`, render the typed persistence notice in `src/docxaicorrector/ui/_ui.py` alongside cleanup/narration notices, and cover typed+legacy coexistence and legacy-only compatibility without duplicate warnings or suppression of the normal accepted success/download flow in `tests/test_ui.py` and `tests/test_processing_runtime.py` per FR-011/FR-013/FR-014 and SC-004 (verified: EN/RU params, invalid-param fail-safe, quality dedup, and legacy fallback)
