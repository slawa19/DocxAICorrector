# Active Spec Checklist

Date: 2026-04-17
Status: Active execution checklist
Primary source specs:
- `docs/ARCHITECTURE_REFACTORING_SPEC_2026-03-25.md`
- `docs/AI_STRUCTURE_RECOGNITION_SPEC_2026-03-26.md`

## How To Use This File

- This is the execution checklist for active spec work, not a replacement for the source specs.
- Checkboxes reflect current repository progress as of the last update to this file.
- `blocked` means intentionally deferred behind an upstream dependency, not forgotten.
- Update this file in the same change set as any completed checklist item.

## Execution Order

1. Finish architecture P0 and the minimum P1 adapter/runtime narrowing needed to stabilize preparation/runtime boundaries.
2. Finish architecture P2 and selected P3 guardrails that affect state, validation, and document boundary safety.
3. Start AI structure recognition Phase 1 on top of the simplified preparation/runtime contract.
4. Leave AI structure recognition Phase 2 and Phase 3 as explicit future work unless requested.

## Architecture Refactoring Checklist

Source: `docs/ARCHITECTURE_REFACTORING_SPEC_2026-03-25.md`

### P0 - Freeze and narrow protected seams

- [x] P0.1 Remove redundant authoritative normalization after the canonical upload boundary.
- [x] P0.1 Keep legacy `.doc` source-identity token semantics while downstream consumers receive normalized DOCX bytes.
- [x] P0.1 Tighten naming and helper signatures so prepared-upload ownership is explicit across `processing_runtime.py`, `application_flow.py`, `preparation.py`, and `document.py`.
- [x] P0.2 Move image-state reset ownership into `state.py` and stop direct image reset mutation in `processing_runtime.py`.
- [x] P0.2 Move preparation marker and preparation success/failure session transitions under `state.py` owner helpers.
- [x] P0.2 Move processing completion and restart/completed-source transition writes behind explicit owner helpers.
- [x] P0.2 Reduce `app.py` dependence on raw runtime marker/session-key reasoning for restart and preparation transition flow.

### P1 - Tighten runtime and adapter boundaries

- [x] P1.1 Decide whether `processing_runtime.py` stays one file or gets one justified extraction with real ownership gain.
- [x] P1.1 If extracting, move one cohesive cluster only: upload contract or runtime transition handling.
- [x] P1.2 Audit every `app_runtime.py` export against the adapter-only rule.
- [x] P1.2 Remove or collapse wrappers that do not protect `app.py` from runtime/state wiring details.
- [x] P1.2 Add/refresh tests that lock `app_runtime.py` as adapter-only behavior.

### P2 - Tighten service facade and validation convergence

- [x] P2.1 Separate collaborator assembly from execution facade methods in `processing_service.py` without introducing generic DI infrastructure.
- [x] P2.1 Keep validation-facing service cloning and execution on the same production-compatible facade family.
- [x] P2.2 Unify validation/report naming and helper ownership across structural validation entrypoints.
- [x] P2.2 Ensure maintained validators do not bypass the shared production-compatible service facade.

### P3 - Cleanup, debt retirement, and guardrails

- [x] P3.1 Remove transitional helpers and compatibility shims that become unnecessary after P0-P2.
- [x] P3.2 Add behavior-level regression guardrails for upload boundary reuse, runtime transitions, and adapter-only seams.
- [x] P3.3 Promote `document.py` helpers consumed by `formatting_transfer.py` to explicit public surface and eliminate `_`-prefixed imports there.
- [x] P3.4 Add state read helpers for the primary session key families and migrate `ui.py` off raw reads where helpers exist.
- [x] P3.5 Add `SetStateEvent` allowed-key guardrail colocated with drain logic in `processing_runtime.py`.

## AI Structure Recognition Checklist

Source: `docs/AI_STRUCTURE_RECOGNITION_SPEC_2026-03-26.md`

### Gate

- [x] Architecture dependency gate cleared: prepared-upload and preparation/runtime transition boundaries are stable enough to insert a new preparation substage.

### Phase 1 - Core module and integration

- [x] Create `structure_recognition.py` with descriptor building, AI invocation, windowing, overlap merge, and structure-map application.
- [x] Add `ParagraphDescriptor`, `ParagraphClassification`, and `StructureMap` dataclasses to `models.py`.
- [x] Extend `ParagraphUnit` metadata surface for descriptor building and AI confidence tracking.
- [x] Export the required paragraph font/bold helpers from `document.py` as explicit callable surface.
- [x] Add `[structure_recognition]` config surface to `config.py` and `config.toml`.
- [x] Insert structure recognition into `preparation.py` between extraction and text/block building.
- [x] Extend preparation progress stages and metrics for structure recognition and fallback paths.
- [x] Extend `PreparedDocumentData` and `PreparedRunContext` with structure-recognition summary counters/artifact access.
- [x] Extend `_store_preparation_summary` in `app.py` with AI classification counters.
- [x] Extend `render_preparation_summary` in `ui.py` with the conditional AI summary line.
- [x] Create `prompts/structure_recognition_system.txt`.
- [x] Create `tests/test_structure_recognition.py` for descriptor building, windowing, merge rules, priority rules, and fallback behavior.
- [x] Update `tests/test_config.py` for the new config surface.
- [x] Update `tests/test_preparation.py` for cache-key and structure-recognition-enabled behavior.
- [x] Add the real-document integration validation path for the Lietaer source under the existing integration-test contract.

### Phase 2 - Heuristic deprecation

- [x] Guard current heading heuristics so they only promote when AI classification did not already decide the paragraph role.
- [x] Track AI-vs-heuristic divergence in diagnostics before removing heuristic paths.
- [ ] Reduce heuristic-only heading promotion code after multi-document validation proves AI reliability.

### Phase 3 - Extended taxonomy consumers

- [x] Teach `build_semantic_blocks` to use `structural_role` where the spec requires it.
- [x] Teach formatting restoration to preserve epigraph/attribution semantics where needed.
- [x] Teach markdown/rendered-text surfaces to use the richer structure taxonomy where appropriate.

## Verification Checklist

- [x] Current completed architecture slices re-verified with visible VS Code tasks.
- [x] For each architecture slice, run the matching visible task coverage from the source spec verification plan.
- [x] Before starting AI Structure Phase 1, confirm the architecture dependency gate is satisfied in this file.

## Progress Log

- 2026-04-17: completed P0.1 double-normalization removal in `document.py` and added regression coverage.
- 2026-04-17: completed the remaining P0.1 signature-hardening slice by making `FrozenUploadPayload` the explicit preparation boundary between `application_flow.py` and `preparation.py`.
- 2026-04-17: completed P0.2 image reset ownership migration into `state.py`.
- 2026-04-17: completed P0.2 preparation marker and preparation success/failure owner-helper migration into `state.py`.
- 2026-04-17: completed P0.2 processing completion and restart/completed-source owner-helper migration into `state.py`.
- 2026-04-17: completed P0.2 `app.py` cleanup for preparation/restart transition reads through `state.py` helpers.
- 2026-04-17: completed P1.2 adapter-surface audit for `app_runtime.py`, narrowed the explicit export surface, and added adapter-contract tests.
- 2026-04-17: completed P3.5 `SetStateEvent` allowlist guardrail with warning-on-unknown-key behavior.
- 2026-04-17: completed P3.4 primary state read contract for `ui.py` hot paths.
- 2026-04-17: completed P3.3 public helper promotion for the `document.py` -> `formatting_transfer.py` boundary and removed low-value `app_runtime` wiring tests.
- 2026-04-17: completed the first P1.1 decision slice by keeping `processing_runtime.py` unified for now and documenting its intended public surface explicitly.
- 2026-04-17: completed P2.1 by separating `ProcessingService` collaborator assembly into an explicit dependency bundle while preserving singleton/clone semantics and validation-facing facade reuse.
- 2026-04-17: completed P2.2 by centralizing validation runtime-config/event-log helpers and removing transitional `source_file` reporting aliases from maintained validation entrypoints.
- 2026-04-17: completed P3.1 by removing dead transitional validation adapters and their now-unused import surface from the maintained real-document runner.
- 2026-04-17: completed P3.2 by locking the UI upload boundary and validation report shape with behavior-level regression tests, including legacy `.doc` normalization at the preparation adapter seam.
- 2026-04-17: cleared the AI architecture gate and landed the first Phase 1 foundation slice: structure-recognition dataclasses, config surface, prompt contract, standalone module, cache-key flagging, and baseline unit coverage. Verified with visible task `Run Full Pytest` (`726 passed, 6 skipped`).
- 2026-04-17: completed the main Phase 1 preparation integration slice by inserting structure recognition before text/block assembly, adding fallback-aware preparation progress metrics, propagating `structure_map` and AI counters through `PreparedRunContext`, and surfacing AI counts in the static preparation summary/UI. Verified with visible task `Run Full Pytest` (`729 passed, 6 skipped`).
- 2026-04-17: completed the Lietaer real-document integration path for AI structure recognition by extending the canonical runner report/summary with AI preparation counters and adding an opt-in `@pytest.mark.integration` smoke test that runs the standard `scripts/run-real-document-validation.sh` path with structure recognition enabled. Verified registry/unit coverage with visible task `Run Full Pytest` (`729 passed, 7 skipped`).
- 2026-04-17: completed the first Phase 2 heuristic-deprecation guardrail by preventing late standalone-heading heuristics from overriding AI-classified body/attribution paragraphs. Verified with visible task `Run Full Pytest` (`731 passed, 7 skipped`).
- 2026-04-17: completed the divergence-diagnostics slice by tracking AI-vs-heuristic role changes, heading promotions/demotions, and structural-role changes through preparation metrics, the static summary/UI, and the canonical Lietaer validation report. Verified with visible task `Run Full Pytest` (`733 passed, 7 skipped`).
- 2026-04-17: advanced the first Phase 3 consumer slice by teaching rendered-text/marker-wrapped markdown surfaces to render `epigraph` and `attribution` paragraphs as blockquotes while preserving existing marker flow. `toc_entry` suppression remains pending before the full Phase 3 markdown item can be closed. Verified with visible task `Run Full Pytest` (`736 passed, 7 skipped`).
- 2026-04-17: closed the remaining technical Phase 1/Phase 3 follow-up items by exporting the paragraph font/bold helper surface from `document.py`, teaching semantic block assembly to respect `structural_role` directly for quote/TOC clusters, moving TOC-only editing chunks onto safe passthrough jobs, and restoring epigraph/attribution italics during formatting preservation. Verified with visible tasks `Phase 2 Test Document` (`116 passed`) and `Phase 2 Test Formatting` (`18 passed`), then `Run Full Pytest` (`740 passed, 7 skipped`).
- 2026-04-17: architecture checklist verification coverage is now fully backed by visible VS Code task runs recorded in this log; the only remaining open AI item is heuristic-code reduction that the source spec explicitly defers until multi-document AI validation is proven.