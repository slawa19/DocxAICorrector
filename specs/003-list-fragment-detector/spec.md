# Feature Specification: List-fragment detection keyed on source list context

Date: 2026-07-10
Status: ACTIVE forward spec
Owner surface: the `list_fragment_regressions_present` acceptance axis (priority 4 — "no broken paragraphs")
Companion: `docs/specs/GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR_2026-07-09.md` (blocker 4);
`specs/002-gate-report-honesty/spec.md`
Changelog:
- 2026-07-10 — Created from a break-detector audit of four fresh full-tier runs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A cross-reference sentence does not fail the book (Priority: P1)

A body paragraph that ends in a number-and-period — a cross-reference ("…как мы видели в главе 7."), a year
("…в 1929."), a citation ("…p. 12.") — is prose, not a broken list item. It must not fail acceptance.

**Why this priority:** today one such sentence hard-fails a whole book. It is the gate lying — the same class of
defect this session has been removing.

**Independent Test:** run Mazzucato full-tier; `list_fragment_regressions_present` does not fail on the
paragraph ending "…как мы видели в главе 7.".

**Acceptance Scenarios:**

1. **Given** a body paragraph ending in a trailing ordinal with NO source-backed list entry as itself or as
   either adjacent entry, **When** the gate runs, **Then** it is NOT flagged as a list-fragment regression.
2. **Given** a genuinely broken numbered-list item — a fragment whose neighbour IS a source-backed list entry —
   **When** the gate runs, **Then** it is still flagged.
3. **Given** bare standalone footnote/page numbers ("18.", "1491.") with no list context, **When** the gate
   runs, **Then** they are not treated as body list-fragment regressions (footnotes are out of scope).

### Edge Cases

- A carry-over sample whose entry could not be resolved to a markdown line (no `line`, or line off the end).
- The fallback path (`used_fallback`, no registry) where entries carry no role — behaviour must not change.
- A real broken list item whose source role was ALSO lost (`role=body`, `list_kind=None`, no list neighbour):
  by Constitution VII this is ACCEPTED, not flagged — there is no source signal to key on.

## Verified findings

Verified 2026-07-10 against fresh runs. Saved fixtures not used for live claims (Constitution VIII).

- **One prose sentence fails a book.** Mazzucato `20260710T_mazzucato_fixed` line 2213 is a 693-char body
  paragraph ending "…как мы видели в главе 7." It matches the carry-over pattern
  `^(?:(?P<current>\d+)\.\s+)?(?P<body>.+?)\s+(?P<next>\d+)\.$` in
  `collect_list_fragment_regression_samples` (`src/docxaicorrector/pipeline/output_validation.py`). Its entry is
  `role=body, list_kind=None`; both neighbours are body/heading. Nothing list-like is near it.
- **One non-creditable sample hard-fails.** `_is_reviewable_list_fragment_residue`
  (`src/docxaicorrector/pipeline/late_phases.py`) returns False as soon as ONE residue sample is non-creditable,
  turning soft review into an acceptance failure. That one sample is the cross-reference sentence.
- **Zero genuine catches.** Across all four books the detector caught 0 real broken body list items and produced
  1 false positive that reaches the gate (Mazzucato). (14 genuine mid-sentence paragraph splits exist across the
  books; NO axis reports them — a separate false-negative gap, out of scope here.)
- **The source signal is already available and already used.** `_is_source_backed_list_entry`
  (`late_phases.py:1845`) keys on `list_kind ∈ {ordered, unordered, list}`; it already collapsed Lietaer 20→0 and
  Mazzucato 66→5 inside `_resolve_list_fragment_regression_gate_samples` (`late_phases.py:1789`). The line→entry
  map `_build_source_backed_entry_by_markdown_line` (`late_phases.py:1818`) is already built there. So an
  adjacent-entry list-context check needs NO new plumbing.

## Requirements *(mandatory)*

### Functional Requirements

> Binding (Constitution VII): the decision keys on the source-declared `list_kind` role of the sample's entry and
> its neighbours — never on the text shape (a trailing number). "No source signal, no repair": a fragment with no
> list context and no list role is ACCEPTED.

- **FR-001**: A carry-over sample is a list-fragment regression only if it has SOURCE LIST CONTEXT: the sample's
  resolved entry is a source-backed list entry, OR the immediately preceding or following assembly entry is.
- **FR-002**: A sample with no list context (its entry and both neighbours are non-list) MUST NOT reach the
  hard-fail decision. It is dropped from the list-fragment axis.
- **FR-003**: The existing source-backed-list credit (a sample matching a real list entry's text or line) is
  preserved — do not regress the Lietaer 20→0 / Mazzucato 66→5 collapse.
- **FR-004**: The fallback / legacy path (`source_backed_entry_authority` false, or no assembly entries) is
  unchanged — no entries means no list-context signal, so behave exactly as today.
- **FR-005**: A genuinely broken list item whose neighbour is a source-backed list entry is still flagged and can
  still hard-fail (do not blunt priority 4 where the signal exists).

### Key Entities

- **FinalAssemblyEntry** — carries `list_kind`, `from_registry`, `used_fallback`, `text`, ordered in a sequence.
- **List context** — the sample's entry, or entry[k-1] / entry[k+1], being a source-backed list entry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Mazzucato full-tier no longer fails `list_fragment_regressions_present` on the "…в главе 7."
  paragraph; if Mazzucato passes acceptance, that is the intended result.
- **SC-002**: On all four books, no acceptance failure is caused by a prose paragraph ending in a number.
- **SC-003**: A synthetic broken numbered-list item adjacent to a real list entry is still flagged (counter-test).
- **SC-004**: Full suite green; pyright ratchet ≤ 244.

## Non-goals

- **Not adding a broken-paragraph detector** for the 14 mid-sentence splits the audit found. That false-negative
  gap is a separate axis and a separate decision.
- **Not changing the repair pass** `normalize_list_fragment_regressions_markdown` — only the gate's decision of
  what counts as a regression. (The repair pass is already source-heading-guarded from spec 001.)
- **Not touching thresholds, other detectors, or the DOCX assembly.**
- A broken list item with no source list signal anywhere near it is ACCEPTED (Constitution VII).

## Anti-regression

- **The source-backed-list credit must survive.** Re-verify Lietaer and Mazzucato still collapse their large raw
  counts; a test must assert a sample matching a real list entry is still dropped.
- **A real broken list item must still hard-fail** when a list neighbour exists — counter-test with a synthetic
  `ordered`/`unordered` neighbour entry.
- **The entry-less predicate tests must be reconciled.** `test_list_fragment_broken_body_list_still_hard_fails`
  and siblings in `tests/test_gate_detectors_stage2.py` feed samples with NO assembly entries; the new
  list-context filter needs entries, so it must not silently pass/fail those — state explicitly how the
  entry-less path behaves and keep those tests meaningful.
- **Verify on all four books by reading the produced report**, not a fixture (Constitution VIII). A fix that
  helps Mazzucato and changes another book's verdict must be caught before closing.

## Assumptions

- `assembly_entries` is an ordered sequence aligned to non-empty markdown lines (the existing
  `_build_source_backed_entry_by_markdown_line` relies on this), so entry[k±1] are the true document neighbours.
- The false-positive class is entirely "prose ending in a number with no list nearby"; the audit found no other
  class reaching the gate.
