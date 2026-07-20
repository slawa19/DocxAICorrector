# Feature Specification: Universal Short-Heading Evidence

**Feature Branch**: `[046-universal-short-heading-evidence]`

**Created**: 2026-07-20

**Status**: Draft

**Input**: User description: "Remove length-only promotion of very short body paragraphs to headings. Preserve only universal, source-backed heading evidence; if the source has no structural or form signal, do not repair it."

**Date**: 2026-07-20

**Owner surface**: DOCX/PDF-normalized paragraph-role preparation before semantic-block assembly

**Companion**: `docs/reviews/CODE_REVIEW_ROUND10_2026-07-20.md` (F5); `.specify/memory/constitution.md` (Constitution VII)

**Changelog**:

- 2026-07-20 — Initial specification from the agreed round-10 F5 finding, verified against current `main @ 23020a9`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Keep short body content as body (Priority: P1)

As a user preparing a document, I need a short standalone body paragraph to remain body content when the source provides no heading role, level, or typographic/structural form evidence, so ordinary text is not silently turned into a heading.

**Why this priority**: A false heading changes document structure, block boundaries, output formatting, navigation, and later validation. The current behavior can create that error solely because a paragraph has four or fewer words.

**Independent Test**: Prepare a document containing a short unstyled body paragraph between ordinary body paragraphs, in both supported structure-recovery modes, and verify that its role, structural role, heading level/source, and heuristic hint remain non-heading values.

**Acceptance Scenarios**:

1. **Given** a one-to-four-word paragraph whose source role is body and which has no heading level, heading style, outline level, or distinct typographic form, **When** the document is prepared, **Then** it remains body and receives no heading-level assignment or heading hint.
2. **Given** otherwise identical no-signal body paragraphs that differ only by capitalization, leading ordinal, punctuation, length, or surrounding prose length, **When** the document is prepared, **Then** none is promoted or hinted as a heading from those text-shape properties.
3. **Given** the same no-signal paragraph under legacy and AI-first structure-recovery settings, **When** each document is prepared, **Then** neither setting invents heading semantics.

---

### User Story 2 - Preserve genuine source-backed headings (Priority: P2)

As a user whose document contains a genuinely short heading, I need its heading role preserved when the source carries explicit structural evidence or an already-supported universal form signal, so eliminating the unsafe shortcut does not erase valid structure.

**Why this priority**: The correction must stop false positives without creating a vacuum that demotes real headings for which the source does provide reusable evidence.

**Independent Test**: Prepare short headings represented by explicit heading semantics and by an existing universal form signal, then verify that both retain or receive the expected heading semantics while an adjacent no-signal short body control remains body.

**Acceptance Scenarios**:

1. **Given** a short paragraph with an explicit heading role, heading level, heading style, or outline level, **When** the document is prepared, **Then** its source-backed heading semantics are preserved.
2. **Given** a short body-classified paragraph with an already-supported universal typographic distinction from its body context, **When** the current form-based recovery rule applies, **Then** removing the length-only shortcut does not prevent that rule from recognizing the heading.
3. **Given** one source-backed short heading and one no-signal short body paragraph in the same acceptance set, **When** both are prepared, **Then** only the source-backed candidate has heading semantics.

---

### User Story 3 - Respect authoritative classifications (Priority: P3)

As an operator using structure recovery, I need authoritative paragraph classifications to survive deterministic post-processing, so a body or attribution decision is not overwritten by a lower-confidence short-text heuristic.

**Why this priority**: This protects existing precedence behavior and ensures the fix does not relocate the same false-positive problem into the hint path.

**Independent Test**: Pass short paragraphs already classified as body or attribution with authoritative confidence through preparation and verify that their role and structural metadata are unchanged.

**Acceptance Scenarios**:

1. **Given** a short paragraph authoritatively classified as body, **When** short-heading recovery runs, **Then** it remains body without a heuristic heading level or source.
2. **Given** a short paragraph authoritatively classified as an attribution, **When** short-heading recovery runs, **Then** its attribution semantics remain intact.

### Edge Cases

- A single-word or empty-looking paragraph has no special entitlement to heading status; without source evidence it remains unchanged.
- A leading number, all-capital text, title case, a missing terminal period, or placement between long paragraphs is text shape/context, not structural evidence.
- A short paragraph with explicit heading semantics remains a heading even if its typography is visually indistinguishable from nearby body text.
- A short paragraph with a supported universal form distinction is evaluated by that form-based rule, not by a word-count bypass.
- Existing protection for AI-classified body and attribution paragraphs remains effective.
- Front-matter title normalization is a separate bounded region rule and is not changed by this feature.

## Verified findings

- **Length-only promotion is live** — after body-context checks, any candidate accepted by `_is_very_short_standalone_heading_text` is immediately promoted or hinted without requiring a font, alignment, style, outline, or structural-role signal, `src/docxaicorrector/document/roles.py:230` (verified 2026-07-20 on `main @ 23020a9`).
- **The decisive predicate is text shape** — the very-short predicate accepts up to four words and 48 normalized characters, while its parent predicate is also based on character count, word count, caption text, and punctuation, `src/docxaicorrector/document/roles.py:448` and `src/docxaicorrector/document/roles.py:464` (verified 2026-07-20 on `main @ 23020a9`).
- **The unsafe rule is in the normal preparation path** — extraction invokes short-heading promotion after logical paragraph construction and inline-break normalization, before front-matter title normalization and later semantic processing, `src/docxaicorrector/document/extraction.py:222` and `src/docxaicorrector/document/extraction.py:234` (verified 2026-07-20 on `main @ 23020a9`).
- **Fresh deterministic proof** — the current test constructs an unstyled, same-size, very short paragraph between body paragraphs and expects it to become `heading` with level 2, `tests/test_document_extraction.py:1729` and `tests/test_document_extraction.py:1748`; the canonical WSL command `bash scripts/test.sh tests/test_document_extraction.py::test_extract_document_content_from_docx_promotes_very_short_subheading_between_body_paragraphs_without_larger_font -vv -x` passed on 2026-07-20 against the current workspace at `main @ 23020a9`, proving the undesired behavior is live rather than inferred from a stale artifact.
- **A bounded form-evidence path already exists** — candidates outside the very-short bypass require available contextual font sizes and a universal font-size delta before heading semantics are applied, `src/docxaicorrector/document/roles.py:238` and `src/docxaicorrector/document/roles.py:252` (verified 2026-07-20 on `main @ 23020a9`).
- **Authoritative AI decisions already have precedence** — short-heading recovery skips paragraphs with AI confidence, `src/docxaicorrector/document/roles.py:213` and `src/docxaicorrector/document/roles.py:216` (verified 2026-07-20 on `main @ 23020a9`).

## Requirements *(mandatory)*

### Functional Requirements

> **Binding rule for detection/classification (Constitution VII)**: heading detection and repair MUST key on a source document region, structural role, or form. Text length, word count, capitalization, a leading ordinal, punctuation, position, neighboring prose length, a per-document string, and broad substring matching MUST NOT substitute for a source signal. No source signal means no repair.

- **FR-001**: The system MUST NOT assign a heading role, structural role, heading level, heading source, or heuristic heading hint solely because a paragraph is short or has heading-like text shape.
- **FR-002**: A paragraph that arrives as body with no source heading/structural/form signal MUST retain its incoming non-heading semantics in both legacy and AI-first recovery modes.
- **FR-003**: Existing explicit source heading evidence, including a declared heading role/level, heading style, or outline level, MUST remain authoritative regardless of paragraph length.
- **FR-004**: Existing universal form-based recovery MAY continue only where its positive decision is independently supported by source form metadata; the removed length-only shortcut MUST NOT be replaced by another text-shape shortcut.
- **FR-005**: Existing precedence for authoritative body, attribution, caption, list, table, and image classifications MUST remain unchanged.
- **FR-006**: The correction MUST apply on the normal document-preparation path before semantic-block assembly, so downstream consumers receive one consistent role contract.
- **FR-007**: Regression expectations that currently require no-signal very-short body text to become a heading MUST be replaced with expectations matching the no-source-signal contract.
- **FR-008**: All detection rules and acceptance examples MUST be reusable across documents and languages; implementation MUST introduce no book-specific literals, title vocabulary, word lists, or containment matchers.
- **FR-009**: Acceptance evidence MUST include paired anti-vacuum counter-proofs: at least one no-signal short body paragraph remains body, and at least one genuinely short heading with explicit or supported universal form evidence remains a heading.
- **FR-010**: This feature MUST NOT add external inference, new validation gates, user-visible artifacts, or new logging/retention behavior.

### Key Entities

- **Prepared paragraph**: A source paragraph together with its text, role, structural role, confidence, heading level/source, heuristic hint, and available form metadata.
- **Source heading evidence**: Existing source-carried semantics or universal form metadata that can justify a heading decision independently of the lexical shape of the paragraph text.
- **No-signal paragraph**: A paragraph whose source provides no heading role, structural role, level, style, outline, or supported distinct form evidence; its missing structure is accepted rather than guessed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the acceptance set, 100% of one-to-four-word body controls without source evidence remain body and receive no heading level, heading source, or heading hint in every supported recovery mode.
- **SC-002**: In the paired anti-vacuum acceptance set, 100% of short headings carrying explicit source semantics retain their heading role and level.
- **SC-003**: In the paired form-evidence acceptance set, the existing supported universal form-based heading case remains recognized while its same-text, no-form-signal control remains body.
- **SC-004**: Zero acceptance decisions depend on a document-specific phrase, title vocabulary, capitalization, leading ordinal, word-count threshold, or substring match as positive heading evidence.
- **SC-005**: All existing protected non-heading classifications covered by the focused extraction acceptance set remain unchanged after the correction.
- **SC-006**: In the focused acceptance tests, processing the same synthetic documents before and after the correction adds zero external/provider calls and zero new preparation stages; the change only removes the unsupported classification path.

## Non-goals

- Recovering headings from body paragraphs that carry no source structural or form signal — these rare quality tails are explicitly ACCEPTED under Constitution VII; the honest follow-up is to fix an importer so a reusable signal exists, not to guess in assembly.
- Designing a new heading classifier, adding AI inference, or broadening the current typography rules — this feature removes one unsafe shortcut and preserves established source-backed behavior.
- Changing front-matter display-title normalization — it is a separate bounded document-region rule with separate behavior and regression coverage.
- Changing TOC, footnote, caption, list, table, image, or paragraph-boundary handling — those surfaces are not required to correct the length-only branch.
- Adding per-language title lexicons, per-book literals, ordinal patterns, capitalization rules, or substring heuristics — these do not transfer safely to new documents.
- Turning structural review data into a delivery gate or adding a verifier to compensate for ambiguous source data — Constitution VII requires acceptance, not gating, when no general repair rule exists.
- Reworking downstream semantic-block assembly or output formatting — they should consume corrected preparation roles without unrelated refactoring.

## Anti-regression

- **No-signal body counter-proof**: add or rename a focused acceptance test such as `test_extract_document_content_from_docx_does_not_promote_very_short_body_without_source_signal`; it MUST assert unchanged `role`, `structural_role`, `heading_level`, `heading_source`, and heuristic heading hint in both recovery modes.
- **Explicit-heading counter-proof**: retain a focused test such as `test_extract_document_content_from_docx_preserves_very_short_explicit_heading`; it MUST prove a genuine short heading with source style/outline/level evidence is not demoted.
- **Form-signal counter-proof**: keep `test_extract_document_content_from_docx_promotes_short_larger_subheading_between_body_paragraphs` or an equivalent paired test green; it MUST prove removal of the length-only bypass does not vacuum away the existing universal font/form signal.
- **Matched negative control**: the form-signal test MUST include or be paired with a candidate whose text and body context are equivalent but whose form distinction is absent; that control MUST remain body.
- **Authoritative-classification invariants**: the existing AI-classified body and attribution protections MUST remain green and MUST receive no lower-confidence heading mutation or hint.
- **Universal-rule review**: changed tests and production logic MUST contain no document-specific title strings used to drive classification. Example strings in tests may describe synthetic content, but changing those strings MUST NOT change the outcome when source metadata stays constant.
- This work adds no credit/subtraction rule to validation metrics. The mandatory anti-vacuum proof is nevertheless supplied at the classification boundary by the paired real-heading and body-control cases above.

## Assumptions

- Existing paragraph metadata is the authoritative source of role and form evidence during this feature; this scope does not invent missing importer metadata.
- A universal source form signal is acceptable only when it is already represented in paragraph metadata and its decision does not depend on the words in a particular document.
- The current importer-first architecture remains in force; there is no separate AI structure-recognition stage to restore as part of this work.
- A heading lost because an upstream PDF/DOC import supplied only `role=body` and no reusable structural/form evidence is an accepted residual until a separate, evidence-backed importer fix exists.
- Focused verification will use the canonical WSL entry point defined by `AGENTS.md`; full-suite verification belongs to the later implementation phase, not specification creation.
