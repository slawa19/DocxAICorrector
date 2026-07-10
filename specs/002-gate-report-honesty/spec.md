# Feature Specification: Honest report data the UI can bind to

Date: 2026-07-10
Status: Implemented (2026-07-10). Verdict half `dda7f5c`, anchor half `8b9fd4c`; verified on live runs.
Owner surface: `translation_quality_report` (the report the UI and `formatting_review.txt` consume)
Companion: `docs/specs/UI/FORMATTING_DISCREPANCY_REPORTING_SPEC_2026-06-15.md` (the consumer);
`docs/specs/GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR_2026-07-09.md` (its blocker 6 remains open);
`specs/001-heading-role-preservation/spec.md`
Changelog:
- 2026-07-10 — Created from a UI-readiness audit of four fresh full-tier runs.
- 2026-07-10 — Implemented in two commits. Verdict half (FR-001/002/008/009): `dda7f5c`; production
  verdict now agrees with the harness (Money live: both pass; Mazzucato deterministic: both fail on the real
  list_fragment defect). Third cause found during implementation: production has NO acceptance thresholds
  configured, so they are now NOT-APPLICABLE, not silent zero-failures. Fourth thing found: the delivered DOCX
  does not exist yet at verdict time on the reader-cleanup path, so `output_docx_openable` is NOT-APPLICABLE
  there (never guessed). Anchor half (FR-004/005/006): `8b9fd4c`; verified live on `20260710T_lietaer_anchors` —
  zero `[[DOCX_` leaks, `$` aggregates into a count line, `### CONTENTS` → `CONTENTS`.
  CAVEAT: FR-005's rendered "примените стиль «Заголовок N»" line is unit-verified but was NOT exercised in that
  live report, because the only role-loss item present was the anchorless `$` (aggregated). It will render the
  first time a locatable role-loss item appears.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The report agrees with itself (Priority: P1)

An operator (or the UI) reads the pass/fail verdict from the produced report. It says the same thing the
acceptance harness says about the same run. A document that passed is never shown as failed.

**Why this priority:** the UI's top-level state binds to this field. If it is wrong, everything below it is
noise. Today it is wrong on every run.

**Independent Test:** run any book; compare `acceptance.passed` (harness) with
`translation_quality_report.acceptance_verdict.passed` (report). They must agree, and their `failed_checks` must
agree except for checks production genuinely cannot evaluate.

**Acceptance Scenarios:**

1. **Given** a run whose output DOCX opened successfully, **When** the report is written, **Then**
   `acceptance_verdict` does NOT list `output_docx_openable` as failed.
2. **Given** a run where no source↔output structural comparison was performed (production has no source DOCX),
   **When** the report is written, **Then** `structural_comparison_available` is absent or explicitly marked
   not-applicable — never counted as a failure.
3. **Given** a run the harness accepts, **When** the report is written, **Then** `acceptance_verdict.passed`
   is `true`.

### User Story 2 - A discrepancy the user can actually find (Priority: P2)

A translator opens `formatting_review.txt`. Every item quotes a fragment of real text they can search for in the
DOCX, and tells them what to do — which Word style to apply.

**Why this priority:** an anchor the user cannot locate makes the report unusable, and internal ids are
explicitly forbidden by the UI spec.

**Independent Test:** for every `formatting_review_items[].sample.text`, assert it contains no `[[DOCX_…]]`
placeholder and is not a bare punctuation token.

**Acceptance Scenarios:**

1. **Given** a review item whose paragraph text contains `[[DOCX_PARA_p0052]]` or `[[DOCX_IMAGE_…]]`, **When**
   the item is serialized, **Then** the placeholder is removed from the anchor; if nothing human-readable
   remains, the item is aggregated into a count rather than shown.
2. **Given** a `role_loss` item, **When** it is rendered, **Then** it names the concrete action — the Word style
   the user should apply (e.g. "Заголовок 1"), derived from the source `role` / `heading_level`.
3. **Given** an item with no locatable anchor at all, **When** it is rendered, **Then** it appears in a count,
   not as an empty row.

### Edge Cases

- The source paragraph text is a single symbol (`$`) — a real Lietaer case. There is nothing to anchor on.
- The anchor is entirely untranslated structural text (`### CONTENTS`) — TOC, out of scope by project rule.
- Production has no source DOCX (PDF input), so structural comparison is genuinely unavailable — a third state,
  neither pass nor fail.

## Verified findings

Verified 2026-07-10 against fresh runs `20260710T_lietaer_fixed`, `20260710T_money_fixed4`,
`20260710T_mazzucato_fixed`, `20260710T_creatingwealth_fixed`. Saved fixtures were not used (Constitution VIII).

- **The embedded verdict is permanently failed.** `_build_report_context_for_acceptance`
  (`src/docxaicorrector/pipeline/late_phases.py:2644`) returns `"output_artifacts": {}` (line 2657), and its call
  site passes `structural_checks_builder=None`. `build_acceptance_verdict` reads
  `output_artifacts.get("output_docx_openable")` (`src/docxaicorrector/validation/acceptance.py:350-352`) and
  emits `structural_comparison_available` (`acceptance.py:629`). Both therefore fail on every run.
- **Same run, two verdicts.** `20260710T_lietaer_fixed`: harness `acceptance.passed = True`, `failed_checks = []`.
  Report `translation_quality_report.acceptance_verdict.passed = False`, `failed_checks =
  [output_docx_openable, formatting_diagnostics_threshold, unmapped_source_threshold, unmapped_target_threshold,
  structural_comparison_available]`.
- **Production has no acceptance thresholds at all** (third cause, found while implementing; the first draft of
  this spec wrongly blamed the empty context for the threshold failures). The config keys
  `acceptance_max_unmapped_source_paragraphs` / `..._target_paragraphs` exist ONLY as two constants
  (`late_phases.py:2599-2600`); they are absent from `config.toml` and set nowhere. So
  `_resolve_acceptance_thresholds` (`late_phases.py:2628`) always returns `(0, 0, False)` and any unmapped
  paragraph fails the check. The harness gets real thresholds per book from `corpus_registry.toml`
  (`document_profile.max_unmapped_source_paragraphs`) — a source production cannot have, because the user uploads
  an arbitrary document.
- **Director decision (2026-07-10):** production must not judge what it cannot judge. Threshold and structural
  checks become NOT-APPLICABLE in the production verdict rather than silently failing. A per-document expected
  loss budget is a test-corpus concept and is not invented for arbitrary uploads.
- **Anchors leak internal ids.** Real `formatting_review_items[].sample.text` values from that same run:
  `'$'`, `'### 67– 69'`, `'[[DOCX_PARA_p0052]]\n### CONTENTS'`, `'### WISPOS'`.
- **The UI spec forbids exactly this.** `docs/specs/UI/FORMATTING_DISCREPANCY_REPORTING_SPEC_2026-06-15.md`
  requires each item to carry an anchor the user can locate — "preceding text snippet or the paragraph text
  itself — never an internal paragraph id" — plus a concrete manual action naming the Word style, and lists "no
  internal ids, strategy names, or basis labels in the user-facing body" among its non-goals.
- **Blocker 6 is not discharged.** The shared verdict module IS shared (`acceptance.py`, called from
  `late_phases.py:2619` and from the harness), but the production caller feeds it an empty context, so the
  numbers do not match. Parity of code, not of output. The original parity claim was validated on saved harness
  reports, which never exercise the production context builder — which is why this survived.

## Requirements *(mandatory)*

### Functional Requirements

> Binding (Constitution VII): rules key on the report's own provenance and on the source-declared role. No word
> lists, no per-book literals. Where production genuinely lacks a signal, the check is marked not-applicable —
> never silently failed, never guessed ("No source signal, no repair").

- **FR-001**: `_build_report_context_for_acceptance` MUST pass the run's real `output_artifacts` (at minimum
  `output_docx_openable`) instead of `{}`.
- **FR-002**: A check production cannot evaluate MUST NOT be reported as failed. `structural_comparison_available`
  MUST be omitted, or carry an explicit not-applicable state distinguishable from both pass and fail.
- **FR-003**: For a given run, `translation_quality_report.acceptance_verdict.passed` MUST equal the harness
  verdict, and the two `failed_checks` sets MUST be equal after removing not-applicable checks.
- **FR-004**: A user-facing anchor (`formatting_review_items[].sample.text` and its source counterpart) MUST NOT
  contain `[[DOCX_PARA_…]]`, `[[DOCX_IMAGE_…]]`, or any other internal placeholder.
- **FR-005**: A `role_loss` item MUST carry the concrete manual action — the target Word style name derived from
  the source `role` / `heading_level` (e.g. `heading_level=1` → "Заголовок 1").
- **FR-006**: An item whose anchor, after placeholder removal, holds no human-locatable text MUST be aggregated
  into a count rather than emitted as a row with an empty or single-symbol anchor.
- **FR-007**: The report MUST keep emitting review-item DATA under the advisory policy (do not regress `291a24a`).
- **FR-008**: When an acceptance threshold is not configured, the corresponding check MUST be reported as
  NOT-APPLICABLE, not failed. A threshold of `0` MUST NOT be silently substituted for "unconfigured".
- **FR-009**: A check has three distinguishable states in the data: passed, failed, not-applicable. Only failed
  checks appear in `failed_checks`; `passed` is true when `failed_checks` is empty. The harness path — which
  DOES supply thresholds and a structural comparison — MUST produce a byte-identical verdict to today's.

### Key Entities

- **Acceptance context** — the mapping `build_acceptance_verdict` consumes: `result`, `runtime_config`,
  `translation_quality_report`, `formatting_diagnostics`, `output_artifacts`, `runtime`,
  `reader_cleanup_evidence`, `preparation_diagnostic_snapshot`.
- **Review item** — `{reason, label, count, severity, sample:{line, text, source_text, role, structural_role}}`.
- **Anchor** — the human-locatable fragment inside `sample.text`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all four books, `acceptance_verdict.passed` equals the harness `acceptance.passed`.
- **SC-002**: On all four books, zero `formatting_review_items[].sample.text` values contain `[[DOCX_`.
- **SC-003**: On all four books, zero review items render with an anchor shorter than 3 visible characters; such
  items are aggregated into a count instead.
- **SC-004**: Every `role_loss` item names a Word style in its rendered action line.
- **SC-005**: The full test suite stays green; the pyright ratchet does not rise above 244.

## Non-goals

- **Not changing any threshold, detector, or credit rule.** The numbers stay as they are; only the context they
  are computed from is repaired.
- **Not touching the DOCX assembly.** This changes report data, nothing the user's document is built from.
- **Not closing the `final_markdown` ↔ `runtime_display_markdown` divergence.** The gate still measures a
  different artifact than the one delivered. Consequence for this spec: SC-002 guarantees the anchor's FORM is
  honest, not that the anchor still exists in the delivered DOCX. That larger decision is deferred.
- **Not adding the missing `unmapped_target` and `note_fragment` review-item classes** the UI spec lists.
- **Not validating the `[КРИТ]` path on live data.** `bad_pair_count = 0` on all four books; the path is
  code-complete and unexercised. Deferred, not removed.
- An item that genuinely has no anchor because the source paragraph is a single symbol is ACCEPTED as a counted
  aggregate, not invented (Constitution VII, "No source signal, no repair").

## Anti-regression

- **Advisory emission must survive.** `291a24a` made review-item DATA policy-independent; a counter-test must
  prove items are still emitted under `policy=advisory` after this change.
- **Verdict parity must be asserted on the PRODUCTION context, not a synthetic one.** The original parity claim
  was byte-identical on four saved harness reports and still let this defect through, because the production
  context builder was never exercised. A test must build the production context and assert the verdict equals the
  harness verdict for the same payload.
- **Placeholder stripping must not eat real text.** A paragraph whose text legitimately contains `[[` must not be
  truncated. Counter-test required.
- **A not-applicable check must not silently become a pass.** The three states (passed / failed / not-applicable)
  must be distinguishable in the data; a test must assert that.
- Verify on all four books before closing, by reading the produced report — not a fixture (Constitution VIII).

## Assumptions

- `output_artifacts` carrying at least `output_docx_openable` is reachable at the point where
  `_build_report_context_for_acceptance` is called. If it is not, threading it is in scope for FR-001.
- The source `role` / `heading_level` needed for FR-005 is already on the review item's `sample` (`role` and
  `structural_role` are present today; `heading_level` may need adding to the serializer).
