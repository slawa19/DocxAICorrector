# Feature Specification: Result Delivery Integrity

**Feature Branch**: `[044-result-delivery-integrity]`

**Created**: 2026-07-20

**Status**: Draft

**Input**: User description: "Implement the agreed round-10 F1/F2 remediation: sanitize marker-mode controlled fallbacks and make blocked quality-gate results honest in the UI."

**Date**: 2026-07-20

**Owner surface**: model-response controlled fallback + final quality-gate disposition + UI result presentation/download

**Companion**: User-approved code-review round 10 findings F1 and F2 (2026-07-20)

**Changelog**:

- 2026-07-20 — Initial specification from fresh current-code trace and deterministic WSL reproduction.
- 2026-07-20 — Cross-spec review clarified that blocked delivery remains primary without erasing independent cleanup/narration degradation facts from spec 047.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Safe source fallback in marker mode (Priority: P1)

As a user processing a document, I receive readable source content when the model exhausts a controlled fallback path, without internal paragraph-control markers appearing in the output.

**Why this priority**: Internal `DOCX_PARA` markers are pipeline control data. Exposing them turns a recoverable model failure into visible document corruption and can carry that corruption into the final DOCX.

**Independent Test**: Force each supported controlled source-fallback condition for a marker-mode block and verify that the returned text preserves the source paragraph content but contains no internal paragraph markers.

**Acceptance Scenarios**:

1. **Given** a marker-mode block containing paragraph markers, **When** incomplete-response recovery is exhausted and source fallback is allowed, **Then** the fallback contains the original paragraph text in order and no `DOCX_PARA` marker.
2. **Given** the same marker-mode block, **When** empty-response recovery is exhausted and source fallback is allowed, **Then** the fallback contains the original paragraph text in order and no `DOCX_PARA` marker.
3. **Given** the same marker-mode block, **When** the model remains in a non-completed state after bounded retries and source fallback is allowed, **Then** the fallback contains the original paragraph text in order and no `DOCX_PARA` marker.
4. **Given** a persistent marker-validation failure, **When** the existing controlled source fallback is used, **Then** it remains marker-free and preserves the source paragraph text.

---

### User Story 2 - Honest blocked-result presentation (Priority: P1)

As a user whose generated document is rejected by the final quality gate, I see that the result is blocked rather than successfully completed, while any retained bytes remain available only as an explicitly diagnostic download.

**Why this priority**: A green success state and ordinary primary download for a rejected document contradict the delivery gate and can cause a user to trust a result that the pipeline declared unsafe to deliver.

**Independent Test**: Produce a non-empty result rejected by the final quality gate, rerender the application for the same source, and verify that the blocked disposition survives the result-bundle boundary and drives both the notice and download presentation.

**Acceptance Scenarios**:

1. **Given** a final quality-gate failure with non-empty DOCX bytes, **When** the result view is rendered, **Then** no success confirmation is shown and a prominent blocked-result explanation is shown.
2. **Given** a blocked result whose bytes are retained for inspection, **When** download controls are rendered, **Then** every offered control identifies the download as blocked/diagnostic rather than as the accepted result.
3. **Given** a blocked result and a rerun of the application for the same source, **When** the stored result is reconstructed, **Then** its blocked disposition and explanation are preserved and the UI does not infer success merely from the presence of bytes.
4. **Given** an accepted result, **When** the result view is rendered, **Then** the normal success confirmation and normal result-download labels remain available.
5. **Given** an advisory (`warn`) quality outcome, **When** the result view is rendered, **Then** the result remains accepted and downloadable while its existing warning/review information remains visible.

### Edge Cases

- A blocked gate result with no non-empty DOCX remains an ordinary failure; this feature does not invent a diagnostic download for absent bytes.
- Both the initial final gate and the post-reader-cleanup final gate must produce the same blocked presentation when they reject a non-empty result.
- A page rerun or source reselection must not turn a retained blocked result into an accepted result because its source token still matches.
- Image-only passthrough content is not paragraph-marker fallback content and must retain its existing placeholder behavior.

## Verified findings

- **F1 — three controlled source-fallback branches return the marker-bearing input** — marker mode first derives a validated marker-free source value at `src/docxaicorrector/generation/_generation.py:991`, and the marker-validation fallback already returns that value at `src/docxaicorrector/generation/_generation.py:1060`; however, exhausted incomplete-response, empty-response, and non-completed-response branches return the original `target_text` at `src/docxaicorrector/generation/_generation.py:1050`, `src/docxaicorrector/generation/_generation.py:1074`, and `src/docxaicorrector/generation/_generation.py:1091` (verified 2026-07-20).
- **F1 live reproduction** — a deterministic marker-mode request whose responses remained incomplete returned `[[DOCX_PARA_p0001]]\nSource paragraph` unchanged. Reproduced on 2026-07-20 in the canonical WSL runtime with `bash scripts/test.sh tests/_spec044_evidence_test.py -vv`; the temporary evidence test passed and was then removed (2-test evidence run: 2 passed).
- **F2 — the pipeline retains bytes and an error notice while returning a failed outcome** — on a final quality-gate failure the pipeline emits non-empty Markdown/DOCX together with an error-level `latest_result_notice`, then emits the failed terminal result at `src/docxaicorrector/pipeline/late_phases.py:670` through `src/docxaicorrector/pipeline/late_phases.py:724` (verified 2026-07-20). The existing gate test also requires that primary UI artifacts are not persisted for this path at `tests/test_late_phases_finalize_gate_persistence.py:509` (verified 2026-07-20).
- **F2 — the result boundary drops the notice** — the current result bundle carries source identity, bytes, text, operation, narration mode, and quality warning, but not `latest_result_notice`, at `src/docxaicorrector/processing/processing_runtime.py:1611` through `src/docxaicorrector/processing/processing_runtime.py:1658` (verified 2026-07-20).
- **F2 — the UI equates matching non-empty bytes with completion** — the selected-file path sets `has_completed_result` from retained DOCX/narration bytes plus source-token equality, without consulting the failed outcome or blocked notice, and then calls the completed-result renderer at `src/docxaicorrector/ui/_app.py:993` through `src/docxaicorrector/ui/_app.py:1027` (verified 2026-07-20).
- **F2 — the completed renderer always supplies a success message** — the common renderer forwards an unconditional success message and no blocked notice at `src/docxaicorrector/ui/_app.py:677` through `src/docxaicorrector/ui/_app.py:694`; the download renderer displays that success before creating ordinary result downloads at `src/docxaicorrector/ui/_ui.py:818` through `src/docxaicorrector/ui/_ui.py:905` (verified 2026-07-20).
- **F2 live reproduction** — a deterministic call to the current completed renderer with non-empty blocked DOCX bytes and an error-level result notice still forwarded a success message and omitted the notice from its rendering contract. Reproduced on 2026-07-20 in the same canonical WSL evidence run described above; the temporary test passed as a characterization of the defect and was removed afterward.

## Requirements *(mandatory)*

### Functional Requirements

> **Binding rule for detection/classification (Constitution VII, item 8)**: any rule that detects, classifies, credits, or excludes content MUST key on document region, structural role, or form — never on a word list, a signal count, or a literal taken from one book. Per-book literals do not transfer to the next document and are rejected in review.

- **FR-001**: Every controlled source fallback after exhausted incomplete, empty, non-completed, or marker-validation response handling MUST return marker-free paragraph content when paragraph-marker mode is active.
- **FR-002**: Marker removal MUST be based on the pipeline's structural paragraph-marker form and MUST preserve the source paragraph text, order, Unicode content, Markdown content, and non-paragraph placeholders.
- **FR-003**: When paragraph-marker mode is inactive, controlled source fallbacks MUST retain their existing source-text behavior without newly stripping text that merely resembles ordinary document content.
- **FR-004**: Existing retry limits, retry classification, fallback eligibility, and fallback observability MUST remain unchanged except for the corrected marker-free returned payload and accurate returned-length metadata.
- **FR-005**: A final quality-gate rejection MUST produce a machine-readable blocked delivery disposition that remains associated with retained result bytes across the pipeline, session, result-bundle, and UI boundaries.
- **FR-006**: The blocked disposition MUST include a user-readable explanation and MUST remain distinguishable from accepted-with-warning review information.
- **FR-007**: The UI MUST NOT display a success confirmation for a result whose final delivery disposition is blocked.
- **FR-008**: The UI MUST determine whether a retained result is accepted or blocked from its final delivery disposition; byte presence and source-token equality alone MUST NOT establish successful completion.
- **FR-009**: If blocked bytes are offered for download, the surrounding notice and every applicable download label MUST clearly identify them as blocked diagnostic material, not as the accepted output.
- **FR-010**: A blocked result MUST remain excluded from primary UI result persistence and MUST NOT be reported through the accepted-result artifact signal.
- **FR-011**: Accepted results, including advisory-warning results, MUST continue to use the normal success/download flow and existing review presentation.
- **FR-012**: Both ordinary final-gate rejection and post-reader-cleanup final-gate rejection MUST obey the same blocked-result presentation contract.
- **FR-013**: The corrected presentation MUST be consistent in both completed-result entry paths: restored/current result rendering and same-source selected-file rendering.
- **FR-014**: User-facing blocked notices and diagnostic-download labels MUST be available in every locale supported by the existing result screen.
- **FR-015**: A blocked delivery disposition MUST remain the primary result status without erasing independently recorded non-blocking cleanup or narration degradation facts; those facts MUST NOT turn a blocked result into an accepted result.

### Key Entities

- **Controlled Source Fallback**: A permitted return of the original block content after bounded model-response handling fails; its payload must be safe for downstream document assembly.
- **Delivery Disposition**: The authoritative final classification of a result as accepted, accepted with advisory information, or blocked from normal delivery.
- **Result Bundle**: The state passed to the common result renderer, including source identity, available payloads, delivery disposition, explanation, and advisory review data.
- **Blocked Diagnostic Download**: Retained result bytes offered for investigation without representing them as accepted primary output or persisting them as ordinary UI result artifacts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In deterministic tests covering all four controlled source-fallback classes in paragraph-marker mode, 100% of returned payloads preserve the expected source text and contain zero internal paragraph markers.
- **SC-002**: In deterministic UI tests covering both result entry paths and both final-gate rejection points, 100% of blocked results show a blocked explanation and 0% show a success confirmation.
- **SC-003**: For every blocked result that offers retained bytes, 100% of applicable download controls identify the payload as blocked/diagnostic.
- **SC-004**: In regression tests for accepted and advisory-warning results, 100% retain the normal success confirmation, normal download labels, and existing advisory review information.
- **SC-005**: In blocked-result persistence tests, zero accepted output artifact groups are created and zero accepted-result saved signals are emitted.
- **SC-006**: Existing image-only passthrough and non-marker source-fallback tests remain behaviorally unchanged.

## Non-goals

- Changing which quality checks produce `pass`, `warn`, or `fail` — this work makes delivery presentation honest; it does not redesign gate policy.
- Changing retry counts, provider fallback order, model budgets, or which response failures qualify for source fallback — none is needed to remove leaked paragraph markers.
- Redesigning the paragraph-marker protocol or removing paragraph markers from the model-facing request — the markers remain necessary control data before fallback/output finalization.
- Persisting blocked diagnostic bytes as ordinary `.run/ui_results/*.result.*` artifacts — that would contradict the existing delivery-gate and artifact contract.
- Adding a new long-term retention class for blocked bytes — current-session diagnostic availability is sufficient for this remediation.
- Changing reader-cleanup behavior, formatting-review classification, source identity, preparation caching, or diagnostics scoping — those concerns belong to separate agreed specifications.
- Patching document-specific content or adding substring heuristics — this feature is keyed only on an existing universal control-marker form and delivery disposition (Constitution VII).

## Anti-regression

- Non-marker-mode controlled source fallback must continue returning the original source text without semantic rewriting.
- Persistent marker-validation fallback must remain marker-free; the already-correct neighboring branch is the reference behavior, not a new exception.
- Paragraph-marker sanitization must preserve Unicode, Markdown formatting, paragraph order, and image placeholders; it must not strip arbitrary bracketed user text.
- Image-only target passthrough must retain its existing placeholder-preservation behavior and must not call the model merely because fallback sanitation changed.
- Accepted results must continue to show the existing success state and ordinary DOCX/Markdown/narration downloads.
- Advisory formatting coverage remains review data rather than a hard gate, as required by Constitution VII; an advisory result must not be relabeled blocked.
- Coexisting cleanup or narration degradation notices introduced by `specs/047-reader-cleanup-production-parity` must survive result bundling; delivery disposition remains the sole authority for accepted-versus-blocked presentation.
- A blocked result must continue to produce a failed terminal outcome, must not write primary `.run/ui_results/` artifacts, and must not emit `ui_result_artifacts_saved`.
- No credit/subtraction rule is introduced by this feature, so Constitution VII's anti-vacuum counter-proof requirement is not applicable; tests must nevertheless include ordinary bracketed text to prove marker sanitation is form-scoped rather than broad text removal.

## Assumptions

- The final quality-gate disposition is authoritative for user-facing delivery, while retained non-empty bytes may still be useful for immediate diagnosis.
- A blocked diagnostic download is available only when bytes already exist; the feature does not synthesize an artifact after an empty-output failure.
- Existing result-screen locales are the complete localization scope for this change.
- Existing primary artifact and structured logging contracts remain authoritative: accepted UI results live under `.run/ui_results/` and use `ui_result_artifacts_saved`; blocked diagnostic bytes do not.
- The temporary 2026-07-20 evidence test was characterization-only and was intentionally removed; implementation must add durable regression tests under the repository's normal test suite.
