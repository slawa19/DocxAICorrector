# Feature Specification: Stable Source and Preparation Identity

**Feature Branch**: `[045-source-preparation-identity]`

**Created**: 2026-07-20

**Status**: Draft

**Input**: User description: "Preserve authoritative PDF/DOC source identity across persisted normalized-payload reuse, verify that payload independently, and make UI preparation identity sensitive to source and target languages."

**Date**: 2026-07-20

**Owner surface**: persisted restart/completed source contract + UI preparation request identity

**Companion**: `specs/040-preparation-cache-tenant-identity/spec.md` (prepared-cache identity isolation); `docs/specs/GLOBAL_PLAN_2026-06-16.md` (living roadmap)

**Changelog**:

- 2026-07-20 — Initial specification from the accepted round-10 findings F3 and F11, verified against current `main @ 23020a9`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reuse a converted source without identity drift (Priority: P1)

After a successful PDF or legacy DOC run, a user can start another run from the persisted normalized document without the application treating it as a different upload. The restored document keeps the identity of the original source while its stored normalized payload is checked independently for integrity.

**Why this priority**: False source changes discard valid result/preparation state and can repeat expensive conversion work even though the persisted normalized document is already usable.

**Independent Test**: Complete and persist a PDF or DOC-derived normalized document, restore it without uploading the original again, and verify that the source token is unchanged, the normalized bytes pass integrity validation, and no conversion is requested.

**Acceptance Scenarios**:

1. **Given** a persisted normalized payload produced from a PDF and carrying its authoritative source identity and matching integrity metadata, **When** the application restores it, **Then** the restored upload has the same source token as the original PDF and reuses the normalized payload without reconversion.
2. **Given** the equivalent persisted payload produced from a legacy DOC, **When** it is restored, **Then** the same identity and reuse guarantees apply.
3. **Given** a successfully restored payload, **When** source-selection synchronization runs, **Then** it does not report a source change or clear state solely because the payload bytes are normalized DOCX bytes.

---

### User Story 2 - Refresh preparation when languages change (Priority: P1)

A user who changes the selected source or target language receives preparation data built for the new language pair rather than a previously prepared context selected under the old pair.

**Why this priority**: Language-sensitive glossary and document context can influence every processed block; reusing them after a language change produces a plausible but incorrect run configuration.

**Independent Test**: Prepare one upload for one language pair, change only the source language and then only the target language, and verify that each semantically different pair selects a distinct preparation request while equivalent normalized values reuse the same request.

**Acceptance Scenarios**:

1. **Given** an upload prepared for English to Russian, **When** the target language changes to German, **Then** the old prepared context is not selected and a German-target preparation is requested.
2. **Given** the same upload and target language, **When** the source language changes, **Then** the old prepared context is not selected.
3. **Given** language values that differ only by accepted casing or surrounding whitespace, **When** the request identity is evaluated, **Then** they resolve to the same preparation request.

---

### User Story 3 - Reject unusable persisted payloads safely (Priority: P2)

A user is not given a silently corrupted or ambiguously identified persisted source. If the saved payload cannot be verified, the application treats it as unavailable and asks for a fresh upload instead of inventing identity from normalized bytes.

**Why this priority**: The persisted cache is a convenience mechanism; preserving trustworthy document identity is more important than attempting speculative recovery from incomplete or damaged cache data.

**Independent Test**: Modify the persisted payload, its size, digest, or required identity metadata and verify that restoration is refused without processing the altered bytes or deleting files outside the governed cache location.

**Acceptance Scenarios**:

1. **Given** persisted bytes that do not match their stored integrity metadata, **When** restoration is attempted, **Then** the record is rejected and the user must provide the source again.
2. **Given** a legacy or incomplete record that lacks enough metadata to verify both source identity and payload integrity, **When** restoration is attempted, **Then** it is treated as unavailable rather than assigned a token derived from normalized bytes.

### Edge Cases

- A native DOCX uses the same source and payload bytes; its current stable token and no-conversion path remain unchanged.
- Two different original PDF/DOC files may normalize to identical bytes; they retain distinct authoritative source tokens even if their payload-integrity values match.
- The same original source may normalize differently after converter changes; its source token remains stable, while payload-integrity metadata accurately describes the particular persisted normalized bytes.
- A zero-length, missing, truncated, or altered persisted payload is not restored.
- Defaulted and explicitly selected equivalent language values produce one canonical request identity; genuinely different source or target languages do not.
- Changing languages while a prior preparation exists must not expose that prior context as current, even if the document, chunk size, and operation are unchanged.

## Verified findings

- **Original-source identity is intentional** — token components for PDF and legacy DOC use the original source bytes, not normalized DOCX bytes, `src/docxaicorrector/processing/processing_runtime.py:1265` (verified 2026-07-20).
- **Materialization preserves that identity** — PDF/DOC conversion produces normalized DOCX bytes but explicitly carries the original payload token forward, `src/docxaicorrector/processing/processing_runtime.py:1502` and `src/docxaicorrector/processing/processing_runtime.py:1555` (verified 2026-07-20). The deterministic PDF contract test passed through the canonical WSL entry point on 2026-07-20: `tests/test_processing_runtime.py:1494`.
- **Persistence does not record independent payload integrity or source format** — a persisted record contains filename, authoritative token, path, and byte size, while the bytes are stored directly, `src/docxaicorrector/processing/restart_store.py:43` (verified 2026-07-20).
- **Restoration drops the authoritative token** — completed/restart restoration rebuilds an in-memory upload from only the persisted filename and bytes, `src/docxaicorrector/ui/application_flow.py:73` and `src/docxaicorrector/ui/application_flow.py:95` (verified 2026-07-20). A subsequent upload-token build therefore derives identity from the restored normalized DOCX payload via `src/docxaicorrector/processing/processing_runtime.py:1574`, rather than retaining the stored PDF/DOC source token (verified 2026-07-20).
- **UI preparation identity omits languages** — the outer request marker contains upload identity, chunk size, and optionally operation, but no source or target language, `src/docxaicorrector/processing/processing_runtime.py:1605` (verified 2026-07-20). Both UI call sites omit language values despite resolving them before preparation, `src/docxaicorrector/ui/_app.py:813` and `src/docxaicorrector/ui/_app.py:853` (verified 2026-07-20). The current deterministic marker contract passed through the canonical WSL entry point on 2026-07-20: `tests/test_processing_runtime.py:105`.
- **The underlying prepared-document identity is already language-sensitive** — source and target languages are canonicalized and included in the prepared source key, `src/docxaicorrector/processing/preparation.py:306` (verified 2026-07-20). The defect is therefore the stale outer UI request selection, not a need to redesign the preparation cache.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every newly persisted normalized PDF/DOC payload MUST retain the authoritative identity of the original uploaded source independently of the normalized payload bytes.
- **FR-002**: Every newly persisted payload MUST carry independently checkable integrity metadata covering the exact stored bytes, including both byte length and a content digest.
- **FR-003**: Restoration MUST verify the stored payload against its integrity metadata before making it available for preparation or processing.
- **FR-004**: A successfully verified restored payload MUST preserve the stored authoritative source token throughout selection, preparation, processing, and result matching; the token MUST NOT be recomputed from normalized bytes.
- **FR-005**: A successfully verified normalized PDF/DOC payload MUST be reused directly and MUST NOT invoke PDF or DOC conversion again.
- **FR-006**: A missing, empty, corrupted, or insufficiently described persisted record MUST be treated as unavailable and MUST NOT be assigned a guessed identity. The user-facing workflow MUST remain recoverable through a fresh upload.
- **FR-007**: Persisted-source cleanup and retention MUST continue to obey the existing confined-path and expiry rules; added identity metadata MUST NOT broaden deletion scope.
- **FR-008**: The UI preparation request identity MUST include canonical source language and canonical target language in addition to the document, chunk-size, and operation axes already represented.
- **FR-009**: Semantically different source-language or target-language selections MUST produce different UI preparation request identities; equivalent normalized values MUST produce the same identity.
- **FR-010**: When either language changes, preparation lookup MUST NOT return a context prepared for the previous language pair.
- **FR-011**: Native DOCX uploads MUST retain their existing stable identity and no-conversion behavior across initial upload and persisted reuse.
- **FR-012**: Identity and integrity failures MUST be observable through the existing user-facing error/activity and structured logging conventions without logging document contents.

### Key Entities

- **Authoritative Source Identity**: Stable identity of the original user upload, including its original-source token and enough format/name context to distinguish it from the normalized working payload.
- **Normalized Payload Integrity**: Independently verifiable description of the exact persisted working bytes, including their size and content digest.
- **Persisted Source Record**: Restart/completed cache record binding authoritative source identity to a verified normalized payload and its governed storage location.
- **Preparation Request Identity**: Canonical identity of the preparation requested by the UI, covering source identity, chunk size, operation, source language, and target language.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of deterministic PDF and legacy DOC persist/restore scenarios, the restored source token equals the original upload token.
- **SC-002**: In 100% of verified persisted PDF/DOC reuse scenarios, the normalized payload is reused with zero conversion attempts.
- **SC-003**: In 100% of corruption cases covering changed bytes, changed length, changed digest, missing bytes, and missing required identity metadata, restoration is refused before preparation begins.
- **SC-004**: For one document and fixed non-language settings, changing either source or target language produces a distinct preparation request in 100% of supported-language test pairs; equivalent normalized values produce the same request.
- **SC-005**: Existing native-DOCX upload, restart, and completed-source scenarios retain their current token and reuse behavior with no new user action.
- **SC-006**: A user can recover from every rejected persisted-source case by uploading the source again, without restarting the application process.

## Non-goals

- Retaining a second full copy of the original PDF or legacy DOC alongside the normalized payload is not required; stable source identity plus independently verified normalized bytes is sufficient for this workflow.
- Redesigning the shared preparation cache, its eviction policy, tenant identity, or all configuration fingerprints is excluded; `specs/040-preparation-cache-tenant-identity` and the existing prepared-source key govern those concerns.
- Changing conversion output, PDF/DOC import quality, document structure recognition, or formatting restoration is excluded because neither accepted finding originates in those transformations.
- Recovering corrupted persisted bytes, inferring a missing original token, or migrating unverifiable legacy records is excluded; the safe bounded behavior is to reject the convenience cache and request a fresh upload.
- Changing final result-artifact locations or treating `.run/completed_*` files as output documents is excluded; they remain persisted source cache only.
- Document-specific filename, content, or language literals are forbidden. A defect without a general identity rule is accepted rather than patched (Constitution VII).

## Anti-regression

- The same original PDF/DOC bytes retain one authoritative source token regardless of converter output; a changed normalized payload changes only its independent integrity value.
- Different original sources that happen to normalize identically remain different sources; payload equality MUST NOT collapse authoritative identities.
- A native DOCX continues to use its actual bytes for both source identity and payload integrity and does not enter a conversion path.
- A verified restored normalized payload is accepted; a one-byte mutation and a size/digest mismatch are rejected. This is the counter-proof that integrity validation cannot become a vacuous always-pass credit.
- A source or target language change invalidates only the stale UI preparation selection; returning to the same canonical pair remains eligible for normal cache reuse.
- Existing operation and chunk-size distinctions in preparation request identity remain effective.
- Existing confined deletion, TTL cleanup, result-token matching, and restart/completed-source lifecycle behavior remain intact.
- No rule introduced by this feature keys on a book title, filename literal, source text, or substring (Constitution VII).

## Assumptions

- Persisted restart/completed sources are an ephemeral convenience cache; rejecting an unverifiable old record and requesting re-upload is preferable to silently assigning a false identity.
- The normalized DOCX payload is the appropriate reusable working artifact for PDF/DOC processing after the initial conversion.
- Source and target language values have an existing canonical default and normalization policy; request identity will use the same semantic normalization so cosmetic value differences do not cause needless preparation.
- The authoritative token already computed from the original upload remains the source of truth; this feature does not introduce a second competing source-token algorithm.
- Existing logging and artifact-retention contracts are sufficient; the plan may extend an existing record or event context but should not introduce a parallel persistence system.
