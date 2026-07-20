# Feature Specification: Reader Cleanup Production Parity

**Feature Branch**: `[047-reader-cleanup-production-parity]`

**Created**: 2026-07-20

**Status**: Draft

**Input**: User description: "Activate the existing reader-cleanup contract consistently in the production UI, make its final evidence, cancellation, advisory failures, and narration output agree with the delivered result, while preserving the disabled-by-default posture."

**Date**: 2026-07-20

**Owner surface**: UI effective configuration + translation reader-cleanup late phase + final diagnostics/acceptance + cancellation + narration delivery

**Companion**: User-approved code-review round 10 findings F4, F7, F8, and F9 (2026-07-20); preserves the final-DOCX gate behavior introduced by `specs/043-reader-cleanup-caption-gate-completion/spec.md`; consumes the run/source-owned diagnostics contract from `specs/048-run-scoped-formatting-diagnostics/spec.md` once available

**Changelog**:

- 2026-07-20 — Initial specification from fresh current-code trace and targeted canonical WSL characterization tests.
- 2026-07-20 — Cross-spec review removed time-window ownership assumptions, made spec 048 a prerequisite for final-diagnostics work, and clarified coexistence with spec-044 blocked delivery notices.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configured cleanup actually applies in the UI (Priority: P1)

As an operator, I can enable reader cleanup through the supported application configuration and know that UI translation runs receive that effective setting, while installations that do not opt in remain unchanged.

**Why this priority**: The configuration surface currently exposes an opt-in default, but the production UI passes a different key to the pipeline. The feature can therefore appear configured while remaining inactive.

**Independent Test**: Run the same UI translation with reader cleanup explicitly disabled and explicitly enabled, then verify from observable cleanup activity and final output that only the enabled run executes cleanup.

**Acceptance Scenarios**:

1. **Given** no reader-cleanup override, **When** a UI translation starts, **Then** cleanup remains disabled.
2. **Given** the supported reader-cleanup setting resolves to enabled, **When** a UI translation starts, **Then** the effective processing configuration enables reader cleanup.
3. **Given** reader cleanup is enabled but the operation is not translation, **When** processing starts, **Then** the existing operation restriction remains in force and cleanup does not run.

---

### User Story 2 - Final evidence describes the delivered document (Priority: P1)

As an operator reviewing a completed translation, I receive diagnostics and an acceptance verdict computed from the final post-cleanup DOCX, including when cleanup makes no Markdown change.

**Why this priority**: A verdict that combines final bytes with pre-cleanup diagnostics is internally inconsistent and can misrepresent the artifact the user actually receives.

**Independent Test**: Defer DOCX construction to reader cleanup, leave Markdown unchanged, produce distinct final formatting diagnostics, and verify that the surviving report and verdict reference those final diagnostics and delivered bytes.

**Acceptance Scenarios**:

1. **Given** reader cleanup changes the delivered Markdown or DOCX, **When** final acceptance is evaluated, **Then** the evaluation uses the delivered Markdown, delivered DOCX, and diagnostics emitted for that final DOCX.
2. **Given** reader cleanup is a Markdown no-op but builds the final DOCX, **When** final acceptance is evaluated, **Then** output-openability and formatting-dependent checks use the final bytes and freshly collected final diagnostics.
3. **Given** a pre-cleanup report was written before the final DOCX existed, **When** a final authoritative report is available, **Then** operators are left with one clearly authoritative current report rather than a stale report presented as current.
4. **Given** final diagnostics contain caption-to-heading conflicts, **When** the final gate runs, **Then** the existing spec 043 blocking behavior remains effective regardless of whether cleanup changed Markdown.

---

### User Story 3 - Stop remains honest during late processing (Priority: P1)

As a user who presses Stop during reader cleanup or narration preparation, I see the run finish as stopped at the next safe boundary, without new late-stage work or a false success/failure outcome.

**Why this priority**: The current cancellation contract is honored during earlier block/image phases but is not consulted through cleanup, final rebuild, narration, and final persistence.

**Independent Test**: Request stop at each late-phase boundary and during a multi-call cleanup/narration pass; verify that no subsequent external call or accepted-result persistence begins after the request is observed and that the terminal outcome is stopped.

**Acceptance Scenarios**:

1. **Given** stop is already requested before reader cleanup, **When** late processing begins, **Then** cleanup does not start and the run finishes as stopped.
2. **Given** stop is requested during a multi-call reader-cleanup pass, **When** the current in-flight call reaches a safe boundary, **Then** no later cleanup call, DOCX rebuild, narration pass, or accepted-result persistence starts.
3. **Given** stop is requested after cleanup but before or during narration preparation, **When** the request is observed, **Then** no later narration group or accepted-result persistence starts.
4. **Given** a late stop, **When** terminal state is emitted, **Then** it is `stopped`, not `succeeded`, `failed`, or an advisory cleanup failure.

---

### User Story 4 - Advisory cleanup failure remains visible (Priority: P1)

As a user whose advisory reader cleanup fails, I still receive the preserved base translation, together with a visible explanation that cleanup was not applied.

**Why this priority**: Fail-open behavior is intentional for advisory cleanup, but silently clearing its error leaves the user unable to distinguish a cleaned result from the preserved base result.

**Independent Test**: Force a reader-cleanup stage failure under advisory policy, allow normal finalization to complete, rerender the result, and verify that the base result is delivered with a persistent warning and matching structured diagnostic event.

**Acceptance Scenarios**:

1. **Given** advisory cleanup fails, **When** the pipeline preserves the base DOCX/Markdown, **Then** the run may complete successfully but a non-blocking cleanup-failure notice remains visible.
2. **Given** advisory cleanup fails and narration succeeds or is disabled, **When** final session state is emitted, **Then** the cleanup notice is not overwritten by an empty later-stage error value.
3. **Given** cleanup and narration both produce non-blocking failures while the base document remains deliverable, **When** the result is rendered, **Then** neither failure is silently lost and the user can distinguish the two degraded capabilities.

---

### User Story 5 - Narration matches the accepted cleaned text (Priority: P1)

As a user requesting narration alongside translation, I receive TTS text derived from the final accepted post-cleanup content rather than from stale pre-cleanup chunks.

**Why this priority**: Delivering a cleaned DOCX with narration generated from content that cleanup removed or changed creates two contradictory outputs from one run.

**Independent Test**: Make cleanup remove or rewrite a narration-eligible block, request narration, and verify that the removed text is absent and the accepted replacement text is present in the narration source/output while narration exclusions remain excluded.

**Acceptance Scenarios**:

1. **Given** cleanup accepts changes to narration-eligible content, **When** narration is prepared, **Then** its source reflects the final accepted cleaned text.
2. **Given** cleanup is a no-op or advisory cleanup fails and preserves the base result, **When** narration is prepared, **Then** its source reflects that same final accepted base text.
3. **Given** existing narration exclusions such as bibliography or image-only blocks, **When** final text is projected into narration, **Then** those exclusions remain effective.
4. **Given** final cleanup output cannot be reconciled safely with narration inclusion boundaries, **When** narration would otherwise start, **Then** no narration artifact is published and the base DOCX/Markdown remains available with a visible narration warning.

### Edge Cases

- A stop request cannot forcibly terminate an already in-flight provider call; it must be honored immediately after that call returns or fails, before the next side effect.
- A no-op cleanup may reuse unchanged Markdown metrics, but it may not reuse formatting diagnostics from a different DOCX build when computing the final verdict.
- A cleanup warning and an advisory quality warning are separate facts and must not erase or reclassify each other.
- A stop observed after final bytes exist but before accepted-result persistence must still prevent the run from being reported or persisted as completed.
- Standalone audiobook processing does not run translation reader cleanup and therefore retains its existing narration-source contract.

## Verified findings

- **F4 — configured UI default and pipeline activation use different keys** — configuration loading resolves `reader_cleanup_default` with a default of `false` and an environment override at `src/docxaicorrector/core/config_runtime_sections.py:83`, then exposes that same key at `src/docxaicorrector/core/config_runtime_sections.py:248`; the UI copies several effective sidebar values but does not map reader cleanup into the processing configuration at `src/docxaicorrector/ui/_app.py:718` through `src/docxaicorrector/ui/_app.py:730`; the pipeline activates translation cleanup only from `reader_cleanup_enabled` at `src/docxaicorrector/pipeline/reader_cleanup_rebuild.py:45` (verified 2026-07-20).
- **F7 — final diagnostics are collected but the no-op verdict still receives the earlier list** — after deferred final-DOCX construction the late phase recollects final diagnostics at `src/docxaicorrector/pipeline/late_phases.py:778` through `src/docxaicorrector/pipeline/late_phases.py:806`; changed-Markdown re-evaluation uses that final list at `src/docxaicorrector/pipeline/late_phases.py:829` through `src/docxaicorrector/pipeline/late_phases.py:854`, but the no-op acceptance refresh passes the original `formatting_diagnostics_artifacts` at `src/docxaicorrector/pipeline/late_phases.py:935` through `src/docxaicorrector/pipeline/late_phases.py:961` (verified 2026-07-20).
- **F7 fresh characterization** — `tests/test_late_phases_finalize_gate_persistence.py::test_finalize_skips_regate_when_cleanup_leaves_markdown_unchanged` passed in the canonical WSL runtime on 2026-07-20 and explicitly verifies one pre-cleanup gate computation with no no-op re-gate (`tests/test_late_phases_finalize_gate_persistence.py:425` through `tests/test_late_phases_finalize_gate_persistence.py:448`). This is current evidence for the behavior the final-evidence contract must refine.
- **F8 — late phases do not consult the injected stop predicate** — the dependency contract exposes `should_stop_processing` at `src/docxaicorrector/pipeline/contracts.py:194`, and block execution checks it at `src/docxaicorrector/pipeline/block_execution.py:1104`; by contrast, finalization enters reader cleanup at `src/docxaicorrector/pipeline/late_phases.py:729` and narration at `src/docxaicorrector/pipeline/late_phases.py:988` without a stop check, while the narration post-pass can issue multiple provider calls in its group loop at `src/docxaicorrector/pipeline/narration_postprocess.py:183` through `src/docxaicorrector/pipeline/narration_postprocess.py:231` without consulting cancellation (verified 2026-07-20).
- **F9 — advisory outer failure has no result notice and its error is later cleared** — reader-cleanup exception handling creates a notice only for strict policy; the advisory branch logs preservation but leaves `result_notice` unset at `src/docxaicorrector/pipeline/reader_cleanup_postprocess.py:434` through `src/docxaicorrector/pipeline/reader_cleanup_postprocess.py:485`. The final state later sets `last_error` to `narration_error_message`, initialized as empty, at `src/docxaicorrector/pipeline/late_phases.py:725` and `src/docxaicorrector/pipeline/late_phases.py:1095` through `src/docxaicorrector/pipeline/late_phases.py:1112` (verified 2026-07-20).
- **F9 fresh characterization** — `tests/test_document_pipeline.py::test_run_document_processing_preserves_base_result_when_reader_cleanup_fails` passed in the canonical WSL runtime on 2026-07-20, confirming the intended fail-open base-result contract (`tests/test_document_pipeline.py:1784` through `tests/test_document_pipeline.py:1845`) that must now gain durable user-visible advisory state.
- **Narration provenance — narration is accumulated before cleanup and consumed afterward** — processed block text is appended to `state.narration_chunks` during block execution at `src/docxaicorrector/pipeline/block_execution.py:847` through `src/docxaicorrector/pipeline/block_execution.py:852`; reader cleanup may subsequently replace the delivered Markdown at `src/docxaicorrector/pipeline/late_phases.py:742` through `src/docxaicorrector/pipeline/late_phases.py:773`; narration then reads only the pre-existing state chunks at `src/docxaicorrector/pipeline/narration_postprocess.py:34` through `src/docxaicorrector/pipeline/narration_postprocess.py:73` and `src/docxaicorrector/pipeline/narration_postprocess.py:137` through `src/docxaicorrector/pipeline/narration_postprocess.py:163` (verified 2026-07-20).

## Requirements *(mandatory)*

### Functional Requirements

> **Binding rule for detection/classification (Constitution VII, item 8)**: any rule that detects, classifies, credits, or excludes content MUST key on document region, structural role, or form — never on a word list, a signal count, or a literal taken from one book. Per-book literals do not transfer to the next document and are rejected in review.

- **FR-001**: The production UI MUST translate the supported reader-cleanup configuration default into the effective setting consumed by the translation pipeline.
- **FR-002**: Reader cleanup MUST remain disabled by default; only an explicit supported configuration or environment override may enable it.
- **FR-003**: Enabling reader cleanup MUST NOT broaden it beyond the existing translation operation scope or bypass an explicit `off` policy.
- **FR-004**: When reader cleanup participates in final DOCX construction, all formatting-dependent final acceptance checks MUST use diagnostics emitted for that final DOCX, whether or not cleanup changed Markdown.
- **FR-005**: The final acceptance verdict MUST describe one coherent delivered state: final accepted Markdown, final DOCX bytes, and the final diagnostics set associated with that build and processing run.
- **FR-006**: Any superseded pre-cleanup report MUST NOT remain discoverable as the current authoritative report after a final report has been safely produced.
- **FR-007**: Existing final caption-to-heading conflict blocking MUST continue to aggregate across all final diagnostics and MUST remain effective on cleanup no-op and changed-content paths.
- **FR-008**: Late processing MUST observe the existing stop request before reader cleanup, between cleanup calls, before final rebuild/re-evaluation, before narration, between narration calls, and before accepted-result persistence/completion.
- **FR-009**: After a stop request is observed, the pipeline MUST initiate no further model/provider calls and no accepted-result persistence; it MAY retain already-produced partial data under the existing stopped-run contract.
- **FR-010**: A stop observed during late processing MUST terminate with the existing stopped outcome and stopped activity/status semantics, not success, failure, or advisory-degradation semantics.
- **FR-011**: An in-flight external call MAY finish normally before cancellation is observed, but cancellation MUST be honored at the first safe boundary after it returns or fails.
- **FR-012**: Under advisory cleanup policy, a cleanup-stage failure MUST preserve the base DOCX/Markdown result and MUST remain visible as a non-blocking cleanup-failure notice through final state and UI reruns.
- **FR-013**: Later narration success, absence, or failure MUST NOT erase an existing cleanup advisory; when both cleanup and narration degrade, both facts MUST remain available to the user and diagnostics.
- **FR-014**: Cleanup failures and stop requests MUST remain distinguishable: cancellation MUST NOT be caught, logged, or presented as a cleanup failure.
- **FR-015**: When reader cleanup applies, the narration source MUST be derived from the final accepted post-cleanup text while preserving the existing narration inclusion/exclusion contract.
- **FR-016**: Text removed by accepted cleanup operations MUST be absent from narration, and accepted replacement/split/join content that remains narration-eligible MUST be represented in narration in final order.
- **FR-017**: If the final accepted cleanup text cannot be safely reconciled with narration eligibility metadata, the system MUST omit the narration artifact, preserve the accepted DOCX/Markdown, and show a non-blocking narration warning rather than publish stale or guessed TTS text.
- **FR-018**: The final artifact metadata and structured events MUST make it possible to determine whether cleanup ran, whether it changed or preserved the base result, which final diagnostics informed acceptance, whether narration was produced from the final accepted text, and whether the run stopped.
- **FR-019**: User-visible cleanup, narration, and stopped notices introduced or changed by this feature MUST be available in every locale supported by the current result screen.
- **FR-020**: Cleanup and narration degradation facts MUST coexist with the delivery disposition defined by `specs/044-result-delivery-integrity`; they MUST remain recorded when delivery is blocked, but MUST NOT override or soften a blocked disposition.

### Key Entities

- **Effective Reader-Cleanup Setting**: The resolved opt-in value used by a UI translation run after defaults and supported overrides are applied.
- **Final Evidence Set**: The delivered Markdown, delivered DOCX bytes, and final formatting diagnostics associated with the same build and processing run used to produce the authoritative acceptance verdict.
- **Late-Phase Cancellation Boundary**: A safe point before or between cleanup, rebuild, narration, validation, and persistence operations where an observed stop prevents subsequent work.
- **Degradation Notice**: Persistent, non-blocking user-visible information that a supplementary cleanup or narration capability failed while the base document remained deliverable.
- **Final Narration Source**: Narration-eligible content projected from the final accepted document state, not from superseded pre-cleanup chunks.

### Deterministic Narration Decision

When reader cleanup applies to a translation run, narration/TTS has exactly one authoritative textual source: the final accepted cleanup result. Existing narration inclusion/exclusion boundaries remain binding, but pre-cleanup `narration_chunks` may not be used as final narration merely because they are already available. If those boundaries cannot be mapped to the final text without guessing, narration is omitted with a visible warning; publishing stale narration is not an allowed fallback. This rule does not alter the standalone audiobook operation: translation reader cleanup never applies there, its existing narration-source contract remains authoritative, and it receives no new cleanup projection, omission, or warning behavior from this specification.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In configuration tests, 100% of explicitly enabled UI translation runs execute reader cleanup, while 100% of default/unset runs and non-translation operations retain disabled behavior.
- **SC-002**: In changed and no-op cleanup tests, 100% of final acceptance verdicts use delivered bytes and the final diagnostics set associated with that build/run; zero surviving authoritative reports reference a superseded diagnostic set.
- **SC-003**: In deterministic stop tests at every defined late-phase boundary, 100% terminate as stopped, initiate zero subsequent external calls after observation, and create zero accepted-result artifact groups.
- **SC-004**: In advisory cleanup-failure tests, 100% preserve the base DOCX/Markdown and retain a visible cleanup warning through final state and rerender.
- **SC-005**: In narration parity tests where cleanup removes or changes eligible text, 100% of published narration artifacts match final accepted content and contain zero text removed by cleanup.
- **SC-006**: In ambiguous narration-projection tests, zero stale narration artifacts are published and 100% retain the accepted DOCX/Markdown with a visible narration warning.
- **SC-007**: Existing tests for disabled cleanup, strict cleanup preservation, caption-conflict blocking, standalone audiobook narration, and advisory formatting review remain green.

## Non-goals

- Enabling reader cleanup by default — the rollout remains explicitly opt-in to limit production risk.
- Adding a new UI toggle or redesigning the settings panel — the current supported configuration surface is sufficient for activation parity.
- Expanding reader cleanup to edit or standalone audiobook operations — this spec repairs the existing translation workflow only.
- Changing cleanup prompts, accepted operation types, deletion thresholds, structural heuristics, or per-document quality behavior — those algorithms are outside the contract mismatch being fixed.
- Changing quality-gate thresholds or turning formatting coverage review data into a hard gate — Constitution VII remains binding.
- Forcibly aborting an in-flight network/provider call — bounded cancellation at the next safe boundary is sufficient and avoids provider-specific complexity.
- Persisting partial stopped outputs as accepted UI result artifacts — stopped work remains non-final.
- Guessing narration eligibility from text shape or document-specific literals when final cleanup lineage is insufficient — narration is omitted instead (Constitution VII).

## Anti-regression

- `reader_cleanup_default` remains `false` when neither configuration nor environment explicitly enables it.
- Reader cleanup remains restricted to translation and respects the existing `off` policy.
- Cleanup-disabled runs retain the existing single DOCX build path and do not incur cleanup model calls or extra final-report churn.
- A cleanup no-op preserves final Markdown text and existing formatting; only stale evidence fields may be refreshed.
- Spec 043 final-DOCX caption-conflict aggregation and delivery blocking remain intact on both changed and no-op cleanup paths.
- Formatting coverage remains advisory review data and is never promoted to a hard verdict gate by fresh-diagnostics work.
- Advisory cleanup failure continues to preserve and deliver the base document; visibility must not accidentally convert this fail-open path into a terminal failure.
- Existing strict-policy preservation behavior is not weakened or silently reclassified by the advisory-notice change.
- Stops before and during block/image phases retain their established behavior; new late checks use the same stopped outcome rather than a parallel cancellation state.
- Narration exclusions established from structural role/form remain effective after projection to final cleanup text; bibliography, intentionally excluded blocks, and image-only blocks must not leak into TTS.
- Standalone audiobook processing remains mutually exclusive with the additive narration post-pass and is unchanged by cleanup provenance work.
- No credit/subtraction rule is introduced. If implementation introduces any rule that subtracts content from a defect/loss count, it MUST add the Constitution VII anti-vacuum counter-proof proving genuine body content is still counted.

## Assumptions

- The loaded `reader_cleanup_default` value, after supported environment override, is the authoritative opt-in source for ordinary UI runs; validation/run profiles may continue to supply their explicit effective setting through their existing path.
- Spec 048's run/source-owned diagnostics contract is implemented before this feature. Final diagnostics are associated with the final build through that ownership contract; no temporary mtime/build-window compatibility path is permitted.
- The existing stopped outcome and stopped UI messaging are the authoritative cancellation semantics and should be reused.
- Advisory reader-cleanup failure is a degraded success of the base document, not acceptance of a cleaned document.
- Existing cleanup identity/lineage and narration eligibility metadata are sufficient for normal final-text projection; the deterministic omit-with-warning rule handles cases where they are not.
- Artifact paths, retention, and canonical event requirements will be specified concretely in the implementation plan/quickstart in accordance with Constitution V and `docs/LOGGING_AND_ARTIFACT_RETENTION.md`.
