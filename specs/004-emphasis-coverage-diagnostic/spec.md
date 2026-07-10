# Feature Specification: Emphasis-coverage diagnostic (bold / italic visibility)

Date: 2026-07-10
Status: Implemented (2026-07-10). Live Money: bold 0.93, italic 0.64 — matches audit floor; advisory, non-gating.
Owner surface: `translation_quality_report` — a new emphasis-coverage diagnostic + advisory check
Companion: `docs/specs/GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR_2026-07-09.md`; `specs/002-gate-report-honesty/spec.md`
Changelog:
- 2026-07-10 — Created from an emphasis-coverage audit of four fresh full-tier runs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Emphasis loss becomes visible (Priority: P1 for this feature; overall priorities 2 & 3)

An operator reads the report. It shows how much of the source's bold and italic emphasis survived into the
output. A document that dropped most of its italics is no longer indistinguishable from one that preserved them.

**Why this priority:** bold (priority 2) and italic (priority 3) are two of the project's four stated quality
priorities, and today they are measured NOWHERE. A book can lose 100% of its italics and pass acceptance.

**Independent Test:** run any book; the report carries `emphasis_coverage` with source and output bold/italic
counts and retention ratios.

**Acceptance Scenarios:**

1. **Given** a source with bold/italic runs and an output that preserved them, **When** the report is built,
   **Then** `emphasis_coverage` reports high retention ratios.
2. **Given** an output that stripped all italics, **When** the report is built, **Then** the italic retention
   ratio is near zero and an advisory signal is present — but acceptance is NOT hard-failed by it.
3. **Given** a source paragraph that is a heading, **When** counts are computed, **Then** it is excluded from
   the body-emphasis counts (headings become a Word style, not body bold).

### Edge Cases

- The import path carries no emphasis signal at all (neither `pdf_emphasis_runs` nor inline `**`/`*`). Then
  emphasis loss is UNDETECTABLE for that document and MUST be reported as not-measured, never guessed
  (Constitution VII, "No source signal, no repair").
- The source count is zero (a document with no emphasis). A ratio of 0/0 must be reported as not-applicable, not
  as 0% retention.

## Verified findings

Verified 2026-07-10. Saved fixtures not used for live claims (Constitution VIII).

- **No emphasis measurement exists.** Grepping `src/` for bold/italic/emphasis touchpoints: code EMITS emphasis
  (`processing/processing_runtime.py`, `document/extraction.py::_apply_run_markdown`) and RESTORES it
  (`generation/formatting_transfer.py` paragraph-level), but nothing MEASURES retention. `_normalize_text_for_mapping`
  (`formatting_transfer.py`) deletes `*`/`**` before comparison, so emphasis is stripped and never counted.
- **A book can lose all italics and pass.** No check in `validation/acceptance.py` or `validation/structural.py`
  reads bold/italic/emphasis. The mapping/threshold checks count paragraph coverage only.
- **The source signal exists on both import paths.** PDF: `ParagraphUnit.pdf_emphasis_runs`
  (`core/models.py:258`, char-level `(text, is_bold, is_italic)`). DOCX: inline `**`/`*` in `ParagraphUnit.text`
  from `_apply_run_markdown`. So loss IS in-principle detectable (no import path lacks the signal). Commit
  `57f93e4` established the PDF signal (its log: lietaer italic runs 3→798, mazzucato 259→885).
- **Measured floor (four books, char-runs vs DOCX body runs):** italic retention clusters ~0.54–0.64; bold is
  low and volatile because much source "bold" is heading text that correctly becomes a Heading STYLE, not a body
  bold run. The raw ratio conflates out-of-scope regions — hence the diagnostic must exclude heading-role
  paragraphs and is advisory, not a hard gate.
- **The advisory pattern exists.** `theology_style_deterministic_issues_present` (`acceptance.py:633`,
  `failed_reason="advisory_only"`) is a reported-but-non-gating check to mirror. The diagnostics payload is
  assembled in `_map_source_target_paragraphs` (`formatting_transfer.py:2034`, additions near `:2609`), where
  source paragraphs — and the target — are in scope.

## Requirements *(mandatory)*

### Functional Requirements

> Binding (Constitution VII): counts key on the source-declared emphasis signal (`pdf_emphasis_runs` or inline
> markdown) and on the paragraph role. No word lists, no per-book literals. Where the signal is absent, the
> metric is not-measured — never inferred.

- **FR-001**: A new `emphasis_coverage` diagnostic is added to the report, carrying `source_bold`,
  `source_italic`, `output_bold`, `output_italic`, and `bold_retention_ratio` / `italic_retention_ratio`.
- **FR-002**: Source counts use `pdf_emphasis_runs` when present, else inline `**`/`*` spans in the paragraph
  text. Heading-role paragraphs are EXCLUDED (they map to a Heading style, not body emphasis).
- **FR-003**: Output counts use the produced DOCX body runs (`run.bold` / `run.italic`), excluding
  Heading-styled paragraphs.
- **FR-004**: When source emphasis count is zero, the corresponding ratio is reported not-applicable (not 0%).
- **FR-005**: The metric is surfaced as an ADVISORY check (mirror `advisory_only`) — it MUST NOT hard-fail
  acceptance. No hard retention threshold is invented from the four-book corpus.
- **FR-006**: If a document's import path carries no emphasis signal at all, `emphasis_coverage` records
  `measured=false` with a reason, rather than emitting misleading zero counts.

### Key Entities

- **ParagraphUnit** — carries `role`, `pdf_emphasis_runs`, `is_bold`/`is_italic`, `text`.
- **Emphasis coverage** — `{source_bold, source_italic, output_bold, output_italic, bold_retention_ratio,
  italic_retention_ratio, measured}`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all four books, the report carries `emphasis_coverage` with non-null source and output counts
  (all four are PDF, so the signal is present).
- **SC-002**: A synthetic source with 10 italic runs whose output preserved 10 → ratio 1.0; whose output
  preserved 0 → ratio 0.0 with an advisory signal and NO acceptance hard-fail.
- **SC-003**: A synthetic heading-role paragraph with bold text does not inflate the body-bold source count.
- **SC-004**: Full suite green; pyright ratchet ≤ 244.

## Non-goals

- **Not hard-gating on emphasis.** Advisory-only. A hard threshold needs more than four books of evidence.
- **Not restoring lost emphasis.** This makes loss visible; it does not change what the pipeline emits.
- **Not measuring emphasis inside TOC / footnotes / front-matter** beyond the heading-role exclusion — full
  region-gating (like the pass-through machinery) is a refinement, not required for the first advisory metric.
- **Not touching the DOCX assembly, thresholds, or other detectors.**
- Where an import path carries no emphasis signal, loss is ACCEPTED as not-measured (Constitution VII).

## Anti-regression

- **The number must not become a silent gate.** A near-zero ratio produces an advisory signal only; a test must
  assert acceptance still passes (all else equal) with `italic_retention_ratio = 0`.
- **Heading exclusion must hold.** A counter-test: a heading-role paragraph's bold does not enter the body-bold
  source count (else every book looks like it "lost" bold that was correctly turned into a Heading style).
- **No-signal path must be honest.** A document with neither `pdf_emphasis_runs` nor inline markup reports
  `measured=false`, not `0/0` presented as loss.
- **Verify on all four books by reading the produced report** (Constitution VIII); confirm the numbers are
  plausible against the audit's floor (italic ~0.5–0.65) and explain any large deviation before closing.

## Assumptions

- The target DOCX (or its paragraph runs) is reachable at the diagnostics-assembly point in
  `_map_source_target_paragraphs`; if only source paragraphs are in scope there, output counts are computed
  where the produced DOCX is available and threaded into the report — that wiring is in scope for FR-003.
- `pdf_emphasis_runs` concatenation equals `paragraph.text` (established by `57f93e4`), so counting runs by flag
  is a faithful source measure.
