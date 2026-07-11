# Feature Specification: Emit unmapped-target review-items (the missing UI review-data class)

Date: 2026-07-11
Status: IMPLEMENTED (2026-07-11). Verified by 6 deterministic tests (incl. the anti-vacuum SC-002 counter-proof)
over the classifier + summary + emitter; full suite green (1973 passed), pyright ratchet 244. DATA-only — no
verdict change (SC-004).
Owner surface: the production review-item emission in `late_phases.py`, fed by the target passthrough
classifier in `validation/formatting_coverage.py`.
Companion: `specs/002-gate-report-honesty/spec.md` (policy-independent review-item emission);
`docs/specs/UI/FORMATTING_DISCREPANCY_REPORTING_SPEC_2026-06-15.md` (the UI that consumes this class);
`docs/specs/GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR_2026-07-09.md` residual (b);
`specs/010-production-acceptance-semantics/spec.md` (coverage is review-DATA, not a gate — this makes the
target side of that data actually reviewable, item by item).
Changelog:
- 2026-07-11 — Created after the pre-UI UI-data-gap assessment. Verified: `unmapped_source` has a per-paragraph
  review-item emitter (`late_phases.py:2650`) but the TARGET side emits only a COUNT
  (`acceptance.py:530-556`) — the UI cannot list WHICH target paragraphs are unmapped. Two adjacent gaps in the
  same assessment were closed differently: `[КРИТ]`/false_pair is REAL and correct-and-latent (kept, already
  test-covered — do not touch); `note_fragment` is SCOPED OUT (footnotes are out of scope per Constitution VII;
  short-note residue already flows through this unmapped-target set as `short_note_or_marker`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The UI can list which target paragraphs are unmapped (Priority: P1; overall priority 2, pre-UI UI-data)

The production report surfaces, per genuinely-unmapped TARGET paragraph (after passthrough crediting), a review
item with its text — mirroring the existing unmapped-SOURCE review items — so the UI's `unmapped_target`
`[ПРОВЕРКА]` row has data, not just a number.

**Why this priority:** spec 010 decided the coverage axis is review-DATA. For the SOURCE side that data is
already itemized; for the TARGET side only a count exists, so the UI would show "N unmapped target paragraphs"
with nothing to inspect. The data to itemize is already computed and then dropped.

**Independent Test:** run the target passthrough classifier + summary over a saved report payload; a genuinely
unmapped body target paragraph appears as an `unmapped_target_paragraphs_review_required` item with its
`text_preview`, while a front-matter/reference/caption target paragraph (credited passthrough) does NOT.

**Acceptance Scenarios:**

1. **Given** a payload whose `unmapped_target_indexes` contains a genuine body-prose target paragraph (not in
   any passthrough category), **When** the report is built, **Then** a review item
   `unmapped_target_paragraphs_review_required` is emitted carrying that paragraph's `text_preview`, severity
   `review` (`[ПРОВЕРКА]`).
2. **Given** an unmapped target index that classifies as front-matter / references / caption / part / index /
   attribution / page-furniture (credited passthrough), **When** the report is built, **Then** it is NOT emitted
   as a review item (it is credited, not a loss — the same passthrough classification spec 010 relies on).
3. **Given** more retained unmapped target paragraphs than the sample cap, **When** items are emitted, **Then**
   the first item carries an `aggregate_count`, mirroring the source emitter's capping invariant.

### Edge Cases

- No role-aware target summary (no target-split accounting) — fall back to a single count-only review item
  (mirror the source emitter's `else` branch, `late_phases.py:2694-2701`), never silently emit nothing.
- Zero retained unmapped target paragraphs — emit no review item (nothing to review).

## Verified findings

Verified 2026-07-11 by code reading (Constitution VIII — the change is verified by deterministic tests over
saved payloads; no live run needed).

- **Source has an itemizer; target does not.** `_emit_unmapped_source_discrepancy_review_items`
  (`late_phases.py:2650-2701`) emits `unmapped_source_paragraphs_review_required` (and role_loss) items. There is
  no target counterpart; the target contributes only the `unmapped_target_threshold` check's `actual`
  (`acceptance.py:530-556`).
- **The data is already computed and then dropped.** `classify_passthrough_unmapped_target`
  (`formatting_coverage.py:604-684`) resolves, per unmapped target index, its `text_preview` (`:649`) and its
  passthrough category, and returns `retained_indexes` (`:680`) — the genuinely-unmapped set after crediting.
  But `resolve_role_aware_formatting_unmapped_target_summary` (`formatting_coverage.py:948-996`) keeps only
  counts (`:967-984`); it does NOT carry `retained_indexes` or their text outward.
- **The emission point exists.** `effective_unmapped_target_count` is computed at `late_phases.py:3005-3017`
  from `role_aware_target_summary`; that is where the target items belong, adjacent to the source emission.
- **The winning payload carries the samples.** The summary returns `**max_summary` (`:991`) — the payload with
  the max effective count — so retained samples added to each per-payload summary flow out via `max_summary`,
  consistent with how the existing counts are chosen.
- **Universal (Constitution VII):** the retained set is exactly what survives the passthrough classification
  (region boundaries + form) that already credits front-matter/references/captions — no word list, no per-book
  literal. `retained` is the anti-vacuum residue: real body that was NOT credited.

## Requirements *(mandatory)*

> Binding (Constitution VII): the emitted items are precisely the passthrough-classifier's `retained` set — real
> unmapped body after region/form crediting. No new detector, no per-book literal; a credited passthrough
> paragraph is never emitted, a genuine unmapped body paragraph always is.

- **FR-001**: `classify_passthrough_unmapped_target` also returns `retained_samples` — a list of
  `{target_index, text_preview}` for each retained (genuinely-unmapped) index, using the `text_preview` already
  resolved at `formatting_coverage.py:649`. `retained_indexes`/`retained_count` are unchanged.
- **FR-002**: `resolve_role_aware_formatting_unmapped_target_summary` threads a capped `retained_samples`
  (first 8, mirroring the source cap at `late_phases.py:2670`) into each per-payload summary, so `**max_summary`
  carries the winning payload's samples outward.
- **FR-003**: A new `_emit_unmapped_target_discrepancy_review_items` (mirroring
  `_emit_unmapped_source_discrepancy_review_items`) emits `unmapped_target_paragraphs_review_required` items with
  severity `review`, one per retained sample (with `text_preview`), applying the same capping/`aggregate_count`
  invariant. Called from the target emission site (after `late_phases.py:3017`), policy-independent (emitted under
  advisory too, like the source items — GATE_TRUSTWORTHINESS Task B).
- **FR-004**: When `role_aware_target_summary is None` (no target-split accounting), emit a single count-only
  `unmapped_target_paragraphs_review_required` item carrying `effective_unmapped_target_count` (mirror the source
  `else` branch), never nothing.
- **FR-005**: A credited passthrough target paragraph (front-matter/references/caption/part/index/attribution/
  page-furniture) is NEVER emitted as a review item — it is not in `retained`.
- **FR-006**: This is DATA emission only — it does NOT change any gate/verdict (coverage stays NOT-APPLICABLE in
  production per spec 010) and changes NO delivered bytes.

### Key Entities

- **Retained unmapped target paragraph** — an `unmapped_target_indexes` entry not in any passthrough category;
  `{target_index, text_preview}`.
- **`unmapped_target_paragraphs_review_required` review item** — severity `review` (`[ПРОВЕРКА]`), the target
  counterpart of `unmapped_source_paragraphs_review_required`.

## Success Criteria *(mandatory)*

- **SC-001**: Over a saved payload with a genuine unmapped body target paragraph, the report's review-items
  include an `unmapped_target_paragraphs_review_required` item carrying that paragraph's `text_preview`.
- **SC-002 (anti-vacuum counter-proof)**: A payload whose unmapped target indexes are ALL passthrough
  (front-matter/references/caption) emits NO `unmapped_target_paragraphs_review_required` item, AND a payload
  with one genuine body paragraph among passthrough noise emits exactly one item for the body paragraph — real
  body is still surfaced, credited passthrough is not.
- **SC-003**: The capping/`aggregate_count` invariant matches the source emitter (first item carries
  `aggregate_count` when retained > cap).
- **SC-004**: No gate/verdict change — `acceptance_verdict.failed_checks` is byte-identical on the four saved
  reports before/after (DATA-only, per spec 010 / FR-006).
- **SC-005**: Full suite green; pyright ratchet ≤ 244.

## Non-goals

- **Not gating on unmapped target** — coverage stays review-data (spec 010). This only ITEMIZES the existing
  count.
- **Not creating a `note_fragment` class** — footnotes are out of scope (Constitution VII); short-note residue
  already appears in this set tagged `short_note_or_marker` and is a UI-copy concern, not a new data class.
- **Not touching `[КРИТ]`/false_pair** — it is real, correct-and-latent, and already test-covered; forcing it to
  fire on live data would require a forbidden per-book literal.
- **Not changing the passthrough categories or boundaries** — reuse them exactly.
- **Not changing delivered bytes or the DOCX.**

## Anti-regression

- **Anti-vacuum (Constitution VII):** SC-002 — a genuine unmapped body target paragraph is ALWAYS emitted; a
  credited passthrough one is NEVER emitted. This is the counter-proof that the crediting does not vacuum real
  losses.
- **Verdict unchanged:** SC-004 — `failed_checks` identical before/after; this is DATA-only (spec 010 keeps
  coverage NOT-APPLICABLE in production).
- **Capping invariant preserved:** the source and target emitters share the cap + `aggregate_count` behavior.
- **Degrade-safe:** no target summary → a count-only item, never silence (FR-004).

## Assumptions

- `text_preview` on the target registry entry is a faithful, already-available preview of the target paragraph
  (used verbatim by the classifier at `formatting_coverage.py:649`).
- The winning payload (`max_summary`) is the right source of samples — the same payload whose count is already
  reported (consistent with the existing summary selection at `formatting_coverage.py:990`).
